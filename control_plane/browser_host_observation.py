"""Pure browser-host observation qualification for Browser Fabric Capacity input.

This module consumes one already-acquired Surface Bindings observation. It does
not inspect Chrome, start a backend, rank hosts, allocate capacity, admit a
caller, create a lease, persist state, or read a clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re

from control_plane.executive_steward import Freshness, SourceOwner, SourceRef

SCHEMA = "mastermind.browser_host_qualification.v1"
EXPECTED_BACKEND_VERSION = "1.10.1"
MIN_AUTOCONNECT_CHROME_MAJOR = 144

_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_CHROME_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$")
_BACKEND_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class BrowserHostObservationError(ValueError):
    """One host observation is structurally invalid or cannot be qualified."""


class BrowserHostState(str, Enum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


def _token(value: object, field: str) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        raise BrowserHostObservationError(f"{field} is invalid")
    return value


def _timestamp(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise BrowserHostObservationError(f"{field} is invalid")
    return value


def _nullable_bool(value: object, field: str) -> bool | None:
    if value is not None and type(value) is not bool:
        raise BrowserHostObservationError(f"{field} is invalid")
    return value


def _source(value: object) -> SourceRef:
    if type(value) is not SourceRef or value.owner is not SourceOwner.SURFACE_BINDINGS:
        raise BrowserHostObservationError("source owner is invalid")
    return value


@dataclass(frozen=True, slots=True)
class BrowserHostObservation:
    host_ref: str
    boot_ref: str
    profile_ref: str
    browser_instance_ref: str
    connector_generation: str
    browser_version: str
    backend_version: str
    backend_schema_digest: str
    remote_debugging_enabled: bool | None
    user_consent_observed: bool | None
    connected: bool | None
    observed_at_ms: int
    expires_at_ms: int
    source: SourceRef

    def __post_init__(self) -> None:
        for field in (
            "host_ref",
            "boot_ref",
            "profile_ref",
            "browser_instance_ref",
            "connector_generation",
        ):
            _token(getattr(self, field), field)
        if type(self.browser_version) is not str or _CHROME_VERSION.fullmatch(self.browser_version) is None:
            raise BrowserHostObservationError("browser_version is invalid")
        if type(self.backend_version) is not str or _BACKEND_VERSION.fullmatch(self.backend_version) is None:
            raise BrowserHostObservationError("backend_version is invalid")
        if type(self.backend_schema_digest) is not str or _DIGEST.fullmatch(self.backend_schema_digest) is None:
            raise BrowserHostObservationError("backend_schema_digest is invalid")
        for field in ("remote_debugging_enabled", "user_consent_observed", "connected"):
            _nullable_bool(getattr(self, field), field)
        _timestamp(self.observed_at_ms, "observed_at_ms")
        _timestamp(self.expires_at_ms, "expires_at_ms")
        if self.expires_at_ms <= self.observed_at_ms:
            raise BrowserHostObservationError("observation validity window is invalid")
        _source(self.source)


@dataclass(frozen=True, slots=True)
class BrowserHostQualification:
    host_ref: str
    profile_ref: str
    browser_instance_ref: str
    connector_generation: str
    state: BrowserHostState
    reason: str

    @property
    def is_placement(self) -> bool:
        return False

    @property
    def is_admission(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "host_ref": self.host_ref,
            "profile_ref": self.profile_ref,
            "browser_instance_ref": self.browser_instance_ref,
            "connector_generation": self.connector_generation,
            "state": self.state.value,
            "reason": self.reason,
            "is_placement": False,
            "is_admission": False,
        }


def _result(row: BrowserHostObservation, state: BrowserHostState, reason: str) -> BrowserHostQualification:
    return BrowserHostQualification(
        host_ref=row.host_ref,
        profile_ref=row.profile_ref,
        browser_instance_ref=row.browser_instance_ref,
        connector_generation=row.connector_generation,
        state=state,
        reason=reason,
    )


def qualify_browser_host(
    value: BrowserHostObservation,
    *,
    expected_backend_schema_digest: str,
    trusted_now_ms: int,
) -> BrowserHostQualification:
    """Qualify one observed host without selecting, admitting, or starting it."""
    if type(value) is not BrowserHostObservation:
        raise BrowserHostObservationError("typed BrowserHostObservation required")
    value.__post_init__()
    if type(expected_backend_schema_digest) is not str or _DIGEST.fullmatch(expected_backend_schema_digest) is None:
        raise BrowserHostObservationError("expected backend schema digest is invalid")
    _timestamp(trusted_now_ms, "trusted_now_ms")

    if (
        value.source.freshness is not Freshness.CURRENT
        or value.observed_at_ms > trusted_now_ms
        or trusted_now_ms >= value.expires_at_ms
    ):
        return _result(value, BrowserHostState.UNKNOWN, "observation_not_current")

    major = int(_CHROME_VERSION.fullmatch(value.browser_version).group(1))
    if major < MIN_AUTOCONNECT_CHROME_MAJOR:
        return _result(value, BrowserHostState.UNAVAILABLE, "browser_version_unsupported")
    if value.backend_version != EXPECTED_BACKEND_VERSION:
        return _result(value, BrowserHostState.UNAVAILABLE, "backend_version_mismatch")
    if value.backend_schema_digest != expected_backend_schema_digest:
        return _result(value, BrowserHostState.UNAVAILABLE, "backend_schema_mismatch")

    live_fields = (
        value.remote_debugging_enabled,
        value.user_consent_observed,
        value.connected,
    )
    if any(item is None for item in live_fields):
        return _result(value, BrowserHostState.UNKNOWN, "surface_state_unknown")
    if value.remote_debugging_enabled is False:
        return _result(value, BrowserHostState.UNAVAILABLE, "remote_debugging_disabled")
    if value.user_consent_observed is False:
        return _result(value, BrowserHostState.UNAVAILABLE, "browser_consent_missing")
    if value.connected is False:
        return _result(value, BrowserHostState.UNAVAILABLE, "backend_disconnected")
    return _result(value, BrowserHostState.READY, "ready")
