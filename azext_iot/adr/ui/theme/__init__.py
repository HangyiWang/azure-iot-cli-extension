# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Themes: style tokens and application stylesheet.

`core` emits abstract style tokens (``ok``, ``warn``, ``error``...) rather than colours, so
the model layer stays presentation-free and a theme can be swapped without touching it.

Accessibility: colour is never the only signal. Status columns carry their state as text,
and the high-contrast theme is provided for low-colour or low-vision use.
"""

from typing import Dict

from azext_iot.adr.ui.core.spec import (
    STYLE_ACTIVE,
    STYLE_ERROR,
    STYLE_MUTED,
    STYLE_OK,
    STYLE_WARN,
)

DEFAULT_THEME = "default"
HIGH_CONTRAST_THEME = "high-contrast"

#: Textual theme whose variables the stylesheet builds on.
BASE_THEME = "nord"
HIGH_CONTRAST_BASE_THEME = "textual-ansi"


def base_theme_for(name: str = None) -> str:
    return (
        HIGH_CONTRAST_BASE_THEME
        if (name or "").strip().lower() == HIGH_CONTRAST_THEME
        else BASE_THEME
    )


# Drawn from the same palette as the base theme, so status colours sit beside the
# chrome rather than fighting it. Muted on purpose: status should be legible, not loud.
_DEFAULT_TOKENS: Dict[str, str] = {
    STYLE_OK: "#a3be8c",      # sage
    STYLE_WARN: "#ebcb8b",    # soft amber
    STYLE_ERROR: "#bf616a",   # muted rose
    STYLE_MUTED: "#6b7280",   # slate
    STYLE_ACTIVE: "#88c0d0",  # frost
}

_HIGH_CONTRAST_TOKENS: Dict[str, str] = {
    STYLE_OK: "bold bright_green",
    STYLE_WARN: "bold bright_yellow",
    STYLE_ERROR: "bold bright_red",
    STYLE_MUTED: "bright_white",
    STYLE_ACTIVE: "bold bright_cyan",
}

THEMES: Dict[str, Dict[str, str]] = {
    DEFAULT_THEME: _DEFAULT_TOKENS,
    HIGH_CONTRAST_THEME: _HIGH_CONTRAST_TOKENS,
}


def resolve_theme(name: str = None) -> Dict[str, str]:
    """Return a token map, falling back to the default for an unknown name."""
    return THEMES.get((name or DEFAULT_THEME).strip().lower(), _DEFAULT_TOKENS)


def style_for(token: str, theme: Dict[str, str] = None) -> str:
    """Resolve a style token to a rich style string; unknown tokens render unstyled."""
    if not token:
        return ""
    return (theme or _DEFAULT_TOKENS).get(token, "")


APP_CSS = """
/* Design notes
   - A border says where focus is: near-invisible ($panel) until focused ($primary).
     Borrowed from Harlequin, which uses exactly this to orient the eye.
   - Panes carry their name in the border title, so no row is spent on a heading.
   - Chrome is flat and quiet; only content and the focused pane carry weight.
   - Sizes are proportional (fr), so the layout holds from 80 columns upward. */

Screen {
    layout: vertical;
    background: $background;
}

/* ---------- chrome: one line each, no borders, deliberately recessive ---------- */

ContextBar {
    height: 1;
    padding: 0 2;
    background: $primary-darken-3;
    color: $text;
}

InfoPanel {
    height: auto;
    max-height: 4;
    padding: 0 2;
    color: $text-muted;
}

/* The guide is the one piece of chrome allowed more than a row. A left rule sets it
   apart from the bars above and below without spending a border on it. */
PageGuide {
    height: auto;
    max-height: 8;
    padding: 0 2;
    margin: 1 2 0 2;
    border-left: outer $primary-darken-1;
    color: $text-muted;
    background: $boost;
}

HintBar {
    height: 1;
    padding: 0 2;
    margin: 1 0 0 0;
    color: $text-muted;
}

Breadcrumbs {
    height: 1;
    padding: 0 2;
    color: $text;
    text-style: bold;
}

FlashLine {
    height: 1;
    padding: 0 2;
}

OperationsTray {
    height: 1;
    padding: 0 2;
    color: $text-muted;
}

/* ---------- content: bordered, focus-aware ---------- */

DataTable {
    height: 1fr;
    border: round $panel;
    background: $background;
    padding: 0 1;
}

DataTable:focus {
    border: round $primary;
}

DataTable {
    border-title-color: $primary;
    border-title-style: bold;
}

DataTable > .datatable--header {
    text-style: bold;
    color: $primary;
    background: $background;
}

DataTable > .datatable--cursor {
    background: $primary-darken-2;
    color: $text;
    text-style: bold;
}

DataTable > .datatable--hover {
    background: $boost;
}

/* Striping alternated two greys that read as noise against this palette. Rows are
   separated by the cursor and hover instead. */
DataTable > .datatable--odd-row,
DataTable > .datatable--even-row {
    background: $background;
}

#status-line {
    height: auto;
    padding: 0 2;
    color: $text-muted;
}

/* ---------- inputs ---------- */

Input {
    border: round $panel;
    background: transparent;
    padding: 0 1;
}

Input:focus {
    border: round $primary;
}

Button {
    min-width: 12;
    height: 3;
    margin-left: 1;
}

/* ---------- guided setup: rail and working pane ---------- */

.rail {
    width: 1fr;
    min-width: 28;
    max-width: 46;
    padding: 0 1;
    border: round $panel;
}

.rail:focus-within {
    border: round $primary;
}

.pane {
    width: 3fr;
    padding: 0 1;
    border: round $panel;
}

.pane:focus-within {
    border: round $primary;
}

.pane {
    border-title-color: $primary;
    border-title-style: bold;
}

.rail {
    border-title-color: $text-muted;
}

#step-list {
    height: 1fr;
    background: transparent;
    border: none;
}

#step-list > ListItem {
    padding: 0 1;
    background: transparent;
}

#step-list > ListItem.--highlight {
    background: $primary-darken-2;
    text-style: bold;
}

#step-list:focus > ListItem.--highlight {
    background: $primary;
    color: $text;
}

#step-body {
    height: auto;
    padding: 1 1 0 1;
}

#candidate-status {
    height: auto;
    padding: 0 1;
    color: $text-muted;
}

#candidates {
    height: 1fr;
    min-height: 8;
    /* The pane already draws a border; a second one inside it reads as clutter. */
    border: none;
    padding: 0;
}

#create-form {
    height: auto;
    border: round $accent;
    padding: 1 2;
    margin: 1 0;
}

#create-form Input {
    margin-bottom: 1;
}

#create-form .modal-buttons {
    height: auto;
    align-horizontal: right;
    padding-top: 1;
}

#command-hint {
    height: auto;
    padding: 0 2;
    color: $accent;
}

/* ---------- dialogs: reserved for confirm and error only ---------- */

ModalBox {
    width: 76;
    height: auto;
    max-height: 24;
    border: round $primary;
    background: $surface;
    padding: 1 2;
}

ModalBox.danger {
    border: round $error;
}

ModalBox > .modal-title {
    text-style: bold;
    padding-bottom: 1;
}

/* Applies to every dialog, not only ModalBox: the operations and plan dialogs use
   #help-body and were rendering with unstyled, overlapping buttons. */
.modal-buttons {
    height: auto;
    width: 100%;
    align-horizontal: right;
    padding: 1 1 0 0;
}

/* Every modal is centred; only HelpScreen was, so dialogs appeared in the corner. */
ModalScreen {
    align: center middle;
    background: $background 60%;
}

#help-body {
    width: 84;
    max-width: 90%;
    /* Shrink to the content: an empty operations list should not fill the screen. */
    height: auto;
    max-height: 80%;
    border: round $primary;
    background: $surface;
    padding: 1 2;
}

#help-body > Static,
#help-body > Label {
    height: auto;
}

#json-body {
    padding: 0 1;
}
"""
