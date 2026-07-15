# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import AzureResponseError


# ==================== Create ====================


def test_create_registry_device(fixture_registry_device_provider, mock_poller):
    """Create resolves location and waits for the RegistryDevice LRO."""
    sentinel = {"name": "dev"}
    fixture_registry_device_provider.client.registry_devices.begin_create_or_replace.return_value = mock_poller(
        sentinel
    )
    fixture_registry_device_provider.client.namespaces.get.return_value = {"location": "eastus"}

    result = fixture_registry_device_provider.create(
        registry_device_name="dev", namespace_name="ns", resource_group_name="rg",
        manufacturer="Contoso", model="X1", external_device_id="ext-1",
        hardware_revision="hw1", software_revision="sw1",
    )

    assert result == sentinel
    call = fixture_registry_device_provider.client.registry_devices.begin_create_or_replace.call_args[1]
    resource = call["resource"]
    assert resource["location"] == "eastus"
    props = resource["properties"]
    assert props["manufacturer"] == "Contoso"
    assert props["model"] == "X1"
    assert props["externalDeviceId"] == "ext-1"
    assert props["hardwareRevision"] == "hw1"
    assert props["softwareRevision"] == "sw1"
    assert props["enablementState"] == "Enabled"


def test_create_registry_device_uses_explicit_location(
    fixture_registry_device_provider, mock_poller
):
    """Create skips namespace lookup when location is supplied explicitly."""
    fixture_registry_device_provider.client.registry_devices.begin_create_or_replace.return_value = mock_poller(
        {}
    )

    fixture_registry_device_provider.create(
        registry_device_name="dev", namespace_name="ns", resource_group_name="rg", location="westus",
    )

    fixture_registry_device_provider.client.namespaces.get.assert_not_called()
    call = fixture_registry_device_provider.client.registry_devices.begin_create_or_replace.call_args[1]
    assert call["resource"]["location"] == "westus"


def test_create_registry_device_missing_location(fixture_registry_device_provider):
    """Create raises when the parent namespace has no location."""
    fixture_registry_device_provider.client.namespaces.get.return_value = {}

    with pytest.raises(AzureResponseError, match=r"location"):
        fixture_registry_device_provider.create(
            registry_device_name="dev", namespace_name="ns", resource_group_name="rg",
        )


# ==================== Show / List ====================


def test_show_registry_device(fixture_registry_device_provider):
    """Show returns the registry device resource."""
    fixture_registry_device_provider.client.registry_devices.get.return_value = {"name": "dev"}

    result = fixture_registry_device_provider.show(
        registry_device_name="dev", namespace_name="ns", resource_group_name="rg",
    )

    assert result["name"] == "dev"
    fixture_registry_device_provider.client.registry_devices.get.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", registry_device_name="dev",
    )


def test_list_registry_device(fixture_registry_device_provider):
    """List returns the registry devices as a list."""
    fixture_registry_device_provider.client.registry_devices.list_by_namespace.return_value = iter(
        [{"name": "d1"}, {"name": "d2"}]
    )

    result = fixture_registry_device_provider.list(namespace_name="ns", resource_group_name="rg")

    assert [r["name"] for r in result] == ["d1", "d2"]


# ==================== Update ====================


def test_update_registry_device(fixture_registry_device_provider, mock_poller):
    """Update sends only mutable properties and waits for the LRO."""
    sentinel = {"name": "dev"}
    fixture_registry_device_provider.client.registry_devices.begin_update.return_value = mock_poller(
        sentinel
    )

    result = fixture_registry_device_provider.update(
        registry_device_name="dev", namespace_name="ns", resource_group_name="rg",
        software_revision="2.0",
    )

    assert result == sentinel
    props = fixture_registry_device_provider.client.registry_devices.begin_update.call_args[1]["properties"]
    assert props["properties"]["softwareRevision"] == "2.0"
    assert "manufacturer" not in props["properties"]


# ==================== Delete ====================


def test_delete_registry_device(fixture_registry_device_provider, mock_poller):
    """Delete triggers begin_delete LRO and returns the result."""
    sentinel = Mock()
    fixture_registry_device_provider.client.registry_devices.begin_delete.return_value = mock_poller(
        sentinel
    )

    result = fixture_registry_device_provider.delete(
        registry_device_name="dev", namespace_name="ns", resource_group_name="rg",
    )

    assert result == sentinel
    fixture_registry_device_provider.client.registry_devices.begin_delete.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", registry_device_name="dev",
    )


# ==================== --no-wait + guards ====================


def test_delete_registry_device_no_wait_returns_poller(fixture_registry_device_provider, mock_poller):
    """With --no-wait, delete returns the poller without waiting."""
    poller = mock_poller(None)
    fixture_registry_device_provider.client.registry_devices.begin_delete.return_value = poller

    result = fixture_registry_device_provider.delete(
        registry_device_name="dev", namespace_name="ns", resource_group_name="rg", no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_create_registry_device_no_wait_returns_poller(
    fixture_registry_device_provider, mock_poller
):
    poller = mock_poller({"name": "dev"})
    fixture_registry_device_provider.client.registry_devices.begin_create_or_replace.return_value = poller
    fixture_registry_device_provider.client.namespaces.get.return_value = {"location": "eastus"}

    result = fixture_registry_device_provider.create(
        registry_device_name="dev",
        namespace_name="ns",
        resource_group_name="rg",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_update_registry_device_no_wait_returns_poller(
    fixture_registry_device_provider, mock_poller
):
    poller = mock_poller({"name": "dev"})
    fixture_registry_device_provider.client.registry_devices.begin_update.return_value = poller

    result = fixture_registry_device_provider.update(
        registry_device_name="dev",
        namespace_name="ns",
        resource_group_name="rg",
        enablement_state="Disabled",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_update_registry_device_requires_a_field(fixture_registry_device_provider):
    """Update with no fields raises RequiredArgumentMissingError."""
    from azure.cli.core.azclierror import RequiredArgumentMissingError

    with pytest.raises(RequiredArgumentMissingError):
        fixture_registry_device_provider.update(
            registry_device_name="dev", namespace_name="ns", resource_group_name="rg",
        )


def test_create_registry_device_with_tags(fixture_registry_device_provider, mock_poller):
    """Tags are included in the create body when provided."""
    fixture_registry_device_provider.client.registry_devices.begin_create_or_replace.return_value = mock_poller(
        {"name": "dev"}
    )
    fixture_registry_device_provider.client.namespaces.get.return_value = {"location": "eastus"}

    fixture_registry_device_provider.create(
        registry_device_name="dev", namespace_name="ns", resource_group_name="rg",
        manufacturer="Contoso", tags={"env": "prod"},
    )

    resource = fixture_registry_device_provider.client.registry_devices.begin_create_or_replace.call_args[
        1
    ]["resource"]
    assert resource["tags"] == {"env": "prod"}


def test_update_registry_device_with_tags(fixture_registry_device_provider, mock_poller):
    """Tags-only update sends tags in the patch body."""
    fixture_registry_device_provider.client.registry_devices.begin_update.return_value = mock_poller(
        {"name": "dev"}
    )

    fixture_registry_device_provider.update(
        registry_device_name="dev", namespace_name="ns", resource_group_name="rg",
        tags={"env": "prod"},
    )

    body = fixture_registry_device_provider.client.registry_devices.begin_update.call_args[1]["properties"]
    assert body["tags"] == {"env": "prod"}


def test_update_registry_device_enablement_state(
    fixture_registry_device_provider, mock_poller
):
    fixture_registry_device_provider.client.registry_devices.begin_update.return_value = mock_poller(
        {"name": "dev"}
    )

    fixture_registry_device_provider.update(
        registry_device_name="dev",
        namespace_name="ns",
        resource_group_name="rg",
        enablement_state="Disabled",
    )

    body = fixture_registry_device_provider.client.registry_devices.begin_update.call_args[1]["properties"]
    assert body["properties"]["enablementState"] == "Disabled"
