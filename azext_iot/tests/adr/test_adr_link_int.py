# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR link integration tests (P2/P3/P4).

Validates the namespace-linking surface exposed as ``iot adr ns link ...``:

* ``link dps add / update / show / list`` (P3); ``remove`` is rejected by design
* ``link hub add / update / show / list`` (P2); ``remove`` is rejected by design — including DPS-first ordering
* ``link add`` bundled Hub+DPS PATCH in a single round trip (P4)

These tests require real Hub and DPS resources to be linked to a real ADR
namespace, so they re-use :class:`ADRHubInfraHelper` to provision the full
infrastructure once per test class and exercise the link CLI surface against
it. The Hub created by ``setup_full_infra`` already links itself to the ADR
namespace via the ``--ns-resource-id`` / ``--ns-identity-id`` flags during
``iot hub create``; we do **not** drive ``ns create`` to attach the Hub.

What is intentionally NOT covered here (covered by unit tests):
- DPS-first ordering reject (``test_hub_add_rejects_when_no_dps_linked``)
- One-DPS-per-namespace cap rejection
- MI mutually-exclusive rejection
"""

import time

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import (
    TEST_RG,
    generate_adr_namespace_name,
    generate_dps_name,
    generate_hub_name,
    generate_identity_name,
)


@pytest.mark.usefixtures("set_cwd")
class TestADRLinkLifecycle(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """End-to-end lifecycle of namespace-side Hub and DPS link entries.

    The flow follows the design's enforced DPS-first ordering:

    1. Setup: provision ADR + UAMI + Hub (Hub auto-links to ADR via ``iot hub create``)
    2. Setup: create a standalone DPS for the namespace to link
    3. ``link dps add`` to attach the DPS
    4. ``link hub add`` to attach a second Hub messaging endpoint (validates DPS-first
       ordering passes once a DPS is present)
    5. Exercise ``show`` / ``list`` / ``update`` on both endpoint types
    6. ``link hub remove`` and ``link dps remove`` (both must fail with the
       'not supported by design' error — the namespace cleanup path is the
       only way to remove the link entries)
    """

    def test_adr_link_lifecycle(self):
        _log(LogKind.TEST, "test_adr_link_lifecycle")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        primary_hub = generate_hub_name()  # auto-linked at hub-create time
        secondary_hub = generate_hub_name()  # linked via `link hub add`
        dps_name = generate_dps_name()
        identity_name = generate_identity_name()

        secondary_endpoint = "secondary"
        dps_endpoint = "dps-primary"

        try:
            infra = self.setup_full_infra(
                resource_group=rg,
                namespace_name=namespace_name,
                hub_name=primary_hub,
                identity_name=identity_name,
                use_default_policy=True,
            )
            identity_resource_id = infra["identity_resource_id"]

            # The Hub created by setup_full_infra is linked via `iot hub create
            # --ns-resource-id` which writes a hub-side reference. The namespace's
            # `properties.messaging.endpoints` collection is what `iot adr ns link
            # hub *` manipulates and is intended to grow via the link surface, so
            # we don't make any assumptions about the auto-linked endpoint name —
            # the link tests add their own endpoints explicitly.

            # Step 1: link DPS (P3) — DPS-first ordering means this must
            # succeed before any `link hub add`.
            with timed_step("Step 1 ❯ link dps add"):
                cmd = (
                    f"iot dps create --name {dps_name} -g {rg} "
                    f"--location {infra['adr_resource_id'].split('/')[-3]} "
                    f"--mi-user-assigned {identity_resource_id}"
                )
                _log(LogKind.CMD, "az %s", cmd)
                self.cmd(cmd)
                _log(LogKind.RESULT, "DPS '%s' created", dps_name)

                dps_show = self.cmd(f"iot dps show --name {dps_name} -g {rg}").get_output_in_json()
                dps_id = dps_show["id"]
                _log(LogKind.RESULT, "dps_id=%s", dps_id)

                add_cmd = (
                    f"iot adr ns link dps add --ns {namespace_name} -g {rg} "
                    f"-n {dps_endpoint} --dps-id {dps_id} "
                    f"--mi-user-assigned {identity_resource_id}"
                )
                _log(LogKind.CMD, "az %s", add_cmd)
                self.cmd(add_cmd)
                _log(LogKind.OK, "DPS link '%s' created", dps_endpoint)

            with timed_step("Step 2 ❯ link dps show / list"):
                shown = self.cmd(
                    f"iot adr ns link dps show --ns {namespace_name} -g {rg} -n {dps_endpoint}"
                ).get_output_in_json()
                assert shown.get("name") == dps_endpoint or shown.get("endpointName") == dps_endpoint, (
                    f"link dps show did not surface name field: {shown}"
                )
                _log(LogKind.OK, "DPS link visible on namespace")

                listed = self.cmd(
                    f"iot adr ns link dps list --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                assert isinstance(listed, list) and len(listed) == 1, (
                    f"Expected exactly one DPS link, got {listed}"
                )
                _log(LogKind.OK, "DPS list returned 1 entry")

            # Step 3: link hub (P2) — should now succeed since a DPS is linked.
            with timed_step("Step 3 ❯ link hub add (DPS-first satisfied)"):
                # Create a second Hub Gen2 (lightweight — no namespace link, no MI)
                hub_cmd = (
                    f"iot hub create -n {secondary_hub} -g {rg} --sku GEN2 "
                    f"--mi-user-assigned {identity_resource_id}"
                )
                _log(LogKind.CMD, "az %s", hub_cmd)
                hub = self.cmd(hub_cmd).get_output_in_json()
                hub_id = hub["id"]
                _log(LogKind.RESULT, "Secondary Hub '%s' created (id=%s)", secondary_hub, hub_id)

                add_cmd = (
                    f"iot adr ns link hub add --ns {namespace_name} -g {rg} "
                    f"-n {secondary_endpoint} --hub-id {hub_id} "
                    f"--mi-user-assigned {identity_resource_id} "
                    f"--availability Available --weight 1"
                )
                _log(LogKind.CMD, "az %s", add_cmd)
                self.cmd(add_cmd)
                _log(LogKind.OK, "Hub link '%s' created", secondary_endpoint)

            with timed_step("Step 4 ❯ link hub show / list"):
                shown = self.cmd(
                    f"iot adr ns link hub show --ns {namespace_name} -g {rg} -n {secondary_endpoint}"
                ).get_output_in_json()
                assert (
                    shown.get("name") == secondary_endpoint
                    or shown.get("endpointName") == secondary_endpoint
                ), f"link hub show did not surface name field: {shown}"
                _log(LogKind.OK, "Hub link visible on namespace")

                listed = self.cmd(
                    f"iot adr ns link hub list --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                assert isinstance(listed, list), f"Expected list, got {type(listed)}"
                hub_names = {
                    h.get("name") or h.get("endpointName") for h in listed
                }
                assert secondary_endpoint in hub_names, (
                    f"Hub link '{secondary_endpoint}' missing from list: {hub_names}"
                )
                _log(LogKind.OK, "Hub list returned %d entry/entries", len(listed))

            with timed_step("Step 5 ❯ link hub update (partial patch)"):
                # Flip availability to Unavailable and bump weight
                update_cmd = (
                    f"iot adr ns link hub update --ns {namespace_name} -g {rg} "
                    f"-n {secondary_endpoint} --availability Unavailable --weight 5"
                )
                _log(LogKind.CMD, "az %s", update_cmd)
                self.cmd(update_cmd)
                updated = self.cmd(
                    f"iot adr ns link hub show --ns {namespace_name} -g {rg} -n {secondary_endpoint}"
                ).get_output_in_json()
                # The shape of the surfaced provisioning fields depends on backend serialization;
                # accept either nested or flat representation defensively.
                prov = updated.get("properties", updated).get("provisioning") or updated.get(
                    "provisioning"
                ) or {}
                avail = prov.get("availability") or updated.get("availability")
                weight = prov.get("allocationWeight") or updated.get("allocationWeight")
                assert avail == "Unavailable", f"Availability not updated, saw {avail}"
                assert weight == 5, f"Weight not updated, saw {weight}"
                _log(LogKind.OK, "Hub link updated: availability=Unavailable, weight=5")

            with timed_step("Step 6 ❯ link dps update (rotate identity)"):
                update_cmd = (
                    f"iot adr ns link dps update --ns {namespace_name} -g {rg} "
                    f"-n {dps_endpoint} --mi-user-assigned {identity_resource_id}"
                )
                _log(LogKind.CMD, "az %s", update_cmd)
                self.cmd(update_cmd)
                _log(LogKind.OK, "DPS link identity rotated (idempotent)")

            with timed_step("Step 7 ❯ link hub remove (must fail by design)"):
                remove_cmd = (
                    f"iot adr ns link hub remove --ns {namespace_name} -g {rg} "
                    f"-n {secondary_endpoint} -y"
                )
                _log(LogKind.CMD, "az %s", remove_cmd)
                self.cmd(remove_cmd, expect_failure=True)
                # Verify endpoint is still present — the command must not mutate state
                listed = self.cmd(
                    f"iot adr ns link hub list --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                names = {h.get("name") or h.get("endpointName") for h in (listed or [])}
                assert secondary_endpoint in names, (
                    f"Hub link '{secondary_endpoint}' was unexpectedly removed: {names}"
                )
                _log(LogKind.OK, "Hub link remove rejected as designed; entry untouched")

            with timed_step("Step 8 ❯ link dps remove (must fail by design)"):
                remove_cmd = (
                    f"iot adr ns link dps remove --ns {namespace_name} -g {rg} "
                    f"-n {dps_endpoint} -y"
                )
                _log(LogKind.CMD, "az %s", remove_cmd)
                self.cmd(remove_cmd, expect_failure=True)
                listed = self.cmd(
                    f"iot adr ns link dps list --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                names = {d.get("name") or d.get("endpointName") for d in (listed or [])}
                assert dps_endpoint in names, (
                    f"DPS link '{dps_endpoint}' was unexpectedly removed: {names}"
                )
                _log(LogKind.OK, "DPS link remove rejected as designed; entry untouched")

            _log(LogKind.OK, "Link lifecycle passed")

        finally:
            self.cleanup_full_infra(
                resource_group=rg,
                hub_name=primary_hub,
                namespace_name=namespace_name,
                identity_name=identity_name,
                dps_name=dps_name,
            )
            # Best-effort cleanup of the secondary Hub
            with timed_step("Cleanup ❯ Delete secondary Hub"):
                try:
                    self.cmd(f"iot hub delete -n {secondary_hub} -g {rg}")
                    _log(LogKind.RESULT, "Secondary Hub deleted")
                except Exception as e:
                    _log(LogKind.WARN, "Secondary Hub cleanup failed: %s", e)


@pytest.mark.usefixtures("set_cwd")
class TestADRLinkBundledAdd(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """``iot adr ns link add`` bundled Hub+DPS in one PATCH (P4).

    Tests the single round-trip variant that links both a Hub messaging endpoint
    and a DPS provisioning endpoint at once, with the DPS entry serialized first
    to satisfy the DPS-first ordering constraint server-side.
    """

    def test_adr_link_bundled_add(self):
        _log(LogKind.TEST, "test_adr_link_bundled_add")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        hub_name = generate_hub_name()
        dps_name = generate_dps_name()
        identity_name = generate_identity_name()

        try:
            # We need a UAMI, namespace, AND a separately created Hub and DPS to
            # link. We deliberately do NOT use setup_full_infra here because we
            # want the namespace to start with zero linked endpoints so we can
            # observe the bundled add adding both at once.
            from azext_iot.tests.adr.conftest import TEST_LOCATION

            with timed_step("Setup 1/4 ❯ Create UAMI"):
                identity = self.cmd(
                    f"identity create -n {identity_name} -g {rg} --location {TEST_LOCATION}"
                ).get_output_in_json()
                identity_resource_id = identity["id"]
                identity_principal_id = identity["principalId"]
                subscription_id = self.cmd("account show").get_output_in_json()["id"]
                self.assign_hub_rp_contributor_role(subscription_id, rg)

            with timed_step("Setup 2/4 ❯ Create ADR namespace (no Hub link)"):
                ns = self.cmd(
                    f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION}"
                ).get_output_in_json()
                self.assign_adr_roles_to_identity(identity_principal_id, ns["id"])

            with timed_step("Setup 3/4 ❯ Create standalone Hub Gen2"):
                hub = self.cmd(
                    f"iot hub create -n {hub_name} -g {rg} --sku GEN2 --location {TEST_LOCATION} "
                    f"--mi-user-assigned {identity_resource_id}"
                ).get_output_in_json()
                hub_id = hub["id"]

            with timed_step("Setup 4/4 ❯ Create standalone DPS"):
                dps = self.cmd(
                    f"iot dps create --name {dps_name} -g {rg} --location {TEST_LOCATION} "
                    f"--mi-user-assigned {identity_resource_id}"
                ).get_output_in_json()
                dps_id = dps["id"]

            # Allow role assignments to propagate
            time.sleep(30)

            with timed_step("Step 1 ❯ link add (bundled Hub + DPS in one PATCH)"):
                bundled_cmd = (
                    f"iot adr ns link add --ns {namespace_name} -g {rg} "
                    f"--hub-name primary --hub-id {hub_id} "
                    f"--hub-mi-user-assigned {identity_resource_id} "
                    f"--hub-availability Available --hub-weight 1 "
                    f"--dps-name dps-primary --dps-id {dps_id} "
                    f"--dps-mi-user-assigned {identity_resource_id}"
                )
                _log(LogKind.CMD, "az %s", bundled_cmd)
                self.cmd(bundled_cmd)
                _log(LogKind.OK, "Bundled link add succeeded")

            with timed_step("Step 2 ❯ Verify both endpoints landed"):
                hubs = self.cmd(
                    f"iot adr ns link hub list --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                dpss = self.cmd(
                    f"iot adr ns link dps list --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                assert len(hubs) == 1, f"Expected 1 hub link, got {hubs}"
                assert len(dpss) == 1, f"Expected 1 DPS link, got {dpss}"
                _log(LogKind.OK, "Bundled add produced both endpoints")

        finally:
            self.cleanup_full_infra(
                resource_group=rg,
                hub_name=hub_name,
                namespace_name=namespace_name,
                identity_name=identity_name,
                dps_name=dps_name,
            )
