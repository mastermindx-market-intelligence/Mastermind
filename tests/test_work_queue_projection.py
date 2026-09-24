"""Truth-rule matrix for the workspace work-queue projection (parent ruling 5805095742).

Encodes R1-R8 plus the byte-identity and closed-key-set assertions.  Pure
projection — no I/O, no clock beyond the injected ``generated_at``.
"""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
import json

import pytest

from control_plane.executive_runtime import JobStatus
from control_plane.fabric_job_view import (
    _BOUNDED_UNAVAILABLE_NOTE,
    _GENERATION_CONFLICT_NOTE,
    _ROOT_ENUMERATION_NOTE,
)
from control_plane.work_queue_projection import (
    ACCEPTANCE_KEYS,
    COVERAGE_KEYS,
    OUTPUT_KEYS,
    ROW_KEYS,
    WORK_QUEUE_SCHEMA,
    _DEGRADATION_NOTES,
    _GROUP_ORDER,
    _is_degradation_note,
    _JOB_STATUS_GROUPS,
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
                           degraded=[_BOUNDED_UNAVAILABLE_NOTE])
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
    assert na == {"value": "UNKNOWN", "source": None, "reason": "no_producer",
                  "evidence_ref": None, "observed_at": None}


def test_r2_next_actor_needs_sol_with_accountability():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    accountability = {"JOB-1": {"next_actor": "SOL",
                                "evidence_ref": "agent-os:sol",
                                "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, accountability=accountability,
                                   evidence_as_of="2026-09-23T00:01:00Z")
    na = result["groups"]["NEEDS_SOL"][0]["next_actor"]
    assert na == {"value": "NEEDS_SOL", "source": "AGENT_OS", "reason": "evidence_supplied",
                  "evidence_ref": "agent-os:sol", "observed_at": "2026-09-23T00:00:00Z"}


def test_r2_next_actor_needs_worker_with_accountability():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    accountability = {"JOB-1": {"next_actor": "WORKER",
                                "evidence_ref": "agent-os:wrk",
                                "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, accountability=accountability,
                                   evidence_as_of="2026-09-23T00:01:00Z")
    na = result["groups"]["NEEDS_WORKER"][0]["next_actor"]
    assert na == {"value": "NEEDS_WORKER", "source": "AGENT_OS", "reason": "evidence_supplied",
                  "evidence_ref": "agent-os:wrk", "observed_at": "2026-09-23T00:00:00Z"}


# ---------------------------------------------------------------------------
# R3 — capacity WAITING_CAPACITY only when pre-START AND placement evidence
# ---------------------------------------------------------------------------


def test_r3_capacity_unknown_without_placement():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    result = compose_work_queue_v1(root_list)
    cap = result["groups"]["QUEUED"][0]["capacity"]
    assert cap == {"value": "UNKNOWN", "source": None, "reason": "no_producer",
                   "evidence_ref": None, "observed_at": None}


def test_r3_capacity_waiting_capacity_only_when_prestart_with_placement():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    placement = {"JOB-1": {"state": "WAITING",
                           "evidence_ref": "autonomy:placement",
                           "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, placement=placement,
                                   evidence_as_of="2026-09-23T00:01:00Z")
    assert len(result["groups"]["WAITING_CAPACITY"]) == 1
    cap = result["groups"]["WAITING_CAPACITY"][0]["capacity"]
    assert cap["value"] == "WAITING_CAPACITY"
    assert cap["source"] == "AUTONOMY"
    assert cap["reason"] == "pre_start_placement_evidence"
    assert cap["evidence_ref"] == "autonomy:placement"
    assert cap["observed_at"] == "2026-09-23T00:00:00Z"


def test_r3_capacity_not_applicable_post_start():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    placement = {"JOB-1": {"state": "WAITING",
                           "evidence_ref": "autonomy:placement",
                           "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, placement=placement,
                                   evidence_as_of="2026-09-23T00:01:00Z")
    cap = result["groups"]["RUNNING"][0]["capacity"]
    assert cap == {"value": "NOT_APPLICABLE", "source": "EXECUTIVE_RUNTIME",
                   "reason": "post_start_lifecycle",
                   "evidence_ref": None, "observed_at": None}


# ---------------------------------------------------------------------------
# R4 — effect_exception sticky + queue-level effect_exception
# ---------------------------------------------------------------------------


def test_r4_effect_unknown_sticky_overrides_lifecycle_to_effect_exception():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    effects = {"JOB-1": {"state": "EFFECT_UNKNOWN", "carrier": "agent-os:effect",
                         "evidence_ref": "agent-os:effect",
                         "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, effects=effects,
                                   evidence_as_of="2026-09-23T00:01:00Z")
    assert len(result["groups"]["EFFECT_EXCEPTION"]) == 1
    # never lands in WAITING_CAPACITY even with placement evidence
    placement = {"JOB-1": {"state": "WAITING",
                           "evidence_ref": "autonomy:placement",
                           "observed_at": "2026-09-23T00:00:00Z"}}
    result2 = compose_work_queue_v1(root_list, placement=placement, effects=effects,
                                    evidence_as_of="2026-09-23T00:01:00Z")
    assert len(result2["groups"]["EFFECT_EXCEPTION"]) == 1
    assert len(result2["groups"]["WAITING_CAPACITY"]) == 0
    assert len(result2["groups"]["RUNNING"]) == 0


def test_r4_effect_unknown_unknown_without_input():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    eff = result["groups"]["RUNNING"][0]["effect"]
    assert eff == {"value": "UNKNOWN", "source": None,
                   "reason": "no_producer",
                   "evidence_ref": None, "observed_at": None}


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
        "value": "EFFECT_UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER",
        "observable": True, "reason": "exception_observed",
    }
    # B3: with no effects map, the queue-level exception is unattributed;
    # the document must surface that as a reason code.
    assert result["reason_codes"] == ["effect_not_row_attributed"]


def test_r4_effect_not_row_attributed_reason_absent_when_effects_map_present():
    """B3: when a per-row effects map is supplied, the queue-level
    EFFECT_UNKNOWN IS attributed — the reason code is NOT appended."""
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
    effects = {"JOB-1": {"state": "EFFECT_UNKNOWN", "carrier": "agent-os:effect",
                         "evidence_ref": "agent-os:effect",
                         "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, control_room=control_room,
                                   effects=effects,
                                   evidence_as_of="2026-09-23T00:01:00Z")
    assert "effect_not_row_attributed" not in result["reason_codes"]


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
        "value": "NONE", "scope": "RUNTIME_CURRENT_WORKER",
        "observable": False, "reason": "no_exception_observed",
    }


def test_r4_queue_level_effect_exception_unknown_when_control_room_none():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    result = compose_work_queue_v1(root_list, control_room=None)
    assert result["effect_exception"] == {
        "value": "UNKNOWN", "scope": "RUNTIME_CURRENT_WORKER",
        "observable": False, "reason": "control_room_missing",
    }


def test_r4_queue_level_effect_exception_unknown_when_autonomy_missing():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    control_room = {"schema": "mastermind.chairman_control_room.v1",
                    "generated_at": "2026-09-23T00:00:00Z"}
    result = compose_work_queue_v1(root_list, control_room=control_room)
    assert result["effect_exception"]["value"] == "UNKNOWN"
    assert result["effect_exception"]["reason"] == "autonomy_missing"


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


def test_r6_bytes_match_deterministic_production_shaped_fixture():
    """N8: ``available.json`` is a PRODUCTION-SHAPED fixture (SAME
    generation + ``_ROOT_ENUMERATION_NOTE`` in ``degraded`` + PARTIAL
    provenance + ``total == 4`` as the producer would give).  Stays
    byte-identical under recompose."""
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
        provenance_state="PARTIAL",
        degraded=[_ROOT_ENUMERATION_NOTE],
    )
    # The fixture's PARTIAL provenance carries an unjoined job id; mirror it.
    root_list["runtime"]["acquisition"]["provenance"]["unjoined_job_ids"] = ["JOB-3"]
    recomposed = compose_work_queue_v1(root_list, generated_at=generated_at)
    assert canonical(fixture) == canonical(recomposed)
    # Sanity: the production-shaped fixture surfaces
    # ``coverage.completeness == "PARTIAL"`` (PARTIAL provenance) and
    # ``reason_codes == []`` (enumeration note alone never contributes).
    assert fixture["coverage"]["completeness"] == "PARTIAL"
    assert fixture["reason_codes"] == []
    assert fixture["lifecycle_source"]["degraded"] == [_ROOT_ENUMERATION_NOTE]


def test_r6_bytes_match_deterministic_available_complete_composer_only_fixture():
    """N8: ``available_complete_composer_only.json`` is the COMPOSER-ONLY
    COMPLETE-provenance fixture (no enumeration note, COMPLETE
    provenance, full universe).  Achieved only when the root list is
    hand-crafted; the live bounded acquisition always surfaces the
    enumeration note.  Stays byte-identical under recompose."""
    from pathlib import Path
    fixture_path = (Path(__file__).parent / "fixtures" / "workspace_work_queue_v1"
                    / "available_complete_composer_only.json")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    generated_at = fixture["generated_at"]
    root_list = _root_list(
        roots=[_row(row["root_job_id"], row["lifecycle"]["status"],
                    depth=row["lifecycle"]["depth"],
                    role=row["lifecycle"]["orchestration_role"])
               for row in fixture["groups"]["QUEUED"] + fixture["groups"]["RUNNING"]
               + fixture["groups"]["COMPLETED_NOT_ACCEPTED"] + fixture["groups"]["TERMINAL"]],
        total=4,
        provenance_state="COMPLETE",
        degraded=[],
    )
    recomposed = compose_work_queue_v1(root_list, generated_at=generated_at)
    assert canonical(fixture) == canonical(recomposed)
    # Sanity: the composer-only fixture renders COMPLETE coverage.
    assert fixture["coverage"]["completeness"] == "COMPLETE"
    assert fixture["reason_codes"] == []
    assert fixture["lifecycle_source"]["degraded"] == []


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


def test_r8_unknown_status_raises_value_error():
    """Anything outside the table is a closed-validator refusal (R8).

    A new enum member must NOT silently land in ``UNKNOWN`` — the
    validator raises ``ValueError`` so the route can map it to
    ``UNAVAILABLE`` rather than promote an unrecognized status.
    """
    root_list = _root_list(roots=[_row("JOB-1", "SOMETHING_NEW")])
    with pytest.raises(ValueError, match="status not mapped"):
        compose_work_queue_v1(root_list)


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


# ---------------------------------------------------------------------------
# B1 — capacity NOT_APPLICABLE for any post-START row, regardless of placement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["RUNNING", "CHECKPOINTED", "RATE_LIMITED",
                                    "CANCEL_REQUESTED", "COMPLETED", "FAILED",
                                    "LOST", "CANCELLED"])
def test_b1_post_start_capacity_not_applicable_without_placement(status):
    """B1: post-START rows are NOT_APPLICABLE regardless of placement evidence.

    The lifecycle test fires BEFORE the placement test.  A row in any
    post-START lifecycle stage can never reach ``WAITING_CAPACITY`` and
    can never be ``UNKNOWN`` from missing placement — placement is simply
    not applicable to it.
    """
    root_list = _root_list(roots=[_row("JOB-1", status)])
    result = compose_work_queue_v1(root_list)
    cap = result["groups"][_JOB_STATUS_GROUPS[status]][0]["capacity"]
    assert cap == {"value": "NOT_APPLICABLE", "source": "EXECUTIVE_RUNTIME",
                   "reason": "post_start_lifecycle",
                   "evidence_ref": None, "observed_at": None}


def test_b1_prestart_capacity_unknown_without_placement():
    """B1: a QUEUED row without placement evidence is UNKNOWN — placement
    evidence is required to land in ``WAITING_CAPACITY``, not assumed."""
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    result = compose_work_queue_v1(root_list)
    cap = result["groups"]["QUEUED"][0]["capacity"]
    assert cap == {"value": "UNKNOWN", "source": None, "reason": "no_producer",
                   "evidence_ref": None, "observed_at": None}


# ---------------------------------------------------------------------------
# B2 — UNAVAILABLE branch coverage never claims COMPLETE; identity with the
# read-service fallback (covered by an integration test in
# tests/test_workspace_read_service.py).
# ---------------------------------------------------------------------------


def test_b2_unavailable_coverage_never_claims_complete():
    """B2: degraded root list → UNAVAILABLE branch with PARTIAL coverage."""
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")],
                           degraded=[_BOUNDED_UNAVAILABLE_NOTE])
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "UNAVAILABLE"
    assert result["coverage"] == {"count": 0, "total": None,
                                  "truncated": False, "completeness": "PARTIAL"}


def test_b2_unavailable_truncated_root_list_reflects_truncated_in_coverage():
    """B2: even when the row set is empty the coverage reflects the root
    list's ``truncated`` flag — never silently coerced to False."""
    root_list = _root_list(roots=[], count=0, total=None, truncated=True,
                           degraded=[_BOUNDED_UNAVAILABLE_NOTE])
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "UNAVAILABLE"
    assert result["coverage"]["truncated"] is True
    assert result["coverage"]["completeness"] == "PARTIAL"


def test_b2_composer_unavailable_body_is_key_stable():
    """B2: the composer's UNAVAILABLE body is a closed document; every
    top-level key equals the closed :data:`OUTPUT_KEYS` set, and the
    coverage envelope matches the B2 PARTIAL claim.  Round-1 finding
    ``test_b2_composer_unavailable_body_is_key_stable is vacuous`` is
    addressed by asserting both the closed key set and the coverage
    envelope (not just that one of them happens to contain "coverage").
    """
    from control_plane.work_queue_projection import OUTPUT_KEYS
    root_list = _root_list(roots=[], count=0, total=None, truncated=False,
                           degraded=[_BOUNDED_UNAVAILABLE_NOTE])
    composer_body = compose_work_queue_v1(root_list, generated_at="FROZEN")
    assert set(composer_body) == OUTPUT_KEYS
    assert composer_body["availability"] == "UNAVAILABLE"
    assert composer_body["reason_codes"] == ["LIFECYCLE_UNAVAILABLE"]
    assert composer_body["coverage"] == {"count": 0, "total": None,
                                         "truncated": False, "completeness": "PARTIAL"}
    # Every group is an empty list (not absent) — the closed group list
    # is observed even on the UNAVAILABLE branch.
    from control_plane.work_queue_projection import _GROUP_ORDER
    assert set(composer_body["groups"]) == set(_GROUP_ORDER)
    assert all(composer_body["groups"][key] == [] for key in _GROUP_ORDER)


# ---------------------------------------------------------------------------
# B3 — evidence freshness: strict RFC3339 UTC, max-age window, evidence_as_of
#      required when any producer is non-None.
# ---------------------------------------------------------------------------


def test_b3_missing_evidence_as_of_with_non_none_producer_raises():
    """B3: a producer without ``evidence_as_of`` is a hard refusal."""
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    accountability = {"JOB-1": {"next_actor": "SOL",
                                "evidence_ref": "agent-os:sol",
                                "observed_at": "2026-09-23T00:00:00Z"}}
    with pytest.raises(ValueError, match="evidence_as_of is required"):
        compose_work_queue_v1(root_list, accountability=accountability)


@pytest.mark.parametrize("observed_at", ["yesterday", "2026-09-24T04:00:00", "",
                                          "2026-09-23T00:00:00+00:00",
                                          "2026-09-23T00:00:00.1234567Z",
                                          "2026-09-23T00:00:00Z extra",
                                          "2026-02-30T00:00:00Z",
                                          "2026-01-01T23:59:60Z"])
def test_b3_unparseable_observed_at_raises(observed_at):
    """B3/N9: every ``observed_at`` must parse as strict RFC3339 UTC.  Anything
    else is a producer refusal — the composer never silently downgrades.
    Calendar-invalid but pattern-valid values raise the module's own message
    (not strptime's text)."""
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    accountability = {"JOB-1": {"next_actor": "SOL", "evidence_ref": "x",
                                "observed_at": observed_at}}
    with pytest.raises(ValueError, match="observed_at invalid"):
        compose_work_queue_v1(root_list, accountability=accountability,
                              evidence_as_of="2026-09-23T00:01:00Z")


@pytest.mark.parametrize("evidence_as_of", ["2026-02-30T00:00:00Z",
                                            "2026-01-01T23:59:60Z",
                                            "yesterday", "2026-09-23T00:00:00+00:00"])
def test_n9_unparseable_evidence_as_of_raises(evidence_as_of):
    """N9: an unparseable ``evidence_as_of`` raises the module's own
    ``evidence_as_of invalid`` message, never ``strptime``'s text."""
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    with pytest.raises(ValueError, match="evidence_as_of invalid"):
        compose_work_queue_v1(root_list, accountability={"JOB-1": {
            "next_actor": "SOL", "evidence_ref": "x",
            "observed_at": "2026-09-23T00:00:00Z"}},
            evidence_as_of=evidence_as_of)


def test_b3_stale_observed_at_falls_back_to_unknown_for_next_actor():
    """B3: a row's ``observed_at`` older than the validity window falls back
    to UNKNOWN with reason ``evidence_stale``; the evidence_ref/observed_at
    are still carried for audit."""
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    accountability = {"JOB-1": {"next_actor": "SOL", "evidence_ref": "old-ref",
                                "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, accountability=accountability,
                                   evidence_as_of="2026-09-23T00:16:00Z")  # 16 min later
    na = result["groups"]["QUEUED"][0]["next_actor"]
    assert na == {"value": "UNKNOWN", "source": None, "reason": "evidence_stale",
                  "evidence_ref": "old-ref", "observed_at": "2026-09-23T00:00:00Z"}


def test_b3_future_observed_at_also_falls_back_to_unknown():
    """B3: an ``observed_at`` later than ``evidence_as_of`` is rejected —
    producer clocks cannot claim future facts."""
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    accountability = {"JOB-1": {"next_actor": "SOL", "evidence_ref": "future-ref",
                                "observed_at": "2026-09-23T00:00:10Z"}}
    result = compose_work_queue_v1(root_list, accountability=accountability,
                                   evidence_as_of="2026-09-23T00:00:00Z")
    na = result["groups"]["QUEUED"][0]["next_actor"]
    assert na["reason"] == "evidence_stale"
    assert na["value"] == "UNKNOWN"


def test_b3_boundary_observed_at_exactly_max_age_admitted():
    """B3: ``observed_at`` exactly at ``evidence_as_of - evidence_max_age_s``
    is admitted (inclusive boundary); the row reaches ``WAITING_CAPACITY``."""
    from control_plane.work_queue_projection import EVIDENCE_MAX_AGE_S
    placement = {"JOB-1": {"state": "WAITING", "evidence_ref": "p",
                           "observed_at": "2026-09-23T00:00:00Z"}}
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    # Use a custom max age of 60 seconds so the test is independent of
    # the module default.  observed_at + 60s = evidence_as_of is the boundary.
    result = compose_work_queue_v1(root_list, placement=placement,
                                   evidence_as_of="2026-09-23T00:01:00Z",
                                   evidence_max_age_s=60)
    assert len(result["groups"]["WAITING_CAPACITY"]) == 1
    assert EVIDENCE_MAX_AGE_S == 900  # module default unchanged


def test_b3_stale_effect_unknown_still_sticks_with_stale_reason():
    """B3 + R4: a stale EFFECT_UNKNOWN effect STILL sticks — staleness
    never clears an exception.  The reason reads ``evidence_supplied_stale``."""
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    effects = {"JOB-1": {"state": "EFFECT_UNKNOWN", "carrier": "agent-os:effect",
                         "evidence_ref": "old", "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, effects=effects,
                                   evidence_as_of="2026-09-23T00:16:00Z")
    assert len(result["groups"]["EFFECT_EXCEPTION"]) == 1
    eff = result["groups"]["EFFECT_EXCEPTION"][0]["effect"]
    assert eff == {"value": "EFFECT_UNKNOWN", "source": "EFFECT_PRODUCER",
                   "reason": "evidence_supplied_stale",
                   "evidence_ref": "old", "observed_at": "2026-09-23T00:00:00Z"}


def test_b3_stale_placement_falls_back_to_unknown_no_waiting_capacity():
    """B3: a stale placement cannot promote a QUEUED row to
    ``WAITING_CAPACITY`` — the row falls back to UNKNOWN with
    reason ``evidence_stale``."""
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    placement = {"JOB-1": {"state": "WAITING", "evidence_ref": "old-p",
                           "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, placement=placement,
                                   evidence_as_of="2026-09-23T00:16:00Z")
    assert len(result["groups"]["WAITING_CAPACITY"]) == 0
    cap = result["groups"]["QUEUED"][0]["capacity"]
    assert cap["value"] == "UNKNOWN"
    assert cap["reason"] == "evidence_stale"


def test_b3_evidence_as_of_required_with_placement():
    root_list = _root_list(roots=[_row("JOB-1", "QUEUED")])
    placement = {"JOB-1": {"state": "WAITING", "evidence_ref": "p",
                           "observed_at": "2026-09-23T00:00:00Z"}}
    with pytest.raises(ValueError, match="evidence_as_of is required"):
        compose_work_queue_v1(root_list, placement=placement)


def test_b3_evidence_as_of_required_with_effects():
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    effects = {"JOB-1": {"state": "EFFECT_UNKNOWN", "carrier": "c",
                         "evidence_ref": "e", "observed_at": "2026-09-23T00:00:00Z"}}
    with pytest.raises(ValueError, match="evidence_as_of is required"):
        compose_work_queue_v1(root_list, effects=effects)


# ---------------------------------------------------------------------------
# B4 — next_actor precedence must respect terminal/completed lifecycle groups
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["COMPLETED", "FAILED", "LOST", "CANCELLED"])
@pytest.mark.parametrize("actor", ["SOL", "WORKER"])
def test_b4_terminal_and_completed_groups_never_overridden_by_accountability(status, actor):
    """B4: when the lifecycle group is COMPLETED_NOT_ACCEPTED or TERMINAL,
    the NEEDS_SOL/NEEDS_WORKER override does NOT fire — those groups are
    terminal/completed and are decided by lifecycle alone.  The row may
    still carry the next_actor column value for audit, but its group is
    the lifecycle group."""
    root_list = _root_list(roots=[_row("JOB-1", status)])
    accountability = {"JOB-1": {"next_actor": actor, "evidence_ref": "x",
                                "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, accountability=accountability,
                                   evidence_as_of="2026-09-23T00:01:00Z")
    expected_group = _JOB_STATUS_GROUPS[status]
    assert len(result["groups"][expected_group]) == 1
    row = result["groups"][expected_group][0]
    # next_actor column still carries the producer value for audit.
    assert row["next_actor"]["value"] == f"NEEDS_{actor}"


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "CHECKPOINTED",
                                    "RATE_LIMITED", "CANCEL_REQUESTED"])
@pytest.mark.parametrize("actor", ["SOL", "WORKER"])
def test_b4_queued_and_running_groups_do_override_by_accountability(status, actor):
    """B4: when the lifecycle group is QUEUED or RUNNING, accountability
    CAN reclassify the row into NEEDS_SOL/NEEDS_WORKER."""
    root_list = _root_list(roots=[_row("JOB-1", status)])
    accountability = {"JOB-1": {"next_actor": actor, "evidence_ref": "x",
                                "observed_at": "2026-09-23T00:00:00Z"}}
    result = compose_work_queue_v1(root_list, accountability=accountability,
                                   evidence_as_of="2026-09-23T00:01:00Z")
    expected_group = f"NEEDS_{actor}"
    assert len(result["groups"][expected_group]) == 1
    row = result["groups"][expected_group][0]
    assert row["lifecycle"]["status"] == status


@pytest.mark.parametrize("status", list(_JOB_STATUS_GROUPS.keys()))
def test_b4_no_accountability_uses_lifecycle_group(status):
    """B4: without accountability the row uses its lifecycle group exactly."""
    root_list = _root_list(roots=[_row("JOB-1", status)])
    result = compose_work_queue_v1(root_list)
    expected_group = _JOB_STATUS_GROUPS[status]
    assert len(result["groups"][expected_group]) == 1
    row = result["groups"][expected_group][0]
    assert row["next_actor"]["value"] == "UNKNOWN"
    assert row["next_actor"]["source"] is None
    assert row["next_actor"]["reason"] == "no_producer"


# ---------------------------------------------------------------------------
# N6 — duplicate job_id rejection
# ---------------------------------------------------------------------------


def test_n6_duplicate_job_id_raises_value_error():
    """N6: duplicate job_id in the root list is a closed-validator refusal."""
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING"),
                                  _row("JOB-1", "QUEUED")])
    with pytest.raises(ValueError, match="duplicate job_id"):
        compose_work_queue_v1(root_list)


# ---------------------------------------------------------------------------
# N3 — lifecycle_source echoes degraded; reason code on AVAILABLE when non-empty
# ---------------------------------------------------------------------------


def test_n3_lifecycle_source_echoes_degraded_verbatim():
    """N3: the root list's degraded list is echoed verbatim in lifecycle_source."""
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")],
                           degraded=["producer warning A", "producer warning B"])
    result = compose_work_queue_v1(root_list)
    assert result["lifecycle_source"]["degraded"] == ["producer warning A",
                                                     "producer warning B"]


def test_n3_lifecycle_source_degraded_default_is_empty_list():
    """N3: a root list without degraded notes yields an empty list, not None."""
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    assert result["lifecycle_source"]["degraded"] == []


def test_n3_available_document_appends_lifecycle_degraded_reason_when_degraded():
    """N3: a non-empty degraded list on an AVAILABLE document adds the
    ``lifecycle_degraded`` reason code ONLY when the entry matches the
    closed-set degradation phrase list; an unknown producer note never
    contributes a reason code (N3 closed-set refactor)."""
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")],
                           degraded=["producer warning A"])
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "AVAILABLE"
    assert "lifecycle_degraded" not in result["reason_codes"]
    assert result["lifecycle_source"]["degraded"] == ["producer warning A"]


def test_n3_no_lifecycle_degraded_reason_when_degraded_empty():
    """N3: a healthy AVAILABLE document keeps reason_codes=[]."""
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")])
    result = compose_work_queue_v1(root_list)
    assert "lifecycle_degraded" not in result["reason_codes"]


# ---------------------------------------------------------------------------
# B1 — lifecycle_degraded is gated on a closed set of degradation phrases;
# the informational _ROOT_ENUMERATION_NOTE must never contribute a reason
# code (every bounded acquisition surfaces it, so emitting a reason code
# would render the channel non-diagnostic).
# ---------------------------------------------------------------------------


def test_b1_root_enumeration_note_alone_does_not_add_reason_code():
    """B1: the informational ``_ROOT_ENUMERATION_NOTE`` is echoed in
    ``lifecycle_source.degraded`` but never adds a ``lifecycle_degraded``
    reason code on its own."""
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")],
                           degraded=[_ROOT_ENUMERATION_NOTE])
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "AVAILABLE"
    assert result["reason_codes"] == []
    assert result["lifecycle_source"]["degraded"] == [_ROOT_ENUMERATION_NOTE]


@pytest.mark.parametrize("entry", [
    "bounded root discovery truncated; omitted roots are not counted",
    _GENERATION_CONFLICT_NOTE,
])
def test_b1_closed_set_degradation_phrases_add_reason_code(entry):
    """Item 4 / round-4 audit: every entry in the closed degradation set
    fires the ``lifecycle_degraded`` reason code on an AVAILABLE
    document.

    COMPOSER-ONLY STATE: each parametrised entry below corresponds to a
    producer note that the live pipeline cannot deliver on an AVAILABLE
    document.

    - ``"bounded root discovery truncated; ..."`` — the live bounded
      producer (``list_roots_v2_from_runtime``) flips ``truncated=True``
      AND emits this note alongside a SAME generation receipt, so the
      composer reaches the AVAILABLE branch and the reason code fires.
      This IS the live trigger.
    - ``_GENERATION_CONFLICT_NOTE`` — the producer emits this only when
      ``generation.state == "CONFLICT"``; a CONFLICT generation drives
      :func:`_lifecycle_unavailable` to refuse as UNAVAILABLE BEFORE
      the reason-code gate runs, so the AVAILABLE branch never sees it.
      The composer-only contract is preserved here so the closed set
      stays an exhaustive three-element vocabulary.

    Truncation is the only live trigger; the CONFLICT entry exists to
    keep the closed set frozen under future producer evolution.
    """
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")],
                           degraded=[entry])
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "AVAILABLE"
    assert result["reason_codes"] == ["lifecycle_degraded"]
    # Producer's degraded note is still echoed verbatim for audit.
    assert result["lifecycle_source"]["degraded"] == [entry]


def test_b1_bounded_unavailable_note_drives_unavailable_branch_via_prefix_match():
    """B1: the bounded-unavailable note is matched by ``startswith`` so
    the producer's appended detail (e.g. ``": read failed"``) keeps the
    UNAVAILABLE branch (the existing R1 behavior — the prefix phrase
    belongs to the closed degradation set AND triggers UNAVAILABLE)."""
    for entry in (_BOUNDED_UNAVAILABLE_NOTE,
                  _BOUNDED_UNAVAILABLE_NOTE + ": read failed"):
        root_list = _root_list(roots=[_row("JOB-1", "RUNNING")],
                               degraded=[entry])
        result = compose_work_queue_v1(root_list)
        assert result["availability"] == "UNAVAILABLE"
        assert result["reason_codes"] == ["LIFECYCLE_UNAVAILABLE"]
        # The producer's degraded note is still echoed verbatim for audit.
        assert result["lifecycle_source"]["degraded"] == [entry]


def test_b1_bounded_unavailable_predicate_drives_unavailable_with_arbitrary_detail():
    """Item 1 / round-4 audit: the legacy ``list_roots_v2`` producer path
    emits ``"bounded acquisition unavailable: <failure first line>"`` —
    an arbitrary detail the composer does NOT have a constant for.  The
    only stable closed-set invariant is the shared prefix
    :func:`control_plane.work_queue_projection._is_bounded_unavailable_note`,
    matched by ``startswith(_BOUNDED_UNAVAILABLE_PHRASE)``.  This test
    RED's on the previous exact-match / constant-startswith behaviour
    and GREEN's after the substring restoration.

    The test pins the new contract: any producer note that begins with
    ``"bounded acquisition unavailable"`` drives the UNAVAILABLE branch
    AND the AVAILABLE ``lifecycle_degraded`` reason code (they share
    one predicate — see also ``test_b1_bounded_unavailable_predicate_couples_lifecycle_unavailable_and_reason_gate``).
    """
    arbitrary = "bounded acquisition unavailable: disk I/O error"
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")], degraded=[arbitrary])
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "UNAVAILABLE"
    assert result["reason_codes"] == ["LIFECYCLE_UNAVAILABLE"]
    # The producer's degraded note is still echoed verbatim for audit.
    assert result["lifecycle_source"]["degraded"] == [arbitrary]


def test_b1_bounded_unavailable_predicate_couples_lifecycle_unavailable_and_reason_gate():
    """Item 2 / round-4 audit: the closed-set invariant
    "any bounded-unavailable producer note drives BOTH the UNAVAILABLE
    branch and the ``lifecycle_degraded`` reason code" was previously
    enforced by two independent inline checks (one in
    :func:`_lifecycle_unavailable`, one in :func:`_is_degradation_note`).
    The two sites now share the predicate
    :func:`_is_bounded_unavailable_note` — coupling is asserted by
    construction (both call sites import it from the same module
    location) and by example here (every member of the bounded-
    unavailable family drives BOTH the UNAVAILABLE branch on a SAME
    root list and the AVAILABLE reason code on a degraded-bounded root
    list).
    """
    from control_plane.work_queue_projection import _is_bounded_unavailable_note
    family = (
        _BOUNDED_UNAVAILABLE_NOTE,
        "bounded acquisition unavailable",
        "bounded acquisition unavailable: read failed",
        "bounded acquisition unavailable: disk I/O error",
    )
    # Same predicate at both call sites — assert it accepts the family
    # (the close-set invariant).
    for entry in family:
        assert _is_bounded_unavailable_note(entry) is True
    # UNAVAILABLE branch: SAME root list, degraded note in the family.
    for entry in family:
        root_list = _root_list(roots=[_row("JOB-1", "RUNNING")], degraded=[entry])
        result = compose_work_queue_v1(root_list)
        assert result["availability"] == "UNAVAILABLE", entry
        assert result["reason_codes"] == ["LIFECYCLE_UNAVAILABLE"], entry
    # AVAILABLE branch: generation CONFLICT (suppresses UNAVAILABLE
    # via the non-SAME gate — but the closed degradation set still fires
    # the reason code on the document the gate would have refused, so
    # we exercise the reason-code gate alone by feeding the
    # ``_is_degradation_note`` predicate directly with the SAME entry).
    for entry in family:
        assert _is_degradation_note(entry) is True, entry


def test_b1_unknown_note_is_echoed_but_does_not_add_reason_code():
    """B1: an unknown degraded note is echoed verbatim in
    ``lifecycle_source.degraded`` but contributes no reason code —
    ``lifecycle_degraded`` is gated on a closed set of phrases, not on
    ``degraded`` being non-empty."""
    root_list = _root_list(roots=[_row("JOB-1", "RUNNING")],
                           degraded=["producer-future-warning: x"])
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "AVAILABLE"
    assert result["reason_codes"] == []
    assert result["lifecycle_source"]["degraded"] == ["producer-future-warning: x"]


def test_b1_degradation_notes_tuple_is_closed_and_sourced_from_fabric():
    """B1: ``_DEGRADATION_NOTES`` is built from the imported
    ``fabric_job_view`` constants — the composer never re-types the
    producer's note strings."""
    # All three phrases come from ``fabric_job_view``.
    assert _BOUNDED_UNAVAILABLE_NOTE in _DEGRADATION_NOTES
    assert _GENERATION_CONFLICT_NOTE in _DEGRADATION_NOTES
    assert ("bounded root discovery truncated; omitted roots are not counted"
            in _DEGRADATION_NOTES)
    # The informational enumeration note is NEVER in the closed set.
    assert _ROOT_ENUMERATION_NOTE not in _DEGRADATION_NOTES
    # Predicate matches each phrase and startswith-matches the bounded note.
    assert _is_degradation_note(_BOUNDED_UNAVAILABLE_NOTE) is True
    assert _is_degradation_note(_BOUNDED_UNAVAILABLE_NOTE + ": read failed") is True
    assert _is_degradation_note("bounded root discovery truncated; "
                                "omitted roots are not counted") is True
    assert _is_degradation_note(_GENERATION_CONFLICT_NOTE) is True
    # Informational + unknown notes never match.
    assert _is_degradation_note(_ROOT_ENUMERATION_NOTE) is False
    assert _is_degradation_note("producer-future-warning: x") is False


def test_b1_truncation_note_literal_pinned_to_producer_source():
    """Item 3 / round-4 audit: the closed-set truncation literal at
    ``_DEGRADATION_NOTES[1]`` is hand-typed in this composer; the
    closed-set test above asserts membership against the SAME literal,
    so a producer-side rename would not be detected.  Pin the literal
    byte-for-byte against what the producer's source actually emits.

    ``fabric_job_view.list_roots_v2_from_runtime`` is OUT OF SCOPE for
    this PR (parent note), so the producer is read via
    :func:`inspect.getsource` and the literal grep-pin asserts the
    composer's copy is byte-identical to the producer's emission.
    """
    import inspect
    from control_plane import fabric_job_view
    producer_source = inspect.getsource(fabric_job_view)
    literal = "bounded root discovery truncated; omitted roots are not counted"
    # The literal MUST appear in the producer's source text — pin it.
    assert literal in producer_source, (
        f"truncation literal {literal!r} not found in "
        f"control_plane.fabric_job_view source — producer may have "
        f"renamed; update _DEGRADATION_NOTES to match"
    )
    # And the composer's closed-set MUST carry the same literal byte-for-byte.
    assert literal in _DEGRADATION_NOTES


# ---------------------------------------------------------------------------
# N4 — byte-identity fixture tests for unavailable.json and effect_exception.json
# ---------------------------------------------------------------------------


def _read_fixture(name):
    from pathlib import Path
    return json.loads((Path(__file__).parent / "fixtures" / "workspace_work_queue_v1"
                       / name).read_text(encoding="utf-8"))


def test_r6_unavailable_fixture_bytes_match_deterministic_recompose():
    """N4: unavailable.json stays byte-identical under recompose."""
    from control_plane.work_queue_projection import (
        _coverage_for_unavailable, _GROUP_ORDER,
    )
    fixture = _read_fixture("unavailable.json")
    generated_at = fixture["generated_at"]
    root_list = {
        "schema": "mastermind.fabric_job_root_list.v2",
        "generated_at": "2026-09-23T00:00:00Z",
        "runtime": {"root": "/tmp/fake", "db_present": True, "identity": None,
                    "acquisition": {
                        "schema": "mastermind.fabric_runtime_acquisition.v1",
                        "query": {"kind": "root_discovery"},
                        "owner": "executive_runtime",
                        "snapshot_digest": None,
                        "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                                    "attempts_total": 340, "creation_events_per_job": 1},
                        "truncation": {"jobs": False, "attempt_job_ids": [],
                                       "roots": False, "projection": False},
                        "provenance": {"state": "COMPLETE", "unjoined_job_ids": []},
                        "generation": {"schema": "mastermind.runtime_read_observation.v1",
                                       "state": "SAME",
                                       "source_identity": "b" * 64,
                                       "before": 1, "after": 1}}},
        "roots": [],
        "count": 0,
        "total": None,
        "truncated": False,
        "degraded": [_BOUNDED_UNAVAILABLE_NOTE],
    }
    recomposed = compose_work_queue_v1(root_list, generated_at=generated_at)
    assert canonical(fixture) == canonical(recomposed)
    # Sanity: the B2 coverage envelope is in the fixture.
    assert fixture["coverage"] == _coverage_for_unavailable(root_list)
    assert set(fixture["groups"]) == set(_GROUP_ORDER)


def test_r6_effect_exception_fixture_bytes_match_deterministic_recompose():
    """B3/N4: effect_exception.json (the real route path — no effects map)
    stays byte-identical under recompose, and carries the
    ``effect_not_row_attributed`` reason code."""
    fixture = _read_fixture("effect_exception.json")
    generated_at = fixture["generated_at"]
    root_list = {
        "schema": "mastermind.fabric_job_root_list.v2",
        "generated_at": "2026-09-23T00:00:00Z",
        "runtime": {"root": "/tmp/fake", "db_present": True, "identity": None,
                    "acquisition": {
                        "schema": "mastermind.fabric_runtime_acquisition.v1",
                        "query": {"kind": "root_discovery"},
                        "owner": "executive_runtime",
                        "snapshot_digest": "a" * 64,
                        "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                                    "attempts_total": 340, "creation_events_per_job": 1},
                        "truncation": {"jobs": False, "attempt_job_ids": [],
                                       "roots": True, "projection": False},
                        "provenance": {"state": "PARTIAL", "unjoined_job_ids": ["JOB-7"]},
                        "generation": {"schema": "mastermind.runtime_read_observation.v1",
                                       "state": "SAME",
                                       "source_identity": "b" * 64,
                                       "before": 1, "after": 1}}},
        "roots": [
            {"job_id": "JOB-1", "status": "RUNNING", "depth": 0,
             "parent_job_id": None, "orchestration_role": "aggregation"},
            {"job_id": "JOB-7", "status": "QUEUED", "depth": 0,
             "parent_job_id": None, "orchestration_role": "aggregation"},
        ],
        "count": 2,
        "total": None,
        "truncated": True,
        "degraded": [],
    }
    control_room = {
        "schema": "mastermind.chairman_control_room.v1",
        "generated_at": "2026-09-23T00:00:00Z",
        "autonomy": {
            "schema": "mastermind.autonomy_control_room.v1",
            "generated_at": "2026-09-23T00:00:00Z",
            "responsibilities": [
                {"responsibility_ref": "WS:ONE", "root_job_id": "JOB-1",
                 "placement_state": {"value": "EFFECT_UNKNOWN", "observable": True,
                                     "reason": "worker_effect_unknown"}},
            ],
        },
    }
    recomposed = compose_work_queue_v1(root_list, control_room=control_room,
                                       generated_at=generated_at)
    assert canonical(fixture) == canonical(recomposed)
    # B3: the row-attribution reason code is on the document because no
    # per-row effects map was supplied.
    assert fixture["reason_codes"] == ["effect_not_row_attributed"]
    # No row-level EFFECT_EXCEPTION — the queue-level exception has no
    # per-row attribution when the producer doesn't supply one.
    assert len(fixture["groups"]["EFFECT_EXCEPTION"]) == 0


def test_r6_effect_exception_row_attributed_fixture_bytes_match_deterministic_recompose():
    """B3/N4: the composer-only effect_exception_row_attributed.json fixture
    stays byte-identical under recompose, and has NO reason code because
    the per-row effects map attributes the exception."""
    fixture = _read_fixture("effect_exception_row_attributed.json")
    generated_at = fixture["generated_at"]
    root_list = {
        "schema": "mastermind.fabric_job_root_list.v2",
        "generated_at": "2026-09-23T00:00:00Z",
        "runtime": {"root": "/tmp/fake", "db_present": True, "identity": None,
                    "acquisition": {
                        "schema": "mastermind.fabric_runtime_acquisition.v1",
                        "query": {"kind": "root_discovery"},
                        "owner": "executive_runtime",
                        "snapshot_digest": "a" * 64,
                        "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                                    "attempts_total": 340, "creation_events_per_job": 1},
                        "truncation": {"jobs": False, "attempt_job_ids": [],
                                       "roots": True, "projection": False},
                        "provenance": {"state": "PARTIAL", "unjoined_job_ids": ["JOB-7"]},
                        "generation": {"schema": "mastermind.runtime_read_observation.v1",
                                       "state": "SAME",
                                       "source_identity": "b" * 64,
                                       "before": 1, "after": 1}}},
        "roots": [
            {"job_id": "JOB-1", "status": "RUNNING", "depth": 0,
             "parent_job_id": None, "orchestration_role": "aggregation"},
            {"job_id": "JOB-7", "status": "QUEUED", "depth": 0,
             "parent_job_id": None, "orchestration_role": "aggregation"},
        ],
        "count": 2,
        "total": None,
        "truncated": True,
        "degraded": [],
    }
    control_room = {
        "schema": "mastermind.chairman_control_room.v1",
        "generated_at": "2026-09-23T00:00:00Z",
        "autonomy": {
            "schema": "mastermind.autonomy_control_room.v1",
            "generated_at": "2026-09-23T00:00:00Z",
            "responsibilities": [
                {"responsibility_ref": "WS:ONE", "root_job_id": "JOB-1",
                 "placement_state": {"value": "EFFECT_UNKNOWN", "observable": True,
                                     "reason": "worker_effect_unknown"}},
            ],
        },
    }
    effects = {"JOB-1": {"state": "EFFECT_UNKNOWN", "carrier": "agent-os:effect",
                         "evidence_ref": "agent-os:effect",
                         "observed_at": "2026-09-23T00:00:00Z"}}
    recomposed = compose_work_queue_v1(root_list, control_room=control_room,
                                       effects=effects,
                                       evidence_as_of="2026-09-23T00:01:00Z",
                                       generated_at=generated_at)
    assert canonical(fixture) == canonical(recomposed)
    assert "effect_not_row_attributed" not in fixture["reason_codes"]
    assert len(fixture["groups"]["EFFECT_EXCEPTION"]) == 1


# ---------------------------------------------------------------------------
# B2 integration — composer UNAVAILABLE body vs read-service fallback
# ---------------------------------------------------------------------------


def test_b2_unavailable_bodies_match_in_keys_excluding_legitimate_divergence(tmp_path):
    """B2/N1/N9: composer's UNAVAILABLE body (with degraded root list) and the
    read-service typed refusal body share the same key-for-key shape,
    except for keys (and sub-keys) that legitimately differ.

    The ``autonomy`` deletion fails the FIRST ``_qualified`` check inside
    ``_read_work`` (BEFORE acquire/compose are reached) — the injected
    ``work_acquire`` is therefore never called.  This exercises the
    read-service typed refusal pathway that fires when the cache bracket
    itself is unqualified.

    Excluded keys and reasons (top-level):
    - ``generated_at``: composer accepts caller-supplied or wall-clock;
      the read-service fallback uses its own wall-clock.
    - ``source_observation``: composer passes the caller-supplied receipt
      through; the read-service fallback builds its own minimal receipt.
    - ``reason_codes``: composer emits ``["LIFECYCLE_UNAVAILABLE"]``;
      the read-service fallback emits ``["source_unavailable"]`` because
      the cache bracket refused before a root list ever existed.
    - ``lifecycle_source``: composer echoes ``root_list.runtime`` identity;
      the read-service fallback has no root list to echo from so this
      field is ``None`` (the read service is the route's typed refusal
      pathway, not a partial composer projection).
    - ``coverage``: the read-service fallback fires BEFORE any root list is
      acquired, so its ``truncated`` cannot honestly mirror a producer flag
      it has never seen — it remains ``False`` while the composer's body
      carries the producer's value.  Both bodies agree on the other keys.

    Excluded sub-keys (effect_exception envelope — only ``reason``
    legitimately differs):
    - ``effect_exception.value``: both bodies agree on ``"UNKNOWN"``
      (no producer of EFFECT_UNKNOWN ever attached).
    - ``effect_exception.scope``: both bodies agree on
      ``"RUNTIME_CURRENT_WORKER"`` (the same scope semantics apply on
      both code paths).
    - ``effect_exception.observable``: both bodies agree on ``False``
      (no effect exception was observed).
    - ``effect_exception.reason``: the composer's UNAVAILABLE body uses
      ``"control_room_missing"`` (the composer's vocabulary for a missing
      control room input it was handed ``None``); the read-service
      fallback uses ``"read_refused"`` (N4 — the read service's own
      vocabulary for its OWN read failure, never the composer's).
    """
    import asyncio
    from control_plane.workspace_read_service import WorkspaceReadService
    from tests.test_workspace_read_service import (
        cache_fixture, _work_frame, _root_list_payload,
    )
    owners, _, cache = cache_fixture(tmp_path)
    # Strip autonomy so the FIRST ``_qualified`` check refuses (BEFORE
    # the runtime acquisition — the injected ``work_acquire`` is never
    # called).  Exercises the read-service typed refusal path that fires
    # when the cache bracket itself is unqualified.
    del owners[0].state_cache["doc"]["autonomy"]
    acquire_called = []
    def work_acquire(*args, **kwargs):
        acquire_called.append(True)
        return _root_list_payload(rows=[])
    def work_compose(root_list_arg, **kwargs):
        from control_plane.work_queue_projection import compose_work_queue_v1
        return compose_work_queue_v1(root_list_arg,
                                      control_room=kwargs.get("control_room"))
    service = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    fallback = asyncio.run(service.handle_frame(_work_frame())).get("result")
    # N9: the FIRST ``_qualified`` check refused — acquire was never called.
    assert acquire_called == []
    # The composer body, with generated_at frozen for diff parity.
    composer_root = _root_list(roots=[], count=0, total=None, truncated=False,
                                degraded=[_BOUNDED_UNAVAILABLE_NOTE])
    composer_doc = compose_work_queue_v1(composer_root, generated_at="FROZEN")
    # Every key in the composer body must exist in the fallback body.
    assert set(composer_doc) == set(fallback)
    # Legitimate differences, value-for-value at the TOP LEVEL.
    EXCLUDED_TOP = {"generated_at", "source_observation", "reason_codes",
                    "lifecycle_source", "coverage", "effect_exception"}
    for key in composer_doc:
        if key in EXCLUDED_TOP:
            continue
        assert composer_doc[key] == fallback[key], (
            f"key {key!r} differs: composer={composer_doc[key]!r} "
            f"fallback={fallback[key]!r}"
        )
    # effect_exception: agree on value/scope/observable; only reason
    # legitimately differs (composer uses ``control_room_missing``;
    # read-service uses ``read_refused``).
    assert composer_doc["effect_exception"]["value"] == fallback["effect_exception"]["value"]
    assert composer_doc["effect_exception"]["scope"] == fallback["effect_exception"]["scope"]
    assert composer_doc["effect_exception"]["observable"] == fallback["effect_exception"]["observable"]
    assert composer_doc["effect_exception"]["reason"] != fallback["effect_exception"]["reason"]
    # coverage.truncated: composer mirrors root_list.truncated (False
    # here); fallback is hard-coded False.  They agree on this case but
    # the fallback cannot honestly report the producer flag.
    assert composer_doc["coverage"]["truncated"] is False
    assert fallback["coverage"]["truncated"] is False


def test_n1_composer_truncated_true_root_list_reflects_in_coverage():
    """N1: a truncated=True root list (even with zero rows) renders with
    ``coverage.truncated = True`` and ``completeness = "PARTIAL"``.  This
    is the legitimate divergence from the read-service fallback's hard-
    coded ``truncated = False``."""
    root_list = _root_list(roots=[], count=0, total=None, truncated=True,
                           degraded=[_BOUNDED_UNAVAILABLE_NOTE])
    result = compose_work_queue_v1(root_list)
    assert result["availability"] == "UNAVAILABLE"
    assert result["coverage"]["truncated"] is True
    assert result["coverage"]["total"] is None
    assert result["coverage"]["completeness"] == "PARTIAL"


def test_n1_fallback_coverage_truncated_false_when_no_root_list_admitted(tmp_path):
    """N1: the read-service fallback fires BEFORE acquisition, so it cannot
    know whether the root list is truncated.  ``coverage.truncated`` stays
    ``False`` — it is a documented honest lie, not a bug."""
    import asyncio
    from control_plane.workspace_read_service import WorkspaceReadService
    from tests.test_workspace_read_service import cache_fixture, _work_frame, _root_list_payload
    owners, _, cache = cache_fixture(tmp_path)
    del owners[0].state_cache["doc"]["autonomy"]
    def work_acquire(*args, **kwargs):
        return _root_list_payload(rows=[])
    def work_compose(root_list_arg, **kwargs):
        from control_plane.work_queue_projection import compose_work_queue_v1
        return compose_work_queue_v1(root_list_arg,
                                      control_room=kwargs.get("control_room"))
    service = WorkspaceReadService(
        cache=cache, runtime=object(), authorize=lambda p: True,
        armed={}, runtime_identity={},
        work_acquire=work_acquire, work_compose=work_compose,
    )
    fallback = asyncio.run(service.handle_frame(_work_frame())).get("result")
    assert fallback["availability"] == "UNAVAILABLE"
    assert fallback["reason_codes"] == ["source_unavailable"]
    assert fallback["coverage"]["truncated"] is False