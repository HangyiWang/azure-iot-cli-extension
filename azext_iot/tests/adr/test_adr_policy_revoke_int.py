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

import pytest
from knack.log import get_logger

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr.conftest import (
    TEST_RG,
    generate_adr_namespace_name,
)

logger = get_logger(__name__)

TEST_LOCATION = "centraluseuap"


def _get_byor_config(policy: dict) -> dict:
    """Extract the bringYourOwnRoot config from a policy response."""
    return (
        policy["properties"]["certificate"]["certificateAuthorityConfiguration"]["bringYourOwnRoot"]
    )


def _get_ca_config(policy: dict) -> dict:
    """Extract the certificateAuthorityConfiguration from a policy response."""
    return policy["properties"]["certificate"]["certificateAuthorityConfiguration"]


def sign_csr_with_ca(csr_pem: str, valid_days: int = 365) -> str:
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

        # Generate EC P-256 CA key
        subprocess.run(
            ["openssl", "ecparam", "-genkey", "-name", "prime256v1",
             "-noout", "-out", paths["ca_key"]],
            check=True, capture_output=True,
        )

        # Self-signed CA certificate
        subprocess.run(
            ["openssl", "req", "-x509", "-new",
             "-key", paths["ca_key"], "-out", paths["ca_cert"],
             "-days", "365", "-subj", "/CN=Test BYOR Root CA"],
            check=True, capture_output=True,
        )

        # X.509 extensions for the signed certificate
        with open(paths["ext"], "w") as f:
            f.write(
                "[v3_intermediate_ca]\n"
                "basicConstraints = critical, CA:TRUE, pathlen:0\n"
                "keyUsage = critical, digitalSignature, keyCertSign, cRLSign\n"
            )

        # Sign the CSR
        subprocess.run(
            ["openssl", "x509", "-req",
             "-in", paths["csr"], "-CA", paths["ca_cert"], "-CAkey", paths["ca_key"],
             "-CAcreateserial", "-out", paths["signed"],
             "-days", str(valid_days), "-extfile", paths["ext"],
             "-extensions", "v3_intermediate_ca"],
            check=True, capture_output=True,
        )

        # Return signed cert + CA cert as chain
        signed = open(paths["signed"]).read()
        ca = open(paths["ca_cert"]).read()
        return signed + ca


class _NamespaceCleanupMixin:
    """Shared cleanup for integration tests that create namespaces."""

    def _cleanup_namespace(self, namespace_name: str, resource_group: str):
        try:
            self.cmd(f"iot adr ns delete -n {namespace_name} -g {resource_group} -y")
        except Exception as e:
            logger.warning(f"Cleanup failed for namespace '{namespace_name}': {e}")


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyRevokeLifecycle(_NamespaceCleanupMixin, CaptureOutputLiveScenarioTest):
    """Tests for the revoke-issuer command that rotates the CA certificate."""

    def __init__(self, test_case):
        super().__init__(test_case)

    @pytest.mark.xfail(strict=False, reason="Backend returns GenericServerError on revoke-issuer LRO")
    def test_policy_revoke_issuer(self):
        """Revoke the CA certificate and verify a new one is generated."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )

            policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
            ).get_output_in_json()

            assert policy["properties"]["provisioningState"] == "Succeeded"
            initial_thumbprint = _get_ca_config(policy).get("thumbprint")

            # Revoke — triggers CA regeneration
            self.cmd(
                f"iot adr ns policy revoke-issuer --ns {namespace_name} -g {rg} --policy-name default -y"
            )

            updated = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
            ).get_output_in_json()

            new_thumbprint = _get_ca_config(updated).get("thumbprint")
            if initial_thumbprint and new_thumbprint:
                assert initial_thumbprint != new_thumbprint, "CA thumbprint should change after revoke"
            assert updated["properties"]["provisioningState"] == "Succeeded"

        finally:
            self._cleanup_namespace(namespace_name, rg)


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyBYORLifecycle(_NamespaceCleanupMixin, CaptureOutputLiveScenarioTest):
    """Tests for BYOR (Bring Your Own Root) policy creation and activation."""

    def __init__(self, test_case):
        super().__init__(test_case)

    def test_policy_create_with_enable_byor(self):
        """Create a BYOR policy and verify CSR generation with PendingActivation status."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            # Create namespace + credential without auto-policy, then create BYOR directly
            self.cmd(f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION}")
            self.cmd(f"iot adr ns credential create --ns {namespace_name} -g {rg}")

            policy = self.cmd(
                f"iot adr ns policy create --ns {namespace_name} -g {rg} "
                f"--policy-name default --enable-byor"
            ).get_output_in_json()

            assert policy["properties"]["provisioningState"] == "Succeeded"

            byor = _get_byor_config(policy)
            assert byor.get("enabled") is True
            assert byor.get("status") == "PendingActivation"
            assert "BEGIN CERTIFICATE REQUEST" in byor.get("certificateSigningRequest", "")

        finally:
            self._cleanup_namespace(namespace_name, rg)

    def test_policy_activate_byor_full_lifecycle(self):
        """Create BYOR policy, sign its CSR with a test CA, activate, and verify Active status."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            # Create namespace + credential without auto-policy to avoid delete-then-recreate
            self.cmd(f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION}")
            self.cmd(f"iot adr ns credential create --ns {namespace_name} -g {rg}")

            policy = self.cmd(
                f"iot adr ns policy create --ns {namespace_name} -g {rg} "
                f"--policy-name default --enable-byor"
            ).get_output_in_json()

            byor = _get_byor_config(policy)
            assert byor["status"] == "PendingActivation"

            # Sign the CSR and write chain to a temp file
            chain_pem = sign_csr_with_ca(byor["certificateSigningRequest"])

            with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
                f.write(chain_pem)
                cert_file_path = f.name

            try:
                self.cmd(
                    f"iot adr ns policy activate-byor --ns {namespace_name} -g {rg} "
                    f"--policy-name default --certificate-chain-file {cert_file_path}"
                )

                activated = self.cmd(
                    f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
                ).get_output_in_json()

                activated_byor = _get_byor_config(activated)
                assert activated_byor["status"] == "Active"
                assert activated_byor.get("issuingCertificateThumbprint") is not None
            finally:
                os.unlink(cert_file_path)

        finally:
            self._cleanup_namespace(namespace_name, rg)


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyLimits(_NamespaceCleanupMixin, CaptureOutputLiveScenarioTest):
    """Tests for backend-enforced policy constraints."""

    def __init__(self, test_case):
        super().__init__(test_case)

    def test_single_policy_limit_per_credential(self):
        """Verify the backend rejects creating more than one policy per credential."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )

            # Ensure default policy is in Succeeded state (may need recreation due to race)
            default_policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
            ).get_output_in_json()

            if default_policy["properties"]["provisioningState"] != "Succeeded":
                logger.warning("Default policy in non-Succeeded state, recreating...")
                self.cmd(f"iot adr ns policy delete --ns {namespace_name} -g {rg} --policy-name default -y")
                default_policy = self.cmd(
                    f"iot adr ns policy create --ns {namespace_name} -g {rg} --policy-name default"
                ).get_output_in_json()

            assert default_policy["properties"]["provisioningState"] == "Succeeded"

            # Second policy should be rejected
            with pytest.raises(Exception, match="PolicyLimitExceeded|more than 1 policies"):
                self.cmd(f"iot adr ns policy create --ns {namespace_name} -g {rg} --policy-name secondpolicy")

            # Only one Succeeded policy should exist
            policies = self.cmd(
                f"iot adr ns policy list --ns {namespace_name} -g {rg}"
            ).get_output_in_json()

            succeeded = [p for p in policies if p["properties"]["provisioningState"] == "Succeeded"]
            assert len(succeeded) == 1
            assert succeeded[0]["name"] == "default"

        finally:
            self._cleanup_namespace(namespace_name, rg)

    def test_byor_not_enabled_on_standard_policy(self):
        """Verify a standard (non-BYOR) policy does not have BYOR enabled."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )

            policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default"
            ).get_output_in_json()

            byor = _get_ca_config(policy).get("bringYourOwnRoot")
            if byor:
                assert byor.get("enabled") is not True

        finally:
            self._cleanup_namespace(namespace_name, rg)
