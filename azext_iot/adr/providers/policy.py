# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azure.cli.core.azclierror import AzureResponseError, CLIError, ResourceNotFoundError
from azure.core.exceptions import HttpResponseError
from rich.console import Console

from azext_iot.adr.common import (
    DEFAULT_NS_POLICY_CERT_KEY_TYPE,
    DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS,
    POLICY_PARENT_RESOURCE_NOT_FOUND_MSG,
)
from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state

console = Console()


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
            location = namespace.get("location")
            if not location:
                raise AzureResponseError(
                    "Error attempting to determine location from parent Namespace: "
                    "Namespace does not contain a location property."
                )

        # Build certificate configuration when any cert parameter or BYOR is specified
        certificate_config = None
        has_cert_params = any([enable_byor, certificate_key_type, certificate_subject, certificate_validity_days])

        if has_cert_params:
            key_type = certificate_key_type or DEFAULT_NS_POLICY_CERT_KEY_TYPE
            validity_days = certificate_validity_days or DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS

            ca_config = {"keyType": key_type}
            if enable_byor:
                ca_config["bringYourOwnRoot"] = {"enabled": True}

            certificate_config = {
                "certificateAuthorityConfiguration": ca_config,
                "leafCertificateConfiguration": {"validityPeriodInDays": validity_days},
            }

        resource = {"properties": {}}
        if certificate_config:
            resource["properties"]["certificate"] = certificate_config

        with console.status(f"Creating policy '{policy_name}' for namespace {namespace_name}..."):
            poller = self.client.policies.begin_create_or_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                policy_name=policy_name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, policy_name: str, namespace_name: str, resource_group_name: str):
        # Ensure namespace exists
        self.client.namespaces.get(resource_group_name=resource_group_name, namespace_name=namespace_name)

        try:
            return self.client.policies.get(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                policy_name=policy_name,
            )
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
            results = self.client.policies.list_by_credential(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
            return list(results)
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
        # Build a sparse PATCH body so we never round-trip empty `properties` blocks
        # (the backend treats an empty `properties` dict as "no-op" but emitting it
        # adds noise to telemetry / activity logs).
        resource: dict = {}
        if tags is not None:
            resource["tags"] = tags
        if certificate_validity_days is not None:
            resource["properties"] = {
                "certificate": {
                    "leafCertificateConfiguration": {
                        "validityPeriodInDays": certificate_validity_days,
                    }
                }
            }

        with console.status(f"Updating policy '{policy_name}' for namespace {namespace_name}..."):
            poller = self.client.policies.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                policy_name=policy_name,
                properties=resource,
            )
            wait_for_terminal_state(poller, **kwargs)

        # LRO update may return incomplete object; always fetch updated resource
        return self.show(
            policy_name=policy_name, namespace_name=namespace_name, resource_group_name=resource_group_name
        )

    def revoke_issuer(self, policy_name: str, namespace_name: str, resource_group_name: str, **kwargs):
        """Revoke the CA certificate for a policy, triggering regeneration of a new CA."""
        # API endpoint not yet available in current Microsoft.DeviceRegistry preview.
        raise CLIError(
            "'az iot adr ns policy revoke-issuer' is not available yet: the underlying "
            "Microsoft.DeviceRegistry API is still being finalized. Please try again "
            "in a future release."
        )

    def activate_byor(
        self,
        policy_name: str,
        namespace_name: str,
        resource_group_name: str,
        certificate_chain: str,
        **kwargs,
    ):
        """Activate or renew a Bring Your Own Root policy with a signed certificate chain."""
        # API endpoint not yet available in current Microsoft.DeviceRegistry preview.
        raise CLIError(
            "'az iot adr ns policy activate-byor' is not available yet: the underlying "
            "Microsoft.DeviceRegistry API is still being finalized. Please try again "
            "in a future release."
        )
