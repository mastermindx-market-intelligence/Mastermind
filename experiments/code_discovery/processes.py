"""Host-only lifecycle controls for disposable exact-pinned Zoekt processes."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import os
import selectors
import shutil
import signal
import socket
import stat
import subprocess
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from .discovery_contract import RepositoryIndexStatus
from .index_manifest import IndexManifest, RepositorySpec


ZOEKT_SOURCE_COMMIT: Final = "5f833dde1bc4b1a8f99007617b4b721e44506c4f"
_MAX_PROCESS_OUTPUT_BYTES: Final = 64 * 1024
_MAX_STARTUP_ATTEMPTS: Final = 3
_STARTUP_STABILITY_SECONDS: Final = 0.20
_IDENTITY_PROBE_TIMEOUT_SECONDS: Final = 0.25
_MAX_IDENTITY_RESPONSE_BYTES: Final = 64 * 1024
_CLOSED_ENV: Final = {"LANG": "C", "LC_ALL": "C"}
_HOST_ROLES: Final = frozenset({"zoekt-git-index", "zoekt-webserver"})
_STARTUP_CATEGORIES: Final = frozenset(
    {
        "STARTED",
        "BIND_COLLISION",
        "PROCESS_EXITED",
        "OUTPUT_OVERFLOW",
        "START_TIMEOUT",
        "START_ERROR",
    }
)
_ENDPOINT_DISPOSITIONS: Final = frozenset(
    {"BOUND", "RELEASED", "EXTERNAL_OCCUPIED", "UNEXPECTED_OPEN"}
)
_BIND_COLLISION_MARKERS: Final = (
    b"address already in use",
    b"eaddrinuse",
)


class ExecutableVerificationError(ValueError):
    """A purported pinned binary is not safe to invoke."""


class StaleShardGenerationError(RuntimeError):
    """A prior disposable generation would be merged without explicit discard."""


class ProcessOutputOverflow(RuntimeError):
    """A child emitted more diagnostics than the disposable runner permits."""


class ZoektProcessExited(RuntimeError):
    """The local Zoekt process died before or during the requested operation."""


class ZoektProcessTimeout(RuntimeError):
    """A disposable Zoekt child did not finish or bind within the bounded window."""


class ZoektProcessError(RuntimeError):
    """A checked Zoekt subprocess exited unsuccessfully."""


@dataclass(frozen=True)
class ExecutableSpec:
    """Exact host-approved binary for one of the two closed Zoekt roles."""

    path: Path
    role: str
    sha256: str
    source_commit: str

    def verify(self) -> None:
        """Check the binary before and after every invocation."""

        if self.role not in _HOST_ROLES:
            raise ExecutableVerificationError("executable role is not a closed Zoekt role")
        if not self.path.is_absolute():
            raise ExecutableVerificationError("executable path must be absolute")
        if self.source_commit != ZOEKT_SOURCE_COMMIT:
            raise ExecutableVerificationError(
                "executable source_commit does not equal pinned Zoekt source"
            )
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ExecutableVerificationError("executable sha256 must be lowercase hex")
        try:
            metadata = self.path.lstat()
        except OSError as error:
            raise ExecutableVerificationError("executable does not exist") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ExecutableVerificationError("executable must not be a symlink")
        if not stat.S_ISREG(metadata.st_mode):
            raise ExecutableVerificationError("executable must be a regular file")
        if metadata.st_mode & 0o022:
            raise ExecutableVerificationError(
                "executable must not be group/world writable"
            )
        if not metadata.st_mode & stat.S_IXUSR:
            raise ExecutableVerificationError("executable must be owner executable")
        observed = _sha256_file(self.path)
        if observed != self.sha256:
            raise ExecutableVerificationError("executable digest mismatch")


@dataclass(frozen=True)
class LoopbackEndpoint:
    """A numeric loopback endpoint, with no ambient host or transport choice."""

    host: str
    port: int

    def __post_init__(self) -> None:
        try:
            address = ipaddress.ip_address(self.host)
        except ValueError as error:
            raise ValueError("listener must use a numeric loopback address") from error
        if not address.is_loopback:
            raise ValueError("listener must use a loopback address")
        if type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ValueError("listener port must be in 1..65535")

    @property
    def authority(self) -> str:
        if ":" in self.host:
            return f"[{self.host}]:{self.port}"
        return f"{self.host}:{self.port}"

    @property
    def url(self) -> str:
        return f"http://{self.authority}"


@dataclass(frozen=True)
class StartupAttemptReceipt:
    """Closed, non-echoing evidence for one host-owned startup attempt."""

    attempt: int
    category: str
    return_code: int | None
    stdout_bytes: int
    stderr_bytes: int
    diagnostics_truncated: bool
    diagnostics_sha256: str
    endpoint_disposition: str
    cleanup_complete: bool

    def __post_init__(self) -> None:
        if type(self.attempt) is not int or not 1 <= self.attempt <= _MAX_STARTUP_ATTEMPTS:
            raise ValueError("startup attempt is outside the closed range")
        if self.category not in _STARTUP_CATEGORIES:
            raise ValueError("startup category is not closed")
        if self.return_code is not None and type(self.return_code) is not int:
            raise ValueError("startup return_code must be an integer or null")
        if type(self.stdout_bytes) is not int or self.stdout_bytes < 0:
            raise ValueError("stdout_bytes must be a non-negative integer")
        if type(self.stderr_bytes) is not int or self.stderr_bytes < 0:
            raise ValueError("stderr_bytes must be a non-negative integer")
        if type(self.diagnostics_truncated) is not bool:
            raise ValueError("diagnostics_truncated must be a boolean")
        if (
            len(self.diagnostics_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.diagnostics_sha256)
        ):
            raise ValueError("diagnostics_sha256 must be lowercase SHA-256")
        if self.endpoint_disposition not in _ENDPOINT_DISPOSITIONS:
            raise ValueError("endpoint disposition is not closed")
        if type(self.cleanup_complete) is not bool:
            raise ValueError("cleanup_complete must be a boolean")


@dataclass(frozen=True)
class _CaptureSnapshot:
    stdout: bytes
    stderr: bytes
    stdout_bytes: int
    stderr_bytes: int
    truncated: bool
    sha256: str


@dataclass(frozen=True)
class _RepositoryIdentity:
    """One exact pinned-Zoekt repository identity for this disposable generation."""

    repository_name: str
    metadata: dict[str, str]
    ref_label: str
    commit_sha: str


class _ProcessCapture:
    """Retain bounded private diagnostics while stopping a noisy server."""

    def __init__(self, process: subprocess.Popen[bytes], maximum: int) -> None:
        self._process = process
        self._maximum = maximum
        self._buffers = {"stdout": bytearray(), "stderr": bytearray()}
        self._counts = {"stdout": 0, "stderr": 0}
        self._stored = 0
        self._overflow = False
        self._lock = threading.Lock()
        self._threads = tuple(
            threading.Thread(
                target=self._drain,
                args=(label, stream),
                daemon=True,
            )
            for label, stream in (
                ("stdout", process.stdout),
                ("stderr", process.stderr),
            )
            if stream is not None
        )
        for thread in self._threads:
            thread.start()

    def _drain(self, label: str, stream: object) -> None:
        assert hasattr(stream, "read")
        reader = getattr(stream, "read1", stream.read)
        while True:
            chunk = reader(8192)
            if not chunk:
                return
            overflow_now = False
            with self._lock:
                self._counts[label] += len(chunk)
                room = max(0, self._maximum - self._stored)
                retained = chunk[:room]
                if retained:
                    self._buffers[label].extend(retained)
                    self._stored += len(retained)
                if len(retained) != len(chunk):
                    self._overflow = True
                    overflow_now = True
            if overflow_now and self._process.poll() is None:
                _signal_process_group(self._process.pid, signal.SIGTERM)

    def raise_if_overflow(self) -> None:
        with self._lock:
            if self._overflow:
                raise ProcessOutputOverflow("Zoekt process exceeded bounded diagnostics")

    def snapshot(self) -> _CaptureSnapshot:
        with self._lock:
            stdout = bytes(self._buffers["stdout"])
            stderr = bytes(self._buffers["stderr"])
            stdout_bytes = self._counts["stdout"]
            stderr_bytes = self._counts["stderr"]
            truncated = self._overflow
        material = b"stdout\0" + stdout + b"\0stderr\0" + stderr
        return _CaptureSnapshot(
            stdout=stdout,
            stderr=stderr,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            truncated=truncated,
            sha256=hashlib.sha256(material).hexdigest(),
        )

    def join(self) -> None:
        for thread in self._threads:
            thread.join(timeout=1)


class ZoektProcessSet:
    """One disposable host-owned index generation and optional loopback server."""

    def __init__(
        self,
        *,
        indexer: ExecutableSpec,
        webserver: ExecutableSpec,
        shard_root: Path,
        log_root: Path,
        startup_timeout_seconds: float = 10.0,
    ) -> None:
        if startup_timeout_seconds <= 0:
            raise ValueError("startup_timeout_seconds must be positive")
        self.indexer = indexer
        self.webserver = webserver
        self.indexer.verify()
        self.webserver.verify()
        if self.indexer.role != "zoekt-git-index":
            raise ExecutableVerificationError("indexer must use role zoekt-git-index")
        if self.webserver.role != "zoekt-webserver":
            raise ExecutableVerificationError("webserver must use role zoekt-webserver")
        self.shard_root = _prepare_external_directory(Path(shard_root), "shard_root")
        self.log_root = _prepare_external_directory(Path(log_root), "log_root")
        self.startup_timeout_seconds = startup_timeout_seconds
        self._statuses: tuple[RepositoryIndexStatus, ...] = ()
        self._repository_identities: tuple[_RepositoryIdentity, ...] = ()
        self._search_process: subprocess.Popen[bytes] | None = None
        self._search_capture: _ProcessCapture | None = None
        self._endpoint: LoopbackEndpoint | None = None
        self._startup_receipts: list[StartupAttemptReceipt] = []
        self._closed = False
        self._generation_id = hashlib.sha256(
            os.urandom(32) + os.fspath(self.shard_root).encode("utf-8")
        ).hexdigest()

    @property
    def startup_attempt_receipts(self) -> tuple[StartupAttemptReceipt, ...]:
        """Return immutable, non-echoing startup evidence in attempt order."""

        return tuple(self._startup_receipts)

    def build_indexes(
        self, manifest: IndexManifest
    ) -> tuple[RepositoryIndexStatus, ...]:
        """Index each source row independently into an empty logical namespace."""

        self._require_open()
        _assert_external_to_sources(self.shard_root, self.log_root, manifest.repositories)
        statuses: list[RepositoryIndexStatus] = []
        identities: list[_RepositoryIdentity] = []
        for spec in manifest.repositories:
            generation = self.shard_root / spec.shard_namespace
            if generation.exists():
                raise StaleShardGenerationError(
                    f"stale shard generation requires host discard: {generation}"
                )
            generation.mkdir(mode=0o700)
            metadata_path = generation / "z0-index-meta.json"
            metadata = _index_identity_metadata(spec, self._generation_id)
            _write_json(
                metadata_path,
                {"Name": spec.repository_name, "Metadata": metadata},
            )
            self.indexer.verify()
            argv = _indexer_argv(self.indexer, spec, generation, metadata_path)
            _run_bounded(
                self.indexer,
                argv,
                cwd=spec.source_snapshot_root,
                timeout_seconds=self.startup_timeout_seconds,
            )
            self.indexer.verify()
            now = datetime.now(UTC)
            status = RepositoryIndexStatus(
                repository_id=spec.repository_id,
                ref_label=spec.ref_label,
                indexed_commit_sha=spec.commit_sha,
                source_tree_digest=spec.source_tree_digest,
                shard_namespace=spec.shard_namespace,
                health="healthy",
                coverage="covered",
                generated_at=now,
                observed_at=now,
                freshness_seconds=0.0,
            )
            _write_json(generation / "z0-index-receipt.json", _receipt_payload(status))
            _verify_receipt(generation / "z0-index-receipt.json", status)
            statuses.append(status)
            identities.append(
                _RepositoryIdentity(
                    repository_name=spec.repository_name,
                    metadata=metadata,
                    ref_label=spec.ref_label,
                    commit_sha=spec.commit_sha,
                )
            )
        self._statuses = tuple(statuses)
        self._repository_identities = tuple(identities)
        return self._statuses

    def start_search(self) -> LoopbackEndpoint:
        """Start the exact webserver through bounded host-owned local attempts."""

        self._require_open()
        if self._search_process is not None:
            self.assert_search_alive()
            raise ZoektProcessError("search process is already running")
        if not self._statuses:
            raise ZoektProcessError("build_indexes must complete before start_search")
        for status in self._statuses:
            assert status.shard_namespace is not None
            _verify_receipt(
                self.shard_root / status.shard_namespace / "z0-index-receipt.json",
                status,
            )
        self.webserver.verify()

        for attempt in range(1, _MAX_STARTUP_ATTEMPTS + 1):
            endpoint = LoopbackEndpoint("127.0.0.1", _reserve_loopback_port())
            endpoint_was_open_before_spawn = _loopback_is_open(endpoint)
            attempt_log_root = self.log_root / f"startup-{attempt}"
            if attempt_log_root.exists():
                self._terminal_start_failure()
                raise ZoektProcessError("startup attempt log root already exists")
            attempt_log_root.mkdir(mode=0o700)
            argv = _webserver_argv(
                self.webserver, endpoint, self.shard_root, attempt_log_root
            )
            try:
                process = _spawn_exact(
                    self.webserver,
                    argv,
                    cwd=self.shard_root,
                )
            except Exception:
                cleanup_complete = _remove_attempt_log_root(attempt_log_root)
                snapshot = _empty_capture_snapshot()
                self._startup_receipts.append(
                    _startup_receipt(
                        attempt=attempt,
                        category="START_ERROR",
                        return_code=None,
                        snapshot=snapshot,
                        endpoint_disposition=(
                            "UNEXPECTED_OPEN" if _loopback_is_open(endpoint) else "RELEASED"
                        ),
                        cleanup_complete=cleanup_complete,
                    )
                )
                self._terminal_start_failure()
                raise

            capture = _ProcessCapture(process, _MAX_PROCESS_OUTPUT_BYTES)
            try:
                self.webserver.verify()
                _wait_for_loopback(
                    process,
                    capture,
                    endpoint,
                    self.startup_timeout_seconds,
                    endpoint_was_open_before_spawn=endpoint_was_open_before_spawn,
                    expected_identities=self._repository_identities,
                )
                self.webserver.verify()
                capture.raise_if_overflow()
                if process.poll() is not None:
                    raise ZoektProcessExited(
                        f"ZOEKT_PROCESS_EXITED: zoekt-webserver exited with {process.returncode}"
                    )
            except ProcessOutputOverflow:
                snapshot, return_code, endpoint_open, cleanup_complete = (
                    _cleanup_startup_attempt(
                        process, capture, endpoint, attempt_log_root
                    )
                )
                self._startup_receipts.append(
                    _startup_receipt(
                        attempt=attempt,
                        category="OUTPUT_OVERFLOW",
                        return_code=return_code,
                        snapshot=snapshot,
                        endpoint_disposition=(
                            "UNEXPECTED_OPEN" if endpoint_open else "RELEASED"
                        ),
                        cleanup_complete=cleanup_complete and not endpoint_open,
                    )
                )
                self._terminal_start_failure()
                raise
            except ZoektProcessExited as error:
                snapshot, return_code, endpoint_open, cleanup_complete = (
                    _cleanup_startup_attempt(
                        process, capture, endpoint, attempt_log_root
                    )
                )
                bind_collision = _is_bind_collision(
                    snapshot=snapshot,
                    return_code=return_code,
                    endpoint_open=endpoint_open,
                )
                self._startup_receipts.append(
                    _startup_receipt(
                        attempt=attempt,
                        category=("BIND_COLLISION" if bind_collision else "PROCESS_EXITED"),
                        return_code=return_code,
                        snapshot=snapshot,
                        endpoint_disposition=(
                            "EXTERNAL_OCCUPIED"
                            if bind_collision
                            else ("UNEXPECTED_OPEN" if endpoint_open else "RELEASED")
                        ),
                        cleanup_complete=cleanup_complete,
                    )
                )
                if bind_collision and cleanup_complete and attempt < _MAX_STARTUP_ATTEMPTS:
                    continue
                self._terminal_start_failure()
                if bind_collision:
                    raise ZoektProcessExited(
                        "ZOEKT_PROCESS_EXITED: loopback bind collision attempts exhausted"
                    ) from error
                raise
            except ZoektProcessTimeout:
                snapshot, return_code, endpoint_open, cleanup_complete = (
                    _cleanup_startup_attempt(
                        process, capture, endpoint, attempt_log_root
                    )
                )
                self._startup_receipts.append(
                    _startup_receipt(
                        attempt=attempt,
                        category="START_TIMEOUT",
                        return_code=return_code,
                        snapshot=snapshot,
                        endpoint_disposition=(
                            "UNEXPECTED_OPEN" if endpoint_open else "RELEASED"
                        ),
                        cleanup_complete=cleanup_complete and not endpoint_open,
                    )
                )
                self._terminal_start_failure()
                raise
            except Exception:
                snapshot, return_code, endpoint_open, cleanup_complete = (
                    _cleanup_startup_attempt(
                        process, capture, endpoint, attempt_log_root
                    )
                )
                self._startup_receipts.append(
                    _startup_receipt(
                        attempt=attempt,
                        category="START_ERROR",
                        return_code=return_code,
                        snapshot=snapshot,
                        endpoint_disposition=(
                            "UNEXPECTED_OPEN" if endpoint_open else "RELEASED"
                        ),
                        cleanup_complete=cleanup_complete and not endpoint_open,
                    )
                )
                self._terminal_start_failure()
                raise

            snapshot = capture.snapshot()
            self._startup_receipts.append(
                _startup_receipt(
                    attempt=attempt,
                    category="STARTED",
                    return_code=None,
                    snapshot=snapshot,
                    endpoint_disposition="BOUND",
                    cleanup_complete=False,
                )
            )
            self._search_process = process
            self._search_capture = capture
            self._endpoint = endpoint
            return endpoint

        self._terminal_start_failure()
        raise ZoektProcessExited("ZOEKT_PROCESS_EXITED: no startup attempt succeeded")

    def assert_search_alive(self) -> None:
        """Raise a typed failure if the local disposable server no longer exists."""

        if self._search_process is None:
            raise ZoektProcessExited("ZOEKT_PROCESS_EXITED: search process was not started")
        if self._search_capture is not None:
            self._search_capture.raise_if_overflow()
        code = self._search_process.poll()
        if code is not None:
            raise ZoektProcessExited(
                f"ZOEKT_PROCESS_EXITED: zoekt-webserver exited with {code}"
            )
        if self._endpoint is None or not _loopback_has_exact_identities(
            self._endpoint, self._repository_identities
        ):
            raise ZoektProcessExited(
                "ZOEKT_PROCESS_EXITED: zoekt-webserver identity probe failed"
            )

    def close(self) -> None:
        """Terminate the whole generation group and discard its dedicated scratch roots."""

        if self._closed:
            return
        process, capture = self._search_process, self._search_capture
        self._search_process = None
        self._search_capture = None
        endpoint, self._endpoint = self._endpoint, None
        try:
            if process is not None:
                _terminate_process_group(process, timeout_seconds=2.0)
            if capture is not None:
                capture.join()
            if endpoint is not None and _loopback_is_open(endpoint):
                raise ZoektProcessError("Zoekt listener remained open after process cleanup")
        finally:
            self._discard_scratch()
            self._closed = True

    def _terminal_start_failure(self) -> None:
        try:
            self._discard_scratch()
        finally:
            self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise ZoektProcessError("disposable Zoekt generation has already been closed")

    def _discard_scratch(self) -> None:
        for root in (self.shard_root, self.log_root):
            try:
                if root.exists():
                    shutil.rmtree(root)
            except OSError as error:
                raise ZoektProcessError(
                    f"unable to discard disposable Zoekt scratch root: {root}"
                ) from error


def _startup_receipt(
    *,
    attempt: int,
    category: str,
    return_code: int | None,
    snapshot: _CaptureSnapshot,
    endpoint_disposition: str,
    cleanup_complete: bool,
) -> StartupAttemptReceipt:
    return StartupAttemptReceipt(
        attempt=attempt,
        category=category,
        return_code=return_code,
        stdout_bytes=snapshot.stdout_bytes,
        stderr_bytes=snapshot.stderr_bytes,
        diagnostics_truncated=snapshot.truncated,
        diagnostics_sha256=snapshot.sha256,
        endpoint_disposition=endpoint_disposition,
        cleanup_complete=cleanup_complete,
    )


def _empty_capture_snapshot() -> _CaptureSnapshot:
    material = b"stdout\0\0stderr\0"
    return _CaptureSnapshot(
        stdout=b"",
        stderr=b"",
        stdout_bytes=0,
        stderr_bytes=0,
        truncated=False,
        sha256=hashlib.sha256(material).hexdigest(),
    )


def _cleanup_startup_attempt(
    process: subprocess.Popen[bytes],
    capture: _ProcessCapture,
    endpoint: LoopbackEndpoint,
    attempt_log_root: Path,
) -> tuple[_CaptureSnapshot, int | None, bool, bool]:
    cleanup_error: Exception | None = None
    try:
        _terminate_process_group(process, timeout_seconds=2.0)
    except Exception as error:
        cleanup_error = error
    capture.join()
    snapshot = capture.snapshot()
    return_code = process.poll()
    endpoint_open = _loopback_is_open(endpoint)
    logs_removed = _remove_attempt_log_root(attempt_log_root)
    group_dead = not _process_group_is_alive(process.pid)
    cleanup_complete = cleanup_error is None and logs_removed and group_dead
    if cleanup_error is not None:
        raise ZoektProcessError("startup process-group cleanup failed") from cleanup_error
    return snapshot, return_code, endpoint_open, cleanup_complete


def _remove_attempt_log_root(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return True
    if path.is_symlink():
        path.unlink(missing_ok=True)
        return False
    try:
        shutil.rmtree(path)
    except OSError:
        return False
    return not path.exists()


def _snapshot_has_bind_collision(snapshot: _CaptureSnapshot) -> bool:
    if snapshot.truncated:
        return False
    diagnostics = (snapshot.stdout + b"\n" + snapshot.stderr).lower()
    return any(marker in diagnostics for marker in _BIND_COLLISION_MARKERS)


def _is_bind_collision(
    *, snapshot: _CaptureSnapshot, return_code: int | None, endpoint_open: bool
) -> bool:
    """Classify only a bounded diagnostic plus an independently occupied endpoint."""

    return (
        return_code not in (None, 0)
        and endpoint_open
        and _snapshot_has_bind_collision(snapshot)
    )


def _indexer_argv(
    executable: ExecutableSpec,
    spec: RepositorySpec,
    generation: Path,
    metadata_path: Path,
) -> tuple[str, ...]:
    """Frozen argv for zoekt-git-index at the exact Z0 upstream source pin."""

    return (
        os.fspath(executable.path),
        f"--index={generation}",
        f"--branches={spec.ref_label}",
        "--prefix=refs/heads/",
        "--incremental=false",
        "--submodules=false",
        f"--meta={metadata_path}",
        os.fspath(spec.source_snapshot_root),
    )


def _webserver_argv(
    executable: ExecutableSpec,
    endpoint: LoopbackEndpoint,
    shard_root: Path,
    log_root: Path,
) -> tuple[str, ...]:
    """Frozen argv for zoekt-webserver with every optional network surface off."""

    return (
        os.fspath(executable.path),
        f"--listen={endpoint.authority}",
        f"--index={shard_root}",
        f"--log_dir={log_root}",
        "--html=true",
        "--rpc=true",
        "--indexserver_proxy=false",
        "--pprof=false",
    )


def _run_bounded(
    executable: ExecutableSpec,
    argv: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
) -> tuple[bytes, bytes]:
    process = _spawn_exact(executable, argv, cwd=cwd)
    stdout, stderr = _collect_bounded_output(
        process, maximum=_MAX_PROCESS_OUTPUT_BYTES, timeout_seconds=timeout_seconds
    )
    if process.returncode:
        raise ZoektProcessError(
            f"Zoekt command exited {process.returncode}: {_diagnostic(stderr or stdout)!r}"
        )
    return stdout, stderr


def _spawn_exact(
    executable: ExecutableSpec, argv: Sequence[str], *, cwd: Path
) -> subprocess.Popen[bytes]:
    executable.verify()
    if not argv or argv[0] != os.fspath(executable.path):
        raise ZoektProcessError("closed Zoekt role received an unbound argv template")
    if not cwd.is_absolute() or cwd.is_symlink() or not cwd.is_dir():
        raise ZoektProcessError("closed Zoekt role requires a real absolute working directory")
    return subprocess.Popen(
        list(argv),
        cwd=os.fspath(cwd),
        env=dict(_CLOSED_ENV),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        start_new_session=True,
    )


def _collect_bounded_output(
    process: subprocess.Popen[bytes], *, maximum: int, timeout_seconds: float
) -> tuple[bytes, bytes]:
    assert process.stdout is not None
    assert process.stderr is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    overflow = False
    deadline = time.monotonic() + timeout_seconds
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_process_group(process, timeout_seconds=1.0)
                raise ZoektProcessTimeout("Zoekt command exceeded bounded timeout")
            events = selector.select(timeout=remaining)
            if not events:
                continue
            for key, _ in events:
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffer = buffers[key.data]
                if len(buffer) + len(chunk) > maximum:
                    overflow = True
                    if process.poll() is None:
                        _signal_process_group(process.pid, signal.SIGTERM)
                else:
                    buffer.extend(chunk)
        process.wait(timeout=1)
    finally:
        selector.close()
    if overflow:
        raise ProcessOutputOverflow("Zoekt command exceeded bounded diagnostics")
    return bytes(buffers["stdout"]), bytes(buffers["stderr"])


def _wait_for_loopback(
    process: subprocess.Popen[bytes],
    capture: _ProcessCapture,
    endpoint: LoopbackEndpoint,
    timeout_seconds: float,
    *,
    endpoint_was_open_before_spawn: bool,
    expected_identities: Sequence[_RepositoryIdentity],
) -> None:
    deadline = time.monotonic() + timeout_seconds
    stable_since: float | None = None
    while time.monotonic() < deadline:
        capture.raise_if_overflow()
        if process.poll() is not None:
            raise ZoektProcessExited(
                f"ZOEKT_PROCESS_EXITED: zoekt-webserver exited with {process.returncode}"
            )
        snapshot = capture.snapshot()
        contested = endpoint_was_open_before_spawn or _snapshot_has_bind_collision(snapshot)
        reachable = _loopback_has_exact_identities(endpoint, expected_identities)
        now = time.monotonic()
        if reachable and not contested:
            if stable_since is None:
                stable_since = now
            elif now - stable_since >= _STARTUP_STABILITY_SECONDS:
                return
        else:
            stable_since = None
        time.sleep(0.02)
    raise ZoektProcessTimeout(
        "zoekt-webserver did not establish an uncontested loopback listener before timeout"
    )


def _signal_process_group(group_id: int, sig: signal.Signals) -> None:
    try:
        os.killpg(group_id, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _process_group_is_alive(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(
    process: subprocess.Popen[bytes], *, timeout_seconds: float
) -> None:
    """Terminate and verify the fresh-session process group, even if its leader exited."""

    group_id = process.pid
    for sig in (signal.SIGTERM, signal.SIGKILL):
        _signal_process_group(group_id, sig)
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            process.poll()
            if not _process_group_is_alive(group_id):
                try:
                    process.wait(timeout=0.1)
                except (subprocess.TimeoutExpired, ChildProcessError):
                    pass
                return
            time.sleep(0.02)
    try:
        process.wait(timeout=timeout_seconds)
    except (subprocess.TimeoutExpired, ChildProcessError):
        pass
    if _process_group_is_alive(group_id):
        raise ZoektProcessError("Zoekt process group survived forced cleanup")


def _loopback_is_open(endpoint: LoopbackEndpoint) -> bool:
    try:
        with socket.create_connection((endpoint.host, endpoint.port), timeout=0.1):
            return True
    except OSError:
        return False


def _index_identity_metadata(spec: RepositorySpec, generation_id: str) -> dict[str, str]:
    """Return the only caller-authored metadata accepted by pinned Zoekt."""

    return {
        "schema": "mastermind.codeintel_index_identity.v1",
        "generation_id": generation_id,
        "logical_repository_id": spec.repository_id,
        "canonical_repository": spec.repository_name,
        "ref_label": spec.ref_label,
        "commit_sha": spec.commit_sha,
        "source_tree_digest": spec.source_tree_digest,
        "shard_namespace": spec.shard_namespace,
    }


def _loopback_has_exact_identities(
    endpoint: LoopbackEndpoint, expected: Sequence[_RepositoryIdentity]
) -> bool:
    """Probe pinned Zoekt's private RPC list without accepting a generic listener."""

    try:
        payload = _post_loopback_list(endpoint)
        repositories = payload.get("Repos")
        if not isinstance(repositories, list) or len(repositories) != len(expected):
            return False
        observed: list[_RepositoryIdentity] = []
        for item in repositories:
            if not isinstance(item, dict) or set(item) != {"Repository"}:
                return False
            repository = item["Repository"]
            if not isinstance(repository, dict):
                return False
            name = repository.get("Name")
            metadata = repository.get("Metadata")
            branches = repository.get("Branches")
            if not isinstance(name, str) or not _is_exact_string_map(metadata):
                return False
            if not isinstance(branches, list) or len(branches) != 1:
                return False
            branch = branches[0]
            if not isinstance(branch, dict) or set(branch) != {"Name", "Version"}:
                return False
            ref_label, commit_sha = branch.get("Name"), branch.get("Version")
            if not isinstance(ref_label, str) or not isinstance(commit_sha, str):
                return False
            observed.append(
                _RepositoryIdentity(
                    repository_name=name,
                    metadata=metadata,
                    ref_label=ref_label,
                    commit_sha=commit_sha,
                )
            )
        observed_keys = {_repository_identity_key(identity) for identity in observed}
        expected_keys = {_repository_identity_key(identity) for identity in expected}
        return len(observed_keys) == len(observed) and observed_keys == expected_keys
    except (OSError, ValueError, json.JSONDecodeError, http.client.HTTPException):
        return False


def _post_loopback_list(endpoint: LoopbackEndpoint) -> dict[str, object]:
    """Perform the closed, bounded, no-proxy POST probe used only by the host runner."""

    connection = http.client.HTTPConnection(
        endpoint.host, endpoint.port, timeout=_IDENTITY_PROBE_TIMEOUT_SECONDS
    )
    try:
        connection.request(
            "POST",
            "/api/list",
            body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "2"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("identity probe did not return HTTP 200")
        length_header = response.getheader("Content-Length")
        if length_header is not None and (
            not length_header.isdecimal() or int(length_header) > _MAX_IDENTITY_RESPONSE_BYTES
        ):
            raise ValueError("identity probe response exceeds its bound")
        body = response.read(_MAX_IDENTITY_RESPONSE_BYTES + 1)
        if len(body) > _MAX_IDENTITY_RESPONSE_BYTES:
            raise ValueError("identity probe response exceeds its bound")
    finally:
        connection.close()
    loaded = json.loads(
        body.decode("utf-8"),
        object_pairs_hook=_reject_duplicate_json_keys,
        parse_constant=_reject_non_finite_json_constant,
    )
    if not isinstance(loaded, dict):
        raise ValueError("identity probe JSON must be an object")
    return loaded


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("identity probe JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_non_finite_json_constant(value: str) -> object:
    raise ValueError(f"identity probe JSON constant is forbidden: {value}")


def _is_exact_string_map(value: object) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    )


def _repository_identity_key(identity: _RepositoryIdentity) -> tuple[object, ...]:
    return (
        identity.repository_name,
        tuple(sorted(identity.metadata.items())),
        identity.ref_label,
        identity.commit_sha,
    )


def _prepare_external_directory(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute disposable host path")
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"{label} must be a real directory")
    else:
        path.mkdir(parents=True, mode=0o700)
    return path


def _assert_external_to_sources(
    shard_root: Path, log_root: Path, repositories: Sequence[RepositorySpec]
) -> None:
    for root in (shard_root, log_root):
        resolved = root.resolve()
        for spec in repositories:
            source = spec.source_snapshot_root.resolve()
            if resolved == source or source in resolved.parents:
                raise ZoektProcessError(
                    f"disposable process directory must be external to source: {root}"
                )


def _reserve_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        return int(reservation.getsockname()[1])


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


def _receipt_payload(status: RepositoryIndexStatus) -> dict[str, str]:
    assert status.indexed_commit_sha is not None
    assert status.source_tree_digest is not None
    assert status.shard_namespace is not None
    return {
        "repository_id": status.repository_id,
        "ref_label": status.ref_label,
        "indexed_commit_sha": status.indexed_commit_sha,
        "source_tree_digest": status.source_tree_digest,
        "shard_namespace": status.shard_namespace,
    }


def _verify_receipt(path: Path, status: RepositoryIndexStatus) -> None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ZoektProcessError(f"missing or malformed index receipt: {path}") from error
    if loaded != _receipt_payload(status):
        raise ZoektProcessError(f"index receipt mismatch: {path}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _diagnostic(output: bytes) -> str:
    return output[:512].decode("utf-8", errors="replace")
