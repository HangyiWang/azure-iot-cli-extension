# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Integration tests for ADR policy revoke-issuer commands.

Requirements:
- Azure subscription with appropriate permissions
- Resource group specified in azext_iot_testrg environment variable
"""

import pytest
from knack.log import get_logger

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

logger = get_logger(__name__)


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyRevokeLifecycle(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Tests for the revoke-issuer command with full IoT Hub integration.

    Validates the backend contract:
    - Revoke deletes the old ICA from the linked hub
    - Revoke creates a new ICA on the policy
    - The new ICA is uploaded to the linked hub via credential sync
    """

    def test_policy_revoke_issuer_e2e(self):
        """Full E2E: create infra -> sync -> revoke -> verify ICA rotation on policy and hub.

        For standard (non-BYOR) policies, the revokeIssuer LRO should handle hub
        cert rotation internally.  However, a known backend bug causes the hub
        upload step to fail (NullReferenceException), so a follow-up credential
        sync is used to push the newly generated ICA to the hub.
        """
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

            # --- Step 2: Credential sync (pushes ICA cert to hub) ---
            # With --enable-credential-policy, sync should succeed on first attempt.
            logger.warning("[e2e] Running credential sync ...")
            self.cmd(
                f"iot adr ns credential sync --ns {namespace_name} -g {rg}"
            )
            logger.warning("[e2e] Credential sync succeeded")

            # Verify the ICA cert arrived on the hub
            pre_revoke_certs = self.get_hub_certificates(hub_name, rg)
            pre_revoke_cert_names = [c["name"] for c in pre_revoke_certs]
            logger.warning(
                "[e2e] Hub certs after sync (before revoke): count=%d, names=%s",
                len(pre_revoke_certs), pre_revoke_cert_names,
            )
            initial_hub_cert = self.find_hub_cert_by_policy(hub_name, rg, policy_rid)
            assert initial_hub_cert is not None, (
                "ICA certificate should be on hub after sync"
            )
            initial_hub_cert_name = initial_hub_cert["name"]
            logger.warning("[e2e] Initial hub cert: %s", initial_hub_cert_name)

            # Snapshot the initial policy CA config for comparison after revoke
            pre_policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {policy_name}"
            ).get_output_in_json()
            pre_ca = get_ca_config(pre_policy)
            logger.warning(
                "[e2e] Pre-revoke policy CA: keyType=%s, subject=%s",
                pre_ca.get("keyType"), pre_ca.get("subject"),
            )

            # --- Step 3: Revoke issuer ---
            # The revoke LRO internally: (a) generates new ICA, (b) deletes old
            # hub cert, (c) uploads new cert to hub.  Currently step (c) fails
            # with a NullReferenceException (GenericServerError), but (a) and (b)
            # still succeed — the policy subject changes and the old hub cert is
            # removed.  We detect this and run a follow-up sync to push the new
            # ICA to the hub.
            pre_subject = pre_ca.get("subject")
            logger.warning("[e2e] Calling revoke-issuer ...")
            try:
                self.cmd(
                    f"iot adr ns policy revoke-issuer --ns {namespace_name} -g {rg} "
                    f"--policy-name {policy_name} -y"
                )
                logger.warning("[e2e] revoke-issuer succeeded")
            except Exception as exc:
                # The LRO may report failure (GenericServerError) but still
                # partially succeed — continue to verify policy + hub state.
                logger.warning("[e2e] revoke-issuer LRO failed: %s", exc)

            # Check whether the revoke actually took effect (new ICA generated)
            post_policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} "
                f"--policy-name {policy_name}"
            ).get_output_in_json()
            post_ca = get_ca_config(post_policy)
            post_subject = post_ca.get("subject")
            logger.warning(
                "[e2e] Post-revoke policy: state=%s, subject=%s (was %s)",
                post_policy["properties"]["provisioningState"],
                post_subject, pre_subject,
            )
            assert post_subject != pre_subject, (
                f"Policy ICA subject should change after revoke: "
                f"before={pre_subject}, after={post_subject}"
            )
            logger.warning("[e2e] Revoke confirmed: ICA regenerated (subject changed)")

            # Check hub certs — the revoke LRO deletes the old cert but may
            # fail to upload the new one (GenericServerError).
            post_hub_certs = self.get_hub_certificates(hub_name, rg)
            post_hub_names = [c["name"] for c in post_hub_certs]
            logger.warning(
                "[e2e] Hub certs after revoke: count=%d, names=%s",
                len(post_hub_certs), post_hub_names,
            )
            assert initial_hub_cert_name not in post_hub_names, (
                f"Old hub cert '{initial_hub_cert_name}' should be removed after revoke"
            )

            # --- Step 4: Follow-up sync to push the new ICA to hub ---
            # The revoke LRO's hub-upload step is currently broken (backend bug),
            # so run a credential sync to push the newly generated ICA.
            if len(post_hub_certs) == 0:
                logger.warning(
                    "[e2e] Hub has 0 certs after revoke — running follow-up sync "
                    "to push new ICA ..."
                )
                self.cmd(
                    f"iot adr ns credential sync --ns {namespace_name} -g {rg}"
                )
                logger.warning("[e2e] Follow-up sync succeeded")

                # Verify new cert appeared on hub
                final_certs = self.get_hub_certificates(hub_name, rg)
                final_names = [c["name"] for c in final_certs]
                logger.warning(
                    "[e2e] Hub certs after follow-up sync: count=%d, names=%s",
                    len(final_certs), final_names,
                )
                new_hub_cert = self.find_hub_cert_by_policy(hub_name, rg, policy_rid)
                assert new_hub_cert is not None, (
                    "New ICA certificate should be on hub after follow-up sync"
                )
                assert new_hub_cert["name"] != initial_hub_cert_name, (
                    "Hub certificate name should differ after revoke"
                )
                logger.warning(
                    "[e2e] New hub cert: %s (was %s)",
                    new_hub_cert["name"], initial_hub_cert_name,
                )
            else:
                # LRO managed to upload the new cert — just verify it
                new_hub_cert = self.find_hub_cert_by_policy(hub_name, rg, policy_rid)
                assert new_hub_cert is not None, (
                    "New ICA certificate should be on hub after revoke"
                )
                assert new_hub_cert["name"] != initial_hub_cert_name, (
                    "Hub certificate name should differ after revoke"
                )

            # --- Step 5: Final verification ---
            updated_policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {policy_name}"
            ).get_output_in_json()
            assert updated_policy["properties"]["provisioningState"] == "Succeeded"
            logger.warning(
                "[e2e] PASS: revoke-issuer completed — ICA regenerated, hub cert rotated"
            )

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
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            default_policy = self.setup_namespace_with_policy(namespace_name, rg)
            assert default_policy["properties"]["provisioningState"] == "Succeeded"

            # Second policy should be rejected
            with pytest.raises(Exception):
                self.cmd(f"iot adr ns policy create --ns {namespace_name} -g {rg} --policy-name secondpolicy --cert-key-type ECC")

            # Only one Succeeded policy should exist
            policies = self.cmd(
                f"iot adr ns policy list --ns {namespace_name} -g {rg}"
            ).get_output_in_json()

            succeeded = [p for p in policies if p["properties"]["provisioningState"] == "Succeeded"]
            assert len(succeeded) == 1
            assert succeeded[0]["name"] == "default"

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_revoke_nonexistent_policy(self):
        """Attempting revoke-issuer on a nonexistent policy should fail."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            self.setup_namespace_with_policy(namespace_name, rg)

            with pytest.raises(Exception):
                self.cmd(
                    f"iot adr ns policy revoke-issuer --ns {namespace_name} -g {rg} "
                    f"--policy-name nonexistent -y"
                )
        finally:
            self.cleanup_namespace(namespace_name, rg)
