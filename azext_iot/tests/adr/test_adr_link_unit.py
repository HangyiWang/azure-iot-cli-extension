# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Unit tests for Azure Device Registry namespace link providers (Hub).

These tests target P2 functionality: `az iot adr ns link hub add/update/remove/show/list`.
"""

import pytest
from azure.cli.core.azclierror import (
    ArgumentUsageError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)

from azext_iot.adr.common import (
    DPS_ENDPOINT_TYPE,
    IOT_HUB_ENDPOINT_TYPE,
    ADU_ENDPOINT_TYPE,
    IdentityType,
    MessagingEndpointAvailability,
)


HUB_RESOURCE_ID = (
    "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.Devices/IotHubs/myhub"
)
UAMI_RESOURCE_ID = (
    "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.ManagedIdentity/"
    "userAssignedIdentities/myuami"
)
DPS_RESOURCE_ID = (
    "/subscriptions/sub-id/resourceGroups/rg/providers/"
    "Microsoft.Devices/provisioningServices/mydps"
)
ADU_RESOURCE_ID = (
    "/subscriptions/sub-id/resourceGroups/rg/providers/"
    "Microsoft.DeviceUpdate/linkedAccounts/myadu"
)


def _ns_with_dps(extra_messaging_endpoints=None):
    """Return a namespace dict that already has a linked DPS (DPS-first satisfied)."""
    messaging = {"endpoints": dict(extra_messaging_endpoints or {})}
    return {
        "name": "ns",
        "properties": {
            "messaging": messaging,
            "provisioning": {
                "endpoints": {
                    "primary": {
                        "endpointType": "Microsoft.Devices/provisioningServices",
                        "resourceId": DPS_RESOURCE_ID,
                    }
                }
            },
        },
    }


def _ns_without_dps():
    return {
        "name": "ns",
        "properties": {
            "messaging": {"endpoints": {}},
            "provisioning": {"endpoints": {}},
        },
    }


# ==================== Add ====================


def test_hub_add_rejects_when_no_dps_linked(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_dps()

    with pytest.raises(ArgumentUsageError, match="Link a DPS"):
        fixture_link_provider.hub_add(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
            hub_resource_id=HUB_RESOURCE_ID,
            mi_system_assigned=True,
        )

    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_hub_add_sami_writes_expected_patch_body(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.hub_add(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        hub_resource_id=HUB_RESOURCE_ID,
        mi_system_assigned=True,
        availability=MessagingEndpointAvailability.available.value,
        allocation_weight=1,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args[1]["properties"]
    endpoint = body["properties"]["messaging"]["endpoints"]["primary"]
    assert endpoint["endpointType"] == IOT_HUB_ENDPOINT_TYPE
    assert endpoint["resourceId"] == HUB_RESOURCE_ID
    assert endpoint["inboundCallerIdentity"] == {
        "type": IdentityType.system_assigned.value
    }
    assert endpoint["provisioning"] == {"availability": "Available", "allocationWeight": 1}


def test_hub_add_uami_writes_user_assigned_identity(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.hub_add(
        endpoint_name="secondary",
        namespace_name="ns",
        resource_group_name="rg",
        hub_resource_id=HUB_RESOURCE_ID,
        mi_user_assigned=UAMI_RESOURCE_ID,
    )

    endpoint = fixture_link_provider.client.namespaces.begin_update.call_args[1][
        "properties"
    ]["properties"]["messaging"]["endpoints"]["secondary"]
    assert endpoint["inboundCallerIdentity"] == {
        "type": IdentityType.user_assigned.value,
        "userAssignedIdentity": UAMI_RESOURCE_ID,
    }
    # No provisioning fields provided -> not emitted
    assert "provisioning" not in endpoint


def test_hub_add_mi_mutually_exclusive(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    with pytest.raises(ArgumentUsageError, match="mutually exclusive"):
        fixture_link_provider.hub_add(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
            hub_resource_id=HUB_RESOURCE_ID,
            mi_system_assigned=True,
            mi_user_assigned=UAMI_RESOURCE_ID,
        )


def test_hub_add_requires_inbound_identity(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    with pytest.raises(RequiredArgumentMissingError):
        fixture_link_provider.hub_add(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
            hub_resource_id=HUB_RESOURCE_ID,
        )


# ==================== Update ====================


def test_hub_update_resends_full_endpoint(fixture_link_provider, mock_poller):
    # An update must re-send the full endpoint (endpointType + resourceId), not a sparse delta,
    # or the backend rejects it with InvalidRequestContent. The existing inboundCallerIdentity is
    # preserved and only the requested change (availability) is overlaid.
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps(
        {
            "primary": {
                "endpointType": IOT_HUB_ENDPOINT_TYPE,
                "resourceId": HUB_RESOURCE_ID,
                "inboundCallerIdentity": {"type": "SystemAssigned"},
            }
        }
    )
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller({"name": "ns"})

    fixture_link_provider.hub_update(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        availability=MessagingEndpointAvailability.disabled.value,
    )

    endpoint_patch = fixture_link_provider.client.namespaces.begin_update.call_args[1][
        "properties"
    ]["properties"]["messaging"]["endpoints"]["primary"]
    assert endpoint_patch == {
        "endpointType": IOT_HUB_ENDPOINT_TYPE,
        "resourceId": HUB_RESOURCE_ID,
        "inboundCallerIdentity": {"type": "SystemAssigned"},
        "provisioning": {"availability": "Disabled"},
    }


def test_hub_update_missing_endpoint_raises(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    with pytest.raises(ResourceNotFoundError):
        fixture_link_provider.hub_update(
            endpoint_name="missing",
            namespace_name="ns",
            resource_group_name="rg",
            mi_system_assigned=True,
        )


def test_hub_update_requires_at_least_one_field(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps(
        {
            "primary": {
                "endpointType": IOT_HUB_ENDPOINT_TYPE,
                "resourceId": HUB_RESOURCE_ID,
                "inboundCallerIdentity": {"type": "SystemAssigned"},
            }
        }
    )
    with pytest.raises(RequiredArgumentMissingError):
        fixture_link_provider.hub_update(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
        )


# ==================== Remove (always rejected by design) ====================


def test_hub_remove_always_raises_even_when_endpoint_exists(fixture_link_provider):
    """Hub link entries cannot be removed directly — must delete underlying Hub or namespace."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps(
        {
            "primary": {
                "endpointType": IOT_HUB_ENDPOINT_TYPE,
                "resourceId": HUB_RESOURCE_ID,
                "inboundCallerIdentity": {"type": "SystemAssigned"},
            }
        }
    )

    with pytest.raises(ArgumentUsageError, match="not supported"):
        fixture_link_provider.hub_remove(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
        )

    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_hub_remove_raises_when_endpoint_missing(fixture_link_provider):
    """Even when the named endpoint does not exist, raise the same actionable error."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    with pytest.raises(ArgumentUsageError, match="not supported"):
        fixture_link_provider.hub_remove(
            endpoint_name="missing",
            namespace_name="ns",
            resource_group_name="rg",
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


# ==================== Show / List ====================


def test_hub_show_returns_endpoint(fixture_link_provider):
    endpoint = {
        "endpointType": IOT_HUB_ENDPOINT_TYPE,
        "resourceId": HUB_RESOURCE_ID,
        "inboundCallerIdentity": {"type": "SystemAssigned"},
    }
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps(
        {"primary": endpoint}
    )

    assert (
        fixture_link_provider.hub_show(
            endpoint_name="primary", namespace_name="ns", resource_group_name="rg"
        )
        == endpoint
    )


def test_hub_show_passes_through_new_readonly_fields(fixture_link_provider):
    """New 2026-11-01-preview read-only link fields must survive show() unchanged."""
    endpoint = {
        "endpointType": IOT_HUB_ENDPOINT_TYPE,
        "resourceId": HUB_RESOURCE_ID,
        "inboundCallerIdentity": {"type": "SystemAssigned"},
        # New read-only fields introduced in 2026-11-01-preview
        "linkingState": "Linked",
        "linkingError": None,
        "deviceAddress": "device-addr",
        "serviceAddress": "service-addr",
        "legacyDeviceAddress": "legacy-addr",
    }
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps(
        {"primary": endpoint}
    )

    result = fixture_link_provider.hub_show(
        endpoint_name="primary", namespace_name="ns", resource_group_name="rg"
    )

    for field in [
        "linkingState",
        "linkingError",
        "deviceAddress",
        "serviceAddress",
        "legacyDeviceAddress",
    ]:
        assert field in result
    assert result == endpoint


def test_hub_show_missing_raises(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    with pytest.raises(ResourceNotFoundError):
        fixture_link_provider.hub_show(
            endpoint_name="missing", namespace_name="ns", resource_group_name="rg"
        )


def test_hub_list_filters_non_hub_endpoints(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps(
        {
            "primary": {
                "endpointType": IOT_HUB_ENDPOINT_TYPE,
                "resourceId": HUB_RESOURCE_ID,
                "inboundCallerIdentity": {"type": "SystemAssigned"},
            },
            "other": {
                "endpointType": "Microsoft.SomethingElse/other",
                "resourceId": "/sub/foo",
            },
        }
    )

    result = fixture_link_provider.hub_list(namespace_name="ns", resource_group_name="rg")
    assert set(result.keys()) == {"primary"}


def test_hub_list_empty(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    assert fixture_link_provider.hub_list(namespace_name="ns", resource_group_name="rg") == {}


# ==================== DPS add (P3) ====================


def _ns_with_no_dps_or_hub():
    return {
        "name": "ns",
        "properties": {
            "messaging": {"endpoints": {}},
            "provisioning": {"endpoints": {}},
        },
    }


def _ns_with_only_dps(name="primary"):
    return {
        "name": "ns",
        "properties": {
            "messaging": {"endpoints": {}},
            "provisioning": {
                "endpoints": {
                    name: {
                        "endpointType": DPS_ENDPOINT_TYPE,
                        "resourceId": DPS_RESOURCE_ID,
                        "inboundCallerIdentity": {"type": "SystemAssigned"},
                    }
                }
            },
        },
    }


def test_dps_add_writes_expected_patch_body(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.dps_add(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        dps_resource_id=DPS_RESOURCE_ID,
        mi_system_assigned=True,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args[1]["properties"]
    endpoint = body["properties"]["provisioning"]["endpoints"]["primary"]
    assert endpoint["endpointType"] == DPS_ENDPOINT_TYPE
    assert endpoint["resourceId"] == DPS_RESOURCE_ID
    assert endpoint["inboundCallerIdentity"] == {
        "type": IdentityType.system_assigned.value
    }
    # DPS endpoints do not get availability / allocationWeight
    assert "provisioning" not in endpoint


def test_dps_add_rejects_when_dps_cap_exceeded(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_only_dps()
    with pytest.raises(ArgumentUsageError, match="already has a linked DPS"):
        fixture_link_provider.dps_add(
            endpoint_name="secondary",
            namespace_name="ns",
            resource_group_name="rg",
            dps_resource_id=DPS_RESOURCE_ID,
            mi_system_assigned=True,
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_dps_add_rejects_invalid_dps_resource_id(fixture_link_provider):
    with pytest.raises(InvalidArgumentValueError):
        fixture_link_provider.dps_add(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
            dps_resource_id="/not/a/real/dps/id",
            mi_system_assigned=True,
        )
    fixture_link_provider.client.namespaces.get.assert_not_called()


def test_dps_add_mi_mutually_exclusive(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    with pytest.raises(ArgumentUsageError, match="mutually exclusive"):
        fixture_link_provider.dps_add(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
            dps_resource_id=DPS_RESOURCE_ID,
            mi_system_assigned=True,
            mi_user_assigned=UAMI_RESOURCE_ID,
        )


# ==================== DPS update / remove / show / list ====================


def test_dps_update_resends_full_endpoint(fixture_link_provider, mock_poller):
    # An update must re-send the full endpoint (endpointType + resourceId), not a sparse delta,
    # or the backend rejects it with InvalidRequestContent. Only the inbound identity is changed.
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_only_dps("primary")
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller({"name": "ns"})

    fixture_link_provider.dps_update(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        mi_user_assigned=UAMI_RESOURCE_ID,
    )

    endpoint_patch = fixture_link_provider.client.namespaces.begin_update.call_args[1][
        "properties"
    ]["properties"]["provisioning"]["endpoints"]["primary"]
    assert endpoint_patch == {
        "endpointType": DPS_ENDPOINT_TYPE,
        "resourceId": DPS_RESOURCE_ID,
        "inboundCallerIdentity": {
            "type": IdentityType.user_assigned.value,
            "userAssignedIdentity": UAMI_RESOURCE_ID,
        },
    }


def test_dps_update_requires_an_identity_flag(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_only_dps("primary")
    with pytest.raises(RequiredArgumentMissingError):
        fixture_link_provider.dps_update(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
        )


def test_dps_update_missing_endpoint_raises(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    with pytest.raises(ResourceNotFoundError):
        fixture_link_provider.dps_update(
            endpoint_name="missing",
            namespace_name="ns",
            resource_group_name="rg",
            mi_system_assigned=True,
        )


def test_dps_remove_always_raises_even_when_endpoint_exists(fixture_link_provider):
    """DPS link entries cannot be removed directly — must delete underlying DPS or namespace."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_only_dps("primary")

    with pytest.raises(ArgumentUsageError, match="not supported"):
        fixture_link_provider.dps_remove(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
        )

    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_dps_remove_raises_when_endpoint_missing(fixture_link_provider):
    """Even when the named DPS endpoint does not exist, raise the same actionable error."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    with pytest.raises(ArgumentUsageError, match="not supported"):
        fixture_link_provider.dps_remove(
            endpoint_name="missing",
            namespace_name="ns",
            resource_group_name="rg",
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_dps_show_surfaces_brownfield_hubs(fixture_link_provider, monkeypatch):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_only_dps("primary")

    # Patch the factory call inside link.py so we don't touch the real DPS client.
    monkeypatch.setattr(
        "azext_iot.adr.providers.link.iot_service_provisioning_factory",
        lambda cli_ctx: type(
            "FakeFactory",
            (),
            {
                "iot_dps_resource": type(
                    "FakeRes",
                    (),
                    {
                        "get": staticmethod(
                            lambda resource_group_name, provisioning_service_name: {
                                "properties": {
                                    "iotHubs": [
                                        {"name": "existing-hub-1", "location": "eastus"},
                                        {"name": "existing-hub-2", "location": "westus"},
                                    ]
                                }
                            }
                        )
                    },
                )()
            },
        )(),
    )

    result = fixture_link_provider.dps_show(
        endpoint_name="primary", namespace_name="ns", resource_group_name="rg"
    )
    assert result["endpointType"] == DPS_ENDPOINT_TYPE
    assert result["resourceId"] == DPS_RESOURCE_ID
    assert result["brownfieldHubs"] == [
        {"name": "existing-hub-1", "location": "eastus"},
        {"name": "existing-hub-2", "location": "westus"},
    ]


def test_dps_show_brownfield_failure_is_non_fatal(fixture_link_provider, monkeypatch):
    """If the side-GET against the DPS RP throws, dps_show still returns the endpoint."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_only_dps("primary")

    def _boom(*_a, **_kw):
        raise RuntimeError("RBAC denied on DPS RP")

    monkeypatch.setattr(
        "azext_iot.adr.providers.link.iot_service_provisioning_factory", _boom
    )

    result = fixture_link_provider.dps_show(
        endpoint_name="primary", namespace_name="ns", resource_group_name="rg"
    )
    # Endpoint still returned; brownfieldHubs defaults to empty list.
    assert result["resourceId"] == DPS_RESOURCE_ID
    assert result["brownfieldHubs"] == []


def test_dps_show_missing_endpoint_raises(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    with pytest.raises(ResourceNotFoundError):
        fixture_link_provider.dps_show(
            endpoint_name="missing", namespace_name="ns", resource_group_name="rg"
        )


def test_dps_list_filters_non_dps_endpoints(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = {
        "name": "ns",
        "properties": {
            "messaging": {"endpoints": {}},
            "provisioning": {
                "endpoints": {
                    "primary": {
                        "endpointType": DPS_ENDPOINT_TYPE,
                        "resourceId": DPS_RESOURCE_ID,
                    },
                    "other": {
                        "endpointType": "Microsoft.SomethingElse/other",
                        "resourceId": "/sub/foo",
                    },
                }
            },
        },
    }

    result = fixture_link_provider.dps_list(namespace_name="ns", resource_group_name="rg")
    assert set(result.keys()) == {"primary"}


def test_dps_list_empty(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    assert fixture_link_provider.dps_list(namespace_name="ns", resource_group_name="rg") == {}


# ==================== link add bundled (P4) ====================


def test_link_add_emits_bundled_patch_body(fixture_link_provider, mock_poller):
    """Bundled add composes a single PATCH that writes both DPS + Hub endpoints."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller({"name": "ns"})

    fixture_link_provider.link_add(
        namespace_name="ns",
        resource_group_name="rg",
        hub_endpoint_name="primary-hub",
        hub_resource_id=HUB_RESOURCE_ID,
        dps_endpoint_name="primary-dps",
        dps_resource_id=DPS_RESOURCE_ID,
        hub_mi_system_assigned=True,
        dps_mi_system_assigned=True,
        hub_availability=MessagingEndpointAvailability.available.value,
        hub_allocation_weight=1,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args[1]["properties"]
    inner = body["properties"]

    # DPS-first ordering: provisioning key appears before messaging key.
    assert list(inner.keys()) == ["provisioning", "messaging"]

    dps_entry = inner["provisioning"]["endpoints"]["primary-dps"]
    assert dps_entry["endpointType"] == DPS_ENDPOINT_TYPE
    assert dps_entry["resourceId"] == DPS_RESOURCE_ID
    assert dps_entry["inboundCallerIdentity"] == {
        "type": IdentityType.system_assigned.value
    }

    hub_entry = inner["messaging"]["endpoints"]["primary-hub"]
    assert hub_entry["endpointType"] == IOT_HUB_ENDPOINT_TYPE
    assert hub_entry["resourceId"] == HUB_RESOURCE_ID
    assert hub_entry["provisioning"] == {"availability": "Available", "allocationWeight": 1}


def test_link_add_rejects_when_dps_cap_exceeded(fixture_link_provider):
    """Cannot bundle when the namespace already has a linked DPS."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_only_dps("existing-dps")
    with pytest.raises(ArgumentUsageError, match="already has a linked DPS"):
        fixture_link_provider.link_add(
            namespace_name="ns",
            resource_group_name="rg",
            hub_endpoint_name="primary-hub",
            hub_resource_id=HUB_RESOURCE_ID,
            dps_endpoint_name="primary-dps",
            dps_resource_id=DPS_RESOURCE_ID,
            hub_mi_system_assigned=True,
            dps_mi_system_assigned=True,
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_link_add_rejects_invalid_dps_resource_id(fixture_link_provider):
    with pytest.raises(InvalidArgumentValueError):
        fixture_link_provider.link_add(
            namespace_name="ns",
            resource_group_name="rg",
            hub_endpoint_name="primary-hub",
            hub_resource_id=HUB_RESOURCE_ID,
            dps_endpoint_name="primary-dps",
            dps_resource_id="/not/a/real/dps/id",
            hub_mi_system_assigned=True,
            dps_mi_system_assigned=True,
        )
    fixture_link_provider.client.namespaces.get.assert_not_called()


def test_link_add_hub_mi_mutually_exclusive(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    with pytest.raises(ArgumentUsageError, match="mutually exclusive"):
        fixture_link_provider.link_add(
            namespace_name="ns",
            resource_group_name="rg",
            hub_endpoint_name="primary-hub",
            hub_resource_id=HUB_RESOURCE_ID,
            dps_endpoint_name="primary-dps",
            dps_resource_id=DPS_RESOURCE_ID,
            hub_mi_system_assigned=True,
            hub_mi_user_assigned=UAMI_RESOURCE_ID,
            dps_mi_system_assigned=True,
        )


def test_link_add_dps_mi_required(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    with pytest.raises(RequiredArgumentMissingError):
        fixture_link_provider.link_add(
            namespace_name="ns",
            resource_group_name="rg",
            hub_endpoint_name="primary-hub",
            hub_resource_id=HUB_RESOURCE_ID,
            dps_endpoint_name="primary-dps",
            dps_resource_id=DPS_RESOURCE_ID,
            hub_mi_system_assigned=True,
            # no dps_mi_*
        )


# ==================== --no-wait short-circuit ====================


def test_hub_add_no_wait_returns_poller(fixture_link_provider, mock_poller):
    """no_wait=True should return the poller directly without invoking wait_for_terminal_state."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    poller = mock_poller({"name": "ns"})
    fixture_link_provider.client.namespaces.begin_update.return_value = poller

    result = fixture_link_provider.hub_add(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        hub_resource_id=HUB_RESOURCE_ID,
        mi_system_assigned=True,
        no_wait=True,
    )

    # When no_wait is set we get the poller object back, NOT poller.result().
    assert result is poller
    poller.result.assert_not_called()


def test_dps_add_no_wait_returns_poller(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_dps()
    poller = mock_poller({"name": "ns"})
    fixture_link_provider.client.namespaces.begin_update.return_value = poller

    result = fixture_link_provider.dps_add(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        dps_resource_id=DPS_RESOURCE_ID,
        mi_system_assigned=True,
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_link_add_no_wait_returns_poller(fixture_link_provider, mock_poller):
    """Bundled link add (hub + dps in one PATCH) should also honor no_wait."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_dps()
    poller = mock_poller({"name": "ns"})
    fixture_link_provider.client.namespaces.begin_update.return_value = poller

    result = fixture_link_provider.link_add(
        namespace_name="ns",
        resource_group_name="rg",
        hub_endpoint_name="primary-hub",
        hub_resource_id=HUB_RESOURCE_ID,
        dps_endpoint_name="primary-dps",
        dps_resource_id=DPS_RESOURCE_ID,
        hub_mi_system_assigned=True,
        dps_mi_system_assigned=True,
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


# ==================== Edge-case fills: UAMI variants & --no-wait coverage ====================


def test_dps_add_with_user_assigned_mi(fixture_link_provider, mock_poller):
    """UAMI variant of dps_add — emits userAssignedIdentity in inboundCallerIdentity."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.dps_add(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        dps_resource_id=DPS_RESOURCE_ID,
        mi_user_assigned=UAMI_RESOURCE_ID,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args[1]["properties"]
    endpoint = body["properties"]["provisioning"]["endpoints"]["primary"]
    assert endpoint["inboundCallerIdentity"] == {
        "type": IdentityType.user_assigned.value,
        "userAssignedIdentity": UAMI_RESOURCE_ID,
    }


def test_dps_update_with_system_assigned_mi(fixture_link_provider, mock_poller):
    """SAMI variant of dps_update — switching from UAMI back to SAMI clears the
    userAssignedIdentity sub-field by emitting only ``type``."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_only_dps("primary")
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.dps_update(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        mi_system_assigned=True,
    )

    endpoint_patch = fixture_link_provider.client.namespaces.begin_update.call_args[1][
        "properties"
    ]["properties"]["provisioning"]["endpoints"]["primary"]
    assert endpoint_patch == {
        "endpointType": DPS_ENDPOINT_TYPE,
        "resourceId": DPS_RESOURCE_ID,
        "inboundCallerIdentity": {"type": IdentityType.system_assigned.value},
    }


def test_link_add_with_user_assigned_mi_on_both_sides(fixture_link_provider, mock_poller):
    """Bundled link add with UAMI on both Hub and DPS sides."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_no_dps_or_hub()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.link_add(
        namespace_name="ns",
        resource_group_name="rg",
        hub_endpoint_name="primary-hub",
        hub_resource_id=HUB_RESOURCE_ID,
        dps_endpoint_name="primary-dps",
        dps_resource_id=DPS_RESOURCE_ID,
        hub_mi_user_assigned=UAMI_RESOURCE_ID,
        dps_mi_user_assigned=UAMI_RESOURCE_ID,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args[1]["properties"]
    dps_entry = body["properties"]["provisioning"]["endpoints"]["primary-dps"]
    hub_entry = body["properties"]["messaging"]["endpoints"]["primary-hub"]
    assert dps_entry["inboundCallerIdentity"] == {
        "type": IdentityType.user_assigned.value,
        "userAssignedIdentity": UAMI_RESOURCE_ID,
    }
    assert hub_entry["inboundCallerIdentity"] == {
        "type": IdentityType.user_assigned.value,
        "userAssignedIdentity": UAMI_RESOURCE_ID,
    }


def test_hub_add_with_only_availability_no_weight(fixture_link_provider, mock_poller):
    """Only ``availability`` set; ``allocationWeight`` must be omitted (not None)."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.hub_add(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        hub_resource_id=HUB_RESOURCE_ID,
        mi_system_assigned=True,
        availability=MessagingEndpointAvailability.available.value,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args[1]["properties"]
    endpoint = body["properties"]["messaging"]["endpoints"]["primary"]
    assert endpoint["provisioning"] == {"availability": "Available"}
    assert "allocationWeight" not in endpoint["provisioning"]


def test_hub_add_with_only_allocation_weight_no_availability(fixture_link_provider, mock_poller):
    """Only ``allocationWeight`` set; ``availability`` must be omitted."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.hub_add(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        hub_resource_id=HUB_RESOURCE_ID,
        mi_system_assigned=True,
        allocation_weight=7,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args[1]["properties"]
    endpoint = body["properties"]["messaging"]["endpoints"]["primary"]
    assert endpoint["provisioning"] == {"allocationWeight": 7}
    assert "availability" not in endpoint["provisioning"]


# ==================== ADU add / update / remove / show / list ====================


def _ns_with_adu(name="my-adu", identity=None):
    """Return a namespace dict with a linked ADU updating endpoint."""
    return {
        "name": "ns",
        "properties": {
            "updating": {
                "endpoints": {
                    name: {
                        "endpointType": ADU_ENDPOINT_TYPE,
                        "resourceId": ADU_RESOURCE_ID,
                        "inboundCallerIdentity": identity or {"type": "SystemAssigned"},
                    }
                }
            },
        },
    }


def _ns_without_adu():
    return {"name": "ns", "properties": {"updating": {"endpoints": {}}}}


def test_adu_add_sami_writes_expected_patch_body(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_adu()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.adu_add(
        endpoint_name="my-adu",
        namespace_name="ns",
        resource_group_name="rg",
        adu_resource_id=ADU_RESOURCE_ID,
        mi_system_assigned=True,
    )

    body = fixture_link_provider.client.namespaces.begin_update.call_args[1]["properties"]
    endpoint = body["properties"]["updating"]["endpoints"]["my-adu"]
    assert endpoint["endpointType"] == ADU_ENDPOINT_TYPE
    assert endpoint["resourceId"] == ADU_RESOURCE_ID
    assert endpoint["inboundCallerIdentity"] == {
        "type": IdentityType.system_assigned.value
    }


def test_adu_add_uami_writes_user_assigned_identity(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_adu()
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.adu_add(
        endpoint_name="my-adu",
        namespace_name="ns",
        resource_group_name="rg",
        adu_resource_id=ADU_RESOURCE_ID,
        mi_user_assigned=UAMI_RESOURCE_ID,
    )

    endpoint = fixture_link_provider.client.namespaces.begin_update.call_args[1][
        "properties"
    ]["properties"]["updating"]["endpoints"]["my-adu"]
    assert endpoint["inboundCallerIdentity"] == {
        "type": IdentityType.user_assigned.value,
        "userAssignedIdentity": UAMI_RESOURCE_ID,
    }


def test_adu_add_rejects_invalid_adu_resource_id(fixture_link_provider):
    with pytest.raises(InvalidArgumentValueError):
        fixture_link_provider.adu_add(
            endpoint_name="my-adu",
            namespace_name="ns",
            resource_group_name="rg",
            adu_resource_id="/not/a/real/adu/id",
            mi_system_assigned=True,
        )
    fixture_link_provider.client.namespaces.get.assert_not_called()


def test_adu_add_rejects_wrong_resource_type(fixture_link_provider):
    """A valid ARM id of the wrong RP/type is rejected."""
    with pytest.raises(InvalidArgumentValueError):
        fixture_link_provider.adu_add(
            endpoint_name="my-adu",
            namespace_name="ns",
            resource_group_name="rg",
            adu_resource_id=HUB_RESOURCE_ID,
            mi_system_assigned=True,
        )
    fixture_link_provider.client.namespaces.get.assert_not_called()


def test_adu_add_rejects_duplicate_endpoint_name(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_adu("my-adu")
    with pytest.raises(ArgumentUsageError, match="already exists"):
        fixture_link_provider.adu_add(
            endpoint_name="my-adu",
            namespace_name="ns",
            resource_group_name="rg",
            adu_resource_id=ADU_RESOURCE_ID,
            mi_system_assigned=True,
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_adu_add_mi_mutually_exclusive(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_adu()
    with pytest.raises(ArgumentUsageError, match="mutually exclusive"):
        fixture_link_provider.adu_add(
            endpoint_name="my-adu",
            namespace_name="ns",
            resource_group_name="rg",
            adu_resource_id=ADU_RESOURCE_ID,
            mi_system_assigned=True,
            mi_user_assigned=UAMI_RESOURCE_ID,
        )


def test_adu_add_requires_inbound_identity(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_adu()
    with pytest.raises(RequiredArgumentMissingError):
        fixture_link_provider.adu_add(
            endpoint_name="my-adu",
            namespace_name="ns",
            resource_group_name="rg",
            adu_resource_id=ADU_RESOURCE_ID,
        )


def test_adu_update_resends_full_endpoint(fixture_link_provider, mock_poller):
    # An update must re-send the full endpoint (endpointType + resourceId), not a sparse delta,
    # or the backend rejects it with InvalidRequestContent. Only the inbound identity is changed.
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_adu("my-adu")
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.adu_update(
        endpoint_name="my-adu",
        namespace_name="ns",
        resource_group_name="rg",
        mi_user_assigned=UAMI_RESOURCE_ID,
    )

    endpoint_patch = fixture_link_provider.client.namespaces.begin_update.call_args[1][
        "properties"
    ]["properties"]["updating"]["endpoints"]["my-adu"]
    assert endpoint_patch == {
        "endpointType": ADU_ENDPOINT_TYPE,
        "resourceId": ADU_RESOURCE_ID,
        "inboundCallerIdentity": {
            "type": IdentityType.user_assigned.value,
            "userAssignedIdentity": UAMI_RESOURCE_ID,
        },
    }


def test_adu_update_requires_an_identity_flag(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_adu("my-adu")
    with pytest.raises(RequiredArgumentMissingError):
        fixture_link_provider.adu_update(
            endpoint_name="my-adu",
            namespace_name="ns",
            resource_group_name="rg",
        )


def test_adu_update_missing_endpoint_raises(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_adu()
    with pytest.raises(ResourceNotFoundError):
        fixture_link_provider.adu_update(
            endpoint_name="missing",
            namespace_name="ns",
            resource_group_name="rg",
            mi_system_assigned=True,
        )


def test_adu_update_mi_mutually_exclusive(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_adu("my-adu")
    with pytest.raises(ArgumentUsageError, match="mutually exclusive"):
        fixture_link_provider.adu_update(
            endpoint_name="my-adu",
            namespace_name="ns",
            resource_group_name="rg",
            mi_system_assigned=True,
            mi_user_assigned=UAMI_RESOURCE_ID,
        )


def test_adu_remove_always_raises_even_when_endpoint_exists(fixture_link_provider):
    """ADU link entries cannot be removed directly — must delete underlying account or namespace."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_adu("my-adu")

    with pytest.raises(ArgumentUsageError, match="not supported"):
        fixture_link_provider.adu_remove(
            endpoint_name="my-adu",
            namespace_name="ns",
            resource_group_name="rg",
        )

    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_adu_remove_raises_when_endpoint_missing(fixture_link_provider):
    """Even when the named ADU endpoint does not exist, raise the same actionable error."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_adu()
    with pytest.raises(ArgumentUsageError, match="not supported"):
        fixture_link_provider.adu_remove(
            endpoint_name="missing",
            namespace_name="ns",
            resource_group_name="rg",
        )
    fixture_link_provider.client.namespaces.begin_update.assert_not_called()


def test_adu_show_returns_endpoint(fixture_link_provider):
    endpoint = {
        "endpointType": ADU_ENDPOINT_TYPE,
        "resourceId": ADU_RESOURCE_ID,
        "inboundCallerIdentity": {"type": "SystemAssigned"},
    }
    fixture_link_provider.client.namespaces.get.return_value = {
        "name": "ns",
        "properties": {"updating": {"endpoints": {"my-adu": endpoint}}},
    }

    assert (
        fixture_link_provider.adu_show(
            endpoint_name="my-adu", namespace_name="ns", resource_group_name="rg"
        )
        == endpoint
    )


def test_adu_show_missing_raises(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_adu()
    with pytest.raises(ResourceNotFoundError):
        fixture_link_provider.adu_show(
            endpoint_name="missing", namespace_name="ns", resource_group_name="rg"
        )


def test_adu_list_filters_non_adu_endpoints(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = {
        "name": "ns",
        "properties": {
            "updating": {
                "endpoints": {
                    "my-adu": {
                        "endpointType": ADU_ENDPOINT_TYPE,
                        "resourceId": ADU_RESOURCE_ID,
                    },
                    "other": {
                        "endpointType": "Microsoft.SomethingElse/other",
                        "resourceId": "/sub/foo",
                    },
                }
            }
        },
    }

    result = fixture_link_provider.adu_list(namespace_name="ns", resource_group_name="rg")
    assert set(result.keys()) == {"my-adu"}


def test_adu_list_empty(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_adu()
    assert fixture_link_provider.adu_list(namespace_name="ns", resource_group_name="rg") == {}


def test_adu_add_no_wait_returns_poller(fixture_link_provider, mock_poller):
    """no_wait=True should return the poller directly without invoking wait_for_terminal_state."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_without_adu()
    poller = mock_poller({"name": "ns"})
    fixture_link_provider.client.namespaces.begin_update.return_value = poller

    result = fixture_link_provider.adu_add(
        endpoint_name="my-adu",
        namespace_name="ns",
        resource_group_name="rg",
        adu_resource_id=ADU_RESOURCE_ID,
        mi_system_assigned=True,
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_adu_update_with_system_assigned_mi(fixture_link_provider, mock_poller):
    """SAMI variant of adu_update — emits only ``type`` in inboundCallerIdentity."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_adu(
        "my-adu",
        identity={
            "type": IdentityType.user_assigned.value,
            "userAssignedIdentity": UAMI_RESOURCE_ID,
        },
    )
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_link_provider.adu_update(
        endpoint_name="my-adu",
        namespace_name="ns",
        resource_group_name="rg",
        mi_system_assigned=True,
    )

    endpoint_patch = fixture_link_provider.client.namespaces.begin_update.call_args[1][
        "properties"
    ]["properties"]["updating"]["endpoints"]["my-adu"]
    assert endpoint_patch == {
        "endpointType": ADU_ENDPOINT_TYPE,
        "resourceId": ADU_RESOURCE_ID,
        "inboundCallerIdentity": {"type": IdentityType.system_assigned.value},
    }


# ==================== Resource-ID parsing + identity normalization edge cases ====================


from azext_iot.adr.providers.link import (  # noqa: E402
    _parse_dps_resource_id,
    _parse_adu_resource_id,
    _resolve_inbound_identity,
)


@pytest.mark.parametrize("value", ["", "   "])
def test_parse_dps_resource_id_rejects_empty(value):
    """An empty/whitespace DPS id is rejected with a required-value hint."""
    with pytest.raises(InvalidArgumentValueError, match="--dps-id is required"):
        _parse_dps_resource_id(value)


def test_parse_dps_resource_id_rejects_bare_name():
    """A bare DPS name (no slashes) gets a friendly 'pass the full ARM id' hint."""
    with pytest.raises(InvalidArgumentValueError, match="bare DPS name"):
        _parse_dps_resource_id("mydps")


def test_parse_dps_resource_id_rejects_wrong_type():
    """A valid ARM id of the wrong resource type is rejected as not-a-DPS."""
    with pytest.raises(InvalidArgumentValueError, match="provisioningServices"):
        _parse_dps_resource_id(HUB_RESOURCE_ID)


@pytest.mark.parametrize("value", ["", "   "])
def test_parse_adu_resource_id_rejects_empty(value):
    """An empty/whitespace ADU id is rejected with a required-value hint."""
    with pytest.raises(InvalidArgumentValueError, match="--adu-id is required"):
        _parse_adu_resource_id(value)


def test_parse_adu_resource_id_rejects_bare_name():
    """A bare ADU account name (no slashes) gets a friendly 'pass the full ARM id' hint."""
    with pytest.raises(InvalidArgumentValueError, match="bare ADU account name"):
        _parse_adu_resource_id("myadu")


def test_resolve_inbound_identity_whitespace_uami_is_unset():
    """A whitespace-only UAMI is normalized to None and yields no identity body."""
    assert _resolve_inbound_identity(False, "   ") is None


def test_hub_update_mi_mutually_exclusive(fixture_link_provider):
    """SAMI + UAMI together on hub update raises before any namespace fetch."""
    with pytest.raises(ArgumentUsageError, match="mutually exclusive"):
        fixture_link_provider.hub_update(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
            mi_system_assigned=True,
            mi_user_assigned=UAMI_RESOURCE_ID,
        )
    fixture_link_provider.client.namespaces.get.assert_not_called()


def test_hub_update_sets_identity_and_allocation_weight(fixture_link_provider, mock_poller):
    """Update applies a new inbound identity and allocationWeight in one patch."""
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_dps(
        {
            "primary": {
                "endpointType": IOT_HUB_ENDPOINT_TYPE,
                "resourceId": HUB_RESOURCE_ID,
                "inboundCallerIdentity": {"type": "SystemAssigned"},
            }
        }
    )
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller({"name": "ns"})

    fixture_link_provider.hub_update(
        endpoint_name="primary",
        namespace_name="ns",
        resource_group_name="rg",
        mi_system_assigned=True,
        allocation_weight=50,
    )

    endpoint_patch = fixture_link_provider.client.namespaces.begin_update.call_args[1][
        "properties"
    ]["properties"]["messaging"]["endpoints"]["primary"]
    assert endpoint_patch["inboundCallerIdentity"] == {"type": IdentityType.system_assigned.value}
    assert endpoint_patch["provisioning"]["allocationWeight"] == 50


def test_dps_update_mi_mutually_exclusive(fixture_link_provider):
    """SAMI + UAMI together on dps update raises before any namespace fetch."""
    with pytest.raises(ArgumentUsageError, match="mutually exclusive"):
        fixture_link_provider.dps_update(
            endpoint_name="primary",
            namespace_name="ns",
            resource_group_name="rg",
            mi_system_assigned=True,
            mi_user_assigned=UAMI_RESOURCE_ID,
        )
    fixture_link_provider.client.namespaces.get.assert_not_called()


def test_hub_remove_enrichment_failure_is_non_fatal(fixture_link_provider):
    """If the best-effort namespace fetch fails, hub_remove still raises the actionable error."""
    fixture_link_provider.client.namespaces.get.side_effect = RuntimeError("boom")
    with pytest.raises(ArgumentUsageError, match="not supported"):
        fixture_link_provider.hub_remove(
            endpoint_name="primary", namespace_name="ns", resource_group_name="rg",
        )


def test_dps_remove_enrichment_failure_is_non_fatal(fixture_link_provider):
    """If the best-effort namespace fetch fails, dps_remove still raises the actionable error."""
    fixture_link_provider.client.namespaces.get.side_effect = RuntimeError("boom")
    with pytest.raises(ArgumentUsageError, match="not supported"):
        fixture_link_provider.dps_remove(
            endpoint_name="primary", namespace_name="ns", resource_group_name="rg",
        )


def test_adu_remove_enrichment_failure_is_non_fatal(fixture_link_provider):
    """If the best-effort namespace fetch fails, adu_remove still raises the actionable error."""
    fixture_link_provider.client.namespaces.get.side_effect = RuntimeError("boom")
    with pytest.raises(ArgumentUsageError, match="not supported"):
        fixture_link_provider.adu_remove(
            endpoint_name="primary", namespace_name="ns", resource_group_name="rg",
        )
