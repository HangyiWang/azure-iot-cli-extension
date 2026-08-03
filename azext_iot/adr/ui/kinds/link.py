# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Endpoint links.

The CLI splits these across `link hub`, `link dps` and `link su`, but they are three
sections of one namespace and are read together far more often than separately. They are
presented as a single table with a TYPE column, which is also what makes the ordering rule
(a provisioning endpoint must exist before a hub) visible at a glance.
"""

from azext_iot.adr.ui.core.spec import (
    STYLE_ERROR,
    STYLE_MUTED,
    STYLE_OK,
    STYLE_WARN,
    Column,
    Guide,
    ResourceSpec,
)
from azext_iot.adr.ui.kinds._common import dig, name_of, prop, short_id, value_style

#: Endpoint type discriminator -> short label shown in the TYPE column.
_TYPE_LABELS = {
    "Microsoft.Devices/IotHubs": "hub",
    "Microsoft.Devices/provisioningServices": "provisioning",
    "Microsoft.DeviceUpdate/updateInstances": "updating",
}
_TYPE_STYLES = {"provisioning": STYLE_WARN, "hub": STYLE_OK, "updating": STYLE_MUTED}

#: The order the endpoints must be established in, which is also the most useful reading
#: order: provisioning first, then messaging, then updating.
_TYPE_ORDER = {"provisioning": 0, "hub": 1, "updating": 2}


def _endpoint_type(payload) -> str:
    return _TYPE_LABELS.get(str(payload.get("endpointType") or ""), "other")


def _identity(payload) -> str:
    identity = payload.get("inboundCallerIdentity") or {}
    kind = str(identity.get("type") or "")
    if not kind:
        return "none"
    assigned = identity.get("userAssignedIdentity")
    return f"{kind}:{short_id(assigned)}" if assigned else kind


def build(session) -> ResourceSpec:
    def list_endpoints(scope):
        """Concatenate the three endpoint sections into one collection."""
        namespace_name = scope.get("namespace_name")
        resource_group_name = scope.get("resource_group_name")
        endpoints = []
        for method in ("dps_list", "hub_list", "su_list"):
            endpoints.extend(
                session.list_from(
                    "link",
                    method,
                    namespace_name=namespace_name,
                    resource_group_name=resource_group_name,
                )
            )
        return endpoints

    return ResourceSpec(
        kind="link",
        title="Endpoint",
        title_plural="Endpoints",
        aliases=("ep", "endpoint"),
        parent="namespace",
        # Endpoint names are unique only within their section, so identity includes type.
        guide=Guide(
            about=(
                "Resources linked to this namespace: the provisioning service that assigns devices, the IoT Hubs they "
                "are assigned to, and any update instances."
            ),
            runs="az iot adr ns link dps|hub|su list --ns <namespace> -g <resource-group>  ·  read-only",
            note=(
                "Exactly one DPS may be linked, and it must be linked before any hub. Press w for guided setup, which "
                "handles the ordering and the role assignments."
            ),
        ),
        row_id=lambda p: f"{_endpoint_type(p)}/{name_of(p)}",
        list=list_endpoints,
        columns=(
            Column("name", "NAME", name_of, width=24),
            Column(
                "type",
                "TYPE",
                _endpoint_type,
                width=14,
                style=value_style(_endpoint_type, _TYPE_STYLES),
                sort_key=lambda p: (_TYPE_ORDER.get(_endpoint_type(p), 9), name_of(p)),
            ),
            Column("target", "TARGET", lambda p: short_id(p.get("resourceId")), width=26),
            Column("identity", "IDENTITY", _identity, width=22),
            Column(
                "linking",
                "LINKING",
                lambda p: dig(p, "provisioningStatus", "status", default="")
                or p.get("linkingState", ""),
                width=12,
                style=value_style(
                    lambda p: dig(p, "provisioningStatus", "status", default="")
                    or p.get("linkingState", ""),
                    {"Succeeded": STYLE_OK, "Failed": STYLE_ERROR, "Accepted": STYLE_WARN},
                ),
            ),
            Column("availability", "AVAILABILITY", prop("availability"), width=13, wide=True),
            Column("weight", "WEIGHT", prop("allocationWeight"), width=8, wide=True),
            Column("resource", "RESOURCE ID", lambda p: p.get("resourceId", ""), width=60, wide=True),
        ),
        sort=("type", False),
        requires=("namespace_name", "resource_group_name"),
        scope_key="endpoint_name",
    )
