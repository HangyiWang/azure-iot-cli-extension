# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import (
    CleanupLedger,
    wait_for_resource_succeeded,
)
from azext_iot.tests.adr.conftest import TEST_LOCATION, TEST_RG
from azext_iot.tests.generators import generate_generic_id

SU_PROVISIONING_MAX_POLLS = 360
SU_PROVISIONING_POLL_INTERVAL = 10


def _update_instance_name() -> str:
    return f"testsu{generate_generic_id()[:8]}"


@pytest.mark.usefixtures("set_cwd")
class TestADRUpdateInstanceLifecycle(CaptureOutputLiveScenarioTest):
    def test_update_instance_lifecycle(self):
        instance_name = _update_instance_name()
        identity_name = f"testsuid{generate_generic_id()[:8]}"
        show_command = f"iot adr ns su instance show -n {instance_name} -g {TEST_RG}"
        delete_command = (
            f"iot adr ns su instance delete -n {instance_name} " f"-g {TEST_RG} --yes"
        )
        with CleanupLedger() as cleanup:
            identity = self.cmd(
                f"identity create -n {identity_name} -g {TEST_RG} "
                f"--location {TEST_LOCATION}"
            ).get_output_in_json()
            identity_id = identity["id"]
            cleanup.register(
                "UpdateInstance UAMI",
                lambda: self.cmd(
                    f"identity delete -n {identity_name} -g {TEST_RG}"
                ),
            )

            availability = self.cmd(
                f"iot adr ns su instance check-name -n {instance_name}"
            ).get_output_in_json()
            assert availability["nameAvailable"] is True

            self.cmd(
                f"iot adr ns su instance create -n {instance_name} "
                f"-g {TEST_RG} --location {TEST_LOCATION} "
                "--mi-system-assigned --tags env=integration --no-wait"
            )
            cleanup.register(
                "UpdateInstance",
                lambda: self.cmd(delete_command),
            )
            created = wait_for_resource_succeeded(
                self,
                show_command,
                max_polls=SU_PROVISIONING_MAX_POLLS,
                poll_interval=SU_PROVISIONING_POLL_INTERVAL,
            )
            assert created["name"] == instance_name
            assert "SystemAssigned" in created["identity"]["type"]

            self.cmd(
                f"iot adr ns su instance wait -n {instance_name} -g {TEST_RG} "
                "--custom \"properties.provisioningState=='Succeeded'\""
            )

            unavailable = self.cmd(
                f"iot adr ns su instance check-name -n {instance_name}"
            ).get_output_in_json()
            assert unavailable["nameAvailable"] is False

            listed_by_group = self.cmd(
                f"iot adr ns su instance list -g {TEST_RG}"
            ).get_output_in_json()
            assert instance_name in {instance["name"] for instance in listed_by_group}

            listed_by_subscription = self.cmd(
                "iot adr ns su instance list"
            ).get_output_in_json()
            assert instance_name in {
                instance["name"] for instance in listed_by_subscription
            }

            updated = self.cmd(
                f"iot adr ns su instance update -n {instance_name} "
                f"-g {TEST_RG} --tags env=updated"
            ).get_output_in_json()
            assert updated["tags"]["env"] == "updated"

            combined = self.cmd(
                f"iot adr ns su instance update -n {instance_name} "
                f"-g {TEST_RG} --mi-system-assigned "
                f"--mi-user-assigned {identity_id}"
            ).get_output_in_json()
            combined_types = {
                value.strip()
                for value in combined["identity"]["type"].split(",")
            }
            assert combined_types == {"SystemAssigned", "UserAssigned"}
            assert identity_id.casefold() in {
                resource_id.casefold()
                for resource_id in (
                    combined["identity"].get("userAssignedIdentities") or {}
                )
            }

            user_only = self.cmd(
                f"iot adr ns su instance update -n {instance_name} "
                f"-g {TEST_RG} --mi-user-assigned {identity_id}"
            ).get_output_in_json()
            assert user_only["identity"]["type"] == "UserAssigned"

            system_only = self.cmd(
                f"iot adr ns su instance update -n {instance_name} "
                f"-g {TEST_RG} --mi-system-assigned"
            ).get_output_in_json()
            assert system_only["identity"]["type"] == "SystemAssigned"
            assert not system_only["identity"].get("userAssignedIdentities")

            cleared_tags = self.cmd(
                f"iot adr ns su instance update -n {instance_name} "
                f"-g {TEST_RG} --tags ''"
            ).get_output_in_json()
            assert cleared_tags.get("tags") in ({}, None)

            no_identity = self.cmd(
                f"iot adr ns su instance update -n {instance_name} "
                f"-g {TEST_RG} --mi-system-assigned false"
            ).get_output_in_json()
            assert no_identity["identity"]["type"] == "None"

            self.cmd(
                f"iot adr ns su instance update -n {instance_name} " f"-g {TEST_RG}",
                expect_failure=True,
            )

            self.cmd(f"{delete_command} --no-wait")
            self.cmd(
                f"iot adr ns su instance wait -n {instance_name} "
                f"-g {TEST_RG} --deleted"
            )
            cleanup.dismiss("UpdateInstance")
            self.cmd(show_command, expect_failure=True)


@pytest.mark.usefixtures("set_cwd")
class TestADRUpdateInstanceValidation(CaptureOutputLiveScenarioTest):
    def test_update_instance_validation_negatives(self):
        self.cmd(
            "iot adr ns su instance update -n missing-instance " f"-g {TEST_RG}",
            expect_failure=True,
        )
        self.cmd(
            "iot adr ns su instance update -n missing-instance "
            f"-g {TEST_RG} --mi-user-assigned not-an-arm-id",
            expect_failure=True,
        )
