"""Authenticated MCP adapter for bounded attended Workbench text patches.

The model sees three explicit actions rather than a generic filesystem or shell:
prepare is read-only, commit consumes one signed preparation, and reconcile is
read-only after response loss. The server never accepts an absolute root,
credential, host selector, shell string, Git push, or browser instruction.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from jsonschema import Draft202012Validator
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from integrations.business_mcp_auth.contracts import (
    AuthAuditSink,
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier

from .contracts import ActionCaller, MAX_ACTION_REF_BYTES, MAX_PATCH_TEXT_BYTES
from .patch_port import ProjectActionRefused

PREPARE_TOOL = "prepare_text_patch"
COMMIT_TOOL = "commit_text_patch"
RECONCILE_TOOL = "reconcile_text_patch"
MAX_ARGUMENT_BYTES = 65536
MAX_RESULT_BYTES = 131072

_PREPARE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_ref": {
            "type": "string",
            "minLength": 1,
            "maxLength": 256,
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
        },
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "mode": {"type": "string", "enum": ["CREATE", "REPLACE"]},
        "expected_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "old_text": {"type": "string", "maxLength": MAX_PATCH_TEXT_BYTES},
        "new_text": {"type": "string", "maxLength": MAX_PATCH_TEXT_BYTES},
    },
    "required": ["project_ref", "relative_path", "mode", "new_text"],
    "additionalProperties": False,
}
_ACTION_REF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action_ref": {
            "type": "string",
            "minLength": 16,
            "maxLength": MAX_ACTION_REF_BYTES,
        }
    },
    "required": ["action_ref"],
    "additionalProperties": False,
}
_PREPARE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"const": "PREPARED"},
        "action_ref": {"type": "string", "minLength": 16, "maxLength": MAX_ACTION_REF_BYTES},
        "project_ref": {"type": "string", "minLength": 1, "maxLength": 256},
        "responsibility_ref": {"type": "string", "minLength": 1, "maxLength": 256},
        "operation_ref": {"type": "string", "minLength": 1, "maxLength": 256},
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "preimage_sha256": {
            "anyOf": [
                {"type": "null"},
                {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            ]
        },
        "postimage_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "expires_at_ms": {"type": "integer", "minimum": 0, "maximum": 2**63 - 1},
    },
    "required": [
        "status",
        "action_ref",
        "project_ref",
        "responsibility_ref",
        "operation_ref",
        "relative_path",
        "preimage_sha256",
        "postimage_sha256",
        "expires_at_ms",
    ],
    "additionalProperties": False,
}
_EFFECT_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"const": "OK"},
        "effect_state": {
            "type": "string",
            "enum": ["NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN"],
        },
        "cleanup_state": {"type": "string", "enum": ["CLEAN", "UNCERTAIN"]},
        "project_ref": {"type": "string", "minLength": 1, "maxLength": 256},
        "responsibility_ref": {"type": "string", "minLength": 1, "maxLength": 256},
        "operation_ref": {"type": "string", "minLength": 1, "maxLength": 256},
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 512},
        "preimage_sha256": {
            "anyOf": [
                {"type": "null"},
                {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            ]
        },
        "postimage_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "observed_sha256": {
            "anyOf": [
                {"type": "null"},
                {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            ]
        },
    },
    "required": [
        "status",
        "effect_state",
        "cleanup_state",
        "project_ref",
        "responsibility_ref",
        "operation_ref",
        "relative_path",
        "preimage_sha256",
        "postimage_sha256",
        "observed_sha256",
    ],
    "additionalProperties": False,
}

PatchPrepare = Callable[[ActionCaller, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]
PatchCommit = Callable[[ActionCaller, object], Awaitable[Mapping[str, Any]]]
PatchReconcile = Callable[[ActionCaller, object], Awaitable[Mapping[str, Any]]]
CallReceiptSink = Callable[[Mapping[str, Any]], None]
CALL_RECEIPT_SCHEMA = "mastermind.workbench_action_call_receipt.v1"


def _snapshot(value: object, maximum: int) -> object:
    text = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    raw = text.encode("utf-8", errors="strict")
    if len(raw) > maximum:
        raise ValueError("payload too large")
    return json.loads(text)


def _error(code: str) -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps({"code": code}, separators=(",", ":")),
            )
        ],
        isError=True,
    )


def _caller_from_access(access: Any, policy: ResourcePolicy) -> ActionCaller:
    caller = ActionCaller(
        subject_digest=access.subject,
        client_ref=access.client_id,
        resource=str(access.resource),
        scopes=tuple(access.scopes),
        expires_at=access.expires_at,
    )
    if (
        type(caller.subject_digest) is not str
        or re.fullmatch(r"[0-9a-f]{64}", caller.subject_digest) is None
        or caller.resource != policy.resource
        or caller.scopes != policy.required_scopes
    ):
        raise ValueError("caller authentication projection refused")
    return caller


def create_authenticated_action_server(
    *,
    authenticator: JwtAuthenticator,
    policy: ResourcePolicy,
    now: Callable[[], int],
    audit_sink: AuthAuditSink,
    prepare_port: PatchPrepare,
    commit_port: PatchCommit,
    reconcile_port: PatchReconcile,
    allowed_hosts: tuple[str, ...],
    call_receipt_sink: CallReceiptSink | None = None,
    allowed_origins: tuple[str, ...] = (),
) -> FastMCP:
    selected_policy = validate_resource_policy(policy)
    if selected_policy.required_scopes != ("workbench.action",):
        raise ValueError("a dedicated workbench.action policy is required")
    if (
        not callable(now)
        or not callable(prepare_port)
        or not callable(commit_port)
        or not callable(reconcile_port)
        or (call_receipt_sink is not None and not callable(call_receipt_sink))
        or type(allowed_hosts) is not tuple
        or not allowed_hosts
    ):
        raise ValueError("explicit Workbench Action services are required")

    prepare_schema = _snapshot(_PREPARE_SCHEMA, 32768)
    ref_schema = _snapshot(_ACTION_REF_SCHEMA, 32768)
    prepare_output = _snapshot(_PREPARE_OUTPUT_SCHEMA, 32768)
    effect_output = _snapshot(_EFFECT_OUTPUT_SCHEMA, 32768)
    prepare_validator = Draft202012Validator(prepare_schema)
    ref_validator = Draft202012Validator(ref_schema)
    prepare_output_validator = Draft202012Validator(prepare_output)
    effect_output_validator = Draft202012Validator(effect_output)
    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=selected_policy,
        now=now,
        audit_sink=audit_sink,
    )

    server = FastMCP(
        name="Mastermind Workbench Action",
        instructions=(
            "Modify only an already-authorized selected project through explicit "
            "prepared text patches. Prepare and reconcile are read-only. Commit "
            "consumes one signed preparation and must never be blindly retried."
        ),
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=selected_policy.issuer,
            resource_server_url=selected_policy.resource,
            required_scopes=list(selected_policy.required_scopes),
        ),
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(allowed_hosts),
            allowed_origins=list(allowed_origins),
        ),
    )

    @server._mcp_server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=PREPARE_TOOL,
                description=(
                    "Prepare exactly one bounded CREATE or unique-text REPLACE "
                    "against an approved project path. This does not write."
                ),
                inputSchema=prepare_schema,
                outputSchema=prepare_output,
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
            Tool(
                name=COMMIT_TOOL,
                description=(
                    "Commit exactly one previously prepared text patch. The only "
                    "input is its signed action reference. Safe replay reconciles "
                    "the same postimage; never substitute another path or payload."
                ),
                inputSchema=ref_schema,
                outputSchema=effect_output,
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
            Tool(
                name=RECONCILE_TOOL,
                description=(
                    "Read current source state for one prepared action and classify "
                    "NOT_APPLIED, APPLIED, or EFFECT_UNKNOWN without writing."
                ),
                inputSchema=ref_schema,
                outputSchema=effect_output,
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
        ]

    def emit_call_receipt(
        *, name: str, request: object, caller: ActionCaller
    ) -> None:
        if call_receipt_sink is None:
            return
        try:
            canonical = json.dumps(
                request,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
            call_ref = hashlib.sha256(
                caller.subject_digest.encode("ascii")
                + b"\0"
                + name.encode("ascii")
                + b"\0"
                + canonical
            ).hexdigest()
            call_receipt_sink(
                {
                    "schema": CALL_RECEIPT_SCHEMA,
                    "phase": "RECEIVED",
                    "tool": name,
                    "call_ref": call_ref,
                    "subject_digest": caller.subject_digest,
                    "client_ref": caller.client_ref,
                }
            )
        except Exception:
            # Diagnostic telemetry is not an authority/effect owner. A sink
            # outage must never mutate action semantics or trigger a retry.
            return

    @server._mcp_server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        access = get_access_token()
        if access is None:
            return _error("AUTHENTICATION_REQUIRED")
        if name not in (PREPARE_TOOL, COMMIT_TOOL, RECONCILE_TOOL):
            return _error("TOOL_NOT_AVAILABLE")
        try:
            request = _snapshot(arguments, MAX_ARGUMENT_BYTES)
            if name == PREPARE_TOOL:
                prepare_validator.validate(request)
            else:
                ref_validator.validate(request)
            caller = _caller_from_access(access, selected_policy)
            original_token = access.token
        except Exception:
            return _error("INVALID_REQUEST")

        emit_call_receipt(name=name, request=request, caller=caller)
        try:
            if name == PREPARE_TOOL:
                observed = await prepare_port(caller, request)
            elif name == COMMIT_TOOL:
                observed = await commit_port(caller, request["action_ref"])
            else:
                observed = await reconcile_port(caller, request["action_ref"])
        except ProjectActionRefused as error:
            return _error(error.code)
        except Exception:
            return _error("ACTION_UNAVAILABLE")

        # A response loss after commit may hide an already-applied effect. Never
        # convert post-action auth uncertainty into an invitation to retry.
        try:
            current_access = await verifier.verify_token(original_token)
            if current_access is None:
                return _error(
                    "ACTION_EFFECT_UNKNOWN" if name == COMMIT_TOOL else "AUTHENTICATION_CHANGED"
                )
            current_caller = _caller_from_access(current_access, selected_policy)
            if current_caller != caller:
                return _error(
                    "ACTION_EFFECT_UNKNOWN" if name == COMMIT_TOOL else "AUTHENTICATION_CHANGED"
                )
            data = _snapshot(dict(observed), MAX_RESULT_BYTES // 2)
            if name == PREPARE_TOOL:
                prepare_output_validator.validate(data)
            else:
                effect_output_validator.validate(data)
            result = CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    )
                ],
                structuredContent=data,
                isError=False,
            )
            _snapshot(
                result.model_dump(mode="json", by_alias=True, exclude_none=True),
                MAX_RESULT_BYTES,
            )
            return result
        except Exception:
            return _error(
                "ACTION_EFFECT_UNKNOWN" if name == COMMIT_TOOL else "ACTION_RESULT_UNVERIFIED"
            )

    return server


__all__ = [
    "CALL_RECEIPT_SCHEMA",
    "COMMIT_TOOL",
    "PREPARE_TOOL",
    "RECONCILE_TOOL",
    "create_authenticated_action_server",
]
