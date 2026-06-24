# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

# Dormant provider: the job/group/job-run operations were dropped from the regenerated
# 2026-11-01-preview SDK but the code is retained for a future re-introduction. The SDK
# client no longer exposes the `job_runs` member, so suppress the resulting false positive.
# pylint: disable=no-member

from typing import Iterator

from azure.core.rest import HttpRequest
from knack.log import get_logger

from azext_iot.adr.providers.base import ADRProvider

logger = get_logger(__name__)


class JobRunProvider(ADRProvider):
    """Read-only surface over ``JobRunsOperations``.

    Job runs are spawned by the service when a job is scheduled; the CLI only
    exposes ``show``/``list``/``results`` because the spec does not provide a
    write surface (no ``cancel``, no ``delete``). See design \u00a73.1 jobs table.
    """

    def __init__(self, cmd):
        super(JobRunProvider, self).__init__(cmd)

    # ---------------------------------------------------------------- show / list
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
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> list:
        """List runs for a job (auto-paged by the SDK)."""
        return list(
            self.client.job_runs.list_by_job(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                job_name=job_name,
            )
        )

    # ---------------------------------------------------------------- results
    def results(
        self,
        job_name: str,
        run_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> Iterator[dict]:
        """Yield every per-device result item across all ``nextLink`` pages.

        The SDK's ``job_runs.results`` is **not** auto-paged \u2014 it returns the
        raw ``{value: [...], nextLink: str|None}`` envelope from a single
        ``POST .../results`` call. We unwrap the envelope here and follow
        ``nextLink`` via the client's :meth:`send_request` until the page chain
        terminates, so callers receive a flat iterator suitable for ``--query``
        and Azure CLI table rendering.

        Implemented as a generator so the CLI can stream large result sets
        without buffering everything in memory.
        """
        response = self.client.job_runs.results(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            job_name=job_name,
            run_name=run_name,
        )
        while response:
            for item in response.get("value") or []:
                yield item
            next_link = response.get("nextLink")
            if not next_link:
                return
            response = self._fetch_next_page(next_link)

    def _fetch_next_page(self, next_link: str) -> dict:
        """Follow a ``nextLink`` URL via the SDK client's raw send-request channel.

        Uses :meth:`MicrosoftDeviceRegistryManagementService.send_request` so
        the call inherits the configured pipeline (auth, retry, telemetry,
        ``api-version`` policy) instead of bypassing it with a raw HTTP call.
        """
        request = HttpRequest("GET", next_link)
        http_response = self.client.send_request(request)
        http_response.raise_for_status()
        return http_response.json()
