"""Bounded, secret-free Studio Direct read-capability evidence producer.

This module is deliberately not a Studio Direct client. An already-authorized
runtime/operator path performs any live probe and supplies only the reviewed,
versioned observation fields below. The producer converts that receipt into the
existing mastermind.sol_capability_status.v1 projection, attributed to the
existing Studio Direct owner; the broader Fleet/Capacity lineage remains the
placement owner. It opens no shell, file, browser, provider, RuntimeBinding,
fleet, or persistence path itself.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from control_plane.sol_capability_status import (
    CapabilityFact,
    CapabilityState,
    DependencyFact,
    PrivilegeClass,
    project_sol_capability_status,
)

OBSERVATION_SCHEMA = "mastermind.studio_direct_read_evidence.v1"
SOURCE_REF = "studio-direct:read-evidence"
CANONICAL_OWNER = "studio-direct"
APP_ID = "studio-direct"

_RELEVANT_KEYS = frozenset(
    {
        "schema",
        "observed_at",
        "gateway_generation",
        "gateway_version",
        "backend_version",
        "quality",
        "gateway_reachable",
        "file_read_exposed",
        "file_read_proven",
        "terminal_read_probe_exposed",
        "terminal_read_probe_proven",
    }
)
_GENERATION_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,3}(?:[-+][A-Za-z0-9._-]+)?$")
_SECRET_SHAPE = re.compile(
    r"(?:github_pat_|\bgh[pousr]_|\bxox[baprs]-|\bsk-[A-Za-z0-9]|"
    r"bearer\s+|password\s*=|authorization\s*=|-----BEGIN)",
    re.IGNORECASE,
)
_SCHEMA_DIGEST = hashlib.sha256(OBSERVATION_SCHEMA.encode("ascii")).hexdigest()


class StudioDirectEvidenceError(ValueError):
    """The supplied producer receipt is malformed, unsafe, or contradictory."""


class ObservationQuality(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    AMBIGUOUS = "AMBIGUOUS"
    UNAVAILABLE = "UNAVAILABLE"


@dataclasses.dataclass(frozen=True)
class StudioDirectReadObservation:
    schema: str
    observed_at: str
    gateway_generation: str | None
    gateway_version: str | None
    backend_version: str | None
    quality: ObservationQuality
    gateway_reachable: bool | None
    file_read_exposed: bool | None
    file_read_proven: bool
    terminal_read_probe_exposed: bool | None
    terminal_read_probe_proven: bool


def _optional_bool(value: object, field: str) -> bool | None:
    if value is not None and type(value) is not bool:
        raise StudioDirectEvidenceError(f"{field} must be boolean or null")
    return value


def _required_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise StudioDirectEvidenceError(f"{field} must be boolean")
    return value


def _version(value: object, field: str) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or value != value.strip()
        or _VERSION_RE.fullmatch(value) is None
        or _SECRET_SHAPE.search(value)
    ):
        raise StudioDirectEvidenceError(f"{field} is not a safe version token")
    return value


def _generation(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StudioDirectEvidenceError("gateway_generation must be a string or null")
    candidate = value.strip().lower()
    if (
        candidate != value.lower()
        or _GENERATION_RE.fullmatch(candidate) is None
        or _SECRET_SHAPE.search(candidate)
    ):
        raise StudioDirectEvidenceError(
            "gateway_generation must be a secret-free UUID generation"
        )
    return candidate


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or value != value.strip() or not value.endswith("Z"):
        raise StudioDirectEvidenceError("observed_at must be a UTC RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise StudioDirectEvidenceError(
            "observed_at must be a UTC RFC3339 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.astimezone(timezone.utc).utcoffset() is None:
        raise StudioDirectEvidenceError("observed_at must be a UTC RFC3339 timestamp")
    if _SECRET_SHAPE.search(value):
        raise StudioDirectEvidenceError("observed_at contains secret-shaped text")
    return value


def parse_studio_direct_read_observation(
    value: Mapping[str, Any] | object,
) -> StudioDirectReadObservation:
    """Validate one already-acquired, execution-free Studio evidence receipt.

    The closed key set is intentional. There is no representable field for a
    command, path, browser/profile/session locator, credential, provider secret,
    raw tool output, or arbitrary metadata.
    """

    if not isinstance(value, Mapping):
        raise StudioDirectEvidenceError("observation must be an object")
    try:
        raw = dict(value)
    except Exception as exc:
        raise StudioDirectEvidenceError("observation must be a plain mapping") from exc
    if set(raw) != _RELEVANT_KEYS:
        raise StudioDirectEvidenceError("observation has an unsupported field set")
    if raw["schema"] != OBSERVATION_SCHEMA:
        raise StudioDirectEvidenceError("observation schema mismatch")
    observed_at = _timestamp(raw["observed_at"])

    try:
        quality = ObservationQuality(raw["quality"])
    except (TypeError, ValueError) as exc:
        raise StudioDirectEvidenceError("quality is unsupported") from exc

    gateway_generation = _generation(raw["gateway_generation"])
    gateway_reachable = _optional_bool(raw["gateway_reachable"], "gateway_reachable")
    file_read_exposed = _optional_bool(raw["file_read_exposed"], "file_read_exposed")
    file_read_proven = _required_bool(raw["file_read_proven"], "file_read_proven")
    terminal_exposed = _optional_bool(
        raw["terminal_read_probe_exposed"], "terminal_read_probe_exposed"
    )
    terminal_proven = _required_bool(
        raw["terminal_read_probe_proven"], "terminal_read_probe_proven"
    )

    if file_read_proven and file_read_exposed is not True:
        raise StudioDirectEvidenceError(
            "file_read_proven requires file_read_exposed=true"
        )
    if terminal_proven and terminal_exposed is not True:
        raise StudioDirectEvidenceError(
            "terminal_read_probe_proven requires terminal_read_probe_exposed=true"
        )
    if gateway_reachable is False and (file_read_proven or terminal_proven):
        raise StudioDirectEvidenceError(
            "subcapability proof contradicts gateway_reachable=false"
        )
    if (
        gateway_reachable is True or file_read_proven or terminal_proven
    ) and gateway_generation is None:
        raise StudioDirectEvidenceError(
            "live proof requires an exact gateway generation"
        )
    if quality is ObservationQuality.COMPLETE and (
        gateway_reachable is None
        or file_read_exposed is None
        or terminal_exposed is None
    ):
        raise StudioDirectEvidenceError(
            "COMPLETE observation cannot contain unknown capability exposure"
        )
    if quality is ObservationQuality.UNAVAILABLE and (
        gateway_reachable is True or file_read_proven or terminal_proven
    ):
        raise StudioDirectEvidenceError(
            "UNAVAILABLE observation cannot carry live proof"
        )

    return StudioDirectReadObservation(
        OBSERVATION_SCHEMA,
        observed_at,
        gateway_generation,
        _version(raw["gateway_version"], "gateway_version"),
        _version(raw["backend_version"], "backend_version"),
        quality,
        gateway_reachable,
        file_read_exposed,
        file_read_proven,
        terminal_exposed,
        terminal_proven,
    )


def _quality_issues(quality: ObservationQuality) -> tuple[str, ...]:
    if quality is ObservationQuality.PARTIAL:
        return ("OBSERVATION_PARTIAL",)
    if quality is ObservationQuality.AMBIGUOUS:
        return ("OBSERVATION_AMBIGUOUS",)
    if quality is ObservationQuality.UNAVAILABLE:
        return ("SOURCE_UNAVAILABLE",)
    return ()


def _state(*, available: bool | None, proven: bool) -> CapabilityState:
    if proven:
        return CapabilityState.PROVEN_LIVE
    if available is False:
        return CapabilityState.DARK_OR_DISCONNECTED
    return CapabilityState.BUILT_NOT_PROVEN


def _gateway_dependency(receipt: StudioDirectReadObservation) -> DependencyFact:
    """Required owner-native reachability dependency for Studio subcapabilities."""

    available = receipt.gateway_reachable
    return DependencyFact(
        name="studio-direct.gateway",
        state=_state(available=available, proven=available is True),
        required=True,
        available=available,
        source_ref=SOURCE_REF,
        issues=_quality_issues(receipt.quality),
    )


def _fact(
    receipt: StudioDirectReadObservation,
    *,
    name: str,
    required_scope: str,
    available: bool | None,
    proven: bool,
    dependencies: tuple[DependencyFact, ...] = (),
) -> CapabilityFact:
    issues = list(_quality_issues(receipt.quality))
    if available is True and not proven:
        issues.append("LIVE_PROOF_UNOBSERVED")
    if available is None:
        issues.append("CAPABILITY_EXPOSURE_UNKNOWN")
    generation = receipt.gateway_generation or "unknown-generation"
    current_scopes = (required_scope,) if available is not False else ()
    return CapabilityFact(
        name=name,
        app_id=APP_ID,
        app_generation=generation,
        privilege_class=PrivilegeClass.R0_OBSERVE,
        production_armed=False,
        required_scopes=(required_scope,),
        required_write_scopes=(),
        current_scopes=current_scopes,
        confirmation_required=False,
        prepared_action_required=False,
        canonical_owner=CANONICAL_OWNER,
        dependencies=dependencies,
        schema_digest=_SCHEMA_DIGEST,
        source_state=_state(available=available, proven=proven),
        observed_available=available,
        live_proof_current=proven,
        write_capable=False,
        last_proven_at=receipt.observed_at if proven else None,
        source_refs=(SOURCE_REF,),
        issues=tuple(issues),
    )


def project_studio_direct_read_capabilities(
    receipt: StudioDirectReadObservation,
):
    """Project the bounded receipt through the incumbent CAP1 owner."""

    if not isinstance(receipt, StudioDirectReadObservation):
        raise StudioDirectEvidenceError(
            "receipt must be StudioDirectReadObservation"
        )
    gateway_dependency = _gateway_dependency(receipt)
    facts = (
        _fact(
            receipt,
            name="studio_direct_reachability",
            required_scope="studio:read",
            available=receipt.gateway_reachable,
            proven=receipt.gateway_reachable is True,
        ),
        _fact(
            receipt,
            name="studio_direct_file_read",
            required_scope="filesystem:read",
            available=receipt.file_read_exposed,
            proven=receipt.file_read_proven,
            dependencies=(gateway_dependency,),
        ),
        _fact(
            receipt,
            name="studio_direct_terminal_read_probe",
            required_scope="terminal:read_probe",
            available=receipt.terminal_read_probe_exposed,
            proven=receipt.terminal_read_probe_proven,
            dependencies=(gateway_dependency,),
        ),
    )
    generation = receipt.gateway_generation or "unknown"
    return project_sol_capability_status(
        facts,
        observed_at=receipt.observed_at,
        capability_generation=f"studio-direct-{generation}",
    )


__all__ = [
    "APP_ID",
    "CANONICAL_OWNER",
    "OBSERVATION_SCHEMA",
    "ObservationQuality",
    "SOURCE_REF",
    "StudioDirectEvidenceError",
    "StudioDirectReadObservation",
    "parse_studio_direct_read_observation",
    "project_studio_direct_read_capabilities",
]
