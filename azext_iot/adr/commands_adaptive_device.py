# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from knack.log import get_logger

from azext_iot.adr.providers.adaptive_device import AdaptiveDeviceProvider

logger = get_logger(__name__)


def adr_adaptive_device_create(
    cmd,
    adaptive_device_name: str,
    namespace_name: str,
    resource_group_name: str,
    external_device_id: Optional[str] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    hardware_revision: Optional[str] = None,
    software_revision: Optional[str] = None,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs,
):
    provider = AdaptiveDeviceProvider(cmd)
    return provider.create(
        adaptive_device_name=adaptive_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        external_device_id=external_device_id,
        manufacturer=manufacturer,
        model=model,
        hardware_revision=hardware_revision,
        software_revision=software_revision,
        location=location,
        tags=tags,
        **kwargs,
    )


def adr_adaptive_device_show(
    cmd, adaptive_device_name: str, namespace_name: str, resource_group_name: str
):
    provider = AdaptiveDeviceProvider(cmd)
    return provider.show(
        adaptive_device_name=adaptive_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_adaptive_device_list(cmd, namespace_name: str, resource_group_name: str):
    provider = AdaptiveDeviceProvider(cmd)
    return provider.list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_adaptive_device_update(
    cmd,
    adaptive_device_name: str,
    namespace_name: str,
    resource_group_name: str,
    external_device_id: Optional[str] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    hardware_revision: Optional[str] = None,
    software_revision: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs,
):
    provider = AdaptiveDeviceProvider(cmd)
    return provider.update(
        adaptive_device_name=adaptive_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        external_device_id=external_device_id,
        manufacturer=manufacturer,
        model=model,
        hardware_revision=hardware_revision,
        software_revision=software_revision,
        tags=tags,
        **kwargs,
    )


def adr_adaptive_device_delete(
    cmd, adaptive_device_name: str, namespace_name: str, resource_group_name: str, **kwargs
):
    provider = AdaptiveDeviceProvider(cmd)
    return provider.delete(
        adaptive_device_name=adaptive_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        **kwargs,
    )
