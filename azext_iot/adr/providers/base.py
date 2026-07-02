# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Optional

from azure.cli.core.azclierror import AzureResponseError, ResourceNotFoundError
from azure.core.exceptions import HttpResponseError
from knack.log import get_logger
from rich.console import Console

from azext_iot._factory import adr_service_factory
from azext_iot.common.utility import wait_for_terminal_state

__all__ = ["ADRProvider", "console"]

logger = get_logger(__name__)

# Shared Rich console for all ADR providers. Declared once here (instead of a
# module-level `Console()` in every provider) so spinners/print styling stay consistent.
console = Console()


class ADRProvider(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.client = adr_service_factory(cmd.cli_ctx)

    def _wait(self, poller, status_message: str, **kwargs):
        """Block on a long-running-operation poller, honoring ``--no-wait``.

        This captures the epilogue shared by nearly every mutating ADR command:
        pop ``no_wait`` from kwargs and return the poller immediately when set,
        otherwise show ``status_message`` in a spinner while waiting for the
        operation to reach a terminal state. Remaining kwargs are forwarded to
        ``wait_for_terminal_state`` (e.g. polling interval overrides).
        """
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(status_message):
            return wait_for_terminal_state(poller, **kwargs)

    def _raise_if_parent_not_found(self, error: Exception, message: str):
        """Translate a backend "ParentResourceNotFound" 404 into a friendly error.

        ARM returns an opaque 404 when a parent in the resource path (e.g. the
        certificate authority behind a certificate policy) does not exist. Callers
        pass a resource-specific ``message`` so the user gets actionable guidance.
        Any other error is re-raised unchanged.
        """
        if (
            isinstance(error, HttpResponseError)
            and error.status_code == 404
            and "ParentResourceNotFound" in str(error)
        ):
            raise ResourceNotFoundError(message)
        raise error

    def _resolve_location(
        self, namespace_name: str, resource_group_name: str, location: Optional[str] = None
    ):
        """Resolve a child resource location from its parent Device Registry namespace.

        Child resources (certificate authorities, certificate policies, registry devices) must be
        co-located with their parent namespace, so default to the namespace's location when the
        caller does not specify one explicitly. Use this when a parent namespace is guaranteed to
        exist; use ``_ensure_location`` instead when only the resource group is available.
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
        """Resolve a location, falling back to the resource group's location.

        Unlike ``_resolve_location`` (which reads the parent namespace), this is used when there
        is no parent resource yet — e.g. creating the namespace itself — so the resource group's
        location is the sensible default.
        """
        if location:
            return location

        # Get resource group location as fallback
        from azure.cli.core.commands.client_factory import get_mgmt_service_client
        from azure.mgmt.resource import ResourceManagementClient

        resource_client = get_mgmt_service_client(cli_ctx, ResourceManagementClient)
        rg = resource_client.resource_groups.get(resource_group_name)
        return rg.location
