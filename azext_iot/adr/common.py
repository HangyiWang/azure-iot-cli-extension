# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from enum import Enum


class IdentityType(Enum):
    system_assigned = "SystemAssigned"


class InboundCallerIdentityType(Enum):
    system_assigned = "SystemAssigned"
    user_assigned = "UserAssigned"


class OutboundIdentityType(Enum):
    system_assigned = "SystemAssigned"
    user_assigned = "UserAssigned"


class MessagingEndpointAvailability(Enum):
    available = "Available"
    disabled = "Disabled"


class LinkingState(Enum):
    """Linking state of a messaging/provisioning endpoint entry on a Namespace."""
    in_progress = "InProgress"
    succeeded = "Succeeded"
    failed = "Failed"


class PolicyCertificateKeyType(Enum):
    ecc = "ECC"
    rsa = "RSA"


# Endpoint type discriminators on Namespace messaging / provisioning endpoints
IOT_HUB_ENDPOINT_TYPE = "Microsoft.Devices/IotHubs"
DPS_ENDPOINT_TYPE = "Microsoft.Devices/provisioningServices"


DEFAULT_NS_POLICY_CERT_VALIDITY_DAYS = 30
DEFAULT_NS_CREDENTIAL_NAME = "default"
DEFAULT_NS_POLICY_NAME = "default"
DEFAULT_NS_POLICY_CERT_KEY_TYPE = PolicyCertificateKeyType.ecc.value

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
