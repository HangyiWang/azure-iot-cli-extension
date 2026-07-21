# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import (
    AzureResponseError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from azure.core.exceptions import HttpResponseError

from azext_iot.adr.common import PolicyCertificateKeyType


def test_legacy_policy_key_type_surface_is_ecc_only():
    assert [member.value for member in PolicyCertificateKeyType] == ["ECC"]


def test_policy_create_rejects_non_ecc_key_type(fixture_policy_provider):
    with pytest.raises(InvalidArgumentValueError, match="must be ECC"):
        fixture_policy_provider.create(
            "policy",
            "namespace",
            "rg",
            location="eastus",
            certificate_key_type="RSA",
        )
    fixture_policy_provider.client.policies.begin_create_or_update.assert_not_called()


def test_policy_create_all_fields(fixture_policy_provider, mock_poller):
    fixture_policy_provider.client.policies.begin_create_or_update.return_value = (
        mock_poller({"name": "policy"})
    )

    result = fixture_policy_provider.create(
        policy_name="policy",
        namespace_name="namespace",
        resource_group_name="rg",
        location="eastus",
        tags={"env": "test"},
        certificate_key_type="ECC",
        certificate_validity_days=14,
    )

    assert result == {"name": "policy"}
    fixture_policy_provider.client.policies.begin_create_or_update.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        policy_name="policy",
        resource={
            "location": "eastus",
            "tags": {"env": "test"},
            "properties": {
                "certificate": {
                    "certificateAuthorityConfiguration": {"keyType": "ECC"},
                    "leafCertificateConfiguration": {
                        "validityPeriodInDays": 14
                    },
                }
            },
        },
    )


def test_policy_create_without_certificate_options(fixture_policy_provider, mock_poller):
    fixture_policy_provider.client.policies.begin_create_or_update.return_value = (
        mock_poller({})
    )

    fixture_policy_provider.create(
        "policy", "namespace", "rg", location="eastus"
    )

    resource = fixture_policy_provider.client.policies.begin_create_or_update.call_args.kwargs[
        "resource"
    ]
    assert resource == {"location": "eastus", "properties": {}}


def test_policy_create_byor_uses_ecc_defaults(fixture_policy_provider, mock_poller):
    fixture_policy_provider.client.policies.begin_create_or_update.return_value = (
        mock_poller({})
    )

    fixture_policy_provider.create(
        "policy",
        "namespace",
        "rg",
        location="eastus",
        enable_byor=True,
    )

    certificate = fixture_policy_provider.client.policies.begin_create_or_update.call_args.kwargs[
        "resource"
    ]["properties"]["certificate"]
    assert certificate == {
        "certificateAuthorityConfiguration": {
            "keyType": "ECC",
            "bringYourOwnRoot": {"enabled": True},
        },
        "leafCertificateConfiguration": {"validityPeriodInDays": 30},
    }


def test_policy_create_inherits_parent_namespace_location(
    fixture_policy_provider, mock_poller
):
    fixture_policy_provider.client.namespaces.get.return_value = {
        "location": "westus2"
    }
    fixture_policy_provider.client.policies.begin_create_or_update.return_value = (
        mock_poller({})
    )

    fixture_policy_provider.create("policy", "namespace", "rg")

    resource = fixture_policy_provider.client.policies.begin_create_or_update.call_args.kwargs[
        "resource"
    ]
    assert resource["location"] == "westus2"


def test_policy_create_requires_parent_location(fixture_policy_provider):
    fixture_policy_provider.client.namespaces.get.return_value = {}

    with pytest.raises(AzureResponseError, match="location"):
        fixture_policy_provider.create("policy", "namespace", "rg")


@pytest.mark.parametrize("validity_days", [7, 8, 29, 30])
def test_policy_accepts_validity_range(
    fixture_policy_provider, mock_poller, validity_days
):
    fixture_policy_provider.client.policies.begin_create_or_update.return_value = (
        mock_poller({})
    )

    fixture_policy_provider.create(
        "policy",
        "namespace",
        "rg",
        location="eastus",
        certificate_validity_days=validity_days,
    )

    certificate = fixture_policy_provider.client.policies.begin_create_or_update.call_args.kwargs[
        "resource"
    ]["properties"]["certificate"]
    assert (
        certificate["leafCertificateConfiguration"]["validityPeriodInDays"]
        == validity_days
    )


@pytest.mark.parametrize("validity_days", [-1, 0, 6, 31, 365])
@pytest.mark.parametrize("operation", ["create", "update"])
def test_policy_rejects_validity_outside_7_to_30(
    fixture_policy_provider, validity_days, operation
):
    kwargs = {
        "policy_name": "policy",
        "namespace_name": "namespace",
        "resource_group_name": "rg",
        "certificate_validity_days": validity_days,
    }
    if operation == "create":
        kwargs["location"] = "eastus"

    with pytest.raises(InvalidArgumentValueError, match="between 7 and 30"):
        getattr(fixture_policy_provider, operation)(**kwargs)


def test_policy_create_no_wait(fixture_policy_provider, mock_poller):
    poller = mock_poller({})
    fixture_policy_provider.client.policies.begin_create_or_update.return_value = (
        poller
    )

    result = fixture_policy_provider.create(
        "policy", "namespace", "rg", location="eastus", no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()


def test_policy_show_and_list(fixture_policy_provider):
    fixture_policy_provider.client.namespaces.get.return_value = {}
    fixture_policy_provider.client.policies.get.return_value = {"name": "policy"}
    fixture_policy_provider.client.policies.list_by_credential.return_value = iter(
        [{"name": "one"}, {"name": "two"}]
    )

    assert fixture_policy_provider.show("policy", "namespace", "rg") == {
        "name": "policy"
    }
    assert fixture_policy_provider.list("namespace", "rg") == [
        {"name": "one"},
        {"name": "two"},
    ]


def _parent_not_found_error():
    class ParentNotFound(HttpResponseError):
        def __str__(self):
            return "ParentResourceNotFound"

    return ParentNotFound(response=Mock(status_code=404))


@pytest.mark.parametrize("operation", ["show", "list"])
def test_policy_translates_missing_credential(
    fixture_policy_provider, operation
):
    fixture_policy_provider.client.namespaces.get.return_value = {}
    target = (
        fixture_policy_provider.client.policies.get
        if operation == "show"
        else fixture_policy_provider.client.policies.list_by_credential
    )
    target.side_effect = _parent_not_found_error()
    args = (
        ("policy", "namespace", "rg")
        if operation == "show"
        else ("namespace", "rg")
    )

    with pytest.raises(ResourceNotFoundError, match="No credential exists"):
        getattr(fixture_policy_provider, operation)(*args)


def test_policy_update_tags_and_validity(fixture_policy_provider, mock_poller):
    fixture_policy_provider.client.policies.begin_update.return_value = mock_poller(
        {}
    )
    fixture_policy_provider.client.namespaces.get.return_value = {}
    fixture_policy_provider.client.policies.get.return_value = {"name": "policy"}

    result = fixture_policy_provider.update(
        "policy",
        "namespace",
        "rg",
        tags={"env": "prod"},
        certificate_validity_days=20,
    )

    assert result == {"name": "policy"}
    fixture_policy_provider.client.policies.begin_update.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        policy_name="policy",
        properties={
            "tags": {"env": "prod"},
            "properties": {
                "certificate": {
                    "leafCertificateConfiguration": {
                        "validityPeriodInDays": 20
                    }
                }
            },
        },
    )


def test_policy_update_rejects_empty_patch(fixture_policy_provider):
    with pytest.raises(RequiredArgumentMissingError, match="Nothing to update"):
        fixture_policy_provider.update("policy", "namespace", "rg")
    fixture_policy_provider.client.policies.begin_update.assert_not_called()


def test_policy_update_no_wait_does_not_get_resource(
    fixture_policy_provider, mock_poller
):
    poller = mock_poller({})
    fixture_policy_provider.client.policies.begin_update.return_value = poller

    result = fixture_policy_provider.update(
        "policy", "namespace", "rg", tags={}, no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()
    fixture_policy_provider.client.policies.get.assert_not_called()


def test_policy_delete_no_wait(fixture_policy_provider, mock_poller):
    poller = mock_poller(None)
    fixture_policy_provider.client.policies.begin_delete.return_value = poller

    result = fixture_policy_provider.delete(
        "policy", "namespace", "rg", no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()


def test_policy_revoke_and_activate_actions(fixture_policy_provider, mock_poller):
    fixture_policy_provider.client.policies.begin_revoke_issuer.return_value = (
        mock_poller({"revoked": True})
    )
    fixture_policy_provider.client.policies.begin_activate_bring_your_own_root.return_value = (
        mock_poller({"active": True})
    )

    assert fixture_policy_provider.revoke_issuer(
        "policy", "namespace", "rg"
    ) == {"revoked": True}
    assert fixture_policy_provider.activate_byor(
        "policy", "namespace", "rg", "certificate-chain"
    ) == {"active": True}
    fixture_policy_provider.client.policies.begin_activate_bring_your_own_root.assert_called_once_with(
        resource_group_name="rg",
        namespace_name="namespace",
        policy_name="policy",
        body={"certificateChain": "certificate-chain"},
    )


@pytest.mark.parametrize(
    "operation,sdk_method,extra_args",
    [
        ("revoke_issuer", "begin_revoke_issuer", ()),
        (
            "activate_byor",
            "begin_activate_bring_your_own_root",
            ("certificate-chain",),
        ),
    ],
)
def test_policy_actions_support_no_wait(
    fixture_policy_provider,
    mock_poller,
    operation,
    sdk_method,
    extra_args,
):
    poller = mock_poller(None)
    getattr(fixture_policy_provider.client.policies, sdk_method).return_value = poller

    result = getattr(fixture_policy_provider, operation)(
        "policy", "namespace", "rg", *extra_args, no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()
