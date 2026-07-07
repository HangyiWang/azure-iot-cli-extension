# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR device lifecycle integration tests.

Exercises the full `iot adr ns device` command surface (create / show / list /
update / revoke / delete) directly against a minimal namespace + default policy.
No external SDK or DPS provisioning is required -- devices are created via the
CLI itself.

Run via ``tox -e ADR-int``.
"""

import pytest

from azext_iot.adr.common import DEFAULT_NS_POLICY_NAME
from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
    generate_device_id,
)

# Substring of the provider's `CLIError` stub message emitted while the
# Microsoft.DeviceRegistry revoke API is still being finalized. Once the
# backend ships, the revoke call will succeed and the post-revoke assertions
# in Step 9 will run automatically -- no test changes required.
_REVOKE_STUB_MARKER = "not available yet"


@pytest.mark.usefixtures("set_cwd")
class TestADRDeviceLifecycle(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """End-to-end device lifecycle exercised purely through the CLI.

    No DPS, hub, or preview SDK required -- a single ADR namespace with the
    default credential policy is enough to cover create / show / list /
    update (all option groups) / revoke / delete and the corresponding
    negative paths.
    """

    def test_adr_device_lifecycle(self):
        """Exercise the full `iot adr ns device` command surface against a single namespace."""
        _log(LogKind.TEST, "test_adr_device_lifecycle")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        device_id = generate_device_id()
        minimal_device_id = generate_device_id()

        try:
            # --- Setup: namespace + default policy ---
            with timed_step("Setup ❯ Create namespace (with default policy)"):
                ns_cmd = (
                    f"iot adr ns create -n {namespace_name} -g {rg} "
                    f"--location {TEST_LOCATION} --policy-name {DEFAULT_NS_POLICY_NAME}"
                )
                _log(LogKind.CMD, "az %s", ns_cmd)
                self.cmd(ns_cmd).get_output_in_json()
                _log(LogKind.RESULT, "ok")

                subscription_id = self.cmd("account show").get_output_in_json()["id"]
                policy_resource_id = self.build_policy_resource_id(
                    subscription_id, rg, namespace_name, DEFAULT_NS_POLICY_NAME,
                )
                _log(LogKind.RESULT, "policy_resource_id=%s", policy_resource_id)

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
                    f"--policy-resource-id {policy_resource_id} --tags env=int owner=adr-tests"
                ).get_output_in_json()
                assert created["name"] == device_id
                cp = props(created)
                assert cp.get("manufacturer") == "Contoso"
                assert cp.get("model") == "SensorPro"
                assert cp.get("operatingSystem") == "Linux"
                assert cp.get("operatingSystemVersion") == "1.2.3"
                assert (cp.get("policy") or {}).get("resourceId") == policy_resource_id
                assert created.get("tags", {}).get("env") == "int"
                assert created.get("tags", {}).get("owner") == "adr-tests"
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
                    f'update -n {device_id} --attributes \'{{{{"region": "us", "tier": 1}}}}\''
                ).get_output_in_json()
                assert props(updated).get("attributes", {}).get("region") == "us"
                assert props(updated).get("attributes", {}).get("tier") == 1
                _log(LogKind.OK, "attributes set on device '%s'", device_id)

                updated = device_cmd(f"update -n {device_id} --attributes ''").get_output_in_json()
                attrs = props(updated).get("attributes")
                assert attrs == {} or attrs is None
                _log(LogKind.OK, "attributes cleared on device '%s'", device_id)

            # --- Step 8: Update --policy-resource-id clear + reassign ---
            with timed_step("Step 8 ❯ Update --policy-resource-id clear & reassign"):
                updated = device_cmd(
                    f"update -n {device_id} --policy-resource-id ''"
                ).get_output_in_json()
                pol = props(updated).get("policy")
                assert not pol or not pol.get("resourceId")
                _log(LogKind.OK, "policy cleared on device '%s'", device_id)

                updated = device_cmd(
                    f"update -n {device_id} --policy-resource-id {policy_resource_id}"
                ).get_output_in_json()
                assert (props(updated).get("policy") or {}).get("resourceId") == policy_resource_id
                _log(LogKind.OK, "policy reassigned on device '%s'", device_id)

            # --- Step 9: Revoke (graceful while backend API is being finalized) ---
            with timed_step("Step 9 ❯ Revoke credentials"):
                # Re-enable device first; policy already assigned.
                device_cmd(f"update -n {device_id} --enabled true")

                def revoke_and_check(revoke_args, expected_enabled, label):
                    """Call revoke and verify; tolerate the stub `CLIError` until the backend ships."""
                    full_cmd = f"revoke -n {device_id} {revoke_args} -y".strip()
                    try:
                        revoke_result = device_cmd(full_cmd).get_output_in_json()
                    except Exception as e:  # noqa: BLE001 - stub returns CLIError until backend ships
                        msg = str(e)
                        if _REVOKE_STUB_MARKER in msg:
                            _log(
                                LogKind.WARN,
                                "[%s] revoke API not yet shipped -- deferring assertions. msg=%s",
                                label, msg[:200],
                            )
                            return
                        raise

                    _log(
                        LogKind.OK,
                        "[%s] Revoke response: result=%s, error=%s",
                        label,
                        revoke_result.get("result"),
                        revoke_result.get("error"),
                    )
                    assert revoke_result.get("error") is None, (
                        f"[{label}] Revoke returned error: {revoke_result.get('error')}"
                    )

                    d = device_cmd(f"show -n {device_id}").get_output_in_json()
                    dp = props(d)
                    if expected_enabled is not None:
                        assert dp.get("enabled") is expected_enabled, (
                            f"[{label}] expected enabled={expected_enabled}, got {dp.get('enabled')}"
                        )
                    _log(
                        LogKind.OK,
                        "[%s] ADR device: enabled=%s, version=%s",
                        label, dp.get("enabled"), dp.get("version"),
                    )

                revoke_and_check("", expected_enabled=True, label="revoke-default")
                revoke_and_check("--disable", expected_enabled=False, label="revoke-disable")
                revoke_and_check("", expected_enabled=None, label="revoke-while-disabled")

                device_cmd(f"update -n {device_id} --enabled true")
                _log(LogKind.RESULT, "Device re-enabled for idempotency test")
                revoke_and_check("", expected_enabled=True, label="revoke-idempotency")

            # --- Step 10: Negative: revoke nonexistent device ---
            with timed_step("Step 10 ❯ Negative: revoke nonexistent device fails"):
                bad_revoke = (
                    f"iot adr ns device revoke -n nonexistent-device "
                    f"--ns {namespace_name} -g {rg} -y"
                )
                _log(LogKind.CMD, "az %s  (expect failure)", bad_revoke)
                self.cmd(bad_revoke, expect_failure=True)
                _log(LogKind.OK, "Revoking nonexistent device correctly failed")

            # --- Step 11: Minimal create (no optional flags) round-trip ---
            with timed_step("Step 11 ❯ Create device with no optional flags"):
                minimal = device_cmd(f"create -n {minimal_device_id}").get_output_in_json()
                assert minimal["name"] == minimal_device_id
                _log(LogKind.OK, "Minimal device '%s' created", minimal_device_id)

                listed_names = [d["name"] for d in device_cmd("list").get_output_in_json()]
                assert minimal_device_id in listed_names and device_id in listed_names

            # --- Step 12: Delete first device & confirm gone ---
            with timed_step("Step 12 ❯ Delete device and verify gone"):
                device_cmd(f"delete -n {device_id} -y")
                _log(LogKind.OK, "Delete returned for device '%s'", device_id)

                bad_show = (
                    f"iot adr ns device show -n {device_id} "
                    f"--ns {namespace_name} -g {rg}"
                )
                _log(LogKind.CMD, "az %s  (expect failure)", bad_show)
                self.cmd(bad_show, expect_failure=True)
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
            _log(LogKind.STEP, "Setup ❯ Create namespace with credential+policy")
            ns_cmd = (
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --policy-name {DEFAULT_NS_POLICY_NAME}"
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
