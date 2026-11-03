"""App research submission on the existing authenticated foreground owner.

The installed Session Bridge still owns the single strict-v2 admission and
finite COO continuation. This adapter owns no Job, scheduler, receipt store,
provider selection or retry. Its App response remains the original admission
receipt; current results are read from their existing Runtime owners.
"""
from __future__ import annotations

from collections.abc import Mapping

from control_plane.ceo_request import app_request_ref, automated_intent_id
from integrations.mastermind_executive_app.admission import (
    AdmissionError, AdmissionOutcome, STATUS_ACCEPTED, STATUS_CONFLICT,
    STATUS_EFFECT_UNKNOWN, STATUS_REFUSED, STATUS_TRANSPORT_UNAVAILABLE,
    _finalize_receipt, _validate_five_tool_shape, principal_authorizes_submit,
)
from integrations.session_bridge.http_foreground import bind_request
from integrations.session_bridge.installed import (
    InstalledSessionBridgeClient, TransportNotSent,
)
from integrations.session_bridge.schemas import BridgeError


async def compose_foreground_admission(request, principal, arguments, client, *, clock):
    """Drive once after the inner App has independently verified the bearer."""
    if type(client) is not InstalledSessionBridgeClient:
        raise AdmissionError("authority_refused", "installed ingress owner is unavailable")
    if not principal_authorizes_submit(principal):
        raise AdmissionError("authority_refused", "the requested execution authority was refused")
    validated = _validate_five_tool_shape(arguments)
    if validated.get("execution_profile") != "research_only":
        raise AdmissionError("authority_refused", "foreground research profile required")
    request_ref = app_request_ref(validated["operation_key"])

    def unknown():
        return AdmissionOutcome(
            status=STATUS_EFFECT_UNKNOWN, request_ref=request_ref,
            code="effect_unknown",
            message="reconcile the original Executive operation; do not resubmit",
        )

    try:
        with bind_request(request, principal, clock=clock) as source:
            receipt = await source.run(lambda: client.summon(principal, validated))
            source.require_live()
    except TransportNotSent:
        # The trusted transport proved the original frame was never sent, so
        # no Executive effect began. The incumbent ingress-unavailable admission
        # retains the original request pointer; every other failure stays
        # conservatively unknown.
        return AdmissionOutcome(
            status=STATUS_TRANSPORT_UNAVAILABLE, request_ref=request_ref,
            code="ingress_unavailable",
            message="Executive CEO ingress did not send the original request",
        )
    except BridgeError as exc:
        # The existing owner distinguishes these pre-commit refusals. All other
        # failures conservatively retain the original pointer as unknown.
        if exc.code in {"invalid_input", "authority_refused", "operation_conflict"}:
            return AdmissionOutcome(
                status=STATUS_CONFLICT if exc.code == "operation_conflict" else STATUS_REFUSED,
                request_ref=request_ref, code=exc.code, message=exc.message,
            )
        return unknown()
    except Exception:
        return unknown()
    if not isinstance(receipt, Mapping):
        return unknown()
    # Same-call execution is separate from immutable admission. Do not put a
    # result or a root-completion claim inside the App's admission receipt.
    admitted = {key: value for key, value in receipt.items() if key != "foreground_completion"}
    if (admitted.get("intent_id") != automated_intent_id(request_ref)
            or admitted.get("work_ref") != validated.get("workstream")):
        return unknown()
    try:
        admitted = _finalize_receipt(admitted)
    except AdmissionError:
        return unknown()
    return AdmissionOutcome(status=STATUS_ACCEPTED, request_ref=request_ref, receipt=admitted)
