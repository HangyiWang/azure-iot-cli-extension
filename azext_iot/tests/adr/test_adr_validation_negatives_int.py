# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR client-side validation negatives (cross-surface).

Every scenario in this module exercises argument validation that the providers
perform *before* issuing any service round trip — required-argument guards,
mutually-exclusive identity flags, and the "not-yet-supported" UAMI rejection on
namespace outbound identity.

Because these commands fail client-side, they require neither pre-provisioned
ADR resources nor backend readiness: each ``self.cmd(...)`` is expected to fail
during command processing. They complement the lifecycle suites (happy paths)
by driving the rejection branches end-to-end through the CLI, mirroring the
provider unit tests at the command surface so the same lines are also covered
under integration.
"""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import TEST_LOCATION, TEST_RG


_UAMI_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/"
    "rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/uami"
)


@pytest.mark.usefixtures("set_cwd")
class TestADRValidationNegatives(CaptureOutputLiveScenarioTest):
    """Command-surface coverage of provider validation guards (no backend needed)."""

    def test_adr_validation_negatives(self):
        _log(LogKind.TEST, "test_adr_validation_negatives")
        rg = TEST_RG
        # Names need not resolve to real resources: each command fails during
        # argument validation, before the provider issues any service call.
        ns = "validation-ns-does-not-matter"

        # --- Namespace: outbound identity guards (resolved before the LRO) ---
        with timed_step("ns create ❯ outbound UAMI rejected (not yet supported)"):
            self.cmd(
                f"iot adr ns create -n {ns} -g {rg} --location {TEST_LOCATION} "
                f"--omi-ua {_UAMI_ID}",
                expect_failure=True,
            )
        with timed_step("ns create ❯ outbound SAMI + UAMI together rejected"):
            self.cmd(
                f"iot adr ns create -n {ns} -g {rg} --location {TEST_LOCATION} "
                f"--omi-sa --omi-ua {_UAMI_ID}",
                expect_failure=True,
            )

        # --- Certificate authority: update requires --tags ---
        with timed_step("ca update ❯ nothing-to-update rejected"):
            self.cmd(
                f"iot adr ns ca update -n myca --ns {ns} -g {rg}",
                expect_failure=True,
            )

        # --- Certificate policy: update requires --validity-days and/or --tags ---
        with timed_step("ca policy update ❯ nothing-to-update rejected"):
            self.cmd(
                f"iot adr ns ca policy update -n mypolicy --ca myca --ns {ns} -g {rg}",
                expect_failure=True,
            )

        # --- Adaptive device: update requires at least one mutable field ---
        with timed_step("adaptive-device update ❯ nothing-to-update rejected"):
            self.cmd(
                f"iot adr ns adaptive-device update -n mydev --ns {ns} -g {rg}",
                expect_failure=True,
            )

        _log(LogKind.OK, "All cross-surface validation negatives rejected client-side as designed")
