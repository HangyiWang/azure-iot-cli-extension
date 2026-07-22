# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, Optional

from azext_iot.adr.providers.discovered_asset import DiscoveredAssetProvider


def adr_discovered_asset_create(
    cmd,
    discovered_asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    properties: Any,
    extended_location: Any,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    no_wait: bool = False,
):
    provider = DiscoveredAssetProvider(cmd)
    return provider.create(
        resource_name=discovered_asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        properties=properties,
        extended_location=extended_location,
        location=location,
        tags=tags,
        no_wait=no_wait,
    )


def adr_discovered_asset_show(
    cmd,
    discovered_asset_name: str,
    namespace_name: str,
    resource_group_name: str,
):
    provider = DiscoveredAssetProvider(cmd)
    return provider.show(
        resource_name=discovered_asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_discovered_asset_list(cmd, namespace_name: str, resource_group_name: str):
    provider = DiscoveredAssetProvider(cmd)
    return provider.list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_discovered_asset_update(
    cmd,
    discovered_asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    properties: Any = None,
    tags: Optional[Dict[str, str]] = None,
    no_wait: bool = False,
):
    provider = DiscoveredAssetProvider(cmd)
    return provider.update(
        resource_name=discovered_asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        properties=properties,
        tags=tags,
        no_wait=no_wait,
    )


def adr_discovered_asset_delete(
    cmd,
    discovered_asset_name: str,
    namespace_name: str,
    resource_group_name: str,
    no_wait: bool = False,
):
    provider = DiscoveredAssetProvider(cmd)
    return provider.delete(
        resource_name=discovered_asset_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )
