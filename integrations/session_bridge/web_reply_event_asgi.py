"""Opt-in, authenticated event-method dispatcher INSIDE the incumbent /mcp route.

The existing Executive MCP server must mount this only beneath its unchanged
BearerAuthBackend + RequireAuthMiddleware + PreAuthMcpBodyApp composition.
This adapter advertises NO events and cannot install, enroll or deliver one.
It implements no duplicate token verifier, callback transport, state or timer.
Old SDK methods remain byte-for-byte forwarded to the incumbent SDK handler.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from starlette.responses import JSONResponse
from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.session_bridge.web_reply_event_rpc import WebReplyEventRpc, VERSION

_EVENT_METHODS = frozenset({"events/list", "events/subscribe", "events/unsubscribe"})
_MODERN_METHODS = _EVENT_METHODS | {"server/discover", "tools/list", "tools/call"}
_MODERN_META = "io.modelcontextprotocol/protocolVersion"
_MAX_BODY = 65536


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate RPC field")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("nonfinite RPC value")


class WebReplyEventASGI:
    """Single raw MCP endpoint, existing auth before event subscription effects."""

    def __init__(self, downstream: Any, *, rpc: WebReplyEventRpc,
                 authenticate: Callable[..., Any], tools: tuple[Any, ...],
                 tool_dispatch: Callable[..., Any]) -> None:
        if (type(rpc) is not WebReplyEventRpc
                or not callable(downstream) or not callable(authenticate)
                or not callable(tool_dispatch) or type(tools) is not tuple
                or any(not isinstance(getattr(t, "name", None), str)
                       or not callable(getattr(t, "model_dump", None)) for t in tools)
                or len({t.name for t in tools}) != len(tools)):
            raise TypeError("verified, opt-in Executive event/tool composition required")
        self._downstream = downstream
        self._rpc = rpc
        self._authenticate = authenticate
        self._tools = tools
        self._tool_dispatch = tool_dispatch

    async def __call__(self, scope: Mapping[str, Any], receive: Any, send: Any) -> None:
        if (scope.get("type") != "http" or scope.get("path") != "/mcp"
                or scope.get("method") != "POST"):
            await self._downstream(scope, receive, send)
            return

        chunks: list[bytes] = []
        used = 0
        while True:
            event = await receive()
            if event.get("type") != "http.request":
                await JSONResponse({"jsonrpc":"2.0","id":None,"error":{
                    "code":-32600,"message":"incomplete MCP event request"
                }},status_code=400)(scope,receive,send)
                return
            chunk = event.get("body",b"")
            if type(chunk) is not bytes or used + len(chunk) > _MAX_BODY:
                await JSONResponse({"jsonrpc":"2.0","id":None,"error":{
                    "code":-32600,"message":"MCP event request exceeds transport bound"
                }},status_code=413)(scope,receive,send)
                return
            chunks.append(chunk)
            used += len(chunk)
            if event.get("more_body") is not True:
                break
        raw = b"".join(chunks)
        try:
            parsed = json.loads(raw,object_pairs_hook=_unique_pairs,parse_constant=_invalid_constant)
        except (ValueError,UnicodeDecodeError,RecursionError):
            await JSONResponse({"jsonrpc":"2.0","id":None,"error":{
                "code":-32600,"message":"invalid MCP JSON-RPC envelope"
            }},status_code=200,headers={"Cache-Control":"no-store"})(scope,receive,send)
            return

        versions = [v for k, v in scope.get("headers", ())
                    if k.lower() == b"mcp-protocol-version"]
        modern = versions == [VERSION.encode("ascii")]
        method = parsed.get("method") if type(parsed) is dict else None
        # Never hash model/user-controlled JSON values before validating type.
        if modern and type(parsed) is dict and type(method) is not str:
            identifier = parsed.get("id")
            if type(identifier) not in (int, str):
                identifier = None
            await JSONResponse({"jsonrpc":"2.0","id":identifier,"error":{
                "code":-32600,"message":"invalid MCP 2.0 method",
            }},status_code=200,headers={"Cache-Control":"no-store"})(scope,receive,send)
            return
        if (type(parsed) is dict and type(method) is str
                and (method in _EVENT_METHODS
                     or (modern and method in _MODERN_METHODS))):
            response = await self._modern_response(scope, parsed)
            await JSONResponse(response,status_code=200,
                               headers={"Cache-Control":"no-store"})(scope,receive,send)
            return

        sent = False
        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type":"http.request","body":raw,"more_body":False}
            return {"type":"http.disconnect"}
        await self._downstream(scope,replay,send)

    async def _modern_response(self, scope: Mapping[str, Any],
                               request: dict[str, Any]) -> dict[str, Any]:
        request_id = request.get("id")
        if type(request_id) not in (str,int):
            request_id = None

        def err(code: int, message: str):
            return {"jsonrpc":"2.0","id":request_id,
                    "error":{"code":code,"message":message}}

        def ok(result: dict[str, Any]):
            return {"jsonrpc":"2.0","id":request_id,"result":result}

        if (request_id is None or request.get("jsonrpc")!="2.0"
                or set(request) - {"jsonrpc","id","method","params"}):
            return err(-32600,"invalid MCP 2.0 request")
        versions = [v for k,v in scope.get("headers",())
                    if k.lower() == b"mcp-protocol-version"]
        if versions != [VERSION.encode("ascii")]:
            return err(-32600,"MCP Events requires protocol 2026-07-28")

        method = request["method"]
        params = request.get("params",{})
        if type(params) is not dict:
            return err(-32602,"invalid MCP 2.0 parameters")
        meta = params.get("_meta",{})
        if (type(meta) is not dict or meta not in (
                {}, {_MODERN_META: VERSION})):
            return err(-32602,"unsupported MCP protocol metadata")
        try:
            principal = await self._authenticate(scope)
        except Exception:
            principal = None
        if type(principal) is not NeutralPrincipalProjection:
            return err(-32001,"event authorization unavailable")

        if method in _EVENT_METHODS:
            return await self._rpc.handle(request,principal)
        if method == "server/discover":
            if set(params) - {"_meta"}:
                return err(-32602,"invalid discovery parameters")
            catalog = await self._rpc.handle(
                {"jsonrpc":"2.0","id":request_id,"method":"events/list","params":{}},
                principal,
            )
            if "error" in catalog:
                return catalog
            capabilities = {"tools":{}}
            if catalog["result"]["events"]:
                capabilities["events"] = {}
            return ok({"resultType":"complete","supportedVersions":[VERSION],
                       "capabilities":capabilities})
        if method == "tools/list":
            if set(params) - {"_meta","cursor"} or params.get("cursor") is not None:
                return err(-32602,"non-paginated tool catalog")
            return ok({"tools":[tool.model_dump(by_alias=True,mode="json",exclude_none=True)
                                for tool in self._tools]})
        if method == "tools/call":
            if (set(params) - {"name","arguments","_meta"}
                    or type(params.get("name")) is not str
                    or params["name"] not in {t.name for t in self._tools}
                    or type(params.get("arguments")) is not dict):
                return err(-32602,"invalid registered tool call")
            try:
                result = await self._tool_dispatch(
                    scope,params["name"],params["arguments"],
                )
                if type(result) is not dict or type(result.get("content")) is not list:
                    raise ValueError("typed tool result unavailable")
                return ok(result)
            except Exception:
                # The original tool effect might have committed before a lost
                # response. Do not retry, downgrade or claim not-found.
                return err(-32010,"original tool outcome unknown")
        return err(-32601,"unsupported MCP method")


__all__ = ["WebReplyEventASGI"]
