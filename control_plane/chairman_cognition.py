"""Deterministic preflight for Mastermind Chairman-cognition decisions.

This module is a read-only policy projector.  It accepts a closed, source-attributed
snapshot plus candidate strategic options and returns:

* a Pareto frontier without inventing a hidden global priority score;
* a deterministic authority/serviceability preflight for every option; and
* at most one mechanical recommendation when exactly one eligible option remains
  non-dominated.

It grants no organizational authority and performs no I/O, persistence, scheduling,
routing, admission, wake, retry, provider, GitHub, Slack, Linear, Agent OS, or
Executive OS action.  A downstream owner must re-read current canonical evidence and
apply its own existing mutation/authority contract immediately before any effect.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from control_plane.wake_events import canonical_json_bytes


INPUT_SCHEMA = "mastermind.chairman_cognition_input.v1"
PACKET_SCHEMA = "mastermind.chairman_cognition_packet.v1"
ENVELOPE_SCHEMA = "mastermind.chairman_delegation_envelope.v1"
ERROR_SCHEMA = "mastermind.chairman_cognition_error.v1"

_OPTION_ID_RE = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_OPERATION_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,191}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_PATH_PREFIX_RE = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[^\x00-\x1f]{1,240}$")
_ISO_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]00:00)$"
)

MAX_OPTIONS = 64
MAX_SOURCE_RECEIPTS = 128
MAX_SOURCE_REFS_PER_OPTION = 16
MAX_SCOPE_REPOSITORIES = 8
MAX_SCOPE_PATHS = 64
MAX_SCOPE_REFS = 32
MAX_SCOPE_PREFIXES = 32
MAX_CARRIER_PREFIXES = 32
MAX_BUDGET_UNITS = 1_000_000
MAX_ACTIVE_CHILDREN = 128

BENEFIT_DIMENSIONS = (
    "strategic_leverage",
    "dependency_unlock",
    "learning_value",
    "chairman_load_reduction",
    "user_or_machine_value",
)
COST_DIMENSIONS = (
    "time_to_evidence",
    "execution_cost",
    "coordination_risk",
    "irreversibility_risk",
    "scarce_cognition_cost",
)

ALLOWED_SOURCE_OWNERS = frozenset(
    {
        "CHAIRMAN_DIRECTIVE",
        "STRATEGIC_STATE",
        "AGENT_OS",
        "EXECUTIVE_OS",
        "GITHUB",
        "LINEAR",
        "SLACK",
        "CAPACITY",
        "RUNTIME_BINDING",
        "WAKE",
        "STEWARD",
        "CONTROL_ROOM",
        "OBSERVABILITY",
        "OPERATION_ASSURANCE",
    }
)

READ_ONLY_ACTIONS = frozenset(
    {
        "READ_ONLY_RESEARCH",
        "READ_ONLY_AUDIT",
        "ARCHITECTURE_PROPOSAL",
        "STRATEGIC_ANALYSIS",
        "PORTFOLIO_HOLD",
    }
)
MODIFYING_ACTIONS = frozenset(
    {
        "DURABLE_RECORD_WRITE",
        "SOURCE_BRANCH_WRITE",
        "SOURCE_MERGE",
        "EXECUTIVE_CHILD_COMMISSION",
        "REVERSIBLE_RUNTIME_CANARY",
        "PROGRAM_START",
        "PROGRAM_PAUSE",
        "PROGRAM_RESUME",
        "PROGRAM_RETIRE",
        "PROGRAM_COMBINE",
        "PROGRAM_SPLIT",
        "RESOURCE_REALLOCATION",
        "ORGANIZATIONAL_RESTRUCTURE",
        "PRODUCTION_DEPLOY",
        "LIVE_CAPITAL_EXECUTION",
        "CONSTITUTION_CHANGE",
        "TERMINAL_OBJECTIVE_CHANGE",
        "BUDGET_EXPANSION",
        "ADMIN_INFRASTRUCTURE",
    }
)
ALL_ACTIONS = READ_ONLY_ACTIONS | MODIFYING_ACTIONS
NEW_CHILD_ACTIONS = frozenset({"EXECUTIVE_CHILD_COMMISSION", "PROGRAM_START"})

ALWAYS_CHAIRMAN_ACTIONS = frozenset(
    {
        "CONSTITUTION_CHANGE",
        "TERMINAL_OBJECTIVE_CHANGE",
        "BUDGET_EXPANSION",
        "ADMIN_INFRASTRUCTURE",
    }
)


class ChairmanCognitionError(ValueError):
    """The closed Chairman-cognition input is malformed."""


class SourceState(str, enum.Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    CONFLICT = "CONFLICT"
    UNKNOWN = "UNKNOWN"


class EffectState(str, enum.Enum):
    NONE = "NONE"
    KNOWN_APPLIED = "KNOWN_APPLIED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"


class CarrierState(str, enum.Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXACT_EXISTING = "EXACT_EXISTING"
    NEW_CHILD = "NEW_CHILD"
    AMBIGUOUS = "AMBIGUOUS"


class Reversibility(str, enum.Enum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE = "REVERSIBLE"
    COSTLY_REVERSIBLE = "COSTLY_REVERSIBLE"
    IRREVERSIBLE = "IRREVERSIBLE"
    UNKNOWN = "UNKNOWN"


class EnvelopeMode(str, enum.Enum):
    SUPERVISED_LIVE_CANARY = "SUPERVISED_LIVE_CANARY"
    BOUNDED_AUTONOMOUS = "BOUNDED_AUTONOMOUS"


class EnvelopeState(str, enum.Enum):
    MISSING = "MISSING"
    ACCEPTED = "ACCEPTED"
    SOURCE_NOT_CURRENT = "SOURCE_NOT_CURRENT"
    EXPIRED = "EXPIRED"


class Disposition(str, enum.Enum):
    READ_ONLY_ELIGIBLE = "READ_ONLY_ELIGIBLE"
    ELIGIBLE_WITHIN_DELEGATION = "ELIGIBLE_WITHIN_DELEGATION"
    CHAIRMAN_REQUIRED = "CHAIRMAN_REQUIRED"
    REFUSED = "REFUSED"


class ReasonCode(str, enum.Enum):
    READ_ONLY_INHERENT = "READ_ONLY_INHERENT"
    EXPLICIT_DELEGATION_ENVELOPE = "EXPLICIT_DELEGATION_ENVELOPE"
    MISSING_DELEGATION_ENVELOPE = "MISSING_DELEGATION_ENVELOPE"
    ENVELOPE_SOURCE_NOT_CURRENT = "ENVELOPE_SOURCE_NOT_CURRENT"
    ENVELOPE_EXPIRED = "ENVELOPE_EXPIRED"
    ACTION_NOT_DELEGATED = "ACTION_NOT_DELEGATED"
    SOURCE_NOT_CURRENT = "SOURCE_NOT_CURRENT"
    EFFECT_UNKNOWN_RECONCILE_FIRST = "EFFECT_UNKNOWN_RECONCILE_FIRST"
    EFFECT_ALREADY_APPLIED = "EFFECT_ALREADY_APPLIED"
    DUPLICATE_CONTROL_PLANE_REFUSED = "DUPLICATE_CONTROL_PLANE_REFUSED"
    STRATEGIC_CONSTRAINT_PROHIBITS = "STRATEGIC_CONSTRAINT_PROHIBITS"
    STRATEGIC_CONSTRAINT_REQUIRES_CHAIRMAN = (
        "STRATEGIC_CONSTRAINT_REQUIRES_CHAIRMAN"
    )
    CONSTITUTIONAL_CHAIRMAN_BOUNDARY = "CONSTITUTIONAL_CHAIRMAN_BOUNDARY"
    IRREVERSIBLE_REQUIRES_CHAIRMAN = "IRREVERSIBLE_REQUIRES_CHAIRMAN"
    REVERSIBILITY_NOT_DELEGATED = "REVERSIBILITY_NOT_DELEGATED"
    SCOPE_OUTSIDE_ENVELOPE = "SCOPE_OUTSIDE_ENVELOPE"
    BUDGET_EXCEEDS_ENVELOPE = "BUDGET_EXCEEDS_ENVELOPE"
    ACTIVE_CHILDREN_EXCEED_ENVELOPE = "ACTIVE_CHILDREN_EXCEED_ENVELOPE"
    EXACT_CARRIER_REQUIRED = "EXACT_CARRIER_REQUIRED"
    STABLE_OPERATION_REQUIRED = "STABLE_OPERATION_REQUIRED"
    EXPECTED_HEAD_REQUIRED = "EXPECTED_HEAD_REQUIRED"
    NEW_CHILD_CARRIER_REQUIRED = "NEW_CHILD_CARRIER_REQUIRED"
    CANARY_CONTROLS_REQUIRED = "CANARY_CONTROLS_REQUIRED"


@dataclasses.dataclass(frozen=True)
class SourceReceipt:
    source_ref: str
    owner: str
    revision: str
    state: SourceState
    load_bearing: bool
    observed_at: str


@dataclasses.dataclass(frozen=True)
class DelegationEnvelope:
    envelope_id: str
    authority_source_refs: tuple[str, ...]
    mode: EnvelopeMode
    allowed_actions: frozenset[str]
    allowed_reversibility: frozenset[Reversibility]
    allowed_repositories: frozenset[str]
    allowed_path_prefixes: Mapping[str, tuple[str, ...]]
    allowed_scope_prefixes: tuple[str, ...]
    allowed_carrier_prefixes: tuple[str, ...]
    max_budget_units: int
    max_active_children: int
    require_exact_carrier: bool
    expires_at: str


@dataclasses.dataclass(frozen=True)
class StrategicOption:
    option_id: str
    title: str
    action: str
    reversibility: Reversibility
    source_refs: tuple[str, ...]
    scope_refs: tuple[str, ...]
    effect_state: EffectState
    operation_key: str | None
    carrier_state: CarrierState
    carrier_ref: str | None
    expected_head_sha: str | None
    repositories: tuple[str, ...]
    paths: tuple[str, ...]
    budget_units: int
    active_children_after: int
    creates_duplicate_control_plane: bool
    stop_condition: str | None
    rollback_plan: str | None
    falsifier: str | None
    benefits: Mapping[str, int | None]
    costs: Mapping[str, int | None]


@dataclasses.dataclass(frozen=True)
class Adjudication:
    option_id: str
    disposition: Disposition
    reason: ReasonCode
    serviceable: bool
    source_state: SourceState
    execution_authority_granted: bool = False


def evaluate_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and evaluate one closed Chairman-cognition input document.

    The returned packet is deterministic and contains no reusable authority token.
    It can support a Meta-CEO decision, but the actual owner of any effect must re-read
    canonical evidence and enforce its existing mutation contract.
    """

    doc = _closed_mapping(
        document,
        required={
            "schema",
            "as_of",
            "source_receipts",
            "strategic_constraints",
            "delegation_envelope",
            "options",
        },
        optional=set(),
        where="document",
    )
    if doc["schema"] != INPUT_SCHEMA:
        raise ChairmanCognitionError("unsupported input schema")
    as_of = _iso_utc(doc["as_of"], "document.as_of")
    source_receipts = _parse_source_receipts(doc["source_receipts"])
    if any(
        _parse_time(receipt.observed_at) > _parse_time(as_of)
        for receipt in source_receipts.values()
    ):
        raise ChairmanCognitionError("source receipt cannot postdate document.as_of")
    strategic_constraints = _parse_constraints(doc["strategic_constraints"])
    envelope, envelope_state = _parse_envelope(
        doc["delegation_envelope"], source_receipts, as_of
    )
    options = _parse_options(doc["options"])

    source_refs = set(source_receipts)
    for option in options:
        missing = [ref for ref in option.source_refs if ref not in source_refs]
        if missing:
            raise ChairmanCognitionError(
                f"option {option.option_id} references unknown source receipt"
            )

    adjudications = tuple(
        _adjudicate(
            option=option,
            source_receipts=source_receipts,
            strategic_constraints=strategic_constraints,
            envelope=envelope,
            envelope_state=envelope_state,
        )
        for option in options
    )
    adjudication_by_id = {item.option_id: item for item in adjudications}

    strategic_frontier = _frontier(
        tuple(
            option
            for option in options
            if adjudication_by_id[option.option_id].source_state is SourceState.CURRENT
            and option.effect_state is EffectState.NONE
            and not option.creates_duplicate_control_plane
        )
    )
    actionable_frontier = _frontier(
        tuple(
            option
            for option in options
            if adjudication_by_id[option.option_id].disposition
            in {
                Disposition.READ_ONLY_ELIGIBLE,
                Disposition.ELIGIBLE_WITHIN_DELEGATION,
            }
        )
    )

    if len(actionable_frontier) == 1:
        selection_state = "UNIQUE_ACTIONABLE_FRONTIER"
        recommended_option_id: str | None = actionable_frontier[0]
    elif actionable_frontier:
        selection_state = "MULTIPLE_INCOMPARABLE_ACTIONABLE_OPTIONS"
        recommended_option_id = None
    else:
        selection_state = "NO_ACTIONABLE_FRONTIER"
        recommended_option_id = None

    packet: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "as_of": as_of,
        "input_digest": hashlib.sha256(canonical_json_bytes(doc)).hexdigest(),
        "delegation_envelope": {
            "state": envelope_state.value,
            "envelope_id": envelope.envelope_id if envelope is not None else None,
            "mode": envelope.mode.value if envelope is not None else None,
        },
        "strategic_frontier": list(strategic_frontier),
        "actionable_frontier": list(actionable_frontier),
        "selection_state": selection_state,
        "recommended_option_id": recommended_option_id,
        "adjudications": [
            {
                "option_id": item.option_id,
                "disposition": item.disposition.value,
                "reason": item.reason.value,
                "serviceable": item.serviceable,
                "source_state": item.source_state.value,
                "execution_authority_granted": False,
            }
            for item in adjudications
        ],
        "execution_authority_granted": False,
        "next_effect_requires_owner_revalidation": True,
    }
    packet["packet_digest"] = hashlib.sha256(canonical_json_bytes(packet)).hexdigest()
    return packet


def _parse_source_receipts(value: Any) -> dict[str, SourceReceipt]:
    if not isinstance(value, list) or not value or len(value) > MAX_SOURCE_RECEIPTS:
        raise ChairmanCognitionError("source_receipts must be a bounded non-empty list")
    out: dict[str, SourceReceipt] = {}
    for index, raw in enumerate(value):
        item = _closed_mapping(
            raw,
            required={
                "source_ref",
                "owner",
                "revision",
                "state",
                "load_bearing",
                "observed_at",
            },
            optional=set(),
            where=f"source_receipts[{index}]",
        )
        source_ref = _nonempty(item["source_ref"], "source_ref", 256)
        if source_ref in out:
            raise ChairmanCognitionError("duplicate source_ref")
        owner = _nonempty(item["owner"], "owner", 64)
        if owner not in ALLOWED_SOURCE_OWNERS:
            raise ChairmanCognitionError("unknown source owner")
        revision = _nonempty(item["revision"], "revision", 256)
        state = _enum(SourceState, item["state"], "source state")
        if type(item["load_bearing"]) is not bool:
            raise ChairmanCognitionError("load_bearing must be boolean")
        observed_at = _iso_utc(item["observed_at"], "observed_at")
        out[source_ref] = SourceReceipt(
            source_ref=source_ref,
            owner=owner,
            revision=revision,
            state=state,
            load_bearing=item["load_bearing"],
            observed_at=observed_at,
        )
    return out


def _parse_constraints(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ChairmanCognitionError("strategic_constraints must be a non-empty mapping")
    out: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _nonempty(raw_key, "constraint name", 128)
        level = _nonempty(raw_value, "constraint level", 32)
        if level not in {"permitted", "constrained", "prohibited"}:
            raise ChairmanCognitionError("unknown strategic constraint level")
        out[key] = level
    for required in (
        "autonomous_production_deploy",
        "autonomous_live_capital_execution",
        "duplicate_control_planes",
        "unbounded_autonomous_strategic_modification",
    ):
        if required not in out:
            raise ChairmanCognitionError("missing load-bearing strategic constraint")
    return out


def _parse_envelope(
    value: Any,
    source_receipts: Mapping[str, SourceReceipt],
    as_of: str,
) -> tuple[DelegationEnvelope | None, EnvelopeState]:
    if value is None:
        return None, EnvelopeState.MISSING
    item = _closed_mapping(
        value,
        required={
            "schema",
            "envelope_id",
            "authority_source_refs",
            "mode",
            "allowed_actions",
            "allowed_reversibility",
            "allowed_repositories",
            "allowed_path_prefixes",
            "allowed_scope_prefixes",
            "allowed_carrier_prefixes",
            "max_budget_units",
            "max_active_children",
            "require_exact_carrier",
            "expires_at",
        },
        optional=set(),
        where="delegation_envelope",
    )
    if item["schema"] != ENVELOPE_SCHEMA:
        raise ChairmanCognitionError("unsupported delegation envelope schema")
    envelope_id = _nonempty(item["envelope_id"], "envelope_id", 128)
    authority_source_refs = _str_tuple(
        item["authority_source_refs"], "authority_source_refs", 1, 8, 256
    )
    for ref in authority_source_refs:
        if ref not in source_receipts:
            raise ChairmanCognitionError("envelope references unknown authority source")
        if source_receipts[ref].owner != "CHAIRMAN_DIRECTIVE":
            raise ChairmanCognitionError(
                "delegation authority must come from Chairman directive"
            )
        if not source_receipts[ref].load_bearing:
            raise ChairmanCognitionError(
                "delegation authority source must be load-bearing"
            )
    mode = _enum(EnvelopeMode, item["mode"], "envelope mode")
    allowed_actions = frozenset(
        _str_tuple(item["allowed_actions"], "allowed_actions", 1, len(ALL_ACTIONS), 64)
    )
    if not allowed_actions <= ALL_ACTIONS:
        raise ChairmanCognitionError("envelope contains unknown action")
    allowed_reversibility = frozenset(
        _enum(Reversibility, raw, "allowed reversibility")
        for raw in _str_tuple(
            item["allowed_reversibility"], "allowed_reversibility", 1, 5, 32
        )
    )
    allowed_repositories = frozenset(
        _str_tuple(
            item["allowed_repositories"],
            "allowed_repositories",
            0,
            MAX_SCOPE_REPOSITORIES,
            160,
        )
    )
    prefixes_raw = item["allowed_path_prefixes"]
    if not isinstance(prefixes_raw, Mapping):
        raise ChairmanCognitionError("allowed_path_prefixes must be a mapping")
    prefixes: dict[str, tuple[str, ...]] = {}
    for repository, raw_prefixes in prefixes_raw.items():
        repo = _nonempty(repository, "allowed_path_prefixes repository", 160)
        if repo not in allowed_repositories:
            raise ChairmanCognitionError("path-prefix repository is not allowed")
        parsed = _str_tuple(raw_prefixes, "path prefixes", 0, MAX_SCOPE_PATHS, 240)
        for prefix in parsed:
            if _PATH_PREFIX_RE.fullmatch(prefix) is None:
                raise ChairmanCognitionError("invalid path prefix")
        prefixes[repo] = parsed
    allowed_scope_prefixes = _str_tuple(
        item["allowed_scope_prefixes"],
        "allowed_scope_prefixes",
        1,
        MAX_SCOPE_PREFIXES,
        256,
    )
    allowed_carrier_prefixes = _str_tuple(
        item["allowed_carrier_prefixes"],
        "allowed_carrier_prefixes",
        1,
        MAX_CARRIER_PREFIXES,
        256,
    )
    max_budget_units = _bounded_int(
        item["max_budget_units"], "max_budget_units", 0, MAX_BUDGET_UNITS
    )
    max_active_children = _bounded_int(
        item["max_active_children"],
        "max_active_children",
        0,
        MAX_ACTIVE_CHILDREN,
    )
    if item["require_exact_carrier"] is not True:
        raise ChairmanCognitionError(
            "delegation envelope must require exact carrier"
        )
    expires_at = _iso_utc(item["expires_at"], "expires_at")
    envelope = DelegationEnvelope(
        envelope_id=envelope_id,
        authority_source_refs=authority_source_refs,
        mode=mode,
        allowed_actions=allowed_actions,
        allowed_reversibility=allowed_reversibility,
        allowed_repositories=allowed_repositories,
        allowed_path_prefixes=prefixes,
        allowed_scope_prefixes=allowed_scope_prefixes,
        allowed_carrier_prefixes=allowed_carrier_prefixes,
        max_budget_units=max_budget_units,
        max_active_children=max_active_children,
        require_exact_carrier=item["require_exact_carrier"],
        expires_at=expires_at,
    )
    source_state = _aggregate_source_state(
        tuple(source_receipts[ref] for ref in authority_source_refs)
    )
    if source_state is not SourceState.CURRENT:
        return envelope, EnvelopeState.SOURCE_NOT_CURRENT
    if _parse_time(expires_at) <= _parse_time(as_of):
        return envelope, EnvelopeState.EXPIRED
    return envelope, EnvelopeState.ACCEPTED


def _parse_options(value: Any) -> tuple[StrategicOption, ...]:
    if not isinstance(value, list) or not value or len(value) > MAX_OPTIONS:
        raise ChairmanCognitionError("options must be a bounded non-empty list")
    out: list[StrategicOption] = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        item = _closed_mapping(
            raw,
            required={
                "option_id",
                "title",
                "action",
                "reversibility",
                "source_refs",
                "scope_refs",
                "effect_state",
                "operation_key",
                "carrier_state",
                "carrier_ref",
                "expected_head_sha",
                "repositories",
                "paths",
                "budget_units",
                "active_children_after",
                "creates_duplicate_control_plane",
                "stop_condition",
                "rollback_plan",
                "falsifier",
                "benefits",
                "costs",
            },
            optional=set(),
            where=f"options[{index}]",
        )
        option_id = _nonempty(item["option_id"], "option_id", 128)
        if _OPTION_ID_RE.fullmatch(option_id) is None:
            raise ChairmanCognitionError("invalid option_id")
        if option_id in seen:
            raise ChairmanCognitionError("duplicate option_id")
        seen.add(option_id)
        action = _nonempty(item["action"], "action", 64)
        if action not in ALL_ACTIONS:
            raise ChairmanCognitionError("unknown option action")
        effect_state = _enum(
            EffectState, item["effect_state"], "effect_state"
        )
        reversibility = _enum(
            Reversibility, item["reversibility"], "reversibility"
        )
        if action in READ_ONLY_ACTIONS and reversibility is not Reversibility.READ_ONLY:
            raise ChairmanCognitionError("read-only action must use READ_ONLY reversibility")
        if action in MODIFYING_ACTIONS and reversibility is Reversibility.READ_ONLY:
            raise ChairmanCognitionError("modifying action cannot use READ_ONLY reversibility")
        if action in READ_ONLY_ACTIONS and effect_state is not EffectState.NONE:
            raise ChairmanCognitionError(
                "read-only action must use NONE effect_state"
            )
        scope_refs = _str_tuple(
            item["scope_refs"], "scope_refs", 0, MAX_SCOPE_REFS, 256
        )
        if action in MODIFYING_ACTIONS and not scope_refs:
            raise ChairmanCognitionError(
                "modifying action requires at least one scope_ref"
            )
        operation_key = _nullable_str(item["operation_key"], "operation_key", 192)
        if operation_key is not None and _OPERATION_KEY_RE.fullmatch(operation_key) is None:
            raise ChairmanCognitionError("invalid operation_key")
        expected_head_sha = _nullable_str(
            item["expected_head_sha"], "expected_head_sha", 40
        )
        if expected_head_sha is not None and _SHA_RE.fullmatch(expected_head_sha) is None:
            raise ChairmanCognitionError("invalid expected_head_sha")
        repositories = _str_tuple(
            item["repositories"],
            "repositories",
            0,
            MAX_SCOPE_REPOSITORIES,
            160,
        )
        paths = _str_tuple(item["paths"], "paths", 0, MAX_SCOPE_PATHS, 240)
        for path in paths:
            if _PATH_PREFIX_RE.fullmatch(path) is None:
                raise ChairmanCognitionError("invalid scope path")
        if paths and not repositories:
            raise ChairmanCognitionError("paths require at least one repository")
        if action in {"SOURCE_BRANCH_WRITE", "SOURCE_MERGE"} and (
            len(repositories) != 1 or not paths
        ):
            raise ChairmanCognitionError(
                "source actions require one repository and explicit paths"
            )
        if type(item["creates_duplicate_control_plane"]) is not bool:
            raise ChairmanCognitionError(
                "creates_duplicate_control_plane must be boolean"
            )
        carrier_state = _enum(
            CarrierState, item["carrier_state"], "carrier_state"
        )
        carrier_ref = _nullable_str(item["carrier_ref"], "carrier_ref", 256)
        if carrier_state is CarrierState.EXACT_EXISTING and carrier_ref is None:
            raise ChairmanCognitionError("exact existing carrier requires carrier_ref")
        if (
            carrier_state in {CarrierState.NOT_APPLICABLE, CarrierState.NEW_CHILD}
            and carrier_ref is not None
        ):
            raise ChairmanCognitionError(
                "carrier_ref is not valid for this carrier_state"
            )
        out.append(
            StrategicOption(
                option_id=option_id,
                title=_nonempty(item["title"], "title", 240),
                action=action,
                reversibility=reversibility,
                source_refs=_str_tuple(
                    item["source_refs"],
                    "source_refs",
                    1,
                    MAX_SOURCE_REFS_PER_OPTION,
                    256,
                ),
                scope_refs=scope_refs,
                effect_state=effect_state,
                operation_key=operation_key,
                carrier_state=carrier_state,
                carrier_ref=carrier_ref,
                expected_head_sha=expected_head_sha,
                repositories=repositories,
                paths=paths,
                budget_units=_bounded_int(
                    item["budget_units"], "budget_units", 0, MAX_BUDGET_UNITS
                ),
                active_children_after=_bounded_int(
                    item["active_children_after"],
                    "active_children_after",
                    0,
                    MAX_ACTIVE_CHILDREN,
                ),
                creates_duplicate_control_plane=item[
                    "creates_duplicate_control_plane"
                ],
                stop_condition=_nullable_str(
                    item["stop_condition"], "stop_condition", 500
                ),
                rollback_plan=_nullable_str(
                    item["rollback_plan"], "rollback_plan", 500
                ),
                falsifier=_nullable_str(item["falsifier"], "falsifier", 500),
                benefits=_parse_dimensions(
                    item["benefits"], BENEFIT_DIMENSIONS, "benefits"
                ),
                costs=_parse_dimensions(item["costs"], COST_DIMENSIONS, "costs"),
            )
        )
    return tuple(out)


def _adjudicate(
    *,
    option: StrategicOption,
    source_receipts: Mapping[str, SourceReceipt],
    strategic_constraints: Mapping[str, str],
    envelope: DelegationEnvelope | None,
    envelope_state: EnvelopeState,
) -> Adjudication:
    source_state = _aggregate_source_state(
        tuple(source_receipts[ref] for ref in option.source_refs)
    )
    if source_state is not SourceState.CURRENT:
        return _decision(
            option, Disposition.REFUSED, ReasonCode.SOURCE_NOT_CURRENT, source_state
        )
    if option.effect_state is EffectState.EFFECT_UNKNOWN:
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.EFFECT_UNKNOWN_RECONCILE_FIRST,
            source_state,
        )
    if option.effect_state is EffectState.KNOWN_APPLIED:
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.EFFECT_ALREADY_APPLIED,
            source_state,
        )
    if option.creates_duplicate_control_plane:
        if strategic_constraints["duplicate_control_planes"] == "prohibited":
            return _decision(
                option,
                Disposition.REFUSED,
                ReasonCode.DUPLICATE_CONTROL_PLANE_REFUSED,
                source_state,
            )
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.CONSTITUTIONAL_CHAIRMAN_BOUNDARY,
            source_state,
        )
    if option.action == "PRODUCTION_DEPLOY" and strategic_constraints.get(
        "autonomous_production_deploy"
    ) == "prohibited":
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.STRATEGIC_CONSTRAINT_PROHIBITS,
            source_state,
        )
    if option.action == "LIVE_CAPITAL_EXECUTION" and strategic_constraints.get(
        "autonomous_live_capital_execution"
    ) == "prohibited":
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.STRATEGIC_CONSTRAINT_PROHIBITS,
            source_state,
        )
    if option.action in ALWAYS_CHAIRMAN_ACTIONS:
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.CONSTITUTIONAL_CHAIRMAN_BOUNDARY,
            source_state,
        )
    if option.reversibility in {Reversibility.IRREVERSIBLE, Reversibility.UNKNOWN}:
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.IRREVERSIBLE_REQUIRES_CHAIRMAN,
            source_state,
        )
    if option.action in READ_ONLY_ACTIONS:
        return _decision(
            option,
            Disposition.READ_ONLY_ELIGIBLE,
            ReasonCode.READ_ONLY_INHERENT,
            source_state,
            serviceable=True,
        )

    if envelope is None or envelope_state is EnvelopeState.MISSING:
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.MISSING_DELEGATION_ENVELOPE,
            source_state,
        )
    if envelope_state is EnvelopeState.SOURCE_NOT_CURRENT:
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.ENVELOPE_SOURCE_NOT_CURRENT,
            source_state,
        )
    if envelope_state is EnvelopeState.EXPIRED:
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.ENVELOPE_EXPIRED,
            source_state,
        )
    if envelope.mode is EnvelopeMode.BOUNDED_AUTONOMOUS:
        autonomous_level = strategic_constraints[
            "unbounded_autonomous_strategic_modification"
        ]
        if autonomous_level == "prohibited":
            return _decision(
                option,
                Disposition.REFUSED,
                ReasonCode.STRATEGIC_CONSTRAINT_PROHIBITS,
                source_state,
            )
        if autonomous_level == "constrained":
            return _decision(
                option,
                Disposition.CHAIRMAN_REQUIRED,
                ReasonCode.STRATEGIC_CONSTRAINT_REQUIRES_CHAIRMAN,
                source_state,
            )
    if option.action not in envelope.allowed_actions:
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.ACTION_NOT_DELEGATED,
            source_state,
        )
    if option.reversibility not in envelope.allowed_reversibility:
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.REVERSIBILITY_NOT_DELEGATED,
            source_state,
        )
    if not _refs_allowed(option.scope_refs, envelope.allowed_scope_prefixes):
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.SCOPE_OUTSIDE_ENVELOPE,
            source_state,
        )
    if option.budget_units > envelope.max_budget_units:
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.BUDGET_EXCEEDS_ENVELOPE,
            source_state,
        )
    if option.active_children_after > envelope.max_active_children:
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.ACTIVE_CHILDREN_EXCEED_ENVELOPE,
            source_state,
        )
    if not _scope_allowed(option, envelope):
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.SCOPE_OUTSIDE_ENVELOPE,
            source_state,
        )
    if option.operation_key is None:
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.STABLE_OPERATION_REQUIRED,
            source_state,
        )
    if option.action == "SOURCE_MERGE" and option.expected_head_sha is None:
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.EXPECTED_HEAD_REQUIRED,
            source_state,
        )
    if (
        option.action in NEW_CHILD_ACTIONS
        and option.carrier_state is not CarrierState.NEW_CHILD
    ):
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.NEW_CHILD_CARRIER_REQUIRED,
            source_state,
        )
    if (
        option.action not in NEW_CHILD_ACTIONS
        and option.carrier_state is not CarrierState.EXACT_EXISTING
    ):
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.EXACT_CARRIER_REQUIRED,
            source_state,
        )
    if (
        option.carrier_ref is not None
        and not _refs_allowed(
            (option.carrier_ref,), envelope.allowed_carrier_prefixes
        )
    ):
        return _decision(
            option,
            Disposition.CHAIRMAN_REQUIRED,
            ReasonCode.SCOPE_OUTSIDE_ENVELOPE,
            source_state,
        )
    if option.carrier_state is CarrierState.AMBIGUOUS:
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.EXACT_CARRIER_REQUIRED,
            source_state,
        )
    requires_canary_controls = (
        option.action == "REVERSIBLE_RUNTIME_CANARY"
        or envelope.mode is EnvelopeMode.SUPERVISED_LIVE_CANARY
    )
    if requires_canary_controls and not all(
        (option.stop_condition, option.rollback_plan, option.falsifier)
    ):
        return _decision(
            option,
            Disposition.REFUSED,
            ReasonCode.CANARY_CONTROLS_REQUIRED,
            source_state,
        )
    return _decision(
        option,
        Disposition.ELIGIBLE_WITHIN_DELEGATION,
        ReasonCode.EXPLICIT_DELEGATION_ENVELOPE,
        source_state,
        serviceable=True,
    )


def _decision(
    option: StrategicOption,
    disposition: Disposition,
    reason: ReasonCode,
    source_state: SourceState,
    *,
    serviceable: bool = False,
) -> Adjudication:
    return Adjudication(
        option_id=option.option_id,
        disposition=disposition,
        reason=reason,
        serviceable=serviceable,
        source_state=source_state,
        execution_authority_granted=False,
    )


def _refs_allowed(refs: Sequence[str], prefixes: Sequence[str]) -> bool:
    return all(any(ref.startswith(prefix) for prefix in prefixes) for ref in refs)


def _scope_allowed(option: StrategicOption, envelope: DelegationEnvelope) -> bool:
    if option.repositories and not set(option.repositories) <= envelope.allowed_repositories:
        return False
    if not option.paths:
        return True
    if len(option.repositories) != 1:
        return False
    repository = option.repositories[0]
    prefixes = envelope.allowed_path_prefixes.get(repository, ())
    return bool(prefixes) and all(
        any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)
        for path in option.paths
    )


def _frontier(options: tuple[StrategicOption, ...]) -> tuple[str, ...]:
    frontier: list[str] = []
    for candidate in sorted(options, key=lambda item: item.option_id):
        if any(
            other.option_id != candidate.option_id and _dominates(other, candidate)
            for other in options
        ):
            continue
        frontier.append(candidate.option_id)
    return tuple(frontier)


def _dominates(left: StrategicOption, right: StrategicOption) -> bool:
    better = False
    for key in BENEFIT_DIMENSIONS:
        lval, rval = left.benefits[key], right.benefits[key]
        if lval is None or rval is None:
            return False
        if lval < rval:
            return False
        better = better or lval > rval
    for key in COST_DIMENSIONS:
        lval, rval = left.costs[key], right.costs[key]
        if lval is None or rval is None:
            return False
        if lval > rval:
            return False
        better = better or lval < rval
    return better


def _aggregate_source_state(receipts: Sequence[SourceReceipt]) -> SourceState:
    load_bearing = [receipt for receipt in receipts if receipt.load_bearing]
    relevant = load_bearing or list(receipts)
    states = {receipt.state for receipt in relevant}
    if SourceState.CONFLICT in states:
        return SourceState.CONFLICT
    if SourceState.UNKNOWN in states:
        return SourceState.UNKNOWN
    if SourceState.STALE in states:
        return SourceState.STALE
    return SourceState.CURRENT


def _parse_dimensions(
    value: Any, expected_keys: Sequence[str], where: str
) -> dict[str, int | None]:
    item = _closed_mapping(
        value,
        required=set(expected_keys),
        optional=set(),
        where=where,
    )
    out: dict[str, int | None] = {}
    for key in expected_keys:
        raw = item[key]
        if raw is None:
            out[key] = None
        else:
            out[key] = _bounded_int(raw, f"{where}.{key}", 0, 100)
    return out


def _closed_mapping(
    value: Any,
    *,
    required: set[str],
    optional: set[str],
    where: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ChairmanCognitionError(f"{where} must be a mapping")
    keys = set(value)
    missing = required - keys
    extra = keys - required - optional
    if missing:
        raise ChairmanCognitionError(f"{where} is missing required fields")
    if extra:
        raise ChairmanCognitionError(f"{where} contains unknown fields")
    return value


def _str_tuple(
    value: Any,
    name: str,
    minimum: int,
    maximum: int,
    max_len: int,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ChairmanCognitionError(f"{name} must be a bounded list")
    out = tuple(_nonempty(item, name, max_len) for item in value)
    if len(set(out)) != len(out):
        raise ChairmanCognitionError(f"{name} contains duplicates")
    return out


def _nonempty(value: Any, name: str, max_len: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ChairmanCognitionError(f"{name} must be a non-empty trimmed string")
    if len(value) > max_len or any(ord(ch) < 32 for ch in value):
        raise ChairmanCognitionError(f"{name} is out of bounds")
    return value


def _nullable_str(value: Any, name: str, max_len: int) -> str | None:
    if value is None:
        return None
    return _nonempty(value, name, max_len)


def _bounded_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ChairmanCognitionError(f"{name} must be a bounded integer")
    return value


def _enum(enum_type: type[enum.Enum], value: Any, name: str):
    if not isinstance(value, str):
        raise ChairmanCognitionError(f"{name} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ChairmanCognitionError(f"unknown {name}") from exc


def _iso_utc(value: Any, name: str) -> str:
    text = _nonempty(value, name, 40)
    if _ISO_UTC_RE.fullmatch(text) is None:
        raise ChairmanCognitionError(f"{name} must be UTC ISO-8601")
    _parse_time(text)
    return text


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ChairmanCognitionError("timestamp must use UTC")
    return parsed


__all__ = [
    "BENEFIT_DIMENSIONS",
    "COST_DIMENSIONS",
    "CarrierState",
    "ChairmanCognitionError",
    "Disposition",
    "EffectState",
    "ENVELOPE_SCHEMA",
    "EnvelopeMode",
    "INPUT_SCHEMA",
    "PACKET_SCHEMA",
    "ReasonCode",
    "Reversibility",
    "SourceState",
    "evaluate_document",
]
