"""Read-only exact merge-group proof for avoiding a redundant post-merge pytest run.

This is not a release authority, check replacement, queue, or background
observer. On a protected master push only, a successful *same-SHA* native
merge_group CI workflow with all three shards and its required test may be
reused. Missing, ambiguous, stale, unauthorized or invalid evidence means
"reuse=false": the incumbent shard runs normally. Non-pytest gates still run.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

_REPOSITORY = "mastermindx-market-intelligence/Mastermind"
_WORKFLOW = ".github/workflows/ci.yml"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_JOB_NAMES = {"pytest shard 0", "pytest shard 1", "pytest shard 2", "test"}
_API = "https://api.github.com"
_MAX_RESPONSE = 256_000


def _source_ok(item: object, *, sha: str, repository: str) -> bool:
    if not isinstance(item, dict):
        return False
    own = item.get("repository")
    head = item.get("head_repository")
    return (
        item.get("head_sha") == sha
        and item.get("event") == "merge_group"
        and item.get("path") == _WORKFLOW
        and item.get("status") == "completed"
        and item.get("conclusion") == "success"
        and isinstance(own, dict) and own.get("full_name") == repository
        and isinstance(head, dict) and head.get("full_name") == repository
    )


def find_reusable_run(
    env: Mapping[str, str], *, read_json: Callable[[str], Any]
) -> int | None:
    """Return the proven merge-group run ID, never a guessed release decision.

    read_json accepts a relative, fixed-repository GitHub API path. It must
    return a parsed JSON value, or raise on any missing/denied/partial read.
    """
    sha = env.get("GITHUB_SHA", "")
    if (
        env.get("GITHUB_EVENT_NAME") != "push"
        or env.get("GITHUB_REF") != "refs/heads/master"
        or env.get("GITHUB_REPOSITORY") != _REPOSITORY
        or env.get("GITHUB_API_URL") != _API
        or not _SHA.fullmatch(sha)
        or not env.get("GH_TOKEN")
        or not env.get("GITHUB_RUN_ID", "").isdigit()
    ):
        return None

    prefix = f"/repos/{_REPOSITORY}"
    listing = read_json(
        f"{prefix}/actions/workflows/ci.yml/runs"
        f"?event=merge_group&head_sha={sha}&per_page=100"
    )
    if not isinstance(listing, dict) or type(listing.get("total_count")) is not int:
        return None
    runs = listing.get("workflow_runs")
    # Ambiguous or incomplete pages cannot substitute for full protected CI.
    if listing["total_count"] != 1 or not isinstance(runs, list) or len(runs) != 1:
        return None
    run = runs[0]
    if not _source_ok(run, sha=sha, repository=_REPOSITORY):
        return None
    identifier, attempt = run.get("id"), run.get("run_attempt")
    if (
        type(identifier) is not int or identifier <= 0
        or type(attempt) is not int or attempt <= 0
        or str(identifier) == env["GITHUB_RUN_ID"]
    ):
        return None

    jobs = read_json(f"{prefix}/actions/runs/{identifier}/attempts/{attempt}/jobs?per_page=100")
    if not isinstance(jobs, dict) or jobs.get("total_count") != 4:
        return None
    members = jobs.get("jobs")
    if not isinstance(members, list) or len(members) != 4:
        return None
    seen: set[str] = set()
    check_ids: set[int] = set()
    for job in members:
        if not isinstance(job, dict):
            return None
        name, check_id = job.get("name"), job.get("id")
        if (
            not isinstance(name, str)
            or name not in _JOB_NAMES or name in seen
            or type(check_id) is not int or check_id <= 0
            or check_id in check_ids
            or job.get("status") != "completed"
            or job.get("conclusion") != "success"
            or job.get("head_sha") != sha
            or job.get("run_id") != identifier
            or job.get("run_attempt") != attempt
            or job.get("workflow_name") != "CI"
            or job.get("check_run_url") != f"{_API}{prefix}/check-runs/{check_id}"
        ):
            return None
        # GitHub reports a successful JOB even if its test STEP was skipped.
        # Verify the actual executable steps in the prior integrated run.
        required = (
            {"Run repository test gate"} if name == "test"
            else {"Run repository test shard"}
        )
        if name == "pytest shard 0":
            required |= {
                "Verify Paper direct pinned MCP SDK",
                "Verify private Fabric HTTP compatibility and incumbent backend lifetime",
                "Compile source",
                "Validate shell scripts",
            }
        steps = job.get("steps")
        if not isinstance(steps, list):
            return None
        for required_name in required:
            matches = [
                step for step in steps
                if isinstance(step, dict) and step.get("name") == required_name
            ]
            if (
                len(matches) != 1
                or matches[0].get("status") != "completed"
                or matches[0].get("conclusion") != "success"
            ):
                return None
        seen.add(name)
        check_ids.add(check_id)
    if seen != _JOB_NAMES:
        return None

    # Detect a newer rerun/attempt that began during multi-request sampling.
    recheck = read_json(f"{prefix}/actions/runs/{identifier}")
    if (
        not _source_ok(recheck, sha=sha, repository=_REPOSITORY)
        or recheck.get("id") != identifier
        or recheck.get("run_attempt") != attempt
        or recheck.get("workflow_id") != run.get("workflow_id")
    ):
        return None
    return identifier


def _github_read(path: str, token: str) -> Any:
    if not path.startswith(f"/repos/{_REPOSITORY}/") or "//" in path:
        raise ValueError("unsupported GitHub endpoint")
    request = urllib.request.Request(
        f"{_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mastermind-ci-mergegroup-reuse",
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        data = response.read(_MAX_RESPONSE + 1)
    if len(data) > _MAX_RESPONSE:
        raise ValueError("GitHub evidence exceeded the bounded response")
    return json.loads(data)


def main() -> int:
    env = dict(os.environ)
    proven: int | None = None
    try:
        proven = find_reusable_run(
            env,
            read_json=lambda path: _github_read(path, env.get("GH_TOKEN", "")),
        )
    except Exception:
        # Source or provider faults must result in the complete normal pytest
        # path, not an unverified green or a retry via another identity.
        proven = None

    usable = proven is not None
    output = env.get("GITHUB_OUTPUT")
    if not output:
        print("ci_mergegroup_reuse: GITHUB_OUTPUT unavailable", file=sys.stderr)
        return 1
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"reuse={'true' if usable else 'false'}\n")
    print(
        f"ci_mergegroup_reuse: {'verified exact group ' + str(proven) if usable else 'no qualifying proof; run full pytest'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
