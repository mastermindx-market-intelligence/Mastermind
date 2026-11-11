"""Pure consumer for the frozen CF2F worker-capacity observation wire.

This module performs no broker call, provider work, clock read, persistence,
admission, ranking, reservation or lifecycle mutation. It validates one already
acquired success object against caller-supplied trusted identity and time facts.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from control_plane.executive_host_pressure import HOST_REF_RE

OBSERVATION_SCHEMA = "mastermind.executive_worker_capacity_observation/v1"
OBSERVATION_LIFETIME_MS = 15_000
CLOCK_SKEW_MS = 2_000
MAX_CANONICAL_BYTES = 4_096
OBSERVATION_FIELDS = frozenset({
    "schema_version", "host_ref", "capacity_capability_id",
    "realm_metadata_valid", "credential_present",
    "credential_metadata_valid", "provider_binary_attested",
    "broker_generation_ready", "source_config_digest", "observed_at",
    "expires_at", "observation_digest",
})
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_SECONDS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_VALIDATED_SEAL = object()


class CapacityObservationError(ValueError):
    """Closed refusal for invalid or unusable capacity evidence."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _refuse(code: str) -> None:
    raise CapacityObservationError(code)


def _token(value: object) -> str:
    if type(value) is not str or _TOKEN_RE.fullmatch(value) is None:
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    return value


def _digest(value: object) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        _refuse("CAPACITY_OBSERVE_DIGEST_INVALID")
    return value


def _host_ref(value: object) -> str:
    if type(value) is not str or (
        value != "local-unbound" and HOST_REF_RE.fullmatch(value) is None
    ):
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    return value


def _parse_utc_ms(value: object) -> int:
    if type(value) is not str or _UTC_SECONDS_RE.fullmatch(value) is None:
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise CapacityObservationError("CAPACITY_OBSERVE_SCHEMA_INVALID") from None
    return int(parsed.timestamp() * 1_000)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    try:
        rendered = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise CapacityObservationError("CAPACITY_OBSERVE_SCHEMA_INVALID") from None
    return rendered


@dataclasses.dataclass(frozen=True, slots=True)
class WorkerCapacityObservation:
    schema_version: str
    host_ref: str
    capacity_capability_id: str
    realm_metadata_valid: bool
    credential_present: bool
    credential_metadata_valid: bool
    provider_binary_attested: bool
    broker_generation_ready: bool
    source_config_digest: str
    observed_at: str
    expires_at: str
    observation_digest: str
    _seal: object = dataclasses.field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self._seal is not _VALIDATED_SEAL:
            raise CapacityObservationError("CAPACITY_OBSERVE_SCHEMA_INVALID")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "host_ref": self.host_ref,
            "capacity_capability_id": self.capacity_capability_id,
            "realm_metadata_valid": self.realm_metadata_valid,
            "credential_present": self.credential_present,
            "credential_metadata_valid": self.credential_metadata_valid,
            "provider_binary_attested": self.provider_binary_attested,
            "broker_generation_ready": self.broker_generation_ready,
            "source_config_digest": self.source_config_digest,
            "observed_at": self.observed_at,
            "expires_at": self.expires_at,
            "observation_digest": self.observation_digest,
        }


_READINESS_REFUSALS = (
    ("realm_metadata_valid", "CAPACITY_OBSERVE_REALM_INVALID"),
    ("credential_present", "CAPACITY_OBSERVE_CREDENTIAL_ABSENT"),
    (
        "credential_metadata_valid",
        "CAPACITY_OBSERVE_CREDENTIAL_METADATA_INVALID",
    ),
    ("provider_binary_attested", "CAPACITY_OBSERVE_BINARY_UNATTESTED"),
    ("broker_generation_ready", "CAPACITY_OBSERVE_GENERATION_UNREADY"),
)


def validate_worker_capacity_observation(
    value: object,
    *,
    expected_host_ref: str,
    expected_capacity_capability_id: str,
    expected_source_config_digest: str,
    trusted_current_ms: int,
) -> WorkerCapacityObservation:
    """Validate one acquired success object against explicit current facts."""

    expected_host = _host_ref(expected_host_ref)
    expected_capability = _token(expected_capacity_capability_id)
    expected_config = _digest(expected_source_config_digest)
    if type(trusted_current_ms) is not int or trusted_current_ms < 0:
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")

    if type(value) is not dict or len(value) != len(OBSERVATION_FIELDS):
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    snapshot = value.copy()
    if set(snapshot) != OBSERVATION_FIELDS:
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    if snapshot.get("schema_version") != OBSERVATION_SCHEMA:
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")

    host_ref = _host_ref(snapshot.get("host_ref"))
    capacity_capability_id = _token(snapshot.get("capacity_capability_id"))
    source_config_digest = _digest(snapshot.get("source_config_digest"))
    observation_digest = _digest(snapshot.get("observation_digest"))
    observed_at = snapshot.get("observed_at")
    expires_at = snapshot.get("expires_at")
    observed_at_ms = _parse_utc_ms(observed_at)
    expires_at_ms = _parse_utc_ms(expires_at)

    for field, _code in _READINESS_REFUSALS:
        if type(snapshot.get(field)) is not bool:
            _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")

    without_digest = {
        key: snapshot[key]
        for key in OBSERVATION_FIELDS
        if key != "observation_digest"
    }
    canonical_without_digest = _canonical_bytes(without_digest)
    actual_digest = hashlib.sha256(canonical_without_digest).hexdigest()
    if observation_digest != actual_digest:
        _refuse("CAPACITY_OBSERVE_DIGEST_INVALID")

    canonical_full = _canonical_bytes(snapshot)
    if len(canonical_full) > MAX_CANONICAL_BYTES:
        _refuse("CAPACITY_OBSERVE_OVERSIZE")

    if (
        host_ref != expected_host
        or capacity_capability_id != expected_capability
        or source_config_digest != expected_config
    ):
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")

    for field, code in _READINESS_REFUSALS:
        if snapshot[field] is not True:
            _refuse(code)

    if expires_at_ms - observed_at_ms != OBSERVATION_LIFETIME_MS:
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    if trusted_current_ms < observed_at_ms - CLOCK_SKEW_MS:
        _refuse("CAPACITY_OBSERVE_FUTURE")
    if trusted_current_ms > expires_at_ms + CLOCK_SKEW_MS:
        _refuse("CAPACITY_OBSERVE_STALE")

    return WorkerCapacityObservation(
        schema_version=OBSERVATION_SCHEMA,
        host_ref=host_ref,
        capacity_capability_id=capacity_capability_id,
        realm_metadata_valid=snapshot["realm_metadata_valid"],
        credential_present=snapshot["credential_present"],
        credential_metadata_valid=snapshot["credential_metadata_valid"],
        provider_binary_attested=snapshot["provider_binary_attested"],
        broker_generation_ready=snapshot["broker_generation_ready"],
        source_config_digest=source_config_digest,
        observed_at=observed_at,
        expires_at=expires_at,
        observation_digest=observation_digest,
        _seal=_VALIDATED_SEAL,
    )


def canonical_worker_capacity_observation_json(
    value: WorkerCapacityObservation,
) -> bytes:
    """Render a previously validated observation as canonical bounded JSON."""

    if (
        not isinstance(value, WorkerCapacityObservation)
        or value._seal is not _VALIDATED_SEAL
    ):
        raise TypeError("value must be a validated WorkerCapacityObservation")
    rendered = _canonical_bytes(value.to_dict())
    if len(rendered) > MAX_CANONICAL_BYTES:
        _refuse("CAPACITY_OBSERVE_OVERSIZE")
    return rendered


__all__ = [
    "CLOCK_SKEW_MS",
    "MAX_CANONICAL_BYTES",
    "OBSERVATION_FIELDS",
    "OBSERVATION_LIFETIME_MS",
    "OBSERVATION_SCHEMA",
    "CapacityObservationError",
    "WorkerCapacityObservation",
    "canonical_worker_capacity_observation_json",
    "validate_worker_capacity_observation",
]
