# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Creation form used by every "create a new one" step."""

import re
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from azext_iot.adr.ui.screens.onboard.create import CreateRequest

#: Azure resource names: letters, digits and hyphens, not starting or ending with one.
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{1,48}[A-Za-z0-9]$")


def validate_name(name: str) -> Optional[str]:
    """Return an error message, or None when the name is acceptable."""
    text = (name or "").strip()
    if not text:
        return "a name is required"
    if not _NAME_PATTERN.match(text):
        return "3-50 characters: letters, digits and hyphens, not starting or ending with '-'"
    return None


class CreateResourceDialog(ModalScreen[Optional[CreateRequest]]):
    """Collect the few fields a new resource needs.

    Validation happens here so a mistake is caught before anything is planned, let alone
    applied.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    def __init__(self, kind: str, label: str, resource_group_name: str, location: str,
                 suggested_name: str = ""):
        super().__init__()
        self.kind = kind
        self.label = label
        self.resource_group_name = resource_group_name
        self.location = location
        self.suggested_name = suggested_name

    def compose(self) -> ComposeResult:
        with Vertical(id="help-body"):
            yield Label(Text(f"Create a new {self.label}", style="bold"))
            yield Static(Text("name", style="dim"))
            yield Input(value=self.suggested_name, placeholder="name", id="name")
            yield Static(Text("resource group", style="dim"))
            yield Input(value=self.resource_group_name, placeholder="resource group", id="rg")
            yield Static(Text("region", style="dim"))
            yield Input(value=self.location, placeholder="region", id="location")
            yield Static(
                Text("a system-assigned identity is always enabled, because linking "
                     "requires one", style="dim"),
            )
            yield Static("", id="create-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Create", id="create", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#name", Input).focus()

    def _collect(self) -> Optional[CreateRequest]:
        name = self.query_one("#name", Input).value.strip()
        problem = validate_name(name)
        resource_group = self.query_one("#rg", Input).value.strip()
        location = self.query_one("#location", Input).value.strip()
        if problem is None and not resource_group:
            problem = "a resource group is required"
        if problem is None and not location:
            problem = "a region is required"
        if problem:
            self.query_one("#create-error", Static).update(Text(problem, style="bold red"))
            return None
        return CreateRequest(
            kind=self.kind,
            name=name,
            resource_group_name=resource_group,
            location=location,
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        request = self._collect()
        if request is not None:
            self.dismiss(request)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "create":
            self.dismiss(None)
            return
        request = self._collect()
        if request is not None:
            self.dismiss(request)

    def action_cancel(self) -> None:
        self.dismiss(None)
