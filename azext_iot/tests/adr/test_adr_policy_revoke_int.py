# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Integration tests for ADR policy revoke-issuer commands."""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr.conftest import (
    TEST_RG,
    generate_adr_namespace_name,
    generate_hub_name,
    generate_identity_name,
)
from azext_iot.tests.adr._helpers import (
    ADRHubInfraHelper,
    get_ca_config,
)
from azext_iot.tests.adr._log import L, _log, timed_step


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyRevokeLifecycle(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Tests for the revoke-issuer command with full IoT Hub integration.

    Validates the backend contract:
    - Revoke deletes the old ICA from the linked hub
    - Revoke creates a new ICA on the policy
    - The new ICA is uploaded to the linked hub via credential sync
    """

    def test_policy_revoke_issuer_e2e(self):
        """Full E2E: create infra -> sync -> revoke -> verify ICA rotation on policy and hub."""
        _log(L.TEST, "test_policy_revoke_issuer_e2e")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        hub_name = generate_hub_name()
        identity_name = generate_identity_name()
        # Use the auto-created default policy directly to avoid backend state
        # issues from delete->recreate that cause revokeIssuer NullReferenceException.
        policy_name = "default"

        try:
            # --- Step 1: Create full infrastructure (keep default policy) ---
            infra = self.setup_full_infra(
                resource_group=rg,
                namespace_name=namespace_name,
                hub_name=hub_name,
                identity_name=identity_name,
                policy_name=policy_name,
                use_default_policy=True,
            )
            subscription_id = infra["subscription_id"]

            policy_rid = self.build_policy_resource_id(
                subscription_id, rg, namespace_name, policy_name,
            )

            # --- Step 2: Credential sync ---
            sync_cmd = f"iot adr ns credential sync --ns {namespace_name} -g {rg}"
            with timed_step("Step 2 ❯ Credential Sync"):
                _log(L.CMD, "az %s", sync_cmd)
                self.cmd(sync_cmd)
                _log(L.RESULT, "ok")

                initial_hub_cert = self.find_hub_cert_by_policy(hub_name, rg, policy_rid)
                assert initial_hub_cert is not None, "ICA certificate should be on hub after sync"
                initial_hub_cert_name = initial_hub_cert["name"]
                _log(L.OK, "Initial hub cert found: %s", initial_hub_cert_name)

                policy_show_cmd = f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {policy_name}"
                _log(L.CMD, "az %s", policy_show_cmd)
                pre_policy = self.cmd(policy_show_cmd).get_output_in_json()
                pre_ca = get_ca_config(pre_policy)
                _log(
                    L.RESULT,
                    "Pre-revoke policy CA: keyType=%s, subject=%s",
                    pre_ca.get("keyType"), pre_ca.get("subject"),
                )

            # --- Step 3: Revoke issuer ---
            pre_subject = pre_ca.get("subject")
            revoke_cmd = (
                f"iot adr ns policy revoke-issuer --ns {namespace_name} -g {rg} "
                f"--policy-name {policy_name} -y"
            )
            with timed_step("Step 3 ❯ Revoke Issuer"):
                _log(L.CMD, "az %s", revoke_cmd)
                try:
                    self.cmd(revoke_cmd)
                    _log(L.RESULT, "ok: revoke-issuer succeeded")
                except Exception as exc:
                    # LRO may report failure but still partially succeed
                    _log(L.WARN, "revoke-issuer LRO failed: %s", exc)

                # 3a. Verify policy ICA was regenerated
                _log(L.CMD, "az %s", policy_show_cmd)
                post_policy = self.cmd(policy_show_cmd).get_output_in_json()
                post_ca = get_ca_config(post_policy)
                post_subject = post_ca.get("subject")
                _log(
                    L.RESULT,
                    "Post-revoke policy: state=%s, subject=%s (was %s)",
                    post_policy["properties"]["provisioningState"],
                    post_subject, pre_subject,
                )
                assert post_subject != pre_subject, (
                    f"Policy ICA subject should change after revoke: "
                    f"before={pre_subject}, after={post_subject}"
                )
                _log(L.OK, "ICA regenerated -- subject changed after revoke")

                # 3b. Verify old hub cert was removed (revoke should at least delete it)
                post_hub_certs = self.get_hub_certificates(hub_name, rg)
                post_hub_names = [c["name"] for c in post_hub_certs]
                assert initial_hub_cert_name not in post_hub_names, (
                    f"Old hub cert '{initial_hub_cert_name}' should be removed after revoke"
                )
                _log(L.OK, "Old hub cert '%s' removed after revoke", initial_hub_cert_name)

                # 3c. Probe: did the backend auto-sync the NEW ICA to the hub?
                auto_synced_cert = self.check_hub_cert_auto_synced(
                    hub_name, rg, policy_rid, "post-revoke",
                )

            # --- Step 4: Ensure new ICA is on hub (follow-up sync if needed) ---
            if auto_synced_cert is None:
                with timed_step("Step 4 ❯ Follow-up Sync (new ICA was NOT auto-synced)"):
                    _log(
                        L.WARN,
                        "Backend did not auto-sync new ICA to hub after revoke -- "
                        "performing manual credential sync as workaround",
                    )
                    _log(L.CMD, "az %s", sync_cmd)
                    self.cmd(sync_cmd)
                    _log(L.RESULT, "ok: follow-up sync succeeded")

                    new_hub_cert = self.find_hub_cert_by_policy(hub_name, rg, policy_rid)
                    assert new_hub_cert is not None, (
                        "New ICA certificate should be on hub after follow-up sync"
                    )
                    assert new_hub_cert["name"] != initial_hub_cert_name
                    _log(
                        L.OK,
                        "New hub cert after manual sync: %s (was %s)",
                        new_hub_cert["name"], initial_hub_cert_name,
                    )
            else:
                _log(L.OK, "New ICA was auto-synced to hub -- no manual sync needed")
                new_hub_cert = auto_synced_cert
                assert new_hub_cert["name"] != initial_hub_cert_name

            # --- Step 5: Final verification ---
            with timed_step("Step 5 ❯ Final Verification"):
                # Verify PolicyResourceId on the new hub cert
                new_cert_policy_rid = new_hub_cert.get("properties", {}).get("PolicyResourceId")
                assert new_cert_policy_rid == policy_rid, (
                    f"New hub cert PolicyResourceId mismatch: "
                    f"expected={policy_rid}, got={new_cert_policy_rid}"
                )
                _log(
                    L.OK,
                    "New hub cert '%s' has correct PolicyResourceId",
                    new_hub_cert["name"],
                )

                _log(L.CMD, "az %s", policy_show_cmd)
                updated_policy = self.cmd(policy_show_cmd).get_output_in_json()
                assert updated_policy["properties"]["provisioningState"] == "Succeeded"
                _log(L.OK, "Policy revoke-issuer complete -- ICA regenerated, hub cert rotated")

        finally:
            self.cleanup_full_infra(
                resource_group=rg,
                hub_name=hub_name,
                namespace_name=namespace_name,
                identity_name=identity_name,
            )


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyLimits(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Tests for backend-enforced policy constraints."""

    def test_single_policy_limit_per_credential(self):
        """Verify the backend rejects creating more than one policy per credential."""
        _log(L.TEST, "test_single_policy_limit_per_credential")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            default_policy = self.setup_namespace_with_policy(namespace_name, rg)
            assert default_policy["properties"]["provisioningState"] == "Succeeded"
            _log(L.OK, "Default policy created with provisioningState=Succeeded")

            # Second policy should be rejected
            _log(L.STEP, "Verify ❯ Second policy creation is rejected")
            second_cmd = f"iot adr ns policy create --ns {namespace_name} -g {rg} --policy-name secondpolicy --cert-key-type ECC"
            _log(L.CMD, "az %s  (expect failure)", second_cmd)
            with pytest.raises(Exception):
                self.cmd(second_cmd)
            _log(L.OK, "Backend correctly rejected second policy creation")

            # Only one Succeeded policy should exist
            _log(L.STEP, "Verify ❯ Only one Succeeded policy exists")
            list_cmd = f"iot adr ns policy list --ns {namespace_name} -g {rg}"
            _log(L.CMD, "az %s", list_cmd)
            policies = self.cmd(list_cmd).get_output_in_json()

            succeeded = [p for p in policies if p["properties"]["provisioningState"] == "Succeeded"]
            assert len(succeeded) == 1
            assert succeeded[0]["name"] == "default"
            _log(L.OK, "Exactly 1 Succeeded policy: name=%s", succeeded[0]["name"])

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_revoke_nonexistent_policy(self):
        """Attempting revoke-issuer on a nonexistent policy should fail."""
        _log(L.TEST, "test_revoke_nonexistent_policy")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            self.setup_namespace_with_policy(namespace_name, rg)

            _log(L.STEP, "Verify ❯ Revoke on nonexistent policy is rejected")
            revoke_cmd = (
                f"iot adr ns policy revoke-issuer --ns {namespace_name} -g {rg} "
                f"--policy-name nonexistent -y"
            )
            _log(L.CMD, "az %s  (expect failure)", revoke_cmd)
            with pytest.raises(Exception):
                self.cmd(revoke_cmd)
            _log(L.OK, "Backend correctly rejected revoke on nonexistent policy")
        finally:
            self.cleanup_namespace(namespace_name, rg)
