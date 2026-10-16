"""Immutable, SDK-free contract for the Business Sol HC0 surface probe.

This module owns only the public shape of the read-only probe.  It does not
import the MCP SDK, authenticate callers, bind a runtime, persist observations,
or grant authority.  The contract deliberately exposes correlation evidence
rather than raw OpenAI host metadata.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

RESULT_SCHEMA = "mastermind.host_context_probe.v1"
CONTRACT_SCHEMA = "mastermind.host_context_probe_contract.v1"
SERVER_IDENTITY = "mastermind-surface-probe-mcp"
SERVER_VERSION = "1.0.0"
TOOL_NAME = "inspect_surface_context"
TOOL_TITLE = "Inspect Mastermind surface context"
TOOL_DESCRIPTION = (
    "Report pseudonymous, read-only ChatGPT request-host correlation evidence "
    "for this app generation. The result is never authorization, a runtime "
    "binding, lifecycle state, or proof that any modifying effect occurred."
)
MAX_RESPONSE_BYTES = 16 * 1024

HOST_CONTEXT_KEYS = (
    "openai_session",
    "openai_subject",
    "openai_organization",
    "openai_locale",
    "user_agent_hint",
    "user_location_hint",
)
IDENTIFIER_HOST_FIELDS = frozenset(
    {"openai_session", "openai_subject", "openai_organization"}
)
DEGRADATION_CODES = frozenset(
    {
        "OPENAI_SESSION_ABSENT",
        "OPENAI_SUBJECT_ABSENT",
        "OPENAI_ORGANIZATION_ABSENT",
        "OPENAI_LOCALE_ABSENT",
        "USER_AGENT_HINT_ABSENT",
        "USER_LOCATION_HINT_ABSENT",
        "UNKNOWN_HOST_META_IGNORED",
        "TUNNEL_ATTESTATION_UNAVAILABLE",
        "OAUTH_NOT_CONFIGURED",
    }
)

SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$"
FINGERPRINT_PATTERN = r"^hmac-sha256:[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?:[0-9a-f]{64}$"
DIGEST_PATTERN = r"^[0-9a-f]{64}$"

INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

_IDENTIFIER_ROW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "present": {"type": "boolean"},
        "fingerprint": {
            "oneOf": [
                {"type": "string", "pattern": FINGERPRINT_PATTERN},
                {"type": "null"},
            ]
        },
        "comparison_fingerprint": {
            "oneOf": [
                {"type": "string", "pattern": FINGERPRINT_PATTERN},
                {"type": "null"},
            ]
        },
        "usable_for_authorization": {"const": False},
    },
    "required": [
        "present",
        "fingerprint",
        "comparison_fingerprint",
        "usable_for_authorization",
    ],
    "additionalProperties": False,
}

_HINT_ROW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "present": {"type": "boolean"},
        "fingerprint": {"type": "null"},
        "comparison_fingerprint": {"type": "null"},
        "usable_for_authorization": {"const": False},
    },
    "required": [
        "present",
        "fingerprint",
        "comparison_fingerprint",
        "usable_for_authorization",
    ],
    "additionalProperties": False,
}

HOST_CONTEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        key: deepcopy(
            _IDENTIFIER_ROW_SCHEMA if key in IDENTIFIER_HOST_FIELDS else _HINT_ROW_SCHEMA
        )
        for key in HOST_CONTEXT_KEYS
    },
    "required": list(HOST_CONTEXT_KEYS),
    "additionalProperties": False,
}

OAUTH_POSTURE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "configured": {"const": False},
        "resource": {"type": "null"},
        "scopes": {
            "type": "array",
            "maxItems": 0,
            "items": {"type": "string"},
        },
        "principal_fingerprint": {"type": "null"},
    },
    "required": ["configured", "resource", "scopes", "principal_fingerprint"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "Mastermind Host Context Probe Result",
    "type": "object",
    "properties": {
        "schema": {"const": RESULT_SCHEMA},
        "server_identity": {"const": SERVER_IDENTITY},
        "server_version": {"const": SERVER_VERSION},
        "app_realm": {"type": "string", "pattern": SLUG_PATTERN},
        "app_generation": {"type": "string", "pattern": SLUG_PATTERN},
        "contract_digest": {"type": "string", "pattern": DIGEST_PATTERN},
        "transport_profile": {"type": "string", "pattern": SLUG_PATTERN},
        "fingerprint_key_id": {"type": "string", "pattern": SLUG_PATTERN},
        "fingerprint_key_version": {"type": "string", "pattern": SLUG_PATTERN},
        "fingerprint_scope": {"type": "string", "pattern": SLUG_PATTERN},
        "observed_at": {"type": "string", "format": "date-time"},
        "correlation_only": {"const": True},
        "host_context": HOST_CONTEXT_SCHEMA,
        "oauth_posture": OAUTH_POSTURE_SCHEMA,
        "degradations": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(DEGRADATION_CODES)},
            "uniqueItems": True,
            "maxItems": len(DEGRADATION_CODES),
        },
    },
    "required": [
        "schema",
        "server_identity",
        "server_version",
        "app_realm",
        "app_generation",
        "contract_digest",
        "transport_profile",
        "fingerprint_key_id",
        "fingerprint_key_version",
        "fingerprint_scope",
        "observed_at",
        "correlation_only",
        "host_context",
        "oauth_posture",
        "degradations",
    ],
    "additionalProperties": False,
}

TOOL_ANNOTATIONS: dict[str, bool] = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


def canonical_json(value: object) -> bytes:
    """Return the one canonical UTF-8 encoding used for contract hashing."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def contract_snapshot() -> dict[str, Any]:
    """Return a defensive copy of the complete model-visible HC0 contract."""

    return {
        "schema": CONTRACT_SCHEMA,
        "server_identity": SERVER_IDENTITY,
        "server_version": SERVER_VERSION,
        "tool": {
            "name": TOOL_NAME,
            "title": TOOL_TITLE,
            "description": TOOL_DESCRIPTION,
            "input_schema": deepcopy(INPUT_SCHEMA),
            "output_schema": deepcopy(OUTPUT_SCHEMA),
            "annotations": dict(TOOL_ANNOTATIONS),
        },
        "degradation_codes": sorted(DEGRADATION_CODES),
    }


def contract_digest() -> str:
    """Digest the exact immutable server/tool/schema generation contract."""

    return hashlib.sha256(canonical_json(contract_snapshot())).hexdigest()


CONTRACT_DIGEST = contract_digest()

__all__ = [
    "CONTRACT_DIGEST",
    "CONTRACT_SCHEMA",
    "DEGRADATION_CODES",
    "HOST_CONTEXT_KEYS",
    "HOST_CONTEXT_SCHEMA",
    "IDENTIFIER_HOST_FIELDS",
    "INPUT_SCHEMA",
    "MAX_RESPONSE_BYTES",
    "OAUTH_POSTURE_SCHEMA",
    "OUTPUT_SCHEMA",
    "RESULT_SCHEMA",
    "SERVER_IDENTITY",
    "SERVER_VERSION",
    "TOOL_ANNOTATIONS",
    "TOOL_DESCRIPTION",
    "TOOL_NAME",
    "TOOL_TITLE",
    "canonical_json",
    "contract_digest",
    "contract_snapshot",
]
