# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azext_iot.adr.providers.device import DeviceProvider


def adr_device_create(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    operating_system: Optional[str] = None,
    operating_system_version: Optional[str] = None,
    external_device_id: Optional[str] = None,
    enabled: Optional[bool] = None,
    attributes: Optional[str] = None,
    endpoints: Optional[str] = None,
    discovered_device_ref: Optional[str] = None,
    policy_resource_id: Optional[str] = None,
    no_wait: bool = False,
):
    provider = DeviceProvider(cmd)
    return provider.create(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        location=location,
        tags=tags,
        manufacturer=manufacturer,
        model=model,
        operating_system=operating_system,
        operating_system_version=operating_system_version,
        external_device_id=external_device_id,
        enabled=enabled,
        attributes=attributes,
        endpoints=endpoints,
        discovered_device_ref=discovered_device_ref,
        policy_resource_id=policy_resource_id,
        no_wait=no_wait,
    )


def adr_device_delete(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    no_wait: bool = False,
):
    provider = DeviceProvider(cmd)
    return provider.delete(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )


def adr_device_show(cmd, device_name: str, namespace_name: str, resource_group_name: str):
    provider = DeviceProvider(cmd)
    return provider.show(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_device_list(cmd, namespace_name: str, resource_group_name: str):
    provider = DeviceProvider(cmd)
    return provider.list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_device_update(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    enabled: Optional[bool] = None,
    tags: Optional[Dict[str, str]] = None,
    operating_system_version: Optional[str] = None,
    attributes: Optional[str] = None,
    endpoints: Optional[str] = None,
    policy_resource_id: Optional[str] = None,
    no_wait: bool = False,
):
    provider = DeviceProvider(cmd)
    return provider.update(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        enabled=enabled,
        tags=tags,
        operating_system_version=operating_system_version,
        attributes=attributes,
        endpoints=endpoints,
        policy_resource_id=policy_resource_id,
        no_wait=no_wait,
    )
