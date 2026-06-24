# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Optional

from azure.cli.core.azclierror import AzureResponseError
from knack.log import get_logger

from azext_iot._factory import adr_service_factory

__all__ = ["ADRProvider"]

logger = get_logger(__name__)


class ADRProvider(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.client = adr_service_factory(cmd.cli_ctx)

    def _resolve_location(
        self, namespace_name: str, resource_group_name: str, location: Optional[str] = None
    ):
        """Resolve a child resource location from its parent Device Registry namespace.

        Child resources (certificate authorities, certificate policies, adaptive devices) must be
        co-located with their parent namespace, so default to the namespace's location when the
        caller does not specify one explicitly.
        """
        if location:
            return location
        namespace = self.client.namespaces.get(
            resource_group_name=resource_group_name, namespace_name=namespace_name
        )
        location = namespace.get("location")
        if not location:
            raise AzureResponseError(
                "Error attempting to determine location from parent Namespace: "
                "Namespace does not contain a location property."
            )
        return location

    def _ensure_location(self, cli_ctx, resource_group_name: str, location: Optional[str] = None):
        if location:
            return location

        # Get resource group location as fallback
        from azure.cli.core.commands.client_factory import get_mgmt_service_client
        from azure.mgmt.resource import ResourceManagementClient

        resource_client = get_mgmt_service_client(cli_ctx, ResourceManagementClient)
        rg = resource_client.resource_groups.get(resource_group_name)
        return rg.location
