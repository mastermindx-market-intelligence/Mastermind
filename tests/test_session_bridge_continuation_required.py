from __future__ import annotations

import dataclasses
import pytest

from integrations.session_bridge.continuation_required import (
    ContinuationProjectionError,
    TrustedTurnDisposition,
    project_continuation_requirement,
)


def _state(**overrides):
    value = dict(
        operation_key="op-current-001",
        carrier_ref="carrier:root:001",
        target_ref="chatgpt:target:001",
        target_generation="gen-7",
        mission_revision="mission-rev-12",
        authorization_ref="auth-current-12",
        mission_complete=False,
        disposition_evidence_complete=True,
        finalization_disposition=None,
        user_stop=False,
        denial_active=False,
        unresolved_modifying_effect=False,
        target_addressable=True,
        authorization_current=True,
        exact_next_action_ref="action:source-read:next",
        prior_continue_effect_unresolved=False,
    )
    value.update(overrides)
    return TrustedTurnDisposition(**value)


def test_incomplete_healthy_exact_session_requires_continuation():
    result = project_continuation_requirement(_state())
    assert result.required is True
    assert result.reason == "continuation_required"
    assert result.target_ref == "chatgpt:target:001"
    assert result.target_generation == "gen-7"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"mission_complete": True}, "mission_complete"),
        ({"user_stop": True}, "user_stop"),
        ({"denial_active": True}, "denial_active"),
        ({"unresolved_modifying_effect": True}, "effect_unknown"),
        ({"prior_continue_effect_unresolved": True}, "continue_effect_unresolved"),
        ({"disposition_evidence_complete": False}, "disposition_evidence_incomplete"),
        ({"target_addressable": False}, "target_not_addressable"),
        ({"authorization_current": False}, "authorization_stale"),
        ({"exact_next_action_ref": None}, "next_action_missing"),
    ],
)
def test_fail_closed_boundaries_never_require_continuation(changes, reason):
    result = project_continuation_requirement(_state(**changes))
    assert result.required is False
    assert result.reason == reason


@pytest.mark.parametrize(
    "disposition",
    [
        "PROVEN_OUTCOME",
        "EXACT_HUMAN_GATE",
        "EFFECT_UNKNOWN",
        "ALL_SCOPED_LANES_BLOCKED",
        "DURABLE_EXECUTION_RUNNING",
        "CHECKPOINTED_CONTINUATION",
    ],
)
def test_every_lawful_stop_disposition_holds(disposition):
    result = project_continuation_requirement(
        _state(finalization_disposition=disposition)
    )
    assert result.required is False
    assert result.reason == "lawful_stop_disposition"


def test_identical_free_form_prose_cannot_affect_projection():
    # There is intentionally no text/next_step/model field in the trusted projection.
    fields = {field.name for field in dataclasses.fields(TrustedTurnDisposition)}
    assert fields.isdisjoint({"text", "next_step", "assistant_text", "model_claim"})


def test_missing_or_unknown_disposition_evidence_is_not_positive_absence():
    assert project_continuation_requirement(
        _state(disposition_evidence_complete=False)
    ).required is False
    with pytest.raises(ContinuationProjectionError):
        _state(finalization_disposition="MORE_WORK_EXISTS")


def test_projection_has_no_send_retry_wake_or_provider_surface():
    result = project_continuation_requirement(_state())
    for forbidden in ("send", "retry", "wake", "dispatch", "provider"):
        assert not hasattr(result, forbidden)
