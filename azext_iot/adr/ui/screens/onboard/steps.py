# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""The onboarding step graph for connectivity (S0 through S5).

Scope is deliberately limited to reaching minimum viability: a namespace that can
provision and communicate with devices. Certificates, software updates, the first device
and the first group are later steps that plug into this same engine.

Ordering here is not a UI preference. Each rule mirrors one the service enforces:
a DPS endpoint must exist before a messaging endpoint is accepted, at most one
DPS endpoint may be linked, and both the namespace and each linked resource must
present an identity.

This module is deliberately free of any UI framework import.
"""

from typing import Any, Dict, List

from azext_iot.adr.ui.core.commands import quote, render
from azext_iot.adr.ui.screens.onboard.create import (
    create_dps,
    create_hub,
    create_namespace,
    create_update_instance,
)
from azext_iot.adr.ui.screens.onboard.flow import Flow, PlanItem, Step

#: Roles the linking saga needs, in both directions.
NAMESPACE_TO_RESOURCE_ROLES = {
    "hub": ("Contributor", "IoT Hub Data Contributor"),
    "dps": ("Contributor",),
}
RESOURCE_TO_NAMESPACE_ROLE = "Contributor"
#: Role assignments are not effective immediately; linking too soon fails for a reason
#: that looks like a backend bug. The e2e waits the same amount.
ROLE_PROPAGATION_WAIT_SEC = 60

#: Execution phases. Grants must precede the links that depend on them.
PHASE_PREREQUISITE = 10
PHASE_GRANT = 20
PHASE_PROPAGATION = 30
PHASE_LINK = 40


# -- detection ----------------------------------------------------------------------


def _namespace(context: Dict[str, Any]) -> Dict[str, Any]:
    return context.get("namespace") or {}


def _endpoints(context: Dict[str, Any], section: str) -> Dict[str, Any]:
    properties = _namespace(context).get("properties") or {}
    group = properties.get(section) or {}
    return group.get("endpoints") or {}


def has_subscription(context: Dict[str, Any]) -> bool:
    return bool(context.get("subscription_id"))


def has_scope(context: Dict[str, Any]) -> bool:
    return bool(context.get("resource_group_name"))


def scope_planned(context: Dict[str, Any]) -> bool:
    return bool(context.get("resource_group_name")) or context.get("create_resource_group") is not None


def has_namespace(context: Dict[str, Any]) -> bool:
    return bool(_namespace(context))


def software_updates_linked(context: Dict[str, Any]) -> bool:
    return bool(_endpoints(context, "updating"))


def software_updates_chosen(context: Dict[str, Any]) -> bool:
    return bool(context.get("selected_sus")) or context.get("create_su") is not None


def has_identity(context: Dict[str, Any]) -> bool:
    identity = _namespace(context).get("identity") or {}
    kind = str(identity.get("type") or "None")
    return kind not in ("", "None")


def has_provisioning(context: Dict[str, Any]) -> bool:
    return bool(_endpoints(context, "provisioning"))


def has_messaging(context: Dict[str, Any]) -> bool:
    return bool(_endpoints(context, "messaging"))


# -- "will the plan satisfy this?" ---------------------------------------------------


def namespace_planned(context: Dict[str, Any]) -> bool:
    return bool(context.get("namespace_name")) or context.get("create_namespace") is not None


def identity_planned(context: Dict[str, Any]) -> bool:
    # An identity can always be assigned once the namespace exists or is planned.
    return namespace_planned(context)


def provisioning_planned(context: Dict[str, Any]) -> bool:
    return context.get("selected_dps") is not None or context.get("create_dps") is not None


def messaging_planned(context: Dict[str, Any]) -> bool:
    return bool(context.get("selected_hubs")) or context.get("create_hub") is not None


def permissions_confirmed(context: Dict[str, Any]) -> bool:
    """Role assignments are advisory until the open security question is settled.

    The flow reports what is required and lets the operator confirm it is done, rather
    than silently granting rights on the customer's behalf.
    """
    return bool(context.get("permissions_confirmed"))


# -- plan contributions --------------------------------------------------------------


class _PendingResource:
    """Stands in for a resource the plan will create.

    Its ARM id is deterministic, so the link command can be written now. Its principal id
    is not known until it exists, which is why its reverse grant is reported separately.
    """

    def __init__(self, request, subscription_id: str):
        self.name = request.name
        self.resource_id = request.arm_id(subscription_id or "<subscription>")
        self.raw = {}
        self.pending = True


def _placeholder(request, context: Dict[str, Any]) -> "_PendingResource":
    return _PendingResource(request, context.get("subscription_id") or "")


def _scope_of(context: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "namespace_name": context.get("namespace_name"),
        "resource_group_name": context.get("resource_group_name"),
    }


def plan_resource_group(context: Dict[str, Any]) -> List[PlanItem]:
    request = context.get("create_resource_group")
    if request is None:
        return [
            PlanItem(key="scope", description="Choose a resource group", action="blocked",
                     blocked_reason="no resource group chosen yet", phase=0,
                     long_running=False)
        ]

    def make(session, _ctx, _request=request):
        from azext_iot._factory import resource_service_factory

        client = resource_service_factory(session.cmd.cli_ctx).resource_groups
        return client.create_or_update(_request.name, {"location": _request.location})

    return [
        PlanItem(
            key="resource-group",
            description=f"Create resource group '{request.name}' in {request.location}",
            phase=PHASE_PREREQUISITE,
            command=f"az group create -n {request.name} -l {request.location}",
            long_running=False,
            invoke=make,
        )
    ]


def plan_namespace(context: Dict[str, Any]) -> List[PlanItem]:
    request = context.get("create_namespace")
    if request is None:
        return [
            PlanItem(
                key="namespace",
                description="Select an existing namespace, or create a new one",
                action="blocked",
                blocked_reason="no namespace selected yet",
                phase=0,
                long_running=False,
            )
        ]

    def make(session, _ctx, _request=request):
        return create_namespace(session, _request)

    command = render(
        "iot adr ns create",
        name=request.name,
        scope={"resource_group_name": request.resource_group_name},
        options={"location": request.location},
        flags=("--outbound-mi-system-assigned",),
    )
    if request.tags:
        tag_args = " ".join(
            quote(f"{key}={value}") for key, value in request.tags.items()
        )
        command += f" --tags {tag_args}"

    return [
        PlanItem(
            key="namespace",
            description=f"Create namespace '{request.name}' in {request.location}",
            phase=PHASE_PREREQUISITE,
            command=command,
            invoke=make,
        )
    ]


def _assign_identity(session, context: Dict[str, Any]):
    """Assign a system-assigned identity. PR1: no_wait, the tray drives the poller."""
    return session.call(
        session.provider("namespace").identity_assign,
        namespace_name=context.get("namespace_name"),
        resource_group_name=context.get("resource_group_name"),
        system_assigned=True,
        no_wait=True,
    )


def plan_identity(context: Dict[str, Any]) -> List[PlanItem]:
    name = context.get("namespace_name") or "<namespace>"
    if context.get("create_namespace") is not None:
        # `ns create` always assigns a system-assigned identity, so assigning one again
        # fails with "All requested managed identities are already assigned."
        return [
            PlanItem(
                key="identity",
                description="Namespace identity - assigned as part of creating the namespace",
                action="exists",
                phase=0,
                long_running=False,
            )
        ]
    return [
        PlanItem(
            key="identity",
            description="Assign a system-assigned identity to the namespace",
            phase=PHASE_PREREQUISITE,
            command=render("iot adr ns identity assign", name=name,
                           scope={"resource_group_name": context.get("resource_group_name")},
                           flags=("--system-assigned",)),
            depends_on=("namespace",),
            invoke=_assign_identity,
        )
    ]


def plan_provisioning(context: Dict[str, Any]) -> List[PlanItem]:
    dps = context.get("selected_dps")
    request = context.get("create_dps")
    items: List[PlanItem] = []

    if dps is None and request is None:
        return [
            PlanItem(key="dps", description="Select or create a DPS",
                     action="blocked", blocked_reason="no DPS chosen yet",
                     phase=0, long_running=False)
        ]

    if request is not None:
        def make(session, ctx, _request=request):
            return create_dps(ctx["_catalog"], _request)

        items.append(
            PlanItem(
                key="dps-create",
                description=(
                    f"Create DPS '{request.name}' in {request.location} "
                    f"with {request.capacity} S1 unit(s)"
                ),
                phase=PHASE_PREREQUISITE,
                command=(
                    f"az iot dps create -n {request.name} -g {request.resource_group_name} "
                    f"-l {request.location} --sku {request.sku or 'S1'} "
                    f"--unit {request.capacity} --mi-system-assigned"
                ),
                invoke=make,
            )
        )
        dps = _placeholder(request, context)

    endpoint = context.get("dps_endpoint_name") or "dps"

    def link(session, ctx, _dps=dps, _endpoint=endpoint):
        return session.call(
            session.provider("link").dps_add,
            endpoint_name=_endpoint,
            namespace_name=ctx.get("namespace_name"),
            resource_group_name=ctx.get("resource_group_name"),
            dps_resource_id=_dps.resource_id,
            mi_system_assigned=True,
            no_wait=True,
        )

    items.append(
        PlanItem(
            key="dps",
            description=f"Link DPS '{dps.name}' as endpoint '{endpoint}'",
            phase=PHASE_LINK,
            command=render("iot adr ns link dps add", scope=_scope_of(context),
                           options={"endpoint_name": endpoint, "dps_id": dps.resource_id},
                           flags=("--mi-system-assigned",)),
            depends_on=("identity",),
            invoke=link,
        )
    )
    return items


def plan_messaging(context: Dict[str, Any]) -> List[PlanItem]:
    hubs = list(context.get("selected_hubs") or [])
    request = context.get("create_hub")
    items: List[PlanItem] = []

    if not hubs and request is None:
        return [
            PlanItem(key="hub", description="Select or create an IoT Hub", action="blocked",
                     blocked_reason="no hub chosen yet", phase=0, long_running=False)
        ]

    if request is not None:
        def make(session, ctx, _request=request):
            return create_hub(ctx["_catalog"], _request)

        items.append(
            PlanItem(
                key="hub-create",
                description=(
                    f"Create IoT Hub '{request.name}' in {request.location} "
                    f"with {request.capacity} {request.sku or 'S1'} unit(s)"
                ),
                phase=PHASE_PREREQUISITE,
                command=(
                    f"az iot hub create -n {request.name} -g {request.resource_group_name} "
                    f"-l {request.location} --sku {request.sku or 'S1'} "
                    f"--unit {request.capacity} --mi-system-assigned"
                ),
                invoke=make,
            )
        )
        hubs.append(_placeholder(request, context))
    for index, hub in enumerate(hubs):
        endpoint = hub.name if len(hubs) > 1 else (context.get("hub_endpoint_name") or hub.name)

        def link(session, ctx, _hub=hub, _endpoint=endpoint):
            return session.call(
                session.provider("link").hub_add,
                endpoint_name=_endpoint,
                namespace_name=ctx.get("namespace_name"),
                resource_group_name=ctx.get("resource_group_name"),
                hub_resource_id=_hub.resource_id,
                mi_system_assigned=True,
                no_wait=True,
            )

        items.append(
            PlanItem(
                key=f"hub-{index}",
                description=f"Link IoT Hub '{hub.name}' as endpoint '{endpoint}'",
                phase=PHASE_LINK,
                command=render("iot adr ns link hub add", scope=_scope_of(context),
                               options={"endpoint_name": endpoint, "hub_id": hub.resource_id},
                               flags=("--mi-system-assigned",)),
                # The service rejects a messaging endpoint before a provisioning one exists.
                depends_on=("dps",),
                invoke=link,
            )
        )
    return items


def principal_of(payload: Dict[str, Any]) -> str:
    """SystemAssigned principal id of a resource, or empty when it has none."""
    identity = (payload or {}).get("identity") or {}
    return str(identity.get("principalId") or "") if isinstance(identity, dict) else ""


def namespace_arm_id(context: Dict[str, Any]) -> str:
    return (
        f"/subscriptions/{context.get('subscription_id') or '<subscription>'}"
        f"/resourceGroups/{context.get('resource_group_name') or '<resource-group>'}"
        f"/providers/Microsoft.DeviceRegistry/namespaces/"
        f"{context.get('namespace_name') or '<namespace>'}"
    )


def grant_command(principal: str, role: str, scope: str) -> str:
    """A role grant addressed by object id.

    Matches the form the e2e uses: an object id needs no directory lookup, and the
    principal type must be given explicitly for a managed identity.
    """
    return (
        f"az role assignment create --assignee-object-id {principal} "
        f'--assignee-principal-type ServicePrincipal --role "{role}" --scope {scope}'
    )


def plan_software_updates(context: Dict[str, Any]) -> List[PlanItem]:
    """Optional: link an update instance so the namespace can run update jobs."""
    instances = list(context.get("selected_sus") or [])
    request = context.get("create_su")
    if not instances and request is None:
        return []

    items: List[PlanItem] = []
    if request is not None:
        def make(session, _ctx, _request=request):
            return create_update_instance(session, _request)

        items.append(
            PlanItem(
                key="su-create",
                description=f"Create update instance '{request.name}' in {request.location}",
                phase=PHASE_PREREQUISITE,
                command=render("iot adr ns su instance create", name=request.name,
                               scope={"resource_group_name": request.resource_group_name},
                               options={"location": request.location},
                               flags=("--mi-system-assigned",)),
                invoke=make,
            )
        )
        instances.append(_placeholder(request, context))

    # Updating endpoints are a map on the namespace, so several may be linked. One chosen
    # instance keeps the configured endpoint name; several must be named apart.
    for index, instance in enumerate(instances):
        endpoint = (
            instance.name if len(instances) > 1
            else (context.get("su_endpoint_name") or "su")
        )

        def link(session, ctx, _su=instance, _endpoint=endpoint):
            return session.call(
                session.provider("link").su_add,
                endpoint_name=_endpoint,
                namespace_name=ctx.get("namespace_name"),
                resource_group_name=ctx.get("resource_group_name"),
                su_resource_id=_su.resource_id,
                mi_system_assigned=True,
                no_wait=True,
            )

        items.append(
            PlanItem(
                key="su" if index == 0 else f"su-{index}",
                description=f"Link update instance '{instance.name}' as endpoint '{endpoint}'",
                phase=PHASE_LINK,
                command=render("iot adr ns link su add", scope=_scope_of(context),
                               options={"endpoint_name": endpoint, "su_id": instance.resource_id},
                               flags=("--mi-system-assigned",)),
                depends_on=("dps",),
                invoke=link,
            )
        )
    return items


def _grant_invoker(principal: str, principal_source: str, role: str, scope: str):
    """Bind one grant so the plan can run it like any other operation.

    ``principal`` may be empty when the resource holding the identity is created by an
    earlier item of this same plan; ``principal_source`` is then read at run time, by
    which point the resource exists.
    """
    def invoke(session, _context):
        from azext_iot.adr.ui.core.rbac import grant_role, resolve_principal

        assignee = principal or resolve_principal(session, principal_source)
        if not assignee:
            raise RuntimeError(
                f"could not read a system-assigned identity for "
                f"{(principal_source or '').rsplit('/', 1)[-1] or 'the resource'}, "
                f"so '{role}' could not be granted"
            )
        created = grant_role(session, assignee, role, scope)
        if created:
            # Only a newly created assignment has to propagate; see the wait below.
            _context["_granted_any"] = True
        return None
    return invoke


def _wait_for_propagation(_session, context):
    """Role assignments are not effective the instant they are created.

    Skipped when every grant already existed - re-running setup should not idle for a
    minute waiting for propagation that happened long ago.
    """
    import time

    if not context.get("_granted_any"):
        return None
    time.sleep(ROLE_PROPAGATION_WAIT_SEC)
    return None


def plan_permissions(context: Dict[str, Any]) -> List[PlanItem]:
    """Emit the grants the linking saga needs, in both directions, ready to run.

    Both principal ids are already known - the namespace payload and each candidate carry
    their own identity - so the commands are emitted complete rather than as placeholders
    a customer would have to fill in by hand.

    Whether radr runs them itself turns on ``can_grant_roles`` in the context, which is
    ARM's own answer about this caller at this scope. When ARM says no, the grants stay in
    the plan as commands to hand to someone with Owner or User Access Administrator -
    the customer still sees exactly what has to happen, and why radr stopped short.
    """
    namespace_scope = namespace_arm_id(context)
    namespace_principal = principal_of(context.get("namespace") or {})
    #: None means "not probed / could not tell", which is treated as no.
    may_grant = context.get("can_grant_roles") is True

    items: List[PlanItem] = []
    targets = []
    # Resources being created need the same grants as existing ones; their principal id
    # is simply not known yet, which the reverse grant reports explicitly.
    if context.get("selected_dps") is not None:
        targets.append(("dps", context["selected_dps"]))
    elif context.get("create_dps") is not None:
        targets.append(("dps", _placeholder(context["create_dps"], context)))
    for hub in context.get("selected_hubs") or []:
        targets.append(("hub", hub))
    if context.get("create_hub") is not None:
        targets.append(("hub", _placeholder(context["create_hub"], context)))

    for kind, target in targets:
        target_principal = principal_of(getattr(target, "raw", None) or {})
        target_pending = bool(getattr(target, "pending", False))
        namespace_pending = context.get("create_namespace") is not None

        # Forward: the namespace identity acts on the linked resource.
        for role in NAMESPACE_TO_RESOURCE_ROLES[kind]:
            item = PlanItem(
                key=f"grant-ns-to-{kind}-{target.name}-{role}",
                description=f"Grant the namespace identity '{role}' on {kind} '{target.name}'",
                action="manual",
                phase=PHASE_GRANT,
                long_running=False,
            )
            if namespace_principal or namespace_pending:
                item.command = grant_command(
                    namespace_principal or "<namespace principal id>", role, target.resource_id
                )
                if may_grant:
                    item.action = "create"
                    # An empty principal is resolved when the item runs, by which point an
                    # earlier item in this same plan has created the namespace.
                    item.invoke = _grant_invoker(
                        namespace_principal, namespace_scope, role, target.resource_id
                    )
                elif not namespace_principal:
                    item.blocked_reason = (
                        "run this after the namespace is created, using its principal id"
                    )
            else:
                item.action = "blocked"
                item.blocked_reason = (
                    "the namespace has no system-assigned identity yet; assign one first"
                )
            items.append(item)

        # Reverse: the linked resource's identity acts on the namespace.
        reverse = PlanItem(
            key=f"grant-{kind}-to-ns-{target.name}",
            description=(
                f"Grant {kind} '{target.name}' identity "
                f"'{RESOURCE_TO_NAMESPACE_ROLE}' on the namespace"
            ),
            action="manual",
            phase=PHASE_GRANT,
            long_running=False,
        )
        if target_principal or target_pending:
            reverse.command = grant_command(
                target_principal or f"<{target.name} principal id>",
                RESOURCE_TO_NAMESPACE_ROLE,
                namespace_scope,
            )
            if may_grant:
                reverse.action = "create"
                reverse.invoke = _grant_invoker(
                    target_principal, target.resource_id,
                    RESOURCE_TO_NAMESPACE_ROLE, namespace_scope,
                )
            elif not target_principal:
                reverse.blocked_reason = (
                    f"run this after {target.name} is created, using its principal id"
                )
        else:
            reverse.action = "blocked"
            reverse.blocked_reason = (
                f"{target.name} exposes no system-assigned identity, so the reverse grant "
                "cannot be made; recreate it with an identity"
            )
        items.append(reverse)

    if items:
        items.append(
            PlanItem(
                key="grant-propagation",
                description=(
                    f"Wait about {ROLE_PROPAGATION_WAIT_SEC}s for role propagation before linking"
                ),
                action="create" if may_grant else "manual",
                phase=PHASE_PROPAGATION,
                long_running=False,
                command=f"sleep {ROLE_PROPAGATION_WAIT_SEC}",
                invoke=_wait_for_propagation if may_grant else None,
            )
        )
    return items


# -- graph ---------------------------------------------------------------------------


def build_flow(context: Dict[str, Any]) -> Flow:
    """The connectivity flow: scope, namespace, identity, provisioning, messaging, grants."""
    steps = [
        Step(id="subscription", title="Subscription", detect=has_subscription),
        Step(id="scope", title="Resource group", after=("subscription",), detect=has_scope,
             planned=scope_planned, plan=plan_resource_group,
             blocked_reason="Choose a subscription first."),
        Step(id="namespace", title="Namespace", after=("scope",), detect=has_namespace,
             planned=namespace_planned, plan=plan_namespace),
        # Never a decision: `ns create` always assigns one, and adopting a namespace
        # without one simply adds an assign to the plan.
        Step(
            id="identity",
            title="Namespace identity",
            after=("namespace",),
            detect=has_identity,
            planned=identity_planned,
            plan=plan_identity,
            hidden=True,
            blocked_reason=(
                "Choose a namespace first. radr will enable its managed identity "
                "automatically when setup runs."
            ),
        ),
        Step(
            id="dps",
            title="Link DPS",
            after=("identity",),
            detect=has_provisioning,
            planned=provisioning_planned,
            plan=plan_provisioning,
            blocked_reason=(
                "The namespace needs a managed identity so Azure can authorize access "
                "to DPS and IoT Hub. radr adds it automatically when setup runs."
            ),
        ),
        Step(
            id="hub",
            title="Link Hub",
            after=("dps",),
            detect=has_messaging,
            planned=messaging_planned,
            plan=plan_messaging,
            blocked_reason=(
                "Choose a DPS first. Azure requires the DPS link before any IoT Hub link."
            ),
        ),
        Step(id="su", title="Link Software Updates", after=("dps",),
             detect=software_updates_linked, planned=software_updates_chosen,
             plan=plan_software_updates, optional=True,
             blocked_reason="Choose a DPS first."),
        Step(id="permissions", title="Grant role assignments",
             after=("dps",), detect=permissions_confirmed, plan=plan_permissions,
             hidden=True,
             blocked_reason="Choose the DPS, hubs, or update instances to link first."),
        # The commit point, named so the rail shows where changes happen.
        Step(id="review", title="Review and run", after=("namespace",),
             detect=lambda ctx: False, optional=True,
             blocked_reason="Choose or create a namespace first."),
    ]
    return Flow(steps=steps, context=context)
