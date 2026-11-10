#!/usr/bin/env python3
"""Non-root client for the Mastermind privileged-action broker."""
from __future__ import annotations

import argparse
import json
import re
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
    validate_request,
    validate_status_request,
)
from control_plane.executive_privileged_client import (
    BrokerTrustError,
    DEFAULT_CLIENT_TIMEOUT_SECONDS,
    DEFAULT_SOCKET,
    send_effect,
    send_status,
    validate_effect_response,
    validate_status_response,
)


_ACTIONS = (
    "executive.services.start",
    "executive.services.stop",
    "executive.services.restart",
    "executive.services.start_readside",
    "executive.services.start_paid",
    "executive.services.stop_paid",
    "executive.services.stop_readside",
    "executive.worker_auth.verify_only",
    "executive.worker_auth.verify_ready",
    "executive.worker_auth.recover_transaction",
    "executive.worker_auth.issue_due10_incident_grant",
)
_PAID_ACTIONS = frozenset({"executive.services.start_paid", "executive.services.stop_paid"})
_INCIDENT_ACTION = "executive.worker_auth.issue_due10_incident_grant"
_STATUS_ACTION = "status"
_SLOT_IDS = ("codex-01", "codex-pro-01", "codex-pro-02", "codex-pro-03")
_CREDENTIAL_KINDS = ("service-account", "personal-access-token", "device-auth")
_EFFECT_ONLY_FLAGS = (
    ("--expected-definition-sha256", "expected_definition_sha256"),
    ("--slot-id", "slot_id"),
    ("--expected-credential-kind", "expected_credential_kind"),
    ("--workspace-binding-class", "workspace_binding_class"),
    ("--credential-expires-at", "credential_expires_at"),
    ("--requalify-terminal-adverse-sha256", "requalify_terminal_adverse_sha256"),
    ("--renew-device-revalidation-sha256", "renew_device_revalidation_sha256"),
    ("--requalify-company-device-drift-sha256", "requalify_company_device_drift_sha256"),
    ("--requalify-native-probe-drift-sha256", "requalify_native_probe_drift_sha256"),
    ("--recover-current-pin-grant-sha256", "recover_current_pin_grant_sha256"),
    ("--successor-request-id", "successor_request_id"),
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Invoke one reviewed Mastermind privileged action")
    parser.add_argument("action", choices=_ACTIONS + (_STATUS_ACTION,))
    parser.add_argument("--request-id")
    parser.add_argument("--expected-definition-sha256")
    parser.add_argument("--slot-id", choices=_SLOT_IDS)
    parser.add_argument("--expected-credential-kind", choices=_CREDENTIAL_KINDS)
    parser.add_argument("--workspace-binding-class")
    parser.add_argument("--credential-expires-at")
    parser.add_argument("--requalify-terminal-adverse-sha256")
    parser.add_argument("--renew-device-revalidation-sha256")
    parser.add_argument("--requalify-company-device-drift-sha256")
    parser.add_argument("--requalify-native-probe-drift-sha256")
    parser.add_argument("--recover-current-pin-grant-sha256")
    parser.add_argument("--successor-request-id")
    return parser


def build_request(argv: Sequence[str]) -> dict[str, object]:
    args = _parser().parse_args(list(argv))
    if args.action == _INCIDENT_ACTION:
        # The issuer request identity is explicit and never randomly replaced.
        # Only the designated successor argument exists; caller evidence,
        # authority, body, date, budget, path and source overrides are all
        # rejected here before any request is built.
        if args.request_id is None:
            parser = _parser()
            parser.error("incident issuance requires an explicit --request-id")
        if args.successor_request_id is None:
            parser = _parser()
            parser.error("incident issuance requires --successor-request-id")
        for flag, attribute in _EFFECT_ONLY_FLAGS:
            if attribute != "successor_request_id" and getattr(args, attribute) is not None:
                parser = _parser()
                parser.error(f"incident issuance does not accept {flag}")
    if args.requalify_native_probe_drift_sha256 is not None and args.request_id is None:
        _parser().error("native-probe drift requires an explicit --request-id")
    if args.action in _PAID_ACTIONS and args.request_id is None:
        _parser().error("paid lifecycle requires an explicit --request-id")
    values: dict[str, str] = {}
    if args.expected_definition_sha256 is not None:
        values["expected_definition_sha256"] = args.expected_definition_sha256
    if args.slot_id is not None:
        values["slot_id"] = args.slot_id
    if args.expected_credential_kind is not None:
        values["expected_credential_kind"] = args.expected_credential_kind
    if args.workspace_binding_class is not None:
        values["workspace_binding_class"] = args.workspace_binding_class
    if args.credential_expires_at is not None:
        values["credential_expires_at"] = args.credential_expires_at
    if args.requalify_terminal_adverse_sha256 is not None:
        values["requalify_terminal_adverse_sha256"] = args.requalify_terminal_adverse_sha256
    if args.renew_device_revalidation_sha256 is not None:
        values["renew_device_revalidation_sha256"] = args.renew_device_revalidation_sha256
    if args.requalify_company_device_drift_sha256 is not None:
        values["requalify_company_device_drift_sha256"] = args.requalify_company_device_drift_sha256
    if args.requalify_native_probe_drift_sha256 is not None:
        values["requalify_native_probe_drift_sha256"] = args.requalify_native_probe_drift_sha256
    if args.recover_current_pin_grant_sha256 is not None:
        values["recover_current_pin_grant_sha256"] = args.recover_current_pin_grant_sha256
    if args.successor_request_id is not None:
        values["successor_request_id"] = args.successor_request_id
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


def send_request(
    request: dict[str, object],
    *,
    socket_path: Path = DEFAULT_SOCKET,
    timeout_seconds: int = DEFAULT_CLIENT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    return send_effect(request, socket_path=socket_path, timeout_seconds=timeout_seconds)


def send_status_request(
    request: dict[str, object],
    *,
    socket_path: Path = DEFAULT_SOCKET,
    timeout_seconds: int = DEFAULT_CLIENT_TIMEOUT_SECONDS,
) -> dict[str, object]:
    return send_status(request, socket_path=socket_path, timeout_seconds=timeout_seconds)


def _expected_release_sha() -> str | None:
    release_name = _RELEASE_ROOT.name
    return release_name if re.fullmatch(r"[0-9a-f]{40}", release_name) else None


def _status_exit_code(response: dict[str, object], request_id: str) -> int:
    # A successful query is not evidence that the historical effect succeeded.
    # Correlate it before exposing a terminal/successful retrieval to callers.
    try:
        validated = validate_status_response(response, expected_request_id=request_id)
    except RuntimeError:
        return 1
    status = validated["status"]
    if status in ("TERMINAL", "RECONCILED_NOT_APPLIED"):
        # Zero means trusted retrieval; NOT_APPLIED remains NOT_APPLIED.
        return 0
    if status == "EFFECT_UNKNOWN":
        return 75
    if status == "NOT_FOUND":
        return 4
    return 1


def _effect_exit_code(
    response: dict[str, object], request: dict[str, object]
) -> int:
    validated = validate_effect_response(response, request, expected_release_sha=_expected_release_sha())
    if validated["ok"] is False:
        return 75 if validated["error"] == "EFFECT_UNKNOWN" else 1
    return 0 if validated["receipt"]["outcome"] == "SUCCEEDED" else 1


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
