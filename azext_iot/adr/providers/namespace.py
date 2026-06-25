# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azure.cli.core.azclierror import (
    ArgumentUsageError,
    MutuallyExclusiveArgumentError,
)
from knack.log import get_logger
from rich.console import Console

from azext_iot.adr.common import (
    DEFAULT_NS_POLICY_NAME,
    DEFAULT_NS_POLICY_CERT_KEY_TYPE,
    DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS,
    CertificateManagementState,
    IdentityType,
    build_mi_body,
)
from azext_iot.adr.providers.base import ADRProvider
from azext_iot.adr.providers.credential import CredentialProvider
from azext_iot.adr.providers.policy import PolicyProvider
from azext_iot.common.utility import wait_for_terminal_state

console = Console()
logger = get_logger(__name__)


_OUTBOUND_MI_MUTEX_MSG = (
    "Specify only one outbound identity: --outbound-mi-system-assigned uses the namespace's "
    "system-assigned identity, --outbound-mi-user-assigned <uami-resource-id> uses a user-assigned "
    "managed identity (the two options are mutually exclusive)."
)

_OUTBOUND_UAMI_PENDING_MSG = (
    "User-assigned managed identity for outbound identity is not yet available from the backend. "
    "Use --outbound-mi-system-assigned instead."
)


def _resolve_outbound_identity(
    outbound_mi_system_assigned: Optional[bool],
    outbound_mi_user_assigned: Optional[str],
) -> Optional[dict]:
    """Return the OutboundIdentity body (or None when no flag provided).

    SAMI and UAMI are mutually exclusive. UAMI is currently rejected because
    it is not yet available from the backend.
    """
    # An empty/whitespace UAMI (e.g. `--outbound-mi-user-assigned ""`) means the caller
    # did not actually supply one. Clear it first so it neither trips the SAMI/UAMI
    # mutually-exclusive check below nor reaches build_mi_body as a malformed value.
    if outbound_mi_user_assigned is not None and not outbound_mi_user_assigned.strip():
        outbound_mi_user_assigned = None
    if outbound_mi_system_assigned and outbound_mi_user_assigned:
        raise MutuallyExclusiveArgumentError(_OUTBOUND_MI_MUTEX_MSG)
    if outbound_mi_user_assigned:
        raise ArgumentUsageError(_OUTBOUND_UAMI_PENDING_MSG)
    return build_mi_body(
        outbound_mi_system_assigned,
        outbound_mi_user_assigned,
        sami_type=IdentityType.system_assigned.value,
        uami_type=IdentityType.user_assigned.value,
    )


class NamespaceProvider(ADRProvider):
    def __init__(self, cmd):
        super(NamespaceProvider, self).__init__(cmd)

    def create(
        self,
        namespace_name: str,
        resource_group_name: str,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        enable_certificate_management: Optional[bool] = None,
        policy_name: Optional[str] = None,
        certificate_key_type: Optional[str] = None,
        certificate_subject: Optional[str] = None,
        certificate_validity_days: Optional[int] = None,
        outbound_mi_system_assigned: Optional[bool] = None,
        outbound_mi_user_assigned: Optional[str] = None,
        **kwargs,
    ):
        # Legacy credential/policy bootstrap (DEPRECATED): triggered only by explicit legacy policy
        # args. `--enable-certificate-management` no longer drives this; it now solely sets the
        # namespace-level `certificateManagement` state (the real API field). Certificate authorities
        # and policies are managed via `iot adr ns ca`.
        should_create_credential_policy = any([
            policy_name,
            certificate_key_type,
            certificate_subject,
            certificate_validity_days,
        ])

        if should_create_credential_policy:
            # Contradictory inputs: cannot bootstrap a credential policy while disabling cert management
            if enable_certificate_management is False:
                raise MutuallyExclusiveArgumentError(
                    "Cannot create a custom credential policy while "
                    "`--enable-certificate-management` is false."
                )

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

        # Default system assigned identity
        namespace_resource["identity"] = {"type": IdentityType.system_assigned.value}

        if tags:
            namespace_resource["tags"] = tags

        outbound_identity = _resolve_outbound_identity(
            outbound_mi_system_assigned, outbound_mi_user_assigned
        )

        properties = {}
        if enable_certificate_management is not None:
            properties["certificateManagement"] = (
                CertificateManagementState.enabled.value
                if enable_certificate_management
                else CertificateManagementState.disabled.value
            )
        if outbound_identity is not None:
            properties["outboundIdentity"] = outbound_identity
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
            namespace_result = wait_for_terminal_state(poller, **kwargs)

        # The create response may omit resourceGroup; backfill it from the request input.
        if not namespace_result.get("resourceGroup"):
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
                    certificate_subject=certificate_subject,
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
            "All child resources (credentials, policies, devices) under namespace '%s' will be deleted.",
            namespace_name,
        )
        logger.warning(
            "Deletion will fail if there are DPS or IoT Hub instances linked to this namespace. Unlink them first."
        )
        poller = self.client.namespaces.begin_delete(
            resource_group_name=resource_group_name, namespace_name=namespace_name
        )
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(f"Deleting namespace {namespace_name}..."):
            return wait_for_terminal_state(poller, **kwargs)

    def update(
        self,
        namespace_name: str,
        resource_group_name: str,
        tags: Optional[Dict[str, str]] = None,
        enable_certificate_management: Optional[bool] = None,
        outbound_mi_system_assigned: Optional[bool] = None,
        outbound_mi_user_assigned: Optional[str] = None,
        **kwargs,
    ):
        # NamespaceUpdate body: tags at top, substantive fields nested under "properties".
        body: dict = {}
        if tags is not None:
            body["tags"] = tags

        properties: dict = {}
        if enable_certificate_management is not None:
            properties["certificateManagement"] = (
                CertificateManagementState.enabled.value
                if enable_certificate_management
                else CertificateManagementState.disabled.value
            )

        outbound_identity = _resolve_outbound_identity(
            outbound_mi_system_assigned, outbound_mi_user_assigned
        )
        if outbound_identity is not None:
            properties["outboundIdentity"] = outbound_identity
        if properties:
            body["properties"] = properties

        poller = self.client.namespaces.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            properties=body,
        )
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(f"Updating namespace {namespace_name}..."):
            return wait_for_terminal_state(poller, **kwargs)
