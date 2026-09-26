"""Net differences between two already-authorized Fabric v2 root snapshots.

This is a pure consumer, not an Event store, Runtime reader or session registry.
It neither acquires private sources nor grants authority from supplied documents.
The caller must retain the exact snapshots through its existing checkpoint owner.
"""
from __future__ import annotations
import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from control_plane.executive_runtime import AttemptStatus, JobStatus

_STATUSES = frozenset(item.value for enum in (JobStatus, AttemptStatus) for item in enum)


def _status(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value not in _STATUSES:
        raise ValueError("invalid_execution_status")
    return value

SCHEMA = "mastermind.fabric_checkpoint_changes.v1"
SOURCE_SCHEMA = "mastermind.fabric_job_view.v2"
MAX_INPUT_BYTES = 512 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
MAX_RECORDS = 512
MAX_CHANGES = 128
_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_JOB = re.compile(r"JOB-[0-9]{1,9}\Z")


def _mapping(value: Any) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _ref(value: Any, *, job: bool = False) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not (_JOB if job else _REF).fullmatch(value):
        raise ValueError("invalid_reference")
    return value


def _source(document: Mapping) -> str:
    acquisition = _mapping(_mapping(document.get("runtime")).get("acquisition"))
    gen = _mapping(acquisition.get("generation"))
    source, first, last = gen.get("source_identity"), gen.get("before"), gen.get("after")
    digest = acquisition.get("snapshot_digest")
    if (gen.get("schema") != "mastermind.runtime_read_observation.v1"
            or gen.get("state") != "SAME"
            or not isinstance(source, str) or re.fullmatch(r"[0-9a-f]{32}", source) is None
            or type(first) is not int or type(last) is not int or first < 0 or first != last
            or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
        raise ValueError("unqualified_source_generation")
    return source


def _partial(document: Mapping) -> bool:
    acquisition = _mapping(_mapping(document.get("runtime")).get("acquisition"))
    truncation = _mapping(acquisition.get("truncation"))
    return (_mapping(document.get("capability")).get("state") != "PROVEN"
            or bool(document.get("unjoined_job_ids"))
            or any(value is True or (isinstance(value, (list, tuple)) and bool(value))
                   for value in truncation.values())
            or any(owner.get(key) is True for owner in (document, acquisition)
                   for key in ("truncated", "jobs_truncated", "attempts_truncated")))


def _records(document: Mapping) -> tuple[str, dict[str, dict], bool]:
    if document.get("schema") != SOURCE_SCHEMA:
        raise ValueError("unsupported_snapshot_schema")
    root = _mapping(document.get("root"))
    root_id = _ref(root.get("job_id"), job=True)
    children = document.get("children")
    if root_id is None or not isinstance(children, list) or len(children) >= MAX_RECORDS:
        raise ValueError("missing_or_over_budget_records")
    records: dict[str, dict] = {}
    partial = _partial(document)
    for value in [root, *children]:
        row = _mapping(value)
        job_id = _ref(row.get("job_id"), job=True)
        if job_id is None or job_id in records:
            raise ValueError("ambiguous_job_identity")
        recorded_root = _ref(row.get("root_job_id"), job=True)
        parent = _ref(row.get("parent_job_id"), job=True)
        if ((job_id == root_id and (parent is not None or recorded_root not in (None, root_id)))
                or (job_id != root_id and (recorded_root != root_id or parent is None))):
            raise ValueError("foreign_root_membership")
        attempts = row.get("attempts")
        if not isinstance(attempts, list):
            partial = True
            attempts = []
        if len(attempts) > MAX_CHANGES:
            raise ValueError("attempts_over_budget")
        normalized = []
        seen = set()
        for value in attempts:
            attempt = _mapping(value)
            attempt_id = _ref(attempt.get("attempt_id"))
            if attempt_id is None or attempt_id in seen:
                raise ValueError("ambiguous_attempt_identity")
            seen.add(attempt_id)
            if attempt.get("status") is None:
                partial = True
            normalized.append({"attempt_id": attempt_id,
                "worker_id": _ref(attempt.get("worker_id")), "status": _status(attempt.get("status"))})
        if row.get("status") is None:
            partial = True
        records[job_id] = {"status": _status(row.get("status")), "parent_job_id": parent,
            "current_attempt_id": _ref(row.get("current_attempt_id")),
            "assigned_worker_id": _ref(row.get("assigned_worker_id")),
            "orchestration_role": _ref(row.get("orchestration_role")),
            "attempts": sorted(normalized, key=lambda a: a["attempt_id"])}
    if any(row["parent_job_id"] not in records for key, row in records.items() if key != root_id):
        raise ValueError("unjoined_parent")
    return root_id, records, partial


def _chronology(before: Mapping, after: Mapping) -> bool:
    values = [doc.get("generated_at") for doc in (before, after)]
    if any(value is None for value in values):
        return False
    if any(not isinstance(value, str) or len(value) > 64 for value in values):
        raise ValueError("invalid_snapshot_time")
    try:
        times = [datetime.fromisoformat(value.replace("Z", "+00:00")) for value in values]
    except ValueError:
        raise ValueError("invalid_snapshot_time") from None
    if any(value.tzinfo is None for value in times) or times[1] < times[0]:
        raise ValueError("unordered_snapshot_times")
    return True


def compare_fabric_snapshots(before: Mapping, after: Mapping, *, limit: int = MAX_CHANGES) -> dict:
    """Compare one root's snapshots without treating observations as commands.

    COMPLETE means a complete net comparison of these bounded inputs, not full
    event history, provider liveness, product acceptance or all-company coverage.
    Receipt counters are not used as an Event sequence or a cross-connection clock.
    """
    if type(limit) is not int or not 1 <= limit <= MAX_CHANGES:
        raise ValueError(f"limit must be an integer in 1..{MAX_CHANGES}")
    result = {"schema": SCHEMA, "state": "UNAVAILABLE", "reason": None,
        "history_kind": "NET_SNAPSHOT_DIFFERENCE", "scope": "ONE_RECORDED_EXECUTIVE_ROOT",
        "intermediate_events_included": False, "native_session_census": "NOT_OBSERVED",
        "can_act": False, "binding_transfer_authorized": False,
        "root_job_id": None, "source_identity": None, "input_digests": None,
        "changes": [], "truncated": False, "total_observed_changes": None}
    try:
        encoded = [_json(doc) for doc in (before, after)]
        if any(len(value) > MAX_INPUT_BYTES for value in encoded):
            raise ValueError("snapshot_over_budget")
        if not isinstance(before, Mapping) or not isinstance(after, Mapping):
            raise ValueError("invalid_snapshot")
        source_before, source_after = _source(before), _source(after)
        root_before, previous, partial_before = _records(before)
        root_after, current, partial_after = _records(after)
        if source_before != source_after or root_before != root_after:
            raise ValueError("different_root_or_runtime_source")
        ordered = _chronology(before, after)
    except (ValueError, TypeError, RecursionError):
        result["reason"] = "snapshots_unqualified_incompatible_or_over_budget"
        return result
    result.update({"root_job_id": root_after, "source_identity": source_after,
        "input_digests": {"before_sha256": hashlib.sha256(encoded[0]).hexdigest(),
                          "after_sha256": hashlib.sha256(encoded[1]).hexdigest()},
        "state": "PARTIAL" if partial_before or partial_after or not ordered else "COMPLETE"})
    if result["state"] == "PARTIAL":
        result["reason"] = "incomplete_scope_or_unverified_chronology"
    changes = []
    for job_id in sorted(previous.keys() | current.keys()):
        if job_id not in previous:
            changes.append({"kind": "NEWLY_OBSERVED", "job_id": job_id, "after": current[job_id]})
        elif job_id not in current:
            kind = "NOT_OBSERVED_IN_PARTIAL_SNAPSHOT" if partial_after else "NO_LONGER_OBSERVED"
            changes.append({"kind": kind, "job_id": job_id, "before": previous[job_id]})
        else:
            fields = {key: {"before": previous[job_id][key], "after": value}
                      for key, value in current[job_id].items() if previous[job_id][key] != value}
            if fields:
                changes.append({"kind": "CHANGED", "job_id": job_id, "fields": fields})
    result["total_observed_changes"] = len(changes)
    result["changes"] = changes[:limit]
    result["truncated"] = len(changes) > limit
    while len(_json(result)) > MAX_RESPONSE_BYTES and result["changes"]:
        result["changes"].pop()
        result["truncated"] = True
    if result["truncated"]:
        result["state"] = "PARTIAL"
        result["reason"] = "comparison_response_truncated"
    return result
