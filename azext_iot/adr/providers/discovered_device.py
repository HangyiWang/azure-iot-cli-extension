# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azext_iot.adr.providers._resource import (
    NamespaceTrackedResourceProvider,
    validate_discovery_properties,
)


class DiscoveredDeviceProvider(NamespaceTrackedResourceProvider):
    operation_group = "namespace_discovered_devices"
    name_argument = "discovered_device_name"
    resource_label = "discovered device"

    create_allowed_properties = frozenset(
        {
            "externalDeviceId",
            "endpoints",
            "manufacturer",
            "model",
            "operatingSystem",
            "operatingSystemVersion",
            "attributes",
            "discoveryId",
            "version",
        }
    )
    create_required_properties = frozenset({"discoveryId", "version"})
    update_allowed_properties = frozenset(
        {
            "externalDeviceId",
            "endpoints",
            "operatingSystemVersion",
            "attributes",
            "discoveryId",
            "version",
        }
    )

    def _validate_create_properties(self, properties):
        validate_discovery_properties(properties)

    def _validate_update_properties(self, properties):
        validate_discovery_properties(properties)
