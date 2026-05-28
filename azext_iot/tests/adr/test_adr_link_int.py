# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Integration tests for ``iot adr ns link {hub|dps} {add|show|list|remove}``.

Contains two classes:

* ``TestADRLinkIdentityValidation`` — fast CLI-validation negative tests
  (namespace only; no Hub / DPS create).
* ``TestADRLinkLifecycle`` — end-to-end add/show/list/remove for both hub and
  dps link kinds against real Gen2 Hub + DPS (heavyweight, slowest).
"""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import (
    CUSTOM_POLICY_NAME,
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
    generate_dps_name,
    generate_hub_name,
    generate_identity_name,
)
from azext_iot.tests.generators import generate_generic_id


def _gen_link_name(prefix: str) -> str:
    return f"{prefix}{generate_generic_id()[:6]}"


# ---------- 1. Link command identity validation (no Hub/DPS required) ----------

@pytest.mark.usefixtures("set_cwd")
class TestADRLinkIdentityValidation(CaptureOutputLiveScenarioTest):
    """Validation-only: confirm the CLI rejects bad identity arg combinations
    before any ARM call is made. Uses bogus resource IDs because the request
    should fail at the parameter-validation layer.
    """

    def test_link_add_identity_validation(self):
        _log(LogKind.TEST, "test_link_add_identity_validation")
        rg = TEST_RG
        ns = generate_adr_namespace_name()
        link_name = _gen_link_name("hub")
        bogus_hub_id = (
            f"/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/{rg}"
            f"/providers/Microsoft.Devices/IotHubs/nonexistent-hub"
        )
        bogus_uami_id = (
            f"/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/{rg}"
            f"/providers/Microsoft.ManagedIdentity/userAssignedIdentities/nonexistent"
        )

        try:
            with timed_step("Step 1 ❯ Create namespace"):
                self.cmd(f"iot adr ns create -n {ns} -g {rg} --location {TEST_LOCATION}")

            with timed_step("Step 2 ❯ Reject add with no identity flag"):
                # Neither --mi-system-assigned nor --mi-user-assigned: must fail
                # at the validator stage with RequiredArgumentMissingError.
                no_id_cmd = (
                    f"iot adr ns link hub add -n {link_name} --ns {ns} -g {rg} "
                    f"--hub-resource-id {bogus_hub_id}"
                )
                _log(LogKind.CMD, "az %s  (expect failure)", no_id_cmd)
                self.cmd(no_id_cmd, expect_failure=True)
                _log(LogKind.OK, "rejected as expected")

            with timed_step("Step 3 ❯ Reject add with both identity flags"):
                # Both flags set: must fail with MutuallyExclusiveArgumentError.
                both_cmd = (
                    f"iot adr ns link hub add -n {link_name} --ns {ns} -g {rg} "
                    f"--hub-resource-id {bogus_hub_id} "
                    f"--mi-system-assigned --mi-user-assigned {bogus_uami_id}"
                )
                _log(LogKind.CMD, "az %s  (expect failure)", both_cmd)
                self.cmd(both_cmd, expect_failure=True)
                _log(LogKind.OK, "rejected as expected")

        finally:
            with timed_step("Cleanup ❯ Delete Namespace"):
                try:
                    self.cmd(f"iot adr ns delete -n {ns} -g {rg} -y")
                except Exception as e:
                    _log(LogKind.WARN, "namespace cleanup failed: %s", e)


# ---------- 2. Link lifecycle: Hub + DPS end-to-end (heavyweight) ----------

@pytest.mark.usefixtures("set_cwd")
class TestADRLinkLifecycle(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """End-to-end add/show/list/remove for both hub and dps link kinds.

    Reuses ``ADRHubInfraHelper.setup_full_infra`` to provision the namespace +
    Gen2 Hub + UAMI (so the namespace already has a system-assigned identity
    suitable for ``--mi-system-assigned``). DPS is added inline to keep the
    test self-contained.
    """

    def test_link_hub_and_dps_lifecycle(self):
        _log(LogKind.TEST, "test_link_hub_and_dps_lifecycle")
        rg = TEST_RG
        ns = generate_adr_namespace_name()
        hub_name = generate_hub_name()
        dps_name = generate_dps_name()
        identity_name = generate_identity_name()
        hub_link = _gen_link_name("hublink")
        dps_link = _gen_link_name("dpslink")

        try:
            infra = self.setup_full_infra(
                resource_group=rg,
                namespace_name=ns,
                hub_name=hub_name,
                identity_name=identity_name,
                policy_name=CUSTOM_POLICY_NAME,
            )
            hub_id = self.cmd(
                f"iot hub show -n {hub_name} -g {rg}"
            ).get_output_in_json()["id"]

            # ---------- Hub link CRUD ----------

            with timed_step("Hub link 1 ❯ Add (system-assigned identity)"):
                add_cmd = (
                    f"iot adr ns link hub add -n {hub_link} --ns {ns} -g {rg} "
                    f"--hub-resource-id {hub_id} --mi-system-assigned"
                )
                _log(LogKind.CMD, "az %s", add_cmd)
                added = self.cmd(add_cmd).get_output_in_json()
                # Provider normalizes the response into a flat dict with
                # 'name' + endpoint properties.
                assert added.get("name") == hub_link or added.get("resourceId") == hub_id
                _log(LogKind.OK, "hub link added")

            with timed_step("Hub link 2 ❯ Show"):
                show_cmd = f"iot adr ns link hub show -n {hub_link} --ns {ns} -g {rg}"
                _log(LogKind.CMD, "az %s", show_cmd)
                shown = self.cmd(show_cmd).get_output_in_json()
                assert shown["resourceId"] == hub_id
                identity = shown.get("inboundCallerIdentity", {})
                assert identity.get("type") == "SystemAssigned"
                _log(LogKind.OK, "hub link show roundtrip ok")

            with timed_step("Hub link 3 ❯ List"):
                list_cmd = f"iot adr ns link hub list --ns {ns} -g {rg}"
                _log(LogKind.CMD, "az %s", list_cmd)
                links = self.cmd(list_cmd).get_output_in_json()
                assert isinstance(links, list)
                assert hub_link in {entry["name"] for entry in links}
                _log(LogKind.OK, "hub link present in list (%d total)", len(links))

            with timed_step("Hub link 4 ❯ Remove"):
                _log(LogKind.CMD, "az iot adr ns link hub remove -n %s --ns %s -g %s -y",
                     hub_link, ns, rg)
                self.cmd(
                    f"iot adr ns link hub remove -n {hub_link} --ns {ns} -g {rg} -y"
                )
                self.cmd(show_cmd, expect_failure=True)
                links_after = self.cmd(list_cmd).get_output_in_json()
                assert hub_link not in {entry["name"] for entry in links_after}
                _log(LogKind.OK, "hub link removed")

            # ---------- DPS link CRUD ----------

            with timed_step("DPS setup ❯ Create DPS"):
                identity_resource_id = infra["identity_resource_id"]
                adr_resource_id = infra["adr_resource_id"]
                dps_cmd = (
                    f"iot dps create --name {dps_name} -g {rg} --location {TEST_LOCATION} "
                    f"--mi-user-assigned {identity_resource_id} "
                    f"--ns-resource-id {adr_resource_id} "
                    f"--ns-identity-id {identity_resource_id}"
                )
                _log(LogKind.CMD, "az %s", dps_cmd)
                dps = self.cmd(dps_cmd).get_output_in_json()
                dps_id = dps["id"]
                _log(LogKind.RESULT, "dps id=%s", dps_id)

            with timed_step("DPS link 1 ❯ Add (system-assigned identity)"):
                add_cmd = (
                    f"iot adr ns link dps add -n {dps_link} --ns {ns} -g {rg} "
                    f"--dps-resource-id {dps_id} --mi-system-assigned"
                )
                _log(LogKind.CMD, "az %s", add_cmd)
                self.cmd(add_cmd)
                _log(LogKind.OK, "dps link added")

            with timed_step("DPS link 2 ❯ Show + List"):
                show_dps = f"iot adr ns link dps show -n {dps_link} --ns {ns} -g {rg}"
                shown = self.cmd(show_dps).get_output_in_json()
                assert shown["resourceId"] == dps_id
                assert shown.get("inboundCallerIdentity", {}).get("type") == "SystemAssigned"

                list_dps = f"iot adr ns link dps list --ns {ns} -g {rg}"
                links = self.cmd(list_dps).get_output_in_json()
                assert dps_link in {entry["name"] for entry in links}
                _log(LogKind.OK, "dps link present in show + list")

            with timed_step("DPS link 3 ❯ Remove"):
                self.cmd(
                    f"iot adr ns link dps remove -n {dps_link} --ns {ns} -g {rg} -y"
                )
                self.cmd(show_dps, expect_failure=True)
                _log(LogKind.OK, "dps link removed")

        finally:
            with timed_step("Cleanup ❯ Delete Hub + DPS + Namespace + UAMI"):
                self.cleanup_full_infra(
                    resource_group=rg,
                    hub_name=hub_name,
                    namespace_name=ns,
                    identity_name=identity_name,
                    dps_name=dps_name,
                )
