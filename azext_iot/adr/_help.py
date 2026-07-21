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
    To bootstrap a default credential and credential policy (deprecated), provide any policy parameters.
    The policy resource name can be customized with the --policy-name argument, but the 'default' credential name cannot be changed.
  examples:
    - name: Create a basic Device Registry namespace
      text: az iot adr ns create -n myNamespace -g myResourceGroup
    - name: Create a Device Registry namespace with a default credential policy (deprecated)
      text: az iot adr ns create -n myNamespace -g myResourceGroup --policy-name default
    - name: Create a Device Registry namespace with custom credential policy
      text: az iot adr ns create -n myNamespace -g myResourceGroup --policy-name myPolicy --cert-validity-days 30
    - name: Create a Device Registry namespace with system-assigned outbound identity
      text: az iot adr ns create -n myNamespace -g myResourceGroup --outbound-mi-system-assigned
    - name: Create a namespace with a user-assigned outbound identity
      text: |
        az iot adr ns create -n myNamespace -g myResourceGroup \\
          --outbound-mi-user-assigned /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ManagedIdentity/userAssignedIdentities/<id>
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
    - name: Switch outbound identity to system-assigned managed identity
      text: az iot adr ns update -n myNamespace -g myResourceGroup --outbound-mi-system-assigned
    - name: Switch outbound identity to a user-assigned managed identity
      text: |
        az iot adr ns update -n myNamespace -g myResourceGroup \\
          --outbound-mi-user-assigned /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ManagedIdentity/userAssignedIdentities/<id>
  """

    helps[
        "iot adr ns migrate"
    ] = """
  type: command
  short-summary: Migrate resources into a Device Registry namespace.
  examples:
    - name: Migrate resources into a namespace
      text: |
        az iot adr ns migrate -n myNamespace -g myResourceGroup \\
          --scope Resources --resource-ids /subscriptions/.../resources/resource1
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
        "iot adr ns ca"
    ] = """
  type: group
  short-summary: Manage certificate authorities for a Device Registry namespace.
  """

    helps[
        "iot adr ns ca create"
    ] = """
  type: command
  short-summary: Create a certificate authority for a Device Registry namespace.
  long-summary: |
    The certificate authority type determines the required associated properties:
    - Root: a service-managed self-signed root CA.
    - ICA with an Internal issuer: signed by another CA in the same namespace. Pass the issuing
      CA's UUID with --issuer-ca-uuid.
    - ICA with an External issuer: signed by an external PKI. After creation the service returns
      a CSR; sign it and complete activation with 'az iot adr ns ca activate'.
  examples:
    - name: Create a service-managed root certificate authority
      text: az iot adr ns ca create -n myRootCA --ns myNamespace -g myResourceGroup --type Root
    - name: Create an internally issued intermediate certificate authority
      text: |
        az iot adr ns ca create -n myInternalICA --ns myNamespace -g myResourceGroup \\
          --type ICA --issuer-type Internal --issuer-ca-uuid 11111111-1111-1111-1111-111111111111
    - name: Create an externally issued intermediate certificate authority
      text: |
        az iot adr ns ca create -n myExternalICA --ns myNamespace -g myResourceGroup \\
          --type ICA --issuer-type External
  """

    helps[
        "iot adr ns ca show"
    ] = """
  type: command
  short-summary: Show a certificate authority for a Device Registry namespace.
  examples:
    - name: Show a certificate authority
      text: az iot adr ns ca show -n myCA --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns ca list"
    ] = """
  type: command
  short-summary: List the certificate authorities for a Device Registry namespace.
  examples:
    - name: List certificate authorities
      text: az iot adr ns ca list --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns ca update"
    ] = """
  type: command
  short-summary: Update a certificate authority for a Device Registry namespace.
  examples:
    - name: Update certificate authority tags
      text: az iot adr ns ca update -n myCA --ns myNamespace -g myResourceGroup --tags env=prod
  """

    helps[
        "iot adr ns ca delete"
    ] = """
  type: command
  short-summary: Delete a certificate authority from a Device Registry namespace.
  examples:
    - name: Delete a certificate authority
      text: az iot adr ns ca delete -n myCA --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns ca activate"
    ] = """
  type: command
  short-summary: Activate an externally issued intermediate certificate authority.
  long-summary: |
    Use this after creating an ICA with --issuer-type External and signing the service-generated
    CSR with your external PKI. The certificate chain file must be in PEM
    format with certificates ordered from leaf to root.
  examples:
    - name: Activate an externally issued ICA
      text: az iot adr ns ca activate -n myExternalICA --ns myNamespace -g myResourceGroup --certificate-chain-file ./signed-chain.pem
  """

    helps[
        "iot adr ns ca revoke"
    ] = """
  type: command
  short-summary: Revoke an intermediate certificate authority issued by an internal CA.
  examples:
    - name: Revoke a certificate authority
      text: az iot adr ns ca revoke -n myCA --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns ca policy"
    ] = """
  type: group
  short-summary: Manage certificate policies for a certificate authority.
  long-summary: |
    A certificate policy carries the leaf certificate issuance settings for a certificate authority.
  """

    helps[
        "iot adr ns ca policy create"
    ] = """
  type: command
  short-summary: Create a certificate policy for a certificate authority.
  examples:
    - name: Create a certificate policy with a 10 day leaf certificate validity period
      text: az iot adr ns ca policy create -n myPolicy --ca-name myCA --ns myNamespace -g myResourceGroup --validity-days 10
  """

    helps[
        "iot adr ns ca policy show"
    ] = """
  type: command
  short-summary: Show a certificate policy for a certificate authority.
  examples:
    - name: Show a certificate policy
      text: az iot adr ns ca policy show -n myPolicy --ca-name myCA --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns ca policy list"
    ] = """
  type: command
  short-summary: List the certificate policies for a certificate authority.
  examples:
    - name: List certificate policies
      text: az iot adr ns ca policy list --ca-name myCA --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns ca policy update"
    ] = """
  type: command
  short-summary: Update a certificate policy for a certificate authority.
  examples:
    - name: Update certificate policy tags
      text: az iot adr ns ca policy update -n myPolicy --ca-name myCA --ns myNamespace -g myResourceGroup --tags env=prod
  """

    helps[
        "iot adr ns ca policy delete"
    ] = """
  type: command
  short-summary: Delete a certificate policy from a certificate authority.
  examples:
    - name: Delete a certificate policy
      text: az iot adr ns ca policy delete -n myPolicy --ca-name myCA --ns myNamespace -g myResourceGroup
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
    - name: Create a device with minimal arguments (location inherited from the namespace)
      text: az iot adr ns device create -n myDevice --ns myNamespace -g myResourceGroup
    - name: Create a device with manufacturer, model, and OS details
      text: |
        az iot adr ns device create -n myDevice --ns myNamespace -g myResourceGroup \\
          --manufacturer Contoso --model X100 --os Linux --os-version 5.15
    - name: Create an enabled device with external identity and attributes
      text: |
        az iot adr ns device create -n myDevice --ns myNamespace -g myResourceGroup \\
          --external-device-id device-42 --enabled true \\
          --attributes '{"environment":"production"}'
    - name: Create a device bound to a credential policy
      text: |
        az iot adr ns device create -n myDevice --ns myNamespace -g myResourceGroup \\
          --policy-resource-id /subscriptions/.../policies/default
    - name: Create a device with an assigned outbound endpoint
      text: |
        az iot adr ns device create -n myDevice --ns myNamespace -g myResourceGroup \\
          --endpoints '{"outbound":{"assigned":{"events":{"endpointType":"Microsoft.Devices","address":"https://example.eventgrid.azure.net/api/events"}}}}'
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
    --mi-system-assigned and --mi-user-assigned are optional. When supplied, exactly one may be
    used to set the inbound caller identity that the Hub will use to call back into the namespace.
    Prerequisite role assignments (otherwise linking fails with AdrMiNotAuthorized): the
    namespace's managed identity needs Contributor AND 'IoT Hub Data Contributor' on the Hub,
    and the Hub's own managed identity needs Contributor on the namespace. Creating these role
    assignments requires Owner or User Access Administrator on the scope.
  examples:
    - name: Link a Hub using the Hub's system-assigned identity for inbound calls
      text: |
        az iot adr ns link hub add -n primary --ns myNamespace -g myResourceGroup \\
          --hub-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Devices/IotHubs/<hub> \\
          --mi-system-assigned
    - name: Link a Hub without configuring an inbound caller identity
      text: |
        az iot adr ns link hub add -n primary --ns myNamespace -g myResourceGroup \\
          --hub-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Devices/IotHubs/<hub>
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
    Only the inbound caller identity can be updated. The linked Hub resource and provisioning
    settings cannot be changed in place.
  examples:
    - name: Switch a Hub link to a system-assigned identity
      text: az iot adr ns link hub update -n primary --ns myNamespace -g myResourceGroup --mi-system-assigned
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
    Prerequisite role assignments (otherwise linking fails with AdrMiNotAuthorized): the
    namespace's managed identity needs Contributor on the DPS, and the DPS's own managed identity
    needs Contributor on the namespace. Creating these role assignments requires Owner or User
    Access Administrator on the scope.
  examples:
    - name: Link a DPS using the DPS resource's system-assigned identity
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
    Only the inbound caller identity may be updated. The linked DPS resource cannot be changed
    in place.
  examples:
    - name: Rotate to a system-assigned identity on an existing DPS link
      text: az iot adr ns link dps update -n primary --ns myNamespace -g myResourceGroup --mi-system-assigned
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
        "iot adr ns link adu"
    ] = """
  type: group
  short-summary: Manage Azure Device Update (ADU) links (updating endpoints) on a Device Registry namespace.
  long-summary: |
    Links a 'Microsoft.DeviceUpdate/updateInstances' resource to the namespace as an
    updating endpoint under properties.updating.endpoints. Links live on the namespace, not on
    the ADU resource. Linking is asynchronous; read-only address fields (serviceAddress,
    deviceAddress, legacyDeviceAddress) are resolved once linking succeeds.
  """

    helps[
        "iot adr ns link adu add"
    ] = """
  type: command
  short-summary: Link an Azure Device Update instance to a Device Registry namespace.
  long-summary: |
    Adds an ADU updating endpoint entry under the namespace's properties.updating.endpoints.
    Exactly one of --mi-system-assigned or --mi-user-assigned must be provided to set the
    inbound caller identity that the update instance will use to call back into the namespace.
  examples:
    - name: Link an ADU instance using its system-assigned identity for inbound calls
      text: |
        az iot adr ns link adu add -n my-adu --ns myNamespace -g myResourceGroup \\
          --adu-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.DeviceUpdate/updateInstances/<instance> \\
          --mi-system-assigned
    - name: Link an ADU account with a user-assigned identity
      text: |
        az iot adr ns link adu add -n my-adu --ns myNamespace -g myResourceGroup \\
          --adu-id /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.DeviceUpdate/updateInstances/<instance> \\
          --mi-user-assigned /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.ManagedIdentity/userAssignedIdentities/<id>
  """

    helps[
        "iot adr ns link adu update"
    ] = """
  type: command
  short-summary: Update an existing ADU updating endpoint on a Device Registry namespace.
  long-summary: |
    Only the inbound caller identity may be updated. The linked update instance cannot be changed
    in place.
  examples:
    - name: Rotate to a system-assigned identity on an existing ADU link
      text: az iot adr ns link adu update -n my-adu --ns myNamespace -g myResourceGroup --mi-system-assigned
  """

    helps[
        "iot adr ns link adu show"
    ] = """
  type: command
  short-summary: Show a single ADU updating endpoint on a Device Registry namespace.
  examples:
    - name: Show an ADU link by endpoint name
      text: az iot adr ns link adu show -n my-adu --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns link adu list"
    ] = """
  type: command
  short-summary: List ADU updating endpoints on a Device Registry namespace.
  examples:
    - name: List all ADU links on a namespace
      text: az iot adr ns link adu list --ns myNamespace -g myResourceGroup
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
    - name: Link both resources without configuring a Hub inbound caller identity
      text: |
        az iot adr ns link add --ns myNamespace -g myResourceGroup \\
          --hub-name primary-hub --hub-id <hub-id> \\
          --dps-name primary-dps --dps-id <dps-id> --dps-mi-system-assigned
    - name: Link both with custom Hub availability and weight
      text: |
        az iot adr ns link add --ns myNamespace -g myResourceGroup \\
          --hub-name primary-hub --hub-id <hub-id> --hub-mi-system-assigned \\
          --hub-availability Available --hub-allocation-weight 1 \\
          --dps-name primary-dps --dps-id <dps-id> --dps-mi-system-assigned
  """

    helps[
        "iot adr ns group"
    ] = """
    type: group
    short-summary: Manage Device Registry namespace groups.
  """

    helps[
        "iot adr ns group create"
    ] = """
  type: command
  short-summary: Create a group in a Device Registry namespace.
  long-summary: |
    PUT is a long-running operation. The group's --group-type and --query-string
    are immutable after creation. Only 'Device' is supported as the group type
    in the current preview API.
  examples:
    - name: Create a device group with a membership query
      text: |
        az iot adr ns group create -n myGroup --ns myNamespace -g myResourceGroup \\
          --query-string "SELECT * FROM devices WHERE tags.env = 'prod'"
    - name: Create a device group with a display name and description
      text: |
        az iot adr ns group create -n myGroup --ns myNamespace -g myResourceGroup \\
          --query-string "SELECT * FROM devices WHERE tags.env = 'prod'" \\
          --display-name "Production devices" --description "All prod-tagged devices"
  """

    helps[
        "iot adr ns group update"
    ] = """
  type: command
  short-summary: Update a group in a Device Registry namespace.
  long-summary: |
    PATCH is a long-running operation. Only mutable fields are exposed:
    --display-name, --description, and --tags. The group's type and membership
    query cannot be changed after creation; recreate the group instead.
  examples:
    - name: Update a group's display name
      text: az iot adr ns group update -n myGroup --ns myNamespace -g myResourceGroup --display-name "New name"
    - name: Update a group's description and tags
      text: az iot adr ns group update -n myGroup --ns myNamespace -g myResourceGroup --description "Updated" --tags env=prod
  """

    helps[
        "iot adr ns group show"
    ] = """
  type: command
  short-summary: Show a group in a Device Registry namespace.
  examples:
    - name: Show group details
      text: az iot adr ns group show -n myGroup --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns group list"
    ] = """
  type: command
  short-summary: List groups in a Device Registry namespace.
  examples:
    - name: List all groups in a namespace
      text: az iot adr ns group list --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns group delete"
    ] = """
  type: command
  short-summary: Delete a group from a Device Registry namespace.
  examples:
    - name: Delete a group
      text: az iot adr ns group delete -n myGroup --ns myNamespace -g myResourceGroup
    - name: Delete a group without confirmation prompt
      text: az iot adr ns group delete -n myGroup --ns myNamespace -g myResourceGroup --yes
  """

    helps[
        "iot adr ns group refresh"
    ] = """
  type: command
  short-summary: Trigger an asynchronous refresh of a group's membership.
  long-summary: |
    Refreshing membership is a long-running operation. Use 'az iot adr ns group wait'
    to wait for the refresh to complete, or 'az iot adr ns group show' to poll
    the 'membershipState' field.
  examples:
    - name: Refresh group membership
      text: az iot adr ns group refresh -n myGroup --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns group list-members"
    ] = """
  type: command
  short-summary: List the current members of a group.
  long-summary: |
    Follows the service's skip-token pagination and returns member resource ID
    objects.
  examples:
    - name: List group members
      text: az iot adr ns group list-members -n myGroup --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns group count"
    ] = """
  type: command
  short-summary: Show the current member count of a group.
  examples:
    - name: Show member count
      text: az iot adr ns group count -n myGroup --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns group wait"
    ] = """
  type: command
  short-summary: Wait for a Device Registry group to reach a desired state.
  examples:
    - name: Wait until a group is created
      text: az iot adr ns group wait -n myGroup --ns myNamespace -g myResourceGroup --created
    - name: Wait until a group's membership refresh completes
      text: az iot adr ns group wait -n myGroup --ns myNamespace -g myResourceGroup --custom "properties.membershipState=='Ready'"
  """

    helps[
        "iot adr ns job"
    ] = """
    type: group
    short-summary: Manage Device Registry namespace jobs.
  """

    helps[
        "iot adr ns job create"
    ] = """
  type: command
  short-summary: Create a job in a Device Registry namespace.
  long-summary: |
    PUT is a long-running operation. SoftwareUpdate jobs require a target group.
    OnboardingUpdate jobs target all compatible onboarding devices and do not
    accept a target group. Job definition fields are immutable after creation.

    The target group is specified by --target-group-name and must live in the
    same namespace and resource group as the job (cross-namespace targets are
    not supported in this preview release). The ADU update identity
    (--update-id-provider, --update-id-name, --update-id-version) is passed
    opaquely to the backend; no ADU preflight is performed.
  examples:
    - name: Create a SoftwareUpdate job targeting a group
      text: |
        az iot adr ns job create -n myJob --ns myNamespace -g myResourceGroup \\
          --type SoftwareUpdate \\
          --target-group-name myGroup \\
          --update-id-provider Contoso --update-id-name gateway-firmware --update-id-version 1.2.3
    - name: Create an OnboardingUpdate job
      text: |
        az iot adr ns job create -n onboarding --ns myNamespace -g myResourceGroup \\
          --type OnboardingUpdate \\
          --update-id-provider Contoso --update-id-name gateway-firmware --update-id-version 1.2.3
  """

    helps[
        "iot adr ns job update"
    ] = """
  type: command
  short-summary: Update tags on a job in a Device Registry namespace.
  long-summary: |
    PATCH is synchronous and tags-only by design. The job's --type, target
    group, update identity, and scheduling fields are immutable after creation
    because mutating them would have unintended effects on already-scheduled
    runs. To change these, delete and recreate the job.
  examples:
    - name: Update job tags
      text: az iot adr ns job update -n myJob --ns myNamespace -g myResourceGroup --tags env=prod owner=platform
    - name: Clear all job tags
      text: az iot adr ns job update -n myJob --ns myNamespace -g myResourceGroup --tags ""
  """

    helps[
        "iot adr ns job show"
    ] = """
  type: command
  short-summary: Show a job in a Device Registry namespace.
  examples:
    - name: Show job details
      text: az iot adr ns job show -n myJob --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns job list"
    ] = """
  type: command
  short-summary: List jobs in a Device Registry namespace.
  examples:
    - name: List all jobs in a namespace
      text: az iot adr ns job list --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns job delete"
    ] = """
  type: command
  short-summary: Delete a job from a Device Registry namespace.
  long-summary: |
    DELETE is a long-running operation. If any in-flight runs (status
    'Scheduled', 'Queued', or 'Active') exist for this job, a warning is
    surfaced before deletion; the backend cancels affected runs with reason
    'CanceledByCustomer'.
  examples:
    - name: Delete a job
      text: az iot adr ns job delete -n myJob --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns job schedule"
    ] = """
  type: command
  short-summary: Schedule a job for execution.
  long-summary: |
    Scheduling is a long-running operation. Both --scheduled-time and
    --timeout are optional; omit --scheduled-time to schedule immediately.
    --timeout is validated client-side as an ISO 8601 duration
    (e.g. 'PT1H', 'P1D', 'PT30M').
  examples:
    - name: Schedule a job to run immediately
      text: az iot adr ns job schedule -n myJob --ns myNamespace -g myResourceGroup
    - name: Schedule a job for a specific UTC time with a 2-hour timeout
      text: |
        az iot adr ns job schedule -n myJob --ns myNamespace -g myResourceGroup \\
          --scheduled-time 2025-12-01T08:00:00Z --timeout PT2H
  """

    helps[
        "iot adr ns job wait"
    ] = """
  type: command
  short-summary: Wait for a Device Registry job to reach a desired state.
  examples:
    - name: Wait until a job is created
      text: az iot adr ns job wait -n myJob --ns myNamespace -g myResourceGroup --created
    - name: Wait until a job reaches a terminal provisioning state
      text: az iot adr ns job wait -n myJob --ns myNamespace -g myResourceGroup --custom "properties.provisioningState=='Succeeded'"
  """

    helps[
        "iot adr ns job run"
    ] = """
    type: group
    short-summary: Manage runs of Device Registry namespace jobs.
    long-summary: |
      Job runs are spawned when a job is scheduled. Commands can inspect,
      filter, and cancel runs.
  """

    helps[
        "iot adr ns job run show"
    ] = """
  type: command
  short-summary: Show a single run of a Device Registry job.
  examples:
    - name: Show a job run
      text: az iot adr ns job run show -n myRun --job-name myJob --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns job run list"
    ] = """
  type: command
  short-summary: List job runs by parent job or across a namespace.
  examples:
    - name: List all runs for a job
      text: az iot adr ns job run list --job-name myJob --ns myNamespace -g myResourceGroup
    - name: List active runs across the namespace
      text: az iot adr ns job run list --ns myNamespace -g myResourceGroup --filter "status eq 'Active'"
  """

    helps[
        "iot adr ns job run results"
    ] = """
  type: command
  short-summary: Browse per-device results of a job run.
  long-summary: |
    Returns a flat list of per-device results aggregated across all pages of
    the service-side `POST .../listResults` response. Use --filter for
    server-side status filtering.
  examples:
    - name: List every per-device result for a run
      text: az iot adr ns job run results -n myRun --job-name myJob --ns myNamespace -g myResourceGroup
    - name: Show only the failed devices in a run
      text: |
        az iot adr ns job run results -n myRun --job-name myJob --ns myNamespace -g myResourceGroup \\
          --filter "status eq 'Failed'"
  """

    helps[
        "iot adr ns job run cancel"
    ] = """
  type: command
  short-summary: Cancel a Device Registry job run.
  examples:
    - name: Cancel a run
      text: az iot adr ns job run cancel -n myRun --job-name myJob --ns myNamespace -g myResourceGroup
  """

    helps[
        "iot adr ns report"
    ] = """
  type: group
  short-summary: Manage Device Registry update-compliance reports.
  """

    helps[
        "iot adr ns report generate"
    ] = """
  type: command
  short-summary: Generate an update-compliance report.
  examples:
    - name: Generate a namespace update-compliance report
      text: az iot adr ns report generate --ns myNamespace -g myResourceGroup --report-type NamespaceUpdateComplianceReport
    - name: Generate a group best-updates report
      text: az iot adr ns report generate --ns myNamespace -g myResourceGroup --report-type GroupBestUpdatesComplianceReport --group-name myGroup
  """

    helps[
        "iot adr ns report latest"
    ] = """
  type: command
  short-summary: Show the latest update-compliance report.
  examples:
    - name: Show the latest namespace update-compliance report
      text: az iot adr ns report latest --ns myNamespace -g myResourceGroup --report-type NamespaceUpdateComplianceReport
  """
