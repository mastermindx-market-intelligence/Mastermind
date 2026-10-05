"""Static schema surface for the bounded Company Dialogue COO-principal facet.

This is a distinct provider-facing projection over the existing Dialogue V2
transport. It owns no target selection, identity lookup, persistence, retry,
wake, Runtime lifecycle, or authority. Trusted binding facts remain absent
from every model-visible input.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from integrations.mastermind_company_mcp.schemas import ToolSpec
from integrations.slack_agent_dialogue.contract import (
    DialogueContractError,
    MAX_BOUNDED_TEXT_CHARS,
    MAX_EVIDENCE_REFS,
    MAX_SUMMARY_CHARS,
    MAX_TEXT_CHARS,
    validate_body,
    validate_evidence_ref,
)

PRINCIPAL_SERVER_NAME = "mastermind-company-dialogue-principal"
PRINCIPAL_SERVER_IDENTITY = "mastermind-company-dialogue-principal-mcp"
PRINCIPAL_SERVER_VERSION = "0.1.0"
PRINCIPAL_RESULT_SCHEMA = "mastermind.company_dialogue_principal_mcp_result.v1"

MAX_REQUEST_BYTES = 32 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_ERROR_MESSAGE_CHARS = 240

ERROR_CODES = frozenset(
    {
        "INVALID_REQUEST",
        "BINDING_UNAVAILABLE",
        "DIALOGUE_REFUSED",
        "SERVICE_UNAVAILABLE",
        "EFFECT_FENCE_UNAVAILABLE",
        "EFFECT_UNKNOWN",
        "INTERNAL_ERROR",
    }
)

_SECRET_SHAPED_RE = re.compile(
    r"(?i)(?:xox[a-z]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"sk-[A-Za-z0-9_-]{20,}|bearer\s+[A-Za-z0-9._~-]{16,})"
)
_MESSAGE_KEY_RE = re.compile(r"\Aasd-[a-z0-9][a-z0-9-]{7,95}\Z")


class PrincipalGatewayError(RuntimeError):
    """One fixed principal-facade refusal."""

    def __init__(self, code: str, message: str | None = None) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown company-dialogue principal error code")
        super().__init__(message or code)
        self.code = code


def _string(
    *, max_length: int, min_length: int = 1, pattern: str | None = None
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "string",
        "minLength": min_length,
        "maxLength": max_length,
    }
    if pattern is not None:
        value["pattern"] = pattern
    return value


_EVIDENCE_REFS = {
    "type": "array",
    "maxItems": MAX_EVIDENCE_REFS,
    "uniqueItems": True,
    "items": {
        "type": "string",
        "minLength": 1,
        "maxLength": MAX_SUMMARY_CHARS,
        "pattern": r"^https://(?:github\.com|linear\.app)/",
    },
}
def _object(
    properties: Mapping[str, Any], *, required: tuple[str, ...] = ()
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if required:
        result["required"] = list(required)
    return result


_OUTPUT_DESCRIPTION = (
    "mastermind.company_dialogue_principal_mcp_result.v1 fixed bounded envelope. "
    "A successful transport edge is not Executive lifecycle, source release, "
    "production acceptance, or new mission authority."
)

PRINCIPAL_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="read_thread",
        description=(
            "Read the already-bound exact Company Dialogue thread. The caller "
            "cannot select a child, channel, thread, principal, mission, or context."
        ),
        input_schema=_object({}),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=True,
    ),
    ToolSpec(
        name="ruling",
        description=(
            "Reply to the already-bound worker decision request with one role-correct "
            "COO ruling. Authority class and option remain subject to the existing "
            "Dialogue authority adjudicator."
        ),
        input_schema=_object(
            {
                "authority_class": {
                    "type": "string",
                    "enum": ["WITHIN_COMMISSION"],
                },
                "selected_option": _string(
                    max_length=32,
                    pattern=r"^opt-[a-z0-9][a-z0-9-]{1,31}$",
                ),
                "decision": _string(max_length=MAX_TEXT_CHARS),
                "rationale": _string(max_length=MAX_TEXT_CHARS),
                "evidence_refs": _EVIDENCE_REFS,
            },
            required=(
                "authority_class",
                "selected_option",
                "decision",
                "rationale",
            ),
        ),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=False,
    ),
    ToolSpec(
        name="continue",
        description=(
            "Continue the already-bound live subordinate within the current "
            "commission. Scope change is structurally fixed false and is not "
            "model-selectable."
        ),
        input_schema=_object(
            {
                "instruction": _string(max_length=MAX_TEXT_CHARS),
                "stop_condition": _string(max_length=MAX_BOUNDED_TEXT_CHARS),
                "evidence_refs": _EVIDENCE_REFS,
            },
            required=("instruction", "stop_condition"),
        ),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=False,
    ),
    ToolSpec(
        name="stop",
        description=(
            "Send one terminal STOP edge to the already-bound subordinate. This "
            "does not create a successor child or release any source/runtime lease."
        ),
        input_schema=_object(
            {
                "reason": _string(max_length=MAX_TEXT_CHARS),
                "next_authority": {
                    "type": "string",
                    "enum": ["sol", "chairman", "canonical_ref"],
                },
                "evidence_refs": _EVIDENCE_REFS,
            },
            required=("reason", "next_authority"),
        ),
        output_description=_OUTPUT_DESCRIPTION,
        read_only=False,
    ),
)

_TOOLS_BY_NAME = {spec.name: spec for spec in PRINCIPAL_TOOL_SPECS}
_MESSAGE_TYPES = {
    "ruling": "RULING",
    "continue": "CONTINUE",
    "stop": "STOP",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise PrincipalGatewayError("INVALID_REQUEST")


def canonical_principal_json(value: Any) -> bytes:
    try:
        return json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise PrincipalGatewayError("INVALID_REQUEST") from None


def _validated_evidence_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_EVIDENCE_REFS:
        raise PrincipalGatewayError("INVALID_REQUEST")
    try:
        refs = [validate_evidence_ref(item) for item in value]
    except DialogueContractError:
        raise PrincipalGatewayError("INVALID_REQUEST") from None
    if len(refs) != len(set(refs)):
        raise PrincipalGatewayError("INVALID_REQUEST")
    return refs


def validate_principal_tool_arguments(
    tool_name: str, arguments: Any
) -> dict[str, Any]:
    """Normalize one model-visible principal call; binding fields are absent."""

    spec = _TOOLS_BY_NAME.get(tool_name)
    if spec is None:
        raise PrincipalGatewayError("INVALID_REQUEST")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise PrincipalGatewayError("INVALID_REQUEST")
    raw = dict(arguments)
    if len(canonical_principal_json({"arguments": raw})) > MAX_REQUEST_BYTES:
        raise PrincipalGatewayError("INVALID_REQUEST")
    allowed = set(spec.input_schema["properties"])
    if not set(raw) <= allowed:
        raise PrincipalGatewayError("INVALID_REQUEST")
    required = set(spec.input_schema.get("required", ()))
    if not required <= set(raw):
        raise PrincipalGatewayError("INVALID_REQUEST")
    if tool_name == "read_thread":
        if raw:
            raise PrincipalGatewayError("INVALID_REQUEST")
        return {}

    evidence_refs = _validated_evidence_refs(raw.pop("evidence_refs", None))
    message_type = _MESSAGE_TYPES[tool_name]
    if tool_name == "ruling":
        raw["canonical_ref"] = None
    elif tool_name == "continue":
        raw["scope_change"] = False
    try:
        body = validate_body(message_type, raw)
    except DialogueContractError:
        raise PrincipalGatewayError("INVALID_REQUEST") from None
    return {**body, "evidence_refs": evidence_refs}


def _safe_message(code: str, message: Any) -> str:
    if not isinstance(message, str) or _SECRET_SHAPED_RE.search(message):
        return code
    if any(ord(character) < 32 or ord(character) == 127 for character in message):
        return code
    cleaned = message.strip()
    return (cleaned or code)[:MAX_ERROR_MESSAGE_CHARS]


def principal_result_envelope(tool: str, *, data: Any) -> dict[str, Any]:
    envelope = {
        "schema": PRINCIPAL_RESULT_SCHEMA,
        "tool": tool if tool in _TOOLS_BY_NAME else "unknown",
        "ok": True,
        "server_version": PRINCIPAL_SERVER_VERSION,
        "data": _jsonable(data),
        "error": None,
    }
    if len(canonical_principal_json(envelope)) > MAX_RESPONSE_BYTES:
        raise PrincipalGatewayError("INTERNAL_ERROR")
    return envelope


def principal_error_envelope(
    tool: str,
    *,
    code: str,
    message: Any,
    detail_code: str | None = None,
    reconciliation_message_key: str | None = None,
) -> dict[str, Any]:
    if code not in ERROR_CODES:
        code = "INTERNAL_ERROR"
    error: dict[str, Any] = {
        "code": code,
        "message": _safe_message(code, message),
    }
    if (
        isinstance(detail_code, str)
        and re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", detail_code)
    ):
        error["detail_code"] = detail_code
    data = None
    if (
        isinstance(reconciliation_message_key, str)
        and _MESSAGE_KEY_RE.fullmatch(reconciliation_message_key) is not None
    ):
        data = {"message_key": reconciliation_message_key}
    return {
        "schema": PRINCIPAL_RESULT_SCHEMA,
        "tool": tool if tool in _TOOLS_BY_NAME else "unknown",
        "ok": False,
        "server_version": PRINCIPAL_SERVER_VERSION,
        "data": data,
        "error": error,
    }


def principal_schema_snapshot() -> dict[str, Any]:
    return {
        "server_name": PRINCIPAL_SERVER_NAME,
        "server_identity": PRINCIPAL_SERVER_IDENTITY,
        "server_version": PRINCIPAL_SERVER_VERSION,
        "result_schema": PRINCIPAL_RESULT_SCHEMA,
        "errors": sorted(ERROR_CODES),
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": copy.deepcopy(spec.input_schema),
                "output_description": spec.output_description,
                "annotations": copy.deepcopy(spec.annotations),
                "read_only": spec.read_only,
            }
            for spec in PRINCIPAL_TOOL_SPECS
        ],
    }


def principal_schema_snapshot_sha256() -> str:
    return hashlib.sha256(
        canonical_principal_json(principal_schema_snapshot())
    ).hexdigest()


def principal_tool_schema_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "annotations": copy.deepcopy(spec.annotations),
            "input_schema": copy.deepcopy(spec.input_schema),
            "name": spec.name,
            "output_schema": None,
        }
        for spec in sorted(PRINCIPAL_TOOL_SPECS, key=lambda item: item.name)
    ]


def principal_tool_schema_digest() -> str:
    return hashlib.sha256(
        canonical_principal_json(principal_tool_schema_snapshot())
    ).hexdigest()


# Source-candidate literals. Updating any tool description, schema, or annotation
# requires explicit review and rotation of both values.
PRINCIPAL_SCHEMA_SNAPSHOT_SHA256 = (
    "29926ecd02d5391fa80beccbd5d6e8d785cc190f77b6263d060fd8d080e3e66f"
)
PRINCIPAL_TOOL_SCHEMA_DIGEST = (
    "d45c0f8fe2451c726757c42be729e0e49fc5b2637c33efc97dee00168fab7abd"
)


__all__ = [
    "ERROR_CODES",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "PRINCIPAL_RESULT_SCHEMA",
    "PRINCIPAL_SCHEMA_SNAPSHOT_SHA256",
    "PRINCIPAL_SERVER_IDENTITY",
    "PRINCIPAL_SERVER_NAME",
    "PRINCIPAL_SERVER_VERSION",
    "PRINCIPAL_TOOL_SCHEMA_DIGEST",
    "PRINCIPAL_TOOL_SPECS",
    "PrincipalGatewayError",
    "canonical_principal_json",
    "principal_error_envelope",
    "principal_result_envelope",
    "principal_schema_snapshot",
    "principal_schema_snapshot_sha256",
    "principal_tool_schema_digest",
    "principal_tool_schema_snapshot",
    "validate_principal_tool_arguments",
]
