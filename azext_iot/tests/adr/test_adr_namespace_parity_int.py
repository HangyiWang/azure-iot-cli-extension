# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Namespace identity and management-endpoint integration coverage."""

import json
import os
import shlex

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._log import LogKind, _log
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)
from azext_iot.tests.generators import generate_generic_id


MANAGEMENT_ENDPOINT = {
    "endpointType": os.getenv("azext_iot_adr_management_endpoint_type"),
    "address": os.getenv("azext_iot_adr_management_endpoint_address"),
    "scopeId": os.getenv("azext_iot_adr_management_endpoint_scope_id"),
    "resourceId": os.getenv("azext_iot_adr_management_endpoint_resource_id"),
}
HAS_MANAGEMENT_ENDPOINT = all(MANAGEMENT_ENDPOINT.values())


def _create_namespace(test, namespace_name: str) -> None:
    test.cmd(
        f"iot adr ns create -n {namespace_name} -g {TEST_RG} "
        f"--location {TEST_LOCATION}"
    )


def _cleanup_namespace(test, namespace_name: str) -> None:
    try:
        test.cmd(
            f"iot adr ns delete -n {namespace_name} -g {TEST_RG} --yes"
        )
    except Exception as error:  # noqa: BLE001 - cleanup is best-effort
        _log(LogKind.WARN, "Cleanup failed: %s", error)


@pytest.mark.usefixtures("set_cwd")
class TestADRNamespaceIdentityParity(CaptureOutputLiveScenarioTest):
    def test_namespace_identity_assign_remove_show(self):
        namespace_name = generate_adr_namespace_name()
        missing_namespace = f"missing{generate_generic_id()[:8]}"

        try:
            _create_namespace(self, namespace_name)

            identity = self.cmd(
                f"iot adr ns identity show -n {namespace_name} -g {TEST_RG}"
            ).get_output_in_json()
            assert "SystemAssigned" in identity["type"]

            removed = self.cmd(
                f"iot adr ns identity remove -n {namespace_name} "
                f"-g {TEST_RG} --system true"
            ).get_output_in_json()
            assert removed["type"] == "None"

            assigned = self.cmd(
                f"iot adr ns identity assign -n {namespace_name} "
                f"-g {TEST_RG} --system true"
            ).get_output_in_json()
            assert assigned["type"] == "SystemAssigned"

            shown = self.cmd(
                f"iot adr ns identity show -n {namespace_name} -g {TEST_RG}"
            ).get_output_in_json()
            assert shown["type"] == "SystemAssigned"

            updated = self.cmd(
                f"iot adr ns update -n {namespace_name} -g {TEST_RG} "
                "--management-endpoints '{}'"
            ).get_output_in_json()
            management = (updated.get("properties") or {}).get("management") or {}
            assert management.get("endpoints") in ({}, None)

            endpoints = self.cmd(
                f"iot adr ns management-endpoint list --ns {namespace_name} "
                f"-g {TEST_RG}"
            ).get_output_in_json()
            assert endpoints == []
            self.cmd(
                "iot adr ns management-endpoint show -n missing "
                f"--ns {namespace_name} -g {TEST_RG}",
                expect_failure=True,
            )
            self.cmd(
                f"iot adr ns identity show -n {missing_namespace} -g {TEST_RG}",
                expect_failure=True,
            )
        finally:
            _cleanup_namespace(self, namespace_name)


@pytest.mark.skipif(
    not HAS_MANAGEMENT_ENDPOINT,
    reason=(
        "Set all azext_iot_adr_management_endpoint_* environment variables "
        "to run management-endpoint lifecycle coverage."
    ),
)
@pytest.mark.usefixtures("set_cwd")
class TestADRNamespaceManagementEndpointParity(CaptureOutputLiveScenarioTest):
    def test_management_endpoint_set_show_list_and_direct_update(self):
        namespace_name = generate_adr_namespace_name()
        endpoint_name = f"endpoint{generate_generic_id()[:8]}"

        try:
            _create_namespace(self, namespace_name)

            self.cmd(
                f"iot adr ns management-endpoint set -n {endpoint_name} "
                f"--ns {namespace_name} -g {TEST_RG} "
                f"--endpoint-type {shlex.quote(MANAGEMENT_ENDPOINT['endpointType'])} "
                f"--address {shlex.quote(MANAGEMENT_ENDPOINT['address'])} "
                f"--scope-id {shlex.quote(MANAGEMENT_ENDPOINT['scopeId'])} "
                f"--resource-id {shlex.quote(MANAGEMENT_ENDPOINT['resourceId'])}"
            )

            shown = self.cmd(
                f"iot adr ns management-endpoint show -n {endpoint_name} "
                f"--ns {namespace_name} -g {TEST_RG}"
            ).get_output_in_json()
            assert shown["name"] == endpoint_name
            assert shown["resourceId"].casefold() == (
                MANAGEMENT_ENDPOINT["resourceId"].casefold()
            )

            listed = self.cmd(
                f"iot adr ns management-endpoint list --ns {namespace_name} "
                f"-g {TEST_RG}"
            ).get_output_in_json()
            assert endpoint_name in [endpoint["name"] for endpoint in listed]

            endpoint_map = {endpoint_name: MANAGEMENT_ENDPOINT}
            updated = self.cmd(
                f"iot adr ns update -n {namespace_name} -g {TEST_RG} "
                f"--management-endpoints "
                f"{shlex.quote(json.dumps(endpoint_map))}"
            ).get_output_in_json()
            endpoints = updated["properties"]["management"]["endpoints"]
            assert endpoint_name in endpoints
        finally:
            _cleanup_namespace(self, namespace_name)
