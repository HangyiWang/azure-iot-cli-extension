# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import pytest
from azure.cli.core.azclierror import ArgumentUsageError


@pytest.mark.parametrize(
    "report_type,group_name,selector",
    [
        (
            "NamespaceUpdateComplianceReport",
            None,
            {"reportType": "NamespaceUpdateComplianceReport"},
        ),
        (
            "GroupBestUpdatesComplianceReport",
            "group",
            {
                "reportType": "GroupBestUpdatesComplianceReport",
                "reportTarget": "group",
            },
        ),
        (
            "GroupInstallableUpdatesReport",
            "group",
            {
                "reportType": "GroupInstallableUpdatesReport",
                "reportTarget": "group",
            },
        ),
    ],
)
def test_report_generate_all_types(
    fixture_report_provider,
    mock_poller,
    report_type,
    group_name,
    selector,
):
    fixture_report_provider.client.namespaces.begin_generate_report.return_value = (
        mock_poller({"reportType": report_type})
    )

    result = fixture_report_provider.generate(
        namespace_name="namespace",
        resource_group_name="rg",
        report_type=report_type,
        group_name=group_name,
    )

    assert result == {"reportType": report_type}
    fixture_report_provider.client.namespaces.begin_generate_report.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        body=selector,
    )


@pytest.mark.parametrize(
    "report_type,group_name,selector",
    [
        (
            "NamespaceUpdateComplianceReport",
            None,
            {"reportType": "NamespaceUpdateComplianceReport"},
        ),
        (
            "GroupBestUpdatesComplianceReport",
            "group",
            {
                "reportType": "GroupBestUpdatesComplianceReport",
                "reportTarget": "group",
            },
        ),
        (
            "GroupInstallableUpdatesReport",
            "group",
            {
                "reportType": "GroupInstallableUpdatesReport",
                "reportTarget": "group",
            },
        ),
    ],
)
def test_report_latest_all_types(
    fixture_report_provider, report_type, group_name, selector
):
    fixture_report_provider.client.namespaces.get_latest_report.return_value = {
        "reportType": report_type
    }

    result = fixture_report_provider.latest(
        namespace_name="namespace",
        resource_group_name="rg",
        report_type=report_type,
        group_name=group_name,
    )

    assert result == {"reportType": report_type}
    fixture_report_provider.client.namespaces.get_latest_report.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        body=selector,
    )


@pytest.mark.parametrize(
    "report_type",
    [
        "GroupBestUpdatesComplianceReport",
        "GroupInstallableUpdatesReport",
    ],
)
def test_group_report_requires_group(fixture_report_provider, report_type):
    with pytest.raises(ArgumentUsageError, match="--group-name is required"):
        fixture_report_provider.generate(
            "namespace", "rg", report_type=report_type
        )
    fixture_report_provider.client.namespaces.begin_generate_report.assert_not_called()


def test_namespace_report_rejects_group(fixture_report_provider):
    with pytest.raises(
        ArgumentUsageError, match="only valid for group update reports"
    ):
        fixture_report_provider.latest(
            "namespace",
            "rg",
            report_type="NamespaceUpdateComplianceReport",
            group_name="group",
        )
    fixture_report_provider.client.namespaces.get_latest_report.assert_not_called()


def test_report_rejects_unknown_type(fixture_report_provider):
    with pytest.raises(ArgumentUsageError, match="Unsupported report type"):
        fixture_report_provider.generate(
            "namespace", "rg", report_type="UnknownReport"
        )


def test_report_generate_no_wait(fixture_report_provider, mock_poller):
    poller = mock_poller(None)
    fixture_report_provider.client.namespaces.begin_generate_report.return_value = (
        poller
    )

    result = fixture_report_provider.generate(
        "namespace",
        "rg",
        report_type="NamespaceUpdateComplianceReport",
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()
