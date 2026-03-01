# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
ADR infrastructure smoke test.

Validates the full ADR pipeline in the standard ADR-int tox environment
(no preview SDK required):

    UAMI -> ADR namespace (credential + policy) -> IoT Hub Gen2 (ADR link)
    -> DPS (linked hub, enrollments) -> credential sync -> hub cert verification

This is the only test in ADR-int that exercises DPS integration + credential sync.
"""

import pytest

from azext_iot.tests import CaptureOutputLiveScenarioTest
from azext_iot.tests.adr._helpers import ADRHubInfraHelper
from azext_iot.tests.adr._log import L, _log
from azext_iot.tests.adr.conftest import (
    TEST_RG,
    generate_adr_namespace_name,
    generate_device_id,
    generate_dps_name,
    generate_enrollment_group_id,
    generate_hub_name,
    generate_identity_name,
)


@pytest.mark.usefixtures("set_cwd")
class TestADRInfrastructure(ADRHubInfraHelper, CaptureOutputLiveScenarioTest):
    """Smoke test: full ADR infrastructure pipeline including DPS and credential sync."""

    def test_adr_infra_pipeline(self):
        """Validate ADR namespace, credential, policy, hub, DPS, enrollment, and sync."""
        _log(L.TEST, "test_adr_infra_pipeline")
        rg = TEST_RG
        namespace_name = generate_adr_namespace_name()
        hub_name = generate_hub_name()
        dps_name = generate_dps_name()
        identity_name = generate_identity_name()
        device_id = generate_device_id()
        enrollment_group_id = generate_enrollment_group_id()

        _log(L.STEP, 
            "Info ❯ ns=%s hub=%s dps=%s",
            namespace_name, hub_name, dps_name,
        )

        try:
            infra = self.setup_full_infra(
                resource_group=rg,
                namespace_name=namespace_name,
                hub_name=hub_name,
                identity_name=identity_name,
            )
            self.setup_dps_with_sync(
                infra=infra,
                resource_group=rg,
                namespace_name=namespace_name,
                dps_name=dps_name,
                device_id=device_id,
                enrollment_group_id=enrollment_group_id,
            )
            _log(L.OK, "Infrastructure test passed")
        finally:
            self.cleanup_full_infra(
                resource_group=rg,
                hub_name=hub_name,
                namespace_name=namespace_name,
                identity_name=identity_name,
                dps_name=dps_name,
            )
