# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("disable", [None, True, False])
def test_device_revoke(fixture_device_provider, mock_poller, disable):
    """Test device credential revocation with various disable options."""
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
    """Test device revoke when response contains an error."""
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
