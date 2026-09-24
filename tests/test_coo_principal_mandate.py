from __future__ import annotations

import dataclasses

import pytest

from control_plane.coo_principal_mandate import (
    RESERVED_BOUNDARIES,
    DecisionPosture,
    EffectState,
    MissionAuthorityFact,
    NewEffectGate,
    PrincipalFact,
    ReleaseClass,
    SafetyFact,
    Seat,
    SessionAssurance,
    project_coo_principal_mandate,
)


D0 = "0" * 64
D1 = "1" * 64
D2 = "2" * 64
D3 = "3" * 64
D4 = "4" * 64


def principal() -> PrincipalFact:
    return PrincipalFact(
        policy_id="mastermind-executive-coo",
        issuer_digest=D0,
        subject_digest=D1,
        client_ref=D2,
        resource_ref="https://mcp.mastermind-x.com/mcp",
        scopes=(
            "mastermind.executive.coo.act",
            "mastermind.executive.read",
        ),
        principal_binding_digest=D3,
    )


def mission(
    *,
    accountable_seat: Seat = Seat.COO,
    owed_seat: Seat = Seat.COO,
    release_class: ReleaseClass = ReleaseClass.AUTONOMOUS_SOURCE_RELEASE_WITH_GATES,
) -> MissionAuthorityFact:
    return MissionAuthorityFact(
        work_ref="WS:EXECUTIVE-CAPACITY-FABRIC",
        mission_authority_ref="authority:coo-principal-v1",
        authority_generation_digest=D4,
        accountable_seat=accountable_seat,
        owed_seat=owed_seat,
        release_class=release_class,
        outcome_ref="outcome:fable-executive-integration",
        proof_contract_ref="proof:coo-end-to-end-v1",
        capability_profile_ref="capability:claude-rich-principal-v1",
        source_grant_ref="source:mission-branch-v1",
        economic_envelope_ref="economics:mission-budget-v1",
    )


def safety(
    *,
    effect_state: EffectState = EffectState.NONE,
    conflict: bool = False,
    assurance: SessionAssurance = SessionAssurance.MISSION_BOUND,
) -> SafetyFact:
    return SafetyFact(
        effect_state=effect_state,
        live_source_or_lease_conflict=conflict,
        runtime_binding_ref="binding:coo-current",
        session_assurance=assurance,
    )


def test_coo_owed_turn_defaults_to_decide_and_continue():
    result = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(owed_seat=Seat.COO),
        safety=safety(),
    )
    assert result["schema"] == "mastermind.coo_principal_mandate.v1"
    assert result["seat"] == "coo"
    assert result["decision_posture"] == DecisionPosture.DECIDE_CONTINUE.value
    assert result["new_effect_gate"] == NewEffectGate.OPEN.value
    assert result["reason_codes"] == []
    assert result["reserved_boundaries"] == list(RESERVED_BOUNDARIES)


@pytest.mark.parametrize("owed", [Seat.CEO, Seat.CHAIRMAN])
def test_higher_seat_owed_turn_preserves_path_disjoint_coo_autonomy(owed: Seat):
    result = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(owed_seat=owed),
        safety=safety(),
    )
    assert result["decision_posture"] == DecisionPosture.CONTINUE_PATH_DISJOINT.value
    assert result["new_effect_gate"] == NewEffectGate.OPEN.value
    assert result["reason_codes"] == [f"{owed.value}_turn_reserved"]


def test_worker_owed_turn_does_not_turn_fable_into_worker_micromanager():
    result = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(owed_seat=Seat.WORKER),
        safety=safety(),
    )
    assert result["decision_posture"] == DecisionPosture.DO_NOT_MICROMANAGE_WORKER.value
    assert result["new_effect_gate"] == NewEffectGate.OPEN.value


def test_effect_unknown_fences_new_effects_and_requires_reconciliation():
    result = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(),
        safety=safety(effect_state=EffectState.EFFECT_UNKNOWN),
    )
    assert result["decision_posture"] == DecisionPosture.RECONCILE_REQUIRED.value
    assert result["new_effect_gate"] == NewEffectGate.FENCED_EFFECT_UNKNOWN.value
    assert result["reason_codes"] == ["effect_unknown", "new_effects_fenced"]


def test_live_source_or_lease_conflict_fences_new_effects():
    result = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(),
        safety=safety(conflict=True),
    )
    assert result["decision_posture"] == DecisionPosture.RECONCILE_REQUIRED.value
    assert result["new_effect_gate"] == NewEffectGate.FENCED_SOURCE_OR_LEASE_CONFLICT.value
    assert result["reason_codes"] == [
        "live_source_or_lease_conflict",
        "new_effects_fenced",
    ]


def test_non_coo_accountability_cannot_be_promoted_by_projection():
    result = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(accountable_seat=Seat.CEO, owed_seat=Seat.COO),
        safety=safety(),
    )
    assert result["decision_posture"] == DecisionPosture.RECOMMEND_ONLY_FOR_OWED_TURN.value
    assert result["new_effect_gate"] == NewEffectGate.OPEN.value
    assert result["reason_codes"] == ["coo_not_accountable_seat"]


def test_release_class_is_projected_but_not_interpreted_as_gate_completion():
    result = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(release_class=ReleaseClass.RESERVED_RELEASE),
        safety=safety(),
    )
    assert result["release"] == {"release_class": "RESERVED_RELEASE"}
    assert "merge_allowed" not in result["release"]
    assert "deploy_allowed" not in result["release"]


def test_session_assurance_is_explicit_and_defaults_to_mission_bound():
    result = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(),
        safety=SafetyFact(
            effect_state=EffectState.NONE,
            live_source_or_lease_conflict=False,
        ),
    )
    assert result["continuity"]["session_assurance"] == "COO_PRINCIPAL_MISSION_BOUND"

    stronger = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(),
        safety=safety(assurance=SessionAssurance.PROVIDER_SESSION_BOUND),
    )
    assert (
        stronger["continuity"]["session_assurance"]
        == "COO_PRINCIPAL_PROVIDER_SESSION_BOUND"
    )


def test_projection_is_deterministic_and_contains_no_mutating_callable_or_store():
    left = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(),
        safety=safety(),
    )
    right = project_coo_principal_mandate(
        principal=principal(),
        mission=mission(),
        safety=safety(),
    )
    assert left == right
    assert "submit" not in left
    assert "queue" not in left
    assert "token" not in left


@pytest.mark.parametrize(
    ("factory", "replacement"),
    [
        (principal, {"issuer_digest": "bad"}),
        (principal, {"scopes": ("mastermind.executive.read", "mastermind.executive.read")}),
        (mission, {"work_ref": "not-a-workstream"}),
        (mission, {"authority_generation_digest": "bad"}),
    ],
)
def test_closed_fact_construction_refuses_malformed_identity(factory, replacement):
    value = factory()
    with pytest.raises((TypeError, ValueError)):
        dataclasses.replace(value, **replacement)


def test_scope_order_is_canonical():
    with pytest.raises(ValueError, match="scopes must be sorted"):
        PrincipalFact(
            policy_id="mastermind-executive-coo",
            issuer_digest=D0,
            subject_digest=D1,
            client_ref=D2,
            resource_ref="https://mcp.mastermind-x.com/mcp",
            scopes=(
                "mastermind.executive.read",
                "mastermind.executive.coo.act",
            ),
            principal_binding_digest=D3,
        )
