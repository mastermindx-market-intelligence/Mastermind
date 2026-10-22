"""Pure construction core for CF2F worker-capacity observations.

This module converts one validated, secret-free root-owned source identity and
five already-observed readiness facts into the frozen observation consumed by
``executive_capacity_observation``.  It performs no filesystem, broker,
provider, clock, network, persistence, admission, ranking or lifecycle work.
The later host-local broker integration remains responsible for deriving every
input from its accepted owners and for enforcing raw-wire framing.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from control_plane.executive_capacity_observation import (
    OBSERVATION_LIFETIME_MS,
    OBSERVATION_SCHEMA,
    CapacityObservationError,
    WorkerCapacityObservation,
    validate_worker_capacity_observation,
)
from control_plane.executive_host_pressure import HOST_REF_RE

SOURCE_CONFIG_SCHEMA = "mastermind.executive_worker_capacity_source_config/v1"
SOURCE_CONFIG_FIELDS = frozenset(
    {
        "schema_version",
        "host_ref",
        "capacity_capability_id",
        "broker_release_identity_digest",
        "broker_operation_identity_digest",
        "broker_generation",
        "executive_peer_policy_digest",
        "worker_realm_metadata_policy_digest",
        "provider_binary_identity_digest",
    }
)
READINESS_FIELDS = frozenset(
    {
        "realm_metadata_valid",
        "credential_present",
        "credential_metadata_valid",
        "provider_binary_attested",
        "broker_generation_ready",
    }
)
INT64_MAX = (1 << 63) - 1
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_SECONDS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SOURCE_SEAL = object()
_READINESS_SEAL = object()


def _refuse(code: str) -> None:
    raise CapacityObservationError(code)


def _token(value: object) -> str:
    if type(value) is not str or _TOKEN_RE.fullmatch(value) is None:
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    return value


def _digest(value: object) -> str:
    if type(value) is not str or _DIGEST_RE.fullmatch(value) is None:
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    return value


def _host_ref(value: object) -> str:
    if type(value) is not str or (
        value != "local-unbound" and HOST_REF_RE.fullmatch(value) is None
    ):
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    return value


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise CapacityObservationError("CAPACITY_OBSERVE_SCHEMA_INVALID") from None


def _parse_observed_at(value: object) -> tuple[datetime, int]:
    if type(value) is not str or _UTC_SECONDS_RE.fullmatch(value) is None:
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        raise CapacityObservationError("CAPACITY_OBSERVE_SCHEMA_INVALID") from None
    return parsed, int(parsed.timestamp() * 1_000)


@dataclasses.dataclass(frozen=True, slots=True)
class WorkerCapacitySourceConfig:
    schema_version: str
    host_ref: str
    capacity_capability_id: str
    broker_release_identity_digest: str
    broker_operation_identity_digest: str
    broker_generation: int
    executive_peer_policy_digest: str
    worker_realm_metadata_policy_digest: str
    provider_binary_identity_digest: str
    _seal: object = dataclasses.field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self._seal is not _SOURCE_SEAL:
            _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "host_ref": self.host_ref,
            "capacity_capability_id": self.capacity_capability_id,
            "broker_release_identity_digest": self.broker_release_identity_digest,
            "broker_operation_identity_digest": self.broker_operation_identity_digest,
            "broker_generation": self.broker_generation,
            "executive_peer_policy_digest": self.executive_peer_policy_digest,
            "worker_realm_metadata_policy_digest": self.worker_realm_metadata_policy_digest,
            "provider_binary_identity_digest": self.provider_binary_identity_digest,
        }


@dataclasses.dataclass(frozen=True, slots=True)
class WorkerCapacityReadiness:
    realm_metadata_valid: bool
    credential_present: bool
    credential_metadata_valid: bool
    provider_binary_attested: bool
    broker_generation_ready: bool
    _seal: object = dataclasses.field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self._seal is not _READINESS_SEAL:
            _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")

    def to_dict(self) -> dict[str, bool]:
        return {
            "realm_metadata_valid": self.realm_metadata_valid,
            "credential_present": self.credential_present,
            "credential_metadata_valid": self.credential_metadata_valid,
            "provider_binary_attested": self.provider_binary_attested,
            "broker_generation_ready": self.broker_generation_ready,
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


def validate_worker_capacity_source_config(
    value: object,
) -> WorkerCapacitySourceConfig:
    """Validate the exact secret-free root-owned source identity object."""

    if type(value) is not dict or len(value) != len(SOURCE_CONFIG_FIELDS):
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    snapshot = value.copy()
    if set(snapshot) != SOURCE_CONFIG_FIELDS:
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    if snapshot.get("schema_version") != SOURCE_CONFIG_SCHEMA:
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    generation = snapshot.get("broker_generation")
    if type(generation) is not int or not 0 <= generation <= INT64_MAX:
        _refuse("CAPACITY_OBSERVE_CONFIG_DRIFT")
    return WorkerCapacitySourceConfig(
        schema_version=SOURCE_CONFIG_SCHEMA,
        host_ref=_host_ref(snapshot.get("host_ref")),
        capacity_capability_id=_token(snapshot.get("capacity_capability_id")),
        broker_release_identity_digest=_digest(
            snapshot.get("broker_release_identity_digest")
        ),
        broker_operation_identity_digest=_digest(
            snapshot.get("broker_operation_identity_digest")
        ),
        broker_generation=generation,
        executive_peer_policy_digest=_digest(
            snapshot.get("executive_peer_policy_digest")
        ),
        worker_realm_metadata_policy_digest=_digest(
            snapshot.get("worker_realm_metadata_policy_digest")
        ),
        provider_binary_identity_digest=_digest(
            snapshot.get("provider_binary_identity_digest")
        ),
        _seal=_SOURCE_SEAL,
    )


def validate_worker_capacity_readiness(value: object) -> WorkerCapacityReadiness:
    """Validate the fixed five source-owned readiness facts."""

    if type(value) is not dict or len(value) != len(READINESS_FIELDS):
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    snapshot = value.copy()
    if set(snapshot) != READINESS_FIELDS or any(
        type(snapshot[field]) is not bool for field in READINESS_FIELDS
    ):
        _refuse("CAPACITY_OBSERVE_SCHEMA_INVALID")
    return WorkerCapacityReadiness(
        **snapshot,
        _seal=_READINESS_SEAL,
    )


def canonical_worker_capacity_source_config_json(
    value: WorkerCapacitySourceConfig,
) -> bytes:
    """Render one validated source identity with no newline or path material."""

    if not isinstance(value, WorkerCapacitySourceConfig) or value._seal is not _SOURCE_SEAL:
        raise TypeError("value must be a validated WorkerCapacitySourceConfig")
    return _canonical_bytes(value.to_dict())


def worker_capacity_source_config_digest(
    value: WorkerCapacitySourceConfig,
) -> str:
    return hashlib.sha256(canonical_worker_capacity_source_config_json(value)).hexdigest()


def build_worker_capacity_observation(
    *,
    source_config: WorkerCapacitySourceConfig,
    readiness: WorkerCapacityReadiness,
    observed_at: str,
) -> WorkerCapacityObservation:
    """Build one canonical success fact from already-trusted local evidence.

    False readiness never emits an observation. The broker integration must
    derive these inputs from accepted host-local owners; this pure function does
    not turn caller assertions into admission authority.
    """

    if (
        not isinstance(source_config, WorkerCapacitySourceConfig)
        or source_config._seal is not _SOURCE_SEAL
    ):
        raise TypeError("source_config must be validated")
    if (
        not isinstance(readiness, WorkerCapacityReadiness)
        or readiness._seal is not _READINESS_SEAL
    ):
        raise TypeError("readiness must be validated")
    for field, code in _READINESS_REFUSALS:
        if getattr(readiness, field) is not True:
            _refuse(code)

    observed, observed_ms = _parse_observed_at(observed_at)
    try:
        expires_at = (observed + timedelta(milliseconds=OBSERVATION_LIFETIME_MS)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (OverflowError, ValueError):
        raise CapacityObservationError("CAPACITY_OBSERVE_SCHEMA_INVALID") from None

    payload: dict[str, Any] = {
        "schema_version": OBSERVATION_SCHEMA,
        "host_ref": source_config.host_ref,
        "capacity_capability_id": source_config.capacity_capability_id,
        **readiness.to_dict(),
        "source_config_digest": worker_capacity_source_config_digest(source_config),
        "observed_at": observed_at,
        "expires_at": expires_at,
    }
    payload["observation_digest"] = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    return validate_worker_capacity_observation(
        payload,
        expected_host_ref=source_config.host_ref,
        expected_capacity_capability_id=source_config.capacity_capability_id,
        expected_source_config_digest=payload["source_config_digest"],
        trusted_current_ms=observed_ms,
    )


__all__ = [
    "INT64_MAX",
    "READINESS_FIELDS",
    "SOURCE_CONFIG_FIELDS",
    "SOURCE_CONFIG_SCHEMA",
    "WorkerCapacityReadiness",
    "WorkerCapacitySourceConfig",
    "build_worker_capacity_observation",
    "canonical_worker_capacity_source_config_json",
    "validate_worker_capacity_readiness",
    "validate_worker_capacity_source_config",
    "worker_capacity_source_config_digest",
]
