# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import sys
from typing import List, Optional

from azure.cli.core.azclierror import (
    ArgumentUsageError,
    CLIError,
    InvalidArgumentValueError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id
from azext_iot.adr.workflows.input import (
    BackRequested,
    WorkflowCancelled,
    build_setup_request,
    resolve_scope_inputs,
    select_value,
    write_receipt_file,
    write_script_file,
)
from azext_iot.adr.workflows.namespace import NamespaceWorkflow
from azext_iot.adr.workflows.rendering import (
    RenderedWorkflowError,
    WorkflowRenderer,
)
from azext_iot.adr.workflows.services import WorkflowServices, is_not_found


class ReconfigureRequested(Exception):
    pass


def _load_resource_choices(renderer, label, loader):
    renderer.busy(f"loading accessible {label}…")
    try:
        return loader()
    finally:
        renderer.idle()


def _structured_output_requested(cmd):
    del cmd
    arguments = sys.argv[1:]
    explicit_output = any(
        argument in {"-o", "--output"}
        or argument.startswith("--output=")
        for argument in arguments
    )
    stdout = getattr(sys, "__stdout__", None) or sys.stdout
    return explicit_output or not stdout.isatty()


def _persist_receipt(result):
    try:
        result["receipt"] = write_receipt_file(result)
    except OSError as error:
        result["receiptError"] = str(error)
    return result


def _select_subscription(cmd, renderer, services, interactive, guided):
    account = services.account_context()
    renderer.account(account)
    subscription_id = services.subscription_id
    if not (interactive and guided):
        return subscription_id, services
    name = account.get("subscriptionName") or subscription_id
    while True:
        try:
            answer = renderer.prompt(
                f"Use subscription '{name}' ({subscription_id})? "
                "[y/n/q]: "
            ).casefold()
        except BackRequested:
            renderer.write(
                "Subscription is the first step; choose y, n, or q."
            )
            continue
        if answer in {"q", "quit"}:
            raise WorkflowCancelled()
        if answer not in {"n", "no"}:
            return subscription_id, services
        try:
            subscriptions = services.list_subscriptions()
        except Exception as error:
            renderer.write(
                f"! Unable to browse subscriptions: {error}. "
                "Enter an exact subscription name or ID."
            )
            try:
                exact = renderer.prompt("Subscription name or ID: ")
            except BackRequested:
                continue
            selected_account = services.resolve_subscription(exact)
            selected = selected_account.get("id")
            if not selected:
                raise ResourceNotFoundError(
                    f"Subscription '{exact}' was not found or is "
                    "inaccessible."
                )
        else:
            options = {
                str(index): (
                    item["id"],
                    " · ".join(
                        value
                        for value in (
                            item.get("name"),
                            item.get("id"),
                            item.get("state"),
                        )
                        if value
                    ),
                    str(item.get("name") or ""),
                )
                for index, item in enumerate(subscriptions, start=1)
                if item.get("id")
            }
            try:
                selected = select_value(
                    "Subscriptions",
                    options,
                    renderer.prompt,
                    renderer.write,
                )
            except BackRequested:
                continue
        cmd.cli_ctx.data["subscription_id"] = selected
        services = WorkflowServices(cmd)
        renderer.account(services.account_context())
        return selected, services


def _validate_subscription(services, renderer, subscription_id):
    renderer.phase("Subscription")
    renderer.busy("validating subscription…")
    subscription = services.show_subscription(subscription_id)
    if subscription is None:
        raise ResourceNotFoundError(
            f"Subscription '{subscription_id}' was not found or is no "
            "longer accessible."
        )
    renderer.input_status(
        "Subscription",
        str(
            subscription.get("displayName")
            or subscription.get("display_name")
            or subscription_id
        ),
        "Satisfied",
        f"{subscription_id} · {subscription.get('state') or 'Found'}",
    )


def _validate_resource_group(services, renderer, resource_group_name):
    renderer.phase("Resource group")
    renderer.busy(f"validating resource group {resource_group_name}…")
    resource_group = services.show_resource_group(resource_group_name)
    if resource_group is None:
        raise ResourceNotFoundError(
            f"Resource group '{resource_group_name}' was not found in the "
            "active subscription."
        )
    permission = services.rbac.can_create_assignments(
        resource_group.get("id")
        or (
            f"/subscriptions/{services.subscription_id}"
            f"/resourceGroups/{resource_group_name}"
        )
    )
    renderer.input_status(
        "Resource group",
        resource_group_name,
        "Satisfied",
        " · ".join(
            value
            for value in (
                "Found",
                resource_group.get("location"),
                (
                    "role grants allowed"
                    if permission is True
                    else "manual role grants required"
                    if permission is False
                    else None
                ),
            )
            if value
        ),
    )


def _validate_namespace(
    services,
    renderer,
    namespace_name,
    resource_group_name,
    allow_missing,
    confirm_create=False,
):
    renderer.phase("Namespace")
    renderer.busy(f"looking up namespace {namespace_name}…")
    namespace = services.show_namespace(
        namespace_name, resource_group_name
    )
    if namespace is None:
        if not allow_missing:
            raise ResourceNotFoundError(
                f"Namespace '{namespace_name}' was not found in resource "
                f"group '{resource_group_name}'."
            )
        renderer.input_status(
            "Namespace",
            namespace_name,
            "Planned",
            "Not found; setup will create it.",
        )
        if confirm_create:
            while True:
                answer = renderer.prompt(
                    f"Create namespace '{namespace_name}' during apply? "
                    "[y/n]: "
                ).casefold()
                if answer in {"", "y", "yes"}:
                    break
                if answer in {"n", "no"}:
                    raise BackRequested()
                renderer.write(
                    "Enter y or n. Use :back, :help, or :quit."
                )
        return
    renderer.input_status(
        "Namespace",
        namespace_name,
        "Satisfied",
        " · ".join(
            value
            for value in (
                "Found",
                namespace.get("location"),
                (
                    namespace.get("properties", {}).get(
                        "provisioningState"
                    )
                    if isinstance(namespace.get("properties"), dict)
                    else None
                ),
                (
                    namespace.get("systemData", {}).get("createdBy")
                    if isinstance(namespace.get("systemData"), dict)
                    else None
                ),
            )
            if value
        ),
    )


def _validate_endpoint(
    services,
    renderer,
    endpoint,
    allow_missing,
):
    resource = _validate_endpoint_resource(
        services, renderer, endpoint, allow_missing
    )
    if resource is not None:
        _validate_endpoint_identity(
            services, renderer, endpoint, resource
        )


def _validate_endpoint_resource(
    services,
    renderer,
    endpoint,
    allow_missing,
):
    renderer.phase("Configuration")
    renderer.busy(
        f"validating {endpoint.kind} {endpoint.endpoint_name}…"
    )
    try:
        resource = services.resolve_resource(endpoint)
    except Exception as error:
        if (
            allow_missing
            and endpoint.kind == "software-updates"
            and is_not_found(error)
        ):
            renderer.input_status(
                "Update Instance",
                endpoint.resource_id,
                "Planned",
                "Not found; setup will create it.",
            )
            return None
        raise
    labels = {
        "dps": "DPS",
        "hub": "IoT Hub",
        "software-updates": "Update Instance",
    }
    renderer.input_status(
        labels[endpoint.kind],
        endpoint.resource_id,
        "Satisfied",
        _resource_metadata(resource),
    )
    return resource


def _resource_metadata(resource):
    properties = resource.get("properties", {})
    if not isinstance(properties, dict):
        properties = {}
    sku = resource.get("sku", {})
    if not isinstance(sku, dict):
        sku = {}
    linked_hubs = properties.get("iotHubs") or []
    return " · ".join(
        str(value)
        for value in (
            resource.get("location"),
            sku.get("name"),
            properties.get("provisioningState"),
            (
                f"{len(linked_hubs)} linked hub(s)"
                if linked_hubs
                else None
            ),
            "Found",
        )
        if value
    )


def _validate_endpoint_identity(
    services,
    renderer,
    endpoint,
    resource,
):
    labels = {
        "dps": "DPS",
        "hub": "IoT Hub",
        "software-updates": "Update Instance",
    }
    renderer.busy(
        f"validating {labels[endpoint.kind]} identity…"
    )
    services.principal_for_identity(
        endpoint.identity_type,
        endpoint.user_assigned_identity,
        resource,
    )
    renderer.input_status(
        f"{labels[endpoint.kind]} identity",
        endpoint.user_assigned_identity or "SystemAssigned",
        "Satisfied",
        "Ready",
    )


def _validate_identity(services, renderer, resource_id):
    renderer.phase("Configuration")
    renderer.busy("validating user-assigned identity…")
    services.resolve_uami(resource_id)
    renderer.input_status(
        "Outbound identity",
        resource_id,
        "Satisfied",
        "Found",
    )


def _can_reuse_identity(services, namespace_name, resource_group_name):
    namespace = services.show_namespace(
        namespace_name, resource_group_name
    )
    if namespace is None:
        return False
    try:
        services.namespace_outbound_principal(namespace)
    except (InvalidArgumentValueError, ResourceNotFoundError):
        return False
    return True


def _confirm_setup(renderer, plan, namespace_name):
    while True:
        renderer.confirmation(plan)
        try:
            answer = renderer.prompt(
                f"Apply namespace setup for '{namespace_name}'? "
                "[y/n]: "
            ).casefold()
        except BackRequested:
            renderer.phase("Review")
            renderer.plan(plan)
            try:
                renderer.prompt(
                    "Press Enter to return to Apply, or :back to edit "
                    "Resources and Access: "
                )
            except BackRequested:
                raise ReconfigureRequested() from None
            renderer.phase("Apply")
            continue
        if answer in {"y", "yes"}:
            return
        if answer in {"", "n", "no"}:
            raise WorkflowCancelled()
        renderer.write("Enter y or n. Use :back, :help, or :quit.")


def _prepare_namespace_setup(
    renderer,
    services,
    subscription_id,
    interactive,
    arguments,
):
    request = build_setup_request(
        namespace_name=arguments["namespace_name"],
        resource_group_name=arguments["resource_group_name"],
        subscription_id=subscription_id,
        location=arguments["location"],
        namespace_outbound_identity=arguments[
            "namespace_outbound_identity"
        ],
        dps=arguments["dps"],
        hubs=arguments["hubs"],
        software_updates=arguments["software_updates"],
        complete_connectivity=arguments["complete_connectivity"],
        assign_roles=arguments["assign_roles"],
        config=arguments["config"],
        no_input=arguments["no_input"],
        interactive=interactive,
        prompt=renderer.prompt,
        write=renderer.write,
        validate_resource_group=lambda value: _validate_resource_group(
            services, renderer, value
        ),
        validate_namespace=lambda name, group: _validate_namespace(
            services,
            renderer,
            name,
            group,
            True,
            confirm_create=(
                interactive
                and not arguments["no_input"]
                and not arguments["config"]
                and not arguments["namespace_name"]
            ),
        ),
        validate_endpoint=lambda endpoint, allow_missing: (
            _validate_endpoint(
                services,
                renderer,
                endpoint,
                allow_missing,
            )
        ),
        validate_endpoint_resource=lambda endpoint, allow_missing: (
            _validate_endpoint_resource(
                services,
                renderer,
                endpoint,
                allow_missing,
            )
        ),
        validate_endpoint_identity=lambda endpoint, resource: (
            _validate_endpoint_identity(
                services,
                renderer,
                endpoint,
                resource,
            )
        ),
        validate_identity=lambda resource_id: _validate_identity(
            services,
            renderer,
            resource_id,
        ),
        can_reuse_identity=lambda name, group: _can_reuse_identity(
            services, name, group
        ),
        browse_resources=lambda kind, group: _load_resource_choices(
            renderer,
            {
                "hub": "IoT Hubs",
                "dps": "DPS instances",
                "software-updates": "Software Updates instances",
            }.get(kind, f"{kind} resources"),
            lambda: services.list_link_targets(kind, group),
        ),
        browse_resource_groups=lambda: _load_resource_choices(
            renderer,
            "resource groups",
            services.list_resource_groups,
        ),
        browse_namespaces=lambda group: _load_resource_choices(
            renderer,
            "namespaces",
            lambda: services.list_namespaces(group),
        ),
        probe_status=lambda name, group: _probe_namespace_status(
            services,
            renderer,
            name,
            group,
        ),
        initial_request=arguments.get("initial_request"),
        back_from_resource_group=True,
    )
    renderer.phase("Configuration")
    renderer.resolved_setup(request)
    workflow = NamespaceWorkflow(services)
    plan, items = workflow.plan_setup(request)
    renderer.trust(plan)
    renderer.plan(plan)
    return request, plan, items


def _probe_namespace_status(
    services,
    renderer,
    namespace_name,
    resource_group_name,
):
    if services.show_namespace(
        namespace_name, resource_group_name
    ) is None:
        renderer.input_status(
            "Namespace status",
            namespace_name,
            "Planned",
            "Namespace is staged; readiness will run after apply.",
        )
        return None
    result = NamespaceWorkflow(services).check(
        namespace_name, resource_group_name
    )
    renderer.input_status(
        "Namespace status",
        namespace_name,
        (
            "Satisfied"
            if result["state"] == "Succeeded"
            else "Warning"
        ),
        result["state"],
    )
    return result


def adr_namespace_check(
    cmd,
    namespace_name: Optional[str] = None,
    resource_group_name: Optional[str] = None,
    no_input: bool = False,
    plain: bool = False,
):
    interactive = (
        sys.stdin.isatty() and sys.stderr.isatty() and not no_input
    )
    subscription_id = get_subscription_id(cmd.cli_ctx)
    renderer = WorkflowRenderer(
        "Namespace check",
        plain=plain or _structured_output_requested(cmd),
    )
    services = WorkflowServices(cmd)
    renderer.header(
        subscription_id, resource_group_name, namespace_name
    )
    renderer.journey(
        "Scope", "Resources", "Access", "Results"
    )
    renderer.phase("Scope")
    try:
        renderer.account(services.account_context())
        _validate_subscription(services, renderer, subscription_id)
        namespace_name, resource_group_name = resolve_scope_inputs(
            namespace_name,
            resource_group_name,
            subscription_id=subscription_id,
            no_input=no_input,
            interactive=interactive,
            prompt=renderer.prompt,
            write=renderer.write,
            validate_resource_group=lambda value: _validate_resource_group(
                services, renderer, value
            ),
            validate_namespace=lambda name, group: _validate_namespace(
                services, renderer, name, group, False
            ),
            browse_resource_groups=lambda: _load_resource_choices(
                renderer,
                "resource groups",
                services.list_resource_groups,
            ),
            browse_namespaces=lambda group: _load_resource_choices(
                renderer,
                "namespaces",
                lambda: services.list_namespaces(group),
            ),
        )
    except WorkflowCancelled:
        renderer.cancelled()
        return None
    except Exception as error:
        raise RenderedWorkflowError(error, renderer) from error
    renderer.phase("Resources")
    try:
        with renderer.execution() as progress:
            result = NamespaceWorkflow(
                services, progress=progress
            ).check(
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
            )
    except Exception as error:
        raise RenderedWorkflowError(error, renderer) from error
    renderer.validation(
        result,
        lambda item: item.get("id") in {
            "namespace",
            "namespace-outbound-identity",
        }
        or str(item.get("id", "")).startswith("resource-"),
    )
    renderer.phase("Access")
    renderer.trust(result)
    renderer.phase("Links")
    renderer.validation(
        result,
        lambda item: "-link-" in str(item.get("id", ""))
        or str(item.get("id", "")).endswith("-links"),
    )
    renderer.phase("Results")
    if result["state"] in {"Blocked", "Failed"}:
        blockers = [
            item
            for item in result["items"]
            if item["state"] in {"Blocked", "Failed"}
        ]
        details = "\n".join(
            f"- {item['target']}: {item.get('message', item['state'])}"
            for item in blockers
        )
        error = CLIError(f"Namespace check found blockers:\n{details}")
        raise RenderedWorkflowError(
            CLIError("Namespace check found blockers."),
            renderer,
            result,
        ) from error
    renderer.receipt(result)
    return result


def adr_namespace_setup(
    cmd,
    namespace_name: Optional[str] = None,
    resource_group_name: Optional[str] = None,
    location: Optional[str] = None,
    namespace_outbound_identity: Optional[str] = None,
    dps: Optional[List[str]] = None,
    hubs: Optional[List[List[str]]] = None,
    software_updates: Optional[List[str]] = None,
    complete_connectivity: bool = False,
    assign_roles: Optional[bool] = None,
    manual_rbac: bool = False,
    config: Optional[str] = None,
    no_input: bool = False,
    plan_only: bool = False,
    output_script: Optional[str] = None,
    yes: bool = False,
    plain: bool = False,
):
    interactive = (
        sys.stdin.isatty()
        and sys.stderr.isatty()
        and not no_input
        and not config
    )
    subscription_id = get_subscription_id(cmd.cli_ctx)
    renderer = WorkflowRenderer(
        "Namespace setup",
        plain=(
            plain
            or bool(config)
            or _structured_output_requested(cmd)
        ),
    )
    renderer.header(
        subscription_id, resource_group_name, namespace_name
    )
    renderer.journey(
        "Subscription",
        "Resource group",
        "Namespace",
        "Configuration",
    )
    renderer.phase("Subscription")
    services = WorkflowServices(cmd)
    setup_arguments = {
        "namespace_name": namespace_name,
        "resource_group_name": resource_group_name,
        "location": location,
        "namespace_outbound_identity": namespace_outbound_identity,
        "dps": dps,
        "hubs": hubs,
        "software_updates": software_updates,
        "complete_connectivity": complete_connectivity,
        "assign_roles": (
            False if manual_rbac else assign_roles
        ),
        "config": config,
        "no_input": no_input,
        "initial_request": None,
    }
    try:
        subscription_id, services = _select_subscription(
            cmd,
            renderer,
            services,
            interactive,
            guided=not any(
                (
                    namespace_name,
                    resource_group_name,
                    config,
                    no_input,
                )
            ),
        )
        _validate_subscription(services, renderer, subscription_id)
    except WorkflowCancelled:
        renderer.cancelled()
        return None
    except Exception as error:
        raise RenderedWorkflowError(error, renderer) from error
    while True:
        try:
            request, plan, items = _prepare_namespace_setup(
                renderer,
                services,
                subscription_id,
                interactive,
                setup_arguments,
            )
        except BackRequested:
            renderer.reset_setup()
            try:
                subscription_id, services = _select_subscription(
                    cmd,
                    renderer,
                    services,
                    interactive,
                    guided=True,
                )
                _validate_subscription(
                    services, renderer, subscription_id
                )
            except WorkflowCancelled:
                renderer.cancelled()
                return None
            except Exception as error:
                raise RenderedWorkflowError(
                    error, renderer
                ) from error
            continue
        except WorkflowCancelled:
            renderer.cancelled()
            return None
        except Exception as error:
            raise RenderedWorkflowError(error, renderer) from error
        if output_script:
            missing_commands = [
                item
                for item in items
                if item.state in {"Planned", "Manual"} and not item.command
            ]
            if missing_commands:
                renderer.close()
                raise ArgumentUsageError(
                    "The plan contains operations whose final command cannot "
                    "be resolved yet. Apply prerequisites or rerun setup "
                    "before using --output-script."
                )
            write_script_file(
                output_script,
                [
                    item.command
                    for item in items
                    if item.state in {"Planned", "Manual"} and item.command
                ],
            )
        if plan_only:
            renderer.close()
            return plan
        if plan["state"] == "Blocked":
            error = ArgumentUsageError(
                "Namespace setup is blocked. Resolve the reported items and "
                "rerun."
            )
            raise RenderedWorkflowError(error, renderer, plan) from error
        renderer.phase("Apply")
        if not yes:
            if no_input or not interactive:
                renderer.close()
                raise ArgumentUsageError(
                    "Namespace setup requires confirmation. Pass --yes in a "
                    "non-interactive environment."
                )
            try:
                _confirm_setup(renderer, plan, request.namespace_name)
            except WorkflowCancelled:
                renderer.cancelled()
                return None
            except ReconfigureRequested:
                renderer.reset_setup()
                setup_arguments = {
                    "namespace_name": request.namespace_name,
                    "resource_group_name": request.resource_group_name,
                    "location": request.location,
                    "namespace_outbound_identity": None,
                    "dps": None,
                    "hubs": None,
                    "software_updates": None,
                    "complete_connectivity": False,
                    "assign_roles": request.assign_roles,
                    "config": None,
                    "no_input": False,
                    "initial_request": request,
                }
                continue
        break
    try:
        with renderer.execution() as progress:
            result = NamespaceWorkflow(
                services, progress=progress
            ).setup(request)
    except Exception as error:
        failure_result = getattr(error, "result", plan)
        _persist_receipt(failure_result)
        raise RenderedWorkflowError(
            error,
            renderer,
            failure_result,
        ) from error
    if result["state"] in {"Blocked", "Failed"}:
        _persist_receipt(result)
        error = CLIError(
            "Namespace setup completed with readiness blockers."
        )
        raise RenderedWorkflowError(error, renderer, result) from error
    renderer.phase("Verify")
    _persist_receipt(result)
    renderer.receipt(result)
    return result
