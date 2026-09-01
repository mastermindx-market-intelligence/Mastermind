"""Frozen, SDK-free contract for the six Secretary grounding reads.

This module contains data shapes and validation only. It deliberately imports
neither an MCP SDK nor any canonical owner, transport, provider, browser, host,
or persistence implementation.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
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

ERROR_CODES = frozenset(
    {
        "INVALID_REQUEST",
        "STEWARD_UNAVAILABLE",
        "GROUNDING_REFUSED",
        "RESPONSE_REFUSED",
        "INTERNAL_ERROR",
    }
)
GROUNDING_STATES = frozenset({"FACTS", "UNKNOWN", "DEGRADED", "REFUSED"})
FRESHNESS_STATES = frozenset({"FRESH", "STALE", "UNKNOWN"})
GROUNDING_REASON_CODES = frozenset(
    {
        "AMBIGUOUS_JOIN",
        "DENIED",
        "DEPENDENCY_UNAVAILABLE",
        "EFFECT_UNKNOWN",
        "NO_SOURCE",
        "POLICY_REFUSAL",
        "RESPONSIBILITY_UNKNOWN",
        "RUNTIME_UNKNOWN",
        "STALE_SOURCE",
        "STEWARD_DEGRADED",
        "SURFACE_UNKNOWN",
    }
)
SOURCE_NAMESPACE_BY_OWNER = MappingProxyType(
    {
        "agent_os": ("WS", "DEC", "DSC"),
        "executive_os": ("JOB", "ATTEMPT", "WORKER", "EVENT", "EXEC"),
        "runtime_binding": ("RUNTIME",),
        "capacity": ("CAPACITY",),
        "wake": ("WAKE",),
        "agent_dialogue": ("DIALOGUE",),
        "surface_binding": ("SURFACE",),
        "provider_control": ("POLICY",),
        "unknown": ("UNKNOWN",),
    }
)
SOURCE_OWNERS = frozenset(SOURCE_NAMESPACE_BY_OWNER)

_CANONICAL_CREDENTIAL_PREFIX = (
    r"(?:sb_secret_|sb_publishable_|sbp_|sk-ant-|sk-|github_pat_|ghp_|gho_|ghs_|"
    r"xox[abeprs]-|xapp-|eyJ|AKIA|ASIA|ABIA|ACCA)"
)
_CANONICAL_CREDENTIAL_FENCE = (
    rf"(?!{_CANONICAL_CREDENTIAL_PREFIX})"
    rf"(?![A-Za-z0-9._-]*[._-]{_CANONICAL_CREDENTIAL_PREFIX})"
)
_RESPONSIBILITY_REF_PATTERN = (
    rf"^responsibility:{_CANONICAL_CREDENTIAL_FENCE}"
    r"[a-z0-9][a-z0-9._-]{0,144}$"
)
_RESPONSIBILITY_REF_RE = re.compile(
    rf"\Aresponsibility:{_CANONICAL_CREDENTIAL_FENCE}"
    r"[a-z0-9][a-z0-9._-]{0,144}\Z"
)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_URL_RE = re.compile(r"(?i)\b(?:https?|file|ssh|postgres(?:ql)?|mysql|redis)://")
_PRIVATE_PATH_RE = re.compile(
    r"(?i)(?:^|[\s='\"])(?:/Users/|/home/|/private/|/tmp/|/var/|/etc/|~/|[A-Z]:\\)"
)
_SECRET_RE = re.compile(
    rf"(?i)(?:{_CANONICAL_CREDENTIAL_PREFIX}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:bearer|api[_-]?key|token|secret|password)\s*[:=]\s*\S{6,})"
)
_PRIVATE_LOCATOR_RE = re.compile(
    r"(?i)\b(?:provider(?:_session)?|native_(?:session|handle)|account(?:_id)?|"
    r"browser_profile|profile_id|host|channel|thread|coordinates|pid|pgid)\s*[:=]\s*\S+"
)
_HIGH_ENTROPY_RE = re.compile(
    r"\b(?=[A-Za-z0-9]{32,}\b)(?=[A-Za-z0-9]*[a-z])(?=[A-Za-z0-9]*[A-Z])"
    r"(?=[A-Za-z0-9]*[0-9])[A-Za-z0-9]+\b"
)
_PUBLIC_TEXT_PATTERN = (
    r"^(?!.*[\x00-\x1f\x7f])"
    r"(?!.*(?:https?://|file://|ssh://|postgres(?:ql)?://|mysql://|redis://))"
    r"(?!.*[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
    r"(?!.*(?:/Users/|/home/|/private/|/tmp/|/var/|/etc/|~/|[A-Za-z]:\\))"
    rf"(?!.*{_CANONICAL_CREDENTIAL_PREFIX})"
    r"(?!.*\b(?:bearer|api[_-]?key|token|secret|password)\s*[:=])"
    r"(?!.*\b(?:provider(?:_session)?|native_(?:session|handle)|account(?:_id)?|"
    r"browser_profile|profile_id|host|channel|thread|coordinates|pid|pgid)\s*[:=])"
    r".+$"
)


def _source_ref_pattern(namespaces: tuple[str, ...]) -> str:
    joined = "|".join(namespaces)
    return (
        rf"^(?:{joined}):{_CANONICAL_CREDENTIAL_FENCE}"
        r"[A-Za-z0-9][A-Za-z0-9._-]{0,223}$"
    )


class GatewayError(RuntimeError):
    """One fixed Secretary gateway refusal."""

    def __init__(self, code: str) -> None:
        if code not in ERROR_CODES:
            raise ValueError("unknown Secretary gateway error code")
        super().__init__(code)
        self.code = code


def _string(*, max_length: int, pattern: str | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"type": "string", "minLength": 1, "maxLength": max_length}
    if pattern is not None:
        value["pattern"] = pattern
    return value


def _object(properties: Mapping[str, Any], *, required: tuple[str, ...] = ()) -> dict[str, Any]:
    value: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": False,
    }
    if required:
        value["required"] = list(required)
    return value


def _normalize_public_text(value: Any, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or _CONTROL_RE.search(value)
        or _EMAIL_RE.search(value)
        or _URL_RE.search(value)
        or _PRIVATE_PATH_RE.search(value)
        or _SECRET_RE.search(value)
        or _PRIVATE_LOCATOR_RE.search(value)
        or _HIGH_ENTROPY_RE.search(value)
    ):
        raise GatewayError("RESPONSE_REFUSED")
    return value


@dataclasses.dataclass(frozen=True)
class _PublicFactContract:
    """One reviewed public predicate and its only representable value language."""

    predicate: str
    value_kind: str
    enum_values: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    reference_namespaces: tuple[str, ...] = ()
    corroborating_owners: tuple[str, ...] = ()

    @property
    def value_schema(self) -> dict[str, Any]:
        if self.value_kind == "enum":
            return {"type": "string", "enum": list(self.enum_values)}
        if self.value_kind == "boolean":
            return {"type": "boolean"}
        if self.value_kind == "integer":
            return {
                "type": "integer",
                "minimum": self.minimum,
                "maximum": self.maximum,
            }
        if self.value_kind == "text":
            return _string(max_length=int(self.max_length or 1), pattern=_PUBLIC_TEXT_PATTERN)
        if self.value_kind == "reference":
            return _string(
                max_length=256,
                pattern=_source_ref_pattern(self.reference_namespaces),
            )
        raise RuntimeError("unsupported public fact contract")

    def normalize(self, value: Any) -> str | int | bool:
        if self.value_kind == "enum":
            if isinstance(value, str) and value in self.enum_values:
                return value
        elif self.value_kind == "boolean":
            if isinstance(value, bool):
                return value
        elif self.value_kind == "integer":
            if (
                isinstance(value, int)
                and not isinstance(value, bool)
                and self.minimum is not None
                and self.maximum is not None
                and self.minimum <= value <= self.maximum
            ):
                return value
        elif self.value_kind == "text":
            return _normalize_public_text(value, int(self.max_length or 0))
        elif self.value_kind == "reference":
            if (
                isinstance(value, str)
                and 1 <= len(value) <= 256
                and not _CONTROL_RE.search(value)
                and re.fullmatch(_source_ref_pattern(self.reference_namespaces), value)
            ):
                return value
        raise GatewayError("RESPONSE_REFUSED")


_FACT_CONTRACT_ROWS = (
    _PublicFactContract("responsibility.identity", "reference", reference_namespaces=("WS",), corroborating_owners=("agent_os",)),
    _PublicFactContract("responsibility.title", "text", max_length=160, corroborating_owners=("agent_os",)),
    _PublicFactContract("responsibility.accountable_seat", "enum", ("CHAIRMAN", "SOL", "COO", "WORKER", "EXTERNAL", "UNKNOWN")),
    _PublicFactContract("responsibility.objective", "text", max_length=480, corroborating_owners=("agent_os",)),
    _PublicFactContract("responsibility.next_action", "text", max_length=480, corroborating_owners=("agent_os",)),
    _PublicFactContract("responsibility.state", "enum", ("ACTIVE", "BLOCKED", "COMPLETE", "UNKNOWN", "WAITING")),
    _PublicFactContract("responsibility.priority", "integer", minimum=0, maximum=100),
    _PublicFactContract("responsibility.requires_attention", "boolean"),
    _PublicFactContract("attention.ref", "reference", reference_namespaces=("EVENT", "EXEC", "WAKE", "DIALOGUE"), corroborating_owners=("executive_os", "wake", "agent_dialogue")),
    _PublicFactContract("attention.target_seat", "enum", ("CHAIRMAN", "SOL", "COO", "WORKER", "EXTERNAL", "UNKNOWN")),
    _PublicFactContract("attention.kind", "enum", ("BLOCKER", "CAPACITY", "CONTINUATION", "DECISION", "DELIVERY", "REVIEW", "OTHER", "UNKNOWN")),
    _PublicFactContract("attention.reason", "text", max_length=320, corroborating_owners=("agent_os", "executive_os", "wake", "agent_dialogue")),
    _PublicFactContract("attention.requested_action", "text", max_length=320, corroborating_owners=("agent_os", "executive_os", "wake", "agent_dialogue")),
    _PublicFactContract("attention.state", "enum", ("CHAIRMAN_REQUIRED", "COO_REQUIRED", "EXTERNAL_REQUIRED", "NONE", "SOL_REQUIRED", "UNKNOWN")),
    _PublicFactContract("runtime.job_ref", "reference", reference_namespaces=("JOB",), corroborating_owners=("executive_os",)),
    _PublicFactContract("runtime.attempt_ref", "reference", reference_namespaces=("ATTEMPT",), corroborating_owners=("executive_os",)),
    _PublicFactContract("runtime.worker_ref", "reference", reference_namespaces=("WORKER",), corroborating_owners=("executive_os",)),
    _PublicFactContract("runtime.binding_ref", "reference", reference_namespaces=("RUNTIME",), corroborating_owners=("runtime_binding",)),
    _PublicFactContract("runtime.state", "enum", ("IDLE", "PAUSED", "RUNNING", "STOPPED", "UNAVAILABLE", "UNKNOWN")),
    _PublicFactContract("runtime.effect_state", "enum", ("NONE", "NOT_APPLIED", "APPLIED", "EFFECT_UNKNOWN")),
    _PublicFactContract("runtime.continuation", "enum", ("ACKNOWLEDGED", "PREPARED", "MISSING", "TERMINAL", "UNKNOWN", "AMBIGUOUS", "BOUND", "STALE", "UNAVAILABLE", "UNBOUND")),
    _PublicFactContract("runtime.capacity_state", "enum", ("AVAILABLE", "BUSY", "WAITING", "UNAVAILABLE", "UNKNOWN")),
    _PublicFactContract("runtime.age_seconds", "integer", minimum=0, maximum=31_536_000),
    _PublicFactContract("blocker.kind", "enum", ("AUTHORITY_REQUIRED", "CAPACITY_REQUIRED", "EXTERNAL_DEPENDENCY", "NONE", "POLICY_REFUSAL", "RUNTIME_UNAVAILABLE", "SOURCE_AMBIGUOUS", "SOURCE_STALE", "SOURCE_UNKNOWN", "SURFACE_UNAVAILABLE", "UNKNOWN")),
    _PublicFactContract("blocker.present", "boolean"),
    _PublicFactContract("blocker.explanation", "text", max_length=480, corroborating_owners=("agent_os", "executive_os", "runtime_binding", "capacity", "surface_binding", "provider_control")),
    _PublicFactContract("blocker.dependency_ref", "reference", reference_namespaces=("WS", "DEC", "DSC", "JOB", "ATTEMPT", "WORKER", "EVENT", "EXEC", "RUNTIME", "CAPACITY", "WAKE", "DIALOGUE", "SURFACE", "POLICY")),
    _PublicFactContract("blocker.action_ref", "reference", reference_namespaces=("WS", "DEC", "DSC", "JOB", "ATTEMPT", "WORKER", "EVENT", "EXEC", "RUNTIME", "CAPACITY", "WAKE", "DIALOGUE", "SURFACE", "POLICY")),
    _PublicFactContract("surface.ref", "reference", reference_namespaces=("SURFACE",), corroborating_owners=("surface_binding",)),
    _PublicFactContract("surface.locator_kind", "enum", ("CONTROL_ROOM", "CHAT", "GITHUB", "LINEAR", "SLACK", "WEB", "OTHER", "UNKNOWN")),
    _PublicFactContract("surface.review_state", "enum", ("APPROVED", "PENDING", "REJECTED", "UNKNOWN")),
    _PublicFactContract("surface.health", "enum", ("AMBIGUOUS", "AUTH_REQUIRED", "DEGRADED", "HOST_UNREACHABLE", "PROVIDER_ERROR", "RESPONSIVE", "TARGET_MISSING", "UNKNOWN", "UNRESPONSIVE")),
    _PublicFactContract("surface.repair_required", "boolean"),
    _PublicFactContract("surface.observation_age_seconds", "integer", minimum=0, maximum=31_536_000),
)
PUBLIC_FACT_CONTRACTS = MappingProxyType(
    {contract.predicate: contract for contract in _FACT_CONTRACT_ROWS}
)
_PUBLIC_FACTS_BY_PREDICATE = PUBLIC_FACT_CONTRACTS
_PREDICATE_ORDER = {predicate: index for index, predicate in enumerate(PUBLIC_FACT_CONTRACTS)}

TOOL_REQUIRED_PREDICATES = MappingProxyType(
    {
        "list_responsibilities": frozenset({"responsibility.identity", "responsibility.title", "responsibility.state", "responsibility.next_action"}),
        "get_responsibility": frozenset({"responsibility.identity", "responsibility.title", "responsibility.objective", "responsibility.next_action", "responsibility.state"}),
        "get_attention": frozenset({"attention.ref", "attention.reason", "attention.requested_action", "attention.state"}),
        "get_current_runtime": frozenset({"runtime.job_ref", "runtime.attempt_ref", "runtime.worker_ref", "runtime.binding_ref", "runtime.state", "runtime.effect_state"}),
        "explain_blocker": frozenset({"blocker.present", "blocker.kind", "blocker.explanation"}),
        "resolve_surface": frozenset({"surface.ref", "surface.locator_kind", "surface.review_state", "surface.health"}),
    }
)

_RESPONSIBILITY_REF_SCHEMA = _string(max_length=MAX_RESPONSIBILITY_REF_CHARS, pattern=_RESPONSIBILITY_REF_PATTERN)
_SOURCE_SCHEMA = _object(
    {
        "owner": {"type": "string", "enum": sorted(SOURCE_OWNERS)},
        "source_ref": _string(
            max_length=256,
            pattern=_source_ref_pattern(
                tuple(namespace for namespaces in SOURCE_NAMESPACE_BY_OWNER.values() for namespace in namespaces)
            ),
        ),
        "observed_at": {"oneOf": [{"type": "null"}, _string(max_length=20, pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")]},
    },
    required=("owner", "source_ref", "observed_at"),
)
_SOURCE_SCHEMA["allOf"] = [{"oneOf": [{"properties": {"owner": {"const": owner}, "source_ref": {"type": "string", "minLength": 1, "maxLength": 256, "pattern": _source_ref_pattern(namespaces)}}} for owner, namespaces in SOURCE_NAMESPACE_BY_OWNER.items()]}]

_FACT_SCHEMA = _object(
    {
        "subject_ref": _RESPONSIBILITY_REF_SCHEMA,
        "predicate": {"type": "string", "enum": list(PUBLIC_FACT_CONTRACTS)},
        "value": {"anyOf": [{"type": "boolean"}, {"type": "integer", "minimum": 0, "maximum": 31_536_000}, {"type": "string"}]},
        "freshness": {"type": "string", "enum": sorted(FRESHNESS_STATES)},
        "sources": {"type": "array", "minItems": 1, "maxItems": MAX_SOURCES_PER_FACT, "items": _SOURCE_SCHEMA},
    },
    required=("subject_ref", "predicate", "value", "freshness", "sources"),
)
_FACT_SCHEMA["allOf"] = [{"oneOf": [{"properties": {"predicate": {"const": contract.predicate}, "value": contract.value_schema}} for contract in _FACT_CONTRACT_ROWS]}]
_RESULT_DATA_SCHEMA = _object(
    {
        "state": {"type": "string", "enum": sorted(GROUNDING_STATES)},
        "facts": {"type": "array", "maxItems": MAX_FACTS, "items": _FACT_SCHEMA},
        "reason_codes": {"type": "array", "maxItems": MAX_REASON_CODES, "uniqueItems": True, "items": {"type": "string", "enum": sorted(GROUNDING_REASON_CODES)}},
    },
    required=("state", "facts", "reason_codes"),
)
_FRESH_FACT_SCHEMA = copy.deepcopy(_FACT_SCHEMA)
_FRESH_FACT_SCHEMA["properties"]["freshness"] = {"const": "FRESH"}
_RESULT_DATA_SCHEMA["allOf"] = [{"oneOf": [
    {"properties": {"state": {"const": "FACTS"}, "facts": {"type": "array", "minItems": 1, "maxItems": MAX_FACTS, "items": _FRESH_FACT_SCHEMA}, "reason_codes": {"type": "array", "maxItems": 0}}},
    {"properties": {"state": {"const": "UNKNOWN"}, "facts": {"type": "array", "maxItems": 0}, "reason_codes": {"type": "array", "minItems": 1, "maxItems": MAX_REASON_CODES}}},
    {"properties": {"state": {"const": "DEGRADED"}, "reason_codes": {"type": "array", "minItems": 1, "maxItems": MAX_REASON_CODES}}},
    {"properties": {"state": {"const": "REFUSED"}, "facts": {"type": "array", "maxItems": 0}, "reason_codes": {"type": "array", "minItems": 1, "maxItems": MAX_REASON_CODES}}},
]}]
_ERROR_DETAIL_SCHEMA = {"oneOf": [_object({"code": {"const": code}, "message": {"const": code}}, required=("code", "message")) for code in sorted(ERROR_CODES)]}


def _output_schema(tool_name: str) -> dict[str, Any]:
    value = _object(
        {
            "schema": {"const": RESULT_SCHEMA},
            "tool": {"const": tool_name},
            "ok": {"type": "boolean"},
            "server_version": {"const": SERVER_VERSION},
            "data": {"oneOf": [{"type": "null"}, _RESULT_DATA_SCHEMA]},
            "error": {"oneOf": [{"type": "null"}, copy.deepcopy(_ERROR_DETAIL_SCHEMA)]},
        },
        required=("schema", "tool", "ok", "server_version", "data", "error"),
    )
    value["allOf"] = [{"oneOf": [
        {"properties": {"ok": {"const": True}, "data": copy.deepcopy(_RESULT_DATA_SCHEMA), "error": {"type": "null"}}},
        {"properties": {"ok": {"const": False}, "data": {"type": "null"}, "error": copy.deepcopy(_ERROR_DETAIL_SCHEMA)}},
    ]}]
    return value


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    """One immutable reviewed Secretary read tool."""

    name: str
    description: str
    requires_responsibility_ref: bool
    read_only: bool = True

    @property
    def input_schema(self) -> dict[str, Any]:
        if self.requires_responsibility_ref:
            return _object({"responsibility_ref": copy.deepcopy(_RESPONSIBILITY_REF_SCHEMA)}, required=("responsibility_ref",))
        return _object({})

    @property
    def output_schema(self) -> dict[str, Any]:
        return _output_schema(self.name)

    @property
    def annotations(self) -> dict[str, Any]:
        return {"title": self.name, "readOnlyHint": self.read_only, "destructiveHint": False, "idempotentHint": self.read_only, "openWorldHint": False}


_TOOL_ROWS = (
    ("list_responsibilities", "List source-attributed responsibility grounding from the injected Steward read port.", False),
    ("get_responsibility", "Read one exact responsibility reference without heuristic identity resolution.", True),
    ("get_attention", "Read source-attributed attention facts without selecting a person, role, or transport.", False),
    ("get_current_runtime", "Read current runtime facts for one exact responsibility reference.", True),
    ("explain_blocker", "Read source-attributed company, runtime, and surface blocker facts for one responsibility.", True),
    ("resolve_surface", "Read exact reviewed surface resolution and health without performing any action.", True),
)
TOOL_SPECS: tuple[ToolSpec, ...] = tuple(ToolSpec(*row) for row in _TOOL_ROWS)
_TOOLS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if dataclasses.is_dataclass(value):
        return _jsonable(dataclasses.asdict(value))
    raise GatewayError("INVALID_REQUEST")


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError):
        raise GatewayError("INVALID_REQUEST") from None


def validate_tool_arguments(tool_name: str, arguments: Any) -> dict[str, Any]:
    assert_contract_integrity()
    if not isinstance(tool_name, str):
        raise GatewayError("INVALID_REQUEST")
    spec = _TOOLS_BY_NAME.get(tool_name)
    if spec is None:
        raise GatewayError("INVALID_REQUEST")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, Mapping):
        raise GatewayError("INVALID_REQUEST")
    raw = dict(arguments)
    allowed = set(spec.input_schema["properties"])
    if set(raw) != set(spec.input_schema.get("required", ())) or not set(raw) <= allowed:
        raise GatewayError("INVALID_REQUEST")
    if not raw:
        return {}
    responsibility_ref = raw.get("responsibility_ref")
    if not isinstance(responsibility_ref, str) or _RESPONSIBILITY_REF_RE.fullmatch(responsibility_ref) is None:
        raise GatewayError("INVALID_REQUEST")
    if len(canonical_json({"arguments": raw})) > MAX_REQUEST_BYTES:
        raise GatewayError("INVALID_REQUEST")
    return {"responsibility_ref": responsibility_ref}


def _validated_source(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"owner", "source_ref", "observed_at"}:
        raise GatewayError("RESPONSE_REFUSED")
    owner, source_ref, observed_at = value["owner"], value["source_ref"], value["observed_at"]
    if not isinstance(owner, str) or owner not in SOURCE_OWNERS:
        raise GatewayError("RESPONSE_REFUSED")
    if (
        not isinstance(source_ref, str)
        or not 1 <= len(source_ref) <= 256
        or re.fullmatch(_source_ref_pattern(SOURCE_NAMESPACE_BY_OWNER[owner]), source_ref) is None
        or _CONTROL_RE.search(source_ref)
    ):
        raise GatewayError("RESPONSE_REFUSED")
    if observed_at is not None and (
        not isinstance(observed_at, str)
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", observed_at) is None
    ):
        raise GatewayError("RESPONSE_REFUSED")
    return {"owner": owner, "source_ref": source_ref, "observed_at": observed_at}


def _validated_fact(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"subject_ref", "predicate", "value", "freshness", "sources"}:
        raise GatewayError("RESPONSE_REFUSED")
    subject_ref, predicate, freshness, sources = value["subject_ref"], value["predicate"], value["freshness"], value["sources"]
    if (
        not isinstance(subject_ref, str)
        or _RESPONSIBILITY_REF_RE.fullmatch(subject_ref) is None
        or not isinstance(predicate, str)
        or predicate not in PUBLIC_FACT_CONTRACTS
        or not isinstance(freshness, str)
        or freshness not in FRESHNESS_STATES
        or not isinstance(sources, (list, tuple))
        or not 1 <= len(sources) <= MAX_SOURCES_PER_FACT
    ):
        raise GatewayError("RESPONSE_REFUSED")
    contract = PUBLIC_FACT_CONTRACTS[predicate]
    normalized_sources = sorted((_validated_source(source) for source in sources), key=lambda row: (row["owner"], row["source_ref"], row["observed_at"] or ""))
    normalized_value = contract.normalize(value["value"])
    if contract.corroborating_owners and not any(source["owner"] in contract.corroborating_owners for source in normalized_sources):
        raise GatewayError("RESPONSE_REFUSED")
    if contract.value_kind == "reference" and not any(source["source_ref"] == normalized_value and (not contract.corroborating_owners or source["owner"] in contract.corroborating_owners) for source in normalized_sources):
        raise GatewayError("RESPONSE_REFUSED")
    return {"subject_ref": subject_ref, "predicate": predicate, "value": normalized_value, "freshness": freshness, "sources": normalized_sources}


def _validate_cross_fact_law(state: str, facts: list[dict[str, Any]], reason_codes: list[str]) -> None:
    seen: set[tuple[str, str]] = set()
    identity_by_subject: dict[str, str] = {}
    subject_by_identity: dict[str, str] = {}
    by_subject: dict[str, dict[str, dict[str, Any]]] = {}
    for fact in facts:
        key = (fact["subject_ref"], fact["predicate"])
        if key in seen:
            raise GatewayError("RESPONSE_REFUSED")
        seen.add(key)
        by_subject.setdefault(fact["subject_ref"], {})[fact["predicate"]] = fact
        if fact["predicate"] == "responsibility.identity":
            identity = str(fact["value"])
            if fact["subject_ref"] in identity_by_subject or identity in subject_by_identity:
                raise GatewayError("RESPONSE_REFUSED")
            identity_by_subject[fact["subject_ref"]] = identity
            subject_by_identity[identity] = fact["subject_ref"]

    selected_predicates = {"runtime.job_ref", "runtime.attempt_ref", "runtime.worker_ref", "runtime.binding_ref", "surface.ref"}
    selected = any(fact["predicate"] in selected_predicates for fact in facts)
    unsafe_reasons = {"AMBIGUOUS_JOIN", "EFFECT_UNKNOWN", "RUNTIME_UNKNOWN", "STALE_SOURCE", "SURFACE_UNKNOWN"}
    if selected and (state != "FACTS" or unsafe_reasons.intersection(reason_codes)):
        raise GatewayError("RESPONSE_REFUSED")

    for subject, rows in by_subject.items():
        surface = rows.get("surface.ref")
        if surface is None:
            continue
        locator = rows.get("surface.locator_kind")
        review = rows.get("surface.review_state")
        health = rows.get("surface.health")
        if (
            locator is None
            or review is None
            or health is None
            or review["value"] != "APPROVED"
            or any(row["freshness"] != "FRESH" for row in (surface, locator, review, health))
            or any(source["owner"] != "surface_binding" for row in (surface, locator, review, health) for source in row["sources"])
        ):
            raise GatewayError("RESPONSE_REFUSED")


def validate_result_data(value: Any) -> dict[str, Any]:
    """Validate the complete typed Steward return without inference or repair."""

    if not isinstance(value, Mapping) or set(value) != {"state", "facts", "reason_codes"}:
        raise GatewayError("RESPONSE_REFUSED")
    state, facts, reason_codes = value["state"], value["facts"], value["reason_codes"]
    if (
        not isinstance(state, str)
        or state not in GROUNDING_STATES
        or not isinstance(facts, (list, tuple))
        or len(facts) > MAX_FACTS
        or not isinstance(reason_codes, (list, tuple))
        or len(reason_codes) > MAX_REASON_CODES
        or any(not isinstance(code, str) or code not in GROUNDING_REASON_CODES for code in reason_codes)
        or len(reason_codes) != len(set(reason_codes))
    ):
        raise GatewayError("RESPONSE_REFUSED")
    normalized_facts = [_validated_fact(fact) for fact in facts]
    normalized_reasons = sorted(reason_codes)
    if state == "FACTS" and (not normalized_facts or normalized_reasons or any(fact["freshness"] != "FRESH" for fact in normalized_facts)):
        raise GatewayError("RESPONSE_REFUSED")
    if state in {"UNKNOWN", "REFUSED"} and (normalized_facts or not normalized_reasons):
        raise GatewayError("RESPONSE_REFUSED")
    if state == "DEGRADED" and not normalized_reasons:
        raise GatewayError("RESPONSE_REFUSED")
    _validate_cross_fact_law(state, normalized_facts, normalized_reasons)
    normalized_facts.sort(key=lambda fact: (fact["subject_ref"], _PREDICATE_ORDER[fact["predicate"]], canonical_json(fact["value"])))
    return {"state": state, "facts": normalized_facts, "reason_codes": normalized_reasons}


def result_envelope(tool_name: str, *, data: Any) -> dict[str, Any]:
    if tool_name not in _TOOLS_BY_NAME:
        raise GatewayError("RESPONSE_REFUSED")
    normalized = validate_result_data(data)
    envelope = {"schema": RESULT_SCHEMA, "tool": tool_name, "ok": True, "server_version": SERVER_VERSION, "data": normalized, "error": None}
    try:
        if len(canonical_json(envelope)) > MAX_RESPONSE_BYTES:
            raise GatewayError("RESPONSE_REFUSED")
    except GatewayError:
        raise GatewayError("RESPONSE_REFUSED") from None
    return envelope


def error_envelope(tool_name: str, code: str) -> dict[str, Any]:
    if code not in ERROR_CODES:
        code = "INTERNAL_ERROR"
    return {"schema": RESULT_SCHEMA, "tool": tool_name if isinstance(tool_name, str) and tool_name in _TOOLS_BY_NAME else "unknown", "ok": False, "server_version": SERVER_VERSION, "data": None, "error": {"code": code, "message": code}}


def schema_snapshot() -> dict[str, Any]:
    return {
        "server_name": SERVER_NAME,
        "server_identity": SERVER_IDENTITY,
        "server_version": SERVER_VERSION,
        "result_schema": RESULT_SCHEMA,
        "errors": sorted(ERROR_CODES),
        "grounding_reason_codes": sorted(GROUNDING_REASON_CODES),
        "source_namespaces": {owner: list(namespaces) for owner, namespaces in SOURCE_NAMESPACE_BY_OWNER.items()},
        "public_fact_contracts": [
            {
                "predicate": contract.predicate,
                "value_kind": contract.value_kind,
                "enum_values": list(contract.enum_values),
                "minimum": contract.minimum,
                "maximum": contract.maximum,
                "max_length": contract.max_length,
                "reference_namespaces": list(contract.reference_namespaces),
                "corroborating_owners": list(contract.corroborating_owners),
            }
            for contract in _FACT_CONTRACT_ROWS
        ],
        "tool_required_predicates": {tool: sorted(predicates) for tool, predicates in TOOL_REQUIRED_PREDICATES.items()},
        "limits": {"request_bytes": MAX_REQUEST_BYTES, "response_bytes": MAX_RESPONSE_BYTES, "facts": MAX_FACTS, "sources_per_fact": MAX_SOURCES_PER_FACT, "reason_codes": MAX_REASON_CODES},
        "tools": [{"name": spec.name, "description": spec.description, "input_schema": copy.deepcopy(spec.input_schema), "output_schema": copy.deepcopy(spec.output_schema), "annotations": copy.deepcopy(spec.annotations), "read_only": spec.read_only} for spec in TOOL_SPECS],
    }


def schema_snapshot_sha256() -> str:
    return hashlib.sha256(canonical_json(schema_snapshot())).hexdigest()


def tool_schema_snapshot() -> list[dict[str, Any]]:
    return [{"annotations": copy.deepcopy(spec.annotations), "input_schema": copy.deepcopy(spec.input_schema), "name": spec.name, "output_schema": copy.deepcopy(spec.output_schema)} for spec in sorted(TOOL_SPECS, key=lambda item: item.name)]


def tool_schema_digest() -> str:
    return hashlib.sha256(canonical_json(tool_schema_snapshot())).hexdigest()


SCHEMA_SNAPSHOT_SHA256 = "1b0c99fb9b8a0a325d0440191a64848e510569ef6e979737a8e91dfeca508429"
TOOL_SCHEMA_DIGEST = "9bc30d9185ca6df2bbb1dbb3a19a593756017fbc1d4e8bb0c54b33c5f9ba679d"


def assert_contract_integrity() -> None:
    if schema_snapshot_sha256() != SCHEMA_SNAPSHOT_SHA256 or tool_schema_digest() != TOOL_SCHEMA_DIGEST:
        raise GatewayError("INTERNAL_ERROR")


__all__ = [
    "ERROR_CODES", "FRESHNESS_STATES", "GROUNDING_REASON_CODES", "GROUNDING_STATES",
    "GatewayError", "MAX_FACTS", "MAX_REQUEST_BYTES", "MAX_RESPONSE_BYTES",
    "MAX_SOURCES_PER_FACT", "PUBLIC_FACT_CONTRACTS", "RESULT_SCHEMA",
    "SCHEMA_SNAPSHOT_SHA256", "SERVER_IDENTITY", "SERVER_NAME", "SERVER_VERSION",
    "SOURCE_NAMESPACE_BY_OWNER", "SOURCE_OWNERS", "TOOL_REQUIRED_PREDICATES",
    "TOOL_SCHEMA_DIGEST", "TOOL_SPECS", "ToolSpec", "assert_contract_integrity",
    "canonical_json", "error_envelope", "result_envelope", "schema_snapshot",
    "schema_snapshot_sha256", "tool_schema_digest", "tool_schema_snapshot",
    "validate_result_data", "validate_tool_arguments",
]
