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
    from control_plane.executive_runtime import WorkerQuotaClass

SCHEMA = "mastermind.fabric_attended_route/v1"
FINITE_DEFINITION_DIR = '/Library/Application Support/MastermindExecutive/config/fabric-minimax-finite-01'
FINITE_SOCKET_PATH = '/var/run/mastermind-executive/fabric-minimax-finite-01.sock'
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
class AttendedQualification:
    """Fixed-host restriction to one exact request, never an admission grant.

    This may select the prepromotion finite path. The original authenticated
    foreground owner must match it before admission and every driven cycle.
    No JSON, environment or RPC field can select this host configuration.
    """

    operation_key: str
    arguments_sha256: str

    def __post_init__(self):
        from control_plane.ceo_request import app_request_ref
        app_request_ref(self.operation_key)
        if type(self.arguments_sha256) is not str or _DIGEST.fullmatch(self.arguments_sha256) is None:
            raise ValueError("qualification requires exact normalized request digest")


@dataclasses.dataclass(frozen=True)
class AttendedWorkPlacement:
    """Host configuration only; no Worker or capacity row is created here."""

    model_alias: str
    harness_binding_id: str
    quota_class: str
    qualification: AttendedQualification | None = None

    def __post_init__(self) -> None:
        for value in (self.model_alias, self.harness_binding_id, self.quota_class):
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise ValueError("attended placement requires exact bounded identifiers")
        if self.qualification is not None and type(self.qualification) is not AttendedQualification:
            raise ValueError("qualification requires fixed typed host configuration")


def qualification_for(placements):
    """One finite qualification cannot be mixed with ordinary placements."""
    selected = [p.qualification for p in placements if p.qualification is not None]
    if selected and (len(selected) != 1 or len(placements) != 1):
        raise ValueError("qualification requires exactly one attended placement")
    return selected[0] if selected else None


def installed_control_placements(raw):
    """Fixed source composition for the one original-parent finite proof.

    Called only by the installed Control wrapper. Existing protected config
    and its owner-produced autonomy receipt govern activation; no JSON, argv,
    environment or model output supplies a placement or operation selector.
    Merely staging definitions while disarmed retains ordinary startup.
    This does not register a worker/quota or qualify any host resource.
    """
    if 'fabric_attended_probe' not in raw:
        return ()
    from scripts.executive_os_phase1c import _validate_fabric_bridge_config
    _validate_fabric_bridge_config(raw)
    if (raw.get('coo_autonomy_armed', False) is False
            and raw.get('coo_foreground_only', False) is False):
        return ()
    if (raw.get('coo_autonomy_armed') is not True
            or raw.get('coo_foreground_only') is not True
            or raw.get('coo_operator_model_alias') != 'coo.operator.readonly'
            or raw.get('fabric_bindings_path') != FINITE_DEFINITION_DIR + '/bindings.json'
            or raw['fabric_attended_probe']['worker_config_path'] != FINITE_DEFINITION_DIR + '/worker.json'):
        raise ValueError('installed finite composition requires original foreground-only owner')
    return (AttendedWorkPlacement(
        'minimax.attended', 'minimax-token-plan.claude-code-anthropic', 'minimax-finite-read',
        qualification=AttendedQualification(
            'fabric-parent-native-operator-proof-01a11e90-v1',
            '36678c742b06b0ce04aa2b6acc46cb8aba9eba82c322ca960611e2cbb2580f56')),)


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
    return _resolve_attended_alias(router, alias_name, binding_id)


def _resolve_attended_alias(router, alias_name, binding_id, *, qualification=None):
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
        if qualification is None:
            if not provider.enabled or not descriptor.implemented:
                raise ValueError("attended alias requires an implemented nonautonomous provider")
        elif (type(qualification) is not AttendedQualification
                or alias_name != "minimax.attended" or alias.provider_alias != "minimax"
                or binding_id != "minimax-token-plan.claude-code-anthropic"
                or alias.model != "MiniMax-M3" or provider.enabled
                or descriptor.implemented or binding.implementation_state != "BUILT_NOT_PROVEN"):
            raise ValueError("qualification requires the exact unpromoted finite catalogue")
        if (alias.worker_eligible or provider.autonomous_allowed
                or alias.adapter_id != "attended-fabric"
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
    alias, route = _resolve_attended_alias(router, placement.model_alias,
        placement.harness_binding_id, qualification=placement.qualification)
    return {"provider_realm": alias.provider_alias, "quota_class": placement.quota_class,
            "attended_route": route}


def attended_launch_model(constraints: Mapping[str, Any], quota: WorkerQuotaClass) -> str:
    """Restore exact catalogue case only after matching the claimed route.

    Runtime intentionally canonicalizes its scalar selectors to lowercase.
    The retained closed route preserves the provider's exact launch spelling;
    neither that spelling nor this compiler grants permission to START.
    """
    route = normalize_attended_route(constraints.get("attended_route"))
    claimed = normalize_attended_route(quota.metadata.get("attended_route"))
    if route != claimed:
        raise ValueError("claimed quota catalogue differs from the Job")
    if quota.provider != route["provider_alias"] or constraints.get("provider") != quota.provider:
        raise ValueError("claimed quota provider differs from the attended route")
    for key in ("model", "effort", "cost_class"):
        expected = route[key].lower()
        if getattr(quota, key) != expected or constraints.get(key) != expected:
            raise ValueError(f"claimed quota {key} differs from the attended route")
    return route["model"]
