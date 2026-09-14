"""Borrow the accepted Read port inside one Workbench Action runtime.

This module creates no descriptor, executor, lease, audit sink, or cache.  Each
Read operation resolves the runtime's current project binding again, then runs
the synchronous borrowed port through that same runtime's bounded executor.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from integrations.workbench_local_mcp.adapter import (
    BoundWorkbenchReadPort,
    create_bound_read_port,
)
from integrations.workbench_local_mcp.schemas import (
    PROFILE_PRO_READ_PREPARE,
    RESULT_SCHEMA,
    SERVER_VERSION as READ_SERVER_VERSION,
    TOOL_SPECS,
    LocalProfileError,
    ToolSpec,
)
from integrations.workbench_read_mcp.observer import ReadScope

from .contracts import ProjectActionBinding
from .runtime import WorkbenchActionRuntime

WORKSPACE_MANIFEST_TOOL = "workspace_manifest"
READ_PROJECT_FILE_TOOL = "read_project_file"
PREVIEW_TEXT_REPLACE_TOOL = "preview_text_replace"
READ_TOOL_NAMES = (
    WORKSPACE_MANIFEST_TOOL,
    READ_PROJECT_FILE_TOOL,
    PREVIEW_TEXT_REPLACE_TOOL,
)
READ_REFUSAL_CODES = frozenset(
    {
        "INVALID_REQUEST",
        "PROJECT_READ_REFUSED",
        "PREIMAGE_MISMATCH",
        "SOURCE_CHANGED",
        "PREVIEW_NOT_APPLICABLE",
        "PREVIEW_TOO_LARGE",
        "INTERNAL_ERROR",
    }
)
PHASE_A_TOOL_NAMES = (
    *READ_TOOL_NAMES,
    "prepare_text_patch",
    "commit_text_patch",
    "reconcile_text_patch",
)

_READ_SPEC_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}
READ_TOOL_SPECS: tuple[ToolSpec, ...] = tuple(
    _READ_SPEC_BY_NAME[name] for name in READ_TOOL_NAMES
)

_REFERENCE = {"type": "string", "minLength": 1, "maxLength": 256}
_SHA256 = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_COMMITTED_HEAD = {
    "anyOf": [
        {"type": "null"},
        {"type": "string", "pattern": "^[0-9a-f]{40}$"},
    ]
}


def _closed_object(
    properties: dict[str, Any], required: tuple[str, ...]
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_MANIFEST_DATA = _closed_object(
    {
        "capability_state": {"const": "BUILT_NOT_PROVEN"},
        "transport": {"const": "stdio-via-secure-mcp-tunnel"},
        "project_ref": _REFERENCE,
        "profile": {"const": PROFILE_PRO_READ_PREPARE},
        "allowed_paths": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 512},
            "minItems": 1,
            "maxItems": 64,
            "uniqueItems": True,
        },
        "committed_head": _COMMITTED_HEAD,
        "lease_expires_at_ms": {"type": "integer", "minimum": 0},
        "context_ref": _REFERENCE,
        "owner_ref": _REFERENCE,
        "generation": _REFERENCE,
        "supported_tools": {
            "type": "array",
            "prefixItems": [{"const": name} for name in PHASE_A_TOOL_NAMES],
            "minItems": len(PHASE_A_TOOL_NAMES),
            "maxItems": len(PHASE_A_TOOL_NAMES),
        },
        "effects": _closed_object(
            {
                "file_write": {"const": True},
                "process_start": {"const": False},
                "network_call": {"const": False},
                "durable_prepare": {"const": True},
            },
            ("file_write", "process_start", "network_call", "durable_prepare"),
        ),
    },
    (
        "capability_state",
        "transport",
        "project_ref",
        "profile",
        "allowed_paths",
        "committed_head",
        "lease_expires_at_ms",
        "context_ref",
        "owner_ref",
        "generation",
        "supported_tools",
        "effects",
    ),
)

_READ_DATA = _closed_object(
    {
        "status": {"const": "OK"},
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "context_ref": _REFERENCE,
        "owner_ref": _REFERENCE,
        "generation": _REFERENCE,
        "view_kind": {"const": "WORKING_TREE"},
        "committed_head": _COMMITTED_HEAD,
        "file_sha256": _SHA256,
        "file_identity_digest": _SHA256,
        "file_bytes": {"type": "integer", "minimum": 0, "maximum": 1048576},
        "content": {"type": "string", "maxLength": 32768},
        "content_bytes": {"type": "integer", "minimum": 0, "maximum": 32768},
        "total_lines": {"type": "integer", "minimum": 0},
        "line_start": {"type": "integer", "minimum": 0},
        "line_end": {"type": "integer", "minimum": 0},
        "truncated": {"type": "boolean"},
        "next_line": {
            "anyOf": [{"type": "null"}, {"type": "integer", "minimum": 0}]
        },
        "observed_at_ms": {"type": "integer", "minimum": 0},
        "index_status": {"const": "NOT_OBSERVED"},
        "atomic_workspace_snapshot": {"const": False},
        "observation_digest": _SHA256,
        "project_ref": _REFERENCE,
    },
    (
        "status",
        "relative_path",
        "context_ref",
        "owner_ref",
        "generation",
        "view_kind",
        "committed_head",
        "file_sha256",
        "file_identity_digest",
        "file_bytes",
        "content",
        "content_bytes",
        "total_lines",
        "line_start",
        "line_end",
        "truncated",
        "next_line",
        "observed_at_ms",
        "index_status",
        "atomic_workspace_snapshot",
        "observation_digest",
        "project_ref",
    ),
)

_PREVIEW_DATA = _closed_object(
    {
        "status": {"const": "PREVIEW_ONLY"},
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "preimage_sha256": _SHA256,
        "proposed_sha256": _SHA256,
        "diff": {"type": "string", "maxLength": 98304},
        "change_digest": _SHA256,
        "applied": {"const": False},
        "persisted": {"const": False},
    },
    (
        "status",
        "relative_path",
        "preimage_sha256",
        "proposed_sha256",
        "diff",
        "change_digest",
        "applied",
        "persisted",
    ),
)


def _result_schema(tool: str, data_schema: dict[str, Any]) -> dict[str, Any]:
    return _closed_object(
        {
            "schema": {"const": RESULT_SCHEMA},
            "tool": {"const": tool},
            "ok": {"const": True},
            "server_version": {"const": READ_SERVER_VERSION},
            "profile": {"const": PROFILE_PRO_READ_PREPARE},
            "mutation_allowed": {"const": False},
            "project_ref": _REFERENCE,
            "data": data_schema,
            "error": {"type": "null"},
        },
        (
            "schema",
            "tool",
            "ok",
            "server_version",
            "profile",
            "mutation_allowed",
            "project_ref",
            "data",
            "error",
        ),
    )


READ_OUTPUT_SCHEMAS = {
    WORKSPACE_MANIFEST_TOOL: _result_schema(WORKSPACE_MANIFEST_TOOL, _MANIFEST_DATA),
    READ_PROJECT_FILE_TOOL: _result_schema(READ_PROJECT_FILE_TOOL, _READ_DATA),
    PREVIEW_TEXT_REPLACE_TOOL: _result_schema(PREVIEW_TEXT_REPLACE_TOOL, _PREVIEW_DATA),
}


@dataclasses.dataclass(frozen=True)
class BoundReadComposition:
    """A borrowed port whose only physical execution owner is ``runtime``."""

    runtime: WorkbenchActionRuntime
    port: BoundWorkbenchReadPort

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        observed = await self.runtime.run_io(lambda: self.port.call(name, arguments))
        if name == WORKSPACE_MANIFEST_TOOL and observed.get("ok") is True:
            data = dict(observed["data"])
            data["supported_tools"] = list(PHASE_A_TOOL_NAMES)
            data["effects"] = {
                "file_write": True,
                "process_start": False,
                "network_call": False,
                "durable_prepare": True,
            }
            observed = {**observed, "data": data}
        return observed


def create_bound_read_composition(runtime: WorkbenchActionRuntime) -> BoundReadComposition:
    if not isinstance(runtime, WorkbenchActionRuntime):
        raise ValueError("WORKBENCH_ACTION_RUNTIME_REQUIRED")
    services = runtime.channel_services
    caller = services.caller
    project_ref = services.project_ref

    def resolve_scope() -> ReadScope:
        binding = runtime.resolve_binding(caller, project_ref)
        if type(binding) is not ProjectActionBinding:
            raise LocalProfileError("PROJECT_READ_REFUSED")
        scope = binding.scope
        return ReadScope(
            root_fd=scope.root_fd,
            root_device=scope.root_device,
            root_inode=scope.root_inode,
            context_ref=scope.context_ref,
            owner_ref=scope.owner_ref,
            generation=scope.generation,
            allowed_paths=scope.allowed_paths,
            expires_at_ms=scope.expires_at_ms,
            committed_head=scope.committed_head,
        )

    initial_binding = runtime.resolve_binding(caller, project_ref)
    if type(initial_binding) is not ProjectActionBinding:
        raise ValueError("FIXED_CHANNEL_BINDING_REQUIRED")
    port = create_bound_read_port(
        project_ref,
        PROFILE_PRO_READ_PREPARE,
        initial_binding.scope.allowed_paths,
        resolve_scope,
        services.clock_ms,
    )
    return BoundReadComposition(runtime=runtime, port=port)


__all__ = [
    "PHASE_A_TOOL_NAMES",
    "PREVIEW_TEXT_REPLACE_TOOL",
    "READ_REFUSAL_CODES",
    "READ_OUTPUT_SCHEMAS",
    "READ_PROJECT_FILE_TOOL",
    "READ_TOOL_NAMES",
    "READ_TOOL_SPECS",
    "WORKSPACE_MANIFEST_TOOL",
    "BoundReadComposition",
    "create_bound_read_composition",
]
