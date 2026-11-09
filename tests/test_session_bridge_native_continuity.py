"""Continuity classification tests — the five distinguished states and the
idempotent-recovery rule (no fixture bots, no live gateway)."""
import pytest

from integrations.session_bridge.hermes_native_continuity import (
    AUTH_CHANGED,
    EFFECT_UNKNOWN,
    GATEWAY_BUSY,
    IDLE,
    MODEL_LIMITED,
    NATIVE_TERMINAL,
    TURN_RUNNING,
    UNCLASSIFIED,
    VIEWER_DISCONNECTED,
    classify_error_code,
    classify_native_continuity,
    fresh_send_allowed,
    interventions,
    permitted_continuations,
)

PENDING = {"operation_key": "session-continue-" + "a" * 64,
           "session_id": "original-session", "request_id": "b" * 32}
ADMISSION = {"admission_id": "admission-1", "session_id": "original-session"}


class TestErrorCodes:
    def test_busy_pending_and_viewer_codes_stay_distinct(self):
        assert classify_error_code("NATIVE_SESSION_BUSY")["state"] == GATEWAY_BUSY
        assert classify_error_code("NATIVE_SESSION_BUSY")["reason"] == "session_busy"
        assert classify_error_code("NATIVE_PROMPT_PENDING")["reason"] == "prompt_pending"
        assert classify_error_code("NATIVE_BUSY")["reason"] == "port_busy"
        assert classify_error_code("NATIVE_CLIENT_INTERRUPTED")["state"] == VIEWER_DISCONNECTED
        assert classify_error_code("NATIVE_CLIENT_UNAVAILABLE")["reason"] == "client_unavailable"
        assert classify_error_code("AUTHENTICATION_CHANGED")["state"] == AUTH_CHANGED

    def test_unknown_error_with_a_pending_mutation_is_effect_unknown(self):
        state = classify_error_code("SOMETHING_ELSE", pending=PENDING)
        assert state["state"] == EFFECT_UNKNOWN
        assert state["pending"] == PENDING

    def test_unknown_error_without_pending_stays_unclassified(self):
        assert classify_error_code("SOMETHING_ELSE")["state"] == UNCLASSIFIED
        assert classify_error_code(None)["state"] == UNCLASSIFIED
        assert classify_error_code(42)["state"] == UNCLASSIFIED


class TestNativeResults:
    def test_terminal_receipt_is_native_terminal(self):
        state = classify_native_continuity("OBSERVED", admission={
            **ADMISSION, "status": "terminal", "outcome": "completed"})
        assert state == {"state": NATIVE_TERMINAL, "session_id": "original-session",
                         "admission_id": "admission-1", "outcome": "completed"}

    def test_model_quota_and_rate_limit_are_model_limited_never_retryable(self):
        for reason in ("provider_rate_limit", "provider_quota_limit"):
            state = classify_native_continuity("OBSERVED", admission={
                **ADMISSION, "status": "terminal", "outcome": "failed"},
                failure_reason=reason)
            assert state["state"] == MODEL_LIMITED
            assert state["failure_reason"] == reason
            assert state["retry_policy"] == "never_auto"
            continuations = permitted_continuations(state)
            assert [c["operation"] for c in continuations] == ["read"]
            assert all(c["idempotent"] for c in continuations)

    def test_other_failed_reasons_stay_native_terminal_with_reason(self):
        state = classify_native_continuity("OBSERVED", admission={
            **ADMISSION, "status": "terminal", "outcome": "failed"},
            failure_reason="provider_auth_or_access")
        assert state["state"] == NATIVE_TERMINAL
        assert state["failure_reason"] == "provider_auth_or_access"

    def test_running_admission_is_turn_running(self):
        for status in ("queued", "started", "unknown"):
            state = classify_native_continuity("ADMITTED", admission={
                **ADMISSION, "status": status})
            assert state["state"] == TURN_RUNNING
            assert state["admission_status"] == status

    def test_not_submitted_and_unavailable_are_viewer_disconnected(self):
        assert classify_native_continuity("NOT_SUBMITTED")["reason"] == "host_interrupted"
        assert classify_native_continuity("UNAVAILABLE")["reason"] == "client_unavailable"

    def test_refused_without_a_busy_code_is_unclassified_not_idle(self):
        assert classify_native_continuity("REFUSED")["state"] == UNCLASSIFIED

    def test_effect_unknown_requires_the_original_pointer(self):
        state = classify_native_continuity("EFFECT_UNKNOWN", pending=PENDING)
        assert state["state"] == EFFECT_UNKNOWN
        assert state["pending"]["request_id"] == PENDING["request_id"]
        assert classify_native_continuity("EFFECT_UNKNOWN")["state"] == UNCLASSIFIED

    def test_missing_admission_is_never_guessed(self):
        assert classify_native_continuity("ADMITTED")["state"] == UNCLASSIFIED
        assert classify_native_continuity("OBSERVED", admission={"status": "weird"})["state"] == UNCLASSIFIED
        assert classify_native_continuity(None)["state"] == UNCLASSIFIED

    def test_quiet_session_snapshot_is_idle_and_busy_snapshot_is_not(self):
        quiet = classify_native_continuity(None, session={
            "session_id": "original-session", "running": False,
            "pending": [], "prompts_pending": False})
        assert quiet == {"state": IDLE, "session_id": "original-session"}
        running = classify_native_continuity(None, session={
            "session_id": "original-session", "running": True,
            "pending": [], "prompts_pending": False})
        assert running["state"] == TURN_RUNNING
        queued = classify_native_continuity(None, session={
            "session_id": "original-session", "running": False,
            "pending": [{"admission_id": "adm-9", "status": "started"}],
            "prompts_pending": False})
        assert queued["state"] == TURN_RUNNING
        assert queued["admission_id"] == "adm-9"
        prompts = classify_native_continuity(None, session={
            "session_id": "original-session", "running": False,
            "pending": [], "prompts_pending": True})
        assert prompts["state"] == GATEWAY_BUSY
        unobserved = classify_native_continuity(None, session={
            "session_id": "original-session"})
        assert unobserved["state"] == UNCLASSIFIED


class TestPermittedContinuations:
    def test_effect_unknown_recovers_only_by_the_original_operation_key(self):
        state = classify_native_continuity("EFFECT_UNKNOWN", pending=PENDING)
        continuations = permitted_continuations(state)
        assert len(continuations) == 1
        recovery = continuations[0]
        assert recovery["operation"] == "recover"
        assert recovery["operation_key"] == PENDING["operation_key"]
        assert recovery["session_id"] == PENDING["session_id"]
        assert recovery["idempotent"] is True

    def test_only_idle_permits_a_fresh_send(self):
        idle = {"state": IDLE, "session_id": "original-session"}
        assert fresh_send_allowed(idle) is True
        send = [c for c in permitted_continuations(idle) if c["operation"] == "send"]
        assert send and send[0]["fresh_request_id_required"] is True
        for state in ({"state": EFFECT_UNKNOWN, "pending": PENDING},
                      {"state": MODEL_LIMITED},
                      {"state": GATEWAY_BUSY},
                      {"state": VIEWER_DISCONNECTED},
                      {"state": TURN_RUNNING},
                      {"state": NATIVE_TERMINAL},
                      {"state": AUTH_CHANGED},
                      {"state": UNCLASSIFIED, "code": "X"}):
            assert fresh_send_allowed(state) is False
            assert all(c["operation"] != "send" for c in permitted_continuations(state))

    def test_auth_changed_and_unclassified_have_no_continuation(self):
        assert permitted_continuations({"state": AUTH_CHANGED}) == []
        assert permitted_continuations({"state": UNCLASSIFIED, "code": "X"}) == []
        assert permitted_continuations({"state": EFFECT_UNKNOWN}) == []


def test_stop_and_steer_are_not_exposed():
    assert interventions() == {"stop": "not_exposed_by_native_port",
                               "steer": "not_exposed_by_native_port"}
