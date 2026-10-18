"""Adversarial pure tests over incumbent Runtime Event/Job/Attempt types."""
from __future__ import annotations

import copy
from dataclasses import replace
import json

import pytest

from control_plane.executive_runtime import (
    Attempt, AttemptStatus, BoundedRoleResultRootMetadata, Event, Job, JobStatus,
    RuntimeReadObservationReceipt,
)
from control_plane.operator_activity_projection import (
    ACTIVITY_VIEW_SCHEMA, ActivityProjectionRefusal, RetainedActivitySnapshot,
    MAX_EVENT_ROWS, project_retained_operator_activity,
)

WORK_REF = "WS:ACTIVITY"
ROOT_ID = "JOB-100"
JOB_ID = "JOB-101"
ATTEMPT_ID = "ATT-" + "a" * 32
TURN_ID = "TURN-1"
SOURCE_ID = "b" * 32
STAMP = "2026-10-18T08:15:00Z"
SECRET = "secret-prompt-and-private-token-NEVER-EXPOSE"


def _job():
    return Job(job_id=JOB_ID, objective=SECRET, department="testing", priority=1,
               status=JobStatus.COMPLETED, assigned_worker_id="worker-a",
               assigned_quota_class="routine", authority_level="owner",
               branch="private-branch", worktree="/private/dont-share",
               checkpoint={"secret": SECRET}, result={"secret": SECRET},
               created_at=STAMP, updated_at=STAMP, root_job_id=ROOT_ID,
               parent_job_id=ROOT_ID, orchestration_role="work")


def _attempt():
    return Attempt(
        attempt_id=ATTEMPT_ID, job_id=JOB_ID, attempt_number=1,
        worker_id="worker-a", quota_class="routine", status=AttemptStatus.COMPLETED,
        fence_generation=1, lease_owner=SECRET,
        lease_expires_at=STAMP, heartbeat_at=STAMP, checkpoint_sequence=0,
        checkpoint={"secret": SECRET}, result={"secret": SECRET},
        error=None, started_at=STAMP, finished_at=STAMP, version=1,
        authority_policy_hash="f" * 64,
        pid=None, pgid=None, process_start_identity=None, boot_id=None,
        provider_session_id=SECRET, stdout_path="/private/stdout",
        stderr_path="/private/stderr", result_path="/private/result",
        exit_code=0, launch_metadata={"secret": SECRET},
    )


def _payload(kinds=("claude/tool_use", "item/completed", "turn/completed"), *, turn_id=TURN_ID):
    turn = {"turn_id": turn_id, "attempt_id": ATTEMPT_ID,
            "session_epoch_id": "EPOCH-1", "process_generation_id": "GEN-1"}
    return {
        "schema_version": "mastermind.operator_harness_candidate_evidence/v1",
        "turn": turn,
        "candidate": {
            "attempt_id": ATTEMPT_ID, "session_epoch_id": "EPOCH-1",
            "process_generation_id": "GEN-1",
            "artifact_digest": None, "summary": SECRET,
            "complete_job_permitted": False,
        },
        "cursor": {
            "attempt_id": ATTEMPT_ID, "session_epoch_id": "EPOCH-1",
            "process_generation_id": "GEN-1", "turn_id": turn_id,
            "local_sequence": len(kinds),
            "provider_replay_cursor": SECRET,
        },
        "events": [
            {"attempt_id": ATTEMPT_ID, "session_epoch_id": "EPOCH-1",
             "process_generation_id": "GEN-1", "turn_id": turn_id,
             "kind": kind, "provider_event_id": SECRET,
             "native_subordinate_id": SECRET,
             "payload_redacted": {"input": SECRET, "raw_output": SECRET,
                                  "cwd": "/private/machine", "token": SECRET}}
            for kind in kinds
        ],
    }


def _event(*, number=10, payload=None, turn_id=TURN_ID):
    return Event(
        event_id=number, aggregate_type="operator_turn", aggregate_id=turn_id,
        sequence=1, event_type="OHF_CANDIDATE_RESULT_RECORDED",
        command_id="ohf-candidate:" + turn_id, actor="supervisor",
        job_id=JOB_ID, attempt_id=ATTEMPT_ID, worker_id="worker-a",
        quota_class="routine", payload=payload or _payload(turn_id=turn_id),
        created_at=STAMP,
    )


def _snapshot(events=None, *, truncated=False, **changes):
    return replace(RetainedActivitySnapshot(
        root_metadata=BoundedRoleResultRootMetadata(
            job_id=ROOT_ID, root_job_id=ROOT_ID, orchestration_role="aggregation",
            creation_command_id="ceo-intent:AUTHORITY", work_ref=WORK_REF,
            orchestration_provenance_digest="c" * 64, source_digest="d" * 64,
        ),
        job=_job(), attempt=_attempt(),
        events=(_event(),) if events is None else tuple(events),
        observation_source_identity=SOURCE_ID, source_truncated=truncated,
    ), **changes)


def _receipt(**changes):
    return replace(RuntimeReadObservationReceipt(
        schema="mastermind.runtime_read_observation.v1",
        state="SAME", source_identity=SOURCE_ID, before=5, after=5,
    ), **changes)


def _project(snapshot=None, receipt=None, **selected):
    selection = dict(work_ref=WORK_REF, root_job_id=ROOT_ID, job_id=JOB_ID,
                     attempt_id=ATTEMPT_ID)
    selection.update(selected)
    return project_retained_operator_activity(
        _snapshot() if snapshot is None else snapshot,
        _receipt() if receipt is None else receipt, **selection,
    )


def _refused(snapshot=None, receipt=None, *, code="SOURCE_UNAVAILABLE", **selected):
    with pytest.raises(ActivityProjectionRefusal) as error:
        _project(snapshot, receipt, **selected)
    assert error.value.code == code


def test_retained_metadata_only_never_exposes_provider_or_machine_content():
    owned = _snapshot()
    previous = copy.deepcopy(owned)
    view = _project(owned)
    assert view["schema"] == ACTIVITY_VIEW_SCHEMA
    assert view["availability"] == "RETAINED"
    assert view["source"] == {
        "state": "SAME_AS_OF_READ", "scope": "RETAINED_CANDIDATES_ONLY",
        "source_truncated": False,
        "live_worker_count": None, "global_event_total": None,
    }
    assert view["candidate_receipts_in_sample"] == 1
    assert view["normalized_events_in_sample"] == 3
    assert view["omitted_in_sample"] == 0
    assert view["rows"] == [
        {"candidate_event_id": 10, "turn_id": TURN_ID,
         "ordinal_in_candidate": ordinal, "category": category,
         "candidate_recorded_at": STAMP}
        for ordinal, category in enumerate(("TOOL_ACTIVITY", "ITEM_ACTIVITY", "TURN_COMPLETED"))
    ]
    payload = json.dumps(view, sort_keys=True)
    for secret in (SECRET, "/private/machine", "stdout", "raw_output",
                   "private-branch", "provider_replay_cursor", "lease_owner"):
        assert secret not in payload
    assert owned == previous
    view["rows"][0]["category"] = "mutated by presentation"
    assert owned == previous


@pytest.mark.parametrize("variant", [
    "wrong_root", "wrong_work", "wrong_job", "wrong_attempt",
    "root_self_identity", "metadata_foreign", "non_runtime_job",
])
def test_no_cross_root_job_attempt_or_workstream_authority_from_labels(variant):
    snapshot = _snapshot()
    selected = {}
    if variant == "wrong_root": selected["root_job_id"] = "JOB-999"
    elif variant == "wrong_work": selected["work_ref"] = "WS:OTHER"
    elif variant == "wrong_job": selected["job_id"] = "JOB-999"
    elif variant == "wrong_attempt": selected["attempt_id"] = "ATT-" + "f" * 32
    elif variant == "root_self_identity":
        snapshot = replace(snapshot, root_metadata=replace(snapshot.root_metadata, job_id="JOB-999"))
    elif variant == "metadata_foreign":
        snapshot = replace(snapshot, job=replace(snapshot.job, root_job_id="JOB-999"))
    else: snapshot = replace(snapshot, job={"job_id": JOB_ID})
    _refused(snapshot, **selected)


@pytest.mark.parametrize("changes,code", [
    ({"state": "CONFLICT"}, "SOURCE_CHANGED"),
    ({"state": "UNKNOWN"}, "SOURCE_UNAVAILABLE"),
    ({"source_identity": None}, "SOURCE_UNAVAILABLE"),
    ({"source_identity": "f" * 32}, "SOURCE_UNAVAILABLE"),
    ({"before": 4, "after": 5}, "SOURCE_UNAVAILABLE"),
    ({"before": True}, "SOURCE_UNAVAILABLE"),
    ({"schema": "foreign"}, "SOURCE_UNAVAILABLE"),
])
def test_finite_same_runtime_receipt_required(changes, code):
    _refused(receipt=_receipt(**changes), code=code)


def test_snapshot_identity_must_match_finalized_receipt():
    _refused(_snapshot(observation_source_identity="e" * 32))
    _refused(_snapshot(source_truncated="False"))


@pytest.mark.parametrize("attribute,replacement", [
    ("worker_id", "other-worker"),
    ("quota_class", "private-class"),
    ("command_id", "ohf-candidate:NOT-ORIGINAL"),
    ("actor", "provider"),
    ("aggregate_type", "operator_operation"),
    ("job_id", "JOB-999"),
    ("attempt_id", "ATT-" + "f" * 32),
])
def test_owner_event_identity_and_lease_fields_cannot_be_substituted(attribute, replacement):
    _refused(_snapshot(events=[replace(_event(), **{attribute: replacement})]))


@pytest.mark.parametrize("path,replacement", [
    (("turn", "turn_id"), "TURN-FOREIGN"),
    (("turn", "attempt_id"), "ATT-" + "f" * 32),
    (("candidate", "complete_job_permitted"), True),
    (("candidate", "session_epoch_id"), "EPOCH-OTHER"),
    (("cursor", "turn_id"), "TURN-OTHER"),
    (("cursor", "local_sequence"), -1),
    (("events", 0, "turn_id"), "TURN-OTHER"),
    (("events", 0, "attempt_id"), "ATT-" + "f" * 32),
    (("events", 0, "payload_redacted"), "secret"),
])
def test_canonical_turn_candidate_cursor_and_normalized_event_joins(path, replacement):
    payload = _payload()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    _refused(_snapshot(events=[_event(payload=payload)]))


def test_new_field_and_unrecognized_kind_never_becomes_raw_provider_text():
    payload = _payload((SECRET,))
    view = _project(_snapshot(events=[_event(payload=payload)]))
    assert view["rows"][0]["category"] == "OTHER_REDACTED_EVENT"
    assert SECRET not in json.dumps(view)
    payload = _payload()
    payload["unauthorized"] = SECRET
    _refused(_snapshot(events=[_event(payload=payload)]))


def test_no_retained_candidate_does_not_mean_no_live_workers():
    no_candidate = replace(_event(), event_type="JOB_STARTED")
    view = _project(_snapshot(events=[no_candidate]))
    assert view["availability"] == "NO_RETAINED_CANDIDATES"
    assert view["rows"] == []
    assert view["source"]["global_event_total"] is None
    assert view["source"]["live_worker_count"] is None


def test_more_than_32_normalized_rows_are_explicitly_sample_partial():
    kinds = ("item/started",) * (MAX_EVENT_ROWS + 4)
    view = _project(_snapshot(events=[_event(payload=_payload(kinds))]))
    assert view["availability"] == "PARTIAL"
    assert view["normalized_events_in_sample"] == MAX_EVENT_ROWS + 4
    assert len(view["rows"]) == MAX_EVENT_ROWS
    assert view["omitted_in_sample"] == 4
    assert view["rows"][0]["ordinal_in_candidate"] == 4
    assert view["rows"][-1]["ordinal_in_candidate"] == MAX_EVENT_ROWS + 3


def test_source_truncation_and_budgets_are_not_hidden():
    view = _project(_snapshot(truncated=True))
    assert view["availability"] == "PARTIAL" and view["source"]["source_truncated"] is True
    _refused(_snapshot(events=[replace(_event(), event_id=i + 1, event_type="OTHER")
                               for i in range(65)]), code="SOURCE_OVER_BUDGET")
    _refused(_snapshot(events=[_event(payload=_payload(("item/started",) * 257))]),
             code="SOURCE_OVER_BUDGET")


def test_candidate_source_order_and_duplicate_turn_protection():
    _refused(_snapshot(events=[_event(number=10), _event(number=9)]))
    _refused(_snapshot(events=[_event(number=10), _event(number=11)]))
    valid = _snapshot(events=[
        _event(number=10),
        _event(number=11, turn_id="TURN-2",
               payload=_payload(("turn/completed",), turn_id="TURN-2")),
    ])
    view = _project(valid)
    assert view["candidate_receipts_in_sample"] == 2
    assert view["rows"][-1]["turn_id"] == "TURN-2"


def test_snapshot_mutation_and_foreign_records_refused():
    _refused(_snapshot(events=[{"event_type": "OHF_CANDIDATE_RESULT_RECORDED"}]))
    _refused(_snapshot(events=[replace(_event(), event_id=0)]))
    _refused(_snapshot(events=[replace(_event(), attempt_id="ATT-" + "d" * 32)]))


def test_source_fixture_matches_existing_runtime_typed_wire_not_a_new_format():
    from control_plane.operator_harness_contract import (
        CandidateResult, EventCursor, NormalizedEvent, TurnRef,
    )
    from control_plane.executive_runtime import _ohf_jsonable
    turn = TurnRef(TURN_ID, "EPOCH-1", "GEN-1", ATTEMPT_ID)
    candidate = CandidateResult(
        ATTEMPT_ID, "EPOCH-1", "GEN-1", None, SECRET,
    )
    cursor = EventCursor(
        ATTEMPT_ID, "EPOCH-1", "GEN-1",
        local_sequence=3, turn_id=TURN_ID, provider_replay_cursor=SECRET,
    )
    events = tuple(
        NormalizedEvent(
            ATTEMPT_ID, "EPOCH-1", "GEN-1", TURN_ID,
            kind, provider_event_id=SECRET, native_subordinate_id=SECRET,
            payload_redacted={"input": SECRET, "raw_output": SECRET,
                              "cwd": "/private/machine", "token": SECRET},
        )
        for kind in ("claude/tool_use", "item/completed", "turn/completed")
    )
    payload = _payload()
    assert _ohf_jsonable(turn) == payload["turn"]
    assert _ohf_jsonable(candidate) == payload["candidate"]
    assert _ohf_jsonable(cursor) == payload["cursor"]
    assert _ohf_jsonable(events) == payload["events"]
    view = _project(_snapshot(events=[_event(payload={
        "schema_version": payload["schema_version"],
        "turn": _ohf_jsonable(turn),
        "candidate": _ohf_jsonable(candidate),
        "cursor": _ohf_jsonable(cursor),
        "events": _ohf_jsonable(events),
    })]))
    assert view["normalized_events_in_sample"] == 3


@pytest.mark.parametrize("timestamp", [
    SECRET, "2026-02-30T08:15:00Z", "2026-10-18T08:15:00+07:00",
    "2026-10-18", "2026-10-18T08:15:00ZPRIVATE", "",
])
def test_invalid_timestamp_cannot_be_echoed_as_runtime_observation(timestamp):
    _refused(_snapshot(events=[replace(_event(), created_at=timestamp)]))


def test_incumbent_runtime_utc_isoformat_is_supported_without_timing_claims():
    value = "2026-10-18T08:15:00+00:00"
    view = _project(_snapshot(events=[replace(_event(), created_at=value)]))
    assert view["rows"][0]["candidate_recorded_at"] == value
    assert view["source"]["scope"] == "RETAINED_CANDIDATES_ONLY"


def test_output_byte_ceiling_and_foreign_non_candidate_identity(monkeypatch):
    from control_plane import operator_activity_projection as owner
    foreign = replace(_event(), event_type="SOME_OTHER_EVENT", job_id="JOB-999")
    _refused(_snapshot(events=[foreign]))
    monkeypatch.setattr(owner, "MAX_PROJECTION_BYTES", 32)
    _refused(code="SOURCE_OVER_BUDGET")
