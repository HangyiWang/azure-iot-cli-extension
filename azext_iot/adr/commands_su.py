# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from azext_iot.adr.providers.update_instance import UpdateInstanceProvider


def adr_su_instance_check_name(cmd, update_instance_name: str):
    return UpdateInstanceProvider(cmd).check_name(update_instance_name)


def adr_su_instance_list(cmd, resource_group_name: Optional[str] = None):
    return UpdateInstanceProvider(cmd).list(resource_group_name=resource_group_name)


def adr_su_instance_show(cmd, update_instance_name: str, resource_group_name: str):
    return UpdateInstanceProvider(cmd).show(
        update_instance_name=update_instance_name,
        resource_group_name=resource_group_name,
    )


def adr_su_instance_create(
    cmd,
    update_instance_name: str,
    resource_group_name: str,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    mi_system_assigned: Optional[bool] = None,
    mi_user_assigned: Optional[List[str]] = None,
    no_wait: bool = False,
):
    return UpdateInstanceProvider(cmd).create(
        update_instance_name=update_instance_name,
        resource_group_name=resource_group_name,
        location=location,
        tags=tags,
        mi_system_assigned=mi_system_assigned,
        mi_user_assigned=mi_user_assigned,
        no_wait=no_wait,
    )


def adr_su_instance_update(
    cmd,
    update_instance_name: str,
    resource_group_name: str,
    tags: Optional[Dict[str, str]] = None,
    mi_system_assigned: Optional[bool] = None,
    mi_user_assigned: Optional[List[str]] = None,
    no_wait: bool = False,
):
    return UpdateInstanceProvider(cmd).update(
        update_instance_name=update_instance_name,
        resource_group_name=resource_group_name,
        tags=tags,
        mi_system_assigned=mi_system_assigned,
        mi_user_assigned=mi_user_assigned,
        no_wait=no_wait,
    )


def adr_su_instance_delete(
    cmd,
    update_instance_name: str,
    resource_group_name: str,
    no_wait: bool = False,
):
    return UpdateInstanceProvider(cmd).delete(
        update_instance_name=update_instance_name,
        resource_group_name=resource_group_name,
        no_wait=no_wait,
    )
