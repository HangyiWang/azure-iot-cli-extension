# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest


# ==================== show / list ====================


def test_job_run_show_delegates_to_sdk_get(fixture_job_run_provider):
    expected = {"name": "run-1", "properties": {"status": "Succeeded"}}
    fixture_job_run_provider.client.job_runs.get.return_value = expected

    result = fixture_job_run_provider.show(
        job_name="test-job",
        run_name="run-1",
        namespace_name="test-ns",
        resource_group_name="test-rg",
    )

    assert result is expected
    fixture_job_run_provider.client.job_runs.get.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-ns",
        job_name="test-job",
        run_name="run-1",
    )


def test_job_run_list_materializes_iterable(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_by_job.return_value = iter([
        {"name": "run-1"},
        {"name": "run-2"},
    ])

    result = fixture_job_run_provider.list(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
    )

    assert [r["name"] for r in result] == ["run-1", "run-2"]
    fixture_job_run_provider.client.job_runs.list_by_job.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-ns",
        job_name="test-job",
    )


# ==================== results (manual pagination) ====================


def test_job_run_results_single_page_returns_all_items(fixture_job_run_provider):
    """A single-page response (no nextLink) yields every value item exactly once."""
    fixture_job_run_provider.client.job_runs.results.return_value = {
        "value": [
            {"deviceUuid": "d1", "status": "Succeeded", "reason": ""},
            {"deviceUuid": "d2", "status": "Failed", "reason": "timeout"},
        ],
        "nextLink": None,
    }

    result = list(
        fixture_job_run_provider.results(
            job_name="test-job",
            run_name="run-1",
            namespace_name="test-ns",
            resource_group_name="test-rg",
        )
    )

    assert [r["deviceUuid"] for r in result] == ["d1", "d2"]
    fixture_job_run_provider.client.job_runs.results.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-ns",
        job_name="test-job",
        run_name="run-1",
    )
    # Single page ⇒ no nextLink follow-up.
    fixture_job_run_provider.client.send_request.assert_not_called()


def test_job_run_results_follows_next_link_until_exhausted(fixture_job_run_provider):
    """Manual pagination: chain pages via client.send_request until nextLink is None."""
    fixture_job_run_provider.client.job_runs.results.return_value = {
        "value": [{"deviceUuid": "d1", "status": "Succeeded"}],
        "nextLink": "https://example/page2",
    }
    page2 = Mock()
    page2.json.return_value = {
        "value": [{"deviceUuid": "d2", "status": "Failed"}],
        "nextLink": "https://example/page3",
    }
    page3 = Mock()
    page3.json.return_value = {
        "value": [{"deviceUuid": "d3", "status": "Succeeded"}],
        "nextLink": None,
    }
    fixture_job_run_provider.client.send_request.side_effect = [page2, page3]

    result = list(
        fixture_job_run_provider.results(
            job_name="test-job",
            run_name="run-1",
            namespace_name="test-ns",
            resource_group_name="test-rg",
        )
    )

    assert [r["deviceUuid"] for r in result] == ["d1", "d2", "d3"]
    assert fixture_job_run_provider.client.send_request.call_count == 2
    page2.raise_for_status.assert_called_once()
    page3.raise_for_status.assert_called_once()
    # Verify the nextLink URLs were preserved in the follow-up requests.
    follow_up_urls = [
        c.args[0].url for c in fixture_job_run_provider.client.send_request.call_args_list
    ]
    assert follow_up_urls == ["https://example/page2", "https://example/page3"]


def test_job_run_results_handles_empty_envelope(fixture_job_run_provider):
    """Missing/null ``value`` field degrades to an empty iterator."""
    fixture_job_run_provider.client.job_runs.results.return_value = {
        "value": None,
        "nextLink": None,
    }
    result = list(
        fixture_job_run_provider.results(
            job_name="test-job",
            run_name="run-1",
            namespace_name="test-ns",
            resource_group_name="test-rg",
        )
    )
    assert not result


def test_job_run_results_is_lazy(fixture_job_run_provider):
    """Generator should not call send_request until the first page is consumed past."""
    fixture_job_run_provider.client.job_runs.results.return_value = {
        "value": [{"deviceUuid": "d1"}, {"deviceUuid": "d2"}],
        "nextLink": "https://example/page2",
    }
    page2 = Mock()
    page2.json.return_value = {"value": [{"deviceUuid": "d3"}], "nextLink": None}
    fixture_job_run_provider.client.send_request.side_effect = [page2]

    gen = fixture_job_run_provider.results(
        job_name="test-job",
        run_name="run-1",
        namespace_name="test-ns",
        resource_group_name="test-rg",
    )
    # Pulling only the first 2 items must NOT trigger nextLink follow-up.
    first_two = [next(gen), next(gen)]
    assert [r["deviceUuid"] for r in first_two] == ["d1", "d2"]
    fixture_job_run_provider.client.send_request.assert_not_called()

    # Pulling the next item advances to page 2.
    assert next(gen)["deviceUuid"] == "d3"
    assert fixture_job_run_provider.client.send_request.call_count == 1

    # Generator exhausted.
    with pytest.raises(StopIteration):
        next(gen)


def test_job_run_results_propagates_http_error_on_next_page(fixture_job_run_provider):
    """A non-success status on a follow-up page surfaces via raise_for_status."""
    fixture_job_run_provider.client.job_runs.results.return_value = {
        "value": [{"deviceUuid": "d1"}],
        "nextLink": "https://example/page2",
    }
    page2 = Mock()
    page2.raise_for_status.side_effect = RuntimeError("503 Service Unavailable")
    fixture_job_run_provider.client.send_request.return_value = page2

    with pytest.raises(RuntimeError, match="503"):
        list(
            fixture_job_run_provider.results(
                job_name="test-job",
                run_name="run-1",
                namespace_name="test-ns",
                resource_group_name="test-rg",
            )
        )


# ==================== Edge-case fills ====================


def test_job_run_results_empty_first_page_with_next_link(fixture_job_run_provider):
    """Empty ``value`` on page 1 must still trigger the nextLink follow-up.

    Defensive: a backend that returns no items on the first envelope but does
    advertise a continuation must still drain subsequent pages.
    """
    fixture_job_run_provider.client.job_runs.results.return_value = {
        "value": [],
        "nextLink": "https://example/page2",
    }
    page2 = Mock()
    page2.json.return_value = {
        "value": [{"deviceUuid": "d1", "status": "Succeeded"}],
        "nextLink": None,
    }
    fixture_job_run_provider.client.send_request.return_value = page2

    result = list(
        fixture_job_run_provider.results(
            job_name="test-job",
            run_name="run-1",
            namespace_name="test-ns",
            resource_group_name="test-rg",
        )
    )

    assert [r["deviceUuid"] for r in result] == ["d1"]
    assert fixture_job_run_provider.client.send_request.call_count == 1
    page2.raise_for_status.assert_called_once()
