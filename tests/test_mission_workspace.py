"""Contract tests for the pure, held mission-workspace reducer."""

from __future__ import annotations

import ast
import copy
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.fabric_job_view import (
    ATTEMPT_CARD_KEYS as OWNER_ATTEMPT_CARD_KEYS,
    JOB_CARD_KEYS as OWNER_JOB_CARD_KEYS,
    compose_fabric_view,
)
from control_plane.mission_workspace import (
    ACCEPTANCE_KEYS,
    ARM_OUTPUT_KEYS,
    ATTEMPT_KEYS,
    CAPABILITY_KEYS,
    CARRIER_KEYS,
    CHILD_ITEM_KEYS,
    CHILDREN_KEYS,
    COVERAGE_STATES,
    CONSUMED_JOB_CARD_KEYS,
    DISPATCH_STATES,
    EVIDENCE_FRESHNESS_STATES,
    EVIDENCE_KEYS,
    EVIDENCE_OWNERS,
    EXECUTION_KEYS,
    FABRIC_ATTEMPT_CARD_KEYS,
    MISSION_KEYS,
    OUTPUT_KEYS,
    POSTURE_KEYS,
    PR_KEYS,
    PRINCIPAL_KEYS,
    PROGRAM_KEYS,
    PROJECTED_DISPATCH_STATES,
    RUNTIME_CARD_KEYS,
    READ_STATES,
    READ_STATE_KEYS,
    REVIEW_KEYS,
    SCHEMA,
    SCHEMA_V2,
    SECTION_KEYS,
    SECTION_STATES,
    SOURCE_KEYS,
    SOURCE_GENERATION_KEYS,
    SOURCE_ROW_STATES,
    TRANSPORT_KEYS,
    W3C_KEYS,
    W3C_RECEIPT_KEYS,
    _posture,
    _posture_v2,
    _qualified_current,
    _safe_timestamp,
    compose_mission_workspace,
    compose_mission_workspace_v2,
)
from tests import test_chairman_control_room_server as control_room_server_tests


STAMP = "2026-09-20T00:00:00Z"
PROOF = "a" * 64


def _meta(proof: str = PROOF, *, budget: int = 1) -> dict:
    return {
        "schema": "mastermind.autonomy_validity.v1",
        "policy": "mapper-inclusive-48h-future-1h.v1",
        "qualified_at": STAMP,
        "proof_ref": proof,
        "sources": [],
        "valid_for_ms": budget,
        "reason": "source_budget",
    }


def _validity(proof: str = PROOF, *, remaining: int = 1) -> dict:
    components = {
        name: {
            "proof_ref": proof,
            "qualified_at": STAMP,
            "remaining_ms": remaining,
            "state": "current",
        }
        for name in ("card", "decision_current", "dispatch", "owed_open_age")
    }
    return {
        "schema": "mastermind.control_room_source_validity.v1",
        "profile": "b5.darwin-chrome-paired-v1",
        "browser_qualification": None,
        "publication_seq": 1,
        "cards": [
            {
                "responsibility_ref": "WS:ONE",
                "root_job_id": "JOB-1",
                "components": components,
            }
        ],
    }


def _inputs(
    *,
    candidates=("JOB-1",),
    dispatch_state="STARTED",
    historical=False,
    execution_state="IN_PROGRESS",
    unjoined_count=0,
    unjoined_ids=(),
) -> dict:
    metadata = {
        name: _meta()
        for name in ("card", "decision_current", "dispatch", "owed_open_age")
    }
    responsibility = {
        "responsibility_ref": "WS:ONE",
        "root_job_id": "JOB-1" if len(candidates) == 1 else None,
        "root_job_candidates": list(candidates),
        "root_job_ambiguous": len(candidates) > 1,
        "runtime_root_state": (
            "RESOLVED" if len(candidates) == 1 else "CONFLICT" if candidates else "UNKNOWN"
        ),
        "accountable_seat": "ceo",
        "current_worker": None,
        "current_sol_target": None,
        "owed_turn": {"seat": "ceo", "reason": "attention_targets_seat", "source_refs": []},
        "blocker": None,
        "declared_blocker": None,
        "disagreements": [],
        "validity": metadata,
        "dispatch": {
            "dispatch_state": dispatch_state,
            "reason": "fixture",
            "historical": historical,
            "actionable": dispatch_state == "RETURNED" and not historical,
            "watch_proven": True,
            "carrier": None,
            "w3c": None,
            "evidence": None,
        },
    }
    control_room = {
        "schema": "mastermind.chairman_control_room.v1",
        "generated_at": STAMP,
        "degraded": [],
        "work": [
            {
                "work_ref": "WS:ONE",
                "agent_os": {
                    "title": "One",
                    "state": "active",
                    "status": "active",
                    "next_action": "Read",
                },
                "github": {"prs": []},
                "attention_ids": [],
                "disagreements": [],
            }
        ],
        "autonomy": {"generated_at": STAMP, "responsibilities": [responsibility]},
    }
    fabric_view = {
        "schema": "mastermind.fabric_job_view.v1",
        "generated_at": STAMP,
        "runtime": {"root": "/private/never-project", "db_present": True, "identity": "x"},
        "armed": {"source": "absent"},
        "root": {
            "job_id": "JOB-1",
            "root_job_id": "JOB-1",
            "parent_job_id": None,
            "status": "RUNNING",
            "depth": 0,
            "orchestration_role": "plan",
            "plan_step_id": None,
            "result": {
                "state": execution_state,
                "summary": None,
                "artifacts": [],
                "errors": [],
                "next_actions": [],
            },
            "review": {"required": False, "reviews_job_id": None, "verdict": "NOT_YET"},
        },
        "children": [],
        "unjoined_job_count": unjoined_count,
        "unjoined_job_ids": list(unjoined_ids),
        "missingness": [],
        "degraded": [],
        "capability": {
            "state": "PROVEN",
            "installed": True,
            "version": None,
            "detail": "the requested root job was found",
        },
    }
    return {
        "control_room": control_room,
        "fabric_view": fabric_view,
        "work_ref": "WS:ONE",
        "root_job_id": "JOB-1",
        "source_validity": _validity(),
        "cache_currentness": {"state": "fresh", "publication_seq": 1},
        "source_generation": None,
    }


def _compose(**changes):
    inputs = _inputs()
    inputs.update(changes)
    return compose_mission_workspace(**inputs)


def _inputs_v2(*, execution_state="COMPLETED", dispatch_state="RETURNED") -> dict:
    """Frozen Fabric-v2 shape from immutable #819 semantic head 1ba7d2d2."""

    args = _inputs(execution_state=execution_state, dispatch_state=dispatch_state)
    fabric = args["fabric_view"]
    fabric["schema"] = "mastermind.fabric_job_view.v2"
    fabric["root"].update(
        {
            "status": "COMPLETED",
            "attempt_count": 1,
            "attempt_limit": 2,
            "current_attempt_id": None,
            "attempts": [],
            "latest_attempt": None,
            "repair": {"repair_round": None, "supersedes_job_id": None},
            "acceptance": {
                "state": "NOT_PROJECTED",
                "producer_owner": None,
                "reason": "product acceptance has no producer in this projection",
            },
        }
    )
    return args


def _compose_v2(**changes):
    args = _inputs_v2()
    args.update(changes)
    return compose_mission_workspace_v2(**args)


def test_closed_nested_shape_and_real_owner_vocabulary_are_exact():
    document = _compose()

    assert set(document) == OUTPUT_KEYS
    assert set(document["source"]) == SOURCE_KEYS
    assert set(document["source"]["source_generation"]) == SOURCE_GENERATION_KEYS
    assert set(document["read_state"]) == READ_STATE_KEYS
    assert set(document["program"]) == PROGRAM_KEYS
    assert set(document["mission"]) == MISSION_KEYS
    assert set(document["mission"]["armed"]) == ARM_OUTPUT_KEYS
    assert set(document["mission"]["capability"]) == CAPABILITY_KEYS
    assert set(document["principal"]) == PRINCIPAL_KEYS
    assert set(document["children"]) == CHILDREN_KEYS
    assert set(document["execution"]) == EXECUTION_KEYS
    assert set(document["review"]) == REVIEW_KEYS
    assert set(document["transport"]) == TRANSPORT_KEYS
    assert document["transport"]["carrier"] is None
    assert document["transport"]["w3c"] is None
    assert set(document["acceptance"]) == ACCEPTANCE_KEYS
    assert set(document["posture"]) == POSTURE_KEYS
    assert set(document["conversation"]) == SECTION_KEYS
    assert document["schema"] == SCHEMA
    assert document["read_state"]["state"] in READ_STATES
    assert document["children"]["state"] in SECTION_STATES
    assert document["children"]["coverage"] in COVERAGE_STATES
    assert document["read_state"]["state"] == "PARTIAL"
    assert document["posture"] == {
        "value": "HISTORICAL_OBSERVATION", "rule": "G1h", "evidence": [],
    }
    assert document["acceptance"]["state"] == "NOT_PROJECTED"
    assert document["mission"]["title"] is None
    assert document["mission"]["capability"]["detail"] == "the requested root job was found"
    assert not document["program"]["github_prs"]
    assert {"CONTINUED", "STOPPED"}.issubset(DISPATCH_STATES)
    assert {"CONTINUED", "STOPPED"}.isdisjoint(PROJECTED_DISPATCH_STATES)
    assert SOURCE_ROW_STATES == {
        "CURRENT", "PARTIAL", "HISTORICAL", "UNAVAILABLE", "CONFLICT",
        "NOT_PROJECTED", "NOT_APPLICABLE",
    }


def test_populated_nested_cards_have_only_the_frozen_keys_and_owner_enums():
    args = _inputs()
    responsibility = args["control_room"]["autonomy"]["responsibilities"][0]
    responsibility["current_worker"] = {
        "worker_id": "worker-1", "attempt_id": "ATTEMPT-1", "status": "RUNNING",
        "session_alias": "private-session-alias", "runtime_binding_id": "BINDING-1",
        "binding_generation": 3, "continuation_state": "ACKNOWLEDGED",
        "effect_state": "none", "capacity_state": "available",
        "previous_attempt_id": None, "movement_reason_code": None,
    }
    responsibility["dispatch"]["carrier"] = {
        "state": "RESOLVED", "reason": "C2_CURRENT_CAPACITY_COMMITMENT",
        "historical": False, "actionable": False,
    }
    responsibility["dispatch"]["w3c"] = {
        "state": "RESOLVED", "reason": "CANONICAL_TERMINAL_WAKE_RESOLVED",
        "terminal_state": "APPLIED", "wake_state": "TARGET_ACKNOWLEDGED",
        "terminal_applied": True,
        "source_receipt": {
            "observed_at": STAMP, "freshness": "SOURCE_EVIDENCE_TIME",
            "snapshot_digest": PROOF,
            "terminal_source_owner": "executive_terminal_return",
            "wake_source_owner": "wake_ledger",
        },
    }
    args["fabric_view"]["children"] = [
        {
            "job_id": "CHILD", "root_job_id": "JOB-1", "parent_job_id": "JOB-1",
            "status": "RUNNING", "depth": 1, "orchestration_role": "work",
            "plan_step_id": "STEP-1", "attempt_count": 1, "attempt_limit": 2,
            "current_attempt_id": "ATTEMPT-1", "latest_attempt": {
                "attempt_id": "ATTEMPT-1", "attempt_number": 1, "status": "RUNNING",
                "started_at": STAMP, "finished_at": None, "exit_code": None,
                "has_result": False, "error": None,
            },
        }
    ]
    args["control_room"]["work"][0]["github"]["prs"] = [
        {
            "repo": "org/repo", "number": 7,
            "url": "https://github.com/org/repo/pull/7", "title": "Bounded change",
            "branch": "claude/bounded", "draft": True, "merge_state": "BLOCKED",
        }
    ]

    document = compose_mission_workspace(**args)
    assert set(document["principal"]["current_worker"]) == RUNTIME_CARD_KEYS
    assert "session_alias" not in document["principal"]["current_worker"]
    assert set(document["children"]["items"][0]) == CHILD_ITEM_KEYS
    assert set(document["children"]["items"][0]["latest_attempt"]) == ATTEMPT_KEYS
    assert set(document["program"]["github_prs"][0]) == PR_KEYS
    assert set(document["transport"]["carrier"]) == CARRIER_KEYS
    assert set(document["transport"]["w3c"]) == W3C_KEYS
    assert set(document["transport"]["w3c"]["source_receipt"]) == W3C_RECEIPT_KEYS
    assert document["principal"]["current_worker"]["status"] == "RUNNING"
    assert document["transport"]["w3c"]["wake_state"] == "TARGET_ACKNOWLEDGED"


def test_real_producer_shapes_remain_partial_without_coherent_live_acquisition(
    tmp_path, monkeypatch,
):
    """Real composers prove shape compatibility, not an admitted G8 generation vector."""
    config, clock, _binding = control_room_server_tests._b5_navigation_fixture(tmp_path, monkeypatch)
    generation = control_room_server_tests.server_mod._reserve_composition(config)
    control_room_server_tests.server_mod._refresh_state_cache(
        config,
        timeout=240,
        generation=generation,
        include_capabilities=False,
    )
    clock[:] = control_room_server_tests._b5_sample(1001)
    envelope = control_room_server_tests.server_mod._cached_state_snapshot(config)

    root = SimpleNamespace(
        job_id="JOB-B5", status="RUNNING", parent_job_id=None, root_job_id="JOB-B5",
        depth=0, orchestration_role="plan", plan_step_id=None, attempt_count=1,
        attempt_limit=2, current_attempt_id="ATTEMPT-ROOT", result={}, review_required=False,
        reviews_job_id=None, repair_round=None, supersedes_job_id=None,
    )
    child = SimpleNamespace(
        job_id="JOB-CHILD", status="RUNNING", parent_job_id="JOB-B5", root_job_id="JOB-B5",
        depth=1, orchestration_role="work", plan_step_id="STEP-1", attempt_count=1,
        attempt_limit=2, current_attempt_id="ATTEMPT-1", result={}, review_required=False,
        reviews_job_id=None, repair_round=None, supersedes_job_id=None,
    )
    attempt = SimpleNamespace(
        attempt_id="ATTEMPT-1", attempt_number=1, status="RUNNING", started_at=STAMP,
        finished_at=None, exit_code=None, result=None, error="/private/raw failure",
    )
    fabric = compose_fabric_view(
        root_job_id="JOB-B5",
        root_job=root,
        jobs=[root, child],
        attempts_by_job={"JOB-CHILD": [attempt]},
        joined_job_ids={"JOB-B5", "JOB-CHILD"},
        runtime_identity={"root": "/private/never-project", "db_present": True, "identity": "id"},
        armed={},
        degraded=[],
        generated_at=STAMP,
    )
    document = compose_mission_workspace(
        control_room=envelope["doc"],
        fabric_view=fabric,
        work_ref="WS:B5",
        root_job_id="JOB-B5",
        source_validity=envelope["source_validity"],
        cache_currentness={"state": "fresh", "publication_seq": envelope["source_validity"]["publication_seq"]},
        source_generation=None,
    )

    assert "qualification_generation" not in envelope["source_validity"]
    assert document["read_state"]["state"] == "PARTIAL"
    assert document["posture"] == {
        "value": "CONSUMPTION_UNKNOWN", "rule": "E3", "evidence": [],
    }
    assert document["mission"]["root_job_id"] == "JOB-B5"
    assert document["principal"]["accountable_seat"] == "ceo"
    assert document["children"]["state"] == "AVAILABLE"
    assert document["children"]["items"][0]["orchestration_role"] == "work"
    latest = document["children"]["items"][0]["latest_attempt"]
    assert latest["error_present"] is True
    assert latest["error_class"] == "WITHHELD"
    assert "/private/raw failure" not in json.dumps(document, sort_keys=True)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda args: args["cache_currentness"].update(state="CURRENT"),
        lambda args: args["cache_currentness"].update(publication_seq=True),
        lambda args: args["cache_currentness"].update(publication_seq=2),
        lambda args: args["source_validity"].update(schema="wrong"),
        lambda args: args["source_validity"].update(profile="wrong"),
        lambda args: args["source_validity"].update(publication_seq=0),
        lambda args: args["control_room"]["autonomy"].update(
            generated_at="2026-09-19T00:00:00Z"
        ),
        lambda args: args["source_validity"].update(cards=args["source_validity"]["cards"] * 2),
        lambda args: args["source_validity"]["cards"][0]["components"].pop("dispatch"),
        lambda args: args["source_validity"]["cards"][0]["components"]["dispatch"].update(remaining_ms=True),
        lambda args: args["source_validity"]["cards"][0]["components"]["dispatch"].update(remaining_ms=0),
        lambda args: args["source_validity"]["cards"][0]["components"]["dispatch"].update(state="expired"),
        lambda args: args["source_validity"]["cards"][0]["components"]["dispatch"].update(proof_ref="A" * 64),
        lambda args: args["source_validity"]["cards"][0]["components"]["dispatch"].update(qualified_at="2026-09-19T00:00:00Z"),
        lambda args: args["control_room"]["autonomy"]["responsibilities"][0]["validity"]["dispatch"].update(schema="wrong"),
        lambda args: args["control_room"]["autonomy"]["responsibilities"][0]["validity"]["dispatch"].update(policy="wrong"),
        lambda args: args["control_room"]["autonomy"]["responsibilities"][0]["validity"]["dispatch"].update(valid_for_ms=True),
        lambda args: args["control_room"]["autonomy"]["responsibilities"][0]["validity"]["dispatch"].update(valid_for_ms=0),
    ],
)
def test_each_currentness_contract_failure_independently_refuses_present_liveness(mutate):
    args = _inputs()
    mutate(args)
    document = compose_mission_workspace(**args)
    assert document["read_state"]["state"] != "CURRENT"
    assert document["posture"]["value"] != "RUNNING"


@pytest.mark.parametrize(
    "diagnostic,projected_state",
    [
        (None, "UNKNOWN"),
        ({}, "UNKNOWN"),
        ({"state": "UNKNOWN", "version": 1, "generation": 2}, "UNKNOWN"),
        ({"state": "STALE", "version": 1, "generation": 2}, "STALE"),
        ({"state": "CURRENT", "version": 1, "generation": 2}, "CURRENT"),
        ({"state": "invented", "version": 1, "generation": 2}, "UNKNOWN"),
    ],
)
def test_unproved_generation_diagnostics_never_establish_present_liveness(
    diagnostic, projected_state,
):
    document = _compose(source_generation=diagnostic)
    assert document["source"]["source_generation"]["state"] == projected_state
    assert document["read_state"]["state"] == "PARTIAL"
    assert document["posture"] == {
        "value": "HISTORICAL_OBSERVATION", "rule": "G1h", "evidence": [],
    }


def test_projected_generation_conflict_drives_the_conflict_predicate():
    document = _compose(
        source_generation={"state": "CONFLICT", "version": 1, "generation": 2}
    )
    assert document["source"]["source_generation"] == {
        "state": "CONFLICT", "version": 1, "generation": 2,
    }
    assert document["read_state"]["state"] == "PARTIAL"
    assert document["posture"] == {
        "value": "RECONCILIATION_REQUIRED", "rule": "B2", "evidence": [],
    }


def test_hidden_generation_conflict_boolean_has_no_unprojected_authority():
    document = _compose(source_generation={"conflict": True})
    assert document["source"]["source_generation"] == {
        "state": "UNKNOWN", "version": None, "generation": None,
    }
    assert document["posture"]["rule"] == "G1h"


def test_missing_fabric_generation_never_yields_current_or_present_liveness():
    args = _inputs()
    args["fabric_view"].pop("generated_at")
    document = compose_mission_workspace(**args)
    assert document["source"]["fabric_view_generated_at"] is None
    assert document["read_state"]["state"] == "PARTIAL"
    assert document["posture"]["rule"] == "G1h"
    assert any(
        row["target_field"] == "source.fabric_view_generated_at"
        for row in document["missingness"]
    )


def test_decision_current_is_admitted_but_is_not_a_mission_currentness_gate():
    args = _inputs()
    before = compose_mission_workspace(**copy.deepcopy(args))
    args["source_validity"]["cards"][0]["components"]["decision_current"].update(
        state="expired", remaining_ms=0
    )
    args["control_room"]["autonomy"]["responsibilities"][0]["validity"]["decision_current"].update(
        valid_for_ms=0
    )
    after = compose_mission_workspace(**args)
    assert after == before


@pytest.mark.parametrize("duplicate", ["program", "responsibility"])
def test_duplicate_exact_identity_is_conflict_not_first_winner(duplicate):
    args = _inputs()
    if duplicate == "program":
        args["control_room"]["work"].append(copy.deepcopy(args["control_room"]["work"][0]))
    else:
        args["control_room"]["autonomy"]["responsibilities"].append(
            copy.deepcopy(args["control_room"]["autonomy"]["responsibilities"][0])
        )
    document = compose_mission_workspace(**args)
    assert document["mission"]["root_job_id"] is None
    assert document["mission"]["runtime_root_state"] == "CONFLICT"
    assert document["posture"]["rule"] == "B2"


def test_zero_two_and_unhashable_root_candidates_fail_closed_without_throwing():
    zero = compose_mission_workspace(**_inputs(candidates=()))
    assert zero["mission"]["runtime_root_state"] == "UNKNOWN"
    assert zero["mission"]["root_job_id"] is None

    two = compose_mission_workspace(**_inputs(candidates=("JOB-1", "JOB-2")))
    assert two["mission"]["runtime_root_state"] == "CONFLICT"
    assert two["mission"]["root_job_candidates"] == ["JOB-1", "JOB-2"]

    args = _inputs()
    card = args["control_room"]["autonomy"]["responsibilities"][0]
    card["root_job_candidates"] = [["unhashable"]]
    malformed = compose_mission_workspace(**args)
    assert malformed["mission"]["runtime_root_state"] == "CONFLICT"
    assert malformed["mission"]["root_job_id"] is None


def test_unjoined_ids_are_bounded_and_incomplete_counts_remain_null():
    args = _inputs(unjoined_count=72, unjoined_ids=tuple(f"JOB-{index:03d}" for index in range(72)))
    args["fabric_view"]["children"] = [
        {
            "job_id": "CHILD", "root_job_id": "JOB-1", "parent_job_id": "JOB-1",
            "status": "RUNNING", "depth": 1, "orchestration_role": "work",
            "plan_step_id": None, "attempt_count": 0, "attempt_limit": 1,
            "current_attempt_id": None, "latest_attempt": None,
        }
    ]
    section = compose_mission_workspace(**args)["children"]
    assert section["state"] == "PARTIAL"
    assert section["coverage"] == "INCOMPLETE"
    assert section["total_count"] is None and section["overflow_count"] is None
    assert section["unjoined_job_count"] == 72
    assert len(section["unjoined_job_ids"]) == 50
    assert section["items"][0]["job_id"] == "CHILD"


def test_program_evidence_sources_and_autonomy_disagreement_are_preserved_safely():
    args = _inputs()
    work = args["control_room"]["work"][0]
    work["github"]["prs"] = [
        {
            "repo": "org/repo", "number": 7, "url": "https://github.com/org/repo/pull/7",
            "title": "Bounded change", "branch": "claude/bounded", "draft": True,
            "merge_state": "BLOCKED",
        }
    ]
    work["attention_ids"] = ["ATTENTION-1"]
    work["disagreements"] = ["Agent OS and GitHub disagree"]
    args["control_room"]["autonomy"]["responsibilities"][0]["disagreements"] = [
        {"field": "wake_outcome", "values": ["acknowledged", "failed"], "sources": []}
    ]
    program = compose_mission_workspace(**args)["program"]
    assert program["github_prs"][0]["number"] == 7
    assert program["attention_ids"] == ["ATTENTION-1"]
    assert {row["source"] for row in program["disagreements"]} == {
        "control_room", "autonomy_projection",
    }


def test_evidence_accepts_only_the_exact_closed_tuple_and_enums():
    args = _inputs()
    evidence = {
        "owner": "EXECUTIVE_OS",
        "ref": "JOB-1",
        "field": "root.status",
        "source_revision": None,
        "source_time": None,
        "observed_at": STAMP,
        "freshness_state": "CURRENT",
    }
    args["control_room"]["work"][0]["evidence"] = [
        evidence,
        copy.deepcopy(evidence),
        {**evidence, "owner": "invented"},
        {**evidence, "freshness_state": "UNKNOWN"},
        {**evidence, "extra": "not closed"},
    ]
    output = compose_mission_workspace(**args)["program"]["evidence"]
    assert output == [evidence]
    assert set(output[0]) == EVIDENCE_KEYS
    assert output[0]["owner"] in EVIDENCE_OWNERS
    assert output[0]["freshness_state"] in EVIDENCE_FRESHNESS_STATES


@pytest.mark.parametrize(
    "bad_timestamp",
    [
        "TbadZ",
        "2026-13-01T00:00:00Z",
        "2026-02-29T00:00:00Z",
        "2026-09-20T24:00:00Z",
        "2026-09-20T00:00:60Z",
        "2026-09-20 00:00:00Z",
        "2026-09-20T00:00:00-07:00",
    ],
)
def test_invalid_evidence_timestamp_is_withheld_with_fixed_missingness(bad_timestamp):
    args = _inputs()
    args["control_room"]["work"][0]["evidence"] = [
        {
            "owner": "EXECUTIVE_OS",
            "ref": "private diagnostic must not echo",
            "field": "root.status",
            "source_revision": None,
            "source_time": None,
            "observed_at": bad_timestamp,
            "freshness_state": "CURRENT",
        }
    ]
    document = compose_mission_workspace(**args)
    raw = json.dumps(document, sort_keys=True)
    assert document["program"]["evidence"] == []
    assert bad_timestamp not in raw
    assert "private diagnostic must not echo" not in raw
    evidence_facts = [
        row for row in document["missingness"]
        if row["target_field"] == "program.evidence"
    ]
    assert evidence_facts == [
        {
            "missingness_class": "DEGRADED",
            "target_field": "program.evidence",
            "producer_owner": None,
            "reason": "source detail withheld",
        }
    ]


def test_invalid_source_timestamp_is_null_and_generates_fixed_missingness():
    args = _inputs()
    args["fabric_view"]["generated_at"] = "TbadZ"
    document = compose_mission_workspace(**args)
    assert document["source"]["fabric_view_generated_at"] is None
    assert document["read_state"]["state"] == "PARTIAL"
    assert any(
        row["target_field"] == "source.fabric_view_generated_at"
        and row["reason"] == "source detail withheld"
        for row in document["missingness"]
    )
    assert "TbadZ" not in json.dumps(document, sort_keys=True)


def test_equivalent_utc_forms_are_canonicalized_before_currentness_equality():
    utc_offset_form = "2026-09-20T00:00:00+00:00"
    args = _inputs()
    responsibility = args["control_room"]["autonomy"]["responsibilities"][0]
    for metadata in responsibility["validity"].values():
        metadata["qualified_at"] = utc_offset_form

    assert _safe_timestamp(utc_offset_form) == STAMP
    assert _qualified_current(
        validity=args["source_validity"],
        cache=args["cache_currentness"],
        responsibility=responsibility,
        responsibility_ref="WS:ONE",
        root_job_id="JOB-1",
        control_generated_at=STAMP,
        autonomy_generated_at=STAMP,
    ) is True

    args["control_room"]["work"][0]["evidence"] = [
        {
            "owner": "EXECUTIVE_OS",
            "ref": "JOB-1",
            "field": "root.status",
            "source_revision": None,
            "source_time": utc_offset_form,
            "observed_at": utc_offset_form,
            "freshness_state": "CURRENT",
        }
    ]
    evidence = compose_mission_workspace(**args)["program"]["evidence"][0]
    assert evidence["source_time"] == STAMP
    assert evidence["observed_at"] == STAMP


@pytest.mark.parametrize("invalid_evidence", [{"not": "an array"}, [None], "raw diagnostic"])
def test_invalid_evidence_container_is_not_silently_dropped(invalid_evidence):
    args = _inputs()
    args["control_room"]["work"][0]["evidence"] = invalid_evidence
    document = compose_mission_workspace(**args)
    assert document["program"]["evidence"] == []
    assert any(
        row["target_field"] == "program.evidence"
        and row["reason"] == "source detail withheld"
        for row in document["missingness"]
    )
    assert "raw diagnostic" not in json.dumps(document, sort_keys=True)


def test_invalid_owed_turn_source_receipt_is_withheld_with_fixed_missingness():
    args = _inputs()
    owed_turn = args["control_room"]["autonomy"]["responsibilities"][0]["owed_turn"]
    owed_turn["source_refs"] = [
        {
            "owner": "executive_inbox", "ref": "private raw receipt",
            "observed_at": "TbadZ", "freshness": "current",
        }
    ]
    document = compose_mission_workspace(**args)
    assert document["principal"]["owed_turn"]["source_refs"] == []
    assert any(
        row["target_field"] == "principal.owed_turn.source_refs"
        and row["reason"] == "source detail withheld"
        for row in document["missingness"]
    )
    raw = json.dumps(document, sort_keys=True)
    assert "private raw receipt" not in raw
    assert "TbadZ" not in raw


@pytest.mark.parametrize("state", ["CONTINUED", "STOPPED"])
def test_unproduced_dialogue_states_remain_typed_not_projected(state):
    args = _inputs(dispatch_state=state)
    document = compose_mission_workspace(**args)
    assert document["transport"]["dispatch_state"] == "UNKNOWN"
    assert document["posture"]["value"] != "RUNNING"
    assert any(row["target_field"] == f"transport.{state.lower()}" for row in document["missingness"])


def test_execution_review_transport_and_acceptance_remain_four_distinct_facets():
    args = _inputs(dispatch_state="RETURNED", execution_state="ACCEPTED")
    args["fabric_view"]["root"]["review"] = {
        "required": True, "reviews_job_id": "REVIEW-1", "verdict": "approve",
    }
    document = compose_mission_workspace(**args)
    assert document["execution"]["state"] == "ACCEPTED"
    assert document["review"]["verdict"] == "approve"
    assert document["transport"]["dispatch_state"] == "RETURNED"
    assert document["acceptance"] == {
        "state": "NOT_PROJECTED",
        "reason_codes": ["ACCEPTANCE_OWNER_NOT_PROJECTED"],
        "owner": None,
        "artifact_revision": None,
        "ruling": None,
        "evidence": [],
    }
    assert document["posture"] == {
        "value": "CONSUMPTION_UNKNOWN", "rule": "E3", "evidence": [],
    }


def test_historical_cache_and_stale_start_never_announce_present_liveness():
    args = _inputs()
    args["cache_currentness"] = {
        "state": "historical_refresh_error", "publication_seq": 1,
    }
    document = compose_mission_workspace(**args)
    assert document["read_state"]["state"] == "HISTORICAL"
    assert document["posture"] == {
        "value": "HISTORICAL_OBSERVATION", "rule": "G1h", "evidence": [],
    }
    assert document["children"]["state"] == "HISTORICAL"
    assert document["children"]["coverage"] == "HISTORICAL_ONLY"
    assert document["children"]["total_count"] is None
    assert document["children"]["overflow_count"] is None


@pytest.mark.parametrize("owner", ["control_room", "fabric_view"])
def test_wrong_schema_cannot_contribute_nested_owner_fields(owner):
    args = _inputs()
    args[owner]["schema"] = "wrong"
    if owner == "control_room":
        args["control_room"]["autonomy"]["responsibilities"][0]["current_worker"] = {
            "worker_id": "must-not-project", "status": "RUNNING",
        }
    else:
        args["fabric_view"]["armed"] = {
            "ceo_submit_armed": False, "source": "must-not-project",
        }
        args["fabric_view"]["capability"]["detail"] = "must-not-project"
        args["fabric_view"]["unjoined_job_ids"] = ["must-not-project"]

    document = compose_mission_workspace(**args)
    raw = json.dumps(document, sort_keys=True)
    assert "must-not-project" not in raw
    assert document["read_state"]["state"] != "CURRENT"


def test_fabric_root_must_be_a_self_identified_root():
    args = _inputs()
    args["fabric_view"]["root"]["root_job_id"] = None
    document = compose_mission_workspace(**args)
    assert document["mission"]["root_job_id"] is None
    assert document["mission"]["runtime_root_state"] == "CONFLICT"
    assert document["mission"]["root_job_ambiguous"] is True
    assert document["children"]["coverage"] == "INCOMPLETE"
    assert document["posture"]["rule"] == "B2"


@pytest.mark.parametrize("malformed_result", [None, "BOGUS", {}, {"state": "BOGUS"}])
def test_malformed_root_result_never_invents_not_started(malformed_result):
    args = _inputs()
    args["fabric_view"]["root"]["result"] = malformed_result
    document = compose_mission_workspace(**args)
    assert document["execution"]["state"] is None
    assert document["posture"]["value"] not in {"NOT_STARTED", "RUNNING", "WAITING"}
    assert any(
        row["missingness_class"] == "DEGRADED" and row["target_field"] == "execution"
        for row in document["missingness"]
    )
    assert "BOGUS" not in json.dumps(document, sort_keys=True)


def test_explicit_valid_not_started_result_remains_a_real_execution_fact():
    args = _inputs(execution_state="NOT_STARTED")
    document = compose_mission_workspace(**args)
    assert document["execution"]["state"] == "NOT_STARTED"


def _child_row(job_id="CHILD", *, root_job_id="JOB-1"):
    return {
        "job_id": job_id,
        "root_job_id": root_job_id,
        "parent_job_id": "JOB-1",
        "status": "RUNNING",
        "depth": 1,
        "orchestration_role": "work",
        "plan_step_id": None,
        "attempt_count": 0,
        "attempt_limit": 1,
        "current_attempt_id": None,
        "latest_attempt": None,
    }


def _attempt_row():
    return {
        "attempt_id": "ATTEMPT-1",
        "attempt_number": 1,
        "status": "RUNNING",
        "started_at": STAMP,
        "finished_at": None,
        "exit_code": None,
        "has_result": False,
        "error": None,
    }


def _child_with_attempt():
    child = _child_row()
    child.update(
        attempt_count=1,
        current_attempt_id="ATTEMPT-1",
        latest_attempt=_attempt_row(),
    )
    return child


def _assert_incomplete_children(document, *, expected_job_ids):
    section = document["children"]
    assert section["state"] == "PARTIAL"
    assert section["coverage"] == "INCOMPLETE"
    assert section["total_count"] is None
    assert section["overflow_count"] is None
    assert [row["job_id"] for row in section["items"]] == expected_job_ids
    assert any(
        row == {
            "missingness_class": "DEGRADED",
            "target_field": "children",
            "producer_owner": "executive_os",
            "reason": "source detail withheld",
        }
        for row in document["missingness"]
    )


def test_child_input_key_tables_are_bound_to_the_protected_fabric_contract():
    assert CONSUMED_JOB_CARD_KEYS == {
        "job_id", "status", "parent_job_id", "root_job_id", "depth",
        "orchestration_role", "plan_step_id", "attempt_count", "attempt_limit",
        "current_attempt_id", "latest_attempt",
    }
    assert CONSUMED_JOB_CARD_KEYS < OWNER_JOB_CARD_KEYS
    assert FABRIC_ATTEMPT_CARD_KEYS == OWNER_ATTEMPT_CARD_KEYS


@pytest.mark.parametrize("invalid_kind", ["malformed", "duplicate", "wrong_root"])
def test_invalid_child_identity_rows_are_rejected_without_false_empty_complete(invalid_kind):
    args = _inputs()
    valid = _child_row("VALID")
    if invalid_kind == "malformed":
        rows = [None, valid]
    elif invalid_kind == "duplicate":
        rows = [_child_row("DUP"), _child_row("DUP"), valid]
    else:
        rows = [_child_row("WRONG", root_job_id="OTHER-ROOT"), valid]
    args["fabric_view"]["children"] = rows

    document = compose_mission_workspace(**args)
    _assert_incomplete_children(document, expected_job_ids=["VALID"])


@pytest.mark.parametrize("missing_field", sorted(CONSUMED_JOB_CARD_KEYS))
def test_every_missing_consumed_child_field_refuses_complete_coverage(missing_field):
    args = _inputs()
    child = _child_with_attempt()
    child.pop(missing_field)
    args["fabric_view"]["children"] = [child]

    document = compose_mission_workspace(**args)
    expected_ids = [] if missing_field in {"job_id", "parent_job_id", "root_job_id"} else ["CHILD"]
    _assert_incomplete_children(document, expected_job_ids=expected_ids)


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("status", "BOGUS", id="status-enum"),
        pytest.param("status", [], id="status-unhashable"),
        pytest.param("depth", "one", id="depth-string"),
        pytest.param("depth", True, id="depth-bool"),
        pytest.param("depth", -1, id="depth-negative"),
        pytest.param("orchestration_role", "delegate", id="role-enum"),
        pytest.param("orchestration_role", [], id="role-type"),
        pytest.param("plan_step_id", [], id="plan-step-type"),
        pytest.param("plan_step_id", "", id="plan-step-empty"),
        pytest.param("attempt_count", "one", id="attempt-count-string"),
        pytest.param("attempt_count", True, id="attempt-count-bool"),
        pytest.param("attempt_count", -1, id="attempt-count-negative"),
        pytest.param("attempt_limit", "one", id="attempt-limit-string"),
        pytest.param("attempt_limit", True, id="attempt-limit-bool"),
        pytest.param("attempt_limit", 0, id="attempt-limit-nonpositive"),
        pytest.param("current_attempt_id", [], id="current-attempt-type"),
        pytest.param("current_attempt_id", "", id="current-attempt-empty"),
        pytest.param("latest_attempt", [], id="latest-attempt-type"),
    ],
)
def test_invalid_consumed_child_values_preserve_safe_facts_but_refuse_complete_coverage(
    field, value,
):
    args = _inputs()
    child = _child_with_attempt()
    child[field] = value
    args["fabric_view"]["children"] = [child]

    document = compose_mission_workspace(**args)
    _assert_incomplete_children(document, expected_job_ids=["CHILD"])
    raw = json.dumps(document, sort_keys=True)
    assert "BOGUS" not in raw
    assert "delegate" not in raw
    assert '"one"' not in raw


@pytest.mark.parametrize("missing_field", sorted(FABRIC_ATTEMPT_CARD_KEYS))
def test_every_missing_latest_attempt_field_refuses_complete_coverage(missing_field):
    args = _inputs()
    child = _child_with_attempt()
    child["latest_attempt"].pop(missing_field)
    args["fabric_view"]["children"] = [child]

    document = compose_mission_workspace(**args)
    _assert_incomplete_children(document, expected_job_ids=["CHILD"])


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("attempt_id", "", id="attempt-id-empty"),
        pytest.param("attempt_id", [], id="attempt-id-type"),
        pytest.param("attempt_number", "one", id="attempt-number-string"),
        pytest.param("attempt_number", True, id="attempt-number-bool"),
        pytest.param("attempt_number", 0, id="attempt-number-nonpositive"),
        pytest.param("status", "BOGUS", id="attempt-status-enum"),
        pytest.param("status", [], id="attempt-status-unhashable"),
        pytest.param("started_at", "TbadZ", id="started-at-invalid"),
        pytest.param("started_at", "", id="started-at-empty"),
        pytest.param("started_at", None, id="started-at-null"),
        pytest.param("finished_at", "TbadZ", id="finished-at-invalid"),
        pytest.param("finished_at", 1, id="finished-at-type"),
        pytest.param("exit_code", "one", id="exit-code-string"),
        pytest.param("exit_code", True, id="exit-code-bool"),
        pytest.param("has_result", "yes", id="has-result-string"),
        pytest.param("has_result", 1, id="has-result-int"),
        pytest.param("has_result", None, id="has-result-null"),
        pytest.param("error", {}, id="error-mapping"),
        pytest.param("error", 1, id="error-int"),
    ],
)
def test_invalid_latest_attempt_values_preserve_safe_facts_but_refuse_complete_coverage(
    field, value,
):
    args = _inputs()
    child = _child_with_attempt()
    child["latest_attempt"][field] = value
    args["fabric_view"]["children"] = [child]

    document = compose_mission_workspace(**args)
    _assert_incomplete_children(document, expected_job_ids=["CHILD"])
    projected = document["children"]["items"][0]["latest_attempt"]
    assert projected["attempt_id"] == (
        None if field == "attempt_id" else "ATTEMPT-1"
    )
    raw = json.dumps(document, sort_keys=True)
    assert "BOGUS" not in raw
    assert "TbadZ" not in raw
    assert '"one"' not in raw
    assert '"yes"' not in raw


def test_valid_nullable_child_and_attempt_fields_remain_complete():
    args = _inputs()
    without_attempt = _child_row("NO-ATTEMPT")
    without_attempt["orchestration_role"] = None
    with_attempt = _child_with_attempt()
    args["fabric_view"]["children"] = [without_attempt, with_attempt]

    document = compose_mission_workspace(**args)
    section = document["children"]
    assert section["state"] == "AVAILABLE"
    assert section["coverage"] == "COMPLETE"
    assert section["total_count"] == 2
    assert section["overflow_count"] == 0
    assert section["items"][0]["latest_attempt"] is None
    latest = section["items"][1]["latest_attempt"]
    assert latest["finished_at"] is None
    assert latest["exit_code"] is None
    assert latest["error_present"] is False
    assert latest["error_class"] is None


def test_persisted_runtime_attempt_utc_forms_survive_fabric_and_reducer(tmp_path):
    """Exercise incumbent Runtime timestamps instead of a synthetic attempt card."""

    from control_plane.executive_runtime import Runtime

    runtime = Runtime.at(tmp_path / "runtime")
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="primary",
        worker_type="mock",
        capabilities=["code"],
    )
    root = runtime.jobs.create_job("Persisted root")
    child = runtime.jobs.create_job("Persisted child", parent_job_id=root.job_id)
    assert runtime.attempts.claim_job(child.job_id, worker_id="worker-01") is not None

    persisted_root = runtime.jobs.get_job(root.job_id)
    persisted_child = runtime.jobs.get_job(child.job_id)
    assert persisted_root is not None
    assert persisted_child is not None
    persisted_attempts = runtime.attempts.list_attempts(child.job_id)
    fabric = compose_fabric_view(
        root_job_id=root.job_id,
        root_job=persisted_root,
        jobs=[persisted_root, persisted_child],
        attempts_by_job={child.job_id: persisted_attempts},
        joined_job_ids={root.job_id, child.job_id},
        runtime_identity={"root": str(tmp_path / "runtime"), "db_present": True},
        armed={},
        degraded=[],
        generated_at=STAMP,
    )
    owner_attempt = fabric["children"][0]["latest_attempt"]
    assert owner_attempt["started_at"].endswith("+00:00")
    assert owner_attempt["finished_at"] == ""

    args = _inputs()
    responsibility = args["control_room"]["autonomy"]["responsibilities"][0]
    responsibility.update(
        root_job_id=root.job_id,
        root_job_candidates=[root.job_id],
    )
    args["source_validity"]["cards"][0]["root_job_id"] = root.job_id
    args["root_job_id"] = root.job_id
    args["fabric_view"] = fabric

    document = compose_mission_workspace(**args)
    section = document["children"]
    assert document["read_state"]["state"] == "PARTIAL"
    assert section["state"] == "AVAILABLE"
    assert section["coverage"] == "COMPLETE"
    projected_attempt = section["items"][0]["latest_attempt"]
    assert projected_attempt["started_at"] == f"{owner_attempt['started_at'][:-6]}Z"
    assert projected_attempt["finished_at"] is None
    assert not any(
        row["missingness_class"] == "DEGRADED" and row["target_field"] == "children"
        for row in document["missingness"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda fabric: fabric.pop("children"),
        lambda fabric: fabric.update(children=None),
        lambda fabric: fabric.update(unjoined_job_count=None),
        lambda fabric: fabric.update(unjoined_job_count=True),
        lambda fabric: fabric.pop("unjoined_job_ids"),
    ],
)
def test_exact_child_zero_requires_a_valid_owner_document(mutation):
    args = _inputs()
    mutation(args["fabric_view"])
    section = compose_mission_workspace(**args)["children"]
    assert section["state"] == "PARTIAL"
    assert section["coverage"] == "INCOMPLETE"
    assert section["total_count"] is None
    assert section["overflow_count"] is None


@pytest.mark.parametrize("armed, expected", [(False, "UNAVAILABLE_NEW_SUBMISSION"), (True, "UNKNOWN"), (None, "UNKNOWN")])
def test_arm_state_is_tri_state_and_never_establishes_positive_availability(armed, expected):
    args = _inputs()
    if armed is not None:
        args["fabric_view"]["armed"] = {"ceo_submit_armed": armed, "source": "control.json"}
    document = compose_mission_workspace(**args)
    assert document["mission"]["armed"]["ceo_submit_armed"] is armed
    assert document["mission"]["submission_availability"] == expected
    assert document["mission"]["root_job_id"] == "JOB-1"
    assert "no Chairman-authenticated admitted job can exist" not in json.dumps(document)


def test_private_paths_hosts_tokens_raw_errors_and_source_reasons_never_escape():
    args = _inputs()
    args["control_room"]["work"][0]["agent_os"]["next_action"] = "Bearer secret-value"
    args["control_room"]["work"][0]["agent_os"]["title"] = "private.internal"
    args["control_room"]["degraded"] = ["failed at /Users/private/runtime.sqlite3"]
    args["fabric_view"]["degraded"] = ["token X-CCR-Token=secret at /private/thing"]
    args["fabric_view"]["missingness"] = [
        {
            "missingness_class": "DEGRADED", "target_field": "runtime.jobs",
            "producer_owner": "executive_os", "reason": "raw /private/path and ghp_secret",
        }
    ]
    args["fabric_view"]["children"] = [
        {
            "job_id": "CHILD", "root_job_id": "JOB-1", "parent_job_id": "JOB-1",
            "status": "FAILED", "depth": 1, "orchestration_role": "work",
            "plan_step_id": None, "attempt_count": 1, "attempt_limit": 1,
            "current_attempt_id": "ATTEMPT", "latest_attempt": {
                "attempt_id": "ATTEMPT", "attempt_number": 1, "status": "FAILED",
                "started_at": STAMP, "finished_at": STAMP, "exit_code": 1,
                "has_result": False, "error": "provider_session_id=secret /private/path",
            },
        }
    ]
    args["fabric_view"]["root"]["result"].update(
        artifacts=["/private/artifact", "safe receipt"],
        next_actions=["https://private.internal/do", "safe next action"],
    )
    raw = json.dumps(compose_mission_workspace(**args), sort_keys=True)
    for secret in (
        "/Users/private", "/private/thing", "/private/path", "private.internal",
        "secret-value", "ghp_secret", "provider_session_id=secret",
    ):
        assert secret not in raw
    assert "agent_os_detail_redacted" in raw
    assert "source detail withheld" in raw
    assert "WITHHELD" in raw
    assert "safe receipt" in raw and "safe next action" in raw


@pytest.mark.parametrize(
    "field,value",
    [
        ("control_room", None),
        ("fabric_view", None),
        ("source_validity", None),
        ("cache_currentness", None),
        ("source_generation", None),
        ("control_room", []),
        ("fabric_view", []),
        ("source_validity", []),
        ("cache_currentness", []),
    ],
)
def test_malformed_top_level_inputs_return_typed_output_and_never_throw(field, value):
    args = _inputs()
    args[field] = value
    document = compose_mission_workspace(**args)
    assert set(document) == OUTPUT_KEYS
    assert document["read_state"]["state"] in READ_STATES


def test_permanent_full_3696_posture_oracle_sweep_is_total_and_currentness_safe():
    execution_states = (
        "NOT_STARTED", "IN_PROGRESS", "ACCEPTED", "CANCELLED", "FAILED", "LOST", "RATE_LIMITED",
    )
    dispatch_states = (
        "WAITING_CAPACITY", "RECEIVER_SELECTED", "DELIVERY_SENT", "PICKUP_ACKNOWLEDGED",
        "STARTED", "RETURNED", "DELIVERY_UNCONSUMED", "WATCH_UNPROVEN",
        "RUNTIME_BINDING_RECONCILIATION_REQUIRED", "EFFECT_UNKNOWN", "UNKNOWN",
    )
    review_verdicts = ("approve", "reject", "NOT_YET")
    acceptances = (
        {"state": "NOT_PROJECTED", "artifact_revision": None, "ruling": None},
        {"state": "ACCEPTED", "artifact_revision": "revision-1", "ruling": "accept"},
    )
    observed_rules = set()
    observed_postures = set()
    count = 0
    for execution, dispatch, review, acceptance, current, blocker, conflict in itertools.product(
        execution_states,
        dispatch_states,
        review_verdicts,
        acceptances,
        (False, True),
        (False, True),
        (False, True),
    ):
        posture, rule = _posture(
            execution=execution,
            dispatch=dispatch,
            current=current,
            conflict=conflict,
            blocker=blocker,
            acceptance=acceptance,
            review=review,
        )
        count += 1
        observed_rules.add(rule)
        observed_postures.add(posture)
        assert isinstance(posture, str) and posture
        assert isinstance(rule, str) and rule
        if not current:
            assert posture not in {"RUNNING", "WAITING"}
        if posture == "ACCEPTED_PRODUCT":
            assert acceptance["state"] == "ACCEPTED"
            assert rule == "F2"
        if dispatch == "RUNTIME_BINDING_RECONCILIATION_REQUIRED":
            assert (posture, rule) == ("RECONCILIATION_REQUIRED", "B1")
        if dispatch == "EFFECT_UNKNOWN":
            assert (posture, rule) == ("EFFECT_UNKNOWN", "A1")

    assert count == 3696
    assert observed_rules == {
        "A1", "B1", "B2", "C1", "C2", "C3", "C4", "D1", "E1", "E2", "E3",
        "F0", "F1", "F2", "F3", "F4", "F5", "G1", "G1h", "G2", "G2h", "H1", "I1",
    }
    assert len(observed_postures) == 20


def test_mission_v2_uses_completed_execution_and_keeps_acceptance_unproduced():
    document = _compose_v2()

    assert document["schema"] == SCHEMA_V2
    assert document["source"]["fabric_view_schema"] == "mastermind.fabric_job_view.v2"
    assert document["execution"]["state"] == "COMPLETED"
    assert document["acceptance"] == {
        "state": "NOT_PROJECTED",
        "reason_codes": ["ACCEPTANCE_OWNER_NOT_PROJECTED"],
        "owner": None,
        "artifact_revision": None,
        "ruling": None,
        "evidence": [],
    }
    assert document["read_state"]["state"] == "PARTIAL"
    assert document["posture"] == {
        "value": "CONSUMPTION_UNKNOWN", "rule": "E3", "evidence": [],
    }


def test_mission_v2_retains_program_when_frozen_fabric_v2_emits_null_root():
    args = _inputs_v2()
    args["fabric_view"]["root"] = None
    args["fabric_view"]["capability"] = {
        "state": "PARTIAL",
        "installed": True,
        "version": None,
        "detail": "the executive runtime database was read; the requested root job is not in it",
    }

    document = compose_mission_workspace_v2(**args)

    assert document["schema"] == SCHEMA_V2
    assert document["program"]["work_ref"] == "WS:ONE"
    assert document["source"]["fabric_view_schema"] == "mastermind.fabric_job_view.v2"
    assert document["mission"]["root_job_id"] is None
    assert document["mission"]["runtime_root_state"] == "UNKNOWN"
    assert document["children"]["state"] == "UNAVAILABLE"
    assert document["read_state"]["state"] == "PARTIAL"


def test_mission_v2_refuses_malformed_non_null_root_instead_of_treating_it_as_absent():
    args = _inputs_v2()
    args["fabric_view"]["root"] = {}

    with pytest.raises(ValueError, match="root"):
        compose_mission_workspace_v2(**args)


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda args: args["fabric_view"].update(schema="mastermind.fabric_job_view.v1"), "schema"),
        (lambda args: args["fabric_view"]["root"]["result"].update(state="ACCEPTED"), "result.state"),
        (lambda args: args["fabric_view"]["root"].pop("acceptance"), "acceptance"),
        (lambda args: args["fabric_view"]["root"]["acceptance"].update(producer_owner="fabric"), "acceptance"),
        (lambda args: args["fabric_view"]["root"]["acceptance"].update(state="ACCEPTED"), "acceptance"),
    ],
)
def test_mission_v2_refuses_wrong_fabric_version_execution_alias_and_invalid_acceptance(
    mutate, expected,
):
    args = _inputs_v2()
    mutate(args)

    with pytest.raises(ValueError, match=expected):
        compose_mission_workspace_v2(**args)


def test_mission_v2_refuses_missing_and_foreign_child_acceptance_facets():
    args = _inputs_v2()
    child = copy.deepcopy(args["fabric_view"]["root"])
    child.update({"job_id": "JOB-CHILD", "root_job_id": "JOB-1", "parent_job_id": "JOB-1", "depth": 1})
    args["fabric_view"]["children"] = [child]
    args["fabric_view"]["children"][0].pop("acceptance")

    with pytest.raises(ValueError, match="child.*acceptance"):
        compose_mission_workspace_v2(**args)

    args["fabric_view"]["children"][0]["acceptance"] = {
        "state": "NOT_PROJECTED", "producer_owner": "other-owner",
        "reason": "product acceptance has no producer in this projection",
    }
    with pytest.raises(ValueError, match="child.*acceptance"):
        compose_mission_workspace_v2(**args)


def test_mission_v2_refuses_unclosed_or_unknown_root_and_child_review_facets():
    args = _inputs_v2()
    args["fabric_view"]["root"]["review"]["evidence"] = []

    with pytest.raises(ValueError, match="root.*review"):
        compose_mission_workspace_v2(**args)

    args = _inputs_v2()
    child = copy.deepcopy(args["fabric_view"]["root"])
    child.update({"job_id": "JOB-CHILD", "root_job_id": "JOB-1", "parent_job_id": "JOB-1", "depth": 1})
    child["review"]["verdict"] = "foreign"
    args["fabric_view"]["children"] = [child]

    with pytest.raises(ValueError, match="child.*review"):
        compose_mission_workspace_v2(**args)


def test_mission_v2_refuses_non_string_root_and_child_result_states_with_value_error():
    args = _inputs_v2()
    args["fabric_view"]["root"]["result"]["state"] = ["COMPLETED"]

    with pytest.raises(ValueError, match="root result.state"):
        compose_mission_workspace_v2(**args)

    args = _inputs_v2()
    child = copy.deepcopy(args["fabric_view"]["root"])
    child.update({"job_id": "JOB-CHILD", "root_job_id": "JOB-1", "parent_job_id": "JOB-1", "depth": 1})
    child["result"]["state"] = {"state": "COMPLETED"}
    args["fabric_view"]["children"] = [child]

    with pytest.raises(ValueError, match="child result.state"):
        compose_mission_workspace_v2(**args)

def test_mission_v2_result_and_approved_review_cannot_manufacture_acceptance():
    args = _inputs_v2()
    args["fabric_view"]["root"]["result"].update(
        summary="accepted product", artifacts=["accepted=true", "ruling=approve"]
    )
    args["fabric_view"]["root"]["review"].update(
        required=True, reviews_job_id="REVIEW-1", verdict="approve"
    )

    document = compose_mission_workspace_v2(**args)

    assert document["execution"]["state"] == "COMPLETED"
    assert document["review"]["verdict"] == "approve"
    assert document["acceptance"]["state"] == "NOT_PROJECTED"
    assert document["acceptance"]["owner"] is None
    assert document["posture"]["value"] != "ACCEPTED_PRODUCT"


def test_mission_v2_current_generation_diagnostic_stays_unproduced_without_owner_receipt():
    document = _compose_v2(
        source_generation={"state": "CURRENT", "version": 1, "generation": 1},
    )

    assert document["source"]["source_generation"] == {
        "state": "CURRENT", "version": 1, "generation": 1,
    }
    assert document["read_state"]["state"] == "PARTIAL"
    assert document["posture"]["value"] == "CONSUMPTION_UNKNOWN"


def test_mission_v2_full_3696_posture_oracle_replaces_execution_accepted_with_completed():
    execution_states = (
        "NOT_STARTED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "FAILED", "LOST", "RATE_LIMITED",
    )
    dispatch_states = (
        "WAITING_CAPACITY", "RECEIVER_SELECTED", "DELIVERY_SENT", "PICKUP_ACKNOWLEDGED",
        "STARTED", "RETURNED", "DELIVERY_UNCONSUMED", "WATCH_UNPROVEN",
        "RUNTIME_BINDING_RECONCILIATION_REQUIRED", "EFFECT_UNKNOWN", "UNKNOWN",
    )
    acceptances = (
        {"state": "NOT_PROJECTED", "artifact_revision": None, "ruling": None},
        {"state": "ACCEPTED", "artifact_revision": "revision-1", "ruling": "accept"},
    )
    observed_rules = set()
    count = 0
    for execution, dispatch, review, acceptance, current, blocker, conflict in itertools.product(
        execution_states, dispatch_states, ("approve", "reject", "NOT_YET"),
        acceptances,
        (False, True), (False, True), (False, True),
    ):
        posture, rule = _posture_v2(
            execution=execution,
            dispatch=dispatch,
            current=current,
            conflict=conflict,
            blocker=blocker,
            acceptance=acceptance,
            review=review,
        )
        count += 1
        observed_rules.add(rule)
        assert isinstance(posture, str) and posture
        assert isinstance(rule, str) and rule
        if not current:
            assert posture not in {"RUNNING", "WAITING"}
        if (
            dispatch == "RETURNED"
            and current
            and execution in {"NOT_STARTED", "IN_PROGRESS"}
            and not blocker
            and not conflict
        ):
            assert (posture, rule) == ("RETURN_EXECUTION_MISMATCH", "F0")

    assert count == 3696
    assert observed_rules == {
        "A1", "B1", "B2", "C1", "C2", "C3", "C4", "D1", "E1", "E2", "E3",
        "F0", "F1", "F2", "F3", "F4", "F5", "G1", "G1h", "G2", "G2h", "H1", "I1",
    }


def test_same_inputs_are_byte_identical_and_not_mutated():
    args = _inputs()
    before = copy.deepcopy(args)
    first = json.dumps(compose_mission_workspace(**args), sort_keys=True)
    second = json.dumps(compose_mission_workspace(**copy.deepcopy(args)), sort_keys=True)
    assert first == second
    assert args == before


def test_module_has_no_acquisition_clock_randomness_or_authority_imports():
    source = Path("control_plane/mission_workspace.py").read_text()
    tree = ast.parse(source)
    names = {
        name.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for name in node.names
    }
    modules = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    forbidden = {
        "os", "subprocess", "socket", "random", "time", "datetime", "requests", "httpx",
        "executive_runtime", "executive_worker_broker",
    }
    assert not (names | modules) & forbidden
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    attributes = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not calls & {"open", "exec", "eval", "__import__"}
    assert not attributes & {"read_text", "write_text", "run", "Popen", "request", "post", "connect"}


# Ratified workspace owner observation: fixture construction is test-only. The
# service, not the HTTP/model caller, supplies this receipt to the pure reducer.
def _owner_observation_inputs():
    import hashlib

    args = _inputs_v2()
    def digest(value):
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode()).hexdigest()
    generation = {
        "schema": "mastermind.runtime_read_observation.v1", "state": "SAME",
        "source_identity": "runtime_fixture_123456", "before": 7, "after": 7,
    }
    args["fabric_view"]["runtime"]["acquisition"] = {
        "schema": "mastermind.fabric_runtime_acquisition.v1",
        "owner": "executive_runtime",
        "query": {"kind": "root_detail", "root_job_id": args["root_job_id"]},
        "snapshot_digest": "c" * 64,
        "generation": copy.deepcopy(generation),
        "truncation": {"jobs": False, "attempt_job_ids": [], "roots": False, "projection": False},
        "provenance": {"state": "COMPLETE", "unjoined_job_ids": []},
    }
    args["owner_observation"] = {
        "schema": "mastermind.workspace_source_observation.v1", "state": "SAME",
        "selection": {"work_ref": args["work_ref"], "root_job_id": args["root_job_id"]},
        "control_room": {
            "instance_before": "control_fixture_123456", "instance_after": "control_fixture_123456",
            "publication_before": 1, "publication_after": 1,
            "document_digest": digest(args["control_room"]),
            "source_validity_digest": digest(args["source_validity"]),
            "cache_currentness_digest": digest(args["cache_currentness"]),
        },
        "runtime": dict(generation, snapshot_digest="c" * 64),
    }
    return args


def _refresh_observation_digests(args):
    import hashlib
    for name, key in (("control_room", "document_digest"), ("source_validity", "source_validity_digest"), ("cache_currentness", "cache_currentness_digest")):
        args["owner_observation"]["control_room"][key] = hashlib.sha256(json.dumps(
            args[name], sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode()).hexdigest()


def test_v2_bound_owner_observation_makes_current_reachable_without_acceptance():
    args = _owner_observation_inputs()
    before = copy.deepcopy(args)
    doc = compose_mission_workspace_v2(**args)
    assert args == before
    assert doc["read_state"]["state"] == "CURRENT"
    assert doc["source"]["owner_observation"] == args["owner_observation"]
    assert doc["execution"]["state"] == "COMPLETED"
    assert doc["acceptance"]["state"] == "NOT_PROJECTED"
    assert not any(f["target_field"] == "source.generation_vector" for f in doc["missingness"])


@pytest.mark.parametrize("branch,field,value", [
    (None, "schema", "foreign"), (None, "state", []), (None, "extra", "private data"),
    ("selection", "root_job_id", "JOB-OTHER"), ("selection", "work_ref", "WS:OTHER"),
    ("selection", "extra", True),
    ("control_room", "instance_after", "different_instance_123456"),
    ("control_room", "publication_after", 2), ("control_room", "publication_before", True),
    ("control_room", "document_digest", "d" * 64),
    ("control_room", "source_validity_digest", "d" * 64),
    ("control_room", "cache_currentness_digest", "d" * 64),
    ("control_room", "instance_before", "/private/host/path"),
    ("control_room", "extra", True),
    ("runtime", "schema", "foreign"), ("runtime", "state", "UNKNOWN"),
    ("runtime", "before", True), ("runtime", "after", 8),
    ("runtime", "source_identity", "different_runtime_123456"),
    ("runtime", "source_identity", "sk-secret-token-123456789"),
    ("runtime", "snapshot_digest", "e" * 64), ("runtime", "extra", True),
])
def test_v2_owner_receipt_each_mismatch_refuses_current(branch, field, value):
    args = _owner_observation_inputs()
    target = args["owner_observation"] if branch is None else args["owner_observation"][branch]
    target[field] = value
    doc = compose_mission_workspace_v2(**args)
    assert doc["read_state"]["state"] != "CURRENT"
    assert doc["source"]["owner_observation"]["state"] == "UNKNOWN"
    assert "private data" not in json.dumps(doc)
    assert "sk-secret-token" not in json.dumps(doc)


@pytest.mark.parametrize("branch", ["runtime", "control_room"])
def test_v2_same_requires_both_owner_components(branch):
    args = _owner_observation_inputs()
    args["owner_observation"][branch] = None
    assert compose_mission_workspace_v2(**args)["read_state"]["state"] == "PARTIAL"


@pytest.mark.parametrize("mutation", [
    lambda a: a["fabric_view"]["runtime"].pop("acquisition"),
    lambda a: a["fabric_view"]["runtime"]["acquisition"].update(schema="foreign"),
    lambda a: a["fabric_view"]["runtime"]["acquisition"].update(owner="viewer"),
    lambda a: a["fabric_view"]["runtime"]["acquisition"].update(query={"kind": "root_discovery", "root_job_id": "JOB-1"}),
    lambda a: a["fabric_view"]["runtime"]["acquisition"].update(snapshot_digest="d" * 64),
    lambda a: a["fabric_view"]["runtime"]["acquisition"].pop("generation"),
    lambda a: a["fabric_view"]["runtime"]["acquisition"]["generation"].update(state="UNKNOWN"),
    lambda a: a["fabric_view"]["runtime"]["acquisition"]["generation"].update(before=True, after=True),
    lambda a: a["fabric_view"].update(generated_at=None),
])
def test_v2_owner_receipt_requires_actual_fabric_acquisition_binding(mutation):
    args = _owner_observation_inputs()
    mutation(args)
    assert compose_mission_workspace_v2(**args)["read_state"]["state"] == "PARTIAL"


def test_v2_fresh_digests_do_not_override_expired_existing_validity():
    args = _owner_observation_inputs()
    args["source_validity"]["cards"][0]["components"]["dispatch"].update(remaining_ms=0, state="expired")
    _refresh_observation_digests(args)
    assert compose_mission_workspace_v2(**args)["read_state"]["state"] == "PARTIAL"


def test_v2_changed_input_invalidates_receipt_even_when_schema_is_valid():
    args = _owner_observation_inputs()
    args["control_room"]["work"][0]["agent_os"]["title"] = "Changed after observation"
    doc = compose_mission_workspace_v2(**args)
    assert doc["read_state"]["state"] == "PARTIAL"
    assert doc["source"]["owner_observation"]["state"] == "UNKNOWN"


@pytest.mark.parametrize("owner", ["runtime", "control_room"])
def test_v2_real_owner_conflict_is_preserved_in_conflict_posture(owner):
    args = _owner_observation_inputs()
    args["owner_observation"]["state"] = "CONFLICT"
    if owner == "runtime":
        args["owner_observation"]["runtime"].update(state="CONFLICT", after=8)
    else:
        args["owner_observation"]["control_room"]["instance_after"] = "new_instance_123456789"
    doc = compose_mission_workspace_v2(**args)
    assert doc["source"]["owner_observation"]["state"] == "CONFLICT"
    assert doc["read_state"]["state"] == "PARTIAL"
    assert doc["posture"]["value"] == "RECONCILIATION_REQUIRED"


@pytest.mark.parametrize("state", ["STALE", "CONFLICT"])
def test_v2_owner_same_does_not_override_existing_generation_diagnostic_conflict(state):
    args = _owner_observation_inputs()
    args["source_generation"] = {"state": state, "version": 1, "generation": 3}
    assert compose_mission_workspace_v2(**args)["read_state"]["state"] == "PARTIAL"


def test_v2_unknown_receipt_cannot_hide_or_upgrade_missingness():
    args = _owner_observation_inputs()
    args["owner_observation"]["state"] = "UNKNOWN"
    doc = compose_mission_workspace_v2(**args)
    assert doc["source"]["owner_observation"]["state"] == "UNKNOWN"
    assert doc["read_state"]["state"] == "PARTIAL"
    assert any(f["target_field"] == "source.generation_vector" for f in doc["missingness"])


def test_v2_source_currentness_and_child_completeness_remain_distinct():
    args = _owner_observation_inputs()
    args["fabric_view"].update(unjoined_job_count=1, unjoined_job_ids=["JOB-CHILD"])
    args["fabric_view"]["runtime"]["acquisition"]["provenance"].update(state="PARTIAL", unjoined_job_ids=["JOB-CHILD"])
    doc = compose_mission_workspace_v2(**args)
    assert doc["read_state"]["state"] == "CURRENT"
    assert doc["children"]["coverage"] == "INCOMPLETE"
    assert doc["children"]["unjoined_job_count"] == 1
    assert doc["acceptance"]["state"] == "NOT_PROJECTED"


def test_v2_real_fabric_without_finalized_owner_generation_cannot_be_promoted(tmp_path):
    from control_plane.executive_runtime import Runtime
    from control_plane.fabric_job_view import read_fabric_view_v2

    runtime = Runtime.at(tmp_path)
    job = runtime.jobs.create_job("Bounded producer composition fixture")
    fabric = read_fabric_view_v2(tmp_path, job.job_id)
    args = _owner_observation_inputs()
    args["fabric_view"] = fabric
    args["root_job_id"] = job.job_id
    args["owner_observation"]["selection"]["root_job_id"] = job.job_id
    responsibility = args["control_room"]["autonomy"]["responsibilities"][0]
    responsibility.update(root_job_id=job.job_id, root_job_candidates=[job.job_id])
    args["source_validity"]["cards"][0]["root_job_id"] = job.job_id
    _refresh_observation_digests(args)
    doc = compose_mission_workspace_v2(**args)
    assert doc["mission"]["root_job_id"] == job.job_id
    assert doc["read_state"]["state"] == "PARTIAL"
    assert doc["source"]["owner_observation"]["state"] == "UNKNOWN"


@pytest.mark.parametrize("historical", [True, None, 0, "false"])
def test_v2_same_owner_receipt_requires_exact_nonhistorical_dispatch(historical):
    args = _owner_observation_inputs()
    args["control_room"]["autonomy"]["responsibilities"][0]["dispatch"]["historical"] = historical
    _refresh_observation_digests(args)
    doc = compose_mission_workspace_v2(**args)
    assert doc["source"]["owner_observation"]["state"] == "SAME"
    assert doc["read_state"]["state"] == "PARTIAL"
    assert doc["posture"]["value"] == "CONSUMPTION_UNKNOWN"
