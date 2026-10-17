from __future__ import annotations

import dataclasses
import pytest

from control_plane.session_targets import RuntimeBinding, load_session_targets
from control_plane.sol_action_target import (
    ActionTargetReason,
    ActionTargetState,
    RuntimeBindingSnapshot,
    SolActionTargetResolution,
    resolve_sol_action_target,
)
from control_plane.pro_continuation_requirement import (
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
        root_job_id="JOB-001",
        mission_revision="mission-rev-12",
        authorization_ref="auth-current-12",
        mission_complete=False,
        disposition_evidence_complete=True,
        finalization_disposition=None,
        user_stop=False,
        denial_active=False,
        unresolved_modifying_effect=False,
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
    assert result.root_job_id == "JOB-001"
    assert result.session_alias == "EXECUTIVE-CEO-A"
    assert result.binding_id == "bind-current-0001"
    assert result.binding_generation == 7
    assert result.reasoning_surface == "chatgpt-sol"
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
        ({"authorization_current": False}, "authorization_stale"),
        ({"exact_next_action_ref": None}, "next_action_missing"),
    ],
)
def test_turn_boundaries_never_require_continuation(changes, reason):
    result = _project(_state(**changes))
    assert result.required is False
    assert result.reason == reason


def test_unresolved_modifying_effect_outranks_optimistic_mission_complete():
    result = _project(
        _state(mission_complete=True, unresolved_modifying_effect=True)
    )
    assert result.required is False
    assert result.reason == "effect_unknown"


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


def test_platform_failure_is_a_blocker_reason_not_a_finalization_disposition():
    with pytest.raises(ContinuationProjectionError, match="invalid_finalization_disposition"):
        _state(finalization_disposition="PLATFORM_FAILURE")


def test_model_prose_and_target_selectors_cannot_affect_projection():
    fields = {field.name for field in dataclasses.fields(TrustedTurnDisposition)}
    assert fields.isdisjoint({
        "text",
        "next_step",
        "assistant_text",
        "model_claim",
        "target_ref",
        "target_generation",
        "session_alias",
        "binding_id",
        "binding_generation",
        "reasoning_surface",
    })


def test_missing_or_unknown_disposition_evidence_is_not_positive_absence():
    assert _project(_state(disposition_evidence_complete=False)).required is False
    with pytest.raises(ContinuationProjectionError):
        _state(finalization_disposition="MORE_WORK_EXISTS")


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        (
            _target(
                state=ActionTargetState.UNKNOWN,
                reason=ActionTargetReason.BINDING_EVIDENCE_UNKNOWN,
                action_authoritative=False,
            ),
            "action_target_unresolved",
        ),
        (
            _target(
                action_authoritative=False,
                observer_only=True,
                reason=ActionTargetReason.ACTOR_OBSERVER_ONLY,
            ),
            "actor_not_action_authoritative",
        ),
        (_target(binding_id=None), "action_target_incomplete"),
    ],
)
def test_canonical_action_target_must_be_exact_and_authoritative(target, reason):
    result = _project(target=target)
    assert result.required is False
    assert result.reason == reason


def test_valid_resolution_for_another_root_refuses():
    result = _project(target=_target(root_job_id="JOB-002"))
    assert result.required is False
    assert result.reason == "action_target_root_mismatch"


def test_real_action_target_resolution_cannot_be_replayed_across_root():
    registry = load_session_targets().with_root_job_bindings(
        {"JOB-001": {"ceo": "EXECUTIVE-CEO-A"}}
    )
    binding = RuntimeBinding(
        session_alias="EXECUTIVE-CEO-A",
        binding_id="bind-chatgpt-current-0001",
        binding_generation=4,
        native_handle="provider-thread-001",
        account_label="test-account",
        reasoning_surface="chatgpt-sol",
    )
    resolution = resolve_sol_action_target(
        root_job_id="JOB-001",
        registry=registry,
        binding_snapshot=RuntimeBindingSnapshot.current((binding,)),
        actor_binding=binding,
    )
    assert resolution.action_authoritative is True
    result = project_continuation_requirement(
        _state(root_job_id="JOB-002"),
        action_target=resolution,
    )
    assert result.required is False
    assert result.reason == "action_target_root_mismatch"


def test_operation_root_cannot_be_swapped_while_reusing_valid_target():
    result = _project(state=_state(root_job_id="JOB-002"))
    assert result.required is False
    assert result.reason == "action_target_root_mismatch"


def test_destination_is_derived_only_from_canonical_action_target():
    target = _target(
        session_alias="EXECUTIVE-CEO-B",
        binding_id="bind-current-0002",
        binding_generation=11,
        reasoning_surface="chatgpt-sol",
    )
    result = _project(target=target)
    assert result.required is True
    assert result.session_alias == "EXECUTIVE-CEO-B"
    assert result.binding_id == "bind-current-0002"
    assert result.binding_generation == 11
    assert result.reasoning_surface == "chatgpt-sol"


def test_malformed_root_refuses_before_projection():
    with pytest.raises(ContinuationProjectionError, match="invalid_root_job_id"):
        _state(root_job_id="not-a-job")


def test_projection_has_no_send_retry_wake_or_provider_surface():
    result = _project()
    for forbidden in ("send", "retry", "wake", "dispatch", "provider", "target_ref"):
        assert not hasattr(result, forbidden)


def test_raw_dict_cannot_impersonate_action_target():
    with pytest.raises(ContinuationProjectionError):
        project_continuation_requirement(_state(), action_target={})  # type: ignore[arg-type]
