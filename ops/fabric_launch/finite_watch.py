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
import re
import signal
import subprocess
import sys
import time
import urllib.error
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
    }), frozenset()),
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


def _gh_get_json(path, timeout):
    """One bounded read. The response text never leaves this function."""
    try:
        completed = subprocess.run(
            _gh_argv(path),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        raise _unavailable("GH_EXECUTABLE_MISSING")
    except subprocess.TimeoutExpired:
        raise _unavailable("GH_API_TIMEOUT")
    except OSError:
        raise _unavailable("GH_API_UNAVAILABLE")
    if completed.returncode != 0:
        raise _unavailable("GH_API_FAILED", exit_code=completed.returncode)
    if len(completed.stdout) > MAX_RESPONSE_BYTES:
        raise _unavailable("GH_RESPONSE_TOO_LARGE")
    try:
        return json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise _unavailable("GH_RESPONSE_INVALID")


def _read_pull_request_head(spec, gh_get, timeout):
    path = ("repos/" + spec.params["repository"] + "/pulls/"
            + str(spec.params["pull_request"]))
    value = gh_get(path, timeout)
    if type(value) is not dict:
        raise _unavailable("PULL_REQUEST_RESPONSE_INVALID")
    base = value.get("base")
    if type(base) is dict and type(base.get("repo")) is dict:
        full_name = base["repo"].get("full_name")
        if type(full_name) is str and full_name.casefold() != spec.params["repository"].casefold():
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
    if value.get("id") != run_id:
        raise invalid("WORKFLOW_RUN_IDENTITY_MISMATCH")
    head_repository = value.get("head_repository")
    if type(head_repository) is dict:
        full_name = head_repository.get("full_name")
        if type(full_name) is not str or full_name.casefold() != repository.casefold():
            raise invalid("WORKFLOW_RUN_IDENTITY_MISMATCH")
    elif head_repository is not None:
        raise invalid("WORKFLOW_RUN_RESPONSE_INVALID")
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
                "status": run["status"],
                "conclusion": run["conclusion"],
            })
        return runs

    def sample(remaining):
        timeout = max(1.0, min(MAX_COMMAND_TIMEOUT_SECONDS, float(remaining)))
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


def _read_reviews(spec, gh_get, timeout):
    """Bounded full pagination. Partial coverage fails closed."""
    repository = spec.params["repository"]
    records = []
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
            if type(review_id) is not int or review_id < 0 or type(state) is not str:
                raise _unavailable("REVIEW_RECORD_INVALID")
            if commit is not None and (
                    type(commit) is not str or not _HEAD_SHA_RE.match(commit)):
                raise _unavailable("REVIEW_RECORD_INVALID")
            if login is not None and type(login) is not str:
                raise _unavailable("REVIEW_RECORD_INVALID")
            records.append({"id": review_id, "state": state,
                            "commit": commit, "login": login})
        if len(value) < REVIEW_PAGE_SIZE:
            return records
    raise _unavailable("REVIEW_COVERAGE_INCOMPLETE")


def _make_review_sampler(spec, gh_get):
    def sample(remaining):
        timeout = max(1.0, min(MAX_COMMAND_TIMEOUT_SECONDS, float(remaining)))
        try:
            head, records = _observe_with_head_guard(
                spec, gh_get, lambda t: _read_reviews(spec, gh_get, t), timeout)
        except _Stale as stale:
            return _stale(spec, stale.observed, stale.origin)
        changed = []
        for record in records:
            if record["id"] <= spec.params["after_review_id"]:
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


def _default_service_probe(service):
    """Reuse the existing read-only MCP observation and classify its health."""
    try:
        probe = observe.ReadOnlyMcpProbe(service)
        _initialized, tools = probe.observe()
        names = {row.get("name") for row in tools if type(row) is dict}
        action = "search_openai_docs" if service == "openai-docs" else "studio_ping"
        if action not in names:
            return "DEGRADED"
        arguments = {"query": "skills"} if service == "openai-docs" else {}
        result = probe.call("tools/call", {"name": action, "arguments": arguments}, 3)
    except urllib.error.HTTPError as exc:
        return _http_health(exc)
    except urllib.error.URLError:
        return "UNAVAILABLE"
    except ValueError:
        return "DEGRADED"
    except OSError:
        return "UNAVAILABLE"
    if type(result) is not dict or result.get("isError") is True:
        return "DEGRADED"
    return "READY"


def _make_health_sampler(spec, service_probe):
    service = spec.params["service"]
    expected_state = spec.params["expected_state"]
    baseline = {"value": None}

    def sample(remaining):
        health = service_probe(service)
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


def _wait(seconds, sleep, cancel, cancel_state):
    """Wait in short slices so a stop request is noticed promptly.

    Returns False when the wait was cut short by a stop request. No other
    process is signalled and no lease is touched.
    """
    remaining = float(seconds)
    while remaining > 0:
        if cancel_state["triggered"]:
            return False
        if cancel is not None and cancel():
            return False
        step = min(remaining, CANCEL_POLL_SECONDS)
        sleep(step)
        remaining -= step
    return True


def run_watch(request, *, clock=None, wall=None, sleep=None, gh_get=None,
              service_probe=None, cancel=None, handle_signals=True):
    """Run one finite watch and return exactly one bounded result.

    ``clock`` is the monotonic deadline clock, ``wall`` the UTC wall clock,
    ``sleep`` the pause, ``gh_get`` the GitHub reader, ``service_probe`` the
    service health reader and ``cancel`` a callback that reports a requested
    stop. Every one of them is injectable so tests never touch the network.
    """
    spec = request if isinstance(request, WatchSpec) else parse_request(request)
    clock = clock or time.monotonic
    wall = wall or (lambda: dt.datetime.now(dt.timezone.utc))
    sleep = sleep or time.sleep
    gh_get = gh_get or _gh_get_json
    service_probe = service_probe or _default_service_probe

    cancel_state = {"triggered": False}
    restore = _install_sigterm(cancel_state) if handle_signals else None
    sample_count = 0
    due_at = None

    def done(outcome, event, payload):
        return _result(spec, outcome, event, payload, sample_count)

    if spec.source == "timer":
        due_at = dt.datetime.fromisoformat(spec.params["due_at"])
        if (due_at - wall()).total_seconds() > spec.limits.timeout_seconds:
            # The deadline is not inside the admitted finite duration.
            return done("TIMEOUT", None, {"code": "DEADLINE_OUTSIDE_BUDGET"})
    try:
        sampler = _build_sampler(
            spec, wall=wall, gh_get=gh_get, service_probe=service_probe)
        previous_digest = None
        deadline = clock() + spec.limits.timeout_seconds
        while True:
            if cancel is not None and cancel():
                return done("CANCELLED", None, {"code": "CANCELLED_BY_CALLBACK"})
            if cancel_state["triggered"]:
                return done("CANCELLED", None, {"code": "CANCELLED_BY_SIGNAL"})
            remaining = deadline - clock()
            if remaining <= 0:
                return done("TIMEOUT", None, {"code": "DEADLINE_EXCEEDED"})
            sample_count += 1
            try:
                sample = sampler(remaining)
            except SourceUnavailable as exc:
                return done("SOURCE_UNAVAILABLE", None, exc.signal_payload)
            if sample.event is not None:
                return done("EVENT", sample.event, sample.signal or {})
            if previous_digest is None or sample.digest != previous_digest:
                previous_digest = sample.digest
            if sample_count >= spec.limits.max_samples:
                return done("TIMEOUT", None, {"code": "SAMPLE_BUDGET_EXHAUSTED"})
            delay = min(float(spec.limits.interval_seconds), deadline - clock())
            if due_at is not None:
                until_due = (due_at - wall()).total_seconds()
                if until_due > 0:
                    delay = min(delay, until_due)
            if delay > 0:
                _wait(delay, sleep, cancel, cancel_state)
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
