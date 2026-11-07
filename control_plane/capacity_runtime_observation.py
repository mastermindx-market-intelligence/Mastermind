"""Bounded, read-only recorded workload and first-claim timing from Runtime.

One existing Runtime acquisition owns both Job and Attempt pages. A recorded
creation-to-first-claim interval includes admission/dependency/scheduled waiting;
it is not ready-queue service time, model reasoning time or desktop occupancy.
Rows are deliberately unclassified: proof/acceptance fixtures are not evidence
of ordinary or busy demand. No clock, provider, persistence or admission is used.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import re

from control_plane.executive_runtime import Attempt, Job, Runtime

SCHEMA = "mastermind.capacity_runtime_workload.v1"
MAX_JOBS = 128
MAX_ATTEMPTS = 512
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z")


def _stamp(value):
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        raise ValueError("RECORDED_TIMESTAMP_UNAVAILABLE")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("RECORDED_TIMESTAMP_UNAVAILABLE")
    return parsed


def _counts(values):
    return dict(sorted(Counter(values).items()))


def _summary(rows):
    samples = sorted(row["value"] for row in rows if row["state"] == "COMPLETED")
    return {
        "population": len(rows), "completed": len(samples),
        "unfinished": sum(row["state"] == "UNFINISHED" for row in rows),
        "unavailable": sum(row["state"] == "UNAVAILABLE" for row in rows),
        "p50": samples[math.ceil(len(samples) * .5) - 1] if samples else None,
        "p95": samples[math.ceil(len(samples) * .95) - 1] if samples else None,
        "max": samples[-1] if samples else None,
        "quantile_method": "NEAREST_RANK",
        "scope": "COMPLETED_CREATION_TO_FIRST_CLAIM_SAMPLES_ONLY_NOT_READY_QUEUE_SLO",
    }


def _first_claim(job, attempts, *, attempts_truncated):
    row = {"job_id": job.job_id, "attempt_id": None, "state": "UNAVAILABLE",
           "value": None, "reason": None}
    try:
        created = _stamp(job.created_at)
        if not attempts_truncated and len(attempts) != job.attempt_count:
            raise ValueError("ATTEMPT_COUNT_DISAGREEMENT")
        if len(attempts) > job.attempt_count:
            raise ValueError("ATTEMPT_COUNT_DISAGREEMENT")
        first = [attempt for attempt in attempts if attempt.attempt_number == 1]
        if not first:
            if job.attempt_count == 0 and not attempts and job.status.value == "QUEUED":
                row.update(state="UNFINISHED", reason="FIRST_CLAIM_NOT_RECORDED")
            else:
                row["reason"] = "ATTEMPT_PAGE_INCOMPLETE" if attempts_truncated else "FIRST_CLAIM_UNAVAILABLE"
            return row
        if len(first) != 1:
            raise ValueError("FIRST_CLAIM_CARDINALITY_INVALID")
        elapsed = _stamp(first[0].started_at) - created
        if elapsed.total_seconds() < 0:
            raise ValueError("RECORDED_CLOCK_ORDER_INVALID")
        milliseconds = elapsed.days * 86_400_000 + elapsed.seconds * 1000 + elapsed.microseconds // 1000
        row.update(attempt_id=first[0].attempt_id, state="COMPLETED", value=milliseconds)
    except ValueError as exc:
        row["reason"] = str(exc) if str(exc) in {
            "RECORDED_TIMESTAMP_UNAVAILABLE", "ATTEMPT_COUNT_DISAGREEMENT",
            "FIRST_CLAIM_CARDINALITY_INVALID", "RECORDED_CLOCK_ORDER_INVALID",
        } else "RECORDED_TIMESTAMP_UNAVAILABLE"
    return row


def observe_runtime_workload(
    runtime: Runtime, *, max_jobs: int = MAX_JOBS, max_attempts: int = MAX_ATTEMPTS,
) -> dict:
    """Read at most two SQL-bounded pages from one canonical stable snapshot.

The attempted page is restricted to the selected Jobs. Overflow is retained as
partial coverage, never silently promoted to a complete Runtime/demand census.
Only counts, identifiers and recorded timing leave this consumer; no objective,
result, account/credential, lease token or arbitrary metadata is projected.
"""
    if (type(max_jobs) is not int or not 1 <= max_jobs <= MAX_JOBS
            or type(max_attempts) is not int or not 1 <= max_attempts <= MAX_ATTEMPTS):
        raise ValueError("INVALID_RUNTIME_OBSERVATION_BOUND")
    report = {
        "schema": SCHEMA, "mode": "point_observation", "writes_applied": False,
        "campaign_qualified": False, "installed_coverage_claimed": False,
        "ordinary_busy_classification_claimed": False,
        "population_scope": "BOUNDED_RUNTIME_ROWS_UNCLASSIFIED_INCLUDES_PROOF_ACCEPTANCE_AND_PRODUCTION",
        "clock_scope": "RECORDED_RUNTIME_CREATION_TO_FIRST_CLAIM_NOT_MODEL_OR_WORKER_DURATION",
        "recorded_timestamp_resolution_ms": 1000,
        "snapshot_consistency": "ONE_RUNTIME_OWNED_READ_SNAPSHOT_SEPARATE_FROM_WAKE_SNAPSHOT",
        "source_provenance": "RUNTIME_OWNER_METADATA_NOT_INSTALLED_ATTESTATION",
        "bounds": {"jobs": max_jobs, "attempts": max_attempts, "max_owner_pages": 2},
        "state": "UNAVAILABLE", "degraded": [], "snapshot_digest": None,
        "coverage": None, "jobs_by_status": None, "attempts_by_status": None,
        "review_jobs_by_status": None, "review_required_jobs_by_status": None,
        "recorded_creation_to_first_claim_ms": None, "first_claims": [],
    }
    try:
        with runtime.bounded_acquisition() as acquisition:
            job_page = acquisition.list_jobs(limit=max_jobs)
            jobs = job_page.items
            if len(jobs) > max_jobs or any(not isinstance(job, Job) for job in jobs):
                raise ValueError("OWNER_PAGE_INVALID")
            by_id = {job.job_id: job for job in jobs}
            if len(by_id) != len(jobs):
                raise ValueError("OWNER_PAGE_INVALID")
            if jobs:
                attempt_page = acquisition.list_attempts(limit=max_attempts, job_ids=tuple(by_id))
                attempts = attempt_page.items
                attempts_truncated = attempt_page.next_cursor is not None
            else:
                attempts, attempts_truncated = (), False
            if len(attempts) > max_attempts or any(not isinstance(a, Attempt) for a in attempts):
                raise ValueError("OWNER_PAGE_INVALID")
        jobs_truncated = job_page.next_cursor is not None
        selected = {job.job_id: [] for job in jobs}
        attempt_ids, attempt_numbers = set(), set()
        for attempt in attempts:
            identity = (attempt.job_id, attempt.attempt_number)
            if (attempt.job_id not in selected or attempt.attempt_id in attempt_ids
                    or type(attempt.attempt_number) is not int or attempt.attempt_number < 1
                    or attempt.attempt_number > by_id[attempt.job_id].attempt_count
                    or identity in attempt_numbers):
                raise ValueError("OWNER_ATTEMPT_JOIN_INVALID")
            attempt_ids.add(attempt.attempt_id)
            attempt_numbers.add(identity)
            selected[attempt.job_id].append(attempt)
        for job in jobs:
            if type(job.attempt_count) is not int or job.attempt_count < 0:
                raise ValueError("OWNER_ATTEMPT_JOIN_INVALID")
        rows = [_first_claim(job, selected[job.job_id], attempts_truncated=attempts_truncated)
                for job in sorted(jobs, key=lambda item: item.job_id)]
        degraded = []
        if jobs_truncated:
            degraded.append("JOB_PAGE_INCOMPLETE")
        if attempts_truncated:
            degraded.append("ATTEMPT_PAGE_INCOMPLETE")
        if any(row["state"] == "UNAVAILABLE" for row in rows):
            degraded.append("FIRST_CLAIM_SAMPLES_UNAVAILABLE")
        facts = {
            "jobs": sorted((job.job_id, job.root_job_id, job.status.value, job.created_at,
                job.attempt_count, job.review_required, job.reviews_job_id, job.orchestration_role)
                for job in jobs),
            "attempts": sorted((a.attempt_id, a.job_id, a.attempt_number, a.status.value, a.started_at)
                               for a in attempts),
            "jobs_truncated": jobs_truncated, "attempts_truncated": attempts_truncated,
        }
        digest = hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(",", ":"),
                                          allow_nan=False).encode()).hexdigest()
        report.update(
            state="PARTIAL" if degraded else "OBSERVED" if jobs else "EMPTY",
            degraded=degraded, snapshot_digest=digest,
            coverage={"jobs_observed": len(jobs), "attempts_observed": len(attempts),
                      "jobs_truncated": jobs_truncated, "attempts_truncated": attempts_truncated,
                      "selected_pages_complete": not jobs_truncated and not attempts_truncated,
                      "complete_company_demand_census": False},
            jobs_by_status=_counts(job.status.value for job in jobs),
            attempts_by_status=_counts(a.status.value for a in attempts),
            review_jobs_by_status=_counts(job.status.value for job in jobs
                if job.reviews_job_id is not None or job.orchestration_role == "review"),
            review_required_jobs_by_status=_counts(job.status.value for job in jobs if job.review_required),
            recorded_creation_to_first_claim_ms=_summary(rows), first_claims=rows,
        )
    except Exception:
        # No raw exception text or half-read rows escape an owner acquisition
        # failure. The caller retains this typed unavailable point and rc2.
        report["degraded"] = ["RUNTIME_WORKLOAD_ACQUISITION_UNAVAILABLE"]
    return report
