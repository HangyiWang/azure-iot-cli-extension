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
    MessagingEndpointAvailability,
    PolicyCertificateKeyType,
)


def load_adr_management_arguments(self, _):
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
        # Enable certificate management and policy creation
        context.argument(
            "enable_certificate_management",
            arg_group="Credential",
            options_list=["--enable-certificate-management", "--ecm"],
            arg_type=get_three_state_flag(),
            help="Create a credential and credential policy for this Device Registry namespace. "
                 "This is also enabled when any custom policy parameters are provided.",
        )
        context.argument(
            "policy_name",
            arg_group="Policy",
            options_list=["--policy-name", "--pn"],
            help="Customize the name of the namespace credential policy",
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
        # TODO - CMS Preview - (-n for standard naming convention, --pn to match adr ns create)
        context.argument(
            "policy_name", options_list=["--policy-name", "--pn", "--name", "-n"], help="Name of the policy."
        )

    # Policy certificate arguments for create commands only (key type and subject cannot be changed after creation)
    for cmd in ["iot adr ns policy create", "iot adr ns create"]:
        with self.argument_context(cmd) as context:
            context.argument(
                "certificate_key_type",
                options_list=["--cert-key-type"],
                arg_type=get_enum_type(PolicyCertificateKeyType),
                arg_group="Policy Certificate",
                help="Policy certificate authority key type.",
            )
            context.argument(
                "certificate_subject",
                options_list=["--cert-subject"],
                help="Policy certificate subject.",
                arg_group="Policy Certificate",
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
            "policy_resource_id",
            options_list=["--policy-resource-id"],
            help="Resource ID of the credential policy to associate with the device.",
        )

    # Device revoke arguments
    with self.argument_context("iot adr ns device revoke") as context:
        context.argument(
            "disable",
            options_list=["--disable"],
            action="store_true",
            help="Disable the device after revoking credentials. "
                 "Prevents new credentials from being issued.",
        )

    # Device create arguments
    with self.argument_context("iot adr ns device create") as context:
        context.argument(
            "location",
            arg_type=get_location_type(self.cli_ctx),
            validator=get_default_location_from_resource_group,
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
                help="User-assigned managed identity resource ID for the outbound identity. "
                     "NOTE: Currently unsupported; the underlying API surface is still being finalized.",
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
                help="Use the namespace's system-assigned managed identity as the inbound caller "
                     "identity on this messaging endpoint.",
            )
            context.argument(
                "mi_user_assigned",
                arg_group="Inbound Caller Identity",
                options_list=["--mi-user-assigned", "--mi-ua"],
                help="Resource ID of the user-assigned managed identity to use as the inbound caller "
                     "identity on this messaging endpoint.",
            )
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

    with self.argument_context("iot adr ns link hub add") as context:
        context.argument(
            "hub_resource_id",
            options_list=["--hub-resource-id", "--hub-id"],
            help="Azure resource ID of the IoT Hub to link to this namespace.",
        )

    # Link DPS arguments (P3)
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
                help="Use the namespace's system-assigned managed identity as the inbound caller "
                     "identity on this DPS endpoint.",
            )
            context.argument(
                "mi_user_assigned",
                arg_group="Inbound Caller Identity",
                options_list=["--mi-user-assigned", "--mi-ua"],
                help="Resource ID of the user-assigned managed identity to use as the inbound caller "
                     "identity on this DPS endpoint.",
            )

    with self.argument_context("iot adr ns link dps add") as context:
        context.argument(
            "dps_resource_id",
            options_list=["--dps-resource-id", "--dps-id"],
            help="Azure resource ID of the Device Provisioning Service to link to this namespace.",
        )

    # Bundled link add (P4)
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
            help="Use the namespace's system-assigned managed identity as the Hub inbound caller identity.",
        )
        context.argument(
            "hub_mi_user_assigned",
            arg_group="Hub",
            options_list=["--hub-mi-user-assigned", "--hub-mi-ua"],
            help="User-assigned managed identity resource ID for the Hub inbound caller identity.",
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
            help="Use the namespace's system-assigned managed identity as the DPS inbound caller identity.",
        )
        context.argument(
            "dps_mi_user_assigned",
            arg_group="DPS",
            options_list=["--dps-mi-user-assigned", "--dps-mi-ua"],
            help="User-assigned managed identity resource ID for the DPS inbound caller identity.",
        )
