# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Optional

from knack.log import get_logger

from azext_iot.adr.providers.device import DeviceProvider

logger = get_logger(__name__)


def adr_device_revoke(
    cmd,
    device_name: str,
    namespace_name: str,
    resource_group_name: str,
    disable: Optional[bool] = None,
):
    provider = DeviceProvider(cmd)
    return provider.revoke(
        device_name=device_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        disable=disable,
    )
