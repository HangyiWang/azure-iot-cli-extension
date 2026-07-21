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


def test_removed_command_surfaces_are_not_registered():
    commands = _registered_commands()

    assert not any("registry-device" in command for command in commands)
    assert "iot adr ns device revoke" not in commands
    for endpoint in ("hub", "dps", "adu"):
        assert f"iot adr ns link {endpoint} remove" not in commands


def test_credential_and_policy_writes_support_no_wait():
    commands = _registered_commands()
    for command in (
        "iot adr ns credential create",
        "iot adr ns credential delete",
        "iot adr ns credential sync",
        "iot adr ns policy create",
        "iot adr ns policy update",
        "iot adr ns policy delete",
        "iot adr ns policy revoke-issuer",
        "iot adr ns policy activate-byor",
    ):
        assert commands[command][2]["supports_no_wait"] is True


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

    assert "location" in arguments["iot adr ns policy create"]
    assert "certificate_subject" not in arguments["iot adr ns policy create"]
    assert {
        "availability",
        "allocation_weight",
    }.isdisjoint(arguments["iot adr ns link hub update"])

    assert not any("registry-device" in command for command in arguments)
    assert "iot adr ns device revoke" not in arguments
    assert not any(command.endswith(" remove") for command in arguments)


def test_help_surface_matches_2026_commands_and_adu_type():
    load_adr_help()

    for command in (
        "iot adr ns migrate",
        "iot adr ns group list-members",
        "iot adr ns job run cancel",
        "iot adr ns report generate",
        "iot adr ns report latest",
    ):
        assert command in helps

    assert "Microsoft.DeviceUpdate/updateInstances" in helps["iot adr ns link adu"]
    assert "linkedAccounts" not in helps["iot adr ns link adu"]

    assert not any(key.startswith("iot adr ns registry-device") for key in helps)
    assert not any("registry-device" in help_text for help_text in helps.values())
    assert "iot adr ns device revoke" not in helps
    for endpoint in ("hub", "dps", "adu"):
        assert f"iot adr ns link {endpoint} remove" not in helps


def test_all_adr_help_is_valid_yaml():
    load_adr_help()

    for command, help_text in helps.items():
        if command.startswith("iot adr"):
            assert isinstance(yaml.safe_load(help_text), dict), command
