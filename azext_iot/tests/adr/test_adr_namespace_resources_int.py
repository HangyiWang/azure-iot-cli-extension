# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Infrastructure-dependent Namespace Asset and discovery integration coverage."""

import json
import os
import shlex

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import wait_for_resource_succeeded
from azext_iot.tests.adr._log import LogKind, _log
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)
from azext_iot.tests.generators import generate_generic_id


CUSTOM_LOCATION_ID = os.getenv("azext_iot_adr_custom_location_id")
RUN_RESOURCE_PARITY = os.getenv("azext_iot_adr_run_resource_parity_int") == "1"
ASSET_ACTION_NAME = os.getenv("azext_iot_adr_asset_action_name")
ASSET_MANAGEMENT_GROUP = os.getenv("azext_iot_adr_asset_management_group")
ASSET_ACTION_PAYLOAD = os.getenv("azext_iot_adr_asset_action_payload", "{}")
ASSET_ACTION_NAMESPACE = os.getenv("azext_iot_adr_asset_action_namespace")
ASSET_ACTION_ASSET_NAME = os.getenv(
    "azext_iot_adr_asset_action_asset_name"
)
ASSET_ACTION_RESOURCE_GROUP = os.getenv(
    "azext_iot_adr_asset_action_resource_group", TEST_RG
)
HAS_ASSET_ACTION = all(
    (
        ASSET_ACTION_NAME,
        ASSET_MANAGEMENT_GROUP,
        ASSET_ACTION_NAMESPACE,
        ASSET_ACTION_ASSET_NAME,
    )
)


def _name(prefix: str) -> str:
    return f"{prefix}{generate_generic_id()[:8]}"


def _json_argument(value: dict) -> str:
    return shlex.quote(json.dumps(value, separators=(",", ":")))


def _create_namespace_device(
    test,
    namespace_name: str,
    device_name: str,
    endpoint_name: str,
    extended_location: dict,
) -> None:
    test.cmd(
        f"iot adr ns create -n {namespace_name} -g {TEST_RG} "
        f"--location {TEST_LOCATION}"
    )
    test.cmd(
        f"iot adr ns device create -n {device_name} "
        f"--ns {namespace_name} -g {TEST_RG} "
        f"--extended-location {_json_argument(extended_location)} "
        "--enabled true "
        "--endpoints "
        + _json_argument(
            {
                "outbound": {
                    "assigned": {
                        endpoint_name: {
                            "endpointType": "Microsoft.Devices",
                            "address": "https://example.invalid/events",
                        }
                    }
                }
            }
        )
    )


@pytest.mark.skipif(
    not RUN_RESOURCE_PARITY or not CUSTOM_LOCATION_ID,
    reason=(
        "Set azext_iot_adr_run_resource_parity_int=1 and "
        "azext_iot_adr_custom_location_id to run custom-location parity tests."
    ),
)
@pytest.mark.usefixtures("set_cwd")
class TestADRNamespaceResourceLifecycle(CaptureOutputLiveScenarioTest):
    def test_asset_and_discovery_lifecycles(self):
        namespace_name = generate_adr_namespace_name()
        device_name = _name("device")
        discovered_device_name = _name("discdev")
        discovered_asset_name = _name("discasset")
        asset_name = _name("asset")
        endpoint_name = "events"
        extended_location = {
            "name": CUSTOM_LOCATION_ID,
            "type": "CustomLocation",
        }
        device_ref = {
            "deviceName": device_name,
            "endpointName": endpoint_name,
        }

        try:
            _create_namespace_device(
                self,
                namespace_name,
                device_name,
                endpoint_name,
                extended_location,
            )

            discovered_device_show = (
                f"iot adr ns discovered-device show -n {discovered_device_name} "
                f"--ns {namespace_name} -g {TEST_RG}"
            )
            self.cmd(
                f"iot adr ns discovered-device create -n {discovered_device_name} "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--extended-location {_json_argument(extended_location)} "
                f"--properties {_json_argument({'discoveryId': 'scan-1', 'version': 1})} "
                "--no-wait"
            )
            self.cmd(
                f"iot adr ns discovered-device wait -n {discovered_device_name} "
                f"--ns {namespace_name} -g {TEST_RG} --created"
            )
            discovered_device = wait_for_resource_succeeded(
                self, discovered_device_show
            )
            assert discovered_device["name"] == discovered_device_name
            assert discovered_device["properties"]["version"] == 1
            assert discovered_device_name in [
                item["name"]
                for item in self.cmd(
                    f"iot adr ns discovered-device list --ns {namespace_name} "
                    f"-g {TEST_RG}"
                ).get_output_in_json()
            ]
            updated_device = self.cmd(
                f"iot adr ns discovered-device update -n {discovered_device_name} "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--properties {_json_argument({'discoveryId': 'scan-2', 'version': 2})}"
            ).get_output_in_json()
            assert updated_device["properties"]["version"] == 2
            cleared_device = self.cmd(
                f"iot adr ns discovered-device update "
                f"-n {discovered_device_name} --ns {namespace_name} "
                f"-g {TEST_RG} "
                f"--properties "
                f"{_json_argument({'attributes': {}, 'version': 3})}"
            ).get_output_in_json()
            assert cleared_device["properties"]["attributes"] == {}
            assert cleared_device["properties"]["version"] == 3
            self.cmd(
                f"iot adr ns discovered-device update "
                f"-n {discovered_device_name} --ns {namespace_name} "
                f"-g {TEST_RG} "
                f"--properties {_json_argument({'version': -1})}",
                expect_failure=True,
            )
            self.cmd(
                f"iot adr ns discovered-device update -n {discovered_device_name} "
                f"--ns {namespace_name} -g {TEST_RG}",
                expect_failure=True,
            )

            discovered_asset_properties = {
                "deviceRef": device_ref,
                "discoveryId": "asset-scan-1",
                "externalAssetId": "external-asset",
                "version": 1,
            }
            discovered_asset_show = (
                f"iot adr ns discovered-asset show -n {discovered_asset_name} "
                f"--ns {namespace_name} -g {TEST_RG}"
            )
            self.cmd(
                f"iot adr ns discovered-asset create -n {discovered_asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--extended-location {_json_argument(extended_location)} "
                f"--properties {_json_argument(discovered_asset_properties)} "
                "--no-wait"
            )
            self.cmd(
                f"iot adr ns discovered-asset wait -n {discovered_asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} --created"
            )
            discovered_asset = wait_for_resource_succeeded(
                self, discovered_asset_show
            )
            assert discovered_asset["name"] == discovered_asset_name
            assert discovered_asset_name in [
                item["name"]
                for item in self.cmd(
                    f"iot adr ns discovered-asset list --ns {namespace_name} "
                    f"-g {TEST_RG}"
                ).get_output_in_json()
            ]
            updated_discovered_asset = self.cmd(
                f"iot adr ns discovered-asset update -n {discovered_asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--properties {_json_argument({'displayName': 'updated', 'version': 2})}"
            ).get_output_in_json()
            assert updated_discovered_asset["properties"]["displayName"] == "updated"
            cleared_discovered_asset = self.cmd(
                f"iot adr ns discovered-asset update "
                f"-n {discovered_asset_name} --ns {namespace_name} "
                f"-g {TEST_RG} "
                f"--properties "
                f"{_json_argument({'displayName': '', 'version': 3})}"
            ).get_output_in_json()
            assert cleared_discovered_asset["properties"].get(
                "displayName"
            ) in (
                "",
                None,
            )
            self.cmd(
                f"iot adr ns discovered-asset create -n invalid-reference "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--extended-location {_json_argument(extended_location)} "
                f"--properties "
                f"{_json_argument({'discoveryId': 'invalid', 'version': 1})}",
                expect_failure=True,
            )
            self.cmd(
                f"iot adr ns discovered-asset update -n {discovered_asset_name} "
                f"--ns {namespace_name} -g {TEST_RG}",
                expect_failure=True,
            )

            asset_properties = {
                "deviceRef": device_ref,
                "externalAssetId": "external-promoted-asset",
                "enabled": True,
            }
            asset_show = (
                f"iot adr ns asset show -n {asset_name} "
                f"--ns {namespace_name} -g {TEST_RG}"
            )
            self.cmd(
                f"iot adr ns asset create -n {asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--extended-location {_json_argument(extended_location)} "
                f"--properties {_json_argument(asset_properties)} --no-wait"
            )
            self.cmd(
                f"iot adr ns asset wait -n {asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} --created"
            )
            asset = wait_for_resource_succeeded(self, asset_show)
            assert asset["name"] == asset_name
            assert asset_name in [
                item["name"]
                for item in self.cmd(
                    f"iot adr ns asset list --ns {namespace_name} -g {TEST_RG}"
                ).get_output_in_json()
            ]
            updated_asset = self.cmd(
                f"iot adr ns asset update -n {asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--properties {_json_argument({'displayName': 'updated', 'enabled': True})}"
            ).get_output_in_json()
            assert updated_asset["properties"]["enabled"] is True
            self.cmd(
                f"iot adr ns asset update -n {asset_name} "
                f"--ns {namespace_name} -g {TEST_RG}",
                expect_failure=True,
            )

            disabled_asset = self.cmd(
                f"iot adr ns asset update -n {asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--properties {_json_argument({'enabled': False})}"
            ).get_output_in_json()
            assert disabled_asset["properties"]["enabled"] is False
            cleared_asset = self.cmd(
                f"iot adr ns asset update -n {asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--properties "
                f"{_json_argument({'displayName': '', 'enabled': False})}"
            ).get_output_in_json()
            assert cleared_asset["properties"].get("displayName") in ("", None)

            self.cmd(
                f"iot adr ns asset delete -n {asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} --yes"
            )
            self.cmd(asset_show, expect_failure=True)
            self.cmd(
                f"iot adr ns discovered-asset delete -n {discovered_asset_name} "
                f"--ns {namespace_name} -g {TEST_RG} --yes"
            )
            self.cmd(discovered_asset_show, expect_failure=True)
            self.cmd(
                f"iot adr ns discovered-device delete -n {discovered_device_name} "
                f"--ns {namespace_name} -g {TEST_RG} --yes"
            )
            self.cmd(discovered_device_show, expect_failure=True)

            missing_namespace = f"missing{generate_generic_id()[:8]}"
            for group in ("asset", "discovered-asset", "discovered-device"):
                self.cmd(
                    f"iot adr ns {group} list --ns {missing_namespace} "
                    f"-g {TEST_RG}",
                    expect_failure=True,
                )
        finally:
            try:
                self.cmd(
                    f"iot adr ns delete -n {namespace_name} -g {TEST_RG} --yes"
                )
            except Exception as error:  # noqa: BLE001 - cleanup is best-effort
                _log(LogKind.WARN, "Cleanup failed: %s", error)


@pytest.mark.usefixtures("set_cwd")
class TestADRNamespaceAssetActionValidation(CaptureOutputLiveScenarioTest):
    def test_asset_action_rejects_missing_names_and_malformed_payload(self):
        base_command = (
            "iot adr ns asset execute-action -n missing-asset "
            f"--ns missing-namespace -g {TEST_RG}"
        )
        self.cmd(
            f"{base_command} --action-name '' "
            "--management-group-name group",
            expect_failure=True,
        )
        self.cmd(
            f"{base_command} --action-name action "
            "--management-group-name ''",
            expect_failure=True,
        )
        self.cmd(
            f"{base_command} --action-name action "
            "--management-group-name group --payload not-json",
            expect_failure=True,
        )


@pytest.mark.skipif(
    not HAS_ASSET_ACTION,
    reason=(
        "Set azext_iot_adr_asset_action_name, "
        "azext_iot_adr_asset_management_group, and "
        "azext_iot_adr_asset_action_namespace/asset_name to a "
        "preconfigured management-enabled asset."
    ),
)
@pytest.mark.usefixtures("set_cwd")
class TestADRNamespaceAssetAction(CaptureOutputLiveScenarioTest):
    def test_namespace_asset_execute_action(self):
        result = self.cmd(
            f"iot adr ns asset execute-action "
            f"-n {ASSET_ACTION_ASSET_NAME} "
            f"--ns {ASSET_ACTION_NAMESPACE} "
            f"-g {ASSET_ACTION_RESOURCE_GROUP} "
            f"--action-name {shlex.quote(ASSET_ACTION_NAME)} "
            f"--management-group-name "
            f"{shlex.quote(ASSET_MANAGEMENT_GROUP)} "
            f"--payload {shlex.quote(ASSET_ACTION_PAYLOAD)}"
        ).get_output_in_json()
        assert result["status"] == "Succeeded"
        assert result["managementActionName"] == ASSET_ACTION_NAME
        assert result["managementGroupName"] == ASSET_MANAGEMENT_GROUP
