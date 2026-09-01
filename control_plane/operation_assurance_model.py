"""control_plane.operation_assurance_model — OLS-A1 closed model parser (OLS-F0).

Implements the strict parser, cross-reference validator, and canonical
identity for one authored ``mastermind.operation_assurance_model.v1``
document, per the controlling OLS-A1 sources in this exact precedence order:

1. docs/superpowers/specs/2026-08-31-operation-assurance-a1-wire-release-finalization.md
2. docs/superpowers/specs/2026-08-30-operation-assurance-immutable-report-projection-clarification.md
3. docs/superpowers/specs/2026-08-30-operation-assurance-model-fidelity-counterexample-validation-amendment.md
4. docs/superpowers/specs/2026-08-30-operation-assurance-a1-trusted-input-total-proof-clarification.md
5. docs/superpowers/specs/2026-08-30-operation-assurance-a1-controlling-execution-overlay.md
6. docs/superpowers/plans/2026-08-30-operation-assurance-core.md

Purity boundary (OLS-A1 no-rebuild law)
----------------------------------------
This module performs **zero** network, socket, subprocess, telemetry,
filesystem-write, SQLite, or runtime I/O. It is standard-library only and
import-safe: importing it has no side effect.

Trust ceiling
-------------
A1 invocation authority is fixed to ``AUTHORED_INPUT``. This module never
promotes a caller-supplied compiler name, freshness label, validation kind,
validation ref, or source ref to trusted evidence — see
``source_applicability_at_generation`` composition in
``operation_assurance_checker``, which normalizes every authored positive
label back down to the A1 ceiling.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# Hard resource ceilings (plan Section 7)
# ---------------------------------------------------------------------------

MAX_INPUT_BYTES = 4_194_304
MAX_JSON_DEPTH = 64
MAX_TOTAL_JSON_NODES = 200_000
MAX_TEXT_CHARS = 4096
MAX_TOKEN_CHARS = 128
MAX_STATE_VARIABLES = 128
MAX_DOMAIN_VALUES_PER_VARIABLE = 128
MAX_TOP_LEVEL_COLLECTION_ITEMS = 2048
MAX_NESTED_COLLECTION_ITEMS = 256
MAX_GUARDS_PER_OBJECT = 128
MAX_EFFECTS_PER_TRANSITION = 128
MAX_EXPLORATION_STATES = 1_000_000
MAX_EXPLORATION_DEPTH = 100_000

SCHEMA = "mastermind.operation_assurance_model.v1"
PROPERTY_SET = "mastermind.operation_assurance.properties.v1"

_CANONICAL_TOKEN_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_STABLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:/_-]{0,127}$")
_SOURCE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.:/_@-]{0,127}$")

GENERIC_MANDATORY_PROPERTY_IDS = frozenset(
    {
        "OPTION_TO_COMPLETE",
        "PROPER_COMPLETION",
        "NO_DEAD_REQUIRED_TRANSITION",
        "NO_POST_TERMINAL_TRANSITION",
        "GATE_OR_WAIT_RETURN_PATH_VALID",
        "UNIVERSAL_PROGRESS",
        "RECURRING_PROGRESS_VALID",
        "NO_STARVATION_UNDER_DECLARED_FAIRNESS",
        "FAIRNESS_REALIZABLE",
    }
)

_ABSTRACTION_KINDS = frozenset(
    {
        "DECLARED_EXACT",
        "SOUND_OVERAPPROXIMATION",
        "TRACE_BACKED_UNDERAPPROXIMATION",
        "HEURISTIC_ABSTRACTION",
        "UNKNOWN_FIDELITY",
    }
)
_PRESERVES = frozenset(
    {
        "SAFETY",
        "REACHABLE_COUNTEREXAMPLE",
        "OPTION_TO_COMPLETE",
        "UNIVERSAL_PROGRESS",
        "LIVENESS_UNDER_DECLARED_FAIRNESS",
        "RESOURCE_OWNERSHIP",
        "EFFECT_RETRY_SAFETY",
    }
)
_INTRO_EXCLUDED = frozenset({"NONE_DECLARED", "MAY_EXIST", "KNOWN_PRESENT", "UNKNOWN"})
_VALIDATION_KINDS = frozenset(
    {
        "AUTHOR_DECLARATION",
        "SOURCE_COMPILER_ATTESTATION",
        "SOURCE_CONTRACT_REPLAY",
        "RUNTIME_EVENT_REPLAY",
        "INDEPENDENT_FORMAL_EQUIVALENCE",
        "NONE",
    }
)
_FRESHNESS = frozenset({"FRESH", "STALE", "UNKNOWN"})
_CONFLICT = frozenset({"NONE", "CONFLICT", "UNKNOWN"})
_COVERAGE = frozenset({"COMPLETE", "PARTIAL", "UNKNOWN"})
_GUARD_OPS = frozenset({"EQ", "NEQ", "IN", "NOT_IN"})
_GATE_DISPOSITIONS = frozenset({"EXTERNAL_GATE", "INTENTIONAL_WAIT"})
_TERMINAL_KINDS = frozenset(
    {"TERMINAL_SUCCESS", "TERMINAL_REFUSAL", "TERMINAL_CANCELLED", "TERMINAL_FAILED_SAFE"}
)
_RECURRING_KIND = "RECURRING_PROGRESS"
_SAFETY_KINDS = frozenset({"STATE_FORBIDDEN", "TRANSITION_FORBIDDEN"})
_FAIRNESS_KIND = "WEAK"


class ModelParseError(ValueError):
    """A closed model document is refused. Carries a stable reason code and path."""

    def __init__(self, reason_code: str, message: str, path: str = ""):
        self.reason_code = reason_code
        self.path = path
        super().__init__(f"{reason_code} at {path or '<root>'}: {message}")


def _fail(reason_code: str, message: str, path: str = "") -> "ModelParseError":
    return ModelParseError(reason_code, message, path)


# ---------------------------------------------------------------------------
# Canonical JSON + hashing
# ---------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Strict JSON loading
# ---------------------------------------------------------------------------


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    seen: dict[str, Any] = {}
    for key, val in pairs:
        if key in seen:
            raise _fail("DUPLICATE_JSON_KEY", f"duplicate key {key!r}")
        seen[key] = val
    return seen


def _reject_non_finite(_token: str) -> float:
    raise _fail("NON_FINITE_NUMBER", "NaN/Infinity/-Infinity are not valid OLS-A1 JSON")


def _strict_loads(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except ModelParseError:
        raise
    except json.JSONDecodeError as exc:
        raise _fail("MALFORMED_JSON", str(exc)) from exc


def _walk_limits(node: Any, depth: int, counter: list[int]) -> None:
    counter[0] += 1
    if counter[0] > MAX_TOTAL_JSON_NODES:
        raise _fail("TOO_MANY_JSON_NODES", "input exceeds MAX_TOTAL_JSON_NODES")
    if depth > MAX_JSON_DEPTH:
        raise _fail("JSON_TOO_DEEP", "input exceeds MAX_JSON_DEPTH")
    if isinstance(node, dict):
        for v in node.values():
            _walk_limits(v, depth + 1, counter)
    elif isinstance(node, list):
        for v in node:
            _walk_limits(v, depth + 1, counter)
    elif isinstance(node, str):
        if len(node) > MAX_TEXT_CHARS:
            raise _fail("TEXT_TOO_LONG", "string exceeds MAX_TEXT_CHARS")


def parse_model_bytes(raw: bytes) -> "OperationAssuranceModel":
    if len(raw) > MAX_INPUT_BYTES:
        raise _fail("INPUT_TOO_LARGE", "input exceeds MAX_INPUT_BYTES")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise _fail("BYTE_ORDER_MARK", "UTF-8 byte-order mark is not accepted")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _fail("INVALID_UTF8", str(exc)) from exc
    return parse_model_text(text)


def parse_model_text(text: str) -> "OperationAssuranceModel":
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise _fail("INPUT_TOO_LARGE", "input exceeds MAX_INPUT_BYTES")
    stripped = text.strip()
    if not stripped:
        raise _fail("EMPTY_INPUT", "input is empty")
    doc = _strict_loads(text)
    # reject trailing non-whitespace: json.loads already requires the whole
    # string to parse as exactly one value, so trailing garbage after a
    # complete JSON value is only reachable via json.JSONDecodeError, which
    # _strict_loads already turns into ModelParseError. Nothing further here.
    if not isinstance(doc, dict):
        raise _fail("TOP_LEVEL_NOT_OBJECT", "top-level JSON value must be an object")
    _walk_limits(doc, 0, [0])
    return _parse_model_doc(doc)


# ---------------------------------------------------------------------------
# Immutable value objects
# ---------------------------------------------------------------------------


def _dc_to_dict(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {f.name: _dc_to_dict(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return [_dc_to_dict(v) for v in value]
    return value


@dataclasses.dataclass(frozen=True)
class OperationRef:
    operation_key: str
    root_job_id: str | None
    pre_admission_identity: str | None


@dataclasses.dataclass(frozen=True)
class Compiler:
    name: str
    version: str
    invocation_mode: str


@dataclasses.dataclass(frozen=True)
class SourceRecord:
    owner: str
    source_kind: str
    source_identity: str
    schema_version: str
    digest: str
    effective_at: str | None
    observed_at: str | None
    correction_ref: str | None
    freshness: str
    conflict: str
    coverage: str
    truncated: bool
    continuation: str | None


@dataclasses.dataclass(frozen=True)
class SourceSnapshot:
    schema: str
    sources: tuple[SourceRecord, ...]
    snapshot_hash: str


@dataclasses.dataclass(frozen=True)
class AbstractionContract:
    kind: str
    concrete_scope: str
    preserves: tuple[str, ...]
    introduced_behavior: str
    excluded_behavior: str
    validation_kind: str
    validation_refs: tuple[str, ...]
    notes: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Guard:
    variable: str
    op: str
    value: Any  # str for EQ/NEQ, tuple[str, ...] for IN/NOT_IN


@dataclasses.dataclass(frozen=True)
class Effect:
    variable: str
    value: str


@dataclasses.dataclass(frozen=True)
class Transition:
    transition_id: str
    kind: str
    actor_class: str
    authority_requirement: str
    guards: tuple[Guard, ...]
    effects: tuple[Effect, ...]
    progress_tags: tuple[str, ...]
    source_refs: tuple[str, ...]
    fairness_ref: str | None
    external_assumption_ref: str | None
    gate_refs: tuple[str, ...]
    required_reachable: bool


@dataclasses.dataclass(frozen=True)
class Outcome:
    outcome_id: str
    kind: str
    guards: tuple[Guard, ...]
    owned_persistent_obligation_ids: tuple[str, ...]
    owned_persistent_resource_ids: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Obligation:
    obligation_id: str
    kind: str
    state_variable: str
    pending_values: tuple[str, ...]
    discharged_values: tuple[str, ...]
    persistent: bool
    owner_or_authority: str
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Resource:
    resource_id: str
    holder_variable: str
    released_values: tuple[str, ...]
    persistent: bool
    owner_or_authority: str
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Gate:
    gate_id: str
    disposition: str
    state_guards: tuple[Guard, ...]
    owner_or_authority: str
    release_condition: str
    release_transition_ids: tuple[str, ...]
    return_or_observation_source: str
    wake_or_review_path: str
    time_contract: str
    correction_contract: str
    escalation_or_close_path: str
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class FairnessAssumption:
    fairness_id: str
    kind: str
    transition_ids: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class EnvironmentAssumption:
    assumption_id: str
    kind: str
    transition_ids: tuple[str, ...]
    required_for_property_ids: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class SafetyProperty:
    property_id: str
    kind: str
    violation_when: tuple[Guard, ...] | None
    when: tuple[Guard, ...] | None
    forbidden_transition_kinds: tuple[str, ...] | None
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class ModelGap:
    gap_id: str
    reason: str
    load_bearing: bool
    affects_property_ids: tuple[str, ...]
    affects_transition_ids: tuple[str, ...]
    affects_variable_ids: tuple[str, ...]
    source_refs: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class ExplorationLimits:
    max_states: int
    max_depth: int


@dataclasses.dataclass(frozen=True)
class OperationAssuranceModel:
    schema: str
    model_id: str
    operation_ref: OperationRef
    compiler: Compiler
    source_snapshot: SourceSnapshot
    abstraction_contract: AbstractionContract
    state_domains: tuple[tuple[str, tuple[str, ...]], ...]
    initial_state: tuple[tuple[str, str], ...]
    transitions: tuple[Transition, ...]
    terminal_outcomes: tuple[Outcome, ...]
    recurring_progress_outcomes: tuple[Outcome, ...]
    obligations: tuple[Obligation, ...]
    resources: tuple[Resource, ...]
    external_gates: tuple[Gate, ...]
    fairness_assumptions: tuple[FairnessAssumption, ...]
    environment_assumptions: tuple[EnvironmentAssumption, ...]
    safety_properties: tuple[SafetyProperty, ...]
    property_set: str
    exploration_limits: ExplorationLimits
    known_model_gaps: tuple[ModelGap, ...]
    model_hash: str

    def domains_dict(self) -> dict[str, tuple[str, ...]]:
        return dict(self.state_domains)

    def initial_state_dict(self) -> dict[str, str]:
        return dict(self.initial_state)

    def to_dict(self) -> dict:
        out = {
            "schema": self.schema,
            "model_id": self.model_id,
            "operation_ref": _dc_to_dict(self.operation_ref),
            "compiler": _dc_to_dict(self.compiler),
            "source_snapshot": _dc_to_dict(self.source_snapshot),
            "abstraction_contract": _dc_to_dict(self.abstraction_contract),
            "state_domains": {k: list(v) for k, v in self.state_domains},
            "initial_state": dict(self.initial_state),
            "transitions": [_dc_to_dict(t) for t in self.transitions],
            "terminal_outcomes": [_dc_to_dict(o) for o in self.terminal_outcomes],
            "recurring_progress_outcomes": [_dc_to_dict(o) for o in self.recurring_progress_outcomes],
            "obligations": [_dc_to_dict(o) for o in self.obligations],
            "resources": [_dc_to_dict(r) for r in self.resources],
            "external_gates": [_dc_to_dict(g) for g in self.external_gates],
            "fairness_assumptions": [_dc_to_dict(f) for f in self.fairness_assumptions],
            "environment_assumptions": [_dc_to_dict(a) for a in self.environment_assumptions],
            "safety_properties": [_safety_property_to_dict(p) for p in self.safety_properties],
            "property_set": self.property_set,
            "exploration_limits": _dc_to_dict(self.exploration_limits),
            "known_model_gaps": [_dc_to_dict(g) for g in self.known_model_gaps],
        }
        return out


def _safety_property_to_dict(p: SafetyProperty) -> dict:
    if p.kind == "STATE_FORBIDDEN":
        return {
            "property_id": p.property_id,
            "kind": p.kind,
            "violation_when": [_dc_to_dict(g) for g in (p.violation_when or ())],
            "source_refs": list(p.source_refs),
        }
    return {
        "property_id": p.property_id,
        "kind": p.kind,
        "when": [_dc_to_dict(g) for g in (p.when or ())],
        "forbidden_transition_kinds": list(p.forbidden_transition_kinds or ()),
        "source_refs": list(p.source_refs),
    }


# ---------------------------------------------------------------------------
# Field-level scalar validators
# ---------------------------------------------------------------------------


def _require_dict(value: Any, path: str) -> dict:
    if not isinstance(value, dict):
        raise _fail("EXPECTED_OBJECT", "expected a JSON object", path)
    return value


def _require_list(value: Any, path: str, *, max_items: int = MAX_NESTED_COLLECTION_ITEMS) -> list:
    if not isinstance(value, list):
        raise _fail("EXPECTED_ARRAY", "expected a JSON array", path)
    if len(value) > max_items:
        raise _fail("COLLECTION_TOO_LARGE", "array exceeds its item ceiling", path)
    return value


def _require_str(value: Any, path: str, *, max_len: int = MAX_TEXT_CHARS) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise _fail("EXPECTED_STRING", "expected a string", path)
    if not value:
        raise _fail("EMPTY_STRING", "string must be non-empty", path)
    if len(value) > max_len:
        raise _fail("STRING_TOO_LONG", "string exceeds its length ceiling", path)
    if value != value.strip():
        raise _fail("NON_CANONICAL_TEXT", "leading/trailing whitespace is not accepted", path)
    for ch in value:
        if ord(ch) < 0x20:
            raise _fail("NON_CANONICAL_TEXT", "C0 control characters are not accepted", path)
    import unicodedata

    if unicodedata.normalize("NFC", value) != value:
        raise _fail("NON_CANONICAL_TEXT", "text must already be Unicode NFC", path)
    return value


def _require_opt_str(value: Any, path: str, *, max_len: int = MAX_TEXT_CHARS) -> str | None:
    if value is None:
        return None
    return _require_str(value, path, max_len=max_len)


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise _fail("EXPECTED_BOOLEAN", "expected a boolean", path)
    return value


def _require_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail("EXPECTED_INTEGER", "expected a non-boolean integer", path)
    return value


def _require_token(value: Any, path: str) -> str:
    s = _require_str(value, path, max_len=MAX_TOKEN_CHARS)
    if not _CANONICAL_TOKEN_RE.match(s):
        raise _fail("BAD_TOKEN", "expected a canonical token [A-Z][A-Z0-9_]*", path)
    return s


def _require_id(value: Any, path: str) -> str:
    s = _require_str(value, path, max_len=MAX_TOKEN_CHARS)
    if not _STABLE_ID_RE.match(s):
        raise _fail("BAD_ID", "expected a canonical stable id", path)
    return s


def _require_source_ref(value: Any, path: str) -> str:
    s = _require_str(value, path, max_len=MAX_TOKEN_CHARS)
    if not _SOURCE_REF_RE.match(s):
        raise _fail("BAD_SOURCE_REF", "expected a canonical source reference token", path)
    return s


def _require_enum(value: Any, path: str, allowed: frozenset) -> str:
    s = _require_str(value, path, max_len=MAX_TOKEN_CHARS)
    if s not in allowed:
        raise _fail("UNKNOWN_ENUM_VALUE", f"{s!r} is not one of {sorted(allowed)}", path)
    return s


def _require_token_list(value: Any, path: str, *, max_items: int = MAX_NESTED_COLLECTION_ITEMS) -> tuple[str, ...]:
    items = _require_list(value, path, max_items=max_items)
    out = []
    for i, v in enumerate(items):
        out.append(_require_token(v, f"{path}[{i}]"))
    if len(set(out)) != len(out):
        raise _fail("DUPLICATE_SET_MEMBER", "duplicate member in a set-like array", path)
    return tuple(sorted(out))


def _require_id_list(value: Any, path: str, *, max_items: int = MAX_NESTED_COLLECTION_ITEMS, sort: bool = True) -> tuple[str, ...]:
    items = _require_list(value, path, max_items=max_items)
    out = []
    for i, v in enumerate(items):
        out.append(_require_id(v, f"{path}[{i}]"))
    if len(set(out)) != len(out):
        raise _fail("DUPLICATE_SET_MEMBER", "duplicate member in a set-like array", path)
    return tuple(sorted(out) if sort else out)


def _require_source_ref_list(value: Any, path: str) -> tuple[str, ...]:
    items = _require_list(value, path, max_items=MAX_NESTED_COLLECTION_ITEMS)
    out = []
    for i, v in enumerate(items):
        out.append(_require_source_ref(v, f"{path}[{i}]"))
    if len(set(out)) != len(out):
        raise _fail("DUPLICATE_SET_MEMBER", "duplicate source ref", path)
    return tuple(sorted(out))


def _check_unknown_keys(d: dict, allowed: frozenset, path: str) -> None:
    unknown = set(d.keys()) - allowed
    if unknown:
        raise _fail("UNKNOWN_FIELD", f"unknown field(s) {sorted(unknown)}", path)


def _require_keys(d: dict, required: frozenset, path: str) -> None:
    missing = required - set(d.keys())
    if missing:
        raise _fail("MISSING_FIELD", f"missing required field(s) {sorted(missing)}", path)


# ---------------------------------------------------------------------------
# Guard parsing (needs domain awareness; resolved in a second pass)
# ---------------------------------------------------------------------------

_GUARD_FIELDS = frozenset({"variable", "op", "value"})


def _parse_guard_raw(d: Any, path: str) -> dict:
    d = _require_dict(d, path)
    _check_unknown_keys(d, _GUARD_FIELDS, path)
    _require_keys(d, _GUARD_FIELDS, path)
    variable = _require_id(d["variable"], f"{path}.variable")
    op = _require_enum(d["op"], f"{path}.op", _GUARD_OPS)
    if op in ("EQ", "NEQ"):
        value: Any = _require_token(d["value"], f"{path}.value")
    else:
        vals = _require_list(d["value"], f"{path}.value", max_items=MAX_DOMAIN_VALUES_PER_VARIABLE)
        if not vals:
            raise _fail("EMPTY_ARRAY", "IN/NOT_IN requires a non-empty value list", f"{path}.value")
        parsed = [_require_token(v, f"{path}.value[{i}]") for i, v in enumerate(vals)]
        if len(set(parsed)) != len(parsed):
            raise _fail("DUPLICATE_SET_MEMBER", "duplicate value in guard list", f"{path}.value")
        value = tuple(parsed)
    return {"variable": variable, "op": op, "value": value}


def _parse_guard_list_raw(value: Any, path: str, *, max_items: int = MAX_GUARDS_PER_OBJECT) -> list[dict]:
    items = _require_list(value, path, max_items=max_items)
    return [_parse_guard_raw(g, f"{path}[{i}]") for i, g in enumerate(items)]


# ---------------------------------------------------------------------------
# Top-level parse
# ---------------------------------------------------------------------------

_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema",
        "model_id",
        "operation_ref",
        "compiler",
        "source_snapshot",
        "abstraction_contract",
        "state_domains",
        "initial_state",
        "transitions",
        "terminal_outcomes",
        "recurring_progress_outcomes",
        "obligations",
        "resources",
        "external_gates",
        "fairness_assumptions",
        "environment_assumptions",
        "safety_properties",
        "property_set",
        "exploration_limits",
        "known_model_gaps",
    }
)


def _parse_model_doc(doc: dict) -> OperationAssuranceModel:
    _check_unknown_keys(doc, _TOP_LEVEL_FIELDS, "")
    _require_keys(doc, _TOP_LEVEL_FIELDS, "")

    schema = _require_str(doc["schema"], "schema")
    if schema != SCHEMA:
        raise _fail("BAD_SCHEMA", f"expected schema {SCHEMA!r}", "schema")
    model_id = _require_id(doc["model_id"], "model_id")

    operation_ref = _parse_operation_ref(doc["operation_ref"])
    compiler = _parse_compiler(doc["compiler"])
    source_snapshot = _parse_source_snapshot(doc["source_snapshot"])
    abstraction_contract = _parse_abstraction_contract(doc["abstraction_contract"])

    state_domains, domain_index = _parse_state_domains(doc["state_domains"])
    initial_state = _parse_initial_state(doc["initial_state"], domain_index)

    property_set = _require_str(doc["property_set"], "property_set", max_len=MAX_TOKEN_CHARS)
    if property_set != PROPERTY_SET:
        raise _fail("BAD_PROPERTY_SET", f"expected property_set {PROPERTY_SET!r}", "property_set")

    exploration_limits = _parse_exploration_limits(doc["exploration_limits"])

    # --- raw parses that need cross-reference resolution ---
    transitions_raw = _parse_transitions_raw(doc["transitions"], domain_index)
    terminal_raw = _parse_outcomes_raw(doc["terminal_outcomes"], "terminal_outcomes", _TERMINAL_KINDS)
    recurring_raw = _parse_outcomes_raw(
        doc["recurring_progress_outcomes"], "recurring_progress_outcomes", frozenset({_RECURRING_KIND})
    )
    obligations_raw = _parse_obligations_raw(doc["obligations"], domain_index)
    resources_raw = _parse_resources_raw(doc["resources"], domain_index)
    gates_raw = _parse_gates_raw(doc["external_gates"], domain_index)
    fairness_raw = _parse_fairness_raw(doc["fairness_assumptions"])
    env_raw = _parse_environment_assumptions_raw(doc["environment_assumptions"])
    safety_raw = _parse_safety_properties_raw(doc["safety_properties"], domain_index)
    gaps_raw = _parse_model_gaps_raw(doc["known_model_gaps"])

    transition_ids = {t["transition_id"] for t in transitions_raw}
    outcome_ids = {o["outcome_id"] for o in terminal_raw} | {o["outcome_id"] for o in recurring_raw}
    obligation_ids = {o["obligation_id"] for o in obligations_raw}
    resource_ids = {r["resource_id"] for r in resources_raw}
    gate_ids = {g["gate_id"] for g in gates_raw}
    fairness_ids = {f["fairness_id"] for f in fairness_raw}
    env_ids = {a["assumption_id"] for a in env_raw}
    all_property_ids = GENERIC_MANDATORY_PROPERTY_IDS | {s["property_id"] for s in safety_raw}
    variable_ids = set(domain_index.keys())

    if len(outcome_ids) != len(terminal_raw) + len(recurring_raw):
        raise _fail("DUPLICATE_ID", "duplicate outcome_id across terminal/recurring outcomes")

    # cross-reference: transitions -> outcomes owned obligations/resources
    for o in terminal_raw + recurring_raw:
        for oid in o["owned_persistent_obligation_ids"]:
            if oid not in obligation_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown obligation_id {oid!r}", f"outcome[{o['outcome_id']}]")
        for rid in o["owned_persistent_resource_ids"]:
            if rid not in resource_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown resource_id {rid!r}", f"outcome[{o['outcome_id']}]")

    # bidirectional fairness references
    fairness_declared_pairs = set()
    for f in fairness_raw:
        for tid in f["transition_ids"]:
            if tid not in transition_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown transition_id {tid!r}", f"fairness_assumptions[{f['fairness_id']}]")
            fairness_declared_pairs.add((f["fairness_id"], tid))
    transition_fairness_pairs = set()
    for t in transitions_raw:
        if t["fairness_ref"] is not None:
            if t["fairness_ref"] not in fairness_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown fairness_ref {t['fairness_ref']!r}", f"transitions[{t['transition_id']}]")
            transition_fairness_pairs.add((t["fairness_ref"], t["transition_id"]))
    if fairness_declared_pairs != transition_fairness_pairs:
        raise _fail("ONE_SIDED_REFERENCE", "fairness_ref and fairness_assumptions.transition_ids must agree exactly")

    # bidirectional environment-assumption references
    env_declared_pairs = set()
    for a in env_raw:
        for tid in a["transition_ids"]:
            if tid not in transition_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown transition_id {tid!r}", f"environment_assumptions[{a['assumption_id']}]")
            env_declared_pairs.add((a["assumption_id"], tid))
        for pid in a["required_for_property_ids"]:
            if pid not in all_property_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown property_id {pid!r}", f"environment_assumptions[{a['assumption_id']}]")
    transition_env_pairs = set()
    for t in transitions_raw:
        if t["external_assumption_ref"] is not None:
            if t["external_assumption_ref"] not in env_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown external_assumption_ref {t['external_assumption_ref']!r}", f"transitions[{t['transition_id']}]")
            transition_env_pairs.add((t["external_assumption_ref"], t["transition_id"]))
    if env_declared_pairs != transition_env_pairs:
        raise _fail("ONE_SIDED_REFERENCE", "external_assumption_ref and environment_assumptions.transition_ids must agree exactly")

    # bidirectional gate <-> transition.gate_refs
    gate_declared_pairs = set()
    for g in gates_raw:
        for tid in g["release_transition_ids"]:
            if tid not in transition_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown transition_id {tid!r}", f"external_gates[{g['gate_id']}]")
            gate_declared_pairs.add((g["gate_id"], tid))
        if g["escalation_or_close_path"] not in g["release_transition_ids"]:
            raise _fail("INVALID_GATE", "escalation_or_close_path must name one of release_transition_ids", f"external_gates[{g['gate_id']}]")
    transition_gate_pairs = set()
    for t in transitions_raw:
        for gid in t["gate_refs"]:
            if gid not in gate_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown gate_id {gid!r}", f"transitions[{t['transition_id']}]")
            transition_gate_pairs.add((gid, t["transition_id"]))
    if gate_declared_pairs != transition_gate_pairs:
        raise _fail("ONE_SIDED_REFERENCE", "gate.release_transition_ids and transition.gate_refs must agree exactly")

    # model gaps: resolve every affected identity
    for g in gaps_raw:
        for pid in g["affects_property_ids"]:
            if pid not in all_property_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown property_id {pid!r}", f"known_model_gaps[{g['gap_id']}]")
        for tid in g["affects_transition_ids"]:
            if tid not in transition_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown transition_id {tid!r}", f"known_model_gaps[{g['gap_id']}]")
        for vid in g["affects_variable_ids"]:
            if vid not in variable_ids:
                raise _fail("UNRESOLVED_REFERENCE", f"unknown variable_id {vid!r}", f"known_model_gaps[{g['gap_id']}]")
        total_affected = (
            len(g["affects_property_ids"]) + len(g["affects_transition_ids"]) + len(g["affects_variable_ids"])
        )
        if total_affected == 0 and g["load_bearing"]:
            raise _fail("INVALID_MODEL_GAP", "a load-bearing gap must affect at least one identity", f"known_model_gaps[{g['gap_id']}]")

    # obligations: state_variable resolves
    for o in obligations_raw:
        if o["state_variable"] not in domain_index:
            raise _fail("UNRESOLVED_REFERENCE", f"unknown variable {o['state_variable']!r}", f"obligations[{o['obligation_id']}]")

    # resources: holder_variable resolves
    for r in resources_raw:
        if r["holder_variable"] not in domain_index:
            raise _fail("UNRESOLVED_REFERENCE", f"unknown variable {r['holder_variable']!r}", f"resources[{r['resource_id']}]")

    if len(state_domains) > MAX_STATE_VARIABLES:
        raise _fail("TOO_MANY_STATE_VARIABLES", "state_domains exceeds MAX_STATE_VARIABLES")

    # --- freeze into dataclasses ---
    transitions = tuple(
        Transition(
            transition_id=t["transition_id"],
            kind=t["kind"],
            actor_class=t["actor_class"],
            authority_requirement=t["authority_requirement"],
            guards=tuple(_freeze_guard(g) for g in t["guards"]),
            effects=tuple(Effect(**e) for e in t["effects"]),
            progress_tags=t["progress_tags"],
            source_refs=t["source_refs"],
            fairness_ref=t["fairness_ref"],
            external_assumption_ref=t["external_assumption_ref"],
            gate_refs=t["gate_refs"],
            required_reachable=t["required_reachable"],
        )
        for t in sorted(transitions_raw, key=lambda x: x["transition_id"])
    )
    terminal_outcomes = tuple(_freeze_outcome(o) for o in sorted(terminal_raw, key=lambda x: x["outcome_id"]))
    recurring_outcomes = tuple(_freeze_outcome(o) for o in sorted(recurring_raw, key=lambda x: x["outcome_id"]))
    obligations = tuple(
        Obligation(
            obligation_id=o["obligation_id"],
            kind=o["kind"],
            state_variable=o["state_variable"],
            pending_values=o["pending_values"],
            discharged_values=o["discharged_values"],
            persistent=o["persistent"],
            owner_or_authority=o["owner_or_authority"],
            source_refs=o["source_refs"],
        )
        for o in sorted(obligations_raw, key=lambda x: x["obligation_id"])
    )
    resources = tuple(
        Resource(
            resource_id=r["resource_id"],
            holder_variable=r["holder_variable"],
            released_values=r["released_values"],
            persistent=r["persistent"],
            owner_or_authority=r["owner_or_authority"],
            source_refs=r["source_refs"],
        )
        for r in sorted(resources_raw, key=lambda x: x["resource_id"])
    )
    gates = tuple(
        Gate(
            gate_id=g["gate_id"],
            disposition=g["disposition"],
            state_guards=tuple(_freeze_guard(x) for x in g["state_guards"]),
            owner_or_authority=g["owner_or_authority"],
            release_condition=g["release_condition"],
            release_transition_ids=g["release_transition_ids"],
            return_or_observation_source=g["return_or_observation_source"],
            wake_or_review_path=g["wake_or_review_path"],
            time_contract=g["time_contract"],
            correction_contract=g["correction_contract"],
            escalation_or_close_path=g["escalation_or_close_path"],
            source_refs=g["source_refs"],
        )
        for g in sorted(gates_raw, key=lambda x: x["gate_id"])
    )
    fairness_assumptions = tuple(
        FairnessAssumption(
            fairness_id=f["fairness_id"],
            kind=f["kind"],
            transition_ids=f["transition_ids"],
            source_refs=f["source_refs"],
        )
        for f in sorted(fairness_raw, key=lambda x: x["fairness_id"])
    )
    environment_assumptions = tuple(
        EnvironmentAssumption(
            assumption_id=a["assumption_id"],
            kind=a["kind"],
            transition_ids=a["transition_ids"],
            required_for_property_ids=a["required_for_property_ids"],
            source_refs=a["source_refs"],
        )
        for a in sorted(env_raw, key=lambda x: x["assumption_id"])
    )
    safety_properties = tuple(_freeze_safety(s) for s in sorted(safety_raw, key=lambda x: x["property_id"]))
    known_model_gaps = tuple(
        ModelGap(
            gap_id=g["gap_id"],
            reason=g["reason"],
            load_bearing=g["load_bearing"],
            affects_property_ids=g["affects_property_ids"],
            affects_transition_ids=g["affects_transition_ids"],
            affects_variable_ids=g["affects_variable_ids"],
            source_refs=g["source_refs"],
        )
        for g in sorted(gaps_raw, key=lambda x: x["gap_id"])
    )

    model = OperationAssuranceModel(
        schema=schema,
        model_id=model_id,
        operation_ref=operation_ref,
        compiler=compiler,
        source_snapshot=source_snapshot,
        abstraction_contract=abstraction_contract,
        state_domains=state_domains,
        initial_state=initial_state,
        transitions=transitions,
        terminal_outcomes=terminal_outcomes,
        recurring_progress_outcomes=recurring_outcomes,
        obligations=obligations,
        resources=resources,
        external_gates=gates,
        fairness_assumptions=fairness_assumptions,
        environment_assumptions=environment_assumptions,
        safety_properties=safety_properties,
        property_set=property_set,
        exploration_limits=exploration_limits,
        known_model_gaps=known_model_gaps,
        model_hash="",
    )
    model_hash = sha256_hex(canonical_json(model.to_dict()))
    return dataclasses.replace(model, model_hash=model_hash)


def _freeze_guard(g: dict) -> Guard:
    value = g["value"]
    return Guard(variable=g["variable"], op=g["op"], value=value)


def _freeze_outcome(o: dict) -> Outcome:
    return Outcome(
        outcome_id=o["outcome_id"],
        kind=o["kind"],
        guards=tuple(_freeze_guard(g) for g in o["guards"]),
        owned_persistent_obligation_ids=o["owned_persistent_obligation_ids"],
        owned_persistent_resource_ids=o["owned_persistent_resource_ids"],
        source_refs=o["source_refs"],
    )


def _freeze_safety(s: dict) -> SafetyProperty:
    if s["kind"] == "STATE_FORBIDDEN":
        return SafetyProperty(
            property_id=s["property_id"],
            kind=s["kind"],
            violation_when=tuple(_freeze_guard(g) for g in s["violation_when"]),
            when=None,
            forbidden_transition_kinds=None,
            source_refs=s["source_refs"],
        )
    return SafetyProperty(
        property_id=s["property_id"],
        kind=s["kind"],
        violation_when=None,
        when=tuple(_freeze_guard(g) for g in s["when"]),
        forbidden_transition_kinds=s["forbidden_transition_kinds"],
        source_refs=s["source_refs"],
    )


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------

_OPERATION_REF_FIELDS = frozenset({"operation_key", "root_job_id", "pre_admission_identity"})


def _parse_operation_ref(d: Any) -> OperationRef:
    d = _require_dict(d, "operation_ref")
    _check_unknown_keys(d, _OPERATION_REF_FIELDS, "operation_ref")
    _require_keys(d, _OPERATION_REF_FIELDS, "operation_ref")
    operation_key = _require_id(d["operation_key"], "operation_ref.operation_key")
    root_job_id = _require_opt_str(d["root_job_id"], "operation_ref.root_job_id", max_len=MAX_TOKEN_CHARS)
    pre_admission_identity = _require_opt_str(
        d["pre_admission_identity"], "operation_ref.pre_admission_identity", max_len=MAX_TOKEN_CHARS
    )
    if (root_job_id is None) == (pre_admission_identity is None):
        raise _fail(
            "INVALID_OPERATION_REF",
            "exactly one of root_job_id/pre_admission_identity must be non-null",
            "operation_ref",
        )
    return OperationRef(operation_key, root_job_id, pre_admission_identity)


_COMPILER_FIELDS = frozenset({"name", "version", "invocation_mode"})


def _parse_compiler(d: Any) -> Compiler:
    d = _require_dict(d, "compiler")
    _check_unknown_keys(d, _COMPILER_FIELDS, "compiler")
    _require_keys(d, _COMPILER_FIELDS, "compiler")
    name = _require_str(d["name"], "compiler.name", max_len=MAX_TOKEN_CHARS)
    version = _require_str(d["version"], "compiler.version", max_len=MAX_TOKEN_CHARS)
    invocation_mode = _require_str(d["invocation_mode"], "compiler.invocation_mode", max_len=MAX_TOKEN_CHARS)
    if invocation_mode != "AUTHORED_INPUT":
        raise _fail("INVALID_INVOCATION_MODE", "OLS-A1 requires invocation_mode=AUTHORED_INPUT", "compiler.invocation_mode")
    return Compiler(name, version, invocation_mode)


_SOURCE_RECORD_FIELDS = frozenset(
    {
        "owner",
        "source_kind",
        "source_identity",
        "schema_version",
        "digest",
        "effective_at",
        "observed_at",
        "correction_ref",
        "freshness",
        "conflict",
        "coverage",
        "truncated",
        "continuation",
    }
)
_SOURCE_SNAPSHOT_FIELDS = frozenset({"schema", "sources", "snapshot_hash"})


def _parse_source_snapshot(d: Any) -> SourceSnapshot:
    d = _require_dict(d, "source_snapshot")
    _check_unknown_keys(d, _SOURCE_SNAPSHOT_FIELDS, "source_snapshot")
    _require_keys(d, _SOURCE_SNAPSHOT_FIELDS, "source_snapshot")
    schema = _require_str(d["schema"], "source_snapshot.schema", max_len=MAX_TOKEN_CHARS)
    sources_raw = _require_list(d["sources"], "source_snapshot.sources", max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    records = []
    identities = set()
    for i, s in enumerate(sources_raw):
        rec = _parse_source_record(s, f"source_snapshot.sources[{i}]")
        if rec.source_identity in identities:
            raise _fail("DUPLICATE_ID", "duplicate source_identity", "source_snapshot.sources")
        identities.add(rec.source_identity)
        records.append(rec)
    records.sort(key=lambda r: r.source_identity)
    body = {"schema": schema, "sources": [_dc_to_dict(r) for r in records]}
    expected_hash = sha256_hex(canonical_json(body))
    snapshot_hash = _require_str(d["snapshot_hash"], "source_snapshot.snapshot_hash", max_len=64)
    if snapshot_hash != expected_hash:
        raise _fail("BAD_SNAPSHOT_HASH", "snapshot_hash does not match recomputed content hash", "source_snapshot.snapshot_hash")
    return SourceSnapshot(schema=schema, sources=tuple(records), snapshot_hash=snapshot_hash)


def _parse_source_record(d: Any, path: str) -> SourceRecord:
    d = _require_dict(d, path)
    _check_unknown_keys(d, _SOURCE_RECORD_FIELDS, path)
    _require_keys(d, _SOURCE_RECORD_FIELDS, path)
    return SourceRecord(
        owner=_require_token(d["owner"], f"{path}.owner"),
        source_kind=_require_token(d["source_kind"], f"{path}.source_kind"),
        source_identity=_require_id(d["source_identity"], f"{path}.source_identity"),
        schema_version=_require_str(d["schema_version"], f"{path}.schema_version", max_len=MAX_TOKEN_CHARS),
        digest=_require_str(d["digest"], f"{path}.digest", max_len=MAX_TOKEN_CHARS),
        effective_at=_require_opt_str(d["effective_at"], f"{path}.effective_at", max_len=MAX_TOKEN_CHARS),
        observed_at=_require_opt_str(d["observed_at"], f"{path}.observed_at", max_len=MAX_TOKEN_CHARS),
        correction_ref=_require_opt_str(d["correction_ref"], f"{path}.correction_ref", max_len=MAX_TOKEN_CHARS),
        freshness=_require_enum(d["freshness"], f"{path}.freshness", _FRESHNESS),
        conflict=_require_enum(d["conflict"], f"{path}.conflict", _CONFLICT),
        coverage=_require_enum(d["coverage"], f"{path}.coverage", _COVERAGE),
        truncated=_require_bool(d["truncated"], f"{path}.truncated"),
        continuation=_require_opt_str(d["continuation"], f"{path}.continuation", max_len=MAX_TOKEN_CHARS),
    )


_ABSTRACTION_FIELDS = frozenset(
    {
        "kind",
        "concrete_scope",
        "preserves",
        "introduced_behavior",
        "excluded_behavior",
        "validation_kind",
        "validation_refs",
        "notes",
    }
)


def _parse_abstraction_contract(d: Any) -> AbstractionContract:
    d = _require_dict(d, "abstraction_contract")
    _check_unknown_keys(d, _ABSTRACTION_FIELDS, "abstraction_contract")
    _require_keys(d, _ABSTRACTION_FIELDS, "abstraction_contract")
    kind = _require_enum(d["kind"], "abstraction_contract.kind", _ABSTRACTION_KINDS)
    concrete_scope = _require_str(d["concrete_scope"], "abstraction_contract.concrete_scope")
    preserves_raw = _require_list(d["preserves"], "abstraction_contract.preserves")
    preserves = tuple(sorted({_require_enum(v, "abstraction_contract.preserves[]", _PRESERVES) for v in preserves_raw}))
    introduced_behavior = _require_enum(d["introduced_behavior"], "abstraction_contract.introduced_behavior", _INTRO_EXCLUDED)
    excluded_behavior = _require_enum(d["excluded_behavior"], "abstraction_contract.excluded_behavior", _INTRO_EXCLUDED)
    validation_kind = _require_enum(d["validation_kind"], "abstraction_contract.validation_kind", _VALIDATION_KINDS)
    validation_refs = _require_source_ref_list(d["validation_refs"], "abstraction_contract.validation_refs")
    notes_raw = _require_list(d["notes"], "abstraction_contract.notes")
    notes = tuple(_require_str(n, f"abstraction_contract.notes[{i}]") for i, n in enumerate(notes_raw))
    return AbstractionContract(
        kind=kind,
        concrete_scope=concrete_scope,
        preserves=preserves,
        introduced_behavior=introduced_behavior,
        excluded_behavior=excluded_behavior,
        validation_kind=validation_kind,
        validation_refs=validation_refs,
        notes=notes,
    )


def _parse_state_domains(d: Any) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], dict[str, tuple[str, ...]]]:
    d = _require_dict(d, "state_domains")
    if len(d) > MAX_STATE_VARIABLES:
        raise _fail("TOO_MANY_STATE_VARIABLES", "state_domains exceeds MAX_STATE_VARIABLES", "state_domains")
    index: dict[str, tuple[str, ...]] = {}
    for var, domain in d.items():
        var_id = _require_id(var, f"state_domains.{var}")
        values = _require_list(domain, f"state_domains.{var}", max_items=MAX_DOMAIN_VALUES_PER_VARIABLE)
        if not values:
            raise _fail("EMPTY_DOMAIN", "domain must be non-empty", f"state_domains.{var}")
        parsed = [_require_token(v, f"state_domains.{var}[{i}]") for i, v in enumerate(values)]
        if len(set(parsed)) != len(parsed):
            raise _fail("DUPLICATE_DOMAIN_VALUE", "duplicate domain value", f"state_domains.{var}")
        index[var_id] = tuple(sorted(parsed))
    ordered = tuple(sorted(index.items(), key=lambda kv: kv[0]))
    return ordered, index


def _parse_initial_state(d: Any, domain_index: dict[str, tuple[str, ...]]) -> tuple[tuple[str, str], ...]:
    d = _require_dict(d, "initial_state")
    if set(d.keys()) != set(domain_index.keys()):
        raise _fail("INITIAL_STATE_KEY_MISMATCH", "initial_state keys must exactly equal state_domains keys", "initial_state")
    out = {}
    for var, value in d.items():
        val = _require_token(value, f"initial_state.{var}")
        if val not in domain_index[var]:
            raise _fail("VALUE_OUTSIDE_DOMAIN", f"{val!r} is outside the declared domain", f"initial_state.{var}")
        out[var] = val
    return tuple(sorted(out.items(), key=lambda kv: kv[0]))


_EXPLORATION_LIMITS_FIELDS = frozenset({"max_states", "max_depth"})


def _parse_exploration_limits(d: Any) -> ExplorationLimits:
    d = _require_dict(d, "exploration_limits")
    _check_unknown_keys(d, _EXPLORATION_LIMITS_FIELDS, "exploration_limits")
    _require_keys(d, _EXPLORATION_LIMITS_FIELDS, "exploration_limits")
    max_states = _require_int(d["max_states"], "exploration_limits.max_states")
    max_depth = _require_int(d["max_depth"], "exploration_limits.max_depth")
    if max_states < 1 or max_states > MAX_EXPLORATION_STATES:
        raise _fail("BAD_EXPLORATION_LIMIT", "max_states out of bounds", "exploration_limits.max_states")
    if max_depth < 0 or max_depth > MAX_EXPLORATION_DEPTH:
        raise _fail("BAD_EXPLORATION_LIMIT", "max_depth out of bounds", "exploration_limits.max_depth")
    return ExplorationLimits(max_states=max_states, max_depth=max_depth)


_TRANSITION_FIELDS = frozenset(
    {
        "transition_id",
        "kind",
        "actor_class",
        "authority_requirement",
        "guards",
        "effects",
        "progress_tags",
        "source_refs",
        "fairness_ref",
        "external_assumption_ref",
        "gate_refs",
        "required_reachable",
    }
)


def _parse_transitions_raw(value: Any, domain_index: dict[str, tuple[str, ...]]) -> list[dict]:
    items = _require_list(value, "transitions", max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    out = []
    seen_ids = set()
    for i, t in enumerate(items):
        path = f"transitions[{i}]"
        t = _require_dict(t, path)
        _check_unknown_keys(t, _TRANSITION_FIELDS, path)
        _require_keys(t, _TRANSITION_FIELDS, path)
        tid = _require_id(t["transition_id"], f"{path}.transition_id")
        if tid in seen_ids:
            raise _fail("DUPLICATE_ID", "duplicate transition_id", path)
        seen_ids.add(tid)
        guards = _parse_guard_list_raw(t["guards"], f"{path}.guards")
        for g in guards:
            _resolve_guard_against_domain(g, domain_index, f"{path}.guards")
        effects = _parse_effects_raw(t["effects"], domain_index, path)
        out.append(
            {
                "transition_id": tid,
                "kind": _require_token(t["kind"], f"{path}.kind"),
                "actor_class": _require_token(t["actor_class"], f"{path}.actor_class"),
                "authority_requirement": _require_token(t["authority_requirement"], f"{path}.authority_requirement"),
                "guards": guards,
                "effects": effects,
                "progress_tags": _require_token_list(t["progress_tags"], f"{path}.progress_tags"),
                "source_refs": _require_source_ref_list(t["source_refs"], f"{path}.source_refs"),
                "fairness_ref": _require_opt_str(t["fairness_ref"], f"{path}.fairness_ref", max_len=MAX_TOKEN_CHARS),
                "external_assumption_ref": _require_opt_str(
                    t["external_assumption_ref"], f"{path}.external_assumption_ref", max_len=MAX_TOKEN_CHARS
                ),
                "gate_refs": _require_id_list(t["gate_refs"], f"{path}.gate_refs"),
                "required_reachable": _require_bool(t["required_reachable"], f"{path}.required_reachable"),
            }
        )
    return out


def _resolve_guard_against_domain(g: dict, domain_index: dict[str, tuple[str, ...]], path: str) -> None:
    if g["variable"] not in domain_index:
        raise _fail("UNRESOLVED_REFERENCE", f"unknown variable {g['variable']!r}", path)
    domain = domain_index[g["variable"]]
    if g["op"] in ("EQ", "NEQ"):
        if g["value"] not in domain:
            raise _fail("VALUE_OUTSIDE_DOMAIN", f"{g['value']!r} is outside the declared domain", path)
    else:
        for v in g["value"]:
            if v not in domain:
                raise _fail("VALUE_OUTSIDE_DOMAIN", f"{v!r} is outside the declared domain", path)


def _parse_effects_raw(value: Any, domain_index: dict[str, tuple[str, ...]], path: str) -> list[dict]:
    items = _require_list(value, f"{path}.effects", max_items=MAX_EFFECTS_PER_TRANSITION)
    out = []
    seen_vars = set()
    for i, e in enumerate(items):
        epath = f"{path}.effects[{i}]"
        e = _require_dict(e, epath)
        _check_unknown_keys(e, frozenset({"variable", "value"}), epath)
        _require_keys(e, frozenset({"variable", "value"}), epath)
        var = _require_id(e["variable"], f"{epath}.variable")
        if var not in domain_index:
            raise _fail("UNRESOLVED_REFERENCE", f"unknown variable {var!r}", epath)
        if var in seen_vars:
            raise _fail("DUPLICATE_EFFECT", "duplicate effect for the same variable", epath)
        seen_vars.add(var)
        val = _require_token(e["value"], f"{epath}.value")
        if val not in domain_index[var]:
            raise _fail("VALUE_OUTSIDE_DOMAIN", f"{val!r} is outside the declared domain", epath)
        out.append({"variable": var, "value": val})
    out.sort(key=lambda x: x["variable"])
    return out


_OUTCOME_FIELDS = frozenset(
    {
        "outcome_id",
        "kind",
        "guards",
        "owned_persistent_obligation_ids",
        "owned_persistent_resource_ids",
        "source_refs",
    }
)


def _parse_outcomes_raw(value: Any, field_name: str, allowed_kinds: frozenset) -> list[dict]:
    items = _require_list(value, field_name, max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    out = []
    seen = set()
    for i, o in enumerate(items):
        path = f"{field_name}[{i}]"
        o = _require_dict(o, path)
        _check_unknown_keys(o, _OUTCOME_FIELDS, path)
        _require_keys(o, _OUTCOME_FIELDS, path)
        oid = _require_id(o["outcome_id"], f"{path}.outcome_id")
        if oid in seen:
            raise _fail("DUPLICATE_ID", "duplicate outcome_id", path)
        seen.add(oid)
        kind = _require_enum(o["kind"], f"{path}.kind", allowed_kinds)
        guards = _parse_guard_list_raw(o["guards"], f"{path}.guards")
        obl_ids = _require_id_list(o["owned_persistent_obligation_ids"], f"{path}.owned_persistent_obligation_ids")
        res_ids = _require_id_list(o["owned_persistent_resource_ids"], f"{path}.owned_persistent_resource_ids")
        out.append(
            {
                "outcome_id": oid,
                "kind": kind,
                "guards": guards,
                "owned_persistent_obligation_ids": obl_ids,
                "owned_persistent_resource_ids": res_ids,
                "source_refs": _require_source_ref_list(o["source_refs"], f"{path}.source_refs"),
            }
        )
    return out


_OBLIGATION_FIELDS = frozenset(
    {
        "obligation_id",
        "kind",
        "state_variable",
        "pending_values",
        "discharged_values",
        "persistent",
        "owner_or_authority",
        "source_refs",
    }
)


def _parse_obligations_raw(value: Any, domain_index: dict[str, tuple[str, ...]]) -> list[dict]:
    items = _require_list(value, "obligations", max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    out = []
    seen = set()
    for i, o in enumerate(items):
        path = f"obligations[{i}]"
        o = _require_dict(o, path)
        _check_unknown_keys(o, _OBLIGATION_FIELDS, path)
        _require_keys(o, _OBLIGATION_FIELDS, path)
        oid = _require_id(o["obligation_id"], f"{path}.obligation_id")
        if oid in seen:
            raise _fail("DUPLICATE_ID", "duplicate obligation_id", path)
        seen.add(oid)
        state_variable = _require_id(o["state_variable"], f"{path}.state_variable")
        domain = domain_index.get(state_variable)
        pending = _require_token_list(o["pending_values"], f"{path}.pending_values", max_items=MAX_DOMAIN_VALUES_PER_VARIABLE)
        discharged = _require_token_list(
            o["discharged_values"], f"{path}.discharged_values", max_items=MAX_DOMAIN_VALUES_PER_VARIABLE
        )
        if not pending or not discharged:
            raise _fail("EMPTY_ARRAY", "pending_values/discharged_values must be non-empty", path)
        if set(pending) & set(discharged):
            raise _fail("NON_DISJOINT_SETS", "pending_values and discharged_values must be disjoint", path)
        if domain is not None:
            for v in list(pending) + list(discharged):
                if v not in domain:
                    raise _fail("VALUE_OUTSIDE_DOMAIN", f"{v!r} is outside the declared domain", path)
        out.append(
            {
                "obligation_id": oid,
                "kind": _require_token(o["kind"], f"{path}.kind"),
                "state_variable": state_variable,
                "pending_values": pending,
                "discharged_values": discharged,
                "persistent": _require_bool(o["persistent"], f"{path}.persistent"),
                "owner_or_authority": _require_token(o["owner_or_authority"], f"{path}.owner_or_authority"),
                "source_refs": _require_source_ref_list(o["source_refs"], f"{path}.source_refs"),
            }
        )
    return out


_RESOURCE_FIELDS = frozenset(
    {"resource_id", "holder_variable", "released_values", "persistent", "owner_or_authority", "source_refs"}
)


def _parse_resources_raw(value: Any, domain_index: dict[str, tuple[str, ...]]) -> list[dict]:
    items = _require_list(value, "resources", max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    out = []
    seen = set()
    for i, r in enumerate(items):
        path = f"resources[{i}]"
        r = _require_dict(r, path)
        _check_unknown_keys(r, _RESOURCE_FIELDS, path)
        _require_keys(r, _RESOURCE_FIELDS, path)
        rid = _require_id(r["resource_id"], f"{path}.resource_id")
        if rid in seen:
            raise _fail("DUPLICATE_ID", "duplicate resource_id", path)
        seen.add(rid)
        holder_variable = _require_id(r["holder_variable"], f"{path}.holder_variable")
        domain = domain_index.get(holder_variable)
        released = _require_token_list(
            r["released_values"], f"{path}.released_values", max_items=MAX_DOMAIN_VALUES_PER_VARIABLE
        )
        if not released:
            raise _fail("EMPTY_ARRAY", "released_values must be non-empty", path)
        if domain is not None:
            for v in released:
                if v not in domain:
                    raise _fail("VALUE_OUTSIDE_DOMAIN", f"{v!r} is outside the declared domain", path)
        out.append(
            {
                "resource_id": rid,
                "holder_variable": holder_variable,
                "released_values": released,
                "persistent": _require_bool(r["persistent"], f"{path}.persistent"),
                "owner_or_authority": _require_token(r["owner_or_authority"], f"{path}.owner_or_authority"),
                "source_refs": _require_source_ref_list(r["source_refs"], f"{path}.source_refs"),
            }
        )
    return out


_GATE_FIELDS = frozenset(
    {
        "gate_id",
        "disposition",
        "state_guards",
        "owner_or_authority",
        "release_condition",
        "release_transition_ids",
        "return_or_observation_source",
        "wake_or_review_path",
        "time_contract",
        "correction_contract",
        "escalation_or_close_path",
        "source_refs",
    }
)


def _parse_gates_raw(value: Any, domain_index: dict[str, tuple[str, ...]]) -> list[dict]:
    items = _require_list(value, "external_gates", max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    out = []
    seen = set()
    for i, g in enumerate(items):
        path = f"external_gates[{i}]"
        g = _require_dict(g, path)
        _check_unknown_keys(g, _GATE_FIELDS, path)
        _require_keys(g, _GATE_FIELDS, path)
        gid = _require_id(g["gate_id"], f"{path}.gate_id")
        if gid in seen:
            raise _fail("DUPLICATE_ID", "duplicate gate_id", path)
        seen.add(gid)
        state_guards = _parse_guard_list_raw(g["state_guards"], f"{path}.state_guards")
        for sg in state_guards:
            _resolve_guard_against_domain(sg, domain_index, f"{path}.state_guards")
        release_ids = _require_id_list(g["release_transition_ids"], f"{path}.release_transition_ids", sort=False)
        if not release_ids:
            raise _fail("EMPTY_ARRAY", "release_transition_ids must be non-empty", path)
        release_ids = tuple(sorted(set(release_ids)))
        out.append(
            {
                "gate_id": gid,
                "disposition": _require_enum(g["disposition"], f"{path}.disposition", _GATE_DISPOSITIONS),
                "state_guards": state_guards,
                "owner_or_authority": _require_token(g["owner_or_authority"], f"{path}.owner_or_authority"),
                "release_condition": _require_str(g["release_condition"], f"{path}.release_condition"),
                "release_transition_ids": release_ids,
                "return_or_observation_source": _require_str(
                    g["return_or_observation_source"], f"{path}.return_or_observation_source"
                ),
                "wake_or_review_path": _require_str(g["wake_or_review_path"], f"{path}.wake_or_review_path"),
                "time_contract": _require_str(g["time_contract"], f"{path}.time_contract"),
                "correction_contract": _require_str(g["correction_contract"], f"{path}.correction_contract"),
                "escalation_or_close_path": _require_id(g["escalation_or_close_path"], f"{path}.escalation_or_close_path"),
                "source_refs": _require_source_ref_list(g["source_refs"], f"{path}.source_refs"),
            }
        )
    return out


_FAIRNESS_FIELDS = frozenset({"fairness_id", "kind", "transition_ids", "source_refs"})


def _parse_fairness_raw(value: Any) -> list[dict]:
    items = _require_list(value, "fairness_assumptions", max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    out = []
    seen = set()
    for i, f in enumerate(items):
        path = f"fairness_assumptions[{i}]"
        f = _require_dict(f, path)
        _check_unknown_keys(f, _FAIRNESS_FIELDS, path)
        _require_keys(f, _FAIRNESS_FIELDS, path)
        fid = _require_id(f["fairness_id"], f"{path}.fairness_id")
        if fid in seen:
            raise _fail("DUPLICATE_ID", "duplicate fairness_id", path)
        seen.add(fid)
        kind = _require_str(f["kind"], f"{path}.kind", max_len=MAX_TOKEN_CHARS)
        if kind != _FAIRNESS_KIND:
            raise _fail("UNSUPPORTED_FAIRNESS", "OLS-A1 supports only WEAK fairness", f"{path}.kind")
        tids = _require_id_list(f["transition_ids"], f"{path}.transition_ids")
        if not tids:
            raise _fail("EMPTY_ARRAY", "transition_ids must be non-empty", path)
        out.append(
            {
                "fairness_id": fid,
                "kind": kind,
                "transition_ids": tids,
                "source_refs": _require_source_ref_list(f["source_refs"], f"{path}.source_refs"),
            }
        )
    return out


_ENV_ASSUMPTION_FIELDS = frozenset(
    {"assumption_id", "kind", "transition_ids", "required_for_property_ids", "source_refs"}
)


def _parse_environment_assumptions_raw(value: Any) -> list[dict]:
    items = _require_list(value, "environment_assumptions", max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    out = []
    seen = set()
    for i, a in enumerate(items):
        path = f"environment_assumptions[{i}]"
        a = _require_dict(a, path)
        _check_unknown_keys(a, _ENV_ASSUMPTION_FIELDS, path)
        _require_keys(a, _ENV_ASSUMPTION_FIELDS, path)
        aid = _require_id(a["assumption_id"], f"{path}.assumption_id")
        if aid in seen:
            raise _fail("DUPLICATE_ID", "duplicate assumption_id", path)
        seen.add(aid)
        tids = _require_id_list(a["transition_ids"], f"{path}.transition_ids")
        if not tids:
            raise _fail("EMPTY_ARRAY", "transition_ids must be non-empty", path)
        out.append(
            {
                "assumption_id": aid,
                "kind": _require_token(a["kind"], f"{path}.kind"),
                "transition_ids": tids,
                "required_for_property_ids": _require_id_list(
                    a["required_for_property_ids"], f"{path}.required_for_property_ids"
                ),
                "source_refs": _require_source_ref_list(a["source_refs"], f"{path}.source_refs"),
            }
        )
    return out


_STATE_FORBIDDEN_FIELDS = frozenset({"property_id", "kind", "violation_when", "source_refs"})
_TRANSITION_FORBIDDEN_FIELDS = frozenset(
    {"property_id", "kind", "when", "forbidden_transition_kinds", "source_refs"}
)


def _parse_safety_properties_raw(value: Any, domain_index: dict[str, tuple[str, ...]]) -> list[dict]:
    items = _require_list(value, "safety_properties", max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    out = []
    seen = set()
    for i, s in enumerate(items):
        path = f"safety_properties[{i}]"
        s = _require_dict(s, path)
        pid = _require_id(s.get("property_id", ""), f"{path}.property_id") if "property_id" in s else None
        kind = s.get("kind")
        if kind == "STATE_FORBIDDEN":
            _check_unknown_keys(s, _STATE_FORBIDDEN_FIELDS, path)
            _require_keys(s, _STATE_FORBIDDEN_FIELDS, path)
        elif kind == "TRANSITION_FORBIDDEN":
            _check_unknown_keys(s, _TRANSITION_FORBIDDEN_FIELDS, path)
            _require_keys(s, _TRANSITION_FORBIDDEN_FIELDS, path)
        else:
            raise _fail("UNKNOWN_ENUM_VALUE", "safety property kind must be STATE_FORBIDDEN or TRANSITION_FORBIDDEN", f"{path}.kind")
        if pid is None:
            pid = _require_id(s["property_id"], f"{path}.property_id")
        if pid in seen:
            raise _fail("DUPLICATE_ID", "duplicate property_id", path)
        if pid in GENERIC_MANDATORY_PROPERTY_IDS:
            raise _fail("PROPERTY_ID_COLLISION", "authored property_id collides with a generic mandatory property", path)
        seen.add(pid)
        if kind == "STATE_FORBIDDEN":
            guards = _parse_guard_list_raw(s["violation_when"], f"{path}.violation_when")
            for g in guards:
                _resolve_guard_against_domain(g, domain_index, f"{path}.violation_when")
            out.append(
                {
                    "property_id": pid,
                    "kind": kind,
                    "violation_when": guards,
                    "source_refs": _require_source_ref_list(s["source_refs"], f"{path}.source_refs"),
                }
            )
        else:
            guards = _parse_guard_list_raw(s["when"], f"{path}.when")
            for g in guards:
                _resolve_guard_against_domain(g, domain_index, f"{path}.when")
            kinds = _require_token_list(s["forbidden_transition_kinds"], f"{path}.forbidden_transition_kinds")
            if not kinds:
                raise _fail("EMPTY_ARRAY", "forbidden_transition_kinds must be non-empty", path)
            out.append(
                {
                    "property_id": pid,
                    "kind": kind,
                    "when": guards,
                    "forbidden_transition_kinds": kinds,
                    "source_refs": _require_source_ref_list(s["source_refs"], f"{path}.source_refs"),
                }
            )
    return out


_MODEL_GAP_FIELDS = frozenset(
    {
        "gap_id",
        "reason",
        "load_bearing",
        "affects_property_ids",
        "affects_transition_ids",
        "affects_variable_ids",
        "source_refs",
    }
)


def _parse_model_gaps_raw(value: Any) -> list[dict]:
    items = _require_list(value, "known_model_gaps", max_items=MAX_TOP_LEVEL_COLLECTION_ITEMS)
    out = []
    seen = set()
    for i, g in enumerate(items):
        path = f"known_model_gaps[{i}]"
        g = _require_dict(g, path)
        _check_unknown_keys(g, _MODEL_GAP_FIELDS, path)
        _require_keys(g, _MODEL_GAP_FIELDS, path)
        gid = _require_id(g["gap_id"], f"{path}.gap_id")
        if gid in seen:
            raise _fail("DUPLICATE_ID", "duplicate gap_id", path)
        seen.add(gid)
        out.append(
            {
                "gap_id": gid,
                "reason": _require_str(g["reason"], f"{path}.reason"),
                "load_bearing": _require_bool(g["load_bearing"], f"{path}.load_bearing"),
                "affects_property_ids": _require_id_list(g["affects_property_ids"], f"{path}.affects_property_ids"),
                "affects_transition_ids": _require_id_list(g["affects_transition_ids"], f"{path}.affects_transition_ids"),
                "affects_variable_ids": _require_id_list(g["affects_variable_ids"], f"{path}.affects_variable_ids"),
                "source_refs": _require_source_ref_list(g["source_refs"], f"{path}.source_refs"),
            }
        )
    return out
