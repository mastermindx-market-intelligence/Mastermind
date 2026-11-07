#!/usr/bin/env python3
"""Apply the one reviewed AC power policy required for secondary fleet hosts."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Callable, Dict, NoReturn, Optional, Sequence, TextIO, Tuple

RECEIPT_SCHEMA = "mastermind.secondary_host_power_policy_receipt/v1"
PMSET_SET_COMMAND = (
    "/usr/bin/pmset",
    "-c",
    "sleep",
    "0",
    "autorestart",
    "1",
)
PMSET_READ_COMMAND = ("/usr/bin/pmset", "-g", "custom")
COMMAND_TIMEOUT_SECONDS = 10
MAX_OUTPUT_BYTES = 64 * 1024
_FIXED_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"}
_POWER_SECTION_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*:\s*$")
_POWER_SETTING_RE = re.compile(r"^([a-z][a-z0-9]*)\s+(0|[1-9][0-9]{0,9})$")


class SecondaryHostPowerPolicyError(RuntimeError):
    """A fixed, secret-free refusal before the bounded effect begins."""


class SecondaryHostPowerPolicyEffectUnknown(SecondaryHostPowerPolicyError):
    """The fixed mutation may have started but its final postcondition is unknown."""


def _refuse() -> NoReturn:
    raise SecondaryHostPowerPolicyError("SECONDARY_HOST_POWER_POLICY_REFUSED")


def _effect_unknown() -> NoReturn:
    raise SecondaryHostPowerPolicyEffectUnknown("SECONDARY_HOST_POWER_POLICY_EFFECT_UNKNOWN")


def _default_runner(command: Tuple[str, ...]) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        close_fds=True,
        env=_FIXED_ENV,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


def _run_mutation(
    runner: Callable[[Tuple[str, ...]], subprocess.CompletedProcess],
) -> subprocess.CompletedProcess:
    try:
        completed = runner(PMSET_SET_COMMAND)
    except Exception:
        _effect_unknown()
    if (
        not isinstance(completed, subprocess.CompletedProcess)
        or completed.returncode != 0
    ):
        _effect_unknown()
    return completed


def _run_readback(
    runner: Callable[[Tuple[str, ...]], subprocess.CompletedProcess],
) -> subprocess.CompletedProcess:
    try:
        completed = runner(PMSET_READ_COMMAND)
    except Exception:
        _effect_unknown()
    if (
        not isinstance(completed, subprocess.CompletedProcess)
        or completed.returncode != 0
        or not isinstance(completed.stdout, str)
        or len(completed.stdout.encode("utf-8", errors="replace")) > MAX_OUTPUT_BYTES
    ):
        _effect_unknown()
    return completed


def _parse_ac_power(stdout: str) -> Dict[str, int]:
    """Parse only the numeric AC section needed for the post-effect proof."""

    if not isinstance(stdout, str) or not stdout.strip():
        _refuse()
    sections: Dict[str, Dict[str, int]] = {}
    current: Optional[Dict[str, int]] = None
    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        section = _POWER_SECTION_RE.fullmatch(raw.strip())
        if section is not None:
            current = {}
            sections[section.group(1)] = current
            continue
        if current is None:
            _refuse()
        setting = _POWER_SETTING_RE.fullmatch(raw.strip())
        if setting is not None:
            current[setting.group(1)] = int(setting.group(2))
    ac = sections.get("AC Power")
    if not isinstance(ac, dict):
        _refuse()
    return ac


def prepare_secondary_host_power_policy(
    *,
    runner: Optional[Callable[[Tuple[str, ...]], subprocess.CompletedProcess]] = None,
    euid: Optional[int] = None,
) -> Dict[str, object]:
    """Set charger-only fleet power policy and prove the resulting AC state."""

    observed_euid = os.geteuid() if euid is None else euid
    if isinstance(observed_euid, bool) or not isinstance(observed_euid, int) or observed_euid != 0:
        _refuse()

    run = runner or _default_runner
    _run_mutation(run)
    observed = _run_readback(run)
    try:
        ac = _parse_ac_power(observed.stdout)
    except SecondaryHostPowerPolicyError:
        _effect_unknown()
    if ac.get("sleep") != 0 or ac.get("autorestart") != 1:
        _effect_unknown()

    return {
        "schema": RECEIPT_SCHEMA,
        "scope": "charger",
        "sleep": 0,
        "autorestart": 1,
    }


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    stdout: Optional[TextIO] = None,
    stderr: Optional[TextIO] = None,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if list(sys.argv[1:] if argv is None else argv):
        print("secondary-host power policy refused", file=err)
        return 64
    try:
        receipt = prepare_secondary_host_power_policy()
    except SecondaryHostPowerPolicyEffectUnknown:
        print("secondary-host power policy effect unknown", file=err)
        return 75
    except SecondaryHostPowerPolicyError:
        print("secondary-host power policy refused", file=err)
        return 65
    out.write(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
