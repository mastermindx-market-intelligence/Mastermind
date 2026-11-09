"""Pure, nullable activation contract for one Dialogue Wake canary obligation.

This module is deliberately disconnected from configuration, Runtime, Wake routes,
providers and persistence.  It can validate one closed grant and compare it with
trusted current facts.  Matching bytes are evidence of equality only; callers remain
responsible for authenticated provenance and all existing authority/fence checks.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
from enum import Enum
from typing import Any

from control_plane.session_targets import (
    BINDING_ID_RE,
    SESSION_ALIAS_RE,
    WakeRoute,
    route_digest,
)
from control_plane.wake_events import (
    ATTEMPT_ID_RE,
    JOB_ID_RE,
    SEATS,
    WAKE_ID_RE,
    canonical_json_bytes,
)


SCHEMA = "mastermind.dialogue_wake_canary_activation.v1"
MAX_CANONICAL_BYTES = 8 * 1024
# A single scalar cannot lawfully exceed the already accepted whole-grant envelope.
# Existing field-specific regexes retain their tighter identity-contract limits.
MAX_IDENTITY_TEXT_BYTES = MAX_CANONICAL_BYTES
# RuntimeBinding generations are persisted in SQLite INTEGER columns.
MAX_BINDING_GENERATION = (1 << 63) - 1
MAX_VALIDITY_SECONDS = 15 * 60
MAX_EPOCH_SECONDS = 4_102_444_800  # 2100-01-01T00:00:00Z
MAX_CONTAINER_DEPTH = 1  # one flat object; every child is a scalar

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_POLICY_DIGEST_RE = re.compile(r"^[0-9a-f]{16}$")
_OPERATION_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PROCESS_GENERATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

IDENTITY_FIELDS = (
    "installed_release_sha",
    "operation_key",
    "source_root_job_id",
    "source_job_id",
    "source_attempt_id",
    "source_worker_id",
    "source_semantic_digest",
    "obligation_id",
    "target_seat",
    "target_session_alias",
    "target_attempt_id",
    "binding_id",
    "binding_generation",
    "process_generation_id",
    "policy_digest",
)
GRANT_FIELDS = ("schema", *IDENTITY_FIELDS, "valid_from_epoch_seconds", "expires_at_epoch_seconds")
GRANT_KEYS = frozenset(GRANT_FIELDS)
MAX_NODE_COUNT = 1 + len(GRANT_FIELDS)  # the object plus its fixed scalar leaves


class ActivationRefusalCode(str, Enum):
    MALFORMED = "MALFORMED"
    NOT_YET_VALID = "NOT_YET_VALID"
    EXPIRED = "EXPIRED"
    CURRENT_FACT_MISMATCH = "CURRENT_FACT_MISMATCH"


class DialogueWakeCanaryActivationError(ValueError):
    """Typed refusal; no route, authority or effect was produced."""

    def __init__(
        self,
        code: ActivationRefusalCode,
        reason: str,
        *,
        field: str | None = None,
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.field = field


def _refuse(reason: str, *, field: str | None = None) -> None:
    raise DialogueWakeCanaryActivationError(
        ActivationRefusalCode.MALFORMED,
        reason,
        field=field,
    )


def _text(value: Any, *, field: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str:
        _refuse(f"{field} is malformed", field=field)
    if len(value) > MAX_IDENTITY_TEXT_BYTES:
        _refuse(f"{field} is malformed", field=field)
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        _refuse(f"{field} is malformed", field=field)
    if len(encoded) > MAX_IDENTITY_TEXT_BYTES or pattern.fullmatch(value) is None:
        _refuse(f"{field} is malformed", field=field)
    return value


def _positive_int(value: Any, *, field: str) -> int:
    if type(value) is not int or not (1 <= value <= MAX_BINDING_GENERATION):
        _refuse(f"{field} is outside the supported positive integer range", field=field)
    return value


def _epoch(value: Any, *, field: str) -> int:
    if type(value) is not int or not (0 <= value <= MAX_EPOCH_SECONDS):
        _refuse(f"{field} is outside the supported epoch range", field=field)
    return value


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    """Serialize closed validated data, translating codec failures to one opaque refusal."""

    try:
        encoded = canonical_json_bytes(value)
    except (TypeError, ValueError, OverflowError, UnicodeError):
        _refuse("canary identity cannot be serialized canonically")
    if len(encoded) > MAX_CANONICAL_BYTES:
        _refuse("canary identity exceeds canonical byte limit")
    return encoded


def _validate_identity_values(values: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "installed_release_sha": _text(
            values["installed_release_sha"], field="installed_release_sha", pattern=_GIT_SHA_RE
        ),
        "operation_key": _text(
            values["operation_key"], field="operation_key", pattern=_OPERATION_KEY_RE
        ),
        "source_root_job_id": _text(
            values["source_root_job_id"], field="source_root_job_id", pattern=JOB_ID_RE
        ),
        "source_job_id": _text(values["source_job_id"], field="source_job_id", pattern=JOB_ID_RE),
        "source_attempt_id": _text(
            values["source_attempt_id"], field="source_attempt_id", pattern=ATTEMPT_ID_RE
        ),
        "source_worker_id": _text(
            values["source_worker_id"], field="source_worker_id", pattern=_WORKER_ID_RE
        ),
        "source_semantic_digest": _text(
            values["source_semantic_digest"],
            field="source_semantic_digest",
            pattern=_DIGEST_RE,
        ),
        "obligation_id": _text(
            values["obligation_id"], field="obligation_id", pattern=WAKE_ID_RE
        ),
        "target_seat": values["target_seat"],
        "target_session_alias": _text(
            values["target_session_alias"],
            field="target_session_alias",
            pattern=SESSION_ALIAS_RE,
        ),
        "target_attempt_id": _text(
            values["target_attempt_id"], field="target_attempt_id", pattern=ATTEMPT_ID_RE
        ),
        "binding_id": _text(values["binding_id"], field="binding_id", pattern=BINDING_ID_RE),
        "binding_generation": _positive_int(
            values["binding_generation"], field="binding_generation"
        ),
        "process_generation_id": _text(
            values["process_generation_id"],
            field="process_generation_id",
            pattern=_PROCESS_GENERATION_ID_RE,
        ),
        "policy_digest": _text(
            values["policy_digest"], field="policy_digest", pattern=_POLICY_DIGEST_RE
        ),
    }
    if type(normalized["target_seat"]) is not str or normalized["target_seat"] not in SEATS:
        _refuse("target_seat is unknown", field="target_seat")
    return normalized


@dataclasses.dataclass(frozen=True)
class DialogueWakeCanaryCurrentFacts:
    """Authenticated current owner facts supplied by later Runtime composition."""

    installed_release_sha: str
    operation_key: str
    source_root_job_id: str
    source_job_id: str
    source_attempt_id: str
    source_worker_id: str
    source_semantic_digest: str
    obligation_id: str
    target_seat: str
    target_session_alias: str
    target_attempt_id: str
    binding_id: str
    binding_generation: int
    process_generation_id: str
    policy_digest: str

    def __post_init__(self) -> None:
        normalized = _validate_identity_values(
            {field: getattr(self, field) for field in IDENTITY_FIELDS}
        )
        for field, value in normalized.items():
            object.__setattr__(self, field, value)
        _canonical_bytes(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in IDENTITY_FIELDS}


@dataclasses.dataclass(frozen=True)
class DialogueWakeCanaryActivationGrant:
    """One immutable, bounded and non-self-authenticating canary grant."""

    schema: str
    installed_release_sha: str
    operation_key: str
    source_root_job_id: str
    source_job_id: str
    source_attempt_id: str
    source_worker_id: str
    source_semantic_digest: str
    obligation_id: str
    target_seat: str
    target_session_alias: str
    target_attempt_id: str
    binding_id: str
    binding_generation: int
    process_generation_id: str
    policy_digest: str
    valid_from_epoch_seconds: int
    expires_at_epoch_seconds: int

    def __post_init__(self) -> None:
        if type(self.schema) is not str or self.schema != SCHEMA:
            _refuse("schema is unknown", field="schema")
        normalized = _validate_identity_values(
            {field: getattr(self, field) for field in IDENTITY_FIELDS}
        )
        for field, value in normalized.items():
            object.__setattr__(self, field, value)
        start = _epoch(self.valid_from_epoch_seconds, field="valid_from_epoch_seconds")
        expiry = _epoch(self.expires_at_epoch_seconds, field="expires_at_epoch_seconds")
        if expiry <= start:
            _refuse("validity interval must be positive", field="expires_at_epoch_seconds")
        if expiry - start > MAX_VALIDITY_SECONDS:
            _refuse(
                f"validity interval exceeds {MAX_VALIDITY_SECONDS} seconds",
                field="expires_at_epoch_seconds",
            )
        _canonical_bytes(self.to_dict())

    @classmethod
    def from_dict(cls, value: Any) -> "DialogueWakeCanaryActivationGrant":
        if type(value) is not dict:
            _refuse("activation grant must be a plain object")
        if len(value) > len(GRANT_FIELDS):
            _refuse("activation grant exceeds the closed field/node limit")
        for key in value:
            if type(key) is not str:
                _refuse("activation grant keys must be strings")
            if len(key) > MAX_IDENTITY_TEXT_BYTES:
                _refuse("activation grant key is malformed")
            try:
                key.encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                _refuse("activation grant key is malformed")
        actual = frozenset(value)
        if actual != GRANT_KEYS:
            _refuse("activation grant fields drifted")
        return cls(**{field: value[field] for field in GRANT_FIELDS})

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in GRANT_FIELDS}

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical_bytes(self.to_dict())).hexdigest()


@dataclasses.dataclass(frozen=True)
class DialogueWakeCanaryActivationMatch:
    """Exact equality receipt only; it is not an authorization or WakeRoute."""

    grant: DialogueWakeCanaryActivationGrant
    grant_digest: str


@dataclasses.dataclass(frozen=True)
class DialogueWakeCanaryProfile:
    """Trusted composition marker for the one canary lane.

    The profile is deliberately present even when the nullable grant is absent,
    so removal of the grant cannot silently select generic carrier behavior.
    """

    grant: DialogueWakeCanaryActivationGrant | None

    def __post_init__(self) -> None:
        if (
            self.grant is not None
            and type(self.grant) is not DialogueWakeCanaryActivationGrant
        ):
            _refuse("canary profile grant must be parsed")


def effective_dialogue_wake_canary_route(
    profile: DialogueWakeCanaryProfile,
    base_route: WakeRoute,
) -> WakeRoute:
    """Derive the sole armed route from a trusted disarmed base route and grant."""

    if type(profile) is not DialogueWakeCanaryProfile or not isinstance(
        base_route, WakeRoute
    ):
        _refuse("canary route inputs are malformed")
    grant = profile.grant
    if grant is None:
        _refuse("canary activation grant is unavailable")
    if base_route.production_armed or base_route.target_enabled:
        _refuse("canary base route must remain explicitly disarmed")
    expected = {
        "obligation_id": grant.obligation_id,
        "session_alias": grant.target_session_alias,
        "target_seat": grant.target_seat,
        "binding_id": grant.binding_id,
        "binding_generation": grant.binding_generation,
        "policy_digest": grant.policy_digest,
    }
    for field, value in expected.items():
        if getattr(base_route, field) != value:
            raise DialogueWakeCanaryActivationError(
                ActivationRefusalCode.CURRENT_FACT_MISMATCH,
                f"canary base route does not match {field}",
                field=field,
            )
    effective_policy = hashlib.sha256(
        _canonical_bytes(
            {
                "base_policy_digest": base_route.policy_digest,
                "grant_digest": grant.digest,
            }
        )
    ).hexdigest()[:16]
    return dataclasses.replace(
        base_route,
        production_armed=True,
        target_enabled=True,
        policy_digest=effective_policy,
        route_digest=route_digest(
            obligation_id=base_route.obligation_id,
            destination=base_route.destination_digest,
            policy_digest=effective_policy,
        ),
    )


def parse_dialogue_wake_canary_activation(
    value: Any | None,
) -> DialogueWakeCanaryActivationGrant | None:
    """Parse the nullable config value.  ``None`` means deterministically disarmed."""

    if value is None:
        return None
    return DialogueWakeCanaryActivationGrant.from_dict(value)


def match_dialogue_wake_canary_activation(
    grant: DialogueWakeCanaryActivationGrant | None,
    current: DialogueWakeCanaryCurrentFacts,
    *,
    now_epoch_seconds: int,
) -> DialogueWakeCanaryActivationMatch | None:
    """Return exact-match data or a typed refusal without performing any effect."""

    if grant is None:
        return None
    if type(grant) is not DialogueWakeCanaryActivationGrant:
        _refuse("activation grant must be parsed before matching")
    if type(current) is not DialogueWakeCanaryCurrentFacts:
        _refuse("current facts must be trusted typed facts")
    now = _epoch(now_epoch_seconds, field="now_epoch_seconds")
    if now < grant.valid_from_epoch_seconds:
        raise DialogueWakeCanaryActivationError(
            ActivationRefusalCode.NOT_YET_VALID,
            "activation grant is not yet valid",
        )
    if now >= grant.expires_at_epoch_seconds:
        raise DialogueWakeCanaryActivationError(
            ActivationRefusalCode.EXPIRED,
            "activation grant has expired",
        )
    for field in IDENTITY_FIELDS:
        if getattr(grant, field) != getattr(current, field):
            raise DialogueWakeCanaryActivationError(
                ActivationRefusalCode.CURRENT_FACT_MISMATCH,
                f"activation grant does not match current {field}",
                field=field,
            )
    return DialogueWakeCanaryActivationMatch(grant=grant, grant_digest=grant.digest)


__all__ = [
    "ActivationRefusalCode",
    "DialogueWakeCanaryActivationError",
    "DialogueWakeCanaryActivationGrant",
    "DialogueWakeCanaryActivationMatch",
    "DialogueWakeCanaryCurrentFacts",
    "DialogueWakeCanaryProfile",
    "GRANT_FIELDS",
    "IDENTITY_FIELDS",
    "MAX_CANONICAL_BYTES",
    "MAX_BINDING_GENERATION",
    "MAX_CONTAINER_DEPTH",
    "MAX_EPOCH_SECONDS",
    "MAX_IDENTITY_TEXT_BYTES",
    "MAX_NODE_COUNT",
    "MAX_VALIDITY_SECONDS",
    "SCHEMA",
    "match_dialogue_wake_canary_activation",
    "effective_dialogue_wake_canary_route",
    "parse_dialogue_wake_canary_activation",
]
