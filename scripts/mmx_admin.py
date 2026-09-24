#!/usr/bin/env python3
"""Non-root client for the Mastermind privileged-action broker."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sys
import uuid
from pathlib import Path
from typing import Sequence

_RELEASE_ROOT = Path(__file__).resolve().parents[1]
if str(_RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(_RELEASE_ROOT))

from control_plane.executive_privileged_action import (
    REQUEST_SCHEMA,
    STATUS_REQUEST_SCHEMA,
    canonical_request_bytes,
    validate_request,
    validate_status_request,
)
from control_plane.executive_privileged_broker import (
    BrokerTrustError,
    STATUS_RECONCILED_NOT_APPLIED,
    WIRE_RESPONSE_SCHEMA,
    validate_reconciliation_record,
    validate_terminal_receipt,
)


DEFAULT_SOCKET = Path("/var/run/mastermind-executive/privileged.sock")
DEFAULT_CLIENT_TIMEOUT_SECONDS = 660
_MAX_RESPONSE_BYTES = 128 * 1024
_ACTIONS = (
    "executive.services.start",
    "executive.services.stop",
    "executive.services.restart",
    "executive.worker_auth.verify_only",
    "executive.worker_auth.verify_ready",
    "executive.worker_auth.recover_transaction",
)
_STATUS_ACTION = "status"
_SLOT_IDS = ("codex-01", "codex-pro-01", "codex-pro-02", "codex-pro-03")
_CREDENTIAL_KINDS = ("service-account", "personal-access-token", "device-auth")
_EFFECT_ONLY_FLAGS = (
    ("--slot-id", "slot_id"),
    ("--expected-credential-kind", "expected_credential_kind"),
    ("--workspace-binding-class", "workspace_binding_class"),
    ("--credential-expires-at", "credential_expires_at"),
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Invoke one reviewed Mastermind privileged action")
    parser.add_argument("action", choices=_ACTIONS + (_STATUS_ACTION,))
    parser.add_argument("--request-id")
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


def build_status_request(argv: Sequence[str]) -> dict[str, object]:
    parser = _parser()
    args = parser.parse_args(list(argv))
    if args.action != _STATUS_ACTION:
        parser.error("build_status_request requires the status action")
    if args.request_id is None:
        parser.error("status requires an explicit --request-id")
    for flag, attribute in _EFFECT_ONLY_FLAGS:
        if getattr(args, attribute) is not None:
            parser.error(f"status does not accept {flag}")
    raw = {"schema": STATUS_REQUEST_SCHEMA, "request_id": args.request_id}
    return validate_status_request(raw).to_dict()


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


def send_request(
    request: dict[str, object],
    *,
    socket_path: Path = DEFAULT_SOCKET,
    timeout_seconds: int = DEFAULT_CLIENT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    validated = validate_request(request)
    payload = (json.dumps(validated.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout_seconds)
        connection.connect(str(socket_path))
        connection.sendall(payload)
        return _read_response(connection)
    finally:
        connection.close()


def send_status_request(
    request: dict[str, object],
    *,
    socket_path: Path = DEFAULT_SOCKET,
    timeout_seconds: int = DEFAULT_CLIENT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    validated = validate_status_request(request)
    payload = (json.dumps(validated.to_dict(), sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout_seconds)
        connection.connect(str(socket_path))
        connection.sendall(payload)
        return _read_response(connection)
    finally:
        connection.close()


def _status_exit_code(response: dict[str, object], request_id: str) -> int:
    # A successful query is not evidence that the historical effect succeeded.
    # Correlate it before exposing a terminal/successful retrieval to callers.
    if (
        response.get("schema") != "mastermind.executive_privileged_action_response.v1"
        or response.get("ok") is not True
        or response.get("query") is not True
        or response.get("request_id") != request_id
        or not isinstance(response.get("installed_release_sha"), str)
        or re.fullmatch(r"[0-9a-f]{40}", response["installed_release_sha"]) is None
    ):
        return 1
    status = response.get("status")
    if status == "TERMINAL":
        receipt = response.get("receipt")
        if not isinstance(receipt, dict) or receipt.get("request_id") != request_id:
            return 1
        exit_code = receipt.get("exit_code")
        outcome = receipt.get("outcome")
        if (
            isinstance(exit_code, bool)
            or not isinstance(exit_code, int)
            or outcome not in ("SUCCEEDED", "FAILED")
            or (outcome == "SUCCEEDED") != (exit_code == 0)
        ):
            return 1
        return 0
    if status == STATUS_RECONCILED_NOT_APPLIED:
        if frozenset(response) != frozenset(
            {
                "schema",
                "ok",
                "query",
                "status",
                "request_id",
                "installed_release_sha",
                "marker_release_sha",
                "reconciliation",
            }
        ):
            return 1
        marker_release_sha = response.get("marker_release_sha")
        if (
            not isinstance(marker_release_sha, str)
            or re.fullmatch(r"[0-9a-f]{40}", marker_release_sha) is None
        ):
            return 1
        reconciliation = response.get("reconciliation")
        if not isinstance(reconciliation, dict):
            return 1
        try:
            validated_reconciliation = validate_reconciliation_record(
                reconciliation, expected_request_id=request_id
            )
        except BrokerTrustError:
            return 1
        if validated_reconciliation.get("target_release_sha") != marker_release_sha:
            return 1
        # Exit 0 means the status retrieval is trusted.  The reconciliation
        # record itself preserves that the original privileged effect was NOT_APPLIED.
        return 0
    if status == "EFFECT_UNKNOWN":
        return 75
    if status == "NOT_FOUND":
        return 4
    return 1


def _effect_exit_code(
    response: dict[str, object], request: dict[str, object]
) -> int:
    if response.get("schema") != WIRE_RESPONSE_SCHEMA or not isinstance(response.get("ok"), bool):
        raise RuntimeError("privileged broker returned an invalid effect response")
    if response["ok"] is False:
        if frozenset(response) != frozenset({"schema", "ok", "error", "detail"}):
            raise RuntimeError("privileged broker returned an invalid refusal response")
        if not isinstance(response.get("error"), str) or not isinstance(response.get("detail"), str):
            raise RuntimeError("privileged broker returned an invalid refusal response")
        return 75 if response["error"] == "EFFECT_UNKNOWN" else 1
    if (
        frozenset(response) != frozenset({"schema", "ok", "replayed", "receipt"})
        or not isinstance(response.get("replayed"), bool)
        or not isinstance(response.get("receipt"), dict)
    ):
        raise RuntimeError("privileged broker returned an invalid success response")
    validated = validate_request(request)
    digest = hashlib.sha256(canonical_request_bytes(validated)).hexdigest()
    release_name = _RELEASE_ROOT.name
    expected_release = release_name if re.fullmatch(r"[0-9a-f]{40}", release_name) else None
    receipt = validate_terminal_receipt(
        response["receipt"],
        expected_request_id=validated.request_id,
        expected_request_sha256=digest,
        expected_release_sha=expected_release,
        expected_action=validated.action,
    )
    return 0 if receipt["outcome"] == "SUCCEEDED" else 1


def _main_status(values: Sequence[str], namespace: argparse.Namespace) -> int:
    request = build_status_request(values)
    sys.stderr.write(f"mmx-admin request_id={request['request_id']}\n")
    sys.stderr.flush()
    try:
        response = send_status_request(request, socket_path=DEFAULT_SOCKET)
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"mmx-admin transport failure: {exc}\n")
        return 69
    exit_code = _status_exit_code(response, str(request["request_id"]))
    if exit_code == 1:
        sys.stderr.write("mmx-admin status response refused or invalid\n")
        return 1
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    namespace = parser.parse_args(values)
    if namespace.action == _STATUS_ACTION:
        return _main_status(values, namespace)
    request = build_request(values)
    sys.stderr.write(f"mmx-admin request_id={request['request_id']}\n")
    sys.stderr.flush()
    try:
        response = send_request(request, socket_path=DEFAULT_SOCKET)
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"mmx-admin transport failure: {exc}\n")
        return 69
    try:
        exit_code = _effect_exit_code(response, request)
    except (BrokerTrustError, RuntimeError) as exc:
        sys.stderr.write(f"mmx-admin effect response refused or invalid: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(response, sort_keys=True, separators=(",", ":")) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
