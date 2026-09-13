"""Reviewed subscription-backed provider profiles for the common worker harness.

Profiles are non-secret routing/configuration metadata. They never contain API keys,
provider-account identity, or live capacity. Credentials remain adapter-private and
capacity remains owned by shared Provider Control.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "mastermind.subscription_provider_profiles/v1"
ADAPTER_ID = "claude-compatible-subscription"
DEFAULT_PROFILES_PATH = Path(__file__).resolve().parents[1] / "config" / "subscription_provider_profiles.v1.json"
_ALLOWED_PROTOCOLS = {"anthropic"}
_ALLOWED_MODEL_CLASSES = {"routine", "hard", "fast", "subagent"}


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

    def model_for(self, model_class: str | None = None) -> str:
        key = model_class or self.default_model_class
        try:
            return self.models[key]
        except KeyError as exc:
            raise ProviderProfileError(
                f"profile {self.profile_id!r} does not support model class {key!r}"
            ) from exc


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProviderProfileError(f"invalid {label}: {value!r}")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")
    lowered = value.lower()
    if any(ch not in allowed for ch in lowered):
        raise ProviderProfileError(f"invalid {label}: {value!r}")
    return value


def validate_profiles(document: Any) -> Mapping[str, Any]:
    if not isinstance(document, Mapping) or document.get("schema") != SCHEMA:
        raise ProviderProfileError("unsupported provider-profile schema")
    if document.get("adapter_id") != ADAPTER_ID:
        raise ProviderProfileError("subscription profiles must bind the common reviewed adapter")
    profiles = document.get("profiles")
    if not isinstance(profiles, Mapping) or not profiles:
        raise ProviderProfileError("profiles are required")
    for profile_id, row in profiles.items():
        _identifier(profile_id, "profile id")
        if not isinstance(row, Mapping):
            raise ProviderProfileError(f"profile {profile_id!r} must be a mapping")
        _identifier(row.get("provider"), "provider")
        _identifier(row.get("product"), "product")
        if row.get("protocol") not in _ALLOWED_PROTOCOLS:
            raise ProviderProfileError(f"profile {profile_id!r} has unsupported protocol")
        base_url = row.get("base_url")
        if not isinstance(base_url, str) or not base_url.startswith("https://") or "@" in base_url:
            raise ProviderProfileError(f"profile {profile_id!r} has invalid base URL")
        if row.get("credential_binding") != "adapter_private_provider_realm":
            raise ProviderProfileError(f"profile {profile_id!r} leaks credential authority")
        models = row.get("models")
        if not isinstance(models, Mapping) or not models:
            raise ProviderProfileError(f"profile {profile_id!r} requires models")
        if not set(models).issubset(_ALLOWED_MODEL_CLASSES):
            raise ProviderProfileError(f"profile {profile_id!r} has unknown model class")
        if not all(isinstance(model, str) and model.strip() for model in models.values()):
            raise ProviderProfileError(f"profile {profile_id!r} has invalid model identifiers")
        default = row.get("default_model_class")
        if default not in models:
            raise ProviderProfileError(f"profile {profile_id!r} default model class is absent")
        if row.get("activation_gate") != "provider_realm_enrolled_and_capacity_known":
            raise ProviderProfileError(f"profile {profile_id!r} weakens activation gate")
        if row.get("autonomous_allowed") is not False:
            raise ProviderProfileError(
                f"profile {profile_id!r} cannot be autonomous before enrollment/capacity proof"
            )
        quota = row.get("quota_profile")
        if not isinstance(quota, Mapping) or quota.get("provider") != row.get("provider"):
            raise ProviderProfileError(f"profile {profile_id!r} quota identity disagrees")
    return document


def load_profiles(path: Path | str = DEFAULT_PROFILES_PATH) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return validate_profiles(json.load(handle))


def get_profile(profile_id: str, *, document: Mapping[str, Any] | None = None) -> SubscriptionProviderProfile:
    catalog = validate_profiles(document) if document is not None else load_profiles()
    row = catalog["profiles"].get(profile_id)
    if not isinstance(row, Mapping):
        raise ProviderProfileError(f"unknown subscription provider profile {profile_id!r}")
    return SubscriptionProviderProfile(
        profile_id=profile_id,
        provider=row["provider"],
        product=row["product"],
        protocol=row["protocol"],
        base_url=row["base_url"],
        models=dict(row["models"]),
        default_model_class=row["default_model_class"],
        supported_tool_only=bool(row.get("supported_tool_only")),
        autonomous_allowed=bool(row["autonomous_allowed"]),
        activation_gate=row["activation_gate"],
        quota_profile=dict(row["quota_profile"]),
    )


__all__ = ["ADAPTER_ID", "DEFAULT_PROFILES_PATH", "ProviderProfileError", "SubscriptionProviderProfile", "get_profile", "load_profiles", "validate_profiles"]
