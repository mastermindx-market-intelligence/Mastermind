"""Closed model-visible schemas for the bounded GitHub exact-repair app."""
from __future__ import annotations

import dataclasses
import hashlib
from typing import Mapping

from integrations.mastermind_github_app.prepared_token import (
    MAX_TOKEN_CHARS,
    canonical_json,
)


SERVER_NAME = "mastermind-github-exact-repair"
SERVER_VERSION = "0.2.0"

_OPERATION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,191}$"
_OID_PATTERN = r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_PATH_PATTERN = r"^(?!/)(?!.*(?:^|/)\.\.?/)(?!.*\\)(?!.*//)[^\x00-\x1f\x7f]{1,512}$"


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: Mapping[str, object]
    annotations: Mapping[str, object]


def _replacement_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["old_text", "new_text"],
        "properties": {
            "old_text": {
                "type": "string",
                "minLength": 1,
                "maxLength": 65_536,
            },
            "new_text": {
                "type": "string",
                "maxLength": 131_072,
            },
        },
    }


def _file_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "expected_blob_oid", "replacements"],
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "maxLength": 512,
                "pattern": _PATH_PATTERN,
            },
            "expected_blob_oid": {"type": "string", "pattern": _OID_PATTERN},
            "replacements": {
                "type": "array",
                "minItems": 1,
                "maxItems": 10,
                "items": _replacement_schema(),
            },
        },
    }


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="prepare_exact_branch_repair",
        description=(
            "Prepare exact unique old/new text replacements for the already-bound "
            "operation-owned non-protected pull-request branch. The app resolves "
            "repository, branch, writer, authority, and allowed paths server-side; "
            "preparation performs no GitHub mutation and never returns complete file bytes."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["operation_key", "expected_head_oid", "files"],
            "properties": {
                "operation_key": {"type": "string", "pattern": _OPERATION_PATTERN},
                "expected_head_oid": {"type": "string", "pattern": _OID_PATTERN},
                "files": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": _file_schema(),
                },
            },
        },
        annotations={
            "title": "Prepare exact branch repair",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
    ToolSpec(
        name="commit_exact_branch_repair",
        description=(
            "Commit exactly one previously prepared exact branch repair after full "
            "principal, authority, carrier, writer, head, blob, effect, and current-source "
            "revalidation."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["prepared_token"],
            "properties": {
                "prepared_token": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_TOKEN_CHARS,
                }
            },
        },
        annotations={
            "title": "Commit exact branch repair",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
    ToolSpec(
        name="reconcile_exact_branch_repair",
        description=(
            "Read canonical GitHub evidence for one prepared exact branch repair and "
            "classify it as NOT_APPLIED, APPLIED, or EFFECT_UNKNOWN without resubmitting."
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": [
                "operation_key",
                "normalized_effect_digest",
                "prepared_token",
            ],
            "properties": {
                "operation_key": {"type": "string", "pattern": _OPERATION_PATTERN},
                "normalized_effect_digest": {
                    "type": "string",
                    "pattern": _SHA256_PATTERN,
                },
                "prepared_token": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_TOKEN_CHARS,
                },
            },
        },
        annotations={
            "title": "Reconcile exact branch repair",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
)

TOOL_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}
SCHEMA_DIGEST = hashlib.sha256(
    canonical_json(
        [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "annotations": spec.annotations,
            }
            for spec in TOOL_SPECS
        ]
    )
).hexdigest()


__all__ = [
    "SCHEMA_DIGEST",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TOOL_BY_NAME",
    "TOOL_SPECS",
    "ToolSpec",
]
