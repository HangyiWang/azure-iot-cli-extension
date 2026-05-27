# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azext_iot.adr.providers.job import JobProvider


def adr_job_create(
    cmd,
    job_name: str,
    namespace_name: str,
    resource_group_name: str,
    target_group_id: str,
    update_provider: str,
    update_name: str,
    update_version: str,
    location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
):
    provider = JobProvider(cmd)
    return provider.create(
        job_name=job_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
        target_group_id=target_group_id,
        update_provider=update_provider,
        update_name=update_name,
        update_version=update_version,
        location=location,
        tags=tags,
    )


def adr_job_show(cmd, job_name: str, namespace_name: str, resource_group_name: str):
    provider = JobProvider(cmd)
    return provider.show(
        job_name=job_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_job_list(cmd, namespace_name: str, resource_group_name: str):
    provider = JobProvider(cmd)
    return provider.list(
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_job_delete(cmd, job_name: str, namespace_name: str, resource_group_name: str):
    provider = JobProvider(cmd)
    return provider.delete(
        job_name=job_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )
