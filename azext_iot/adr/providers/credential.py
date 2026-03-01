# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import TYPE_CHECKING, Dict, Optional

from azure.cli.core.azclierror import AzureResponseError, ResourceNotFoundError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich.console import Console

from azext_iot.adr.common import CREDENTIAL_NOT_FOUND_MSG
from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state

if TYPE_CHECKING:
    from azure.core.polling import LROPoller

console = Console()
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

        with console.status(f"Creating credentials for namespace {namespace_name}..."):
            poller = self.client.credentials.begin_create_or_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                location=location,
                tags=tags,
            )
            result = wait_for_terminal_state(poller, **kwargs)
            return result.serialize(keep_readonly=True) if result else result

    def show(self, namespace_name: str, resource_group_name: str):
        # Check if parent namespace exists, will 404 if not
        self.client.namespaces.get(resource_group_name=resource_group_name, namespace_name=namespace_name)

        # Show friendly error if credential doesn't exist
        try:
            result = self.client.credentials.get(resource_group_name=resource_group_name, namespace_name=namespace_name)
            return result.serialize(keep_readonly=True)
        except HttpResponseError as e:
            if e.status_code == 404:
                raise ResourceNotFoundError(
                    CREDENTIAL_NOT_FOUND_MSG.format(
                        namespace_name=namespace_name, resource_group_name=resource_group_name
                    )
                )
            raise

    def delete(self, namespace_name: str, resource_group_name: str, **kwargs):
        with console.status(f"Deleting credentials for namespace {namespace_name}..."):
            poller = self.client.credentials.begin_delete(
                resource_group_name=resource_group_name, namespace_name=namespace_name
            )
            return wait_for_terminal_state(poller, **kwargs)

    def synchronize(self, namespace_name: str, resource_group_name: str, **kwargs):
        with console.status(f"Synchronizing credentials for namespace {namespace_name}..."):
            poller: LROPoller = self.client.credentials.begin_synchronize(
                resource_group_name=resource_group_name, namespace_name=namespace_name
            )
            try:
                result = wait_for_terminal_state(poller, **kwargs)
            except HttpResponseError as e:
                # The backend returns 200 OK with an empty body when the LRO completes,
                # but ARMPolling expects a "status" or "provisioningState" field in the
                # response to determine the terminal state. Without it, ARMPolling falls
                # back to the HTTP reason phrase "OK" which is not a recognized terminal
                # state, causing a false-positive error. A real failure would surface as
                # a 4xx/5xx status code. Swallow the false positive here.
                if e.response and e.response.status_code == 200:
                    logger.debug(
                        "Synchronize LRO returned HTTP 200 but ARMPolling could not "
                        "determine terminal state from response body. Treating as success."
                    )
                    result = None
                else:
                    raise
            console.print(
                f"Successfully synchronized credentials for namespace '{namespace_name}'",
                style="green",
            )
            return result
