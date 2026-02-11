# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azure.cli.core.azclierror import AzureResponseError, ResourceNotFoundError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich.console import Console

from azext_iot.adr.common import (
    DEFAULT_NS_POLICY_CERT_KEY_TYPE,
    DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS,
    POLICY_PARENT_RESOURCE_NOT_FOUND_MSG,
)
from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state
from azext_iot.sdk.deviceregistry.mgmt.models import (
    CertificateAuthorityConfiguration,
    CertificateConfiguration,
    CertificateConfigurationUpdate,
    LeafCertificateConfiguration,
    LeafCertificateConfigurationUpdate,
)

console = Console()
logger = get_logger(__name__)


class PolicyProvider(ADRProvider):
    def __init__(self, cmd):
        super(PolicyProvider, self).__init__(cmd)

    def create(
        self,
        policy_name: str,
        namespace_name: str,
        resource_group_name: str,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        certificate_key_type: Optional[str] = None,
        certificate_subject: Optional[str] = None,
        certificate_validity_days: Optional[int] = None,
        enable_byor: Optional[bool] = None,
        **kwargs,
    ):

        if not location:
            namespace = self.client.namespaces.get(
                resource_group_name=resource_group_name, namespace_name=namespace_name
            )
            location = namespace.location
            if not location:
                raise AzureResponseError(
                    "Error attempting to determine location from parent Namespace: "
                    "Namespace does not contain a location property."
                )

        # Build certificate configuration model
        certificate_config = None

        # If user provides custom values, create custom policy cert object
        if certificate_key_type or certificate_subject or certificate_validity_days:
            # Set defaults for required parameters if not provided
            if certificate_key_type is None:
                certificate_key_type = DEFAULT_NS_POLICY_CERT_KEY_TYPE
            if certificate_validity_days is None:
                certificate_validity_days = DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS

            ca_config = {"keyType": certificate_key_type}
            if certificate_subject:
                ca_config["subject"] = certificate_subject
            certificate_config["certificateAuthorityConfiguration"] = ca_config
            certificate_config["leafCertificateConfiguration"] = {"validityPeriodInDays": certificate_validity_days}
            properties["certificate"] = certificate_config

        # Enable Bring Your Own Root if requested
        if enable_byor:
            if "certificate" not in properties:
                properties["certificate"] = {}
            properties["certificate"]["bringYourOwnRoot"] = {"enabled": True}

        policy_resource["properties"] = properties

        with console.status(f"Creating policy '{policy_name}' for namespace {namespace_name}..."):
            poller = self.client.policies.begin_create_or_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                policy_name=policy_name,
                certificate=certificate_config,
            )
            result = wait_for_terminal_state(poller, **kwargs)
            serialized = result.serialize(keep_readonly=True) if result else result
            logger.warning("DEBUG policy create result: %s", serialized)
            return serialized

    def show(self, policy_name: str, namespace_name: str, resource_group_name: str):
        # Ensure namespace exists
        self.client.namespaces.get(resource_group_name=resource_group_name, namespace_name=namespace_name)

        try:
            result = self.client.policies.get(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                policy_name=policy_name,
            )
            return result.serialize(keep_readonly=True)
        except HttpResponseError as e:
            if e.status_code == 404 and "ParentResourceNotFound" in str(e):
                raise ResourceNotFoundError(
                    POLICY_PARENT_RESOURCE_NOT_FOUND_MSG.format(
                        namespace_name=namespace_name, resource_group_name=resource_group_name
                    )
                )
            raise

    def list(self, namespace_name: str, resource_group_name: str):
        # Ensure namespace exists
        self.client.namespaces.get(resource_group_name=resource_group_name, namespace_name=namespace_name)

        try:
            results = self.client.policies.list_by_resource_group(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
            return [item.serialize(keep_readonly=True) for item in results]
        except HttpResponseError as e:
            if e.status_code == 404 and "ParentResourceNotFound" in str(e):
                raise ResourceNotFoundError(
                    POLICY_PARENT_RESOURCE_NOT_FOUND_MSG.format(
                        namespace_name=namespace_name, resource_group_name=resource_group_name
                    )
                )
            raise

    def delete(self, policy_name: str, namespace_name: str, resource_group_name: str, **kwargs):
        with console.status(f"Deleting policy '{policy_name}' from namespace {namespace_name}..."):
            poller = self.client.policies.begin_delete(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                policy_name=policy_name,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def update(
        self,
        policy_name: str,
        namespace_name: str,
        resource_group_name: str,
        tags: Optional[Dict[str, str]] = None,
        certificate_key_type: Optional[str] = None,
        certificate_validity_days: Optional[int] = None,
        **kwargs,
    ):
        # Build certificate update model if needed
        cert_update = None
        if certificate_validity_days is not None:
            leaf_update = LeafCertificateConfigurationUpdate(
                validity_period_in_days=certificate_validity_days
            )
            cert_update = CertificateConfigurationUpdate(
                leaf_certificate_configuration=leaf_update
            )

        with console.status(f"Updating policy '{policy_name}' for namespace {namespace_name}..."):
            poller = self.client.policies.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                policy_name=policy_name,
                certificate=cert_update,
            )
<<<<<<< HEAD
            return wait_for_terminal_state(poller, **kwargs)

    def revoke_issuer(self, policy_name: str, namespace_name: str, resource_group_name: str, **kwargs):
        """Revoke the CA certificate for a policy, triggering regeneration of a new CA."""
        with console.status(f"Revoking issuer certificate for policy '{policy_name}' in namespace {namespace_name}..."):
            poller = self.client.policies.begin_revoke_issuer(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                policy_name=policy_name,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def activate_byor(
        self,
        policy_name: str,
        namespace_name: str,
        resource_group_name: str,
        certificate_chain: str,
        **kwargs,
    ):
        """Activate or renew a Bring Your Own Root policy with a signed certificate chain."""
        with console.status(
            f"Activating BYOR certificate for policy '{policy_name}' in namespace {namespace_name}..."
        ):
            poller = self.client.policies.begin_activate_bring_your_own_root(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                policy_name=policy_name,
                certificate_chain=certificate_chain,
            )
            return wait_for_terminal_state(poller, **kwargs)
=======
            wait_for_terminal_state(poller, **kwargs)

        # LRO update may return incomplete object; always fetch updated resource
        return self.show(
            policy_name=policy_name, namespace_name=namespace_name, resource_group_name=resource_group_name
        )
>>>>>>> users/hangyiwang/update-new-adr-sdk
