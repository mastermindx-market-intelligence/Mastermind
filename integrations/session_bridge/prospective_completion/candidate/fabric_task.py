#!/usr/bin/env python3
"""Thin native-feeling CLI adapter over the incumbent Subagent Fabric owners.

This module owns no scheduler, queue, retry loop, idempotency database, provider
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


def _paths(run_id: str) -> tuple[Path, Path]:
    rid = validate_run_id(run_id)
    return (
        HERE / "state" / "remote_sub" / f"{rid}.log",
        HERE / "lanes" / f"{rid}.remote.stdout",
    )



def _acceptance_unknown(reason: str) -> dict[str, Any]:
    return {"accepted": None, "accepted_by": None, "acceptance_state": "UNVERIFIED",
            "acceptance_reason": reason, "root_id": None, "parent_run_id": None}


def _acceptance_projection(rid: str, status: dict[str, Any], original_log: bytes) -> dict[str, Any]:
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
                log_path, _ = _paths(rid)
                if _bounded_regular(log_path, MAX_LOG_BYTES) != original_log:
                    return projection
                identity = pool_ledger.read_execution_identity(
                    rid, expected_rc=status["rc"], expected_signal=status["signal"])
                if _bounded_regular(log_path, MAX_LOG_BYTES) == original_log:
                    projection.update(identity)
            except (AttributeError, OSError, FabricTaskError):
                pass
        return projection
    log_path, result_path = _paths(rid)
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
        projection = pool_ledger.read_acceptance(rid, expected_rc=status["rc"], expected_signal=status["signal"])
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


def inspect_run(run_id: str) -> dict[str, Any]:
    rid = validate_run_id(run_id)
    log_path, result_path = _paths(rid)
    missing_log = False
    metadata_error = None
    try:
        log_path.lstat()
    except FileNotFoundError:
        missing_log = True
    except OSError as exc:
        metadata_error = exc
    if missing_log:
        return {
            "schema": "mastermind.fabric_task_status.v1",
            "run_id": rid,
            "state": "NOT_FOUND",
            **_acceptance_unknown("EXECUTION_NOT_ELIGIBLE"),
            "rc": None,
            "signal": None,
            "result_available": False,
            "result_bytes": None,
        }
    try:
        if metadata_error is not None:
            raise metadata_error
        original_log = _bounded_regular(log_path, MAX_LOG_BYTES)
        text = original_log.decode("utf-8", errors="replace")
    except (OSError, FabricTaskError):
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
            verified.update(_acceptance_projection(rid, verified, original_log))
            return verified

    result_available = False
    result_bytes = None
    try:
        info = result_path.lstat()
        result_available = stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
        result_bytes = info.st_size if result_available else None
    except FileNotFoundError:
        pass
    except OSError:
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
    status.update(_acceptance_projection(rid, status, original_log))
    return status


def read_result(run_id: str, *, max_bytes: int = DEFAULT_RESULT_BYTES) -> bytes:
    rid = validate_run_id(run_id)
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or not 1 <= max_bytes <= MAX_RESULT_BYTES:
        raise ValueError("invalid result byte limit")
    _, result_path = _paths(rid)
    try:
        return _bounded_regular(result_path, max_bytes)
    except FileNotFoundError as exc:
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
    recoverable_return: bool = False,
    qualification_host: str | None = None,
) -> int:
    rid = validate_run_id(run_id)
    if bool(packet) == bool(stdin_bytes is not None):
        raise ValueError("provide exactly one of packet or stdin")
    env = os.environ.copy()
    observed_root = resolve_request_root(root_id, env)
    # Explicit empty arguments clear inherited values; None uses the existing
    # economic metadata. Selection and launch see the same exact witness.
    complexity = task_complexity if task_complexity is not None else env.get("POOL_TASK_COMPLEXITY", "")
    reason = escalation_reason if escalation_reason is not None else env.get("POOL_ESCALATION_REASON", "")
    if recoverable_return:
        if (artifact_names or qualification_host or task_class == 'domain_orchestration'
                or env.get('POOL_OPERATOR_CHILD_BUDGET','0') != '0'):
            raise FabricTaskError('RECOVERABLE_RETURN_OPTIONS_REFUSED')
        import original_delivery_collector
        original_delivery_collector.completion_caller(observed_root,parent_run_id)
    if artifact_names:
        import artifact_production
    if qualification_host:
        if pool != "grok" or artifact_names or native_return or requested_model or prefer:
            raise FabricTaskError("QUALIFICATION_OPTIONS_REFUSED")
        import fabric_host_qualification
        route = _parse_route(fabric_host_qualification.qualification_route(
            qualification_host, task_class=task_class, complexity=complexity,
            reason=reason, subject_pool=subject_pool,
            root=observed_root, parent=parent_run_id,
        ))
    else:
        route = _parse_route(pick.format_pick(
            task_class, prefer=prefer, host="auto", pool=pool,
            **({"subject_pool": subject_pool} if subject_pool is not None else {}),
            task_complexity=complexity, escalation_reason=reason,
            requested_model=requested_model, route_key=rid,
            **({"required_modes": sorted(artifact_production.MODES),
                "required_platforms": ["linux"]} if artifact_names else
               {"required_modes": ["glm","minimax","qwen"],"required_platforms": ["linux"]} if recoverable_return else {}),
        ))
    guard = pick.launch_policy(
        route["MODE"], task_class, route["MODEL"],
        escalation_reason=reason, task_complexity=complexity,
    )
    if not guard.get("allowed"):
        raise FabricTaskError("ECONOMIC_POLICY_REFUSED: " + str(guard.get("reason")))
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

    completion = None
    temp_path: Path | None = None
    try:
        if recoverable_return:
            import artifact_production
            state_dir = HERE / 'state' / 'remote_sub'
            state_dir.mkdir(parents=True,exist_ok=True)
            completion = original_delivery_collector.begin_completion(rid,observed_root,parent_run_id,
                route,packet.read_bytes() if packet is not None else stdin_bytes,cwd,artifact_production.source_digest(HERE))
            packet_path = completion.path / 'packet.txt'
            env['FABRIC_COMPLETION_CONTEXT'] = str(completion.path)
            env['FABRIC_COMPLETION_CONTROLLER_PID'] = str(os.getpid())
            env['FABRIC_COMPLETION_CUSTODY_FD'] = str(completion.lock)
        elif packet is None:
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
        proc = subprocess.run(argv, env=env, **({"pass_fds":(completion.lock,)} if completion is not None else {}))
        return int(proc.returncode)
    finally:
        if completion is not None:completion.close()
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def wait_for(run_id: str, *, timeout: float, interval: float) -> dict[str, Any]:
    rid = validate_run_id(run_id)
    if not (0 <= timeout <= 7200 and 0.05 <= interval <= 60):
        raise ValueError("invalid wait bounds")
    deadline = time.monotonic() + timeout
    while True:
        status = inspect_run(rid)
        if status["state"] in {
            "NOT_FOUND", "TERMINAL", "TERMINAL_FAILURE", "RESULT_UNAVAILABLE", "EFFECT_UNKNOWN", "STATUS_UNREADABLE", "RECONCILED_PRESTART_FAILURE", "RECONCILED_PREEXEC_FAILURE"
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_request = sub.add_parser("request")
    p_request.add_argument("--id", required=True)
    p_request.add_argument("--class", dest="task_class", required=True)
    p_request.add_argument("--recoverable-return",action="store_true",help="Prospective ordinary Linux run capture; no adoption or retry of existing operations")
    p_request.add_argument("--native-return", action="store_true", help="Subscribe this new paid child to the separately reviewed/trusted native Stop hook")
    p_request.add_argument("--artifact-output", action="append", help="Required new file basename; opts into verified artifact production")
    p_request.add_argument("--cwd", default=os.getcwd())
    packet_group = p_request.add_mutually_exclusive_group(required=True)
    packet_group.add_argument("--packet")
    packet_group.add_argument("--stdin", action="store_true")
    p_request.add_argument("--pool")
    p_request.add_argument("--qualification-host", choices=("mb", "m1"), help="Explicit first Grok worker on a pending qualified Mac; no enrollment")
    p_request.add_argument("--prefer")
    p_request.add_argument("--subject-pool", help="Author pool for canonical reviewer independence rules")
    p_request.add_argument("--root")
    p_request.add_argument("--parent")
    p_request.add_argument("--task-complexity")
    p_request.add_argument("--escalation-reason")
    p_request.add_argument("--model", dest="requested_model")

    p_mac_return = sub.add_parser("recover-mac-policy")
    p_mac_return.add_argument("run_id")
    p_mac_return.add_argument("--root", required=True)
    p_mac_return.add_argument("--destination", required=True)

    for command in ("collect", "collection-result", "collect-prospective"):
        collect_parser = sub.add_parser(command)
        collect_parser.add_argument("run_id")
        for name in ("root", "parent"):
            collect_parser.add_argument("--"+name, required=True)
        for name in (("binding", "destination") if command == "collect" else ("destination",) if command == "collect-prospective" else ("collection", "receipt-sha256")):
            collect_parser.add_argument("--"+name, required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("run_id")

    p_wait = sub.add_parser("wait")
    p_wait.add_argument("run_id")
    p_wait.add_argument("--timeout", type=float, default=30.0)
    p_wait.add_argument("--interval", type=float, default=1.0)

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

    p_accept = sub.add_parser("accept")
    p_accept.add_argument("run_id")
    p_accept.add_argument("--by", required=True, choices=("deterministic", "reviewer"))

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
    if args.cmd in {"collect", "collection-result", "collect-prospective"}:
        command = ["/bin/bash", str(HERE/"remote_sub.sh"), "--collect-existing", args.run_id,
                   "--root", args.root, "--parent", args.parent]
        names = ("binding", "destination") if args.cmd == "collect" else ("destination",) if args.cmd == "collect-prospective" else ("collection", "receipt-sha256")
        if args.cmd == "collect-prospective":command.append("--prospective")
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
    if args.cmd == "current-output":
        command = ["/bin/bash", str(HERE / "remote_sub.sh"), "--read-artifacts", "--current-output",
                   args.run_id, "--root", args.root, "--destination", args.destination]
        return subprocess.run(command).returncode
    if args.cmd == "observe-run":
        command = ["/bin/bash",str(HERE/"remote_sub.sh"),"--read-artifacts","--observe-run",args.run_id,"--root",args.root,"--destination",args.destination]
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
        if args.cmd == "request":
            stdin_bytes = sys.stdin.buffer.read() if args.stdin else None
            return request(
                args.id,
                args.task_class,
                **({"artifact_names": args.artifact_output} if args.artifact_output else {}),
                **({"native_return": True} if args.native_return else {}),
                **({"recoverable_return": True} if args.recoverable_return else {}),
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
            )
        if args.cmd == "status":
            _json(inspect_run(args.run_id))
            return 0
        if args.cmd == "wait":
            _json(wait_for(args.run_id, timeout=args.timeout, interval=args.interval))
            return 0
        if args.cmd == "result":
            sys.stdout.buffer.write(read_result(args.run_id, max_bytes=args.max_bytes))
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
