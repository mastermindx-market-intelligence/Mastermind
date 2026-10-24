"""The two fixed direct-result operations over the existing CeoIngress owner.

No Runtime, result path, token cache, listener or retry is constructed here.
The normal OS transport authenticates before body handling and again around
this call. The private receiver independently qualifies its actual App peer
and current direct admission; principal_scope is not a public grant DTO.
"""
from __future__ import annotations

from pathlib import Path

from starlette.responses import JSONResponse

from common import direct_native_result_contract as contract
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, TRANSPORT_NOT_SENT, TRANSPORT_SENT_OK,
)


class DirectNativeResultClient:
    def __init__(self, socket_path, client):
        if type(client) is not CeoIngressClient or socket_path is None:
            raise TypeError("existing dedicated Executive client required")
        path = Path(socket_path)
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("qualified dedicated Executive socket required")
        self.socket_path, self.client = path, client

    async def request(self, body, *, principal_scope, consume=False):
        arguments = contract.validate_request(body, consume=consume)
        contract.hex_digest(principal_scope)
        frame = dict(arguments, schema=contract.PRIVATE_SCHEMA,
                     operation="consume" if consume else "result", principal_scope=principal_scope)
        # Existing send_frame transmits once. A lost reply cannot fall through
        # to another call, operation, account or result source.
        return await self.client.send_frame(self.socket_path, frame)


async def dispatch_direct_native(owner, scope, body, principal, *, consume):
    # Import after construction to avoid an OS transport/module import cycle.
    from integrations.mastermind_executive_app.os_transport import (
        OsExecutiveTransportApp, _OS_HTTP_HEADERS, principal_scope,
    )
    if type(owner) is not OsExecutiveTransportApp or type(principal) is not VerifiedPrincipal:
        raise TypeError("actual OS transport principal required")
    try:
        arguments = contract.validate_request(body, consume=consume)
    except contract.DirectResultContractError:
        return JSONResponse({"ok": False, "error": {"code": "invalid_input",
            "message": "fixed direct-native selection required"}}, status_code=400, headers=_OS_HTTP_HEADERS)
    selection = {key: arguments[key] for key in contract.SELECTION_KEYS}

    def unavailable(reason, status=503):
        return JSONResponse(contract.unavailable(selection, reason), status_code=status, headers=_OS_HTTP_HEADERS)

    if not await owner._still_current(scope, principal):
        return unavailable("AUTHORITY_UNAVAILABLE", 401)
    client = owner._direct_result_client
    if type(client) is not DirectNativeResultClient:
        return unavailable("SOURCE_UNAVAILABLE")
    try:
        response = await client.request(arguments, principal_scope=principal_scope(principal), consume=consume)
    except Exception:
        # Once the one private call begins an unexpected failure is not proof
        # of no mutation. Read/consume never dispatch a Job or provider turn.
        return unavailable("EFFECT_UNKNOWN" if consume else "SOURCE_UNAVAILABLE", 202 if consume else 503)
    if not await owner._still_current(scope, principal):
        return unavailable("EFFECT_UNKNOWN" if consume else "AUTHORITY_UNAVAILABLE", 202 if consume else 401)
    if response.transport == TRANSPORT_NOT_SENT:
        return unavailable("SOURCE_UNAVAILABLE")
    if response.transport != TRANSPORT_SENT_OK:
        return unavailable("EFFECT_UNKNOWN" if consume else "SOURCE_UNAVAILABLE", 202 if consume else 503)
    if response.ok is not True:
        code = response.error.get("code") if isinstance(response.error, dict) else None
        if code in {"authority_refused", "authentication_required"}:
            return unavailable("AUTHORITY_UNAVAILABLE")
        if code in {"state_conflict", "consumption_conflict"}:
            return unavailable("CONSUMPTION_CONFLICT")
        # A clean dependency/size error can follow the actual commit. It is
        # not a receipt proving the acknowledgment absent; retain the original
        # selection for read-only reconciliation, never another mutation send.
        return unavailable("EFFECT_UNKNOWN" if consume else "SOURCE_UNAVAILABLE",
                           202 if consume else 503)
    try:
        value = contract.validate_response(response.result)
        if (any(value["selection"][k] != selection[k] for k in ("work_ref", "job_id"))
                or (selection["attempt_id"] is not None and value["selection"]["attempt_id"] != selection["attempt_id"])):
            raise contract.DirectResultContractError("selection changed")
        if consume and value["availability"] == "AVAILABLE" and (
            value["result"]["result_digest"] != arguments["result_digest"]
            or value["consumption"]["state"] != "CONSUMED"
        ):
            raise contract.DirectResultContractError("consumption changed")
    except (contract.DirectResultContractError, TypeError, KeyError):
        return unavailable("EFFECT_UNKNOWN" if consume else "SOURCE_UNAVAILABLE", 202 if consume else 503)
    return JSONResponse(value, headers=_OS_HTTP_HEADERS)
