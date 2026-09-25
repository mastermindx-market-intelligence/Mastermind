#!/usr/bin/env python3
"""One-shot client for privileged-action not-applied reconciliation."""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Mapping, Sequence

_RELEASE_ROOT = Path(__file__).resolve().parents[1]
if str(_RELEASE_ROOT) not in sys.path:
    sys.path.insert(0, str(_RELEASE_ROOT))

from control_plane.executive_privileged_broker import (
    RECONCILE_REQUEST_SCHEMA,
    WIRE_RESPONSE_SCHEMA,
    validate_reconcile_not_applied_request,
    validate_reconciliation_record,
)


DEFAULT_SOCKET = Path("/var/run/mastermind-executive/privileged.sock")
DEFAULT_CLIENT_TIMEOUT_SECONDS = 30
_MAX_RESPONSE_BYTES = 128 * 1024


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile one stale privileged verify_ready marker as not applied."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    reconcile = subparsers.add_parser("reconcile-not-applied")
    reconcile.add_argument("--request-id", required=True)
    reconcile.add_argument("--request-sha256", required=True)
    reconcile.add_argument("--marker-sha256", required=True)
    reconcile.add_argument("--marker-release-sha", required=True)
    reconcile.add_argument("--readiness-receipt-sha256", required=True)
    reconcile.add_argument("--expected-credential-kind", required=True)
    reconcile.add_argument("--workspace-binding-class", required=True)
    reconcile.add_argument("--credential-expires-at", required=True)
    return parser


def build_reconcile_request(argv: Sequence[str]) -> dict[str, str]:
    args = _parser().parse_args(list(argv))
    if args.command != "reconcile-not-applied":
        raise AssertionError(args.command)
    raw = {
        "schema": RECONCILE_REQUEST_SCHEMA,
        "target_request_id": args.request_id,
        "target_request_sha256": args.request_sha256,
        "target_marker_sha256": args.marker_sha256,
        "target_release_sha": args.marker_release_sha,
        "readiness_receipt_sha256": args.readiness_receipt_sha256,
        "expected_credential_kind": args.expected_credential_kind,
        "workspace_binding_class": args.workspace_binding_class,
        "credential_expires_at": args.credential_expires_at,
    }
    return validate_reconcile_not_applied_request(raw).to_dict()


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
    try:
        value = json.loads(bytes(buffer[:-1]).decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("privileged broker returned invalid JSON") from exc
    if not isinstance(value, dict) or not isinstance(value.get("ok"), bool):
        raise RuntimeError("privileged broker returned an invalid response")
    return value


def send_reconcile_request(
    request: Mapping[str, object],
    *,
    socket_path: Path = DEFAULT_SOCKET,
    timeout_seconds: int = DEFAULT_CLIENT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    validated = validate_reconcile_not_applied_request(request)
    payload = (
        json.dumps(validated.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("ascii")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        connection.settimeout(timeout_seconds)
        connection.connect(str(socket_path))
        connection.sendall(payload)
        return _read_response(connection)
    finally:
        connection.close()


def validate_reconcile_response(
    response: Mapping[str, object],
    *,
    expected_request_id: str,
) -> dict[str, object]:
    if not isinstance(response, Mapping) or response.get("schema") != WIRE_RESPONSE_SCHEMA:
        raise RuntimeError("reconciliation response schema is invalid")
    if response.get("ok") is not True:
        raise RuntimeError("reconciliation request was refused")
    if frozenset(response) != frozenset(
        {"schema", "ok", "reconciled", "replayed", "reconciliation"}
    ):
        raise RuntimeError("reconciliation response keys are invalid")
    if response.get("reconciled") is not True or not isinstance(
        response.get("replayed"), bool
    ):
        raise RuntimeError("reconciliation response state is invalid")
    record = response.get("reconciliation")
    if not isinstance(record, Mapping):
        raise RuntimeError("reconciliation response has no record")
    validated = validate_reconciliation_record(
        record, expected_request_id=expected_request_id
    )
    return {**dict(response), "reconciliation": validated}


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    request = build_reconcile_request(values)
    target = request["target_request_id"]
    sys.stderr.write(f"mmx-privileged-reconcile target_request_id={target}\n")
    sys.stderr.flush()
    try:
        response = send_reconcile_request(request)
    except (OSError, RuntimeError, UnicodeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"mmx-privileged-reconcile transport failure: {exc}\n")
        return 69
    if response.get("ok") is False:
        if frozenset(response) != frozenset({"schema", "ok", "error", "detail"}):
            sys.stderr.write("mmx-privileged-reconcile invalid refusal response\n")
            return 1
        sys.stderr.write(
            "mmx-privileged-reconcile refused: "
            f"{response.get('error')}: {response.get('detail')}\n"
        )
        return 1
    try:
        validated = validate_reconcile_response(
            response, expected_request_id=str(target)
        )
    except RuntimeError as exc:
        sys.stderr.write(f"mmx-privileged-reconcile invalid response: {exc}\n")
        return 1
    sys.stdout.write(json.dumps(validated, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
