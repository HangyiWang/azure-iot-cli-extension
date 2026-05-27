# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

TARGET_GROUP_ID = (
    "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.DeviceRegistry/"
    "namespaces/ns/groups/g1"
)


def test_job_show(fixture_job_provider):
    mock_job = Mock()
    fixture_job_provider.client.jobs.get.return_value = mock_job

    result = fixture_job_provider.show(
        job_name="j1",
        namespace_name="ns1",
        resource_group_name="rg1",
    )

    assert result == mock_job
    fixture_job_provider.client.jobs.get.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        job_name="j1",
    )


def test_job_list(fixture_job_provider):
    fixture_job_provider.client.jobs.list_by_namespace.return_value = [Mock()]

    result = fixture_job_provider.list(
        namespace_name="ns1",
        resource_group_name="rg1",
    )

    assert len(result) == 1
    fixture_job_provider.client.jobs.list_by_namespace.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
    )


def test_job_create(fixture_job_provider, mock_poller):
    expected = {"name": "j1"}
    fixture_job_provider.client.jobs.begin_create_or_replace.return_value = mock_poller(expected)

    result = fixture_job_provider.create(
        job_name="j1",
        namespace_name="ns1",
        resource_group_name="rg1",
        target_group_id=TARGET_GROUP_ID,
        update_provider="Contoso",
        update_name="Toaster",
        update_version="1.0.0",
    )

    assert result == expected
    fixture_job_provider.client.jobs.begin_create_or_replace.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        job_name="j1",
        resource={
            "location": "westus",
            "properties": {
                "jobType": "Update",
                "target": {"targetResourceId": TARGET_GROUP_ID},
                "definition": {
                    "schedulingType": "continuous",
                    "update": {
                        "updateId": {
                            "provider": "Contoso",
                            "name": "Toaster",
                            "version": "1.0.0",
                        }
                    },
                },
            },
        },
    )


def test_job_create_with_tags_and_location(fixture_job_provider, mock_poller):
    fixture_job_provider.client.jobs.begin_create_or_replace.return_value = mock_poller(Mock())

    fixture_job_provider.create(
        job_name="j1",
        namespace_name="ns1",
        resource_group_name="rg1",
        target_group_id=TARGET_GROUP_ID,
        update_provider="p",
        update_name="n",
        update_version="v",
        location="eastus",
        tags={"env": "demo"},
    )

    called_kwargs = fixture_job_provider.client.jobs.begin_create_or_replace.call_args.kwargs
    assert called_kwargs["resource"]["location"] == "eastus"
    assert called_kwargs["resource"]["tags"] == {"env": "demo"}


def test_job_delete(fixture_job_provider, mock_poller):
    fixture_job_provider.client.jobs.begin_delete.return_value = mock_poller(None)

    fixture_job_provider.delete(
        job_name="j1",
        namespace_name="ns1",
        resource_group_name="rg1",
    )

    fixture_job_provider.client.jobs.begin_delete.assert_called_once_with(
        resource_group_name="rg1",
        namespace_name="ns1",
        job_name="j1",
    )
