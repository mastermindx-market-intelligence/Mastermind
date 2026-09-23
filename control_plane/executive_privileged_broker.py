"""Receipt-gated root executor for a closed Executive OS action catalog.

The broker is intentionally not a scheduler, queue, or generic sudo service.
It accepts a validated action request, authenticates the kernel peer UID, and
runs one exact argv from :mod:`control_plane.executive_privileged_action`.
Every effect is fenced by an fsync'd in-flight marker and a durable terminal
receipt so transport loss can never be interpreted as proof of no effect.
"""
from __future__ import annotations

import ctypes
import dataclasses
import datetime as dt
import hashlib
import json
import os
import platform
import re
import signal
import socket
import stat
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from common.redaction import sanitize_external_text
from control_plane.executive_privileged_action import (
    ACTION_EFFECT_CLASS,
    ACTION_EFFECT_UNKNOWN_EXIT_CODE,
    PrivilegedActionRequest,
    PrivilegedActionStatusRequest,
    REQUEST_SCHEMA,
    STATUS_REQUEST_SCHEMA,
    build_argv,
    canonical_request_bytes,
    validate_request,
    validate_status_request,
)


BROKER_CONFIG_SCHEMA = "mastermind.executive_privileged_broker_config.v1"
RECEIPT_SCHEMA = "mastermind.executive_privileged_action_receipt.v1"
INFLIGHT_SCHEMA = "mastermind.executive_privileged_action_inflight.v1"
RECONCILE_REQUEST_SCHEMA = (
    "mastermind.executive_privileged_action_reconcile_not_applied_request.v1"
)
RECONCILIATION_SCHEMA = "mastermind.executive_privileged_action_reconciliation.v1"
STATUS_TERMINAL = "TERMINAL"
STATUS_EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
STATUS_RECONCILED_NOT_APPLIED = "RECONCILED_NOT_APPLIED"
STATUS_NOT_FOUND = "NOT_FOUND"
_RELEASE_PREFIX = Path("/Library/Application Support/MastermindExecutive/releases")
_RECEIPT_ROOT = Path("/var/db/mastermind-executive/privileged-actions/receipts")
_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CLOSED_ENV = {
    "HOME": "/var/empty",
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG": "C",
    "LC_ALL": "C",
    "NO_COLOR": "1",
}
_MAX_RECEIPT_BYTES = 64 * 1024
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_READINESS_RECEIPT_PATH = Path(
    "/Library/Application Support/MastermindExecutive/config/provider-readiness-v2.json"
)
_READINESS_TRANSACTION_LOCK = Path(
    "/Library/Application Support/MastermindExecutive/config/provider-readiness.transaction.lock"
)
_RECONCILE_REQUEST_KEYS = frozenset(
    {
        "schema",
        "target_request_id",
        "target_request_sha256",
        "target_marker_sha256",
        "target_release_sha",
        "readiness_receipt_sha256",
        "expected_credential_kind",
        "workspace_binding_class",
        "credential_expires_at",
    }
)
_INFLIGHT_RECORD_KEYS = frozenset(
    {
        "schema",
        "request_id",
        "request_sha256",
        "action",
        "effect_class",
        "started_at",
        "release_sha",
    }
)
_RECONCILIATION_KEYS = frozenset(
    {
        "schema",
        "classification",
        "target_request_id",
        "target_request_sha256",
        "target_action",
        "target_effect_class",
        "target_started_at",
        "target_release_sha",
        "target_marker_sha256",
        "readiness_receipt_sha256",
        "readiness_observed_at",
        "expected_credential_kind",
        "workspace_binding_class",
        "credential_expires_at",
        "readiness_transaction_lock_absent",
        "verify_ready_process_absent",
        "readiness_identity_current",
        "target_deadline_absent",
        "reconciler_release_sha",
        "reconciled_at",
        "broker_version",
    }
)
_TRUSTED_EFFECT_PATHS = (
    "ops/executive_os/service-control.sh",
    "ops/executive_os/provision-worker-auth.sh",
    "ops/executive_os/secondary_host_power_policy.py",
)
_TERMINAL_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "request_id",
        "request_sha256",
        "action",
        "effect_class",
        "started_at",
        "finished_at",
        "exit_code",
        "outcome",
        "release_sha",
        "broker_version",
        "stdout_bytes",
        "stdout_sha256",
        "stdout_excerpt",
        "stderr_bytes",
        "stderr_sha256",
        "stderr_excerpt",
    }
)


class PrivilegedBrokerError(RuntimeError):
    """Base class for a fail-closed privileged broker refusal."""


class PeerAuthorizationError(PrivilegedBrokerError):
    """The kernel peer is not an approved caller."""


class RequestIdConflictError(PrivilegedBrokerError):
    """One request id was reused with different canonical content."""


class EffectUnknownError(PrivilegedBrokerError):
    """An effect may have happened but lacks a safe terminal receipt."""


class BrokerTrustError(PrivilegedBrokerError):
    """The installed root trust boundary is absent or drifted."""


class ChildStartError(PrivilegedBrokerError):
    """The reviewed child failed before a process existed."""


class ReconciledNotAppliedError(PrivilegedBrokerError):
    """The original request is durably reconciled as not applied and must not replay."""


@dataclasses.dataclass(frozen=True)
class ReconcileNotAppliedRequest:
    target_request_id: str
    target_request_sha256: str
    target_marker_sha256: str
    target_release_sha: str
    readiness_receipt_sha256: str
    expected_credential_kind: str
    workspace_binding_class: str
    credential_expires_at: str

    def to_dict(self) -> dict[str, str]:
        return {
            "schema": RECONCILE_REQUEST_SCHEMA,
            "target_request_id": self.target_request_id,
            "target_request_sha256": self.target_request_sha256,
            "target_marker_sha256": self.target_marker_sha256,
            "target_release_sha": self.target_release_sha,
            "readiness_receipt_sha256": self.readiness_receipt_sha256,
            "expected_credential_kind": self.expected_credential_kind,
            "workspace_binding_class": self.workspace_binding_class,
            "credential_expires_at": self.credential_expires_at,
        }


def validate_reconcile_not_applied_request(
    raw: Mapping[str, Any],
) -> ReconcileNotAppliedRequest:
    if not isinstance(raw, Mapping) or frozenset(raw) != _RECONCILE_REQUEST_KEYS:
        raise PrivilegedBrokerError("reconciliation request keys are invalid")
    if raw.get("schema") != RECONCILE_REQUEST_SCHEMA:
        raise PrivilegedBrokerError("unsupported reconciliation request schema")
    request_id = raw.get("target_request_id")
    if not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise PrivilegedBrokerError("reconciliation target request_id is invalid")
    request_sha = raw.get("target_request_sha256")
    marker_sha = raw.get("target_marker_sha256")
    readiness_sha = raw.get("readiness_receipt_sha256")
    for value, label in (
        (request_sha, "target request"),
        (marker_sha, "target marker"),
        (readiness_sha, "readiness receipt"),
    ):
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise PrivilegedBrokerError(f"reconciliation {label} digest is invalid")
    release_sha = raw.get("target_release_sha")
    if not isinstance(release_sha, str) or _SHA40_RE.fullmatch(release_sha) is None:
        raise PrivilegedBrokerError("reconciliation target release is invalid")

    target_raw = {
        "schema": REQUEST_SCHEMA,
        "request_id": request_id,
        "action": "executive.worker_auth.verify_ready",
        "args": {
            "expected_credential_kind": raw.get("expected_credential_kind"),
            "workspace_binding_class": raw.get("workspace_binding_class"),
            "credential_expires_at": raw.get("credential_expires_at"),
        },
    }
    try:
        target = validate_request(target_raw)
    except ValueError as exc:
        raise PrivilegedBrokerError(
            "reconciliation target verify_ready arguments are invalid"
        ) from exc
    canonical_digest = hashlib.sha256(canonical_request_bytes(target)).hexdigest()
    if canonical_digest != request_sha:
        raise RequestIdConflictError(
            "reconciliation target request digest does not match supplied arguments"
        )
    args = target.args_dict()
    return ReconcileNotAppliedRequest(
        target_request_id=request_id,
        target_request_sha256=request_sha,
        target_marker_sha256=marker_sha,
        target_release_sha=release_sha,
        readiness_receipt_sha256=readiness_sha,
        expected_credential_kind=args["expected_credential_kind"],
        workspace_binding_class=args["workspace_binding_class"],
        credential_expires_at=args["credential_expires_at"],
    )


class Executor(Protocol):
    def __call__(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[bytes]: ...


@dataclasses.dataclass(frozen=True)
class PrivilegedBrokerConfig:
    release_root: Path
    receipt_root: Path
    allowed_peer_uids: tuple[int, ...]
    timeout_seconds: int = 120
    broker_version: str = "1"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "PrivilegedBrokerConfig":
        expected = {
            "schema",
            "release_root",
            "receipt_root",
            "allowed_peer_uids",
            "timeout_seconds",
            "broker_version",
        }
        if not isinstance(raw, Mapping) or set(raw) != expected:
            raise ValueError("privileged broker config keys are not exact")
        if raw["schema"] != BROKER_CONFIG_SCHEMA:
            raise ValueError("unsupported privileged broker config schema")
        release_text = raw["release_root"]
        receipt_text = raw["receipt_root"]
        if not isinstance(release_text, str) or not isinstance(receipt_text, str):
            raise ValueError("privileged broker paths must be strings")
        release = Path(release_text)
        try:
            relative = release.relative_to(_RELEASE_PREFIX)
        except ValueError as exc:
            raise ValueError("release_root is outside the installed Executive release root") from exc
        if len(relative.parts) != 1 or _SHA40_RE.fullmatch(relative.name) is None:
            raise ValueError("release_root must name one exact installed commit")
        receipt_root = Path(receipt_text)
        if receipt_root != _RECEIPT_ROOT:
            raise ValueError("receipt_root is not the reviewed privileged receipt root")
        peers_raw = raw["allowed_peer_uids"]
        if not isinstance(peers_raw, list) or not peers_raw:
            raise ValueError("allowed_peer_uids must be a non-empty list")
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in peers_raw):
            raise ValueError("allowed_peer_uids contains an invalid uid")
        peers = tuple(sorted(set(peers_raw)))
        if len(peers) != len(peers_raw) or 450 not in peers or 0 in peers:
            raise ValueError("allowed_peer_uids must include control uid 450 exactly once and exclude root")
        timeout = raw["timeout_seconds"]
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 900:
            raise ValueError("timeout_seconds is outside the reviewed range")
        version = raw["broker_version"]
        if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z._-]{1,32}", version):
            raise ValueError("broker_version is invalid")
        return cls(
            release_root=release,
            receipt_root=receipt_root,
            allowed_peer_uids=peers,
            timeout_seconds=timeout,
            broker_version=version,
        )


@dataclasses.dataclass(frozen=True)
class _ExecutionObservation:
    returncode: int
    stdout: bytes
    stderr: bytes


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_exclusive_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while persisting privileged broker state")
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _replace_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        _write_exclusive_json(temporary, value)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _read_bounded_json(path: Path) -> dict[str, Any]:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise BrokerTrustError(f"broker state is not a regular file: {path.name}")
    if info.st_size <= 0 or info.st_size > _MAX_RECEIPT_BYTES:
        raise BrokerTrustError(f"broker state has invalid size: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BrokerTrustError(f"broker state is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise BrokerTrustError(f"broker state is not a mapping: {path.name}")
    return value


def _read_optional_bounded_json(path: Path) -> dict[str, Any] | None:
    # exists() follows symlinks and hides malformed state as apparent absence.
    # Only a genuine missing directory entry permits the no-record path.
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise BrokerTrustError(f"broker state is unreadable: {path.name}") from exc
    return _read_bounded_json(path)


def _stable_file_identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        info.st_gid,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_stable_bounded_bytes(path: Path) -> tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise BrokerTrustError(f"broker evidence is unreadable: {path.name}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > _MAX_RECEIPT_BYTES:
            raise BrokerTrustError(f"broker evidence metadata is invalid: {path.name}")
        chunks: list[bytes] = []
        remaining = _MAX_RECEIPT_BYTES + 1
        while remaining > 0:
            part = os.read(descriptor, min(4096, remaining))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    try:
        path_after = path.lstat()
    except OSError as exc:
        raise BrokerTrustError(f"broker evidence identity changed: {path.name}") from exc
    if (
        len(raw) != before.st_size
        or _stable_file_identity(before) != _stable_file_identity(after)
        or _stable_file_identity(after) != _stable_file_identity(path_after)
    ):
        raise BrokerTrustError(f"broker evidence changed during read: {path.name}")
    return raw, after


def _validate_stored_release_sha(value: Any) -> str:
    if not isinstance(value, str) or _SHA40_RE.fullmatch(value) is None:
        raise BrokerTrustError("stored release_sha is not an exact Git commit")
    return value


def _validate_stored_digest(value: Any) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise BrokerTrustError("stored request_sha256 is not a valid digest")
    return value


def _validate_receipt_time(value: Any, field: str) -> dt.datetime:
    if not isinstance(value, str) or _UTC_RE.fullmatch(value) is None:
        raise BrokerTrustError(f"terminal receipt {field} is invalid")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise BrokerTrustError(f"terminal receipt {field} is invalid") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise BrokerTrustError(f"terminal receipt {field} is not canonical UTC")
    return parsed


def validate_terminal_receipt(
    value: Mapping[str, Any],
    *,
    expected_request_id: str | None = None,
    expected_request_sha256: str | None = None,
    expected_release_sha: str | None = None,
    expected_action: str | None = None,
) -> dict[str, Any]:
    """Validate one complete stored/wire receipt without granting effect authority."""
    if not isinstance(value, Mapping) or frozenset(value) != _TERMINAL_RECEIPT_KEYS:
        raise BrokerTrustError("terminal receipt keys are invalid")
    receipt = dict(value)
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise BrokerTrustError("terminal receipt schema is invalid")
    request_id = receipt.get("request_id")
    if not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise BrokerTrustError("terminal receipt request_id is invalid")
    try:
        digest = _validate_stored_digest(receipt.get("request_sha256"))
    except BrokerTrustError as exc:
        raise BrokerTrustError("terminal receipt request_sha256 is invalid") from exc
    action = receipt.get("action")
    if not isinstance(action, str) or action not in ACTION_EFFECT_CLASS:
        raise BrokerTrustError("terminal receipt action is invalid")
    if receipt.get("effect_class") != ACTION_EFFECT_CLASS[action]:
        raise BrokerTrustError("terminal receipt effect class is invalid")
    started_at = _validate_receipt_time(receipt.get("started_at"), "started_at")
    finished_at = _validate_receipt_time(receipt.get("finished_at"), "finished_at")
    if finished_at < started_at:
        raise BrokerTrustError("terminal receipt time order is invalid")
    exit_code = receipt.get("exit_code")
    outcome = receipt.get("outcome")
    if (
        isinstance(exit_code, bool)
        or not isinstance(exit_code, int)
        or outcome not in ("SUCCEEDED", "FAILED")
        or (outcome == "SUCCEEDED") != (exit_code == 0)
    ):
        raise BrokerTrustError("terminal receipt outcome is invalid")
    release_sha = _validate_stored_release_sha(receipt.get("release_sha"))
    version = receipt.get("broker_version")
    if not isinstance(version, str) or re.fullmatch(r"[0-9A-Za-z._-]{1,32}", version) is None:
        raise BrokerTrustError("terminal receipt broker_version is invalid")
    for stream in ("stdout", "stderr"):
        size = receipt.get(f"{stream}_bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise BrokerTrustError(f"terminal receipt {stream}_bytes is invalid")
        try:
            _validate_stored_digest(receipt.get(f"{stream}_sha256"))
        except BrokerTrustError as exc:
            raise BrokerTrustError(f"terminal receipt {stream}_sha256 is invalid") from exc
        excerpt = receipt.get(f"{stream}_excerpt")
        if not isinstance(excerpt, str) or len(excerpt) > 300:
            raise BrokerTrustError(f"terminal receipt {stream}_excerpt is invalid")
    for observed, expected, label in (
        (request_id, expected_request_id, "request_id"),
        (digest, expected_request_sha256, "request_sha256"),
        (release_sha, expected_release_sha, "release_sha"),
        (action, expected_action, "action"),
    ):
        if expected is not None and observed != expected:
            raise BrokerTrustError(f"terminal receipt {label} does not match the request")
    return receipt


def validate_reconciliation_record(
    value: Mapping[str, Any],
    *,
    expected_request_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) != _RECONCILIATION_KEYS:
        raise BrokerTrustError("reconciliation record keys are invalid")
    record = dict(value)
    if record.get("schema") != RECONCILIATION_SCHEMA:
        raise BrokerTrustError("reconciliation record schema is invalid")
    if record.get("classification") != "NOT_APPLIED":
        raise BrokerTrustError("reconciliation classification is invalid")
    request_id = record.get("target_request_id")
    if not isinstance(request_id, str) or _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise BrokerTrustError("reconciliation target request_id is invalid")
    if expected_request_id is not None and request_id != expected_request_id:
        raise BrokerTrustError("reconciliation target request_id differs")
    for field in (
        "target_request_sha256",
        "target_marker_sha256",
        "readiness_receipt_sha256",
    ):
        _validate_stored_digest(record.get(field))
    _validate_stored_release_sha(record.get("target_release_sha"))
    _validate_stored_release_sha(record.get("reconciler_release_sha"))
    if record.get("target_action") != "executive.worker_auth.verify_ready":
        raise BrokerTrustError("reconciliation target action is not verify_ready")
    if record.get("target_effect_class") != ACTION_EFFECT_CLASS[
        "executive.worker_auth.verify_ready"
    ]:
        raise BrokerTrustError("reconciliation target effect class is invalid")
    target_raw = {
        "schema": REQUEST_SCHEMA,
        "request_id": request_id,
        "action": "executive.worker_auth.verify_ready",
        "args": {
            "expected_credential_kind": record.get("expected_credential_kind"),
            "workspace_binding_class": record.get("workspace_binding_class"),
            "credential_expires_at": record.get("credential_expires_at"),
        },
    }
    try:
        target = validate_request(target_raw)
    except ValueError as exc:
        raise BrokerTrustError(
            "reconciliation target verify_ready arguments are invalid"
        ) from exc
    if (
        hashlib.sha256(canonical_request_bytes(target)).hexdigest()
        != record["target_request_sha256"]
    ):
        raise BrokerTrustError(
            "reconciliation target digest does not match recorded arguments"
        )
    target_started = _validate_receipt_time(
        record.get("target_started_at"), "target_started_at"
    )
    readiness_observed = _validate_receipt_time(
        record.get("readiness_observed_at"), "readiness_observed_at"
    )
    reconciled_at = _validate_receipt_time(
        record.get("reconciled_at"), "reconciled_at"
    )
    if readiness_observed >= target_started or reconciled_at < target_started:
        raise BrokerTrustError("reconciliation time ordering is invalid")
    if record.get("readiness_transaction_lock_absent") is not True:
        raise BrokerTrustError("reconciliation did not prove readiness lock absence")
    if record.get("verify_ready_process_absent") is not True:
        raise BrokerTrustError("reconciliation did not prove verify_ready process absence")
    if record.get("readiness_identity_current") is not True:
        raise BrokerTrustError("reconciliation did not prove readiness identity continuity")
    if record.get("target_deadline_absent") is not True:
        raise BrokerTrustError("reconciliation did not prove target deadline absence")
    version = record.get("broker_version")
    if not isinstance(version, str) or re.fullmatch(r"[0-9A-Za-z._-]{1,32}", version) is None:
        raise BrokerTrustError("reconciliation broker_version is invalid")
    return record


def _read_strict_inflight_marker_file(
    path: str | os.PathLike[str],
    *,
    expected_request_id: str,
    require_root_metadata: bool,
) -> tuple[dict[str, Any], bytes]:
    marker_path = Path(path)
    raw, info = _read_stable_bounded_bytes(marker_path)
    if require_root_metadata and (
        info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise BrokerTrustError("in-flight marker metadata is unsafe")
    try:
        marker = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BrokerTrustError("in-flight marker is invalid JSON") from exc
    if not isinstance(marker, dict) or frozenset(marker) != _INFLIGHT_RECORD_KEYS:
        raise BrokerTrustError("in-flight marker fields are invalid")
    if (
        marker.get("schema") != INFLIGHT_SCHEMA
        or marker.get("request_id") != expected_request_id
    ):
        raise BrokerTrustError("in-flight marker identity is invalid")
    _validate_stored_digest(marker.get("request_sha256"))
    _validate_stored_release_sha(marker.get("release_sha"))
    action = marker.get("action")
    if not isinstance(action, str) or action not in ACTION_EFFECT_CLASS:
        raise BrokerTrustError("in-flight marker action is invalid")
    if marker.get("effect_class") != ACTION_EFFECT_CLASS[action]:
        raise BrokerTrustError("in-flight marker effect class is invalid")
    _validate_receipt_time(marker.get("started_at"), "started_at")
    return marker, raw


def _read_strict_reconciliation_record_file(
    path: str | os.PathLike[str],
    *,
    expected_request_id: str,
    require_root_metadata: bool,
) -> dict[str, Any]:
    record_path = Path(path)
    raw, info = _read_stable_bounded_bytes(record_path)
    if require_root_metadata and (
        info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_nlink != 1
    ):
        raise BrokerTrustError("reconciliation record metadata is unsafe")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BrokerTrustError("reconciliation record is invalid JSON") from exc
    return validate_reconciliation_record(
        value,
        expected_request_id=expected_request_id,
    )


def validate_reconciliation_pair(
    marker_path: str | os.PathLike[str],
    reconciliation_path: str | os.PathLike[str],
    *,
    expected_request_id: str,
    require_root_metadata: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate one preserved marker and its create-only NOT_APPLIED record."""

    marker_path = Path(marker_path)
    reconciliation_path = Path(reconciliation_path)
    expected_name = f"{expected_request_id}.json"
    if (
        marker_path.name != expected_name
        or reconciliation_path.name != expected_name
        or marker_path.parent.name != "inflight"
        or reconciliation_path.parent.name != "reconciled"
        or marker_path.parent.parent != reconciliation_path.parent.parent
    ):
        raise BrokerTrustError("reconciliation evidence paths are not the reviewed pair")

    receipt_root = marker_path.parent.parent
    if require_root_metadata:
        if receipt_root != _RECEIPT_ROOT:
            raise BrokerTrustError("reconciliation evidence is outside the privileged receipt root")
        for ancestor in (
            receipt_root.parent.parent,
            receipt_root.parent,
            receipt_root,
            marker_path.parent,
            reconciliation_path.parent,
        ):
            try:
                info = ancestor.lstat()
            except OSError as exc:
                raise BrokerTrustError(
                    "reconciliation evidence namespace is unavailable"
                ) from exc
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or info.st_gid != 0
                or stat.S_IMODE(info.st_mode) & 0o022
            ):
                raise BrokerTrustError(
                    "reconciliation evidence namespace metadata is unsafe"
                )

    record = _read_strict_reconciliation_record_file(
        reconciliation_path,
        expected_request_id=expected_request_id,
        require_root_metadata=require_root_metadata,
    )
    marker, raw = _read_strict_inflight_marker_file(
        marker_path,
        expected_request_id=expected_request_id,
        require_root_metadata=require_root_metadata,
    )
    if hashlib.sha256(raw).hexdigest() != record["target_marker_sha256"]:
        raise BrokerTrustError("reconciled in-flight marker bytes changed")
    for marker_field, record_field in (
        ("request_sha256", "target_request_sha256"),
        ("action", "target_action"),
        ("effect_class", "target_effect_class"),
        ("started_at", "target_started_at"),
        ("release_sha", "target_release_sha"),
    ):
        if marker.get(marker_field) != record.get(record_field):
            raise BrokerTrustError(
                f"reconciliation no longer matches marker field {marker_field}"
            )
    return record, marker


def _default_reconciliation_observer() -> Mapping[str, Any]:
    raw, info = _read_stable_bounded_bytes(_READINESS_RECEIPT_PATH)
    if (
        info.st_uid != 0
        or info.st_gid != 0
        or stat.S_IMODE(info.st_mode) != 0o400
        or info.st_nlink != 1
    ):
        raise BrokerTrustError("provider readiness receipt metadata is unsafe")
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BrokerTrustError("provider readiness receipt is invalid JSON") from exc
    if not isinstance(document, dict):
        raise BrokerTrustError("provider readiness receipt is not an object")

    try:
        from control_plane.codex_worker import load_codex_attestation_receipt
        from ops.executive_os import provider_readiness

        current_auth_identity = provider_readiness.current_auth_identity(
            provider_readiness.AUTH_PATH,
            worker_uid=provider_readiness.WORKER_UID,
            worker_gid=provider_readiness.WORKER_GID,
        )
        attestation_receipt_path = (
            _RELEASE_PREFIX.parent
            / f"codex-attestation-{provider_readiness.CODEX_VERSION}.json"
        )
        binary_attestation = load_codex_attestation_receipt(
            attestation_receipt_path,
            expected_binary_path=provider_readiness.CODEX_BINARY,
            expected_owner_gid=provider_readiness.WORKER_GID,
        )
        binary_info = provider_readiness.CODEX_BINARY.lstat()
        current_binary_identity = {
            "path": binary_attestation.path,
            "version": binary_attestation.version,
            "sha256": binary_attestation.sha256,
            "team_identifier": binary_attestation.team_identifier,
            "size": binary_attestation.size,
            "device": binary_attestation.device,
            "inode": binary_attestation.inode,
            "mode": binary_attestation.mode,
            "uid": binary_attestation.uid,
            "gid": binary_attestation.gid,
            "mtime_ns": binary_attestation.mtime_ns,
            "ctime_ns": binary_info.st_ctime_ns,
            "nlink": binary_info.st_nlink,
        }
    except Exception as exc:
        raise BrokerTrustError(
            "current provider readiness identities could not be validated"
        ) from exc

    try:
        _READINESS_TRANSACTION_LOCK.lstat()
    except FileNotFoundError:
        lock_present = False
    except OSError as exc:
        raise BrokerTrustError("provider readiness transaction lock is unreadable") from exc
    else:
        lock_present = True

    completed = subprocess.run(
        ["/bin/ps", "ax", "-o", "command="],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_CLOSED_ENV,
        timeout=5,
        check=False,
    )
    if completed.returncode != 0:
        raise BrokerTrustError("could not census provider readiness processes")
    commands = completed.stdout.decode("utf-8", errors="replace").splitlines()
    active = tuple(
        line.strip()
        for line in commands
        if "provision-worker-auth.sh" in line and "--verify-ready" in line
    )
    return {
        "readiness_receipt_sha256": hashlib.sha256(raw).hexdigest(),
        "readiness_document": document,
        "readiness_transaction_lock_present": lock_present,
        "verify_ready_processes": active,
        "current_auth_identity": current_auth_identity,
        "current_binary_identity": current_binary_identity,
    }


def _default_executor(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], timeout: int
) -> subprocess.CompletedProcess[bytes]:
    try:
        process = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=dict(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as exc:
        raise ChildStartError("privileged child could not be started") from exc

    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.communicate()
        except OSError:
            pass
        raise EffectUnknownError(
            "privileged child timed out after spawn; effect is unknown"
        ) from exc
    except OSError as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
        try:
            process.communicate()
        except OSError:
            pass
        raise EffectUnknownError(
            "privileged child transport failed after spawn; effect is unknown"
        ) from exc

    return subprocess.CompletedProcess(list(argv), process.returncode, stdout, stderr)


def _assert_root_owned_nonwritable(path: Path, *, directory: bool) -> os.stat_result:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        raise BrokerTrustError(f"trusted path is a symlink: {path}")
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(info.st_mode):
        raise BrokerTrustError(f"trusted path has wrong type: {path}")
    if info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022:
        raise BrokerTrustError(f"trusted path ownership/mode drifted: {path}")
    return info


def _verify_release_entry(release_root: Path, manifest: Mapping[str, Any], relative: str) -> None:
    rows = manifest.get("entries")
    if not isinstance(rows, list):
        raise BrokerTrustError("release manifest entries are invalid")
    matches = [row for row in rows if isinstance(row, dict) and row.get("path") == relative]
    if len(matches) != 1:
        raise BrokerTrustError(f"release manifest has no unique entry for {relative}")
    row = matches[0]
    path = release_root / relative
    info = _assert_root_owned_nonwritable(path, directory=False)
    if row.get("type") != "file" or row.get("uid") != 0 or row.get("gid") != 0:
        raise BrokerTrustError(f"release manifest metadata drifted for {relative}")
    mode = row.get("mode")
    size = row.get("size")
    digest = row.get("sha256")
    if mode != stat.S_IMODE(info.st_mode) or size != info.st_size:
        raise BrokerTrustError(f"installed metadata drifted for {relative}")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise BrokerTrustError(f"release manifest digest is invalid for {relative}")
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed != digest:
        raise BrokerTrustError(f"installed digest drifted for {relative}")


def verify_production_trust(config: PrivilegedBrokerConfig) -> None:
    if os.geteuid() != 0:
        raise BrokerTrustError("privileged broker must run as root")
    _assert_root_owned_nonwritable(_RELEASE_PREFIX, directory=True)
    _assert_root_owned_nonwritable(config.release_root, directory=True)
    manifest_path = config.release_root / ".executive-release-manifest.json"
    _assert_root_owned_nonwritable(manifest_path, directory=False)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BrokerTrustError("release manifest is unreadable") from exc
    if not isinstance(manifest, dict):
        raise BrokerTrustError("release manifest is invalid")
    if manifest.get("schema_version") != "mastermind.executive_release_manifest/v1":
        raise BrokerTrustError("release manifest schema is invalid")
    if manifest.get("commit_sha") != config.release_root.name:
        raise BrokerTrustError("release manifest commit does not match release root")
    for relative in _TRUSTED_EFFECT_PATHS:
        _verify_release_entry(config.release_root, manifest, relative)


class PrivilegedActionBroker:
    def __init__(
        self,
        config: PrivilegedBrokerConfig,
        *,
        executor: Executor = _default_executor,
        require_root: bool = True,
        trust_validator: Callable[[PrivilegedBrokerConfig], None] = verify_production_trust,
        reconciliation_observer: Callable[[], Mapping[str, Any]] = _default_reconciliation_observer,
    ) -> None:
        self.config = config
        self.receipt_root = Path(config.receipt_root)
        self.inflight_root = self.receipt_root / "inflight"
        self.reconciliation_root = self.receipt_root / "reconciled"
        self._executor = executor
        self._require_root = require_root
        self._reconciliation_observer = reconciliation_observer
        if require_root and os.geteuid() != 0:
            raise BrokerTrustError("privileged broker must run as root")
        trust_validator(config)
        self.receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.inflight_root.mkdir(exist_ok=True, mode=0o700)
        self.reconciliation_root.mkdir(exist_ok=True, mode=0o700)
        if require_root:
            for path, label in (
                (self.receipt_root, "privileged receipt root"),
                (self.inflight_root, "privileged in-flight root"),
                (self.reconciliation_root, "privileged reconciliation root"),
            ):
                info = path.lstat()
                if info.st_uid != 0 or info.st_gid != 0 or not stat.S_ISDIR(info.st_mode):
                    raise BrokerTrustError(f"{label} ownership drifted")
                os.chmod(path, 0o700)

    def receipt_path(self, request_id: str) -> Path:
        return self.receipt_root / f"{request_id}.json"

    def inflight_path(self, request_id: str) -> Path:
        return self.inflight_root / f"{request_id}.json"

    def reconciliation_path(self, request_id: str) -> Path:
        return self.reconciliation_root / f"{request_id}.json"

    def _read_strict_inflight_marker(
        self, request_id: str
    ) -> tuple[dict[str, Any], bytes]:
        return _read_strict_inflight_marker_file(
            self.inflight_path(request_id),
            expected_request_id=request_id,
            require_root_metadata=self._require_root,
        )

    def _read_reconciliation_for_status(
        self, request_id: str
    ) -> dict[str, Any] | None:
        path = self.reconciliation_path(request_id)
        try:
            path.lstat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise BrokerTrustError("reconciliation record is unreadable") from exc
        return _read_strict_reconciliation_record_file(
            path,
            expected_request_id=request_id,
            require_root_metadata=self._require_root,
        )

    def _validate_reconciliation_marker(
        self, record: Mapping[str, Any]
    ) -> dict[str, Any]:
        request_id = str(record["target_request_id"])
        validated_record, marker = validate_reconciliation_pair(
            self.inflight_path(request_id),
            self.reconciliation_path(request_id),
            expected_request_id=request_id,
            require_root_metadata=self._require_root,
        )
        if dict(record) != validated_record:
            raise BrokerTrustError("reconciliation record changed during validation")
        return marker

    def _existing_reconciliation_for_request(
        self, request: PrivilegedActionRequest, digest: str
    ) -> dict[str, Any] | None:
        record = self._read_reconciliation_for_status(request.request_id)
        if record is None:
            return None
        if record["target_request_sha256"] != digest:
            raise RequestIdConflictError(
                "request id already has a different reconciled request"
            )
        if record["target_action"] != request.action:
            raise RequestIdConflictError(
                "request id already has a different reconciled action"
            )
        self._validate_reconciliation_marker(record)
        return record

    @staticmethod
    def _request_digest(request: PrivilegedActionRequest) -> str:
        return hashlib.sha256(canonical_request_bytes(request)).hexdigest()

    def _existing_terminal(self, request: PrivilegedActionRequest, digest: str) -> dict[str, Any] | None:
        path = self.receipt_path(request.request_id)
        value = _read_optional_bounded_json(path)
        if value is None:
            return None
        receipt = validate_terminal_receipt(value, expected_request_id=request.request_id)
        if receipt["release_sha"] != self.config.release_root.name:
            raise RequestIdConflictError("request id belongs to a different installed release")
        if receipt["request_sha256"] != digest:
            raise RequestIdConflictError("request id already has a different terminal request")
        if receipt["action"] != request.action:
            raise BrokerTrustError("terminal receipt action does not match the request")
        return receipt

    def _check_inflight(self, request: PrivilegedActionRequest, digest: str) -> None:
        path = self.inflight_path(request.request_id)
        value = _read_optional_bounded_json(path)
        if value is None:
            return
        if value.get("schema") != INFLIGHT_SCHEMA or value.get("request_id") != request.request_id:
            raise BrokerTrustError("in-flight marker identity is invalid")
        if value.get("release_sha") != self.config.release_root.name:
            raise RequestIdConflictError("request id belongs to a different installed release")
        if value.get("request_sha256") != digest:
            raise RequestIdConflictError("request id already has a different in-flight request")
        raise EffectUnknownError("matching request has a stale in-flight marker; effect is unknown")

    def _write_inflight(self, request: PrivilegedActionRequest, digest: str, started_at: str) -> None:
        value = {
            "schema": INFLIGHT_SCHEMA,
            "request_id": request.request_id,
            "request_sha256": digest,
            "action": request.action,
            "effect_class": request.effect_class,
            "started_at": started_at,
            "release_sha": self.config.release_root.name,
        }
        try:
            _write_exclusive_json(self.inflight_path(request.request_id), value)
        except FileExistsError:
            self._check_inflight(request, digest)
            raise EffectUnknownError("in-flight marker appeared concurrently")

    def _write_terminal_receipt(self, request: PrivilegedActionRequest, receipt: Mapping[str, Any]) -> None:
        _replace_json(self.receipt_path(request.request_id), receipt)

    def _remove_inflight(self, request_id: str) -> None:
        path = self.inflight_path(request_id)
        path.unlink()
        _fsync_directory(self.inflight_root)

    def _handle_outcome(
        self, raw_request: Mapping[str, Any], *, peer_uid: int
    ) -> tuple[dict[str, Any], bool]:
        if isinstance(peer_uid, bool) or not isinstance(peer_uid, int) or peer_uid not in self.config.allowed_peer_uids:
            raise PeerAuthorizationError("kernel peer uid is not authorized for privileged actions")
        request = validate_request(raw_request)
        digest = self._request_digest(request)
        reconciled = self._existing_reconciliation_for_request(request, digest)
        existing = self._existing_terminal(request, digest)
        if reconciled is not None and existing is not None:
            raise BrokerTrustError(
                "request id has both terminal and reconciliation records"
            )
        if reconciled is not None:
            raise ReconciledNotAppliedError(
                "matching request was reconciled as not applied and cannot replay"
            )
        if existing is not None:
            return existing, True
        self._check_inflight(request, digest)

        started_at = _utc_now()
        self._write_inflight(request, digest, started_at)
        argv = build_argv(request, self.config.release_root)
        try:
            completed = self._executor(
                argv,
                cwd=self.config.release_root,
                env=_CLOSED_ENV,
                timeout=self.config.timeout_seconds,
            )
        except ChildStartError as exc:
            try:
                self._remove_inflight(request.request_id)
            except OSError as cleanup_exc:
                raise EffectUnknownError("child start failed and in-flight cleanup failed") from cleanup_exc
            raise PrivilegedBrokerError("privileged child could not be started") from exc
        except EffectUnknownError:
            raise
        except subprocess.TimeoutExpired as exc:
            raise EffectUnknownError("privileged child timed out after spawn; effect is unknown") from exc
        except OSError as exc:
            # An injected executor cannot prove whether its OSError occurred before
            # or after spawn. Preserve the marker and fail closed as effect-unknown.
            raise EffectUnknownError("privileged executor failed after admission; effect is unknown") from exc

        uncertain_exit = ACTION_EFFECT_UNKNOWN_EXIT_CODE.get(request.action)
        if uncertain_exit is not None and completed.returncode == uncertain_exit:
            raise EffectUnknownError(
                "privileged child reported action-level effect uncertainty"
            )

        stdout = bytes(completed.stdout or b"")
        stderr = bytes(completed.stderr or b"")
        finished_at = _utc_now()
        receipt: dict[str, Any] = {
            "schema": RECEIPT_SCHEMA,
            "request_id": request.request_id,
            "request_sha256": digest,
            "action": request.action,
            "effect_class": request.effect_class,
            "started_at": started_at,
            "finished_at": finished_at,
            "exit_code": int(completed.returncode),
            "outcome": "SUCCEEDED" if completed.returncode == 0 else "FAILED",
            "release_sha": self.config.release_root.name,
            "broker_version": self.config.broker_version,
            "stdout_bytes": len(stdout),
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stdout_excerpt": sanitize_external_text(stdout.decode("utf-8", "replace"), limit=300),
            "stderr_bytes": len(stderr),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "stderr_excerpt": sanitize_external_text(stderr.decode("utf-8", "replace"), limit=300),
        }
        try:
            self._write_terminal_receipt(request, receipt)
        except OSError as exc:
            raise EffectUnknownError("privileged child completed but terminal receipt failed") from exc
        try:
            self._remove_inflight(request.request_id)
        except OSError as exc:
            # The terminal receipt wins replay, but cleanup drift must not be called clean success.
            raise EffectUnknownError("terminal receipt exists but in-flight cleanup failed") from exc
        return receipt, False

    def handle(self, raw_request: Mapping[str, Any], *, peer_uid: int) -> dict[str, Any]:
        receipt, _replayed = self._handle_outcome(raw_request, peer_uid=peer_uid)
        return receipt

    def reconcile_not_applied(
        self, raw_request: Mapping[str, Any], *, peer_uid: int
    ) -> tuple[dict[str, Any], bool]:
        if (
            isinstance(peer_uid, bool)
            or not isinstance(peer_uid, int)
            or peer_uid not in self.config.allowed_peer_uids
        ):
            raise PeerAuthorizationError(
                "kernel peer uid is not authorized for privileged actions"
            )
        request = validate_reconcile_not_applied_request(raw_request)
        terminal = self._read_terminal_for_status(request.target_request_id)
        if terminal is not None:
            raise PrivilegedBrokerError(
                "target request already has a terminal receipt and cannot be reconciled"
            )

        existing = self._read_reconciliation_for_status(request.target_request_id)
        if existing is not None:
            expected = {
                "target_request_sha256": request.target_request_sha256,
                "target_marker_sha256": request.target_marker_sha256,
                "target_release_sha": request.target_release_sha,
                "readiness_receipt_sha256": request.readiness_receipt_sha256,
                "expected_credential_kind": request.expected_credential_kind,
                "workspace_binding_class": request.workspace_binding_class,
                "credential_expires_at": request.credential_expires_at,
            }
            if any(existing.get(key) != value for key, value in expected.items()):
                raise RequestIdConflictError(
                    "target request already has a different reconciliation record"
                )
            self._validate_reconciliation_marker(existing)
            return existing, True

        marker, marker_raw = self._read_strict_inflight_marker(
            request.target_request_id
        )
        if marker["action"] != "executive.worker_auth.verify_ready":
            raise PrivilegedBrokerError(
                "only verify_ready in-flight markers may be reconciled as not applied"
            )
        if marker["request_sha256"] != request.target_request_sha256:
            raise RequestIdConflictError(
                "target request digest differs from the in-flight marker"
            )
        if marker["release_sha"] != request.target_release_sha:
            raise RequestIdConflictError(
                "target release differs from the in-flight marker"
            )
        if hashlib.sha256(marker_raw).hexdigest() != request.target_marker_sha256:
            raise BrokerTrustError("target in-flight marker bytes differ")

        evidence = self._reconciliation_observer()
        required_evidence = {
            "readiness_receipt_sha256",
            "readiness_document",
            "readiness_transaction_lock_present",
            "verify_ready_processes",
            "current_auth_identity",
            "current_binary_identity",
        }
        if not isinstance(evidence, Mapping) or set(evidence) != required_evidence:
            raise BrokerTrustError("readiness reconciliation evidence is incomplete")
        if evidence["readiness_receipt_sha256"] != request.readiness_receipt_sha256:
            raise BrokerTrustError("provider readiness receipt changed after target request")
        document = evidence["readiness_document"]
        if (
            not isinstance(document, Mapping)
            or document.get("schema_version")
            != "mastermind.executive_provider_readiness/v2"
            or document.get("passed") is not True
            or document.get("refusal") is not None
            or document.get("expected_credential_kind")
            != request.expected_credential_kind
            or document.get("workspace_binding_class")
            != request.workspace_binding_class
        ):
            raise BrokerTrustError(
                "current provider readiness receipt is not the prior passing receipt"
            )
        prior_credential_expires_at = document.get("credential_expires_at")
        if (
            not isinstance(prior_credential_expires_at, str)
            or _UTC_RE.fullmatch(prior_credential_expires_at) is None
        ):
            raise BrokerTrustError(
                "current provider readiness receipt has an invalid credential expiry"
            )
        if prior_credential_expires_at == request.credential_expires_at:
            raise BrokerTrustError(
                "current provider readiness receipt already carries the target deadline"
            )

        current_auth_identity = evidence["current_auth_identity"]
        current_binary_identity = evidence["current_binary_identity"]
        receipt_auth_identity = document.get("credential_lstat")
        receipt_binary_identity = document.get("codex_binary")
        provider_identity = document.get("provider_identity")
        if (
            not isinstance(current_auth_identity, Mapping)
            or not isinstance(current_binary_identity, Mapping)
            or not isinstance(receipt_auth_identity, Mapping)
            or not isinstance(receipt_binary_identity, Mapping)
            or not isinstance(provider_identity, Mapping)
            or receipt_auth_identity != dict(current_auth_identity)
            or receipt_binary_identity != dict(current_binary_identity)
            or provider_identity.get("credential_lstat") != dict(current_auth_identity)
            or provider_identity.get("codex_binary") != dict(current_binary_identity)
        ):
            raise BrokerTrustError(
                "current provider auth or installed binary identity differs from the pre-effect readiness receipt"
            )

        observed_at = document.get("observed_at")
        observed_time = _validate_receipt_time(
            observed_at, "readiness_observed_at"
        )
        target_started = _validate_receipt_time(
            marker["started_at"], "target_started_at"
        )
        if observed_time >= target_started:
            raise BrokerTrustError(
                "provider readiness receipt is not provably older than target request"
            )
        if evidence["readiness_transaction_lock_present"] is not False:
            raise BrokerTrustError(
                "provider readiness transaction lock is still present"
            )
        processes = evidence["verify_ready_processes"]
        if (
            not isinstance(processes, (tuple, list))
            or any(not isinstance(value, str) for value in processes)
            or len(processes) != 0
        ):
            raise BrokerTrustError("a verify_ready process may still be active")

        record: dict[str, Any] = {
            "schema": RECONCILIATION_SCHEMA,
            "classification": "NOT_APPLIED",
            "target_request_id": request.target_request_id,
            "target_request_sha256": request.target_request_sha256,
            "target_action": marker["action"],
            "target_effect_class": marker["effect_class"],
            "target_started_at": marker["started_at"],
            "target_release_sha": marker["release_sha"],
            "target_marker_sha256": request.target_marker_sha256,
            "readiness_receipt_sha256": request.readiness_receipt_sha256,
            "readiness_observed_at": observed_at,
            "expected_credential_kind": request.expected_credential_kind,
            "workspace_binding_class": request.workspace_binding_class,
            "credential_expires_at": request.credential_expires_at,
            "readiness_transaction_lock_absent": True,
            "verify_ready_process_absent": True,
            "readiness_identity_current": True,
            "target_deadline_absent": True,
            "reconciler_release_sha": self.config.release_root.name,
            "reconciled_at": _utc_now(),
            "broker_version": self.config.broker_version,
        }
        validate_reconciliation_record(
            record, expected_request_id=request.target_request_id
        )
        try:
            _write_exclusive_json(
                self.reconciliation_path(request.target_request_id), record
            )
        except FileExistsError:
            existing = self._read_reconciliation_for_status(
                request.target_request_id
            )
            if existing is None:
                raise BrokerTrustError(
                    "reconciliation record appeared without readable state"
                )
            expected = {
                "target_request_sha256": request.target_request_sha256,
                "target_marker_sha256": request.target_marker_sha256,
                "target_release_sha": request.target_release_sha,
                "readiness_receipt_sha256": request.readiness_receipt_sha256,
                "expected_credential_kind": request.expected_credential_kind,
                "workspace_binding_class": request.workspace_binding_class,
                "credential_expires_at": request.credential_expires_at,
            }
            if any(existing.get(key) != value for key, value in expected.items()):
                raise RequestIdConflictError(
                    "target request acquired a different reconciliation record"
                )
            self._validate_reconciliation_marker(existing)
            return existing, True
        self._validate_reconciliation_marker(record)
        return record, False

    def _read_terminal_for_status(self, request_id: str) -> dict[str, Any] | None:
        path = self.receipt_path(request_id)
        value = _read_optional_bounded_json(path)
        if value is None:
            return None
        return validate_terminal_receipt(value, expected_request_id=request_id)

    def _read_inflight_for_status(self, request_id: str) -> dict[str, Any] | None:
        path = self.inflight_path(request_id)
        value = _read_optional_bounded_json(path)
        if value is None:
            return None
        if value.get("schema") != INFLIGHT_SCHEMA or value.get("request_id") != request_id:
            raise BrokerTrustError("in-flight marker identity is invalid")
        _validate_stored_release_sha(value.get("release_sha"))
        _validate_stored_digest(value.get("request_sha256"))
        return value

    def query_status(
        self, raw_status_request: Mapping[str, Any], *, peer_uid: int
    ) -> dict[str, Any]:
        """Read-only status lookup: never executes, writes, or reconciles state."""
        if isinstance(peer_uid, bool) or not isinstance(peer_uid, int) or peer_uid not in self.config.allowed_peer_uids:
            raise PeerAuthorizationError("kernel peer uid is not authorized for privileged actions")
        status_request: PrivilegedActionStatusRequest = validate_status_request(raw_status_request)
        request_id = status_request.request_id
        installed_release_sha = self.config.release_root.name

        terminal = self._read_terminal_for_status(request_id)
        reconciliation = self._read_reconciliation_for_status(request_id)
        if terminal is not None and reconciliation is not None:
            raise BrokerTrustError(
                "request id has both terminal and reconciliation records"
            )
        if terminal is not None:
            return {
                "status": STATUS_TERMINAL,
                "request_id": request_id,
                "installed_release_sha": installed_release_sha,
                "receipt": terminal,
            }

        if reconciliation is not None:
            marker = self._validate_reconciliation_marker(reconciliation)
            return {
                "status": STATUS_RECONCILED_NOT_APPLIED,
                "request_id": request_id,
                "installed_release_sha": installed_release_sha,
                "marker_release_sha": marker.get("release_sha"),
                "reconciliation": reconciliation,
            }

        marker = self._read_inflight_for_status(request_id)
        if marker is not None:
            return {
                "status": STATUS_EFFECT_UNKNOWN,
                "request_id": request_id,
                "installed_release_sha": installed_release_sha,
                "marker_release_sha": marker.get("release_sha"),
            }

        return {
            "status": STATUS_NOT_FOUND,
            "request_id": request_id,
            "installed_release_sha": installed_release_sha,
        }


WIRE_RESPONSE_SCHEMA = "mastermind.executive_privileged_action_response.v1"
_MAX_REQUEST_BYTES = 64 * 1024
_LAUNCHD_SOCKET_NAME = "PrivilegedActions"
_BROKER_IDLE_TIMEOUT_SECONDS = 120


def get_peer_uid(peer_socket: socket.socket) -> int:
    """Return the kernel-authenticated Unix peer UID."""
    descriptor = peer_socket.fileno()
    if descriptor < 0:
        raise PeerAuthorizationError("peer socket is closed")
    if platform.system() == "Darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.getpeereid
        function.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint),
            ctypes.POINTER(ctypes.c_uint),
        ]
        function.restype = ctypes.c_int
        uid = ctypes.c_uint()
        gid = ctypes.c_uint()
        if function(descriptor, ctypes.byref(uid), ctypes.byref(gid)) != 0:
            raise PeerAuthorizationError("cannot resolve Unix peer credentials")
        return int(uid.value)
    if hasattr(socket, "SO_PEERCRED"):
        import struct
        raw = peer_socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", raw)
        return int(uid)
    getter = getattr(peer_socket, "getpeereid", None)
    if callable(getter):
        uid, _gid = getter()
        return int(uid)
    raise PeerAuthorizationError("Unix peer credentials are unavailable")


def activate_launchd_socket(name: str = _LAUNCHD_SOCKET_NAME) -> socket.socket:
    """Claim exactly one launchd-activated listener by its fixed socket key."""
    if platform.system() != "Darwin":
        raise BrokerTrustError("launchd socket activation is available only on macOS")
    if name != _LAUNCHD_SOCKET_NAME:
        raise BrokerTrustError("privileged launchd socket name is not reviewed")
    libc = ctypes.CDLL(None, use_errno=True)
    activate = libc.launch_activate_socket
    activate.argtypes = [
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
        ctypes.POINTER(ctypes.c_size_t),
    ]
    activate.restype = ctypes.c_int
    descriptors = ctypes.POINTER(ctypes.c_int)()
    count = ctypes.c_size_t()
    result = activate(name.encode("ascii"), ctypes.byref(descriptors), ctypes.byref(count))
    if result != 0:
        raise BrokerTrustError(f"launchd socket activation failed with errno {result}")
    try:
        values = [int(descriptors[index]) for index in range(int(count.value))]
    finally:
        libc.free.argtypes = [ctypes.c_void_p]
        libc.free.restype = None
        libc.free(descriptors)
    if len(values) != 1:
        for descriptor in values:
            os.close(descriptor)
        raise BrokerTrustError("privileged broker requires exactly one launchd socket")
    listener = socket.socket(fileno=values[0])
    listener.setblocking(True)
    return listener


def _wire_error(code: str, detail: str) -> dict[str, Any]:
    return {
        "schema": WIRE_RESPONSE_SCHEMA,
        "ok": False,
        "error": code,
        "detail": sanitize_external_text(detail, limit=300),
    }


def _wire_success(receipt: Mapping[str, Any], *, replayed: bool) -> dict[str, Any]:
    return {
        "schema": WIRE_RESPONSE_SCHEMA,
        "ok": True,
        "replayed": replayed,
        "receipt": dict(receipt),
    }


def _wire_status(projection: Mapping[str, Any]) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": WIRE_RESPONSE_SCHEMA,
        "ok": True,
        "query": True,
        "status": projection["status"],
        "request_id": projection["request_id"],
        "installed_release_sha": projection["installed_release_sha"],
    }
    if "receipt" in projection:
        value["receipt"] = dict(projection["receipt"])
    if "marker_release_sha" in projection:
        value["marker_release_sha"] = projection["marker_release_sha"]
    if "reconciliation" in projection:
        value["reconciliation"] = dict(projection["reconciliation"])
    return value


def _wire_reconciliation(
    reconciliation: Mapping[str, Any], *, replayed: bool
) -> dict[str, Any]:
    return {
        "schema": WIRE_RESPONSE_SCHEMA,
        "ok": True,
        "reconciled": True,
        "replayed": replayed,
        "reconciliation": dict(reconciliation),
    }


def _send_wire(connection: socket.socket, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    connection.sendall(payload)


def _read_request_frame(connection: socket.socket) -> Mapping[str, Any]:
    buffer = bytearray()
    while True:
        chunk = connection.recv(min(4096, _MAX_REQUEST_BYTES + 1 - len(buffer)))
        if not chunk:
            raise PrivilegedBrokerError("client closed before a complete request frame")
        buffer.extend(chunk)
        if len(buffer) > _MAX_REQUEST_BYTES:
            raise PrivilegedBrokerError("privileged request frame is too large")
        newline = buffer.find(b"\n")
        if newline >= 0:
            if newline != len(buffer) - 1:
                raise PrivilegedBrokerError("privileged protocol accepts exactly one JSON frame")
            break
    try:
        value = json.loads(bytes(buffer[:-1]).decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PrivilegedBrokerError("privileged request frame is invalid JSON") from exc
    if not isinstance(value, dict):
        raise PrivilegedBrokerError("privileged request frame must contain a mapping")
    return value


def serve_connection(
    broker: PrivilegedActionBroker,
    connection: socket.socket,
    *,
    peer_resolver: Callable[[socket.socket], int] = get_peer_uid,
) -> None:
    """Serve one request, checking the kernel peer before reading its body."""
    try:
        peer_uid = peer_resolver(connection)
        if peer_uid not in broker.config.allowed_peer_uids:
            raise PeerAuthorizationError("kernel peer uid is not authorized for privileged actions")
        raw = _read_request_frame(connection)
        if raw.get("schema") == STATUS_REQUEST_SCHEMA:
            projection = broker.query_status(raw, peer_uid=peer_uid)
            _send_wire(connection, _wire_status(projection))
        elif raw.get("schema") == RECONCILE_REQUEST_SCHEMA:
            reconciliation, replayed = broker.reconcile_not_applied(
                raw, peer_uid=peer_uid
            )
            _send_wire(
                connection,
                _wire_reconciliation(reconciliation, replayed=replayed),
            )
        else:
            receipt, replayed = broker._handle_outcome(raw, peer_uid=peer_uid)
            _send_wire(connection, _wire_success(receipt, replayed=replayed))
    except PeerAuthorizationError:
        # Do not parse or reflect an unauthorized peer's body.
        _send_wire(connection, _wire_error("PEER_UNAUTHORIZED", "kernel peer uid is not authorized"))
    except EffectUnknownError as exc:
        _send_wire(connection, _wire_error("EFFECT_UNKNOWN", str(exc)))
    except ReconciledNotAppliedError as exc:
        _send_wire(connection, _wire_error("RECONCILED_NOT_APPLIED", str(exc)))
    except RequestIdConflictError as exc:
        _send_wire(connection, _wire_error("REQUEST_ID_CONFLICT", str(exc)))
    except (PrivilegedBrokerError, ValueError) as exc:
        _send_wire(connection, _wire_error("REFUSED", str(exc)))


def run_broker(
    config: PrivilegedBrokerConfig,
    *,
    activated_socket: socket.socket | None = None,
) -> None:
    broker = PrivilegedActionBroker(config)
    listener = activated_socket if activated_socket is not None else activate_launchd_socket()
    listener.settimeout(_BROKER_IDLE_TIMEOUT_SECONDS)
    while True:
        try:
            connection, _address = listener.accept()
        except TimeoutError:
            return
        with connection:
            connection.settimeout(30)
            try:
                serve_connection(broker, connection)
            except OSError:
                # A disconnected client cannot pin the privileged process resident.
                continue


__all__ = [
    "BROKER_CONFIG_SCHEMA",
    "BrokerTrustError",
    "EffectUnknownError",
    "PeerAuthorizationError",
    "PrivilegedActionBroker",
    "PrivilegedBrokerConfig",
    "PrivilegedBrokerError",
    "RECEIPT_SCHEMA",
    "RECONCILE_REQUEST_SCHEMA",
    "RECONCILIATION_SCHEMA",
    "ReconciledNotAppliedError",
    "RequestIdConflictError",
    "STATUS_EFFECT_UNKNOWN",
    "STATUS_NOT_FOUND",
    "STATUS_RECONCILED_NOT_APPLIED",
    "STATUS_TERMINAL",
    "WIRE_RESPONSE_SCHEMA",
    "activate_launchd_socket",
    "get_peer_uid",
    "run_broker",
    "serve_connection",
    "validate_reconcile_not_applied_request",
    "validate_reconciliation_pair",
    "validate_reconciliation_record",
    "validate_terminal_receipt",
    "verify_production_trust",
]
