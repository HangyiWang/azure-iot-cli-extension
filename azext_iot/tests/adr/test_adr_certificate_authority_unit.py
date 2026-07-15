# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import (
    ArgumentUsageError,
    AzureResponseError,
    RequiredArgumentMissingError,
)


# ==================== Create ====================


@pytest.mark.parametrize(
    "ca_type, issuer_type, issuer_uuid, key_type, location",
    [
        ("Root", None, None, "ECC", None),
        ("ICA", "Internal", "11111111-1111-1111-1111-111111111111", None, "westus"),
        ("ICA", "External", None, "ECC", "eastus"),
    ],
    ids=["root-default-keytype", "internal-ica", "external-ica"],
)
def test_create_ca(
    fixture_ca_provider, mock_poller, ca_type, issuer_type, issuer_uuid, key_type, location
):
    """CA creation builds the expected resource body and resolves location."""
    sentinel = Mock()
    fixture_ca_provider.client.certificate_authorities.begin_create_or_replace.return_value = mock_poller(
        sentinel
    )
    fixture_ca_provider.client.namespaces.get.return_value = {"location": "eastus"}

    result = fixture_ca_provider.create(
        certificate_authority_name="ca",
        namespace_name="ns",
        resource_group_name="rg",
        certificate_authority_type=ca_type,
        issuer_type=issuer_type,
        issuer_certificate_authority_uuid=issuer_uuid,
        key_type=key_type,
        location=location,
    )

    assert result == sentinel
    call = fixture_ca_provider.client.certificate_authorities.begin_create_or_replace.call_args[1]
    resource = call["resource"]
    assert resource["properties"]["certificateAuthorityType"] == ca_type
    assert resource["properties"]["keyType"] == (key_type or "ECC")
    if issuer_type:
        assert resource["properties"]["issuer"]["issuerType"] == issuer_type
        if issuer_uuid:
            assert (
                resource["properties"]["issuer"]["issuerCertificateAuthorityUuid"]
                == issuer_uuid
            )
    else:
        assert "issuer" not in resource["properties"]
    assert resource["location"] == (location or "eastus")
    # location resolved from namespace only when not provided
    if location is None:
        fixture_ca_provider.client.namespaces.get.assert_called_once()
    else:
        fixture_ca_provider.client.namespaces.get.assert_not_called()


def test_create_ca_with_tags(fixture_ca_provider, mock_poller):
    """CA creation forwards tags in the resource body."""
    fixture_ca_provider.client.certificate_authorities.begin_create_or_replace.return_value = mock_poller(
        Mock()
    )

    fixture_ca_provider.create(
        certificate_authority_name="ca",
        namespace_name="ns",
        resource_group_name="rg",
        certificate_authority_type="Root",
        location="eastus",
        tags={"env": "test"},
    )

    resource = fixture_ca_provider.client.certificate_authorities.begin_create_or_replace.call_args[1][
        "resource"
    ]
    assert resource["tags"] == {"env": "test"}


def test_create_ca_namespace_missing_location(fixture_ca_provider):
    """Create raises when location is omitted and the namespace has none."""
    fixture_ca_provider.client.namespaces.get.return_value = {}

    with pytest.raises(AzureResponseError, match=r"location"):
        fixture_ca_provider.create(
            certificate_authority_name="ca",
            namespace_name="ns",
            resource_group_name="rg",
            certificate_authority_type="Root",
        )
    fixture_ca_provider.client.certificate_authorities.begin_create_or_replace.assert_not_called()


def test_create_ica_requires_issuer_type(fixture_ca_provider):
    with pytest.raises(RequiredArgumentMissingError, match="issuer-type"):
        fixture_ca_provider.create(
            certificate_authority_name="ca",
            namespace_name="ns",
            resource_group_name="rg",
            certificate_authority_type="ICA",
            location="eastus",
        )


def test_create_internal_ica_requires_issuer_uuid(fixture_ca_provider):
    with pytest.raises(RequiredArgumentMissingError, match="issuer-ca-uuid"):
        fixture_ca_provider.create(
            certificate_authority_name="ca",
            namespace_name="ns",
            resource_group_name="rg",
            certificate_authority_type="ICA",
            issuer_type="Internal",
            location="eastus",
        )


def test_create_root_rejects_issuer(fixture_ca_provider):
    with pytest.raises(ArgumentUsageError, match="only valid when --type ICA"):
        fixture_ca_provider.create(
            certificate_authority_name="ca",
            namespace_name="ns",
            resource_group_name="rg",
            certificate_authority_type="Root",
            issuer_type="External",
            location="eastus",
        )


# ==================== Show / List ====================


def test_show_ca(fixture_ca_provider):
    """Show returns the certificate authority resource."""
    fixture_ca_provider.client.certificate_authorities.get.return_value = {"name": "ca"}

    result = fixture_ca_provider.show(
        certificate_authority_name="ca", namespace_name="ns", resource_group_name="rg",
    )

    assert result["name"] == "ca"
    fixture_ca_provider.client.certificate_authorities.get.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", certificate_authority_name="ca",
    )


def test_list_ca(fixture_ca_provider):
    """List returns the certificate authorities as a list."""
    fixture_ca_provider.client.certificate_authorities.list_by_namespace.return_value = iter(
        [{"name": "ca1"}, {"name": "ca2"}]
    )

    result = fixture_ca_provider.list(namespace_name="ns", resource_group_name="rg")

    assert [r["name"] for r in result] == ["ca1", "ca2"]
    fixture_ca_provider.client.certificate_authorities.list_by_namespace.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns",
    )


# ==================== Update ====================


def test_update_ca_with_tags(fixture_ca_provider, mock_poller):
    """Update sends tags and then fetches fresh state via show()."""
    fixture_ca_provider.client.certificate_authorities.begin_update.return_value = mock_poller(Mock())
    fixture_ca_provider.client.certificate_authorities.get.return_value = {"name": "ca"}

    result = fixture_ca_provider.update(
        certificate_authority_name="ca", namespace_name="ns", resource_group_name="rg",
        tags={"env": "prod"},
    )

    assert result["name"] == "ca"
    properties = fixture_ca_provider.client.certificate_authorities.begin_update.call_args[1]["properties"]
    assert properties["tags"] == {"env": "prod"}


# ==================== Delete ====================


def test_delete_ca(fixture_ca_provider, mock_poller):
    """Delete triggers begin_delete LRO and returns the result."""
    sentinel = Mock()
    fixture_ca_provider.client.certificate_authorities.begin_delete.return_value = mock_poller(sentinel)

    result = fixture_ca_provider.delete(
        certificate_authority_name="ca", namespace_name="ns", resource_group_name="rg",
    )

    assert result == sentinel
    fixture_ca_provider.client.certificate_authorities.begin_delete.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", certificate_authority_name="ca",
    )


# ==================== Activate ====================


def test_activate_ca(fixture_ca_provider, mock_poller):
    """Activate triggers begin_activate with the certificate chain body."""
    sentinel = Mock()
    chain = "-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----"
    fixture_ca_provider.client.certificate_authorities.get.return_value = {
        "properties": {
            "certificateAuthorityType": "ICA",
            "issuer": {"issuerType": "External"},
        }
    }
    fixture_ca_provider.client.certificate_authorities.begin_activate.return_value = mock_poller(sentinel)

    result = fixture_ca_provider.activate(
        certificate_authority_name="ca", namespace_name="ns", resource_group_name="rg",
        certificate_chain=chain,
    )

    assert result == sentinel
    fixture_ca_provider.client.certificate_authorities.begin_activate.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", certificate_authority_name="ca",
        body={"certificateChain": chain},
    )


# ==================== Revoke ====================


def test_revoke_ca(fixture_ca_provider, mock_poller):
    """Revoke triggers begin_revoke LRO and returns the result."""
    sentinel = Mock()
    fixture_ca_provider.client.certificate_authorities.get.return_value = {
        "properties": {
            "certificateAuthorityType": "ICA",
            "issuer": {"issuerType": "Internal"},
        }
    }
    fixture_ca_provider.client.certificate_authorities.begin_revoke.return_value = mock_poller(sentinel)

    result = fixture_ca_provider.revoke(
        certificate_authority_name="ca", namespace_name="ns", resource_group_name="rg",
    )

    assert result == sentinel
    fixture_ca_provider.client.certificate_authorities.begin_revoke.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", certificate_authority_name="ca",
    )


def test_activate_rejects_internal_ica(fixture_ca_provider):
    fixture_ca_provider.client.certificate_authorities.get.return_value = {
        "properties": {
            "certificateAuthorityType": "ICA",
            "issuer": {"issuerType": "Internal"},
        }
    }

    with pytest.raises(ArgumentUsageError, match="issuerType 'External'"):
        fixture_ca_provider.activate(
            certificate_authority_name="ca",
            namespace_name="ns",
            resource_group_name="rg",
            certificate_chain="chain",
        )
    fixture_ca_provider.client.certificate_authorities.begin_activate.assert_not_called()


def test_revoke_rejects_external_ica(fixture_ca_provider):
    fixture_ca_provider.client.certificate_authorities.get.return_value = {
        "properties": {
            "certificateAuthorityType": "ICA",
            "issuer": {"issuerType": "External"},
        }
    }

    with pytest.raises(ArgumentUsageError, match="issuerType 'Internal'"):
        fixture_ca_provider.revoke(
            certificate_authority_name="ca",
            namespace_name="ns",
            resource_group_name="rg",
        )
    fixture_ca_provider.client.certificate_authorities.begin_revoke.assert_not_called()


# ==================== --no-wait + guards ====================


def test_create_ca_no_wait_returns_poller(fixture_ca_provider, mock_poller):
    """With --no-wait, create returns the poller without waiting."""
    poller = mock_poller({"name": "ca"})
    fixture_ca_provider.client.certificate_authorities.begin_create_or_replace.return_value = poller
    fixture_ca_provider.client.namespaces.get.return_value = {"location": "eastus"}

    result = fixture_ca_provider.create(
        certificate_authority_name="ca", namespace_name="ns", resource_group_name="rg",
        certificate_authority_type="Root", no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_delete_ca_no_wait_returns_poller(fixture_ca_provider, mock_poller):
    """With --no-wait, delete returns the poller without waiting."""
    poller = mock_poller(None)
    fixture_ca_provider.client.certificate_authorities.begin_delete.return_value = poller

    result = fixture_ca_provider.delete(
        certificate_authority_name="ca", namespace_name="ns", resource_group_name="rg", no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_update_ca_requires_a_field(fixture_ca_provider):
    """Update with no updatable fields raises RequiredArgumentMissingError."""
    with pytest.raises(RequiredArgumentMissingError):
        fixture_ca_provider.update(
            certificate_authority_name="ca", namespace_name="ns", resource_group_name="rg",
        )


def test_update_ca_no_wait_returns_poller(fixture_ca_provider, mock_poller):
    """With --no-wait, update returns the poller without waiting or re-fetching."""
    poller = mock_poller(Mock())
    fixture_ca_provider.client.certificate_authorities.begin_update.return_value = poller

    result = fixture_ca_provider.update(
        certificate_authority_name="ca", namespace_name="ns", resource_group_name="rg",
        tags={"env": "prod"}, no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()
    fixture_ca_provider.client.certificate_authorities.get.assert_not_called()
