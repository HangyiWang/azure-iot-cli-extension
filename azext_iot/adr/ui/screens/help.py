# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Help overlay and the command bar."""

from typing import Sequence, Tuple

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

GLOBAL_KEYS: Sequence[Tuple[str, str]] = (
    (":", "command bar - jump to a resource kind"),
    ("/", "filter the current table"),
    ("?", "this help"),
    ("w", "guided setup for the highlighted namespace"),
    (":new", "guided setup from scratch - creates a new namespace too"),
    ("o", "operations - long-running work"),
    ("ctrl+g", "show or hide the guide at the top of each page"),
    ("esc", "clear filter, then go back"),
    ("enter", "open the selected row"),
    ("space", "mark a row"),
    ("y", "show JSON for the selected row"),
    ("r", "refresh now"),
    ("s", "sort by the column under the cursor"),
    ("ctrl+w", "show wide columns"),
    ("q", "quit"),
)

#: Guided setup has its own keys. Listing them only in the footer means a customer who
#: opens help while stuck on a multi-select step is told nothing useful.
SETUP_KEYS: Sequence[Tuple[str, str]] = (
    ("space", "choose the highlighted resource"),
    ("d", "done with this step - move to the next one"),
    ("n", "create a new resource for this step"),
    ("/", "filter the candidate list"),
    ("1-9", "jump straight to a step"),
    ("p", "show the full plan"),
    ("a", "run the plan"),
    ("x", "export the plan as a shell script"),
    ("r", "re-read live state and permissions"),
)


class HelpScreen(ModalScreen[None]):
    """Key reference. Global keys are static; resource aliases come from the registry."""

    BINDINGS = [
        Binding("escape", "close", "Close", show=True),
        Binding("question_mark", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    def __init__(self, aliases: Sequence[Tuple[str, str]] = ()):
        super().__init__()
        self._aliases = list(aliases)

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-body"):
            yield Label(Text("radr - key reference", style="bold"))
            yield Static("")
            yield Static(self._format(GLOBAL_KEYS))
            yield Static("")
            yield Label(Text("guided setup", style="bold"))
            yield Static(self._format(SETUP_KEYS))
            if self._aliases:
                yield Static("")
                yield Label(Text("resource aliases (type after ':')", style="bold"))
                yield Static(self._format(self._aliases))
            yield Static("")
            yield Static(Text("press escape to close", style="dim"))

    @staticmethod
    def _format(rows: Sequence[Tuple[str, str]]) -> Text:
        text = Text()
        width = max((len(key) for key, _ in rows), default=0)
        for key, description in rows:
            text.append(f"  {key.ljust(width)}  ", style="bold cyan")
            text.append(f"{description}\n")
        return text

    def action_close(self) -> None:
        self.dismiss(None)


class CommandBar(ModalScreen[str]):
    """Single-line prompt that resolves a token to a resource kind."""

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=True)]

    def __init__(self, known: Sequence[str] = ()):
        super().__init__()
        self._known = sorted(set(known))

    def compose(self) -> ComposeResult:
        with Vertical(id="help-body"):
            yield Label(Text("command", style="bold"))
            yield Input(placeholder="resource alias, or 'q' to quit", id="command-input")
            if self._known:
                yield Static(Text("  ".join(self._known), style="dim"))

    def on_mount(self) -> None:
        self.query_one("#command-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss("")
