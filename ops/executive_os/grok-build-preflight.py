#!/usr/bin/env python3
"""Provider-work-free Grok Build native OAuth/ACP preflight.

This executable proves only whether the exact caller-selected Grok Build binary
can advertise ACP v1 and authenticate through its already-cached native OAuth
method without creating a model session or prompt.  It never reads, copies or
prints credential material and never claims Executive routing readiness.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import json
import os
import re
import select
import signal
import stat
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "mastermind.grok_build_preflight.v1"
ACP_PROTOCOL_VERSION = 1
PUBLIC_FAILURE = "PREFLIGHT_FAILED"
VERSION_TIMEOUT_SECONDS = 5.0
ACP_TIMEOUT_SECONDS = 8.0
MAX_LINE_BYTES = 64 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^Grok Build [0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?$")
_SECRET_SHAPED_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|bearer\s+[A-Za-z0-9._~-]{16,}|"
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)"
    r"\s*[:=]\s*[^\s,}\]]{8,})"
)
_ALLOWED_ENV_KEYS = frozenset(
    {
        "HOME",
        "PATH",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TMPDIR",
        "GROK_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
    }
)


class PreflightError(RuntimeError):
    """One private implementation failure collapsed at the public boundary."""


class AcpOutcome(str, Enum):
    READY = "READY"
    CACHED_TOKEN_UNAVAILABLE = "CACHED_TOKEN_UNAVAILABLE"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    INITIALIZE_FAILED = "INITIALIZE_FAILED"
    PROTOCOL_UNSUPPORTED = "PROTOCOL_UNSUPPORTED"


@dataclasses.dataclass(frozen=True)
class BinaryIdentity:
    device: int
    inode: int
    size: int
    mtime_ns: int
    sha256: str


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise PreflightError("ACP_RESPONSE_INVALID") from exc


def _contains_secret_shape(value: Any) -> bool:
    if isinstance(value, str):
        return _SECRET_SHAPED_RE.search(value) is not None
    if isinstance(value, Mapping):
        return any(
            _contains_secret_shape(key) or _contains_secret_shape(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_secret_shape(item) for item in value)
    return False


def _require_no_secret_shape(value: Any) -> None:
    if _contains_secret_shape(value):
        raise PreflightError("SECRET_SHAPED_VALUE")


def sanitized_provider_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a minimal environment with API credentials and unrelated data absent."""

    values = os.environ if source is None else source
    result: dict[str, str] = {}
    for key in sorted(_ALLOWED_ENV_KEYS):
        value = values.get(key)
        if isinstance(value, str) and value:
            result[key] = value
    return result


def build_allowed_argv(binary: Path, command: str) -> tuple[str, ...]:
    path = str(binary)
    if command == "version":
        return (path, "--no-auto-update", "version")
    if command == "acp_stdio":
        return (path, "--no-auto-update", "agent", "stdio")
    raise PreflightError("COMMAND_NOT_ALLOWED")


def _require_binary(path: Path) -> tuple[Path, os.stat_result]:
    if not isinstance(path, Path) or not path.is_absolute():
        raise PreflightError("BINARY_INVALID")
    try:
        observed = path.lstat()
    except OSError as exc:
        raise PreflightError("BINARY_INVALID") from exc
    if (
        stat.S_ISLNK(observed.st_mode)
        or not stat.S_ISREG(observed.st_mode)
        or observed.st_mode & 0o111 == 0
    ):
        raise PreflightError("BINARY_INVALID")
    return path, observed


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise PreflightError("BINARY_INVALID") from exc
    return digest.hexdigest()


def snapshot_binary(path: Path) -> tuple[Path, BinaryIdentity]:
    binary, observed = _require_binary(path)
    identity = BinaryIdentity(
        device=observed.st_dev,
        inode=observed.st_ino,
        size=observed.st_size,
        mtime_ns=observed.st_mtime_ns,
        sha256=_sha256_file(binary),
    )
    if _SHA256_RE.fullmatch(identity.sha256) is None:
        raise PreflightError("BINARY_INVALID")
    assert_binary_unchanged(binary, identity)
    return binary, identity


def assert_binary_unchanged(path: Path, identity: BinaryIdentity) -> None:
    _, current = _require_binary(path)
    if (
        current.st_dev != identity.device
        or current.st_ino != identity.inode
        or current.st_size != identity.size
        or current.st_mtime_ns != identity.mtime_ns
        or _sha256_file(path) != identity.sha256
    ):
        raise PreflightError("BINARY_CHANGED_DURING_PREFLIGHT")


def observe_version(binary: Path) -> None:
    """Verify a bounded recognizable executable without exposing version text."""

    try:
        completed = subprocess.run(
            build_allowed_argv(binary, "version"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=VERSION_TIMEOUT_SECONDS,
            check=False,
            env=sanitized_provider_env(),
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise PreflightError("VERSION_PROBE_FAILED") from exc
    output = completed.stdout.strip()
    if completed.returncode != 0 or _VERSION_RE.fullmatch(output) is None:
        raise PreflightError("VERSION_PROBE_FAILED")


def initialize_request() -> str:
    return _canonical_json(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": ACP_PROTOCOL_VERSION,
                "clientCapabilities": {},
                "clientInfo": {"name": "mastermind-grok-preflight", "version": "1.0.0"},
            },
        }
    )


def authenticate_request() -> str:
    return _canonical_json(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "authenticate",
            "params": {"_meta": {"headless": True}, "methodId": "cached_token"},
        }
    )


def _require_exact_rpc(value: Any, expected_id: int) -> dict[str, Any]:
    _require_no_secret_shape(value)
    if not isinstance(value, dict) or set(value) not in (
        {"jsonrpc", "id", "result"},
        {"jsonrpc", "id", "error"},
    ):
        raise PreflightError("ACP_RESPONSE_INVALID")
    if value.get("jsonrpc") != "2.0" or value.get("id") != expected_id:
        raise PreflightError("ACP_RESPONSE_INVALID")
    return value


def normalize_initialize_response(value: Any) -> AcpOutcome | None:
    message = _require_exact_rpc(value, 1)
    if "error" in message:
        if not isinstance(message["error"], dict):
            raise PreflightError("ACP_RESPONSE_INVALID")
        return AcpOutcome.INITIALIZE_FAILED
    result = message["result"]
    if not isinstance(result, dict):
        raise PreflightError("ACP_RESPONSE_INVALID")
    protocol_version = result.get("protocolVersion")
    if protocol_version != ACP_PROTOCOL_VERSION:
        return AcpOutcome.PROTOCOL_UNSUPPORTED
    methods = result.get("authMethods")
    if not isinstance(methods, list):
        raise PreflightError("ACP_RESPONSE_INVALID")
    identifiers: list[str] = []
    for item in methods:
        if not isinstance(item, dict) or set(item) != {"id"}:
            raise PreflightError("ACP_RESPONSE_INVALID")
        identifier = item["id"]
        if not isinstance(identifier, str) or not identifier:
            raise PreflightError("ACP_RESPONSE_INVALID")
        identifiers.append(identifier)
    if len(identifiers) != len(set(identifiers)):
        raise PreflightError("ACP_RESPONSE_INVALID")
    if "cached_token" not in identifiers:
        return AcpOutcome.CACHED_TOKEN_UNAVAILABLE
    return None


def normalize_authenticate_response(value: Any) -> AcpOutcome:
    message = _require_exact_rpc(value, 2)
    if "error" in message:
        if not isinstance(message["error"], dict):
            raise PreflightError("ACP_RESPONSE_INVALID")
        return AcpOutcome.AUTHENTICATION_FAILED
    if not isinstance(message["result"], dict):
        raise PreflightError("ACP_RESPONSE_INVALID")
    return AcpOutcome.READY


def _send_json_line(stream, payload: str) -> None:
    try:
        stream.write((payload + "\n").encode("utf-8"))
        stream.flush()
    except (OSError, ValueError) as exc:
        raise PreflightError("ACP_TRANSPORT_FAILED") from exc


def _read_json_line(stream, timeout: float) -> Any:
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PreflightError("ACP_TRANSPORT_TIMEOUT")
        ready, _, _ = select.select([stream], [], [], remaining)
        if not ready:
            raise PreflightError("ACP_TRANSPORT_TIMEOUT")
        chunk = os.read(stream.fileno(), 1)
        if not chunk:
            raise PreflightError("ACP_TRANSPORT_FAILED")
        if chunk == b"\n":
            break
        buffer.extend(chunk)
        if len(buffer) > MAX_LINE_BYTES:
            raise PreflightError("ACP_RESPONSE_TOO_LARGE")
    try:
        text = buffer.decode("utf-8", errors="strict")
        return json.loads(text)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError("ACP_RESPONSE_INVALID") from exc


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except (OSError, subprocess.SubprocessError):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.SubprocessError:
            pass


def observe_acp_cached_oauth(binary: Path) -> AcpOutcome:
    try:
        process = subprocess.Popen(
            build_allowed_argv(binary, "acp_stdio"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=sanitized_provider_env(),
            start_new_session=True,
        )
    except OSError as exc:
        raise PreflightError("ACP_START_FAILED") from exc
    try:
        if process.stdin is None or process.stdout is None:
            raise PreflightError("ACP_TRANSPORT_FAILED")
        _send_json_line(process.stdin, initialize_request())
        initialize = normalize_initialize_response(
            _read_json_line(process.stdout, ACP_TIMEOUT_SECONDS)
        )
        if initialize is not None:
            return initialize
        _send_json_line(process.stdin, authenticate_request())
        return normalize_authenticate_response(
            _read_json_line(process.stdout, ACP_TIMEOUT_SECONDS)
        )
    finally:
        _terminate_process_group(process)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _receipt_base(binary_sha256: str, observed_at: str) -> dict[str, Any]:
    if _SHA256_RE.fullmatch(binary_sha256) is None:
        raise PreflightError("BINARY_INVALID")
    return {
        "schema": SCHEMA,
        "observed_at": observed_at,
        "grok_binary_sha256": binary_sha256,
        "acp_protocol_version": ACP_PROTOCOL_VERSION,
        "cached_token_offered": False,
        "oauth_ready": False,
        "model_turn_performed": False,
        "executive_routing_ready": False,
        "verdict": "UNKNOWN",
        "reason_codes": [],
    }


def render_ready_receipt(binary_sha256: str, observed_at: str) -> str:
    value = _receipt_base(binary_sha256, observed_at)
    value.update(
        cached_token_offered=True,
        oauth_ready=True,
        verdict="READY",
        reason_codes=[],
    )
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def render_cached_unavailable_receipt(binary_sha256: str, observed_at: str) -> str:
    value = _receipt_base(binary_sha256, observed_at)
    value.update(
        cached_token_offered=False,
        oauth_ready=False,
        verdict="CACHED_OAUTH_UNAVAILABLE",
        reason_codes=["CACHED_OAUTH_UNAVAILABLE"],
    )
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def render_auth_failed_receipt(binary_sha256: str, observed_at: str) -> str:
    value = _receipt_base(binary_sha256, observed_at)
    value.update(
        cached_token_offered=True,
        oauth_ready=False,
        verdict="AUTHENTICATION_FAILED",
        reason_codes=["AUTHENTICATION_FAILED"],
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
