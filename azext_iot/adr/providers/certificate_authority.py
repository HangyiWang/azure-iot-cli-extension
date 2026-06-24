# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azure.cli.core.azclierror import RequiredArgumentMissingError

from azext_iot.adr.common import DEFAULT_NS_CA_KEY_TYPE
from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state
from rich.console import Console

console = Console()


class CertificateAuthorityProvider(ADRProvider):
    def __init__(self, cmd):
        super(CertificateAuthorityProvider, self).__init__(cmd)

    def create(
        self,
        certificate_authority_name: str,
        namespace_name: str,
        resource_group_name: str,
        certificate_authority_type: str,
        key_type: Optional[str] = None,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        location = self._resolve_location(namespace_name, resource_group_name, location)

        resource = {
            "location": location,
            "properties": {
                "certificateAuthorityType": certificate_authority_type,
                "keyType": key_type or DEFAULT_NS_CA_KEY_TYPE,
            },
        }
        if tags is not None:
            resource["tags"] = tags

        no_wait = kwargs.pop("no_wait", False)
        poller = self.client.certificate_authorities.begin_create_or_replace(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            certificate_authority_name=certificate_authority_name,
            resource=resource,
        )
        if no_wait:
            return poller
        with console.status(
            f"Creating certificate authority '{certificate_authority_name}' on namespace {namespace_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, certificate_authority_name: str, namespace_name: str, resource_group_name: str):
        return self.client.certificate_authorities.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            certificate_authority_name=certificate_authority_name,
        )

    def list(self, namespace_name: str, resource_group_name: str):
        return list(
            self.client.certificate_authorities.list_by_namespace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
        )

    def update(
        self,
        certificate_authority_name: str,
        namespace_name: str,
        resource_group_name: str,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        if tags is None:
            raise RequiredArgumentMissingError(
                "Nothing to update. Provide --tags to update the certificate authority."
            )

        properties: dict = {"tags": tags}

        no_wait = kwargs.pop("no_wait", False)
        poller = self.client.certificate_authorities.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            certificate_authority_name=certificate_authority_name,
            properties=properties,
        )
        if no_wait:
            return poller
        with console.status(
            f"Updating certificate authority '{certificate_authority_name}' on namespace {namespace_name}..."
        ):
            wait_for_terminal_state(poller, **kwargs)

        return self.show(
            certificate_authority_name=certificate_authority_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
        )

    def delete(self, certificate_authority_name: str, namespace_name: str, resource_group_name: str, **kwargs):
        no_wait = kwargs.pop("no_wait", False)
        poller = self.client.certificate_authorities.begin_delete(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            certificate_authority_name=certificate_authority_name,
        )
        if no_wait:
            return poller
        with console.status(
            f"Deleting certificate authority '{certificate_authority_name}' from namespace {namespace_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)

    def activate(
        self,
        certificate_authority_name: str,
        namespace_name: str,
        resource_group_name: str,
        certificate_chain: str,
        **kwargs,
    ):
        body = {"certificateChain": certificate_chain}
        no_wait = kwargs.pop("no_wait", False)
        poller = self.client.certificate_authorities.begin_activate(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            certificate_authority_name=certificate_authority_name,
            body=body,
        )
        if no_wait:
            return poller
        with console.status(
            f"Activating certificate authority '{certificate_authority_name}' on namespace {namespace_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)

    def revoke(self, certificate_authority_name: str, namespace_name: str, resource_group_name: str, **kwargs):
        no_wait = kwargs.pop("no_wait", False)
        poller = self.client.certificate_authorities.begin_revoke(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            certificate_authority_name=certificate_authority_name,
        )
        if no_wait:
            return poller
        with console.status(
            f"Revoking certificate authority '{certificate_authority_name}' on namespace {namespace_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)
