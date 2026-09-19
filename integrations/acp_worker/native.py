"""Native subprocess owner for a fixed, reviewed ACP stdio profile.

This module owns only one provider subprocess generation and its byte streams.
Executive OS and the common broker still own admission/lifecycle; AcpWorkerAdapter
owns ACP semantics/result normalization.  Provider selection, credentials and
route activation are fixed outside WorkerLaunchSpec at trusted construction.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
import re
import signal
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from control_plane.codex_worker import (
    ProcessInspector as LocalProcessInspector,
    _MAX_SCHEMA_BYTES,
    _assert_binary_unchanged,
    _create_private_file,
    _ensure_run_directory,
    _git_snapshot,
    _is_relative_to,
    _read_limited,
    _utc_now,
)
from control_plane.worker_execution_contract import (
    BinaryAttestation,
    CancelReceipt,
    ProcessInspector,
    WorkerLaunchSpec,
    WorkerProcessRef,
)
from integrations.acp_worker.adapter import AcpProcessCompletion, AcpRunResources
from integrations.acp_worker.turn import _nonfinite, _object_pairs

_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_MAX_ENV_BYTES = 256 * 1024
_DEFAULT_STDOUT_LIMIT = 32 * 1024 * 1024
_DEFAULT_STDERR_LIMIT = 4 * 1024 * 1024
_PIPE_CHUNK = 64 * 1024
_PIPE_LIMIT = 64 * 1024

EnvironmentLoader = Callable[[], Mapping[str, str]]


class AcpNativeProcessError(RuntimeError):
    """The fixed native ACP process could not be safely opened or settled."""


@dataclasses.dataclass(frozen=True)
class AcpNativeProfile:
    """Immutable executable/argv identity; never selected by a Job payload."""

    profile_id: str
    binary: BinaryAttestation
    argv: tuple[str, ...]
    stdout_limit_bytes: int = _DEFAULT_STDOUT_LIMIT
    stderr_limit_bytes: int = _DEFAULT_STDERR_LIMIT

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(self.argv))
        if _PROFILE_ID.fullmatch(self.profile_id) is None:
            raise ValueError("invalid ACP native profile id")
        if not self.argv or self.argv[0] != self.binary.real_path:
            raise ValueError("ACP argv must start with the attested executable")
        if len(self.argv) > 64:
            raise ValueError("ACP argv exceeds reviewed ceiling")
        for arg in self.argv:
            if not isinstance(arg, str) or not arg or "\x00" in arg or "\n" in arg or "\r" in arg:
                raise ValueError("ACP argv contains an invalid argument")
        for value in (self.stdout_limit_bytes, self.stderr_limit_bytes):
            if type(value) is not int or not 1024 <= value <= 64 * 1024 * 1024:
                raise ValueError("ACP capture limit is outside reviewed bounds")


@dataclasses.dataclass(frozen=True)
class _Capture:
    sha256: str
    size: int
    overflow: bool


@dataclasses.dataclass
class _NativeRun:
    spec: WorkerLaunchSpec
    process: asyncio.subprocess.Process
    ref: WorkerProcessRef
    writer: asyncio.StreamWriter
    reader: asyncio.StreamReader
    wait_task: asyncio.Task[int]
    stdout_task: asyncio.Task[_Capture]
    stderr_task: asyncio.Task[_Capture]
    launch_attestation: Mapping[str, Any]
    finish_task: asyncio.Task[AcpProcessCompletion] | None = None
    finish_reason: str | None = None


class AcpNativeProcessOwner:
    """Open and settle one exact ACP subprocess without creating a new lifecycle."""

    def __init__(
        self,
        profile: AcpNativeProfile,
        *,
        environment_loader: EnvironmentLoader,
        inspector: ProcessInspector | None = None,
    ) -> None:
        if not callable(environment_loader):
            raise ValueError("ACP environment loader is required")
        self.profile = profile
        self.environment_loader = environment_loader
        self.inspector = inspector or LocalProcessInspector()
        self._runs: dict[str, _NativeRun] = {}
        self._active: str | None = None

    @staticmethod
    def _environment(loader: EnvironmentLoader) -> dict[str, str]:
        raw = loader()
        if not isinstance(raw, Mapping) or len(raw) > 128:
            raise AcpNativeProcessError("ACP native environment is invalid")
        result: dict[str, str] = {}
        total = 0
        for key, value in raw.items():
            if not isinstance(key, str) or _ENV_KEY.fullmatch(key) is None or not isinstance(value, str):
                raise AcpNativeProcessError("ACP native environment is invalid")
            encoded = value.encode("utf-8")
            if b"\x00" in encoded or len(encoded) > 32 * 1024:
                raise AcpNativeProcessError("ACP native environment is invalid")
            total += len(key.encode("utf-8")) + len(encoded)
            if total > _MAX_ENV_BYTES:
                raise AcpNativeProcessError("ACP native environment exceeds reviewed ceiling")
            result[key] = value
        return result

    @staticmethod
    def _schema(spec: WorkerLaunchSpec) -> Any:
        try:
            raw = _read_limited(spec.result_schema_path, _MAX_SCHEMA_BYTES)
            value = json.loads(raw, object_pairs_hook=_object_pairs, parse_constant=_nonfinite)
        except Exception:
            raise AcpNativeProcessError("ACP native result schema changed or is invalid") from None
        if not isinstance(value, (dict, bool)):
            raise AcpNativeProcessError("ACP native result schema root is invalid")
        return value

    def _identity_matches(self, ref: WorkerProcessRef) -> bool:
        try:
            if self.inspector.boot_session_id() != ref.boot_session_id:
                return False
            observed = self.inspector.inspect(ref.pid)
        except Exception:
            return False
        return (
            getattr(observed, "start_identity", None) == ref.process_start_identity
            and getattr(observed, "pgid", None) == ref.pgid
            and getattr(observed, "session_id", None) == ref.session_id
            and getattr(observed, "effective_uid", None) == ref.effective_uid
            and getattr(observed, "effective_gid", None) == ref.effective_gid
            and getattr(observed, "real_uid", None) == ref.real_uid
            and getattr(observed, "real_gid", None) == ref.real_gid
        )

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("ACP native capture write made no progress")
            view = view[written:]

    async def _pump(
        self,
        source: asyncio.StreamReader,
        destination: asyncio.StreamReader | None,
        fd: int,
        limit: int,
    ) -> _Capture:
        digest = hashlib.sha256()
        size = 0
        overflow = False
        try:
            while True:
                chunk = await source.read(_PIPE_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                if not overflow and size <= limit:
                    self._write_all(fd, chunk)
                    if destination is not None:
                        destination.feed_data(chunk)
                elif not overflow:
                    overflow = True
                    if destination is not None:
                        destination.set_exception(AcpNativeProcessError("ACP native stdout exceeded capture ceiling"))
            if destination is not None and not overflow:
                destination.feed_eof()
        finally:
            os.close(fd)
        return _Capture(digest.hexdigest(), size, overflow)

    async def open_run(self, spec: WorkerLaunchSpec) -> AcpRunResources:
        if self._active is not None or spec.run_id in self._runs:
            raise AcpNativeProcessError("ACP native owner already has active or known work")
        _assert_binary_unchanged(self.profile.binary)
        workspace = Path(spec.workspace_path).resolve(strict=True)
        run_dir = _ensure_run_directory(
            Path(spec.run_dir),
            shared_gid=(int(spec.shared_run_gid) if spec.shared_run_gid is not None else None),
        )
        if _is_relative_to(run_dir, workspace) or _is_relative_to(workspace, run_dir):
            raise AcpNativeProcessError("ACP run directory overlaps the workspace")
        baseline = _git_snapshot(workspace, require_clean=True)
        if spec.expected_base_sha is None or baseline.head != spec.expected_base_sha:
            raise AcpNativeProcessError("ACP workspace base is not exactly bound")
        if spec.expected_worker_uid is not None and os.geteuid() != int(spec.expected_worker_uid):
            raise AcpNativeProcessError("ACP native worker uid does not match admission")
        if spec.expected_worker_gid is not None and os.getegid() != int(spec.expected_worker_gid):
            raise AcpNativeProcessError("ACP native worker gid does not match admission")
        schema = self._schema(spec)
        logs = run_dir / "logs"
        output = run_dir / "output"
        logs.mkdir(mode=0o700, exist_ok=True)
        output.mkdir(mode=0o700, exist_ok=True)
        stdout_path = logs / "acp-stdout.ndjson"
        stderr_path = logs / "acp-stderr.log"
        result_path = output / "result.json"
        stdout_fd = _create_private_file(stdout_path)
        stderr_fd = _create_private_file(stderr_path)
        result_fd = _create_private_file(result_path)
        os.close(result_fd)
        env = self._environment(self.environment_loader)
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *self.profile.argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
                env=env,
                start_new_session=True,
                limit=_PIPE_LIMIT,
            )
            if process.stdin is None or process.stdout is None or process.stderr is None:
                raise AcpNativeProcessError("ACP native stdio pipes are unavailable")
            observed = self.inspector.inspect(process.pid)
            boot_id = self.inspector.boot_session_id()
            pgid = int(getattr(observed, "pgid"))
            session_id = int(getattr(observed, "session_id"))
            if pgid != process.pid or session_id != process.pid:
                raise AcpNativeProcessError("ACP child did not enter its own process/session generation")
            ref = WorkerProcessRef(
                run_id=spec.run_id,
                pid=process.pid,
                pgid=pgid,
                process_start_identity=str(getattr(observed, "start_identity")),
                boot_session_id=boot_id,
                launch_nonce=hashlib.sha256(os.urandom(32)).hexdigest()[:32],
                provider_session_id=None,
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                result_path=str(result_path),
                started_at=_utc_now(),
                binary=self.profile.binary,
                base_sha=baseline.head,
                session_id=session_id,
                effective_uid=int(getattr(observed, "effective_uid")),
                effective_gid=int(getattr(observed, "effective_gid")),
                real_uid=int(getattr(observed, "real_uid")),
                real_gid=int(getattr(observed, "real_gid")),
            )
            if spec.expected_worker_uid is not None and ref.effective_uid != int(spec.expected_worker_uid):
                raise AcpNativeProcessError("ACP child effective uid does not match admission")
            if spec.expected_worker_gid is not None and ref.effective_gid != int(spec.expected_worker_gid):
                raise AcpNativeProcessError("ACP child effective gid does not match admission")
            proxy = asyncio.StreamReader(limit=_PIPE_LIMIT)
            stdout_task = asyncio.create_task(
                self._pump(process.stdout, proxy, stdout_fd, self.profile.stdout_limit_bytes)
            )
            stderr_task = asyncio.create_task(
                self._pump(process.stderr, None, stderr_fd, self.profile.stderr_limit_bytes)
            )
            wait_task = asyncio.create_task(process.wait())
            argv_digest = hashlib.sha256(
                json.dumps(self.profile.argv, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            ).hexdigest()
            attestation = {
                "schema_version": "mastermind.acp_native_launch/v1",
                "profile_id": self.profile.profile_id,
                "binary_sha256": self.profile.binary.sha256,
                "binary_version": self.profile.binary.version,
                "argv_sha256": argv_digest,
                "environment_keys": sorted(env),
                "credential_values_persisted": False,
                "process_identity": {
                    "pid": ref.pid,
                    "pgid": ref.pgid,
                    "session_id": ref.session_id,
                    "start_identity": ref.process_start_identity,
                    "boot_id": ref.boot_session_id,
                    "effective_uid": ref.effective_uid,
                    "effective_gid": ref.effective_gid,
                },
            }
            run = _NativeRun(spec, process, ref, process.stdin, proxy, wait_task,
                             stdout_task, stderr_task, attestation)
            self._runs[spec.run_id] = run
            self._active = spec.run_id
        except BaseException:
            if process is not None and process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except Exception:
                    pass
            for fd in (stdout_fd, stderr_fd):
                try:
                    os.close(fd)
                except OSError:
                    pass
            raise

        async def finish(reason: str | None) -> AcpProcessCompletion:
            return await self._finish(run, reason)

        return AcpRunResources(ref, process.stdin, proxy, attestation, schema, finish)

    async def _finish(self, run: _NativeRun, reason: str | None) -> AcpProcessCompletion:
        normalized = reason.strip() if isinstance(reason, str) else None
        if reason is not None and not normalized:
            raise AcpNativeProcessError("ACP native cancellation reason is invalid")
        if run.finish_task is None:
            run.finish_reason = normalized
            run.finish_task = asyncio.create_task(self._finish_once(run, normalized))
        elif run.finish_reason != normalized:
            raise AcpNativeProcessError("ACP native finish was already bound to another reason")
        return await asyncio.shield(run.finish_task)

    async def _finish_once(self, run: _NativeRun, reason: str | None) -> AcpProcessCompletion:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + float(run.spec.cancel_grace_seconds)
        signal_sent = False
        escalated = False
        already_exited = run.wait_task.done() or run.process.returncode is not None
        writer_settled = False
        if not run.writer.is_closing():
            run.writer.close()
        try:
            close_task = asyncio.create_task(run.writer.wait_closed())
            done, _ = await asyncio.wait({close_task}, timeout=max(0.0, min(0.5, deadline - loop.time())))
            writer_settled = bool(done)
            if not done:
                close_task.cancel()
        except Exception:
            writer_settled = False

        if not run.wait_task.done():
            done, _ = await asyncio.wait({run.wait_task}, timeout=max(0.0, min(0.25, deadline - loop.time())))
            if not done and self._identity_matches(run.ref):
                try:
                    os.killpg(run.ref.pgid, signal.SIGTERM)
                    signal_sent = True
                except ProcessLookupError:
                    pass
                done, _ = await asyncio.wait({run.wait_task}, timeout=max(0.0, (deadline - loop.time()) / 2))
                if not done and self._identity_matches(run.ref):
                    try:
                        os.killpg(run.ref.pgid, signal.SIGKILL)
                        signal_sent = True
                        escalated = True
                    except ProcessLookupError:
                        pass
        if not run.wait_task.done():
            await asyncio.wait({run.wait_task}, timeout=max(0.0, deadline - loop.time()))

        capture_tasks = {run.stdout_task, run.stderr_task}
        if any(not task.done() for task in capture_tasks):
            await asyncio.wait(capture_tasks, timeout=max(0.0, deadline - loop.time()))
        stdout = run.stdout_task.result() if run.stdout_task.done() and not run.stdout_task.cancelled() else None
        stderr = run.stderr_task.result() if run.stderr_task.done() and not run.stderr_task.cancelled() else None
        process_done = run.wait_task.done() and run.process.returncode is not None
        captures_done = stdout is not None and stderr is not None
        settled = bool(
            process_done and captures_done and writer_settled
            and not stdout.overflow and not stderr.overflow
        )
        finished_at = _utc_now()
        cancellation = None
        if reason is not None:
            cancellation = CancelReceipt(
                run.ref.run_id, reason, signal_sent, escalated, already_exited, finished_at
            )
        if settled and self._active == run.ref.run_id:
            self._active = None
        empty = hashlib.sha256(b"").hexdigest()
        return AcpProcessCompletion(
            process_ref=run.ref,
            exit_code=run.process.returncode,
            finished_at=finished_at,
            stdout_sha256=stdout.sha256 if stdout is not None else empty,
            stderr_sha256=stderr.sha256 if stderr is not None else empty,
            settled=settled,
            cancellation=cancellation,
        )


__all__ = [
    "AcpNativeProcessError",
    "AcpNativeProcessOwner",
    "AcpNativeProfile",
    "EnvironmentLoader",
]
