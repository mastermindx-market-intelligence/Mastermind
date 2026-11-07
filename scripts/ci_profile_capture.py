"""Read-only Actions consumer for ci_run_profile; no release or retry authority.

Only GitHub JSON metadata is read. Candidate code, logs, caches and artifacts are
never downloaded or executed. Every request binds one repository/run/attempt;
the existing offline profiler remains the only timing/identity calculation owner.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts.ci_run_profile import MAX_INPUT_BYTES, ProfileError, build_profile

MAX_JOBS = 1000
PAGE_SIZE = 100
API_VERSION = "2026-03-10"
_API_PATH = re.compile(
    r"repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[1-9][0-9]*/attempts/[1-9][0-9]*"
    r"(?:/jobs\?per_page=100&page=[1-9][0-9]*)?\Z"
)


class CaptureError(ValueError):
    """Bounded, non-secret diagnostic. Failure never changes the source CI run."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _repository(value: str) -> str:
    if (not isinstance(value, str)
            or re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value) is None
            or any(part in (".", "..") for part in value.split("/"))):
        raise CaptureError("INVALID_REPOSITORY")
    return value


def _positive(value: int) -> int:
    if type(value) is not int or value < 1:
        raise CaptureError("INVALID_RUN_OR_ATTEMPT")
    return value


def github_reader(token: str, *, opener=None) -> Callable[[str], dict]:
    """Fixed-host, bounded GET only; no redirects, mutation, retry or raw errors."""
    if not isinstance(token, str) or not token or any(ch.isspace() for ch in token):
        raise CaptureError("TOKEN_UNAVAILABLE")
    opener = opener if opener is not None else build_opener(NoRedirect())

    def read(path: str) -> dict:
        if not _API_PATH.fullmatch(path):
            raise CaptureError("UNSUPPORTED_API_PATH")
        _repository("/".join(path.split("/")[1:3]))
        request = Request("https://api.github.com/" + path, method="GET", headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "mastermind-ci-profile",
        })
        try:
            with opener.open(request, timeout=20) as response:
                raw = response.read(MAX_INPUT_BYTES + 1)
        except HTTPError as exc:
            raise CaptureError(f"GITHUB_HTTP_{exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise CaptureError("GITHUB_READ_UNAVAILABLE") from None
        if len(raw) > MAX_INPUT_BYTES:
            raise CaptureError("API_RESPONSE_TOO_LARGE")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise CaptureError("INVALID_API_JSON") from None
        if not isinstance(value, dict):
            raise CaptureError("INVALID_API_OBJECT")
        return value

    return read


def capture_attempt(repository: str, run_id: int, attempt: int, *, read_json) -> dict:
    """Capture all pages of exactly one completed attempt, without inventing fields."""
    _repository(repository)
    _positive(run_id)
    _positive(attempt)
    endpoint = f"repos/{repository}/actions/runs/{run_id}/attempts/{attempt}"
    run = read_json(endpoint)
    if not isinstance(run, dict):
        raise CaptureError("INVALID_RUN_OBJECT")
    if (type(run.get("id")) is not int or run["id"] != run_id
            or type(run.get("run_attempt")) is not int or run["run_attempt"] != attempt
            or not isinstance(run.get("repository"), dict)
            or run["repository"].get("full_name") != repository):
        raise CaptureError("RUN_IDENTITY_MISMATCH")
    if run.get("name") != "CI" or run.get("path") != ".github/workflows/ci.yml":
        raise CaptureError("UNEXPECTED_WORKFLOW")
    if run.get("status") != "completed":
        raise CaptureError("ATTEMPT_NOT_COMPLETED")
    jobs, seen, total = [], set(), None
    for page in range(1, MAX_JOBS // PAGE_SIZE + 1):
        response = read_json(endpoint + f"/jobs?per_page={PAGE_SIZE}&page={page}")
        if not isinstance(response, dict):
            raise CaptureError("INVALID_JOBS_OBJECT")
        count, batch = response.get("total_count"), response.get("jobs")
        if type(count) is not int or count < 0 or count > MAX_JOBS or not isinstance(batch, list):
            raise CaptureError("INVALID_JOBS_PAGE")
        if total is not None and count != total:
            raise CaptureError("JOB_COUNT_CHANGED")
        total = count
        if len(batch) > PAGE_SIZE or len(jobs) + len(batch) > total:
            raise CaptureError("JOB_PAGE_COUNT_MISMATCH")
        for job in batch:
            if not isinstance(job, dict) or type(job.get("id")) is not int or job["id"] < 1:
                raise CaptureError("INVALID_JOB_ID")
            if job["id"] in seen:
                raise CaptureError("DUPLICATE_JOB_ID")
            seen.add(job["id"])
        jobs.extend(batch)
        if len(jobs) == total:
            break
        if len(batch) != PAGE_SIZE:
            raise CaptureError("INCOMPLETE_JOBS_PAGE")
    else:
        raise CaptureError("JOB_PAGE_LIMIT")
    snapshot = {
        "run": run, "jobs": {"total_count": total, "jobs": jobs},
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    if len(json.dumps(snapshot).encode("utf-8")) > MAX_INPUT_BYTES:
        raise CaptureError("CAPTURE_TOO_LARGE")
    build_profile(snapshot)  # existing identity/timing owner, including hostile cases
    return snapshot


def _cell(value: object) -> str:
    # Names are candidate-controlled text, never executable Markdown or mentions.
    text = html.escape(str(value), quote=True)
    text = " ".join(text.split())[:180]
    for char, entity in (("|", "&#124;"), ("@", "&#64;"), ("[", "&#91;"),
                         ("]", "&#93;"), ("`", "&#96;"), ("\\", "&#92;")):
        text = text.replace(char, entity)
    return text


def _minutes(seconds) -> str:
    return "unknown" if seconds is None else f"{seconds / 60:.2f}"


def render_summary(profile: dict) -> str:
    identity = profile["identity"]
    repo, run_id = identity["repository_full_name"], identity["run_id"]
    _repository(repo)
    _positive(run_id)
    lines = [
        "# CI performance report",
        f"Source: [{_cell(repo)} run {run_id}, attempt {identity['run_attempt']}]"
        f"(https://github.com/{repo}/actions/runs/{run_id}/attempts/{identity['run_attempt']})",
        "",
        f"Reported result: **{_cell(profile['reported']['conclusion'])}**. "
        "Not a merge, deployment, or acceptance verdict.",
        "",
        "| Measure | Minutes |", "| --- | ---: |",
        f"| Creation to last observed job completion | {_minutes(profile['workflow_elapsed_seconds'])} |",
        f"| Summed job execution (not billed cost) | {_minutes(profile['compute_time_seconds'])} |",
        f"| Union of running job intervals | {_minutes(profile['concurrent_wall_time_seconds'])} |",
        "",
        "Start offsets below are measured from workflow creation, **not runner queue time**. "
        "Dependencies and scheduling both contribute; the API snapshot does not identify causality.",
        "",
        "## Slowest jobs",
        "| Job | Result | Running minutes | Start offset minutes |",
        "| --- | --- | ---: | ---: |",
    ]
    rows = sorted(profile["jobs"], key=lambda row: -(row.get("running_seconds") or 0))[:15]
    for row in rows:
        lines.append(f"| {_cell(row['name'])} | {_cell(row['conclusion'])} | "
                     f"{_minutes(row['running_seconds'])} | {_minutes(row['start_offset_seconds_from_created_at'])} |")
    failures = [row for row in profile["jobs"]
                if row["status"] != "completed"
                or row["conclusion"] not in ("success", "skipped", "neutral")]
    lines.extend(["", "## Failed or incomplete jobs"])
    for row in failures[:20]:
        lines.append(f"- [{_cell(row['name'])}]"
                     f"(https://github.com/{repo}/actions/runs/{run_id}/job/{row['job_id']}): "
                     f"{_cell(row['status'])} / {_cell(row['conclusion'])}")
    if not failures:
        lines.append("None in the captured job metadata; this is not an acceptance decision.")
    elif len(failures) > 20:
        lines.append(f"{len(failures) - 20} additional affected jobs are retained in profile.json.")
    lines.extend(["", "## Evidence gaps"])
    gaps = list(profile["evidence_gaps"])
    if not profile["identity_verified"]:
        gaps.insert(0, "Some native identity fields are missing; no replacement values were synthesized.")
    lines.extend("- " + _cell(gap) for gap in gaps[:20])
    if not gaps:
        lines.append("No gaps reported by the existing offline profile validator.")
    lines.extend(["", "The retained snapshot and profile contain every captured job, not only this top-15 view. "
                  "Missing measurements stay unknown. No performance improvement, billing saving, "
                  "or release eligibility is inferred from this report.", ""])
    return "\n".join(lines)


def write_report(snapshot: dict, output: Path) -> None:
    profile = build_profile(snapshot)
    summary = render_summary(profile)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("snapshot.json", snapshot), ("profile.json", profile)):
        (output / name).write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    (output / "summary.md").write_text(summary, encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        snapshot = capture_attempt(args.repository, args.run_id, args.attempt,
                                   read_json=github_reader(os.environ.get("GH_TOKEN", "")))
        write_report(snapshot, args.output)
    except (CaptureError, ProfileError) as exc:
        # Error classes are bounded metadata; no token/HTTP body is printed.
        safe_error = str(exc).encode("unicode_escape").decode("ascii")[:300]
        print("ci-profile: " + safe_error, file=sys.stderr)
        return 1
    except OSError:
        print("ci-profile: OUTPUT_UNAVAILABLE", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
