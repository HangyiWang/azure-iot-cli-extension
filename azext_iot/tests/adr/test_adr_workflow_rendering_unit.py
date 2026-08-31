# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from dataclasses import replace
from io import StringIO
from unittest.mock import MagicMock

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document
from rich.console import Console

from azext_iot.adr.workflows import rendering as subject
from azext_iot.adr.workflows.models import EndpointSpec, SetupRequest


def _console(stream, force_terminal=False):
    return Console(
        file=stream,
        force_terminal=force_terminal,
        color_system="standard" if force_terminal else None,
        theme=subject._THEME,
        width=100,
    )


def _request():
    return SetupRequest(
        "ns",
        "rg",
        outbound_identity_type="SystemAssigned",
        dps=EndpointSpec(
            "dps", "primary", "/subscriptions/s/dps", "system-assigned"
        ),
        hubs=(
            EndpointSpec(
                "hub",
                "primary",
                "/subscriptions/s/hub",
                "user-assigned",
                "/subscriptions/s/uami",
            ),
        ),
        assign_roles=True,
    )


def _plan():
    return {
        "state": "Planned",
        "summary": {
            "Satisfied": 1,
            "Planned": 2,
            "Manual": 1,
            "Blocked": 1,
        },
        "items": [
            {
                "id": "namespace",
                "state": "Planned",
                "action": "create",
                "target": "ns",
                "details": {"location": "eastus"},
            },
            {
                "id": "resource-hub-primary",
                "state": "Planned",
                "action": "validate",
                "target": "hub",
                "message": "exact GET",
            },
            {
                "id": "role-hub-namespace-access",
                "state": "Manual",
                "action": "grant",
                "target": "/hub",
                "command": "az role assignment create",
                "details": {
                    "principalId": "principal",
                    "role": "Contributor",
                },
            },
            {
                "id": "link-hub-primary",
                "state": "Blocked",
                "action": "link",
                "target": "hub",
                "message": "missing role",
            },
            {
                "id": "unknown",
                "state": "Unknown",
                "action": "verify",
                "target": "hub",
            },
        ],
    }


def test_plain_renderer_outputs_all_views(mocker):
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        plain=True,
        console=_console(stream),
    )
    mocker.patch("builtins.input", return_value="answer")
    assert renderer.prompt("Value: ") == "answer"
    renderer.write("message")
    renderer.header("sub", "rg", "ns")
    renderer.journey("Prepare", "Resources", "Access")
    renderer.phase("Prepare")
    renderer.input_status("Subscription", "sub", "Satisfied", "Found")
    renderer.input_status("Namespace", "ns", "Satisfied", "Found")
    renderer.phase("Prepare")
    renderer.phase("Resources")
    renderer.input_status("Resource group", "rg", "Satisfied", "Found")
    renderer.resolved_setup(_request())
    renderer.resolved_setup(
        replace(
            _request(),
            software_updates=EndpointSpec(
                "software-updates",
                "updates",
                "/subscriptions/s/updateInstances/updates",
                "system-assigned",
            ),
        )
    )
    renderer.validation(_plan())
    renderer.trust(_plan())
    renderer.plan(_plan())
    renderer.confirmation(_plan())
    renderer.receipt({
        "namespace": "ns",
        "state": "Succeeded",
        "summary": {"Succeeded": 2},
    })
    renderer.error(RuntimeError("failed"), _plan())
    output = stream.getvalue()
    assert "Azure Device Registry" in output
    assert output.count(">> Prepare") == 1
    assert "Resolved setup" in output
    assert "Identity and permissions" in output
    assert "[satisfied]" in output
    assert "Create namespace: ns" in output
    assert "Location: eastus" in output
    assert "Configure IoT Hub link: hub" in output
    assert "Apply namespace setup?" in output
    assert "Namespace setup complete" in output
    assert "Fix: az role assignment create" in output


def test_plain_execution_reports_success_and_failure():
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        plain=True,
        console=_console(stream),
    )
    original_quiet = subject.provider_console.quiet
    with renderer.execution() as execution:
        assert subject.provider_console.quiet is True
        assert execution.run("Successful", lambda: "result") == "result"
        with pytest.raises(RuntimeError, match="boom"):
            execution.run(
                "Failed", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
            )
    assert subject.provider_console.quiet is original_quiet
    output = stream.getvalue()
    assert "[running] Successful" in output
    assert "[done] Successful" in output
    assert "[failed] Failed" in output


def test_rich_execution_and_symbols():
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(stream, force_terminal=True),
    )
    assert renderer.rich
    renderer.header("sub", "rg", "ns")
    renderer.journey("Prepare", "Resources", "Access")
    renderer.phase("Prepare")
    renderer.input_status("Subscription", "sub", "Satisfied", "Found")
    renderer.input_status("Namespace", "ns", "Satisfied", "Found")
    request = replace(
        _request(),
        software_updates=EndpointSpec(
            "software-updates",
            "updates",
            "/subscriptions/s/updateInstances/updates",
            "system-assigned",
        ),
    )
    renderer.resolved_setup(request)
    renderer.phase("Resources")
    workspace = renderer._workspace_ansi("")
    assert "Software Updates" in workspace
    renderer.validation(_plan())
    renderer.trust(_plan())
    assert renderer._plan == _plan()
    renderer.plan(_plan())
    renderer.confirmation(_plan())
    renderer.receipt({
        "namespace": "ns",
        "state": "Warning",
        "summary": {"Warning": 1},
    })
    renderer.error(RuntimeError("failed"), _plan())
    with renderer.execution() as execution:
        assert execution.run("Successful", lambda: 1) == 1
        with pytest.raises(ValueError):
            execution.run(
                "Failed", lambda: (_ for _ in ()).throw(ValueError("bad"))
            )
    output = stream.getvalue()
    assert "✓" in output
    assert "Successful" in output
    assert "Failed" in output
    assert "step 2/3" in output
    assert "Resources" in output


def test_prompt_navigation_commands(mocker):
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        plain=True,
        console=_console(stream),
    )
    mocker.patch("builtins.input", side_effect=[":help", "value"])
    assert renderer.prompt("Input: ") == "value"
    assert ":back previous input" in stream.getvalue()

    mocker.patch("builtins.input", return_value=":back")
    with pytest.raises(subject.BackRequested):
        renderer.prompt("Input: ")

    mocker.patch("builtins.input", return_value=":quit")
    with pytest.raises(subject.WorkflowCancelled):
        renderer.prompt("Input: ")


def test_rich_renderer_escapes_dynamic_markup():
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(stream, force_terminal=True),
    )
    renderer.write("Validation failed: bad [value] [/]")
    renderer.input_status(
        "IoT Hub",
        "hub[value]",
        "Blocked",
        "bad [/]",
    )
    renderer.resolved_setup(
        SetupRequest("ns[value]", "rg[/]")
    )
    output = renderer._workspace().plain
    assert "[value]" in output
    assert "[/]" in output
    assert "[y/n]" in renderer._workspace_ansi(
        "Apply namespace setup? [y/n]: "
    )


def test_rich_prompt_reuses_workspace(mocker):
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(stream, force_terminal=True),
    )
    renderer.header("sub", None, None)
    renderer.journey("Prepare", "Resources")
    renderer.phase("Prepare")
    renderer.write("Configure")
    renderer.write("  1  Namespace identity")
    live_class = mocker.patch.object(subject, "Live")
    prompt = mocker.patch.object(
        renderer._prompt_session,
        "prompt",
        side_effect=[":help", "1"],
    )
    assert renderer.prompt("Selection: ") == "1"
    assert prompt.call_count == 2
    assert prompt.call_args.kwargs["bottom_toolbar"]
    assert stream.getvalue() == ""
    live_class.return_value.start.assert_called_once_with(refresh=True)
    assert renderer._body.count(
        ":back previous input  ·  :help commands  ·  :quit cancel"
    ) == 1

    renderer.write("Selected: Namespace identity")
    assert renderer._body == []
    live_class.return_value.update.assert_called()
    renderer.close()
    live_class.return_value.stop.assert_called_once()


def test_rich_selection_supports_number_and_clears_menu(mocker):
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    prompt = mocker.patch.object(
        renderer, "_prompt", return_value="2"
    )
    selected = renderer.select(
        "Resources",
        {
            "one": ("one", "First"),
            "two": ("two", "Second"),
        },
    )
    assert selected == "two"
    assert renderer._body == []
    assert prompt.call_args.kwargs["completer"]

    prompt.side_effect = ["invalid", "q"]
    with pytest.raises(subject.WorkflowCancelled):
        renderer.select(
            "Resources", {"one": ("one", "First")}
        )

    prompt.side_effect = None
    prompt.return_value = "Exact-Resource"
    assert renderer.select(
        "Resource",
        {"one": ("one", "First")},
        guidance="Type a name or ARM ID.",
        allow_custom=True,
    ) == "Exact-Resource"


def test_configuration_selection_shows_all_options(mocker):
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    renderer.header("sub", "rg", "ns")
    renderer.journey(
        "Subscription",
        "Resource group",
        "Namespace",
        "Configuration",
    )
    renderer.phase("Configuration")
    snapshots = []

    def prompt(*_, **__):
        snapshots.append(renderer._workspace().plain)
        return "done"

    mocker.patch.object(renderer, "_prompt", side_effect=prompt)
    assert renderer.select(
        "Configuration — every item is optional",
        {
            "identity": ("identity", "Outbound identity          pending"),
            "hub": ("hub", "Link IoT Hub               pending"),
            "done": ("done", "Done → review plan"),
        },
    ) == "done"
    assert "1  Outbound identity" in snapshots[0]
    assert "2  Link IoT Hub" in snapshots[0]
    assert "3  Done → review plan" in snapshots[0]
    assert snapshots[0].index("Namespace") < snapshots[0].index(
        "Workflow  ─"
    )
    assert snapshots[0].index("Workflow  ─") < snapshots[0].index(
        "Configuration —"
    )


def test_prompt_reserves_space_for_completions_below_input(mocker):
    session = mocker.patch.object(subject, "PromptSession")
    subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    assert session.call_args.kwargs["reserve_space_for_menu"] == 8


def test_plain_selection_prints_choices(mocker):
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup", plain=True, console=_console(stream)
    )
    mocker.patch("builtins.input", return_value="1")
    assert renderer.select(
        "Resources", {"one": ("one", "First")}
    ) == "one"
    assert "1  First" in stream.getvalue()


def test_resource_choices_hidden_until_filtering():
    base = subject.FuzzyWordCompleter(["hub-one", "hub-two"])
    completer = subject.InputFilteredCompleter(base)
    assert list(
        completer.get_completions(
            Document(""), CompleteEvent()
        )
    ) == []
    completions = list(
        completer.get_completions(
            Document("one"), CompleteEvent()
        )
    )
    assert any(item.text == "hub-one" for item in completions)


def test_picker_has_one_completion_per_resource(mocker):
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    captured = {}

    def prompt(*_, **kwargs):
        captured["completer"] = kwargs["completer"]
        captured["workspace"] = renderer._workspace().plain
        return "adr-vnext-scale-rg-10"

    mocker.patch.object(renderer, "_prompt", side_effect=prompt)
    assert renderer.select(
        "Resource group",
        {
            "one": (
                "adr-vnext-scale-rg-10",
                "adr-vnext-scale-rg-10 · centraluseuap",
                "adr-vnext-scale-rg-10",
            )
        },
        allow_custom=True,
        show_options=False,
    ) == "adr-vnext-scale-rg-10"
    completions = list(
        captured["completer"].get_completions(
            Document("adr-vnext"), CompleteEvent()
        )
    )
    assert len(completions) == 1
    assert completions[0].text == (
        "adr-vnext-scale-rg-10 · centraluseuap"
    )
    assert "1  adr-vnext-scale-rg-10" not in captured["workspace"]


def test_picker_keybindings_do_not_traverse_history():
    event = MagicMock()
    buffer = event.current_buffer
    buffer.complete_state = None
    buffer.text = ""
    subject.WorkflowRenderer._up_key(event)
    subject.WorkflowRenderer._down_key(event)
    buffer.start_completion.assert_not_called()
    buffer.history_backward.assert_not_called()

    buffer.text = "hub"
    subject.WorkflowRenderer._up_key(event)
    subject.WorkflowRenderer._down_key(event)
    assert buffer.start_completion.call_count == 2

    buffer.complete_state = object()
    subject.WorkflowRenderer._up_key(event)
    subject.WorkflowRenderer._down_key(event)
    buffer.complete_previous.assert_called_once()
    buffer.complete_next.assert_called_once()

    subject.WorkflowRenderer._back_key(event)
    assert buffer.text == ":back"
    buffer.validate_and_handle.assert_called_once()


def test_validation_error_stays_with_visible_actions(mocker):
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    renderer.write("Validation failed: resource not found")
    snapshots = []

    def prompt(*_, **__):
        snapshots.append(renderer._workspace().plain)
        return "2"

    mocker.patch.object(renderer, "_prompt", side_effect=prompt)
    assert renderer.select(
        "Next action",
        {
            "retry": ("retry", "Retry"),
            "edit": ("edit", "Edit input"),
            "quit": ("quit", "Quit"),
        },
    ) == "edit"
    assert "Validation failed: resource not found" in snapshots[0]
    assert "1  Retry" in snapshots[0]
    assert "2  Edit input" in snapshots[0]
    assert "3  Quit" in snapshots[0]


def test_busy_status_and_step_bar_follow_scope():
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    renderer.journey(
        "Subscription",
        "Resource group",
        "Namespace",
        "Configuration",
    )
    renderer.phase("Resource group")
    renderer.input_status("Subscription", "sub", "Satisfied", "Found")
    renderer.busy("validating resource group…")
    workspace = renderer._workspace()
    output = workspace.plain
    assert output.index("subscription") < output.index("step 2/4")
    assert "Subscription  →  Resource group  →  Namespace" in output
    assert "⠋ validating resource group" in output
    for token in ("⠋", ":back", ":help", ":quit"):
        offset = output.index(token)
        assert any(
            span.start <= offset < span.end and span.style == "active"
            for span in workspace.spans
        )
    renderer.idle()
    assert renderer._busy is None
    renderer.close()


def test_subphases_map_to_real_steps():
    setup = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    setup.journey(
        "Subscription", "Resource group", "Namespace", "Configuration"
    )
    setup.phase("Apply")
    assert setup._active_stage() == "Configuration"

    check = subject.WorkflowRenderer(
        "Namespace check",
        console=_console(StringIO(), force_terminal=True),
    )
    check.journey("Scope", "Resources", "Access", "Results")
    check.phase("Subscription")
    assert check._active_stage() == "Scope"
    check.phase("Links")
    assert check._active_stage() == "Results"


def test_rich_prompt_hands_visible_card_to_next_prompt(mocker):
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    live_class = mocker.patch.object(subject, "Live")
    mocker.patch.object(
        renderer._prompt_session,
        "prompt",
        side_effect=["first", "second"],
    )
    assert renderer.prompt("First: ") == "first"
    first_live = live_class.return_value
    renderer.input_status("Namespace", "ns", "Satisfied", "Found")
    first_live.update.assert_called()

    assert renderer.prompt("Second: ") == "second"
    assert first_live.stop.call_count == 1
    assert live_class.call_count == 2
    renderer.close()


def test_plain_renderer_close_is_noop():
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        plain=True,
        console=_console(StringIO()),
    )
    renderer.close()


def test_renderer_cancelled_is_neutral():
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(stream, force_terminal=True),
    )
    renderer.cancelled()
    output = stream.getvalue()
    assert "Namespace setup cancelled" in output
    assert "Nothing was changed." in output
    assert "failed" not in output
    assert "nonzero" not in output


def test_workspace_reset_preserves_scope():
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    renderer.input_status("Subscription", "sub", "Satisfied", "Found")
    renderer.input_status("Resource group", "rg", "Satisfied", "Found")
    renderer.input_status("Namespace", "ns", "Satisfied", "Found")
    renderer.input_status("IoT Hub", "hub", "Satisfied", "Found")
    renderer._request = _request()
    renderer._plan = _plan()
    renderer._tasks.append({"state": "Succeeded", "target": "task"})
    renderer._body.append("old")

    renderer.reset_setup()

    assert set(renderer._statuses) == {
        "Subscription",
        "Resource group",
        "Namespace",
    }
    assert renderer._request is None
    assert renderer._plan is None
    assert renderer._tasks == []
    assert renderer._body == []
    assert renderer._phase == "Configuration"


def test_workspace_plan_is_bounded():
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    renderer.journey("Review", "Apply")
    renderer.phase("Review")
    plan = {
        "summary": {"Planned": 10},
        "items": [
            {
                "state": "Planned",
                "action": "create",
                "target": f"item-{index}",
            }
            for index in range(10)
        ],
    }
    renderer.plan(plan)
    output = renderer._workspace_ansi("")
    assert "╭" not in output
    assert "item-7" in output
    assert "item-8" not in output
    assert "2 more plan item(s)" in output
    assert ":back previous" in renderer._workspace().plain
    assert ":back previous" not in renderer._workspace_ansi("")


def test_workspace_confirmation_replaces_ephemeral_body():
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(StringIO(), force_terminal=True),
    )
    renderer.write("old input")
    renderer.confirmation(_plan())
    renderer.write("invalid answer")
    renderer.confirmation(_plan())
    assert renderer._body == [
        "Apply namespace setup?  3 change(s)",
        "No missing role assignments will be created.",
        "Successful operations are preserved if a later step fails.",
    ]


@pytest.mark.parametrize(
    "item_id, action, expected",
    [
        ("namespace", "reuse", "Use namespace"),
        (
            "namespace-outbound-identity",
            "configure",
            "Configure namespace outbound identity",
        ),
        (
            "resource-software-updates-main",
            "create",
            "Create Update Instance",
        ),
        (
            "resource-software-updates-main",
            "validate",
            "Validate Update Instance",
        ),
        ("resource-dps-main", "validate", "Validate DPS"),
        ("resource-hub-main", "validate", "Validate IoT Hub"),
        ("link-dps-main", "link", "Configure DPS link"),
        ("link-hub-main", "link", "Configure IoT Hub link"),
        (
            "link-software-updates-main",
            "link",
            "Configure Software Updates link",
        ),
        ("roles-hub-main", "grant", "Configure access"),
        ("hub-prerequisite", "validate", "Check Hub prerequisite"),
        ("skip-dps", "skip", "Skip target"),
        ("namespace-status", "check", "Check namespace status"),
        ("other", "update", "Update target"),
    ],
)
def test_workspace_plan_labels(item_id, action, expected):
    assert expected in subject.WorkflowRenderer._plan_label({
        "id": item_id,
        "action": action,
        "target": "target",
    })


def test_workspace_plan_details_and_empty_sections():
    item = {
        "id": "link-hub-main",
        "state": "Planned",
        "action": "link",
        "target": "main",
        "message": "needed",
        "details": {
            "resourceId": "/hub",
            "userAssignedIdentity": "/uami",
            "role": "Contributor",
            "principalId": "principal",
            "location": "eastus",
        },
    }
    details = subject.WorkflowRenderer._plan_details(item)
    assert details == [
        ("Target", "/hub"),
        ("Identity", "/uami"),
        ("Role", "Contributor"),
        ("Principal", "principal"),
        ("Location", "eastus"),
        ("Reason", "needed"),
    ]
    content = subject.Text()
    subject.WorkflowRenderer._append_plan_item(content, item)
    assert "Configure IoT Hub link" in content.plain
    assert "Principal: principal" in content.plain

    renderer = subject.WorkflowRenderer(
        "Namespace check",
        console=_console(StringIO(), force_terminal=True),
    )
    renderer.validation({"items": []})
    renderer.trust({"items": []})

    renderer.account({
        "subscriptionId": "sub",
        "userName": "user@example.com",
        "tenantId": "tenant",
    })
    renderer.journey("One", "Two")
    renderer.phase("Unknown")
    output = renderer._workspace().plain
    assert "signed in" in output
    assert "tenant tenant" in output
    assert "step 1/2" in output
    assert "One  →  Two" in output
    lines = output.splitlines()
    signed_in = next(line for line in lines if "signed in" in line)
    subscription = next(line for line in lines if "subscription" in line)
    assert signed_in.index("user@example.com") == subscription.rindex("sub")


def test_manual_receipt_includes_rbac_and_resume():
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(stream, force_terminal=True),
    )
    renderer.header("sub", "rg", "ns")
    renderer.receipt({
        "namespace": "ns",
        "resourceGroup": "rg",
        "state": "Manual",
        "summary": {"Manual": 1},
        "items": [{
            "id": "role-hub",
            "state": "Manual",
            "action": "grant",
            "target": "/hub",
            "command": "az role assignment create",
        }],
        "receipt": "/tmp/receipt.json",
    })
    output = stream.getvalue()
    assert "az role assignment create" in output
    assert "Resume: az iot adr ns setup" in output
    assert "Receipt: /tmp/receipt.json" in output


def test_receipts_render_check_and_link_details():
    check_stream = StringIO()
    check = subject.WorkflowRenderer(
        "Namespace check",
        console=_console(check_stream, force_terminal=True),
    )
    check.receipt({
        "namespace": "ns",
        "resourceGroup": "rg",
        "state": "Succeeded",
        "summary": {"Satisfied": 1},
        "items": [{
            "state": "Satisfied",
            "target": "namespace",
            "message": "ready",
        }],
    })
    assert "namespace: ready" in check_stream.getvalue()

    setup_stream = StringIO()
    setup = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(setup_stream, force_terminal=True),
    )
    setup.header("sub", "rg", "ns")
    setup.receipt({
        "namespace": "ns",
        "resourceGroup": "rg",
        "state": "Succeeded",
        "summary": {"Succeeded": 1},
        "items": [{
            "id": "link-hub-main",
            "state": "Succeeded",
            "action": "link",
            "target": "main",
            "details": {"principalId": "principal"},
        }],
    })
    output = setup_stream.getvalue()
    assert "Configure IoT Hub link: main" in output
    assert "Identity principal: principal" in output
    assert "Resource ID:" in output

    error_stream = StringIO()
    error_renderer = subject.WorkflowRenderer(
        "Namespace setup",
        console=_console(error_stream, force_terminal=True),
    )
    error_renderer.error(
        RuntimeError("failed"),
        {
            "receipt": "/tmp/failure.json",
            "receiptError": "secondary write failed",
            "items": [{
                "state": "Succeeded",
                "target": "namespace",
            }],
        },
    )
    error_output = error_stream.getvalue()
    assert "successful action(s) were kept" in error_output
    assert "Receipt: /tmp/failure.json" in error_output
    assert "Receipt write failed: secondary write failed" in error_output


def test_plain_account_and_role_confirmation():
    stream = StringIO()
    renderer = subject.WorkflowRenderer(
        "Namespace setup", plain=True, console=_console(stream)
    )
    renderer.account({
        "userName": "user@example.com",
        "tenantId": "tenant",
    })
    renderer.confirmation({
        "summary": {"Planned": 1},
        "items": [{
            "action": "grant",
            "state": "Planned",
        }],
    })
    output = stream.getvalue()
    assert "Signed in: user@example.com · tenant tenant" in output
    assert "1 missing role assignment(s) will be created" in output


def test_renderer_creates_default_console():
    renderer = subject.WorkflowRenderer("Namespace check", plain=True)
    assert renderer.console


def test_redirected_stdin_disables_rich(mocker):
    mocker.patch.object(subject.sys.stdin, "isatty", return_value=False)
    renderer = subject.WorkflowRenderer("Namespace check")
    assert not renderer.rich
