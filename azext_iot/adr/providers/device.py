# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azure.cli.core.azclierror import (
    CLIInternalError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import shell_safe_json_parse


def _parse_json_object(value, argument_name: str):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = shell_safe_json_parse(value)
        except CLIInternalError as error:
            raise InvalidArgumentValueError(
                f"{argument_name} must be valid JSON."
            ) from error
    if not isinstance(value, dict):
        raise InvalidArgumentValueError(f"{argument_name} must be a JSON object.")
    return value


def _parse_endpoints(value):
    endpoints = _parse_json_object(value, "--endpoints")
    unsupported = set(endpoints) - {"inbound", "outbound"}
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise InvalidArgumentValueError(
            f"--endpoints only supports 'inbound' and 'outbound' properties; found: {names}."
        )
    return endpoints


class DeviceProvider(ADRProvider):
    def __init__(self, cmd):
        super(DeviceProvider, self).__init__(cmd)

    def create(
        self,
        device_name: str,
        namespace_name: str,
        resource_group_name: str,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        operating_system: Optional[str] = None,
        operating_system_version: Optional[str] = None,
        external_device_id: Optional[str] = None,
        enabled: Optional[bool] = None,
        attributes: Optional[str] = None,
        endpoints: Optional[str] = None,
        discovered_device_ref: Optional[str] = None,
        policy_resource_id: Optional[str] = None,
        **kwargs,
    ):
        """Create a device in the namespace."""
        location = self._resolve_location(namespace_name, resource_group_name, location)

        inner_props = {}
        if manufacturer is not None:
            inner_props["manufacturer"] = manufacturer
        if model is not None:
            inner_props["model"] = model
        if operating_system is not None:
            inner_props["operatingSystem"] = operating_system
        if operating_system_version is not None:
            inner_props["operatingSystemVersion"] = operating_system_version
        if external_device_id is not None:
            inner_props["externalDeviceId"] = external_device_id
        if enabled is not None:
            inner_props["enabled"] = enabled
        if attributes is not None:
            inner_props["attributes"] = _parse_json_object(attributes, "--attributes")
        if endpoints is not None:
            inner_props["endpoints"] = _parse_endpoints(endpoints)
        if discovered_device_ref is not None:
            inner_props["discoveredDeviceRef"] = discovered_device_ref
        if policy_resource_id is not None:
            inner_props["policy"] = {"resourceId": policy_resource_id}

        resource = {"location": location}
        if inner_props:
            resource["properties"] = inner_props
        if tags is not None:
            resource["tags"] = tags

        poller = self.client.namespace_devices.begin_create_or_replace(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=device_name,
            resource=resource,
        )
        return self._wait(
            poller, f"Creating device '{device_name}' in namespace {namespace_name}...", **kwargs
        )

    def delete(
        self,
        device_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        """Delete a device from the namespace."""
        poller = self.client.namespace_devices.begin_delete(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=device_name,
        )
        return self._wait(
            poller, f"Deleting device '{device_name}' from namespace {namespace_name}...", **kwargs
        )

    def show(self, device_name: str, namespace_name: str, resource_group_name: str):
        return self.client.namespace_devices.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=device_name,
        )

    def list(self, namespace_name: str, resource_group_name: str):
        return list(
            self.client.namespace_devices.list_by_resource_group(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
        )

    def update(
        self,
        device_name: str,
        namespace_name: str,
        resource_group_name: str,
        enabled: Optional[bool] = None,
        tags: Optional[Dict[str, str]] = None,
        operating_system_version: Optional[str] = None,
        attributes: Optional[str] = None,
        endpoints: Optional[str] = None,
        policy_resource_id: Optional[str] = None,
        **kwargs,
    ):
        """Update a device in the namespace."""
        inner_props = {}

        if enabled is not None:
            inner_props["enabled"] = enabled
        if operating_system_version is not None:
            inner_props["operatingSystemVersion"] = operating_system_version
        if attributes is not None:
            inner_props["attributes"] = _parse_json_object(attributes, "--attributes")
        if endpoints is not None:
            inner_props["endpoints"] = _parse_endpoints(endpoints)
        if policy_resource_id is not None:
            inner_props["policy"] = (
                None if policy_resource_id == "" else {"resourceId": policy_resource_id}
            )

        if not inner_props and tags is None:
            raise RequiredArgumentMissingError(
                "Nothing to update. Provide --enabled, --os-version, --attributes, "
                "--endpoints, --policy-resource-id, or --tags."
            )

        properties = {}
        if inner_props:
            properties["properties"] = inner_props
        if tags is not None:
            properties["tags"] = tags

        poller = self.client.namespace_devices.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            device_name=device_name,
            properties=properties,
        )
        return self._wait(
            poller, f"Updating device '{device_name}' in namespace {namespace_name}...", **kwargs
        )
