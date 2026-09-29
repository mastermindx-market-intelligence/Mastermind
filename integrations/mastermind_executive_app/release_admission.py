"""Authenticated release ingress using the existing single-send client.

No Runtime, signing key, lifecycle writer, or automatic retry lives in the app.
The installed Control and root broker retain current authority decisions.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from control_plane.executive_release_ingress import (
    RESPONSE_SCHEMA, ReleaseIngressError, project_frame,
)
from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.mastermind_executive_app.gateway import (
    CeoIngressClient, TRANSPORT_NOT_SENT, TRANSPORT_SENT_UNKNOWN,
)

_PUBLIC_CODES = frozenset({
    "RELEASE_UNAVAILABLE", "RELEASE_APPROVAL_NOT_FOUND", "RELEASE_APPROVAL_EXPIRED",
    "RELEASE_COMMIT_DISARMED", "RELEASE_BROKER_REFUSED", "RELEASE_PRINCIPAL_NOT_CURRENT",
    "RELEASE_APPROVAL_PRINCIPAL_MISMATCH", "RELEASE_APPROVAL_READBACK_UNKNOWN",
    "RELEASE_BROKER_RESPONSE_UNKNOWN", "RELEASE_BROKER_IDENTITY_MISMATCH",
    "RELEASE_BROKER_APPROVAL_CHANGED", "RELEASE_FRAME_INVALID", "RELEASE_ARGUMENTS_INVALID",
})


async def compose_release_admission(*, operation: str, arguments: Any,
        principal: Any, client: CeoIngressClient, socket_path: Path | str) -> dict:
    # Principal is an exact VerifiedPrincipal supplied by app authentication;
    # public arguments have no principal/grant/policy/path/argv fields.
    neutral = principal_projection(principal)
    frame = project_frame(operation, arguments, principal=neutral)
    response = await client.send_frame(socket_path, frame)
    if response.transport == TRANSPORT_NOT_SENT:
        return {"ok": False, "error": {"code": "RELEASE_TRANSPORT_UNAVAILABLE"},
                "effect": "NONE"}
    if response.transport == TRANSPORT_SENT_UNKNOWN:
        return {"ok": False, "error": {"code": "RELEASE_RESPONSE_UNKNOWN"},
                "effect": "EFFECT_UNKNOWN"}
    if response.ok is not True:
        code = (response.error or {}).get("code")
        # A decoded response is not permission to resubmit. Only the owner
        # chooses a typed refusal; no raw local/transport diagnostics escape.
        return {"ok": False, "error": {"code": code if type(code) is str and
                code in _PUBLIC_CODES else "RELEASE_REFUSED"}}
    result = response.result
    if (type(result) is not dict or result.get("schema") != RESPONSE_SCHEMA
            or result.get("operation") != operation or type(result.get("ok")) is not bool):
        return {"ok": False, "error": {"code": "RELEASE_RESPONSE_UNKNOWN"},
                "effect": "EFFECT_UNKNOWN"}
    return result
