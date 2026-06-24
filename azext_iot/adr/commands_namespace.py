# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from knack.log import get_logger

from azext_iot.adr.providers.namespace import NamespaceProvider

logger = get_logger(__name__)


def adr_namespace_create(
    cmd,
    namespace_name: str,
    resource_group_name: str,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    enable_certificate_management: Optional[bool] = None,
    policy_name: Optional[str] = None,
    certificate_key_type: Optional[str] = None,
    certificate_subject: Optional[str] = None,
    certificate_validity_days: Optional[int] = None,
    outbound_mi_system_assigned: Optional[bool] = None,
    outbound_mi_user_assigned: Optional[str] = None,
    no_wait: bool = False,
):
    provider = NamespaceProvider(cmd)
    return provider.create(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        location=location,
        tags=tags,
        enable_certificate_management=enable_certificate_management,
        policy_name=policy_name,
        certificate_key_type=certificate_key_type,
        certificate_subject=certificate_subject,
        certificate_validity_days=certificate_validity_days,
        outbound_mi_system_assigned=outbound_mi_system_assigned,
        outbound_mi_user_assigned=outbound_mi_user_assigned,
        no_wait=no_wait,
    )


def adr_namespace_show(cmd, namespace_name: str, resource_group_name: str):
    provider = NamespaceProvider(cmd)
    return provider.show(namespace_name=namespace_name, resource_group_name=resource_group_name)


def adr_namespace_list(cmd, resource_group_name: Optional[str] = None):
    provider = NamespaceProvider(cmd)
    return provider.list(resource_group_name=resource_group_name)


def adr_namespace_delete(cmd, namespace_name: str, resource_group_name: str, no_wait: bool = False):
    provider = NamespaceProvider(cmd)
    return provider.delete(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )


def adr_namespace_update(
    cmd,
    namespace_name: str,
    resource_group_name: str,
    tags: Optional[Dict[str, str]] = None,
    enable_certificate_management: Optional[bool] = None,
    outbound_mi_system_assigned: Optional[bool] = None,
    outbound_mi_user_assigned: Optional[str] = None,
    no_wait: bool = False,
):
    provider = NamespaceProvider(cmd)
    return provider.update(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        tags=tags,
        enable_certificate_management=enable_certificate_management,
        outbound_mi_system_assigned=outbound_mi_system_assigned,
        outbound_mi_user_assigned=outbound_mi_user_assigned,
        no_wait=no_wait,
    )
