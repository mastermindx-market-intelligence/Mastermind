"""NM-06 (T3_HANDOFF_V2 §6): gateway DISCONNECTED vs STOPPED — distinct labels.

A stopped-gateway error code classifies as its own ``gateway_stopped`` state,
distinct from ``gateway_busy`` and ``viewer_disconnected``, is never
effect-unknown (a stopped gateway is a stopped gateway, even with a pending
pointer), and offers only read/status continuations: the gateway must be
started by its owner — never auto-restarted, reconnected or remade from here.
"""
from __future__ import annotations

from integrations.session_bridge import hermes_native_continuity as continuity

PENDING = {"operation_key": "session-continue-" + "a" * 64,
           "session_id": "original-session", "request_id": "b" * 32}


def test_stopped_code_classifies_gateway_stopped_with_reason():
    stopped = continuity.classify_error_code("NATIVE_GATEWAY_STOPPED")
    assert stopped["state"] == continuity.GATEWAY_STOPPED
    assert stopped["reason"] == "gateway_not_running"
    # The alias code in the closed table maps to the same typed state.
    alias = continuity.classify_error_code("NATIVE_GATEWAY_NOT_RUNNING")
    assert alias["state"] == continuity.GATEWAY_STOPPED
    assert alias["reason"] == "gateway_not_running"
    assert continuity.GATEWAY_STOPPED == "gateway_stopped"
    assert continuity.GATEWAY_STOPPED in continuity.STATES


def test_stopped_busy_and_viewer_codes_yield_three_distinct_states():
    stopped = continuity.classify_error_code("NATIVE_GATEWAY_STOPPED")["state"]
    busy = continuity.classify_error_code("NATIVE_SESSION_BUSY")["state"]
    disconnected = continuity.classify_error_code("NATIVE_CLIENT_UNAVAILABLE")["state"]
    assert {stopped, busy, disconnected} == {
        continuity.GATEWAY_STOPPED, continuity.GATEWAY_BUSY,
        continuity.VIEWER_DISCONNECTED,
    }


def test_stopped_permits_only_read_status_idempotent_operations():
    stopped = continuity.classify_error_code("NATIVE_GATEWAY_STOPPED")
    continuations = continuity.permitted_continuations(stopped)
    assert continuations, "a stopped gateway still offers observation"
    for row in continuations:
        assert row["operation"] in {"read", "status"}
        assert row["operation"] not in {"send", "restart", "reconnect", "recover"}
        assert row["idempotent"] is True
    assert continuity.fresh_send_allowed(stopped) is False


def test_stopped_code_beats_the_pending_fallback_never_effect_unknown():
    # A pending pointer must not turn a stopped gateway into effect-unknown:
    # there is nothing in flight to reconcile while the gateway is down.
    stopped = continuity.classify_error_code("NATIVE_GATEWAY_STOPPED", pending=PENDING)
    assert stopped["state"] == continuity.GATEWAY_STOPPED
    assert stopped["reason"] == "gateway_not_running"
    assert "pending" not in stopped
    assert stopped["state"] != continuity.EFFECT_UNKNOWN


def test_existing_code_table_rows_are_unchanged():
    # Regression pins: the NM-06 fix adds a state without reclassifying any
    # previously-mapped code.
    pins = {
        "NATIVE_SESSION_BUSY": continuity.GATEWAY_BUSY,
        "NATIVE_PROMPT_PENDING": continuity.GATEWAY_BUSY,
        "NATIVE_CLIENT_INTERRUPTED": continuity.VIEWER_DISCONNECTED,
        "NATIVE_PIPE_UNAVAILABLE": continuity.VIEWER_DISCONNECTED,
        "AUTHENTICATION_CHANGED": continuity.AUTH_CHANGED,
        "SOMETHING_ELSE": continuity.UNCLASSIFIED,
    }
    for code, expected in pins.items():
        assert continuity.classify_error_code(code)["state"] == expected, code
    # Unknown codes with a pending pointer stay effect-unknown (unchanged).
    unknown = continuity.classify_error_code("SOMETHING_ELSE", pending=PENDING)
    assert unknown["state"] == continuity.EFFECT_UNKNOWN
