# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import re
from datetime import datetime, timezone
from typing import Iterator, Optional

from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.core.rest import HttpRequest

from azext_iot.adr.common import validate_iso8601_datetime
from azext_iot.adr.providers.base import ADRProvider

_JOB_RUN_STATUSES = {
    "Scheduled",
    "Queued",
    "Active",
    "Succeeded",
    "Failed",
    "TimedOut",
    "Canceled",
}
_RESULT_STATUSES = {
    "Succeeded",
    "Failed",
    "InProgress",
    "Canceled",
    "NotApplied",
}
_STATUS_CLAUSE = re.compile(r"status eq '([^']+)'")
_ORDER_BY_CLAUSE = re.compile(r"(?P<field>[A-Za-z][A-Za-z0-9_.]*)(?:\s+(?P<dir>asc|desc))?")
_ORDER_BY_FIELDS = {"status"}


def generate_job_run_name() -> str:
    """Generate a default job run name.

    ``runName`` is a required path segment, but the common case is "run this job
    now" where the caller does not care about the name. A UTC timestamp keeps
    generated names sortable and collision-free at second resolution.
    """
    return f"run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def _validate_order_by(order_by: Optional[str]):
    """Validate an OData ``orderBy`` expression, e.g. ``status asc``."""
    if not order_by:
        return
    match = _ORDER_BY_CLAUSE.fullmatch(order_by.strip())
    if not match or match.group("field") not in _ORDER_BY_FIELDS:
        values = ", ".join(sorted(_ORDER_BY_FIELDS))
        raise InvalidArgumentValueError(
            "Use an order by expression such as \"status asc\" or \"status desc\". "
            f"Supported fields: {values}."
        )


def _validate_status_filter(
    status_filter: Optional[str],
    allowed_statuses: set,
    allow_multiple: bool,
):
    if not status_filter:
        return
    clauses = status_filter.split(" or ")
    if not allow_multiple and len(clauses) != 1:
        raise InvalidArgumentValueError("Result filtering accepts one status equality clause.")
    for clause in clauses:
        match = _STATUS_CLAUSE.fullmatch(clause.strip())
        if not match or match.group(1) not in allowed_statuses:
            values = ", ".join(sorted(allowed_statuses))
            raise InvalidArgumentValueError(
                "Use status equality clauses such as \"status eq 'Failed'\". "
                f"Supported statuses: {values}."
            )


class JobRunProvider(ADRProvider):
    def create(
        self,
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
        run_name: Optional[str] = None,
        scheduled_time: Optional[str] = None,
        **kwargs,
    ):
        """Create a run for an existing job.

        ``scheduledTime`` is the only writable field on ``JobRunProperties``; every
        other field is service-populated. ``run_name`` is a required path segment,
        so when the caller omits it a UTC-timestamped name is generated and echoed
        back in the response.
        """
        if scheduled_time is not None:
            validate_iso8601_datetime(scheduled_time)
        run_name = run_name or generate_job_run_name()

        resource = {"properties": {}}
        if scheduled_time is not None:
            resource["properties"]["scheduledTime"] = scheduled_time

        poller = self.client.job_runs.begin_create_or_replace(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            run_name=run_name,
            resource=resource,
        )
        return self._wait(
            poller,
            f"Creating run '{run_name}' for job '{job_name}'...",
            **kwargs,
        )

    def delete(
        self,
        job_name: str,
        run_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        poller = self.client.job_runs.begin_delete(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            run_name=run_name,
        )
        return self._wait(
            poller,
            f"Deleting run '{run_name}' for job '{job_name}'...",
            **kwargs,
        )

    def summary(
        self,
        job_name: str,
        run_name: str,
        namespace_name: str,
        resource_group_name: str,
    ):
        return self.client.job_runs.get_summary(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            run_name=run_name,
        )

    def show(
        self,
        job_name: str,
        run_name: str,
        namespace_name: str,
        resource_group_name: str,
    ):
        return self.client.job_runs.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            run_name=run_name,
        )

    def list(
        self,
        namespace_name: str,
        resource_group_name: str,
        job_name: Optional[str] = None,
        status_filter: Optional[str] = None,
    ) -> list:
        _validate_status_filter(status_filter, _JOB_RUN_STATUSES, allow_multiple=True)
        kwargs = {"filter": status_filter} if status_filter else {}
        if job_name:
            result = self.client.job_runs.list_by_job(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                job_name=job_name,
                **kwargs,
            )
        else:
            result = self.client.job_runs.list_by_namespace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                **kwargs,
            )
        return list(result)

    def cancel(
        self,
        job_name: str,
        run_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        poller = self.client.job_runs.begin_cancel(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            run_name=run_name,
        )
        return self._wait(
            poller,
            f"Canceling run '{run_name}' for job '{job_name}'...",
            **kwargs,
        )

    def results(
        self,
        job_name: str,
        run_name: str,
        namespace_name: str,
        resource_group_name: str,
        status_filter: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> Iterator[dict]:
        _validate_status_filter(status_filter, _RESULT_STATUSES, allow_multiple=False)
        _validate_order_by(order_by)
        body = {}
        if status_filter:
            body["filter"] = status_filter
        if order_by:
            body["orderBy"] = order_by
        response = self.client.job_runs.list_results(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            run_name=run_name,
            body=body,
        )
        while response:
            yield from response.get("value") or []
            next_link = response.get("nextLink")
            if not next_link:
                return
            response = self._fetch_next_page(next_link)

    def _fetch_next_page(self, next_link: str) -> dict:
        response = self.client.send_request(HttpRequest("GET", next_link))
        response.raise_for_status()
        return response.json()
