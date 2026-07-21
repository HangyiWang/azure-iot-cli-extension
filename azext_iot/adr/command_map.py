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

adr_ca_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_certificate_authority#{}",
    client_factory=adr_service_factory,
)

adr_ca_policy_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_certificate_policy#{}",
    client_factory=adr_service_factory,
)

adr_device_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_device#{}",
    client_factory=adr_service_factory,
)

adr_link_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_link#{}",
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

adr_job_run_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_job_run#{}",
    client_factory=adr_service_factory,
)

adr_report_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_report#{}",
    client_factory=adr_service_factory,
)


def load_adr_commands(self, _):
    # Namespace commands
    with self.command_group("iot adr ns", command_type=adr_namespace_ops) as cmd_group:
        cmd_group.command("create", "adr_namespace_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_namespace_show")
        cmd_group.command("list", "adr_namespace_list")
        cmd_group.command("delete", "adr_namespace_delete", confirmation=True, supports_no_wait=True)
        cmd_group.command("update", "adr_namespace_update", supports_no_wait=True)
        cmd_group.command("migrate", "adr_namespace_migrate", supports_no_wait=True)
        cmd_group.wait_command("wait", "adr_namespace_show")

    # Credential commands
    # Deprecated: superseded by `iot adr ns ca`. Not hidden so existing automation keeps
    # working and users are guided to the replacement during the transition.
    with self.command_group(
        "iot adr ns credential",
        command_type=adr_credential_ops,
        deprecate_info=self.deprecate(redirect="iot adr ns ca"),
    ) as cmd_group:
        cmd_group.command("create", "adr_credential_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_credential_show")
        cmd_group.command("delete", "adr_credential_delete", confirmation=True, supports_no_wait=True)
        cmd_group.command("sync", "adr_credential_synchronize", supports_no_wait=True)

    # Policy commands
    # Deprecated: superseded by `iot adr ns ca` (and `iot adr ns ca policy`).
    with self.command_group(
        "iot adr ns policy",
        command_type=adr_policy_ops,
        deprecate_info=self.deprecate(redirect="iot adr ns ca"),
    ) as cmd_group:
        cmd_group.command("create", "adr_policy_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_policy_show")
        cmd_group.command("list", "adr_policy_list")
        cmd_group.command("delete", "adr_policy_delete", confirmation=True, supports_no_wait=True)
        cmd_group.command("update", "adr_policy_update", supports_no_wait=True)
        cmd_group.command(
            "revoke-issuer", "adr_policy_revoke_issuer", confirmation=True, supports_no_wait=True
        )
        cmd_group.command("activate-byor", "adr_policy_activate_byor", supports_no_wait=True)

    # Certificate Authority commands
    with self.command_group("iot adr ns ca", command_type=adr_ca_ops) as cmd_group:
        cmd_group.command("create", "adr_ca_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_ca_show")
        cmd_group.command("list", "adr_ca_list")
        cmd_group.command("update", "adr_ca_update", supports_no_wait=True)
        cmd_group.command("delete", "adr_ca_delete", confirmation=True, supports_no_wait=True)
        cmd_group.command("activate", "adr_ca_activate", supports_no_wait=True)
        cmd_group.command("revoke", "adr_ca_revoke", confirmation=True, supports_no_wait=True)

    # Certificate Policy commands (nested under a certificate authority)
    with self.command_group("iot adr ns ca policy", command_type=adr_ca_policy_ops) as cmd_group:
        cmd_group.command("create", "adr_ca_policy_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_ca_policy_show")
        cmd_group.command("list", "adr_ca_policy_list")
        cmd_group.command("update", "adr_ca_policy_update", supports_no_wait=True)
        cmd_group.command("delete", "adr_ca_policy_delete", confirmation=True, supports_no_wait=True)

    # Device commands
    with self.command_group("iot adr ns device", command_type=adr_device_ops) as cmd_group:
        cmd_group.command("create", "adr_device_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_device_show")
        cmd_group.command("list", "adr_device_list")
        cmd_group.command("update", "adr_device_update", supports_no_wait=True)
        cmd_group.command("delete", "adr_device_delete", confirmation=True, supports_no_wait=True)

    # Link commands (mutate namespace.properties.messaging.endpoints / provisioning.endpoints)
    with self.command_group("iot adr ns link", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_add", supports_no_wait=True)

    with self.command_group("iot adr ns link hub", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_hub_add", supports_no_wait=True)
        cmd_group.command("update", "adr_link_hub_update", supports_no_wait=True)
        cmd_group.show_command("show", "adr_link_hub_show")
        cmd_group.command("list", "adr_link_hub_list")

    with self.command_group("iot adr ns link dps", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_dps_add", supports_no_wait=True)
        cmd_group.command("update", "adr_link_dps_update", supports_no_wait=True)
        cmd_group.show_command("show", "adr_link_dps_show")
        cmd_group.command("list", "adr_link_dps_list")

    with self.command_group("iot adr ns link adu", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_adu_add", supports_no_wait=True)
        cmd_group.command("update", "adr_link_adu_update", supports_no_wait=True)
        cmd_group.show_command("show", "adr_link_adu_show")
        cmd_group.command("list", "adr_link_adu_list")

    # Group commands
    with self.command_group("iot adr ns group", command_type=adr_group_ops) as cmd_group:
        cmd_group.command("create", "adr_group_create", supports_no_wait=True)
        cmd_group.command("update", "adr_group_update", supports_no_wait=True)
        cmd_group.show_command("show", "adr_group_show")
        cmd_group.command("list", "adr_group_list")
        cmd_group.command("delete", "adr_group_delete", confirmation=True, supports_no_wait=True)
        cmd_group.command("refresh", "adr_group_refresh", supports_no_wait=True)
        cmd_group.command("list-members", "adr_group_list_members")
        cmd_group.command("count", "adr_group_count")
        cmd_group.wait_command("wait", "adr_group_show")

    # Job commands
    with self.command_group("iot adr ns job", command_type=adr_job_ops) as cmd_group:
        cmd_group.command("create", "adr_job_create", supports_no_wait=True)
        cmd_group.command("update", "adr_job_update")
        cmd_group.show_command("show", "adr_job_show")
        cmd_group.command("list", "adr_job_list")
        cmd_group.command("delete", "adr_job_delete", confirmation=True, supports_no_wait=True)
        cmd_group.command("schedule", "adr_job_schedule", supports_no_wait=True)
        cmd_group.wait_command("wait", "adr_job_show")

    # Job run commands (read-only)
    with self.command_group("iot adr ns job run", command_type=adr_job_run_ops) as cmd_group:
        cmd_group.show_command("show", "adr_job_run_show")
        cmd_group.command("list", "adr_job_run_list")
        cmd_group.command("results", "adr_job_run_results")
        cmd_group.command(
            "cancel", "adr_job_run_cancel", confirmation=True, supports_no_wait=True
        )

    with self.command_group("iot adr ns report", command_type=adr_report_ops) as cmd_group:
        cmd_group.command("generate", "adr_report_generate", supports_no_wait=True)
        cmd_group.command("latest", "adr_report_latest")
