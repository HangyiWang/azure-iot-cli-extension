# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Integration tests for ``iot adr ns job {create|show|list|delete}``.

Lightweight: namespace + one target group; no Hub / DPS / UAMI required.
"""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)
from azext_iot.tests.generators import generate_generic_id


def _gen_group_name() -> str:
    return f"testgrp{generate_generic_id()[:8]}"


def _gen_job_name() -> str:
    return f"testjob{generate_generic_id()[:8]}"


_TEST_QUERY = "true"


@pytest.mark.usefixtures("set_cwd")
class TestADRJobCrudLifecycle(CaptureOutputLiveScenarioTest):
    """Lifecycle: create namespace + target group -> CRUD jobs -> cleanup.

    Job creation requires a group resource ID as the target, so this test
    provisions a group first.
    """

    def test_job_crud_lifecycle(self):
        _log(LogKind.TEST, "test_job_crud_lifecycle")
        rg = TEST_RG
        ns = generate_adr_namespace_name()
        group = _gen_group_name()
        job = _gen_job_name()

        update_provider = "Contoso"
        update_name = "Firmware"
        update_version = "1.2.3"

        try:
            with timed_step("Step 1 ❯ Create namespace + target group"):
                self.cmd(f"iot adr ns create -n {ns} -g {rg} --location {TEST_LOCATION}")
                group_obj = self.cmd(
                    f"iot adr ns group create -n {group} --ns {ns} -g {rg} "
                    f'--query-string "{_TEST_QUERY}"'
                ).get_output_in_json()
                group_id = group_obj["id"]
                _log(LogKind.RESULT, "group id=%s", group_id)

            with timed_step("Step 2 ❯ Create job"):
                create_cmd = (
                    f"iot adr ns job create -n {job} --ns {ns} -g {rg} "
                    f"--tgid {group_id} "
                    f"--up {update_provider} --un {update_name} --uv {update_version} "
                    f"--tags env=test"
                )
                _log(LogKind.CMD, "az %s", create_cmd)
                job_obj = self.cmd(create_cmd).get_output_in_json()
                assert job_obj["name"] == job
                assert job_obj["properties"]["jobType"] == "Update"
                assert job_obj["properties"]["target"]["targetResourceId"] == group_id
                update_id = job_obj["properties"]["definition"]["update"]["updateId"]
                assert update_id["provider"] == update_provider
                assert update_id["name"] == update_name
                assert update_id["version"] == update_version
                assert job_obj["properties"]["provisioningState"] == "Succeeded"
                assert job_obj.get("tags", {}).get("env") == "test"
                _log(LogKind.OK, "job created with correct target + update id")

            with timed_step("Step 3 ❯ Show + list"):
                show_cmd = f"iot adr ns job show -n {job} --ns {ns} -g {rg}"
                shown = self.cmd(show_cmd).get_output_in_json()
                assert shown["name"] == job
                assert shown["properties"]["target"]["targetResourceId"] == group_id

                list_cmd = f"iot adr ns job list --ns {ns} -g {rg}"
                jobs = self.cmd(list_cmd).get_output_in_json()
                assert isinstance(jobs, list)
                assert job in {j["name"] for j in jobs}
                _log(LogKind.OK, "show + list roundtrip ok (%d jobs)", len(jobs))

            with timed_step("Step 4 ❯ Delete job, verify gone"):
                self.cmd(f"iot adr ns job delete -n {job} --ns {ns} -g {rg} -y")
                self.cmd(show_cmd, expect_failure=True)
                jobs_after = self.cmd(list_cmd).get_output_in_json()
                assert job not in {j["name"] for j in jobs_after}
                _log(LogKind.OK, "job deleted")

        finally:
            with timed_step("Cleanup ❯ Delete Namespace (also deletes child group)"):
                try:
                    self.cmd(f"iot adr ns delete -n {ns} -g {rg} -y")
                except Exception as e:
                    _log(LogKind.WARN, "namespace cleanup failed: %s", e)
