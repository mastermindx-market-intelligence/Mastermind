"""Authenticated stateless MCP edge for Workspace Agent candidate return.

This composes the accepted Business MCP OAuth resource-server boundary with the
one-tool Workspace return contract. It owns no authorization server, OAuth
client enrollment, tunnel, listener lifecycle, Workspace credential, Agent
Dialogue credential, canonical state, retry controller, or result acceptance.
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, Tool, ToolAnnotations

from integrations.business_mcp_auth.contracts import (
    ResourcePolicy,
    validate_resource_policy,
)
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import oauth_security_schemes
from integrations.workspace_agent_return import (
    RETURN_RESULT_SCHEMA,
    TOOL_NAME,
    WorkspaceCandidateReturnGateway,
    canonical_return_json,
    tool_spec,
)

REQUIRED_SCOPE = "mastermind.dialogue.write"
MAX_RESULT_BYTES = 16 * 1024
_MESSAGE_KEY = re.compile(r"\Aasd-wsa-[0-9a-f]{32}\Z")
_ERROR_STATES = frozenset(
    {
        "INVALID_REQUEST",
        "INVALID_RETURN_REF",
        "RETURN_REF_EXPIRED",
        "RETURN_REF_NOT_YET_VALID",
        "CURRENT_TARGET_CHANGED",
        "BINDING_UNAVAILABLE",
        "EFFECT_UNKNOWN",
        "SERVICE_UNAVAILABLE",
        "RETURN_REFUSED",
        "AUTHENTICATION_REQUIRED",
        "AUTHENTICATION_CHANGED",
        "RESULT_UNVERIFIED",
    }
)


def _error(state: str, *, message_key: str | None = None) -> dict[str, Any]:
    if state not in _ERROR_STATES:
        state = "RESULT_UNVERIFIED"
    result: dict[str, Any] = {
        "schema": RETURN_RESULT_SCHEMA,
        "ok": False,
        "state": state,
    }
    if isinstance(message_key, str) and _MESSAGE_KEY.fullmatch(message_key):
        result["message_key"] = message_key
    return result


def _snapshot_result(value: Any) -> dict[str, Any]:
    """Admit only the closed Workspace-return result vocabulary."""

    try:
        raw = canonical_return_json(value)
        if len(raw) > MAX_RESULT_BYTES:
            raise ValueError
        document = json.loads(raw.decode("ascii"))
    except Exception:
        raise ValueError("invalid Workspace return result") from None
    if not isinstance(document, dict) or document.get("schema") != RETURN_RESULT_SCHEMA:
        raise ValueError("invalid Workspace return result")
    ok = document.get("ok")
    state = document.get("state")
    if type(ok) is not bool or not isinstance(state, str):
        raise ValueError("invalid Workspace return result")
    if ok:
        if (
            set(document)
            != {
                "schema",
                "ok",
                "state",
                "message_key",
                "transport_action",
                "accepted",
                "wake_acknowledged",
            }
            or state != "CANDIDATE_RECORDED"
            or not isinstance(document.get("message_key"), str)
            or _MESSAGE_KEY.fullmatch(document["message_key"]) is None
            or document.get("transport_action") not in {"POSTED", "RECOVERED", "DUPLICATE"}
            or document.get("accepted") is not False
            or document.get("wake_acknowledged") is not False
        ):
            raise ValueError("invalid Workspace return result")
        return document
    if (
        state not in _ERROR_STATES
        or not set(document) <= {"schema", "ok", "state", "message_key"}
        or set(document) < {"schema", "ok", "state"}
    ):
        raise ValueError("invalid Workspace return result")
    message_key = document.get("message_key")
    if message_key is not None and (
        not isinstance(message_key, str) or _MESSAGE_KEY.fullmatch(message_key) is None
    ):
        raise ValueError("invalid Workspace return result")
    return document


def _same_access(left: Any, right: Any, policy: ResourcePolicy) -> bool:
    return bool(
        left is not None
        and right is not None
        and left.subject == right.subject
        and left.client_id == right.client_id
        and str(left.resource) == str(right.resource) == policy.resource
        and tuple(left.scopes) == tuple(right.scopes) == policy.required_scopes
        and left.expires_at == right.expires_at
    )


def _result(document: dict[str, Any]) -> CallToolResult:
    payload = _snapshot_result(document)
    result = CallToolResult(
        content=[
            TextContent(
                type="text",
                text=canonical_return_json(payload).decode("ascii"),
            )
        ],
        structuredContent=payload,
        isError=payload["ok"] is not True,
    )
    try:
        encoded = json.dumps(
            result.model_dump(mode="json", by_alias=True, exclude_none=True),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except Exception:
        return CallToolResult(
            content=[TextContent(type="text", text=canonical_return_json(_error("RESULT_UNVERIFIED")).decode("ascii"))],
            structuredContent=_error("RESULT_UNVERIFIED"),
            isError=True,
        )
    if len(encoded) > MAX_RESULT_BYTES:
        return CallToolResult(
            content=[TextContent(type="text", text=canonical_return_json(_error("RESULT_UNVERIFIED")).decode("ascii"))],
            structuredContent=_error("RESULT_UNVERIFIED"),
            isError=True,
        )
    return result


def create_authenticated_return_server(
    *,
    gateway: WorkspaceCandidateReturnGateway,
    policy: ResourcePolicy,
    token_verifier: MastermindTokenVerifier,
    allowed_hosts: tuple[str, ...],
    allowed_origins: Sequence[str] = (),
) -> FastMCP:
    """Build one production-inert, authenticated, tools-only return server."""

    if not isinstance(gateway, WorkspaceCandidateReturnGateway):
        raise TypeError("gateway must be WorkspaceCandidateReturnGateway")
    selected_policy = validate_resource_policy(policy)
    if selected_policy.required_scopes != (REQUIRED_SCOPE,):
        raise ValueError("Workspace return policy must require exactly mastermind.dialogue.write")
    if type(token_verifier) is not MastermindTokenVerifier:
        raise TypeError("token_verifier must be MastermindTokenVerifier")
    if MastermindTokenVerifier._validated_composition(token_verifier) != selected_policy:
        raise ValueError("token_verifier policy must match Workspace return policy")
    if (
        type(allowed_hosts) is not tuple
        or not allowed_hosts
        or any(not isinstance(value, str) or not value for value in allowed_hosts)
    ):
        raise ValueError("explicit allowed_hosts are required")
    origins = tuple(allowed_origins)
    if any(not isinstance(value, str) or not value for value in origins):
        raise ValueError("allowed_origins must contain nonempty strings")

    server = FastMCP(
        name="Mastermind Workspace Agent Return",
        instructions=(
            "Return one bounded Workspace Agent candidate through the supplied "
            "return_ref. A successful tool call records dialogue transport only; "
            "it does not accept the candidate, complete work, acknowledge Wake, "
            "select a lifecycle target, or authorize another provider run."
        ),
        token_verifier=token_verifier,
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
            allowed_origins=list(origins),
        ),
    )
    spec = tool_spec()
    security = oauth_security_schemes((REQUIRED_SCOPE,))

    @server._mcp_server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=spec["name"],
                description=spec["description"],
                inputSchema=spec["input_schema"],
                annotations=ToolAnnotations(**spec["annotations"]),
                securitySchemes=security,
            )
        ]

    @server._mcp_server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        access = get_access_token()
        if access is None:
            return _result(_error("AUTHENTICATION_REQUIRED"))
        if name != TOOL_NAME:
            return _result(_error("INVALID_REQUEST"))
        if (
            not isinstance(access.subject, str)
            or not isinstance(access.client_id, str)
            or str(access.resource) != selected_policy.resource
            or tuple(access.scopes) != selected_policy.required_scopes
            or not isinstance(access.token, str)
            or not access.token
        ):
            return _result(_error("AUTHENTICATION_REQUIRED"))
        original_access = access
        original_token = access.token
        try:
            observed = await gateway.call_tool(name, arguments or {})
            envelope = _snapshot_result(observed)
        except Exception:
            return _result(_error("EFFECT_UNKNOWN"))

        try:
            current_access = await token_verifier.verify_token(original_token)
        except Exception:
            current_access = None
        if not _same_access(original_access, current_access, selected_policy):
            message_key = envelope.get("message_key")
            if envelope["ok"] is True or envelope["state"] == "EFFECT_UNKNOWN":
                return _result(_error("EFFECT_UNKNOWN", message_key=message_key))
            return _result(
                _error("AUTHENTICATION_CHANGED", message_key=message_key)
            )
        return _result(envelope)

    return server


__all__ = [
    "MAX_RESULT_BYTES",
    "REQUIRED_SCOPE",
    "create_authenticated_return_server",
]
