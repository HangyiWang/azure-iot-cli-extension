# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import time
from typing import Optional
from unittest.mock import Mock, patch

import pytest
from knack.log import get_logger

from azext_iot.adr.providers.base import ADRProvider
from azext_iot.adr.providers.credential import CredentialProvider
from azext_iot.adr.providers.device import DeviceProvider
from azext_iot.adr.providers.namespace import NamespaceProvider
from azext_iot.adr.providers.policy import PolicyProvider
from azext_iot.tests.generators import generate_generic_id
from azext_iot.tests.settings import DynamoSettings

# Integration test constants
REQUIRED_TEST_ENV_VARS = ["azext_iot_testrg"]
settings = DynamoSettings(req_env_set=REQUIRED_TEST_ENV_VARS)
TEST_RG = settings.env.azext_iot_testrg

# Test constants for integration tests
CUSTOM_POLICY_NAME = "custompolicy"
CUSTOM_CERT_VALIDITY_DAYS = 25
CUSTOM_CERT_UPDATE_VALIDITY_DAYS = 20
CUSTOM_CERT_UPDATE_KEYTYPE = "RSA"
CUSTOM_CERT_KEY_TYPE = "ECC"
CUSTOM_CERT_SUBJECT = "CN=test-device"

# Shared integration test location (canary region for preview features)
TEST_LOCATION = "centraluseuap"

logger = get_logger(__name__)


@pytest.fixture(autouse=True)
def mock_wait_for_terminal_state(request, monkeypatch):
    """Mock wait_for_terminal_state to avoid sleeping in unit tests.

    Skipped for integration tests (_int.py) which need real polling delays.
    """
    if "_int" in request.node.nodeid:
        return

    def fast_wait(poller, **kwargs):
        """Return poller result immediately without sleeping."""
        return poller.result()

    # Patch the function in all provider modules
    monkeypatch.setattr("azext_iot.adr.providers.namespace.wait_for_terminal_state", fast_wait)
    monkeypatch.setattr("azext_iot.adr.providers.credential.wait_for_terminal_state", fast_wait)
    monkeypatch.setattr("azext_iot.adr.providers.policy.wait_for_terminal_state", fast_wait)
    monkeypatch.setattr("azext_iot.adr.providers.device.wait_for_terminal_state", fast_wait)


@pytest.fixture()
def mock_poller():
    """Create a mock LRO poller for testing."""

    def _create_mock_poller(result_value=None):
        poller = Mock()
        poller.result.return_value = result_value or Mock()
        return poller

    return _create_mock_poller


@pytest.fixture()
def fixture_adr_provider(fixture_cmd):
    """Base ADR provider fixture for testing."""
    with patch("azext_iot.adr.providers.base.adr_service_factory") as mock_factory:
        mock_client = Mock()
        mock_factory.return_value = mock_client
        provider = ADRProvider(fixture_cmd)
        provider.client = mock_client
        return provider


@pytest.fixture()
def fixture_credential_provider(fixture_cmd):
    """Credential provider fixture for testing."""
    with patch("azext_iot.adr.providers.base.adr_service_factory") as mock_factory:
        mock_client = Mock()
        mock_factory.return_value = mock_client
        provider = CredentialProvider(fixture_cmd)
        provider.client = mock_client
        return provider


@pytest.fixture()
def fixture_namespace_provider(fixture_cmd):
    """Namespace provider fixture for testing."""
    with patch("azext_iot.adr.providers.base.adr_service_factory") as mock_factory:
        mock_client = Mock()
        mock_factory.return_value = mock_client
        provider = NamespaceProvider(fixture_cmd)
        provider.client = mock_client
        return provider


@pytest.fixture()
def fixture_policy_provider(fixture_cmd):
    """Policy provider fixture for testing."""
    with patch("azext_iot.adr.providers.base.adr_service_factory") as mock_factory:
        mock_client = Mock()
        mock_factory.return_value = mock_client
        provider = PolicyProvider(fixture_cmd)
        provider.client = mock_client
        return provider


@pytest.fixture()
def fixture_device_provider(fixture_cmd):
    """Device provider fixture for testing."""
    with patch("azext_iot.adr.providers.base.adr_service_factory") as mock_factory:
        mock_client = Mock()
        mock_factory.return_value = mock_client
        provider = DeviceProvider(fixture_cmd)
        provider.client = mock_client
        return provider


def generate_adr_namespace_name() -> str:
    return f"testadr{generate_generic_id()[:8]}"


def generate_hub_name() -> str:
    return f"testhub{generate_generic_id()[:8]}"


def generate_dps_name() -> str:
    return f"testdps{generate_generic_id()[:8]}"


def generate_identity_name() -> str:
    return f"testuami{generate_generic_id()[:8]}"


def generate_device_id() -> str:
    return f"testdev{generate_generic_id()[:8]}"


def generate_enrollment_group_id() -> str:
    return f"testgroup{generate_generic_id()[:8]}"


class RoleAssignmentMixin:
    """RBAC role-assignment and retryable-command helpers for ADR integration tests.

    Must be mixed into a class that provides ``self.cmd()``
    (e.g. ``CaptureOutputLiveScenarioTest``).
    """

    cmd: callable  # provided by CaptureOutputLiveScenarioTest via MRO

    def assign_role(
        self, assignee_id: str, role: str, scope: str, assignee_type: str = "auto",
    ) -> Optional[str]:
        """Assign an Azure RBAC role, skipping if already assigned."""
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

    def retry_cmd(
        self, command: str, retries: int = 3, delay: int = 30, expect_failure: bool = False,
    ):
        """Execute a CLI command with retries for transient service failures."""
        last_error = Exception("retry_cmd: no attempts made")
        for attempt in range(1, retries + 1):
            try:
                return self.cmd(command, expect_failure=expect_failure)
            except Exception as e:
                last_error = e
                if attempt < retries:
                    logger.warning(
                        "Attempt %d/%d failed: %s. Retrying in %ds...",
                        attempt, retries, str(e)[:200], delay,
                    )
                    time.sleep(delay)
                else:
                    logger.warning("All %d attempts failed.", retries)
        raise last_error
