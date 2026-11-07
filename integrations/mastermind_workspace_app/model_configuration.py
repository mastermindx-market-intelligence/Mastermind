"""Fixed authenticated GET composed into the existing Workspace App.

No route-selected filesystem source, writes, credentials, retry or admission.
"""
from starlette.responses import JSONResponse, Response

from common import workspace_model_configuration_contract as wire
from integrations.mastermind_workspace_app import contract
from integrations.mastermind_executive_app.app import _authenticate

PATH = "/workspace/resources/models/current"


async def model_configuration_current(request, *, config):
    from integrations.mastermind_workspace_app.app import (
        _control_room_permissions, _envelope_response, _refuse_json,
        _reject_any_body, _with_no_store,
    )
    principal = await _authenticate(request, config.authenticator, clock=config.now)
    if isinstance(principal, JSONResponse):
        return _with_no_store(principal)
    refused = await _reject_any_body(request)
    if refused is not None:
        return refused
    if request.scope.get("query_string"):
        return _refuse_json(400, "invalid_input")
    try:
        authorizer, client = config.authorize_principal, config.client
        stamps = _control_room_permissions((authorizer,), principal)
        frame = wire.validate_frame({
            "schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
            "selection": None, "principal": contract.principal_frame(principal),
        })
    except Exception:
        return _refuse_json(403, "access_denied")
    try:
        envelope = await client.request(frame)
    except Exception:
        return _refuse_json(503, "source_unavailable")
    try:
        if (config.authorize_principal is not authorizer or config.client is not client
                or _control_room_permissions((authorizer,), principal) != stamps):
            raise ValueError("access_denied")
        now = config.now()
        if type(now) is not int or not 0 <= now < principal.expires_at:
            raise ValueError("access_denied")
    except Exception:
        return _refuse_json(403, "access_denied")
    if type(envelope) is dict and envelope.get("ok") is False:
        return _envelope_response(envelope)
    try:
        if type(envelope) is not dict or set(envelope) != {"ok", "result"} or envelope["ok"] is not True:
            raise ValueError("source_unavailable")
        body = wire.validate_result(envelope["result"])
        raw = contract.bounded_canonical(body, limit=wire.MAX_RESPONSE_BYTES - 1)
    except (TypeError, ValueError, KeyError, RecursionError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200 if body["availability"] == "AVAILABLE" else 503,
                    media_type="application/json", headers={"Cache-Control": "no-store"})
