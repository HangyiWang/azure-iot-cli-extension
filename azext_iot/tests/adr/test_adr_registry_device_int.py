# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR registry device lifecycle integration tests.

Exercises the `iot adr ns registry-device` command surface (create / show / list /
update / delete) against a minimal namespace.

Run via ``tox -e ADR-int``.
"""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
    generate_device_id,
)


@pytest.mark.usefixtures("set_cwd")
class TestADRRegistryDeviceLifecycle(CaptureOutputLiveScenarioTest):
    """End-to-end registry device lifecycle exercised purely through the CLI."""

    def test_adr_registry_device_lifecycle(self):
        _log(LogKind.TEST, "test_adr_registry_device_lifecycle")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        device_name = generate_device_id()

        try:
            # --- Setup: namespace ---
            with timed_step("Setup ❯ Create namespace"):
                ns_cmd = (
                    f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION}"
                )
                _log(LogKind.CMD, "az %s", ns_cmd)
                self.cmd(ns_cmd).get_output_in_json()
                _log(LogKind.RESULT, "ok")

            def adev_cmd(action):
                cmd = f"iot adr ns registry-device {action} --ns {namespace_name} -g {rg}"
                _log(LogKind.CMD, "az %s", cmd)
                return self.cmd(cmd)

            def props(resp):
                return resp.get("properties", resp)

            # --- Step 1: Create with the full option set ---
            with timed_step("Step 1 ❯ Create registry device with all options"):
                created = adev_cmd(
                    f"create -n {device_name} "
                    f"--ext-id ext-001 --manufacturer Contoso --model RegistryPro "
                    f"--hw-rev A1 --sw-rev 2.0.0 --tags env=int"
                ).get_output_in_json()
                assert created["name"] == device_name
                cp = props(created)
                assert cp.get("externalDeviceId") == "ext-001"
                assert cp.get("enablementState") == "Enabled"
                assert cp.get("manufacturer") == "Contoso"
                assert cp.get("model") == "RegistryPro"
                assert cp.get("hardwareRevision") == "A1"
                assert cp.get("softwareRevision") == "2.0.0"
                assert created.get("tags", {}).get("env") == "int"
                _log(LogKind.OK, "Registry device '%s' created with all options", device_name)

            # --- Step 2: Show round-trips the resource ---
            with timed_step("Step 2 ❯ Show round-trip"):
                shown = adev_cmd(f"show -n {device_name}").get_output_in_json()
                assert shown["name"] == device_name
                assert props(shown).get("manufacturer") == "Contoso"

            # --- Step 3: List includes the new device ---
            with timed_step("Step 3 ❯ List includes new registry device"):
                devices = adev_cmd("list").get_output_in_json()
                assert isinstance(devices, list) and len(devices) >= 1
                assert device_name in [d["name"] for d in devices]

            # --- Step 4: Update properties ---
            with timed_step("Step 4 ❯ Disable and update software revision"):
                updated = adev_cmd(
                    f"update -n {device_name} --enablement-state Disabled --sw-rev 3.0.0"
                ).get_output_in_json()
                assert props(updated).get("softwareRevision") == "3.0.0"
                assert props(updated).get("enablementState") == "Disabled"

            # --- Step 5: Update tags ---
            with timed_step("Step 5 ❯ Update tags"):
                updated = adev_cmd(
                    f"update -n {device_name} --tags env=staging"
                ).get_output_in_json()
                assert updated.get("tags", {}).get("env") == "staging"

            # --- Step 6: Negative: update with no fields fails ---
            with timed_step("Step 6 ❯ Negative: update with no fields fails"):
                bad = (
                    f"iot adr ns registry-device update -n {device_name} "
                    f"--ns {namespace_name} -g {rg}"
                )
                _log(LogKind.CMD, "az %s  (expect failure)", bad)
                self.cmd(bad, expect_failure=True)

            # --- Step 7: Delete & confirm gone ---
            with timed_step("Step 7 ❯ Delete registry device and verify gone"):
                adev_cmd(f"delete -n {device_name} -y")
                bad_show = (
                    f"iot adr ns registry-device show -n {device_name} "
                    f"--ns {namespace_name} -g {rg}"
                )
                _log(LogKind.CMD, "az %s  (expect failure)", bad_show)
                self.cmd(bad_show, expect_failure=True)
                remaining = [d["name"] for d in adev_cmd("list").get_output_in_json()]
                assert device_name not in remaining
                _log(LogKind.OK, "Registry device '%s' deleted", device_name)

        finally:
            _log(LogKind.STEP, "Cleanup ❯ Delete namespace")
            try:
                cleanup_cmd = f"iot adr ns delete -n {namespace_name} -g {rg} -y"
                _log(LogKind.CMD, "az %s", cleanup_cmd)
                self.cmd(cleanup_cmd)
            except Exception as e:  # noqa: BLE001 - cleanup is best-effort
                _log(LogKind.WARN, "Cleanup failed: %s", e)
