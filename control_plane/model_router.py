"""Deterministic frontier-lead / economical-worker routing policy.

This module selects a *logical execution shape*. It never creates, claims, or
completes a Job and it stores no state. Executive OS remains the sole lifecycle
authority; worker/account selection still happens atomically in its existing
lease path.
"""
from __future__ import annotations

import dataclasses
import json
import math
import re
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from control_plane.executive_agent_capabilities import (
    CapabilityPolicyError,
    ExecutionCapabilityRegistry,
)
from control_plane.worker_adapter import adapter_descriptor


ROUTER_SCHEMA_VERSION = "mastermind.executive_worker_routes/v2"
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
_METERED_TEXT_MAX = 2048
_PRO_MODE_MIN_DURATION_MINUTES = 80
_PRO_MODE_MAX_DURATION_MINUTES = 1440
_PRO_MODE_REFUSAL = "PRO_MODE_REFUSED / USE_NON_PRO_MODE"
_METERED_ROUTE_REFUSAL = "METERED_ROUTE_REFUSED / WAITING_FOR_LAWFUL_ROUTE"


class RoutingPolicyError(RuntimeError):
    """The routing request or reviewed policy is invalid."""


class RouteMode(str, Enum):
    WORKER = "worker"
    FRONTIER_LEAD = "frontier_lead"


class CognitionRoute(str, Enum):
    """Economic route for Sol-class cognition; never lifecycle authority."""

    CHAT_INCLUDED_DEFAULT = "CHAT_INCLUDED_DEFAULT"
    METERED_EXCEPTION = "METERED_EXCEPTION"


class ChatReasoningMode(str, Enum):
    """Reasoning mode within the included Chat web surface."""

    NON_PRO_DEFAULT = "NON_PRO_DEFAULT"
    PRO_MODE_EXCEPTION = "PRO_MODE_EXCEPTION"


class ProModeTaskClass(str, Enum):
    """Narrow classes that can justify billed Chat Pro reasoning."""

    LONG_HORIZON_FRONTIER_REASONING = "LONG_HORIZON_FRONTIER_REASONING"
    CROSS_SYSTEM_ARCHITECTURE = "CROSS_SYSTEM_ARCHITECTURE"
    HARD_DEBUGGING = "HARD_DEBUGGING"
    ADVERSARIAL_JUDGMENT = "ADVERSARIAL_JUDGMENT"


_PRO_MODE_TASK_CLASSES_BY_KIND = {
    "planning": frozenset(
        {
            ProModeTaskClass.LONG_HORIZON_FRONTIER_REASONING,
            ProModeTaskClass.CROSS_SYSTEM_ARCHITECTURE,
        }
    ),
    "judgment": frozenset(
        {
            ProModeTaskClass.LONG_HORIZON_FRONTIER_REASONING,
            ProModeTaskClass.CROSS_SYSTEM_ARCHITECTURE,
            ProModeTaskClass.ADVERSARIAL_JUDGMENT,
        }
    ),
    "escalation": frozenset(
        {
            ProModeTaskClass.CROSS_SYSTEM_ARCHITECTURE,
            ProModeTaskClass.HARD_DEBUGGING,
            ProModeTaskClass.ADVERSARIAL_JUDGMENT,
        }
    ),
    "implementation": frozenset(
        {
            ProModeTaskClass.CROSS_SYSTEM_ARCHITECTURE,
            ProModeTaskClass.HARD_DEBUGGING,
        }
    ),
    "research": frozenset(
        {ProModeTaskClass.LONG_HORIZON_FRONTIER_REASONING}
    ),
    "review": frozenset({ProModeTaskClass.ADVERSARIAL_JUDGMENT}),
}


def _bounded_id(value: Any, *, field: str) -> str:
    resolved = str(value or "").strip().lower()
    if _ALIAS_RE.fullmatch(resolved) is None:
        raise RoutingPolicyError(f"{field} must be a bounded lowercase identifier")
    return resolved


def _bounded_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise RoutingPolicyError(
            f"{field} must be a non-empty string no longer than "
            f"{_METERED_TEXT_MAX} characters"
        )
    resolved = value.strip()
    if not resolved or len(resolved) > _METERED_TEXT_MAX:
        raise RoutingPolicyError(
            f"{field} must be a non-empty string no longer than {_METERED_TEXT_MAX} characters"
        )
    return resolved


def _bounded_cost(value: Any, *, field: str, strictly_positive: bool) -> float:
    if isinstance(value, bool):
        raise RoutingPolicyError(f"{field} must be a finite number")
    try:
        resolved = float(value)
    except (TypeError, ValueError) as exc:
        raise RoutingPolicyError(f"{field} must be a finite number") from exc
    if not math.isfinite(resolved):
        raise RoutingPolicyError(f"{field} must be a finite number")
    if strictly_positive:
        if resolved <= 0:
            raise RoutingPolicyError(f"{field} must be greater than zero")
    elif resolved < 0:
        raise RoutingPolicyError(f"{field} cannot be negative")
    return resolved


def _coerce_cognition_route(value: CognitionRoute | str) -> CognitionRoute:
    if isinstance(value, CognitionRoute):
        return value
    rendered = str(value or "").strip().upper()
    try:
        return CognitionRoute(rendered)
    except ValueError as exc:
        raise RoutingPolicyError(f"unsupported cognition_route {rendered!r}") from exc


def _coerce_chat_reasoning_mode(
    value: ChatReasoningMode | str,
) -> ChatReasoningMode:
    if isinstance(value, ChatReasoningMode):
        return value
    rendered = str(value or "").strip().upper()
    try:
        return ChatReasoningMode(rendered)
    except ValueError as exc:
        raise RoutingPolicyError(
            f"unsupported chat_reasoning_mode {rendered!r}"
        ) from exc


def _coerce_pro_mode_task_class(
    value: ProModeTaskClass | str,
) -> ProModeTaskClass:
    if isinstance(value, ProModeTaskClass):
        return value
    rendered = str(value or "").strip().upper()
    try:
        return ProModeTaskClass(rendered)
    except ValueError as exc:
        raise RoutingPolicyError(
            f"{_PRO_MODE_REFUSAL}: unsupported task_class {rendered!r}"
        ) from exc


def _bounded_pro_mode_text(value: Any, *, field: str) -> str:
    try:
        return _bounded_text(value, field=field)
    except RoutingPolicyError as exc:
        raise RoutingPolicyError(f"{_PRO_MODE_REFUSAL}: {exc}") from exc


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
class SuitabilityTier:
    """One ordered equivalence class of already-lawful worker aliases."""

    tier_id: str
    model_aliases: tuple[str, ...]

    def __post_init__(self) -> None:
        tier_id = _bounded_id(self.tier_id, field="tier_id")
        if not isinstance(self.model_aliases, tuple) or not self.model_aliases:
            raise RoutingPolicyError("model_aliases must be a non-empty tuple")
        aliases: list[str] = []
        for raw_alias in self.model_aliases:
            alias = _bounded_id(raw_alias, field="model_aliases")
            if alias in aliases:
                raise RoutingPolicyError(
                    f"model_aliases contains duplicate alias {alias!r}"
                )
            aliases.append(alias)
        object.__setattr__(self, "tier_id", tier_id)
        object.__setattr__(self, "model_aliases", tuple(aliases))

    def to_dict(self) -> dict[str, object]:
        return {"tier_id": self.tier_id, "model_aliases": list(self.model_aliases)}


def _tier_aliases(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise RoutingPolicyError(f"{field} must be a list")
    if not value:
        raise RoutingPolicyError(f"{field} cannot be empty")
    if len(value) > 16:
        raise RoutingPolicyError(f"{field} exceeds its 16-item ceiling")
    aliases: list[str] = []
    for raw_alias in value:
        alias = _bounded_id(raw_alias, field=field)
        if alias in aliases:
            raise RoutingPolicyError(f"{field} contains duplicate alias {alias!r}")
        aliases.append(alias)
    return tuple(aliases)


def _parse_suitability_tiers(
    value: Any,
    *,
    field: str,
    model_aliases: Mapping[str, ModelAlias],
    required_capabilities: tuple[str, ...],
) -> tuple[SuitabilityTier, ...]:
    if not isinstance(value, (list, tuple)):
        raise RoutingPolicyError(f"{field} must be a list")
    if not value:
        raise RoutingPolicyError(f"{field} cannot be empty")
    if len(value) > 16:
        raise RoutingPolicyError(f"{field} exceeds its 16-item ceiling")

    tiers: list[SuitabilityTier] = []
    seen_tier_ids: set[str] = set()
    seen_aliases: set[str] = set()
    expected_keys = {"tier_id", "model_aliases"}
    for index, raw_tier in enumerate(value):
        item_field = f"{field}[{index}]"
        if not isinstance(raw_tier, dict):
            raise RoutingPolicyError(f"{item_field} must be an object")
        unknown_keys = set(raw_tier) - expected_keys
        if unknown_keys:
            raise RoutingPolicyError(
                f"{item_field} contains unknown keys {sorted(unknown_keys)!r}"
            )
        missing_keys = expected_keys - set(raw_tier)
        if missing_keys:
            raise RoutingPolicyError(
                f"{item_field} omits required keys {sorted(missing_keys)!r}"
            )
        tier_id = _bounded_id(raw_tier["tier_id"], field=f"{item_field}.tier_id")
        if tier_id in seen_tier_ids:
            raise RoutingPolicyError(f"{field} contains duplicate tier_id {tier_id!r}")
        aliases = _tier_aliases(
            raw_tier["model_aliases"], field=f"{item_field}.model_aliases"
        )
        execution_profiles: set[tuple[str, str]] = set()
        for alias in aliases:
            profile = model_aliases.get(alias)
            if profile is None or not profile.worker_eligible:
                raise RoutingPolicyError(
                    f"{field} names ineligible alias {alias!r}"
                )
            if not set(required_capabilities).issubset(profile.capabilities):
                raise RoutingPolicyError(
                    f"alias {alias!r} lacks capabilities required by {field!r}"
                )
            if alias in seen_aliases:
                raise RoutingPolicyError(f"{field} contains duplicate alias {alias!r}")
            execution_profiles.add(
                (profile.execution_profile_id, profile.execution_profile_digest)
            )
        if len(execution_profiles) != 1:
            raise RoutingPolicyError(
                f"{item_field} aliases must share one execution profile"
            )
        seen_tier_ids.add(tier_id)
        seen_aliases.update(aliases)
        tiers.append(SuitabilityTier(tier_id, aliases))
    return tuple(tiers)


@dataclasses.dataclass(frozen=True)
class MeteredCognitionReceipt:
    """Bounded evidence required before a paid Sol-cognition exception."""

    why_metered: str
    why_pro_chat_insufficient: str
    expected_max_cost: float
    hard_budget_cap: float
    stop_condition: str
    budget_authority: str

    def __post_init__(self) -> None:
        why_metered = _bounded_text(self.why_metered, field="why_metered")
        why_pro_chat_insufficient = _bounded_text(
            self.why_pro_chat_insufficient,
            field="why_pro_chat_insufficient",
        )
        stop_condition = _bounded_text(self.stop_condition, field="stop_condition")
        budget_authority = _bounded_text(
            self.budget_authority, field="budget_authority"
        )
        expected_max_cost = _bounded_cost(
            self.expected_max_cost,
            field="expected_max_cost",
            strictly_positive=False,
        )
        hard_budget_cap = _bounded_cost(
            self.hard_budget_cap,
            field="hard_budget_cap",
            strictly_positive=True,
        )
        if expected_max_cost > hard_budget_cap:
            raise RoutingPolicyError(
                "expected_max_cost cannot exceed hard_budget_cap"
            )
        object.__setattr__(self, "why_metered", why_metered)
        object.__setattr__(
            self, "why_pro_chat_insufficient", why_pro_chat_insufficient
        )
        object.__setattr__(self, "expected_max_cost", expected_max_cost)
        object.__setattr__(self, "hard_budget_cap", hard_budget_cap)
        object.__setattr__(self, "stop_condition", stop_condition)
        object.__setattr__(self, "budget_authority", budget_authority)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class ProModeReceipt:
    """Bounded evidence required before billed Chat Pro reasoning."""

    task_class: ProModeTaskClass | str
    why_pro_mode: str
    why_non_pro_insufficient: str
    expected_duration_minutes: int
    stop_condition: str

    def __post_init__(self) -> None:
        task_class = _coerce_pro_mode_task_class(self.task_class)
        why_pro_mode = _bounded_pro_mode_text(
            self.why_pro_mode,
            field="why_pro_mode",
        )
        why_non_pro_insufficient = _bounded_pro_mode_text(
            self.why_non_pro_insufficient,
            field="why_non_pro_insufficient",
        )
        stop_condition = _bounded_pro_mode_text(
            self.stop_condition,
            field="stop_condition",
        )
        duration = self.expected_duration_minutes
        if isinstance(duration, bool) or not isinstance(duration, int):
            raise RoutingPolicyError(
                f"{_PRO_MODE_REFUSAL}: expected_duration_minutes must be an integer"
            )
        if not (
            _PRO_MODE_MIN_DURATION_MINUTES
            <= duration
            <= _PRO_MODE_MAX_DURATION_MINUTES
        ):
            raise RoutingPolicyError(
                f"{_PRO_MODE_REFUSAL}: expected_duration_minutes must be between "
                f"{_PRO_MODE_MIN_DURATION_MINUTES} and "
                f"{_PRO_MODE_MAX_DURATION_MINUTES}"
            )
        object.__setattr__(self, "task_class", task_class)
        object.__setattr__(self, "why_pro_mode", why_pro_mode)
        object.__setattr__(
            self,
            "why_non_pro_insufficient",
            why_non_pro_insufficient,
        )
        object.__setattr__(self, "stop_condition", stop_condition)

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["task_class"] = self.task_class.value
        return value


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
                raise RoutingPolicyError(
                    "excluded_worker_ids contains an invalid worker id"
                )
            if worker_id not in excluded:
                excluded.append(worker_id)
        object.__setattr__(self, "task_kind", task_kind)
        object.__setattr__(self, "risk", risk)
        object.__setattr__(self, "ambiguity", ambiguity)
        object.__setattr__(self, "required_capabilities", capabilities)
        object.__setattr__(self, "excluded_worker_ids", tuple(excluded))


@dataclasses.dataclass(frozen=True)
class _RoutingDecisionCompatibility:
    """Preserve the inspected v1 field name without accepting a flat input."""

    preferred_model_aliases: tuple[str, ...] = dataclasses.field(init=False)


@dataclasses.dataclass(frozen=True)
class RoutingDecision(_RoutingDecisionCompatibility):
    mode: RouteMode
    policy_version: str
    task_kind: str
    risk: str
    ambiguity: str
    execution_profile_id: str
    execution_profile_digest: str
    capability_policy_version: str
    capability_policy_digest: str
    suitability_tiers: tuple[SuitabilityTier, ...]
    required_capabilities: tuple[str, ...]
    excluded_worker_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    cognition_route: CognitionRoute | None = None
    chat_reasoning_mode: ChatReasoningMode | None = None
    metered_cognition_receipt: MeteredCognitionReceipt | None = None
    pro_mode_receipt: ProModeReceipt | None = None

    @property
    def worker_eligible(self) -> bool:
        return self.mode is RouteMode.WORKER

    @property
    def preferred_model_aliases(self) -> tuple[str, ...]:
        """Compatibility projection for existing persisted Job constraints."""

        if not self.suitability_tiers:
            return ()
        return self.suitability_tiers[0].model_aliases

    def to_dict(self) -> dict[str, Any]:
        value = dataclasses.asdict(self)
        value["mode"] = self.mode.value
        value["worker_eligible"] = self.worker_eligible
        value["suitability_tiers"] = [
            tier.to_dict() for tier in self.suitability_tiers
        ]
        value["preferred_model_aliases"] = list(self.preferred_model_aliases)
        value["cognition_route"] = (
            self.cognition_route.value if self.cognition_route is not None else None
        )
        value["chat_reasoning_mode"] = (
            self.chat_reasoning_mode.value
            if self.chat_reasoning_mode is not None
            else None
        )
        value["metered_cognition_receipt"] = (
            self.metered_cognition_receipt.to_dict()
            if self.metered_cognition_receipt is not None
            else None
        )
        value["pro_mode_receipt"] = (
            self.pro_mode_receipt.to_dict()
            if self.pro_mode_receipt is not None
            else None
        )
        for key in (
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
            raise RoutingPolicyError(
                f"routing policy is unreadable: {type(exc).__name__}"
            ) from exc
        if not isinstance(raw, dict):
            raise RoutingPolicyError("routing policy root must be an object")
        if raw.get("schema_version") != ROUTER_SCHEMA_VERSION:
            raise RoutingPolicyError("routing policy schema_version is unsupported")
        if raw.get("lifecycle_authority") != "executive_os":
            raise RoutingPolicyError(
                "routing policy must preserve Executive OS lifecycle authority"
            )
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
                value.get("capabilities"),
                field=f"model_aliases.{alias}.capabilities",
            )
            worker_eligible = value.get("worker_eligible") is True
            if not model or len(model) > 128:
                raise RoutingPolicyError(
                    f"model alias {alias!r} has an invalid model"
                )
            if worker_eligible and not (
                provider.enabled and provider.autonomous_allowed
            ):
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
        unknown_task_kinds = set(routes_raw) - _WORKER_TASKS
        if unknown_task_kinds:
            raise RoutingPolicyError(
                "routing policy contains unknown route keys "
                f"{sorted(unknown_task_kinds)!r}"
            )
        routes: dict[str, dict[str, Any]] = {}
        for task_kind in sorted(_WORKER_TASKS):
            route = routes_raw.get(task_kind)
            if not isinstance(route, dict):
                raise RoutingPolicyError(f"routing policy omits {task_kind!r}")
            expected_route_keys = {"required_capabilities", "routine", "elevated"}
            unknown_route_keys = set(route) - expected_route_keys
            if unknown_route_keys:
                raise RoutingPolicyError(
                    f"routes.{task_kind} contains unknown keys "
                    f"{sorted(unknown_route_keys)!r}"
                )
            missing_route_keys = expected_route_keys - set(route)
            if missing_route_keys:
                raise RoutingPolicyError(
                    f"routes.{task_kind} omits required keys "
                    f"{sorted(missing_route_keys)!r}"
                )
            capabilities = _string_list(
                route.get("required_capabilities"),
                field=f"routes.{task_kind}.required_capabilities",
            )
            normalized: dict[str, Any] = {"required_capabilities": capabilities}
            for risk in ("routine", "elevated"):
                normalized[risk] = _parse_suitability_tiers(
                    route[risk],
                    field=f"routes.{task_kind}.{risk}",
                    model_aliases=model_aliases,
                    required_capabilities=capabilities,
                )
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

    def route(
        self,
        request: WorkRequest,
        *,
        cognition_route: CognitionRoute | str | None = None,
        chat_reasoning_mode: ChatReasoningMode | str | None = None,
        metered_cognition_receipt: MeteredCognitionReceipt | None = None,
        pro_mode_receipt: ProModeReceipt | None = None,
    ) -> RoutingDecision:
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
            resolved_cognition_route = (
                CognitionRoute.CHAT_INCLUDED_DEFAULT
                if cognition_route is None
                else _coerce_cognition_route(cognition_route)
            )
            resolved_chat_reasoning_mode: ChatReasoningMode | None = None
            if resolved_cognition_route is CognitionRoute.METERED_EXCEPTION:
                if chat_reasoning_mode is not None or pro_mode_receipt is not None:
                    raise RoutingPolicyError(
                        f"{_METERED_ROUTE_REFUSAL}: metered cognition cannot carry "
                        "Chat reasoning mode or Pro receipt fields"
                    )
                if not isinstance(
                    metered_cognition_receipt, MeteredCognitionReceipt
                ):
                    raise RoutingPolicyError(
                        f"{_METERED_ROUTE_REFUSAL}: "
                        "a complete metered cognition receipt is required"
                    )
                reasons.append("metered_exception_receipt_complete")
            else:
                if metered_cognition_receipt is not None:
                    raise RoutingPolicyError(
                        "CHAT_INCLUDED_DEFAULT cannot carry a metered receipt"
                    )
                resolved_chat_reasoning_mode = (
                    ChatReasoningMode.NON_PRO_DEFAULT
                    if chat_reasoning_mode is None
                    else _coerce_chat_reasoning_mode(chat_reasoning_mode)
                )
                reasons.append("chat_included_default")
                if (
                    resolved_chat_reasoning_mode
                    is ChatReasoningMode.PRO_MODE_EXCEPTION
                ):
                    if request.task_kind in {"mechanical", "tests"}:
                        raise RoutingPolicyError(
                            f"{_PRO_MODE_REFUSAL}: {request.task_kind} work is never "
                            "eligible for Pro mode"
                        )
                    if not isinstance(pro_mode_receipt, ProModeReceipt):
                        raise RoutingPolicyError(
                            f"{_PRO_MODE_REFUSAL}: a complete Pro mode receipt is required"
                        )
                    allowed_classes = _PRO_MODE_TASK_CLASSES_BY_KIND.get(
                        request.task_kind,
                        frozenset(),
                    )
                    if pro_mode_receipt.task_class not in allowed_classes:
                        raise RoutingPolicyError(
                            f"{_PRO_MODE_REFUSAL}: task_class "
                            f"{pro_mode_receipt.task_class.value!r} is not coherent "
                            f"with task_kind {request.task_kind!r}"
                        )
                    reasons.append("pro_mode_exception_receipt_complete")
                else:
                    if pro_mode_receipt is not None:
                        raise RoutingPolicyError(
                            f"{_PRO_MODE_REFUSAL}: NON_PRO_DEFAULT cannot carry a "
                            "Pro mode receipt"
                        )
                    reasons.append("non_pro_default")

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
                suitability_tiers=(
                    SuitabilityTier(
                        "frontier.lead", ("frontier.orchestrator",)
                    ),
                ),
                required_capabilities=request.required_capabilities,
                excluded_worker_ids=request.excluded_worker_ids,
                reason_codes=tuple(reasons),
                cognition_route=resolved_cognition_route,
                chat_reasoning_mode=resolved_chat_reasoning_mode,
                metered_cognition_receipt=metered_cognition_receipt,
                pro_mode_receipt=pro_mode_receipt,
            )

        if pro_mode_receipt is not None:
            raise RoutingPolicyError(
                f"{_PRO_MODE_REFUSAL}: a Pro receipt cannot be attached to worker work"
            )
        if chat_reasoning_mode is not None:
            resolved_worker_chat_mode = _coerce_chat_reasoning_mode(
                chat_reasoning_mode
            )
            if resolved_worker_chat_mode is ChatReasoningMode.PRO_MODE_EXCEPTION:
                raise RoutingPolicyError(
                    f"{_PRO_MODE_REFUSAL}: worker work is not eligible for Pro mode"
                )
        if (
            cognition_route is not None
            or chat_reasoning_mode is not None
            or metered_cognition_receipt is not None
        ):
            raise RoutingPolicyError(
                "worker work does not accept Sol cognition route, Chat reasoning mode, "
                "or receipt fields"
            )

        route = self.routes[request.task_kind]
        suitability_tiers = tuple(route[request.risk])
        first_profile = self.model_aliases[
            suitability_tiers[0].model_aliases[0]
        ]
        capabilities = tuple(
            sorted(
                set(route["required_capabilities"])
                | set(request.required_capabilities)
            )
        )
        for tier in suitability_tiers:
            for alias in tier.model_aliases:
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
            suitability_tiers=suitability_tiers,
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
    cognition_route: CognitionRoute | str | None = None,
    chat_reasoning_mode: ChatReasoningMode | str | None = None,
    metered_cognition_receipt: MeteredCognitionReceipt | None = None,
    pro_mode_receipt: ProModeReceipt | None = None,
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
        ),
        cognition_route=cognition_route,
        chat_reasoning_mode=chat_reasoning_mode,
        metered_cognition_receipt=metered_cognition_receipt,
        pro_mode_receipt=pro_mode_receipt,
    )


__all__ = [
    "ChatReasoningMode",
    "CognitionRoute",
    "DEFAULT_POLICY_PATH",
    "MeteredCognitionReceipt",
    "ModelAlias",
    "ModelRouter",
    "ProModeReceipt",
    "ProModeTaskClass",
    "ProviderAlias",
    "ROUTER_SCHEMA_VERSION",
    "RouteMode",
    "RoutingDecision",
    "RoutingPolicyError",
    "SuitabilityTier",
    "WorkRequest",
    "route_work",
]
