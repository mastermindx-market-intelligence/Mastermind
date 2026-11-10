"""Opt-in MCP producer for the WO-12 Hermes host lane (child-request admission).

The existing COO profile is unchanged: the model-facing ``mmx_delegate``
catalogue and its pinned tool-schema digest are untouched (the model-facing
parser refuses the ``selected_child_admit`` action by design — PR #2317
assigns the App-side forwarding of that action to WO-12, which is this
module).  The ``mastermind`` Hermes delegation backend is an EXTERNAL
trusted-host caller, not a model: it authenticates with the same signed
JWT verifiers over the same App, and names the exact admission command the
trusted host already froze into the Control's ``child_request_material``.

Composition follows ``build_principal_ruling_mcp_app`` exactly: an opt-in
producer over an EXISTING :class:`CooApp` — the host owns the core and its
lifecycle; only the MCP session manager is owned here.  One tool,
``child_request_admit``, closed arguments ``{work_ref, command}``.  No
discovery, retargeting, enrollment, retry, listener or Runtime is created
here; the frame is sent once and an uncertain transport keeps the original
command.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

import mcp.types as mcp_types
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.routing import Route

from common.executive_workspace_contract import _check_work_ref
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.business_mcp_auth.metadata import oauth_security_schemes
from integrations.executive_mcp.e1_http import BoundedRequestApp, MAX_RESPONSE_BYTES
from integrations.executive_mcp.schemas import canonical_json
from integrations.mastermind_executive_app.coo import CooApp

import re

HERMES_HOST_MCP_PATH = "/mcp/hermes-host"
HERMES_HOST_SERVER_NAME = "mastermind-executive-hermes-host"
HERMES_HOST_SERVER_VERSION = "0.1.0"
CHILD_REQUEST_ADMIT_TOOL = "child_request_admit"

#: The host-frozen child-request admission command id (WO-13's
#: ``admission_command_id``: ``"child-request:" + sha256(triple)``).  This
#: is deliberately NOT the model-facing ``COMMAND_RE`` (the coo-cycle
#: dispatch shape): child-request command ids never appear in the frozen
#: model catalogue, so the host lane carries its own closed shape.
CHILD_REQUEST_COMMAND_RE = re.compile(r"^child-request:[0-9a-f]{64}$")

#: The closed host-tool input schema: the mission workstream and the exact
#: host-frozen admission command.  Nothing else crosses — the
#: ``ChildExecutionRequest.v1`` envelope never travels through the caller
#: (it is host-frozen under the command id by the trusted host).
CHILD_REQUEST_ADMIT_INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["work_ref", "command"],
    "properties": {
        "work_ref": {"type": "string", "pattern": "^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$",
                     "maxLength": 72},
        "command": {"type": "string",
                     "pattern": CHILD_REQUEST_COMMAND_RE.pattern, "maxLength": 77},
    },
}


def validate_child_request_admit_arguments(arguments: object) -> dict[str, str]:
    """Parse the closed host-tool arguments (work_ref + frozen command)."""

    if not isinstance(arguments, dict):
        raise ValueError("child request arguments must be an object")
    if set(arguments) != {"work_ref", "command"}:
        raise ValueError("child request arguments are not the closed shape")
    work_ref = arguments["work_ref"]
    command = arguments["command"]
    if not isinstance(work_ref, str) or not _check_work_ref(work_ref):
        raise ValueError("child request work_ref is invalid")
    if not isinstance(command, str) or CHILD_REQUEST_COMMAND_RE.fullmatch(command) is None:
        raise ValueError("child request command is not canonical")
    return {"work_ref": work_ref, "command": command}


class HermesHostMcpBoundary:
    """One literal route for the host lane; anything else is not found."""

    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        if (scope.get("path") != HERMES_HOST_MCP_PATH
                or scope.get("raw_path") != HERMES_HOST_MCP_PATH.encode("ascii")
                or scope.get("method") != "POST" or scope.get("query_string")):
            from starlette.responses import JSONResponse
            await JSONResponse({"ok": False, "error": {
                "code": "not_found", "message": "route not found"}},
                status_code=404)(scope, receive, send)
            return
        await self._app(scope, receive, send)


def build_hermes_host_mcp_app(core: CooApp) -> HermesHostMcpBoundary:
    """The host-lane MCP app over an existing authenticated COO App.

    The caller owns the :class:`CooApp` (and through it the ingress socket
    path, policies, JWKS and audit sink); this producer only wraps one more
    MCP session manager around it.  The tool surface is exactly one
    admission-forwarding tool; selection of this app grants no mission,
    placement or COMMIT authority beyond what the App's own authenticated
    providers already prove.
    """

    if type(core) is not CooApp:
        raise ValueError("the Hermes host lane composes over an existing COO App")
    settings = core.settings
    oauth = MastermindTokenVerifier(authenticator=core.authenticator,
        policy=settings.policy, now=settings.executive.clock,
        audit_sink=core._audit_sink)

    class BoundVerifier:
        async def verify_token(self, token):
            access = await oauth.verify_token(token)
            if access is None:
                return None
            try:
                principal, _ = await core.authorize_token(token)
                if (access.client_id != principal.client_ref
                        or access.subject != principal.subject_digest
                        or access.resource != principal.resource
                        or access.scopes != list(principal.scopes)):
                    return None
            except Exception:
                return None
            return access

    server = Server(HERMES_HOST_SERVER_NAME, version=HERMES_HOST_SERVER_VERSION)
    schemes = oauth_security_schemes(settings.policy.required_scopes)
    tool = mcp_types.Tool(name=CHILD_REQUEST_ADMIT_TOOL,
        description=("Forward one host-frozen ChildExecutionRequest.v1 admission "
                     "command to the Executive Control through the App's own "
                     "authenticated providers. The envelope never travels through "
                     "the caller; admission selects nothing (OQ-9)."),
        inputSchema=CHILD_REQUEST_ADMIT_INPUT_SCHEMA,
        annotations=mcp_types.ToolAnnotations(title="Child request admission (host lane)",
            read_only_hint=True),
        securitySchemes=schemes, _meta={"securitySchemes": schemes})

    @server.list_tools()
    async def list_tools():
        return [tool]

    def result(payload, challenge=None):
        return mcp_types.CallToolResult(content=[mcp_types.TextContent(type="text",
            text=canonical_json(payload).decode("utf-8"))],
            isError=payload.get("ok") is not True,
            _meta={"mcp/www_authenticate": [challenge]} if challenge else None)

    def invalid(message):
        return result({"ok": False, "error": {"kind": "invalid_input",
                                              "message": message}})

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        request = server.request_context.request
        if not isinstance(request, Request) or len(request.headers.getlist("authorization")) != 1:
            return invalid("unambiguous current authorization required")
        if name != CHILD_REQUEST_ADMIT_TOOL:
            return invalid("unknown host-lane tool")
        try:
            validated = validate_child_request_admit_arguments(arguments)
        except (TypeError, ValueError):
            return invalid("invalid child request admission arguments")
        try:
            authenticated = await core.authorize_token(
                request.headers["authorization"].removeprefix("Bearer ").strip())
        except Exception:
            return result({"ok": False, "error": {
                "kind": "authority_refused",
                "message": "the host principal is not current"}}, "Bearer")
        try:
            outcome = await core.child_request_admit(request, authenticated, validated)
            if not hasattr(outcome, "body") or not hasattr(outcome, "headers"):
                return result({"ok": False, "error": {
                    "kind": "unknown",
                    "message": "EXECUTIVE_CHILD_REQUEST_EFFECT_UNKNOWN"}})
            payload = json.loads(bytes(outcome.body).decode("utf-8"))
            reply = result(payload, outcome.headers.get("www-authenticate"))
            if len(reply.model_dump_json(by_alias=True).encode("utf-8")) > MAX_RESPONSE_BYTES - 4096:
                return result({"ok": False, "error": {
                    "kind": "unknown",
                    "message": "EXECUTIVE_CHILD_REQUEST_EFFECT_UNKNOWN"}})
            return reply
        except Exception:
            # An unrecognized post-send failure never proves no effect; the
            # caller reconciles by the original command.
            return result({"ok": False, "error": {
                "kind": "unknown",
                "message": "EXECUTIVE_CHILD_REQUEST_EFFECT_UNKNOWN"}})

    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True,
        security_settings=TransportSecuritySettings(
            allowed_hosts=["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*",
                           "::1", "[::1]", "[::1]:*"],
            allowed_origins=[]))
    authenticated = AuthenticationMiddleware(
        RequireAuthMiddleware(BoundedRequestApp(manager.handle_request),
            required_scopes=list(settings.policy.required_scopes),
            resource_metadata_url=settings.policy.resource_metadata_url),
        backend=BearerAuthBackend(BoundVerifier()))

    @asynccontextmanager
    async def lifespan(_app):
        async with manager.run():
            yield

    app = Starlette(routes=[Route(HERMES_HOST_MCP_PATH, authenticated, methods=["POST"])],
                    lifespan=lifespan)
    app.router.redirect_slashes = False
    return HermesHostMcpBoundary(app)
