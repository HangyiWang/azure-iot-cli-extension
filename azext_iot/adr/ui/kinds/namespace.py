# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Namespace: the root kind, and the scope every other kind hangs from."""

from azext_iot.adr.ui.core.spec import ChildRef, Column, Guide, ResourceSpec
from azext_iot.adr.ui.kinds._common import (
    age_column,
    dig,
    name_column,
    name_of,
    resource_group_of,
    state_column,
)


def _endpoint_counts(payload) -> str:
    """Compact 'H1 D1 S1' summary of linked endpoints, the fastest readiness signal."""
    properties = payload.get("properties") or {}
    counts = []
    for label, section in (("H", "messaging"), ("D", "provisioning"), ("S", "updating")):
        endpoints = dig(properties, section, "endpoints", default={}) or {}
        counts.append(f"{label}{len(endpoints)}")
    return " ".join(counts)


def build(session) -> ResourceSpec:
    def list_namespaces(scope):
        return session.list_from(
            "namespace",
            "list",
            resource_group_name=scope.get("resource_group_name"),
        )

    return ResourceSpec(
        kind="namespace",
        title="Namespace",
        title_plural="Namespaces",
        aliases=("ns",),
        guide=Guide(
            about=(
                "Device Registry namespaces you can reach in the current subscription - the top-level container for "
                "devices, groups, jobs and endpoints."
            ),
            runs="az iot adr ns list  ·  read-only, refreshed in the background",
            note=(
                "ENDPOINTS counts the DPS, IoT Hub and update instances linked to each namespace. Press w on a row to "
                "link more."
            ),
        ),
        row_id=name_of,
        list=list_namespaces,
        columns=(
            name_column(width=28),
            Column("rg", "RESOURCE GROUP", resource_group_of, width=22),
            Column("location", "LOCATION", lambda p: p.get("location", ""), width=14),
            state_column(),
            Column("endpoints", "ENDPOINTS", _endpoint_counts, width=11),
            Column(
                "identity",
                "IDENTITY",
                lambda p: dig(p, "identity", "type", default="None"),
                width=20,
                wide=True,
            ),
            age_column(),
        ),
        sort=("name", False),
        scope_key="namespace_name",
        # Children live in the namespace's own resource group, which may differ from the
        # one the session started in.
        scope_extra=lambda p: {"resource_group_name": resource_group_of(p)},
        children=(
            ChildRef("device", "Devices", "d"),
            ChildRef("group", "Groups", "g"),
            ChildRef("job", "Jobs", "j"),
            ChildRef("link", "Endpoints", "l"),
            ChildRef("ca", "Certificate authorities", "c"),
        ),
    )
