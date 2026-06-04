# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Optional

from azure.cli.core.azclierror import (
    ArgumentUsageError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from knack.log import get_logger
from rich.console import Console

from azext_iot._factory import iot_service_provisioning_factory
from azext_iot.adr.common import (
    DPS_ENDPOINT_TYPE,
    IOT_HUB_ENDPOINT_TYPE,
    InboundCallerIdentityType,
    LinkingState,
)
from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state

console = Console()
logger = get_logger(__name__)


DPS_FIRST_REQUIRED_MSG = (
    "Link a DPS to this namespace before adding a Hub. "
    "Run 'az iot adr ns link dps add ...' or 'az iot adr ns link add ...' to add both at once."
)

DPS_CAP_EXCEEDED_MSG = (
    "Namespace already has a linked DPS; use 'az iot adr ns link dps update' "
    "or remove the existing entry first. Only one DPS may be linked per namespace."
)


def _parse_dps_resource_id(dps_resource_id: str) -> dict:
    """Parse a DPS ARM resource ID into its components.

    Expected shape:
        /subscriptions/<sub>/resourceGroups/<rg>/providers/
            Microsoft.Devices/provisioningServices/<name>
    """
    parts = (dps_resource_id or "").strip("/").split("/")
    if (
        len(parts) != 8
        or parts[0].lower() != "subscriptions"
        or parts[2].lower() != "resourcegroups"
        or parts[4].lower() != "providers"
        or parts[5].lower() != "microsoft.devices"
        or parts[6].lower() != "provisioningservices"
    ):
        raise InvalidArgumentValueError(
            f"'{dps_resource_id}' is not a valid Microsoft.Devices/provisioningServices resource ID."
        )
    return {
        "subscription_id": parts[1],
        "resource_group_name": parts[3],
        "name": parts[7],
    }


def _build_inbound_identity(mi_system_assigned: bool, mi_user_assigned: Optional[str]) -> dict:
    """Build the InboundCallerIdentity body from CLI flags. Exactly one variant required."""
    if mi_system_assigned and mi_user_assigned:
        raise ArgumentUsageError(
            "--mi-system-assigned and --mi-user-assigned are mutually exclusive."
        )
    if mi_user_assigned:
        return {
            "type": InboundCallerIdentityType.user_assigned.value,
            "userAssignedIdentity": mi_user_assigned,
        }
    if mi_system_assigned:
        return {"type": InboundCallerIdentityType.system_assigned.value}
    raise RequiredArgumentMissingError(
        "Exactly one of --mi-system-assigned or --mi-user-assigned is required."
    )


def _get_messaging_endpoints(namespace: dict) -> dict:
    return (((namespace or {}).get("properties") or {}).get("messaging") or {}).get("endpoints") or {}


def _get_provisioning_endpoints(namespace: dict) -> dict:
    return (((namespace or {}).get("properties") or {}).get("provisioning") or {}).get("endpoints") or {}


class LinkProvider(ADRProvider):
    def __init__(self, cmd):
        super(LinkProvider, self).__init__(cmd)

    # -------------------- helpers --------------------

    def _get_namespace(self, namespace_name: str, resource_group_name: str) -> dict:
        return self.client.namespaces.get(
            resource_group_name=resource_group_name, namespace_name=namespace_name
        )

    def _patch_messaging_endpoints(
        self,
        namespace_name: str,
        resource_group_name: str,
        endpoints_patch: dict,
        no_wait: bool = False,
        **kwargs,
    ):
        properties = {"properties": {"messaging": {"endpoints": endpoints_patch}}}
        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties=properties,
        )
        if no_wait:
            return poller
        with console.status(f"Updating messaging endpoints on namespace {namespace_name}..."):
            return wait_for_terminal_state(poller, **kwargs)

    # -------------------- hub commands --------------------

    def hub_add(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        hub_resource_id: str,
        mi_system_assigned: bool = False,
        mi_user_assigned: Optional[str] = None,
        availability: Optional[str] = None,
        allocation_weight: Optional[int] = None,
        **kwargs,
    ):
        """Add an IoT Hub messaging endpoint to a namespace (DPS-first preflight)."""
        existing = self._get_namespace(namespace_name, resource_group_name)

        # §2.1 DPS-first: namespace must already have at least one DPS endpoint
        if not _get_provisioning_endpoints(existing):
            raise ArgumentUsageError(DPS_FIRST_REQUIRED_MSG)

        endpoint_body = {
            "endpointType": IOT_HUB_ENDPOINT_TYPE,
            "resourceId": hub_resource_id,
            "inboundCallerIdentity": _build_inbound_identity(mi_system_assigned, mi_user_assigned),
        }
        provisioning = {}
        if availability is not None:
            provisioning["availability"] = availability
        if allocation_weight is not None:
            provisioning["allocationWeight"] = allocation_weight
        if provisioning:
            endpoint_body["provisioning"] = provisioning

        return self._patch_messaging_endpoints(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            endpoints_patch={endpoint_name: endpoint_body},
            **kwargs,
        )

    def hub_update(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        mi_system_assigned: bool = False,
        mi_user_assigned: Optional[str] = None,
        availability: Optional[str] = None,
        allocation_weight: Optional[int] = None,
        **kwargs,
    ):
        """Partial-update an existing IoT Hub messaging endpoint on a namespace."""
        if mi_system_assigned and mi_user_assigned:
            raise ArgumentUsageError(
                "--mi-system-assigned and --mi-user-assigned are mutually exclusive."
            )

        existing = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_messaging_endpoints(existing)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"Hub endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )

        endpoint_patch: dict = {}
        if mi_user_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": InboundCallerIdentityType.user_assigned.value,
                "userAssignedIdentity": mi_user_assigned,
            }
        elif mi_system_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": InboundCallerIdentityType.system_assigned.value
            }

        provisioning_patch = {}
        if availability is not None:
            provisioning_patch["availability"] = availability
        if allocation_weight is not None:
            provisioning_patch["allocationWeight"] = allocation_weight
        if provisioning_patch:
            endpoint_patch["provisioning"] = provisioning_patch

        if not endpoint_patch:
            raise RequiredArgumentMissingError(
                "Provide at least one of --mi-system-assigned, --mi-user-assigned, "
                "--availability, or --allocation-weight."
            )

        return self._patch_messaging_endpoints(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            endpoints_patch={endpoint_name: endpoint_patch},
            **kwargs,
        )

    def hub_remove(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        """Remove an IoT Hub messaging endpoint from the namespace (sets value to null)."""
        existing = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_messaging_endpoints(existing)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"Hub endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )

        endpoint = endpoints.get(endpoint_name) or {}
        linking_state = endpoint.get("linkingState")
        if linking_state == LinkingState.succeeded.value:
            hub_resource_id = endpoint.get("resourceId") or "<hub-resource-id>"
            raise ArgumentUsageError(
                f"Hub endpoint '{endpoint_name}' is in linkingState 'Succeeded'. "
                "The namespace PATCH path cannot unlink a successfully linked Hub; "
                "to break the link you must delete the underlying IoT Hub resource. "
                f"Run: az iot hub delete --ids {hub_resource_id}"
            )

        return self._patch_messaging_endpoints(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            endpoints_patch={endpoint_name: None},
            **kwargs,
        )

    def hub_show(self, endpoint_name: str, namespace_name: str, resource_group_name: str):
        """Project a single Hub messaging endpoint from the namespace."""
        ns = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_messaging_endpoints(ns)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"Hub endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )
        return endpoints[endpoint_name]

    def hub_list(self, namespace_name: str, resource_group_name: str):
        """List all Hub messaging endpoints on the namespace."""
        ns = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_messaging_endpoints(ns)
        # Filter to only Hub-typed entries (defensively; other endpointTypes may exist later)
        return {
            name: ep
            for name, ep in endpoints.items()
            if (ep or {}).get("endpointType") == IOT_HUB_ENDPOINT_TYPE
        }

    # -------------------- dps commands --------------------

    def _patch_provisioning_endpoints(
        self,
        namespace_name: str,
        resource_group_name: str,
        endpoints_patch: dict,
        no_wait: bool = False,
        **kwargs,
    ):
        properties = {"properties": {"provisioning": {"endpoints": endpoints_patch}}}
        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties=properties,
        )
        if no_wait:
            return poller
        with console.status(f"Updating provisioning endpoints on namespace {namespace_name}..."):
            return wait_for_terminal_state(poller, **kwargs)

    def _side_get_dps_resource(self, dps_resource_id: str) -> dict:
        """Side-GET the DPS RP to surface brownfield ``properties.iotHubs[]``.

        Errors here are non-fatal: we surface a warning and return an empty dict so the
        primary projection still succeeds. RBAC on DPS is independent of the namespace.
        """
        try:
            parsed = _parse_dps_resource_id(dps_resource_id)
            client = iot_service_provisioning_factory(self.cmd.cli_ctx).iot_dps_resource
            return client.get(
                resource_group_name=parsed["resource_group_name"],
                provisioning_service_name=parsed["name"],
            ) or {}
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(
                "Unable to fetch brownfield Hubs from DPS %s: %s", dps_resource_id, exc
            )
            return {}

    def dps_add(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        dps_resource_id: str,
        mi_system_assigned: bool = False,
        mi_user_assigned: Optional[str] = None,
        **kwargs,
    ):
        """Add a DPS provisioning endpoint to a namespace (DPS cap = 1)."""
        _parse_dps_resource_id(dps_resource_id)  # validate ARM ID shape up front

        existing = self._get_namespace(namespace_name, resource_group_name)
        if _get_provisioning_endpoints(existing):
            raise ArgumentUsageError(DPS_CAP_EXCEEDED_MSG)

        endpoint_body = {
            "endpointType": DPS_ENDPOINT_TYPE,
            "resourceId": dps_resource_id,
            "inboundCallerIdentity": _build_inbound_identity(
                mi_system_assigned, mi_user_assigned
            ),
        }
        return self._patch_provisioning_endpoints(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            endpoints_patch={endpoint_name: endpoint_body},
            **kwargs,
        )

    def dps_update(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        mi_system_assigned: bool = False,
        mi_user_assigned: Optional[str] = None,
        **kwargs,
    ):
        """Partial-update an existing DPS provisioning endpoint on a namespace."""
        if mi_system_assigned and mi_user_assigned:
            raise ArgumentUsageError(
                "--mi-system-assigned and --mi-user-assigned are mutually exclusive."
            )

        existing = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_provisioning_endpoints(existing)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"DPS endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )

        endpoint_patch: dict = {}
        if mi_user_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": InboundCallerIdentityType.user_assigned.value,
                "userAssignedIdentity": mi_user_assigned,
            }
        elif mi_system_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": InboundCallerIdentityType.system_assigned.value
            }

        if not endpoint_patch:
            raise RequiredArgumentMissingError(
                "Provide at least one of --mi-system-assigned or --mi-user-assigned."
            )

        return self._patch_provisioning_endpoints(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            endpoints_patch={endpoint_name: endpoint_patch},
            **kwargs,
        )

    def dps_remove(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        """Remove a DPS provisioning endpoint from the namespace."""
        existing = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_provisioning_endpoints(existing)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"DPS endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )

        endpoint = endpoints.get(endpoint_name) or {}
        linking_state = endpoint.get("linkingState")
        if linking_state == LinkingState.succeeded.value:
            dps_resource_id = endpoint.get("resourceId") or "<dps-resource-id>"
            raise ArgumentUsageError(
                f"DPS endpoint '{endpoint_name}' is in linkingState 'Succeeded'. "
                "The namespace PATCH path cannot unlink a successfully linked DPS; "
                "to break the link you must delete the underlying DPS resource. "
                f"Run: az iot dps delete --ids {dps_resource_id}"
            )

        return self._patch_provisioning_endpoints(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            endpoints_patch={endpoint_name: None},
            **kwargs,
        )

    def dps_show(self, endpoint_name: str, namespace_name: str, resource_group_name: str):
        """Project a single DPS provisioning endpoint + brownfield Hub list from the DPS RP."""
        ns = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_provisioning_endpoints(ns)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"DPS endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )
        endpoint = dict(endpoints[endpoint_name] or {})
        dps_resource_id = endpoint.get("resourceId")
        if dps_resource_id:
            dps = self._side_get_dps_resource(dps_resource_id)
            brownfield_hubs = (dps.get("properties") or {}).get("iotHubs") or []
            endpoint["brownfieldHubs"] = brownfield_hubs
        return endpoint

    def dps_list(self, namespace_name: str, resource_group_name: str):
        """List all DPS provisioning endpoints on the namespace."""
        ns = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_provisioning_endpoints(ns)
        return {
            name: ep
            for name, ep in endpoints.items()
            if (ep or {}).get("endpointType") == DPS_ENDPOINT_TYPE
        }

    # -------------------- bundled link add (P4) --------------------

    def link_add(
        self,
        namespace_name: str,
        resource_group_name: str,
        hub_endpoint_name: str,
        hub_resource_id: str,
        dps_endpoint_name: str,
        dps_resource_id: str,
        hub_mi_system_assigned: bool = False,
        hub_mi_user_assigned: Optional[str] = None,
        dps_mi_system_assigned: bool = False,
        dps_mi_user_assigned: Optional[str] = None,
        hub_availability: Optional[str] = None,
        hub_allocation_weight: Optional[int] = None,
        **kwargs,
    ):
        """Bundled link: add a Hub + DPS in a single namespace PATCH.

        The DPS entry is serialized into ``properties.provisioning.endpoints`` and the Hub
        entry into ``properties.messaging.endpoints`` in the same request. DPS-first is
        guaranteed by the spec because provisioning endpoints land before messaging
        endpoints in the materialized body order below.
        """
        # Validate DPS ARM ID up front; reject overflow before composing the body.
        _parse_dps_resource_id(dps_resource_id)
        existing = self._get_namespace(namespace_name, resource_group_name)
        if _get_provisioning_endpoints(existing):
            raise ArgumentUsageError(DPS_CAP_EXCEEDED_MSG)

        # Build the two endpoint bodies (each call validates its own MI flag pair).
        dps_body = {
            "endpointType": DPS_ENDPOINT_TYPE,
            "resourceId": dps_resource_id,
            "inboundCallerIdentity": _build_inbound_identity(
                dps_mi_system_assigned, dps_mi_user_assigned
            ),
        }
        hub_body = {
            "endpointType": IOT_HUB_ENDPOINT_TYPE,
            "resourceId": hub_resource_id,
            "inboundCallerIdentity": _build_inbound_identity(
                hub_mi_system_assigned, hub_mi_user_assigned
            ),
        }
        hub_provisioning = {}
        if hub_availability is not None:
            hub_provisioning["availability"] = hub_availability
        if hub_allocation_weight is not None:
            hub_provisioning["allocationWeight"] = hub_allocation_weight
        if hub_provisioning:
            hub_body["provisioning"] = hub_provisioning

        # DPS-first ordering in the bundled PATCH body.
        properties = {
            "properties": {
                "provisioning": {"endpoints": {dps_endpoint_name: dps_body}},
                "messaging": {"endpoints": {hub_endpoint_name: hub_body}},
            }
        }
        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties=properties,
        )
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(f"Linking Hub + DPS on namespace {namespace_name}..."):
            return wait_for_terminal_state(poller, **kwargs)
