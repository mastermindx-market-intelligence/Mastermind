"""Fixed authenticated GET over the installed per-attempt T3 fleet read owner.

The attempt id is company run id (``runs/...``) — it contains ``/`` and so can
never ride the fixed-literal path routes (the raw-path fence rejects any
percent-encoded path byte).  The incumbent router's supported shape is the
strict v2 query param ``?attempt_id=<run id>``, decoded exactly once.  Honest
unknowns and typed refusals are served as 200 with the
``mastermind.t3_attempt_fleet/v1`` document; only request/auth faults are 4xx.
"""
from starlette.responses import JSONResponse, Response

from common import workspace_t3_attempt_fleet_contract as wire
from integrations.mastermind_executive_app.app import _authenticate
from integrations.mastermind_workspace_app import contract

PATH = "/workspace/resources/t3/attempts/current"
QUERY_KEYS = frozenset({"attempt_id"})


async def t3_attempt_fleet_current(request, *, config):
    from control_plane.workspace_t3_attempt_fleet_read import validated_document
    from integrations.mastermind_workspace_app.app import (
        _control_room_permissions, _decode_v2_query, _envelope_response,
        _refuse_json, _reject_any_body, _with_no_store,
    )
    principal = await _authenticate(request, config.authenticator, clock=config.now)
    if isinstance(principal, JSONResponse):
        return _with_no_store(principal)
    refused = await _reject_any_body(request)
    if refused is not None:
        return refused
    query = _decode_v2_query(request.scope.get("query_string", b""),
                             required_keys=QUERY_KEYS)
    if query.get("__invalid__") is True or set(query) != QUERY_KEYS:
        return _refuse_json(400, "invalid_input")
    try:
        selected = wire.attempt_id(query["attempt_id"])
    except ValueError:
        return _refuse_json(400, "invalid_input")
    try:
        authorizer, client = config.authorize_principal, config.client
        stamps = _control_room_permissions((authorizer,), principal)
        frame = wire.validate_frame({"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
            "selection": selected, "principal": contract.principal_frame(principal)})
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
        # Envelope plus the projection's own closed per-attempt validator: the
        # wire envelope and the canonical validator must agree on every byte.
        body = validated_document(envelope["result"])
        raw = contract.bounded_canonical(body, limit=wire.MAX_RESPONSE_BYTES - 1)
    except (TypeError, ValueError, KeyError, RecursionError):
        return _refuse_json(503, "source_unavailable")
    return Response(raw, status_code=200,
                    media_type="application/json", headers={"Cache-Control": "no-store"})
