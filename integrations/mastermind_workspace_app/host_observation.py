"""Fixed authenticated recorded physical-host route; no host acquisition."""
from http import HTTPStatus
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from common import workspace_host_observation_contract as wire
from . import contract
from .app import _authenticate, _with_no_store, _reject_any_body, _decode_v2_query, _check_authorize, _refuse_json, _envelope_response

ROUTE = "/workspace/resources/host-observation/current"
QUERY_KEYS = frozenset({"work_ref", "root_job_id", "job_id", "attempt_id"})


async def host_observation_current(request: Request, *, config):
    if request.method != "GET":
        return _refuse_json(HTTPStatus.METHOD_NOT_ALLOWED, "invalid_input")
    if request.scope.get("raw_path", ROUTE.encode()) != ROUTE.encode():
        return _refuse_json(HTTPStatus.BAD_REQUEST, "invalid_input")
    authenticator, authorize, client, now = config.authenticator, config.authorize_principal, config.client, config.now
    principal = await _authenticate(request, authenticator, clock=now)
    if isinstance(principal, JSONResponse):
        return _with_no_store(principal)
    refused = await _reject_any_body(request)
    if refused is not None:
        return refused
    try:
        parsed = _decode_v2_query(request.scope.get("query_string") or b"", required_keys=QUERY_KEYS)
        selected = wire.selection(parsed)
        frame = wire.validate_frame({"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
            "selection": selected, "principal": contract.principal_frame(principal)})
    except (ValueError, TypeError):
        return _refuse_json(HTTPStatus.BAD_REQUEST, "invalid_input")
    refused = _check_authorize(authorize, principal)
    if refused is not None:
        return refused
    try:
        stamp = contract.permission_stamp(authorize, principal)
        if stamp is None:
            return _refuse_json(HTTPStatus.FORBIDDEN, "access_denied")
        envelope = await client.request(frame)
    except Exception:
        return _refuse_json(HTTPStatus.SERVICE_UNAVAILABLE, "source_unavailable")
    try:
        instant = now()
        if (config.authenticator is not authenticator or config.authorize_principal is not authorize
                or config.client is not client or config.now is not now
                or type(instant) is not int or not principal.issued_at <= instant < principal.expires_at
                or authorize(principal) is not True or contract.permission_stamp(authorize, principal) != stamp):
            return _refuse_json(HTTPStatus.FORBIDDEN, "access_denied")
        if type(envelope) is not dict or envelope.get("ok") is not True:
            return _envelope_response(envelope)
        if set(envelope) != {"ok", "result"}:
            raise ValueError("invalid_response")
        body = wire.validate_result(envelope["result"], selected)
        contract.bounded_canonical(envelope, limit=wire.MAX_RESPONSE_BYTES - 1)
        encoded = contract.bounded_canonical(body, limit=wire.MAX_RESPONSE_BYTES - 1)
        return Response(encoded, status_code=HTTPStatus.OK if body["availability"] == "AVAILABLE" else HTTPStatus.SERVICE_UNAVAILABLE,
            media_type="application/json", headers={"Cache-Control": "no-store"})
    except Exception:
        return _refuse_json(HTTPStatus.SERVICE_UNAVAILABLE, "source_unavailable")
