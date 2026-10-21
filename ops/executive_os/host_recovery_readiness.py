"""Read-only Darwin host recovery-readiness observer and CLI.

One bounded observation of local public system state, classified by the closed
contract in :mod:`control_plane.executive_recovery_readiness`.  Every external
call is a fixed, absolute, read-only macOS system tool, and every filesystem
read is an existence check on a fixed, absolute path derived from the reviewed
label set — never a caller-supplied path and never a directory scan.

The mandatory ``--profile`` argument selects which closed requirement table
classifies the result.  It is deliberately not command authority: all profiles
collect the same fixed superset of observations with the same fixed argv, so
naming a profile can never widen what this module runs or reads.

This module never mutates power policy, launchd state, disk encryption, remote
login, network routes, accounts, credentials, or services; never escalates
privilege; never opens a socket; and never persists anything.  Remediation of a
failing predicate is a separate one-time administrator ceremony owned by the
reviewed privileged broker, not by this observer.
"""
from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, BinaryIO, NoReturn, TextIO


_REPO_ROOT = Path(__file__).resolve().parents[2]
if __package__ in {None, ""} and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from control_plane.executive_recovery_readiness import (  # noqa: E402
    ALL_DAEMON_LABELS,
    HOST_REF_RE,
    READINESS_PROFILES,
    USER_SESSION_CRITICAL_LABELS,
    RecoveryReadinessContractError,
    canonical_recovery_readiness_json,
    classify_recovery_readiness,
)


PMSET_CUSTOM_COMMAND = ("/usr/bin/pmset", "-g", "custom")
SW_VERS_COMMAND = ("/usr/bin/sw_vers", "-productVersion")
SYSCTL_ARM64_COMMAND = ("/usr/sbin/sysctl", "-n", "hw.optional.arm64")
FDESETUP_STATUS_COMMAND = ("/usr/bin/fdesetup", "status")
LAUNCHCTL_PRINT_DISABLED_COMMAND = ("/bin/launchctl", "print-disabled", "system")
READ_ONLY_COMMANDS = (
    PMSET_CUSTOM_COMMAND,
    SW_VERS_COMMAND,
    SYSCTL_ARM64_COMMAND,
    FDESETUP_STATUS_COMMAND,
    LAUNCHCTL_PRINT_DISABLED_COMMAND,
)

SSHD_LABEL = "com.openssh.sshd"
# ``launchctl print-disabled`` is an override table, not an inventory: a normally
# enabled installed service usually has no row at all.  Installation is proven
# instead by the fixed path every Executive installer writes and every
# uninstaller removes (``ops/executive_os/install.sh``, ``uninstall.sh``,
# ``prepare-capacity-host.sh``), and by the macOS-owned sshd job definition.
SYSTEM_DAEMON_PLIST_DIR = Path("/Library/LaunchDaemons")
SSHD_SYSTEM_PLIST = Path("/System/Library/LaunchDaemons/ssh.plist")
ROOT_VOLUME = "/"
DEFAULT_LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
COMMAND_TIMEOUT_SECONDS = 10
MAX_COMMAND_OUTPUT_BYTES = 1 * 1024 * 1024
_FIXED_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"}

_POWER_SECTION_RE = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*:\s*$")
_POWER_SETTING_RE = re.compile(r"^([a-z][a-z0-9]*)\s+(0|[1-9][0-9]{0,9})$")
_DISABLED_ROW_RE = re.compile(r'^"([A-Za-z0-9._\-]{1,255})"\s*=>\s*([A-Za-z]+)$')
_LAUNCHCTL_STATE_RE = re.compile(r"^state\s*=\s*([a-z][a-z ]*)$")
_DISABLED_TOKENS = {"disabled": True, "true": True, "enabled": False, "false": False}

_PROBE_ERROR_CODES = frozenset(
    {
        "ARGUMENTS_INVALID",
        "LAUNCH_AGENTS_PATH_INVALID",
        "OBSERVATION_INTERNAL_ERROR",
        "PLATFORM_UNAVAILABLE",
        "POWER_POLICY_MALFORMED",
        "PROBE_INTERNAL_ERROR",
        "PROFILE_INVALID",
        "REFERENCE_INVALID",
        "UNSUPPORTED_PLATFORM",
        "WALL_CLOCK_INVALID",
    }
)


class RecoveryReadinessProbeError(RuntimeError):
    """A typed probe refusal that never contains raw host output."""

    def __init__(self, code: str) -> None:
        safe_code = (
            code
            if type(code) is str and code in _PROBE_ERROR_CODES
            else "PROBE_INTERNAL_ERROR"
        )
        self.code = safe_code
        super().__init__(safe_code)


def _refuse(code: str) -> NoReturn:
    raise RecoveryReadinessProbeError(code)


def launchctl_print_command(label: str) -> tuple[str, ...]:
    """Return the fixed read-only service-state query for one known label."""

    if label not in ALL_DAEMON_LABELS and label != SSHD_LABEL:
        _refuse("REFERENCE_INVALID")
    return ("/bin/launchctl", "print", f"system/{label}")


def system_daemon_plist_path(label: str) -> Path:
    """Return the fixed install path of one known Executive system LaunchDaemon."""

    if label not in ALL_DAEMON_LABELS:
        _refuse("REFERENCE_INVALID")
    return SYSTEM_DAEMON_PLIST_DIR / f"{label}.plist"


# ------------------------------------------------------------------ parsers


def parse_pmset_custom(stdout: str) -> dict[str, dict[str, int]]:
    """Strictly parse ``pmset -g custom`` into per-power-source settings."""

    if type(stdout) is not str or not stdout.strip():
        _refuse("POWER_POLICY_MALFORMED")

    sections: dict[str, dict[str, int]] = {}
    current: dict[str, int] | None = None
    for raw in stdout.splitlines():
        if not raw.strip():
            continue
        section = _POWER_SECTION_RE.fullmatch(raw.strip())
        if section is not None:
            current = {}
            sections[section.group(1)] = current
            continue
        if current is None:
            _refuse("POWER_POLICY_MALFORMED")
        setting = _POWER_SETTING_RE.fullmatch(raw.strip())
        if setting is None:
            # macOS prints human-labelled rows such as "Sleep On Power Button".
            # They are not machine settings and are deliberately not observed.
            continue
        current[setting.group(1)] = int(setting.group(2))
    if not sections:
        _refuse("POWER_POLICY_MALFORMED")
    return sections


def parse_fdesetup_status(stdout: str) -> str:
    """Classify ``fdesetup status`` without carrying any recovery material."""

    if type(stdout) is not str:
        return "FILEVAULT_STATE_UNKNOWN"
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    for line in lines:
        if line == "FileVault is On.":
            return "FILEVAULT_ON"
        if line == "FileVault is Off.":
            return "FILEVAULT_OFF"
    for line in lines:
        if line.startswith("Encryption in progress"):
            return "FILEVAULT_ENCRYPTION_IN_PROGRESS"
        if line.startswith("Decryption in progress"):
            return "FILEVAULT_DECRYPTION_IN_PROGRESS"
    return "FILEVAULT_STATE_UNKNOWN"


def parse_launchctl_print_disabled(stdout: str) -> dict[str, bool]:
    """Map each listed launchd label to whether it is disabled."""

    disabled: dict[str, bool] = {}
    if type(stdout) is not str:
        return disabled
    for raw in stdout.splitlines():
        row = _DISABLED_ROW_RE.fullmatch(raw.strip())
        if row is None:
            continue
        token = _DISABLED_TOKENS.get(row.group(2).lower())
        if token is None:
            continue
        disabled[row.group(1)] = token
    return disabled


def parse_launchctl_print_state(stdout: str) -> str:
    """Reduce one ``launchctl print`` projection to a closed state token."""

    if type(stdout) is not str:
        return "UNKNOWN"
    for raw in stdout.splitlines():
        state = _LAUNCHCTL_STATE_RE.fullmatch(raw.strip())
        if state is None:
            continue
        return "RUNNING" if state.group(1).strip() == "running" else "LOADED_NOT_RUNNING"
    return "UNKNOWN"


# ---------------------------------------------------------------- collection


def _run(command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Run one fixed read-only system tool with a closed environment."""

    completed = subprocess.run(
        list(command),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=False,
        check=False,
        close_fds=True,
        env=_FIXED_ENV,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    payload = completed.stdout or b""
    if len(payload) > MAX_COMMAND_OUTPUT_BYTES:
        payload = b""
    return subprocess.CompletedProcess(
        command, completed.returncode, payload.decode("utf-8", errors="replace"), ""
    )


def _read_stdout(
    runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]],
    command: tuple[str, ...],
) -> str | None:
    """Return stdout for a successful fixed read, or ``None`` for any refusal."""

    try:
        completed = runner(command)
    except Exception:
        return None
    if not isinstance(completed, subprocess.CompletedProcess):
        return None
    if completed.returncode != 0 or type(completed.stdout) is not str:
        return None
    return completed.stdout


def _default_free_bytes() -> int | None:
    try:
        usage = os.statvfs(ROOT_VOLUME)
        free = usage.f_bavail * usage.f_frsize
    except Exception:
        return None
    if type(free) is not int or free < 0:
        return None
    return free


def _default_wall_time_ms() -> int:
    return time.time_ns() // 1_000_000


def _observe_power(
    runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]],
) -> dict[str, int] | None:
    stdout = _read_stdout(runner, PMSET_CUSTOM_COMMAND)
    if stdout is None:
        return None
    try:
        sections = parse_pmset_custom(stdout)
    except RecoveryReadinessProbeError:
        return None
    return sections.get("AC Power")


def _observe_architecture(
    runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]],
) -> bool | None:
    stdout = _read_stdout(runner, SYSCTL_ARM64_COMMAND)
    if stdout is None:
        return None
    token = stdout.strip()
    if token == "1":
        return True
    if token == "0":
        return False
    return None


def _observe_user_session_agents(launch_agents_dir: Path) -> int | None:
    try:
        if not launch_agents_dir.is_dir():
            return None
        present = 0
        for label in USER_SESSION_CRITICAL_LABELS:
            if (launch_agents_dir / f"{label}.plist").is_file():
                present += 1
    except OSError:
        return None
    return present


def _default_plist_exists(path: Path) -> bool:
    return path.is_file()


def _job_definition_present(
    plist_exists: Callable[[Path], bool], path: Path
) -> bool | None:
    """Return whether one fixed job definition exists, or ``None`` if unreadable."""

    try:
        present = plist_exists(path)
    except Exception:
        return None
    return present if type(present) is bool else None


def _observe_daemon(
    runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]],
    plist_exists: Callable[[Path], bool],
    overrides: dict[str, bool] | None,
    label: str,
) -> str:
    """Classify one fixed label from install, override and runtime evidence in turn."""

    installed = _job_definition_present(plist_exists, system_daemon_plist_path(label))
    if installed is False:
        return "NOT_INSTALLED"
    override = None if overrides is None else overrides.get(label)
    if override is True:
        return "DISABLED"
    if installed is None or overrides is None:
        return "UNKNOWN"
    service_stdout = _read_stdout(runner, launchctl_print_command(label))
    if service_stdout is None:
        # Installed and not overridden, but launchd will not describe the label.
        # It is neither proven loaded nor proven absent, so stay closed.
        return "UNKNOWN"
    return parse_launchctl_print_state(service_stdout)


def _observe_remote_login(
    runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]],
    plist_exists: Callable[[Path], bool],
    overrides: dict[str, bool] | None,
) -> str:
    """Classify Remote Login from the macOS-owned sshd job, not from plist presence."""

    installed = _job_definition_present(plist_exists, SSHD_SYSTEM_PLIST)
    if installed is False:
        return "NOT_INSTALLED"
    override = None if overrides is None else overrides.get(SSHD_LABEL)
    if override is True:
        return "DISABLED"
    if installed is None or overrides is None:
        return "UNKNOWN"
    # ``ssh.plist`` ships with macOS whether or not Remote Login is on, so only a
    # launchd-registered, socket-capable job proves the listener is enabled.
    if _read_stdout(runner, launchctl_print_command(SSHD_LABEL)) is None:
        return "UNKNOWN"
    return "ENABLED"


def _observe_services(
    runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]],
    plist_exists: Callable[[Path], bool],
) -> tuple[dict[str, str], str]:
    """Observe launchd enablement and run state without changing either."""

    stdout = _read_stdout(runner, LAUNCHCTL_PRINT_DISABLED_COMMAND)
    overrides = parse_launchctl_print_disabled(stdout) if stdout is not None else None

    daemons = {
        label: _observe_daemon(runner, plist_exists, overrides, label)
        for label in ALL_DAEMON_LABELS
    }
    return daemons, _observe_remote_login(runner, plist_exists, overrides)


def collect_recovery_observation(
    *,
    host_ref: str | None = None,
    runner: Callable[[tuple[str, ...]], subprocess.CompletedProcess[str]] | None = None,
    platform_system: Callable[[], str] | None = None,
    plist_exists: Callable[[Path], bool] | None = None,
    launch_agents_dir: Path | None = None,
    free_bytes: Callable[[], int | None] | None = None,
    wall_time_ms: Callable[[], int] | None = None,
) -> dict[str, Any]:
    """Collect exactly one bounded, mutation-free recovery-readiness observation."""

    if host_ref is not None and (
        type(host_ref) is not str or HOST_REF_RE.fullmatch(host_ref) is None
    ):
        _refuse("REFERENCE_INVALID")

    platform_fn = platform_system or platform.system
    try:
        observed_platform = platform_fn()
    except Exception:
        _refuse("PLATFORM_UNAVAILABLE")
    if observed_platform != "Darwin":
        _refuse("UNSUPPORTED_PLATFORM")

    agents_dir = (
        launch_agents_dir if launch_agents_dir is not None else DEFAULT_LAUNCH_AGENTS_DIR
    )
    if not isinstance(agents_dir, Path) or not agents_dir.is_absolute():
        _refuse("LAUNCH_AGENTS_PATH_INVALID")

    run = runner or _run
    exists_fn = plist_exists or _default_plist_exists
    wall_fn = wall_time_ms or _default_wall_time_ms
    free_fn = free_bytes or _default_free_bytes

    try:
        observed_at_ms = wall_fn()
    except Exception:
        _refuse("WALL_CLOCK_INVALID")
    if type(observed_at_ms) is not int or observed_at_ms < 1:
        _refuse("WALL_CLOCK_INVALID")

    product_version = _read_stdout(run, SW_VERS_COMMAND)
    fdesetup_stdout = _read_stdout(run, FDESETUP_STATUS_COMMAND)
    daemons, remote_login = _observe_services(run, exists_fn)

    try:
        observed_free = free_fn()
    except Exception:
        observed_free = None
    if observed_free is not None and (
        type(observed_free) is not int or observed_free < 0
    ):
        observed_free = None

    return {
        "host_ref": host_ref,
        "observed_at_ms": observed_at_ms,
        "os_name": "Darwin",
        "macos_product_version": (
            product_version.strip() or None if product_version is not None else None
        ),
        "apple_silicon": _observe_architecture(run),
        "ac_power_settings": _observe_power(run),
        "filevault_code": (
            parse_fdesetup_status(fdesetup_stdout)
            if fdesetup_stdout is not None
            else "FILEVAULT_STATE_UNKNOWN"
        ),
        "remote_login": remote_login,
        "system_daemons": daemons,
        "user_session_agents_present": _observe_user_session_agents(agents_dir),
        "root_free_bytes": observed_free,
    }


# ----------------------------------------------------------------------- CLI


class _ClosedArgumentParser(argparse.ArgumentParser):
    """Reject invalid argv without echoing caller-controlled values."""

    def error(self, _message: str) -> NoReturn:
        _refuse("ARGUMENTS_INVALID")


class _OpaqueHostRefAction(argparse.Action):
    """Accept only one opaque host reference and never echo a rejected value."""

    def __call__(
        self,
        _parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        if option_string is None or type(values) is not str:
            _refuse("ARGUMENTS_INVALID")
        if getattr(namespace, self.dest, None) is not None:
            _refuse("ARGUMENTS_INVALID")
        if HOST_REF_RE.fullmatch(values) is None:
            _refuse("REFERENCE_INVALID")
        setattr(namespace, self.dest, values)


class _ProfileAction(argparse.Action):
    """Accept exactly one of the two closed profile strings, and never guess."""

    def __call__(
        self,
        _parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: str | None = None,
    ) -> None:
        if option_string is None or type(values) is not str:
            _refuse("ARGUMENTS_INVALID")
        if getattr(namespace, self.dest, None) is not None:
            _refuse("ARGUMENTS_INVALID")
        if values not in READINESS_PROFILES:
            _refuse("PROFILE_INVALID")
        setattr(namespace, self.dest, values)


def _parser() -> argparse.ArgumentParser:
    parser = _ClosedArgumentParser(
        description="Emit one read-only canonical host recovery-readiness report",
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument("--host-ref", required=False, action=_OpaqueHostRefAction)
    # Mandatory and never defaulted: the host's role is an operator statement,
    # not something this observer may infer from which services happen to be
    # installed.  See the module docstring of the contract for why.
    parser.add_argument("--profile", required=True, action=_ProfileAction)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    collector: Callable[..., Mapping[str, Any]] | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    collect = collector or collect_recovery_observation
    out = stdout if stdout is not None else sys.stdout.buffer
    err = stderr if stderr is not None else sys.stderr
    try:
        # Argument refusals happen before the first observation, so an omitted
        # or unknown profile never reads or touches host state.
        args = _parser().parse_args(argv)
        observation = collect(host_ref=args.host_ref)
        payload = canonical_recovery_readiness_json(
            classify_recovery_readiness(observation, profile=args.profile),
            expected_profile=args.profile,
        )
    except RecoveryReadinessProbeError as exc:
        print(f"host recovery readiness refused: {exc}", file=err)
        return 65
    except RecoveryReadinessContractError as exc:
        print(f"host recovery readiness refused: {exc}", file=err)
        return 65
    except Exception:
        print("host recovery readiness refused: PROBE_INTERNAL_ERROR", file=err)
        return 65

    try:
        offset = 0
        while offset < len(payload):
            written = out.write(payload[offset:])
            if type(written) is not int or not 1 <= written <= len(payload) - offset:
                raise OSError("stdout_write_failed")
            offset += written
        out.flush()
    except Exception:
        print(
            "host recovery readiness output uncertain: OUTPUT_EFFECT_UNKNOWN",
            file=err,
        )
        return 74
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "COMMAND_TIMEOUT_SECONDS",
    "FDESETUP_STATUS_COMMAND",
    "LAUNCHCTL_PRINT_DISABLED_COMMAND",
    "PMSET_CUSTOM_COMMAND",
    "READ_ONLY_COMMANDS",
    "SSHD_LABEL",
    "SSHD_SYSTEM_PLIST",
    "SW_VERS_COMMAND",
    "SYSCTL_ARM64_COMMAND",
    "SYSTEM_DAEMON_PLIST_DIR",
    "RecoveryReadinessProbeError",
    "collect_recovery_observation",
    "launchctl_print_command",
    "main",
    "parse_fdesetup_status",
    "parse_launchctl_print_disabled",
    "parse_launchctl_print_state",
    "parse_pmset_custom",
    "system_daemon_plist_path",
]
