"""Reviewed provider-plan to execution-harness bindings.

The provider profile describes the purchased plan. A binding describes one
reviewed way to consume that plan. Neither object owns Executive lifecycle,
capacity, credentials, retries, or post-START failover.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from control_plane.subscription_provider_profiles import (
    SubscriptionProviderProfile,
    get_profile,
    load_profiles,
    validate_profiles,
)

SCHEMA = "mastermind.subscription_harness_bindings/v1"
DEFAULT_BINDINGS_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "subscription_harness_bindings.v1.json"
)
_ALLOWED_PROTOCOLS = {"anthropic", "responses", "openai-chat"}
_ALLOWED_STATES = {"SPEC_ONLY", "BUILT_NOT_PROVEN", "PROVEN_LIVE"}
_REQUIRED_GATES = (
    "adapter_implemented",
    "provider_realm_enrolled",    "capacity_known",
    "real_canary_passed",
    "usage_policy_satisfied",
)


class HarnessBindingError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class SubscriptionHarnessBinding:
    binding_id: str
    profile_id: str
    provider: str
    harness_id: str
    adapter_id: str
    protocol: str
    effective_base_url: str
    model_classes: tuple[str, ...]
    implementation_state: str
    autonomous_allowed: bool
    activation_gates: tuple[str, ...]

    def model_for(
        self,
        profile: SubscriptionProviderProfile,
        model_class: str | None = None,
    ) -> str:
        selected = model_class or profile.default_model_class
        if selected not in self.model_classes:
            raise HarnessBindingError(
                f"binding {self.binding_id!r} does not support model class {selected!r}"
            )
        return profile.model_for(selected)


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HarnessBindingError(f"invalid {label}: {value!r}")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_.")
    if any(ch not in allowed for ch in value.lower()):
        raise HarnessBindingError(f"invalid {label}: {value!r}")
    return value


def _safe_https(value: Any) -> str:
    if not isinstance(value, str):
        raise HarnessBindingError("binding endpoint must be HTTPS")
    endpoint = value.strip().rstrip("/")
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise HarnessBindingError("binding endpoint must be credential-free HTTPS")
    return endpoint


def _profiles(document: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return validate_profiles(document) if document is not None else load_profiles()


def validate_bindings(
    document: Any,
    *,
    profiles_document: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    if not isinstance(document, Mapping) or document.get("schema") != SCHEMA:
        raise HarnessBindingError("unsupported harness-binding schema")
    profiles = _profiles(profiles_document)
    bindings = document.get("bindings")
    if not isinstance(bindings, Mapping) or not bindings:
        raise HarnessBindingError("harness bindings are required")
    for binding_id, row in bindings.items():
        _identifier(binding_id, "binding id")
        if not isinstance(row, Mapping):
            raise HarnessBindingError(f"binding {binding_id!r} must be a mapping")
        profile_id = _identifier(row.get("profile_id"), "profile id")
        profile = get_profile(profile_id, document=profiles)
        provider = _identifier(row.get("provider"), "provider")
        if provider != profile.provider:
            raise HarnessBindingError(f"binding {binding_id!r} provider disagrees")
        _identifier(row.get("harness_id"), "harness id")
        _identifier(row.get("adapter_id"), "adapter id")
        protocol = row.get("protocol")
        if protocol not in _ALLOWED_PROTOCOLS:
            raise HarnessBindingError(f"binding {binding_id!r} protocol is unsupported")
        endpoint = row.get("endpoint")
        if not isinstance(endpoint, Mapping):
            raise HarnessBindingError(f"binding {binding_id!r} endpoint is invalid")
        source = endpoint.get("source")
        if source == "profile":
            if set(endpoint) != {"source"} or protocol != profile.protocol:
                raise HarnessBindingError(
                    f"binding {binding_id!r} profile endpoint disagrees"
                )
        elif source == "reviewed_override":
            if set(endpoint) != {"source", "base_url"}:
                raise HarnessBindingError(
                    f"binding {binding_id!r} override endpoint is invalid"
                )
            _safe_https(endpoint.get("base_url"))
        else:
            raise HarnessBindingError(f"binding {binding_id!r} endpoint source is invalid")
        model_classes = row.get("model_classes")
        if (
            not isinstance(model_classes, list)
            or not model_classes
            or len(model_classes) != len(set(model_classes))
            or not set(model_classes).issubset(profile.models)
        ):
            raise HarnessBindingError(f"binding {binding_id!r} model classes disagree")
        state = row.get("implementation_state")
        if state not in _ALLOWED_STATES:
            raise HarnessBindingError(f"binding {binding_id!r} state is invalid")
        autonomous = row.get("autonomous_allowed")
        if type(autonomous) is not bool:
            raise HarnessBindingError(f"binding {binding_id!r} autonomous flag is invalid")
        if autonomous and state != "PROVEN_LIVE":
            raise HarnessBindingError(f"binding {binding_id!r} arms an unproven lane")
        if tuple(row.get("activation_gates") or ()) != _REQUIRED_GATES:
            raise HarnessBindingError(f"binding {binding_id!r} weakens activation gates")
    return document


def load_bindings(
    path: Path | str = DEFAULT_BINDINGS_PATH,
    *,
    profiles_document: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return validate_bindings(
            json.load(handle),
            profiles_document=profiles_document,
        )


def get_binding(
    binding_id: str,
    *,
    document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
) -> SubscriptionHarnessBinding:
    catalog = (
        validate_bindings(document, profiles_document=profiles_document)
        if document is not None
        else load_bindings(profiles_document=profiles_document)
    )
    row = catalog["bindings"].get(binding_id)
    if not isinstance(row, Mapping):
        raise HarnessBindingError(f"unknown harness binding {binding_id!r}")
    profile = get_profile(row["profile_id"], document=_profiles(profiles_document))
    endpoint = row["endpoint"]
    effective_base_url = (
        profile.base_url if endpoint["source"] == "profile" else _safe_https(endpoint["base_url"])
    )
    return SubscriptionHarnessBinding(
        binding_id=binding_id,
        profile_id=row["profile_id"],
        provider=row["provider"],
        harness_id=row["harness_id"],
        adapter_id=row["adapter_id"],
        protocol=row["protocol"],
        effective_base_url=effective_base_url,
        model_classes=tuple(row["model_classes"]),
        implementation_state=row["implementation_state"],
        autonomous_allowed=row["autonomous_allowed"],
        activation_gates=tuple(row["activation_gates"]),
    )


def bindings_for_profile(
    profile_id: str,
    *,
    document: Mapping[str, Any] | None = None,
    profiles_document: Mapping[str, Any] | None = None,
) -> tuple[SubscriptionHarnessBinding, ...]:
    catalog = (
        validate_bindings(document, profiles_document=profiles_document)
        if document is not None
        else load_bindings(profiles_document=profiles_document)
    )
    return tuple(
        get_binding(
            binding_id,
            document=catalog,
            profiles_document=profiles_document,
        )
        for binding_id, row in catalog["bindings"].items()
        if row["profile_id"] == profile_id
    )


def canary_blockers(
    binding: SubscriptionHarnessBinding,
    *,
    adapter_implemented: bool,
    provider_realm_enrolled: bool,
    capacity_known: bool,
    usage_policy_satisfied: bool,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if binding.implementation_state == "SPEC_ONLY":
        blockers.append("implementation_not_built")
    facts = {
        "adapter_implemented": adapter_implemented,
        "provider_realm_enrolled": provider_realm_enrolled,
        "capacity_known": capacity_known,
        "usage_policy_satisfied": usage_policy_satisfied,
    }
    blockers.extend(name for name, ready in facts.items() if not ready)
    return tuple(blockers)


def autonomous_activation_blockers(
    binding: SubscriptionHarnessBinding,
    *,
    adapter_implemented: bool,
    provider_realm_enrolled: bool,
    capacity_known: bool,
    real_canary_passed: bool,
    usage_policy_satisfied: bool,
) -> tuple[str, ...]:
    blockers = list(
        canary_blockers(
            binding,
            adapter_implemented=adapter_implemented,
            provider_realm_enrolled=provider_realm_enrolled,
            capacity_known=capacity_known,
            usage_policy_satisfied=usage_policy_satisfied,
        )
    )
    if binding.implementation_state != "PROVEN_LIVE":
        blockers.append("implementation_not_proven_live")
    if not binding.autonomous_allowed:
        blockers.append("source_policy_disarmed")
    if not real_canary_passed:
        blockers.append("real_canary_not_passed")
    return tuple(dict.fromkeys(blockers))


__all__ = [
    "DEFAULT_BINDINGS_PATH",
    "HarnessBindingError",
    "SCHEMA",
    "SubscriptionHarnessBinding",
    "autonomous_activation_blockers",
    "bindings_for_profile",
    "canary_blockers",
    "get_binding",
    "load_bindings",
    "validate_bindings",
]
