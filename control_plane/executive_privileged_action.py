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
from ops.executive_os.provider_identity_policy import (
    COMPANY_DEVICE_DRIFT_PREDECESSOR_SHA256,
    NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256,
    NATIVE_PROBE_DRIFT_REQUEST_ID,
)


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

SERVICE_ACTION_VERBS = {
    "executive.services.start": "start",
    "executive.services.stop": "stop",
    "executive.services.restart": "restart",
    "executive.services.start_readside": "start-readside",
    "executive.services.stop_readside": "stop-readside",
}
PAID_SERVICE_ACTION_VERBS = {
    "executive.services.start_paid": "start-paid",
    "executive.services.stop_paid": "stop-paid",
}
PAID_SERVICE_ACTIONS = frozenset(PAID_SERVICE_ACTION_VERBS)
SERVICE_ACTIONS = frozenset(SERVICE_ACTION_VERBS)
WORKER_AUTH_ACTIONS = frozenset(
    {
        "executive.worker_auth.verify_only",
        "executive.worker_auth.verify_ready",
        "executive.worker_auth.recover_transaction",
        "executive.worker_auth.issue_due10_incident_grant",
    }
)
HOST_POLICY_ACTIONS = frozenset(
    {
        "executive.host.prepare_secondary_power_policy",
    }
)
PRIVILEGED_ACTIONS = SERVICE_ACTIONS | PAID_SERVICE_ACTIONS | WORKER_AUTH_ACTIONS | HOST_POLICY_ACTIONS
ACTION_EFFECT_CLASS = {
    **{action:"SERVICE_CONTROL" for action in PAID_SERVICE_ACTIONS},
    "executive.services.start": "SERVICE_CONTROL",
    "executive.services.stop": "SERVICE_CONTROL",
    "executive.services.restart": "SERVICE_CONTROL",
    "executive.services.start_readside": "SERVICE_CONTROL",
    "executive.services.stop_readside": "SERVICE_CONTROL",
    "executive.worker_auth.verify_only": "CREDENTIAL_ADMIN_READINESS",
    "executive.worker_auth.verify_ready": "CREDENTIAL_ADMIN_READINESS",
    "executive.worker_auth.recover_transaction": "CREDENTIAL_ADMIN_RECOVERY",
    "executive.worker_auth.issue_due10_incident_grant":
        "CREDENTIAL_ADMIN_INCIDENT_ISSUANCE",
    # Registered only for closed terminal-receipt validation of the dormant
    # forward transition.  It is deliberately absent from every action set
    # above, so the ordinary v1 action-request route always refuses it; only
    # the dedicated inactive-policy dispatcher can admit it.
    "executive.worker_auth.forward_recover_due10_incident_issuer":
        "CREDENTIAL_ADMIN_INCIDENT_FORWARD_RECOVERY",
    "executive.host.prepare_secondary_power_policy": "HOST_POWER_POLICY",
}
ACTION_EFFECT_UNKNOWN_EXIT_CODE = {
    "executive.host.prepare_secondary_power_policy": 75,
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


def _validate_verify_ready_args(
    args: Mapping[str, Any], request_id: str
) -> tuple[tuple[str, str], ...]:
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
    requalification_keys = (
        "requalify_terminal_adverse_sha256", "renew_device_revalidation_sha256",
        "requalify_company_device_drift_sha256",
        "requalify_native_probe_drift_sha256",
    )
    recovery_keys = ("recover_current_pin_grant_sha256", "successor_request_id")
    allowed = (
        company_keys,
        *(company_keys | {key} for key in requalification_keys),
        company_keys | set(recovery_keys),
    )
    if keys not in allowed:
        raise PrivilegedActionError(
            "verify_ready arguments must select a reviewed slot or the complete company policy"
        )
    kind = _require_string(args["expected_credential_kind"], "expected_credential_kind")
    if kind not in _COMPANY_CREDENTIAL_KINDS:
        raise PrivilegedActionError("expected_credential_kind is not reviewed for the company slot")
    binding = _require_string(args["workspace_binding_class"], "workspace_binding_class")
    if binding != _COMPANY_BINDING:
        raise PrivilegedActionError("workspace_binding_class is not the reviewed company binding")
    values = {
        "expected_credential_kind": kind,
        "workspace_binding_class": binding,
        "credential_expires_at": _validate_expiry(args["credential_expires_at"]),
    }
    for requalification_key in requalification_keys:
        if requalification_key in keys:
            digest = _require_string(args[requalification_key], requalification_key)
            if kind != "device-auth" or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise PrivilegedActionError("requalification requires device-auth and an exact receipt SHA256")
            if (requalification_key == "requalify_company_device_drift_sha256"
                    and digest != COMPANY_DEVICE_DRIFT_PREDECESSOR_SHA256):
                raise PrivilegedActionError("company-device drift preimage is not the reviewed incident")
            if requalification_key == "requalify_native_probe_drift_sha256":
                if digest != NATIVE_PROBE_DRIFT_PREDECESSOR_SHA256:
                    raise PrivilegedActionError("native-probe drift preimage is not the reviewed incident")
                if request_id != NATIVE_PROBE_DRIFT_REQUEST_ID:
                    raise PrivilegedActionError("native-probe drift requires its designated request_id")
            values[requalification_key] = digest
    # The bounded current-pin recovery transition is mutually exclusive with
    # every historical requalification route and must designate itself as the
    # grant's named successor request.  It can never ride on another route.
    recovery_digest = args.get("recover_current_pin_grant_sha256")
    successor_request_id = args.get("successor_request_id")
    if (recovery_digest is None) is not (successor_request_id is None):
        raise PrivilegedActionError(
            "current-pin recovery requires both the grant digest and its designated successor request"
        )
    if recovery_digest is not None:
        if keys & set(requalification_keys):
            raise PrivilegedActionError(
                "current-pin recovery cannot be combined with a requalification route"
            )
        if kind != "device-auth":
            raise PrivilegedActionError("current-pin recovery requires device-auth")
        digest = _require_string(recovery_digest, "recover_current_pin_grant_sha256")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise PrivilegedActionError("current-pin recovery requires an exact grant SHA256")
        designated = _require_string(successor_request_id, "successor_request_id")
        if _REQUEST_ID_RE.fullmatch(designated) is None:
            raise PrivilegedActionError("successor_request_id is not a bounded safe token")
        if designated != request_id:
            raise PrivilegedActionError(
                "successor_request_id must name this request, not a different one"
            )
        values["recover_current_pin_grant_sha256"] = digest
        values["successor_request_id"] = designated
    return tuple(sorted(values.items()))


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

    if action in PAID_SERVICE_ACTIONS:
        _require_exact_keys(args,frozenset({"expected_definition_sha256"}),"arguments")
        value=args["expected_definition_sha256"]
        if type(value) is not str or re.fullmatch(r'[0-9a-f]{64}',value) is None:
            raise PrivilegedActionError("paid definition digest invalid")
        validated_args=(("expected_definition_sha256",value),)
    elif action in SERVICE_ACTIONS:
        if args:
            raise PrivilegedActionError("service action arguments must be empty")
        validated_args: tuple[tuple[str, str], ...] = ()
    elif action in HOST_POLICY_ACTIONS:
        if args:
            raise PrivilegedActionError("host policy action arguments must be empty")
        validated_args = ()
    elif action == "executive.worker_auth.verify_ready":
        validated_args = _validate_verify_ready_args(args, request_id)
    elif action == "executive.worker_auth.issue_due10_incident_grant":
        # The incident issuer takes exactly one designated successor request.
        # Caller evidence, authority, body, date, budget, path and source
        # overrides are all rejected; the outer issuer identity is this
        # request's own explicit id.
        _require_exact_keys(args, frozenset({"successor_request_id"}), "arguments")
        designated = _require_string(args["successor_request_id"], "successor_request_id")
        if _REQUEST_ID_RE.fullmatch(designated) is None:
            raise PrivilegedActionError("successor_request_id is not a bounded safe token")
        if designated == request_id:
            raise PrivilegedActionError(
                "incident issuer request cannot designate itself as its own successor"
            )
        validated_args = (("successor_request_id", designated),)
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
    if request.action in PAID_SERVICE_ACTIONS:
        # An internal original-owner action. No standalone root CLI can mint
        # its held in-process lifecycle context from an argv or receipt.
        raise PrivilegedActionError("paid lifecycle is an internal broker action without argv")
    if request.action in SERVICE_ACTIONS:
        verb = SERVICE_ACTION_VERBS[request.action]
        return (
            "/bin/bash",
            str(root / "ops/executive_os/service-control.sh"),
            verb,
        )
    if request.action in HOST_POLICY_ACTIONS:
        return (
            "/usr/bin/python3",
            "-I",
            "-S",
            "-B",
            str(root / "ops/executive_os/secondary_host_power_policy.py"),
        )
    if request.action == "executive.worker_auth.issue_due10_incident_grant":
        # Internal broker action: derivation runs inside the authenticated root
        # broker process.  There is deliberately no reviewed argv, no shell
        # issuer, and no handbuilt credential path for it.
        raise PrivilegedActionError(
            "incident issuance is an internal broker action without an argv"
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
    if "requalify_terminal_adverse_sha256" in args:
        argv.extend(("--requalify-terminal-adverse-sha256", args["requalify_terminal_adverse_sha256"]))
    if "renew_device_revalidation_sha256" in args:
        argv.extend(("--renew-device-revalidation-sha256", args["renew_device_revalidation_sha256"]))
    if "requalify_company_device_drift_sha256" in args:
        argv.extend(("--requalify-company-device-drift-sha256", args["requalify_company_device_drift_sha256"]))
    if "requalify_native_probe_drift_sha256" in args:
        argv.extend(("--requalify-native-probe-drift-sha256", args["requalify_native_probe_drift_sha256"]))
    if "recover_current_pin_grant_sha256" in args:
        argv.extend(("--recover-current-pin-grant-sha256", args["recover_current_pin_grant_sha256"]))
    if "successor_request_id" in args:
        argv.extend(("--successor-request-id", args["successor_request_id"]))
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
    "ACTION_EFFECT_UNKNOWN_EXIT_CODE",
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
