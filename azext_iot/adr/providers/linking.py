# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Optional

from azure.cli.core.azclierror import (
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from knack.log import get_logger
from rich.console import Console

from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state

console = Console()
logger = get_logger(__name__)


# Default endpoint type discriminator strings used when the caller doesn't
# override them. These match the ARM resource type segments for IoT Hub and
# Device Provisioning Service.
DEFAULT_HUB_ENDPOINT_TYPE = "Microsoft.Devices/IotHubs"
DEFAULT_DPS_ENDPOINT_TYPE = "Microsoft.Devices/ProvisioningServices"

LINK_KIND_HUB = "hub"
LINK_KIND_DPS = "dps"


def _build_identity(mi_system_assigned: bool, mi_user_assigned: Optional[str]) -> dict:
    """Build the inboundCallerIdentity body for a linked endpoint.

    Exactly one of system-assigned or user-assigned must be provided.
    """
    if mi_system_assigned and mi_user_assigned:
        raise MutuallyExclusiveArgumentError(
            "--mi-system-assigned and --mi-user-assigned cannot be used together."
        )
    if not mi_system_assigned and not mi_user_assigned:
        raise RequiredArgumentMissingError(
            "An identity is required: pass either --mi-system-assigned or "
            "--mi-user-assigned <userAssignedIdentityResourceId>."
        )
    if mi_user_assigned:
        return {"type": "UserAssigned", "userAssignedIdentity": mi_user_assigned}
    return {"type": "SystemAssigned"}


def _endpoint_section_path(kind: str) -> tuple:
    """Return (top_key, sub_key) pair for the endpoint dictionary on the
    namespace ``properties`` payload. Hub links live under
    ``messaging.endpoints``; DPS links live under ``provisioning.endpoints``.
    """
    if kind == LINK_KIND_HUB:
        return "messaging", "endpoints"
    if kind == LINK_KIND_DPS:
        return "provisioning", "endpoints"
    raise ValueError(f"Unknown link kind: {kind}")


def _read_endpoint_dict(namespace_resource: dict, kind: str) -> dict:
    """Pluck the endpoint dictionary from a namespace resource (as returned
    by GET). Returns an empty dict if the section is missing."""
    top_key, sub_key = _endpoint_section_path(kind)
    props = (namespace_resource or {}).get("properties", {}) or {}
    section = props.get(top_key, {}) or {}
    return section.get(sub_key, {}) or {}


def _build_endpoint_patch(kind: str, name: str, endpoint_body) -> dict:
    """Wrap an endpoint body in the namespace patch envelope.

    ``endpoint_body`` set to ``None`` removes the endpoint key from the
    additionalProperties dictionary.
    """
    top_key, sub_key = _endpoint_section_path(kind)
    return {
        "properties": {
            top_key: {
                sub_key: {name: endpoint_body},
            }
        }
    }


class LinkProvider(ADRProvider):
    """Provider for managing inbound endpoint links (IoT Hub & DPS) attached
    to a Device Registry namespace."""

    def __init__(self, cmd):
        super(LinkProvider, self).__init__(cmd)

    # --------- read helpers (operate on the namespace GET response) ---------

    def _get_namespace(self, namespace_name: str, resource_group_name: str) -> dict:
        return self.client.namespaces.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
        )

    def show(self, kind: str, link_name: str, namespace_name: str, resource_group_name: str):
        namespace = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _read_endpoint_dict(namespace, kind)
        if link_name not in endpoints:
            raise ResourceNotFoundError(
                f"No {kind} link named '{link_name}' was found on namespace "
                f"'{namespace_name}' in resource group '{resource_group_name}'."
            )
        return endpoints[link_name]

    def list(self, kind: str, namespace_name: str, resource_group_name: str) -> list:
        namespace = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _read_endpoint_dict(namespace, kind)
        # Normalize the additionalProperties dict into a list of {name, ...}
        # entries, matching how Azure CLI lists nested children elsewhere.
        result = []
        for name, body in endpoints.items():
            entry = {"name": name}
            if isinstance(body, dict):
                entry.update(body)
            result.append(entry)
        return result

    # --------- write helpers (PATCH the namespace) ---------

    def add(
        self,
        kind: str,
        link_name: str,
        namespace_name: str,
        resource_group_name: str,
        resource_id: str,
        mi_system_assigned: bool = False,
        mi_user_assigned: Optional[str] = None,
        endpoint_type: Optional[str] = None,
        **kwargs,
    ):
        """Add (or replace) a single endpoint link on the namespace."""
        identity = _build_identity(mi_system_assigned, mi_user_assigned)

        endpoint_body = {
            "resourceId": resource_id,
            "inboundCallerIdentity": identity,
        }
        # DPS endpoint requires endpointType per swagger. For hub it is optional
        # but harmless. Set a sensible default when one isn't provided.
        if endpoint_type is None:
            endpoint_type = (
                DEFAULT_DPS_ENDPOINT_TYPE if kind == LINK_KIND_DPS else DEFAULT_HUB_ENDPOINT_TYPE
            )
        endpoint_body["endpointType"] = endpoint_type

        properties = _build_endpoint_patch(kind, link_name, endpoint_body)

        with console.status(
            f"Adding {kind} link '{link_name}' to namespace {namespace_name}..."
        ):
            poller = self.client.namespaces.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                properties=properties,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def remove(
        self,
        kind: str,
        link_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        """Remove an endpoint link from the namespace. Done via PATCH with
        the endpoint key set to ``null`` (ARM additionalProperties tombstone)."""
        properties = _build_endpoint_patch(kind, link_name, None)

        with console.status(
            f"Removing {kind} link '{link_name}' from namespace {namespace_name}..."
        ):
            poller = self.client.namespaces.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                properties=properties,
            )
            return wait_for_terminal_state(poller, **kwargs)
