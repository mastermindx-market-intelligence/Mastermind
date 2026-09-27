"""Pure ownership-boundary decision for one already-admitted delegation candidate.

This module does not select a model, provider, account, worker, host, queue, or
retry policy. It decides only whether work may remain a provider-native helper
inside the current Attempt, must re-enter the existing Executive child-Job
lifecycle, or crosses a boundary that requires a human authority decision.
"""
from __future__ import annotations

import dataclasses
from enum import Enum

from control_plane.operator_harness_contract import (
    NativeHelperPolicy,
    ObservedTriState,
    native_helpers_allowed,
)


class DelegationDisposition(str, Enum):
    NATIVE_HELPER = "NATIVE_HELPER"
    EXECUTIVE_CHILD_JOB = "EXECUTIVE_CHILD_JOB"
    HUMAN_GATE = "HUMAN_GATE"


@dataclasses.dataclass(frozen=True)
class DelegationFacts:
    """Closed facts about the ownership/effect boundary of proposed child work."""

    write_capable: bool
    native_helper_policy: NativeHelperPolicy
    supports_subagent_capability_ceiling: ObservedTriState
    same_attempt_subordinate: bool = True
    capability_subset_of_parent: bool = True
    requires_independent_company_responsibility: bool = False
    requires_independent_review: bool = False
    requires_durable_continuation: bool = False
    requires_distinct_worker_or_placement: bool = False
    requires_separate_effect_custody: bool = False
    authority_expansion: bool = False
    credential_or_admin_change: bool = False
    capital_destructive_or_public_effect: bool = False
    budget_or_risk_expansion: bool = False
    effect_unknown: bool = False
    custody_conflict: bool = False
    explicitly_reserved_for_human: bool = False


@dataclasses.dataclass(frozen=True)
class DelegationDecision:
    disposition: DelegationDisposition
    reasons: tuple[str, ...]

    @property
    def human_intervention_required(self) -> bool:
        return self.disposition is DelegationDisposition.HUMAN_GATE


def decide_delegation_boundary(facts: DelegationFacts) -> DelegationDecision:
    """Choose an ownership boundary without creating a second routing plane.

    Missing or unsupported native-helper capability never escalates to a human
    by itself. It falls back to the existing Executive child-Job path.
    """

    if not isinstance(facts, DelegationFacts):
        raise TypeError("facts must be DelegationFacts")

    human_reasons = tuple(
        name
        for name, active in (
            ("authority_expansion", facts.authority_expansion),
            ("credential_or_admin_change", facts.credential_or_admin_change),
            (
                "capital_destructive_or_public_effect",
                facts.capital_destructive_or_public_effect,
            ),
            ("budget_or_risk_expansion", facts.budget_or_risk_expansion),
            ("effect_unknown", facts.effect_unknown),
            ("custody_conflict", facts.custody_conflict),
            ("explicitly_reserved_for_human", facts.explicitly_reserved_for_human),
        )
        if active
    )
    if human_reasons:
        return DelegationDecision(
            DelegationDisposition.HUMAN_GATE,
            human_reasons,
        )

    durable_reasons = tuple(
        name
        for name, active in (
            (
                "independent_company_responsibility",
                facts.requires_independent_company_responsibility,
            ),
            ("independent_review", facts.requires_independent_review),
            ("durable_continuation", facts.requires_durable_continuation),
            (
                "distinct_worker_or_placement",
                facts.requires_distinct_worker_or_placement,
            ),
            ("separate_effect_custody", facts.requires_separate_effect_custody),
        )
        if active
    )
    if durable_reasons:
        return DelegationDecision(
            DelegationDisposition.EXECUTIVE_CHILD_JOB,
            durable_reasons,
        )

    helper_reasons: list[str] = []
    if not facts.same_attempt_subordinate:
        helper_reasons.append("not_same_attempt_subordinate")
    if not facts.capability_subset_of_parent:
        helper_reasons.append("capability_not_subset_of_parent")
    if not native_helpers_allowed(
        write_capable=facts.write_capable,
        native_helper_policy=facts.native_helper_policy,
        supports_subagent_capability_ceiling=(
            facts.supports_subagent_capability_ceiling
        ),
    ):
        helper_reasons.append("native_helper_not_admitted")

    if not helper_reasons:
        return DelegationDecision(
            DelegationDisposition.NATIVE_HELPER,
            ("same_attempt_shrink_only_helper",),
        )

    return DelegationDecision(
        DelegationDisposition.EXECUTIVE_CHILD_JOB,
        tuple(helper_reasons),
    )


__all__ = [
    "DelegationDecision",
    "DelegationDisposition",
    "DelegationFacts",
    "decide_delegation_boundary",
]
