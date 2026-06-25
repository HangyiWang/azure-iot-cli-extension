# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# The SDK client does not currently expose the `jobs` or `job_runs` members, so
# suppress the resulting no-member false positives.
# pylint: disable=no-member

from typing import Dict, List, Optional

import isodate
from azure.cli.core.azclierror import (
    ArgumentUsageError,
    InvalidArgumentValueError,
)
from azure.cli.core.commands.client_factory import get_subscription_id
from knack.log import get_logger

from azext_iot.adr.common import (
    JOB_RUN_IN_FLIGHT_STATUSES,
    JobSchedulingType,
    JobType,
)
from azext_iot.adr.providers.base import ADRProvider

logger = get_logger(__name__)


# Error templates
_ONLY_UPDATE_SUPPORTED_MSG = (
    "Only --type Update is supported in this preview release. "
    "'Action' and 'State' are not currently supported."
)
_TARGET_GROUP_REQUIRED_MSG = (
    "--target-group-name is required. The target group must live in the same namespace and resource "
    "group as the job (cross-namespace targets are not supported in this preview release)."
)
_UPDATE_FIELDS_REQUIRED_MSG = (
    "--update-id-provider, --update-id-name, and --update-id-version are required for --type Update."
)
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
        job_type: str = JobType.update.value,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """Create a job in the namespace.

        Only ``jobType: Update`` is currently supported. The CLI rejects
        ``Action``/``State`` client-side with a clear message even though help
        names them for forward-compat.

        The target group is always resolved against the job's own namespace and
        resource group (cross-namespace targets are not supported in this
        preview release).
        """
        # Reject non-Update types client-side (forward-compat enum surface).
        if job_type != JobType.update.value:
            raise ArgumentUsageError(_ONLY_UPDATE_SUPPORTED_MSG)

        if not target_group_name:
            raise ArgumentUsageError(_TARGET_GROUP_REQUIRED_MSG)

        target_resource_id = _compose_group_arm_id(
            subscription_id=get_subscription_id(self.cmd.cli_ctx),
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=target_group_name,
        )

        # Update-job requires the ADU update identity triple (passed opaquely;
        # no ADU preflight).
        if not (update_provider and update_name and update_version):
            raise ArgumentUsageError(_UPDATE_FIELDS_REQUIRED_MSG)

        if not location:
            location = self._ensure_location(self.cmd.cli_ctx, resource_group_name, location)

        resource = {
            "location": location,
            "properties": {
                "jobType": JobType.update.value,
                "target": {"targetResourceId": target_resource_id},
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
            },
        }
        if tags:
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
        """Delete a job from the namespace.

        Surface a best-effort warning if any in-flight runs (status in
        ``Scheduled``/``Queued``/``Active``) belong to this job; deletion
        proceeds regardless (the backend DELETE cancels affected runs with
        ``CanceledByCustomer``).
        """
        in_flight_runs = self._check_in_flight_runs(
            job_name=job_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
        )
        if in_flight_runs:
            logger.warning(
                "%d in-flight run(s) for job '%s' will be cancelled: %s",
                len(in_flight_runs),
                job_name,
                ", ".join(in_flight_runs),
            )

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

    def _check_in_flight_runs(
        self,
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> List[str]:
        """Return identifiers of in-flight job runs for this job.

        Best-effort: any exception (RBAC, transient SDK error) is logged at
        warning level and yields an empty list so that deletion is never
        blocked by a probe-failure.
        """
        try:
            runs = self.client.job_runs.list_by_job(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                job_name=job_name,
            )
            return [
                r.get("name", "<unknown>")
                for r in runs
                if (r.get("properties") or {}).get("status") in JOB_RUN_IN_FLIGHT_STATUSES
            ]
        except Exception as ex:  # noqa: BLE001 - best-effort probe
            logger.warning(
                "Unable to enumerate job runs for '%s' (continuing with delete): %s",
                job_name,
                ex,
            )
            return []

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

        Defers to :mod:`isodate` (SDK transitive dep). Accepts both timezone-
        aware and naive forms - the backend rejects naive values, so we only
        guard against malformed input here. Raises
        :class:`InvalidArgumentValueError` on any parse error.
        """
        try:
            isodate.parse_datetime(value)
        except Exception:  # noqa: BLE001 - any parse error is invalid input
            raise InvalidArgumentValueError(_INVALID_SCHEDULED_TIME_MSG.format(value=value))
