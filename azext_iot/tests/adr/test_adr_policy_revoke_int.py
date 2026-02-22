# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Integration tests for ADR policy revoke-issuer and BYOR (Bring Your Own Root) commands.

Requirements:
- Azure subscription with appropriate permissions
- Resource group specified in azext_iot_testrg environment variable
- openssl CLI available on PATH (used for ECDSA certificate signing)
"""

import os
import subprocess
import tempfile
import time
from typing import Dict, List, Optional

import pytest
from knack.log import get_logger

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr.conftest import (
    CUSTOM_CERT_KEY_TYPE,
    CUSTOM_POLICY_NAME,
    TEST_RG,
    generate_adr_namespace_name,
    generate_hub_name,
    generate_identity_name,
)

logger = get_logger(__name__)

TEST_LOCATION = "centraluseuap"

# Propagation delays (seconds) for Azure resource readiness
_ROLE_PROPAGATION_DELAY = 30
_POLICY_PROPAGATION_DELAY = 15


def _get_byor_config(policy: dict) -> dict:
    """Extract the bringYourOwnRoot config from a policy response."""
    return (
        policy["properties"]["certificate"]["certificateAuthorityConfiguration"]["bringYourOwnRoot"]
    )


def _get_ca_config(policy: dict) -> dict:
    """Extract the certificateAuthorityConfiguration from a policy response."""
    return policy["properties"]["certificate"]["certificateAuthorityConfiguration"]


def sign_csr_with_ca(csr_pem: str, valid_days: int = 730) -> str:
    """
    Sign a CSR with a freshly generated EC CA using openssl CLI.

    We use openssl rather than Python's cryptography library because the backend
    generates ECDSA CSRs with explicit curve parameters, which cryptography
    cannot parse. The backend also requires ECDSA signatures (rejects RSA).

    Returns the certificate chain (signed cert + CA cert) as a PEM string.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = {k: os.path.join(tmpdir, v) for k, v in {
            "csr": "csr.pem", "ca_key": "ca.key", "ca_cert": "ca.crt",
            "signed": "signed.crt", "ext": "ext.cnf",
        }.items()}

        # Write CSR
        with open(paths["csr"], "w") as f:
            f.write(csr_pem)

        # Generate EC P-384 CA key (must match backend's ECC curve)
        subprocess.run(
            ["openssl", "ecparam", "-genkey", "-name", "secp384r1",
             "-noout", "-out", paths["ca_key"]],
            check=True, capture_output=True,
        )

        # Self-signed CA certificate (use SHA-384 to match P-384 curve)
        subprocess.run(
            ["openssl", "req", "-x509", "-new", "-sha384",
             "-key", paths["ca_key"], "-out", paths["ca_cert"],
             "-days", "3650", "-subj", "/CN=Test BYOR Root CA",
             "-addext", "basicConstraints=critical,CA:TRUE,pathlen:1",
             "-addext", "keyUsage=critical,keyCertSign,cRLSign"],
            check=True, capture_output=True,
        )

        # X.509 extensions for the signed ICA certificate
        # extendedKeyUsage = clientAuth is REQUIRED for BYOR activation
        with open(paths["ext"], "w") as f:
            f.write(
                "[v3_intermediate_ca]\n"
                "basicConstraints = critical, CA:TRUE, pathlen:0\n"
                "keyUsage = critical, digitalSignature, keyCertSign, cRLSign\n"
                "extendedKeyUsage = clientAuth\n"
                "subjectKeyIdentifier = hash\n"
                "authorityKeyIdentifier = keyid:always, issuer:always\n"
            )

        # Sign the CSR (use SHA-384 to match P-384 curve)
        subprocess.run(
            ["openssl", "x509", "-req", "-sha384",
             "-in", paths["csr"], "-CA", paths["ca_cert"], "-CAkey", paths["ca_key"],
             "-CAcreateserial", "-out", paths["signed"],
             "-days", str(valid_days), "-extfile", paths["ext"],
             "-extensions", "v3_intermediate_ca"],
            check=True, capture_output=True,
        )

        # Return signed cert + CA cert as chain
        with open(paths["signed"]) as f:
            signed = f.read()
        with open(paths["ca_cert"]) as f:
            ca = f.read()
        return signed + ca


class _FullInfraMixin:
    """Shared infrastructure helpers for integration tests that need ADR + IoT Hub.

    Provides:
    - Role assignment helpers (reusable across tests)
    - Full infrastructure setup: UAMI → ADR namespace → credential → policy → IoT Hub Gen2 w/ ADR link
    - Hub certificate listing for post-sync / post-revoke verification
    - Cleanup for namespace-only or full infrastructure (Hub + UAMI + namespace)
    """

    # --- Role assignment helpers ---

    def assign_role(self, assignee_id: str, role: str, scope: str, assignee_type: str = "auto") -> Optional[str]:
        """Assign an Azure role, skipping if it already exists."""
        try:
            existing = self.cmd(
                f"role assignment list --assignee '{assignee_id}' --scope '{scope}' --role '{role}'"
            ).get_output_in_json()
            if existing:
                logger.info("Role '%s' already assigned to %s", role, assignee_id)
                return existing[0].get("id", "existing")

            if assignee_type == "auto":
                result = self.cmd(
                    f"role assignment create --assignee '{assignee_id}' --role '{role}' --scope '{scope}'"
                ).get_output_in_json()
            else:
                result = self.cmd(
                    f"role assignment create --assignee-object-id '{assignee_id}' --role '{role}' "
                    f"--scope '{scope}' --assignee-principal-type '{assignee_type}'"
                ).get_output_in_json()

            return result.get("id", "unknown")
        except Exception as e:
            logger.warning("Failed to assign role '%s' to %s: %s", role, assignee_id, e)
            return None

    def assign_hub_rp_contributor_role(self, subscription_id: str, resource_group: str):
        """Assign Contributor to the IoT Hub first-party RP on the resource group."""
        hub_rp_object_id = "0aab4033-4ad9-4b0b-9934-542334eceffb"
        rg_scope = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        self.assign_role(hub_rp_object_id, "Contributor", rg_scope, assignee_type="ServicePrincipal")

    def assign_adr_roles_to_identity(self, principal_id: str, scope: str):
        """Assign ADR Contributor + Onboarding roles to a managed identity."""
        for role in ["Azure Device Registry Contributor", "Azure Device Registry Onboarding"]:
            self.assign_role(principal_id, role, scope)

    # --- Full infrastructure setup ---

    def setup_full_infra(
        self,
        resource_group: str,
        namespace_name: str,
        hub_name: str,
        identity_name: str,
        policy_name: str = CUSTOM_POLICY_NAME,
        enable_byor: bool = False,
        use_default_policy: bool = False,
    ) -> Dict[str, str]:
        """Create UAMI → ADR namespace (with credential+policy) → IoT Hub Gen2 with ADR link.

        Uses ``--enable-credential-policy`` to atomically create the credential and
        default policy during namespace creation (matching the working reference test
        pattern).  For BYOR tests, the auto-created policy is deleted and replaced
        with a BYOR-enabled policy.

        When *use_default_policy* is True, the auto-created ``default`` policy is
        kept as-is (no delete / recreate).  This avoids potential backend state
        issues that can cause revokeIssuer NullReferenceExceptions.

        Returns a dict with keys: subscription_id, identity_resource_id,
        identity_principal_id, adr_resource_id, hub_name, policy_name.
        """
        # Create UAMI
        logger.warning("[setup] Creating UAMI '%s' ...", identity_name)
        identity = self.cmd(
            f"identity create -n {identity_name} -g {resource_group} --location {TEST_LOCATION}"
        ).get_output_in_json()
        identity_resource_id = identity["id"]
        identity_principal_id = identity["principalId"]
        logger.warning("[setup] UAMI principalId=%s", identity_principal_id)

        # Get subscription ID
        subscription_id = self.cmd("account show").get_output_in_json()["id"]
        logger.warning("[setup] subscription=%s", subscription_id)

        # Hub RP contributor on RG
        logger.warning("[setup] Assigning Hub RP Contributor role ...")
        self.assign_hub_rp_contributor_role(subscription_id, resource_group)

        # ADR namespace with atomically-created credential + default policy.
        # This matches the reference test pattern that is known to work with sync.
        logger.warning("[setup] Creating namespace '%s' with --enable-credential-policy ...", namespace_name)
        namespace = self.cmd(
            f"iot adr ns create -n {namespace_name} -g {resource_group} "
            f"--location {TEST_LOCATION} --enable-credential-policy"
        ).get_output_in_json()
        adr_resource_id = namespace["id"]

        assert namespace["properties"]["provisioningState"] == "Succeeded"
        logger.warning(
            "[setup] Namespace created: id=%s, identity=%s",
            adr_resource_id,
            namespace.get("identity", {}).get("type"),
        )

        # ADR roles for UAMI on namespace
        logger.warning("[setup] Assigning ADR roles to UAMI on namespace ...")
        self.assign_adr_roles_to_identity(identity_principal_id, adr_resource_id)

        if use_default_policy:
            # Keep the auto-created 'default' policy as-is.
            policy_name = "default"
            logger.warning("[setup] Using auto-created default policy as-is")
            policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {resource_group} "
                f"--policy-name {policy_name}"
            ).get_output_in_json()
            logger.warning(
                "[setup] Default policy: provisioningState=%s",
                policy["properties"]["provisioningState"],
            )
        else:
            # Delete the auto-created default policy and create a named one.
            logger.warning("[setup] Deleting auto-created default policy ...")
            self.cmd(
                f"iot adr ns policy delete --ns {namespace_name} -g {resource_group} "
                f"--policy-name default -y"
            )

            byor_flag = " --enable-byor" if enable_byor else ""
            cert_flag = "" if enable_byor else f" --cert-key-type {CUSTOM_CERT_KEY_TYPE}"
            logger.warning("[setup] Creating policy '%s' (byor=%s) ...", policy_name, enable_byor)
            policy = self.cmd(
                f"iot adr ns policy create --ns {namespace_name} -g {resource_group} "
                f"--policy-name {policy_name}{byor_flag}{cert_flag}"
            ).get_output_in_json()

            logger.warning(
                "[setup] Policy ready: provisioningState=%s",
                policy["properties"]["provisioningState"],
            )

        # IoT Hub Gen2 with ADR link
        logger.warning("[setup] Creating IoT Hub Gen2 '%s' with ADR link ...", hub_name)
        hub = self.cmd(
            f"iot hub create -n {hub_name} -g {resource_group} --sku GEN2 --location {TEST_LOCATION} "
            f"--mi-user-assigned {identity_resource_id} "
            f"--ns-resource-id {adr_resource_id} "
            f"--ns-identity-id {identity_resource_id}"
        ).get_output_in_json()

        assert hub["properties"]["state"] == "Active"

        # Validate hub ADR integration
        hub_show = self.cmd(f"iot hub show -n {hub_name} -g {resource_group}").get_output_in_json()
        adr_props = hub_show.get("properties", {}).get("deviceRegistry", {})
        logger.warning(
            "[setup] Hub ADR config: nsResourceId=%s, identityResourceId=%s",
            adr_props.get("namespaceResourceId"),
            adr_props.get("identityResourceId"),
        )

        # Allow time for role assignments and hub-ADR link to propagate
        logger.warning("[setup] Waiting %ds for role/hub propagation ...", _ROLE_PROPAGATION_DELAY)
        time.sleep(_ROLE_PROPAGATION_DELAY)

        return {
            "subscription_id": subscription_id,
            "identity_resource_id": identity_resource_id,
            "identity_principal_id": identity_principal_id,
            "adr_resource_id": adr_resource_id,
            "hub_name": hub_name,
            "policy_name": policy_name,
        }

    # --- Hub certificate helpers ---

    def get_hub_certificates(self, hub_name: str, resource_group: str) -> List[dict]:
        """Return the list of certificates on an IoT Hub."""
        certs = self.cmd(
            f"iot hub certificate list --hub-name {hub_name} -g {resource_group}"
        ).get_output_in_json()
        return certs.get("value", [])

    def find_hub_cert_by_policy(
        self, hub_name: str, resource_group: str, policy_resource_id: str,
    ) -> Optional[dict]:
        """Find a hub certificate matching a given PolicyResourceId."""
        for cert in self.get_hub_certificates(hub_name, resource_group):
            if cert.get("properties", {}).get("PolicyResourceId") == policy_resource_id:
                return cert
        return None

    def build_policy_resource_id(
        self, subscription_id: str, resource_group: str, namespace_name: str, policy_name: str,
    ) -> str:
        """Build the ARM resource ID for a credential policy."""
        return (
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.DeviceRegistry/namespaces/{namespace_name}/credentials/"
            f"default/policies/{policy_name}"
        )

    # --- Namespace + policy helpers ---

    def setup_namespace_with_policy(
        self, namespace_name: str, resource_group: str,
        policy_name: str = "default", enable_byor: bool = False,
    ) -> dict:
        """Create ADR namespace + credential + policy (lightweight setup without hub).

        Returns the policy resource JSON.
        """
        self.cmd(f"iot adr ns create -n {namespace_name} -g {resource_group} --location {TEST_LOCATION}")
        self.cmd(f"iot adr ns credential create --ns {namespace_name} -g {resource_group}")
        byor_flag = " --enable-byor" if enable_byor else f" --cert-key-type {CUSTOM_CERT_KEY_TYPE}"
        return self.cmd(
            f"iot adr ns policy create --ns {namespace_name} -g {resource_group} "
            f"--policy-name {policy_name}{byor_flag}"
        ).get_output_in_json()

    def activate_byor_policy(
        self, namespace_name: str, resource_group: str,
        policy_name: str, csr_pem: str,
    ) -> dict:
        """Sign a BYOR CSR with a test CA, activate the policy, and return updated policy JSON."""
        chain_pem = sign_csr_with_ca(csr_pem)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(chain_pem)
            cert_file = f.name
        try:
            self.cmd(
                f"iot adr ns policy activate-byor --ns {namespace_name} -g {resource_group} "
                f"--policy-name {policy_name} --certificate-chain-file {cert_file}"
            )
        finally:
            os.unlink(cert_file)
        return self.cmd(
            f"iot adr ns policy show --ns {namespace_name} -g {resource_group} "
            f"--policy-name {policy_name}"
        ).get_output_in_json()

    # --- Cleanup helpers ---

    def cleanup_namespace(self, namespace_name: str, resource_group: str):
        """Delete just the ADR namespace (lightweight tests)."""
        try:
            self.cmd(f"iot adr ns delete -n {namespace_name} -g {resource_group} -y")
        except Exception as e:
            logger.warning("Cleanup failed for namespace '%s': %s", namespace_name, e)

    def cleanup_full_infra(
        self,
        resource_group: str,
        hub_name: Optional[str] = None,
        namespace_name: Optional[str] = None,
        identity_name: Optional[str] = None,
    ):
        """Best-effort cleanup of all infrastructure resources."""
        for label, cmd in [
            ("IoT Hub", f"iot hub delete -n {hub_name} -g {resource_group}" if hub_name else None),
            ("ADR namespace", f"iot adr ns delete -n {namespace_name} -g {resource_group} -y" if namespace_name else None),
            ("UAMI", f"identity delete -n {identity_name} -g {resource_group}" if identity_name else None),
        ]:
            if cmd:
                try:
                    self.cmd(cmd)
                except Exception as e:
                    logger.warning("Cleanup failed for %s: %s", label, e)


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyRevokeLifecycle(_FullInfraMixin, CaptureOutputLiveScenarioTest):
    """Tests for the revoke-issuer command with full IoT Hub integration.

    Validates the backend contract:
    - Revoke deletes the old ICA from the linked hub
    - Revoke creates a new ICA on the policy
    - The new ICA is uploaded to the linked hub via credential sync
    """

    def test_policy_revoke_issuer_e2e(self):
        """Full E2E: create infra → sync → revoke → verify ICA rotation on policy and hub.

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
        # issues from delete→recreate that cause revokeIssuer NullReferenceException.
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
            pre_ca = _get_ca_config(pre_policy)
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
            post_ca = _get_ca_config(post_policy)
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
class TestADRPolicyBYORLifecycle(_FullInfraMixin, CaptureOutputLiveScenarioTest):
    """Tests for BYOR (Bring Your Own Root) policy creation and activation."""

    def test_policy_create_with_enable_byor(self):
        """Create a BYOR policy and verify CSR generation with PendingActivation status."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            policy = self.setup_namespace_with_policy(namespace_name, rg, enable_byor=True)
            assert policy["properties"]["provisioningState"] == "Succeeded"

            byor = _get_byor_config(policy)
            assert byor.get("enabled") is True
            assert byor.get("status") == "PendingActivation"
            assert "BEGIN CERTIFICATE REQUEST" in byor.get("certificateSigningRequest", "")

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_policy_activate_byor_full_lifecycle(self):
        """Create BYOR policy, sign its CSR with a test CA, activate, and verify Active status."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            policy = self.setup_namespace_with_policy(namespace_name, rg, enable_byor=True)

            byor = _get_byor_config(policy)
            assert byor["status"] == "PendingActivation"

            # Brief delay for policy internal state to settle after creation
            time.sleep(_POLICY_PROPAGATION_DELAY)

            activated = self.activate_byor_policy(
                namespace_name, rg, "default", byor["certificateSigningRequest"]
            )
            activated_byor = _get_byor_config(activated)
            assert activated_byor["status"] == "Active"
            assert activated_byor.get("issuingCertificateThumbprint") is not None

        finally:
            self.cleanup_namespace(namespace_name, rg)

    def test_byor_activate_and_sync_to_hub(self):
        """BYOR E2E: create infra with BYOR → sign CSR → activate → sync → verify ICA on hub."""
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
            byor = _get_byor_config(policy)
            assert byor["enabled"] is True
            assert byor["status"] == "PendingActivation"
            csr = byor.get("certificateSigningRequest", "")
            assert "BEGIN CERTIFICATE REQUEST" in csr, "CSR must be present for BYOR activation"

            # Brief delay for policy internal state to settle
            time.sleep(_POLICY_PROPAGATION_DELAY)

            # --- Step 3: Sign CSR and activate BYOR ---
            activated_policy = self.activate_byor_policy(namespace_name, rg, policy_name, csr)

            # --- Step 4: Verify BYOR status is Active with thumbprint ---

            activated_byor = _get_byor_config(activated_policy)
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
        """BYOR rotation: activate → sync → revoke → PendingActivation → re-sign → re-activate → sync → verify hub.

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
            byor = _get_byor_config(policy)
            assert byor["status"] == "PendingActivation"

            # Brief delay for policy internal state to settle
            time.sleep(_POLICY_PROPAGATION_DELAY)

            first_csr = byor["certificateSigningRequest"]
            activated = self.activate_byor_policy(namespace_name, rg, policy_name, first_csr)
            first_byor = _get_byor_config(activated)
            assert first_byor["status"] == "Active"
            first_thumbprint = first_byor.get("issuingCertificateThumbprint")
            assert first_thumbprint is not None

            # --- Step 3: Sync and record first ICA on hub ---
            self.cmd(f"iot adr ns credential sync --ns {namespace_name} -g {rg}")

            first_hub_cert = self.find_hub_cert_by_policy(hub_name, rg, policy_rid)
            assert first_hub_cert is not None, "First BYOR ICA should be on hub after sync"
            first_hub_cert_name = first_hub_cert["name"]

            # --- Step 4: Revoke issuer → expect PendingActivation with new CSR ---
            # For BYOR, revokeIssuer transitions back to PendingActivation.
            # The LRO also removes the old ICA from the hub automatically.
            self.cmd(
                f"iot adr ns policy revoke-issuer --ns {namespace_name} -g {rg} "
                f"--policy-name {policy_name} -y"
            )

            revoked = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {policy_name}"
            ).get_output_in_json()

            revoked_byor = _get_byor_config(revoked)
            assert revoked_byor["status"] == "PendingActivation", (
                f"After revoke, BYOR status should be PendingActivation, got '{revoked_byor['status']}'"
            )
            second_csr = revoked_byor.get("certificateSigningRequest", "")
            assert "BEGIN CERTIFICATE REQUEST" in second_csr, "New CSR must be generated after revoke"
            assert second_csr != first_csr, "New CSR should differ from the original CSR"

            # Brief delay for policy internal state to settle after revoke
            time.sleep(_POLICY_PROPAGATION_DELAY)

            # --- Step 5: Re-sign new CSR and re-activate ---
            reactivated = self.activate_byor_policy(namespace_name, rg, policy_name, second_csr)
            reactivated_byor = _get_byor_config(reactivated)
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
class TestADRPolicyLimits(_FullInfraMixin, CaptureOutputLiveScenarioTest):
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

    def test_byor_not_enabled_on_standard_policy(self):
        """Verify a standard (non-BYOR) policy does not have BYOR enabled."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            self.setup_namespace_with_policy(namespace_name, rg)

            policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
            ).get_output_in_json()

            byor = _get_ca_config(policy).get("bringYourOwnRoot")
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

            byor = _get_byor_config(policy)
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

                with open(cert_path) as f:
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
            assert _get_byor_config(still_pending)["status"] == "PendingActivation"

        finally:
            self.cleanup_namespace(namespace_name, rg)
