"""Static release transport contract. Parsing confers no release authority."""
from __future__ import annotations

import re
from typing import Any

from control_plane import executive_release_contract as contract
from control_plane import executive_release_ingress as ingress
from control_plane.executive_privileged_client import validate_status_response
from integrations.executive_mcp import schemas
from integrations.mastermind_executive_app.release_admission import (
    _PUBLIC_CODES, _UNCERTAIN_CODES,
)

RELEASE_CONTROL_PROFILE = "release_control_v1"
RELEASE_CONTROL_SERVER_VERSION = "1.0.0"
_KEY = {"type": "string", "minLength": 3, "maxLength": 96, "pattern": "^[a-z0-9][a-z0-9-]{2,95}$"}


def _spec(name, description, properties, *, read_only):
    return schemas.ToolSpec(
        name=name, description=description,
        input_schema={"type": "object", "properties": properties,
                      "required": list(properties), "additionalProperties": False},
        output_description="Closed release result from the existing authenticated App and root owner.",
        read_only=read_only,
    )


RELEASE_CONTROL_TOOL_SPECS = (
    _spec("approve_release_transition",
          "Persist approval for one exact release transition through the existing Runtime. "
          "Approval does not install, commit, dispatch or create a Job.",
          {"operation_key": _KEY,
           "action": {"type": "string", "enum": ["executive.release.upgrade", "executive.release.rollback"]},
           "transition_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"}}, read_only=False),
    _spec("prepare_release_transition",
          "Read a preview and a bounded token for an already-approved transition. No release effect occurs.",
          {"operation_key": _KEY, "approved_transition_ref": {"type": "string"}}, read_only=True),
    _spec("commit_prepared_release_transition",
          "Request the prepared release effect. Production commit is disarmed and refuses in this generation.",
          {"prepared_token": {"type": "string", "minLength": 1, "maxLength": ingress.MAX_TOKEN_BYTES}},
          read_only=False),
    _spec("reconcile_release_transition",
          "Read the original approval and broker history for an operation. Never resend or retry an effect.",
          {"operation_key": _KEY}, read_only=True),
)


def validate_release_tool_arguments(name: str, arguments: Any) -> dict:
    try:
        return ingress.validate_arguments(name, arguments)
    except (ValueError, TypeError, RecursionError):
        raise schemas.GatewayError("invalid_input", "invalid release operation or arguments") from None


def unknown_release_result() -> dict:
    return {"ok": False, "error": {"code": "RELEASE_RESPONSE_UNKNOWN"}, "effect": "EFFECT_UNKNOWN"}


def _digest(value, length):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None


def valid_release_result(value, operation, arguments, status_code) -> bool:
    """Check transport shape/correlation; the App authenticates and seals results.

    This deliberately does not construct a principal or a trusted context from
    output bytes. Principal/current authority checks remain in the existing App.
    """
    try:
        if type(value) is not dict or type(value.get("ok")) is not bool:
            return False
        schema = "schema" in value or "operation" in value
        base = {"ok"}
        if schema:
            base |= {"schema", "operation"}
            if value.get("schema") != ingress.RESPONSE_SCHEMA or value.get("operation") != operation:
                return False
        if not value["ok"]:
            if set(value) not in (base | {"error"}, base | {"error", "effect"}):
                return False
            error = value["error"]
            if type(error) is not dict or set(error) != {"code"} or type(error["code"]) is not str:
                return False
            code = error["code"]
            if code == "RELEASE_TRANSPORT_UNAVAILABLE":
                return not schema and status_code == 200 and value.get("effect") == "NONE"
            if code not in _PUBLIC_CODES or ("effect" in value and value["effect"] != "EFFECT_UNKNOWN"):
                return False
            if code in _UNCERTAIN_CODES and value.get("effect") != "EFFECT_UNKNOWN":
                return False
            expected = 202 if value.get("effect") == "EFFECT_UNKNOWN" else 200
            return status_code == expected or (
                not schema and status_code == 400 and code == "RELEASE_ARGUMENTS_INVALID" and "effect" not in value)
        if not schema or status_code != 200:
            return False
        if operation == "approve_release_transition":
            return (set(value) == base | {"approved_transition_ref", "approval_evidence_digest"}
                    and value["approved_transition_ref"] == contract.approval_ref_for(arguments["operation_key"])
                    and _digest(value["approval_evidence_digest"], 64))
        if operation == "prepare_release_transition":
            if set(value) != base | {"preview", "prepared_token", "expires_at_ms"}:
                return False
            ingress.validate_arguments("commit_prepared_release_transition", {"prepared_token": value["prepared_token"]})
            preview = value["preview"]
            return (type(value["expires_at_ms"]) is int and 0 < value["expires_at_ms"] < (1 << 63)
                    and type(preview) is dict and set(preview) == {"action", "target_ref", "from_release", "to_release"}
                    and preview["action"] in ("executive.release.upgrade", "executive.release.rollback")
                    and _digest(preview["target_ref"], 64) and _digest(preview["from_release"], 40)
                    and _digest(preview["to_release"], 40))
        if operation == "reconcile_release_transition":
            if set(value) != base | {"approval", "broker_status"}:
                return False
            if value["approval"] is None:
                return value["broker_status"] is None
            approval = contract.validate_approval_evidence(value["approval"])
            if approval["operation_key"] != arguments["operation_key"]:
                return False
            status = validate_status_response(value["broker_status"], expected_request_id=
                contract.broker_request_id_for(contract.request_fingerprint_for(approval)))
            return status["status"] == "NOT_FOUND"
        # No commit-success shape is admitted while production is disarmed.
        return False
    except (KeyError, TypeError, ValueError, RuntimeError, RecursionError):
        return False
