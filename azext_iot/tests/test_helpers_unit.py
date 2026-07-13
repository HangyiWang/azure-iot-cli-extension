# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from types import SimpleNamespace

from azext_iot.tests.helpers import get_closest_marker


def test_get_closest_marker_prefers_current_node(mocker):
    marker = mocker.sentinel.current_marker
    node = mocker.Mock(path="current_test.py")
    node.get_closest_marker.return_value = marker
    request = SimpleNamespace(node=node, session=SimpleNamespace(items=[]))

    assert get_closest_marker(request) is marker


def test_get_closest_marker_limits_fallback_to_current_module(mocker):
    expected_marker = mocker.sentinel.expected_marker
    node = mocker.Mock(path="current_test.py")
    node.get_closest_marker.return_value = None

    unrelated_item = mocker.Mock(path="other_test.py")
    unrelated_item.get_closest_marker.return_value = mocker.sentinel.unrelated_marker
    related_item = mocker.Mock(path="current_test.py")
    related_item.get_closest_marker.return_value = expected_marker
    request = SimpleNamespace(
        node=node,
        session=SimpleNamespace(items=[unrelated_item, related_item]),
    )

    assert get_closest_marker(request) is expected_marker
