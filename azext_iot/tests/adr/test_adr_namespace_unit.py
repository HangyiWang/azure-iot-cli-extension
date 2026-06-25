# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from unittest.mock import Mock, patch

import pytest
from azure.cli.core.azclierror import (
    ArgumentUsageError,
    MutuallyExclusiveArgumentError,
)

from azext_iot.adr.common import (
    DEFAULT_NS_POLICY_CERT_KEY_TYPE,
    DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS,
    DEFAULT_NS_POLICY_NAME,
    IdentityType,
)


# ==================== Create ====================


@pytest.mark.parametrize("enable_certificate_management", [False, True])
@pytest.mark.parametrize("policy_name", [None, "test-policy"])
@pytest.mark.parametrize("cert_key_type", [None, DEFAULT_NS_POLICY_CERT_KEY_TYPE])
@pytest.mark.parametrize("cert_validity_days", [None, 30])
@pytest.mark.parametrize("cert_subject", [None, "CN=TestSubject"])
def test_create_namespace(
    fixture_namespace_provider,
    fixture_credential_provider,
    fixture_policy_provider,
    mock_poller,
    cert_key_type,
    cert_validity_days,
    cert_subject,
    policy_name,
    enable_certificate_management,
):
    """Namespace creation with credential-policy matrix."""
    ns_name, rg, location = "test-namespace", "test-rg", "eastus"

    fixture_credential_provider.create = Mock(return_value={"id": "credential-id"})
    fixture_policy_provider.create = Mock(return_value={"id": "policy-id"})

    # `--ecm` no longer drives the legacy credential/policy bootstrap; only explicit policy args do.
    has_policy_args = any([policy_name, cert_key_type, cert_subject, cert_validity_days])

    with patch(
        "azext_iot.adr.providers.namespace.CredentialProvider", return_value=fixture_credential_provider
    ), patch("azext_iot.adr.providers.namespace.PolicyProvider", return_value=fixture_policy_provider):
        ns_result_data = {
            "id": (
                f"/subscriptions/test-sub/resourceGroups/{rg}/"
                f"providers/Microsoft.DeviceRegistry/namespaces/{ns_name}"
            ),
            "name": ns_name,
            "type": "Microsoft.DeviceRegistry/namespaces",
            "location": location,
            "identity": {"principalId": "test-principal-id", "type": "SystemAssigned"},
            "resourceGroup": rg,
        }
        fixture_namespace_provider.client.namespaces.begin_create_or_replace.return_value = mock_poller(
            ns_result_data
        )

        create_kwargs = {
            "namespace_name": ns_name,
            "resource_group_name": rg,
            "location": location,
            "tags": None,
            "enable_certificate_management": enable_certificate_management,
            "policy_name": policy_name,
            "certificate_key_type": cert_key_type,
            "certificate_subject": cert_subject,
            "certificate_validity_days": cert_validity_days,
        }

        # Mutually-exclusive validation
        if enable_certificate_management is False and any([
            policy_name is not None,
            cert_key_type is not None,
            cert_validity_days is not None,
            cert_subject is not None,
        ]):
            with pytest.raises(MutuallyExclusiveArgumentError):
                fixture_namespace_provider.create(**create_kwargs)
            return

        result = fixture_namespace_provider.create(**create_kwargs)

        assert result["name"] == ns_name
        assert result["resourceGroup"] == rg

        call_args = fixture_namespace_provider.client.namespaces.begin_create_or_replace.call_args[1]
        assert call_args["resource"]["location"] == location
        assert call_args["resource"]["identity"] == {"type": IdentityType.system_assigned.value}

        # certificateManagement reflects the enable_certificate_management flag
        expected_cert_mgmt = "Enabled" if enable_certificate_management else "Disabled"
        assert call_args["resource"]["properties"]["certificateManagement"] == expected_cert_mgmt

        if has_policy_args:
            fixture_credential_provider.create.assert_called_once_with(
                namespace_name=ns_name, resource_group_name=rg, location=location,
            )
            fixture_policy_provider.create.assert_called_once_with(
                policy_name=policy_name or DEFAULT_NS_POLICY_NAME,
                namespace_name=ns_name,
                resource_group_name=rg,
                location=location,
                certificate_key_type=cert_key_type if cert_key_type is not None else DEFAULT_NS_POLICY_CERT_KEY_TYPE,
                certificate_subject=cert_subject,
                certificate_validity_days=(
                    cert_validity_days if cert_validity_days is not None else DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS
                ),
            )
        else:
            fixture_credential_provider.create.assert_not_called()
            fixture_policy_provider.create.assert_not_called()


def test_create_namespace_resolves_location_and_tags(
    fixture_namespace_provider, mock_poller
):
    """When location is omitted it is resolved; tags are passed through."""
    ns_name, rg = "test-namespace", "test-rg"
    fixture_namespace_provider._ensure_location = Mock(return_value="resolvedloc")
    fixture_namespace_provider.client.namespaces.begin_create_or_replace.return_value = mock_poller(
        {"name": ns_name}
    )

    fixture_namespace_provider.create(
        namespace_name=ns_name,
        resource_group_name=rg,
        location=None,
        tags={"env": "test"},
    )

    fixture_namespace_provider._ensure_location.assert_called_once()
    call_args = fixture_namespace_provider.client.namespaces.begin_create_or_replace.call_args[1]
    assert call_args["resource"]["location"] == "resolvedloc"
    assert call_args["resource"]["tags"] == {"env": "test"}


def test_create_namespace_credential_and_policy_errors_logged(
    fixture_namespace_provider, fixture_credential_provider, fixture_policy_provider, mock_poller
):
    """Credential/policy creation failures are caught and logged, not raised."""
    ns_name, rg, location = "test-namespace", "test-rg", "eastus"
    fixture_credential_provider.create = Mock(side_effect=Exception("cred boom"))
    fixture_policy_provider.create = Mock(side_effect=Exception("policy boom"))
    fixture_namespace_provider.client.namespaces.begin_create_or_replace.return_value = mock_poller(
        {"name": ns_name, "resourceGroup": rg}
    )

    with patch(
        "azext_iot.adr.providers.namespace.CredentialProvider", return_value=fixture_credential_provider
    ), patch("azext_iot.adr.providers.namespace.PolicyProvider", return_value=fixture_policy_provider):
        result = fixture_namespace_provider.create(
            namespace_name=ns_name,
            resource_group_name=rg,
            location=location,
            enable_certificate_management=True,
            policy_name="default",
        )

    assert result["name"] == ns_name
    fixture_credential_provider.create.assert_called_once()
    fixture_policy_provider.create.assert_called_once()


# ==================== Show ====================


def test_show_namespace(fixture_namespace_provider):
    """Show returns the serialized namespace."""
    expected = {"name": "test-namespace", "location": "eastus"}
    fixture_namespace_provider.client.namespaces.get.return_value = expected

    result = fixture_namespace_provider.show(namespace_name="test-namespace", resource_group_name="test-rg")

    assert result == expected
    fixture_namespace_provider.client.namespaces.get.assert_called_once_with(
        resource_group_name="test-rg", namespace_name="test-namespace",
    )


# ==================== Delete ====================


def test_delete_namespace(fixture_namespace_provider):
    """Delete triggers begin_delete LRO."""
    fixture_namespace_provider.client.namespaces.begin_delete.return_value = Mock()

    result = fixture_namespace_provider.delete(namespace_name="test-namespace", resource_group_name="test-rg")

    assert result is not None
    fixture_namespace_provider.client.namespaces.begin_delete.assert_called_once_with(
        resource_group_name="test-rg", namespace_name="test-namespace",
    )


# ==================== List ====================


def test_list_namespaces_by_resource_group(fixture_namespace_provider):
    """List by resource group returns serialized results."""
    expected = [{"name": "ns1", "location": "eastus"}, {"name": "ns2", "location": "westus"}]
    fixture_namespace_provider.client.namespaces.list_by_resource_group.return_value = expected

    assert fixture_namespace_provider.list(resource_group_name="test-rg") == expected
    fixture_namespace_provider.client.namespaces.list_by_resource_group.assert_called_once_with(
        resource_group_name="test-rg",
    )


def test_list_namespaces_by_subscription(fixture_namespace_provider):
    """List by subscription returns serialized results."""
    expected = [{"name": "ns1", "location": "eastus"}, {"name": "ns2", "location": "westus"}]
    fixture_namespace_provider.client.namespaces.list_by_subscription.return_value = expected

    assert fixture_namespace_provider.list() == expected
    fixture_namespace_provider.client.namespaces.list_by_subscription.assert_called_once()


# ==================== Update ====================


@pytest.mark.parametrize(
    "namespace_name, resource_group_name, tags",
    [
        ("test-namespace", "test-rg", {"env": "production"}),
        ("prod-namespace", "prod-rg", {"team": "platform", "env": "prod"}),
        ("update-namespace", "update-rg", None),
    ],
)
def test_update_namespace(fixture_namespace_provider, mock_poller, namespace_name, resource_group_name, tags):
    """Update triggers begin_update LRO and returns the serialized result."""
    expected = {"name": namespace_name, "location": "eastus"}
    fixture_namespace_provider.client.namespaces.begin_update.return_value = mock_poller(expected)

    result = fixture_namespace_provider.update(
        namespace_name=namespace_name, resource_group_name=resource_group_name, tags=tags,
    )

    assert result == expected

    kw = fixture_namespace_provider.client.namespaces.begin_update.call_args[1]
    assert kw["resource_group_name"] == resource_group_name
    assert kw["namespace_name"] == namespace_name
    if tags is not None:
        assert kw["properties"]["tags"] == tags
    else:
        assert kw["properties"] == {}


@pytest.mark.parametrize(
    "enable_certificate_management, expected_state",
    [(True, "Enabled"), (False, "Disabled")],
)
def test_update_namespace_certificate_management(
    fixture_namespace_provider, mock_poller, enable_certificate_management, expected_state
):
    """Update maps the certificate management flag to the certificateManagement enum state."""
    fixture_namespace_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )

    fixture_namespace_provider.update(
        namespace_name="ns",
        resource_group_name="rg",
        enable_certificate_management=enable_certificate_management,
    )

    kw = fixture_namespace_provider.client.namespaces.begin_update.call_args[1]
    assert kw["properties"]["properties"]["certificateManagement"] == expected_state


# ==================== Outbound Identity (P2) ====================


def test_create_namespace_outbound_sami(fixture_namespace_provider, mock_poller):
    """Passing --outbound-mi-system-assigned writes OutboundIdentity SAMI under properties."""
    fixture_namespace_provider.client.namespaces.begin_create_or_replace.return_value = mock_poller(
        {"name": "ns", "location": "eastus", "resourceGroup": "rg"}
    )
    fixture_namespace_provider.create(
        namespace_name="ns",
        resource_group_name="rg",
        location="eastus",
        outbound_mi_system_assigned=True,
    )
    body = fixture_namespace_provider.client.namespaces.begin_create_or_replace.call_args[1]["resource"]
    assert body["properties"]["outboundIdentity"] == {
        "type": IdentityType.system_assigned.value
    }


UAMI_RESOURCE_ID = (
    "/subscriptions/x/resourceGroups/y/providers/"
    "Microsoft.ManagedIdentity/userAssignedIdentities/uami"
)


def test_create_namespace_outbound_uami_rejected(fixture_namespace_provider):
    """UAMI for outbound identity is rejected client-side until backend lands."""
    with pytest.raises(ArgumentUsageError):
        fixture_namespace_provider.create(
            namespace_name="ns",
            resource_group_name="rg",
            location="eastus",
            outbound_mi_user_assigned=UAMI_RESOURCE_ID,
        )


def test_create_namespace_outbound_mi_mutually_exclusive(fixture_namespace_provider):
    """SAMI + UAMI together raises MutuallyExclusiveArgumentError."""
    with pytest.raises(MutuallyExclusiveArgumentError):
        fixture_namespace_provider.create(
            namespace_name="ns",
            resource_group_name="rg",
            location="eastus",
            outbound_mi_system_assigned=True,
            outbound_mi_user_assigned=UAMI_RESOURCE_ID,
        )


def test_update_namespace_outbound_sami(fixture_namespace_provider, mock_poller):
    """Updating with --outbound-mi-system-assigned nests OutboundIdentity under properties.properties."""
    fixture_namespace_provider.client.namespaces.begin_update.return_value = mock_poller(
        {"name": "ns"}
    )
    fixture_namespace_provider.update(
        namespace_name="ns",
        resource_group_name="rg",
        outbound_mi_system_assigned=True,
    )
    body = fixture_namespace_provider.client.namespaces.begin_update.call_args[1]["properties"]
    assert body["properties"]["outboundIdentity"] == {
        "type": IdentityType.system_assigned.value
    }


def test_update_namespace_outbound_uami_rejected(fixture_namespace_provider):
    with pytest.raises(ArgumentUsageError):
        fixture_namespace_provider.update(
            namespace_name="ns",
            resource_group_name="rg",
            outbound_mi_user_assigned=UAMI_RESOURCE_ID,
        )


# ==================== --no-wait short-circuit ====================


def test_namespace_delete_no_wait_returns_poller(fixture_namespace_provider, mock_poller):
    poller = mock_poller(None)
    fixture_namespace_provider.client.namespaces.begin_delete.return_value = poller

    result = fixture_namespace_provider.delete(
        namespace_name="ns", resource_group_name="rg", no_wait=True
    )

    assert result is poller
    poller.result.assert_not_called()


def test_namespace_update_no_wait_returns_poller(fixture_namespace_provider, mock_poller):
    poller = mock_poller({"name": "ns"})
    fixture_namespace_provider.client.namespaces.begin_update.return_value = poller

    result = fixture_namespace_provider.update(
        namespace_name="ns",
        resource_group_name="rg",
        outbound_mi_system_assigned=True,
        no_wait=True,
    )

    assert result is poller
    poller.result.assert_not_called()


def test_namespace_create_no_wait_skips_credential_policy_chain(
    fixture_namespace_provider, mock_poller
):
    """When --no-wait is set, chained credential+policy creates must be skipped
    (otherwise they race the still-provisioning namespace)."""
    poller = mock_poller({"name": "ns", "resourceGroup": "rg"})
    fixture_namespace_provider.client.namespaces.begin_create_or_replace.return_value = poller

    result = fixture_namespace_provider.create(
        namespace_name="ns",
        resource_group_name="rg",
        location="eastus",
        enable_certificate_management=True,
        policy_name="default",
        no_wait=True,
    )

    # Returned the poller, no chained calls happened.
    assert result is poller
    poller.result.assert_not_called()
    # Credential/policy provider methods would have hit the same client surface;
    # since we never imported them, the easiest check is that no namespace_credential
    # or namespace_policy calls were issued on the shared mock client.
    fixture_namespace_provider.client.namespace_credential.begin_create_or_replace.assert_not_called()
    fixture_namespace_provider.client.namespace_policies.begin_create_or_replace.assert_not_called()
