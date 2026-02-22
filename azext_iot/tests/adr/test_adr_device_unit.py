# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest


def test_device_show(fixture_device_provider):
    mock_device = Mock()
    fixture_device_provider.client.namespace_devices.get.return_value = mock_device

    result = fixture_device_provider.show(
        device_name="test-device",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    )

    assert result == mock_device
    fixture_device_provider.client.namespace_devices.get.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        device_name="test-device",
    )


def test_device_list(fixture_device_provider):
    mock_devices = [Mock(), Mock()]
    fixture_device_provider.client.namespace_devices.list_by_resource_group.return_value = mock_devices

    result = fixture_device_provider.list(
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    )

    assert len(result) == 2
    fixture_device_provider.client.namespace_devices.list_by_resource_group.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
    )


@pytest.mark.parametrize("enabled", [None, True, False])
def test_device_update_enabled(fixture_device_provider, mock_poller, enabled):
    mock_device = Mock()
    poller = mock_poller(mock_device)
    fixture_device_provider.client.namespace_devices.begin_update.return_value = poller

    result = fixture_device_provider.update(
        device_name="test-device",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        enabled=enabled,
    )

    assert result == mock_device
    expected_props = {}
    if enabled is not None:
        expected_props["enabled"] = enabled
    fixture_device_provider.client.namespace_devices.begin_update.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        device_name="test-device",
        properties=expected_props,
    )


def test_device_update_all_fields(fixture_device_provider, mock_poller):
    mock_device = Mock()
    poller = mock_poller(mock_device)
    fixture_device_provider.client.namespace_devices.begin_update.return_value = poller

    result = fixture_device_provider.update(
        device_name="test-device",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        enabled=False,
        tags={"env": "test"},
        operating_system_version="2.0.1",
        attributes={"key": "value"},
        policy_resource_id=(
            "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.DeviceRegistry/"
            "namespaces/ns/credentials/default/policies/p1"
        ),
    )

    assert result == mock_device
    fixture_device_provider.client.namespace_devices.begin_update.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        device_name="test-device",
        properties={
            "enabled": False,
            "tags": {"env": "test"},
            "operating_system_version": "2.0.1",
            "attributes": {"key": "value"},
            "policy": {
                "resource_id": (
                    "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.DeviceRegistry/"
                    "namespaces/ns/credentials/default/policies/p1"
                )
            },
        },
    )


@pytest.mark.parametrize("disable", [None, True, False])
def test_device_revoke(fixture_device_provider, mock_poller, disable):
    mock_revoke_result = Mock()
    mock_revoke_result.result = "Succeeded"
    poller = mock_poller(mock_revoke_result)
    fixture_device_provider.client.namespace_devices.begin_revoke.return_value = poller

    result = fixture_device_provider.revoke(
        device_name="test-device",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        disable=disable,
    )

    assert result == mock_revoke_result
    fixture_device_provider.client.namespace_devices.begin_revoke.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        device_name="test-device",
        disable=disable,
    )


def test_device_revoke_response_with_error(fixture_device_provider, mock_poller):
    mock_revoke_result = Mock()
    mock_revoke_result.result = "Failed"
    mock_revoke_result.error = Mock()
    mock_revoke_result.error.message = "Device not found"
    poller = mock_poller(mock_revoke_result)
    fixture_device_provider.client.namespace_devices.begin_revoke.return_value = poller

    result = fixture_device_provider.revoke(
        device_name="nonexistent-device",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    )

    assert result == mock_revoke_result
    assert result.result == "Failed"
    assert result.error.message == "Device not found"
