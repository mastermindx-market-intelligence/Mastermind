"""Pure R0 operations-health projection for Sol Capability Fabric.

Callers supply immutable facts from exact service/tunnel owners. This module
performs no I/O, owns no service lifecycle or registry, grants no authority,
and persists nothing.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

SCHEMA = "mastermind.sol_ops_health.v1"
MAX_SERVICES = 64
MAX_TUNNELS = 64
MAX_SOURCE_REFS = 16
MAX_ISSUES = 32
MAX_TIMESTAMP_LENGTH = 32

_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_TUNNEL = re.compile(r"^tunnel_[0-9a-f]{32}$")
_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/@-]{0,255}$")
_ISSUE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,127}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")
_RFC3339 = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$"
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
        r"api[_-]?key\s*=",
        r"-----BEGIN",
    )
)


class OpsHealthError(ValueError):
    """Owner facts are malformed, conflicting, future-invalid, or unsafe."""


class OpsState(str, Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


def _secret(value: str, field: str) -> None:
    if any(pattern.search(value) for pattern in _SECRET):
        raise OpsHealthError(f"{field} contains secret-shaped text")


def _token(value: object, field: str, pattern: re.Pattern[str], message: str) -> str:
    if type(value) is not str:
        raise OpsHealthError(f"{field} must be a string")
    raw = value.strip()
    if raw != value:
        raise OpsHealthError(f"{field} must not contain surrounding whitespace")
    _secret(raw, field)
    if pattern.fullmatch(raw) is None:
        raise OpsHealthError(f"{field} {message}")
    return raw


def _identifier(value: object, field: str) -> str:
    return _token(value, field, _ID, "must be a bounded lowercase identifier")


def _optional_version(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _token(value, field, _VERSION, "contains an invalid version")


def _optional_identifier(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, field)


def _timestamp(value: object, field: str) -> str:
    error = OpsHealthError(f"{field} must be an RFC3339 timestamp")
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
        if parsed.tzinfo is None:
            raise ValueError
        utc = parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise error
    timespec = "microseconds" if utc.microsecond else "seconds"
    return utc.isoformat(timespec=timespec).replace("+00:00", "Z")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _signals(live: object, ready: object, field: str) -> tuple[bool | None, bool | None]:
    for name, value in (("live", live), ("ready", ready)):
        if value is not None and type(value) is not bool:
            raise OpsHealthError(f"{field}.{name} must be boolean or null")
    return live, ready


def _tuple_tokens(
    values: object,
    field: str,
    pattern: re.Pattern[str],
    *,
    maximum: int,
    nonempty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, tuple) or (nonempty and not values):
        shape = "non-empty immutable tuple" if nonempty else "immutable tuple"
        raise OpsHealthError(f"{field} must be a {shape}")
    if len(values) > maximum:
        raise OpsHealthError(f"{field} must contain at most {maximum} items")
    out: list[str] = []
    for raw in values:
        item = _token(raw, field, pattern, "contains an invalid value")
        if item in out:
            raise OpsHealthError(f"{field} contains duplicate value {item!r}")
        out.append(item)
    return tuple(sorted(out))


def _sources(values: object, field: str) -> tuple[str, ...]:
    return _tuple_tokens(
        values, field, _SOURCE, maximum=MAX_SOURCE_REFS, nonempty=True
    )


def _issues(values: object, field: str) -> tuple[str, ...]:
    return _tuple_tokens(values, field, _ISSUE, maximum=MAX_ISSUES)


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
class ServiceFact:
    service_ref: str
    service_kind: str
    scope: str
    owner_ref: str
    observed_at: str
    live: bool | None
    ready: bool | None
    runtime_version: str | None
    deployment_ref: str | None
    source_refs: tuple[str, ...]
    issues: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class TunnelFact:
    tunnel_ref: str
    service_ref: str
    owner_ref: str
    observed_at: str
    live: bool | None
    ready: bool | None
    source_refs: tuple[str, ...]
    issues: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class ServiceHealth:
    service_ref: str
    service_kind: str
    scope: str
    owner_ref: str
    observed_at: str
    state: OpsState
    live: bool | None
    ready: bool | None
    runtime_version: str | None
    deployment_ref: str | None
    source_refs: tuple[str, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            **dataclasses.asdict(self),
            "state": self.state.value,
            "source_refs": list(self.source_refs),
            "issues": list(self.issues),
        }


@dataclasses.dataclass(frozen=True)
class TunnelHealth:
    tunnel_ref: str
    service_ref: str
    owner_ref: str
    observed_at: str
    state: OpsState
    live: bool | None
    ready: bool | None
    source_refs: tuple[str, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            **dataclasses.asdict(self),
            "state": self.state.value,
            "source_refs": list(self.source_refs),
            "issues": list(self.issues),
        }


@dataclasses.dataclass(frozen=True)
class OpsHealthEnvelope:
    schema: str
    generation: str
    observed_at: str
    overall_state: OpsState
    services: tuple[ServiceHealth, ...]
    tunnels: tuple[TunnelHealth, ...]
    issues: tuple[str, ...]
    canonical_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "generation": self.generation,
            "observed_at": self.observed_at,
            "overall_state": self.overall_state.value,
            "services": [row.to_dict() for row in self.services],
            "tunnels": [row.to_dict() for row in self.tunnels],
            "issues": list(self.issues),
            "canonical_digest": self.canonical_digest,
        }


def _state(live: bool | None, ready: bool | None, issues: tuple[str, ...]) -> OpsState:
    if live is False:
        return OpsState.UNAVAILABLE
    if live is None or ready is None:
        return OpsState.UNKNOWN
    if not ready or issues:
        return OpsState.DEGRADED
    return OpsState.READY


def _service(raw: ServiceFact, envelope_observed: datetime) -> ServiceHealth:
    if not isinstance(raw, ServiceFact):
        raise OpsHealthError("services must contain ServiceFact")
    ref = _identifier(raw.service_ref, "service.service_ref")
    kind = _identifier(raw.service_kind, f"{ref}.service_kind")
    scope = _identifier(raw.scope, f"{ref}.scope")
    owner = _identifier(raw.owner_ref, f"{ref}.owner_ref")
    observed = _timestamp(raw.observed_at, f"{ref}.observed_at")
    if _instant(observed) > envelope_observed:
        raise OpsHealthError(f"{ref}.observed_at cannot be in the future")
    live, ready = _signals(raw.live, raw.ready, ref)
    issues = _issues(raw.issues, f"{ref}.issues")
    return ServiceHealth(
        ref,
        kind,
        scope,
        owner,
        observed,
        _state(live, ready, issues),
        live,
        ready,
        _optional_version(raw.runtime_version, f"{ref}.runtime_version"),
        _optional_identifier(raw.deployment_ref, f"{ref}.deployment_ref"),
        _sources(raw.source_refs, f"{ref}.source_refs"),
        issues,
    )


def _tunnel(raw: TunnelFact, envelope_observed: datetime) -> TunnelHealth:
    if not isinstance(raw, TunnelFact):
        raise OpsHealthError("tunnels must contain TunnelFact")
    ref = _token(raw.tunnel_ref, "tunnel.tunnel_ref", _TUNNEL, "must be a tunnel id")
    service_ref = _identifier(raw.service_ref, f"{ref}.service_ref")
    owner = _identifier(raw.owner_ref, f"{ref}.owner_ref")
    observed = _timestamp(raw.observed_at, f"{ref}.observed_at")
    if _instant(observed) > envelope_observed:
        raise OpsHealthError(f"{ref}.observed_at cannot be in the future")
    live, ready = _signals(raw.live, raw.ready, ref)
    issues = _issues(raw.issues, f"{ref}.issues")
    return TunnelHealth(
        ref,
        service_ref,
        owner,
        observed,
        _state(live, ready, issues),
        live,
        ready,
        _sources(raw.source_refs, f"{ref}.source_refs"),
        issues,
    )


def _overall(states: Iterable[OpsState]) -> OpsState:
    states = tuple(states)
    if not states:
        return OpsState.UNKNOWN
    for state in (OpsState.UNAVAILABLE, OpsState.DEGRADED, OpsState.UNKNOWN):
        if state in states:
            return state
    return OpsState.READY


def project_ops_health(
    services: Iterable[ServiceFact],
    tunnels: Iterable[TunnelFact],
    *,
    observed_at: str,
    generation: str,
) -> OpsHealthEnvelope:
    observed_text = _timestamp(observed_at, "observed_at")
    observed = _instant(observed_text)
    generation_value = _identifier(generation, "generation")

    service_rows: list[ServiceHealth] = []
    for index, raw in enumerate(services):
        if index >= MAX_SERVICES:
            raise OpsHealthError(f"services must contain at most {MAX_SERVICES} rows")
        service_rows.append(_service(raw, observed))
    service_rows.sort(key=lambda row: row.service_ref)
    refs = [row.service_ref for row in service_rows]
    if len(refs) != len(set(refs)):
        duplicate = next(ref for ref in refs if refs.count(ref) > 1)
        raise OpsHealthError(f"duplicate service_ref {duplicate!r}")

    service_set = set(refs)
    tunnel_rows: list[TunnelHealth] = []
    for index, raw in enumerate(tunnels):
        if index >= MAX_TUNNELS:
            raise OpsHealthError(f"tunnels must contain at most {MAX_TUNNELS} rows")
        row = _tunnel(raw, observed)
        if row.service_ref not in service_set:
            raise OpsHealthError(
                f"tunnel {row.tunnel_ref!r} references unknown service_ref {row.service_ref!r}"
            )
        tunnel_rows.append(row)
    tunnel_rows.sort(key=lambda row: row.tunnel_ref)
    tunnel_refs = [row.tunnel_ref for row in tunnel_rows]
    if len(tunnel_refs) != len(set(tunnel_refs)):
        duplicate = next(ref for ref in tunnel_refs if tunnel_refs.count(ref) > 1)
        raise OpsHealthError(f"duplicate tunnel_ref {duplicate!r}")

    issues: tuple[str, ...] = ()
    if not service_rows:
        issues = ("NO_SERVICES_OBSERVED",)
    overall = _overall(
        [row.state for row in service_rows] + [row.state for row in tunnel_rows]
    )
    payload = {
        "schema": SCHEMA,
        "generation": generation_value,
        "observed_at": observed_text,
        "overall_state": overall.value,
        "services": [row.to_dict() for row in service_rows],
        "tunnels": [row.to_dict() for row in tunnel_rows],
        "issues": list(issues),
    }
    return OpsHealthEnvelope(
        SCHEMA,
        generation_value,
        observed_text,
        overall,
        tuple(service_rows),
        tuple(tunnel_rows),
        issues,
        _digest(payload),
    )


__all__ = [
    "OpsHealthEnvelope",
    "OpsHealthError",
    "OpsState",
    "SCHEMA",
    "ServiceFact",
    "ServiceHealth",
    "TunnelFact",
    "TunnelHealth",
    "project_ops_health",
]
