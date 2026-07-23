# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Shared helpers for ADR integration tests that require Azure infrastructure."""

import re
import time
from typing import Dict, Optional

from azext_iot.tests.adr._log import (  # noqa: F401 - re-exported for back-compat
    LogKind,
    _fmt_duration,
    _log,
    timed_step,
)
from azext_iot.tests.adr.conftest import RoleAssignmentHelper, TEST_LOCATION


ROLE_PROPAGATION_DELAY = 30
RESOURCE_POLL_INTERVAL = 10
RESOURCE_MAX_POLLS = 30
RESOURCE_RETRYABLE_STATUS_CODES = {
    404,
    408,
    409,
    429,
    500,
    502,
    503,
    504,
}
RESOURCE_RETRYABLE_ERROR = re.compile(
    r"ResourceNotFound|ParentResourceNotFound|"
    r"RequestTimeout|TooManyRequests|Conflict|"
    r"InternalServerError|BadGateway|ServiceUnavailable|GatewayTimeout|"
    r"\b(408|409|429|500|502|503|504)\b",
    re.IGNORECASE,
)


def is_retryable_resource_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        status_code = getattr(
            getattr(error, "response", None), "status_code", None
        )
    return (
        status_code in RESOURCE_RETRYABLE_STATUS_CODES
        or RESOURCE_RETRYABLE_ERROR.search(str(error)) is not None
    )


def wait_for_resource_succeeded(
    test,
    show_command: str,
    *,
    max_polls: int = RESOURCE_MAX_POLLS,
    poll_interval: int = RESOURCE_POLL_INTERVAL,
) -> dict:
    """Poll an ADR resource until provisioning succeeds or fails."""
    last_state = None
    last_error = None
    for _ in range(max_polls):
        try:
            resource = test.cmd(show_command).get_output_in_json()
        except Exception as error:  # noqa: BLE001 - an initial 404 is expected
            if not is_retryable_resource_error(error):
                raise
            last_error = error
        else:
            last_error = None
            last_state = (resource.get("properties") or {}).get(
                "provisioningState"
            )
            if last_state == "Succeeded":
                return resource
            if last_state in {"Failed", "Canceled", "Cancelled"}:
                raise AssertionError(
                    f"Resource provisioning reached terminal state '{last_state}'."
                )
        time.sleep(poll_interval)

    detail = (
        f"last state: {last_state}"
        if last_error is None
        else f"last error: {last_error}"
    )
    raise AssertionError(
        "Resource did not reach provisioningState 'Succeeded' "
        f"after {max_polls} polls ({detail})."
    )


class ADRHubInfraHelper(RoleAssignmentHelper):
    """Setup and teardown for tests linking an ADR namespace to an IoT Hub."""

    def setup_full_infra(
        self,
        resource_group: str,
        namespace_name: str,
        hub_name: str,
        identity_name: str,
    ) -> Dict[str, str]:
        """Create UAMI, ADR namespace, RBAC, and an ADR-linked IoT Hub."""
        with timed_step("Setup 1/5 > Create UAMI"):
            uami_cmd = (
                f"identity create -n {identity_name} -g {resource_group} "
                f"--location {TEST_LOCATION}"
            )
            _log(LogKind.CMD, "az %s", uami_cmd)
            identity = self.cmd(uami_cmd).get_output_in_json()
            identity_resource_id = identity["id"]
            identity_principal_id = identity["principalId"]
            _log(LogKind.RESULT, "principalId=%s", identity_principal_id)

            _log(LogKind.CMD, "az account show")
            subscription_id = self.cmd("account show").get_output_in_json()["id"]
            _log(LogKind.RESULT, "subscription=%s", subscription_id)

        with timed_step("Setup 2/5 > RBAC: Hub RP Contributor"):
            self.assign_hub_rp_contributor_role(
                subscription_id, resource_group
            )

        with timed_step("Setup 3/5 > Create ADR Namespace"):
            ns_cmd = (
                f"iot adr ns create -n {namespace_name} -g {resource_group} "
                f"--location {TEST_LOCATION}"
            )
            _log(LogKind.CMD, "az %s", ns_cmd)
            namespace = self.cmd(ns_cmd).get_output_in_json()
            adr_resource_id = namespace["id"]
            assert namespace["properties"]["provisioningState"] == "Succeeded"
            _log(
                LogKind.RESULT,
                "id=%s, identity=%s",
                adr_resource_id,
                namespace.get("identity", {}).get("type"),
            )

        with timed_step("Setup 4/5 > RBAC: ADR Roles for UAMI"):
            self.assign_adr_roles_to_identity(
                identity_principal_id, adr_resource_id
            )

        with timed_step(
            "Setup 5/5 > Create IoT Hub Gen2 (may take 3-5 min)"
        ):
            hub_cmd = (
                f"iot hub create -n {hub_name} -g {resource_group} "
                f"--sku GEN2 --location {TEST_LOCATION} "
                f"--mi-user-assigned {identity_resource_id} "
                f"--ns-resource-id {adr_resource_id} "
                f"--ns-identity-id {identity_resource_id}"
            )
            _log(LogKind.CMD, "az %s", hub_cmd)
            _log(
                LogKind.WARN,
                "Hub provisioning in progress - this is the slowest step ...",
            )
            hub = self.cmd(hub_cmd).get_output_in_json()
            assert hub["properties"]["state"] == "Active"
            _log(LogKind.RESULT, "Hub state=Active")

            hub_show_cmd = (
                f"iot hub show -n {hub_name} -g {resource_group}"
            )
            _log(LogKind.CMD, "az %s", hub_show_cmd)
            hub_show = self.cmd(hub_show_cmd).get_output_in_json()
            adr_props = hub_show.get("properties", {}).get(
                "deviceRegistry", {}
            )
            _log(
                LogKind.RESULT,
                "ADR config: nsResourceId=%s",
                adr_props.get("namespaceResourceId"),
            )

        _log(
            LogKind.WARN,
            "Waiting %ds for role/hub propagation ...",
            ROLE_PROPAGATION_DELAY,
        )
        time.sleep(ROLE_PROPAGATION_DELAY)

        return {
            "subscription_id": subscription_id,
            "identity_resource_id": identity_resource_id,
            "identity_principal_id": identity_principal_id,
            "adr_resource_id": adr_resource_id,
            "hub_name": hub_name,
        }

    def cleanup_namespace(
        self, namespace_name: str, resource_group: str
    ) -> None:
        """Delete just the ADR namespace."""
        with timed_step("Cleanup > Delete Namespace"):
            cleanup_cmd = (
                f"iot adr ns delete -n {namespace_name} "
                f"-g {resource_group} -y"
            )
            _log(LogKind.CMD, "az %s", cleanup_cmd)
            try:
                self.cmd(cleanup_cmd)
                _log(LogKind.RESULT, "ok")
            except Exception as error:  # noqa: BLE001 - cleanup is best-effort
                _log(LogKind.WARN, "Cleanup failed: %s", error)

    def cleanup_full_infra(
        self,
        resource_group: str,
        hub_name: Optional[str] = None,
        namespace_name: Optional[str] = None,
        identity_name: Optional[str] = None,
        dps_name: Optional[str] = None,
    ) -> None:
        """Best-effort cleanup of infrastructure resources."""
        _log(LogKind.STEP, "Cleanup > Delete All Infrastructure")
        cleanup_start = time.monotonic()
        resources = [
            (
                "DPS",
                f"iot dps delete --name {dps_name} -g {resource_group}"
                if dps_name
                else None,
            ),
            (
                "IoT Hub",
                f"iot hub delete -n {hub_name} -g {resource_group}"
                if hub_name
                else None,
            ),
            (
                "ADR namespace",
                f"iot adr ns delete -n {namespace_name} "
                f"-g {resource_group} -y"
                if namespace_name
                else None,
            ),
            (
                "UAMI",
                f"identity delete -n {identity_name} -g {resource_group}"
                if identity_name
                else None,
            ),
        ]
        for label, command in resources:
            if command:
                _log(LogKind.CMD, "az %s", command)
                try:
                    self.cmd(command)
                    _log(LogKind.RESULT, "%s deleted", label)
                except Exception as error:  # noqa: BLE001
                    _log(LogKind.WARN, "%s cleanup failed: %s", label, error)
        _log(
            "_time",
            "(%s)",
            _fmt_duration(time.monotonic() - cleanup_start),
        )
