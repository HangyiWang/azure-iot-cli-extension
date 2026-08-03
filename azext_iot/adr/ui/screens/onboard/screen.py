# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""The guided onboarding screen: step rail, current step, and the plan."""

from typing import Any, Dict, List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Label, ListItem, ListView, Static

from azext_iot.adr.ui.core import diagnostics
from azext_iot.adr.ui.core.spec import Guide
from azext_iot.adr.ui.screens.base import ChromeScreen
from azext_iot.adr.ui.screens.onboard.flow import StepState
from azext_iot.adr.ui.screens.onboard.pickers import ResourceCatalog, evaluate, rank
from azext_iot.adr.ui.screens.onboard.create import CreateRequest
from azext_iot.adr.ui.screens.onboard.forms import validate_name
from azext_iot.adr.ui.screens.onboard.steps import build_flow
from azext_iot.adr.ui.widgets.tray import CommandPreviewDialog

_STEP_MARKS = {
    StepState.SATISFIED: ("[ok] ", "green"),
    StepState.CURRENT: ("  >  ", "bold cyan"),
    StepState.BLOCKED: ("[!] ", "yellow"),
    StepState.PENDING: ("     ", "grey62"),
}

#: Chosen, but not applied yet: distinct from both "still to do" and "already done".
_READY_MARK = ("[+] ", "bold #b48ead")

_VERDICT_STYLES = {"eligible": "green", "warning": "yellow", "ineligible": "red"}

#: step id -> (creation kind, human label, context key for the request)
_CREATABLE = {
    "scope": ("resource_group", "resource group", "create_resource_group"),
    "namespace": ("namespace", "namespace", "create_namespace"),
    "dps": ("dps", "provisioning service", "create_dps"),
    "hub": ("hub", "IoT Hub", "create_hub"),
    "su": ("su", "update instance", "create_su"),
}
#: step id -> context key holding the chosen existing resource
_SELECTABLE = {"dps": "selected_dps", "hub": "selected_hubs", "su": "selected_sus"}

#: Steps where several resources may be chosen. A namespace accepts many messaging and
#: many updating endpoints, but exactly one provisioning endpoint - so DPS is not here.
_MULTI_SELECT = {"hub": "IoT Hub", "su": "update instance"}

#: How many chosen names the rail spells out before it summarises the rest.
_RAIL_CHOICE_LIMIT = 10
#: Shown when a picker finds nothing. An empty table with no explanation reads as a
#: broken product; every one of these ends with the action that moves the customer on.
_EMPTY_GUIDANCE = {
    "subscription": "No subscriptions found. Run 'az login' and reopen radr.",
    "scope": "No resource groups in this subscription yet - press n to create one.",
    "namespace": "No Device Registry namespaces in this resource group yet - "
                 "press n to create one.",
    "dps": "No Device Provisioning Service found that this namespace can use - "
           "press n to create one.",
    "hub": "No IoT Hub found that this namespace can use - press n to create one.",
    "su": "No Software Updates instance found - press n to create one, or skip this "
          "optional step.",
}

#: What each picker is looking for, used while it loads.
_PICKER_NOUNS = {
    "subscription": "subscriptions",
    "scope": "resource groups",
    "namespace": "namespaces",
    "dps": "provisioning services",
    "hub": "IoT Hubs",
    "su": "update instances",
}

#: Steps that show a picker, and the catalog method that fills it.
_PICKER_STEPS = ("subscription", "scope", "namespace", "dps", "hub", "su")

#: Columns per step. Subscriptions and resource groups have no identity to report, and a
#: column of "n/a" is worse than no column.
_PICKER_COLUMNS = {
    "subscription": (("NAME", 46), ("SUBSCRIPTION ID", 40)),
    "scope": (("NAME", 40), ("REGION", 18)),
    "namespace": (("NAME", 40), ("RESOURCE GROUP", 26), ("REGION", 18)),
}
_DEFAULT_PICKER_COLUMNS = (
    ("NAME", 30), ("RESOURCE GROUP", 22), ("REGION", 15), ("IDENTITY", 15),
    ("ELIGIBILITY", 32),
)


class OnboardScreen(ChromeScreen):
    """Walks the connectivity flow: select, plan, then apply.

    Nothing is mutated while selecting. The plan is the contract shown before apply, and
    plan-only mode never applies at all.
    """

    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
        Binding("space", "select", "Select", show=True),
        Binding("p", "show_plan", "Plan", show=True),
        Binding("a", "apply", "Run setup", show=True),
        Binding("n", "create_new", "Create new", show=True),
        Binding("d", "done_step", "Done, next", show=True),
        Binding("slash", "start_filter", "Filter", show=True, key_display="/"),
        Binding("1,2,3,4,5,6,7,8,9", "goto_step", "Jump to step", show=False),
        Binding("x", "export", "Export script", show=True),
        Binding("r", "reload", "Reload state", show=True),
    ]

    def __init__(self, session, scope: Dict[str, Any], namespace: Optional[Dict[str, Any]] = None,
                 catalog: Optional[ResourceCatalog] = None, **kwargs):
        super().__init__(**kwargs)
        self.session = session
        self.scope = dict(scope or {})
        self.context: Dict[str, Any] = dict(self.scope)
        self.context["namespace"] = namespace or {}
        self.context["_catalog"] = catalog
        self.flow = build_flow(self.context)
        self.catalog = catalog
        self._candidates: List = []
        self._candidates_for: Optional[str] = None
        self._candidates_loading = False
        #: A step the user jumped to. Satisfied steps are skipped by the flow, so without
        #: this there is no way to revisit one - for example to change subscription.
        self._focus_step: Optional[str] = None
        self._candidate_filter = ""
        #: Guards the rail highlight handler while the rail is repainted, so syncing the
        #: highlight does not read back as the customer choosing a step.
        self._syncing_rail = False
        # Step states are meaningless until live state has been read once; showing them
        # early would claim an existing namespace still needs creating.
        self._state_loaded = bool(namespace) or not scope.get("namespace_name")

    # -- composition -------------------------------------------------------

    def compose_content(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="rail", id="rail"):
                # A list, not static text: arrows move through steps and the focused
                # step is what the right-hand pane acts on.
                yield ListView(id="step-list")
            with VerticalScroll(classes="pane", id="work-pane"):
                yield Static(id="step-body")
                yield Static(id="candidate-status")
                yield Input(placeholder="filter...", id="candidate-filter")
                yield DataTable(id="candidates", cursor_type="row")
                # Creation happens in place. A pushed screen would lose the step rail and
                # the context the customer is working against.
                with Vertical(id="create-form"):
                    yield Label(Text("Create new", style="bold"), id="create-title")
                    yield Label(Text("name", style="dim"))
                    yield Input(id="create-name", placeholder="name")
                    yield Label(Text("resource group", style="dim"), id="create-rg-label")
                    yield Input(id="create-rg", placeholder="resource group")
                    yield Label(Text("region", style="dim"))
                    yield Input(id="create-location", placeholder="region")
                    yield Static(
                        Text("a system-assigned identity is always enabled: linking "
                             "requires one", style="dim")
                    )
                    yield Static("", id="create-error")
                    with Horizontal(classes="modal-buttons"):
                        yield Button("Cancel", id="create-cancel")
                        yield Button("Confirm", id="create-confirm", variant="primary")
        yield Static(id="command-hint")

    def on_mount(self) -> None:
        self.query_one("#rail", Vertical).border_title = "setup"
        self.query_one("#work-pane", VerticalScroll).border_title = "current step"
        self.query_one("#candidates", DataTable).border_title = "candidates"
        self.query_one("#create-form", Vertical).border_title = "new resource"
        self.query_one("#create-form", Vertical).display = False
        self.query_one("#candidate-filter", Input).display = False
        self.refresh_view()
        # Focus the picker, or arrow keys would go nowhere on arrival.
        self.query_one("#candidates", DataTable).focus()
        # Principle O3: derive every step from live state rather than trusting a snapshot.
        if self.session is not None and self.context.get("namespace_name") \
                and not self._state_loaded:
            self.run_worker(self._reload_namespace, thread=True, name="onboard-reload")
        if self._state_loaded:
            self._reload_candidates()
        self._probe_grant_rights()

    def _probe_grant_rights(self) -> None:
        """Ask ARM, once per subscription, whether we may create role assignments.

        The answer decides whether the linking grants become operations radr runs or
        commands the customer has to hand to an administrator, so it is worth asking
        rather than assuming the pessimistic case.
        """
        subscription = self.context.get("subscription_id")
        if self.session is None or not subscription:
            return
        if self.context.get("_grant_probe_for") == subscription:
            return
        self.context["_grant_probe_for"] = subscription
        self.run_worker(
            lambda: self._read_grant_rights(subscription), thread=True, name="onboard-rbac"
        )

    def _read_grant_rights(self, subscription: str) -> None:
        from azext_iot.adr.ui.core.rbac import can_grant_roles

        verdict = can_grant_roles(self.session, f"/subscriptions/{subscription}")
        self.app.call_from_thread(self._grant_rights_read, subscription, verdict)

    def _grant_rights_read(self, subscription: str, verdict) -> None:
        # A subscription switch during the probe would otherwise apply a stale answer.
        if self.context.get("subscription_id") != subscription:
            return
        self.context["can_grant_roles"] = verdict
        self.refresh_view()

    # -- rendering ---------------------------------------------------------

    def _render_review(self, text: Text) -> None:
        """The commit point: what will run, what you must run, what is already done."""
        plan = self.flow.build_plan()
        runnable = [item for item in plan if item.invoke is not None]
        manual = [item for item in plan if item.action == "manual"]
        blocked = [item for item in plan if item.action == "blocked"]

        if not runnable and not manual:
            text.append("Everything is already configured. Nothing to run.\n", style="#a3be8c")
            return

        if runnable:
            text.append(f"{len(runnable)} change(s) radr will make:\n", style="bold")
            for item in runnable:
                text.append(f"   {item.description}\n")
        else:
            text.append("No changes for radr to make.\n", style="dim")

        if manual:
            verdict = self.context.get("can_grant_roles")
            reason = (
                "your account cannot create role assignments here - this needs Owner or "
                "User Access Administrator (activate it in PIM and press r)"
                if verdict is False else
                "radr could not confirm whether your account may create role assignments"
            )
            text.append(
                f"\n{len(manual)} role assignment(s) you must run yourself, because "
                f"{reason}:\n",
                style="#ebcb8b",
            )
            for item in manual[:4]:
                text.append(f"   {item.description}\n", style="dim")
            if len(manual) > 4:
                text.append(f"   ... and {len(manual) - 4} more\n", style="dim")
            text.append("   press x to export them as a script for an administrator\n",
                        style="dim")

        if blocked:
            text.append(f"\n{len(blocked)} item(s) still blocked:\n", style="#bf616a")
            for item in blocked[:3]:
                text.append(f"   {item.description}: {item.blocked_reason}\n", style="dim")

        if runnable:
            text.append("\npress a to run these changes, or p for the full plan\n",
                        style="bold #88c0d0")

    #: What the customer has settled on for a step, shown beneath it on the rail. A list,
    #: because a step may hold several choices and "+3 more" hides the very thing the
    #: customer is trying to check before running the plan.
    def _chosen_lines(self, step_id: str) -> List[str]:
        single = {
            "subscription": self.context.get("subscription_name")
            or self.context.get("subscription_id"),
            "scope": self.context.get("resource_group_name"),
            "namespace": self.context.get("namespace_name"),
        }
        if step_id in single:
            value = single[step_id]
            return [value] if value else []
        if step_id == "dps":
            chosen = self.context.get("selected_dps")
            return [chosen.name] if chosen is not None else []
        if step_id in _MULTI_SELECT:
            chosen = self.context.get(_SELECTABLE[step_id]) or []
            names = [item.name for item in chosen[:_RAIL_CHOICE_LIMIT]]
            if len(chosen) > _RAIL_CHOICE_LIMIT:
                names.append(f"and {len(chosen) - _RAIL_CHOICE_LIMIT} more")
            return names
        return []

    def _advance(self, message: str = "") -> None:
        """Move to the next unsatisfied step once a choice is made.

        Without this the pane stays on the step just completed and the customer has to
        navigate manually, which defeats the point of a guided flow.
        """
        self._focus_step = None
        self._candidate_filter = ""
        if not self.is_mounted:
            return
        if message:
            self.flash(message, "success")
        self.refresh_view()
        self._reload_candidates()
        nxt = self.active_step()
        if nxt is not None and nxt.id in _PICKER_STEPS:
            try:
                self.query_one("#candidates", DataTable).focus()
            except Exception:  # noqa: BLE001 - focus is a convenience, never a failure
                pass

    def _pending_creation(self, step_id: str):
        """The creation queued for a step, if any."""
        entry = _CREATABLE.get(step_id)
        return self.context.get(entry[2]) if entry else None

    def active_step(self):
        """The step being worked on: an explicit jump, else the first unsatisfied one."""
        if self._focus_step is not None:
            for step in self.flow.steps:
                if step.id == self._focus_step:
                    return step
        return self.flow.current()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Arrowing through the rail changes which step the right-hand pane serves."""
        if self._syncing_rail:
            return
        rail = self.query_one("#step-list", ListView)
        index = rail.index
        # The rail lists visible steps only; indexing all steps selects the wrong one
        # as soon as a hidden step sits between two visible ones.
        steps = self.flow.visible_steps()
        if index is None or not (0 <= index < len(steps)):
            return
        step = steps[index]
        if step.id == self._focus_step:
            return
        self._focus_step = step.id
        self._render_body()
        self._reload_candidates()

    def action_goto_step(self) -> None:
        """Jump to a step by number, including ones already satisfied."""
        key = self.app.last_key_pressed if hasattr(self.app, "last_key_pressed") else None
        index = int(key) - 1 if key and key.isdigit() else None
        steps = self.flow.visible_steps()
        if index is None or not (0 <= index < len(steps)):
            return
        step = steps[index]
        self._focus_step = step.id
        self.flash(f"step {index + 1}: {step.title}", "info")
        self.refresh_view()
        self._reload_candidates()

    def refresh_view(self) -> None:
        self._render_rail()
        self._render_body()
        self._render_candidate_status()
        if hasattr(self.app, "sync_chrome"):
            self.app.sync_chrome(self)

    def _render_rail(self) -> None:
        rail = self.query_one("#step-list", ListView)
        if not self._state_loaded:
            rail.clear()
            return

        focused = self.active_step()
        index = 0
        self._syncing_rail = True
        rail.clear()
        for position, (step, state) in enumerate(self.flow.states()):
            mark, style = _STEP_MARKS[state]
            pending = self._pending_creation(step.id)
            # A step whose choices are made but not yet applied is neither pending nor
            # done. Leaving it looking untouched reads as "you still have work here",
            # which is the opposite of what selecting a hub just achieved.
            if state is not StepState.SATISFIED and step.is_planned(self.context):
                mark, style = _READY_MARK
            is_focused = focused is not None and step.id == focused.id
            # A pointer on the step being edited: the list highlight alone is easy to
            # lose track of once several steps are satisfied.
            pointer = "\u25b8 " if is_focused else "  "
            label = Text(f"{pointer}{mark}{position + 1} {step.title}",
                         style="bold" if is_focused else style)
            for chosen in self._chosen_lines(step.id):
                label.append(f"\n       {chosen}", style="#88c0d0")
            if pending is not None:
                label.append(f"\n       new: {pending.name}", style="#b48ead")
            if state is StepState.BLOCKED and is_focused:
                blockers = ", ".join(b.title for b in self.flow.blocking(step))
                reason = step.blocked_reason or f"requires: {blockers}"
                label.append(f"\n     {reason}", style="italic yellow")
            rail.append(ListItem(Label(label)))
            if focused is not None and step.id == focused.id:
                index = position
        rail.index = index
        self._syncing_rail = False

        done, total = self.flow.progress()
        self._progress_text = f"{done} of {total} required steps satisfied"

    def _render_body(self) -> None:
        body = self.query_one("#step-body", Static)
        if not self._state_loaded:
            body.update(Text("Reading the namespace to see what is already configured...",
                             style="dim"))
            self.query_one("#command-hint", Static).update("")
            return
        step = self.active_step()
        try:
            self.query_one("#work-pane", VerticalScroll).border_title = (
                step.title.lower() if step is not None else "summary"
            )
        except Exception:  # noqa: BLE001 - the title is decoration, never a failure
            pass
        if step is None:
            body.update(Text("Connectivity is configured. Press p to review the plan.", style="green"))
            self.query_one("#command-hint", Static).update("")
            return
        text = Text()
        text.append(f"{getattr(self, '_progress_text', '')}\n", style="dim")
        if step.id == "review":
            self._render_review(text)
            body.update(text)
            self._render_command_hint(step)
            return
        if step.id == "subscription":
            text.append("Press space to work in a different subscription.\n", style="dim")
        elif step.id == "scope":
            text.append("Press space to use an existing resource group, or n to create "
                        "one.\n", style="dim")
        elif step.id == "namespace":
            text.append("Press n to create a new namespace, or escape and pick an existing "
                        "one from the namespace list.\n", style="dim")
        elif step.id == "dps":
            text.append("Links a Device Provisioning Service to the namespace. Exactly one "
                        "may be linked, and it must be linked before any Hub. Press space to "
                        "use an existing one, or n to create one.\n", style="dim")
        elif step.id == "hub":
            text.append("Links IoT Hubs to the namespace. Hubs already registered on the "
                        "selected DPS are recommended; others will link but will not receive "
                        "device allocations. Press space to select as many as you need, n to "
                        "create one, then d when you are done.\n",
                        style="dim")
        elif step.id == "su":
            text.append("Optional. Links Software Updates instances so this namespace can "
                        "run update jobs. Press space to select as many as you need, n to "
                        "create one, then d when you are done - or d now to skip.\n",
                        style="dim")
        elif step.id == "permissions":
            text.append(
                "Linking only works if the namespace and the linked resource can call each "
                "other, which needs two role assignments per resource:\n"
                "  the namespace identity -> Contributor on the DPS/Hub "
                "(plus IoT Hub Data Contributor on a Hub)\n"
                "  the DPS/Hub identity   -> Contributor on the namespace\n",
                style="dim",
            )
            text.append(self._grant_rights_note(), style="dim")
        pending = self._pending_summary()
        if pending:
            text.append(f"\nto be created: {pending}\n", style="#b48ead")
        selections = self._selection_summary()
        if selections:
            text.append(f"selected: {selections}\n", style="green")
        runnable = [item for item in self.flow.build_plan() if item.invoke is not None]
        if runnable:
            text.append(
                f"\n{len(runnable)} change(s) ready - go to 'Review and run' to apply them\n",
                style="bold #88c0d0",
            )
        body.update(text)
        self._render_command_hint(step)

    def _grant_rights_note(self) -> str:
        """Say plainly whether radr will make the grants, and if not, why not."""
        verdict = self.context.get("can_grant_roles")
        if verdict is True:
            return ("Your account may create role assignments here, so radr will make "
                    "these for you as part of the run.\n")
        if verdict is False:
            return ("Your account may not create role assignments here, so radr will list "
                    "them instead. Activate Owner or User Access Administrator (PIM) and "
                    "press r, or press x to export them for an administrator.\n")
        return ("radr is checking whether your account may create role assignments...\n")

    def _pending_summary(self) -> str:
        parts = []
        for step_id, (_kind, label, context_key) in _CREATABLE.items():
            request = self.context.get(context_key)
            if request is not None:
                parts.append(f"create {label} '{request.name}'")
        return "; ".join(parts)

    def _selection_summary(self) -> str:
        parts = []
        dps = self.context.get("selected_dps")
        if dps is not None:
            parts.append(f"provisioning service {dps.name}")
        for step_id, noun in _MULTI_SELECT.items():
            chosen = self.context.get(_SELECTABLE[step_id]) or []
            if chosen:
                parts.append(f"{noun}s " + ", ".join(item.name for item in chosen))
        return "; ".join(parts)

    def _render_command_hint(self, step) -> None:
        items = [item for item in self.flow.build_plan() if item.key.startswith(step.id)]
        command = next((item.command for item in items if item.command), "")
        hint = self.query_one("#command-hint", Static)
        hint.update(Text(command, style="cyan") if command else Text(""))

    # -- candidates --------------------------------------------------------

    def _reload_candidates(self) -> None:
        if self.catalog is None:
            return
        step = self.active_step()
        if step is None or step.id == self._candidates_for:
            return
        if step.id not in _PICKER_STEPS:
            self._candidates, self._candidates_for = [], step.id
            self._show_candidates([])
            return
        self._candidates_for = step.id
        self._candidate_filter = ""
        self._candidates_loading = True
        self._render_candidate_status()
        self.run_worker(self._load_candidates, thread=True, name="onboard-candidates")

    def _render_candidate_status(self) -> None:
        """Say what the picker is doing; an empty table alone is ambiguous."""
        status = self.query_one("#candidate-status", Static)
        step = self.active_step()
        if step is None or step.id not in _PICKER_STEPS:
            status.update("")
            return
        if self._candidates_loading:
            noun = _PICKER_NOUNS.get(step.id, "candidates")
            status.update(Text(f"finding {noun} in this subscription...", style="dim"))
        elif not self._candidates:
            errors = getattr(self.catalog, "errors", None) or {}
            failure = errors.get({"scope": "resource_group"}.get(step.id, step.id))
            if failure:
                status.update(
                    Text(f"could not list candidates: {failure}", style="bold #bf616a")
                )
            else:
                status.update(Text(_EMPTY_GUIDANCE.get(step.id, ""), style="#ebcb8b"))
        else:
            shown = len(self._visible_candidates())
            total = len(self._candidates)
            summary = f"{shown} of {total}" if shown != total else f"{total}"
            hint = (
                "space selects (choose several), d moves on, / filters"
                if step.id in _MULTI_SELECT
                else "space selects, / filters"
            )
            status.update(Text(f"{summary} candidates - {hint}", style="dim"))

    def _load_candidates(self) -> None:
        """Enumerate selectable resources on a worker; pickers never block the UI."""
        step = self.active_step()
        if step is None or self.catalog is None:
            return
        try:
            if step.id == "subscription":
                candidates = [
                    evaluate(resource, require_identity=False)
                    for resource in self.catalog.subscriptions()
                ]
            elif step.id == "scope":
                candidates = [
                    evaluate(resource, require_identity=False)
                    for resource in self.catalog.resource_groups()
                ]
            elif step.id == "namespace":
                candidates = [
                    evaluate(resource, require_identity=False)
                    for resource in self.catalog.namespaces(
                        self.session, self.context.get("resource_group_name")
                    )
                ]
            elif step.id == "dps":
                resources = self.catalog.provisioning_services()
                candidates = [
                    evaluate(resource, namespace_location=self._namespace_location())
                    for resource in resources
                ]
            elif step.id == "hub":
                dps = self.context.get("selected_dps")
                registered = None
                if dps is not None:
                    registered = self.catalog.registered_hub_names(dps.raw or {})
                candidates = [
                    evaluate(resource, namespace_location=self._namespace_location(),
                             registered_hub_names=registered)
                    for resource in self.catalog.hubs()
                ]
            elif step.id == "su":
                candidates = [
                    evaluate(resource, require_identity=False)
                    for resource in self.catalog.update_instances()
                ]
            else:
                candidates = []
        except Exception as error:  # noqa: BLE001 - an unavailable provider yields no candidates
            diagnostics.exception("candidate enumeration failed: %s", error)
            candidates = []
        self.app.call_from_thread(self._show_candidates, rank(candidates))

    def _namespace_location(self) -> Optional[str]:
        return (self.context.get("namespace") or {}).get("location")

    def _visible_candidates(self) -> List:
        needle = (self._candidate_filter or "").strip().lower()
        if not needle:
            return list(self._candidates)
        return [
            candidate for candidate in self._candidates
            if needle in candidate.name.lower()
            or needle in (candidate.resource_group or "").lower()
            or needle in (candidate.location or "").lower()
        ]

    def _show_candidates(self, candidates) -> None:
        self._candidates = candidates
        self._candidates_loading = False
        self._render_candidate_status()
        self._paint_candidates()

    def _paint_candidates(self) -> None:
        table = self.query_one("#candidates", DataTable)
        table.clear(columns=True)
        candidates = self._visible_candidates()
        if not candidates:
            return
        # Explicit widths: the verdict decides the choice, so it must never be the
        # column pushed off screen.
        step = self.active_step()
        step_id = step.id if step is not None else ""
        columns = _PICKER_COLUMNS.get(step_id, _DEFAULT_PICKER_COLUMNS)
        for label, width in columns:
            table.add_column(label, width=width)

        for candidate in candidates:
            style = _VERDICT_STYLES.get(candidate.verdict, "")
            chosen = self._is_chosen(candidate)
            prefix = "* " if chosen else "  "
            name = Text(
                f"{prefix}{candidate.name}",
                style="bold" if (candidate.recommended or chosen) else "",
            )
            if step_id == "subscription":
                row = (name, Text(candidate.resource_id, style="dim"))
            elif step_id == "scope":
                row = (name, candidate.location)
            elif step_id == "namespace":
                row = (name, candidate.resource_group, candidate.location)
            else:
                row = (
                    name,
                    candidate.resource_group,
                    candidate.location,
                    candidate.identity[:14],
                    Text(candidate.describe(), style=style),
                )
            table.add_row(*row, key=candidate.resource_id or candidate.name)

    def _is_chosen(self, candidate) -> bool:
        """Already queued for linking, so the picker can mark it."""
        single = self.context.get("selected_dps")
        if single is not None and single.resource_id == candidate.resource_id:
            return True
        for key in ("selected_hubs", "selected_sus"):
            if any(chosen.resource_id == candidate.resource_id
                   for chosen in (self.context.get(key) or [])):
                return True
        return False

    def _selected_candidate(self):
        table = self.query_one("#candidates", DataTable)
        visible = self._visible_candidates()
        if table.row_count == 0 or not visible:
            return None
        index = table.cursor_coordinate.row
        return visible[index] if 0 <= index < len(visible) else None

    # -- actions -----------------------------------------------------------

    def _switch_subscription(self, candidate) -> None:
        """Point the whole session at another subscription.

        Clients are built per subscription, so cached providers, cached rows and the
        candidate catalog must all be discarded together.
        """
        subscription_id = candidate.resource_id or candidate.name
        self.context["subscription_id"] = subscription_id
        self.context["subscription_name"] = candidate.name
        self.context.pop("resource_group_name", None)
        if self.session is not None:
            self.session.cmd.cli_ctx.data["subscription_id"] = subscription_id
            self.session.scope.subscription_id = subscription_id
            self.session.scope.subscription_name = candidate.name
            self.session._providers.clear()
        if self.catalog is not None:
            self.catalog.clear()
        store = getattr(self.app, "store", None)
        if store is not None:
            store.clear()
        # Grant rights are per subscription, so the previous answer no longer applies.
        self.context.pop("can_grant_roles", None)
        self._advance(f"subscription {candidate.name}")
        self._probe_grant_rights()

    def action_create_new(self) -> None:
        """Open the inline creation form for the active step."""
        step = self.active_step()
        if step is None or step.id not in _CREATABLE:
            self.flash("nothing to create at this step", "warning")
            return
        kind, label, _ = _CREATABLE[step.id]
        namespace = self.context.get("namespace") or {}
        location = namespace.get("location") or self.context.get("location") or ""
        base = self.context.get("namespace_name") or ""

        form = self.query_one("#create-form", Vertical)
        self.query_one("#create-title", Label).update(
            Text.assemble(
                (f"New {label}", "bold"),
                ("  - created when you run the setup", "dim"),
            )
        )
        self.query_one("#create-name", Input).value = (
            f"{base}-{kind}" if base and kind not in ("namespace", "resource_group") else ""
        )
        self.query_one("#create-rg", Input).value = self.context.get("resource_group_name") or ""
        self.query_one("#create-location", Input).value = location
        self.query_one("#create-error", Static).update("")
        # A resource group carries its own name; the group field would be circular.
        shows_group = kind != "resource_group"
        self.query_one("#create-rg", Input).display = shows_group
        self.query_one("#create-rg-label", Label).display = shows_group
        form.display = True
        self.query_one("#create-name", Input).focus()

    def _close_form(self) -> None:
        self.query_one("#create-form", Vertical).display = False
        self.query_one("#candidate-filter", Input).display = False
        self.query_one("#candidates", DataTable).focus()

    def _submit_form(self) -> None:
        step = self.active_step()
        if step is None or step.id not in _CREATABLE:
            self._close_form()
            return
        kind, _label, context_key = _CREATABLE[step.id]

        name = self.query_one("#create-name", Input).value.strip()
        location = self.query_one("#create-location", Input).value.strip()
        resource_group = (
            name if kind == "resource_group"
            else self.query_one("#create-rg", Input).value.strip()
        )
        problem = validate_name(name)
        if problem is None and not resource_group:
            problem = "a resource group is required"
        if problem is None and not location:
            problem = "a region is required"
        if problem:
            self.query_one("#create-error", Static).update(Text(problem, style="bold red"))
            return

        request = CreateRequest(kind=kind, name=name, resource_group_name=resource_group,
                                location=location)
        self._close_form()
        self._accept_create(step.id, context_key, request)

    def action_start_filter(self) -> None:
        field = self.query_one("#candidate-filter", Input)
        field.display = True
        field.value = self._candidate_filter
        field.focus()

    def _end_filter(self, keep: bool) -> None:
        field = self.query_one("#candidate-filter", Input)
        if not keep:
            self._candidate_filter = ""
            field.value = ""
        field.display = False
        self.query_one("#candidates", DataTable).focus()
        self._paint_candidates()
        self._render_candidate_status()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "candidate-filter":
            self._candidate_filter = event.value
            self._paint_candidates()
            self._render_candidate_status()

    def _accept_create(self, step_id: str, context_key: str,
                       request: Optional[CreateRequest]) -> None:
        """Record a creation request. Nothing is created until apply."""
        if request is None:
            return
        self.context[context_key] = request
        if step_id == "scope":
            # A new resource group fixes both the group and the region for everything below.
            self.context["resource_group_name"] = request.name
            self.context["location"] = request.location
        if step_id == "namespace":
            # Everything downstream is scoped to the namespace being created.
            self.context["namespace_name"] = request.name
            self.context["resource_group_name"] = request.resource_group_name
            self.context["location"] = request.location
        diagnostics.log("queued creation: %s '%s' in %s/%s", request.kind, request.name,
                        request.resource_group_name, request.location)
        if self.is_mounted:
            if step_id == "hub":
                self.flash(f"{request.label} '{request.name}' will be created", "success")
                self.refresh_view()
                self._reload_candidates()
            else:
                self._advance(
                    f"{request.label} '{request.name}' will be created when you run setup"
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "create-confirm":
            self._submit_form()
        elif event.button.id == "create-cancel":
            self._close_form()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "candidate-filter":
            self._end_filter(keep=True)
            return
        self._submit_form()

    def action_select(self) -> None:
        candidate = self._selected_candidate()
        step = self.active_step()
        if candidate is None or step is None:
            return
        if not candidate.selectable:
            self.flash(f"{candidate.name} cannot be used: {candidate.reason}", "warning")
            return
        if step.id == "review":
            self.action_apply()
            return
        if step.id == "subscription":
            self._switch_subscription(candidate)
            return
        if step.id == "namespace":
            self.context["namespace_name"] = candidate.name
            self.context["resource_group_name"] = (
                candidate.resource_group or self.context.get("resource_group_name")
            )
            self.context.pop("create_namespace", None)
            self.context["namespace"] = candidate.raw or {}
            self._state_loaded = True
            self._advance(f"namespace {candidate.name}")
            return
        if step.id == "scope":
            self.context["resource_group_name"] = candidate.name
            self.context["location"] = candidate.location or self.context.get("location", "")
            self._advance(f"resource group {candidate.name}")
            return
        if step.id == "dps":
            self.context["selected_dps"] = candidate
            self.context.pop("create_dps", None)
            self._advance(f"provisioning service {candidate.name}")
            return
        if step.id in _MULTI_SELECT:
            self._toggle_choice(step.id, candidate)
        self.refresh_view()
        self._paint_candidates()

    def _toggle_choice(self, step_id: str, candidate) -> None:
        """Add or remove one resource on a step that accepts several.

        Toggling rather than appending: pressing select twice on the same row used to
        queue it twice, which then failed at link time with a duplicate endpoint.
        """
        noun = _MULTI_SELECT[step_id]
        key = _SELECTABLE[step_id]
        chosen = list(self.context.get(key) or [])
        if any(item.resource_id == candidate.resource_id for item in chosen):
            chosen = [item for item in chosen if item.resource_id != candidate.resource_id]
            self.flash(f"removed {noun} {candidate.name} ({len(chosen)} selected)", "info")
        else:
            chosen.append(candidate)
            self.flash(
                f"{noun} {candidate.name} selected ({len(chosen)} total) - "
                "select more, or press d when done",
                "success",
            )
        self.context[key] = chosen
        self.context.pop({"hub": "create_hub", "su": "create_su"}[step_id], None)

    def action_done_step(self) -> None:
        """Finish a multi-select step and move on.

        Selecting does not advance on these steps, because linking a second hub is the
        normal case; this is the explicit "that is all of them" signal.
        """
        step = self.active_step()
        if step is None:
            return
        if step.id not in _MULTI_SELECT:
            self._advance()
            return
        chosen = self.context.get(_SELECTABLE[step.id]) or []
        pending = self.context.get({"hub": "create_hub", "su": "create_su"}[step.id])
        if not chosen and pending is None:
            if step.optional:
                self._advance(f"skipped {step.title.lower()}")
            else:
                self.flash(
                    f"select at least one {_MULTI_SELECT[step.id]} first, or press n to "
                    "create one",
                    "warning",
                )
            return
        count = len(chosen) + (1 if pending is not None else 0)
        self._advance(f"{count} {_MULTI_SELECT[step.id]}(s) will be linked")

    def action_show_plan(self) -> None:
        self.app.push_screen(PlanDialog(self.flow))

    def action_apply(self) -> None:
        """Run the plan, including the role grants when this account may create them."""
        if getattr(self.app, "read_only", False):
            self.flash("read-only session: apply is disabled", "warning")
            return
        runnable = [item for item in self.flow.build_plan() if item.invoke is not None]
        if not runnable:
            blocked = [item for item in self.flow.build_plan() if item.action == "blocked"]
            if blocked:
                self.flash(f"nothing to apply: {blocked[0].blocked_reason}", "warning")
            else:
                self.flash("nothing to apply - this namespace is already configured", "info")
            return

        manual = [item for item in self.flow.build_plan() if item.action == "manual"]
        grants = sum(1 for item in runnable if item.key.startswith("grant-"))
        note = f"{len(runnable)} operation(s) will run in order."
        if grants:
            note += (
                f" {grants} of them are role assignments radr will create for you, "
                "because your account is allowed to."
            )
        if manual:
            note += (
                f" {len(manual)} role assignment(s) are NOT applied - press escape, then x, "
                "to export them for someone with Owner or User Access Administrator."
            )
        preview = "\n".join(item.command for item in runnable)
        self.app.push_screen(
            CommandPreviewDialog("Run setup", preview, note=note),
            lambda approved: self._start_apply(runnable) if approved else None,
        )

    def _start_apply(self, items) -> None:
        operation = self.app.tracker.start(
            label="Guided setup",
            target=self.context.get("namespace_name") or "namespace",
            command=items[0].command,
            refreshes=("namespace", "link"),
        )
        self.run_worker(
            lambda: self._apply_items(items, operation), thread=True, name="onboard-apply"
        )

    def _apply_items(self, items, operation) -> None:
        """Execute in order, stopping at the first failure: later items depend on earlier."""
        tracker = self.app.tracker
        current = None
        try:
            for item in items:
                current = item
                diagnostics.log("apply: %s | %s", item.key, item.command)
                operation.command = item.command
                poller = item.invoke(self.session, self.context)
                diagnostics.log("apply started: %s", item.key)
                if poller is not None and hasattr(poller, "result"):
                    tracker._waiter(poller)
                diagnostics.log("apply completed: %s", item.key)
        except Exception as error:  # noqa: BLE001 - surfaced through the tray
            step = current.description if current is not None else "apply"
            diagnostics.exception("apply failed at '%s': %s", step, error)
            tracker.fail(operation, RuntimeError(f"{step}: {error}"))
        else:
            diagnostics.log("apply finished successfully")
            tracker.succeed(operation)
        self.app.call_from_thread(self._apply_finished)

    def _apply_finished(self) -> None:
        self.action_reload()
        if hasattr(self.app, "_refresh_tray"):
            self.app._refresh_tray()

    def action_export(self) -> None:
        script = self.flow.script()
        try:
            self.app.copy_to_clipboard(script)
            self.flash("plan script copied to clipboard", "success")
        except Exception:  # noqa: BLE001 - clipboard is unavailable over plain SSH
            self.flash("clipboard unavailable; press p to read the plan", "warning")

    def action_reload(self) -> None:
        """Re-derive every step from live state, which is what makes the flow resumable."""
        self._state_loaded = False
        self.refresh_view()
        self.run_worker(self._reload_namespace, thread=True, name="onboard-reload")
        # Grant rights are live state too: activating Owner in PIM should be picked up
        # here, which is exactly what the review panel tells the customer to do.
        self.context.pop("_grant_probe_for", None)
        self._probe_grant_rights()

    def _reload_namespace(self) -> None:
        try:
            namespace = self.session.call(
                self.session.provider("namespace").show,
                namespace_name=self.context.get("namespace_name"),
                resource_group_name=self.context.get("resource_group_name"),
            )
        except Exception:  # noqa: BLE001 - a missing namespace simply leaves the step unmet
            namespace = {}
        self.app.call_from_thread(self._apply_namespace, namespace)

    def _apply_namespace(self, namespace) -> None:
        self.context["namespace"] = namespace or {}
        self._state_loaded = True
        self.refresh_view()
        # Which candidates matter depends on the current step, which is only known now.
        self._reload_candidates()

    def action_back(self) -> None:
        """Escape precedence: close the form first, then leave."""
        field = self.query_one("#candidate-filter", Input)
        if field.display:
            self._end_filter(keep=False)
            return
        form = self.query_one("#create-form", Vertical)
        if form.display:
            self._close_form()
            return
        self.app.pop_screen_safely()

    def breadcrumb(self) -> str:
        return "guided setup"

    def guide(self) -> Guide:
        """Orientation for the one page that changes infrastructure.

        The note is written from live state rather than fixed, because the single most
        common question here - "will this create the role assignments or not?" - has a
        different answer depending on who is signed in.
        """
        verdict = self.context.get("can_grant_roles")
        if verdict is True:
            grants = ("Your account may create role assignments, so radr will make them "
                      "as part of the run.")
        elif verdict is False:
            grants = ("Your account may not create role assignments, so those are listed "
                      "for an administrator instead of run.")
        else:
            grants = "radr is still checking whether it may create the role assignments."
        return Guide(
            about=(
                "Choose the namespace and the resources to link to it, on the left. Nothing "
                "is changed until you reach 'Review and run' and press a."
            ),
            runs=(
                "az iot adr ns create / link dps add / link hub add / link su add, plus "
                "az role assignment create  ·  the exact commands are on the plan (p)"
            ),
            note=(
                f"Exactly one DPS per namespace, and it must be linked before any hub. {grants}"
            ),
        )


class PlanDialog(ChromeScreen):
    """The plan: what exists, what will be created, what is blocked, and the commands."""

    BINDINGS = [Binding("escape", "back", "Back", show=True)]

    _ACTION_STYLES = {
        "exists": "green",
        "create": "cyan",
        "modify": "cyan",
        "manual": "yellow",
        "blocked": "bold red",
    }

    def __init__(self, flow, **kwargs):
        super().__init__(**kwargs)
        self.flow = flow

    def compose_content(self) -> ComposeResult:
        with VerticalScroll(classes="pane", id="plan-pane"):
            yield Static(id="plan-body")

    def on_mount(self) -> None:
        self.query_one("#plan-pane", VerticalScroll).border_title = "plan"
        text = Text()
        text.append("nothing has been applied yet\n\n", style="bold")
        for item in self.flow.build_plan():
            style = self._ACTION_STYLES.get(item.action, "")
            text.append(f"{item.action.upper():<8}", style=style)
            text.append(f"{item.description}\n")
            if item.blocked_reason:
                text.append(f"         {item.blocked_reason}\n", style="yellow")
            if item.command:
                text.append(f"         {item.command}\n", style="cyan")
        text.append("\npress x on the previous screen to copy this as a script", style="dim")
        self.query_one("#plan-body", Static).update(text)
        if hasattr(self.app, "sync_chrome"):
            self.app.sync_chrome(self)

    def action_back(self) -> None:
        self.app.pop_screen_safely()

    def breadcrumb(self) -> str:
        return "plan"

    def guide(self) -> Guide:
        return Guide(
            about=(
                "Every operation guided setup will perform, in the order it will run them, "
                "with the equivalent az command for each."
            ),
            note=(
                "Grants must land before the links that depend on them, which is why a "
                "propagation wait sits between the two. Press x to export this as a script."
            ),
        )
