"""Render OpenAI-compatible Hermes provider overlays for mmsecretary and mmmeta.

The qualification YAML stays the disarmed preflight document. These overlays
are a separate Hermes ``providers:`` config: key_env names only, chat_completions
transport, and no ``fallback_model`` (that Hermes feature would replay 429s).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from integrations.hermes_models.contract import (
    API_MODE,
    OVERLAY_SCHEMA,
    PROFILE_PRIMARY,
    PROVIDERS,
    UPSTREAM_HERMES_SHA,
    ProviderSpec,
    provider,
)


_QUALIFICATION = (
    Path(__file__).resolve().parents[1] / "hermes_qualification" / "profiles"
)
_HERMES_PROVIDER_ORDER = (
    "zai.glm-5.3",
    "byteplus-modelark.glm-5.3-flash",
    "minimax.attended",
    "cursor-pool",
)


class ProfileRenderError(RuntimeError):
    """The qualification profile no longer matches the role contract."""


def render_profile(profile_name: str) -> str:
    if profile_name not in PROFILE_PRIMARY:
        raise ProfileRenderError("unknown hermes profile")
    source = _load_qualification(profile_name)
    primary = provider(PROFILE_PRIMARY[profile_name])
    logical = source["model"]["default"]
    expected = {
        "mmmeta": "glm-5.3",
        "mmsecretary": "glm-5.3-flash",
    }[profile_name]
    if logical != expected:
        raise ProfileRenderError("qualification profile model intent drifted")
    disabled = list(source["agent"]["disabled_toolsets"])
    toolsets = list(source["toolsets"])
    lines = [
        f"# {OVERLAY_SCHEMA}",
        f"# Hermes provider overlay for profile {profile_name}.",
        f"# Upstream pin NousResearch/hermes-agent@{UPSTREAM_HERMES_SHA}.",
        f"# logical_model: {logical}",
        f"# served_model: {primary.served_model}",
        "# production_armed: false",
        "# executive_admission: false",
        "# No api_key values. key_env names point at 0600 files or env vars.",
        "# Automatic Hermes provider failover is omitted so 429 and outage turns are not replayed.",
        "# Qualification config.yaml is a separate disarmed preflight document.",
        "model:",
        f"  provider: {primary.hermes_name}",
        f"  default: {_yaml_str(primary.served_model)}",
        f"  base_url: {_yaml_str(primary.base_url)}",
        f"  key_env: {primary.credential_env}",
        f"  api_mode: {API_MODE}",
        "auxiliary:",
        "  vision:",
        "    provider: minimax-m3",
        "    model: \"MiniMax-M3\"",
        f"    base_url: {_yaml_str(PROVIDERS['minimax.attended'].base_url)}",
        f"    key_env: {PROVIDERS['minimax.attended'].credential_env}",
        f"    api_mode: {API_MODE}",
        "providers:",
    ]
    seen_hermes_names: set[str] = set()
    for provider_id in _HERMES_PROVIDER_ORDER:
        spec = PROVIDERS[provider_id]
        if spec.hermes_name in seen_hermes_names:
            continue
        seen_hermes_names.add(spec.hermes_name)
        lines.extend(_provider_block(spec))
    lines.append("agent:")
    lines.append("  disabled_toolsets:")
    for name in disabled:
        lines.append(f"    - {name}")
    lines.append("toolsets:")
    for name in toolsets:
        lines.append(f"  - {name}")
    lines.append("")
    text = "\n".join(lines)
    _assert_keyless(text)
    return text


def _provider_block(spec: ProviderSpec) -> list[str]:
    rows = [
        f"  {spec.hermes_name}:",
        f"    name: {_yaml_str(spec.display_name)}",
        f"    api: {_yaml_str(spec.base_url)}",
        f"    key_env: {spec.credential_env}",
        f"    api_mode: {API_MODE}",
        f"    default_model: {_yaml_str(spec.served_model)}",
    ]
    if spec.hermes_name == "byteplus-modelark":
        rows.append("    models:")
        for model_id in (
            PROVIDERS["byteplus-modelark.glm-5.3-flash"].served_model,
            PROVIDERS["byteplus-modelark.deepseek-v4.1-flash"].served_model,
        ):
            rows.append(f"      {_yaml_str(model_id)}: {{}}")
    if not spec.enabled_in_profile:
        rows.append("    enabled: false")
    return rows


def _load_qualification(profile_name: str) -> dict:
    path = _QUALIFICATION / profile_name / "config.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ProfileRenderError("qualification profile is unreadable")
    return loaded


def _yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _assert_keyless(text: str) -> None:
    lowered = text.lower()
    for forbidden in ("api_key:", "bearer ", "sk-", "api/coding"):
        if forbidden in lowered:
            raise ProfileRenderError("rendered profile contains forbidden material")
