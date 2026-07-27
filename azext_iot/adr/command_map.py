# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from azure.cli.core.commands import CliCommandType

from azext_iot._factory import adr_du_service_factory, adr_service_factory

adr_namespace_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_namespace#{}",
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

adr_registry_device_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_registry_device#{}",
    client_factory=adr_service_factory,
)

adr_asset_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_asset#{}",
    client_factory=adr_service_factory,
)

adr_discovered_device_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_discovered_device#{}",
    client_factory=adr_service_factory,
)

adr_discovered_asset_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_discovered_asset#{}",
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

adr_du_ops = CliCommandType(
    operations_tmpl="azext_iot.adr.commands_du#{}",
    client_factory=adr_du_service_factory,
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

    # Certificate Authority commands
    with self.command_group("iot adr ns ca", command_type=adr_ca_ops) as cmd_group:
        cmd_group.command("create", "adr_ca_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_ca_show")
        cmd_group.command("list", "adr_ca_list")
        cmd_group.command("update", "adr_ca_update", supports_no_wait=True)
        cmd_group.command("delete", "adr_ca_delete", confirmation=True, supports_no_wait=True)
        cmd_group.command("activate", "adr_ca_activate", supports_no_wait=True)
        cmd_group.command("revoke", "adr_ca_revoke", confirmation=True, supports_no_wait=True)
        cmd_group.wait_command("wait", "adr_ca_show")

    # Certificate Policy commands (nested under a certificate authority)
    with self.command_group("iot adr ns ca policy", command_type=adr_ca_policy_ops) as cmd_group:
        cmd_group.command("create", "adr_ca_policy_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_ca_policy_show")
        cmd_group.command("list", "adr_ca_policy_list")
        cmd_group.command("update", "adr_ca_policy_update", supports_no_wait=True)
        cmd_group.command("delete", "adr_ca_policy_delete", confirmation=True, supports_no_wait=True)
        cmd_group.wait_command("wait", "adr_ca_policy_show")

    # Device commands
    with self.command_group("iot adr ns device", command_type=adr_device_ops) as cmd_group:
        cmd_group.command("create", "adr_device_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_device_show")
        cmd_group.command("list", "adr_device_list")
        cmd_group.command("update", "adr_device_update", supports_no_wait=True)
        cmd_group.command("delete", "adr_device_delete", confirmation=True, supports_no_wait=True)
        cmd_group.wait_command("wait", "adr_device_show")

    # Registry Device commands
    with self.command_group(
        "iot adr ns registry-device", command_type=adr_registry_device_ops
    ) as cmd_group:
        cmd_group.command("create", "adr_registry_device_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_registry_device_show")
        cmd_group.command("list", "adr_registry_device_list")
        cmd_group.command("update", "adr_registry_device_update", supports_no_wait=True)
        cmd_group.command(
            "delete",
            "adr_registry_device_delete",
            confirmation=True,
            supports_no_wait=True,
        )
        cmd_group.wait_command("wait", "adr_registry_device_show")

    with self.command_group(
        "iot adr ns registry-device auth-profile",
        command_type=adr_registry_device_ops,
    ) as cmd_group:
        cmd_group.command("list", "adr_registry_device_auth_profile_list")
        cmd_group.show_command("show", "adr_registry_device_auth_profile_show")
        cmd_group.command("get-keys", "adr_registry_device_auth_profile_get_keys")
        cmd_group.command(
            "revoke-certificates",
            "adr_registry_device_auth_profile_revoke_certificates",
            confirmation=True,
            supports_no_wait=True,
        )

    with self.command_group(
        "iot adr ns registry-device attribute",
        command_type=adr_registry_device_ops,
    ) as cmd_group:
        cmd_group.command("list", "adr_registry_device_attribute_list")
        cmd_group.show_command("show", "adr_registry_device_attribute_show")

    with self.command_group(
        "iot adr ns registry-device capability",
        command_type=adr_registry_device_ops,
    ) as cmd_group:
        cmd_group.command("list", "adr_registry_device_capability_list")
        cmd_group.show_command("show", "adr_registry_device_capability_show")

    # Namespace Asset commands
    with self.command_group("iot adr ns asset", command_type=adr_asset_ops) as cmd_group:
        cmd_group.command("create", "adr_asset_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_asset_show")
        cmd_group.command("list", "adr_asset_list")
        cmd_group.command("update", "adr_asset_update", supports_no_wait=True)
        cmd_group.command("delete", "adr_asset_delete", confirmation=True, supports_no_wait=True)
        cmd_group.command("execute-action", "adr_asset_execute_action", supports_no_wait=True)
        cmd_group.wait_command("wait", "adr_asset_show")

    # Discovery resource commands
    with self.command_group(
        "iot adr ns discovered-device", command_type=adr_discovered_device_ops
    ) as cmd_group:
        cmd_group.command("create", "adr_discovered_device_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_discovered_device_show")
        cmd_group.command("list", "adr_discovered_device_list")
        cmd_group.command("update", "adr_discovered_device_update", supports_no_wait=True)
        cmd_group.command(
            "delete",
            "adr_discovered_device_delete",
            confirmation=True,
            supports_no_wait=True,
        )
        cmd_group.wait_command("wait", "adr_discovered_device_show")

    with self.command_group(
        "iot adr ns discovered-asset", command_type=adr_discovered_asset_ops
    ) as cmd_group:
        cmd_group.command("create", "adr_discovered_asset_create", supports_no_wait=True)
        cmd_group.show_command("show", "adr_discovered_asset_show")
        cmd_group.command("list", "adr_discovered_asset_list")
        cmd_group.command("update", "adr_discovered_asset_update", supports_no_wait=True)
        cmd_group.command(
            "delete",
            "adr_discovered_asset_delete",
            confirmation=True,
            supports_no_wait=True,
        )
        cmd_group.wait_command("wait", "adr_discovered_asset_show")

    with self.command_group(
        "iot adr ns identity", command_type=adr_namespace_ops
    ) as cmd_group:
        cmd_group.show_command("show", "adr_namespace_identity_show")
        cmd_group.command("assign", "adr_namespace_identity_assign", supports_no_wait=True)
        cmd_group.command("remove", "adr_namespace_identity_remove", supports_no_wait=True)
        cmd_group.wait_command("wait", "adr_namespace_show")

    with self.command_group(
        "iot adr ns management-endpoint", command_type=adr_namespace_ops
    ) as cmd_group:
        cmd_group.command(
            "set", "adr_namespace_management_endpoint_set", supports_no_wait=True
        )
        cmd_group.show_command("show", "adr_namespace_management_endpoint_show")
        cmd_group.command("list", "adr_namespace_management_endpoint_list")
        cmd_group.wait_command("wait", "adr_namespace_show")

    # Link commands (mutate namespace.properties.messaging.endpoints / provisioning.endpoints)
    with self.command_group("iot adr ns link", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_add", supports_no_wait=True)
        cmd_group.wait_command(
            "wait", "adr_namespace_show", getter_type=adr_namespace_ops
        )

    with self.command_group("iot adr ns link hub", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_hub_add", supports_no_wait=True)
        cmd_group.command("update", "adr_link_hub_update", supports_no_wait=True)
        cmd_group.show_command("show", "adr_link_hub_show")
        cmd_group.command("list", "adr_link_hub_list")
        cmd_group.wait_command(
            "wait", "adr_namespace_show", getter_type=adr_namespace_ops
        )

    with self.command_group("iot adr ns link dps", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_dps_add", supports_no_wait=True)
        cmd_group.command("update", "adr_link_dps_update", supports_no_wait=True)
        cmd_group.show_command("show", "adr_link_dps_show")
        cmd_group.command("list", "adr_link_dps_list")
        cmd_group.wait_command(
            "wait", "adr_namespace_show", getter_type=adr_namespace_ops
        )

    with self.command_group("iot adr ns link du", command_type=adr_link_ops) as cmd_group:
        cmd_group.command("add", "adr_link_du_add", supports_no_wait=True)
        cmd_group.command("update", "adr_link_du_update", supports_no_wait=True)
        cmd_group.show_command("show", "adr_link_du_show")
        cmd_group.command("list", "adr_link_du_list")
        cmd_group.wait_command(
            "wait", "adr_namespace_show", getter_type=adr_namespace_ops
        )

    with self.command_group(
        "iot adr ns du instance", command_type=adr_du_ops
    ) as cmd_group:
        cmd_group.command("check-name", "adr_du_instance_check_name")
        cmd_group.command(
            "create", "adr_du_instance_create", supports_no_wait=True
        )
        cmd_group.show_command("show", "adr_du_instance_show")
        cmd_group.command("list", "adr_du_instance_list")
        cmd_group.command(
            "update", "adr_du_instance_update", supports_no_wait=True
        )
        cmd_group.command(
            "delete",
            "adr_du_instance_delete",
            confirmation=True,
            supports_no_wait=True,
        )
        cmd_group.wait_command("wait", "adr_du_instance_show")

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
        cmd_group.wait_command("wait", "adr_job_run_show")

    with self.command_group("iot adr ns report", command_type=adr_report_ops) as cmd_group:
        cmd_group.command("generate", "adr_report_generate", supports_no_wait=True)
        cmd_group.command("latest", "adr_report_latest")
