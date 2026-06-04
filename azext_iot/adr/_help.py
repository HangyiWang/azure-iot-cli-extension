# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Help documentation for Azure Device Registry (ADR) namespace commands.
"""

from knack.help_files import helps


def load_adr_help():
    helps[
        "iot adr"
    ] = """
  type: group
  short-summary: Manage Azure Device Registry (ADR) resources.
  """

    helps[
        "iot adr ns"
    ] = """
  type: group
  short-summary: Manage Device Registry namespaces.
  """

    helps[
        "iot adr ns create"
    ] = """
  type: command
  short-summary: Create a Device Registry namespace.
  long-summary: |
    By default, a namespace is created with a system-assigned managed identity.
    To create a credential and credential policy, use `--enable-certificate-management` or provide any policy parameters.
    The policy resource name can be customized with the --policy-name argument, but the 'default' credential name cannot be changed.
  examples:
    - name: Create a basic Device Registry namespace
      text: az iot adr ns create -n myNamespace -g myResourceGroup
    - name: Create a Device Registry namespace with credential and default policy
      text: az iot adr ns create -n myNamespace -g myResourceGroup --enable-certificate-management
    - name: Create a Device Registry namespace with custom credential policy
      text: az iot adr ns create -n myNamespace -g myResourceGroup --policy-name myPolicy --cert-validity-days 30
    - name: Create a Device Registry namespace with system-assigned outbound identity
      text: az iot adr ns create -n myNamespace -g myResourceGroup --outbound-mi-system-assigned
  """

    helps[
        "iot adr ns show"
    ] = """
  type: command
  short-summary: Show details of a Device Registry namespace.
  examples:
    - name: Show namespace details
      text: az iot adr ns show -n myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns list"
    ] = """
  type: command
  short-summary: List Device Registry namespaces.
  examples:
    - name: List all namespaces in a resource group
      text: az iot adr ns list -g myResourceGroup
    - name: List all namespaces in the subscription
      text: az iot adr ns list
  """

    helps[
        "iot adr ns delete"
    ] = """
  type: command
  short-summary: Delete a Device Registry namespace.
  examples:
    - name: Delete a namespace
      text: az iot adr ns delete -n myNamespace -g myResourceGroup
    - name: Delete a namespace with no confirmation prompt
      text: az iot adr ns delete -n myNamespace -g myResourceGroup --yes
  """

    helps[
        "iot adr ns update"
    ] = """
  type: command
  short-summary: Update a Device Registry namespace.
  examples:
    - name: Update namespace tags
      text: az iot adr ns update -n myNamespace -g myResourceGroup --tags key=value
  """

    helps[
        "iot adr ns credential"
    ] = """
  type: group
  short-summary: Manage Device Registry namespace credentials.
  """

    helps[
        "iot adr ns credential create"
    ] = """
  type: command
  short-summary: Create credentials for a Device Registry namespace.
  examples:
    - name: Create default credentials for a namespace
      text: az iot adr ns credential create --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns credential show"
    ] = """
  type: command
  short-summary: Show credentials for a Device Registry namespace.
  examples:
    - name: Show namespace credentials
      text: az iot adr ns credential show --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns credential delete"
    ] = """
  type: command
  short-summary: Delete a credential for a Device Registry namespace.
  examples:
    - name: Delete a namespace credential
      text: az iot adr ns credential delete --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns credential sync"
    ] = """
  type: command
  short-summary: Synchronize Device Registry credentials to linked Iot Hubs
  long-summary: This will create or update an ADR managed certificate in IoT Hubs linked to this Device Registry Namespace.
  examples:
    - name: Synchronize a namespace credential certificate to linked IoT Hubs
      text: az iot adr ns credential sync --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns policy"
    ] = """
    type: group
    short-summary: Manage Device Registry namespace policies.
  """

    helps[
        "iot adr ns policy create"
    ] = """
  type: command
  short-summary: Create a policy for a Device Registry namespace.
  long-summary: |
    By default, policies use a service-managed CA.
    To use your own CA (Bring Your Own Root), use --enable-byor and then activate the policy with the signed CSR using activate-byor.
  examples:
    - name: Create a basic policy with a default subject, certificate type (ECC), and validity period.
      text: az iot adr ns policy create -n myPolicy --ns myNamespace -g myResourceGroup
    - name: Create a policy with custom validity period
      text: az iot adr ns policy create -n myPolicy --ns myNamespace -g myResourceGroup --cert-validity-days 30
    - name: Create a BYOR (Bring Your Own Root) policy
      text: |
        az iot adr ns policy create -n myPolicy --ns myNamespace -g myResourceGroup --enable-byor
        # After creation, retrieve the CSR from 'policy show' and sign it with your CA,
        # then activate with 'az iot adr ns policy activate-byor'
  """

    helps[
        "iot adr ns policy show"
    ] = """
  type: command
  short-summary: Show a policy for a Device Registry namespace.
  long-summary: |
    For BYOR (Bring Your Own Root) policies, the output includes the certificate signing request (CSR) that needs to be signed by your Certificate Authority.
  examples:
    - name: Show policy details
      text: az iot adr ns policy show -n myPolicy --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns policy list"
    ] = """
  type: command
  short-summary: List policies for Device Registry namespaces.
  examples:
    - name: List policies for a namespace
      text: az iot adr ns policy list --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns policy delete"
    ] = """
  type: command
  short-summary: Delete a policy for a Device Registry namespace.
  examples:
    - name: Delete a policy
      text: az iot adr ns policy delete -n myPolicy --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns policy update"
    ] = """
  type: command
  short-summary: Update a policy for a Device Registry namespace.
  examples:
    - name: Update certificate validity period
      text: az iot adr ns policy update -n myPolicy --cert-validity-days 10 --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns policy revoke-issuer"
    ] = """
  type: command
  short-summary: Revoke the CA certificate for a Device Registry namespace policy.
  long-summary: |
    This command revokes the current CA (issuer) certificate for the policy, triggering the service to generate a new CA certificate. All device credentials issued by the old CA will need to be re-issued. Use this when the CA certificate is compromised or needs rotation.
  examples:
    - name: Revoke the issuer certificate for a policy
      text: az iot adr ns policy revoke-issuer -n myPolicy --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns policy activate-byor"
    ] = """
  type: command
  short-summary: Activate or renew a Bring Your Own Root (BYOR) policy with a signed certificate chain.
  long-summary: |
    This command activates a BYOR policy by uploading the signed certificate chain. Use this after creating a policy with --enable-byor and signing the CSR (from 'policy show') with your CA.

    The certificate chain file must be in PEM format and contain:
    1. The signed certificate (matching the CSR generated by the service)
    2. Any intermediate CA certificates
    3. Optionally, the root CA certificate

    Certificates must be ordered from leaf to root.

    This command is also used for certificate renewal when the BYOR status shows 'ActiveButPendingRenewal'.
  examples:
    - name: Activate a BYOR policy with a signed certificate chain
      text: az iot adr ns policy activate-byor -n myPolicy --ns myNamespace -g myResourceGroup --certificate-chain-file ./signed-chain.pem
  """

    helps[
        "iot adr ns device"
    ] = """
    type: group
    short-summary: Manage Device Registry namespace devices.
  """

    helps[
        "iot adr ns device show"
    ] = """
  type: command
  short-summary: Show a device in a Device Registry namespace.
  examples:
    - name: Show device details
      text: az iot adr ns device show -n myDevice --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns device create"
    ] = """
  type: command
  short-summary: Create a device in a Device Registry namespace.
  examples:
    - name: Create a device with minimal arguments (location inferred from resource group)
      text: az iot adr ns device create -n myDevice --ns myNamespace -g myResourceGroup
    - name: Create a device with manufacturer, model, and OS details
      text: |
        az iot adr ns device create -n myDevice --ns myNamespace -g myResourceGroup \\
          --manufacturer Contoso --model X100 --os Linux --os-version 5.15
    - name: Create a device bound to a credential policy
      text: |
        az iot adr ns device create -n myDevice --ns myNamespace -g myResourceGroup \\
          --policy-resource-id /subscriptions/.../policies/default
  """

    helps[
        "iot adr ns device list"
    ] = """
  type: command
  short-summary: List devices in a Device Registry namespace.
  examples:
    - name: List all devices in a namespace
      text: az iot adr ns device list --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns device update"
    ] = """
  type: command
  short-summary: Update a device in a Device Registry namespace.
  examples:
    - name: Disable a device
      text: az iot adr ns device update -n myDevice --ns myNamespace -g myResourceGroup --enabled false
    - name: Update device OS version
      text: az iot adr ns device update -n myDevice --ns myNamespace -g myResourceGroup --os-version "2.0.1"
  """

    helps[
        "iot adr ns device delete"
    ] = """
  type: command
  short-summary: Delete a device from a Device Registry namespace.
  examples:
    - name: Delete a device
      text: az iot adr ns device delete -n myDevice --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns device revoke"
    ] = """
  type: command
  short-summary: Revoke credentials for a device in a Device Registry namespace.
  long-summary: |
    This command revokes all active credentials for the specified device. The device will need to re-authenticate and obtain new credentials.

    Use --disable to also prevent the device from obtaining new credentials.
  examples:
    - name: Revoke device credentials
      text: az iot adr ns device revoke -n myDevice --ns myNamespace -g myResourceGroup
    - name: Revoke credentials and disable the device
      text: az iot adr ns device revoke -n myDevice --ns myNamespace -g myResourceGroup --disable
  """

    helps[
        "iot adr ns wait"
    ] = """
  type: command
  short-summary: Wait for a Device Registry namespace to reach a desired state.
  examples:
    - name: Wait until a namespace is created.
      text: az iot adr ns wait -n myNamespace -g myResourceGroup --created
  """

    helps[
        "iot adr ns link"
    ] = """
  type: group
  short-summary: Manage links between a Device Registry namespace and downstream resources.
  long-summary: |
    Links live on the namespace, not on the linked IoT Hub or DPS resources. All link operations
    mutate the namespace via PATCH and require the namespace to already exist.
  """

    helps[
        "iot adr ns link hub"
    ] = """
  type: group
  short-summary: Manage IoT Hub links (messaging endpoints) on a Device Registry namespace.
  long-summary: |
    A namespace must have at least one linked DPS before a Hub can be linked (DPS-first ordering).
    Links live on the namespace, not on the IoT Hub resource.
  """

    helps[
        "iot adr ns link hub add"
    ] = """
  type: command
  short-summary: Link an IoT Hub to a Device Registry namespace.
  long-summary: |
    Adds a Hub messaging endpoint entry under the namespace's properties.messaging.endpoints.
    Requires the namespace to already have at least one linked DPS (DPS-first ordering).
    Exactly one of --mi-system-assigned or --mi-user-assigned must be provided to set the
    inbound caller identity that the Hub will use to call back into the namespace.
  examples:
    - name: Link a Hub using the namespace's system-assigned identity for inbound calls
      text: |
        az iot adr ns link hub add -n primary --ns myNamespace -g myResourceGroup \\
          --hub-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Devices/IotHubs/<hub> \\
          --mi-system-assigned
    - name: Link a Hub with a user-assigned identity and custom availability/weight
      text: |
        az iot adr ns link hub add -n secondary --ns myNamespace -g myResourceGroup \\
          --hub-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Devices/IotHubs/<hub> \\
          --mi-user-assigned /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ManagedIdentity/userAssignedIdentities/<id> \\
          --availability Available --allocation-weight 1
  """

    helps[
        "iot adr ns link hub update"
    ] = """
  type: command
  short-summary: Update an existing IoT Hub messaging endpoint on a Device Registry namespace.
  long-summary: |
    Only the inbound caller identity and provisioning fields can be updated. The linked Hub
    resource cannot be changed; to point the endpoint at a different Hub, remove and re-add it.
  examples:
    - name: Switch a Hub link to a system-assigned identity
      text: az iot adr ns link hub update -n primary --ns myNamespace -g myResourceGroup --mi-system-assigned
    - name: Disable an existing Hub endpoint
      text: az iot adr ns link hub update -n primary --ns myNamespace -g myResourceGroup --availability Disabled
  """

    helps[
        "iot adr ns link hub remove"
    ] = """
  type: command
  short-summary: Remove an IoT Hub messaging endpoint from a Device Registry namespace.
  long-summary: |
    Removes the named messaging endpoint from the namespace by issuing a PATCH that sets the
    entry to null. The Hub resource itself is not deleted; only its link to the namespace.
  examples:
    - name: Remove a Hub link
      text: az iot adr ns link hub remove -n primary --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns link hub show"
    ] = """
  type: command
  short-summary: Show a single IoT Hub messaging endpoint on a Device Registry namespace.
  examples:
    - name: Show a Hub link by endpoint name
      text: az iot adr ns link hub show -n primary --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns link hub list"
    ] = """
  type: command
  short-summary: List IoT Hub messaging endpoints on a Device Registry namespace.
  examples:
    - name: List all Hub links on a namespace
      text: az iot adr ns link hub list --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns link dps"
    ] = """
  type: group
  short-summary: Manage DPS links (provisioning endpoints) on a Device Registry namespace.
  long-summary: |
    Only one DPS may be linked per namespace today. Links live on the namespace, not on the
    DPS resource; there is no per-DPS unlink API.
  """

    helps[
        "iot adr ns link dps add"
    ] = """
  type: command
  short-summary: Link a Device Provisioning Service (DPS) to a Device Registry namespace.
  long-summary: |
    Adds a DPS provisioning endpoint entry under the namespace's properties.provisioning.endpoints.
    Rejected if the namespace already has a linked DPS (one DPS per namespace).
    Exactly one of --mi-system-assigned or --mi-user-assigned must be provided.
  examples:
    - name: Link a DPS using the namespace's system-assigned identity
      text: |
        az iot adr ns link dps add -n primary --ns myNamespace -g myResourceGroup \\
          --dps-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Devices/provisioningServices/<dps> \\
          --mi-system-assigned
    - name: Link a DPS with a user-assigned identity
      text: |
        az iot adr ns link dps add -n primary --ns myNamespace -g myResourceGroup \\
          --dps-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Devices/provisioningServices/<dps> \\
          --mi-user-assigned /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ManagedIdentity/userAssignedIdentities/<id>
  """

    helps[
        "iot adr ns link dps update"
    ] = """
  type: command
  short-summary: Update an existing DPS provisioning endpoint on a Device Registry namespace.
  long-summary: |
    Only the inbound caller identity may be updated. The linked DPS resource cannot be changed;
    to point the endpoint at a different DPS, remove and re-add it.
  examples:
    - name: Rotate to a system-assigned identity on an existing DPS link
      text: az iot adr ns link dps update -n primary --ns myNamespace -g myResourceGroup --mi-system-assigned
  """

    helps[
        "iot adr ns link dps remove"
    ] = """
  type: command
  short-summary: Remove a DPS provisioning endpoint from a Device Registry namespace.
  long-summary: |
    Removes the named provisioning endpoint from the namespace by issuing a PATCH that sets the
    entry to null. The DPS resource itself is not deleted; only its link to the namespace.
  examples:
    - name: Remove a DPS link
      text: az iot adr ns link dps remove -n primary --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns link dps show"
    ] = """
  type: command
  short-summary: Show a single DPS provisioning endpoint on a Device Registry namespace.
  long-summary: |
    Projects the named endpoint and, when the linked DPS is accessible, includes a
    read-only 'brownfieldHubs' list (the DPS resource's existing properties.iotHubs[]).
    The brownfield list is informational so you can decide which Hubs to subsequently link
    to the namespace.
  examples:
    - name: Show a DPS link by endpoint name (with brownfield Hubs when accessible)
      text: az iot adr ns link dps show -n primary --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns link dps list"
    ] = """
  type: command
  short-summary: List DPS provisioning endpoints on a Device Registry namespace.
  examples:
    - name: List all DPS links on a namespace
      text: az iot adr ns link dps list --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns link add"
    ] = """
  type: command
  short-summary: Link a Hub and a DPS to a Device Registry namespace in a single operation.
  long-summary: |
    Composes a single namespace PATCH that adds both a DPS provisioning endpoint and an IoT Hub
    messaging endpoint. The DPS entry is serialized first to satisfy DPS-first ordering.
    Equivalent to running 'link dps add' followed by 'link hub add' but as one round-trip.
    Rejected if the namespace already has a linked DPS.
  examples:
    - name: Link both a Hub and a DPS using system-assigned identity for both inbound callers
      text: |
        az iot adr ns link add --ns myNamespace -g myResourceGroup \\
          --hub-name primary-hub --hub-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Devices/IotHubs/<hub> --hub-mi-system-assigned \\
          --dps-name primary-dps --dps-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Devices/provisioningServices/<dps> --dps-mi-system-assigned
    - name: Link both with custom Hub availability and weight
      text: |
        az iot adr ns link add --ns myNamespace -g myResourceGroup \\
          --hub-name primary-hub --hub-id <hub-id> --hub-mi-system-assigned \\
          --hub-availability Available --hub-allocation-weight 1 \\
          --dps-name primary-dps --dps-id <dps-id> --dps-mi-system-assigned
  """
