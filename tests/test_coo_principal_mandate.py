from __future__ import annotations

import copy
import dataclasses

import pytest

from control_plane import mission_workspace as mw
from control_plane.coo_principal_mandate import (
    RESERVED_BOUNDARIES,
    AuthorityFact,
    DecisionPosture,
    NewEffectGate,
    PrincipalFact,
    ReleaseClass,
    SessionAssurance,
    project_coo_principal_mandate,
)


D0 = "0" * 64
D1 = "1" * 64
D2 = "2" * 64
D3 = "3" * 64
D4 = "4" * 64
D5 = "5" * 64
D6 = "6" * 64
D7 = "7" * 64


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


def authority(
    *,
    work_ref: str = "WS:EXECUTIVE-CAPACITY-FABRIC",
    release_class: ReleaseClass = ReleaseClass.AUTONOMOUS_SOURCE_RELEASE_WITH_GATES,
    source_conflict: bool = False,
) -> AuthorityFact:
    return AuthorityFact(
        work_ref=work_ref,
        mission_authority_ref="authority:coo-principal-v1",
        authority_generation_digest=D4,
        outcome_ref="outcome:fable-executive-integration",
        proof_contract_ref="proof:coo-end-to-end-v1",
        release_class=release_class,
        capability_profile_digest=D5,
        source_grant_digest=D6,
        economic_envelope_digest=D7,
        live_source_or_lease_conflict=source_conflict,
    )


def _closed(keys, **values):
    result = {key: None for key in keys}
    result.update(values)
    return result


def mission_doc(
    *,
    work_ref: str = "WS:EXECUTIVE-CAPACITY-FABRIC",
    read_state: str = "CURRENT",
    owner_state: str = "SAME",
    source_generation_state: str = "CURRENT",
    root_state: str = "RESOLVED",
    root_ambiguous: bool = False,
    accountable_seat: str = "coo",
    owed_seat: str = "coo",
    posture: str = "RUNNING",
    posture_rule: str = "G1",
    dispatch_state: str = "STARTED",
):
    source_generation = {
        "state": source_generation_state,
        "version": 1,
        "generation": 1,
    }
    owner_observation = _closed(
        mw.OWNER_OBSERVATION_KEYS,
        schema=mw.OWNER_OBSERVATION_SCHEMA,
        state=owner_state,
        selection={},
        control_room={},
        runtime={},
    )
    source = _closed(
        mw.SOURCE_KEYS_V2,
        control_room_schema=mw.CONTROL_ROOM_SCHEMA,
        control_room_generated_at="2026-09-24T08:00:00Z",
        fabric_view_schema=mw.FABRIC_VIEW_SCHEMA_V2,
        fabric_view_generated_at="2026-09-24T08:00:00Z",
        source_generation=source_generation,
        source_coverage=["control_room", "fabric_view"],
        owner_observation=owner_observation,
    )
    read = _closed(
        mw.READ_STATE_KEYS,
        state=read_state,
        reason_codes=[] if read_state == "CURRENT" else ["SOURCE_OR_VALIDITY_INCOMPLETE"],
        usable_sections=["program", "mission", "principal", "transport"],
    )
    program = _closed(
        mw.PROGRAM_KEYS,
        work_ref=work_ref,
        title="Executive Capacity Fabric",
        state="ACTIVE",
        next_action="Continue the accepted mission.",
        github_prs=[],
        attention_ids=[],
        disagreements=[],
        evidence=[],
    )
    mission = _closed(
        mw.MISSION_KEYS,
        root_job_id="JOB-100",
        root_job_candidates=["JOB-100"],
        root_job_ambiguous=root_ambiguous,
        runtime_root_state=root_state,
        status="RUNNING",
        orchestration_role="aggregation",
        plan_step_id=None,
        depth=0,
        title=None,
        armed={},
        submission_availability="UNKNOWN",
        capability={},
        evidence=[],
    )
    owed_turn = _closed(
        mw.OWED_TURN_KEYS,
        seat=owed_seat,
        reason="current mission owner owes the next turn",
        source_refs=[],
    )
    principal_view = _closed(
        mw.PRINCIPAL_KEYS,
        accountable_seat=accountable_seat,
        current_worker=None,
        current_sol_target=None,
        owed_turn=owed_turn,
        evidence=[],
    )
    transport = _closed(
        mw.TRANSPORT_KEYS,
        dispatch_state=dispatch_state,
        reason=None,
        actionable=True,
        historical=False,
        watch_proven=True,
        carrier=None,
        w3c=None,
        evidence=[],
    )
    posture_view = _closed(
        mw.POSTURE_KEYS,
        value=posture,
        rule=posture_rule,
        evidence=[],
    )

    document = {key: {} for key in mw.OUTPUT_KEYS_V3}
    document.update(
        {
            "schema": mw.SCHEMA_V3,
            "generated_at": "2026-09-24T08:00:00Z",
            "source": source,
            "read_state": read,
            "program": program,
            "mission": mission,
            "principal": principal_view,
            "transport": transport,
            "posture": posture_view,
            "result_refs": {},
        }
    )
    return document


def test_current_coo_mission_defaults_to_decide_continue():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(owed_seat="coo"),
    )
    assert result["schema"] == "mastermind.coo_principal_mandate.v1"
    assert result["seat"] == "coo"
    assert result["decision_posture"] == DecisionPosture.DECIDE_CONTINUE.value
    assert result["new_effect_gate"] == NewEffectGate.OPEN.value
    assert result["mission"]["read_state"] == "CURRENT"
    assert result["mission"]["owner_observation_state"] == "SAME"
    assert result["mission"]["work_ref"] == "WS:EXECUTIVE-CAPACITY-FABRIC"
    assert result["reserved_boundaries"] == list(RESERVED_BOUNDARIES)
    assert result["reason_codes"] == []


@pytest.mark.parametrize("owed", ["ceo", "chairman"])
def test_higher_seat_owed_turn_preserves_path_disjoint_work(owed):
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(owed_seat=owed),
    )
    assert result["decision_posture"] == DecisionPosture.CONTINUE_PATH_DISJOINT.value
    assert result["new_effect_gate"] == NewEffectGate.OPEN.value
    assert result["reason_codes"] == [f"{owed}_turn_reserved"]


def test_worker_owed_turn_does_not_make_fable_micromanage_worker():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(owed_seat="worker"),
    )
    assert result["decision_posture"] == DecisionPosture.DO_NOT_MICROMANAGE_WORKER.value
    assert result["new_effect_gate"] == NewEffectGate.OPEN.value


@pytest.mark.parametrize("state", ["PARTIAL", "HISTORICAL", "UNAVAILABLE"])
def test_noncurrent_mission_is_readable_but_not_modifying_authority(state):
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(read_state=state),
    )
    assert result["decision_posture"] == DecisionPosture.READ_RECOMMEND_ONLY.value
    assert result["new_effect_gate"] == NewEffectGate.FENCED_UNQUALIFIED_MISSION.value
    assert "mission_read_state_not_current" in result["reason_codes"]


def test_owner_observation_must_be_same_for_modifying_mandate():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(owner_state="UNKNOWN"),
    )
    assert result["new_effect_gate"] == NewEffectGate.FENCED_UNQUALIFIED_MISSION.value
    assert "owner_observation_not_same" in result["reason_codes"]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"root_state": "CONFLICT"}, "mission_root_conflict"),
        ({"root_ambiguous": True}, "mission_root_conflict"),
        ({"source_generation_state": "CONFLICT"}, "source_generation_not_current"),
        ({"source_generation_state": "STALE"}, "source_generation_not_current"),
        ({"source_generation_state": "UNKNOWN"}, "source_generation_not_current"),
    ],
)
def test_root_or_generation_conflict_refuses_modifying_mandate(changes, reason):
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(**changes),
    )
    assert result["new_effect_gate"] == NewEffectGate.FENCED_UNQUALIFIED_MISSION.value
    assert reason in result["reason_codes"]


def test_effect_unknown_fences_new_effects_and_requires_reconciliation():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(posture="EFFECT_UNKNOWN", dispatch_state="EFFECT_UNKNOWN"),
    )
    assert result["decision_posture"] == DecisionPosture.RECONCILE_REQUIRED.value
    assert result["new_effect_gate"] == NewEffectGate.FENCED_EFFECT_UNKNOWN.value
    assert "effect_unknown" in result["reason_codes"]


def test_runtime_binding_reconciliation_required_fences_new_effects():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(
            posture="RECONCILIATION_REQUIRED",
            dispatch_state="RUNTIME_BINDING_RECONCILIATION_REQUIRED",
        ),
    )
    assert result["decision_posture"] == DecisionPosture.RECONCILE_REQUIRED.value
    assert result["new_effect_gate"] == NewEffectGate.FENCED_RECONCILIATION_REQUIRED.value
    assert "reconciliation_required" in result["reason_codes"]


def test_source_or_lease_conflict_is_a_separate_owner_fence():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(source_conflict=True),
        mission_workspace=mission_doc(),
    )
    assert result["decision_posture"] == DecisionPosture.RECONCILE_REQUIRED.value
    assert result["new_effect_gate"] == NewEffectGate.FENCED_SOURCE_OR_LEASE_CONFLICT.value
    assert "live_source_or_lease_conflict" in result["reason_codes"]


def test_non_coo_accountability_cannot_be_promoted_by_projection():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(accountable_seat="ceo", owed_seat="coo"),
    )
    assert result["decision_posture"] == DecisionPosture.READ_RECOMMEND_ONLY.value
    assert result["new_effect_gate"] == NewEffectGate.FENCED_NOT_COO_ACCOUNTABLE.value


def test_work_ref_mismatch_is_refused_without_rewriting_either_owner():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(work_ref="WS:OTHER"),
        mission_workspace=mission_doc(),
    )
    assert result["new_effect_gate"] == NewEffectGate.FENCED_UNQUALIFIED_MISSION.value
    assert "mission_work_ref_mismatch" in result["reason_codes"]


def test_release_and_capability_evidence_are_projected_without_claiming_gate_completion():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(release_class=ReleaseClass.RESERVED_RELEASE),
        mission_workspace=mission_doc(),
    )
    assert result["release"] == {"release_class": "RESERVED_RELEASE"}
    assert result["capability"]["capability_profile_digest"] == D5
    assert result["capability"]["source_grant_digest"] == D6
    assert result["capability"]["economic_envelope_digest"] == D7
    assert "merge_allowed" not in result["release"]
    assert "deploy_allowed" not in result["release"]


def test_current_mission_does_not_fabricate_a_current_coo_runtime_binding():
    result = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(),
    )
    assert result["continuity"] == {
        "session_assurance": "COO_PRINCIPAL_MISSION_BOUND",
        "current_coo_target": None,
    }

    stronger = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(),
        session_assurance=SessionAssurance.PROVIDER_SESSION_BOUND,
    )
    assert stronger["continuity"]["session_assurance"] == "COO_PRINCIPAL_PROVIDER_SESSION_BOUND"
    assert stronger["continuity"]["current_coo_target"] is None


def test_mission_workspace_v3_shape_is_not_silently_downgraded_or_upgraded():
    document = mission_doc()
    document["schema"] = mw.SCHEMA_V2
    with pytest.raises(ValueError, match="mission_workspace must use"):
        project_coo_principal_mandate(
            principal=principal(),
            authority=authority(),
            mission_workspace=document,
        )

    document = mission_doc()
    document["unexpected"] = True
    with pytest.raises(ValueError, match="Mission Workspace v3 contract"):
        project_coo_principal_mandate(
            principal=principal(),
            authority=authority(),
            mission_workspace=document,
        )


def test_projection_is_deterministic_and_has_no_mutation_result_surface():
    left = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=mission_doc(),
    )
    right = project_coo_principal_mandate(
        principal=principal(),
        authority=authority(),
        mission_workspace=copy.deepcopy(mission_doc()),
    )
    assert left == right
    assert "submit" not in left
    assert "queue" not in left
    assert "dispatched" not in left


@pytest.mark.parametrize(
    ("factory", "replacement"),
    [
        (principal, {"issuer_digest": "bad"}),
        (principal, {"scopes": ("mastermind.executive.read", "mastermind.executive.read")}),
        (authority, {"work_ref": "not-a-workstream"}),
        (authority, {"authority_generation_digest": "bad"}),
        (authority, {"capability_profile_digest": "bad"}),
    ],
)
def test_owner_fact_construction_refuses_malformed_identity(factory, replacement):
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
