"""Pure Control Room to Steward projection for bounded runtime capability evidence.

This adapter owns no observation, RuntimeBinding, fleet state, cache, index,
retry policy, execution authority, or persistence. It accepts the canonical
Chairman Control Room document together with an incumbent
mastermind.sol_capability_status.v1 envelope composed for the same read
snapshot, validates a deliberately narrow Studio Direct capability family, and
returns secret-free research records.

The ordinary six Secretary tools remain unchanged. A research adapter may
consume this projection additively; doing so never authorizes a fresh probe.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import inspect
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from integrations.studio_direct_mcp.read_evidence import (
    APP_ID,
    CANONICAL_OWNER,
    SOURCE_REF,
)

SCHEMA = "mastermind.steward_runtime_capability_evidence.v1"
CONTROL_ROOM_SCHEMA = "mastermind.chairman_control_room.v1"
CAPABILITY_SCHEMA = "mastermind.sol_capability_status.v1"
RUNTIME_CAPABILITY_FIELD = "runtime_capability_status"
DEFAULT_STALE_AFTER_SECONDS = 900
MAX_CONTROL_ROOM_PAIRING_SKEW_SECONDS = 300

_ALLOWED_CAPABILITIES = frozenset(
    {
        "studio_direct_reachability",
        "studio_direct_file_read",
        "studio_direct_terminal_read_probe",
    }
)
_ALLOWED_AVAILABILITY = frozenset(
    {"AVAILABLE", "READ_ONLY", "DEGRADED", "UNAVAILABLE", "UNKNOWN", "REFUSED"}
)
_ALLOWED_PROOF = frozenset(
    {
        "PROVEN_LIVE",
        "BUILT_NOT_PROVEN",
        "PARTIAL",
        "DARK_OR_DISCONNECTED",
        "BROKEN",
        "SPEC_ONLY",
        "NOT_BUILT",
        "REJECTED_BY_DESIGN",
    }
)
_ISSUE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,127}$")
_GENERATION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class RuntimeCapabilityProjectionError(ValueError):
    """The Control Room capability evidence is malformed or unsafe."""


@dataclasses.dataclass(frozen=True)
class RuntimeCapabilityRecord:
    capability_id: str
    capability_generation: str
    app_id: str
    app_generation: str
    canonical_owner: str
    availability: str
    proof_state: str
    read_serviceable: bool
    write_serviceable: bool
    observed_at: str
    last_proven_at: str | None
    freshness: str
    source_refs: tuple[str, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "capability_id": self.capability_id,
            "capability_generation": self.capability_generation,
            "app_id": self.app_id,
            "app_generation": self.app_generation,
            "canonical_owner": self.canonical_owner,
            "availability": self.availability,
            "proof_state": self.proof_state,
            "read_serviceable": self.read_serviceable,
            "write_serviceable": self.write_serviceable,
            "observed_at": self.observed_at,
            "last_proven_at": self.last_proven_at,
            "freshness": self.freshness,
            "source_refs": list(self.source_refs),
            "issues": list(self.issues),
        }


@dataclasses.dataclass(frozen=True)
class RuntimeCapabilityEvidence:
    schema: str
    control_room_schema: str
    control_room_generated_at: str | None
    capability_generation: str | None
    observed_at: str | None
    freshness: str
    records: tuple[RuntimeCapabilityRecord, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "control_room_schema": self.control_room_schema,
            "control_room_generated_at": self.control_room_generated_at,
            "capability_generation": self.capability_generation,
            "observed_at": self.observed_at,
            "freshness": self.freshness,
            "records": [record.to_dict() for record in self.records],
            "issues": list(self.issues),
        }


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RuntimeCapabilityProjectionError(f"{field} must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise RuntimeCapabilityProjectionError(
            f"{field} must be an RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise RuntimeCapabilityProjectionError(
            f"{field} must include a timezone"
        )
    return parsed.astimezone(timezone.utc)


def _freshness(
    observed_at: object,
    *,
    now: datetime,
    stale_after_seconds: int,
) -> tuple[str, tuple[str, ...]]:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise RuntimeCapabilityProjectionError("now must be timezone-aware")
    if type(stale_after_seconds) is not int or stale_after_seconds < 0:
        raise RuntimeCapabilityProjectionError(
            "stale_after_seconds must be a non-negative integer"
        )
    observed = _utc(observed_at, "runtime_capability_status.observed_at")
    age = (now.astimezone(timezone.utc) - observed).total_seconds()
    if age < 0:
        return "UNKNOWN", ("SOURCE_TIME_INVALID",)
    if age > stale_after_seconds:
        return "STALE", ("STALE_SOURCE",)
    return "FRESH", ()


def _safe_generation(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or _GENERATION_RE.fullmatch(value) is None
    ):
        raise RuntimeCapabilityProjectionError(f"{field} is not a safe generation")
    return value


def _issues(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise RuntimeCapabilityProjectionError(f"{field} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or _ISSUE_RE.fullmatch(item) is None:
            raise RuntimeCapabilityProjectionError(f"{field} contains an unsafe issue")
        if item in result:
            raise RuntimeCapabilityProjectionError(f"{field} contains duplicates")
        result.append(item)
    return tuple(sorted(result))


def _validate_cap1_digest(status: Mapping[str, Any]) -> None:
    expected_keys = {
        "schema",
        "capability_generation",
        "observed_at",
        "capabilities",
        "issues",
        "canonical_digest",
    }
    if set(status) != expected_keys:
        raise RuntimeCapabilityProjectionError("CAP1 envelope field set mismatch")
    digest = status.get("canonical_digest")
    if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
        raise RuntimeCapabilityProjectionError("CAP1 canonical_digest is invalid")
    payload = {
        "schema": status["schema"],
        "capability_generation": status["capability_generation"],
        "observed_at": status["observed_at"],
        "capabilities": status["capabilities"],
        "issues": status["issues"],
    }
    try:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise RuntimeCapabilityProjectionError("CAP1 envelope is not canonical JSON") from exc
    if hashlib.sha256(canonical).hexdigest() != digest:
        raise RuntimeCapabilityProjectionError("CAP1 canonical_digest mismatch")


def _row(
    raw: object,
    *,
    capability_generation: str,
    observed_at: str,
    freshness: str,
) -> RuntimeCapabilityRecord | None:
    if not isinstance(raw, Mapping):
        raise RuntimeCapabilityProjectionError("capability rows must be objects")
    name = raw.get("name")
    if not isinstance(name, str):
        raise RuntimeCapabilityProjectionError("capability name must be a string")
    if name not in _ALLOWED_CAPABILITIES:
        if name.startswith("studio_direct_"):
            raise RuntimeCapabilityProjectionError(
                "unreviewed Studio Direct capability is not admitted"
            )
        return None

    app_id = raw.get("app_id")
    owner = raw.get("canonical_owner")
    source_refs = raw.get("source_refs")
    privilege = raw.get("privilege_class")
    if app_id != APP_ID or owner != CANONICAL_OWNER:
        raise RuntimeCapabilityProjectionError("capability owner identity mismatch")
    if privilege != "R0_OBSERVE":
        raise RuntimeCapabilityProjectionError(
            "runtime research capability must remain R0_OBSERVE"
        )
    if not isinstance(source_refs, Sequence) or isinstance(source_refs, (str, bytes)):
        raise RuntimeCapabilityProjectionError("source_refs must be a list")
    if tuple(source_refs) != (SOURCE_REF,):
        raise RuntimeCapabilityProjectionError("runtime capability source_ref mismatch")

    availability = raw.get("availability")
    proof_state = raw.get("proof_state")
    if availability not in _ALLOWED_AVAILABILITY:
        raise RuntimeCapabilityProjectionError("capability availability is unsupported")
    if proof_state not in _ALLOWED_PROOF:
        raise RuntimeCapabilityProjectionError("capability proof_state is unsupported")
    if type(raw.get("read_serviceable")) is not bool:
        raise RuntimeCapabilityProjectionError("read_serviceable must be boolean")
    if raw.get("write_serviceable") is not False:
        raise RuntimeCapabilityProjectionError(
            "runtime research capability may never be write-serviceable"
        )
    if raw.get("production_armed") is not False:
        raise RuntimeCapabilityProjectionError(
            "runtime research capability may never be production-armed"
        )

    app_generation = _safe_generation(
        raw.get("app_generation"), f"{name}.app_generation"
    )
    expected_capability_generation = (
        "studio-direct-unknown"
        if app_generation == "unknown-generation"
        else f"studio-direct-{app_generation}"
    )
    if capability_generation != expected_capability_generation:
        raise RuntimeCapabilityProjectionError(
            "capability generation does not match app generation"
        )
    last_proven = raw.get("last_proven_at")
    if last_proven is not None:
        _utc(last_proven, f"{name}.last_proven_at")
    row_issues = _issues(raw.get("issues"), f"{name}.issues")

    return RuntimeCapabilityRecord(
        capability_id=name,
        capability_generation=capability_generation,
        app_id=APP_ID,
        app_generation=app_generation,
        canonical_owner=CANONICAL_OWNER,
        availability=str(availability),
        proof_state=str(proof_state),
        read_serviceable=bool(raw["read_serviceable"]),
        write_serviceable=False,
        observed_at=observed_at,
        last_proven_at=last_proven,
        freshness=freshness,
        source_refs=(SOURCE_REF,),
        issues=row_issues,
    )


SnapshotProvider = Callable[[], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]
Clock = Callable[[], datetime]


class ControlRoomRuntimeCapabilityReadPort:
    """Read C evidence from one already-composed Control Room snapshot.

    This port never calls Studio Direct, CAP1 producers, a shell, or a runtime
    observer. Missing injected evidence stays UNKNOWN until an existing owner
    supplies a newer accepted Control Room snapshot.
    """

    def __init__(
        self,
        snapshot_provider: SnapshotProvider,
        *,
        clock: Clock,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    ) -> None:
        if not callable(snapshot_provider) or not callable(clock):
            raise TypeError("snapshot_provider and clock are required")
        if type(stale_after_seconds) is not int or stale_after_seconds < 0:
            raise ValueError("stale_after_seconds must be a non-negative integer")
        self._provider = snapshot_provider
        self._clock = clock
        self._stale = stale_after_seconds

    async def read(self) -> RuntimeCapabilityEvidence:
        try:
            value = self._provider()
            if inspect.isawaitable(value):
                value = await value
        except Exception as exc:
            raise RuntimeCapabilityProjectionError(
                "Control Room capability snapshot unavailable"
            ) from exc
        if not isinstance(value, Mapping):
            raise RuntimeCapabilityProjectionError(
                "Control Room capability snapshot must be an object"
            )
        return project_runtime_capability_evidence(
            {
                "control_room": value,
                RUNTIME_CAPABILITY_FIELD: value.get(RUNTIME_CAPABILITY_FIELD),
            },
            now=self._clock(),
            stale_after_seconds=self._stale,
        )


def project_runtime_capability_evidence(
    state: Mapping[str, Any] | object,
    *,
    now: datetime,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
) -> RuntimeCapabilityEvidence:
    """Project one paired Control Room plus CAP1 snapshot for Steward research.

    Missing capability evidence is an explicit UNKNOWN projection. Present but
    malformed or contradictory evidence is refused rather than silently erased.
    """

    if not isinstance(state, Mapping):
        raise RuntimeCapabilityProjectionError("Control Room state must be an object")
    control_room = state.get("control_room")
    if not isinstance(control_room, Mapping):
        raise RuntimeCapabilityProjectionError("control_room must be an object")
    if control_room.get("schema") != CONTROL_ROOM_SCHEMA:
        raise RuntimeCapabilityProjectionError("Control Room schema mismatch")
    control_room_generated_at = control_room.get("generated_at")
    if control_room_generated_at is not None:
        control_room_time = _utc(
            control_room_generated_at, "control_room.generated_at"
        )
    else:
        control_room_time = None

    status = state.get(RUNTIME_CAPABILITY_FIELD)
    if status is None:
        return RuntimeCapabilityEvidence(
            SCHEMA,
            CONTROL_ROOM_SCHEMA,
            control_room_generated_at if isinstance(control_room_generated_at, str) else None,
            None,
            None,
            "UNKNOWN",
            (),
            ("RUNTIME_CAPABILITY_SOURCE_MISSING",),
        )
    if not isinstance(status, Mapping):
        raise RuntimeCapabilityProjectionError(
            "runtime_capability_status must be an object"
        )
    if status.get("schema") != CAPABILITY_SCHEMA:
        raise RuntimeCapabilityProjectionError("CAP1 schema mismatch")
    _validate_cap1_digest(status)

    capability_generation = _safe_generation(
        status.get("capability_generation"), "capability_generation"
    )
    if not capability_generation.startswith("studio-direct-"):
        raise RuntimeCapabilityProjectionError(
            "capability_generation is outside the Studio Direct family"
        )
    observed_at = status.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at.endswith("Z"):
        raise RuntimeCapabilityProjectionError("observed_at must be canonical UTC")
    observed_time = _utc(observed_at, "runtime_capability_status.observed_at")
    freshness, projection_issues = _freshness(
        observed_at,
        now=now,
        stale_after_seconds=stale_after_seconds,
    )
    status_issues = _issues(
        status.get("issues"), "runtime_capability_status.issues"
    )
    projection_issues = tuple(
        sorted(set(projection_issues) | set(status_issues))
    )
    if control_room_time is not None and abs(
        (observed_time - control_room_time).total_seconds()
    ) > MAX_CONTROL_ROOM_PAIRING_SKEW_SECONDS:
        freshness = "UNKNOWN"
        projection_issues = tuple(
            sorted(set(projection_issues) | {"CONTROL_ROOM_EPOCH_MISMATCH"})
        )

    raw_rows = status.get("capabilities")
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        raise RuntimeCapabilityProjectionError("capabilities must be a list")
    seen: set[str] = set()
    records: list[RuntimeCapabilityRecord] = []
    for raw in raw_rows:
        if not isinstance(raw, Mapping):
            raise RuntimeCapabilityProjectionError("capability rows must be objects")
        name = raw.get("name")
        if isinstance(name, str) and name in seen:
            raise RuntimeCapabilityProjectionError("duplicate capability name")
        if isinstance(name, str):
            seen.add(name)
        record = _row(
            raw,
            capability_generation=capability_generation,
            observed_at=observed_at,
            freshness=freshness,
        )
        if record is not None:
            records.append(record)

    if {record.capability_id for record in records} != _ALLOWED_CAPABILITIES:
        raise RuntimeCapabilityProjectionError(
            "Studio Direct capability family is incomplete"
        )
    records.sort(key=lambda item: item.capability_id)
    return RuntimeCapabilityEvidence(
        SCHEMA,
        CONTROL_ROOM_SCHEMA,
        control_room_generated_at if isinstance(control_room_generated_at, str) else None,
        capability_generation,
        observed_at,
        freshness,
        tuple(records),
        tuple(sorted(set(projection_issues))),
    )


__all__ = [
    "CAPABILITY_SCHEMA",
    "CONTROL_ROOM_SCHEMA",
    "DEFAULT_STALE_AFTER_SECONDS",
    "MAX_CONTROL_ROOM_PAIRING_SKEW_SECONDS",
    "RUNTIME_CAPABILITY_FIELD",
    "ControlRoomRuntimeCapabilityReadPort",
    "RuntimeCapabilityEvidence",
    "RuntimeCapabilityProjectionError",
    "RuntimeCapabilityRecord",
    "SCHEMA",
    "project_runtime_capability_evidence",
]
