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


class GroupType(Enum):
    """Type of a Device Registry group.

    Only ``Device`` is defined in the 2026-11-02-preview spec; the enum is kept
    forward-compatible so future group types can be added without churn.
    """
    device = "Device"


class GroupMembershipState(Enum):
    """Membership state of a Device Registry group (read-only on the resource)."""
    creating = "Creating"
    refreshing_members = "RefreshingMembers"
    ready = "Ready"


class JobType(Enum):
    """Type of a Device Registry job.

    Only ``Update`` ships in the 2026-11-02-preview API. ``action`` and ``state``
    are reserved discriminator values in the spec (designed to be added as
    additional subtypes in v2). The enum is exposed in CLI help today so that
    future variants can be added without changing the surface, but the create
    provider rejects non-``Update`` values client-side until backend support
    lands.
    """
    update = "Update"
    action = "Action"
    state = "State"


class JobSchedulingType(Enum):
    """Scheduling type for an Update job definition.

    Only ``continuous`` is allowed for ``Update`` jobs in the current preview
    (ADU deployments target the group until superseded, canceled, or the parent
    job is deleted).
    """
    continuous = "continuous"


class JobRunStatus(Enum):
    """Status values for a job run (spec ``JobRunStatus`` union).

    Used by the Group/Job pre-delete checks to determine which runs are still
    "in flight" (i.e. consuming concurrency quota or actively executing).
    """
    scheduled = "Scheduled"
    queued = "Queued"
    active = "Active"
    succeeded = "Succeeded"
    failed = "Failed"
    timed_out = "TimedOut"
    canceled = "Canceled"


#: Job-run statuses that count as "in flight" for the job/group pre-delete
#: warning surface. Per design §2.2, the operator is warned that deleting will
#: cancel any runs in these states.
JOB_RUN_IN_FLIGHT_STATUSES = frozenset(
    {JobRunStatus.scheduled.value, JobRunStatus.queued.value, JobRunStatus.active.value}
)

#: Job provisioning states that are still mutable (not yet terminal). Used by
#: the Group cascade warning to filter out completed jobs.
JOB_ACTIVE_PROVISIONING_STATES = frozenset(
    {"Accepted", "Creating", "Updating", "Deleting", "Provisioning", "Running"}
)


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
