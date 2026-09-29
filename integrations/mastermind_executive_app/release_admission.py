"""Authenticated release ingress using the existing single-send client.

No Runtime, signing key, lifecycle writer, or automatic retry lives in the app.
The installed Control and root broker retain current authority decisions.
"""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from control_plane import executive_release_contract as contract
from control_plane.executive_authority import release_principal_projection
from control_plane.executive_release_ingress import (
    RESPONSE_SCHEMA, ReleaseIngressError, project_frame, validate_arguments,
)
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, TRANSPORT_NOT_SENT, TRANSPORT_SENT_UNKNOWN,
)

_PUBLIC_CODES = frozenset({
    "RELEASE_UNAVAILABLE", "RELEASE_APPROVAL_NOT_FOUND", "RELEASE_APPROVAL_EXPIRED",
    "RELEASE_COMMIT_DISARMED", "RELEASE_BROKER_REFUSED", "RELEASE_PRINCIPAL_NOT_CURRENT",
    "RELEASE_APPROVAL_PRINCIPAL_MISMATCH", "RELEASE_APPROVAL_READBACK_UNKNOWN",
    "RELEASE_BROKER_RESPONSE_UNKNOWN", "RELEASE_BROKER_IDENTITY_MISMATCH",
    "RELEASE_BROKER_APPROVAL_CHANGED", "RELEASE_FRAME_INVALID", "RELEASE_ARGUMENTS_INVALID",
    "RELEASE_OWNER_UNCONFIGURED", "RELEASE_REFUSED", "RELEASE_RESPONSE_UNKNOWN",
    "RELEASE_HISTORY_FAMILY_UNQUALIFIED", "RELEASE_HISTORY_ADMISSION_UNQUALIFIED",
    "RELEASE_EFFECT_IN_PROGRESS",
})
_UNCERTAIN_CODES = frozenset({"RELEASE_APPROVAL_READBACK_UNKNOWN",
    "RELEASE_RESPONSE_UNKNOWN", "RELEASE_HISTORY_FAMILY_UNQUALIFIED",
    "RELEASE_HISTORY_ADMISSION_UNQUALIFIED", "RELEASE_EFFECT_IN_PROGRESS"})


def _unknown():
    return {"ok": False, "error": {"code": "RELEASE_RESPONSE_UNKNOWN"},
            "effect": "EFFECT_UNKNOWN"}


def _digest(value, length):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None


def _closed_result(result, *, operation, arguments, principal):
    """Validate before publishing any owner bytes; parsing grants no authority."""
    base = {"schema", "operation", "ok"}
    if (type(result) is not dict or result.get("schema") != RESPONSE_SCHEMA
            or result.get("operation") != operation or type(result.get("ok")) is not bool):
        raise ValueError("invalid release response")
    if not result["ok"]:
        if set(result) not in (base | {"error"}, base | {"error", "effect"}):
            raise ValueError("invalid release refusal")
        error = result["error"]
        if (type(error) is not dict or set(error) != {"code"}
                or type(error["code"]) is not str or error["code"] not in _PUBLIC_CODES
                or ("effect" in result and result["effect"] != "EFFECT_UNKNOWN")
                or (error["code"] in _UNCERTAIN_CODES and result.get("effect") != "EFFECT_UNKNOWN")):
            raise ValueError("invalid release refusal")
        return result
    if operation == "approve_release_transition":
        if (set(result) != base | {"approved_transition_ref", "approval_evidence_digest"}
                or result["approved_transition_ref"] != contract.approval_ref_for(arguments["operation_key"])
                or not _digest(result["approval_evidence_digest"], 64)):
            raise ValueError("invalid approval response")
    elif operation == "prepare_release_transition":
        if set(result) != base | {"preview", "prepared_token", "expires_at_ms"}:
            raise ValueError("invalid preparation response")
        validate_arguments("commit_prepared_release_transition", {"prepared_token": result["prepared_token"]})
        preview = result["preview"]
        if (type(result["expires_at_ms"]) is not int or not 0 < result["expires_at_ms"] < (1 << 63)
                or type(preview) is not dict or set(preview) != {"action", "target_ref", "from_release", "to_release"}
                or preview["action"] not in ("executive.release.upgrade", "executive.release.rollback")
                or not _digest(preview["target_ref"], 64)
                or not _digest(preview["from_release"], 40) or not _digest(preview["to_release"], 40)):
            raise ValueError("invalid preparation response")
    elif operation == "reconcile_release_transition":
        if set(result) != base | {"approval", "broker_status"}:
            raise ValueError("invalid reconciliation response")
        if result["approval"] is None:
            if result["broker_status"] is not None:
                raise ValueError("unbound release history")
        else:
            approval = contract.validate_approval_evidence(result["approval"])
            if (approval["operation_key"] != arguments["operation_key"]
                    or approval["principal_projection"] != release_principal_projection(principal)):
                raise ValueError("unbound release history")
            status = contract.validate_release_terminal_status(
                result["broker_status"], expected_approval=approval)
            if status["state"] not in {"NOT_FOUND", "SUCCEEDED", "ROLLED_BACK", "FAILED_NOT_APPLIED"}:
                raise ValueError("unqualified release history")
    else:
        # Production commit is disarmed; no success shape is admitted here.
        raise ValueError("unexpected release success")
    return result


async def compose_release_admission(*, operation: str, arguments: Any,
        principal: Any, client: CeoIngressClient, socket_path: Path | str) -> dict:
    # Principal is an exact VerifiedPrincipal supplied by app authentication;
    # public arguments have no principal/grant/policy/path/argv fields.
    neutral = principal_projection(principal)
    frame = project_frame(operation, arguments, principal=neutral)
    response = await client.send_frame(socket_path, frame)
    if response.transport == TRANSPORT_NOT_SENT:
        return {"ok": False, "error": {"code": "RELEASE_TRANSPORT_UNAVAILABLE"},
                "effect": "NONE"}
    if response.transport == TRANSPORT_SENT_UNKNOWN:
        return _unknown()
    if response.ok is not True:
        code = (response.error or {}).get("code")
        # A decoded response is not permission to resubmit. Only the owner
        # chooses a typed refusal; no raw local/transport diagnostics escape.
        if type(code) is not str or code not in _PUBLIC_CODES:
            return _unknown()
        result = {"ok": False, "error": {"code": code}}
        if code in _UNCERTAIN_CODES:
            result["effect"] = "EFFECT_UNKNOWN"
        return result
    try:
        return _closed_result(response.result, operation=operation,
                              arguments=arguments, principal=neutral)
    except (KeyError, TypeError, ValueError, RuntimeError, RecursionError):
        return _unknown()
