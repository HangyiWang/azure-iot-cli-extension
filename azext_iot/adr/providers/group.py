# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, Optional

from azure.cli.core.azclierror import (
    AzureResponseError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)

from azext_iot.adr.common import GroupType
from azext_iot.adr.providers.base import ADRProvider


class GroupProvider(ADRProvider):
    def create(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
        query_string: str,
        group_type: str = GroupType.device.value,
        location: Optional[str] = None,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        mi_system_assigned: Optional[bool] = None,
        **kwargs,
    ):
        location = self._resolve_location(namespace_name, resource_group_name, location)
        properties = {"groupType": group_type, "query": query_string}
        if display_name is not None:
            properties["displayName"] = display_name
        if description is not None:
            properties["description"] = description

        resource = {"location": location, "properties": properties}
        if tags is not None:
            resource["tags"] = tags
        if mi_system_assigned:
            resource["identity"] = {"type": "SystemAssigned"}

        poller = self.client.groups.begin_create_or_replace(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
            resource=resource,
        )
        return self._wait(
            poller,
            f"Creating group '{group_name}' in namespace {namespace_name}...",
            **kwargs,
        )

    def update(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        mi_system_assigned: Optional[bool] = None,
        **kwargs,
    ):
        inner_properties = {}
        if display_name is not None:
            inner_properties["displayName"] = display_name
        if description is not None:
            inner_properties["description"] = description
        if not inner_properties and tags is None and mi_system_assigned is None:
            raise RequiredArgumentMissingError(
                "Nothing to update. Provide --display-name, --description, --tags, "
                "or --mi-system-assigned."
            )

        body = {}
        if inner_properties:
            body["properties"] = inner_properties
        if tags is not None:
            body["tags"] = tags
        if mi_system_assigned is not None:
            body["identity"] = {
                "type": "SystemAssigned" if mi_system_assigned else "None"
            }

        poller = self.client.groups.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
            properties=body,
        )
        return self._wait(
            poller,
            f"Updating group '{group_name}' in namespace {namespace_name}...",
            **kwargs,
        )

    def show(self, group_name: str, namespace_name: str, resource_group_name: str):
        return self.client.groups.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
        )

    def list(self, namespace_name: str, resource_group_name: str):
        return list(
            self.client.groups.list_by_namespace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
        )

    def delete(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        poller = self.client.groups.begin_delete(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
        )
        return self._wait(
            poller,
            f"Deleting group '{group_name}' from namespace {namespace_name}...",
            **kwargs,
        )

    def refresh(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        poller = self.client.groups.begin_refresh_members(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
        )
        return self._wait(
            poller,
            f"Refreshing members of group '{group_name}' in namespace {namespace_name}...",
            **kwargs,
        )

    def list_members(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
        page_size: Optional[int] = None,
        skip_token: Optional[str] = None,
    ) -> list:
        if page_size is not None and not 1 <= page_size <= 1000:
            raise InvalidArgumentValueError("--page-size must be between 1 and 1000.")

        body = {}
        if page_size is not None:
            body["pageSize"] = page_size
        if skip_token:
            body["skipToken"] = skip_token

        members = []
        seen_tokens = set()
        while True:
            response = self.client.groups.list_members(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                group_name=group_name,
                body=body,
            )
            members.extend((response or {}).get("members") or [])
            next_token = (response or {}).get("skipToken")
            if not next_token:
                return members
            if next_token in seen_tokens:
                raise AzureResponseError(
                    "The group member list returned a repeated skip token."
                )
            seen_tokens.add(next_token)
            body["skipToken"] = next_token

    def count(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> int:
        response = self.client.groups.count_members(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
        )
        return (response or {}).get("count") or 0
