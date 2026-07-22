# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import inspect
from unittest.mock import Mock, patch

import pytest
from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from azext_iot.adr import commands_registry_device
from azext_iot.adr.common import (
    RegistryDeviceAuthenticationType,
    RegistryDeviceEnablementState,
)
from azext_iot.adr.providers.registry_device import RegistryDeviceProvider

RG = "test-rg"
NS = "test-namespace"
DEVICE = "test-registry-device"
PROFILE = "default"


def _completed_poller(result):
    poller = Mock()
    poller.done.return_value = True
    poller.result.return_value = result
    return poller


@pytest.fixture()
def registry_device_provider():
    with patch("azext_iot.adr.providers.base.adr_service_factory") as factory:
        factory.return_value = Mock()
        yield RegistryDeviceProvider(Mock(cli_ctx=Mock()))


def test_create_builds_exact_camel_case_body_and_waits(registry_device_provider):
    expected = {"name": DEVICE}
    poller = _completed_poller(expected)
    registry_device_provider.client.registry_devices.begin_create_or_replace.return_value = poller

    result = registry_device_provider.create(
        registry_device_name=DEVICE,
        namespace_name=NS,
        resource_group_name=RG,
        location="eastus",
        tags={"environment": "test"},
        enablement_state=RegistryDeviceEnablementState.disabled.value,
        external_device_id="external-42",
        manufacturer="Contoso",
        model="X100",
        hardware_revision="2.0",
        software_revision="3.1",
    )

    assert result == expected
    poller.result.assert_called_once_with()
    registry_device_provider.client.registry_devices.begin_create_or_replace.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
        resource={
            "location": "eastus",
            "tags": {"environment": "test"},
            "properties": {
                "enablementState": "Disabled",
                "externalDeviceId": "external-42",
                "manufacturer": "Contoso",
                "model": "X100",
                "hardwareRevision": "2.0",
                "softwareRevision": "3.1",
            },
        },
    )


def test_create_defaults_enabled_and_inherits_namespace_location(
    registry_device_provider,
):
    registry_device_provider.client.namespaces.get.return_value = {"location": "westus2"}
    registry_device_provider.client.registry_devices.begin_create_or_replace.return_value = (
        _completed_poller({})
    )

    registry_device_provider.create(
        registry_device_name=DEVICE,
        namespace_name=NS,
        resource_group_name=RG,
    )

    registry_device_provider.client.namespaces.get.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
    )
    call = registry_device_provider.client.registry_devices.begin_create_or_replace.call_args
    assert call.kwargs["resource"] == {
        "location": "westus2",
        "properties": {"enablementState": "Enabled"},
    }


def test_external_device_id_is_create_only(registry_device_provider):
    provider_create = inspect.signature(registry_device_provider.create).parameters
    provider_update = inspect.signature(registry_device_provider.update).parameters
    command_create = inspect.signature(
        commands_registry_device.adr_registry_device_create
    ).parameters
    command_update = inspect.signature(
        commands_registry_device.adr_registry_device_update
    ).parameters

    assert "external_device_id" in provider_create
    assert "external_device_id" in command_create
    assert "external_device_id" not in provider_update
    assert "external_device_id" not in command_update

    with pytest.raises(TypeError):
        registry_device_provider.update(
            registry_device_name=DEVICE,
            namespace_name=NS,
            resource_group_name=RG,
            external_device_id="not-updateable",
        )
    registry_device_provider.client.registry_devices.begin_update.assert_not_called()


def test_update_builds_exact_body_for_all_writable_fields_and_waits(
    registry_device_provider,
):
    expected = {"name": DEVICE, "properties": {"enablementState": "Disabled"}}
    poller = _completed_poller(expected)
    registry_device_provider.client.registry_devices.begin_update.return_value = poller

    result = registry_device_provider.update(
        registry_device_name=DEVICE,
        namespace_name=NS,
        resource_group_name=RG,
        tags={"environment": "production"},
        enablement_state="Disabled",
        manufacturer="Fabrikam",
        model="X200",
        hardware_revision="2.1",
        software_revision="4.0",
    )

    assert result == expected
    poller.result.assert_called_once_with()
    registry_device_provider.client.registry_devices.begin_update.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
        properties={
            "tags": {"environment": "production"},
            "properties": {
                "enablementState": "Disabled",
                "manufacturer": "Fabrikam",
                "model": "X200",
                "hardwareRevision": "2.1",
                "softwareRevision": "4.0",
            },
        },
    )


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"tags": {}}, {"tags": {}}),
        ({"manufacturer": ""}, {"properties": {"manufacturer": ""}}),
        ({"model": ""}, {"properties": {"model": ""}}),
        ({"hardware_revision": ""}, {"properties": {"hardwareRevision": ""}}),
        ({"software_revision": ""}, {"properties": {"softwareRevision": ""}}),
    ],
)
def test_update_preserves_explicit_clear_values(
    registry_device_provider, kwargs, expected
):
    registry_device_provider.client.registry_devices.begin_update.return_value = (
        _completed_poller({})
    )

    registry_device_provider.update(
        registry_device_name=DEVICE,
        namespace_name=NS,
        resource_group_name=RG,
        **kwargs,
    )

    call = registry_device_provider.client.registry_devices.begin_update.call_args
    assert call.kwargs["properties"] == expected


def test_update_rejects_empty_patch(registry_device_provider):
    with pytest.raises(RequiredArgumentMissingError, match="Nothing to update"):
        registry_device_provider.update(
            registry_device_name=DEVICE,
            namespace_name=NS,
            resource_group_name=RG,
        )

    registry_device_provider.client.registry_devices.begin_update.assert_not_called()


@pytest.mark.parametrize("operation", ["create", "update"])
def test_registry_device_rejects_invalid_enablement_state(
    registry_device_provider, operation
):
    kwargs = {
        "registry_device_name": DEVICE,
        "namespace_name": NS,
        "resource_group_name": RG,
        "enablement_state": "Unknown",
    }
    if operation == "create":
        kwargs["location"] = "eastus"

    with pytest.raises(InvalidArgumentValueError, match="Enabled.*Disabled"):
        getattr(registry_device_provider, operation)(**kwargs)


def test_show_list_and_delete_select_registry_device_operations(
    registry_device_provider,
):
    registry_device_provider.client.registry_devices.get.return_value = {"name": DEVICE}
    registry_device_provider.client.registry_devices.list_by_namespace.return_value = iter(
        [{"name": "one"}, {"name": "two"}]
    )
    poller = _completed_poller(None)
    registry_device_provider.client.registry_devices.begin_delete.return_value = poller

    assert registry_device_provider.show(DEVICE, NS, RG) == {"name": DEVICE}
    assert registry_device_provider.list(NS, RG) == [
        {"name": "one"},
        {"name": "two"},
    ]
    assert registry_device_provider.delete(DEVICE, NS, RG) is None
    poller.result.assert_called_once_with()

    registry_device_provider.client.registry_devices.get.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
    )
    registry_device_provider.client.registry_devices.list_by_namespace.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
    )
    registry_device_provider.client.registry_devices.begin_delete.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
    )


@pytest.mark.parametrize("operation", ["create", "update", "delete", "revoke"])
def test_mutations_honor_no_wait(registry_device_provider, operation):
    poller = _completed_poller({"name": DEVICE})

    if operation == "create":
        registry_device_provider.client.registry_devices.begin_create_or_replace.return_value = poller
        result = registry_device_provider.create(
            DEVICE,
            NS,
            RG,
            location="eastus",
            no_wait=True,
        )
    elif operation == "update":
        registry_device_provider.client.registry_devices.begin_update.return_value = poller
        result = registry_device_provider.update(
            DEVICE,
            NS,
            RG,
            manufacturer="Contoso",
            no_wait=True,
        )
    elif operation == "delete":
        registry_device_provider.client.registry_devices.begin_delete.return_value = poller
        result = registry_device_provider.delete(DEVICE, NS, RG, no_wait=True)
    else:
        auth_operations = (
            registry_device_provider.client.registry_device_authentication_profiles
        )
        auth_operations.get.return_value = {
            "properties": {"authenticationType": "CertificateAuthority"}
        }
        auth_operations.begin_revoke_certificates.return_value = poller
        result = registry_device_provider.auth_profile_revoke_certificates(
            PROFILE,
            DEVICE,
            NS,
            RG,
            no_wait=True,
        )

    assert result is poller
    poller.result.assert_not_called()


def test_auth_profile_list_and_show_select_expected_operations(
    registry_device_provider,
):
    operations = registry_device_provider.client.registry_device_authentication_profiles
    operations.list_by_device.return_value = iter(
        [{"name": "profile-one"}, {"name": "profile-two"}]
    )
    operations.get.return_value = {"name": PROFILE}

    assert registry_device_provider.auth_profile_list(DEVICE, NS, RG) == [
        {"name": "profile-one"},
        {"name": "profile-two"},
    ]
    assert registry_device_provider.auth_profile_show(PROFILE, DEVICE, NS, RG) == {
        "name": PROFILE
    }

    operations.list_by_device.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
    )
    operations.get.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
        authentication_profile_name=PROFILE,
    )


def test_get_keys_validates_type_and_warns_without_logging_secrets(
    registry_device_provider,
):
    operations = registry_device_provider.client.registry_device_authentication_profiles
    operations.get.return_value = {
        "properties": {"authenticationType": "SymmetricKey"}
    }
    keys = {
        "symmetricKey": {
            "primaryKey": "primary-key-value",
            "secondaryKey": "secondary-key-value",
        }
    }
    operations.get_keys.return_value = keys

    with patch(
        "azext_iot.adr.providers.registry_device.logger.warning"
    ) as warning:
        result = registry_device_provider.auth_profile_get_keys(
            PROFILE,
            DEVICE,
            NS,
            RG,
        )

    assert result == keys
    operations.get.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
        authentication_profile_name=PROFILE,
    )
    operations.get_keys.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
        authentication_profile_name=PROFILE,
        logging_enable=False,
    )
    warning.assert_called_once()
    warning_text = repr(warning.call_args)
    assert "secret" in warning_text.lower()
    assert "primary-key-value" not in warning_text
    assert "secondary-key-value" not in warning_text


@pytest.mark.parametrize(
    "profile",
    [
        {"properties": {"authenticationType": "CertificateAuthority"}},
        {"properties": {"authenticationType": "SelfSignedX509Certificate"}},
        {"properties": {}},
        None,
    ],
)
def test_get_keys_rejects_non_symmetric_profiles(
    registry_device_provider, profile
):
    operations = registry_device_provider.client.registry_device_authentication_profiles
    operations.get.return_value = profile

    with pytest.raises(InvalidArgumentValueError, match="SymmetricKey"):
        registry_device_provider.auth_profile_get_keys(
            PROFILE,
            DEVICE,
            NS,
            RG,
        )

    operations.get.assert_called_once()
    operations.get_keys.assert_not_called()


def test_revoke_certificates_requires_managed_x509_and_waits(
    registry_device_provider,
):
    operations = registry_device_provider.client.registry_device_authentication_profiles
    operations.get.return_value = {
        "properties": {
            "authenticationType": RegistryDeviceAuthenticationType.certificate_authority.value
        }
    }
    poller = _completed_poller(None)
    operations.begin_revoke_certificates.return_value = poller

    assert (
        registry_device_provider.auth_profile_revoke_certificates(
            PROFILE,
            DEVICE,
            NS,
            RG,
        )
        is None
    )
    poller.result.assert_called_once_with()
    operations.get.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
        authentication_profile_name=PROFILE,
    )
    operations.begin_revoke_certificates.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
        authentication_profile_name=PROFILE,
    )


@pytest.mark.parametrize(
    "authentication_type",
    ["SymmetricKey", "SelfSignedX509Certificate", None],
)
def test_revoke_certificates_rejects_ineligible_profiles(
    registry_device_provider, authentication_type
):
    operations = registry_device_provider.client.registry_device_authentication_profiles
    operations.get.return_value = {
        "properties": {"authenticationType": authentication_type}
    }

    with pytest.raises(InvalidArgumentValueError, match="CertificateAuthority"):
        registry_device_provider.auth_profile_revoke_certificates(
            PROFILE,
            DEVICE,
            NS,
            RG,
        )

    operations.get.assert_called_once()
    operations.begin_revoke_certificates.assert_not_called()


@pytest.mark.parametrize(
    "operation_group, list_method, show_method, child_name, name_argument",
    [
        (
            "registry_device_attributes",
            "attribute_list",
            "attribute_show",
            "reported",
            "attribute_name",
        ),
        (
            "registry_device_capabilities",
            "capability_list",
            "capability_show",
            "iotHub",
            "capability_name",
        ),
    ],
)
def test_attribute_and_capability_list_show_operation_selection(
    registry_device_provider,
    operation_group,
    list_method,
    show_method,
    child_name,
    name_argument,
):
    operations = getattr(registry_device_provider.client, operation_group)
    operations.list_by_device.return_value = iter([{"name": child_name}])
    operations.get.return_value = {"name": child_name}

    assert getattr(registry_device_provider, list_method)(DEVICE, NS, RG) == [
        {"name": child_name}
    ]
    assert getattr(registry_device_provider, show_method)(
        child_name,
        DEVICE,
        NS,
        RG,
    ) == {"name": child_name}

    operations.list_by_device.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
    )
    operations.get.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
        registry_device_name=DEVICE,
        **{name_argument: child_name},
    )


COMMAND_CASES = [
    (
        "adr_registry_device_create",
        "create",
        {
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
            "location": "eastus",
            "tags": {"environment": "test"},
            "enablement_state": "Disabled",
            "external_device_id": "external-42",
            "manufacturer": "Contoso",
            "model": "X100",
            "hardware_revision": "2.0",
            "software_revision": "3.0",
            "no_wait": True,
        },
    ),
    (
        "adr_registry_device_show",
        "show",
        {
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
        },
    ),
    (
        "adr_registry_device_list",
        "list",
        {"namespace_name": NS, "resource_group_name": RG},
    ),
    (
        "adr_registry_device_update",
        "update",
        {
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
            "tags": {"environment": "test"},
            "enablement_state": "Enabled",
            "manufacturer": "Contoso",
            "model": "X200",
            "hardware_revision": "2.1",
            "software_revision": "4.0",
            "no_wait": True,
        },
    ),
    (
        "adr_registry_device_delete",
        "delete",
        {
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
            "no_wait": True,
        },
    ),
    (
        "adr_registry_device_auth_profile_list",
        "auth_profile_list",
        {
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
        },
    ),
    (
        "adr_registry_device_auth_profile_show",
        "auth_profile_show",
        {
            "authentication_profile_name": PROFILE,
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
        },
    ),
    (
        "adr_registry_device_auth_profile_get_keys",
        "auth_profile_get_keys",
        {
            "authentication_profile_name": PROFILE,
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
        },
    ),
    (
        "adr_registry_device_auth_profile_revoke_certificates",
        "auth_profile_revoke_certificates",
        {
            "authentication_profile_name": PROFILE,
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
            "no_wait": True,
        },
    ),
    (
        "adr_registry_device_attribute_list",
        "attribute_list",
        {
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
        },
    ),
    (
        "adr_registry_device_attribute_show",
        "attribute_show",
        {
            "attribute_name": "reported",
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
        },
    ),
    (
        "adr_registry_device_capability_list",
        "capability_list",
        {
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
        },
    ),
    (
        "adr_registry_device_capability_show",
        "capability_show",
        {
            "capability_name": "iotHub",
            "registry_device_name": DEVICE,
            "namespace_name": NS,
            "resource_group_name": RG,
        },
    ),
]


@pytest.mark.parametrize("function_name, provider_method, kwargs", COMMAND_CASES)
def test_command_wrappers_delegate_exactly(
    function_name, provider_method, kwargs
):
    cmd = Mock()
    sentinel = object()
    with patch.object(
        commands_registry_device,
        "RegistryDeviceProvider",
    ) as provider_type:
        provider = provider_type.return_value
        getattr(provider, provider_method).return_value = sentinel

        result = getattr(commands_registry_device, function_name)(cmd, **kwargs)

    assert result is sentinel
    provider_type.assert_called_once_with(cmd)
    getattr(provider, provider_method).assert_called_once_with(**kwargs)


def test_command_wrappers_have_explicit_typed_parameters():
    for function_name, _, _ in COMMAND_CASES:
        parameters = inspect.signature(
            getattr(commands_registry_device, function_name)
        ).parameters
        assert not any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        assert all(
            parameter.annotation is not inspect.Parameter.empty
            for name, parameter in parameters.items()
            if name != "cmd"
        )
