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

from azext_iot.tests.adr._log import (  # noqa: F401 – re-exported for back-compat
    L,
    _fmt_duration,
    _log,
    timed_step,
)
from azext_iot.tests.adr.conftest import (
    CUSTOM_CERT_KEY_TYPE,
    CUSTOM_POLICY_NAME,
    RoleAssignmentHelper,
    TEST_LOCATION,
)


# Propagation delays (seconds)
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
        """Create UAMI -> ADR namespace (credential + policy) -> IoT Hub Gen2 with ADR link.

        Returns a dict with keys: subscription_id, identity_resource_id,
        identity_principal_id, adr_resource_id, hub_name, policy_name.
        """
        # UAMI
        with timed_step("Setup 1/6 ❯ Create UAMI"):
            uami_cmd = f"identity create -n {identity_name} -g {resource_group} --location {TEST_LOCATION}"
            _log(L.CMD, "az %s", uami_cmd)
            identity = self.cmd(uami_cmd).get_output_in_json()
            identity_resource_id = identity["id"]
            identity_principal_id = identity["principalId"]
            _log(L.RESULT, "principalId=%s", identity_principal_id)

            _log(L.CMD, "az account show")
            subscription_id = self.cmd("account show").get_output_in_json()["id"]
            _log(L.RESULT, "subscription=%s", subscription_id)

        # Hub RP Contributor on RG
        with timed_step("Setup 2/6 ❯ RBAC: Hub RP Contributor"):
            self.assign_hub_rp_contributor_role(subscription_id, resource_group)

        # ADR namespace with credential + default policy
        with timed_step("Setup 3/6 ❯ Create ADR Namespace"):
            ns_cmd = (
                f"iot adr ns create -n {namespace_name} -g {resource_group} "
                f"--location {TEST_LOCATION} --enable-credential-policy"
            )
            _log(L.CMD, "az %s", ns_cmd)
            namespace = self.cmd(ns_cmd).get_output_in_json()
            adr_resource_id = namespace["id"]

            assert namespace["properties"]["provisioningState"] == "Succeeded"
            _log(
                L.RESULT,
                "id=%s, identity=%s",
                adr_resource_id,
                namespace.get("identity", {}).get("type"),
            )

        # ADR RBAC for UAMI
        with timed_step("Setup 4/6 ❯ RBAC: ADR Roles for UAMI"):
            self.assign_adr_roles_to_identity(identity_principal_id, adr_resource_id)

        if use_default_policy:
            # Keep the auto-created 'default' policy as-is.
            policy_name = "default"
            with timed_step("Setup 5/6 ❯ Policy (keep default)"):
                policy_show_cmd = (
                    f"iot adr ns policy show --ns {namespace_name} -g {resource_group} "
                    f"--policy-name {policy_name}"
                )
                _log(L.CMD, "az %s", policy_show_cmd)
                policy = self.cmd(policy_show_cmd).get_output_in_json()
                _log(
                    L.RESULT,
                    "provisioningState=%s",
                    policy["properties"]["provisioningState"],
                )
        else:
            # Delete the auto-created default policy and create a named one.
            with timed_step(f"Setup 5/6 ❯ Policy (delete default -> create '{policy_name}')"):
                del_cmd = (
                    f"iot adr ns policy delete --ns {namespace_name} -g {resource_group} "
                    f"--policy-name default -y"
                )
                _log(L.CMD, "az %s", del_cmd)
                self.cmd(del_cmd)
                _log(L.RESULT, "ok")

                byor_flag = " --enable-byor" if enable_byor else ""
                cert_flag = "" if enable_byor else f" --cert-key-type {CUSTOM_CERT_KEY_TYPE}"
                create_cmd = (
                    f"iot adr ns policy create --ns {namespace_name} -g {resource_group} "
                    f"--policy-name {policy_name}{byor_flag}{cert_flag}"
                )
                _log(L.CMD, "az %s", create_cmd)
                policy = self.cmd(create_cmd).get_output_in_json()

                _log(
                    L.RESULT,
                    "provisioningState=%s",
                    policy["properties"]["provisioningState"],
                )

        # IoT Hub Gen2
        with timed_step("Setup 6/6 ❯ Create IoT Hub Gen2 (may take 3–5 min)"):
            hub_cmd = (
                f"iot hub create -n {hub_name} -g {resource_group} --sku GEN2 --location {TEST_LOCATION} "
                f"--mi-user-assigned {identity_resource_id} "
                f"--ns-resource-id {adr_resource_id} "
                f"--ns-identity-id {identity_resource_id}"
            )
            _log(L.CMD, "az %s", hub_cmd)
            _log(L.WARN, "Hub provisioning in progress -- this is the slowest step ...")
            hub = self.cmd(hub_cmd).get_output_in_json()

            assert hub["properties"]["state"] == "Active"
            _log(L.RESULT, "Hub state=Active")

            hub_show_cmd = f"iot hub show -n {hub_name} -g {resource_group}"
            _log(L.CMD, "az %s", hub_show_cmd)
            hub_show = self.cmd(hub_show_cmd).get_output_in_json()
            adr_props = hub_show.get("properties", {}).get("deviceRegistry", {})
            _log(
                L.RESULT,
                "ADR config: nsResourceId=%s",
                adr_props.get("namespaceResourceId"),
            )

        # Allow time for role assignments and hub-ADR link to propagate
        _log(L.WARN, "Waiting %ds for role/hub propagation ...", ROLE_PROPAGATION_DELAY)
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

        Returns the *infra* dict augmented with ``id_scope`` and
        ``policy_resource_id``.
        """
        hub_name = infra["hub_name"]
        identity_resource_id = infra["identity_resource_id"]
        adr_resource_id = infra["adr_resource_id"]
        subscription_id = infra["subscription_id"]
        policy_name = infra["policy_name"]

        # Create DPS with ADR integration
        with timed_step("Setup-DPS 1/4 ❯ Create DPS"):
            dps_cmd = (
                f"iot dps create --name {dps_name} -g {resource_group} --location {TEST_LOCATION} "
                f"--mi-user-assigned {identity_resource_id} "
                f"--ns-resource-id {adr_resource_id} "
                f"--ns-identity-id {identity_resource_id}"
            )
            _log(L.CMD, "az %s", dps_cmd)
            dps = self.cmd(dps_cmd).get_output_in_json()
            assert dps["properties"]["state"] == "Active"
            _log(L.RESULT, "DPS state=Active")

        # Link hub to DPS
        with timed_step("Setup-DPS 2/4 ❯ Link Hub to DPS"):
            link_cmd = (
                f"iot dps linked-hub create --dps-name {dps_name} -g {resource_group} "
                f"--hub-name {hub_name}"
            )
            _log(L.CMD, "az %s", link_cmd)
            self.cmd(link_cmd)
            _log(L.RESULT, "ok")

            dps_show_cmd = f"iot dps show --name {dps_name} -g {resource_group}"
            _log(L.CMD, "az %s", dps_show_cmd)
            dps_show = self.cmd(dps_show_cmd).get_output_in_json()
            infra["id_scope"] = dps_show["properties"]["idScope"]
            _log(L.RESULT, "idScope=%s", infra["id_scope"])

        # Create enrollment group with credential policy
        with timed_step("Setup-DPS 3/4 ❯ Create Enrollments"):
            eg_cmd = (
                f"iot dps enrollment-group create --dps-name {dps_name} -g {resource_group} "
                f"--enrollment-id {enrollment_group_id} "
                f"--credential-policy-name {policy_name}"
            )
            _log(L.CMD, "az %s", eg_cmd)
            self.cmd(eg_cmd)
            _log(L.RESULT, "Enrollment group '%s' created", enrollment_group_id)

            # Create individual enrollment with credential policy (symmetric key)
            ie_cmd = (
                f"iot dps enrollment create --dps-name {dps_name} -g {resource_group} "
                f"--enrollment-id {device_id} "
                f"--credential-policy-name {policy_name} "
                f"--attestation-type symmetrickey"
            )
            _log(L.CMD, "az %s", ie_cmd)
            self.cmd(ie_cmd)
            _log(L.RESULT, "Individual enrollment '%s' created", device_id)

        # Credential sync
        with timed_step("Setup-DPS 4/4 ❯ Credential Sync"):
            sync_cmd = f"iot adr ns credential sync --ns {namespace_name} -g {resource_group}"
            _log(L.CMD, "az %s", sync_cmd)
            sync_succeeded = False
            try:
                self.cmd(sync_cmd)
                sync_succeeded = True
                _log(L.RESULT, "ok")
            except Exception as e:
                _log(
                    L.WARN,
                    "Sync LRO failed (may be false negative): %s",
                    str(e)[:300],
                )

            cert_list = self.get_hub_certificates(hub_name, resource_group)
            assert len(cert_list) >= 1, (
                f"No certificates on hub after sync (LRO succeeded={sync_succeeded}). "
                "This indicates a real sync failure."
            )
            _log(L.OK, "Certificates synced to hub")

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
        cert_cmd = f"iot hub certificate list --hub-name {hub_name} -g {resource_group}"
        _log(L.CMD, "az %s", cert_cmd)
        certs = self.cmd(cert_cmd).get_output_in_json()
        result = certs.get("value", [])
        _log(L.RESULT, "Certs: count=%d", len(result))
        return result

    def find_hub_cert_by_policy(
        self, hub_name: str, resource_group: str, policy_resource_id: str,
    ) -> Optional[dict]:
        """Find a hub certificate matching a given PolicyResourceId."""
        for cert in self.get_hub_certificates(hub_name, resource_group):
            if cert.get("properties", {}).get("PolicyResourceId") == policy_resource_id:
                return cert
        return None

    def check_hub_cert_auto_synced(
        self, hub_name: str, resource_group: str, policy_resource_id: str,
        context_label: str = "auto-sync check",
    ) -> Optional[dict]:
        """Probe whether a new ICA cert for *policy_resource_id* exists on the hub.

        Does NOT call credential sync — only reads the current hub cert list.
        Returns the cert dict if found, else None.
        """
        _log(L.STEP, "%s ❯ checking hub for cert (no manual sync)", context_label)
        cert = self.find_hub_cert_by_policy(hub_name, resource_group, policy_resource_id)
        if cert:
            _log(L.OK, "%s ❯ cert auto-synced to hub: %s", context_label, cert["name"])
        else:
            _log(L.WARN, "%s ❯ cert NOT auto-synced to hub (not found)", context_label)
        return cert

    def get_hub_device_identity(
        self, hub_name: str, resource_group: str, device_id: str,
    ) -> dict:
        """Return the IoT Hub device identity for a given device."""
        cmd = f"iot hub device-identity show -n {hub_name} -g {resource_group} -d {device_id}"
        _log(L.CMD, "az %s", cmd)
        result = self.cmd(cmd).get_output_in_json()
        _log(L.RESULT, "Hub device auth type=%s", result.get("authentication", {}).get("type"))
        return result

    def build_policy_resource_id(
        self, subscription_id: str, resource_group: str, namespace_name: str, policy_name: str,
    ) -> str:
        """Build the ARM resource ID for a credential policy."""
        return (
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers/"
            f"Microsoft.DeviceRegistry/namespaces/{namespace_name}/credentials/"
            f"default/policies/{policy_name}"
        )

    def setup_namespace_with_policy(
        self, namespace_name: str, resource_group: str,
        policy_name: str = "default", enable_byor: bool = False,
    ) -> dict:
        """Create ADR namespace + credential + policy (lightweight setup without hub).

        Returns the policy resource JSON.
        """
        mode = "BYOR" if enable_byor else f"standard (cert-key-type={CUSTOM_CERT_KEY_TYPE})"
        _log(
            L.STEP,
            "Lightweight Setup ❯ Namespace + Credential + Policy (policy=%s, mode=%s)",
            policy_name, mode,
        )
        setup_start = time.monotonic()
        ns_cmd = f"iot adr ns create -n {namespace_name} -g {resource_group} --location {TEST_LOCATION}"
        _log(L.CMD, "az %s", ns_cmd)
        self.cmd(ns_cmd)
        _log(L.RESULT, "ok")

        cred_cmd = f"iot adr ns credential create --ns {namespace_name} -g {resource_group}"
        _log(L.CMD, "az %s", cred_cmd)
        self.cmd(cred_cmd)
        _log(L.RESULT, "ok")

        byor_flag = " --enable-byor" if enable_byor else f" --cert-key-type {CUSTOM_CERT_KEY_TYPE}"
        policy_cmd = (
            f"iot adr ns policy create --ns {namespace_name} -g {resource_group} "
            f"--policy-name {policy_name}{byor_flag}"
        )
        _log(L.CMD, "az %s", policy_cmd)
        result = self.cmd(policy_cmd).get_output_in_json()
        _log(L.RESULT, "provisioningState=%s", result["properties"]["provisioningState"])
        _log("_time", "(%s)", _fmt_duration(time.monotonic() - setup_start))
        return result

    def activate_byor_policy(
        self, namespace_name: str, resource_group: str,
        policy_name: str, csr_pem: str,
    ) -> dict:
        """Sign a BYOR CSR with a test CA, activate the policy, and return updated policy JSON."""
        activate_start = time.monotonic()
        _log(L.CMD, "[local] Signing CSR with test CA via openssl ...")
        chain_pem = sign_csr_with_ca(csr_pem)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write(chain_pem)
            cert_file = f.name
        _log(L.RESULT, "Certificate chain written to %s", cert_file)
        try:
            activate_cmd = (
                f"iot adr ns policy activate-byor --ns {namespace_name} -g {resource_group} "
                f"--policy-name {policy_name} --certificate-chain-file {cert_file}"
            )
            _log(L.CMD, "az %s", activate_cmd)
            self.cmd(activate_cmd)
            _log(L.RESULT, "ok")
        finally:
            os.unlink(cert_file)
        show_cmd = (
            f"iot adr ns policy show --ns {namespace_name} -g {resource_group} "
            f"--policy-name {policy_name}"
        )
        _log(L.CMD, "az %s", show_cmd)
        result = self.cmd(show_cmd).get_output_in_json()
        _log(L.RESULT, "provisioningState=%s", result["properties"]["provisioningState"])
        _log("_time", "(%s)", _fmt_duration(time.monotonic() - activate_start))
        return result

    def cleanup_namespace(self, namespace_name: str, resource_group: str):
        """Delete just the ADR namespace (lightweight tests)."""
        with timed_step("Cleanup ❯ Delete Namespace"):
            cleanup_cmd = f"iot adr ns delete -n {namespace_name} -g {resource_group} -y"
            _log(L.CMD, "az %s", cleanup_cmd)
            try:
                self.cmd(cleanup_cmd)
                _log(L.RESULT, "ok")
            except Exception as e:
                _log(L.WARN, "Cleanup failed: %s", e)

    def cleanup_full_infra(
        self,
        resource_group: str,
        hub_name: Optional[str] = None,
        namespace_name: Optional[str] = None,
        identity_name: Optional[str] = None,
        dps_name: Optional[str] = None,
    ):
        """Best-effort cleanup of all infrastructure resources."""
        _log(L.STEP, "Cleanup ❯ Delete All Infrastructure")
        cleanup_start = time.monotonic()
        for label, cmd in [
            ("DPS", f"iot dps delete --name {dps_name} -g {resource_group}" if dps_name else None),
            ("IoT Hub", f"iot hub delete -n {hub_name} -g {resource_group}" if hub_name else None),
            ("ADR namespace", f"iot adr ns delete -n {namespace_name} -g {resource_group} -y" if namespace_name else None),
            ("UAMI", f"identity delete -n {identity_name} -g {resource_group}" if identity_name else None),
        ]:
            if cmd:
                _log(L.CMD, "az %s", cmd)
                try:
                    self.cmd(cmd)
                    _log(L.RESULT, "%s deleted", label)
                except Exception as e:
                    _log(L.WARN, "%s cleanup failed: %s", label, e)
        _log("_time", "(%s)", _fmt_duration(time.monotonic() - cleanup_start))
