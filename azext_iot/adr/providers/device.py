# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, Optional

from knack.log import get_logger
from rich.console import Console

from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state

console = Console()
logger = get_logger(__name__)


class DeviceProvider(ADRProvider):
    def __init__(self, cmd):
        super(DeviceProvider, self).__init__(cmd)

    def show(self, device_name: str, namespace_name: str, resource_group_name: str):
        return self.client.namespace_devices.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=device_name,
        )

    def list(self, namespace_name: str, resource_group_name: str):
        return list(
            self.client.namespace_devices.list_by_resource_group(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
        )

    def update(
        self,
        device_name: str,
        namespace_name: str,
        resource_group_name: str,
        enabled: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        operating_system_version: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        policy_resource_id: Optional[str] = None,
        **kwargs,
    ):
        """Update a device in the namespace."""
        properties = {}

        if tags is not None:
            properties["tags"] = tags
        if enabled is not None:
            properties["enabled"] = enabled
        if operating_system_version is not None:
            properties["operating_system_version"] = operating_system_version
        if attributes is not None:
            properties["attributes"] = attributes
        if policy_resource_id is not None:
            properties["policy"] = {"resource_id": policy_resource_id}

        with console.status(
            f"Updating device '{device_name}' in namespace {namespace_name}..."
        ):
            poller = self.client.namespace_devices.begin_update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                device_name=device_name,
                properties=properties,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def revoke(
        self,
        device_name: str,
        namespace_name: str,
        resource_group_name: str,
        disable: Optional[bool] = None,
        **kwargs,
    ):
        """Revoke credentials for a device in the namespace."""
        with console.status(
            f"Revoking credentials for device '{device_name}' in namespace {namespace_name}..."
        ):
            poller = self.client.namespace_devices.begin_revoke(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                device_name=device_name,
                disable=disable,
            )
            return wait_for_terminal_state(poller, **kwargs)
