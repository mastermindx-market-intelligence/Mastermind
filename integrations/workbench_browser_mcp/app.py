"""Authenticated model-facing Workbench Browser companion MCP surface."""
from __future__ import annotations

import copy
from dataclasses import dataclass
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

from control_plane.browser_resource_contract import (
    ALLOWED_BROWSER_TOOLS,
    READ_ONLY_BROWSER_TOOLS,
    WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
)
from control_plane.executive_agent_capabilities import observed_mcp_tool_schema_digest
from integrations.business_mcp_auth.contracts import (
    AuthAuditSink,
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.workbench_action_mcp.contracts import ActionCaller

from .browser_port import BrowserPortRefused
from .contracts import BrowserContractError
from .resource_port import BrowserResourceRefused


PREPARE_RESOURCE_TOOL = "prepare_browser_resource"
START_RESOURCE_TOOL = "start_browser_resource"
RECONCILE_RESOURCE_TOOL = "reconcile_browser_resource"
RUN_ACTION_TOOL = "run_browser_action"
RECONCILE_ACTION_TOOL = "reconcile_browser_action"
CALL_RECEIPT_SCHEMA = "mastermind.workbench_browser_call_receipt.v1"

MAX_ARGUMENT_BYTES = 128 * 1024
MAX_STRUCTURED_BYTES = 256 * 1024
MAX_RESULT_BYTES = 16 * 1024 * 1024
MAX_REF_BYTES = 16 * 1024

PrepareResource = Callable[[ActionCaller, str, str, str | None], Awaitable[str]]
StartResource = Callable[[ActionCaller, object], Awaitable[Mapping[str, Any]]]
ReconcileResource = Callable[[ActionCaller, object], Awaitable[Mapping[str, Any]]]
ReadTool = Callable[[ActionCaller, object, str, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]
PrepareAction = Callable[[ActionCaller, object, str, Mapping[str, Any]], Awaitable[str]]
RunAction = Callable[[ActionCaller, object, object], Awaitable[Mapping[str, Any]]]
ReconcileAction = Callable[[ActionCaller, object, object], Awaitable[Mapping[str, Any]]]
CallReceiptSink = Callable[[Mapping[str, Any]], None]


def _snapshot(value: object, maximum: int) -> object:
    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
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


def _validated_catalog(
    catalog: Mapping[str, Any],
    *,
    expected_digest: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(catalog, Mapping) or set(catalog) != {"tools"}:
        raise ValueError("browser tool catalog is invalid")
    rows = catalog["tools"]
    if not isinstance(rows, list):
        raise ValueError("browser tool catalog is invalid")
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("browser tool catalog is invalid")
        name = row.get("name")
        schema = row.get("inputSchema")
        if (
            type(name) is not str
            or name in by_name
            or not isinstance(schema, Mapping)
        ):
            raise ValueError("browser tool catalog is invalid")
        by_name[name] = copy.deepcopy(dict(row))
    if not ALLOWED_BROWSER_TOOLS <= set(by_name):
        raise ValueError("browser tool catalog lacks a granted tool")
    selected = {
        "tools": {name: by_name[name] for name in sorted(ALLOWED_BROWSER_TOOLS)}
    }
    if observed_mcp_tool_schema_digest(selected) != expected_digest:
        raise ValueError("browser tool catalog schema drift")
    return {name: by_name[name] for name in ALLOWED_BROWSER_TOOLS}


def _with_browser_ref(native_schema: Mapping[str, Any]) -> dict[str, Any]:
    schema = copy.deepcopy(dict(native_schema))
    if schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
        raise ValueError("browser tool schema is not an object")
    properties = dict(schema["properties"])
    if "browser_ref" in properties:
        raise ValueError("native browser schema collides with browser_ref")
    properties["browser_ref"] = {
        "type": "string",
        "minLength": 16,
        "maxLength": MAX_REF_BYTES,
        "description": "Opaque Workbench browser resource reference.",
    }
    schema["properties"] = properties
    required = list(schema.get("required", []))
    if "browser_ref" not in required:
        required.append("browser_ref")
    schema["required"] = required
    schema["additionalProperties"] = False
    return schema


def _json_result(value: Mapping[str, Any]) -> CallToolResult:
    data = _snapshot(dict(value), MAX_STRUCTURED_BYTES)
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


def _native_result(value: Mapping[str, Any], *, structured: Mapping[str, Any] | None = None) -> CallToolResult:
    if not isinstance(value, Mapping):
        raise ValueError("native browser result is invalid")
    native = CallToolResult.model_validate(dict(value))
    selected_structured = (
        _snapshot(dict(structured), MAX_STRUCTURED_BYTES)
        if structured is not None
        else native.structuredContent
    )
    result = CallToolResult(
        content=native.content,
        structuredContent=selected_structured,
        isError=native.isError,
    )
    _snapshot(
        result.model_dump(mode="json", by_alias=True, exclude_none=True),
        MAX_RESULT_BYTES,
    )
    return result


_RESOURCE_PREPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "project_ref": {
            "type": "string",
            "minLength": 1,
            "maxLength": 256,
            "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
        },
        "mode": {"type": "string", "enum": ["isolated", "persistent"]},
        "profile_ref": {
            "anyOf": [
                {"type": "null"},
                {
                    "type": "string",
                    "minLength": 3,
                    "maxLength": 256,
                    "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$",
                },
            ]
        },
    },
    "required": ["project_ref", "mode"],
    "additionalProperties": False,
}
_START_REF_SCHEMA = {
    "type": "object",
    "properties": {
        "start_ref": {"type": "string", "minLength": 16, "maxLength": MAX_REF_BYTES}
    },
    "required": ["start_ref"],
    "additionalProperties": False,
}
_ACTION_REF_SCHEMA = {
    "type": "object",
    "properties": {
        "browser_ref": {"type": "string", "minLength": 16, "maxLength": MAX_REF_BYTES},
        "action_ref": {"type": "string", "minLength": 16, "maxLength": MAX_REF_BYTES},
    },
    "required": ["browser_ref", "action_ref"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class BrowserToolSurface:
    """One canonical Browser tool/schema projection shared by all transports."""

    catalog: Mapping[str, Mapping[str, Any]]
    schemas: Mapping[str, Mapping[str, Any]]
    validators: Mapping[str, Draft202012Validator]
    prepare_tool_to_native: Mapping[str, str]
    tools: tuple[Tool, ...]


def build_browser_tool_surface(
    tool_catalog: Mapping[str, Any],
    *,
    expected_tool_schema_digest: str = WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
) -> BrowserToolSurface:
    catalog = _validated_catalog(
        tool_catalog,
        expected_digest=expected_tool_schema_digest,
    )
    resource_prepare_schema = _snapshot(_RESOURCE_PREPARE_SCHEMA, 32768)
    start_ref_schema = _snapshot(_START_REF_SCHEMA, 32768)
    action_ref_schema = _snapshot(_ACTION_REF_SCHEMA, 32768)
    schemas: dict[str, dict[str, Any]] = {
        PREPARE_RESOURCE_TOOL: resource_prepare_schema,
        START_RESOURCE_TOOL: start_ref_schema,
        RECONCILE_RESOURCE_TOOL: start_ref_schema,
        RUN_ACTION_TOOL: action_ref_schema,
        RECONCILE_ACTION_TOOL: action_ref_schema,
    }
    prepare_tool_to_native: dict[str, str] = {}
    for name in sorted(ALLOWED_BROWSER_TOOLS):
        wrapped = _snapshot(_with_browser_ref(catalog[name]["inputSchema"]), 32768)
        if name in READ_ONLY_BROWSER_TOOLS:
            schemas[name] = wrapped
        else:
            prepare_name = "prepare_" + name
            prepare_tool_to_native[prepare_name] = name
            schemas[prepare_name] = wrapped
    validators = {
        name: Draft202012Validator(schema) for name, schema in schemas.items()
    }
    rows: list[Tool] = [
        Tool(
            name=PREPARE_RESOURCE_TOOL,
            description="Prepare one browser resource against the current Workbench owner binding. No process is started.",
            inputSchema=resource_prepare_schema,
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name=START_RESOURCE_TOOL,
            description="Start exactly one previously prepared owner-bound browser resource. Safe replay reconciles the same resource.",
            inputSchema=start_ref_schema,
            annotations=ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
        Tool(
            name=RECONCILE_RESOURCE_TOOL,
            description="Read the effect state of one prepared browser start without starting another resource.",
            inputSchema=start_ref_schema,
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                idempotentHint=True,
                openWorldHint=False,
            ),
        ),
    ]
    for name in sorted(READ_ONLY_BROWSER_TOOLS):
        native = catalog[name]
        annotations = native.get("annotations", {})
        rows.append(
            Tool(
                name=name,
                description=str(native.get("description", name)),
                inputSchema=schemas[name],
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=bool(annotations.get("openWorldHint", True)),
                ),
            )
        )
    for prepare_name, native_name in sorted(prepare_tool_to_native.items()):
        native = catalog[native_name]
        rows.append(
            Tool(
                name=prepare_name,
                description=(
                    f"Prepare {native_name} against one browser resource. "
                    "This does not execute the browser action."
                ),
                inputSchema=schemas[prepare_name],
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=False,
                    openWorldHint=False,
                ),
            )
        )
    rows.extend(
        [
            Tool(
                name=RUN_ACTION_TOOL,
                description="Execute exactly one signed prepared browser action. Safe replay reconciles and never dispatches the action twice.",
                inputSchema=action_ref_schema,
                annotations=ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=True,
                    openWorldHint=True,
                ),
            ),
            Tool(
                name=RECONCILE_ACTION_TOOL,
                description="Read NOT_APPLIED, APPLIED, or EFFECT_UNKNOWN for one signed browser action without dispatching it.",
                inputSchema=action_ref_schema,
                annotations=ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            ),
        ]
    )
    return BrowserToolSurface(
        catalog=catalog,
        schemas=schemas,
        validators=validators,
        prepare_tool_to_native=prepare_tool_to_native,
        tools=tuple(rows),
    )


def create_authenticated_browser_server(
    *,
    authenticator: JwtAuthenticator,
    policy: ResourcePolicy,
    now: Callable[[], int],
    audit_sink: AuthAuditSink,
    tool_catalog: Mapping[str, Any],
    prepare_resource: PrepareResource,
    start_resource: StartResource,
    reconcile_resource: ReconcileResource,
    read_tool: ReadTool,
    prepare_action: PrepareAction,
    run_action: RunAction,
    reconcile_action: ReconcileAction,
    allowed_hosts: tuple[str, ...],
    call_receipt_sink: CallReceiptSink | None = None,
    allowed_origins: tuple[str, ...] = (),
    expected_tool_schema_digest: str = WORKBENCH_BROWSER_TOOL_SCHEMA_DIGEST,
) -> FastMCP:
    selected_policy = validate_resource_policy(policy)
    if selected_policy.required_scopes != ("workbench.action",):
        raise ValueError("the existing Workbench action policy is required")
    if (
        not callable(now)
        or not callable(prepare_resource)
        or not callable(start_resource)
        or not callable(reconcile_resource)
        or not callable(read_tool)
        or not callable(prepare_action)
        or not callable(run_action)
        or not callable(reconcile_action)
        or (call_receipt_sink is not None and not callable(call_receipt_sink))
        or type(allowed_hosts) is not tuple
        or not allowed_hosts
    ):
        raise ValueError("explicit Workbench Browser services are required")

    surface = build_browser_tool_surface(
        tool_catalog,
        expected_tool_schema_digest=expected_tool_schema_digest,
    )
    catalog = surface.catalog
    schemas = surface.schemas
    validators = surface.validators
    prepare_tool_to_native = surface.prepare_tool_to_native

    verifier = MastermindTokenVerifier(
        authenticator=authenticator,
        policy=selected_policy,
        now=now,
        audit_sink=audit_sink,
    )
    server = FastMCP(
        name="Mastermind Workbench Browser",
        instructions=(
            "Use one owner-bound browser resource at a time. Read tools act directly. "
            "Every modifying browser action is prepared first, then executed by its "
            "signed action_ref. Reconcile the same ref after response loss; never "
            "prepare a replacement action to retry an uncertain click or submit."
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
        return list(surface.tools)

    def emit_call_receipt(name: str, request: object, caller: ActionCaller) -> None:
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
            call_receipt_sink(
                {
                    "schema": CALL_RECEIPT_SCHEMA,
                    "phase": "RECEIVED",
                    "tool": name,
                    "call_ref": hashlib.sha256(
                        caller.subject_digest.encode("ascii")
                        + b"\0"
                        + name.encode("ascii")
                        + b"\0"
                        + canonical
                    ).hexdigest(),
                    "subject_digest": caller.subject_digest,
                    "client_ref": caller.client_ref,
                }
            )
        except Exception:
            return

    @server._mcp_server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        access = get_access_token()
        if access is None:
            return _error("AUTHENTICATION_REQUIRED")
        if name not in validators:
            return _error("TOOL_NOT_AVAILABLE")
        try:
            request = _snapshot(arguments, MAX_ARGUMENT_BYTES)
            validators[name].validate(request)
            caller = _caller_from_access(access, selected_policy)
            original_token = access.token
        except Exception:
            return _error("INVALID_REQUEST")

        emit_call_receipt(name, request, caller)
        is_effectful = name in {START_RESOURCE_TOOL, RUN_ACTION_TOOL}
        direct_native: Mapping[str, Any] | None = None
        try:
            if name == PREPARE_RESOURCE_TOOL:
                start_ref = await prepare_resource(
                    caller,
                    request["project_ref"],
                    request["mode"],
                    request.get("profile_ref"),
                )
                observed: Mapping[str, Any] = {
                    "status": "PREPARED",
                    "start_ref": start_ref,
                }
            elif name == START_RESOURCE_TOOL:
                observed = await start_resource(caller, request["start_ref"])
            elif name == RECONCILE_RESOURCE_TOOL:
                observed = await reconcile_resource(caller, request["start_ref"])
            elif name in READ_ONLY_BROWSER_TOOLS:
                native_args = dict(request)
                browser_ref = native_args.pop("browser_ref")
                direct_native = await read_tool(caller, browser_ref, name, native_args)
                observed = {}
            elif name in prepare_tool_to_native:
                native_args = dict(request)
                browser_ref = native_args.pop("browser_ref")
                action_ref = await prepare_action(
                    caller,
                    browser_ref,
                    prepare_tool_to_native[name],
                    native_args,
                )
                observed = {"status": "PREPARED", "action_ref": action_ref}
            elif name == RUN_ACTION_TOOL:
                observed = await run_action(
                    caller,
                    request["browser_ref"],
                    request["action_ref"],
                )
            else:
                observed = await reconcile_action(
                    caller,
                    request["browser_ref"],
                    request["action_ref"],
                )
        except (BrowserResourceRefused, BrowserPortRefused) as error:
            return _error(error.code)
        except BrowserContractError:
            return _error("INVALID_REQUEST")
        except Exception:
            return _error(
                "BROWSER_EFFECT_UNKNOWN" if is_effectful else "BROWSER_UNAVAILABLE"
            )

        try:
            current_access = await verifier.verify_token(original_token)
            if current_access is None:
                return _error(
                    "BROWSER_EFFECT_UNKNOWN"
                    if is_effectful
                    else "AUTHENTICATION_CHANGED"
                )
            current_caller = _caller_from_access(current_access, selected_policy)
            if current_caller != caller:
                return _error(
                    "BROWSER_EFFECT_UNKNOWN"
                    if is_effectful
                    else "AUTHENTICATION_CHANGED"
                )

            if direct_native is not None:
                return _native_result(direct_native)

            data = _snapshot(dict(observed), MAX_STRUCTURED_BYTES)
            if name == RUN_ACTION_TOOL and isinstance(data.get("result"), dict):
                native = data.pop("result")
                native_result = _native_result(native, structured=data)
                if data.get("effect_state") == "EFFECT_UNKNOWN":
                    native_result.isError = True
                return native_result
            return _json_result(data)
        except Exception:
            return _error(
                "BROWSER_EFFECT_UNKNOWN"
                if is_effectful
                else "BROWSER_RESULT_UNVERIFIED"
            )

    return server


__all__ = [
    "BrowserToolSurface",
    "CALL_RECEIPT_SCHEMA",
    "PREPARE_RESOURCE_TOOL",
    "RECONCILE_ACTION_TOOL",
    "RECONCILE_RESOURCE_TOOL",
    "RUN_ACTION_TOOL",
    "START_RESOURCE_TOOL",
    "build_browser_tool_surface",
    "create_authenticated_browser_server",
]
