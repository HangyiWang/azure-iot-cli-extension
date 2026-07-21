# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Parameter definitions for Azure Device Registry (ADR) namespace commands.
"""

from azure.cli.core.commands.parameters import (
    get_location_type,
    resource_group_name_type,
    tags_type,
    get_enum_type,
    get_three_state_flag,
)
from azure.cli.core.commands.validators import get_default_location_from_resource_group
from azext_iot.adr.common import (
    CertificateAuthorityKeyType,
    CertificateAuthorityIssuerType,
    CertificateAuthorityType,
    GroupType,
    JobType,
    MessagingEndpointAvailability,
    NamespaceMigrateScope,
    PolicyCertificateKeyType,
    ReportType,
)


def load_adr_arguments(self, _):
    """Load arguments for ADR namespace commands."""

    # Common arguments
    with self.argument_context("iot adr ns") as context:
        context.argument("resource_group_name", arg_type=resource_group_name_type)
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--name", "-n"],
            help="Name of the Device Registry namespace.",
        )
        context.argument("tags", arg_type=tags_type)

    # Namespace create arguments
    with self.argument_context("iot adr ns create") as context:
        context.argument(
            "location",
            arg_type=get_location_type(self.cli_ctx),
            validator=get_default_location_from_resource_group,
        )
        context.argument(
            "policy_name",
            arg_group="Policy",
            options_list=["--policy-name", "--pn"],
            help="Customize the name of the namespace credential policy",
        )

    with self.argument_context("iot adr ns migrate") as context:
        context.argument(
            "scope",
            options_list=["--scope"],
            arg_type=get_enum_type(NamespaceMigrateScope),
            help="Scope of the migration operation.",
        )
        context.argument(
            "resource_ids",
            options_list=["--resource-ids"],
            nargs="+",
            help="One or more resource IDs to migrate into the namespace.",
        )

    # Credentials naming arguments
    with self.argument_context("iot adr ns credential") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace.",
        )

    # Policy naming arguments
    with self.argument_context("iot adr ns policy") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace.",
        )
        # `-n` follows the standard naming convention; `--pn` mirrors `adr ns create`.
        context.argument(
            "policy_name", options_list=["--policy-name", "--pn", "--name", "-n"], help="Name of the policy."
        )

    # Policy certificate key type is create-only.
    for cmd in ["iot adr ns policy create", "iot adr ns create"]:
        with self.argument_context(cmd) as context:
            context.argument(
                "certificate_key_type",
                options_list=["--cert-key-type"],
                arg_type=get_enum_type(PolicyCertificateKeyType),
                arg_group="Policy Certificate",
                help="Policy certificate authority key type.",
            )

    # Certificate validity can be set on create or update
    for cmd in ["iot adr ns policy create", "iot adr ns policy update", "iot adr ns create"]:
        with self.argument_context(cmd) as context:
            context.argument(
                "certificate_validity_days",
                options_list=["--cert-validity-days"],
                type=int,
                arg_group="Policy Certificate",
                help="Policy certificate validity period in days.",
            )

    # BYOR (Bring Your Own Root) arguments for policy create
    with self.argument_context("iot adr ns policy create") as context:
        context.argument(
            "location",
            arg_type=get_location_type(self.cli_ctx),
        )
        context.argument(
            "enable_byor",
            options_list=["--enable-byor"],
            arg_type=get_three_state_flag(),
            arg_group="Bring Your Own Root",
            help="Enable Bring Your Own Root (BYOR) mode for the policy. "
                 "When enabled, you must sign the service-generated CSR with your own CA "
                 "and activate using 'az iot adr ns policy activate-byor'. "
                 "This cannot be changed after policy creation.",
        )

    # BYOR activation arguments
    with self.argument_context("iot adr ns policy activate-byor") as context:
        context.argument(
            "certificate_chain_file",
            options_list=["--certificate-chain-file", "--ccf"],
            help="Path to a PEM file containing the signed certificate chain. "
                 "The file must contain the signed certificate (matching the CSR from policy show), "
                 "followed by any intermediate CAs, and optionally the root CA. "
                 "Certificates must be ordered from leaf to root.",
        )

    # Certificate Authority arguments
    with self.argument_context("iot adr ns ca") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace.",
        )
        context.argument(
            "certificate_authority_name",
            options_list=["--name", "-n", "--ca-name"],
            help="Name of the certificate authority.",
        )
        context.argument("tags", arg_type=tags_type)

    with self.argument_context("iot adr ns ca create") as context:
        context.argument(
            "location",
            arg_type=get_location_type(self.cli_ctx),
        )
        context.argument(
            "certificate_authority_type",
            options_list=["--type", "--ca-type"],
            arg_type=get_enum_type(CertificateAuthorityType),
            help="The certificate authority type. Use 'Root' for a service-managed self-signed root CA "
                 "or 'ICA' for an intermediate CA.",
        )
        context.argument(
            "issuer_type",
            options_list=["--issuer-type"],
            arg_type=get_enum_type(CertificateAuthorityIssuerType),
            help="Issuer type for an ICA. Use 'Internal' for a same-namespace CA or 'External' "
                 "for an external PKI.",
        )
        context.argument(
            "issuer_certificate_authority_uuid",
            options_list=["--issuer-ca-uuid", "--issuer-certificate-authority-uuid"],
            help="UUID of the same-namespace issuing CA. Required with --issuer-type Internal.",
        )
        context.argument(
            "key_type",
            options_list=["--key-type"],
            arg_type=get_enum_type(CertificateAuthorityKeyType),
            help="The cryptographic key type for the certificate authority.",
        )

    with self.argument_context("iot adr ns ca activate") as context:
        context.argument(
            "certificate_chain_file",
            options_list=["--certificate-chain-file", "--ccf"],
            help="Path to a PEM file containing the signed certificate chain for an externally issued "
                 "ICA. Certificates must be ordered from leaf to root.",
        )

    # Certificate Policy (nested under a certificate authority) arguments
    with self.argument_context("iot adr ns ca policy") as context:
        context.argument(
            "certificate_policy_name",
            options_list=["--name", "-n", "--policy-name", "--pn"],
            help="Name of the certificate policy.",
        )
        context.argument(
            "certificate_authority_name",
            options_list=["--ca-name", "--ca"],
            help="Name of the parent certificate authority.",
        )
        context.argument("tags", arg_type=tags_type)

    with self.argument_context("iot adr ns ca policy create") as context:
        context.argument(
            "validity_days",
            options_list=["--validity-days", "--vd"],
            type=int,
            help="Leaf certificate validity period in days.",
        )
        context.argument(
            "location",
            arg_type=get_location_type(self.cli_ctx),
        )

    # Device arguments
    with self.argument_context("iot adr ns device") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace.",
        )
        context.argument(
            "device_name",
            options_list=["--device-name", "--dn", "--name", "-n"],
            help="Name of the device.",
        )

    # Device update arguments
    with self.argument_context("iot adr ns device update") as context:
        context.argument("tags", arg_type=tags_type)
        context.argument(
            "enabled",
            options_list=["--enabled"],
            arg_type=get_three_state_flag(),
            help="Enable or disable the device. A disabled device cannot authenticate with Microsoft Entra ID.",
        )
        context.argument(
            "operating_system_version",
            options_list=["--os-version"],
            help="Operating system version of the device.",
        )
        context.argument(
            "attributes",
            options_list=["--attributes"],
            help="Device attributes in JSON format.",
        )
        context.argument(
            "endpoints",
            options_list=["--endpoints"],
            help="Device messaging endpoints JSON with optional 'inbound' and 'outbound' properties.",
        )
        context.argument(
            "policy_resource_id",
            options_list=["--policy-resource-id"],
            help="Resource ID of the credential policy to associate with the device.",
        )

    # Device create arguments
    with self.argument_context("iot adr ns device create") as context:
        context.argument(
            "location",
            arg_type=get_location_type(self.cli_ctx),
        )
        context.argument("tags", arg_type=tags_type)
        context.argument(
            "manufacturer",
            options_list=["--manufacturer"],
            help="Manufacturer of the device.",
        )
        context.argument(
            "model",
            options_list=["--model"],
            help="Model of the device.",
        )
        context.argument(
            "operating_system",
            options_list=["--os"],
            help="Operating system of the device.",
        )
        context.argument(
            "operating_system_version",
            options_list=["--os-version"],
            help="Operating system version of the device.",
        )
        context.argument(
            "external_device_id",
            options_list=["--external-device-id", "--ext-id"],
            help="External identifier of the device.",
        )
        context.argument(
            "enabled",
            options_list=["--enabled"],
            arg_type=get_three_state_flag(),
            help="Enable or disable the device.",
        )
        context.argument(
            "attributes",
            options_list=["--attributes"],
            help="Device attributes in JSON format.",
        )
        context.argument(
            "endpoints",
            options_list=["--endpoints"],
            help="Device messaging endpoints JSON with optional 'inbound' and 'outbound' properties.",
        )
        context.argument(
            "discovered_device_ref",
            options_list=["--discovered-device-ref", "--ddr"],
            help="Reference to the discovered device this namespace device was provisioned from.",
        )
        context.argument(
            "policy_resource_id",
            options_list=["--policy-resource-id"],
            help="Resource ID of the credential policy to associate with the device.",
        )

    # Outbound managed identity arguments (namespace create + update)
    for cmd in ["iot adr ns create", "iot adr ns update"]:
        with self.argument_context(cmd) as context:
            context.argument(
                "outbound_mi_system_assigned",
                arg_group="Outbound Identity",
                options_list=["--outbound-mi-system-assigned", "--omi-sa"],
                arg_type=get_three_state_flag(),
                help="Enable the system-assigned managed identity as the outbound identity used by "
                     "this namespace when calling linked Hub/DPS resources.",
            )
            context.argument(
                "outbound_mi_user_assigned",
                arg_group="Outbound Identity",
                options_list=["--outbound-mi-user-assigned", "--omi-ua"],
                help="User-assigned managed identity resource ID to assign to the namespace and use "
                     "for outbound calls.",
            )

    # Link hub arguments
    with self.argument_context("iot adr ns link hub") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace that owns the link.",
        )
        context.argument(
            "endpoint_name",
            options_list=["--endpoint-name", "--en", "--name", "-n"],
            help="Logical name of the messaging endpoint entry on the namespace.",
        )

    for cmd in ["iot adr ns link hub add", "iot adr ns link hub update"]:
        with self.argument_context(cmd) as context:
            context.argument(
                "mi_system_assigned",
                arg_group="Inbound Caller Identity",
                options_list=["--mi-system-assigned", "--mi-sa"],
                arg_type=get_three_state_flag(),
                help="Use the linked IoT Hub's system-assigned identity as the inbound caller "
                     "identity. The Hub must have that identity enabled.",
            )
            context.argument(
                "mi_user_assigned",
                arg_group="Inbound Caller Identity",
                options_list=["--mi-user-assigned", "--mi-ua"],
                help="Resource ID of a user-assigned identity attached to the linked IoT Hub.",
            )

    with self.argument_context("iot adr ns link hub add") as context:
        context.argument(
            "availability",
            arg_group="Provisioning",
            options_list=["--availability"],
            arg_type=get_enum_type(MessagingEndpointAvailability),
            help="Whether the endpoint is available for provisioning new devices.",
        )
        context.argument(
            "allocation_weight",
            arg_group="Provisioning",
            options_list=["--allocation-weight", "--weight"],
            type=int,
            help="Relative allocation weight used when distributing devices across endpoints.",
        )
        context.argument(
            "hub_resource_id",
            options_list=["--hub-resource-id", "--hub-id"],
            help="Azure resource ID of the IoT Hub to link to this namespace.",
        )

    # Link DPS arguments
    with self.argument_context("iot adr ns link dps") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace that owns the link.",
        )
        context.argument(
            "endpoint_name",
            options_list=["--endpoint-name", "--en", "--name", "-n"],
            help="Logical name of the provisioning endpoint entry on the namespace.",
        )

    for cmd in ["iot adr ns link dps add", "iot adr ns link dps update"]:
        with self.argument_context(cmd) as context:
            context.argument(
                "mi_system_assigned",
                arg_group="Inbound Caller Identity",
                options_list=["--mi-system-assigned", "--mi-sa"],
                arg_type=get_three_state_flag(),
                help="Use the linked DPS resource's system-assigned identity as the inbound caller "
                     "identity. DPS must have that identity enabled.",
            )
            context.argument(
                "mi_user_assigned",
                arg_group="Inbound Caller Identity",
                options_list=["--mi-user-assigned", "--mi-ua"],
                help="Resource ID of a user-assigned identity attached to the linked DPS resource.",
            )

    with self.argument_context("iot adr ns link dps add") as context:
        context.argument(
            "dps_resource_id",
            options_list=["--dps-resource-id", "--dps-id"],
            help="Azure resource ID of the Device Provisioning Service to link to this namespace.",
        )

    # Link ADU arguments
    with self.argument_context("iot adr ns link adu") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace that owns the link.",
        )
        context.argument(
            "endpoint_name",
            options_list=["--endpoint-name", "--en", "--name", "-n"],
            help="Logical name of the device update (ADU) endpoint entry on the namespace.",
        )

    for cmd in ["iot adr ns link adu add", "iot adr ns link adu update"]:
        with self.argument_context(cmd) as context:
            context.argument(
                "mi_system_assigned",
                arg_group="Inbound Caller Identity",
                options_list=["--mi-system-assigned", "--mi-sa"],
                arg_type=get_three_state_flag(),
                help="Use the linked Device Update instance's system-assigned identity as the inbound "
                     "caller identity. The instance must have that identity enabled.",
            )
            context.argument(
                "mi_user_assigned",
                arg_group="Inbound Caller Identity",
                options_list=["--mi-user-assigned", "--mi-ua"],
                help="Resource ID of a user-assigned identity attached to the linked Device Update instance.",
            )

    with self.argument_context("iot adr ns link adu add") as context:
        context.argument(
            "adu_resource_id",
            options_list=["--adu-resource-id", "--adu-id"],
            help="Azure resource ID of the Device Update instance to link to this namespace.",
        )

    # Bundled link add
    with self.argument_context("iot adr ns link add") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace that will own both new links.",
        )
        context.argument(
            "hub_endpoint_name",
            arg_group="Hub",
            options_list=["--hub-name", "--hn"],
            help="Logical name of the Hub messaging endpoint entry on the namespace.",
        )
        context.argument(
            "hub_resource_id",
            arg_group="Hub",
            options_list=["--hub-resource-id", "--hub-id"],
            help="Azure resource ID of the IoT Hub to link.",
        )
        context.argument(
            "hub_mi_system_assigned",
            arg_group="Hub",
            options_list=["--hub-mi-system-assigned", "--hub-mi-sa"],
            arg_type=get_three_state_flag(),
            help="Use the linked IoT Hub's system-assigned identity as its inbound caller identity.",
        )
        context.argument(
            "hub_mi_user_assigned",
            arg_group="Hub",
            options_list=["--hub-mi-user-assigned", "--hub-mi-ua"],
            help="User-assigned identity resource ID attached to the linked IoT Hub.",
        )
        context.argument(
            "hub_availability",
            arg_group="Hub",
            options_list=["--hub-availability"],
            arg_type=get_enum_type(MessagingEndpointAvailability),
            help="Hub messaging endpoint availability.",
        )
        context.argument(
            "hub_allocation_weight",
            arg_group="Hub",
            options_list=["--hub-allocation-weight", "--hub-weight"],
            type=int,
            help="Hub messaging endpoint allocation weight.",
        )
        context.argument(
            "dps_endpoint_name",
            arg_group="DPS",
            options_list=["--dps-name", "--dn"],
            help="Logical name of the DPS provisioning endpoint entry on the namespace.",
        )
        context.argument(
            "dps_resource_id",
            arg_group="DPS",
            options_list=["--dps-resource-id", "--dps-id"],
            help="Azure resource ID of the Device Provisioning Service to link.",
        )
        context.argument(
            "dps_mi_system_assigned",
            arg_group="DPS",
            options_list=["--dps-mi-system-assigned", "--dps-mi-sa"],
            arg_type=get_three_state_flag(),
            help="Use the linked DPS resource's system-assigned identity as its inbound caller identity.",
        )
        context.argument(
            "dps_mi_user_assigned",
            arg_group="DPS",
            options_list=["--dps-mi-user-assigned", "--dps-mi-ua"],
            help="User-assigned identity resource ID attached to the linked DPS resource.",
        )

    # Group arguments
    with self.argument_context("iot adr ns group") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace.",
        )
        context.argument(
            "group_name",
            options_list=["--group-name", "--gn", "--name", "-n"],
            help="Name of the group.",
        )

    with self.argument_context("iot adr ns group create") as context:
        context.argument(
            "location",
            arg_type=get_location_type(self.cli_ctx),
        )
        context.argument("tags", arg_type=tags_type)
        context.argument(
            "group_type",
            options_list=["--group-type", "--gt"],
            arg_type=get_enum_type(GroupType),
            help="Type of the group. Only 'Device' is supported in the current preview API; "
                 "this is immutable after creation.",
        )
        context.argument(
            "query_string",
            options_list=["--query-string", "--qs"],
            help="Membership query string used to determine which devices belong to the group. "
                 "This is immutable after creation.",
        )
        context.argument(
            "display_name",
            options_list=["--display-name"],
            help="Human-readable display name for the group.",
        )
        context.argument(
            "description",
            options_list=["--description"],
            help="Human-readable description of the group.",
        )

    with self.argument_context("iot adr ns group update") as context:
        context.argument("tags", arg_type=tags_type)
        context.argument(
            "display_name",
            options_list=["--display-name"],
            help="Human-readable display name for the group.",
        )
        context.argument(
            "description",
            options_list=["--description"],
            help="Human-readable description of the group.",
        )

    with self.argument_context("iot adr ns group list-members") as context:
        context.argument(
            "page_size",
            options_list=["--page-size"],
            type=int,
            help="Maximum members per request. The service maximum is 1000.",
        )
        context.argument(
            "skip_token",
            options_list=["--skip-token"],
            help="Opaque token from which to start listing members.",
        )

    # Job arguments
    with self.argument_context("iot adr ns job") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace.",
        )
        context.argument(
            "job_name",
            options_list=["--job-name", "--jn", "--name", "-n"],
            help="Name of the job.",
        )

    with self.argument_context("iot adr ns job create") as context:
        context.argument(
            "location",
            arg_type=get_location_type(self.cli_ctx),
        )
        context.argument("tags", arg_type=tags_type)
        context.argument(
            "job_type",
            options_list=["--type"],
            arg_type=get_enum_type(JobType),
            help="Job type: SoftwareUpdate targets a group; OnboardingUpdate targets all "
                 "compatible onboarding devices.",
        )
        context.argument(
            "target_group_name",
            options_list=["--target-group-name", "--tg"],
            help="Name of the target group. The group must live in the same namespace and resource group "
                 "as the job; cross-namespace targets are not supported in this preview release.",
        )
        context.argument(
            "update_provider",
            arg_group="Update",
            options_list=["--update-id-provider", "--update-provider", "--up"],
            help="ADU updateId.provider (e.g. 'Contoso'). The ADU update identity is a {provider, name, version} triple.",
        )
        context.argument(
            "update_name",
            arg_group="Update",
            options_list=["--update-id-name", "--update-name", "--un"],
            help=(
                "ADU updateId.name (e.g. 'gateway-firmware'). "
                "This is the update identity's name, distinct from the job's --name."
            ),
        )
        context.argument(
            "update_version",
            arg_group="Update",
            options_list=["--update-id-version", "--update-version", "--uv"],
            help="ADU updateId.version (e.g. '1.2.3').",
        )
        context.argument(
            "description",
            options_list=["--description"],
            help="Human-readable job description.",
        )

    with self.argument_context("iot adr ns job update") as context:
        context.argument("tags", arg_type=tags_type)

    with self.argument_context("iot adr ns job schedule") as context:
        context.argument(
            "scheduled_time",
            options_list=["--scheduled-time", "--st"],
            help="Optional ISO 8601 UTC timestamp at which the job should be scheduled to run "
                 "(e.g. '2025-12-01T08:00:00Z'). Omit to schedule immediately.",
        )
        context.argument(
            "timeout",
            options_list=["--timeout"],
            help="Optional ISO 8601 duration after which the job execution times out "
                 "(e.g. 'PT1H' for one hour, 'P1D' for one day).",
        )

    # Job run arguments
    with self.argument_context("iot adr ns job run") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace.",
        )
        context.argument(
            "job_name",
            options_list=["--job-name", "--jn"],
            help="Name of the parent job that owns this run.",
        )
        context.argument(
            "run_name",
            options_list=["--run-name", "--rn", "--name", "-n"],
            help="Name of the job run.",
        )

    with self.argument_context("iot adr ns job run list") as context:
        context.argument(
            "job_name",
            options_list=["--job-name", "--jn", "--name", "-n"],
            help="Optional parent job name. Omit to list runs across the namespace.",
        )

    with self.argument_context("iot adr ns job run list") as context:
        context.argument(
            "status_filter",
            options_list=["--filter"],
            help="Status equality clauses joined by 'or', for example: "
                 "status eq 'Active' or status eq 'Scheduled'.",
        )

    with self.argument_context("iot adr ns job run results") as context:
        context.argument(
            "status_filter",
            options_list=["--filter"],
            help="One result status equality clause, for example: status eq 'Failed'.",
        )

    with self.argument_context("iot adr ns report") as context:
        context.argument(
            "namespace_name",
            options_list=["--namespace", "--ns"],
            help="Name of the Device Registry namespace.",
        )
        context.argument(
            "report_type",
            options_list=["--report-type", "--type"],
            arg_type=get_enum_type(ReportType),
            help="Type of update compliance report.",
        )
        context.argument(
            "group_name",
            options_list=["--group-name", "--gn"],
            help="Group target. Required for group report types.",
        )
