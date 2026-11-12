"""Two fixed Paperclip composition routes on the existing Workspace auth boundary."""
from __future__ import annotations

import json
from urllib.parse import parse_qsl
from starlette.responses import JSONResponse

from integrations.paperclip_control.contract import (
    COMMAND_SCHEMA, MAX_REQUEST_BYTES, SCHEMA, PaperclipError, command_request, read_selection,
)
from integrations.paperclip_control.service import PaperclipWorkspace


async def paperclip_http(request, *, config, command=False):
    from .app import _authenticate, _check_authorize, _reject_any_body, _with_no_store
    principal = await _authenticate(request, config.authenticator, clock=config.now)
    if isinstance(principal, JSONResponse):
        return _with_no_store(principal)
    refusal = _check_authorize(config.authorize_principal, principal)
    if refusal is not None:
        return _with_no_store(refusal)
    operation = None
    try:
        if command:
            if request.scope.get("query_string", b"") or request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                raise PaperclipError("INVALID_COMMAND", status=400)
            chunks = bytearray()
            async for chunk in request.stream():
                if len(chunks) + len(chunk) > MAX_REQUEST_BYTES:
                    raise PaperclipError("INVALID_COMMAND", status=413)
                chunks.extend(chunk)
            def no_duplicate_keys(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate field")
                    result[key] = value
                return result
            operation = command_request(json.loads(chunks, object_pairs_hook=no_duplicate_keys))
        else:
            refusal = await _reject_any_body(request)
            if refusal is not None:
                return _with_no_store(refusal)
            query = request.scope.get("query_string", b"")
            if len(query) > 4096:
                raise PaperclipError("INVALID_SELECTION", status=400)
            pairs = parse_qsl(query.decode("ascii"), keep_blank_values=True, strict_parsing=True, max_num_fields=7)
            if len(pairs) != len(dict(pairs)):
                raise PaperclipError("INVALID_SELECTION", status=400)
            operation = read_selection(dict(pairs))
        if config.paperclip is None:
            raise PaperclipError("PAPERCLIP_NOT_CONFIGURED")
        service = PaperclipWorkspace(config.paperclip, principal, authorize=config.authorize_principal, now=config.now)
        result = await service.command(operation) if command else await service.read(operation)
        # No bearer, connection configuration or upstream body is released here.
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except PaperclipError as exc:
        payload = {"schema": COMMAND_SCHEMA if command else SCHEMA,
                   "state": "EFFECT_UNKNOWN" if exc.effect == "EFFECT_UNKNOWN" else "NOT_APPLIED" if command else "UNAVAILABLE",
                   "code": exc.code, "retryAllowed": False}
        if command and operation is not None:
            payload.update(operation=operation["operation"], requestId=operation["requestId"],
                           bindingRevision=operation["bindingRevision"])
        elif operation is not None:
            payload["view"] = operation["view"]
        if not command:
            payload["availability"] = "UNAVAILABLE"
        # Typed command dispositions are inspectable without guessing from a 5xx.
        # Workspace authentication failures above retain their original status.
        # Source/configuration refusals are typed source availability, not a
        # request to replace the browser's Workspace account.
        return JSONResponse(payload, status_code=200 if command else 400 if exc.status == 400 else 503, headers={"Cache-Control": "no-store"})
    except (ValueError, TypeError, UnicodeError):
        return JSONResponse({"schema": COMMAND_SCHEMA if command else SCHEMA,
            "state": "NOT_APPLIED" if command and operation is None else "EFFECT_UNKNOWN" if command else "UNAVAILABLE",
            "code": "INVALID_COMMAND" if command and operation is None else "SOURCE_RESPONSE_INVALID", "retryAllowed": False},
            status_code=400 if operation is None else 503, headers={"Cache-Control": "no-store"})
