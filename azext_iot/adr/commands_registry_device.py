# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from knack.log import get_logger

from azext_iot.adr.common import RegistryDeviceEnablementState
from azext_iot.adr.providers.registry_device import RegistryDeviceProvider

logger = get_logger(__name__)


def adr_registry_device_create(
    cmd,
    registry_device_name: str,
    namespace_name: str,
    resource_group_name: str,
    external_device_id: Optional[str] = None,
    enablement_state: str = RegistryDeviceEnablementState.enabled.value,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    hardware_revision: Optional[str] = None,
    software_revision: Optional[str] = None,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs,
):
    provider = RegistryDeviceProvider(cmd)
    return provider.create(
        registry_device_name=registry_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        external_device_id=external_device_id,
        enablement_state=enablement_state,
        manufacturer=manufacturer,
        model=model,
        hardware_revision=hardware_revision,
        software_revision=software_revision,
        location=location,
        tags=tags,
        **kwargs,
    )


def adr_registry_device_show(
    cmd, registry_device_name: str, namespace_name: str, resource_group_name: str
):
    provider = RegistryDeviceProvider(cmd)
    return provider.show(
        registry_device_name=registry_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_registry_device_list(cmd, namespace_name: str, resource_group_name: str):
    provider = RegistryDeviceProvider(cmd)
    return provider.list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_registry_device_update(
    cmd,
    registry_device_name: str,
    namespace_name: str,
    resource_group_name: str,
    enablement_state: Optional[str] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    hardware_revision: Optional[str] = None,
    software_revision: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    **kwargs,
):
    provider = RegistryDeviceProvider(cmd)
    return provider.update(
        registry_device_name=registry_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        enablement_state=enablement_state,
        manufacturer=manufacturer,
        model=model,
        hardware_revision=hardware_revision,
        software_revision=software_revision,
        tags=tags,
        **kwargs,
    )


def adr_registry_device_delete(
    cmd, registry_device_name: str, namespace_name: str, resource_group_name: str, **kwargs
):
    provider = RegistryDeviceProvider(cmd)
    return provider.delete(
        registry_device_name=registry_device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        **kwargs,
    )
