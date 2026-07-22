# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, Optional

from azext_iot.adr.providers.discovered_device import DiscoveredDeviceProvider


def adr_discovered_device_create(
    cmd,
    discovered_device_name: str,
    namespace_name: str,
    resource_group_name: str,
    properties: Any,
    extended_location: Any,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    no_wait: bool = False,
):
    provider = DiscoveredDeviceProvider(cmd)
    return provider.create(
        resource_name=discovered_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        properties=properties,
        extended_location=extended_location,
        location=location,
        tags=tags,
        no_wait=no_wait,
    )


def adr_discovered_device_show(
    cmd,
    discovered_device_name: str,
    namespace_name: str,
    resource_group_name: str,
):
    provider = DiscoveredDeviceProvider(cmd)
    return provider.show(
        resource_name=discovered_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_discovered_device_list(
    cmd, namespace_name: str, resource_group_name: str
):
    provider = DiscoveredDeviceProvider(cmd)
    return provider.list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_discovered_device_update(
    cmd,
    discovered_device_name: str,
    namespace_name: str,
    resource_group_name: str,
    properties: Any = None,
    tags: Optional[Dict[str, str]] = None,
    no_wait: bool = False,
):
    provider = DiscoveredDeviceProvider(cmd)
    return provider.update(
        resource_name=discovered_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        properties=properties,
        tags=tags,
        no_wait=no_wait,
    )


def adr_discovered_device_delete(
    cmd,
    discovered_device_name: str,
    namespace_name: str,
    resource_group_name: str,
    no_wait: bool = False,
):
    provider = DiscoveredDeviceProvider(cmd)
    return provider.delete(
        resource_name=discovered_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )
