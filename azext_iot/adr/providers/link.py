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
from msrestazure.tools import is_valid_resource_id, parse_resource_id
from rich.console import Console

from azext_iot._factory import iot_service_provisioning_factory
from azext_iot.adr.common import (
    DPS_ENDPOINT_TYPE,
    IOT_HUB_ENDPOINT_TYPE,
    ADU_ENDPOINT_TYPE,
    IdentityType,
    build_mi_body,
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

_MI_MUTEX_MSG = (
    "Specify only one identity: use --mi-system-assigned for the namespace's "
    "system-assigned identity, or --mi-user-assigned <uami-resource-id> for a "
    "user-assigned managed identity (the two options are mutually exclusive)."
)

_MI_REQUIRED_MSG = (
    "An inbound caller identity is required. Pass --mi-system-assigned to use the "
    "namespace's system-assigned identity, or --mi-user-assigned <uami-resource-id> "
    "to use a user-assigned managed identity."
)


def _parse_dps_resource_id(dps_resource_id: str) -> dict:
    """Parse a DPS ARM resource ID into its components.

    Expected shape:
        /subscriptions/<sub>/resourceGroups/<rg>/providers/
            Microsoft.Devices/provisioningServices/<name>
    """
    raw = (dps_resource_id or "").strip()
    if not raw:
        raise InvalidArgumentValueError(
            "--dps-id is required and must be a Microsoft.Devices/provisioningServices ARM resource ID."
        )
    # Friendly hint: a bare name (no slashes) is the most common mistake here.
    if "/" not in raw:
        raise InvalidArgumentValueError(
            f"'{raw}' looks like a bare DPS name. Pass the full ARM resource ID instead "
            "(use 'az iot dps show -n <dps> --query id -o tsv' to retrieve it)."
        )
    if not is_valid_resource_id(raw):
        raise InvalidArgumentValueError(
            f"'{dps_resource_id}' is not a valid ARM resource ID."
        )
    parsed = parse_resource_id(raw)
    # Reject child resources (e.g. .../provisioningServices/<n>/certificates/<c>) and
    # any non-DPS resource type.
    if (
        (parsed.get("namespace") or "").lower() != "microsoft.devices"
        or (parsed.get("type") or "").lower() != "provisioningservices"
        or "child_name_1" in parsed
    ):
        raise InvalidArgumentValueError(
            f"'{dps_resource_id}' is not a Microsoft.Devices/provisioningServices resource ID."
        )
    return {
        "subscription_id": parsed["subscription"],
        "resource_group_name": parsed["resource_group"],
        "name": parsed["name"],
    }


def _parse_adu_resource_id(adu_resource_id: str) -> dict:
    """Parse an ADU (Device Update) linked account ARM resource ID into its components.

    Expected shape:
        /subscriptions/<sub>/resourceGroups/<rg>/providers/
            Microsoft.DeviceUpdate/linkedAccounts/<name>
    """
    raw = (adu_resource_id or "").strip()
    if not raw:
        raise InvalidArgumentValueError(
            "--adu-id is required and must be a Microsoft.DeviceUpdate/linkedAccounts ARM resource ID."
        )
    # Friendly hint: a bare name (no slashes) is the most common mistake here.
    if "/" not in raw:
        raise InvalidArgumentValueError(
            f"'{raw}' looks like a bare ADU account name. Pass the full ARM resource ID instead."
        )
    if not is_valid_resource_id(raw):
        raise InvalidArgumentValueError(
            f"'{adu_resource_id}' is not a valid ARM resource ID."
        )
    parsed = parse_resource_id(raw)
    # Reject child resources and any non-linkedAccounts resource type.
    if (
        (parsed.get("namespace") or "").lower() != "microsoft.deviceupdate"
        or (parsed.get("type") or "").lower() != "linkedaccounts"
        or "child_name_1" in parsed
    ):
        raise InvalidArgumentValueError(
            f"'{adu_resource_id}' is not a Microsoft.DeviceUpdate/linkedAccounts resource ID. "
            "Pass the full ARM resource ID of the linked Device Update account."
        )
    return {
        "subscription_id": parsed["subscription"],
        "resource_group_name": parsed["resource_group"],
        "name": parsed["name"],
    }


def _build_inbound_identity(mi_system_assigned: bool, mi_user_assigned: Optional[str]) -> dict:
    """Build the InboundCallerIdentity body from CLI flags. Exactly one variant required."""
    # Normalize empty/whitespace UAMI before the mutex check so a stray
    # '--mi-user-assigned ""' is treated as not provided.
    if mi_user_assigned is not None and not mi_user_assigned.strip():
        mi_user_assigned = None
    if mi_system_assigned and mi_user_assigned:
        raise ArgumentUsageError(_MI_MUTEX_MSG)
    body = build_mi_body(
        mi_system_assigned,
        mi_user_assigned,
        sami_type=IdentityType.system_assigned.value,
        uami_type=IdentityType.user_assigned.value,
    )
    if body is None:
        raise RequiredArgumentMissingError(_MI_REQUIRED_MSG)
    return body


def _get_messaging_endpoints(namespace: dict) -> dict:
    return (((namespace or {}).get("properties") or {}).get("messaging") or {}).get("endpoints") or {}


def _get_provisioning_endpoints(namespace: dict) -> dict:
    return (((namespace or {}).get("properties") or {}).get("provisioning") or {}).get("endpoints") or {}


def _get_updating_endpoints(namespace: dict) -> dict:
    return (((namespace or {}).get("properties") or {}).get("updating") or {}).get("endpoints") or {}


def _build_hub_endpoint_body(
    hub_resource_id: str,
    mi_system_assigned: bool,
    mi_user_assigned: Optional[str],
    availability: Optional[str] = None,
    allocation_weight: Optional[int] = None,
) -> dict:
    """Build a full Hub messaging-endpoint body for a namespace PATCH."""
    body = {
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
        body["provisioning"] = provisioning
    return body


def _build_dps_endpoint_body(
    dps_resource_id: str,
    mi_system_assigned: bool,
    mi_user_assigned: Optional[str],
) -> dict:
    """Build a full DPS provisioning-endpoint body for a namespace PATCH."""
    return {
        "endpointType": DPS_ENDPOINT_TYPE,
        "resourceId": dps_resource_id,
        "inboundCallerIdentity": _build_inbound_identity(mi_system_assigned, mi_user_assigned),
    }


def _build_adu_endpoint_body(
    adu_resource_id: str,
    mi_system_assigned: bool,
    mi_user_assigned: Optional[str],
) -> dict:
    """Build a full ADU updating-endpoint body for a namespace PATCH."""
    return {
        "endpointType": ADU_ENDPOINT_TYPE,
        "resourceId": adu_resource_id,
        "inboundCallerIdentity": _build_inbound_identity(mi_system_assigned, mi_user_assigned),
    }


class LinkProvider(ADRProvider):
    def __init__(self, cmd):
        super(LinkProvider, self).__init__(cmd)

    # Helpers

    def _get_namespace(self, namespace_name: str, resource_group_name: str) -> dict:
        return dict(
            self.client.namespaces.get(
                resource_group_name=resource_group_name, namespace_name=namespace_name
            )
            or {}
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

    # Hub commands

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

        # DPS-first: namespace must already have at least one DPS endpoint
        if not _get_provisioning_endpoints(existing):
            raise ArgumentUsageError(DPS_FIRST_REQUIRED_MSG)

        endpoint_body = _build_hub_endpoint_body(
            hub_resource_id,
            mi_system_assigned,
            mi_user_assigned,
            availability=availability,
            allocation_weight=allocation_weight,
        )

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
            raise ArgumentUsageError(_MI_MUTEX_MSG)

        existing = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_messaging_endpoints(existing)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"Hub endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )

        endpoint_patch: dict = {}
        if mi_user_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": IdentityType.user_assigned.value,
                "userAssignedIdentity": mi_user_assigned,
            }
        elif mi_system_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": IdentityType.system_assigned.value
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
                "Nothing to update. Pass at least one of --mi-system-assigned, "
                "--mi-user-assigned <uami-resource-id>, --availability, or --allocation-weight."
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
        """Removing a Hub link entry directly is not supported by design.

        Hub links are bound to the lifecycle of the underlying IoT Hub. To unlink,
        delete the IoT Hub resource or the namespace itself.
        """
        hub_resource_id = "<hub-resource-id>"
        try:
            existing = self._get_namespace(namespace_name, resource_group_name)
            endpoint = _get_messaging_endpoints(existing).get(endpoint_name) or {}
            hub_resource_id = endpoint.get("resourceId") or hub_resource_id
        except Exception:  # noqa: BLE001 - best-effort enrichment only
            pass

        raise ArgumentUsageError(
            f"Removing Hub link '{endpoint_name}' directly is not supported. "
            "Hub links are tied to the underlying IoT Hub lifecycle. To unlink, delete "
            f"the IoT Hub ('az iot hub delete --ids {hub_resource_id}') or the namespace "
            f"('az iot adr ns delete -n {namespace_name} -g {resource_group_name}')."
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

    # DPS commands

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
        """Side-GET the DPS RP to surface existing ``properties.iotHubs[]`` registrations.

        Errors here are non-fatal: we surface a warning and return an empty dict so the
        primary projection still succeeds. RBAC on DPS is independent of the namespace.
        """
        try:
            parsed = _parse_dps_resource_id(dps_resource_id)
        except Exception:  # pragma: no cover - parse already validated upstream
            return {}
        dps_name = parsed["name"]
        try:
            client = iot_service_provisioning_factory(self.cmd.cli_ctx).iot_dps_resource
            return dict(
                client.get(
                    resource_group_name=parsed["resource_group_name"],
                    provisioning_service_name=dps_name,
                )
                or {}
            )
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(
                "Could not list existing IoT Hubs registered on DPS '%s': %s", dps_name, exc
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
        """Add a DPS provisioning endpoint to a namespace.

        Only one DPS endpoint may be linked per namespace; the existence check
        below rejects a second one.
        """
        _parse_dps_resource_id(dps_resource_id)  # validate ARM ID shape up front

        existing = self._get_namespace(namespace_name, resource_group_name)
        if _get_provisioning_endpoints(existing):
            raise ArgumentUsageError(DPS_CAP_EXCEEDED_MSG)

        endpoint_body = _build_dps_endpoint_body(
            dps_resource_id, mi_system_assigned, mi_user_assigned
        )
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
            raise ArgumentUsageError(_MI_MUTEX_MSG)

        existing = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_provisioning_endpoints(existing)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"DPS endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )

        endpoint_patch: dict = {}
        if mi_user_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": IdentityType.user_assigned.value,
                "userAssignedIdentity": mi_user_assigned,
            }
        elif mi_system_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": IdentityType.system_assigned.value
            }

        if not endpoint_patch:
            raise RequiredArgumentMissingError(
                "Nothing to update. Pass --mi-system-assigned or "
                "--mi-user-assigned <uami-resource-id> to change the inbound caller identity."
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
        """Removing a DPS link entry directly is not supported by design.

        DPS links are bound to the lifecycle of the underlying DPS resource. To unlink,
        delete the DPS resource or the namespace itself.
        """
        dps_resource_id = "<dps-resource-id>"
        try:
            existing = self._get_namespace(namespace_name, resource_group_name)
            endpoint = _get_provisioning_endpoints(existing).get(endpoint_name) or {}
            dps_resource_id = endpoint.get("resourceId") or dps_resource_id
        except Exception:  # noqa: BLE001 - best-effort enrichment only
            pass

        raise ArgumentUsageError(
            f"Removing DPS link '{endpoint_name}' directly is not supported. "
            "DPS links are tied to the underlying DPS lifecycle. To unlink, delete "
            f"the DPS ('az iot dps delete --ids {dps_resource_id}') or the namespace "
            f"('az iot adr ns delete -n {namespace_name} -g {resource_group_name}')."
        )

    def dps_show(self, endpoint_name: str, namespace_name: str, resource_group_name: str):
        """Project a single DPS provisioning endpoint, enriched with the DPS RP's existing IoT Hub registrations."""
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
            # NOTE: 'brownfieldHubs' is a public response key documented in _help.py and
            # asserted by tests; do not rename without coordinating those.
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

    # ADU commands

    def _patch_updating_endpoints(
        self,
        namespace_name: str,
        resource_group_name: str,
        endpoints_patch: dict,
        no_wait: bool = False,
        **kwargs,
    ):
        properties = {"properties": {"updating": {"endpoints": endpoints_patch}}}
        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties=properties,
        )
        if no_wait:
            return poller
        with console.status(f"Updating device update endpoints on namespace {namespace_name}..."):
            return wait_for_terminal_state(poller, **kwargs)

    def adu_add(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        adu_resource_id: str,
        mi_system_assigned: bool = False,
        mi_user_assigned: Optional[str] = None,
        **kwargs,
    ):
        """Add an Azure Device Update (ADU) updating endpoint to a namespace."""
        _parse_adu_resource_id(adu_resource_id)  # validate ARM ID shape up front

        existing = self._get_namespace(namespace_name, resource_group_name)
        if endpoint_name in _get_updating_endpoints(existing):
            raise ArgumentUsageError(
                f"Device update endpoint '{endpoint_name}' already exists on namespace "
                f"'{namespace_name}'. Use 'az iot adr ns link adu update' to modify it."
            )

        endpoint_body = _build_adu_endpoint_body(
            adu_resource_id, mi_system_assigned, mi_user_assigned
        )
        return self._patch_updating_endpoints(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            endpoints_patch={endpoint_name: endpoint_body},
            **kwargs,
        )

    def adu_update(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        mi_system_assigned: bool = False,
        mi_user_assigned: Optional[str] = None,
        **kwargs,
    ):
        """Partial-update an existing ADU updating endpoint on a namespace."""
        if mi_system_assigned and mi_user_assigned:
            raise ArgumentUsageError(_MI_MUTEX_MSG)

        existing = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_updating_endpoints(existing)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"Device update endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )

        endpoint_patch: dict = {}
        if mi_user_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": IdentityType.user_assigned.value,
                "userAssignedIdentity": mi_user_assigned,
            }
        elif mi_system_assigned:
            endpoint_patch["inboundCallerIdentity"] = {
                "type": IdentityType.system_assigned.value
            }

        if not endpoint_patch:
            raise RequiredArgumentMissingError(
                "Nothing to update. Pass --mi-system-assigned or "
                "--mi-user-assigned <uami-resource-id> to change the inbound caller identity."
            )

        return self._patch_updating_endpoints(
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
            endpoints_patch={endpoint_name: endpoint_patch},
            **kwargs,
        )

    def adu_remove(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        """Removing an ADU link entry directly is not supported by design.

        ADU links are bound to the lifecycle of the underlying Device Update linked account.
        To unlink, delete the linked account resource or the namespace itself.
        """
        adu_resource_id = "<adu-resource-id>"
        try:
            existing = self._get_namespace(namespace_name, resource_group_name)
            endpoint = _get_updating_endpoints(existing).get(endpoint_name) or {}
            adu_resource_id = endpoint.get("resourceId") or adu_resource_id
        except Exception:  # noqa: BLE001 - best-effort enrichment only
            pass

        raise ArgumentUsageError(
            f"Removing device update link '{endpoint_name}' directly is not supported. "
            "ADU links are tied to the underlying Device Update linked account lifecycle. To unlink, "
            f"delete the linked account ('az resource delete --ids {adu_resource_id}') or the namespace "
            f"('az iot adr ns delete -n {namespace_name} -g {resource_group_name}')."
        )

    def adu_show(self, endpoint_name: str, namespace_name: str, resource_group_name: str):
        """Project a single ADU updating endpoint from the namespace."""
        ns = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_updating_endpoints(ns)
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"Device update endpoint '{endpoint_name}' was not found on namespace '{namespace_name}'."
            )
        return endpoints[endpoint_name]

    def adu_list(self, namespace_name: str, resource_group_name: str):
        """List all ADU updating endpoints on the namespace."""
        ns = self._get_namespace(namespace_name, resource_group_name)
        endpoints = _get_updating_endpoints(ns)
        return {
            name: ep
            for name, ep in endpoints.items()
            if (ep or {}).get("endpointType") == ADU_ENDPOINT_TYPE
        }

    # Bundled link add

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
        entry into ``properties.messaging.endpoints`` in the same request. DPS is applied
        first because provisioning endpoints land before messaging endpoints in the
        materialized body order below.
        """
        # Validate DPS ARM ID up front; reject overflow before composing the body.
        _parse_dps_resource_id(dps_resource_id)
        existing = self._get_namespace(namespace_name, resource_group_name)
        if _get_provisioning_endpoints(existing):
            raise ArgumentUsageError(DPS_CAP_EXCEEDED_MSG)

        # Build the two endpoint bodies (each call validates its own MI flag pair).
        dps_body = _build_dps_endpoint_body(
            dps_resource_id, dps_mi_system_assigned, dps_mi_user_assigned
        )
        hub_body = _build_hub_endpoint_body(
            hub_resource_id,
            hub_mi_system_assigned,
            hub_mi_user_assigned,
            availability=hub_availability,
            allocation_weight=hub_allocation_weight,
        )

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
