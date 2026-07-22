# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, FrozenSet, Optional

from azure.cli.core.azclierror import (
    CLIInternalError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import process_json_arg


def parse_json_object(
    value: Any,
    argument_name: str,
    *,
    allowed_keys: Optional[FrozenSet[str]] = None,
    required_keys: FrozenSet[str] = frozenset(),
) -> Dict[str, Any]:
    """Parse an inline JSON object or JSON file and validate its top-level keys."""
    if isinstance(value, str):
        try:
            value = process_json_arg(value, argument_name)
        except CLIInternalError as error:
            raise InvalidArgumentValueError(
                f"{argument_name} must be a valid JSON object or a path to a JSON file."
            ) from error
    if not isinstance(value, dict):
        raise InvalidArgumentValueError(
            f"{argument_name} must be a JSON object or a path to a JSON file."
        )

    if allowed_keys is not None:
        unsupported = set(value) - allowed_keys
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise InvalidArgumentValueError(
                f"{argument_name} contains unsupported properties: {names}."
            )

    missing = sorted(
        key for key in required_keys if key not in value or value[key] is None
    )
    if missing:
        names = ", ".join(missing)
        raise RequiredArgumentMissingError(
            f"{argument_name} must contain the following properties: {names}."
        )
    return value


def parse_extended_location(value: Any) -> Dict[str, str]:
    extended_location = parse_json_object(
        value,
        "--extended-location",
        allowed_keys=frozenset({"name", "type"}),
        required_keys=frozenset({"name", "type"}),
    )
    for property_name in ("name", "type"):
        property_value = extended_location[property_name]
        if not isinstance(property_value, str) or not property_value.strip():
            raise InvalidArgumentValueError(
                f"--extended-location property '{property_name}' must be a "
                "non-empty string."
            )
    return extended_location


def validate_device_ref(properties: Dict[str, Any], *, require_all: bool) -> None:
    if "deviceRef" not in properties:
        return
    device_ref = properties["deviceRef"]
    if not isinstance(device_ref, dict):
        raise InvalidArgumentValueError(
            "--properties field 'deviceRef' must be a JSON object."
        )
    unsupported = set(device_ref) - {"deviceName", "endpointName"}
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise InvalidArgumentValueError(
            f"--properties field 'deviceRef' contains unsupported properties: {names}."
        )
    if not require_all and not device_ref:
        raise InvalidArgumentValueError(
            "--properties field 'deviceRef' must contain 'deviceName' or "
            "'endpointName'."
        )
    required = ("deviceName", "endpointName") if require_all else tuple(device_ref)
    for property_name in required:
        value = device_ref.get(property_name)
        if not isinstance(value, str) or not value.strip():
            raise InvalidArgumentValueError(
                f"--properties field 'deviceRef.{property_name}' must be a "
                "non-empty string."
            )


def validate_discovery_properties(properties: Dict[str, Any]) -> None:
    if "discoveryId" in properties:
        discovery_id = properties["discoveryId"]
        if not isinstance(discovery_id, str) or not discovery_id.strip():
            raise InvalidArgumentValueError(
                "--properties field 'discoveryId' must be a non-empty string."
            )
    if "version" in properties:
        version = properties["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise InvalidArgumentValueError(
                "--properties field 'version' must be a non-negative integer."
            )


class NamespaceTrackedResourceProvider(ADRProvider):
    """Shared CRUD behavior for JSON-heavy namespace child resources."""

    operation_group = ""
    name_argument = ""
    resource_label = ""
    create_allowed_properties: FrozenSet[str] = frozenset()
    create_required_properties: FrozenSet[str] = frozenset()
    update_allowed_properties: FrozenSet[str] = frozenset()

    @property
    def _operations(self):
        return getattr(self.client, self.operation_group)

    def _resource_arguments(
        self,
        resource_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> Dict[str, str]:
        return {
            "resource_group_name": resource_group_name,
            "namespace_name": namespace_name,
            self.name_argument: resource_name,
        }

    @staticmethod
    def _validate_create_properties(_properties: Dict[str, Any]) -> None:
        return None

    @staticmethod
    def _validate_update_properties(_properties: Dict[str, Any]) -> None:
        return None

    def create(
        self,
        resource_name: str,
        namespace_name: str,
        resource_group_name: str,
        properties: Any,
        extended_location: Any,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        parsed_properties = parse_json_object(
            properties,
            "--properties",
            allowed_keys=self.create_allowed_properties,
            required_keys=self.create_required_properties,
        )
        self._validate_create_properties(parsed_properties)
        resource = {
            "location": self._resolve_location(
                namespace_name, resource_group_name, location
            ),
            "extendedLocation": parse_extended_location(extended_location),
            "properties": parsed_properties,
        }
        if tags is not None:
            resource["tags"] = tags

        poller = self._operations.begin_create_or_replace(
            **self._resource_arguments(
                resource_name, namespace_name, resource_group_name
            ),
            resource=resource,
        )
        return self._wait(
            poller,
            f"Creating {self.resource_label} '{resource_name}' in namespace "
            f"{namespace_name}...",
            **kwargs,
        )

    def show(
        self,
        resource_name: str,
        namespace_name: str,
        resource_group_name: str,
    ):
        return self._operations.get(
            **self._resource_arguments(
                resource_name, namespace_name, resource_group_name
            )
        )

    def list(self, namespace_name: str, resource_group_name: str):
        return list(
            self._operations.list_by_resource_group(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
        )

    def update(
        self,
        resource_name: str,
        namespace_name: str,
        resource_group_name: str,
        properties: Any = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        body: Dict[str, Any] = {}
        if properties is not None:
            parsed_properties = parse_json_object(
                properties,
                "--properties",
                allowed_keys=self.update_allowed_properties,
            )
            self._validate_update_properties(parsed_properties)
            if parsed_properties:
                body["properties"] = parsed_properties
        if tags is not None:
            body["tags"] = tags
        if not body:
            raise RequiredArgumentMissingError(
                "Nothing to update. Provide --properties or --tags."
            )

        poller = self._operations.begin_update(
            **self._resource_arguments(
                resource_name, namespace_name, resource_group_name
            ),
            properties=body,
        )
        return self._wait(
            poller,
            f"Updating {self.resource_label} '{resource_name}' in namespace "
            f"{namespace_name}...",
            **kwargs,
        )

    def delete(
        self,
        resource_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        poller = self._operations.begin_delete(
            **self._resource_arguments(
                resource_name, namespace_name, resource_group_name
            )
        )
        return self._wait(
            poller,
            f"Deleting {self.resource_label} '{resource_name}' from namespace "
            f"{namespace_name}...",
            **kwargs,
        )
