"""One physical ACP process resource, below Worker and retained OHF ownership.

Callers own admission, identities, startup configuration, provider sessions and
results. This handle owns only its actual subprocess, pipes and finite capture.
It allocates no application identifier and maintains no lifecycle registry.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import math
import os
import re
import signal
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path

from control_plane.codex_worker import (
    ProcessInspector as LocalProcessInspector,
    _assert_binary_unchanged, _create_private_file, _utc_now,
)
from control_plane.worker_execution_contract import BinaryAttestation, ProcessInspector

_ENV_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_PIPE_CHUNK = _PIPE_LIMIT = 64 * 1024


class AcpNativeProcessError(RuntimeError):
    """The fixed native ACP process could not be safely opened or settled."""


def bounded_environment(raw: Mapping[str, str]) -> dict[str, str]:
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
        if total > 256 * 1024:
            raise AcpNativeProcessError("ACP native environment exceeds reviewed ceiling")
        result[key] = value
    return result


def bounded_argv(binary: BinaryAttestation, raw: Sequence[str]) -> tuple[str, ...]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise AcpNativeProcessError("ACP launch argv builder returned an invalid sequence")
    argv = tuple(raw)
    if (not argv or len(argv) > 256 or argv[0] != binary.real_path
            or any(not isinstance(value, str) or not value or any(c in value for c in "\x00\n\r")
                   for value in argv)
            or sum(len(value.encode("utf-8")) + 1 for value in argv) > 256 * 1024):
        raise AcpNativeProcessError("ACP launch argv is outside the reviewed boundary")
    return argv


@dataclasses.dataclass(frozen=True)
class NativeProcessIdentity:
    pid: int
    pgid: int
    session_id: int
    process_start_identity: str
    boot_session_id: str
    effective_uid: int
    effective_gid: int
    real_uid: int
    real_gid: int


def identity_matches(inspector: ProcessInspector, identity: NativeProcessIdentity) -> bool:
    try:
        if inspector.boot_session_id() != identity.boot_session_id:
            return False
        observed = inspector.inspect(identity.pid)
    except Exception:
        return False
    return (
        getattr(observed, "start_identity", None) == identity.process_start_identity
        and getattr(observed, "pgid", None) == identity.pgid
        and getattr(observed, "session_id", None) == identity.session_id
        and getattr(observed, "effective_uid", None) == identity.effective_uid
        and getattr(observed, "effective_gid", None) == identity.effective_gid
        and getattr(observed, "real_uid", None) == identity.real_uid
        and getattr(observed, "real_gid", None) == identity.real_gid
    )


@dataclasses.dataclass(frozen=True)
class NativeCapture:
    sha256: str
    size: int
    overflow: bool


@dataclasses.dataclass(frozen=True)
class NativeProcessSettlement:
    exit_code: int | None
    finished_at: str
    stdout: NativeCapture | None
    stderr: NativeCapture | None
    settled: bool
    signal_sent: bool
    escalated: bool
    already_exited: bool


class NativeProcessResource:
    """Single physical generation with one memoized, shielded finish effect."""

    def __init__(self) -> None:
        self.finish_task: asyncio.Task[NativeProcessSettlement] | None = None
        self.finish_reason: str | None = None

    @classmethod
    async def open(
        cls, *, binary: BinaryAttestation, argv: Sequence[str], environment: Mapping[str, str],
        cwd: Path, stdout_path: Path, stderr_path: Path, stdout_limit_bytes: int,
        stderr_limit_bytes: int, settle_seconds: float, stdout_is_protocol: bool = True,
        pass_fds: tuple[int, ...] = (), inspector: ProcessInspector | None = None,
        close_hook: Callable[[], Awaitable[None]] | None = None,
    ) -> NativeProcessResource:
        _assert_binary_unchanged(binary)
        argv, env = bounded_argv(binary, argv), bounded_environment(environment)
        if (isinstance(settle_seconds, bool) or not isinstance(settle_seconds, (int, float))
                or not math.isfinite(settle_seconds) or settle_seconds <= 0):
            raise AcpNativeProcessError("ACP process settlement bound is invalid")
        for limit in (stdout_limit_bytes, stderr_limit_bytes):
            if type(limit) is not int or not 1024 <= limit <= 64 * 1024 * 1024:
                raise AcpNativeProcessError("ACP capture limit is outside reviewed bounds")
        if (type(stdout_is_protocol) is not bool or not isinstance(pass_fds, tuple)
                or any(type(fd) is not int or fd < 3 for fd in pass_fds)
                or len(pass_fds) > 16 or len(set(pass_fds)) != len(pass_fds)
                or (close_hook is not None and not callable(close_hook))):
            raise AcpNativeProcessError("ACP physical stream inputs are invalid")
        self = cls()
        self.inspector = inspector or LocalProcessInspector()
        self.settle_seconds, self.close_hook = float(settle_seconds), close_hook
        stdout_fd = stderr_fd = None
        process = None
        try:
            stdout_fd = _create_private_file(stdout_path)
            stderr_fd = _create_private_file(stderr_path)
            process = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, cwd=str(cwd), env=env,
                start_new_session=True, pass_fds=pass_fds, limit=_PIPE_LIMIT,
            )
            if process.stdin is None or process.stdout is None or process.stderr is None:
                raise AcpNativeProcessError("ACP native stdio pipes are unavailable")
            observed = self.inspector.inspect(process.pid)
            candidate_identity = NativeProcessIdentity(
                process.pid, int(getattr(observed, "pgid")), int(getattr(observed, "session_id")),
                str(getattr(observed, "start_identity")), self.inspector.boot_session_id(),
                int(getattr(observed, "effective_uid")), int(getattr(observed, "effective_gid")),
                int(getattr(observed, "real_uid")), int(getattr(observed, "real_gid")),
            )
            if candidate_identity.pgid != process.pid or candidate_identity.session_id != process.pid:
                raise AcpNativeProcessError("ACP child did not enter its own process/session generation")
            self.identity = candidate_identity
            self.process, self.writer = process, process.stdin
            self.reader = asyncio.StreamReader(limit=_PIPE_LIMIT) if stdout_is_protocol else None
            self.stdout_task = asyncio.create_task(self._pump(
                process.stdout, self.reader, stdout_fd, stdout_limit_bytes))
            stdout_fd = None
            self.stderr_task = asyncio.create_task(self._pump(
                process.stderr, None, stderr_fd, stderr_limit_bytes))
            stderr_fd = None
            self.wait_task = asyncio.create_task(process.wait())
            return self
        except BaseException:
            # This not-yet-published child is still the direct subprocess owned
            # by this launch. Never signal an observed replacement process group.
            try:
                if process is not None and process.returncode is None:
                    observed_identity = getattr(self, "identity", None)
                    try:
                        if observed_identity is not None and identity_matches(self.inspector, observed_identity):
                            os.killpg(observed_identity.pgid, signal.SIGKILL)
                        elif observed_identity is None:
                            process.kill()
                    except (ProcessLookupError, PermissionError):
                        # Failed opening remains uncertain at the original owner.
                        pass
                    try:
                        await asyncio.wait_for(process.communicate(), timeout=2)
                    except Exception:
                        pass
            finally:
                for fd in (stdout_fd, stderr_fd):
                    if fd is not None:
                        os.close(fd)
            raise

    @staticmethod
    def _write_all(fd: int, payload: bytes) -> None:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("ACP native capture write made no progress")
            view = view[written:]

    async def _pump(self, source: asyncio.StreamReader, destination: asyncio.StreamReader | None,
                    fd: int, limit: int) -> NativeCapture:
        digest, size, overflow = hashlib.sha256(), 0, False
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
        return NativeCapture(digest.hexdigest(), size, overflow)

    def identity_matches(self) -> bool:
        return identity_matches(self.inspector, self.identity)

    async def finish(self, reason: str | None) -> NativeProcessSettlement:
        normalized = reason.strip() if isinstance(reason, str) else None
        if reason is not None and not normalized:
            raise AcpNativeProcessError("ACP native cancellation reason is invalid")
        if self.finish_task is None:
            self.finish_reason = normalized
            self.finish_task = asyncio.create_task(self._finish_once(normalized))
        elif self.finish_reason != normalized:
            raise AcpNativeProcessError("ACP native finish was already bound to another reason")
        return await asyncio.shield(self.finish_task)

    async def _finish_once(self, reason: str | None) -> NativeProcessSettlement:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settle_seconds
        signal_sent = escalated = writer_settled = False
        already_exited = self.wait_task.done() or self.process.returncode is not None
        if not self.writer.is_closing():
            self.writer.close()
        try:
            close_task = asyncio.create_task(self.writer.wait_closed())
            done, _ = await asyncio.wait({close_task}, timeout=max(0.0, min(0.5, deadline - loop.time())))
            if not done:
                close_task.cancel()
            elif not close_task.cancelled():
                close_task.result()
                writer_settled = True
        except Exception:
            writer_settled = False
        hook_settled = True
        if self.close_hook is not None:
            try:
                await asyncio.wait_for(self.close_hook(), timeout=max(0.001, min(0.5, deadline - loop.time())))
            except Exception:
                hook_settled = False
        if not self.wait_task.done():
            remaining = max(0.0, deadline - loop.time())
            natural_exit_budget = min(0.25, remaining)
            if reason is None:
                natural_exit_budget = remaining - min(0.5, remaining / 2)
            done, _ = await asyncio.wait({self.wait_task}, timeout=natural_exit_budget)
            if not done and self.identity_matches():
                try:
                    os.killpg(self.identity.pgid, signal.SIGTERM)
                    signal_sent = True
                except ProcessLookupError:
                    pass
                done, _ = await asyncio.wait({self.wait_task}, timeout=max(0.0, (deadline - loop.time()) / 2))
                if not done and self.identity_matches():
                    try:
                        os.killpg(self.identity.pgid, signal.SIGKILL)
                        signal_sent = escalated = True
                    except ProcessLookupError:
                        pass
        if not self.wait_task.done():
            await asyncio.wait({self.wait_task}, timeout=max(0.0, deadline - loop.time()))
        captures = {self.stdout_task, self.stderr_task}
        if any(not task.done() for task in captures):
            await asyncio.wait(captures, timeout=max(0.0, deadline - loop.time()))
        def capture(task):
            if not task.done() or task.cancelled() or task.exception() is not None:
                return None
            return task.result()
        stdout, stderr = capture(self.stdout_task), capture(self.stderr_task)
        settled = bool(self.wait_task.done() and self.process.returncode is not None
                       and stdout is not None and stderr is not None
                       and writer_settled and hook_settled and not stdout.overflow and not stderr.overflow)
        return NativeProcessSettlement(self.process.returncode, _utc_now(), stdout, stderr,
                                       settled, signal_sent, escalated, already_exited)
