#!/usr/bin/env python3
"""Focused local safety for the existing Meta-CEO external lane.

This module is deliberately not a scheduler, queue, provider registry, or durable
Job/Attempt store.  It owns only the lifetime of subprocesses created by the
current Python process and admission locks in the lane's pre-existing active/
directory.  Unknown processes are never terminated by heuristic.
"""
from __future__ import annotations

import atexit
import errno
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
# 2026-10-13: the env floor is strictly positive, in parity with the local registry check
# (0 < load_gate <= cores * MAX_LOAD_RATIO). The former 0.5 floor rejected the Chairman's
# thermal-headroom gate (load1 8 on 32 cores = 0.25) with lane_max_load_ratio_out_of_bounds
# BEFORE admission, killing every new lane on those hosts while the picker scored them eligible.
MIN_LOAD_RATIO = 0.0  # exclusive
MAX_LOAD_RATIO = 1.5
MIN_NICE = 0
MAX_NICE = 19
_LABEL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class LaneRuntimeError(RuntimeError):
    """Base class for bounded local-lane safety failures."""


class OwnedProcessStartError(LaneRuntimeError):
    """Qualified direct-argv executable-not-found or permission-denied failure.

    Only the supported exec-error-pipe shape may produce this verdict.
    An arbitrary Popen OSError does not prove that no child started.
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
    if not MIN_LOAD_RATIO < max_load_ratio <= MAX_LOAD_RATIO:
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
        members, identity_ok = _verified_group_members(expected_pgid)
        if not identity_ok:
            raise ProcessCensusError("process_group_session_identity_mismatch")
        if len(members) > MAX_OWNED_PROCESS_GROUP_MEMBERS:
            return "process_limit"
        if not members:
            if proc.poll() is not None:
                return "completed"
            raise ProcessCensusError(
                "process_group_census_empty_while_leader_live"
            )


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
        _kill_exact_leader(proc, grace=max(0.2, grace))
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
            _kill_exact_leader(proc, grace=2.0)
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


class _BoundedStreamCollector:
    """Drain one child pipe without allowing output volume to grow storage."""

    def __init__(self, stream: Any, limit_bytes: int, name: str):
        self.stream = stream
        self.limit_bytes = int(limit_bytes)
        self.name = name
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
) -> dict[str, Any]:
    cleanup = dict(cleanup)
    cleanup["stdout_capture_complete"] = stdout_complete
    cleanup["stderr_capture_complete"] = stderr_complete
    cleanup["stdin_delivery_complete"] = stdin_complete
    cleanup["stdout_capture_error"] = stdout_error
    cleanup["stderr_capture_error"] = stderr_error
    cleanup["stdin_delivery_error"] = stdin_error
    if stdout_complete and stderr_complete and stdin_complete:
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


def _qualified_owned_process_exec_failure(command, exc, *, shell: bool) -> bool:
    """Recognize only the standard direct-argv exec-error-pipe failure shape.

    Popen may raise a parent-side OSError after forking. Constructor location
    alone is not proof that execution never started; shell and other argument
    shapes remain unproven here.
    """
    return (
        shell is False
        and type(command) in (list, tuple)
        and bool(command)
        and all(type(arg) is str for arg in command)
        and (
            (type(exc) is FileNotFoundError and exc.errno == errno.ENOENT)
            or (type(exc) is PermissionError and exc.errno == errno.EACCES)
        )
        and type(exc.filename) is str
        and exc.filename == command[0]
        and exc.filename2 is None
    )


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
    started_at = _utc_now()
    input_bytes = input_text.encode("utf-8") if input_text is not None else None
    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell,
            executable=_owned_shell() if shell else None,
            env=dict(env) if env is not None else None,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        if _qualified_owned_process_exec_failure(command, exc, shell=shell):
            raise OwnedProcessStartError(exc.errno) from None
        raise LaneRuntimeError("owned_process_start_unproven") from None
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

    stdout_collector = _BoundedStreamCollector(
        proc.stdout, int(capture_limit_bytes), "stdout"
    )
    stderr_collector = _BoundedStreamCollector(
        proc.stderr, int(capture_limit_bytes), "stderr"
    )
    stdout_collector.start()
    stderr_collector.start()
    stdin_thread: threading.Thread | None = None
    stdin_state: dict[str, Any] = {"complete": True, "error_code": None}
    if input_bytes is not None:
        if proc.stdin is None:
            _terminate_verified_group(proc, pgid, grace=0.2, reason="stdin_missing")
            _clear_current(proc)
            raise LaneRuntimeError("owned_stdin_stream_missing")
        stdin_thread, stdin_state = _start_input_writer(proc.stdin, input_bytes)

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
            wait_outcome = _wait_owned_process_with_fuse(proc, pgid, timeout)
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
        _clear_current(proc)
        capture_deadline = time.monotonic() + max(
            0.25, min(2.0, terminate_grace + 0.25)
        )
        if stdin_thread is not None:
            stdin_thread.join(max(0.0, capture_deadline - time.monotonic()))
        stdin_complete = stdin_thread is None or (
            not stdin_thread.is_alive() and bool(stdin_state.get("complete"))
        )
        stdout, stdout_bytes, stdout_truncated, stdout_complete, stdout_error = (
            stdout_collector.finish(max(0.0, capture_deadline - time.monotonic()))
        )
        stderr, stderr_bytes, stderr_truncated, stderr_complete, stderr_error = (
            stderr_collector.finish(max(0.0, capture_deadline - time.monotonic()))
        )
        cleanup = _mark_stream_state_unproven(
            cleanup,
            stdout_complete=stdout_complete,
            stderr_complete=stderr_complete,
            stdin_complete=stdin_complete,
            stdout_error=stdout_error,
            stderr_error=stderr_error,
            stdin_error=stdin_state.get("error_code"),
        )
        ended_at = _utc_now()
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
    )

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
    """Read AMD Tctl or hottest Intel CPU package temperature from Linux hwmon.

    For enrolled hosts, missing or untrustworthy package thermals refuse
    new work under the incumbent LaneLease lock; never infer a cool host.
    Core temperatures are not interchangeable with package observations.
    """
    hwmon = Path("/sys/class/hwmon")
    try:
        chips = list(hwmon.glob("hwmon*"))
    except OSError:
        return None
    amd_tctl = None
    intel_packages: list[float] = []
    for chip in chips:
        try:
            kind = (chip / "name").read_text().strip()
            if kind not in ("k10temp", "coretemp"):
                continue
            for sensor in chip.glob("temp*_input"):
                label = sensor.with_name(sensor.name.replace("_input", "_label"))
                label_value = label.read_text().strip()
                is_amd = kind == "k10temp" and label_value == "Tctl"
                is_intel = kind == "coretemp" and label_value.startswith("Package id ")
                if not is_amd and not is_intel:
                    continue
                value = int(sensor.read_text().strip()) / 1000.0
                if not math.isfinite(value) or not 10 <= value <= 120:
                    continue
                if is_amd:
                    amd_tctl = value if amd_tctl is None else max(amd_tctl, value)
                else:
                    intel_packages.append(value)
        except (OSError, ValueError, OverflowError):
            continue
    return amd_tctl if amd_tctl is not None else (
        max(intel_packages) if intel_packages else None
    )

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
        raw_disk_floor = (os.environ if env is None else env).get("LANE_MIN_FREE_DISK_GB", "0")
        try:
            minimum_free_disk = float(raw_disk_floor)
        except (ValueError, TypeError) as exc:
            raise LaneRuntimeConfigError("lane_min_free_disk_invalid") from exc
        if not math.isfinite(minimum_free_disk) or not 0 <= minimum_free_disk <= 2048:
            raise LaneRuntimeConfigError("lane_min_free_disk_out_of_bounds")
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
            if minimum_free_disk > 0:
                # The incumbent admission lock guards the last-mile check. For
                # Linux lanes active_dir is ~/lanes/ext/active, so ~/lanes/wt
                # must be on the same actual volume. Unknown/mismatch HOLD.
                # resolve(): remote lanes run from an immutable support release
                # whose ext/active is a SYMLINK to ~/lanes/ext/active; the
                # unresolved parent.parent is the release root (no wt there), so
                # every remote lane HELD host_disk_unknown (C19 seat 7ab343c8,
                # 2026-10-13T14:4xZ; backup .bak-pre-wt-resolve-20261013-c19).
                checkout_dir = active_dir.resolve().parent.parent / "wt"
                free_disk_gib = None
                reason_unknown = "host_disk_unknown"
                try:
                    observed = checkout_dir.lstat()
                    if stat.S_ISDIR(observed.st_mode):
                        active_dev = active_dir.stat().st_dev
                        if observed.st_dev == active_dev:
                            usage = os.statvfs(checkout_dir)
                            free_disk_gib = (usage.f_bavail * usage.f_frsize) / (1024 ** 3)
                        else:
                            reason_unknown = "host_disk_volume_mismatch"
                except (OSError, ValueError, OverflowError):
                    pass
                if free_disk_gib is None or free_disk_gib < minimum_free_disk:
                    why = (
                        reason_unknown if free_disk_gib is None
                        else "host_disk_below_staging_reserve"
                    )
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
