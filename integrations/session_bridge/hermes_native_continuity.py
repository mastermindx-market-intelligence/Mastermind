"""Typed continuity classification for native Hermes conversation results.

Session-bridge-side mirror of the #2180 native-path continuity contract
(``app/mastermind_os/src/hermes-native/continuity.ts``).  It separates WHY a
bot conversation is not progressing — viewer disconnected, gateway busy,
gateway stopped, model 429/quota, native terminal, effect-unknown — instead of
collapsing them into a single native error, and it names the exact permitted
continuation.

Binding rules (T3_HANDOFF_V2 §6 failure matrix):

* an effect-unknown mutation is never re-sent.  The only permitted mutation
  continuation is a recovery of the ORIGINAL operation key; a fresh send is
  legal only from ``IDLE`` and always mints a new request id;
* reopen/recovery attaches to the SAME native session — it never creates one;
* stop/steer are not exposed by the native producer (the gateway owns
  ``prompt.cancel``/``prompt.steer_queued``/``session.interrupt``; the native
  port wires none of them), so no state offers an intervention;
* unknown stays unknown: unrecognised inputs classify as ``UNCLASSIFIED``
  carrying the observed code, never as idle/healthy.

This module is pure and owns no transport, store or retry loop.
"""
from __future__ import annotations

import re

NATIVE_STATUSES = frozenset({
    "OBSERVED", "ADMITTED", "NOT_SUBMITTED", "REFUSED", "EFFECT_UNKNOWN", "UNAVAILABLE",
})
ADMISSION_STATES = frozenset({"queued", "started", "unknown", "terminal"})

# Mirror of the Hermes tools.bot_failure_reasons closed vocabulary.
FAILURE_REASONS = frozenset({
    "runtime_offline", "queued_expired", "delivery_timeout", "agent_blocked", "cancelled",
    "provider_auth_or_access", "provider_quota_limit", "provider_rate_limit",
    "provider_server_error", "context_overflow", "missing_config", "model_unavailable",
    "target_scope_unresolved", "unknown",
})
MODEL_LIMITED_REASONS = frozenset({"provider_rate_limit", "provider_quota_limit"})

IDLE = "idle"
TURN_RUNNING = "turn_running"
NATIVE_TERMINAL = "native_terminal"
MODEL_LIMITED = "model_limited"
GATEWAY_BUSY = "gateway_busy"
GATEWAY_STOPPED = "gateway_stopped"
VIEWER_DISCONNECTED = "viewer_disconnected"
AUTH_CHANGED = "auth_changed"
EFFECT_UNKNOWN = "effect_unknown"
UNCLASSIFIED = "unclassified"
STATES = frozenset({
    IDLE, TURN_RUNNING, NATIVE_TERMINAL, MODEL_LIMITED, GATEWAY_BUSY,
    GATEWAY_STOPPED, VIEWER_DISCONNECTED, AUTH_CHANGED, EFFECT_UNKNOWN,
    UNCLASSIFIED,
})

_BUSY_CODES = {"NATIVE_SESSION_BUSY": "session_busy",
               "NATIVE_PROMPT_PENDING": "prompt_pending",
               "NATIVE_BUSY": "port_busy"}
_STOPPED_CODES = {"NATIVE_GATEWAY_STOPPED": "gateway_not_running",
                  "NATIVE_GATEWAY_NOT_RUNNING": "gateway_not_running"}
_VIEWER_CODES = {"NATIVE_CLIENT_INTERRUPTED": "host_interrupted",
                 "NATIVE_CLIENT_UNAVAILABLE": "client_unavailable",
                 "NATIVE_PIPE_UNAVAILABLE": "client_unavailable",
                 "NATIVE_PLATFORM_UNAVAILABLE": "platform_unavailable"}
_AUTH_CODES = frozenset({"AUTHENTICATION_CHANGED", "NATIVE_AUTH_NOT_DISPATCHED"})
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}")


def _state(value, *, session_id=None, admission_id=None, **extra):
    row = {"state": value}
    if session_id is not None:
        row["session_id"] = session_id
    if admission_id is not None:
        row["admission_id"] = admission_id
    row.update(extra)
    return row


def classify_error_code(code, *, pending=None):
    """A thrown/observed error code → typed continuity (closed mapping)."""
    if type(code) is not str or _CODE_PATTERN.fullmatch(code) is None:
        return _state(UNCLASSIFIED, code=str(code)[:80])
    if code in _BUSY_CODES:
        return _state(GATEWAY_BUSY, reason=_BUSY_CODES[code])
    if code in _VIEWER_CODES:
        return _state(VIEWER_DISCONNECTED, reason=_VIEWER_CODES[code])
    if code in _STOPPED_CODES:
        return _state(GATEWAY_STOPPED, reason=_STOPPED_CODES[code])
    if code in _AUTH_CODES:
        return _state(AUTH_CHANGED)
    if pending is not None:
        return _state(EFFECT_UNKNOWN, pending=dict(pending))
    return _state(UNCLASSIFIED, code=code)


def classify_native_continuity(native_status, *, admission=None, failure_reason=None,
                               error_code=None, pending=None, session=None):
    """Classify one observed native result into the continuity vocabulary.

    ``admission``: the public admission projection (``status``/``outcome``).
    ``failure_reason``: the producer's closed classification of a terminal
    failed result (never guessed here).  ``pending``: the durable original
    operation pointer (``operation_key`` + session/request identity).
    ``session``: an observed session snapshot (``running``, ``pending``,
    ``prompts_pending``); with no result observed, a quiet snapshot is IDLE.
    """
    if error_code is not None:
        return classify_error_code(error_code, pending=pending)
    if pending is not None and (native_status is None or native_status not in NATIVE_STATUSES):
        return _state(EFFECT_UNKNOWN, pending=dict(pending))
    if native_status == "EFFECT_UNKNOWN":
        if pending:
            return _state(EFFECT_UNKNOWN, pending=dict(pending))
        return _state(UNCLASSIFIED, code="EFFECT_UNKNOWN_WITHOUT_POINTER")
    if native_status in {"NOT_SUBMITTED", "UNAVAILABLE"}:
        return _state(VIEWER_DISCONNECTED,
                      reason="host_interrupted" if native_status == "NOT_SUBMITTED"
                      else "client_unavailable")
    if native_status == "REFUSED":
        return _state(UNCLASSIFIED, code="NATIVE_REFUSED")
    if native_status in {"ADMITTED", "OBSERVED"}:
        if type(admission) is not dict or admission.get("status") not in ADMISSION_STATES:
            return _state(UNCLASSIFIED, code="ADMISSION_UNOBSERVED")
        session_id = admission.get("session_id")
        if admission["status"] == "terminal":
            if admission.get("outcome") == "failed" and failure_reason in MODEL_LIMITED_REASONS:
                return _state(MODEL_LIMITED, session_id=session_id,
                              admission_id=admission.get("admission_id"),
                              failure_reason=failure_reason, retry_policy="never_auto")
            row = {"failure_reason": failure_reason} if failure_reason in FAILURE_REASONS else {}
            return _state(NATIVE_TERMINAL, session_id=session_id,
                          admission_id=admission.get("admission_id"),
                          outcome=admission.get("outcome"), **row)
        return _state(TURN_RUNNING, session_id=session_id,
                      admission_id=admission.get("admission_id"),
                      admission_status=admission["status"])
    if native_status is None:
        if type(session) is dict:
            session_id = session.get("session_id")
            queued = session.get("pending") or []
            if queued:
                last = queued[-1] if type(queued[-1]) is dict else {}
                return _state(TURN_RUNNING, session_id=session_id,
                              admission_id=last.get("admission_id"),
                              admission_status=last.get("status"))
            if session.get("running") is True:
                return _state(TURN_RUNNING, session_id=session_id,
                              admission_id=None, admission_status="started")
            if session.get("prompts_pending") is True:
                return _state(GATEWAY_BUSY, session_id=session_id,
                              reason="prompt_pending")
            if session.get("running") is False:
                return _state(IDLE, session_id=session_id)
        return _state(UNCLASSIFIED, code="NO_OBSERVATION")
    return _state(UNCLASSIFIED, code=str(native_status))


def permitted_continuations(state):
    """Exact permitted next operations for a classified state.

    Only ``IDLE`` permits a fresh send (new request id).  ``EFFECT_UNKNOWN``
    permits exactly the recovery of the original operation key.
    """
    if state["state"] == EFFECT_UNKNOWN:
        pending = state.get("pending")
        if pending:
            return [{"operation": "recover", "operation_key": pending.get("operation_key"),
                     "session_id": pending.get("session_id"),
                     "idempotent": True,
                     "why": "recover the original request by its operation key"}]
        return []
    if state["state"] == MODEL_LIMITED:
        return [{"operation": "read", "session_id": state.get("session_id"),
                 "idempotent": True,
                 "why": "quota/rate limit: wait for reset; never auto-retry or switch account"}]
    if state["state"] == GATEWAY_BUSY:
        row = {"operation": "read", "idempotent": True,
               "why": "gateway owns the turn; re-read when it clears"}
        if state.get("session_id"):
            row["session_id"] = state["session_id"]
        else:
            row = {"operation": "status", "idempotent": True,
                   "why": "port busy; re-observe before any mutation"}
        return [row]
    if state["state"] == GATEWAY_STOPPED:
        return [{"operation": "status", "idempotent": True,
                 "why": "gateway stopped; its owner starts it — automatic "
                        "gateway recovery is not offered here"}]
    if state["state"] == VIEWER_DISCONNECTED:
        if state.get("session_id"):
            return [{"operation": "read", "session_id": state["session_id"],
                     "idempotent": True,
                     "why": "only the viewer attachment was lost; same native session"}]
        return [{"operation": "status", "idempotent": True, "why": "re-observe the runtime"}]
    if state["state"] in {NATIVE_TERMINAL, TURN_RUNNING}:
        return [{"operation": "read", "session_id": state.get("session_id"),
                 "idempotent": True,
                 "why": "same session; no stop or steer is exposed by the native port"}]
    if state["state"] == IDLE:
        return [{"operation": "read", "session_id": state.get("session_id"),
                 "idempotent": True,
                 "why": "idle; a fresh send mints a new request id"},
                {"operation": "send", "session_id": state.get("session_id"),
                 "idempotent": False, "fresh_request_id_required": True,
                 "why": "idle is the only state where a fresh send is legal"}]
    return []


def fresh_send_allowed(state):
    return state.get("state") == IDLE


def interventions():
    """Stop/steer honesty: the gateway has the verbs, the native port wires none."""
    return {"stop": "not_exposed_by_native_port", "steer": "not_exposed_by_native_port"}
