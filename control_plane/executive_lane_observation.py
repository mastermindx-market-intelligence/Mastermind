"""Bounded Executive-owned recorded-lane read; no lifecycle or authority writes.

Internal callers supply an already-authorized read-only Runtime and exact root.
This source proposal has no installed/MCP route. It does not attest database
handles, native sessions, RuntimeBindings, current permission or provider work.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from control_plane.executive_runtime import AttemptStatus, JobStatus, Runtime, RuntimeProofError

SCHEMA = "mastermind.executive_lane_observation.v1"
MAX_ROWS = 128
MAX_RESPONSE_BYTES = 128 * 1024
MAX_SQL_STEPS = 50_000
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_GAPS = (
    "RUNTIME_BINDING_NOT_PROJECTED", "NATIVE_ACTIVITY_NOT_OBSERVED",
    "ACCOUNT_ENROLLMENT_NOT_PROJECTED", "HOST_NOT_PROJECTED",
    "EFFECT_STATE_NOT_PROJECTED", "CURRENT_PERMISSION_NOT_EVALUATED",
    "INSTALLED_RUNTIME_IDENTITY_NOT_ATTESTED",
)


def _token(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _TOKEN.fullmatch(value) is None:
        raise ValueError("invalid bounded source identifier")
    return value


def _integer(value: Any, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError("invalid bounded source integer")
    return value


def _document(root: str | None, *, status: str, lanes: list | None = None,
              completeness: str = "unknown", issues: tuple[str, ...] = ()) -> dict:
    return {
        "schema": SCHEMA, "status": status, "root_job_id": root,
        "source_owner": "executive_os",
        "source_consistency": "single_read_transaction" if lanes is not None else None,
        "current_permission": "NOT_EVALUATED",
        "coverage": {
            "scope": "ROOT_JOB_AND_EXECUTIVE_DESCENDANTS",
            "completeness": completeness,
            "returned_count": len(lanes) if lanes is not None else None,
            "native_helpers": "not_observed", "account_enrollment": "unknown",
        },
        "gaps": list(_GAPS), "lanes": lanes, "issues": list(issues),
    }


_JOB_COLUMNS = """
 substr(j.job_id,1,129) AS job_id, substr(j.parent_job_id,1,129) AS parent_job_id,
 substr(j.root_job_id,1,129) AS root_job_id, j.depth,
 substr(j.owner_seat,1,129) AS owner_seat, substr(j.status,1,129) AS job_status,
 j.updated_at_ms AS job_updated_at_ms,
 substr(j.current_attempt_id,1,129) AS current_attempt_id
"""

_ATTEMPT_COLUMNS = """
 substr(a.attempt_id,1,129) AS attempt_id, substr(a.worker_id,1,129) AS worker_id,
 substr(a.status,1,129) AS attempt_status, a.fence_generation,
 a.heartbeat_at_ms, a.lease_expires_at_ms, a.checkpoint_sequence,
 a.started_at_ms, a.finished_at_ms,
 substr(w.worker_id,1,129) AS witnessed_worker_id,
 w.last_seen_at_ms AS worker_last_seen_at_ms
"""
_JOIN = """
 LEFT JOIN attempts a ON a.attempt_id=j.current_attempt_id
   AND a.job_id=j.job_id AND a.worker_id=j.assigned_worker_id
   AND a.quota_class=j.assigned_quota_class
 LEFT JOIN workers w ON w.worker_id=a.worker_id
"""


def _lane(row: sqlite3.Row) -> dict:
    lane = {
        "job_id": _token(row["job_id"]),
        "parent_job_id": _token(row["parent_job_id"], nullable=True),
        "root_job_id": _token(row["root_job_id"]),
        "depth": _integer(row["depth"]), "owner_seat": _token(row["owner_seat"]),
        "job_status": JobStatus(row["job_status"]).value,
        "job_updated_at_ms": _integer(row["job_updated_at_ms"]),
        "current_attempt": None, "issues": [],
    }
    current = _token(row["current_attempt_id"], nullable=True)
    if current is None:
        return lane
    if row["attempt_id"] is None or row["witnessed_worker_id"] is None:
        lane["issues"].append("CURRENT_ATTEMPT_JOIN_UNAVAILABLE")
        return lane
    attempt = {
        "attempt_id": _token(row["attempt_id"]),
        "worker_id": _token(row["worker_id"]),
        "status": AttemptStatus(row["attempt_status"]).value,
    }
    for key in ("fence_generation", "heartbeat_at_ms", "lease_expires_at_ms",
                "checkpoint_sequence", "started_at_ms", "worker_last_seen_at_ms"):
        attempt[key] = _integer(row[key])
    attempt["finished_at_ms"] = _integer(row["finished_at_ms"], nullable=True)
    if attempt["attempt_id"] != current or attempt["worker_id"] != row["witnessed_worker_id"]:
        raise ValueError("inconsistent current attempt")
    lane["current_attempt"] = attempt
    return lane


def _valid_graph(lanes: list[dict], root: str) -> bool:
    by_id = {lane["job_id"]: lane for lane in lanes}
    if len(by_id) != len(lanes) or root not in by_id:
        return False
    for lane in lanes:
        if lane["root_job_id"] != root:
            return False
        if lane["job_id"] == root:
            if lane["parent_job_id"] is not None or lane["depth"] != 0:
                return False
        else:
            parent = by_id.get(lane["parent_job_id"])
            if parent is None or lane["depth"] != parent["depth"] + 1:
                return False
    return True


def observe_root_lanes(runtime: Runtime, root_job_id: str, *, max_rows: int = 64) -> dict:
    """Observe recorded Executive lanes; never choose an action target or open a path."""
    try:
        root = _token(root_job_id)
    except ValueError:
        return _document(None, status="REFUSED", issues=("INVALID_ROOT",))
    if type(max_rows) is not int or not 1 <= max_rows <= MAX_ROWS:
        return _document(root, status="REFUSED", issues=("INVALID_ROW_LIMIT",))
    if not isinstance(runtime, Runtime):
        return _document(root, status="REFUSED", issues=("INVALID_RUNTIME",))
    if runtime.store.create or runtime.store.existing_writable:
        return _document(root, status="REFUSED", issues=("READ_ONLY_RUNTIME_REQUIRED",))
    exhausted = False
    try:
        with runtime.store.read() as connection:
            steps = 0
            interval = max(1, min(1000, MAX_SQL_STEPS))

            def budget() -> int:
                nonlocal steps, exhausted
                steps += interval
                exhausted = steps >= MAX_SQL_STEPS
                return int(exhausted)

            connection.set_progress_handler(budget, interval)
            try:
                root_row = connection.execute(
                    "SELECT " + _JOB_COLUMNS + " FROM jobs j WHERE j.job_id=?", (root,)
                ).fetchone()
                if root_row is None:
                    return _document(root, status="UNAVAILABLE", issues=("ROOT_NOT_FOUND",))
                if (root_row["parent_job_id"] is not None or root_row["root_job_id"] != root
                        or root_row["depth"] != 0):
                    return _document(root, status="REFUSED", issues=("NOT_AN_EXACT_ROOT",))
                rows = connection.execute(
                    "SELECT " + _JOB_COLUMNS + "," + _ATTEMPT_COLUMNS
                    + " FROM jobs j " + _JOIN
                    + " WHERE j.root_job_id=? ORDER BY j.depth,j.job_id LIMIT ?",
                    (root, max_rows + 1),
                ).fetchall()
            finally:
                connection.set_progress_handler(None, 0)
        truncated = len(rows) > max_rows
        lanes = [_lane(row) for row in rows[:max_rows]]
        if not _valid_graph(lanes, root):
            return _document(root, status="REFUSED", issues=("SOURCE_LINEAGE_INVALID",))
        issues = sorted({code for lane in lanes for code in lane["issues"]})
        if truncated:
            issues.append("ROW_LIMIT_REACHED")
        result = _document(root, status="PARTIAL" if issues else "OBSERVED", lanes=lanes,
            completeness="truncated" if truncated else "complete", issues=tuple(issues))
        if len(json.dumps(result, sort_keys=True).encode("utf-8")) > MAX_RESPONSE_BYTES:
            return _document(root, status="UNAVAILABLE", issues=("RESPONSE_LIMIT_REACHED",))
        return result
    except (RuntimeProofError, sqlite3.Error, OSError):
        code = "QUERY_BUDGET_EXCEEDED" if exhausted else "RUNTIME_UNAVAILABLE"
        return _document(root, status="UNAVAILABLE", issues=(code,))
    except (ValueError, TypeError, KeyError, IndexError):
        return _document(root, status="REFUSED", issues=("SOURCE_RECORD_INVALID",))
