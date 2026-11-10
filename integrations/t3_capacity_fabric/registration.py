"""Build and apply the T3 provider registration for fabric endpoints.

The registered provider is a thin Anthropic-Messages client pointed at a
fabric gateway: T3 selects a model slug, the fabric owns admission, pool
rotation and load balancing. No T3-side fallback, retry or second provider is
ever configured here, and the catalogue contains only gateway-returned ids.

T3 surface facts this builds on (verified against the T3 Code app bundle):
- ``claudeAgent`` instances take ``environment`` entries verbatim; a custom
  ``ANTHROPIC_BASE_URL`` (host != api.anthropic.com) bypasses CLI login
  gating and may be plain http loopback.
- ``config.homePath`` becomes the instance's dedicated ``CLAUDE_CONFIG_DIR``.
- ``customModels`` entries may carry ``capabilities.optionDescriptors``; an
  ``effort`` select is forwarded to the model as SDK effort.
- ``settings.json`` is live-watched: registration applies without restart.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from integrations.t3_capacity_fabric.endpoints import (
    FabricEndpoint,
    admitted_catalogue,
    fetch_catalog,
    gateway_health,
    load_proxy_token,
)
from integrations.t3_capacity_fabric import t3_config

_ACRONYMS = {"glm", "gpt", "ai", "sdk"}
_EFFORT_OPTIONS = ("low", "medium", "high", "xhigh", "max")


def model_label(model_id: str) -> str:
    """Deterministic display label, e.g. claude-opus-5-5 -> Claude Opus 5.5."""
    dotted = re.sub(r"(?<=\d)-(?=\d)", ".", model_id.replace("_", "-"))
    words = dotted.split("-")
    return " ".join(w.upper() if w.lower() in _ACRONYMS else w.capitalize()
                    for w in words if w) or model_id


def _effort_capabilities() -> dict:
    return {"optionDescriptors": [{
        "id": "effort",
        "label": "Effort",
        "type": "select",
        "role": "reasoning",
        "options": [{"id": value, "label": value.capitalize(),
                     "isDefault": value == "medium"} for value in _EFFORT_OPTIONS],
    }]}


def build_provider_instance(endpoint: FabricEndpoint, models: tuple[str, ...],
                            token: str, *, home_root: Path) -> dict:
    """One providerInstances entry for a fabric endpoint and its live catalogue."""
    if not models:
        raise ValueError(f"empty catalogue for {endpoint.endpoint_id}")
    if not token:
        raise ValueError(f"empty proxy token for {endpoint.endpoint_id}")
    home_path = home_root / f"fabric-{endpoint.endpoint_id.replace('_', '-')}"
    fast = (endpoint.preferred_fast_model if endpoint.preferred_fast_model in models
            else next((m for m in models if "haiku" in m), models[0]))
    environment = [
        {"name": "ANTHROPIC_BASE_URL", "value": endpoint.base_url},
        {"name": "ANTHROPIC_AUTH_TOKEN", "value": token, "sensitive": True},
        {"name": "ANTHROPIC_SMALL_FAST_MODEL", "value": fast},
        {"name": "ANTHROPIC_DEFAULT_HAIKU_MODEL", "value": fast},
        # Fable and gateway model ids omit task tools in recent Claude releases.
        # Keep the existing T3 plan/progress consumer supplied with native tasks.
        {"name": "CLAUDE_CODE_ENABLE_TODO_TOOLS", "value": "1"},
    ]
    custom_models = [{"slug": slug, "name": model_label(slug),
                      "capabilities": _effort_capabilities()} for slug in models]
    return {
        "driver": endpoint.driver,
        "displayName": endpoint.display_name,
        "accentColor": endpoint.accent_color,
        "environment": environment,
        "enabled": True,
        "config": {"homePath": str(home_path), "customModels": custom_models},
    }


@dataclass
class RegistrationReport:
    endpoint_id: str
    instance_id: str
    base_url: str
    health: dict
    models: tuple[str, ...] = ()
    changed: bool = False
    backup: str | None = None
    refusal: str | None = None


def _catalogue_for(endpoint: FabricEndpoint,
                   catalogues: dict[str, tuple[str, ...]] | None) -> tuple[str, ...]:
    """Only ids the fabric itself admits: the deployed list, else /v1/models."""
    if catalogues and endpoint.endpoint_id in catalogues:
        return catalogues[endpoint.endpoint_id]
    admitted = admitted_catalogue(endpoint)
    if admitted is not None:
        return admitted
    return fetch_catalog(endpoint, load_proxy_token(endpoint.env_file, endpoint.token_env_name))


def plan_registration(endpoints: tuple[FabricEndpoint, ...], *,
                      userdata: Path | None = None,
                      home_root: Path | None = None,
                      catalogues: dict[str, tuple[str, ...]] | None = None) -> list[RegistrationReport]:
    """Report what apply would write, without touching T3 configuration."""
    userdata = userdata if userdata is not None else Path.home() / ".t3" / "userdata"
    home_root = home_root if home_root is not None else Path.home() / ".t3" / "providers"
    reports = []
    for endpoint in endpoints:
        health = gateway_health(endpoint)
        report = RegistrationReport(endpoint.endpoint_id, endpoint.instance_id,
                                    endpoint.base_url, health)
        if not health["ok"]:
            report.refusal = "gateway_unhealthy"
            reports.append(report)
            continue
        try:
            models = _catalogue_for(endpoint, catalogues)
            report.models = models
            instance = build_provider_instance(
                endpoint, models, load_proxy_token(endpoint.env_file, endpoint.token_env_name),
                home_root=home_root)
            settings = t3_config.read_settings(t3_config.settings_path(userdata))
            current = settings.get("providerInstances", {}).get(endpoint.instance_id)
            report.changed = current != instance
        except (OSError, ValueError) as exc:
            report.refusal = str(exc)
        reports.append(report)
    return reports


def apply_registration(endpoints: tuple[FabricEndpoint, ...], *,
                       userdata: Path | None = None,
                       home_root: Path | None = None,
                       catalogues: dict[str, tuple[str, ...]] | None = None) -> list[RegistrationReport]:
    """Register every healthy fabric endpoint as a native T3 provider."""
    userdata = userdata if userdata is not None else Path.home() / ".t3" / "userdata"
    home_root = home_root if home_root is not None else Path.home() / ".t3" / "providers"
    settings_file = t3_config.settings_path(userdata)
    settings = t3_config.read_settings(settings_file)
    reports: list[RegistrationReport] = []
    changed = False
    for endpoint in endpoints:
        health = gateway_health(endpoint)
        report = RegistrationReport(endpoint.endpoint_id, endpoint.instance_id,
                                    endpoint.base_url, health)
        if not health["ok"]:
            report.refusal = "gateway_unhealthy"
            reports.append(report)
            continue
        try:
            token = load_proxy_token(endpoint.env_file, endpoint.token_env_name)
            models = _catalogue_for(endpoint, catalogues)
            report.models = models
            instance = build_provider_instance(endpoint, models, token,
                                               home_root=home_root)
            home_path = Path(instance["config"]["homePath"])
            home_path.mkdir(parents=True, exist_ok=True, mode=0o700)
            instance_changed = t3_config.upsert_provider_instance(
                settings, endpoint.instance_id, instance)
            report.changed = instance_changed
            changed |= instance_changed
        except (OSError, ValueError) as exc:
            report.refusal = str(exc)
        reports.append(report)
    if changed:
        t3_config.write_settings(settings_file, settings)
        for report in reports:
            if report.refusal is None:
                report.backup = str(settings_file)
    return reports


def verify_registration(endpoints: tuple[FabricEndpoint, ...], *,
                        userdata: Path | None = None) -> list[RegistrationReport]:
    """Confirm health, catalogue and stored registration for each endpoint."""
    userdata = userdata if userdata is not None else Path.home() / ".t3" / "userdata"
    settings = t3_config.read_settings(t3_config.settings_path(userdata))
    reports = []
    for endpoint in endpoints:
        health = gateway_health(endpoint)
        report = RegistrationReport(endpoint.endpoint_id, endpoint.instance_id,
                                    endpoint.base_url, health)
        instance = settings.get("providerInstances", {}).get(endpoint.instance_id)
        if not isinstance(instance, dict):
            report.refusal = "not_registered"
            reports.append(report)
            continue
        env = {e.get("name"): e.get("value") for e in instance.get("environment", [])
               if isinstance(e, dict)}
        if env.get("ANTHROPIC_BASE_URL") != endpoint.base_url:
            report.refusal = "base_url_mismatch"
            reports.append(report)
            continue
        if not env.get("ANTHROPIC_AUTH_TOKEN"):
            report.refusal = "auth_token_missing"
            reports.append(report)
            continue
        if env.get("CLAUDE_CODE_ENABLE_TODO_TOOLS") != "1":
            report.refusal = "task_tools_not_enabled"
            reports.append(report)
            continue
        try:
            report.models = _catalogue_for(endpoint, None)
            registered = tuple(m.get("slug") for m in instance.get("config", {})
                               .get("customModels", []) if isinstance(m, dict))
            if registered != report.models:
                report.refusal = "catalogue_drift"
        except (OSError, ValueError) as exc:
            report.refusal = str(exc)
        reports.append(report)
    return reports
