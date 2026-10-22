"""Original native-review preexec settlement consumption on existing Fabric controller.

This does not execute, retry, approve, release, or settle a remote worker. The
Ubuntu2 LaneLease owner has already published the exact settlement. This module
only verifies it and records one guarded controller-side reconciliation receipt
under the existing state/remote_sub owner, so Fabric status stops projecting
historical EFFECT_UNKNOWN once a real host settlement is proven.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
from pathlib import Path
import sqlite3
import stat
import subprocess
import time

import lane_runtime

HERE = Path(__file__).resolve().parent
RUN = "native-host-review-22f77378-01a0e0c7"
ROOT = "01a0e0c7-1ed2-7fa0-a4b4-890d30ea6311"
LEASE = "b17b0ca31f28"
HOST_RECEIPT_SHA = "fb06d3da62eb9d5e91326e384a767bc06a1d083672bfa6536589844d33217d75"
LOG_SHA = "8d2263486b863398f108ad83432974fc26240c9a2ae5862eb44dc56571c692fb"
STDOUT_SHA = "755dbdc639c0f1c0ea5f84289026c4ab944209b404fa83951cf36210bb57e04a"
RECEIPT_PATH = "/home/ubuntu2/lanes/ext/active/." + RUN + ".preexec-settlement.json"
MARKER_PATH = "/home/ubuntu2/lanes/ext/active/" + RUN
SCHEMA = "mastermind.fabric.preexec-controller-reconciliation.v1"


class RecoveryUnavailable(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RecoveryUnavailable(reason)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _file(path: Path, size: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        _require(stat.S_ISREG(opened.st_mode)
                 and opened.st_uid == os.getuid()
                 and not opened.st_mode & 0o002
                 and 0 <= opened.st_size <= size, "controller_file_custody")
        data = b""
        while len(data) <= size:
            chunk = os.read(fd, min(65536, size + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        after = os.fstat(fd)
        visible = path.lstat()
        _require(len(data) == opened.st_size
                 and (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                 == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                 == (visible.st_dev, visible.st_ino, visible.st_size, visible.st_mtime_ns),
                 "controller_file_changed")
        return data
    finally:
        os.close(fd)


def _ssh(command: str, max_size: int = 65536) -> bytes:
    # Reuse the original Fabric-owned Ubuntu2 SSH alias and one fixed command.
    process = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "ubuntu2", command],
        capture_output=True, timeout=25,
    )
    _require(process.returncode == 0 and len(process.stdout) <= max_size,
             "original_host_read_unavailable")
    return process.stdout


def _marker_absence_source() -> str:
    """Fixed read-only script; no caller path, PID, receipt or lifecycle input."""
    return 'import os, stat, sys\nfds=[]\nedges=[]\nroot_identity=None\ndef directory_identity(info):\n    return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid)\ndef verify():\n    if (directory_identity(os.fstat(fds[0]))!=root_identity\n            or directory_identity(os.stat("/",follow_symlinks=False))!=root_identity):\n        raise ValueError("root_changed")\n    for parent,name,fd,expected in edges:\n        if (directory_identity(os.fstat(fd))!=expected\n                or directory_identity(os.stat(name,dir_fd=parent,follow_symlinks=False))!=expected):\n            raise ValueError("directory_changed")\ndef missing_leaf(fd):\n    try:\n        os.stat("native-host-review-22f77378-01a0e0c7",dir_fd=fd,follow_symlinks=False)\n    except FileNotFoundError:\n        return\n    raise ValueError("marker_present")\ntry:\n    fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)\n    fds.append(fd)\n    root_info=os.fstat(fd)\n    root_identity=directory_identity(root_info)\n    if not stat.S_ISDIR(root_info.st_mode):\n        raise ValueError("root_not_directory")\n    for name in ("home","ubuntu2","lanes","ext","active"):\n        parent=fd\n        fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)\n        fds.append(fd)\n        info=os.fstat(fd)\n        if not stat.S_ISDIR(info.st_mode):\n            raise ValueError("parent_not_directory")\n        edges.append((parent,name,fd,directory_identity(info)))\n        verify()\n    active=os.fstat(fd)\n    # Match the incumbent LaneLease reconcile_preexec_hold directory guard:\n    # current UID, directory type, and no world-write. Group-write is allowed.\n    if active.st_uid!=os.getuid() or active.st_mode & 0o002:\n        raise ValueError("active_directory_custody")\n    verify()\n    missing_leaf(fd)\n    verify()\n    missing_leaf(fd)\n    verify()\nexcept (OSError,ValueError):\n    sys.exit(1)\nfinally:\n    for held in reversed(fds):\n        os.close(held)\n'


def _marker_absence_command() -> str:
    return "python3 -I -S -c " + shlex.quote(_marker_absence_source())


def _host_receipt() -> str:
    raw = _ssh("cat " + RECEIPT_PATH)
    _require(_sha(raw) == HOST_RECEIPT_SHA, "original_host_receipt_changed")
    try:
        value = json.loads(raw)
        lane_runtime.validate_preexec_settlement_receipt(value)
    except (json.JSONDecodeError, TypeError, ValueError, lane_runtime.LaneRuntimeError) as exc:
        raise RecoveryUnavailable("original_host_receipt_invalid") from exc
    _require(value["run_id"] == RUN and value["root_id"] == ROOT
             and value["lease_id"] == LEASE and value["phase"] == "removal_authorized"
             and len(value["census"]) > 0, "original_host_receipt_identity")
    # The actual marker must be absent; the receipt is not a waiver of a live lock.
    _ssh(_marker_absence_command(), max_size=0)
    _require(_sha(_ssh("cat " + RECEIPT_PATH)) == HOST_RECEIPT_SHA,
             "original_host_receipt_moved")
    return HOST_RECEIPT_SHA


def _controller_facts() -> str:
    original_log = _file(HERE / "state/remote_sub" / (RUN + ".log"), 1048576)
    original_output = _file(HERE / "lanes" / (RUN + ".remote.stdout"), 8388608)
    _require(_sha(original_log) == LOG_SHA and _sha(original_output) == STDOUT_SHA,
             "original_controller_artifact_changed")
    ledger_path = HERE.parent / "orch/fabric/ledger.jsonl"
    ledger_rows = []
    with ledger_path.open("rb") as source:
        for line in source:
            if RUN.encode() in line:
                try:
                    item = json.loads(line)
                except (ValueError, UnicodeError) as exc:
                    raise RecoveryUnavailable("original_ledger_unreadable") from exc
                if item.get("run_id") == RUN:
                    ledger_rows.append((item, line))
    _require(len(ledger_rows) == 1, "original_ledger_ambiguous")
    record, line = ledger_rows[0]
    _require(record.get("root_id") == ROOT and record.get("rc") == 76
             and record.get("signal") == "effect_unknown"
             and record.get("reason") == "remote_cleanup_unproven",
             "original_ledger_identity")
    broker = HERE / "broker/leases.sqlite"
    _require(broker.is_file() and not broker.is_symlink()
             and broker.stat().st_uid == os.getuid(), "original_broker_custody")
    with sqlite3.connect(broker.as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
        data = connection.execute(
            "SELECT id,orchestrator_id,pool,host,state,model FROM leases WHERE id=?",
            (LEASE,),
        ).fetchone()
    _require(data is not None
             and tuple(data[:4]) == (LEASE, ROOT, "minimax", "m2studio")
             and data[4] in ("expired", "released")
             and data[5] == "MiniMax-M3", "original_broker_not_settled")
    return _sha(line)


def sidecar_path() -> Path:
    return HERE / "state/remote_sub" / (RUN + ".preexec-reconciliation.json")


def _read_sidecar() -> dict | None:
    path = sidecar_path()
    if not os.path.lexists(path):
        return None
    raw = _file(path, 65536)
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise RecoveryUnavailable("controller_receipt_unreadable") from exc
    keys = {"schema", "run_id", "root_id", "lease_id", "host_receipt_sha256",
            "ledger_row_sha256", "created_at", "receipt_sha256"}
    _require(type(value) is dict and set(value) == keys
             and value["schema"] == SCHEMA
             and value["run_id"] == RUN and value["root_id"] == ROOT
             and value["lease_id"] == LEASE
             and value["host_receipt_sha256"] == HOST_RECEIPT_SHA,
             "controller_receipt_binding")
    material = dict(value)
    claimed = material.pop("receipt_sha256")
    _require(claimed == _sha(_canonical(material)), "controller_receipt_self_hash")
    return value


def status_from_receipt() -> dict | None:
    try:
        saved = _read_sidecar()
        if saved is None:
            return None
        _require(saved["ledger_row_sha256"] == _controller_facts(), "controller_ledger_changed")
        _require(saved["host_receipt_sha256"] == _host_receipt(), "original_host_settlement_changed")
        return {
            "schema": "mastermind.fabric_task_status.v1", "run_id": RUN,
            "root_id": ROOT, "state": "RECONCILED_PREEXEC_FAILURE",
            "rc": 76, "signal": "preexec_failure",
            "result_available": True, "result_bytes": 32,
            "accepted": None, "accepted_by": None,
            "acceptance_state": "UNVERIFIED",
            "acceptance_reason": "REVIEW_NOT_PERFORMED",
            "reconcile": {
                "original_host_settled": True,
                "broker_lease_expired": True,
                "original_result_preserved": True,
                "review_completed": False,
                "original_host_receipt_sha256": HOST_RECEIPT_SHA,
                "controller_receipt_sha256": saved["receipt_sha256"],
            },
        }
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error,
            subprocess.SubprocessError, RecoveryUnavailable):
        return None


def reconcile_original(run_id: str, root_id: str) -> dict:
    _require((run_id, root_id) == (RUN, ROOT), "original_operation_only")
    digest = _controller_facts()
    verified = _host_receipt()
    path = sidecar_path()
    saved = _read_sidecar()
    if saved is None:
        material = {
            "schema": SCHEMA, "run_id": RUN, "root_id": ROOT, "lease_id": LEASE,
            "host_receipt_sha256": verified, "ledger_row_sha256": digest,
            "created_at": time.time(),
        }
        material["receipt_sha256"] = _sha(_canonical(material))
        # Same original controller carrier, exclusive create, no marker/lease rewrite.
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            saved = _read_sidecar()
        else:
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(_canonical(material) + b"\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
            except BaseException:
                # Effect may have happened: do not unlink or retry blindly.
                raise
            saved = material
    _require(saved is not None and saved["host_receipt_sha256"] == verified
             and saved["ledger_row_sha256"] == digest, "controller_receipt_conflict")
    projection = status_from_receipt()
    _require(projection is not None, "controller_reconciliation_not_verified")
    return projection
