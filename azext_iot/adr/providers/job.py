# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

import isodate
from azure.cli.core.azclierror import (
    ArgumentUsageError,
    InvalidArgumentValueError,
)
from azure.cli.core.commands.client_factory import get_subscription_id
from azext_iot.adr.common import (
    JobSchedulingType,
    JobType,
)
from azext_iot.adr.providers.base import ADRProvider

_TARGET_GROUP_REQUIRED_MSG = (
    "--target-group-name is required for --type SoftwareUpdate. The group must be in the "
    "same namespace and resource group as the job."
)
_TARGET_GROUP_FORBIDDEN_MSG = "--target-group-name cannot be used with --type OnboardingUpdate."
_UPDATE_FIELDS_REQUIRED_MSG = (
    "--update-id-provider, --update-id-name, and --update-id-version are required."
)
_INVALID_JOB_TYPE_MSG = "--type must be SoftwareUpdate or OnboardingUpdate."
_IMMUTABLE_FIELDS_MSG = (
    "Only --tags can be modified after creation. The job's --type, --target-group-name, --update-id-* and "
    "scheduling fields are immutable. To change these, delete and recreate the job."
)
_INVALID_TIMEOUT_MSG = (
    "--timeout must be a valid ISO 8601 duration (e.g. 'PT1H', 'P1D', 'PT30M'). Provided value: '{value}'."
)
_INVALID_SCHEDULED_TIME_MSG = (
    "--scheduled-time must be a valid ISO 8601 UTC datetime (e.g. '2025-12-01T08:00:00Z'). Provided value: '{value}'."
)
_NOTHING_TO_UPDATE_MSG = (
    "Nothing to update. Pass --tags k=v [k2=v2 ...] to set tags or --tags \"\" to clear all tags."
)
_JOB_TYPES = {item.value for item in JobType}


def _compose_group_arm_id(
    subscription_id: str, resource_group_name: str, namespace_name: str, group_name: str
) -> str:
    """Compose the ARM resource ID for a namespace group.

    Uses the ``Microsoft.DeviceRegistry/namespaces/groups`` resource type.
    """
    return (
        f"/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group_name}"
        f"/providers/Microsoft.DeviceRegistry"
        f"/namespaces/{namespace_name}"
        f"/groups/{group_name}"
    )


class JobProvider(ADRProvider):
    def __init__(self, cmd):
        super(JobProvider, self).__init__(cmd)

    def create(
        self,
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
        update_provider: Optional[str] = None,
        update_name: Optional[str] = None,
        update_version: Optional[str] = None,
        target_group_name: Optional[str] = None,
        job_type: str = JobType.software_update.value,
        description: Optional[str] = None,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """Create a software-update or onboarding-update job."""
        if job_type not in _JOB_TYPES:
            raise ArgumentUsageError(_INVALID_JOB_TYPE_MSG)
        if job_type == JobType.software_update.value and not target_group_name:
            raise ArgumentUsageError(_TARGET_GROUP_REQUIRED_MSG)
        if job_type == JobType.onboarding_update.value and target_group_name:
            raise ArgumentUsageError(_TARGET_GROUP_FORBIDDEN_MSG)

        if not (update_provider and update_name and update_version):
            raise ArgumentUsageError(_UPDATE_FIELDS_REQUIRED_MSG)

        location = self._resolve_location(namespace_name, resource_group_name, location)

        job_properties = {
            "jobType": job_type,
            "definition": {
                "schedulingType": JobSchedulingType.continuous.value,
                "update": {
                    "updateId": {
                        "provider": update_provider,
                        "name": update_name,
                        "version": update_version,
                    }
                },
            },
        }
        if description is not None:
            job_properties["description"] = description
        if job_type == JobType.software_update.value:
            target_resource_id = _compose_group_arm_id(
                subscription_id=get_subscription_id(self.cmd.cli_ctx),
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                group_name=target_group_name,
            )
            job_properties["target"] = {"resourceId": target_resource_id}

        resource = {
            "location": location,
            "properties": job_properties,
        }
        if tags is not None:
            resource["tags"] = tags

        poller = self.client.jobs.begin_create_or_replace(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            resource=resource,
        )
        return self._wait(
            poller, f"Creating job '{job_name}' in namespace {namespace_name}...", **kwargs
        )

    def update(
        self,
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """Update (tags-only) a job in the namespace.

        Job updates are synchronous and tags-only. Job properties
        (``jobType``, ``target``, ``definition``) are immutable after creation
        because mutating them would have unintended effects on already-scheduled
        runs. Non-tag kwargs are rejected here so the CLI surfaces a clear
        immutable-properties error instead of silently no-oping.
        """
        # Reject any non-tag mutation up front - the entrypoint signature only
        # exposes tags but kwargs may carry stale fields if upstream layers
        # forward extras (defensive: future-proof against parameter additions).
        disallowed = {k: v for k, v in kwargs.items() if v is not None and k != "no_wait"}
        if disallowed:
            raise ArgumentUsageError(_IMMUTABLE_FIELDS_MSG)

        # `tags is None` means the user did not pass --tags at all. We refuse
        # to silently round-trip an empty tags PATCH (which would clear all
        # existing tags) and require the explicit `--tags ""` form to clear.
        if tags is None:
            raise ArgumentUsageError(_NOTHING_TO_UPDATE_MSG)

        # The PATCH body is tags-only. An empty dict means an explicit clear.
        properties = {"tags": tags}

        return self.client.jobs.update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            properties=properties,
        )

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

    def delete(
        self,
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        poller = self.client.jobs.begin_delete(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
        )
        return self._wait(
            poller, f"Deleting job '{job_name}' from namespace {namespace_name}...", **kwargs
        )

    def schedule(
        self,
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
        scheduled_time: Optional[str] = None,
        timeout: Optional[str] = None,
        **kwargs,
    ):
        """Schedule a job for execution (LRO).

        Both body fields are optional. ``--timeout`` is validated as an ISO 8601
        duration via :func:`isodate.parse_duration` so malformed input fails
        fast rather than reaching the backend.
        """
        if timeout is not None:
            self._validate_iso8601_duration(timeout)
        if scheduled_time is not None:
            self._validate_iso8601_datetime(scheduled_time)

        body = {}
        if scheduled_time is not None:
            body["scheduledTime"] = scheduled_time
        if timeout is not None:
            body["timeout"] = timeout

        poller = self.client.jobs.begin_schedule(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            body=body,
        )
        return self._wait(
            poller, f"Scheduling job '{job_name}' in namespace {namespace_name}...", **kwargs
        )

    @staticmethod
    def _validate_iso8601_duration(value: str) -> None:
        """Validate that *value* is an ISO 8601 duration string.

        Defers to :mod:`isodate` (SDK transitive dep). Raises
        :class:`InvalidArgumentValueError` on any parse error.
        """
        try:
            isodate.parse_duration(value)
        except Exception:  # noqa: BLE001 - any parse error is invalid input
            raise InvalidArgumentValueError(_INVALID_TIMEOUT_MSG.format(value=value))

    @staticmethod
    def _validate_iso8601_datetime(value: str) -> None:
        """Validate that *value* is an ISO 8601 datetime string.

        The service requires an absolute time, so a timezone offset is
        mandatory.
        """
        try:
            parsed = isodate.parse_datetime(value)
            if parsed.utcoffset() is None:
                raise ValueError("timezone offset is required")
        except Exception:  # noqa: BLE001 - any parse error is invalid input
            raise InvalidArgumentValueError(_INVALID_SCHEDULED_TIME_MSG.format(value=value))
