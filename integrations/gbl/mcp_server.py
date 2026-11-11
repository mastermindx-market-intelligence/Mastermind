"""GBL-3 MCP edge — the static five-tool census behind the imported token law.

This edge is wiring, not new authority (BUILD_PLAN row GBL-3; the prep
verdict "serves-with-config"):

* ``business_mcp_auth`` is imported AS IT IS: ``JwtAuthenticator`` enforces
  the whole bearer law (strict RS256, canonical segments, header, lifetime,
  issuer, audience == resource, exact scope ``mastermind.gbl.bridge``,
  enrolled subject digests); ``metadata.py``'s public builders produce the
  RFC 9728 protected-resource document and the ``WWW-Authenticate`` Bearer
  challenge this app serves.  PKCE is the external authorization server's
  concern — this edge hosts no authorize/token/registration endpoint, so it
  works with or without PKCE.
* Admission is by token only, in the lane's fixed order (``admission.py``):
  principal → targets → kinds → rates → per-thread allowlist.  The table
  ships EMPTY.  No source address, no header, no API key is ever admission
  (the connector's static-header variant is refused typed).
* The census is static — exactly ``team.delegate``, ``team.result``,
  ``team.question``, ``team.answer``, ``team.message`` — with the schema
  digest pinned by a literal; there is no dynamic tool registration and
  dispatch refuses any other name.
* Tools dispatch to the GBL-2 bridge over its Unix socket
  (``mastermind.gbl.request.v1`` frames, the GBL-1 codec).  ``team.message``
  goes through ``message_send.MessageSender`` after the allowlist gate —
  the marker law holds one-send; the body is always quoted data.

The verified principal's ``subject_digest`` is the only identity input; the
admission row supplies the bridge-side principal label.  Tool arguments
carry no admission field, and a smuggled one is ``INVALID_ARGUMENTS``.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import socket as socket_module
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

import mcp.types as mcp_types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from common.company_consultation_host_contract import HostFrameError
from common.gbl_contract import (
    ASK_BODY_MAX_CHARS,
    BODY_MAX_CHARS,
    GBLContractError,
    MAX_ANSWER_CHARS,
    MAX_FRAME_BYTES,
    TITLE_MAX_CHARS,
    decode_gbl_frame,
    encode_gbl_frame,
)
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
from integrations.gbl.admission import (
    GblAdmissionError,
    admit_kind,
    admit_message_thread,
    admit_principal,
    admit_rate,
    admit_target,
)
from integrations.gbl.bridge_service import REQUEST_SCHEMA
from integrations.gbl.message_send import GblMessageError, MessageSender

SERVER_NAME = "mastermind-gbl-bridge"
SERVER_VERSION = "1"
RESULT_SCHEMA = "mastermind.gbl.mcp_result.v1"
MAX_ARGUMENT_BYTES = MAX_FRAME_BYTES      # one GBL frame is the edge ceiling
BRIDGE_TIMEOUT_SECONDS = 10.0
MAX_BRIDGE_RESPONSE_BYTES = 2 * 1024 * 1024


class GblEdgeError(ValueError):
    """Closed typed edge failure; ``code`` names the rule."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# ── The static census (digest-pinned; no dynamic registration) ───────────────


def _string(*, max_length: int, pattern: str | None = None) -> dict:
    value: dict[str, Any] = {"type": "string", "minLength": 1,
                             "maxLength": max_length}
    if pattern is not None:
        value["pattern"] = pattern
    return value


def _object(properties: Mapping[str, Any], required: tuple[str, ...]) -> dict:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(required),
        "additionalProperties": False,     # no admission field can ride along
    }


_ASK_KEY = _string(max_length=96,
                   pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_ASK_ID = _string(max_length=35, pattern=r"^gb-[0-9a-f]{32}$")


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """One immutable census row."""

    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool

    @property
    def annotations(self) -> dict[str, Any]:
        return {
            "title": self.name,
            "readOnlyHint": self.read_only,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="team.answer",
        description=(
            "Post the bot's answer to one ask addressed to this principal. "
            "Idempotent by (ask_id, idempotency_key); a replay of the same "
            "key with new text is a CONFLICT."
        ),
        input_schema=_object(
            {"ask_id": _ASK_ID, "text": _string(max_length=MAX_ANSWER_CHARS),
             "idempotency_key": _ASK_KEY},
            ("ask_id", "text", "idempotency_key")),
        read_only=False,
    ),
    ToolSpec(
        name="team.delegate",
        description=(
            "Delegate one bounded job to an admitted teammate target. The "
            "ask id is minted from (principal, target, idempotency_key); "
            "same key and content returns the same ask, changed content is "
            "a CONFLICT."
        ),
        input_schema=_object(
            {"target": _string(max_length=256),
             "title": _string(max_length=TITLE_MAX_CHARS),
             "body": _string(max_length=ASK_BODY_MAX_CHARS),
             "idempotency_key": _ASK_KEY},
            ("target", "title", "body", "idempotency_key")),
        read_only=False,
    ),
    ToolSpec(
        name="team.message",
        description=(
            "Send one quoted-data message to a thread on an admitted "
            "environment, only to a (environment, thread) row the "
            "principal switched on. One send per idempotency key, held by "
            "the [gb-<id>] marker."
        ),
        input_schema=_object(
            {"environment_id": _string(max_length=256),
             "thread_ref": _string(max_length=256),
             "body": _string(max_length=BODY_MAX_CHARS),
             "idempotency_key": _ASK_KEY},
            ("environment_id", "thread_ref", "body", "idempotency_key")),
        read_only=False,
    ),
    ToolSpec(
        name="team.question",
        description=(
            "Read the question body of one ask addressed to this principal. "
            "Read-only; the ask must exist and belong to the caller."
        ),
        input_schema=_object({"ask_id": _ASK_ID}, ("ask_id",)),
        read_only=True,
    ),
    ToolSpec(
        name="team.result",
        description=(
            "Fetch the answer of one of this principal's asks. An "
            "unconsumed answer surfaces as ANSWER_UNCONSUMED; a stale ask "
            "as EXPIRED."
        ),
        input_schema=_object({"ask_id": _ASK_ID}, ("ask_id",)),
        read_only=True,
    ),
)

TOOL_NAMES = frozenset(spec.name for spec in TOOL_SPECS)
TOOL_ARGUMENT_KEYS = {spec.name: frozenset(spec.input_schema["required"])
                      for spec in TOOL_SPECS}


def tool_schema_snapshot() -> list[dict[str, Any]]:
    """The exact advertised census, sorted by name (the digest's input)."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "input_schema": spec.input_schema,
            "annotations": spec.annotations,
        }
        for spec in sorted(TOOL_SPECS, key=lambda item: item.name)
    ]


def tool_schema_digest() -> str:
    payload = json.dumps(tool_schema_snapshot(), sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Deliberately literal: any reviewed schema/description/annotation change
# must update this value explicitly and is therefore visible in review.
TOOL_SCHEMA_DIGEST = "b9e66d2e79804cdac5b165f6be1caa9342b7ed0938a1f792fc7baafb802d1092"


def build_tool_models() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name=spec.name,
            description=spec.description,
            inputSchema=spec.input_schema,
            annotations=mcp_types.ToolAnnotations(**spec.annotations),
        )
        for spec in TOOL_SPECS
    ]


# ── The bridge client (Unix socket, GBL frames) ──────────────────────────────


class BridgeClient:
    """One request per connection to the GBL-2 bridge's AF_UNIX socket."""

    def __init__(self, socket_path: Path | str) -> None:
        self._path = Path(socket_path)

    def call(self, op: str, arguments: Mapping[str, Any]) -> dict:
        request = {"schema": REQUEST_SCHEMA, "op": op,
                   "arguments": dict(arguments)}
        try:
            frame = encode_gbl_frame(request)
        except HostFrameError:
            raise GblEdgeError("FRAME_TOO_LARGE",
                               "bridge request exceeds the frame cap") from None
        with socket_module.socket(socket_module.AF_UNIX,
                                  socket_module.SOCK_STREAM) as connection:
            connection.settimeout(BRIDGE_TIMEOUT_SECONDS)
            connection.connect(str(self._path))
            connection.sendall(frame)
            buffer = b""
            while not buffer.endswith(b"\n"):
                chunk = connection.recv(4096)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > MAX_BRIDGE_RESPONSE_BYTES:
                    raise GblEdgeError("BRIDGE_RESPONSE_TOO_LARGE")
        try:
            response = decode_gbl_frame(buffer)
        except HostFrameError:
            raise GblEdgeError("BRIDGE_PROTOCOL", "unframed bridge reply") from None
        if response.get("ok") is True:
            result = response.get("result")
            return dict(result) if isinstance(result, dict) else {}
        error = response.get("error")
        if isinstance(error, dict):
            raise GblEdgeError(str(error.get("code", "BRIDGE_ERROR")),
                               str(error.get("detail", "")))
        raise GblEdgeError("BRIDGE_PROTOCOL", "untyped bridge refusal")


# ── Result envelopes (fixed shape; no dependency detail crosses) ─────────────


def _text_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _ok_result(result: Mapping[str, Any]) -> mcp_types.CallToolResult:
    payload = {"schema": RESULT_SCHEMA, "ok": True, "result": dict(result)}
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=_text_payload(payload))],
        structuredContent=payload,
        isError=False,
    )


def _error_result(code: str, detail: str = "") -> mcp_types.CallToolResult:
    payload = {"schema": RESULT_SCHEMA, "ok": False,
               "error": {"code": code, "detail": detail}}
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=_text_payload(payload))],
        structuredContent=payload,
        isError=True,
    )


# ── The app ──────────────────────────────────────────────────────────────────

_PRINCIPAL_SCOPE_KEY = "mastermind.gbl_mcp.principal"


def _authorization_header(scope: Scope) -> str | None:
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
    produced = mcp_auth_error_result(policy, error,
                                     required_scopes=policy.required_scopes)
    challenge = produced["_meta"]["mcp/www_authenticate"][0]
    if type(challenge) is not str or not challenge:
        raise AuthError(AuthErrorCode.INTERNAL_ERROR)
    return challenge


def create_gbl_mcp_app(
    *,
    authenticator: JwtAuthenticator,
    policy: ResourcePolicy,
    now: Callable[[], int],
    audit_sink: Any,
    admission_table: tuple = (),
    bridge_client: BridgeClient,
    message_sender: MessageSender,
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost"),
    allowed_origins: tuple[str, ...] = (),
    asks_last_hour: Callable[[str], int] | None = None,
) -> Starlette:
    """Return the inert Starlette app. The caller owns the HTTP lifecycle."""

    if not isinstance(policy, ResourcePolicy):
        raise TypeError("policy must be ResourcePolicy")
    selected = validate_resource_policy(policy)
    if not isinstance(authenticator, JwtAuthenticator):
        raise TypeError("authenticator must be JwtAuthenticator")
    if not callable(now):
        raise ValueError("an explicit clock is required")
    if not callable(getattr(audit_sink, "emit", None)):
        raise TypeError("audit_sink must provide emit")
    if not callable(getattr(bridge_client, "call", None)):
        raise TypeError("bridge_client must provide call(op, arguments)")
    if not isinstance(message_sender, MessageSender):
        raise TypeError("message_sender must be a MessageSender")
    table = tuple(admission_table)
    counter = asks_last_hour or (lambda principal: 0)

    def _clock() -> int:
        current = now()
        if type(current) is not int:
            raise AuthError(AuthErrorCode.INTERNAL_ERROR)
        return current

    def _emit(*, code: str, accepted: bool) -> bool:
        event = AuthAuditEvent(schema=AUTH_AUDIT_SCHEMA,
                               policy_id=selected.policy_id,
                               code=code, accepted=accepted)
        try:
            audit_sink.emit(event)
        except Exception:
            return False
        return True

    server: Server[Any, Any] = Server(SERVER_NAME, version=SERVER_VERSION)

    @server.list_tools()
    async def _list_tools() -> list[mcp_types.Tool]:
        return build_tool_models()          # the frozen census, nothing else

    def _canonical_argument_bytes(arguments: Mapping[str, Any]) -> bytes:
        return json.dumps(arguments, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")

    def _validated_arguments(name: str, arguments: object) -> dict[str, str]:
        if not isinstance(arguments, dict):
            raise GblEdgeError("INVALID_ARGUMENTS", "arguments must be an object")
        expected = TOOL_ARGUMENT_KEYS[name]
        if set(arguments) != set(expected):
            raise GblEdgeError("INVALID_ARGUMENTS",
                               "exact census arguments required")
        for key, value in arguments.items():
            if not isinstance(value, str) or not value:
                raise GblEdgeError("INVALID_ARGUMENTS", f"{key} must be text")
        return dict(arguments)

    async def _dispatch(name: object, arguments: object
                        ) -> mcp_types.CallToolResult:
        try:
            if not isinstance(name, str) or name not in TOOL_NAMES:
                return _error_result("TOOL_NOT_AVAILABLE", str(name)[:64])
            raw = arguments if isinstance(arguments, dict) else {}
            try:
                if len(_canonical_argument_bytes(raw)) > MAX_ARGUMENT_BYTES:
                    return _error_result("FRAME_TOO_LARGE",
                                         "arguments exceed the frame cap")
            except (TypeError, ValueError):
                return _error_result("INVALID_ARGUMENTS", "unserializable")
            args = _validated_arguments(name, raw)

            request = server.request_context.request
            principal = None if request is None else (
                request.scope.get(_PRINCIPAL_SCOPE_KEY))
            if not isinstance(principal, VerifiedPrincipal):
                return _error_result("AUTHENTICATION_REQUIRED")

            # The lane order: principal → target → kind → rate → allowlist.
            row = admit_principal(table, principal.subject_digest)
            if name == "team.delegate":
                admit_target(row, args["target"])
                admit_kind(row, "delegate")
                admit_rate(row, counter(row.principal))
                result = await asyncio.to_thread(
                    bridge_client.call, "ask",
                    {"kind": "delegate", "principal": row.principal,
                     "target": args["target"], "title": args["title"],
                     "body": args["body"],
                     "idempotency_key": args["idempotency_key"]})
            elif name == "team.question":
                result = await asyncio.to_thread(
                    bridge_client.call, "question",
                    {"principal": row.principal, "ask_id": args["ask_id"]})
            elif name == "team.answer":
                result = await asyncio.to_thread(
                    bridge_client.call, "answer",
                    {"principal": row.principal, "ask_id": args["ask_id"],
                     "text": args["text"],
                     "idempotency_key": args["idempotency_key"]})
            elif name == "team.result":
                result = await asyncio.to_thread(
                    bridge_client.call, "result",
                    {"principal": row.principal, "ask_id": args["ask_id"]})
            else:                                       # team.message
                admit_message_thread(row, args["environment_id"],
                                     args["thread_ref"])
                result = await asyncio.to_thread(
                    message_sender.send,
                    principal=row.principal,
                    environment_id=args["environment_id"],
                    thread_ref=args["thread_ref"],
                    idempotency_key=args["idempotency_key"],
                    body=args["body"])
            return _ok_result(result)
        except GblAdmissionError as error:
            return _error_result(error.code, error.detail)
        except GblEdgeError as error:
            return _error_result(error.code, error.detail)
        except GblMessageError as error:
            return _error_result(error.code, error.detail)
        except GBLContractError as error:
            return _error_result(error.code, error.detail)
        except Exception:
            return _error_result("INTERNAL_ERROR")

    @server.call_tool(validate_input=False)
    async def _call_tool(name: str,
                         arguments: dict[str, Any] | None
                         ) -> mcp_types.CallToolResult:
        return await _dispatch(name, arguments)

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[str(host) for host in allowed_hosts],
        allowed_origins=[str(origin) for origin in allowed_origins],
    )
    manager = StreamableHTTPSessionManager(
        app=server,
        stateless=True,
        json_response=True,
        security_settings=security,
    )

    async def _refuse(scope: Scope, receive: Receive, send: Send,
                      error: AuthError) -> None:
        status = 403 if error.code is AuthErrorCode.SCOPE_REFUSED else 401
        headers: dict[str, str] = {}
        try:
            headers["WWW-Authenticate"] = _challenge_header(selected, error)
        except Exception:
            headers = {}
        _emit(code=error.code.value, accepted=False)
        response = JSONResponse(
            {"ok": False,
             "error": {"code": error.code.value,
                       "message": error.public_message}},
            status_code=status,
            headers=headers,
        )
        await response(scope, receive, send)

    class _GblAuthGate:
        async def __call__(self, scope: Scope, receive: Receive,
                           send: Send) -> None:
            if scope.get("type") != "http":
                await manager.handle_request(scope, receive, send)
                return
            try:
                header = _authorization_header(scope)
                principal = await authenticator.verify_authorization_header(
                    header, now=_clock())
            except AuthError as error:
                await _refuse(scope, receive, send, error)
                return
            except Exception:
                await _refuse(scope, receive, send,
                              AuthError(AuthErrorCode.INTERNAL_ERROR))
                return
            if not _emit(code="accepted", accepted=True):
                await _refuse(scope, receive, send,
                              AuthError(AuthErrorCode.INTERNAL_ERROR))
                return
            scope[_PRINCIPAL_SCOPE_KEY] = principal
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
            Route(urlsplit(selected.resource_metadata_url).path or "/",
                  metadata, methods=["GET"]),
            Route(urlsplit(selected.resource).path or "/",
                  endpoint=_GblAuthGate(), methods=["POST", "GET", "DELETE"]),
        ],
        lifespan=lifespan,
    )
    application.router.redirect_slashes = False
    application.state.mcp_session_manager = manager
    application.state.resource_policy = selected
    return application


__all__ = [
    "BRIDGE_TIMEOUT_SECONDS",
    "BridgeClient",
    "MAX_ARGUMENT_BYTES",
    "RESULT_SCHEMA",
    "SERVER_NAME",
    "SERVER_VERSION",
    "TOOL_ARGUMENT_KEYS",
    "TOOL_NAMES",
    "TOOL_SCHEMA_DIGEST",
    "TOOL_SPECS",
    "ToolSpec",
    "build_tool_models",
    "create_gbl_mcp_app",
    "tool_schema_digest",
    "tool_schema_snapshot",
]
