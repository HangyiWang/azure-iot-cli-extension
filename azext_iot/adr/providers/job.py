# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from knack.log import get_logger
from rich.console import Console

from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state

console = Console()
logger = get_logger(__name__)


# Device Registry job provider. Jobs target groups and apply an action (today,
# only "Update" jobs are supported by the service).
class JobProvider(ADRProvider):
    def __init__(self, cmd):
        super(JobProvider, self).__init__(cmd)

    def show(self, job_name: str, namespace_name: str, resource_group_name: str):
        return self.client.jobs.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
        )

    def list(self, namespace_name: str, resource_group_name: str):
        return list(
            self.client.jobs.list_by_namespace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
        )

    def create(
        self,
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
        target_group_id: str,
        update_provider: str,
        update_name: str,
        update_version: str,
        scheduling_type: str = "continuous",
        job_type: str = "Update",
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """Create or replace an Update job targeting the given group."""
        location = location or self._ensure_location(
            self.cmd.cli_ctx, resource_group_name=resource_group_name
        )

        # Job body mirrors the Microsoft.DeviceRegistry Job schema. For PoC we
        # only support the "Update" discriminator.
        inner_props = {
            "jobType": job_type,
            "target": {"targetResourceId": target_group_id},
            "definition": {
                "schedulingType": scheduling_type,
                "update": {
                    "updateId": {
                        "provider": update_provider,
                        "name": update_name,
                        "version": update_version,
                    }
                },
            },
        }

        resource = {
            "location": location,
            "properties": inner_props,
        }
        if tags is not None:
            resource["tags"] = tags

        with console.status(
            f"Creating job '{job_name}' in namespace {namespace_name}..."
        ):
            poller = self.client.jobs.begin_create_or_replace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                job_name=job_name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def delete(
        self,
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        """Delete a job from the namespace."""
        with console.status(
            f"Deleting job '{job_name}' from namespace {namespace_name}..."
        ):
            poller = self.client.jobs.begin_delete(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                job_name=job_name,
            )
            return wait_for_terminal_state(poller, **kwargs)
