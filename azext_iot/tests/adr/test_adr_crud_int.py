# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR namespace, credential, and policy CRUD integration tests.

Exercises the full create/show/list/update/delete lifecycle for each resource
type in a single test to minimise Azure resource creation overhead.
"""

import pytest

from azext_iot.adr.common import (
    DEFAULT_NS_POLICY_CERT_KEY_TYPE,
    DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS,
    DEFAULT_NS_POLICY_NAME,
)
from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._log import LogKind, _log
from azext_iot.tests.adr.conftest import (
    CUSTOM_CERT_KEY_TYPE,
    CUSTOM_CERT_UPDATE_VALIDITY_DAYS,
    CUSTOM_CERT_VALIDITY_DAYS,
    CUSTOM_POLICY_NAME,
    TEST_LOCATION,
    TEST_RG,
    generate_adr_namespace_name,
)


def _cert_config(policy: dict):
    """Extract (leaf_config, ca_config) from a policy JSON response."""
    cert = policy["properties"]["certificate"]
    return cert["leafCertificateConfiguration"], cert["certificateAuthorityConfiguration"]


@pytest.mark.usefixtures("set_cwd")
class TestADRCrudLifecycle(CaptureOutputLiveScenarioTest):
    """Namespace, credential, and policy CRUD lifecycle."""

    def test_adr_crud_lifecycle(self):
        _log(LogKind.TEST, "test_adr_crud_lifecycle")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()

        try:
            # Create ADR namespace with no credentials
            _log(LogKind.STEP, "Step 1 ❯ Create ADR Namespace")
            ns_cmd = f"iot adr ns create -n {namespace_name} -g {rg} --location {TEST_LOCATION}"
            _log(LogKind.CMD, "az %s", ns_cmd)
            namespace = self.cmd(ns_cmd).get_output_in_json()

            assert namespace["name"] == namespace_name
            assert namespace["location"] == TEST_LOCATION
            assert namespace["properties"]["provisioningState"] == "Succeeded"
            _log(LogKind.RESULT, "name=%s, provisioningState=Succeeded", namespace_name)

            # Show ADR namespace
            _log(LogKind.STEP, "Step 2 ❯ Show & List Namespace")
            show_cmd = f"iot adr ns show -n {namespace_name} -g {rg}"
            _log(LogKind.CMD, "az %s", show_cmd)
            namespace_show = self.cmd(show_cmd).get_output_in_json()

            assert namespace_show["name"] == namespace_name
            assert namespace_show["location"] == TEST_LOCATION
            assert namespace_show["properties"]["provisioningState"] == "Succeeded"
            _log(LogKind.OK, "Namespace show returned correctly")

            # List ADR namespaces in resource group
            list_cmd = f"iot adr ns list -g {rg}"
            _log(LogKind.CMD, "az %s", list_cmd)
            namespaces = self.cmd(list_cmd).get_output_in_json()

            assert isinstance(namespaces, list)
            ns_names = [ns["name"] for ns in namespaces]
            assert namespace_name in ns_names, (
                f"Namespace '{namespace_name}' not found in list: {ns_names}"
            )
            _log(LogKind.OK, "Namespace found in list (%d total)", len(namespaces))

            # Update ADR namespace tags
            _log(LogKind.STEP, "Step 3 ❯ Update Namespace Tags")
            update_cmd = f"iot adr ns update -n {namespace_name} -g {rg} --tags env=test purpose=ci"
            _log(LogKind.CMD, "az %s", update_cmd)
            updated_ns = self.cmd(update_cmd).get_output_in_json()

            assert updated_ns["name"] == namespace_name
            assert updated_ns["tags"]["env"] == "test"
            assert updated_ns["tags"]["purpose"] == "ci"
            _log(LogKind.OK, "Tags set: env=test, purpose=ci")

            # Update tags again (replace)
            update2_cmd = f"iot adr ns update -n {namespace_name} -g {rg} --tags owner=adr-tests"
            _log(LogKind.CMD, "az %s", update2_cmd)
            updated_ns2 = self.cmd(update2_cmd).get_output_in_json()

            assert updated_ns2["tags"]["owner"] == "adr-tests"
            # Previous tags should be replaced (not merged)
            assert "env" not in updated_ns2.get("tags", {})
            _log(LogKind.OK, "Tags replaced: owner=adr-tests (env removed)")

            # Verify no credential exists
            _log(LogKind.STEP, "Step 4 ❯ Credential CRUD")
            cred_show_cmd = f"iot adr ns credential show --ns {namespace_name} -g {rg}"
            _log(LogKind.CMD, "az %s  (expect failure)", cred_show_cmd)
            self.cmd(cred_show_cmd, expect_failure=True)
            _log(LogKind.OK, "No credential exists (expected)")

            # Create credential for the namespace
            cred_create_cmd = f"iot adr ns credential create --ns {namespace_name} -g {rg}"
            _log(LogKind.CMD, "az %s", cred_create_cmd)
            credential = self.cmd(cred_create_cmd).get_output_in_json()

            assert credential["name"] == "default"
            assert credential["location"] == TEST_LOCATION
            assert credential["properties"]["provisioningState"] == "Succeeded"
            _log(LogKind.RESULT, "credential created: name=default, provisioningState=Succeeded")

            # Show credential
            _log(LogKind.CMD, "az %s", cred_show_cmd)
            credential_show = self.cmd(cred_show_cmd).get_output_in_json()

            assert credential_show["name"] == "default"
            assert credential_show["location"] == TEST_LOCATION
            assert credential_show["properties"]["provisioningState"] == "Succeeded"
            _log(LogKind.OK, "Credential show returned correctly")

            credential_list = self.cmd(
                f"iot adr ns credential list --ns {namespace_name} -g {rg}"
            ).get_output_in_json()
            assert "default" in [item["name"] for item in credential_list]

            credential_update = self.cmd(
                f"iot adr ns credential update --ns {namespace_name} -g {rg} "
                "--tags phase=updated"
            ).get_output_in_json()
            assert credential_update["tags"]["phase"] == "updated"

            # Create default credential policy
            _log(LogKind.STEP, "Step 5 ❯ Default Policy CRUD")
            # TODO - once service issue is resolved, remove extra default inputs besides name
            policy_create_cmd = (
                f"iot adr ns policy create --ns {namespace_name} -g {rg} "
                f"--policy-name {DEFAULT_NS_POLICY_NAME} "
                f"--location {TEST_LOCATION} --tags kind=default "
                f"--cert-validity-days {DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS} "
                f"--cert-key-type {DEFAULT_NS_POLICY_CERT_KEY_TYPE}"
            )
            _log(LogKind.CMD, "az %s", policy_create_cmd)
            default_policy = self.cmd(policy_create_cmd).get_output_in_json()
            assert default_policy["name"] == DEFAULT_NS_POLICY_NAME
            assert default_policy["location"] == TEST_LOCATION
            assert default_policy["tags"]["kind"] == "default"
            assert default_policy["properties"]["provisioningState"] == "Succeeded"
            leaf, ca = _cert_config(default_policy)
            assert leaf["validityPeriodInDays"] == DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS
            assert ca["keyType"] == DEFAULT_NS_POLICY_CERT_KEY_TYPE
            _log(
                LogKind.RESULT, "policy=%s, keyType=%s, validityDays=%s",
                DEFAULT_NS_POLICY_NAME, DEFAULT_NS_POLICY_CERT_KEY_TYPE,
                DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS,
            )

            # Show default credential policy
            policy_show_cmd = (
                f"iot adr ns policy show --ns {namespace_name} -g {rg} "
                f"--policy-name {DEFAULT_NS_POLICY_NAME}"
            )
            _log(LogKind.CMD, "az %s", policy_show_cmd)
            default_policy_show = self.cmd(policy_show_cmd).get_output_in_json()

            assert default_policy_show["name"] == "default"
            assert default_policy_show["properties"]["provisioningState"] == "Succeeded"
            leaf, ca = _cert_config(default_policy_show)
            assert leaf["validityPeriodInDays"] == DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS
            assert ca["keyType"] == DEFAULT_NS_POLICY_CERT_KEY_TYPE
            _log(LogKind.OK, "Default policy show returned correctly")

            # Delete default policy
            del_cmd = f"iot adr ns policy delete --ns {namespace_name} -g {rg} --policy-name {DEFAULT_NS_POLICY_NAME} -y"
            _log(LogKind.CMD, "az %s", del_cmd)
            self.cmd(del_cmd)
            _log(LogKind.RESULT, "ok")

            # Create custom credential policy
            _log(LogKind.STEP, "Step 6 ❯ Custom Policy CRUD")
            custom_cmd = (
                f"iot adr ns policy create --ns {namespace_name} -g {rg} "
                f"--policy-name {CUSTOM_POLICY_NAME} "
                f"--location {TEST_LOCATION} --tags kind=custom "
                f"--cert-validity-days {CUSTOM_CERT_VALIDITY_DAYS} "
                f"--cert-key-type {CUSTOM_CERT_KEY_TYPE}"
            )
            _log(LogKind.CMD, "az %s", custom_cmd)
            custom_policy = self.cmd(custom_cmd).get_output_in_json()

            assert custom_policy["name"] == CUSTOM_POLICY_NAME
            assert custom_policy["location"] == TEST_LOCATION
            assert custom_policy["tags"]["kind"] == "custom"
            assert custom_policy["properties"]["provisioningState"] == "Succeeded"
            leaf, ca = _cert_config(custom_policy)
            assert leaf["validityPeriodInDays"] == CUSTOM_CERT_VALIDITY_DAYS
            assert ca["keyType"] == CUSTOM_CERT_KEY_TYPE
            _log(
                LogKind.RESULT, "policy=%s, keyType=%s, validityDays=%s",
                CUSTOM_POLICY_NAME, CUSTOM_CERT_KEY_TYPE, CUSTOM_CERT_VALIDITY_DAYS,
            )

            # Show custom credential policy
            custom_show_cmd = f"iot adr ns policy show --ns {namespace_name} -g {rg} --policy-name {CUSTOM_POLICY_NAME}"
            _log(LogKind.CMD, "az %s", custom_show_cmd)
            custom_policy_show = self.cmd(custom_show_cmd).get_output_in_json()

            assert custom_policy_show["name"] == CUSTOM_POLICY_NAME
            leaf, ca = _cert_config(custom_policy_show)
            assert leaf["validityPeriodInDays"] == CUSTOM_CERT_VALIDITY_DAYS
            assert ca["keyType"] == CUSTOM_CERT_KEY_TYPE
            _log(LogKind.OK, "Custom policy show returned correctly")

            # TODO - service currently only supports validity period updates
            # Update custom credential policy
            _log(LogKind.STEP, "Step 7 ❯ Update & List Policies")
            update_policy_cmd = (
                f"iot adr ns policy update --ns {namespace_name} -g {rg} "
                f"--policy-name {CUSTOM_POLICY_NAME} "
                f"--cert-validity-days {CUSTOM_CERT_UPDATE_VALIDITY_DAYS}"
            )
            _log(LogKind.CMD, "az %s", update_policy_cmd)
            updated_policy = self.cmd(update_policy_cmd).get_output_in_json()
            assert updated_policy["properties"]["provisioningState"] == "Succeeded"
            leaf, _ = _cert_config(updated_policy)
            assert leaf["validityPeriodInDays"] == CUSTOM_CERT_UPDATE_VALIDITY_DAYS
            _log(LogKind.RESULT, "validityDays updated to %s", CUSTOM_CERT_UPDATE_VALIDITY_DAYS)

            # List ADR credential policies
            list_policy_cmd = f"iot adr ns policy list --ns {namespace_name} -g {rg}"
            _log(LogKind.CMD, "az %s", list_policy_cmd)
            policies = self.cmd(list_policy_cmd).get_output_in_json()

            assert isinstance(policies, list)
            assert len(policies) == 1
            policy_names = [p["name"] for p in policies]
            assert CUSTOM_POLICY_NAME in policy_names
            _log(LogKind.OK, "Policy list returned %d policy: %s", len(policies), policy_names)

            # Verify credential still exists
            _log(LogKind.CMD, "az %s", cred_show_cmd)
            credentials = self.cmd(cred_show_cmd).get_output_in_json()

            assert credentials["name"] == "default"
            assert credentials["properties"]["provisioningState"] == "Succeeded"
            _log(LogKind.OK, "Credential still exists after policy operations")

            # Delete policies
            _log(LogKind.STEP, "Step 8 ❯ Cleanup: Delete Policy & Credential")
            del_policy_cmd = f"iot adr ns policy delete --ns {namespace_name} -g {rg} --policy-name {CUSTOM_POLICY_NAME} -y"
            _log(LogKind.CMD, "az %s", del_policy_cmd)
            self.cmd(del_policy_cmd)
            _log(LogKind.RESULT, "ok")

            # Verify all policies were deleted
            _log(LogKind.CMD, "az %s", list_policy_cmd)
            policies_after = self.cmd(list_policy_cmd).get_output_in_json()

            assert isinstance(policies_after, list)
            assert len(policies_after) == 0
            _log(LogKind.OK, "All policies deleted")

            # Delete the credential
            cred_del_cmd = f"iot adr ns credential delete --ns {namespace_name} -g {rg} -y"
            _log(LogKind.CMD, "az %s", cred_del_cmd)
            self.cmd(cred_del_cmd)
            _log(LogKind.RESULT, "ok")

            # Verify credentials are deleted (expect failure)
            _log(LogKind.CMD, "az %s  (expect failure)", cred_show_cmd)
            self.cmd(cred_show_cmd, expect_failure=True)
            _log(LogKind.OK, "Credential deleted successfully")

        finally:
            # Cleanup
            _log(LogKind.STEP, "Cleanup ❯ Delete Namespace")
            try:
                cleanup_cmd = f"iot adr ns delete -n {namespace_name} -g {rg} -y"
                _log(LogKind.CMD, "az %s", cleanup_cmd)
                self.cmd(cleanup_cmd)
                _log(LogKind.RESULT, "ok")
            except Exception as e:
                _log(LogKind.WARN, "Cleanup failed: %s", e)
