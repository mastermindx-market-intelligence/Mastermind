"""Authenticated Research Read MCP app. Path (i): lowlevel Server behind a research-owned gate.

The gate calls only the public business_mcp_auth API. It does not parse JWTs
or assemble challenge headers. The tool handler reads the verified principal
back from the Starlette request on ``server.request_context`` and projects it
with ``principal_projection``. The port is not called until authentication,
argument validation, entitlement and the per-tool content-class gate succeed.
"""
from __future__ import annotations

import inspect
import json
import logging
import time
from copy import deepcopy
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlsplit

from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, JSONRPCResponse, TextContent, Tool, ToolAnnotations
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from integrations.business_mcp_auth.contracts import (
    AUTH_AUDIT_SCHEMA,
    AuthAuditEvent,
    AuthError,
    AuthErrorCode,
    ResourcePolicy,
    VerifiedPrincipal,
    validate_resource_policy,
)
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.metadata import (
    mcp_auth_error_result,
    protected_resource_metadata,
)
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.research_read_mcp.contracts import (
    MAX_RESULT_BYTES,
    TOOL_ANNOTATIONS,
    TOOL_NAMES,
    ContractViolation,
    error_payload,
    result_wire_bytes,
    tool_definitions,
    validate_arguments,
    validate_output,
)

from .compatibility_v1 import (
    COMPATIBILITY_TOOL_NAMES, CompatibilityPortV1, MAX_COMPATIBILITY_WIRE_BYTES,
    INPUT_SCHEMAS as COMPATIBILITY_INPUT_SCHEMAS, OUTPUT_SCHEMAS as COMPATIBILITY_OUTPUT_SCHEMAS,
    _refuse as compatibility_refuse, validate_output as compatibility_output,
    grant_is_current as compatibility_grant_is_current, validate_arguments as compatibility_arguments,
)

# MCP SDK construction and JSON-RPC accounting stay at this existing edge.
def compatibility_tool_models() -> list[Tool]:
    descriptions = {
        'search': 'Search qualified complete bounded evidence items in the admitted research scope. Results are item citations, not complete reports.',
        'fetch': 'Retrieve one complete literal bounded evidence item. COMPLETE_BOUNDED_ITEM describes this item only, never report completeness.',
    }
    return [Tool(name=name, description=descriptions[name],
                 inputSchema=deepcopy(COMPATIBILITY_INPUT_SCHEMAS[name]), outputSchema=deepcopy(COMPATIBILITY_OUTPUT_SCHEMAS[name]),
                 annotations=ToolAnnotations(**TOOL_ANNOTATIONS))
            for name in COMPATIBILITY_TOOL_NAMES]


def compatibility_wire_bytes(result: CallToolResult, request_id) -> int:
    """Count actual SDK JSON-RPC envelope, including both copies of JSON data."""
    envelope = JSONRPCResponse(jsonrpc='2.0', id=request_id,
                              result=result.model_dump(mode='json', by_alias=True, exclude_none=True))
    return len(envelope.model_dump_json(by_alias=True, exclude_none=True).encode('utf-8'))


def compatibility_result(name, data, *, quote_limit_chars, request_id) -> CallToolResult:
    data = compatibility_output(name, data, quote_limit_chars=quote_limit_chars)
    rendered = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    result = CallToolResult(content=[TextContent(type='text', text=rendered)],
                            structuredContent=data, isError=False)
    if compatibility_wire_bytes(result, request_id) > MAX_COMPATIBILITY_WIRE_BYTES:
        compatibility_refuse()
    return result



_LOG = logging.getLogger("integrations.research_read_mcp.app")
_REQUIRED_SCOPE = ("mastermind.research.read",)
_PRINCIPAL_SCOPE_KEY = "mastermind.research_read_mcp.principal"
_HEADER_SCOPE_KEY = "mastermind.research_read_mcp.authorization"
# M10 §3. rio_derived is accepted on an entitlement and has no v1 effect.
_REQUIRED_CLASS = {
    "research_status": "catalog_metadata",
    "research_search": "catalog_metadata",
    "research_fetch": "report_text",
    "research_find_evidence": "evidence_passage",
}
# §D.3 closed refusal channel. Any other ContractViolation code is internal.
_PORT_REFUSAL = frozenset({
    "NOT_FOUND",
    "SOURCE_UNAVAILABLE",
    "NOT_ENTITLED",
    "INVALID_REQUEST",
})


def _url_path(url: str) -> str:
    path = urlsplit(url).path or "/"
    if path != "/":
        path = path.rstrip("/")
    return path or "/"


def _tool_models(compatibility_port=None) -> list[Tool]:
    tools: list[Tool] = []
    for definition in tool_definitions():
        annotations = definition["annotations"]
        tools.append(Tool(
            name=definition["name"],
            description=definition["description"],
            inputSchema=definition["inputSchema"],
            outputSchema=definition["outputSchema"],
            annotations=ToolAnnotations(
                readOnlyHint=annotations["readOnlyHint"],
                destructiveHint=annotations["destructiveHint"],
                idempotentHint=annotations["idempotentHint"],
                openWorldHint=annotations["openWorldHint"],
            ),
        ))
    if compatibility_port is not None:
        tools.extend(compatibility_tool_models())
    return tools


def _authorization_header(scope: Scope) -> str | None:
    """Return the single Authorization header value, or None when it is absent."""

    found: list[bytes] = []
    for name, value in scope.get("headers") or ():
        if name.lower() == b"authorization":
            found.append(value)
    if not found:
        return None
    if len(found) != 1 or not isinstance(found[0], (bytes, bytearray)):
        raise AuthError(AuthErrorCode.AUTHORIZATION_MALFORMED)
    try:
        return bytes(found[0]).decode("ascii")
    except UnicodeDecodeError:
        raise AuthError(AuthErrorCode.AUTHORIZATION_MALFORMED) from None


def _challenge_header(policy: ResourcePolicy, error: AuthError) -> str:
    """WWW-Authenticate from the public helper. Never assembled here."""

    produced = mcp_auth_error_result(
        policy, error, required_scopes=policy.required_scopes,
    )
    challenge = produced["_meta"]["mcp/www_authenticate"][0]
    if type(challenge) is not str or not challenge:
        raise AuthError(AuthErrorCode.INTERNAL_ERROR)
    return challenge


def _content_classes(entitlement: object) -> frozenset[str] | None:
    """The only attribute the app reads off a resolver result. Fail closed."""

    if entitlement is None:
        return None
    try:
        classes = entitlement.content_classes
    except Exception:
        return None
    if type(classes) is not frozenset or any(type(item) is not str for item in classes):
        return None
    return classes


def _close_awaitable(value: object) -> None:
    if inspect.iscoroutine(value):
        value.close()


def _report_ids(tool: str, arguments: Mapping[str, Any]) -> tuple[str, ...]:
    if tool == "research_fetch":
        value = arguments.get("report_id")
        return (value,) if type(value) is str else ()
    if tool == "research_find_evidence":
        value = arguments.get("report_ids")
        if type(value) is list and all(type(item) is str for item in value):
            return tuple(value)
    return ()


def _tool_error(code: str, *, meta: Mapping[str, Any] | None = None) -> CallToolResult:
    # Compact JSON of the fixed payload only. Inputs and exception text stay out.
    # mcp 1.28.1 returns a CallToolResult from call_tool unchanged
    # (lowlevel/server.py:546-547), so this isError result is not checked
    # against the tool outputSchema.
    payload = error_payload(code)
    # The field alias is `_meta`. Passing meta= stores an extra and the
    # JSON-RPC dump (by_alias=True) omits the challenge. Assign after init.
    result = CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, separators=(",", ":")))],
        structuredContent=payload,
        isError=True,
    )
    if meta is not None:
        result.meta = dict(meta)
    return result


def _auth_tool_error(policy: ResourcePolicy, error: AuthError) -> CallToolResult:
    produced = mcp_auth_error_result(
        policy, error, required_scopes=policy.required_scopes,
    )
    meta = produced.get("_meta")
    if type(meta) is not dict:
        return _tool_error("INTERNAL_ERROR")
    return _tool_error("AUTHENTICATION_REQUIRED", meta=meta)


def _same_projection(left: object, right: object) -> bool:
    try:
        return (
            left.policy_id == right.policy_id
            and left.subject_digest == right.subject_digest
            and left.client_ref == right.client_ref
            and left.resource == right.resource
            and left.scopes == right.scopes
        )
    except Exception:
        return False


def _log_call(
    *,
    code: str,
    tool: str,
    subject_digest: str,
    report_ids: tuple[str, ...],
    latency_ms: int,
) -> None:
    _LOG.info(
        "code=%s tool=%s subject_digest=%s report_ids=%s latency_ms=%s",
        code,
        tool,
        subject_digest,
        report_ids,
        latency_ms,
        extra={
            "code": code,
            "tool": tool,
            "subject_digest": subject_digest,
            "report_ids": report_ids,
            "latency_ms": latency_ms,
        },
    )


def create_authenticated_research_server(
    *,
    authenticator,
    policy,
    now,
    audit_sink,
    port,
    entitlement_resolver,
    context_builder,
    allowed_hosts,
    allowed_origins=(),
    compatibility_port=None,
    selection_scope=None,
) -> Starlette:
    """Return the inert Starlette app. The caller owns the HTTP lifecycle."""

    if not isinstance(policy, ResourcePolicy):
        raise TypeError("policy must be ResourcePolicy")
    if tuple(policy.required_scopes) != _REQUIRED_SCOPE:
        raise ValueError("a dedicated mastermind.research.read policy is required")
    if not isinstance(authenticator, JwtAuthenticator):
        raise TypeError("authenticator must be JwtAuthenticator")
    if not callable(now) or not callable(port):
        raise ValueError("explicit clock and port are required")
    if not callable(entitlement_resolver) or not callable(context_builder):
        raise ValueError("explicit entitlement resolver and context builder are required")
    if not callable(getattr(audit_sink, "emit", None)):
        raise TypeError("audit_sink must provide emit")
    if not allowed_hosts:
        raise ValueError("allowed_hosts is required")
    if compatibility_port is not None and type(compatibility_port) is not CompatibilityPortV1:
        raise ValueError('COMPATIBILITY_COMPOSITION_REFUSED')
    if selection_scope is not None and not callable(selection_scope):
        raise ValueError("selection_scope must be an explicit callable")
    selected = validate_resource_policy(policy)
    hosts = [str(host) for host in allowed_hosts]
    origins = [str(origin) for origin in allowed_origins]

    def _clock() -> int:
        current = now()
        if type(current) is not int:
            raise AuthError(AuthErrorCode.INTERNAL_ERROR)
        return current

    def _emit(*, code: str, accepted: bool) -> bool:
        event = AuthAuditEvent(
            schema=AUTH_AUDIT_SCHEMA,
            policy_id=selected.policy_id,
            code=code,
            accepted=accepted,
        )
        try:
            audit_sink.emit(event)
        except Exception:
            return False
        return True

    server: Server[Any, Any] = Server(
        "mastermind-research-read",
        instructions=(
            "Read-only research catalog, report text and evidence passages "
            "for an entitled caller. Degraded source state is reported, never hidden."
        ),
    )

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return _tool_models(compatibility_port)

    def _peek_subject() -> str:
        try:
            request = server.request_context.request
            principal = None if request is None else request.scope.get(_PRINCIPAL_SCOPE_KEY)
        except Exception:
            return ""
        if type(principal) is VerifiedPrincipal and type(principal.subject_digest) is str:
            return principal.subject_digest
        return ""

    async def _dispatch(
        name: object, arguments: object,
    ) -> tuple[str, str, tuple[str, ...], CallToolResult]:
        subject = _peek_subject()
        report_ids: tuple[str, ...] = ()
        is_compatibility = (compatibility_port is not None and isinstance(name, str)
                            and name in COMPATIBILITY_TOOL_NAMES)
        if not isinstance(name, str) or (name not in TOOL_NAMES and not is_compatibility):
            return "TOOL_NOT_AVAILABLE", subject, report_ids, _tool_error("TOOL_NOT_AVAILABLE")
        try:
            validated = (compatibility_arguments(name, arguments) if is_compatibility
                         else validate_arguments(name, arguments))
        except ContractViolation as exc:
            code = exc.code if exc.code in {"INVALID_REQUEST", "TOOL_NOT_AVAILABLE"} else "INTERNAL_ERROR"
            return code, subject, report_ids, _tool_error(code)
        except Exception:
            return "INVALID_REQUEST", subject, report_ids, _tool_error("INVALID_REQUEST")
        report_ids = _report_ids(name, validated)

        try:
            request = server.request_context.request
            principal = None if request is None else request.scope.get(_PRINCIPAL_SCOPE_KEY)
            if type(principal) is not VerifiedPrincipal:
                raise AuthError(AuthErrorCode.AUTHORIZATION_MISSING)
            projection = principal_projection(principal)
        except Exception:
            return (
                "AUTHENTICATION_REQUIRED",
                subject,
                report_ids,
                _auth_tool_error(selected, AuthError(AuthErrorCode.AUTHORIZATION_MISSING)),
            )
        if type(projection.subject_digest) is str:
            subject = projection.subject_digest

        try:
            entitlement = entitlement_resolver(projection)
        except Exception:
            return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")
        if inspect.isawaitable(entitlement):
            _close_awaitable(entitlement)
            entitlement = None
        if _content_classes(entitlement) is None:
            return "NOT_ENTITLED", subject, report_ids, _tool_error("NOT_ENTITLED")

        # Step 7. Content-class gate. The port is not called on this path.
        required_class = 'evidence_passage' if is_compatibility else _REQUIRED_CLASS[name]
        if required_class not in entitlement.content_classes:
            return "NOT_ENTITLED", subject, report_ids, _tool_error("NOT_ENTITLED")

        if is_compatibility and not compatibility_grant_is_current(entitlement, _clock()):
            return 'NOT_ENTITLED', subject, report_ids, _tool_error('NOT_ENTITLED')

        try:
            caller_context = context_builder(entitlement)
        except Exception:
            return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")
        if inspect.isawaitable(caller_context):
            _close_awaitable(caller_context)
            return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")
        if not isinstance(caller_context, Mapping) or isinstance(caller_context, (str, bytes)):
            return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")

        if is_compatibility and getattr(caller_context, 'principal_id', None) != projection.subject_digest:
            return 'NOT_ENTITLED', subject, report_ids, _tool_error('NOT_ENTITLED')

        if is_compatibility:
            # Context construction may perform synchronous owner I/O. Recheck
            # known token/current-grant deadlines immediately before body lookup.
            admission_time = _clock()
            if principal.expires_at <= admission_time:
                return ('AUTHENTICATION_REQUIRED', subject, report_ids,
                        _auth_tool_error(selected, AuthError(AuthErrorCode.TOKEN_EXPIRED)))
            if not compatibility_grant_is_current(entitlement, admission_time):
                return 'NOT_ENTITLED', subject, report_ids, _tool_error('NOT_ENTITLED')

        try:
            from contextlib import nullcontext
            scope = selection_scope() if selection_scope is not None else nullcontext(None)
            with scope as selected_capture:
                pending = (compatibility_port(name, validated, caller_context,
                                              quote_limit_chars=entitlement.quote_limit_chars)
                           if is_compatibility else port(name, validated, caller_context))
                if not inspect.isawaitable(pending):
                    return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")
                observed = await pending
        except ContractViolation as exc:
            code = exc.code if exc.code in _PORT_REFUSAL else "INTERNAL_ERROR"
            return code, subject, report_ids, _tool_error(code)
        except Exception:
            return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")

        # Recheck authorization, then the selected-source fence. Final grant
        # and expiration decisions below occur after all awaited owner I/O.
        try:
            current = _clock()
            header = None if request is None else request.scope.get(_HEADER_SCOPE_KEY)
            refreshed = await authenticator.verify_authorization_header(header, now=current)
        except AuthError as exc:
            return "AUTHENTICATION_REQUIRED", subject, report_ids, _auth_tool_error(selected, exc)
        except Exception:
            return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")
        try:
            refreshed_projection = principal_projection(refreshed)
        except Exception:
            return (
                "AUTHENTICATION_REQUIRED",
                subject,
                report_ids,
                _auth_tool_error(selected, AuthError(AuthErrorCode.TOKEN_CLAIMS_REFUSED)),
            )
        if not _same_projection(projection, refreshed_projection):
            return (
                "AUTHENTICATION_REQUIRED",
                subject,
                report_ids,
                _auth_tool_error(selected, AuthError(AuthErrorCode.TOKEN_CLAIMS_REFUSED)),
            )
        if selected_capture is not None:
            try:
                await selected_capture.check()
            except Exception:
                return "SOURCE_UNAVAILABLE", subject, report_ids, _tool_error("SOURCE_UNAVAILABLE")
        try:
            refreshed_entitlement = entitlement_resolver(refreshed_projection)
        except Exception:
            return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")
        if inspect.isawaitable(refreshed_entitlement):
            _close_awaitable(refreshed_entitlement)
            refreshed_entitlement = None
        if refreshed_entitlement != entitlement:
            return "NOT_ENTITLED", subject, report_ids, _tool_error("NOT_ENTITLED")

        if is_compatibility:
            try:
                result = compatibility_result(name, observed,
                    quote_limit_chars=refreshed_entitlement.quote_limit_chars,
                    request_id=server.request_context.request_id)
                # Last decision after synchronous owner I/O AND serialization.
                # No await follows; this does not assert validity after ASGI send.
                decision_time = _clock()
                if refreshed.expires_at <= decision_time:
                    return ('AUTHENTICATION_REQUIRED', subject, report_ids,
                            _auth_tool_error(selected, AuthError(AuthErrorCode.TOKEN_EXPIRED)))
                if not compatibility_grant_is_current(refreshed_entitlement, decision_time):
                    return 'NOT_ENTITLED', subject, report_ids, _tool_error('NOT_ENTITLED')
            except ContractViolation as exc:
                code = exc.code if exc.code in _PORT_REFUSAL else 'INTERNAL_ERROR'
                return code, subject, report_ids, _tool_error(code)
            except Exception:
                return 'INTERNAL_ERROR', subject, report_ids, _tool_error('INTERNAL_ERROR')
            return 'OK', subject, report_ids, result

        try:
            if not isinstance(observed, Mapping) or isinstance(observed, (str, bytes)):
                raise ContractViolation("INTERNAL_ERROR")
            data = dict(observed)
            validate_output(name, data)
            if result_wire_bytes(data) > MAX_RESULT_BYTES:
                raise ContractViolation("INTERNAL_ERROR")
            rendered = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")
        result = CallToolResult(
            content=[TextContent(type="text", text=rendered)],
            structuredContent=data,
            isError=False,
        )
        # Final grant I/O may cross a token or grant deadline. Decide only after
        # that synchronous owner read and serialization; no await follows.
        try:
            final_entitlement = entitlement_resolver(refreshed_projection)
            if inspect.isawaitable(final_entitlement):
                _close_awaitable(final_entitlement)
                final_entitlement = None
            if final_entitlement != refreshed_entitlement:
                return "NOT_ENTITLED", subject, report_ids, _tool_error("NOT_ENTITLED")
            decision_time = _clock()
            if refreshed.expires_at <= decision_time:
                return ("AUTHENTICATION_REQUIRED", subject, report_ids,
                        _auth_tool_error(selected, AuthError(AuthErrorCode.TOKEN_EXPIRED)))
            expires_at = getattr(final_entitlement, "expires_at", None)
            if type(expires_at) is not int or expires_at <= decision_time:
                return "NOT_ENTITLED", subject, report_ids, _tool_error("NOT_ENTITLED")
        except Exception:
            return "INTERNAL_ERROR", subject, report_ids, _tool_error("INTERNAL_ERROR")
        return "OK", subject, report_ids, result

    @server.call_tool(validate_input=False)
    async def _call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
        started = time.perf_counter()
        code = "INTERNAL_ERROR"
        subject = ""
        report_ids: tuple[str, ...] = ()
        try:
            code, subject, report_ids, result = await _dispatch(name, arguments)
            return result
        except Exception:
            code = "INTERNAL_ERROR"
            return _tool_error("INTERNAL_ERROR")
        finally:
            try:
                _log_call(
                    code=code,
                    tool=name if isinstance(name, str) else "",
                    subject_digest=subject,
                    report_ids=report_ids,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            except Exception:
                pass

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )
    manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
        security_settings=security,
    )

    async def _refuse(scope: Scope, receive: Receive, send: Send, error: AuthError) -> None:
        status = 403 if error.code is AuthErrorCode.SCOPE_REFUSED else 401
        headers: dict[str, str] = {}
        try:
            headers["WWW-Authenticate"] = _challenge_header(selected, error)
        except Exception:
            headers = {}
        _emit(code=error.code.value, accepted=False)
        response = JSONResponse(
            {"ok": False, "error": {"code": error.code.value, "message": error.public_message}},
            status_code=status,
            headers=headers,
        )
        await response(scope, receive, send)

    class _ResearchAuthGate:
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope.get("type") != "http":
                await manager.handle_request(scope, receive, send)
                return
            try:
                header = _authorization_header(scope)
                principal = await authenticator.verify_authorization_header(header, now=_clock())
            except AuthError as exc:
                await _refuse(scope, receive, send, exc)
                return
            except Exception:
                await _refuse(scope, receive, send, AuthError(AuthErrorCode.INTERNAL_ERROR))
                return
            if not _emit(code="accepted", accepted=True):
                await _refuse(scope, receive, send, AuthError(AuthErrorCode.INTERNAL_ERROR))
                return
            scope[_PRINCIPAL_SCOPE_KEY] = principal
            scope[_HEADER_SCOPE_KEY] = header
            await manager.handle_request(scope, receive, send)

    async def metadata(_request: object) -> JSONResponse:
        return JSONResponse(protected_resource_metadata(selected))

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        async with manager.run():
            yield

    application = Starlette(
        debug=False,
        routes=[
            Route(_url_path(selected.resource_metadata_url), metadata, methods=["GET"]),
            Route(
                _url_path(selected.resource),
                endpoint=_ResearchAuthGate(),
                methods=["POST", "GET", "DELETE"],
            ),
        ],
        lifespan=lifespan,
    )
    application.router.redirect_slashes = False
    application.state.mcp_session_manager = manager
    application.state.resource_policy = selected
    return application


__all__ = ["create_authenticated_research_server"]
