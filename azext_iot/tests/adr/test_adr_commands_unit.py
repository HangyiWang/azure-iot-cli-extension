# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Command-layer unit tests for the ADR thin command wrappers.

Each command function instantiates a provider and delegates to a single method.
These tests patch the provider class in the command module and assert the
delegation, exercising the commands_*.py modules.
"""

from unittest.mock import Mock

import pytest

from azext_iot.adr import (
    commands_certificate_authority,
    commands_certificate_policy,
    commands_credential,
    commands_device,
    commands_namespace,
    commands_policy,
    commands_registry_device,
)

RG = "test-rg"
NS = "test-namespace"


@pytest.fixture()
def cmd():
    return Mock()


def _patch_provider(mocker, module, attr):
    provider = Mock()
    cls = mocker.patch.object(module, attr, return_value=provider)
    return cls, provider


class TestCredentialCommands:
    def test_create(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_credential, "CredentialProvider")
        commands_credential.adr_credential_create(cmd, namespace_name=NS, resource_group_name=RG, tags={"a": "b"})
        provider.create.assert_called_once_with(namespace_name=NS, resource_group_name=RG, tags={"a": "b"})

    def test_show(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_credential, "CredentialProvider")
        commands_credential.adr_credential_show(cmd, namespace_name=NS, resource_group_name=RG)
        provider.show.assert_called_once_with(namespace_name=NS, resource_group_name=RG)

    def test_delete(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_credential, "CredentialProvider")
        commands_credential.adr_credential_delete(cmd, namespace_name=NS, resource_group_name=RG)
        provider.delete.assert_called_once_with(namespace_name=NS, resource_group_name=RG)

    def test_synchronize(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_credential, "CredentialProvider")
        commands_credential.adr_credential_synchronize(cmd, namespace_name=NS, resource_group_name=RG)
        provider.synchronize.assert_called_once_with(namespace_name=NS, resource_group_name=RG)


class TestDeviceCommands:
    def test_show(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_device, "DeviceProvider")
        commands_device.adr_device_show(cmd, device_name="dev", namespace_name=NS, resource_group_name=RG)
        provider.show.assert_called_once_with(device_name="dev", namespace_name=NS, resource_group_name=RG)

    def test_list(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_device, "DeviceProvider")
        commands_device.adr_device_list(cmd, namespace_name=NS, resource_group_name=RG)
        provider.list.assert_called_once_with(namespace_name=NS, resource_group_name=RG)

    def test_update(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_device, "DeviceProvider")
        commands_device.adr_device_update(
            cmd,
            device_name="dev",
            namespace_name=NS,
            resource_group_name=RG,
            enabled=True,
            tags={"a": "b"},
            operating_system_version="1.0",
            attributes="{}",
            policy_resource_id="pid",
        )
        provider.update.assert_called_once_with(
            device_name="dev",
            namespace_name=NS,
            resource_group_name=RG,
            enabled=True,
            tags={"a": "b"},
            operating_system_version="1.0",
            attributes="{}",
            policy_resource_id="pid",
            no_wait=False,
        )

    def test_revoke(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_device, "DeviceProvider")
        commands_device.adr_device_revoke(
            cmd, device_name="dev", namespace_name=NS, resource_group_name=RG, disable=True
        )
        provider.revoke.assert_called_once_with(
            device_name="dev", namespace_name=NS, resource_group_name=RG, disable=True
        )


class TestNamespaceCommands:
    def test_create(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_namespace, "NamespaceProvider")
        commands_namespace.adr_namespace_create(
            cmd,
            namespace_name=NS,
            resource_group_name=RG,
            location="westus",
            tags={"a": "b"},
            policy_name="pol",
            certificate_key_type="ECC",
            certificate_subject="CN=x",
            certificate_validity_days=30,
        )
        provider.create.assert_called_once_with(
            namespace_name=NS,
            resource_group_name=RG,
            location="westus",
            tags={"a": "b"},
            policy_name="pol",
            certificate_key_type="ECC",
            certificate_subject="CN=x",
            certificate_validity_days=30,
            outbound_mi_system_assigned=None,
            outbound_mi_user_assigned=None,
            no_wait=False,
        )

    def test_show(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_namespace, "NamespaceProvider")
        commands_namespace.adr_namespace_show(cmd, namespace_name=NS, resource_group_name=RG)
        provider.show.assert_called_once_with(namespace_name=NS, resource_group_name=RG)

    def test_list(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_namespace, "NamespaceProvider")
        commands_namespace.adr_namespace_list(cmd, resource_group_name=RG)
        provider.list.assert_called_once_with(resource_group_name=RG)

    def test_delete(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_namespace, "NamespaceProvider")
        commands_namespace.adr_namespace_delete(cmd, namespace_name=NS, resource_group_name=RG)
        provider.delete.assert_called_once_with(namespace_name=NS, resource_group_name=RG, no_wait=False)

    def test_update(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_namespace, "NamespaceProvider")
        commands_namespace.adr_namespace_update(cmd, namespace_name=NS, resource_group_name=RG, tags={"a": "b"})
        provider.update.assert_called_once_with(
            namespace_name=NS,
            resource_group_name=RG,
            tags={"a": "b"},
            outbound_mi_system_assigned=None,
            outbound_mi_user_assigned=None,
            no_wait=False,
        )


class TestPolicyCommands:
    def test_create(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_policy, "PolicyProvider")
        commands_policy.adr_policy_create(
            cmd,
            policy_name="pol",
            namespace_name=NS,
            resource_group_name=RG,
            tags={"a": "b"},
            certificate_key_type="ECC",
            certificate_subject="CN=x",
            certificate_validity_days=30,
            enable_byor=True,
        )
        provider.create.assert_called_once_with(
            policy_name="pol",
            namespace_name=NS,
            resource_group_name=RG,
            tags={"a": "b"},
            certificate_key_type="ECC",
            certificate_subject="CN=x",
            certificate_validity_days=30,
            enable_byor=True,
        )

    def test_show(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_policy, "PolicyProvider")
        commands_policy.adr_policy_show(cmd, policy_name="pol", namespace_name=NS, resource_group_name=RG)
        provider.show.assert_called_once_with(policy_name="pol", namespace_name=NS, resource_group_name=RG)

    def test_list(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_policy, "PolicyProvider")
        commands_policy.adr_policy_list(cmd, namespace_name=NS, resource_group_name=RG)
        provider.list.assert_called_once_with(namespace_name=NS, resource_group_name=RG)

    def test_delete(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_policy, "PolicyProvider")
        commands_policy.adr_policy_delete(cmd, policy_name="pol", namespace_name=NS, resource_group_name=RG)
        provider.delete.assert_called_once_with(policy_name="pol", namespace_name=NS, resource_group_name=RG)

    def test_update(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_policy, "PolicyProvider")
        commands_policy.adr_policy_update(
            cmd,
            policy_name="pol",
            namespace_name=NS,
            resource_group_name=RG,
            tags={"a": "b"},
            certificate_validity_days=30,
        )
        provider.update.assert_called_once_with(
            policy_name="pol",
            namespace_name=NS,
            resource_group_name=RG,
            tags={"a": "b"},
            certificate_validity_days=30,
        )

    def test_revoke_issuer(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_policy, "PolicyProvider")
        commands_policy.adr_policy_revoke_issuer(cmd, policy_name="pol", namespace_name=NS, resource_group_name=RG)
        provider.revoke_issuer.assert_called_once_with(
            policy_name="pol", namespace_name=NS, resource_group_name=RG
        )

    def test_activate_byor(self, mocker, cmd):
        _, provider = _patch_provider(mocker, commands_policy, "PolicyProvider")
        mocker.patch(
            "azext_iot.common.utility.read_file_content", return_value="cert-chain"
        )
        commands_policy.adr_policy_activate_byor(
            cmd,
            policy_name="pol",
            namespace_name=NS,
            resource_group_name=RG,
            certificate_chain_file="chain.pem",
        )
        provider.activate_byor.assert_called_once_with(
            policy_name="pol",
            namespace_name=NS,
            resource_group_name=RG,
            certificate_chain="cert-chain",
        )


class TestCertificateAuthorityCommands:
    def test_create_ica(self, mocker, cmd):
        _, provider = _patch_provider(
            mocker, commands_certificate_authority, "CertificateAuthorityProvider"
        )

        commands_certificate_authority.adr_ca_create(
            cmd,
            certificate_authority_name="ica",
            namespace_name=NS,
            resource_group_name=RG,
            certificate_authority_type="ICA",
            issuer_type="Internal",
            issuer_certificate_authority_uuid="issuer-uuid",
        )

        provider.create.assert_called_once_with(
            certificate_authority_name="ica",
            namespace_name=NS,
            resource_group_name=RG,
            certificate_authority_type="ICA",
            issuer_type="Internal",
            issuer_certificate_authority_uuid="issuer-uuid",
            key_type=None,
            location=None,
            tags=None,
        )


class TestCertificatePolicyCommands:
    def test_update_tags(self, mocker, cmd):
        _, provider = _patch_provider(
            mocker, commands_certificate_policy, "CertificatePolicyProvider"
        )

        commands_certificate_policy.adr_ca_policy_update(
            cmd,
            certificate_policy_name="policy",
            certificate_authority_name="ca",
            namespace_name=NS,
            resource_group_name=RG,
            tags={"env": "test"},
        )

        provider.update.assert_called_once_with(
            certificate_policy_name="policy",
            certificate_authority_name="ca",
            namespace_name=NS,
            resource_group_name=RG,
            tags={"env": "test"},
        )


class TestRegistryDeviceCommands:
    def test_create_defaults_enabled(self, mocker, cmd):
        _, provider = _patch_provider(
            mocker, commands_registry_device, "RegistryDeviceProvider"
        )

        commands_registry_device.adr_registry_device_create(
            cmd,
            registry_device_name="device",
            namespace_name=NS,
            resource_group_name=RG,
        )

        provider.create.assert_called_once_with(
            registry_device_name="device",
            namespace_name=NS,
            resource_group_name=RG,
            external_device_id=None,
            enablement_state="Enabled",
            manufacturer=None,
            model=None,
            hardware_revision=None,
            software_revision=None,
            location=None,
            tags=None,
        )

    def test_update_enablement(self, mocker, cmd):
        _, provider = _patch_provider(
            mocker, commands_registry_device, "RegistryDeviceProvider"
        )

        commands_registry_device.adr_registry_device_update(
            cmd,
            registry_device_name="device",
            namespace_name=NS,
            resource_group_name=RG,
            enablement_state="Disabled",
        )

        provider.update.assert_called_once_with(
            registry_device_name="device",
            namespace_name=NS,
            resource_group_name=RG,
            enablement_state="Disabled",
            manufacturer=None,
            model=None,
            hardware_revision=None,
            software_revision=None,
            tags=None,
        )
