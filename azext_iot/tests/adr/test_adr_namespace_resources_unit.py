# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import inspect
import json
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from azext_iot.adr import (
    commands_asset,
    commands_discovered_asset,
    commands_discovered_device,
)
from azext_iot.adr.providers.asset import AssetProvider
from azext_iot.adr.providers.discovered_asset import DiscoveredAssetProvider
from azext_iot.adr.providers.discovered_device import DiscoveredDeviceProvider

RG = "test-rg"
NS = "test-namespace"
RESOURCE = "test-resource"
EXTENDED_LOCATION = {"name": "/customLocations/test", "type": "CustomLocation"}
DEVICE_REF = {"deviceName": "device", "endpointName": "default"}

ASSET_CREATE_PROPERTIES = {
    "enabled",
    "externalAssetId",
    "displayName",
    "description",
    "deviceRef",
    "assetTypeRefs",
    "manufacturer",
    "manufacturerUri",
    "model",
    "productCode",
    "hardwareRevision",
    "softwareRevision",
    "documentationUri",
    "serialNumber",
    "attributes",
    "discoveredAssetRefs",
    "defaultDatasetsConfiguration",
    "defaultEventsConfiguration",
    "defaultStreamsConfiguration",
    "defaultManagementGroupsConfiguration",
    "defaultDatasetsDestinations",
    "defaultEventsDestinations",
    "defaultStreamsDestinations",
    "datasets",
    "eventGroups",
    "streams",
    "managementGroups",
}
ASSET_UPDATE_PROPERTIES = ASSET_CREATE_PROPERTIES - {
    "externalAssetId",
    "deviceRef",
    "discoveredAssetRefs",
}
DISCOVERED_DEVICE_CREATE_PROPERTIES = {
    "externalDeviceId",
    "endpoints",
    "manufacturer",
    "model",
    "operatingSystem",
    "operatingSystemVersion",
    "attributes",
    "discoveryId",
    "version",
}
DISCOVERED_DEVICE_UPDATE_PROPERTIES = {
    "externalDeviceId",
    "endpoints",
    "operatingSystemVersion",
    "attributes",
    "discoveryId",
    "version",
}
DISCOVERED_ASSET_CREATE_PROPERTIES = {
    "deviceRef",
    "displayName",
    "assetTypeRefs",
    "description",
    "discoveryId",
    "externalAssetId",
    "version",
    "manufacturer",
    "manufacturerUri",
    "model",
    "productCode",
    "hardwareRevision",
    "softwareRevision",
    "documentationUri",
    "serialNumber",
    "attributes",
    "defaultDatasetsConfiguration",
    "defaultEventsConfiguration",
    "defaultStreamsConfiguration",
    "defaultManagementGroupsConfiguration",
    "defaultDatasetsDestinations",
    "defaultEventsDestinations",
    "defaultStreamsDestinations",
    "datasets",
    "eventGroups",
    "streams",
    "managementGroups",
}
DISCOVERED_ASSET_UPDATE_PROPERTIES = DISCOVERED_ASSET_CREATE_PROPERTIES - {
    "externalAssetId"
}

RESOURCE_CASES = [
    pytest.param(
        AssetProvider,
        "namespace_assets",
        "asset_name",
        "asset",
        {"deviceRef": DEVICE_REF},
        id="asset",
    ),
    pytest.param(
        DiscoveredDeviceProvider,
        "namespace_discovered_devices",
        "discovered_device_name",
        "discovered device",
        {"discoveryId": "discovery", "version": 0},
        id="discovered-device",
    ),
    pytest.param(
        DiscoveredAssetProvider,
        "namespace_discovered_assets",
        "discovered_asset_name",
        "discovered asset",
        {
            "deviceRef": DEVICE_REF,
            "discoveryId": "discovery",
            "version": 0,
        },
        id="discovered-asset",
    ),
]

COMMAND_CASES = [
    pytest.param(
        commands_asset,
        "asset",
        "AssetProvider",
        "asset_name",
        id="asset",
    ),
    pytest.param(
        commands_discovered_device,
        "discovered_device",
        "DiscoveredDeviceProvider",
        "discovered_device_name",
        id="discovered-device",
    ),
    pytest.param(
        commands_discovered_asset,
        "discovered_asset",
        "DiscoveredAssetProvider",
        "discovered_asset_name",
        id="discovered-asset",
    ),
]


def _provider(provider_type, operation_group):
    provider = object.__new__(provider_type)
    provider.cmd = Mock()
    provider.client = Mock()
    operations = Mock()
    setattr(provider.client, operation_group, operations)
    return provider, operations


def _resource_arguments(name_argument):
    return {
        "resource_group_name": RG,
        "namespace_name": NS,
        name_argument: RESOURCE,
    }


def test_provider_configuration_matches_2026_11_02_spec():
    assert AssetProvider.operation_group == "namespace_assets"
    assert AssetProvider.name_argument == "asset_name"
    assert AssetProvider.resource_label == "asset"
    assert AssetProvider.create_allowed_properties == ASSET_CREATE_PROPERTIES
    assert AssetProvider.create_required_properties == {"deviceRef"}
    assert AssetProvider.update_allowed_properties == ASSET_UPDATE_PROPERTIES

    assert (
        DiscoveredDeviceProvider.operation_group
        == "namespace_discovered_devices"
    )
    assert DiscoveredDeviceProvider.name_argument == "discovered_device_name"
    assert DiscoveredDeviceProvider.resource_label == "discovered device"
    assert (
        DiscoveredDeviceProvider.create_allowed_properties
        == DISCOVERED_DEVICE_CREATE_PROPERTIES
    )
    assert DiscoveredDeviceProvider.create_required_properties == {
        "discoveryId",
        "version",
    }
    assert (
        DiscoveredDeviceProvider.update_allowed_properties
        == DISCOVERED_DEVICE_UPDATE_PROPERTIES
    )

    assert DiscoveredAssetProvider.operation_group == "namespace_discovered_assets"
    assert DiscoveredAssetProvider.name_argument == "discovered_asset_name"
    assert DiscoveredAssetProvider.resource_label == "discovered asset"
    assert (
        DiscoveredAssetProvider.create_allowed_properties
        == DISCOVERED_ASSET_CREATE_PROPERTIES
    )
    assert DiscoveredAssetProvider.create_required_properties == {
        "deviceRef",
        "discoveryId",
        "version",
    }
    assert (
        DiscoveredAssetProvider.update_allowed_properties
        == DISCOVERED_ASSET_UPDATE_PROPERTIES
    )


@pytest.mark.parametrize(
    "provider_type,operation_group,name_argument,_label,properties", RESOURCE_CASES
)
def test_create_uses_exact_sdk_group_name_and_body(
    provider_type, operation_group, name_argument, _label, properties
):
    provider, operations = _provider(provider_type, operation_group)
    poller = Mock()
    operations.begin_create_or_replace.return_value = poller

    result = provider.create(
        RESOURCE,
        NS,
        RG,
        properties=json.dumps(properties),
        extended_location=json.dumps(EXTENDED_LOCATION),
        location="centraluseuap",
        tags={"env": "test"},
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()
    operations.begin_create_or_replace.assert_called_once_with(
        **_resource_arguments(name_argument),
        resource={
            "location": "centraluseuap",
            "extendedLocation": EXTENDED_LOCATION,
            "properties": properties,
            "tags": {"env": "test"},
        },
    )


@pytest.mark.parametrize(
    "provider_type,operation_group,name_argument,_label,properties", RESOURCE_CASES
)
def test_create_requires_each_required_top_level_property(
    provider_type, operation_group, name_argument, _label, properties
):
    del name_argument
    for required_property in provider_type.create_required_properties:
        provider, operations = _provider(provider_type, operation_group)
        incomplete = dict(properties)
        incomplete.pop(required_property)

        with pytest.raises(
            RequiredArgumentMissingError, match=required_property
        ):
            provider.create(
                RESOURCE,
                NS,
                RG,
                properties=incomplete,
                extended_location=EXTENDED_LOCATION,
                location="centraluseuap",
            )
        operations.begin_create_or_replace.assert_not_called()


@pytest.mark.parametrize(
    "provider_type,operation_group,properties,required_property",
    [
        pytest.param(
            AssetProvider,
            "namespace_assets",
            {"deviceRef": None},
            "deviceRef",
            id="asset",
        ),
        pytest.param(
            DiscoveredDeviceProvider,
            "namespace_discovered_devices",
            {"discoveryId": "discovery", "version": None},
            "version",
            id="discovered-device",
        ),
        pytest.param(
            DiscoveredAssetProvider,
            "namespace_discovered_assets",
            {
                "deviceRef": DEVICE_REF,
                "discoveryId": None,
                "version": 0,
            },
            "discoveryId",
            id="discovered-asset",
        ),
    ],
)
def test_create_treats_null_required_property_as_missing(
    provider_type, operation_group, properties, required_property
):
    provider, operations = _provider(provider_type, operation_group)

    with pytest.raises(RequiredArgumentMissingError, match=required_property):
        provider.create(
            RESOURCE,
            NS,
            RG,
            properties=properties,
            extended_location=EXTENDED_LOCATION,
            location="centraluseuap",
        )
    operations.begin_create_or_replace.assert_not_called()


@pytest.mark.parametrize(
    "provider_type,operation_group,properties",
    [
        pytest.param(
            AssetProvider,
            "namespace_assets",
            {"deviceRef": {}},
            id="asset-missing-device-fields",
        ),
        pytest.param(
            DiscoveredAssetProvider,
            "namespace_discovered_assets",
            {
                "deviceRef": {"deviceName": "device"},
                "discoveryId": "discovery",
                "version": 1,
            },
            id="discovered-asset-missing-endpoint",
        ),
        pytest.param(
            AssetProvider,
            "namespace_assets",
            {"deviceRef": "device"},
            id="asset-non-object-device-ref",
        ),
        pytest.param(
            AssetProvider,
            "namespace_assets",
            {
                "deviceRef": {
                    "deviceName": "device",
                    "endpointName": "endpoint",
                    "extra": "invalid",
                }
            },
            id="asset-unsupported-device-ref-field",
        ),
    ],
)
def test_create_validates_device_reference(
    provider_type, operation_group, properties
):
    provider, operations = _provider(provider_type, operation_group)

    with pytest.raises(InvalidArgumentValueError, match="deviceRef"):
        provider.create(
            RESOURCE,
            NS,
            RG,
            properties=properties,
            extended_location=EXTENDED_LOCATION,
            location="centraluseuap",
        )
    operations.begin_create_or_replace.assert_not_called()


def test_discovered_asset_update_rejects_empty_device_reference():
    provider, operations = _provider(
        DiscoveredAssetProvider, "namespace_discovered_assets"
    )

    with pytest.raises(InvalidArgumentValueError, match="deviceRef"):
        provider.update(RESOURCE, NS, RG, properties={"deviceRef": {}})
    operations.begin_update.assert_not_called()


@pytest.mark.parametrize(
    "provider_type,operation_group,properties",
    [
        pytest.param(
            DiscoveredDeviceProvider,
            "namespace_discovered_devices",
            {"discoveryId": "", "version": 1},
            id="empty-discovery-id",
        ),
        pytest.param(
            DiscoveredDeviceProvider,
            "namespace_discovered_devices",
            {"discoveryId": "discovery", "version": -1},
            id="negative-version",
        ),
        pytest.param(
            DiscoveredAssetProvider,
            "namespace_discovered_assets",
            {
                "deviceRef": DEVICE_REF,
                "discoveryId": "discovery",
                "version": "one",
            },
            id="non-integer-version",
        ),
    ],
)
def test_create_validates_discovery_identifiers(
    provider_type, operation_group, properties
):
    provider, operations = _provider(provider_type, operation_group)

    with pytest.raises(InvalidArgumentValueError):
        provider.create(
            RESOURCE,
            NS,
            RG,
            properties=properties,
            extended_location=EXTENDED_LOCATION,
            location="centraluseuap",
        )
    operations.begin_create_or_replace.assert_not_called()


@pytest.mark.parametrize(
    "provider_type,operation_group,_name_argument,_label,properties",
    RESOURCE_CASES,
)
def test_create_rejects_read_only_property(
    provider_type, operation_group, _name_argument, _label, properties
):
    provider, operations = _provider(provider_type, operation_group)
    invalid_properties = {**properties, "provisioningState": "Succeeded"}

    with pytest.raises(
        InvalidArgumentValueError, match="provisioningState"
    ):
        provider.create(
            RESOURCE,
            NS,
            RG,
            properties=invalid_properties,
            extended_location=EXTENDED_LOCATION,
            location="centraluseuap",
        )
    operations.begin_create_or_replace.assert_not_called()


@pytest.mark.parametrize("property_name", ["status", "uuid", "version"])
def test_asset_create_rejects_version_and_status_fields(property_name):
    provider, operations = _provider(AssetProvider, "namespace_assets")

    with pytest.raises(InvalidArgumentValueError, match=property_name):
        provider.create(
            RESOURCE,
            NS,
            RG,
            properties={"deviceRef": DEVICE_REF, property_name: "read-only"},
            extended_location=EXTENDED_LOCATION,
            location="centraluseuap",
        )
    operations.begin_create_or_replace.assert_not_called()


def test_create_reads_properties_from_json_file():
    provider, operations = _provider(AssetProvider, "namespace_assets")
    poller = Mock()
    operations.begin_create_or_replace.return_value = poller
    path = Path(__file__).with_name(
        f".namespace-resource-properties-{uuid4().hex}.json"
    )
    properties = {"deviceRef": DEVICE_REF, "displayName": "file asset"}
    path.write_text(json.dumps(properties), encoding="utf-8")

    try:
        provider.create(
            RESOURCE,
            NS,
            RG,
            properties=str(path),
            extended_location=EXTENDED_LOCATION,
            location="centraluseuap",
            no_wait=True,
        )
    finally:
        path.unlink(missing_ok=True)

    resource = operations.begin_create_or_replace.call_args.kwargs["resource"]
    assert resource["properties"] == properties


@pytest.mark.parametrize(
    "extended_location,expected_property",
    [
        pytest.param({"name": "custom"}, "type", id="missing-type"),
        pytest.param({"type": "CustomLocation"}, "name", id="missing-name"),
        pytest.param(
            {**EXTENDED_LOCATION, "region": "centraluseuap"},
            "region",
            id="unsupported",
        ),
    ],
)
def test_create_validates_extended_location(
    extended_location, expected_property
):
    provider, operations = _provider(AssetProvider, "namespace_assets")

    with pytest.raises(
        (InvalidArgumentValueError, RequiredArgumentMissingError),
        match=expected_property,
    ):
        provider.create(
            RESOURCE,
            NS,
            RG,
            properties={"deviceRef": DEVICE_REF},
            extended_location=extended_location,
            location="centraluseuap",
        )
    operations.begin_create_or_replace.assert_not_called()


@pytest.mark.parametrize(
    "provider_type,operation_group,name_argument,properties",
    [
        pytest.param(
            AssetProvider,
            "namespace_assets",
            "asset_name",
            {"enabled": False, "displayName": "updated"},
            id="asset",
        ),
        pytest.param(
            DiscoveredDeviceProvider,
            "namespace_discovered_devices",
            "discovered_device_name",
            {"operatingSystemVersion": "2", "version": 2},
            id="discovered-device",
        ),
        pytest.param(
            DiscoveredAssetProvider,
            "namespace_discovered_assets",
            "discovered_asset_name",
            {"deviceRef": DEVICE_REF, "displayName": "updated", "version": 2},
            id="discovered-asset",
        ),
    ],
)
def test_update_uses_exact_sdk_group_name_and_patch_body(
    provider_type, operation_group, name_argument, properties
):
    provider, operations = _provider(provider_type, operation_group)
    poller = Mock()
    operations.begin_update.return_value = poller

    result = provider.update(
        RESOURCE,
        NS,
        RG,
        properties=json.dumps(properties),
        tags={},
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()
    operations.begin_update.assert_called_once_with(
        **_resource_arguments(name_argument),
        properties={"properties": properties, "tags": {}},
    )


@pytest.mark.parametrize(
    "provider_type,operation_group,property_name",
    [
        pytest.param(
            AssetProvider,
            "namespace_assets",
            "externalAssetId",
            id="asset-external-id",
        ),
        pytest.param(
            AssetProvider,
            "namespace_assets",
            "deviceRef",
            id="asset-device-ref",
        ),
        pytest.param(
            AssetProvider,
            "namespace_assets",
            "discoveredAssetRefs",
            id="asset-discovered-refs",
        ),
        pytest.param(
            DiscoveredDeviceProvider,
            "namespace_discovered_devices",
            "manufacturer",
            id="discovered-device-manufacturer",
        ),
        pytest.param(
            DiscoveredDeviceProvider,
            "namespace_discovered_devices",
            "model",
            id="discovered-device-model",
        ),
        pytest.param(
            DiscoveredDeviceProvider,
            "namespace_discovered_devices",
            "operatingSystem",
            id="discovered-device-os",
        ),
        pytest.param(
            DiscoveredAssetProvider,
            "namespace_discovered_assets",
            "externalAssetId",
            id="discovered-asset-external-id",
        ),
    ],
)
def test_update_rejects_immutable_properties(
    provider_type, operation_group, property_name
):
    provider, operations = _provider(provider_type, operation_group)

    with pytest.raises(InvalidArgumentValueError, match=property_name):
        provider.update(
            RESOURCE,
            NS,
            RG,
            properties={property_name: "immutable"},
        )
    operations.begin_update.assert_not_called()


@pytest.mark.parametrize(
    "provider_type,operation_group,_name_argument,_label,_properties",
    RESOURCE_CASES,
)
@pytest.mark.parametrize("properties", [None, {}], ids=["omitted", "empty-object"])
def test_update_rejects_empty_patch(
    provider_type,
    operation_group,
    _name_argument,
    _label,
    _properties,
    properties,
):
    provider, operations = _provider(provider_type, operation_group)

    with pytest.raises(RequiredArgumentMissingError, match="Nothing to update"):
        provider.update(RESOURCE, NS, RG, properties=properties)
    operations.begin_update.assert_not_called()


@pytest.mark.parametrize(
    "provider_type,operation_group,name_argument,_label,_properties",
    RESOURCE_CASES,
)
def test_update_allows_empty_tags(
    provider_type, operation_group, name_argument, _label, _properties
):
    provider, operations = _provider(provider_type, operation_group)
    poller = Mock()
    operations.begin_update.return_value = poller

    provider.update(RESOURCE, NS, RG, tags={}, no_wait=True)

    operations.begin_update.assert_called_once_with(
        **_resource_arguments(name_argument),
        properties={"tags": {}},
    )


@pytest.mark.parametrize(
    "provider_type,operation_group,name_argument,_label,_properties",
    RESOURCE_CASES,
)
def test_show_list_and_delete_use_exact_sdk_parameters(
    provider_type, operation_group, name_argument, _label, _properties
):
    provider, operations = _provider(provider_type, operation_group)
    operations.get.return_value = {"name": RESOURCE}
    operations.list_by_resource_group.return_value = iter(
        [{"name": "one"}, {"name": "two"}]
    )
    poller = Mock()
    operations.begin_delete.return_value = poller

    assert provider.show(RESOURCE, NS, RG) == {"name": RESOURCE}
    assert provider.list(NS, RG) == [{"name": "one"}, {"name": "two"}]
    assert provider.delete(RESOURCE, NS, RG, no_wait=True) is poller

    operations.get.assert_called_once_with(**_resource_arguments(name_argument))
    operations.list_by_resource_group.assert_called_once_with(
        resource_group_name=RG,
        namespace_name=NS,
    )
    operations.begin_delete.assert_called_once_with(
        **_resource_arguments(name_argument)
    )
    poller.result.assert_not_called()


def test_asset_execute_action_builds_sdk_body_and_honors_no_wait():
    provider, operations = _provider(AssetProvider, "namespace_assets")
    poller = Mock()
    operations.begin_execute_action.return_value = poller

    result = provider.execute_action(
        RESOURCE,
        NS,
        RG,
        management_action_name="reboot",
        management_group_name="maintenance",
        payload='{"delaySeconds": 5}',
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()
    operations.begin_execute_action.assert_called_once_with(
        **_resource_arguments("asset_name"),
        body={
            "managementActionName": "reboot",
            "managementGroupName": "maintenance",
            "payload": {"delaySeconds": 5},
        },
    )


def test_asset_execute_action_omits_optional_payload():
    provider, operations = _provider(AssetProvider, "namespace_assets")
    operations.begin_execute_action.return_value = Mock()

    provider.execute_action(
        RESOURCE,
        NS,
        RG,
        management_action_name="reboot",
        management_group_name="maintenance",
        no_wait=True,
    )

    operations.begin_execute_action.assert_called_once_with(
        **_resource_arguments("asset_name"),
        body={
            "managementActionName": "reboot",
            "managementGroupName": "maintenance",
        },
    )


def test_asset_execute_action_requires_object_payload():
    provider, operations = _provider(AssetProvider, "namespace_assets")

    with pytest.raises(InvalidArgumentValueError, match="JSON object"):
        provider.execute_action(
            RESOURCE,
            NS,
            RG,
            management_action_name="reboot",
            management_group_name="maintenance",
            payload="[1, 2]",
        )
    operations.begin_execute_action.assert_not_called()


@pytest.mark.parametrize(
    "action_name,group_name",
    [("", "maintenance"), ("reboot", "")],
)
def test_asset_execute_action_requires_non_empty_names(
    action_name, group_name
):
    provider, operations = _provider(AssetProvider, "namespace_assets")

    with pytest.raises(RequiredArgumentMissingError):
        provider.execute_action(
            RESOURCE,
            NS,
            RG,
            management_action_name=action_name,
            management_group_name=group_name,
        )
    operations.begin_execute_action.assert_not_called()


@pytest.mark.parametrize(
    "module,prefix,provider_attribute,name_parameter", COMMAND_CASES
)
def test_command_signatures(
    module, prefix, provider_attribute, name_parameter
):
    del provider_attribute
    expected = {
        "create": [
            "cmd",
            name_parameter,
            "namespace_name",
            "resource_group_name",
            "properties",
            "extended_location",
            "location",
            "tags",
            "no_wait",
        ],
        "show": [
            "cmd",
            name_parameter,
            "namespace_name",
            "resource_group_name",
        ],
        "list": ["cmd", "namespace_name", "resource_group_name"],
        "update": [
            "cmd",
            name_parameter,
            "namespace_name",
            "resource_group_name",
            "properties",
            "tags",
            "no_wait",
        ],
        "delete": [
            "cmd",
            name_parameter,
            "namespace_name",
            "resource_group_name",
            "no_wait",
        ],
    }

    for operation, parameters in expected.items():
        function = getattr(module, f"adr_{prefix}_{operation}")
        assert list(inspect.signature(function).parameters) == parameters


@pytest.mark.parametrize(
    "module,prefix,provider_attribute,name_parameter", COMMAND_CASES
)
def test_crud_commands_delegate_family_name_as_resource_name(
    module, prefix, provider_attribute, name_parameter
):
    provider = Mock()
    cmd = Mock()
    with patch.object(module, provider_attribute, return_value=provider):
        create = getattr(module, f"adr_{prefix}_create")
        create(
            cmd,
            **{
                name_parameter: RESOURCE,
                "namespace_name": NS,
                "resource_group_name": RG,
                "properties": {"property": "value"},
                "extended_location": EXTENDED_LOCATION,
                "location": "centraluseuap",
                "tags": {"env": "test"},
                "no_wait": True,
            },
        )
        getattr(module, f"adr_{prefix}_show")(
            cmd,
            **{
                name_parameter: RESOURCE,
                "namespace_name": NS,
                "resource_group_name": RG,
            },
        )
        getattr(module, f"adr_{prefix}_list")(
            cmd, namespace_name=NS, resource_group_name=RG
        )
        getattr(module, f"adr_{prefix}_update")(
            cmd,
            **{
                name_parameter: RESOURCE,
                "namespace_name": NS,
                "resource_group_name": RG,
                "properties": {"property": "updated"},
                "tags": {},
                "no_wait": True,
            },
        )
        getattr(module, f"adr_{prefix}_delete")(
            cmd,
            **{
                name_parameter: RESOURCE,
                "namespace_name": NS,
                "resource_group_name": RG,
                "no_wait": True,
            },
        )

    provider.create.assert_called_once_with(
        resource_name=RESOURCE,
        namespace_name=NS,
        resource_group_name=RG,
        properties={"property": "value"},
        extended_location=EXTENDED_LOCATION,
        location="centraluseuap",
        tags={"env": "test"},
        no_wait=True,
    )
    provider.show.assert_called_once_with(
        resource_name=RESOURCE,
        namespace_name=NS,
        resource_group_name=RG,
    )
    provider.list.assert_called_once_with(
        namespace_name=NS,
        resource_group_name=RG,
    )
    provider.update.assert_called_once_with(
        resource_name=RESOURCE,
        namespace_name=NS,
        resource_group_name=RG,
        properties={"property": "updated"},
        tags={},
        no_wait=True,
    )
    provider.delete.assert_called_once_with(
        resource_name=RESOURCE,
        namespace_name=NS,
        resource_group_name=RG,
        no_wait=True,
    )


def test_asset_execute_action_command_signature_and_delegation():
    assert list(
        inspect.signature(commands_asset.adr_asset_execute_action).parameters
    ) == [
        "cmd",
        "asset_name",
        "namespace_name",
        "resource_group_name",
        "management_action_name",
        "management_group_name",
        "payload",
        "no_wait",
    ]
    provider = Mock()
    cmd = Mock()
    with patch.object(commands_asset, "AssetProvider", return_value=provider):
        commands_asset.adr_asset_execute_action(
            cmd,
            asset_name=RESOURCE,
            namespace_name=NS,
            resource_group_name=RG,
            management_action_name="reboot",
            management_group_name="maintenance",
            payload={"delaySeconds": 5},
            no_wait=True,
        )

    provider.execute_action.assert_called_once_with(
        resource_name=RESOURCE,
        namespace_name=NS,
        resource_group_name=RG,
        management_action_name="reboot",
        management_group_name="maintenance",
        payload={"delaySeconds": 5},
        no_wait=True,
    )
