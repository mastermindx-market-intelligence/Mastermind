"""Pure read-only core for the Business Sol HC0 host-context falsifier.

The core accepts only server-observed request metadata plus immutable local
configuration.  It returns pseudonymous correlation evidence, never raw host
values, authentication, RuntimeBinding state, lifecycle state, or permission to
modify another system.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .schemas import (
    CONTRACT_DIGEST,
    HOST_CONTEXT_KEYS,
    IDENTIFIER_HOST_FIELDS,
    MAX_RESPONSE_BYTES,
    RESULT_SCHEMA,
    SERVER_IDENTITY,
    SERVER_VERSION,
    SLUG_PATTERN,
    canonical_json,
)

_ERROR_CODES = frozenset(
    {
        "INVALID_CONFIGURATION",
        "INVALID_HOST_METADATA",
        "INVALID_OBSERVATION_TIME",
        "INTERNAL_RESPONSE_TOO_LARGE",
    }
)
_SLUG_RE = re.compile(SLUG_PATTERN)
_MAX_META_ENTRIES = 64
_MAX_IDENTIFIER_BYTES = 4096
_MAX_LOCALE_BYTES = 128
_MAX_USER_AGENT_BYTES = 2048
_MAX_LOCATION_TEXT_BYTES = 512

_REQUEST_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("openai/session", "openai_session", "OPENAI_SESSION_ABSENT", "identifier"),
    ("openai/subject", "openai_subject", "OPENAI_SUBJECT_ABSENT", "identifier"),
    (
        "openai/organization",
        "openai_organization",
        "OPENAI_ORGANIZATION_ABSENT",
        "identifier",
    ),
    ("openai/locale", "openai_locale", "OPENAI_LOCALE_ABSENT", "locale"),
    ("openai/userAgent", "user_agent_hint", "USER_AGENT_HINT_ABSENT", "user_agent"),
    (
        "openai/userLocation",
        "user_location_hint",
        "USER_LOCATION_HINT_ABSENT",
        "location",
    ),
)
_KNOWN_REQUEST_KEYS = frozenset(field[0] for field in _REQUEST_FIELDS)
_IGNORED_STANDARD_META_KEYS = frozenset({"progressToken"})
_LOCATION_TEXT_KEYS = frozenset({"city", "region", "country", "timezone"})
_LOCATION_NUMBER_KEYS = frozenset({"longitude", "latitude"})
_LOCATION_KEYS = _LOCATION_TEXT_KEYS | _LOCATION_NUMBER_KEYS


class HostContextProbeError(ValueError):
    """Bounded refusal whose text can never echo untrusted metadata."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        safe_code = code if code in _ERROR_CODES else "INVALID_HOST_METADATA"
        self.code = safe_code
        super().__init__(safe_code)

    def __str__(self) -> str:
        return self.code


class HostContextProbeConfig:
    """Validated immutable probe configuration with redacted secret storage."""

    __slots__ = (
        "app_realm",
        "app_generation",
        "transport_profile",
        "fingerprint_key_id",
        "fingerprint_key_version",
        "fingerprint_scope",
        "__secret",
        "__sealed",
    )

    def __init__(
        self,
        *,
        app_realm: str,
        app_generation: str,
        transport_profile: str,
        fingerprint_key_id: str,
        fingerprint_key_version: str,
        fingerprint_scope: str,
        fingerprint_secret: bytes,
    ) -> None:
        values = (
            app_realm,
            app_generation,
            transport_profile,
            fingerprint_key_id,
            fingerprint_key_version,
            fingerprint_scope,
        )
        if any(not isinstance(value, str) or _SLUG_RE.fullmatch(value) is None for value in values):
            raise HostContextProbeError("INVALID_CONFIGURATION")
        if type(fingerprint_secret) is not bytes or not 32 <= len(fingerprint_secret) <= 256:
            raise HostContextProbeError("INVALID_CONFIGURATION")

        object.__setattr__(self, "app_realm", app_realm)
        object.__setattr__(self, "app_generation", app_generation)
        object.__setattr__(self, "transport_profile", transport_profile)
        object.__setattr__(self, "fingerprint_key_id", fingerprint_key_id)
        object.__setattr__(self, "fingerprint_key_version", fingerprint_key_version)
        object.__setattr__(self, "fingerprint_scope", fingerprint_scope)
        object.__setattr__(self, "_HostContextProbeConfig__secret", bytes(fingerprint_secret))
        object.__setattr__(self, "_HostContextProbeConfig__sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_HostContextProbeConfig__sealed", False):
            raise AttributeError("HostContextProbeConfig is immutable")
        object.__setattr__(self, name, value)

    def __repr__(self) -> str:
        return (
            "HostContextProbeConfig("
            f"app_realm={self.app_realm!r}, "
            f"app_generation={self.app_generation!r}, "
            f"transport_profile={self.transport_profile!r}, "
            f"fingerprint_key_id={self.fingerprint_key_id!r}, "
            f"fingerprint_key_version={self.fingerprint_key_version!r}, "
            f"fingerprint_scope={self.fingerprint_scope!r}, "
            "secret=<redacted>)"
        )

    def _secret_bytes(self) -> bytes:
        """Return the immutable key only to this module's HMAC boundary."""

        return self.__secret


def _raise_host_metadata_error() -> None:
    raise HostContextProbeError("INVALID_HOST_METADATA")


def _validate_text(value: object, *, max_bytes: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _raise_host_metadata_error()
    try:
        encoded = value.encode("utf-8", errors="strict")
    except UnicodeError:
        _raise_host_metadata_error()
    if len(encoded) > max_bytes:
        _raise_host_metadata_error()
    if any(unicodedata.category(character).startswith("C") for character in value):
        _raise_host_metadata_error()
    return value


def _validate_location(value: object) -> None:
    if not isinstance(value, Mapping):
        _raise_host_metadata_error()
    try:
        if len(value) > len(_LOCATION_KEYS):
            _raise_host_metadata_error()
        keys = tuple(value.keys())
    except Exception as exc:
        raise HostContextProbeError("INVALID_HOST_METADATA") from None
    if any(not isinstance(key, str) or key not in _LOCATION_KEYS for key in keys):
        _raise_host_metadata_error()

    for key in keys:
        try:
            item = value[key]
        except Exception:
            raise HostContextProbeError("INVALID_HOST_METADATA") from None
        if item is None:
            continue
        if key in _LOCATION_TEXT_KEYS:
            _validate_text(item, max_bytes=_MAX_LOCATION_TEXT_BYTES)
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            _raise_host_metadata_error()
        try:
            number = float(item)
        except (OverflowError, TypeError, ValueError):
            _raise_host_metadata_error()
        if not math.isfinite(number):
            _raise_host_metadata_error()
        if key == "longitude" and not -180.0 <= number <= 180.0:
            _raise_host_metadata_error()
        if key == "latitude" and not -90.0 <= number <= 90.0:
            _raise_host_metadata_error()


def _fingerprint(config: HostContextProbeConfig, *, field: str, raw_value: str) -> str:
    message = canonical_json(
        {
            "schema": RESULT_SCHEMA,
            "app_realm": config.app_realm,
            "app_generation": config.app_generation,
            "fingerprint_scope": config.fingerprint_scope,
            "fingerprint_key_id": config.fingerprint_key_id,
            "fingerprint_key_version": config.fingerprint_key_version,
            "field": field,
            "value": raw_value,
        }
    )
    digest = hmac.new(config._secret_bytes(), message, hashlib.sha256).hexdigest()
    return f"hmac-sha256:{config.fingerprint_key_version}:{digest}"


def _normalize_observation_time(observed_at: datetime) -> str:
    if (
        not isinstance(observed_at, datetime)
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise HostContextProbeError("INVALID_OBSERVATION_TIME")
    return observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _normalize_meta(meta: object) -> Mapping[object, object]:
    if meta is None:
        return {}
    if not isinstance(meta, Mapping):
        _raise_host_metadata_error()
    try:
        if len(meta) > _MAX_META_ENTRIES:
            _raise_host_metadata_error()
    except Exception:
        raise HostContextProbeError("INVALID_HOST_METADATA") from None
    return meta


def inspect_surface_context(
    meta: object,
    *,
    config: HostContextProbeConfig,
    observed_at: datetime,
) -> dict[str, Any]:
    """Return a bounded pseudonymous observation of documented request metadata.

    ``meta`` must already be the server-observed MCP request ``_meta`` mapping.
    The function performs no I/O and retains no observation after returning.
    """

    if not isinstance(config, HostContextProbeConfig):
        raise HostContextProbeError("INVALID_CONFIGURATION")
    normalized_time = _normalize_observation_time(observed_at)
    metadata = _normalize_meta(meta)

    degradations = {"OAUTH_NOT_CONFIGURED", "TUNNEL_ATTESTATION_UNAVAILABLE"}
    try:
        metadata_keys = tuple(metadata.keys())
    except Exception:
        raise HostContextProbeError("INVALID_HOST_METADATA") from None
    if any(
        key not in _KNOWN_REQUEST_KEYS and key not in _IGNORED_STANDARD_META_KEYS
        for key in metadata_keys
    ):
        degradations.add("UNKNOWN_HOST_META_IGNORED")

    host_context: dict[str, dict[str, object]] = {}
    for request_key, output_key, absent_code, kind in _REQUEST_FIELDS:
        try:
            present = request_key in metadata
        except Exception:
            raise HostContextProbeError("INVALID_HOST_METADATA") from None
        if not present:
            degradations.add(absent_code)
            host_context[output_key] = {
                "present": False,
                "fingerprint": None,
                "usable_for_authorization": False,
            }
            continue

        try:
            raw_value = metadata[request_key]
        except Exception:
            raise HostContextProbeError("INVALID_HOST_METADATA") from None

        fingerprint: str | None = None
        if kind == "identifier":
            identifier = _validate_text(raw_value, max_bytes=_MAX_IDENTIFIER_BYTES)
            fingerprint = _fingerprint(config, field=output_key, raw_value=identifier)
        elif kind == "locale":
            _validate_text(raw_value, max_bytes=_MAX_LOCALE_BYTES)
        elif kind == "user_agent":
            _validate_text(raw_value, max_bytes=_MAX_USER_AGENT_BYTES)
        elif kind == "location":
            _validate_location(raw_value)
        else:  # pragma: no cover - the static field table is closed and tested.
            raise HostContextProbeError("INVALID_HOST_METADATA")

        host_context[output_key] = {
            "present": True,
            "fingerprint": fingerprint,
            "usable_for_authorization": False,
        }

    if tuple(host_context) != HOST_CONTEXT_KEYS:  # pragma: no cover - invariant guard.
        raise HostContextProbeError("INVALID_HOST_METADATA")
    if any(
        row["fingerprint"] is not None and key not in IDENTIFIER_HOST_FIELDS
        for key, row in host_context.items()
    ):  # pragma: no cover - invariant guard.
        raise HostContextProbeError("INVALID_HOST_METADATA")

    response: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "server_identity": SERVER_IDENTITY,
        "server_version": SERVER_VERSION,
        "app_realm": config.app_realm,
        "app_generation": config.app_generation,
        "contract_digest": CONTRACT_DIGEST,
        "transport_profile": config.transport_profile,
        "fingerprint_key_id": config.fingerprint_key_id,
        "fingerprint_key_version": config.fingerprint_key_version,
        "fingerprint_scope": config.fingerprint_scope,
        "observed_at": normalized_time,
        "correlation_only": True,
        "host_context": host_context,
        "oauth_posture": {
            "configured": False,
            "resource": None,
            "scopes": [],
            "principal_fingerprint": None,
        },
        "degradations": sorted(degradations),
    }
    try:
        rendered = canonical_json(response)
    except (TypeError, ValueError):  # pragma: no cover - invariant guard.
        raise HostContextProbeError("INVALID_HOST_METADATA") from None
    if len(rendered) > MAX_RESPONSE_BYTES:
        raise HostContextProbeError("INTERNAL_RESPONSE_TOO_LARGE")
    return response


__all__ = [
    "HostContextProbeConfig",
    "HostContextProbeError",
    "inspect_surface_context",
]
