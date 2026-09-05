"""Pure, secret-free projection for ``mastermind.sol_capability_status.v1``.

The caller supplies immutable owner facts. This module performs no I/O, owns no
registry/lifecycle/credential, grants no authority, and persists nothing.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

SCHEMA = "mastermind.sol_capability_status.v1"
MAX_CAPABILITIES = 128
MAX_SCOPES = 128
MAX_DEPENDENCIES = 64
MAX_SOURCE_REFS = 32
MAX_ISSUES = 64
MAX_TIMESTAMP_LENGTH = 32

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_SCOPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/*-]{0,127}$")
_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@-]{0,255}$")
_ISSUE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RFC3339 = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)
_SECRET = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"github_pat_",
        r"\bgh[pousr]_[A-Za-z0-9]",
        r"\bxox[baprs]-",
        r"\bsk-[A-Za-z0-9]",
        r"authorization\s*=",
        r"bearer\s+",
        r"password\s*=",
        r"-----BEGIN",
    )
)


class CapabilityProjectionError(ValueError):
    """Input facts are malformed, conflicting, future-invalid, or unsafe."""


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


def _secret(value: str, field: str) -> None:
    if any(pattern.search(value) for pattern in _SECRET):
        raise CapabilityProjectionError(f"{field} contains secret-shaped text")


def _token(
    value: object,
    field: str,
    pattern: re.Pattern[str],
    message: str,
    *,
    lower: bool = False,
    upper: bool = False,
) -> str:
    if not isinstance(value, str):
        raise CapabilityProjectionError(f"{field} must be a string")
    raw = value.strip()
    _secret(raw, field)
    result = raw.lower() if lower else raw.upper() if upper else raw
    if pattern.fullmatch(result) is None:
        raise CapabilityProjectionError(f"{field} {message}")
    return result


def _identifier(value: object, field: str) -> str:
    return _token(
        value,
        field,
        _ID,
        "must be a bounded lowercase identifier",
        lower=True,
    )


def _digest_value(value: object, field: str) -> str:
    return _token(
        value,
        field,
        _DIGEST,
        "must be a lowercase SHA-256",
        lower=True,
    )


def _timestamp(value: object, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    error = CapabilityProjectionError(f"{field} must be an RFC3339 timestamp")
    if (
        type(value) is not str
        or not value
        or len(value) > MAX_TIMESTAMP_LENGTH
        or value != value.strip()
        or _RFC3339.fullmatch(value) is None
    ):
        raise error
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        parsed = None
    if parsed is None or parsed.tzinfo is None:
        raise error
    canonical = parsed.astimezone(timezone.utc)
    timespec = "microseconds" if canonical.microsecond else "seconds"
    return canonical.isoformat(timespec=timespec).replace("+00:00", "Z")


def _instant(value: str, field: str) -> datetime:
    canonical = _timestamp(value, field)
    assert canonical is not None
    return datetime.fromisoformat(canonical.replace("Z", "+00:00"))


def _tuple_tokens(
    values: object,
    field: str,
    pattern: re.Pattern[str],
    message: str,
    *,
    maximum: int,
    upper: bool = False,
    nonempty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, tuple) or (nonempty and not values):
        suffix = "non-empty immutable tuple" if nonempty else "immutable tuple"
        raise CapabilityProjectionError(f"{field} must be a {suffix}")
    if len(values) > maximum:
        raise CapabilityProjectionError(
            f"{field} must contain at most {maximum} items"
        )
    out: list[str] = []
    for value in values:
        item = _token(value, field, pattern, message, upper=upper)
        if item in out:
            raise CapabilityProjectionError(
                f"{field} contains duplicate value {item!r}"
            )
        out.append(item)
    return tuple(sorted(out))


def _scopes(values: object, field: str) -> tuple[str, ...]:
    return _tuple_tokens(
        values,
        field,
        _SCOPE,
        "contains an invalid scope",
        maximum=MAX_SCOPES,
    )


def _sources(values: object, field: str) -> tuple[str, ...]:
    return _tuple_tokens(
        values,
        field,
        _SOURCE,
        "contains an invalid source reference",
        maximum=MAX_SOURCE_REFS,
        nonempty=True,
    )


def _issues(values: object, field: str) -> tuple[str, ...]:
    return _tuple_tokens(
        values,
        field,
        _ISSUE,
        "contains an invalid issue code",
        maximum=MAX_ISSUES,
        upper=True,
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclasses.dataclass(frozen=True)
class DependencyFact:
    name: str
    state: CapabilityState
    required: bool
    available: bool | None
    source_ref: str
    issues: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class CapabilityFact:
    name: str
    app_id: str
    app_generation: str
    privilege_class: PrivilegeClass
    production_armed: bool
    required_scopes: tuple[str, ...]
    required_write_scopes: tuple[str, ...]
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
        return dataclasses.asdict(self) | {
            "state": self.state.value,
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
    required_read_scopes: tuple[str, ...]
    required_write_scopes: tuple[str, ...]
    current_scopes: tuple[str, ...]
    missing_scopes: tuple[str, ...]
    excess_scopes: tuple[str, ...]
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
        value = dataclasses.asdict(self)
        value.update(
            privilege_class=self.privilege_class.value,
            availability=self.availability.value,
            proof_state=self.proof_state.value,
            required_scopes=list(self.required_scopes),
            required_read_scopes=list(self.required_read_scopes),
            required_write_scopes=list(self.required_write_scopes),
            current_scopes=list(self.current_scopes),
            missing_scopes=list(self.missing_scopes),
            excess_scopes=list(self.excess_scopes),
            dependencies=[dependency.to_dict() for dependency in self.dependencies],
            source_refs=list(self.source_refs),
            issues=list(self.issues),
        )
        return value


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
            "capabilities": [capability.to_dict() for capability in self.capabilities],
            "issues": list(self.issues),
            "canonical_digest": self.canonical_digest,
        }


def _dependency(value: DependencyFact, capability: str) -> DependencyStatus:
    if not isinstance(value, DependencyFact):
        raise CapabilityProjectionError(
            f"capability {capability!r} dependencies must contain DependencyFact"
        )
    name = _identifier(value.name, f"{capability}.dependency.name")
    if not isinstance(value.state, CapabilityState):
        raise CapabilityProjectionError(
            f"{capability}.dependency.{name}.state is unsupported"
        )
    if type(value.required) is not bool:
        raise CapabilityProjectionError(
            f"{capability}.dependency.{name}.required must be boolean"
        )
    if value.available is not None and type(value.available) is not bool:
        raise CapabilityProjectionError(
            f"{capability}.dependency.{name}.available must be boolean or null"
        )
    source = _sources(
        (value.source_ref,),
        f"{capability}.dependency.{name}.source_ref",
    )[0]
    return DependencyStatus(
        name,
        value.state,
        value.required,
        value.available,
        source,
        _issues(value.issues, f"{capability}.dependency.{name}.issues"),
    )


def _fact(value: CapabilityFact) -> CapabilityFact:
    if not isinstance(value, CapabilityFact):
        raise CapabilityProjectionError("capabilities must contain CapabilityFact")
    name = _identifier(value.name, "capability.name")
    boolean_fields = (
        "production_armed",
        "confirmation_required",
        "prepared_action_required",
        "live_proof_current",
        "write_capable",
    )
    for field in boolean_fields:
        if type(getattr(value, field)) is not bool:
            raise CapabilityProjectionError(f"{name}.{field} must be boolean")
    if value.observed_available is not None and type(value.observed_available) is not bool:
        raise CapabilityProjectionError(
            f"{name}.observed_available must be boolean or null"
        )
    if not isinstance(value.privilege_class, PrivilegeClass):
        raise CapabilityProjectionError(f"{name}.privilege_class is unsupported")
    if not isinstance(value.source_state, CapabilityState):
        raise CapabilityProjectionError(f"{name}.source_state is unsupported")

    required = _scopes(value.required_scopes, f"{name}.required_scopes")
    writes = _scopes(value.required_write_scopes, f"{name}.required_write_scopes")
    if set(writes) - set(required):
        raise CapabilityProjectionError(
            f"{name}.required_write_scopes must be a subset of required_scopes"
        )
    if writes and not value.write_capable:
        raise CapabilityProjectionError(
            f"{name}.required_write_scopes require write_capable=true"
        )

    if value.privilege_class is PrivilegeClass.R0_OBSERVE and any(
        (
            value.production_armed,
            value.confirmation_required,
            value.prepared_action_required,
            value.write_capable,
            bool(writes),
        )
    ):
        raise CapabilityProjectionError(f"{name}.R0_OBSERVE must be zero-effect")

    if value.production_armed and not value.write_capable:
        raise CapabilityProjectionError(
            f"{name}.production_armed requires write_capable=true"
        )
    if value.production_armed and value.source_state in {
        CapabilityState.NOT_BUILT,
        CapabilityState.SPEC_ONLY,
        CapabilityState.REJECTED_BY_DESIGN,
    }:
        raise CapabilityProjectionError(
            f"{name}.{value.source_state.value} cannot be production_armed"
        )

    if (
        value.write_capable
        and value.privilege_class
        in {PrivilegeClass.W2_CONSEQUENTIAL, PrivilegeClass.A3_ADMIN}
        and not value.prepared_action_required
    ):
        raise CapabilityProjectionError(
            f"{name}.{value.privilege_class.value} write requires "
            "prepared_action_required=true"
        )
    if (
        value.write_capable
        and value.privilege_class is PrivilegeClass.A3_ADMIN
        and not value.confirmation_required
    ):
        raise CapabilityProjectionError(
            f"{name}.A3_ADMIN write requires confirmation_required=true"
        )

    if not isinstance(value.dependencies, tuple):
        raise CapabilityProjectionError(
            f"{name}.dependencies must be an immutable tuple"
        )
    if len(value.dependencies) > MAX_DEPENDENCIES:
        raise CapabilityProjectionError(
            f"{name}.dependencies must contain at most {MAX_DEPENDENCIES} items"
        )
    dependencies: list[DependencyFact] = []
    seen: set[str] = set()
    for raw in value.dependencies:
        dependency = _dependency(raw, name)
        if dependency.name in seen:
            raise CapabilityProjectionError(
                f"capability {name!r} contains duplicate dependency {dependency.name!r}"
            )
        seen.add(dependency.name)
        dependencies.append(
            DependencyFact(
                dependency.name,
                dependency.state,
                dependency.required,
                dependency.available,
                dependency.source_ref,
                dependency.issues,
            )
        )
    dependencies.sort(key=lambda dependency: dependency.name)

    return CapabilityFact(
        name,
        _identifier(value.app_id, f"{name}.app_id"),
        _identifier(value.app_generation, f"{name}.app_generation"),
        value.privilege_class,
        value.production_armed,
        required,
        writes,
        _scopes(value.current_scopes, f"{name}.current_scopes"),
        value.confirmation_required,
        value.prepared_action_required,
        _identifier(value.canonical_owner, f"{name}.canonical_owner"),
        tuple(dependencies),
        _digest_value(value.schema_digest, f"{name}.schema_digest"),
        value.source_state,
        value.observed_available,
        value.live_proof_current,
        value.write_capable,
        _timestamp(value.last_proven_at, f"{name}.last_proven_at", optional=True),
        _sources(value.source_refs, f"{name}.source_refs"),
        _issues(value.issues, f"{name}.issues"),
    )


def _project(fact: CapabilityFact, observed: datetime) -> CapabilityStatus:
    dependencies = tuple(_dependency(dependency, fact.name) for dependency in fact.dependencies)
    issues = set(fact.issues)
    required = set(fact.required_scopes)
    writes = set(fact.required_write_scopes)
    current = set(fact.current_scopes)
    reads = tuple(sorted(required - writes))
    missing = tuple(sorted(required - current))
    excess = tuple(sorted(current - required))
    missing_reads = tuple(scope for scope in missing if scope not in writes)
    missing_writes = tuple(scope for scope in missing if scope in writes)
    if missing:
        issues.add("REQUIRED_SCOPE_MISSING")
    if excess:
        issues.add("EXCESS_SCOPE_PRESENT")

    rejected = False
    broken = False
    disconnected = False
    spec_only = False
    partial = False
    unknown = False
    for dependency in dependencies:
        if not dependency.required:
            continue
        if dependency.available is None:
            unknown = True
            issues.add("DEPENDENCY_AVAILABILITY_UNKNOWN")
        elif dependency.available is False:
            disconnected = True
            issues.add("DEPENDENCY_UNAVAILABLE")
        if dependency.state is CapabilityState.REJECTED_BY_DESIGN:
            rejected = True
            issues.add("DEPENDENCY_REJECTED_BY_DESIGN")
        elif dependency.state is CapabilityState.BROKEN:
            broken = True
            issues.add("DEPENDENCY_BROKEN")
        elif dependency.state in (
            CapabilityState.NOT_BUILT,
            CapabilityState.DARK_OR_DISCONNECTED,
        ):
            disconnected = True
            issues.add(f"DEPENDENCY_{dependency.state.value}")
        elif dependency.state is CapabilityState.SPEC_ONLY:
            spec_only = True
            issues.add("DEPENDENCY_SPEC_ONLY")
        elif dependency.state in (
            CapabilityState.PARTIAL,
            CapabilityState.BUILT_NOT_PROVEN,
        ):
            partial = True
            issues.add(f"DEPENDENCY_{dependency.state.value}")

    future = bool(
        fact.last_proven_at
        and _instant(fact.last_proven_at, f"{fact.name}.last_proven_at") > observed
    )
    if future:
        issues.add("LIVE_PROOF_FUTURE")
    proof_ok = bool(fact.live_proof_current and fact.last_proven_at and not future)
    proof = fact.source_state
    availability = Availability.UNAVAILABLE
    read_ok = False
    write_ok = False

    if fact.source_state is CapabilityState.REJECTED_BY_DESIGN:
        availability = Availability.REFUSED
        issues.add("CAPABILITY_REJECTED_BY_DESIGN")
    elif rejected:
        proof = CapabilityState.REJECTED_BY_DESIGN
        availability = Availability.REFUSED
    elif fact.source_state in (
        CapabilityState.NOT_BUILT,
        CapabilityState.SPEC_ONLY,
        CapabilityState.BROKEN,
    ):
        issues.add(f"CAPABILITY_{fact.source_state.value}")
    elif broken:
        proof = CapabilityState.BROKEN
    elif spec_only:
        proof = CapabilityState.SPEC_ONLY
        issues.add("CAPABILITY_UNAVAILABLE")
    elif (
        disconnected
        or fact.source_state is CapabilityState.DARK_OR_DISCONNECTED
    ):
        proof = CapabilityState.DARK_OR_DISCONNECTED
        issues.add("CAPABILITY_UNAVAILABLE")
    elif fact.observed_available is None or unknown:
        availability = Availability.UNKNOWN
        issues.add("AVAILABILITY_UNKNOWN")
        if partial or fact.source_state is CapabilityState.PARTIAL:
            proof = CapabilityState.PARTIAL
        elif proof is CapabilityState.PROVEN_LIVE:
            proof = CapabilityState.BUILT_NOT_PROVEN
    elif fact.observed_available is False:
        proof = CapabilityState.DARK_OR_DISCONNECTED
        issues.add("CAPABILITY_UNAVAILABLE")
    elif missing_reads:
        proof = CapabilityState.DARK_OR_DISCONNECTED
        issues.add("READ_SCOPE_MISSING")
    else:
        read_ok = True
        if partial or fact.source_state is CapabilityState.PARTIAL:
            proof = CapabilityState.PARTIAL
            availability = Availability.DEGRADED
        elif fact.source_state is CapabilityState.DARK_OR_DISCONNECTED:
            proof = CapabilityState.DARK_OR_DISCONNECTED
            availability = Availability.UNAVAILABLE
            read_ok = False
        else:
            availability = Availability.AVAILABLE

        if not proof_ok:
            issues.add("LIVE_PROOF_MISSING")
            if proof is CapabilityState.PROVEN_LIVE:
                proof = CapabilityState.BUILT_NOT_PROVEN
        if missing_writes:
            proof = CapabilityState.PARTIAL

        privilege_guards_ok = bool(
            fact.privilege_class is not PrivilegeClass.R0_OBSERVE
            and (
                fact.privilege_class
                not in {PrivilegeClass.W2_CONSEQUENTIAL, PrivilegeClass.A3_ADMIN}
                or fact.prepared_action_required
            )
            and (
                fact.privilege_class is not PrivilegeClass.A3_ADMIN
                or fact.confirmation_required
            )
        )
        write_ok = bool(
            privilege_guards_ok
            and fact.write_capable
            and read_ok
            and not missing
            and not partial
            and fact.production_armed
            and proof_ok
            and proof
            not in (
                CapabilityState.PARTIAL,
                CapabilityState.DARK_OR_DISCONNECTED,
                CapabilityState.BROKEN,
                CapabilityState.SPEC_ONLY,
                CapabilityState.NOT_BUILT,
                CapabilityState.REJECTED_BY_DESIGN,
            )
        )

        if fact.write_capable and not fact.production_armed:
            issues.add("PRODUCTION_DISARMED")
            if proof is CapabilityState.PROVEN_LIVE:
                proof = CapabilityState.BUILT_NOT_PROVEN
        if (
            fact.write_capable
            and read_ok
            and not write_ok
            and availability is Availability.AVAILABLE
        ):
            availability = Availability.READ_ONLY
        can_promote = bool(
            proof_ok
            and read_ok
            and not partial
            and not missing
            and (not fact.write_capable or write_ok)
        )
        if (
            fact.source_state is CapabilityState.BUILT_NOT_PROVEN
            and can_promote
        ):
            proof = CapabilityState.PROVEN_LIVE
        if missing_writes and read_ok:
            availability = Availability.READ_ONLY

    return CapabilityStatus(
        fact.name,
        fact.app_id,
        fact.app_generation,
        fact.privilege_class,
        availability,
        fact.production_armed,
        fact.required_scopes,
        reads,
        fact.required_write_scopes,
        fact.current_scopes,
        missing,
        excess,
        fact.confirmation_required,
        fact.prepared_action_required,
        fact.canonical_owner,
        dependencies,
        fact.schema_digest,
        proof,
        fact.last_proven_at,
        read_ok,
        write_ok,
        fact.source_refs,
        tuple(sorted(issues)),
    )


def project_sol_capability_status(
    facts: Iterable[CapabilityFact],
    *,
    observed_at: str,
    capability_generation: str,
) -> CapabilityStatusEnvelope:
    observed_text = _timestamp(observed_at, "observed_at")
    assert observed_text is not None
    generation = _identifier(capability_generation, "capability_generation")
    if isinstance(facts, (str, bytes)):
        raise CapabilityProjectionError(
            "facts must be an iterable of CapabilityFact"
        )
    try:
        iterator = iter(facts)
    except TypeError as exc:
        raise CapabilityProjectionError(
            "facts must be an iterable of CapabilityFact"
        ) from exc

    normalized: list[CapabilityFact] = []
    for index, value in enumerate(iterator):
        if index >= MAX_CAPABILITIES:
            raise CapabilityProjectionError(
                f"facts must contain at most {MAX_CAPABILITIES} capabilities"
            )
        normalized.append(_fact(value))
    names = [fact.name for fact in normalized]
    if len(names) != len(set(names)):
        duplicate = next(name for name in names if names.count(name) > 1)
        raise CapabilityProjectionError(
            f"duplicate capability name {duplicate!r}"
        )
    normalized.sort(key=lambda fact: fact.name)
    observed = _instant(observed_text, "observed_at")
    statuses = tuple(_project(fact, observed) for fact in normalized)
    issues = () if statuses else ("NO_CAPABILITIES_OBSERVED",)
    payload = {
        "schema": SCHEMA,
        "capability_generation": generation,
        "observed_at": observed_text,
        "capabilities": [status.to_dict() for status in statuses],
        "issues": list(issues),
    }
    return CapabilityStatusEnvelope(
        SCHEMA,
        generation,
        observed_text,
        statuses,
        issues,
        _digest(payload),
    )


__all__ = [
    "MAX_CAPABILITIES",
    "MAX_DEPENDENCIES",
    "MAX_ISSUES",
    "MAX_SCOPES",
    "MAX_SOURCE_REFS",
    "MAX_TIMESTAMP_LENGTH",
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
