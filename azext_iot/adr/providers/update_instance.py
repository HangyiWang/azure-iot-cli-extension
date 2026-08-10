# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from azure.cli.core.azclierror import RequiredArgumentMissingError

from azext_iot._factory import adr_update_instance_service_factory
from azext_iot.adr.common import (
    SU_ENDPOINT_TYPE,
    build_managed_service_identity,
)
from azext_iot.adr.providers import base as provider_base
from azext_iot.adr.providers.base import ADRProvider


class UpdateInstanceProvider(ADRProvider):
    def __init__(self, cmd):
        self.cmd = cmd
        self.client = adr_update_instance_service_factory(cmd.cli_ctx)

    def _await_terminal(self, poller, **kwargs):
        return provider_base.wait_for_terminal_state(poller, **kwargs)

    def check_name(self, update_instance_name: str):
        return self.client.update_instances.check_name_availability(
            {"name": update_instance_name, "type": SU_ENDPOINT_TYPE}
        )

    def list(self, resource_group_name: Optional[str] = None):
        if resource_group_name:
            result = self.client.update_instances.list_by_resource_group(
                resource_group_name=resource_group_name
            )
        else:
            result = self.client.update_instances.list_by_subscription()
        return list(result)

    def show(self, update_instance_name: str, resource_group_name: str):
        return self.client.update_instances.get(
            resource_group_name=resource_group_name,
            update_instance_name=update_instance_name,
        )

    def create(
        self,
        update_instance_name: str,
        resource_group_name: str,
        location: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        mi_system_assigned: Optional[bool] = None,
        mi_user_assigned: Optional[List[str]] = None,
        **kwargs,
    ):
        resource = {
            "location": self._ensure_location(
                self.cmd.cli_ctx, resource_group_name, location
            ),
            "properties": {},
        }
        if tags is not None:
            resource["tags"] = tags
        identity = build_managed_service_identity(mi_system_assigned, mi_user_assigned)
        if identity is not None:
            resource["identity"] = identity

        poller = self.client.update_instances.begin_create(
            resource_group_name=resource_group_name,
            update_instance_name=update_instance_name,
            resource=resource,
        )
        return self._wait(
            poller,
            f"Creating Update Instance '{update_instance_name}'...",
            **kwargs,
        )

    def update(
        self,
        update_instance_name: str,
        resource_group_name: str,
        tags: Optional[Dict[str, str]] = None,
        mi_system_assigned: Optional[bool] = None,
        mi_user_assigned: Optional[List[str]] = None,
        **kwargs,
    ):
        properties = {}
        if tags is not None:
            properties["tags"] = tags
        identity = build_managed_service_identity(mi_system_assigned, mi_user_assigned)
        if identity is not None:
            properties["identity"] = identity
        if not properties:
            raise RequiredArgumentMissingError(
                "Nothing to update. Provide --tags, --mi-system-assigned, "
                "or --mi-user-assigned."
            )

        poller = self.client.update_instances.begin_update(
            resource_group_name=resource_group_name,
            update_instance_name=update_instance_name,
            properties=properties,
        )
        return self._wait(
            poller,
            f"Updating Update Instance '{update_instance_name}'...",
            **kwargs,
        )

    def delete(
        self,
        update_instance_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        poller = self.client.update_instances.begin_delete(
            resource_group_name=resource_group_name,
            update_instance_name=update_instance_name,
        )
        return self._wait(
            poller,
            f"Deleting Update Instance '{update_instance_name}'...",
            **kwargs,
        )
