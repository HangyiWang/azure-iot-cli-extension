# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azure.cli.core.azclierror import RequiredArgumentMissingError

from azext_iot.adr.providers.base import ADRProvider, console


class RegistryDeviceProvider(ADRProvider):
    def __init__(self, cmd):
        super(RegistryDeviceProvider, self).__init__(cmd)

    @staticmethod
    def _build_properties(
        external_device_id: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        software_revision: Optional[str] = None,
    ) -> dict:
        properties: dict = {}
        if external_device_id is not None:
            properties["externalDeviceId"] = external_device_id
        if manufacturer is not None:
            properties["manufacturer"] = manufacturer
        if model is not None:
            properties["model"] = model
        if hardware_revision is not None:
            properties["hardwareRevision"] = hardware_revision
        if software_revision is not None:
            properties["softwareRevision"] = software_revision
        return properties

    def create(
        self,
        registry_device_name: str,
        namespace_name: str,
        resource_group_name: str,
        external_device_id: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        software_revision: Optional[str] = None,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        location = self._resolve_location(namespace_name, resource_group_name, location)

        resource = {
            "location": location,
            "properties": self._build_properties(
                external_device_id=external_device_id,
                manufacturer=manufacturer,
                model=model,
                hardware_revision=hardware_revision,
                software_revision=software_revision,
            ),
        }
        if tags is not None:
            resource["tags"] = tags

        with console.status(
            f"Creating registry device '{registry_device_name}' on namespace {namespace_name}..."
        ):
            return self.client.registry_devices.create_or_replace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                registry_device_name=registry_device_name,
                resource=resource,
            )

    def show(self, registry_device_name: str, namespace_name: str, resource_group_name: str):
        return self.client.registry_devices.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            registry_device_name=registry_device_name,
        )

    def list(self, namespace_name: str, resource_group_name: str):
        return list(
            self.client.registry_devices.list_by_namespace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
        )

    def update(
        self,
        registry_device_name: str,
        namespace_name: str,
        resource_group_name: str,
        external_device_id: Optional[str] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        hardware_revision: Optional[str] = None,
        software_revision: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        properties = self._build_properties(
            external_device_id=external_device_id,
            manufacturer=manufacturer,
            model=model,
            hardware_revision=hardware_revision,
            software_revision=software_revision,
        )
        if not properties and tags is None:
            raise RequiredArgumentMissingError(
                "Nothing to update. Provide at least one of --external-device-id, --manufacturer, "
                "--model, --hardware-revision, --software-revision, or --tags."
            )

        body: dict = {"properties": properties}
        if tags is not None:
            body["tags"] = tags

        with console.status(
            f"Updating registry device '{registry_device_name}' on namespace {namespace_name}..."
        ):
            return self.client.registry_devices.update(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                registry_device_name=registry_device_name,
                properties=body,
            )

    def delete(self, registry_device_name: str, namespace_name: str, resource_group_name: str, **kwargs):
        poller = self.client.registry_devices.begin_delete(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            registry_device_name=registry_device_name,
        )
        return self._wait(
            poller,
            f"Deleting registry device '{registry_device_name}' from namespace {namespace_name}...",
            **kwargs,
        )
