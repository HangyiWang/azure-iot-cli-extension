# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import pytest

from azext_iot.sdk.deviceregistry.aio import operations as aio_operations
from azext_iot.sdk.deviceregistry import operations


@pytest.mark.parametrize(
    "operation_group",
    [
        operations.NamespaceAssetsOperations,
        operations.NamespaceDevicesOperations,
        operations.NamespaceDiscoveredAssetsOperations,
        operations.NamespaceDiscoveredDevicesOperations,
        aio_operations.NamespaceAssetsOperations,
        aio_operations.NamespaceDevicesOperations,
        aio_operations.NamespaceDiscoveredAssetsOperations,
        aio_operations.NamespaceDiscoveredDevicesOperations,
    ],
)
def test_namespace_child_lists_use_namespace_operation_name(operation_group):
    assert hasattr(operation_group, "list_by_namespace")
    assert not hasattr(operation_group, "list_by_resource_group")
