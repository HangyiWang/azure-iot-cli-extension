# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import AzureResponseError


# ==================== Create ====================


def test_create_adaptive_device(fixture_adaptive_device_provider):
    """Create resolves location from the namespace and builds the properties body (non-LRO)."""
    sentinel = {"name": "dev"}
    fixture_adaptive_device_provider.client.namespace_adaptive_devices.create_or_replace.return_value = sentinel
    fixture_adaptive_device_provider.client.namespaces.get.return_value = {"location": "eastus"}

    result = fixture_adaptive_device_provider.create(
        adaptive_device_name="dev", namespace_name="ns", resource_group_name="rg",
        manufacturer="Contoso", model="X1", external_device_id="ext-1",
        hardware_revision="hw1", software_revision="sw1",
    )

    assert result == sentinel
    call = fixture_adaptive_device_provider.client.namespace_adaptive_devices.create_or_replace.call_args[1]
    resource = call["resource"]
    assert resource["location"] == "eastus"
    props = resource["properties"]
    assert props["manufacturer"] == "Contoso"
    assert props["model"] == "X1"
    assert props["externalDeviceId"] == "ext-1"
    assert props["hardwareRevision"] == "hw1"
    assert props["softwareRevision"] == "sw1"


def test_create_adaptive_device_uses_explicit_location(fixture_adaptive_device_provider):
    """Create skips namespace lookup when location is supplied explicitly."""
    fixture_adaptive_device_provider.client.namespace_adaptive_devices.create_or_replace.return_value = {}

    fixture_adaptive_device_provider.create(
        adaptive_device_name="dev", namespace_name="ns", resource_group_name="rg", location="westus",
    )

    fixture_adaptive_device_provider.client.namespaces.get.assert_not_called()
    call = fixture_adaptive_device_provider.client.namespace_adaptive_devices.create_or_replace.call_args[1]
    assert call["resource"]["location"] == "westus"


def test_create_adaptive_device_missing_location(fixture_adaptive_device_provider):
    """Create raises when the parent namespace has no location."""
    fixture_adaptive_device_provider.client.namespaces.get.return_value = {}

    with pytest.raises(AzureResponseError, match=r"location"):
        fixture_adaptive_device_provider.create(
            adaptive_device_name="dev", namespace_name="ns", resource_group_name="rg",
        )


# ==================== Show / List ====================


def test_show_adaptive_device(fixture_adaptive_device_provider):
    """Show returns the adaptive device resource."""
    fixture_adaptive_device_provider.client.namespace_adaptive_devices.get.return_value = {"name": "dev"}

    result = fixture_adaptive_device_provider.show(
        adaptive_device_name="dev", namespace_name="ns", resource_group_name="rg",
    )

    assert result["name"] == "dev"
    fixture_adaptive_device_provider.client.namespace_adaptive_devices.get.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", adaptive_device_name="dev",
    )


def test_list_adaptive_device(fixture_adaptive_device_provider):
    """List returns the adaptive devices as a list."""
    fixture_adaptive_device_provider.client.namespace_adaptive_devices.list_by_namespace.return_value = iter(
        [{"name": "d1"}, {"name": "d2"}]
    )

    result = fixture_adaptive_device_provider.list(namespace_name="ns", resource_group_name="rg")

    assert [r["name"] for r in result] == ["d1", "d2"]


# ==================== Update ====================


def test_update_adaptive_device(fixture_adaptive_device_provider):
    """Update sends only the provided properties (non-LRO) and returns the response."""
    sentinel = {"name": "dev"}
    fixture_adaptive_device_provider.client.namespace_adaptive_devices.update.return_value = sentinel

    result = fixture_adaptive_device_provider.update(
        adaptive_device_name="dev", namespace_name="ns", resource_group_name="rg",
        software_revision="2.0",
    )

    assert result == sentinel
    props = fixture_adaptive_device_provider.client.namespace_adaptive_devices.update.call_args[1]["properties"]
    assert props["properties"]["softwareRevision"] == "2.0"
    assert "manufacturer" not in props["properties"]


# ==================== Delete ====================


def test_delete_adaptive_device(fixture_adaptive_device_provider, mock_poller):
    """Delete triggers begin_delete LRO and returns the result."""
    sentinel = Mock()
    fixture_adaptive_device_provider.client.namespace_adaptive_devices.begin_delete.return_value = mock_poller(
        sentinel
    )

    result = fixture_adaptive_device_provider.delete(
        adaptive_device_name="dev", namespace_name="ns", resource_group_name="rg",
    )

    assert result == sentinel
    fixture_adaptive_device_provider.client.namespace_adaptive_devices.begin_delete.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", adaptive_device_name="dev",
    )


# ==================== --no-wait + guards ====================


def test_delete_adaptive_device_no_wait_returns_poller(fixture_adaptive_device_provider, mock_poller):
    """With --no-wait, delete returns the poller without waiting."""
    poller = mock_poller(None)
    fixture_adaptive_device_provider.client.namespace_adaptive_devices.begin_delete.return_value = poller

    result = fixture_adaptive_device_provider.delete(
        adaptive_device_name="dev", namespace_name="ns", resource_group_name="rg", no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_update_adaptive_device_requires_a_field(fixture_adaptive_device_provider):
    """Update with no fields raises RequiredArgumentMissingError."""
    from azure.cli.core.azclierror import RequiredArgumentMissingError

    with pytest.raises(RequiredArgumentMissingError):
        fixture_adaptive_device_provider.update(
            adaptive_device_name="dev", namespace_name="ns", resource_group_name="rg",
        )
