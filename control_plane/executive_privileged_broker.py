"""Receipt-gated root executor for a closed Executive OS action catalog.

The broker is intentionally not a scheduler, queue, or generic sudo service.
It accepts a validated action request, authenticates the kernel peer UID, and
runs one exact argv from :mod:`control_plane.executive_privileged_action`.
Every effect is fenced by an fsync'd in-flight marker and a durable terminal
receipt so transport loss can never be interpreted as proof of no effect.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from common.redaction import sanitize_external_text
from control_plane.executive_privileged_action import (
    PrivilegedActionRequest,
    build_argv,
    canonical_request_bytes,
    validate_request,
)


BROKER_CONFIG_SCHEMA = "mastermind.executive_privileged_broker_config.v1"
RECEIPT_SCHEMA = "mastermind.executive_privileged_action_receipt.v1"
INFLIGHT_SCHEMA = "mastermind.executive_privileged_action_inflight.v1"
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


def _default_executor(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], timeout: int
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(argv),
        cwd=str(cwd),
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        shell=False,
        close_fds=True,
    )


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
    for relative in (
        "ops/executive_os/service-control.sh",
        "ops/executive_os/provision-worker-auth.sh",
    ):
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
        self._executor = executor
        if require_root and os.geteuid() != 0:
            raise BrokerTrustError("privileged broker must run as root")
        trust_validator(config)
        self.receipt_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if require_root:
            info = self.receipt_root.lstat()
            if info.st_uid != 0 or info.st_gid != 0 or not stat.S_ISDIR(info.st_mode):
                raise BrokerTrustError("privileged receipt root ownership drifted")
            os.chmod(self.receipt_root, 0o700)

    def receipt_path(self, request_id: str) -> Path:
        return self.receipt_root / f"{request_id}.json"

    def inflight_path(self, request_id: str) -> Path:
        return self.receipt_root / f"{request_id}.inflight.json"

    @staticmethod
    def _request_digest(request: PrivilegedActionRequest) -> str:
        return hashlib.sha256(canonical_request_bytes(request)).hexdigest()

    def _existing_terminal(self, request: PrivilegedActionRequest, digest: str) -> dict[str, Any] | None:
        path = self.receipt_path(request.request_id)
        if not path.exists():
            return None
        value = _read_bounded_json(path)
        if value.get("schema") != RECEIPT_SCHEMA or value.get("request_id") != request.request_id:
            raise BrokerTrustError("terminal receipt identity is invalid")
        if value.get("request_sha256") != digest:
            raise RequestIdConflictError("request id already has a different terminal request")
        return value

    def _check_inflight(self, request: PrivilegedActionRequest, digest: str) -> None:
        path = self.inflight_path(request.request_id)
        if not path.exists():
            return
        value = _read_bounded_json(path)
        if value.get("schema") != INFLIGHT_SCHEMA or value.get("request_id") != request.request_id:
            raise BrokerTrustError("in-flight marker identity is invalid")
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
        _fsync_directory(self.receipt_root)

    def handle(self, raw_request: Mapping[str, Any], *, peer_uid: int) -> dict[str, Any]:
        if isinstance(peer_uid, bool) or not isinstance(peer_uid, int) or peer_uid not in self.config.allowed_peer_uids:
            raise PeerAuthorizationError("kernel peer uid is not authorized for privileged actions")
        request = validate_request(raw_request)
        digest = self._request_digest(request)
        existing = self._existing_terminal(request, digest)
        if existing is not None:
            return existing
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
        except subprocess.TimeoutExpired as exc:
            raise EffectUnknownError("privileged child timed out after spawn; effect is unknown") from exc
        except OSError as exc:
            # Popen-level OS errors occur before a child executable can start.
            try:
                self._remove_inflight(request.request_id)
            except OSError as cleanup_exc:
                raise EffectUnknownError("executor failed and in-flight cleanup failed") from cleanup_exc
            raise PrivilegedBrokerError("privileged child could not be started") from exc

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
        return receipt


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
    "verify_production_trust",
]
