# coding=utf-8
# --------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# Code generated by Microsoft (R) AutoRest Code Generator.
# Changes may cause incorrect behavior and will be lost if the code is regenerated.
# --------------------------------------------------------------------------

from typing import Any, TYPE_CHECKING

from azure.core.configuration import Configuration
from azure.core.pipeline import policies
from azure.mgmt.core.policies import ARMChallengeAuthenticationPolicy, ARMHttpLoggingPolicy

from ._version import VERSION

if TYPE_CHECKING:
    # pylint: disable=unused-import,ungrouped-imports
    from azure.core.credentials import TokenCredential


class AzureIoTCentralConfiguration(Configuration):  # pylint: disable=too-many-instance-attributes
    """Configuration for AzureIoTCentral.

    Note that all parameters used to create this instance are saved as instance
    attributes.

    :param subdomain: The application subdomain. Required.
    :type subdomain: str
    :param credential: Credential needed for the client to connect to Azure. Required.
    :type credential: ~azure.core.credentials.TokenCredential
    :param base_domain: The base domain for all Azure IoT Central service requests. Default value
     is "azureiotcentral.com".
    :type base_domain: str
    :keyword api_version: Api Version. Default value is "2022-06-30-preview". Note that overriding
     this default value may result in unsupported behavior.
    :paramtype api_version: str
    """

    def __init__(
        self, subdomain: str, credential: "TokenCredential", base_domain: str = "azureiotcentral.com", **kwargs: Any
    ) -> None:
        super(AzureIoTCentralConfiguration, self).__init__(**kwargs)
        api_version = kwargs.pop("api_version", "2022-06-30-preview")  # type: str

        if subdomain is None:
            raise ValueError("Parameter 'subdomain' must not be None.")
        if credential is None:
            raise ValueError("Parameter 'credential' must not be None.")
        if base_domain is None:
            raise ValueError("Parameter 'base_domain' must not be None.")

        self.subdomain = subdomain
        self.credential = credential
        self.base_domain = base_domain
        self.api_version = api_version
        self.credential_scopes = kwargs.pop("credential_scopes", ["https://apps.azureiotcentral.com/.default"])
        kwargs.setdefault("sdk_moniker", "iotcentral/{}".format(VERSION))
        self._configure(**kwargs)

    def _configure(
        self, **kwargs  # type: Any
    ):
        # type: (...) -> None
        self.user_agent_policy = kwargs.get("user_agent_policy") or policies.UserAgentPolicy(**kwargs)
        self.headers_policy = kwargs.get("headers_policy") or policies.HeadersPolicy(**kwargs)
        self.proxy_policy = kwargs.get("proxy_policy") or policies.ProxyPolicy(**kwargs)
        self.logging_policy = kwargs.get("logging_policy") or policies.NetworkTraceLoggingPolicy(**kwargs)
        self.http_logging_policy = kwargs.get("http_logging_policy") or ARMHttpLoggingPolicy(**kwargs)
        self.retry_policy = kwargs.get("retry_policy") or policies.RetryPolicy(**kwargs)
        self.custom_hook_policy = kwargs.get("custom_hook_policy") or policies.CustomHookPolicy(**kwargs)
        self.redirect_policy = kwargs.get("redirect_policy") or policies.RedirectPolicy(**kwargs)
        self.authentication_policy = kwargs.get("authentication_policy")
        if self.credential and not self.authentication_policy:
            self.authentication_policy = ARMChallengeAuthenticationPolicy(
                self.credential, *self.credential_scopes, **kwargs
            )
