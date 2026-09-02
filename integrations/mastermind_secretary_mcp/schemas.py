"""SDK-free, read-only contract for the six Secretary grounding tools."""
from __future__ import annotations

import copy, dataclasses, hashlib, json, re
from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any

SERVER_NAME = "mastermind-secretary-grounding"
SERVER_IDENTITY = "mastermind-secretary-grounding-mcp"
SERVER_VERSION = "1.0.0"
RESULT_SCHEMA = "mastermind.secretary_grounding_mcp_result.v1"
MAX_REQUEST_BYTES = 8 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_RESPONSIBILITY_REF_CHARS = 160
MAX_FACTS = 64
MAX_SOURCES_PER_FACT = 8
MAX_REASON_CODES = 16

ERROR_CODES = frozenset({"INVALID_REQUEST", "STEWARD_UNAVAILABLE", "GROUNDING_REFUSED", "RESPONSE_REFUSED", "INTERNAL_ERROR"})
GROUNDING_STATES = frozenset({"FACTS", "UNKNOWN", "DEGRADED", "REFUSED"})
FRESHNESS_STATES = frozenset({"FRESH", "STALE", "UNKNOWN"})
GROUNDING_REASON_CODES = frozenset({"AMBIGUOUS_JOIN", "DENIED", "DEPENDENCY_UNAVAILABLE", "EFFECT_UNKNOWN", "NO_SOURCE", "POLICY_REFUSAL", "RESPONSIBILITY_UNKNOWN", "RUNTIME_UNKNOWN", "STALE_SOURCE", "STEWARD_DEGRADED", "SURFACE_UNKNOWN"})
SOURCE_NAMESPACE_BY_OWNER = MappingProxyType({
    "agent_os": ("WS", "DEC", "DSC"),
    "executive_os": ("JOB", "ATTEMPT", "WORKER", "EVENT", "EXEC"),
    "runtime_binding": ("RUNTIME",),
    "executive_inbox": ("EXEC",),
    "capacity": ("CAPACITY",),
    "wake": ("WAKE",),
    "agent_dialogue": ("DIALOGUE",),
    "surface_binding": ("SURFACE",),
    "surface_bindings": ("SURFACE",),
    "provider_control": ("POLICY",),
    "unknown": ("UNKNOWN",),
})
SOURCE_OWNERS = frozenset(SOURCE_NAMESPACE_BY_OWNER)

_CRED = r"(?:sb_secret_|sb_publishable_|sbp_|sk-ant-|sk-|github_pat_|ghp_|gho_|ghs_|xox[abeprs]-|xapp-|eyJ|AKIA|ASIA|ABIA|ACCA)"
_FENCE = rf"(?!{_CRED})(?![A-Za-z0-9._-]*[._-]{_CRED})"
_TOKEN = rf"{_FENCE}[A-Za-z0-9][A-Za-z0-9._:-]{{0,223}}"
_TYPED = rf"{_FENCE}[A-Za-z0-9][A-Za-z0-9._-]{{0,223}}"
_RESP_PATTERN = rf"^responsibility:{_FENCE}[a-z0-9][a-z0-9._-]{{0,144}}$"
_RESP_RE = re.compile(rf"\Aresponsibility:{_FENCE}[a-z0-9][a-z0-9._-]{{0,144}}\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_URL = re.compile(r"(?i)\b(?:https?|file|ssh|postgres(?:ql)?|mysql|redis)://")
_PATH = re.compile(r"(?i)(?:^|[\s='\"])(?:/Users/|/home/|/private/|/tmp/|/var/|/etc/|~/|[A-Z]:\\)")
_SECRET = re.compile(rf"(?i)(?:{_CRED}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:bearer|api[_-]?key|token|secret|password)\s*[:=]\s*\S{{6,}})")
_LOCATOR = re.compile(r"(?i)\b(?:provider(?:_session)?|native_(?:session|handle)|account(?:_id)?|browser_profile|profile_id|host|channel|thread|coordinates|pid|pgid)\s*[:=]\s*\S+")
_ENTROPY = re.compile(r"\b(?=[A-Za-z0-9]{32,}\b)(?=[A-Za-z0-9]*[a-z])(?=[A-Za-z0-9]*[A-Z])(?=[A-Za-z0-9]*[0-9])[A-Za-z0-9]+\b")
_TEXT_PATTERN = (r"^(?!.*[\x00-\x1f\x7f])(?!.*(?:https?://|file://|ssh://|postgres(?:ql)?://|mysql://|redis://))"
                r"(?!.*[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?!.*(?:/Users/|/home/|/private/|/tmp/|/var/|/etc/|~/|[A-Za-z]:\\))"
                rf"(?!.*{_CRED})(?!.*\b(?:bearer|api[_-]?key|token|secret|password)\s*[:=])"
                r"(?!.*\b(?:provider(?:_session)?|native_(?:session|handle)|account(?:_id)?|browser_profile|profile_id|host|channel|thread|coordinates|pid|pgid)\s*[:=]).+$")


def _typed_pattern(namespaces: tuple[str, ...]) -> str:
    return rf"^(?:{'|'.join(map(re.escape, namespaces))}):{_TYPED}$"


def _source_patterns(owner: str) -> tuple[str, ...]:
    extra = {
        "executive_os": (rf"^executive-runtime:{_TOKEN}$",),
        "runtime_binding": (rf"^runtime-binding:{_TOKEN}$",),
        "executive_inbox": (rf"^executive-inbox:{_TOKEN}$",),
        "surface_bindings": (rf"^surface-binding:{_TOKEN}$",),
    }
    return (_typed_pattern(SOURCE_NAMESPACE_BY_OWNER[owner]), *extra.get(owner, ()))


def _all_source_pattern() -> str:
    parts = [p[1:-1] for owner in SOURCE_NAMESPACE_BY_OWNER for p in _source_patterns(owner)]
    return "^(?:" + "|".join(dict.fromkeys(parts)) + ")$"


class GatewayError(RuntimeError):
    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown Secretary gateway error code")
        super().__init__(code); self.code = code


def _string(max_length: int, pattern: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "string", "minLength": 1, "maxLength": max_length}
    if pattern is not None: out["pattern"] = pattern
    return out


def _object(properties: Mapping[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "object", "properties": dict(properties), "additionalProperties": False}
    if required: out["required"] = list(required)
    return out


def _text(value: Any, limit: int) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= limit or value != value.strip()
            or any(rx.search(value) for rx in (_CONTROL, _EMAIL, _URL, _PATH, _SECRET, _LOCATOR, _ENTROPY))):
        raise GatewayError("RESPONSE_REFUSED")
    return value


@dataclasses.dataclass(frozen=True)
class _PublicFactContract:
    predicate: str
    value_kind: str
    enum_values: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    value_pattern: str | None = None
    corroborating_owners: tuple[str, ...] = ()
    aliases: tuple[tuple[str, str], ...] = ()

    @property
    def value_schema(self) -> dict[str, Any]:
        if self.value_kind == "enum": return {"type": "string", "enum": list(self.enum_values)}
        if self.value_kind == "boolean": return {"type": "boolean"}
        if self.value_kind == "integer": return {"type": "integer", "minimum": self.minimum, "maximum": self.maximum}
        if self.value_kind == "text": return _string(int(self.max_length or 1), _TEXT_PATTERN)
        if self.value_kind == "reference": return _string(256, str(self.value_pattern))
        raise RuntimeError("unsupported public fact contract")

    def normalize(self, value: Any) -> str | int | bool:
        if self.value_kind == "enum" and isinstance(value, str):
            normalized = value if value in self.enum_values else dict(self.aliases).get(value)
            if normalized in self.enum_values: return str(normalized)
        elif self.value_kind == "boolean" and isinstance(value, bool): return value
        elif self.value_kind == "integer" and isinstance(value, int) and not isinstance(value, bool) and self.minimum is not None and self.maximum is not None and self.minimum <= value <= self.maximum: return value
        elif self.value_kind == "text": return _text(value, int(self.max_length or 0))
        elif self.value_kind == "reference" and isinstance(value, str) and 1 <= len(value) <= 256 and self.value_pattern and re.fullmatch(self.value_pattern, value) and not _CONTROL.search(value) and not _SECRET.search(value): return value
        raise GatewayError("RESPONSE_REFUSED")


def _aliases(values: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple((value.lower(), value) for value in values)


def _c(predicate: str, kind: str, values: tuple[str, ...] = (), *, minimum=None, maximum=None, max_length=None, pattern=None, owners=(), aliases=()) -> _PublicFactContract:
    return _PublicFactContract(predicate, kind, values, minimum, maximum, max_length, pattern, owners, aliases)


WS = rf"^WS:{_TYPED}$"
ATTN = rf"^(?:eia-{_TYPED}|(?:EVENT|EXEC|WAKE|DIALOGUE):{_TYPED})$"
JOB = rf"^(?:JOB-{_TYPED}|JOB:{_TYPED})$"
ATTEMPT = rf"^(?:ATT-{_TYPED}|ATTEMPT:{_TYPED})$"
WORKER = rf"^(?:WORKER:{_TYPED}|{_TYPED})$"
BINDING = rf"^(?:RUNTIME:{_TYPED}|{_TYPED})$"
TYPED_REF = rf"^(?:WS|DEC|DSC|JOB|ATTEMPT|WORKER|EVENT|EXEC|RUNTIME|CAPACITY|WAKE|DIALOGUE|SURFACE|POLICY):{_TYPED}$"
UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"
SURFACE = rf"^(?:{UUID}|SURFACE:{_TYPED})$"
SEATS = ("CHAIRMAN", "CEO", "SOL", "COO", "WORKER", "EXTERNAL", "UNKNOWN")
RESP_STATES = ("ACTIVE", "BLOCKED", "COMPLETE", "UNKNOWN", "WAITING")
ATTN_STATES = ("CHAIRMAN_REQUIRED", "COO_REQUIRED", "EXTERNAL_REQUIRED", "NONE", "SOL_REQUIRED", "UNKNOWN")
RUNTIME_STATES = ("IDLE", "PAUSED", "RUNNING", "STOPPED", "UNAVAILABLE", "UNKNOWN")
EFFECTS = ("NONE", "NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN")
CONTINUATIONS = ("ACKNOWLEDGED", "PREPARED", "MISSING", "TERMINAL", "UNKNOWN", "AMBIGUOUS", "BOUND", "STALE", "UNAVAILABLE", "UNBOUND")
CAPACITY = ("AVAILABLE", "BUSY", "DEGRADED", "WAITING", "UNAVAILABLE", "UNKNOWN")
SURFACE_KINDS = ("CONTROL_ROOM", "CHAT", "CHATGPT_MANAGED_ENV", "GITHUB", "LINEAR", "SLACK", "WEB", "OTHER", "UNKNOWN")
REVIEWS = ("APPROVED", "PENDING", "REJECTED", "UNKNOWN")
HEALTH = ("AMBIGUOUS", "AUTH_REQUIRED", "DEGRADED", "HOST_UNREACHABLE", "PROVIDER_ERROR", "RESPONSIVE", "TARGET_MISSING", "UNKNOWN", "UNRESPONSIVE")
BLOCKERS = ("AUTHORITY_REQUIRED", "CAPACITY_REQUIRED", "EXTERNAL_DEPENDENCY", "NONE", "POLICY_REFUSAL", "RUNTIME_UNAVAILABLE", "SOURCE_AMBIGUOUS", "SOURCE_STALE", "SOURCE_UNKNOWN", "SURFACE_UNAVAILABLE", "UNKNOWN")
ATTN_KINDS = ("BLOCKER", "CAPACITY", "CONTINUATION", "DECISION", "DELIVERY", "REVIEW", "OTHER", "UNKNOWN")

_FACT_CONTRACT_ROWS = (
    _c("responsibility.identity", "reference", pattern=WS, owners=("agent_os",)),
    _c("responsibility.title", "text", max_length=160, owners=("agent_os",)),
    _c("responsibility.accountable_seat", "enum", SEATS, aliases=_aliases(SEATS)),
    _c("responsibility.objective", "text", max_length=480, owners=("agent_os",)),
    _c("responsibility.next_action", "text", max_length=480, owners=("agent_os",)),
    _c("responsibility.state", "enum", RESP_STATES, aliases=_aliases(RESP_STATES)),
    _c("responsibility.priority", "integer", minimum=0, maximum=100),
    _c("responsibility.requires_attention", "boolean"),
    _c("attention.ref", "reference", pattern=ATTN, owners=("executive_os", "executive_inbox", "wake", "agent_dialogue")),
    _c("attention.target_seat", "enum", SEATS, aliases=_aliases(SEATS)),
    _c("attention.kind", "enum", ATTN_KINDS, aliases=_aliases(ATTN_KINDS) + (("blocker_required", "BLOCKER"), ("capacity_required", "CAPACITY"), ("continuation_required", "CONTINUATION"), ("decision_required", "DECISION"), ("delivery_required", "DELIVERY"), ("review_required", "REVIEW"))),
    _c("attention.reason", "text", max_length=320, owners=("agent_os", "executive_os", "executive_inbox", "wake", "agent_dialogue")),
    _c("attention.requested_action", "text", max_length=320, owners=("agent_os", "executive_os", "executive_inbox", "wake", "agent_dialogue")),
    _c("attention.state", "enum", ATTN_STATES, aliases=_aliases(ATTN_STATES)),
    _c("runtime.job_ref", "reference", pattern=JOB, owners=("executive_os",)),
    _c("runtime.attempt_ref", "reference", pattern=ATTEMPT, owners=("executive_os",)),
    _c("runtime.worker_ref", "reference", pattern=WORKER, owners=("executive_os",)),
    _c("runtime.binding_ref", "reference", pattern=BINDING, owners=("runtime_binding",)),
    _c("runtime.state", "enum", RUNTIME_STATES, aliases=_aliases(RUNTIME_STATES)),
    _c("runtime.effect_state", "enum", EFFECTS, aliases=_aliases(EFFECTS)),
    _c("runtime.continuation", "enum", CONTINUATIONS, aliases=_aliases(CONTINUATIONS)),
    _c("runtime.capacity_state", "enum", CAPACITY, aliases=_aliases(CAPACITY)),
    _c("runtime.age_seconds", "integer", minimum=0, maximum=31_536_000),
    _c("blocker.kind", "enum", BLOCKERS, aliases=_aliases(BLOCKERS)),
    _c("blocker.present", "boolean"),
    _c("blocker.explanation", "text", max_length=480, owners=("agent_os", "executive_os", "executive_inbox", "runtime_binding", "capacity", "surface_binding", "surface_bindings", "provider_control", "wake")),
    _c("blocker.dependency_ref", "reference", pattern=TYPED_REF),
    _c("blocker.action_ref", "reference", pattern=TYPED_REF),
    _c("surface.ref", "reference", pattern=SURFACE, owners=("surface_binding", "surface_bindings")),
    _c("surface.locator_kind", "enum", SURFACE_KINDS, aliases=_aliases(SURFACE_KINDS)),
    _c("surface.review_state", "enum", REVIEWS, aliases=_aliases(REVIEWS)),
    _c("surface.health", "enum", HEALTH, aliases=_aliases(HEALTH)),
    _c("surface.repair_required", "boolean"),
    _c("surface.observation_age_seconds", "integer", minimum=0, maximum=31_536_000),
)
PUBLIC_FACT_CONTRACTS = MappingProxyType({c.predicate: c for c in _FACT_CONTRACT_ROWS})
_PREDICATE_ORDER = {p: i for i, p in enumerate(PUBLIC_FACT_CONTRACTS)}
TOOL_REQUIRED_PREDICATES = MappingProxyType({
    "list_responsibilities": frozenset({"responsibility.identity", "responsibility.title", "responsibility.state", "responsibility.next_action"}),
    "get_responsibility": frozenset({"responsibility.identity", "responsibility.title", "responsibility.objective", "responsibility.next_action", "responsibility.state"}),
    "get_attention": frozenset({"attention.ref", "attention.reason", "attention.requested_action", "attention.state"}),
    "get_current_runtime": frozenset({"runtime.job_ref", "runtime.attempt_ref", "runtime.worker_ref", "runtime.binding_ref", "runtime.state", "runtime.effect_state"}),
    "explain_blocker": frozenset({"blocker.present", "blocker.kind", "blocker.explanation"}),
    "resolve_surface": frozenset({"surface.ref", "surface.locator_kind", "surface.review_state", "surface.health"}),
})

_RESP_SCHEMA = _string(MAX_RESPONSIBILITY_REF_CHARS, _RESP_PATTERN)
_SOURCE_SCHEMA = _object({
    "owner": {"type": "string", "enum": sorted(SOURCE_OWNERS)},
    "source_ref": _string(256, _all_source_pattern()),
    "observed_at": {"oneOf": [{"type": "null"}, _string(20, r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")]},
}, ("owner", "source_ref", "observed_at"))
_FACT_SCHEMA = _object({
    "subject_ref": _RESP_SCHEMA,
    "predicate": {"type": "string", "enum": list(PUBLIC_FACT_CONTRACTS)},
    "value": {"anyOf": [{"type": "boolean"}, {"type": "integer", "minimum": 0, "maximum": 31_536_000}, {"type": "string"}]},
    "freshness": {"type": "string", "enum": sorted(FRESHNESS_STATES)},
    "sources": {"type": "array", "minItems": 1, "maxItems": MAX_SOURCES_PER_FACT, "items": _SOURCE_SCHEMA},
}, ("subject_ref", "predicate", "value", "freshness", "sources"))
_FACT_SCHEMA["allOf"] = [{"oneOf": [{"properties": {"predicate": {"const": c.predicate}, "value": c.value_schema}, "required": ["predicate", "value"]} for c in _FACT_CONTRACT_ROWS]}]
_RESULT_SCHEMA_DATA = _object({
    "state": {"type": "string", "enum": sorted(GROUNDING_STATES)},
    "facts": {"type": "array", "maxItems": MAX_FACTS, "items": _FACT_SCHEMA},
    "reason_codes": {"type": "array", "maxItems": MAX_REASON_CODES, "uniqueItems": True, "items": {"type": "string", "enum": sorted(GROUNDING_REASON_CODES)}},
}, ("state", "facts", "reason_codes"))
_RESULT_SCHEMA_DATA["allOf"] = [
    {"if": {"properties": {"state": {"const": "FACTS"}}, "required": ["state"]}, "then": {"properties": {"facts": {"minItems": 1, "items": {"properties": {"freshness": {"const": "FRESH"}}, "required": ["freshness"]}}, "reason_codes": {"maxItems": 0}}}},
    {"if": {"properties": {"state": {"enum": ["UNKNOWN", "REFUSED"]}}, "required": ["state"]}, "then": {"properties": {"facts": {"maxItems": 0}, "reason_codes": {"minItems": 1}}}},
    {"if": {"properties": {"state": {"const": "DEGRADED"}}, "required": ["state"]}, "then": {"properties": {"reason_codes": {"minItems": 1}}}},
]
_ERROR_SCHEMA = {"oneOf": [_object({"code": {"const": c}, "message": {"const": c}}, ("code", "message")) for c in sorted(ERROR_CODES)]}


def _output_schema(tool: str) -> dict[str, Any]:
    out = _object({
        "schema": {"const": RESULT_SCHEMA}, "tool": {"const": tool}, "ok": {"type": "boolean"}, "server_version": {"const": SERVER_VERSION},
        "data": {"oneOf": [{"type": "null"}, copy.deepcopy(_RESULT_SCHEMA_DATA)]},
        "error": {"oneOf": [{"type": "null"}, copy.deepcopy(_ERROR_SCHEMA)]},
    }, ("schema", "tool", "ok", "server_version", "data", "error"))
    out["allOf"] = [
        {"if": {"properties": {"ok": {"const": True}}, "required": ["ok"]}, "then": {"properties": {"data": {"not": {"type": "null"}}, "error": {"type": "null"}}}},
        {"if": {"properties": {"ok": {"const": False}}, "required": ["ok"]}, "then": {"properties": {"data": {"type": "null"}, "error": copy.deepcopy(_ERROR_SCHEMA)}}},
    ]
    return out


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    name: str; description: str; requires_responsibility_ref: bool; read_only: bool = True
    @property
    def input_schema(self) -> dict[str, Any]:
        return _object({"responsibility_ref": copy.deepcopy(_RESP_SCHEMA)}, ("responsibility_ref",)) if self.requires_responsibility_ref else _object({})
    @property
    def output_schema(self) -> dict[str, Any]: return _output_schema(self.name)
    @property
    def annotations(self) -> dict[str, Any]: return {"title": self.name, "readOnlyHint": self.read_only, "destructiveHint": False, "idempotentHint": self.read_only, "openWorldHint": False}

_TOOL_ROWS = (
    ("list_responsibilities", "List source-attributed responsibility grounding from the injected Steward read port.", False),
    ("get_responsibility", "Read one exact responsibility reference without heuristic identity resolution.", True),
    ("get_attention", "Read source-attributed attention facts without selecting a person, role, or transport.", False),
    ("get_current_runtime", "Read current runtime facts for one exact responsibility reference.", True),
    ("explain_blocker", "Read source-attributed company, runtime, and surface blocker facts for one responsibility.", True),
    ("resolve_surface", "Read exact reviewed surface resolution and health without performing any action.", True),
)
TOOL_SPECS = tuple(ToolSpec(*row) for row in _TOOL_ROWS)
_TOOLS = {spec.name: spec for spec in TOOL_SPECS}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping): return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None: return value
    if dataclasses.is_dataclass(value): return _jsonable(dataclasses.asdict(value))
    raise GatewayError("INVALID_REQUEST")


def canonical_json(value: Any) -> bytes:
    try: return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    except GatewayError: raise
    except (TypeError, ValueError): raise GatewayError("INVALID_REQUEST") from None


def validate_tool_arguments(tool_name: str, arguments: Any) -> dict[str, Any]:
    assert_contract_integrity()
    spec = _TOOLS.get(tool_name) if isinstance(tool_name, str) else None
    if spec is None or (arguments is not None and not isinstance(arguments, Mapping)): raise GatewayError("INVALID_REQUEST")
    raw = dict(arguments or {})
    if set(raw) != set(spec.input_schema.get("required", ())): raise GatewayError("INVALID_REQUEST")
    if not raw: return {}
    ref = raw.get("responsibility_ref")
    if not isinstance(ref, str) or _RESP_RE.fullmatch(ref) is None or len(canonical_json({"arguments": raw})) > MAX_REQUEST_BYTES: raise GatewayError("INVALID_REQUEST")
    return {"responsibility_ref": ref}


def _valid_time(value: str) -> bool:
    try: parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError: return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value


def _validated_source(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"owner", "source_ref", "observed_at"}: raise GatewayError("RESPONSE_REFUSED")
    owner, ref, observed = value["owner"], value["source_ref"], value["observed_at"]
    if not isinstance(owner, str) or owner not in SOURCE_OWNERS: raise GatewayError("RESPONSE_REFUSED")
    if not isinstance(ref, str) or not 1 <= len(ref) <= 256 or _CONTROL.search(ref) or _SECRET.search(ref) or not any(re.fullmatch(p, ref) for p in _source_patterns(owner)): raise GatewayError("RESPONSE_REFUSED")
    if observed is not None and (not isinstance(observed, str) or not _valid_time(observed)): raise GatewayError("RESPONSE_REFUSED")
    return {"owner": owner, "source_ref": ref, "observed_at": observed}


def _validated_fact(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"subject_ref", "predicate", "value", "freshness", "sources"}: raise GatewayError("RESPONSE_REFUSED")
    subject, predicate, fresh, sources = value["subject_ref"], value["predicate"], value["freshness"], value["sources"]
    if not isinstance(subject, str) or _RESP_RE.fullmatch(subject) is None or predicate not in PUBLIC_FACT_CONTRACTS or fresh not in FRESHNESS_STATES or not isinstance(sources, (list, tuple)) or not 1 <= len(sources) <= MAX_SOURCES_PER_FACT: raise GatewayError("RESPONSE_REFUSED")
    contract = PUBLIC_FACT_CONTRACTS[predicate]
    checked = sorted((_validated_source(s) for s in sources), key=lambda s: (s["owner"], s["source_ref"], s["observed_at"] or ""))
    if contract.corroborating_owners and not any(s["owner"] in contract.corroborating_owners for s in checked): raise GatewayError("RESPONSE_REFUSED")
    return {"subject_ref": subject, "predicate": predicate, "value": contract.normalize(value["value"]), "freshness": fresh, "sources": checked}


def _receipts(row: dict[str, Any], owners: frozenset[str]) -> set[str]: return {s["source_ref"] for s in row["sources"] if s["owner"] in owners}


def _cross(state: str, facts: list[dict[str, Any]], reasons: list[str]) -> None:
    seen, identities, subjects, grouped = set(), {}, {}, {}
    for fact in facts:
        key = (fact["subject_ref"], fact["predicate"])
        if key in seen: raise GatewayError("RESPONSE_REFUSED")
        seen.add(key); grouped.setdefault(fact["subject_ref"], {})[fact["predicate"]] = fact
        if fact["predicate"] == "responsibility.identity":
            identity = str(fact["value"])
            if fact["subject_ref"] in identities or identity in subjects: raise GatewayError("RESPONSE_REFUSED")
            identities[fact["subject_ref"]] = identity; subjects[identity] = fact["subject_ref"]
    runtime_refs = {"runtime.job_ref", "runtime.attempt_ref", "runtime.worker_ref", "runtime.binding_ref"}
    selected = any(f["predicate"] in runtime_refs | {"surface.ref"} for f in facts)
    if selected and (state != "FACTS" or {"AMBIGUOUS_JOIN", "EFFECT_UNKNOWN", "RUNTIME_UNKNOWN", "STALE_SOURCE", "SURFACE_UNKNOWN"}.intersection(reasons)): raise GatewayError("RESPONSE_REFUSED")
    for rows in grouped.values():
        if any(p in rows for p in runtime_refs) and rows.get("runtime.effect_state", {}).get("value") == "EFFECT_UNKNOWN": raise GatewayError("RESPONSE_REFUSED")
        if "surface.ref" not in rows: continue
        required = [rows.get(p) for p in ("surface.ref", "surface.locator_kind", "surface.review_state", "surface.health")]
        if any(r is None for r in required) or required[2]["value"] != "APPROVED" or any(r["freshness"] != "FRESH" for r in required): raise GatewayError("RESPONSE_REFUSED")
        sets = [_receipts(r, frozenset({"surface_binding", "surface_bindings"})) for r in required]
        if any(not s for s in sets) or not set.intersection(*sets): raise GatewayError("RESPONSE_REFUSED")


def validate_result_data(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"state", "facts", "reason_codes"}: raise GatewayError("RESPONSE_REFUSED")
    state, facts, reasons = value["state"], value["facts"], value["reason_codes"]
    if state not in GROUNDING_STATES or not isinstance(facts, (list, tuple)) or len(facts) > MAX_FACTS or not isinstance(reasons, (list, tuple)) or len(reasons) > MAX_REASON_CODES or any(c not in GROUNDING_REASON_CODES for c in reasons) or len(reasons) != len(set(reasons)): raise GatewayError("RESPONSE_REFUSED")
    facts = [_validated_fact(f) for f in facts]; reasons = sorted(reasons)
    if state == "FACTS" and (not facts or reasons or any(f["freshness"] != "FRESH" for f in facts)): raise GatewayError("RESPONSE_REFUSED")
    if state in {"UNKNOWN", "REFUSED"} and (facts or not reasons): raise GatewayError("RESPONSE_REFUSED")
    if state == "DEGRADED" and not reasons: raise GatewayError("RESPONSE_REFUSED")
    _cross(state, facts, reasons)
    facts.sort(key=lambda f: (f["subject_ref"], _PREDICATE_ORDER[f["predicate"]], canonical_json(f["value"])))
    return {"state": state, "facts": facts, "reason_codes": reasons}


def result_envelope(tool_name: str, *, data: Any) -> dict[str, Any]:
    if not isinstance(tool_name, str) or tool_name not in _TOOLS: raise GatewayError("RESPONSE_REFUSED")
    out = {"schema": RESULT_SCHEMA, "tool": tool_name, "ok": True, "server_version": SERVER_VERSION, "data": validate_result_data(data), "error": None}
    if len(canonical_json(out)) > MAX_RESPONSE_BYTES: raise GatewayError("RESPONSE_REFUSED")
    return out


def error_envelope(tool_name: str, code: str) -> dict[str, Any]:
    code = code if code in ERROR_CODES else "INTERNAL_ERROR"
    safe_tool = tool_name if isinstance(tool_name, str) and tool_name in _TOOLS else "unknown"
    return {"schema": RESULT_SCHEMA, "tool": safe_tool, "ok": False, "server_version": SERVER_VERSION, "data": None, "error": {"code": code, "message": code}}


def schema_snapshot() -> dict[str, Any]:
    return {"server_name": SERVER_NAME, "server_identity": SERVER_IDENTITY, "server_version": SERVER_VERSION, "result_schema": RESULT_SCHEMA,
            "errors": sorted(ERROR_CODES), "grounding_reason_codes": sorted(GROUNDING_REASON_CODES),
            "source_namespaces": {o: list(n) for o, n in SOURCE_NAMESPACE_BY_OWNER.items()}, "source_receipt_patterns": {o: list(_source_patterns(o)) for o in SOURCE_NAMESPACE_BY_OWNER},
            "public_fact_contracts": [{"predicate": c.predicate, "value_kind": c.value_kind, "enum_values": list(c.enum_values), "minimum": c.minimum, "maximum": c.maximum, "max_length": c.max_length, "value_pattern": c.value_pattern, "corroborating_owners": list(c.corroborating_owners), "aliases": [list(a) for a in c.aliases]} for c in _FACT_CONTRACT_ROWS],
            "tool_required_predicates": {t: sorted(p) for t, p in TOOL_REQUIRED_PREDICATES.items()},
            "limits": {"request_bytes": MAX_REQUEST_BYTES, "response_bytes": MAX_RESPONSE_BYTES, "facts": MAX_FACTS, "sources_per_fact": MAX_SOURCES_PER_FACT, "reason_codes": MAX_REASON_CODES},
            "tools": [{"name": s.name, "description": s.description, "input_schema": copy.deepcopy(s.input_schema), "output_schema": copy.deepcopy(s.output_schema), "annotations": copy.deepcopy(s.annotations), "read_only": s.read_only} for s in TOOL_SPECS]}


def schema_snapshot_sha256() -> str: return hashlib.sha256(canonical_json(schema_snapshot())).hexdigest()
def tool_schema_snapshot() -> list[dict[str, Any]]: return [{"annotations": copy.deepcopy(s.annotations), "input_schema": copy.deepcopy(s.input_schema), "name": s.name, "output_schema": copy.deepcopy(s.output_schema)} for s in sorted(TOOL_SPECS, key=lambda x: x.name)]
def tool_schema_digest() -> str: return hashlib.sha256(canonical_json(tool_schema_snapshot())).hexdigest()
SCHEMA_SNAPSHOT_SHA256 = "a51d892daa9c65b635f5ef869b4b0458593b2f6015b9f9830c141e547520b5f7"
TOOL_SCHEMA_DIGEST = "f1a9e6fb374724ea9b726eee081327112be6c9edd642794233a0d85f20c9466d"

def assert_contract_integrity() -> None:
    if schema_snapshot_sha256() != SCHEMA_SNAPSHOT_SHA256 or tool_schema_digest() != TOOL_SCHEMA_DIGEST: raise GatewayError("INTERNAL_ERROR")

__all__ = ["ERROR_CODES", "FRESHNESS_STATES", "GROUNDING_REASON_CODES", "GROUNDING_STATES", "GatewayError", "MAX_FACTS", "MAX_REQUEST_BYTES", "MAX_RESPONSE_BYTES", "MAX_SOURCES_PER_FACT", "PUBLIC_FACT_CONTRACTS", "RESULT_SCHEMA", "SCHEMA_SNAPSHOT_SHA256", "SERVER_IDENTITY", "SERVER_NAME", "SERVER_VERSION", "SOURCE_NAMESPACE_BY_OWNER", "SOURCE_OWNERS", "TOOL_REQUIRED_PREDICATES", "TOOL_SCHEMA_DIGEST", "TOOL_SPECS", "ToolSpec", "assert_contract_integrity", "canonical_json", "error_envelope", "result_envelope", "schema_snapshot", "schema_snapshot_sha256", "tool_schema_digest", "tool_schema_snapshot", "validate_result_data", "validate_tool_arguments"]
