# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azext_iot.adr.providers._resource import (
    NamespaceTrackedResourceProvider,
    validate_device_ref,
    validate_discovery_properties,
)


class DiscoveredAssetProvider(NamespaceTrackedResourceProvider):
    operation_group = "namespace_discovered_assets"
    name_argument = "discovered_asset_name"
    resource_label = "discovered asset"

    create_allowed_properties = frozenset(
        {
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
    )
    create_required_properties = frozenset({"deviceRef", "discoveryId", "version"})
    update_allowed_properties = create_allowed_properties - {"externalAssetId"}

    def _validate_create_properties(self, properties):
        validate_device_ref(properties, require_all=True)
        validate_discovery_properties(properties)

    def _validate_update_properties(self, properties):
        validate_device_ref(properties, require_all=False)
        validate_discovery_properties(properties)
