"""Pure, secret-free Sol capability-status projection.

This module implements the records-only SCF-CAP1 contract.  It projects
immutable capability/app/dependency facts into
``mastermind.sol_capability_status.v1``.  It owns no capability registry,
credential, app, plugin, MCP server, lifecycle, queue, scheduler, RuntimeBinding,
provider selection, network client, filesystem discovery, persistence, or
production arming.

Canonical owners remain unchanged:

* ``ExecutionCapabilityRegistry`` owns reviewed execution-surface policy;
* Executive OS owns Job/Attempt/Worker/Event and CEO admission;
* RuntimeBinding/SessionTargetRegistry own exact current surfaces;
* each app/connector owner supplies current availability, scope and proof facts.

The projector is intentionally a total deterministic function over caller-
supplied frozen dataclasses.  Missing or contradictory facts fail closed.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Iterable


SCHEMA = "mastermind.sol_capability_status.v1"

_IDENTIFIER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/*-]{0,127}$")
_SOURCE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@-]{0,255}$")
_ISSUE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_SECRET_PATTERNS = (
    re.compile(r"github_pat_", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]", re.IGNORECASE),
    re.compile(r"\bxox[baprs]-", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9]", re.IGNORECASE),
    re.compile(r"authorization\s*=", re.IGNORECASE),
    re.compile(r"bearer\s+", re.IGNORECASE),
    re.compile(r"password\s*=", re.IGNORECASE),
    re.compile(r"-----BEGIN", re.IGNORECASE),
)


class CapabilityProjectionError(ValueError):
    """The frozen input facts are malformed, conflicting, or unsafe."""


class CapabilityState(str, Enum):
    PROVEN_LIVE = "PROVEN_LIVE"
    BUILT_NOT_PROVEN = "BUILT_NOT_PROVEN"
    PARTIAL = "PARTIAL"
    DARK_OR_DISCONNECTED = "DARK_OR_DISCONNECTED"
    BROKEN = "BROKEN"
    SPEC_ONLY = "SPEC_ONLY"
    NOT_BUILT = "NOT_BUILT"
    REJECTED_BY_DESIGN = "REJECTED_BY_DESIGN"


class PrivilegeClass(str, Enum):
    R0_OBSERVE = "R0_OBSERVE"
    W1_ROUTINE = "W1_ROUTINE"
    W2_CONSEQUENTIAL = "W2_CONSEQUENTIAL"
    A3_ADMIN = "A3_ADMIN"


class Availability(str, Enum):
    AVAILABLE = "AVAILABLE"
    READ_ONLY = "READ_ONLY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"
    REFUSED = "REFUSED"


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


def _reject_secret_shape(value: str, *, field: str) -> None:
    if any(pattern.search(value) for pattern in _SECRET_PATTERNS):
        raise CapabilityProjectionError(f"{field} contains secret-shaped text")


def _identifier(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise CapabilityProjectionError(f"{field} must be a string")
    token = value.strip().lower()
    _reject_secret_shape(token, field=field)
    if _IDENTIFIER_RE.fullmatch(token) is None:
        raise CapabilityProjectionError(
            f"{field} must be a bounded lowercase identifier"
        )
    return token


def _digest_value(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise CapabilityProjectionError(f"{field} must be a SHA-256 string")
    token = value.strip().lower()
    _reject_secret_shape(token, field=field)
    if _DIGEST_RE.fullmatch(token) is None:
        raise CapabilityProjectionError(f"{field} must be a lowercase SHA-256")
    return token


def _timestamp(value: object, *, field: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CapabilityProjectionError(f"{field} must be an RFC3339 timestamp")
    token = value.strip()
    _reject_secret_shape(token, field=field)
    try:
        parsed = datetime.fromisoformat(token.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CapabilityProjectionError(
            f"{field} must be an RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise CapabilityProjectionError(f"{field} must include a timezone")
    return token


def _scopes(values: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise CapabilityProjectionError(f"{field} must be an immutable tuple")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise CapabilityProjectionError(f"{field} entries must be strings")
        token = value.strip()
        _reject_secret_shape(token, field=field)
        if _SCOPE_RE.fullmatch(token) is None:
            raise CapabilityProjectionError(f"{field} contains an invalid scope")
        if token in normalized:
            raise CapabilityProjectionError(f"{field} contains duplicate scope {token!r}")
        normalized.append(token)
    return tuple(sorted(normalized))


def _source_refs(values: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise CapabilityProjectionError(f"{field} must be a non-empty immutable tuple")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise CapabilityProjectionError(f"{field} entries must be strings")
        token = value.strip()
        _reject_secret_shape(token, field=field)
        if _SOURCE_REF_RE.fullmatch(token) is None:
            raise CapabilityProjectionError(f"{field} contains an invalid source reference")
        if token in normalized:
            raise CapabilityProjectionError(
                f"{field} contains duplicate source reference {token!r}"
            )
        normalized.append(token)
    return tuple(sorted(normalized))


def _issues(values: object, *, field: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise CapabilityProjectionError(f"{field} must be an immutable tuple")
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise CapabilityProjectionError(f"{field} entries must be strings")
        token = value.strip().upper()
        _reject_secret_shape(value, field=field)
        if _ISSUE_RE.fullmatch(token) is None:
            raise CapabilityProjectionError(f"{field} contains an invalid issue code")
        if token not in normalized:
            normalized.append(token)
    return tuple(sorted(normalized))


def _is_write_scope(scope: str) -> bool:
    lowered = scope.lower()
    return (
        lowered.endswith(":write")
        or lowered.endswith(":admin")
        or lowered.endswith(":manage")
        or ":write:" in lowered
        or ":admin:" in lowered
        or ":manage:" in lowered
    )


@dataclasses.dataclass(frozen=True)
class DependencyFact:
    """One current dependency observation supplied by its canonical owner."""

    name: str
    state: CapabilityState
    required: bool
    available: bool | None
    source_ref: str
    issues: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class CapabilityFact:
    """One immutable, secret-free capability/app observation.

    This is input evidence, not a registration request.  Constructing a fact
    grants no capability and performs no discovery.
    """

    name: str
    app_id: str
    app_generation: str
    privilege_class: PrivilegeClass
    production_armed: bool
    required_scopes: tuple[str, ...]
    current_scopes: tuple[str, ...]
    confirmation_required: bool
    prepared_action_required: bool
    canonical_owner: str
    dependencies: tuple[DependencyFact, ...]
    schema_digest: str
    source_state: CapabilityState
    observed_available: bool | None
    live_proof_current: bool
    write_capable: bool
    last_proven_at: str | None
    source_refs: tuple[str, ...]
    issues: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class DependencyStatus:
    name: str
    state: CapabilityState
    required: bool
    available: bool | None
    source_ref: str
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "state": self.state.value,
            "required": self.required,
            "available": self.available,
            "source_ref": self.source_ref,
            "issues": list(self.issues),
        }


@dataclasses.dataclass(frozen=True)
class CapabilityStatus:
    name: str
    app_id: str
    app_generation: str
    privilege_class: PrivilegeClass
    availability: Availability
    production_armed: bool
    required_scopes: tuple[str, ...]
    current_scopes: tuple[str, ...]
    missing_scopes: tuple[str, ...]
    confirmation_required: bool
    prepared_action_required: bool
    canonical_owner: str
    dependencies: tuple[DependencyStatus, ...]
    schema_digest: str
    proof_state: CapabilityState
    last_proven_at: str | None
    read_serviceable: bool
    write_serviceable: bool
    source_refs: tuple[str, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "app_id": self.app_id,
            "app_generation": self.app_generation,
            "privilege_class": self.privilege_class.value,
            "availability": self.availability.value,
            "production_armed": self.production_armed,
            "required_scopes": list(self.required_scopes),
            "current_scopes": list(self.current_scopes),
            "missing_scopes": list(self.missing_scopes),
            "confirmation_required": self.confirmation_required,
            "prepared_action_required": self.prepared_action_required,
            "canonical_owner": self.canonical_owner,
            "dependencies": [row.to_dict() for row in self.dependencies],
            "schema_digest": self.schema_digest,
            "proof_state": self.proof_state.value,
            "last_proven_at": self.last_proven_at,
            "read_serviceable": self.read_serviceable,
            "write_serviceable": self.write_serviceable,
            "source_refs": list(self.source_refs),
            "issues": list(self.issues),
        }


@dataclasses.dataclass(frozen=True)
class CapabilityStatusEnvelope:
    schema: str
    capability_generation: str
    observed_at: str
    capabilities: tuple[CapabilityStatus, ...]
    issues: tuple[str, ...]
    canonical_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "capability_generation": self.capability_generation,
            "observed_at": self.observed_at,
            "capabilities": [row.to_dict() for row in self.capabilities],
            "issues": list(self.issues),
            "canonical_digest": self.canonical_digest,
        }


def _normalize_dependency(
    value: DependencyFact,
    *,
    capability_name: str,
) -> DependencyStatus:
    if not isinstance(value, DependencyFact):
        raise CapabilityProjectionError(
            f"capability {capability_name!r} dependencies must contain DependencyFact"
        )
    name = _identifier(value.name, field=f"{capability_name}.dependency.name")
    if not isinstance(value.state, CapabilityState):
        raise CapabilityProjectionError(
            f"{capability_name}.dependency.{name}.state is unsupported"
        )
    if type(value.required) is not bool:
        raise CapabilityProjectionError(
            f"{capability_name}.dependency.{name}.required must be boolean"
        )
    if value.available is not None and type(value.available) is not bool:
        raise CapabilityProjectionError(
            f"{capability_name}.dependency.{name}.available must be boolean or null"
        )
    source_ref = _source_refs(
        (value.source_ref,), field=f"{capability_name}.dependency.{name}.source_ref"
    )[0]
    issues = _issues(
        value.issues, field=f"{capability_name}.dependency.{name}.issues"
    )
    return DependencyStatus(
        name=name,
        state=value.state,
        required=value.required,
        available=value.available,
        source_ref=source_ref,
        issues=issues,
    )


def _normalize_fact(value: CapabilityFact) -> CapabilityFact:
    if not isinstance(value, CapabilityFact):
        raise CapabilityProjectionError("capabilities must contain CapabilityFact")
    name = _identifier(value.name, field="capability.name")
    app_id = _identifier(value.app_id, field=f"{name}.app_id")
    app_generation = _identifier(
        value.app_generation, field=f"{name}.app_generation"
    )
    owner = _identifier(value.canonical_owner, field=f"{name}.canonical_owner")
    if not isinstance(value.privilege_class, PrivilegeClass):
        raise CapabilityProjectionError(f"{name}.privilege_class is unsupported")
    if not isinstance(value.source_state, CapabilityState):
        raise CapabilityProjectionError(f"{name}.source_state is unsupported")
    for field_name in (
        "production_armed",
        "confirmation_required",
        "prepared_action_required",
        "live_proof_current",
        "write_capable",
    ):
        if type(getattr(value, field_name)) is not bool:
            raise CapabilityProjectionError(f"{name}.{field_name} must be boolean")
    if value.observed_available is not None and type(value.observed_available) is not bool:
        raise CapabilityProjectionError(
            f"{name}.observed_available must be boolean or null"
        )
    required_scopes = _scopes(value.required_scopes, field=f"{name}.required_scopes")
    current_scopes = _scopes(value.current_scopes, field=f"{name}.current_scopes")
    schema_digest = _digest_value(value.schema_digest, field=f"{name}.schema_digest")
    last_proven_at = _timestamp(
        value.last_proven_at, field=f"{name}.last_proven_at", optional=True
    )
    source_refs = _source_refs(value.source_refs, field=f"{name}.source_refs")
    issues = _issues(value.issues, field=f"{name}.issues")
    if not isinstance(value.dependencies, tuple):
        raise CapabilityProjectionError(f"{name}.dependencies must be an immutable tuple")
    normalized_dependencies: list[DependencyFact] = []
    seen_dependencies: set[str] = set()
    for dependency in value.dependencies:
        status = _normalize_dependency(dependency, capability_name=name)
        if status.name in seen_dependencies:
            raise CapabilityProjectionError(
                f"capability {name!r} contains duplicate dependency {status.name!r}"
            )
        seen_dependencies.add(status.name)
        normalized_dependencies.append(
            DependencyFact(
                name=status.name,
                state=status.state,
                required=status.required,
                available=status.available,
                source_ref=status.source_ref,
                issues=status.issues,
            )
        )
    normalized_dependencies.sort(key=lambda row: row.name)
    return CapabilityFact(
        name=name,
        app_id=app_id,
        app_generation=app_generation,
        privilege_class=value.privilege_class,
        production_armed=value.production_armed,
        required_scopes=required_scopes,
        current_scopes=current_scopes,
        confirmation_required=value.confirmation_required,
        prepared_action_required=value.prepared_action_required,
        canonical_owner=owner,
        dependencies=tuple(normalized_dependencies),
        schema_digest=schema_digest,
        source_state=value.source_state,
        observed_available=value.observed_available,
        live_proof_current=value.live_proof_current,
        write_capable=value.write_capable,
        last_proven_at=last_proven_at,
        source_refs=source_refs,
        issues=issues,
    )


def _project_fact(fact: CapabilityFact) -> CapabilityStatus:
    dependencies = tuple(
        _normalize_dependency(row, capability_name=fact.name)
        for row in fact.dependencies
    )
    issues = set(fact.issues)
    missing_scopes = tuple(
        sorted(set(fact.required_scopes) - set(fact.current_scopes))
    )
    missing_read_scopes = tuple(
        scope for scope in missing_scopes if not _is_write_scope(scope)
    )
    missing_write_scopes = tuple(
        scope for scope in missing_scopes if _is_write_scope(scope)
    )
    if missing_scopes:
        issues.add("REQUIRED_SCOPE_MISSING")

    dependency_broken = False
    dependency_disconnected = False
    dependency_partial = False
    dependency_unknown = False
    for dependency in dependencies:
        if not dependency.required:
            continue
        if dependency.available is None:
            dependency_unknown = True
            issues.add("DEPENDENCY_AVAILABILITY_UNKNOWN")
        elif dependency.available is False:
            dependency_disconnected = True
            issues.add("DEPENDENCY_UNAVAILABLE")
        if dependency.state is CapabilityState.BROKEN:
            dependency_broken = True
            issues.add("DEPENDENCY_BROKEN")
        elif dependency.state is CapabilityState.REJECTED_BY_DESIGN:
            dependency_broken = True
            issues.add("DEPENDENCY_REJECTED_BY_DESIGN")
        elif dependency.state is CapabilityState.NOT_BUILT:
            dependency_disconnected = True
            issues.add("DEPENDENCY_NOT_BUILT")
        elif dependency.state is CapabilityState.DARK_OR_DISCONNECTED:
            dependency_disconnected = True
            issues.add("DEPENDENCY_DARK_OR_DISCONNECTED")
        elif dependency.state in {
            CapabilityState.PARTIAL,
            CapabilityState.BUILT_NOT_PROVEN,
            CapabilityState.SPEC_ONLY,
        }:
            dependency_partial = True
            issues.add(f"DEPENDENCY_{dependency.state.value}")

    proof_state = fact.source_state
    availability = Availability.UNAVAILABLE
    read_serviceable = False
    write_serviceable = False

    if fact.source_state is CapabilityState.REJECTED_BY_DESIGN:
        availability = Availability.REFUSED
        issues.add("CAPABILITY_REJECTED_BY_DESIGN")
    elif fact.source_state is CapabilityState.NOT_BUILT:
        availability = Availability.UNAVAILABLE
        issues.add("CAPABILITY_NOT_BUILT")
    elif fact.source_state is CapabilityState.SPEC_ONLY:
        availability = Availability.UNAVAILABLE
        issues.add("CAPABILITY_SPEC_ONLY")
    elif fact.source_state is CapabilityState.BROKEN:
        availability = Availability.UNAVAILABLE
        issues.add("CAPABILITY_BROKEN")
    elif dependency_broken:
        proof_state = CapabilityState.BROKEN
        availability = Availability.UNAVAILABLE
    elif fact.observed_available is None or dependency_unknown:
        availability = Availability.UNKNOWN
        issues.add("AVAILABILITY_UNKNOWN")
        if proof_state is CapabilityState.PROVEN_LIVE:
            proof_state = CapabilityState.BUILT_NOT_PROVEN
    elif fact.observed_available is False or dependency_disconnected:
        availability = Availability.UNAVAILABLE
        proof_state = CapabilityState.DARK_OR_DISCONNECTED
        issues.add("CAPABILITY_UNAVAILABLE")
    elif missing_read_scopes:
        availability = Availability.UNAVAILABLE
        proof_state = CapabilityState.DARK_OR_DISCONNECTED
        issues.add("READ_SCOPE_MISSING")
    else:
        read_serviceable = True
        if dependency_partial or fact.source_state is CapabilityState.PARTIAL:
            proof_state = CapabilityState.PARTIAL
            availability = Availability.DEGRADED
        elif fact.source_state is CapabilityState.DARK_OR_DISCONNECTED:
            proof_state = CapabilityState.DARK_OR_DISCONNECTED
            availability = Availability.UNAVAILABLE
            read_serviceable = False
        else:
            availability = Availability.AVAILABLE

        live_proof_usable = fact.live_proof_current and fact.last_proven_at is not None
        if not live_proof_usable:
            issues.add("LIVE_PROOF_MISSING")
            if proof_state is CapabilityState.PROVEN_LIVE:
                proof_state = CapabilityState.BUILT_NOT_PROVEN

        if missing_write_scopes:
            proof_state = CapabilityState.PARTIAL

        write_serviceable = bool(
            fact.write_capable
            and read_serviceable
            and not missing_scopes
            and not dependency_partial
            and fact.production_armed
            and live_proof_usable
            and proof_state
            not in {
                CapabilityState.PARTIAL,
                CapabilityState.DARK_OR_DISCONNECTED,
                CapabilityState.BROKEN,
                CapabilityState.SPEC_ONLY,
                CapabilityState.NOT_BUILT,
                CapabilityState.REJECTED_BY_DESIGN,
            }
        )

        if fact.write_capable and not fact.production_armed:
            issues.add("PRODUCTION_DISARMED")
            if proof_state is CapabilityState.PROVEN_LIVE:
                proof_state = CapabilityState.BUILT_NOT_PROVEN

        if fact.write_capable and not write_serviceable and read_serviceable:
            if availability is Availability.AVAILABLE:
                availability = Availability.READ_ONLY

        can_promote_live = bool(
            live_proof_usable
            and read_serviceable
            and not dependency_partial
            and not missing_scopes
            and (
                not fact.write_capable
                or (fact.production_armed and write_serviceable)
            )
        )
        if (
            fact.source_state is CapabilityState.BUILT_NOT_PROVEN
            and can_promote_live
        ):
            proof_state = CapabilityState.PROVEN_LIVE

        if missing_write_scopes and read_serviceable:
            availability = Availability.READ_ONLY

    return CapabilityStatus(
        name=fact.name,
        app_id=fact.app_id,
        app_generation=fact.app_generation,
        privilege_class=fact.privilege_class,
        availability=availability,
        production_armed=fact.production_armed,
        required_scopes=fact.required_scopes,
        current_scopes=fact.current_scopes,
        missing_scopes=missing_scopes,
        confirmation_required=fact.confirmation_required,
        prepared_action_required=fact.prepared_action_required,
        canonical_owner=fact.canonical_owner,
        dependencies=dependencies,
        schema_digest=fact.schema_digest,
        proof_state=proof_state,
        last_proven_at=fact.last_proven_at,
        read_serviceable=read_serviceable,
        write_serviceable=write_serviceable,
        source_refs=fact.source_refs,
        issues=tuple(sorted(issues)),
    )


def project_sol_capability_status(
    facts: Iterable[CapabilityFact],
    *,
    observed_at: str,
    capability_generation: str,
) -> CapabilityStatusEnvelope:
    """Project immutable facts into one deterministic capability envelope.

    The caller owns acquisition and freshness adjudication.  This function
    performs no I/O and grants no authority.
    """

    observed = _timestamp(observed_at, field="observed_at")
    assert observed is not None
    generation = _identifier(
        capability_generation, field="capability_generation"
    )
    if isinstance(facts, (str, bytes)):
        raise CapabilityProjectionError("facts must be an iterable of CapabilityFact")
    normalized: list[CapabilityFact] = []
    seen_names: set[str] = set()
    try:
        iterator = iter(facts)
    except TypeError as exc:
        raise CapabilityProjectionError(
            "facts must be an iterable of CapabilityFact"
        ) from exc
    for raw in iterator:
        fact = _normalize_fact(raw)
        if fact.name in seen_names:
            raise CapabilityProjectionError(
                f"duplicate capability name {fact.name!r}"
            )
        seen_names.add(fact.name)
        normalized.append(fact)
    normalized.sort(key=lambda row: row.name)

    statuses = tuple(_project_fact(fact) for fact in normalized)
    envelope_issues: set[str] = set()
    if not statuses:
        envelope_issues.add("NO_CAPABILITIES_OBSERVED")

    payload = {
        "schema": SCHEMA,
        "capability_generation": generation,
        "observed_at": observed,
        "capabilities": [row.to_dict() for row in statuses],
        "issues": sorted(envelope_issues),
    }
    digest = _digest(payload)
    return CapabilityStatusEnvelope(
        schema=SCHEMA,
        capability_generation=generation,
        observed_at=observed,
        capabilities=statuses,
        issues=tuple(sorted(envelope_issues)),
        canonical_digest=digest,
    )


__all__ = [
    "Availability",
    "CapabilityFact",
    "CapabilityProjectionError",
    "CapabilityState",
    "CapabilityStatus",
    "CapabilityStatusEnvelope",
    "DependencyFact",
    "DependencyStatus",
    "PrivilegeClass",
    "SCHEMA",
    "project_sol_capability_status",
]
