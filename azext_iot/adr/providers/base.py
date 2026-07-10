# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from typing import Optional

from azure.cli.core.azclierror import AzureResponseError, ResourceNotFoundError
from azure.core.exceptions import HttpResponseError
from azure.core.rest import HttpRequest
from knack.log import get_logger
from rich.console import Console

from azext_iot._factory import adr_service_factory
from azext_iot.constants import LRO_POLL_RETRIES, LRO_POLL_WAIT_SEC
from azext_iot.common.utility import wait_for_terminal_state

__all__ = ["ADRProvider", "console"]

logger = get_logger(__name__)

# Shared Rich console for all ADR providers. Declared once here (instead of a
# module-level `Console()` in every provider) so spinners/print styling stay consistent.
console = Console()


# ---------------------------------------------------------------------------
# TEMPORARY WORKAROUND — the Device Registry service is under active development.
#
# ADR mutations are long-running operations (LROs). The status URL the service
# returns (via the ``Azure-AsyncOperation`` header) points at the DIRECT
# resource-provider host (``control-plane.prod.<region>.iotadr.net``), NOT at
# ARM. That host currently requires an ARM PoP (proof-of-possession) token that
# neither the Azure SDK poller nor a plain bearer client sends, so polling the
# async-operation URL returns HTTP 500 "ARM PoP token authentication failed"
# even though the mutation itself succeeds (HTTP 202). Per the Device Registry
# team this async-status implementation is incomplete/temporary; until it is
# fixed we poll the resource's own ``provisioningState`` instead. This matches
# the Device Registry team's own reference tool (Create-AdrNamespace), which
# likewise polls provisioningState "rather than the broken Azure-AsyncOperation
# URL", so this is the sanctioned approach and not merely a client-side hack.
#
# TO REVERT once the backend is fixed: set POLL_PROVISIONING_STATE_WORKAROUND to
# ``False`` (or delete this block, the workaround branch in ``_await_terminal``
# and ``_poll_provisioning_state``). No command call sites need to change.
# ---------------------------------------------------------------------------
POLL_PROVISIONING_STATE_WORKAROUND = True

# Terminal ARM ``provisioningState`` values.
_PROVISIONING_SUCCEEDED = "Succeeded"
_PROVISIONING_FAILURES = ("Failed", "Canceled")

# Only PUT/PATCH/DELETE LROs address the resource itself, so their initial
# request URL can be GET-polled for ``provisioningState``. POST-style action
# LROs (synchronize, revoke, refresh, run, ...) have no such pollable resource
# URL, so they fall back to the default SDK polling.
_RESOURCE_MUTATION_METHODS = ("PUT", "PATCH", "DELETE")


class ADRProvider(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.client = adr_service_factory(cmd.cli_ctx)

    def _wait(self, poller, status_message: str, **kwargs):
        """Block on a long-running-operation poller, honoring ``--no-wait``.

        This captures the epilogue shared by nearly every mutating ADR command:
        pop ``no_wait`` from kwargs and return the poller immediately when set,
        otherwise show ``status_message`` in a spinner while waiting for the
        operation to reach a terminal state. Remaining kwargs are forwarded to
        ``_await_terminal`` (e.g. polling interval overrides).
        """
        no_wait = kwargs.pop("no_wait", False)
        if no_wait:
            return poller
        with console.status(status_message):
            return self._await_terminal(poller, **kwargs)

    def _await_terminal(self, poller, **kwargs):
        """Wait for an ADR long-running operation to reach a terminal state.

        Single choke point used both by ``_wait`` and by the few commands that
        drive their poller directly. While the temporary workaround is enabled we
        poll the resource's ``provisioningState`` (see the module note above);
        otherwise we defer to the shared SDK helper.
        """
        if POLL_PROVISIONING_STATE_WORKAROUND:
            return self._poll_provisioning_state(poller, **kwargs)
        return wait_for_terminal_state(poller, **kwargs)

    @staticmethod
    def _poller_initial_request(poller):
        """Best-effort ``(url, method)`` of the mutating request a poller wraps.

        That request URL *is* the resource URL, which is exactly what we GET to
        read ``provisioningState``. Reaches through SDK internals defensively and
        returns ``(None, None)`` when the poller is not shaped as expected, so the
        caller can fall back to the default polling.
        """
        method = getattr(poller, "_polling_method", None)
        if method is None and hasattr(poller, "polling_method"):
            # Best-effort only; any failure just falls back to default polling.
            try:
                method = poller.polling_method()
            except Exception:  # noqa: BLE001
                method = None
        initial = getattr(method, "_initial_response", None)
        request = getattr(initial, "http_request", None)
        if request is None:
            request = getattr(getattr(initial, "http_response", None), "request", None)
        if request is None:
            return None, None
        return getattr(request, "url", None), (getattr(request, "method", "") or "").upper()

    @staticmethod
    def _extract_failure_detail(body):
        """Best-effort human-readable reason from a Failed resource body.

        Scans the endpoint collections (provisioning / messaging / updating) for an
        entry that carries its own status/error (this is where a failed link records
        *why* it failed), then falls back to a resource-level error object. Returns
        "" when nothing useful is present.
        """
        if not isinstance(body, dict):
            return ""
        props = body.get("properties") or {}
        for group in ("provisioning", "messaging", "updating"):
            endpoints = ((props.get(group) or {}).get("endpoints")) or {}
            if not isinstance(endpoints, dict):
                continue
            for name, endpoint in endpoints.items():
                if not isinstance(endpoint, dict):
                    continue
                status = endpoint.get("provisioningStatus") or endpoint.get("status") or {}
                if not isinstance(status, dict):
                    status = {}
                error = (
                    status.get("error")
                    or endpoint.get("error")
                    or endpoint.get("linkingError")
                    or {}
                )
                if not isinstance(error, dict):
                    error = {}
                message = error.get("message")
                ep_state = status.get("status") or endpoint.get("linkingState")
                if message:
                    return f"endpoint '{name}': {message}"
                if ep_state and str(ep_state).lower() == "failed":
                    return f"endpoint '{name}' is in a 'Failed' state"
        error = props.get("error") or body.get("error") or {}
        if isinstance(error, dict) and error.get("message"):
            code = error.get("code")
            return f"{code}: {error['message']}" if code else error["message"]
        return ""

    def _format_failure(self, state, body, response):
        """Build an actionable error message for a terminal Failed/Canceled LRO.

        Surfaces the backend's endpoint-level reason (when present) plus the GET's
        correlation id, instead of just the bare provisioningState, so the failure
        is diagnosable without hunting through the activity log.
        """
        message = f"The operation did not succeed (provisioningState='{state}')."
        detail = self._extract_failure_detail(body)
        if detail:
            message += f" {detail}" if detail.endswith((".", "!", "?")) else f" {detail}."
        if detail and "not authorized" in detail.lower():
            # AdrMiNotAuthorized: the link saga needs bidirectional role assignments (see the ADR
            # linking reference). Surface the concrete fix instead of just the backend's read hint.
            message += (
                " Linking requires role assignments: grant the namespace's managed identity"
                " Contributor on the linked resource (and 'IoT Hub Data Contributor' on IoT Hubs),"
                " and grant the linked resource's managed identity Contributor on the namespace."
            )
        headers = getattr(response, "headers", None)
        corr = headers.get("x-ms-correlation-request-id") if headers is not None else None
        if corr:
            message += f" Correlation id: {corr}."
        else:
            message += " Inspect the service activity log using the operation's correlation id."
        return message

    def _poll_provisioning_state(self, poller, wait_sec: int = LRO_POLL_WAIT_SEC, **_):
        """TEMPORARY: resolve an LRO by polling the resource's ``provisioningState``.

        See the module-level workaround note. Steps:

        * If the poller already completed inline (e.g. a create/PUT that returns
          the resource with a terminal ``provisioningState``), return its result
          directly - no async-operation/PoP hop needed.
        * Otherwise recover the resource URL from the poller and GET it until
          ``provisioningState`` is terminal: ``Succeeded`` (or a resource that
          exposes no ``provisioningState``) returns the body; ``Failed`` /
          ``Canceled`` raises ``AzureResponseError``.

        For a DELETE a 404 means the resource is gone (success). For any other
        method a 404 is treated as "not readable yet" and retried (the by-name
        read path can briefly 404 on some backend partitions). Action-style
        (POST) LROs and any poller we cannot introspect fall back to the default
        SDK polling, so behavior is never worse than before the workaround.
        """
        from time import sleep

        # Fast path: an LRO that completed inline is already terminal with no
        # further network calls, so return its result and skip the PoP-500 hop.
        if poller.done():
            return poller.result()

        url, method = self._poller_initial_request(poller)
        if not url or method not in _RESOURCE_MUTATION_METHODS:
            # No pollable resource URL (e.g. a POST action) -> default polling.
            return wait_for_terminal_state(poller, wait_sec=wait_sec)

        is_delete = method == "DELETE"
        last_body = None
        for _ in range(LRO_POLL_RETRIES):
            response = self.client.send_request(HttpRequest("GET", url))
            code = response.status_code
            if code == 404:
                if is_delete:
                    return None  # resource removed -> delete complete
                sleep(wait_sec)  # not readable yet -> retry
                continue
            if 200 <= code < 300:
                last_body = response.json()
                state = (last_body.get("properties") or {}).get("provisioningState")
                if state == _PROVISIONING_SUCCEEDED or state is None:
                    return last_body
                if state in _PROVISIONING_FAILURES:
                    raise AzureResponseError(self._format_failure(state, last_body, response))
                sleep(wait_sec)  # still provisioning (Accepted/Updating/...) -> re-check
                continue
            # Unexpected status (e.g. a transient 5xx) -> brief backoff and retry.
            sleep(wait_sec)
        return last_body  # budget exhausted -> return last-known body (may be None)

    def _raise_if_parent_not_found(self, error: Exception, message: str):
        """Translate a backend "ParentResourceNotFound" 404 into a friendly error.

        ARM returns an opaque 404 when a parent in the resource path (e.g. the
        certificate authority behind a certificate policy) does not exist. Callers
        pass a resource-specific ``message`` so the user gets actionable guidance.
        Any other error is re-raised unchanged.
        """
        if (
            isinstance(error, HttpResponseError)
            and error.status_code == 404
            and "ParentResourceNotFound" in str(error)
        ):
            raise ResourceNotFoundError(message)
        raise error

    def _resolve_location(
        self, namespace_name: str, resource_group_name: str, location: Optional[str] = None
    ):
        """Resolve a child resource location from its parent Device Registry namespace.

        Child resources (certificate authorities, certificate policies, registry devices) must be
        co-located with their parent namespace, so default to the namespace's location when the
        caller does not specify one explicitly. Use this when a parent namespace is guaranteed to
        exist; use ``_ensure_location`` instead when only the resource group is available.
        """
        if location:
            return location
        namespace = self.client.namespaces.get(
            resource_group_name=resource_group_name, namespace_name=namespace_name
        )
        location = namespace.get("location")
        if not location:
            raise AzureResponseError(
                "Error attempting to determine location from parent Namespace: "
                "Namespace does not contain a location property."
            )
        return location

    def _ensure_location(self, cli_ctx, resource_group_name: str, location: Optional[str] = None):
        """Resolve a location, falling back to the resource group's location.

        Unlike ``_resolve_location`` (which reads the parent namespace), this is used when there
        is no parent resource yet — e.g. creating the namespace itself — so the resource group's
        location is the sensible default.
        """
        if location:
            return location

        # Get resource group location as fallback
        from azure.cli.core.commands.client_factory import get_mgmt_service_client
        from azure.mgmt.resource import ResourceManagementClient

        resource_client = get_mgmt_service_client(cli_ctx, ResourceManagementClient)
        rg = resource_client.resource_groups.get(resource_group_name)
        return rg.location
