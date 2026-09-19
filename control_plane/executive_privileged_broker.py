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
    STATUS_REQUEST_SCHEMA,
    build_argv,
    canonical_request_bytes,
    validate_request,
    validate_status_request,
)


BROKER_CONFIG_SCHEMA = "mastermind.executive_privileged_broker_config.v1"
RECEIPT_SCHEMA = "mastermind.executive_privileged_action_receipt.v1"
INFLIGHT_SCHEMA = "mastermind.executive_privileged_action_inflight.v1"
STATUS_TERMINAL = "TERMINAL"
STATUS_EFFECT_UNKNOWN = "EFFECT_UNKNOWN"
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
    ) -> None:
        self.config = config
        self.receipt_root = Path(config.receipt_root)
        self.inflight_root = self.receipt_root / "inflight"
        self._executor = executor
        if require_root and os.geteuid() != 0:
            raise BrokerTrustError("privileged broker must run as root")
        trust_validator(config)
        self.receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.inflight_root.mkdir(exist_ok=True, mode=0o700)
        if require_root:
            for path, label in (
                (self.receipt_root, "privileged receipt root"),
                (self.inflight_root, "privileged in-flight root"),
            ):
                info = path.lstat()
                if info.st_uid != 0 or info.st_gid != 0 or not stat.S_ISDIR(info.st_mode):
                    raise BrokerTrustError(f"{label} ownership drifted")
                os.chmod(path, 0o700)

    def receipt_path(self, request_id: str) -> Path:
        return self.receipt_root / f"{request_id}.json"

    def inflight_path(self, request_id: str) -> Path:
        return self.inflight_root / f"{request_id}.json"

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
        existing = self._existing_terminal(request, digest)
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
        if terminal is not None:
            return {
                "status": STATUS_TERMINAL,
                "request_id": request_id,
                "installed_release_sha": installed_release_sha,
                "receipt": terminal,
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
    return value


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
        else:
            receipt, replayed = broker._handle_outcome(raw, peer_uid=peer_uid)
            _send_wire(connection, _wire_success(receipt, replayed=replayed))
    except PeerAuthorizationError:
        # Do not parse or reflect an unauthorized peer's body.
        _send_wire(connection, _wire_error("PEER_UNAUTHORIZED", "kernel peer uid is not authorized"))
    except EffectUnknownError as exc:
        _send_wire(connection, _wire_error("EFFECT_UNKNOWN", str(exc)))
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
    "RequestIdConflictError",
    "STATUS_EFFECT_UNKNOWN",
    "STATUS_NOT_FOUND",
    "STATUS_TERMINAL",
    "WIRE_RESPONSE_SCHEMA",
    "activate_launchd_socket",
    "get_peer_uid",
    "run_broker",
    "serve_connection",
    "validate_terminal_receipt",
    "verify_production_trust",
]
