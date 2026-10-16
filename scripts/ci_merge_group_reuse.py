"""Pure fail-closed provenance check for *possible* same-SHA postmerge CI reuse.

NO runtime consumer is enabled by this module. The protected CI job and native
merge queue remain the only existing release owners. This can only report that
four exact-run GitHub Actions jobs successfully checked the *same* immutable
commit before a later master push. It never replaces validation on an unknown
push and never accepts PR-head success as merge-group proof.

The GitHub API transport, authentication and any workflow use must be separately
qualified before this pure predicate may influence whether tests execute.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_EXPECTED_JOBS = frozenset({"pytest shard 0", "pytest shard 1", "pytest shard 2", "test"})
_REQUIRED_STEPS = {
    "pytest shard 0": (
        "Verify Paper direct pinned MCP SDK",
        "Verify private Fabric HTTP compatibility and incumbent backend lifetime",
        "Compile source",
        "Validate shell scripts",
        "Run repository test shard",
    ),
    "pytest shard 1": ("Run repository test shard",),
    "pytest shard 2": ("Run repository test shard",),
    "test": ("Run repository test gate",),
}


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or len(value) > 48:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else None


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def qualify_merge_group_proof(
    *, repository: str, head_sha: str, current_event: str,
    current_ref: str, current_created_at: str,
    expected_workflow_id: int, workflow_run: object, workflow_jobs: object,
) -> tuple[bool, str]:
    """Reject any absent, mismatched, truncated or post-push external evidence.

    Inputs are snapshots fetched by an already-authorized GitHub API reader.
    This predicate performs no network, scheduling, release or source writes.
    An eligible result does NOT, by itself, grant permission to skip CI.
    """
    if (
        not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository)
        or not isinstance(head_sha, str) or not _SHA.fullmatch(head_sha)
        or not _positive_int(expected_workflow_id)
    ):
        return False, "IDENTITY_INVALID"
    if current_event != "push" or current_ref != "refs/heads/master":
        return False, "NOT_MASTER_PUSH"
    event_time = _timestamp(current_created_at)
    if event_time is None:
        return False, "PUSH_CLOCK_UNKNOWN"
    if not isinstance(workflow_run, dict) or not isinstance(workflow_jobs, dict):
        return False, "EVIDENCE_INVALID"
    run = workflow_run
    if any(run.get(k) != v for k, v in (
        ("head_sha", head_sha), ("event", "merge_group"),
        ("status", "completed"), ("conclusion", "success"),
        ("path", ".github/workflows/ci.yml"),
        ("workflow_id", expected_workflow_id),
    )):
        return False, "RUN_NOT_QUALIFIED"
    if not _positive_int(run.get("id")) or type(run.get("run_attempt")) is not int or run.get("run_attempt") != 1:
        return False, "RUN_GENERATION_INVALID"
    if (
        not isinstance(run.get("repository"), dict)
        or run["repository"].get("full_name") != repository
        or not isinstance(run.get("head_repository"), dict)
        or run["head_repository"].get("full_name") != repository
        or not isinstance(run.get("head_branch"), str)
        or not run["head_branch"].startswith("gh-readonly-queue/master/")
    ):
        return False, "NOT_CANONICAL_QUEUE"
    created_at, concluded_at = _timestamp(run.get("created_at")), _timestamp(run.get("updated_at"))
    if created_at is None or concluded_at is None or not (created_at <= concluded_at <= event_time):
        return False, "RUN_CHRONOLOGY_UNPROVEN"
    jobs = workflow_jobs.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 4 or workflow_jobs.get("total_count") != 4:
        return False, "JOB_COVERAGE_INCOMPLETE"
    names: dict[str, dict[str, Any]] = {}
    job_ids: set[int] = set()
    for candidate in jobs:
        if not isinstance(candidate, dict):
            return False, "JOB_INVALID"
        name, job_id = candidate.get("name"), candidate.get("id")
        if not isinstance(name, str) or name in names or not _positive_int(job_id) or job_id in job_ids:
            return False, "JOB_IDENTITY_INVALID"
        names[name] = candidate
        job_ids.add(job_id)
    if set(names) != _EXPECTED_JOBS:
        return False, "REQUIRED_JOBS_MISSING"
    for name, job in names.items():
        if type(job.get("run_attempt")) is not int:
            return False, "JOB_GENERATION_INVALID"
        if any(job.get(k) != value for k, value in (
            ("head_sha", head_sha), ("run_id", run["id"]),
            ("run_attempt", 1), ("status", "completed"), ("conclusion", "success"),
        )):
            return False, "JOB_GENERATION_INVALID"
        started, completed = _timestamp(job.get("started_at")), _timestamp(job.get("completed_at"))
        if started is None or completed is None or not (created_at <= started <= completed <= concluded_at <= event_time):
            return False, "JOB_CHRONOLOGY_UNPROVEN"
        steps = job.get("steps")
        if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
            return False, "JOB_STEPS_INVALID"
        for step_name in _REQUIRED_STEPS[name]:
            matches = [s for s in steps if s.get("name") == step_name]
            if len(matches) != 1 or matches[0].get("status") != "completed" or matches[0].get("conclusion") != "success":
                return False, "MANDATORY_STEP_UNPROVEN"
    return True, "PRIOR_EXACT_MERGE_GROUP_CI_PROVEN"
