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
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
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


def find_prior_merge_group_proof(
    *, repository: str, head_sha: str,
    current_event: str, current_ref: str, current_run_id: int,
    expected_workflow_id: int, read,
) -> tuple[bool, str]:
    """Compose bounded pre-existing GitHub GET reads; never own their transport.

    A true result is only evidence for a future, separately reviewed CI caller;
    it does not start, stop, skip or authorize anything. `read(path)` must be an
    already-authorized exact-GET transport that raises on missing/denied reads.
    No retry or alternate token/account occurs in this function.
    """
    if current_event != "push" or current_ref != "refs/heads/master":
        return False, "NOT_MASTER_PUSH"
    if (
        not isinstance(repository, str) or not _REPOSITORY.fullmatch(repository)
        or not isinstance(head_sha, str) or not _SHA.fullmatch(head_sha)
        or not _positive_int(current_run_id)
        or not _positive_int(expected_workflow_id)
        or not callable(read)
    ):
        return False, "IDENTITY_INVALID"
    prefix = f"repos/{repository}"
    try:
        current = read(f"{prefix}/actions/runs/{current_run_id}")
    except Exception:
        return False, "CURRENT_RUN_READ_UNAVAILABLE"
    if (
        not isinstance(current, dict)
        or current.get("id") != current_run_id
        or current.get("workflow_id") != expected_workflow_id
        or current.get("head_sha") != head_sha
        or current.get("event") != "push"
        or current.get("head_branch") != "master"
        or current.get("path") != ".github/workflows/ci.yml"
        or not isinstance(current.get("repository"), dict)
        or current["repository"].get("full_name") != repository
        or _timestamp(current.get("created_at")) is None
    ):
        return False, "CURRENT_PUSH_IDENTITY_UNVERIFIED"
    try:
        listings = read(f"{prefix}/actions/runs?head_sha={head_sha}&per_page=100")
    except Exception:
        return False, "RUN_LIST_READ_UNAVAILABLE"
    if not isinstance(listings, dict) or not isinstance(listings.get("workflow_runs"), list):
        return False, "RUN_LIST_INVALID"
    runs = listings["workflow_runs"]
    if type(listings.get("total_count")) is not int or len(runs) != listings["total_count"] or not 1 <= len(runs) <= 100:
        return False, "RUN_LIST_TRUNCATED"
    if any(not isinstance(row, dict) for row in runs):
        return False, "RUN_LIST_INVALID"
    if sum(row.get("id") == current_run_id for row in runs) != 1:
        return False, "CURRENT_RUN_NOT_IN_COVERAGE"
    candidates = [row for row in runs if (
        row.get("event") == "merge_group" and row.get("head_sha") == head_sha
        and row.get("workflow_id") == expected_workflow_id
    )]
    if len(candidates) != 1 or not _positive_int(candidates[0].get("id")):
        return False, "PRIOR_RUN_UNAVAILABLE_OR_AMBIGUOUS"
    original_id = candidates[0]["id"]
    if original_id == current_run_id:
        return False, "PRIOR_RUN_IDENTITY_REUSED"
    try:
        original = read(f"{prefix}/actions/runs/{original_id}")
        jobs = read(f"{prefix}/actions/runs/{original_id}/jobs?per_page=100")
    except Exception:
        return False, "PRIOR_EVIDENCE_READ_UNAVAILABLE"
    if not isinstance(original, dict) or original.get("id") != original_id:
        return False, "PRIOR_RUN_IDENTITY_CHANGED"
    return qualify_merge_group_proof(
        repository=repository, head_sha=head_sha,
        current_event=current_event, current_ref=current_ref,
        current_created_at=current["created_at"],
        expected_workflow_id=expected_workflow_id,
        workflow_run=original, workflow_jobs=jobs,
    )


_GH_READ_ENDPOINT = re.compile(
    r"repos/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*/actions/runs"
    r"(?:/[1-9][0-9]*(?:/jobs\?per_page=100)?"
    r"|\?head_sha=[0-9a-f]{40}&per_page=100)\Z"
)


def read_json_via_existing_gh(endpoint: str, *, run=None, executable: str | None = None) -> dict:
    """One bounded GET through the existing GitHub CLI identity and rate owner.

    No alternate token, credential persistence, retry, mutation, polling worker,
    or new transport registration is introduced. Missing access fails closed
    to *ordinary full CI*, not to a skipped test. This is inactive until an
    existing CI owner explicitly integrates and qualifies its calling site.
    """
    import json
    import shutil
    import subprocess

    if not isinstance(endpoint, str) or not _GH_READ_ENDPOINT.fullmatch(endpoint):
        raise ValueError("ENDPOINT_NOT_ALLOWED")
    binary = executable if executable is not None else shutil.which("gh")
    if not isinstance(binary, str) or not binary.startswith("/"):
        raise ValueError("GH_CLI_UNAVAILABLE")
    perform = subprocess.run if run is None else run
    arguments = [
        binary, "api", "--hostname", "github.com", "--method", "GET",
        "--header", "X-GitHub-Api-Version: 2022-11-28", endpoint,
    ]
    try:
        response = perform(
            arguments, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("PROVIDER_GET_UNAVAILABLE") from None
    if response.returncode != 0:
        raise ValueError("PROVIDER_GET_REFUSED")
    body = response.stdout
    if not isinstance(body, str) or len(body.encode("utf-8")) > 2_000_000:
        raise ValueError("PROVIDER_BODY_UNQUALIFIED")
    try:
        payload = json.loads(body)
    except ValueError:
        raise ValueError("PROVIDER_JSON_INVALID") from None
    if not isinstance(payload, dict):
        raise ValueError("PROVIDER_JSON_INVALID")
    return payload


def _checkout_identity_proven(expected_head: str, *, root=None) -> bool:
    """Prove checkout HEAD and all tracked source match the workflow's SHA.

    The event environment alone is not source integrity. A stale checkout or
    tracked worktree mutation must execute full pytest instead of reusing the
    previous native-queue result. No network, git fetch or checkout mutation.
    """
    import subprocess

    if not isinstance(expected_head, str) or not _SHA.fullmatch(expected_head):
        return False
    commands = (
        ["git", "rev-parse", "--verify", "HEAD"],
        ["git", "diff", "--quiet", "HEAD", "--"],
    )
    for index, command in enumerate(commands):
        try:
            record = subprocess.run(
                command, cwd=root, capture_output=True, text=True,
                timeout=10, stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if record.returncode != 0:
            return False
        if index == 0 and record.stdout.strip() != expected_head:
            return False
    return True


def possible_same_sha_reuse_for_ci_runner(
    *, environ=None, read=None,
) -> tuple[bool, str]:
    """Inactive opt-in environment adapter for the existing Mastermind CI owner.

    No scheduled or external state is introduced. Until `ci_parallel_shard`
    explicitly calls this in a separately qualified release, its answer cannot
    skip anything. A missing GitHub-token read capability means full CI, never
    another credential/account. Every non-push event remains unchanged.
    """
    import os

    values = os.environ if environ is None else environ
    if not hasattr(values, "get"):
        return False, "CALLER_ENVIRONMENT_INVALID"
    if values.get("GITHUB_EVENT_NAME") != "push" or values.get("GITHUB_REF") != "refs/heads/master":
        return False, "NOT_MASTER_PUSH"
    if values.get("GITHUB_REPOSITORY") != "mastermindx-market-intelligence/Mastermind":
        return False, "REPOSITORY_UNQUALIFIED"
    if values.get("GITHUB_WORKFLOW") != "CI":
        return False, "WORKFLOW_UNQUALIFIED"
    head = values.get("GITHUB_SHA")
    raw_id = values.get("GITHUB_RUN_ID")
    if (
        not isinstance(head, str) or not _SHA.fullmatch(head)
        or not isinstance(raw_id, str) or not raw_id.isdecimal()
        or not isinstance(values.get("GH_TOKEN"), str)
        or not values.get("GH_TOKEN")
    ):
        return False, "IDENTITY_OR_READ_ACCESS_MISSING"
    try:
        current_run_id = int(raw_id)
    except (ValueError, OverflowError):
        return False, "RUN_ID_INVALID"
    if not _positive_int(current_run_id):
        return False, "RUN_ID_INVALID"
    if not _checkout_identity_proven(head):
        return False, "LOCAL_CHECKOUT_HEAD_OR_TRACKED_TREE_UNVERIFIED"
    return find_prior_merge_group_proof(
        repository=values["GITHUB_REPOSITORY"], head_sha=head,
        current_event=values["GITHUB_EVENT_NAME"], current_ref=values["GITHUB_REF"],
        current_run_id=current_run_id, expected_workflow_id=324108847,
        read=read_json_via_existing_gh if read is None else read,
    )
