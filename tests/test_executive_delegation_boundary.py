from __future__ import annotations

from control_plane.executive_delegation_boundary import (
    DelegationDisposition,
    DelegationFacts,
    decide_delegation_boundary,
)
from control_plane.operator_harness_contract import (
    NativeHelperPolicy,
    ObservedTriState,
)


def _facts(**overrides):
    values = {
        "write_capable": False,
        "native_helper_policy": NativeHelperPolicy.PARENT_READ_ONLY_CEILING,
        "supports_subagent_capability_ceiling": ObservedTriState.VERIFIED,
    }
    values.update(overrides)
    return DelegationFacts(**values)


def test_same_attempt_shrink_only_work_uses_native_helper():
    decision = decide_delegation_boundary(_facts())
    assert decision.disposition is DelegationDisposition.NATIVE_HELPER
    assert decision.reasons == ("same_attempt_shrink_only_helper",)
    assert decision.human_intervention_required is False


def test_independent_review_reenters_existing_executive_child_job():
    decision = decide_delegation_boundary(
        _facts(requires_independent_review=True)
    )
    assert decision.disposition is DelegationDisposition.EXECUTIVE_CHILD_JOB
    assert decision.reasons == ("independent_review",)
    assert decision.human_intervention_required is False


def test_durable_or_distinct_placement_never_becomes_provider_helper():
    decision = decide_delegation_boundary(
        _facts(
            requires_durable_continuation=True,
            requires_distinct_worker_or_placement=True,
        )
    )
    assert decision.disposition is DelegationDisposition.EXECUTIVE_CHILD_JOB
    assert decision.reasons == (
        "durable_continuation",
        "distinct_worker_or_placement",
    )


def test_missing_helper_ceiling_falls_back_to_executive_not_human():
    decision = decide_delegation_boundary(
        _facts(
            supports_subagent_capability_ceiling=ObservedTriState.UNKNOWN
        )
    )
    assert decision.disposition is DelegationDisposition.EXECUTIVE_CHILD_JOB
    assert decision.reasons == ("native_helper_not_admitted",)
    assert decision.human_intervention_required is False


def test_non_subordinate_or_widened_helper_falls_back_to_executive():
    decision = decide_delegation_boundary(
        _facts(
            same_attempt_subordinate=False,
            capability_subset_of_parent=False,
        )
    )
    assert decision.disposition is DelegationDisposition.EXECUTIVE_CHILD_JOB
    assert decision.reasons == (
        "not_same_attempt_subordinate",
        "capability_not_subset_of_parent",
    )


def test_reserved_authority_boundaries_are_human_gates():
    for field in (
        "authority_expansion",
        "credential_or_admin_change",
        "capital_destructive_or_public_effect",
        "budget_or_risk_expansion",
        "effect_unknown",
        "custody_conflict",
        "explicitly_reserved_for_human",
    ):
        decision = decide_delegation_boundary(_facts(**{field: True}))
        assert decision.disposition is DelegationDisposition.HUMAN_GATE
        assert decision.reasons == (field,)
        assert decision.human_intervention_required is True


def test_human_gate_precedes_otherwise_durable_child_work():
    decision = decide_delegation_boundary(
        _facts(
            requires_independent_review=True,
            effect_unknown=True,
        )
    )
    assert decision.disposition is DelegationDisposition.HUMAN_GATE
    assert decision.reasons == ("effect_unknown",)
