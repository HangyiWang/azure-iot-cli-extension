# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from enum import Enum
from typing import Optional

from azure.cli.core.azclierror import InvalidArgumentValueError


class IdentityType(Enum):
    system_assigned = "SystemAssigned"
    user_assigned = "UserAssigned"


class ManagedServiceIdentityType(Enum):
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


class JobType(Enum):
    software_update = "SoftwareUpdate"
    onboarding_update = "OnboardingUpdate"


class JobSchedulingType(Enum):
    continuous = "Continuous"


class ReportType(Enum):
    namespace_update_compliance = "NamespaceUpdateComplianceReport"
    group_best_updates_compliance = "GroupBestUpdatesComplianceReport"
    group_installable_updates = "GroupInstallableUpdatesReport"


class NamespaceMigrateScope(Enum):
    resources = "Resources"


class PolicyCertificateKeyType(Enum):
    ecc = "ECC"


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


DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS = 30
DEFAULT_NS_CREDENTIAL_NAME = "default"
DEFAULT_NS_POLICY_NAME = "default"
DEFAULT_NS_POLICY_CERT_KEY_TYPE = PolicyCertificateKeyType.ecc.value
DEFAULT_NS_CA_KEY_TYPE = CertificateAuthorityKeyType.ecc.value


def validate_policy_certificate_options(
    key_type: Optional[str],
    validity_days: Optional[int],
) -> None:
    if key_type is not None and key_type != DEFAULT_NS_POLICY_CERT_KEY_TYPE:
        raise InvalidArgumentValueError("--cert-key-type must be ECC.")
    if validity_days is not None and not 7 <= validity_days <= 30:
        raise InvalidArgumentValueError(
            "--cert-validity-days must be between 7 and 30."
        )


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


# Error message templates
CREDENTIAL_NOT_FOUND_MSG = (
    "No credential found for namespace '{namespace_name}' in resource group '{resource_group_name}'. "
    "Use 'az iot adr ns credential create --ns {namespace_name} -g {resource_group_name}' to create one."
)
POLICY_PARENT_RESOURCE_NOT_FOUND_MSG = (
    "No credential exists on namespace '{namespace_name}' in resource group '{resource_group_name}'. "
    "Please create a credential using 'az iot adr ns credential create --ns {namespace_name} -g {resource_group_name}' "
    "to manage credential policies."
)

CA_PARENT_RESOURCE_NOT_FOUND_MSG = (
    "No certificate authority '{certificate_authority_name}' exists on namespace '{namespace_name}' "
    "in resource group '{resource_group_name}'. "
    "Please create one using 'az iot adr ns ca create --name {certificate_authority_name} "
    "--ns {namespace_name} -g {resource_group_name}' to manage certificate policies."
)
