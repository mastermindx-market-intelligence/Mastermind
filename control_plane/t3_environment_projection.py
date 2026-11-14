"""Closed, read-only T3 environment projection.

This module joins exactly two already-collected facts: one
``mastermind.host_readiness_snapshot/v1`` host observation and one
``mastermind.t3_environment_observation/v1`` fact set.  It owns no launch,
spawn, provider process, credential read, pairing, admission, placement or
Runtime authority.

Honesty rule (WO-04 thermal): a capability is ``ready`` only when the joined
evidence says so.  A missing, ``None`` or unobserved fact is ``unknown`` and
``unknown`` is never treated as ``ready``, so an unobservable thermal state
blocks ``launch_eligible`` instead of being assumed nominal.

This module is pure standard library and performs no I/O of its own; the
registry reader only reads caller-supplied host snapshot files.
"""
from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OBSERVATION_SCHEMA = "mastermind.t3_environment_observation/v1"
PROJECTION_SCHEMA = "mastermind.t3_environment_projection/v1"
HOST_SNAPSHOT_SCHEMA = "mastermind.host_readiness_snapshot/v1"
TARGET_KIND = "t3"

DEFAULT_FRESHNESS_WINDOW_S = 45.0
MAX_SOURCE_CHARS = 160
MAX_VERSION_CHARS = 64
MAX_PROVIDER_ID_CHARS = 128

CAPABILITY_READY = "ready"
CAPABILITY_DEGRADED = "degraded"
CAPABILITY_UNKNOWN = "unknown"
CAPABILITY_STATES = frozenset(
    {CAPABILITY_READY, CAPABILITY_DEGRADED, CAPABILITY_UNKNOWN}
)

# Every projection must carry these keys.  Additional keys are permitted only
# when their value is also one of CAPABILITY_STATES, so a host owner cannot add
# an ungraded "ready-ish" capability.
REQUIRED_CAPABILITIES = (
    "host_reachable",
    "t3_server_reachable",
    "auth",
    "service_persistence",
    "provider_sessions",
    "workspace_scratch",
)
CAPABILITY_KEYS = (*REQUIRED_CAPABILITIES, "host_thermal")

_SERVICE_STATES = frozenset({"running", "stopped", CAPABILITY_UNKNOWN})
_PERSISTENCE_STATES = frozenset({"lingering", "login_bound", CAPABILITY_UNKNOWN})
_AUTH_STATES = frozenset({"paired", "unpaired", CAPABILITY_UNKNOWN})
_THERMAL_READY = frozenset({"nominal", "normal", "ok"})
_THERMAL_DEGRADED = frozenset(
    {"throttled", "fair", "serious", "critical", "hot", "overheated"}
)

_ENVIRONMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ENDPOINT_RE = re.compile(r"^(?P<host>[A-Za-z0-9][A-Za-z0-9.-]{0,252}):(?P<port>[0-9]{1,5})$")


class T3ProjectionError(ValueError):
    """A closed, non-secret T3 projection refusal."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> None:
    raise T3ProjectionError(code)


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

_OBSERVATION_KEYS = frozenset(
    {
        "schema",
        "environment_id",
        "server_endpoint",
        "service_state",
        "service_persistence",
        "auth_state",
        "version",
        "provider_instance_ids",
        "reachable",
        "observed_at_utc",
        "source",
    }
)
_REQUIRED_OBSERVATION_KEYS = frozenset(
    {"environment_id", "observed_at_utc", "source"}
)
_OBSERVATION_DEFAULTS: dict[str, Any] = {
    "schema": OBSERVATION_SCHEMA,
    "server_endpoint": None,
    "service_state": CAPABILITY_UNKNOWN,
    "service_persistence": CAPABILITY_UNKNOWN,
    "auth_state": CAPABILITY_UNKNOWN,
    "version": None,
    "provider_instance_ids": None,
    "reachable": None,
}


def _utc_datetime(value: Any, code: str) -> datetime:
    """Parse one explicit-offset instant; never assume a naive local zone."""
    if type(value) is not str or not value:
        _refuse(code)
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        _refuse(code)
    if parsed.tzinfo is None:
        _refuse(code)
    return parsed.astimezone(timezone.utc)


def _environment_id(value: Any) -> str:
    if type(value) is not str or _ENVIRONMENT_ID_RE.fullmatch(value) is None:
        _refuse("ENVIRONMENT_ID_INVALID")
    return value


def _endpoint(value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        _refuse("SERVER_ENDPOINT_INVALID")
    match = _ENDPOINT_RE.fullmatch(value)
    if match is None:
        _refuse("SERVER_ENDPOINT_INVALID")
    if not 1 <= int(match.group("port")) <= 65535:
        _refuse("SERVER_ENDPOINT_INVALID")
    return value


def _provenance(value: Any) -> str:
    if (
        type(value) is not str
        or not value.strip()
        or value != value.strip()
        or "\n" in value
        or len(value) > MAX_SOURCE_CHARS
    ):
        _refuse("OBSERVATION_SOURCE_INVALID")
    return value


def _provider_ids(value: Any) -> list[str] | None:
    if value is None:
        return None
    if type(value) is not list:
        _refuse("PROVIDER_INSTANCE_IDS_INVALID")
    for item in value:
        if (
            type(item) is not str
            or not item.strip()
            or len(item) > MAX_PROVIDER_ID_CHARS
        ):
            _refuse("PROVIDER_INSTANCE_IDS_INVALID")
    if len(set(value)) != len(value):
        _refuse("PROVIDER_INSTANCE_IDS_INVALID")
    return list(value)


def _normalize_observation_payload(payload: Any) -> dict[str, Any]:
    """Return the canonical observation payload or refuse the closed contract.

    Absent optional facts are filled with their unknown/``None`` value; they are
    never filled with a guess.  Present values must be exactly valid.
    """
    if not isinstance(payload, Mapping):
        _refuse("OBSERVATION_FIELDS_INVALID")
    keys = set(payload)
    if keys - _OBSERVATION_KEYS:
        _refuse("OBSERVATION_FIELDS_INVALID")
    if _REQUIRED_OBSERVATION_KEYS - keys:
        _refuse("OBSERVATION_FIELDS_MISSING")
    merged = {**_OBSERVATION_DEFAULTS, **payload}
    if merged.get("schema") != OBSERVATION_SCHEMA:
        _refuse("OBSERVATION_SCHEMA_INVALID")

    environment_id = _environment_id(merged.get("environment_id"))
    observed_at_utc = merged.get("observed_at_utc")
    _utc_datetime(observed_at_utc, "OBSERVED_AT_INVALID")
    source = _provenance(merged.get("source"))
    server_endpoint = _endpoint(merged.get("server_endpoint"))

    service_state = merged.get("service_state")
    if service_state not in _SERVICE_STATES:
        _refuse("SERVICE_STATE_INVALID")
    service_persistence = merged.get("service_persistence")
    if service_persistence not in _PERSISTENCE_STATES:
        _refuse("SERVICE_PERSISTENCE_INVALID")
    auth_state = merged.get("auth_state")
    if auth_state not in _AUTH_STATES:
        _refuse("AUTH_STATE_INVALID")

    version = merged.get("version")
    if version is not None and (
        type(version) is not str
        or not version.strip()
        or len(version) > MAX_VERSION_CHARS
    ):
        _refuse("VERSION_INVALID")

    provider_instance_ids = _provider_ids(merged.get("provider_instance_ids"))
    reachable = merged.get("reachable")
    if reachable is not None and type(reachable) is not bool:
        _refuse("REACHABLE_INVALID")
    if reachable is True and server_endpoint is None:
        # Reachability of an endpoint nobody observed is not evidence.
        _refuse("SERVER_ENDPOINT_REQUIRED")

    return {
        "schema": OBSERVATION_SCHEMA,
        "environment_id": environment_id,
        "server_endpoint": server_endpoint,
        "service_state": service_state,
        "service_persistence": service_persistence,
        "auth_state": auth_state,
        "version": version,
        "provider_instance_ids": provider_instance_ids,
        "reachable": reachable,
        "observed_at_utc": observed_at_utc,
        "source": source,
    }


@dataclasses.dataclass(frozen=True)
class T3EnvironmentObservation:
    """One owner-supplied T3 environment fact set; unknown is a real value."""

    environment_id: str
    observed_at_utc: str
    source: str
    schema: str = OBSERVATION_SCHEMA
    server_endpoint: str | None = None
    service_state: str = CAPABILITY_UNKNOWN
    service_persistence: str = CAPABILITY_UNKNOWN
    auth_state: str = CAPABILITY_UNKNOWN
    version: str | None = None
    provider_instance_ids: tuple[str, ...] | None = None
    reachable: bool | None = None

    def __post_init__(self) -> None:
        payload = self.to_dict()
        if payload != _normalize_observation_payload(payload):
            _refuse("OBSERVATION_VALUE_INVALID")

    def to_dict(self) -> dict[str, Any]:
        ids = self.provider_instance_ids
        return {
            "schema": self.schema,
            "environment_id": self.environment_id,
            "server_endpoint": self.server_endpoint,
            "service_state": self.service_state,
            "service_persistence": self.service_persistence,
            "auth_state": self.auth_state,
            "version": self.version,
            "provider_instance_ids": None if ids is None else list(ids),
            "reachable": self.reachable,
            "observed_at_utc": self.observed_at_utc,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "T3EnvironmentObservation":
        normalized = _normalize_observation_payload(value)
        ids = normalized["provider_instance_ids"]
        return cls(
            **{
                **normalized,
                "provider_instance_ids": None if ids is None else tuple(ids),
            }
        )


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

_PROJECTION_KEYS = frozenset(
    {
        "schema",
        "host_id",
        "host_boot_id",
        "environment_id",
        "server_endpoint",
        "service_state",
        "service_persistence",
        "auth_state",
        "version",
        "provider_instance_ids",
        "reachable",
        "observed_at_utc",
        "host_observed_at_utc",
        "host_reachable",
        "source",
        "capabilities",
        "launch_eligible",
    }
)


def _capabilities(
    *,
    host_reachable: bool | None,
    reachable: bool | None,
    auth_state: str,
    service_persistence: str,
    service_state: str,
    provider_instance_ids: tuple[str, ...] | None,
    runtime_dir_free_gib: float | None,
    thermal: str | None,
) -> dict[str, str]:
    """Derive each capability from evidence only; unknown stays unknown."""
    if host_reachable is True:
        host_state = CAPABILITY_READY
    elif host_reachable is False:
        host_state = CAPABILITY_DEGRADED
    else:
        host_state = CAPABILITY_UNKNOWN

    if reachable is True:
        t3_state = CAPABILITY_READY
    elif reachable is False:
        t3_state = CAPABILITY_DEGRADED
    else:
        t3_state = CAPABILITY_UNKNOWN

    auth = {
        "paired": CAPABILITY_READY,
        "unpaired": CAPABILITY_DEGRADED,
    }.get(auth_state, CAPABILITY_UNKNOWN)

    persistence = {
        "lingering": CAPABILITY_READY,
        "login_bound": CAPABILITY_DEGRADED,
    }.get(service_persistence, CAPABILITY_UNKNOWN)

    # A provider session list is only meaningful for an observed listing.
    if provider_instance_ids is None or service_state == CAPABILITY_UNKNOWN:
        provider_sessions = CAPABILITY_UNKNOWN
    elif service_state == "stopped" or not provider_instance_ids:
        provider_sessions = CAPABILITY_DEGRADED
    else:
        provider_sessions = CAPABILITY_READY

    # Last-known free space is not evidenced for an unreachable host.
    if runtime_dir_free_gib is None or host_reachable is not True:
        workspace_scratch = CAPABILITY_UNKNOWN
    elif runtime_dir_free_gib <= 0:
        workspace_scratch = CAPABILITY_DEGRADED
    else:
        workspace_scratch = CAPABILITY_READY

    if thermal is None or thermal == CAPABILITY_UNKNOWN:
        thermal_state = CAPABILITY_UNKNOWN
    elif thermal in _THERMAL_READY:
        thermal_state = CAPABILITY_READY
    elif thermal in _THERMAL_DEGRADED:
        thermal_state = CAPABILITY_DEGRADED
    else:
        thermal_state = CAPABILITY_UNKNOWN

    return {
        "host_reachable": host_state,
        "t3_server_reachable": t3_state,
        "auth": auth,
        "service_persistence": persistence,
        "provider_sessions": provider_sessions,
        "workspace_scratch": workspace_scratch,
        "host_thermal": thermal_state,
    }


@dataclasses.dataclass(frozen=True)
class T3EnvironmentProjection:
    """Joined host/environment view.  Carries no launch or admission authority."""

    host_id: str
    environment_id: str
    schema: str = PROJECTION_SCHEMA
    host_boot_id: str = ""
    server_endpoint: str | None = None
    service_state: str = CAPABILITY_UNKNOWN
    service_persistence: str = CAPABILITY_UNKNOWN
    auth_state: str = CAPABILITY_UNKNOWN
    version: str | None = None
    provider_instance_ids: tuple[str, ...] | None = None
    reachable: bool | None = None
    observed_at_utc: str = ""
    host_observed_at_utc: str | None = None
    host_reachable: bool | None = None
    source: str = ""
    capabilities: Mapping[str, str] = dataclasses.field(default_factory=dict)
    launch_eligible: bool = False

    def __post_init__(self) -> None:
        payload = self.to_dict()
        if payload != _normalize_projection_payload(payload):
            _refuse("PROJECTION_VALUE_INVALID")

    def to_dict(self) -> dict[str, Any]:
        ids = self.provider_instance_ids
        return {
            "schema": self.schema,
            "host_id": self.host_id,
            "host_boot_id": self.host_boot_id,
            "environment_id": self.environment_id,
            "server_endpoint": self.server_endpoint,
            "service_state": self.service_state,
            "service_persistence": self.service_persistence,
            "auth_state": self.auth_state,
            "version": self.version,
            "provider_instance_ids": None if ids is None else list(ids),
            "reachable": self.reachable,
            "observed_at_utc": self.observed_at_utc,
            "host_observed_at_utc": self.host_observed_at_utc,
            "host_reachable": self.host_reachable,
            "source": self.source,
            "capabilities": dict(sorted(dict(self.capabilities).items())),
            "launch_eligible": self.launch_eligible,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "T3EnvironmentProjection":
        if not isinstance(value, Mapping):
            _refuse("PROJECTION_FIELDS_INVALID")
        payload = dict(value)
        # The schema marker is a constant of this contract, not caller data.
        schema = payload.pop("schema", PROJECTION_SCHEMA)
        if schema != PROJECTION_SCHEMA:
            _refuse("PROJECTION_SCHEMA_INVALID")
        normalized = _normalize_projection_payload(
            {**payload, "schema": PROJECTION_SCHEMA}
        )
        ids = normalized["provider_instance_ids"]
        return cls(
            **{
                **normalized,
                "provider_instance_ids": None if ids is None else tuple(ids),
            }
        )


def _normalize_projection_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _PROJECTION_KEYS:
        _refuse("PROJECTION_FIELDS_INVALID")
    if payload.get("schema") != PROJECTION_SCHEMA:
        _refuse("PROJECTION_SCHEMA_INVALID")

    host_id = payload.get("host_id")
    if type(host_id) is not str or not host_id.strip():
        _refuse("HOST_ID_INVALID")
    host_boot_id = payload.get("host_boot_id")
    if type(host_boot_id) is not str:
        _refuse("HOST_BOOT_ID_INVALID")
    environment_id = _environment_id(payload.get("environment_id"))
    server_endpoint = _endpoint(payload.get("server_endpoint"))

    service_state = payload.get("service_state")
    if service_state not in _SERVICE_STATES:
        _refuse("SERVICE_STATE_INVALID")
    service_persistence = payload.get("service_persistence")
    if service_persistence not in _PERSISTENCE_STATES:
        _refuse("SERVICE_PERSISTENCE_INVALID")
    auth_state = payload.get("auth_state")
    if auth_state not in _AUTH_STATES:
        _refuse("AUTH_STATE_INVALID")

    version = payload.get("version")
    if version is not None and (
        type(version) is not str
        or not version.strip()
        or len(version) > MAX_VERSION_CHARS
    ):
        _refuse("VERSION_INVALID")
    provider_instance_ids = _provider_ids(payload.get("provider_instance_ids"))
    reachable = payload.get("reachable")
    if reachable is not None and type(reachable) is not bool:
        _refuse("REACHABLE_INVALID")
    host_reachable = payload.get("host_reachable")
    if host_reachable is not None and type(host_reachable) is not bool:
        _refuse("HOST_REACHABLE_INVALID")

    observed_at_utc = payload.get("observed_at_utc")
    if type(observed_at_utc) is not str:
        _refuse("OBSERVED_AT_INVALID")
    if observed_at_utc:
        _utc_datetime(observed_at_utc, "OBSERVED_AT_INVALID")
    host_observed_at_utc = payload.get("host_observed_at_utc")
    if host_observed_at_utc is not None:
        _utc_datetime(host_observed_at_utc, "HOST_OBSERVED_AT_INVALID")
    source = payload.get("source")
    if type(source) is not str:
        _refuse("OBSERVATION_SOURCE_INVALID")

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, Mapping):
        _refuse("CAPABILITIES_INVALID")
    missing = [key for key in REQUIRED_CAPABILITIES if key not in capabilities]
    if missing:
        _refuse("CAPABILITIES_MISSING")
    normalized_capabilities: dict[str, str] = {}
    for key, value in capabilities.items():
        if type(key) is not str or not key:
            _refuse("CAPABILITIES_INVALID")
        if value not in CAPABILITY_STATES:
            _refuse("CAPABILITY_STATE_INVALID")
        normalized_capabilities[key] = value

    launch_eligible = payload.get("launch_eligible")
    if type(launch_eligible) is not bool:
        _refuse("LAUNCH_ELIGIBLE_INVALID")
    if launch_eligible and any(
        state != CAPABILITY_READY for state in normalized_capabilities.values()
    ):
        # Eligibility cannot outrun its own capability evidence.
        _refuse("LAUNCH_ELIGIBLE_INCONSISTENT")
    if launch_eligible and host_reachable is not True:
        _refuse("LAUNCH_ELIGIBLE_INCONSISTENT")

    return {
        "schema": PROJECTION_SCHEMA,
        "host_id": host_id,
        "host_boot_id": host_boot_id,
        "environment_id": environment_id,
        "server_endpoint": server_endpoint,
        "service_state": service_state,
        "service_persistence": service_persistence,
        "auth_state": auth_state,
        "version": version,
        "provider_instance_ids": provider_instance_ids,
        "reachable": reachable,
        "observed_at_utc": observed_at_utc,
        "host_observed_at_utc": host_observed_at_utc,
        "host_reachable": host_reachable,
        "source": source,
        "capabilities": dict(sorted(normalized_capabilities.items())),
        "launch_eligible": launch_eligible,
    }


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def _now(clock: Any) -> datetime:
    value = clock() if callable(clock) else clock
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            _refuse("CLOCK_INVALID")
        return value.astimezone(timezone.utc)
    if type(value) in (int, float):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    _refuse("CLOCK_INVALID")


def _is_fresh(observed_at_utc: Any, now: datetime, window_s: float) -> bool:
    """Fresh means already observed and within the window; future is not fresh."""
    if type(observed_at_utc) is not str or not observed_at_utc:
        return False
    try:
        observed = _utc_datetime(observed_at_utc, "OBSERVED_AT_INVALID")
    except T3ProjectionError:
        return False
    age = (now - observed).total_seconds()
    return 0 <= age <= window_s


def _runtime_dir_free_gib(value: Any) -> float | None:
    if not isinstance(value, Mapping):
        return None
    disk = value.get("disk_free_gib")
    if not isinstance(disk, Mapping):
        return None
    free = disk.get("runtime_dir")
    if type(free) not in (int, float):
        return None
    return float(free)


def _thermal(value: Any) -> str | None:
    if type(value) is not str or not value.strip():
        return None
    return value.strip().lower()


def _host_facts(host_snapshot: Any) -> dict[str, Any]:
    """Read only the host facts this projection needs; absence is not a guess."""
    if not isinstance(host_snapshot, Mapping):
        _refuse("HOST_SNAPSHOT_INVALID")
    schema = host_snapshot.get("schema")
    if schema is not None and schema != HOST_SNAPSHOT_SCHEMA:
        _refuse("HOST_SNAPSHOT_SCHEMA_INVALID")
    host_id = host_snapshot.get("host_id")
    if type(host_id) is not str or not host_id.strip():
        _refuse("HOST_ID_INVALID")

    reachable = host_snapshot.get("reachable")
    if reachable is not None and type(reachable) is not bool:
        _refuse("HOST_REACHABLE_INVALID")

    boot_id = host_snapshot.get("boot_id")
    if boot_id is not None and type(boot_id) is not str:
        _refuse("HOST_BOOT_ID_INVALID")

    observed_at_utc = host_snapshot.get("observed_at_utc")
    if observed_at_utc is not None:
        _utc_datetime(observed_at_utc, "HOST_OBSERVED_AT_INVALID")

    unreachable_error = host_snapshot.get("unreachable_error")
    return {
        "host_id": host_id,
        "host_boot_id": boot_id or "",
        "reachable": reachable,
        "observed_at_utc": observed_at_utc,
        "runtime_dir_free_gib": _runtime_dir_free_gib(host_snapshot),
        "thermal": _thermal(host_snapshot.get("thermal")),
        "unreachable_error": (
            unreachable_error if type(unreachable_error) is str else None
        ),
    }


def project(
    host_snapshot: Mapping[str, Any],
    observation: T3EnvironmentObservation | Mapping[str, Any],
    clock: Callable[[], Any] | datetime | float | int | None = None,
    *,
    freshness_window_s: float = DEFAULT_FRESHNESS_WINDOW_S,
) -> T3EnvironmentProjection:
    """Join one host snapshot with one environment observation.

    ``launch_eligible`` is True only when the host is reachable, both the host
    snapshot and the observation are fresh within ``freshness_window_s``, and
    every capability is ``ready``.  It remains a readiness statement, never a
    launch grant.
    """
    if type(freshness_window_s) not in (int, float) or freshness_window_s <= 0:
        _refuse("FRESHNESS_WINDOW_INVALID")
    host = _host_facts(host_snapshot)
    facts = (
        observation
        if isinstance(observation, T3EnvironmentObservation)
        else T3EnvironmentObservation.from_dict(observation)
    )
    now = _now(clock)

    capabilities = _capabilities(
        host_reachable=host["reachable"],
        reachable=facts.reachable,
        auth_state=facts.auth_state,
        service_persistence=facts.service_persistence,
        service_state=facts.service_state,
        provider_instance_ids=facts.provider_instance_ids,
        runtime_dir_free_gib=host["runtime_dir_free_gib"],
        thermal=host["thermal"],
    )
    launch_eligible = (
        host["reachable"] is True
        and _is_fresh(host["observed_at_utc"], now, freshness_window_s)
        and _is_fresh(facts.observed_at_utc, now, freshness_window_s)
        and all(state == CAPABILITY_READY for state in capabilities.values())
    )
    return T3EnvironmentProjection(
        host_id=host["host_id"],
        host_boot_id=host["host_boot_id"],
        environment_id=facts.environment_id,
        server_endpoint=facts.server_endpoint,
        service_state=facts.service_state,
        service_persistence=facts.service_persistence,
        auth_state=facts.auth_state,
        version=facts.version,
        provider_instance_ids=facts.provider_instance_ids,
        reachable=facts.reachable,
        observed_at_utc=facts.observed_at_utc,
        host_observed_at_utc=host["observed_at_utc"],
        host_reachable=host["reachable"],
        source=facts.source,
        capabilities=capabilities,
        launch_eligible=launch_eligible,
    )


def project_registry(
    hosts_dir: str | Path,
    observations: Mapping[str, T3EnvironmentObservation | Mapping[str, Any]],
    clock: Callable[[], Any] | datetime | float | int | None = None,
    *,
    freshness_window_s: float = DEFAULT_FRESHNESS_WINDOW_S,
) -> tuple[tuple[T3EnvironmentProjection, ...], tuple[str, ...]]:
    """Project every readable ``hosts/*.json`` snapshot against one observation map.

    ``observations`` is keyed by host id.  Unreadable, malformed or
    observation-less hosts are skipped with a note instead of raising, because
    one bad snapshot must not hide the rest of the fleet.
    """
    notes: list[str] = []
    if not isinstance(observations, Mapping):
        _refuse("OBSERVATIONS_INVALID")
    directory = Path(hosts_dir)
    if not directory.is_dir():
        return (), (f"hosts_dir unavailable: {directory}",)

    projections: list[T3EnvironmentProjection] = []
    for path in sorted(directory.glob("*.json")):
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            notes.append(f"{path.name}: unreadable ({type(exc).__name__})")
            continue
        if not isinstance(snapshot, Mapping):
            notes.append(f"{path.name}: not an object")
            continue
        host_id = snapshot.get("host_id")
        if type(host_id) is not str or not host_id.strip():
            host_id = path.stem
            notes.append(f"{path.name}: host_id from filename")
        elif host_id != path.stem:
            notes.append(f"{path.name}: host_id field is {host_id}")
        observation = observations.get(host_id)
        if observation is None:
            notes.append(f"{host_id}: no t3 observation supplied")
            continue
        try:
            projections.append(
                project(
                    {**snapshot, "host_id": host_id},
                    observation,
                    clock,
                    freshness_window_s=freshness_window_s,
                )
            )
        except T3ProjectionError as exc:
            notes.append(f"{host_id}: {exc.code}")
    return tuple(projections), tuple(notes)


def to_session_targets(projection: T3EnvironmentProjection) -> dict[str, Any]:
    """Render one projection as a Session Bridge ``t3`` target entry.

    ``target_ref`` is ``t3:<environment_id>``, which satisfies the closed
    Session Bridge target-ref grammar and names the environment explicitly.
    """
    if not isinstance(projection, T3EnvironmentProjection):
        _refuse("PROJECTION_INVALID")
    return {
        "kind": TARGET_KIND,
        "target_ref": f"{TARGET_KIND}:{projection.environment_id}",
        "label": f"{projection.environment_id} on {projection.host_id}",
        "host_id": projection.host_id,
        "environment_id": projection.environment_id,
        "capabilities": dict(sorted(dict(projection.capabilities).items())),
        "launch_eligible": projection.launch_eligible,
    }


__all__ = [
    "CAPABILITY_DEGRADED",
    "CAPABILITY_KEYS",
    "CAPABILITY_READY",
    "CAPABILITY_STATES",
    "CAPABILITY_UNKNOWN",
    "DEFAULT_FRESHNESS_WINDOW_S",
    "HOST_SNAPSHOT_SCHEMA",
    "OBSERVATION_SCHEMA",
    "PROJECTION_SCHEMA",
    "REQUIRED_CAPABILITIES",
    "TARGET_KIND",
    "T3EnvironmentObservation",
    "T3EnvironmentProjection",
    "T3ProjectionError",
    "project",
    "project_registry",
    "to_session_targets",
]
