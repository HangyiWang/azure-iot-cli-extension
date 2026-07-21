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
import time

import pytest
from azure.core.exceptions import ResourceNotFoundError

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
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
        finally:
            self.cleanup_namespace(namespace_name, rg)

    def _get_latest_report(self, namespace_name, report_type, group_name=None):
        command = (
            f"iot adr ns report latest --ns {namespace_name} -g {TEST_RG} "
            f"--report-type {report_type}"
        )
        if group_name:
            command += f" --group-name {group_name}"

        last_error = None
        for attempt in range(_REPORT_POLL_ATTEMPTS):
            try:
                return self.cmd(command).get_output_in_json()
            except (AssertionError, ResourceNotFoundError) as error:
                message = str(error).lower().replace(" ", "")
                if not any(
                    token in message
                    for token in ("404", "notfound", "reportnotready", "inprogress")
                ):
                    raise
                last_error = error
                if attempt < _REPORT_POLL_ATTEMPTS - 1:
                    time.sleep(_REPORT_POLL_INTERVAL_SECONDS)

        pytest.fail(
            f"Report {report_type} was not published within the polling window: "
            f"{last_error}"
        )
