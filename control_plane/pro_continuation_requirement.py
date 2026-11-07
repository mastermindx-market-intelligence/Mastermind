"""Trusted, effect-free projection for anti-premature-finalization continuation.

This module owns no lifecycle state, target registry, scheduler, retry policy, wake
transport, dialogue write, or action authority. It composes host-owned turn facts
with the existing canonical Sol action-target resolution. Model prose is never
authority, and positive output never carries a caller-supplied target selector.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from control_plane.sol_action_target import (
    ActionTargetReason,
    ActionTargetState,
    SolActionTargetResolution,
)
from control_plane.wake_events import JOB_ID_RE

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
    """Current host-owned turn facts; not an authority token or lifecycle record.

    root_job_id must come from the authenticated operation/carrier context.
    The projection joins it to the canonical action-target resolution. There is
    intentionally no caller-supplied target reference or target generation.
    """

    operation_key: str
    carrier_ref: str
    root_job_id: str
    mission_revision: str
    authorization_ref: str
    mission_complete: bool
    disposition_evidence_complete: bool
    finalization_disposition: str | None
    user_stop: bool
    denial_active: bool
    unresolved_modifying_effect: bool
    authorization_current: bool
    exact_next_action_ref: str | None
    prior_continue_effect_unresolved: bool = False

    def __post_init__(self) -> None:
        for field in (
            "operation_key",
            "carrier_ref",
            "mission_revision",
            "authorization_ref",
        ):
            _ref(getattr(self, field), field)
        if not isinstance(self.root_job_id, str) or JOB_ID_RE.fullmatch(self.root_job_id) is None:
            raise ContinuationProjectionError("invalid_root_job_id")
        for field in (
            "mission_complete",
            "disposition_evidence_complete",
            "user_stop",
            "denial_active",
            "unresolved_modifying_effect",
            "authorization_current",
            "prior_continue_effect_unresolved",
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
    root_job_id: str
    exact_next_action_ref: str | None
    session_alias: str | None = None
    binding_id: str | None = None
    binding_generation: int | None = None
    reasoning_surface: str | None = None
    action_target_evidence_digest: str | None = None


def _held(state: TrustedTurnDisposition, reason: str) -> ContinuationRequirement:
    return ContinuationRequirement(
        required=False,
        reason=reason,
        operation_key=state.operation_key,
        carrier_ref=state.carrier_ref,
        root_job_id=state.root_job_id,
        exact_next_action_ref=state.exact_next_action_ref,
    )


def _project_turn_facts(
    state: TrustedTurnDisposition,
) -> ContinuationRequirement:
    """Evaluate only turn/finalization facts; never infer action authority."""
    if state.unresolved_modifying_effect:
        return _held(state, "effect_unknown")
    if state.prior_continue_effect_unresolved:
        return _held(state, "continue_effect_unresolved")
    if state.mission_complete:
        return _held(state, "mission_complete")
    if state.user_stop:
        return _held(state, "user_stop")
    if state.denial_active:
        return _held(state, "denial_active")
    if not state.disposition_evidence_complete:
        return _held(state, "disposition_evidence_incomplete")
    if state.finalization_disposition is not None:
        return _held(state, "lawful_stop_disposition")
    if not state.authorization_current:
        return _held(state, "authorization_stale")
    if state.exact_next_action_ref is None:
        return _held(state, "next_action_missing")
    return ContinuationRequirement(
        required=True,
        reason="turn_continuation_candidate",
        operation_key=state.operation_key,
        carrier_ref=state.carrier_ref,
        root_job_id=state.root_job_id,
        exact_next_action_ref=state.exact_next_action_ref,
    )


def project_continuation_requirement(
    state: TrustedTurnDisposition,
    *,
    action_target: SolActionTargetResolution,
) -> ContinuationRequirement:
    """Project eligibility for one existing canonical CONTINUE, without sending it.

    A positive result requires both trusted turn facts and a fresh resolution from
    the existing sol_action_target owner proving the current actor is the exact
    action-authoritative CEO binding for the same canonical root. The destination
    identity in the result is derived only from that canonical resolution.

    The resolution remains evidence, not a reusable authorization token. The
    existing effect owner must re-resolve current authority/binding before any
    continuation effect.
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
    if (
        action_target.reason is not ActionTargetReason.EXACT_RUNTIME_BINDING
        or action_target.action_authoritative is not True
        or action_target.observer_only is not False
        or action_target.target_seat != "ceo"
    ):
        return _held(state, "actor_not_action_authoritative")
    if action_target.root_job_id != state.root_job_id:
        return _held(state, "action_target_root_mismatch")
    if (
        action_target.session_alias is None
        or action_target.binding_id is None
        or action_target.binding_generation is None
        or action_target.reasoning_surface is None
    ):
        return _held(state, "action_target_incomplete")

    return ContinuationRequirement(
        required=True,
        reason="continuation_required",
        operation_key=state.operation_key,
        carrier_ref=state.carrier_ref,
        root_job_id=state.root_job_id,
        exact_next_action_ref=state.exact_next_action_ref,
        session_alias=action_target.session_alias,
        binding_id=action_target.binding_id,
        binding_generation=action_target.binding_generation,
        reasoning_surface=action_target.reasoning_surface,
        action_target_evidence_digest=action_target.evidence_digest,
    )


__all__ = [
    "ContinuationProjectionError",
    "ContinuationRequirement",
    "TrustedTurnDisposition",
    "project_continuation_requirement",
]
