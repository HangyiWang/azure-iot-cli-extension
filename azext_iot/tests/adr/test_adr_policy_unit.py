# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock

import pytest
from azure.cli.core.azclierror import CLIError, ResourceNotFoundError
from azure.core.exceptions import HttpResponseError

from azext_iot.adr.common import DEFAULT_NS_POLICY_CERT_KEY_TYPE, DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS


# ==================== Helpers ====================


def _setup_create(provider, mock_poller, serialized: dict, ns_location: str = "eastus"):
    """Wire up mocks needed for a ``create()`` call."""
    provider.client.policies.begin_create_or_update.return_value = mock_poller(serialized)
    provider.client.namespaces.get.return_value = {"location": ns_location}


def _setup_show(provider, serialized: dict):
    """Wire up mocks needed for a ``show()`` call (namespaces.get + policies.get)."""
    provider.client.namespaces.get.return_value = {}
    provider.client.policies.get.return_value = serialized


def _get_create_cert(provider) -> dict:
    """Extract the certificate dict from the last ``begin_create_or_update`` resource body."""
    resource = provider.client.policies.begin_create_or_update.call_args[1]["resource"]
    return resource.get("properties", {}).get("certificate")


# ==================== Create ====================


@pytest.mark.parametrize(
    "key_type, subject, days, location",
    [
        ("ECC", "test", 30, None),
        (None, None, None, None),
        ("ECC", "test", 30, "westus"),
    ],
    ids=["all-cert-params", "no-cert-params", "explicit-location"],
)
def test_create_policy(fixture_policy_provider, mock_poller, key_type, subject, days, location):
    """Policy creation with various parameter combinations."""
    expected = {"name": "policy", "properties": {"provisioningState": "Succeeded"}}
    _setup_create(fixture_policy_provider, mock_poller, expected)

    result = fixture_policy_provider.create(
        policy_name="policy", namespace_name="ns", resource_group_name="rg",
        location=location, certificate_key_type=key_type,
        certificate_subject=subject, certificate_validity_days=days,
    )

    assert result == expected

    if location:
        fixture_policy_provider.client.namespaces.get.assert_not_called()
    else:
        fixture_policy_provider.client.namespaces.get.assert_called_once()

    cert = _get_create_cert(fixture_policy_provider)
    if any([key_type, subject, days]):
        assert isinstance(cert, dict)
        assert cert["certificateAuthorityConfiguration"]["keyType"] == (key_type or DEFAULT_NS_POLICY_CERT_KEY_TYPE)
        assert cert["leafCertificateConfiguration"]["validityPeriodInDays"] == (days or DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS)
    else:
        assert cert is None


@pytest.mark.parametrize("key_type", [None, "ECC"])
@pytest.mark.parametrize("days", [None, 30])
@pytest.mark.parametrize("subject", [None, "test"])
def test_create_policy_defaults(fixture_policy_provider, mock_poller, key_type, days, subject):
    """Defaults are applied when at least one cert param is specified."""
    _setup_create(fixture_policy_provider, mock_poller, {"name": "p"})

    fixture_policy_provider.create(
        policy_name="p", namespace_name="ns", resource_group_name="rg",
        certificate_key_type=key_type, certificate_subject=subject, certificate_validity_days=days,
    )

    cert = _get_create_cert(fixture_policy_provider)
    if any([key_type, subject, days]):
        assert cert["certificateAuthorityConfiguration"]["keyType"] == (key_type or DEFAULT_NS_POLICY_CERT_KEY_TYPE)
        assert cert["leafCertificateConfiguration"]["validityPeriodInDays"] == (days or DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS)
    else:
        assert cert is None


def test_create_byor(fixture_policy_provider, mock_poller):
    """BYOR creation sets BringYourOwnRoot(enabled=True) with default cert params."""
    _setup_create(fixture_policy_provider, mock_poller, {"name": "byor"})

    fixture_policy_provider.create(
        policy_name="byor", namespace_name="ns", resource_group_name="rg", enable_byor=True,
    )

    cert = _get_create_cert(fixture_policy_provider)
    assert isinstance(cert, dict)
    ca = cert["certificateAuthorityConfiguration"]
    assert ca["bringYourOwnRoot"]["enabled"] is True
    assert ca["keyType"] == DEFAULT_NS_POLICY_CERT_KEY_TYPE
    assert cert["leafCertificateConfiguration"]["validityPeriodInDays"] == DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS


def test_create_byor_with_custom_options(fixture_policy_provider, mock_poller):
    """BYOR with explicit cert options respects the overrides."""
    _setup_create(fixture_policy_provider, mock_poller, {"name": "byor"})

    fixture_policy_provider.create(
        policy_name="byor", namespace_name="ns", resource_group_name="rg",
        enable_byor=True, certificate_key_type="ECC", certificate_validity_days=60,
    )

    cert = _get_create_cert(fixture_policy_provider)
    assert cert["certificateAuthorityConfiguration"]["bringYourOwnRoot"]["enabled"] is True
    assert cert["certificateAuthorityConfiguration"]["keyType"] == "ECC"
    assert cert["leafCertificateConfiguration"]["validityPeriodInDays"] == 60


# ==================== Show ====================


def test_show_policy(fixture_policy_provider):
    """Show returns the serialized policy and calls the correct SDK methods."""
    expected = {"name": "p", "properties": {"provisioningState": "Succeeded"}}
    _setup_show(fixture_policy_provider, expected)

    result = fixture_policy_provider.show(
        policy_name="p", namespace_name="ns", resource_group_name="rg",
    )

    assert result == expected
    fixture_policy_provider.client.policies.get.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", policy_name="p",
    )


# ==================== List ====================


def test_list_policies(fixture_policy_provider):
    """List returns serialized results for each policy."""
    fixture_policy_provider.client.namespaces.get.return_value = Mock()
    fixture_policy_provider.client.policies.list_by_resource_group.return_value = [
        {"name": "a"},
        {"name": "b"},
    ]

    result = fixture_policy_provider.list(namespace_name="ns", resource_group_name="rg")

    assert result == [{"name": "a"}, {"name": "b"}]

# ==================== Delete ====================


def test_delete_policy(fixture_policy_provider, mock_poller):
    """Delete triggers begin_delete LRO and returns the result."""
    sentinel = Mock()
    fixture_policy_provider.client.policies.begin_delete.return_value = mock_poller(sentinel)

    result = fixture_policy_provider.delete(
        policy_name="p", namespace_name="ns", resource_group_name="rg",
    )

    assert result == sentinel
    fixture_policy_provider.client.policies.begin_delete.assert_called_once_with(
        resource_group_name="rg", namespace_name="ns", policy_name="p",
    )

# ==================== Update ====================


@pytest.mark.parametrize("days", [None, 20], ids=["no-update", "update-validity"])
def test_update_policy(fixture_policy_provider, mock_poller, days):
    """Update triggers begin_update LRO then fetches fresh state via show()."""
    fixture_policy_provider.client.policies.begin_update.return_value = mock_poller(Mock())
    _setup_show(fixture_policy_provider, {"name": "p", "properties": {"provisioningState": "Succeeded"}})

    result = fixture_policy_provider.update(
        policy_name="p", namespace_name="ns", resource_group_name="rg",
        certificate_validity_days=days,
    )

    assert result["name"] == "p"

    resource = fixture_policy_provider.client.policies.begin_update.call_args[1]["properties"]
    if days is not None:
        cert_config = resource["properties"]["certificate"]
        assert cert_config["leafCertificateConfiguration"]["validityPeriodInDays"] == days
    else:
        assert "certificate" not in resource.get("properties", {})


# ==================== Revoke Issuer ====================


def test_revoke_issuer_not_available(fixture_policy_provider):
    """revoke-issuer endpoint not yet exposed by Microsoft.DeviceRegistry API; provider raises CLIError."""
    with pytest.raises(CLIError, match=r"not available yet"):
        fixture_policy_provider.revoke_issuer(
            policy_name="p", namespace_name="ns", resource_group_name="rg",
        )
    fixture_policy_provider.client.policies.begin_revoke_issuer.assert_not_called()


# ==================== Activate BYOR ====================


def test_activate_byor_not_available(fixture_policy_provider):
    """activate-byor endpoint not yet exposed by Microsoft.DeviceRegistry API; provider raises CLIError."""
    with pytest.raises(CLIError, match=r"not available yet"):
        fixture_policy_provider.activate_byor(
            policy_name="p", namespace_name="ns", resource_group_name="rg",
            certificate_chain="-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----",
        )
    fixture_policy_provider.client.policies.begin_activate_bring_your_own_root.assert_not_called()


# ==================== Error Scenarios ====================


def _make_parent_not_found_error():
    """Create an HttpResponseError mimicking a ParentResourceNotFound 404."""
    resp = Mock(status_code=404)

    class _Error(HttpResponseError):
        def __str__(self):
            return "ParentResourceNotFound"

    return _Error(response=resp)


@pytest.mark.parametrize("ns_exists", [True, False], ids=["credential-missing", "namespace-missing"])
def test_show_policy_not_found(fixture_policy_provider, ns_exists):
    """Show raises appropriate error when namespace or credential is missing."""
    _assert_not_found(fixture_policy_provider, "show",
                      {"policy_name": "p", "namespace_name": "ns", "resource_group_name": "rg"},
                      ns_exists)


@pytest.mark.parametrize("ns_exists", [True, False], ids=["credential-missing", "namespace-missing"])
def test_list_policies_not_found(fixture_policy_provider, ns_exists):
    """List raises appropriate error when namespace or credential is missing."""
    _assert_not_found(fixture_policy_provider, "list",
                      {"namespace_name": "ns", "resource_group_name": "rg"},
                      ns_exists)


def _assert_not_found(provider, method_name, kwargs, namespace_exists):
    """
    If the namespace exists but credential doesn't → friendly ResourceNotFoundError.
    If the namespace itself is missing → raw HttpResponseError propagates.
    """
    resp_404 = Mock(status_code=404)

    if namespace_exists:
        provider.client.namespaces.get.return_value = Mock()
        error = _make_parent_not_found_error()
        target = (
            provider.client.policies.list_by_resource_group
            if method_name == "list"
            else provider.client.policies.get
        )
        target.side_effect = error

        with pytest.raises(ResourceNotFoundError, match="No credential exists"):
            getattr(provider, method_name)(**kwargs)
    else:
        provider.client.namespaces.get.side_effect = HttpResponseError(response=resp_404)

        with pytest.raises(HttpResponseError):
            getattr(provider, method_name)(**kwargs)
