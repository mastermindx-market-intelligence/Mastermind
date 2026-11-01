#!/usr/bin/env python3
"""Read or cheaply await one exact CI candidate using installed GitHub CLI auth.

This is a foreground command for an existing native/process owner. It emits one
structured result, never sends a wake, invokes a model, merges, or deploys. A
successful CI observation is not release authority or product acceptance.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import time
from collections.abc import Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from control_plane.github_ci_candidate_observer import observe_candidate_transition
from control_plane.github_ci_candidate_waiter import CandidateWaiterRegistry, wait_for_candidate_material
from integrations.github_ci_candidate_reader import GitHubCandidateReader

SCHEMA = "mastermind.github_ci_candidate_cli.v1"
_MAX_BODY = 5_000_000
_REPOSITORY_PATH = r"repos/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*"
_BRANCH = r"[A-Za-z0-9_.%-]+"
_PROJECTIONS = (
    (rf"{_REPOSITORY_PATH}/pulls/[1-9][0-9]*", "{number,state,head:{ref:.head.ref,sha:.head.sha,repo:{id:.head.repo.id,full_name:.head.repo.full_name}},base:{ref:.base.ref,sha:.base.sha,repo:{id:.base.repo.id,full_name:.base.repo.full_name}}}"),
    (rf"{_REPOSITORY_PATH}/branches/{_BRANCH}", "{name,protected,protection}"),
    (rf"{_REPOSITORY_PATH}/rules/branches/{_BRANCH}\?per_page=100&page=[1-9][0-9]?", "."),
    (rf"{_REPOSITORY_PATH}/commits/[0-9a-f]{{40}}/check-runs\?filter=latest&per_page=100&page=[1-9][0-9]?", "{total_count,check_runs:[.check_runs[]|{id,name,head_sha,status,conclusion,app:{id:.app.id},check_suite:{id:.check_suite.id},details_url}]}"),
    (rf"{_REPOSITORY_PATH}/actions/runs/[1-9][0-9]*", "{id,head_sha,check_suite_id,run_attempt,status}"),
    (rf"{_REPOSITORY_PATH}/actions/runs/[1-9][0-9]*/attempts/[1-9][0-9]*/jobs\?per_page=100&page=[1-9][0-9]?", "{total_count,jobs:[.jobs[]|{id,run_id,run_attempt,head_sha,check_run_url}]}"),
)


class CandidateTransportError(ValueError):
    """A bounded existing-CLI read failed; no retry or alternate identity is used."""


def _bounded_get(arguments: list[str], timeout: float) -> bytes:
    """Bound both process lifetime and returned bytes without logging raw stderr."""
    process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CandidateTransportError("READ_TIMEOUT")
                events = selector.select(remaining)
                if not events:
                    raise CandidateTransportError("READ_TIMEOUT")
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    target = buffers[key.data]
                    target.extend(chunk)
                    limit = _MAX_BODY if key.data == "stdout" else 65536
                    if len(target) > limit:
                        raise CandidateTransportError("READ_OUTPUT_LIMIT")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CandidateTransportError("READ_TIMEOUT")
        try:
            code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            raise CandidateTransportError("READ_TIMEOUT") from None
        if code:
            message = bytes(buffers["stderr"])
            status = re.search(rb"HTTP (401|403|404|429|5[0-9]{2})\b", message)
            reason = "HTTP_" + status.group(1).decode() if status else "CLI_READ_FAILED"
            raise CandidateTransportError(reason)
        return bytes(buffers["stdout"])
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


class GitHubCLIReader:
    """The existing `gh` account supplies GET-only, field-selected observations."""

    def read(self, endpoint: str) -> object:
        if not isinstance(endpoint, str):
            raise CandidateTransportError("ENDPOINT_NOT_ALLOWED")
        projection = next((query for pattern, query in _PROJECTIONS if re.fullmatch(pattern, endpoint)), None)
        if projection is None:
            raise CandidateTransportError("ENDPOINT_NOT_ALLOWED")
        executable = shutil.which("gh")
        if executable is None:
            raise CandidateTransportError("GITHUB_CLI_UNAVAILABLE")
        arguments = [executable, "api", "--hostname", "github.com", "--method", "GET", "--header", "X-GitHub-Api-Version: 2022-11-28", "--jq", projection, endpoint]
        raw = _bounded_get(arguments, 15.0)
        try:
            return json.loads(raw)
        except (UnicodeDecodeError, ValueError):
            raise CandidateTransportError("INVALID_GITHUB_JSON") from None


def observe_candidate(*, reader: GitHubCandidateReader, repository: str, pull_request_number: int, expected_head_sha: str, max_samples: int = 0, interval_seconds: float = 60, wait: Callable[[float], None] = time.sleep) -> dict:
    if type(max_samples) is not int or not 0 <= max_samples <= 120:
        raise ValueError("invalid sample budget")
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)) or not math.isfinite(interval_seconds) or not 15 <= interval_seconds <= 300:
        raise ValueError("invalid observation interval")
    if not callable(wait):
        raise ValueError("invalid wait callback")
    sample_count = 0
    latest = None
    def sample():
        nonlocal sample_count, latest
        latest = reader.sample(repository=repository, pull_request_number=pull_request_number, expected_head_sha=expected_head_sha)
        sample_count += 1
        return latest
    baseline = sample()
    decision = observe_candidate_transition(baseline)
    if max_samples and not decision.wake_reasoning:
        # This baseline was just sampled, not restored from an earlier process.
        # Respect cadence before the first additional read as well as later ones.
        wait(interval_seconds)
        waited = wait_for_candidate_material(baseline, sample=sample, wait=lambda: wait(interval_seconds), registry=CandidateWaiterRegistry(), max_samples=max_samples)
        decision = waited.decision
    assert latest is not None
    return {
        "schema": SCHEMA,
        "observation": latest.to_dict(),
        "decision": None if decision is None else decision.to_dict(),
        "sample_count": sample_count,
        "material_return": decision is not None and decision.wake_reasoning,
        "release_authorized": False,
        "wake_delivered": False,
        "consumer": "existing-caller-owned-native-process",
    }


def exit_code(state: str) -> int:
    return {"GREEN": 0, "FAILED": 1, "UNKNOWN": 2, "STALE": 3, "PENDING": 4}.get(state, 2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--head", required=True, help="Frozen exact candidate SHA; never inferred from latest.")
    parser.add_argument("--max-samples", type=int, default=0, help="Additional samples after baseline (0 means one read; max 120).")
    parser.add_argument("--interval-seconds", type=float, default=60)
    args = parser.parse_args(argv)
    try:
        transport = GitHubCLIReader()
        result = observe_candidate(reader=GitHubCandidateReader(read=transport.read), repository=args.repository, pull_request_number=args.pr, expected_head_sha=args.head, max_samples=args.max_samples, interval_seconds=args.interval_seconds)
    except (ValueError, OSError, PermissionError) as error:
        reason = str(error) if isinstance(error, CandidateTransportError) else "OBSERVATION_REJECTED"
        print(json.dumps({"schema": SCHEMA, "state": "UNKNOWN", "reason": reason, "error_type": type(error).__name__, "release_authorized": False, "wake_delivered": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return exit_code(result["observation"]["state"])


if __name__ == "__main__":
    raise SystemExit(main())
