"""Bounded Worker Browser B1 runner for the local Chairman Control Room.

This module is deliberately a resource adapter, not a lifecycle.  A caller
may request exactly one review of the already-running, exact loopback Control
Room origin.  The runner owns a fresh isolated Playwright MCP process group,
collects two fixed viewport screenshots plus bounded structured evidence, and
does not report success until the process group is proven absent.
"""
from __future__ import annotations

import hashlib
import json
import os
import select
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp"
PLAYWRIGHT_MCP_VERSION = "0.0.79"
DEFAULT_RUNTIME_ROOT = Path("/Volumes/Mastermind/worker-browser-b1/runtime")
DEFAULT_ARTIFACT_ROOT = Path("/Volumes/Mastermind/worker-browser-b1/artifacts")
RECEIPT_SCHEMA = "mastermind.worker_browser_b1.receipt.v1"

ALLOWED_TOOLS = frozenset(
    {
        "browser_close",
        "browser_console_messages",
        "browser_navigate",
        "browser_network_requests",
        "browser_resize",
        "browser_snapshot",
        "browser_take_screenshot",
    }
)

_DESKTOP = {"width": 1440, "height": 900}
_MOBILE = {"width": 390, "height": 844}
_MAX_PROTOCOL_LINE_BYTES = 4 * 1024 * 1024
MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
_CLEANUP_GRACE_SECONDS = 3.0
_CLEANUP_PROOF_SECONDS = 3.0


class BrowserReviewError(RuntimeError):
    """A typed, sanitized B1 failure."""

    def __init__(self, state: str, detail: str):
        super().__init__(detail)
        self.state = state
        self.detail = detail


@dataclass(frozen=True)
class BrowserRunConfig:
    origin: str
    repo_root: Path
    runtime_root: Path = DEFAULT_RUNTIME_ROOT
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    command_override: tuple[str, ...] | None = None
    timeout_seconds: float = 90.0
    max_text_bytes: int = 64 * 1024


def validate_request(data: dict[str, Any]) -> None:
    """Accept the one closed request shape: an empty JSON object."""
    if not isinstance(data, dict):
        raise ValueError("request body must be a JSON object")
    if data:
        key = next(iter(data))
        raise ValueError(f"unknown key: {key!r}")


def _validate_origin(origin: str) -> None:
    parsed = urlsplit(origin)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("origin must be an exact loopback origin") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("",)
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("origin must be an exact loopback origin")


def build_mcp_argv(config: BrowserRunConfig, output_dir: Path) -> list[str]:
    """Build the immutable official-MCP launch envelope."""
    command = list(config.command_override or (
        os.fspath(config.runtime_root / "node_modules" / ".bin" / "playwright-mcp"),
    ))
    return command + [
        "--isolated",
        "--headless",
        "--browser",
        "chrome",
        "--sandbox",
        "--block-service-workers",
        "--image-responses",
        "allow",
        "--allowed-origins",
        config.origin,
        "--output-dir",
        os.fspath(output_dir),
    ]


def _bounded_text(value: str, limit: int) -> str:
    raw = value.encode("utf-8", errors="replace")
    if len(raw) <= limit:
        return value
    return raw[:limit].decode("utf-8", errors="ignore")


def _content_text(result: dict[str, Any]) -> str:
    parts: list[str] = []
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "\n".join(parts)


def _secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    current = path.stat()
    if not stat.S_ISDIR(current.st_mode) or current.st_uid != os.getuid():
        raise BrowserReviewError("ARTIFACT_ROOT_REFUSED", "artifact root is not an owned directory")
    if stat.S_IMODE(current.st_mode) != 0o700:
        raise BrowserReviewError("ARTIFACT_ROOT_REFUSED", "artifact root mode is not 0700")


def _workspace_identity(repo_root: Path) -> tuple[str | None, bool]:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        status_out = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        return head, not bool(status_out.strip())
    except (OSError, subprocess.SubprocessError):
        # Hermetic consumers may provide an immutable non-Git fixture root.
        return None, True


class _JsonLineMcpClient:
    def __init__(self, process: subprocess.Popen[bytes], *, timeout_seconds: float):
        if process.stdin is None or process.stdout is None:
            raise BrowserReviewError("MCP_START_FAILED", "MCP stdio pipes are unavailable")
        self._process = process
        self._stdin = process.stdin
        self._stdout = process.stdout
        self._timeout = timeout_seconds
        self._next_id = 1
        self._buffer = bytearray()

    def _send(self, payload: dict[str, Any]) -> None:
        try:
            self._stdin.write(json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n")
            self._stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise BrowserReviewError("MCP_PROTOCOL_FAILED", "MCP stdio closed before request completion") from exc

    def _read_message(self, deadline: float) -> dict[str, Any]:
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                raw = bytes(self._buffer[:newline])
                del self._buffer[: newline + 1]
                if not raw:
                    continue
                try:
                    value = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError) as exc:
                    raise BrowserReviewError("MCP_PROTOCOL_FAILED", "MCP returned malformed JSON") from exc
                if not isinstance(value, dict):
                    raise BrowserReviewError("MCP_PROTOCOL_FAILED", "MCP returned a non-object message")
                return value

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrowserReviewError("MCP_TIMEOUT", "MCP response timed out")
            ready, _write, _errors = select.select([self._stdout], [], [], remaining)
            if not ready:
                raise BrowserReviewError("MCP_TIMEOUT", "MCP response timed out")
            chunk = os.read(self._stdout.fileno(), 65536)
            if not chunk:
                raise BrowserReviewError("MCP_PROTOCOL_FAILED", "MCP stdout closed before response completion")
            self._buffer.extend(chunk)
            if len(self._buffer) > _MAX_PROTOCOL_LINE_BYTES:
                raise BrowserReviewError("MCP_PROTOCOL_FAILED", "MCP response exceeded the protocol bound")

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self._timeout
        while True:
            response = self._read_message(deadline)
            if response.get("id") != request_id:
                # Playwright may emit legal notifications while a call is in flight.
                if "id" not in response and isinstance(response.get("method"), str):
                    continue
                raise BrowserReviewError("MCP_PROTOCOL_FAILED", "MCP response id did not match the request")
            if "error" in response:
                raise BrowserReviewError("MCP_TOOL_FAILED", f"MCP {method} returned an error")
            result = response.get("result")
            if not isinstance(result, dict):
                raise BrowserReviewError("MCP_PROTOCOL_FAILED", "MCP response result was not an object")
            return result

    def notify_initialized(self) -> None:
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in ALLOWED_TOOLS:
            raise BrowserReviewError("MCP_TOOL_REFUSED", "tool is outside the Worker Browser B1 allowlist")
        return self.request("tools/call", {"name": name, "arguments": arguments})


def _process_group_absent(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _finish_process_group(process: subprocess.Popen[bytes], pgid: int) -> bool:
    if process.stdin is not None:
        try:
            process.stdin.close()
        except OSError:
            pass
    if process.poll() is None:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=_CLEANUP_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=_CLEANUP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            return False

    deadline = time.monotonic() + _CLEANUP_PROOF_SECONDS
    while not _process_group_absent(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)
    return True


def _cleanup_run_directories(output_dir: Path) -> bool:
    """Remove disposable HOME/profile directories after group-death proof."""
    try:
        root = output_dir.resolve(strict=True)
        for child in output_dir.iterdir():
            if child.is_symlink():
                return False
            if child.is_dir():
                resolved = child.resolve(strict=True)
                if resolved.parent != root:
                    return False
                shutil.rmtree(resolved)
        return not any(path.is_dir() for path in output_dir.iterdir())
    except OSError:
        return False


def _screenshot_receipt(output_dir: Path, filename: str, viewport: dict[str, int]) -> dict[str, Any]:
    path = output_dir / filename
    try:
        resolved = path.resolve(strict=True)
        root = output_dir.resolve(strict=True)
        info = resolved.stat()
    except OSError as exc:
        raise BrowserReviewError("SCREENSHOT_MISSING", f"{filename} was not produced") from exc
    if resolved.parent != root or not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise BrowserReviewError("SCREENSHOT_REFUSED", f"{filename} is not a direct regular artifact")
    if info.st_size <= 0 or info.st_size > MAX_SCREENSHOT_BYTES:
        raise BrowserReviewError(
            "SCREENSHOT_OVERSIZE",
            "screenshot evidence size is outside the reviewed bound",
        )
    raw = resolved.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise BrowserReviewError("SCREENSHOT_REFUSED", f"{filename} is not a PNG")
    return {
        "name": filename,
        "viewport": dict(viewport),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _failure_receipt(
    state: str,
    detail: str,
    *,
    cleanup_absent: bool | None = None,
    profile_absent: bool | None = None,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "ok": False,
        "state": state,
        "detail": detail,
    }
    if cleanup_absent is not None:
        receipt["cleanup"] = {"process_group_absent": cleanup_absent}
        if profile_absent is not None:
            receipt["cleanup"]["profile_absent"] = profile_absent
    return receipt


def run_browser_review(config: BrowserRunConfig) -> dict[str, Any]:
    """Run one isolated B1 review and return a terminal sanitized receipt."""
    _validate_origin(config.origin)
    if config.timeout_seconds <= 0 or config.max_text_bytes <= 0:
        raise ValueError("timeouts and evidence bounds must be positive")
    runtime_binary = config.runtime_root / "node_modules" / ".bin" / "playwright-mcp"
    if config.command_override is None and (not runtime_binary.is_file() or not os.access(runtime_binary, os.X_OK)):
        return _failure_receipt(
            "RUNTIME_UNAVAILABLE",
            f"pinned {PLAYWRIGHT_MCP_PACKAGE}@{PLAYWRIGHT_MCP_VERSION} runtime is not installed",
        )
    head_before, clean_before = _workspace_identity(config.repo_root)
    if not clean_before:
        return _failure_receipt("WORKSPACE_DIRTY", "tracked workspace was dirty before browser review")

    _secure_directory(config.artifact_root)
    output_dir = Path(tempfile.mkdtemp(prefix="review-", dir=config.artifact_root))
    output_dir.chmod(0o700)
    private_home = output_dir / "home"
    _secure_directory(private_home)
    stderr_path = output_dir / "mcp.stderr"

    argv = build_mcp_argv(config, output_dir)
    safe_env = {
        "HOME": os.fspath(private_home),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "en_US.UTF-8"),
        "NO_COLOR": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "TMPDIR": os.fspath(output_dir),
    }
    process: subprocess.Popen[bytes] | None = None
    pgid: int | None = None
    browser_close_requested = False
    error: BrowserReviewError | None = None
    snapshot = console = network = ""
    screenshots: list[dict[str, Any]] = []

    try:
        with stderr_path.open("wb") as stderr_file:
            try:
                process = subprocess.Popen(
                    argv,
                    cwd=output_dir,
                    env=safe_env,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=stderr_file,
                    shell=False,
                    start_new_session=True,
                    bufsize=0,
                )
            except OSError as exc:
                raise BrowserReviewError("RUNTIME_UNAVAILABLE", "pinned Playwright MCP could not start") from exc
            pgid = os.getpgid(process.pid)
            client = _JsonLineMcpClient(process, timeout_seconds=config.timeout_seconds)
            initialized = client.request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "mastermind-worker-browser-b1", "version": "1"},
                },
            )
            server_info = initialized.get("serverInfo")
            if not isinstance(server_info, dict) or server_info.get("name") != "Playwright":
                raise BrowserReviewError("MCP_IDENTITY_REFUSED", "MCP server did not identify as Playwright")
            client.notify_initialized()
            tools = client.request("tools/list", {}).get("tools")
            advertised = {
                row.get("name") for row in tools or [] if isinstance(row, dict) and isinstance(row.get("name"), str)
            }
            missing = ALLOWED_TOOLS - advertised
            if missing:
                raise BrowserReviewError("MCP_TOOLSET_INCOMPLETE", "pinned MCP is missing a required B1 tool")

            client.call_tool("browser_navigate", {"url": config.origin})
            snapshot = _bounded_text(_content_text(client.call_tool("browser_snapshot", {})), config.max_text_bytes)
            console = _bounded_text(
                _content_text(client.call_tool("browser_console_messages", {"level": "warning", "all": True})),
                config.max_text_bytes,
            )
            network = _bounded_text(
                _content_text(client.call_tool("browser_network_requests", {"static": True})),
                config.max_text_bytes,
            )
            client.call_tool("browser_resize", dict(_DESKTOP))
            client.call_tool(
                "browser_take_screenshot",
                {"filename": "desktop.png", "fullPage": True, "scale": "css", "type": "png"},
            )
            client.call_tool("browser_resize", dict(_MOBILE))
            client.call_tool(
                "browser_take_screenshot",
                {"filename": "mobile.png", "fullPage": True, "scale": "css", "type": "png"},
            )
            screenshots = [
                _screenshot_receipt(output_dir, "desktop.png", _DESKTOP),
                _screenshot_receipt(output_dir, "mobile.png", _MOBILE),
            ]
            client.call_tool("browser_close", {})
            browser_close_requested = True
    except BrowserReviewError as exc:
        error = exc
    except Exception as exc:  # noqa: BLE001 - sanitize all runtime failures
        error = BrowserReviewError("BROWSER_REVIEW_FAILED", exc.__class__.__name__)

    process_group_absent = True
    if process is not None and pgid is not None:
        process_group_absent = _finish_process_group(process, pgid)
    profile_absent = process_group_absent and _cleanup_run_directories(output_dir)
    head_after, clean_after = _workspace_identity(config.repo_root)
    workspace_clean = clean_after and head_after == head_before

    if not process_group_absent:
        return _failure_receipt(
            "CLEANUP_UNCERTAIN",
            "the browser process group is not proven absent",
            cleanup_absent=False,
            profile_absent=False,
        )
    if not profile_absent:
        return _failure_receipt(
            "CLEANUP_UNCERTAIN",
            "the disposable browser profile is not proven absent",
            cleanup_absent=True,
            profile_absent=False,
        )
    if error is not None:
        return _failure_receipt(
            error.state,
            error.detail,
            cleanup_absent=True,
            profile_absent=True,
        )
    if not workspace_clean:
        return _failure_receipt(
            "WORKSPACE_MUTATED",
            "tracked workspace identity changed during browser review",
            cleanup_absent=True,
            profile_absent=True,
        )
    return {
        "schema": RECEIPT_SCHEMA,
        "ok": True,
        "state": "COMPLETE",
        "origin": config.origin,
        "workspace": {"head": head_before},
        "runtime": {"package": PLAYWRIGHT_MCP_PACKAGE, "version": PLAYWRIGHT_MCP_VERSION},
        "evidence": {"snapshot": snapshot, "console": console, "network": network},
        "screenshots": screenshots,
        "artifact_dir": os.fspath(output_dir),
        "cleanup": {
            "browser_close_requested": browser_close_requested,
            "process_group_absent": True,
            "profile_absent": True,
            "workspace_clean": True,
        },
    }


class BrowserReviewCoordinator:
    """Process-memory single-flight and cleanup interlock for B1."""

    def __init__(
        self,
        config: BrowserRunConfig,
        *,
        run_fn: Callable[[BrowserRunConfig], dict[str, Any]] = run_browser_review,
    ) -> None:
        _validate_origin(config.origin)
        self._config = config
        self._run_fn = run_fn
        self._lock = threading.Lock()
        self._in_flight = False
        self._cleanup_uncertain = False
        self._latest: dict[str, Any] | None = None

    def run(self) -> dict[str, Any]:
        with self._lock:
            if self._cleanup_uncertain:
                return _failure_receipt(
                    "BLOCKED_CLEANUP_UNCERTAIN",
                    "the prior browser process group is not proven absent",
                )
            if self._in_flight:
                return _failure_receipt("BUSY", "one browser review is already running")
            self._in_flight = True
        try:
            receipt = self._run_fn(self._config)
        except Exception as exc:  # noqa: BLE001 - coordinator is an API boundary
            receipt = _failure_receipt("BROWSER_REVIEW_FAILED", exc.__class__.__name__)
        with self._lock:
            self._in_flight = False
            self._latest = json.loads(json.dumps(receipt))
            cleanup = receipt.get("cleanup")
            if isinstance(cleanup, dict) and cleanup.get("process_group_absent") is False:
                self._cleanup_uncertain = True
            return json.loads(json.dumps(receipt))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            if self._in_flight:
                return {
                    "schema": RECEIPT_SCHEMA,
                    "ok": False,
                    "state": "RUNNING",
                    "detail": "one browser review is running",
                }
            if self._latest is None:
                return {
                    "schema": RECEIPT_SCHEMA,
                    "ok": False,
                    "state": "NOT_RUN",
                    "detail": "no browser review has run in this process",
                }
            return json.loads(json.dumps(self._latest))

    def read_artifact(self, name: str) -> bytes | None:
        if name not in {"desktop.png", "mobile.png"}:
            return None
        with self._lock:
            latest = json.loads(json.dumps(self._latest)) if self._latest is not None else None
        if not latest or latest.get("state") != "COMPLETE":
            return None
        artifact_dir = latest.get("artifact_dir")
        if not isinstance(artifact_dir, str):
            return None
        path = Path(artifact_dir) / name
        try:
            resolved = path.resolve(strict=True)
            root = Path(artifact_dir).resolve(strict=True)
            if resolved.parent != root or path.is_symlink() or not stat.S_ISREG(resolved.stat().st_mode):
                return None
            return resolved.read_bytes()
        except OSError:
            return None
