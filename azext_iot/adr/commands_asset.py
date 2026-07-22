# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, Optional

from azext_iot.adr.providers.asset import AssetProvider


def adr_asset_create(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    properties: Any,
    extended_location: Any,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    no_wait: bool = False,
):
    provider = AssetProvider(cmd)
    return provider.create(
        resource_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        properties=properties,
        extended_location=extended_location,
        location=location,
        tags=tags,
        no_wait=no_wait,
    )


def adr_asset_show(
    cmd, asset_name: str, namespace_name: str, resource_group_name: str
):
    provider = AssetProvider(cmd)
    return provider.show(
        resource_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_asset_list(cmd, namespace_name: str, resource_group_name: str):
    provider = AssetProvider(cmd)
    return provider.list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_asset_update(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    properties: Any = None,
    tags: Optional[Dict[str, str]] = None,
    no_wait: bool = False,
):
    provider = AssetProvider(cmd)
    return provider.update(
        resource_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        properties=properties,
        tags=tags,
        no_wait=no_wait,
    )


def adr_asset_delete(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    no_wait: bool = False,
):
    provider = AssetProvider(cmd)
    return provider.delete(
        resource_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )


def adr_asset_execute_action(
    cmd,
    asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    management_action_name: str,
    management_group_name: str,
    payload: Any = None,
    no_wait: bool = False,
):
    provider = AssetProvider(cmd)
    return provider.execute_action(
        resource_name=asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        management_action_name=management_action_name,
        management_group_name=management_group_name,
        payload=payload,
        no_wait=no_wait,
    )
