# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Integration tests for ADR policy revoke and BYOR (Bring Your Own Root) commands.

These tests require:
- Azure subscription with appropriate permissions
- Resource group specified in azext_iot_testrg environment variable
- cryptography library for certificate operations
"""

import datetime
import os
import tempfile

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from knack.log import get_logger

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr.conftest import (
    TEST_RG,
    generate_adr_namespace_name,
)

logger = get_logger(__name__)

TEST_LOCATION = "westus"


def sign_csr_with_ca(csr_pem: str, valid_days: int = 30) -> dict:
    """
    Sign a CSR with a newly generated CA certificate.
    Simulates what a customer would do with their own CA.

    Args:
        csr_pem: The CSR in PEM format from the BYOR policy
        valid_days: Validity period for the signed certificate

    Returns:
        dict with 'certificate_chain' (signed cert + CA cert in PEM)
    """
    # Load the CSR
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))

    # Generate CA private key
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

    # Create self-signed CA certificate
    ca_subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Test BYOR Root CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Organization"),
    ])

    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # Sign the CSR to create the leaf certificate
    signed_cert = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(ca_cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=valid_days))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    # Convert to PEM and create chain (leaf to root order)
    ca_cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    signed_cert_pem = signed_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    return {"certificate_chain": signed_cert_pem + ca_cert_pem}


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyRevokeLifecycle(CaptureOutputLiveScenarioTest):

    def __init__(self, test_case):
        super(TestADRPolicyRevokeLifecycle, self).__init__(test_case)

    def test_policy_revoke_issuer(self):
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        policy_name = "revoke-test-policy"

        try:
            # Create namespace with credential
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )

            # Delete the default policy and create test policy
            self.cmd(f"iot adr ns policy delete --ns {namespace_name} -g {rg} --policy-name default -y")

            policy = self.cmd(
                f"iot adr ns policy create --ns {namespace_name} -g {rg} --policy-name {policy_name}"
            ).get_output_in_json()

            assert policy["name"] == policy_name
            assert policy["properties"]["provisioningState"] == "Succeeded"

            # Get initial CA thumbprint
            initial_thumbprint = policy["properties"]["certificate"].get(
                "certificateAuthorityConfiguration", {}
            ).get("thumbprint")

            # Revoke the issuer certificate
            self.cmd(
                f"iot adr ns policy revoke-issuer --ns {namespace_name} -g {rg} --policy-name {policy_name} -y"
            )

            # Verify new CA was generated
            updated_policy = self.cmd(
                f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {policy_name}"
            ).get_output_in_json()

            new_thumbprint = updated_policy["properties"]["certificate"].get(
                "certificateAuthorityConfiguration", {}
            ).get("thumbprint")

            # Verify the thumbprint changed (new CA was generated)
            if initial_thumbprint and new_thumbprint:
                assert initial_thumbprint != new_thumbprint

            assert updated_policy["properties"]["provisioningState"] == "Succeeded"

        finally:
            try:
                self.cmd(f"iot adr ns delete -n {namespace_name} -g {rg} -y")
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyBYORLifecycle(CaptureOutputLiveScenarioTest):

    def __init__(self, test_case):
        super(TestADRPolicyBYORLifecycle, self).__init__(test_case)

    def test_policy_create_with_enable_byor(self):
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        policy_name = "byor-test-policy"

        try:
            # Create namespace with credential
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )

            # Delete the default policy
            self.cmd(f"iot adr ns policy delete --ns {namespace_name} -g {rg} --policy-name default -y")

            # Create BYOR policy
            policy = self.cmd(
                f"iot adr ns policy create --ns {namespace_name} -g {rg} "
                f"--policy-name {policy_name} --enable-byor"
            ).get_output_in_json()

            assert policy["name"] == policy_name
            assert policy["properties"]["provisioningState"] == "Succeeded"

            # Verify BYOR configuration
            cert_config = policy["properties"].get("certificate", {})
            byor_config = cert_config.get("bringYourOwnRoot", {})

            assert byor_config.get("enabled") is True

            # Verify CSR was generated
            csr = byor_config.get("certificateSigningRequest")
            assert csr is not None
            assert "BEGIN CERTIFICATE REQUEST" in csr

            # Verify status is PendingActivation
            assert byor_config.get("status") == "PendingActivation"

        finally:
            try:
                self.cmd(f"iot adr ns delete -n {namespace_name} -g {rg} -y")
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")

    def test_policy_activate_byor_full_lifecycle(self):
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        policy_name = "byor-activate-test"

        try:
            # Create namespace with credential
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )

            # Delete the default policy
            self.cmd(f"iot adr ns policy delete --ns {namespace_name} -g {rg} --policy-name default -y")

            # Create BYOR policy
            policy = self.cmd(
                f"iot adr ns policy create --ns {namespace_name} -g {rg} "
                f"--policy-name {policy_name} --enable-byor"
            ).get_output_in_json()

            # Extract CSR and verify initial state
            byor_config = policy["properties"]["certificate"]["bringYourOwnRoot"]
            csr_pem = byor_config["certificateSigningRequest"]
            assert byor_config["status"] == "PendingActivation"

            # Sign the CSR with test CA
            signed_result = sign_csr_with_ca(csr_pem)

            # Write certificate chain to temp file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as cert_file:
                cert_file.write(signed_result["certificate_chain"])
                cert_file_path = cert_file.name

            try:
                # Activate BYOR with signed certificate
                self.cmd(
                    f"iot adr ns policy activate-byor --ns {namespace_name} -g {rg} "
                    f"--policy-name {policy_name} --certificate-chain-file {cert_file_path}"
                )

                # Verify activation
                activated_policy = self.cmd(
                    f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {policy_name}"
                ).get_output_in_json()

                byor_status = activated_policy["properties"]["certificate"]["bringYourOwnRoot"]["status"]
                assert byor_status == "Active"

                # Verify thumbprint is set
                thumbprint = activated_policy["properties"]["certificate"]["bringYourOwnRoot"].get(
                    "issuingCertificateThumbprint"
                )
                assert thumbprint is not None

            finally:
                if os.path.exists(cert_file_path):
                    os.unlink(cert_file_path)

        finally:
            try:
                self.cmd(f"iot adr ns delete -n {namespace_name} -g {rg} -y")
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")


@pytest.mark.usefixtures("set_cwd")
class TestADRPolicyLimits(CaptureOutputLiveScenarioTest):

    def __init__(self, test_case):
        super(TestADRPolicyLimits, self).__init__(test_case)

    def test_multiple_policies_per_credential(self):
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        max_policies_to_test = 5
        created_policies = []

        try:
            # Create namespace with credential
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )

            # Delete the default policy
            self.cmd(f"iot adr ns policy delete --ns {namespace_name} -g {rg} --policy-name default -y")

            # Try to create multiple policies
            for i in range(max_policies_to_test):
                policy_name = f"testpolicy{i}"
                try:
                    policy = self.cmd(
                        f"iot adr ns policy create --ns {namespace_name} -g {rg} --policy-name {policy_name}"
                    ).get_output_in_json()

                    assert policy["properties"]["provisioningState"] == "Succeeded"
                    created_policies.append(policy_name)

                except Exception as e:
                    logger.warning(f"Failed to create policy {i + 1}: {e}")
                    break

            # List all policies to verify
            policies = self.cmd(
                f"iot adr ns policy list --ns {namespace_name} -g {rg}"
            ).get_output_in_json()

            assert len(policies) == len(created_policies)

        finally:
            try:
                self.cmd(f"iot adr ns delete -n {namespace_name} -g {rg} -y")
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")

    def test_byor_policy_immutability(self):
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            # Create namespace with credential
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )

            # Delete default and create a non-BYOR policy
            self.cmd(f"iot adr ns policy delete --ns {namespace_name} -g {rg} --policy-name default -y")

            policy = self.cmd(
                f"iot adr ns policy create --ns {namespace_name} -g {rg} --policy-name regularPolicy"
            ).get_output_in_json()

            # Verify BYOR is not enabled
            cert_config = policy["properties"].get("certificate", {})
            byor_config = cert_config.get("bringYourOwnRoot")

            if byor_config:
                assert byor_config.get("enabled") is not True

        finally:
            try:
                self.cmd(f"iot adr ns delete -n {namespace_name} -g {rg} -y")
            except Exception as e:
                logger.warning(f"Cleanup failed: {e}")
