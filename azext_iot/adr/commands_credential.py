# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from knack.log import get_logger

from azext_iot.adr.providers.credential import CredentialProvider

logger = get_logger(__name__)


def adr_credential_create(
    cmd,
    namespace_name: str,
    resource_group_name: str,
    tags: Optional[Dict[str, str]] = None,
    no_wait: bool = False,
):
    provider = CredentialProvider(cmd)
    return provider.create(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        tags=tags,
        no_wait=no_wait,
    )


def adr_credential_show(cmd, namespace_name: str, resource_group_name: str):
    provider = CredentialProvider(cmd)
    return provider.show(namespace_name=namespace_name, resource_group_name=resource_group_name)


def adr_credential_list(cmd, namespace_name: str, resource_group_name: str):
    provider = CredentialProvider(cmd)
    return provider.list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_credential_update(
    cmd,
    namespace_name: str,
    resource_group_name: str,
    tags: Optional[Dict[str, str]] = None,
    no_wait: bool = False,
):
    provider = CredentialProvider(cmd)
    return provider.update(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        tags=tags,
        no_wait=no_wait,
    )


def adr_credential_delete(
    cmd, namespace_name: str, resource_group_name: str, no_wait: bool = False
):
    provider = CredentialProvider(cmd)
    return provider.delete(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )


def adr_credential_synchronize(
    cmd, namespace_name: str, resource_group_name: str, no_wait: bool = False
):
    provider = CredentialProvider(cmd)
    return provider.synchronize(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )
