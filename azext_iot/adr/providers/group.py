# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Dict, List, Optional

from azure.cli.core.azclierror import ArgumentUsageError
from knack.log import get_logger
from rich.console import Console

from azext_iot.adr.common import (
    JOB_ACTIVE_PROVISIONING_STATES,
    JOB_RUN_IN_FLIGHT_STATUSES,
    GroupType,
)
from azext_iot.adr.providers.base import ADRProvider
from azext_iot.common.utility import wait_for_terminal_state

console = Console()
logger = get_logger(__name__)


_GROUP_DELETE_BLOCKED_MSG = (
    "Cannot delete group '{group}': {n} job(s) targeting it cannot be safely deleted right now. "
    "Resolve the blocking jobs first (cancel in-flight runs, or wait for ARM operations to settle), then retry:\n{details}"
)


class GroupProvider(ADRProvider):
    def __init__(self, cmd):
        super(GroupProvider, self).__init__(cmd)

    def create(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
        query_string: str,
        group_type: str = GroupType.device.value,
        location: Optional[str] = None,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """Create a group in the namespace."""
        if not location:
            location = self._ensure_location(self.cmd.cli_ctx, resource_group_name, location)

        inner_props = {
            "groupType": group_type,
            "query": query_string,
        }
        if display_name is not None:
            inner_props["displayName"] = display_name
        if description is not None:
            inner_props["description"] = description

        resource = {
            "location": location,
            "properties": inner_props,
        }
        if tags:
            resource["tags"] = tags

        poller = self.client.groups.begin_create_or_replace(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
            resource=resource,
        )
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(
            f"Creating group '{group_name}' in namespace {namespace_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)

    def update(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
        **kwargs,
    ):
        """Update a group in the namespace.

        Only mutable fields (``displayName``, ``description``, ``tags``) are accepted.
        ``groupType`` and ``query`` are immutable after creation (spec visibility
        ``Lifecycle.Read, Lifecycle.Create``) and are intentionally not exposed
        on this command.
        """
        inner_props = {}
        if display_name is not None:
            inner_props["displayName"] = display_name
        if description is not None:
            inner_props["description"] = description

        properties = {}
        if inner_props:
            properties["properties"] = inner_props
        if tags is not None:
            properties["tags"] = tags

        poller = self.client.groups.begin_update(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
            properties=properties,
        )
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(
            f"Updating group '{group_name}' in namespace {namespace_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, group_name: str, namespace_name: str, resource_group_name: str):
        return self.client.groups.get(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
        )

    def list(self, namespace_name: str, resource_group_name: str):
        return list(
            self.client.groups.list_by_namespace(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
            )
        )

    def delete(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        """Delete a group from the namespace, cascading to referencing jobs.

        A job whose ``target.targetResourceId`` references this group becomes
        inert once the group is removed (it has no devices to act on), so we
        delete those jobs *before* deleting the group. If any referencing job
        is in a state where it cannot be safely deleted right now (ARM
        mid-operation provisioningState or has in-flight runs), the whole
        operation is blocked with a per-job explanation — the user must
        resolve those jobs before retrying.

        The full job inventory (including non-blocking entries) is surfaced
        as a warning before any deletion so the user sees the cascade scope.
        """
        referencing_jobs = self._list_referencing_jobs(
            group_name=group_name,
            namespace_name=namespace_name,
            resource_group_name=resource_group_name,
        )

        if referencing_jobs:
            self._render_job_inventory(group_name, referencing_jobs)
            blocked = [j for j in referencing_jobs if j["blocked_reason"]]
            if blocked:
                details = "\n".join(
                    f"  - {j['name']}: {j['blocked_reason']}" for j in blocked
                )
                raise ArgumentUsageError(
                    _GROUP_DELETE_BLOCKED_MSG.format(
                        group=group_name, n=len(blocked), details=details
                    )
                )
            self._cascade_delete_jobs(
                referencing_jobs,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
            )

        poller = self.client.groups.begin_delete(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
        )
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(
            f"Deleting group '{group_name}' from namespace {namespace_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)

    def _list_referencing_jobs(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> List[dict]:
        """Return an inventory of jobs whose target.targetResourceId points at *group_name*.

        Each entry is::

            {
                "name": str,
                "provisioning_state": Optional[str],
                "in_flight_runs": list[str],   # run names in Scheduled/Queued/Active
                "blocked_reason": Optional[str],
            }

        Best-effort: any exception while listing jobs yields an empty list so
        the cascade probe never blocks deletion on a probe-failure (RBAC,
        transient SDK error). Per-job run enumeration is also best-effort — a
        run-list failure on a single job is logged and treated as "no
        in-flight runs known" for that entry.

        TODO: this currently enumerates *all* jobs in the namespace and filters
        client-side because the 2026-11-02-preview SDK does not expose a
        server-side ``$filter`` on ``targetResourceId``. When the backend adds
        that filter, switch to it so the probe scales to large namespaces.
        """
        try:
            jobs = list(
                self.client.jobs.list_by_namespace(
                    resource_group_name=resource_group_name,
                    namespace_name=namespace_name,
                )
            )
        except Exception as ex:  # noqa: BLE001 - best-effort probe
            logger.warning(
                "Unable to enumerate jobs for group '%s' (continuing with delete): %s",
                group_name,
                ex,
            )
            return []

        suffix = f"/groups/{group_name}".lower()
        inventory: List[dict] = []
        for j in jobs:
            props = j.get("properties") or {}
            target_id = ((props.get("target") or {}).get("targetResourceId") or "")
            # ARM IDs are case-insensitive — compare lowercased suffix.
            if not target_id.lower().endswith(suffix):
                continue
            name = j.get("name", "<unknown>")
            prov_state = props.get("provisioningState")
            in_flight_runs = self._list_in_flight_runs_for_job(
                job_name=name,
                namespace_name=namespace_name,
                resource_group_name=resource_group_name,
            )
            blocked_reason: Optional[str] = None
            if in_flight_runs:
                blocked_reason = (
                    f"{len(in_flight_runs)} in-flight run(s): "
                    f"{', '.join(in_flight_runs)}"
                )
            elif prov_state in JOB_ACTIVE_PROVISIONING_STATES:
                blocked_reason = (
                    f"provisioningState='{prov_state}' (ARM operation in progress)"
                )
            inventory.append({
                "name": name,
                "provisioning_state": prov_state,
                "in_flight_runs": in_flight_runs,
                "blocked_reason": blocked_reason,
            })
        return inventory

    def _list_in_flight_runs_for_job(
        self,
        job_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> List[str]:
        """Return identifiers of in-flight runs for *job_name* (best-effort)."""
        try:
            runs = self.client.job_runs.list_by_job(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                job_name=job_name,
            )
            return [
                r.get("name", "<unknown>")
                for r in runs
                if (r.get("properties") or {}).get("status") in JOB_RUN_IN_FLIGHT_STATUSES
            ]
        except Exception as ex:  # noqa: BLE001 - best-effort probe
            logger.warning(
                "Unable to enumerate runs for job '%s' (treating as no in-flight runs): %s",
                job_name,
                ex,
            )
            return []

    @staticmethod
    def _render_job_inventory(group_name: str, inventory: List[dict]) -> None:
        """Emit a structured warning listing each referencing job and its delete-readiness."""
        logger.warning(
            "Group '%s' has %d referencing job(s); cascading delete (blocked entries marked [BLOCKED]):",
            group_name,
            len(inventory),
        )
        for j in inventory:
            state_str = j["provisioning_state"] or "<unknown>"
            run_str = (
                f"in-flight runs: {len(j['in_flight_runs'])}"
                if j["in_flight_runs"]
                else "no in-flight runs"
            )
            marker = " [BLOCKED]" if j["blocked_reason"] else ""
            logger.warning(
                "  - %s (provisioningState=%s, %s)%s",
                j["name"],
                state_str,
                run_str,
                marker,
            )

    def _cascade_delete_jobs(
        self,
        inventory: List[dict],
        namespace_name: str,
        resource_group_name: str,
    ) -> None:
        """Synchronously delete each referencing job before deleting the group.

        Sequential rather than parallel because the cascade is expected to be
        small (handful of jobs per group) and serial deletes give the user a
        predictable, debuggable failure point if one of them errors.
        """
        for j in inventory:
            logger.warning("Deleting referencing job '%s'...", j["name"])
            poller = self.client.jobs.begin_delete(
                resource_group_name=resource_group_name,
                namespace_name=namespace_name,
                job_name=j["name"],
            )
            wait_for_terminal_state(poller)

    def refresh(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
        **kwargs,
    ):
        """Trigger an asynchronous group-membership refresh."""
        poller = self.client.groups.begin_refresh_members(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
        )
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(
            f"Refreshing members of group '{group_name}' in namespace {namespace_name}..."
        ):
            return wait_for_terminal_state(poller, **kwargs)

    def show_members(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> list:
        """Preview a sample of group members (synchronous, ≤10).

        The SDK returns ``{"members": ["device-name", ...]}``. Unwrap to the
        member list to align with the sibling ``link hub list`` projection
        convention in [link.py](azext_iot/adr/providers/link.py).
        """
        response = self.client.groups.preview_members(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
        )
        return (response or {}).get("members") or []

    def count(
        self,
        group_name: str,
        namespace_name: str,
        resource_group_name: str,
    ) -> int:
        """Return the current member count of the group (synchronous).

        The SDK returns ``{"count": N}``. Unwrap to the integer.
        """
        response = self.client.groups.get_current_member_count(
            resource_group_name=resource_group_name,
            namespace_name=namespace_name,
            group_name=group_name,
        )
        return (response or {}).get("count") or 0
