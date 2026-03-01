#!/usr/bin/env python3
"""Convert old typed log functions to unified _log(L.X, ...) calls."""
import re
import os

FILES = [
    "azext_iot/tests/adr/_helpers.py",
    "azext_iot/tests/adr/conftest.py",
    "azext_iot/tests/adr/test_adr_crud_int.py",
    "azext_iot/tests/adr/test_adr_device_int.py",
    "azext_iot/tests/adr/test_adr_byor_int.py",
    "azext_iot/tests/adr/test_adr_policy_revoke_int.py",
    "azext_iot/tests/adr/test_adr_infra_int.py",
]

# These are simple 1:1 replacements of func_name( -> _log(L.TYPE,
FUNC_TO_TYPE = {
    "test_log":   "L.TEST",
    "step_log":   "L.STEP",
    "cmd_log":    "L.CMD",
    "result_log": "L.RESULT",
    "ok_log":     "L.OK",
    "warn_log":   "L.WARN",
    "error_log":  "L.WARN",
    "wait_log":   "L.WARN",
}

for filepath in FILES:
    if not os.path.exists(filepath):
        print(f"  SKIP (not found): {filepath}")
        continue

    with open(filepath) as f:
        content = f.read()
    original = content

    # 1) Replace func_name( -> _log(L.TYPE,  (but NOT inside _STYLES, def lines, etc.)
    for func, ltype in FUNC_TO_TYPE.items():
        # Negative lookbehind: don't match if preceded by word char (e.g. def test_log)
        # Also don't match import lines — we'll fix those separately
        content = re.sub(
            rf'(?<![.\w]){re.escape(func)}\(',
            f'_log({ltype}, ',
            content,
        )

    # 2) _timed_step -> timed_step
    content = content.replace("_timed_step(", "timed_step(")

    # 3) pass_log(xxx) was already converted to _log(L.WARN, xxx) above — wrong!
    #    Fix: in conftest.py, pass_log -> _log("_pass", ...) and fail_log -> _log("_fail", ...)
    #    But pass_log/fail_log are NOT in FUNC_TO_TYPE, so they weren't touched. Good.

    # 4) time_log(_fmt_duration(...)) -> _log("_time", "(%s)", _fmt_duration(...))
    #    time_log was NOT in FUNC_TO_TYPE so it's still as-is.
    #    Pattern: time_log(_fmt_duration(time.monotonic() - VAR))
    content = re.sub(
        r'(?<![.\w])time_log\(_fmt_duration\(time\.monotonic\(\)\s*-\s*(\w+)\)\)',
        r'_log("_time", "(%s)", _fmt_duration(time.monotonic() - \1))',
        content,
    )

    if content != original:
        with open(filepath, "w") as f:
            f.write(content)
        print(f"✓ {filepath}")
    else:
        print(f"  (no changes) {filepath}")
