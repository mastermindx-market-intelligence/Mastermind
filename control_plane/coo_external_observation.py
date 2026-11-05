"""Versioned external observation gates for the existing Runtime/COO owner.

A V7 plan step may park one bounded external source instead of holding a paid
worker lease.  The plan binds identity, baseline and budgets only.  The trusted
host owns the private capability and the single-sample reader; a caller string,
hash, timestamp or Python type is never authentication.

Nothing here grants a write, a release, a required-check policy, a retry of a
denied action, or unattended healing authority.  A completed selected CI run is
material evidence with its actual conclusion; it is never branch-green and never
release authority.  A formal review record is never reviewer independence and
never merge approval.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from control_plane.coo_observation import (
    EXTERNAL_GATE_SCHEMA,
    EXTERNAL_SOURCE_KINDS,
    MAX_EXTERNAL_INPUT_BYTES,
    MAX_HORIZON_MS,
    ObservationError,
    canonical_bytes,
    digest,
)


SOURCE_KINDS = ("timer", "github_ci", "github_review", "service_health")

FORMAL_REVIEW_STATES = ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")
REVIEW_STATES = (*FORMAL_REVIEW_STATES, "COMMENTED", "PENDING")
HEALTH_STATES = ("READY", "DEGRADED", "UNAVAILABLE", "AUTH_REQUIRED", "DENIED")
TERMINAL_HEALTH_STATES = frozenset({"AUTH_REQUIRED", "DENIED"})

DISPOSITIONS = (
    "MATERIAL", "PENDING", "STALE", "UNAVAILABLE", "DENIED", "EXPIRED", "INTERRUPTED",
)
TERMINAL_DISPOSITIONS = frozenset({"STALE", "DENIED", "EXPIRED"})

MAX_SELECTED_RUNS = 40
MAX_REPOSITORY_BYTES = 100
MAX_LOGIN_BYTES = 100
MAX_SERVICE_BYTES = 64
MAX_API_CALLS = 64
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_SAMPLES = 16
MAX_SAMPLE_TIMEOUT_MS = 120_000
MAX_INTERVAL_MS = 15 * 60 * 1000
PER_SAMPLE_RESPONSE_BYTES = 64 * 1024

_REPOSITORY_RE = re.compile(r"\A[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_HEAD_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")
_LOGIN_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.\[\]-]*\Z")
_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")


class ExternalSourceError(Exception):
    """A bounded source failure.  Carries a code and whether it terminates."""

    def __init__(self, code: str, *, terminal: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.terminal = terminal


def _closed(value: Any, keys: set[str], name: str, *,
            max_bytes: int = MAX_EXTERNAL_INPUT_BYTES) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ObservationError(f"{name} is not the closed wire")
    canonical_bytes(value, max_bytes=max_bytes)
    return copy.deepcopy(value)


def _integer(value: Any, *, minimum: int = 0, maximum: int = 2 ** 63 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ObservationError("observation integer is out of bounds")
    return value


def _repository(value: Any) -> str:
    if type(value) is not str or not 0 < len(value) <= MAX_REPOSITORY_BYTES:
        raise ObservationError("external source repository is invalid")
    if _REPOSITORY_RE.match(value) is None:
        raise ObservationError("external source repository is invalid")
    owner, name = value.split("/", 1)
    if owner in (".", "..") or name in (".", ".."):
        raise ObservationError("external source repository is invalid")
    return value


def _head_sha(value: Any) -> str:
    if type(value) is not str or _HEAD_SHA_RE.match(value) is None:
        raise ObservationError("external source head is invalid")
    return value


def validate_external_source(value: Any) -> dict[str, Any]:
    """Validate one closed external source descriptor."""

    if type(value) is not dict or "kind" not in value:
        raise ObservationError("external source is not the closed wire")
    kind = value["kind"]
    if kind == "timer":
        source = _closed(value, {"kind", "due_at_ms"}, "timer source")
        _integer(source["due_at_ms"])
        return source
    if kind == "github_ci":
        source = _closed(
            value,
            {"kind", "repository", "pull_request", "expected_head_sha", "selected_runs"},
            "github CI source",
        )
        _repository(source["repository"])
        _integer(source["pull_request"], minimum=1, maximum=10 ** 9)
        _head_sha(source["expected_head_sha"])
        runs = source["selected_runs"]
        if type(runs) is not list or not 0 < len(runs) <= MAX_SELECTED_RUNS:
            raise ObservationError("external source selected runs are invalid")
        seen: set[int] = set()
        for run in runs:
            entry = _closed(run, {"run_id", "run_attempt"}, "selected run")
            run_id = _integer(entry["run_id"], minimum=1, maximum=10 ** 12)
            _integer(entry["run_attempt"], minimum=1, maximum=10 ** 6)
            if run_id in seen:
                raise ObservationError("external source selected runs are duplicated")
            seen.add(run_id)
        return source
    if kind == "github_review":
        source = _closed(
            value,
            {"kind", "repository", "pull_request", "expected_head_sha", "baseline"},
            "github review source",
        )
        _repository(source["repository"])
        _integer(source["pull_request"], minimum=1, maximum=10 ** 9)
        _head_sha(source["expected_head_sha"])
        baseline = _closed(
            source["baseline"], {"review_id", "state", "commit", "login"},
            "review baseline",
        )
        _integer(baseline["review_id"], minimum=1, maximum=10 ** 12)
        if baseline["state"] not in REVIEW_STATES:
            raise ObservationError("review baseline state is invalid")
        _head_sha(baseline["commit"])
        if (type(baseline["login"]) is not str or not 0 < len(baseline["login"]) <= MAX_LOGIN_BYTES
                or _LOGIN_RE.match(baseline["login"]) is None):
            raise ObservationError("review baseline login is invalid")
        return source
    if kind == "service_health":
        source = _closed(
            value, {"kind", "service", "baseline_state", "expected_state"},
            "service health source",
        )
        if (type(source["service"]) is not str or not 0 < len(source["service"]) <= MAX_SERVICE_BYTES):
            raise ObservationError("service health identifier is invalid")
        if source["baseline_state"] not in HEALTH_STATES:
            raise ObservationError("service health baseline state is invalid")
        if source["expected_state"] not in HEALTH_STATES:
            raise ObservationError("service health expected state is invalid")
        return source
    raise ObservationError("observation source is not qualified")


def external_gate_schema() -> dict[str, Any]:
    """The closed V7 gate wire.  The published V1 timer gate is unchanged."""

    integer = {"type": "integer", "minimum": 0, "maximum": 2 ** 63 - 1}
    head = {"type": "string", "pattern": _HEAD_SHA_RE.pattern}
    repository = {"type": "string", "minLength": 3, "maxLength": MAX_REPOSITORY_BYTES,
                  "pattern": _REPOSITORY_RE.pattern}
    timer_source = {
        "type": "object", "additionalProperties": False,
        "required": ["kind", "due_at_ms"],
        "properties": {"kind": {"const": "timer"}, "due_at_ms": integer},
    }
    ci_source = {
        "type": "object", "additionalProperties": False,
        "required": ["kind", "repository", "pull_request", "expected_head_sha", "selected_runs"],
        "properties": {
            "kind": {"const": "github_ci"},
            "repository": repository,
            "pull_request": {"type": "integer", "minimum": 1, "maximum": 10 ** 9},
            "expected_head_sha": head,
            "selected_runs": {
                "type": "array", "minItems": 1, "maxItems": MAX_SELECTED_RUNS,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["run_id", "run_attempt"],
                    "properties": {
                        "run_id": {"type": "integer", "minimum": 1, "maximum": 10 ** 12},
                        "run_attempt": {"type": "integer", "minimum": 1, "maximum": 10 ** 6},
                    },
                },
            },
        },
    }
    review_source = {
        "type": "object", "additionalProperties": False,
        "required": ["kind", "repository", "pull_request", "expected_head_sha", "baseline"],
        "properties": {
            "kind": {"const": "github_review"},
            "repository": repository,
            "pull_request": {"type": "integer", "minimum": 1, "maximum": 10 ** 9},
            "expected_head_sha": head,
            "baseline": {
                "type": "object", "additionalProperties": False,
                "required": ["review_id", "state", "commit", "login"],
                "properties": {
                    "review_id": {"type": "integer", "minimum": 1, "maximum": 10 ** 12},
                    "state": {"type": "string", "enum": list(REVIEW_STATES)},
                    "commit": head,
                    "login": {"type": "string", "minLength": 1, "maxLength": MAX_LOGIN_BYTES,
                              "pattern": _LOGIN_RE.pattern},
                },
            },
        },
    }
    health_source = {
        "type": "object", "additionalProperties": False,
        "required": ["kind", "service", "baseline_state", "expected_state"],
        "properties": {
            "kind": {"const": "service_health"},
            "service": {"type": "string", "minLength": 1, "maxLength": MAX_SERVICE_BYTES},
            "baseline_state": {"type": "string", "enum": list(HEALTH_STATES)},
            "expected_state": {"type": "string", "enum": list(HEALTH_STATES)},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "source", "deadline_at_ms", "max_samples",
                     "min_interval_ms", "sample_timeout_ms", "max_api_calls",
                     "max_response_bytes"],
        "properties": {
            "schema_version": {"const": EXTERNAL_GATE_SCHEMA},
            "source": {"anyOf": [timer_source, ci_source, review_source, health_source]},
            "deadline_at_ms": integer,
            "max_samples": {"type": "integer", "minimum": 1, "maximum": MAX_SAMPLES},
            "min_interval_ms": {"type": "integer", "minimum": 0, "maximum": MAX_INTERVAL_MS},
            "sample_timeout_ms": {"type": "integer", "minimum": 0, "maximum": MAX_SAMPLE_TIMEOUT_MS},
            "max_api_calls": {"type": "integer", "minimum": 0, "maximum": MAX_API_CALLS},
            "max_response_bytes": {"type": "integer", "minimum": 0, "maximum": MAX_RESPONSE_BYTES},
        },
    }


def validate_external_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one V2 gate spec.  The V1 timer gate keeps its own meaning."""

    source = validate_external_source(spec["source"])
    kind = source["kind"]
    deadline = _integer(spec["deadline_at_ms"], minimum=1)
    samples = _integer(spec["max_samples"], minimum=1, maximum=MAX_SAMPLES)
    interval = _integer(spec["min_interval_ms"], minimum=0, maximum=MAX_INTERVAL_MS)
    timeout = _integer(spec["sample_timeout_ms"], minimum=0, maximum=MAX_SAMPLE_TIMEOUT_MS)
    calls = _integer(spec["max_api_calls"], minimum=0, maximum=MAX_API_CALLS)
    response_bytes = _integer(spec["max_response_bytes"], minimum=0, maximum=MAX_RESPONSE_BYTES)
    if kind == "timer":
        # A timer keeps its published meaning exactly: one sample and no I/O.
        if (samples, interval, timeout, calls, response_bytes) != (1, 0, 0, 0, 0):
            raise ObservationError("timer budgets must be one sample and zero I/O")
        if source["due_at_ms"] >= deadline:
            raise ObservationError("timer must be due before its acquisition deadline")
        result = dict(spec)
        result["source"] = source
        return result
    if timeout < 1:
        raise ObservationError("external observation budgets are not qualified")
    if calls < per_sample_api_calls(source) or response_bytes < PER_SAMPLE_RESPONSE_BYTES:
        # The gate budget must cover at least one whole bounded sample.
        raise ObservationError("external observation budgets are not qualified")
    result = dict(spec)
    result["source"] = source
    return result


def per_sample_api_calls(source: Mapping[str, Any]) -> int:
    """The bounded API-call cost of one sample of this source."""

    kind = source["kind"]
    if kind == "github_ci":
        return len(source["selected_runs"]) + 2
    if kind == "github_review":
        return 12
    if kind == "service_health":
        # initialize, tools/list, and the fixed read-only tools/call.
        return 3
    return 0


def per_sample_response_bytes(source: Mapping[str, Any]) -> int:
    """The bounded response-byte cost of one sample of this source."""

    kind = source["kind"]
    if kind == "timer":
        return 0
    return PER_SAMPLE_RESPONSE_BYTES


def _snapshot_common(source: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": source["kind"],
        "repository": source.get("repository"),
        "pull_request": source.get("pull_request"),
        "expected_head_sha": source.get("expected_head_sha"),
    }


def evaluate_sample(
    source: Mapping[str, Any], facts: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Classify one bounded sample against the bound source identity.

    Returns ``(disposition, snapshot)``.  The snapshot is the exact bounded
    evidence and is enough to re-derive the disposition on replay.
    """

    kind = source["kind"]
    if kind == "github_ci":
        return _evaluate_ci(source, facts)
    if kind == "github_review":
        return _evaluate_review(source, facts)
    if kind == "service_health":
        return _evaluate_health(source, facts)
    raise ObservationError("observation source is not qualified")


def _evaluate_ci(
    source: Mapping[str, Any], facts: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    from ops.fabric_launch.finite_watch import PENDING_WORKFLOW_STATUSES, WORKFLOW_CONCLUSIONS

    facts = _closed(facts, {"head_sha", "runs"}, "CI facts")
    head, observed = facts["head_sha"], facts["runs"]
    _head_sha(head)
    if type(observed) is not list or not 0 < len(observed) <= MAX_SELECTED_RUNS:
        raise ObservationError("CI run facts are invalid")
    bound = {entry["run_id"]: entry["run_attempt"] for entry in source["selected_runs"]}
    seen: dict[int, Mapping[str, Any]] = {}
    stale = head != source["expected_head_sha"]
    for value in observed:
        run = _closed(value, {"run_id", "run_attempt", "head_sha", "status", "conclusion"},
                      "CI run facts")
        run_id = _integer(run["run_id"], minimum=1, maximum=10 ** 12)
        attempt = _integer(run["run_attempt"], minimum=1, maximum=10 ** 6)
        _head_sha(run["head_sha"])
        if run_id in seen:
            raise ObservationError("CI run facts are duplicated")
        if run["status"] == "completed":
            if type(run["conclusion"]) is not str or run["conclusion"] not in WORKFLOW_CONCLUSIONS:
                raise ObservationError("CI conclusion is invalid")
        elif (type(run["status"]) is not str or run["status"] not in PENDING_WORKFLOW_STATUSES
              or run["conclusion"] is not None):
            raise ObservationError("CI status is invalid")
        stale = stale or bound.get(run_id) != attempt or run["head_sha"] != source["expected_head_sha"]
        seen[run_id] = run
    stale = stale or set(seen) != set(bound)
    terminal = not stale and all(run["status"] == "completed" for run in seen.values())
    snapshot = {**_snapshot_common(source), "head_sha": head,
                "runs": [dict(seen[key]) for key in sorted(seen)], "terminal": terminal}
    return ("STALE" if stale else "MATERIAL" if terminal else "PENDING"), snapshot


def _evaluate_review(
    source: Mapping[str, Any], facts: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    facts = _closed(facts, {"head_sha", "reviews"}, "review facts")
    baseline = source["baseline"]
    head = _head_sha(facts["head_sha"])
    reviews = facts["reviews"]
    snapshot = _snapshot_common(source)
    snapshot["head_sha"] = head
    snapshot["baseline"] = copy.deepcopy(baseline)
    snapshot["changed"] = []
    if type(head) is not str or head != source["expected_head_sha"]:
        return "STALE", snapshot
    if type(reviews) is not list:
        raise ObservationError("review facts are invalid")
    changed: list[dict[str, Any]] = []
    seen: set[int] = set()
    for value in reviews:
        review = _closed(value, {"id", "state", "commit", "login"}, "review facts row")
        review_id = _integer(review["id"], minimum=1, maximum=10 ** 12)
        _head_sha(review["commit"])
        if (review_id in seen or type(review["login"]) is not str
                or not 0 < len(review["login"]) <= MAX_LOGIN_BYTES
                or _LOGIN_RE.fullmatch(review["login"]) is None
                or review["state"] not in REVIEW_STATES):
            raise ObservationError("review facts row is invalid")
        seen.add(review_id)
        state = review["state"]
        if state not in FORMAL_REVIEW_STATES:
            continue
        review_id = review.get("id")
        if type(review_id) is not int:
            return "STALE", snapshot
        if review_id == baseline["review_id"]:
            current = (state, review.get("commit"), review.get("login"))
            if current != (baseline["state"], baseline["commit"], baseline["login"]):
                # The same formal review id changed state, commit or login.
                changed.append({
                    "id": review_id, "state": state,
                    "commit": review.get("commit"), "login": review.get("login"),
                })
        elif review_id > baseline["review_id"] and review.get("commit") == head:
            changed.append({
                "id": review_id, "state": state,
                "commit": review.get("commit"), "login": review.get("login"),
            })
    changed.sort(key=lambda row: row["id"])
    snapshot["changed"] = changed
    return ("MATERIAL" if changed else "PENDING"), snapshot


def _evaluate_health(
    source: Mapping[str, Any], facts: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    facts = _closed(facts, {"state"}, "health facts")
    observed = facts["state"]
    if type(observed) is not str or observed not in HEALTH_STATES:
        observed = None
    snapshot = {
        "kind": "service_health",
        "service": source["service"],
        "baseline_state": source["baseline_state"],
        "expected_state": source["expected_state"],
        "observed_state": observed,
    }
    if type(observed) is not str or observed not in HEALTH_STATES:
        return "UNAVAILABLE", snapshot
    if observed in TERMINAL_HEALTH_STATES:
        # An explicit auth or permission refusal ends this watch action.
        return "DENIED", snapshot
    if observed == "UNAVAILABLE":
        # A temporary missing host capability is not evidence.
        return "UNAVAILABLE", snapshot
    if observed == source["expected_state"] or observed != source["baseline_state"]:
        return "MATERIAL", snapshot
    return "PENDING", snapshot


def disposition_for_snapshot(
    source: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> str:
    """Re-derive a committed disposition from its exact bounded snapshot."""

    if type(snapshot) is not dict or "kind" not in snapshot:
        raise ObservationError("observation snapshot is not the closed wire")
    kind = snapshot["kind"]
    if kind in {"expired", "interrupted"}:
        _closed(snapshot, {"kind"}, "observation terminal snapshot")
        return "EXPIRED" if kind == "expired" else "INTERRUPTED"
    if kind in {"denied", "unavailable"}:
        _closed(snapshot, {"kind", "code"}, "observation error snapshot")
        code = snapshot["code"]
        if type(code) is not str or re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code) is None:
            raise ObservationError("observation error code is invalid")
        return "DENIED" if kind == "denied" else "UNAVAILABLE"
    if kind != source["kind"]:
        raise ObservationError("observation snapshot kind drifted")
    if kind == "github_ci":
        _closed(snapshot, {"kind", "repository", "pull_request", "expected_head_sha",
                           "head_sha", "runs", "terminal"}, "CI snapshot")
        facts = {"head_sha": snapshot["head_sha"], "runs": snapshot["runs"]}
    elif kind == "github_review":
        _closed(snapshot, {"kind", "repository", "pull_request", "expected_head_sha",
                           "head_sha", "baseline", "changed"}, "review snapshot")
        facts = {"head_sha": snapshot["head_sha"], "reviews": snapshot["changed"]}
    elif kind == "service_health":
        _closed(snapshot, {"kind", "service", "baseline_state", "expected_state",
                           "observed_state"}, "health snapshot")
        facts = {"state": snapshot["observed_state"]}
    else:
        raise ObservationError("observation snapshot kind drifted")
    disposition, expected = evaluate_sample(source, facts)
    if canonical_bytes(snapshot, max_bytes=MAX_EXTERNAL_INPUT_BYTES) != canonical_bytes(
            expected, max_bytes=MAX_EXTERNAL_INPUT_BYTES):
        raise ObservationError("observation snapshot differs from its bound source")
    return disposition


def validate_external_record(value: Any, admission: Mapping[str, Any],
                             reservation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Revalidate one committed external sample against its exact admission."""

    from control_plane.coo_observation import _EXTERNAL_RECORD_KEYS

    record = _closed(value, set(_EXTERNAL_RECORD_KEYS), "external observation record")
    expected = {key: admission[key] for key in
                ("root_job_id", "plan_attempt_id", "plan_digest", "plan_step_id", "gate_digest")}
    if any(record[key] != item for key, item in expected.items()):
        raise ObservationError("external observation record binding drifted")
    if record["schema_version"] != "mastermind.coo_observation_record/v2":
        raise ObservationError("external observation record schema drifted")
    _integer(record["sample_index"], minimum=1)
    started = _integer(record["started_at_ms"])
    finished = _integer(record["finished_at_ms"])
    if finished < started:
        raise ObservationError("external observation record clock drifted")
    reservation_id = record["reservation_command_id"]
    if type(reservation_id) is not str or not reservation_id:
        raise ObservationError("external observation record reservation is invalid")
    _integer(record["api_calls"])
    _integer(record["response_bytes"])
    snapshot = record["snapshot"]
    if type(snapshot) is not dict:
        raise ObservationError("external observation snapshot is not the closed wire")
    if record["snapshot_digest"] != digest(snapshot, max_bytes=MAX_EXTERNAL_INPUT_BYTES):
        raise ObservationError("external observation snapshot digest drifted")
    disposition = record["disposition"]
    if disposition not in DISPOSITIONS:
        raise ObservationError("external observation disposition is invalid")
    if disposition_for_snapshot(admission["spec"]["source"], snapshot) != disposition:
        raise ObservationError("external observation disposition drifted")
    previous = record["previous_snapshot_digest"]
    if previous is not None and _DIGEST_RE.fullmatch(str(previous)) is None:
        raise ObservationError("external observation previous digest is invalid")
    material = dict(record)
    evidence = material.pop("evidence_digest")
    if evidence != digest(material, max_bytes=MAX_EXTERNAL_INPUT_BYTES):
        raise ObservationError("external observation evidence digest drifted")
    if reservation is not None:
        from control_plane import coo_observation as owner
        reserved = owner.validate_reservation(dict(reservation), admission)
        if (record["sample_index"] != reserved["sample_index"]
                or record["reservation_command_id"] != owner.reservation_command_id(
                    admission, reserved["sample_index"])
                or record["started_at_ms"] != reserved["reserved_at_ms"]
                or record["api_calls"] > reserved["reserved_api_calls"]
                or record["response_bytes"] > reserved["reserved_response_bytes"]):
            raise ObservationError("external observation escaped its exact reservation")
        if disposition == "MATERIAL" and finished >= min(
                reserved["deadline_at_ms"],
                reserved["reserved_at_ms"] + reserved["sample_timeout_ms"]):
            raise ObservationError("late external observation cannot be material")
    return record


def source_digest(source: Mapping[str, Any]) -> str:
    return digest({"kind": source["kind"], "source": source})


@dataclass(frozen=True)
class ExternalObservationHost:
    """Trusted private capability plus one bounded single-sample reader.

    The reader is supplied by host composition.  It is never built from plan
    input, a caller string, a hash, a timestamp or a Python type.
    """

    binding_ref: str
    reader: Callable[..., Mapping[str, Any]]
    services: frozenset[str]
    max_horizon_ms: int = MAX_HORIZON_MS

    def __post_init__(self) -> None:
        if not isinstance(self.binding_ref, str) or _ID_RE.match(self.binding_ref) is None:
            raise ObservationError("external host binding is invalid")
        if not callable(self.reader):
            raise ObservationError("external host reader is not callable")
        if not isinstance(self.services, frozenset):
            raise ObservationError("external host service allowlist is invalid")
        _integer(self.max_horizon_ms, minimum=1, maximum=MAX_HORIZON_MS)

    def require_scope(self, *, root_job_id: str, source: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(root_job_id, str) or _ID_RE.match(root_job_id) is None:
            raise ObservationError("external root is invalid")
        source = validate_external_source(source)
        if source["kind"] == "service_health" and source["service"] not in self.services:
            raise ObservationError("service health identifier is not in the incumbent allowlist")
        return {
            "source_binding_ref": self.binding_ref,
            "source_binding_digest": digest({
                "root_job_id": root_job_id,
                "binding_ref": self.binding_ref,
                "source": source,
                "services": sorted(self.services),
                "max_horizon_ms": self.max_horizon_ms,
            }),
            "max_horizon_ms": self.max_horizon_ms,
        }

    def require_current(self, *, admission: Mapping[str, Any]) -> None:
        scope = self.require_scope(
            root_job_id=admission["root_job_id"],
            source=admission["spec"]["source"],
        )
        if any(admission.get(key) != scope[key] for key in
               ("source_binding_ref", "source_binding_digest")):
            raise ObservationError("external host binding changed")

    def read_sample(
        self, source: Mapping[str, Any], *,
        timeout_ms: int, max_api_calls: int, max_response_bytes: int,
    ) -> Mapping[str, Any]:
        """Perform exactly one bounded sample.  No loop, no retry, no write."""

        return self.reader(
            source,
            timeout_ms=timeout_ms,
            max_api_calls=max_api_calls,
            max_response_bytes=max_response_bytes,
        )


@dataclass(frozen=True)
class ComposedObservationHost:
    """The incumbent timer host plus an optional external capability.

    The timer keeps its published meaning; the external source is admitted only
    by the trusted external binding.
    """

    timer: Any
    external: ExternalObservationHost

    def require_scope(self, *, root_job_id: str, source: Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(source, Mapping) and source.get("kind") in EXTERNAL_SOURCE_KINDS:
            return self.external.require_scope(root_job_id=root_job_id, source=source)
        return self.timer.require_scope(root_job_id=root_job_id, source=source)

    def require_current(self, *, admission: Mapping[str, Any]) -> None:
        source = admission["spec"]["source"]
        if isinstance(source, Mapping) and source.get("kind") in EXTERNAL_SOURCE_KINDS:
            self.external.require_current(admission=admission)
            return
        self.timer.require_current(admission=admission)

    def read_sample(self, source: Mapping[str, Any], **budget: Any) -> Mapping[str, Any]:
        """The external reader seam.  A timer never reaches this path."""

        if not isinstance(source, Mapping) or source.get("kind") not in EXTERNAL_SOURCE_KINDS:
            raise ExternalSourceError("EXTERNAL_SOURCE_INVALID")
        return self.external.read_sample(source, **budget)


def default_external_reader() -> Callable[..., Mapping[str, Any]]:
    """The incumbent bounded readers: GET-only GitHub and the read-only probe."""

    from ops.fabric_launch import finite_watch

    return finite_watch.read_external_sample


def incumbent_services() -> frozenset[str]:
    """The incumbent closed service allowlist."""

    from ops.fabric_launch import observe

    return frozenset(observe.ENDPOINTS)


__all__ = [
    "DISPOSITIONS",
    "EXTERNAL_GATE_SCHEMA",
    "EXTERNAL_SOURCE_KINDS",
    "ComposedObservationHost",
    "ExternalObservationHost",
    "ExternalSourceError",
    "default_external_reader",
    "disposition_for_snapshot",
    "evaluate_sample",
    "external_gate_schema",
    "incumbent_services",
    "per_sample_api_calls",
    "per_sample_response_bytes",
    "source_digest",
    "validate_external_record",
    "validate_external_source",
    "validate_external_spec",
]
