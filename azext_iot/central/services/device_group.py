# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
# This is largely derived from https://docs.microsoft.com/en-us/rest/api/iotcentral/deviceGroups

from typing import List, Union
import requests

from knack.log import get_logger

from azure.cli.core.azclierror import AzureResponseError
from azext_iot.constants import CENTRAL_ENDPOINT
from azext_iot.central.services import _utility
from azext_iot.central.models.preview import DeviceGroupPreview
from azext_iot.central.models.v1_1_preview import DeviceGroupV1_1_preview
from azext_iot.central.models.enum import ApiVersion

logger = get_logger(__name__)

BASE_PATH = "api/deviceGroups"
MODEL = "deviceGroup"


def list_device_groups(
    cmd,
    app_id: str,
    token: str,
    api_version: str,
    max_pages=0,
    central_dns_suffix=CENTRAL_ENDPOINT,
) -> List[Union[DeviceGroupPreview, DeviceGroupV1_1_preview]]:
    """
    Get a list of all device groups in IoTC app

    Args:
        cmd: command passed into az
        app_id: name of app (used for forming request URL)
        token: (OPTIONAL) authorization token to fetch device details from IoTC.
            MUST INCLUDE type (e.g. 'SharedAccessToken ...', 'Bearer ...')
        central_dns_suffix: {centralDnsSuffixInPath} as found in docs

    Returns:
        list of device groups
    """

    device_groups = []

    url = "https://{}.{}/{}".format(app_id, central_dns_suffix, BASE_PATH)
    headers = _utility.get_headers(token, cmd)

    # Construct parameters
    query_parameters = {}
    query_parameters["api-version"] = api_version

    pages_processed = 0
    while (max_pages == 0 or pages_processed < max_pages) and url:
        response = requests.get(url, headers=headers, params=query_parameters)
        result = _utility.try_extract_result(response)

        if "value" not in result:
            raise AzureResponseError("Value is not present in body: {}".format(result))

        device_groups.extend(
            [
                DeviceGroupPreview(device_group)
                if api_version == ApiVersion.preview.value
                else DeviceGroupV1_1_preview(device_group)
                for device_group in result["value"]
            ]
        )

        url = result.get("nextLink", None)
        pages_processed = pages_processed + 1

    return device_groups


def get_device_group(
    cmd,
    app_id: str,
    device_group_id: str,
    token: str,
    api_version: str,
    central_dns_suffix=CENTRAL_ENDPOINT,
) -> Union[DeviceGroupPreview, DeviceGroupV1_1_preview]:
    """
    Get a specific device group from IoTC

    Args:
        cmd: command passed into az
        device_group_id: case sensitive device group id,
        app_id: name of app (used for forming request URL)
        token: (OPTIONAL) authorization token to fetch device details from IoTC.
            MUST INCLUDE type (e.g. 'SharedAccessToken ...', 'Bearer ...')
        central_dns_suffix: {centralDnsSuffixInPath} as found in docs

    Returns:
        device_group: dict
    """

    url = "https://{}.{}/{}/{}".format(
        app_id, central_dns_suffix, BASE_PATH, device_group_id
    )
    headers = _utility.get_headers(token, cmd)

    # Construct parameters
    query_parameters = {}
    query_parameters["api-version"] = api_version

    response = requests.get(url, headers=headers, params=query_parameters)
    result = _utility.try_extract_result(response)
    return _utility.get_object(result, model=MODEL, api_version=api_version)


def create_device_group(
    cmd,
    app_id: str,
    device_group_id: str,
    payload: dict,
    token: str,
    api_version: str,
    central_dns_suffix=CENTRAL_ENDPOINT,
) -> Union[DeviceGroupPreview, DeviceGroupV1_1_preview]:
    """
    Create a device group in IoTC

    Args:
        cmd: command passed into az
        app_id: name of app (used for forming request URL)
        device_group_id: case sensitive device group id,
        payload: see example payload available in
            <repo-root>/azext_iot/tests/central/json/device_group_int_test.json
            or check here for more information
            https://docs.microsoft.com/en-us/rest/api/iotcentral/devicegroups
        token: (OPTIONAL) authorization token to fetch device details from IoTC.
            MUST INCLUDE type (e.g. 'SharedAccessToken ...', 'Bearer ...')
        central_dns_suffix: {centralDnsSuffixInPath} as found in docs

    Returns:
        device_group: dict
    """

    url = "https://{}.{}/{}/{}".format(
        app_id, central_dns_suffix, BASE_PATH, device_group_id
    )
    headers = _utility.get_headers(token, cmd, has_json_payload=True)

    # Construct parameters
    query_parameters = {}
    query_parameters["api-version"] = api_version

    response = requests.put(url, headers=headers, json=payload, params=query_parameters)
    result = _utility.try_extract_result(response)
    return _utility.get_object(result, model=MODEL, api_version=api_version)


def update_device_group(
    cmd,
    app_id: str,
    device_group_id: str,
    payload: dict,
    token: str,
    api_version: str,
    central_dns_suffix=CENTRAL_ENDPOINT,
) -> Union[DeviceGroupPreview, DeviceGroupV1_1_preview]:
    """
    Updates a device group in IoTC

    Args:
        cmd: command passed into az
        app_id: name of app (used for forming request URL)
        device_group_id: case sensitive device group id,
        payload: see example payload available in
            <repo-root>/azext_iot/tests/central/json/device_group_int_test.json
            or check here for more information
            https://docs.microsoft.com/en-us/rest/api/iotcentral/devicegroups
        token: (OPTIONAL) authorization token to fetch device details from IoTC.
            MUST INCLUDE type (e.g. 'SharedAccessToken ...', 'Bearer ...')
        central_dns_suffix: {centralDnsSuffixInPath} as found in docs

    Returns:
        device_group: dict
    """

    url = "https://{}.{}/{}/{}".format(
        app_id, central_dns_suffix, BASE_PATH, device_group_id
    )
    headers = _utility.get_headers(token, cmd, has_json_payload=True)

    # Construct parameters
    query_parameters = {}
    query_parameters["api-version"] = api_version

    response = requests.patch(
        url, headers=headers, json=payload, params=query_parameters
    )
    result = _utility.try_extract_result(response)
    return _utility.get_object(result, MODEL, api_version)


def delete_device_group(
    cmd,
    app_id: str,
    device_group_id: str,
    token: str,
    api_version: str,
    central_dns_suffix=CENTRAL_ENDPOINT,
) -> dict:
    """
    Delete a device group from IoTC

    Args:
        cmd: command passed into az
        app_id: name of app (used for forming request URL)
        device_group_id: case sensitive device group id,
        token: (OPTIONAL) authorization token to fetch device details from IoTC.
            MUST INCLUDE type (e.g. 'SharedAccessToken ...', 'Bearer ...')
        central_dns_suffix: {centralDnsSuffixInPath} as found in docs

    Returns:
        device_group: dict
    """
    url = "https://{}.{}/{}/{}".format(
        app_id, central_dns_suffix, BASE_PATH, device_group_id
    )
    headers = _utility.get_headers(token, cmd)

    # Construct parameters
    query_parameters = {}
    query_parameters["api-version"] = api_version

    response = requests.delete(url, headers=headers, params=query_parameters)
    return _utility.try_extract_result(response)
