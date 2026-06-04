# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR job run integration tests (P7).

Covers the **read-only** ``iot adr ns job run`` surface:

* ``run list``    — paginated list of runs for a job
* ``run show``    — single run by name
* ``run results`` — per-device target results, paginated manually via nextLink

Job runs are produced by the backend after a job is *scheduled* and the
scheduling window opens. Without a real device-update target deployed to a
real device population, the backend will typically not spawn any runs for a
test job. So the integration coverage here is intentionally minimal:

* Verify ``run list`` returns an **empty list** (not an error) for a
  freshly-scheduled job with no matching devices.
* Verify ``run show`` on a non-existent run returns a clean error.
* Verify ``run results`` on a non-existent run returns a clean error.

The full results-pagination behavior (single page, nextLink follow-through,
HTTP error propagation, lazy generator) is covered exhaustively by
:mod:`azext_iot.tests.adr.test_adr_job_run_unit`.
"""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)
from azext_iot.tests.generators import generate_generic_id


def _generate_group_name() -> str:
    return f"testgrp{generate_generic_id()[:8]}"


def _generate_job_name() -> str:
    return f"testjob{generate_generic_id()[:8]}"


@pytest.mark.usefixtures("set_cwd")
class TestADRJobRunReadOnly(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Read-only smoke for ``iot adr ns job run`` surface."""

    def test_adr_job_run_surface_smoke(self):
        _log(LogKind.TEST, "test_adr_job_run_surface_smoke")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        group_name = _generate_group_name()
        job_name = _generate_job_name()

        try:
            with timed_step("Setup ❯ Namespace + Group + Job"):
                self.cmd(
                    f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION}"
                )
                self.cmd(
                    f"iot adr ns group create -n {group_name} --ns {namespace_name} -g {rg} "
                    f"--query-string \"SELECT * FROM devices\""
                )
                self.cmd(
                    f"iot adr ns job create -n {job_name} --ns {namespace_name} -g {rg} "
                    f"--target-group-name {group_name} "
                    f"--update-id-provider Contoso --update-id-name fw --update-id-version 1.0.0"
                )

            with timed_step("Step 1 ❯ Schedule the job (immediate)"):
                # Immediate schedule (no --scheduled-time) opens the window
                # right away. With zero devices in the group, backend will
                # typically produce zero runs.
                self.cmd(
                    f"iot adr ns job schedule -n {job_name} --ns {namespace_name} -g {rg}"
                )

            with timed_step("Step 2 ❯ job run list returns a list (likely empty)"):
                runs = self.cmd(
                    f"iot adr ns job run list --ns {namespace_name} -g {rg} --jn {job_name}"
                ).get_output_in_json()
                assert isinstance(runs, list), (
                    f"job run list should return list, got {type(runs)}"
                )
                _log(LogKind.RESULT, "runs returned=%d", len(runs))

                # If the backend did produce a run, exercise show + results
                # against the first one to confirm the surface end-to-end.
                if runs:
                    first = runs[0]
                    run_name = first.get("name")
                    _log(LogKind.RESULT, "first run name=%s", run_name)

                    shown = self.cmd(
                        f"iot adr ns job run show --ns {namespace_name} -g {rg} "
                        f"--jn {job_name} -n {run_name}"
                    ).get_output_in_json()
                    assert shown.get("name") == run_name
                    _log(LogKind.OK, "run show returned matching name")

                    # results is a generator surfaced as a list; for an empty
                    # device group it will be [], but the surface itself must
                    # succeed.
                    results = self.cmd(
                        f"iot adr ns job run results --ns {namespace_name} -g {rg} "
                        f"--jn {job_name} --rn {run_name}"
                    ).get_output_in_json()
                    assert isinstance(results, list), (
                        f"job run results should return list, got {type(results)}"
                    )
                    _log(LogKind.OK, "run results returned (count=%d)", len(results))

            with timed_step("Neg ❯ run show on non-existent run fails cleanly"):
                self.cmd(
                    f"iot adr ns job run show --ns {namespace_name} -g {rg} "
                    f"--jn {job_name} -n does-not-exist-{generate_generic_id()[:8]}",
                    expect_failure=True,
                )
                _log(LogKind.OK, "show non-existent run rejected")

            with timed_step("Neg ❯ run results on non-existent run fails cleanly"):
                self.cmd(
                    f"iot adr ns job run results --ns {namespace_name} -g {rg} "
                    f"--jn {job_name} --rn does-not-exist-{generate_generic_id()[:8]}",
                    expect_failure=True,
                )
                _log(LogKind.OK, "results for non-existent run rejected")

            with timed_step("Neg ❯ run list on non-existent job fails cleanly"):
                self.cmd(
                    f"iot adr ns job run list --ns {namespace_name} -g {rg} "
                    f"--jn does-not-exist-{generate_generic_id()[:8]}",
                    expect_failure=True,
                )
                _log(LogKind.OK, "list under non-existent job rejected")

        finally:
            self.cleanup_namespace(namespace_name, rg)
