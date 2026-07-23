# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Command, argument, and help registration contracts for ADR."""

from unittest.mock import MagicMock

import yaml
from knack.help_files import helps

from azext_iot.adr._help import load_adr_help
from azext_iot.adr.command_map import load_adr_commands
from azext_iot.adr.params import load_adr_arguments


class _CommandGroup:
    def __init__(self, name, records):
        self.name = name
        self.records = records

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def _record(self, kind, name, operation, **kwargs):
        self.records.append((self.name, kind, name, operation, kwargs))

    def command(self, name, operation, **kwargs):
        self._record("command", name, operation, **kwargs)

    def show_command(self, name, operation, **kwargs):
        self._record("show", name, operation, **kwargs)

    def wait_command(self, name, operation, **kwargs):
        self._record("wait", name, operation, **kwargs)


class _CommandLoader:
    def __init__(self):
        self.records = []

    def command_group(self, name, **_):
        return _CommandGroup(name, self.records)

    @staticmethod
    def deprecate(**kwargs):
        return kwargs


class _ArgumentContext:
    def __init__(self, name, records):
        self.name = name
        self.records = records

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def argument(self, name, **kwargs):
        self.records.setdefault(self.name, {})[name] = kwargs


class _ArgumentLoader:
    def __init__(self):
        self.cli_ctx = MagicMock()
        self.records = {}

    def argument_context(self, name):
        return _ArgumentContext(name, self.records)


def _registered_commands():
    loader = _CommandLoader()
    load_adr_commands(loader, None)
    return {
        f"{group} {name}": (kind, operation, kwargs)
        for group, kind, name, operation, kwargs in loader.records
    }


def test_2026_command_surface_is_registered():
    commands = _registered_commands()

    assert commands["iot adr ns migrate"] == (
        "command",
        "adr_namespace_migrate",
        {"supports_no_wait": True},
    )
    assert commands["iot adr ns group list-members"][1] == "adr_group_list_members"
    assert commands["iot adr ns job run cancel"] == (
        "command",
        "adr_job_run_cancel",
        {"confirmation": True, "supports_no_wait": True},
    )
    assert commands["iot adr ns report generate"] == (
        "command",
        "adr_report_generate",
        {"supports_no_wait": True},
    )
    assert commands["iot adr ns report latest"][1] == "adr_report_latest"
    expected_commands = {
        "iot adr ns registry-device create",
        "iot adr ns registry-device show",
        "iot adr ns registry-device list",
        "iot adr ns registry-device update",
        "iot adr ns registry-device delete",
        "iot adr ns registry-device wait",
        "iot adr ns registry-device auth-profile list",
        "iot adr ns registry-device auth-profile show",
        "iot adr ns registry-device auth-profile get-keys",
        "iot adr ns registry-device auth-profile revoke-certificates",
        "iot adr ns registry-device attribute list",
        "iot adr ns registry-device attribute show",
        "iot adr ns registry-device capability list",
        "iot adr ns registry-device capability show",
        "iot adr ns asset create",
        "iot adr ns asset show",
        "iot adr ns asset list",
        "iot adr ns asset update",
        "iot adr ns asset delete",
        "iot adr ns asset execute-action",
        "iot adr ns asset wait",
        "iot adr ns discovered-device create",
        "iot adr ns discovered-device show",
        "iot adr ns discovered-device list",
        "iot adr ns discovered-device update",
        "iot adr ns discovered-device delete",
        "iot adr ns discovered-device wait",
        "iot adr ns discovered-asset create",
        "iot adr ns discovered-asset show",
        "iot adr ns discovered-asset list",
        "iot adr ns discovered-asset update",
        "iot adr ns discovered-asset delete",
        "iot adr ns discovered-asset wait",
        "iot adr ns identity show",
        "iot adr ns identity assign",
        "iot adr ns identity remove",
        "iot adr ns identity wait",
        "iot adr ns management-endpoint set",
        "iot adr ns management-endpoint show",
        "iot adr ns management-endpoint list",
        "iot adr ns management-endpoint wait",
        "iot adr ns ca wait",
        "iot adr ns ca policy wait",
        "iot adr ns device wait",
        "iot adr ns job run wait",
        "iot adr ns link wait",
        "iot adr ns link adu wait",
        "iot adr ns link dps wait",
        "iot adr ns link hub wait",
        "iot adr ns du instance check-name",
        "iot adr ns du instance create",
        "iot adr ns du instance show",
        "iot adr ns du instance list",
        "iot adr ns du instance update",
        "iot adr ns du instance delete",
        "iot adr ns du instance wait",
        "iot adr ns du link add",
        "iot adr ns du link update",
        "iot adr ns du link show",
        "iot adr ns du link list",
        "iot adr ns du link wait",
    }
    assert expected_commands <= set(commands)
    assert len(commands) == 120
    assert commands[
        "iot adr ns registry-device auth-profile revoke-certificates"
    ][2] == {"confirmation": True, "supports_no_wait": True}
    assert commands["iot adr ns link wait"][:2] == (
        "wait",
        "adr_namespace_show",
    )


def test_unsupported_command_surfaces_are_not_registered():
    commands = _registered_commands()

    assert not any(
        command.startswith(("iot adr ns credential", "iot adr ns policy"))
        for command in commands
    )
    for child in ("auth-profile", "attribute", "capability"):
        assert f"iot adr ns registry-device {child} create" not in commands
        assert f"iot adr ns registry-device {child} update" not in commands
        assert f"iot adr ns registry-device {child} delete" not in commands
    assert "iot adr ns device revoke" not in commands
    for endpoint in ("hub", "dps", "adu"):
        assert f"iot adr ns link {endpoint} remove" not in commands
    assert "iot adr ns du link delete" not in commands
    for operation in (
        "link-preflight",
        "link-initiate",
        "link-notify",
        "link-update",
    ):
        assert f"iot adr ns du instance {operation}" not in commands


def test_load_adr_arguments():
    loader = _ArgumentLoader()
    load_adr_arguments(loader, None)
    arguments = loader.records

    assert {"scope", "resource_ids"} <= set(arguments["iot adr ns migrate"])
    assert {"page_size", "skip_token"} <= set(
        arguments["iot adr ns group list-members"]
    )
    assert "status_filter" in arguments["iot adr ns job run list"]
    assert "status_filter" in arguments["iot adr ns job run results"]
    assert {"report_type", "group_name"} <= set(arguments["iot adr ns report"])

    assert {
        "external_device_id",
        "enabled",
        "attributes",
        "endpoints",
    } <= set(arguments["iot adr ns device create"])
    assert "endpoints" in arguments["iot adr ns device update"]
    assert "extended_location" in arguments["iot adr ns device create"]
    assert {
        "management_endpoints",
        "messaging_endpoints",
        "provisioning_endpoints",
        "updating_endpoints",
    } <= set(arguments["iot adr ns update"])
    assert {
        "enablement_state",
        "external_device_id",
        "hardware_revision",
        "software_revision",
    } <= set(arguments["iot adr ns registry-device create"])
    assert "external_device_id" not in arguments[
        "iot adr ns registry-device update"
    ]
    for command in (
        "iot adr ns registry-device create",
        "iot adr ns registry-device update",
    ):
        for argument in (
            "manufacturer",
            "model",
            "hardware_revision",
            "software_revision",
        ):
            assert arguments[command][argument]["help"]
    assert {"properties", "extended_location"} <= set(
        arguments["iot adr ns asset create"]
    )
    assert {"management_action_name", "management_group_name", "payload"} <= set(
        arguments["iot adr ns asset execute-action"]
    )
    assert {"system_assigned", "user_assigned_identities"} <= set(
        arguments["iot adr ns identity assign"]
    )
    assert {"endpoint_type", "address", "scope_id", "resource_id"} <= set(
        arguments["iot adr ns management-endpoint set"]
    )
    assert "--ns" in arguments["iot adr ns link"]["namespace_name"]["options_list"]
    assert "mi_system_assigned" in arguments["iot adr ns group create"]
    assert "mi_system_assigned" in arguments["iot adr ns group update"]
    assert {
        "mi_system_assigned",
        "mi_user_assigned",
        "location",
        "tags",
    } <= set(arguments["iot adr ns du instance create"])
    assert {
        "mi_system_assigned",
        "mi_user_assigned",
        "tags",
    } <= set(arguments["iot adr ns du instance update"])
    assert "--du-id" in arguments["iot adr ns du link add"][
        "adu_resource_id"
    ]["options_list"]

    assert not any(
        command.startswith(("iot adr ns credential", "iot adr ns policy"))
        for command in arguments
    )
    assert {
        "policy_name",
        "certificate_key_type",
        "certificate_validity_days",
    }.isdisjoint(arguments["iot adr ns create"])
    assert {
        "availability",
        "allocation_weight",
    }.isdisjoint(arguments["iot adr ns link hub update"])

    assert "iot adr ns device revoke" not in arguments
    assert not any(
        command.startswith("iot adr ns link") and command.endswith(" remove")
        for command in arguments
    )


def test_help_surface_matches_2026_commands_and_adu_type():
    load_adr_help()

    for command in (
        "iot adr ns migrate",
        "iot adr ns group list-members",
        "iot adr ns job run cancel",
        "iot adr ns report generate",
        "iot adr ns report latest",
        "iot adr ns registry-device create",
        "iot adr ns registry-device auth-profile get-keys",
        "iot adr ns registry-device attribute list",
        "iot adr ns registry-device capability show",
        "iot adr ns asset execute-action",
        "iot adr ns discovered-device create",
        "iot adr ns discovered-asset update",
        "iot adr ns identity assign",
        "iot adr ns management-endpoint set",
        "iot adr ns du instance create",
        "iot adr ns du instance check-name",
        "iot adr ns du link add",
    ):
        assert command in helps

    assert "Microsoft.DeviceUpdate/updateInstances" in helps["iot adr ns link adu"]
    assert "linkedAccounts" not in helps["iot adr ns link adu"]

    assert "iot adr ns device revoke" not in helps
    assert not any(
        command.startswith(("iot adr ns credential", "iot adr ns policy"))
        for command in helps
    )
    for endpoint in ("hub", "dps", "adu"):
        assert f"iot adr ns link {endpoint} remove" not in helps
    assert "iot adr ns du link delete" not in helps


def test_every_registered_adr_command_has_help():
    load_adr_help()
    assert set(_registered_commands()) <= set(helps)


def test_all_adr_help_is_valid_yaml():
    load_adr_help()

    for command, help_text in helps.items():
        if command.startswith("iot adr"):
            assert isinstance(yaml.safe_load(help_text), dict), command
