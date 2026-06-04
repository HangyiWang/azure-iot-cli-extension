# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azext_iot.adr.providers.job_run import JobRunProvider


def adr_job_run_show(
    cmd,
    job_name: str,
    run_name: str,
    namespace_name: str,
    resource_group_name: str,
):
    provider = JobRunProvider(cmd)
    return provider.show(
        job_name=job_name,
        run_name=run_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_job_run_list(
    cmd,
    job_name: str,
    namespace_name: str,
    resource_group_name: str,
):
    provider = JobRunProvider(cmd)
    return provider.list(
        job_name=job_name,
        namespace_name=namespace_name,
        resource_group_name=resource_group_name,
    )


def adr_job_run_results(
    cmd,
    job_name: str,
    run_name: str,
    namespace_name: str,
    resource_group_name: str,
):
    provider = JobRunProvider(cmd)
    # CLI command framework can consume a generator; force-list for
    # deterministic output ordering and to ensure errors surface here rather
    # than mid-render.
    return list(
        provider.results(
            job_name=job_name,
            run_name=run_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
        )
    )
