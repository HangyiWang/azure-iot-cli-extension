# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR device lifecycle integration tests.

Exercises the full `iot adr ns device` command surface (create / show / list /
update / delete) directly against a minimal namespace.
No external SDK or DPS provisioning is required -- devices are created via the
CLI itself.

Run via ``tox -e ADR-int``.
"""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
    generate_device_id,
)


_ENDPOINT_NAME = "eventGridEndpoint"
_ENDPOINT_TYPE = "Microsoft.Devices/IoTHubs"
_CREATE_ENDPOINT_ADDRESS = (
    "https://myeventgridtopic.westeurope-1.eventgrid.azure.net/api/events"
)
_UPDATE_ENDPOINT_ADDRESS = (
    "https://updatedeventgridtopic.westeurope-1.eventgrid.azure.net/api/events"
)


@pytest.mark.usefixtures("set_cwd")
class TestADRDeviceLifecycle(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """End-to-end device lifecycle exercised purely through the CLI.

    No DPS, hub, or preview SDK is required.
    """

    def test_adr_device_lifecycle(self):
        """Exercise the full `iot adr ns device` command surface against a single namespace."""
        _log(LogKind.TEST, "test_adr_device_lifecycle")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        device_id = generate_device_id()
        minimal_device_id = generate_device_id()

        try:
            # --- Setup: namespace ---
            with timed_step("Setup ❯ Create namespace"):
                ns_cmd = (
                    f"iot adr ns create -n {namespace_name} -g {rg} "
                    f"--location {TEST_LOCATION}"
                )
                _log(LogKind.CMD, "az %s", ns_cmd)
                self.cmd(ns_cmd).get_output_in_json()
                _log(LogKind.RESULT, "ok")

            def device_cmd(action):
                """Run ``iot adr ns device <action>`` against the test namespace."""
                cmd = f"iot adr ns device {action} --ns {namespace_name} -g {rg}"
                _log(LogKind.CMD, "az %s", cmd)
                return self.cmd(cmd)

            def props(resp):
                """Extract properties sub-dict from ARM resource envelope."""
                return resp.get("properties", resp)

            # --- Step 1: Create device with the full option set ---
            with timed_step("Step 1 ❯ Create device with all options"):
                created = device_cmd(
                    f"create -n {device_id} "
                    f"--manufacturer Contoso --model SensorPro --os Linux --os-version 1.2.3 "
                    f"--external-device-id external-42 --enabled true "
                    f"--attributes '{{\"site\":\"west\"}}' "
                    f"--endpoints '{{\"outbound\":{{\"assigned\":{{\"{_ENDPOINT_NAME}\":"
                    f"{{\"address\":\"{_CREATE_ENDPOINT_ADDRESS}\","
                    f"\"endpointType\":\"{_ENDPOINT_TYPE}\"}}}}}}}}' "
                    "--tags env=int owner=adr-tests"
                ).get_output_in_json()
                assert created["name"] == device_id
                cp = props(created)
                assert cp.get("manufacturer") == "Contoso"
                assert cp.get("model") == "SensorPro"
                assert cp.get("operatingSystem") == "Linux"
                assert cp.get("operatingSystemVersion") == "1.2.3"
                assert cp.get("externalDeviceId") == "external-42"
                assert cp.get("enabled") is True
                assert cp.get("attributes", {}).get("site") == "west"
                assigned_endpoint = (
                    cp["endpoints"]["outbound"]["assigned"][_ENDPOINT_NAME]
                )
                assert assigned_endpoint == {
                    "address": _CREATE_ENDPOINT_ADDRESS,
                    "endpointType": _ENDPOINT_TYPE,
                }
                assert created.get("tags", {}).get("env") == "int"
                assert created.get("tags", {}).get("owner") == "adr-tests"
                device_cmd(f"wait -n {device_id} --created")
                _log(LogKind.OK, "Device '%s' created with all options", device_id)

            # --- Step 2: Show round-trips the resource ---
            with timed_step("Step 2 ❯ Show round-trip"):
                shown = device_cmd(f"show -n {device_id}").get_output_in_json()
                assert shown["name"] == device_id
                assert props(shown).get("manufacturer") == "Contoso"
                _log(LogKind.OK, "Device show returned correct device '%s'", device_id)

            # --- Step 3: List includes the new device ---
            with timed_step("Step 3 ❯ List includes new device"):
                devices = device_cmd("list").get_output_in_json()
                assert isinstance(devices, list) and len(devices) >= 1
                assert device_id in [d["name"] for d in devices]
                _log(LogKind.OK, "Device '%s' present in namespace list", device_id)

            # --- Step 4: Update --enabled true/false toggle ---
            with timed_step("Step 4 ❯ Update --enabled true/false"):
                for val, expected in [("false", False), ("true", True)]:
                    updated = device_cmd(f"update -n {device_id} --enabled {val}").get_output_in_json()
                    assert props(updated).get("enabled") is expected
                    _log(LogKind.OK, "enabled=%s after --enabled %s", expected, val)

            # --- Step 5: Update --os-version set + clear ---
            with timed_step("Step 5 ❯ Update --os-version set & clear"):
                updated = device_cmd(f"update -n {device_id} --os-version 4.0.0").get_output_in_json()
                assert props(updated).get("operatingSystemVersion") == "4.0.0"

                updated = device_cmd(f"update -n {device_id} --os-version ''").get_output_in_json()
                assert props(updated).get("operatingSystemVersion") in ("", None)
                _log(LogKind.OK, "os-version cleared on device '%s'", device_id)

            # --- Step 6: Update --tags set + clear ---
            with timed_step("Step 6 ❯ Update --tags set & clear"):
                updated = device_cmd(f"update -n {device_id} --tags env=staging").get_output_in_json()
                assert updated.get("tags", {}).get("env") == "staging"

                updated = device_cmd(f"update -n {device_id} --tags ''").get_output_in_json()
                assert updated.get("tags") in ({}, None)
                _log(LogKind.OK, "tags cleared on device '%s'", device_id)

            # --- Step 7: Update --attributes set + clear ---
            with timed_step("Step 7 ❯ Update --attributes set & clear"):
                updated = device_cmd(
                    f'update -n {device_id} --attributes \'{{"region": "us", "tier": 1}}\''
                ).get_output_in_json()
                assert props(updated).get("attributes", {}).get("region") == "us"
                assert props(updated).get("attributes", {}).get("tier") == 1
                _log(LogKind.OK, "attributes set on device '%s'", device_id)

                updated = device_cmd(
                    f"update -n {device_id} --attributes '{{}}'"
                ).get_output_in_json()
                attrs = props(updated).get("attributes")
                assert attrs == {}
                _log(LogKind.OK, "attributes cleared on device '%s'", device_id)

            with timed_step("Step 8 ❯ Update contract-valid --endpoints"):
                updated = device_cmd(
                    f'update -n {device_id} --endpoints '
                    f'\'{{"outbound":{{"assigned":{{"{_ENDPOINT_NAME}":'
                    f'{{"address":"{_UPDATE_ENDPOINT_ADDRESS}",'
                    f'"endpointType":"{_ENDPOINT_TYPE}"}}}}}}}}\''
                ).get_output_in_json()
                assigned_endpoint = (
                    props(updated)["endpoints"]["outbound"]["assigned"][_ENDPOINT_NAME]
                )
                assert assigned_endpoint == {
                    "address": _UPDATE_ENDPOINT_ADDRESS,
                    "endpointType": _ENDPOINT_TYPE,
                }
                removed_endpoint = device_cmd(
                    f"update -n {device_id} "
                    "--endpoints '{\"outbound\":{\"assigned\":{}}}'"
                ).get_output_in_json()
                assert (
                    props(removed_endpoint)
                    .get("endpoints", {})
                    .get("outbound", {})
                    .get("assigned")
                    in ({}, None)
                )

            with timed_step("Step 9 ❯ Reject empty update"):
                self.cmd(
                    f"iot adr ns device update -n {device_id} "
                    f"--ns {namespace_name} -g {rg}",
                    expect_failure=True,
                )

            # --- Step 10: Minimal create (no optional flags) round-trip ---
            with timed_step("Step 10 ❯ Create device with no optional flags"):
                minimal = device_cmd(f"create -n {minimal_device_id}").get_output_in_json()
                assert minimal["name"] == minimal_device_id
                _log(LogKind.OK, "Minimal device '%s' created", minimal_device_id)

                listed_names = [d["name"] for d in device_cmd("list").get_output_in_json()]
                assert minimal_device_id in listed_names and device_id in listed_names

            # --- Step 11: Delete first device & confirm gone ---
            with timed_step("Step 11 ❯ Delete device and verify gone"):
                device_cmd(f"delete -n {device_id} -y")
                _log(LogKind.OK, "Delete returned for device '%s'", device_id)

                bad_show = (
                    f"iot adr ns device show -n {device_id} "
                    f"--ns {namespace_name} -g {rg}"
                )
                _log(LogKind.CMD, "az %s  (expect failure)", bad_show)
                self.cmd(bad_show, expect_failure=True)
                device_cmd(f"delete -n {device_id} -y")
                _log(LogKind.OK, "Device '%s' no longer resolvable after delete", device_id)

                remaining = [d["name"] for d in device_cmd("list").get_output_in_json()]
                assert device_id not in remaining
                assert minimal_device_id in remaining, (
                    f"Sibling device '{minimal_device_id}' should still exist; got {remaining}"
                )

        finally:
            _log(LogKind.STEP, "Cleanup ❯ Delete namespace")
            try:
                cleanup_cmd = f"iot adr ns delete -n {namespace_name} -g {rg} -y"
                _log(LogKind.CMD, "az %s", cleanup_cmd)
                self.cmd(cleanup_cmd)
                _log(LogKind.RESULT, "ok")
            except Exception as e:  # noqa: BLE001 - cleanup is best-effort
                _log(LogKind.WARN, "Cleanup failed: %s", e)


@pytest.mark.usefixtures("set_cwd")
class TestADRDeviceEdgeCases(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Negative and edge-case device tests that don't require DPS or the preview SDK."""

    def test_adr_device_negative_and_edge_cases(self):
        """Verify device command behavior for empty namespaces, nonexistent resources."""
        _log(LogKind.TEST, "test_adr_device_negative_and_edge_cases")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            _log(LogKind.STEP, "Setup ❯ Create namespace")
            ns_cmd = (
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION}"
            )
            _log(LogKind.CMD, "az %s", ns_cmd)
            self.cmd(ns_cmd)
            _log(LogKind.RESULT, "ok")

            # Device list on empty namespace returns an empty list
            _log(LogKind.STEP, "Verify ❯ Device list on empty namespace returns empty")
            list_cmd = f"iot adr ns device list --ns {namespace_name} -g {rg}"
            _log(LogKind.CMD, "az %s", list_cmd)
            devices = self.cmd(list_cmd).get_output_in_json()
            assert isinstance(devices, list)
            assert len(devices) == 0, (
                f"Expected empty device list on fresh namespace, got {len(devices)} devices"
            )
            _log(LogKind.OK, "Device list returned empty list (0 devices)")

            # Show nonexistent device returns ResourceNotFound
            _log(LogKind.STEP, "Verify ❯ Show nonexistent device fails")
            show_cmd = f"iot adr ns device show -n nonexistent-device --ns {namespace_name} -g {rg}"
            _log(LogKind.CMD, "az %s  (expect failure)", show_cmd)
            self.cmd(show_cmd, expect_failure=True)
            _log(LogKind.OK, "Show nonexistent device correctly returned failure")

            self.cmd(
                f"iot adr ns device create -n invalid-json "
                f"--ns {namespace_name} -g {rg} --attributes not-json",
                expect_failure=True,
            )

        finally:
            _log(LogKind.STEP, "Cleanup ❯ Delete Namespace")
            try:
                cleanup_cmd = f"iot adr ns delete -n {namespace_name} -g {rg} -y"
                _log(LogKind.CMD, "az %s", cleanup_cmd)
                self.cmd(cleanup_cmd)
                _log(LogKind.RESULT, "ok")
            except Exception as e:
                _log(LogKind.WARN, "Cleanup failed: %s", e)

        # Device list against a nonexistent namespace returns a 404
        # (ParentResourceNotFound) because the parent namespace does not exist.
        _log(LogKind.STEP, "Verify ❯ Device list on nonexistent namespace fails with 404")
        nonexistent_list_cmd = f"iot adr ns device list --ns nonexistent-ns-{namespace_name} -g {rg}"
        _log(LogKind.CMD, "az %s  (expect failure)", nonexistent_list_cmd)
        self.cmd(nonexistent_list_cmd, expect_failure=True)
        _log(LogKind.OK, "Device list on nonexistent namespace correctly returned failure")
