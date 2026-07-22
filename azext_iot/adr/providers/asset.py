# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Any, Optional

from azure.cli.core.azclierror import RequiredArgumentMissingError

from azext_iot.adr.providers._resource import (
    NamespaceTrackedResourceProvider,
    parse_json_object,
    validate_device_ref,
)


class AssetProvider(NamespaceTrackedResourceProvider):
    operation_group = "namespace_assets"
    name_argument = "asset_name"
    resource_label = "asset"

    create_allowed_properties = frozenset(
        {
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
    )
    create_required_properties = frozenset({"deviceRef"})
    update_allowed_properties = create_allowed_properties - {
        "externalAssetId",
        "deviceRef",
        "discoveredAssetRefs",
    }

    def _validate_create_properties(self, properties):
        validate_device_ref(properties, require_all=True)

    def execute_action(
        self,
        resource_name: str,
        namespace_name: str,
        resource_group_name: str,
        management_action_name: str,
        management_group_name: str,
        payload: Optional[Any] = None,
        **kwargs,
    ):
        if not management_action_name or not management_action_name.strip():
            raise RequiredArgumentMissingError(
                "Provide a non-empty --action-name."
            )
        if not management_group_name or not management_group_name.strip():
            raise RequiredArgumentMissingError(
                "Provide a non-empty --management-group-name."
            )
        body = {
            "managementActionName": management_action_name,
            "managementGroupName": management_group_name,
        }
        if payload is not None:
            body["payload"] = parse_json_object(payload, "--payload")

        poller = self._operations.begin_execute_action(
            **self._resource_arguments(
                resource_name, namespace_name, resource_group_name
            ),
            body=body,
        )
        return self._wait(
            poller,
            f"Executing management action '{management_action_name}' on asset "
            f"'{resource_name}' in namespace {namespace_name}...",
            **kwargs,
        )
