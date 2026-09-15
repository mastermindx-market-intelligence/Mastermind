#!/usr/bin/env python3
"""Register the existing loopback Mastermind Executive MCP with Codex.

This is a stateless Codex client-configuration helper. It never reads or stores
OAuth/bearer credentials, never logs in, and never owns Executive lifecycle.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from typing import Any
from urllib.parse import urlsplit

SERVER_NAME = "mastermind-executive"
_ALLOWED_HOSTS = frozenset({"127.0.0.1"})
_KNOWN_STREAMABLE_HTTP_TRANSPORT_KEYS = frozenset({
    "type",
    "url",
    "bearer_token_env_var",
    "http_headers",
    "env_http_headers",
    "http_headers_helper",
})


class RegistrationError(RuntimeError):
    """Codex Executive MCP registration could not be proven safe."""


class _CommandEffectUnknown(RuntimeError):
    """One effectful Codex command may have committed before its reply was lost."""


@dataclasses.dataclass(frozen=True)
class RegistrationReceipt:
    server_name: str
    url: str
    created: bool
    auth_status: str | None
    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)



def _validated_url(value: str) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise RegistrationError("Executive MCP URL is invalid")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise RegistrationError("Executive MCP URL is invalid") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname is None
        or parsed.hostname.lower() not in _ALLOWED_HOSTS
        or port is None
        or not 1024 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/mcp"
        or parsed.query
        or parsed.fragment
    ):
        raise RegistrationError("Executive MCP URL must be explicit loopback HTTP /mcp")
    return value


def _run(
    codex_bin: str, *args: str, effectful: bool = False
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [codex_bin, *args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        if effectful:
            raise _CommandEffectUnknown from exc
        raise RegistrationError("Codex MCP command is unavailable") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise RegistrationError("Codex MCP command is unavailable") from exc


def _list_servers(codex_bin: str) -> list[dict[str, Any]]:
    completed = _run(codex_bin, "mcp", "list", "--json")
    if completed.returncode != 0:
        raise RegistrationError("Codex MCP census failed")
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RegistrationError("Codex MCP census is malformed") from exc
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise RegistrationError("Codex MCP census is malformed")
    return payload


def _matching_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [row for row in rows if row.get("name") == SERVER_NAME]
    if len(matches) > 1:
        raise RegistrationError("Codex has duplicate mastermind-executive registrations")
    return matches[0] if matches else None


def _validate_existing(row: dict[str, Any], expected_url: str) -> str | None:
    transport = row.get("transport")
    if not isinstance(transport, dict):
        raise RegistrationError("existing mastermind-executive has different configuration")
    if set(transport) - _KNOWN_STREAMABLE_HTTP_TRANSPORT_KEYS:
        raise RegistrationError("existing mastermind-executive has different configuration")
    if (
        row.get("enabled") is not True
        or transport.get("type") != "streamable_http"
        or transport.get("url") != expected_url
        or transport.get("bearer_token_env_var") is not None
        or transport.get("http_headers") not in (None, {})
        or transport.get("env_http_headers") not in (None, {})
        or transport.get("http_headers_helper") is not None
    ):
        raise RegistrationError("existing mastermind-executive has different configuration")
    auth_status = row.get("auth_status")
    if auth_status is not None and not isinstance(auth_status, str):
        raise RegistrationError("Codex MCP auth status is malformed")
    return auth_status


def register(server_url: str, *, codex_bin: str = "codex") -> RegistrationReceipt:
    """Ensure one exact, secret-free Executive MCP registration exists."""

    expected_url = _validated_url(server_url)
    existing = _matching_row(_list_servers(codex_bin))
    if existing is not None:
        auth_status = _validate_existing(existing, expected_url)
        return RegistrationReceipt(
            server_name=SERVER_NAME,
            url=expected_url,
            created=False,
            auth_status=auth_status,
        )

    effect_unknown = False
    try:
        completed = _run(
            codex_bin, "mcp", "add", SERVER_NAME, "--url", expected_url, effectful=True
        )
    except _CommandEffectUnknown:
        completed = None
        effect_unknown = True

    # Reconcile the canonical Codex census after every add attempt.  This is
    # required after a timeout because the config mutation may have committed
    # before the subprocess reply was lost.  Never issue a second add here.
    registered = _matching_row(_list_servers(codex_bin))
    if registered is not None:
        auth_status = _validate_existing(registered, expected_url)
        return RegistrationReceipt(
            server_name=SERVER_NAME,
            url=expected_url,
            created=True,
            auth_status=auth_status,
        )
    if effect_unknown:
        raise RegistrationError("Codex MCP registration effect is unknown")
    if completed is not None and completed.returncode != 0:
        raise RegistrationError("Codex MCP registration failed")
    raise RegistrationError("Codex MCP registration could not be verified")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True)
    parser.add_argument("--codex-bin", default="codex")
    args = parser.parse_args(argv)
    try:
        receipt = register(args.url, codex_bin=args.codex_bin)
    except RegistrationError as exc:
        print(f"register-executive-mcp: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
