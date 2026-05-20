# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import pytest
from azure.cli.core.azclierror import RequiredArgumentMissingError
from azext_iot.core.shared import DeviceRegistryNamespaceAuthenticationType
from azext_iot.tests.generators import generate_generic_id

# Import the functions under test
from azext_iot.core.custom import _build_dps_adr_properties

# Test constants
rg_id = f"/subscriptions/{generate_generic_id()}/resourceGroups/test-rg"
namespace_id = f"{rg_id}/providers/Microsoft.DeviceRegistry/namespaces/test-namespace"
identity_id = f"{rg_id}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/test-identity"


mock_existing_adr_properties = {
    "resourceId": "/old/namespace/id",
    "authenticationType": DeviceRegistryNamespaceAuthenticationType.SYSTEM_ASSIGNED,
}


class TestBuildDPSADRProperties(object):
    @pytest.mark.parametrize("existing_namespace", [None, mock_existing_adr_properties])
    @pytest.mark.parametrize("adr_ns_id", [None, namespace_id, ""])
    @pytest.mark.parametrize("adr_ns_identity_id", [None, identity_id, ""])
    def test_build_dps_adr_properties(self, existing_namespace, adr_ns_id, adr_ns_identity_id):
        """Test building DPS ADR properties with different parameter combinations."""

        # Determine if this should raise an error
        should_error = existing_namespace is None and not adr_ns_id

        # Handle error cases
        if should_error:
            with pytest.raises(RequiredArgumentMissingError) as exc_info:
                _build_dps_adr_properties(
                    existing_namespace=existing_namespace, adr_ns_id=adr_ns_id, adr_ns_identity_id=adr_ns_identity_id
                )
            assert "Device Registry namespace resource ID (--ns-resource-id) is required" in str(exc_info.value)
            return

        # Clear property scenario (existing namespace in get, user passed empty string for ns_id)
        if existing_namespace is not None and adr_ns_id == "":
            result = _build_dps_adr_properties(
                existing_namespace=existing_namespace, adr_ns_id=adr_ns_id, adr_ns_identity_id=adr_ns_identity_id
            )
            assert result is None
            return

        result = _build_dps_adr_properties(
            existing_namespace=existing_namespace, adr_ns_id=adr_ns_id, adr_ns_identity_id=adr_ns_identity_id
        )

        assert result is not None

        has_user_identity = adr_ns_identity_id and adr_ns_identity_id != ""

        if existing_namespace is None:
            # Creating new namespace
            assert result["resourceId"] == adr_ns_id
            if has_user_identity:
                assert result["authenticationType"] == DeviceRegistryNamespaceAuthenticationType.USER_ASSIGNED
                assert result["selectedUserAssignedIdentityResourceId"] == adr_ns_identity_id
            else:
                assert result["authenticationType"] == DeviceRegistryNamespaceAuthenticationType.SYSTEM_ASSIGNED
                assert result.get("selectedUserAssignedIdentityResourceId") is None
        else:
            # Updating existing namespace

            # Check if namespace ID was updated
            if adr_ns_id:
                assert result["resourceId"] == adr_ns_id
            else:
                assert result["resourceId"] == existing_namespace["resourceId"]

            # Check identity updates
            if adr_ns_identity_id is not None:
                if adr_ns_identity_id == "":
                    # Clearing identity - should switch to system auth
                    assert result["selectedUserAssignedIdentityResourceId"] is None
                    assert result["authenticationType"] == DeviceRegistryNamespaceAuthenticationType.SYSTEM_ASSIGNED
                else:
                    # Setting identity - should switch to user auth
                    assert result["selectedUserAssignedIdentityResourceId"] == adr_ns_identity_id
                    assert result["authenticationType"] == DeviceRegistryNamespaceAuthenticationType.USER_ASSIGNED
            else:
                # No identity change
                assert result["authenticationType"] == existing_namespace["authenticationType"]
                assert (
                    result.get("selectedUserAssignedIdentityResourceId")
                    == existing_namespace.get("selectedUserAssignedIdentityResourceId")
                )
