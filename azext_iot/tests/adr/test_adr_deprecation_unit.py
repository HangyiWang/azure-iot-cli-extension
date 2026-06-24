# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""Unit tests verifying that legacy ADR command groups are marked deprecated.

The CMS remodel introduces `iot adr ns ca` (+ `iot adr ns ca policy`) which supersede the
`iot adr ns credential` and `iot adr ns policy` command groups. These remain usable during the
transition (not hidden) but must redirect users to the replacement.
"""

from unittest.mock import MagicMock, call

from azext_iot.adr.command_map import load_adr_commands


def test_legacy_groups_are_deprecated_with_redirect():
    loader = MagicMock()
    load_adr_commands(loader, None)

    # Both legacy groups should redirect users to `iot adr ns ca`.
    assert call(redirect="iot adr ns ca") in loader.deprecate.call_args_list

    # Deprecation must not hide the groups (keep them discoverable during transition).
    for c in loader.deprecate.call_args_list:
        assert c.kwargs.get("hide", False) is False
