# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Shared helpers for ADR integration tests that require Azure infrastructure.

Contains:
- ``ADRHubInfraHelper``: setup / teardown for tests needing an ADR namespace
  linked to an IoT Hub (UAMI, namespace, credential, policy, Hub Gen2).
- ``sign_csr_with_ca``: sign a BYOR CSR with a freshly generated EC CA via openssl.
- Policy JSON extraction helpers (``get_byor_config``, ``get_ca_config``).
"""

import os
import subprocess
import tempfile
import time
from typing import Dict, List, Optional

from knack.log import get_logger

from azext_iot.tests.adr.conftest import (
    CUSTOM_CERT_KEY_TYPE,
    CUSTOM_POLICY_NAME,
    RoleAssignmentHelper,
    TEST_LOCATION,
)

logger = get_logger(__name__)

# Propagation delays (seconds) for Azure resource readiness
ROLE_PROPAGATION_DELAY = 30
POLICY_PROPAGATION_DELAY = 15


def get_byor_config(policy: dict) -> dict:
    """Extract the bringYourOwnRoot config from a policy response."""
    return (
        policy["properties"]["certificate"]["certificateAuthorityConfiguration"]["bringYourOwnRoot"]
    )


def get_ca_config(policy: dict) -> dict:
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
        with open(paths["csr"], "w", encoding="utf-8") as f:
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
        with open(paths["ext"], "w", encoding="utf-8") as f:
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
        with open(paths["signed"], encoding="utf-8") as f:
            signed = f.read()
        with open(paths["ca_cert"], encoding="utf-8") as f:
            ca = f.read()
        return signed + ca


class ADRHubInfraHelper(RoleAssignmentHelper):
    """Setup / teardown helpers for tests that need an ADR namespace linked to an IoT Hub.

    Inherits RBAC helpers from ``RoleAssignmentHelper`` and adds:
    - Full infrastructure setup: UAMI -> ADR namespace -> credential -> policy -> IoT Hub Gen2 w/ ADR link
    - Hub certificate listing for post-sync / post-revoke verification
    - Cleanup for namespace-only or full infrastructure (Hub + UAMI + namespace)
    """

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
        """Create UAMI -> ADR namespace (with credential+policy) -> IoT Hub Gen2 with ADR link.

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
        logger.warning("[setup] Waiting %ds for role/hub propagation ...", ROLE_PROPAGATION_DELAY)
        time.sleep(ROLE_PROPAGATION_DELAY)

        return {
            "subscription_id": subscription_id,
            "identity_resource_id": identity_resource_id,
            "identity_principal_id": identity_principal_id,
            "adr_resource_id": adr_resource_id,
            "hub_name": hub_name,
            "policy_name": policy_name,
        }

    # --- DPS + enrollment + credential sync ---

    def setup_dps_with_sync(
        self,
        infra: Dict[str, str],
        resource_group: str,
        namespace_name: str,
        dps_name: str,
        device_id: str,
        enrollment_group_id: str,
    ) -> Dict[str, str]:
        """Create DPS with ADR link, hub link, enrollments, and credential sync.

        Call after ``setup_full_infra`` to add DPS + enrollment infrastructure.
        Returns the *infra* dict augmented with ``id_scope`` and
        ``policy_resource_id``.
        """
        hub_name = infra["hub_name"]
        identity_resource_id = infra["identity_resource_id"]
        adr_resource_id = infra["adr_resource_id"]
        subscription_id = infra["subscription_id"]
        policy_name = infra["policy_name"]

        # Create DPS with ADR integration
        logger.warning("[setup-dps] Creating DPS '%s' ...", dps_name)
        dps = self.cmd(
            f"iot dps create --name {dps_name} -g {resource_group} --location {TEST_LOCATION} "
            f"--mi-user-assigned {identity_resource_id} "
            f"--ns-resource-id {adr_resource_id} "
            f"--ns-identity-id {identity_resource_id}"
        ).get_output_in_json()
        assert dps["properties"]["state"] == "Active"

        # Link hub to DPS
        logger.warning("[setup-dps] Linking hub '%s' to DPS ...", hub_name)
        self.cmd(
            f"iot dps linked-hub create --dps-name {dps_name} -g {resource_group} "
            f"--hub-name {hub_name}"
        )

        dps_show = self.cmd(
            f"iot dps show --name {dps_name} -g {resource_group}"
        ).get_output_in_json()
        infra["id_scope"] = dps_show["properties"]["idScope"]

        # Create enrollment group with credential policy
        logger.warning(
            "[setup-dps] Creating enrollment group '%s' (policy=%s) ...",
            enrollment_group_id, policy_name,
        )
        self.cmd(
            f"iot dps enrollment-group create --dps-name {dps_name} -g {resource_group} "
            f"--enrollment-id {enrollment_group_id} "
            f"--credential-policy-name {policy_name}"
        )

        # Create individual enrollment with credential policy (symmetric key)
        logger.warning("[setup-dps] Creating individual enrollment '%s' ...", device_id)
        self.cmd(
            f"iot dps enrollment create --dps-name {dps_name} -g {resource_group} "
            f"--enrollment-id {device_id} "
            f"--credential-policy-name {policy_name} "
            f"--attestation-type symmetrickey"
        )

        # Credential sync — push CA certs to IoT Hub
        logger.warning("[setup-dps] Running credential sync ...")
        sync_succeeded = False
        try:
            self.cmd(
                f"iot adr ns credential sync --ns {namespace_name} -g {resource_group}"
            )
            sync_succeeded = True
            logger.warning("[setup-dps] Sync: SUCCESS")
        except Exception as e:
            # Known centraluseuap issue: sync LRO reports "Failed" but certs
            # may still land on the hub.
            logger.warning(
                "[setup-dps] Sync LRO FAILED (may be false negative): %s",
                str(e)[:300],
            )

        # Verify certificates landed on hub
        cert_list = self.get_hub_certificates(hub_name, resource_group)
        logger.warning("[setup-dps] Certificates on hub: count=%d", len(cert_list))
        assert len(cert_list) >= 1, (
            f"No certificates on hub after sync (LRO succeeded={sync_succeeded}). "
            "This indicates a real sync failure."
        )

        # Build and verify policy resource ID
        infra["policy_resource_id"] = self.build_policy_resource_id(
            subscription_id, resource_group, namespace_name, policy_name,
        )
        assert self.find_hub_cert_by_policy(
            hub_name, resource_group, infra["policy_resource_id"],
        ), (
            f"Certificate for policy not found on hub. "
            f"Expected PolicyResourceId={infra['policy_resource_id']}"
        )

        return infra

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
        dps_name: Optional[str] = None,
    ):
        """Best-effort cleanup of all infrastructure resources.

        DPS is deleted first because it may hold a linked-hub reference to the IoT Hub.
        """
        for label, cmd in [
            ("DPS", f"iot dps delete --name {dps_name} -g {resource_group}" if dps_name else None),
            ("IoT Hub", f"iot hub delete -n {hub_name} -g {resource_group}" if hub_name else None),
            ("ADR namespace", f"iot adr ns delete -n {namespace_name} -g {resource_group} -y" if namespace_name else None),
            ("UAMI", f"identity delete -n {identity_name} -g {resource_group}" if identity_name else None),
        ]:
            if cmd:
                try:
                    self.cmd(cmd)
                except Exception as e:
                    logger.warning("Cleanup failed for %s: %s", label, e)
