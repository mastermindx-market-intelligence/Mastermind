"""Bounded stdio JSON-RPC client for the C0 falsifier.

Design rules, all of them load-bearing:

* the executable is pinned by digest and checked before *and* after launch, so
  a swap during the run is caught;
* the child gets a closed, minimal environment whose HOME and TMPDIR point at
  external scratch — a server that writes "next to the project" writes into the
  sandbox instead;
* frames and stderr are bounded, so a hostile or broken server cannot exhaust
  memory;
* every failure is typed and terminal for the affected request. There is no
  shell fallback, no automatic resend, and no network path.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from experiments.code_intelligence.backend import ExecutableSpec

__all__ = [
    "MAX_FRAME_BYTES",
    "MAX_STDERR_BYTES",
    "JsonRpcError",
    "JsonRpcStdioClient",
]

MAX_FRAME_BYTES = 4 * 1024 * 1024
MAX_STDERR_BYTES = 32 * 1024
_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_NOTIFICATIONS = 256
_READ_CHUNK = 64 * 1024


class JsonRpcError(Exception):
    """Typed, fail-closed transport or protocol refusal."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass
class _Pending:
    event: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: Any = None
    answered: bool = False


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


class JsonRpcStdioClient:
    """Minimal, hostile-input-tolerant JSON-RPC 2.0 client over stdio."""

    used_shell = False

    def __init__(
        self,
        *,
        spec: ExecutableSpec,
        scratch: Path,
        max_notifications: int = _DEFAULT_MAX_NOTIFICATIONS,
        default_timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self._spec = spec
        self._scratch = Path(scratch)
        self._default_timeout = default_timeout
        self._process: subprocess.Popen[bytes] | None = None
        self._pending: dict[int, _Pending] = {}
        self._notifications: deque[dict[str, Any]] = deque(maxlen=max_notifications)
        self._stderr = bytearray()
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._fatal: JsonRpcError | None = None
        self._next_id = 1
        self._reader: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._closed = False

    # ---------------------------------------------------------------- identity

    @property
    def launch_argv(self) -> list[str]:
        return [str(self._spec.path), *self._spec.argv_suffix]

    @property
    def child_env_allowlist(self) -> tuple[str, ...]:
        return tuple(sorted(self._child_env()))

    def _child_env(self) -> dict[str, str]:
        """A closed environment. Nothing from the host propagates implicitly."""
        return {
            "PATH": "/usr/bin:/bin",
            "HOME": str(self._scratch),
            "TMPDIR": str(self._scratch),
            "LANG": "C",
            "LC_ALL": "C",
            "PYTHONHASHSEED": "0",
            # A language server must never leave bytecode in the candidate tree.
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stderr_tail(self) -> bytes:
        with self._lock:
            return bytes(self._stderr)

    # ------------------------------------------------------------------- start

    def _verify_executable(self) -> None:
        path = self._spec.path
        if path.is_symlink():
            raise JsonRpcError("EXECUTABLE_SYMLINK_REFUSED", str(path))
        if not path.is_file():
            raise JsonRpcError("EXECUTABLE_UNAVAILABLE", str(path))
        actual = _file_digest(path)
        if actual != self._spec.sha256:
            raise JsonRpcError(
                "EXECUTABLE_DIGEST_MISMATCH",
                f"expected {self._spec.sha256}, found {actual}",
            )

    def start(self) -> None:
        self._verify_executable()
        self._scratch.mkdir(parents=True, exist_ok=True)
        try:
            self._process = subprocess.Popen(  # noqa: S603 - fixed argv, shell=False
                self.launch_argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._child_env(),
                cwd=str(self._scratch),
                shell=False,
                close_fds=True,
            )
        except OSError as exc:
            raise JsonRpcError("EXECUTABLE_UNAVAILABLE", str(exc)) from exc

        # Re-verify after launch: a swap between check and exec is still a swap.
        self._verify_executable()

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._stderr_thread = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_thread.start()

    # ------------------------------------------------------------------ reading

    def _read_frame(self, stream) -> dict[str, Any] | None:
        headers: dict[bytes, bytes] = {}
        while True:
            line = stream.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            if b":" not in line:
                raise JsonRpcError(
                    "PROTOCOL_MALFORMED_HEADER", line[:120].decode("ascii", "replace")
                )
            key, value = line.split(b":", 1)
            headers[key.strip().lower()] = value.strip()

        raw_length = headers.get(b"content-length")
        if raw_length is None:
            raise JsonRpcError("PROTOCOL_MALFORMED_HEADER", "no content-length")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise JsonRpcError(
                "PROTOCOL_MALFORMED_HEADER", raw_length.decode("ascii", "replace")
            ) from exc
        if length < 0:
            raise JsonRpcError("PROTOCOL_MALFORMED_HEADER", "negative length")
        if length > MAX_FRAME_BYTES:
            raise JsonRpcError(
                "PROTOCOL_FRAME_TOO_LARGE", f"{length} exceeds {MAX_FRAME_BYTES}"
            )

        body = stream.read(length)
        if body is None or len(body) < length:
            return None
        try:
            message = json.loads(body)
        except ValueError as exc:
            raise JsonRpcError("PROTOCOL_MALFORMED_BODY", str(exc)[:160]) from exc
        if not isinstance(message, dict):
            raise JsonRpcError("PROTOCOL_MALFORMED_BODY", "frame is not an object")
        return message

    def _read_loop(self) -> None:
        assert self._process is not None
        stream = self._process.stdout
        try:
            while True:
                try:
                    message = self._read_frame(stream)
                except JsonRpcError as exc:
                    self._fail_all(exc)
                    return
                except (OSError, ValueError) as exc:
                    self._fail_all(JsonRpcError("SERVER_EXITED", str(exc)[:160]))
                    return
                if message is None:
                    self._fail_all(JsonRpcError("SERVER_EXITED", "stdout closed"))
                    return
                self._dispatch(message)
        finally:  # pragma: no cover - defensive
            pass

    def _dispatch(self, message: dict[str, Any]) -> None:
        message_id = message.get("id")
        if message_id is not None and ("result" in message or "error" in message):
            with self._lock:
                pending = self._pending.get(message_id)
                if pending is None:
                    return  # cancelled or unknown: drop, never resurrect
                pending.result = message.get("result")
                pending.error = message.get("error")
                pending.answered = True
            pending.event.set()
            return
        if message.get("method"):
            with self._lock:
                self._notifications.append(
                    {"method": message["method"], "params": message.get("params")}
                )

    def _stderr_loop(self) -> None:
        assert self._process is not None
        stream = self._process.stderr
        try:
            while True:
                chunk = stream.read(_READ_CHUNK)
                if not chunk:
                    return
                with self._lock:
                    self._stderr.extend(chunk)
                    if len(self._stderr) > MAX_STDERR_BYTES:
                        del self._stderr[:-MAX_STDERR_BYTES]
        except (OSError, ValueError):  # pragma: no cover - defensive
            return

    def _fail_all(self, error: JsonRpcError) -> None:
        with self._lock:
            self._fatal = error
            pending = list(self._pending.values())
        for item in pending:
            item.event.set()

    # ------------------------------------------------------------------ writing

    def _send(self, message: Mapping[str, Any]) -> None:
        assert self._process is not None
        body = json.dumps(
            message, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        frame = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        with self._write_lock:
            try:
                self._process.stdin.write(frame)
                self._process.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                raise JsonRpcError("SERVER_EXITED", str(exc)[:160]) from exc

    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None:
        if self._process is None:
            raise JsonRpcError("SERVER_NOT_STARTED", method)
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        if self._process is None:
            raise JsonRpcError("SERVER_NOT_STARTED", method)
        with self._lock:
            if self._fatal is not None:
                raise self._fatal
            request_id = self._next_id
            self._next_id += 1
            pending = _Pending()
            self._pending[request_id] = pending

        try:
            self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params or {},
                }
            )
        except JsonRpcError:
            with self._lock:
                self._pending.pop(request_id, None)
            raise

        waited = pending.event.wait(
            self._default_timeout if timeout is None else timeout
        )

        with self._lock:
            self._pending.pop(request_id, None)
            fatal = self._fatal

        if not waited:
            # Tell the server to stop working, then refuse. Never auto-resend.
            try:
                self.notify("$/cancelRequest", {"id": request_id})
            except JsonRpcError:
                pass
            raise JsonRpcError("REQUEST_TIMEOUT", f"{method} exceeded budget")

        if not pending.answered:
            raise fatal or JsonRpcError("SERVER_EXITED", method)

        if pending.error is not None:
            raise JsonRpcError(
                "SERVER_ERROR",
                json.dumps(pending.error, sort_keys=True)[:300],
            )
        return pending.result

    def drain_notifications(self) -> list[dict[str, Any]]:
        with self._lock:
            drained = list(self._notifications)
            self._notifications.clear()
        return drained

    # ------------------------------------------------------------------- close

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process is None:
            return
        for stream in (process.stdin,):
            try:
                if stream is not None:
                    stream.close()
            except OSError:  # pragma: no cover - defensive
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                process.kill()
                process.wait(timeout=5)
        for thread in (self._reader, self._stderr_thread):
            if thread is not None:
                thread.join(timeout=5)
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:  # pragma: no cover - defensive
                pass
