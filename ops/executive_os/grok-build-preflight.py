"""Provider-work-free Grok Build OAuth/ACP preflight.

This source proves only that an exact local Grok Build executable can speak the
reviewed ACP initialization wire and authenticate through the provider-owned
cached OAuth method. It never creates an Executive Job/Attempt/Worker, chooses
capacity, starts an ACP session, sends a model prompt, or reads credential
contents.

The provider remains the credential owner. The preflight deliberately removes
``XAI_API_KEY`` from the child environment so a successful result cannot be
caused by that environment variable. This does not prove that every future
Grok model invocation is OAuth-only; later worker admission must separately
prove the accepted provider/config precedence for the real execution realm.
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
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, TextIO


SCHEMA = "mastermind.grok_build_preflight.v1"
ACP_PROTOCOL_VERSION = 1
CLIENT_NAME = "mastermind-grok-preflight"
CLIENT_VERSION = "1"
CACHED_TOKEN_METHOD = "cached_token"

VERDICTS = frozenset(
    {
        "LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE",
        "CACHED_TOKEN_METHOD_UNAVAILABLE",
        "ACP_AUTHENTICATION_FAILED",
        "ACP_INITIALIZE_FAILED",
        "ACP_PROTOCOL_UNSUPPORTED",
    }
)
REASON_CODES = VERDICTS | frozenset(
    {
        "BINARY_UNAVAILABLE",
        "BINARY_INVALID",
        "COMMAND_NOT_ALLOWED",
        "PROVIDER_TIMEOUT",
        "PROVIDER_COMMAND_FAILED",
        "ACP_RESPONSE_INVALID",
        "ACP_PROCESS_EXITED",
        "SECRET_SHAPED_VALUE",
        "RECEIPT_INVALID",
    }
)

_RECEIPT_KEYS = frozenset(
    {
        "schema",
        "observed_at",
        "grok_binary_sha256",
        "grok_version",
        "acp_protocol_version",
        "cached_token_offered",
        "oauth_ready",
        "model_turn_performed",
        "executive_routing_ready",
        "verdict",
        "reason_codes",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}|"
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token)\s*[:=]\s*[^\s]{12,})"
)
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+() /-]{0,127}$")
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
_PROVIDER_TIMEOUT_SECONDS = 15.0
_ACP_RESPONSE_TIMEOUT_SECONDS = 20.0
_MAX_LINE_BYTES = 256 * 1024
_HASH_CHUNK_BYTES = 1024 * 1024
MAX_BINARY_BYTES = 512 * 1024 * 1024


PUBLIC_FAILURE = "PREFLIGHT_FAILED"


class PreflightError(RuntimeError):
    """Bounded fail-closed preflight refusal with a closed public code."""

    def __init__(self, code: str) -> None:
        # Never expose arbitrary exception text. Only a compile-time closed code
        # may cross the CLI boundary, even if a future caller passes tainted text.
        self.public_code = code if code in REASON_CODES else PUBLIC_FAILURE
        super().__init__(self.public_code)


@dataclasses.dataclass(frozen=True)
class AcpAuthObservation:
    cached_token_offered: bool
    oauth_ready: bool
    verdict: str
    reason_codes: tuple[str, ...] = ()


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


def _bounded_text(value: Any, *, maximum: int = 128) -> str:
    text = str(value or "").strip()
    if not text or len(text) > maximum or _CONTROL_RE.search(text):
        _raise("RECEIPT_INVALID")
    _reject_secret_shaped(text)
    return text


def _require_utc(value: Any) -> str:
    text = _bounded_text(value, maximum=40)
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        _raise("RECEIPT_INVALID")
    if parsed.tzinfo is None or parsed.utcoffset() != datetime.now(UTC).utcoffset():
        _raise("RECEIPT_INVALID")
    return text


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_binary(binary: Path) -> Path:
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
    return raw


def _hash_binary(binary: Path) -> str:
    resolved = _require_binary(binary)
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


def build_allowed_argv(binary: Path, operation: str) -> tuple[str, ...]:
    resolved = _require_binary(binary)
    if operation == "version":
        return (str(resolved), "--no-auto-update", "version")
    if operation == "acp_stdio":
        return (str(resolved), "--no-auto-update", "agent", "stdio")
    _raise("COMMAND_NOT_ALLOWED")


def sanitized_provider_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return a minimal provider environment without API-key authentication."""

    incoming = dict(os.environ if source is None else source)
    result = {
        key: str(value)
        for key, value in incoming.items()
        if key in _ALLOWED_ENV_KEYS and isinstance(value, str)
    }
    # Belt-and-suspenders guard: these names are never forwarded even if a
    # future allowlist edit accidentally includes them.
    for key in tuple(result):
        upper = key.upper()
        if upper == "XAI_API_KEY" or "AUTH_TOKEN" in upper or "ACCESS_TOKEN" in upper:
            result.pop(key, None)
    return result


def _normalize_version(raw: str) -> str:
    text = str(raw or "").strip()
    if not text or len(text) > 128 or _CONTROL_RE.search(text):
        _raise("BINARY_INVALID")
    _reject_secret_shaped(text)
    if _VERSION_RE.fullmatch(text) is None:
        _raise("BINARY_INVALID")
    return text


def observe_version(binary: Path) -> str:
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
    return _normalize_version(completed.stdout)


def _jsonrpc_request(request_id: int, method: str, params: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": dict(params),
        },
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


def _extract_auth_method_ids(result: Mapping[str, Any]) -> tuple[str, ...]:
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


def normalize_initialize_response(payload: Mapping[str, Any]) -> tuple[bool, str | None]:
    _reject_secret_shaped(payload)
    if not isinstance(payload, Mapping) or payload.get("jsonrpc") != "2.0" or payload.get("id") != 1:
        _raise("ACP_RESPONSE_INVALID")
    if "error" in payload:
        return False, "ACP_INITIALIZE_FAILED"
    result = payload.get("result")
    if not isinstance(result, Mapping):
        _raise("ACP_RESPONSE_INVALID")
    protocol = result.get("protocolVersion")
    if protocol != ACP_PROTOCOL_VERSION:
        return False, "ACP_PROTOCOL_UNSUPPORTED"
    methods = _extract_auth_method_ids(result)
    if CACHED_TOKEN_METHOD not in methods:
        return False, "CACHED_TOKEN_METHOD_UNAVAILABLE"
    return True, None


def normalize_authenticate_response(payload: Mapping[str, Any]) -> AcpAuthObservation:
    _reject_secret_shaped(payload)
    if not isinstance(payload, Mapping) or payload.get("jsonrpc") != "2.0" or payload.get("id") != 2:
        _raise("ACP_RESPONSE_INVALID")
    if "error" in payload:
        return AcpAuthObservation(
            cached_token_offered=True,
            oauth_ready=False,
            verdict="ACP_AUTHENTICATION_FAILED",
            reason_codes=("ACP_AUTHENTICATION_FAILED",),
        )
    if "result" not in payload:
        _raise("ACP_RESPONSE_INVALID")
    return AcpAuthObservation(
        cached_token_offered=True,
        oauth_ready=True,
        verdict="LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE",
        reason_codes=(),
    )


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


def observe_acp_cached_oauth(binary: Path) -> AcpAuthObservation:
    """Initialize ACP and authenticate cached OAuth; never create a session/prompt."""

    argv = build_allowed_argv(binary, "acp_stdio")
    env = sanitized_provider_env()
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
            start_new_session=True,
        )
    except OSError:
        _raise("PROVIDER_COMMAND_FAILED")
    try:
        if proc.stdin is None or proc.stdout is None:
            _raise("PROVIDER_COMMAND_FAILED")
        _send_json_line(proc.stdin, initialize_request())
        initialized = _read_json_line(proc.stdout, _ACP_RESPONSE_TIMEOUT_SECONDS)
        offered, refusal = normalize_initialize_response(initialized)
        if not offered:
            assert refusal is not None
            return AcpAuthObservation(
                cached_token_offered=False,
                oauth_ready=False,
                verdict=refusal,
                reason_codes=(refusal,),
            )

        _send_json_line(proc.stdin, authenticate_request())
        authenticated = _read_json_line(proc.stdout, _ACP_RESPONSE_TIMEOUT_SECONDS)
        return normalize_authenticate_response(authenticated)
    finally:
        # Authentication may refresh provider-owned OAuth state. We only ensure
        # the local ACP process group is reaped; no model session exists to cancel.
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


def validate_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    _reject_secret_shaped(value)
    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        _raise("RECEIPT_INVALID")
    result = dict(value)
    if result["schema"] != SCHEMA:
        _raise("RECEIPT_INVALID")
    _require_utc(result["observed_at"])
    digest = result["grok_binary_sha256"]
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        _raise("RECEIPT_INVALID")
    result["grok_version"] = _normalize_version(str(result["grok_version"]))
    if result["acp_protocol_version"] != ACP_PROTOCOL_VERSION:
        _raise("RECEIPT_INVALID")
    for key in (
        "cached_token_offered",
        "oauth_ready",
        "model_turn_performed",
        "executive_routing_ready",
    ):
        if type(result[key]) is not bool:
            _raise("RECEIPT_INVALID")
    if result["model_turn_performed"] is not False or result["executive_routing_ready"] is not False:
        _raise("RECEIPT_INVALID")
    verdict = result["verdict"]
    if verdict not in VERDICTS:
        _raise("RECEIPT_INVALID")
    reasons = result["reason_codes"]
    if not isinstance(reasons, list) or len(reasons) > 8:
        _raise("RECEIPT_INVALID")
    for code in reasons:
        if code not in REASON_CODES:
            _raise("RECEIPT_INVALID")
    if len(reasons) != len(set(reasons)):
        _raise("RECEIPT_INVALID")

    ready = verdict == "LOCAL_OAUTH_ACP_READY_NOT_ROUTABLE"
    if ready != bool(result["oauth_ready"]):
        _raise("RECEIPT_INVALID")
    if ready and not result["cached_token_offered"]:
        _raise("RECEIPT_INVALID")
    if ready and reasons:
        _raise("RECEIPT_INVALID")
    if not ready and not reasons:
        _raise("RECEIPT_INVALID")
    return result


def build_receipt(binary: Path) -> dict[str, Any]:
    binary_path = _require_binary(binary)
    digest = _hash_binary(binary_path)
    version = observe_version(binary_path)
    auth = observe_acp_cached_oauth(binary_path)
    return validate_receipt(
        {
            "schema": SCHEMA,
            "observed_at": now_iso(),
            "grok_binary_sha256": digest,
            "grok_version": version,
            "acp_protocol_version": ACP_PROTOCOL_VERSION,
            "cached_token_offered": auth.cached_token_offered,
            "oauth_ready": auth.oauth_ready,
            "model_turn_performed": False,
            "executive_routing_ready": False,
            "verdict": auth.verdict,
            "reason_codes": list(auth.reason_codes),
        }
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Secret-free Grok Build OAuth/ACP preflight")
    parser.add_argument("--grok-binary", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        receipt = build_receipt(args.grok_binary)
    except PreflightError:
        # No exception-derived text crosses stdout. Expected auth/protocol refusal
        # is represented by a validated receipt; exceptional failures are opaque.
        print(json.dumps({"ok": False, "error": PUBLIC_FAILURE}, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return 0 if receipt["oauth_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
