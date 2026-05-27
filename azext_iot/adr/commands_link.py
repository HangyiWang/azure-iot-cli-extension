# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Optional

from azext_iot.adr.providers.linking import (
    LINK_KIND_DPS,
    LINK_KIND_HUB,
    LinkProvider,
)


# ---- IoT Hub link commands ----

def adr_link_hub_add(
    cmd,
    link_name: str,
    namespace_name: str,
    resource_group_name: str,
    resource_id: str,
    mi_system_assigned: bool = False,
    mi_user_assigned: Optional[str] = None,
    endpoint_type: Optional[str] = None,
):
    provider = LinkProvider(cmd)
    return provider.add(
        kind=LINK_KIND_HUB,
        link_name=link_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        resource_id=resource_id,
        mi_system_assigned=mi_system_assigned,
        mi_user_assigned=mi_user_assigned,
        endpoint_type=endpoint_type,
    )


def adr_link_hub_show(cmd, link_name: str, namespace_name: str, resource_group_name: str):
    provider = LinkProvider(cmd)
    return provider.show(
        kind=LINK_KIND_HUB,
        link_name=link_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_link_hub_list(cmd, namespace_name: str, resource_group_name: str):
    provider = LinkProvider(cmd)
    return provider.list(
        kind=LINK_KIND_HUB,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_link_hub_remove(cmd, link_name: str, namespace_name: str, resource_group_name: str):
    provider = LinkProvider(cmd)
    return provider.remove(
        kind=LINK_KIND_HUB,
        link_name=link_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


# ---- DPS link commands ----

def adr_link_dps_add(
    cmd,
    link_name: str,
    namespace_name: str,
    resource_group_name: str,
    resource_id: str,
    mi_system_assigned: bool = False,
    mi_user_assigned: Optional[str] = None,
    endpoint_type: Optional[str] = None,
):
    provider = LinkProvider(cmd)
    return provider.add(
        kind=LINK_KIND_DPS,
        link_name=link_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        resource_id=resource_id,
        mi_system_assigned=mi_system_assigned,
        mi_user_assigned=mi_user_assigned,
        endpoint_type=endpoint_type,
    )


def adr_link_dps_show(cmd, link_name: str, namespace_name: str, resource_group_name: str):
    provider = LinkProvider(cmd)
    return provider.show(
        kind=LINK_KIND_DPS,
        link_name=link_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_link_dps_list(cmd, namespace_name: str, resource_group_name: str):
    provider = LinkProvider(cmd)
    return provider.list(
        kind=LINK_KIND_DPS,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_link_dps_remove(cmd, link_name: str, namespace_name: str, resource_group_name: str):
    provider = LinkProvider(cmd)
    return provider.remove(
        kind=LINK_KIND_DPS,
        link_name=link_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
