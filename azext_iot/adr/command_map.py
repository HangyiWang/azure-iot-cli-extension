# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.commands import CliCommandType

from azext_iot._factory import adr_service_factory

adr_namespace_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_namespace#{}",
    client_factory=adr_service_factory,
)

adr_credential_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_credential#{}",
    client_factory=adr_service_factory,
)

adr_policy_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_policy#{}",
    client_factory=adr_service_factory,
)

adr_device_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_device#{}",
    client_factory=adr_service_factory,
)

adr_group_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_group#{}",
    client_factory=adr_service_factory,
)

adr_job_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_job#{}",
    client_factory=adr_service_factory,
)

adr_link_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_link#{}",
    client_factory=adr_service_factory,
)


def load_adr_commands(self, _):
    # Namespace commands
    with self.command_group("iot adr ns", command_type=adr_namespace_ops) as cmd_group:
        cmd_group.command("create", "adr_namespace_create")
        cmd_group.show_command("show", "adr_namespace_show")
        cmd_group.command("list", "adr_namespace_list")
        cmd_group.command("delete", "adr_namespace_delete", confirmation=True)
        cmd_group.command("update", "adr_namespace_update")

    # Credential commands
    with self.command_group("iot adr ns credential", command_type=adr_credential_ops) as cmd_group:
        cmd_group.command("create", "adr_credential_create")
        cmd_group.show_command("show", "adr_credential_show")
        cmd_group.command("delete", "adr_credential_delete", confirmation=True)
        cmd_group.command("sync", "adr_credential_synchronize")

    # Policy commands
    with self.command_group("iot adr ns policy", command_type=adr_policy_ops) as cmd_group:
        cmd_group.command("create", "adr_policy_create")
        cmd_group.show_command("show", "adr_policy_show")
        cmd_group.command("list", "adr_policy_list")
        cmd_group.command("delete", "adr_policy_delete", confirmation=True)
        cmd_group.command("update", "adr_policy_update")
        cmd_group.command("revoke-issuer", "adr_policy_revoke_issuer", confirmation=True)
        cmd_group.command("activate-byor", "adr_policy_activate_byor")

    # Device commands
    with self.command_group("iot adr ns device", command_type=adr_device_ops) as cmd_group:
        cmd_group.show_command("show", "adr_device_show")
        cmd_group.command("list", "adr_device_list")
        cmd_group.command("update", "adr_device_update")
        cmd_group.command("revoke", "adr_device_revoke", confirmation=True)

    # Group commands
    with self.command_group("iot adr ns group", command_type=adr_group_ops) as cmd_group:
        cmd_group.command("create", "adr_group_create")
        cmd_group.show_command("show", "adr_group_show")
        cmd_group.command("list", "adr_group_list")
        cmd_group.command("delete", "adr_group_delete", confirmation=True)

    # Job commands
    with self.command_group("iot adr ns job", command_type=adr_job_ops) as cmd_group:
        cmd_group.command("create", "adr_job_create")
        cmd_group.show_command("show", "adr_job_show")
        cmd_group.command("list", "adr_job_list")
        cmd_group.command("delete", "adr_job_delete", confirmation=True)

    # Link commands (IoT Hub)
    with self.command_group("iot adr ns link hub", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_hub_add")
        cmd_group.show_command("show", "adr_link_hub_show")
        cmd_group.command("list", "adr_link_hub_list")
        cmd_group.command("remove", "adr_link_hub_remove", confirmation=True)

    # Link commands (DPS)
    with self.command_group("iot adr ns link dps", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_dps_add")
        cmd_group.show_command("show", "adr_link_dps_show")
        cmd_group.command("list", "adr_link_dps_list")
        cmd_group.command("remove", "adr_link_dps_remove", confirmation=True)
