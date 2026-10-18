"""Pure, bounded *retained* Operator Harness activity metadata.

Consumes only the incumbent Runtime's typed, previously authorized same-read
material. It creates no event store, live watcher, scheduler, permissions, or
worker controls. Projected rows are recorded-with-candidate facts, never a
live provider event stream, private reasoning, review verdict or Job acceptance.

The owning Runtime/Workspace reader must still prove one principal's entitlement
to the original root/Job/Attempt and sample the canonical source under one
bounded observation. This pure leaf is NOT itself that owner or a public API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re

from control_plane.executive_runtime import (
    Attempt, BoundedRoleResultRootMetadata, Event, Job,
    OHF_CANDIDATE_EVIDENCE_SCHEMA_VERSION, RuntimeReadObservationReceipt,
)

ACTIVITY_VIEW_SCHEMA = "mastermind.operator_retained_activity_metadata.v1"
MAX_SOURCE_EVENTS = 64
MAX_EVENT_ROWS = 32
MAX_EVENTS_IN_CANDIDATE = 256
MAX_PROJECTION_BYTES = 16_384
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_WORK = re.compile(r"^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$")
_JOB = re.compile(r"^JOB-[0-9]{1,9}$")
_REQUEST_ID = re.compile(r"^[0-9a-f]{32}$")
_UTC_SECOND_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|\+00:00)$")

__all__ = [
    "ACTIVITY_VIEW_SCHEMA", "RetainedActivitySnapshot", "ActivityProjectionRefusal",
    "project_retained_operator_activity",
]


class ActivityProjectionRefusal(ValueError):
    """Typed source refusal, without retaining raw event or candidate content."""

    def __init__(self, code: str):
        if code not in {"SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SOURCE_OVER_BUDGET"}:
            raise ValueError("invalid_refusal")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class RetainedActivitySnapshot:
    """In-memory proof-bearing *input*, not an additional durable owner.

    Only the original Runtime bounded observation is entitled to construct
    production instances and bind them to the finalized same-read receipt.
    The pure projector cannot independently authenticate or grant a user.
    """

    root_metadata: BoundedRoleResultRootMetadata
    job: Job
    attempt: Attempt
    events: tuple[Event, ...]
    observation_source_identity: str
    source_truncated: bool


def _refuse(code: str = "SOURCE_UNAVAILABLE") -> None:
    raise ActivityProjectionRefusal(code)


def _token(value: object) -> bool:
    return type(value) is str and _ID.fullmatch(value) is not None


def _exact(value: object, keys: set[str]) -> bool:
    return type(value) is dict and set(value) == keys


def _event_category(value: object) -> str:
    """Coarsen provider event kinds; never copy opaque kind or payload text."""
    if value == "turn/completed":
        return "TURN_COMPLETED"
    if value in {"turn/started", "turn/updated"}:
        return "TURN_ACTIVITY"
    if value in {"item/started", "item/updated", "item/completed"}:
        return "ITEM_ACTIVITY"
    if value in {
        "claude/tool_use", "claude/tool_result", "claude/tool_start",
        "claude/tool_end", "claude/tool_use_start", "claude/tool_use_end",
    }:
        return "TOOL_ACTIVITY"
    if value in {"claude/assistant", "claude/result"}:
        return "MODEL_ACTIVITY"
    return "OTHER_REDACTED_EVENT"


def _qualify(snapshot: RetainedActivitySnapshot, receipt: RuntimeReadObservationReceipt,
             *, work_ref: str, root_job_id: str, job_id: str, attempt_id: str) -> None:
    if not isinstance(receipt, RuntimeReadObservationReceipt) or receipt.schema != "mastermind.runtime_read_observation.v1":
        _refuse()
    if receipt.state == "CONFLICT":
        _refuse("SOURCE_CHANGED")
    if (receipt.state != "SAME" or type(receipt.source_identity) is not str
            or _REQUEST_ID.fullmatch(receipt.source_identity) is None
            or type(receipt.before) is not int or receipt.before < 0
            or type(receipt.after) is not int or receipt.after != receipt.before):
        _refuse()
    if not isinstance(snapshot, RetainedActivitySnapshot):
        _refuse()
    if (type(snapshot.observation_source_identity) is not str
            or snapshot.observation_source_identity != receipt.source_identity
            or type(snapshot.source_truncated) is not bool
            or type(snapshot.events) is not tuple):
        _refuse()
    if len(snapshot.events) > MAX_SOURCE_EVENTS:
        _refuse("SOURCE_OVER_BUDGET")
    if (type(work_ref) is not str or _WORK.fullmatch(work_ref) is None
            or type(root_job_id) is not str or _JOB.fullmatch(root_job_id) is None
            or type(job_id) is not str or _JOB.fullmatch(job_id) is None
            or not _token(attempt_id)):
        _refuse()
    root, job, attempt = snapshot.root_metadata, snapshot.job, snapshot.attempt
    if (not isinstance(root, BoundedRoleResultRootMetadata)
            or root.job_id != root_job_id or root.root_job_id != root_job_id
            or root.orchestration_role != "aggregation" or root.work_ref != work_ref
            or not isinstance(job, Job) or job.job_id != job_id
            or job.root_job_id != root_job_id or not isinstance(attempt, Attempt)
            or attempt.attempt_id != attempt_id or attempt.job_id != job_id):
        _refuse()


def _candidate(event: Event, *, job: Job, attempt: Attempt) -> tuple[str, list[dict]]:
    if (event.aggregate_type != "operator_turn"
            or event.event_type != "OHF_CANDIDATE_RESULT_RECORDED"
            or event.actor != "supervisor"
            or event.job_id != job.job_id or event.attempt_id != attempt.attempt_id
            or event.worker_id != attempt.worker_id
            or event.quota_class != attempt.quota_class
            or type(event.payload) is not dict
            or not _exact(event.payload, {"schema_version", "turn", "candidate", "events", "cursor"})
            or event.payload["schema_version"] != OHF_CANDIDATE_EVIDENCE_SCHEMA_VERSION):
        _refuse()
    if type(event.created_at) is not str or _UTC_SECOND_STAMP.fullmatch(event.created_at) is None:
        _refuse()
    try:
        recorded = datetime.fromisoformat(event.created_at.replace("Z", "+00:00"))
    except ValueError:
        _refuse()
    if recorded.utcoffset() != timedelta(0):
        _refuse()
    payload = event.payload
    turn, candidate, cursor, events = (
        payload["turn"], payload["candidate"], payload["cursor"], payload["events"],
    )
    if (not _exact(turn, {"turn_id", "attempt_id", "session_epoch_id", "process_generation_id"})
            or not _exact(candidate, {
                "attempt_id", "session_epoch_id", "process_generation_id",
                "artifact_digest", "summary", "complete_job_permitted",
            }) or not _exact(cursor, {
                "attempt_id", "session_epoch_id", "process_generation_id",
                "local_sequence", "turn_id", "provider_replay_cursor",
            }) or type(events) is not list):
        _refuse()
    turn_id = turn["turn_id"]
    if (not _token(turn_id)
            or event.aggregate_id != turn_id
            or event.command_id != "ohf-candidate:" + turn_id
            or not _token(turn["session_epoch_id"]) or not _token(turn["process_generation_id"])
            or turn["attempt_id"] != attempt.attempt_id
            or candidate["complete_job_permitted"] is not False
            or any(candidate[key] != turn[key] for key in (
                "attempt_id", "session_epoch_id", "process_generation_id",
            ))
            or any(cursor[key] != turn[key] for key in (
                "attempt_id", "session_epoch_id", "process_generation_id",
            ))
            or cursor["turn_id"] != turn_id
            or type(cursor["local_sequence"]) is not int
            or cursor["local_sequence"] < 0):
        _refuse()
    if len(events) > MAX_EVENTS_IN_CANDIDATE:
        _refuse("SOURCE_OVER_BUDGET")
    normalized = []
    for ordinal, item in enumerate(events):
        if (not _exact(item, {
            "attempt_id", "session_epoch_id", "process_generation_id",
            "turn_id", "kind", "provider_event_id",
            "native_subordinate_id", "payload_redacted",
        }) or item["attempt_id"] != turn["attempt_id"]
                or item["session_epoch_id"] != turn["session_epoch_id"]
                or item["process_generation_id"] != turn["process_generation_id"]
                or item["turn_id"] not in (None, turn_id)
                or type(item["kind"]) is not str
                or type(item["payload_redacted"]) is not dict):
            _refuse()
        normalized.append({
            "candidate_event_id": event.event_id,
            "turn_id": turn_id,
            "ordinal_in_candidate": ordinal,
            "category": _event_category(item["kind"]),
            # Recorded when Runtime persisted the *candidate*, not event occurrence.
            "candidate_recorded_at": event.created_at,
        })
    return turn_id, normalized


def project_retained_operator_activity(
    snapshot: RetainedActivitySnapshot,
    receipt: RuntimeReadObservationReceipt,
    *,
    work_ref: str,
    root_job_id: str,
    job_id: str,
    attempt_id: str,
) -> dict:
    """One pure bounded metadata projection. No I/O, storage, or permission grant."""
    _qualify(snapshot, receipt, work_ref=work_ref, root_job_id=root_job_id,
             job_id=job_id, attempt_id=attempt_id)
    rows: list[dict] = []
    candidate_receipts = 0
    seen_turns: set[str] = set()
    previous_id = 0
    assert isinstance(snapshot, RetainedActivitySnapshot)
    for event in snapshot.events:
        if (not isinstance(event, Event) or type(event.event_id) is not int
                or event.event_id <= previous_id or event.attempt_id != attempt_id
                or event.job_id != job_id):
            _refuse()
        previous_id = event.event_id
        if event.event_type != "OHF_CANDIDATE_RESULT_RECORDED":
            continue
        turn_id, items = _candidate(event, job=snapshot.job, attempt=snapshot.attempt)
        if turn_id in seen_turns:
            _refuse()
        seen_turns.add(turn_id)
        candidate_receipts += 1
        rows.extend(items)
        if len(rows) > MAX_SOURCE_EVENTS * MAX_EVENTS_IN_CANDIDATE:
            _refuse("SOURCE_OVER_BUDGET")
    omitted = max(0, len(rows) - MAX_EVENT_ROWS)
    rows = rows[-MAX_EVENT_ROWS:]
    result = {
        "schema": ACTIVITY_VIEW_SCHEMA,
        "selection": {"work_ref": work_ref, "root_job_id": root_job_id,
                      "job_id": job_id, "attempt_id": attempt_id},
        "availability": "PARTIAL" if snapshot.source_truncated or omitted else (
            "RETAINED" if rows else "NO_RETAINED_CANDIDATES"
        ),
        "source": {"state": "SAME_AS_OF_READ",
                   "scope": "RETAINED_CANDIDATES_ONLY",
                   "source_truncated": snapshot.source_truncated,
                   "live_worker_count": None, "global_event_total": None},
        "candidate_receipts_in_sample": candidate_receipts,
        "normalized_events_in_sample": len(rows) + omitted,
        "omitted_in_sample": omitted,
        "rows": rows,
    }
    try:
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        _refuse("SOURCE_OVER_BUDGET")
    if len(encoded.encode("utf-8")) > MAX_PROJECTION_BYTES:
        _refuse("SOURCE_OVER_BUDGET")
    return result
