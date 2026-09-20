"""Contract tests for the pure, held mission-workspace reducer."""

from __future__ import annotations

import ast
import copy
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from control_plane.fabric_job_view import compose_fabric_view
from control_plane.mission_workspace import (
    ACCEPTANCE_KEYS,
    ARM_OUTPUT_KEYS,
    ATTEMPT_KEYS,
    CAPABILITY_KEYS,
    CARRIER_KEYS,
    CHILD_ITEM_KEYS,
    CHILDREN_KEYS,
    COVERAGE_STATES,
    DISPATCH_STATES,
    EVIDENCE_FRESHNESS_STATES,
    EVIDENCE_KEYS,
    EVIDENCE_OWNERS,
    EXECUTION_KEYS,
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
    SECTION_KEYS,
    SECTION_STATES,
    SOURCE_KEYS,
    SOURCE_GENERATION_KEYS,
    SOURCE_ROW_STATES,
    TRANSPORT_KEYS,
    W3C_KEYS,
    W3C_RECEIPT_KEYS,
    _posture,
    compose_mission_workspace,
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
        "source_generation": {},
    }


def _compose(**changes):
    inputs = _inputs()
    inputs.update(changes)
    return compose_mission_workspace(**inputs)


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
    assert document["posture"] == {"value": "RUNNING", "rule": "G1", "evidence": []}
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


def test_real_b5_server_fixture_and_real_fabric_composer_reduce_current_root(tmp_path, monkeypatch):
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
        source_generation={},
    )

    assert "qualification_generation" not in envelope["source_validity"]
    assert document["read_state"]["state"] == "CURRENT"
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


def test_decision_current_is_admitted_but_is_not_a_mission_currentness_gate():
    args = _inputs()
    args["source_validity"]["cards"][0]["components"]["decision_current"].update(
        state="expired", remaining_ms=0
    )
    args["control_room"]["autonomy"]["responsibilities"][0]["validity"]["decision_current"].update(
        valid_for_ms=0
    )
    assert compose_mission_workspace(**args)["read_state"]["state"] == "CURRENT"


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
        "value": "REVIEWED_NOT_ACCEPTED", "rule": "F5", "evidence": [],
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
