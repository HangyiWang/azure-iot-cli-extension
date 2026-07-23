# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import pytest
from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from azext_iot.adr.providers.device import _parse_json_object

ENDPOINTS = {
    "outbound": {
        "assigned": {
            "eventGridEndpoint": {
                "endpointType": "Microsoft.Devices",
                "address": "https://example.westeurope-1.eventgrid.azure.net/api/events",
            }
        }
    }
}


def test_device_json_object_parser_preserves_none():
    assert _parse_json_object(None, "--attributes") is None


def test_device_create_minimal(fixture_device_provider, mock_poller):
    fixture_device_provider.client.namespace_devices.begin_create_or_replace.return_value = (
        mock_poller({"name": "device"})
    )

    result = fixture_device_provider.create(
        "device", "namespace", "rg", location="eastus"
    )

    assert result == {"name": "device"}
    fixture_device_provider.client.namespace_devices.begin_create_or_replace.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        device_name="device",
        resource={"location": "eastus"},
    )


def test_device_create_all_2026_fields(fixture_device_provider, mock_poller):
    fixture_device_provider.client.namespace_devices.begin_create_or_replace.return_value = (
        mock_poller({"name": "device"})
    )

    fixture_device_provider.create(
        "device",
        "namespace",
        "rg",
        location="eastus",
        tags={"env": "test"},
        manufacturer="Contoso",
        model="X100",
        operating_system="Linux",
        operating_system_version="5.15",
        external_device_id="external-42",
        enabled=False,
        attributes='{"site":"west"}',
        endpoints=ENDPOINTS,
        discovered_device_ref="discovered-1",
    )

    resource = fixture_device_provider.client.namespace_devices.begin_create_or_replace.call_args.kwargs[
        "resource"
    ]
    assert resource == {
        "location": "eastus",
        "tags": {"env": "test"},
        "properties": {
            "manufacturer": "Contoso",
            "model": "X100",
            "operatingSystem": "Linux",
            "operatingSystemVersion": "5.15",
            "externalDeviceId": "external-42",
            "enabled": False,
            "attributes": {"site": "west"},
            "endpoints": ENDPOINTS,
            "discoveredDeviceRef": "discovered-1",
        },
    }


def test_device_create_inherits_parent_namespace_location(
    fixture_device_provider, mock_poller
):
    fixture_device_provider.client.namespaces.get.return_value = {
        "location": "westus2"
    }
    fixture_device_provider.client.namespace_devices.begin_create_or_replace.return_value = (
        mock_poller({})
    )

    fixture_device_provider.create("device", "namespace", "rg")

    fixture_device_provider.client.namespaces.get.assert_called_once_with(
        resource_group_name="rg", namespace_name="namespace"
    )
    resource = fixture_device_provider.client.namespace_devices.begin_create_or_replace.call_args.kwargs[
        "resource"
    ]
    assert resource["location"] == "westus2"


def test_device_create_supports_extended_location(
    fixture_device_provider, mock_poller
):
    fixture_device_provider.client.namespace_devices.begin_create_or_replace.return_value = (
        mock_poller({})
    )

    fixture_device_provider.create(
        "device",
        "namespace",
        "rg",
        location="eastus",
        extended_location='{"name":"/customLocations/edge","type":"CustomLocation"}',
    )

    resource = fixture_device_provider.client.namespace_devices.begin_create_or_replace.call_args.kwargs[
        "resource"
    ]
    assert resource["extendedLocation"] == {
        "name": "/customLocations/edge",
        "type": "CustomLocation",
    }


@pytest.mark.parametrize(
    "extended_location",
    [
        '{"name":"/customLocations/edge"}',
        '{"name":"","type":"CustomLocation"}',
        '{"name":"/customLocations/edge","type":"CustomLocation","extra":true}',
    ],
)
def test_device_create_validates_extended_location(
    fixture_device_provider, extended_location
):
    with pytest.raises(
        (InvalidArgumentValueError, RequiredArgumentMissingError)
    ):
        fixture_device_provider.create(
            "device",
            "namespace",
            "rg",
            location="eastus",
            extended_location=extended_location,
        )
    fixture_device_provider.client.namespace_devices.begin_create_or_replace.assert_not_called()


@pytest.mark.parametrize(
    "argument,value",
    [
        ("attributes", "[]"),
        ("attributes", "[1, 2]"),
        ("endpoints", '"string"'),
        ("endpoints", "[]"),
    ],
)
def test_device_create_requires_json_objects(
    fixture_device_provider, argument, value
):
    with pytest.raises(InvalidArgumentValueError, match="JSON object"):
        fixture_device_provider.create(
            "device",
            "namespace",
            "rg",
            location="eastus",
            **{argument: value},
        )
    fixture_device_provider.client.namespace_devices.begin_create_or_replace.assert_not_called()


def test_device_create_rejects_unknown_endpoint_groups(fixture_device_provider):
    with pytest.raises(InvalidArgumentValueError, match="inbound.*outbound"):
        fixture_device_provider.create(
            "device",
            "namespace",
            "rg",
            location="eastus",
            endpoints='{"mqtt": {}}',
        )


def test_device_create_no_wait(fixture_device_provider, mock_poller):
    poller = mock_poller({"name": "device"})
    fixture_device_provider.client.namespace_devices.begin_create_or_replace.return_value = (
        poller
    )

    result = fixture_device_provider.create(
        "device", "namespace", "rg", location="eastus", no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()


def test_device_show_list_and_delete(fixture_device_provider, mock_poller):
    fixture_device_provider.client.namespace_devices.get.return_value = {
        "name": "device"
    }
    fixture_device_provider.client.namespace_devices.list_by_resource_group.return_value = iter(
        [{"name": "one"}, {"name": "two"}]
    )
    fixture_device_provider.client.namespace_devices.begin_delete.return_value = (
        mock_poller(None)
    )

    assert fixture_device_provider.show("device", "namespace", "rg") == {
        "name": "device"
    }
    assert fixture_device_provider.list("namespace", "rg") == [
        {"name": "one"},
        {"name": "two"},
    ]
    fixture_device_provider.delete("device", "namespace", "rg")

    fixture_device_provider.client.namespace_devices.get.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        device_name="device",
    )
    fixture_device_provider.client.namespace_devices.list_by_resource_group.assert_called_once_with(
        resource_group_name="rg", namespace_name="namespace"
    )
    fixture_device_provider.client.namespace_devices.begin_delete.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        device_name="device",
    )


def test_device_update_all_mutable_fields(fixture_device_provider, mock_poller):
    fixture_device_provider.client.namespace_devices.begin_update.return_value = (
        mock_poller({"name": "device"})
    )

    fixture_device_provider.update(
        "device",
        "namespace",
        "rg",
        enabled=False,
        tags={"env": "prod"},
        operating_system_version="6.0",
        attributes={"site": "east"},
        endpoints=ENDPOINTS,
    )

    properties = fixture_device_provider.client.namespace_devices.begin_update.call_args.kwargs[
        "properties"
    ]
    assert properties == {
        "properties": {
            "enabled": False,
            "operatingSystemVersion": "6.0",
            "attributes": {"site": "east"},
            "endpoints": ENDPOINTS,
        },
        "tags": {"env": "prod"},
    }


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"tags": {}}, {"tags": {}}),
        ({"attributes": "{}"}, {"properties": {"attributes": {}}}),
        ({"endpoints": "{}"}, {"properties": {"endpoints": {}}}),
        (
            {"operating_system_version": ""},
            {"properties": {"operatingSystemVersion": ""}},
        ),
    ],
)
def test_device_update_clear_values(
    fixture_device_provider, mock_poller, kwargs, expected
):
    fixture_device_provider.client.namespace_devices.begin_update.return_value = (
        mock_poller({})
    )

    fixture_device_provider.update("device", "namespace", "rg", **kwargs)

    assert (
        fixture_device_provider.client.namespace_devices.begin_update.call_args.kwargs[
            "properties"
        ]
        == expected
    )


@pytest.mark.parametrize(
    "argument,value",
    [("attributes", "[]"), ("endpoints", "[1]")],
)
def test_device_update_requires_json_objects(
    fixture_device_provider, argument, value
):
    with pytest.raises(InvalidArgumentValueError, match="JSON object"):
        fixture_device_provider.update(
            "device", "namespace", "rg", **{argument: value}
        )
    fixture_device_provider.client.namespace_devices.begin_update.assert_not_called()


@pytest.mark.parametrize("argument", ["attributes", "endpoints"])
def test_device_update_rejects_empty_json_objects(
    fixture_device_provider, argument
):
    with pytest.raises(InvalidArgumentValueError):
        fixture_device_provider.update(
            "device", "namespace", "rg", **{argument: ""}
        )


def test_device_update_rejects_empty_patch(fixture_device_provider):
    with pytest.raises(RequiredArgumentMissingError, match="Nothing to update"):
        fixture_device_provider.update("device", "namespace", "rg")
    fixture_device_provider.client.namespace_devices.begin_update.assert_not_called()


def test_device_update_no_wait(fixture_device_provider, mock_poller):
    poller = mock_poller({"name": "device"})
    fixture_device_provider.client.namespace_devices.begin_update.return_value = poller

    result = fixture_device_provider.update(
        "device", "namespace", "rg", endpoints="{}", no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()


def test_device_delete_no_wait(fixture_device_provider, mock_poller):
    poller = mock_poller(None)
    fixture_device_provider.client.namespace_devices.begin_delete.return_value = poller

    result = fixture_device_provider.delete(
        "device", "namespace", "rg", no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()
