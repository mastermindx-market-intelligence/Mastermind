"""Derive non-modifying quota rollover proof from existing Executive owners.

No tables, retries, routing, provider calls or lifecycle writes live here. Absence
of an active process is NOT positive release evidence. Historical replay validates
an existing Event only; it cannot authorize a fresh requeue.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Mapping

SCHEMA = "mastermind.quota_rollover_proof/v1"
_ADVERSE = {
    "OPERATOR_OPERATION_EFFECT_UNKNOWN", "OHF_CANDIDATE_RESULT_RECORDED",
    "ORCHESTRATION_ROLE_RESULT_SEALED",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _json(raw: str) -> Any:
    if not isinstance(raw, str) or len(raw.encode()) > 1_048_576:
        raise ValueError("unbounded or absent source JSON")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate source JSON key")
            result[key] = value
        return result

    def invalid(value):
        raise ValueError("non-finite source JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _positive_int(value: Any) -> bool:
    return type(value) is int and value > 0


def _event(row, *, event_type, actor, aggregate_type, aggregate_id, job, attempt):
    return bool(
        row is not None
        and _positive_int(row["event_id"])
        and row["event_type"] == event_type
        and row["actor"] == actor
        and row["aggregate_type"] == aggregate_type
        and row["aggregate_id"] == aggregate_id
        and row["job_id"] == job["job_id"]
        and row["attempt_id"] == attempt["attempt_id"]
        and row["worker_id"] == attempt["worker_id"]
        and row["quota_class"] == attempt["quota_class"]
    )


def quota_rollover_material(
    connection: sqlite3.Connection, *, job: Mapping[str, Any],
    attempt: Mapping[str, Any], require_current_quota: bool = True,
) -> dict[str, Any] | None:
    """Return positive, content-bound release proof or None in one owner snapshot.

    Caller must separately enforce remaining allowance, root/grant admission and
    the existing RetrySafety classifier, then rederive inside its write transaction.
    require_current_quota=False is exclusively for immutable Event replay checks.
    """
    try:
        return _material(connection, job, attempt, require_current_quota)
    except (KeyError, TypeError, ValueError):
        return None


def _material(con, job, attempt, require_current_quota):
    rid = attempt["attempt_id"]
    if (
        not isinstance(rid, str) or not rid
        or attempt["job_id"] != job["job_id"]
        or job["current_attempt_id"] != rid
        or job["status"] != "RATE_LIMITED" or attempt["status"] != "RATE_LIMITED"
        or attempt["execution_mode"] != "OPERATOR_HARNESS"
        or attempt["lease_token"] is not None
        or not _positive_int(attempt["fence_generation"])
        or not _positive_int(attempt["finished_at_ms"])
        or not _positive_int(attempt["checkpoint_sequence"])
        or not attempt["checkpoint_json"]
        or job["checkpoint_json"] != attempt["checkpoint_json"]
        or job["result_json"] is not None or attempt["result_json"] is not None
    ):
        return None
    grant = _json(attempt["effective_grant_json"])
    authorities = grant.get("authorities") if isinstance(grant, dict) else None
    if (not isinstance(authorities, list) or not authorities
            or any(item not in {"READ", "RUN_TESTS"} for item in authorities)
            or grant.get("write_paths") != []):
        return None
    checkpoint = _json(attempt["checkpoint_json"])
    actions = checkpoint.get("next_actions") if isinstance(checkpoint, dict) else None
    if (not isinstance(actions, list) or not actions
            or any(not isinstance(item, str) or not item.strip() for item in actions)):
        return None
    quota = con.execute(
        "SELECT * FROM worker_quota_classes WHERE worker_id=? AND quota_class=?",
        (attempt["worker_id"], attempt["quota_class"]),
    ).fetchone()
    if require_current_quota and (
        quota is None or quota["status"] != "RATE_LIMITED"
        or quota["held_attempt_id"] != rid
        or quota["fence_counter"] != attempt["fence_generation"]
    ):
        return None
    events = list(con.execute("SELECT * FROM events WHERE attempt_id=? ORDER BY event_id", (rid,)))
    if any(row["event_type"] in _ADVERSE for row in events):
        return None
    limits = [row for row in events if row["event_type"] == "JOB_RATE_LIMITED"]
    if len(limits) != 1:
        return None
    limited = limits[0]
    limit_payload = _json(limited["payload_json"])
    if (not isinstance(limit_payload, dict)
            or set(limit_payload) != {"checkpoint_sequence"}
            or type(limit_payload["checkpoint_sequence"]) is not int):
        return None
    if (not _event(limited, event_type="JOB_RATE_LIMITED", actor="worker",
                   aggregate_type="job", aggregate_id=job["job_id"], job=job, attempt=attempt)
            or limited["created_at_ms"] != attempt["finished_at_ms"]
            or _json(limited["payload_json"]) != {"checkpoint_sequence": attempt["checkpoint_sequence"]}):
        return None
    epochs = list(con.execute(
        "SELECT * FROM harness_session_epochs WHERE attempt_id=? ORDER BY session_epoch_id", (rid,)))
    if not epochs:
        return None
    releases = []
    generation_ids = []
    for epoch in epochs:
        if (epoch["state"] not in {"ABANDONED", "TERMINAL"}
                or epoch["worker_id"] != attempt["worker_id"]):
            return None
        generations = list(con.execute(
            "SELECT * FROM process_generations WHERE session_epoch_id=? ORDER BY process_generation_id",
            (epoch["session_epoch_id"],)))
        if not generations:
            return None
        for generation in generations:
            gid = generation["process_generation_id"]
            ended = generation["ended_at_ms"]
            if (not _positive_int(ended)
                    or not _positive_int(generation["started_at_ms"])
                    or not generation["started_at_ms"] <= ended <= limited["created_at_ms"]
                    or generation["executive_writer_held"] != 0
                    or generation["provider_writer_state"] != "RELEASED"
                    or generation["worker_id"] != attempt["worker_id"]
                    or generation["provider_session_id"] != epoch["provider_session_id"]):
                return None
            stopped = [row for row in events if row["event_type"] == "OHF_GRACEFUL_STOP"
                       and row["aggregate_id"] == gid]
            if len(stopped) != 1:
                return None
            stop = stopped[0]
            release_payload = _json(stop["payload_json"])
            if (not _event(stop, event_type="OHF_GRACEFUL_STOP", actor="supervisor",
                           aggregate_type="process_generation", aggregate_id=gid, job=job, attempt=attempt)
                    or not ended <= stop["created_at_ms"] <= limited["created_at_ms"]
                    or not isinstance(release_payload, dict)
                    or set(release_payload) != {"writer_released"}
                    or release_payload["writer_released"] is not True):
                return None
            generation_ids.append(gid)
            releases.append({
                "generation_id": gid, "epoch_id": epoch["session_epoch_id"],
                "epoch_state": epoch["state"], "ended_at_ms": ended,
                "event_id": stop["event_id"], "event_digest": _digest(dict(stop)),
            })
    value = {
        "schema_version": SCHEMA, "job_id": job["job_id"], "attempt_id": rid,
        "worker_id": attempt["worker_id"], "quota_class": attempt["quota_class"],
        "fence_generation": attempt["fence_generation"],
        "checkpoint_sequence": attempt["checkpoint_sequence"],
        "checkpoint_digest": _digest(checkpoint), "grant_digest": _digest(grant),
        "rate_limit_event_id": limited["event_id"],
        "rate_limit_event_digest": _digest(dict(limited)),
        "generation_ids": sorted(generation_ids), "releases": releases,
    }
    value["evidence_digest"] = _digest(value)
    return value


def validate_saved_quota_proof(connection, proof: Any) -> bool:
    """Validate an already-committed requeue proof against its historical sources.

    This does not inspect current capacity or authorize execution. Successor work
    may have advanced the Job; predecessor Attempt/checkpoint/Event bytes remain
    the immutable source of its existing requeue receipt.
    """
    if (not isinstance(proof, dict) or proof.get("schema_version") != SCHEMA
            or not isinstance(proof.get("attempt_id"), str) or not proof["attempt_id"]):
        return False
    attempt_row = connection.execute(
        "SELECT * FROM attempts WHERE attempt_id=?", (proof.get("attempt_id"),)).fetchone()
    if attempt_row is None:
        return False
    attempt = dict(attempt_row)
    historical_job = {
        "job_id": attempt["job_id"], "current_attempt_id": attempt["attempt_id"],
        "status": "RATE_LIMITED", "checkpoint_json": attempt["checkpoint_json"],
        "result_json": None,
    }
    observed = quota_rollover_material(connection, job=historical_job, attempt=attempt,
                                       require_current_quota=False)
    return observed is not None and observed == proof
