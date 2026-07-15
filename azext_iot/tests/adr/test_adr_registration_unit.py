# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Smoke tests that exercise the ADR command/argument registration modules.

These modules are declarative (command-to-implementation maps and argument
definitions) and contain no runtime business logic. Invoking the loader
functions with a mock command loader executes every registration line, which
catches import errors, typos in implementation references, and malformed
argument declarations without requiring a live Azure CLI command table.
"""

from unittest.mock import MagicMock, call

import azext_iot.adr._help  # noqa: F401  (covered on import)
from azext_iot.adr.command_map import load_adr_commands
from azext_iot.adr.params import load_adr_arguments


def test_load_adr_commands():
    load_adr_commands(MagicMock(), None)


def test_registry_device_lro_commands_support_no_wait():
    loader = MagicMock()
    command_group = loader.command_group.return_value.__enter__.return_value

    load_adr_commands(loader, None)

    assert call(
        "create", "adr_registry_device_create", supports_no_wait=True
    ) in command_group.command.call_args_list
    assert call(
        "update", "adr_registry_device_update", supports_no_wait=True
    ) in command_group.command.call_args_list


def test_load_adr_arguments():
    load_adr_arguments(MagicMock(), None)
