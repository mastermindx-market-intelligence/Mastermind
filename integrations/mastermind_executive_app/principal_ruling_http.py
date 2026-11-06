"""Opt-in HTTP boundary for one host-bound authenticated principal ruling.

The existing COO profile is unchanged. Selection of this app grants no mission,
principal or COMMIT authority. The host supplies a fixed original obligation;
model input is only the existing ruling schema. No discovery, retargeting,
enrollment, retry, listener or Runtime is created here.
"""
from __future__ import annotations

import asyncio
import json

from starlette.responses import JSONResponse

from control_plane.principal_ruling_target import PrincipalRulingTarget  # public compatibility import
from integrations.company_dialogue_principal_host_contract import encode_json_frame
from integrations.executive_mcp.e1_http import (
    BoundedE1App, MAX_REQUEST_BYTES, PREAUTH_RECEIVE_DEADLINE_SECONDS, _RequestTooLarge,
)

PRINCIPAL_RULING_MCP_PATH = "/mcp/principal-ruling"
PRINCIPAL_RULING_SERVER_NAME = "mastermind-principal-ruling"
PRINCIPAL_RULING_SERVER_VERSION = "0.1.0"
PRINCIPAL_RULING_RESULT_SCHEMA = "mastermind.principal_ruling_forward.v1"


class PrincipalRulingHttpBoundary:
    """One literal route, bounded strict JSON and unambiguous credentials.

    Reject duplicate JSON keys before the SDK can normalize them. Preserve the
    original body and Authorization for the existing verifier and call owner.
    This boundary does not authenticate, authorize or retry a request.
    """

    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return
        if (scope.get("path") != PRINCIPAL_RULING_MCP_PATH
                or scope.get("raw_path") != PRINCIPAL_RULING_MCP_PATH.encode("ascii")
                or scope.get("method") != "POST" or scope.get("query_string")):
            await JSONResponse({"ok": False, "error": {"code": "not_found", "message": "route not found"}}, status_code=404)(scope, receive, send)
            return
        credentials = [value for key, value in scope.get("headers", [])
                       if key.lower() == b"authorization"]
        if len(credentials) > 1:
            await JSONResponse({"ok": False, "error": {"code": "authority_refused", "message": "ambiguous authorization"}},
                status_code=401, headers={"WWW-Authenticate": "Bearer"})(scope, receive, send)
            return

        def pairs(items):
            value = {}
            for key, item in items:
                if key in value:
                    raise ValueError("duplicate key")
                value[key] = item
            return value

        def nonfinite(_value):
            raise ValueError("nonfinite value")

        try:
            body = await asyncio.wait_for(BoundedE1App._bounded_request(receive),
                timeout=PREAUTH_RECEIVE_DEADLINE_SECONDS)
            parsed = json.loads(body.decode("utf-8"), object_pairs_hook=pairs,
                                parse_constant=nonfinite)
            # Reuse the existing depth/node/finite/UTF-8 bound. Do not replace the
            # original request with this serialization or relax its byte bound.
            encode_json_frame(parsed, limit=MAX_REQUEST_BYTES)
        except _RequestTooLarge:
            await JSONResponse({"ok": False, "error": {"code": "invalid_input",
                "message": "request body exceeds 65536 bytes"}}, status_code=413)(scope, receive, send)
            return
        except Exception:
            await JSONResponse({"ok": False, "error": {"code": "invalid_input",
                "message": "request body is invalid or incomplete"}},
                status_code=400)(scope, receive, send)
            return
        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self._app(scope, replay, send)
