# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from contextlib import AbstractContextManager
from io import StringIO
import sys
import time
from typing import Any, Callable, Dict, Optional

from azure.cli.core.azclierror import AzCLIError
from prompt_toolkit import ANSI, PromptSession
from prompt_toolkit.completion import Completer, FuzzyWordCompleter
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.styles import Style
from prompt_toolkit.output.defaults import create_output
from rich.console import Console
from rich.markup import escape
from rich.live import Live
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

from azext_iot.adr.providers.base import console as provider_console
from azext_iot.adr.workflows.input import BackRequested, WorkflowCancelled
from azext_iot.adr.workflows.models import SetupRequest
from azext_iot.constants import VERSION


_THEME = Theme(
    {
        "brand": "#eef1f4",
        "active": "#4aa8ff",
        "satisfied": "#57c98a",
        "planned": "#57c98a",
        "manual": "#e0b464",
        "blocked": "#ec7367",
        "warning": "#e0b464",
        "muted": "#7c8794",
        "body": "#d6d9de",
        "selected": "#4aa8ff on #1b2734",
    }
)
_SYMBOLS = {
    "Satisfied": ("✓", "[satisfied]", "satisfied"),
    "Succeeded": ("✓", "[done]", "satisfied"),
    "Planned": ("+", "[planned]", "planned"),
    "Manual": ("!", "[manual]", "manual"),
    "Blocked": ("✖", "[blocked]", "blocked"),
    "Failed": ("✖", "[failed]", "blocked"),
    "Warning": ("!", "[warning]", "warning"),
    "NotConfigured": ("~", "[not configured]", "muted"),
}


class InputFilteredCompleter(Completer):
    def __init__(self, completer):
        self.completer = completer

    def get_completions(self, document, complete_event):
        if not document.text_before_cursor.strip():
            return
        yield from self.completer.get_completions(
            document, complete_event
        )


class RenderedWorkflowError(AzCLIError):
    def __init__(
        self,
        error: Exception,
        renderer: "WorkflowRenderer",
        result: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(str(error) or error.__class__.__name__)
        self.renderer = renderer
        self.result = result

    def print_error(self):
        self.renderer.error(self, self.result)


class WorkflowRenderer:
    def __init__(
        self,
        command_name: str,
        plain: bool = False,
        console: Optional[Console] = None,
    ):
        self.command_name = command_name
        injected_console = console is not None
        self.console = console or Console(
            stderr=True,
            theme=_THEME,
            no_color=plain,
            highlight=False,
        )
        self.rich = (
            self.console.is_terminal
            and (injected_console or sys.stdin.isatty())
            and not plain
        )
        self.content_width = min(96, max(40, self.console.width))
        self._phase = None
        self._stages = ()
        self._subscription_id = None
        self._resource_group_name = None
        self._namespace_name = None
        self._statuses = {}
        self._body = []
        self._request = None
        self._plan = None
        self._tasks = []
        self._account = {}
        self._hold_live = None
        self._alert = None
        self._busy = None
        self._footer = ":back previous · :help commands · :quit cancel"
        bindings = KeyBindings()
        bindings.add("escape")(self._back_key)
        bindings.add("up")(self._up_key)
        bindings.add("down")(self._down_key)

        self._prompt_style = Style.from_dict(
            {
                "completion-menu.completion": "fg:#7c8794",
                "completion-menu.completion.current": (
                    "fg:#4aa8ff bg:#1b2734"
                ),
                "scrollbar.background": "bg:#101317",
                "scrollbar.button": "bg:#3b424b",
            }
        )
        self._prompt_session = (
            PromptSession(
                erase_when_done=True,
                reserve_space_for_menu=8,
                output=create_output(stdout=sys.stderr),
                key_bindings=bindings,
                style=self._prompt_style,
            )
            if self.rich
            else None
        )

    @staticmethod
    def _back_key(event):
        event.current_buffer.text = ":back"
        event.current_buffer.validate_and_handle()

    @staticmethod
    def _up_key(event):
        buffer = event.current_buffer
        if buffer.complete_state:
            buffer.complete_previous()
        elif buffer.text.strip():
            buffer.start_completion(select_first=False)

    @staticmethod
    def _down_key(event):
        buffer = event.current_buffer
        if buffer.complete_state:
            buffer.complete_next()
        elif buffer.text.strip():
            buffer.start_completion(select_first=False)

    def prompt(self, label: str) -> str:
        return self._prompt(label)

    def select(
        self,
        title: str,
        options: Dict[str, tuple],
        guidance: Optional[str] = None,
        allow_custom: bool = False,
        show_options: bool = True,
    ) -> str:
        lookup = {}
        self._body.clear()
        self._show(title)
        if guidance:
            self._show(guidance)
        words = []
        for number, (value, label, *aliases) in enumerate(
            options.values(), start=1
        ):
            display = f"{number}  {label}"
            if not self.rich or show_options:
                self._show(display)
            words.append(str(label))
            for key in (str(number), label, value, *aliases):
                lookup[str(key).casefold()] = value
        completer = InputFilteredCompleter(
            FuzzyWordCompleter(
                [str(word) for word in words if word],
                WORD=True,
            )
        )
        self._footer = (
            "↑↓ choose · enter select · type to filter · esc back · q quit"
        )
        while True:
            raw_choice = self._prompt(
                "❯ ",
                completer=completer,
            ).strip()
            choice = raw_choice.casefold()
            if choice in {"q", "quit"}:
                raise WorkflowCancelled()
            selected = lookup.get(choice)
            if selected is not None:
                self._body.clear()
                self._alert = None
                self._footer = (
                    ":back previous · :help commands · :quit cancel"
                )
                self._refresh_hold()
                return selected
            if allow_custom and choice:
                self._body.clear()
                self._alert = None
                self._refresh_hold()
                return raw_choice
            self._body[:] = [
                title,
                "! Choose a listed number or name.",
            ]

    def _prompt(self, label: str, completer=None) -> str:
        while True:
            if self.rich:
                self._stop_hold()
                value = self._prompt_session.prompt(
                    ANSI(self._workspace_ansi(label)),
                    completer=completer,
                    complete_style=CompleteStyle.COLUMN,
                    complete_while_typing=bool(completer),
                    style=self._prompt_style,
                    bottom_toolbar=ANSI(self._footer_ansi()),
                ).strip()
            else:
                self.console.print(
                    label, style="active", end="", markup=False
                )
                value = input().strip()
            command = value.casefold()
            if command == ":back":
                self._start_hold()
                raise BackRequested()
            if command == ":quit":
                self._body.clear()
                raise WorkflowCancelled()
            if command == ":help":
                help_text = (
                    ":back previous input  ·  :help commands  ·  :quit cancel"
                )
                if help_text not in self._body:
                    self._show(help_text)
                continue
            self._start_hold()
            return value

    def write(self, message: str):
        if message.startswith("Selected:"):
            if self.rich:
                self._body.clear()
                self._refresh_hold()
            return
        if message.startswith("Validation failed:"):
            self._busy = None
            self._alert = message
            self._refresh_hold()
            return
        if message.startswith("!"):
            self._alert = message
            self._refresh_hold()
            return
        self._show(message)

    def busy(self, message: str):
        self._alert = None
        self._busy = message
        self._start_hold()
        self._refresh_hold()

    def idle(self):
        self._busy = None
        self._refresh_hold()

    def header(
        self,
        subscription_id: str,
        resource_group_name: Optional[str],
        namespace_name: Optional[str],
    ):
        self._subscription_id = subscription_id
        self._resource_group_name = resource_group_name
        self._namespace_name = namespace_name
        if self.rich:
            self._refresh_hold()
            return
        self.console.print(
            f"Azure Device Registry - {self.command_name}\n"
            f"Subscription: {subscription_id or 'not resolved'}\n"
            f"Resource group: {resource_group_name or 'not provided'}\n"
            f"Namespace: {namespace_name or 'not provided'}",
            markup=False,
        )

    def account(self, value: Dict[str, Any]):
        self._account = dict(value or {})
        self._subscription_id = (
            self._account.get("subscriptionId")
            or self._subscription_id
        )
        self._refresh_hold()
        if not self.rich and self._account.get("userName"):
            self.console.print(
                "Signed in: "
                f"{self._account['userName']}"
                + (
                    f" · tenant {self._account['tenantId']}"
                    if self._account.get("tenantId")
                    else ""
                ),
                markup=False,
            )

    def journey(self, *stages: str):
        self._stages = stages
        if self.rich:
            self._refresh_hold()
            return
        self.console.print(" > ".join(stages), markup=False)

    def phase(self, name: str):
        if self._phase == name:
            return
        self._phase = name
        self._body.clear()
        self._alert = None
        self._busy = None
        self._refresh_hold()
        if not self.rich:
            self.console.print(f">> {name}", markup=False)

    def input_status(
        self,
        label: str,
        value: str,
        state: str,
        message: str = "",
    ):
        item = {
            "state": state,
            "target": f"{label}: {value}",
            "label": label,
            "value": value,
            "message": message,
        }
        self._statuses[label] = item
        self._alert = None
        self._busy = None
        if label == "Resource group":
            self._resource_group_name = value
        elif label == "Namespace":
            self._namespace_name = value
        if self.rich:
            self._refresh_hold()
            return
        self._status_line(item)

    def resolved_setup(self, request: SetupRequest):
        self._request = request
        self._resource_group_name = request.resource_group_name
        self._namespace_name = request.namespace_name
        if self.rich:
            self._refresh_hold()
            return
        tree = Tree("[brand]Resolved setup[/brand]")
        namespace = tree.add(
            f"[bold]Namespace[/bold]  {escape(request.namespace_name)}"
        )
        namespace.add(
            f"Resource group  {escape(request.resource_group_name)}"
        )
        namespace.add(
            f"Outbound identity  "
            f"{escape(request.outbound_identity_type or 'unchanged')}"
        )
        if request.dps:
            self._endpoint_branch(tree, "DPS", request.dps)
        for hub in request.hubs:
            self._endpoint_branch(tree, "IoT Hub", hub)
        if request.software_updates:
            self._endpoint_branch(
                tree, "Software Updates", request.software_updates
            )
        tree.add(
            "Role assignments  "
            + ("create missing" if request.assign_roles else "detect only")
        )
        self.console.print(tree)

    @staticmethod
    def _endpoint_branch(tree: Tree, label: str, endpoint):
        branch = tree.add(
            f"[bold]{label}[/bold]  {escape(endpoint.endpoint_name)}"
        )
        branch.add(f"Resource  {escape(endpoint.resource_id)}")
        branch.add(
            "Identity  "
            + escape(
                "SystemAssigned"
                if endpoint.identity_type == "system-assigned"
                else endpoint.user_assigned_identity
            )
        )

    def validation(
        self,
        plan: Dict[str, Any],
        item_filter: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ):
        items = [
            item
            for item in plan["items"]
            if item["action"] in {"validate", "reuse", "check"}
            and (item_filter is None or item_filter(item))
        ]
        if not items:
            return
        if self.rich:
            self._plan = plan
            self._refresh_hold()
            return
        self.console.print("[brand]Validation[/brand]")
        for item in items:
            self._status_line(item)

    def trust(self, plan: Dict[str, Any]):
        roles = [
            item
            for item in plan["items"]
            if (item.get("details") or {}).get("role")
        ]
        if not roles:
            return
        if self.rich:
            self._plan = plan
            self._refresh_hold()
            return
        self.console.print("[brand]Identity and permissions[/brand]")
        for item in roles:
            details = item.get("details") or {}
            principal = str(details.get("principalId") or "resolved at apply")
            role = str(details.get("role") or "required role")
            target = item["target"]
            line = Text("  ")
            line.append(principal)
            line.append(" ── ")
            line.append(role)
            line.append(" ──> ")
            line.append(target)
            self.console.print(line, soft_wrap=True)
            self._status_line(item, indent="    ")

    def plan(self, plan: Dict[str, Any]):
        self._plan = plan
        if self.rich:
            self._refresh_hold()
            return
        self.console.print("[brand]Plan[/brand]")
        for item in plan["items"]:
            self._status_line(
                {
                    "state": item["state"],
                    "target": self._plan_label(item),
                }
            )
            for label, value in self._plan_details(item):
                self.console.print(
                    f"    {label}: {value}",
                    markup=False,
                    soft_wrap=True,
                )
        summary = " · ".join(
            f"{count} {state.lower()}"
            for state, count in plan.get("summary", {}).items()
        )
        if summary:
            self.console.print(summary, style="muted")

    def confirmation(self, plan: Dict[str, Any]):
        self._plan = plan
        changes = sum(
            count
            for state, count in plan.get("summary", {}).items()
            if state in {"Planned", "Manual"}
        )
        role_changes = sum(
            item.get("action") == "grant"
            and item.get("state") == "Planned"
            for item in plan.get("items", [])
        )
        role_message = (
            f"{role_changes} missing role assignment(s) will be created."
            if role_changes
            else "No missing role assignments will be created."
        )
        if self.rich:
            self._body[:] = [
                f"Apply namespace setup?  {changes} change(s)",
                role_message,
                "Successful operations are preserved if a later step fails.",
            ]
            self._refresh_hold()
            return
        self.console.print(
            "Apply namespace setup?\n"
            f"Changes: {changes}\n"
            f"{role_message}\n"
            "Successful operations are preserved if a later step fails.",
            markup=False,
        )

    def receipt(self, result: Dict[str, Any]):
        summary = result.get("summary", {})
        if not self.rich:
            lines = [
                f"{self.command_name} complete",
                f"Namespace: {result.get('namespace')}",
                f"State: {result.get('state')}",
            ]
            lines.extend(f"{state}: {count}" for state, count in summary.items())
            self.console.print("\n".join(lines), markup=False)
            return
        self._stop_hold()
        self._body.clear()
        self._tasks.clear()
        self._plan = None
        self._body.extend(
            [
                f"State: {result.get('state')}",
                *(
                    f"{state}: {count}"
                    for state, count in summary.items()
                ),
            ]
        )
        if self.command_name == "Namespace check":
            for item in result.get("items", []):
                self._body.append(
                    f"{_SYMBOLS.get(item.get('state'), ('○', '', ''))[0]} "
                    f"{item.get('target')}: "
                    f"{item.get('message') or item.get('state')}"
                )
        else:
            namespace_id = (
                f"/subscriptions/{self._subscription_id}"
                f"/resourceGroups/{result.get('resourceGroup')}"
                "/providers/Microsoft.DeviceRegistry/namespaces/"
                f"{result.get('namespace')}"
            )
            self._body.append(f"Resource ID: {namespace_id}")
            principals = {
                str((item.get("details") or {}).get("principalId"))
                for item in result.get("items", [])
                if (item.get("details") or {}).get("principalId")
            }
            for principal in sorted(principals):
                self._body.append(f"Identity principal: {principal}")
            for item in result.get("items", []):
                item_id = str(item.get("id") or "")
                if item_id.startswith("link-") or item_id.startswith("skip-"):
                    self._body.append(
                        f"{_SYMBOLS.get(item.get('state'), ('○', '', ''))[0]} "
                        f"{self._plan_label(item)}"
                    )
        if result.get("receipt"):
            self._body.append(f"Receipt: {result['receipt']}")
        manual_items = [
            item
            for item in result.get("items", [])
            if item.get("state") == "Manual"
        ]
        for item in manual_items:
            self._body.append(
                f"Manual: {self._plan_label(item)}"
            )
            if item.get("command"):
                self._body.append(f"  {item['command']}")
        if manual_items:
            self._body.append(
                "Resume: "
                + str(
                    result.get("resumeCommand")
                    or (
                        "az iot adr ns setup "
                        f"-n {result.get('namespace')} "
                        f"-g {result.get('resourceGroup')} --yes"
                    )
                )
            )
        else:
            self._body.extend(
                [
                    "Next: az iot adr ns show "
                    f"-n {result.get('namespace')} "
                    f"-g {result.get('resourceGroup')}",
                    "Next: az iot adr ns check "
                    f"-n {result.get('namespace')} "
                    f"-g {result.get('resourceGroup')}",
                ]
            )
        style = (
            "satisfied"
            if result.get("state") == "Succeeded"
            else "warning"
        )
        self.console.print(
            self._final_view(
                f"✓ {self.command_name} complete", style
            )
        )

    def error(self, error: Exception, result: Optional[Dict[str, Any]] = None):
        if not self.rich:
            lines = [
                f"{self.command_name} failed",
                str(error) or error.__class__.__name__,
            ]
            for item in (result or {}).get("items", []):
                if item["state"] not in {"Manual", "Blocked", "Failed"}:
                    continue
                lines.append(
                    f"{item['target']}: "
                    f"{item.get('message') or item['state']}"
                )
                if item.get("command"):
                    lines.append(f"Fix: {item['command']}")
            self.console.print("\n".join(lines), markup=False)
            return
        self._stop_hold()
        self._body.clear()
        self._tasks.clear()
        self._plan = None
        self._body.append(str(error) or error.__class__.__name__)
        self._body.append("Exit: nonzero")
        if result:
            succeeded = sum(
                item.get("state") in {"Succeeded", "Satisfied"}
                for item in result.get("items", [])
            )
            if succeeded:
                self._body.append(
                    f"{succeeded} successful action(s) were kept; "
                    "rerunning setup is safe."
                )
            for item in result.get("items", []):
                if item["state"] not in {"Manual", "Blocked", "Failed"}:
                    continue
                self._body.append(
                    f"{item['target']}: "
                    f"{item.get('message') or item['state']}"
                )
                if item.get("command"):
                    self._body.append(f"Fix: {item['command']}")
            if result.get("receipt"):
                self._body.append(f"Receipt: {result['receipt']}")
            if result.get("receiptError"):
                self._body.append(
                    "Receipt write failed: "
                    f"{result['receiptError']}"
                )
        self.console.print(
            self._final_view(
                f"✖ {self.command_name} failed", "blocked"
            )
        )

    def cancelled(self):
        self._stop_hold()
        message = Text(f"{self.command_name} cancelled", style="brand")
        message.append(" · Nothing was changed.", style="muted")
        self.console.print(message)

    def execution(self):
        return WorkflowExecution(self)

    def close(self):
        self._stop_hold()

    def reset_setup(self):
        self._stop_hold()
        self._statuses = {
            label: item
            for label, item in self._statuses.items()
            if label in {"Subscription", "Resource group", "Namespace"}
        }
        self._body.clear()
        self._alert = None
        self._busy = None
        self._request = None
        self._plan = None
        self._tasks.clear()
        self._phase = None
        self.phase("Configuration")

    def _show(self, message: str):
        if self.rich:
            self._body.append(message)
            self._body[:] = self._body[-12:]
            self._refresh_hold()
        else:
            self.console.print(message, markup=False)

    def _start_hold(self):
        if not self.rich or self._hold_live:
            return
        self._hold_live = Live(
            self._workspace(),
            console=self.console,
            transient=True,
            auto_refresh=False,
        )
        self._hold_live.start(refresh=True)

    def _refresh_hold(self):
        if self._hold_live:
            self._hold_live.update(
                self._workspace(), refresh=True
            )

    def _stop_hold(self):
        if not self._hold_live:
            return
        self._hold_live.stop()
        self._hold_live = None

    def _workspace_ansi(self, prompt_label: str) -> str:
        stream = StringIO()
        console = Console(
            file=stream,
            force_terminal=True,
            color_system=self.console.color_system or "standard",
            width=self.console.width,
            theme=_THEME,
            highlight=False,
        )
        console.print(self._workspace(include_footer=False))
        console.print(
            prompt_label,
            style="active",
            end="",
            markup=False,
        )
        return stream.getvalue()

    def _footer_ansi(self) -> str:
        stream = StringIO()
        console = Console(
            file=stream,
            force_terminal=True,
            color_system=self.console.color_system or "standard",
            width=self.console.width,
            theme=_THEME,
            highlight=False,
        )
        footer = Text()
        self._append_footer(footer)
        console.print(footer, end="")
        return stream.getvalue()

    def _workspace(self, include_footer=True):
        content = Text()
        content.append(
            f"$ az iot adr ns {self.command_name.split()[-1].lower()}",
            style="satisfied",
        )
        content.append("\n")
        content.append(
            f"Azure IoT · Device Registry {self.command_name.lower()} "
            f"· v{VERSION}",
            style="muted",
        )
        content.append(
            " · ctrl-c aborts, nothing is applied before confirmation",
            style="muted",
        )
        content.append("\n\n")
        if self._account.get("userName"):
            content.append(f"✓ {'signed in':<18}", style="muted")
            content.append(str(self._account["userName"]))
            if self._account.get("tenantId"):
                content.append(
                    f" · tenant {self._account['tenantId']}",
                    style="muted",
                )
            content.append("\n")
        self._append_scope(content, "Subscription", self._subscription_id)
        content.append("\n")
        self._append_scope(
            content, "Resource group", self._resource_group_name
        )
        content.append("\n")
        self._append_scope(content, "Namespace", self._namespace_name)

        if self._stages:
            active_stage = self._active_stage()
            current = self._stages.index(active_stage) + 1
            content.append("\n\n")
            content.append(
                f"step {current}/{len(self._stages)}  ",
                style="muted",
            )
            content.append(
                active_stage,
                style="active",
            )
            content.append("\n")
            for index, stage in enumerate(self._stages):
                if index:
                    content.append("  →  ", style="muted")
                content.append(
                    stage,
                    style=(
                        "active"
                        if stage == active_stage
                        else "muted"
                    ),
                )
            content.append("\n\n")
            content.append("Workflow", style="brand")
            content.append("  ", style="muted")
            content.append(
                "─" * max(4, self.content_width - 10),
                style="muted",
            )

        extra_statuses = [
            item
            for label, item in self._statuses.items()
            if label not in {"Subscription", "Resource group", "Namespace"}
        ]
        for item in extra_statuses[-6:]:
            content.append("\n")
            self._append_item(content, item)

        if self._request and self._phase in {
            "Resources",
            "Access",
            "Review",
            "Apply",
        }:
            content.append("\n\n")
            content.append("Setup", style="brand")
            content.append(
                f"\nOutbound identity: "
                f"{self._request.outbound_identity_type or 'unchanged'}"
            )
            if self._request.dps:
                content.append(
                    f"\nDPS: {self._request.dps.endpoint_name}"
                )
            for hub in self._request.hubs:
                content.append(f"\nIoT Hub: {hub.endpoint_name}")
            if self._request.software_updates:
                content.append(
                    "\nSoftware Updates: "
                    f"{self._request.software_updates.endpoint_name}"
                )
            content.append(
                "\nRole assignments: "
                + (
                    "create missing"
                    if self._request.assign_roles
                    else "detect only"
                )
            )

        if self._plan and self._phase in {"Review", "Apply"}:
            content.append("\n\n")
            content.append("Plan", style="brand")
            plan_items = self._plan.get("items", [])
            actionable = sum(
                item.get("state") in {"Planned", "Manual"}
                for item in plan_items
            )
            content.append(
                f"  nothing has been changed yet · "
                f"{actionable} action(s)",
                style="muted",
            )
            for item in plan_items[:8]:
                content.append("\n")
                self._append_plan_item(content, item)
            if len(plan_items) > 8:
                content.append(
                    f"\n… {len(plan_items) - 8} more plan item(s)",
                    style="muted",
                )
            summary = " · ".join(
                f"{count} {state.lower()}"
                for state, count in self._plan.get("summary", {}).items()
            )
            if summary:
                content.append(f"\n{summary}", style="muted")

        if self._tasks:
            content.append("\n\n")
            content.append("Tasks", style="brand")
            completed = sum(
                item["state"] in {"Succeeded", "Failed"}
                for item in self._tasks
            )
            total = max(
                completed,
                sum(
                    count
                    for state, count in (
                        self._plan or {}
                    ).get("summary", {}).items()
                    if state == "Planned"
                ),
                len(self._tasks),
            )
            if total:
                width = 24
                filled = int(width * completed / total)
                content.append("\n")
                content.append("█" * filled, style="satisfied")
                content.append("█" * (width - filled), style="#2a3138")
                content.append(
                    f"  {completed}/{total}  "
                    f"{int(100 * completed / total)}%",
                    style="muted",
                )
            for item in self._tasks[-7:]:
                content.append("\n")
                self._append_item(content, item)

        if self._body:
            content.append("\n\n")
            for index, line in enumerate(self._body):
                if index:
                    content.append("\n")
                content.append(str(line))

        if self._busy:
            content.append("\n\n")
            content.append("⠋ ", style="active")
            content.append(self._busy, style="body")
        if self._alert:
            content.append("\n\n")
            content.append(self._alert, style="blocked")

        if include_footer and not self._tasks:
            content.append("\n\n")
            self._append_footer(content)
        return content

    def _append_footer(self, content: Text):
        for index, item in enumerate(self._footer.split(" · ")):
            if index:
                content.append(" · ", style="muted")
            key, separator, description = item.partition(" ")
            content.append(key, style="active")
            if separator:
                content.append(
                    f"{separator}{description}",
                    style="muted",
                )

    def _active_stage(self):
        if self._phase in self._stages:
            return self._phase
        if "Subscription" in self._stages:
            return "Configuration"
        if self._phase in {"Subscription", "Resource group", "Namespace"}:
            return "Scope"
        if self._phase == "Links":
            return "Results"
        return self._stages[0] if self._stages else ""

    def _final_view(self, title: str, style: str):
        content = Text()
        content.append(title, style=style)
        content.append("\n")
        content.append("─" * min(self.content_width, len(title) + 12), style="muted")
        if self._body:
            content.append("\n")
            for line in self._body:
                content.append(f"\n{line}")
        return content

    def _append_scope(self, content: Text, label: str, value: Optional[str]):
        item = self._statuses.get(label)
        if item:
            symbol, _, _ = _SYMBOLS.get(
                item["state"], ("○", "[pending]", "muted")
            )
            content.append(symbol, style="muted")
            content.append(f" {label.lower():<18}", style="muted")
            content.append(str(item.get("value") or value or "not provided"))
            if item.get("message"):
                content.append(f" · {item['message']}", style="muted")
            return
        content.append(f"○ {label.lower():<18}", style="muted")
        content.append(value or "not provided")

    @staticmethod
    def _append_item(content: Text, item: Dict[str, Any]):
        symbol, fallback, style = _SYMBOLS.get(
            item["state"], ("…", "[pending]", "muted")
        )
        content.append(symbol or fallback, style=style)
        action = f" {item['action']}" if item.get("action") else ""
        content.append(f"{action} {item['target']}")
        if item.get("message"):
            content.append(f" · {item['message']}", style="muted")

    @classmethod
    def _append_plan_item(cls, content: Text, item: Dict[str, Any]):
        symbol, _, style = _SYMBOLS.get(
            item["state"], ("…", "[pending]", "muted")
        )
        content.append(symbol, style=style)
        content.append(f" {cls._plan_label(item)}")

        for label, value in cls._plan_details(item):
            content.append(f"\n    {label}: ", style="muted")
            content.append(value)

    @staticmethod
    def _plan_details(item: Dict[str, Any]):
        details = item.get("details") or {}
        result = []
        if details.get("resourceId"):
            result.append(
                ("Target", str(details["resourceId"]))
            )
        identity = (
            details.get("userAssignedIdentity")
            or details.get("identityType")
        )
        if identity:
            result.append(("Identity", str(identity)))
        if details.get("role"):
            result.append(("Role", str(details["role"])))
        if details.get("principalId"):
            result.append(
                ("Principal", str(details["principalId"]))
            )
        if details.get("location"):
            result.append(("Location", str(details["location"])))
        if item.get("message"):
            result.append(("Reason", str(item["message"])))
        return result

    @staticmethod
    def _plan_label(item: Dict[str, Any]) -> str:
        item_id = str(item.get("id") or "")
        action = str(item.get("action") or "update")
        target = str(item.get("target") or "")
        if item_id == "namespace":
            verb = "Create" if action == "create" else "Use"
            return f"{verb} namespace: {target}"
        if item_id == "namespace-outbound-identity":
            return f"Configure namespace outbound identity: {target}"
        if item_id.startswith("resource-software-updates-"):
            verb = "Create" if action == "create" else "Validate"
            return f"{verb} Update Instance: {target}"
        if item_id.startswith("resource-dps-"):
            return f"Validate DPS: {target}"
        if item_id.startswith("resource-hub-"):
            return f"Validate IoT Hub: {target}"
        if item_id.startswith("link-dps-"):
            return f"Configure DPS link: {target}"
        if item_id.startswith("link-hub-"):
            return f"Configure IoT Hub link: {target}"
        if item_id.startswith("link-software-updates-"):
            return f"Configure Software Updates link: {target}"
        if item_id.startswith("role") or item_id.startswith("roles-"):
            return f"Configure access: {target}"
        if item_id == "hub-prerequisite":
            return f"Check Hub prerequisite: {target}"
        if item_id.startswith("skip-"):
            return f"Skip {target}: not configured in this run"
        if item_id == "namespace-status":
            return f"Check namespace status: {target}"
        return f"{action.capitalize()} {target}"

    def _status_line(self, item: Dict[str, Any], indent: str = ""):
        _, fallback, _ = _SYMBOLS.get(
            item["state"], ("…", "[pending]", "muted")
        )
        message = f" - {item['message']}" if item.get("message") else ""
        action = f"{item['action']} " if item.get("action") else ""
        self.console.print(
            f"{indent}{fallback} {action}{item['target']}{message}",
            markup=False,
            soft_wrap=True,
        )


class WorkflowExecution(AbstractContextManager):
    def __init__(self, renderer: WorkflowRenderer):
        self.renderer = renderer
        self.console = renderer.console
        self.rich = renderer.rich
        self.live = None
        self._provider_quiet = provider_console.quiet

    def __enter__(self):
        provider_console.quiet = True
        if self.rich:
            self.renderer.close()
            self.renderer._body.clear()
            self.renderer._tasks.clear()
            self.live = Live(
                self.renderer._workspace(),
                console=self.console,
                transient=True,
                auto_refresh=False,
            )
            self.live.start(refresh=True)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if self.rich:
            self.live.stop()
        provider_console.quiet = self._provider_quiet
        return False

    def run(
        self,
        label: str,
        operation: Callable,
        *args,
        **kwargs,
    ):
        if not self.rich:
            self.console.print(
                f"[running] {label}", markup=False, style="active"
            )
        task = {
            "state": "Warning",
            "target": label,
            "message": "running",
            "startedAt": time.monotonic(),
        }
        if self.rich:
            self.renderer._tasks.append(task)
            self.live.update(
                self.renderer._workspace(), refresh=True
            )
        try:
            result = operation(*args, **kwargs)
        except Exception:
            if self.rich:
                task.update(
                    state="Failed",
                    message=(
                        f"failed · "
                        f"{time.monotonic() - task['startedAt']:.1f}s"
                    ),
                )
                self.live.update(
                    self.renderer._workspace(), refresh=True
                )
            else:
                self.console.print(
                    f"[failed] {label}", markup=False, style="blocked"
                )
            raise
        if self.rich:
            task.update(
                state="Succeeded",
                message=(
                    f"done · "
                    f"{time.monotonic() - task['startedAt']:.1f}s"
                ),
            )
            self.live.update(
                self.renderer._workspace(), refresh=True
            )
        else:
            self.console.print(
                f"[done] {label}", markup=False, style="satisfied"
            )
        return result
