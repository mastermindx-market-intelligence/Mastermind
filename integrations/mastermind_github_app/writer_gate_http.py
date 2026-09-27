"""Authenticated HTTP composition for the existing writer-gate read companion.

Borrows the existing Business authentication and target/installation owners.
The factory opens no listener and never loads a credential or ambient session.
The patch server/catalog, Source Continuity meaning and default disarm are unchanged.
"""
from __future__ import annotations

from copy import deepcopy
import dataclasses
import re
from urllib.parse import urlsplit

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Tool, ToolAnnotations

from integrations.business_mcp_auth.contracts import validate_resource_policy
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from .github_port import UrllibHttpTransport
from .models import AuthenticatedPrincipal
from .writer_gate_port import GithubWriterGatePort, WriterGateServiceRefused, WriterGateTarget, WRITER_GATE_SCOPE, WRITER_GATE_TOOL_SPEC
from .writer_gate_server import _result, invoke_writer_gate


def _access_identity(access, policy):
    try:
        identity = (access.subject, access.client_id, str(access.resource), tuple(access.scopes), access.expires_at)
    except (AttributeError, TypeError, ValueError):
        raise WriterGateServiceRefused("AUTHENTICATION_REFUSED") from None
    if (type(identity[0]) is not str or re.fullmatch(r"[0-9a-f]{64}", identity[0]) is None
            or type(identity[1]) is not str or not identity[1]
            or identity[2] != policy.resource or identity[3] != policy.required_scopes
            or type(identity[4]) is not int):
        raise WriterGateServiceRefused("AUTHENTICATION_REFUSED")
    return identity


class _RequestPrincipal:
    """Ephemeral request projection, not a stored identity or authentication owner."""
    def __init__(self, access, verifier, policy):
        self._identity = _access_identity(access, policy)
        self._token = access.token
        self._verifier = verifier
        self._policy = policy

    @property
    def expires_at(self):
        return self._identity[4]

    async def current_principal(self):
        current = await self._verifier.verify_token(self._token)
        if current is None or _access_identity(current, self._policy) != self._identity:
            raise WriterGateServiceRefused("AUTHENTICATION_REFUSED")
        return AuthenticatedPrincipal(self._identity[0], self._identity[3])


class _RequestAuthority:
    """Narrow the owner's deadline to authenticated request expiry; never extend it."""
    def __init__(self, owner, principal):
        self._owner = owner
        self._principal = principal

    async def resolve_writer_gate_target(self, operation_key, principal_digest):
        target = await self._owner.resolve_writer_gate_target(operation_key, principal_digest)
        if type(target) is not WriterGateTarget or type(target.expires_at) is not int:
            return None
        return dataclasses.replace(target, expires_at=min(target.expires_at, self._principal.expires_at))


def create_authenticated_writer_gate_server(
    *, authenticator, policy, now, audit_sink, authority, token_provider,
    allowed_hosts: tuple[str, ...], allowed_origins: tuple[str, ...] = (),
    read_transport=UrllibHttpTransport._request_sync, production_armed: bool = False,
) -> FastMCP:
    """Construct a stateless authenticated endpoint; deployment owns activation."""
    selected = validate_resource_policy(policy)
    if selected.required_scopes != (WRITER_GATE_SCOPE,):
        raise ValueError("WRITER_GATE_SCOPE_REQUIRED")
    if validate_resource_policy(authenticator.policy) != selected:
        raise ValueError("AUTH_POLICY_BINDING_MISMATCH")
    if (type(production_armed) is not bool or not callable(now) or not callable(read_transport)
            or not callable(getattr(authority, "resolve_writer_gate_target", None))
            or not callable(getattr(token_provider, "installation_token", None))):
        raise ValueError("WRITER_GATE_SERVICES_REQUIRED")
    for values, required in ((allowed_hosts, True), (allowed_origins, False)):
        if (type(values) is not tuple or (required and not values)
                or any(type(v) is not str or not v or "*" in v
                       or any(ord(c) <= 32 or ord(c) == 127 for c in v) for v in values)):
            raise ValueError("TRANSPORT_POLICY_INVALID")
    verifier = MastermindTokenVerifier(authenticator=authenticator, policy=selected, now=now, audit_sink=audit_sink)
    server = FastMCP(
        name="Mastermind GitHub Writer Gate",
        instructions="Read canonical evidence for an owner-bound operation. This tool grants no write, merge or release authority.",
        token_verifier=verifier,
        auth=AuthSettings(issuer_url=selected.issuer, resource_server_url=selected.resource,
                          required_scopes=list(selected.required_scopes)),
        stateless_http=True, json_response=True,
        streamable_http_path=urlsplit(selected.resource).path or "/mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=list(allowed_hosts), allowed_origins=list(allowed_origins)),
    )
    tool = Tool(name=WRITER_GATE_TOOL_SPEC["name"], description=WRITER_GATE_TOOL_SPEC["description"],
                inputSchema=deepcopy(WRITER_GATE_TOOL_SPEC["inputSchema"]),
                annotations=ToolAnnotations(**WRITER_GATE_TOOL_SPEC["annotations"]))

    @server._mcp_server.list_tools()
    async def list_tools():
        return [tool.model_copy(deep=True)]

    @server._mcp_server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        try:
            access = get_access_token()
            if access is None:
                raise WriterGateServiceRefused("AUTHENTICATION_REFUSED")
            principal = _RequestPrincipal(access, verifier, selected)
            port = GithubWriterGatePort(principals=principal, authority=_RequestAuthority(authority, principal),
                token_provider=token_provider, clock=now, read_transport=read_transport,
                production_armed=production_armed)
            return await invoke_writer_gate(port, name, arguments)
        except WriterGateServiceRefused as error:
            return _result({"code": error.code, "receipt": None}, failed=True)
        except Exception:
            return _result({"code": "SERVICE_UNAVAILABLE", "receipt": None}, failed=True)

    return server
