"""Fail-closed effective-tool preflight for attended Web CEO placement.

This module closes one narrow gap between Web-session observation and the
existing Capacity placement/commitment path. It does not discover ChatGPT
tools, grant authority, mutate Capacity, create RuntimeBindings, select a
provider, or perform a retry/failover. It consumes a point-in-time capability
receipt bound to the exact current RuntimeBinding and effective-action scope
produced by accepted owners, then determines whether the already-selected
attended Web CEO may cross the pre-START placement-commitment boundary.

The important asymmetry is deliberate:

* an absent required capability may exclude a PRE_START/effect=NONE candidate;
* an unknown capability never widens authority or causes automatic rebinding;
* schema presence alone never proves a positive capability; a successful
  current-action-scope no-effect serviceability probe is required;
* after START, or while an effect is unknown, the current binding stays sticky.

The real effectful consumer is still the existing Capacity-C2 commitment
contract. The guarded commitment helper simply refuses to call that owner
unless this preflight is READY and bound to the selected worker/quota, current
RuntimeBinding, and current effective-action scope.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from control_plane import executive_placement_commitment as c2
from control_plane import executive_placement_selection as c1
from control_plane.executive_steward import EffectState


RECEIPT_SCHEMA = "mastermind.web_ceo_session_capability_receipt.v2"
PREFLIGHT_SCHEMA = "mastermind.web_ceo_session_capability_preflight.v2"
MAX_RECEIPT_TTL_MS = 300_000

_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CAPABILITY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,95}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "worker_id",
        "quota_class",
        "session_ref",
        "binding_ref",
        "binding_generation",
        "action_scope_ref",
        "observed_at_ms",
        "expires_at_ms",
        "schema_complete",
        "tool_schema_digest",
        "capability_contract_digest",
        "observer_evidence_digest",
        "serviceability_evidence_digest",
        "observations",
        "evidence_digest",
    }
)
_OBSERVATION_KEYS = frozenset({"name", "state", "proof_class"})

KNOWN_EFFECTIVE_CAPABILITIES = (
    "desktop_commander_command",
    "desktop_commander_read",
    "desktop_commander_write",
    "executive_read",
    "executive_submit",
    "github_read",
    "github_write",
    "studio_direct_command",
    "studio_direct_read",
    "studio_direct_write",
)
_KNOWN_EFFECTIVE_CAPABILITY_SET = frozenset(KNOWN_EFFECTIVE_CAPABILITIES)


class WebCeoSessionCapabilityError(ValueError):
    """Fixed, secret-safe refusal for Web CEO capability-preflight input."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _ValueEnum(str, enum.Enum):
    """String enum whose value is the public wire value."""


class CapabilityObservationState(_ValueEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class CapabilityProofClass(_ValueEnum):
    EFFECTIVE_SCHEMA = "effective_schema"
    NO_EFFECT_PROBE = "no_effect_probe"


class SessionStartState(_ValueEnum):
    PRE_START = "pre_start"
    STARTED = "started"


class ReceiverBindingMode(_ValueEnum):
    CAPACITY_SELECTABLE = "capacity_selectable"
    EXACT_SESSION_REQUIRED = "exact_session_required"


class PreflightState(_ValueEnum):
    READY = "ready"
    CAPABILITY_PROOF_REQUIRED = "capability_proof_required"
    PRESTART_REBIND_REQUIRED = "prestart_rebind_required"
    EXACT_SESSION_BLOCKED = "exact_session_blocked"
    STICKY_DEGRADED = "sticky_degraded"
    STARTED_STICKY = "started_sticky"
    STALE_EVIDENCE = "stale_evidence"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    EFFECT_UNKNOWN = "effect_unknown"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _token(value: object, *, code: str) -> str:
    if not isinstance(value, str) or _TOKEN_RE.fullmatch(value) is None:
        raise WebCeoSessionCapabilityError(code)
    return value


def _capability(value: object) -> str:
    if not isinstance(value, str) or _CAPABILITY_RE.fullmatch(value) is None:
        raise WebCeoSessionCapabilityError("CAPABILITY_NAME_INVALID")
    if value not in _KNOWN_EFFECTIVE_CAPABILITY_SET:
        raise WebCeoSessionCapabilityError("CAPABILITY_OUTSIDE_CLOSED_SET")
    return value


def _positive_int(value: object, *, code: str) -> int:
    if type(value) is not int or value < 1:
        raise WebCeoSessionCapabilityError(code)
    return value


def _enum(value: object, enum_type: type[_ValueEnum], *, code: str) -> _ValueEnum:
    if not isinstance(value, enum_type):
        raise WebCeoSessionCapabilityError(code)
    return value


def _tool_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 256
        or any(char.isspace() or ord(char) < 32 for char in value)
    ):
        raise WebCeoSessionCapabilityError("EFFECTIVE_TOOL_NAME_INVALID")
    return value


def _schema_digest(value: object) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise WebCeoSessionCapabilityError("INVOCATION_SCHEMA_DIGEST_INVALID")
    return value


@dataclasses.dataclass(frozen=True, slots=True, order=True)
class EffectiveToolDescriptor:
    """One exact connector action plus its reviewed invocation-contract digest."""

    tool_name: str
    invocation_schema_digest: str

    def __post_init__(self) -> None:
        _tool_name(self.tool_name)
        _schema_digest(self.invocation_schema_digest)

    def to_dict(self) -> dict[str, str]:
        return {
            "tool_name": self.tool_name,
            "invocation_schema_digest": self.invocation_schema_digest,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class ActionServiceabilityFact:
    """One exact no-effect connector/serviceability observation."""

    tool: EffectiveToolDescriptor
    session_ref: str
    binding_ref: str
    binding_generation: int
    action_scope_ref: str
    observed_at_ms: int
    expires_at_ms: int
    serviceable: bool
    evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.tool, EffectiveToolDescriptor):
            raise WebCeoSessionCapabilityError("SERVICEABILITY_FACT_INVALID")
        _token(self.session_ref, code="SERVICEABILITY_SESSION_REF_INVALID")
        _token(self.binding_ref, code="SERVICEABILITY_BINDING_REF_INVALID")
        _positive_int(
            self.binding_generation,
            code="SERVICEABILITY_BINDING_GENERATION_INVALID",
        )
        _token(
            self.action_scope_ref,
            code="SERVICEABILITY_ACTION_SCOPE_REF_INVALID",
        )
        observed = _positive_int(
            self.observed_at_ms,
            code="SERVICEABILITY_OBSERVED_AT_INVALID",
        )
        expires = _positive_int(
            self.expires_at_ms,
            code="SERVICEABILITY_EXPIRES_AT_INVALID",
        )
        if expires < observed or expires - observed > MAX_RECEIPT_TTL_MS:
            raise WebCeoSessionCapabilityError("SERVICEABILITY_FACT_TTL_INVALID")
        if type(self.serviceable) is not bool:
            raise WebCeoSessionCapabilityError("SERVICEABILITY_RESULT_INVALID")
        if (
            not isinstance(self.evidence_digest, str)
            or _DIGEST_RE.fullmatch(self.evidence_digest) is None
        ):
            raise WebCeoSessionCapabilityError("SERVICEABILITY_EVIDENCE_DIGEST_INVALID")

    def evidence_projection(self) -> dict[str, Any]:
        return {
            "tool": self.tool.to_dict(),
            "session_ref": self.session_ref,
            "binding_ref": self.binding_ref,
            "binding_generation": self.binding_generation,
            "action_scope_ref": self.action_scope_ref,
            "observed_at_ms": self.observed_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "serviceable": self.serviceable,
            "evidence_digest": self.evidence_digest,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class CapabilityActionContract:
    """Existing-owner exact action contract for one closed capability."""

    capability: str
    required_actions: tuple[EffectiveToolDescriptor, ...]

    def __post_init__(self) -> None:
        _capability(self.capability)
        if not isinstance(self.required_actions, tuple) or not self.required_actions:
            raise WebCeoSessionCapabilityError("CAPABILITY_ACTION_CONTRACT_INVALID")
        if any(
            not isinstance(item, EffectiveToolDescriptor)
            for item in self.required_actions
        ):
            raise WebCeoSessionCapabilityError("CAPABILITY_ACTION_CONTRACT_INVALID")
        normalized = tuple(sorted(self.required_actions))
        if len(set(normalized)) != len(normalized):
            raise WebCeoSessionCapabilityError("CAPABILITY_ACTION_CONTRACT_INVALID")
        if len({item.tool_name for item in normalized}) != len(normalized):
            raise WebCeoSessionCapabilityError("CAPABILITY_ACTION_NAME_DUPLICATE")
        object.__setattr__(self, "required_actions", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "required_actions": [item.to_dict() for item in self.required_actions],
        }


def _normalize_tool_descriptors(
    values: Sequence[EffectiveToolDescriptor],
) -> tuple[EffectiveToolDescriptor, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise WebCeoSessionCapabilityError("EFFECTIVE_TOOL_SCHEMA_INVALID")
    if any(not isinstance(item, EffectiveToolDescriptor) for item in values):
        raise WebCeoSessionCapabilityError("EFFECTIVE_TOOL_SCHEMA_INVALID")
    normalized = tuple(sorted(values))
    if len(set(normalized)) != len(normalized):
        raise WebCeoSessionCapabilityError("DUPLICATE_EFFECTIVE_TOOL_DESCRIPTOR")
    if len({item.tool_name for item in normalized}) != len(normalized):
        raise WebCeoSessionCapabilityError("DUPLICATE_EFFECTIVE_TOOL_NAME")
    return normalized


def _normalize_capability_contracts(
    values: Sequence[CapabilityActionContract],
) -> tuple[CapabilityActionContract, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise WebCeoSessionCapabilityError("CAPABILITY_ACTION_CONTRACTS_INVALID")
    if any(not isinstance(item, CapabilityActionContract) for item in values):
        raise WebCeoSessionCapabilityError("CAPABILITY_ACTION_CONTRACTS_INVALID")
    by_name = {item.capability: item for item in values}
    if len(by_name) != len(values):
        raise WebCeoSessionCapabilityError("DUPLICATE_CAPABILITY_ACTION_CONTRACT")
    if set(by_name) != _KNOWN_EFFECTIVE_CAPABILITY_SET:
        raise WebCeoSessionCapabilityError("CAPABILITY_ACTION_CONTRACTS_INCOMPLETE")
    return tuple(by_name[name] for name in KNOWN_EFFECTIVE_CAPABILITIES)


def _surface_state_for_contract(
    *,
    effective: tuple[EffectiveToolDescriptor, ...],
    contract: CapabilityActionContract,
    schema_complete: bool,
) -> CapabilityObservationState:
    by_name = {item.tool_name: item for item in effective}
    saw_missing = False
    for required in contract.required_actions:
        actual = by_name.get(required.tool_name)
        if actual is None:
            saw_missing = True
            continue
        if actual.invocation_schema_digest != required.invocation_schema_digest:
            return CapabilityObservationState.UNKNOWN
    if saw_missing:
        return (
            CapabilityObservationState.ABSENT
            if schema_complete
            else CapabilityObservationState.UNKNOWN
        )
    return CapabilityObservationState.PRESENT


@dataclasses.dataclass(frozen=True, slots=True)
class CapabilityObservation:
    """One capability observation, with a closed non-prose proof class."""

    name: str
    state: CapabilityObservationState
    proof_class: CapabilityProofClass

    def __post_init__(self) -> None:
        _capability(self.name)
        _enum(
            self.state,
            CapabilityObservationState,
            code="CAPABILITY_OBSERVATION_STATE_INVALID",
        )
        _enum(
            self.proof_class,
            CapabilityProofClass,
            code="CAPABILITY_PROOF_CLASS_INVALID",
        )
        if (
            self.state is CapabilityObservationState.PRESENT
            and self.proof_class is not CapabilityProofClass.NO_EFFECT_PROBE
        ):
            raise WebCeoSessionCapabilityError(
                "PRESENT_REQUIRES_SERVICEABILITY_PROOF"
            )
        if (
            self.state is CapabilityObservationState.ABSENT
            and self.proof_class is not CapabilityProofClass.EFFECTIVE_SCHEMA
        ):
            raise WebCeoSessionCapabilityError("ABSENCE_REQUIRES_SCHEMA_PROOF")

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "state": self.state.value,
            "proof_class": self.proof_class.value,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class WebCeoSessionCapabilityReceipt:
    """Exact-action-scope point-in-time effective-tool evidence.

    ``action_scope_ref`` is an opaque provider/host observation scope that must
    change whenever the effective action set can change. On ChatGPT it must be
    no broader than the message-scoped app/action selection. ``session_ref`` or
    RuntimeBinding generation alone cannot prove that surface. ``schema_complete``
    therefore applies only to this exact action scope. A failed/no-effect probe
    can prove presence or uncertainty but cannot prove that an unobserved tool
    is absent.
    """

    worker_id: str
    quota_class: str
    session_ref: str
    binding_ref: str
    binding_generation: int
    action_scope_ref: str
    observed_at_ms: int
    expires_at_ms: int
    schema_complete: bool
    tool_schema_digest: str
    capability_contract_digest: str
    observer_evidence_digest: str
    serviceability_evidence_digest: str
    observations: tuple[CapabilityObservation, ...]

    def __post_init__(self) -> None:
        _token(self.worker_id, code="WORKER_ID_INVALID")
        _token(self.quota_class, code="QUOTA_CLASS_INVALID")
        _token(self.session_ref, code="SESSION_REF_INVALID")
        _token(self.binding_ref, code="BINDING_REF_INVALID")
        _positive_int(self.binding_generation, code="BINDING_GENERATION_INVALID")
        _token(self.action_scope_ref, code="ACTION_SCOPE_REF_INVALID")
        observed = _positive_int(self.observed_at_ms, code="OBSERVED_AT_INVALID")
        expires = _positive_int(self.expires_at_ms, code="EXPIRES_AT_INVALID")
        if expires < observed or expires - observed > MAX_RECEIPT_TTL_MS:
            raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_TTL_INVALID")
        if type(self.schema_complete) is not bool:
            raise WebCeoSessionCapabilityError("SCHEMA_COMPLETENESS_INVALID")
        for digest_value, code in (
            (self.tool_schema_digest, "TOOL_SCHEMA_DIGEST_INVALID"),
            (
                self.capability_contract_digest,
                "CAPABILITY_CONTRACT_DIGEST_INVALID",
            ),
            (self.observer_evidence_digest, "OBSERVER_EVIDENCE_DIGEST_INVALID"),
            (
                self.serviceability_evidence_digest,
                "SERVICEABILITY_EVIDENCE_DIGEST_INVALID",
            ),
        ):
            if (
                not isinstance(digest_value, str)
                or _DIGEST_RE.fullmatch(digest_value) is None
            ):
                raise WebCeoSessionCapabilityError(code)
        if not isinstance(self.observations, tuple):
            raise WebCeoSessionCapabilityError("CAPABILITY_OBSERVATIONS_INVALID")
        normalized: list[CapabilityObservation] = []
        names: set[str] = set()
        for item in self.observations:
            if not isinstance(item, CapabilityObservation):
                raise WebCeoSessionCapabilityError("CAPABILITY_OBSERVATIONS_INVALID")
            if item.name in names:
                raise WebCeoSessionCapabilityError("DUPLICATE_CAPABILITY_OBSERVATION")
            if item.name not in _KNOWN_EFFECTIVE_CAPABILITY_SET:
                raise WebCeoSessionCapabilityError(
                    "CAPABILITY_OUTSIDE_CLOSED_SET"
                )
            if (
                item.state is CapabilityObservationState.ABSENT
                and not self.schema_complete
            ):
                raise WebCeoSessionCapabilityError(
                    "ABSENCE_REQUIRES_COMPLETE_SCHEMA"
                )
            names.add(item.name)
            normalized.append(item)
        if self.schema_complete and names != _KNOWN_EFFECTIVE_CAPABILITY_SET:
            raise WebCeoSessionCapabilityError(
                "COMPLETE_SCHEMA_OBSERVATIONS_INCOMPLETE"
            )
        normalized.sort(key=lambda item: item.name)
        object.__setattr__(self, "observations", tuple(normalized))

    def _evidence_body(self) -> dict[str, Any]:
        return {
            "schema_version": RECEIPT_SCHEMA,
            "worker_id": self.worker_id,
            "quota_class": self.quota_class,
            "session_ref": self.session_ref,
            "binding_ref": self.binding_ref,
            "binding_generation": self.binding_generation,
            "action_scope_ref": self.action_scope_ref,
            "observed_at_ms": self.observed_at_ms,
            "expires_at_ms": self.expires_at_ms,
            "schema_complete": self.schema_complete,
            "tool_schema_digest": self.tool_schema_digest,
            "capability_contract_digest": self.capability_contract_digest,
            "observer_evidence_digest": self.observer_evidence_digest,
            "serviceability_evidence_digest": self.serviceability_evidence_digest,
            "observations": [item.to_dict() for item in self.observations],
        }

    @property
    def evidence_digest(self) -> str:
        return _digest(self._evidence_body())

    def to_dict(self) -> dict[str, Any]:
        value = self._evidence_body()
        value["evidence_digest"] = self.evidence_digest
        return value


def build_receipt_from_effective_tool_schema(
    *,
    effective_tools: Sequence[EffectiveToolDescriptor],
    capability_contracts: Sequence[CapabilityActionContract],
    schema_complete: bool,
    observer_evidence_digest: str,
    worker_id: str,
    quota_class: str,
    session_ref: str,
    binding_ref: str,
    binding_generation: int,
    action_scope_ref: str,
    observed_at_ms: int,
    expires_at_ms: int,
    action_serviceability: Sequence[ActionServiceabilityFact] | None = None,
) -> WebCeoSessionCapabilityReceipt:
    """Compose one short-lived exact-action-scope capability receipt.

    Existing owners supply the exact effective action descriptors, the reviewed
    closed capability contracts, one opaque action-surface scope, and no-effect
    serviceability facts. This pure compositor verifies their
    identity/generation/action-scope/schema/TTL intersection and emits only
    bounded digests plus closed capability observations. It owns no registry,
    lifecycle, permission, retry, or provider discovery.
    """

    _token(action_scope_ref, code="ACTION_SCOPE_REF_INVALID")
    effective = _normalize_tool_descriptors(effective_tools)
    contracts = _normalize_capability_contracts(capability_contracts)
    if type(schema_complete) is not bool:
        raise WebCeoSessionCapabilityError("SCHEMA_COMPLETENESS_INVALID")
    if (
        not isinstance(observer_evidence_digest, str)
        or _DIGEST_RE.fullmatch(observer_evidence_digest) is None
    ):
        raise WebCeoSessionCapabilityError("OBSERVER_EVIDENCE_DIGEST_INVALID")

    if action_serviceability is None:
        serviceability: tuple[ActionServiceabilityFact, ...] = ()
    elif (
        isinstance(action_serviceability, (str, bytes))
        or not isinstance(action_serviceability, Sequence)
        or any(
            not isinstance(item, ActionServiceabilityFact)
            for item in action_serviceability
        )
    ):
        raise WebCeoSessionCapabilityError("SERVICEABILITY_FACTS_INVALID")
    else:
        serviceability = tuple(
            sorted(action_serviceability, key=lambda item: item.tool.tool_name)
        )
    if len({item.tool.tool_name for item in serviceability}) != len(serviceability):
        raise WebCeoSessionCapabilityError("DUPLICATE_SERVICEABILITY_FACT")

    all_contract_actions = {
        action.tool_name: action
        for contract in contracts
        for action in contract.required_actions
    }
    if len(all_contract_actions) != sum(len(c.required_actions) for c in contracts):
        raise WebCeoSessionCapabilityError("CAPABILITY_ACTION_OWNERSHIP_AMBIGUOUS")

    facts_by_name: dict[str, ActionServiceabilityFact] = {}
    for fact in serviceability:
        expected = all_contract_actions.get(fact.tool.tool_name)
        if expected is None:
            raise WebCeoSessionCapabilityError(
                "SERVICEABILITY_FACT_OUTSIDE_CONTRACT"
            )
        if fact.tool != expected:
            raise WebCeoSessionCapabilityError(
                "SERVICEABILITY_FACT_SCHEMA_MISMATCH"
            )
        if (
            fact.session_ref != session_ref
            or fact.binding_ref != binding_ref
            or fact.binding_generation != binding_generation
            or fact.action_scope_ref != action_scope_ref
        ):
            raise WebCeoSessionCapabilityError(
                "SERVICEABILITY_FACT_BINDING_MISMATCH"
            )
        if (
            fact.observed_at_ms > observed_at_ms
            or fact.expires_at_ms < observed_at_ms
            or fact.expires_at_ms < expires_at_ms
        ):
            raise WebCeoSessionCapabilityError(
                "SERVICEABILITY_FACT_NOT_CURRENT_FOR_RECEIPT"
            )
        facts_by_name[fact.tool.tool_name] = fact

    observations: list[CapabilityObservation] = []
    for contract in contracts:
        surface_state = _surface_state_for_contract(
            effective=effective,
            contract=contract,
            schema_complete=schema_complete,
        )
        by_name = {item.tool_name: item for item in effective}
        bound_facts = [
            facts_by_name.get(action.tool_name)
            for action in contract.required_actions
        ]
        missing_actions = [
            action
            for action in contract.required_actions
            if by_name.get(action.tool_name) is None
        ]
        schema_drift = any(
            (
                actual := by_name.get(action.tool_name)
            ) is not None
            and actual.invocation_schema_digest
            != action.invocation_schema_digest
            for action in contract.required_actions
        )
        if surface_state is CapabilityObservationState.ABSENT:
            if any(
                (
                    fact := facts_by_name.get(action.tool_name)
                ) is not None
                and fact.serviceable is True
                for action in missing_actions
            ):
                raise WebCeoSessionCapabilityError(
                    "COMPLETE_SCHEMA_CONTRADICTS_POSITIVE_SERVICEABILITY"
                )
            if any(item is not None for item in bound_facts):
                raise WebCeoSessionCapabilityError(
                    "SERVICEABILITY_FACT_WITHOUT_SURFACE"
                )
            state = CapabilityObservationState.ABSENT
            proof = CapabilityProofClass.EFFECTIVE_SCHEMA
        elif surface_state is CapabilityObservationState.UNKNOWN:
            if schema_drift:
                if any(item is not None for item in bound_facts):
                    raise WebCeoSessionCapabilityError(
                        "SERVICEABILITY_FACT_WITH_SCHEMA_DRIFT"
                    )
                state = CapabilityObservationState.UNKNOWN
                proof = CapabilityProofClass.EFFECTIVE_SCHEMA
            elif all(
                item is not None and item.serviceable is True
                for item in bound_facts
            ):
                state = CapabilityObservationState.PRESENT
                proof = CapabilityProofClass.NO_EFFECT_PROBE
            elif any(
                item is not None and item.serviceable is False
                for item in bound_facts
            ):
                state = CapabilityObservationState.UNKNOWN
                proof = CapabilityProofClass.NO_EFFECT_PROBE
            else:
                state = CapabilityObservationState.UNKNOWN
                proof = CapabilityProofClass.EFFECTIVE_SCHEMA
        else:
            if all(
                item is not None and item.serviceable is True
                for item in bound_facts
            ):
                state = CapabilityObservationState.PRESENT
                proof = CapabilityProofClass.NO_EFFECT_PROBE
            elif any(
                item is not None and item.serviceable is False
                for item in bound_facts
            ):
                state = CapabilityObservationState.UNKNOWN
                proof = CapabilityProofClass.NO_EFFECT_PROBE
            else:
                state = CapabilityObservationState.UNKNOWN
                proof = CapabilityProofClass.EFFECTIVE_SCHEMA
        observations.append(
            CapabilityObservation(
                name=contract.capability, state=state, proof_class=proof
            )
        )

    tool_schema_digest = _digest(
        {
            "schema_complete": schema_complete,
            "tools": [item.to_dict() for item in effective],
        }
    )
    capability_contract_digest = _digest(
        {"contracts": [item.to_dict() for item in contracts]}
    )
    serviceability_evidence_digest = _digest(
        {
            "facts": [
                item.evidence_projection() for item in serviceability
            ]
        }
    )
    return WebCeoSessionCapabilityReceipt(
        worker_id=worker_id,
        quota_class=quota_class,
        session_ref=session_ref,
        binding_ref=binding_ref,
        binding_generation=binding_generation,
        action_scope_ref=action_scope_ref,
        observed_at_ms=observed_at_ms,
        expires_at_ms=expires_at_ms,
        schema_complete=schema_complete,
        tool_schema_digest=tool_schema_digest,
        capability_contract_digest=capability_contract_digest,
        observer_evidence_digest=observer_evidence_digest,
        serviceability_evidence_digest=serviceability_evidence_digest,
        observations=tuple(observations),
    )


@dataclasses.dataclass(frozen=True, slots=True)
class CurrentSessionBindingFacts:
    """Action-time current facts from the existing RuntimeBinding owner."""

    worker_id: str
    quota_class: str
    session_ref: str
    binding_ref: str
    binding_generation: int

    def __post_init__(self) -> None:
        _token(self.worker_id, code="CURRENT_WORKER_ID_INVALID")
        _token(self.quota_class, code="CURRENT_QUOTA_CLASS_INVALID")
        _token(self.session_ref, code="CURRENT_SESSION_REF_INVALID")
        _token(self.binding_ref, code="CURRENT_BINDING_REF_INVALID")
        _positive_int(
            self.binding_generation,
            code="CURRENT_BINDING_GENERATION_INVALID",
        )


@dataclasses.dataclass(frozen=True, slots=True)
class CurrentActionSurfaceFacts:
    """Current effective-action observation scope from the existing surface owner.

    This is a transient action-time fact, not another RuntimeBinding or
    capability registry. The owner must rotate ``action_scope_ref`` whenever
    the effective action set can change; on ChatGPT it must be no broader than
    the message-scoped app/action selection.
    """

    session_ref: str
    binding_ref: str
    binding_generation: int
    action_scope_ref: str

    def __post_init__(self) -> None:
        _token(self.session_ref, code="ACTION_SURFACE_SESSION_REF_INVALID")
        _token(self.binding_ref, code="ACTION_SURFACE_BINDING_REF_INVALID")
        _positive_int(
            self.binding_generation,
            code="ACTION_SURFACE_BINDING_GENERATION_INVALID",
        )
        _token(self.action_scope_ref, code="ACTION_SURFACE_REF_INVALID")


@dataclasses.dataclass(frozen=True, slots=True)
class WebCeoCapabilityPreflightDecision:
    """Machine-readable assessment; never effect authority by itself."""

    state: PreflightState
    receiver_binding_mode: ReceiverBindingMode
    worker_id: str
    quota_class: str
    session_ref: str
    binding_ref: str
    binding_generation: int
    action_scope_ref: str
    capability_contract_digest: str
    required_capabilities: tuple[str, ...]
    proven_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    unknown_capabilities: tuple[str, ...]
    evidence_digest: str
    rebind_allowed: bool
    exclusion: dict[str, str] | None
    selection_is_commitment: bool = False

    def __post_init__(self) -> None:
        _enum(self.state, PreflightState, code="PREFLIGHT_STATE_INVALID")
        _enum(
            self.receiver_binding_mode,
            ReceiverBindingMode,
            code="RECEIVER_BINDING_MODE_INVALID",
        )
        _token(self.worker_id, code="WORKER_ID_INVALID")
        _token(self.quota_class, code="QUOTA_CLASS_INVALID")
        _token(self.session_ref, code="SESSION_REF_INVALID")
        _token(self.binding_ref, code="BINDING_REF_INVALID")
        _positive_int(self.binding_generation, code="BINDING_GENERATION_INVALID")
        _token(self.action_scope_ref, code="ACTION_SCOPE_REF_INVALID")
        for digest_value, code in (
            (self.capability_contract_digest, "CAPABILITY_CONTRACT_DIGEST_INVALID"),
            (self.evidence_digest, "EVIDENCE_DIGEST_INVALID"),
        ):
            if (
                not isinstance(digest_value, str)
                or _DIGEST_RE.fullmatch(digest_value) is None
            ):
                raise WebCeoSessionCapabilityError(code)

        sets: list[set[str]] = []
        for field in (
            self.required_capabilities,
            self.proven_capabilities,
            self.missing_capabilities,
            self.unknown_capabilities,
        ):
            if not isinstance(field, tuple):
                raise WebCeoSessionCapabilityError("PREFLIGHT_CAPABILITY_SET_INVALID")
            if tuple(sorted(field)) != field or len(set(field)) != len(field):
                raise WebCeoSessionCapabilityError("PREFLIGHT_CAPABILITY_SET_INVALID")
            for item in field:
                _capability(item)
            sets.append(set(field))
        required, proven, missing, unknown = sets
        if not required:
            raise WebCeoSessionCapabilityError("PREFLIGHT_REQUIRED_EMPTY")
        if (proven & missing) or (proven & unknown) or (missing & unknown):
            raise WebCeoSessionCapabilityError("PREFLIGHT_PARTITION_INVALID")
        if proven | missing | unknown != required:
            raise WebCeoSessionCapabilityError("PREFLIGHT_PARTITION_INVALID")

        if type(self.rebind_allowed) is not bool:
            raise WebCeoSessionCapabilityError("REBIND_FLAG_INVALID")
        if self.selection_is_commitment is not False:
            raise WebCeoSessionCapabilityError("PREFLIGHT_CANNOT_BE_COMMITMENT")

        expected_exclusion = {
            "worker_id": self.worker_id,
            "quota_class": self.quota_class,
            "reason": "effective_capability_missing",
        }
        if self.state is PreflightState.READY:
            if proven != required or missing or unknown or self.rebind_allowed:
                raise WebCeoSessionCapabilityError("READY_PREFLIGHT_INVALID")
        elif self.state is PreflightState.PRESTART_REBIND_REQUIRED:
            if (
                self.receiver_binding_mode
                is not ReceiverBindingMode.CAPACITY_SELECTABLE
                or not missing
                or not self.rebind_allowed
                or self.exclusion != expected_exclusion
            ):
                raise WebCeoSessionCapabilityError("REBIND_STATE_INVALID")
        elif self.state is PreflightState.EXACT_SESSION_BLOCKED:
            if (
                self.receiver_binding_mode
                is not ReceiverBindingMode.EXACT_SESSION_REQUIRED
                or not missing
                or self.rebind_allowed
                or self.exclusion is not None
            ):
                raise WebCeoSessionCapabilityError("EXACT_SESSION_BLOCK_STATE_INVALID")
        elif self.state is PreflightState.CAPABILITY_PROOF_REQUIRED:
            if not unknown or missing or self.rebind_allowed:
                raise WebCeoSessionCapabilityError("CAPABILITY_PROOF_STATE_INVALID")
        elif self.state is PreflightState.STICKY_DEGRADED:
            if not missing or self.rebind_allowed:
                raise WebCeoSessionCapabilityError("STICKY_DEGRADED_STATE_INVALID")
        elif self.state is PreflightState.STARTED_STICKY:
            if missing or unknown or proven != required or self.rebind_allowed:
                raise WebCeoSessionCapabilityError("STARTED_STICKY_STATE_INVALID")
        elif self.rebind_allowed:
            raise WebCeoSessionCapabilityError("REBIND_STATE_INVALID")

        if self.state is not PreflightState.PRESTART_REBIND_REQUIRED:
            if self.exclusion is not None:
                raise WebCeoSessionCapabilityError("REBIND_EXCLUSION_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PREFLIGHT_SCHEMA,
            "state": self.state.value,
            "receiver_binding_mode": self.receiver_binding_mode.value,
            "worker_id": self.worker_id,
            "quota_class": self.quota_class,
            "session_ref": self.session_ref,
            "binding_ref": self.binding_ref,
            "binding_generation": self.binding_generation,
            "action_scope_ref": self.action_scope_ref,
            "capability_contract_digest": self.capability_contract_digest,
            "required_capabilities": list(self.required_capabilities),
            "proven_capabilities": list(self.proven_capabilities),
            "missing_capabilities": list(self.missing_capabilities),
            "unknown_capabilities": list(self.unknown_capabilities),
            "evidence_digest": self.evidence_digest,
            "rebind_allowed": self.rebind_allowed,
            "exclusion": dict(self.exclusion) if self.exclusion is not None else None,
            "selection_is_commitment": False,
        }


def validate_session_capability_receipt(
    value: object,
) -> WebCeoSessionCapabilityReceipt:
    """Rebuild one closed receipt and verify its canonical digest."""

    if not isinstance(value, Mapping):
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SHAPE_INVALID")
    raw = dict(value)
    if set(raw) != _RECEIPT_KEYS:
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SHAPE_INVALID")
    if raw.get("schema_version") != RECEIPT_SCHEMA:
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SCHEMA_INVALID")
    observations_raw = raw.get("observations")
    if not isinstance(observations_raw, list):
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SHAPE_INVALID")
    observations: list[CapabilityObservation] = []
    for item in observations_raw:
        if not isinstance(item, Mapping) or set(item) != _OBSERVATION_KEYS:
            raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_SHAPE_INVALID")
        try:
            state = CapabilityObservationState(item["state"])
            proof = CapabilityProofClass(item["proof_class"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WebCeoSessionCapabilityError(
                "CAPABILITY_RECEIPT_SHAPE_INVALID"
            ) from exc
        observations.append(
            CapabilityObservation(
                name=item["name"],
                state=state,
                proof_class=proof,
            )
        )
    receipt = WebCeoSessionCapabilityReceipt(
        worker_id=raw["worker_id"],
        quota_class=raw["quota_class"],
        session_ref=raw["session_ref"],
        binding_ref=raw["binding_ref"],
        binding_generation=raw["binding_generation"],
        action_scope_ref=raw["action_scope_ref"],
        observed_at_ms=raw["observed_at_ms"],
        expires_at_ms=raw["expires_at_ms"],
        schema_complete=raw["schema_complete"],
        tool_schema_digest=raw["tool_schema_digest"],
        capability_contract_digest=raw["capability_contract_digest"],
        observer_evidence_digest=raw["observer_evidence_digest"],
        serviceability_evidence_digest=raw["serviceability_evidence_digest"],
        observations=tuple(observations),
    )
    if raw["evidence_digest"] != receipt.evidence_digest:
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_DIGEST_MISMATCH")
    return receipt


def _decision(
    *,
    state: PreflightState,
    receiver_binding_mode: ReceiverBindingMode,
    receipt: WebCeoSessionCapabilityReceipt,
    required: tuple[str, ...],
    proven: tuple[str, ...],
    missing: tuple[str, ...],
    unknown: tuple[str, ...],
    rebind_allowed: bool = False,
) -> WebCeoCapabilityPreflightDecision:
    exclusion = (
        {
            "worker_id": receipt.worker_id,
            "quota_class": receipt.quota_class,
            "reason": "effective_capability_missing",
        }
        if rebind_allowed
        else None
    )
    return WebCeoCapabilityPreflightDecision(
        state=state,
        receiver_binding_mode=receiver_binding_mode,
        worker_id=receipt.worker_id,
        quota_class=receipt.quota_class,
        session_ref=receipt.session_ref,
        binding_ref=receipt.binding_ref,
        binding_generation=receipt.binding_generation,
        action_scope_ref=receipt.action_scope_ref,
        capability_contract_digest=receipt.capability_contract_digest,
        required_capabilities=required,
        proven_capabilities=proven,
        missing_capabilities=missing,
        unknown_capabilities=unknown,
        evidence_digest=receipt.evidence_digest,
        rebind_allowed=rebind_allowed,
        exclusion=exclusion,
    )


def assess_web_ceo_session_capabilities(
    *,
    receipt: WebCeoSessionCapabilityReceipt,
    required_capabilities: frozenset[str],
    receiver_binding_mode: ReceiverBindingMode,
    expected_worker_id: str,
    expected_quota_class: str,
    expected_session_ref: str,
    expected_binding_ref: str,
    expected_binding_generation: int,
    expected_action_scope_ref: str,
    expected_capability_contract_digest: str,
    expected_observer_evidence_digest: str,
    expected_serviceability_evidence_digest: str,
    now_ms: int,
    start_state: SessionStartState,
    effect_state: EffectState,
) -> WebCeoCapabilityPreflightDecision:
    """Re-assess one exact-session receipt against action-time owner facts."""

    if not isinstance(receipt, WebCeoSessionCapabilityReceipt):
        raise WebCeoSessionCapabilityError("CAPABILITY_RECEIPT_INVALID")
    if not isinstance(required_capabilities, frozenset) or not required_capabilities:
        raise WebCeoSessionCapabilityError("REQUIRED_CAPABILITIES_INVALID")
    required = tuple(sorted(_capability(item) for item in required_capabilities))
    _enum(
        receiver_binding_mode,
        ReceiverBindingMode,
        code="RECEIVER_BINDING_MODE_INVALID",
    )
    _token(expected_worker_id, code="EXPECTED_WORKER_ID_INVALID")
    _token(expected_quota_class, code="EXPECTED_QUOTA_CLASS_INVALID")
    _token(expected_session_ref, code="EXPECTED_SESSION_REF_INVALID")
    _token(expected_binding_ref, code="EXPECTED_BINDING_REF_INVALID")
    _positive_int(
        expected_binding_generation,
        code="EXPECTED_BINDING_GENERATION_INVALID",
    )
    _token(expected_action_scope_ref, code="EXPECTED_ACTION_SCOPE_REF_INVALID")
    if (
        not isinstance(expected_capability_contract_digest, str)
        or _DIGEST_RE.fullmatch(expected_capability_contract_digest) is None
    ):
        raise WebCeoSessionCapabilityError("EXPECTED_CAPABILITY_CONTRACT_DIGEST_INVALID")
    if (
        not isinstance(expected_observer_evidence_digest, str)
        or _DIGEST_RE.fullmatch(expected_observer_evidence_digest) is None
    ):
        raise WebCeoSessionCapabilityError("EXPECTED_OBSERVER_EVIDENCE_DIGEST_INVALID")
    if (
        not isinstance(expected_serviceability_evidence_digest, str)
        or _DIGEST_RE.fullmatch(expected_serviceability_evidence_digest) is None
    ):
        raise WebCeoSessionCapabilityError(
            "EXPECTED_SERVICEABILITY_EVIDENCE_DIGEST_INVALID"
        )
    current_ms = _positive_int(now_ms, code="CURRENT_TIME_INVALID")
    _enum(start_state, SessionStartState, code="SESSION_START_STATE_INVALID")
    if not isinstance(effect_state, EffectState):
        raise WebCeoSessionCapabilityError("EFFECT_STATE_INVALID")

    observed = {item.name: item for item in receipt.observations}
    proven: list[str] = []
    missing: list[str] = []
    unknown: list[str] = []
    for name in required:
        item = observed.get(name)
        if item is None:
            if receipt.schema_complete:
                raise WebCeoSessionCapabilityError(
                    "COMPLETE_SCHEMA_OBSERVATIONS_INCOMPLETE"
                )
            unknown.append(name)
        elif item.state is CapabilityObservationState.PRESENT:
            proven.append(name)
        elif item.state is CapabilityObservationState.ABSENT:
            missing.append(name)
        else:
            unknown.append(name)
    proven_tuple = tuple(proven)
    missing_tuple = tuple(missing)
    unknown_tuple = tuple(unknown)

    common = dict(
        receiver_binding_mode=receiver_binding_mode,
        receipt=receipt,
        required=required,
        proven=proven_tuple,
        missing=missing_tuple,
        unknown=unknown_tuple,
    )

    if (
        receipt.worker_id != expected_worker_id
        or receipt.quota_class != expected_quota_class
        or receipt.session_ref != expected_session_ref
        or receipt.binding_ref != expected_binding_ref
        or receipt.binding_generation != expected_binding_generation
        or receipt.action_scope_ref != expected_action_scope_ref
        or receipt.capability_contract_digest
        != expected_capability_contract_digest
        or receipt.observer_evidence_digest
        != expected_observer_evidence_digest
        or receipt.serviceability_evidence_digest
        != expected_serviceability_evidence_digest
    ):
        return _decision(state=PreflightState.RECONCILIATION_REQUIRED, **common)

    if effect_state is EffectState.EFFECT_UNKNOWN:
        return _decision(state=PreflightState.EFFECT_UNKNOWN, **common)

    if current_ms < receipt.observed_at_ms or current_ms > receipt.expires_at_ms:
        return _decision(state=PreflightState.STALE_EVIDENCE, **common)

    if (
        start_state is SessionStartState.PRE_START
        and effect_state is not EffectState.NONE
    ):
        return _decision(state=PreflightState.RECONCILIATION_REQUIRED, **common)

    if missing_tuple:
        if (
            start_state is SessionStartState.PRE_START
            and effect_state is EffectState.NONE
        ):
            if receiver_binding_mode is ReceiverBindingMode.EXACT_SESSION_REQUIRED:
                return _decision(
                    state=PreflightState.EXACT_SESSION_BLOCKED,
                    **common,
                )
            return _decision(
                state=PreflightState.PRESTART_REBIND_REQUIRED,
                rebind_allowed=True,
                **common,
            )
        return _decision(state=PreflightState.STICKY_DEGRADED, **common)

    if unknown_tuple:
        return _decision(state=PreflightState.CAPABILITY_PROOF_REQUIRED, **common)

    if start_state is SessionStartState.STARTED:
        return _decision(state=PreflightState.STARTED_STICKY, **common)

    return _decision(state=PreflightState.READY, **common)


def _placement_action_requirements(
    decision: c1.PlacementSelectionDecision,
    *,
    principal_action_demand: c1.PrincipalActionDemandReceipt,
    current_principal_action_facts: c1.PrincipalActionOwnerFacts,
) -> tuple[frozenset[str], ReceiverBindingMode]:
    """Consume source-attributed principal-local action demand at C2 time.

    General PlacementDemand capabilities may include downstream worker-local
    requirements. The C1 receipt carries the exact principal subset plus its
    Capacity and worker-route provenance. At the effect boundary we compare it
    to freshly supplied owner facts; no parallel caller-owned "expected"
    digest can self-certify a narrowed subset.
    """

    if not isinstance(principal_action_demand, c1.PrincipalActionDemandReceipt):
        raise WebCeoSessionCapabilityError("PRINCIPAL_ACTION_DEMAND_INVALID")
    if not isinstance(current_principal_action_facts, c1.PrincipalActionOwnerFacts):
        raise WebCeoSessionCapabilityError(
            "CURRENT_PRINCIPAL_ACTION_FACTS_INVALID"
        )

    demand = decision.demand
    if (
        principal_action_demand.selection_document_digest
        != c1.placement_selection_document_digest(decision)
        or principal_action_demand.principal_required_capabilities
        != current_principal_action_facts.principal_required_capabilities
        or principal_action_demand.action_partition_source
        != current_principal_action_facts.action_partition_source
        or principal_action_demand.action_partition_evidence_digest
        != current_principal_action_facts.action_partition_evidence_digest
        or principal_action_demand.worker_route_source
        != current_principal_action_facts.worker_route_source
        or principal_action_demand.worker_route_evidence_digest
        != current_principal_action_facts.worker_route_evidence_digest
    ):
        raise WebCeoSessionCapabilityError(
            "PRINCIPAL_ACTION_DEMAND_RECONCILIATION_REQUIRED"
        )

    principal = frozenset(principal_action_demand.principal_required_capabilities)
    if not principal.issubset(demand.required_capabilities):
        raise WebCeoSessionCapabilityError("PRINCIPAL_ACTION_DEMAND_INVALID")
    if any(
        capability not in _KNOWN_EFFECTIVE_CAPABILITY_SET
        for capability in principal
    ):
        raise WebCeoSessionCapabilityError(
            "PRINCIPAL_ACTION_DEMAND_OUTSIDE_CONTRACT"
        )

    binding_mode = (
        ReceiverBindingMode.EXACT_SESSION_REQUIRED
        if demand.allowed_modes
        == frozenset({c1.PlacementMode.EXISTING_SESSION_REUSE})
        else ReceiverBindingMode.CAPACITY_SELECTABLE
    )
    return principal, binding_mode


def build_guarded_commitment_plan_from_selection_decision(
    *,
    source_root_job_id: str,
    expected_source_root_revision: int,
    placement_selection: c1.PlacementSelectionDecision,
    validated_target_facts: Any,
    capability_receipt: WebCeoSessionCapabilityReceipt,
    current_binding: CurrentSessionBindingFacts,
    current_action_surface: CurrentActionSurfaceFacts,
    principal_action_demand: c1.PrincipalActionDemandReceipt,
    current_principal_action_facts: c1.PrincipalActionOwnerFacts,
    expected_capability_contract_digest: str,
    expected_observer_evidence_digest: str,
    expected_serviceability_evidence_digest: str,
    now_ms: int,
    start_state: SessionStartState,
    effect_state: EffectState,
) -> c2.PlacementCommitmentPlan:
    """Re-read capability/binding facts at effect boundary, then call C2."""

    if not isinstance(placement_selection, c1.PlacementSelectionDecision):
        raise WebCeoSessionCapabilityError("PLACEMENT_SELECTION_INVALID")
    if not isinstance(current_binding, CurrentSessionBindingFacts):
        raise WebCeoSessionCapabilityError("CURRENT_BINDING_INVALID")
    if not isinstance(current_action_surface, CurrentActionSurfaceFacts):
        raise WebCeoSessionCapabilityError("CURRENT_ACTION_SURFACE_INVALID")
    if (
        current_action_surface.session_ref != current_binding.session_ref
        or current_action_surface.binding_ref != current_binding.binding_ref
        or current_action_surface.binding_generation
        != current_binding.binding_generation
    ):
        raise WebCeoSessionCapabilityError("ACTION_SURFACE_BINDING_MISMATCH")
    required_capabilities, receiver_binding_mode = _placement_action_requirements(
        placement_selection,
        principal_action_demand=principal_action_demand,
        current_principal_action_facts=current_principal_action_facts,
    )
    wire = placement_selection.to_dict()
    selected = wire.get("selected")
    if not isinstance(selected, Mapping):
        raise WebCeoSessionCapabilityError("PLACEMENT_SELECTION_INVALID")
    if (
        selected.get("worker_id") != current_binding.worker_id
        or selected.get("quota_class") != current_binding.quota_class
    ):
        raise WebCeoSessionCapabilityError(
            "CAPABILITY_PREFLIGHT_SELECTION_MISMATCH"
        )

    preflight = assess_web_ceo_session_capabilities(
        receipt=capability_receipt,
        required_capabilities=required_capabilities,
        receiver_binding_mode=receiver_binding_mode,
        expected_worker_id=current_binding.worker_id,
        expected_quota_class=current_binding.quota_class,
        expected_session_ref=current_binding.session_ref,
        expected_binding_ref=current_binding.binding_ref,
        expected_binding_generation=current_binding.binding_generation,
        expected_action_scope_ref=current_action_surface.action_scope_ref,
        expected_capability_contract_digest=expected_capability_contract_digest,
        expected_observer_evidence_digest=expected_observer_evidence_digest,
        expected_serviceability_evidence_digest=(
            expected_serviceability_evidence_digest
        ),
        now_ms=now_ms,
        start_state=start_state,
        effect_state=effect_state,
    )
    if preflight.state is not PreflightState.READY:
        raise WebCeoSessionCapabilityError("CAPABILITY_PREFLIGHT_NOT_READY")

    return c2.build_commitment_plan_from_selection_decision(
        source_root_job_id=source_root_job_id,
        expected_source_root_revision=expected_source_root_revision,
        placement_selection=placement_selection,
        validated_target_facts=validated_target_facts,
    )


__all__ = [
    "ActionServiceabilityFact",
    "CapabilityActionContract",
    "CapabilityObservation",
    "CapabilityObservationState",
    "CapabilityProofClass",
    "CurrentActionSurfaceFacts",
    "CurrentSessionBindingFacts",
    "EffectiveToolDescriptor",
    "KNOWN_EFFECTIVE_CAPABILITIES",
    "MAX_RECEIPT_TTL_MS",
    "PREFLIGHT_SCHEMA",
    "PreflightState",
    "RECEIPT_SCHEMA",
    "ReceiverBindingMode",
    "SessionStartState",
    "WebCeoCapabilityPreflightDecision",
    "WebCeoSessionCapabilityError",
    "WebCeoSessionCapabilityReceipt",
    "assess_web_ceo_session_capabilities",
    "build_guarded_commitment_plan_from_selection_decision",
    "build_receipt_from_effective_tool_schema",
    "validate_session_capability_receipt",
]
