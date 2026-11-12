"""HostExecutor role + heartbeat pull semantics (MMOS V1 WO-15; Rev 4 S2 l.88-99, l.152-156).

One supervised executor per enrolled host.  The executor PULLS claims from
the coordinator only when a local slot is free (no work stealing, no host
queues), heartbeats ``HostReadinessSnapshot.v1`` (WO-04) on every pull, and
RECHECKS LOCAL PRESSURE BEFORE START -- a refusal releases the original
claim through the WO-14 pre-start path (``release_unstarted_claim``), never
launches, and never queues the work locally.

Hard rules encoded here:

* The SQLite engine stays coordinator-local (M2 Studio).  This module opens
  NO database on the worker; remote hosts speak the closed authenticated
  RPC framing below only.
* A STALE HOST GETS NO NEW CLAIMS: the coordinator-side intake refuses to
  claim when the heartbeat age exceeds ``no_new_claims_after_s`` (45 s).
* LEASE EXPIRY IS NEVER PROOF OF STOP (l.154): an expired lease only
  requires presence verification; the executor never reports a stop,
  kills, or releases a run on expiry alone.
* launchd/systemd ownership of supervised processes is preserved: the
  executor owns no daemon lifecycle and spawns no supervisors.

This module is deliberately STDLIB-ONLY and importable standalone (python >=
3.9) so the worker side can run verbatim on an enrolled remote host with a
plain interpreter.  Coordinator-side integration (WO-14 placement authority,
Executive Runtime) is imported lazily inside the intake so importing this
file on a worker never pulls the Mastermind package.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _datetime
import json
import math
import os
import platform
import re
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

# --- closed schemas -------------------------------------------------------------

HOST_READINESS_SNAPSHOT_SCHEMA = "mastermind.host_readiness_snapshot/v1"
HOST_EXECUTOR_REQUEST_SCHEMA = "mastermind.host_executor_request/v1"
HOST_EXECUTOR_RESPONSE_SCHEMA = "mastermind.host_executor_response/v1"
HOST_EXECUTOR_OPERATIONS = frozenset({"heartbeat/v1", "heartbeat-pull/v1", "release-unstarted/v1"})
HEARTBEAT_OPERATION = "heartbeat/v1"
HEARTBEAT_PULL_OPERATION = "heartbeat-pull/v1"
RELEASE_UNSTARTED_OPERATION = "release-unstarted/v1"
RELEASE_REASON_LOCAL_PRESSURE = "local pressure recheck refused"
MAX_RPC_FRAME_BYTES = 256 * 1024
MAX_HEARTBEAT_LEDGER_BYTES = 8 * 1024 * 1024

DEFAULT_HEARTBEAT_S = 15
DEFAULT_NO_NEW_CLAIMS_AFTER_S = 45
DEFAULT_MEMORY_RESERVE_GIB = 4.0
DEFAULT_RUNTIME_FLOOR_GIB = 20.0
# Refuse a start when the 1-minute load already exceeds the logical core
# count (load ratio > 1.0): the host is saturated, not merely busy.
DEFAULT_PRESSURE_REFUSE_LOAD_RATIO = 1.0

MEMORY_RESERVE_FORMULA = "max(4, 0.10 * ram_gib)"
SLOTS_DERIVATION = "worker_slots = min(floor(cores/2), floor((ram_gib - max(4, 0.10*ram_gib)) / 6))"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_SNAPSHOT_REQUIRED_KEYS = frozenset({
    "schema", "host_id", "role", "reachable", "collected_at", "observed_at_utc",
    "cores", "ram_gib", "disk_free_gib", "load_1m", "uptime_s", "os", "python",
    "runtimes_present", "thermal", "proposed_worker_slots", "slots_derivation",
    "eligible_slots", "proposed_thresholds", "unreachable_error",
})
_SNAPSHOT_OPTIONAL_KEYS = frozenset({"boot_epoch_s"})
_THERMAL_ALLOWED = frozenset({"unknown", "nominal", "elevated", "critical"})
_RUNTIME_KEYS = frozenset({"hermes", "opencode", "deepseek"})
_THRESHOLD_KEYS = frozenset({
    "heartbeat_s", "no_new_claims_after_s", "memory_reserve_gib", "runtime_floor_gib",
})
_REQUEST_KEYS = frozenset({"schema", "request_id", "operation", "payload"})
_RESPONSE_KEYS = frozenset({"schema", "request_id", "operation", "ok", "result"})
_ERROR_RESPONSE_KEYS = frozenset({"schema", "request_id", "operation", "ok", "error"})
_PULL_PAYLOAD_KEYS = frozenset({"host_id", "snapshot", "free_local_slots"})
_HEARTBEAT_PAYLOAD_KEYS = frozenset({"host_id", "snapshot"})
_RELEASE_PAYLOAD_KEYS = frozenset({
    "host_id", "attempt_id", "fence_generation", "lease_token", "reason",
})


class HostExecutorError(ValueError):
    """A closed, non-secret HostExecutor contract refusal."""


def _utc_now_iso() -> str:
    return _datetime.datetime.now(_datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_to_ms(value: str) -> int:
    parsed = _datetime.datetime.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ")
    return int(parsed.replace(tzinfo=_datetime.timezone.utc).timestamp() * 1000)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)


def _digest(value: Any) -> str:
    import hashlib

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


# --- HostReadinessSnapshot.v1 validation ----------------------------------------


def validate_host_readiness_snapshot(value: Any) -> dict[str, Any]:
    """Validate one WO-04 ``HostReadinessSnapshot.v1`` projection.

    Mirrors the WO-04 host census groups (``mmos/hosts/*.json``).  An
    unreachable host is forced to ``eligible_slots == 0`` and a thermal
    reading without sensor evidence must be ``unknown`` -- never healthy
    (Rev 4 l.150).
    """

    if not isinstance(value, dict):
        raise HostExecutorError("SNAPSHOT_NOT_OBJECT")
    keys = set(value)
    missing = _SNAPSHOT_REQUIRED_KEYS - keys
    extra = keys - _SNAPSHOT_REQUIRED_KEYS - _SNAPSHOT_OPTIONAL_KEYS
    if missing or extra:
        raise HostExecutorError("SNAPSHOT_FIELDS_INVALID")
    if value["schema"] != HOST_READINESS_SNAPSHOT_SCHEMA:
        raise HostExecutorError("SNAPSHOT_SCHEMA_UNSUPPORTED")
    host_id = value["host_id"]
    if not isinstance(host_id, str) or not _ID_RE.fullmatch(host_id):
        raise HostExecutorError("SNAPSHOT_HOST_ID_INVALID")
    if value["role"] not in ("worker", "coordinator"):
        raise HostExecutorError("SNAPSHOT_ROLE_INVALID")
    for stamp in (value["collected_at"], value["observed_at_utc"]):
        if not isinstance(stamp, str) or not _ISO_RE.fullmatch(stamp):
            raise HostExecutorError("SNAPSHOT_TIMESTAMP_INVALID")
    if value["reachable"] is not True:
        if value["reachable"] is not False:
            raise HostExecutorError("SNAPSHOT_REACHABLE_INVALID")
        if value["unreachable_error"] is None:
            raise HostExecutorError("SNAPSHOT_UNREACHABLE_REASON_MISSING")
    elif value["unreachable_error"] is not None:
        raise HostExecutorError("SNAPSHOT_UNREACHABLE_REASON_PRESENT")
    if type(value["cores"]) is not int or value["cores"] <= 0:
        raise HostExecutorError("SNAPSHOT_CORES_INVALID")
    for field in ("ram_gib", "load_1m"):
        number = value[field]
        if not isinstance(number, (int, float)) or isinstance(number, bool) or number < 0:
            raise HostExecutorError("SNAPSHOT_NUMERIC_INVALID")
    disk = value["disk_free_gib"]
    if not isinstance(disk, dict) or set(disk) != {"root", "runtime_dir", "runtime_dir_path"}:
        raise HostExecutorError("SNAPSHOT_DISK_INVALID")
    if not isinstance(disk["root"], (int, float)) or isinstance(disk["root"], bool) or disk["root"] < 0:
        raise HostExecutorError("SNAPSHOT_DISK_INVALID")
    if disk["runtime_dir"] is not None and (
        not isinstance(disk["runtime_dir"], (int, float))
        or isinstance(disk["runtime_dir"], bool)
        or disk["runtime_dir"] < 0
    ):
        raise HostExecutorError("SNAPSHOT_DISK_INVALID")
    if disk["runtime_dir_path"] is not None and (
        not isinstance(disk["runtime_dir_path"], str) or not disk["runtime_dir_path"].strip()
    ):
        raise HostExecutorError("SNAPSHOT_DISK_INVALID")
    if disk["runtime_dir"] is not None and disk["runtime_dir_path"] is None:
        raise HostExecutorError("SNAPSHOT_DISK_INVALID")
    if type(value["uptime_s"]) is not int or value["uptime_s"] < 0:
        raise HostExecutorError("SNAPSHOT_UPTIME_INVALID")
    for field in ("os", "python"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise HostExecutorError("SNAPSHOT_TEXT_INVALID")
    if not isinstance(value["runtimes_present"], dict) or set(value["runtimes_present"]) != _RUNTIME_KEYS:
        raise HostExecutorError("SNAPSHOT_RUNTIMES_INVALID")
    if value["thermal"] not in _THERMAL_ALLOWED:
        raise HostExecutorError("SNAPSHOT_THERMAL_INVALID")
    for field in ("proposed_worker_slots", "eligible_slots"):
        if type(value[field]) is not int or value[field] < 0:
            raise HostExecutorError("SNAPSHOT_SLOTS_INVALID")
    if value["slots_derivation"] != SLOTS_DERIVATION:
        raise HostExecutorError("SNAPSHOT_DERIVATION_INVALID")
    thresholds = value["proposed_thresholds"]
    if not isinstance(thresholds, dict) or set(thresholds) != _THRESHOLD_KEYS:
        raise HostExecutorError("SNAPSHOT_THRESHOLDS_INVALID")
    for field in ("heartbeat_s", "no_new_claims_after_s"):
        if type(thresholds[field]) is not int or not 1 <= thresholds[field] <= 3600:
            raise HostExecutorError("SNAPSHOT_THRESHOLDS_INVALID")
    reserve = thresholds["memory_reserve_gib"]
    if isinstance(reserve, str):
        if reserve != MEMORY_RESERVE_FORMULA:
            raise HostExecutorError("SNAPSHOT_THRESHOLDS_INVALID")
    elif isinstance(reserve, (int, float)) and not isinstance(reserve, bool):
        if reserve < DEFAULT_MEMORY_RESERVE_GIB:
            raise HostExecutorError("SNAPSHOT_THRESHOLDS_INVALID")
    else:
        raise HostExecutorError("SNAPSHOT_THRESHOLDS_INVALID")
    floor = thresholds["runtime_floor_gib"]
    if not isinstance(floor, (int, float)) or isinstance(floor, bool) or floor < 0:
        raise HostExecutorError("SNAPSHOT_THRESHOLDS_INVALID")
    if value["reachable"] is not True and value["eligible_slots"] != 0:
        raise HostExecutorError("SNAPSHOT_UNREACHABLE_MUST_HAVE_ZERO_SLOTS")
    return dict(value)


def snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    return _digest(validate_host_readiness_snapshot(dict(snapshot)))


def snapshot_age_ms(snapshot: Mapping[str, Any], *, now_ms: int) -> int:
    observed = _iso_to_ms(str(snapshot.get("observed_at_utc")))
    return now_ms - observed


# --- closed RPC framing ----------------------------------------------------------


def build_request(operation: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if operation not in HOST_EXECUTOR_OPERATIONS:
        raise HostExecutorError("OPERATION_NOT_ALLOWED")
    if operation == HEARTBEAT_PULL_OPERATION:
        _validate_pull_payload(payload)
    elif operation == HEARTBEAT_OPERATION:
        _validate_heartbeat_payload(payload)
    else:
        _validate_release_payload(payload)
    return {
        "schema": HOST_EXECUTOR_REQUEST_SCHEMA,
        "request_id": f"hx-{uuid.uuid4().hex}",
        "operation": operation,
        "payload": json.loads(canonical_json(dict(payload))),
    }


def _require(request: Any, *, expected_schema: str) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise HostExecutorError("REQUEST_NOT_OBJECT")
    if request.get("schema") != expected_schema:
        raise HostExecutorError("REQUEST_SCHEMA_UNSUPPORTED")
    return request


def validate_request(value: Any) -> dict[str, Any]:
    request = _require(value, expected_schema=HOST_EXECUTOR_REQUEST_SCHEMA)
    if set(request) != _REQUEST_KEYS:
        raise HostExecutorError("REQUEST_FIELDS_INVALID")
    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not re.fullmatch(r"^hx-[0-9a-f]{32}$", request_id):
        raise HostExecutorError("REQUEST_ID_INVALID")
    operation = request.get("operation")
    if operation not in HOST_EXECUTOR_OPERATIONS:
        raise HostExecutorError("OPERATION_NOT_ALLOWED")
    payload = request.get("payload")
    if not isinstance(payload, dict):
        raise HostExecutorError("PAYLOAD_NOT_OBJECT")
    if operation == HEARTBEAT_PULL_OPERATION:
        _validate_pull_payload(payload)
    elif operation == HEARTBEAT_OPERATION:
        _validate_heartbeat_payload(payload)
    else:
        _validate_release_payload(payload)
    return request


def build_response(request: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": HOST_EXECUTOR_RESPONSE_SCHEMA,
        "request_id": request["request_id"],
        "operation": request["operation"],
        "ok": True,
        "result": json.loads(canonical_json(dict(result))),
    }


def build_error_response(request: Mapping[str, Any], code: str, detail: str = "") -> dict[str, Any]:
    return {
        "schema": HOST_EXECUTOR_RESPONSE_SCHEMA,
        "request_id": request.get("request_id") if isinstance(request, dict) else "invalid",
        "operation": request.get("operation") if isinstance(request, dict) else "invalid",
        "ok": False,
        "error": {"code": str(code), "detail": str(detail)[:500]},
    }


def validate_response(value: Any, *, request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HostExecutorError("RESPONSE_NOT_OBJECT")
    if type(value.get("ok")) is not bool:
        raise HostExecutorError("RESPONSE_OK_INVALID")
    expected_keys = _RESPONSE_KEYS if value["ok"] else _ERROR_RESPONSE_KEYS
    if set(value) != expected_keys:
        raise HostExecutorError("RESPONSE_FIELDS_INVALID")
    if value["schema"] != HOST_EXECUTOR_RESPONSE_SCHEMA:
        raise HostExecutorError("RESPONSE_SCHEMA_UNSUPPORTED")
    if value["request_id"] != request.get("request_id") or value["operation"] != request.get("operation"):
        raise HostExecutorError("RESPONSE_IDENTITY_MISMATCH")
    if value["ok"] is not True:
        error = value.get("error")
        if (not isinstance(error, dict) or set(error) != {"code", "detail"}
                or not isinstance(error["code"], str) or not error["code"]
                or not isinstance(error["detail"], str)):
            raise HostExecutorError("RESPONSE_ERROR_INVALID")
        raise HostExecutorError(f"REMOTE_REFUSED:{error['code']}")
    if not isinstance(value["result"], dict):
        raise HostExecutorError("RESPONSE_RESULT_INVALID")
    return value


def encode_frame(document: Mapping[str, Any]) -> bytes:
    raw = (canonical_json(document) + "\n").encode("utf-8")
    if len(raw) > MAX_RPC_FRAME_BYTES:
        raise HostExecutorError("FRAME_TOO_LARGE")
    return raw


def decode_frame(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_RPC_FRAME_BYTES or not raw.endswith(b"\n"):
        raise HostExecutorError("FRAME_INVALID")
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HostExecutorError("FRAME_NOT_JSON") from exc
    if not isinstance(document, dict):
        raise HostExecutorError("FRAME_NOT_OBJECT")
    return document


def _validate_pull_payload(payload: Mapping[str, Any]) -> None:
    if set(payload) != _PULL_PAYLOAD_KEYS:
        raise HostExecutorError("PAYLOAD_FIELDS_INVALID")
    _validate_host_and_snapshot(payload)
    if type(payload["free_local_slots"]) is not int or payload["free_local_slots"] < 0:
        raise HostExecutorError("PAYLOAD_FREE_LOCAL_SLOTS_INVALID")


def _validate_heartbeat_payload(payload: Mapping[str, Any]) -> None:
    if set(payload) != _HEARTBEAT_PAYLOAD_KEYS:
        raise HostExecutorError("PAYLOAD_FIELDS_INVALID")
    _validate_host_and_snapshot(payload)


def _validate_host_and_snapshot(payload: Mapping[str, Any]) -> None:
    host_id = payload.get("host_id")
    if not isinstance(host_id, str) or not _ID_RE.fullmatch(host_id):
        raise HostExecutorError("PAYLOAD_HOST_ID_INVALID")
    snapshot = validate_host_readiness_snapshot(payload.get("snapshot"))
    if snapshot["host_id"] != host_id:
        raise HostExecutorError("PAYLOAD_HOST_MISMATCH")


def _validate_release_payload(payload: Mapping[str, Any]) -> None:
    if set(payload) != _RELEASE_PAYLOAD_KEYS:
        raise HostExecutorError("PAYLOAD_FIELDS_INVALID")
    host_id = payload.get("host_id")
    if not isinstance(host_id, str) or not _ID_RE.fullmatch(host_id):
        raise HostExecutorError("PAYLOAD_HOST_ID_INVALID")
    if not isinstance(payload.get("attempt_id"), str) or not payload["attempt_id"]:
        raise HostExecutorError("PAYLOAD_ATTEMPT_INVALID")
    if type(payload.get("fence_generation")) is not int or payload["fence_generation"] < 0:
        raise HostExecutorError("PAYLOAD_FENCE_INVALID")
    if not isinstance(payload.get("lease_token"), str) or not payload["lease_token"]:
        raise HostExecutorError("PAYLOAD_LEASE_TOKEN_INVALID")
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 256:
        raise HostExecutorError("PAYLOAD_REASON_INVALID")


# --- local readiness probe (worker side; user-space reads only) ------------------


def _logical_cores() -> int:
    try:
        affinity = len(os.sched_getaffinity(0))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        affinity = 0
    return max(affinity, os.cpu_count() or 1)


def _memory_gib_linux() -> tuple[float, float]:
    total = available = 0.0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    total = float(line.split()[1]) / 1024 ** 2
                elif line.startswith("MemAvailable:"):
                    available = float(line.split()[1]) / 1024 ** 2
    except OSError:
        return 0.0, 0.0
    return total, available


def _memory_gib_macos() -> tuple[float, float]:
    import subprocess

    try:
        total = int(subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
            timeout=10, check=True,
        ).stdout.strip()) / 1024 ** 3
    except (OSError, subprocess.SubprocessError, ValueError):
        total = 0.0
    # No unprivileged MemAvailable equivalent on macOS; page stats are a
    # lower bound (free + inactive + speculative), reported as-is.
    available = 0.0
    try:
        pagesize = int(subprocess.run(
            ["sysctl", "-n", "vm.pagesize"], capture_output=True, text=True,
            timeout=10, check=True,
        ).stdout.strip())
        counts: dict[str, int] = {}
        vm = subprocess.run(
            ["vm_stat"], capture_output=True, text=True, timeout=10, check=True,
        ).stdout
        for line in vm.splitlines():
            match = re.match(r"^" + r"(.+?):\s+(\d+)\.", line.strip())
            if match:
                counts[match.group(1)] = int(match.group(2))
        freeish = sum(counts.get(key, 0) for key in
                      ("Pages free", "Pages inactive", "Pages speculative"))
        available = freeish * pagesize / 1024 ** 3
    except (OSError, subprocess.SubprocessError, ValueError):
        available = 0.0
    return total, available


def _uptime_seconds() -> int:
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as handle:
            return int(float(handle.read().split()[0]))
    except (OSError, ValueError, IndexError):
        pass
    import subprocess

    try:  # macOS
        boot = subprocess.run(
            ["sysctl", "-n", "kern.boottime"], capture_output=True, text=True,
            timeout=10, check=True,
        ).stdout
        stamp = re.search(r"sec = (\d+)", boot)
        if stamp:
            return max(0, int(time.time()) - int(stamp.group(1)))
    except (OSError, subprocess.SubprocessError):
        pass
    return 0


def probe_host_readiness(
    host_id: str,
    *,
    role: str = "worker",
    eligible_slots: int = 0,
    runtime_dir: str | os.PathLike[str] | None = None,
    thresholds: Mapping[str, Any] | None = None,
    now_iso: str | None = None,
) -> dict[str, Any]:
    """Collect one real ``HostReadinessSnapshot.v1`` from this host.

    User-space reads only (``/proc``, ``sysctl``, ``shutil.disk_usage``);
    no sudo, no daemons touched.  An unreadable group reports 0.0/unknown,
    never a healthy guess: thermal is ``unknown`` until a sensor evidence
    source exists (Rev 4 l.150).
    """

    settings = dict(thresholds or {})
    heartbeat_s = int(settings.get("heartbeat_s") or DEFAULT_HEARTBEAT_S)
    no_new_claims_after_s = int(
        settings.get("no_new_claims_after_s") or DEFAULT_NO_NEW_CLAIMS_AFTER_S
    )
    runtime_floor_gib = float(settings.get("runtime_floor_gib") or DEFAULT_RUNTIME_FLOOR_GIB)
    reserve = settings.get("memory_reserve_gib", MEMORY_RESERVE_FORMULA)

    cores = _logical_cores()
    if sys.platform == "darwin":
        ram_gib, mem_available_gib = _memory_gib_macos()
    else:
        ram_gib, mem_available_gib = _memory_gib_linux()

    try:
        load_1m = float(os.getloadavg()[0])
    except (OSError, ValueError):
        load_1m = 0.0

    runtime_path = str(runtime_dir) if runtime_dir is not None else os.path.expanduser("~/.hermes")
    root_free = shutil.disk_usage(os.path.expanduser("~")).free / 1024 ** 3
    runtime_free = None
    if runtime_path and os.path.isdir(runtime_path):
        runtime_free = shutil.disk_usage(runtime_path).free / 1024 ** 3

    hermes_bin = shutil.which("hermes") or (
        os.path.join(runtime_path, "hermes-agent", ".hermes", "bin", "hermes")
        if runtime_path else None
    )

    observed = now_iso or _utc_now_iso()
    ram = ram_gib if ram_gib > 0 else 0.0
    proposed = _derive_worker_slots(cores, ram)
    snapshot = {
        "schema": HOST_READINESS_SNAPSHOT_SCHEMA,
        "host_id": host_id,
        "role": role,
        "reachable": True,
        "collected_at": observed,
        "observed_at_utc": observed,
        "cores": cores,
        "ram_gib": round(ram, 2),
        "disk_free_gib": {
            "root": round(root_free, 2),
            "runtime_dir": round(runtime_free, 2) if runtime_free is not None else None,
            "runtime_dir_path": runtime_path if runtime_free is not None else None,
        },
        "load_1m": round(load_1m, 2),
        "uptime_s": _uptime_seconds(),
        "os": " ".join(platform.uname()),
        "python": platform.python_version(),
        "runtimes_present": {
            "hermes": hermes_bin if hermes_bin and os.path.exists(hermes_bin) else None,
            "opencode": shutil.which("opencode"),
            "deepseek": shutil.which("deepseek"),
        },
        "thermal": "unknown",
        "proposed_worker_slots": proposed,
        "slots_derivation": SLOTS_DERIVATION,
        "eligible_slots": max(0, int(eligible_slots)),
        "proposed_thresholds": {
            "heartbeat_s": heartbeat_s,
            "no_new_claims_after_s": no_new_claims_after_s,
            "memory_reserve_gib": reserve,
            "runtime_floor_gib": runtime_floor_gib,
        },
        "unreachable_error": None,
        "boot_epoch_s": int(time.time()) - _uptime_seconds(),
    }
    # Non-public detail channel for the local pressure recheck; stripped by
    # validate_host_readiness_snapshot consumers that re-canonicalize.
    snapshot["_mem_available_gib"] = round(mem_available_gib, 2)
    return snapshot


def _derive_worker_slots(cores: int, ram_gib: float) -> int:
    """WO-04 census formula: min(floor(cores/2), floor((ram - reserve)/6))."""

    if cores <= 0 or ram_gib <= 0:
        return 0
    reserve = max(DEFAULT_MEMORY_RESERVE_GIB, 0.10 * ram_gib)
    return max(0, min(cores // 2, int((ram_gib - reserve) // 6)))


def public_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """The wire form of a snapshot: schema-valid, private fields stripped."""

    return {k: v for k, v in snapshot.items() if not k.startswith("_")}


# --- worker-side executor ---------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ClaimAssignment:
    """At most ONE claim per pull; carried, never queued."""

    attempt_id: str
    job_id: str
    worker_id: str
    host_id: str
    fence_generation: int
    lease_token: str
    lease_expires_at_ms: int
    execution_binding: Mapping[str, Any] | None


@dataclasses.dataclass(frozen=True)
class PullOutcome:
    claimed: ClaimAssignment | None
    reason_code: str
    detail: str = ""
    heartbeat_digest: str = ""
    contacted_coordinator: bool = False


@dataclasses.dataclass(frozen=True)
class LeaseExpiryDisposition:
    """Lease expiry is NEVER proof of stop (Rev 4 l.154)."""

    proof_of_stop: bool
    release_allowed: bool
    requires_presence_verification: bool

    def __post_init__(self) -> None:
        if self.proof_of_stop or self.release_allowed or not self.requires_presence_verification:
            raise HostExecutorError("LEASE_EXPIRY_IS_NOT_PROOF_OF_STOP")


class HostExecutor:
    """One supervised executor bound to ONE enrolled host (WO-15).

    Pull semantics only: ``pull_once`` contacts the coordinator ONLY when a
    local slot is free, receives AT MOST ONE claim, holds no queue, and
    never steals work addressed to another host.  Before starting an
    accepted claim the executor RECHECKS LOCAL PRESSURE; a refusal releases
    the claim back to the WO-14 authority instead of launching.  The
    executor opens no database: all durable state is coordinator-local
    (M2), reached only through the authenticated ``transport``.
    """

    def __init__(
        self,
        *,
        host_id: str,
        eligible_slots: int,
        transport: Any = None,
        thresholds: Mapping[str, Any] | None = None,
        runtime_dir: str | os.PathLike[str] | None = None,
        probe: Callable[..., dict[str, Any]] = probe_host_readiness,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(host_id, str) or not _ID_RE.fullmatch(host_id):
            raise HostExecutorError("host_id is invalid")
        if type(eligible_slots) is not int or eligible_slots < 0:
            raise HostExecutorError("eligible_slots must be a non-negative integer")
        self.host_id = host_id
        self.eligible_slots = eligible_slots
        self.transport = transport
        self.thresholds = dict(thresholds or {})
        self._probe = probe
        self._clock = clock
        self._runtime_dir = runtime_dir
        # Locally accepted, still-running claims only.  This is a slot
        # accounting set, NOT a work queue: entries exist only after a claim
        # was accepted and started, and are removed on completion.
        self._active_attempts: dict[str, ClaimAssignment] = {}
        self.last_heartbeat: dict[str, Any] | None = None

    # -- heartbeat ---------------------------------------------------------

    def heartbeat(self) -> dict[str, Any]:
        """Probe local readiness and remember the snapshot (WO-04 shape)."""

        snapshot = validate_host_readiness_snapshot(public_snapshot(self._probe(
            self.host_id, role="worker", eligible_slots=self.eligible_slots,
            runtime_dir=self._runtime_dir, thresholds=self.thresholds,
        )))
        self.last_heartbeat = snapshot
        return snapshot

    # -- local pressure recheck ---------------------------------------------

    def _memory_reserve_gib(self, ram_gib: float) -> float:
        reserve = self.thresholds.get(
            "memory_reserve_gib", (self.last_heartbeat or {}).get(
                "proposed_thresholds", {}
            ).get("memory_reserve_gib", MEMORY_RESERVE_FORMULA),
        )
        if isinstance(reserve, str):
            return max(DEFAULT_MEMORY_RESERVE_GIB, 0.10 * ram_gib)
        return max(DEFAULT_MEMORY_RESERVE_GIB, float(reserve))

    def local_pressure_ok(
        self, snapshot: Mapping[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Recheck local pressure BEFORE start (Rev 4 l.129/l.148).

        Refuses when: load ratio exceeds the ceiling, available memory is
        below the reserve, or the runtime disk is under the floor.  Unknown
        readings (0.0 on macOS memory probes without evidence) do not pass
        silently when the reserve cannot be evaluated -- they refuse.
        """

        raw = snapshot if snapshot is not None else self._probe(
            self.host_id, role="worker", eligible_slots=self.eligible_slots,
            runtime_dir=self._runtime_dir, thresholds=self.thresholds,
        )
        ram_gib = float(raw.get("ram_gib") or 0.0)
        available = raw.get("_mem_available_gib")
        mem_available_gib = float(available) if available is not None else None
        cores = int(raw.get("cores") or 0)
        load_1m = float(raw.get("load_1m") or 0.0)
        if cores > 0 and load_1m / cores > DEFAULT_PRESSURE_REFUSE_LOAD_RATIO:
            return False, f"load ratio {load_1m / cores:.2f} exceeds core count"
        reserve = self._memory_reserve_gib(ram_gib)
        if mem_available_gib is None:
            # No trustworthy availability reading: recheck must not guess.
            if ram_gib > 0:
                return False, "memory availability unknown at recheck"
        elif mem_available_gib < reserve:
            return False, f"memory available {mem_available_gib:.1f} GiB below reserve {reserve:.1f} GiB"
        disk = raw.get("disk_free_gib")
        runtime_free = disk.get("runtime_dir") if isinstance(disk, Mapping) else None
        if (not isinstance(runtime_free, (int, float)) or isinstance(runtime_free, bool)
                or not math.isfinite(runtime_free)):
            return False, "runtime disk availability unknown at recheck"
        floor = float(self.thresholds.get(
            "runtime_floor_gib", (raw.get("proposed_thresholds") or {}).get(
                "runtime_floor_gib", DEFAULT_RUNTIME_FLOOR_GIB),
        ))
        if float(runtime_free) < floor:
            return False, f"runtime disk {float(runtime_free):.1f} GiB below floor {floor:.1f} GiB"
        return True, ""

    # -- slots ----------------------------------------------------------------

    def free_local_slots(self) -> int:
        return max(0, self.eligible_slots - len(self._active_attempts))

    # -- pull -----------------------------------------------------------------

    def pull_once(self) -> PullOutcome:
        """Pull AT MOST one claim, only when a local slot is free.

        No free slot means NO contact with the coordinator at all -- an
        occupied host neither asks for nor receives work (no stealing, no
        queues).  A claim addressed to another host is refused and never
        stored.
        """

        snapshot = self.heartbeat()
        digest = snapshot_digest(snapshot)
        if self.free_local_slots() <= 0:
            return PullOutcome(
                claimed=None, reason_code="NO_FREE_LOCAL_SLOT",
                detail=f"{len(self._active_attempts)}/{self.eligible_slots} slots busy",
                heartbeat_digest=digest, contacted_coordinator=False,
            )
        if self.transport is None:
            return PullOutcome(
                claimed=None, reason_code="NO_CONTROL_PATH",
                detail="no authenticated transport configured",
                heartbeat_digest=digest, contacted_coordinator=False,
            )
        request = build_request(HEARTBEAT_PULL_OPERATION, {
            "host_id": self.host_id,
            "snapshot": snapshot,
            "free_local_slots": self.free_local_slots(),
        })
        response = validate_response(self.transport.call(request), request=request)
        result = response["result"]
        if set(result) != {"claim", "reason_code", "detail", "heartbeat_digest"}:
            raise HostExecutorError("RESPONSE_RESULT_INVALID")
        if result["heartbeat_digest"] != digest:
            raise HostExecutorError("HEARTBEAT_DIGEST_MISMATCH")
        if result["claim"] is not None:
            assignment = self._assignment_from_claim(result["claim"])
            if assignment is None:
                return PullOutcome(
                    claimed=None, reason_code="CLAIM_HOST_MISMATCH",
                    detail="coordinator offered a claim for a foreign host",
                    heartbeat_digest=digest, contacted_coordinator=True,
                )
            return PullOutcome(
                claimed=assignment, reason_code="CLAIMED",
                detail=assignment.attempt_id, heartbeat_digest=digest,
                contacted_coordinator=True,
            )
        return PullOutcome(
            claimed=None, reason_code=str(result["reason_code"]),
            detail=str(result.get("detail") or ""), heartbeat_digest=digest,
            contacted_coordinator=True,
        )

    def _assignment_from_claim(self, claim: Any) -> ClaimAssignment | None:
        if not isinstance(claim, dict) or set(claim) != {
            "attempt_id", "job_id", "worker_id", "host_id", "fence_generation",
            "lease_token", "lease_expires_at_ms", "execution_binding",
        }:
            raise HostExecutorError("CLAIM_FIELDS_INVALID")
        if claim["host_id"] != self.host_id:
            return None  # never steal: a foreign claim is refused, not queued
        for field in ("attempt_id", "job_id", "worker_id", "host_id", "lease_token"):
            if not isinstance(claim[field], str) or not claim[field]:
                raise HostExecutorError("CLAIM_FIELDS_INVALID")
        if type(claim["fence_generation"]) is not int or claim["fence_generation"] < 0:
            raise HostExecutorError("CLAIM_FIELDS_INVALID")
        if type(claim["lease_expires_at_ms"]) is not int:
            raise HostExecutorError("CLAIM_FIELDS_INVALID")
        if claim["execution_binding"] is not None and not isinstance(claim["execution_binding"], dict):
            raise HostExecutorError("CLAIM_FIELDS_INVALID")
        return ClaimAssignment(
            attempt_id=claim["attempt_id"], job_id=claim["job_id"],
            worker_id=claim["worker_id"], host_id=claim["host_id"],
            fence_generation=claim["fence_generation"], lease_token=claim["lease_token"],
            lease_expires_at_ms=claim["lease_expires_at_ms"],
            execution_binding=claim["execution_binding"],
        )

    # -- pre-start recheck + release -------------------------------------------

    def start_claimed(self, assignment: ClaimAssignment) -> tuple[bool, str]:
        """Recheck local pressure BEFORE start; refuse => release, never launch.

        On refusal the ORIGINAL claim is released exactly once through the
        WO-14 pre-start path (coordinator-owned).  The executor never
        queues, retries, or hands the claim to another host.
        """

        if assignment.attempt_id in self._active_attempts:
            raise HostExecutorError("attempt already active on this executor")
        ok, detail = self.local_pressure_ok()
        if ok:
            self._active_attempts[assignment.attempt_id] = assignment
            return True, ""
        released = self.release_unstarted(assignment, RELEASE_REASON_LOCAL_PRESSURE)
        if not released:
            raise HostExecutorError(
                "pre-start refusal could not release the original claim; claim retained"
            )
        return False, detail

    def release_unstarted(self, assignment: ClaimAssignment, reason: str) -> bool:
        """Return an unstarted claim to the WO-14 authority (exactly once)."""

        if self.transport is None:
            return False
        request = build_request(RELEASE_UNSTARTED_OPERATION, {
            "host_id": self.host_id,
            "attempt_id": assignment.attempt_id,
            "fence_generation": assignment.fence_generation,
            "lease_token": assignment.lease_token,
            "reason": reason,
        })
        response = validate_response(self.transport.call(request), request=request)
        result = response["result"]
        if set(result) != {"released"} or result["released"] is not True:
            raise HostExecutorError("RELEASE_RESULT_INVALID")
        self._active_attempts.pop(assignment.attempt_id, None)
        return True

    def complete_attempt(self, attempt_id: str) -> None:
        self._active_attempts.pop(attempt_id, None)

    # -- lease expiry semantics ---------------------------------------------------

    def lease_expired(self, assignment: ClaimAssignment, *, now_ms: int | None = None) -> LeaseExpiryDisposition:
        """Expiry alone proves NOTHING (Rev 4 l.154).

        An expired lease never authorizes this executor to stop, report,
        kill, or forget the run.  It only demands presence verification
        through the authenticated process controller; reconciliation is
        owned by the coordinator + supervisor, not by the executor.
        """

        now = now_ms if now_ms is not None else int(self._clock() * 1000)
        if now >= assignment.lease_expires_at_ms:
            return LeaseExpiryDisposition(
                proof_of_stop=False, release_allowed=False,
                requires_presence_verification=True,
            )
        return LeaseExpiryDisposition(
            proof_of_stop=False, release_allowed=False,
            requires_presence_verification=True,
        )


# --- coordinator-side intake (M2; the SQLite engine stays HERE) -------------------


class HostHeartbeatIntake:
    """Coordinator-side receiver for executor heartbeats and claim pulls.

    Runs on the coordinator (M2 Studio) only.  Every durable effect --
    heartbeat ledger rows, WO-14 claims, pre-start releases -- happens in
    coordinator-local storage; the worker side of the protocol carries the
    closed JSON framing and nothing else.  The claim path delegates to the
    SOLE placement authority (``AttemptRegistry.claim_job``, OQ-1) with
    frozen observations built from the pulling host's own heartbeat: a
    stale or not-ready heartbeat yields ZERO new claims, never a degraded
    placement.
    """

    def __init__(
        self,
        *,
        runtime: Any = None,
        shared_quota_provider: Callable[[], Mapping[str, Any]] | None = None,
        ledger_path: str | os.PathLike[str] | None = None,
        allowed_hosts: Sequence[str] | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self._runtime = runtime
        self._shared_quota_provider = shared_quota_provider
        self._ledger_path = Path(ledger_path) if ledger_path is not None else None
        self._allowed_hosts = frozenset(allowed_hosts) if allowed_hosts is not None else None
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.latest: dict[str, dict[str, Any]] = {}
        self.received_count = 0

    # -- heartbeat record ------------------------------------------------------

    def _record(self, request: Mapping[str, Any], *, received_at_utc: str) -> dict[str, Any]:
        payload = request["payload"]
        snapshot = payload["snapshot"]
        entry = {
            "received_at_utc": received_at_utc,
            "host_id": snapshot["host_id"],
            "schema": snapshot["schema"],
            "observed_at_utc": snapshot["observed_at_utc"],
            "collected_at": snapshot["collected_at"],
            "reachable": snapshot["reachable"],
            "eligible_slots": snapshot["eligible_slots"],
            "proposed_worker_slots": snapshot["proposed_worker_slots"],
            "cores": snapshot["cores"],
            "ram_gib": snapshot["ram_gib"],
            "load_1m": snapshot["load_1m"],
            "uptime_s": snapshot["uptime_s"],
            "snapshot_digest": snapshot_digest(snapshot),
            "request_id": request["request_id"],
            "operation": request["operation"],
        }
        self.latest[entry["host_id"]] = entry
        self.received_count += 1
        if self._ledger_path is not None:
            self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self._ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(canonical_json(entry) + "\n")
        return entry

    # -- claim gating -------------------------------------------------------------

    def _claim_gate(
        self, snapshot: Mapping[str, Any], *, now_ms: int,
    ) -> tuple[bool, str, str]:
        """STALE HOST => NO NEW CLAIMS (Rev 4 l.129/l.148; WO-15)."""

        host_id = snapshot["host_id"]
        if self._allowed_hosts is not None and host_id not in self._allowed_hosts:
            return False, "HOST_NOT_ENROLLED", host_id
        if snapshot.get("reachable") is not True:
            return False, "HOST_NOT_REACHABLE", host_id
        eligible = snapshot.get("eligible_slots")
        if type(eligible) is not int or eligible <= 0:
            return False, "HOST_SLOTS_EXHAUSTED", f"eligible_slots={eligible}"
        thresholds = snapshot.get("proposed_thresholds") or {}
        max_age_s = int(thresholds.get("no_new_claims_after_s") or DEFAULT_NO_NEW_CLAIMS_AFTER_S)
        age_ms = snapshot_age_ms(snapshot, now_ms=now_ms)
        if age_ms < 0 or age_ms > max_age_s * 1000:
            return (
                False, "HOST_HEARTBEAT_STALE",
                f"heartbeat age {max(0, age_ms) // 1000}s > {max_age_s}s",
            )
        return True, "", ""

    # -- request handling ----------------------------------------------------------

    def receive(self, request: Any, *, now_ms: int | None = None) -> dict[str, Any]:
        now = now_ms if now_ms is not None else self._clock_ms()
        try:
            valid = validate_request(request)
        except HostExecutorError as exc:
            return build_error_response(
                request if isinstance(request, dict) else {}, str(exc),
            )
        operation = valid["operation"]
        payload = valid["payload"]
        if operation == RELEASE_UNSTARTED_OPERATION:
            return self._release_unstarted(valid, payload, now_ms=now)
        snapshot = payload["snapshot"]
        record = self._record(valid, received_at_utc=_ms_to_iso(now))
        if operation == HEARTBEAT_OPERATION:
            return build_response(valid, {
                "recorded": True,
                "received_at_utc": record["received_at_utc"],
                "snapshot_digest": record["snapshot_digest"],
            })
        ok, code, detail = self._claim_gate(snapshot, now_ms=now)
        if not ok:
            # Zero new claims: the placement authority is never consulted.
            return build_response(valid, {
                "claim": None, "reason_code": code, "detail": detail,
                "heartbeat_digest": record["snapshot_digest"],
            })
        if payload["free_local_slots"] == 0:
            # Readiness capacity is not evidence of an available local slot.
            # Keep the heartbeat, but do not enter the claim authority.
            return build_response(valid, {
                "claim": None, "reason_code": "NO_FREE_LOCAL_SLOT",
                "detail": "free_local_slots=0",
                "heartbeat_digest": record["snapshot_digest"],
            })
        claim, reason_code, reason_detail = self._claim_for_host(
            snapshot, now_ms=now,
        )
        return build_response(valid, {
            "claim": claim, "reason_code": reason_code, "detail": reason_detail,
            "heartbeat_digest": record["snapshot_digest"],
        })

    def receive_frame(self, raw: bytes, *, now_ms: int | None = None) -> bytes:
        try:
            document = decode_frame(raw)
        except HostExecutorError as exc:
            return encode_frame(build_error_response({}, str(exc)))
        return encode_frame(self.receive(document, now_ms=now_ms))

    # -- the sole placement authority (WO-14, OQ-1) --------------------------------

    def _claim_for_host(
        self, snapshot: Mapping[str, Any], *, now_ms: int,
    ) -> tuple[Mapping[str, Any] | None, str, str]:
        runtime = self._runtime
        if runtime is None:
            return None, "COORDINATOR_RUNTIME_UNAVAILABLE", "no coordinator Runtime configured"
        from control_plane.executive_placement_authority import (
            CHILD_PLACEMENT_KEY, HostObservation, PlacementObservations,
        )

        try:
            host_observation = HostObservation.from_host_readiness_snapshot(dict(snapshot))
        except (ValueError, KeyError, TypeError):
            return None, "HOST_OBSERVATION_INVALID", "heartbeat did not project"

        # Bounded scan: one pull examines at most the first 16 queued
        # child-placement Jobs; anything else stays with the COO owner.
        examined = 0
        for job in runtime.jobs.list_jobs():
            if getattr(job.status, "value", job.status) != "QUEUED":
                continue
            spec = (job.constraints or {}).get(CHILD_PLACEMENT_KEY)
            if not isinstance(spec, dict):
                continue
            examined += 1
            if examined > 16:
                break
            shared_quota = self._shared_quota_snapshot(spec, now_ms=now_ms)
            observations = PlacementObservations(
                registry_revision=str(spec["registry_revision"]),
                observed_at_ms=host_observation.observed_at_ms,
                hosts={host_observation.host_id: host_observation},
                shared_quota=shared_quota,
            )
            lease_owner = f"host-executor:{host_observation.host_id}"
            try:
                lease = runtime.attempts.claim_job(
                    job.job_id, placement_observations=observations,
                    lease_owner=lease_owner,
                )
            except Exception as exc:  # typed refusal, never a crash of intake
                return None, "CLAIM_REFUSED", f"{type(exc).__name__}: {exc}"[:200]
            if lease is None:
                reason = runtime.attempts.placement_wait_reason(job.job_id)
                code = reason["reason_code"] if reason else "NO_CLAIM"
                detail = reason.get("detail", "") if reason else ""
                continue  # this Job cannot place here; try the next queued Job
            return self._claim_payload(runtime, lease, host_id=host_observation.host_id), "CLAIMED", ""
        return None, "NO_ELIGIBLE_JOB", "no queued child-placement Job for this host"

    def _shared_quota_snapshot(self, spec: Mapping[str, Any], *, now_ms: int) -> dict[str, Any]:
        refs = list(spec.get("shared_quota_resource_refs") or ())
        if self._shared_quota_provider is None:
            return {}
        observed = dict(self._shared_quota_provider() or {})
        return {ref: observed[ref] for ref in refs if ref in observed}

    @staticmethod
    def _claim_payload(runtime: Any, lease: Any, *, host_id: str) -> dict[str, Any]:
        attempt = lease.attempt
        binding = None
        try:
            binding = runtime.attempts.execution_binding(attempt.attempt_id)
        except Exception:
            binding = None
        return {
            "attempt_id": attempt.attempt_id,
            "job_id": attempt.job_id,
            "worker_id": str(attempt.worker_id),
            "host_id": host_id,
            "fence_generation": int(attempt.fence_generation),
            "lease_token": str(lease.lease_token),
            "lease_expires_at_ms": _iso_ms_of(attempt.lease_expires_at),
            "execution_binding": binding,
        }

    # -- pre-start release (WO-14 path) ----------------------------------------------

    def _release_unstarted(
        self, request: Mapping[str, Any], payload: Mapping[str, Any], *, now_ms: int,
    ) -> dict[str, Any]:
        """Return an executor-refused unstarted claim to the WO-14 authority.

        The executor's lease token + fence prove the claim it holds; the
        coordinator releases the ORIGINAL claim exactly once.  A typed
        runtime refusal (stale fence, already released, orchestration Job)
        is returned as a typed error, never retried here.
        """

        runtime = self._runtime
        if runtime is None:
            return build_error_response(request, "COORDINATOR_RUNTIME_UNAVAILABLE")
        try:
            runtime.attempts.release_unstarted_claim(
                payload["attempt_id"],
                fence_generation=payload["fence_generation"],
                lease_token=payload["lease_token"],
                reason=payload["reason"],
            )
        except Exception as exc:
            return build_error_response(
                request, "RELEASE_REFUSED", f"{type(exc).__name__}: {exc}",
            )
        return build_response(request, {"released": True})


def _ms_to_iso(value: int) -> str:
    moment = _datetime.datetime.fromtimestamp(value / 1000, tz=_datetime.timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_ms_of(value: Any) -> int:
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = _datetime.datetime.fromisoformat(text)
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_datetime.timezone.utc)
    return int(parsed.timestamp() * 1000)


# --- CLI ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """Worker heartbeat path + coordinator receive path.

    Worker (on the enrolled host, supervised or invoked through the
    authenticated control channel):

        python3 executive_host_executor.py --host-id ubuntu0 --eligible-slots 4 \\
            --runtime-dir ~/.hermes --heartbeat

    Coordinator (M2; reads ONE framed request from stdin, records the
    heartbeat, answers the pull):

        python3 -m control_plane.executive_host_executor --receive \\
            --ledger mmos/heartbeats.jsonl
    """

    parser = argparse.ArgumentParser(prog="executive_host_executor")
    parser.add_argument("--host-id", help="enrolled host identity")
    parser.add_argument("--eligible-slots", type=int, default=0)
    parser.add_argument("--runtime-dir", default=None)
    parser.add_argument("--heartbeat", action="store_true",
                        help="probe local readiness and emit one heartbeat pull request")
    parser.add_argument("--receive", action="store_true",
                        help="coordinator: read one framed request from stdin")
    parser.add_argument("--ledger", default=None, help="coordinator heartbeat ledger path")
    parser.add_argument("--no-pull", action="store_true",
                        help="heartbeat only (heartbeat/v1, no claim pull)")
    args = parser.parse_args(argv)

    if args.receive:
        raw = sys.stdin.buffer.readline()
        intake = HostHeartbeatIntake(ledger_path=args.ledger)
        sys.stdout.buffer.write(intake.receive_frame(raw))
        sys.stdout.buffer.flush()
        return 0

    if args.heartbeat:
        if not args.host_id:
            parser.error("--host-id is required for --heartbeat")
        operation = HEARTBEAT_OPERATION if args.no_pull else HEARTBEAT_PULL_OPERATION
        snapshot = probe_host_readiness(
            args.host_id, eligible_slots=args.eligible_slots,
            runtime_dir=args.runtime_dir,
        )
        payload: dict[str, Any] = {"host_id": args.host_id, "snapshot": public_snapshot(snapshot)}
        if operation == HEARTBEAT_PULL_OPERATION:
            payload["free_local_slots"] = max(0, args.eligible_slots)
        request = build_request(operation, payload)
        sys.stdout.buffer.write(encode_frame(request))
        sys.stdout.buffer.flush()
        return 0

    parser.error("choose --heartbeat or --receive")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
