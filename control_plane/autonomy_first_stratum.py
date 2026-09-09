"""Offline first-stratum recorded-clock diagnostics; never execution authority.

The caller supplies all bytes and a separately trusted manifest digest. Comparing
two caller-controlled values does not authenticate a caller. This module neither
captures evidence nor promotes a stage. Its historical draft wire and source pins
belong to the accepted contract, independently of the source build's Git base.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re


__all__ = ("reduce_first_stratum",)

_CONTRACT = "ec8d19c3177f30bc7661f6b810e8bd6450c5a2154be6d1f68b798eb5dcc31784"
_INPUT_SCHEMA = "551ffa7078806523f595c1ad6b0a0b0d9ba97adfc08b4c8f3dc4bb08e5b92248"
_OUTPUT_SCHEMA = "4d833e0da396324afb5ea50dd280f41e2390b09dd5e9e38903d5ffaa2d680da5"
_DERIVATIVE = "50676bc4103aeb0f61d1b439366a57c43e6b0a21579bba165b2ee82fb4b03755"
_SOURCE = "2bf0266d5476c8e75dae4afa87cca67a8f12a838"
_RUNTIME = "9f5eeec9e69102a74b7bc95681c063d1c139ae1f"
_MIB = 1024 * 1024
_FULL = "EventRegistry.get_event_by_command_id"
_MS = "RuntimeStore.find_event_by_command_id"
_EVENTS = "EventRegistry.list_events"
_JOB = "JobRegistry.get_job"
_JOBS = "JobRegistry.list_jobs"
_ATTEMPT = "AttemptRegistry.get_attempt"
_RECEIPT = "ceo_intent.resolve_intent"
_EXECUTION_ROLES = ("plan", "work", "review", "repair")
_OUTCOMES = ("ACTIVE", "FAILED", "CANCELLED", "LOST", "TERMINAL_OTHER", "UNKNOWN")
_COVERAGE = ("OBSERVED_PREFIX_ONLY", "CLOSED_DECLARED_SCOPE", "UNKNOWN")
_COMPARABILITY = ("SUPPORTED_RECORDED_BASIS", "UNKNOWN", "CONFLICT")
_POSITION_ROLES = {
    "/source/instance_binding_ref": "INSTANCE_BINDING",
    "/run/environment_ref": "ENVIRONMENT",
    "/run/protocol_ref": "PROTOCOL",
    "/run/operation_authority_ref": "OPERATION_AUTHORITY",
    "/run/clock/basis_ref": "CLOCK_BASIS",
    "/run/clock/interpretation_ref": "CLOCK_INTERPRETATION",
    "/run/cutoff/basis_ref": "CUTOFF_BASIS",
    "/run/cutoff/closure_ref": "CUTOFF_CLOSURE",
    "/inventory/closure_ref": "INVENTORY_CLOSURE",
}
_JOB_IMMUTABLE = (
    "job_id", "parent_job_id", "root_job_id", "depth", "orchestration_role",
    "orchestration_provenance", "orchestration_provenance_digest",
    "authority_policy_hash", "plan_attempt_id", "plan_digest", "plan_step_id",
)


class _Refusal(ValueError):
    def __init__(self, reason, state="INVALID"):
        self.reason = reason
        self.state = state
        super().__init__(reason)


def _require(condition, reason="INPUT_SHAPE_INVALID", state="INVALID"):
    if not condition:
        raise _Refusal(reason, state)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _same(a, b):
    # JSON scalar identity matters: Python's True == 1 must not bind evidence.
    return _canonical(a) == _canonical(b)


def _str(value):
    return type(value) is str


def _text(value):
    return _str(value) and bool(value)


def _nullable_text(value):
    return value is None or _str(value)


def _integer(value):
    return type(value) is int and value >= 0


def _positive(value):
    return type(value) is int and value > 0


def _nullable_integer(value):
    return value is None or _integer(value)


def _digest(value):
    return _str(value) and re.fullmatch("[0-9a-f]{64}", value) is not None


def _object(value):
    return type(value) is dict


def _shape(value, fields, *, optional=(), open_record=False):
    """Local field checker for this fixed wire, not a JSON Schema interpreter."""
    _require(_object(value))
    _require(set(fields) - set(optional) <= value.keys())
    _require(open_record or value.keys() <= fields.keys())
    for key, validator in fields.items():
        if key in value:
            _require(validator(value[key]))
    return True


def _array(value, validator):
    _require(type(value) is list)
    for item in value:
        _require(validator(item))
    return True


def _reference(value):
    return _shape(value, {"uri": _text, "sha256": _digest,
                          "bytes": _integer, "json_pointer": _str})


def _nullable_ref(value):
    return value is None or _reference(value)


def _pair_shape(value):
    return _shape(value, {"full_read": _nullable_text, "millisecond_read": _nullable_text})


def _event_shape(value):
    return _shape(value, {
        "event_id": _positive, "aggregate_type": _text, "aggregate_id": _text,
        "sequence": _positive, "event_type": _text, "command_id": _text, "actor": _text,
        "job_id": _nullable_text, "attempt_id": _nullable_text,
        "worker_id": _nullable_text, "quota_class": _nullable_text,
        "payload": _object, "created_at": _text,
    })


def _job_shape(value):
    return _shape(value, {
        "job_id": _text, "parent_job_id": _nullable_text, "root_job_id": _text,
        "depth": _integer, "orchestration_role": lambda x: x in ("aggregation", *_EXECUTION_ROLES, None),
        "orchestration_provenance": lambda x: x is None or _object(x),
        "orchestration_provenance_digest": _nullable_text, "status": _text,
        "current_attempt_id": _nullable_text, "authority_policy_hash": _text,
        "plan_attempt_id": _nullable_text, "plan_digest": _nullable_text,
        "plan_step_id": _nullable_text,
    }, open_record=True)


def _attempt_shape(value):
    return _shape(value, {
        "attempt_id": _text, "job_id": _text, "attempt_number": _positive,
        "worker_id": _text, "quota_class": _text, "fence_generation": _positive,
        "authority_policy_hash": _text, "status": _text,
    }, open_record=True)


def _receipt_shape(value):
    return _shape(value, {
        "schema": lambda x: x in ("mastermind.ceo_intent_receipt.v1", "mastermind.ceo_intent_receipt.v2"),
        "intent_id": _text, "fingerprint": _digest, "job_id": _text, "status": _text,
        "accepted": lambda x: type(x) is bool, "duplicate": lambda x: type(x) is bool,
        "dispatched": lambda x: type(x) is bool, "created_at_ms": _integer,
        "authority": _object, "grounding": _object,
    }, open_record=True)


def _observation_shape(value):
    return _shape(value, {
        "runtime_instance_epoch": _nullable_text, "read_group": _text,
        "scope": _object, "read_started_at_ms": _nullable_integer,
        "read_finished_at_ms": _nullable_integer, "prefix_last_event_id": _nullable_integer,
        "coverage": lambda x: x in _COVERAGE, "closure_ref": _nullable_ref,
    })


def _read_shape(value):
    _shape(value, {
        "reader": lambda x: x in (_FULL, _MS, _EVENTS, _JOB, _JOBS, _ATTEMPT, _RECEIPT),
        "arguments": _object, "record": lambda x: True,
        "evidence_ref": _reference, "observation": _observation_shape,
        "invocation_ref": _reference,
    })
    reader, args, record = value["reader"], value["arguments"], value["record"]
    if reader in (_FULL, _MS):
        _shape(args, {"command_id": _text})
        validator = _event_shape if reader == _FULL else lambda x: _shape(x, {
            "event_type": _text, "job_id": _nullable_text, "payload": _object, "created_at_ms": _integer})
    elif reader == _EVENTS:
        fields = dict.fromkeys(("job_id", "attempt_id", "aggregate_type", "aggregate_id", "command_id_prefix"), _text)
        _shape(args, fields, optional=fields)
        validator = lambda x: _array(x, _event_shape)
    elif reader == _JOBS:
        _shape(args, {})
        validator = lambda x: _array(x, _job_shape)
    else:
        identity, validator = {
            _JOB: ("job_id", _job_shape), _ATTEMPT: ("attempt_id", _attempt_shape),
            _RECEIPT: ("intent_id", _receipt_shape),
        }[reader]
        _shape(args, {identity: _text})
    if record is not None:
        validator(record)
    return True


def _candidate_shape(value):
    return _shape(value, {
        "creation_read": _nullable_text, "job_read": _nullable_text, "claim": _pair_shape,
        "attempt_read": _nullable_text, "authority_ref": _nullable_ref,
    })


def _member_shape(value):
    return _shape(value, {
        "intent_id": _text, "fingerprint": _digest,
        "decision": lambda x: x in ("ACCEPTED", "REJECTED", "NOT_APPLICABLE", "UNKNOWN", "CONFLICT"),
        "decision_evidence_ref": _nullable_ref, "reason": _nullable_text,
        "receipt_read": _nullable_text, "root_admission": _pair_shape, "root_job_read": _nullable_text,
        "child_inventory_read": _nullable_text, "child_event_inventory_reads": lambda x: _array(x, _text),
        "claim_candidates": lambda x: _array(x, _candidate_shape),
        "lifecycle_outcome": lambda x: x in _OUTCOMES,
        "lifecycle_evidence_reads": lambda x: _array(x, _text), "lifecycle_subject_job_id": _nullable_text,
    })


def _capsule_shape(capsule):
    _shape(capsule, {
        "schema": lambda x: x == "mastermind.autonomy_first_stratum_input/draft1",
        "contract_sha256": lambda x: x == _CONTRACT,
        "evidence_class": lambda x: x in ("SYNTHETIC", "OWNER_EXPORTED"),
        "source": _object, "run": _object, "inventory": _object, "reads": _object,
    })
    _shape(capsule["source"], {
        "repository": lambda x: x == "mastermindx-market-intelligence/Mastermind",
        "commit": lambda x: x == _SOURCE, "runtime_blob": lambda x: x == _RUNTIME,
        "runtime_instance_epoch": _nullable_text, "instance_binding_ref": _nullable_ref,
    })
    run = capsule["run"]
    _shape(run, {
        "cohort_id": _nullable_text, "work_class": _nullable_text,
        "environment_ref": _nullable_ref, "protocol_ref": _nullable_ref,
        "operation_authority_ref": _nullable_ref, "clock": _object, "cutoff": _object,
        "accepted_budget_ms": _object,
        "budget_candidate_status": lambda x: x == "PROPOSED_ONLY_NOT_EVALUATED",
    })
    _shape(run["clock"], {
        "basis": lambda x: x == "RECORDED_EVENT_APPEND_OBSERVATION",
        "storage_granularity_ms": lambda x: type(x) is int and x == 1,
        "public_display_resolution_ms": lambda x: type(x) is int and x == 1000,
        "comparability": lambda x: x in _COMPARABILITY,
        "basis_ref": _nullable_ref, "interpretation_ref": _nullable_ref,
        "error_bound_ms": _nullable_integer,
    })
    _shape(run["cutoff"], {"recorded_at_ms": _nullable_integer,
                           "basis_ref": _nullable_ref, "closure_ref": _nullable_ref})
    _shape(run["accepted_budget_ms"], dict.fromkeys(("p50", "p95", "max"), lambda x: True))
    _shape(capsule["inventory"], {
        "coverage": lambda x: x in ("COMPLETE", "UNKNOWN", "CONFLICT"),
        "closure_ref": _nullable_ref, "members": lambda x: _array(x, _member_shape),
    })
    for read in capsule["reads"].values():
        _read_shape(read)
    # The accepted E13 discriminator follows all other closed-shape validation.
    _require(all(x is None for x in run["accepted_budget_ms"].values()),
             "DRAFT_ACCEPTED_BUDGET_FORBIDDEN")


def _decode(raw, remaining):
    """Bound nesting before recursive json.loads; count all decoded value nodes.

    Depth counts nested objects/arrays (root container is depth one). Node count
    includes each container and scalar value, excluding object member names.
    The shared allowance covers capsule, manifest and every supplied artifact.
    """
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "INPUT_DUPLICATE_KEY")
            result[key] = value
        return result
    def bad_constant(value):
        raise _Refusal("INPUT_NONFINITE_NUMBER")
    try:
        text = raw.decode("utf-8", errors="strict")
        depth = 0
        quoted = escaped = False
        for character in text:
            if quoted:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in "[{":
                depth += 1
                _require(depth <= 64, "INPUT_RESOURCE_LIMIT")
            elif character in "]}":
                depth -= 1
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)
        pending = [value]
        while pending:
            item = pending.pop()
            remaining[0] -= 1
            _require(remaining[0] >= 0, "INPUT_RESOURCE_LIMIT")
            if type(item) is dict:
                for key in item:
                    key.encode("utf-8", errors="strict")
                pending.extend(item.values())
            elif type(item) is list:
                pending.extend(item)
            elif type(item) is float:
                _require(math.isfinite(item), "INPUT_NONFINITE_NUMBER")
            elif type(item) is str:
                item.encode("utf-8", errors="strict")
            _require(len(pending) <= remaining[0], "INPUT_RESOURCE_LIMIT")
        return value
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise _Refusal("INPUT_INVALID_JSON") from exc
    except (RecursionError, MemoryError) as exc:
        raise _Refusal("INPUT_RESOURCE_LIMIT") from exc
    except ValueError as exc:
        if isinstance(exc, _Refusal):
            raise
        raise _Refusal("INPUT_INVALID_JSON") from exc


def _pointer(value, pointer):
    _require(pointer == "" or pointer.startswith("/"), "EVIDENCE_POINTER_INVALID")
    _require(re.search(r"~(?![01])", pointer) is None, "EVIDENCE_POINTER_INVALID")
    if pointer:
        for token in pointer.split("/")[1:]:
            token = token.replace("~1", "/").replace("~0", "~")
            if type(value) is list:
                _require(re.fullmatch("0|[1-9][0-9]*", token) is not None, "EVIDENCE_POINTER_INVALID")
                _require(len(token) <= 10, "EVIDENCE_POINTER_INVALID")
                index = int(token)
                _require(index < len(value), "EVIDENCE_POINTER_INVALID")
                value = value[index]
            else:
                _require(_object(value) and token in value, "EVIDENCE_POINTER_INVALID")
                value = value[token]
    return value


def _positions(capsule):
    positions = dict(_POSITION_ROLES)
    for index, member in enumerate(capsule["inventory"]["members"]):
        positions[f"/inventory/members/{index}/decision_evidence_ref"] = "ADMISSION_DECISION"
        for ci in range(len(member["claim_candidates"])):
            positions[f"/inventory/members/{index}/claim_candidates/{ci}/authority_ref"] = "CANDIDATE_AUTHORITY"
    return positions


def _manifest_check(capsule, raw, manifest, manifest_raw, expected):
    _require(_digest(expected) and _sha(manifest_raw) == expected, "TRUST_ANCHOR_MISMATCH")
    try:
        _shape(manifest, {
            "schema": lambda x: x == "mastermind.autonomy_first_stratum_trusted_inputs/v1",
            "evidence_class": lambda x: x in ("SYNTHETIC", "OWNER_EXPORTED"),
            "capsule_sha256": _digest, "capsule_bytes": _integer,
            "contract_sha256": lambda x: x == _CONTRACT,
            "input_schema_sha256": lambda x: x == _INPUT_SCHEMA,
            "output_schema_sha256": lambda x: x == _OUTPUT_SCHEMA,
            "derivative_index_sha256": lambda x: x == _DERIVATIVE,
            "source_commit": lambda x: x == _SOURCE, "runtime_blob": lambda x: x == _RUNTIME,
            "runtime_instance_epoch": _nullable_text, "cohort_id": _nullable_text,
            "work_class": _nullable_text, "cutoff_recorded_at_ms": _nullable_integer,
            "accepted_refs": lambda x: type(x) is list,
        })
        _require(manifest["capsule_bytes"] == len(raw) and manifest["capsule_sha256"] == _sha(raw))
        for key, actual in (("runtime_instance_epoch", capsule["source"]["runtime_instance_epoch"]),
                            ("cohort_id", capsule["run"]["cohort_id"]),
                            ("work_class", capsule["run"]["work_class"]),
                            ("cutoff_recorded_at_ms", capsule["run"]["cutoff"]["recorded_at_ms"])):
            _require(_same(manifest[key], actual))
        positions = _positions(capsule)
        required = {p for p in positions if _pointer(capsule, p) is not None}
        seen = set()
        for ref in manifest["accepted_refs"]:
            _shape(ref, {"role": _text, "capsule_ref_pointer": _text, "uri": _text,
                         "bytes": _integer, "sha256": _digest, "json_pointer": _str})
            position = ref["capsule_ref_pointer"]
            _require(position in required and position not in seen)
            _require(ref["role"] == positions[position])
            _require(_same({k: ref[k] for k in ("uri", "bytes", "sha256", "json_pointer")},
                           _pointer(capsule, position)))
            seen.add(position)
        _require(seen == required)
    except _Refusal as exc:
        raise _Refusal("TRUST_ANCHOR_MISMATCH") from exc


class _Evidence:
    """Invocation-local byte resolver. URI strings are only mapping keys."""
    def __init__(self, capsule, artifacts, decoded):
        self.c = capsule
        self.reads = capsule["reads"]
        self.artifacts = artifacts
        self.decoded = decoded
        self.digests = {}
        self.synthetic = False

    def resolve(self, ref):
        _require(ref is not None, "EVIDENCE_REFERENCE_UNAVAILABLE", "MISSING")
        uri = ref["uri"]
        _require(uri in self.artifacts, "EVIDENCE_BYTES_MISSING", "MISSING")
        raw = self.artifacts[uri]
        if uri not in self.digests:
            self.digests[uri] = _sha(raw)
        _require(len(raw) == ref["bytes"] and self.digests[uri] == ref["sha256"], "EVIDENCE_BYTES_MISMATCH")
        value = _pointer(self.decoded[uri], ref["json_pointer"])
        # Provenance belongs to the admitted content at the actual pointer. A
        # legal wrapper cannot launder a synthetic receipt into owner evidence.
        if not self.synthetic:
            pending = [value]
            while pending:
                item = pending.pop()
                if _object(item):
                    if item.get("synthetic") is True:
                        self.synthetic = True
                        break
                    pending.extend(item.values())
                elif type(item) is list:
                    pending.extend(item)
        return value

    def validate(self):
        for position in _positions(self.c):
            ref = _pointer(self.c, position)
            if ref is not None:
                self.resolve(ref)
        for read_id, read in self.reads.items():
            _require(_same(self.resolve(read["evidence_ref"]), read["record"]), "READ_RECORD_MISMATCH")
            invocation = {k: read[k] for k in ("reader", "arguments", "observation")}
            _require(_same(self.resolve(read["invocation_ref"]), invocation), "READER_INVOCATION_MISMATCH")
            obs = read["observation"]
            _require(obs["runtime_instance_epoch"] == self.c["source"]["runtime_instance_epoch"]
                     and bool(obs["runtime_instance_epoch"]), "RUNTIME_INSTANCE_MISMATCH")
            start, end = obs["read_started_at_ms"], obs["read_finished_at_ms"]
            _require(start is not None and end is not None and start <= end, "READ_WINDOW_UNPROVEN", "UNKNOWN")
            if obs["closure_ref"] is not None:
                self.resolve(obs["closure_ref"])
            if read["record"] is not None and read["reader"] != _MS:
                _named(self, read_id, read["reader"], "READ_RECORD_MISSING")

    def read(self, read_id, reader, reason):
        _require(read_id is not None and read_id in self.reads, reason, "MISSING")
        read = self.reads[read_id]
        _require(read["reader"] == reader, "READER_TYPE_MISMATCH")
        _require(read["record"] is not None, reason, "MISSING")
        return read


def _output(raw):
    return {
        "schema": "mastermind.autonomy_first_stratum_output/draft1", "contract_sha256": _CONTRACT,
        "evidence_class": "SYNTHETIC", "derivation_status": "HOLD_UNSUPPORTED",
        "reason_codes": ["DRAFT_NOT_ACCEPTED"], "inventory_population": None,
        "known_admitted_roots": 0, "completed_recorded_intervals": 0, "distinct_contributing_roots": 0,
        "member_results": [],
        "completed_sample_quantiles_ms": {"p50": None, "p95": None, "max": None,
            "interpretation": "CONDITIONAL_ON_COMPLETED_RECORDED_INTERVALS_NOT_AN_SLO"},
        "other_metrics": {name: {"state": "UNAVAILABLE", "p50": None, "p95": None, "max": None}
            for name in ("claim_to_provider_start", "provider_terminal_to_company_return",
                         "company_return_to_sol_target", "sol_action_to_worker_continuation", "eligible_capacity_wait")},
        "accepted_budget_ms": {"p50": None, "p95": None, "max": None}, "accepted_stage": "NONE",
        "verdict": "HOLD", "promotion_applied": False, "operational_qualified_count": 0,
        "adverse_obligations": {"count": 18, "state": "NOT_RUN_THIS_OPERATION"},
        "distribution_status": "NOT_QUALIFIED",
        "production_continuation_rule": "ceil(N/3) AND at least 7 distinct cohort roots; no production cohort observed",
        "input_sha256": _sha(raw), "source_commit": _SOURCE, "runtime_instance_epoch": None,
        "semantic_adjudication": "PENDING_ROOT_INDEPENDENT_REVIEW",
        "clock_summary": {"basis": "RECORDED_EVENT_APPEND_OBSERVATION", "storage_granularity_ms": 1,
            "public_display_resolution_ms": 1000, "comparability": "UNKNOWN", "error_bound_ms": None,
            "physical_elapsed_accuracy": "NOT_ESTABLISHED", "timestamp_order": "UNKNOWN"},
        "read_scope_qualifiers": [], "inventory_coverage": "UNKNOWN",
    }


def _metadata(output, capsule, *, evidence_validated=False):
    # Called only after all shapes (except E13's accepted budget discriminator) pass.
    # Category is declared, not authenticated provenance. Synthetic diagnostics
    # retain their frozen projection; owner observations need complete evidence.
    output["evidence_class"] = capsule["evidence_class"]
    if capsule["evidence_class"] != "SYNTHETIC" and not evidence_validated:
        return
    output["runtime_instance_epoch"] = capsule["source"]["runtime_instance_epoch"]
    output["inventory_coverage"] = capsule["inventory"]["coverage"]
    for key in ("comparability", "error_bound_ms"):
        output["clock_summary"][key] = capsule["run"]["clock"][key]
    output["read_scope_qualifiers"] = [
        {"read_id": key, **{k: read["observation"][k]
                           for k in ("scope", "prefix_last_event_id", "coverage")}}
        for key, read in sorted(capsule["reads"].items())
    ]


def _member_result(key=None, outcome="ACTIVE", subject=None):
    return {"observation_key": key, "state": "UNKNOWN", "reason_codes": [],
            "raw_difference_ms": None, "recorded_delta_ms": None,
            "right_censor_lower_bound_ms": None, "outcome_retained": outcome,
            "root_weight": 0, "outcome_subject_job_id": subject}


def _mark(result, reason, state="INVALID"):
    result["state"] = state
    if reason not in result["reason_codes"]:
        result["reason_codes"].append(reason)


def _order(output):
    values = [m["raw_difference_ms"] for m in output["member_results"] if m["raw_difference_ms"] is not None]
    output["clock_summary"]["timestamp_order"] = (
        "REVERSED" if any(v < 0 for v in values) else "NONDECREASING_RECORDED_PAIR" if values else "UNKNOWN")


def _iso(milliseconds):
    try:
        # Integer division reproduces the source's whole-second UTC projection
        # without a float conversion or any clock read.
        return (datetime(1970, 1, 1, tzinfo=timezone.utc)
                + timedelta(seconds=milliseconds // 1000)).isoformat(timespec="seconds")
    except (OverflowError, ValueError) as exc:
        raise _Refusal("RECORDED_TIMESTAMP_UNREPRESENTABLE") from exc


def _scope(read):
    _require(_same(read["arguments"], read["observation"]["scope"]), "READ_SCOPE_MISMATCH")


def _pair(evidence, pair, name):
    full = evidence.read(pair["full_read"], _FULL, name + "_FULL_EVENT_MISSING")
    narrow = evidence.read(pair["millisecond_read"], _MS, name + "_MILLISECOND_RECORD_MISSING")
    event, ms = full["record"], narrow["record"]
    _require(full["arguments"] == narrow["arguments"]
             and full["arguments"]["command_id"] == event["command_id"], "EVENT_PAIR_COMMAND_MISMATCH")
    _require(all(_same(event[key], ms[key]) for key in ("event_type", "job_id", "payload")),
             "EVENT_PAIR_PAYLOAD_MISMATCH")
    _require(event["created_at"] == _iso(ms["created_at_ms"]), "EVENT_PAIR_DISPLAY_MISMATCH")
    _scope(full)
    _scope(narrow)
    return event, ms["created_at_ms"]


def _named(evidence, read_id, reader, reason):
    read = evidence.read(read_id, reader, reason)
    _scope(read)
    if reader in (_JOB, _ATTEMPT, _RECEIPT):
        key = {_JOB: "job_id", _ATTEMPT: "attempt_id", _RECEIPT: "intent_id"}[reader]
        _require(read["arguments"][key] == read["record"][key], "READER_ARGUMENT_IDENTITY_MISMATCH")
    elif reader == _FULL:
        _require(read["arguments"]["command_id"] == read["record"]["command_id"],
                 "EVENT_PAIR_COMMAND_MISMATCH")
    elif reader == _EVENTS:
        for event in read["record"]:
            for key, value in read["arguments"].items():
                if key == "command_id_prefix":
                    matches = event["command_id"].startswith(value)
                else:
                    matches = event[key] == value
                _require(matches, "READER_ARGUMENT_IDENTITY_MISMATCH")
    return read["record"]


def _provenance(job, creation, *, creator, source_id, source_digest):
    provenance = job["orchestration_provenance"]
    expected = {
        "schema_version": "mastermind.executive_orchestration_provenance/v1",
        "creator": creator, "source_id": source_id, "source_digest": source_digest,
        "command_id": creation["command_id"], "job_id": job["job_id"],
        "root_job_id": job["root_job_id"], "parent_job_id": job["parent_job_id"],
        "role": job["orchestration_role"],
    }
    _require(_same(provenance, expected), "ORCHESTRATION_PROVENANCE_MISMATCH")
    digest = _sha(_canonical(provenance).encode("utf-8"))
    _require(job["orchestration_provenance_digest"] == digest
             and creation["payload"].get("orchestration_provenance_digest") == digest,
             "ORCHESTRATION_PROVENANCE_DIGEST_MISMATCH")


def _creation_identity(job, event):
    _require(event["event_type"] == "JOB_CREATED" and event["aggregate_type"] == "job"
             and event["aggregate_id"] == job["job_id"] == event["job_id"], "CREATION_IDENTITY_MISMATCH")
    for key in ("parent_job_id", "root_job_id", "depth", "orchestration_role"):
        _require(key in event["payload"] and _same(event["payload"][key], job[key]),
                 "CREATION_LINEAGE_MISMATCH")


def _known_admission(evidence, member):
    if member["decision"] != "ACCEPTED" or member["decision_evidence_ref"] is None:
        return False
    try:
        receipt = _named(evidence, member["receipt_read"], _RECEIPT, "ADMISSION_RECEIPT_MISSING")
        return (receipt["accepted"] and receipt["schema"] == "mastermind.ceo_intent_receipt.v2"
                and receipt["intent_id"] == member["intent_id"]
                and receipt["fingerprint"] == member["fingerprint"]
                and receipt["grounding"].get("mastermind_sha") == _SOURCE)
    except _Refusal:
        return False


def _root(evidence, member):
    _require(member["decision_evidence_ref"] is not None, "ADMISSION_AUTHORITY_UNPROVEN", "UNKNOWN")
    _require(_known_admission(evidence, member), "STRICT_V2_ADMISSION_UNPROVEN")
    start, start_ms = _pair(evidence, member["root_admission"], "ROOT")
    job = _named(evidence, member["root_job_read"], _JOB, "ROOT_JOB_MISSING")
    receipt = _named(evidence, member["receipt_read"], _RECEIPT, "ADMISSION_RECEIPT_MISSING")
    _require(job["parent_job_id"] is None and job["root_job_id"] == job["job_id"]
             and job["depth"] == 0 and job["orchestration_role"] == "aggregation", "ROOT_LINEAGE_MISMATCH")
    _creation_identity(job, start)
    _require(start["command_id"] == "ceo-intent:" + member["intent_id"]
             and receipt["job_id"] == job["job_id"] and receipt["created_at_ms"] == start_ms,
             "ROOT_RECEIPT_IDENTITY_MISMATCH")
    provenance = start["payload"].get("provenance")
    _require(_object(provenance), "STRICT_V2_PROVENANCE_MISSING")
    _require(provenance.get("schema") == "mastermind.ceo_intent.v2"
             and provenance.get("intent_id") == member["intent_id"]
             and provenance.get("fingerprint") == member["fingerprint"]
             and _same(provenance.get("grounding"), receipt["grounding"]), "STRICT_V2_PROVENANCE_MISMATCH")
    _require(receipt["authority"].get("policy_sha256") == job["authority_policy_hash"],
             "ADMISSION_AUTHORITY_MISMATCH")
    _provenance(job, start, creator="ceo_intent", source_id=member["intent_id"], source_digest=member["fingerprint"])
    return start, start_ms, job


def _child(evidence, candidate, start, root_job):
    job = _named(evidence, candidate["job_read"], _JOB, "CHILD_JOB_MISSING")
    creation = _named(evidence, candidate["creation_read"], _FULL, "CHILD_CREATION_MISSING")
    if job["orchestration_role"] is None:
        raise _Refusal("ROLE_NULL_CARRIER_EXCLUDED")
    _require(job["orchestration_role"] in _EXECUTION_ROLES, "NON_EXECUTION_ROLE_EXCLUDED")
    _require(job["job_id"] != root_job["job_id"]
             and job["parent_job_id"] == job["root_job_id"] == root_job["job_id"]
             and job["depth"] == 1, "CHILD_LINEAGE_MISMATCH")
    _creation_identity(job, creation)
    _provenance(job, creation, creator="coo_cycle", source_id=root_job["job_id"],
                source_digest=root_job["orchestration_provenance_digest"])
    for key in ("plan_attempt_id", "plan_digest", "plan_step_id"):
        _require(key in creation["payload"] and _same(creation["payload"][key], job[key]),
                 "CHILD_PLAN_IDENTITY_MISMATCH")
    _require(start["event_id"] < creation["event_id"], "CAUSAL_EVENT_ORDER_INVALID")
    _require(candidate["authority_ref"] is not None, "CANDIDATE_AUTHORITY_UNPROVEN", "UNKNOWN")
    return job, creation


def _claim(evidence, candidate, start, root_job, pair):
    event, milliseconds = pair
    job, creation = _child(evidence, candidate, start, root_job)
    _require(event["event_type"] == "JOB_CLAIMED" and event["aggregate_type"] == "job"
             and event["aggregate_id"] == event["job_id"] == job["job_id"], "CLAIM_JOB_IDENTITY_MISMATCH")
    _require(start["event_id"] < creation["event_id"] < event["event_id"]
             and creation["sequence"] < event["sequence"], "CAUSAL_EVENT_ORDER_INVALID")
    attempt = _named(evidence, candidate["attempt_read"], _ATTEMPT, "HISTORICAL_ATTEMPT_MISSING")
    for key in ("attempt_id", "job_id", "worker_id", "quota_class"):
        _require(event[key] is not None and event[key] == attempt[key], "HISTORICAL_CLAIM_IDENTITY_MISMATCH")
    for key in ("attempt_number", "fence_generation", "authority_policy_hash"):
        _require(key in event["payload"] and _same(event["payload"][key], attempt[key]),
                 "HISTORICAL_CLAIM_IDENTITY_MISMATCH")
    _require(attempt["authority_policy_hash"] == job["authority_policy_hash"], "CLAIM_POLICY_MISMATCH")
    for key in ("effective_grant_digest", "placement_snapshot_digest"):
        if key in attempt or key in event["payload"]:
            _require(key in attempt and key in event["payload"]
                     and _same(attempt[key], event["payload"][key])
                     and (attempt[key] is None or _digest(attempt[key])), "CLAIM_GRANT_PLACEMENT_MISMATCH")
    for key, expected in (("orchestration_role", job["orchestration_role"]),
                          ("cycle_command_id", event["command_id"]), ("dispatch_job_id", job["job_id"])):
        if key in event["payload"]:
            _require(_same(event["payload"][key], expected), "CLAIM_DISPATCH_IDENTITY_MISMATCH")
    # Deliberately do not equate job.current_attempt_id with this historical Attempt.
    return event, milliseconds, job


def _closure(evidence, ref, *, read=None, root=None):
    """Recognize only the accepted synthetic assumptions, never invent an export.

    The externally pinned whole capsule binds each assumption to its finite
    membership and invocation. Real owner closure formats have not been admitted
    by this contract; an opaque approval flag is not a closure proof.
    """
    if ref is None:
        return False
    content = evidence.resolve(ref)
    if not _object(content) or content.get("synthetic") is not True:
        return False
    if set(content) == {"synthetic", "assumption", "authority"}:
        return (content["assumption"] == "closure"
                and content["authority"] == "NONE; example assumption only")
    cutoff_fields = {"synthetic", "authority", "runtime_instance_epoch", "root_job_id", "child_job_id",
                     "cutoff_recorded_at_ms", "complete_no_claim_prefix_event_ids", "last_scoped_event_id",
                     "late_backdated_or_pending_pre_cutoff_claims", "no_global_watermark_claim"}
    if (set(content) != cutoff_fields or not _text(content["root_job_id"])
            or not _text(content["child_job_id"]) or not _integer(content["cutoff_recorded_at_ms"])
            or type(content["complete_no_claim_prefix_event_ids"]) is not list
            or not all(_positive(i) for i in content["complete_no_claim_prefix_event_ids"])
            or not _integer(content["last_scoped_event_id"])):
        return False
    if read is None or root is None:
        # Detailed cutoff assumption is checked against its actual scoped read below.
        return (content.get("runtime_instance_epoch") == evidence.c["source"]["runtime_instance_epoch"]
                and content.get("cutoff_recorded_at_ms") == evidence.c["run"]["cutoff"]["recorded_at_ms"]
                and content.get("no_global_watermark_claim") is True
                and content.get("late_backdated_or_pending_pre_cutoff_claims")
                    == "hypothetically excluded for this synthetic case")
    records = read["record"]
    if "complete_no_claim_prefix_event_ids" in content:
        return (content.get("runtime_instance_epoch") == evidence.c["source"]["runtime_instance_epoch"]
                and content.get("root_job_id") == root
                and content.get("child_job_id") == read["arguments"].get("job_id")
                and content.get("cutoff_recorded_at_ms") == evidence.c["run"]["cutoff"]["recorded_at_ms"]
                and _same(content.get("complete_no_claim_prefix_event_ids"), [e["event_id"] for e in records])
                and content.get("last_scoped_event_id") == read["observation"]["prefix_last_event_id"]
                and all(e["event_type"] != "JOB_CLAIMED" for e in records)
                and content.get("no_global_watermark_claim") is True
                and content.get("late_backdated_or_pending_pre_cutoff_claims")
                    == "hypothetically excluded for this synthetic case")
    # Later retained observations are useful evidence but do not close the cutoff.
    return False


def _closed_read(evidence, read, root=None):
    return (read["observation"]["coverage"] == "CLOSED_DECLARED_SCOPE"
            and _closure(evidence, read["observation"]["closure_ref"], read=read, root=root))


def _coverage(evidence, member, root_job, claims, cutoff):
    jobs_read = evidence.read(member["child_inventory_read"], _JOBS, "CHILD_INVENTORY_MISSING")
    jobs = _named(evidence, member["child_inventory_read"], _JOBS, "CHILD_INVENTORY_MISSING")
    children = {job["job_id"]: job for job in jobs if job["parent_job_id"] == root_job["job_id"]
                and job["root_job_id"] == root_job["job_id"] and job["depth"] == 1
                and job["orchestration_role"] in _EXECUTION_ROLES}
    _require(any(job["job_id"] == root_job["job_id"] for job in jobs),
             "FIRST_CLAIM_NOT_ESTABLISHED", "UNKNOWN")
    membership_closed = _closed_read(evidence, jobs_read)
    if not membership_closed and jobs_read["observation"]["closure_ref"] is not None:
        # A detailed accepted cutoff assumption freezes this root's child. A
        # separately retained later Job snapshot can identify that child without
        # pretending its later observation closes the earlier timestamp cut.
        cut = evidence.resolve(evidence.c["inventory"]["closure_ref"])
        later = evidence.resolve(jobs_read["observation"]["closure_ref"])
        membership_closed = (
            _object(cut) and _object(later) and _text(cut.get("child_job_id"))
            and cut.get("root_job_id") == root_job["job_id"]
            and set(children) == {cut["child_job_id"]}
            and later.get("synthetic") is True
            and later.get("runtime_instance_epoch") == evidence.c["source"]["runtime_instance_epoch"]
            and later.get("job_id") == cut["child_job_id"]
            and later.get("not_a_cutoff_point_observation") is True
            and jobs_read["observation"]["coverage"] == "CLOSED_DECLARED_SCOPE"
        )
    _require(membership_closed, "FIRST_CLAIM_NOT_ESTABLISHED", "UNKNOWN")
    inventories = []
    for read_id in member["child_event_inventory_reads"]:
        read = evidence.read(read_id, _EVENTS, "CHILD_EVENT_INVENTORY_MISSING")
        _named(evidence, read_id, _EVENTS, "CHILD_EVENT_INVENTORY_MISSING")
        inventories.append(read)
    claims_by_id = {event["event_id"]: (event, ms, child) for event, ms, child in claims}
    observed_claims = set()
    for child_id in children:
        # A filtered Attempt/prefix query cannot establish all claims of a child.
        scoped = [r for r in inventories if r["arguments"] == {"job_id": child_id}]
        closed = [r for r in scoped if _closed_read(evidence, r, root_job["job_id"])]
        _require(bool(closed), "FIRST_CLAIM_NOT_ESTABLISHED", "UNKNOWN")
        for read in scoped:
            records = read["record"]
            ids = [e["event_id"] for e in records]
            _require(ids == sorted(set(ids)), "EVENT_INVENTORY_ORDER_CONFLICT")
            _require(read["observation"]["prefix_last_event_id"] == (max(ids) if ids else 0),
                     "SCOPED_PREFIX_IDENTITY_MISMATCH")
            for event in records:
                if event["event_type"] == "JOB_CLAIMED":
                    _require(event["event_id"] in claims_by_id, "FIRST_CLAIM_NOT_ESTABLISHED", "UNKNOWN")
                    observed_claims.add(event["event_id"])
        # Every supplied pre-cutoff claim must occur in a positively closed prefix.
        for event, milliseconds, job in claims:
            if job["job_id"] == child_id and milliseconds <= cutoff:
                _require(any(any(e["event_id"] == event["event_id"] for e in r["record"])
                             for r in closed), "CUTOFF_CLOSURE_UNPROVEN", "UNKNOWN")
    for event, _, job in claims:
        _require(job["job_id"] in children and event["event_id"] in observed_claims,
                 "FIRST_CLAIM_NOT_ESTABLISHED", "UNKNOWN")
    return children


def _terminal(evidence, member, root_job, children, start, start_ms, first, cutoff):
    subject = member["lifecycle_subject_job_id"]
    outcome = member["lifecycle_outcome"]
    allowed_subjects = {root_job["job_id"], *children}
    _require(subject is None or subject in allowed_subjects, "OUTCOME_SUBJECT_MISMATCH")
    full, narrow = {}, {}
    for read_id in member["lifecycle_evidence_reads"]:
        _require(read_id in evidence.reads, "LIFECYCLE_EVIDENCE_MISSING", "MISSING")
        read = evidence.reads[read_id]
        record = read["record"]
        if record is None:
            continue
        if read["reader"] == _FULL:
            full[record["command_id"]] = read_id
        elif read["reader"] == _MS:
            narrow[read["arguments"]["command_id"]] = read_id
    terminal_types = {"FAILED": "JOB_FAILED", "CANCELLED": "JOB_CANCELLED", "LOST": "JOB_LOST"}
    terminals = []
    for command, read_id in full.items():
        event = evidence.reads[read_id]["record"]
        if event["event_type"] in (*terminal_types.values(), "JOB_COMPLETED"):
            pair = {"full_read": read_id, "millisecond_read": narrow.get(command)}
            event, ms = _pair(evidence, pair, "TERMINAL")
            _require(event["aggregate_type"] == "job" and event["aggregate_id"] == event["job_id"]
                     and event["job_id"] in allowed_subjects and event["event_id"] > start["event_id"]
                     and ms >= start_ms, "TERMINAL_IDENTITY_MISMATCH")
            terminals.append((event, ms))
    if outcome == "ACTIVE":
        measured_subjects = {root_job["job_id"]}
        if first is not None:
            measured_subjects.add(first[2]["job_id"])
        observed_terminal = any(
            event["event_type"] in (*terminal_types.values(), "JOB_COMPLETED")
            and event["job_id"] in measured_subjects
            for read in evidence.reads.values() if read["record"] is not None
            for event in ([read["record"]] if read["reader"] == _FULL
                          else read["record"] if read["reader"] == _EVENTS else [])
        )
        # Already-validated Job projections cannot be hidden by a favorable
        # lifecycle selector. A current snapshot cannot date a terminal state
        # at cutoff; only the declared subject and measured jobs are relevant.
        snapshot_subjects = measured_subjects | {subject}
        observed_terminal_snapshot = any(
            job["job_id"] in snapshot_subjects
            and job["status"] in ("FAILED", "CANCELLED", "LOST", "COMPLETED")
            for read in evidence.reads.values() if read["record"] is not None
            for job in ([read["record"]] if read["reader"] == _JOB
                        else read["record"] if read["reader"] == _JOBS else [])
        )
        _require(not terminals and not observed_terminal and not observed_terminal_snapshot,
                 "OUTCOME_AT_CUTOFF_UNKNOWN", "UNKNOWN")
        return None
    if outcome == "UNKNOWN":
        raise _Refusal("OUTCOME_AT_CUTOFF_UNKNOWN", "UNKNOWN")
    expected_type = terminal_types.get(outcome, "JOB_COMPLETED")
    matching = [(event, ms) for event, ms in terminals
                if event["job_id"] == subject and event["event_type"] == expected_type]
    _require(bool(matching), "OUTCOME_AT_CUTOFF_UNKNOWN", "UNKNOWN")
    for event, ms in matching:
        if event["event_type"] == "JOB_FAILED" and event["attempt_id"] is not None:
            claimed = any(r["reader"] == _FULL and r["record"] is not None
                          and r["record"]["event_type"] == "JOB_CLAIMED"
                          and r["record"]["attempt_id"] == event["attempt_id"]
                          and r["record"]["job_id"] == event["job_id"]
                          and r["record"]["event_id"] < event["event_id"] for r in evidence.reads.values())
            _require(claimed, "TERMINAL_ATTEMPT_CLAIM_MISSING", "MISSING")
        if first is not None:
            before_id, before_ms = event["event_id"] < first[0]["event_id"], ms < first[1]
            _require(not (before_id != before_ms and ms != first[1]), "TERMINAL_CLOCK_ORDER_CONFLICT")
        if subject == root_job["job_id"] and ms <= cutoff and (first is None or event["event_id"] < first[0]["event_id"]):
            return {"FAILED": "FAILED_BEFORE_CLAIM", "CANCELLED": "CANCELLED_BEFORE_CLAIM",
                    "LOST": "LOST_BEFORE_CLAIM", "TERMINAL_OTHER": "TERMINAL_WITHOUT_CLAIM"}[outcome]
    return None


def _member(evidence, member, key):
    result = _member_result(key, member["lifecycle_outcome"], member["lifecycle_subject_job_id"])
    try:
        if member["decision"] in ("REJECTED", "NOT_APPLICABLE"):
            _require(member["decision_evidence_ref"] is not None and bool(member["reason"]),
                     "ADMISSION_DECISION_UNPROVEN", "UNKNOWN")
            _mark(result, member["reason"], member["decision"])
            return result
        _require(member["decision"] == "ACCEPTED", "ADMISSION_DECISION_UNPROVEN", "UNKNOWN")
        start, start_ms, root_job = _root(evidence, member)
        pairs = [(candidate, _pair(evidence, candidate["claim"], "CLAIM")) for candidate in member["claim_candidates"]]
        if pairs:
            first_pair = min((pair for _, pair in pairs), key=lambda pair: pair[0]["event_id"])
            result["raw_difference_ms"] = first_pair[1] - start_ms
        claims = [_claim(evidence, candidate, start, root_job, pair) for candidate, pair in pairs]
        first = min(claims, key=lambda item: item[0]["event_id"]) if claims else None
        if result["raw_difference_ms"] is not None:
            _require(result["raw_difference_ms"] >= 0, "RECORDED_CLOCK_REVERSED")
        inventory, run = evidence.c["inventory"], evidence.c["run"]
        _require(inventory["coverage"] == "COMPLETE" and _closure(evidence, inventory["closure_ref"]),
                 "INVENTORY_COVERAGE_UNKNOWN", "UNKNOWN")
        clock = run["clock"]
        _require(clock["comparability"] == "SUPPORTED_RECORDED_BASIS" and clock["basis_ref"] is not None
                 and clock["interpretation_ref"] is not None, "CLOCK_BASIS_UNPROVEN", "UNKNOWN")
        cutoff = run["cutoff"]["recorded_at_ms"]
        _require(cutoff is not None and run["cutoff"]["basis_ref"] is not None, "CUTOFF_UNSELECTED", "ACTIVE")
        _require(cutoff >= start_ms, "CUTOFF_PRECEDES_START")
        _require(_closure(evidence, run["cutoff"]["closure_ref"]), "CUTOFF_CLOSURE_UNPROVEN", "UNKNOWN")
        children = _coverage(evidence, member, root_job, claims, cutoff)
        terminal = _terminal(evidence, member, root_job, children, start, start_ms, first, cutoff)
        if terminal:
            _mark(result, "COMPETING_TERMINAL_BEFORE_CLAIM", terminal)
        elif first is None:
            _mark(result, "NO_POINT_ENDPOINT", "RIGHT_CENSORED")
            result["right_censor_lower_bound_ms"] = cutoff - start_ms
        elif first[1] > cutoff:
            # Event-ID firstness is not a timestamp watermark. A later append
            # carrying a pre-cutoff claim contradicts the alleged no-claim cut,
            # even when a generic closure assumption includes both Events.
            _require(all(milliseconds > cutoff for _, milliseconds, _ in claims),
                     "CUTOFF_CLOSURE_UNPROVEN", "UNKNOWN")
            _mark(result, "FIRST_CLAIM_AFTER_CUTOFF", "RIGHT_CENSORED_AT_CUTOFF")
            result["right_censor_lower_bound_ms"] = cutoff - start_ms
        else:
            result["state"] = "COMPLETE_RECORDED_INTERVAL"
            result["recorded_delta_ms"] = first[1] - start_ms
            result["root_weight"] = 1
    except _Refusal as exc:
        _mark(result, exc.reason, exc.state)
        if exc.reason == "OUTCOME_AT_CUTOFF_UNKNOWN":
            result["outcome_retained"] = "UNKNOWN"
    return result


def _census(evidence):
    """Census all immutable projections before a single group can contribute."""
    events, commands, milliseconds, jobs, mutable, attempts, receipts = {}, {}, {}, {}, {}, {}, {}
    conflicting_commands, conflicting_jobs = set(), set()
    for read in evidence.reads.values():
        record, reader = read["record"], read["reader"]
        if record is None:
            continue
        for event in ([record] if reader == _FULL else record if reader == _EVENTS else []):
            for index, key in ((events, event["event_id"]), (commands, event["command_id"])):
                if key in index and not _same(index[key], event):
                    conflicting_commands.update((event["command_id"], index[key]["command_id"]))
                    conflicting_jobs.update((event["job_id"], index[key]["job_id"]))
                else:
                    index[key] = event
        if reader == _MS:
            command = read["arguments"]["command_id"]
            if command in milliseconds and not _same(milliseconds[command], record):
                conflicting_commands.add(command)
                conflicting_jobs.update((record["job_id"], milliseconds[command]["job_id"]))
            else:
                milliseconds[command] = record
        if reader in (_ATTEMPT, _RECEIPT):
            if reader == _ATTEMPT:
                index, identity_key = attempts, "attempt_id"
                fields = ("attempt_id", "job_id", "attempt_number", "worker_id", "quota_class",
                          "fence_generation", "authority_policy_hash", "effective_grant_digest",
                          "placement_snapshot_digest")
            else:
                index, identity_key = receipts, "intent_id"
                fields = ("schema", "intent_id", "fingerprint", "job_id", "accepted", "created_at_ms",
                          "authority", "grounding")
            identity = {key: record[key] for key in fields if key in record}
            key = record[identity_key]
            if key in index and not _same(index[key], identity):
                conflicting_jobs.update((record["job_id"], index[key]["job_id"]))
            else:
                index[key] = identity
        for job in ([record] if reader == _JOB else record if reader == _JOBS else []):
            identity = {key: job[key] for key in _JOB_IMMUTABLE}
            key = job["job_id"]
            if key in jobs and not _same(jobs[key], identity):
                conflicting_jobs.add(key)
            else:
                jobs[key] = identity
            group = (key, read["observation"]["read_group"])
            snapshot = {key: job[key] for key in ("status", "current_attempt_id")}
            if group in mutable and not _same(mutable[group], snapshot):
                conflicting_jobs.add(job["job_id"])
            else:
                mutable[group] = snapshot
    groups = {}
    roots = {}
    for member in evidence.c["inventory"]["members"]:
        read = evidence.reads.get(member["root_admission"]["full_read"])
        event = read["record"] if read and read["reader"] == _FULL else None
        command = event["command_id"] if event else "ceo-intent:" + member["intent_id"]
        job_id = event["job_id"] if event else None
        groups.setdefault(command, []).append((member, event))
        if job_id is not None:
            roots.setdefault(job_id, set()).add(command)
    for job_id, root_commands in roots.items():
        if len(root_commands) > 1:
            conflicting_jobs.add(job_id)
    return groups, conflicting_commands, conflicting_jobs


def _reduce(evidence, output):
    groups, conflicting_commands, conflicting_jobs = _census(evidence)
    inventory = evidence.c["inventory"]
    if inventory["coverage"] == "COMPLETE" and _closure(evidence, inventory["closure_ref"]):
        output["inventory_population"] = len(groups)
    results = []
    for command, group in sorted(groups.items()):
        # Deterministic selection here is only for the diagnostic shell; conflicts
        # are adjudicated over the WHOLE group before this representative is used.
        group = sorted(group, key=lambda item: _canonical(item[0]))
        member, event = group[0]
        job_id = event["job_id"] if event else None
        key = (evidence.c["source"]["runtime_instance_epoch"] + "|" + command + "|" + job_id
               if job_id is not None else None)
        identities = {(m["fingerprint"], e["event_id"] if e else None, e["job_id"] if e else None,
                       m["decision"]) for m, e in group}
        admitted = any(_known_admission(evidence, m) for m, _ in group)
        output["known_admitted_roots"] += int(admitted)
        used_jobs = {job_id}
        for m, _ in group:
            for candidate in m["claim_candidates"]:
                read = evidence.reads.get(candidate["job_read"])
                if read and read["reader"] == _JOB and read["record"]:
                    used_jobs.add(read["record"]["job_id"])
        if len(identities) != 1 or command in conflicting_commands or used_jobs & conflicting_jobs:
            result = _member_result(key, member["lifecycle_outcome"], member["lifecycle_subject_job_id"])
            _mark(result, "REPLAY_CONFLICT")
        else:
            # Exact replay duplicates are collapsed before semantic work; distinct
            # observations must agree rather than choosing the favorable replay.
            unique = {_canonical(m): m for m, _ in group}
            reduced = [_member(evidence, m, key) for _, m in sorted(unique.items())]
            result = reduced[0]
            if any(not _same(result, other) for other in reduced[1:]):
                result = _member_result(key, member["lifecycle_outcome"], member["lifecycle_subject_job_id"])
                _mark(result, "REPLAY_OBSERVATION_CONFLICT", "UNKNOWN")
        results.append(result)
    output["member_results"] = sorted(results, key=lambda m: (m["observation_key"] or "", _canonical(m)))
    values = sorted(m["recorded_delta_ms"] for m in results if m["root_weight"] == 1)
    count = len(values)
    output["completed_recorded_intervals"] = count
    output["distinct_contributing_roots"] = count
    if count:
        output["completed_sample_quantiles_ms"].update(
            p50=values[(50 * count + 99) // 100 - 1],
            p95=values[(95 * count + 99) // 100 - 1], max=values[-1])
        if all(m["state"] not in ("INVALID", "MISSING", "UNKNOWN", "ACTIVE") for m in results):
            output["derivation_status"] = ("SYNTHETIC_DERIVATION_ONLY" if evidence.c["evidence_class"] == "SYNTHETIC"
                                           else "DERIVED_NOT_ADJUDICATED")
    _order(output)


def reduce_first_stratum(
    capsule_bytes: bytes,
    artifact_bytes_by_uri: dict[str, bytes],
    *,
    trusted_manifest_bytes: bytes | None,
    expected_trusted_manifest_sha256: str | None,
) -> dict[str, object]:
    """Reduce only supplied, externally anchored evidence into inert diagnostics.

    Limits are 16 MiB capsule, 1 MiB manifest, 4 MiB per artifact, 64 MiB
    aggregate artifacts, depth 64 and one million decoded JSON value nodes.
    The artifact map must be an exact built-in dict with exact str keys and
    bytes values; arbitrary container and entry protocols are not invoked.
    Resource/decoding/shape refusals precede trust and all contributions. No
    filesystem, network, clock, Runtime or provider is accessed by this function.
    """
    # An invalid Python argument has no input bytes to hash; it cannot recover an
    # observation. For the specified bytes interface, the digest always covers
    # exactly the caller's original bytes, including whitespace.
    output = _output(capsule_bytes if type(capsule_bytes) is bytes else b"")
    try:
        _require(type(capsule_bytes) is bytes and type(artifact_bytes_by_uri) is dict, "INPUT_ARGUMENT_TYPE")
        _require(len(capsule_bytes) <= 16 * _MIB, "INPUT_RESOURCE_LIMIT")
        if trusted_manifest_bytes is not None:
            _require(type(trusted_manifest_bytes) is bytes, "TRUST_ANCHOR_MISMATCH")
            _require(len(trusted_manifest_bytes) <= _MIB, "INPUT_RESOURCE_LIMIT")
        artifacts = {}
        total = 0
        for uri, raw in artifact_bytes_by_uri.items():
            _require(_text(uri) and type(raw) is bytes, "INPUT_ARGUMENT_TYPE")
            total += len(raw)
            _require(len(raw) <= 4 * _MIB and total <= 64 * _MIB, "INPUT_RESOURCE_LIMIT")
            artifacts[uri] = raw
        remaining = [1_000_000]
        capsule = _decode(capsule_bytes, remaining)
        decoded = {uri: _decode(raw, remaining) for uri, raw in artifacts.items()}
        manifest = _decode(trusted_manifest_bytes, remaining) if trusted_manifest_bytes is not None else None
        try:
            _capsule_shape(capsule)
        except _Refusal as exc:
            if exc.reason == "DRAFT_ACCEPTED_BUDGET_FORBIDDEN":
                _metadata(output, capsule)
                if capsule["evidence_class"] == "SYNTHETIC" or any(
                        _object(value) and value.get("synthetic") is True for value in decoded.values()):
                    output["reason_codes"].append("SYNTHETIC_INPUT")
                member = _member_result()
                _mark(member, exc.reason)
                output["member_results"] = [member]
                return output
            raise
        _metadata(output, capsule)
        synthetic = capsule["evidence_class"] == "SYNTHETIC" or any(
            _object(value) and value.get("synthetic") is True for value in decoded.values())
        if synthetic:
            output["reason_codes"].append("SYNTHETIC_INPUT")
        # The accepted unselected template asserts no observations and makes no
        # trust claim. Preserve its original absence diagnostics before anchoring.
        run = capsule["run"]
        if (not capsule["inventory"]["members"] and not capsule["reads"]
                and run["cohort_id"] is None and run["work_class"] is None
                and capsule["source"]["runtime_instance_epoch"] is None):
            output["reason_codes"].extend(("OPERATIONAL_PARAMETERS_UNSELECTED", "INVENTORY_COVERAGE_UNKNOWN"))
            return output
        _require(trusted_manifest_bytes is not None and expected_trusted_manifest_sha256 is not None,
                 "TRUST_ANCHOR_UNAVAILABLE")
        _manifest_check(capsule, capsule_bytes, manifest, trusted_manifest_bytes, expected_trusted_manifest_sha256)
        evidence = _Evidence(capsule, artifacts, decoded)
        evidence.validate()
        _metadata(output, capsule, evidence_validated=True)
        if evidence.synthetic:
            synthetic = True
            if "SYNTHETIC_INPUT" not in output["reason_codes"]:
                output["reason_codes"].append("SYNTHETIC_INPUT")
        if capsule["evidence_class"] != manifest["evidence_class"] or (synthetic and capsule["evidence_class"] != "SYNTHETIC"):
            result = _member_result()
            # Diagnostic arithmetic alone is retained for the accepted laundering
            # discriminator, after byte anchoring and complete pair validation.
            try:
                member = capsule["inventory"]["members"][0]
                _, start_ms = _pair(evidence, member["root_admission"], "ROOT")
                pairs = [_pair(evidence, c["claim"], "CLAIM") for c in member["claim_candidates"]]
                if pairs:
                    result["raw_difference_ms"] = min(pairs, key=lambda pair: pair[0]["event_id"])[1] - start_ms
            except (IndexError, _Refusal):
                pass
            _mark(result, "SYNTHETIC_PROVENANCE_LAUNDERING")
            output["member_results"] = [result]
            _order(output)
            return output
        _require(bool(run["cohort_id"]) and bool(run["work_class"])
                 and bool(capsule["source"]["runtime_instance_epoch"]), "OPERATIONAL_PARAMETERS_UNSELECTED", "UNKNOWN")
        _require(all(ref is not None for ref in (capsule["source"]["instance_binding_ref"],
                     run["environment_ref"], run["protocol_ref"], run["operation_authority_ref"])),
                 "OPERATION_AUTHORITY_UNPROVEN", "UNKNOWN")
        _reduce(evidence, output)
    except _Refusal as exc:
        # No aggregate survives a call-level refusal, including any late resource
        # exception. Only validated metadata and the exact raw input digest remain.
        output["reason_codes"].append(exc.reason)
        output["derivation_status"] = "HOLD_UNSUPPORTED"
        output["inventory_population"] = None
        output["known_admitted_roots"] = 0
        output["completed_recorded_intervals"] = output["distinct_contributing_roots"] = 0
        output["member_results"] = []
        output["completed_sample_quantiles_ms"].update(p50=None, p95=None, max=None)
    except (RecursionError, MemoryError):
        output = _output(capsule_bytes)
        output["reason_codes"].append("INPUT_RESOURCE_LIMIT")
    return output
