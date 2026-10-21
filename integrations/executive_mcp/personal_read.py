"""Static installed read-only Executive MCP profile for Personal ChatGPT seats.

This profile publishes only the four legacy Executive readers.  It reuses the
existing installed CeoIngress v1 read owner and adds no Runtime access,
submission route, lifecycle, queue, retry, credential, or permission plane.
"""
from __future__ import annotations

import dataclasses
import hashlib
from typing import Any

from integrations.executive_mcp import schemas as legacy

PERSONAL_READ_PROFILE = "personal_read"
PERSONAL_READ_SERVER_NAME = f"{legacy.SERVER_NAME}-personal-read"
PERSONAL_READ_SERVER_VERSION = "1.0.1"
PERSONAL_READ_TOOL_NAMES = (
    "executive_state",
    "executive_inbox",
    "executive_job",
    "ceo_intent_status",
)

_BY_NAME = {spec.name: spec for spec in legacy.TOOL_SPECS}
_PERSONAL_DESCRIPTIONS = {
    "executive_state": (
        "Read-only snapshot of current Executive OS grounding, runtime counts, "
        "attention counts, strategic summary, and explicitly degraded inputs."
    ),
    "executive_inbox": (
        "Read-only canonical Executive OS attention projection, without changing "
        "priority, eligibility, ownership, or lifecycle state."
    ),
    "executive_job": (
        "Read-only inspection of one durable Executive OS Job by job_id, including "
        "status, attempts, bounded result/error fields, next actions, and timestamps."
    ),
    "ceo_intent_status": (
        "Read-only lookup of one existing CEO intent receipt by intent_id."
    ),
}


def _personal_spec(name: str) -> legacy.ToolSpec:
    base = _BY_NAME[name]
    input_schema = base.input_schema
    if name == "ceo_intent_status":
        input_schema = {
            "type": "object",
            "properties": {
                "intent_id": {
                    "type": "string",
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$",
                    "maxLength": 64,
                    "description": "Existing CEO intent identifier.",
                }
            },
            "required": ["intent_id"],
            "additionalProperties": False,
        }
    return dataclasses.replace(
        base,
        description=_PERSONAL_DESCRIPTIONS[name],
        input_schema=input_schema,
    )


PERSONAL_READ_TOOL_SPECS = tuple(_personal_spec(name) for name in PERSONAL_READ_TOOL_NAMES)


def validate_personal_read_tool_arguments(tool_name: str, arguments: Any) -> dict[str, Any]:
    if tool_name not in PERSONAL_READ_TOOL_NAMES:
        raise legacy.GatewayError("not_found", f"unknown tool {tool_name!r}")
    return legacy.validate_tool_arguments(tool_name, arguments)


def personal_read_schema_snapshot() -> dict[str, Any]:
    return {
        "server_name": PERSONAL_READ_SERVER_NAME,
        "server_version": PERSONAL_READ_SERVER_VERSION,
        "result_schema": legacy.RESULT_SCHEMA,
        "profile": PERSONAL_READ_PROFILE,
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "output_description": spec.output_description,
                "annotations": spec.annotations,
                "read_only": spec.read_only,
            }
            for spec in PERSONAL_READ_TOOL_SPECS
        ],
    }


def personal_read_schema_snapshot_sha256() -> str:
    return hashlib.sha256(legacy.canonical_json(personal_read_schema_snapshot())).hexdigest()


# Filled from the deterministic snapshot and pinned by acceptance tests.
PERSONAL_READ_SCHEMA_SNAPSHOT_SHA256 = "2f18437a2d187b8c1cc3a46e573f07d32c85c752879f14b90bcf79228125af3f"
