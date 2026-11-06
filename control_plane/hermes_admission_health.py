"""H24-08: ephemeral, non-authorizing composition of acquired owner evidence.

No acquisition, clock read, reservation, retry, registry, or lifecycle effect.
The trusted caller supplies current bindings and authenticated owner reads; a
matching digest or ``source_verified`` flag is NOT authentication. This module
must never be exposed as a model-authored admission or provider-health endpoint.
Native provider V2 currently supports MiniMax only. Other schemas fail closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

from control_plane import native_capacity_v2 as capacity
from control_plane.executive_capacity_observation import (
    CapacityObservationError, validate_worker_capacity_observation,
)
from control_plane.executive_capacity_observation_producer import (
    validate_worker_capacity_source_config, worker_capacity_source_config_digest,
)
from control_plane.executive_host_capacity import (
    HostCapacityContractError, project_native_host_capacity,
)
from control_plane.remote_worker_transport import TransportEffect, validate_broker_operation


SCHEMA = "mastermind.hermes_admission_health/v1"
OWNERS = {
    "host": "executive_host_capacity",
    "worker_capacity": "worker_capacity_observer",
    "provider": "native_capacity_acquisition",
    "runtime": "executive_runtime",
    "slot": "slot",
    "transport": "remote_worker_transport",
}
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")
_MAX_INT = (1 << 63) - 1
_MAX_BYTES = 131_072
_STAMP = frozenset({"owner", "source_verified", "reader_generation",
                    "observed_at_ms", "observed_monotonic_ms", "expires_at_ms", "value"})
_EXPECTED = frozenset({
    "root_job_id", "job_id", "worker_id", "quota_class", "provider",
    "host_binding", "capacity_join", "worker_source_config", "provider_source",
    "producer_sha256", "realm_generation", "enrollment_receipt_digest",
    "slot_id", "lane_id", "credential_scope_sha256", "process_generation",
    "process_identity_sha256", "quota_fence_generation", "original_attempt_id",
    "original_broker_operation", "original_request_sha256",
})
_WORKER_STATES = frozenset({"AVAILABLE", "BUSY", "DRAINING", "RATE_LIMITED", "OFFLINE", "ERROR"})
_JOB_STATES = frozenset({"QUEUED", "RUNNING", "CHECKPOINTED", "RATE_LIMITED", "FAILED",
                         "LOST", "CANCEL_REQUESTED", "COMPLETED", "CANCELLED"})
_ATTEMPT_STATES = (_JOB_STATES - {"QUEUED"}) | {"CLAIMED"}


class HealthInputError(ValueError):
    """Closed input error; never includes supplied values or credential paths."""


def _require(condition, code="INPUT_INVALID"):
    if not condition:
        raise HealthInputError(code)


def _integer(value, minimum=0, maximum=_MAX_INT):
    _require(type(value) is int and minimum <= value <= maximum)
    return value


def _token(value, nullable=False):
    _require(nullable and value is None or type(value) is str and _TOKEN.fullmatch(value) is not None)


def _closed(value, keys):
    _require(type(value) is dict and set(value) == set(keys))
    return value


def _enum(value, choices):
    _require(type(value) is str and value in choices)


def _utc_ms(value):
    _require(type(value) is str and len(value) <= 32)
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(stamp.utcoffset() == timezone.utc.utcoffset(stamp))
        return _integer(int(stamp.timestamp() * 1000), 1)
    except (ValueError, OverflowError, OSError):
        raise HealthInputError("INPUT_INVALID") from None


def _detach(value):
    # Bound plain JSON before copying. Reject custom mappings, floats, recursion,
    # and excessive depth; validators never execute caller-provided methods.
    budget = [0]

    def visit(item, depth):
        _require(depth <= 12)
        budget[0] += 1
        _require(budget[0] <= 8192)
        if type(item) is dict:
            _require(all(type(k) is str and len(k) <= 128 for k in item))
            for child in item.values():
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) is str:
            _require(len(item) <= 4096)
        else:
            _require(item is None or type(item) is bool or type(item) is int)
            if type(item) is int:
                _integer(item)

    visit(value, 0)
    wire = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    _require(len(wire.encode()) <= _MAX_BYTES)
    return json.loads(wire)


@dataclass(frozen=True)
class HealthPolicy:
    """Explicit owner-supplied policy; no production thresholds are invented."""

    max_age_ms: int
    min_cpu_capacity_millicores: int
    min_memory_headroom_bytes: int
    min_disk_usable_bytes: int
    max_cpu_busy_milli_pct: int
    max_cpu_pressure_milli_pct: int
    max_memory_pressure_milli_pct: int
    max_io_pressure_milli_pct: int

    def __post_init__(self):
        _integer(self.max_age_ms, 1, 15_000)
        for value in (self.min_cpu_capacity_millicores, self.min_memory_headroom_bytes,
                      self.min_disk_usable_bytes):
            _integer(value, 1)
        for value in (self.max_cpu_busy_milli_pct, self.max_cpu_pressure_milli_pct,
                      self.max_memory_pressure_milli_pct, self.max_io_pressure_milli_pct):
            _integer(value, 0, 100_000)


@dataclass(frozen=True)
class BlockingReason:
    source: str
    code: str


@dataclass(frozen=True)
class HealthDecision:
    status: str
    eligible: bool
    recovery_action: str
    expires_at_ms: int
    expires_monotonic_ms: int
    original_attempt_id: str | None
    original_request_sha256: str | None
    blocking_reasons: tuple[BlockingReason, ...]
    source_states: tuple[tuple[str, str], ...]
    evidence_sha256: tuple[tuple[str, str], ...]

    def to_dict(self):
        return {
            "schema": SCHEMA, "status": self.status, "eligible": self.eligible,
            "recovery_action": self.recovery_action,
            "expires_at_ms": self.expires_at_ms,
            "expires_monotonic_ms": self.expires_monotonic_ms,
            "original_attempt_id": self.original_attempt_id,
            "original_request_sha256": self.original_request_sha256,
            "blocking_reasons": [{"source": r.source, "code": r.code} for r in self.blocking_reasons],
            "source_states": dict(self.source_states), "evidence_sha256": dict(self.evidence_sha256),
            "admitted": False, "reserved": False, "worker_started": False,
            "retry_authorized": False, "requires_owner_reservation": True,
        }


def _binding(expected):
    e = _closed(expected, _EXPECTED)
    for key in ("root_job_id", "job_id", "worker_id", "quota_class", "provider",
                "slot_id", "lane_id", "process_generation"):
        _token(e[key])
    _token(e["original_attempt_id"], nullable=True)
    if e["original_broker_operation"] is not None:
        validate_broker_operation(e["original_broker_operation"])
    if e["original_request_sha256"] is not None:
        capacity.reference(e["original_request_sha256"])
    _require((e["original_broker_operation"] is None) == (e["original_request_sha256"] is None))
    for key in ("producer_sha256", "enrollment_receipt_digest",
                "credential_scope_sha256", "process_identity_sha256"):
        _require(type(e[key]) is str and _SHA.fullmatch(e[key]) is not None)
    _integer(e["realm_generation"], 1)
    _integer(e["quota_fence_generation"])
    join = capacity.validate_join(e["capacity_join"])
    host = _closed(e["host_binding"], {"host_ref", "boot_ref", "capacity_pool_ref",
        "source_generation_sha256", "execution_scope_sha256", "namespace_sha256", "ancestry_sha256"})
    for key, prefix in (("host_ref", "host-"), ("boot_ref", "boot-"),
                        ("capacity_pool_ref", "capacity-pool-")):
        capacity.reference(host[key], prefix)
    for key in ("source_generation_sha256", "execution_scope_sha256", "namespace_sha256", "ancestry_sha256"):
        capacity.reference(host[key])
    _require(join["host_ref"] == host["host_ref"], "BINDING_MISMATCH")
    config = validate_worker_capacity_source_config(e["worker_source_config"])
    _require(config.host_ref == host["host_ref"] and
             config.capacity_capability_id == join["capacity_capability_id"] and
             worker_capacity_source_config_digest(config) == join["worker_source_config_digest"],
             "SOURCE_CONFIG_MISMATCH")
    source = _closed(e["provider_source"], capacity.SOURCE)
    for key, value in source.items():
        pattern = r"[0-9a-f]{40}" if key.endswith("commit") else r"[0-9a-f]{64}"
        _require(type(value) is str and re.fullmatch(pattern, value) is not None)
    return e


class _Composition:
    def __init__(self, expected, now, mono, generation, policy):
        self.e, self.now, self.mono = expected, now, mono
        self.generation, self.policy = generation, policy
        self.reasons = []
        self.states = {}
        self.digests = {}
        self.expiry = now + policy.max_age_ms
        self.mono_expiry = mono + policy.max_age_ms
        self.reconcile = expected["original_attempt_id"] is not None or expected["original_request_sha256"] is not None
        self.original = expected["original_attempt_id"]
        self.original_request = expected["original_request_sha256"]
        self.hard_block = False

    def block(self, source, code, *, partial=False):
        _require(type(code) is str and _CODE.fullmatch(code) is not None)
        reason = BlockingReason(source, code)
        if reason not in self.reasons:
            self.reasons.append(reason)
        if partial:
            if self.states.get(source) != "UNAVAILABLE":
                self.states[source] = "PARTIAL"
        else:
            self.hard_block = True

    def fresh(self, source, observed, expiry=None):
        _integer(observed, 1)
        end = observed + self.policy.max_age_ms if expiry is None else min(
            observed + self.policy.max_age_ms, _integer(expiry, 1))
        self.expiry = min(self.expiry, end)
        if observed > self.now or self.now >= end:
            self.block(source, "OBSERVATION_EXPIRED_OR_FUTURE", partial=True)

    def acquire(self, source, envelope):
        if envelope is None:
            self.states[source] = "UNAVAILABLE"
            self.block(source, "SOURCE_MISSING", partial=True)
            return None
        env = _closed(envelope, _STAMP)
        _require(env["owner"] == OWNERS[source], "SOURCE_OWNER_MISMATCH")
        _require(type(env["source_verified"]) is bool)
        if not env["source_verified"]:
            raise HealthInputError("SOURCE_UNVERIFIED")
        _token(env["reader_generation"])
        if env["reader_generation"] != self.generation:
            raise HealthInputError("READER_GENERATION_CHANGED")
        wall = _integer(env["observed_at_ms"], 1)
        mono = _integer(env["observed_monotonic_ms"])
        end = _integer(env["expires_at_ms"], wall + 1, wall + self.policy.max_age_ms)
        if mono > self.mono or wall > self.now or abs((self.now - wall) - (self.mono - mono)) > 2000:
            raise HealthInputError("MONOTONIC_CLOCK_MISMATCH")
        self.states[source] = "COMPLETE"
        self.fresh(source, wall, end)
        self.mono_expiry = min(self.mono_expiry, mono + end - wall)
        if self.mono >= mono + end - wall:
            self.block(source, "MONOTONIC_OBSERVATION_EXPIRED", partial=True)
        self.digests[source] = hashlib.sha256(json.dumps(env, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        return env["value"]

    def host(self, value):
        view = project_native_host_capacity(value, expected_binding=self.e["host_binding"],
            now_ms=self.now, max_age_ms=self.policy.max_age_ms)
        self.fresh("host", view["observed_at_ms"] - view["total_observation_window_ms"])
        if view["telemetry_status"] != "COMPLETE":
            self.block("host", "HOST_METRICS_PARTIAL", partial=True)
        metrics = view["metrics"]
        checks = (
            ("effective_cpu_capacity_millicores", self.policy.min_cpu_capacity_millicores, False, "CPU_CAPACITY_LOW"),
            ("effective_memory_headroom_estimate_bytes", self.policy.min_memory_headroom_bytes, False, "MEMORY_HEADROOM_LOW"),
            ("disk_usable_bytes", self.policy.min_disk_usable_bytes, False, "DISK_HEADROOM_LOW"),
            ("host_cpu_busy_milli_pct", self.policy.max_cpu_busy_milli_pct, True, "CPU_PRESSURE"),
            ("cpu_some_avg10", self.policy.max_cpu_pressure_milli_pct, True, "CPU_PRESSURE"),
            ("memory_some_avg10", self.policy.max_memory_pressure_milli_pct, True, "MEMORY_PRESSURE"),
            ("memory_full_avg10", self.policy.max_memory_pressure_milli_pct, True, "MEMORY_PRESSURE"),
            ("io_some_avg10", self.policy.max_io_pressure_milli_pct, True, "IO_PRESSURE"),
            ("io_full_avg10", self.policy.max_io_pressure_milli_pct, True, "IO_PRESSURE"),
        )
        for name, threshold, maximum, code in checks:
            number = metrics[name]["value"]
            if number is not None and (number > threshold if maximum else number < threshold):
                self.block("host", code)

    def worker_capacity(self, value):
        join = self.e["capacity_join"]
        observation = validate_worker_capacity_observation(value,
            expected_host_ref=join["host_ref"],
            expected_capacity_capability_id=join["capacity_capability_id"],
            expected_source_config_digest=join["worker_source_config_digest"],
            trusted_current_ms=self.now)
        self.fresh("worker_capacity", _utc_ms(observation.observed_at), _utc_ms(observation.expires_at))

    def provider(self, value):
        snapshot = capacity.validate_snapshot(value, now_ms=self.now)
        _require(snapshot["source"] == self.e["provider_source"] and
                 snapshot["producer_sha256"] == self.e["producer_sha256"], "CAPACITY_SOURCE_MISMATCH")
        join = self.e["capacity_join"]
        rows = [r for r in snapshot["slots"] if all(r[k] == join[k] for k in (
            "host_ref", "capacity_capability_id", "capability_generation", "worker_source_config_digest"))]
        _require(len(rows) == 1, "CAPACITY_JOIN_MISMATCH")
        row = rows[0]
        _require(row["boot_ref"] == self.e["host_binding"]["boot_ref"], "HOST_BOOT_CHANGED")
        _require(row["provider"] == self.e["provider"] and
                 row["realm_generation"] == self.e["realm_generation"] and
                 row["enrollment_receipt_digest"] == self.e["enrollment_receipt_digest"],
                 "PROVIDER_REALM_MISMATCH")
        self.fresh("provider", snapshot["generated_at_ms"])
        self.fresh("provider", capacity.timestamp(row["observed_at"]))
        for fact in (row["provider_health"], row["cooling"], row["last_provider_outcome"], *row["quota_horizons"]):
            if fact["observed_at"] is not None:
                self.fresh("provider", capacity.timestamp(fact["observed_at"]))
        for horizon in row["quota_horizons"]:
            self.expiry = min(self.expiry, capacity.timestamp(horizon["reset_at"]))
        if row["cooling"]["active"] is True:
            self.block("provider", "PROVIDER_COOLING")
        if any(q["remaining"] == 0 for q in row["quota_horizons"]):
            self.block("provider", "PROVIDER_QUOTA_EXHAUSTED")
        try:
            capacity.known_admissible(snapshot, join, now_ms=self.now)
        except capacity.NativeCapacityRefusal as exc:
            code = str(exc)
            # Classify the fact that actually failed. An unknown quota must
            # never soften a known disabled/unhealthy provider into uncertainty.
            partial = {
                "V2_PROVIDER_ENABLEMENT_UNQUALIFIED": row["provider_enabled"] is None,
                "V2_AUTH_UNQUALIFIED": row["realm_auth"]["state"] != "unauthenticated",
                "V2_HEALTH_UNQUALIFIED": (row["provider_health"]["state"] != "unhealthy" and
                                          row["provider_health"]["error_class"] is None),
                "V2_COOLING_UNQUALIFIED": row["cooling"]["active"] is not True,
                "V2_QUOTA_UNQUALIFIED": not row["quota_horizons"],
            }.get(code, False)
            self.block("provider", code, partial=partial)

    def runtime(self, value):
        value = _closed(value, {"root", "job", "worker", "quota", "attempt"})
        e = self.e
        for key in ("root", "job"):
            row = value[key]
            if row is None:
                self.block("runtime", "ROOT_MISSING" if key == "root" else "JOB_MISSING")
                continue
            _closed(row, {"job_id", "root_job_id", "status", "current_attempt_id"})
            _require(row["job_id"] == e["root_job_id" if key == "root" else "job_id"] and
                     row["root_job_id"] == e["root_job_id"], "ROOT_OR_JOB_IDENTITY_MISMATCH")
            _enum(row["status"], _JOB_STATES)
            _token(row["current_attempt_id"], nullable=True)
            if row["status"] not in {"QUEUED", "RUNNING", "CHECKPOINTED"}:
                self.block("runtime", "ROOT_OR_JOB_NOT_ACTIVE")
            if key == "job" and row["status"] != "QUEUED":
                # Missing current_attempt_id on a running/lost/finished Job is
                # a reconciliation gap, never evidence of a fresh request.
                self.reconcile = True
                self.block("runtime", "JOB_NOT_UNATTEMPTED")
            if key == "job" and row["current_attempt_id"] is not None:
                self.reconcile = True
                self.original = self.original or row["current_attempt_id"]
                self.block("runtime", "ORIGINAL_ATTEMPT_PRESENT")
            if key == "job" and row["current_attempt_id"] != e["original_attempt_id"]:
                self.block("runtime", "ATTEMPT_IDENTITY_MISMATCH")
        for key in ("worker", "quota"):
            row = value[key]
            if row is None:
                self.block("runtime", "WORKER_MISSING" if key == "worker" else "QUOTA_MISSING", partial=True)
                continue
            fields = {"worker_id", "provider", "status", "last_seen_at", "active_job_id"}
            if key == "quota":
                fields |= {"quota_class", "active_attempt_id", "fence_generation", "capacity_join"}
            _closed(row, fields)
            _require(row["worker_id"] == e["worker_id"] and row["provider"] == e["provider"],
                     "WORKER_IDENTITY_MISMATCH")
            _enum(row["status"], _WORKER_STATES)
            _token(row["active_job_id"], nullable=True)
            self.fresh("runtime", _utc_ms(row["last_seen_at"]))
            if row["status"] != "AVAILABLE":
                self.block("runtime", "WORKER_NOT_AVAILABLE" if key == "worker" else "QUOTA_NOT_AVAILABLE")
            if row["active_job_id"] is not None:
                self.block("runtime", "WORKER_OCCUPIED")
            if key == "quota":
                _require(row["quota_class"] == e["quota_class"] and
                         _integer(row["fence_generation"]) == e["quota_fence_generation"] and
                         capacity.validate_join(row["capacity_join"]) == e["capacity_join"], "QUOTA_BINDING_MISMATCH")
                _token(row["active_attempt_id"], nullable=True)
                if row["active_attempt_id"] is not None:
                    self.block("runtime", "QUOTA_OCCUPIED")
                    if row["active_job_id"] == e["job_id"]:
                        self.reconcile = True
                        self.original = self.original or row["active_attempt_id"]
        attempt = value["attempt"]
        if attempt is not None:
            _closed(attempt, {"attempt_id", "job_id", "worker_id", "quota_class", "status", "fence_generation"})
            self.reconcile = True
            _token(attempt["attempt_id"])
            self.original = self.original or attempt["attempt_id"]
            _require(attempt["job_id"] == e["job_id"] and attempt["worker_id"] == e["worker_id"] and
                     attempt["quota_class"] == e["quota_class"] and
                     attempt["attempt_id"] == e["original_attempt_id"] and
                     _integer(attempt["fence_generation"]) == e["quota_fence_generation"], "ATTEMPT_IDENTITY_MISMATCH")
            _enum(attempt["status"], _ATTEMPT_STATES)
            self.block("runtime", "ORIGINAL_ATTEMPT_PRESENT")
        elif e["original_attempt_id"] is not None:
            self.block("runtime", "ORIGINAL_ATTEMPT_MISSING")

    def slot(self, value):
        fields = {"slot_id", "lane_id", "worker_id", "provider", "host_ref", "boot_ref",
                  "credential_scope_sha256", "process_generation", "process_identity_sha256",
                  "process_alive", "state", "owner_attempt_id", "host_occupied", "available_count"}
        row = _closed(value, fields)
        for key in ("slot_id", "lane_id", "worker_id", "provider", "credential_scope_sha256",
                    "process_generation", "process_identity_sha256"):
            _require(row[key] == self.e[key], "SLOT_IDENTITY_MISMATCH")
        for key in ("host_ref", "boot_ref"):
            _require(row[key] == self.e["host_binding"][key], "SLOT_HOST_BOOT_MISMATCH")
        _enum(row["state"], {"free", "held", "rented", "lost", "unknown"})
        _token(row["owner_attempt_id"], nullable=True)
        for key in ("process_alive", "host_occupied"):
            _require(row[key] is None or type(row[key]) is bool)
            if row[key] is None:
                self.block("slot", "LANE_HEALTH_UNKNOWN", partial=True)
        if row["process_alive"] is False:
            self.block("slot", "WORKER_PROCESS_DEAD")
        if row["host_occupied"] is True:
            self.block("slot", "HOST_OCCUPIED")
        if row["state"] != "free" or row["owner_attempt_id"] is not None:
            self.block("slot", "SLOT_NOT_FREE", partial=row["state"] == "unknown")
        if row["available_count"] is None:
            self.block("slot", "AVAILABLE_COUNT_UNKNOWN", partial=True)
        elif _integer(row["available_count"]) == 0:
            self.block("slot", "NO_AVAILABLE_CAPACITY")

    def transport(self, value):
        row = _closed(value, {"host_ref", "worker_id", "job_id", "attempt_id", "phase", "outcome", "effect",
                              "broker_operation", "request_sha256"})
        _require(row["host_ref"] == self.e["host_binding"]["host_ref"] and
                 row["worker_id"] == self.e["worker_id"] and row["job_id"] == self.e["job_id"],
                 "TRANSPORT_IDENTITY_MISMATCH")
        _token(row["attempt_id"], nullable=True)
        if row["broker_operation"] is not None:
            validate_broker_operation(row["broker_operation"])
        if row["request_sha256"] is not None:
            capacity.reference(row["request_sha256"])
        _require((row["broker_operation"] is None) == (row["request_sha256"] is None))
        _enum(row["phase"], {"PRE_SUBMIT", "SUBMITTED", "CONTROLLER_CREATED", "WORKER_STARTED", "UNKNOWN"})
        _enum(row["outcome"], {"ready", "ok", "refused", "error", "unavailable", "unknown"})
        if row["effect"] is not None:
            _enum(row["effect"], {TransportEffect.NO_EFFECT.value, TransportEffect.EFFECT_UNKNOWN.value})
        if (row["phase"] != "PRE_SUBMIT" or row["effect"] != TransportEffect.NO_EFFECT.value or
                row["attempt_id"] is not None or row["request_sha256"] is not None):
            self.reconcile = True
            self.original = self.original or row["attempt_id"]
            self.original_request = self.original_request or row["request_sha256"]
            self.block("transport", "ORIGINAL_TRANSPORT_RECONCILE")
        if row["effect"] == TransportEffect.EFFECT_UNKNOWN.value:
            self.block("transport", "TRANSPORT_EFFECT_UNKNOWN")
        if row["attempt_id"] != self.e["original_attempt_id"]:
            self.block("transport", "ATTEMPT_IDENTITY_MISMATCH")
        if (row["broker_operation"] != self.e["original_broker_operation"] or
                row["request_sha256"] != self.e["original_request_sha256"]):
            self.block("transport", "TRANSPORT_REQUEST_IDENTITY_MISMATCH")
        if row["outcome"] != "ready":
            self.block("transport", "TRANSPORT_NOT_READY", partial=row["outcome"] in {"unknown", "unavailable"})

    def result(self):
        if self.reconcile and not any(r.code.startswith("ORIGINAL_") for r in self.reasons):
            self.block("runtime", "ORIGINAL_ATTEMPT_RECONCILE")
        eligible = not self.reasons
        status = ("READY" if eligible else "BLOCKED" if self.hard_block else
                  "UNAVAILABLE" if all(s == "UNAVAILABLE" for s in self.states.values()) else "PARTIAL")
        recovery = ("ORIGINAL_RECONCILE" if self.reconcile else "NEW_CANDIDATE_ELIGIBLE" if eligible else
                    "NO_ELIGIBLE_CANDIDATE" if self.hard_block else "OWNER_EVIDENCE_REQUIRED")
        # A UTC deadline also shortens the same-reader monotonic deadline.
        expiry = max(0, min(self.expiry, self.now) if not eligible else self.expiry)
        mono_expiry = max(0, min(self.mono_expiry, self.mono + expiry - self.now))
        return HealthDecision(status, eligible, recovery, expiry, mono_expiry, self.original, self.original_request,
            tuple(sorted(self.reasons, key=lambda r: (r.source, r.code))),
            tuple(sorted(self.states.items())), tuple(sorted(self.digests.items())))


def compose_admission_health(*, expected, observations, now_ms, now_monotonic_ms,
                             reader_generation, policy):
    """Evaluate one candidate from injected owner reads; never reserve or START.

    Stamps use the acquiring reader's clock and process generation, never a
    comparison of monotonic clocks on different hosts. Original source times
    are checked separately, so rewrapping an old observation cannot freshen it.
    Slot/Runtime fragments are explicit projections documented in H24's policy
    table, not new persistent records or replacements for transactional owners.
    """
    _integer(now_ms, 1, _MAX_INT - 30_000)
    _integer(now_monotonic_ms, 0, _MAX_INT - 30_000)
    _token(reader_generation)
    _require(type(policy) is HealthPolicy)
    try:
        e = _binding(_detach(expected))
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        known = isinstance(exc, (HealthInputError, CapacityObservationError, capacity.NativeCapacityRefusal))
        code = str(exc) if known and _CODE.fullmatch(str(exc)) else "BINDING_INVALID"
        original = expected.get("original_attempt_id") if type(expected) is dict else None
        original = original if type(original) is str and _TOKEN.fullmatch(original) else None
        request = expected.get("original_request_sha256") if type(expected) is dict else None
        request = request if type(request) is str and _SHA.fullmatch(request) else None
        return HealthDecision("UNAVAILABLE", False,
            "ORIGINAL_RECONCILE" if original or request else "OWNER_EVIDENCE_REQUIRED", now_ms,
            now_monotonic_ms, original, request, (BlockingReason("binding", code),), (), ())
    result = _Composition(e, now_ms, now_monotonic_ms, reader_generation, policy)
    try:
        supplied = _closed(_detach(observations), OWNERS)
    except HealthInputError:
        result.states = {key: "UNAVAILABLE" for key in OWNERS}
        result.block("binding", "OBSERVATIONS_INVALID", partial=True)
        return result.result()
    for source in OWNERS:
        try:
            value = result.acquire(source, supplied[source])
            if value is not None:
                getattr(result, source)(value)
            elif supplied[source] is not None:
                raise HealthInputError("SOURCE_VALUE_MISSING")
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            # Some incumbent validators raise builtin errors for wrong-type
            # nested values. Preserve refusal without projecting raw messages.
            known = isinstance(exc, (HealthInputError, HostCapacityContractError,
                                     CapacityObservationError, capacity.NativeCapacityRefusal))
            code = str(exc) if known and _CODE.fullmatch(str(exc)) else "OWNER_VALIDATION_REFUSED"
            result.states[source] = "UNAVAILABLE"
            result.block(source, code, partial=True)
    return result.result()


__all__ = ["HealthPolicy", "HealthDecision", "BlockingReason", "HealthInputError",
           "compose_admission_health"]
