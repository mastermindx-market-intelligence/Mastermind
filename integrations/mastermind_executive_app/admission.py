"""integrations.mastermind_executive_app.admission — the ONE modifying path.

Composes, in the load-bearing order below, the exact steps BSC-E1's FROZEN
SPEC requires for ``submit_ceo_intent``:

1. Validate the caller payload against the EXISTING public five-tool request
   shape (:func:`integrations.executive_mcp.schemas.validate_tool_arguments`
   — reused verbatim, never copied).  A caller/model cannot supply ``actor``,
   ``authority``, raw capabilities, ``branch``, ``worktree``, ``grounding``,
   ``request_ref``, intent/job/status, provider/account/session, or a socket
   target: none of those names appear in that schema's
   ``additionalProperties: false`` object, so they are structurally
   impossible, not merely refused by a runtime check.
2. Derive one stable ``req-*`` outer identity via
   :func:`control_plane.ceo_request.app_request_ref` — depends ONLY on the
   validated ``operation_key`` (the approved logical operation identity),
   never on the caller's OAuth subject/client/app/session/transport/time.
3. Fresh-read trusted grounding immediately before effect
   (:func:`integrations.mastermind_executive_app.gateway.observe_trusted_grounding`).
4. Build the exact CeoIngress v2 submit frame and send it to ONE bounded
   request against the already-installed dedicated ingress socket
   (:class:`integrations.mastermind_executive_app.gateway.CeoIngressClient`).
   ``ceo_intent.submit_intent`` is never called in this module, and no
   ``control_plane.executive_runtime.Runtime`` is ever opened here.
5. Classify the response: ``dispatched`` must be exactly ``False``; a
   missing, non-boolean, or ``True`` value is a backend contract defect,
   never presented as success.
6. On response loss after the frame was provably sent (``EFFECT_UNKNOWN``),
   reconcile through the SAME v2 status frame on the SAME ``request_ref`` —
   never resubmit, never fail over to another transport.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from control_plane import ceo_request
from control_plane import executive_ceo_ingress as ceo_ingress
from integrations.business_mcp_auth.contracts import VerifiedPrincipal
from integrations.executive_mcp.schemas import MODIFYING_TOOL, GatewayError, validate_tool_arguments
from integrations.mastermind_executive_app.gateway import (
    READ_SCOPE,
    SUBMIT_SCOPE,
    CeoIngressClient,
    CeoIngressResponse,
    GroundingUnavailable,
    TRANSPORT_SENT_OK,
    TRANSPORT_SENT_UNKNOWN,
    observe_trusted_grounding,
)

__all__ = [
    "STATUS_ACCEPTED",
    "STATUS_CONFLICT",
    "STATUS_EFFECT_UNKNOWN",
    "STATUS_REFUSED",
    "STATUS_TRANSPORT_UNAVAILABLE",
    "AdmissionError",
    "AdmissionOutcome",
    "AdmissionRequest",
    "compose_admission",
    "principal_authorizes_submit",
    "reconcile_by_request_ref",
]


#: Closed outcome vocabulary this module ever returns.  A caller (the ASGI
#: edge) maps each 1:1 onto an HTTP status; nothing here invents a sixth.
STATUS_ACCEPTED = "accepted"
STATUS_CONFLICT = "operation_conflict"
STATUS_REFUSED = "refused"
STATUS_TRANSPORT_UNAVAILABLE = "ingress_unavailable"
STATUS_EFFECT_UNKNOWN = "effect_unknown"


class AdmissionError(ValueError):
    """One caller-facing admission refusal: closed ``code`` + bounded message.

    Always raised for a refusal that happened BEFORE any socket effect was
    possible (payload/scope refusals, grounding unavailable). A refusal that
    arrives FROM the dedicated ingress after a real send is never raised as
    an exception — it is returned as a :class:`AdmissionOutcome` with
    ``status=STATUS_REFUSED`` so its receipt-shaped detail survives.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclasses.dataclass(frozen=True)
class AdmissionOutcome:
    """One classified result of one attempted admission."""

    status: str
    request_ref: str
    receipt: dict[str, Any] | None = None
    code: str | None = None
    message: str = ""


def principal_authorizes_submit(principal: VerifiedPrincipal) -> bool:
    """Require BOTH scopes on the already-verified principal (step 1).

    ``principal`` must already have been verified against
    :attr:`gateway.AppPolicies.submit`, whose ``required_scopes`` is exactly
    ``(SUBMIT_SCOPE, READ_SCOPE)`` sorted — this is a defense-in-depth
    re-assertion, not the primary gate (the primary gate is which policy the
    bearer token was checked against at all).
    """

    scopes = set(principal.scopes)
    return READ_SCOPE in scopes and SUBMIT_SCOPE in scopes


@dataclasses.dataclass(frozen=True)
class AdmissionRequest:
    """Everything one admission attempt needs, all already-trusted/injected.

    ``payload`` is the ONLY caller/model-controlled value.  Every other field
    is host configuration or an already-verified principal — never
    reconstructible from the wire request.
    """

    payload: Mapping[str, Any]
    principal: VerifiedPrincipal
    ceo_ingress_socket_path: "Path | str"
    mastermind_root: "Path | str"
    macro_root_flag: str | None
    environ: Mapping[str, str]
    client: CeoIngressClient


def _validate_five_tool_shape(payload: Any) -> dict[str, Any]:
    """Step 1 — reuse the EXISTING public ``submit_ceo_intent`` validator.

    Raises :class:`AdmissionError` (never a bare ``GatewayError``) so this
    module owns one closed vocabulary end to end.
    """

    try:
        return validate_tool_arguments(MODIFYING_TOOL, payload)
    except GatewayError as exc:
        raise AdmissionError("invalid_input", exc.message) from exc


def _build_v2_frame(
    *, request_ref: str, grounding: Mapping[str, str], semantic_request: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema": ceo_ingress.SUBMIT_SCHEMA_V2,
        "request_ref": request_ref,
        "observed_grounding": dict(grounding),
        "request": dict(semantic_request),
    }


def _build_v2_status_frame(*, request_ref: str) -> dict[str, Any]:
    return {"schema": ceo_ingress.STATUS_SCHEMA_V2, "request_ref": request_ref}


def _finalize_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Step 5 — a receipt claiming ``dispatched`` true/missing/non-bool is a
    backend contract defect, never presented as success (mirrors
    ``executive_ceo_ingress._finalize_receipt`` — this module holds no
    independent copy of that rule; it is re-asserted here because this
    receipt arrived over the wire, not from an in-process call the ingress
    module already guards)."""

    if receipt.get("dispatched") is not False:
        raise AdmissionError(
            "backend_refused", "Executive CEO ingress backend refused the request"
        )
    return dict(receipt)


async def compose_admission(request: AdmissionRequest) -> AdmissionOutcome:
    """Run the full ADMISSION path once.  Never retries internally."""

    if not principal_authorizes_submit(request.principal):
        raise AdmissionError(
            "authority_refused", "the requested execution authority was refused"
        )

    # Step 1: existing public five-tool shape.  Still carries operation_key —
    # that is the caller's logical operation identity, consumed ONLY for
    # request_ref derivation (step 2) and NEVER forwarded inside the v2
    # semantic request (AD-ID1 automated requests carry no operation_key).
    validated = _validate_five_tool_shape(request.payload)
    operation_key = validated["operation_key"]
    semantic_request = {k: v for k, v in validated.items() if k != "operation_key"}

    # Step 2: one stable req-* outer identity through the canonical owner.
    try:
        request_ref = ceo_request.app_request_ref(operation_key)
    except ceo_request.CeoRequestError as exc:
        raise AdmissionError("internal_error", "Executive CEO ingress failed") from exc

    # Step 3: fresh trusted grounding, immediately before effect.
    try:
        grounding = observe_trusted_grounding(
            mastermind_root=request.mastermind_root,
            macro_root_flag=request.macro_root_flag,
            environ=request.environ,
        )
    except GroundingUnavailable as exc:
        raise AdmissionError("grounding_unavailable", "trusted grounding is unavailable") from exc

    # Step 4: exact CeoIngress v2 submit frame, ONE bounded request, dedicated
    # ingress socket only.
    frame = _build_v2_frame(
        request_ref=request_ref, grounding=grounding, semantic_request=semantic_request
    )
    response = await request.client.send_frame(request.ceo_ingress_socket_path, frame)
    return _classify_send_response(response, request_ref=request_ref)


def _classify_send_response(
    response: CeoIngressResponse, *, request_ref: str
) -> AdmissionOutcome:
    if response.transport != TRANSPORT_SENT_OK:
        if response.transport == TRANSPORT_SENT_UNKNOWN:
            # Step 6: possible commit, response lost. Never resubmit here.
            return AdmissionOutcome(
                status=STATUS_EFFECT_UNKNOWN,
                request_ref=request_ref,
                code="effect_unknown",
                message="the dedicated CEO ingress response was lost after the "
                "frame was sent; reconcile by request_ref before taking any "
                "further action",
            )
        # Never connected / refused locally before any bytes were sent: zero
        # effect, safe.
        return AdmissionOutcome(
            status=STATUS_TRANSPORT_UNAVAILABLE,
            request_ref=request_ref,
            code="ingress_unavailable",
            message="Executive CEO ingress is not currently reachable",
        )

    if response.ok is False:
        error = response.error or {}
        code = str(error.get("code") or "backend_refused")
        status = STATUS_CONFLICT if code == "operation_conflict" else STATUS_REFUSED
        return AdmissionOutcome(
            status=status,
            request_ref=request_ref,
            code=code,
            message=str(error.get("message") or "the request was refused"),
        )

    receipt = _finalize_receipt(response.result or {})
    return AdmissionOutcome(status=STATUS_ACCEPTED, request_ref=request_ref, receipt=receipt)


async def reconcile_by_request_ref(
    client: CeoIngressClient, *, socket_path: "Path | str", request_ref: str
) -> AdmissionOutcome:
    """Step 6/7 reconciliation — the ONLY legal follow-up to EFFECT_UNKNOWN.

    Sends exactly one v2 STATUS frame keyed by the SAME ``request_ref`` —
    never a new submit, never a different transport. A caller may call this
    repeatedly (status reads are naturally idempotent); it is
    :func:`compose_admission` that must never be called twice for one
    logical operation without this reconciliation step in between.
    """

    frame = _build_v2_status_frame(request_ref=request_ref)
    response = await client.send_frame(socket_path, frame)
    return _classify_send_response(response, request_ref=request_ref)
