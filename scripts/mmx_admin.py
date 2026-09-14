#!/usr/bin/env python3
"""Non-root client for the Mastermind privileged-action broker."""
from __future__ import annotations

import argparse
import json
import socket
import sys
import uuid
from pathlib import Path
from typing import Sequence

from control_plane.executive_privileged_action import REQUEST_SCHEMA, validate_request


DEFAULT_SOCKET = Path("/var/run/mastermind-executive/privileged.sock")
_MAX_RESPONSE_BYTES = 128 * 1024
_ACTIONS = (
    "executive.services.start",
    "executive.services.stop",
    "executive.services.restart",
    "executive.worker_auth.verify_only",
    "executive.worker_auth.verify_ready",
    "executive.worker_auth.recover_transaction",
)
_SLOT_IDS = ("codex-01", "codex-pro-01", "codex-pro-02", "codex-pro-03")
_CREDENTIAL_KINDS = ("service-account", "personal-access-token", "device-auth")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Invoke one reviewed Mastermind privileged action")
    parser.add_argument("action", choices=_ACTIONS)
    parser.add_argument("--request-id")
    parser.add_argument("--socket", dest="socket_path", type=Path, default=DEFAULT_SOCKET)
    parser.add_argument("--slot-id", choices=_SLOT_IDS)
    parser.add_argument("--expected-credential-kind", choices=_CREDENTIAL_KINDS)
    parser.add_argument("--workspace-binding-class")
    parser.add_argument("--credential-expires-at")
    return parser


def build_request(argv: Sequence[str]) -> dict[str, object]:
    args = _parser().parse_args(list(argv))
    values: dict[str, str] = {}
    if args.slot_id is not None:
        values["slot_id"] = args.slot_id
    if args.expected_credential_kind is not None:
        values["expected_credential_kind"] = args.expected_credential_kind
    if args.workspace_binding_class is not None:
        values["workspace_binding_class"] = args.workspace_binding_class
    if args.credential_expires_at is not None:
        values["credential_expires_at"] = args.credential_expires_at
    raw = {
        "schema": REQUEST_SCHEMA,
        "request_id": args.request_id or f"req-{uuid.uuid4().hex}",
        "action": args.action,
        "args": values,
    }
    return validate_request(raw).to_dict()


def _read_response(connection: socket.socket) -> dict[str, object]:
    buffer = bytearray()
    while True:
        chunk = connection.recv(min(4096, _MAX_RESPONSE_BYTES + 1 - len(buffer)))
        if not chunk:
            raise RuntimeError("privileged broker closed before a response")
        buffer.extend(chunk)
        if len(buffer) > _MAX_RESPONSE_BYTES:
            raise RuntimeError("privileged broker response exceeded the client bound")
        newline = buffer.find(b"\n")
        if newline >= 0:
            if newline != len(buffer) - 1:
                raise RuntimeError("privileged broker returned multiple frames")
            break
    value = json.loads(bytes(buffer[:-1]).decode("utf-8", errors="strict"))
    if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
        raise RuntimeError("privileged broker returned an invalid response")
    return value


def send_request(request: dict[str, object], *, socket_path: Path = DEFAULT_SOCKET) -> dict[str, object]:
    validated = validate_request(request)
    payload = (json.dumps(validated.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(30)
        connection.connect(str(socket_path))
        connection.sendall(payload)
        return _read_response(connection)
    finally:
        connection.close()


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    namespace = parser.parse_args(values)
    request = build_request(values)
    try:
        response = send_request(request, socket_path=namespace.socket_path)
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"mmx-admin transport failure: {exc}\n")
        return 69
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
    if response.get("ok") is not True:
        return 75 if response.get("error") == "EFFECT_UNKNOWN" else 1
    receipt = response.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("outcome") != "SUCCEEDED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
