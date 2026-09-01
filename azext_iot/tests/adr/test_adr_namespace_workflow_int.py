# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)

_DPS_ID = os.getenv("azext_iot_adr_workflow_dps_id", "").strip()
_HUB_ID = os.getenv("azext_iot_adr_workflow_hub_id", "").strip()


@pytest.mark.usefixtures("set_cwd")
class TestADRNamespaceWorkflow(CaptureOutputLiveScenarioTest):
    def test_namespace_setup_tagged_plan_is_read_only(self):
        namespace_name = generate_adr_namespace_name()
        plan = self.cmd(
            "iot adr ns setup "
            f"-n {namespace_name} -g {TEST_RG} -l {TEST_LOCATION} "
            "--tags env=integration owner=adr-workflow "
            "--namespace-outbound-identity system-assigned "
            "--plan-only"
        ).get_output_in_json()
        namespace = next(
            item for item in plan["items"] if item["id"] == "namespace"
        )
        assert namespace["state"] == "Planned"
        assert namespace["details"]["tags"] == {
            "env": "integration",
            "owner": "adr-workflow",
        }

    def test_namespace_setup_check_and_resume(self):
        namespace_name = generate_adr_namespace_name()
        setup = (
            f"iot adr ns setup -n {namespace_name} -g {TEST_RG} "
            f"-l {TEST_LOCATION} "
            "--namespace-outbound-identity system-assigned"
        )
        try:
            plan = self.cmd(f"{setup} --plan-only").get_output_in_json()
            assert plan["state"] == "Planned"
            assert any(
                item["id"] == "namespace" and item["state"] == "Planned"
                for item in plan["items"]
            )

            applied = self.cmd(f"{setup} --yes").get_output_in_json()
            assert applied["state"] == "Succeeded"

            checked = self.cmd(
                f"iot adr ns check -n {namespace_name} -g {TEST_RG}"
            ).get_output_in_json()
            assert checked["state"] == "Succeeded"
            assert checked["summary"]["NotConfigured"] == 3

            resumed = self.cmd(f"{setup} --yes").get_output_in_json()
            assert resumed["state"] == "Succeeded"
            assert any(
                item["id"] == "namespace"
                and item["state"] == "Satisfied"
                for item in resumed["items"]
            )
        finally:
            self.cmd(
                f"iot adr ns delete -n {namespace_name} -g {TEST_RG} --yes",
                checks=[],
            )

    @pytest.mark.skipif(
        not (_DPS_ID and _HUB_ID),
        reason=(
            "Set azext_iot_adr_workflow_dps_id and "
            "azext_iot_adr_workflow_hub_id to disposable resources with SAMIs."
        ),
    )
    def test_namespace_setup_links_dps_and_hub_with_rbac(self):
        namespace_name = generate_adr_namespace_name()
        setup = (
            f"iot adr ns setup -n {namespace_name} -g {TEST_RG} "
            f"-l {TEST_LOCATION} "
            "--namespace-outbound-identity system-assigned "
            f"--dps name=primary resource-id={_DPS_ID} "
            "identity=system-assigned "
            f"--hub name=primary resource-id={_HUB_ID} "
            "identity=system-assigned "
            "--assign-roles"
        )
        applied = None
        try:
            plan = self.cmd(f"{setup} --plan-only").get_output_in_json()
            assert plan["state"] == "Planned"

            applied = self.cmd(f"{setup} --yes").get_output_in_json()
            assert applied["state"] == "Succeeded"
            assert self.cmd(
                f"iot adr ns link dps show -n primary "
                f"--ns {namespace_name} -g {TEST_RG}"
            ).get_output_in_json()["linkingState"] == "Succeeded"
            assert self.cmd(
                f"iot adr ns link hub show -n primary "
                f"--ns {namespace_name} -g {TEST_RG}"
            ).get_output_in_json()["linkingState"] == "Succeeded"

            checked = self.cmd(
                f"iot adr ns check -n {namespace_name} -g {TEST_RG}"
            ).get_output_in_json()
            assert checked["state"] == "Succeeded"

            resumed = self.cmd(f"{setup} --yes").get_output_in_json()
            assert resumed["state"] == "Succeeded"
            assert resumed["summary"]["Satisfied"] >= 3
        finally:
            for item in (applied or {}).get("items", []):
                if item.get("action") != "grant":
                    continue
                details = item.get("details") or {}
                try:
                    self.cmd(
                        "role assignment delete "
                        f"--assignee-object-id {details['principalId']} "
                        f"--role \"{details['role']}\" "
                        f"--scope {item['target']}",
                        checks=[],
                    )
                except Exception:  # noqa: BLE001 - cleanup is best effort
                    pass
            try:
                self.cmd(
                    f"iot adr ns delete -n {namespace_name} "
                    f"-g {TEST_RG} --yes",
                    checks=[],
                )
            except Exception:  # noqa: BLE001 - cleanup is best effort
                pass
