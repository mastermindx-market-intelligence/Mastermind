"""Finite Class-T deterministic observer for one admitted Fabric worker.

It runs inside the worker's own process: it waits cheaply on a monotonic
deadline, samples one read-only source and returns at most one material
signal before the worker's already-authorized repair/test workflow
continues. It is not a daemon, scheduler, queue, registry, state file,
lifecycle, worker spawn, credential broker, browser controller or release
authority.

Frozen behaviour
-----------------
* Schema ``mastermind.fabric_finite_watch.v1``. Unknown fields are rejected,
  integers are exact (``bool`` is not an integer) and identity strings are
  echoed unchanged. ``run_id``/``root_id``/``parent_id``/``watch_id``/``source``
  are identity only: a caller-supplied root grants no admission, custody,
  release or retry authority.
* Sources: ``timer`` (one UTC due time), ``github_ci`` (explicitly selected
  workflow runs on one exact PR head), ``github_review`` (formal review
  decisions on one exact PR head) and ``service_health`` (one service from the
  existing ``observe.ENDPOINTS`` allowlist).
* GitHub reads are GET-only ``gh api`` argv calls with ``shell=False``,
  ``--method GET``, ``--hostname github.com``, a per-command timeout and a
  bounded response size. The service surface reuses the incumbent read-only
  MCP observation in ``ops.fabric_launch.observe``; its JSON-RPC envelope is a
  POST to a fixed read endpoint that calls no write tool and accepts no caller
  URL, header, body or credential. A parent that requires a GET-only service
  surface injects its own probe.
* One run yields exactly one ``EVENT``/``TIMEOUT``/``CANCELLED``/
  ``SOURCE_UNAVAILABLE`` result; ``release_authorized``, ``retry_authorized``
  and ``native_parent_wake`` are always false. Unchanged samples are
  suppressed, so a run never calls a reasoning model. ``sample_count`` counts
  observation attempts, including one that failed with a source error.
* The watch keeps no state across process restarts: a worker process that
  survives a Web turn is not restart-persistent and never resumes a watch.
* No response text, stderr or credential is returned. Failures surface as
  bounded codes only, and a source failure never becomes a success.
* ``github_ci`` reports each selected run's actual conclusion; it is not
  branch CI green, a policy synthesis or a release-readiness claim.
  ``github_review`` observes formal review records only: never an approval
  count, never proof of reviewer independence, never authority to merge.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import selectors
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ops.fabric_launch import observe
from ops.fabric_launch.context import (
    LaunchInputError,
    MAX_INPUT_BYTES,
    canonical,
    digest,
    fail,
    parse as parse_json,
    text,
    timestamp,
)

SCHEMA = "mastermind.fabric_finite_watch.v1"
RESULT_SCHEMA = "mastermind.fabric_finite_watch_result.v1"
SOURCES = ("timer", "github_ci", "github_review", "service_health")
NETWORK_SOURCES = frozenset({"github_ci", "github_review", "service_health"})
EXTERNAL_SOURCE_KINDS = ("github_ci", "github_review", "service_health")

MAX_TIMEOUT_SECONDS = 7200
MAX_INTERVAL_SECONDS = 300
MIN_NETWORK_INTERVAL_SECONDS = 15
MAX_SAMPLES = 120
MAX_WORKFLOW_RUN_IDS = 120
MAX_IDENTITY_BYTES = 192
MAX_REPOSITORY_BYTES = 100
MAX_RESPONSE_BYTES = 256 * 1024
MAX_COMMAND_TIMEOUT_SECONDS = 10.0
CANCEL_POLL_SECONDS = 1.0
REVIEW_PAGE_SIZE = 100
MAX_REVIEW_PAGES = 10
MAX_REVIEW_LOGIN_BYTES = 100
MAX_JSON_DEPTH = 32

FORMAL_REVIEW_STATES = ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")
HEALTH_STATES = ("READY", "DEGRADED", "UNAVAILABLE", "AUTH_REQUIRED", "DENIED")
TERMINAL_HEALTH_STATES = frozenset({"UNAVAILABLE", "AUTH_REQUIRED", "DENIED"})
WORKFLOW_CONCLUSIONS = frozenset({
    "success", "failure", "cancelled", "timed_out", "action_required",
    "skipped", "neutral", "stale",
})
PENDING_WORKFLOW_STATUSES = frozenset({
    "queued", "in_progress", "waiting", "requested", "pending",
})

_REPOSITORY_RE = re.compile(r"\A[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_HEAD_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")

_COMMON_FIELDS = frozenset({
    "schema", "run_id", "root_id", "parent_id", "watch_id", "source", "limits",
})
LIMIT_FIELDS = frozenset({"timeout_seconds", "interval_seconds", "max_samples"})
# source -> (required fields, optional fields)
_SOURCE_FIELDS = {
    "timer": (frozenset({"due_at"}), frozenset()),
    "github_ci": (frozenset({
        "repository", "pull_request", "expected_head_sha", "workflow_run_ids",
    }), frozenset()),
    "github_review": (frozenset({
        "repository", "pull_request", "expected_head_sha", "after_review_id",
    }), frozenset({"review_baseline"})),
    "service_health": (frozenset({"service"}), frozenset({"expected_state"})),
}


class SourceUnavailable(Exception):
    """A bounded source failure. Carries a code, never text or credentials."""

    def __init__(self, signal_payload: dict):
        super().__init__(str(signal_payload.get("code", "SOURCE_UNAVAILABLE")))
        self.signal_payload = signal_payload


class _Stale(Exception):
    """The watched head moved. Raised inside a sampler, never outward."""

    def __init__(self, observed, origin):
        super().__init__(origin)
        self.observed = observed
        self.origin = origin


class _DeadlineExceeded(Exception):
    pass


class _Cancelled(Exception):
    def __init__(self, code):
        self.code = code


class _Budget:
    """One absolute clock and latched cancellation across every acquisition."""

    def __init__(self, clock, deadline, cancel, state):
        self.clock, self.deadline, self.cancel, self.state = clock, deadline, cancel, state

    def check(self):
        if self.state["triggered"]:
            raise _Cancelled(self.state.get("code", "CANCELLED_BY_SIGNAL"))
        if self.cancel is not None and self.cancel():
            self.state.update(triggered=True, code="CANCELLED_BY_CALLBACK")
            raise _Cancelled("CANCELLED_BY_CALLBACK")
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise _DeadlineExceeded()
        return remaining

    def read(self, reader, identity, proposed):
        timeout = min(float(proposed), MAX_COMMAND_TIMEOUT_SECONDS, self.check())
        try:
            value = reader(identity, timeout)
        except Exception:
            self.check()  # Cancellation/deadline wins a late error, too.
            raise
        self.check()      # A late successful response is never an EVENT.
        return value


@dataclass(frozen=True)
class Limits:
    timeout_seconds: int
    interval_seconds: int
    max_samples: int


@dataclass(frozen=True)
class WatchSpec:
    run_id: str
    root_id: str
    parent_id: str
    watch_id: str
    source: str
    limits: Limits
    params: dict
    source_digest: str


@dataclass(frozen=True)
class Sample:
    """One bounded observation. ``event`` is material; nothing else is."""

    digest: str
    event: str | None = None
    signal: dict | None = None


def _unavailable(code, **detail):
    return SourceUnavailable({"code": code, **detail})


def _digest_of(value):
    return digest(canonical(value))


def _identity(value):
    try:
        return text(value, MAX_IDENTITY_BYTES)
    except LaunchInputError:
        fail("IDENTITY_INVALID")


def _integer(value, code, low, high):
    # ``type(value) is int`` refuses bool: a boolean is never an exact count.
    if type(value) is not int or not low <= value <= high:
        fail(code)
    return value


def _repository(value):
    if type(value) is not str or len(value) > MAX_REPOSITORY_BYTES:
        fail("REPOSITORY_INVALID")
    if not _REPOSITORY_RE.match(value):
        fail("REPOSITORY_INVALID")
    owner, name = value.split("/", 1)
    if owner in (".", "..") or name in (".", ".."):
        fail("REPOSITORY_INVALID")
    return value


def _head_sha(value):
    if type(value) is not str or not _HEAD_SHA_RE.match(value):
        fail("HEAD_SHA_INVALID")
    return value


def _utc_timestamp(value):
    try:
        stamp = timestamp(value)
    except LaunchInputError:
        fail("DUE_AT_INVALID")
    if stamp.utcoffset() != dt.timedelta(0):
        fail("DUE_AT_NOT_UTC")
    return stamp


def parse_request(value):
    """Validate one frozen request. No field grants authority."""
    if type(value) is not dict:
        fail("REQUEST_OBJECT_REQUIRED")
    if value.get("schema") != SCHEMA:
        fail("REQUEST_SCHEMA_INVALID")
    source = value.get("source")
    if type(source) is not str or source not in SOURCES:
        fail("REQUEST_SOURCE_INVALID")
    required, optional = _SOURCE_FIELDS[source]
    if set(value) - (_COMMON_FIELDS | required | optional):
        fail("REQUEST_FIELDS_UNKNOWN")
    if (_COMMON_FIELDS | required) - set(value):
        fail("REQUEST_FIELDS_MISSING")

    identity = [_identity(value[name]) for name in
                ("run_id", "root_id", "parent_id", "watch_id")]

    limits_raw = value["limits"]
    if type(limits_raw) is not dict or set(limits_raw) != LIMIT_FIELDS:
        fail("LIMITS_INVALID")
    timeout_seconds = _integer(
        limits_raw["timeout_seconds"], "LIMIT_TIMEOUT_INVALID", 1, MAX_TIMEOUT_SECONDS)
    interval_seconds = _integer(
        limits_raw["interval_seconds"], "LIMIT_INTERVAL_INVALID", 1, MAX_INTERVAL_SECONDS)
    max_samples = _integer(
        limits_raw["max_samples"], "LIMIT_SAMPLES_INVALID", 1, MAX_SAMPLES)
    if source in NETWORK_SOURCES and interval_seconds < MIN_NETWORK_INTERVAL_SECONDS:
        fail("LIMIT_INTERVAL_TOO_SHORT_FOR_NETWORK_SOURCE")
    limits = Limits(timeout_seconds, interval_seconds, max_samples)

    params = {}
    if source == "timer":
        params = {"due_at": _utc_timestamp(value["due_at"]).isoformat()}
    elif source in ("github_ci", "github_review"):
        params = {
            "repository": _repository(value["repository"]),
            "pull_request": _integer(value["pull_request"], "PULL_REQUEST_INVALID", 1, 10 ** 9),
            "expected_head_sha": _head_sha(value["expected_head_sha"]),
        }
        if source == "github_ci":
            run_ids = value["workflow_run_ids"]
            if type(run_ids) is not list or not run_ids or len(run_ids) > MAX_WORKFLOW_RUN_IDS:
                fail("WORKFLOW_RUN_IDS_INVALID")
            unique, seen = [], set()
            for run_id in run_ids:
                run_id = _integer(run_id, "WORKFLOW_RUN_IDS_INVALID", 1, 10 ** 12)
                if run_id in seen:
                    fail("WORKFLOW_RUN_IDS_DUPLICATE")
                seen.add(run_id)
                unique.append(run_id)
            params["workflow_run_ids"] = unique
        else:
            params["after_review_id"] = _integer(
                value["after_review_id"], "AFTER_REVIEW_ID_INVALID", 0, 10 ** 12)
            if "review_baseline" in value:
                baseline = value["review_baseline"]
                if type(baseline) is not list or len(baseline) > REVIEW_PAGE_SIZE * MAX_REVIEW_PAGES:
                    fail("REVIEW_BASELINE_INVALID")
                rows, seen = [], set()
                for row in baseline:
                    if type(row) is not dict or set(row) != {"id", "state", "commit", "login"}:
                        fail("REVIEW_BASELINE_INVALID")
                    try:
                        normal = _normal_review(row["id"], row["state"], row["commit"], row["login"])
                    except SourceUnavailable:
                        fail("REVIEW_BASELINE_INVALID")
                    if normal["id"] in seen or normal["id"] > params["after_review_id"]:
                        fail("REVIEW_BASELINE_INVALID")
                    seen.add(normal["id"])
                    rows.append(normal)
                params["review_baseline"] = sorted(rows, key=lambda row: row["id"])
    else:
        service = value["service"]
        if type(service) is not str or service not in observe.ENDPOINTS:
            fail("SERVICE_NOT_ALLOWED")
        expected_state = value.get("expected_state")
        if expected_state is not None and (
                type(expected_state) is not str or expected_state not in HEALTH_STATES):
            fail("EXPECTED_STATE_INVALID")
        params = {"service": service, "expected_state": expected_state}

    return WatchSpec(
        run_id=identity[0], root_id=identity[1], parent_id=identity[2],
        watch_id=identity[3], source=source, limits=limits, params=params,
        source_digest=_digest_of({"source": source, "spec": params}),
    )


def _result(spec, outcome, event, signal_payload, sample_count):
    return {
        "schema": RESULT_SCHEMA,
        "run_id": spec.run_id,
        "root_id": spec.root_id,
        "parent_id": spec.parent_id,
        "watch_id": spec.watch_id,
        "source": spec.source,
        "source_digest": spec.source_digest,
        "outcome": outcome,
        "event": event,
        "signal": signal_payload,
        "sample_count": sample_count,
        "release_authorized": False,
        "retry_authorized": False,
        "native_parent_wake": False,
        "execution_authority": False,
    }


def _gh_argv(path):
    """Build one GET-only read command. No shell, no injection, no write."""
    if type(path) is not str or not path or len(path) > 1024:
        raise _unavailable("GH_PATH_INVALID")
    if any(character in path for character in ("\x00", "\n", "\r")):
        raise _unavailable("GH_PATH_INVALID")
    return ["gh", "api", path, "--method", "GET", "--hostname", "github.com"]


def _bounded_json(raw):
    """Strict bounded external JSON, including list-valued GitHub endpoints."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_RESPONSE_BYTES:
        raise _unavailable("GH_RESPONSE_TOO_LARGE" if raw else "GH_RESPONSE_INVALID")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("nonfinite number")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        stack = [(value, 0)]
        while stack:
            node, depth = stack.pop()
            if depth > MAX_JSON_DEPTH:
                raise ValueError("JSON depth exceeded")
            if isinstance(node, dict):
                stack.extend((child, depth + 1) for child in node.values())
            elif isinstance(node, list):
                stack.extend((child, depth + 1) for child in node)
            elif type(node) is float and not math.isfinite(node):
                raise ValueError("nonfinite number")
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise _unavailable("GH_RESPONSE_INVALID") from None


def _gh_get_json(path, timeout, *, check=None):
    """Stream a bounded GET and always reap its exact child, including overflow."""
    process = None
    selector = None
    deadline = time.monotonic() + float(timeout)
    data = bytearray()

    def remaining():
        if check is not None:
            check()
        left = deadline - time.monotonic()
        if left <= 0:
            raise _unavailable("GH_API_TIMEOUT")
        return left

    try:
        remaining()
        process = subprocess.Popen(_gh_argv(path), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False, bufsize=0)
        assert process.stdout is not None
        os.set_blocking(process.stdout.fileno(), False)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            ready = selector.select(min(remaining(), CANCEL_POLL_SECONDS))
            remaining()
            if not ready:
                continue
            chunk = os.read(process.stdout.fileno(), min(8192, MAX_RESPONSE_BYTES + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_RESPONSE_BYTES:
                raise _unavailable("GH_RESPONSE_TOO_LARGE")
        code = process.wait(timeout=remaining())
        remaining()
        if code != 0:
            raise _unavailable("GH_API_FAILED", exit_code=code)
        return _bounded_json(bytes(data))
    except FileNotFoundError:
        raise _unavailable("GH_EXECUTABLE_MISSING") from None
    except subprocess.TimeoutExpired:
        raise _unavailable("GH_API_TIMEOUT") from None
    except OSError:
        raise _unavailable("GH_API_UNAVAILABLE") from None
    finally:
        if selector is not None:
            selector.close()
        if process is not None:
            if process.poll() is None:
                process.kill()  # Only the process this call actually created.
            process.wait()     # SIGKILL/reap; no detached reader survives a return.
            if process.stdout is not None:
                process.stdout.close()


def _read_pull_request_head(spec, gh_get, timeout):
    path = ("repos/" + spec.params["repository"] + "/pulls/"
            + str(spec.params["pull_request"]))
    value = gh_get(path, timeout)
    if type(value) is not dict:
        raise _unavailable("PULL_REQUEST_RESPONSE_INVALID")
    if type(value.get("number")) is not int or value["number"] != spec.params["pull_request"]:
        raise _unavailable("PULL_REQUEST_IDENTITY_MISMATCH")
    base = value.get("base")
    full_name = base.get("repo", {}).get("full_name") if type(base) is dict and type(base.get("repo")) is dict else None
    if type(full_name) is not str or full_name.casefold() != spec.params["repository"].casefold():
        raise _unavailable("PULL_REQUEST_REPOSITORY_MISMATCH")
    head = value.get("head")
    if type(head) is not dict:
        raise _unavailable("PULL_REQUEST_RESPONSE_INVALID")
    sha = head.get("sha")
    if type(sha) is not str or not _HEAD_SHA_RE.match(sha):
        raise _unavailable("PULL_REQUEST_HEAD_INVALID")
    return sha


def _observe_with_head_guard(spec, gh_get, read_body, timeout):
    """Read the PR head, run the body reader, then re-read the head."""
    expected = spec.params["expected_head_sha"]
    head_before = _read_pull_request_head(spec, gh_get, timeout)
    if head_before != expected:
        raise _Stale(head_before, "pull_request_head")
    body = read_body(timeout)
    head_after = _read_pull_request_head(spec, gh_get, timeout)
    if head_after != head_before:
        raise _Stale(head_after, "pull_request_head")
    return head_after, body


def _stale(spec, observed, origin):
    return Sample(
        digest=_digest_of({"event": "STALE", "head": observed}),
        event="STALE",
        signal={
            "code": "HEAD_CHANGED",
            "expected_head_sha": spec.params["expected_head_sha"],
            "observed_head_sha": observed,
            "observed_at": origin,
        },
    )


def _make_timer_sampler(spec, wall):
    due_at = dt.datetime.fromisoformat(spec.params["due_at"])

    def sample(remaining):
        if wall() >= due_at:
            return Sample(
                digest=_digest_of({"event": "TIMER_DUE", "due_at": spec.params["due_at"]}),
                event="TIMER_DUE",
                signal={"code": "TIMER_DUE", "due_at": spec.params["due_at"]},
            )
        return Sample(
            digest=_digest_of({"state": "PENDING", "due_at": spec.params["due_at"]}),
        )

    return sample


def _read_workflow_run(spec, gh_get, run_id, timeout):
    repository = spec.params["repository"]

    def invalid(code):
        return _unavailable(code, run_id=run_id)

    value = gh_get("repos/" + repository + "/actions/runs/" + str(run_id), timeout)
    if type(value) is not dict:
        raise invalid("WORKFLOW_RUN_RESPONSE_INVALID")
    if type(value.get("id")) is not int or value["id"] != run_id:
        raise invalid("WORKFLOW_RUN_IDENTITY_MISMATCH")
    execution_repository = value.get("repository")
    full_name = execution_repository.get("full_name") if type(execution_repository) is dict else None
    if type(full_name) is not str or full_name.casefold() != repository.casefold():
        raise invalid("WORKFLOW_RUN_IDENTITY_MISMATCH")
    # head_repository may legitimately be a contributor's fork. The execution
    # repository and exact head are the identities this watch actually binds.
    attempt = value.get("run_attempt")
    if type(attempt) is not int or not 1 <= attempt <= 10 ** 6:
        raise invalid("WORKFLOW_RUN_ATTEMPT_INVALID")
    run_head = value.get("head_sha")
    if type(run_head) is not str or not _HEAD_SHA_RE.match(run_head):
        raise invalid("WORKFLOW_RUN_RESPONSE_INVALID")
    status = value.get("status")
    if type(status) is not str:
        raise invalid("WORKFLOW_RUN_RESPONSE_INVALID")
    conclusion = value.get("conclusion")
    if status == "completed":
        if type(conclusion) is not str or conclusion not in WORKFLOW_CONCLUSIONS:
            raise invalid("WORKFLOW_RUN_CONCLUSION_INVALID")
    elif status not in PENDING_WORKFLOW_STATUSES:
        raise invalid("WORKFLOW_RUN_STATUS_INVALID")
    return {
        "run_id": run_id,
        "run_attempt": attempt,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "head_sha": run_head,
    }


def _make_ci_sampler(spec, gh_get):
    def read_runs(timeout):
        runs = []
        for run_id in spec.params["workflow_run_ids"]:
            run = _read_workflow_run(spec, gh_get, run_id, timeout)
            if run["head_sha"] != spec.params["expected_head_sha"]:
                raise _Stale(run["head_sha"], "workflow_run_head")
            runs.append({
                "run_id": run["run_id"],
                "run_attempt": run["run_attempt"],
                "status": run["status"],
                "conclusion": run["conclusion"],
            })
        return runs

    def sample(remaining):
        timeout = min(MAX_COMMAND_TIMEOUT_SECONDS, float(remaining))
        try:
            head, runs = _observe_with_head_guard(spec, gh_get, read_runs, timeout)
        except _Stale as stale:
            return _stale(spec, stale.observed, stale.origin)
        if all(run["status"] == "completed" for run in runs):
            return Sample(
                digest=_digest_of({"event": "CI_TERMINAL", "runs": runs}),
                event="CI_TERMINAL",
                signal={"code": "CI_TERMINAL", "head_sha": head, "runs": runs},
            )
        return Sample(
            digest=_digest_of({"state": "PENDING", "head": head, "runs": runs}),
        )

    return sample


def _normal_review(review_id, state, commit, login):
    if (type(review_id) is not int or not 1 <= review_id <= 10 ** 12
            or type(state) is not str or state not in {
                *FORMAL_REVIEW_STATES, "COMMENTED", "PENDING",
            }
            or type(commit) is not str or not _HEAD_SHA_RE.fullmatch(commit)
            or type(login) is not str or not login or len(login) > MAX_REVIEW_LOGIN_BYTES
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\[\]-]*", login)):
        raise _unavailable("REVIEW_RECORD_INVALID")
    return {"id": review_id, "state": state, "commit": commit, "login": login}


def _read_reviews(spec, gh_get, timeout):
    """Bounded full pagination. Partial coverage fails closed."""
    repository = spec.params["repository"]
    records = {}
    for page in range(1, MAX_REVIEW_PAGES + 1):
        path = ("repos/" + repository + "/pulls/" + str(spec.params["pull_request"])
                + "/reviews?per_page=" + str(REVIEW_PAGE_SIZE) + "&page=" + str(page))
        value = gh_get(path, timeout)
        if type(value) is not list or len(value) > REVIEW_PAGE_SIZE:
            raise _unavailable("REVIEWS_RESPONSE_INVALID")
        for row in value:
            if type(row) is not dict:
                raise _unavailable("REVIEW_RECORD_INVALID")
            review_id, state = row.get("id"), row.get("state")
            commit = row.get("commit_id")
            user = row.get("user")
            login = user.get("login") if type(user) is dict else None
            normal = _normal_review(review_id, state, commit, login)
            if review_id in records and records[review_id] != normal:
                raise _unavailable("REVIEW_ID_CONFLICT")
            records[review_id] = normal
        if len(value) < REVIEW_PAGE_SIZE:
            return [records[key] for key in sorted(records)]
    raise _unavailable("REVIEW_COVERAGE_INCOMPLETE")


def _make_review_sampler(spec, gh_get):
    supplied = spec.params.get("review_baseline")
    baseline = None if supplied is None else {row["id"]: row for row in supplied}

    def sample(remaining):
        nonlocal baseline
        timeout = min(MAX_COMMAND_TIMEOUT_SECONDS, float(remaining))
        try:
            head, records = _observe_with_head_guard(
                spec, gh_get, lambda t: _read_reviews(spec, gh_get, t), timeout)
        except _Stale as stale:
            return _stale(spec, stale.observed, stale.origin)
        changed = []
        if baseline is None:
            # Without an owner baseline, the first complete acquisition is the
            # reference for existing IDs. A later dismissal keeps that ID.
            baseline = {row["id"]: row for row in records
                        if row["id"] <= spec.params["after_review_id"]}
        for record in records:
            prior = baseline.get(record["id"])
            if record["id"] <= spec.params["after_review_id"] and (
                    prior is None or prior == record):
                continue
            if record["state"] not in FORMAL_REVIEW_STATES:
                continue
            if record["commit"] != head:
                # A record on another commit is stale or future, never authority.
                continue
            changed.append({
                "id": record["id"],
                "login": record["login"],
                "state": record["state"],
                "commit": record["commit"],
            })
        changed.sort(key=lambda row: row["id"])
        if changed:
            return Sample(
                digest=_digest_of({"event": "REVIEW_CHANGED", "reviews": changed}),
                event="REVIEW_CHANGED",
                signal={"code": "REVIEW_CHANGED", "head_sha": head, "reviews": changed},
            )
        return Sample(
            digest=_digest_of({"state": "PENDING", "head": head, "reviews": records}),
        )

    return sample


def _http_health(exc):
    if exc.code == 401:
        return "AUTH_REQUIRED"
    if exc.code == 403:
        return "DENIED"
    return "UNAVAILABLE"


def _service_evidence_health(service, result):
    """Require the fixed action's affirmative shape, not a non-error envelope."""
    if type(result) is not dict:
        return "UNAVAILABLE"
    value = result.get("structuredContent")
    content = result.get("content")
    parsed = None
    if type(content) is list and len(content) == 1 and type(content[0]) is dict:
        row = content[0]
        if row.get("type") == "text" and type(row.get("text")) is str:
            try:
                parsed = _bounded_json(row["text"].encode("utf-8"))
            except (SourceUnavailable, UnicodeError):
                parsed = None
    if value is None:
        value = parsed
    explicit = value if type(value) is dict else {}
    state = next((explicit[key] for key in ("state", "status", "code")
                  if explicit.get(key) in ("DENIED", "FORBIDDEN", "PERMISSION_DENIED",
                    "AUTH_REQUIRED", "UNAUTHORIZED", 401, 403)), None)
    is_error = result.get("isError") is True or "error" in result or "error" in explicit or state is not None
    if is_error:
        encoded = json.dumps(result, default=lambda _: "", ensure_ascii=True)[:MAX_RESPONSE_BYTES].lower()
        if state in ("AUTH_REQUIRED", "UNAUTHORIZED", 401) or re.search(
                r"unauthorized|authentication required|auth_required", encoded):
            return "AUTH_REQUIRED"
        if state in ("DENIED", "FORBIDDEN", "PERMISSION_DENIED", 403) or re.search(
                r"permission.denied|access.denied|forbidden|not.authorized", encoded):
            return "DENIED"
        return "UNAVAILABLE"
    if type(value) is not dict or (parsed is not None and canonical(parsed) != canonical(value)):
        return "UNAVAILABLE"
    if service == "studio-read":
        if any(type(value.get(key)) is not str or not 0 < len(value[key]) <= 192
               for key in ("timestamp", "generation", "pingId", "gatewayVersion")):
            return "UNAVAILABLE"
        try:
            stamp = dt.datetime.fromisoformat(value["timestamp"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                return "UNAVAILABLE"
        except ValueError:
            return "UNAVAILABLE"
        if any(type(value.get(key)) not in (int, float) or not math.isfinite(value[key]) or value[key] < 0
               for key in ("monotonicMs", "monotonicDurationMs")):
            return "UNAVAILABLE"
        return "READY"
    hits = value.get("hits")
    if type(hits) is not list or not 0 < len(hits) <= 100:
        return "UNAVAILABLE"
    for hit in hits:
        if type(hit) is not dict or type(hit.get("url")) is not str:
            return "UNAVAILABLE"
        url = urllib.parse.urlsplit(hit["url"])
        if url.scheme != "https" or url.hostname not in {
                "developers.openai.com", "platform.openai.com", "help.openai.com", "learn.chatgpt.com"}:
            return "UNAVAILABLE"
        if type(hit.get("hierarchy")) is not dict or not any(
                type(text) is str and text for text in hit["hierarchy"].values()):
            return "UNAVAILABLE"
    return "READY"


def _default_service_probe(service, timeout, *, check=None):
    """Reuse the existing read-only MCP observation and classify its health."""
    try:
        probe = observe.ReadOnlyMcpProbe(service, deadline=time.monotonic() + timeout,
                                       clock=time.monotonic, check=check)
        initialized, tools = probe.observe()
        if (type(initialized) is not dict or type(initialized.get("protocolVersion")) is not str
                or type(initialized.get("capabilities")) is not dict
                or type(initialized.get("serverInfo")) is not dict
                or any(type(initialized["serverInfo"].get(key)) is not str
                       or not initialized["serverInfo"][key] for key in ("name", "version"))):
            return "UNAVAILABLE"
        names = {row.get("name") for row in tools if type(row) is dict}
        action = "search_openai_docs" if service == "openai-docs" else "studio_ping"
        if action not in names:
            return "DEGRADED"
        arguments = {"query": "skills"} if service == "openai-docs" else {}
        result = probe.call("tools/call", {"name": action, "arguments": arguments}, 3)
        return _service_evidence_health(service, result)
    except urllib.error.HTTPError as exc:
        return _http_health(exc)
    except observe.ProbeResponseError as exc:
        return exc.state
    except urllib.error.URLError:
        return "UNAVAILABLE"
    except (ValueError, OSError, StopIteration, TypeError):
        return "UNAVAILABLE"


def _make_health_sampler(spec, service_probe):
    service = spec.params["service"]
    expected_state = spec.params["expected_state"]
    baseline = {"value": None}

    def sample(remaining):
        health = service_probe(service, min(MAX_COMMAND_TIMEOUT_SECONDS, remaining))
        if type(health) is not str or health not in HEALTH_STATES:
            raise _unavailable("SERVICE_HEALTH_INVALID")
        if health in TERMINAL_HEALTH_STATES:
            raise _unavailable("SERVICE_" + health, service=service)
        if expected_state is not None:
            reference = expected_state
        elif baseline["value"] is None:
            baseline["value"] = health
            reference = health
        else:
            reference = baseline["value"]
        if health != reference:
            return Sample(
                digest=_digest_of({"event": "SERVICE_CHANGED", "health": health}),
                event="SERVICE_CHANGED",
                signal={
                    "code": "SERVICE_CHANGED",
                    "service": service,
                    "from": reference,
                    "to": health,
                },
            )
        # Only the readiness/error class is compared. A per-ping nonce or
        # timestamp never reaches this digest.
        return Sample(digest=_digest_of({"service": service, "health": health}))

    return sample


def _build_sampler(spec, *, wall, gh_get, service_probe):
    if spec.source == "timer":
        return _make_timer_sampler(spec, wall)
    if spec.source == "github_ci":
        return _make_ci_sampler(spec, gh_get)
    if spec.source == "github_review":
        return _make_review_sampler(spec, gh_get)
    return _make_health_sampler(spec, service_probe)


class _SourceSpec:
    """The minimal read-only view the incumbent readers already expect."""

    def __init__(self, params):
        self.params = params


def read_external_sample(source, *, timeout_ms=10_000, max_api_calls=1,
                         max_response_bytes=MAX_RESPONSE_BYTES, gh_get=None,
                         service_probe=None, check=None):
    """Take exactly one bounded sample of one external source.

    The caller owns the reservation and every budget; this performs at most
    ``max_api_calls`` reads, bounds each by the remaining timeout, and returns
    the measured call and byte counts.  It has no loop, no retry, no state, no
    write and no authority.  A bounded source failure raises
    :class:`SourceUnavailable`; it never becomes a success.
    """

    if type(source) is not dict or source.get("kind") not in EXTERNAL_SOURCE_KINDS:
        raise _unavailable("EXTERNAL_SOURCE_INVALID")
    kind = source["kind"]
    if type(timeout_ms) is not int or timeout_ms <= 0:
        raise _unavailable("EXTERNAL_TIMEOUT_INVALID")
    if type(max_api_calls) is not int or max_api_calls <= 0:
        raise _unavailable("EXTERNAL_CALL_BUDGET_INVALID")
    if type(max_response_bytes) is not int or max_response_bytes <= 0:
        raise _unavailable("EXTERNAL_BYTE_BUDGET_INVALID")
    timeout = min(float(timeout_ms) / 1000.0, MAX_COMMAND_TIMEOUT_SECONDS)
    counts = {"calls": 0, "bytes": 0}
    reader = gh_get if gh_get is not None else (
        lambda path, remaining: _gh_get_json(path, remaining, check=check))

    def counted(path, remaining):
        if counts["calls"] >= max_api_calls:
            raise _unavailable("EXTERNAL_CALL_BUDGET_EXHAUSTED")
        counts["calls"] += 1
        try:
            value = reader(path, remaining)
        except SourceUnavailable as exc:
            # An explicit credential refusal terminates this watch action; it
            # is never retried as if it were a temporary source failure.
            payload = dict(exc.signal_payload)
            if payload.get("code") == "GH_API_FAILED" and payload.get("exit_code") == 4:
                payload["code"] = "GH_AUTH_REFUSED"
                payload["terminal"] = True
                raise SourceUnavailable(payload) from None
            raise
        size = len(json.dumps(value, ensure_ascii=True, sort_keys=True,
                              separators=(",", ":"), default=str).encode("utf-8"))
        counts["bytes"] += size
        if counts["bytes"] > max_response_bytes:
            raise _unavailable("EXTERNAL_BYTE_BUDGET_EXHAUSTED")
        return value

    if kind in ("github_ci", "github_review"):
        spec = _SourceSpec({
            "repository": source["repository"],
            "pull_request": source["pull_request"],
            "expected_head_sha": source["expected_head_sha"],
        })
        counted_reader = counted
        if kind == "github_ci":
            def read_runs(remaining):
                runs = []
                for entry in source["selected_runs"]:
                    run = _read_workflow_run(spec, counted_reader, entry["run_id"], remaining)
                    runs.append({
                        "run_id": run["run_id"],
                        "run_attempt": run["run_attempt"],
                        "status": run["status"],
                        "conclusion": run["conclusion"],
                    })
                return runs
            head, runs = _observe_with_head_guard(spec, counted_reader, read_runs, timeout)
            facts = {"head_sha": head, "runs": runs}
        else:
            head, records = _observe_with_head_guard(
                spec, counted_reader, lambda t: _read_reviews(spec, counted_reader, t), timeout)
            facts = {"head_sha": head, "reviews": records}
        return {"facts": facts, "api_calls": counts["calls"],
                "response_bytes": counts["bytes"]}

    probe = service_probe or (lambda service, remaining:
                               _default_service_probe(service, remaining, check=check))
    counts["calls"] = 1
    state = probe(source["service"], timeout)
    if type(state) is not str or state not in HEALTH_STATES:
        raise _unavailable("SERVICE_HEALTH_INVALID")
    counts["bytes"] = len(state.encode("utf-8"))
    return {"facts": {"state": state}, "api_calls": counts["calls"],
            "response_bytes": counts["bytes"]}


def _install_sigterm(state):
    def handler(signum, frame):
        state["triggered"] = True

    try:
        previous = signal.signal(signal.SIGTERM, handler)
    except (ValueError, OSError, AttributeError):
        return None

    def restore():
        try:
            signal.signal(signal.SIGTERM, previous)
        except (ValueError, OSError):
            pass

    return restore


def _wait(seconds, sleep, budget):
    """Wait in short slices so a stop request is noticed promptly.

    Cancellation stays latched even if its callback was a one-shot pulse.
    No other process is signalled and no lease is touched.
    """
    end = min(budget.deadline, budget.clock() + seconds)
    while budget.clock() < end:
        remaining = budget.check()
        sleep(min(end - budget.clock(), remaining, CANCEL_POLL_SECONDS))
    budget.check()


def run_watch(request, *, clock=None, wall=None, sleep=None, gh_get=None,
              service_probe=None, cancel=None, handle_signals=True):
    """Run one finite watch and return exactly one bounded result.

    ``clock`` is the monotonic deadline clock, ``wall`` the UTC wall clock,
    ``sleep`` the pause, ``gh_get`` the GitHub reader, ``service_probe`` the
    service health reader ``(service, remaining_timeout)`` and ``cancel`` a
    callback that reports a requested stop. Every read gets the current bound;
    an injected reader must honor it. Tests need no network.
    """
    spec = request if isinstance(request, WatchSpec) else parse_request(request)
    clock = clock or time.monotonic
    wall = wall or (lambda: dt.datetime.now(dt.timezone.utc))
    sleep = sleep or time.sleep
    cancel_state = {"triggered": False}
    budget = _Budget(clock, clock() + spec.limits.timeout_seconds, cancel, cancel_state)
    raw_gh_get = gh_get or (lambda path, timeout: _gh_get_json(path, timeout, check=budget.check))
    raw_service_probe = service_probe or (lambda service, timeout:
        _default_service_probe(service, timeout, check=budget.check))
    gh_get = lambda path, timeout: budget.read(raw_gh_get, path, timeout)
    service_probe = lambda service, timeout: budget.read(raw_service_probe, service, timeout)
    restore = _install_sigterm(cancel_state) if handle_signals else None
    sample_count = 0
    due_at = None

    def done(outcome, event, payload):
        return _result(spec, outcome, event, payload, sample_count)

    try:
        budget.check()
        if spec.source == "timer":
            due_at = dt.datetime.fromisoformat(spec.params["due_at"])
            if (due_at - wall()).total_seconds() > budget.check():
                return done("TIMEOUT", None, {"code": "DEADLINE_OUTSIDE_BUDGET"})
        sampler = _build_sampler(
            spec, wall=wall, gh_get=gh_get, service_probe=service_probe)
        previous_digest = None
        while True:
            remaining = budget.check()
            sample_count += 1
            try:
                sample = sampler(remaining)
            except SourceUnavailable as exc:
                budget.check()
                return done("SOURCE_UNAVAILABLE", None, exc.signal_payload)
            budget.check()
            if sample.event is not None:
                return done("EVENT", sample.event, sample.signal or {})
            if previous_digest is None or sample.digest != previous_digest:
                previous_digest = sample.digest
            if sample_count >= spec.limits.max_samples:
                return done("TIMEOUT", None, {"code": "SAMPLE_BUDGET_EXHAUSTED"})
            delay = min(float(spec.limits.interval_seconds), budget.check())
            if due_at is not None:
                until_due = (due_at - wall()).total_seconds()
                if until_due > 0:
                    delay = min(delay, until_due)
            if delay > 0:
                _wait(delay, sleep, budget)
    except _Cancelled as exc:
        return done("CANCELLED", None, {"code": exc.code})
    except _DeadlineExceeded:
        return done("TIMEOUT", None, {"code": "DEADLINE_EXCEEDED"})
    except KeyboardInterrupt:
        return done("CANCELLED", None, {"code": "CANCELLED_BY_INTERRUPT"})
    finally:
        if restore is not None:
            restore()


def main(argv=None):
    """Print exactly one JSON result for one request file."""
    parser = argparse.ArgumentParser(
        description="Run one finite Class-T watch for an admitted Fabric worker.")
    parser.add_argument("request", help="Path to one finite-watch request JSON file.")
    args = parser.parse_args(argv)
    try:
        # Imported at invocation time: ops.fabric_launch.cli imports this
        # module's neighbours, so a module-level import would close a cycle.
        from ops.fabric_launch.cli import read_regular
        raw = read_regular(args.request, MAX_INPUT_BYTES)
        result = run_watch(parse_json(raw, MAX_INPUT_BYTES))
    except LaunchInputError as exc:
        print("FABRIC_FINITE_WATCH_REFUSED " + str(exc), file=sys.stderr)
        return 78
    except (OSError, ValueError, UnicodeError) as exc:
        print("FABRIC_FINITE_WATCH_REFUSED " + type(exc).__name__, file=sys.stderr)
        return 78
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
