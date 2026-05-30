# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Integration tests for TLS 1.3 DPS linked hub features.

Tests cover:
- Linked hub create with hostname types (auto, classic, device)
- Hostname resolution for GWv2 hubs
- Linked hub list after creation
"""

import pytest
from azext_iot.common.embedded_cli import EmbeddedCLI

cli = EmbeddedCLI()


def _find_gwv2_hub(rg):
    """Find a GWv2 hub in the RG"""
    hubs = cli.invoke(f"iot hub list -g {rg}").as_json()
    for hub in hubs:
        if hub.get("properties", {}).get("deviceHostName"):
            return hub
    return None


def _cleanup_linked_hub(dps_name, rg, linked_hub_name):
    cli.invoke(
        f"iot dps linked-hub delete --dps-name {dps_name} -g {rg} "
        f"--linked-hub {linked_hub_name}"
    )


def test_linked_hub_create_auto_hostname(provisioned_iot_dps_no_hub_module):
    """On a GWv2 hub, auto (default) should resolve to the device hostname."""
    dps_name = provisioned_iot_dps_no_hub_module["name"]
    dps_rg = provisioned_iot_dps_no_hub_module["resourceGroup"]

    gwv2_hub = _find_gwv2_hub(dps_rg)
    if not gwv2_hub:
        pytest.skip("No GWv2 hub available in resource group for TLS 1.3 testing")

    hub_name = gwv2_hub["name"]
    device_hostname = gwv2_hub["properties"]["deviceHostName"]

    try:
        result = cli.invoke(
            f"iot dps linked-hub create --dps-name {dps_name} -g {dps_rg} "
            f"--hub-name {hub_name}"
        ).as_json()

        assert result, "Linked hub create should return a result"
        linked_hubs = result if isinstance(result, list) else [result]
        matching = [h for h in linked_hubs if h["name"] == device_hostname]
        assert len(matching) == 1, \
            f"Expected linked hub with name '{device_hostname}'. Got: {[h['name'] for h in linked_hubs]}"
        assert device_hostname in matching[0]["connectionString"], \
            "Connection string should use device hostname"
    finally:
        _cleanup_linked_hub(dps_name, dps_rg, device_hostname)


def test_linked_hub_create_classic_hostname(provisioned_iot_dps_no_hub_module):
    """Create linked hub with explicit classic hostname type."""
    dps_name = provisioned_iot_dps_no_hub_module["name"]
    dps_rg = provisioned_iot_dps_no_hub_module["resourceGroup"]

    gwv2_hub = _find_gwv2_hub(dps_rg)
    if not gwv2_hub:
        pytest.skip("No GWv2 hub available in resource group")

    hub_name = gwv2_hub["name"]
    classic_hostname = gwv2_hub["properties"]["hostName"]

    try:
        result = cli.invoke(
            f"iot dps linked-hub create --dps-name {dps_name} -g {dps_rg} "
            f"--hub-name {hub_name} --hostname-type classic"
        ).as_json()

        assert result, "Linked hub create should return a result"
        linked_hubs = result if isinstance(result, list) else [result]
        matching = [h for h in linked_hubs if h["name"] == classic_hostname]
        assert len(matching) == 1, \
            f"Expected linked hub with name '{classic_hostname}'. Got: {[h['name'] for h in linked_hubs]}"
        assert ".device." not in matching[0]["name"], \
            "Classic hostname should not contain .device. segment"
    finally:
        _cleanup_linked_hub(dps_name, dps_rg, classic_hostname)


def test_linked_hub_create_device_hostname(provisioned_iot_dps_no_hub_module):
    """Create linked hub with explicit device hostname type on a GWv2 hub."""
    dps_name = provisioned_iot_dps_no_hub_module["name"]
    dps_rg = provisioned_iot_dps_no_hub_module["resourceGroup"]

    gwv2_hub = _find_gwv2_hub(dps_rg)
    if not gwv2_hub:
        pytest.skip("No GWv2 hub available in resource group")

    hub_name = gwv2_hub["name"]
    device_hostname = gwv2_hub["properties"]["deviceHostName"]

    try:
        result = cli.invoke(
            f"iot dps linked-hub create --dps-name {dps_name} -g {dps_rg} "
            f"--hub-name {hub_name} --hostname-type device"
        ).as_json()

        assert result, "Linked hub create should return a result"
        linked_hubs = result if isinstance(result, list) else [result]
        matching = [h for h in linked_hubs if h["name"] == device_hostname]
        assert len(matching) == 1, \
            f"Expected linked hub with name '{device_hostname}'. Got: {[h['name'] for h in linked_hubs]}"
        assert ".device." in matching[0]["name"], \
            "Device hostname should contain .device. segment"
    finally:
        _cleanup_linked_hub(dps_name, dps_rg, device_hostname)


def test_hub_show_returns_tls13_hostnames(provisioned_iot_dps_no_hub_module):
    """Verify hub show returns TLS 1.3 hostname properties for GWv2 hubs."""
    dps_rg = provisioned_iot_dps_no_hub_module["resourceGroup"]

    gwv2_hub = _find_gwv2_hub(dps_rg)
    if not gwv2_hub:
        pytest.skip("No GWv2 hub available in resource group")

    hub_name = gwv2_hub["name"]
    result = cli.invoke(f"iot hub show -n {hub_name}").as_json()
    props = result["properties"]

    assert props.get("hostName"), "hostName (classic) should be present"
    assert props.get("deviceHostName"), "deviceHostName should be present for GWv2 hub"
    assert props.get("serviceHostName"), "serviceHostName should be present for GWv2 hub"

    assert ".device." in props["deviceHostName"]
    assert ".service." in props["serviceHostName"]
    assert hub_name in props["hostName"]
    assert hub_name in props["deviceHostName"]
    assert hub_name in props["serviceHostName"]


def test_linked_hub_list_shows_hostname(provisioned_iot_dps_no_hub_module):
    """Verify linked hub list returns the correct hostname after linking."""
    dps_name = provisioned_iot_dps_no_hub_module["name"]
    dps_rg = provisioned_iot_dps_no_hub_module["resourceGroup"]

    gwv2_hub = _find_gwv2_hub(dps_rg)
    if not gwv2_hub:
        pytest.skip("No GWv2 hub available in resource group")

    hub_name = gwv2_hub["name"]
    device_hostname = gwv2_hub["properties"]["deviceHostName"]

    try:
        cli.invoke(
            f"iot dps linked-hub create --dps-name {dps_name} -g {dps_rg} "
            f"--hub-name {hub_name}"
        )

        linked_hubs = cli.invoke(
            f"iot dps linked-hub list --dps-name {dps_name} -g {dps_rg}"
        ).as_json()

        matching = [h for h in linked_hubs if h["name"] == device_hostname]
        assert len(matching) == 1, \
            f"Should find linked hub with name '{device_hostname}'. Found: {[h['name'] for h in linked_hubs]}"
    finally:
        _cleanup_linked_hub(dps_name, dps_rg, device_hostname)


def test_linked_hub_update_combined_migration(provisioned_iot_dps_no_hub_module):
    """Migrate a hub link from KeyBased + classic endpoint to
    SystemAssigned + device endpoint in a single update call.
    """
    dps_name = provisioned_iot_dps_no_hub_module["name"]
    dps_rg = provisioned_iot_dps_no_hub_module["resourceGroup"]

    gwv2_hub = _find_gwv2_hub(dps_rg)
    if not gwv2_hub:
        pytest.skip("No GWv2 hub available in resource group")

    hub_name = gwv2_hub["name"]
    classic_hostname = gwv2_hub["properties"]["hostName"]
    device_hostname = gwv2_hub["properties"]["deviceHostName"]

    # Ensure DPS has SystemAssigned MI for the swap target
    cli.invoke(f"iot dps identity assign --name {dps_name} -g {dps_rg} --system-assigned")

    # Cleanup state for both possible end-state hostnames
    cleanup_targets = [classic_hostname, device_hostname]

    try:
        # Initial state: link with KeyBased + classic
        cli.invoke(
            f"iot dps linked-hub create --dps-name {dps_name} -g {dps_rg} "
            f"--hub-name {hub_name} --hostname-type classic"
        )
        initial = cli.invoke(
            f"iot dps linked-hub list --dps-name {dps_name} -g {dps_rg}"
        ).as_json()
        assert any(
            h["name"] == classic_hostname and h["authenticationType"] == "KeyBased"
            for h in initial
        ), f"Pre-condition failed; got: {[(h['name'], h['authenticationType']) for h in initial]}"

        # Combined update: classic -> device endpoint + KeyBased -> SystemAssigned
        cli.invoke(
            f"iot dps linked-hub update --dps-name {dps_name} -g {dps_rg} "
            f"--hub-name {hub_name} --hostname-type device "
            f"--authentication-type SystemAssigned"
        )

        after = cli.invoke(
            f"iot dps linked-hub list --dps-name {dps_name} -g {dps_rg}"
        ).as_json()
        matching = [h for h in after if h["name"] == device_hostname]
        assert len(matching) == 1, (
            f"Expected single entry at device hostname '{device_hostname}', "
            f"got: {[h['name'] for h in after]}"
        )
        assert matching[0]["authenticationType"] == "SystemAssigned"
        assert matching[0].get("connectionString", "") == ""
    finally:
        for hostname in cleanup_targets:
            _cleanup_linked_hub(dps_name, dps_rg, hostname)
