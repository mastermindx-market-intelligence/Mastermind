"""Trusted, effect-free projection for anti-premature-finalization continuation.

This module owns no lifecycle state, target registry, scheduler, retry policy, wake
transport, or dialogue write. A trusted host may project whether the existing
exact-session CONTINUE owner is eligible to act. Model prose is never authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

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
    """Host-bound current state used only to decide whether CONTINUE is eligible."""

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


def project_continuation_requirement(
    state: TrustedTurnDisposition,
) -> ContinuationRequirement:
    """Project eligibility for one existing canonical CONTINUE, without sending it."""
    if not isinstance(state, TrustedTurnDisposition):
        raise ContinuationProjectionError("invalid_trusted_turn_disposition")

    reason = "continuation_required"
    required = True
    if state.mission_complete:
        required, reason = False, "mission_complete"
    elif state.user_stop:
        required, reason = False, "user_stop"
    elif state.denial_active:
        required, reason = False, "denial_active"
    elif state.unresolved_modifying_effect:
        required, reason = False, "effect_unknown"
    elif state.prior_continue_effect_unresolved:
        required, reason = False, "continue_effect_unresolved"
    elif not state.disposition_evidence_complete:
        required, reason = False, "disposition_evidence_incomplete"
    elif state.finalization_disposition is not None:
        required, reason = False, "lawful_stop_disposition"
    elif not state.target_addressable:
        required, reason = False, "target_not_addressable"
    elif not state.authorization_current:
        required, reason = False, "authorization_stale"
    elif state.exact_next_action_ref is None:
        required, reason = False, "next_action_missing"

    return ContinuationRequirement(
        required=required,
        reason=reason,
        operation_key=state.operation_key,
        carrier_ref=state.carrier_ref,
        target_ref=state.target_ref,
        target_generation=state.target_generation,
        exact_next_action_ref=state.exact_next_action_ref,
    )


__all__ = [
    "ContinuationProjectionError",
    "ContinuationRequirement",
    "TrustedTurnDisposition",
    "project_continuation_requirement",
]
