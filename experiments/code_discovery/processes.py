"""Host-only lifecycle controls for disposable exact-pinned Zoekt processes."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import selectors
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
_CLOSED_ENV: Final = {"LANG": "C", "LC_ALL": "C"}


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
    """Exact host-approved executable identity; never a PATH lookup."""

    path: Path
    sha256: str
    source_commit: str

    def verify(self) -> None:
        """Check the binary before and after every invocation."""

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


class _ProcessCapture:
    """Bound diagnostic capture that terminates a noisy long-lived server."""

    def __init__(self, process: subprocess.Popen[bytes], maximum: int) -> None:
        self._process = process
        self._maximum = maximum
        self._seen = 0
        self._overflow = False
        self._lock = threading.Lock()
        self._threads = tuple(
            threading.Thread(target=self._drain, args=(stream,), daemon=True)
            for stream in (process.stdout, process.stderr)
            if stream is not None
        )
        for thread in self._threads:
            thread.start()

    def _drain(self, stream: object) -> None:
        assert hasattr(stream, "read")
        reader = getattr(stream, "read1", stream.read)
        while True:
            chunk = reader(8192)
            if not chunk:
                return
            with self._lock:
                self._seen += len(chunk)
                if self._seen > self._maximum:
                    self._overflow = True
                    if self._process.poll() is None:
                        self._process.terminate()

    def raise_if_overflow(self) -> None:
        with self._lock:
            if self._overflow:
                raise ProcessOutputOverflow("Zoekt process exceeded bounded diagnostics")

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
        self.shard_root = _prepare_external_directory(Path(shard_root), "shard_root")
        self.log_root = _prepare_external_directory(Path(log_root), "log_root")
        self.startup_timeout_seconds = startup_timeout_seconds
        self._statuses: tuple[RepositoryIndexStatus, ...] = ()
        self._search_process: subprocess.Popen[bytes] | None = None
        self._search_capture: _ProcessCapture | None = None

    def build_indexes(
        self, manifest: IndexManifest
    ) -> tuple[RepositoryIndexStatus, ...]:
        """Index each source row independently into an empty logical namespace."""

        _assert_external_to_sources(self.shard_root, self.log_root, manifest.repositories)
        statuses: list[RepositoryIndexStatus] = []
        for spec in manifest.repositories:
            generation = self.shard_root / spec.shard_namespace
            if generation.exists():
                raise StaleShardGenerationError(
                    f"stale shard generation requires host discard: {generation}"
                )
            generation.mkdir(mode=0o700)
            metadata_path = generation / "z0-index-meta.json"
            _write_json(
                metadata_path,
                {
                    "repository_id": spec.repository_id,
                    "repository_name": spec.repository_name,
                    "ref_label": spec.ref_label,
                    "commit_sha": spec.commit_sha,
                    "source_tree_digest": spec.source_tree_digest,
                    "shard_namespace": spec.shard_namespace,
                },
            )
            self.indexer.verify()
            argv = _indexer_argv(self.indexer, spec, generation, metadata_path)
            _run_bounded(
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
        self._statuses = tuple(statuses)
        return self._statuses

    def start_search(self) -> LoopbackEndpoint:
        """Start one exact webserver bound to numeric loopback after receipt checks."""

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
        endpoint = LoopbackEndpoint("127.0.0.1", _reserve_loopback_port())
        argv = _webserver_argv(self.webserver, endpoint, self.shard_root, self.log_root)
        process = _spawn(
            argv,
            cwd=self.shard_root,
        )
        capture = _ProcessCapture(process, _MAX_PROCESS_OUTPUT_BYTES)
        self._search_process = process
        self._search_capture = capture
        try:
            self.webserver.verify()
            _wait_for_loopback(process, capture, endpoint, self.startup_timeout_seconds)
        except Exception:
            self.close()
            raise
        return endpoint

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

    def close(self) -> None:
        """Terminate the child once; subsequent cleanup is deliberately harmless."""

        process, capture = self._search_process, self._search_capture
        self._search_process = None
        self._search_capture = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if capture is not None:
            capture.join()


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
        "--rpc=false",
        "--indexserver_proxy=false",
        "--pprof=false",
    )


def _run_bounded(
    argv: Sequence[str], *, cwd: Path, timeout_seconds: float
) -> tuple[bytes, bytes]:
    process = _spawn(argv, cwd=cwd)
    stdout, stderr = _collect_bounded_output(
        process, maximum=_MAX_PROCESS_OUTPUT_BYTES, timeout_seconds=timeout_seconds
    )
    if process.returncode:
        raise ZoektProcessError(
            f"Zoekt command exited {process.returncode}: {_diagnostic(stderr or stdout)!r}"
        )
    return stdout, stderr


def _spawn(argv: Sequence[str], *, cwd: Path) -> subprocess.Popen[bytes]:
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
                process.kill()
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
                        process.kill()
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
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        capture.raise_if_overflow()
        if process.poll() is not None:
            raise ZoektProcessExited(
                f"ZOEKT_PROCESS_EXITED: zoekt-webserver exited with {process.returncode}"
            )
        try:
            with socket.create_connection((endpoint.host, endpoint.port), timeout=0.1):
                return
        except OSError:
            time.sleep(0.02)
    raise ZoektProcessTimeout("zoekt-webserver did not bind loopback before timeout")


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
