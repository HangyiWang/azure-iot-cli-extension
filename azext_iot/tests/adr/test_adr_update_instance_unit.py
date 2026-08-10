# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock, patch

import pytest
from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from azext_iot import _factory
from azext_iot.adr.common import build_managed_service_identity
from azext_iot.adr.providers.update_instance import UpdateInstanceProvider

RG = "test-rg"
INSTANCE = "test-update-instance"
UAMI_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/"
    "Microsoft.ManagedIdentity/userAssignedIdentities/identity"
)


@pytest.fixture()
def update_instance_provider():
    with patch(
        "azext_iot.adr.providers.update_instance."
        "adr_update_instance_service_factory"
    ) as factory:
        client = Mock()
        factory.return_value = client
        provider = UpdateInstanceProvider(Mock(cli_ctx=Mock()))
        yield provider


@pytest.mark.parametrize(
    "system_assigned, user_assigned, expected",
    [
        (None, None, None),
        (False, None, {"type": "None"}),
        (True, None, {"type": "SystemAssigned"}),
        (
            None,
            [UAMI_ID],
            {
                "type": "UserAssigned",
                "userAssignedIdentities": {UAMI_ID: {}},
            },
        ),
        (
            True,
            [UAMI_ID, UAMI_ID.upper()],
            {
                "type": "SystemAssigned,UserAssigned",
                "userAssignedIdentities": {UAMI_ID: {}},
            },
        ),
    ],
)
def test_build_managed_service_identity(system_assigned, user_assigned, expected):
    assert build_managed_service_identity(system_assigned, user_assigned) == expected


@pytest.mark.parametrize(
    "resource_id",
    [
        "not-an-id",
        "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/a",
        f"{UAMI_ID}/children/child",
    ],
)
def test_build_managed_service_identity_rejects_invalid_uami(resource_id):
    with pytest.raises(InvalidArgumentValueError):
        build_managed_service_identity(None, [resource_id])


def test_check_name_uses_update_instance_resource_type(update_instance_provider):
    expected = {"nameAvailable": True}
    operation = update_instance_provider.client.update_instances.check_name_availability
    operation.return_value = expected

    assert update_instance_provider.check_name(INSTANCE) == expected
    operation.assert_called_once_with(
        {
            "name": INSTANCE,
            "type": "Microsoft.DeviceUpdate/updateInstances",
        }
    )


def test_list_selects_subscription_or_resource_group_operation(
    update_instance_provider,
):
    operations = update_instance_provider.client.update_instances
    operations.list_by_subscription.return_value = [{"name": "subscription"}]
    operations.list_by_resource_group.return_value = [{"name": "group"}]

    assert update_instance_provider.list() == [{"name": "subscription"}]
    assert update_instance_provider.list(RG) == [{"name": "group"}]
    operations.list_by_subscription.assert_called_once_with()
    operations.list_by_resource_group.assert_called_once_with(resource_group_name=RG)


def test_show_calls_generated_sdk(update_instance_provider):
    expected = {"name": INSTANCE}
    update_instance_provider.client.update_instances.get.return_value = expected

    assert update_instance_provider.show(INSTANCE, RG) == expected
    update_instance_provider.client.update_instances.get.assert_called_once_with(
        resource_group_name=RG,
        update_instance_name=INSTANCE,
    )


def test_wait_uses_standard_arm_poller(update_instance_provider):
    poller = Mock()
    with patch(
        "azext_iot.adr.providers.update_instance."
        "provider_base.wait_for_terminal_state",
        return_value={"name": INSTANCE},
    ) as wait:
        assert update_instance_provider._await_terminal(poller, wait_sec=0) == {
            "name": INSTANCE
        }

    wait.assert_called_once_with(poller, wait_sec=0)


def test_create_builds_complete_resource_and_waits(update_instance_provider):
    expected = {"name": INSTANCE}
    poller = Mock()
    poller.result.return_value = expected
    operations = update_instance_provider.client.update_instances
    operations.begin_create.return_value = poller

    result = update_instance_provider.create(
        update_instance_name=INSTANCE,
        resource_group_name=RG,
        location="eastus2",
        tags={"env": "test"},
        mi_system_assigned=True,
        mi_user_assigned=[UAMI_ID],
    )

    assert result == expected
    operations.begin_create.assert_called_once_with(
        resource_group_name=RG,
        update_instance_name=INSTANCE,
        resource={
            "location": "eastus2",
            "properties": {},
            "tags": {"env": "test"},
            "identity": {
                "type": "SystemAssigned,UserAssigned",
                "userAssignedIdentities": {UAMI_ID: {}},
            },
        },
    )
    poller.result.assert_called_once_with()


def test_create_resolves_location_and_supports_no_wait(
    update_instance_provider,
):
    poller = Mock()
    operations = update_instance_provider.client.update_instances
    operations.begin_create.return_value = poller
    update_instance_provider._ensure_location = Mock(return_value="westus2")

    result = update_instance_provider.create(
        update_instance_name=INSTANCE,
        resource_group_name=RG,
        no_wait=True,
    )

    assert result is poller
    update_instance_provider._ensure_location.assert_called_once_with(
        update_instance_provider.cmd.cli_ctx, RG, None
    )
    assert operations.begin_create.call_args.kwargs["resource"] == {
        "location": "westus2",
        "properties": {},
    }
    poller.result.assert_not_called()


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"tags": {}}, {"tags": {}}),
        (
            {"mi_system_assigned": False},
            {"identity": {"type": "None"}},
        ),
        (
            {"mi_user_assigned": [UAMI_ID]},
            {
                "identity": {
                    "type": "UserAssigned",
                    "userAssignedIdentities": {UAMI_ID: {}},
                }
            },
        ),
    ],
)
def test_update_builds_patch_and_waits(update_instance_provider, kwargs, expected):
    poller = Mock()
    poller.result.return_value = {"name": INSTANCE}
    operations = update_instance_provider.client.update_instances
    operations.begin_update.return_value = poller

    assert update_instance_provider.update(INSTANCE, RG, **kwargs) == {"name": INSTANCE}
    operations.begin_update.assert_called_once_with(
        resource_group_name=RG,
        update_instance_name=INSTANCE,
        properties=expected,
    )


def test_update_rejects_empty_patch(update_instance_provider):
    with pytest.raises(RequiredArgumentMissingError, match="Nothing to update"):
        update_instance_provider.update(INSTANCE, RG)
    update_instance_provider.client.update_instances.begin_update.assert_not_called()


def test_update_supports_no_wait(update_instance_provider):
    poller = Mock()
    update_instance_provider.client.update_instances.begin_update.return_value = poller

    result = update_instance_provider.update(
        INSTANCE, RG, tags={"env": "test"}, no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()


def test_delete_waits_and_supports_no_wait(update_instance_provider):
    first_poller = Mock()
    first_poller.result.return_value = None
    second_poller = Mock()
    operation = update_instance_provider.client.update_instances.begin_delete
    operation.side_effect = [first_poller, second_poller]

    assert update_instance_provider.delete(INSTANCE, RG) is None
    assert update_instance_provider.delete(INSTANCE, RG, no_wait=True) is second_poller
    assert operation.call_count == 2
    first_poller.result.assert_called_once_with()
    second_poller.result.assert_not_called()


def test_update_instance_factory_uses_generated_sdk_and_canary_arm_endpoint():
    cli_ctx = Mock()
    client_path = (
        "azext_iot.sdk.deviceupdate.duregistry."
        "DeviceRegistryLinkedDeviceUpdatingServiceUnderMicrosoftDeviceUpdate"
    )
    with patch(
        "azure.cli.core.commands.client_factory.get_subscription_id",
        return_value="subscription",
    ), patch(
        "azext_iot._factory._get_credential_scopes",
        return_value=["scope"],
    ), patch(
        client_path
    ) as client_type:
        assert (
            _factory.adr_update_instance_service_factory(cli_ctx)
            is client_type.return_value
        )

    assert client_type.call_args.kwargs["subscription_id"] == "subscription"
    assert (
        client_type.call_args.kwargs["endpoint"]
        == "https://centraluseuap.management.azure.com"
    )
    assert client_type.call_args.kwargs["credential_scopes"] == ["scope"]
