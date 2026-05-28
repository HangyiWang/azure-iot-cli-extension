# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Integration tests for ``iot adr ns group {create|show|list|delete}``.

Lightweight: only requires a namespace, no Hub / DPS / UAMI.
"""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)
from azext_iot.tests.generators import generate_generic_id


def _gen_group_name() -> str:
    return f"testgrp{generate_generic_id()[:8]}"


# Simple membership query — service accepts arbitrary KQL-style filter strings
# on create; we only need the round-trip to work for CRUD coverage.
_TEST_QUERY = "true"


@pytest.mark.usefixtures("set_cwd")
class TestADRGroupCrudLifecycle(CaptureOutputLiveScenarioTest):
    """Lifecycle: create namespace -> CRUD groups -> cleanup."""

    def test_group_crud_lifecycle(self):
        _log(LogKind.TEST, "test_group_crud_lifecycle")
        rg = TEST_RG
        ns = generate_adr_namespace_name()
        group_a = _gen_group_name()
        group_b = _gen_group_name()

        try:
            with timed_step("Step 1 ❯ Create ADR Namespace"):
                ns_cmd = f"iot adr ns create -n {ns} -g {rg} --location {TEST_LOCATION}"
                _log(LogKind.CMD, "az %s", ns_cmd)
                self.cmd(ns_cmd)
                _log(LogKind.RESULT, "namespace=%s", ns)

            with timed_step("Step 2 ❯ Create group (minimal)"):
                create_a = (
                    f"iot adr ns group create -n {group_a} --ns {ns} -g {rg} "
                    f'--query-string "{_TEST_QUERY}"'
                )
                _log(LogKind.CMD, "az %s", create_a)
                a = self.cmd(create_a).get_output_in_json()
                assert a["name"] == group_a
                assert a["properties"]["groupType"] == "Device"
                assert a["properties"]["query"] == _TEST_QUERY
                assert a["properties"]["provisioningState"] == "Succeeded"
                _log(LogKind.OK, "group_a created, groupType=Device")

            with timed_step("Step 3 ❯ Create group (with display name, description, tags)"):
                create_b = (
                    f"iot adr ns group create -n {group_b} --ns {ns} -g {rg} "
                    f'--query-string "{_TEST_QUERY}" '
                    f'--display-name "Test Group B" --description "integration-test group" '
                    f"--tags env=test owner=adr-tests"
                )
                _log(LogKind.CMD, "az %s", create_b)
                b = self.cmd(create_b).get_output_in_json()
                assert b["name"] == group_b
                assert b["properties"]["displayName"] == "Test Group B"
                assert b["properties"]["description"] == "integration-test group"
                assert b.get("tags", {}).get("env") == "test"
                assert b.get("tags", {}).get("owner") == "adr-tests"
                _log(LogKind.OK, "group_b created with display name + tags")

            with timed_step("Step 4 ❯ Show group"):
                show_cmd = f"iot adr ns group show -n {group_a} --ns {ns} -g {rg}"
                _log(LogKind.CMD, "az %s", show_cmd)
                shown = self.cmd(show_cmd).get_output_in_json()
                assert shown["name"] == group_a
                assert shown["properties"]["query"] == _TEST_QUERY
                _log(LogKind.OK, "group show roundtrip ok")

            with timed_step("Step 5 ❯ List groups"):
                list_cmd = f"iot adr ns group list --ns {ns} -g {rg}"
                _log(LogKind.CMD, "az %s", list_cmd)
                groups = self.cmd(list_cmd).get_output_in_json()
                assert isinstance(groups, list)
                names = {g["name"] for g in groups}
                assert group_a in names and group_b in names, (
                    f"missing groups in list: {names}"
                )
                _log(LogKind.OK, "list returned %d groups including both created", len(groups))

            with timed_step("Step 6 ❯ Delete one group, verify gone"):
                del_cmd = f"iot adr ns group delete -n {group_a} --ns {ns} -g {rg} -y"
                _log(LogKind.CMD, "az %s", del_cmd)
                self.cmd(del_cmd)

                _log(LogKind.CMD, "az %s  (expect failure)", show_cmd)
                self.cmd(show_cmd, expect_failure=True)

                groups_after = self.cmd(list_cmd).get_output_in_json()
                remaining = {g["name"] for g in groups_after}
                assert group_a not in remaining
                assert group_b in remaining
                _log(LogKind.OK, "group_a deleted, group_b remains")

            with timed_step("Step 7 ❯ Delete remaining group"):
                self.cmd(f"iot adr ns group delete -n {group_b} --ns {ns} -g {rg} -y")
                _log(LogKind.OK, "group_b deleted")

        finally:
            with timed_step("Cleanup ❯ Delete Namespace"):
                try:
                    self.cmd(f"iot adr ns delete -n {ns} -g {rg} -y")
                except Exception as e:
                    _log(LogKind.WARN, "namespace cleanup failed: %s", e)
