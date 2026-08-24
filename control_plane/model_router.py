"""Deterministic frontier-lead / economical-worker routing policy.

This module selects a *logical execution shape*.  It never creates, claims, or
completes a Job and it stores no state.  Executive OS remains the sole lifecycle
authority; worker/account selection still happens atomically in its existing
lease path.
"""
from __future__ import annotations

import dataclasses
import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.worker_adapter import adapter_descriptor


ROUTER_SCHEMA_VERSION = "mastermind.executive_worker_routes/v1"
DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "executive_worker_routes.json"
)
_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_LEAD_TASKS = frozenset({"planning", "judgment", "escalation"})
_WORKER_TASKS = frozenset(
    {"implementation", "mechanical", "tests", "research", "review"}
)
_RISKS = frozenset({"routine", "elevated", "critical"})
_AMBIGUITIES = frozenset({"low", "medium", "high"})


class RoutingPolicyError(RuntimeError):
    """The routing request or reviewed policy is invalid."""


class RouteMode(str, Enum):
    WORKER = "worker"
    FRONTIER_LEAD = "frontier_lead"


def _bounded_id(value: Any, *, field: str) -> str:
    resolved = str(value or "").strip().lower()
    if _ALIAS_RE.fullmatch(resolved) is None:
        raise RoutingPolicyError(f"{field} must be a bounded lowercase identifier")
    return resolved


def _string_list(
    value: Any, *, field: str, maximum: int = 16
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise RoutingPolicyError(f"{field} must be a list")
    if len(value) > maximum:
        raise RoutingPolicyError(f"{field} exceeds its {maximum}-item ceiling")
    result: list[str] = []
    for raw in value:
        item = str(raw or "").strip().lower()
        if not item:
            raise RoutingPolicyError(f"{field} contains an empty value")
        if item not in result:
            result.append(item)
    return tuple(result)


@dataclasses.dataclass(frozen=True)
class ProviderAlias:
    provider_alias: str
    adapter_id: str
    enabled: bool
    autonomous_allowed: bool


@dataclasses.dataclass(frozen=True)
class ModelAlias:
    model_alias: str
    provider_alias: str
    adapter_id: str
    execution_profile_id: str
    execution_profile_digest: str
    capability_policy_version: str
    capability_policy_digest: str
    model: str
    effort: str
    cost_class: str
    capabilities: tuple[str, ...]
    worker_eligible: bool


@dataclasses.dataclass(frozen=True)
class WorkRequest:
    task_kind: str
    risk: str = "routine"
    ambiguity: str = "low"
    required_capabilities: tuple[str, ...] = ()
    excluded_worker_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        task_kind = str(self.task_kind).strip().lower()
        risk = str(self.risk).strip().lower()
        ambiguity = str(self.ambiguity).strip().lower()
        if task_kind not in _WORKER_TASKS | _LEAD_TASKS:
            raise RoutingPolicyError(f"unsupported task_kind {task_kind!r}")
        if risk not in _RISKS:
            raise RoutingPolicyError(f"unsupported risk {risk!r}")
        if ambiguity not in _AMBIGUITIES:
            raise RoutingPolicyError(f"unsupported ambiguity {ambiguity!r}")
        capabilities = tuple(
            sorted(
                {
                    _bounded_id(value, field="required_capabilities")
                    for value in self.required_capabilities
                }
            )
        )
        excluded: list[str] = []
        for raw in self.excluded_worker_ids:
            worker_id = str(raw).strip()
            if _WORKER_ID_RE.fullmatch(worker_id) is None:
                raise RoutingPolicyError("excluded_worker_ids contains an invalid worker id")
            if worker_id not in excluded:
                excluded.append(worker_id)
        object.__setattr__(self, "task_kind", task_kind)
        object.__setattr__(self, "risk", risk)
        object.__setattr__(self, "ambiguity", ambiguity)
        object.__setattr__(self, "required_capabilities", capabilities)
        object.__setattr__(self, "excluded_worker_ids", tuple(excluded))


@dataclasses.dataclass(frozen=True)
class RoutingDecision:
    mode: RouteMode
    policy_version: str
    task_kind: str
    risk: str
    ambiguity: str
    execution_profile_id: str
    execution_profile_digest: str
    capability_policy_version: str
    capability_policy_digest: str
    preferred_model_aliases: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    excluded_worker_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    @property
    def worker_eligible(self) -> bool:
        return self.mode is RouteMode.WORKER

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["mode"] = self.mode.value
        value["worker_eligible"] = self.worker_eligible
        for key in (
            "preferred_model_aliases",
            "required_capabilities",
            "excluded_worker_ids",
            "reason_codes",
        ):
            value[key] = list(value[key])
        return value

    def job_constraints(self) -> dict[str, Any]:
        """Return worker-placement constraints, never raw credentials or authority."""

        if not self.worker_eligible:
            raise RoutingPolicyError(
                "frontier-lead work must be decomposed or adjudicated before worker dispatch"
            )
        return {
            "task_kind": self.task_kind,
            "risk": self.risk,
            "ambiguity": self.ambiguity,
            "execution_profile_id": self.execution_profile_id,
            "execution_profile_digest": self.execution_profile_digest,
            "capability_policy_version": self.capability_policy_version,
            "capability_policy_digest": self.capability_policy_digest,
            "preferred_model_aliases": list(self.preferred_model_aliases),
            "required_capabilities": list(self.required_capabilities),
            "excluded_worker_ids": list(self.excluded_worker_ids),
            "routing_policy_version": self.policy_version,
            "routing_reason_codes": list(self.reason_codes),
        }


class ModelRouter:
    """Loaded, validated, side-effect-free routing policy."""

    def __init__(
        self,
        *,
        policy_version: str,
        providers: Mapping[str, ProviderAlias],
        model_aliases: Mapping[str, ModelAlias],
        routes: Mapping[str, Mapping[str, Any]],
        capability_registry: ExecutionCapabilityRegistry,
        source_path: Path,
    ) -> None:
        self.policy_version = policy_version
        self.providers = dict(providers)
        self.model_aliases = dict(model_aliases)
        self.routes = {key: dict(value) for key, value in routes.items()}
        self.capability_registry = capability_registry
        self.source_path = source_path

    @classmethod
    def load(
        cls,
        path: str | Path | None = None,
        *,
        capability_policy_path: str | Path | None = None,
    ) -> "ModelRouter":
        source = Path(path or DEFAULT_POLICY_PATH).expanduser().resolve(strict=True)
        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RoutingPolicyError(f"routing policy is unreadable: {type(exc).__name__}") from exc
        if not isinstance(raw, dict):
            raise RoutingPolicyError("routing policy root must be an object")
        if raw.get("schema_version") != ROUTER_SCHEMA_VERSION:
            raise RoutingPolicyError("routing policy schema_version is unsupported")
        if raw.get("lifecycle_authority") != "executive_os":
            raise RoutingPolicyError("routing policy must preserve Executive OS lifecycle authority")
        if raw.get("production_armed") is not False:
            raise RoutingPolicyError("routing policy must remain production_armed=false")
        policy_version = _bounded_id(raw.get("policy_version"), field="policy_version")
        try:
            capability_registry = ExecutionCapabilityRegistry.load(
                capability_policy_path
            )
        except CapabilityPolicyError as exc:
            raise RoutingPolicyError(f"capability policy is invalid: {exc}") from exc

        provider_raw = raw.get("providers")
        if not isinstance(provider_raw, dict) or not provider_raw:
            raise RoutingPolicyError("routing policy requires provider aliases")
        providers: dict[str, ProviderAlias] = {}
        for name, value in provider_raw.items():
            alias = _bounded_id(name, field="provider_alias")
            if not isinstance(value, dict):
                raise RoutingPolicyError(f"provider {alias!r} must be an object")
            adapter_id = _bounded_id(value.get("adapter_id"), field="adapter_id")
            try:
                descriptor = adapter_descriptor(adapter_id)
            except ValueError as exc:
                raise RoutingPolicyError(str(exc)) from exc
            enabled = value.get("enabled") is True
            autonomous = value.get("autonomous_allowed") is True
            if (enabled or autonomous) and not descriptor.implemented:
                raise RoutingPolicyError(
                    f"provider {alias!r} cannot enable unimplemented adapter {adapter_id!r}"
                )
            if autonomous and not enabled:
                raise RoutingPolicyError(
                    f"provider {alias!r} cannot allow autonomous use while disabled"
                )
            providers[alias] = ProviderAlias(alias, adapter_id, enabled, autonomous)

        aliases_raw = raw.get("model_aliases")
        if not isinstance(aliases_raw, dict) or not aliases_raw:
            raise RoutingPolicyError("routing policy requires model_aliases")
        model_aliases: dict[str, ModelAlias] = {}
        for name, value in aliases_raw.items():
            alias = _bounded_id(name, field="model_alias")
            if not isinstance(value, dict):
                raise RoutingPolicyError(f"model alias {alias!r} must be an object")
            provider_alias = _bounded_id(
                value.get("provider_alias"), field="provider_alias"
            )
            provider = providers.get(provider_alias)
            if provider is None:
                raise RoutingPolicyError(
                    f"model alias {alias!r} names unknown provider {provider_alias!r}"
                )
            execution_profile_id = _bounded_id(
                value.get("execution_profile_id"), field="execution_profile_id"
            )
            try:
                execution_profile = capability_registry.resolve(execution_profile_id)
            except CapabilityPolicyError as exc:
                raise RoutingPolicyError(str(exc)) from exc
            model = str(value.get("model") or "").strip()
            effort = _bounded_id(value.get("effort"), field="effort")
            cost_class = _bounded_id(value.get("cost_class"), field="cost_class")
            capabilities = _string_list(
                value.get("capabilities"), field=f"model_aliases.{alias}.capabilities"
            )
            worker_eligible = value.get("worker_eligible") is True
            if not model or len(model) > 128:
                raise RoutingPolicyError(f"model alias {alias!r} has an invalid model")
            if worker_eligible and not (provider.enabled and provider.autonomous_allowed):
                raise RoutingPolicyError(
                    f"worker alias {alias!r} requires an enabled autonomous provider"
                )
            if worker_eligible and execution_profile.execution_surface not in {
                "codex-exec",
                "codex-app-server",
            }:
                raise RoutingPolicyError(
                    f"worker alias {alias!r} requires an implemented Codex execution surface"
                )
            model_aliases[alias] = ModelAlias(
                model_alias=alias,
                provider_alias=provider_alias,
                adapter_id=provider.adapter_id,
                execution_profile_id=execution_profile.profile_id,
                execution_profile_digest=execution_profile.profile_digest,
                capability_policy_version=capability_registry.policy_version,
                capability_policy_digest=capability_registry.policy_digest,
                model=model,
                effort=effort,
                cost_class=cost_class,
                capabilities=capabilities,
                worker_eligible=worker_eligible,
            )

        routes_raw = raw.get("routes")
        if not isinstance(routes_raw, dict):
            raise RoutingPolicyError("routing policy requires routes")
        routes: dict[str, dict[str, Any]] = {}
        for task_kind in sorted(_WORKER_TASKS):
            route = routes_raw.get(task_kind)
            if not isinstance(route, dict):
                raise RoutingPolicyError(f"routing policy omits {task_kind!r}")
            capabilities = _string_list(
                route.get("required_capabilities"),
                field=f"routes.{task_kind}.required_capabilities",
            )
            normalized: dict[str, Any] = {"required_capabilities": capabilities}
            for risk in ("routine", "elevated"):
                aliases = _string_list(
                    route.get(risk), field=f"routes.{task_kind}.{risk}"
                )
                if not aliases:
                    raise RoutingPolicyError(f"routes.{task_kind}.{risk} cannot be empty")
                for alias in aliases:
                    profile = model_aliases.get(alias)
                    if profile is None or not profile.worker_eligible:
                        raise RoutingPolicyError(
                            f"routes.{task_kind}.{risk} names ineligible alias {alias!r}"
                        )
                    if not set(capabilities).issubset(profile.capabilities):
                        raise RoutingPolicyError(
                            f"alias {alias!r} lacks capabilities required by {task_kind!r}"
                        )
                execution_profiles = {
                    (
                        model_aliases[alias].execution_profile_id,
                        model_aliases[alias].execution_profile_digest,
                    )
                    for alias in aliases
                }
                if len(execution_profiles) != 1:
                    raise RoutingPolicyError(
                        f"routes.{task_kind}.{risk} fallback aliases must share one execution profile"
                    )
                normalized[risk] = aliases
            routes[task_kind] = normalized
        return cls(
            policy_version=policy_version,
            providers=providers,
            model_aliases=model_aliases,
            routes=routes,
            capability_registry=capability_registry,
            source_path=source,
        )

    def resolve_model_alias(self, model_alias: str) -> ModelAlias:
        alias = _bounded_id(model_alias, field="model_alias")
        try:
            profile = self.model_aliases[alias]
        except KeyError as exc:
            raise RoutingPolicyError(f"unknown model alias {alias!r}") from exc
        if not profile.worker_eligible:
            raise RoutingPolicyError(f"model alias {alias!r} is not worker eligible")
        return profile

    def route(self, request: WorkRequest) -> RoutingDecision:
        reasons: list[str] = []
        lead_required = False
        if request.task_kind in _LEAD_TASKS:
            lead_required = True
            reasons.append(f"task_kind_{request.task_kind}")
        if request.risk == "critical":
            lead_required = True
            reasons.append("critical_risk")
        if request.ambiguity == "high":
            lead_required = True
            reasons.append("high_ambiguity")
        if lead_required:
            lead_profile = self.model_aliases["frontier.orchestrator"]
            return RoutingDecision(
                mode=RouteMode.FRONTIER_LEAD,
                policy_version=self.policy_version,
                task_kind=request.task_kind,
                risk=request.risk,
                ambiguity=request.ambiguity,
                execution_profile_id=lead_profile.execution_profile_id,
                execution_profile_digest=lead_profile.execution_profile_digest,
                capability_policy_version=lead_profile.capability_policy_version,
                capability_policy_digest=lead_profile.capability_policy_digest,
                preferred_model_aliases=("frontier.orchestrator",),
                required_capabilities=request.required_capabilities,
                excluded_worker_ids=request.excluded_worker_ids,
                reason_codes=tuple(reasons),
            )

        route = self.routes[request.task_kind]
        aliases = tuple(route[request.risk])
        first_profile = self.model_aliases[aliases[0]]
        capabilities = tuple(
            sorted(set(route["required_capabilities"]) | set(request.required_capabilities))
        )
        for alias in aliases:
            profile = self.model_aliases[alias]
            if not set(capabilities).issubset(profile.capabilities):
                raise RoutingPolicyError(
                    f"route alias {alias!r} cannot satisfy requested capabilities"
                )
        reasons.extend(
            [
                f"bounded_{request.task_kind}",
                f"risk_{request.risk}",
                "economical_worker_first",
            ]
        )
        if request.task_kind == "review" and request.excluded_worker_ids:
            reasons.append("review_worker_exclusion")
        return RoutingDecision(
            mode=RouteMode.WORKER,
            policy_version=self.policy_version,
            task_kind=request.task_kind,
            risk=request.risk,
            ambiguity=request.ambiguity,
            execution_profile_id=first_profile.execution_profile_id,
            execution_profile_digest=first_profile.execution_profile_digest,
            capability_policy_version=first_profile.capability_policy_version,
            capability_policy_digest=first_profile.capability_policy_digest,
            preferred_model_aliases=aliases,
            required_capabilities=capabilities,
            excluded_worker_ids=request.excluded_worker_ids,
            reason_codes=tuple(reasons),
        )


def route_work(
    task_kind: str,
    *,
    risk: str = "routine",
    ambiguity: str = "low",
    required_capabilities: Sequence[str] = (),
    excluded_worker_ids: Sequence[str] = (),
    policy_path: str | Path | None = None,
    capability_policy_path: str | Path | None = None,
) -> RoutingDecision:
    """Convenience entry point used by CLI and future 1F child-job creation."""

    return ModelRouter.load(
        policy_path, capability_policy_path=capability_policy_path
    ).route(
        WorkRequest(
            task_kind=task_kind,
            risk=risk,
            ambiguity=ambiguity,
            required_capabilities=tuple(required_capabilities),
            excluded_worker_ids=tuple(excluded_worker_ids),
        )
    )


__all__ = [
    "DEFAULT_POLICY_PATH",
    "ModelAlias",
    "ModelRouter",
    "ProviderAlias",
    "ROUTER_SCHEMA_VERSION",
    "RouteMode",
    "RoutingDecision",
    "RoutingPolicyError",
    "WorkRequest",
    "route_work",
]
