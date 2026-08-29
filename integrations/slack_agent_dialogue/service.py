"""Command-scoped AF_UNIX service/client for Active-Session Dialogue.

The service owns no token, lifecycle state, queue, cursor, or background loop.
A caller composes it with an injected ``DialogueEngine`` for one bounded command
window, and closes it when that command finishes.
"""
from __future__ import annotations

import asyncio
import ctypes
import errno
import json
import os
import socket
import stat
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from integrations.slack_agent_dialogue.engine import (
    DialogueContext,
    DialogueEngine,
    DialogueEngineError,
    jsonable,
)
from integrations.slack_agent_dialogue.engine import ERROR_CODES as DialogueEngineErrorCodes
from integrations.slack_agent_dialogue.engine_v2 import DialogueContextV2, DialogueEngineV2

CONTROL_VERSION = "mastermind.agent_dialogue_control.v1"
CONTROL_VERSION_V2 = "mastermind.agent_dialogue_control.v2"
DEFAULT_MAX_REQUEST_BYTES = 32 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024

ERROR_CODES = frozenset(
    {
        "INTERNAL_ERROR",
        "PEER_CREDENTIALS_UNAVAILABLE",
        "PEER_DENIED",
        "REQUEST_INVALID",
        "REQUEST_TOO_LARGE",
        "RESPONSE_TOO_LARGE",
        "SERVICE_UNAVAILABLE",
    }
)
_CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)

# Filesystem AF_UNIX addresses must leave one byte for the terminating NUL in
# the target kernel's ``sockaddr_un.sun_path`` buffer. Validate the encoded
# path that Python passes to the kernel, not its character count.
AF_UNIX_PATH_MAX_BYTES = 107 if sys.platform.startswith("linux") else 103


class DialogueServiceError(RuntimeError):
    """One closed service/client refusal code."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES and code not in DialogueEngineErrorCodes:
            raise ValueError("unknown dialogue service error code")
        super().__init__(code)
        self.code = code


def _socket_path_is_target_valid(path: Path) -> bool:
    try:
        encoded = os.fsencode(path)
    except (TypeError, ValueError, UnicodeEncodeError):
        return False
    return b"\x00" not in encoded and len(encoded) <= AF_UNIX_PATH_MAX_BYTES


@dataclass(frozen=True)
class ServiceConfig:
    socket_path: Path
    allowed_peer_uids: tuple[int, ...]
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    request_timeout_seconds: float = 15.0
    socket_parent_mode: int = 0o700
    socket_mode: int = 0o600
    socket_group_gid: int | None = None

    def __post_init__(self) -> None:
        path = Path(self.socket_path)
        if not path.is_absolute():
            raise ValueError("socket_path must be absolute")
        if not _socket_path_is_target_valid(path):
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        try:
            path = path.resolve(strict=False)
        except (OSError, ValueError):
            raise DialogueServiceError("SERVICE_UNAVAILABLE") from None
        if not _socket_path_is_target_valid(path):
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        object.__setattr__(self, "socket_path", path)
        if (
            not isinstance(self.allowed_peer_uids, tuple)
            or not self.allowed_peer_uids
            or self.allowed_peer_uids != tuple(sorted(set(self.allowed_peer_uids)))
            or any(not isinstance(uid, int) or uid < 0 for uid in self.allowed_peer_uids)
        ):
            raise ValueError("allowed_peer_uids must be sorted unique non-negative integers")
        if not 1024 <= self.max_request_bytes <= 1024 * 1024:
            raise ValueError("max_request_bytes out of range")
        if not 4096 <= self.max_response_bytes <= 1024 * 1024:
            raise ValueError("max_response_bytes out of range")
        if not 0.1 <= self.request_timeout_seconds <= 120:
            raise ValueError("request_timeout_seconds out of range")
        private_modes = (
            self.socket_parent_mode == 0o700
            and self.socket_mode == 0o600
            and self.socket_group_gid is None
        )
        shared_modes = (
            self.socket_parent_mode == 0o710
            and self.socket_mode == 0o660
            and isinstance(self.socket_group_gid, int)
            and not isinstance(self.socket_group_gid, bool)
            and self.socket_group_gid >= 0
        )
        if not private_modes and not shared_modes:
            raise ValueError("socket reachability configuration is invalid")


def _peer_uid(connection: socket.socket) -> int | None:
    getpeereid = getattr(connection, "getpeereid", None)
    if callable(getpeereid):
        uid, _gid = getpeereid()
        return int(uid)
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        function = libc.getpeereid
        function.argtypes = [
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        function.restype = ctypes.c_int
        uid = ctypes.c_uint32()
        gid = ctypes.c_uint32()
        if function(connection.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        return int(uid.value)
    if hasattr(socket, "SO_PEERCRED"):
        size = struct.calcsize("3i")
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
        _pid, uid, _gid = struct.unpack("3i", raw)
        return int(uid)
    return None


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(
            jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DialogueServiceError("REQUEST_INVALID")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise DialogueServiceError("REQUEST_INVALID")


def _strict_json(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except DialogueServiceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise DialogueServiceError("REQUEST_INVALID") from None


def _exact_mapping(value: Any, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise DialogueServiceError("REQUEST_INVALID")
    return value


def _context(value: Any) -> DialogueContext:
    item = _exact_mapping(
        value, {"work_ref", "commission_ref", "session_ref", "applies_to"}
    )
    context = DialogueContext(
        work_ref=item["work_ref"],
        commission_ref=item["commission_ref"],
        session_ref=item["session_ref"],
        applies_to=item["applies_to"],
    )
    try:
        context.normalized()
    except Exception:
        raise DialogueServiceError("REQUEST_INVALID") from None
    return context


def _context_v2(value: Any) -> DialogueContextV2:
    item = _exact_mapping(
        value,
        {
            "work_ref",
            "commission_ref",
            "session_ref",
            "operation_key",
            "watch_mode",
            "actor_ref",
            "applies_to",
        },
    )
    context = DialogueContextV2(
        work_ref=item["work_ref"],
        commission_ref=item["commission_ref"],
        session_ref=item["session_ref"],
        operation_key=item["operation_key"],
        watch_mode=item["watch_mode"],
        actor_ref=item["actor_ref"],
        applies_to=item["applies_to"],
    )
    try:
        context.normalized()
    except Exception:
        raise DialogueServiceError("REQUEST_INVALID") from None
    return context


class AgentDialogueService:
    """Peer-authorized one-request-at-a-time service over injected engines."""

    def __init__(
        self,
        config: ServiceConfig,
        engine: DialogueEngine,
        *,
        engine_v2: DialogueEngineV2 | None = None,
    ) -> None:
        self.config = config
        self.engine = engine
        self.engine_v2 = engine_v2
        self._server: asyncio.AbstractServer | None = None
        self._bound_socket_identity: tuple[int, int] | None = None
        self._handled = asyncio.Event()

    def _prepare_socket(self) -> None:
        parent = self.config.socket_path.parent
        if self.config.socket_group_gid is None:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        else:
            created = False
            try:
                parent.mkdir(
                    mode=self.config.socket_parent_mode,
                    parents=True,
                    exist_ok=False,
                )
                created = True
            except FileExistsError:
                pass
            if created:
                parent.chmod(self.config.socket_parent_mode)
        info = parent.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.geteuid()
            or (
                self.config.socket_group_gid is not None
                and info.st_gid != self.config.socket_group_gid
            )
        ):
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        if self.config.socket_group_gid is None:
            parent.chmod(0o700)
        if stat.S_IMODE(parent.lstat().st_mode) != self.config.socket_parent_mode:
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        try:
            socket_info = self.config.socket_path.lstat()
        except FileNotFoundError:
            return
        if (
            not stat.S_ISSOCK(socket_info.st_mode)
            or socket_info.st_uid != os.geteuid()
            or (
                self.config.socket_group_gid is not None
                and (
                    socket_info.st_gid != self.config.socket_group_gid
                    or stat.S_IMODE(socket_info.st_mode) != self.config.socket_mode
                )
            )
        ):
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            result = probe.connect_ex(str(self.config.socket_path))
        finally:
            probe.close()
        if result == 0:
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        if result not in {errno.ECONNREFUSED, errno.ENOENT}:
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        self.config.socket_path.unlink(missing_ok=True)

    async def start(self) -> None:
        if self._server is not None or self._bound_socket_identity is not None:
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        path_prepared = False
        try:
            self._prepare_socket()
            path_prepared = True
            self._server = await asyncio.start_unix_server(
                self._handle_connection,
                path=str(self.config.socket_path),
                limit=self.config.max_request_bytes + 1,
            )
            bound_info = self.config.socket_path.lstat()
            if (
                not stat.S_ISSOCK(bound_info.st_mode)
                or bound_info.st_uid != os.geteuid()
                or (
                    self.config.socket_group_gid is not None
                    and bound_info.st_gid != self.config.socket_group_gid
                )
            ):
                raise DialogueServiceError("SERVICE_UNAVAILABLE")
            self._bound_socket_identity = (bound_info.st_dev, bound_info.st_ino)
            self.config.socket_path.chmod(self.config.socket_mode)
            socket_info = self.config.socket_path.lstat()
            if (
                (socket_info.st_dev, socket_info.st_ino)
                != self._bound_socket_identity
                or stat.S_IMODE(socket_info.st_mode) != self.config.socket_mode
            ):
                raise DialogueServiceError("SERVICE_UNAVAILABLE")
            if self.config.socket_group_gid is not None and (
                not stat.S_ISSOCK(socket_info.st_mode)
                or socket_info.st_uid != os.geteuid()
                or socket_info.st_gid != self.config.socket_group_gid
            ):
                raise DialogueServiceError("SERVICE_UNAVAILABLE")
        except DialogueServiceError:
            if path_prepared:
                await self.close()
            raise
        except Exception:
            if path_prepared:
                await self.close()
            raise DialogueServiceError("SERVICE_UNAVAILABLE") from None

    async def close(self) -> None:
        server = self._server
        bound_socket_identity = self._bound_socket_identity
        self._server = None
        self._bound_socket_identity = None
        if server is not None:
            server.close()
            await server.wait_closed()
        if bound_socket_identity is None:
            return
        try:
            info = self.config.socket_path.lstat()
        except (FileNotFoundError, OSError):
            return
        if (info.st_dev, info.st_ino) != bound_socket_identity:
            return
        owned_private_socket = (
            self.config.socket_group_gid is None
            and stat.S_ISSOCK(info.st_mode)
            and info.st_uid == os.geteuid()
        )
        owned_shared_socket = (
            self.config.socket_group_gid is not None
            and stat.S_ISSOCK(info.st_mode)
            and info.st_uid == os.geteuid()
            and info.st_gid == self.config.socket_group_gid
            and stat.S_IMODE(info.st_mode) == self.config.socket_mode
        )
        if owned_private_socket or owned_shared_socket:
            self.config.socket_path.unlink()

    async def serve_one(self) -> None:
        await self.start()
        try:
            await self._handled.wait()
        finally:
            await self.close()

    async def serve_forever(self) -> None:
        """Serve sequential callers until cancellation, then remove the socket."""

        await self.start()
        server = self._server
        if server is None:
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        try:
            await server.serve_forever()
        finally:
            await self.close()

    async def _send(self, writer: asyncio.StreamWriter, value: Mapping[str, Any]) -> None:
        payload = _canonical_json(value)
        if len(payload) > self.config.max_response_bytes:
            payload = _canonical_json(
                {"ok": False, "error": {"code": "RESPONSE_TOO_LARGE"}}
            )
        writer.write(payload)
        try:
            await writer.drain()
        except _CLIENT_GONE:
            pass

    async def _error(self, writer: asyncio.StreamWriter, code: str) -> None:
        allowed = ERROR_CODES | DialogueEngineErrorCodes
        safe = code if code in allowed else "INTERNAL_ERROR"
        await self._send(writer, {"ok": False, "error": {"code": safe}})

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            connection = writer.get_extra_info("socket")
            if connection is None:
                await self._error(writer, "PEER_CREDENTIALS_UNAVAILABLE")
                return
            try:
                peer = _peer_uid(connection)
            except OSError:
                await self._error(writer, "PEER_CREDENTIALS_UNAVAILABLE")
                return
            if peer is None:
                await self._error(writer, "PEER_CREDENTIALS_UNAVAILABLE")
                return
            if peer not in self.config.allowed_peer_uids:
                await self._error(writer, "PEER_DENIED")
                return
            try:
                raw = await asyncio.wait_for(
                    reader.readuntil(b"\n"),
                    timeout=self.config.request_timeout_seconds,
                )
            except asyncio.TimeoutError:
                await self._error(writer, "REQUEST_INVALID")
                return
            except asyncio.LimitOverrunError:
                await self._error(writer, "REQUEST_TOO_LARGE")
                return
            except asyncio.IncompleteReadError:
                await self._error(writer, "REQUEST_INVALID")
                return
            if len(raw) > self.config.max_request_bytes:
                await self._error(writer, "REQUEST_TOO_LARGE")
                return
            try:
                request = _strict_json(raw)
                result = await self._dispatch(request)
            except DialogueServiceError as exc:
                await self._error(writer, exc.code)
                return
            except DialogueEngineError as exc:
                await self._error(writer, exc.code)
                return
            except Exception:
                await self._error(writer, "INTERNAL_ERROR")
                return
            await self._send(writer, {"ok": True, "result": result})
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except _CLIENT_GONE:
                pass
            self._handled.set()

    async def _dispatch(self, request: Any) -> Any:
        item = _exact_mapping(request, {"version", "operation", "args"})
        if item["version"] == CONTROL_VERSION:
            return await self._dispatch_v1(item["operation"], item["args"])
        if item["version"] == CONTROL_VERSION_V2 and self.engine_v2 is not None:
            return await self._dispatch_v2(item["operation"], item["args"])
        raise DialogueServiceError("REQUEST_INVALID")

    async def _dispatch_v1(self, operation: Any, args: Any) -> Any:
        if not isinstance(operation, str) or not isinstance(args, dict):
            raise DialogueServiceError("REQUEST_INVALID")

        if operation == "status":
            _exact_mapping(args, set())
            return self.engine.status()
        if operation == "bind_or_verify_thread":
            values = _exact_mapping(args, {"context"})
            return self.engine_result(
                await self.engine.bind_or_verify_thread(_context(values["context"]))
            )
        if operation == "send_message":
            values = _exact_mapping(args, {"context", "thread_ts", "message"})
            if not isinstance(values["thread_ts"], str) or not isinstance(
                values["message"], dict
            ):
                raise DialogueServiceError("REQUEST_INVALID")
            return self.engine_result(
                await self.engine.send_message(
                    thread_ts=values["thread_ts"],
                    context=_context(values["context"]),
                    message=values["message"],
                )
            )
        if operation == "read_thread":
            values = _exact_mapping(args, {"context", "thread_ts"})
            if not isinstance(values["thread_ts"], str):
                raise DialogueServiceError("REQUEST_INVALID")
            return self.engine_result(
                await self.engine.read_thread(
                    thread_ts=values["thread_ts"],
                    context=_context(values["context"]),
                )
            )
        if operation == "wait_for_reply":
            values = _exact_mapping(
                args,
                {
                    "context",
                    "thread_ts",
                    "request_message_key",
                    "expected_types",
                    "max_attempts",
                },
            )
            if (
                not isinstance(values["thread_ts"], str)
                or not isinstance(values["request_message_key"], str)
                or not isinstance(values["expected_types"], list)
                or any(not isinstance(item, str) for item in values["expected_types"])
                or type(values["max_attempts"]) is not int
            ):
                raise DialogueServiceError("REQUEST_INVALID")
            return self.engine_result(
                await self.engine.wait_for_reply(
                    thread_ts=values["thread_ts"],
                    context=_context(values["context"]),
                    request_message_key=values["request_message_key"],
                    expected_types=values["expected_types"],
                    max_attempts=values["max_attempts"],
                )
            )
        raise DialogueServiceError("REQUEST_INVALID")

    async def _dispatch_v2(self, operation: Any, args: Any) -> Any:
        engine = self.engine_v2
        if engine is None or not isinstance(operation, str) or not isinstance(args, dict):
            raise DialogueServiceError("REQUEST_INVALID")

        if operation == "status":
            _exact_mapping(args, set())
            return engine.status()
        if operation == "bind_or_verify_thread":
            values = _exact_mapping(args, {"context"})
            return self.engine_result(
                await engine.bind_or_verify_thread(_context_v2(values["context"]))
            )
        if operation == "send_message":
            values = _exact_mapping(args, {"context", "thread_ts", "message"})
            if not isinstance(values["thread_ts"], str) or not isinstance(
                values["message"], dict
            ):
                raise DialogueServiceError("REQUEST_INVALID")
            return self.engine_result(
                await engine.send_message(
                    thread_ts=values["thread_ts"],
                    context=_context_v2(values["context"]),
                    message=values["message"],
                )
            )
        if operation == "read_thread":
            values = _exact_mapping(args, {"context", "thread_ts"})
            if not isinstance(values["thread_ts"], str):
                raise DialogueServiceError("REQUEST_INVALID")
            return self.engine_result(
                await engine.read_thread(
                    thread_ts=values["thread_ts"],
                    context=_context_v2(values["context"]),
                )
            )
        if operation == "wait_for_reply":
            values = _exact_mapping(
                args,
                {
                    "context",
                    "thread_ts",
                    "request_message_key",
                    "expected_types",
                    "max_attempts",
                },
            )
            if (
                not isinstance(values["thread_ts"], str)
                or not isinstance(values["request_message_key"], str)
                or not isinstance(values["expected_types"], list)
                or any(not isinstance(item, str) for item in values["expected_types"])
                or type(values["max_attempts"]) is not int
            ):
                raise DialogueServiceError("REQUEST_INVALID")
            return self.engine_result(
                await engine.wait_for_reply(
                    thread_ts=values["thread_ts"],
                    context=_context_v2(values["context"]),
                    request_message_key=values["request_message_key"],
                    expected_types=values["expected_types"],
                    max_attempts=values["max_attempts"],
                )
            )
        raise DialogueServiceError("REQUEST_INVALID")

    @staticmethod
    def engine_result(value: Any) -> Any:
        return jsonable(value)


async def call_service(
    socket_path: Path | str,
    request: Mapping[str, Any],
    *,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    path = Path(socket_path)
    if (
        not path.is_absolute()
        or not 4096 <= max_response_bytes <= 1024 * 1024
        or not 0.1 <= timeout_seconds <= 120
    ):
        raise DialogueServiceError("REQUEST_INVALID")
    if not _socket_path_is_target_valid(path):
        raise DialogueServiceError("SERVICE_UNAVAILABLE")
    payload = _canonical_json(request)
    if len(payload) > DEFAULT_MAX_REQUEST_BYTES:
        raise DialogueServiceError("REQUEST_TOO_LARGE")
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(
                str(path), limit=max_response_bytes + 1
            ),
            timeout=timeout_seconds,
        )
    except Exception:
        raise DialogueServiceError("SERVICE_UNAVAILABLE") from None
    try:
        writer.write(payload)
        await asyncio.wait_for(writer.drain(), timeout=timeout_seconds)
        try:
            raw = await asyncio.wait_for(
                reader.readuntil(b"\n"), timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            raise DialogueServiceError("SERVICE_UNAVAILABLE") from None
        except asyncio.LimitOverrunError:
            raise DialogueServiceError("RESPONSE_TOO_LARGE") from None
        except asyncio.IncompleteReadError:
            raise DialogueServiceError("SERVICE_UNAVAILABLE") from None
        if len(raw) > max_response_bytes:
            raise DialogueServiceError("RESPONSE_TOO_LARGE")
        response = _strict_json(raw)
        if not isinstance(response, dict):
            raise DialogueServiceError("SERVICE_UNAVAILABLE")
        if set(response) == {"ok", "result"}:
            if response["ok"] is not True:
                raise DialogueServiceError("SERVICE_UNAVAILABLE")
            return response
        if set(response) == {"ok", "error"}:
            error = response["error"]
            if (
                response["ok"] is not False
                or not isinstance(error, dict)
                or set(error) != {"code"}
                or error["code"] not in (ERROR_CODES | DialogueEngineErrorCodes)
            ):
                raise DialogueServiceError("SERVICE_UNAVAILABLE")
            return response
        raise DialogueServiceError("SERVICE_UNAVAILABLE")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except _CLIENT_GONE:
            pass


def client_main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--socket-path", required=True)
    namespace = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        raw = sys.stdin.buffer.read(DEFAULT_MAX_REQUEST_BYTES + 1)
        if not raw or len(raw) > DEFAULT_MAX_REQUEST_BYTES:
            raise DialogueServiceError("REQUEST_TOO_LARGE")
        request = _strict_json(raw)
        response = asyncio.run(call_service(namespace.socket_path, request))
        sys.stdout.buffer.write(_canonical_json(response))
        return 0 if response.get("ok") is True else 2
    except DialogueServiceError as exc:
        sys.stdout.buffer.write(
            _canonical_json({"ok": False, "error": {"code": exc.code}})
        )
        return 2
    except Exception:
        sys.stdout.buffer.write(
            _canonical_json({"ok": False, "error": {"code": "INTERNAL_ERROR"}})
        )
        return 2


__all__ = [
    "AF_UNIX_PATH_MAX_BYTES",
    "AgentDialogueService",
    "CONTROL_VERSION",
    "CONTROL_VERSION_V2",
    "DialogueServiceError",
    "ERROR_CODES",
    "ServiceConfig",
    "call_service",
    "client_main",
]
