from __future__ import annotations

import copy

import pytest

from integrations.chairman_surfaces import web_sol_rotation_classifier as classifier


FP = "a" * 64
OTHER_FP = "b" * 64


def probe(**overrides):
    value = {
        "schema": "mastermind.web_sol_surface_probe.v1",
        "target_present": True,
        "exact_conversation_loaded": True,
        "page_responsive": True,
        "document_ready_state": "complete",
        "visibility": "visible",
        "composer_available": True,
        "generation_state": "idle",
        "auth_required": False,
        "provider_error_present": False,
    }
    value.update(overrides)
    return value


def failure(index: int, **overrides):
    value = {
        "attempt_id": f"turn-attempt-{index}",
        "conversation_fingerprint": FP,
        "observed_at": f"2026-09-16T0{index}:00:00Z",
        "provider_error_present": True,
        "generation_state": "idle",
        "composer_available": True,
        "page_responsive": True,
    }
    value.update(overrides)
    return value


def classify(*, current=None, failures=(), **kwargs):
    return classifier.classify_session_health(
        current_probe=probe() if current is None else current,
        conversation_fingerprint=FP,
        consecutive_terminal_failures=failures,
        **kwargs,
    )


def test_healthy_idle_surface_remains_session_healthy():
    result = classify()
    assert result.state is classifier.SessionHealth.SESSION_HEALTHY
    assert result.reason is None
    assert result.distinct_terminal_failures == 0


def test_active_generation_is_healthy_even_without_composer():
    result = classify(current=probe(generation_state="active", composer_available=False))
    assert result.state is classifier.SessionHealth.SESSION_HEALTHY
    assert result.reason is None


def test_one_generic_provider_error_is_transient_not_context_exhaustion():
    result = classify(
        current=probe(provider_error_present=True),
        failures=[failure(1)],
    )
    assert result.state is classifier.SessionHealth.PROVIDER_TRANSIENT
    assert result.reason is classifier.RotationReason.UNKNOWN
    assert result.distinct_terminal_failures == 1


def test_two_distinct_failed_turns_are_rotation_suspected():
    result = classify(
        current=probe(provider_error_present=True),
        failures=[failure(1), failure(2)],
    )
    assert result.state is classifier.SessionHealth.ROTATION_SUSPECTED
    assert result.reason is classifier.RotationReason.REPEATED_TERMINAL_GENERATION_FAILURE
    assert result.distinct_terminal_failures == 2


def test_three_corroborated_consecutive_failed_turns_require_rotation():
    result = classify(
        current=probe(provider_error_present=True),
        failures=[failure(1), failure(2), failure(3)],
    )
    assert result.state is classifier.SessionHealth.ROTATION_REQUIRED
    assert result.reason is classifier.RotationReason.REPEATED_TERMINAL_GENERATION_FAILURE
    assert result.distinct_terminal_failures == classifier.REPEATED_FAILURE_THRESHOLD


def test_duplicate_poll_of_same_failed_attempt_cannot_inflate_threshold():
    result = classify(
        current=probe(provider_error_present=True),
        failures=[
            failure(1),
            failure(2),
            failure(3, attempt_id="turn-attempt-2"),
        ],
    )
    assert result.state is classifier.SessionHealth.ROTATION_SUSPECTED
    assert result.distinct_terminal_failures == 2


def test_three_failures_without_responsive_composer_are_not_auto_rotation_required():
    result = classify(
        current=probe(provider_error_present=True),
        failures=[
            failure(1),
            failure(2),
            failure(3, composer_available=False),
        ],
    )
    assert result.state is classifier.SessionHealth.ROTATION_SUSPECTED
    assert result.reason is classifier.RotationReason.REPEATED_TERMINAL_GENERATION_FAILURE


def test_failure_evidence_from_another_conversation_is_refused():
    with pytest.raises(
        classifier.WebSolRotationClassifierError,
        match="crosses conversation identity",
    ):
        classify(
            current=probe(provider_error_present=True),
            failures=[failure(1), failure(2, conversation_fingerprint=OTHER_FP)],
        )


def test_failure_evidence_must_be_strictly_chronological():
    with pytest.raises(
        classifier.WebSolRotationClassifierError,
        match="strictly chronological",
    ):
        classify(
            current=probe(provider_error_present=True),
            failures=[failure(2), failure(1)],
        )


def test_raw_or_unknown_failure_fields_are_refused():
    row = failure(1)
    row["error_text"] = "Thinking failed"
    with pytest.raises(
        classifier.WebSolRotationClassifierError,
        match="invalid fields",
    ):
        classify(current=probe(provider_error_present=True), failures=[row])


def test_supported_context_limit_is_rotation_required_without_claiming_exhaustion():
    result = classify(supported_context_limit=True)
    assert result.state is classifier.SessionHealth.ROTATION_REQUIRED
    assert result.reason is classifier.RotationReason.CONTEXT_LIMIT_SUSPECTED


def test_manual_retirement_is_rotation_required():
    result = classify(manual_retirement=True)
    assert result.state is classifier.SessionHealth.ROTATION_REQUIRED
    assert result.reason is classifier.RotationReason.MANUAL_RETIREMENT


def test_auth_wall_has_priority_over_provider_error_history():
    result = classify(
        current=probe(auth_required=True, provider_error_present=True),
        failures=[failure(1), failure(2), failure(3)],
    )
    assert result.state is classifier.SessionHealth.AUTH_REQUIRED
    assert result.reason is None


def test_exhausted_surface_recovery_stays_surface_unusable_not_fake_context_limit():
    result = classify(
        current=probe(page_responsive=False, composer_available=None, generation_state="unknown"),
        surface_recovery_exhausted=True,
    )
    assert result.state is classifier.SessionHealth.SURFACE_UNUSABLE
    assert result.reason is classifier.RotationReason.SURFACE_UNUSABLE


def test_missing_exact_target_is_unknown_without_inventing_rotation():
    result = classify(
        current=probe(
            target_present=False,
            exact_conversation_loaded=False,
            composer_available=None,
            generation_state="unknown",
            auth_required=None,
            provider_error_present=None,
        )
    )
    assert result.state is classifier.SessionHealth.UNKNOWN
    assert result.reason is classifier.RotationReason.UNKNOWN


def test_classification_output_is_closed_and_contains_no_error_text():
    result = classify(
        current=probe(provider_error_present=True),
        failures=[failure(1), failure(2), failure(3)],
    )
    payload = result.to_dict()
    assert payload["schema"] == "mastermind.web_sol_rotation_classification/v1"
    assert payload["state"] == "ROTATION_REQUIRED"
    assert payload["reason"] == "REPEATED_TERMINAL_GENERATION_FAILURE"
    assert "error" not in payload
    assert "text" not in payload


def test_probe_validation_returns_detached_copy_for_classifier_consumers():
    from integrations.chairman_surfaces import web_sol_protocol as wsp

    original = probe()
    accepted = wsp.validate_probe(original)
    accepted["generation_state"] = "active"
    assert original["generation_state"] == "idle"


def test_classifier_does_not_mutate_caller_evidence():
    current = probe(provider_error_present=True)
    failures = [failure(1), failure(2), failure(3)]
    current_before = copy.deepcopy(current)
    failures_before = copy.deepcopy(failures)
    classify(current=current, failures=failures)
    assert current == current_before
    assert failures == failures_before
