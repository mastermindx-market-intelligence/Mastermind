"""Truth-rule matrix for the workspace work-queue projection (parent ruling 5805095742).

Encodes R1-R8 plus the byte-identity and closed-key-set assertions.  Pure
projection — no I/O, no clock beyond the injected ``generated_at``.
"""
from __future__ import annotations

from collections.abc import Mapping
import json

import pytest

from control_plane.executive_runtime import JobStatus
from control_plane.work_queue_projection import (
    ACCEPTANCE_KEYS,
    COVERAGE_KEYS,
    OUTPUT_KEYS,
    ROW_KEYS,
    WORK_QUEUE_SCHEMA,
    _GROUP_ORDER,
    compose_work_queue_v1,
)
from common.executive_workspace_contract import canonical, digest


# ---------------------------------------------------------------------------
# deterministic root-list factory
# ---------------------------------------------------------------------------


def _acquisition(*, generation_state="SAME", provenance_state="COMPLETE",
                 truncated=False):
    return {
        "schema": "mastermind.fabric_runtime_acquisition.v1",
        "query": {"kind": "root_discovery"},
        "owner": "executive_runtime",
        "snapshot_digest": "a" * 64,
        "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                    "attempts_total": 340, "creation_events_per_job": 1},
        "truncation": {"jobs": False, "attempt_job_ids": [], "roots": truncated,
                        "projection": False},
        "provenance": {"state": provenance_state, "unjoined_job_ids": []},
        "generation": {"schema": "mastermind.runtime_read_observation.v1",
                       "state": generation_state, "source_identity": "b" * 64,
                       "before": 1, "after": 1},
    }


def _root_list(*, roots=(), count=None, total=None, truncated=False,
               degraded=(), db_present=True, generation_state="SAME",
               provenance_state="COMPLETE"):
    rows = list(roots)
    return {
        "schema": "mastermind.fabric_job_root_list.v2",
        "generated_at": "2026-09-23T00:00:00Z",
        "runtime": {
            "root": "/tmp/fake",
            "db_present": db_present,
            "identity": None,
            "acquisition": _acquisition(generation_state=generation_state,
                                        provenance_state=provenance_state,
                                        truncated=truncated),
        },
        "roots": rows,
        "count": count if count is not None else len(rows),
        "total": total if total is not None else (None if truncated else len(rows)),
        "truncated": truncated,
        "degraded": list(degraded),
    }


def _row(job_id, status, *, depth=0, role="aggregation"):
    return {"job_id": job_id, "status": status, "depth": depth,
            "parent_job_id": None, "orchestration_role": role}


# ---------------------------------------------------------------------------
# R1 — lifecycle unavailable
# ---------------------------------------------------------------------------


def test_r1_db_absent_renders_unavailable_with_empty_groups():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")], db_present=False)
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "UNAVAILABLE"
    assert result["reason_codes"] == ["LIFECYCLE_UNAVAILABLE"]
    assert all(len(rows) == 0 for rows in result["groups"].values())
    # All nine groups present, even when empty.
    assert set(result["groups"]) == set(_GROUP_ORDER)


def test_r1_degraded_bounded_acquisition_renders_unavailable():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")],
                           degraded=["bounded acquisition unavailable: read failed"])
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "UNAVAILABLE"
    assert result["reason_codes"] == ["LIFECYCLE_UNAVAILABLE"]
    assert all(len(rows) == 0 for rows in result["groups"].values())


def test_r1_generation_unknown_renders_unavailable():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")],
                           generation_state="UNKNOWN")
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "UNAVAILABLE"
    assert result["reason_codes"] == ["LIFECYCLE_UNAVAILABLE"]


def test_r1_unavailable_is_distinct_from_empty_available():
    """AVAILABLE with zero rows is a healthy empty, never UNAVAILABLE."""
    root_list = _root_list(roots=[], count=0, total=0)
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "AVAILABLE"
    assert result["reason_codes"] == []
    assert all(len(rows) == 0 for rows in result["groups"].values())


# ---------------------------------------------------------------------------
# R2 — next_actor only from explicit Agent OS accountability
# ---------------------------------------------------------------------------


def test_r2_next_actor_unknown_without_accountability():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    result = compose_work_queue_v1(root_list, accountability=None)
    na = result["groups"]["QUEUED"][0]["next_actor"]
    assert na == {"value": "UNKNOWN", "source": "AGENT_OS", "reason": "no_producer"}


def test_r2_next_actor_needs_sol_with_accountability():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    accountability = {"JOB-1": {"next_actor": "SOL",
                                "evidence_ref": "agent-os:sol",
                                "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, accountability=accountability)
    na = result["groups"]["NEEDS_SOL"][0]["next_actor"]
    assert na == {"value": "NEEDS_SOL", "source": "AGENT_OS", "reason": "evidence_supplied"}


def test_r2_next_actor_needs_worker_with_accountability():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    accountability = {"JOB-1": {"next_actor": "WORKER",
                                "evidence_ref": "agent-os:wrk",
                                "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, accountability=accountability)
    na = result["groups"]["NEEDS_WORKER"][0]["next_actor"]
    assert na == {"value": "NEEDS_WORKER", "source": "AGENT_OS", "reason": "evidence_supplied"}


# ---------------------------------------------------------------------------
# R3 — capacity WAITING_CAPACITY only when pre-START AND placement evidence
# ---------------------------------------------------------------------------


def test_r3_capacity_unknown_without_placement():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    result = compose_work_queue_v1(root_list)
    cap = result["groups"]["QUEUED"][0]["capacity"]
    assert cap == {"value": "UNKNOWN", "source": "AUTONOMY", "reason": "no_producer"}


def test_r3_capacity_waiting_capacity_only_when_prestart_with_placement():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    placement = {"JOB-1": {"state": "WAITING",
                           "evidence_ref": "autonomy:placement",
                           "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, placement=placement)
    assert len(result["groups"]["WAITING_CAPACITY"]) == 1
    cap = result["groups"]["WAITING_CAPACITY"][0]["capacity"]
    assert cap["value"] == "WAITING_CAPACITY"


def test_r3_capacity_not_applicable_post_start():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    placement = {"JOB-1": {"state": "WAITING",
                           "evidence_ref": "autonomy:placement",
                           "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, placement=placement)
    cap = result["groups"]["RUNNING"][0]["capacity"]
    assert cap == {"value": "NOT_APPLICABLE", "source": "AUTONOMY",
                   "reason": "post_start_lifecycle"}


# ---------------------------------------------------------------------------
# R4 — effect_exception sticky + queue-level effect_exception
# ---------------------------------------------------------------------------


def test_r4_effect_unknown_sticky_overrides_lifecycle_to_effect_exception():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    effects = {"JOB-1": {"state": "EFFECT_UNKNOWN", "carrier": "agent-os:effect"}}
    result = compose_work_queue_v1(root_list, effects=effects)
    assert len(result["groups"]["EFFECT_EXCEPTION"]) == 1
    # never lands in WAITING_CAPACITY even with placement evidence
    placement = {"JOB-1": {"state": "WAITING",
                           "evidence_ref": "autonomy:placement",
                           "observed_at": "2026-09-23T00:00:00Z"}}
    result2 = compose_work_queue_v1(root_list, placement=placement, effects=effects)
    assert len(result2["groups"]["EFFECT_EXCEPTION"]) == 1
    assert len(result2["groups"]["WAITING_CAPACITY"]) == 0
    assert len(result2["groups"]["RUNNING"]) == 0


def test_r4_effect_unknown_unknown_without_input():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    eff = result["groups"]["RUNNING"][0]["effect"]
    assert eff == {"value": "UNKNOWN", "source": "EFFECT_PRODUCER",
                   "reason": "no_producer"}


def test_r4_queue_level_effect_exception_from_control_room_autonomy():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    control_room = {
        "schema": "mastermind.chairman_control_room.v1",
        "generated_at": "2026-09-23T00:00:00Z",
        "autonomy": {
            "schema": "mastermind.autonomy_control_room.v1",
            "generated_at": "2026-09-23T00:00:00Z",
            "responsibilities": [
                {"responsibility_ref": "WS:ONE", "root_job_id": "JOB-1",
                 "placement_state": {"value": "EFFECT_UNKNOWN",
                                     "observable": True, "reason": "x"}},
            ],
        },
    }
    result = compose_work_queue_v1(root_list, control_room=control_room)
    assert result["effect_exception"] == {
        "value": "EFFECT_UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER", "observable": True,
    }


def test_r4_queue_level_effect_exception_none_when_no_placement_match():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    control_room = {
        "schema": "mastermind.chairman_control_room.v1",
        "generated_at": "2026-09-23T00:00:00Z",
        "autonomy": {
            "schema": "mastermind.autonomy_control_room.v1",
            "generated_at": "2026-09-23T00:00:00Z",
            "responsibilities": [
                {"responsibility_ref": "WS:ONE", "root_job_id": "JOB-1",
                 "placement_state": {"value": "WAITING_CAPACITY",
                                     "observable": True, "reason": "x"}},
            ],
        },
    }
    result = compose_work_queue_v1(root_list, control_room=control_room)
    assert result["effect_exception"] == {
        "value": "NONE", "scope": "RUNTIME_CURRENT_WORKER", "observable": False,
    }


def test_r4_queue_level_effect_exception_unknown_when_control_room_none():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    result = compose_work_queue_v1(root_list, control_room=None)
    assert result["effect_exception"] == {
        "value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER", "observable": False,
    }


def test_r4_queue_level_effect_exception_unknown_when_autonomy_missing():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    control_room = {"schema": "mastermind.chairman_control_room.v1",
                    "generated_at": "2026-09-23T00:00:00Z"}
    result = compose_work_queue_v1(root_list, control_room=control_room)
    assert result["effect_exception"]["value"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# R5 — acceptance is ALWAYS NOT_PROJECTED; COMPLETED → COMPLETED_NOT_ACCEPTED
# ---------------------------------------------------------------------------


def test_r5_acceptance_always_not_projected_for_running():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    acc = result["groups"]["RUNNING"][0]["acceptance"]
    assert acc == {"state": "NOT_PROJECTED", "producer_owner": None,
                   "reason": "product acceptance has no producer in this projection"}


def test_r5_completed_lifecycle_maps_to_completed_not_accepted_not_accepted():
    root_list = _root_list(roots=[_row("JOB-1", "COMPLETED")])
    result = compose_work_queue_v1(root_list)
    assert len(result["groups"]["COMPLETED_NOT_ACCEPTED"]) == 1
    assert len(result["groups"].get("ACCEPTED", [])) == 0


# ---------------------------------------------------------------------------
# R6 — deterministic ordering and idempotent bytes
# ---------------------------------------------------------------------------


def test_r6_groups_are_fixed_order_and_every_group_present():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    assert list(result["groups"].keys()) == list(_GROUP_ORDER)
    assert set(result["groups"]) == set(_GROUP_ORDER)


def test_r6_rows_sorted_by_root_job_id_within_group():
    root_list = _root_list(roots=[
        _row("JOB-3", "RUNNING"), _row("JOB-1", "RUNNING"), _row("JOB-2", "RUNNING"),
    ])
    result = compose_work_queue_v1(root_list)
    ids = [row["root_job_id"] for row in result["groups"]["RUNNING"]]
    assert ids == ["JOB-1", "JOB-2", "JOB-3"]


def test_r6_composing_twice_yields_byte_identical_canonical_json():
    root_list = _root_list(roots=[
        _row("JOB-1", "QUEUED"), _row("JOB-2", "RUNNING"),
        _row("JOB-3", "COMPLETED"), _row("JOB-4", "FAILED"),
    ])
    first = compose_work_queue_v1(root_list, generated_at="2026-09-23T00:00:00Z")
    second = compose_work_queue_v1(root_list, generated_at="2026-09-23T00:00:00Z")
    assert canonical(first) == canonical(second)


def test_r6_bytes_match_deterministic_fixture():
    """Sanity-check the fixture compared to a recompose."""
    from pathlib import Path
    fixture_path = Path(__file__).parent / "fixtures" / "workspace_work_queue_v1" / "available.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    generated_at = fixture["generated_at"]
    root_list = _root_list(
        roots=[_row(row["root_job_id"], row["lifecycle"]["status"],
                    depth=row["lifecycle"]["depth"],
                    role=row["lifecycle"]["orchestration_role"])
               for row in fixture["groups"]["QUEUED"] + fixture["groups"]["RUNNING"]
               + fixture["groups"]["COMPLETED_NOT_ACCEPTED"] + fixture["groups"]["TERMINAL"]],
        total=4,
    )
    recomposed = compose_work_queue_v1(root_list, generated_at=generated_at)
    assert canonical(fixture) == canonical(recomposed)


# ---------------------------------------------------------------------------
# R7 — coverage explicit and PARTIAL when truncated or PARTIAL provenance
# ---------------------------------------------------------------------------


def test_r7_total_null_when_truncated():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")], truncated=True,
                           total=None, count=1)
    result = compose_work_queue_v1(root_list)
    assert result["coverage"]["truncated"] is True
    assert result["coverage"]["total"] is None
    assert result["coverage"]["completeness"] == "PARTIAL"


def test_r7_complete_when_not_truncated_and_complete_provenance():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    assert result["coverage"]["truncated"] is False
    assert result["coverage"]["total"] == 1
    assert result["coverage"]["completeness"] == "COMPLETE"


def test_r7_partial_when_provenance_partial():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")],
                           provenance_state="PARTIAL")
    result = compose_work_queue_v1(root_list)
    assert result["coverage"]["completeness"] == "PARTIAL"


# ---------------------------------------------------------------------------
# R8 — every JobStatus member mapped explicitly
# ---------------------------------------------------------------------------


def test_r8_every_jobstatus_member_is_mapped_explicitly():
    """The closed lifecycle→group table must cover every enum member."""
    from control_plane.work_queue_projection import _JOB_STATUS_GROUPS
    members = [member.value for s in JobStatus for member in [s]]
    assert set(_JOB_STATUS_GROUPS) == set(members)
    expected = {
        "QUEUED": "QUEUED",
        "RUNNING": "RUNNING",
        "CHECKPOINTED": "RUNNING",
        "RATE_LIMITED": "RUNNING",
        "CANCEL_REQUESTED": "RUNNING",
        "COMPLETED": "COMPLETED_NOT_ACCEPTED",
        "FAILED": "TERMINAL",
        "LOST": "TERMINAL",
        "CANCELLED": "TERMINAL",
    }
    assert _JOB_STATUS_GROUPS == expected


def test_r8_unknown_status_falls_through_to_unknown_group():
    """Anything outside the table → UNKNOWN (defensive fallback)."""
    root_list = _root_list(roots=[_row("JOB-1", "SOMETHING_NEW")])
    result = compose_work_queue_v1(root_list)
    assert len(result["groups"]["UNKNOWN"]) == 1


# ---------------------------------------------------------------------------
# shape validation — closed key sets, malformed input
# ---------------------------------------------------------------------------


def test_document_has_closed_top_level_keys():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    assert set(result) == OUTPUT_KEYS


def test_row_has_closed_keys():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    row = result["groups"]["RUNNING"][0]
    assert set(row) == ROW_KEYS


def test_coverage_has_closed_keys():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    assert set(result["coverage"]) == COVERAGE_KEYS


def test_acceptance_column_matches_frozen_vocabulary():
    root_list = _root_list(roots=[_row("JOB-1", "COMPLETED")])
    result = compose_work_queue_v1(root_list)
    acc = result["groups"]["COMPLETED_NOT_ACCEPTED"][0]["acceptance"]
    assert set(acc) == ACCEPTANCE_KEYS


@pytest.mark.parametrize("mutation", [
    "schema", "missing_root", "extra_root", "bad_runtime", "bad_acquisition",
    "bad_row", "bad_total", "bad_truncated", "bad_degraded",
])
def test_malformed_root_list_raises_value_error(mutation):
    base = _root_list(roots=[_row("JOB-1", "RUNNING")])
    if mutation == "schema":
        base["schema"] = "mastermind.fabric_job_root_list.v1"
    elif mutation == "missing_root":
        del base["roots"]
    elif mutation == "extra_root":
        base["forbidden"] = True
    elif mutation == "bad_runtime":
        del base["runtime"]["db_present"]
    elif mutation == "bad_acquisition":
        del base["runtime"]["acquisition"]["generation"]
    elif mutation == "bad_row":
        base["roots"][0]["status"] = 7  # not a str
    elif mutation == "bad_total":
        base["total"] = -3
    elif mutation == "bad_truncated":
        base["truncated"] = "yes"
    elif mutation == "bad_degraded":
        base["degraded"] = [42]
    with pytest.raises(ValueError):
        compose_work_queue_v1(base)


# ---------------------------------------------------------------------------
# source_observation attach point — the read service passes it through
# ---------------------------------------------------------------------------


def test_source_observation_can_be_attached_unchanged():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    observation = {"schema": "mastermind.workspace_source_observation.v1",
                   "state": "SAME", "selection": None,
                   "control_room": {"instance_before": "x" * 64,
                                    "instance_after": "x" * 64,
                                    "publication_before": 1, "publication_after": 1,
                                    "document_digest": "d" * 64,
                                    "source_validity_digest": "d" * 64,
                                    "cache_currentness_digest": "d" * 64},
                   "runtime": {"state": "SAME", "source_identity": "b" * 64,
                               "before": 1, "after": 1,
                               "snapshot_digest": "a" * 64}}
    result = compose_work_queue_v1(root_list, source_observation=observation)
    assert result["source_observation"] == observation


# ---------------------------------------------------------------------------
# sanity — composition deterministic across shuffle of input rows
# ---------------------------------------------------------------------------


def test_composition_is_input_order_independent():
    a = _root_list(roots=[_row("JOB-1", "RUNNING"), _row("JOB-2", "QUEUED"),
                          _row("JOB-3", "COMPLETED")])
    b = _root_list(roots=[_row("JOB-3", "COMPLETED"), _row("JOB-1", "RUNNING"),
                          _row("JOB-2", "QUEUED")])
    left = compose_work_queue_v1(a, generated_at="2026-09-23T00:00:00Z")
    right = compose_work_queue_v1(b, generated_at="2026-09-23T00:00:00Z")
    assert canonical(left) == canonical(right)