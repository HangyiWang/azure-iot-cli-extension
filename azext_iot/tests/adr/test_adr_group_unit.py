# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock


def test_group_create_minimal(fixture_group_provider, mock_poller):
    mock_group = Mock()
    fixture_group_provider.client.groups.begin_create_or_replace.return_value = mock_poller(mock_group)

    result = fixture_group_provider.create(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        query_string="SELECT * FROM devices WHERE tags.env = 'prod'",
        location="eastus",
    )

    assert result == mock_group
    fixture_group_provider.client.groups.begin_create_or_replace.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        group_name="test-group",
        resource={
            "location": "eastus",
            "properties": {
                "groupType": "Device",
                "query": "SELECT * FROM devices WHERE tags.env = 'prod'",
            },
        },
    )


def test_group_create_all_fields(fixture_group_provider, mock_poller):
    mock_group = Mock()
    fixture_group_provider.client.groups.begin_create_or_replace.return_value = mock_poller(mock_group)

    fixture_group_provider.create(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        query_string="SELECT * FROM devices",
        group_type="Device",
        location="eastus",
        display_name="Production",
        description="Prod devices",
        tags={"env": "prod"},
    )

    fixture_group_provider.client.groups.begin_create_or_replace.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        group_name="test-group",
        resource={
            "location": "eastus",
            "properties": {
                "groupType": "Device",
                "query": "SELECT * FROM devices",
                "displayName": "Production",
                "description": "Prod devices",
            },
            "tags": {"env": "prod"},
        },
    )


def test_group_create_infers_location(fixture_group_provider, mock_poller):
    """When --location omitted, provider resolves it from the resource group."""
    fixture_group_provider.client.groups.begin_create_or_replace.return_value = mock_poller(Mock())
    fixture_group_provider._ensure_location = Mock(return_value="westus2")

    fixture_group_provider.create(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        query_string="SELECT * FROM devices",
    )

    fixture_group_provider._ensure_location.assert_called_once()
    call_args = fixture_group_provider.client.groups.begin_create_or_replace.call_args[1]
    assert call_args["resource"]["location"] == "westus2"


def test_group_update_display_name_and_description(fixture_group_provider, mock_poller):
    mock_group = Mock()
    fixture_group_provider.client.groups.begin_update.return_value = mock_poller(mock_group)

    fixture_group_provider.update(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        display_name="New name",
        description="New description",
    )

    fixture_group_provider.client.groups.begin_update.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        group_name="test-group",
        properties={
            "properties": {
                "displayName": "New name",
                "description": "New description",
            },
        },
    )


def test_group_update_tags_only(fixture_group_provider, mock_poller):
    fixture_group_provider.client.groups.begin_update.return_value = mock_poller(Mock())

    fixture_group_provider.update(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        tags={"env": "staging"},
    )

    fixture_group_provider.client.groups.begin_update.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        group_name="test-group",
        properties={"tags": {"env": "staging"}},
    )


def test_group_show(fixture_group_provider):
    mock_group = Mock()
    fixture_group_provider.client.groups.get.return_value = mock_group

    result = fixture_group_provider.show(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    )

    assert result == mock_group
    fixture_group_provider.client.groups.get.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        group_name="test-group",
    )


def test_group_list(fixture_group_provider):
    fixture_group_provider.client.groups.list_by_namespace.return_value = iter(["g1", "g2"])

    result = fixture_group_provider.list(
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    )

    assert result == ["g1", "g2"]
    fixture_group_provider.client.groups.list_by_namespace.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
    )


def test_group_delete(fixture_group_provider, mock_poller):
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([])
    fixture_group_provider.client.groups.begin_delete.return_value = mock_poller()

    fixture_group_provider.delete(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    )

    fixture_group_provider.client.groups.begin_delete.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        group_name="test-group",
    )


def test_group_refresh(fixture_group_provider, mock_poller):
    fixture_group_provider.client.groups.begin_refresh_members.return_value = mock_poller()

    fixture_group_provider.refresh(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    )

    fixture_group_provider.client.groups.begin_refresh_members.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        group_name="test-group",
    )


def test_group_show_members_unwraps_members_array(fixture_group_provider):
    """SDK returns ``{"members": [...]}``; provider unwraps to the list."""
    fixture_group_provider.client.groups.preview_members.return_value = {
        "members": ["dev1", "dev2"]
    }

    result = fixture_group_provider.show_members(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    )

    assert result == ["dev1", "dev2"]
    fixture_group_provider.client.groups.preview_members.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        group_name="test-group",
    )


def test_group_show_members_handles_empty_envelope(fixture_group_provider):
    """Missing/null ``members`` field degrades to an empty list."""
    fixture_group_provider.client.groups.preview_members.return_value = {}
    assert fixture_group_provider.show_members(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    ) == []


def test_group_count_unwraps_count_field(fixture_group_provider):
    """SDK returns ``{"count": N}``; provider unwraps to the integer."""
    fixture_group_provider.client.groups.get_current_member_count.return_value = {"count": 42}

    result = fixture_group_provider.count(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
    )

    assert result == 42
    fixture_group_provider.client.groups.get_current_member_count.assert_called_once_with(
        resource_group_name="test-rg",
        namespace_name="test-namespace",
        group_name="test-group",
    )


# ==================== --no-wait + cascade stub ====================


def test_group_create_no_wait_returns_poller(fixture_group_provider, mock_poller):
    poller = mock_poller({"name": "test-group"})
    fixture_group_provider.client.groups.begin_create_or_replace.return_value = poller

    result = fixture_group_provider.create(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        query_string="SELECT * FROM devices",
        location="eastus",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_group_update_no_wait_returns_poller(fixture_group_provider, mock_poller):
    poller = mock_poller({"name": "test-group"})
    fixture_group_provider.client.groups.begin_update.return_value = poller

    result = fixture_group_provider.update(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        display_name="New",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_group_delete_no_wait_returns_poller(fixture_group_provider, mock_poller):
    poller = mock_poller(None)
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([])
    fixture_group_provider.client.groups.begin_delete.return_value = poller

    result = fixture_group_provider.delete(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_group_refresh_no_wait_returns_poller(fixture_group_provider, mock_poller):
    poller = mock_poller(None)
    fixture_group_provider.client.groups.begin_refresh_members.return_value = poller

    result = fixture_group_provider.refresh(
        group_name="test-group",
        namespace_name="test-namespace",
        resource_group_name="test-rg",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


# ==================== cascade-delete: jobs referencing the group ====================


def _job_dict(name: str, group: str, *, prov_state: str = "Succeeded") -> dict:
    return {
        "name": name,
        "properties": {
            "target": {
                "targetResourceId": (
                    f"/subscriptions/sub1/resourceGroups/rg/providers/"
                    f"Microsoft.DeviceRegistry/namespaces/ns/groups/{group}"
                )
            },
            "provisioningState": prov_state,
        },
    }


def test_group_delete_no_referencing_jobs_skips_cascade(fixture_group_provider, mock_poller):
    """Empty job list ⇒ no cascade, only the group delete runs."""
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([])
    fixture_group_provider.client.groups.begin_delete.return_value = mock_poller(None)

    fixture_group_provider.delete(
        group_name="test-group",
        namespace_name="ns",
        resource_group_name="rg",
    )

    fixture_group_provider.client.jobs.begin_delete.assert_not_called()
    fixture_group_provider.client.groups.begin_delete.assert_called_once()


def test_group_delete_cascades_through_clean_jobs(fixture_group_provider, mock_poller):
    """Referencing jobs with terminal state and no in-flight runs are deleted first."""
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([
        _job_dict("job-a", "test-group", prov_state="Succeeded"),
        _job_dict("job-other", "other-group", prov_state="Accepted"),  # filtered out
        _job_dict("job-b", "test-group", prov_state="Failed"),
    ])
    fixture_group_provider.client.job_runs.list_by_job.return_value = iter([])
    fixture_group_provider.client.jobs.begin_delete.return_value = mock_poller(None)
    fixture_group_provider.client.groups.begin_delete.return_value = mock_poller(None)

    fixture_group_provider.delete(
        group_name="test-group",
        namespace_name="ns",
        resource_group_name="rg",
    )

    # Cascade-delete invoked for both referencing jobs, in spec-list order.
    deleted_jobs = [
        c.kwargs["job_name"] for c in fixture_group_provider.client.jobs.begin_delete.call_args_list
    ]
    assert deleted_jobs == ["job-a", "job-b"]
    fixture_group_provider.client.groups.begin_delete.assert_called_once()


def test_group_delete_blocked_by_in_flight_runs(fixture_group_provider):
    """Any referencing job with in-flight runs blocks the group delete entirely."""
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([
        _job_dict("job-running", "test-group", prov_state="Succeeded"),
    ])
    fixture_group_provider.client.job_runs.list_by_job.return_value = iter([
        {"name": "run-1", "properties": {"status": "Active"}},
        {"name": "run-2", "properties": {"status": "Queued"}},
    ])

    import pytest
    from azure.cli.core.azclierror import ArgumentUsageError
    with pytest.raises(ArgumentUsageError, match="2 in-flight run\\(s\\): run-1, run-2"):
        fixture_group_provider.delete(
            group_name="test-group",
            namespace_name="ns",
            resource_group_name="rg",
        )

    fixture_group_provider.client.jobs.begin_delete.assert_not_called()
    fixture_group_provider.client.groups.begin_delete.assert_not_called()


def test_group_delete_blocked_by_mid_operation_provisioning_state(fixture_group_provider):
    """Job in ARM mid-operation state (e.g. Creating) blocks the cascade."""
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([
        _job_dict("job-creating", "test-group", prov_state="Creating"),
    ])
    fixture_group_provider.client.job_runs.list_by_job.return_value = iter([])

    import pytest
    from azure.cli.core.azclierror import ArgumentUsageError
    with pytest.raises(ArgumentUsageError, match="provisioningState='Creating'"):
        fixture_group_provider.delete(
            group_name="test-group",
            namespace_name="ns",
            resource_group_name="rg",
        )

    fixture_group_provider.client.jobs.begin_delete.assert_not_called()
    fixture_group_provider.client.groups.begin_delete.assert_not_called()


def test_group_delete_block_message_lists_all_blocking_jobs(fixture_group_provider):
    """When multiple jobs block, every offender appears in the error message."""
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([
        _job_dict("job-a", "test-group", prov_state="Creating"),
        _job_dict("job-b", "test-group", prov_state="Succeeded"),
        _job_dict("job-c", "test-group", prov_state="Updating"),
    ])
    fixture_group_provider.client.job_runs.list_by_job.return_value = iter([])

    import pytest
    from azure.cli.core.azclierror import ArgumentUsageError
    with pytest.raises(ArgumentUsageError) as excinfo:
        fixture_group_provider.delete(
            group_name="test-group",
            namespace_name="ns",
            resource_group_name="rg",
        )
    msg = str(excinfo.value)
    assert "job-a" in msg
    assert "job-c" in msg
    assert "job-b" not in msg  # not blocked; not listed in the blocked summary
    assert "2 job(s)" in msg


def test_group_delete_handles_jobs_list_rbac_failure(fixture_group_provider, mock_poller):
    """Best-effort: jobs-list failure ⇒ empty inventory ⇒ group delete proceeds."""
    fixture_group_provider.client.jobs.list_by_namespace.side_effect = RuntimeError("forbidden")
    fixture_group_provider.client.groups.begin_delete.return_value = mock_poller(None)

    fixture_group_provider.delete(
        group_name="test-group",
        namespace_name="ns",
        resource_group_name="rg",
    )

    fixture_group_provider.client.jobs.begin_delete.assert_not_called()
    fixture_group_provider.client.groups.begin_delete.assert_called_once()


def test_group_delete_handles_runs_list_rbac_failure(fixture_group_provider, mock_poller):
    """Best-effort: per-job run-list failure ⇒ treat as no in-flight runs."""
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([
        _job_dict("job-a", "test-group", prov_state="Succeeded"),
    ])
    fixture_group_provider.client.job_runs.list_by_job.side_effect = RuntimeError("forbidden")
    fixture_group_provider.client.jobs.begin_delete.return_value = mock_poller(None)
    fixture_group_provider.client.groups.begin_delete.return_value = mock_poller(None)

    fixture_group_provider.delete(
        group_name="test-group",
        namespace_name="ns",
        resource_group_name="rg",
    )

    # Run-list failure must not block cascade; job-a should still be deleted.
    fixture_group_provider.client.jobs.begin_delete.assert_called_once()
    fixture_group_provider.client.groups.begin_delete.assert_called_once()


# ==================== Edge-case fills ====================


def test_group_delete_target_resource_id_case_insensitive(fixture_group_provider, mock_poller):
    """ARM resource IDs are case-insensitive; cascade inventory must match
    even when the job's targetResourceId stores the group segment in a
    different case than the delete request."""
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([
        {
            "name": "job-a",
            "properties": {
                "target": {
                    "targetResourceId": (
                        "/subscriptions/sub1/resourceGroups/RG/providers/"
                        "Microsoft.DeviceRegistry/namespaces/NS/groups/TEST-GROUP"
                    )
                },
                "provisioningState": "Succeeded",
            },
        },
    ])
    fixture_group_provider.client.job_runs.list_by_job.return_value = iter([])
    fixture_group_provider.client.jobs.begin_delete.return_value = mock_poller(None)
    fixture_group_provider.client.groups.begin_delete.return_value = mock_poller(None)

    fixture_group_provider.delete(
        group_name="test-group",  # lowercase
        namespace_name="ns",
        resource_group_name="rg",
    )

    # Despite case mismatch in the stored ID, the job must be identified as
    # referencing and cascaded.
    fixture_group_provider.client.jobs.begin_delete.assert_called_once()


def test_group_delete_per_job_run_list_failure_does_not_skip_other_jobs(
    fixture_group_provider, mock_poller
):
    """If one referencing job's runs-list call fails, the other jobs must still
    be inspected and cascade-deleted; the partial failure is treated as 'no
    in-flight runs' for that one job only."""
    fixture_group_provider.client.jobs.list_by_namespace.return_value = iter([
        _job_dict("job-a", "test-group", prov_state="Succeeded"),
        _job_dict("job-b", "test-group", prov_state="Succeeded"),
    ])

    call_count = {"n": 0}

    def side_effect(*_a, **_kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("forbidden on job-a only")
        return iter([])  # job-b: no in-flight runs

    fixture_group_provider.client.job_runs.list_by_job.side_effect = side_effect
    fixture_group_provider.client.jobs.begin_delete.return_value = mock_poller(None)
    fixture_group_provider.client.groups.begin_delete.return_value = mock_poller(None)

    fixture_group_provider.delete(
        group_name="test-group",
        namespace_name="ns",
        resource_group_name="rg",
    )

    # Both jobs must be cascade-deleted; the per-job RBAC failure on job-a
    # is degraded to "treat as no in-flight runs".
    deleted_jobs = [
        c.kwargs["job_name"] for c in fixture_group_provider.client.jobs.begin_delete.call_args_list
    ]
    assert deleted_jobs == ["job-a", "job-b"]


def test_group_show_members_with_null_members_field(fixture_group_provider):
    """SDK returns ``{"members": None}``; provider degrades to an empty list."""
    fixture_group_provider.client.groups.preview_members.return_value = {"members": None}
    assert (
        fixture_group_provider.show_members(
            group_name="g", namespace_name="ns", resource_group_name="rg"
        )
        == []
    )


def test_group_count_with_null_or_missing_count(fixture_group_provider):
    """SDK returns ``{}`` or ``{"count": None}``; provider returns 0."""
    fixture_group_provider.client.groups.get_current_member_count.return_value = {}
    assert (
        fixture_group_provider.count(
            group_name="g", namespace_name="ns", resource_group_name="rg"
        )
        == 0
    )

    fixture_group_provider.client.groups.get_current_member_count.return_value = {"count": None}
    assert (
        fixture_group_provider.count(
            group_name="g", namespace_name="ns", resource_group_name="rg"
        )
        == 0
    )
