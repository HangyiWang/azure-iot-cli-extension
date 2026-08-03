# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Architectural guards.

These encode the design doc's structural rules so a regression fails a test rather than
being discovered later as a maintenance problem.
"""

import pathlib

import pytest

UI_ROOT = pathlib.Path(__file__).resolve().parents[3] / "adr" / "ui"

#: Kind identifiers that must never appear as literals in the generic machinery.
KIND_LITERALS = ("namespace", "device", "attribute", "group", "job", "certificate")


def read(*parts: str) -> str:
    return (UI_ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_ui_root_exists():
    assert UI_ROOT.is_dir(), f"expected the UI package at {UI_ROOT}"


def test_browse_screen_has_no_per_kind_branching():
    """The step 4 gate: one screen serves every kind, driven only by its spec."""
    source = read("screens", "browse.py")
    for literal in KIND_LITERALS:
        assert f'"{literal}"' not in source, (
            f"browse.py references the kind '{literal}'. The generic screen must be "
            "driven by ResourceSpec alone, or adding a kind stops being a one-file change."
        )


def test_core_is_free_of_the_ui_framework():
    """Layering rule: core stays framework-free so it is testable without a terminal."""
    for module in ("spec.py", "table.py"):
        source = read("core", module)
        assert "textual" not in source, f"core/{module} must not import the UI framework"


def test_core_does_not_import_screens_or_widgets():
    """Dependency rule: core may not import from the layers above it."""
    for module in ("spec.py", "table.py"):
        source = read("core", module)
        for upper in ("ui.screens", "ui.widgets", "ui.app"):
            assert upper not in source, f"core/{module} must not depend on {upper}"


def test_entry_point_does_not_import_the_framework_at_module_scope():
    """The framework is imported lazily so no other command pays the cost."""
    source = read("entry.py")
    module_scope = source.split("def adr_ui_launch")[0]
    assert "import textual" not in module_scope
    assert "from textual" not in module_scope
    assert "from azext_iot.adr.ui.app import" in source, "the app import stays inside the function"


def test_entry_point_silences_the_provider_console():
    """PR2: providers print rich spinners that would corrupt the screen."""
    source = read("entry.py")
    assert "console.quiet = True" in source


@pytest.mark.parametrize("module", ["spec", "table"])
def test_core_modules_are_importable_without_a_terminal(module):
    __import__(f"azext_iot.adr.ui.core.{module}")


def test_app_has_no_per_kind_branching():
    """The application must not know any kind by name.

    Child scoping is declared on the spec (``scope_key`` / ``scope_extra``), so adding a
    kind stays a one-file change. This guard exists because an earlier revision carried a
    kind-to-scope-key map here.
    """
    source = read("app.py")
    for literal in KIND_LITERALS:
        assert f'"{literal}"' not in source, (
            f"app.py references the kind '{literal}'; declare it on the ResourceSpec instead"
        )


def test_row_loading_happens_off_the_ui_thread():
    """Rule C1: the source performs network I/O from M1 and must never block the UI."""
    source = read("screens", "browse.py")
    assert "run_worker" in source and "thread=True" in source
    assert "call_from_thread" in source, "worker results must be marshalled back to the UI"
    assert "if self._loading:" in source, (
        "rule C2: an overlapping refresh is dropped, never cancelling the in-flight request"
    )


def test_widgets_do_not_import_core_internals():
    """Chrome widgets are presentation only; they must not reach into the model."""
    for module in ("chrome.py", "dialogs.py"):
        source = read("widgets", module)
        assert "core.table" not in source, f"widgets/{module} must not depend on the table model"


def test_no_method_shadows_a_framework_method():
    """Overriding a framework method by accident breaks the UI in obscure ways.

    This has bitten twice: `_render` on a Static, and `run_action` on the App. A scan is
    cheaper than rediscovering it each time.
    """
    import re

    from textual.app import App
    from textual.screen import Screen
    from textual.widgets import Static

    bases = {"App": set(dir(App)), "Screen": set(dir(Screen)), "Static": set(dir(Static))}
    targets = {
        ("app.py",): "App",
        ("screens", "base.py"): "Screen",
        ("screens", "browse.py"): "Screen",
        ("screens", "detail.py"): "Screen",
        ("screens", "help.py"): "Screen",
        ("widgets", "chrome.py"): "Static",
        ("widgets", "tray.py"): "Static",
    }
    # Textual dispatches these by name on purpose; overriding them is the intended API.
    allowed_prefixes = ("on_", "action_", "watch_", "compose", "validate_", "check_")

    collisions = []
    for parts, base in targets.items():
        source = read(*parts)
        for match in re.finditer(r"^    def ([a-zA-Z_]\w*)\(", source, re.M):
            name = match.group(1)
            if name.startswith(allowed_prefixes) or name == "__init__":
                continue
            if name in bases[base]:
                collisions.append(f"{'/'.join(parts)}: {name}() shadows {base}.{name}")
    assert not collisions, "framework methods shadowed: " + "; ".join(collisions)


def test_tables_declare_explicit_column_widths():
    """Auto-width collides at 80-120 columns and pushes the decisive column off screen."""
    source = read("screens", "onboard", "screen.py")
    assert "width=" in source, "candidate table must size its columns explicitly"


def test_every_modal_is_centred():
    """Only HelpScreen was centred, so other dialogs rendered in the top-left corner."""
    from azext_iot.adr.ui.theme import APP_CSS

    assert "ModalScreen {" in APP_CSS
    modal_block = APP_CSS.split("ModalScreen {", 1)[1].split("}", 1)[0]
    assert "align: center middle" in modal_block


def test_status_colours_come_from_the_designed_palette():
    """Raw ANSI green/red is loud; the tokens track the base theme's palette."""
    from azext_iot.adr.ui.theme import DEFAULT_THEME, THEMES

    for token, colour in THEMES[DEFAULT_THEME].items():
        assert colour.startswith("#"), f"{token} should use a designed colour, got {colour}"


# -- page guides ---------------------------------------------------------------------


def _real_specs():
    from azext_iot.adr.ui.kinds import build_registry

    class OfflineSession:
        def list_from(self, *args, **kwargs):
            return []

        def provider(self, name):
            return None

        def call(self, func, *args, **kwargs):
            return None

    return list(build_registry(OfflineSession()).all())


def test_every_kind_explains_itself():
    """A page that cannot say what it is leaves the customer guessing against live Azure."""
    missing = [spec.kind for spec in _real_specs() if spec.guide is None]
    assert not missing, f"these kinds have no page guide: {missing}"


def test_every_guide_says_what_runs_behind_it():
    """'What is this actually doing to my subscription' is the question that matters most."""
    missing = [spec.kind for spec in _real_specs() if not (spec.guide and spec.guide.runs)]
    assert not missing, f"these guides do not say what they run: {missing}"


def _real_commands():
    """Every `iot adr ns ...` command the extension actually registers."""
    import re

    source = read("..", "command_map.py")
    commands = set()
    for block in re.split(r"with self\.command_group\(", source)[1:]:
        group = re.search(r'"([^"]+)"', block)
        if not group:
            continue
        body = block.split("with self.command_group(")[0]
        for verb in re.findall(r'cmd_group\.(?:custom_|show_|wait_)?command\(\s*\n?\s*"([^"]+)"', body):
            commands.add(f"{group.group(1)} {verb}")
    return commands


def test_guides_cite_commands_that_actually_exist():
    """Hand-written command names drift. Anything cited must be a real command."""
    import re

    real = _real_commands()
    assert "iot adr ns list" in real, "the command table could not be parsed"

    failures = []
    for spec in _real_specs():
        for cited in re.findall(r"az (iot adr ns [a-z|\- ]+)", spec.guide.runs or ""):
            words = []
            for word in cited.split():
                # Flags are not part of the command name; the first one ends it.
                if word.startswith("-"):
                    break
                words.append(word)
            # Expand alternatives written as `dps|hub|su`, then check each spelling.
            spellings = [""]
            for word in words:
                spellings = [
                    f"{prefix} {choice}".strip()
                    for prefix in spellings
                    for choice in word.split("|")
                ]
            for spelling in spellings:
                if spelling not in real:
                    failures.append(f"{spec.kind}: 'az {spelling}' is not a real command")
    assert not failures, "\n".join(failures)


def test_guides_do_not_repeat_the_key_hints():
    """The hint bar is generated from real bindings; a hand-written copy would drift."""
    for spec in _real_specs():
        rows = dict(spec.guide.rows())
        assert "press enter" not in rows.get("about", "").lower()
        assert "arrow" not in rows.get("about", "").lower()


def test_guides_stay_short_enough_to_read():
    """Three lines of orientation, not documentation - the guide must not crowd the table."""
    for spec in _real_specs():
        rows = spec.guide.rows()
        assert len(rows) <= 3, f"{spec.kind} guide has {len(rows)} rows"
        for label, value in rows:
            assert len(value) <= 190, f"{spec.kind} '{label}' is {len(value)} characters"


def test_no_global_key_is_shadowed_by_a_drill_down_child():
    """A screen binding wins over an app binding, so a clash silently disables the global.

    This is exactly how 'g' for the page guide became unreachable on the namespace list,
    where 'g' already opened Groups.
    """
    from azext_iot.adr.ui.app import RadrApp
    from azext_iot.adr.ui.screens.browse import BrowseScreen

    child_keys = {
        child.key
        for spec in _real_specs()
        for child in spec.children
        if child.key
    }
    screen_keys = {binding.key for binding in BrowseScreen.BINDINGS}
    taken = child_keys | screen_keys
    clashes = [
        binding.key for binding in RadrApp.BINDINGS
        if binding.key in taken
    ]
    assert not clashes, f"these global keys are shadowed on the browse screen: {clashes}"
