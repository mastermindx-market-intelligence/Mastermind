"""Finite attended catalogue projection; never admission or presence proof.

Ordinary worker eligibility continues to mean autonomous eligibility. This
separate resolver only supplies a host-reviewed plan placement. Fresh claim
and START still require the live foreground owner and qualified worker realm.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from control_plane.fabric_attended_claude import CONTRACT_NAME
from control_plane.subscription_catalog import compose_catalog_digest
from control_plane.subscription_harness_bindings import get_binding, load_bindings
from control_plane.subscription_provider_profiles import get_profile, load_profiles
from control_plane.worker_adapter import adapter_descriptor

if TYPE_CHECKING:
    from control_plane.model_router import ModelAlias, ModelRouter

SCHEMA = "mastermind.fabric_attended_route/v1"
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_DIGEST = re.compile(r"^[a-f0-9]{64}$")
_KEYS = frozenset({
    "schema", "model_alias", "provider_alias", "adapter_id", "harness_binding_id",
    "subscription_catalog_digest", "model", "effort", "cost_class",
    "routing_policy_version", "execution_profile_id", "execution_profile_digest",
    "capability_policy_version", "capability_policy_digest",
})
_DIGEST_KEYS = frozenset({
    "subscription_catalog_digest", "execution_profile_digest", "capability_policy_digest",
})


@dataclasses.dataclass(frozen=True)
class AttendedWorkPlacement:
    """Host configuration only; no Worker or capacity row is created here."""

    model_alias: str
    harness_binding_id: str
    quota_class: str

    def __post_init__(self) -> None:
        for value in dataclasses.astuple(self):
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise ValueError("attended placement requires exact bounded identifiers")


def normalize_attended_route(value: Any) -> dict[str, str]:
    """Validate retained identity, not permission to use it."""
    if not isinstance(value, Mapping) or set(value) != _KEYS:
        raise ValueError("attended route must carry the complete closed identity")
    route = dict(value)
    for key, item in route.items():
        if not isinstance(item, str) or not item or item != item.strip():
            raise ValueError("attended route values must be exact nonempty strings")
        if key in _DIGEST_KEYS:
            valid = _DIGEST.fullmatch(item) is not None
        elif key == "model":
            valid = re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", item) is not None
        elif key == "schema":
            valid = item == SCHEMA
        else:
            valid = _IDENTIFIER.fullmatch(item) is not None
        if not valid:
            raise ValueError(f"invalid attended route {key}")
    if (route["adapter_id"] != "attended-fabric"
            or route["execution_profile_id"] != CONTRACT_NAME):
        raise ValueError("attended route requires the finite Fabric profile")
    return route


def resolve_attended_alias(router: ModelRouter, alias_name: str,
                           binding_id: str) -> tuple[ModelAlias, dict[str, str]]:
    from control_plane.model_router import RoutingPolicyError

    try:
        alias = router.model_aliases[alias_name]
        provider = router.providers[alias.provider_alias]
        descriptor = adapter_descriptor(alias.adapter_id)
        execution = router.capability_registry.resolve(alias.execution_profile_id)
        # Read each protected catalogue once and bind both resolution and digest
        # to those same bytes. A later reread is the dispatch owner's obligation.
        profiles = load_profiles()
        bindings = load_bindings(profiles_document=profiles)
        binding = get_binding(binding_id, document=bindings, profiles_document=profiles)
        profile = get_profile(binding.profile_id, document=profiles)
        if (alias.worker_eligible or not provider.enabled or provider.autonomous_allowed
                or alias.adapter_id != "attended-fabric" or not descriptor.implemented
                or binding.autonomous_allowed or profile.autonomous_allowed):
            raise ValueError("attended alias requires an implemented nonautonomous provider")
        if (execution.profile_id != CONTRACT_NAME
                or execution.execution_surface != "claude-code"
                or execution.auth_realm != "dedicated-worker-account"
                or execution.sandbox_policy != "read-only" or execution.write_capable
                or execution.approval_policy != "never" or execution.network_policy != "disabled"
                or execution.native_helper_policy.value != "DISABLED"
                or execution.native_helper is not None or execution.skills
                or execution.mcp_servers or execution.plugins or execution.resource_grants):
            raise ValueError("attended alias requires the closed READ-only execution profile")
        if (binding.provider != alias.provider_alias or profile.provider != alias.provider_alias
                or binding.harness_id != "claude-code" or binding.protocol != "anthropic"
                or profile.protocol != "anthropic"
                or binding.adapter_id != "claude-compatible-subscription"
                or binding.effective_base_url != profile.base_url
                or alias.model not in {binding.model_for(profile, k) for k in binding.model_classes}):
            raise ValueError("attended alias differs from its supported harness or exact model")
        expected_usage = {"supported_harness_required": True, "interactive_only": True,
                          "unattended_background_allowed": False, "production_backend_allowed": False}
        if any(profile.usage_policy.get(k) is not v for k, v in expected_usage.items()):
            raise ValueError("attended alias requires the reviewed foreground usage restrictions")
        if (alias.execution_profile_digest != execution.profile_digest
                or alias.capability_policy_version != router.capability_registry.policy_version
                or alias.capability_policy_digest != router.capability_registry.policy_digest):
            raise ValueError("attended alias execution policy drifted")
        route = {key: getattr(alias, key) for key in (
            "model_alias", "provider_alias", "adapter_id", "model", "effort", "cost_class", "execution_profile_id",
            "execution_profile_digest", "capability_policy_version", "capability_policy_digest")}
        route.update(schema=SCHEMA, routing_policy_version=router.policy_version,
                     harness_binding_id=binding_id, subscription_catalog_digest=compose_catalog_digest(
                         profiles_document=profiles, bindings_document=bindings))
        return alias, normalize_attended_route(route)
    except (KeyError, ValueError) as exc:
        raise RoutingPolicyError(f"attended model alias refused: {exc}") from exc


def placement_member(router: ModelRouter, placement: AttendedWorkPlacement) -> dict[str, Any]:
    if type(placement) is not AttendedWorkPlacement:
        raise ValueError("attended work placement must be host configuration")
    alias, route = resolve_attended_alias(router, placement.model_alias, placement.harness_binding_id)
    return {"provider_realm": alias.provider_alias, "quota_class": placement.quota_class,
            "attended_route": route}
