"""Host-owned forwarding of one authenticated COO principal ruling.

This module composes existing source contracts: the authenticated COO
App caller derivation, the closed App-peer request framing, and the existing
dedicated ingress client. It registers no HTTP/MCP route, owns no credential,
socket, retry, queue, Runtime handle or identity, and never accepts caller,
context, peer or guard facts from request data.

Outcome law is the existing transport vocabulary. Refusals before the single
send return the existing bounded refused JSONResponse with zero sends. After
the send, the original authentication is compared once more with the existing
comparison only — a successful ruling may legitimately change owed-turn and
new-effect state, so no fresh mandate is acquired and the identity is never
retargeted. Any post-send exception, malformed or lost response, or changed
authentication yields TRANSPORT_SENT_UNKNOWN with the result withheld;
``obligation_id`` is known before the send and stays attached so the original
reply can be recovered even when the response is lost.
"""
from __future__ import annotations

import dataclasses
import json

from starlette.requests import Request
from starlette.responses import JSONResponse

from integrations.company_dialogue_principal_app_contract import encode_app_request
from integrations.company_dialogue_principal_host_contract import (
    MAX_RESPONSE_BYTES,
    encode_json_frame,
    validate_response,
)
from integrations.mastermind_company_mcp.principal_schemas import principal_error_envelope
from integrations.mastermind_executive_app.coo import CooApp, refused
from integrations.mastermind_executive_app.gateway import (
    TRANSPORT_NOT_SENT,
    TRANSPORT_SENT_OK,
    TRANSPORT_SENT_UNKNOWN,
    CeoIngressResponse,
)

FORWARD_TOOL = "ruling"


@dataclasses.dataclass(frozen=True)
class PrincipalDialogueForwardResult:
    """One classified forwarding outcome.

    ``result`` is a detached, canonical host-validated principal result — the
    envelope for a proven ruling, or the bounded sanitized envelope produced by
    the existing principal error projection for a proven inner refusal — and is
    None whenever the outcome is not provable.
    """

    obligation_id: str
    transport: str
    result: dict | None


def _unknown(obligation_id: str) -> PrincipalDialogueForwardResult:
    return PrincipalDialogueForwardResult(obligation_id=obligation_id,
        transport=TRANSPORT_SENT_UNKNOWN, result=None)


def _validated_inner_result(result) -> dict:
    """Validate one inner principal result against the canonical host shape."""
    return validate_response(encode_json_frame(result, limit=MAX_RESPONSE_BYTES),
        tool=FORWARD_TOOL)


def _normalized_result(validated: dict) -> dict:
    """Detach and bound one validated inner result for the host caller."""
    if validated["ok"] is True:
        return validated
    error = validated["error"]
    data = validated["data"]
    return principal_error_envelope(FORWARD_TOOL, code=error["code"],
        message=error["message"], detail_code=error.get("detail_code"),
        reconciliation_message_key=None if data is None else data["message_key"])


async def forward_principal_ruling(app: CooApp, request: Request, *, work_ref: str,
                                   obligation_id: str, arguments: dict,
                                   reasoning_surface: str,
                                   ) -> "PrincipalDialogueForwardResult | JSONResponse":
    """Forward exactly one authenticated principal ruling to the ingress.

    Host-owned helper, not an HTTP/MCP action. The caller is always derived
    from the request's own authenticated principal through the existing COO
    App derivation, which performs the mission and currentness checks; no
    caller, context, peer or guard fact is ever taken from request data.
    """
    try:
        if not isinstance(app, CooApp):
            return refused("internal_error", 500)
        original = await app._auth(request)
        if isinstance(original, JSONResponse):
            return original
        caller = await app.resolve_principal_dialogue_caller(request, work_ref=work_ref,
            reasoning_surface=reasoning_surface)
        if isinstance(caller, JSONResponse):
            return caller
    except Exception:
        return refused("internal_error", 500)
    try:
        frame = json.loads(encode_app_request(caller=caller, obligation_id=obligation_id,
            tool=FORWARD_TOOL, arguments=arguments))
    except Exception:
        return refused("invalid_input", 400)
    try:
        # Mandatory final host guard immediately before the one send.
        if not await app._same_auth(request, original):
            return refused()
    except Exception:
        return refused("internal_error", 500)
    try:
        response = await app._client.send_frame(
            app.settings.executive.ceo_ingress_socket_path, frame)
    except Exception:
        # A transport failure never proves the frame was not delivered.
        return _unknown(obligation_id)
    if type(response) is not CeoIngressResponse:
        return _unknown(obligation_id)
    if response.transport == TRANSPORT_NOT_SENT:
        return PrincipalDialogueForwardResult(obligation_id=obligation_id,
            transport=TRANSPORT_NOT_SENT, result=None)
    if response.transport != TRANSPORT_SENT_OK or response.ok is not True:
        return _unknown(obligation_id)
    if type(response.result) is not dict:
        return _unknown(obligation_id)
    try:
        if not await app._same_auth(request, original):
            return _unknown(obligation_id)
        validated = _validated_inner_result(response.result)
    except Exception:
        return _unknown(obligation_id)
    try:
        result = _normalized_result(validated)
    except Exception:
        return _unknown(obligation_id)
    return PrincipalDialogueForwardResult(obligation_id=obligation_id,
        transport=TRANSPORT_SENT_OK, result=result)
