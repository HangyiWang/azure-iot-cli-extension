# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional

from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from knack.log import get_logger
from msrestazure.tools import is_valid_resource_id

from azext_iot.adr.common import (
    IdentityType,
    ManagedServiceIdentityType,
    build_mi_body,
    validate_uami_resource_id,
)
from azext_iot.adr.providers.base import ADRProvider, console
from azext_iot.adr.providers._resource import parse_json_object

logger = get_logger(__name__)


_OUTBOUND_MI_MUTEX_MSG = (
    "Specify only one outbound identity: --outbound-mi-system-assigned uses the namespace's "
    "system-assigned identity, --outbound-mi-user-assigned <uami-resource-id> uses a user-assigned "
    "managed identity (the two options are mutually exclusive)."
)


def _normalize_resource_id(resource_id: str) -> str:
    return resource_id.rstrip("/").casefold()


def _resolve_outbound_identity(
    outbound_mi_system_assigned: Optional[bool],
    outbound_mi_user_assigned: Optional[str],
) -> Optional[dict]:
    """Return the OutboundIdentity body (or None when no flag provided)."""
    # An empty/whitespace UAMI (e.g. `--outbound-mi-user-assigned ""`) means the caller
    # did not actually supply one. Clear it first so it neither trips the SAMI/UAMI
    # mutually-exclusive check below nor reaches build_mi_body as a malformed value.
    if outbound_mi_user_assigned is not None and not outbound_mi_user_assigned.strip():
        outbound_mi_user_assigned = None
    if outbound_mi_system_assigned and outbound_mi_user_assigned:
        raise MutuallyExclusiveArgumentError(_OUTBOUND_MI_MUTEX_MSG)
    if outbound_mi_user_assigned:
        validate_uami_resource_id(outbound_mi_user_assigned)
    return build_mi_body(
        outbound_mi_system_assigned,
        outbound_mi_user_assigned,
        sami_type=IdentityType.system_assigned.value,
        uami_type=IdentityType.user_assigned.value,
    )


def _build_namespace_identity(
    existing_identity: Optional[dict] = None,
    user_assigned_identity: Optional[str] = None,
    ensure_system_assigned: bool = False,
) -> dict:
    """Build a namespace ARM identity while preserving existing UAMI assignments."""
    existing_identity = existing_identity or {}
    identity_type = existing_identity.get("type") or ""
    has_system_assigned = ensure_system_assigned or "SystemAssigned" in identity_type
    user_assigned_identities = {
        _normalize_resource_id(resource_id): resource_id
        for resource_id in (existing_identity.get("userAssignedIdentities") or {})
    }
    if user_assigned_identity:
        user_assigned_identities.setdefault(
            _normalize_resource_id(user_assigned_identity),
            user_assigned_identity,
        )

    if has_system_assigned and user_assigned_identities:
        resolved_type = ManagedServiceIdentityType.system_assigned_user_assigned.value
    elif has_system_assigned:
        resolved_type = ManagedServiceIdentityType.system_assigned.value
    else:
        resolved_type = ManagedServiceIdentityType.user_assigned.value

    identity = {"type": resolved_type}
    if user_assigned_identities:
        identity["userAssignedIdentities"] = {
            resource_id: {} for resource_id in user_assigned_identities.values()
        }
    return identity


def _build_endpoint_properties(
    management_endpoints: Any = None,
    messaging_endpoints: Any = None,
    provisioning_endpoints: Any = None,
    updating_endpoints: Any = None,
) -> dict:
    properties = {}
    endpoint_inputs = (
        ("management", "--management-endpoints", management_endpoints),
        ("messaging", "--messaging-endpoints", messaging_endpoints),
        ("provisioning", "--provisioning-endpoints", provisioning_endpoints),
        ("updating", "--updating-endpoints", updating_endpoints),
    )
    for property_name, argument_name, value in endpoint_inputs:
        if value is not None:
            properties[property_name] = {
                "endpoints": parse_json_object(value, argument_name)
            }
    return properties


def _managed_identity_type(has_system_assigned: bool, user_identity_ids) -> str:
    if has_system_assigned and user_identity_ids:
        return ManagedServiceIdentityType.system_assigned_user_assigned.value
    if has_system_assigned:
        return ManagedServiceIdentityType.system_assigned.value
    if user_identity_ids:
        return ManagedServiceIdentityType.user_assigned.value
    return "None"


def _clean_identity_ids(identity_ids: Optional[List[str]]) -> Optional[List[str]]:
    if identity_ids is None:
        return None
    cleaned = [
        identity_id.strip()
        for identity_id in identity_ids
        if isinstance(identity_id, str) and identity_id.strip()
    ]
    if len(cleaned) != len(identity_ids):
        raise InvalidArgumentValueError(
            "User-assigned identity resource IDs must not be empty."
        )
    unique_ids = {}
    for identity_id in cleaned:
        validate_uami_resource_id(identity_id)
        unique_ids.setdefault(_normalize_resource_id(identity_id), identity_id)
    return list(unique_ids.values())


class NamespaceProvider(ADRProvider):
    def __init__(self, cmd):
        super(NamespaceProvider, self).__init__(cmd)

    def create(
        self,
        namespace_name: str,
        resource_group_name: str,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        outbound_mi_system_assigned: Optional[bool] = None,
        outbound_mi_user_assigned: Optional[str] = None,
        management_endpoints: Any = None,
        messaging_endpoints: Any = None,
        provisioning_endpoints: Any = None,
        updating_endpoints: Any = None,
        **kwargs,
    ):
        if not location:
            location = self._ensure_location(self.cmd.cli_ctx, resource_group_name, location)

        namespace_resource = {"location": location}

        if tags is not None:
            namespace_resource["tags"] = tags

        outbound_identity = _resolve_outbound_identity(
            outbound_mi_system_assigned, outbound_mi_user_assigned
        )

        properties = _build_endpoint_properties(
            management_endpoints=management_endpoints,
            messaging_endpoints=messaging_endpoints,
            provisioning_endpoints=provisioning_endpoints,
            updating_endpoints=updating_endpoints,
        )
        if outbound_identity is not None:
            properties["outboundIdentity"] = outbound_identity
        namespace_resource["identity"] = _build_namespace_identity(
            user_assigned_identity=(
                outbound_identity.get("userAssignedIdentity") if outbound_identity else None
            ),
            ensure_system_assigned=True,
        )
        if properties:
            namespace_resource["properties"] = properties

        poller = self.client.namespaces.begin_create_or_replace(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            resource=namespace_resource,
        )
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(f"Creating namespace {namespace_name}..."):
            namespace_result = self._await_terminal(poller, **kwargs)

        # The create response may omit resourceGroup; backfill it from the request input.
        # (namespace_result can be None if the provisioningState poll times out.)
        if namespace_result and not namespace_result.get("resourceGroup"):
            namespace_result["resourceGroup"] = resource_group_name

        return namespace_result

    def show(self, namespace_name: str, resource_group_name: str):
        return self.client.namespaces.get(resource_group_name=resource_group_name, namespace_name=namespace_name)

    def list(self, resource_group_name: Optional[str] = None):
        if resource_group_name:
            result = self.client.namespaces.list_by_resource_group(resource_group_name=resource_group_name)
        else:
            result = self.client.namespaces.list_by_subscription()
        return list(result)

    def delete(self, namespace_name: str, resource_group_name: str, **kwargs):
        logger.warning(
            "All child resources under namespace '%s' will be deleted.",
            namespace_name,
        )
        poller = self.client.namespaces.begin_delete(
            resource_group_name=resource_group_name, namespace_name=namespace_name
        )
        return self._wait(poller, f"Deleting namespace {namespace_name}...", **kwargs)

    def update(
        self,
        namespace_name: str,
        resource_group_name: str,
        tags: Optional[Dict[str, str]] = None,
        outbound_mi_system_assigned: Optional[bool] = None,
        outbound_mi_user_assigned: Optional[str] = None,
        management_endpoints: Any = None,
        messaging_endpoints: Any = None,
        provisioning_endpoints: Any = None,
        updating_endpoints: Any = None,
        **kwargs,
    ):
        # NamespaceUpdate body: tags at top, substantive fields nested under "properties".
        body: dict = {}
        if tags is not None:
            body["tags"] = tags

        properties = _build_endpoint_properties(
            management_endpoints=management_endpoints,
            messaging_endpoints=messaging_endpoints,
            provisioning_endpoints=provisioning_endpoints,
            updating_endpoints=updating_endpoints,
        )

        outbound_identity = _resolve_outbound_identity(
            outbound_mi_system_assigned, outbound_mi_user_assigned
        )
        if outbound_identity is not None:
            properties["outboundIdentity"] = outbound_identity
            namespace = self.client.namespaces.get(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
            body["identity"] = _build_namespace_identity(
                existing_identity=(namespace or {}).get("identity"),
                user_assigned_identity=outbound_identity.get("userAssignedIdentity"),
                ensure_system_assigned=bool(outbound_mi_system_assigned),
            )
        elif outbound_mi_system_assigned is False:
            properties["outboundIdentity"] = None
        if properties:
            body["properties"] = properties
        if not body:
            raise RequiredArgumentMissingError(
                "Nothing to update. Provide --tags, endpoint configuration, or an "
                "outbound managed identity."
            )

        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties=body,
        )
        return self._wait(poller, f"Updating namespace {namespace_name}...", **kwargs)

    def identity_show(self, namespace_name: str, resource_group_name: str):
        namespace = self.show(namespace_name, resource_group_name)
        return (namespace or {}).get("identity")

    def identity_assign(
        self,
        namespace_name: str,
        resource_group_name: str,
        system_assigned: bool = False,
        user_assigned_identities: Optional[List[str]] = None,
        **kwargs,
    ):
        user_assigned_identities = _clean_identity_ids(user_assigned_identities)
        if not system_assigned and not user_assigned_identities:
            raise RequiredArgumentMissingError(
                "Specify --system-assigned or at least one "
                "--user-assigned-identity."
            )

        namespace = self.show(namespace_name, resource_group_name)
        existing_identity = (namespace or {}).get("identity") or {}
        existing_type = existing_identity.get("type") or ""
        has_system_assigned = system_assigned or "SystemAssigned" in existing_type
        existing_ids = {
            _normalize_resource_id(identity_id): identity_id
            for identity_id in (
                existing_identity.get("userAssignedIdentities") or {}
            )
        }
        requested_ids = {
            _normalize_resource_id(identity_id): identity_id
            for identity_id in (user_assigned_identities or [])
        }
        added_ids = set(requested_ids) - set(existing_ids)
        adds_system_identity = system_assigned and "SystemAssigned" not in existing_type
        if not added_ids and not adds_system_identity:
            raise InvalidArgumentValueError(
                "All requested managed identities are already assigned."
            )
        identity_ids = {
            **existing_ids,
            **{
                normalized_id: requested_ids[normalized_id]
                for normalized_id in added_ids
            },
        }
        identity = {
            "type": _managed_identity_type(has_system_assigned, identity_ids)
        }
        if identity_ids:
            identity["userAssignedIdentities"] = {
                identity_id: {} for identity_id in sorted(identity_ids.values())
            }

        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties={"identity": identity},
        )
        no_wait = kwargs.get("no_wait", False)
        result = self._wait(
            poller,
            f"Assigning managed identities to namespace {namespace_name}...",
            **kwargs,
        )
        if no_wait:
            return result
        return (result or {}).get("identity")

    def identity_remove(
        self,
        namespace_name: str,
        resource_group_name: str,
        system_assigned: bool = False,
        user_assigned_identities: Optional[List[str]] = None,
        **kwargs,
    ):
        user_assigned_identities = _clean_identity_ids(user_assigned_identities)
        if not system_assigned and user_assigned_identities is None:
            raise RequiredArgumentMissingError(
                "Specify --system-assigned or --user-assigned-identity."
            )

        namespace = self.show(namespace_name, resource_group_name)
        existing_identity = (namespace or {}).get("identity") or {}
        existing_type = existing_identity.get("type") or ""
        has_system_assigned = "SystemAssigned" in existing_type
        existing_ids = {
            _normalize_resource_id(identity_id): identity_id
            for identity_id in (
                existing_identity.get("userAssignedIdentities") or {}
            )
        }
        requested_ids = {
            _normalize_resource_id(identity_id): identity_id
            for identity_id in (user_assigned_identities or [])
        }
        remove_ids = (
            set(existing_ids)
            if user_assigned_identities == []
            else set(requested_ids)
        )
        if not system_assigned and not remove_ids:
            raise InvalidArgumentValueError(
                "The namespace has no user-assigned identities to remove."
            )
        missing_ids = remove_ids - set(existing_ids)
        if missing_ids:
            names = ", ".join(
                sorted(requested_ids[identity_id] for identity_id in missing_ids)
            )
            raise InvalidArgumentValueError(
                f"These user-assigned identities are not assigned: {names}."
            )
        if system_assigned and not has_system_assigned:
            raise InvalidArgumentValueError(
                "The namespace does not have a system-assigned identity."
            )

        outbound_identity = ((namespace or {}).get("properties") or {}).get(
            "outboundIdentity"
        ) or {}
        if system_assigned and outbound_identity.get("type") == "SystemAssigned":
            raise InvalidArgumentValueError(
                "The system-assigned identity is configured as the outbound "
                "identity. Change the outbound identity before removing it."
            )
        outbound_uami = outbound_identity.get("userAssignedIdentity")
        if (
            outbound_uami
            and _normalize_resource_id(outbound_uami) in remove_ids
        ):
            raise InvalidArgumentValueError(
                "A selected user-assigned identity is configured as the outbound "
                "identity. Change the outbound identity before removing it."
            )

        remaining_ids = set(existing_ids) - remove_ids
        has_system_assigned = has_system_assigned and not system_assigned
        identity = {
            "type": _managed_identity_type(has_system_assigned, remaining_ids)
        }
        if existing_ids:
            identity["userAssignedIdentities"] = {
                **{
                    existing_ids[identity_id]: {}
                    for identity_id in sorted(remaining_ids)
                },
                **{
                    existing_ids[identity_id]: None
                    for identity_id in sorted(remove_ids)
                },
            }

        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties={"identity": identity},
        )
        no_wait = kwargs.get("no_wait", False)
        result = self._wait(
            poller,
            f"Removing managed identities from namespace {namespace_name}...",
            **kwargs,
        )
        if no_wait:
            return result
        return (result or {}).get("identity")

    def management_endpoint_set(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
        endpoint_type: str,
        address: str,
        scope_id: str,
        resource_id: str,
        **kwargs,
    ):
        endpoint_fields = {
            "--name": endpoint_name,
            "--endpoint-type": endpoint_type,
            "--address": address,
            "--scope-id": scope_id,
            "--resource-id": resource_id,
        }
        for argument_name, value in endpoint_fields.items():
            if not isinstance(value, str) or not value.strip():
                raise InvalidArgumentValueError(
                    f"{argument_name} must be a non-empty string."
                )
        if not is_valid_resource_id(resource_id):
            raise InvalidArgumentValueError(
                "--resource-id must be a valid ARM resource ID."
            )
        endpoint = {
            "endpointType": endpoint_type,
            "address": address,
            "scopeId": scope_id,
            "resourceId": resource_id,
        }
        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties={
                "properties": {
                    "management": {"endpoints": {endpoint_name: endpoint}}
                }
            },
        )
        return self._wait(
            poller,
            f"Setting management endpoint '{endpoint_name}' on namespace "
            f"{namespace_name}...",
            **kwargs,
        )

    def management_endpoint_show(
        self,
        endpoint_name: str,
        namespace_name: str,
        resource_group_name: str,
    ):
        endpoints = self._management_endpoints(
            namespace_name, resource_group_name
        )
        if endpoint_name not in endpoints:
            raise ResourceNotFoundError(
                f"Management endpoint '{endpoint_name}' was not found on "
                f"namespace '{namespace_name}'."
            )
        return {"name": endpoint_name, **(endpoints[endpoint_name] or {})}

    def management_endpoint_list(
        self, namespace_name: str, resource_group_name: str
    ):
        endpoints = self._management_endpoints(
            namespace_name, resource_group_name
        )
        return [
            {"name": name, **(endpoint or {})}
            for name, endpoint in sorted(endpoints.items())
        ]

    def _management_endpoints(
        self, namespace_name: str, resource_group_name: str
    ) -> dict:
        namespace = self.show(namespace_name, resource_group_name)
        return (
            (((namespace or {}).get("properties") or {}).get("management") or {})
            .get("endpoints")
            or {}
        )

    def migrate(
        self,
        namespace_name: str,
        resource_group_name: str,
        resource_ids: List[str],
        scope: str,
        **kwargs,
    ):
        resource_ids = [
            resource_id.strip()
            for resource_id in resource_ids
            if isinstance(resource_id, str) and resource_id.strip()
        ]
        if not resource_ids:
            raise RequiredArgumentMissingError("Provide at least one resource ID to migrate.")

        poller = self.client.namespaces.begin_migrate(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            body={"scope": scope, "resourceIds": resource_ids},
        )
        return self._wait(
            poller,
            f"Migrating {len(resource_ids)} resource(s) into namespace {namespace_name}...",
            **kwargs,
        )
