# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Integration tests for ADR BYOR (Bring Your Own Root) policy lifecycle.

Requirements:
- Azure subscription with appropriate permissions
- Resource group specified in azext_iot_testrg environment variable
- openssl CLI available on PATH (used for ECDSA certificate signing)
"""

import os
import subprocess
import tempfile
import time

import pytest
from knack.log import get_logger

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import (
    ADRHubInfraHelper,
    POLICY_PROPAGATION_DELAY,
    get_byor_config,
    get_ca_config,
)
from azext_iot.tests.adr.conftest import (
    CUSTOM_POLICY_NAME,
    TEST_RG,
    generate_adr_namespace_name,
    generate_hub_name,
    generate_identity_name,
)

logger = get_logger(__name__)


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyBYORLifecycle(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Tests for BYOR (Bring Your Own Root) policy creation and activation."""

    def test_policy_create_with_enable_byor(self):
        """Create a BYOR policy and verify CSR generation with PendingActivation status."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            policy = self.setup_namespace_with_policy(namespace_name, rg, enable_byor=True)
            assert policy["properties"]["provisioningState"] == "Succeeded"

            byor = get_byor_config(policy)
            assert byor["enabled"] is True
            assert byor["status"] == "PendingActivation"
            assert "BEGIN CERTIFICATE REQUEST" in byor.get("certificateSigningRequest", "")

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_policy_activate_byor_full_lifecycle(self):
        """Create BYOR policy, sign its CSR with a test CA, activate, and verify Active status."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            policy = self.setup_namespace_with_policy(namespace_name, rg, enable_byor=True)

            byor = get_byor_config(policy)
            assert byor["status"] == "PendingActivation"

            # Brief delay for policy internal state to settle after creation
            time.sleep(POLICY_PROPAGATION_DELAY)

            activated = self.activate_byor_policy(
                namespace_name, rg, "default", byor["certificateSigningRequest"]
            )
            activated_byor = get_byor_config(activated)
            assert activated_byor["status"] == "Active"
            assert activated_byor.get("issuingCertificateThumbprint") is not None

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_byor_activate_and_sync_to_hub(self):
        """BYOR E2E: create infra with BYOR -> sign CSR -> activate -> sync -> verify ICA on hub."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        hub_name = generate_hub_name()
        identity_name = generate_identity_name()
        policy_name = CUSTOM_POLICY_NAME

        try:
            # --- Step 1: Create full infrastructure with BYOR policy ---
            infra = self.setup_full_infra(
                resource_group=rg,
                namespace_name=namespace_name,
                hub_name=hub_name,
                identity_name=identity_name,
                policy_name=policy_name,
                enable_byor=True,
            )
            subscription_id = infra["subscription_id"]

            policy_rid = self.build_policy_resource_id(
                subscription_id, rg, namespace_name, policy_name,
            )

            # --- Step 2: Verify BYOR is PendingActivation with CSR ---
            policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {policy_name}"
            ).get_output_in_json()

            assert policy["properties"]["provisioningState"] == "Succeeded"
            byor = get_byor_config(policy)
            assert byor["enabled"] is True
            assert byor["status"] == "PendingActivation"
            csr = byor.get("certificateSigningRequest", "")
            assert "BEGIN CERTIFICATE REQUEST" in csr, "CSR must be present for BYOR activation"

            # Brief delay for policy internal state to settle
            time.sleep(POLICY_PROPAGATION_DELAY)

            # --- Step 3: Sign CSR and activate BYOR ---
            activated_policy = self.activate_byor_policy(namespace_name, rg, policy_name, csr)

            # --- Step 4: Verify BYOR status is Active with thumbprint ---

            activated_byor = get_byor_config(activated_policy)
            assert activated_byor["status"] == "Active", (
                f"Expected BYOR status 'Active', got '{activated_byor['status']}'"
            )
            issuing_thumbprint = activated_byor.get("issuingCertificateThumbprint")
            assert issuing_thumbprint is not None, "Active BYOR must have issuingCertificateThumbprint"

            # --- Step 5: Sync credentials and verify ICA on hub ---
            self.cmd(f"iot adr ns credential sync --ns {namespace_name} -g {rg}")

            hub_cert = self.find_hub_cert_by_policy(hub_name, rg, policy_rid)
            assert hub_cert is not None, (
                "BYOR ICA certificate should appear on hub after activation + sync"
            )
            assert hub_cert.get("properties", {}).get("PolicyResourceId") == policy_rid

        finally:
            self.cleanup_full_infra(
                resource_group=rg,
                hub_name=hub_name,
                namespace_name=namespace_name,
                identity_name=identity_name,
            )

    def test_byor_revoke_and_reactivate(self):
        """BYOR rotation: activate -> sync -> revoke -> PendingActivation -> re-sign -> re-activate -> sync -> verify hub.

        Validates the full BYOR certificate rotation lifecycle:
        1. BYOR policy activated and ICA synced to hub (sync needed after BYOR activation)
        2. Revoke issuer transitions back to PendingActivation with a new CSR
           (revokeIssuer LRO removes old ICA from hub automatically)
        3. Re-signing the new CSR and re-activating restores Active status
        4. Explicit credential sync after re-activation pushes new ICA to hub
        """
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        hub_name = generate_hub_name()
        identity_name = generate_identity_name()
        policy_name = CUSTOM_POLICY_NAME

        try:
            # --- Step 1: Full infra with BYOR policy ---
            infra = self.setup_full_infra(
                resource_group=rg,
                namespace_name=namespace_name,
                hub_name=hub_name,
                identity_name=identity_name,
                policy_name=policy_name,
                enable_byor=True,
            )
            subscription_id = infra["subscription_id"]

            policy_rid = self.build_policy_resource_id(
                subscription_id, rg, namespace_name, policy_name,
            )

            # --- Step 2: First activation ---
            policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {policy_name}"
            ).get_output_in_json()
            byor = get_byor_config(policy)
            assert byor["status"] == "PendingActivation"

            # Brief delay for policy internal state to settle
            time.sleep(POLICY_PROPAGATION_DELAY)

            first_csr = byor["certificateSigningRequest"]
            activated = self.activate_byor_policy(namespace_name, rg, policy_name, first_csr)
            first_byor = get_byor_config(activated)
            assert first_byor["status"] == "Active"
            first_thumbprint = first_byor.get("issuingCertificateThumbprint")
            assert first_thumbprint is not None

            # --- Step 3: Sync and record first ICA on hub ---
            self.cmd(f"iot adr ns credential sync --ns {namespace_name} -g {rg}")

            first_hub_cert = self.find_hub_cert_by_policy(hub_name, rg, policy_rid)
            assert first_hub_cert is not None, "First BYOR ICA should be on hub after sync"
            first_hub_cert_name = first_hub_cert["name"]

            # --- Step 4: Revoke issuer -> expect PendingActivation with new CSR ---
            # For BYOR, revokeIssuer transitions back to PendingActivation.
            # The LRO also removes the old ICA from the hub automatically.
            self.cmd(
                f"iot adr ns policy revoke-issuer --ns {namespace_name} -g {rg} "
                f"--policy-name {policy_name} -y"
            )

            revoked = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {policy_name}"
            ).get_output_in_json()

            revoked_byor = get_byor_config(revoked)
            assert revoked_byor["status"] == "PendingActivation", (
                f"After revoke, BYOR status should be PendingActivation, got '{revoked_byor['status']}'"
            )
            second_csr = revoked_byor.get("certificateSigningRequest", "")
            assert "BEGIN CERTIFICATE REQUEST" in second_csr, "New CSR must be generated after revoke"
            assert second_csr != first_csr, "New CSR should differ from the original CSR"

            # Brief delay for policy internal state to settle after revoke
            time.sleep(POLICY_PROPAGATION_DELAY)

            # --- Step 5: Re-sign new CSR and re-activate ---
            reactivated = self.activate_byor_policy(namespace_name, rg, policy_name, second_csr)
            reactivated_byor = get_byor_config(reactivated)
            assert reactivated_byor["status"] == "Active", (
                f"Expected Active after re-activation, got '{reactivated_byor['status']}'"
            )
            second_thumbprint = reactivated_byor.get("issuingCertificateThumbprint")
            assert second_thumbprint is not None
            assert second_thumbprint != first_thumbprint, (
                "Thumbprint must change after revoke + re-activate"
            )

            # --- Step 6: Sync after re-activation to push new BYOR ICA to hub ---
            # For BYOR, explicit sync IS needed after activation (confirmed by bugbash docs).
            self.cmd(f"iot adr ns credential sync --ns {namespace_name} -g {rg}")

            post_certs = self.get_hub_certificates(hub_name, rg)
            post_cert_names = [c["name"] for c in post_certs]
            assert first_hub_cert_name not in post_cert_names, (
                f"Old BYOR ICA '{first_hub_cert_name}' should be removed from hub after revoke cycle"
            )

            new_hub_cert = self.find_hub_cert_by_policy(hub_name, rg, policy_rid)
            assert new_hub_cert is not None, "New BYOR ICA should be on hub after re-activation + sync"
            assert new_hub_cert["name"] != first_hub_cert_name

        finally:
            self.cleanup_full_infra(
                resource_group=rg,
                hub_name=hub_name,
                namespace_name=namespace_name,
                identity_name=identity_name,
            )


@pytest.mark.usefixtures("set_cwd")
class TestADRBYOREdgeCases(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Edge-case and negative tests for BYOR policy behavior."""

    def test_byor_not_enabled_on_standard_policy(self):
        """Verify a standard (non-BYOR) policy does not have BYOR enabled."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            self.setup_namespace_with_policy(namespace_name, rg)

            policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
            ).get_output_in_json()

            byor = get_ca_config(policy).get("bringYourOwnRoot")
            if byor:
                assert byor.get("enabled") is not True

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_activate_byor_on_standard_policy_fails(self):
        """Attempting activate-byor on a non-BYOR policy should fail."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            self.setup_namespace_with_policy(namespace_name, rg)

            # Write a dummy PEM file (content doesn't matter — should be rejected before validation)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
                f.write("-----BEGIN CERTIFICATE-----\nZHVtbXk=\n-----END CERTIFICATE-----\n")
                dummy_cert = f.name

            try:
                with pytest.raises(Exception):
                    self.cmd(
                        f"iot adr ns policy activate-byor --ns {namespace_name} -g {rg} "
                        f"--policy-name default --certificate-chain-file {dummy_cert}"
                    )
            finally:
                os.unlink(dummy_cert)

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_activate_byor_with_mismatched_chain_fails(self):
        """Activating BYOR with a certificate that doesn't match the CSR should fail."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            policy = self.setup_namespace_with_policy(namespace_name, rg, enable_byor=True)

            byor = get_byor_config(policy)
            assert byor["status"] == "PendingActivation"

            # Generate a self-signed cert that does NOT match the CSR
            with tempfile.TemporaryDirectory() as tmpdir:
                key_path = os.path.join(tmpdir, "wrong.key")
                cert_path = os.path.join(tmpdir, "wrong.pem")

                subprocess.run(
                    ["openssl", "ecparam", "-genkey", "-name", "secp384r1",
                     "-noout", "-out", key_path],
                    check=True, capture_output=True,
                )
                subprocess.run(
                    ["openssl", "req", "-x509", "-new", "-sha384",
                     "-key", key_path, "-out", cert_path,
                     "-days", "365", "-subj", "/CN=Wrong CA",
                     "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
                     "-addext", "keyUsage=critical,keyCertSign,cRLSign"],
                    check=True, capture_output=True,
                )

                with open(cert_path, encoding="utf-8") as f:
                    wrong_chain = f.read()

            with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
                f.write(wrong_chain)
                wrong_cert_file = f.name

            try:
                with pytest.raises(Exception):
                    self.cmd(
                        f"iot adr ns policy activate-byor --ns {namespace_name} -g {rg} "
                        f"--policy-name default --certificate-chain-file {wrong_cert_file}"
                    )
            finally:
                os.unlink(wrong_cert_file)

            # Policy should still be PendingActivation after failed attempt
            still_pending = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
            ).get_output_in_json()
            assert get_byor_config(still_pending)["status"] == "PendingActivation"

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_revoke_pending_byor_before_activation(self):
        """Revoking a BYOR policy still in PendingActivation (never activated).

        Validates behavior when revoking before the BYOR CSR has been signed.
        The backend may reject the operation or regenerate the CSR.
        """
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            policy = self.setup_namespace_with_policy(namespace_name, rg, enable_byor=True)
            byor = get_byor_config(policy)
            assert byor["status"] == "PendingActivation"
            original_csr = byor.get("certificateSigningRequest", "")

            try:
                self.cmd(
                    f"iot adr ns policy revoke-issuer --ns {namespace_name} -g {rg} "
                    f"--policy-name default -y"
                )
                # If revoke succeeds, policy should still be PendingActivation with new CSR
                revoked = self.cmd(
                    f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
                ).get_output_in_json()
                revoked_byor = get_byor_config(revoked)
                assert revoked_byor["status"] == "PendingActivation"
                new_csr = revoked_byor.get("certificateSigningRequest", "")
                assert new_csr != original_csr, (
                    "CSR should change after revoking PendingActivation BYOR"
                )
            except Exception:
                # Backend may reject revoke on unactivated policy — verify unchanged state
                still_pending = self.cmd(
                    f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
                ).get_output_in_json()
                assert get_byor_config(still_pending)["status"] == "PendingActivation"

        finally:
            self.cleanup_namespace(namespace_name, rg)
