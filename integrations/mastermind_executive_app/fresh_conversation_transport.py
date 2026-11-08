"""Fixed versioned conversation routes on the existing BFF/carrier.

This leaf owns no listener, credential, Runtime, profile arm, dispatch retry or
session registry. The integrator mounts these literal POST paths only. The
existing Executive audit/verifier pair and independently audited Workspace
READ policy prove each resource; neither principal is injected into ASGI state.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from common import fresh_conversation_contract as wire
from common.executive_workspace_contract import permission_stamp
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK,
)
from integrations.mastermind_executive_app.os_transport import (
    OsExecutiveTransportApp, _OS_HTTP_HEADERS, _access_matches_principal,
    _bearer_token, _bounded_receive_body, _parse_body, RECEIVE_DEADLINE_SECONDS,
    _InvalidBody, _ReceiveTimeout,
)
from integrations.mastermind_workspace_app.app import WorkspaceAppConfig
from integrations.session_bridge.http_foreground import owned_request, bind_request, current_request


class InstalledFreshConversationClient:
    def __init__(self, socket_path, client):
        path = Path(socket_path)
        if type(client) is not CeoIngressClient or not path.is_absolute() or ".." in path.parts:
            raise TypeError("existing dedicated Executive client required")
        self.socket_path, self.client = path, client

    async def request(self, frame):
        frame = wire.validate_private_frame(frame)
        if frame["operation"] in wire.modifying_operations(frame["schema"]):
            # Incumbent transport and upstream attendance source; no new
            # framing flag or caller field may request a duplex lifetime.
            return await self.client._send_frame(self.socket_path, frame,
                keep_write_open=True, foreground_source=current_request())
        return await self.client.send_frame(self.socket_path, frame)


class FreshConversationTransportApp:
    ROUTES = (*wire.ROUTES, *wire.NATIVE_ROUTES)

    def __init__(self, inner_app, *, executive, workspace_config, workspace_verifier, client):
        if (type(executive) is not OsExecutiveTransportApp
                or type(workspace_config) is not WorkspaceAppConfig
                or type(workspace_verifier) is not MastermindTokenVerifier
                or type(client) is not InstalledFreshConversationClient):
            raise TypeError("fixed audited Executive and Workspace composition required")
        self._inner, self._executive = inner_app, executive
        self._workspace, self._workspace_verifier, self._client = workspace_config, workspace_verifier, client

    async def _workspace_principal(self, token):
        access, _ = await self._workspace_verifier.verify_token_with_code(token)
        if access is None:
            return None
        now = self._executive._clock()
        principal = await self._workspace.authenticator.verify_token(token, now=now)
        if (type(principal) is not VerifiedPrincipal or type(now) is not int
                or not principal.issued_at <= now < principal.expires_at
                or not _access_matches_principal(access, principal)
                or self._workspace.authorize_principal(principal) is not True):
            return None
        permission_stamp(self._workspace.authorize_principal, principal)
        return principal

    @staticmethod
    def _token(scope, name):
        values = [value for key, value in scope.get("headers", ()) if key.lower() == name]
        if len(values) != 1:
            raise ValueError("authentication required")
        try:
            return _bearer_token(values[0])
        except Exception:
            raise PermissionError("authentication required") from None

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") not in self.ROUTES:
            await self._inner(scope, receive, send)
            return
        path = scope["path"]
        native = path in wire.NATIVE_ROUTES
        schema = wire.NATIVE_SCHEMA if native else wire.SCHEMA
        result_schema = wire.NATIVE_RESULT_SCHEMA if native else wire.RESULT_SCHEMA
        operation = (wire.NATIVE_ROUTES if native else wire.ROUTES)[path]
        modifying = wire.modifying_operations(schema)
        dual_resource = wire.dual_resource_operations(schema)
        if (scope.get("method") != "POST" or scope.get("scheme") != "https"
                or scope.get("query_string") or scope.get("raw_path") != path.encode("ascii")):
            await Response(status_code=404, headers=_OS_HTTP_HEADERS)(scope, receive, send)
            return

        def refused(code, status=403):
            return JSONResponse(dict(schema=result_schema, operation=operation, ok=False,
                data=None, error=dict(code=code, message="Reconcile the original conversation operation"
                    if code == "effect_unknown" else "Conversation authority or source unavailable")),
                status_code=status, headers=_OS_HTTP_HEADERS)

        entered = False
        try:
            headers = scope.get("headers", ())
            if any(key.lower() in {b"content-encoding", b"transfer-encoding"} for key, _ in headers):
                raise ValueError("invalid input")
            media = [value for key, value in headers if key.lower() == b"content-type"]
            if len(media) != 1 or media[0].split(b";", 1)[0].strip().lower() != b"application/json":
                raise ValueError("invalid input")
            token = self._token(scope, b"authorization")
            executive = await self._executive._verified_binding(token)
            if executive is None:
                response = refused("authentication_required", 401)
            else:
                workspace = workspace_token = stamp = None
                if operation in dual_resource:
                    workspace_token = self._token(scope, b"x-mastermind-workspace-authorization")
                    workspace = await self._workspace_principal(workspace_token)
                    if workspace is None or any(getattr(workspace, key) != getattr(executive, key)
                            for key in ("issuer_digest", "subject_digest", "client_ref")):
                        raise PermissionError("principal mismatch")
                    stamp = permission_stamp(self._workspace.authorize_principal, workspace)
                body_options = {"max_bytes": wire.NATIVE_MAX_REQUEST_BYTES} if native else {}
                raw = await _bounded_receive_body(receive, deadline_seconds=RECEIVE_DEADLINE_SECONDS,
                    **body_options)
                body = _parse_body(raw)
                if type(body) is not dict or set(body) != {"arguments"}:
                    raise ValueError("invalid input")
                arguments = wire.validate_request(body["arguments"], operation=operation, schema=schema)
                def projection(principal):
                    value = dataclasses.asdict(principal)
                    value["scopes"] = list(value["scopes"])
                    return value
                frame = wire.validate_private_frame(dict(schema=schema, operation=operation,
                    principal=projection(executive), workspace_principal=projection(workspace) if workspace else None,
                    arguments=arguments))
                if not await self._executive._still_current(scope, executive):
                    raise PermissionError("principal changed")
                if workspace is not None and (await self._workspace_principal(workspace_token) != workspace
                        or permission_stamp(self._workspace.authorize_principal, workspace) != stamp):
                    raise PermissionError("principal changed")
                now = self._executive._clock()
                remaining = min(300, executive.expires_at - now,
                    workspace.expires_at - now if workspace is not None else 300)
                async with owned_request(scope, receive, deadline_seconds=remaining) as current:
                    with bind_request(Request(current), executive, clock=self._executive._clock) as source:
                        entered = True
                        result = await source.run(lambda: self._client.request(frame))
                        source.require_live()
                if (not await self._executive._still_current(scope, executive)
                        or (workspace is not None and (await self._workspace_principal(workspace_token) != workspace
                            or permission_stamp(self._workspace.authorize_principal, workspace) != stamp))):
                    raise PermissionError("principal changed")
                if result.transport == TRANSPORT_NOT_SENT:
                    response = refused("conversation_unavailable", 503)
                elif result.transport != TRANSPORT_SENT_OK or result.ok is not True:
                    response = refused("effect_unknown" if operation in modifying else "conversation_unavailable",
                        202 if operation in modifying else 503)
                else:
                    value = result.result
                    if (type(value) is not dict or set(value) != {"schema", "operation", "ok", "data", "error"}
                            or value["schema"] != result_schema or value["operation"] != operation
                            or type(value["ok"]) is not bool):
                        raise ValueError("foreign result")
                    if native:
                        wire.validate_native_response(value, arguments, operation=operation)
                    if value["ok"] is True:
                        if value["error"] is not None:
                            raise ValueError("foreign result")
                        if not native:
                            wire.validate_data(value["data"], arguments)
                            if ((operation == "preview") != (value["data"]["state"] == "PREVIEW_READY")
                                    or ((operation == "turn_preview") != (value["data"]["state"] == "TURN_READY"))
                                    or (operation in {"preview", "status", "read", "turn_preview"} and value["data"]["effect"] != "NONE")):
                                raise ValueError("foreign operation result")
                        response = JSONResponse(value, headers=_OS_HTTP_HEADERS)
                    else:
                        unknown = type(value["error"]) is dict and value["error"].get("code") == "effect_unknown"
                        response = refused("effect_unknown" if unknown else "refused", 202 if unknown else 403)
        except PermissionError:
            response = refused("effect_unknown" if entered and operation in modifying else "authentication_required",
                202 if entered and operation in modifying else 403)
        except (TypeError, ValueError, _InvalidBody, _ReceiveTimeout):
            response = refused("effect_unknown" if entered and operation in modifying else "invalid_input",
                202 if entered and operation in modifying else 400)
        except Exception:
            response = refused("effect_unknown" if entered and operation in modifying else "conversation_unavailable",
                202 if entered and operation in modifying else 503)
        await response(scope, receive, send)
