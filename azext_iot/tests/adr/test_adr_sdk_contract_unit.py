# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import inspect
from unittest.mock import Mock

from azext_iot.sdk.deviceregistry import (
    MicrosoftDeviceRegistryManagementService,
)
from azext_iot.sdk.deviceregistry._configuration import (
    MicrosoftDeviceRegistryManagementServiceConfiguration,
)
from azext_iot.sdk.deviceregistry.aio import (
    MicrosoftDeviceRegistryManagementService as AsyncMicrosoftDeviceRegistryManagementService,
)
from azext_iot.sdk.deviceregistry.aio._configuration import (
    MicrosoftDeviceRegistryManagementServiceConfiguration as AsyncConfiguration,
)
from azext_iot.sdk.deviceregistry.aio.operations import (
    _operations as async_operations,
)
from azext_iot.sdk.deviceregistry.operations import _operations as sync_operations


EXPECTED_OPERATION_COUNTS = {
    "Operations": 1,
    "AssetEndpointProfilesOperations": 6,
    "AssetsOperations": 6,
    "BillingContainersOperations": 2,
    "AsyncOperationStatusOperations": 1,
    "OperationStatusOperations": 1,
    "NamespacesOperations": 9,
    "SchemaRegistriesOperations": 6,
    "NamespaceAssetsOperations": 6,
    "CertificateAuthoritiesOperations": 7,
    "CertificatePoliciesOperations": 5,
    "CredentialsOperations": 6,
    "PoliciesOperations": 7,
    "NamespaceDevicesOperations": 5,
    "NamespaceDiscoveredAssetsOperations": 5,
    "NamespaceDiscoveredDevicesOperations": 5,
    "GroupsOperations": 8,
    "JobRunsOperations": 5,
    "JobsOperations": 6,
    "RegistryDevicesOperations": 5,
    "RegistryDeviceAttributesOperations": 2,
    "RegistryDeviceAuthenticationProfilesOperations": 4,
    "RegistryDeviceCapabilitiesOperations": 2,
    "SchemasOperations": 4,
    "SchemaVersionsOperations": 4,
}

PROVIDER_METHODS = {
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
    "namespace_devices": {
        "list_by_resource_group",
        "get",
        "begin_create_or_replace",
        "begin_update",
        "begin_delete",
    },
    "namespace_assets": {
        "list_by_resource_group",
        "get",
        "begin_create_or_replace",
        "begin_update",
        "begin_delete",
        "begin_execute_action",
    },
    "namespace_discovered_devices": {
        "list_by_resource_group",
        "get",
        "begin_create_or_replace",
        "begin_update",
        "begin_delete",
    },
    "namespace_discovered_assets": {
        "list_by_resource_group",
        "get",
        "begin_create_or_replace",
        "begin_update",
        "begin_delete",
    },
    "registry_devices": {
        "list_by_namespace",
        "get",
        "begin_create_or_replace",
        "begin_update",
        "begin_delete",
    },
    "registry_device_authentication_profiles": {
        "list_by_device",
        "get",
        "get_keys",
        "begin_revoke_certificates",
    },
    "registry_device_attributes": {"list_by_device", "get"},
    "registry_device_capabilities": {"list_by_device", "get"},
}


def _operation_inventory(module):
    inventory = {}
    for name, operation_class in inspect.getmembers(module, inspect.isclass):
        if not name.endswith("Operations") or operation_class.__module__ != module.__name__:
            continue
        inventory[name] = len(
            {
                method_name
                for method_name, method in inspect.getmembers(
                    operation_class, inspect.isfunction
                )
                if not method_name.startswith("_")
            }
        )
    return inventory


def test_full_sync_and_async_operation_inventory():
    assert _operation_inventory(sync_operations) == EXPECTED_OPERATION_COUNTS
    assert _operation_inventory(async_operations) == EXPECTED_OPERATION_COUNTS
    assert sum(EXPECTED_OPERATION_COUNTS.values()) == 118


def test_generated_clients_default_to_2026_11_02_preview():
    assert (
        MicrosoftDeviceRegistryManagementServiceConfiguration(
            Mock(), "00000000-0000-0000-0000-000000000000"
        ).api_version
        == "2026-11-02-preview"
    )
    assert (
        AsyncConfiguration(
            Mock(), "00000000-0000-0000-0000-000000000000"
        ).api_version
        == "2026-11-02-preview"
    )


def test_every_handwritten_provider_operation_exists():
    client = MicrosoftDeviceRegistryManagementService(
        Mock(), "00000000-0000-0000-0000-000000000000"
    )
    for operation_group, methods in PROVIDER_METHODS.items():
        group = getattr(client, operation_group)
        assert methods <= set(dir(group))

    async_client = AsyncMicrosoftDeviceRegistryManagementService(
        Mock(), "00000000-0000-0000-0000-000000000000"
    )
    for operation_group, methods in PROVIDER_METHODS.items():
        group = getattr(async_client, operation_group)
        assert methods <= set(dir(group))

    assert not hasattr(client, "adaptive_devices")
    assert not hasattr(async_client, "adaptive_devices")
