# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR group integration tests (P5).

Covers the ``iot adr ns group`` surface end-to-end:

* CRUD: create / show / list / update / delete
* ``refresh`` (long-running membership refresh)
* ``show-members`` and ``count`` (synchronous member preview)
* ``wait`` (LRO polling)
* Cascade-delete semantics from §2.2 of the design:
  - clean cascade (group has a referencing job in a terminal state)
  - hard-block cascade (group has a referencing job with an in-flight run
    or a non-terminal provisioningState)

Groups do not require any Hub/DPS infrastructure; they live entirely under
``Microsoft.DeviceRegistry/namespaces/{ns}/groups/{name}`` and only need an
ADR namespace to exist. We keep the namespace lightweight (no credential, no
policy) since group operations do not exercise the credential surface.
"""

import time

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr._log import LogKind, _log, timed_step
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)
from azext_iot.tests.generators import generate_generic_id


def _generate_group_name() -> str:
    # Service constraints: 3-63 chars, ``^[a-z0-9][a-z0-9-]*[a-z0-9]$``.
    return f"testgrp{generate_generic_id()[:8]}"


def _generate_job_name() -> str:
    return f"testjob{generate_generic_id()[:8]}"


@pytest.mark.usefixtures("set_cwd")
class TestADRGroupLifecycle(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """End-to-end CRUD + refresh + show-members + count + wait + delete."""

    def test_adr_group_lifecycle(self):
        _log(LogKind.TEST, "test_adr_group_lifecycle")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        group_name = _generate_group_name()

        try:
            with timed_step("Setup ❯ Create ADR namespace (no credential)"):
                self.cmd(
                    f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION}"
                )
                _log(LogKind.RESULT, "namespace=%s", namespace_name)

            with timed_step("Step 1 ❯ group create (minimal)"):
                created = self.cmd(
                    f"iot adr ns group create -n {group_name} --ns {namespace_name} -g {rg} "
                    f"--query-string \"SELECT * FROM devices\""
                ).get_output_in_json()
                assert created["name"] == group_name
                assert created["properties"]["provisioningState"] == "Succeeded"
                _log(LogKind.OK, "group created: %s", group_name)

            with timed_step("Step 2 ❯ group show / list"):
                shown = self.cmd(
                    f"iot adr ns group show -n {group_name} --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                assert shown["name"] == group_name
                listed = self.cmd(
                    f"iot adr ns group list --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                assert isinstance(listed, list)
                assert group_name in [g["name"] for g in listed]
                _log(LogKind.OK, "group visible in show + list")

            with timed_step("Step 3 ❯ group update (display name + description + tags)"):
                updated = self.cmd(
                    f"iot adr ns group update -n {group_name} --ns {namespace_name} -g {rg} "
                    f"--display-name 'Test group' --description 'created by int test' "
                    f"--tags env=ci owner=adr-tests"
                ).get_output_in_json()
                assert updated["properties"]["provisioningState"] == "Succeeded"
                assert updated["properties"].get("displayName") == "Test group"
                assert updated["properties"].get("description") == "created by int test"
                assert updated["tags"]["env"] == "ci"
                _log(LogKind.OK, "group fields updated")

            with timed_step("Step 4 ❯ group update (tags-only replacement)"):
                updated = self.cmd(
                    f"iot adr ns group update -n {group_name} --ns {namespace_name} -g {rg} "
                    f"--tags purpose=p5-int"
                ).get_output_in_json()
                # Tags PATCH replaces, doesn't merge.
                assert updated["tags"]["purpose"] == "p5-int"
                assert "env" not in updated.get("tags", {})
                _log(LogKind.OK, "tags replaced")

            with timed_step("Step 5 ❯ group refresh (LRO)"):
                self.cmd(
                    f"iot adr ns group refresh -n {group_name} --ns {namespace_name} -g {rg}"
                )
                _log(LogKind.OK, "refresh succeeded")

            with timed_step("Step 6 ❯ group show-members (≤10) + count"):
                # Group membership starts empty; we just verify the SDK shape is
                # unwrapped correctly by the provider (returns [] not a dict).
                members = self.cmd(
                    f"iot adr ns group show-members -n {group_name} --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                assert isinstance(members, list), f"members must be a list, got {type(members)}"
                _log(LogKind.RESULT, "members=%d", len(members))

                count_resp = self.cmd(
                    f"iot adr ns group count -n {group_name} --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                # count provider returns int; CLI core may wrap or pass through.
                count = count_resp if isinstance(count_resp, int) else int(count_resp or 0)
                assert count >= 0
                _log(LogKind.RESULT, "count=%d", count)

            with timed_step("Step 7 ❯ group wait --created"):
                self.cmd(
                    f"iot adr ns group wait -n {group_name} --ns {namespace_name} -g {rg} --created"
                )
                _log(LogKind.OK, "wait --created returned")

            with timed_step("Step 8 ❯ group delete (no referencing jobs)"):
                self.cmd(
                    f"iot adr ns group delete -n {group_name} --ns {namespace_name} -g {rg} -y"
                )
                # Verify gone
                self.cmd(
                    f"iot adr ns group show -n {group_name} --ns {namespace_name} -g {rg}",
                    expect_failure=True,
                )
                _log(LogKind.OK, "group deleted")

        finally:
            self.cleanup_namespace(namespace_name, rg)


@pytest.mark.usefixtures("set_cwd")
class TestADRGroupCascadeDelete(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Cascade-delete behavior on ``group delete``.

    Verifies the two paths from design §2.2:

    * **Clean cascade**: a referencing job in a terminal ``provisioningState``
      with no in-flight runs is sequentially deleted before the group's own
      delete proceeds.
    * **Hard block**: a referencing job whose ``provisioningState`` is still
      in the ``JOB_ACTIVE_PROVISIONING_STATES`` set (``Accepted`` / ``Running``
      / etc.) prevents the entire operation and raises with a per-job
      blocking reason; nothing is deleted.
    """

    def test_adr_group_cascade_delete_clean(self):
        """Group has a referencing job in a terminal state → cascade succeeds."""
        _log(LogKind.TEST, "test_adr_group_cascade_delete_clean")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        group_name = _generate_group_name()
        job_name = _generate_job_name()

        try:
            with timed_step("Setup ❯ Namespace + Group"):
                self.cmd(
                    f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION}"
                )
                self.cmd(
                    f"iot adr ns group create -n {group_name} --ns {namespace_name} -g {rg} "
                    f"--query-string \"SELECT * FROM devices\""
                )

            with timed_step("Step 1 ❯ Create a referencing job"):
                self.cmd(
                    f"iot adr ns job create -n {job_name} --ns {namespace_name} -g {rg} "
                    f"--target-group-name {group_name} "
                    f"--update-id-provider Contoso --update-id-name test-fw --update-id-version 1.0.0"
                )
                # Wait for the job to reach a terminal provisioningState
                # (Succeeded). The job is NOT scheduled, so no runs are spawned.
                for poll in range(30):
                    job = self.cmd(
                        f"iot adr ns job show -n {job_name} --ns {namespace_name} -g {rg}"
                    ).get_output_in_json()
                    state = job["properties"]["provisioningState"]
                    if state in {"Succeeded", "Failed", "Canceled"}:
                        _log(LogKind.RESULT, "job provisioningState=%s (poll %d)", state, poll + 1)
                        break
                    time.sleep(5)
                else:
                    pytest.fail(f"Job did not reach terminal state, last={state}")
                assert state == "Succeeded", f"Expected Succeeded, got {state}"

            with timed_step("Step 2 ❯ group delete (clean cascade)"):
                # Should: warn-list the job, cascade-delete it, then delete the group.
                self.cmd(
                    f"iot adr ns group delete -n {group_name} --ns {namespace_name} -g {rg} -y"
                )
                # Verify both group AND job are gone
                self.cmd(
                    f"iot adr ns group show -n {group_name} --ns {namespace_name} -g {rg}",
                    expect_failure=True,
                )
                self.cmd(
                    f"iot adr ns job show -n {job_name} --ns {namespace_name} -g {rg}",
                    expect_failure=True,
                )
                _log(LogKind.OK, "Cascade deleted job + group")

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_adr_group_cascade_delete_blocked_by_active_job(self):
        """Hard-block: group has a referencing job with an active provisioningState.

        Strategy: Issue ``group delete`` immediately after ``job create``
        returns asynchronously (``--no-wait``). The job will still be in
        ``Accepted`` / ``Creating`` provisioningState, which is in the
        ``JOB_ACTIVE_PROVISIONING_STATES`` set, so ``group delete`` should
        raise an ``ArgumentUsageError`` before issuing any DELETE.

        Note: this race depends on the backend taking measurable time to
        transition out of Accepted. If the backend completes the job before
        we issue the group delete, this test may exit the assertion path —
        in which case we fall through and clean up.
        """
        _log(LogKind.TEST, "test_adr_group_cascade_delete_blocked_by_active_job")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        group_name = _generate_group_name()
        job_name = _generate_job_name()

        try:
            with timed_step("Setup ❯ Namespace + Group"):
                self.cmd(
                    f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION}"
                )
                self.cmd(
                    f"iot adr ns group create -n {group_name} --ns {namespace_name} -g {rg} "
                    f"--query-string \"SELECT * FROM devices\""
                )

            with timed_step("Step 1 ❯ Create job (--no-wait) so prov state is still Accepted"):
                self.cmd(
                    f"iot adr ns job create -n {job_name} --ns {namespace_name} -g {rg} "
                    f"--target-group-name {group_name} "
                    f"--update-id-provider Contoso --update-id-name test-fw "
                    f"--update-id-version 1.0.0 --no-wait"
                )
                job = self.cmd(
                    f"iot adr ns job show -n {job_name} --ns {namespace_name} -g {rg}"
                ).get_output_in_json()
                state = job["properties"].get("provisioningState")
                _log(LogKind.RESULT, "job provisioningState immediately after create=%s", state)

            with timed_step("Step 2 ❯ group delete must HARD-BLOCK"):
                # The provider raises ArgumentUsageError; CLI exits non-zero
                # and surfaces a per-job blocking reason in the message.
                if state in {"Succeeded", "Failed", "Canceled"}:
                    # Backend was too fast; skip the assertion path.
                    pytest.skip(
                        f"Job already in terminal state ({state}); cannot exercise hard-block path."
                    )
                self.cmd(
                    f"iot adr ns group delete -n {group_name} --ns {namespace_name} -g {rg} -y",
                    expect_failure=True,
                )
                # Verify NOTHING was deleted: both group and job still present.
                self.cmd(
                    f"iot adr ns group show -n {group_name} --ns {namespace_name} -g {rg}"
                )
                self.cmd(
                    f"iot adr ns job show -n {job_name} --ns {namespace_name} -g {rg}"
                )
                _log(LogKind.OK, "Hard-block succeeded: nothing was deleted")

        finally:
            # Wait out the active job before namespace cleanup
            for _ in range(30):
                try:
                    job = self.cmd(
                        f"iot adr ns job show -n {job_name} --ns {namespace_name} -g {rg}"
                    ).get_output_in_json()
                    if job["properties"]["provisioningState"] in {
                        "Succeeded", "Failed", "Canceled"
                    }:
                        break
                except Exception:
                    break
                time.sleep(5)
            self.cleanup_namespace(namespace_name, rg)
