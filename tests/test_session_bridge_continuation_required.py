from __future__ import annotations

import dataclasses
import pytest

from control_plane.sol_action_target import (
    ActionTargetReason,
    ActionTargetState,
    SolActionTargetResolution,
)
from integrations.session_bridge.continuation_required import (
    ContinuationProjectionError,
    TrustedTurnDisposition,
    project_continuation_requirement,
)


def _target(**overrides):
    value = dict(
        schema="mastermind.sol_action_target.v1",
        state=ActionTargetState.RESOLVED,
        reason=ActionTargetReason.EXACT_RUNTIME_BINDING,
        root_job_id="JOB-001",
        target_seat="ceo",
        session_alias="EXECUTIVE-CEO-A",
        binding_id="bind-current-0001",
        binding_generation=7,
        reasoning_surface="chatgpt-sol",
        action_authoritative=True,
        observer_only=False,
        evidence_digest="a" * 64,
    )
    value.update(overrides)
    return SolActionTargetResolution(**value)


def _state(**overrides):
    value = dict(
        operation_key="op-current-001",
        carrier_ref="carrier:root:001",
        target_ref="chatgpt:target:001",
        target_generation="EXECUTIVE-CEO-A:bind-current-0001:7:chatgpt-sol",
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


def _project(state=None, target=None):
    return project_continuation_requirement(
        state or _state(), action_target=target or _target()
    )


def test_incomplete_healthy_exact_authoritative_session_requires_continuation():
    result = _project()
    assert result.required is True
    assert result.reason == "continuation_required"
    assert result.target_ref == "chatgpt:target:001"
    assert result.action_target_evidence_digest == "a" * 64


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
def test_turn_boundaries_never_require_continuation(changes, reason):
    result = _project(_state(**changes))
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
    result = _project(_state(finalization_disposition=disposition))
    assert result.required is False
    assert result.reason == "lawful_stop_disposition"


def test_model_prose_cannot_affect_projection():
    fields = {field.name for field in dataclasses.fields(TrustedTurnDisposition)}
    assert fields.isdisjoint({"text", "next_step", "assistant_text", "model_claim"})


def test_missing_or_unknown_disposition_evidence_is_not_positive_absence():
    assert _project(_state(disposition_evidence_complete=False)).required is False
    with pytest.raises(ContinuationProjectionError):
        _state(finalization_disposition="MORE_WORK_EXISTS")


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        (_target(state=ActionTargetState.UNKNOWN,
                 reason=ActionTargetReason.BINDING_EVIDENCE_UNKNOWN,
                 action_authoritative=False), "action_target_unresolved"),
        (_target(action_authoritative=False, observer_only=True,
                 reason=ActionTargetReason.ACTOR_OBSERVER_ONLY),
         "actor_not_action_authoritative"),
        (_target(binding_id=None), "action_target_incomplete"),
    ],
)
def test_canonical_action_target_must_be_exact_and_authoritative(target, reason):
    result = _project(target=target)
    assert result.required is False
    assert result.reason == reason


def test_runtime_binding_generation_drift_holds():
    result = _project(_state(
        target_generation="EXECUTIVE-CEO-A:bind-current-0001:8:chatgpt-sol"
    ))
    assert result.required is False
    assert result.reason == "action_target_generation_mismatch"


def test_surface_or_binding_identity_drift_holds():
    for target in (
        _target(binding_id="bind-current-0002"),
        _target(reasoning_surface="codex"),
        _target(session_alias="EXECUTIVE-CEO-B"),
    ):
        assert _project(target=target).required is False


def test_projection_has_no_send_retry_wake_or_provider_surface():
    result = _project()
    for forbidden in ("send", "retry", "wake", "dispatch", "provider"):
        assert not hasattr(result, forbidden)


def test_raw_dict_cannot_impersonate_action_target():
    with pytest.raises(ContinuationProjectionError):
        project_continuation_requirement(_state(), action_target={})  # type: ignore[arg-type]
