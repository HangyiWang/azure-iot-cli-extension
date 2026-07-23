# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import wait_for_resource_succeeded
from azext_iot.tests.adr._log import LogKind, _log
from azext_iot.tests.adr.conftest import TEST_LOCATION, TEST_RG
from azext_iot.tests.generators import generate_generic_id


def _update_instance_name() -> str:
    return f"testdu{generate_generic_id()[:8]}"


@pytest.mark.usefixtures("set_cwd")
class TestADRDUInstanceLifecycle(CaptureOutputLiveScenarioTest):
    def test_adr_du_instance_lifecycle(self):
        instance_name = _update_instance_name()
        show_command = f"iot adr ns du instance show -n {instance_name} -g {TEST_RG}"
        delete_command = (
            f"iot adr ns du instance delete -n {instance_name} " f"-g {TEST_RG} --yes"
        )
        instance_created = False

        try:
            availability = self.cmd(
                f"iot adr ns du instance check-name -n {instance_name}"
            ).get_output_in_json()
            assert availability["nameAvailable"] is True

            self.cmd(
                f"iot adr ns du instance create -n {instance_name} "
                f"-g {TEST_RG} --location {TEST_LOCATION} "
                "--mi-system-assigned --tags env=integration --no-wait"
            )
            instance_created = True
            created = wait_for_resource_succeeded(self, show_command)
            assert created["name"] == instance_name
            assert "SystemAssigned" in created["identity"]["type"]

            self.cmd(
                f"iot adr ns du instance wait -n {instance_name} -g {TEST_RG} "
                "--custom \"properties.provisioningState=='Succeeded'\""
            )

            listed_by_group = self.cmd(
                f"iot adr ns du instance list -g {TEST_RG}"
            ).get_output_in_json()
            assert instance_name in {instance["name"] for instance in listed_by_group}

            listed_by_subscription = self.cmd(
                "iot adr ns du instance list"
            ).get_output_in_json()
            assert instance_name in {
                instance["name"] for instance in listed_by_subscription
            }

            updated = self.cmd(
                f"iot adr ns du instance update -n {instance_name} "
                f"-g {TEST_RG} --tags env=updated"
            ).get_output_in_json()
            assert updated["tags"]["env"] == "updated"

            self.cmd(
                f"iot adr ns du instance update -n {instance_name} " f"-g {TEST_RG}",
                expect_failure=True,
            )

            self.cmd(f"{delete_command} --no-wait")
            self.cmd(
                f"iot adr ns du instance wait -n {instance_name} "
                f"-g {TEST_RG} --deleted"
            )
            instance_created = False
            self.cmd(show_command, expect_failure=True)
        finally:
            if instance_created:
                try:
                    self.cmd(delete_command)
                except Exception as error:  # noqa: BLE001 - cleanup is best-effort
                    _log(
                        LogKind.WARN,
                        "UpdateInstance cleanup failed: %s",
                        error,
                    )


@pytest.mark.usefixtures("set_cwd")
class TestADRDUValidationNegatives(CaptureOutputLiveScenarioTest):
    def test_adr_du_validation_negatives(self):
        self.cmd(
            "iot adr ns du instance update -n missing-instance " f"-g {TEST_RG}",
            expect_failure=True,
        )
        self.cmd(
            "iot adr ns du instance update -n missing-instance "
            f"-g {TEST_RG} --mi-user-assigned not-an-arm-id",
            expect_failure=True,
        )
