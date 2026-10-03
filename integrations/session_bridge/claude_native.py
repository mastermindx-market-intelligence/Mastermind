"""Storeless exact-target Claude Code cross-session native attention.

Claude Code's supported same-machine messaging endpoint is a private per-session
Unix socket. This adapter never discovers by title/recency, never mutates
crossSessionInbound, never reads or transmits CLAUDE_CODE_MESSAGING_TOKEN, and
never creates a lifecycle/session registry.

A target is addressable only when all current host facts agree:
- direct private socket root owned by the expected uid;
- direct private Unix socket named for one live pid;
- live process owned by that uid and rooted in a host-approved executable tree;
- exactly one canonical --resume UUID in that process;
- stable process-start and socket inode/device identity.

Transport write is attention only. It is not target consumption, model START,
RESULT, or parent consumption. Durable at-most-once/effect reservation remains
with the incumbent Executive/Wake owner.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import stat
import subprocess
from collections.abc import Callable
from typing import Any
from uuid import UUID

from .native_wire import AttentionReference, _notice
from .schemas import BridgeError

_SOCKET_NAME = re.compile(r"^([1-9][0-9]{0,9})\.sock$")
_MAX_PROCESS_TEXT = 32_768
_MAX_START_TEXT = 128
_MAX_HOST_REF = 255


@dataclasses.dataclass(frozen=True)
class ClaudeProcessObservation:
    pid: int
    uid: int
    process_start: str
    executable: str
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.pid) is not int or self.pid < 1:
            raise ValueError("Claude process pid is invalid")
        if type(self.uid) is not int or self.uid < 0:
            raise ValueError("Claude process uid is invalid")
        if (
            not isinstance(self.process_start, str)
            or not self.process_start.strip()
            or len(self.process_start) > _MAX_START_TEXT
        ):
            raise ValueError("Claude process start identity is invalid")
        executable = Path(self.executable)
        if not executable.is_absolute():
            raise ValueError("Claude process executable must be absolute")
        if (
            type(self.argv) is not tuple
            or not self.argv
            or any(not isinstance(item, str) or not item for item in self.argv)
            or len(" ".join(self.argv)) > _MAX_PROCESS_TEXT
        ):
            raise ValueError("Claude process argv is invalid")


@dataclasses.dataclass(frozen=True)
class ClaudeNativeTarget:
    target_ref: str
    host_ref: str
    session_id: str
    pid: int
    process_start: str
    executable: str
    socket_path: str
    socket_device: int
    socket_inode: int
    socket_uid: int
    socket_mode: int

    def __post_init__(self) -> None:
        if not isinstance(self.target_ref, str) or not self.target_ref.startswith("claude:"):
            raise ValueError("Claude target ref is invalid")
        if (
            not isinstance(self.host_ref, str)
            or not self.host_ref
            or len(self.host_ref) > _MAX_HOST_REF
        ):
            raise ValueError("Claude host ref is invalid")
        try:
            if str(UUID(self.session_id)) != self.session_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Claude session id is invalid") from None
        if type(self.pid) is not int or self.pid < 1:
            raise ValueError("Claude target pid is invalid")
        if not isinstance(self.process_start, str) or not self.process_start:
            raise ValueError("Claude target process generation is invalid")
        if not Path(self.executable).is_absolute() or not Path(self.socket_path).is_absolute():
            raise ValueError("Claude target paths must be absolute")
        for name in ("socket_device", "socket_inode", "socket_uid", "socket_mode"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"Claude target {name} is invalid")

    def public_projection(self) -> dict[str, Any]:
        """Bounded display facts; physical coordinates remain host-owned."""
        return {
            "target_ref": self.target_ref,
            "kind": "claude",
            "session_id": self.session_id,
            "host_ref": self.host_ref,
            "generation": hashlib.sha256(
                f"{self.process_start}\n{self.socket_device}:{self.socket_inode}".encode()
            ).hexdigest()[:24],
            "addressable": True,
        }


ProcessObserver = Callable[[int], ClaudeProcessObservation | None]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _canonical_uuid(value: str) -> str | None:
    try:
        normalized = str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        return None
    return value if normalized == value else None


def _resume_session_id(argv: tuple[str, ...]) -> str | None:
    values: list[str] = []
    index = 1
    while index < len(argv):
        item = argv[index]
        if item.startswith("--resume="):
            values.append(item.split("=", 1)[1])
        elif item == "--resume" and index + 1 < len(argv):
            index += 1
            values.append(argv[index])
        index += 1
    if len(values) != 1:
        return None
    return _canonical_uuid(values[0])


def _provider_session_id(
    pid: int, socket_path: Path, *, uid: int, session_root: Path
) -> tuple[bool, str | None]:
    """Read Claude's own ephemeral session binding without creating a registry."""
    root = session_root
    metadata = root / f"{pid}.json"
    if not metadata.exists():
        return False, None
    try:
        root_stat = root.lstat()
        meta_stat = metadata.lstat()
        if (
            stat.S_ISLNK(root_stat.st_mode)
            or not stat.S_ISDIR(root_stat.st_mode)
            or root_stat.st_uid != uid
            or stat.S_IMODE(root_stat.st_mode) & 0o022
            or stat.S_ISLNK(meta_stat.st_mode)
            or not stat.S_ISREG(meta_stat.st_mode)
            or meta_stat.st_uid != uid
            or stat.S_IMODE(meta_stat.st_mode) & 0o022
            or meta_stat.st_size > 64 * 1024
        ):
            return True, None
        value = json.loads(metadata.read_text(encoding="utf-8", errors="strict"))
        if not isinstance(value, dict) or value.get("pid") != pid:
            return True, None
        session_id = _canonical_uuid(value.get("sessionId"))
        provider_socket = value.get("messagingSocketPath")
        if session_id is None or not isinstance(provider_socket, str):
            return True, None
        provider_path = Path(provider_socket)
        if not provider_path.is_absolute():
            return True, None
        if provider_path.resolve(strict=True) != socket_path.resolve(strict=True):
            return True, None
        return True, session_id
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return True, None


def _ps_text(pid: int, field: str) -> str | None:
    try:
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", f"{field}="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=2.0,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    if not text or len(text) > _MAX_PROCESS_TEXT:
        return None
    return text


def observe_claude_process(pid: int) -> ClaudeProcessObservation | None:
    """Read one live process without retaining provider/session state."""
    uid_text = _ps_text(pid, "uid")
    started = _ps_text(pid, "lstart")
    executable_text = _ps_text(pid, "comm")
    command = _ps_text(pid, "command")
    if uid_text is None or started is None or executable_text is None:
        return None
    try:
        uid = int(uid_text)
        executable = str(Path(executable_text).resolve(strict=True))
        argv: tuple[str, ...] = (executable,)
        if command is not None:
            try:
                parsed = tuple(shlex.split(command, posix=True))
            except ValueError:
                parsed = ()
            if parsed:
                try:
                    parsed_executable = str(Path(parsed[0]).resolve(strict=True))
                except OSError:
                    parsed_executable = ""
                if parsed_executable == executable:
                    argv = (executable, *parsed[1:])
        return ClaudeProcessObservation(
            pid=pid,
            uid=uid,
            process_start=started,
            executable=executable,
            argv=argv,
        )
    except (OSError, TypeError, ValueError):
        return None


class ClaudeNativeTargetProjector:
    """Project exact currently addressable same-machine Claude inboxes."""

    def __init__(
        self,
        *,
        socket_root: Path,
        session_root: Path,
        allowed_executable_roots: tuple[Path, ...],
        process_observer: ProcessObserver = observe_claude_process,
        uid: int | None = None,
        host_ref: str | None = None,
    ) -> None:
        if not callable(process_observer):
            raise TypeError("process_observer must be callable")
        selected_uid = os.geteuid() if uid is None else uid
        if type(selected_uid) is not int or selected_uid < 0:
            raise ValueError("Claude native uid is invalid")
        root = Path(socket_root)
        session_path = Path(session_root)
        if not root.is_absolute():
            raise ValueError("Claude socket root must be absolute")
        if not session_path.is_absolute():
            raise ValueError("Claude session root must be absolute")
        if not isinstance(allowed_executable_roots, tuple) or not allowed_executable_roots:
            raise ValueError("Claude executable roots are required")
        resolved_roots: list[Path] = []
        for value in allowed_executable_roots:
            path = Path(value)
            if not path.is_absolute():
                raise ValueError("Claude executable root must be absolute")
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                raise ValueError("Claude executable root is unavailable") from None
            if not resolved.is_dir():
                raise ValueError("Claude executable root must be a directory")
            resolved_roots.append(resolved)
        selected_host = socket.gethostname() if host_ref is None else host_ref
        if (
            not isinstance(selected_host, str)
            or not selected_host.strip()
            or len(selected_host) > _MAX_HOST_REF
        ):
            raise ValueError("Claude host ref is invalid")
        self._socket_root = root
        self._session_root = session_path
        self._allowed_roots = tuple(resolved_roots)
        self._process_observer = process_observer
        self._uid = selected_uid
        self._host_ref = selected_host.strip()

    def _root_ready(self) -> None:
        try:
            observed = self._socket_root.lstat()
        except OSError:
            raise BridgeError("native_unavailable", "Claude inbox root is unavailable") from None
        if (
            stat.S_ISLNK(observed.st_mode)
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != self._uid
            or stat.S_IMODE(observed.st_mode) != 0o700
        ):
            raise BridgeError("native_unavailable", "Claude inbox root is unavailable")

    def _executable_allowed(self, executable: str) -> str | None:
        try:
            path = Path(executable)
            if not path.is_absolute():
                return None
            resolved = path.resolve(strict=True)
            if not resolved.is_file():
                return None
            if not any(resolved.is_relative_to(root) for root in self._allowed_roots):
                return None
            return str(resolved)
        except OSError:
            return None

    def _project_path(self, path: Path) -> ClaudeNativeTarget | None:
        match = _SOCKET_NAME.fullmatch(path.name)
        if match is None:
            return None
        pid = int(match.group(1))
        try:
            observed = path.lstat()
        except OSError:
            return None
        if (
            not stat.S_ISSOCK(observed.st_mode)
            or observed.st_uid != self._uid
            or stat.S_IMODE(observed.st_mode) != 0o600
        ):
            return None
        process = self._process_observer(pid)
        if (
            type(process) is not ClaudeProcessObservation
            or process.pid != pid
            or process.uid != self._uid
        ):
            return None
        executable = self._executable_allowed(process.executable)
        if executable is None:
            return None
        try:
            if str(Path(process.argv[0]).resolve(strict=True)) != executable:
                return None
        except OSError:
            return None
        metadata_present, metadata_session_id = _provider_session_id(
            pid, path, uid=self._uid, session_root=self._session_root
        )
        argv_session_id = _resume_session_id(process.argv)
        if metadata_present:
            if metadata_session_id is None:
                return None
            if argv_session_id is not None and argv_session_id != metadata_session_id:
                return None
            session_id = metadata_session_id
        else:
            session_id = argv_session_id
        if session_id is None:
            return None
        socket_path = str(path)
        identity = {
            "host_ref": self._host_ref,
            "session_id": session_id,
            "pid": pid,
            "process_start": process.process_start,
            "executable": executable,
            "socket_path": socket_path,
            "socket_device": int(observed.st_dev),
            "socket_inode": int(observed.st_ino),
            "socket_uid": int(observed.st_uid),
            "socket_mode": stat.S_IMODE(observed.st_mode),
        }
        digest = hashlib.sha256(_canonical_json(identity).encode("ascii")).hexdigest()
        return ClaudeNativeTarget(target_ref=f"claude:{digest}", **identity)

    def list_targets(self) -> list[ClaudeNativeTarget]:
        self._root_ready()
        try:
            entries = sorted(self._socket_root.iterdir(), key=lambda item: item.name)
        except OSError:
            raise BridgeError("native_unavailable", "Claude inbox root is unavailable") from None
        targets: list[ClaudeNativeTarget] = []
        seen: set[str] = set()
        for path in entries:
            target = self._project_path(path)
            if target is None:
                continue
            if target.target_ref in seen:
                raise BridgeError("native_unavailable", "Claude target projection is ambiguous")
            seen.add(target.target_ref)
            targets.append(target)
        return targets

    def resolve(self, target_ref: str) -> ClaudeNativeTarget:
        if not isinstance(target_ref, str) or not target_ref.startswith("claude:"):
            raise BridgeError("native_target_stale", "Claude target is no longer current")
        matches = [item for item in self.list_targets() if item.target_ref == target_ref]
        if len(matches) != 1:
            raise BridgeError("native_target_stale", "Claude target is no longer current")
        return matches[0]


class ClaudeNativeAttentionClient:
    """Write one supported same-machine Claude user frame to an exact target."""

    def __init__(
        self,
        projector: ClaudeNativeTargetProjector,
        *,
        target: ClaudeNativeTarget,
        timeout_seconds: float = 2.0,
        socket_factory: Callable[[], Any] | None = None,
    ) -> None:
        if type(projector) is not ClaudeNativeTargetProjector:
            raise TypeError("Claude native projector is required")
        if type(target) is not ClaudeNativeTarget:
            raise TypeError("exact Claude native target is required")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not 0.05 <= float(timeout_seconds) <= 30.0
        ):
            raise ValueError("Claude native timeout is out of range")
        self._projector = projector
        self._target = target
        self._timeout = float(timeout_seconds)
        self._socket_factory = socket_factory or (
            lambda: socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        )

    def _current_target(self) -> ClaudeNativeTarget:
        current = self._projector.resolve(self._target.target_ref)
        if current != self._target:
            raise BridgeError("native_target_stale", "Claude target is no longer current")
        return current

    def _frame(self, reference: AttentionReference) -> bytes:
        if type(reference) is not AttentionReference:
            raise BridgeError("invalid_input", "Claude attention reference is invalid")
        frame = {
            "type": "user",
            "message": {"role": "user", "content": _notice(reference)},
        }
        return (_canonical_json(frame) + "\n").encode("utf-8")

    def _send_sync(self, reference: AttentionReference) -> dict[str, Any]:
        target = self._current_target()
        raw = self._frame(reference)
        client = self._socket_factory()
        connected = False
        try:
            client.settimeout(self._timeout)
            try:
                client.connect(target.socket_path)
                connected = True
            except Exception:
                raise BridgeError(
                    "native_unavailable", "Claude native target did not accept a connection"
                ) from None

            # Re-resolve after connect but before any content write. If the
            # pathname/process generation changed in the connect race, closing
            # this connection is still a no-message effect.
            current = self._current_target()
            if current != target:
                raise BridgeError("native_target_stale", "Claude target changed before send")
            try:
                client.sendall(raw)
            except Exception:
                raise BridgeError(
                    "native_effect_unknown",
                    "Claude native attention outcome is unknown; reconcile the original operation",
                ) from None
        finally:
            try:
                client.close()
            except Exception:
                pass
        if not connected:
            raise BridgeError("native_unavailable", "Claude native target is unavailable")
        return {
            "state": "TRANSPORT_WRITTEN",
            "target_ref": target.target_ref,
            "session_id": target.session_id,
            "target_consumed": False,
            "parent_consumed": False,
        }

    async def deliver(self, reference: AttentionReference) -> dict[str, Any]:
        # Cancellation remains cancellation. The higher-level effect owner must
        # reconcile the original operation rather than assuming no write.
        return await asyncio.to_thread(self._send_sync, reference)


__all__ = [
    "ClaudeNativeAttentionClient",
    "ClaudeNativeTarget",
    "ClaudeNativeTargetProjector",
    "ClaudeProcessObservation",
    "observe_claude_process",
]
