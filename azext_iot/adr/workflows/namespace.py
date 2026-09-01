# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import shlex
from typing import Any, Dict, Iterable, List, Optional, Tuple

from azure.cli.core.azclierror import ArgumentUsageError

from azext_iot.adr.workflows.models import (
    STATE_BLOCKED,
    STATE_FAILED,
    STATE_MANUAL,
    STATE_NOT_CONFIGURED,
    STATE_PLANNED,
    STATE_SATISFIED,
    STATE_SUCCEEDED,
    STATE_WARNING,
    EndpointSpec,
    PlanItem,
    SetupRequest,
    WorkflowExecutionError,
    workflow_result,
)
from azext_iot.adr.workflows.services import (
    DEFAULT_ROLE,
    HUB_ROLES,
    WorkflowServices,
    as_dict,
    is_not_found,
    value_of,
)


ADU_FIRST_PARTY_APPLICATION_ID = "6ee392c4-d339-4083-b04d-6b7947c6cf78"
ROLE_PROPAGATION_WAIT_SECONDS = 60

_SECTIONS = {
    "dps": "provisioning",
    "hub": "messaging",
    "software-updates": "updating",
}


def _nested(mapping: Dict[str, Any], *names: str):
    value: Any = mapping
    for name in names:
        value = as_dict(value).get(name)
    return value


def _endpoint_map(namespace: Optional[Dict[str, Any]], kind: str):
    return as_dict(
        _nested(
            namespace or {},
            "properties",
            _SECTIONS[kind],
            "endpoints",
        )
    )


def _normalize_id(value: Optional[str]) -> str:
    return (value or "").rstrip("/").casefold()


def _hub_name(value: Any) -> str:
    name = str(value or "").rstrip("/").rsplit("/", 1)[-1]
    return name.split(".", 1)[0].casefold()


def _quote(value: Any) -> str:
    return shlex.quote(str(value))


def _outbound_matches(namespace: Dict[str, Any], request: SetupRequest) -> bool:
    if not request.outbound_identity_type:
        return True
    outbound = as_dict(_nested(namespace, "properties", "outboundIdentity"))
    if value_of(outbound, "type") != request.outbound_identity_type:
        return False
    if request.outbound_identity_type == "UserAssigned":
        current = value_of(
            outbound, "userAssignedIdentity", "user_assigned_identity"
        )
        return _normalize_id(current) == _normalize_id(
            request.outbound_user_assigned_identity
        )
    return True


def _link_matches(link: Dict[str, Any], endpoint: EndpointSpec) -> bool:
    if _normalize_id(value_of(link, "resourceId", "resource_id")) != _normalize_id(
        endpoint.resource_id
    ):
        return False
    identity = as_dict(
        value_of(link, "inboundCallerIdentity", "inbound_caller_identity")
    )
    identity_type = str(value_of(identity, "type") or "")
    if endpoint.identity_type == "system-assigned":
        return identity_type == "SystemAssigned"
    current_uami = value_of(
        identity, "userAssignedIdentity", "user_assigned_identity"
    )
    return identity_type == "UserAssigned" and _normalize_id(
        current_uami
    ) == _normalize_id(endpoint.user_assigned_identity)


def _link_state(link: Dict[str, Any]) -> str:
    return str(value_of(link, "linkingState", "linking_state") or "")


def _has_healthy_dps(namespace: Optional[Dict[str, Any]]) -> bool:
    return any(
        _link_state(as_dict(endpoint)) == "Succeeded"
        for endpoint in _endpoint_map(namespace, "dps").values()
    )


def _link_spec(kind: str, name: str, link: Dict[str, Any]) -> EndpointSpec:
    identity = as_dict(
        value_of(link, "inboundCallerIdentity", "inbound_caller_identity")
    )
    identity_type = str(value_of(identity, "type") or "")
    return EndpointSpec(
        kind=kind,
        endpoint_name=name,
        resource_id=value_of(link, "resourceId", "resource_id") or "",
        identity_type=(
            "user-assigned"
            if identity_type == "UserAssigned"
            else "system-assigned"
        ),
        user_assigned_identity=value_of(
            identity, "userAssignedIdentity", "user_assigned_identity"
        ),
    )


class NamespaceWorkflow:
    def __init__(self, services: WorkflowServices, progress=None):
        self.services = services
        self.progress = progress

    def _run(
        self,
        label: str,
        operation,
        *args,
        workflow_scope=None,
        mutation=False,
        handled_error=None,
        **kwargs,
    ):
        if self.progress:
            if workflow_scope:
                progress_options = {
                    "workflow_scope": workflow_scope,
                }
                if mutation:
                    progress_options["mutation"] = True
                if handled_error:
                    progress_options["handled_error"] = handled_error
                return self.progress.run(
                    label,
                    operation,
                    *args,
                    **progress_options,
                    **kwargs,
                )
            return self.progress.run(label, operation, *args, **kwargs)
        return operation(*args, **kwargs)

    def check(self, namespace_name: str, resource_group_name: str):
        items: List[PlanItem] = []
        namespace = self._run(
            "Read namespace",
            self.services.show_namespace,
            namespace_name,
            resource_group_name,
        )
        if namespace is None:
            raise ArgumentUsageError(
                f"Namespace '{namespace_name}' was not found in resource group "
                f"'{resource_group_name}'."
            )
        provisioning_state = _nested(
            namespace, "properties", "provisioningState"
        )
        namespace_state = STATE_SATISFIED
        if provisioning_state in {"Failed", "Canceled"}:
            namespace_state = STATE_BLOCKED
        elif provisioning_state not in (None, "Succeeded"):
            namespace_state = STATE_WARNING
        items.append(
            PlanItem(
                "namespace",
                "check",
                namespace_name,
                namespace_state,
                f"provisioningState={provisioning_state or 'not returned'}",
            )
        )

        configured_endpoints = {
            kind: _endpoint_map(namespace, kind)
            for kind in ("dps", "hub", "software-updates")
        }
        has_links = any(configured_endpoints.values())
        try:
            outbound_principal = self._run(
                "Resolve outbound identity",
                self.services.namespace_outbound_principal,
                namespace,
            )
            items.append(
                PlanItem(
                    "namespace-outbound-identity",
                    "check",
                    namespace_name,
                    STATE_SATISFIED,
                    f"principalId={outbound_principal}",
                )
            )
        except Exception as error:  # noqa: BLE001 - readiness records the reason
            outbound_principal = None
            items.append(
                PlanItem(
                    "namespace-outbound-identity",
                    "check",
                    namespace_name,
                    STATE_BLOCKED if has_links else STATE_NOT_CONFIGURED,
                    (
                        str(error)
                        if has_links
                        else "No configured link requires an outbound identity."
                    ),
                )
            )

        for kind in ("dps", "hub", "software-updates"):
            endpoints = configured_endpoints[kind]
            if not endpoints:
                items.append(
                    PlanItem(
                        f"{kind}-links",
                        "check",
                        kind,
                        STATE_NOT_CONFIGURED,
                        "No endpoint is configured.",
                    )
                )
                continue
            for name, value in endpoints.items():
                link = as_dict(value)
                spec = _link_spec(kind, name, link)
                state = _link_state(link)
                item_state = (
                    STATE_SATISFIED
                    if state == "Succeeded"
                    else STATE_BLOCKED
                    if state in {"Failed", "Canceled"}
                    else STATE_WARNING
                )
                items.append(
                    PlanItem(
                        f"{kind}-link-{name}",
                        "check",
                        name,
                        item_state,
                        f"linkingState={state or 'not returned'}",
                        details={"resourceId": spec.resource_id},
                    )
                )
                self._check_link_resource_and_roles(
                    items,
                    namespace,
                    outbound_principal,
                    spec,
                )

        state = (
            STATE_BLOCKED
            if any(item.state in {STATE_BLOCKED, STATE_FAILED} for item in items)
            else STATE_WARNING
            if any(item.state == STATE_WARNING for item in items)
            else STATE_SUCCEEDED
        )
        return workflow_result(
            "az iot adr ns check",
            state,
            namespace_name,
            resource_group_name,
            items,
        )

    def plan_setup(self, request: SetupRequest) -> Tuple[Dict[str, Any], List[PlanItem]]:
        items: List[PlanItem] = []
        endpoint_names = [
            endpoint.endpoint_name.casefold()
            for endpoint in self._requested_endpoints(request)
        ]
        duplicates = sorted({
            name for name in endpoint_names
            if endpoint_names.count(name) > 1
        })
        if duplicates:
            raise ArgumentUsageError(
                "Endpoint names must be unique across DPS, Hub, and "
                "Software Updates links: "
                + ", ".join(duplicates)
            )
        resource_ids = [
            _normalize_id(endpoint.resource_id)
            for endpoint in self._requested_endpoints(request)
        ]
        duplicate_resources = sorted({
            resource_id for resource_id in resource_ids
            if resource_ids.count(resource_id) > 1
        })
        if duplicate_resources:
            raise ArgumentUsageError(
                "Each target resource can be linked only once: "
                + ", ".join(duplicate_resources)
            )
        namespace = self.services.show_namespace(
            request.namespace_name, request.resource_group_name
        )
        if namespace is None:
            create_command = (
                f"az iot adr ns create -n {_quote(request.namespace_name)} "
                f"-g {_quote(request.resource_group_name)}"
            )
            if request.location:
                create_command += f" --location {_quote(request.location)}"
            if request.tags:
                create_command += " --tags " + " ".join(
                    _quote(f"{key}={value}")
                    for key, value in sorted(request.tags.items())
                )
            details = {}
            if request.location:
                details["location"] = request.location
            if request.tags:
                details["tags"] = request.tags
            items.append(
                PlanItem(
                    "namespace",
                    "create",
                    request.namespace_name,
                    STATE_PLANNED,
                    command=create_command,
                    details=details,
                )
            )
        else:
            provisioning_state = _nested(
                namespace, "properties", "provisioningState"
            )
            if provisioning_state not in (None, "Succeeded"):
                items.append(
                    PlanItem(
                        "namespace",
                        "reuse",
                        request.namespace_name,
                        STATE_BLOCKED,
                        f"Namespace provisioningState is "
                        f"'{provisioning_state}'. Wait for Succeeded, then rerun.",
                    )
                )
            else:
                items.append(
                    PlanItem(
                        "namespace",
                        "reuse",
                        request.namespace_name,
                        STATE_SATISFIED,
                    )
                )
            if request.tags is not None:
                existing_tags = namespace.get("tags") or {}
                mismatched = existing_tags != request.tags
                items.append(
                    PlanItem(
                        "namespace-tags",
                        "reuse",
                        request.namespace_name,
                        (
                            STATE_WARNING
                            if mismatched
                            else STATE_SATISFIED
                        ),
                        (
                            "Requested tags differ from the existing "
                            "namespace. Tags are only applied when setup "
                            "creates a namespace."
                            if mismatched
                            else "Requested tags already match."
                        ),
                        details={"tags": request.tags},
                        command=(
                            "az iot adr ns update "
                            f"-n {_quote(request.namespace_name)} "
                            f"-g {_quote(request.resource_group_name)} "
                            "--tags "
                            + " ".join(
                                _quote(f"{key}={value}")
                                for key, value in sorted(
                                    request.tags.items()
                                )
                            )
                            if mismatched and request.tags
                            else ""
                        ),
                    )
                )

        if request.outbound_identity_type:
            state = (
                STATE_SATISFIED
                if namespace and _outbound_matches(namespace, request)
                else STATE_PLANNED
            )
            items.append(
                PlanItem(
                    "namespace-outbound-identity",
                    "configure",
                    request.namespace_name,
                    state,
                    command=(
                        f"az iot adr ns update "
                        f"-n {_quote(request.namespace_name)} "
                        f"-g {_quote(request.resource_group_name)} "
                        + (
                            "--outbound-mi-system-assigned"
                            if request.outbound_identity_type == "SystemAssigned"
                            else "--outbound-mi-user-assigned "
                            f"{_quote(request.outbound_user_assigned_identity)}"
                        )
                    ),
                    dependencies=("namespace",),
                    details={
                        "identityType": request.outbound_identity_type,
                        "userAssignedIdentity": (
                            request.outbound_user_assigned_identity
                        ),
                    },
                )
            )
        elif namespace is None and request.requests_links:
            items.append(
                PlanItem(
                    "namespace-outbound-identity",
                    "validate",
                    request.namespace_name,
                    STATE_BLOCKED,
                    "A new namespace requires an outbound identity before "
                    "endpoint links can be configured.",
                )
            )

        resources: Dict[str, Dict[str, Any]] = {}
        resource_items = []
        for endpoint in self._requested_endpoints(request):
            key = self._endpoint_key(endpoint)
            try:
                resources[key] = self._run(
                    f"Validate {endpoint.kind} {endpoint.endpoint_name}",
                    self.services.resolve_resource,
                    endpoint,
                    workflow_scope=endpoint.kind,
                    handled_error=(
                        is_not_found
                        if endpoint.kind == "software-updates"
                        and request.create_update_instance
                        else None
                    ),
                )
                resource_items.append(
                    PlanItem(
                        f"resource-{key}",
                        "validate",
                        endpoint.resource_id,
                        STATE_SATISFIED,
                    )
                )
            except Exception as error:  # noqa: BLE001 - only SU may be planned
                if (
                    endpoint.kind == "software-updates"
                    and request.create_update_instance
                    and is_not_found(error)
                ):
                    resource_items.append(
                        PlanItem(
                            f"resource-{key}",
                            "create",
                            endpoint.resource_id,
                            STATE_PLANNED,
                        )
                    )
                    continue
                raise

        items.extend(resource_items)
        if request.dps:
            dps_resource = resources.get(
                self._endpoint_key(request.dps), {}
            )
            dps_hubs = [
                as_dict(item)
                for item in as_dict(
                    dps_resource.get("properties")
                ).get("iotHubs", [])
            ]
            requested_hubs = {
                _hub_name(endpoint.resource_id)
                for endpoint in request.hubs
            }
            existing_hubs = {
                _hub_name(
                    value_of(
                        as_dict(link), "resourceId", "resource_id"
                    )
                )
                for link in _endpoint_map(namespace, "hub").values()
            }
            unlinked = sorted(
                str(value_of(hub, "name", "hostName", "host_name"))
                for hub in dps_hubs
                if value_of(hub, "name", "hostName", "host_name")
                and _hub_name(
                    value_of(hub, "name", "hostName", "host_name")
                )
                not in requested_hubs | existing_hubs
            )
            if unlinked:
                items.append(
                    PlanItem(
                        "dps-allocation-warning",
                        "validate",
                        request.dps.endpoint_name,
                        STATE_WARNING,
                        "DPS references Hub(s) not linked in this run: "
                        + ", ".join(unlinked)
                        + ". Devices allocated there may not appear in the "
                        "registry.",
                    )
                )
        if request.hubs and not (request.dps or _has_healthy_dps(namespace)):
            items.append(
                PlanItem(
                    "hub-prerequisite",
                    "validate",
                    "DPS link",
                    STATE_BLOCKED,
                    "A healthy existing or requested DPS link is required before Hub linking.",
                )
            )

        link_items = []
        for endpoint in self._requested_endpoints(request):
            existing = _endpoint_map(namespace, endpoint.kind)
            current = as_dict(existing.get(endpoint.endpoint_name))
            matching_name = next(
                (
                    name
                    for name, link in existing.items()
                    if _normalize_id(
                        value_of(
                            as_dict(link),
                            "resourceId",
                            "resource_id",
                        )
                    )
                    == _normalize_id(endpoint.resource_id)
                ),
                None,
            )
            if current:
                if _link_matches(current, endpoint):
                    link_state = _link_state(current)
                    if link_state == "Succeeded":
                        state = STATE_SATISFIED
                        message = "Matching endpoint already exists."
                    elif link_state in {"Failed", "Canceled"}:
                        state = STATE_BLOCKED
                        message = (
                            f"Matching endpoint is in {link_state} state."
                        )
                    else:
                        state = STATE_PLANNED
                        message = (
                            "Matching endpoint exists and will be awaited."
                        )
                else:
                    state = STATE_BLOCKED
                    message = "Endpoint name already targets another resource or identity."
            elif matching_name:
                state = STATE_BLOCKED
                message = (
                    f"Target resource is already linked as "
                    f"'{matching_name}'. Reuse that endpoint name."
                )
            elif endpoint.kind == "dps" and existing:
                state = STATE_BLOCKED
                message = "The namespace already has a DPS endpoint."
            else:
                state = STATE_PLANNED
                message = ""
            link_items.append(
                PlanItem(
                    f"link-{self._endpoint_key(endpoint)}",
                    "link",
                    endpoint.endpoint_name,
                    state,
                    message,
                    command=(
                        self._link_command(request, endpoint)
                        if not current
                        else ""
                    ),
                    dependencies=("namespace-outbound-identity",),
                    details={
                        "resourceId": endpoint.resource_id,
                        "identityType": endpoint.identity_type,
                        "userAssignedIdentity": (
                            endpoint.user_assigned_identity
                        ),
                    },
                )
            )

        if request.requests_links:
            if namespace and _outbound_matches(namespace, request):
                try:
                    items.extend(
                        self._plan_roles(request, namespace, resources)
                    )
                except Exception as error:  # noqa: BLE001 - plan surfaces validation
                    items.append(
                        PlanItem(
                            "roles",
                            "grant",
                            request.namespace_name,
                            STATE_BLOCKED,
                            str(error),
                        )
                    )
            else:
                for endpoint in self._requested_endpoints(request):
                    state = (
                        STATE_PLANNED
                        if request.assign_roles
                        else STATE_MANUAL
                    )
                    items.append(
                        PlanItem(
                            f"roles-{self._endpoint_key(endpoint)}",
                            "grant",
                            endpoint.resource_id,
                            state,
                            "Principal IDs will be resolved after identity setup.",
                            dependencies=("namespace-outbound-identity",),
                        )
                    )

        items.extend(link_items)
        for capability in request.skipped:
            items.append(
                PlanItem(
                    f"skip-{capability}",
                    "skip",
                    capability,
                    STATE_NOT_CONFIGURED,
                    "Skipped by user.",
                )
            )
        if request.check_status:
            items.append(
                PlanItem(
                    "namespace-status",
                    "check",
                    request.namespace_name,
                    (
                        STATE_SATISFIED
                        if namespace
                        else STATE_PLANNED
                    ),
                    (
                        "Read-only status probe completed."
                        if namespace
                        else "Readiness will be verified after apply."
                    ),
                )
            )
        state = (
            STATE_BLOCKED
            if any(item.state == STATE_BLOCKED for item in items)
            else STATE_MANUAL
            if any(item.state == STATE_MANUAL for item in items)
            else STATE_PLANNED
            if any(item.state == STATE_PLANNED for item in items)
            else STATE_SUCCEEDED
        )
        return workflow_result(
            "az iot adr ns setup",
            state,
            request.namespace_name,
            request.resource_group_name,
            items,
        ), items

    def setup(self, request: SetupRequest):
        _, plan = self.plan_setup(request)
        blocked = [item for item in plan if item.state == STATE_BLOCKED]
        if blocked:
            messages = "; ".join(item.message for item in blocked)
            raise ArgumentUsageError(f"Namespace setup is blocked: {messages}")

        items: List[PlanItem] = [
            item
            for item in plan
            if item.action == "skip" or item.item_id == "namespace-tags"
        ]
        try:
            return self._apply_setup(request, items)
        except KeyboardInterrupt as error:
            raise self._execution_error(request, items, error) from error
        except Exception as error:
            raise self._execution_error(request, items, error) from error

    @staticmethod
    def _execution_error(request, items, error):
        items.append(
            PlanItem(
                "execution",
                "apply",
                request.namespace_name,
                STATE_FAILED,
                (
                    "Interrupted by user."
                    if isinstance(error, KeyboardInterrupt)
                    else str(error) or error.__class__.__name__
                ),
            )
        )
        result = workflow_result(
            "az iot adr ns setup",
            STATE_FAILED,
            request.namespace_name,
            request.resource_group_name,
            items,
        )
        return WorkflowExecutionError(error, result)

    def _apply_setup(
        self, request: SetupRequest, items: List[PlanItem]
    ) -> Dict[str, Any]:
        namespace = self.services.show_namespace(
            request.namespace_name, request.resource_group_name
        )
        if namespace is None:
            namespace = self._run(
                f"Create namespace {request.namespace_name}",
                self.services.create_namespace,
                request.namespace_name,
                request.resource_group_name,
                request.location,
                request.outbound_identity_type,
                request.outbound_user_assigned_identity,
                tags=request.tags,
            )
            items.append(
                PlanItem(
                    "namespace",
                    "create",
                    request.namespace_name,
                    STATE_SUCCEEDED,
                )
            )
        else:
            items.append(
                PlanItem(
                    "namespace",
                    "reuse",
                    request.namespace_name,
                    STATE_SATISFIED,
                )
            )

        if request.outbound_identity_type and not _outbound_matches(
            namespace, request
        ):
            self._run(
                "Configure namespace outbound identity",
                self.services.configure_outbound_identity,
                request.namespace_name,
                request.resource_group_name,
                request.outbound_identity_type,
                request.outbound_user_assigned_identity,
            )
            items.append(
                PlanItem(
                    "namespace-outbound-identity",
                    "configure",
                    request.namespace_name,
                    STATE_SUCCEEDED,
                )
            )
            namespace = self.services.show_namespace(
                request.namespace_name, request.resource_group_name
            )
        elif request.outbound_identity_type:
            items.append(
                PlanItem(
                    "namespace-outbound-identity",
                    "reuse",
                    request.namespace_name,
                    STATE_SATISFIED,
                )
            )

        resources = self._resolve_or_create_resources(request, namespace, items)
        role_items, roles_ready = self._ensure_roles(
            request, namespace, resources
        )
        items.extend(role_items)
        if not roles_ready:
            status_state = None
            if request.check_status:
                status_state = self._append_status_check(
                    request, items
                )
            result = workflow_result(
                "az iot adr ns setup",
                (
                    STATE_BLOCKED
                    if status_state in {STATE_BLOCKED, STATE_FAILED}
                    else STATE_MANUAL
                ),
                request.namespace_name,
                request.resource_group_name,
                items,
            )
            result["resumeCommand"] = self._resume_command(request)
            return result

        self._apply_links(request, namespace, items)
        if request.check_status:
            self._append_status_check(request, items)
        result_state = (
            STATE_BLOCKED
            if any(
                item.state in {STATE_BLOCKED, STATE_FAILED}
                for item in items
            )
            else STATE_WARNING
            if any(item.state == STATE_WARNING for item in items)
            else STATE_SUCCEEDED
        )
        return workflow_result(
            "az iot adr ns setup",
            result_state,
            request.namespace_name,
            request.resource_group_name,
            items,
        )

    def _append_status_check(
        self, request: SetupRequest, items: List[PlanItem]
    ):
        status = self.check(
            request.namespace_name, request.resource_group_name
        )
        state = (
            STATE_SUCCEEDED
            if status["state"] == STATE_SUCCEEDED
            else STATE_BLOCKED
            if status["state"] in {STATE_BLOCKED, STATE_FAILED}
            else STATE_WARNING
        )
        items.append(
            PlanItem(
                "namespace-status",
                "check",
                request.namespace_name,
                state,
                f"Read-only readiness result: {status['state']}.",
            )
        )
        return state

    def _check_link_resource_and_roles(
        self,
        items: List[PlanItem],
        namespace: Dict[str, Any],
        outbound_principal: Optional[str],
        endpoint: EndpointSpec,
    ):
        key = self._endpoint_key(endpoint)
        try:
            resource = self._run(
                f"Validate {endpoint.kind} {endpoint.endpoint_name}",
                self.services.resolve_resource,
                endpoint,
                workflow_scope=endpoint.kind,
            )
            items.append(
                PlanItem(
                    f"resource-{key}",
                    "check",
                    endpoint.resource_id,
                    STATE_SATISFIED,
                )
            )
            target_principal = self._run(
                f"Resolve {endpoint.kind} identity",
                self.services.principal_for_identity,
                endpoint.identity_type,
                endpoint.user_assigned_identity,
                resource,
                workflow_scope=endpoint.kind,
            )
        except Exception as error:  # noqa: BLE001 - readiness records the reason
            items.append(
                PlanItem(
                    f"resource-{key}",
                    "check",
                    endpoint.resource_id,
                    STATE_BLOCKED,
                    str(error),
                )
            )
            return
        if not outbound_principal:
            return
        for role in self._roles_for(
            endpoint,
            namespace,
            outbound_principal,
            target_principal,
            include_setup_only=False,
        ):
            try:
                exists = self._run(
                    f"Check {role['role']} on {endpoint.endpoint_name}",
                    self.services.rbac.has_assignment,
                    role["principalId"],
                    role["role"],
                    role["scope"],
                    workflow_scope=endpoint.kind,
                )
                state = STATE_SATISFIED if exists else STATE_BLOCKED
                message = "" if exists else "Required role assignment is missing."
            except Exception as error:  # noqa: BLE001 - distinguish unreadable RBAC
                state = STATE_WARNING
                message = f"Unable to inspect role assignment: {error}"
            items.append(
                PlanItem(
                    role["id"],
                    "check",
                    role["scope"],
                    state,
                    message,
                    command=self._role_command(role),
                    details={
                        "principalId": role["principalId"],
                        "role": role["role"],
                    },
                )
            )

    def _resolve_or_create_resources(
        self,
        request: SetupRequest,
        namespace: Dict[str, Any],
        items: List[PlanItem],
    ):
        resources = {}
        for endpoint in self._requested_endpoints(request):
            key = self._endpoint_key(endpoint)
            try:
                resource = self._run(
                    f"Validate {endpoint.kind} {endpoint.endpoint_name}",
                    self.services.resolve_resource,
                    endpoint,
                    workflow_scope=endpoint.kind,
                    handled_error=(
                        is_not_found
                        if endpoint.kind == "software-updates"
                        and request.create_update_instance
                        else None
                    ),
                )
                state = STATE_SATISFIED
                action = "reuse"
            except Exception as error:  # noqa: BLE001 - only planned SU creation
                if not (
                    endpoint.kind == "software-updates"
                    and request.create_update_instance
                    and is_not_found(error)
                ):
                    raise
                resource = self._run(
                    f"Create Update Instance {endpoint.endpoint_name}",
                    self.services.create_update_instance,
                    endpoint,
                    request.location or namespace.get("location"),
                    workflow_scope=endpoint.kind,
                    mutation=True,
                )
                state = STATE_SUCCEEDED
                action = "create"
            resources[key] = resource
            items.append(
                PlanItem(
                    f"resource-{key}",
                    action,
                    endpoint.resource_id,
                    state,
                )
            )
        return resources

    def _plan_roles(
        self,
        request: SetupRequest,
        namespace: Dict[str, Any],
        resources: Dict[str, Dict[str, Any]],
    ):
        outbound_principal = self.services.namespace_outbound_principal(namespace)
        items = []
        for endpoint in self._requested_endpoints(request):
            resource = resources.get(self._endpoint_key(endpoint))
            if resource is None:
                items.append(
                    PlanItem(
                        f"roles-{self._endpoint_key(endpoint)}",
                        "grant",
                        endpoint.resource_id,
                        (
                            STATE_PLANNED
                            if request.assign_roles
                            else STATE_MANUAL
                        ),
                        "Principal IDs will be resolved after resource creation.",
                    )
                )
                continue
            target_principal = self._run(
                f"Resolve {endpoint.kind} identity",
                self.services.principal_for_identity,
                endpoint.identity_type,
                endpoint.user_assigned_identity,
                resource,
                workflow_scope=endpoint.kind,
            )
            for role in self._roles_for(
                endpoint, namespace, outbound_principal, target_principal
            ):
                exists = self._run(
                    f"Check {role['role']} assignment",
                    self.services.rbac.has_assignment,
                    role["principalId"],
                    role["role"],
                    role["scope"],
                    workflow_scope=endpoint.kind,
                )
                if exists:
                    state = STATE_SATISFIED
                    message = ""
                elif role.get("manual") or not request.assign_roles:
                    state = STATE_MANUAL
                    message = "Apply this role assignment, then rerun setup."
                elif self._run(
                    "Check role-assignment permission",
                    self.services.rbac.can_create_assignments,
                    role["scope"],
                    workflow_scope=endpoint.kind,
                ) is not True:
                    state = STATE_MANUAL
                    message = (
                        "The current caller cannot create this role assignment."
                    )
                else:
                    state = STATE_PLANNED
                    message = ""
                items.append(
                    PlanItem(
                        role["id"],
                        "grant",
                        role["scope"],
                        state,
                        message,
                        command=self._role_command(role),
                        details={
                            "principalId": role["principalId"],
                            "role": role["role"],
                        },
                    )
                )
        return items

    def _ensure_roles(
        self,
        request: SetupRequest,
        namespace: Dict[str, Any],
        resources: Dict[str, Dict[str, Any]],
    ):
        if not request.requests_links:
            return [], True
        outbound_principal = self.services.namespace_outbound_principal(namespace)
        role_specs = []
        for endpoint in self._requested_endpoints(request):
            resource = resources[self._endpoint_key(endpoint)]
            target_principal = self._run(
                f"Resolve {endpoint.kind} identity",
                self.services.principal_for_identity,
                endpoint.identity_type,
                endpoint.user_assigned_identity,
                resource,
                workflow_scope=endpoint.kind,
            )
            role_specs.extend(
                self._roles_for(
                    endpoint, namespace, outbound_principal, target_principal
                )
            )
        items = []
        created = False
        ready = True
        for role in role_specs:
            if self._run(
                f"Check {role['role']} assignment",
                self.services.rbac.has_assignment,
                role["principalId"],
                role["role"],
                role["scope"],
                workflow_scope=role.get("workflowScope"),
            ):
                state = STATE_SATISFIED
                message = ""
            elif role.get("manual") or not request.assign_roles:
                state = STATE_MANUAL
                message = "Apply this role assignment, then rerun setup."
                ready = False
            elif self._run(
                "Check role-assignment permission",
                self.services.rbac.can_create_assignments,
                role["scope"],
                workflow_scope=role.get("workflowScope"),
            ) is not True:
                state = STATE_MANUAL
                message = "The current caller cannot create this role assignment."
                ready = False
            else:
                self._run(
                    f"Create {role['role']} assignment",
                    self.services.rbac.create_assignment,
                    role["principalId"],
                    role["role"],
                    role["scope"],
                    workflow_scope=role.get("workflowScope"),
                    mutation=True,
                )
                state = STATE_SUCCEEDED
                message = ""
                created = True
            items.append(
                PlanItem(
                    role["id"],
                    "grant",
                    role["scope"],
                    state,
                    message,
                    command=self._role_command(role),
                    details={
                        "principalId": role["principalId"],
                        "role": role["role"],
                    },
                )
            )
        if created:
            self.services.sleep(ROLE_PROPAGATION_WAIT_SECONDS)
        return items, ready

    def _apply_links(
        self,
        request: SetupRequest,
        namespace: Dict[str, Any],
        items: List[PlanItem],
    ):
        dps_existing = _endpoint_map(namespace, "dps")
        hub_existing = _endpoint_map(namespace, "hub")
        remaining_hubs = list(request.hubs)
        bundled_dps = False
        if request.dps and not dps_existing and remaining_hubs:
            first_hub = remaining_hubs[0]
            if first_hub.endpoint_name not in hub_existing:
                remaining_hubs.pop(0)
                self._run(
                    "Link DPS and first IoT Hub",
                    self.services.add_dps_and_hub,
                    request,
                    request.dps,
                    first_hub,
                )
                items.extend(
                    [
                        PlanItem(
                            f"link-{self._endpoint_key(request.dps)}",
                            "link",
                            request.dps.endpoint_name,
                            STATE_SUCCEEDED,
                            "Link request submitted.",
                        ),
                        PlanItem(
                            f"link-{self._endpoint_key(first_hub)}",
                            "link",
                            first_hub.endpoint_name,
                            STATE_SUCCEEDED,
                            "Link request submitted.",
                        ),
                    ]
                )
                self._run(
                    f"Wait for DPS {request.dps.endpoint_name}",
                    self.services.wait_for_link,
                    request.namespace_name,
                    request.resource_group_name,
                    "provisioning",
                    request.dps.endpoint_name,
                )
                self._run(
                    f"Wait for IoT Hub {first_hub.endpoint_name}",
                    self.services.wait_for_link,
                    request.namespace_name,
                    request.resource_group_name,
                    "messaging",
                    first_hub.endpoint_name,
                )
                namespace = self.services.show_namespace(
                    request.namespace_name, request.resource_group_name
                )
                dps_existing = _endpoint_map(namespace, "dps")
                hub_existing = _endpoint_map(namespace, "hub")
                bundled_dps = True

        if request.dps and not bundled_dps:
            self._apply_one_link(
                request, request.dps, dps_existing, items
            )
            namespace = self.services.show_namespace(
                request.namespace_name, request.resource_group_name
            )
            hub_existing = _endpoint_map(namespace, "hub")

        for hub in remaining_hubs:
            self._apply_one_link(request, hub, hub_existing, items)
            hub_existing[hub.endpoint_name] = {
                "resourceId": hub.resource_id
            }

        if request.software_updates:
            namespace = self._run(
                "Refresh namespace for Software Updates",
                self.services.show_namespace,
                request.namespace_name,
                request.resource_group_name,
                workflow_scope="software-updates",
            )
            self._apply_one_link(
                request,
                request.software_updates,
                _endpoint_map(namespace, "software-updates"),
                items,
            )

    def _apply_one_link(
        self,
        request: SetupRequest,
        endpoint: EndpointSpec,
        existing: Dict[str, Any],
        items: List[PlanItem],
    ):
        item_id = f"link-{self._endpoint_key(endpoint)}"
        current = as_dict(existing.get(endpoint.endpoint_name))
        if current and _link_matches(current, endpoint):
            if _link_state(current) != "Succeeded":
                self._run(
                    f"Wait for {endpoint.endpoint_name}",
                    self.services.wait_for_link,
                    request.namespace_name,
                    request.resource_group_name,
                    _SECTIONS[endpoint.kind],
                    endpoint.endpoint_name,
                    workflow_scope=endpoint.kind,
                    mutation=True,
                )
            items.append(
                PlanItem(
                    item_id,
                    "reuse",
                    endpoint.endpoint_name,
                    STATE_SATISFIED,
                )
            )
            return
        if endpoint.kind == "dps":
            self._run(
                f"Link DPS {endpoint.endpoint_name}",
                self.services.add_dps,
                request,
                endpoint,
                workflow_scope=endpoint.kind,
                mutation=True,
            )
        elif endpoint.kind == "hub":
            self._run(
                f"Link IoT Hub {endpoint.endpoint_name}",
                self.services.add_hub,
                request,
                endpoint,
                workflow_scope=endpoint.kind,
                mutation=True,
            )
        else:
            self._run(
                f"Link Software Updates {endpoint.endpoint_name}",
                self.services.add_su,
                request,
                endpoint,
                workflow_scope=endpoint.kind,
                mutation=True,
            )
        items.append(
            PlanItem(
                item_id,
                "link",
                endpoint.endpoint_name,
                STATE_SUCCEEDED,
                "Link request submitted.",
            )
        )
        self._run(
            f"Wait for {endpoint.endpoint_name}",
            self.services.wait_for_link,
            request.namespace_name,
            request.resource_group_name,
            _SECTIONS[endpoint.kind],
            endpoint.endpoint_name,
            workflow_scope=endpoint.kind,
        )

    def _roles_for(
        self,
        endpoint: EndpointSpec,
        namespace: Dict[str, Any],
        outbound_principal: str,
        target_principal: str,
        include_setup_only: bool = True,
    ):
        roles = []
        outbound_roles = HUB_ROLES if endpoint.kind == "hub" else (DEFAULT_ROLE,)
        for role in outbound_roles:
            roles.append(
                {
                    "id": (
                        f"role-{endpoint.kind}-{endpoint.endpoint_name}"
                        f"-namespace-{role.replace(' ', '-').lower()}"
                    ),
                    "principalId": outbound_principal,
                    "role": role,
                    "scope": endpoint.resource_id,
                    "workflowScope": endpoint.kind,
                }
            )
        roles.append(
            {
                "id": (
                    f"role-{endpoint.kind}-{endpoint.endpoint_name}"
                    "-target-contributor"
                ),
                "principalId": target_principal,
                "role": DEFAULT_ROLE,
                "scope": namespace.get("id"),
                "workflowScope": endpoint.kind,
            }
        )
        if endpoint.kind == "software-updates" and include_setup_only:
            first_party_object_id = self._run(
                "Resolve Software Updates service principal",
                self.services.rbac.resolve_service_principal,
                ADU_FIRST_PARTY_APPLICATION_ID,
                workflow_scope="software-updates",
            )
            roles.append(
                {
                    "id": "role-software-updates-first-party",
                    "principalId": first_party_object_id,
                    "role": DEFAULT_ROLE,
                    "scope": endpoint.resource_id,
                    "manual": True,
                    "workflowScope": endpoint.kind,
                }
            )
        return roles

    @staticmethod
    def _role_command(role: Dict[str, str]) -> str:
        return (
            "az role assignment create "
            f"--assignee-object-id {_quote(role['principalId'])} "
            "--assignee-principal-type ServicePrincipal "
            f"--role {_quote(role['role'])} --scope {_quote(role['scope'])}"
        )

    @classmethod
    def _resume_command(cls, request: SetupRequest) -> str:
        command = (
            "az iot adr ns setup "
            f"-n {_quote(request.namespace_name)} "
            f"-g {_quote(request.resource_group_name)}"
        )
        if request.subscription_id:
            command += (
                f" --subscription {_quote(request.subscription_id)}"
            )
        if request.location:
            command += f" --location {_quote(request.location)}"
        if request.tags:
            command += " --tags " + " ".join(
                _quote(f"{key}={value}")
                for key, value in sorted(request.tags.items())
            )
        if request.outbound_identity_type == "SystemAssigned":
            command += " --outbound-identity system-assigned"
        elif request.outbound_user_assigned_identity:
            command += (
                " --outbound-identity "
                f"{_quote(request.outbound_user_assigned_identity)}"
            )
        for endpoint in cls._requested_endpoints(request):
            option = {
                "dps": "--dps",
                "hub": "--hub",
                "software-updates": "--su",
            }[endpoint.kind]
            identity = (
                "system-assigned"
                if endpoint.identity_type == "system-assigned"
                else endpoint.user_assigned_identity
            )
            command += (
                f" {option} endpoint={_quote(endpoint.endpoint_name)} "
                f"resource-id={_quote(endpoint.resource_id)} "
                f"identity={_quote(identity)}"
            )
            if endpoint.kind == "hub" and endpoint.availability:
                command += (
                    f" availability={_quote(endpoint.availability)}"
                )
            if (
                endpoint.kind == "hub"
                and endpoint.allocation_weight is not None
            ):
                command += (
                    " allocation-weight="
                    f"{endpoint.allocation_weight}"
                )
        if request.manual_rbac:
            command += " --manual-rbac"
        command += " --yes"
        if request.check_status:
            command += (
                " && az iot adr ns check "
                f"-n {_quote(request.namespace_name)} "
                f"-g {_quote(request.resource_group_name)}"
            )
            if request.subscription_id:
                command += (
                    " --subscription "
                    f"{_quote(request.subscription_id)}"
                )
        return command

    @staticmethod
    def _link_command(request: SetupRequest, endpoint: EndpointSpec) -> str:
        identity = (
            "--mi-system-assigned"
            if endpoint.identity_type == "system-assigned"
            else "--mi-user-assigned "
            f"{_quote(endpoint.user_assigned_identity)}"
        )
        resource_option = {
            "dps": "--dps-id",
            "hub": "--hub-id",
            "software-updates": "--su-id",
        }[endpoint.kind]
        group = {
            "dps": "link dps add",
            "hub": "link hub add",
            "software-updates": "link su add",
        }[endpoint.kind]
        command = (
            f"az iot adr ns {group} -n {_quote(endpoint.endpoint_name)} "
            f"--ns {_quote(request.namespace_name)} "
            f"-g {_quote(request.resource_group_name)} "
            f"{resource_option} {_quote(endpoint.resource_id)} {identity}"
        )
        if endpoint.kind == "hub":
            if endpoint.availability:
                command += f" --availability {_quote(endpoint.availability)}"
            if endpoint.allocation_weight is not None:
                command += (
                    f" --allocation-weight {endpoint.allocation_weight}"
                )
        return command

    @staticmethod
    def _requested_endpoints(request: SetupRequest) -> Iterable[EndpointSpec]:
        if request.dps:
            yield request.dps
        yield from request.hubs
        if request.software_updates:
            yield request.software_updates

    @staticmethod
    def _endpoint_key(endpoint: EndpointSpec) -> str:
        return f"{endpoint.kind}-{endpoint.endpoint_name}"
