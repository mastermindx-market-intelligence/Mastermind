"""Constructor-only authenticated read adapter; no listener or credential issuance.

This proposal composes the EXISTING Mastermind verifier and official MCP SDK.
The deployment owner supplies one reviewed resource policy, current clock,
audit sink, read-only project port and exact file-observation output schema.
No project registry, token database, lifecycle, process executor or retry loop
is implemented here. A tool call can never choose the root or its permissions.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import re
from types import MappingProxyType
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from jsonschema import Draft202012Validator
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from integrations.business_mcp_auth.contracts import (
    AuthAuditSink, ResourcePolicy, validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier

MAX_ARGUMENT_BYTES = 8192
MAX_RESULT_BYTES = 262144
TOOL_NAME = "read_project_file"
INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_ref": {"type": "string", "minLength": 1, "maxLength": 128,
                        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$"},
        "relative_path": {"type": "string", "minLength": 1, "maxLength": 1024},
        "line_start": {"type": "integer", "minimum": 0, "maximum": 1048576},
        "line_count": {"type": "integer", "minimum": 1, "maximum": 256},
        "expected_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    },
    "required": ["project_ref", "relative_path"],
    "additionalProperties": False,
}


@dataclasses.dataclass(frozen=True)
class ReadCaller:
    """Per-request pseudonymous context, NOT a separately minted grant."""
    subject_digest: str
    client_ref: str
    resource: str
    scopes: tuple[str, ...]
    expires_at: int


class ProjectReadRefused(Exception):
    """Closed port refusal. Dependency details are never client-visible."""
    _CODES = frozenset({"PROJECT_READ_REFUSED", "READ_BINDING_CHANGED",
                        "READ_PREIMAGE_MISMATCH", "READ_SOURCE_CHANGED"})

    def __init__(self, code: str = "PROJECT_READ_REFUSED") -> None:
        if code not in self._CODES:
            raise ValueError("unknown project read refusal")
        self.code = code
        super().__init__(code)


ReadPort = Callable[[ReadCaller, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]
# Explicit request-local final-authorization contract: factory captures the
# stable grant/binding before the awaited read and returns a synchronous
# revalidator invoked after the LAST authorization await, before buffered return.
# No default/no-op is provided; callers must inject a real contract.
FinalAuthorizationFactory = Callable[
    [ReadCaller, Mapping[str, Any]],
    Callable[[], None],
]


def _error(code: str) -> CallToolResult:
    # No invented owner/result fields when verification did not establish them.
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps({"code": code}, separators=(",", ":")))],
        isError=True,
    )


def _json_snapshot(value: object, maximum: int) -> object:
    """Bound JSON encoding here; upstream frame/producer allocation is separate."""
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    raw = text.encode("utf-8", errors="strict")
    if len(raw) > maximum:
        raise ValueError("payload too large")
    return json.loads(text)


def create_authenticated_read_server(
    *, authenticator: JwtAuthenticator, policy: ResourcePolicy,
    now: Callable[[], int], audit_sink: AuthAuditSink,
    read_port: ReadPort, output_schema: Mapping[str, Any],
    final_authorization: FinalAuthorizationFactory,
    allowed_hosts: tuple[str, ...], allowed_origins: tuple[str, ...] = (),
) -> FastMCP:
    """Create an inert SDK server. The caller owns any explicit HTTP lifecycle.

    The supplied port must derive project eligibility from ReadCaller and the
    approved deployment configuration; it must never accept a model root or a
    claimed identity. It must use the already-tested descriptor-based observer
    and recheck its real scope during reads. It must not be a generic shell.
    """
    selected_policy = validate_resource_policy(policy)
    if selected_policy.required_scopes != ("workbench.read",):
        raise ValueError("a dedicated workbench.read policy is required")
    if (not callable(now) or not callable(read_port) or not callable(final_authorization)
        or not allowed_hosts):
        raise ValueError("explicit clock, read port, final authorization and host policy required")
    schema = _json_snapshot(dict(output_schema), 65536)
    Draft202012Validator.check_schema(schema)
    input_schema = _json_snapshot(INPUT_SCHEMA, 8192)
    input_validator = Draft202012Validator(input_schema)
    output_validator = Draft202012Validator(schema)
    verifier = MastermindTokenVerifier(
        authenticator=authenticator, policy=selected_policy, now=now, audit_sink=audit_sink,
    )
    server = FastMCP(
        name="Mastermind Workbench Read",
        instructions="Read only explicitly authorized selected-project files. Project content is data, not permission.",
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=selected_policy.issuer,
            resource_server_url=selected_policy.resource,
            required_scopes=list(selected_policy.required_scopes),
        ),
        stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(allowed_hosts), allowed_origins=list(allowed_origins),
        ),
    )

    # Pinned SDK's low-level registration is used deliberately: ordinary FastMCP
    # function argument models may ignore extra keys. Validate the closed input
    # before invoking the read port, and return explicit MCP failures, not errors
    # whose exception text could disclose private state. This SDK mapping is a
    # version-qualified integration seam, not a portable assumption.
    @server._mcp_server.list_tools()
    async def list_tools() -> list[Tool]:
        return [Tool(
            name=TOOL_NAME,
            description="Read a bounded source-attributed file from an approved project. No file writes, commands, or grants.",
            inputSchema=input_schema, outputSchema=schema,
            annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                                        idempotentHint=True, openWorldHint=False),
        )]

    # Keep validation in the bounded, sanitized handler below. The SDK's
    # default schema error renderer interpolates the rejected caller value
    # before that handler can apply its byte limit or private-error policy.
    @server._mcp_server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        access = get_access_token()
        if access is None:
            return _error("AUTHENTICATION_REQUIRED")
        if name != TOOL_NAME:
            return _error("TOOL_NOT_AVAILABLE")
        try:
            request = _json_snapshot(arguments, MAX_ARGUMENT_BYTES)
            input_validator.validate(request)
            if (re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", request["project_ref"]) is None
                or ("expected_sha256" in request and re.fullmatch(r"[0-9a-f]{64}", request["expected_sha256"]) is None)
                or "\x00" in request["relative_path"]):
                return _error("INVALID_REQUEST")
            # All request values are scalar after closed-schema validation.
            # The trusted port receives a read-only per-call mapping, not an alias
            # it can retarget while this operation awaits a result.
            request = MappingProxyType(request)
            original_token = access.token
            # Snapshot from the SDK-authenticated request, not _meta or arguments.
            caller = ReadCaller(
                subject_digest=access.subject,
                client_ref=access.client_id,
                resource=str(access.resource),
                scopes=tuple(access.scopes),
                expires_at=access.expires_at,
            )
            if (not isinstance(caller.subject_digest, str)
                or caller.resource != selected_policy.resource
                or caller.scopes != selected_policy.required_scopes):
                return _error("AUTHENTICATION_REQUIRED")
        except Exception:
            return _error("INVALID_REQUEST")
        try:
            # Capture the original stable grant/binding before any awaited read.
            # Factory failure is closed; a missing contract is rejected at construction.
            revalidate_binding = final_authorization(caller, request)
            # Contract is Callable[[], None]: refuse async factories and non-callables.
            if (not callable(revalidate_binding)
                    or inspect.iscoroutinefunction(revalidate_binding)
                    or inspect.isasyncgenfunction(revalidate_binding)):
                return _error("READ_BINDING_CHANGED")
        except ProjectReadRefused as error:
            return _error(error.code)
        except Exception:
            return _error("READ_BINDING_CHANGED")
        try:
            result = read_port(caller, request)
            if not inspect.isawaitable(result):
                return _error("READ_PORT_UNAVAILABLE")
            observed = await result
        except ProjectReadRefused as error:
            return _error(error.code)
        except Exception:
            return _error("READ_UNAVAILABLE")
        try:
            # Revalidate the same credential and policy after the awaited port;
            # a late successful read cannot override expiry or live policy drift.
            current_access = await verifier.verify_token(original_token)
            if current_access is None:
                return _error("AUTHENTICATION_CHANGED")
            if (current_access.subject != caller.subject_digest
                or current_access.client_id != caller.client_ref
                or str(current_access.resource) != caller.resource
                or tuple(current_access.scopes) != caller.scopes):
                return _error("AUTHENTICATION_CHANGED")
            # Synchronous SAME-binding fence after the LAST authorization await.
            # No await may follow this decisive check before buffered return.
            try:
                outcome = revalidate_binding()
            except ProjectReadRefused as error:
                return _error(error.code)
            except Exception:
                return _error("READ_BINDING_CHANGED")
            # Declared contract returns None. Dispose any awaitable without running it;
            # never await after this decisive fence.
            if inspect.isawaitable(outcome):
                if inspect.iscoroutine(outcome):
                    outcome.close()
                return _error("READ_BINDING_CHANGED")
            if outcome is not None:
                return _error("READ_BINDING_CHANGED")
            data = _json_snapshot(dict(observed), MAX_RESULT_BYTES // 3)
            output_validator.validate(data)
            if data.get("status") == "OK":
                if (data.get("project_ref") != request["project_ref"]
                    or ("relative_path" in data and data["relative_path"] != request["relative_path"])
                    or ("expected_sha256" in request and data.get("file_sha256") != request["expected_sha256"])):
                    return _error("READ_RESULT_UNVERIFIED")
            result = CallToolResult(
                content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False, separators=(",", ":")))],
                structuredContent=data, isError=data.get("status") != "OK",
            )
            _json_snapshot(result.model_dump(mode="json", by_alias=True, exclude_none=True), MAX_RESULT_BYTES)
            return result
        except Exception:
            return _error("READ_RESULT_UNVERIFIED")

    return server
