# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import (
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)

from azext_iot.adr.providers.linking import (
    DEFAULT_DPS_ENDPOINT_TYPE,
    DEFAULT_HUB_ENDPOINT_TYPE,
    LINK_KIND_DPS,
    LINK_KIND_HUB,
)

HUB_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Devices/IotHubs/myhub"
)
DPS_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Devices/"
    "ProvisioningServices/mydps"
)
UAMI_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ManagedIdentity/"
    "userAssignedIdentities/myuami"
)


def _ns_with_messaging(endpoints):
    return {"properties": {"messaging": {"endpoints": endpoints}}}


def _ns_with_provisioning(endpoints):
    return {"properties": {"provisioning": {"endpoints": endpoints}}}


# ---------- show ----------

def test_link_hub_show(fixture_link_provider):
    body = {"resourceId": HUB_ID, "inboundCallerIdentity": {"type": "SystemAssigned"}}
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_messaging({"hub1": body})

    result = fixture_link_provider.show(
        kind=LINK_KIND_HUB, link_name="hub1", namespace_name="ns1", resource_group_name="rg1",
    )

    assert result == body


def test_link_dps_show_missing_raises(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_provisioning({})

    with pytest.raises(ResourceNotFoundError):
        fixture_link_provider.show(
            kind=LINK_KIND_DPS, link_name="dps1", namespace_name="ns1", resource_group_name="rg1",
        )


# ---------- list ----------

def test_link_hub_list_normalizes_dict(fixture_link_provider):
    body = {"resourceId": HUB_ID, "inboundCallerIdentity": {"type": "SystemAssigned"}}
    fixture_link_provider.client.namespaces.get.return_value = _ns_with_messaging(
        {"hub1": body, "hub2": body}
    )

    result = fixture_link_provider.list(
        kind=LINK_KIND_HUB, namespace_name="ns1", resource_group_name="rg1",
    )

    assert len(result) == 2
    names = sorted(entry["name"] for entry in result)
    assert names == ["hub1", "hub2"]
    for entry in result:
        assert entry["resourceId"] == HUB_ID


def test_link_dps_list_empty_when_section_missing(fixture_link_provider):
    fixture_link_provider.client.namespaces.get.return_value = {"properties": {}}

    result = fixture_link_provider.list(
        kind=LINK_KIND_DPS, namespace_name="ns1", resource_group_name="rg1",
    )

    assert result == []


# ---------- add (hub) ----------

def test_link_hub_add_system_assigned(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(Mock())

    fixture_link_provider.add(
        kind=LINK_KIND_HUB,
        link_name="hub1",
        namespace_name="ns1",
        resource_group_name="rg1",
        resource_id=HUB_ID,
        mi_system_assigned=True,
    )

    fixture_link_provider.client.namespaces.begin_update.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        properties={
            "properties": {
                "messaging": {
                    "endpoints": {
                        "hub1": {
                            "resourceId": HUB_ID,
                            "inboundCallerIdentity": {"type": "SystemAssigned"},
                            "endpointType": DEFAULT_HUB_ENDPOINT_TYPE,
                        }
                    }
                }
            }
        },
    )


def test_link_hub_add_user_assigned(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(Mock())

    fixture_link_provider.add(
        kind=LINK_KIND_HUB,
        link_name="hub1",
        namespace_name="ns1",
        resource_group_name="rg1",
        resource_id=HUB_ID,
        mi_user_assigned=UAMI_ID,
    )

    called = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs["properties"]
    identity = called["properties"]["messaging"]["endpoints"]["hub1"]["inboundCallerIdentity"]
    assert identity == {"type": "UserAssigned", "userAssignedIdentity": UAMI_ID}


# ---------- add (dps) ----------

def test_link_dps_add_system_assigned(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(Mock())

    fixture_link_provider.add(
        kind=LINK_KIND_DPS,
        link_name="dps1",
        namespace_name="ns1",
        resource_group_name="rg1",
        resource_id=DPS_ID,
        mi_system_assigned=True,
    )

    fixture_link_provider.client.namespaces.begin_update.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        properties={
            "properties": {
                "provisioning": {
                    "endpoints": {
                        "dps1": {
                            "resourceId": DPS_ID,
                            "inboundCallerIdentity": {"type": "SystemAssigned"},
                            "endpointType": DEFAULT_DPS_ENDPOINT_TYPE,
                        }
                    }
                }
            }
        },
    )


def test_link_add_requires_identity(fixture_link_provider):
    with pytest.raises(RequiredArgumentMissingError):
        fixture_link_provider.add(
            kind=LINK_KIND_HUB,
            link_name="hub1",
            namespace_name="ns1",
            resource_group_name="rg1",
            resource_id=HUB_ID,
        )


def test_link_add_rejects_both_identities(fixture_link_provider):
    with pytest.raises(MutuallyExclusiveArgumentError):
        fixture_link_provider.add(
            kind=LINK_KIND_HUB,
            link_name="hub1",
            namespace_name="ns1",
            resource_group_name="rg1",
            resource_id=HUB_ID,
            mi_system_assigned=True,
            mi_user_assigned=UAMI_ID,
        )


def test_link_add_custom_endpoint_type(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(Mock())

    fixture_link_provider.add(
        kind=LINK_KIND_HUB,
        link_name="hub1",
        namespace_name="ns1",
        resource_group_name="rg1",
        resource_id=HUB_ID,
        mi_system_assigned=True,
        endpoint_type="Microsoft.Custom/Thing",
    )

    called = fixture_link_provider.client.namespaces.begin_update.call_args.kwargs["properties"]
    assert called["properties"]["messaging"]["endpoints"]["hub1"]["endpointType"] == \
        "Microsoft.Custom/Thing"


# ---------- remove ----------

def test_link_hub_remove(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(Mock())

    fixture_link_provider.remove(
        kind=LINK_KIND_HUB,
        link_name="hub1",
        namespace_name="ns1",
        resource_group_name="rg1",
    )

    fixture_link_provider.client.namespaces.begin_update.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        properties={
            "properties": {
                "messaging": {
                    "endpoints": {"hub1": None}
                }
            }
        },
    )


def test_link_dps_remove(fixture_link_provider, mock_poller):
    fixture_link_provider.client.namespaces.begin_update.return_value = mock_poller(Mock())

    fixture_link_provider.remove(
        kind=LINK_KIND_DPS,
        link_name="dps1",
        namespace_name="ns1",
        resource_group_name="rg1",
    )

    fixture_link_provider.client.namespaces.begin_update.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        properties={
            "properties": {
                "provisioning": {
                    "endpoints": {"dps1": None}
                }
            }
        },
    )
