"""Regenerate the work-queue fixtures in tests/fixtures/workspace_work_queue_v1/.

Run with::

    python3 -B tests/fixtures/workspace_work_queue_v1/_regenerate.py

Four fixtures are produced:

* ``available.json`` — a healthy ``AVAILABLE`` projection over four
  representative rows (QUEUED, RUNNING, COMPLETED, FAILED) with no
  producer evidence supplied.
* ``unavailable.json`` — the composer's ``UNAVAILABLE`` branch over a
  degraded bounded acquisition (B2: ``coverage.completeness = "PARTIAL"``).
* ``effect_exception.json`` — the REAL route path: queue-level
  ``effect_exception.value == "EFFECT_UNKNOWN"`` from control_room
  autonomy, but NO ``effects`` map is supplied.  The fixture therefore
  carries ``reason_codes == ["effect_not_row_attributed"]`` (B3).
* ``effect_exception_row_attributed.json`` — composer-only case where an
  ``effects`` map is supplied; the row-attributed exception removes the
  reason code so the byte-identity test distinguishes the two paths.

The fixtures are byte-stable inputs the product integrator consumes. The
matching tests
(``tests/test_work_queue_projection.py::test_r6_bytes_match_deterministic_*``)
re-run the composer against the same root-list inputs and assert
byte-identity.  This script is the deterministic producer — keep its
inputs frozen; do not let it read clocks or files.

Note: ``generated_at`` is the composer wall-clock — every fixture sets it
to the same frozen constant below so two regenerations are byte-identical.
"""
from __future__ import annotations

import json
from pathlib import Path

from control_plane.work_queue_projection import compose_work_queue_v1

HERE = Path(__file__).parent

GENERATED_AT = "2026-09-23T00:00:00Z"
EVIDENCE_AS_OF = "2026-09-23T00:01:00Z"
SOURCE_IDENTITY = "b" * 64
SNAPSHOT_DIGEST = "a" * 64

ACQUISITION = {
    "schema": "mastermind.fabric_runtime_acquisition.v1",
    "query": {"kind": "root_discovery"},
    "owner": "executive_runtime",
    "snapshot_digest": SNAPSHOT_DIGEST,
    "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                "attempts_total": 340, "creation_events_per_job": 1},
    "truncation": {"jobs": False, "attempt_job_ids": [], "roots": False,
                   "projection": False},
    "provenance": {"state": "COMPLETE", "unjoined_job_ids": []},
    "generation": {"schema": "mastermind.runtime_read_observation.v1",
                   "state": "SAME", "source_identity": SOURCE_IDENTITY,
                   "before": 1, "after": 1},
}

ACQUISITION_PARTIAL = {
    "schema": "mastermind.fabric_runtime_acquisition.v1",
    "query": {"kind": "root_discovery"},
    "owner": "executive_runtime",
    "snapshot_digest": SNAPSHOT_DIGEST,
    "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                "attempts_total": 340, "creation_events_per_job": 1},
    "truncation": {"jobs": False, "attempt_job_ids": [], "roots": True,
                   "projection": False},
    "provenance": {"state": "PARTIAL", "unjoined_job_ids": ["JOB-7"]},
    "generation": {"schema": "mastermind.runtime_read_observation.v1",
                   "state": "SAME", "source_identity": SOURCE_IDENTITY,
                   "before": 1, "after": 1},
}

ACQUISITION_DEGRADED = {
    "schema": "mastermind.fabric_runtime_acquisition.v1",
    "query": {"kind": "root_discovery"},
    "owner": "executive_runtime",
    "snapshot_digest": None,
    "budgets": {"roots": 64, "jobs": 17, "attempts_per_job": 20,
                "attempts_total": 340, "creation_events_per_job": 1},
    "truncation": {"jobs": False, "attempt_job_ids": [], "roots": False,
                   "projection": False},
    "provenance": {"state": "COMPLETE", "unjoined_job_ids": []},
    "generation": {"schema": "mastermind.runtime_read_observation.v1",
                   "state": "SAME", "source_identity": SOURCE_IDENTITY,
                   "before": 1, "after": 1},
}


def _row(job_id, status, *, depth=0, role="aggregation"):
    return {"job_id": job_id, "status": status, "depth": depth,
            "parent_job_id": None, "orchestration_role": role}


# Available fixture: four deterministic rows exercising the lifecycle table.
AVAILABLE_ROOT_LIST = {
    "schema": "mastermind.fabric_job_root_list.v2",
    "generated_at": GENERATED_AT,
    "runtime": {"root": "/tmp/fake", "db_present": True, "identity": None,
                "acquisition": ACQUISITION},
    "roots": [
        _row("JOB-1", "QUEUED"),
        _row("JOB-2", "RUNNING"),
        _row("JOB-3", "COMPLETED"),
        _row("JOB-4", "FAILED"),
    ],
    "count": 4,
    "total": 4,
    "truncated": False,
    "degraded": [],
}

# Unavailable fixture: degraded bounded acquisition.  B2 forces the
# coverage envelope to claim PARTIAL completeness (count=0, total=None,
# truncated from root_list) — never COMPLETE on a degraded source.
UNAVAILABLE_ROOT_LIST = {
    "schema": "mastermind.fabric_job_root_list.v2",
    "generated_at": GENERATED_AT,
    "runtime": {"root": "/tmp/fake", "db_present": True, "identity": None,
                "acquisition": ACQUISITION_DEGRADED},
    "roots": [],
    "count": 0,
    "total": None,
    "truncated": False,
    "degraded": ["bounded acquisition unavailable: read failed"],
}

# effect_exception fixture (B3 real path): control_room autonomy reports
# EFFECT_UNKNOWN on one row but NO ``effects`` producer map is supplied.
# The queue-level exception is EFFECT_UNKNOWN; the document carries
# reason_codes=["effect_not_row_attributed"] because no per-row effect
# attestation exists.
EFFECT_CONTROL_ROOM = {
    "schema": "mastermind.chairman_control_room.v1",
    "generated_at": GENERATED_AT,
    "autonomy": {
        "schema": "mastermind.autonomy_control_room.v1",
        "generated_at": GENERATED_AT,
        "responsibilities": [
            {"responsibility_ref": "WS:ONE", "root_job_id": "JOB-1",
             "placement_state": {"value": "EFFECT_UNKNOWN",
                                  "observable": True,
                                  "reason": "worker_effect_unknown"}},
        ],
    },
}

EFFECT_EXCEPTION_ROOT_LIST = {
    "schema": "mastermind.fabric_job_root_list.v2",
    "generated_at": GENERATED_AT,
    "runtime": {"root": "/tmp/fake", "db_present": True, "identity": None,
                "acquisition": ACQUISITION_PARTIAL},
    "roots": [
        _row("JOB-1", "RUNNING"),
        _row("JOB-7", "QUEUED"),
    ],
    "count": 2,
    "total": None,
    "truncated": True,
    "degraded": [],
}

EFFECTS_INPUT = {"JOB-1": {"state": "EFFECT_UNKNOWN", "carrier": "agent-os:effect",
                          "evidence_ref": "agent-os:effect",
                          "observed_at": "2026-09-23T00:00:00Z"}}


def _dump(name, document):
    target = HERE / name
    target.write_text(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=False) + "\n",
                       encoding="utf-8")


def main():
    available = compose_work_queue_v1(AVAILABLE_ROOT_LIST,
                                       generated_at=GENERATED_AT)
    _dump("available.json", available)
    unavailable = compose_work_queue_v1(UNAVAILABLE_ROOT_LIST,
                                         generated_at=GENERATED_AT)
    _dump("unavailable.json", unavailable)
    # B3: real route path — no effects map supplied, queue-level
    # EFFECT_UNKNOWN surfaces as reason_codes=["effect_not_row_attributed"].
    effect_exception = compose_work_queue_v1(EFFECT_EXCEPTION_ROOT_LIST,
                                              control_room=EFFECT_CONTROL_ROOM,
                                              generated_at=GENERATED_AT)
    _dump("effect_exception.json", effect_exception)
    # Composer-only case: the producer supplies an effects map; the
    # exception is row-attributed and the reason code is absent.
    effect_exception_row = compose_work_queue_v1(EFFECT_EXCEPTION_ROOT_LIST,
                                                  control_room=EFFECT_CONTROL_ROOM,
                                                  effects=EFFECTS_INPUT,
                                                  evidence_as_of=EVIDENCE_AS_OF,
                                                  generated_at=GENERATED_AT)
    _dump("effect_exception_row_attributed.json", effect_exception_row)


if __name__ == "__main__":
    main()