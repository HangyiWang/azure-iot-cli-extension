# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Optional

from knack.log import get_logger
from rich.console import Console

from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state

console = Console()
logger = get_logger(__name__)


class DeviceProvider(ADRProvider):
    def __init__(self, cmd):
        super(DeviceProvider, self).__init__(cmd)

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
