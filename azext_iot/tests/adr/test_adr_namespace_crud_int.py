# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""ADR namespace CRUD integration coverage."""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._log import LogKind, _log
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)


@pytest.mark.usefixtures("set_cwd")
class TestADRNamespaceCrud(CaptureOutputLiveScenarioTest):
    def test_namespace_crud_lifecycle(self):
        namespace_name = generate_adr_namespace_name()
        namespace_created = False

        try:
            created = self.cmd(
                f"iot adr ns create -n {namespace_name} -g {TEST_RG} "
                f"--location {TEST_LOCATION}"
            ).get_output_in_json()
            namespace_created = True
            assert created["name"] == namespace_name
            assert created["location"] == TEST_LOCATION
            assert created["properties"]["provisioningState"] == "Succeeded"

            shown = self.cmd(
                f"iot adr ns show -n {namespace_name} -g {TEST_RG}"
            ).get_output_in_json()
            assert shown["name"] == namespace_name

            listed = self.cmd(
                f"iot adr ns list -g {TEST_RG}"
            ).get_output_in_json()
            assert namespace_name in [namespace["name"] for namespace in listed]

            updated = self.cmd(
                f"iot adr ns update -n {namespace_name} -g {TEST_RG} "
                "--tags env=test purpose=ci"
            ).get_output_in_json()
            assert updated["tags"] == {"env": "test", "purpose": "ci"}

            replaced = self.cmd(
                f"iot adr ns update -n {namespace_name} -g {TEST_RG} "
                "--tags owner=adr-tests"
            ).get_output_in_json()
            assert replaced["tags"] == {"owner": "adr-tests"}

            self.cmd(
                f"iot adr ns update -n {namespace_name} -g {TEST_RG}",
                expect_failure=True,
            )

            self.cmd(
                f"iot adr ns delete -n {namespace_name} -g {TEST_RG} --yes"
            )
            namespace_created = False
            self.cmd(
                f"iot adr ns show -n {namespace_name} -g {TEST_RG}",
                expect_failure=True,
            )
        finally:
            if namespace_created:
                try:
                    self.cmd(
                        f"iot adr ns delete -n {namespace_name} "
                        f"-g {TEST_RG} --yes"
                    )
                except Exception as error:  # noqa: BLE001
                    _log(LogKind.WARN, "Cleanup failed: %s", error)
