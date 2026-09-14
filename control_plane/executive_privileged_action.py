"""Closed request contract for Executive OS privileged host actions.

This module deliberately contains no privileged effects.  It converts an
untrusted JSON-like mapping into one immutable, validated request and then maps
that request to an argv chosen entirely by the reviewed action catalog.  A
caller can select an action and reviewed scalar values; it can never select an
executable, shell fragment, or filesystem path.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Mapping

from ops.executive_os.provider_worker_slots import all_slots, get_slot


REQUEST_SCHEMA = "mastermind.executive_privileged_action_request.v1"
STATUS_REQUEST_SCHEMA = "mastermind.executive_privileged_action_status_request.v1"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_UTC_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_REQUEST_KEYS = frozenset({"schema", "request_id", "action", "args"})
_STATUS_REQUEST_KEYS = frozenset({"schema", "request_id"})
_REVIEWED_SLOT_IDS = frozenset(slot.slot_id for slot in all_slots())
_COMPANY_SLOT = get_slot("codex-01")
_COMPANY_BINDING = _COMPANY_SLOT.workspace_binding_class
_COMPANY_CREDENTIAL_KINDS = frozenset(_COMPANY_SLOT.allowed_credential_kinds)

SERVICE_ACTIONS = frozenset(
    {
        "executive.services.start",
        "executive.services.stop",
        "executive.services.restart",
    }
)
WORKER_AUTH_ACTIONS = frozenset(
    {
        "executive.worker_auth.verify_only",
        "executive.worker_auth.verify_ready",
        "executive.worker_auth.recover_transaction",
    }
)
PRIVILEGED_ACTIONS = SERVICE_ACTIONS | WORKER_AUTH_ACTIONS
ACTION_EFFECT_CLASS = {
    "executive.services.start": "SERVICE_CONTROL",
    "executive.services.stop": "SERVICE_CONTROL",
    "executive.services.restart": "SERVICE_CONTROL",
    "executive.worker_auth.verify_only": "CREDENTIAL_ADMIN_READINESS",
    "executive.worker_auth.verify_ready": "CREDENTIAL_ADMIN_READINESS",
    "executive.worker_auth.recover_transaction": "CREDENTIAL_ADMIN_RECOVERY",
}


class PrivilegedActionError(ValueError):
    """The request is outside the reviewed privileged-action contract."""


@dataclasses.dataclass(frozen=True)
class PrivilegedActionRequest:
    schema: str
    request_id: str
    action: str
    args: tuple[tuple[str, str], ...]

    @property
    def effect_class(self) -> str:
        return ACTION_EFFECT_CLASS[self.action]

    def args_dict(self) -> dict[str, str]:
        return dict(self.args)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "request_id": self.request_id,
            "action": self.action,
            "args": self.args_dict(),
        }


ValidatedPrivilegedAction = PrivilegedActionRequest


@dataclasses.dataclass(frozen=True)
class PrivilegedActionStatusRequest:
    schema: str
    request_id: str

    def to_dict(self) -> dict[str, object]:
        return {"schema": self.schema, "request_id": self.request_id}


def _require_exact_keys(mapping: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    observed = frozenset(mapping)
    if observed != expected:
        raise PrivilegedActionError(
            f"{label} keys must be exactly {sorted(expected)}; got {sorted(observed)}"
        )


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PrivilegedActionError(f"{field} must be a non-empty string")
    return value


def _validate_slot_id(value: Any) -> str:
    slot_id = _require_string(value, "slot_id")
    if slot_id not in _REVIEWED_SLOT_IDS:
        raise PrivilegedActionError("slot_id is not in the reviewed worker inventory")
    return slot_id


def _validate_expiry(value: Any) -> str:
    expiry = _require_string(value, "credential_expires_at")
    if _UTC_RE.fullmatch(expiry) is None:
        raise PrivilegedActionError(
            "credential_expires_at must be exact UTC YYYY-MM-DDTHH:MM:SSZ"
        )
    try:
        parsed = dt.datetime.strptime(expiry, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise PrivilegedActionError("credential_expires_at is not a valid UTC timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != expiry:
        raise PrivilegedActionError("credential_expires_at is not canonical UTC")
    return expiry


def _validate_optional_slot_args(args: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    if not args:
        return ()
    _require_exact_keys(args, frozenset({"slot_id"}), "arguments")
    return (("slot_id", _validate_slot_id(args["slot_id"])),)


def _validate_verify_ready_args(args: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    keys = frozenset(args)
    slot_keys = frozenset({"slot_id", "credential_expires_at"})
    company_keys = frozenset(
        {
            "expected_credential_kind",
            "workspace_binding_class",
            "credential_expires_at",
        }
    )
    if "slot_id" in keys and keys != slot_keys:
        raise PrivilegedActionError("slot_id mode cannot include policy override arguments")
    if keys == slot_keys:
        return tuple(
            sorted(
                {
                    "slot_id": _validate_slot_id(args["slot_id"]),
                    "credential_expires_at": _validate_expiry(args["credential_expires_at"]),
                }.items()
            )
        )
    if keys != company_keys:
        raise PrivilegedActionError(
            "verify_ready arguments must select a reviewed slot or the complete company policy"
        )
    kind = _require_string(args["expected_credential_kind"], "expected_credential_kind")
    if kind not in _COMPANY_CREDENTIAL_KINDS:
        raise PrivilegedActionError("expected_credential_kind is not reviewed for the company slot")
    binding = _require_string(args["workspace_binding_class"], "workspace_binding_class")
    if binding != _COMPANY_BINDING:
        raise PrivilegedActionError("workspace_binding_class is not the reviewed company binding")
    return tuple(
        sorted(
            {
                "expected_credential_kind": kind,
                "workspace_binding_class": binding,
                "credential_expires_at": _validate_expiry(args["credential_expires_at"]),
            }.items()
        )
    )


def validate_request(raw: Mapping[str, Any]) -> ValidatedPrivilegedAction:
    if not isinstance(raw, Mapping):
        raise PrivilegedActionError("privileged request must be a mapping")
    _require_exact_keys(raw, _REQUEST_KEYS, "request")
    schema = _require_string(raw["schema"], "schema")
    if schema != REQUEST_SCHEMA:
        raise PrivilegedActionError("unsupported privileged request schema")
    request_id = _require_string(raw["request_id"], "request_id")
    if _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise PrivilegedActionError("request_id is not a bounded safe token")
    action = _require_string(raw["action"], "action")
    if action not in PRIVILEGED_ACTIONS:
        raise PrivilegedActionError(f"unknown privileged action: {action}")
    args = raw["args"]
    if not isinstance(args, Mapping):
        raise PrivilegedActionError("arguments must be a mapping")

    if action in SERVICE_ACTIONS:
        if args:
            raise PrivilegedActionError("service action arguments must be empty")
        validated_args: tuple[tuple[str, str], ...] = ()
    elif action == "executive.worker_auth.verify_ready":
        validated_args = _validate_verify_ready_args(args)
    else:
        validated_args = _validate_optional_slot_args(args)

    return PrivilegedActionRequest(
        schema=schema,
        request_id=request_id,
        action=action,
        args=validated_args,
    )


def validate_status_request(raw: Mapping[str, Any]) -> PrivilegedActionStatusRequest:
    if not isinstance(raw, Mapping):
        raise PrivilegedActionError("privileged status request must be a mapping")
    _require_exact_keys(raw, _STATUS_REQUEST_KEYS, "status request")
    schema = _require_string(raw["schema"], "schema")
    if schema != STATUS_REQUEST_SCHEMA:
        raise PrivilegedActionError("unsupported privileged status request schema")
    request_id = _require_string(raw["request_id"], "request_id")
    if _REQUEST_ID_RE.fullmatch(request_id) is None:
        raise PrivilegedActionError("request_id is not a bounded safe token")
    return PrivilegedActionStatusRequest(schema=schema, request_id=request_id)


def build_argv(request: ValidatedPrivilegedAction, release_root: str | Path) -> tuple[str, ...]:
    root = Path(release_root)
    args = request.args_dict()
    if request.action in SERVICE_ACTIONS:
        verb = request.action.rsplit(".", 1)[1]
        return (
            "/bin/bash",
            str(root / "ops/executive_os/service-control.sh"),
            verb,
        )

    argv: list[str] = [
        "/bin/bash",
        str(root / "ops/executive_os/provision-worker-auth.sh"),
    ]
    if request.action == "executive.worker_auth.verify_only":
        argv.append("--verify-only")
    elif request.action == "executive.worker_auth.verify_ready":
        argv.append("--verify-ready")
    elif request.action == "executive.worker_auth.recover_transaction":
        argv.append("--recover-readiness-transaction")
    else:  # defensive: validated requests cannot reach this branch.
        raise PrivilegedActionError(f"unknown privileged action: {request.action}")

    if "slot_id" in args:
        argv.extend(("--slot-id", args["slot_id"]))
    if "expected_credential_kind" in args:
        argv.extend(("--expected-credential-kind", args["expected_credential_kind"]))
    if "workspace_binding_class" in args:
        argv.extend(("--workspace-binding-class", args["workspace_binding_class"]))
    if "credential_expires_at" in args:
        argv.extend(("--credential-expires-at", args["credential_expires_at"]))
    return tuple(argv)


def canonical_request_bytes(request: ValidatedPrivilegedAction) -> bytes:
    return (
        json.dumps(
            request.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("ascii")


__all__ = [
    "ACTION_EFFECT_CLASS",
    "PRIVILEGED_ACTIONS",
    "REQUEST_SCHEMA",
    "STATUS_REQUEST_SCHEMA",
    "PrivilegedActionError",
    "PrivilegedActionRequest",
    "PrivilegedActionStatusRequest",
    "ValidatedPrivilegedAction",
    "build_argv",
    "canonical_request_bytes",
    "validate_request",
    "validate_status_request",
]
