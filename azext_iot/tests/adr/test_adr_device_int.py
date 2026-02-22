# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR device lifecycle integration tests.

Provisions a device via the preview azure-iot-device SDK with CSR support,
then validates device list/show/update/revoke via CLI.

The lifecycle test requires the preview azure-iot-device SDK
(feature/dps-csr-preview) and ``ADR_PREVIEW_SDK=1``.
Run via ``tox -e ADR-device-int``.
"""

import os
import time

import pytest
from knack.log import get_logger

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr.conftest import (
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
    generate_device_id,
    generate_dps_name,
    generate_enrollment_group_id,
    generate_hub_name,
    generate_identity_name,
)

logger = get_logger(__name__)

DPS_PROVISIONING_HOST = "global.azure-devices-provisioning.net"


@pytest.mark.usefixtures("set_cwd")
class TestADRDeviceLifecycle(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Device provisioning + CRUD + revoke via CLI.

    Uses the preview azure-iot-device SDK to register a device with CSR
    through DPS, then exercises list/show/update/revoke commands.
    """

    @pytest.mark.skipif(
        not os.environ.get("ADR_PREVIEW_SDK"),
        reason=(
            "Device lifecycle requires azure-iot-device preview SDK with CSR support "
            "(feature/dps-csr-preview). Set ADR_PREVIEW_SDK=1 or run via tox -e ADR-device-int."
        ),
    )
    def test_adr_device_provision_crud_and_revoke(self):
        """Provision a device with CSR via preview SDK, then test list/show/update/revoke via CLI."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        hub_name = generate_hub_name()
        dps_name = generate_dps_name()
        identity_name = generate_identity_name()
        device_id = generate_device_id()
        enrollment_group_id = generate_enrollment_group_id()

        try:
            infra = self.setup_full_infra(
                resource_group=rg,
                namespace_name=namespace_name,
                hub_name=hub_name,
                identity_name=identity_name,
            )
            infra = self.setup_dps_with_sync(
                infra=infra,
                resource_group=rg,
                namespace_name=namespace_name,
                dps_name=dps_name,
                device_id=device_id,
                enrollment_group_id=enrollment_group_id,
            )

            # Register device via preview SDK with CSR
            from cryptography import x509 as crypto_x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.x509.oid import NameOID

            # Generate EC P-256 key pair and CSR
            private_key = ec.generate_private_key(ec.SECP256R1())
            csr = (
                crypto_x509.CertificateSigningRequestBuilder()
                .subject_name(crypto_x509.Name([
                    crypto_x509.NameAttribute(NameOID.COMMON_NAME, device_id),
                ]))
                .sign(private_key, hashes.SHA256())
            )
            csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode()

            # Retrieve the individual enrollment's symmetric key
            enrollment_keys = self.cmd(
                f"iot dps enrollment show --dps-name {dps_name} -g {rg} "
                f"--enrollment-id {device_id} --show-keys"
            ).get_output_in_json()
            sym_key = enrollment_keys["attestation"]["symmetricKey"]["primaryKey"]
            id_scope = infra["id_scope"]

            from azure.iot.device import ProvisioningDeviceClient

            client = ProvisioningDeviceClient.create_from_symmetric_key(
                provisioning_host=DPS_PROVISIONING_HOST,
                registration_id=device_id,
                id_scope=id_scope,
                symmetric_key=sym_key,
            )
            client.client_certificate_signing_request = csr_pem
            result = client.register()
            assert result.status == "assigned", (
                f"DPS registration failed: status={result.status}"
            )

            def device_cmd(action):
                """Run ``iot adr ns device <action>`` against the test namespace."""
                return self.cmd(f"iot adr ns device {action} --ns {namespace_name} -g {rg}")

            # Poll until device appears (ZTP provisioning is async)
            max_polls = 40
            devices = []
            for _poll in range(1, max_polls + 1):
                devices = device_cmd("list").get_output_in_json()
                if devices:
                    break
                time.sleep(15)

            assert len(devices) >= 1, (
                f"Device '{device_id}' never appeared in namespace after provisioning."
            )
            assert device_id in [d["name"] for d in devices]

            device = device_cmd(f"show -n {device_id}").get_output_in_json()
            assert device["name"] == device_id

            # Assign the credential policy so revoke has a policy to act on
            updated_dev = device_cmd(
                f"update -n {device_id} --policy-resource-id {infra['policy_resource_id']}"
            ).get_output_in_json()
            assert updated_dev.get("policy"), (
                f"Policy assignment failed: {updated_dev}"
            )

            # Disable then re-enable
            for val, expected in [("false", False), ("true", True)]:
                updated = device_cmd(f"update -n {device_id} --enabled {val}").get_output_in_json()
                assert updated.get("enabled") is expected

            # Update OS version
            updated = device_cmd(f"update -n {device_id} --os-version 2.0.1").get_output_in_json()
            assert updated.get("operatingSystemVersion") == "2.0.1", (
                f"OS version not updated: {updated}"
            )

            # Update multiple properties in one call
            updated = device_cmd(
                f"update -n {device_id} --enabled false --os-version 3.0.0 --tags env=test"
            ).get_output_in_json()
            assert updated.get("enabled") is False, f"Expected enabled=False, got {updated.get('enabled')}"
            assert updated.get("operatingSystemVersion") == "3.0.0", (
                f"OS version not updated in multi-prop call: {updated}"
            )
            assert updated.get("tags", {}).get("env") == "test", (
                f"Tags not updated in multi-prop call: {updated.get('tags')}"
            )
            # Re-enable for revoke tests
            device_cmd(f"update -n {device_id} --enabled true")

            # Revoke scenarios
            def revoke_and_check(revoke_args, expected_enabled):
                """Revoke device credentials and verify enabled state."""
                device_cmd(f"revoke -n {device_id} {revoke_args} -y")
                if expected_enabled is not None:
                    d = device_cmd(f"show -n {device_id}").get_output_in_json()
                    assert d.get("enabled") is expected_enabled, (
                        f"expected enabled={expected_enabled}, got {d.get('enabled')}"
                    )

            # Basic revoke -- device stays enabled
            revoke_and_check("", expected_enabled=True)

            # Revoke --disable -- device becomes disabled
            revoke_and_check("--disable", expected_enabled=False)

            # Revoke already-disabled device -- should succeed
            revoke_and_check("", expected_enabled=None)

            # Revoke --disable false -- device stays disabled
            revoke_and_check("--disable false", expected_enabled=False)

            # Re-enable then revoke -- verify idempotency
            device_cmd(f"update -n {device_id} --enabled true")
            revoke_and_check("", expected_enabled=True)

            # Revoke nonexistent device -- expect failure
            self.cmd(
                f"iot adr ns device revoke -n nonexistent-device --ns {namespace_name} -g {rg} -y",
                expect_failure=True,
            )

        finally:
            self.cleanup_full_infra(
                resource_group=rg,
                hub_name=hub_name,
                namespace_name=namespace_name,
                identity_name=identity_name,
                dps_name=dps_name,
            )


@pytest.mark.usefixtures("set_cwd")
class TestADRDeviceEdgeCases(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Negative and edge-case device tests that don't require DPS or the preview SDK."""

    def test_adr_device_negative_and_edge_cases(self):
        """Verify device command behavior for empty namespaces, nonexistent resources."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            self.cmd(
                f"iot adr ns create -n {namespace_name} -g {rg} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )

            # Device list on empty namespace returns an empty list
            devices = self.cmd(
                f"iot adr ns device list --ns {namespace_name} -g {rg}"
            ).get_output_in_json()
            assert isinstance(devices, list)
            assert len(devices) == 0, (
                f"Expected empty device list on fresh namespace, got {len(devices)} devices"
            )

            # Show nonexistent device returns ResourceNotFound
            self.cmd(
                f"iot adr ns device show -n nonexistent-device --ns {namespace_name} -g {rg}",
                expect_failure=True,
            )

        finally:
            try:
                self.cmd(f"iot adr ns delete -n {namespace_name} -g {rg} -y")
            except Exception as e:
                logger.warning("Cleanup failed: %s", e)

        # Device list against a nonexistent namespace returns an empty list
        # (the ARM list API does not 404 for a missing parent resource).
        devices = self.cmd(
            f"iot adr ns device list --ns nonexistent-ns-{namespace_name} -g {rg}"
        ).get_output_in_json()
        assert isinstance(devices, list)
        assert len(devices) == 0
