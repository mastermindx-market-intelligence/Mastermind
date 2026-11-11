"""Offline CI timing report for one captured GitHub Actions workflow-run snapshot.

#917/#1957 P3.O3: turn an already-captured ``run`` object (unmodified GitHub
REST workflow-run) plus the COMPLETE ``jobs`` response into a deterministic,
JSON-safe timing profile. Capture stays with the existing authenticated
readers; this module never opens a network connection, dispatches, cancels or
writes authoritative CI state — it is an offline derived report, not a service,
telemetry store, scheduler or gate.

Frozen interface:
  - ``build_profile(snapshot) -> JSON-safe dict`` (standard library only)
  - ``python -m scripts.ci_run_profile INPUT.json`` prints the profile JSON;
    ``INPUT.json`` may be ``-`` to read stdin. No output file is ever written.
  - Input reads are bounded to ``MAX_INPUT_BYTES`` (8 MiB).

Fail-closed: mismatched run id / head SHA / run attempt evidence, duplicate job
ids, naive or unparseable execution timestamps and inverted execution durations
raise ``ProfileError``. A completed skipped job with empty steps and no runner
has no execution interval: retain its raw metadata and leave execution timings
unknown. Unqualified synthetic completion metadata keeps completion unknown.
Missing identity fields, missing timestamps, pending jobs and
page-truncated job lists never become zeros or "complete" — they surface as
``evidence_gaps`` and the affected numbers stay ``null``.

Deliberately NOT computed: runner queue time (no queued_at in the jobs list),
job dependencies or a critical path, billing cost, and any achieved elapsed-
time reduction. ``updated_at`` is never used as a completion timestamp. A CI
success never means the underlying feature is delivered or accepted.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone

MAX_INPUT_BYTES = 8 * 1024 * 1024  # bounded read: 8 MiB
SHARD_STEP_NAME = "Run repository test shard"  # exact existing ci.yml step name
PROFILE_SCHEMA = "ci-run-profile/1"

USAGE = "usage: python -m scripts.ci_run_profile INPUT.json   (INPUT '-' reads stdin)"

_LIMITATIONS = (
    "runner queue time is not observable: no queued_at in the jobs list; start offsets measure"
    " job start relative to workflow creation, not runner assignment",
    "job dependencies (needs:) are not in this snapshot; no critical path is inferred",
    "offline derived report over one captured snapshot; no live API access, dispatch,"
    " cancellation or authoritative CI state",
    "a CI success never means the feature is delivered or accepted",
)

_IDENTITY_BASIS = (
    "run and job identity metadata and supplied repository URLs checked for consistency;"
    " missing identity remains unverified; an offline capture is not authenticated here"
)


class ProfileError(ValueError):
    """Invalid, contradictory or inverted snapshot evidence (fail closed)."""


def _fail(message: str) -> None:
    raise ProfileError(message)


def _cut(value: object, limit: int = 100) -> str:
    """Bounded string form so error text can never echo unbounded payloads."""
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _round(value: float) -> float:
    return round(value, 6)


def _identity(value, field, where, *, required=False):
    if value is None:
        if required:
            _fail(f"{where}: {field} missing; run identity requires real ids")
        return None
    if field in ("id", "run_id", "run_attempt"):
        valid = type(value) is int and value > 0
    elif field == "head_sha":
        valid = type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None
    else:
        valid = type(value) is str and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value) is not None
    if not valid:
        _fail(f"{where}: invalid {field} identity")
    return value


def _url(value, expected, where):
    if value is not None and (type(value) is not str or value != expected):
        _fail(f"{where}: URL contradicts repository/run/job identity")


def _parse_ts(value: object, where: str):
    """Parse an ISO8601 timestamp that must carry an explicit UTC offset.

    ``None`` stays ``None``: absence is an evidence gap, never a zero.
    Naive stamps, garbage strings and impossible offsets fail closed.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        _fail(f"{where}: timestamp must be an ISO8601 string, got {_cut(type(value).__name__)}")
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        _fail(f"{where}: invalid ISO8601 timestamp {_cut(value, 60)!r}")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(f"{where}: timestamp {_cut(value, 60)!r} carries no UTC offset (naive)")
    return parsed.astimezone(timezone.utc)


def _union_seconds(intervals):
    """Total length of the union of ``(start, end)`` aware-datetime intervals."""
    total = 0.0
    span_start = span_end = None
    for start, end in sorted(intervals):
        if span_end is None or start > span_end:
            if span_end is not None:
                total += (span_end - span_start).total_seconds()
            span_start, span_end = start, end
        elif end > span_end:
            span_end = end
    if span_end is not None:
        total += (span_end - span_start).total_seconds()
    return _round(total)


def build_profile(snapshot):
    """Build the deterministic JSON-safe timing profile for one captured run."""
    if not isinstance(snapshot, dict):
        _fail("snapshot must be a JSON object with 'run' and 'jobs'")
    run = snapshot.get("run")
    jobs_response = snapshot.get("jobs")
    if not isinstance(run, dict):
        _fail("snapshot['run'] must be the unmodified GitHub REST workflow-run object")
    if not isinstance(jobs_response, dict):
        _fail("snapshot['jobs'] must be the unmodified GitHub REST jobs response")
    total_count = jobs_response.get("total_count")
    jobs = jobs_response.get("jobs")
    if not isinstance(total_count, int) or isinstance(total_count, bool):
        _fail("snapshot['jobs']['total_count'] must be an integer")
    if not isinstance(jobs, list):
        _fail("snapshot['jobs']['jobs'] must be a list of job objects")
    if total_count < 0 or len(jobs) > total_count:
        _fail("jobs total_count contradicts the captured job count")

    gaps: list[str] = []
    repository = run.get("repository")
    if not isinstance(repository, dict):
        repository = {}

    # --- run-level identity; run.updated_at is deliberately never read as completion ---
    run_id = _identity(run.get("id"), "id", "workflow run", required=True)
    head_sha = _identity(run.get("head_sha"), "head_sha", "workflow run")
    run_attempt = _identity(run.get("run_attempt"), "run_attempt", "workflow run")
    repository_full_name = _identity(repository.get("full_name"), "repository", "workflow run")
    if repository_full_name is not None:
        api = f"https://api.github.com/repos/{repository_full_name}"
        web = f"https://github.com/{repository_full_name}"
        _url(repository.get("html_url"), web, "repository.html_url")
        _url(run.get("url"), f"{api}/actions/runs/{run_id}", "run.url")
        _url(run.get("html_url"), f"{web}/actions/runs/{run_id}", "run.html_url")
        jobs_url = f"{api}/actions/runs/{run_id}/jobs"
        # GitHub's attempt-specific run endpoint emits an attempt-qualified
        # jobs_url. Accept only that SAME validated attempt, never a foreign
        # attempt, a query-string variant, or rewritten captured evidence.
        if run_attempt is not None:
            attempt_jobs_url = f"{api}/actions/runs/{run_id}/attempts/{run_attempt}/jobs"
            if run.get("jobs_url") == attempt_jobs_url:
                jobs_url = attempt_jobs_url
        _url(run.get("jobs_url"), jobs_url, "run.jobs_url")
    created_at = _parse_ts(run.get("created_at"), "run.created_at")
    observed_at = _parse_ts(snapshot.get("observed_at"), "observed_at")
    if created_at is not None and observed_at is not None and observed_at < created_at:
        _fail("observed_at precedes run.created_at (inverted observation window)")

    # --- job-level identity cross-checks and timestamp validation ---
    seen_ids: dict[str, int] = {}
    job_run_ids: set = set()
    job_head_shas: set = set()
    job_attempts: set = set()
    missing_job_identity = False
    parsed_jobs = []
    nonexecuted_ids = set()
    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            _fail(f"jobs[{index}] must be a job object")
        job_id = _identity(job.get("id"), "id", f"jobs[{index}]", required=True)
        key = str(job_id)
        if key in seen_ids:
            _fail(f"duplicate job id {key}: jobs[{seen_ids[key]}] and jobs[{index}]")
        seen_ids[key] = index
        for field, run_value, collected in (
            ("run_id", run_id, job_run_ids),
            ("head_sha", head_sha, job_head_shas),
            ("run_attempt", run_attempt, job_attempts),
        ):
            job_value = _identity(job.get(field), field, f"job {key}")
            if job_value is None:
                missing_job_identity = True
                gaps.append(f"job {key} {field} absent; job identity unverified")
                continue
            collected.add(job_value)
            if run_value is not None and job_value != run_value:
                _fail(
                    f"job {key} ({_cut(job.get('name'))}) field {field} {_cut(job_value)!r}"
                    f" does not match workflow run {field} {_cut(run_value)!r}"
                )
        if repository_full_name is not None:
            _url(job.get("run_url"), f"{api}/actions/runs/{run_id}", f"job {key}.run_url")
            _url(job.get("url"), f"{api}/actions/jobs/{job_id}", f"job {key}.url")
            _url(job.get("html_url"), f"{web}/actions/runs/{run_id}/job/{job_id}", f"job {key}.html_url")
        # A job skipped, or cancelled before any runner took it, never executed: GitHub
        # reports no steps and no runner, and its timestamps are synthetic (real
        # job129715087606 was cancelled at 08:24:00 with started_at 08:24:01 and an
        # unexpanded matrix name). A cancelled job with a runner or steps stays strict.
        nonexecuted = (
            job.get("status") == "completed" and job.get("conclusion") in ("skipped", "cancelled")
            and job.get("steps") == []
            and all(job.get(field) is None for field in (
                "runner_id", "runner_name", "runner_group_id", "runner_group_name"
            ))
        )
        if nonexecuted:
            nonexecuted_ids.add(key)
            gaps.append(f"job {key} has only nonexecution evidence; raw synthetic timestamps retained, execution timings unknown")
            started = None
            try:
                completed = _parse_ts(job.get("completed_at"), f"job {key} synthetic completed_at")
            except ProfileError:
                completed = None
                gaps.append(f"job {key} synthetic completed_at is invalid; completion stays unknown")
            if completed is not None and (
                created_at is not None and completed < created_at
                or observed_at is not None and completed > observed_at
            ):
                completed = None
                gaps.append(f"job {key} synthetic completed_at is outside the observation window; completion stays unknown")
        else:
            started = _parse_ts(job.get("started_at"), f"job {key} ({_cut(job.get('name'))}) started_at")
            completed = _parse_ts(job.get("completed_at"), f"job {key} ({_cut(job.get('name'))}) completed_at")
        if started is not None and completed is not None and completed < started:
            _fail(f"job {key} ({_cut(job.get('name'))}): completed_at precedes started_at (inverted duration)")
        if created_at is not None and started is not None and started < created_at:
            _fail(f"job {key} ({_cut(job.get('name'))}): started_at precedes run.created_at (inverted start offset)")
        if created_at is not None and completed is not None and completed < created_at:
            _fail(f"job {key} ({_cut(job.get('name'))}): completed_at precedes run.created_at (inverted elapsed)")
        if observed_at is not None and any(t is not None and t > observed_at for t in (started, completed)):
            _fail(f"job {key}: timestamp follows observed_at (inverted observation window)")
        parsed_jobs.append((key, job, started, completed))

    for field, run_value, collected in (
        ("run_id", run_id, job_run_ids),
        ("head_sha", head_sha, job_head_shas),
        ("run_attempt", run_attempt, job_attempts),
    ):
        if len(collected) > 1:
            _fail(
                f"mixed {field} evidence across jobs: "
                f"{[_cut(value, 24) for value in sorted(str(v) for v in collected)]}"
            )
        if len(collected) == 1 and run_value is None:
            gaps.append(f"workflow run {field} absent; job evidence shows {_cut(next(iter(collected)), 24)}")
    if head_sha is None:
        gaps.append("workflow run head_sha absent; run identity not fully verified")
    if run_attempt is None:
        gaps.append("workflow run run_attempt absent; run identity not fully verified")
    if repository_full_name is None:
        gaps.append("run.repository.full_name absent; repository identity unverified")
    identity_verified = (
        None not in (head_sha, run_attempt, repository_full_name)
        and bool(jobs) and not missing_job_identity
    )

    # --- completeness, never inferred from updated_at or page counts alone ---
    page_complete = len(jobs) == total_count
    if not page_complete:
        gaps.append(
            f"jobs response is page-incomplete: total_count={total_count}"
            f" but {len(jobs)} job objects captured"
        )
    elif not jobs:
        gaps.append("jobs response is internally complete but contains zero jobs (total_count=0)")

    # --- per-job rows: offsets are job start vs workflow creation, NOT runner queue time ---
    rows = []
    intervals = []
    durations = []
    completed_times = []
    unfinished = []
    missing_started = []
    missing_completed = []
    for key, job, started, completed in parsed_jobs:
        status = job.get("status")
        start_offset = (
            _round((started - created_at).total_seconds())
            if started is not None and created_at is not None
            else None
        )
        duration = (
            _round((completed - started).total_seconds())
            if started is not None and completed is not None
            else None
        )
        if duration is not None:
            durations.append(duration)
            intervals.append((started, completed))
        name = job.get("name")
        if status != "completed":
            unfinished.append({"job_id": job.get("id"), "name": name, "status": status})
        elif completed is None:
            missing_completed.append({"job_id": job.get("id"), "name": name})
        else:
            completed_times.append((completed, job.get("id"), name, job.get("completed_at")))
        if started is None and key not in nonexecuted_ids:
            missing_started.append({"job_id": job.get("id"), "name": name})
        age = (
            _round((observed_at - started).total_seconds())
            if completed is None and started is not None and observed_at is not None
            else None
        )
        rows.append(
            {
                "job_id": job.get("id"),
                "name": name,
                "run_attempt": job.get("run_attempt"),
                "status": status,
                "conclusion": job.get("conclusion"),
                "started_at": job.get("started_at"),
                "completed_at": job.get("completed_at"),
                "execution_timing_eligible": key not in nonexecuted_ids,
                "start_offset_seconds_from_created_at": start_offset,
                "running_seconds": duration,
                "age_at_observed_at_seconds": age,
                "html_url": job.get("html_url"),
            }
        )

    if missing_started:
        gaps.append(f"{len(missing_started)} job(s) have no started_at; their offsets and running durations stay unknown")
    if missing_completed:
        gaps.append(f"{len(missing_completed)} completed job(s) lack completed_at; durations and completion stay unknown")
    if unfinished:
        gaps.append(f"{len(unfinished)} job(s) not terminal; run stays visible as incomplete (see progress.unfinished_jobs)")
    if created_at is None:
        gaps.append("run.created_at absent: start offsets and workflow elapsed time stay unknown (updated_at is never substituted)")

    if run.get("status") != "completed":
        gaps.append("workflow run not terminal; the currently captured jobs do not prove final completion")
    complete_jobs = (
        bool(jobs) and identity_verified and page_complete
        and run.get("status") == "completed" and not unfinished and not missing_completed
    )

    last_job = None
    tail_seconds = None
    workflow_elapsed = None
    elapsed_basis = None
    if completed_times:
        last_completed, last_id, last_name, last_iso = max(completed_times, key=lambda item: item[0])
        last_job = {"job_id": last_id, "name": last_name, "completed_at": last_iso}
        if created_at is not None:
            tail_seconds = _round((last_completed - created_at).total_seconds())
    if complete_jobs and created_at is not None and len(completed_times) == len(jobs):
        # Completion is max(job.completed_at) — run.updated_at is never used.
        workflow_elapsed = tail_seconds
        elapsed_basis = "run.created_at -> max(job.completed_at); run.updated_at deliberately not used"

    compute_seconds = _round(sum(durations)) if durations else None
    if not durations:
        gaps.append("no job exposes both started_at and completed_at; COMPUTE time and concurrent wall time stay unknown")
    wall_seconds = _union_seconds(intervals) if intervals else None
    run_age = (
        _round((observed_at - created_at).total_seconds())
        if observed_at is not None and created_at is not None
        else None
    )

    # --- exact-name shard-step matching over the captured steps arrays ---
    shard_rows = []
    shard_seconds = []
    steps_complete = True
    for key, job, job_started, job_completed in parsed_jobs:
        steps = job.get("steps")
        if steps is None:
            steps_complete = False
            gaps.append(f"job {key} has no steps array; shard-step matching impossible for it")
            continue
        if not isinstance(steps, list):
            _fail(f"job {key} ({_cut(job.get('name'))}) steps must be a list of step objects")
        for step in steps:
            if not isinstance(step, dict):
                _fail(f"job {key} ({_cut(job.get('name'))}) steps contains a non-object entry")
            if step.get("name") != SHARD_STEP_NAME:
                continue
            label = f"job {key} shard step {step.get('number')!r}"
            step_start = _parse_ts(step.get("started_at"), f"{label} started_at")
            step_end = _parse_ts(step.get("completed_at"), f"{label} completed_at")
            seconds = None
            executed = step.get("status") == "completed" and step.get("conclusion") != "skipped"
            if not executed:
                steps_complete = False
                gaps.append(f"{label} not executed/completed; no zero-duration shard is inferred")
            elif step_start is not None and step_end is not None:
                if step_end < step_start:
                    _fail(f"{label}: completed_at precedes started_at (inverted duration)")
                if (job_started is not None and step_start < job_started
                        or job_completed is not None and step_end > job_completed):
                    _fail(f"{label}: step timestamps fall outside the job interval")
                if observed_at is not None and step_end > observed_at:
                    _fail(f"{label}: timestamp follows observed_at")
                seconds = _round((step_end - step_start).total_seconds())
                shard_seconds.append(seconds)
            else:
                steps_complete = False
                gaps.append(f"{label} lacks started_at/completed_at; its duration stays unknown")
            shard_rows.append(
                {
                    "job_id": job.get("id"),
                    "job_name": job.get("name"),
                    "step_number": step.get("number"),
                    "status": step.get("status"),
                    "conclusion": step.get("conclusion"),
                    "started_at": step.get("started_at"),
                    "completed_at": step.get("completed_at"),
                    "seconds": seconds,
                }
            )
    if not shard_rows:
        gaps.append(f"no steps matched the exact step name {SHARD_STEP_NAME!r}; shard statistics stay unknown")
    stats = None
    lower_bound = None
    if shard_rows:
        stats = {
            "count": len(shard_rows),
            "timed_count": len(shard_seconds),
            "min_seconds": min(shard_seconds) if shard_seconds else None,
            "max_seconds": max(shard_seconds) if shard_seconds else None,
            "sum_seconds": _round(sum(shard_seconds)) if shard_seconds else None,
            "mean_seconds": _round(sum(shard_seconds) / len(shard_seconds)) if shard_seconds else None,
        }
        if complete_jobs and steps_complete and len(shard_seconds) == len(shard_rows):
            # Theoretical sum/N perfectly balanced bound; NOT an achieved saving.
            lower_bound = stats["mean_seconds"]

    return {
        "schema": PROFILE_SCHEMA,
        "generator": "scripts/ci_run_profile.py",
        "offline": True,
        "identity": {
            "repository_full_name": repository_full_name,
            "run_id": run_id,
            "run_number": run.get("run_number"),
            "run_attempt": run_attempt,
            "head_sha": head_sha,
            "head_branch": run.get("head_branch"),
            "event": run.get("event"),
            "workflow_id": run.get("workflow_id"),
            "workflow_name": run.get("name"),
            "workflow_path": run.get("path"),
        },
        "identity_basis": _IDENTITY_BASIS,
        "identity_verified": identity_verified,
        "reported": {"status": run.get("status"), "conclusion": run.get("conclusion")},
        "source_urls": {
            "run_html_url": run.get("html_url"),
            "jobs_api_url": run.get("jobs_url"),
            "repository_html_url": repository.get("html_url"),
            "job_html_urls": {str(row["job_id"]): row["html_url"] for row in rows if row["html_url"]},
        },
        "complete_jobs": complete_jobs,
        "progress": {
            "total_count": total_count,
            "jobs_captured": len(jobs),
            "page_complete": page_complete,
            "completed_jobs": len(completed_times),
            "unfinished_jobs": unfinished,
            "jobs_missing_started_at": missing_started,
            "jobs_missing_completed_at": missing_completed,
            "nonexecuted_jobs": [
                {"job_id": job.get("id"), "name": job.get("name")}
                for key, job, _, _ in parsed_jobs if key in nonexecuted_ids
            ],
        },
        "workflow_elapsed_seconds": workflow_elapsed,
        "workflow_elapsed_basis": elapsed_basis,
        "compute_time_seconds": compute_seconds,
        "compute_time_complete": complete_jobs and len(durations) == len(jobs),
        "compute_time_basis": "sum of observed per-job running_seconds; may be partial, not a billing estimate",
        "concurrent_wall_time_seconds": wall_seconds,
        "concurrent_wall_time_basis": "union of observed running intervals [started_at, completed_at); idle gaps excluded",
        "last_job_finished": last_job,
        "tail_seconds_after_created_at": tail_seconds,
        "observed": {"observed_at": snapshot.get("observed_at"), "run_age_seconds": run_age},
        "jobs": rows,
        "test_shards": {
            "matched_step_name": SHARD_STEP_NAME,
            "match_basis": "exact step-name equality against each captured step",
            "rows": shard_rows,
            "stats": stats,
            "theoretical_perfectly_balanced_lower_bound_seconds": lower_bound,
            "lower_bound_note": "theoretical sum/N bound assuming perfectly balanced shards;"
            " no balancing is proven and no achieved savings are claimed",
        },
        "attempts": {
            "run_attempt": run_attempt,
            "distinct_job_attempts": sorted({str(value) for value in job_attempts}),
            "all_jobs_match_run_attempt": (job_attempts == {run_attempt}) if job_attempts else None,
        },
        "evidence_gaps": gaps,
        "limitations": list(_LIMITATIONS),
        "claim_boundaries": {
            "billing_estimate": None,
            "achieved_elapsed_reduction_percent": None,
            "delivery_or_acceptance_verdict": None,
            "note": "no billing estimate, no proven >=80% elapsed-time reduction and no"
            " delivery/acceptance verdict is computed here",
        },
    }


def _read_bounded(handle, label: str) -> bytes:
    data = handle.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        _fail(f"{label}: input exceeds the bounded read limit of {MAX_INPUT_BYTES} bytes (8 MiB)")
    return data


def load_snapshot(source: str):
    """Load the snapshot JSON from ``source`` or '-' (stdin); reads stay bounded."""
    if source == "-":
        data = _read_bounded(sys.stdin.buffer, "stdin")
    else:
        try:
            with open(source, "rb") as handle:
                data = _read_bounded(handle, source)
        except OSError as exc:
            _fail(f"cannot read input {source!r}: {exc.strerror or exc}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _fail(f"input {source!r} is not valid UTF-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        _fail(f"input {source!r} is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}")


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if len(args) != 1:
        print(USAGE, file=sys.stderr)
        return 2
    try:
        profile = build_profile(load_snapshot(args[0]))
    except ProfileError as exc:
        print(f"ci_run_profile: error: {_cut(exc, 500)}", file=sys.stderr)
        return 2
    json.dump(profile, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

