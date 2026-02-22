# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR device lifecycle integration tests.

Provisions a device via the preview azure-iot-device SDK with CSR support,
then validates device list/show/update/revoke via CLI.

Requires the preview azure-iot-device SDK (feature/dps-csr-preview) and
ADR_PREVIEW_SDK=1 environment variable.  Run via ``tox -e ADR-device-int``.
"""

import os
import time

import pytest
from knack.log import get_logger

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr.conftest import (
    TEST_RG,
    generate_adr_namespace_name,
    generate_device_id,
    generate_dps_name,
    generate_enrollment_group_id,
    generate_hub_name,
    generate_identity_name,
)

logger = get_logger(__name__)

# DPS provisioning host -- canary endpoint for preview API features.
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
    def test_adr_device_certmgmt_lifecycle(self):
        """Provision a device with CSR via preview SDK, then test list/show/update/revoke via CLI."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        hub_name = generate_hub_name()
        dps_name = generate_dps_name()
        identity_name = generate_identity_name()
        device_id = generate_device_id()
        enrollment_group_id = generate_enrollment_group_id()

        logger.warning(
            "=== [device-lifecycle] ns=%s hub=%s dps=%s device=%s ===",
            namespace_name, hub_name, dps_name, device_id,
        )

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

            # === Register device via preview SDK with CSR ===
            logger.warning("[device] Provisioning device with CSR via preview SDK")

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
            logger.warning("  Generated CSR for device: %s", device_id)

            # Retrieve the individual enrollment's symmetric key
            enrollment_keys = self.cmd(
                f"iot dps enrollment show --dps-name {dps_name} -g {rg} "
                f"--enrollment-id {device_id} --show-keys"
            ).get_output_in_json()
            sym_key = enrollment_keys["attestation"]["symmetricKey"]["primaryKey"]
            id_scope = infra["id_scope"]

            # Register with the preview SDK (sets CSR on the client before .register())
            from azure.iot.device import ProvisioningDeviceClient

            client = ProvisioningDeviceClient.create_from_symmetric_key(
                provisioning_host=DPS_PROVISIONING_HOST,
                registration_id=device_id,
                id_scope=id_scope,
                symmetric_key=sym_key,
            )
            client.client_certificate_signing_request = csr_pem
            result = client.register()

            logger.warning(
                "  DPS registration: status=%s hub=%s",
                result.status,
                result.registration_state.assigned_hub if result.registration_state else "N/A",
            )
            assert result.status == "assigned", (
                f"DPS registration failed: status={result.status}"
            )

            # === Device CRUD + revoke via CLI ===

            def device_cmd(action):
                """Run an ``iot adr ns device <action>`` command against the test namespace."""
                return self.cmd(f"iot adr ns device {action} --ns {namespace_name} -g {rg}")

            # Device list/show -- poll until device appears (ZTP is async)
            max_polls = 40
            logger.warning("[device] Waiting for device in namespace (max %d polls)", max_polls)
            devices = []
            for poll in range(1, max_polls + 1):
                devices = device_cmd("list").get_output_in_json()
                if devices:
                    logger.warning("  Device appeared after %d poll(s)", poll)
                    break
                logger.warning("  Poll %d/%d: empty, waiting 15s...", poll, max_polls)
                time.sleep(15)

            assert len(devices) >= 1, (
                f"Device '{device_id}' never appeared in namespace after provisioning."
            )
            assert device_id in [d["name"] for d in devices]

            device = device_cmd(f"show -n {device_id}").get_output_in_json()
            assert device["name"] == device_id
            logger.warning(
                "  Device show: enabled=%s policy=%s",
                device.get("enabled"), device.get("policy"),
            )

            # Assign the credential policy to the device.
            # DPS credentialPolicyName controls which CA signs the leaf cert, but the ADR device
            # resource needs an explicit policy association for revoke to work.
            logger.warning("  Assigning policy to device: %s", infra["policy_resource_id"])
            updated_dev = device_cmd(
                f"update -n {device_id} --policy-resource-id {infra['policy_resource_id']}"
            ).get_output_in_json()
            assert updated_dev.get("policy"), (
                f"Policy assignment failed -- device has no policy after update: {updated_dev}"
            )
            logger.warning("  Policy assigned: %s", updated_dev["policy"])

            # Device update -- disable then re-enable
            logger.warning("[device] Device update (disable/enable)")
            for val, expected in [("false", False), ("true", True)]:
                updated = device_cmd(f"update -n {device_id} --enabled {val}").get_output_in_json()
                logger.warning("  update --enabled %s -> enabled=%s", val, updated.get("enabled"))
                assert updated.get("enabled") is expected

            # Device revoke scenarios
            logger.warning("[device] Device revoke scenarios")

            def revoke_and_check(label, revoke_args, expected_enabled):
                """Revoke device credentials and verify enabled state."""
                logger.warning("  %s", label)
                device_cmd(f"revoke -n {device_id} {revoke_args} -y")
                if expected_enabled is not None:
                    d = device_cmd(f"show -n {device_id}").get_output_in_json()
                    assert d.get("enabled") is expected_enabled, (
                        f"{label}: expected enabled={expected_enabled}, got {d.get('enabled')}"
                    )

            # 1/6 Basic revoke -- device stays enabled
            revoke_and_check("[1/6] Basic revoke", "", expected_enabled=True)

            # 2/6 Revoke --disable -- device becomes disabled
            revoke_and_check("[2/6] Revoke --disable", "--disable", expected_enabled=False)

            # 3/6 Revoke already-disabled device -- should succeed (no state check needed)
            revoke_and_check("[3/6] Revoke already-disabled", "", expected_enabled=None)

            # 4/6 Revoke --disable false -- device stays disabled
            revoke_and_check("[4/6] Revoke --disable false", "--disable false", expected_enabled=False)

            # 5/6 Re-enable then revoke -- verify idempotency
            logger.warning("  [5/6] Re-enable + revoke (idempotency)")
            device_cmd(f"update -n {device_id} --enabled true")
            revoke_and_check("[5/6] Revoke after re-enable", "", expected_enabled=True)

            # 6/6 Revoke nonexistent device -- expect failure
            logger.warning("  [6/6] Revoke nonexistent device (expect failure)")
            self.cmd(
                f"iot adr ns device revoke -n nonexistent-device --ns {namespace_name} -g {rg} -y",
                expect_failure=True,
            )

            logger.warning("=== Device lifecycle test PASSED ===")

        finally:
            self.cleanup_full_infra(
                resource_group=rg,
                hub_name=hub_name,
                namespace_name=namespace_name,
                identity_name=identity_name,
                dps_name=dps_name,
            )
