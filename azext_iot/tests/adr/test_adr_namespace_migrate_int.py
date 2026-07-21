# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Opt-in ADR namespace migration integration coverage.

Set ``azext_iot_adr_migrate_resource_id`` to the full ARM ID of a
pre-provisioned, migratable source resource to enable this test. The source
resource is retained; only the destination namespace created here is deleted.
"""

import os

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)


_MIGRATE_RESOURCE_ID_ENV = "azext_iot_adr_migrate_resource_id"
_MIGRATE_RESOURCE_ID = os.getenv(_MIGRATE_RESOURCE_ID_ENV, "").strip()


@pytest.mark.skipif(
    not _MIGRATE_RESOURCE_ID,
    reason=(
        "Set azext_iot_adr_migrate_resource_id to a pre-provisioned, "
        "migratable source resource ID."
    ),
)
@pytest.mark.usefixtures("set_cwd")
class TestADRNamespaceMigration(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    def test_adr_namespace_migrate_preprovisioned_resource(self):
        namespace_name = generate_adr_namespace_name()
        rg = TEST_RG

        try:
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION}"
            )
            result = self.cmd(
                f"iot adr ns migrate -n {namespace_name} -g {rg} "
                f"--scope Resources --resource-ids '{_MIGRATE_RESOURCE_ID}'"
            ).get_output_in_json()

            assert isinstance(result, dict), (
                f"Migration should return a result envelope, got {type(result)}"
            )
            migrate_results = result.get("migrateResults")
            assert isinstance(migrate_results, list), (
                f"Migration envelope should contain a migrateResults list: {result}"
            )
            assert migrate_results and all(
                isinstance(item, dict) for item in migrate_results
            ), f"Migration should return at least one structured result: {result}"
        finally:
            self.cleanup_namespace(namespace_name, rg)
