"""Immutable Job-bound login-check request/binding primitives.

This module owns only the strict, model-free external request contract, the
logical family key and its ``pvrf-`` family aggregate ID, and the complete
first-admission binding and its ``pvr-`` operation/broker request ID for one
Executive Job/Attempt's login-status observation
(``executive.worker_auth.verify_only``). It performs no Runtime/Event
mutation, no broker call, no service composition, and no host effect: it is
the deterministic identifier/serialization contract that a later controller
substep composes with Runtime authority and the shared broker client.

Every observation this contract can name carries the fixed
``observation_scope`` below and proves at most a login-status check; it never
asserts a ready-to-work claim for any worker slot.
"""
from __future__ import annotations

import dataclasses
import enum
import hashlib
import json
import re
from typing import Any, Mapping


REQUEST_KEYS = frozenset({"job_id", "attempt_id", "fence_generation"})

FIXED_ACTION = "executive.worker_auth.verify_only"
OBSERVATION_SCOPE = "LOGIN_STATUS_ONLY_NO_READY_ASSERTION"

FAMILY_KEY_SCHEMA = "mastermind.executive_privileged_readiness_family_key/v1"
BINDING_SCHEMA = "mastermind.executive_privileged_readiness_binding/v1"
RESULT_SCHEMA = "mastermind.executive_privileged_readiness_result/v1"

READINESS_AGGREGATE_TYPE = "privileged_readiness"

# The merged PR #613 broker emits exactly four wire error codes. Three of them
# are pre-effect refusals; EFFECT_UNKNOWN names an unresolved effect and must
# never be projected as a refusal. This set reuses that merged domain rather
# than forking a second reason vocabulary.
BROKER_REFUSAL_REASON_CODES = frozenset(
    {"PEER_UNAUTHORIZED", "REQUEST_ID_CONFLICT", "REFUSED"}
)
BROKER_EFFECT_UNKNOWN_ERROR = "EFFECT_UNKNOWN"

REASON_ORIGIN_BROKER = "BROKER"

RESULT_CANONICAL_KEYS = frozenset(
    {
        "schema_version",
        "family_id",
        "operation_id",
        "state",
        "replayed",
        "observed_at_ms",
        "evidence_currency",
        "observation_scope",
        "binding",
        "receipt",
        "reason_origin",
        "reason_code",
    }
)

FAMILY_ID_PREFIX = "pvrf-"
OPERATION_ID_PREFIX = "pvr-"
_ID_HEX_LENGTH = 48

_JOB_ID_RE = re.compile(r"^JOB-(?:(?!000$)[0-9]{3}|[1-9][0-9]{3,17})$")
_ATTEMPT_ID_RE = re.compile(r"^ATT-[0-9a-f]{32}$")
_SAFE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_BOOT_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_FAMILY_ID_RE = re.compile(r"^pvrf-[0-9a-f]{48}$")
_OPERATION_ID_RE = re.compile(r"^pvr-[0-9a-f]{48}$")
_ADAPTER_FALLBACK_RE = re.compile(r"^adapter-[0-9]+$")
_NIL_BOOT_UUID = "00000000-0000-0000-0000-000000000000"

BINDING_CANONICAL_KEYS = frozenset(
    {
        "schema_version",
        "action",
        "job_id",
        "attempt_id",
        "worker_id",
        "quota_class",
        "fence_generation",
        "authority_policy_hash",
        "effective_grant_digest",
        "release_sha",
        "boot_id",
        "slot_id",
    }
)


class PrivilegedReadinessError(ValueError):
    """The readiness request/binding is outside the reviewed contract."""


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Sorted-key, compact, UTF-8 canonical JSON with no NaN/Infinity."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _require_exact_keys(mapping: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    observed = frozenset(mapping)
    if observed != expected:
        raise PrivilegedReadinessError(
            f"{label} keys must be exactly {sorted(expected)}; got {sorted(observed)}"
        )


def _require_pattern(value: Any, field: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise PrivilegedReadinessError(f"{field} is not a bounded safe identifier")
    return value


def validate_job_id(value: Any) -> str:
    return _require_pattern(value, "job_id", _JOB_ID_RE)


def validate_attempt_id(value: Any) -> str:
    return _require_pattern(value, "attempt_id", _ATTEMPT_ID_RE)


def validate_safe_id(value: Any, field: str) -> str:
    return _require_pattern(value, field, _SAFE_ID_RE)


def validate_fence_generation(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PrivilegedReadinessError("fence_generation must be a JSON integer")
    if value <= 0:
        raise PrivilegedReadinessError("fence_generation must be a positive integer")
    return value


def validate_release_sha(value: Any) -> str:
    if not isinstance(value, str) or _RELEASE_SHA_RE.fullmatch(value) is None:
        raise PrivilegedReadinessError("release_sha must be lowercase 40-hex")
    return value


def validate_sha256_hex(value: Any, field: str) -> str:
    if not isinstance(value, str) or _SHA256_HEX_RE.fullmatch(value) is None:
        raise PrivilegedReadinessError(f"{field} must be lowercase 64-hex")
    return value


def validate_effective_grant_digest(value: Any) -> str | None:
    if value is None:
        return None
    return validate_sha256_hex(value, "effective_grant_digest")


def validate_boot_id(value: Any) -> str:
    """Validate a real kernel boot-session UUID; reject the adapter-<pid> fallback.

    UUID case is representation, not identity: the real macOS kernel returns
    uppercase text, so both spellings are accepted and normalized to the same
    lowercase canonical string, ensuring one boot session hashes to one ID.
    """

    if not isinstance(value, str) or not value:
        raise PrivilegedReadinessError("boot_id is not a real kernel boot-session identity")
    if _ADAPTER_FALLBACK_RE.fullmatch(value) is not None:
        raise PrivilegedReadinessError("boot_id cannot be a process-local adapter fallback")
    if _BOOT_UUID_RE.fullmatch(value) is None:
        raise PrivilegedReadinessError("boot_id must be a canonical kernel boot-session UUID")
    canonical = value.lower()
    if canonical == _NIL_BOOT_UUID:
        raise PrivilegedReadinessError("boot_id cannot be the nil UUID")
    return canonical


@dataclasses.dataclass(frozen=True)
class ReadinessRequest:
    """One strict external login-check request; exactly three caller fields."""

    job_id: str
    attempt_id: str
    fence_generation: int

    def __post_init__(self) -> None:
        validate_job_id(self.job_id)
        validate_attempt_id(self.attempt_id)
        validate_fence_generation(self.fence_generation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "fence_generation": self.fence_generation,
        }


def validate_readiness_request(raw: Any) -> ReadinessRequest:
    if not isinstance(raw, Mapping):
        raise PrivilegedReadinessError("readiness request must be a mapping")
    _require_exact_keys(raw, REQUEST_KEYS, "readiness request")
    return ReadinessRequest(
        job_id=raw["job_id"],
        attempt_id=raw["attempt_id"],
        fence_generation=raw["fence_generation"],
    )


@dataclasses.dataclass(frozen=True)
class ReadinessFamilyKey:
    """The logical effect key ``(job_id, attempt_id, fence_generation, action)``."""

    job_id: str
    attempt_id: str
    fence_generation: int
    action: str = FIXED_ACTION

    def __post_init__(self) -> None:
        validate_job_id(self.job_id)
        validate_attempt_id(self.attempt_id)
        validate_fence_generation(self.fence_generation)
        if self.action != FIXED_ACTION:
            raise PrivilegedReadinessError("family key action must be the fixed verify_only action")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FAMILY_KEY_SCHEMA,
            "action": self.action,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "fence_generation": self.fence_generation,
        }

    @property
    def family_id(self) -> str:
        digest = hashlib.sha256(canonical_json_bytes(self.to_canonical_dict())).hexdigest()
        return f"{FAMILY_ID_PREFIX}{digest[:_ID_HEX_LENGTH]}"


def family_key_from_request(request: ReadinessRequest) -> ReadinessFamilyKey:
    return ReadinessFamilyKey(
        job_id=request.job_id,
        attempt_id=request.attempt_id,
        fence_generation=request.fence_generation,
    )


@dataclasses.dataclass(frozen=True)
class ReadinessBinding:
    """The complete first-admission binding; source of the ``pvr-...`` operation ID."""

    job_id: str
    attempt_id: str
    worker_id: str
    quota_class: str
    fence_generation: int
    authority_policy_hash: str
    effective_grant_digest: str | None
    release_sha: str
    boot_id: str
    slot_id: str
    schema_version: str = BINDING_SCHEMA
    action: str = FIXED_ACTION

    def __post_init__(self) -> None:
        validate_job_id(self.job_id)
        validate_attempt_id(self.attempt_id)
        validate_safe_id(self.worker_id, "worker_id")
        validate_safe_id(self.quota_class, "quota_class")
        validate_fence_generation(self.fence_generation)
        validate_sha256_hex(self.authority_policy_hash, "authority_policy_hash")
        validate_effective_grant_digest(self.effective_grant_digest)
        validate_release_sha(self.release_sha)
        canonical_boot_id = validate_boot_id(self.boot_id)
        if canonical_boot_id != self.boot_id:
            object.__setattr__(self, "boot_id", canonical_boot_id)
        validate_safe_id(self.slot_id, "slot_id")
        if self.schema_version != BINDING_SCHEMA:
            raise PrivilegedReadinessError("binding schema_version is not the reviewed binding schema")
        if self.action != FIXED_ACTION:
            raise PrivilegedReadinessError("binding action must be the fixed verify_only action")
        if self.slot_id != self.worker_id:
            raise PrivilegedReadinessError("binding slot_id must equal worker_id")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "quota_class": self.quota_class,
            "fence_generation": self.fence_generation,
            "authority_policy_hash": self.authority_policy_hash,
            "effective_grant_digest": self.effective_grant_digest,
            "release_sha": self.release_sha,
            "boot_id": self.boot_id,
            "slot_id": self.slot_id,
        }

    @property
    def operation_id(self) -> str:
        digest = hashlib.sha256(canonical_json_bytes(self.to_canonical_dict())).hexdigest()
        return f"{OPERATION_ID_PREFIX}{digest[:_ID_HEX_LENGTH]}"


class ReadinessResultState(str, enum.Enum):
    """The closed login-check result domain.

    There is deliberately no ready-to-work member: the fixed
    ``observation_scope`` below bounds every member to point-in-time
    login-status evidence.
    """

    TERMINAL = "TERMINAL"
    REFUSED = "REFUSED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"


class ReadinessEvidenceCurrency(str, enum.Enum):
    """How current the binding's release/boot/policy facts are at return time.

    This bounds only fact freshness. Neither member asserts a worker is
    usable, that a credential is valid, or that a provider account resolved.
    """

    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"


class ReadinessEventPhase(str, enum.Enum):
    """The closed set of durable ``events`` rows one operation family may hold."""

    INTENT = "PRIVILEGED_READINESS_INTENT"
    ATTEMPTED = "PRIVILEGED_READINESS_ATTEMPTED"
    TERMINAL = "PRIVILEGED_READINESS_TERMINAL"
    BROKER_REFUSED = "PRIVILEGED_READINESS_BROKER_REFUSED"
    EFFECT_UNKNOWN = "PRIVILEGED_READINESS_EFFECT_UNKNOWN"
    RECONCILED = "PRIVILEGED_READINESS_RECONCILED"


def result_state_for_broker_error(code: Any) -> ReadinessResultState:
    """Map one merged-broker wire error code onto the closed result domain.

    ``EFFECT_UNKNOWN`` is an unresolved effect, never a refusal, so it must not
    collapse into ``REFUSED``. An unrecognised code fails closed instead of
    defaulting, so a future broker code cannot silently become a refusal.
    """

    if not isinstance(code, str):
        raise PrivilegedReadinessError("broker error code is not a string")
    if code == BROKER_EFFECT_UNKNOWN_ERROR:
        return ReadinessResultState.EFFECT_UNKNOWN
    if code in BROKER_REFUSAL_REASON_CODES:
        return ReadinessResultState.REFUSED
    raise PrivilegedReadinessError(f"broker error code {code!r} is outside the reviewed domain")


def evidence_currency_for(
    binding: "ReadinessBinding",
    *,
    current_boot_id: Any,
    current_release_sha: Any,
    current_authority_policy_hash: Any,
) -> ReadinessEvidenceCurrency:
    """Compare a stored binding against freshly observed host facts.

    ``CURRENT`` requires exact equality on all three facts. Any mismatch, any
    unprovable fact (``None``), and any malformed observation yields
    ``HISTORICAL``. Boot-session UUID case is representation, not identity, so
    both spellings canonicalize before comparison.
    """

    if not isinstance(binding, ReadinessBinding):
        raise PrivilegedReadinessError("evidence currency requires a validated binding")
    try:
        observed_boot_id = validate_boot_id(current_boot_id)
        observed_release_sha = validate_release_sha(current_release_sha)
        observed_policy_hash = validate_sha256_hex(
            current_authority_policy_hash, "current_authority_policy_hash"
        )
    except PrivilegedReadinessError:
        return ReadinessEvidenceCurrency.HISTORICAL
    if (
        observed_boot_id == binding.boot_id
        and observed_release_sha == binding.release_sha
        and observed_policy_hash == binding.authority_policy_hash
    ):
        return ReadinessEvidenceCurrency.CURRENT
    return ReadinessEvidenceCurrency.HISTORICAL


@dataclasses.dataclass(frozen=True)
class ReadinessResult:
    """One secret-free login-check result projection.

    State/receipt/reason coherence is enforced at construction so a consumer
    can never read a success receipt off a refusal or an unresolved effect.
    """

    family_id: str
    operation_id: str
    state: ReadinessResultState
    replayed: bool
    observed_at_ms: int
    evidence_currency: ReadinessEvidenceCurrency
    binding: "ReadinessBinding"
    receipt: Mapping[str, Any] | None = None
    reason_origin: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        _require_pattern(self.family_id, "family_id", _FAMILY_ID_RE)
        _require_pattern(self.operation_id, "operation_id", _OPERATION_ID_RE)
        if not isinstance(self.state, ReadinessResultState):
            raise PrivilegedReadinessError("state is outside the closed result domain")
        if not isinstance(self.evidence_currency, ReadinessEvidenceCurrency):
            raise PrivilegedReadinessError("evidence_currency is outside the closed domain")
        if type(self.replayed) is not bool:
            raise PrivilegedReadinessError("replayed must be a real boolean")
        if type(self.observed_at_ms) is not int or self.observed_at_ms <= 0:
            raise PrivilegedReadinessError("observed_at_ms must be a positive integer")
        if not isinstance(self.binding, ReadinessBinding):
            raise PrivilegedReadinessError("binding must be a validated ReadinessBinding")
        if self.state is ReadinessResultState.TERMINAL:
            if not isinstance(self.receipt, Mapping):
                raise PrivilegedReadinessError("a terminal result requires a validated receipt")
            if self.reason_origin is not None or self.reason_code is not None:
                raise PrivilegedReadinessError("a terminal result carries no refusal reason")
        elif self.state is ReadinessResultState.REFUSED:
            if self.receipt is not None:
                raise PrivilegedReadinessError("a refusal carries no receipt")
            if self.reason_origin != REASON_ORIGIN_BROKER:
                raise PrivilegedReadinessError("a refusal reason must originate at the broker")
            if self.reason_code not in BROKER_REFUSAL_REASON_CODES:
                raise PrivilegedReadinessError("refusal reason_code is outside the broker domain")
        else:
            if self.receipt is not None:
                raise PrivilegedReadinessError("an unresolved effect carries no receipt")
            if self.reason_origin is not None or self.reason_code is not None:
                raise PrivilegedReadinessError("an unresolved effect carries no refusal reason")

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_SCHEMA,
            "family_id": self.family_id,
            "operation_id": self.operation_id,
            "state": self.state.value,
            "replayed": self.replayed,
            "observed_at_ms": self.observed_at_ms,
            "evidence_currency": self.evidence_currency.value,
            "observation_scope": OBSERVATION_SCOPE,
            "binding": self.binding.to_canonical_dict(),
            "receipt": dict(self.receipt) if self.receipt is not None else None,
            "reason_origin": self.reason_origin,
            "reason_code": self.reason_code,
        }


__all__ = [
    "BROKER_EFFECT_UNKNOWN_ERROR",
    "BROKER_REFUSAL_REASON_CODES",
    "REASON_ORIGIN_BROKER",
    "READINESS_AGGREGATE_TYPE",
    "RESULT_CANONICAL_KEYS",
    "ReadinessEventPhase",
    "ReadinessEvidenceCurrency",
    "ReadinessResult",
    "ReadinessResultState",
    "evidence_currency_for",
    "result_state_for_broker_error",
    "BINDING_CANONICAL_KEYS",
    "BINDING_SCHEMA",
    "FAMILY_ID_PREFIX",
    "FAMILY_KEY_SCHEMA",
    "FIXED_ACTION",
    "OBSERVATION_SCOPE",
    "OPERATION_ID_PREFIX",
    "REQUEST_KEYS",
    "RESULT_SCHEMA",
    "PrivilegedReadinessError",
    "ReadinessBinding",
    "ReadinessFamilyKey",
    "ReadinessRequest",
    "canonical_json_bytes",
    "family_key_from_request",
    "validate_attempt_id",
    "validate_boot_id",
    "validate_effective_grant_digest",
    "validate_fence_generation",
    "validate_job_id",
    "validate_readiness_request",
    "validate_release_sha",
    "validate_safe_id",
    "validate_sha256_hex",
]
