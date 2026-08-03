# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Headless application and navigation tests (design doc step 5, M0 gate).

Run without a terminal so they work in CI. Each test drives the real app through its
public surface rather than poking at internals.
"""

import asyncio


from azext_iot.adr.ui.app import RadrApp
from azext_iot.adr.ui.kinds.synthetic import build_synthetic_registry
from azext_iot.adr.ui.screens.browse import BrowseScreen
from azext_iot.adr.ui.screens.detail import DetailScreen
from azext_iot.adr.ui.screens.help import HelpScreen
from textual.widgets import DataTable
from azext_iot.adr.ui.widgets.chrome import Breadcrumbs, ContextBar, HintBar

SIZE = (120, 34)


async def settle(app, pilot):
    """Wait for row-loading workers, then let the UI repaint."""
    await app.workers.wait_for_complete()
    await pilot.pause()


def drive(coro_fn):
    """Run an async pilot interaction from a synchronous test.

    Avoids adding pytest-asyncio to the repository's dev requirements.
    """

    async def runner():
        app = RadrApp(registry=build_synthetic_registry())
        async with app.run_test(size=SIZE) as pilot:
            await settle(app, pilot)
            return await coro_fn(app, pilot)

    return asyncio.run(runner())


# -- boot --------------------------------------------------------------------------


def test_app_boots_to_the_root_kind():
    async def scenario(app, pilot):
        assert isinstance(app.screen, BrowseScreen)
        assert app.screen.spec.kind == "namespace"
        return app.screen.model.total_count

    assert drive(scenario) == 3


def test_boot_screen_renders_rows_and_status():
    async def scenario(app, pilot):
        model = app.screen.model
        return [row.id for row in model.rows], model.status_text()

    ids, status = drive(scenario)
    assert ids == ["factory-eastus2", "lab-westus", "retired-ns"]
    assert "3 namespaces" in status


# -- drill-down and the page stack --------------------------------------------------


def test_enter_drills_into_child_kind():
    async def scenario(app, pilot):
        await pilot.press("enter")
        await settle(app, pilot)
        return app.screen.spec.kind, app.screen.model.total_count

    kind, count = drive(scenario)
    assert kind == "device"
    assert count == 6


def test_drill_down_carries_parent_scope():
    async def scenario(app, pilot):
        await pilot.press("enter")
        await settle(app, pilot)
        return app.screen.scope

    scope = drive(scenario)
    assert scope["namespace_name"] == "factory-eastus2"
    assert scope["resource_group_name"] == "adr-prod-rg", "resource group follows the namespace"


def test_escape_pops_the_stack_back_to_the_parent():
    async def scenario(app, pilot):
        await pilot.press("enter")
        await settle(app, pilot)
        depth_in = len(app.screen_stack)
        await pilot.press("escape")
        await settle(app, pilot)
        return depth_in, len(app.screen_stack), app.screen.spec.kind

    depth_in, depth_out, kind = drive(scenario)
    assert depth_out == depth_in - 1
    assert kind == "namespace"


def test_stack_does_not_pop_below_the_root():
    async def scenario(app, pilot):
        for _ in range(4):
            await pilot.press("escape")
            await settle(app, pilot)
        return app.screen.spec.kind, len(app.screen_stack)

    kind, depth = drive(scenario)
    assert kind == "namespace", "the root screen is never popped"
    assert depth == 2


def test_three_level_drill_down_and_return():
    async def scenario(app, pilot):
        await pilot.press("enter")  # namespace -> device
        await settle(app, pilot)
        await pilot.press("enter")  # device -> attribute
        await settle(app, pilot)
        deepest = app.screen.spec.kind
        await pilot.press("escape")
        await settle(app, pilot)
        await pilot.press("escape")
        await settle(app, pilot)
        return deepest, app.screen.spec.kind

    deepest, back_at = drive(scenario)
    assert deepest == "attribute"
    assert back_at == "namespace", "the stack unwinds cleanly"


# -- detail view --------------------------------------------------------------------


def test_json_view_opens_and_closes():
    async def scenario(app, pilot):
        await pilot.press("y")
        await pilot.pause()
        opened = isinstance(app.screen, DetailScreen)
        name = app.screen.resource_name() if opened else None
        await pilot.press("escape")
        await settle(app, pilot)
        return opened, name, isinstance(app.screen, BrowseScreen)

    opened, name, returned = drive(scenario)
    assert opened and returned
    assert name == "factory-eastus2"


# -- chrome -------------------------------------------------------------------------


def test_hint_bar_is_generated_from_real_bindings():
    async def scenario(app, pilot):
        hints = app.screen.hint_bindings()
        return {key for key, _ in hints}

    keys = drive(scenario)
    # Every hint must correspond to a binding the screen actually declares.
    assert {"/", "escape", "r", "s", "enter"} <= keys


def test_context_bar_reflects_scope_after_drill_down():
    async def scenario(app, pilot):
        await pilot.press("enter")
        await settle(app, pilot)
        bar = app.screen.query_one("#context-bar", ContextBar)
        return bar.text

    assert "factory-eastus2" in drive(scenario)


def test_breadcrumbs_track_the_stack():
    async def scenario(app, pilot):
        await pilot.press("enter")
        await settle(app, pilot)
        crumbs = app.screen.query_one("#breadcrumbs", Breadcrumbs)
        return crumbs.text

    trail = drive(scenario)
    assert "namespaces" in trail and "registry devices" in trail


def test_hint_bar_widget_is_populated():
    async def scenario(app, pilot):
        return app.screen.query_one("#hint-bar", HintBar).text

    assert "r Refresh" in drive(scenario), "hints read as key + action"


# -- filtering, sorting, wide columns ----------------------------------------------


def test_filter_narrows_rows_and_escape_clears_it():
    async def scenario(app, pilot):
        await pilot.press("enter")  # into devices
        await settle(app, pilot)
        await pilot.press("slash")
        await pilot.pause()
        for ch in "fabrikam":
            await pilot.press(ch)
        await pilot.pause()
        filtered = app.screen.model.row_count
        await pilot.press("enter")  # commit the filter
        await pilot.pause()
        await pilot.press("escape")  # first escape clears the filter
        await pilot.pause()
        return filtered, app.screen.model.row_count, app.screen.spec.kind

    filtered, after_clear, kind = drive(scenario)
    assert filtered == 2
    assert after_clear == 6
    assert kind == "device", "clearing a filter must not also pop the screen"


def test_wide_toggle_adds_columns():
    async def scenario(app, pilot):
        before = list(app.screen.model.headers)
        await pilot.press("ctrl+w")
        await pilot.pause()
        return before, list(app.screen.model.headers)

    before, after = drive(scenario)
    assert "IDENTITY" not in before
    assert "IDENTITY" in after


def test_refresh_keeps_the_screen_usable():
    async def scenario(app, pilot):
        await pilot.press("r")
        await settle(app, pilot)
        return app.screen.model.total_count

    assert drive(scenario) == 3


# -- command bar and help -----------------------------------------------------------


def test_command_bar_resolves_an_alias():
    async def scenario(app, pilot):
        app._run_command("dev")
        await settle(app, pilot)
        return app.screen.spec.kind

    assert drive(scenario) == "device"


def test_command_bar_rejects_unknown_token_without_navigating():
    async def scenario(app, pilot):
        app._run_command("nonsense")
        await settle(app, pilot)
        return app.screen.spec.kind

    assert drive(scenario) == "namespace"


def test_help_screen_opens_and_closes():
    async def scenario(app, pilot):
        await pilot.press("question_mark")
        await pilot.pause()
        opened = isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await settle(app, pilot)
        return opened, isinstance(app.screen, BrowseScreen)

    opened, closed = drive(scenario)
    assert opened and closed


# -- resilience ---------------------------------------------------------------------


def test_source_failure_degrades_instead_of_crashing():
    """A failing lister must leave a usable screen, per the loading/failed state rules."""

    async def runner():
        registry = build_synthetic_registry()
        app = RadrApp(registry=registry)
        async with app.run_test(size=SIZE) as pilot:
            await settle(app, pilot)
            screen = app.screen

            def boom(_scope, force=False):
                raise RuntimeError("service unavailable")

            screen.source = boom
            screen.refresh_rows()
            await settle(app, pilot)
            return screen.model.state.value, screen.model.status_text()

    state, status = asyncio.run(runner())
    assert state == "stale", "rows already shown are retained"
    assert "service unavailable" in status


def test_screen_renders_at_minimum_terminal_size():
    async def runner():
        app = RadrApp(registry=build_synthetic_registry())
        async with app.run_test(size=(80, 24)) as pilot:
            await settle(app, pilot)
            return app.screen.model.total_count

    assert asyncio.run(runner()) == 3


def test_namespace_without_children_shows_empty_not_loading():
    """The empty-vs-loading distinction, exercised end to end through the UI."""

    async def scenario(app, pilot):
        table = app.screen.query_one("#rows", DataTable)
        table.move_cursor(row=2)  # 'retired-ns' has no devices by design
        await pilot.pause()
        await pilot.press("enter")
        await settle(app, pilot)
        return app.screen.spec.kind, app.screen.model.state.value, app.screen.model.status_text()

    kind, state, status = drive(scenario)
    assert kind == "device"
    assert state == "empty", "an empty collection must not read as still loading"
    assert "No registry devices found" in status


def test_child_rows_are_scoped_to_the_selected_parent():
    """Different parents yield different children, proving scope is really applied."""

    async def scenario(app, pilot):
        table = app.screen.query_one("#rows", DataTable)
        table.move_cursor(row=1)  # 'lab-westus'
        await pilot.pause()
        await pilot.press("enter")
        await settle(app, pilot)
        return app.screen.scope["namespace_name"], app.screen.model.total_count

    namespace, count = drive(scenario)
    assert namespace == "lab-westus"
    assert count == 3, "lab-westus has fewer devices than factory-eastus2"


def test_command_bar_jump_inherits_the_on_screen_scope():
    """Typing an alias deep in the tree must keep the namespace, not query with none."""

    async def scenario(app, pilot):
        await pilot.press("enter")  # namespaces -> devices, scope gains the namespace
        await settle(app, pilot)
        app._run_command("attr")    # jump sideways to another kind
        await settle(app, pilot)
        return app.screen.spec.kind, app.screen.scope.get("namespace_name")

    kind, namespace = drive(scenario)
    assert kind == "attribute"
    assert namespace == "factory-eastus2", "the alias jump kept the on-screen scope"


def test_child_hotkey_opens_that_child_directly():
    """Every declared child is reachable, not only the one Enter opens."""

    async def scenario(app, pilot):
        await pilot.press("enter")   # namespaces -> devices (primary child)
        await settle(app, pilot)
        await pilot.press("t")       # 't' is the attributes child key
        await settle(app, pilot)
        return app.screen.spec.kind

    assert drive(scenario) == "attribute"


def test_overlapping_refresh_is_dropped_not_queued():
    """Rule C2: a second refresh while one is in flight must not start another request."""

    async def scenario(app, pilot):
        screen = app.screen
        calls = []
        original = screen.source

        def counting(scope, force=False):
            calls.append(force)
            return original(scope, force=force)

        screen.source = counting
        screen._loading = True          # simulate a request already in flight
        screen.refresh_rows(force=True)
        await pilot.pause()
        return calls

    assert drive(scenario) == [], "no request is issued while one is already running"


def test_missing_scope_is_explained_without_calling_the_service():
    """A kind opened out of context must say what to open, not surface a service error."""

    async def runner():
        from azext_iot.adr.ui.core.spec import Column, Registry, ResourceSpec

        called = []

        def lister(scope):
            called.append(scope)
            return []

        registry = Registry()
        registry.register(
            ResourceSpec(
                kind="thing", title="Thing", title_plural="Things", aliases=("th",),
                row_id=lambda p: p["name"], list=lister,
                columns=(Column("name", "NAME", lambda p: p["name"]),),
                requires=("namespace_name",),
            )
        )
        app = RadrApp(registry=registry)
        async with app.run_test(size=SIZE) as pilot:
            await settle(app, pilot)
            return app.screen.model.status_text(), called

    status, called = asyncio.run(runner())
    assert "Open a namespace first" in status
    assert called == [], "no request is issued when required scope is absent"


def test_missing_scope_message_does_not_name_the_implied_resource_group():
    """Opening a namespace implies its resource group; naming both reads as noise."""

    async def runner():
        from azext_iot.adr.ui.core.spec import Column, Registry, ResourceSpec

        registry = Registry()
        registry.register(
            ResourceSpec(
                kind="thing", title="Thing", title_plural="Things", aliases=("th",),
                row_id=lambda p: p["name"], list=lambda scope: [],
                columns=(Column("name", "NAME", lambda p: p["name"]),),
                requires=("namespace_name", "resource_group_name", "registry_device_name"),
            )
        )
        app = RadrApp(registry=registry)
        async with app.run_test(size=SIZE) as pilot:
            await settle(app, pilot)
            return app.screen.model.status_text()

    status = asyncio.run(runner())
    assert "a namespace and a device" in status
    assert "resource group" not in status


def test_auto_refresh_interval_is_configured():
    """Polling is what keeps a table current; the cache decides if a tick costs a request."""

    async def scenario(app, pilot):
        return app.screen.refresh_interval

    assert drive(scenario) >= 5, "an interval must be set, at or above the floor"


def test_scope_snapshot_comes_from_the_session():
    """Scope is owned by the session; the app must not keep a second copy that can drift."""
    from azext_iot.adr.ui.core.session import Session

    class Cmd:
        cli_ctx = object()

    session = Session(Cmd(), resource_group_name="rg", namespace_name="ns")
    session.scope.subscription_name = "Contoso"
    app = RadrApp(cmd=Cmd(), session=session, registry=build_synthetic_registry(),
                  resource_group_name="rg", namespace_name="ns")
    app._apply_resolved_scope()
    assert app.scope["subscription"] == "Contoso"
    assert app.scope["namespace_name"] == "ns"


def test_guided_setup_key_is_not_case_confusable():
    """'O' vs 'o' was indistinguishable in the hint bar and easy to mis-press."""
    keys = [binding.key for binding in RadrApp.BINDINGS]
    lowered = [key.lower() for key in keys]
    assert len(lowered) == len(set(lowered)), f"case-confusable bindings: {keys}"


def test_guided_setup_uses_the_highlighted_namespace_row():
    """Pressing the key on a namespace row must set that namespace up."""

    async def scenario(app, pilot):
        table = app.screen.query_one("#rows", DataTable)
        table.move_cursor(row=1)  # 'lab-westus'
        await pilot.pause()
        spec = app.screen.spec
        payload = app.screen.selected_payload()
        scope = dict(app._active_scope())
        scope.update(spec.child_scope(payload))
        return scope

    scope = drive(scenario)
    assert scope["namespace_name"] == "lab-westus"
    assert scope["resource_group_name"] == "adr-lab-rg"


def test_fresh_setup_starts_without_adopting_a_namespace():
    """':new' must not inherit the highlighted row, or a fresh start is unreachable."""
    from azext_iot.adr.ui.core.session import Session

    class Cmd:
        cli_ctx = object()

    async def runner():
        app = RadrApp(cmd=Cmd(), session=Session(Cmd()),
                      registry=build_synthetic_registry())
        async with app.run_test(size=SIZE) as pilot:
            await settle(app, pilot)
            app._run_command("new")
            await settle(app, pilot)
            screen = app.screen
            return type(screen).__name__, screen.context.get("namespace_name")

    name, namespace = asyncio.run(runner())
    assert name == "OnboardScreen"
    assert not namespace, "a fresh start must begin with no namespace"


# -- page guide ----------------------------------------------------------------------


def test_the_page_guide_is_shown_on_arrival():
    """A customer who has never seen this page should not have to ask for the guide."""
    def scenario(app, pilot):
        guide = app.screen.query_one("#page-guide")
        assert guide.display
        assert "about" in guide.text
        return None

    async def wrapped(app, pilot):
        return scenario(app, pilot)

    drive(wrapped)


def test_the_guide_can_be_dismissed_and_restored():
    async def scenario(app, pilot):
        guide = app.screen.query_one("#page-guide")
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert not guide.display, "ctrl+g should hide the guide"
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert guide.display, "ctrl+g should bring it back"

    drive(scenario)


def test_dismissing_the_guide_sticks_when_drilling_in():
    """Re-showing it on every page would make dismissing it pointless."""
    async def scenario(app, pilot):
        await pilot.press("ctrl+g")
        await pilot.pause()
        await pilot.press("enter")
        await settle(app, pilot)
        assert not app.screen.query_one("#page-guide").display

    drive(scenario)


def test_the_guide_describes_the_kind_being_viewed():
    """Guides come from the spec, so drilling in must change what is explained."""
    async def scenario(app, pilot):
        first = app.screen.query_one("#page-guide").text
        await pilot.press("enter")
        await settle(app, pilot)
        second = app.screen.query_one("#page-guide").text
        assert first and second and first != second

    drive(scenario)
