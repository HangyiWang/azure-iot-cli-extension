# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import os

from azure.cli.core.extension import get_extension_path
from azext_iot.deviceupdate.providers.loaders import reload_modules
from azext_iot.constants import EXTENSION_NAME, INTERNAL_AZURE_CORE_NAMESPACE


def test_adu_reload_modules():
    reload_modules()

    import azure
    import azure.core
    import azure.core.exceptions
    import azure.core.utils
    import sys
    import msrest

    ext_path = get_extension_path(EXTENSION_NAME)
    ext_azure_core_dir = os.path.join(ext_path, "azure", "core")
    uses_extension_dependencies = os.path.isdir(ext_azure_core_dir)

    internal_core = sys.modules.get(INTERNAL_AZURE_CORE_NAMESPACE)
    assert internal_core
    assert internal_core.__name__ == "azure.core"
    assert internal_core.exceptions.__name__ == "azure.core.exceptions"

    if uses_extension_dependencies:
        assert internal_core.__path__ == [ext_azure_core_dir]
        assert internal_core.exceptions.__file__ == os.path.join(ext_azure_core_dir, "exceptions.py")
    else:
        assert internal_core.__path__ == azure.core.__path__
        assert internal_core.exceptions.__file__ == azure.core.exceptions.__file__

    assert azure.core.__name__ == "azure.core"
    assert azure.core.__path__

    assert azure.core.utils.__name__ == "azure.core.utils"
    assert azure.core.utils.__path__

    assert msrest.__name__ == "msrest"
    assert msrest.__path__
