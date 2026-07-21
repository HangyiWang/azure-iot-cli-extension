# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from importlib.util import find_spec
from unittest.mock import Mock

from azext_iot.sdk.deviceregistry import (
    MicrosoftDeviceRegistryManagementService,
    operations,
)
from azext_iot.sdk.deviceregistry._configuration import (
    MicrosoftDeviceRegistryManagementServiceConfiguration,
)


def test_generated_sdk_defaults_to_2026_11_02_preview():
    configuration = MicrosoftDeviceRegistryManagementServiceConfiguration(
        credential=Mock(), subscription_id="00000000-0000-0000-0000-000000000000"
    )
    assert configuration.api_version == "2026-11-02-preview"


def test_generated_sdk_has_required_2026_operation_groups_and_methods():
    client = MicrosoftDeviceRegistryManagementService(
        credential=Mock(),
        subscription_id="00000000-0000-0000-0000-000000000000",
    )
    required = {
        "namespaces": {
            "list_by_subscription",
            "list_by_resource_group",
            "get",
            "begin_create_or_replace",
            "begin_update",
            "begin_delete",
            "begin_generate_report",
            "get_latest_report",
            "begin_migrate",
        },
        "certificate_authorities": {
            "list_by_namespace",
            "get",
            "begin_create_or_replace",
            "begin_update",
            "begin_delete",
            "begin_activate",
            "begin_revoke",
        },
        "certificate_policies": {
            "list_by_certificate_authority",
            "get",
            "begin_create_or_update",
            "begin_update",
            "begin_delete",
        },
        "credentials": {
            "list_by_namespace",
            "get",
            "begin_create_or_update",
            "begin_update",
            "begin_delete",
            "begin_synchronize",
        },
        "policies": {
            "list_by_credential",
            "get",
            "begin_create_or_update",
            "begin_update",
            "begin_delete",
            "begin_activate_bring_your_own_root",
            "begin_revoke_issuer",
        },
        "namespace_devices": {
            "list_by_resource_group",
            "get",
            "begin_create_or_replace",
            "begin_update",
            "begin_delete",
        },
        "groups": {
            "list_by_namespace",
            "get",
            "begin_create_or_replace",
            "begin_update",
            "begin_delete",
            "list_members",
            "count_members",
            "begin_refresh_members",
        },
        "job_runs": {
            "list_by_namespace",
            "list_by_job",
            "get",
            "list_results",
            "begin_cancel",
        },
        "jobs": {
            "list_by_namespace",
            "get",
            "begin_create_or_replace",
            "update",
            "begin_delete",
            "begin_schedule",
        },
    }

    try:
        for group_name, methods in required.items():
            group = getattr(client, group_name)
            assert methods <= set(dir(group)), group_name
        assert not hasattr(client.namespace_devices, "begin_revoke")
        assert not hasattr(client, "registry_devices")
    finally:
        client.close()


def test_registry_device_operations_class_is_absent():
    assert "RegistryDevicesOperations" not in operations.__all__
    assert not hasattr(operations, "RegistryDevicesOperations")
    assert find_spec("azext_iot.adr.providers.registry_device") is None
    assert find_spec("azext_iot.adr.commands_registry_device") is None
