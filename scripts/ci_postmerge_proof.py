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
import subprocess
import urllib.request
from datetime import datetime
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


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except ValueError:
        return None


def _checkout_identity_proven(sha: str) -> bool:
    if not _SHA.fullmatch(sha):
        return False
    # HEAD-to-worktree equality alone does not prove a clean index: an
    # adversarial staged blob can differ from HEAD while the working file
    # happens to match it. Check both surfaces independently, without
    # refreshing or altering the checkout.
    for args in (("git", "rev-parse", "--verify", "HEAD"),
                 ("git", "diff", "--quiet", "--"),
                 ("git", "diff", "--cached", "--quiet", "--")):
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if proc.returncode or (args[1] == "rev-parse" and proc.stdout.strip() != sha):
            return False
    return True


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
        or not env.get("GITHUB_RUN_ATTEMPT", "").isdigit()
        or int(env["GITHUB_RUN_ATTEMPT"]) != 1
    ):
        return None

    prefix = f"/repos/{_REPOSITORY}"
    current = read_json(f"{prefix}/actions/runs/{env['GITHUB_RUN_ID']}")
    if (not isinstance(current, dict)
        or current.get("id") != int(env["GITHUB_RUN_ID"])
        or current.get("run_attempt") != 1
        or current.get("workflow_id") != 324108847
        or current.get("event") != "push"
        or current.get("head_branch") != "master"
        # Only the native merge queue may originate a reusable protected
        # push. A direct human/API push of even an otherwise proven group SHA
        # must run full pytest. Identity is obtained from the GitHub API, not
        # from caller-provided GITHUB_ACTOR environment variables.
        or any(
            not isinstance(current.get(key), dict)
            or current[key].get("login") != "github-merge-queue[bot]"
            or current[key].get("type") != "Bot"
            for key in ("actor", "triggering_actor")
        )
        or current.get("head_sha") != sha
        or current.get("path") != _WORKFLOW
        or current.get("status") not in {"in_progress", "completed"}
        or not isinstance(current.get("repository"), dict)
        or current["repository"].get("full_name") != _REPOSITORY
        or not isinstance(current.get("head_repository"), dict)
        or current["head_repository"].get("full_name") != _REPOSITORY
        or _time(current.get("created_at")) is None):
        return None
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
    if (not _source_ok(run, sha=sha, repository=_REPOSITORY)
        or run.get("workflow_id") != current["workflow_id"]
        or not isinstance(run.get("head_branch"), str)
        or not run["head_branch"].startswith("gh-readonly-queue/master/")
        or _time(run.get("created_at")) is None
        or _time(run.get("updated_at")) is None
        or not (_time(run["created_at"]) <= _time(run["updated_at"]) <= _time(current["created_at"]))):
        return None
    identifier, attempt = run.get("id"), run.get("run_attempt")
    if (
        type(identifier) is not int or identifier <= 0
        or type(attempt) is not int or attempt != 1
        or str(identifier) == env["GITHUB_RUN_ID"]
    ):
        return None

    group_start = _time(run["created_at"])
    group_end = _time(run["updated_at"])
    push_start = _time(current["created_at"])
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
        job_start = _time(job.get("started_at"))
        job_end = _time(job.get("completed_at"))
        if (
            job_start is None or job_end is None
            or not (group_start <= job_start <= job_end <= group_end <= push_start)
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
    current_recheck = read_json(f"{prefix}/actions/runs/{env['GITHUB_RUN_ID']}")
    if (not isinstance(current_recheck, dict)
        or any(current_recheck.get(key) != current.get(key) for key in
               ("id", "run_attempt", "workflow_id", "head_sha", "event", "head_branch",
                "created_at", "actor", "triggering_actor"))):
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

    usable = proven is not None and _checkout_identity_proven(env.get("GITHUB_SHA", ""))
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
