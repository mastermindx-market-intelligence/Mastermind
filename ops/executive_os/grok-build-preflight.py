"""Provider-work-free Grok Build OAuth/ACP preflight.

This probe attests one exact local Grok Build executable, validates its version
output internally, speaks only ACP initialize/authenticate, and proves whether
the provider-owned cached OAuth method can authenticate. It never creates an
ACP model session or any Mastermind Executive lifecycle object.

Provider responses are never serialized to stdout. They may only select one of
a closed set of receipt renderers; each renderer receives non-provider inputs
(binary digest + UTC observation time) and emits literal status fields.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, TextIO

SCHEMA = "mastermind.grok_build_preflight.v1"
ACP_PROTOCOL_VERSION = 1
CLIENT_NAME = "mastermind-grok-preflight"
CLIENT_VERSION = "1"
CACHED_TOKEN_METHOD = "cached_token"
PUBLIC_FAILURE = "PREFLIGHT_FAILED"

_PROVIDER_TIMEOUT_SECONDS = 15.0
_ACP_RESPONSE_TIMEOUT_SECONDS = 20.0
_MAX_LINE_BYTES = 256 * 1024
_HASH_CHUNK_BYTES = 1024 * 1024
MAX_BINARY_BYTES = 512 * 1024 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}|"
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret)"
    r"\s*[:=]\s*[^\s]{8,})"
)
_VERSION_RE = re.compile(r"^[\x20-\x7e]{1,128}$")
_ALLOWED_ENV_KEYS = frozenset(
    {
        "HOME",
        "USER",
        "LOGNAME",
        "PATH",
        "SHELL",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "GROK_HOME",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
)

REASON_CODES = frozenset(
    {
        "BINARY_UNAVAILABLE",
        "BINARY_INVALID",
        "BINARY_CHANGED_DURING_PREFLIGHT",
        "COMMAND_NOT_ALLOWED",
        "PROVIDER_TIMEOUT",
        "PROVIDER_COMMAND_FAILED",
        "ACP_RESPONSE_INVALID",
        "ACP_PROCESS_EXITED",
        "SECRET_SHAPED_VALUE",
    }
)


class PreflightError(RuntimeError):
    """Fail-closed internal error. Public output never includes its text."""

    def __init__(self, code: str) -> None:
        self.code = code if code in REASON_CODES else PUBLIC_FAILURE
        super().__init__(self.code)


class AcpOutcome(Enum):
    READY = "ready"
    CACHED_TOKEN_UNAVAILABLE = "cached_token_unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    INITIALIZE_FAILED = "initialize_failed"
    PROTOCOL_UNSUPPORTED = "protocol_unsupported"


@dataclasses.dataclass(frozen=True)
class BinaryIdentity:
    sha256: str
    size: int
    device: int
    inode: int
    mtime_ns: int


def _raise(code: str) -> None:
    raise PreflightError(code)


def _reject_secret_shaped(value: Any) -> None:
    if isinstance(value, str):
        if _SECRET_RE.search(value):
            _raise("SECRET_SHAPED_VALUE")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_secret_shaped(str(key))
            _reject_secret_shaped(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_secret_shaped(item)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_observed_at(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 40 or _CONTROL_RE.search(value):
        _raise("BINARY_INVALID")
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        _raise("BINARY_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() != datetime.now(UTC).utcoffset():
        _raise("BINARY_INVALID")
    return value


def _require_binary(binary: Path) -> tuple[Path, os.stat_result]:
    raw = Path(binary)
    if not raw.is_absolute():
        _raise("BINARY_INVALID")
    try:
        info = raw.lstat()
    except OSError:
        _raise("BINARY_UNAVAILABLE")
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        _raise("BINARY_INVALID")
    if not os.access(raw, os.X_OK):
        _raise("BINARY_INVALID")
    if info.st_size <= 0 or info.st_size > MAX_BINARY_BYTES:
        _raise("BINARY_INVALID")
    return raw, info


def _hash_binary(binary: Path) -> str:
    resolved, _ = _require_binary(binary)
    digest = hashlib.sha256()
    read_bytes = 0
    try:
        with resolved.open("rb") as stream:
            while True:
                chunk = stream.read(_HASH_CHUNK_BYTES)
                if not chunk:
                    break
                read_bytes += len(chunk)
                if read_bytes > MAX_BINARY_BYTES:
                    _raise("BINARY_INVALID")
                digest.update(chunk)
    except OSError:
        _raise("BINARY_INVALID")
    return digest.hexdigest()


def snapshot_binary(binary: Path) -> tuple[Path, BinaryIdentity]:
    resolved, info = _require_binary(binary)
    return resolved, BinaryIdentity(
        sha256=_hash_binary(resolved),
        size=int(info.st_size),
        device=int(info.st_dev),
        inode=int(info.st_ino),
        mtime_ns=int(info.st_mtime_ns),
    )


def assert_binary_unchanged(binary: Path, identity: BinaryIdentity) -> None:
    _, info = _require_binary(binary)
    if (
        int(info.st_size) != identity.size
        or int(info.st_dev) != identity.device
        or int(info.st_ino) != identity.inode
        or int(info.st_mtime_ns) != identity.mtime_ns
        or _hash_binary(binary) != identity.sha256
    ):
        _raise("BINARY_CHANGED_DURING_PREFLIGHT")


def build_allowed_argv(binary: Path, operation: str) -> tuple[str, ...]:
    resolved, _ = _require_binary(binary)
    if operation == "version":
        return (str(resolved), "--no-auto-update", "version")
    if operation == "acp_stdio":
        return (str(resolved), "--no-auto-update", "agent", "stdio")
    _raise("COMMAND_NOT_ALLOWED")


def sanitized_provider_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    incoming = dict(os.environ if source is None else source)
    result = {
        key: str(value)
        for key, value in incoming.items()
        if key in _ALLOWED_ENV_KEYS and isinstance(value, str)
    }
    for key in tuple(result):
        upper = key.upper()
        if upper == "XAI_API_KEY" or "AUTH_TOKEN" in upper or "ACCESS_TOKEN" in upper:
            result.pop(key, None)
    return result


def observe_version(binary: Path) -> None:
    argv = build_allowed_argv(binary, "version")
    try:
        completed = subprocess.run(
            argv,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=_PROVIDER_TIMEOUT_SECONDS,
            env=sanitized_provider_env(),
        )
    except subprocess.TimeoutExpired:
        _raise("PROVIDER_TIMEOUT")
    except OSError:
        _raise("PROVIDER_COMMAND_FAILED")
    if completed.returncode != 0:
        _raise("PROVIDER_COMMAND_FAILED")
    text = str(completed.stdout or "").strip()
    if _VERSION_RE.fullmatch(text) is None:
        _raise("BINARY_INVALID")
    _reject_secret_shaped(text)


def _jsonrpc_request(request_id: int, method: str, params: Mapping[str, Any]) -> str:
    return json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def initialize_request() -> str:
    return _jsonrpc_request(
        1,
        "initialize",
        {
            "protocolVersion": ACP_PROTOCOL_VERSION,
            "clientCapabilities": {},
            "clientInfo": {
                "name": CLIENT_NAME,
                "title": "Mastermind Grok Preflight",
                "version": CLIENT_VERSION,
            },
        },
    )


def authenticate_request() -> str:
    return _jsonrpc_request(
        2,
        "authenticate",
        {"methodId": CACHED_TOKEN_METHOD, "_meta": {"headless": True}},
    )


def _auth_method_ids(result: Mapping[str, Any]) -> tuple[str, ...]:
    raw_methods = result.get("authMethods")
    if not isinstance(raw_methods, list):
        _raise("ACP_RESPONSE_INVALID")
    method_ids: list[str] = []
    for row in raw_methods:
        if not isinstance(row, Mapping):
            _raise("ACP_RESPONSE_INVALID")
        method_id = row.get("id")
        if not isinstance(method_id, str) or not method_id or len(method_id) > 64:
            _raise("ACP_RESPONSE_INVALID")
        if _CONTROL_RE.search(method_id):
            _raise("ACP_RESPONSE_INVALID")
        _reject_secret_shaped(method_id)
        method_ids.append(method_id)
    if len(method_ids) != len(set(method_ids)):
        _raise("ACP_RESPONSE_INVALID")
    return tuple(method_ids)


def normalize_initialize_response(payload: Mapping[str, Any]) -> AcpOutcome | None:
    _reject_secret_shaped(payload)
    if not isinstance(payload, Mapping) or payload.get("jsonrpc") != "2.0" or payload.get("id") != 1:
        _raise("ACP_RESPONSE_INVALID")
    if "error" in payload:
        return AcpOutcome.INITIALIZE_FAILED
    result = payload.get("result")
    if not isinstance(result, Mapping):
        _raise("ACP_RESPONSE_INVALID")
    if result.get("protocolVersion") != ACP_PROTOCOL_VERSION:
        return AcpOutcome.PROTOCOL_UNSUPPORTED
    if CACHED_TOKEN_METHOD not in _auth_method_ids(result):
        return AcpOutcome.CACHED_TOKEN_UNAVAILABLE
    return None


def normalize_authenticate_response(payload: Mapping[str, Any]) -> AcpOutcome:
    _reject_secret_shaped(payload)
    if not isinstance(payload, Mapping) or payload.get("jsonrpc") != "2.0" or payload.get("id") != 2:
        _raise("ACP_RESPONSE_INVALID")
    if "error" in payload:
        return AcpOutcome.AUTHENTICATION_FAILED
    if "result" not in payload:
        _raise("ACP_RESPONSE_INVALID")
    return AcpOutcome.READY


def _read_json_line(stream: TextIO, timeout_seconds: float) -> Mapping[str, Any]:
    selector = selectors.DefaultSelector()
    try:
        selector.register(stream, selectors.EVENT_READ)
        ready = selector.select(timeout_seconds)
        if not ready:
            _raise("PROVIDER_TIMEOUT")
        line = stream.readline(_MAX_LINE_BYTES + 1)
    finally:
        selector.close()
    if not line:
        _raise("ACP_PROCESS_EXITED")
    if len(line.encode("utf-8", "replace")) > _MAX_LINE_BYTES:
        _raise("ACP_RESPONSE_INVALID")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        _raise("ACP_RESPONSE_INVALID")
    if not isinstance(payload, Mapping):
        _raise("ACP_RESPONSE_INVALID")
    _reject_secret_shaped(payload)
    return payload


def _send_json_line(stream: TextIO, payload: str) -> None:
    try:
        stream.write(payload + "\n")
        stream.flush()
    except OSError:
        _raise("PROVIDER_COMMAND_FAILED")


def observe_acp_cached_oauth(binary: Path) -> AcpOutcome:
    """Perform only ACP initialize + cached-token authenticate; never session/new."""

    argv = build_allowed_argv(binary, "acp_stdio")
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=sanitized_provider_env(),
            start_new_session=True,
        )
    except OSError:
        _raise("PROVIDER_COMMAND_FAILED")
    try:
        if proc.stdin is None or proc.stdout is None:
            _raise("PROVIDER_COMMAND_FAILED")
        _send_json_line(proc.stdin, initialize_request())
        init_outcome = normalize_initialize_response(
            _read_json_line(proc.stdout, _ACP_RESPONSE_TIMEOUT_SECONDS)
        )
        if init_outcome is not None:
            return init_outcome
        _send_json_line(proc.stdin, authenticate_request())
        return normalize_authenticate_response(
            _read_json_line(proc.stdout, _ACP_RESPONSE_TIMEOUT_SECONDS)
        )
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass


def _receipt_base(binary_sha256: str, observed_at: str) -> dict[str, Any]:
    if _SHA256_RE.fullmatch(binary_sha256) is None:
        _raise("BINARY_INVALID")
    _validate_observed_at(observed_at)
    return {
        "schema": SCHEMA,
        "observed_at": observed_at,
        "grok_binary_sha256": binary_sha256,
        "acp_protocol_version": ACP_PROTOCOL_VERSION,
        "model_turn_performed": False,
        "executive_routing_ready": False,
    }


def render_ready_receipt(binary_sha256: str, observed_at: str) -> str:
    value = _receipt_base(binary_sha256, observed_at)
    value.update(
        cached_token_offered=True,
        oauth_ready=True,
        verdict="LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE",
        reason_codes=[],
    )
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def render_cached_unavailable_receipt(binary_sha256: str, observed_at: str) -> str:
    value = _receipt_base(binary_sha256, observed_at)
    value.update(
        cached_token_offered=False,
        oauth_ready=False,
        verdict="CACHED_TOKEN_METHOD_UNAVAILABLE",
        reason_codes=["CACHED_TOKEN_METHOD_UNAVAILABLE"],
    )
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def render_auth_failed_receipt(binary_sha256: str, observed_at: str) -> str:
    value = _receipt_base(binary_sha256, observed_at)
    value.update(
        cached_token_offered=True,
        oauth_ready=False,
        verdict="ACP_AUTHENTICATION_FAILED",
        reason_codes=["ACP_AUTHENTICATION_FAILED"],
    )
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def render_initialize_failed_receipt(binary_sha256: str, observed_at: str) -> str:
    value = _receipt_base(binary_sha256, observed_at)
    value.update(
        cached_token_offered=False,
        oauth_ready=False,
        verdict="ACP_INITIALIZE_FAILED",
        reason_codes=["ACP_INITIALIZE_FAILED"],
    )
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def render_protocol_unsupported_receipt(binary_sha256: str, observed_at: str) -> str:
    value = _receipt_base(binary_sha256, observed_at)
    value.update(
        cached_token_offered=False,
        oauth_ready=False,
        verdict="ACP_PROTOCOL_UNSUPPORTED",
        reason_codes=["ACP_PROTOCOL_UNSUPPORTED"],
    )
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Secret-free Grok Build OAuth/ACP preflight")
    parser.add_argument("--grok-binary", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        binary, identity = snapshot_binary(args.grok_binary)
        observe_version(binary)
        assert_binary_unchanged(binary, identity)
        outcome = observe_acp_cached_oauth(binary)
        assert_binary_unchanged(binary, identity)
        observed_at = now_iso()
    except Exception:
        print(json.dumps({"ok": False, "error": PUBLIC_FAILURE}, sort_keys=True))
        return 2

    # Provider-derived state only selects a branch. No provider-derived value is
    # passed into a renderer or serialized to stdout.
    if outcome is AcpOutcome.READY:
        print(render_ready_receipt(identity.sha256, observed_at))
        return 0
    if outcome is AcpOutcome.CACHED_TOKEN_UNAVAILABLE:
        print(render_cached_unavailable_receipt(identity.sha256, observed_at))
        return 1
    if outcome is AcpOutcome.AUTHENTICATION_FAILED:
        print(render_auth_failed_receipt(identity.sha256, observed_at))
        return 1
    if outcome is AcpOutcome.INITIALIZE_FAILED:
        print(render_initialize_failed_receipt(identity.sha256, observed_at))
        return 1
    if outcome is AcpOutcome.PROTOCOL_UNSUPPORTED:
        print(render_protocol_unsupported_receipt(identity.sha256, observed_at))
        return 1

    print(json.dumps({"ok": False, "error": PUBLIC_FAILURE}, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())