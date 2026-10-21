#!/usr/bin/env python3
"""Focused local safety for the existing Meta-CEO external lane.

This module is deliberately not a scheduler, queue, provider registry, or durable
Job/Attempt store.  It owns only the lifetime of subprocesses created by the
current Python process and admission locks in the lane's pre-existing active/
directory.  Unknown processes are never terminated by heuristic.
"""
from __future__ import annotations

import atexit
import asyncio
import ctypes
import sys
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import socket
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

LEASE_SCHEMA = "mastermind.local_lane_lease.v1"
PROCESS_RECEIPT_SCHEMA = "mastermind.local_owned_process_receipt.v1"
RECONCILIATION_HOLD_SCHEMA = "mastermind.local_lane_reconciliation_hold.v1"
DEFAULT_CAPTURE_LIMIT_BYTES = 1_048_576
MAX_CAPTURE_LIMIT_BYTES = 8_388_608
MAX_RECEIPT_FILE_BYTES = 1_048_576
MAX_RECEIPT_RECORD_BYTES = 800_000
MAX_RECEIPT_BACKUPS = 2
DEFAULT_MAX_ACTIVE = 2
DEFAULT_MAX_LOAD_RATIO = 0.70
DEFAULT_NICE = 10
MAX_CONFIGURED_ACTIVE = 32
# Hard host-safety fuse for one owned provider process group. 256 matches the
# reviewed census ceiling in the canonical Claude worker and is far above the
# historical external-lane cleanup counts while remaining well below the 908
# process storm observed during the Mini2 2026-10-03 watchdog incident.
MAX_OWNED_PROCESS_GROUP_MEMBERS = 256
OWNED_PROCESS_CENSUS_INTERVAL_SECONDS = 1.0
PROCESS_LIMIT_RETURNCODE = 78
MIN_LOAD_RATIO = 0.5
MAX_LOAD_RATIO = 1.5
MIN_NICE = 0
MAX_NICE = 19
_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class LaneRuntimeError(RuntimeError):
    """Base class for bounded local-lane safety failures."""


class OwnedProcessStartError(LaneRuntimeError):
    """Popen failed before successful exec; no owned process was returned.

    Only the immediate Popen OSError boundary may construct this verdict.
    Preserve a bounded errno without leaking argv, environment or paths.
    """
    def __init__(self, error_number: int | None):
        self.error_number = (error_number if type(error_number) is int
                             and 0 < error_number <= 65535 else None)
        super().__init__("owned_process_exec_not_started")


class LaneRuntimeConfigError(LaneRuntimeError):
    """A local safety override is malformed or outside reviewed bounds."""


class ProcessCensusError(LaneRuntimeError):
    """The process table or session identity could not be proven."""


_PROCESS_CENSUS_FAILURE_CODES = frozenset(('process_census_timeout', 'process_census_unavailable', 'process_census_nonzero', 'process_census_empty', 'process_census_pid_ambiguous', 'process_census_malformed', 'process_census_pid_mismatch', 'process_group_identity_invalid', 'process_session_identity_invalid', 'process_session_identity_permission_denied', 'process_signal_permission_denied', 'process_group_session_identity_mismatch', 'process_group_census_empty_while_leader_live', 'process_identity_permission_denied'))

def _runtime_failure_code(exc: BaseException) -> str | None:
    code = str(exc) if type(exc) is ProcessCensusError else ""
    return code if code in _PROCESS_CENSUS_FAILURE_CODES else None


@dataclass(frozen=True)
class LaneRuntimeConfig:
    max_active: int
    max_load_ratio: float
    nice: int


@dataclass(frozen=True)
class HostAdmissionSnapshot:
    allowed: bool
    active_count: int
    legacy_count: int
    json_locked_count: int
    stale_reaped: tuple[str, ...]
    max_active: int
    load1: float
    cpu_count: int
    load_ratio_limit: float
    reasons: tuple[str, ...]

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class LaneAdmissionRefused(LaneRuntimeError):
    def __init__(self, snapshot: HostAdmissionSnapshot):
        super().__init__(",".join(snapshot.reasons) or "lane_admission_refused")
        self.snapshot = snapshot


@dataclass(frozen=True)
class OwnedProcessResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    pid: int
    pgid: int
    cleanup: dict[str, Any]
    stdout_bytes: int = 0
    stderr_bytes: int = 0
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    owned_capture: dict[str, Any] | None = None
    structured_result: dict[str, Any] | None = None

    @property
    def cleanup_proven(self) -> bool:
        return cleanup_receipt_is_proven(self.cleanup)


_CURRENT_LOCK = threading.RLock()
_CURRENT_PROCESS: tuple[subprocess.Popen[str], int, str] | None = None
_SIGNAL_HANDLERS_INSTALLED = False
_UNPROVEN_CLEANUP_CALLBACK: Callable[[str], None] | None = None
_PS_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_label(label: str) -> str:
    value = str(label)
    if _LABEL_RE.fullmatch(value):
        return value
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]
    return f"redacted-{digest}"


def _parse_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise LaneRuntimeConfigError(f"{key.lower()}_invalid") from exc


def _parse_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise LaneRuntimeConfigError(f"{key.lower()}_invalid") from exc
    if not value or value != value or value in (float("inf"), float("-inf")):
        raise LaneRuntimeConfigError(f"{key.lower()}_invalid")
    return value


def parse_bounded_seconds(
    raw: str | int | float | None,
    *,
    default: float,
    minimum: float,
    maximum: float,
    key: str,
) -> float:
    """Parse a finite timeout without leaking caller-supplied text into errors."""
    candidate: str | int | float = default if raw is None or str(raw).strip() == "" else raw
    try:
        value = float(candidate)
    except (TypeError, ValueError) as exc:
        raise LaneRuntimeConfigError(f"{key.lower()}_invalid") from exc
    if value != value or value in (float("inf"), float("-inf")):
        raise LaneRuntimeConfigError(f"{key.lower()}_invalid")
    if value < minimum or value > maximum:
        raise LaneRuntimeConfigError(f"{key.lower()}_out_of_bounds")
    return value


def load_runtime_config(
    env: Mapping[str, str] | None = None,
    *,
    cpu_count: int | None = None,
) -> LaneRuntimeConfig:
    values = os.environ if env is None else env
    cpus = int(cpu_count or os.cpu_count() or 1)
    max_active = _parse_int(values, "LANE_MAX_ACTIVE", DEFAULT_MAX_ACTIVE)
    max_load_ratio = _parse_float(values, "LANE_MAX_LOAD_RATIO", DEFAULT_MAX_LOAD_RATIO)
    nice = _parse_int(values, "LANE_NICE", DEFAULT_NICE)
    active_ceiling = min(MAX_CONFIGURED_ACTIVE, max(1, cpus))
    if not 1 <= max_active <= active_ceiling:
        raise LaneRuntimeConfigError("lane_max_active_out_of_bounds")
    if not MIN_LOAD_RATIO <= max_load_ratio <= MAX_LOAD_RATIO:
        raise LaneRuntimeConfigError("lane_max_load_ratio_out_of_bounds")
    if not MIN_NICE <= nice <= MAX_NICE:
        raise LaneRuntimeConfigError("lane_nice_out_of_bounds")
    return LaneRuntimeConfig(
        max_active=max_active,
        max_load_ratio=max_load_ratio,
        nice=nice,
    )


def enforce_remote_first_lane_launch(
    base_dir: Path,
    env: Mapping[str, str] | None = None,
    *,
    hostname: str | None = None,
    requested_engines: Sequence[str] | None = None,
) -> dict[str, int | float] | None:
    """Bind lane admission to the physical host declared by hosts.json.

    host_pick/host_queue remain the placement owners. A remote marker is accepted
    only when the current physical hostname matches that registry entry. Direct
    seat execution is allowed only when the one local registry entry explicitly
    carries the lanes role; environment variables cannot override this policy.
    """
    values = os.environ if env is None else env
    registry = Path(base_dir) / "hosts.json"
    if not registry.is_file():
        return None
    try:
        document = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LaneRuntimeConfigError("hosts_registry_unreadable") from exc

    current_host = str(hostname or socket.gethostname()).split(".", 1)[0]
    requested = {
        str(value).strip().lower()
        for value in (requested_engines or ())
        if str(value).strip() and str(value).strip().lower() not in {"seat", "none"}
    }
    remote_key = str(values.get("LANE_REMOTE_HOST") or "").strip()
    if remote_key:
        entry = document.get(remote_key)
        if not isinstance(entry, dict):
            raise LaneRuntimeConfigError("remote_host_unknown")
        if entry.get("local") is True:
            raise LaneRuntimeConfigError("remote_host_points_to_local")
        roles = {str(x) for x in (entry.get("roles") or [])}
        if not roles.intersection({"lanes", "lanes-shadow"}):
            raise LaneRuntimeConfigError("remote_host_not_lane_role")
        raw_allowed_modes = entry.get("allowed_modes")
        if raw_allowed_modes is not None:
            if (
                not isinstance(raw_allowed_modes, list)
                or not all(isinstance(value, str) and value.strip() for value in raw_allowed_modes)
            ):
                raise LaneRuntimeConfigError("remote_host_allowed_modes_invalid")
            allowed_modes = {value.strip().lower() for value in raw_allowed_modes}
            if requested and not requested.issubset(allowed_modes):
                raise LaneRuntimeConfigError("remote_host_mode_not_allowed")
        expected = entry.get("hostnames")
        if not isinstance(expected, list) or not expected or not all(isinstance(x, str) and x for x in expected):
            raise LaneRuntimeConfigError("remote_host_identity_missing")
        if current_host not in expected:
            raise LaneRuntimeConfigError("remote_host_identity_mismatch")
        return None

    locals_ = [
        key
        for key, value in document.items()
        if not str(key).startswith("_")
        and isinstance(value, dict)
        and value.get("local") is True
    ]
    if len(locals_) != 1:
        raise LaneRuntimeConfigError("hosts_registry_local_identity_invalid")
    local_entry = document[locals_[0]]
    expected = local_entry.get("hostnames")
    if isinstance(expected, list) and expected and current_host not in expected:
        raise LaneRuntimeConfigError("local_host_identity_mismatch")
    roles = {str(x) for x in (local_entry.get("roles") or [])}
    raw_local_only = local_entry.get("local_only_engines") or []
    if not isinstance(raw_local_only, list) or not all(
        isinstance(value, str) and value.strip() for value in raw_local_only
    ):
        raise LaneRuntimeConfigError("local_only_engines_invalid")
    local_only = {value.strip().lower() for value in raw_local_only}
    if "lanes" not in roles and not requested.intersection(local_only):
        raise LaneRuntimeConfigError("direct_seat_launch_refused_use_remote_queue")
    max_active = local_entry.get("max_active")
    load_gate = local_entry.get("load_gate")
    cores = local_entry.get("cores")
    if (
        isinstance(max_active, bool)
        or not isinstance(max_active, int)
        or not 1 <= max_active <= min(MAX_CONFIGURED_ACTIVE, cores)
        or isinstance(cores, bool)
        or not isinstance(cores, int)
        or cores < 1
        or isinstance(load_gate, bool)
        or not isinstance(load_gate, (int, float))
        or not 0 < float(load_gate) <= float(cores) * MAX_LOAD_RATIO
    ):
        raise LaneRuntimeConfigError("local_host_policy_invalid")
    return {
        "max_active": max_active,
        "load_ratio_limit": float(load_gate) / float(cores),
    }

def _run_ps_lines(argv: Sequence[str], *, timeout: float) -> tuple[str, ...]:
    # On busy shared CI hosts, a read-only ps call can briefly stall behind IO.
    # Retry that single observation once, with a bounded extended timeout.
    # No process is signaled and a second failure remains effect-unknown.
    if timeout <= 0 or timeout > 8:
        raise ProcessCensusError("process_census_timeout")
    extended = max(timeout, min(8.0, timeout * 2))
    for attempt, budget in enumerate((timeout, extended)):
        try:
            probe = subprocess.run(
                list(argv),
                capture_output=True,
                text=True,
                timeout=budget,
                check=False,
                env=_PS_ENV,
            )
            break
        except subprocess.TimeoutExpired as exc:
            if attempt:
                raise ProcessCensusError("process_census_timeout") from exc
        except OSError as exc:
            raise ProcessCensusError("process_census_unavailable") from exc
    if probe.returncode != 0:
        raise ProcessCensusError("process_census_nonzero")
    lines = tuple(line.strip() for line in probe.stdout.splitlines() if line.strip())
    if not lines:
        raise ProcessCensusError("process_census_empty")
    return lines


def process_exists(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    lines = _run_ps_lines(
        ["/bin/ps", "-o", "pid=,stat=", "-p", str(pid)], timeout=2
    )
    if len(lines) != 1:
        raise ProcessCensusError("process_census_pid_ambiguous")
    fields = lines[0].split()
    if len(fields) != 2:
        raise ProcessCensusError("process_census_malformed")
    try:
        observed_pid = int(fields[0])
    except ValueError as exc:
        raise ProcessCensusError("process_census_malformed") from exc
    if observed_pid != pid:
        raise ProcessCensusError("process_census_pid_mismatch")
    return not fields[1].startswith("Z")


def _group_pids(pgid: int) -> tuple[int, ...]:
    if not isinstance(pgid, int) or pgid <= 0:
        raise ProcessCensusError("process_group_identity_invalid")
    lines = _run_ps_lines(
        ["/bin/ps", "-axo", "pid=,pgid=,stat="], timeout=3
    )
    found: list[int] = []
    for line in lines:
        fields = line.split()
        if len(fields) != 3:
            raise ProcessCensusError("process_census_malformed")
        try:
            pid, observed_group = int(fields[0]), int(fields[1])
        except ValueError as exc:
            raise ProcessCensusError("process_census_malformed") from exc
        state = fields[2]
        if not state:
            raise ProcessCensusError("process_census_malformed")
        if observed_group == pgid and not state.startswith("Z"):
            found.append(pid)
    return tuple(sorted(set(found)))


def _session_pids(expected_sid: int) -> tuple[int, ...]:
    """List live processes that still belong to the private owned session."""
    if not isinstance(expected_sid, int) or expected_sid <= 0:
        raise ProcessCensusError("process_session_identity_invalid")
    lines = _run_ps_lines(["/bin/ps", "-axo", "pid=,stat="], timeout=3)
    found: list[int] = []
    for line in lines:
        fields = line.split()
        if len(fields) != 2:
            raise ProcessCensusError("process_census_malformed")
        try:
            pid = int(fields[0])
        except ValueError as exc:
            raise ProcessCensusError("process_census_malformed") from exc
        state = fields[1]
        if not state:
            raise ProcessCensusError("process_census_malformed")
        if state.startswith("Z"):
            continue
        try:
            observed_sid = os.getsid(pid)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise ProcessCensusError("process_session_identity_permission_denied") from exc
        if observed_sid == expected_sid:
            found.append(pid)
    return tuple(sorted(set(found)))

def _wait_session_empty(expected_sid: int, seconds: float) -> tuple[int, ...]:
    deadline = time.monotonic() + max(0.0, seconds)
    residual = _session_pids(expected_sid)
    while residual and time.monotonic() < deadline:
        time.sleep(0.03)
        residual = _session_pids(expected_sid)
    return residual


def _signal_owned_session(
    expected_sid: int,
    leader_pid: int,
    signum: int,
) -> tuple[int, bool]:
    """Signal verified session members, descendants first and leader last."""
    members = sorted(_session_pids(expected_sid), key=lambda pid: pid == leader_pid)
    sent = 0
    for pid in members:
        if pid == os.getpid():
            return sent, False
        try:
            if os.getsid(pid) != expected_sid:
                return sent, False
            os.kill(pid, signum)
            sent += 1
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise ProcessCensusError("process_signal_permission_denied") from exc
    return sent, True

def _wait_group_empty(pgid: int, seconds: float) -> tuple[int, ...]:
    deadline = time.monotonic() + max(0.0, seconds)
    residual = _group_pids(pgid)
    while residual and time.monotonic() < deadline:
        time.sleep(0.03)
        residual = _group_pids(pgid)
    return residual


def _verified_group_members(expected_pgid: int) -> tuple[tuple[int, ...], bool]:
    """Return live members only when every observed member retains our session id."""
    verified: list[int] = []
    for pid in _group_pids(expected_pgid):
        try:
            observed_sid = os.getsid(pid)
        except ProcessLookupError:
            continue
        except PermissionError as exc:
            raise ProcessCensusError("process_session_identity_permission_denied") from exc
        if observed_sid != expected_pgid:
            return tuple(verified), False
        verified.append(pid)
    return tuple(verified), True


def _wait_owned_process_with_fuse(
    proc: subprocess.Popen[str], expected_pgid: int, timeout: float
) -> str:
    """Wait for one owned leader while bounding live process-group growth.

    The process group is the cheap in-run ownership census. Terminal cleanup
    still uses the wider session census so descendants cannot survive merely by
    changing process groups. Any ambiguous group/session identity fails closed.
    """
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return "timeout"
        try:
            proc.wait(
                timeout=min(OWNED_PROCESS_CENSUS_INTERVAL_SECONDS, remaining)
            )
        except subprocess.TimeoutExpired:
            pass
        else:
            return "completed"

        if time.monotonic() >= deadline:
            return "timeout"
        outcome = _owned_fuse_check(proc, expected_pgid)
        if outcome is not None:
            return outcome


def _owned_fuse_check(proc, expected_pgid):
    """One shared sync/async identity and growth decision; no altered policy."""
    members, identity_ok = _verified_group_members(expected_pgid)
    if not identity_ok:
        raise ProcessCensusError("process_group_session_identity_mismatch")
    if len(members) > MAX_OWNED_PROCESS_GROUP_MEMBERS:
        return "process_limit"
    if not members:
        if proc.poll() is not None:
            return "completed"
        raise ProcessCensusError("process_group_census_empty_while_leader_live")
    return None


def cleanup_receipt_is_proven(value: Mapping[str, Any]) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("census_proven") is True
        and value.get("identity_verified") is True
        and value.get("residual_count") == 0
        and value.get("status") in {"not_needed", "terminated"}
    )


def _kill_exact_leader(
    proc: subprocess.Popen[Any], *, grace: float
) -> tuple[bool, bool]:
    sent = False
    try:
        if proc.poll() is None:
            proc.kill()
            sent = True
    except ProcessLookupError:
        pass
    except PermissionError:
        return sent, False
    try:
        proc.wait(timeout=max(0.2, grace))
    except subprocess.TimeoutExpired:
        return sent, False
    return sent, proc.poll() is not None


def _unproven_cleanup_receipt(
    receipt: dict[str, Any],
    proc: subprocess.Popen[Any],
    error: BaseException,
    *,
    grace: float,
) -> dict[str, Any]:
    leader_kill_sent, leader_exit_observed = _kill_exact_leader(proc, grace=grace)
    receipt.update(
        {
            "status": "process_census_unproven",
            "identity_verified": False,
            "census_proven": False,
            "residual_count": None,
            "error_code": str(error) if str(error) else type(error).__name__,
            "leader_kill_sent": leader_kill_sent,
            "leader_exit_observed": leader_exit_observed,
        }
    )
    return receipt


def _terminate_verified_group(
    proc: subprocess.Popen[str],
    expected_pgid: int,
    *,
    grace: float,
    reason: str,
) -> dict[str, Any]:
    expected_sid = expected_pgid
    receipt: dict[str, Any] = {
        "status": "not_needed",
        "reason": reason,
        "sigterm_sent": False,
        "sigkill_sent": False,
        "identity_verified": False,
        "census_proven": False,
        "residual_count": None,
        "session_id": expected_sid,
        "sigterm_member_count": 0,
        "sigkill_member_count": 0,
        "error_code": None,
    }

    def direct_only() -> dict[str, Any]:
        receipt["status"] = "identity_mismatch_direct_only"
        receipt["identity_verified"] = False
        killed, exited = _kill_exact_leader(proc, grace=max(0.2, grace))
        receipt['leader_kill_sent'] = killed
        receipt['leader_exit_observed'] = exited
        try:
            residual = _session_pids(expected_sid)
        except ProcessCensusError as exc:
            return _unproven_cleanup_receipt(
                receipt, proc, exc, grace=max(0.2, grace)
            )
        receipt["census_proven"] = True
        receipt["residual_count"] = len(residual)
        receipt["error_code"] = "process_identity_mismatch"
        return receipt

    try:
        if expected_pgid != proc.pid:
            return direct_only()
        if process_exists(proc.pid):
            try:
                observed_pgid = os.getpgid(proc.pid)
                observed_sid = os.getsid(proc.pid)
            except ProcessLookupError:
                observed_pgid = expected_pgid
                observed_sid = expected_sid
            except PermissionError as exc:
                return _unproven_cleanup_receipt(
                    receipt, proc, ProcessCensusError("process_identity_permission_denied"),
                    grace=max(0.2, grace),
                )
            if observed_pgid != expected_pgid or observed_sid != expected_sid:
                return direct_only()
        members = _session_pids(expected_sid)
        if not members and proc.poll() is not None:
            receipt["identity_verified"] = True
            receipt["census_proven"] = True
            receipt["residual_count"] = 0
            return receipt
        receipt["identity_verified"] = True

        sent, identity_ok = _signal_owned_session(expected_sid, proc.pid, signal.SIGTERM)
        if not identity_ok:
            return direct_only()
        receipt["sigterm_member_count"] = sent
        receipt["sigterm_sent"] = sent > 0
        residual = _wait_session_empty(expected_sid, grace)
        if residual:
            sent, identity_ok = _signal_owned_session(expected_sid, proc.pid, signal.SIGKILL)
            if not identity_ok:
                return direct_only()
            receipt["sigkill_member_count"] = sent
            receipt["sigkill_sent"] = sent > 0
            residual = _wait_session_empty(expected_sid, max(1.0, grace * 4))
        try:
            proc.wait(timeout=max(0.2, grace))
        except subprocess.TimeoutExpired:
            killed, exited = _kill_exact_leader(proc, grace=2.0)
            receipt['leader_kill_sent'] = killed
            receipt['leader_exit_observed'] = exited
        residual = _session_pids(expected_sid)
        receipt["census_proven"] = True
        receipt["residual_count"] = len(residual)
        receipt["status"] = "terminated" if not residual else "residual_processes"
        return receipt
    except ProcessCensusError as exc:
        return _unproven_cleanup_receipt(
            receipt, proc, exc, grace=max(0.2, grace)
        )

def _set_current(proc: subprocess.Popen[str], pgid: int, label: str) -> None:
    global _CURRENT_PROCESS
    with _CURRENT_LOCK:
        if _CURRENT_PROCESS is not None:
            raise LaneRuntimeError("nested_owned_process_not_supported")
        _CURRENT_PROCESS = (proc, pgid, label)


def _clear_current(proc: subprocess.Popen[str]) -> None:
    global _CURRENT_PROCESS
    with _CURRENT_LOCK:
        if _CURRENT_PROCESS is not None and _CURRENT_PROCESS[0] is proc:
            _CURRENT_PROCESS = None


def cancel_current_owned_process(reason: str = "parent_exit") -> dict[str, Any] | None:
    with _CURRENT_LOCK:
        current = _CURRENT_PROCESS
    if current is None:
        return None
    proc, pgid, _label = current
    return _terminate_verified_group(proc, pgid, grace=1.0, reason=reason)


def settle_owned_process_session(
    proc: subprocess.Popen[Any], *, grace: float = 2.0, reason: str = "settle"
) -> dict[str, Any]:
    """Prove an externally spawned session-owned subprocess has no descendants.

    The caller must have created the process with start_new_session=True so
    pid == pgid == sid. This keeps cleanup and census authority in lane_runtime
    while wrappers such as slot.py retain their existing streaming semantics.
    """
    return _terminate_verified_group(
        proc, int(proc.pid), grace=float(grace), reason=reason
    )


def _notify_unproven_cleanup(
    receipt: Mapping[str, Any] | None, reason: str
) -> None:
    callback = _UNPROVEN_CLEANUP_CALLBACK
    if receipt is not None and not cleanup_receipt_is_proven(receipt) and callback is not None:
        callback(reason)


def install_signal_cleanup(
    on_unproven: Callable[[str], None] | None = None,
) -> None:
    global _SIGNAL_HANDLERS_INSTALLED, _UNPROVEN_CLEANUP_CALLBACK
    if on_unproven is not None:
        _UNPROVEN_CLEANUP_CALLBACK = on_unproven
    if _SIGNAL_HANDLERS_INSTALLED:
        return

    def handler(signum: int, _frame: Any) -> None:
        receipt = cancel_current_owned_process(reason=f"signal_{signum}")
        _notify_unproven_cleanup(receipt, "signal_cleanup_unproven")
        raise SystemExit(128 + signum)

    def atexit_cleanup() -> None:
        receipt = cancel_current_owned_process(reason="parent_exit")
        _notify_unproven_cleanup(receipt, "atexit_cleanup_unproven")

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, handler)
    atexit.register(atexit_cleanup)
    _SIGNAL_HANDLERS_INSTALLED = True

def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise LaneRuntimeError("short_write")
        view = view[written:]


def _regular_lstat(path: Path) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise LaneRuntimeError("unsafe_nonregular_path")
    return info


def _fsync_parent(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path.parent, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rotate_process_receipts(path: Path) -> None:
    for index in range(MAX_RECEIPT_BACKUPS, 0, -1):
        source = path if index == 1 else path.with_name(f"{path.name}.{index - 1}")
        destination = path.with_name(f"{path.name}.{index}")
        source_info = _regular_lstat(source)
        if source_info is None:
            continue
        destination_info = _regular_lstat(destination)
        if destination_info is not None:
            destination.unlink()
        os.replace(source, destination)
    _fsync_parent(path)


def _append_process_receipt(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(dict(record), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")
    if len(payload) > MAX_RECEIPT_RECORD_BYTES:
        raise LaneRuntimeError("process_receipt_record_too_large")
    current = _regular_lstat(path)
    if current is not None and current.st_size + len(payload) > MAX_RECEIPT_FILE_BYTES:
        _rotate_process_receipts(path)
    flags = (
        os.O_WRONLY
        | os.O_APPEND
        | os.O_CREAT
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise LaneRuntimeError("process_receipt_path_unsafe")
        visible = path.lstat()
        if (visible.st_dev, visible.st_ino) != (info.st_dev, info.st_ino):
            raise LaneRuntimeError("process_receipt_identity_mismatch")
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_parent(path)


# --- owned private file capture (opt-in) ------------------------------------
# Fixed bounded stdout/stderr/result file capture for ONE owned process of the
# original runner.  This is capture mechanics on the same original handle, not
# a second owner, queue, callback registry, lease producer or restart path.
# Paths are fixed under the existing private run_dir; callers never name files.

OWNED_CAPTURE_SCHEMA = "mastermind.local_owned_capture_files.v1"
_OWNED_CAPTURE_LAYOUT = (
    ("stdout", "logs", "stdout.json"),
    ("stderr", "logs", "stderr.log"),
    ("result", "output", "result.json"),
)
_OWNED_CAPTURE_DIR_MODE = 0o700
_OWNED_CAPTURE_FILE_MODE = 0o600
_OWNED_CAPTURE_SCHEMA_JSON_MAX_BYTES = 262_144
_OWNED_RESULT_STDOUT_CAP_BYTES = MAX_CAPTURE_LIMIT_BYTES


class _OwnedCaptureResultParse(LaneRuntimeError):
    """Typed provider-result refusal; never invents success from bad stdout."""


def _parse_owned_result_schema(result_schema_json: str):
    """Parse the real prepared result schema once, before Popen."""
    if type(result_schema_json) is not str or not result_schema_json:
        raise LaneRuntimeConfigError("owned_capture_result_schema_invalid")
    if (len(result_schema_json.encode("utf-8"))
            > _OWNED_CAPTURE_SCHEMA_JSON_MAX_BYTES):
        raise LaneRuntimeConfigError("owned_capture_result_schema_too_large")
    try:
        schema = json.loads(result_schema_json)
    except (ValueError, TypeError) as exc:
        raise LaneRuntimeConfigError("owned_capture_result_schema_invalid") from exc
    if not isinstance(schema, dict):
        raise LaneRuntimeConfigError("owned_capture_result_schema_invalid")
    try:
        from control_plane.claude_subscription_worker import ClaudeSubscriptionWorkerAdapter
        from control_plane.codex_worker import validate_json_schema
    except ImportError as exc:
        raise LaneRuntimeConfigError("owned_capture_parser_unavailable") from exc
    except Exception as exc:
        raise LaneRuntimeConfigError("owned_capture_result_schema_invalid") from exc
    return schema


def _owned_capture_parse_cli_result(raw: bytes, schema):
    from control_plane.claude_subscription_worker import (
        ClaudeSubscriptionWorkerAdapter, ClaudeSubscriptionWorkerError)
    from control_plane.codex_worker import ResultValidationError
    try:
        return ClaudeSubscriptionWorkerAdapter._parse_cli_result(raw, schema)
    except (ResultValidationError, ClaudeSubscriptionWorkerError) as exc:
        raise _OwnedCaptureResultParse(str(exc)) from exc


class _PinnedPrivateDir:
    """One opened private directory pinned by identity on a retained fd."""

    def __init__(self, *, fd: int, name: str, parent_fd: int | None,
                 identity: tuple[int, int], created: bool):
        self.fd = fd
        self.name = name
        self.parent_fd = parent_fd
        self.reservation = None
        self.identity = (int(identity[0]), int(identity[1]))
        self.created = bool(created)

    def verify(self, euid: int) -> None:
        if self.reservation is not None:
            self.reservation.verify_run_chain()
        info = os.fstat(self.fd)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != euid
                or stat.S_IMODE(info.st_mode) & 0o077
                or (info.st_dev, info.st_ino) != self.identity):
            raise LaneRuntimeError("owned_capture_directory_changed")
        if self.parent_fd is not None:
            visible = os.stat(self.name, dir_fd=self.parent_fd,
                              follow_symlinks=False)
            if (visible.st_dev, visible.st_ino) != self.identity:
                raise LaneRuntimeError("owned_capture_directory_replaced")


class _OwnedCaptureFile:
    """One exclusive private capture file retained open on the same handle.

    The collector thread of the original runner is the only writer.  Sealing,
    readback and close happen on the original controller thread only after the
    collector has provably finished; an uncertain collector keeps every
    retained resource open and the capture stays unqualified.
    """

    def __init__(self, *, fd: int, parent: _PinnedPrivateDir, name: str,
                 identity: tuple[int, int], limit_bytes: int, euid: int):
        self.fd = fd
        self.parent = parent
        self.name = name
        self.identity = (int(identity[0]), int(identity[1]))
        self.limit_bytes = int(limit_bytes)
        self.euid = int(euid)
        self._lock = threading.Lock()
        self._written = 0
        self._hash = hashlib.sha256()
        self._overcap = False
        self._error_code: str | None = None
        self._state = "reserved"
        self.close_confirmed = None

    # -- collector thread only -------------------------------------------------
    def note_streaming(self) -> None:
        with self._lock:
            if self._state == "reserved":
                self._state = "streaming"

    def tee(self, payload: bytes) -> None:
        """Tee one drained chunk into the retained fd, bounded by the cap.

        A write failure, identity change or overcap never stops the pipe
        drain: the collector keeps reading and hashing the full stream.
        """
        with self._lock:
            if self.fd is None or self._state == "sealed":
                return
            room = self.limit_bytes - self._written
            if room <= 0:
                self._overcap = True
                return
            take = payload if len(payload) <= room else payload[:room]
            try:
                self.parent.verify(self.euid)
                info = os.fstat(self.fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or (info.st_dev, info.st_ino) != self.identity
                        or info.st_uid != self.euid
                        or stat.S_IMODE(info.st_mode) != _OWNED_CAPTURE_FILE_MODE):
                    self._error_code = "owned_capture_identity_changed"
                    return
                visible = os.stat(self.name, dir_fd=self.parent.fd,
                                  follow_symlinks=False)
                if (visible.st_dev, visible.st_ino) != self.identity:
                    self._error_code = "owned_capture_path_replaced"
                    return
                _write_all(self.fd, take)
            except (OSError, LaneRuntimeError):
                self._error_code = "owned_capture_write_failed"
                return
            self._written += len(take)
            self._hash.update(take)
            if len(payload) > room:
                self._overcap = True

    # -- either thread ---------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "written": self._written,
                "overcap": self._overcap,
                "error_code": self._error_code,
            }

    def mark_retained_unknown(self) -> None:
        with self._lock:
            if self._state != "sealed":
                self._state = "retained_unknown"

    def release_fd(self) -> int | None:
        with self._lock:
            fd = self.fd
            self.fd = None
            if self._state not in ("sealed", "retained_unknown"):
                self._state = "closed"
        return fd

    # -- original controller thread, after proof the collector finished --------
    def seal(self) -> tuple[bytes, str | None]:
        """fsync, read back and verify one finished stream file, then close.

        Returns the exact stored bytes and an error code (``None`` when the
        stored bytes may still qualify).  The caller must have proven the
        collector thread dead; no fd is closed while a live collector owns it.
        """
        error_code = None
        content = b""
        try:
            os.fsync(self.fd)
        except OSError:
            error_code = "owned_capture_fsync_failed"
        if error_code is None:
            try:
                os.lseek(self.fd, 0, os.SEEK_SET)
                chunks: list[bytes] = []
                remaining = self.limit_bytes + 1
                while remaining > 0:
                    part = os.read(self.fd, min(65_536, remaining))
                    if not part:
                        break
                    chunks.append(part)
                    remaining -= len(part)
                content = b"".join(chunks)
                if len(content) > self.limit_bytes:
                    error_code = "owned_capture_file_overgrown"
            except OSError:
                error_code = "owned_capture_readback_failed"
        try:
            info = os.fstat(self.fd)
            visible = os.stat(self.name, dir_fd=self.parent.fd,
                              follow_symlinks=False)
            self.parent.verify(self.euid)
            identity_ok = (
                stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and (info.st_dev, info.st_ino) == self.identity
                and info.st_uid == self.euid
                and stat.S_IMODE(info.st_mode) == _OWNED_CAPTURE_FILE_MODE
                and (visible.st_dev, visible.st_ino) == self.identity
            )
        except (OSError, LaneRuntimeError):
            identity_ok = False
        if not identity_ok and error_code is None:
            error_code = "owned_capture_identity_changed"
        try:
            os.close(self.fd)
            self.close_confirmed = True
        except OSError:
            self.close_confirmed = False
            # The close outcome is unknown; never repeat this numeric FD.
            error_code = error_code or 'owned_capture_close_unconfirmed'
        with self._lock:
            self.fd = None
            self._state = 'sealed' if error_code is None else 'unqualified'
        return content, error_code


def _open_private_dir_child(parent_fd: int, name: str, euid: int) -> _PinnedPrivateDir:
    """Open an existing private child directory or create one, never repair."""
    created = False
    try:
        os.mkdir(name, _OWNED_CAPTURE_DIR_MODE, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise LaneRuntimeError("owned_capture_directory_unavailable") from exc

    def remove_created() -> None:
        # An unsuccessful open supplies no pinned identity for safe deletion.
        # Retain unknown names; setup failure never authorizes their removal.
        return

    try:
        fd = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                     | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
                     dir_fd=parent_fd)
    except OSError as exc:
        remove_created()
        raise LaneRuntimeError("owned_capture_directory_unavailable") from exc
    try:
        info = os.fstat(fd)
        visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode)
                or info.st_uid != euid
                or stat.S_IMODE(info.st_mode) & 0o077
                or (visible.st_dev, visible.st_ino) != (info.st_dev, info.st_ino)):
            raise LaneRuntimeError("owned_capture_directory_unsafe")
    except BaseException:
        os.close(fd)
        remove_created()
        raise
    return _PinnedPrivateDir(fd=fd, name=name, parent_fd=parent_fd,
                             identity=(info.st_dev, info.st_ino), created=created)


class _OwnedCaptureReservation:
    """Fixed-path private capture reserved before Popen on ONE original handle.

    The three files are exclusive, private, non-inheritable and created before
    Popen under the existing private run_dir.  Every directory and file is
    pinned by opened identity on retained fds of this same handle.  A refused
    or failed setup closes exactly what this attempt created and never unlinks
    unknown or reused names; any pre-existing file refuses (no replay).
    """

    def __init__(self, run_dir: str, schema, schema_json: str,
                 limit_bytes: int, euid: int, assignment=None):
        self.assignment = assignment
        self.run_dir = run_dir
        self.result_schema = schema
        self.result_schema_json = schema_json
        self.result_schema_sha256 = hashlib.sha256(
            schema_json.encode("utf-8")).hexdigest()
        self.limit_bytes = int(limit_bytes)
        self.euid = int(euid)
        self.run_dir_fd: int | None = None
        self.run_chain = []
        self.terminal_stdout = None
        self.terminal_stderr = None
        self.expected_identity = {}
        self.dirs: dict[str, _PinnedPrivateDir] = {}
        self.files: dict[str, _OwnedCaptureFile] = {}
        self.paths: dict[str, str] = {}
        self.retained_unknown = False
        self._closed = False

    @classmethod
    def create(cls, run_dir, *, result_schema_json: str, limit_bytes: int, assignment=None):
        if (os.open not in os.supports_dir_fd
                or os.mkdir not in os.supports_dir_fd
                or os.stat not in os.supports_follow_symlinks
                or not hasattr(os, "geteuid")):
            raise LaneRuntimeError("owned_capture_platform_unqualified")
        run_dir = os.fspath(run_dir)
        if (type(run_dir) is not str or not run_dir.startswith("/")
                or "\x00" in run_dir or ".." in run_dir.split("/")
                or not run_dir.split("/")[-1]):
            raise LaneRuntimeConfigError("owned_capture_run_dir_invalid")
        schema = _parse_owned_result_schema(result_schema_json)
        euid = os.geteuid()
        if assignment is not None:
            assignment = json.loads(json.dumps(assignment, allow_nan=False))
            if (type(assignment) is not dict or set(assignment) != {'run', 'store', 'control_uid', 'worker_gid'}
                    or type(assignment['control_uid']) is not int or assignment['control_uid'] <= 0
                    or assignment['control_uid'] == euid
                    or assignment['worker_gid'] != os.getegid()):
                raise LaneRuntimeError('owned_capture_assignment_invalid')
            fields = {'path', 'device', 'inode', 'mode', 'uid', 'gid', 'mtime_ns'}
            for name in ('run', 'store'):
                if (type(assignment[name]) is not dict or set(assignment[name]) != fields
                        or any(type(assignment[name][key]) is not int for key in fields - {'path'})):
                    raise LaneRuntimeError('owned_capture_assignment_invalid')
            if (assignment['run']['path'] != run_dir
                    or str(Path(run_dir).parent) != assignment['store']['path']):
                raise LaneRuntimeError('owned_capture_assignment_invalid')
        reservation = cls(run_dir, schema, result_schema_json, limit_bytes, euid, assignment)
        try:
            root_fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            info = os.fstat(root_fd)
            reservation.run_chain.append((root_fd, None, '/', (info.st_dev, info.st_ino)))
            for component in run_dir.split('/')[1:]:
                parent_fd = reservation.run_chain[-1][0]
                fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                             os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                info = os.fstat(fd)
                reservation.run_chain.append((fd, parent_fd, component,
                                               (info.st_dev, info.st_ino)))
            run_fd = reservation.run_chain[-1][0]
            reservation.run_dir_fd = run_fd
            reservation.verify_run_chain()
        except (OSError, LaneRuntimeError) as exc:
            reservation._close_remaining_fds()
            if isinstance(exc, LaneRuntimeError): raise
            raise LaneRuntimeError("owned_capture_run_dir_unavailable") from exc
        try:
            info = os.fstat(run_fd)
            if (not stat.S_ISDIR(info.st_mode) or (assignment is None and (
                    info.st_uid != euid or stat.S_IMODE(info.st_mode) & 0o077))):
                raise LaneRuntimeError("owned_capture_run_dir_unsafe")
            reservation.run_dir_fd = run_fd
            try:
                for _key, dirname, _filename in _OWNED_CAPTURE_LAYOUT:
                    if dirname not in reservation.dirs:
                        reservation.dirs[dirname] = _open_private_dir_child(
                            run_fd, dirname, euid)
                        reservation.dirs[dirname].reservation = reservation
            except BaseException:
                reservation.abort()
                raise
            try:
                for key, dirname, filename in _OWNED_CAPTURE_LAYOUT:
                    pinned = reservation.dirs[dirname]
                    try:
                        # O_RDWR: the same retained handle must serve the
                        # sealed readback verification and the single result
                        # publication read-back later on.
                        fd = os.open(
                            filename,
                            os.O_RDWR | os.O_CREAT | os.O_EXCL
                            | getattr(os, "O_NOFOLLOW", 0)
                            | getattr(os, "O_CLOEXEC", 0),
                            _OWNED_CAPTURE_FILE_MODE,
                            dir_fd=pinned.fd,
                        )
                    except FileExistsError as exc:
                        # Any existing file refuses: no replay into it, and an
                        # unknown pre-existing name is never unlinked.
                        raise LaneRuntimeError("owned_capture_file_exists") from exc
                    except OSError as exc:
                        raise LaneRuntimeError("owned_capture_file_unavailable") from exc
                    try:
                        info = os.fstat(fd)
                        visible = os.stat(filename, dir_fd=pinned.fd,
                                          follow_symlinks=False)
                        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                                or stat.S_IMODE(info.st_mode) != _OWNED_CAPTURE_FILE_MODE
                                or info.st_uid != euid
                                or (visible.st_dev, visible.st_ino)
                                != (info.st_dev, info.st_ino)):
                            raise LaneRuntimeError("owned_capture_file_unsafe")
                    except BaseException:
                        # Close and remove exactly this just-created exclusive
                        # file; a replaced or unknown name is never unlinked.
                        try:
                            observed = os.fstat(fd)
                        except OSError:
                            observed = None
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                        if observed is not None:
                            try:
                                visible = os.stat(filename, dir_fd=pinned.fd,
                                                  follow_symlinks=False)
                                if (visible.st_dev, visible.st_ino) == (
                                        observed.st_dev, observed.st_ino):
                                    os.unlink(filename, dir_fd=pinned.fd)
                            except OSError:
                                pass
                        raise
                    reservation.files[key] = _OwnedCaptureFile(
                        fd=fd, parent=pinned, name=filename,
                        identity=(info.st_dev, info.st_ino),
                        limit_bytes=limit_bytes, euid=euid)
                    reservation.paths[key] = run_dir + "/" + dirname + "/" + filename
            except BaseException:
                reservation.abort()
                raise
            for cap in reservation.files.values():
                os.fsync(cap.fd)
            for directory in reservation.dirs.values():
                directory.verify(euid)
                os.fsync(directory.fd)
            reservation.verify_run_chain()
            os.fsync(run_fd)
            return reservation
        except BaseException:
            reservation.abort()
            raise

    def verify_run_chain(self):
        if self._closed or not self.run_chain:
            raise LaneRuntimeError('owned_capture_run_dir_not_retained')
        for fd, parent_fd, name, identity in self.run_chain:
            observed = os.fstat(fd)
            visible = (os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                       if parent_fd is not None else os.stat('/', follow_symlinks=False))
            if (not stat.S_ISDIR(observed.st_mode)
                    or (observed.st_dev, observed.st_ino) != identity
                    or (visible.st_dev, visible.st_ino) != identity):
                raise LaneRuntimeError('owned_capture_run_dir_replaced')
        run = os.fstat(self.run_chain[-1][0])
        if self.assignment is None:
            if run.st_uid != self.euid or stat.S_IMODE(run.st_mode) & 0o077:
                raise LaneRuntimeError('owned_capture_run_dir_unsafe')
        else:
            store = os.fstat(self.run_chain[-2][0])
            for name, info, mode in (('run', run, 0o770), ('store', store, 0o750)):
                expected = self.assignment[name]
                actual = dict(device=info.st_dev, inode=info.st_ino,
                    mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
                if (any(actual[key] != expected[key] for key in actual)
                        or actual['uid'] != self.assignment['control_uid']
                        or actual['gid'] != self.assignment['worker_gid'] or actual['mode'] != mode):
                    raise LaneRuntimeError('owned_capture_assignment_changed')

    def describe(self) -> dict[str, Any]:
        return {
            "schema": OWNED_CAPTURE_SCHEMA,
            "run_dir": self.run_dir,
            "limit_bytes": self.limit_bytes,
            "result_schema_sha256": self.result_schema_sha256,
            "assignment": self.assignment,
            "files": {
                key: {
                    "path": self.paths[key],
                    "device": cap.identity[0],
                    "inode": cap.identity[1],
                    "parent_device": cap.parent.identity[0],
                    "parent_inode": cap.parent.identity[1],
                }
                for key, cap in self.files.items()
            },
        }

    def _close_remaining_fds(self) -> bool:
        closed = True
        for pinned in self.dirs.values():
            try:
                os.close(pinned.fd)
            except OSError:
                closed = False
        self.dirs.clear()
        for fd, _, _, _ in reversed(self.run_chain):
            try: os.close(fd)
            except OSError: closed = False
        self.run_chain.clear()
        self.run_dir_fd = None
        self._closed = True
        if not closed: self.retained_unknown = True
        return closed

    def abort(self) -> None:
        """Pre-spawn rollback: close retained fds, remove exactly the files
        this attempt created.  Unknown, replaced or reused names, and any
        pre-existing directory, are never touched."""
        if self._closed:
            return
        for cap in self.files.values():
            fd = cap.release_fd()
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                visible = os.stat(cap.name, dir_fd=cap.parent.fd,
                                  follow_symlinks=False)
                if (visible.st_dev, visible.st_ino) == cap.identity:
                    os.unlink(cap.name, dir_fd=cap.parent.fd)
            except OSError:
                pass
        self.files.clear()
        for pinned in self.dirs.values():
            if pinned.created:
                try:
                    info = os.fstat(pinned.fd)
                    visible = os.stat(pinned.name, dir_fd=pinned.parent_fd, follow_symlinks=False)
                    if (info.st_dev, info.st_ino) == pinned.identity and (
                            visible.st_dev, visible.st_ino) == pinned.identity:
                        os.rmdir(pinned.name, dir_fd=pinned.parent_fd)
                except OSError:
                    pass
        self._close_remaining_fds()

    def close_fds_only(self) -> None:
        """Post-spawn rollback with no unlink: the run happened, so the
        exclusive empty files stay bound to this run_dir (no replay)."""
        if self._closed:
            return
        for cap in self.files.values():
            fd = cap.release_fd()
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.files.clear()
        self._close_remaining_fds()

    def _verify_result_file(self):
        cap = self.files['result']
        cap.parent.verify(self.euid)
        info = os.fstat(cap.fd)
        visible = os.stat(cap.name, dir_fd=cap.parent.fd, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or (info.st_dev, info.st_ino) != cap.identity
                or (visible.st_dev, visible.st_ino) != cap.identity
                or info.st_uid != self.euid or stat.S_IMODE(info.st_mode) != 0o600):
            raise LaneRuntimeError('owned_capture_result_identity_changed')
        return info

    def _publish_result_file(self, payload: bytes) -> str | None:
        cap = self.files['result']
        try:
            if self._verify_result_file().st_size != 0:
                return 'result_identity_changed'
            _write_all(cap.fd, payload)
            os.fsync(cap.fd)
            os.lseek(cap.fd, 0, os.SEEK_SET)
            content = bytearray()
            while len(content) <= len(payload):
                part = os.read(cap.fd, min(65536, len(payload) + 1 - len(content)))
                if not part: break
                content.extend(part)
            self._verify_result_file()
            cap.parent.verify(self.euid)
            os.fsync(cap.parent.fd)
            self._verify_result_file()
            if bytes(content) != payload:
                raise LaneRuntimeError('owned_capture_result_readback_changed')
            return None
        except (OSError, LaneRuntimeError) as exc:
            # Preserve original failed bytes and identities for reconciliation.
            # A mismatched readback never creates an empty state for retry.
            return ('result_identity_changed' if 'identity_changed' in str(exc)
                    else 'result_write_failed')

    def finalize(self, stdout_collector, stderr_collector, *, cleanup,
                 returncode: int, timed_out: bool, cancelled: bool = False):
        """Seal files after collector joins, publish the qualified result.

        Returns ``(capture_block, structured_result)``.  Any overcap, write
        failure, identity change, missing EOF or durability failure keeps the
        capture unqualified (and the existing reconciliation hold via the
        cleanup flags).  The result file stays empty unless every file, the
        full-stream hash and the original cleanup are proven first.
        """
        block = self.describe()
        records: dict[str, dict[str, Any]] = {}
        contents: dict[str, bytes | None] = {}
        for key, collector in (("stdout", stdout_collector),
                               ("stderr", stderr_collector)):
            summary = collector.capture_summary()
            record: dict[str, Any] = {
                "path": self.paths[key],
                "device": self.files[key].identity[0],
                "inode": self.files[key].identity[1],
                "stream_bytes": summary.get("total"),
                "stream_sha256": summary.get("stream_sha256"),
                "file_bytes": None,
                "file_sha256": None,
                "overcap": bool(summary.get("overcap")),
                "complete": False,
                "error_code": None,
                "sealed": False,
            }
            records[key] = record
            contents[key] = None
            if summary.get("live"):
                # Uncertain collector thread: every retained resource stays
                # open, the capture stays unqualified, nothing is retried.
                self.files[key].mark_retained_unknown()
                self.retained_unknown = True
                record["error_code"] = "owned_capture_collector_live"
                continue
            content, error_code = self.files[key].seal()
            record["sealed"] = True
            record["file_bytes"] = len(content)
            record["file_sha256"] = hashlib.sha256(content).hexdigest()
            # the tee-side failure (write/identity/overcap) and the seal-side
            # failure (fsync/readback/durability) are both refusals
            record["error_code"] = error_code or summary.get("error_code")
            complete = (
                record['error_code'] is None
                and summary.get("eof") is True
                and summary.get("stream_error") is None
                and not record["overcap"]
                and summary.get("stream_sha256") is not None
                and record["file_bytes"] == summary.get("total")
                and record["file_sha256"] == summary.get("stream_sha256")
            )
            record["complete"] = complete
            if complete:
                contents[key] = content
        if not self.retained_unknown and "logs" in self.dirs:
            try:
                self.dirs["logs"].verify(self.euid)
                os.fsync(self.dirs["logs"].fd)
            except (OSError, LaneRuntimeError):
                for key in ("stdout", "stderr"):
                    if records[key]["sealed"] and records[key]["error_code"] is None:
                        records[key]["error_code"] = "owned_capture_dir_sync_failed"
                        records[key]["complete"] = False
                        contents[key] = None
        session = None
        usage: dict[str, Any] = {}
        structured: dict[str, Any] | None = None
        reason: str | None
        stdout_ok = records["stdout"]["complete"]
        stderr_ok = records["stderr"]["complete"]
        if not (stdout_ok and stderr_ok):
            reason = "capture_unqualified"
        elif not cleanup_receipt_is_proven(cleanup):
            reason = "cleanup_unproven"
        elif cancelled:
            reason = "cancelled"
        elif timed_out:
            reason = "timed_out"
        elif int(returncode) != 0:
            reason = "nonzero_exit"
        else:
            reason = None
        result_record: dict[str, Any] = {
            "path": self.paths["result"],
            "device": self.files["result"].identity[0],
            "inode": self.files["result"].identity[1],
            "state": "not_published",
            "reason": None,
            "bytes": 0,
            "sha256": None,
        }
        if reason is None:
            try:
                structured, session, usage = _owned_capture_parse_cli_result(
                    contents["stdout"], self.result_schema)
                for field, expected in self.expected_identity.items():
                    if field in structured and structured[field] != expected:
                        raise _OwnedCaptureResultParse("result identity " + field + " does not match launch")
            except _OwnedCaptureResultParse as exc:
                structured = None
                reason = "parse_refused:" + str(exc)
            else:
                try:
                    payload = (
                        json.dumps(structured, sort_keys=True,
                                   separators=(",", ":"), ensure_ascii=False,
                                   allow_nan=False).encode("utf-8") + b"\n")
                except (TypeError, ValueError, RecursionError) as exc:
                    structured = None
                    reason = "result_not_canonical:" + type(exc).__name__
                else:
                    if len(payload) > self.limit_bytes:
                        structured = None
                        reason = "result_too_large"
                    else:
                        failure = self._publish_result_file(payload)
                        if failure is not None:
                            structured = None
                            session = None
                            usage = {}
                            reason = failure
                        else:
                            result_record["state"] = "published"
                            result_record["bytes"] = len(payload)
                            result_record["sha256"] = hashlib.sha256(
                                payload).hexdigest()
        result_record["reason"] = reason
        block["stdout_file_complete"] = records["stdout"]["complete"]
        block["stderr_file_complete"] = records["stderr"]["complete"]
        block["stdout"] = records["stdout"]
        block["stderr"] = records["stderr"]
        block["result"] = result_record
        block["provider_observations"] = (
            None if result_record["state"] != "published"
            else {"session_id": session, "usage": usage, "authority": False})
        result_complete = False
        files_closed = False
        if not self.retained_unknown:
            content, error = self.files['result'].seal()
            expected = (json.dumps(structured, sort_keys=True, separators=(',', ':'),
                        ensure_ascii=False, allow_nan=False).encode() + b'\n'
                        if result_record['state'] == 'published' else b'')
            result_complete = error is None and content == expected and reason not in {
                'result_write_failed', 'result_identity_changed'}
            if not result_complete:
                structured = None
                result_record['state'] = 'unqualified'
                result_record['reason'] = reason if reason in {'result_write_failed', 'result_identity_changed'} else (error or 'result_readback_unconfirmed')
            try:
                self.dirs['output'].verify(self.euid)
                os.fsync(self.dirs['output'].fd)
                self.verify_run_chain()
                os.fsync(self.run_dir_fd)
            except (OSError, LaneRuntimeError):
                result_complete = False
                structured = None
                result_record['state'] = 'unqualified'
                result_record['reason'] = 'result_parent_sync_unconfirmed'
            fd = self.files["result"].release_fd()
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            files_closed = all(cap.close_confirmed is True for cap in self.files.values())
            self.files.clear()
            closed = self._close_remaining_fds()
            if not closed:
                result_complete = False
                structured = None
                result_record['state'] = 'unqualified'
                result_record['reason'] = 'capture_directory_close_unconfirmed'
        block['file_descriptors_closed'] = files_closed and not self.retained_unknown
        if not block['file_descriptors_closed']:
            result_complete = False
            structured = None
            result_record['state'] = 'unqualified'
            result_record['reason'] = result_record['reason'] or 'capture_file_close_unconfirmed'
        block['result_file_complete'] = result_complete
        if result_record['state'] != 'published':
            block['provider_observations'] = None
        self.terminal_stdout = contents['stdout']
        self.terminal_stderr = contents['stderr']
        return block, structured


def owned_capture_paths(owner) -> dict[str, str]:
    """Fixed capture paths actually reserved on THIS original handle.

    Keyed exactly as the START assembler's capture-path contract
    (``stdout_path``/``stderr_path``/``result_path``).
    """
    _require_owned_execution(owner)
    reservation = getattr(owner, "_capture_reservation", None)
    if reservation is None or reservation._closed:
        raise LaneRuntimeError("owned_capture_not_reserved")
    return {
        "stdout_path": reservation.paths["stdout"],
        "stderr_path": reservation.paths["stderr"],
        "result_path": reservation.paths["result"],
    }


def validate_owned_capture_live(owner) -> dict[str, Any]:
    """Fixed live-owner validator for pinned capture files before START.

    Requires every pinned file to still exist at its pinned private parent
    with the pinned identity, exact 0600 mode, this owner's euid, and a
    retained fd still denoting that exact inode.  Path strings alone never
    satisfy this: START may claim live bound output ownership only, never a
    completed result.
    """
    _require_owned_execution(owner)
    reservation = getattr(owner, "_capture_reservation", None)
    if reservation is None or reservation._closed:
        raise LaneRuntimeError("owned_capture_not_reserved")
    euid = os.geteuid()
    verified: dict[str, Any] = {}
    for key, path_key in (("stdout", "stdout_path"),
                          ("stderr", "stderr_path"),
                          ("result", "result_path")):
        cap = reservation.files.get(key)
        if cap is None or cap.fd is None:
            raise LaneRuntimeError("owned_capture_file_not_retained")
        try:
            info = os.fstat(cap.fd)
            visible = os.stat(cap.name, dir_fd=cap.parent.fd,
                              follow_symlinks=False)
            cap.parent.verify(euid)
        except (OSError, LaneRuntimeError) as exc:
            raise LaneRuntimeError("owned_capture_file_missing") from exc
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or (info.st_dev, info.st_ino) != cap.identity
                or (visible.st_dev, visible.st_ino) != cap.identity
                or info.st_uid != euid
                or stat.S_IMODE(info.st_mode) != _OWNED_CAPTURE_FILE_MODE):
            raise LaneRuntimeError("owned_capture_identity_changed")
        if key == 'result' and info.st_size != 0:
            raise LaneRuntimeError('owned_capture_result_not_empty')
        verified[path_key] = {
            "path": reservation.paths[key],
            "device": int(info.st_dev),
            "inode": int(info.st_ino),
            "size": int(info.st_size),
        }
    return {
        "schema": OWNED_CAPTURE_SCHEMA,
        "run_dir": reservation.run_dir,
        "files": verified,
    }

# --- end owned private file capture ------------------------------------------


class _BoundedStreamCollector:
    """Drain one child pipe without allowing output volume to grow storage."""

    def __init__(self, stream: Any, limit_bytes: int, name: str,
                 capture_file: "_OwnedCaptureFile | None" = None):
        self.stream = stream
        self.limit_bytes = int(limit_bytes)
        self.name = name
        self.capture_file = capture_file
        self.total_bytes = 0
        self.capture_hash = hashlib.sha256()
        self.tail = bytearray()
        self.eof = False
        self.error_code: str | None = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._consume,
            name=f"lane-{name}-collector",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def _consume(self) -> None:
        try:
            while True:
                chunk = self.stream.read(65_536)
                if not chunk:
                    with self._lock:
                        self.eof = True
                    return
                if not isinstance(chunk, (bytes, bytearray)):
                    raise LaneRuntimeError("owned_output_stream_not_binary")
                payload = bytes(chunk)
                if self.capture_file is not None:
                    self.capture_file.tee(payload)
                with self._lock:
                    self.total_bytes += len(payload)
                    self.capture_hash.update(payload)
                    if len(payload) >= self.limit_bytes:
                        self.tail[:] = payload[-self.limit_bytes :]
                    else:
                        self.tail.extend(payload)
                        overflow = len(self.tail) - self.limit_bytes
                        if overflow > 0:
                            del self.tail[:overflow]
        except (OSError, ValueError, LaneRuntimeError) as exc:
            with self._lock:
                self.error_code = type(exc).__name__
        finally:
            try:
                self.stream.close()
            except (OSError, ValueError):
                pass

    def complete_digest(self):
        with self._lock:
            return self.capture_hash.hexdigest() if self.eof and self.error_code is None else None

    def capture_summary(self) -> dict[str, Any]:
        file = self.capture_file
        if file is None:
            return {"opted": False, "live": False, "eof": False, "total": 0,
                    "stream_error": None, "stream_sha256": None,
                    "overcap": False, "error_code": None}
        with self._lock:
            eof = self.eof
            total = self.total_bytes
            stream_error = self.error_code
        live = self._thread.is_alive()
        state = file.snapshot()
        return {
            "opted": True,
            "live": live,
            "eof": eof,
            "total": total,
            "stream_error": stream_error,
            "stream_sha256": (self.capture_hash.hexdigest()
                              if eof and stream_error is None else None),
            "overcap": state["overcap"],
            "error_code": state["error_code"],
        }

    def finish(self, wait_seconds: float) -> tuple[str, int, bool, bool, str | None]:
        self._thread.join(max(0.0, wait_seconds))
        alive = self._thread.is_alive()
        with self._lock:
            total = self.total_bytes
            tail = bytes(self.tail)
            eof = self.eof
            error_code = self.error_code
        truncated = total > self.limit_bytes
        if truncated:
            marker = f"[... {total - self.limit_bytes} bytes omitted ...]\n".encode("utf-8")
            keep = max(0, self.limit_bytes - len(marker))
            payload = marker + tail[-keep:]
        else:
            payload = tail
        complete = not alive and eof and error_code is None
        return (
            payload.decode("utf-8", errors="replace"),
            total,
            truncated,
            complete,
            error_code,
        )


def _start_input_writer(stream: Any, payload: bytes) -> tuple[threading.Thread, dict[str, Any]]:
    state: dict[str, Any] = {"complete": False, "error_code": None}

    def write_input() -> None:
        try:
            view = memoryview(payload)
            while view:
                written = stream.write(view)
                if written is None:
                    written = 0
                if written <= 0:
                    raise LaneRuntimeError("owned_stdin_short_write")
                view = view[written:]
            stream.flush()
            state["complete"] = True
        except BrokenPipeError:
            state["error_code"] = "BrokenPipeError"
        except (OSError, ValueError, LaneRuntimeError) as exc:
            state["error_code"] = type(exc).__name__
        finally:
            try:
                stream.close()
            except (OSError, ValueError):
                pass

    thread = threading.Thread(
        target=write_input,
        name="lane-stdin-writer",
        daemon=True,
    )
    thread.start()
    return thread, state


def _mark_stream_state_unproven(
    cleanup: dict[str, Any],
    *,
    stdout_complete: bool,
    stderr_complete: bool,
    stdin_complete: bool,
    stdout_error: str | None,
    stderr_error: str | None,
    stdin_error: str | None,
    stdout_file_complete: bool | None = None,
    stderr_file_complete: bool | None = None,
    result_file_complete: bool | None = None,
) -> dict[str, Any]:
    cleanup = dict(cleanup)
    cleanup["stdout_capture_complete"] = stdout_complete
    cleanup["stderr_capture_complete"] = stderr_complete
    cleanup["stdin_delivery_complete"] = stdin_complete
    cleanup["stdout_capture_error"] = stdout_error
    cleanup["stderr_capture_error"] = stderr_error
    cleanup["stdin_delivery_error"] = stdin_error
    if stdout_file_complete is not None:
        cleanup["stdout_file_capture_complete"] = stdout_file_complete
    if stderr_file_complete is not None:
        cleanup["stderr_file_capture_complete"] = stderr_file_complete
    if result_file_complete is not None:
        cleanup["result_file_capture_complete"] = result_file_complete
    complete = stdout_complete and stderr_complete and stdin_complete
    if (stdout_file_complete is False or stderr_file_complete is False
            or result_file_complete is False):
        complete = False
    if complete:
        return cleanup
    if cleanup_receipt_is_proven(cleanup):
        cleanup["status"] = "output_capture_unproven"
        cleanup["identity_verified"] = False
        cleanup["census_proven"] = False
        cleanup["residual_count"] = None
        cleanup["error_code"] = "owned_stream_not_closed"
    return cleanup


def _owned_shell() -> str | None:
    # 2026-10-05 seat 0e657eec: /bin/zsh was hardcoded, so every shell=True lane on a
    # Linux host (ubuntu1) died at Popen with FileNotFoundError before checkout. Prefer
    # zsh where it exists (macOS hosts, unchanged), else bash (Ubuntu's /bin/sh is dash).
    for cand in ("/bin/zsh", "/bin/bash"):
        if os.path.exists(cand):
            return cand
    return None



LAUNCH_RECEIPT_SCHEMA = "mastermind.local_owned_process_launch.v1"
_LAUNCH_ID_FIELDS = frozenset({"root_id", "job_id", "attempt_id"})
_LAUNCH_DIGEST_FIELDS = frozenset({"effective_grant_sha256", "commission_sha256"})
_LAUNCH_BINDING_FIELDS = frozenset({"physical_binding_sha256", "start_request_sha256"})


def _launch_receipt_input(path, metadata):
    # Correlation comes from the embedding adapter, never prompt/environment.
    # It is receipt-only data and cannot authorize or alter the launch.
    if path is None:
        if metadata is not None:
            raise LaneRuntimeError("launch_metadata_without_receipt")
        return None, {}
    destination = Path(path)
    if not destination.is_absolute():
        raise LaneRuntimeError("launch_receipt_path_invalid")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise LaneRuntimeError("launch_correlation_invalid")
    context = {} if metadata is None else dict(metadata)
    if set(context) - (
        _LAUNCH_ID_FIELDS | _LAUNCH_DIGEST_FIELDS | _LAUNCH_BINDING_FIELDS
    ):
        raise LaneRuntimeError("launch_correlation_invalid")
    for key, value in context.items():
        if type(value) is not str or not (
            _LABEL_RE.fullmatch(value) if key in _LAUNCH_ID_FIELDS
            else re.fullmatch(r"[0-9a-f]{64}", value)
        ):
            raise LaneRuntimeError("launch_correlation_invalid")
    if _LAUNCH_BINDING_FIELDS & set(context) and not (
        _LAUNCH_ID_FIELDS | _LAUNCH_DIGEST_FIELDS | _LAUNCH_BINDING_FIELDS
    ) <= set(context):
        # Optional new binding is atomic: both new digests plus every
        # legacy correlation key, or the new keys are refused entirely.
        raise LaneRuntimeError("launch_binding_incomplete")
    _launch_receipt_directory(destination)
    if os.path.lexists(destination):
        raise LaneRuntimeError("launch_receipt_already_exists")
    return destination, context


def _launch_receipt_directory(path):
    # Require an existing owner-private directory; no permission repairs.
    try:
        visible = path.parent.lstat()
        if (not stat.S_ISDIR(visible.st_mode) or visible.st_uid != os.geteuid()
                or stat.S_IMODE(visible.st_mode) & 0o077):
            raise LaneRuntimeError("launch_receipt_directory_unsafe")
    except OSError as exc:
        raise LaneRuntimeError("launch_receipt_directory_unavailable") from exc
    return visible


def _write_immutable_launch_receipt(path, record):
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False) + "\n").encode()
    _write_immutable_owned_bytes(path, payload, maximum=8192)


def _write_immutable_owned_bytes(path, payload, *, maximum):
    # Same no-replace carrier for early receipts and complete START retention.
    # A retained inode is observation, never restart admission or Control authority.
    if type(payload) is not bytes or not payload or len(payload) > maximum:
        raise LaneRuntimeError("launch_receipt_too_large")
    parent = _launch_receipt_directory(path)
    directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                           | getattr(os, "O_NOFOLLOW", 0))
    temporary = ".launch-" + os.urandom(16).hex()
    fd = None
    try:
        actual = os.fstat(directory_fd)
        if (actual.st_dev, actual.st_ino) != (parent.st_dev, parent.st_ino):
            raise LaneRuntimeError("launch_receipt_directory_moved")
        fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL
                     | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
        _write_all(fd, payload)
        os.fsync(fd)
        os.fchmod(fd, 0o400)
        os.fsync(fd)
        # The complete immutable inode becomes visible atomically, without replace.
        os.link(temporary, path.name, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
        os.fsync(directory_fd)
        visible = _launch_receipt_directory(path)
        if (visible.st_dev, visible.st_ino) != (actual.st_dev, actual.st_ino):
            raise LaneRuntimeError("launch_receipt_directory_moved")
        published = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        written = os.fstat(fd)
        if (published.st_dev, published.st_ino) != (written.st_dev, written.st_ino):
            raise LaneRuntimeError("launch_receipt_inode_moved")
        os.lseek(fd, 0, os.SEEK_SET)
        if os.read(fd, len(payload) + 1) != payload:
            raise LaneRuntimeError("launch_receipt_readback_changed")
    except OSError as exc:
        raise LaneRuntimeError("launch_receipt_publication_failed") from exc
    finally:
        try:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
        finally:
            os.close(directory_fd)


class _LaunchProcBSDInfo(ctypes.Structure):
    # Same PROC_PIDTBSDINFO layout as the reviewed Executive ProcessInspector.
    _fields_ = [(n, ctypes.c_uint32) for n in (
        "flags", "status", "xstatus", "pid", "ppid", "uid", "gid", "ruid",
        "rgid", "svuid", "svgid", "reserved")]
    _fields_ += [("comm", ctypes.c_char * 16), ("name", ctypes.c_char * 32)]
    _fields_ += [(n, ctypes.c_uint32) for n in (
        "nfiles", "pgid", "pjobc", "e_tdev", "e_tpgid")]
    _fields_ += [("nice", ctypes.c_int32), ("start_sec", ctypes.c_uint64),
                 ("start_usec", ctypes.c_uint64)]


def _launch_kernel_text(path):
    # Only fixed boot/stat/status paths of this owned child, never environ.
    with Path(path).open("rb") as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise LaneRuntimeError("launch_identity_unavailable")
    return data.decode("ascii")


def _observe_owned_launch_identity(pid):
    if type(pid) is not int or pid <= 0:
        raise LaneRuntimeError("launch_identity_unavailable")
    try:
        if sys.platform == "darwin":
            boot = _run_ps_lines(
                ["/usr/sbin/sysctl", "-n", "kern.bootsessionuuid"], timeout=2)
            if len(boot) != 1:
                raise LaneRuntimeError("launch_identity_unavailable")
            libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            read = libproc.proc_pidinfo
            read.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                             ctypes.c_void_p, ctypes.c_int]
            read.restype = ctypes.c_int
            info = _LaunchProcBSDInfo()
            size = ctypes.sizeof(info)
            if read(pid, 3, 0, ctypes.byref(info), size) != size or info.pid != pid:
                raise LaneRuntimeError("launch_identity_unavailable")
            if info.start_sec <= 0 or info.start_usec >= 1000000:
                raise LaneRuntimeError("launch_identity_unavailable")
            generation = f"darwin:{info.start_sec}.{info.start_usec:06d}"
            pgid = int(info.pgid)
            uid, gid, ruid, rgid = info.uid, info.gid, info.ruid, info.rgid
            boot_id = boot[0]
        elif sys.platform.startswith("linux"):
            boot_id = _launch_kernel_text("/proc/sys/kernel/random/boot_id").strip()
            raw = _launch_kernel_text(f"/proc/{pid}/stat")
            close = raw.rfind(") ")
            if close < 0 or int(raw.split("(", 1)[0]) != pid:
                raise LaneRuntimeError("launch_identity_unavailable")
            fields = raw[close + 2:].split()
            if len(fields) < 20 or fields[0] in {"Z", "X"}:
                raise LaneRuntimeError("launch_identity_unavailable")
            start_ticks = int(fields[19])
            if start_ticks < 0:
                raise LaneRuntimeError("launch_identity_unavailable")
            generation = "linux:" + str(start_ticks)
            pgid = int(fields[2])
            status = _launch_kernel_text(f"/proc/{pid}/status")
            ids = {}
            for line in status.splitlines():
                key, _, values = line.partition(":")
                if key in {"Uid", "Gid"}:
                    if key in ids:
                        raise LaneRuntimeError("launch_identity_unavailable")
                    ids[key] = [int(v) for v in values.split()]
            if set(ids) != {"Uid", "Gid"} or any(len(v) != 4 for v in ids.values()):
                raise LaneRuntimeError("launch_identity_unavailable")
            ruid, uid = ids["Uid"][:2]
            rgid, gid = ids["Gid"][:2]
        else:
            raise LaneRuntimeError("launch_identity_platform_unavailable")
        if (not re.fullmatch(r"[A-Za-z0-9-]{8,128}", boot_id) or pgid != pid
                or os.getpgid(pid) != pid or os.getsid(pid) != pid
                or any(type(v) is not int or v < 0 for v in (uid, gid, ruid, rgid))):
            raise LaneRuntimeError("launch_identity_unavailable")
        return dict(pid=pid, pgid=pgid, session_id=pid, boot_id=boot_id,
                    process_start_identity=generation, effective_uid=int(uid),
                    effective_gid=int(gid), real_uid=int(ruid), real_gid=int(rgid))
    except (OSError, ValueError, UnicodeError, ProcessCensusError) as exc:
        raise LaneRuntimeError("launch_identity_unavailable") from exc


def _publish_owned_launch_receipt(path, proc, label, context, context_sha256=None):
    if proc.poll() is not None:
        raise LaneRuntimeError("launch_child_not_live")
    observed = _observe_owned_launch_identity(proc.pid)
    receipt = dict(schema=LAUNCH_RECEIPT_SCHEMA, label=label, observed_at=_utc_now(),
                   phase="PRE_EXEC_HANDSHAKE", process_identity=observed,
                   correlation=context, correlation_is_authority=False,
                   executable_kind="isolated-python-exec-gate",
                   provider_execution_attested=False)
    if proc.poll() is not None or _observe_owned_launch_identity(proc.pid) != observed:
        raise LaneRuntimeError("launch_process_generation_moved")
    if context_sha256 is not None:
        receipt["context_sha256"] = context_sha256
    _write_immutable_launch_receipt(path, receipt)
    raw = (json.dumps(receipt, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False) + "\n").encode()
    return hashlib.sha256(raw).hexdigest()


def _owned_gate_command(command, shell, fd):
    if shell:
        values = [command] if isinstance(command, str) else list(command)
        target = [_owned_shell() or "/bin/sh", "-c", *values]
    else:
        target = [command] if isinstance(command, str) else list(command)
    if not target or any(not isinstance(v, (str, os.PathLike)) for v in target):
        raise LaneRuntimeError("launch_command_invalid")
    # -I -B excludes Python user startup code. exec preserves the actual PID,
    # generation, UID/GID and session. EOF/failure never executes the target.
    code = ("import os,sys; fd=int(sys.argv[1]); token=os.read(fd,1); os.close(fd); "
            "token==b'1' or sys.exit(78); os.execvp(sys.argv[2],sys.argv[2:])")
    return [sys.executable, "-I", "-B", "-c", code, str(fd),
            *(os.fspath(v) for v in target)]


def _owned_process_steps(
    command: str | Sequence[str],
    _owner,
    *,
    cwd: str | os.PathLike[str] | None = None,
    timeout: float,
    input_text: str | None = None,
    shell: bool = False,
    env: Mapping[str, str] | None = None,
    nice: int | None = None,
    terminate_grace: float = 2.0,
    label: str = "lane-process",
    receipt_path: str | os.PathLike[str] | None = None,
    timeout_returncode: int = -9,
    capture_limit_bytes: int = DEFAULT_CAPTURE_LIMIT_BYTES,
    receipt_diagnostics=None,
    launch_receipt_path: str | os.PathLike[str] | None = None,
    launch_receipt_metadata: Mapping[str, str] | None = None,
    launch_receipt_context_sha256: str | None = None,
    owned_capture_run_dir: str | os.PathLike[str] | None = None,
    owned_capture_result_schema_json: str | None = None,
    owned_capture_assignment: Mapping[str, Any] | None = None,
) -> OwnedProcessResult:
    try:
        timeout = float(timeout)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout_invalid") from exc
    if timeout != timeout or timeout in (float("inf"), float("-inf")):
        raise ValueError("timeout_invalid")
    if timeout <= 0:
        raise ValueError("timeout_must_be_positive")
    if terminate_grace < 0:
        raise ValueError("terminate_grace_must_be_nonnegative")
    if not 64 <= int(capture_limit_bytes) <= MAX_CAPTURE_LIMIT_BYTES:
        raise LaneRuntimeConfigError("capture_limit_out_of_bounds")
    safe_label = _safe_label(label)
    launch_path, launch_context = _launch_receipt_input(
        launch_receipt_path, launch_receipt_metadata)
    if launch_receipt_context_sha256 is not None and (
            launch_path is None or type(launch_receipt_context_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", launch_receipt_context_sha256) is None):
        raise LaneRuntimeError("launch_context_digest_invalid")
    launch_receipt_sha256 = None
    input_bytes = input_text.encode("utf-8") if input_text is not None else None
    # Retain provenance before opening the exec gate or attempting Popen.
    # Never retain secret values; the nonce is minted once by this owner.
    _owner.launch_nonce = os.urandom(16).hex()
    _owner._invocation = dict(
        command=command if isinstance(command, str) else list(command),
        cwd=os.fspath(cwd) if cwd is not None else None, shell=shell,
        environment_keys=sorted(env) if env is not None else None,
        environment_projection_sha256=_nonsecret_environment_sha256(env),
        prompt_sha256=hashlib.sha256(input_bytes).hexdigest() if input_bytes is not None else None)
    started_at = _utc_now()
    _owner.started_at = started_at
    capture_reservation = None
    if (owned_capture_run_dir is not None or owned_capture_result_schema_json is not None
            or owned_capture_assignment is not None):
        if owned_capture_run_dir is None or owned_capture_result_schema_json is None:
            raise LaneRuntimeConfigError("owned_capture_options_incomplete")
        capture_reservation = _OwnedCaptureReservation.create(
            owned_capture_run_dir,
            result_schema_json=owned_capture_result_schema_json,
            limit_bytes=int(capture_limit_bytes), assignment=owned_capture_assignment,
        )
        _owner._capture_reservation = capture_reservation
        _owner.owned_capture = capture_reservation.describe()
    gate_read = gate_write = None
    launch_command = command
    extra_popen = {}
    if launch_path is not None:
        try:
            gate_read, gate_write = os.pipe()
        except BaseException:
            if capture_reservation is not None: capture_reservation.abort()
            raise
        try:
            launch_command = _owned_gate_command(command, shell, gate_read)
        except BaseException:
            os.close(gate_read)
            os.close(gate_write)
            if capture_reservation is not None: capture_reservation.abort()
            raise
        extra_popen["pass_fds"] = (gate_read,)
    _owner.spawn_attempted = True
    try:
        proc = subprocess.Popen(
            launch_command,
            cwd=cwd,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell if launch_path is None else False,
            executable=_owned_shell() if shell and launch_path is None else None,
            env=dict(env) if env is not None else None,
            close_fds=True,
            start_new_session=True,
            **extra_popen,
        )
    except OSError as exc:
        _owner.spawn_attempted = False
        # Popen's exec-error pipe confirms failed exec. Exceptions after this
        # boundary remain uncertain and must preserve the reconciliation hold.
        if gate_write is not None:
            os.close(gate_write)
        if capture_reservation is not None:
            capture_reservation.abort()
            capture_reservation = None
        raise OwnedProcessStartError(exc.errno) from None
    except BaseException:
        if gate_write is not None:
            os.close(gate_write)
        if capture_reservation is not None:
            capture_reservation.abort()
            capture_reservation = None
        raise
    finally:
        if gate_read is not None:
            os.close(gate_read)
    _owner.process = proc
    try:
        pgid = proc.pid
        try:
            observed_pgid = os.getpgid(proc.pid)
            observed_sid = os.getsid(proc.pid)
        except ProcessLookupError:
            if proc.poll() is None:
                _kill_exact_leader(proc, grace=2.0)
                raise LaneRuntimeError("owned_process_identity_unavailable")
            observed_pgid = pgid
            observed_sid = pgid
        except PermissionError as exc:
            _kill_exact_leader(proc, grace=2.0)
            raise LaneRuntimeError("owned_process_identity_unavailable") from exc
        if observed_pgid != pgid:
            _kill_exact_leader(proc, grace=2.0)
            raise LaneRuntimeError("owned_process_group_identity_failed")
        if observed_sid != pgid:
            _kill_exact_leader(proc, grace=2.0)
            raise LaneRuntimeError("owned_process_session_identity_failed")
        if proc.stdout is None or proc.stderr is None:
            _kill_exact_leader(proc, grace=2.0)
            raise LaneRuntimeError("owned_output_stream_missing")

        applied_nice = False
        if nice is not None:
            if not MIN_NICE <= int(nice) <= MAX_NICE:
                _terminate_verified_group(proc, pgid, grace=0.2, reason="invalid_nice")
                raise LaneRuntimeConfigError("lane_nice_out_of_bounds")
            try:
                os.setpriority(os.PRIO_PROCESS, proc.pid, int(nice))
                applied_nice = True
            except (AttributeError, PermissionError, ProcessLookupError):
                applied_nice = False

        try:
            _set_current(proc, pgid, safe_label)
        except BaseException:
            _terminate_verified_group(proc, pgid, grace=0.2, reason="set_current_failed")
            raise

    except BaseException:
        if gate_write is not None:
            os.close(gate_write)
        if capture_reservation is not None:
            capture_reservation.close_fds_only()
            capture_reservation = None
        raise

    stdout_collector = stderr_collector = None
    stdout_started = stderr_started = False
    stdin_thread: threading.Thread | None = None
    stdin_state: dict[str, Any] = {"complete": True, "error_code": None}

    timed_out = False
    cleanup: dict[str, Any] = {
        "status": "not_needed",
        "reason": "normal_completion",
        "sigterm_sent": False,
        "sigkill_sent": False,
        "identity_verified": True,
        "census_proven": False,
        "residual_count": None,
        "error_code": None,
    }
    returncode = 1
    stdout = ""
    stderr = ""
    stdout_bytes = 0
    stderr_bytes = 0
    stdout_truncated = False
    stderr_truncated = False
    runtime_failure_code: str | None = None
    try:
        try:
            # Collector setup is post-spawn and must share the same settlement
            # and gate-fd finally path as publication, exec and input delivery.
            stdout_capture = (capture_reservation.files["stdout"]
                              if capture_reservation is not None else None)
            stderr_capture = (capture_reservation.files["stderr"]
                              if capture_reservation is not None else None)
            if capture_reservation is None:
                stdout_collector = _BoundedStreamCollector(proc.stdout, int(capture_limit_bytes), 'stdout')
                stderr_collector = _BoundedStreamCollector(proc.stderr, int(capture_limit_bytes), 'stderr')
            else:
                stdout_collector = _BoundedStreamCollector(proc.stdout, int(capture_limit_bytes), 'stdout', capture_file=stdout_capture)
                stderr_collector = _BoundedStreamCollector(proc.stderr, int(capture_limit_bytes), 'stderr', capture_file=stderr_capture)
            if stdout_capture is not None:
                stdout_capture.note_streaming()
            if stderr_capture is not None:
                stderr_capture.note_streaming()
            stdout_collector.start()
            stdout_started = True
            stderr_collector.start()
            stderr_started = True
            if input_bytes is not None and launch_path is None:
                if proc.stdin is None:
                    raise LaneRuntimeError("owned_stdin_stream_missing")
                stdin_thread, stdin_state = _start_input_writer(proc.stdin, input_bytes)
            if launch_path is not None:
                if launch_receipt_context_sha256 is None:
                    launch_receipt_sha256 = _publish_owned_launch_receipt(
                        launch_path, proc, safe_label, launch_context)
                else:
                    launch_receipt_sha256 = _publish_owned_launch_receipt(
                        launch_path, proc, safe_label, launch_context, launch_receipt_context_sha256)
                os.write(gate_write, b"1")
                os.close(gate_write)
                gate_write = None
                if input_bytes is not None:
                    stdin_thread, stdin_state = _start_input_writer(proc.stdin, input_bytes)
            _owner.pgid = pgid
            _owner.label = safe_label
            _owner.timeout = timeout
            _owner.deadline = time.monotonic() + timeout
            if _owner.capture_identity:
                if proc.poll() is not None:
                    raise LaneRuntimeError("owned_child_not_live")
                _owner._identity = _observe_owned_launch_identity(proc.pid)
                if proc.poll() is not None:
                    raise LaneRuntimeError("owned_child_not_live")
            # The same stack retains collectors, gate, receipt and cleanup.
            # Yield is mechanics only: it is not a POST_EXEC/START attestation.
            wait_outcome = yield
            if wait_outcome == "completed":
                returncode = int(proc.returncode or 0)
                try:
                    residual = _session_pids(pgid)
                except ProcessCensusError as exc:
                    cleanup = _unproven_cleanup_receipt(
                        cleanup, proc, exc, grace=max(0.2, terminate_grace)
                    )
                else:
                    if residual:
                        cleanup = _terminate_verified_group(
                            proc,
                            pgid,
                            grace=terminate_grace,
                            reason="leader_exited_with_descendants",
                        )
                    else:
                        cleanup["census_proven"] = True
                        cleanup["residual_count"] = 0
            elif wait_outcome == "process_limit":
                cleanup = _terminate_verified_group(
                    proc,
                    pgid,
                    grace=terminate_grace,
                    reason="process_group_member_limit_exceeded",
                )
                returncode = PROCESS_LIMIT_RETURNCODE
            elif wait_outcome == "timeout":
                timed_out = True
                cleanup = _terminate_verified_group(
                    proc, pgid, grace=terminate_grace, reason="timeout"
                )
                returncode = int(timeout_returncode)
            else:
                raise LaneRuntimeError("owned_process_wait_outcome_invalid")
        except BaseException as exc:
            runtime_failure_code = _runtime_failure_code(exc)
            cleanup = _terminate_verified_group(
                proc, pgid, grace=terminate_grace, reason="parent_exception"
            )
            raise
    finally:
        if gate_write is not None:
            os.close(gate_write)
        _clear_current(proc)
        capture_deadline = time.monotonic() + max(
            0.25, min(2.0, terminate_grace + 0.25)
        )
        if stdin_thread is not None:
            stdin_thread.join(max(0.0, capture_deadline - time.monotonic()))
        stdin_complete = stdin_thread is None or (
            not stdin_thread.is_alive() and bool(stdin_state.get("complete"))
        )
        if not stdout_started:
            proc.stdout.close()
        if not stderr_started:
            proc.stderr.close()
        stdout, stdout_bytes, stdout_truncated, stdout_complete, stdout_error = (
            stdout_collector.finish(max(0.0, capture_deadline - time.monotonic()))
            if stdout_started else ("", 0, False, False, "collector_unavailable")
        )
        stderr, stderr_bytes, stderr_truncated, stderr_complete, stderr_error = (
            stderr_collector.finish(max(0.0, capture_deadline - time.monotonic()))
            if stderr_started else ("", 0, False, False, "collector_unavailable")
        )
        owned_capture_block = None
        structured_result = None
        stdout_file_complete = None
        stderr_file_complete = None
        result_file_complete = None
        cleanup = _mark_stream_state_unproven(cleanup,
            stdout_complete=stdout_complete, stderr_complete=stderr_complete,
            stdin_complete=stdin_complete, stdout_error=stdout_error,
            stderr_error=stderr_error, stdin_error=stdin_state.get('error_code'))
        if capture_reservation is not None:
            try:
                # A no-signal observation after natural process exit does not
                # cancel its result. The once-only request fence stays consumed;
                # missing/uncertain/signaled observations remain conservative.
                cancel_observation = _owner._cancel_observation
                cancelled = _owner._cancel_attempted
                if (cancelled and type(cancel_observation) is dict
                        and cancel_observation.get('already_exited') is True
                        and cancel_observation.get('signal_sent') is False
                        and cancel_observation.get('escalated_to_sigkill') is False
                        and type(_owner._cancel_receipt) is dict
                        and cleanup_receipt_is_proven(_owner._cancel_receipt)):
                    cancelled = False
                owned_capture_block, structured_result = capture_reservation.finalize(
                    stdout_collector, stderr_collector,
                    cleanup=cleanup, returncode=returncode, timed_out=timed_out,
                    cancelled=cancelled,
                )
                stdout_file_complete = bool(owned_capture_block.get("stdout_file_complete"))
                stderr_file_complete = bool(owned_capture_block.get("stderr_file_complete"))
                result_file_complete = bool(owned_capture_block.get("result_file_complete"))
            except BaseException as exc:  # capture must never mask the run outcome
                owned_capture_block = {
                    "schema": OWNED_CAPTURE_SCHEMA,
                    "stdout_file_complete": False,
                    "stderr_file_complete": False,
                    "finalization_error": type(exc).__name__,
                }
                structured_result = None
                stdout_file_complete = False
                stderr_file_complete = False
                result_file_complete = False
        cleanup = _mark_stream_state_unproven(
            cleanup,
            stdout_complete=stdout_complete,
            stderr_complete=stderr_complete,
            stdin_complete=stdin_complete,
            stdout_error=stdout_error,
            stderr_error=stderr_error,
            stdin_error=stdin_state.get("error_code"),
            stdout_file_complete=stdout_file_complete,
            stderr_file_complete=stderr_file_complete,
            result_file_complete=result_file_complete,
        )
        ended_at = _utc_now()
        _owner._terminal_finished_at = ended_at
        _owner._terminal_cleanup_record = json.dumps(cleanup, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
        if capture_reservation is not None and owned_capture_block is not None:
            _owner._capture_stdout_bytes = capture_reservation.terminal_stdout
            _owner._capture_stderr_bytes = capture_reservation.terminal_stderr
            _owner._capture_terminal_record = json.dumps(owned_capture_block,
                sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                allow_nan=False).encode()
        diagnostic_fields = {}
        if receipt_diagnostics is not None:
            try:
                if not (stdout_complete and stderr_complete and stdin_complete):
                    raise ValueError('diagnostic_capture_incomplete')
                diagnostic_fields['operator_hook_diagnostics'] = receipt_diagnostics()
            except Exception:
                diagnostic_fields['operator_hook_diagnostics'] = {
                    'schema': 'mastermind.fabric_operator_hook_diagnostics.v1',
                    'state': 'UNAVAILABLE', 'events': [], 'authority': False,
                    'invocation_authenticated': False}
        if receipt_path is not None:
            _append_process_receipt(
                Path(receipt_path),
                {
                    "schema": PROCESS_RECEIPT_SCHEMA,
                    **diagnostic_fields,
                    **({"launch_capture": {
                        "phase": "PRE_EXEC_HANDSHAKE",
                        "receipt_sha256": launch_receipt_sha256,
                        "context_sha256": launch_receipt_context_sha256,
                        "provider_execution_attested": False,
                    }} if launch_path is not None else {}),
                    **({"owned_capture": owned_capture_block}
                       if owned_capture_block is not None else {}),
                    "label": safe_label,
                    "pid": proc.pid,
                    "pgid": pgid,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "returncode": returncode,
                    "timed_out": timed_out,
                    "nice_requested": nice,
                    "nice_applied": applied_nice,
                    "stdout_bytes": stdout_bytes,
                    "stdout_sha256": stdout_collector.complete_digest() if stdout_complete else None,
                    "stderr_bytes": stderr_bytes,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "runtime_failure_code": runtime_failure_code,
                    "cleanup": cleanup,
                },
            )
    return OwnedProcessResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        pid=proc.pid,
        pgid=pgid,
        cleanup=cleanup,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        owned_capture=owned_capture_block,
        structured_result=structured_result,
    )


_EXECUTION_OWNER = None


def _nonsecret_environment_sha256(environment):
    if environment is None:
        return None
    # Credential values are never retained or hashed. This digest binds only
    # the existing preparer's non-secret model/endpoint/HOME/TMP controls.
    projection = {k: v for k, v in environment.items() if not re.search(
        r'api.?key|authorization|credential|secret|token|password', k, re.I)}
    return hashlib.sha256(json.dumps(projection, sort_keys=True,
        separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class OwnedExecution:
    """Resources of the one original runner, not a Job registry or authority.

    A handle must stay in its original main-thread controller until terminal
    collection/cleanup. Its finisher survives cancellation of an RPC waiter.
    The surrounding original owner retains its lease and assignment exclusion.
    """
    def __init__(self, *, capture_identity):
        self.capture_identity = capture_identity
        self.owner_thread = threading.get_ident()
        self.process = None
        self.spawn_attempted = False
        self.pgid = None
        self.label = None
        self.timeout = None
        self.deadline = None
        self._identity = None
        self._steps = None
        self._finisher = None
        self._cancel_receipt = None
        self._cancel_attempted = False
        self._cancel_observation = None
        self._terminal_finished_at = None
        self._capture_terminal_record = None
        self._terminal_cleanup_record = None
        self._capture_stdout_bytes = None
        self._capture_stderr_bytes = None
        self.result = None
        self.failure = None
        self._settling = False
        self.started_at = None
        self.launch_nonce = None
        self._invocation = None
        self._start_assembly_attempted = False
        self._start_publication_attempted = False
        self._start_record_sha256 = None
        self.owned_capture = None
        self._capture_reservation = None

    @property
    def process_identity(self):
        return dict(self._identity) if self._identity is not None else None

    @property
    def invocation(self):
        return json.loads(json.dumps(self._invocation)) if self._invocation is not None else None


def _require_owned_execution(owner):
    if type(owner) is not OwnedExecution or owner.owner_thread != threading.get_ident():
        raise LaneRuntimeError("owned_process_owner_thread_required")
    if owner.failure is not None:
        raise owner.failure
    if owner.result is not None:
        return
    if _EXECUTION_OWNER is not owner:
        raise LaneRuntimeError("owned_process_handle_stale")


def retain_owned_start_bytes(owner, payload):
    """Retain once on THIS live handle's prebound original carrier.

    This is a publication mechanic, not an attestation or admission producer.
    The embedding original owner must first run both full START validators with
    independently qualified inputs. No receipt can recreate this live handle.
    Failure keeps the original finisher and puts its existing lease in hold.
    """
    _require_owned_execution(owner)
    if owner._start_publication_attempted:
        raise LaneRuntimeError("owned_start_publication_already_attempted")
    owner._start_publication_attempted = True
    try:
        if owner.process is None or owner.process.poll() is not None or owner.result is not None:
            raise LaneRuntimeError("owned_start_process_not_live")
        context = getattr(owner, '_original_start_context', None)
        path = getattr(owner, '_original_start_receipt_path', None)
        if type(context) is not dict or not isinstance(path, Path):
            raise LaneRuntimeError("owned_start_original_carrier_required")
        if type(payload) is not bytes or not 0 < len(payload) <= 65536:
            raise LaneRuntimeError("owned_start_record_invalid")
        record = json.loads(payload)
        if (type(record) is not dict or set(record) != {'schema', 'contract_name',
                'run_id', 'adapter_id', 'request_sha256', 'physical_binding_sha256',
                'start_result', 'retained_at'}
                or record['schema'] != 'mastermind.fabric_owned_complete_start/v1'
                or record['adapter_id'] != 'attended-fabric'
                or json.dumps(record, sort_keys=True, separators=(',', ':'),
                    ensure_ascii=False, allow_nan=False).encode() != payload):
            raise LaneRuntimeError('owned_start_record_invalid')
        result = record['start_result']
        ref, att = result['process_ref'], result['launch_attestation']
        identity = owner.process_identity
        invocation = owner.invocation
        preparation = getattr(owner, '_original_preparation', None)
        if (preparation is None or invocation['environment_projection_sha256'] !=
                _nonsecret_environment_sha256(preparation.environment)):
            raise LaneRuntimeError('owned_start_prepared_environment_changed')
        expected_ref = dict(run_id=owner.label, pid=identity['pid'], pgid=identity['pgid'],
            session_id=identity['session_id'], boot_session_id=identity['boot_id'],
            process_start_identity=identity['process_start_identity'],
            launch_nonce=owner.launch_nonce, started_at=owner.started_at,
            **{k: identity[k] for k in ('effective_uid', 'effective_gid', 'real_uid', 'real_gid')})
        expected_identity = {k: identity[k] for k in ('pid', 'pgid', 'session_id',
            'boot_id', 'effective_uid', 'effective_gid', 'real_uid', 'real_gid')}
        expected_identity['start_identity'] = identity['process_start_identity']
        if (record['run_id'] != owner.label
                or record['request_sha256'] != context['request_sha256']
                or record['physical_binding_sha256'] != context['physical_binding_sha256']
                or result['adapter_id'] != 'attended-fabric'
                or result['binding'] != context['binding']
                or result['physical_binding_sha256'] != context['physical_binding_sha256']
                or result['request_sha256'] != context['request_sha256']
                or any(ref.get(k) != v for k, v in expected_ref.items())
                or att['launch_nonce'] != owner.launch_nonce or att['process_identity'] != expected_identity
                or invocation['shell'] is not False
                or att['rendered_argv'] != invocation['command']
                or att['environment_keys'] != invocation['environment_keys']
                or att['prompt_sha256'] != invocation['prompt_sha256']
                or att['workspace_identity']['path'] != invocation['cwd']):
            raise LaneRuntimeError("owned_start_original_invocation_changed")
        if any(key in ref for key in ('stdout_path', 'stderr_path', 'result_path')):
            live = validate_owned_capture_live(owner)
            if any(ref.get(key) != value['path'] for key, value in live['files'].items()):
                raise LaneRuntimeError('owned_start_capture_changed')
        snapshot = getattr(owner, '_observed_image_snapshot', None)
        if snapshot is None or observe_owned_process_image(owner) != snapshot:
            raise LaneRuntimeError('owned_start_image_unconfirmed')
        _write_immutable_owned_bytes(path, payload, maximum=65536)
        if observe_owned_process_image(owner) != snapshot:
            raise LaneRuntimeError('owned_start_image_unconfirmed_after_write')
        if any(key in ref for key in ('stdout_path', 'stderr_path', 'result_path')):
            validate_owned_capture_live(owner)
        owner._start_record_sha256 = hashlib.sha256(payload).hexdigest()
        return owner._start_record_sha256
    except BaseException:
        lease = getattr(owner, '_original_lease', None)
        if lease is not None:
            lease.hold_for_reconciliation('owned_start_publication_unconfirmed')
        raise


def _begin_owned_process(command, *, _main_thread, **kwargs):
    global _EXECUTION_OWNER
    if _main_thread and threading.current_thread() is not threading.main_thread():
        raise LaneRuntimeError("owned_process_main_thread_required")
    owner = OwnedExecution(capture_identity=_main_thread)
    with _CURRENT_LOCK:
        if _EXECUTION_OWNER is not None or _CURRENT_PROCESS is not None:
            raise LaneRuntimeError("owned_process_owner_busy")
        _EXECUTION_OWNER = owner
    owner._steps = _owned_process_steps(command, _owner=owner, **kwargs)
    try:
        next(owner._steps)
    except BaseException as exc:
        owner.failure = exc
        # A proven pre-spawn/exec failure has no effect. An interruption
        # during Popen may have an unknown effect even without a returned PID.
        if not owner.spawn_attempted or not owner.capture_identity:
            with _CURRENT_LOCK:
                if _EXECUTION_OWNER is owner:
                    _EXECUTION_OWNER = None
        raise
    return owner


def begin_owned_process(command, **kwargs):
    """Begin once on the original main thread. Does not claim native START."""
    return _begin_owned_process(command, _main_thread=True, **kwargs)


def observe_owned_process_image(owner):
    """Observe THIS original live handle; never a caller pathname or START grant."""
    _require_owned_execution(owner)
    if (owner.result is not None or owner.process is None
            or owner.process.poll() is not None or owner._identity is None):
        raise LaneRuntimeError("owned_image_not_live")
    try:
        if sys.platform == "darwin":
            from control_plane.darwin_process_image import inspect_owned_darwin_image
            image = inspect_owned_darwin_image(owner.process.pid)
        elif sys.platform.startswith("linux"):
            from control_plane.linux_process_identity import inspect_linux_process_image
            image = inspect_linux_process_image(owner.process.pid)
            image['process_start_identity'] = 'linux:' + image['start_identity']
        else:
            raise LaneRuntimeError("owned_image_platform_unqualified")
    except LaneRuntimeError:
        raise
    except Exception as exc:
        raise LaneRuntimeError("owned_image_observation_unqualified") from exc
    identity = dict(pid=owner.process.pid, pgid=image['pgid'],
        session_id=image['session_id'], boot_id=image['boot_id'],
        process_start_identity=image['process_start_identity'],
        effective_uid=image['effective_uid'], effective_gid=image['effective_gid'],
        real_uid=image['real_uid'], real_gid=image['real_gid'])
    if identity != owner._identity or owner.process.poll() is not None:
        raise LaneRuntimeError("owned_image_generation_changed")
    # Darwin's exec-sensitive identity must remain unchanged across the first
    # image observation and original retention boundary, even for same-path exec.
    instance = image.get('exec_instance')
    previous = getattr(owner, '_observed_image_instance', None)
    if previous is not None and instance != previous:
        raise LaneRuntimeError("owned_image_exec_instance_changed")
    if instance is not None:
        owner._observed_image_instance = dict(instance)
    observed = dict(image, pid=owner.process.pid, label=owner.label)
    snapshot = getattr(owner, '_observed_image_snapshot', None)
    if snapshot is not None and observed != snapshot:
        raise LaneRuntimeError('owned_image_changed_after_latch')
    owner._observed_image_snapshot = json.loads(json.dumps(observed))
    _require_owned_execution(owner)
    return observed


def _settle_owned_process(owner, *, outcome=None, failure=None):
    global _EXECUTION_OWNER
    _require_owned_execution(owner)
    if owner.result is not None:
        return owner.result
    if owner._settling:
        raise LaneRuntimeError("owned_process_settlement_already_owned")
    owner._settling = True
    try:
        if failure is not None:
            owner._steps.throw(failure)
        else:
            owner._steps.send(outcome)
        raise LaneRuntimeError("owned_process_unexpected_second_yield")
    except StopIteration as done:
        owner.result = done.value
        if type(owner.result) is not OwnedProcessResult:
            raise LaneRuntimeError("owned_process_result_invalid")
        # Keep exclusion through capture and durable terminal receipt. Unknown
        # cleanup must stay held; no public reset or new run replaces it.
        if owner.result.cleanup_proven or not owner.capture_identity:
            with _CURRENT_LOCK:
                if _EXECUTION_OWNER is owner:
                    _EXECUTION_OWNER = None
        return owner.result
    except BaseException as exc:
        owner.failure = exc
        raise
    finally:
        owner._settling = False
        # Legacy synchronous callers still settle their reconciliation lease
        # in the incumbent controller; do not add a new lasting global hold.
        if not owner.capture_identity:
            with _CURRENT_LOCK:
                if _EXECUTION_OWNER is owner:
                    _EXECUTION_OWNER = None


def abort_owned_process(owner, failure):
    """Original begin/owner failure uses the same exception/cleanup stack."""
    if not isinstance(failure, BaseException):
        raise TypeError("owned_process_exception_required")
    return _settle_owned_process(owner, failure=failure)


def finish_owned_process(owner):
    _require_owned_execution(owner)
    if owner.result is not None:
        return owner.result
    if owner._finisher is not None:
        raise LaneRuntimeError("owned_process_async_finisher_owns_settlement")
    try:
        outcome = _wait_owned_process_with_fuse(
            owner.process, owner.pgid, max(0.0, owner.deadline - time.monotonic()))
    except BaseException as exc:
        return abort_owned_process(owner, exc)
    return _settle_owned_process(owner, outcome=outcome)


async def _finish_owned_process_async(owner):
    try:
        while True:
            remaining = owner.deadline - time.monotonic()
            if remaining <= 0:
                outcome = "timeout"
                break
            if owner.process.poll() is not None:
                outcome = "completed"
                break
            await asyncio.sleep(min(OWNED_PROCESS_CENSUS_INTERVAL_SECONDS, remaining))
            if owner.process.poll() is not None:
                outcome = "completed"
                break
            if time.monotonic() >= owner.deadline:
                outcome = "timeout"
                break
            outcome = _owned_fuse_check(owner.process, owner.pgid)
            if outcome is not None:
                break
    except BaseException as exc:
        return abort_owned_process(owner, exc)
    return _settle_owned_process(owner, outcome=outcome)


def start_owned_process_finisher(owner):
    """Exactly one retained task uses this runner's wait/settlement stack."""
    _require_owned_execution(owner)
    if threading.current_thread() is not threading.main_thread():
        raise LaneRuntimeError("owned_process_main_thread_required")
    if owner._finisher is None:
        owner._finisher = asyncio.get_running_loop().create_task(_finish_owned_process_async(owner))
        def cancelled_before_entry(task):
            # Cancelling a Task before its coroutine first executes never enters
            # that coroutine's try/finally. Close the SAME yielded runner stack
            # on its owner thread; its original collectors/receipt settle once.
            if task.cancelled() and owner.result is None and owner.failure is None:
                try:
                    abort_owned_process(owner, asyncio.CancelledError())
                except BaseException:
                    # The exact failure is retained on owner; no replacement.
                    pass
        owner._finisher.add_done_callback(cancelled_before_entry)
    return owner._finisher


async def collect_owned_process(owner):
    _require_owned_execution(owner)
    if owner.result is not None:
        return owner.result
    return await asyncio.shield(start_owned_process_finisher(owner))


def cancel_exact_owned_process(owner, *, label, process_identity, reason):
    """Exact original handle; one cancellation attempt and its actual telemetry.

    Returned top-level cleanup fields retain compatibility. cancel_receipt is
    separate from the group observation and never claims dedicated UID sweep.
    """
    _require_owned_execution(owner)
    if (label != owner.label or type(process_identity) is not dict
            or owner._identity is None or process_identity != owner._identity):
        raise LaneRuntimeError('owned_process_cancel_identity_mismatch')
    if type(reason) is not str or not 1 <= len(reason) <= 500 or '\x00' in reason:
        raise LaneRuntimeError('owned_process_cancel_reason_invalid')
    if owner._cancel_receipt is not None:
        if owner._cancel_observation['reason'] != reason:
            raise LaneRuntimeError('owned_process_cancel_reason_changed')
        return {**dict(owner._cancel_receipt),
                'cancel_receipt': dict(owner._cancel_observation)}
    if owner._cancel_attempted:
        raise LaneRuntimeError('owned_process_cancel_unconfirmed')
    with _CURRENT_LOCK:
        already_exited = owner.process.poll() is not None
        if owner.result is None:
            if (_CURRENT_PROCESS is None or _CURRENT_PROCESS[0] is not owner.process
                    or _CURRENT_PROCESS[1:] != (owner.pgid, owner.label)):
                raise LaneRuntimeError('owned_process_cancel_generation_changed')
            if (not already_exited and
                    _observe_owned_launch_identity(owner.process.pid) != owner._identity):
                raise LaneRuntimeError('owned_process_cancel_generation_changed')
        owner._cancel_attempted = True
        try:
            if owner.result is not None:
                cleanup = json.loads(owner._terminal_cleanup_record)
                sent, escalated = False, False
            else:
                cleanup = _terminate_verified_group(owner.process, owner.pgid,
                    grace=1.0, reason=_safe_label(reason))
                sent = cleanup['sigterm_sent']
                escalated = cleanup['sigkill_sent']
                if 'leader_kill_sent' in cleanup:
                    if type(cleanup['leader_kill_sent']) is not bool:
                        raise LaneRuntimeError('owned_process_cancel_telemetry_unconfirmed')
                    escalated = escalated or cleanup['leader_kill_sent']
                if type(sent) is not bool or type(escalated) is not bool:
                    raise LaneRuntimeError('owned_process_cancel_telemetry_unconfirmed')
            observation = dict(run_id=owner.label, reason=reason,
                signal_sent=sent, escalated_to_sigkill=escalated,
                already_exited=already_exited, finished_at=_utc_now())
            owner._cancel_observation = observation
            owner._cancel_receipt = dict(cleanup)
            if not cleanup_receipt_is_proven(cleanup):
                lease = getattr(owner, '_original_lease', None)
                if lease is not None:
                    lease.hold_for_reconciliation('owned_cancel_cleanup_unconfirmed')
        except BaseException:
            lease = getattr(owner, '_original_lease', None)
            if lease is not None:
                lease.hold_for_reconciliation('owned_cancel_observation_unconfirmed')
            raise
    return {**dict(owner._cancel_receipt),
            'cancel_receipt': dict(owner._cancel_observation)}


def owned_capture_collection(owner):
    """Defensive projection from original joined finisher, never a new collect.

    stdout/stderr are immutable exact bytes; incomplete/truncated capture has
    no full-byte projection. This observation is not canonical WorkerResult or
    artifact/Git validation, and never proves UID cleanup or assignment ACK.
    """
    _require_owned_execution(owner)
    if owner.result is None or owner._capture_terminal_record is None:
        raise LaneRuntimeError('owned_capture_terminal_unconfirmed')
    record = json.loads(owner._capture_terminal_record)
    if (owner._capture_stdout_bytes is None or owner._capture_stderr_bytes is None
            or not record.get('stdout_file_complete') or not record.get('stderr_file_complete')
            or not record.get('result_file_complete')):
        raise LaneRuntimeError('owned_capture_terminal_unqualified')
    return dict(run_id=owner.label, stdout=owner._capture_stdout_bytes,
        stderr=owner._capture_stderr_bytes, capture=record,
        returncode=owner.result.returncode, timed_out=owner.result.timed_out,
        finished_at=owner._terminal_finished_at,
        cleanup=json.loads(owner._terminal_cleanup_record),
        cancel_receipt=(dict(owner._cancel_observation) if owner._cancel_observation else None))


def run_owned_process(
    command: str | Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    timeout: float,
    input_text: str | None = None,
    shell: bool = False,
    env: Mapping[str, str] | None = None,
    nice: int | None = None,
    terminate_grace: float = 2.0,
    label: str = "lane-process",
    receipt_path: str | os.PathLike[str] | None = None,
    timeout_returncode: int = -9,
    capture_limit_bytes: int = DEFAULT_CAPTURE_LIMIT_BYTES,
    receipt_diagnostics=None,
    launch_receipt_path: str | os.PathLike[str] | None = None,
    launch_receipt_metadata: Mapping[str, str] | None = None,
    launch_receipt_context_sha256: str | None = None,
    owned_capture_run_dir: str | os.PathLike[str] | None = None,
    owned_capture_result_schema_json: str | None = None,
    owned_capture_assignment: Mapping[str, Any] | None = None,
) -> OwnedProcessResult:
    owner = _begin_owned_process(command, _main_thread=False, cwd=cwd, timeout=timeout, input_text=input_text, shell=shell, env=env, nice=nice, terminate_grace=terminate_grace, label=label, receipt_path=receipt_path, timeout_returncode=timeout_returncode, capture_limit_bytes=capture_limit_bytes, receipt_diagnostics=receipt_diagnostics, launch_receipt_path=launch_receipt_path, launch_receipt_metadata=launch_receipt_metadata, launch_receipt_context_sha256=launch_receipt_context_sha256, owned_capture_run_dir=owned_capture_run_dir, owned_capture_result_schema_json=owned_capture_result_schema_json, owned_capture_assignment=owned_capture_assignment)
    return finish_owned_process(owner)

def _read_marker(fd: int) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        part = os.read(fd, 65536)
        if not part:
            break
        chunks.append(part)
        if sum(map(len, chunks)) > 1_000_000:
            break
    return b"".join(chunks).decode("utf-8", errors="replace")


def _marker_schema(raw: str) -> str | None:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(value, dict) or not isinstance(value.get("schema"), str):
        return None
    return value["schema"]


def _is_json_lease(raw: str) -> bool:
    return _marker_schema(raw) == LEASE_SCHEMA


def _is_reconciliation_hold(raw: str) -> bool:
    return _marker_schema(raw) == RECONCILIATION_HOLD_SCHEMA


def _scan_lane_markers(
    active_dir: Path, *, reap_stale: bool, own_key: str | None = None
) -> tuple[int, int, int, list[str], bool, bool, int]:
    """Shared marker rules. Caller holds admission lock; only admission may reap."""
    active_count = 0
    legacy_count = 0
    json_locked_count = 0
    stale_reaped: list[str] = []
    unlocked_count = 0
    own_active = False
    hold_present = False
    for path in sorted(active_dir.iterdir(), key=lambda item: item.name):
        if path.name.startswith("."):
            continue
        try:
            visible = path.lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(visible.st_mode):
            legacy_count += 1
            active_count += 1
            own_active = own_active or path.name == own_key
            continue
        flags = ((os.O_RDWR if reap_stale else os.O_RDONLY | os.O_NONBLOCK)
                 | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            continue
        except OSError:
            legacy_count += 1
            active_count += 1
            own_active = own_active or path.name == own_key
            continue
        try:
            observed = os.fstat(fd)
            if (
                not stat.S_ISREG(observed.st_mode)
                or (observed.st_dev, observed.st_ino) != (visible.st_dev, visible.st_ino)
            ):
                legacy_count += 1
                active_count += 1
                own_active = own_active or path.name == own_key
                continue
            try:
                raw = _read_marker(fd)
            except OSError:
                if reap_stale:
                    raise
                legacy_count += 1
                active_count += 1
                continue
            if _is_reconciliation_hold(raw):
                hold_present = True
                legacy_count += 1
                active_count += 1
                own_active = own_active or path.name == own_key
                continue
            if not _is_json_lease(raw):
                legacy_count += 1
                active_count += 1
                own_active = own_active or path.name == own_key
                continue
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                json_locked_count += 1
                active_count += 1
                own_active = own_active or path.name == own_key
                continue
            try:
                current = path.lstat()
            except FileNotFoundError:
                continue
            if (
                stat.S_ISREG(current.st_mode)
                and (current.st_dev, current.st_ino) == (observed.st_dev, observed.st_ino)
            ):
                # Opted-in callers require proven release. A failed hold write
                # may leave the original lease JSON intact; unlocked is not
                # proof that its descendants/capture were reconciled.
                if json.loads(raw).get("reconcile_unreleased") is True:
                    hold_present = True
                    legacy_count += 1
                    active_count += 1
                    own_active = own_active or path.name == own_key
                    continue
                unlocked_count += 1
                if reap_stale:
                    path.unlink()
                    stale_reaped.append(path.name)
            else:
                legacy_count += 1
                active_count += 1
                own_active = own_active or path.name == own_key
        finally:
            os.close(fd)
    return (active_count, legacy_count, json_locked_count, stale_reaped,
            own_active, hold_present, unlocked_count)


def evaluate_admission(
    active_dir: Path,
    *,
    max_active: int,
    load1: float,
    cpu_count: int,
    load_ratio_limit: float,
    own_key: str | None = None,
) -> HostAdmissionSnapshot:
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_count, legacy_count, json_locked_count, stale_reaped,
     own_active, hold_present, _) = _scan_lane_markers(
        active_dir, reap_stale=True, own_key=own_key
    )
    reasons: list[str] = []
    if hold_present:
        reasons.append("reconciliation_hold_present")
    if own_active:
        reasons.append("lane_key_already_active")
    if active_count >= max_active:
        reasons.append("active_lane_limit_reached")
    if float(load1) >= float(cpu_count) * float(load_ratio_limit):
        reasons.append("host_load_at_or_above_limit")
    return HostAdmissionSnapshot(
        allowed=not reasons,
        active_count=active_count,
        legacy_count=legacy_count,
        json_locked_count=json_locked_count,
        stale_reaped=tuple(stale_reaped),
        max_active=int(max_active),
        load1=round(float(load1), 3),
        cpu_count=int(cpu_count),
        load_ratio_limit=float(load_ratio_limit),
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class LaneOccupancySnapshot:
    """A placement observation, never an admission or reservation."""
    status: str
    active_count: int | None
    legacy_count: int = 0
    json_locked_count: int = 0
    unlocked_count: int = 0
    reason: str = ""


def read_lane_occupancy(active_dir: Path) -> LaneOccupancySnapshot:
    """Read existing leases without mkdir, marker writes, reaping or waiting.

    A shared lock on the existing admission file prevents observing a half-written
    new lease. Missing/busy/unreadable census is UNKNOWN, never spare capacity.
    Unlocked JSON leases are reported but left for final admission to reconcile.
    """
    admission_fd = None
    try:
        directory = active_dir.lstat()
        if not stat.S_ISDIR(directory.st_mode):
            return LaneOccupancySnapshot("unknown", None, reason="active_directory_not_regular")
        lock_path = active_dir / ".admission.lock"
        visible = lock_path.lstat()
        if not stat.S_ISREG(visible.st_mode):
            return LaneOccupancySnapshot("unknown", None, reason="admission_lock_not_regular")
        admission_fd = os.open(lock_path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
                               | getattr(os, "O_NOFOLLOW", 0))
        observed = os.fstat(admission_fd)
        if ((observed.st_dev, observed.st_ino) != (visible.st_dev, visible.st_ino)
                or not stat.S_ISREG(observed.st_mode)):
            return LaneOccupancySnapshot("unknown", None, reason="admission_lock_changed")
        fcntl.flock(admission_fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        (active, legacy, locked, _, _, held, unlocked) = _scan_lane_markers(
            active_dir, reap_stale=False
        )
        current = lock_path.lstat()
        final_directory = active_dir.lstat()
        if ((current.st_dev, current.st_ino) != (observed.st_dev, observed.st_ino)
                or (final_directory.st_dev, final_directory.st_ino)
                   != (directory.st_dev, directory.st_ino)):
            return LaneOccupancySnapshot("unknown", None, reason="census_identity_changed")
        return LaneOccupancySnapshot("held" if held else "known", active, legacy,
                                     locked, unlocked,
                                     "reconciliation_hold_present" if held else "")
    except BlockingIOError:
        return LaneOccupancySnapshot("unknown", None, reason="admission_busy")
    except OSError:
        return LaneOccupancySnapshot("unknown", None, reason="census_unavailable")
    finally:
        if admission_fd is not None:
            os.close(admission_fd)


def _preexec_incident_contract(run_id=None):
    """Closed exact incident contracts; no caller-supplied release authority."""
    if run_id == 'native-host-review-22f77378-01a0e0c7':
        return ('native-host-review-22f77378-01a0e0c7', '01a0e0c7-1ed2-7fa0-a4b4-890d30ea6311', 'b17b0ca31f28', 'ff7b5bc29d6d2a72a7aa660af75176a2d9b65e12a05005fa5db1f5236c4c6d44'), {'schema': 'mastermind.exact-preexec-recovery.v1', 'run_id': 'native-host-review-22f77378-01a0e0c7', 'root_id': '01a0e0c7-1ed2-7fa0-a4b4-890d30ea6311', 'lease_id': 'b17b0ca31f28', 'host': 'ubuntu2', 'verdict': 'exec_argument_impossible', 'argument_bytes': 201147, 'page_size': 4096, 'packet_sha256': '898779496051a23123473d58c6c9f599ed4a541898d5a051029583e3da153d49', 'stdout_sha256': '755dbdc639c0f1c0ea5f84289026c4ab944209b404fa83951cf36210bb57e04a', 'support_digest': '3df14e1a295570df7519adec21acf65eba6dccee80b5ab9c1e6a68a570dfb4c9', 'boot_id': '64eea8d4-e0a9-4391-af46-c2f4b8c8cef7'}
    if run_id not in (None, "paper-01a1101f-qualifier-review-r2"):
        raise LaneRuntimeError("preexec_incident_refused")
    expected = ('paper-01a1101f-qualifier-review-r2',
     '01a1101f-2a37-7320-9a9b-5df3ce1b890d',
     'f29df7daea02',
     '52c06eb2ca15f7d96a3cd2a6b9f63a6216c210bec335bb067e7a91d9e721bf58')
    required = {'schema': 'mastermind.exact-preexec-recovery.v1',
     'run_id': 'paper-01a1101f-qualifier-review-r2',
     'root_id': '01a1101f-2a37-7320-9a9b-5df3ce1b890d',
     'lease_id': 'f29df7daea02',
     'host': 'ubuntu2',
     'verdict': 'exec_argument_impossible',
     'argument_bytes': 141778,
     'page_size': 4096,
     'packet_sha256': '1908b246109a7f31d7f51d1a2c4c50e85d870d4d21b4be18cc20aaf609558e45',
     'terminal_sha256': '2dbb189c835e067ba651cd5e37438bd6afe8c35827476425451e4c20b69dccbd',
     'support_digest': '0ff7c09a8a21d750e72f80a8a8be4db4bed957c68be10c0cf3c89c148544db05',
     'boot_id': '64eea8d4-e0a9-4391-af46-c2f4b8c8cef7'}
    return expected, required


def _preexec_original_identity(run_id):
    _preexec_incident_contract(run_id)
    if run_id == "native-host-review-22f77378-01a0e0c7":
        return 2553528, "2026-10-11T05:47:53.290Z"
    return 1479895, "2026-10-07T07:28:57.499Z"


def _preexec_service_bindings(run_id):
    # Only these exact systemd-owned processes may use the alternate public
    # identity proof. Unknown or changed services still fail the census.
    if run_id != "native-host-review-22f77378-01a0e0c7":
        return {}
    return {2558781: {'pid': 2558781, 'start_ticks': 124333108, 'excluded': 'verified_system_service', 'service': 'cups.service', 'invocation_id': '7b641283f8144d1dac369b8930eec7a1', 'uid': 0, 'cgroup': '/system.slice/cups.service'}, 2558786: {'pid': 2558786, 'start_ticks': 124333111, 'excluded': 'verified_system_service', 'service': 'cups-browsed.service', 'invocation_id': '83d73a28365748ca854f6c167fb6ee92', 'uid': 115, 'cgroup': '/system.slice/cups-browsed.service'}}


def validate_preexec_settlement_receipt(receipt) -> None:
    """Pure validation of the exact owner-emitted retained receipt.

    This checks bytes/shape/bindings, not current process absence or authority
    to settle an effect. The owner still requires its fresh proof callback,
    file custody, admission lock and marker CAS before any mutation.
    """
    import math
    expected, required = _preexec_incident_contract(receipt.get("run_id") if type(receipt) is dict else None)
    keys = {'schema', 'run_id', 'root_id', 'lease_id', 'marker_sha256',
            'original_lease', 'marker_identity', 'proof', 'census',
            'created_at', 'phase', 'receipt_sha256'}
    if type(receipt) is not dict or set(receipt) != keys:
        raise LaneRuntimeError('preexec_receipt_shape')
    material = dict(receipt)
    claimed = material.pop('receipt_sha256')
    try:
        encoded = json.dumps(material, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise LaneRuntimeError('preexec_receipt_binding') from exc
    proof = receipt['proof']
    created = receipt['created_at']
    try:
        valid_created = (type(created) in (int, float) and math.isfinite(created)
                         and created >= (1791697673.290 if expected[0] == "native-host-review-22f77378-01a0e0c7" else 1791358137.0))
    except OverflowError:
        valid_created = False
    if (len(encoded) > MAX_RECEIPT_FILE_BYTES
            or type(claimed) is not str or not re.fullmatch(r'[0-9a-f]{64}', claimed)
            or claimed != hashlib.sha256(encoded).hexdigest()
            or receipt['schema'] != 'mastermind.lane.preexec-settlement.v1'
            or receipt['phase'] != 'removal_authorized'
            or any(type(receipt[k]) is not str or receipt[k] != wanted
                   for k, wanted in zip(('run_id', 'root_id', 'lease_id', 'marker_sha256'), expected))
            or not valid_created
            or type(proof) is not dict or set(proof) != set(required)
            or any(type(proof[k]) is not type(wanted) or proof[k] != wanted
                   for k, wanted in required.items())
            or type(receipt['census']) is not list):
        raise LaneRuntimeError('preexec_receipt_binding')
    identity = receipt['marker_identity']
    if (type(identity) is not dict or set(identity) != {'device', 'inode'}
            or any(type(v) is not int or v < 0 for v in identity.values())):
        raise LaneRuntimeError('preexec_receipt_inode')
    original = receipt['original_lease']
    original_keys = {'schema', 'key', 'label', 'host', 'pid', 'started_at',
                     'source_sha256', 'admission', 'reconcile_unreleased'}
    original_binding = {'schema': LEASE_SCHEMA, 'key': expected[0],
                        'label': expected[0], 'host': 'ubuntu2', 'pid': _preexec_original_identity(expected[0])[0],
                        'started_at': _preexec_original_identity(expected[0])[1],
                        'reconcile_unreleased': True}
    if (type(original) is not dict or set(original) != original_keys
            or any(type(original[k]) is not type(wanted) or original[k] != wanted
                   for k, wanted in original_binding.items())
            or type(original['admission']) is not dict
            or (original['source_sha256'] is not None
                and (type(original['source_sha256']) is not str
                     or not re.fullmatch(r'[0-9a-f]{64}', original['source_sha256'])))):
        raise LaneRuntimeError('preexec_receipt_original')
    if expected[0] == "native-host-review-22f77378-01a0e0c7" and not receipt['census']:
        raise LaneRuntimeError('preexec_receipt_census')
    seen = set()
    for row in receipt['census']:
        if type(row) is dict and row.get('excluded') == 'verified_system_service':
            pid = row.get('pid')
            wanted = _preexec_service_bindings(expected[0]).get(pid) if type(pid) is int else None
            if (wanted is None or set(row) != set(wanted) or pid in seen
                    or any(type(row[k]) is not type(v) or row[k] != v for k,v in wanted.items())):
                raise LaneRuntimeError('preexec_receipt_census')
            seen.add(pid)
            continue
        if (type(row) is not dict
                or set(row) not in ({'pid', 'start_ticks', 'checked'},
                                    {'pid', 'start_ticks', 'excluded'})
                or type(row['pid']) is not int or row['pid'] <= 0
                or type(row['start_ticks']) is not int or row['start_ticks'] < 0
                or row['pid'] in seen
                or ('checked' in row and row['checked'] is not True)
                or ('excluded' in row and row['excluded'] not in
                    ('predates_attempt', 'probe_ancestor', 'verified_kernel_thread'))):
            raise LaneRuntimeError('preexec_receipt_census')
        seen.add(row['pid'])


def _linux_cpu_tctl_c() -> float | None:
    """Read one live AMD CPU Tctl sensor; unknown must block enrolled admission.

    This is a last-mile physical admission check, not another telemetry store
    or process controller. No caller may infer that a missing sensor is cool.
    """
    hwmon = Path("/sys/class/hwmon")
    try:
        chips = list(hwmon.glob("hwmon*"))
    except OSError:
        return None
    for chip in chips:
        try:
            if (chip / "name").read_text().strip() != "k10temp":
                continue
            for sensor in chip.glob("temp*_input"):
                label = sensor.with_name(sensor.name.replace("_input", "_label"))
                if label.read_text().strip() != "Tctl":
                    continue
                value = int(sensor.read_text().strip()) / 1000.0
                return value if 10 <= value <= 120 else None
        except (OSError, ValueError):
            continue
    return None


@dataclass(frozen=True)
class LaneReleaseReceipt:
    """Original physical release observation, never assignment/ACK authority."""
    schema: str
    key: str
    marker_device: int
    marker_inode: int
    parent_device: int
    parent_inode: int
    released_at: str
    marker_absent: bool
    parent_synced: bool


class LaneLease:
    def __init__(self, path: Path, fd: int, snapshot: HostAdmissionSnapshot,
                 reconciliation_binding: Mapping[str, Any] | None = None):
        self.path = path
        self.fd: int | None = fd
        self.snapshot = snapshot
        info = os.fstat(fd)
        self._device = info.st_dev
        self._inode = info.st_ino
        self._released = False
        self._preserve = False
        self._reconciliation_binding = dict(reconciliation_binding or {})
        self._hold_replaced = False
        self._assignment_release_attempted = False
        self._assignment_release_receipt = None
        self._assignment_release_lock_fd = None
        self._assignment_release_parent_fd = None
        self._assignment_release_failure = None
        self._assignment_owner_pid = os.getpid()
        self._assignment_owner_thread = threading.get_ident()
        # Optional observation only: constructing an ordinary legacy lease
        # keeps its old behavior. The finite release requires these preimages.
        self._assignment_parent_identity = None
        self._assignment_admission_identity = None
        try:
            parent = path.parent.lstat()
            lock = (path.parent / ".admission.lock").lstat()
            if stat.S_ISDIR(parent.st_mode) and stat.S_ISREG(lock.st_mode):
                self._assignment_parent_identity = (
                    parent.st_dev, parent.st_ino, parent.st_uid, parent.st_gid,
                    stat.S_IMODE(parent.st_mode))
                self._assignment_admission_identity = (
                    lock.st_dev, lock.st_ino, lock.st_uid, lock.st_gid,
                    stat.S_IMODE(lock.st_mode))
        except OSError:
            pass
        atexit.register(self.release)

    @classmethod
    def acquire(
        cls,
        active_dir: Path,
        *,
        key: str,
        label: str,
        max_active: int | None = None,
        load1: float | None = None,
        cpu_count: int | None = None,
        load_ratio_limit: float | None = None,
        source_sha256: str | None = None,
        env: Mapping[str, str] | None = None,
        reconcile_unreleased: bool = False,
    ) -> "LaneLease":
        if not isinstance(reconcile_unreleased, bool):
            raise LaneRuntimeConfigError("lane_reconcile_unreleased_invalid")
        if not _LABEL_RE.fullmatch(str(key)):
            raise LaneRuntimeConfigError("lane_key_invalid")
        cpus = int(cpu_count or os.cpu_count() or 1)
        config = load_runtime_config(env, cpu_count=cpus)
        minimum_free_memory = 0.0
        raw_memory_floor = (os.environ if env is None else env).get("LANE_MIN_FREE_MEM_GB", "0")
        try:
            minimum_free_memory = float(raw_memory_floor)
        except (ValueError, TypeError) as exc:
            raise LaneRuntimeConfigError("lane_min_free_mem_invalid") from exc
        if minimum_free_memory != minimum_free_memory or not 0 <= minimum_free_memory <= 256:
            raise LaneRuntimeConfigError("lane_min_free_mem_out_of_bounds")
        raw_tctl = (os.environ if env is None else env).get("LANE_MAX_CPU_TCTL_C", "0")
        try:
            cpu_tctl_limit = float(raw_tctl)
        except (ValueError, TypeError) as exc:
            raise LaneRuntimeConfigError("lane_cpu_tctl_limit_invalid") from exc
        if (not math.isfinite(cpu_tctl_limit)
                or (cpu_tctl_limit != 0 and not 50 <= cpu_tctl_limit <= 100)):
            raise LaneRuntimeConfigError("lane_cpu_tctl_limit_out_of_bounds")
        chosen_max = config.max_active if max_active is None else int(max_active)
        chosen_ratio = config.max_load_ratio if load_ratio_limit is None else float(load_ratio_limit)
        observed_load = float(os.getloadavg()[0] if load1 is None else load1)
        active_dir.mkdir(parents=True, exist_ok=True)
        admission_path = active_dir / ".admission.lock"
        admission_fd = os.open(admission_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(admission_fd, fcntl.LOCK_EX)
            # New immutable routing generations retain shared admission policy.
            # Recheck compatibility atomically before this physical marker exists.
            policy_here = Path(__file__).resolve().parent
            if os.path.lexists(policy_here / "pools.yaml"):
                try:
                    from fabric_policy_snapshot import verify_for_admission
                    verify_for_admission(policy_here, active_dir)
                except Exception as exc:
                    raise LaneRuntimeError("routing_policy_admission_refused") from exc
            snapshot = evaluate_admission(
                active_dir,
                max_active=chosen_max,
                load1=observed_load,
                cpu_count=cpus,
                load_ratio_limit=chosen_ratio,
                own_key=str(key),
            )
            if minimum_free_memory > 0:
                available_memory = None
                try:
                    with open("/proc/meminfo", encoding="utf-8") as info:
                        for line in info:
                            if line.startswith("MemAvailable:"):
                                available_memory = int(line.split()[1]) / (1024 * 1024)
                                break
                except (OSError, ValueError, IndexError):
                    pass
                if available_memory is None or available_memory < minimum_free_memory:
                    why = ("host_memory_unknown" if available_memory is None
                           else "host_memory_below_floor")
                    snapshot = HostAdmissionSnapshot(**{
                        **snapshot.public_dict(),
                        "allowed": False,
                        "reasons": tuple(dict.fromkeys((*snapshot.reasons, why))),
                    })
            # The picker uses cached thermal telemetry. Re-read the enrolled
            # CPU sensor under this SAME physical admission lock so new workers
            # cannot slip onto a hot host between fleet probes.
            if cpu_tctl_limit > 0:
                tctl = _linux_cpu_tctl_c()
                if tctl is None or tctl >= cpu_tctl_limit:
                    why = ("host_temperature_unknown" if tctl is None
                           else "host_temperature_at_or_above_limit")
                    snapshot = HostAdmissionSnapshot(**{
                        **snapshot.public_dict(),
                        "allowed": False,
                        "reasons": tuple(dict.fromkeys((*snapshot.reasons, why))),
                    })
            if not snapshot.allowed:
                raise LaneAdmissionRefused(snapshot)
            path = active_dir / str(key)
            flags = (
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            try:
                fd = os.open(path, flags, 0o600)
            except FileExistsError:
                duplicate = HostAdmissionSnapshot(
                    **{
                        **snapshot.public_dict(),
                        "allowed": False,
                        "reasons": tuple(
                            dict.fromkeys((*snapshot.reasons, "lane_key_already_active"))
                        ),
                    }
                )
                raise LaneAdmissionRefused(duplicate)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                observed = os.fstat(fd)
                visible = path.lstat()
                if (
                    not stat.S_ISREG(observed.st_mode)
                    or not stat.S_ISREG(visible.st_mode)
                    or (observed.st_dev, observed.st_ino)
                    != (visible.st_dev, visible.st_ino)
                ):
                    raise LaneRuntimeError("lane_marker_identity_mismatch")
                payload = {
                    "schema": LEASE_SCHEMA,
                    "key": str(key),
                    "label": _safe_label(label),
                    "pid": os.getpid(),
                    "started_at": _utc_now(),
                    "host": socket.gethostname().split(".")[0],
                    "source_sha256": source_sha256
                    if re.fullmatch(r"[0-9a-f]{64}", source_sha256 or "")
                    else None,
                    "admission": snapshot.public_dict(),
                }
                if reconcile_unreleased:
                    payload["reconcile_unreleased"] = True
                encoded = json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("utf-8")
                os.ftruncate(fd, 0)
                os.lseek(fd, 0, os.SEEK_SET)
                _write_all(fd, encoded)
                os.fsync(fd)
                _fsync_parent(path)
                if reconcile_unreleased:
                    return cls(path, fd, snapshot, reconciliation_binding=payload)
                return cls(path, fd, snapshot)
            except BaseException:
                try:
                    visible = path.lstat()
                    observed = os.fstat(fd)
                    if (
                        stat.S_ISREG(visible.st_mode)
                        and (visible.st_dev, visible.st_ino)
                        == (observed.st_dev, observed.st_ino)
                    ):
                        path.unlink()
                except (FileNotFoundError, OSError):
                    pass
                os.close(fd)
                raise
        finally:
            try:
                fcntl.flock(admission_fd, fcntl.LOCK_UN)
            finally:
                os.close(admission_fd)

    def hold_for_reconciliation(self, reason: str) -> None:
        if self._released or self.fd is None:
            raise LaneRuntimeError("lane_lease_not_live")
        if getattr(self, "_assignment_release_attempted", False) and self._preserve:
            # A finite release interruption already holds the SAME admission
            # lock/FDs. Reacquiring it on another FD deadlocks this owner; a
            # partial unlink must not be rewritten into fabricated hold history.
            return
        # Retention is sticky even if writing/syncing the hold fails. Otherwise
        # explicit release or atexit would erase custody with cleanup unproven.
        self._preserve = True
        if self._hold_replaced:
            return
        payload = {
            "schema": RECONCILIATION_HOLD_SCHEMA,
            "key": self.path.name,
            "reason": _safe_label(reason),
            "held_at": _utc_now(),
            "host": socket.gethostname().split(".")[0],
        }
        if self._reconciliation_binding:
            payload["original_lease"] = self._reconciliation_binding
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        if self._reconciliation_binding:
            # Keep the original, durably opted-in binding intact until a full
            # typed hold replaces it. A partial write must not lose its identity.
            admission_fd = os.open(self.path.parent / ".admission.lock", os.O_RDWR)
            temporary_fd = None
            temporary_path = None
            try:
                fcntl.flock(admission_fd, fcntl.LOCK_EX)
                temporary_fd, name = tempfile.mkstemp(prefix=".hold-", dir=self.path.parent)
                temporary_path = Path(name)
                os.ftruncate(temporary_fd, 0)
                os.lseek(temporary_fd, 0, os.SEEK_SET)
                _write_all(temporary_fd, encoded)
                os.fsync(temporary_fd)
                visible = self.path.lstat()
                if (visible.st_dev, visible.st_ino) != (self._device, self._inode):
                    raise LaneRuntimeError("lane_marker_identity_mismatch")
                os.replace(temporary_path, self.path)
                self._hold_replaced = True
                _fsync_parent(self.path)
            finally:
                try:
                    if temporary_fd is not None:
                        os.close(temporary_fd)
                    if temporary_path is not None:
                        try:
                            temporary_path.unlink()
                        except FileNotFoundError:
                            pass
                finally:
                    try:
                        fcntl.flock(admission_fd, fcntl.LOCK_UN)
                    finally:
                        os.close(admission_fd)
            return
        os.ftruncate(self.fd, 0)
        os.lseek(self.fd, 0, os.SEEK_SET)
        _write_all(self.fd, encoded)
        os.fsync(self.fd)
        _fsync_parent(self.path)

    @classmethod
    def reconcile_preexec_hold(cls, active_dir: Path, *, run_id: str, root_id: str,
                               lease_id: str, marker_sha256: str, proof,
                               mutate: bool = False) -> dict:
        """Exact incident host-owner edge; no provider/broker/normal admission.

        The proof callback is incumbent authenticated owner code, not user JSON.
        A durable removal authorization precedes unlink. Both crash windows are
        recoverable under the same lock with fresh proof and exact marker CAS.
        """
        import hashlib
        expected, expected_proof = _preexec_incident_contract(run_id)
        if (run_id, root_id, lease_id, marker_sha256) != expected or type(mutate) is not bool:
            raise LaneRuntimeError('preexec_incident_refused')
        active_dir = Path(active_dir)
        info = active_dir.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o002:
            raise LaneRuntimeError('preexec_directory_refused')
        if socket.gethostname().split('.')[0] != 'ubuntu2':
            raise LaneRuntimeError('preexec_host_refused')
        path = active_dir / run_id
        receipt_path = active_dir / ('.' + run_id + '.preexec-settlement.json')
        def digest(b): return hashlib.sha256(b).hexdigest()
        def encode(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        def open_safe(p, flags):
            fd = os.open(p, flags | os.O_NOFOLLOW | getattr(os, 'O_CLOEXEC', 0))
            s = os.fstat(fd); v = p.lstat()
            if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o022
                    or (s.st_dev, s.st_ino) != (v.st_dev, v.st_ino)):
                os.close(fd); raise LaneRuntimeError('preexec_file_custody')
            return fd
        lock_fd = open_safe(active_dir / '.admission.lock', os.O_RDWR)
        marker_fd = None
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            # Verify lock pathname again after acquisition, not only before wait.
            if (os.fstat(lock_fd).st_dev, os.fstat(lock_fd).st_ino) != ( (active_dir / '.admission.lock').lstat().st_dev, (active_dir / '.admission.lock').lstat().st_ino):
                raise LaneRuntimeError('preexec_admission_lock_changed')
            facts = proof()
            required = expected_proof
            if type(facts) is not dict or set(facts) != set(required) | {'census'} or any(type(facts[k]) is not type(v) or facts[k] != v for k,v in required.items()) or type(facts['census']) is not list:
                raise LaneRuntimeError('preexec_proof_refused')
            original = None
            if os.path.lexists(path):
                marker_fd = open_safe(path, os.O_RDWR)
                try: fcntl.flock(marker_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc: raise LaneRuntimeError('preexec_marker_live') from exc
                raw = os.read(marker_fd, 65537)
                if len(raw)>65536 or digest(raw)!=marker_sha256:
                    raise LaneRuntimeError('preexec_marker_changed')
                hold = json.loads(raw); original = hold.get('original_lease', {})
                if (hold.get('schema') != RECONCILIATION_HOLD_SCHEMA or hold.get('key') != run_id
                        or hold.get('host') != 'ubuntu2' or hold.get('reason') != 'worker_cleanup_unproven'
                        or original.get('schema') != LEASE_SCHEMA or original.get('key') != run_id
                        or original.get('label') != run_id or original.get('host') != 'ubuntu2'
                        or original.get('pid') != _preexec_original_identity(run_id)[0]
                        or original.get('started_at') != _preexec_original_identity(run_id)[1]
                        or original.get('reconcile_unreleased') is not True):
                    raise LaneRuntimeError('preexec_original_binding')
            receipt = None
            if os.path.lexists(receipt_path):
                fd = open_safe(receipt_path, os.O_RDONLY)
                try: raw_receipt = os.read(fd, 1048577)
                finally: os.close(fd)
                if len(raw_receipt)>1048576: raise LaneRuntimeError('preexec_receipt_large')
                receipt = json.loads(raw_receipt)
                validate_preexec_settlement_receipt(receipt)
                identity = receipt['marker_identity']
                if marker_fd is not None and identity != {'device':os.fstat(marker_fd).st_dev,'inode':os.fstat(marker_fd).st_ino}:
                    raise LaneRuntimeError('preexec_receipt_marker_replaced')
                binding = receipt['original_lease']
                if original is not None and original != binding:
                    raise LaneRuntimeError('preexec_receipt_marker_mismatch')
            if receipt is None:
                if marker_fd is None: raise LaneRuntimeError('preexec_no_marker_or_receipt')
                if not mutate: raise LaneRuntimeError('preexec_not_settled')
                receipt = {'schema':'mastermind.lane.preexec-settlement.v1','run_id':run_id,
                           'root_id':root_id,'lease_id':lease_id,'marker_sha256':marker_sha256,
                           'original_lease':original,'marker_identity':{'device':os.fstat(marker_fd).st_dev,'inode':os.fstat(marker_fd).st_ino},'proof':required,'census':facts['census'],'created_at':time.time(),
                           'phase':'removal_authorized'}
                receipt['receipt_sha256'] = digest(encode(receipt))
                validate_preexec_settlement_receipt(receipt)
                # Atomic publication avoids a partially written durable receipt.
                fd,name = tempfile.mkstemp(prefix='.preexec-', dir=active_dir)
                temp=Path(name)
                try:
                    _write_all(fd, encode(receipt)+b'\n');os.fsync(fd)
                    os.link(temp, receipt_path, follow_symlinks=False)
                    _fsync_parent(receipt_path)
                finally:
                    os.close(fd);temp.unlink()
            if marker_fd is not None:
                if not mutate: raise LaneRuntimeError('preexec_removal_pending')
                visible=path.lstat(); opened=os.fstat(marker_fd)
                os.lseek(marker_fd,0,os.SEEK_SET)
                if (visible.st_dev,visible.st_ino)!=(opened.st_dev,opened.st_ino) or digest(os.read(marker_fd,65537))!=marker_sha256:
                    raise LaneRuntimeError('preexec_marker_cas_changed')
                path.unlink();_fsync_parent(path)
            return {**receipt, 'settled':True}
        finally:
            if marker_fd is not None: os.close(marker_fd)
            fcntl.flock(lock_fd, fcntl.LOCK_UN);os.close(lock_fd)

    def release_after_assignment_ack(self) -> LaneReleaseReceipt:
        """Once-only physical release after the original owner verified its ACK.

        This method does NOT validate or mint an ACK. The Backend owns that
        separate authenticated evidence and may free its slot only after this
        actual observation returns. Legacy release remains unchanged. Unknown
        unlink/durability keeps the existing admission lock and descriptors,
        never recreates a missing marker or supplies restart reconciliation.
        """
        if (self._released or self._preserve or self.fd is None
                or self._assignment_release_attempted):
            raise LaneRuntimeError("lane_assignment_release_not_fresh")
        self._assignment_release_attempted = True
        directory_fd = admission_fd = None
        effect_possible = False
        def directory_identity(info):
            return (info.st_dev, info.st_ino, info.st_uid, info.st_gid,
                    stat.S_IMODE(info.st_mode))
        try:
            if (os.getpid() != self._assignment_owner_pid
                    or threading.get_ident() != self._assignment_owner_thread
                    or not self._reconciliation_binding
                    or self._reconciliation_binding.get("reconcile_unreleased") is not True
                    or self._reconciliation_binding.get("pid") != os.getpid()
                    or self._reconciliation_binding.get("key") != self.path.name
                    or not self.path.is_absolute()
                    or self._assignment_parent_identity is None
                    or self._assignment_admission_identity is None):
                raise LaneRuntimeError("lane_assignment_release_owner_unqualified")
            directory_fd = os.open(self.path.parent, os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
            parent = os.fstat(directory_fd)
            if (not stat.S_ISDIR(parent.st_mode)
                    or directory_identity(parent) != self._assignment_parent_identity
                    or directory_identity(self.path.parent.lstat()) != self._assignment_parent_identity):
                raise LaneRuntimeError("lane_assignment_release_parent_changed")
            admission_fd = os.open(".admission.lock", os.O_RDWR
                | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory_fd)
            lock = os.fstat(admission_fd)
            if (not stat.S_ISREG(lock.st_mode) or lock.st_nlink != 1
                    or directory_identity(lock) != self._assignment_admission_identity
                    or directory_identity(os.stat(".admission.lock", dir_fd=directory_fd,
                        follow_symlinks=False)) != self._assignment_admission_identity):
                raise LaneRuntimeError("lane_assignment_release_lock_changed")
            # Same existing physical admission lock; bounded refusal if another
            # original admission is in progress, not a second queue or retry.
            fcntl.flock(admission_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            opened = os.fstat(self.fd)
            visible = os.stat(self.path.name, dir_fd=directory_fd, follow_symlinks=False)
            expected = json.dumps(self._reconciliation_binding, sort_keys=True,
                separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            if (not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(visible.st_mode)
                    or opened.st_nlink != 1 or visible.st_nlink != 1
                    or (opened.st_dev, opened.st_ino) != (self._device, self._inode)
                    or directory_identity(opened) != directory_identity(visible)
                    or opened.st_size != len(expected)
                    or os.pread(self.fd, len(expected) + 1, 0) != expected
                    or directory_identity(self.path.parent.lstat()) != self._assignment_parent_identity):
                raise LaneRuntimeError("lane_assignment_release_marker_changed")
            effect_possible = True
            os.unlink(self.path.name, dir_fd=directory_fd)
            os.fsync(directory_fd)
            try:
                os.stat(self.path.name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise LaneRuntimeError("lane_assignment_release_marker_still_visible")
            if (directory_identity(os.fstat(directory_fd)) != self._assignment_parent_identity
                    or directory_identity(self.path.parent.lstat()) != self._assignment_parent_identity
                    or directory_identity(os.stat(".admission.lock", dir_fd=directory_fd,
                        follow_symlinks=False)) != self._assignment_admission_identity
                    or os.fstat(self.fd).st_nlink != 0):
                raise LaneRuntimeError("lane_assignment_release_readback_changed")
            fd = self.fd
            self.fd = None
            os.close(fd)
            value = LaneReleaseReceipt("mastermind.lane.owned_release/v1", self.path.name,
                self._device, self._inode, parent.st_dev, parent.st_ino, _utc_now(), True, True)
            # Keep admission excluded until the entire physical observation is
            # complete. A close failure is uncertainty, never a success receipt.
            os.close(directory_fd)
            directory_fd = None
            os.close(admission_fd)
            admission_fd = None
            self._assignment_release_receipt = value
            self._released = True
            return value
        except BaseException as exc:
            self._preserve = True
            self._assignment_release_failure = type(exc).__name__
            if effect_possible:
                self._assignment_release_lock_fd = admission_fd
                self._assignment_release_parent_fd = directory_fd
                admission_fd = directory_fd = None
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise LaneRuntimeError("lane_assignment_release_unknown") from exc
        finally:
            if admission_fd is not None:
                os.close(admission_fd)
            if directory_fd is not None:
                os.close(directory_fd)

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        fd = self.fd
        self.fd = None
        if fd is None:
            return
        try:
            if not self._preserve:
                try:
                    visible = self.path.lstat()
                    if (
                        stat.S_ISREG(visible.st_mode)
                        and (visible.st_dev, visible.st_ino)
                        == (self._device, self._inode)
                    ):
                        self.path.unlink()
                        _fsync_parent(self.path)
                except FileNotFoundError:
                    pass
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        finally:
            os.close(fd)

    def __enter__(self) -> "LaneLease":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.release()


__all__ = [
    "HostAdmissionSnapshot",
    "LaneOccupancySnapshot",
    "read_lane_occupancy",
    "LaneAdmissionRefused",
    "LaneLease",
    "LaneRuntimeConfig",
    "LaneRuntimeConfigError",
    "LaneRuntimeError",
    "ProcessCensusError",
    "OwnedProcessResult",
    "cancel_current_owned_process",
    "cleanup_receipt_is_proven",
    "evaluate_admission",
    "enforce_remote_first_lane_launch",
    "install_signal_cleanup",
    "load_runtime_config",
    "process_exists",
    "run_owned_process",
]


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["--occupancy"]:
        raise SystemExit("usage: lane_runtime.py --occupancy")
    occupancy = read_lane_occupancy(Path(__file__).resolve().parent / "active")
    print("active_lanes_status=" + occupancy.status)
    print("active_lanes=" + (str(occupancy.active_count) if occupancy.status == "known" else ""))
    print("lease_active_lanes=" + (str(occupancy.active_count) if occupancy.active_count is not None else ""))
    print("lease_legacy_lanes=" + str(occupancy.legacy_count))
    print("lease_locked_lanes=" + str(occupancy.json_locked_count))
    print("lease_unlocked_lanes=" + str(occupancy.unlocked_count))
    print("lease_reason=" + occupancy.reason)
