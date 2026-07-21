# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)
from azext_iot.tests.generators import generate_generic_id


@pytest.mark.usefixtures("set_cwd")
class TestADRServiceNegatives(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    def test_report_and_migrate_service_negatives(self):
        namespace_name = generate_adr_namespace_name()
        rg = TEST_RG

        try:
            namespace = self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION}"
            ).get_output_in_json()

            report_failure = self.cmd(
                f"iot adr ns report latest --ns {namespace_name} -g {rg} "
                "--report-type NamespaceUpdateComplianceReport",
                expect_failure=True,
            )
            assert report_failure.exit_code == 3, (
                "Report latest must reach ARM and return a service error, not fail "
                "during client-side command processing."
            )
            process_error = getattr(report_failure, "process_error", None)
            if process_error is not None and hasattr(process_error, "status_code"):
                assert process_error.status_code == 404

            subscription_id = namespace["id"].split("/")[2]
            missing_asset_id = (
                f"/subscriptions/{subscription_id}/resourceGroups/{rg}/providers/"
                "Microsoft.DeviceRegistry/assets/"
                f"missing-{generate_generic_id()[:8]}"
            )
            result = self.cmd(
                f"iot adr ns migrate -n {namespace_name} -g {rg} "
                f"--scope Resources --resource-ids {missing_asset_id}"
            ).get_output_in_json()

            migrate_results = result.get("migrateResults") or []
            assert len(migrate_results) == 1, result
            assert migrate_results[0]["resourceId"].lower() == missing_asset_id.lower()
            assert migrate_results[0]["result"] == "Failed"
            assert (migrate_results[0].get("error") or {}).get("code")
        finally:
            self.cleanup_namespace(namespace_name, rg)
