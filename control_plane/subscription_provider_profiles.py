"""Reviewed subscription-backed provider profiles.

MIGRATION NOTE: harness/adapter selection lives in subscription_harness_bindings
(PR #583). This layer describes the purchased plan only.

Profiles are non-secret routing/configuration metadata. They never contain API keys,
provider-account identity, or live capacity. Credentials remain adapter-private and
capacity remains owned by shared Provider Control.
"""
from __future__ import annotations

import dataclasses
import ipaddress
import json
import posixpath
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

from control_plane.provider_protocols import PROVIDER_PROTOCOLS as _ALLOWED_PROTOCOLS

SCHEMA = "mastermind.subscription_provider_profiles/v1"
DEFAULT_PROFILES_PATH = Path(__file__).resolve().parents[1] / "config" / "subscription_provider_profiles.v1.json"
_ALLOWED_MODEL_CLASSES = frozenset({"routine", "hard", "fast", "subagent"})
_FORBIDDEN_HARNESS_FIELDS = frozenset({"adapter_id", "harness_id"})

_MAX_STRING_CHARS = 256
_MAX_MAP_KEYS = 32
_MAX_BASE_URL_PATH_CHARS = 128
_MAX_BASE_URL_PATH_GRAMMAR_CHARS = 256
_MAX_BASE_URL_PATH_SEGMENTS = 8
_MAX_BASE_URL_CHARS = 512
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._~-]{1,64}$")
_DNS_HOST_RE = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)
_IPV4_LITERAL_RE = re.compile(r"^[0-9]+(\.[0-9]+){3}$")

_DOCUMENT_REQUIRED = frozenset({"schema", "verified_at", "profiles"})
_DOCUMENT_ALLOWED = _DOCUMENT_REQUIRED | frozenset({"metadata"})

_PROFILE_REQUIRED = frozenset({
    "provider",
    "product",
    "protocol",
    "base_url",
    "models",
    "default_model_class",
    "supported_tool_only",
    "credential_binding",
    "quota_profile",
    "autonomous_allowed",
    "activation_gate",
    "usage_policy",
})
_PROFILE_ALLOWED = _PROFILE_REQUIRED | frozenset({"metadata"})

_QUOTA_ALLOWED = frozenset({"provider", "product", "tier"})
_MODEL_ENTRY_ALLOWED = frozenset({"id"})
_METADATA_ALLOWED = frozenset()

_USAGE_POLICY_REQUIRED = {
    "supported_harness_required": True,
    "interactive_only": True,
    "unattended_background_allowed": False,
    "production_backend_allowed": False,
}
_USAGE_POLICY_OPTIONAL = frozenset({"single_user_only", "payg_recommended_for_production"})
_USAGE_POLICY_ALLOWED = frozenset(_USAGE_POLICY_REQUIRED) | _USAGE_POLICY_OPTIONAL

_IDENTIFIER_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_.")
_VERIFIED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_CREDENTIAL_BINDING = "adapter_private_provider_realm"
_ACTIVATION_GATE = "provider_realm_enrolled_and_capacity_known"


class ProviderProfileError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class SubscriptionProviderProfile:
    profile_id: str
    provider: str
    product: str
    protocol: str
    base_url: str
    models: Mapping[str, str]
    default_model_class: str
    supported_tool_only: bool
    autonomous_allowed: bool
    activation_gate: str
    quota_profile: Mapping[str, Any]
    usage_policy: Mapping[str, bool]

    def model_for(self, model_class: str | None = None) -> str:
        key = model_class or self.default_model_class
        try:
            return self.models[key]
        except KeyError as exc:
            raise ProviderProfileError(
                f"profile {self.profile_id!r} does not support model class {key!r}"
            ) from exc


def _raise(message: str) -> None:
    raise ProviderProfileError(message)


def _reject_harness(mapping: Mapping[str, Any], where: str) -> None:
    if _FORBIDDEN_HARNESS_FIELDS.intersection(mapping):
        if where == "profile document":
            _raise(
                "profile document must not name an adapter or harness; "
                "harness/adapter selection lives in subscription_harness_bindings"
            )
        _raise(f"{where} must not name an adapter or harness")


def _closed_mapping(
    value: Any,
    path: str,
    allowed: frozenset[str],
    *,
    required: frozenset[str] | None = None,
    harness_where: str | None = None,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _raise(f"{path} must be a mapping")
    if len(value) > _MAX_MAP_KEYS:
        _raise(f"{path} exceeds {_MAX_MAP_KEYS} keys")
    _reject_harness(value, harness_where or path)
    unknown = [key for key in value if key not in allowed]
    if unknown:
        _raise(f"{path}.{unknown[0]}: unknown key")
    missing = [key for key in sorted(required or ()) if key not in value]
    if missing:
        _raise(f"{path}.{missing[0]}: missing key")
    return value


def _exact_string(value: Any, path: str, *, max_chars: int = _MAX_STRING_CHARS) -> str:
    if type(value) is not str:
        _raise(f"{path} must be a string")
    if not value or value != value.strip() or len(value) > max_chars:
        _raise(f"{path} exceeds string bounds")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProviderProfileError(f"invalid {label}: {value!r}")
    if len(value) > _MAX_STRING_CHARS:
        raise ProviderProfileError(f"invalid {label}: {value!r}")
    if any(ch not in _IDENTIFIER_CHARS for ch in value.lower()):
        raise ProviderProfileError(f"invalid {label}: {value!r}")
    return value


def _exact_bool(value: Any, path: str, *, expected: bool | None = None) -> bool:
    if type(value) is not bool:
        _raise(f"{path} must be a bool")
    if expected is not None and value is not expected:
        _raise(f"{path} is unsafe")
    return value


def _verified_at(value: Any, path: str) -> str:
    token = _exact_string(value, path)
    if _VERIFIED_AT_RE.fullmatch(token) is None:
        _raise(f"{path} is not a UTC timestamp")
    try:
        datetime.fromisoformat(token[:-1] + "+00:00")
    except ValueError as exc:
        raise ProviderProfileError(f"{path} is not a UTC timestamp") from exc
    return token


def _allowlisted_base_url_path(raw_path: str) -> bool:
    if raw_path in {"", "/"}:
        return True
    if len(raw_path) > _MAX_BASE_URL_PATH_GRAMMAR_CHARS:
        return False
    if not raw_path.startswith("/") or raw_path.endswith("/"):
        return False
    segments = raw_path.split("/")[1:]
    if not (1 <= len(segments) <= _MAX_BASE_URL_PATH_SEGMENTS):
        return False
    for segment in segments:
        if not segment or set(segment) <= {"."}:
            return False
        if _PATH_SEGMENT_RE.fullmatch(segment) is None:
            return False
    return True


def _validate_base_url(value: Any, path: str) -> str:
    token = _exact_string(value, path, max_chars=_MAX_BASE_URL_CHARS)
    if any(ch.isspace() or ord(ch) <= 0x1F or ord(ch) == 0x7F for ch in token):
        _raise(f"{path} has invalid base URL")
    try:
        parsed = urlparse(token)
        _ = parsed.port
    except ValueError as exc:
        raise ProviderProfileError(f"{path} has invalid base URL") from exc
    userinfo = parsed.username is not None or parsed.password is not None or "@" in parsed.netloc
    raw_path = parsed.path or ""
    segments = raw_path.split("/")
    if any(unquote(segment) == ".." for segment in segments):
        _raise(f"{path} has invalid base URL")
    if any(unquote(segment) == "." for segment in segments):
        _raise(f"{path} has invalid base URL")
    if "//" in raw_path or "%2F" in raw_path.upper():
        _raise(f"{path} has invalid base URL")
    normalized = "" if not raw_path else posixpath.normpath(raw_path)
    if normalized == ".":
        normalized = ""
    if raw_path != normalized:
        _raise(f"{path} has invalid base URL")
    hostname = parsed.hostname or ""
    if (
        not token.startswith("https://")
        or parsed.scheme != "https"
        or not hostname
        or userinfo
        or parsed.netloc != hostname
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
        or parsed.params
        or len(normalized) > _MAX_BASE_URL_PATH_CHARS
    ):
        _raise(f"{path} has invalid base URL")
    if (
        not token.isascii()
        or "\\" in token
        or len(hostname) > 253
        or _DNS_HOST_RE.fullmatch(hostname) is None
        or _IPV4_LITERAL_RE.fullmatch(hostname) is not None
        or any(label.startswith("xn--") for label in hostname.split("."))
    ):
        _raise(f"{path} has invalid base URL")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        _raise(f"{path} has invalid base URL")
    if "%" in raw_path or "%" in (parsed.hostname or "") or "%" in parsed.netloc:
        _raise(f"{path} has invalid base URL")
    if not _allowlisted_base_url_path(raw_path):
        _raise(f"{path} has invalid base URL")
    if token != "https://" + hostname + raw_path:
        _raise(f"{path} has invalid base URL")
    return token


def _validate_metadata(value: Any, path: str) -> Mapping[str, Any]:
    return _closed_mapping(value, path, _METADATA_ALLOWED, required=frozenset())


def _model_identifier(value: Any, path: str) -> str:
    if isinstance(value, Mapping):
        entry = _closed_mapping(value, path, _MODEL_ENTRY_ALLOWED, required=_MODEL_ENTRY_ALLOWED)
        return _identifier(entry["id"], path)
    return _identifier(value, path)


def _validate_models(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        _raise(f"{path} requires models")
    if len(value) > _MAX_MAP_KEYS:
        _raise(f"{path} exceeds {_MAX_MAP_KEYS} keys")
    _reject_harness(value, path)
    unknown = [key for key in value if key not in _ALLOWED_MODEL_CLASSES]
    if unknown:
        _raise(f"{path}.{unknown[0]}: unknown key")
    for key, model in value.items():
        _model_identifier(model, f"{path}.{key}")
    return value


def _validate_quota(value: Any, path: str, *, provider: str, product: str) -> Mapping[str, Any]:
    quota = _closed_mapping(value, path, _QUOTA_ALLOWED, required=_QUOTA_ALLOWED)
    if _identifier(quota.get("provider"), "quota provider") != provider:
        _raise(f"{path} quota identity disagrees")
    if _identifier(quota.get("product"), "quota product") != product:
        _raise(f"{path} quota identity disagrees")
    tier = quota.get("tier")
    if tier is not None:
        _identifier(tier, "quota tier")
    return quota


def _validate_usage_policy(value: Any, path: str) -> Mapping[str, Any]:
    policy = _closed_mapping(value, path, _USAGE_POLICY_ALLOWED, required=frozenset(_USAGE_POLICY_REQUIRED))
    for key, expected in _USAGE_POLICY_REQUIRED.items():
        _exact_bool(policy[key], f"{path}.{key}", expected=expected)
    for key in _USAGE_POLICY_OPTIONAL:
        if key in policy:
            _exact_bool(policy[key], f"{path}.{key}")
    return policy


def _validate_row(profile_id: str, row: Any) -> Mapping[str, Any]:
    path = f"profiles.{profile_id}"
    mapping = _closed_mapping(
        row,
        path,
        _PROFILE_ALLOWED,
        required=_PROFILE_REQUIRED,
        harness_where=f"profile {profile_id!r}",
    )
    provider = _identifier(mapping.get("provider"), "provider")
    product = _identifier(mapping.get("product"), "product")
    protocol = _exact_string(mapping.get("protocol"), f"{path}.protocol")
    if protocol not in _ALLOWED_PROTOCOLS:
        _raise(f"profile {profile_id!r} has unsupported protocol")
    _validate_base_url(mapping.get("base_url"), f"{path}.base_url")
    if mapping.get("credential_binding") != _CREDENTIAL_BINDING:
        _raise(f"profile {profile_id!r} leaks credential authority")
    _exact_string(mapping.get("credential_binding"), f"{path}.credential_binding")
    models = _validate_models(mapping.get("models"), f"{path}.models")
    default = mapping.get("default_model_class")
    if default not in models:
        _raise(f"profile {profile_id!r} default model class is absent")
    _exact_bool(mapping.get("supported_tool_only"), f"{path}.supported_tool_only")
    if mapping.get("activation_gate") != _ACTIVATION_GATE:
        _raise(f"profile {profile_id!r} weakens activation gate")
    _exact_string(mapping.get("activation_gate"), f"{path}.activation_gate")
    _exact_bool(mapping.get("autonomous_allowed"), f"{path}.autonomous_allowed")
    if mapping.get("autonomous_allowed") is not False:
        _raise(f"profile {profile_id!r} cannot be autonomous before enrollment/capacity proof")
    _validate_quota(
        mapping.get("quota_profile"),
        f"{path}.quota_profile",
        provider=provider,
        product=product,
    )
    _validate_usage_policy(mapping.get("usage_policy"), f"{path}.usage_policy")
    if "metadata" in mapping:
        _validate_metadata(mapping.get("metadata"), f"{path}.metadata")
    return mapping


def validate_profiles(document: Any) -> Mapping[str, Any]:
    if not isinstance(document, Mapping) or document.get("schema") != SCHEMA:
        raise ProviderProfileError("unsupported provider-profile schema")
    _reject_harness(document, "profile document")
    catalog = _closed_mapping(
        document,
        "document",
        _DOCUMENT_ALLOWED,
        required=_DOCUMENT_REQUIRED,
        harness_where="profile document",
    )
    _verified_at(catalog.get("verified_at"), "document.verified_at")
    if "metadata" in catalog:
        _validate_metadata(catalog.get("metadata"), "document.metadata")
    profiles = catalog.get("profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        raise ProviderProfileError("profiles are required")
    if len(profiles) > _MAX_MAP_KEYS:
        _raise(f"document.profiles exceeds {_MAX_MAP_KEYS} keys")
    _reject_harness(profiles, "document.profiles")
    for profile_id, row in profiles.items():
        _identifier(profile_id, "profile id")
        _validate_row(profile_id, row)
    return document


def load_profiles(path: Path | str = DEFAULT_PROFILES_PATH) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return validate_profiles(json.load(handle))


def get_profile(profile_id: str, *, document: Mapping[str, Any] | None = None) -> SubscriptionProviderProfile:
    catalog = validate_profiles(document) if document is not None else load_profiles()
    row = catalog["profiles"].get(profile_id)
    if not isinstance(row, Mapping):
        raise ProviderProfileError(f"unknown subscription provider profile {profile_id!r}")
    models = {
        key: value["id"] if isinstance(value, Mapping) else value
        for key, value in row["models"].items()
    }
    return SubscriptionProviderProfile(
        profile_id=profile_id,
        provider=row["provider"],
        product=row["product"],
        protocol=row["protocol"],
        base_url=row["base_url"],
        models=models,
        default_model_class=row["default_model_class"],
        supported_tool_only=row["supported_tool_only"],
        autonomous_allowed=row["autonomous_allowed"],
        activation_gate=row["activation_gate"],
        quota_profile=dict(row["quota_profile"]),
        usage_policy=dict(row["usage_policy"]),
    )


__all__ = ["DEFAULT_PROFILES_PATH", "ProviderProfileError", "SubscriptionProviderProfile", "get_profile", "load_profiles", "validate_profiles"]
