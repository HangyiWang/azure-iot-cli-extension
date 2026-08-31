# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import MagicMock

import pytest
from azure.cli.core.azclierror import (
    ArgumentUsageError,
    InvalidArgumentValueError,
    ResourceNotFoundError,
)

from azext_iot.adr.workflows import namespace as subject
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
    SetupRequest,
)


SUB = "00000000-0000-0000-0000-000000000000"
RG = "test-rg"
NS_ID = (
    f"/subscriptions/{SUB}/resourceGroups/{RG}"
    "/providers/Microsoft.DeviceRegistry/namespaces/ns"
)
HUB_ID = (
    f"/subscriptions/{SUB}/resourceGroups/{RG}"
    "/providers/Microsoft.Devices/IotHubs/hub"
)
DPS_ID = (
    f"/subscriptions/{SUB}/resourceGroups/{RG}"
    "/providers/Microsoft.Devices/provisioningServices/dps"
)
SU_ID = (
    f"/subscriptions/{SUB}/resourceGroups/{RG}"
    "/providers/Microsoft.DeviceUpdate/updateInstances/su"
)


def _namespace(
    outbound=True,
    dps=None,
    hubs=None,
    su=None,
    state="Succeeded",
):
    properties = {
        "provisioningState": state,
        "provisioning": {"endpoints": dps or {}},
        "messaging": {"endpoints": hubs or {}},
        "updating": {"endpoints": su or {}},
    }
    if outbound:
        properties["outboundIdentity"] = {"type": "SystemAssigned"}
    return {
        "id": NS_ID,
        "name": "ns",
        "location": "eastus",
        "identity": {"principalId": "namespace-principal"},
        "properties": properties,
    }


def _endpoint(kind, resource_id, name=None, identity="system-assigned"):
    return EndpointSpec(kind, name or kind, resource_id, identity)


def _link(resource_id, state="Succeeded", identity="SystemAssigned"):
    return {
        "resourceId": resource_id,
        "linkingState": state,
        "inboundCallerIdentity": {"type": identity},
    }


@pytest.fixture
def services():
    service = MagicMock()
    service.namespace_outbound_principal.return_value = "namespace-principal"
    service.principal_for_identity.return_value = "target-principal"
    service.rbac.has_assignment.return_value = True
    service.rbac.can_create_assignments.return_value = True
    return service


def test_private_helpers():
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
    )
    namespace = _namespace()
    assert subject._nested(namespace, "properties", "provisioningState") == "Succeeded"
    assert subject._endpoint_map(namespace, "hub") == {}
    assert subject._normalize_id("/A/") == "/a"
    assert subject._outbound_matches(namespace, request)

    hub = _endpoint("hub", HUB_ID, "primary")
    link = _link(HUB_ID)
    assert subject._link_matches(link, hub)
    assert subject._link_state(link) == "Succeeded"
    spec = subject._link_spec("hub", "primary", link)
    assert spec.endpoint_name == "primary"
    assert spec.identity_type == "system-assigned"

    user_link = _link(HUB_ID, identity="UserAssigned")
    user_link["inboundCallerIdentity"]["userAssignedIdentity"] = "/UAMI"
    user = EndpointSpec("hub", "primary", HUB_ID, "user-assigned", "/uami")
    assert subject._link_matches(user_link, user)
    assert subject._link_spec("hub", "primary", user_link).identity_type == "user-assigned"
    assert not subject._link_matches(_link(DPS_ID), hub)
    assert subject._has_healthy_dps(
        _namespace(dps={"dps": _link(DPS_ID)})
    )
    assert not subject._has_healthy_dps(
        _namespace(dps={"dps": _link(DPS_ID, "Failed")})
    )
    assert subject._outbound_matches(
        namespace, SetupRequest("ns", RG)
    )

    uami_namespace = _namespace()
    uami_namespace["properties"]["outboundIdentity"] = {
        "type": "UserAssigned",
        "userAssignedIdentity": "/UAMI/",
    }
    uami_request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="UserAssigned",
        outbound_user_assigned_identity="/uami",
    )
    assert subject._outbound_matches(uami_namespace, uami_request)


def test_progress_and_failed_state_helpers(services):
    progress = MagicMock()
    progress.run.side_effect = lambda _, operation, *args, **kwargs: operation(
        *args, **kwargs
    )
    workflow = subject.NamespaceWorkflow(services, progress=progress)
    assert workflow._run("show", lambda: "value") == "value"
    progress.run.assert_called_once()

    services.show_namespace.return_value = _namespace(state="Failed")
    result = workflow.check("ns", RG)
    assert result["state"] == STATE_BLOCKED


def test_check_ready_namespace_without_links(services):
    services.show_namespace.return_value = _namespace()
    result = subject.NamespaceWorkflow(services).check("ns", RG)
    assert result["state"] == STATE_SUCCEEDED
    assert result["summary"][STATE_NOT_CONFIGURED] == 3


def test_check_allows_missing_outbound_identity_without_links(services):
    services.show_namespace.return_value = _namespace(outbound=False)
    services.namespace_outbound_principal.side_effect = InvalidArgumentValueError(
        "missing identity"
    )
    result = subject.NamespaceWorkflow(services).check("ns", RG)
    assert result["state"] == STATE_SUCCEEDED
    identity = next(
        item for item in result["items"]
        if item["id"] == "namespace-outbound-identity"
    )
    assert identity["state"] == STATE_NOT_CONFIGURED


def test_check_detects_link_and_missing_role(services):
    services.show_namespace.return_value = _namespace(
        hubs={"primary": _link(HUB_ID)}
    )
    services.resolve_resource.return_value = {
        "id": HUB_ID,
        "identity": {"principalId": "hub-principal"},
    }
    services.rbac.has_assignment.side_effect = [True, False, True]
    result = subject.NamespaceWorkflow(services).check("ns", RG)
    assert result["state"] == STATE_BLOCKED
    assert any(
        item.get("message") == "Required role assignment is missing."
        for item in result["items"]
    )


def test_check_records_warning_and_resource_failure(services):
    services.show_namespace.return_value = _namespace(
        hubs={
            "pending": _link(HUB_ID, "InProgress"),
            "failed": _link(HUB_ID, "Failed"),
        }
    )
    services.resolve_resource.side_effect = [
        {"identity": {"principalId": "hub"}},
        InvalidArgumentValueError("missing"),
    ]
    services.rbac.has_assignment.side_effect = RuntimeError("forbidden")
    result = subject.NamespaceWorkflow(services).check("ns", RG)
    states = {item["state"] for item in result["items"]}
    assert STATE_WARNING in states
    assert STATE_BLOCKED in states
    assert any("Unable to inspect" in item.get("message", "") for item in result["items"])


def test_check_missing_namespace_and_identity(services):
    services.show_namespace.return_value = None
    with pytest.raises(ArgumentUsageError, match="not found"):
        subject.NamespaceWorkflow(services).check("ns", RG)

    services.show_namespace.return_value = _namespace(
        outbound=False,
        dps={"dps": _link(DPS_ID)},
    )
    services.namespace_outbound_principal.side_effect = InvalidArgumentValueError(
        "missing identity"
    )
    result = subject.NamespaceWorkflow(services).check("ns", RG)
    assert result["state"] == STATE_BLOCKED


def test_check_reports_transient_namespace_as_warning(services):
    services.show_namespace.return_value = _namespace(state="Updating")
    result = subject.NamespaceWorkflow(services).check("ns", RG)
    assert result["state"] == STATE_WARNING


def test_plan_setup_missing_namespace_and_manual_roles(services):
    services.show_namespace.return_value = None
    services.resolve_resource.return_value = {
        "identity": {"principalId": "hub"}
    }
    request = SetupRequest(
        "ns",
        RG,
        location="eastus",
        outbound_identity_type="SystemAssigned",
        hubs=(_endpoint("hub", HUB_ID),),
    )
    result, items = subject.NamespaceWorkflow(services).plan_setup(request)
    assert result["state"] == STATE_BLOCKED
    assert any(item.item_id == "namespace" and item.state == STATE_PLANNED for item in items)
    assert "--location eastus" in items[0].command
    assert items[0].details["location"] == "eastus"
    identity = next(
        item
        for item in items
        if item.item_id == "namespace-outbound-identity"
    )
    assert identity.details["identityType"] == "SystemAssigned"
    assert any(item.item_id == "hub-prerequisite" for item in items)
    assert any(item.state == STATE_PLANNED for item in items)


def test_plan_setup_blocks_new_namespace_links_without_identity(services):
    services.show_namespace.return_value = None
    services.resolve_resource.return_value = {
        "identity": {"principalId": "dps"}
    }
    request = SetupRequest(
        "ns",
        RG,
        dps=_endpoint("dps", DPS_ID),
    )
    result, items = subject.NamespaceWorkflow(services).plan_setup(request)
    identity = next(
        item
        for item in items
        if item.item_id == "namespace-outbound-identity"
    )
    assert result["state"] == STATE_BLOCKED
    assert identity.state == STATE_BLOCKED
    assert "requires an outbound identity" in identity.message


def test_plan_setup_rejects_duplicate_endpoint_names(services):
    services.show_namespace.return_value = _namespace()
    request = SetupRequest(
        "ns",
        RG,
        dps=EndpointSpec(
            "dps", "same", DPS_ID, "system-assigned"
        ),
        hubs=(
            EndpointSpec(
                "hub", "same", HUB_ID, "system-assigned"
            ),
        ),
    )
    with pytest.raises(ArgumentUsageError, match="must be unique"):
        subject.NamespaceWorkflow(services).plan_setup(request)


def test_plan_setup_records_skipped_and_status_items(services):
    services.show_namespace.return_value = _namespace()
    request = SetupRequest(
        "ns",
        RG,
        skipped=("dps", "software-updates"),
        check_status=True,
    )
    result, items = subject.NamespaceWorkflow(services).plan_setup(request)
    assert result["state"] == STATE_SUCCEEDED
    assert {
        item.item_id for item in items if item.action == "skip"
    } == {"skip-dps", "skip-software-updates"}
    assert any(item.item_id == "namespace-status" for item in items)


def test_plan_warns_for_dps_hubs_not_linked_in_run(services):
    services.show_namespace.return_value = _namespace()
    services.resolve_resource.return_value = {
        "properties": {
            "iotHubs": [
                {"hostName": "selected.azure-devices.net"},
                {"hostName": "not-linked.azure-devices.net"},
            ]
        },
        "identity": {"principalId": "dps"},
    }
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
        hubs=(
            _endpoint(
                "hub",
                HUB_ID.replace("/hub", "/selected"),
            ),
        ),
    )
    services.resolve_resource.side_effect = [
        {
            "properties": {
                "iotHubs": [
                    {"hostName": "selected.azure-devices.net"},
                    {"hostName": "not-linked.azure-devices.net"},
                ]
            },
            "identity": {"principalId": "dps"},
        },
        {"identity": {"principalId": "hub"}},
    ]
    _, items = subject.NamespaceWorkflow(services).plan_setup(request)
    warning = next(
        item
        for item in items
        if item.item_id == "dps-allocation-warning"
    )
    assert warning.state == STATE_WARNING
    assert "not-linked" in warning.message
    assert "selected.azure-devices.net" not in warning.message


def test_setup_runs_selected_status_probe(services, mocker):
    namespace = _namespace()
    services.show_namespace.return_value = namespace
    workflow = subject.NamespaceWorkflow(services)
    check = mocker.patch.object(
        workflow,
        "check",
        return_value={"state": STATE_SUCCEEDED},
    )
    result = workflow.setup(
        SetupRequest("ns", RG, check_status=True)
    )
    check.assert_called_once_with("ns", RG)
    assert any(
        item["id"] == "namespace-status"
        for item in result["items"]
    )


def test_setup_propagates_blocked_selected_status(services, mocker):
    services.show_namespace.return_value = _namespace()
    workflow = subject.NamespaceWorkflow(services)
    mocker.patch.object(
        workflow,
        "check",
        return_value={"state": STATE_BLOCKED},
    )
    result = workflow.setup(
        SetupRequest("ns", RG, check_status=True)
    )
    assert result["state"] == STATE_BLOCKED


def test_manual_rbac_still_runs_selected_status(services, mocker):
    services.show_namespace.return_value = _namespace(
        dps={"dps": _link(DPS_ID)}
    )
    services.resolve_resource.return_value = {
        "identity": {"principalId": "dps"}
    }
    services.rbac.has_assignment.return_value = False
    workflow = subject.NamespaceWorkflow(services)
    mocker.patch.object(
        workflow,
        "check",
        return_value={"state": STATE_BLOCKED},
    )
    result = workflow.setup(
        SetupRequest(
            "ns",
            RG,
            dps=_endpoint("dps", DPS_ID),
            assign_roles=False,
            check_status=True,
        )
    )
    assert result["state"] == STATE_BLOCKED
    assert result["resumeCommand"]


def test_identity_refresh_failure_keeps_successful_mutation(services):
    services.show_namespace.side_effect = [
        _namespace(outbound=False),
        _namespace(outbound=False),
        RuntimeError("refresh failed"),
    ]
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
    )
    with pytest.raises(
        subject.WorkflowExecutionError, match="refresh failed"
    ) as raised:
        subject.NamespaceWorkflow(services).setup(request)
    assert any(
        item["id"] == "namespace-outbound-identity"
        and item["state"] == STATE_SUCCEEDED
        for item in raised.value.result["items"]
    )


def test_link_wait_failure_keeps_submitted_action(services):
    namespace = _namespace(dps={"dps": _link(DPS_ID)})
    services.show_namespace.return_value = namespace
    services.resolve_resource.return_value = {
        "identity": {"principalId": "hub"}
    }
    services.rbac.has_assignment.return_value = True
    services.wait_for_link.side_effect = RuntimeError("wait failed")
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        hubs=(_endpoint("hub", HUB_ID),),
    )
    with pytest.raises(
        subject.WorkflowExecutionError, match="wait failed"
    ) as raised:
        subject.NamespaceWorkflow(services).setup(request)
    assert any(
        item["id"].startswith("link-hub-")
        and item["state"] == STATE_SUCCEEDED
        for item in raised.value.result["items"]
    )


def test_plan_setup_matching_and_conflicting_links(services):
    matching = _namespace(
        dps={"dps": _link(DPS_ID)},
        hubs={"hub": _link(HUB_ID)},
    )
    services.show_namespace.return_value = matching
    services.resolve_resource.side_effect = [
        {"identity": {"principalId": "dps"}},
        {"identity": {"principalId": "hub"}},
    ]
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
        hubs=(_endpoint("hub", HUB_ID),),
        assign_roles=True,
    )
    result, items = subject.NamespaceWorkflow(services).plan_setup(request)
    assert result["state"] == STATE_SUCCEEDED
    assert sum(item.state == STATE_SATISFIED for item in items) >= 4

    conflicting = _namespace(
        dps={"other": _link("/different")},
        hubs={"hub": _link("/different")},
    )
    services.show_namespace.return_value = conflicting
    services.resolve_resource.side_effect = None
    services.resolve_resource.return_value = {
        "identity": {"principalId": "target"}
    }
    result, _ = subject.NamespaceWorkflow(services).plan_setup(request)
    assert result["state"] == STATE_BLOCKED


def test_plan_setup_blocks_failed_dps_prerequisite(services):
    services.show_namespace.return_value = _namespace(
        dps={"dps": _link(DPS_ID, "Failed")}
    )
    services.resolve_resource.return_value = {
        "identity": {"principalId": "hub"}
    }
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        hubs=(_endpoint("hub", HUB_ID),),
    )
    result, _ = subject.NamespaceWorkflow(services).plan_setup(request)
    assert result["state"] == STATE_BLOCKED


def test_plan_setup_blocks_unready_namespace(services):
    services.show_namespace.return_value = _namespace(state="Failed")
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
    )
    result, items = subject.NamespaceWorkflow(services).plan_setup(request)
    assert result["state"] == STATE_BLOCKED
    assert items[0].item_id == "namespace"
    assert "Wait for Succeeded" in items[0].message


def test_plan_setup_allows_planned_update_instance(services):
    services.show_namespace.return_value = _namespace()
    services.resolve_resource.side_effect = ResourceNotFoundError("missing")
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        software_updates=_endpoint("software-updates", SU_ID),
        create_update_instance=True,
    )
    result, items = subject.NamespaceWorkflow(services).plan_setup(request)
    assert result["state"] == STATE_PLANNED
    assert any(item.action == "create" for item in items)


def test_plan_setup_propagates_resource_failure(services):
    services.show_namespace.return_value = _namespace()
    services.resolve_resource.side_effect = RuntimeError("service unavailable")
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
    )
    with pytest.raises(RuntimeError, match="service unavailable"):
        subject.NamespaceWorkflow(services).plan_setup(request)


def test_plan_setup_records_role_planning_failure(services):
    services.show_namespace.return_value = _namespace(
        dps={"dps": _link(DPS_ID)}
    )
    services.resolve_resource.return_value = {
        "identity": {"principalId": "dps"}
    }
    services.namespace_outbound_principal.side_effect = RuntimeError("identity")
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
    )
    result, _ = subject.NamespaceWorkflow(services).plan_setup(request)
    assert result["state"] == STATE_BLOCKED


def test_plan_setup_role_states(services):
    namespace = _namespace(dps={"dps": _link(DPS_ID)})
    services.show_namespace.return_value = namespace
    services.resolve_resource.return_value = {
        "identity": {"principalId": "dps"}
    }
    services.rbac.has_assignment.side_effect = [True, False]
    services.rbac.can_create_assignments.return_value = False
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
        assign_roles=True,
    )
    result, items = subject.NamespaceWorkflow(services).plan_setup(request)
    assert result["state"] == STATE_MANUAL
    assert any(item.state == STATE_MANUAL for item in items)
    role_index = next(
        index for index, item in enumerate(items)
        if item.item_id.startswith("role-")
    )
    link_index = next(
        index for index, item in enumerate(items)
        if item.item_id.startswith("link-")
    )
    assert role_index < link_index


def test_check_skips_roles_without_outbound_principal(services):
    services.show_namespace.return_value = _namespace(
        outbound=False,
        dps={"dps": _link(DPS_ID)},
    )
    services.namespace_outbound_principal.side_effect = InvalidArgumentValueError(
        "missing"
    )
    services.resolve_resource.return_value = {
        "identity": {"principalId": "dps"}
    }
    result = subject.NamespaceWorkflow(services).check("ns", RG)
    assert result["state"] == STATE_BLOCKED
    services.rbac.has_assignment.assert_not_called()


def test_setup_rejects_blocked_plan(services):
    services.show_namespace.return_value = _namespace()
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        hubs=(_endpoint("hub", HUB_ID),),
    )
    with pytest.raises(ArgumentUsageError, match="DPS"):
        subject.NamespaceWorkflow(services).setup(request)


def test_setup_creates_namespace_and_configures_identity(services):
    created = _namespace(outbound=False)
    configured = _namespace()
    services.show_namespace.side_effect = [None, None, created, configured]
    services.create_namespace.return_value = created
    services.configure_outbound_identity.return_value = configured
    request = SetupRequest(
        "ns",
        RG,
        location="eastus",
        outbound_identity_type="SystemAssigned",
    )
    result = subject.NamespaceWorkflow(services).setup(request)
    assert result["state"] == STATE_SUCCEEDED
    services.create_namespace.assert_called_once()
    services.configure_outbound_identity.assert_called_once()


def test_setup_returns_manual_when_roles_missing(services):
    namespace = _namespace(dps={"dps": _link(DPS_ID)})
    services.show_namespace.return_value = namespace
    services.resolve_resource.return_value = {
        "identity": {"principalId": "dps"}
    }
    services.rbac.has_assignment.return_value = False
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
        assign_roles=False,
    )
    result = subject.NamespaceWorkflow(services).setup(request)
    assert result["state"] == STATE_MANUAL
    assert "--dps" in result["resumeCommand"]
    assert f"resource-id={DPS_ID}" in result["resumeCommand"]
    assert result["resumeCommand"].endswith("--yes")
    services.add_dps.assert_not_called()


def test_resume_command_preserves_all_setup_inputs():
    request = SetupRequest(
        "ns",
        RG,
        subscription_id=SUB,
        location="eastus",
        outbound_identity_type="UserAssigned",
        outbound_user_assigned_identity="/uami",
        dps=_endpoint("dps", DPS_ID),
        hubs=(
            EndpointSpec(
                "hub",
                "weighted",
                HUB_ID,
                "user-assigned",
                "/hub-uami",
                availability="Available",
                allocation_weight=5,
            ),
        ),
        software_updates=_endpoint("software-updates", SU_ID),
        manual_rbac=True,
    )
    command = subject.NamespaceWorkflow._resume_command(request)
    assert "--location eastus" in command
    assert f"--subscription {SUB}" in command
    assert "--outbound-identity /uami" in command
    assert "--dps" in command and "--hub" in command and "--su" in command
    assert "availability=Available" in command
    assert "allocation-weight=5" in command
    assert "--manual-rbac" in command


def test_setup_assigns_roles_and_bundles_links(services):
    initial = _namespace()
    linked = _namespace(
        dps={"dps": _link(DPS_ID)},
        hubs={"hub": _link(HUB_ID)},
    )
    services.show_namespace.side_effect = [initial, initial, initial, linked]
    services.resolve_resource.side_effect = [
        {"identity": {"principalId": "dps"}},
        {"identity": {"principalId": "hub"}},
        {"identity": {"principalId": "dps"}},
        {"identity": {"principalId": "hub"}},
    ]
    services.rbac.has_assignment.side_effect = [False] * 10
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
        hubs=(_endpoint("hub", HUB_ID),),
        assign_roles=True,
    )
    result = subject.NamespaceWorkflow(services).setup(request)
    assert result["state"] == STATE_SUCCEEDED
    services.add_dps_and_hub.assert_called_once()
    services.add_dps.assert_not_called()
    services.wait_for_link.assert_any_call("ns", RG, "provisioning", "dps")
    services.wait_for_link.assert_any_call("ns", RG, "messaging", "hub")
    services.sleep.assert_called_with(subject.ROLE_PROPAGATION_WAIT_SECONDS)


def test_setup_applies_individual_existing_and_su_links(services):
    namespace = _namespace(
        dps={"dps": _link(DPS_ID)},
        hubs={"hub": _link(HUB_ID, "InProgress")},
    )
    services.show_namespace.return_value = namespace
    services.resolve_resource.side_effect = [
        {"identity": {"principalId": "hub"}},
        {"identity": {"principalId": "su"}},
        {"identity": {"principalId": "hub"}},
        {"identity": {"principalId": "su"}},
    ]
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        hubs=(_endpoint("hub", HUB_ID),),
        software_updates=_endpoint("software-updates", SU_ID),
        assign_roles=True,
    )
    result = subject.NamespaceWorkflow(services).setup(request)
    assert result["state"] == STATE_SUCCEEDED
    services.add_hub.assert_not_called()
    services.add_su.assert_called_once()
    services.wait_for_link.assert_any_call("ns", RG, "messaging", "hub")


def test_setup_creates_missing_update_instance(services):
    namespace = _namespace()
    services.show_namespace.return_value = namespace
    services.resolve_resource.side_effect = [
        ResourceNotFoundError("missing"),
        ResourceNotFoundError("missing"),
    ]
    services.create_update_instance.return_value = {
        "identity": {"principalId": "su"}
    }
    services.rbac.has_assignment.side_effect = [True, True, False]
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        software_updates=_endpoint("software-updates", SU_ID),
        create_update_instance=True,
    )
    result = subject.NamespaceWorkflow(services).setup(request)
    assert result["state"] == STATE_MANUAL
    services.create_update_instance.assert_called_once()


def test_setup_propagates_non_su_resource_failure(services):
    services.show_namespace.return_value = _namespace()
    services.resolve_resource.side_effect = RuntimeError("lookup failed")
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
    )
    with pytest.raises(RuntimeError, match="lookup failed"):
        subject.NamespaceWorkflow(services).setup(request)


def test_setup_reports_partial_state_on_apply_failure(services):
    services.show_namespace.return_value = _namespace()
    resource = {"identity": {"principalId": "dps"}}
    services.resolve_resource.side_effect = [
        resource,
        RuntimeError("apply lookup failed"),
    ]
    request = SetupRequest(
        "ns",
        RG,
        dps=_endpoint("dps", DPS_ID),
    )
    with pytest.raises(
        subject.WorkflowExecutionError, match="apply lookup failed"
    ) as raised:
        subject.NamespaceWorkflow(services).setup(request)
    assert raised.value.result["state"] == STATE_FAILED
    assert raised.value.result["items"][-1]["state"] == STATE_FAILED


def test_setup_returns_manual_when_caller_cannot_assign(services):
    namespace = _namespace(dps={"dps": _link(DPS_ID)})
    services.show_namespace.return_value = namespace
    services.resolve_resource.return_value = {
        "identity": {"principalId": "dps"}
    }
    services.rbac.has_assignment.return_value = False
    services.rbac.can_create_assignments.return_value = False
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
        assign_roles=True,
    )
    result = subject.NamespaceWorkflow(services).setup(request)
    assert result["state"] == STATE_MANUAL
    services.rbac.create_assignment.assert_not_called()


def test_setup_adds_individual_dps_before_existing_hubs(services):
    namespace = _namespace(hubs={"existing": _link(HUB_ID)})
    linked = _namespace(
        dps={"dps": _link(DPS_ID)},
        hubs={"existing": _link(HUB_ID)},
    )
    services.show_namespace.side_effect = [namespace, namespace, namespace, linked]
    services.resolve_resource.side_effect = [
        {"identity": {"principalId": "dps"}},
        {"identity": {"principalId": "dps"}},
    ]
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
        assign_roles=True,
    )
    result = subject.NamespaceWorkflow(services).setup(request)
    assert result["state"] == STATE_SUCCEEDED
    services.add_dps.assert_called_once()


def test_setup_preserves_existing_first_hub_when_adding_dps(services):
    namespace = _namespace(
        hubs={"hub": _link(HUB_ID, "InProgress")}
    )
    linked = _namespace(
        dps={"dps": _link(DPS_ID)},
        hubs={"hub": _link(HUB_ID, "InProgress")},
    )
    services.show_namespace.side_effect = [
        namespace,
        namespace,
        namespace,
        linked,
    ]
    services.resolve_resource.side_effect = [
        {"identity": {"principalId": "dps"}},
        {"identity": {"principalId": "hub"}},
        {"identity": {"principalId": "dps"}},
        {"identity": {"principalId": "hub"}},
    ]
    request = SetupRequest(
        "ns",
        RG,
        outbound_identity_type="SystemAssigned",
        dps=_endpoint("dps", DPS_ID),
        hubs=(_endpoint("hub", HUB_ID),),
        assign_roles=True,
    )
    result = subject.NamespaceWorkflow(services).setup(request)
    assert result["state"] == STATE_SUCCEEDED
    services.add_dps.assert_called_once()
    services.wait_for_link.assert_any_call("ns", RG, "messaging", "hub")


def test_apply_one_link_dispatches_all_kinds(services):
    workflow = subject.NamespaceWorkflow(services)
    request = SetupRequest("ns", RG)
    items = []
    for endpoint, method in (
        (_endpoint("dps", DPS_ID), services.add_dps),
        (_endpoint("hub", HUB_ID), services.add_hub),
        (_endpoint("software-updates", SU_ID), services.add_su),
    ):
        workflow._apply_one_link(request, endpoint, {}, items)
        method.assert_called_once()
    assert len(items) == 3


def test_role_helpers_and_endpoint_iteration(services):
    workflow = subject.NamespaceWorkflow(services)
    su = _endpoint("software-updates", SU_ID)
    roles = workflow._roles_for(
        su, _namespace(), "namespace-principal", "su-principal"
    )
    services.rbac.resolve_service_principal.assert_called_once_with(
        subject.ADU_FIRST_PARTY_APPLICATION_ID
    )
    assert any(role.get("manual") for role in roles)
    assert "role assignment create" in workflow._role_command(roles[0])

    request = SetupRequest(
        "ns",
        RG,
        dps=_endpoint("dps", DPS_ID),
        hubs=(_endpoint("hub", HUB_ID),),
        software_updates=su,
    )
    assert [item.kind for item in workflow._requested_endpoints(request)] == [
        "dps",
        "hub",
        "software-updates",
    ]
    command = workflow._link_command(
        request,
        EndpointSpec(
            "hub",
            "hub",
            HUB_ID,
            "user-assigned",
            "/uami",
            availability="Available",
            allocation_weight=5,
        ),
    )
    assert "--mi-user-assigned /uami" in command
    assert "--allocation-weight 5" in command

    injected = workflow._link_command(
        SetupRequest("ns; echo bad", "rg"),
        EndpointSpec(
            "hub",
            "safe; echo bad",
            "/subscriptions/s/resourceGroups/r/providers/"
            "Microsoft.Devices/IotHubs/hub",
            "system-assigned",
        ),
    )
    assert "'safe; echo bad'" in injected
    assert "'ns; echo bad'" in injected
