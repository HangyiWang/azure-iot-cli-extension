# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from enum import Enum
from typing import Optional, Sequence

from azure.cli.core.azclierror import InvalidArgumentValueError
from msrestazure.tools import is_valid_resource_id, parse_resource_id


class IdentityType(Enum):
    system_assigned = "SystemAssigned"
    user_assigned = "UserAssigned"


class ManagedServiceIdentityType(Enum):
    none = "None"
    system_assigned = "SystemAssigned"
    user_assigned = "UserAssigned"
    system_assigned_user_assigned = "SystemAssigned,UserAssigned"


class MessagingEndpointAvailability(Enum):
    available = "Available"
    disabled = "Disabled"


class GroupType(Enum):
    """Type of a Device Registry group.

    Only ``Device`` is currently defined; the enum is kept forward-compatible
    so future group types can be added without churn.
    """
    device = "Device"


class RegistryDeviceEnablementState(Enum):
    enabled = "Enabled"
    disabled = "Disabled"


class RegistryDeviceAuthenticationType(Enum):
    certificate_authority = "CertificateAuthority"
    self_signed_x509_certificate = "SelfSignedX509Certificate"
    symmetric_key = "SymmetricKey"


class JobType(Enum):
    software_update = "SoftwareUpdate"
    onboarding_update = "OnboardingUpdate"


class JobSchedulingType(Enum):
    continuous = "Continuous"


class ReportType(Enum):
    namespace_update_compliance = "NamespaceUpdateComplianceReport"
    group_best_updates_compliance = "GroupBestUpdatesComplianceReport"
    group_installable_updates = "GroupInstallableUpdatesReport"


class CertificateAuthorityType(Enum):
    root = "Root"
    ica = "ICA"


class CertificateAuthorityKeyType(Enum):
    ecc = "ECC"


class CertificateAuthorityIssuerType(Enum):
    internal = "Internal"
    external = "External"


# Endpoint type discriminators on Namespace messaging / provisioning / updating endpoints
IOT_HUB_ENDPOINT_TYPE = "Microsoft.Devices/IotHubs"
DPS_ENDPOINT_TYPE = "Microsoft.Devices/provisioningServices"
ADU_ENDPOINT_TYPE = "Microsoft.DeviceUpdate/updateInstances"


DEFAULT_NS_CA_KEY_TYPE = CertificateAuthorityKeyType.ecc.value


def validate_uami_resource_id(resource_id: str) -> str:
    """Validate and return a user-assigned managed identity ARM ID."""
    if not is_valid_resource_id(resource_id):
        raise InvalidArgumentValueError(
            f"'{resource_id}' is not a valid user-assigned managed identity "
            "resource ID."
        )
    parsed = parse_resource_id(resource_id)
    if (
        (parsed.get("namespace") or "").lower()
        != "microsoft.managedidentity"
        or (parsed.get("type") or "").lower() != "userassignedidentities"
        or "child_name_1" in parsed
    ):
        raise InvalidArgumentValueError(
            f"'{resource_id}' is not a Microsoft.ManagedIdentity/"
            "userAssignedIdentities resource ID."
        )
    return resource_id


def build_managed_service_identity(
    system_assigned: Optional[bool],
    user_assigned_identities: Optional[Sequence[str]],
) -> Optional[dict]:
    """Build the complete desired ARM managed identity state."""
    identities = {}
    for resource_id in user_assigned_identities or []:
        validated_id = validate_uami_resource_id(resource_id)
        identities.setdefault(validated_id.rstrip("/").casefold(), validated_id)

    if system_assigned is None and not identities:
        return None
    if system_assigned and identities:
        identity_type = ManagedServiceIdentityType.system_assigned_user_assigned.value
    elif system_assigned:
        identity_type = ManagedServiceIdentityType.system_assigned.value
    elif identities:
        identity_type = ManagedServiceIdentityType.user_assigned.value
    else:
        identity_type = ManagedServiceIdentityType.none.value

    identity = {"type": identity_type}
    if identities:
        identity["userAssignedIdentities"] = {
            resource_id: {} for resource_id in identities.values()
        }
    return identity


def build_mi_body(
    mi_system_assigned: Optional[bool],
    mi_user_assigned: Optional[str],
    *,
    sami_type: str,
    uami_type: str,
) -> Optional[dict]:
    """Build a managed-identity body dict, or None if neither flag is set.

    Shared by the link endpoint (InboundCallerIdentity) and namespace
    (OutboundIdentity) surfaces. Callers are responsible for SAMI/UAMI mutex
    enforcement, required-argument checks, and any surface-specific UAMI
    restrictions (the contracts vary).

    Empty/whitespace ``mi_user_assigned`` is treated as "not provided" so a
    stray ``--…-mi-user-assigned ""`` does not emit a malformed body.
    """
    if mi_user_assigned is not None and not mi_user_assigned.strip():
        mi_user_assigned = None
    if mi_user_assigned:
        return {"type": uami_type, "userAssignedIdentity": mi_user_assigned}
    if mi_system_assigned:
        return {"type": sami_type}
    return None


CA_PARENT_RESOURCE_NOT_FOUND_MSG = (
    "No certificate authority '{certificate_authority_name}' exists on namespace '{namespace_name}' "
    "in resource group '{resource_group_name}'. "
    "Please create one using 'az iot adr ns ca create --name {certificate_authority_name} "
    "--ns {namespace_name} -g {resource_group_name}' to manage certificate policies."
)
