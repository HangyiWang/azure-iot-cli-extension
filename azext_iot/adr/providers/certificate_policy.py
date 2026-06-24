# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azure.cli.core.azclierror import RequiredArgumentMissingError, ResourceNotFoundError
from azure.core.exceptions import HttpResponseError

from azext_iot.adr.common import CA_PARENT_RESOURCE_NOT_FOUND_MSG
from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state
from rich.console import Console

console = Console()


class CertificatePolicyProvider(ADRProvider):
    def __init__(self, cmd):
        super(CertificatePolicyProvider, self).__init__(cmd)

    def _handle_parent_not_found(self, e, certificate_authority_name, namespace_name, resource_group_name):
        if e.status_code == 404 and "ParentResourceNotFound" in str(e):
            raise ResourceNotFoundError(
                CA_PARENT_RESOURCE_NOT_FOUND_MSG.format(
                    certificate_authority_name=certificate_authority_name,
                    namespace_name=namespace_name,
                    resource_group_name=resource_group_name,
                )
            )
        raise e

    def create(
        self,
        certificate_policy_name: str,
        certificate_authority_name: str,
        namespace_name: str,
        resource_group_name: str,
        validity_days: int,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        location = self._resolve_location(namespace_name, resource_group_name, location)

        resource = {
            "location": location,
            "properties": {"certificate": {"validityPeriodInDays": validity_days}},
        }
        if tags is not None:
            resource["tags"] = tags

        no_wait = kwargs.pop("no_wait", False)
        try:
            poller = self.client.certificate_policies.begin_create_or_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                certificate_authority_name=certificate_authority_name,
                certificate_policy_name=certificate_policy_name,
                resource=resource,
            )
        except HttpResponseError as e:
            self._handle_parent_not_found(
                e, certificate_authority_name, namespace_name, resource_group_name
            )

        if no_wait:
            return poller
        with console.status(
            f"Creating certificate policy '{certificate_policy_name}' on certificate authority "
            f"{certificate_authority_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)

    def show(
        self,
        certificate_policy_name: str,
        certificate_authority_name: str,
        namespace_name: str,
        resource_group_name: str,
    ):
        try:
            return self.client.certificate_policies.get(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                certificate_authority_name=certificate_authority_name,
                certificate_policy_name=certificate_policy_name,
            )
        except HttpResponseError as e:
            self._handle_parent_not_found(e, certificate_authority_name, namespace_name, resource_group_name)

    def list(self, certificate_authority_name: str, namespace_name: str, resource_group_name: str):
        try:
            return list(
                self.client.certificate_policies.list_by_certificate_authority(
                    resource_group_name=resource_group_name,
                    namespace_name=namespace_name,
                    certificate_authority_name=certificate_authority_name,
                )
            )
        except HttpResponseError as e:
            self._handle_parent_not_found(e, certificate_authority_name, namespace_name, resource_group_name)

    def update(
        self,
        certificate_policy_name: str,
        certificate_authority_name: str,
        namespace_name: str,
        resource_group_name: str,
        validity_days: Optional[int] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        if validity_days is None and tags is None:
            raise RequiredArgumentMissingError(
                "Nothing to update. Provide --validity-days and/or --tags to update the certificate policy."
            )

        properties: dict = {}
        if tags is not None:
            properties["tags"] = tags
        if validity_days is not None:
            properties["properties"] = {"certificate": {"validityPeriodInDays": validity_days}}

        no_wait = kwargs.pop("no_wait", False)
        try:
            poller = self.client.certificate_policies.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                certificate_authority_name=certificate_authority_name,
                certificate_policy_name=certificate_policy_name,
                properties=properties,
            )
        except HttpResponseError as e:
            self._handle_parent_not_found(e, certificate_authority_name, namespace_name, resource_group_name)

        if no_wait:
            return poller
        with console.status(
            f"Updating certificate policy '{certificate_policy_name}' on certificate authority "
            f"{certificate_authority_name}..."
        ):
            wait_for_terminal_state(poller, **kwargs)

        return self.show(
            certificate_policy_name=certificate_policy_name,
            certificate_authority_name=certificate_authority_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
        )

    def delete(
        self,
        certificate_policy_name: str,
        certificate_authority_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        no_wait = kwargs.pop("no_wait", False)
        try:
            poller = self.client.certificate_policies.begin_delete(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                certificate_authority_name=certificate_authority_name,
                certificate_policy_name=certificate_policy_name,
            )
        except HttpResponseError as e:
            self._handle_parent_not_found(e, certificate_authority_name, namespace_name, resource_group_name)

        if no_wait:
            return poller
        with console.status(
            f"Deleting certificate policy '{certificate_policy_name}' from certificate authority "
            f"{certificate_authority_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)
