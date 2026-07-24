# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR report integration tests.

Set ``azext_iot_adr_reports_enabled=true`` to enable these tests when the report
backend is deployed.
"""

import os

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import (
    ADRHubInfraHelper,
    wait_for_condition,
)
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)
from azext_iot.tests.generators import generate_generic_id


_REPORTS_ENABLED = os.getenv("azext_iot_adr_reports_enabled", "").lower() in {
    "1",
    "true",
}
_REPORT_POLL_ATTEMPTS = 12
_REPORT_POLL_INTERVAL_SECONDS = 10


@pytest.mark.skipif(
    not _REPORTS_ENABLED,
    reason="Set azext_iot_adr_reports_enabled=true when the report backend is deployed.",
)
@pytest.mark.usefixtures("set_cwd")
class TestADRReports(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    def test_adr_namespace_and_group_reports(self):
        namespace_name = generate_adr_namespace_name()
        group_name = f"testgrp{generate_generic_id()[:8]}"
        rg = TEST_RG

        try:
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION}"
            )
            self.cmd(
                f"iot adr ns group create -n {group_name} --ns {namespace_name} -g {rg} "
                '--query-string "SELECT * FROM DEVICE"'
            )

            self.cmd(
                f"iot adr ns report latest --ns {namespace_name} -g {rg} "
                "--report-type NamespaceUpdateComplianceReport",
                expect_failure=True,
            )
            self.cmd(
                f"iot adr ns report generate --ns {namespace_name} -g {rg} "
                "--report-type NamespaceUpdateComplianceReport"
            )
            namespace_report = self._get_latest_report(
                namespace_name, "NamespaceUpdateComplianceReport"
            )
            assert namespace_report["reportType"] == "NamespaceUpdateComplianceReport"

            self.cmd(
                f"iot adr ns report generate --ns {namespace_name} -g {rg} "
                "--report-type GroupBestUpdatesComplianceReport "
                f"--group-name {group_name}"
            )
            group_report = self._get_latest_report(
                namespace_name,
                "GroupBestUpdatesComplianceReport",
                group_name=group_name,
            )
            assert group_report["reportType"] == "GroupBestUpdatesComplianceReport"
            assert group_report["reportTarget"] == group_name

            self.cmd(
                f"iot adr ns report generate --ns {namespace_name} -g {rg} "
                "--report-type GroupInstallableUpdatesReport "
                f"--group-name {group_name}"
            )
            installable_report = self._get_latest_report(
                namespace_name,
                "GroupInstallableUpdatesReport",
                group_name=group_name,
            )
            assert installable_report["reportType"] == (
                "GroupInstallableUpdatesReport"
            )
            assert installable_report["reportTarget"] == group_name

            self.cmd(
                f"iot adr ns report generate --ns {namespace_name} -g {rg} "
                "--report-type NamespaceUpdateComplianceReport "
                f"--group-name {group_name}",
                expect_failure=True,
            )
            self.cmd(
                f"iot adr ns report generate --ns {namespace_name} -g {rg} "
                "--report-type GroupBestUpdatesComplianceReport",
                expect_failure=True,
            )
        finally:
            self.cleanup_namespace(namespace_name, rg)

    def _get_latest_report(self, namespace_name, report_type, group_name=None):
        command = (
            f"iot adr ns report latest --ns {namespace_name} -g {TEST_RG} "
            f"--report-type {report_type}"
        )
        if group_name:
            command += f" --group-name {group_name}"

        def report_not_ready(error):
            message = str(error).lower().replace(" ", "")
            return any(
                token in message
                for token in (
                    "404",
                    "notfound",
                    "reportnotready",
                    "inprogress",
                )
            )

        return wait_for_condition(
            lambda: self.cmd(command).get_output_in_json(),
            lambda _: True,
            description=f"{report_type} publication",
            timeout=None,
            interval=_REPORT_POLL_INTERVAL_SECONDS,
            max_attempts=_REPORT_POLL_ATTEMPTS,
            describe=lambda report: (
                f"reportType={(report or {}).get('reportType')!r}"
            ),
            is_retryable_error=report_not_ready,
        )
