# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
"""
ADR Certificate Management integration tests.

Two test methods share the same infrastructure setup:

- test_adr_certmgmt_infrastructure
    Always runs. Validates namespace, credential, policy, hub, DPS, enrollment,
    and credential-sync (steps 1-12). No preview SDK required.

- test_adr_device_certmgmt_lifecycle
    Runs ONLY in the ADR-device-int tox environment (ADR_PREVIEW_SDK=1).
    Provisions a device via the preview azure-iot-device SDK with CSR support,
    then validates device list/show/update/revoke via CLI (steps 1-16).
"""

import os
import time

import pytest
from knack.log import get_logger

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr.conftest import (
    CUSTOM_CERT_KEY_TYPE,
    CUSTOM_CERT_SUBJECT,
    CUSTOM_CERT_VALIDITY_DAYS,
    CUSTOM_POLICY_NAME,
    RoleAssignmentMixin,
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

# DPS provisioning host — canary endpoint for preview API features.
DPS_PROVISIONING_HOST = "global.azure-devices-provisioning.net"


@pytest.mark.usefixtures("set_cwd")
class TestADRCertificateManagementLifecycle(RoleAssignmentMixin, CaptureOutputLiveScenarioTest):

    # --- Infrastructure setup (shared by tests) ---

    def _setup_infrastructure(self, rg, namespace_name, hub_name, dps_name,
                              identity_name, device_id, enrollment_group_id,
                              total_steps=12):
        """Create all Azure resources for ADR certificate management testing.

        Returns an ``infra`` dict with keys: subscription_id, identity_resource_id,
        identity_principal_id, adr_resource_id, policy_resource_id, id_scope.
        """
        infra = {}

        # [1] Create user-assigned managed identity
        logger.warning("[1/%d] Creating user-assigned managed identity: %s", total_steps, identity_name)
        identity = self.cmd(
            f"identity create -n {identity_name} -g {rg} --location {TEST_LOCATION}"
        ).get_output_in_json()
        infra["identity_resource_id"] = identity["id"]
        infra["identity_principal_id"] = identity["principalId"]
        logger.warning("  principalId=%s", infra["identity_principal_id"])

        subscription_info = self.cmd("account show").get_output_in_json()
        infra["subscription_id"] = subscription_info["id"]

        # [2] Assign IoT Hub RP contributor role
        logger.warning("[2/%d] Assigning IoT Hub RP contributor role", total_steps)
        self.assign_hub_rp_contributor_role(infra["subscription_id"], rg)

        # [3] Create ADR namespace with --enable-credential-policy
        logger.warning("[3/%d] Creating ADR namespace: %s with --enable-credential-policy", total_steps, namespace_name)
        namespace = self.cmd(
            f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION} --enable-credential-policy"
        ).get_output_in_json()
        infra["adr_resource_id"] = namespace["id"]
        logger.warning("  provisioningState=%s", namespace["properties"]["provisioningState"])

        assert namespace["name"] == namespace_name
        assert namespace["properties"]["provisioningState"] == "Succeeded"
        assert namespace["location"] == TEST_LOCATION.lower()
        assert namespace["identity"]["type"] == "SystemAssigned"
        assert "principalId" in namespace["identity"]
        assert "tenantId" in namespace["identity"]

        # [4] Assign ADR roles to identity
        logger.warning("[4/%d] Assigning ADR roles to identity", total_steps)
        self.assign_adr_roles_to_identity(infra["identity_principal_id"], infra["adr_resource_id"])

        # [5] Verify/create credential
        credential_exists = False
        try:
            self.cmd(f"iot adr ns credential show --ns {namespace_name} -g {rg}").get_output_in_json()
            credential_exists = True
            logger.warning("[5/%d] Credential exists (created by --enable-credential-policy)", total_steps)
        except Exception as e:
            logger.warning("[5/%d] Credential not found, creating explicitly: %s", total_steps, str(e)[:200])

        if not credential_exists:
            self.retry_cmd(f"iot adr ns credential create --ns {namespace_name} -g {rg}").get_output_in_json()

        # [6] Replace default policy with custom policy
        try:
            self.cmd(f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name default").get_output_in_json()
            logger.warning("[6/%d] Deleting default policy, creating custom policy: %s", total_steps, CUSTOM_POLICY_NAME)
            self.cmd(f"iot adr ns policy delete --ns {namespace_name} -g {rg} --policy-name default -y")
        except Exception:
            logger.warning("[6/%d] No default policy found, creating custom policy: %s", total_steps, CUSTOM_POLICY_NAME)

        custom_policy = self.retry_cmd(
            f"iot adr ns policy create --ns {namespace_name} -g {rg} "
            f"--policy-name {CUSTOM_POLICY_NAME} "
            f"--cert-subject '{CUSTOM_CERT_SUBJECT}' "
            f"--cert-validity-days {CUSTOM_CERT_VALIDITY_DAYS} "
            f"--cert-key-type {CUSTOM_CERT_KEY_TYPE}"
        ).get_output_in_json()

        assert custom_policy["name"] == CUSTOM_POLICY_NAME
        assert custom_policy["properties"]["provisioningState"] == "Succeeded"
        leaf_cfg = custom_policy["properties"]["certificate"]["leafCertificateConfiguration"]
        ca_cfg = custom_policy["properties"]["certificate"]["certificateAuthorityConfiguration"]
        assert leaf_cfg["validityPeriodInDays"] == CUSTOM_CERT_VALIDITY_DAYS
        assert ca_cfg["keyType"] == CUSTOM_CERT_KEY_TYPE
        assert "subject" in ca_cfg

        # [7] Create IoT Hub with ADR integration
        logger.warning("[7/%d] Creating IoT Hub: %s (GEN2)", total_steps, hub_name)
        hub = self.cmd(
            f"iot hub create -n {hub_name} -g {rg} --sku GEN2 --location {TEST_LOCATION} "
            f"--mi-user-assigned {infra['identity_resource_id']} "
            f"--ns-resource-id {infra['adr_resource_id']} "
            f"--ns-identity-id {infra['identity_resource_id']}"
        ).get_output_in_json()
        assert hub["name"] == hub_name
        assert hub["properties"]["state"] == "Active"

        hub_show = self.cmd(f"iot hub show -n {hub_name} -g {rg}").get_output_in_json()
        adr_props = hub_show["properties"]["deviceRegistry"]
        assert adr_props["identityResourceId"] == infra["identity_resource_id"]
        assert adr_props["namespaceResourceId"] == infra["adr_resource_id"]
        assert hub_show["identity"]["type"] == "UserAssigned"
        assert infra["identity_resource_id"] in hub_show["identity"]["userAssignedIdentities"]

        # [8] Create DPS with ADR integration
        logger.warning("[8/%d] Creating DPS: %s", total_steps, dps_name)
        dps = self.cmd(
            f"iot dps create --name {dps_name} -g {rg} --location {TEST_LOCATION} "
            f"--mi-user-assigned {infra['identity_resource_id']} "
            f"--ns-resource-id {infra['adr_resource_id']} "
            f"--ns-identity-id {infra['identity_resource_id']}"
        ).get_output_in_json()
        assert dps["name"] == dps_name
        assert dps["properties"]["state"] == "Active"

        # [9] Link IoT Hub to DPS
        logger.warning("[9/%d] Linking hub to DPS", total_steps)
        self.cmd(f"iot dps linked-hub create --dps-name {dps_name} -g {rg} --hub-name {hub_name}").get_output_in_json()

        dps_show = self.cmd(f"iot dps show --name {dps_name} -g {rg}").get_output_in_json()
        drn_props = dps_show["properties"]["deviceRegistryNamespace"]
        assert drn_props["authenticationType"] == "UserAssigned"
        assert drn_props["resourceId"] == infra["adr_resource_id"]
        assert drn_props["selectedUserAssignedIdentityResourceId"] == infra["identity_resource_id"]
        linked_hubs = dps_show["properties"]["iotHubs"]
        assert any(h["name"] == f"{hub_name}.azure-devices.net" for h in linked_hubs)
        infra["id_scope"] = dps_show["properties"]["idScope"]

        # [10] Create enrollment group with credential policy
        logger.warning("[10/%d] Creating enrollment group: %s", total_steps, enrollment_group_id)
        eg = self.cmd(
            f"iot dps enrollment-group create --dps-name {dps_name} -g {rg} "
            f"--enrollment-id {enrollment_group_id} "
            f"--credential-policy-name {CUSTOM_POLICY_NAME}"
        ).get_output_in_json()
        assert eg["enrollmentGroupId"] == enrollment_group_id
        assert eg["credentialPolicyName"] == CUSTOM_POLICY_NAME

        # [11] Create individual enrollment with credential policy
        logger.warning("[11/%d] Creating individual enrollment: %s", total_steps, device_id)
        ie = self.cmd(
            f"iot dps enrollment create --dps-name {dps_name} -g {rg} "
            f"--enrollment-id {device_id} "
            f"--credential-policy-name {CUSTOM_POLICY_NAME} "
            f"--attestation-type symmetrickey"
        ).get_output_in_json()
        assert ie["registrationId"] == device_id
        assert ie["credentialPolicyName"] == CUSTOM_POLICY_NAME
        assert ie["attestation"]["type"] == "symmetricKey"

        # [12] Credential sync — push CA certs to IoT Hub
        logger.warning("[12/%d] Running credential sync", total_steps)
        sync_succeeded = False
        try:
            self.cmd(f"iot adr ns credential sync --ns {namespace_name} -g {rg}")
            sync_succeeded = True
            logger.warning("  Sync LRO: SUCCESS")
        except Exception as e:
            # Known centraluseuap issue: sync LRO reports "Failed" but certs may still land.
            logger.warning("  Sync LRO: FAILED (may be false negative): %s", str(e)[:300])

        certificates = self.cmd(
            f"iot hub certificate list --hub-name {hub_name} -g {rg}"
        ).get_output_in_json()
        cert_list = certificates.get("value", [])
        logger.warning("  Certificates on hub: count=%d", len(cert_list))

        assert len(cert_list) >= 1, (
            f"No certificates on hub after sync (LRO succeeded={sync_succeeded}). "
            "This indicates a real sync failure."
        )

        infra["policy_resource_id"] = (
            f"/subscriptions/{infra['subscription_id']}/resourceGroups/{rg}/providers/"
            f"Microsoft.DeviceRegistry/namespaces/{namespace_name}/credentials/"
            f"default/policies/{CUSTOM_POLICY_NAME}"
        )
        matching = [c for c in cert_list if c["properties"]["PolicyResourceId"] == infra["policy_resource_id"]]
        assert matching, (
            f"Certificate for policy not found. Expected PolicyResourceId={infra['policy_resource_id']}, "
            f"got: {[c['properties'].get('PolicyResourceId') for c in cert_list]}"
        )

        return infra

    def _cleanup_resources(self, rg, namespace_name, hub_name, dps_name, identity_name):
        """Delete all test resources. Errors are logged but do not raise."""
        logger.warning("=== Cleanup ===")
        for label, cmd in [
            ("DPS", f"iot dps delete --name {dps_name} -g {rg}"),
            ("IoT Hub", f"iot hub delete -n {hub_name} -g {rg}"),
            ("Namespace", f"iot adr ns delete -n {namespace_name} -g {rg} -y"),
            ("Identity", f"identity delete -n {identity_name} -g {rg}"),
        ]:
            try:
                logger.warning("  Deleting %s ...", label)
                self.cmd(cmd)
            except Exception as e:
                logger.warning("  Failed to delete %s: %s", label, e)

    # --- Test: Infrastructure (always runs) ---

    def test_adr_certmgmt_infrastructure(self):
        """Validate ADR namespace, credential, policy, hub, DPS, enrollment, and sync."""
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        hub_name = generate_hub_name()
        dps_name = generate_dps_name()
        identity_name = generate_identity_name()
        device_id = generate_device_id()
        enrollment_group_id = generate_enrollment_group_id()

        logger.warning(
            "=== [infrastructure] ns=%s hub=%s dps=%s ===",
            namespace_name, hub_name, dps_name,
        )

        try:
            self._setup_infrastructure(
                rg, namespace_name, hub_name, dps_name,
                identity_name, device_id, enrollment_group_id,
                total_steps=12,
            )
            logger.warning("=== Infrastructure test PASSED ===")
        finally:
            self._cleanup_resources(rg, namespace_name, hub_name, dps_name, identity_name)

    # --- Test: Device lifecycle (preview azure-iot-device SDK for now) ---

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
            infra = self._setup_infrastructure(
                rg, namespace_name, hub_name, dps_name,
                identity_name, device_id, enrollment_group_id,
                total_steps=16,
            )

            # === Step 13: Register device via preview SDK with CSR ===
            logger.warning("[13/16] Provisioning device with CSR via preview SDK")

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

            # === Steps 14-16: Device CRUD + revoke via CLI ===

            def device_cmd(action):
                """Run an `iot adr ns device <action>` command against the test namespace."""
                return self.cmd(f"iot adr ns device {action} --ns {namespace_name} -g {rg}")

            # [14] Device list/show — poll until device appears (ZTP is async)
            max_polls = 40
            logger.warning("[14/16] Waiting for device in namespace (max %d polls)", max_polls)
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
            logger.warning("  Device show: enabled=%s policy=%s", device.get("enabled"), device.get("policy"))

            # Assign the credential policy to the device.
            # DPS credentialPolicyName controls which CA signs the leaf cert, but the ADR device
            # resource needs an explicit policy association for revoke to work.
            logger.warning("  Assigning policy to device: %s", infra["policy_resource_id"])
            updated_dev = device_cmd(
                f"update -n {device_id} --policy-resource-id {infra['policy_resource_id']}"
            ).get_output_in_json()
            assert updated_dev.get("policy"), (
                f"Policy assignment failed — device has no policy after update: {updated_dev}"
            )
            logger.warning("  Policy assigned: %s", updated_dev["policy"])

            # [15] Device update — disable then re-enable
            logger.warning("[15/16] Device update (disable/enable)")
            for val, expected in [("false", False), ("true", True)]:
                updated = device_cmd(f"update -n {device_id} --enabled {val}").get_output_in_json()
                logger.warning("  update --enabled %s -> enabled=%s", val, updated.get("enabled"))
                assert updated.get("enabled") is expected

            # [16] Device revoke scenarios
            logger.warning("[16/16] Device revoke scenarios")

            def revoke_and_check(label, revoke_args, expected_enabled):
                """Revoke device credentials and verify enabled state."""
                logger.warning("  %s", label)
                device_cmd(f"revoke -n {device_id} {revoke_args} -y")
                if expected_enabled is not None:
                    d = device_cmd(f"show -n {device_id}").get_output_in_json()
                    assert d.get("enabled") is expected_enabled, (
                        f"{label}: expected enabled={expected_enabled}, got {d.get('enabled')}"
                    )

            # 1/6 Basic revoke — device stays enabled
            revoke_and_check("[1/6] Basic revoke", "", expected_enabled=True)

            # 2/6 Revoke --disable — device becomes disabled
            revoke_and_check("[2/6] Revoke --disable", "--disable", expected_enabled=False)

            # 3/6 Revoke already-disabled device — should succeed (no state check needed)
            revoke_and_check("[3/6] Revoke already-disabled", "", expected_enabled=None)

            # 4/6 Revoke --disable false — device stays disabled
            revoke_and_check("[4/6] Revoke --disable false", "--disable false", expected_enabled=False)

            # 5/6 Re-enable then revoke — verify idempotency
            logger.warning("  [5/6] Re-enable + revoke (idempotency)")
            device_cmd(f"update -n {device_id} --enabled true")
            revoke_and_check("[5/6] Revoke after re-enable", "", expected_enabled=True)

            # 6/6 Revoke nonexistent device — expect failure
            logger.warning("  [6/6] Revoke nonexistent device (expect failure)")
            self.cmd(
                f"iot adr ns device revoke -n nonexistent-device --ns {namespace_name} -g {rg} -y",
                expect_failure=True,
            )

            logger.warning("=== Device lifecycle test PASSED ===")

        finally:
            self._cleanup_resources(rg, namespace_name, hub_name, dps_name, identity_name)
