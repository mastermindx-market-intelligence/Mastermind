"""Pure SCF-OPS2 contract for one exact service restart.

This module owns no service lifecycle and performs no I/O. Exact service owners
remain authoritative for observation and restart effects.
"""
from __future__ import annotations

import dataclasses
import re
from enum import Enum

SCHEMA = "mastermind.sol_ops_restart.v1"
ALLOWED_SERVICES = frozenset(
    {
        "studio-direct.chatgpt1",
        "studio-direct.chatgpt2-personal",
        "studio-direct.chatgpt2-business",
        "studio-direct.chatgpt3-w570f6f34",
        "studio-direct.chatgpt3-wa2a9e6f9",
        "studio-direct.chatgpt4",
    }
)
ALLOWED_REASONS = frozenset(
    {"health_recovery", "operator_recovery", "release_canary"}
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$")


class RestartState(str, Enum):
    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    EFFECT_UNKNOWN = "EFFECT_UNKNOWN"


@dataclasses.dataclass(frozen=True)
class RestartObservation:
    service_ref: str
    instance_identity: str
    build_identity: str
    ready: bool
    runtime_version: str | None
    issues: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class RestartRequest:
    service_ref: str
    expected_instance_identity: str
    expected_build_identity: str
    reason_code: str


@dataclasses.dataclass(frozen=True)
class RestartResult:
    state: RestartState
    code: str
    service_ref: str
    instance_identity: str | None
    build_identity: str | None
    ready: bool | None
    runtime_version: str | None
    retry_allowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "state": self.state.value,
            "code": self.code,
            "service_ref": self.service_ref,
            "instance_identity": self.instance_identity,
            "build_identity": self.build_identity,
            "ready": self.ready,
            "runtime_version": self.runtime_version,
            "retry_allowed": self.retry_allowed,
        }


def _validate_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return value


def _validate_observation(value: RestartObservation) -> RestartObservation:
    if not isinstance(value, RestartObservation):
        raise ValueError("observation must be RestartObservation")
    if value.service_ref not in ALLOWED_SERVICES:
        raise ValueError("observation service_ref is outside the closed allowlist")
    _validate_digest(value.instance_identity, "instance_identity")
    _validate_digest(value.build_identity, "build_identity")
    if type(value.ready) is not bool:
        raise ValueError("ready must be boolean")
    if value.runtime_version is not None and (
        not isinstance(value.runtime_version, str)
        or _VERSION.fullmatch(value.runtime_version) is None
    ):
        raise ValueError("runtime_version is invalid")
    if not isinstance(value.issues, tuple) or any(
        not isinstance(item, str) or not item for item in value.issues
    ):
        raise ValueError("issues must be an immutable tuple of non-empty strings")
    return value


def validate_request(value: RestartRequest) -> RestartRequest:
    if not isinstance(value, RestartRequest):
        raise ValueError("request must be RestartRequest")
    if value.service_ref not in ALLOWED_SERVICES:
        raise ValueError("service_ref is outside the closed allowlist")
    if value.reason_code not in ALLOWED_REASONS:
        raise ValueError("reason_code is outside the closed allowlist")
    _validate_digest(value.expected_instance_identity, "expected_instance_identity")
    _validate_digest(value.expected_build_identity, "expected_build_identity")
    return value


def _not_applied(request: RestartRequest, observed: RestartObservation, code: str) -> RestartResult:
    return RestartResult(
        RestartState.NOT_APPLIED,
        code,
        request.service_ref,
        observed.instance_identity,
        observed.build_identity,
        observed.ready,
        observed.runtime_version,
        False,
    )


def preflight_restart(
    request: RestartRequest,
    observed: RestartObservation,
) -> RestartResult | None:
    """Validate exact preconditions before the owner receives a modifying call."""
    request = validate_request(request)
    observed = _validate_observation(observed)
    if observed.service_ref != request.service_ref:
        raise ValueError("observation does not match request service_ref")
    if observed.instance_identity != request.expected_instance_identity:
        return _not_applied(request, observed, "STALE_INSTANCE_IDENTITY")
    if observed.build_identity != request.expected_build_identity:
        return _not_applied(request, observed, "STALE_BUILD_IDENTITY")
    if "CONFIGURATION_DRIFT" in observed.issues:
        return _not_applied(request, observed, "CONFIGURATION_DRIFT")
    return None


__all__ = [
    "ALLOWED_REASONS",
    "ALLOWED_SERVICES",
    "RestartObservation",
    "RestartRequest",
    "RestartResult",
    "RestartState",
    "SCHEMA",
    "preflight_restart",
    "validate_request",
]
