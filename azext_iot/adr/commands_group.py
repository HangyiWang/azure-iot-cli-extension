# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azext_iot.adr.providers.group import GroupProvider


def adr_group_create(
    cmd,
    group_name: str,
    namespace_name: str,
    resource_group_name: str,
    query: str,
    group_type: str = "Device",
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
):
    provider = GroupProvider(cmd)
    return provider.create(
        group_name=group_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        query=query,
        group_type=group_type,
        display_name=display_name,
        description=description,
        location=location,
        tags=tags,
    )


def adr_group_show(cmd, group_name: str, namespace_name: str, resource_group_name: str):
    provider = GroupProvider(cmd)
    return provider.show(
        group_name=group_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_group_list(cmd, namespace_name: str, resource_group_name: str):
    provider = GroupProvider(cmd)
    return provider.list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_group_delete(cmd, group_name: str, namespace_name: str, resource_group_name: str):
    provider = GroupProvider(cmd)
    return provider.delete(
        group_name=group_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
