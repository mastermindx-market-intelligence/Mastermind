#!/usr/bin/env python3
"""Thin native-feeling CLI adapter over the incumbent Subagent Fabric owners.

This module owns no scheduler, queue, background retry, idempotency database, provider
credential, host placement policy, or worker lifecycle. It composes pick.py,
remote_sub.sh, the existing per-run log/result artifacts, and pool_ledger.py.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import pick
import pool_ledger
import a04_terminal_reconcile as terminal_reconcile
import native_completion_reconcile as completion_reconcile
import native_prestart_reconcile as prestart_reconcile
import native_preexec_reconcile as preexec_reconcile
import native_host_review_controller_reconcile as native_review_reconcile

HERE = Path(__file__).resolve().parent
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
MAX_LOG_BYTES = 1_048_576
DEFAULT_RESULT_BYTES = 1_048_576
MAX_RESULT_BYTES = 8_388_608
_DONE_RE = re.compile(r"\bDONE rc=([0-9]+) signal=([A-Za-z0-9_.:-]+)")
_REMOTE_DONE_RE = re.compile(r"\bREMOTE_DONE rc=([0-9]+)")
_PRELAUNCH_RC_RE = re.compile(r"\b(?:NO_HOST|[A-Z0-9_]+_(?:FAILED|REFUSED))\b[^\n]*\brc=([0-9]+)")
_GLM_AUTH_GUARD_RE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z "
    r"\[remote_sub id=(?P<run>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}) "
    r"host=(?P<host>[A-Za-z0-9_.-]+)\] "
    r"GLM_REMOTE_AUTH_UNAVAILABLE host=(?P=host)"
)


class FabricTaskError(RuntimeError):
    pass


# Closed diagnostics only: these labels grant no routing, retry or acceptance.
# Never retain arbitrary picker text, provider output, paths or account detail.
_REQUEST_REFUSAL_CODES = frozenset({
    "NO_OPERATOR_AVAILABLE", "NO_POOL_AVAILABLE", "NO_ROUTE",
    "ROUTE_INCOMPLETE", "REQUEST_ROUTING_RETURN_UNQUALIFIED",
    "REQUEST_MAX_TURNS_INVALID", "REQUEST_MAX_TURNS_ROUTE_UNSUPPORTED",
    "ECONOMIC_POLICY_REFUSED", "UNCLASSIFIED_PRELAUNCH_REFUSAL",
})


def _safe_request_refusal_code(exc: BaseException) -> str:
    unknown = "UNCLASSIFIED_PRELAUNCH_REFUSAL"
    if type(exc) is not FabricTaskError:
        return unknown
    args = exc.args
    if not args or type(args[0]) is not str or len(args[0]) > 1024:
        return unknown
    message = args[0]
    # The deadline-aware picker runs in an owned subprocess. It returns only
    # this fixed no-operator marker; historical receipts omitted the cause.
    if message == "NONE reason=no_operator_available":
        return "NO_OPERATOR_AVAILABLE"
    if message == "NONE reason=no_pool_available":
        return "NO_POOL_AVAILABLE"
    code = message.partition(":")[0]
    return code if code in _REQUEST_REFUSAL_CODES else unknown


def validate_run_id(value: object) -> str:
    token = str(value or "").strip()
    if not RUN_ID_RE.fullmatch(token):
        raise ValueError("invalid run id")
    return token


def resolve_request_root(root_id: str | None, env: dict[str, str]) -> str | None:
    """Select a transport default, never an authentication or custody proof."""
    if root_id is not None:
        return validate_run_id(root_id)
    if "CODEX_THREAD_ID" in env:
        if not env["CODEX_THREAD_ID"]:
            raise FabricTaskError("CODEX_ROOT_REQUIRES_EXPLICIT_VERIFIED_ROOT")
        native_root = validate_run_id(env["CODEX_THREAD_ID"])
        inherited = env.get("POOL_ORCHESTRATOR_ID")
        if inherited and validate_run_id(inherited) != native_root:
            raise FabricTaskError("ROOT_BINDING_CONFLICT: use an explicit verified root")
        return native_root
    if "CODEX_SESSION_ID" in env:
        raise FabricTaskError("CODEX_ROOT_REQUIRES_EXPLICIT_VERIFIED_ROOT")
    inherited = env.get("POOL_ORCHESTRATOR_ID") or env.get("CLAUDE_SESSION_ID")
    return validate_run_id(inherited) if inherited else None


def _bounded_regular(path: Path, limit: int) -> bytes:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise FabricTaskError("artifact is not a regular file")
    if info.st_size > limit:
        raise FabricTaskError("artifact exceeds bounded read limit")
    # Validate and read the same inode. O_NONBLOCK prevents a raced FIFO from
    # hanging before fstat can reject it; O_NOFOLLOW rejects a raced symlink.
    # This is local file-integrity checking, not producer or parent attestation.
    def identity(value: os.stat_result) -> tuple[int, ...]:
        return (value.st_dev, value.st_ino, value.st_size,
                value.st_mtime_ns, value.st_ctime_ns)

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or identity(opened) != identity(info):
            raise FabricTaskError("artifact changed before read")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        retained = path.lstat()
        if (identity(os.fstat(descriptor)) != identity(opened)
                or not stat.S_ISREG(retained.st_mode)
                or identity(retained) != identity(opened)
                or len(data) != opened.st_size):
            raise FabricTaskError("artifact changed during read")
    finally:
        os.close(descriptor)
    if len(data) > limit:
        raise FabricTaskError("artifact exceeds bounded read limit")
    return data


def _paths(run_id: str, *, owner_ext: Path | None = None) -> tuple[Path, Path]:
    rid = validate_run_id(run_id)
    here = HERE if owner_ext is None else owner_ext
    return (
        here / "state" / "remote_sub" / f"{rid}.log",
        here / "lanes" / f"{rid}.remote.stdout",
    )




def _result_snapshot(rid: str, limit: int, original_log: bytes | None = None,
                     *, owner_ext: Path | None = None) -> bytes:
    """Read one coherent result observation under the current run's protocol."""
    from remote_sub_helpers import read_macro_result
    log_path, result_path = _paths(rid, owner_ext=owner_ext)
    log = _bounded_regular(log_path, MAX_LOG_BYTES) if original_log is None else original_log
    verified = read_macro_result(HERE if owner_ext is None else owner_ext, log_path, rid, limit, log)
    if verified is not None:
        return verified
    # Intact legacy logs keep their bounded result reads.  An orphan or a
    # partial log cannot establish which publication protocol owns the file.
    # Recheck after the result read so a newly appended policy cannot race a
    # legacy observation into exposing an unqualified canonical file.
    data = _bounded_regular(result_path, limit)
    if _bounded_regular(log_path, MAX_LOG_BYTES) != log:
        raise FabricTaskError("result log changed during read")
    return data


def _acceptance_unknown(reason: str) -> dict[str, Any]:
    return {"accepted": None, "accepted_by": None, "acceptance_state": "UNVERIFIED",
            "acceptance_reason": reason, "root_id": None, "parent_run_id": None}


def _active_lineage_projection(rid: str, original_log: bytes,
                               *, owner_ext: Path | None = None) -> dict[str, Any]:
    """Read existing artifact PRE_LAUNCH correlation, never worker/auth proof.

    The original controller validates the artifact packet and acquire response
    before publishing this record. This reader cannot recreate those checks or
    authenticate a caller; it only projects that owned, stable retained record.
    Plain packets and old runs without the record remain unverified.
    """
    unknown = {"controller_lineage": {"state": "UNVERIFIED"}}
    try:
        import artifact_delivery as delivery
        log_path, _ = _paths(rid, owner_ext=owner_ext)
        initial = log_path.lstat()
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
                    info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if initial.st_nlink != 1 or initial.st_mode & 0o022:
            return unknown
        # Reuse the incumbent private-chain/owner/regular-file reader. A poll
        # appended during either read makes this observation unavailable.
        if delivery.local_file(log_path, MAX_LOG_BYTES) != original_log:
            return unknown
        if not original_log.endswith(b"\n"):
            return unknown
        events = []
        hosts = set()
        prefix = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z "
                  r"\[remote_sub id=" + re.escape(rid) + r" host=([A-Za-z0-9_.-]+)\] (.*)")
        from remote_sub_helpers import macro_result_status_text
        for line in macro_result_status_text(original_log, rid).splitlines():
            match = re.fullmatch(prefix, line)
            if match is None:
                return unknown
            hosts.add(match[1])
            events.append(match[2])
        indices = [i for i, event in enumerate(events) if event.startswith("LAUNCH_BINDING ")]
        if len(indices) != 1 or len(hosts) != 1:
            return unknown
        if any(token in event for event in events
               for token in ("REFUSED", "FAILED", "EFFECT_UNKNOWN")):
            return unknown
        index = indices[0]
        def unique_pairs(pairs):
            data = {}
            for key, value in pairs:
                if key in data:
                    raise ValueError("duplicate binding key")
                data[key] = value
            return data
        binding = json.loads(events[index][len("LAUNCH_BINDING "):], object_pairs_hook=unique_pairs)
        keys = {"schema", "run_id", "root", "parent", "host", "mode", "requested_model",
                "pool", "lease_id", "account", "packet_sha256", "support_digest",
                "acquire_response_sha256", "source", "phase"}
        if type(binding) is dict and binding.get("schema") == "mastermind.fabric_launch_binding.v2":
            keys.add("acquisition_pool")
        if type(binding) is not dict or set(binding) != keys:
            return unknown
        if (binding["schema"] not in {"mastermind.fabric_launch_binding.v1", "mastermind.fabric_launch_binding.v2"}
                or binding["run_id"] != rid or binding["host"] not in hosts
                or binding["source"] != "controller_original_acquire_return"
                or binding["phase"] != "PRE_LAUNCH"
                or binding["mode"] not in ("glm", "qwen")
                or binding["pool"] != {"glm": "glm", "qwen": "bailian"}[binding["mode"]]):
            return unknown
        for field in ("run_id", "root", "parent", "host", "requested_model", "account"):
            if type(binding[field]) is not str or not RUN_ID_RE.fullmatch(binding[field]):
                return unknown
        for field in ("packet_sha256", "support_digest", "acquire_response_sha256"):
            if type(binding[field]) is not str or not re.fullmatch("[a-f0-9]{64}", binding[field]):
                return unknown
        if type(binding["lease_id"]) is not str or not re.fullmatch("[a-f0-9]{12}", binding["lease_id"]):
            return unknown
        if binding["schema"] == "mastermind.fabric_launch_binding.v2":
            from remote_sub_helpers import validate_acquisition_pool
            acquisition_pool = validate_acquisition_pool(
                binding["mode"], binding["requested_model"], binding["acquisition_pool"])
            acquired = (f'LEASE={binding["lease_id"]} ACCOUNT={binding["account"]}').encode("ascii")
            if binding["acquire_response_sha256"] not in {
                    delivery.digest(acquired), delivery.digest(acquired + b"\n")}:
                return unknown
        else:
            acquisition_pool = binding["pool"]
        before = events[:index]
        support = "SUPPORT_VERSION_READY digest=" + binding["support_digest"] + r" policy=[a-f0-9]{64}"
        if (sum(event == "RUN_RESERVED explicit=1" for event in before) != 1
                or [event for event in before if event.startswith("LEASE_OK ")] != ["LEASE_OK pool=" + acquisition_pool]
                or len([event for event in before if event.startswith("SUPPORT_VERSION_READY ")]) != 1
                or not any(re.fullmatch(support, event) for event in before)
                or any(event.startswith(("LAUNCH", "DONE", "REMOTE_DONE", "LEASE_PRESERVED")) for event in before)
                or any(token in event for event in before for token in ("REFUSED", "FAILED", "EFFECT_UNKNOWN"))):
            return unknown
        if not (before.index("RUN_RESERVED explicit=1")
                < before.index("LEASE_OK pool=" + acquisition_pool)
                < next(i for i, event in enumerate(before) if event.startswith("SUPPORT_VERSION_READY "))):
            return unknown
        if delivery.local_file(log_path, MAX_LOG_BYTES) != original_log:
            return unknown
        if identity(log_path.lstat()) != identity(initial):
            return unknown
        return {"controller_lineage": {
            "root_id": binding["root"], "parent_run_id": binding["parent"],
            "state": "RECORDED_PRE_LAUNCH",
            "source": "controller_original_acquire_return",
            "is_authentication": False}}
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, ImportError):
        return unknown


def _acceptance_projection(rid: str, status: dict[str, Any], original_log: bytes,
                           *, owner_ext: Path | None = None) -> dict[str, Any]:
    ledger = {} if owner_ext is None else {"ledger_path": str(owner_ext.parent / "orch/fabric/ledger.jsonl")}
    # Retain all legacy execution fields. This additive observation neither
    # accepts a result nor creates a native RuntimeBinding or retry right.
    if (status["state"] != "TERMINAL" or status["rc"] != 0
            or status["signal"] != "ok" or not status["result_available"]):
        projection = _acceptance_unknown("EXECUTION_NOT_ELIGIBLE")
        # Failure does not erase the original lineage. A terminal ledger read
        # supplies provenance only; acceptance and all effect states stay held.
        if (status["state"] == "TERMINAL" and type(status["rc"]) is int
                and status["rc"] != 0 and status["signal"] != "effect_unknown"):
            try:
                log_path, _ = _paths(rid, owner_ext=owner_ext)
                if _bounded_regular(log_path, MAX_LOG_BYTES) != original_log:
                    return projection
                identity = pool_ledger.read_execution_identity(
                    rid, expected_rc=status["rc"], expected_signal=status["signal"], **ledger)
                if _bounded_regular(log_path, MAX_LOG_BYTES) == original_log:
                    projection.update(identity)
            except (AttributeError, OSError, FabricTaskError):
                pass
        return projection
    log_path, result_path = _paths(rid, owner_ext=owner_ext)
    # Transport retains group-writable result modes (e.g. 0664). Preserve that
    # existing format; require local ownership, no world write, and stable reads.
    # Ledger acceptance does not attest result bytes or authenticate the parent.
    def artifact(path: Path, bound: int) -> tuple[bytes, tuple[int, ...]]:
        info = path.lstat()
        if info.st_uid != os.getuid() or info.st_mode & 0o002:
            raise FabricTaskError("unsafe acceptance artifact")
        data = _bounded_regular(path, bound)
        after = path.lstat()
        if (after.st_uid != os.getuid() or after.st_mode & 0o002
                or (info.st_dev, info.st_ino, info.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_ctime_ns)):
            raise FabricTaskError("acceptance artifact changed")
        return data, (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                      after.st_ctime_ns, after.st_mode, after.st_uid)
    try:
        log = artifact(log_path, MAX_LOG_BYTES)
        result = artifact(result_path, MAX_RESULT_BYTES)
        if not result[0] or len(result[0]) != status["result_bytes"]:
            return _acceptance_unknown("RESULT_NOT_VERIFIABLE")
        if log[0] != original_log:
            return _acceptance_unknown("ARTIFACT_CHANGED")
        projection = pool_ledger.read_acceptance(rid, expected_rc=status["rc"], expected_signal=status["signal"], **ledger)
        if (artifact(result_path, MAX_RESULT_BYTES) != result
                or artifact(log_path, MAX_LOG_BYTES) != log):
            return _acceptance_unknown("ARTIFACT_CHANGED")
        return projection
    except AttributeError:
        return _acceptance_unknown("LEDGER_PROJECTION_UNAVAILABLE")
    except (OSError, FabricTaskError):
        return _acceptance_unknown("ARTIFACT_UNVERIFIED")


def _glm_auth_prelaunch_failure(text: str, run_id: str, result_path: Path) -> bool:
    # remote_sub.sh's exact GLM guard sets RC=78 and exits before LAUNCH.
    # Recognize only its complete final line for this run/host; generic absent
    # rc fields, progress, remote output and lost launch replies prove nothing.
    if not text.endswith("\n") or any(marker in text for marker in (
        " LAUNCH", " NATIVE_SSH_ENTER ", " REMOTE_DONE ", " DONE rc=",
    )):
        return False
    match = _GLM_AUTH_GUARD_RE.fullmatch(text[:-1].rsplit("\n", 1)[-1])
    if match is None or match.group("run") != run_id:
        return False
    try:
        result_path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return False


def _controller_observation(text: str, rid: str) -> dict[str, Any] | None:
    """Expose old local evidence without inferring remote death or retry rights.

    Minute-resolution log timestamps give only a lower bound on silence. The
    threshold is the original controller's own recorded wait bound; it is not a
    worker deadline, a new lifecycle timer, or an instruction to relaunch.
    """
    pattern = re.compile(
        r"^(?P<stamp>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z) "
        r"\[remote_sub id=" + re.escape(rid) + r" host=[A-Za-z0-9_.-]+\] "
        r"POLL [1-9][0-9]*/(?P<bound>[1-9][0-9]{0,4}) "
        r"elapsed=(?P<elapsed>[0-9]{1,6}) file=[^\r\n]+$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    last = matches[-1]
    try:
        stamp = datetime.strptime(last['stamp'], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    bound = int(last['bound'])
    silence = max(0, int(time.time() - stamp.timestamp() - 60))
    return {
        "source": "local_retained_controller_log",
        "state": ("STALE_NO_TERMINAL_EVIDENCE" if silence > bound
                  else "LOCAL_POLL_EVIDENCE_ONLY"),
        "last_poll_at": last['stamp'],
        "last_poll_elapsed_seconds": int(last['elapsed']),
        "configured_controller_wait_seconds": bound,
        "silence_lower_bound_seconds": silence,
        "worker_state": "UNKNOWN",
        "retry_authorized": False,
    }


# These reviewed wrapper bytes classify normal SSH255 as controller uncertainty
# and rescan that earlier marker at exit. They identify affected source semantics,
# not a run, principal, lease, helper generation, or permission to consume output.
_POLL255_AFFECTED_WRAPPERS = frozenset({
    "e24d6123ae1c303fe7a72b88c9ae6093979dcf35a9984d7ba16ccb9689700b05",
    "a1e271170778f992cf07c780234620c22d17f6242581311c414e30dd428ade40",
})
_PROCESS_RECEIPT_KEYS = frozenset({
    "schema", "label", "pid", "pgid", "started_at", "ended_at", "returncode",
    "timed_out", "nice_requested", "nice_applied", "stdout_bytes", "stdout_sha256",
    "stderr_bytes", "stdout_truncated", "stderr_truncated", "runtime_failure_code", "cleanup",
})


def _normal_process_receipt(row: dict[str, Any], *, label: str, rc: int) -> tuple[datetime, datetime]:
    """Require the narrow normal-completion form of the existing process owner."""
    from lane_runtime import cleanup_receipt_is_proven
    if (set(row) != _PROCESS_RECEIPT_KEYS
            or row.get("schema") != "mastermind.local_owned_process_receipt.v1"
            or row.get("label") != label
            or type(row.get("returncode")) is not int or row["returncode"] != rc
            or any(type(row.get(k)) is not int or row[k] <= 0 for k in ("pid", "pgid"))
            or row["pid"] != row["pgid"]
            or any(type(row.get(k)) is not int or row[k] < 0 for k in ("stdout_bytes", "stderr_bytes"))
            or any(row.get(k) is not False for k in ("timed_out", "stdout_truncated", "stderr_truncated"))
            or row.get("runtime_failure_code") is not None
            or type(row.get("nice_applied")) is not bool
            or not (row.get("nice_requested") is None or type(row["nice_requested"]) is int)
            or type(row.get("stdout_sha256")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", row["stdout_sha256"]) is None):
        raise ValueError("poll_reconciliation_process_unqualified")
    cleanup = row.get("cleanup")
    if (not isinstance(cleanup, dict) or not cleanup_receipt_is_proven(cleanup)
            or type(cleanup.get("residual_count")) is not int
            or cleanup.get("status") != "not_needed"
            or cleanup.get("reason") != "normal_completion"
            or any(cleanup.get(k) is not False for k in ("sigterm_sent", "sigkill_sent"))
            or any(cleanup.get(k) is not True for k in (
                "stdout_capture_complete", "stderr_capture_complete", "stdin_delivery_complete"))
            or any(k not in cleanup or cleanup[k] is not None for k in (
                "error_code", "stdout_capture_error", "stderr_capture_error", "stdin_delivery_error"))):
        raise ValueError("poll_reconciliation_cleanup_unqualified")
    stamps = []
    for key in ("started_at", "ended_at"):
        value = row.get(key)
        if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value) is None:
            raise ValueError("poll_reconciliation_process_time")
        stamps.append(datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc))
    if stamps[0] > stamps[1]:
        raise ValueError("poll_reconciliation_process_order")
    return stamps[0], stamps[1]


def _poll255_request_chain(raw: dict[str, bytes], rid: str) -> tuple[dict, dict, dict]:
    import hashlib
    import quota_circuit
    sha = lambda value: hashlib.sha256(value).hexdigest()
    request, launch, returned = [pool_ledger._strict_json(raw[s].decode("utf-8"))
                                for s in (".request.json", ".request-launch.json", ".request-return.json")]
    # These three records come from provider_outcome.write_new. Require that
    # owner's complete JSON line, including its final newline, before composing
    # the retained byte digests; a partial or rewritten encoding is not a return.
    for suffix, value in zip((".request.json", ".request-launch.json", ".request-return.json"),
                             (request, launch, returned)):
        if raw[suffix] != (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode():
            raise ValueError("poll_reconciliation_record_encoding")
    fields = (
        (request, "mastermind.fabric_request_artifact.v1", {
            "schema", "run_id", "root_id", "parent_run_id", "task_class", "cwd", "packet",
            "packet_sha256", "packet_bytes", "created_at", "automatic_background_execution"}),
        (launch, "mastermind.fabric_request_launch.v1", {
            "schema", "run_id", "root_id", "parent_run_id", "packet_sha256", "state", "created_at",
            "request_sha256", "capacity_handoff", "route", "native_sources"}),
        (returned, "mastermind.fabric_request_return.v1", {
            "schema", "run_id", "root_id", "parent_run_id", "state", "controller_rc",
            "request_sha256", "launch_sha256", "prelease_sha256", "log_sha256"}),
    )
    for value, schema, keys in fields:
        if (set(value) != keys or value["schema"] != schema or value["run_id"] != rid
                or any(type(value[k]) is not str or not RUN_ID_RE.fullmatch(value[k])
                       or value[k] != request[k] for k in ("root_id", "parent_run_id"))):
            raise ValueError("poll_reconciliation_request_identity")
    if (request["automatic_background_execution"] is not False
            or type(request["task_class"]) is not str or not RUN_ID_RE.fullmatch(request["task_class"])
            or request["cwd"] != "~"
            or request["packet"] != rid + ".request.packet"
            or type(request["packet_bytes"]) is not int
            or not 0 < request["packet_bytes"] <= MAX_RESULT_BYTES
            or len(raw[".request.packet"]) != request["packet_bytes"]
            or request["packet_sha256"] != sha(raw[".request.packet"])
            or launch["packet_sha256"] != request["packet_sha256"]
            or launch["state"] != "LAUNCH_ATTEMPT_RESERVED"
            or launch["capacity_handoff"] is not True
            or returned["state"] != "NATIVE_CONTROLLER_RETURNED"
            or type(returned["controller_rc"]) is not int or returned["controller_rc"] != 0
            or returned["prelease_sha256"] is not None
            or any(value["request_sha256"] != sha(raw[".request.json"]) for value in (launch, returned))
            or returned["launch_sha256"] != sha(raw[".request-launch.json"])
            or returned["log_sha256"] != sha(raw[".log"])
            or any(type(value["created_at"]) not in (int, float) or value["created_at"] <= 0
                   for value in (request, launch))
            or request["created_at"] > launch["created_at"]):
        raise ValueError("poll_reconciliation_request_binding")
    sources, route = launch["native_sources"], launch["route"]
    if (not isinstance(sources, dict) or set(sources) != set(quota_circuit.PRELEASE_SOURCES)
            or any(type(v) is not str or re.fullmatch(r"[0-9a-f]{64}", v) is None for v in sources.values())
            or sources["remote_sub.sh"] not in _POLL255_AFFECTED_WRAPPERS
            or not isinstance(route, dict)
            or set(route) != {"ESCALATE_TO", "HOST", "KEY", "MODE", "MODEL", "POOL", "REASON"}
            or any(type(v) is not str or re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", v) is None
                   for v in route.values())
            or route["MODE"] != "minimax" or route["POOL"] != "minimax"
            or re.fullmatch(r"[A-Za-z0-9_.-]+", route["HOST"]) is None):
        raise ValueError("poll_reconciliation_source_or_route")
    return request, launch, returned


def _poll255_event_sequence(raw: bytes, rid: str, route: dict, rows: list[dict],
                            worker: dict, provider: dict) -> None:
    import hashlib
    from remote_sub_helpers import _macro_log_events, macro_result_status_text
    projected = macro_result_status_text(raw, rid).encode("utf-8")
    events, _ = _macro_log_events(projected, rid, route["HOST"])
    lines = projected.decode("utf-8").splitlines()
    def once(prefix: str, exact: str | None = None) -> int:
        found = [i for i, event in enumerate(events) if event.startswith(prefix)]
        if len(found) != 1 or (exact is not None and events[found[0]] != exact):
            raise ValueError("poll_reconciliation_event_count")
        return found[0]
    reserved = once("RUN_RESERVED", "RUN_RESERVED explicit=1")
    lease = once("LEASE_OK", "LEASE_OK pool=" + route["POOL"])
    launch = once("LAUNCH stdout=")
    attempt = once("LAUNCH_ATTEMPT", "LAUNCH_ATTEMPT attempt=1")
    remote_done = once("REMOTE_DONE", "REMOTE_DONE rc=0")
    process_saved = once("PROCESS_RECEIPT_SAVED", "PROCESS_RECEIPT_SAVED file=" + rid + ".process.jsonl")
    provider_saved = once("PROVIDER_OUTCOME_RECORDED", "PROVIDER_OUTCOME_RECORDED file=" + rid + ".provider.json")
    cleaned = once("REMOTE_CLEANED")
    if re.fullmatch(r"REMOTE_CLEANED transport=1 receipt_saved=1 usage_saved=[01]", events[cleaned]) is None:
        raise ValueError("poll_reconciliation_remote_cleanup")
    done = once("DONE", "DONE rc=0 signal=ok")
    held = once("LEASE_PRESERVED", "LEASE_PRESERVED effect_unknown=1 lease=" + provider["lease_id"])
    if (not reserved < lease < launch < attempt < remote_done < process_saved < provider_saved < cleaned < done < held
            or held != len(events) - 1
            or re.fullmatch(r"LAUNCH stdout=lanes_" + re.escape(rid)
                            + r"\.stdout rc_file=ext/lanes_" + re.escape(rid) + r"\.rc cwd=~", events[launch]) is None):
        raise ValueError("poll_reconciliation_terminal_order")
    bad_markers = []
    for i, event in enumerate(events):
        if event == "CONTROLLER_PROCESS_UNPROVEN stage=poll rc=255":
            bad_markers.append(i)
            continue
        if i == held or re.fullmatch(r"POLL_TRANSPORT_FAILED rc=255 poll=[1-9][0-9]*", event):
            continue
        if (any(token in event for token in ("UNPROVEN", "EFFECT_UNKNOWN", "signal=effect_unknown",
                                            "FAILED", "REFUSED", "LEASE_PRESERVED"))
                or event.startswith(("ADMISSION_", "RESULT_UNAVAILABLE", "POLL_PROTOCOL_INVALID"))):
            raise ValueError("poll_reconciliation_other_uncertainty")
    if not bad_markers:
        raise ValueError("poll_reconciliation_no_affected_poll")
    intervals = []
    for row in rows:
        label, rc = row.get("label"), row.get("returncode")
        if (type(label) is not str or re.fullmatch(r"commission-[a-z][a-z0-9_-]{0,63}", label) is None
                or type(rc) is not int or rc not in (0, 255)
                or rc == 255 and label != "commission-poll"):
            raise ValueError("poll_reconciliation_controller_failure")
        interval = _normal_process_receipt(row, label=label, rc=rc)
        if intervals and interval[0] < intervals[-1][1]:
            raise ValueError("poll_reconciliation_controller_order")
        intervals.append(interval)
    launches = [row for row in rows if row["label"] == "commission-launch"]
    polls = [row for row in rows if row["label"] == "commission-poll"]
    if len(launches) != 1 or launches[0]["returncode"] != 0 or not polls:
        raise ValueError("poll_reconciliation_execution_count")
    headers = [(i, re.fullmatch(r"POLL ([1-9][0-9]*)/([1-9][0-9]*) elapsed=([0-9]+) file=(.+)", event))
               for i, event in enumerate(events) if event.startswith("POLL ")]
    if len(headers) != len(polls) or any(match is None for _, match in headers):
        raise ValueError("poll_reconciliation_poll_count")
    matched_bad = []
    matched_outcomes = []
    bound, elapsed = None, -1
    for position, ((index, match), receipt) in enumerate(zip(headers, polls), start=1):
        assert match is not None
        end = headers[position][0] if position < len(headers) else remote_done
        if (not attempt < index < end <= remote_done or int(match[1]) != position
                or bound is not None and int(match[2]) != bound
                or int(match[3]) < elapsed
                or not match[4].endswith("/ext/lanes_" + rid + ".rc")):
            raise ValueError("poll_reconciliation_poll_order")
        bound, elapsed = int(match[2]), int(match[3])
        segment = events[index + 1:end]
        outcomes = [(j, event) for j, event in enumerate(segment, start=index + 1)
                    if event.startswith(("POLL_PENDING", "POLL_TRANSPORT_FAILED", "RC value="))]
        if len(outcomes) != 1:
            raise ValueError("poll_reconciliation_poll_result")
        outcome_index, outcome = outcomes[0]
        matched_outcomes.append(outcome_index)
        unproven = [j for j in bad_markers if index < j < end]
        if receipt["returncode"] == 255:
            if (outcome != f"POLL_TRANSPORT_FAILED rc=255 poll={position}"
                    or len(unproven) != 1 or not unproven[0] < outcome_index
                    or receipt["stdout_bytes"] != 0
                    or receipt["stdout_sha256"] != hashlib.sha256(b"").hexdigest()):
                raise ValueError("poll_reconciliation_failed_poll_binding")
            matched_bad.extend(unproven)
        else:
            expected = (f"RC value=0 poll={position}" if position == len(headers)
                        else f"POLL_PENDING poll={position}")
            output = b"0\n" if position == len(headers) else b"__REMOTE_SUB_PENDING__\n"
            if (unproven or outcome != expected or receipt["stdout_bytes"] != len(output)
                    or receipt["stdout_sha256"] != hashlib.sha256(output).hexdigest()):
                raise ValueError("poll_reconciliation_successful_poll_binding")
        start, finish = _normal_process_receipt(receipt, label="commission-poll", rc=receipt["returncode"])
        log_start = datetime.strptime(lines[index][:17], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        log_finish = datetime.strptime(lines[outcome_index][:17], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        if start < log_start or not log_finish.timestamp() <= finish.timestamp() < log_finish.timestamp() + 60:
            raise ValueError("poll_reconciliation_poll_time_binding")
    all_outcomes = [i for i, event in enumerate(events)
                    if event.startswith(("POLL_PENDING", "POLL_TRANSPORT_FAILED", "RC value="))]
    if (matched_bad != bad_markers or matched_outcomes != all_outcomes
            or polls[-1]["returncode"] != 0):
        raise ValueError("poll_reconciliation_unmatched_uncertainty")
    worker_start, worker_end = _normal_process_receipt(worker, label=rid, rc=0)
    launch_start, _ = _normal_process_receipt(launches[0], label="commission-launch", rc=0)
    final_start, _ = _normal_process_receipt(polls[-1], label="commission-poll", rc=0)
    if not launch_start <= worker_start <= worker_end <= final_start:
        raise ValueError("poll_reconciliation_worker_time_order")


def _qualify_completed_poll255(rid: str, original_log: bytes, *, owner_ext: Path | None = None) -> bool:
    """Read-only correction of one proven completed plain MiniMax execution.

    The incumbent private namespace, original request/return, process/provider
    receipts and unique terminal ledger must all agree. This reads no result or
    provider capture, grants no authority, writes nothing and never releases a
    held lease. Missing or different evidence retains the original uncertainty.
    """
    import artifact_delivery as delivery
    import provider_outcome
    from native_runtime_bindings import owner_path
    try:
        here = HERE if owner_ext is None else Path(owner_ext)
        directory = owner_path(here / "state" / "remote_sub", HERE)
        ledger = owner_path(here.parent / "orch" / "fabric" / "ledger.jsonl", HERE)
        limits = {".request.json": 32768, ".request-launch.json": 32768,
                  ".request-return.json": 32768, ".request.packet": MAX_RESULT_BYTES,
                  ".log": MAX_LOG_BYTES, ".controller-process.jsonl": 2 * 1024 * 1024,
                  ".process.jsonl": 32768, ".provider.json": 32768}
        with delivery.DirectoryChain(directory) as chain:
            def artifact(suffix: str) -> tuple[bytes, tuple[int, ...]]:
                name = rid + suffix
                before = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
                identity = lambda s: (s.st_dev, s.st_ino, s.st_uid, s.st_gid, s.st_mode,
                                      s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
                if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                        or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1):
                    raise ValueError("poll_reconciliation_receipt_custody")
                data = delivery.read_local_at(chain, name, limits[suffix])
                after = os.stat(name, dir_fd=chain.fd, follow_symlinks=False)
                if identity(before) != identity(after):
                    raise ValueError("poll_reconciliation_receipt_changed")
                return data, identity(after)
            retained = {suffix: artifact(suffix) for suffix in limits}
            raw = {suffix: value[0] for suffix, value in retained.items()}
            if raw[".log"] != original_log:
                raise ValueError("poll_reconciliation_log_changed")
            request, launch, _ = _poll255_request_chain(raw, rid)
            def jsonlines(suffix: str, maximum: int) -> list[dict]:
                data = raw[suffix]
                lines = data.splitlines()
                if (not data.endswith(b"\n") or not 0 < len(lines) <= maximum
                        or any(not line or len(line) > 8192 for line in lines)):
                    raise ValueError("poll_reconciliation_receipt_lines")
                return [pool_ledger._strict_json(line.decode("utf-8")) for line in lines]
            workers = jsonlines(".process.jsonl", 1)
            worker = workers[0]
            _normal_process_receipt(worker, label=rid, rc=0)
            provider = pool_ledger._strict_json(raw[".provider.json"].decode("utf-8"))
            provider_outcome.validate_receipt(provider, worker, rid)
            if (provider.get("root_id") != request["root_id"]
                    or any(provider.get(k) != launch["route"][source] for k, source in
                           (("host", "HOST"), ("model", "MODEL"), ("provider", "MODE")))
                    or provider.get("kind") != "success" or provider.get("cli_subtype") != "success"
                    or provider.get("cli_terminal_reason") != "completed"
                    or provider.get("complete_event_capture") is not True
                    or provider.get("initial_rejection") is not False
                    or any(type(provider.get(k)) is not int or provider[k] != 0
                           for k in ("command_rc", "cli_command_rc", "permission_denial_count"))
                    or provider.get("permission_denials_role") != "none"
                    or type(provider.get("lease_id")) is not str
                    or re.fullmatch(r"[0-9a-f]{12}", provider["lease_id"]) is None
                    or type(provider.get("account")) is not str
                    or re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", provider["account"]) is None
                    or worker["stdout_bytes"] <= 0):
                raise ValueError("poll_reconciliation_provider_binding")
            _poll255_event_sequence(original_log, rid, launch["route"],
                                    jsonlines(".controller-process.jsonl", 4096), worker, provider)
            identity = pool_ledger.read_execution_identity(
                rid, expected_rc=0, expected_signal="ok", ledger_path=str(ledger))
            expected = {"lineage_state": "VERIFIED_TERMINAL", "root_id": request["root_id"],
                        "parent_run_id": request["parent_run_id"]}
            if identity != expected:
                raise ValueError("poll_reconciliation_terminal_unqualified")
            if any(artifact(suffix) != retained[suffix] for suffix in limits):
                raise ValueError("poll_reconciliation_snapshot_changed")
            chain.verify()
            # Unrelated ledger appends are allowed; a conflicting original
            # terminal or outcome is still rejected by the incumbent reader.
            return pool_ledger.read_execution_identity(
                rid, expected_rc=0, expected_signal="ok", ledger_path=str(ledger)) == expected
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        return False


def inspect_run(run_id: str, *, owner_ext: Path | None = None) -> dict[str, Any]:
    # The original paid owner binds immutable code to its fixed existing data
    # namespace. This read-only parameter grants no caller authority, starts
    # no process, and never changes module globals shared by concurrent reads.
    here = HERE if owner_ext is None else Path(owner_ext)
    if not here.is_absolute() or ".." in here.parts:
        raise ValueError("invalid Fabric owner namespace")
    owner = {} if owner_ext is None else {"owner_ext": here}
    rid = validate_run_id(run_id)
    log_path, result_path = _paths(rid, **owner)
    missing_log = False
    metadata_error = None
    try:
        log_path.lstat()
    except FileNotFoundError:
        missing_log = True
    except OSError as exc:
        metadata_error = exc
    if missing_log:
        retained = here / "state" / "remote_sub" / f"{rid}.request.json"
        retained_present, artifact_unverified = True, False
        try:
            retained.lstat()
        except FileNotFoundError:
            retained_present = False
        except OSError:
            retained_present, artifact_unverified = False, True
        if retained_present:
            try:
                row = json.loads(_bounded_regular(retained, 32768))
                if row.get("schema") != "mastermind.fabric_request_artifact.v1" or row.get("run_id") != rid:
                    raise FabricTaskError("retained_request_invalid")
                state = "REQUEST_RETAINED_NO_START_EVIDENCE"
                refusal_diagnostic: dict[str, str] = {}
                refused = retained.with_name(rid + ".request-refused.json")
                launch = retained.with_name(rid + ".request-launch.json")
                if refused.exists() and not (launch.exists() or launch.is_symlink()):
                    import provider_outcome
                    proof = json.loads(_bounded_regular(refused, 32768))
                    if (proof.get("schema") != "mastermind.fabric_request_refusal.v1"
                            or proof.get("run_id") != rid or proof.get("root_id") != row.get("root_id")
                            or proof.get("parent_run_id") != row.get("parent_run_id")
                            or proof.get("request_sha256") != provider_outcome.digest(_bounded_regular(retained,32768))
                            or proof.get("launch_attempted") is not False):
                        raise FabricTaskError("retained_refusal_invalid")
                    state = "REQUEST_REFUSED_BEFORE_LAUNCH"
                    code = proof.get("refusal_code")
                    refusal_diagnostic["request_refusal_code"] = (
                        code if type(code) is str and code in _REQUEST_REFUSAL_CODES
                        else "UNCLASSIFIED_PRELAUNCH_REFUSAL")
                return {"schema": "mastermind.fabric_task_status.v1", "run_id": rid,
                    "state": state, "rc": None, "signal": None,
                    "result_available": False, "result_bytes": None,
                    **_acceptance_unknown("EXECUTION_NOT_ELIGIBLE"),
                    "request_root_id": row.get("root_id"), "request_parent_run_id": row.get("parent_run_id"),
                    "execution_absence_proven": state == "REQUEST_REFUSED_BEFORE_LAUNCH",
                    "background_execution": False, "request_retained": True,
                    "same_run_replay_allowed": False, **refusal_diagnostic}
            except (OSError, ValueError, FabricTaskError, AttributeError):
                return {"schema": "mastermind.fabric_task_status.v1", "run_id": rid,
                    "state": "STATUS_UNREADABLE", "rc": None, "signal": None,
                    "result_available": False, "result_bytes": None,
                    **_acceptance_unknown("ARTIFACT_UNVERIFIED")}
        # The packet is fsynced before its descriptor. A crash in that window
        # still occupies the original run, as does an orphan result. Check only
        # the fixed artifacts guarded by request(); their presence or unreadable
        # metadata proves neither execution absence nor root identity. Never read
        # their contents or turn a missing log into permission to redispatch.
        if not artifact_unverified:
            for artifact in (retained.with_name(f"{rid}.request.packet"), result_path):
                try:
                    artifact.lstat()
                except FileNotFoundError:
                    continue
                except OSError:
                    pass
                artifact_unverified = True
                break
        return {
            "schema": "mastermind.fabric_task_status.v1",
            "run_id": rid,
            "state": "STATUS_UNREADABLE" if artifact_unverified else "NOT_FOUND",
            **_acceptance_unknown("ARTIFACT_UNVERIFIED" if artifact_unverified else "EXECUTION_NOT_ELIGIBLE"),
            "rc": None,
            "signal": None,
            "result_available": False,
            "result_bytes": None,
        }
    try:
        if metadata_error is not None:
            raise metadata_error
        original_log = _bounded_regular(log_path, MAX_LOG_BYTES)
        from remote_sub_helpers import macro_result_status_text
        text = macro_result_status_text(original_log, rid)
    except (OSError, ValueError, TypeError, KeyError, FabricTaskError):
        return {
            "schema": "mastermind.fabric_task_status.v1",
            "run_id": rid,
            "state": "STATUS_UNREADABLE",
            **_acceptance_unknown("ARTIFACT_UNVERIFIED"),
            "rc": None,
            "signal": None,
            "result_available": False,
            "result_bytes": None,
        }

    prelease = here / "state" / "remote_sub" / f"{rid}.prelease-quota.json"
    if prelease.exists() or prelease.is_symlink():
        import quota_circuit
        # Preserve the incumbent sticky uncertainty rule before any new
        # capacity projection, even when a contradictory log is hash-bound.
        if any(marker in text for marker in quota_circuit.PRELEASE_UNCERTAINTY_MARKERS):
            return {"schema": "mastermind.fabric_task_status.v1", "run_id": rid,
                "state": "EFFECT_UNKNOWN", "rc": None, "signal": None,
                "result_available": False, "result_bytes": None,
                **_acceptance_unknown("EXECUTION_NOT_ELIGIBLE")}
        # The broker may have published its refusal while the exact native
        # controller is still returning. Only the adapter's retained subprocess
        # return completes this no-task-start observation.
        returned = prelease.with_name(rid + ".request-return.json")
        if not (returned.exists() or returned.is_symlink()):
            return {"schema": "mastermind.fabric_task_status.v1", "run_id": rid,
                "state": "SETTLING", "rc": None, "signal": None,
                "result_available": False, "result_bytes": None,
                **_acceptance_unknown("EXECUTION_NOT_ELIGIBLE")}
        try:
            request = json.loads(_bounded_regular(prelease.with_name(rid + ".request.json"), 32768))
            root, parent = request.get("root_id"), request.get("parent_run_id")
            quota_circuit.validate_prelease_refusal(here, rid, root, parent,
                                                   packet_limit=MAX_RESULT_BYTES)
            return {"schema": "mastermind.fabric_task_status.v1", "run_id": rid,
                **_acceptance_unknown("EXECUTION_NOT_ELIGIBLE"),
                "state": "TERMINAL_FAILURE", "rc": 75, "signal": "quota",
                "reason": "prelease_quota_cooldown", "root_id": root, "parent_run_id": parent,
                "result_available": False, "result_bytes": None,
                "execution_absence_proven": True, "request_retained": True,
                "same_run_replay_allowed": False}
        except (OSError, ValueError, TypeError, AttributeError, FabricTaskError):
            return {"schema": "mastermind.fabric_task_status.v1", "run_id": rid,
                "state": "STATUS_UNREADABLE", "rc": None, "signal": None,
                "result_available": False, "result_bytes": None,
                **_acceptance_unknown("ARTIFACT_UNVERIFIED")}

    rc = None
    signal = None
    state = "ACTIVE_OR_WAITING"
    # Effect uncertainty is sticky unless a future explicit reconciliation edge
    # is added by the incumbent owner. A DONE line with effect_unknown is not
    # successful completion.
    if (
        "LEASE_PRESERVED effect_unknown=1" in text
        or "REMOTE_EFFECT_UNKNOWN" in text
        or "signal=effect_unknown" in text
    ):
        state = "EFFECT_UNKNOWN"
    elif "RESULT_UNAVAILABLE" in text:
        state = "RESULT_UNAVAILABLE"
        rc = 76
        signal = "other"
    elif "LAUNCH stdout=" not in text:
        # remote_sub's pure economic gate precedes all lease/provider effects.
        # Its refusal line has no rc field; preserve a terminal status for it.
        if " ECONOMIC_POLICY_REFUSED " in text and " LEASE_WAIT " not in text:
            state, rc, signal = "TERMINAL_FAILURE", 78, "prelaunch_failure"
        if _glm_auth_prelaunch_failure(text, rid, result_path):
            state, rc, signal = "TERMINAL_FAILURE", 78, "prelaunch_failure"
        failures = list(_PRELAUNCH_RC_RE.finditer(text))
        if failures:
            rc = int(failures[-1].group(1))
            signal = "prelaunch_failure"
            state = "TERMINAL_FAILURE"
    if state == "ACTIVE_OR_WAITING":
        matches = list(_DONE_RE.finditer(text))
        if matches:
            last = matches[-1]
            rc = int(last.group(1))
            signal = last.group(2)
            state = "TERMINAL" if signal != "effect_unknown" else "EFFECT_UNKNOWN"
        elif _REMOTE_DONE_RE.search(text):
            state = "SETTLING"

    if state == "EFFECT_UNKNOWN" and _qualify_completed_poll255(rid, original_log, **owner):
        state, rc, signal = "TERMINAL", 0, "ok"

    if (state == "TERMINAL_FAILURE" and rc == 78 and signal == "prelaunch_failure"
            and rid == "news-9612-exact-3a663-release-review-20261021"):
        import native_plain_packet_reconcile as packet_reconcile
        try:
            verified = packet_reconcile.status_from_receipt()
            if verified is not None:
                return {**_acceptance_unknown("EXECUTION_NOT_ELIGIBLE"), **verified}
        except (OSError, ValueError, TypeError, KeyError):
            return {"schema": "mastermind.fabric_task_status.v1", "run_id": rid,
                "state": "STATUS_UNREADABLE", "rc": None, "signal": None,
                "result_available": False, "result_bytes": None,
                **_acceptance_unknown("ARTIFACT_UNVERIFIED")}

    if state == "EFFECT_UNKNOWN" and rid == prestart_reconcile.RUN_ID:
        verified = prestart_reconcile.status_from_receipt()
        if verified is not None:
            return verified

    if state == "EFFECT_UNKNOWN" and rid == preexec_reconcile.RUN_ID:
        verified = preexec_reconcile.status_from_receipt()
        if verified is not None:
            return verified

    if state == "EFFECT_UNKNOWN" and rid == native_review_reconcile.RUN:
        verified = native_review_reconcile.status_from_receipt()
        if verified is not None:
            return verified

    if state == "SETTLING" and rid == terminal_reconcile.RUN_ID:
        verified = terminal_reconcile.status_from_ledger()
        if verified is not None:
            return verified

    if state == "SETTLING" and rid in completion_reconcile.KNOWN_RUNS:
        verified = completion_reconcile.status_from_receipt(rid)
        if verified is not None:
            verified.update(_acceptance_projection(rid, verified, original_log, **owner))
            return verified

    result_available = False
    result_bytes = None
    try:
        snapshot = _result_snapshot(rid, MAX_RESULT_BYTES, original_log, **owner)
        result_available = True
        result_bytes = len(snapshot)
    except (OSError, ValueError, TypeError, KeyError, FabricTaskError):
        pass

    status = {
        "schema": "mastermind.fabric_task_status.v1",
        "run_id": rid,
        "state": state,
        "rc": rc,
        "signal": signal,
        "result_available": result_available,
        "result_bytes": result_bytes,
    }
    if state == "ACTIVE_OR_WAITING":
        observation = _controller_observation(text, rid)
        if observation is not None:
            status["controller_observation"] = observation
    status.update(_acceptance_projection(rid, status, original_log, **owner))
    if state == "ACTIVE_OR_WAITING":
        status.update(_active_lineage_projection(rid, original_log, **owner))
    for suffix in (".session-retained.json", ".session-created.json"):
        path = here / "state" / "remote_sub" / (rid + suffix)
        if suffix == ".session-created.json" and rc == 0:
            continue
        try:
            raw = _bounded_regular(path, 16384)
            row = json.loads(raw)
            if (row.get("run_id") != rid or row.get("root_id") != status.get("root_id")
                    or row.get("parent_id") != status.get("parent_run_id")
                    or row.get("schema") not in {"mastermind.local_session_retained.v1", "mastermind.local_session_created.v1"}):
                continue
            import hashlib
            status["session_home_reference"] = {
                "host": row.get("host"), "home_path": row.get("home_path"),
                "provider": row.get("provider"), "index_file": path.name,
                "index_sha256": hashlib.sha256(raw).hexdigest(),
                "current_home_existence": "UNPROBED", "resume_authorized": False,
                "reclaim_authorized": False,
            }
            break
        except (OSError, ValueError, AttributeError, FabricTaskError):
            continue
    return status


def read_result(run_id: str, *, max_bytes: int = DEFAULT_RESULT_BYTES) -> bytes:
    rid = validate_run_id(run_id)
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= MAX_RESULT_BYTES:
        raise ValueError("invalid result byte limit")
    try:
        return _result_snapshot(rid, max_bytes)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise FabricTaskError("RESULT_NOT_AVAILABLE") from exc


def _parse_route(line: str) -> dict[str, str]:
    if not isinstance(line, str) or not line.startswith("POOL="):
        raise FabricTaskError(line.strip() or "NO_ROUTE")
    fields: dict[str, str] = {}
    for token in shlex.split(line):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value
    required = ("POOL", "MODEL", "HOST", "MODE")
    if any(not fields.get(key) for key in required):
        raise FabricTaskError("ROUTE_INCOMPLETE")
    return fields


def _route_with_deadline(task_class, options, deadline_ns, env, state_dir, run_id):
    """Bound the incumbent picker, including its existing quota lookups.

    This process receives routing metadata only. It cannot launch the task and
    never receives the task packet. The existing local process owner captures
    its return and proves cleanup; no new router or retry plane is introduced.
    """
    from commission_deadline import CommissionDeadlineExpired, require_remaining
    from lane_runtime import run_owned_process
    program = ("import json,sys; sys.path.insert(0,sys.argv[1]); import pick; "
               "value=json.load(sys.stdin); task=value.pop('task_class'); "
               "print(pick.format_pick(task,**value))")
    result = run_owned_process(
        [sys.executable, "-c", program, str(Path(pick.__file__).resolve().parent)],
        input_text=json.dumps({"task_class": task_class, **options}),
        timeout=require_remaining(deadline_ns), env=env,
        label=run_id[:100] + ".routing", capture_limit_bytes=65536,
        timeout_returncode=75,
        receipt_path=state_dir / (run_id + ".routing-process.jsonl"))
    if not result.cleanup_proven:
        raise FabricTaskError("REQUEST_ROUTING_CLEANUP_UNPROVEN")
    if result.timed_out:
        raise CommissionDeadlineExpired("commission deadline expired during routing")
    require_remaining(deadline_ns)
    if (result.returncode != 0 or result.stdout_truncated or result.stderr_truncated):
        raise FabricTaskError("REQUEST_ROUTING_RETURN_UNQUALIFIED")
    return result.stdout.strip()


def validate_request_max_turns(value: object) -> int:
    """Validate a per-request ceiling; the existing shell profile owns limits."""
    if type(value) is not int or not 1 <= value <= 400:
        raise FabricTaskError("REQUEST_MAX_TURNS_INVALID")
    return value


def _manual_token(value: str | None) -> str | None:
    """A literal preference is not an admission or quota grant."""
    if value is None:
        return None
    if type(value) is not str:
        raise FabricTaskError("MANUAL_SELECTOR_INVALID")
    token = value.strip()
    if not token or token.casefold() == "auto":
        return None
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}", token) is None:
        raise FabricTaskError("MANUAL_SELECTOR_INVALID")
    return token


def _enforce_manual_route(route: dict[str, str], pool: str | None, model: str | None) -> None:
    """Match the reselected *actual* worker route before native launch effects."""
    named_pool = _manual_token(pool)
    if named_pool is None:
        raise FabricTaskError("MANUAL_POOL_REQUIRED")
    canonical = pick.canonical_pool(named_pool)
    canonical = pick.ROUTING_TOKEN_POOLS.get(canonical, canonical)
    if route.get("POOL") != canonical:
        raise FabricTaskError("MANUAL_POOL_ROUTE_MISMATCH")
    if route.get("MODE") not in pick._HOST_POOL_MODES.get(canonical, ()):
        raise FabricTaskError("MANUAL_POOL_MODE_MISMATCH")
    named_model = _manual_token(model)
    if named_model is not None and route.get("MODEL", "").casefold() != named_model.casefold():
        raise FabricTaskError("MANUAL_MODEL_ROUTE_MISMATCH")


def preview_route(
    run_id: str,
    task_class: str,
    *,
    pool: str | None = None,
    model: str | None = None,
    prefer: str | None = None,
    subject_pool: str | None = None,
    task_complexity: str = "",
    escalation_reason: str = "",
) -> dict[str, object]:
    """Read-only incumbent picker and economic preflight; no lease, packet or worker."""
    rid = validate_run_id(run_id)
    selected_pool = _manual_token(pool)
    selected_model = _manual_token(model)
    if selected_model is not None and selected_pool is None:
        raise FabricTaskError("MANUAL_MODEL_REQUIRES_POOL")
    route = _parse_route(pick.format_pick(
        task_class, host="auto", pool=selected_pool,
        prefer=_manual_token(prefer),
        **({"subject_pool": subject_pool} if subject_pool is not None else {}),
        task_complexity=task_complexity, escalation_reason=escalation_reason,
        requested_model=selected_model, route_key=rid,
    ))
    if selected_pool is not None:
        _enforce_manual_route(route, selected_pool, selected_model)
    policy = pick.launch_policy(
        route["MODE"], task_class, route["MODEL"],
        escalation_reason=escalation_reason, task_complexity=task_complexity,
    )
    if not policy.get("allowed"):
        raise FabricTaskError("ECONOMIC_POLICY_REFUSED: " + str(policy.get("reason")))
    return {
        "state": "PREVIEW_ONLY", "reserved": False, "run_id": rid,
        "pool": route["POOL"], "model": route["MODEL"],
        "host": route["HOST"], "mode": route["MODE"],
        "reason": route.get("REASON") or "",
        "selection_rechecked_at_request": True,
        "strict_pin_enforced_at_request": selected_pool is not None,
    }


def request(
    run_id: str,
    task_class: str,
    *,
    cwd: str,
    packet: Path | None,
    stdin_bytes: bytes | None,
    pool: str | None = None,
    prefer: str | None = None,
    subject_pool: str | None = None,
    root_id: str | None = None,
    parent_run_id: str | None = None,
    task_complexity: str | None = None,
    escalation_reason: str | None = None,
    requested_model: str | None = None,
    artifact_names: list[str] | None = None,
    native_return: bool = False,
    qualification_host: str | None = None,
    new_macro_worktree: str | None = None,
    cpu_scope_percent: int | None = None,
    max_turns: int | None = None,
    request_remaining_seconds: int | None = None,
    request_capacity_preflight: bool = False,
    request_deadline_ns: int | None = None,
    not_before: str | None = None,
    strict_manual_pin: bool = False,
) -> int:
    rid = validate_run_id(run_id)
    # Match preview: AUTO is never a literal provider/model pin. Validate
    # before retaining a packet or consulting any provider/runtime owner.
    pool = _manual_token(pool)
    requested_model = _manual_token(requested_model)
    prefer = _manual_token(prefer)
    if bool(packet) == bool(stdin_bytes is not None):
        raise ValueError("provide exactly one of packet or stdin")
    if max_turns is not None:
        max_turns = validate_request_max_turns(max_turns)
    env = os.environ.copy()
    # An inherited transport label cannot silently constrain or authorize a new request.
    env.pop("POOL_CALLER_NOT_BEFORE", None)
    if not_before is not None:
        from commission_deadline import validate_not_before
        not_before = validate_not_before(not_before)
        env["POOL_CALLER_NOT_BEFORE"] = not_before
    # A parent request ceiling must not leak into unrelated child commissions.
    env.pop("POOL_REQUEST_MAX_TURNS", None)
    if max_turns is not None:
        env["POOL_REQUEST_MAX_TURNS"] = str(max_turns)
    env.pop("POOL_CAPACITY_PREFLIGHT",None)
    env.pop("POOL_COMMISSION_DEADLINE_NS", None)
    env.pop("POOL_PRELEASE_HANDOFF", None)
    env.pop("POOL_REQUEST_SHA256", None)
    env.pop("POOL_REQUEST_LAUNCH_SHA256", None)
    if request_capacity_preflight is True:
        env["POOL_CAPACITY_PREFLIGHT"]="1"
    if request_remaining_seconds is not None:
        if type(request_remaining_seconds) is not int or not 1 <= request_remaining_seconds <= 14400:
            raise FabricTaskError("REQUEST_REMAINING_TIME_INVALID")
        env["POOL_COMMISSION_REMAINING_SECONDS"] = str(request_remaining_seconds)
    if request_deadline_ns is not None:
        from commission_deadline import (DEADLINE_ENV, CommissionDeadlineExpired,
                                         require_remaining, validate_deadline_ns)
        request_deadline_ns = validate_deadline_ns(request_deadline_ns)
        if request_deadline_ns > time.monotonic_ns() + 14400 * 1_000_000_000:
            raise FabricTaskError("REQUEST_DEADLINE_INVALID")
        env[DEADLINE_ENV] = str(request_deadline_ns)
    def check_deadline():
        if not_before is not None:
            from commission_deadline import require_not_before
            require_not_before(not_before)
        if request_deadline_ns is not None:
            remaining = int(require_remaining(request_deadline_ns, minimum_seconds=1))
            if request_remaining_seconds is not None:
                remaining = min(remaining, request_remaining_seconds)
            env["POOL_COMMISSION_REMAINING_SECONDS"] = str(remaining)
    observed_root = resolve_request_root(root_id, env)
    # Freeze the input before route selection. Exhausted capacity or an ended
    # caller must not destroy the only copy of an unfinished commission. These
    # are per-run artifacts, not queued work or permission to resume a process.
    import hashlib
    import provider_outcome
    state_dir = HERE / "state" / "remote_sub"
    state_dir.mkdir(parents=True, exist_ok=True)
    request_file = state_dir / f"{rid}.request.json"
    retained_packet = state_dir / f"{rid}.request.packet"
    if any(p.exists() or p.is_symlink() for p in (*_paths(rid), request_file, retained_packet)):
        raise FabricTaskError("REQUEST_RUN_ALREADY_EXISTS_RECONCILE_ORIGINAL")
    source = _bounded_regular(packet, MAX_RESULT_BYTES) if packet is not None else stdin_bytes or b""
    if len(source) > MAX_RESULT_BYTES:
        raise FabricTaskError("REQUEST_PACKET_TOO_LARGE")
    descriptor = os.open(retained_packet, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(source)
        output.flush()
        os.fsync(output.fileno())
    provider_outcome.write_new(request_file, {
        "schema": "mastermind.fabric_request_artifact.v1", "run_id": rid,
        "root_id": observed_root, "parent_run_id": parent_run_id,
        "task_class": task_class, "cwd": cwd, "packet": retained_packet.name,
        "packet_sha256": hashlib.sha256(source).hexdigest(),
        "packet_bytes": len(source), "created_at": time.time(),
        "automatic_background_execution": False,
        **({"not_before": not_before} if not_before is not None else {}),
        **({"max_turns": max_turns} if max_turns is not None else {}),
    })
    packet, stdin_bytes = retained_packet, None
    selection_key, selection_facts, selection_line = object(), None, None
    try:
        check_deadline()
        # An explicit NEW worktree request is not permission to adopt an existing
        # session, mutate an incumbent checkout, or mint before a host lease.
        if new_macro_worktree is not None:
            if (re.fullmatch(r"[0-9a-f]{40}", new_macro_worktree) is None
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", rid) is None
                    or cwd != "~/lanes/repos/macro"
                    or not observed_root or not parent_run_id
                    or qualification_host or artifact_names or native_return):
                raise FabricTaskError("FABRIC_NEW_MACRO_WORKTREE_SCOPE_REFUSED")
        if cpu_scope_percent is not None:
            if (type(cpu_scope_percent) is not int
                    or cpu_scope_percent not in (100, 200, 400)
                    or not observed_root or not parent_run_id
                    or artifact_names or native_return or qualification_host):
                raise FabricTaskError("CPU_SCOPE_REQUEST_UNQUALIFIED")
        # Explicit empty arguments clear inherited values; None uses the existing
        # economic metadata. Selection and launch see the same exact witness.
        complexity = task_complexity if task_complexity is not None else env.get("POOL_TASK_COMPLEXITY", "")
        reason = escalation_reason if escalation_reason is not None else env.get("POOL_ESCALATION_REASON", "")
        if artifact_names:
            import artifact_production
        if qualification_host:
            if pool not in ("grok", "minimax") or artifact_names or native_return or requested_model or prefer:
                raise FabricTaskError("QUALIFICATION_OPTIONS_REFUSED")
            import fabric_host_qualification
            route = _parse_route(fabric_host_qualification.qualification_route(
                qualification_host, pool=pool, task_class=task_class, complexity=complexity,
                reason=reason, subject_pool=subject_pool,
                root=observed_root, parent=parent_run_id,
            ))
        else:
            route_options = dict(prefer=prefer, host="auto", pool=pool,
                **({"excluded_hosts": ["m2"]} if request_deadline_ns is not None else {}),
                **({"subject_pool": subject_pool} if subject_pool is not None else {}),
                task_complexity=complexity, escalation_reason=reason,
                requested_model=requested_model, route_key=rid,
                **({"required_modes": sorted(artifact_production.MODES),
                    "required_platforms": ["linux"]} if artifact_names else
                   {"required_modes": sorted({"glm", "glm-codex", "minimax", "qwen"}),
                    "required_platforms": ["linux"]} if (new_macro_worktree is not None or cpu_scope_percent is not None) else {}),
            )
            if max_turns is not None:
                # Only these admitted remote wrappers enforce the existing Claude
                # turn fuse. Never silently ignore the requested ceiling elsewhere.
                route_options["required_modes"] = sorted(
                    set(route_options.get("required_modes", ("glm", "minimax")))
                    & {"glm", "minimax"})
            if request_deadline_ns is not None:
                selection_line = _route_with_deadline(
                    task_class, route_options, request_deadline_ns, env, state_dir, rid)
            else:
                selection_request_sha = None
                try:
                    selection_request_sha = provider_outcome.digest(
                        provider_outcome.regular_bytes(request_file, 32768))
                except Exception:
                    pass  # Optional diagnostics cannot prevent the original pick.
                selection_line, selection_facts = pick.observed_format_pick(
                    task_class, observation_key=selection_key,
                    request_sha256=selection_request_sha, **route_options)
            route = _parse_route(selection_line)
        if strict_manual_pin:
            _enforce_manual_route(route, pool, requested_model)
        check_deadline()
        if max_turns is not None and route["MODE"] not in {"glm", "minimax"}:
            raise FabricTaskError("REQUEST_MAX_TURNS_ROUTE_UNSUPPORTED")
        guard = pick.launch_policy(
            route["MODE"], task_class, route["MODEL"],
            escalation_reason=reason, task_complexity=complexity,
        )
        if not guard.get("allowed"):
            raise FabricTaskError("ECONOMIC_POLICY_REFUSED: " + str(guard.get("reason")))
        if new_macro_worktree is not None:
            if route["HOST"] not in {"ubuntu0", "ubuntu1", "ubuntu2", "ubuntu3", "ubuntu4"}:
                raise FabricTaskError("FABRIC_SPARSE_HOST_REFUSED")
            if route["MODE"] not in {"glm", "glm-codex", "minimax", "qwen"}:
                raise FabricTaskError("FABRIC_SPARSE_MODE_NOT_YET_QUALIFIED")
        if cpu_scope_percent is not None:
            if route["HOST"] not in {"ubuntu2", "ubuntu3"}:
                raise FabricTaskError("CPU_SCOPE_HOST_NOT_QUALIFIED")
            if route["MODE"] not in {"glm", "glm-codex", "minimax", "qwen"}:
                raise FabricTaskError("CPU_SCOPE_MODE_NOT_QUALIFIED")
        env["POOL_TASK_CLASS"] = task_class
        if task_complexity is not None or "POOL_TASK_COMPLEXITY" in env:
            env["POOL_TASK_COMPLEXITY"] = complexity
        if escalation_reason is not None or "POOL_ESCALATION_REASON" in env:
            env["POOL_ESCALATION_REASON"] = reason
        if observed_root:
            env["POOL_ORCHESTRATOR_ID"] = observed_root
        if parent_run_id:
            env["POOL_PARENT_RUN_ID"] = validate_run_id(parent_run_id)

        if native_return:
            # Transport binding is not an authentication/custody grant. Explicit new
            # requests only: never adopt a retained or uncertain operation.
            if (not observed_root or env.get("CODEX_THREAD_ID") != observed_root
                    or env.get("POOL_PARENT_RUN_ID") != observed_root):
                raise FabricTaskError("NATIVE_RETURN_REQUIRES_CURRENT_ORIGINAL_PARENT")
            log_path, result_path = _paths(rid)
            if any(path.exists() or path.is_symlink() for path in (log_path, result_path)):
                raise FabricTaskError("NATIVE_RETURN_EXISTING_RUN_NOT_ADOPTED")

        # Explicit opt-in only. The existing router/lease/controller still own execution.
        if artifact_names:
            import artifact_production
            if route["MODE"] not in artifact_production.MODES:
                raise FabricTaskError("ARTIFACT_CONTRACT_MODE_UNAVAILABLE")
            if route["HOST"] == "m2":
                raise FabricTaskError("ARTIFACT_CONTRACT_LOCAL_UNAVAILABLE")
            if not observed_root or not env.get("POOL_PARENT_RUN_ID"):
                raise FabricTaskError("ARTIFACT_CONTRACT_REQUIRES_ORIGINAL_ROOT_AND_PARENT")
            source = packet.read_bytes() if packet is not None else stdin_bytes
            stdin_bytes = artifact_production.encode_packet(
                source.decode("utf-8"), root=env["POOL_ORCHESTRATOR_ID"],
                parent=env["POOL_PARENT_RUN_ID"], run_id=rid, names=artifact_names,
                support_digest=artifact_production.source_digest(HERE)).encode()
            packet = None

        if native_return:
            import fabric_stop_return
            # This private metadata records one attention subscription, not a job,
            # lease, result, retry permission or native RuntimeBinding.
            fabric_stop_return.register_subscription(observed_root, rid, HERE / "state" / "native_return")

        temp_path: Path | None = None
        try:
            if packet is None:
                state_dir = HERE / "state" / "remote_sub"
                state_dir.mkdir(parents=True, exist_ok=True)
                fd, raw = tempfile.mkstemp(prefix=f"{rid}.packet.", dir=state_dir)
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(stdin_bytes or b"")
                    handle.flush()
                    os.fsync(handle.fileno())
                temp_path = Path(raw)
                packet_path = temp_path
            else:
                packet_path = packet
            argv = [
                "/bin/bash",
                str(HERE / "remote_sub.sh"),
                route["HOST"],
                route["MODE"],
                str(packet_path),
                cwd,
                route["MODEL"],
                "--run-id",
                rid,
            ]
            if not_before is not None:
                argv.extend(["--not-before", not_before])
            if new_macro_worktree is not None:
                argv.extend(["--new-macro-worktree", new_macro_worktree])
            if cpu_scope_percent is not None:
                argv.extend(["--cpu-scope-quota", str(cpu_scope_percent)])
            check_deadline()
            request_sha = provider_outcome.digest(provider_outcome.regular_bytes(request_file, 32768))
            launch_row = {
                "schema": "mastermind.fabric_request_launch.v1", "run_id": rid,
                "root_id": observed_root, "parent_run_id": parent_run_id,
                "packet_sha256": hashlib.sha256(source).hexdigest(),
                "state": "LAUNCH_ATTEMPT_RESERVED", "created_at": time.time(),
                "request_sha256": request_sha,
                **({"not_before": not_before} if not_before is not None else {}),
            }
            if request_capacity_preflight is True:
                import quota_circuit
                code = Path(__file__).resolve().parent
                launch_row.update(capacity_handoff=True, route=route,
                    native_sources={name: provider_outcome.digest(provider_outcome.regular_bytes(
                        code / name, 256 * 1024)) for name in quota_circuit.PRELEASE_SOURCES})
                env["POOL_PRELEASE_HANDOFF"] = "1"
                env["POOL_REQUEST_SHA256"] = request_sha
            launch_file = state_dir / f"{rid}.request-launch.json"
            provider_outcome.write_new(launch_file, launch_row)
            if request_capacity_preflight is True:
                env["POOL_REQUEST_LAUNCH_SHA256"] = provider_outcome.digest(
                    provider_outcome.regular_bytes(launch_file, 32768))
            check_deadline()
            proc = subprocess.run(argv, env=env)
            if request_capacity_preflight is True:
                refusal = state_dir / f"{rid}.prelease-quota.json"
                log = state_dir / f"{rid}.log"
                provider_outcome.write_new(state_dir / f"{rid}.request-return.json", {
                    "schema": "mastermind.fabric_request_return.v1", "run_id": rid,
                    "root_id": observed_root, "parent_run_id": parent_run_id,
                    "state": "NATIVE_CONTROLLER_RETURNED", "controller_rc": int(proc.returncode),
                    "request_sha256": request_sha,
                    "launch_sha256": env["POOL_REQUEST_LAUNCH_SHA256"],
                    "prelease_sha256": provider_outcome.digest(provider_outcome.regular_bytes(refusal, 32768))
                        if refusal.exists() or refusal.is_symlink() else None,
                    "log_sha256": provider_outcome.digest(provider_outcome.regular_bytes(log, MAX_LOG_BYTES))
                        if log.exists() or log.is_symlink() else None,
                })
            return int(proc.returncode)
        finally:
            if temp_path is not None:
                # Original input is indexed by request.json. Artifact compilation
                # is deterministic and is not a separately resumable commission.
                temp_path.unlink(missing_ok=True)
    except BaseException as exc:
        # Only this invocation owns its just-created request. A launch intent,
        # even without a log, withholds no-start evidence after any crash.
        launch = state_dir / f"{rid}.request-launch.json"
        if not any(p.exists() or p.is_symlink() for p in (*_paths(rid), launch)):
            try:
                refused_request_sha = provider_outcome.digest(
                    provider_outcome.regular_bytes(request_file, 32768))
                try:
                    selection_diagnostics = pick.consume_selection_refusal(
                        selection_facts, selection_key, refused_request_sha, selection_line)
                except Exception:
                    selection_diagnostics = None
                provider_outcome.write_new(state_dir / f"{rid}.request-refused.json", {
                    "schema": "mastermind.fabric_request_refusal.v1", "run_id": rid,
                    "root_id": observed_root, "parent_run_id": parent_run_id,
                    "request_sha256": refused_request_sha,
                    **({"selection_diagnostics": selection_diagnostics}
                       if selection_diagnostics is not None else {}),
                    "reason": "prelaunch_" + type(exc).__name__,
                    "refusal_code": _safe_request_refusal_code(exc),
                    **({"eligible_at": exc.eligible_at} if hasattr(exc, "eligible_at") else {}),
                    "launch_attempted": False, "created_at": time.time(),
                })
            except (OSError, ValueError):
                pass  # Preserve the original refusal; never invent a receipt.
        raise


def _current_source_owner_factory(registry):
    """Native CLI owner boundary for bounded CURRENT source observation.

    Built from the host registry this incumbent process read itself.  Admission
    re-checks the exact validated request digest handed to it, the invoking OS
    principal, the original observer correlation and the registry host with its
    declared custody; the ssh_alias for the incumbent strict-SSH transport
    comes only from that same registry entry.  No grant is installed by this
    source: the new route is unavailable until its qualified generation is
    installed/selected. Current OS/tool permission and the external scoped
    commission authorize the invocation; labels and host provider modes do not
    grant read authority. No provider-mode or grant-registry addition is made.
    """
    import current_source_observation as observation
    from host_pick import MODE_TOOLS

    class CurrentSourceOwner(observation.NativeInvocationOwner):
        def __init__(self, request_sha256: str):
            self.request_sha256 = request_sha256
            self.active = set()
            self.revoked = False

        def _entry(self, view):
            entry = registry.get(view.host) if isinstance(registry, dict) else None
            if (type(entry) is not dict
                    or type(entry.get("roles")) is not list or "lanes" not in entry["roles"]
                    or not isinstance(entry.get("ssh_alias"), str)
                    or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}",
                                    entry["ssh_alias"]) is None):
                return None
            modes = entry.get("allowed_modes")
            if modes is not None and (type(modes) is not list
                    or any(type(mode) is not str or mode not in MODE_TOOLS for mode in modes)
                    or len(modes) != len(set(modes))):
                return None
            return entry

        def admit_invocation(self, view, invoking_uid):
            if (type(view) is not observation.NativeInvocationView
                    or view.request_sha256 != self.request_sha256 or self.revoked
                    or type(invoking_uid) is not int or invoking_uid != os.getuid()
                    or os.environ.get('CODEX_THREAD_ID') != view.observer
                    or view.observer == view.receiver
                    or not isinstance(view.worktree, str)
                    or not view.worktree.startswith("/")):
                return False
            if view.custody is not None:
                # Resolution variant: the whole custody dict is the scoped
                # resource selector this owner consumes.  Exactly the closed
                # union validation applies -- the boundary must be absolute,
                # non-root and strictly contain the declared worktree; it is a
                # selector, never an authority or label-as-proof.
                try:
                    observation.require_boundary_contains(
                        observation.validate_custody_variant(view.custody),
                        observation.validate_absolute_custody(view.worktree))
                except observation.CurrentSourceError:
                    return False
                return self._entry(view) is not None
            if (not isinstance(view.git_dir, str)
                    or not view.git_dir.startswith("/")
                    or not isinstance(view.common_dir, str)
                    or not view.common_dir.startswith("/")):
                return False
            return self._entry(view) is not None

        def registered(self, invocation):
            self.active.add(invocation.scope_digest)

        def invocation_active(self, invocation):
            return not self.revoked and invocation.scope_digest in self.active

        def authorize_publication(self, invocation):
            return self.invocation_active(invocation)

        def transport_alias(self, view):
            if view.request_sha256 != self.request_sha256 or self.revoked:
                return None
            entry = self._entry(view)
            return None if entry is None else entry["ssh_alias"]

    return CurrentSourceOwner


def current_source_flow(request_path: Path, destination: str, owner_factory, *,
                        reserve=None, transport=None, load_request=None) -> dict:
    """One bounded CURRENT observation: qualified native invocation -> the
    incumbent strict-SSH bounded transport -> the fixed generated Git reader
    -> validated receiver-bound exclusive receipt.  The invocation scope is
    minted inside this incumbent CLI process through ``owner_factory``;
    ``transport``/``reserve``/``load_request`` default to the incumbent
    transport, the incumbent exclusive destination reservation and the
    incumbent owned request reader."""
    import current_source_observation as observation
    return observation.native_current_source_receipt(
        request_path, destination, owner_factory, transport=transport,
        reserve=reserve, load_request=load_request)


def plan_accepted_macro_worktree_release(
    run_id: str, *, root_id: str, parent_run_id: str, pinned_sha: str,
) -> dict[str, Any]:
    """Read-only bridge from original accepted Fabric result to exact host GC.

    The original accepted ledger owns the terminal/result outcome; the
    original remote_sub log binds THIS run to an explicitly new sparse
    workspace. Neither fact alone permits Git removal, and this function
    NEVER launches a remote command or changes checkout state.
    """
    rid = validate_run_id(run_id)
    root = validate_run_id(root_id)
    parent = validate_run_id(parent_run_id)
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", rid)
            or not re.fullmatch(r"[0-9a-f]{40}", pinned_sha)):
        raise FabricTaskError("FABRIC_RECLAIM_INVALID_EXACT_SCOPE")
    current = inspect_run(rid)
    if (current.get("state") != "TERMINAL"
            or current.get("rc") != 0
            or current.get("signal") != "ok"
            or current.get("result_available") is not True
            or current.get("accepted") is not True
            or current.get("accepted_by") not in ("deterministic", "reviewer")
            or current.get("acceptance_state") != "ACCEPTED"
            or current.get("root_id") != root
            or current.get("parent_run_id") != parent):
        raise FabricTaskError("FABRIC_RECLAIM_ACCEPTANCE_OR_CUSTODY_UNVERIFIED")
    log_path, _ = _paths(rid)
    try:
        original = _bounded_regular(log_path, MAX_LOG_BYTES)
        original.decode("utf-8", errors="strict")
        from remote_sub_helpers import macro_result_status_text
        text = macro_result_status_text(original, rid)
    except (OSError, ValueError, TypeError, KeyError, FabricTaskError) as exc:
        raise FabricTaskError("FABRIC_RECLAIM_ORIGINAL_LOG_UNVERIFIED") from exc
    pattern = re.compile(
        r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}Z "
        r"\[remote_sub id=" + re.escape(rid) +
        r" host=(?P<host>ubuntu[0-4])\] "
        r"FABRIC_NEW_MACRO_WORKTREE run=" + re.escape(rid) +
        r" commit=(?P<sha>[0-9a-f]{40}) "
        r"root=(?P<root>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}) "
        r"parent=(?P<parent>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127})$",
        re.MULTILINE,
    )
    markers = [line for line in text.splitlines()
               if "FABRIC_NEW_MACRO_WORKTREE" in line]
    matched = list(pattern.finditer(text))
    if (len(markers) != 1 or len(matched) != 1
            or matched[0].group("sha") != pinned_sha
            or matched[0].group("root") != root
            or matched[0].group("parent") != parent):
        raise FabricTaskError("FABRIC_RECLAIM_ORIGINAL_LAUNCH_PROOF_UNVERIFIED")
    # A second bounded owner observation must agree with the initial
    # acceptance, not merely with the caller's run-id spelling.
    second = inspect_run(rid)
    keys = ("state", "rc", "signal", "result_available", "accepted",
            "accepted_by", "acceptance_state", "root_id", "parent_run_id")
    if any(second.get(key) != current.get(key) for key in keys):
        raise FabricTaskError("FABRIC_RECLAIM_ACCEPTANCE_CHANGED")
    if _bounded_regular(log_path, MAX_LOG_BYTES) != original:
        raise FabricTaskError("FABRIC_RECLAIM_LAUNCH_LOG_CHANGED")
    return {
        "schema": "mastermind.fabric_accepted_sparse_worktree_plan.v1",
        "state": "HOST_WORKTREE_SOURCE_AND_LIVENESS_PROOF_REQUIRED",
        "run_id": rid, "original_root": root, "parent_run_id": parent,
        "host": matched[0].group("host"),
        "checkout_path": "~/lanes/wt/" + rid,
        "expected_branch": "lane/" + rid,
        "source_pinned_sha": pinned_sha,
        "execution_accepted_by": current["accepted_by"],
        "cleanup_authorized": False,
    }


def wait_for(run_id: str, *, timeout: float, interval: float) -> dict[str, Any]:
    rid = validate_run_id(run_id)
    if not (0 <= timeout <= 7200 and 0.05 <= interval <= 60):
        raise ValueError("invalid wait bounds")
    deadline = time.monotonic() + timeout
    while True:
        status = inspect_run(rid)
        if status["state"] in {
            "NOT_FOUND", "TERMINAL", "TERMINAL_FAILURE", "RESULT_UNAVAILABLE", "EFFECT_UNKNOWN", "STATUS_UNREADABLE", "RECONCILED_PRESTART_FAILURE", "RECONCILED_PREEXEC_FAILURE", "REQUEST_RETAINED_NO_START_EVIDENCE", "REQUEST_REFUSED_BEFORE_LAUNCH"
        }:
            return status
        # A wait on unchanged local files cannot reconnect a lost collector.
        # Return the observation for owner diagnosis, preserving execution state.
        if status.get("controller_observation", {}).get("state") == "STALE_NO_TERMINAL_EVIDENCE":
            return status
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return status
        time.sleep(min(interval, remaining))


def _json(value: object) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _discard_failed_stdout() -> None:
    """Prevent a failed acknowledgment from flushing again to its old channel."""
    target_fd = null_fd = None
    try:
        target_fd = sys.stdout.fileno()
        null_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null_fd, target_fd)
    except (AttributeError, OSError, TypeError, ValueError):
        # Embedded/test streams may have no descriptor. Never assume fd 1 or
        # sys.__stdout__ belongs to that stream, and do not close the caller's
        # retained object merely to disarm this CLI response.
        sys.stdout = None
    finally:
        if null_fd is not None and null_fd != target_fd:
            try:
                os.close(null_fd)
            except OSError:
                pass


def _plain_packet_reconciliation_response(value: object, effect_state: str) -> bool:
    """Deliver either response without losing the operation's effect state."""
    try:
        _json(value)
        sys.stdout.flush()
    except (OSError, ValueError, TypeError) as exc:
        _discard_failed_stdout()
        print("PLAIN_PACKET_RECONCILIATION_RETURN_UNDELIVERED: "
              + effect_state + ": " + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr, flush=True)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_packet_check = sub.add_parser("check-plain-packet-retention", help="Read-only fixed original News retention proof; no reconciliation or retry")
    p_packet_check.add_argument("run_id")
    p_packet_check.add_argument("--root", required=True)

    p_packet_reconcile = sub.add_parser("reconcile-plain-packet-retention",
        help="Record the exact original historical failure disposition; never replay or accept")
    p_packet_reconcile.add_argument("run_id")
    p_packet_reconcile.add_argument("--root", required=True)
    p_packet_reconcile.add_argument("--expected-proof-sha256", required=True)


    p_preview = sub.add_parser("preview", help="read-only incumbent model and provider selection")
    p_preview.add_argument("--id", required=True)
    p_preview.add_argument("--class", dest="task_class", required=True)
    p_preview.add_argument("--pool", default="auto")
    p_preview.add_argument("--model", dest="requested_model", default="auto")
    p_preview.add_argument("--prefer")
    p_preview.add_argument("--subject-pool")
    p_preview.add_argument("--task-complexity", default="")
    p_preview.add_argument("--escalation-reason", default="")

    p_request = sub.add_parser("request")
    p_request.add_argument("--id", required=True)
    p_request.add_argument("--class", dest="task_class", required=True)
    p_request.add_argument("--native-return", action="store_true", help="Subscribe this new paid child to the separately reviewed/trusted native Stop hook")
    p_request.add_argument("--artifact-output", action="append", help="Required new file basename; opts into verified artifact production")
    # Resolve an implicit working directory on the receiving host.
    # The receiving host still validates explicit --cwd values.
    p_request.add_argument("--cwd", default="~")
    p_request.add_argument("--new-macro-worktree", metavar="COMMIT_SHA40",
                           help="Explicit new Macro sparse workspace at original run ID; never resume/reuse")
    p_request.add_argument("--cpu-scope-percent", type=int, choices=(100, 200, 400),
                           help="Explicit per-new-worker user cgroup CPU budget on qualified 9950X hosts")
    packet_group = p_request.add_mutually_exclusive_group(required=True)
    packet_group.add_argument("--packet")
    packet_group.add_argument("--stdin", action="store_true")
    p_request.add_argument("--pool")
    p_request.add_argument("--strict-manual-pin", action="store_true", help="fail closed if provider or model changes after preview")
    p_request.add_argument("--qualification-host", choices=("mb", "m1", "ubuntu4"), help="Explicit pending-host first worker (Grok on Mac or Ubuntu4, MiniMax on M1 or Ubuntu4); no provider enrollment")
    p_request.add_argument("--prefer")
    p_request.add_argument("--subject-pool", help="Author pool for canonical reviewer independence rules")
    p_request.add_argument("--root")
    p_request.add_argument("--parent")
    p_request.add_argument("--task-complexity")
    p_request.add_argument("--escalation-reason")
    p_request.add_argument("--model", dest="requested_model")
    p_request.add_argument("--not-before", help="Strict UTC Z lower bound for this new request; never queues or authorizes retry")
    p_request.add_argument("--max-turns", type=int,
                           help="Per-request Claude turn ceiling (1..400); only tightens the existing admitted wrapper limit")
    p_request.add_argument("--quota-fallback", action="store_true",
                           help="Bounded foreground successors for proven initial quota rejection; inspect with status --follow")

    p_mac_return = sub.add_parser("recover-mac-policy")
    p_mac_return.add_argument("run_id")
    p_mac_return.add_argument("--root", required=True)
    p_mac_return.add_argument("--destination", required=True)

    for command in ("collect", "collection-result"):
        collect_parser = sub.add_parser(command)
        collect_parser.add_argument("run_id")
        for name in ("root", "parent"):
            collect_parser.add_argument("--"+name, required=True)
        for name in (("binding", "destination") if command == "collect" else ("collection", "receipt-sha256")):
            collect_parser.add_argument("--"+name, required=True)

    p_diag = sub.add_parser("provider-diagnostics", help="Explicit original-owner safe diagnostic projection; no raw capture or acceptance")
    p_diag.add_argument("run_id")
    for name in ("root", "parent", "binding", "destination"):
        p_diag.add_argument("--"+name, required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("run_id")
    p_status.add_argument("--follow", action="store_true")

    p_wait = sub.add_parser("wait")
    p_wait.add_argument("run_id")
    p_wait.add_argument("--timeout", type=float, default=30.0)
    p_wait.add_argument("--interval", type=float, default=1.0)
    p_wait.add_argument("--follow", action="store_true")

    p_result = sub.add_parser("result")
    p_result.add_argument("run_id")
    p_result.add_argument("--max-bytes", type=int, default=DEFAULT_RESULT_BYTES)

    p_artifacts = sub.add_parser("artifacts")
    p_artifacts.add_argument("run_id")
    for name in ("root", "parent", "host", "stdout-sha256", "destination"):
        p_artifacts.add_argument("--" + name, required=True)
    p_artifacts.add_argument("--path", action="append", required=True)

    p_capsule = sub.add_parser("capsule-artifacts")
    p_capsule.add_argument("run_id")
    p_capsule.add_argument("--destination", required=True)

    p_diagnose = sub.add_parser("capsule-diagnose")
    p_diagnose.add_argument("run_id")
    p_diagnose.add_argument("--destination", required=True)

    p_observe = sub.add_parser("observe-run")
    p_observe.add_argument("run_id")
    p_observe.add_argument("--root",required=True)
    p_observe.add_argument("--parent", help="opt in to ordinary artifact observation by its assigning parent")
    p_observe.add_argument("--destination",required=True)
    p_observe.add_argument("--support-metadata-only",action="store_true")

    p_native_sources = sub.add_parser("read-native-host-review-source")
    p_native_sources.add_argument("run_id")
    p_native_sources.add_argument("--root", required=True)
    p_native_sources.add_argument("--destination", required=True)

    p_native_review = sub.add_parser("inspect-native-host-review")
    p_native_review.add_argument("run_id")
    p_native_review.add_argument("--root", required=True)
    p_native_review.add_argument("--destination", required=True)

    p_current = sub.add_parser("current-output")
    p_current.add_argument("run_id")
    p_current.add_argument("--root", required=True)
    p_current.add_argument("--destination", required=True)

    p_current_source = sub.add_parser(
        "current-source",
        help="bounded CURRENT Git source observation; requires qualified installed "
             "route and current external scoped OS/tool permission")
    p_current_source.add_argument("--request", required=True)
    p_current_source.add_argument("--destination", required=True)

    p_accept = sub.add_parser("accept")
    p_accept.add_argument("run_id")
    p_accept.add_argument("--by", required=True, choices=("deterministic", "reviewer"))

    p_release_plan = sub.add_parser(
        "reclaim-plan", help="read-only exact accepted sparse worker provenance; no deletion")
    p_release_plan.add_argument("run_id")
    p_release_plan.add_argument("--root", required=True)
    p_release_plan.add_argument("--parent", required=True)
    p_release_plan.add_argument("--pinned-sha", required=True)

    p_cancel = sub.add_parser("cancel")
    p_cancel.add_argument("run_id")

    p_reconcile = sub.add_parser("reconcile-prestart")
    p_reconcile.add_argument("run_id")
    p_reconcile.add_argument("--root", required=True)

    p_preexec = sub.add_parser("reconcile-preexec")
    p_preexec.add_argument("run_id")
    p_preexec.add_argument("--root", required=True)
    p_preexec.add_argument("--recovery-support", required=True)

    p_original_native_review = sub.add_parser("reconcile-native-host-review")
    p_original_native_review.add_argument("run_id")
    p_original_native_review.add_argument("--root", required=True)

    for command in ("check-terminal", "reconcile-terminal"):
        p_terminal = sub.add_parser(command)
        p_terminal.add_argument("run_id")
        p_terminal.add_argument("--root", required=True)

    p_completed = sub.add_parser("reconcile-completed")
    p_completed.add_argument("run_id")
    p_completed.add_argument("--root", required=True)
    p_completed.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "provider-diagnostics":
        import original_delivery_collector as collector
        try:
            result=collector.collect_provider_diagnostics(args.binding,run_id=args.run_id,root=args.root,parent=args.parent,destination=args.destination)
            print(json.dumps(result,sort_keys=True))
            return 0
        except Exception:
            print('{"state":"UNAVAILABLE","reason":"diagnostic_unavailable"}')
            return 76
    if args.cmd in {"collect", "collection-result"}:
        command = ["/bin/bash", str(HERE/"remote_sub.sh"), "--collect-existing", args.run_id,
                   "--root", args.root, "--parent", args.parent]
        names = ("binding", "destination") if args.cmd == "collect" else ("collection", "receipt-sha256")
        for name in names:
            command.extend(["--"+name, getattr(args, name.replace("-", "_"))])
        return subprocess.run(command).returncode
    if args.cmd == "read-native-host-review-source":
        import artifact_delivery
        if artifact_delivery.digest(artifact_delivery.local_file(HERE / "native_host_review_source_delivery.py", 65536)) != '3ec53fa0be3c69c28e265a1bb5b1cab3cc0ee3f6f6c03b93908d6c2685f2e902':
            raise ValueError("native_source_delivery_head_changed")
        import native_host_review_source_delivery
        return native_host_review_source_delivery.main([args.run_id, "--root", args.root,
                                                      "--destination", args.destination])
    if args.cmd == "inspect-native-host-review":
        import native_host_review_delivery
        return native_host_review_delivery.main([args.run_id, "--root", args.root,
                                                "--destination", args.destination])
    if args.cmd == "recover-mac-policy":
        command = ["/bin/bash", str(HERE / "remote_sub.sh"), "--read-artifacts",
                   "--mac-policy-return", args.run_id, "--root", args.root,
                   "--destination", args.destination]
        return subprocess.run(command).returncode
    if args.cmd == "current-source":
        import artifact_delivery
        import current_source_observation as observation
        try:
            registry_raw = artifact_delivery.local_file(HERE / "hosts.json", 65536)
            registry = artifact_delivery.reader.strict_json(registry_raw)
            summary = current_source_flow(Path(args.request), args.destination,
                                          _current_source_owner_factory(registry))
            print(artifact_delivery.reader.canonical(summary).decode())
            return 0 if summary["state"] == "PUBLISHED" else 76
        except (observation.CurrentSourceError, OSError, ValueError, TypeError,
                KeyError, subprocess.SubprocessError):
            print('{"state":"REFUSED",'
                  '"reason":"current_source_intent_or_delivery_unconfirmed"}')
            return 75
    if args.cmd == "current-output":
        command = ["/bin/bash", str(HERE / "remote_sub.sh"), "--read-artifacts", "--current-output",
                   args.run_id, "--root", args.root, "--destination", args.destination]
        return subprocess.run(command).returncode
    if args.cmd == "observe-run":
        command = ["/bin/bash",str(HERE/"remote_sub.sh"),"--read-artifacts","--observe-run",args.run_id,"--root",args.root,"--destination",args.destination]
        if args.parent is not None:
            command.extend(["--parent", args.parent])
        if args.support_metadata_only:
            command.append("--support-metadata-only")
        return subprocess.run(command).returncode
    if args.cmd == "capsule-diagnose":
        command = ["/bin/bash", str(HERE / "remote_sub.sh"), "--read-artifacts",
                   "--capsule-diagnose", args.run_id, "--destination", args.destination]
        return subprocess.run(command).returncode
    if args.cmd == "capsule-artifacts":
        command = ["/bin/bash", str(HERE / "remote_sub.sh"), "--read-artifacts",
                   "--capsule-current", args.run_id, "--destination", args.destination]
        return subprocess.run(command).returncode
    if args.cmd == "artifacts":
        command = ["/bin/bash", str(HERE / "remote_sub.sh"), "--read-artifacts", args.run_id]
        for name in ("root", "parent", "host", "stdout-sha256", "destination"):
            command.extend(["--" + name, getattr(args, name.replace("-", "_"))])
        for path in args.path:
            command.extend(["--path", path])
        return subprocess.run(command).returncode
    try:
        if args.cmd == "reconcile-plain-packet-retention":
            import native_plain_packet_reconcile as packet_reconcile
            try:
                response = packet_reconcile.reconcile_original(
                    args.run_id, args.root, args.expected_proof_sha256)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                effect_state = getattr(exc, "effect_state", "NOT_APPLIED")
                _plain_packet_reconciliation_response(
                    {"schema": packet_reconcile.SCHEMA, "action": "UNQUALIFIED",
                     "run_id": args.run_id, "expected_root_id": args.root,
                     "effect_state": effect_state, "retry_allowed": False,
                     "worker_dispatch_performed": False}, effect_state)
                print("PLAIN_PACKET_RECONCILIATION_UNQUALIFIED: " + effect_state
                      + ": " + type(exc).__name__ + ": " + str(exc),
                      file=sys.stderr, flush=True)
                return 78
            # A returned operation may already have published the receipt.
            return 0 if _plain_packet_reconciliation_response(response, "EFFECT_UNKNOWN") else 78
        if args.cmd == "check-plain-packet-retention":
            import native_plain_packet_check as packet_check
            try:
                _json(packet_check.check_original(args.run_id, args.root))
                return 0
            except (OSError, ValueError, TypeError, KeyError) as exc:
                print("PLAIN_PACKET_CHECK_UNQUALIFIED: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
                return 78
        if args.cmd == "reconcile-completed":
            try:
                _json(completion_reconcile.reconcile(args.run_id, args.root, apply=args.apply))
                return 0
            except (OSError, ValueError, completion_reconcile.sqlite3.Error) as exc:
                print(str(exc), file=sys.stderr)
                return 78
        if args.cmd in {"check-terminal", "reconcile-terminal"}:
            try:
                action = terminal_reconcile.check if args.cmd == "check-terminal" else terminal_reconcile.reconcile
                _json(action(args.run_id, args.root))
                return 0
            except (terminal_reconcile.ReconciliationError, OSError, ValueError, terminal_reconcile.sqlite3.Error) as exc:
                print(str(exc), file=sys.stderr)
                return 78
        if args.cmd == "reconcile-preexec":
            try:
                _json(preexec_reconcile.reconcile_preexec(args.run_id, args.root, args.recovery_support))
                return 0
            except (preexec_reconcile.PreexecError, OSError, ValueError, subprocess.SubprocessError) as exc:
                print(str(exc), file=sys.stderr)
                return 78
        if args.cmd == "reconcile-native-host-review":
            try:
                _json(native_review_reconcile.reconcile_original(args.run_id, args.root))
                return 0
            except (native_review_reconcile.RecoveryUnavailable, OSError, ValueError,
                    subprocess.SubprocessError, native_review_reconcile.sqlite3.Error) as exc:
                print(str(exc), file=sys.stderr)
                return 78
        if args.cmd == "reconcile-prestart":
            try:
                _json(prestart_reconcile.reconcile_prestart(args.run_id, args.root))
                return 0
            except (prestart_reconcile.PrestartReconcileError, OSError, ValueError) as exc:
                print(str(exc), file=sys.stderr)
                return 78

        if args.cmd == "preview":
            _json(preview_route(
                args.id, args.task_class, pool=args.pool,
                model=args.requested_model, prefer=args.prefer,
                subject_pool=args.subject_pool,
                task_complexity=args.task_complexity,
                escalation_reason=args.escalation_reason,
            ))
            return 0
        if args.cmd == "request":
            if args.strict_manual_pin and args.quota_fallback:
                raise FabricTaskError("MANUAL_PIN_QUOTA_FALLBACK_REFUSED")
            stdin_bytes = sys.stdin.buffer.read() if args.stdin else None
            request_fn = request
            if args.quota_fallback:
                import fabric_continuation
                request_fn = lambda *a, **kw: fabric_continuation.foreground(sys.modules[__name__], *a, **kw)
            return request_fn(
                args.id,
                args.task_class,
                **({"artifact_names": args.artifact_output} if args.artifact_output else {}),
                **({"native_return": True} if args.native_return else {}),
                cwd=args.cwd,
                packet=Path(args.packet) if args.packet else None,
                stdin_bytes=stdin_bytes,
                pool=args.pool,
                prefer=args.prefer,
                **({"subject_pool": args.subject_pool} if args.subject_pool is not None else {}),
                root_id=args.root,
                parent_run_id=args.parent,
                task_complexity=args.task_complexity,
                escalation_reason=args.escalation_reason,
                requested_model=args.requested_model,
                qualification_host=args.qualification_host,
                new_macro_worktree=args.new_macro_worktree,
                cpu_scope_percent=args.cpu_scope_percent,
                strict_manual_pin=args.strict_manual_pin,
                **({"not_before": args.not_before} if args.not_before is not None else {}),
                **({"max_turns": args.max_turns} if args.max_turns is not None else {}),
            )
        if args.cmd == "status":
            if args.follow:
                import fabric_continuation
                _json(fabric_continuation.resolve(sys.modules[__name__], args.run_id))
            else:
                _json(inspect_run(args.run_id))
            return 0
        if args.cmd == "wait":
            if args.follow:
                import fabric_continuation
                _json(fabric_continuation.wait(sys.modules[__name__], args.run_id, args.timeout, args.interval))
            else:
                _json(wait_for(args.run_id, timeout=args.timeout, interval=args.interval))
            return 0
        if args.cmd == "result":
            sys.stdout.buffer.write(read_result(args.run_id, max_bytes=args.max_bytes))
            return 0
        if args.cmd == "reclaim-plan":
            _json(plan_accepted_macro_worktree_release(
                args.run_id, root_id=args.root,
                parent_run_id=args.parent, pinned_sha=args.pinned_sha))
            return 0
        if args.cmd == "accept":
            rid = validate_run_id(args.run_id)
            if rid in {prestart_reconcile.RUN_ID, preexec_reconcile.RUN_ID}:
                raise FabricTaskError("PRESTART_FAILURE_IS_NOT_ACCEPTED_WORK")
            # This adapter must not turn a failed, uncertain, or undelivered
            # child into a positive outcome. Review authority remains with the
            # caller; the existing ledger remains the sole outcome owner.
            current = inspect_run(rid)
            if (current["state"] != "TERMINAL"
                    or current["rc"] != 0
                    or current["signal"] != "ok"
                    or not current["result_available"]):
                raise FabricTaskError("ACCEPT_REFUSED: no successful delivered terminal result")
            try:
                delivered = read_result(rid, max_bytes=MAX_RESULT_BYTES)
            except (OSError, FabricTaskError) as exc:
                raise FabricTaskError("ACCEPT_REFUSED: retained result unreadable") from exc
            if not delivered:
                raise FabricTaskError("ACCEPT_REFUSED: retained result empty")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "pool_ledger.py"),
                    "outcome",
                    rid,
                    "--strict",
                    "--accepted-by",
                    args.by,
                ]
            )
            return int(proc.returncode)
        if args.cmd == "cancel":
            status = inspect_run(args.run_id)
            if status["state"] in {"TERMINAL", "TERMINAL_FAILURE", "RESULT_UNAVAILABLE"}:
                _json({**status, "cancel": "ALREADY_TERMINAL"})
                return 0
            _json({**status, "cancel": "CANCEL_UNAVAILABLE_USE_EXISTING_OWNER"})
            return 78
    except (ValueError, FabricTaskError) as exc:
        print(str(exc), file=sys.stderr)
        return 75
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
