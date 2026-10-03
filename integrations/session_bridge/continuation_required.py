"""Trusted, effect-free projection for anti-premature-finalization continuation.

This module owns no lifecycle state, target registry, scheduler, retry policy, wake
transport, dialogue write, or action authority. It composes a host-owned turn
disposition with the existing canonical Sol action-target resolution. Model prose
is never authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from control_plane.sol_action_target import (
    ActionTargetState,
    SolActionTargetResolution,
)

_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_STOP_DISPOSITIONS = frozenset({
    "PROVEN_OUTCOME",
    "EXACT_HUMAN_GATE",
    "EFFECT_UNKNOWN",
    "ALL_SCOPED_LANES_BLOCKED",
    "DURABLE_EXECUTION_RUNNING",
    "CHECKPOINTED_CONTINUATION",
})


class ContinuationProjectionError(ValueError):
    """Static validation failure; never include model/provider text."""


def _ref(value: object, field: str) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise ContinuationProjectionError(f"invalid_{field}")
    return value


@dataclass(frozen=True)
class TrustedTurnDisposition:
    """Current host-owned turn facts; not an authority token or lifecycle record."""

    operation_key: str
    carrier_ref: str
    target_ref: str
    target_generation: str
    mission_revision: str
    authorization_ref: str
    mission_complete: bool
    disposition_evidence_complete: bool
    finalization_disposition: str | None
    user_stop: bool
    denial_active: bool
    unresolved_modifying_effect: bool
    target_addressable: bool
    authorization_current: bool
    exact_next_action_ref: str | None
    prior_continue_effect_unresolved: bool = False

    def __post_init__(self) -> None:
        for field in (
            "operation_key", "carrier_ref", "target_ref", "target_generation",
            "mission_revision", "authorization_ref",
        ):
            _ref(getattr(self, field), field)
        for field in (
            "mission_complete", "disposition_evidence_complete", "user_stop",
            "denial_active", "unresolved_modifying_effect", "target_addressable",
            "authorization_current", "prior_continue_effect_unresolved",
        ):
            if type(getattr(self, field)) is not bool:
                raise ContinuationProjectionError(f"invalid_{field}")
        if self.finalization_disposition is not None:
            if self.finalization_disposition not in _STOP_DISPOSITIONS:
                raise ContinuationProjectionError("invalid_finalization_disposition")
        if self.exact_next_action_ref is not None:
            _ref(self.exact_next_action_ref, "exact_next_action_ref")


@dataclass(frozen=True)
class ContinuationRequirement:
    required: bool
    reason: str
    operation_key: str
    carrier_ref: str
    target_ref: str
    target_generation: str
    exact_next_action_ref: str | None
    action_target_evidence_digest: str | None = None


def _held(state: TrustedTurnDisposition, reason: str) -> ContinuationRequirement:
    return ContinuationRequirement(
        required=False,
        reason=reason,
        operation_key=state.operation_key,
        carrier_ref=state.carrier_ref,
        target_ref=state.target_ref,
        target_generation=state.target_generation,
        exact_next_action_ref=state.exact_next_action_ref,
    )


def _project_turn_facts(
    state: TrustedTurnDisposition,
) -> ContinuationRequirement:
    """Evaluate only turn/finalization facts; never infer action authority."""
    if state.mission_complete:
        return _held(state, "mission_complete")
    if state.user_stop:
        return _held(state, "user_stop")
    if state.denial_active:
        return _held(state, "denial_active")
    if state.unresolved_modifying_effect:
        return _held(state, "effect_unknown")
    if state.prior_continue_effect_unresolved:
        return _held(state, "continue_effect_unresolved")
    if not state.disposition_evidence_complete:
        return _held(state, "disposition_evidence_incomplete")
    if state.finalization_disposition is not None:
        return _held(state, "lawful_stop_disposition")
    if not state.target_addressable:
        return _held(state, "target_not_addressable")
    if not state.authorization_current:
        return _held(state, "authorization_stale")
    if state.exact_next_action_ref is None:
        return _held(state, "next_action_missing")
    return ContinuationRequirement(
        required=True,
        reason="turn_continuation_candidate",
        operation_key=state.operation_key,
        carrier_ref=state.carrier_ref,
        target_ref=state.target_ref,
        target_generation=state.target_generation,
        exact_next_action_ref=state.exact_next_action_ref,
    )


def project_continuation_requirement(
    state: TrustedTurnDisposition,
    *,
    action_target: SolActionTargetResolution,
) -> ContinuationRequirement:
    """Project eligibility for one existing canonical CONTINUE, without sending it.

    A positive result requires both the trusted turn facts and a fresh resolution
    from the existing sol_action_target owner proving the current actor is the
    exact action-authoritative CEO binding. The resolution remains evidence, not a
    reusable authorization token; an effect owner must re-resolve at action time.
    """
    if not isinstance(state, TrustedTurnDisposition):
        raise ContinuationProjectionError("invalid_trusted_turn_disposition")
    if not isinstance(action_target, SolActionTargetResolution):
        raise ContinuationProjectionError("invalid_action_target_resolution")

    turn = _project_turn_facts(state)
    if not turn.required:
        return turn

    if action_target.state is not ActionTargetState.RESOLVED:
        return _held(state, "action_target_unresolved")
    if action_target.action_authoritative is not True:
        return _held(state, "actor_not_action_authoritative")
    if (
        action_target.session_alias is None
        or action_target.binding_id is None
        or action_target.binding_generation is None
        or action_target.reasoning_surface is None
    ):
        return _held(state, "action_target_incomplete")

    expected_generation = (
        f"{action_target.session_alias}:"
        f"{action_target.binding_id}:"
        f"{action_target.binding_generation}:"
        f"{action_target.reasoning_surface}"
    )
    if state.target_generation != expected_generation:
        return _held(state, "action_target_generation_mismatch")

    return ContinuationRequirement(
        required=True,
        reason="continuation_required",
        operation_key=state.operation_key,
        carrier_ref=state.carrier_ref,
        target_ref=state.target_ref,
        target_generation=state.target_generation,
        exact_next_action_ref=state.exact_next_action_ref,
        action_target_evidence_digest=action_target.evidence_digest,
    )


__all__ = [
    "ContinuationProjectionError",
    "ContinuationRequirement",
    "TrustedTurnDisposition",
    "project_continuation_requirement",
]
