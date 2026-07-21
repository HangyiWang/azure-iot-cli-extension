# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ADR_REGEN = REPO_ROOT / "scripts" / "regen_deviceregistry_sdk.sh"
GENERIC_REGEN = REPO_ROOT / "scripts" / "regen_autorest_sdk.sh"


def _run(*args):
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_regeneration_scripts_have_valid_shell_syntax():
    result = _run("bash", "-n", ADR_REGEN, GENERIC_REGEN)

    assert result.returncode == 0, result.stderr


def test_regeneration_scripts_use_portable_paths():
    scripts = ADR_REGEN.read_text(encoding="utf-8") + GENERIC_REGEN.read_text(
        encoding="utf-8"
    )

    assert "realpath" not in scripts
    assert "/home/hangyiwang" not in scripts


def test_device_registry_wrapper_rejects_namespace_override():
    result = _run(ADR_REGEN, "--namespace", ".")

    assert result.returncode == 2
    assert "Unknown flag: --namespace" in result.stderr
    assert (REPO_ROOT / "azext_iot").is_dir()


def test_device_registry_wrapper_rejects_unsafe_tag():
    result = _run(ADR_REGEN, "--tag", "../../repo", "--no-install")

    assert result.returncode == 2
    assert "unsupported tag" in result.stderr


def test_generic_generator_rejects_root_output(tmp_path):
    readme = tmp_path / "readme.md"
    readme.write_text("### Tag: safe-tag\n", encoding="utf-8")

    result = _run(
        GENERIC_REGEN,
        "--tag",
        "safe-tag",
        "--readme",
        readme,
        "--output",
        "/",
    )

    assert result.returncode == 2
    assert "refusing unsafe output folder" in result.stderr
