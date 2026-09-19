#!/usr/bin/env python3
"""Apply the one reviewed AC power policy required for secondary fleet hosts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NoReturn, TextIO

_REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""} and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ops.executive_os.host_recovery_readiness import (  # noqa: E402
    RecoveryReadinessProbeError,
    parse_pmset_custom,
)

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


class SecondaryHostPowerPolicyError(RuntimeError):
    """A fixed, secret-free refusal for the bounded power-policy action."""


def _refuse() -> NoReturn:
    raise SecondaryHostPowerPolicyError("SECONDARY_HOST_POWER_POLICY_REFUSED")


def _default_runner(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
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


def _run_checked(
    runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]],
    command: tuple[str, ...],
) -> subprocess.CompletedProcess[str]:
    try:
        completed = runner(command)
    except Exception:
        _refuse()
    if (
        not isinstance(completed, subprocess.CompletedProcess)
        or completed.returncode != 0
        or not isinstance(completed.stdout, str)
        or len(completed.stdout.encode("utf-8", errors="replace")) > MAX_OUTPUT_BYTES
    ):
        _refuse()
    return completed


def prepare_secondary_host_power_policy(
    *,
    runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]] | None = None,
    euid: int | None = None,
) -> dict[str, object]:
    """Set charger-only fleet power policy and prove the resulting AC state."""

    observed_euid = os.geteuid() if euid is None else euid
    if isinstance(observed_euid, bool) or not isinstance(observed_euid, int) or observed_euid != 0:
        _refuse()

    run = runner or _default_runner
    _run_checked(run, PMSET_SET_COMMAND)
    observed = _run_checked(run, PMSET_READ_COMMAND)
    try:
        sections = parse_pmset_custom(observed.stdout)
    except RecoveryReadinessProbeError:
        _refuse()

    ac = sections.get("AC Power")
    if not isinstance(ac, dict) or ac.get("sleep") != 0 or ac.get("autorestart") != 1:
        _refuse()

    return {
        "schema": RECEIPT_SCHEMA,
        "scope": "charger",
        "sleep": 0,
        "autorestart": 1,
    }


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if list(sys.argv[1:] if argv is None else argv):
        print("secondary-host power policy refused", file=err)
        return 64
    try:
        receipt = prepare_secondary_host_power_policy()
    except SecondaryHostPowerPolicyError:
        print("secondary-host power policy refused", file=err)
        return 65
    out.write(json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
