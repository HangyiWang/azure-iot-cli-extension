# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from knack.log import get_logger

from azext_iot.adr.providers.policy import PolicyProvider

logger = get_logger(__name__)


def adr_policy_create(
    cmd,
    policy_name: str,
    namespace_name: str,
    resource_group_name: str,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    certificate_key_type: Optional[str] = None,
    certificate_validity_days: Optional[int] = None,
    enable_byor: Optional[bool] = None,
    no_wait: bool = False,
):
    provider = PolicyProvider(cmd)
    return provider.create(
        policy_name=policy_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        location=location,
        tags=tags,
        certificate_key_type=certificate_key_type,
        certificate_validity_days=certificate_validity_days,
        enable_byor=enable_byor,
        no_wait=no_wait,
    )


def adr_policy_show(cmd, policy_name: str, namespace_name: str, resource_group_name: str):
    provider = PolicyProvider(cmd)
    return provider.show(
        policy_name=policy_name, namespace_name=namespace_name, resource_group_name=resource_group_name
    )


def adr_policy_list(cmd, namespace_name: str, resource_group_name: str):
    provider = PolicyProvider(cmd)
    return provider.list(namespace_name=namespace_name, resource_group_name=resource_group_name)


def adr_policy_delete(
    cmd, policy_name: str, namespace_name: str, resource_group_name: str, no_wait: bool = False
):
    provider = PolicyProvider(cmd)
    return provider.delete(
        policy_name=policy_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )


def adr_policy_update(
    cmd,
    policy_name: str,
    namespace_name: str,
    resource_group_name: str,
    tags: Optional[Dict[str, str]] = None,
    certificate_validity_days: Optional[int] = None,
    no_wait: bool = False,
):
    provider = PolicyProvider(cmd)
    return provider.update(
        policy_name=policy_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        tags=tags,
        certificate_validity_days=certificate_validity_days,
        no_wait=no_wait,
    )


def adr_policy_revoke_issuer(
    cmd,
    policy_name: str,
    namespace_name: str,
    resource_group_name: str,
    no_wait: bool = False,
):
    provider = PolicyProvider(cmd)
    return provider.revoke_issuer(
        policy_name=policy_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )


def adr_policy_activate_byor(
    cmd,
    policy_name: str,
    namespace_name: str,
    resource_group_name: str,
    certificate_chain_file: str,
    no_wait: bool = False,
):
    from azext_iot.common.utility import read_file_content

    certificate_chain = read_file_content(certificate_chain_file)
    provider = PolicyProvider(cmd)
    return provider.activate_byor(
        policy_name=policy_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        certificate_chain=certificate_chain,
        no_wait=no_wait,
    )
