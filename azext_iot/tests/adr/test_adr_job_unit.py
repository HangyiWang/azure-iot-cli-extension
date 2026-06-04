# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest

from azure.cli.core.azclierror import (
    ArgumentUsageError,
    InvalidArgumentValueError,
)


_FAKE_SUB_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture(autouse=True)
def _patch_subscription_id(monkeypatch):
    """Stub get_subscription_id used by JobProvider.create to compose target ARM ID."""
    monkeypatch.setattr(
        "azext_iot.adr.providers.job.get_subscription_id",
        lambda _ctx: _FAKE_SUB_ID,
    )


# ==================== create ====================


def test_job_create_minimal_with_target_group_name(fixture_job_provider, mock_poller):
    mock_job = Mock()
    fixture_job_provider.client.jobs.begin_create_or_replace.return_value = mock_poller(mock_job)

    result = fixture_job_provider.create(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        target_group_name="test-group",
        update_provider="Contoso",
        update_name="gateway-firmware",
        update_version="1.2.3",
        location="eastus",
    )

    assert result == mock_job
    expected_target = (
        f"/subscriptions/{_FAKE_SUB_ID}/resourceGroups/test-rg"
        "/providers/Microsoft.DeviceRegistry/namespaces/test-ns/groups/test-group"
    )
    fixture_job_provider.client.jobs.begin_create_or_replace.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-ns",
        job_name="test-job",
        resource={
            "location": "eastus",
            "properties": {
                "jobType": "Update",
                "target": {"targetResourceId": expected_target},
                "definition": {
                    "schedulingType": "continuous",
                    "update": {
                        "updateId": {
                            "provider": "Contoso",
                            "name": "gateway-firmware",
                            "version": "1.2.3",
                        }
                    },
                },
            },
        },
    )


def test_job_create_with_target_group_in_same_namespace(fixture_job_provider, mock_poller):
    """Target group is always composed against the job's own subscription/RG/namespace."""
    fixture_job_provider.client.jobs.begin_create_or_replace.return_value = mock_poller(Mock())

    fixture_job_provider.create(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        target_group_name="test-group",
        update_provider="P",
        update_name="N",
        update_version="V",
        location="eastus",
    )

    expected_id = (
        f"/subscriptions/{_FAKE_SUB_ID}/resourceGroups/test-rg"
        "/providers/Microsoft.DeviceRegistry/namespaces/test-ns/groups/test-group"
    )
    call_args = fixture_job_provider.client.jobs.begin_create_or_replace.call_args[1]
    assert call_args["resource"]["properties"]["target"]["targetResourceId"] == expected_id


def test_job_create_with_tags(fixture_job_provider, mock_poller):
    fixture_job_provider.client.jobs.begin_create_or_replace.return_value = mock_poller(Mock())

    fixture_job_provider.create(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        target_group_name="test-group",
        update_provider="P", update_name="N", update_version="V",
        location="eastus",
        tags={"env": "prod"},
    )

    call_args = fixture_job_provider.client.jobs.begin_create_or_replace.call_args[1]
    assert call_args["resource"]["tags"] == {"env": "prod"}


def test_job_create_infers_location(fixture_job_provider, mock_poller):
    fixture_job_provider.client.jobs.begin_create_or_replace.return_value = mock_poller(Mock())
    fixture_job_provider._ensure_location = Mock(return_value="westus2")

    fixture_job_provider.create(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        target_group_name="test-group",
        update_provider="P", update_name="N", update_version="V",
    )

    fixture_job_provider._ensure_location.assert_called_once()
    call_args = fixture_job_provider.client.jobs.begin_create_or_replace.call_args[1]
    assert call_args["resource"]["location"] == "westus2"


def test_job_create_rejects_type_action(fixture_job_provider):
    with pytest.raises(ArgumentUsageError, match="Only --type Update is supported"):
        fixture_job_provider.create(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
            target_group_name="test-group",
            update_provider="P", update_name="N", update_version="V",
            job_type="Action",
            location="eastus",
        )


def test_job_create_rejects_type_state(fixture_job_provider):
    with pytest.raises(ArgumentUsageError, match="Only --type Update is supported"):
        fixture_job_provider.create(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
            target_group_name="test-group",
            update_provider="P", update_name="N", update_version="V",
            job_type="State",
            location="eastus",
        )


def test_job_create_requires_a_target(fixture_job_provider):
    with pytest.raises(ArgumentUsageError, match="--target-group-name is required"):
        fixture_job_provider.create(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
            update_provider="P", update_name="N", update_version="V",
            location="eastus",
        )


def test_job_create_requires_full_update_triple(fixture_job_provider):
    with pytest.raises(ArgumentUsageError, match="--update-id-provider, --update-id-name, and --update-id-version"):
        fixture_job_provider.create(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
            target_group_name="test-group",
            update_provider="P",
            update_name="N",
            # update_version omitted
            location="eastus",
        )


def test_job_create_no_wait_returns_poller(fixture_job_provider, mock_poller):
    poller = mock_poller({"name": "test-job"})
    fixture_job_provider.client.jobs.begin_create_or_replace.return_value = poller

    result = fixture_job_provider.create(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        target_group_name="test-group",
        update_provider="P", update_name="N", update_version="V",
        location="eastus",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


# ==================== update (sync, tags-only) ====================


def test_job_update_tags_only_calls_sync_update(fixture_job_provider):
    fixture_job_provider.client.jobs.update.return_value = {"name": "test-job"}

    result = fixture_job_provider.update(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        tags={"env": "staging"},
    )

    assert result == {"name": "test-job"}
    fixture_job_provider.client.jobs.update.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-ns",
        job_name="test-job",
        properties={"tags": {"env": "staging"}},
    )


def test_job_update_empty_tags_clears(fixture_job_provider):
    """Explicit `--tags ""` (tags={}) clears all tags via ArmTagsPatchSync."""
    fixture_job_provider.client.jobs.update.return_value = Mock()

    fixture_job_provider.update(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        tags={},
    )
    call_args = fixture_job_provider.client.jobs.update.call_args[1]
    assert call_args["properties"] == {"tags": {}}


def test_job_update_no_args_raises_nothing_to_update(fixture_job_provider):
    """Calling `job update` without --tags is a guard error (no silent tag-clear)."""
    with pytest.raises(ArgumentUsageError, match="Nothing to update"):
        fixture_job_provider.update(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
            tags=None,
        )
    fixture_job_provider.client.jobs.update.assert_not_called()


def test_job_update_rejects_non_tag_fields(fixture_job_provider):
    with pytest.raises(ArgumentUsageError, match="Only --tags can be modified"):
        fixture_job_provider.update(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
            tags={"a": "b"},
            target_group_name="will-be-rejected",
        )


# ==================== show / list ====================


def test_job_show(fixture_job_provider):
    mock_job = Mock()
    fixture_job_provider.client.jobs.get.return_value = mock_job

    result = fixture_job_provider.show(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
    )

    assert result == mock_job
    fixture_job_provider.client.jobs.get.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-ns",
        job_name="test-job",
    )


def test_job_list(fixture_job_provider):
    fixture_job_provider.client.jobs.list_by_namespace.return_value = iter(["j1", "j2"])

    result = fixture_job_provider.list(
        namespace_name="test-ns",
        resource_group_name="test-rg",
    )

    assert result == ["j1", "j2"]


# ==================== delete + in-flight runs probe ====================


def test_job_delete_in_flight_runs_warning(fixture_job_provider, mock_poller, caplog):
    fixture_job_provider.client.job_runs.list_by_job.return_value = iter([
        {"name": "run-1", "properties": {"status": "Active"}},
        {"name": "run-2", "properties": {"status": "Scheduled"}},
        {"name": "run-3", "properties": {"status": "Queued"}},
        {"name": "run-done", "properties": {"status": "Succeeded"}},
        {"name": "run-failed", "properties": {"status": "Failed"}},
    ])
    fixture_job_provider.client.jobs.begin_delete.return_value = mock_poller()

    import logging
    with caplog.at_level(logging.WARNING, logger="azext_iot.adr.providers.job"):
        fixture_job_provider.delete(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
        )

    # In-flight runs warning surfaced exactly once.
    in_flight_msgs = [r for r in caplog.records if "in-flight run(s)" in r.message]
    assert len(in_flight_msgs) == 1
    assert "3 in-flight run(s)" in in_flight_msgs[0].message
    fixture_job_provider.client.jobs.begin_delete.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-ns",
        job_name="test-job",
    )


def test_job_delete_no_in_flight_runs(fixture_job_provider, mock_poller, caplog):
    fixture_job_provider.client.job_runs.list_by_job.return_value = iter([
        {"name": "run-done", "properties": {"status": "Succeeded"}},
    ])
    fixture_job_provider.client.jobs.begin_delete.return_value = mock_poller()

    import logging
    with caplog.at_level(logging.WARNING, logger="azext_iot.adr.providers.job"):
        fixture_job_provider.delete(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
        )

    assert not any("in-flight run(s)" in r.message for r in caplog.records)
    fixture_job_provider.client.jobs.begin_delete.assert_called_once()


def test_job_delete_in_flight_probe_rbac_failure_degrades(fixture_job_provider, mock_poller, caplog):
    """RBAC failure on job_runs.list_by_job must NOT block deletion."""
    fixture_job_provider.client.job_runs.list_by_job.side_effect = RuntimeError("forbidden")
    fixture_job_provider.client.jobs.begin_delete.return_value = mock_poller()

    import logging
    with caplog.at_level(logging.WARNING, logger="azext_iot.adr.providers.job"):
        fixture_job_provider.delete(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
        )

    # Delete still issued.
    fixture_job_provider.client.jobs.begin_delete.assert_called_once()
    # Best-effort warning (probe failure) surfaced.
    assert any("Unable to enumerate job runs" in r.message for r in caplog.records)


def test_job_delete_no_wait_returns_poller(fixture_job_provider, mock_poller):
    fixture_job_provider.client.job_runs.list_by_job.return_value = iter([])
    poller = mock_poller(None)
    fixture_job_provider.client.jobs.begin_delete.return_value = poller

    result = fixture_job_provider.delete(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


# ==================== schedule ====================


def test_job_schedule_empty_body(fixture_job_provider, mock_poller):
    fixture_job_provider.client.jobs.begin_schedule.return_value = mock_poller()

    fixture_job_provider.schedule(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
    )

    fixture_job_provider.client.jobs.begin_schedule.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-ns",
        job_name="test-job",
        body={},
    )


def test_job_schedule_with_iso_timeout_and_time(fixture_job_provider, mock_poller):
    fixture_job_provider.client.jobs.begin_schedule.return_value = mock_poller()

    fixture_job_provider.schedule(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        scheduled_time="2025-12-01T08:00:00Z",
        timeout="PT2H",
    )

    call_args = fixture_job_provider.client.jobs.begin_schedule.call_args[1]
    assert call_args["body"] == {
        "scheduledTime": "2025-12-01T08:00:00Z",
        "timeout": "PT2H",
    }


def test_job_schedule_invalid_timeout_raises(fixture_job_provider):
    with pytest.raises(InvalidArgumentValueError, match="ISO 8601 duration"):
        fixture_job_provider.schedule(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
            timeout="not-a-duration",
        )
    fixture_job_provider.client.jobs.begin_schedule.assert_not_called()


def test_job_schedule_invalid_scheduled_time_raises(fixture_job_provider):
    with pytest.raises(InvalidArgumentValueError, match="ISO 8601 UTC datetime"):
        fixture_job_provider.schedule(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
            scheduled_time="tomorrow at noon",
        )
    fixture_job_provider.client.jobs.begin_schedule.assert_not_called()


def test_job_schedule_no_wait_returns_poller(fixture_job_provider, mock_poller):
    poller = mock_poller(None)
    fixture_job_provider.client.jobs.begin_schedule.return_value = poller

    result = fixture_job_provider.schedule(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


# ==================== Edge-case fills ====================


@pytest.mark.parametrize(
    "missing_field",
    [
        # Each tuple omits exactly one of (provider, name, version)
        {"update_name": "N", "update_version": "V"},  # provider missing
        {"update_provider": "P", "update_version": "V"},  # name missing
        {"update_provider": "P", "update_name": "N"},  # version missing
    ],
    ids=["missing_provider", "missing_name", "missing_version"],
)
def test_job_create_partial_update_triple_each_component(fixture_job_provider, missing_field):
    """Each individual missing field in the update-id triple raises the same guard."""
    with pytest.raises(
        ArgumentUsageError,
        match="--update-id-provider, --update-id-name, and --update-id-version",
    ):
        fixture_job_provider.create(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
            target_group_name="test-group",
            location="eastus",
            **missing_field,
        )


def test_job_schedule_only_timeout(fixture_job_provider, mock_poller):
    """Timeout without scheduled-time produces a single-key body."""
    fixture_job_provider.client.jobs.begin_schedule.return_value = mock_poller()

    fixture_job_provider.schedule(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        timeout="PT30M",
    )

    call_args = fixture_job_provider.client.jobs.begin_schedule.call_args[1]
    assert call_args["body"] == {"timeout": "PT30M"}


def test_job_schedule_only_scheduled_time(fixture_job_provider, mock_poller):
    """Scheduled-time without timeout produces a single-key body."""
    fixture_job_provider.client.jobs.begin_schedule.return_value = mock_poller()

    fixture_job_provider.schedule(
        job_name="test-job",
        namespace_name="test-ns",
        resource_group_name="test-rg",
        scheduled_time="2025-12-01T08:00:00Z",
    )

    call_args = fixture_job_provider.client.jobs.begin_schedule.call_args[1]
    assert call_args["body"] == {"scheduledTime": "2025-12-01T08:00:00Z"}


def test_job_delete_terminal_runs_not_counted(fixture_job_provider, mock_poller, caplog):
    """Only Scheduled/Queued/Active runs count toward the in-flight tally.
    Succeeded/Failed/Canceled/Skipped runs must be excluded from the warning."""
    fixture_job_provider.client.job_runs.list_by_job.return_value = iter([
        {"name": "r-succ", "properties": {"status": "Succeeded"}},
        {"name": "r-fail", "properties": {"status": "Failed"}},
        {"name": "r-canc", "properties": {"status": "Canceled"}},
        {"name": "r-skip", "properties": {"status": "Skipped"}},
    ])
    fixture_job_provider.client.jobs.begin_delete.return_value = mock_poller()

    import logging
    with caplog.at_level(logging.WARNING, logger="azext_iot.adr.providers.job"):
        fixture_job_provider.delete(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
        )

    assert not any("in-flight run(s)" in r.message for r in caplog.records)
    fixture_job_provider.client.jobs.begin_delete.assert_called_once()


def test_job_delete_single_in_flight_run(fixture_job_provider, mock_poller, caplog):
    """Singular phrasing in the warning when exactly one run is in-flight."""
    fixture_job_provider.client.job_runs.list_by_job.return_value = iter([
        {"name": "run-1", "properties": {"status": "Active"}},
    ])
    fixture_job_provider.client.jobs.begin_delete.return_value = mock_poller()

    import logging
    with caplog.at_level(logging.WARNING, logger="azext_iot.adr.providers.job"):
        fixture_job_provider.delete(
            job_name="test-job",
            namespace_name="test-ns",
            resource_group_name="test-rg",
        )

    in_flight_msgs = [r for r in caplog.records if "in-flight run(s)" in r.message]
    assert len(in_flight_msgs) == 1
    assert "1 in-flight run(s)" in in_flight_msgs[0].message
