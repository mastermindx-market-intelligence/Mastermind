"""Closed model-visible schemas for the bounded GitHub patch owner app."""
from __future__ import annotations

import dataclasses
import hashlib
from typing import Mapping

from integrations.mastermind_github_app.prepared_token import (
    MAX_TOKEN_CHARS,
    canonical_json,
)


SERVER_NAME = "mastermind-github-patch"
SERVER_VERSION = "0.1.0"

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


def _file_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "expected_blob_oid", "unified_diff"],
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "maxLength": 512,
                "pattern": _PATH_PATTERN,
            },
            "expected_blob_oid": {"type": "string", "pattern": _OID_PATTERN},
            "unified_diff": {
                "type": "string",
                "minLength": 1,
                "maxLength": 65_536,
            },
        },
    }


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="prepare_branch_patch",
        description=(
            "Prepare a strict bounded patch for the already-bound operation-owned feature branch. "
            "The app resolves repository, branch, writer, authority, and allowed paths server-side; "
            "preparation performs no GitHub mutation."
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
            "title": "Prepare bounded branch patch",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
    ToolSpec(
        name="commit_branch_patch",
        description=(
            "Commit exactly one previously prepared branch patch after full current-source, "
            "principal, authority, head, blob, effect, and confirmation revalidation."
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
            "title": "Commit bounded branch patch",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    ),
    ToolSpec(
        name="reconcile_branch_patch",
        description=(
            "Read canonical GitHub evidence for one prepared branch patch and classify it as "
            "NOT_APPLIED, APPLIED, or EFFECT_UNKNOWN without resubmitting."
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
            "title": "Reconcile bounded branch patch",
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
