# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock


def test_group_show(fixture_group_provider):
    mock_group = Mock()
    fixture_group_provider.client.groups.get.return_value = mock_group

    result = fixture_group_provider.show(
        group_name="g1",
        namespace_name="ns1",
        resource_group_name="rg1",
    )

    assert result == mock_group
    fixture_group_provider.client.groups.get.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        group_name="g1",
    )


def test_group_list(fixture_group_provider):
    fixture_group_provider.client.groups.list_by_namespace.return_value = [Mock(), Mock()]

    result = fixture_group_provider.list(
        namespace_name="ns1",
        resource_group_name="rg1",
    )

    assert len(result) == 2
    fixture_group_provider.client.groups.list_by_namespace.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
    )


def test_group_create_minimal(fixture_group_provider, mock_poller):
    expected = {"name": "g1"}
    fixture_group_provider.client.groups.begin_create_or_replace.return_value = mock_poller(expected)

    result = fixture_group_provider.create(
        group_name="g1",
        namespace_name="ns1",
        resource_group_name="rg1",
        query="attributes.x == 'y'",
    )

    assert result == expected
    fixture_group_provider.client.groups.begin_create_or_replace.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        group_name="g1",
        resource={
            "location": "westus",
            "properties": {
                "groupType": "Device",
                "query": "attributes.x == 'y'",
            },
        },
    )


def test_group_create_full(fixture_group_provider, mock_poller):
    fixture_group_provider.client.groups.begin_create_or_replace.return_value = mock_poller(Mock())

    fixture_group_provider.create(
        group_name="g1",
        namespace_name="ns1",
        resource_group_name="rg1",
        query="q",
        group_type="Device",
        display_name="My group",
        description="hello",
        location="eastus",
        tags={"env": "demo"},
    )

    fixture_group_provider.client.groups.begin_create_or_replace.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        group_name="g1",
        resource={
            "location": "eastus",
            "properties": {
                "groupType": "Device",
                "query": "q",
                "displayName": "My group",
                "description": "hello",
            },
            "tags": {"env": "demo"},
        },
    )


def test_group_delete(fixture_group_provider, mock_poller):
    fixture_group_provider.client.groups.begin_delete.return_value = mock_poller(None)

    fixture_group_provider.delete(
        group_name="g1",
        namespace_name="ns1",
        resource_group_name="rg1",
    )

    fixture_group_provider.client.groups.begin_delete.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        group_name="g1",
    )
