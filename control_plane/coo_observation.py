"""Closed timer evidence for the existing Runtime/COO owner.

No loop, store, transport, worker selection or authority is created here. The
service supplies a trusted host; its scope data and hashes are not authentication.
Only timers are qualified. External readers require a separately reviewed source
contract and bounded acquisition implementation before they can be admitted.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


GATE_SCHEMA = "mastermind.coo_observation_gate/v1"
ADMISSION_SCHEMA = "mastermind.coo_observation_admission/v1"
RECORD_SCHEMA = "mastermind.coo_observation_record/v1"
INPUT_SCHEMA = "mastermind.coo_observation_input/v1"
EVENT_TYPE = "COO_OBSERVATION_RECORDED"
MAX_HORIZON_MS = 7 * 24 * 60 * 60 * 1000
MAX_INPUT_BYTES = 16_384
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SPEC_KEYS = {"schema_version", "source", "deadline_at_ms", "max_samples",
              "min_interval_ms", "sample_timeout_ms", "max_api_calls", "max_response_bytes"}
_ADMISSION_KEYS = {"schema_version", "root_job_id", "plan_attempt_id", "plan_digest",
                   "plan_step_id", "root_creation_event_id", "authority_policy_hash",
                   "source_binding_ref", "source_binding_digest", "admitted_at_ms",
                   "effective_deadline_at_ms", "spec", "gate_digest"}
_RECORD_KEYS = {"schema_version", "root_job_id", "plan_attempt_id", "plan_digest",
                "plan_step_id", "gate_digest", "sample_index", "reservation_command_id",
                "started_at_ms", "finished_at_ms", "disposition", "previous_snapshot_digest",
                "snapshot", "snapshot_digest", "evidence_digest"}


class ObservationError(ValueError):
    """A timer wire, binding or bounded observation is invalid."""


def canonical_bytes(value: Any) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ObservationError("observation is not bounded canonical JSON") from exc
    if len(raw) > MAX_INPUT_BYTES:
        raise ObservationError("observation exceeds the canonical byte budget")
    return raw


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _closed(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ObservationError(f"{name} is not the closed wire")
    canonical_bytes(value)
    return copy.deepcopy(value)


def _integer(value: Any, *, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ObservationError("observation integer is out of bounds")
    return value


def gate_schema() -> dict[str, Any]:
    integer = {"type": "integer", "minimum": 0, "maximum": 2**63 - 1}
    return {"type": "object", "additionalProperties": False,
            "required": sorted(_SPEC_KEYS), "properties": {
                "schema_version": {"const": GATE_SCHEMA},
                "source": {"type": "object", "additionalProperties": False,
                           "required": ["kind", "due_at_ms"], "properties": {
                               "kind": {"const": "timer"}, "due_at_ms": integer}},
                "deadline_at_ms": integer, "max_samples": {"const": 1},
                **{key: {"const": 0} for key in (
                    "min_interval_ms", "sample_timeout_ms", "max_api_calls", "max_response_bytes")}}}


def validate_spec(value: Any) -> dict[str, Any]:
    spec = _closed(value, _SPEC_KEYS, "observation gate")
    source = _closed(spec["source"], {"kind", "due_at_ms"}, "timer source")
    if spec["schema_version"] != GATE_SCHEMA or source["kind"] != "timer":
        raise ObservationError("observation source is not qualified")
    due = _integer(source["due_at_ms"])
    if due >= _integer(spec["deadline_at_ms"], minimum=1):
        raise ObservationError("timer must be due before its acquisition deadline")
    for key, expected in (("max_samples", 1), ("min_interval_ms", 0),
                          ("sample_timeout_ms", 0), ("max_api_calls", 0),
                          ("max_response_bytes", 0)):
        if _integer(spec[key]) != expected:
            raise ObservationError("timer budgets must be one sample and zero I/O")
    return spec


class ObservationHost(Protocol):
    """Trusted private service composition; never constructed from plan input."""

    def require_scope(self, *, root_job_id: str, source: Mapping[str, Any]) -> dict[str, Any]: ...

    def require_current(self, *, admission: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True)
class TimerObservationHost:
    """A stable service binding, not a new grant or authentication token."""

    binding_ref: str
    max_horizon_ms: int = MAX_HORIZON_MS

    def __post_init__(self) -> None:
        if not isinstance(self.binding_ref, str) or _ID.fullmatch(self.binding_ref) is None:
            raise ObservationError("timer host binding is invalid")
        _integer(self.max_horizon_ms, minimum=1, maximum=MAX_HORIZON_MS)

    def require_scope(self, *, root_job_id: str, source: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(root_job_id, str) or _ID.fullmatch(root_job_id) is None:
            raise ObservationError("timer root is invalid")
        source = _closed(source, {"kind", "due_at_ms"}, "timer source")
        if source["kind"] != "timer":
            raise ObservationError("external observation source is not composed")
        _integer(source["due_at_ms"])
        return {"source_binding_ref": self.binding_ref,
                "source_binding_digest": digest({"root_job_id": root_job_id,
                    "binding_ref": self.binding_ref, "source": source,
                    "max_horizon_ms": self.max_horizon_ms}),
                "max_horizon_ms": self.max_horizon_ms}

    def require_current(self, *, admission: Mapping[str, Any]) -> None:
        scope = self.require_scope(root_job_id=admission["root_job_id"],
                                   source=admission["spec"]["source"])
        if any(admission.get(key) != scope[key] for key in
               ("source_binding_ref", "source_binding_digest")):
            raise ObservationError("timer host binding changed")


def make_admission(*, root_job_id: str, plan_attempt_id: str, plan_digest: str,
                   plan_step_id: str, root_creation_event_id: int,
                   authority_policy_hash: str, spec: Any, admitted_at_ms: int,
                   scope: Mapping[str, Any], finite_expiry_ms: int | None) -> dict[str, Any]:
    spec = validate_spec(spec)
    scope = _closed(scope, {"source_binding_ref", "source_binding_digest", "max_horizon_ms"},
                    "observation host scope")
    now = _integer(admitted_at_ms)
    horizon = _integer(scope["max_horizon_ms"], minimum=1, maximum=MAX_HORIZON_MS)
    deadlines = [spec["deadline_at_ms"], now + horizon]
    if finite_expiry_ms is not None:
        deadlines.append(_integer(finite_expiry_ms))
    effective = min(deadlines)
    if effective <= now or spec["source"]["due_at_ms"] >= effective:
        raise ObservationError("timer does not fit the remaining observation horizon")
    result = {"schema_version": ADMISSION_SCHEMA, "root_job_id": root_job_id,
              "plan_attempt_id": plan_attempt_id, "plan_digest": plan_digest,
              "plan_step_id": plan_step_id, "root_creation_event_id": root_creation_event_id,
              "authority_policy_hash": authority_policy_hash,
              "source_binding_ref": scope["source_binding_ref"],
              "source_binding_digest": scope["source_binding_digest"],
              "admitted_at_ms": now, "effective_deadline_at_ms": effective, "spec": spec}
    result["gate_digest"] = digest(result)
    return validate_admission(result, root_job_id=root_job_id, plan_attempt_id=plan_attempt_id,
                              plan_digest=plan_digest, plan_step_id=plan_step_id, spec=spec,
                              root_creation_event_id=root_creation_event_id,
                              authority_policy_hash=authority_policy_hash)


def validate_admission(value: Any, *, root_job_id: str, plan_attempt_id: str,
                       plan_digest: str, plan_step_id: str, spec: Any,
                       root_creation_event_id: int, authority_policy_hash: str) -> dict[str, Any]:
    value = _closed(value, _ADMISSION_KEYS, "observation admission")
    expected = {"schema_version": ADMISSION_SCHEMA, "root_job_id": root_job_id,
                "plan_attempt_id": plan_attempt_id, "plan_digest": plan_digest,
                "plan_step_id": plan_step_id, "root_creation_event_id": root_creation_event_id,
                "authority_policy_hash": authority_policy_hash, "spec": validate_spec(spec)}
    if any(value[key] != item for key, item in expected.items()):
        raise ObservationError("observation admission binding drifted")
    for key in ("root_job_id", "plan_attempt_id", "plan_step_id", "source_binding_ref"):
        if not isinstance(value[key], str) or _ID.fullmatch(value[key]) is None:
            raise ObservationError("observation admission identity is invalid")
    for key in ("plan_digest", "authority_policy_hash", "source_binding_digest", "gate_digest"):
        if not isinstance(value[key], str) or _SHA.fullmatch(value[key]) is None:
            raise ObservationError("observation admission digest is invalid")
    _integer(value["root_creation_event_id"], minimum=1)
    now = _integer(value["admitted_at_ms"])
    deadline = _integer(value["effective_deadline_at_ms"], minimum=1)
    if not (max(now, value["spec"]["source"]["due_at_ms"]) < deadline
            <= min(value["spec"]["deadline_at_ms"], now + MAX_HORIZON_MS)):
        raise ObservationError("observation admission horizon is invalid")
    material = dict(value)
    if material.pop("gate_digest") != digest(material):
        raise ObservationError("observation admission digest drifted")
    return value


def command_id(admission: Mapping[str, Any]) -> str:
    return f"coo-observation:{admission['gate_digest']}:1"


def timer_disposition(admission: Mapping[str, Any], now_ms: int) -> str:
    now = _integer(now_ms)
    if now >= admission["effective_deadline_at_ms"]:
        return "EXPIRED"
    if now < max(admission["admitted_at_ms"], admission["spec"]["source"]["due_at_ms"]):
        return "PENDING"
    return "MATERIAL"


def make_record(admission: Mapping[str, Any], now_ms: int) -> dict[str, Any]:
    disposition = timer_disposition(admission, now_ms)
    if disposition == "PENDING":
        raise ObservationError("pending timer has no record")
    snapshot = ({"kind": "timer", "due_at_ms": admission["spec"]["source"]["due_at_ms"],
                 "observed_at_ms": now_ms} if disposition == "MATERIAL" else None)
    record = {"schema_version": RECORD_SCHEMA,
              **{key: admission[key] for key in ("root_job_id", "plan_attempt_id", "plan_digest",
                                                "plan_step_id", "gate_digest")},
              "sample_index": 1, "reservation_command_id": None,
              "started_at_ms": now_ms, "finished_at_ms": now_ms,
              "disposition": disposition, "previous_snapshot_digest": None,
              "snapshot": snapshot, "snapshot_digest": None if snapshot is None else digest(snapshot)}
    record["evidence_digest"] = digest(record)
    return record


def validate_record(value: Any, admission: Mapping[str, Any]) -> dict[str, Any]:
    record = _closed(value, _RECORD_KEYS, "observation record")
    now = _integer(record["finished_at_ms"])
    if canonical_bytes(record) != canonical_bytes(make_record(admission, now)):
        raise ObservationError("observation record identity, time or evidence drifted")
    return record
