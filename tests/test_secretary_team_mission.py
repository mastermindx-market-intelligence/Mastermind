"""Shared-team Mission v3 projection over real canonical producer fixtures.

The success body comes from the real owner chain (closed fixture Runtime →
WorkspaceReadService mission_v3), never a hand-shaped pretend success.  Edge
scenarios compose through the authoritative ``compose_mission_workspace_v3``
producer with the existing test custody.  No live network is involved.
"""
import asyncio
import copy
import datetime
import hashlib

import pytest

from common.executive_workspace_contract import canonical
from control_plane.mission_workspace import (
    FABRIC_VIEW_SCHEMA_V3,
    compose_mission_workspace_v3,
)
from integrations.secretary_team_access.mission import (
    DEFAULT_ROWS,
    LOCAL_FRESHNESS_GUARD_SECONDS,
    MAX_ROWS,
    SUMMARY_MAX_BYTES,
    _parse_utc,
    summarize_mission,
)
from tests.test_mission_workspace import (
    STAMP as _FIXTURE_STAMP,
    _child_with_attempt,
    _current_args_for_wrapper,
    _index_with_refs,
    _owner_observation_inputs,
    _ref,
    _refresh_observation_digests,
)
from tests.test_workspace_result_service import request, result_owner, service

_STAMP = "2026-09-21T00:00:00Z"
_STAMP_EPOCH = int(datetime.datetime(
    2026, 9, 21, tzinfo=datetime.timezone.utc).timestamp())


@pytest.fixture
def mission_body(result_owner):
    """One real canonical Mission v3 body from the joined producer chain."""

    envelope = asyncio.run(service(result_owner).handle_frame(
        request(result_owner, "mission_v3")))
    assert envelope["ok"] is True, envelope
    return envelope["result"], result_owner


def _selection(owner):
    return {key: owner["selection"][key] for key in ("work_ref", "root_job_id")}


def _summarize(body, owner, **kwargs):
    return summarize_mission(body, selection=_selection(owner), **kwargs)


# ---------------------------------------------------------------------------
# Real producer body: bounded truthful summary.
# ---------------------------------------------------------------------------


def test_real_mission_summary_bounded_and_truthful(mission_body):
    body, owner = mission_body
    selected = _selection(owner)
    summary = _summarize(body, owner, now=_STAMP_EPOCH + 30)
    assert summary["schema"] == "mastermind.secretary_team_mission_summary.v1"
    assert summary["selection"] == selected
    assert summary["changed"] is None and summary["details_included"] is True
    assert summary["omitted_detail_count"] == 0
    assert summary["read_state"] == {
        "state": body["read_state"]["state"],
        "reason_codes": sorted(set(body["read_state"]["reason_codes"])),
        "usable_sections": sorted(set(body["read_state"]["usable_sections"])),
    }
    assert summary["read_state"]["state"] == "CURRENT"
    # Selected work and root join exactly; no invented identity.
    assert summary["program"]["work_ref"] == selected["work_ref"]
    assert summary["mission"]["root_job_id"] == selected["root_job_id"]
    assert summary["mission"]["runtime_root_state"] == "RESOLVED"
    assert summary["mission"]["status"] == "QUEUED"
    # Execution status and product acceptance stay two independent facets;
    # the projection never manufactures acceptance or control state.
    assert summary["execution"]["state"] == "NOT_STARTED"
    assert summary["acceptance"] == {
        "state": "NOT_PROJECTED",
        "reason_codes": ["ACCEPTANCE_OWNER_NOT_PROJECTED"],
    }
    assert summary["review"]["verdict"] == "NOT_YET"
    # Transport and watch remain factual observations, not a subscription.
    assert summary["transport"]["dispatch_state"] == "RETURNED"
    assert summary["transport"]["watch_proven"] is True
    assert summary["transport"]["historical"] is False
    assert summary["mission"]["posture_value"] == body["posture"]["value"]
    assert summary["mission"]["posture_rule"] == body["posture"]["rule"]
    # Result refs keep the original exact tuple rows and partitions.
    refs = summary["coverage"]["result_refs"]
    assert refs["availability"] == "AVAILABLE" and refs["truncated"] is False
    assert refs["absent_count"] == 1 and refs["omitted_count"] == 0
    assert summary["absent_job_ids"] == ["JOB-001"] and summary["omitted_job_ids"] == []
    assert len(summary["result_ref_rows"]) == len(body["result_refs"]["refs"]) == 3
    for projected, original in zip(summary["result_ref_rows"], body["result_refs"]["refs"]):
        assert projected == original
        assert set(projected) == {
            "root_job_id", "job_id", "attempt_id", "result_envelope_digest",
            "orchestration_role", "validation"}
    assert summary["coverage"]["full_fleet"] is False
    assert summary["coverage"]["scope"] == "single_mission"
    # Freshness: owner evidence preserved; local guard is separate and never
    # upgrades the owner's read_state.
    fresh = summary["freshness"]
    assert fresh["owner_observation_state"] == "SAME"
    assert fresh["runtime_snapshot_digest"] == (
        body["source"]["owner_observation"]["runtime"]["snapshot_digest"])
    assert fresh["generated_at"] == body["generated_at"]
    assert fresh["local"] == {"state": "FRESH", "age_seconds": 30,
                              "guard_seconds": LOCAL_FRESHNESS_GUARD_SECONDS}
    aged = _summarize(body, owner, now=_STAMP_EPOCH + 3600)["freshness"]["local"]
    assert aged["state"] == "AGED" and aged["age_seconds"] == 3600
    assert summary["read_state"]["state"] == "CURRENT"
    assert len(summary["fingerprint"]) == 64
    assert len(canonical(summary)) + 1 <= SUMMARY_MAX_BYTES


def test_real_mission_fingerprint_stable_across_reread_and_churn_immune(mission_body):
    body, owner = mission_body
    selected = _selection(owner)
    first = summarize_mission(body, selection=selected, now=_STAMP_EPOCH)
    second = summarize_mission(body, selection=selected, now=_STAMP_EPOCH + 500)
    assert first["fingerprint"] == second["fingerprint"]
    # Per-observation churn is excluded, not lifecycle fact: generated_at and
    # owner observation sample counters move without changing the fingerprint.
    churned = copy.deepcopy(body)
    churned["generated_at"] = "2026-09-21T00:05:00Z"
    churned["source"]["owner_observation"]["runtime"]["before"] = 9
    churned["source"]["owner_observation"]["runtime"]["after"] = 9
    churned["source"]["owner_observation"]["control_room"]["publication_before"] = 4
    churned["source"]["owner_observation"]["control_room"]["publication_after"] = 4
    # The per-observation runtime source identity is churn, not source fact.
    churned["source"]["owner_observation"]["runtime"]["source_identity"] = "f" * 32
    churned["result_refs"]["generation"]["source_identity"] = "e" * 32
    assert summarize_mission(churned, selection=selected, now=_STAMP_EPOCH)[
        "fingerprint"] == first["fingerprint"]


def test_real_mission_changed_detection_and_detail_omission(mission_body):
    body, owner = mission_body
    selected = _selection(owner)
    fingerprint = summarize_mission(body, selection=selected, now=_STAMP_EPOCH)[
        "fingerprint"]
    unchanged = summarize_mission(body, selection=selected, now=_STAMP_EPOCH + 1,
                                  previous_fingerprint=fingerprint)
    assert unchanged["changed"] is False and unchanged["details_included"] is False
    assert unchanged["omitted_detail_count"] > 0
    assert unchanged["coverage"]["result_refs"]["returned_count"] == 3
    assert unchanged["coverage"]["children"]["state"] == body["children"]["state"]
    assert unchanged["freshness"]["owner_observation_state"] == "SAME"
    assert unchanged["selection"] == selected
    assert "program" not in unchanged and "result_ref_rows" not in unchanged
    for key in ("execution", "review", "acceptance", "transport", "mission",
                "principal", "children_rows", "missingness_rows", "degraded"):
        assert key not in unchanged
    # A semantic execution fact changes the fingerprint; details return.
    mutated = copy.deepcopy(body)
    mutated["execution"]["state"] = "COMPLETED"
    changed = summarize_mission(mutated, selection=selected, now=_STAMP_EPOCH + 2,
                                previous_fingerprint=fingerprint)
    assert changed["changed"] is True and changed["details_included"] is True
    assert changed["execution"]["state"] == "COMPLETED"
    # A read-qualification change (owner observation state) changes it too.
    mutated = copy.deepcopy(body)
    mutated["source"]["owner_observation"]["state"] = "CONFLICT"
    qualified = summarize_mission(mutated, selection=selected, now=_STAMP_EPOCH + 3,
                                  previous_fingerprint=fingerprint)
    assert qualified["changed"] is True
    assert qualified["freshness"]["owner_observation_state"] == "CONFLICT"


# ---------------------------------------------------------------------------
# Refusals: unknown schema, malformed consumed fields, selection mismatch.
# ---------------------------------------------------------------------------


def test_real_mission_refuses_mismatch_schema_and_malformed_consumed_fields(mission_body):
    body, owner = mission_body
    selected = _selection(owner)
    with pytest.raises(ValueError, match="invalid_input"):
        summarize_mission(body, selection={"work_ref": "nope"}, now=_STAMP_EPOCH)
    with pytest.raises(ValueError, match="invalid_now"):
        summarize_mission(body, selection=selected, now="later")
    with pytest.raises(ValueError, match="invalid_previous_fingerprint"):
        summarize_mission(body, selection=selected, now=_STAMP_EPOCH,
                          previous_fingerprint="ZZ")
    with pytest.raises(ValueError, match="invalid_limit"):
        summarize_mission(body, selection=selected, now=_STAMP_EPOCH, limit=33)
    # Foreign work/root: the exact join refuses per section, in order.
    with pytest.raises(ValueError, match="selection_mismatch:program.work_ref"):
        summarize_mission(body, selection=dict(selected, work_ref="WS:ZZZ"),
                          now=_STAMP_EPOCH)
    with pytest.raises(ValueError, match="selection_mismatch:mission.root_job_id"):
        summarize_mission(body, selection=dict(selected, root_job_id="JOB-999"),
                          now=_STAMP_EPOCH)
    foreign_index = copy.deepcopy(body)
    index = foreign_index["result_refs"]
    index["root_job_id"] = "JOB-foreign"
    for row in index["refs"]:
        row["root_job_id"] = "JOB-foreign"
    with pytest.raises(ValueError, match="selection_mismatch:result_refs.root_job_id"):
        summarize_mission(foreign_index, selection=selected, now=_STAMP_EPOCH)
    foreign_observation = copy.deepcopy(body)
    foreign_observation["source"]["owner_observation"]["selection"]["work_ref"] = "WS:OTHER"
    with pytest.raises(ValueError, match="selection_mismatch:owner_observation"):
        summarize_mission(foreign_observation, selection=selected, now=_STAMP_EPOCH)
    wrong_schema = copy.deepcopy(body)
    wrong_schema["schema"] = "mastermind.mission_workspace.v2"
    with pytest.raises(ValueError, match="unknown_schema"):
        summarize_mission(wrong_schema, selection=selected, now=_STAMP_EPOCH)
    bad_state = copy.deepcopy(body)
    bad_state["read_state"]["state"] = "MAYBE"
    with pytest.raises(ValueError, match="invalid_mission_body:state"):
        summarize_mission(bad_state, selection=selected, now=_STAMP_EPOCH)
    bad_enum = copy.deepcopy(body)
    bad_enum["mission"]["status"] = "RUNNABLE"
    with pytest.raises(ValueError, match="invalid_mission_body:field_enum"):
        summarize_mission(bad_enum, selection=selected, now=_STAMP_EPOCH)
    bad_type = copy.deepcopy(body)
    bad_type["mission"]["root_job_ambiguous"] = "yes"
    with pytest.raises(ValueError, match="invalid_mission_body"):
        summarize_mission(bad_type, selection=selected, now=_STAMP_EPOCH)
    bad_digest = copy.deepcopy(body)
    bad_digest["result_refs"]["refs"][0]["result_envelope_digest"] = "nothex"
    with pytest.raises(ValueError):
        summarize_mission(bad_digest, selection=selected, now=_STAMP_EPOCH)
    bad_partition = copy.deepcopy(body)
    bad_partition["result_refs"]["truncated"] = "maybe"
    with pytest.raises(ValueError):
        summarize_mission(bad_partition, selection=selected, now=_STAMP_EPOCH)
    extra_private = copy.deepcopy(body)
    extra_private["children"]["unjoined_job_ids"] = ["JOB-X", 7]
    with pytest.raises(ValueError, match="invalid_mission_body:unjoined_job_ids"):
        summarize_mission(extra_private, selection=selected, now=_STAMP_EPOCH)
    with pytest.raises(ValueError):
        summarize_mission(None, selection=selected, now=_STAMP_EPOCH)


def test_real_mission_never_serializes_private_payload_through(mission_body):
    body, owner = mission_body
    selected = _selection(owner)
    private = copy.deepcopy(body)
    private["execution"]["artifacts"] = [{"secret_payload": "x" * 5000}]
    summary = summarize_mission(private, selection=selected, now=_STAMP_EPOCH)
    assert summary["execution"]["artifact_count"] == 1
    text = canonical(summary).decode()
    assert "secret_payload" not in text and "x" * 500 not in text
    assert len(canonical(summary)) + 1 <= SUMMARY_MAX_BYTES


# ---------------------------------------------------------------------------
# Composed producer scenarios: unjoined/attempt rows, omitted/truncated refs,
# historical cache — each keeps truthful section state, never false health.
# ---------------------------------------------------------------------------


def _full_v2_child_card():
    """Complete the consumed-subset fixture into a closed Fabric v2 child card."""

    child = _child_with_attempt()
    child.update(
        attempts=[],
        result={"state": "IN_PROGRESS", "summary": None, "artifacts": [],
                "errors": [], "next_actions": []},
        review={"required": False, "reviews_job_id": None, "verdict": "NOT_YET"},
        repair={"repair_round": None, "supersedes_job_id": None},
        acceptance={"state": "NOT_PROJECTED", "producer_owner": None,
                    "reason": "product acceptance has no producer in this projection"},
    )
    return child


def _wrapper_args(*, refs=(), absent=(), omitted=(), truncated=False,
                  children=None, unjoined_count=0, unjoined_ids=()):
    args = _owner_observation_inputs()
    fabric = args["fabric_view"]
    if children is not None:
        fabric["children"] = [_full_v2_child_card() for _ in range(len(children))]
    fabric["unjoined_job_count"] = unjoined_count
    fabric["unjoined_job_ids"] = list(unjoined_ids)
    acquisition = fabric["runtime"]["acquisition"]
    index = _index_with_refs(
        list(refs), absent=absent, omitted=omitted, truncated=truncated,
        snapshot_digest=acquisition["snapshot_digest"],
        generation=acquisition["generation"])
    wrapper = {"schema": FABRIC_VIEW_SCHEMA_V3, "fabric_view": fabric,
               "result_refs": index}
    return _current_args_for_wrapper(wrapper)


def test_composed_unjoined_children_and_omitted_truncated_refs_stay_visible():
    refs = [_ref(job_id="JOB-C1"), _ref(job_id="JOB-C2", role="review")]
    args = _wrapper_args(refs=refs, omitted=("JOB-OMITTED",), truncated=True,
                         children=[_child_with_attempt()],
                         unjoined_count=2, unjoined_ids=("JOB-U1", "JOB-U2"))
    body = compose_mission_workspace_v3(**args)
    selected = {"work_ref": args["work_ref"], "root_job_id": args["root_job_id"]}
    summary = summarize_mission(body, selection=selected, now=_STAMP_EPOCH)
    assert summary["read_state"]["state"] == "CURRENT"
    # Child identity, current attempt and native attempt lifecycle stay.
    rows = summary["children_rows"]
    assert [row["job_id"] for row in rows] == ["CHILD"]
    attempt = rows[0]["latest_attempt"]
    assert attempt["attempt_id"] == "ATTEMPT-1" and attempt["attempt_number"] == 1
    assert attempt["status"] == "RUNNING" and attempt["started_at"] == _FIXTURE_STAMP
    assert rows[0]["current_attempt_id"] == "ATTEMPT-1"
    # Unjoined coverage stays visible with counts, never an EMPTY/healthy mask.
    coverage = summary["coverage"]["children"]
    assert coverage["state"] == "PARTIAL" and coverage["coverage"] == "INCOMPLETE"
    assert "UNJOINED_JOBS_PRESENT" in coverage["reason_codes"]
    assert coverage["unjoined_job_count"] == 2
    assert summary["unjoined_job_ids"] == ["JOB-U1", "JOB-U2"]
    # Omitted and truncated partitions stay visible; availability is downgraded.
    refs_coverage = summary["coverage"]["result_refs"]
    assert refs_coverage["availability"] == "PARTIAL"
    assert refs_coverage["omitted_count"] == 1 and refs_coverage["truncated"] is True
    assert summary["omitted_job_ids"] == ["JOB-OMITTED"]
    assert [row["job_id"] for row in summary["result_ref_rows"]] == ["JOB-C1", "JOB-C2"]
    # Display window: rows beyond limit are counted, not silently dropped.
    windowed = summarize_mission(body, selection=selected, now=_STAMP_EPOCH, limit=1)
    assert len(windowed["result_ref_rows"]) == 1
    assert windowed["coverage"]["result_refs"]["display_overflow_count"] == 1
    assert windowed["coverage"]["result_refs"]["returned_count"] == 2
    ordered = summarize_mission(body, selection=selected, now=_STAMP_EPOCH)
    assert ordered == summarize_mission(body, selection=selected, now=_STAMP_EPOCH)
    assert MAX_ROWS >= DEFAULT_ROWS == 8


def test_composed_historical_cache_keeps_read_state_without_local_upgrade():
    args = _wrapper_args(refs=[_ref(job_id="JOB-C1")])
    args["cache_currentness"] = {"state": "historical_refresh_error",
                                 "publication_seq": 1}
    _refresh_observation_digests(args)
    body = compose_mission_workspace_v3(**args)
    assert body["read_state"]["state"] == "HISTORICAL"
    selected = {"work_ref": args["work_ref"], "root_job_id": args["root_job_id"]}
    summary = summarize_mission(body, selection=selected, now=_STAMP_EPOCH)
    assert summary["read_state"]["state"] == "HISTORICAL"
    assert summary["coverage"]["children"]["coverage"] == "HISTORICAL_ONLY"
    assert summary["coverage"]["result_refs"]["availability"] == "UNAVAILABLE"
    assert summary["result_ref_rows"] == []
    # The local guard is a separate derived diagnostic only.
    assert summary["freshness"]["local"]["guard_seconds"] == (
        LOCAL_FRESHNESS_GUARD_SECONDS)
    assert summary["freshness"]["owner_observation_state"] == "SAME"
    assert summary["coverage"]["full_fleet"] is False


def test_parse_utc_and_windows_edge_behavior():
    assert _parse_utc("2026-09-21T00:00:00Z") == _STAMP_EPOCH
    assert _parse_utc("2026-09-21T00:00:00+00:00") == _STAMP_EPOCH
    assert _parse_utc("not-a-stamp") is None and _parse_utc(None) is None
    assert _parse_utc(123) is None
