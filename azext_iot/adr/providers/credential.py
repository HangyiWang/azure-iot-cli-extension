# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Dict, Optional

from azure.cli.core.azclierror import ResourceNotFoundError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger

from azext_iot.adr.common import CREDENTIAL_NOT_FOUND_MSG
from azext_iot.adr.providers.base import ADRProvider, console

if TYPE_CHECKING:
    from azure.core.polling import LROPoller

logger = get_logger(__name__)


class CredentialProvider(ADRProvider):
    def __init__(self, cmd):
        super(CredentialProvider, self).__init__(cmd)

    def create(
        self,
        namespace_name: str,
        resource_group_name: str,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        location = self._resolve_location(namespace_name, resource_group_name, location)
        resource = {"location": location}
        if tags is not None:
            resource["tags"] = tags
        poller = self.client.credentials.begin_create_or_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            resource=resource,
        )
        return self._wait(
            poller,
            f"Creating credentials for namespace {namespace_name}...",
            **kwargs,
        )

    def show(self, namespace_name: str, resource_group_name: str):
        # Check if parent namespace exists, will 404 if not
        self.client.namespaces.get(resource_group_name=resource_group_name, namespace_name=namespace_name)

        # Show friendly error if credential doesn't exist
        try:
            return self.client.credentials.get(resource_group_name=resource_group_name, namespace_name=namespace_name)
        except HttpResponseError as e:
            if e.status_code == 404:
                raise ResourceNotFoundError(
                    CREDENTIAL_NOT_FOUND_MSG.format(
                        namespace_name=namespace_name, resource_group_name=resource_group_name
                    )
                )
            raise

    def delete(self, namespace_name: str, resource_group_name: str, **kwargs):
        poller = self.client.credentials.begin_delete(
            resource_group_name=resource_group_name, namespace_name=namespace_name
        )
        return self._wait(
            poller,
            f"Deleting credentials for namespace {namespace_name}...",
            **kwargs,
        )

    def synchronize(self, namespace_name: str, resource_group_name: str, **kwargs):
        poller: LROPoller = self.client.credentials.begin_synchronize(
            resource_group_name=resource_group_name, namespace_name=namespace_name
        )
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        try:
            result = self._wait(
                poller,
                f"Synchronizing credentials for namespace {namespace_name}...",
                **kwargs,
            )
        except HttpResponseError as e:
            # The service can complete this action with an empty 200 response,
            # which older ARMPolling versions do not recognize as terminal.
            if not e.response or e.response.status_code != 200:
                raise
            logger.debug("Treating the empty HTTP 200 synchronize response as success.")
            result = None
        console.print(
            f"Successfully synchronized credentials for namespace '{namespace_name}'",
            style="green",
        )
        return result
