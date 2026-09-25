"""One-resource Unix-socket relay over one pinned Playwright MCP stdio child.

The relay owns no organizational lifecycle or placement decision. Its caller
must already own a browser resource lease. One relay process owns one child MCP
process group and serializes calls for that resource. A signed browser_ref held
by the parent service is sufficient to rediscover the relay from OS process and
socket identity; this module intentionally has no global session registry.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import subprocess
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane.browser_resource_contract import (
    ALLOWED_BROWSER_TOOLS,
    WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
    BrowserMode,
)
from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest


RELAY_REQUEST_SCHEMA = "mastermind.workbench_browser_relay_request.v1"
RELAY_RESPONSE_SCHEMA = "mastermind.workbench_browser_relay_response.v1"
_MAX_LINE_BYTES = 16 * 1024 * 1024
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_TOOL = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


class BrowserRelayError(RuntimeError):
    """The owned browser relay cannot safely provide the requested operation."""


@dataclasses.dataclass(frozen=True)
class McpSessionReceipt:
    child_pid: int
    tool_schema_digest: str
    allowed_tools: tuple[str, ...]


def _strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise BrowserRelayError("duplicate JSON field")
            value[key] = item
        return value

    def constant(_value: str) -> None:
        raise BrowserRelayError("non-finite JSON number")

    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except BrowserRelayError:
        raise
    except Exception as error:
        raise BrowserRelayError("invalid JSON") from error


class McpStdioSession:
    """Minimal bounded MCP client for one already-selected stdio child."""

    def __init__(
        self,
        *,
        argv: Sequence[str],
        env: Mapping[str, str],
        allowed_tools: frozenset[str],
        expected_tool_schema_digest: str,
        rpc_timeout_seconds: float = 30.0,
    ) -> None:
        if (
            not isinstance(argv, Sequence)
            or isinstance(argv, (str, bytes))
            or not argv
            or any(type(item) is not str or not item for item in argv)
        ):
            raise BrowserRelayError("child argv is invalid")
        if type(env) is not dict or any(type(k) is not str or type(v) is not str for k, v in env.items()):
            raise BrowserRelayError("child environment is invalid")
        if (
            type(allowed_tools) is not frozenset
            or not allowed_tools
            or any(_TOOL.fullmatch(name) is None for name in allowed_tools)
        ):
            raise BrowserRelayError("allowed tool set is invalid")
        if (
            type(expected_tool_schema_digest) is not str
            or _HEX64.fullmatch(expected_tool_schema_digest) is None
        ):
            raise BrowserRelayError("expected tool schema digest is invalid")
        if not isinstance(rpc_timeout_seconds, (int, float)) or not 0 < rpc_timeout_seconds <= 120:
            raise BrowserRelayError("RPC timeout is invalid")
        self._argv = tuple(argv)
        self._env = dict(env)
        self._allowed_tools = allowed_tools
        self._expected_digest = expected_tool_schema_digest
        self._timeout = float(rpc_timeout_seconds)
        self._process: subprocess.Popen[bytes] | None = None
        self._next_id = 1
        self._buffer = b""
        self._receipt: McpSessionReceipt | None = None
        self._gate = threading.RLock()

    @property
    def receipt(self) -> McpSessionReceipt:
        if self._receipt is None:
            raise BrowserRelayError("MCP child is not initialized")
        return self._receipt

    def _send(self, value: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise BrowserRelayError("MCP child is unavailable")
        try:
            raw = json.dumps(
                value,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise BrowserRelayError("MCP request is not JSON-safe") from error
        if len(raw) > _MAX_LINE_BYTES:
            raise BrowserRelayError("MCP request is too large")
        try:
            process.stdin.write(raw + b"\n")
            process.stdin.flush()
        except OSError as error:
            raise BrowserRelayError("MCP child write failed") from error

    def _read_line(self, *, timeout: float) -> bytes:
        process = self._process
        if process is None or process.stdout is None:
            raise BrowserRelayError("MCP child is unavailable")
        deadline = time.monotonic() + timeout
        fd = process.stdout.fileno()
        while True:
            if b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                if len(line) > _MAX_LINE_BYTES:
                    raise BrowserRelayError("MCP response is too large")
                return line
            if len(self._buffer) > _MAX_LINE_BYTES:
                raise BrowserRelayError("MCP response is too large")
            if process.poll() is not None:
                raise BrowserRelayError("MCP child exited")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrowserRelayError("MCP child response timed out")
            readable, _, _ = select.select([fd], [], [], min(remaining, 0.25))
            if not readable:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError as error:
                raise BrowserRelayError("MCP child read failed") from error
            if not chunk:
                raise BrowserRelayError("MCP child closed stdout")
            self._buffer += chunk

    def _rpc(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": dict(params),
            }
        )
        deadline = time.monotonic() + self._timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrowserRelayError("MCP RPC timed out")
            value = _strict_json(self._read_line(timeout=remaining))
            if type(value) is not dict:
                raise BrowserRelayError("MCP response is invalid")
            if value.get("id") != request_id:
                # Notifications are allowed; a response for another request is
                # impossible because this session serializes all calls.
                if "id" not in value:
                    continue
                raise BrowserRelayError("MCP response identity changed")
            if value.get("jsonrpc") != "2.0":
                raise BrowserRelayError("MCP response protocol is invalid")
            if "error" in value:
                raise BrowserRelayError("MCP child returned a protocol error")
            result = value.get("result")
            if type(result) is not dict:
                raise BrowserRelayError("MCP result is invalid")
            return result

    def start(self) -> McpSessionReceipt:
        with self._gate:
            if self._process is not None:
                raise BrowserRelayError("MCP child already started")
            executable = self._argv[0]
            if not os.path.isabs(executable):
                raise BrowserRelayError("MCP executable must be absolute")
            try:
                self._process = subprocess.Popen(
                    list(self._argv),
                    cwd="/",
                    env=dict(self._env),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    close_fds=True,
                )
                initialize = self._rpc(
                    "initialize",
                    {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "mastermind-workbench-browser-relay",
                            "version": "1.0",
                        },
                    },
                )
                if (
                    type(initialize.get("protocolVersion")) is not str
                    or type(initialize.get("serverInfo")) is not dict
                ):
                    raise BrowserRelayError("MCP initialize response is invalid")
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {},
                    }
                )
                catalog = self._rpc("tools/list", {})
                rows = catalog.get("tools")
                if not isinstance(rows, list) or not rows:
                    raise BrowserRelayError("MCP tool catalog is invalid")
                by_name: dict[str, Mapping[str, Any]] = {}
                for row in rows:
                    if not isinstance(row, Mapping):
                        raise BrowserRelayError("MCP tool catalog is invalid")
                    name = row.get("name")
                    if type(name) is not str or _TOOL.fullmatch(name) is None or name in by_name:
                        raise BrowserRelayError("MCP tool catalog name is invalid")
                    by_name[name] = dict(row)
                if not self._allowed_tools <= set(by_name):
                    raise BrowserRelayError("MCP tool catalog lacks a granted tool")
                selected = {
                    "tools": {
                        name: by_name[name] for name in sorted(self._allowed_tools)
                    }
                }
                digest = observed_mcp_tool_schema_digest(selected)
                if digest != self._expected_digest:
                    raise BrowserRelayError("MCP tool schema drift")
                process = self._process
                if process is None or process.poll() is not None:
                    raise BrowserRelayError("MCP child exited during initialization")
                self._receipt = McpSessionReceipt(
                    child_pid=process.pid,
                    tool_schema_digest=digest,
                    allowed_tools=tuple(sorted(self._allowed_tools)),
                )
                return self._receipt
            except BaseException:
                self.close()
                raise

    def call(self, tool: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        with self._gate:
            if self._receipt is None:
                raise BrowserRelayError("MCP child is not initialized")
            if tool not in self._allowed_tools:
                raise BrowserRelayError("browser tool is not granted")
            if type(arguments) is not dict:
                raise BrowserRelayError("browser tool arguments must be an object")
            return self._rpc(
                "tools/call",
                {"name": tool, "arguments": dict(arguments)},
            )

    def close(self) -> None:
        with self._gate:
            process = self._process
            self._process = None
            self._receipt = None
            if process is None:
                return
            cleanup_error: BaseException | None = None
            if process.poll() is None:
                # The relay itself is the owner process-group leader. The MCP
                # child intentionally remains in that same group so host-owner
                # retirement can fence relay, Node and browser descendants with
                # one exact process-group identity. Here we terminate only the
                # direct child; external resource cleanup owns group fencing.
                try:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                except ProcessLookupError:
                    pass
                except BaseException as error:
                    cleanup_error = error
                    try:
                        process.kill()
                        process.wait(timeout=2)
                    except BaseException:
                        pass
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError as error:
                        cleanup_error = cleanup_error or error
            if cleanup_error is not None:
                raise BrowserRelayError("MCP child cleanup was uncertain") from cleanup_error


class BrowserRelayServer:
    """One Unix socket and one MCP child for one exact browser resource."""

    def __init__(
        self,
        *,
        resource_id: str,
        socket_path: Path,
        session: McpStdioSession,
    ) -> None:
        if type(resource_id) is not str or _HEX32.fullmatch(resource_id) is None:
            raise BrowserRelayError("resource identity is invalid")
        if not isinstance(socket_path, Path) or not socket_path.is_absolute():
            raise BrowserRelayError("relay socket path is invalid")
        try:
            encoded_socket = os.fsencode(socket_path)
        except (TypeError, UnicodeError, ValueError) as error:
            raise BrowserRelayError("relay socket path is invalid") from error
        if len(encoded_socket) >= 104:
            raise BrowserRelayError("relay socket path is too long")
        if not isinstance(session, McpStdioSession):
            raise BrowserRelayError("relay MCP session is invalid")
        self._resource_id = resource_id
        self._socket_path = socket_path
        self._session = session
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._server: socket.socket | None = None
        self._serve_error: BaseException | None = None
        self._socket_identity: tuple[int, int] | None = None

    def _validate_parent(self) -> None:
        parent = self._socket_path.parent
        try:
            info = parent.lstat()
        except OSError as error:
            raise BrowserRelayError("relay socket parent is unavailable") from error
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise BrowserRelayError("relay socket parent is unsafe")
        if os.path.lexists(self._socket_path):
            raise BrowserRelayError("relay socket path already exists")

    def wait_ready(self, *, timeout: float) -> None:
        if not self._ready.wait(timeout):
            raise BrowserRelayError("relay readiness timed out")
        if self._serve_error is not None:
            raise BrowserRelayError("relay failed before readiness") from self._serve_error

    def stop(self) -> None:
        self._stop.set()

    def _response(
        self,
        *,
        request_id: str,
        ok: bool,
        **values: Any,
    ) -> dict[str, Any]:
        return {
            "schema": RELAY_RESPONSE_SCHEMA,
            "request_id": request_id,
            "resource_id": self._resource_id,
            "ok": ok,
            **values,
        }

    def _handle(self, value: object) -> dict[str, Any]:
        if type(value) is not dict:
            raise BrowserRelayError("relay request is invalid")
        schema = value.get("schema")
        kind = value.get("kind")
        request_id = value.get("request_id")
        resource_id = value.get("resource_id")
        if (
            schema != RELAY_REQUEST_SCHEMA
            or type(request_id) is not str
            or _HEX32.fullmatch(request_id) is None
            or type(resource_id) is not str
            or _HEX32.fullmatch(resource_id) is None
        ):
            raise BrowserRelayError("relay request is invalid")
        if resource_id != self._resource_id:
            return self._response(
                request_id=request_id,
                ok=False,
                error="RESOURCE_MISMATCH",
            )
        if kind == "status":
            if set(value) != {"schema", "kind", "request_id", "resource_id"}:
                raise BrowserRelayError("relay status request is invalid")
            receipt = self._session.receipt
            return self._response(
                request_id=request_id,
                ok=True,
                tool_schema_digest=receipt.tool_schema_digest,
                allowed_tools=list(receipt.allowed_tools),
                child_pid=receipt.child_pid,
            )
        if kind == "tool":
            if set(value) != {
                "schema",
                "kind",
                "request_id",
                "resource_id",
                "tool",
                "arguments",
            }:
                raise BrowserRelayError("relay tool request is invalid")
            tool = value.get("tool")
            arguments = value.get("arguments")
            if type(tool) is not str or type(arguments) is not dict:
                raise BrowserRelayError("relay tool request is invalid")
            try:
                result = self._session.call(tool, arguments)
            except BrowserRelayError:
                # Once the MCP child call begins, request bytes may already have
                # crossed the browser-effect boundary. A missing/invalid reply
                # can never be downgraded to a pre-dispatch refusal.
                return self._response(
                    request_id=request_id,
                    ok=False,
                    error="EFFECT_UNKNOWN",
                )
            return self._response(
                request_id=request_id,
                ok=True,
                result=dict(result),
            )
        raise BrowserRelayError("relay request kind is invalid")

    def _read_request(self, connection: socket.socket) -> object:
        data = b""
        while b"\n" not in data:
            chunk = connection.recv(65536)
            if not chunk:
                raise BrowserRelayError("relay request ended before newline")
            data += chunk
            if len(data) > _MAX_LINE_BYTES:
                raise BrowserRelayError("relay request is too large")
        line, extra = data.split(b"\n", 1)
        if extra:
            raise BrowserRelayError("relay accepts one request per connection")
        return _strict_json(line)

    def _write_response(self, connection: socket.socket, value: Mapping[str, Any]) -> None:
        raw = json.dumps(
            value,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(raw) > _MAX_LINE_BYTES:
            raise BrowserRelayError("relay response is too large")
        connection.sendall(raw + b"\n")

    def serve_forever(self) -> None:
        server: socket.socket | None = None
        try:
            self._validate_parent()
            self._session.start()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(self._socket_path))
            os.chmod(self._socket_path, 0o600)
            info = self._socket_path.lstat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.geteuid():
                raise BrowserRelayError("relay socket identity is invalid")
            self._socket_identity = (info.st_dev, info.st_ino)
            server.listen(8)
            server.settimeout(0.2)
            self._server = server
            self._ready.set()
            while not self._stop.is_set():
                try:
                    connection, _ = server.accept()
                except socket.timeout:
                    continue
                with connection:
                    connection.settimeout(5)
                    request_id = "0" * 32
                    try:
                        value = self._read_request(connection)
                        if type(value) is dict and type(value.get("request_id")) is str:
                            request_id = value["request_id"]
                        response = self._handle(value)
                    except BrowserRelayError:
                        response = self._response(
                            request_id=request_id
                            if _HEX32.fullmatch(request_id or "") is not None
                            else "0" * 32,
                            ok=False,
                            error="REQUEST_REFUSED",
                        )
                    self._write_response(connection, response)
        except BaseException as error:
            self._serve_error = error
            self._ready.set()
            raise
        finally:
            self._server = None
            if server is not None:
                try:
                    server.close()
                except OSError:
                    pass
            try:
                self._session.close()
            finally:
                identity = self._socket_identity
                if identity is not None:
                    try:
                        current = self._socket_path.lstat()
                        if (current.st_dev, current.st_ino) == identity and stat.S_ISSOCK(current.st_mode):
                            self._socket_path.unlink()
                    except FileNotFoundError:
                        pass
                self._socket_identity = None
                self._ready.set()


def relay_request(
    socket_path: Path,
    request: Mapping[str, Any],
    *,
    timeout: float,
) -> dict[str, Any]:
    if not isinstance(socket_path, Path) or not socket_path.is_absolute():
        raise BrowserRelayError("relay socket path is invalid")
    if not isinstance(request, Mapping):
        raise BrowserRelayError("relay request is invalid")
    try:
        raw = json.dumps(
            dict(request),
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise BrowserRelayError("relay request is not JSON-safe") from error
    if len(raw) > _MAX_LINE_BYTES:
        raise BrowserRelayError("relay request is too large")
    data = b""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(socket_path))
            client.sendall(raw + b"\n")
            while b"\n" not in data:
                chunk = client.recv(65536)
                if not chunk:
                    raise BrowserRelayError("relay closed before response")
                data += chunk
                if len(data) > _MAX_LINE_BYTES:
                    raise BrowserRelayError("relay response is too large")
    except BrowserRelayError:
        raise
    except OSError as error:
        raise BrowserRelayError("relay transport failed") from error
    line, extra = data.split(b"\n", 1)
    if extra:
        raise BrowserRelayError("relay returned multiple responses")
    value = _strict_json(line)
    if type(value) is not dict or value.get("schema") != RELAY_RESPONSE_SCHEMA:
        raise BrowserRelayError("relay response is invalid")
    return value


def _absolute_cli_path(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
        raise BrowserRelayError(f"{name} must be absolute")
    selected = Path(value)
    if ".." in selected.parts or str(selected) != value.rstrip("/"):
        raise BrowserRelayError(f"{name} is not normalized")
    return value


def playwright_child_argv(
    *,
    node_executable: str,
    mcp_cli_path: str,
    chrome_executable: str,
    output_dir: str,
    mode: str,
    profile_dir: str | None,
) -> tuple[str, ...]:
    node_executable = _absolute_cli_path(node_executable, "node_executable")
    mcp_cli_path = _absolute_cli_path(mcp_cli_path, "mcp_cli_path")
    chrome_executable = _absolute_cli_path(chrome_executable, "chrome_executable")
    output_dir = _absolute_cli_path(output_dir, "output_dir")
    if not mcp_cli_path.endswith("/node_modules/@playwright/mcp/cli.js"):
        raise BrowserRelayError("unexpected Playwright MCP entrypoint")
    if mode not in {BrowserMode.ISOLATED.value, BrowserMode.PERSISTENT.value}:
        raise BrowserRelayError("browser mode is invalid")
    argv = [
        node_executable,
        mcp_cli_path,
        "--browser",
        "chrome",
        "--executable-path",
        chrome_executable,
        "--output-dir",
        output_dir,
        "--headless",
    ]
    if mode == BrowserMode.ISOLATED.value:
        if profile_dir is not None:
            raise BrowserRelayError("isolated relay cannot bind a profile directory")
        argv.append("--isolated")
    else:
        if profile_dir is None:
            raise BrowserRelayError("persistent relay requires a profile directory")
        argv.extend(("--user-data-dir", _absolute_cli_path(profile_dir, "profile_dir")))
    forbidden = {"--shared-browser-context", "--cdp-endpoint", "--extension"}
    if forbidden.intersection(argv):
        raise BrowserRelayError("unsafe shared or attached browser requested")
    return tuple(argv)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mastermind one-resource browser relay")
    parser.add_argument("--resource-id", required=True)
    parser.add_argument("--socket-path", required=True)
    parser.add_argument("--node-executable", required=True)
    parser.add_argument("--mcp-cli-path", required=True)
    parser.add_argument("--chrome-executable", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", choices=[BrowserMode.ISOLATED.value, BrowserMode.PERSISTENT.value], required=True)
    parser.add_argument("--profile-dir")
    parser.add_argument("--home-dir", required=True)
    parser.add_argument("--tmp-dir", required=True)
    parser.add_argument("--barrier-fd", type=int, required=True)
    args = parser.parse_args(argv)

    if _HEX32.fullmatch(args.resource_id) is None:
        raise BrowserRelayError("resource identity is invalid")
    socket_path = Path(_absolute_cli_path(args.socket_path, "socket_path"))
    home_dir = _absolute_cli_path(args.home_dir, "home_dir")
    tmp_dir = _absolute_cli_path(args.tmp_dir, "tmp_dir")
    child_argv = playwright_child_argv(
        node_executable=args.node_executable,
        mcp_cli_path=args.mcp_cli_path,
        chrome_executable=args.chrome_executable,
        output_dir=args.output_dir,
        mode=args.mode,
        profile_dir=args.profile_dir,
    )
    if args.barrier_fd < 3:
        raise BrowserRelayError("launch barrier descriptor is invalid")
    try:
        barrier = os.read(args.barrier_fd, 1)
    finally:
        os.close(args.barrier_fd)
    if barrier != b"\x01":
        raise BrowserRelayError("launch barrier was not released")

    session = McpStdioSession(
        argv=child_argv,
        env={
            "HOME": home_dir,
            "TMPDIR": tmp_dir,
            "LANG": "C",
            "LC_ALL": "C",
            "NO_COLOR": "1",
            "PATH": "/usr/bin:/bin",
        },
        allowed_tools=ALLOWED_BROWSER_TOOLS,
        expected_tool_schema_digest=WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
    )
    relay = BrowserRelayServer(
        resource_id=args.resource_id,
        socket_path=socket_path,
        session=session,
    )
    previous: dict[int, Any] = {}

    def stop_handler(_signum: int, _frame: object) -> None:
        relay.stop()

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, stop_handler)
    try:
        relay.serve_forever()
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by host canary
    raise SystemExit(main())


__all__ = [
    "RELAY_REQUEST_SCHEMA",
    "RELAY_RESPONSE_SCHEMA",
    "BrowserRelayError",
    "BrowserRelayServer",
    "McpSessionReceipt",
    "McpStdioSession",
    "playwright_child_argv",
    "relay_request",
]
