# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError


def test_job_run_show(fixture_job_run_provider):
    expected = {"name": "run", "properties": {"status": "Succeeded"}}
    fixture_job_run_provider.client.job_runs.get.return_value = expected

    assert (
        fixture_job_run_provider.show("job", "run", "namespace", "rg")
        is expected
    )
    fixture_job_run_provider.client.job_runs.get.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        job_name="job",
        run_name="run",
    )


def test_job_run_list_by_job(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_by_job.return_value = iter(
        [{"name": "one"}, {"name": "two"}]
    )

    result = fixture_job_run_provider.list(
        "namespace", "rg", job_name="job"
    )

    assert result == [{"name": "one"}, {"name": "two"}]
    fixture_job_run_provider.client.job_runs.list_by_job.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        job_name="job",
    )
    fixture_job_run_provider.client.job_runs.list_by_namespace.assert_not_called()


def test_job_run_list_by_job_with_filter(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_by_job.return_value = iter([])

    fixture_job_run_provider.list(
        "namespace",
        "rg",
        job_name="job",
        status_filter="status eq 'Active'",
    )

    fixture_job_run_provider.client.job_runs.list_by_job.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        job_name="job",
        filter="status eq 'Active'",
    )


def test_job_run_list_by_namespace_with_filter(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_by_namespace.return_value = iter(
        [{"name": "one"}]
    )

    result = fixture_job_run_provider.list(
        "namespace",
        "rg",
        status_filter="status eq 'Active'",
    )

    assert result == [{"name": "one"}]
    fixture_job_run_provider.client.job_runs.list_by_namespace.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        filter="status eq 'Active'",
    )
    fixture_job_run_provider.client.job_runs.list_by_job.assert_not_called()


def test_job_run_list_accepts_status_equality_or(fixture_job_run_provider):
    status_filter = "status eq 'Active' or status eq 'Scheduled'"
    fixture_job_run_provider.client.job_runs.list_by_namespace.return_value = iter([])

    fixture_job_run_provider.list(
        "namespace", "rg", status_filter=status_filter
    )

    assert (
        fixture_job_run_provider.client.job_runs.list_by_namespace.call_args.kwargs[
            "filter"
        ]
        == status_filter
    )


@pytest.mark.parametrize(
    "status_filter",
    [
        "status ne 'Canceled'",
        "status eq 'Unknown'",
        "name eq 'Active'",
    ],
)
def test_job_run_list_rejects_unsupported_filters(
    fixture_job_run_provider, status_filter
):
    with pytest.raises(InvalidArgumentValueError):
        fixture_job_run_provider.list(
            "namespace", "rg", status_filter=status_filter
        )


def test_job_run_results_posts_empty_body(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_results.return_value = {
        "value": [{"deviceId": "one"}],
        "nextLink": None,
    }

    result = list(
        fixture_job_run_provider.results("job", "run", "namespace", "rg")
    )

    assert result == [{"deviceId": "one"}]
    fixture_job_run_provider.client.job_runs.list_results.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        job_name="job",
        run_name="run",
        body={},
    )


def test_job_run_results_posts_filter_body(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_results.return_value = {
        "value": [],
        "nextLink": None,
    }

    list(
        fixture_job_run_provider.results(
            "job",
            "run",
            "namespace",
            "rg",
            status_filter="status eq 'Failed'",
        )
    )

    assert (
        fixture_job_run_provider.client.job_runs.list_results.call_args.kwargs["body"]
        == {"filter": "status eq 'Failed'"}
    )


@pytest.mark.parametrize(
    "status_filter",
    [
        "status ne 'Failed'",
        "status eq 'Unknown'",
        "status eq 'Failed' or status eq 'Canceled'",
    ],
)
def test_job_run_results_rejects_unsupported_filters(
    fixture_job_run_provider, status_filter
):
    with pytest.raises(InvalidArgumentValueError):
        list(
            fixture_job_run_provider.results(
                "job",
                "run",
                "namespace",
                "rg",
                status_filter=status_filter,
            )
        )


def test_job_run_results_flattens_next_links(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_results.return_value = {
        "value": [{"deviceId": "one"}],
        "nextLink": "https://management.azure.com/page/2",
    }
    page_two = Mock()
    page_two.json.return_value = {
        "value": [{"deviceId": "two"}],
        "nextLink": "https://management.azure.com/page/3",
    }
    page_three = Mock()
    page_three.json.return_value = {
        "value": [{"deviceId": "three"}],
        "nextLink": None,
    }
    fixture_job_run_provider.client.send_request.side_effect = [
        page_two,
        page_three,
    ]

    result = list(
        fixture_job_run_provider.results("job", "run", "namespace", "rg")
    )

    assert [item["deviceId"] for item in result] == ["one", "two", "three"]
    requests = [
        call.args[0]
        for call in fixture_job_run_provider.client.send_request.call_args_list
    ]
    assert [(request.method, request.url) for request in requests] == [
        ("GET", "https://management.azure.com/page/2"),
        ("GET", "https://management.azure.com/page/3"),
    ]
    page_two.raise_for_status.assert_called_once_with()
    page_three.raise_for_status.assert_called_once_with()


def test_job_run_results_follows_next_link_after_empty_page(
    fixture_job_run_provider,
):
    fixture_job_run_provider.client.job_runs.list_results.return_value = {
        "value": None,
        "nextLink": "https://management.azure.com/page/2",
    }
    page_two = Mock()
    page_two.json.return_value = {
        "value": [{"deviceId": "one"}],
        "nextLink": None,
    }
    fixture_job_run_provider.client.send_request.return_value = page_two

    assert list(
        fixture_job_run_provider.results("job", "run", "namespace", "rg")
    ) == [{"deviceId": "one"}]


def test_job_run_results_handles_empty_response(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_results.return_value = None

    assert not list(
        fixture_job_run_provider.results("job", "run", "namespace", "rg")
    )


def test_job_run_results_is_lazy_across_pages(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_results.return_value = {
        "value": [{"deviceId": "one"}, {"deviceId": "two"}],
        "nextLink": "https://management.azure.com/page/2",
    }
    page_two = Mock()
    page_two.json.return_value = {
        "value": [{"deviceId": "three"}],
        "nextLink": None,
    }
    fixture_job_run_provider.client.send_request.return_value = page_two

    results = fixture_job_run_provider.results(
        "job", "run", "namespace", "rg"
    )
    assert [next(results), next(results)] == [
        {"deviceId": "one"},
        {"deviceId": "two"},
    ]
    fixture_job_run_provider.client.send_request.assert_not_called()
    assert next(results) == {"deviceId": "three"}


def test_job_run_results_propagates_next_page_error(fixture_job_run_provider):
    fixture_job_run_provider.client.job_runs.list_results.return_value = {
        "value": [],
        "nextLink": "https://management.azure.com/page/2",
    }
    response = Mock()
    response.raise_for_status.side_effect = RuntimeError("503 unavailable")
    fixture_job_run_provider.client.send_request.return_value = response

    with pytest.raises(RuntimeError, match="503"):
        list(
            fixture_job_run_provider.results(
                "job", "run", "namespace", "rg"
            )
        )


def test_job_run_cancel_waits_for_lro(fixture_job_run_provider, mock_poller):
    fixture_job_run_provider.client.job_runs.begin_cancel.return_value = mock_poller(
        {"status": "Canceled"}
    )

    result = fixture_job_run_provider.cancel(
        "job", "run", "namespace", "rg"
    )

    assert result == {"status": "Canceled"}
    fixture_job_run_provider.client.job_runs.begin_cancel.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        job_name="job",
        run_name="run",
    )


def test_job_run_cancel_no_wait(fixture_job_run_provider, mock_poller):
    poller = mock_poller(None)
    fixture_job_run_provider.client.job_runs.begin_cancel.return_value = poller

    result = fixture_job_run_provider.cancel(
        "job", "run", "namespace", "rg", no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()
