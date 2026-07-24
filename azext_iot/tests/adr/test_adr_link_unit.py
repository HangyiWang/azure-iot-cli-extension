# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import inspect

import pytest
from azure.cli.core.azclierror import (
    ArgumentUsageError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)

from azext_iot.adr.common import (
    ADU_ENDPOINT_TYPE,
    DPS_ENDPOINT_TYPE,
    IOT_HUB_ENDPOINT_TYPE,
    build_mi_body,
)
from azext_iot.adr.providers.link import (
    LinkProvider,
    _endpoint_update_body,
    _parse_adu_resource_id,
    _parse_dps_resource_id,
)


HUB_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/"
    "Microsoft.Devices/IotHubs/hub"
)
DPS_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/"
    "Microsoft.Devices/provisioningServices/dps"
)
ADU_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/"
    "Microsoft.DeviceUpdate/updateInstances/adu"
)
UAMI_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/"
    "Microsoft.ManagedIdentity/userAssignedIdentities/identity"
)


def _namespace(*, hubs=None, dps=None, adu=None):
    return {
        "properties": {
            "messaging": {"endpoints": hubs or {}},
            "provisioning": {"endpoints": dps or {}},
            "updating": {"endpoints": adu or {}},
        }
    }


def _endpoint(endpoint_type, resource_id, **extra):
    return {
        "endpointType": endpoint_type,
        "resourceId": resource_id,
        **extra,
    }


def test_identity_body_treats_whitespace_uami_as_unset():
    assert (
        build_mi_body(
            False,
            " ",
            sami_type="SystemAssigned",
            uami_type="UserAssigned",
        )
        is None
    )


def test_adu_contract_uses_update_instances():
    assert ADU_ENDPOINT_TYPE == "Microsoft.DeviceUpdate/updateInstances"
    assert _parse_adu_resource_id(ADU_ID) == {
        "subscription_id": "sub",
        "resource_group_name": "rg",
        "name": "adu",
    }


@pytest.mark.parametrize(
    "resource_id",
    [
        "",
        "adu",
        "/not/an/arm/id",
        (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.DeviceUpdate/linkedAccounts/adu"
        ),
        (
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.DeviceUpdate/updateInstances/adu/children/child"
        ),
        HUB_ID,
    ],
)
def test_adu_parser_rejects_non_update_instance_ids(resource_id):
    with pytest.raises(InvalidArgumentValueError):
        _parse_adu_resource_id(resource_id)


@pytest.mark.parametrize(
    "resource_id",
    [
        "",
        "dps",
        "/not/an/arm/id",
        HUB_ID,
        f"{DPS_ID}/certificates/certificate",
    ],
)
def test_dps_parser_rejects_non_dps_ids(resource_id):
    with pytest.raises(InvalidArgumentValueError):
        _parse_dps_resource_id(resource_id)


def test_hub_add_includes_create_only_provisioning_fields(
    fixture_link_provider, mock_poller
):
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        dps={"dps": _endpoint(DPS_ENDPOINT_TYPE, DPS_ID)}
    )
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {}
    )

    fixture_link_provider.hub_add(
        endpoint_name="hub-endpoint",
        namespace_name="namespace",
        resource_group_name="rg",
        hub_resource_id=HUB_ID,
        mi_system_assigned=True,
        availability="Available",
        allocation_weight=10,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs[
        "properties"
    ]
    assert body == {
        "properties": {
            "messaging": {
                "endpoints": {
                    "hub-endpoint": {
                        "endpointType": IOT_HUB_ENDPOINT_TYPE,
                        "resourceId": HUB_ID,
                        "inboundCallerIdentity": {"type": "SystemAssigned"},
                        "provisioning": {
                            "availability": "Available",
                            "allocationWeight": 10,
                        },
                    }
                }
            }
        }
    }


def test_hub_add_allows_no_inbound_identity(
    fixture_link_provider, mock_poller
):
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        dps={"dps": _endpoint(DPS_ENDPOINT_TYPE, DPS_ID)}
    )
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {}
    )

    fixture_link_provider.hub_add(
        "hub-endpoint", "namespace", "rg", HUB_ID
    )

    endpoint = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs[
        "properties"
    ]["properties"]["messaging"]["endpoints"]["hub-endpoint"]
    assert "inboundCallerIdentity" not in endpoint
    assert "provisioning" not in endpoint


def test_hub_add_requires_dps_first(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()

    with pytest.raises(ArgumentUsageError, match="Link a DPS"):
        fixture_link_provider.hub_add(
            "hub-endpoint", "namespace", "rg", HUB_ID
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_hub_update_surface_is_identity_only():
    parameters = inspect.signature(LinkProvider.hub_update).parameters
    assert "availability" not in parameters
    assert "allocation_weight" not in parameters


def test_hub_update_rotates_identity_and_drops_provisioning(
    fixture_link_provider, mock_poller
):
    existing = _endpoint(
        IOT_HUB_ENDPOINT_TYPE,
        HUB_ID,
        inboundCallerIdentity={"type": "SystemAssigned"},
        provisioning={"availability": "Available", "allocationWeight": 50},
        serviceAddress="host.azure-devices.net",
    )
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        hubs={"hub-endpoint": existing}
    )
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {}
    )

    fixture_link_provider.hub_update(
        "hub-endpoint",
        "namespace",
        "rg",
        mi_user_assigned=UAMI_ID,
    )

    endpoint = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs[
        "properties"
    ]["properties"]["messaging"]["endpoints"]["hub-endpoint"]
    assert endpoint == {
        "endpointType": IOT_HUB_ENDPOINT_TYPE,
        "resourceId": HUB_ID,
        "inboundCallerIdentity": {
            "type": "UserAssigned",
            "userAssignedIdentity": UAMI_ID,
        },
    }
    assert "provisioning" not in endpoint
    assert "serviceAddress" not in endpoint


@pytest.mark.parametrize(
    "kwargs,exception",
    [
        ({}, RequiredArgumentMissingError),
        (
            {"mi_system_assigned": True, "mi_user_assigned": UAMI_ID},
            ArgumentUsageError,
        ),
    ],
)
def test_hub_update_validates_identity(
    fixture_link_provider, kwargs, exception
):
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        hubs={"hub-endpoint": _endpoint(IOT_HUB_ENDPOINT_TYPE, HUB_ID)}
    )

    with pytest.raises(exception):
        fixture_link_provider.hub_update(
            "hub-endpoint", "namespace", "rg", **kwargs
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_hub_update_requires_existing_endpoint(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()

    with pytest.raises(ResourceNotFoundError, match="hub-endpoint"):
        fixture_link_provider.hub_update(
            "hub-endpoint",
            "namespace",
            "rg",
            mi_system_assigned=True,
        )


def test_endpoint_update_body_can_preserve_identity_or_omit_it():
    existing = _endpoint(
        IOT_HUB_ENDPOINT_TYPE,
        HUB_ID,
        inboundCallerIdentity={"type": "SystemAssigned"},
    )
    assert _endpoint_update_body(existing) == {
        "endpointType": IOT_HUB_ENDPOINT_TYPE,
        "resourceId": HUB_ID,
        "inboundCallerIdentity": {"type": "SystemAssigned"},
    }
    assert _endpoint_update_body(
        _endpoint(IOT_HUB_ENDPOINT_TYPE, HUB_ID)
    ) == {
        "endpointType": IOT_HUB_ENDPOINT_TYPE,
        "resourceId": HUB_ID,
    }


def test_hub_show_and_list_include_endpoint_names(fixture_link_provider):
    hub = _endpoint(
        IOT_HUB_ENDPOINT_TYPE, HUB_ID, serviceAddress="hub.azure-devices.net"
    )
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        hubs={
            "primary": hub,
            "future": _endpoint("Future.Type/endpoints", "/future"),
        }
    )

    assert fixture_link_provider.hub_show(
        "primary", "namespace", "rg"
    ) == {"name": "primary", **hub}
    assert fixture_link_provider.hub_list("namespace", "rg") == [
        {"name": "primary", **hub}
    ]


def test_hub_list_empty_is_list(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()
    result = fixture_link_provider.hub_list("namespace", "rg")
    assert result == []
    assert isinstance(result, list)


def test_dps_add_uses_update_body(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {}
    )

    fixture_link_provider.dps_add(
        "dps-endpoint",
        "namespace",
        "rg",
        DPS_ID,
        mi_system_assigned=True,
    )

    endpoint = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs[
        "properties"
    ]["properties"]["provisioning"]["endpoints"]["dps-endpoint"]
    assert endpoint == {
        "endpointType": DPS_ENDPOINT_TYPE,
        "resourceId": DPS_ID,
        "inboundCallerIdentity": {"type": "SystemAssigned"},
    }


def test_dps_add_requires_identity(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()

    with pytest.raises(RequiredArgumentMissingError, match="identity is required"):
        fixture_link_provider.dps_add(
            "dps-endpoint", "namespace", "rg", DPS_ID
        )


def test_dps_add_treats_whitespace_uami_as_missing(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()

    with pytest.raises(RequiredArgumentMissingError, match="identity is required"):
        fixture_link_provider.dps_add(
            "dps-endpoint",
            "namespace",
            "rg",
            DPS_ID,
            mi_user_assigned=" ",
        )


def test_dps_add_rejects_second_endpoint(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        dps={"existing": _endpoint(DPS_ENDPOINT_TYPE, DPS_ID)}
    )

    with pytest.raises(ArgumentUsageError, match="already has a linked DPS"):
        fixture_link_provider.dps_add(
            "second",
            "namespace",
            "rg",
            DPS_ID,
            mi_system_assigned=True,
        )


def test_dps_update_show_and_list_named_objects(
    fixture_link_provider, mock_poller, mocker
):
    endpoint = _endpoint(
        DPS_ENDPOINT_TYPE,
        DPS_ID,
        inboundCallerIdentity={"type": "SystemAssigned"},
    )
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        dps={"primary": endpoint}
    )
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {}
    )
    dps_client = mocker.patch(
        "azext_iot.adr.providers.link.iot_service_provisioning_factory"
    ).return_value.iot_dps_resource
    dps_client.get.return_value = {
        "properties": {"iotHubs": [{"name": "brownfield"}]}
    }

    fixture_link_provider.dps_update(
        "primary", "namespace", "rg", mi_user_assigned=UAMI_ID
    )
    updated = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs[
        "properties"
    ]["properties"]["provisioning"]["endpoints"]["primary"]
    assert updated["inboundCallerIdentity"]["type"] == "UserAssigned"

    shown = fixture_link_provider.dps_show("primary", "namespace", "rg")
    assert shown["name"] == "primary"
    assert shown["brownfieldHubs"] == [{"name": "brownfield"}]
    assert fixture_link_provider.dps_list("namespace", "rg") == [
        {"name": "primary", **endpoint}
    ]
    dps_client.get.assert_called_once_with(
        resource_group_name="rg", provisioning_service_name="dps"
    )


def test_dps_show_without_resource_id_still_returns_named_object(
    fixture_link_provider,
):
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        dps={"primary": {"endpointType": DPS_ENDPOINT_TYPE}}
    )

    assert fixture_link_provider.dps_show("primary", "namespace", "rg") == {
        "name": "primary",
        "endpointType": DPS_ENDPOINT_TYPE,
    }


@pytest.mark.parametrize(
    "kind,section,endpoint_type,resource_id",
    [
        ("dps", "dps", DPS_ENDPOINT_TYPE, DPS_ID),
        ("adu", "adu", ADU_ENDPOINT_TYPE, ADU_ID),
    ],
)
@pytest.mark.parametrize(
    "existing,kwargs,exception",
    [
        (True, {}, RequiredArgumentMissingError),
        (
            True,
            {"mi_system_assigned": True, "mi_user_assigned": UAMI_ID},
            ArgumentUsageError,
        ),
        (False, {"mi_system_assigned": True}, ResourceNotFoundError),
    ],
)
def test_dps_and_adu_update_validation(
    fixture_link_provider,
    kind,
    section,
    endpoint_type,
    resource_id,
    existing,
    kwargs,
    exception,
):
    endpoints = (
        {"primary": _endpoint(endpoint_type, resource_id)} if existing else {}
    )
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        **{section: endpoints}
    )

    with pytest.raises(exception):
        getattr(fixture_link_provider, f"{kind}_update")(
            "primary", "namespace", "rg", **kwargs
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


@pytest.mark.parametrize("kind,resource_id", [("dps", DPS_ID), ("adu", ADU_ID)])
def test_dps_and_adu_add_reject_mutually_exclusive_identity(
    fixture_link_provider, kind, resource_id
):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()

    with pytest.raises(ArgumentUsageError):
        getattr(fixture_link_provider, f"{kind}_add")(
            "primary",
            "namespace",
            "rg",
            resource_id,
            mi_system_assigned=True,
            mi_user_assigned=UAMI_ID,
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


@pytest.mark.parametrize("resource_id", ["not-an-arm-id", DPS_ID])
def test_dps_show_enrichment_failure_is_non_fatal(
    fixture_link_provider, mocker, resource_id
):
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        dps={"primary": _endpoint(DPS_ENDPOINT_TYPE, resource_id)}
    )
    mocker.patch(
        "azext_iot.adr.providers.link.iot_service_provisioning_factory",
        side_effect=RuntimeError("unavailable"),
    )

    result = fixture_link_provider.dps_show("primary", "namespace", "rg")

    assert result["name"] == "primary"
    assert result["brownfieldHubs"] == []


def test_adu_add_uses_update_instance_endpoint(
    fixture_link_provider, mock_poller
):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {}
    )

    fixture_link_provider.adu_add(
        "adu-endpoint",
        "namespace",
        "rg",
        ADU_ID,
        mi_system_assigned=True,
    )

    endpoint = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs[
        "properties"
    ]["properties"]["updating"]["endpoints"]["adu-endpoint"]
    assert endpoint == {
        "endpointType": "Microsoft.DeviceUpdate/updateInstances",
        "resourceId": ADU_ID,
        "inboundCallerIdentity": {"type": "SystemAssigned"},
    }


def test_adu_add_requires_identity(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()

    with pytest.raises(RequiredArgumentMissingError, match="identity is required"):
        fixture_link_provider.adu_add(
            "adu-endpoint", "namespace", "rg", ADU_ID
        )


def test_adu_add_rejects_duplicate_name(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        adu={"adu-endpoint": _endpoint(ADU_ENDPOINT_TYPE, ADU_ID)}
    )

    with pytest.raises(ArgumentUsageError, match="link adu update"):
        fixture_link_provider.adu_add(
            "adu-endpoint",
            "namespace",
            "rg",
            ADU_ID,
            mi_system_assigned=True,
        )


def test_adu_update_show_and_list_named_objects(
    fixture_link_provider, mock_poller
):
    endpoint = _endpoint(
        ADU_ENDPOINT_TYPE,
        ADU_ID,
        inboundCallerIdentity={"type": "SystemAssigned"},
        serviceAddress="https://adu.example",
    )
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        adu={"primary": endpoint}
    )
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {}
    )

    fixture_link_provider.adu_update(
        "primary", "namespace", "rg", mi_user_assigned=UAMI_ID
    )

    updated = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs[
        "properties"
    ]["properties"]["updating"]["endpoints"]["primary"]
    assert updated == {
        "endpointType": ADU_ENDPOINT_TYPE,
        "resourceId": ADU_ID,
        "inboundCallerIdentity": {
            "type": "UserAssigned",
            "userAssignedIdentity": UAMI_ID,
        },
    }
    assert fixture_link_provider.adu_show(
        "primary", "namespace", "rg"
    ) == {"name": "primary", **endpoint}
    assert fixture_link_provider.adu_list("namespace", "rg") == [
        {"name": "primary", **endpoint}
    ]


@pytest.mark.parametrize("kind", ["hub", "dps", "adu"])
def test_show_missing_endpoint_raises(
    fixture_link_provider, kind
):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()
    with pytest.raises(ResourceNotFoundError):
        getattr(fixture_link_provider, f"{kind}_show")(
            "missing", "namespace", "rg"
        )


def test_bundled_link_add_keeps_create_only_hub_fields(
    fixture_link_provider, mock_poller
):
    fixture_link_provider.client.namespaces.get.return_value = _namespace()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {}
    )

    fixture_link_provider.link_add(
        namespace_name="namespace",
        resource_group_name="rg",
        hub_endpoint_name="hub",
        hub_resource_id=HUB_ID,
        dps_endpoint_name="dps",
        dps_resource_id=DPS_ID,
        hub_mi_system_assigned=True,
        dps_mi_system_assigned=True,
        hub_availability="Available",
        hub_allocation_weight=25,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs[
        "properties"
    ]["properties"]
    assert list(body) == ["provisioning", "messaging"]
    assert body["messaging"]["endpoints"]["hub"]["provisioning"] == {
        "availability": "Available",
        "allocationWeight": 25,
    }


def test_bundled_link_add_rejects_existing_dps(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        dps={"existing": _endpoint(DPS_ENDPOINT_TYPE, DPS_ID)}
    )

    with pytest.raises(ArgumentUsageError, match="already has a linked DPS"):
        fixture_link_provider.link_add(
            namespace_name="namespace",
            resource_group_name="rg",
            hub_endpoint_name="hub",
            hub_resource_id=HUB_ID,
            dps_endpoint_name="dps",
            dps_resource_id=DPS_ID,
            dps_mi_system_assigned=True,
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_link_mutation_supports_no_wait(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.get.return_value = _namespace(
        dps={"dps": _endpoint(DPS_ENDPOINT_TYPE, DPS_ID)}
    )
    poller = mock_poller(None)
    fixture_link_provider.client.namespaces.begin_update.return_value = poller

    result = fixture_link_provider.hub_add(
        "hub", "namespace", "rg", HUB_ID, no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()


def test_remove_provider_methods_are_absent():
    for method in ("hub_remove", "dps_remove", "adu_remove"):
        assert not hasattr(LinkProvider, method)
