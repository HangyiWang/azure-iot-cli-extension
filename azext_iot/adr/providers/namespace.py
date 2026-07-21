# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from azure.cli.core.azclierror import (
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)
from knack.log import get_logger

from azext_iot.adr.common import (
    DEFAULT_NS_POLICY_NAME,
    DEFAULT_NS_POLICY_CERT_KEY_TYPE,
    DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS,
    IdentityType,
    ManagedServiceIdentityType,
    build_mi_body,
    validate_policy_certificate_options,
)
from azext_iot.adr.providers.base import ADRProvider, console
from azext_iot.adr.providers.credential import CredentialProvider
from azext_iot.adr.providers.policy import PolicyProvider

logger = get_logger(__name__)


_OUTBOUND_MI_MUTEX_MSG = (
    "Specify only one outbound identity: --outbound-mi-system-assigned uses the namespace's "
    "system-assigned identity, --outbound-mi-user-assigned <uami-resource-id> uses a user-assigned "
    "managed identity (the two options are mutually exclusive)."
)


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
        resource_id: {}
        for resource_id in (existing_identity.get("userAssignedIdentities") or {})
    }
    if user_assigned_identity:
        user_assigned_identities[user_assigned_identity] = {}

    if has_system_assigned and user_assigned_identities:
        resolved_type = ManagedServiceIdentityType.system_assigned_user_assigned.value
    elif has_system_assigned:
        resolved_type = ManagedServiceIdentityType.system_assigned.value
    else:
        resolved_type = ManagedServiceIdentityType.user_assigned.value

    identity = {"type": resolved_type}
    if user_assigned_identities:
        identity["userAssignedIdentities"] = user_assigned_identities
    return identity


class NamespaceProvider(ADRProvider):
    def __init__(self, cmd):
        super(NamespaceProvider, self).__init__(cmd)

    def create(
        self,
        namespace_name: str,
        resource_group_name: str,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        policy_name: Optional[str] = None,
        certificate_key_type: Optional[str] = None,
        certificate_validity_days: Optional[int] = None,
        outbound_mi_system_assigned: Optional[bool] = None,
        outbound_mi_user_assigned: Optional[str] = None,
        **kwargs,
    ):
        validate_policy_certificate_options(
            certificate_key_type, certificate_validity_days
        )
        # Legacy credential/policy bootstrap (DEPRECATED): triggered only by explicit legacy policy
        # args. Certificate authorities and policies are managed via `iot adr ns ca`.
        should_create_credential_policy = any([
            policy_name,
            certificate_key_type,
            certificate_validity_days,
        ])

        if should_create_credential_policy:
            logger.warning(
                "Creating a default credential and credential policy is deprecated and will be "
                "removed in a future release. Use 'az iot adr ns ca' to manage certificate "
                "authorities and policies instead."
            )

            # Set defaults for certificate parameters if not provided
            if certificate_key_type is None:
                certificate_key_type = DEFAULT_NS_POLICY_CERT_KEY_TYPE
            if certificate_validity_days is None:
                certificate_validity_days = DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS

        if not location:
            location = self._ensure_location(self.cmd.cli_ctx, resource_group_name, location)

        namespace_resource = {"location": location}

        if tags is not None:
            namespace_resource["tags"] = tags

        outbound_identity = _resolve_outbound_identity(
            outbound_mi_system_assigned, outbound_mi_user_assigned
        )

        properties = {}
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
            if should_create_credential_policy:
                logger.warning(
                    "--no-wait skips default credential and policy creation; create them "
                    "manually once the namespace finishes provisioning."
                )
            return poller
        with console.status(f"Creating namespace {namespace_name}..."):
            namespace_result = self._await_terminal(poller, **kwargs)

        # The create response may omit resourceGroup; backfill it from the request input.
        # (namespace_result can be None if the provisioningState poll times out.)
        if namespace_result and not namespace_result.get("resourceGroup"):
            namespace_result["resourceGroup"] = resource_group_name

        if should_create_credential_policy:
            try:
                credential_provider = CredentialProvider(self.cmd)
                credential_provider.create(
                    namespace_name=namespace_name, resource_group_name=resource_group_name, location=location, **kwargs
                )
            except Exception as e:  # noqa: BLE001 - namespace itself is created; default cred is best-effort
                logger.warning(
                    "Namespace '%s' was created, but default credential creation failed: %s. "
                    "Retry with 'az iot adr ns credential create --ns %s -g %s'.",
                    namespace_name, e, namespace_name, resource_group_name,
                )

            try:
                policy_provider = PolicyProvider(self.cmd)
                policy_provider.create(
                    policy_name=policy_name or DEFAULT_NS_POLICY_NAME,
                    namespace_name=namespace_name,
                    resource_group_name=resource_group_name,
                    location=location,
                    certificate_key_type=certificate_key_type,
                    certificate_validity_days=certificate_validity_days,
                    **kwargs,
                )
            except Exception as e:  # noqa: BLE001 - namespace itself is created; default policy is best-effort
                logger.warning(
                    "Namespace '%s' was created, but default policy creation failed: %s. "
                    "Retry with 'az iot adr ns policy create -n %s --ns %s -g %s'.",
                    namespace_name, e, policy_name or DEFAULT_NS_POLICY_NAME, namespace_name, resource_group_name,
                )

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
            "All child resources (credentials, policies, devices, groups, and jobs) under "
            "namespace '%s' will be deleted.",
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
        **kwargs,
    ):
        # NamespaceUpdate body: tags at top, substantive fields nested under "properties".
        body: dict = {}
        if tags is not None:
            body["tags"] = tags

        properties: dict = {}

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
        if properties:
            body["properties"] = properties
        if not body:
            raise RequiredArgumentMissingError(
                "Nothing to update. Provide --tags or an outbound managed identity."
            )

        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties=body,
        )
        return self._wait(poller, f"Updating namespace {namespace_name}...", **kwargs)

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
