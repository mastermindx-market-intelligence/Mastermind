"""Render the intended BYOK text-model into the *native* Hermes profile.

Pure configuration: does not read keys, contact providers, enable MCP, enable
vision/computer use, grant Executive admission, or start a process. Only the
already reviewed WP2 provider names and WP3 disabled Steward server are used.
"""
from __future__ import annotations

from integrations.hermes_harness.native_mcp import render_disarmed_native_config
from integrations.hermes_models.contract import (
    API_MODE, PROFILE_PRIMARY, PROVIDERS, MODELARK_CONTRACT, native_provider,
)
from integrations.hermes_models.profile_config import render_profile
from integrations.hermes_runtime.errors import RuntimeRefusal
from integrations.hermes_runtime.profile import RuntimeProfile
from integrations.hermes_steward.config_guard import _load_unique_yaml


def _expected_providers() -> dict:
    names = (
        "zai.glm-5.3",
        "byteplus-modelark.glm-5.3-flash",
        "minimax.attended",
        "cursor-pool",
    )
    result: dict = {}
    for ident in names:
        spec = PROVIDERS[ident]
        entry: dict = {
            "name": spec.display_name,
            "api": spec.base_url,
            "key_env": spec.credential_env,
            "api_mode": API_MODE,
            "default_model": spec.served_model,
        }
        if ident == "byteplus-modelark.glm-5.3-flash":
            entry["models"] = {
                spec.served_model: {},
                PROVIDERS["byteplus-modelark.deepseek-v4.1-flash"].served_model: {},
            }
        if not spec.enabled_in_profile:
            entry["enabled"] = False
        result[spec.hermes_name] = entry
    return result


def render_disarmed_native_byok(profile: RuntimeProfile) -> str:
    """Compose an exact, keyless vendor config with no automatic fallback.

    Profile authority continues to require the existing pinned role source.
    A configured model/provider is not a successful inference or credential
    grant. Primary, URL, mode, and key *names* are checked before publication.
    """
    if not isinstance(profile, RuntimeProfile) or profile.role not in PROFILE_PRIMARY:
        raise RuntimeRefusal("NATIVE_BYOK_ROLE_REFUSED")
    if profile.extension_allowlist:
        raise RuntimeRefusal("NATIVE_BYOK_EXTENSION_NOT_INSTALLED")
    try:
        native = _load_unique_yaml(render_disarmed_native_config(profile).encode("utf-8"))
        overlay = _load_unique_yaml(render_profile(
            profile.role, native_provider_id=profile.native_provider_id,
        ).encode("utf-8"))
    except RuntimeRefusal:
        raise
    except (OSError, RuntimeError, ValueError, UnicodeError):
        raise RuntimeRefusal("NATIVE_BYOK_SOURCE_INVALID") from None
    if not isinstance(native, dict) or not isinstance(overlay, dict):
        raise RuntimeRefusal("NATIVE_BYOK_SOURCE_INVALID")
    if set(overlay) != {"model", "providers", "auxiliary", "agent", "toolsets"}:
        raise RuntimeRefusal("NATIVE_BYOK_OVERLAY_DRIFT")
    if (
        not isinstance(overlay["agent"], dict)
        or set(overlay["agent"]) != {"disabled_toolsets"}
        or set(overlay["agent"]["disabled_toolsets"]) != set(native["agent"]["disabled_toolsets"])
        or len(overlay["agent"]["disabled_toolsets"]) != len(native["agent"]["disabled_toolsets"])
        or overlay["toolsets"] != native["toolsets"]
    ):
        raise RuntimeRefusal("NATIVE_BYOK_TOOLSET_DRIFT")
    try:
        primary = native_provider(profile.role, profile.native_provider_id)
    except (ValueError, KeyError):
        raise RuntimeRefusal("NATIVE_MODEL_SELECTION_UNQUALIFIED") from None
    required_model = {
        "provider": primary.hermes_name,
        "default": primary.served_model,
        "base_url": primary.base_url,
        "key_env": primary.credential_env,
        "api_mode": API_MODE,
    }
    if overlay["model"] != required_model:
        raise RuntimeRefusal("NATIVE_BYOK_MODEL_DRIFT")
    if overlay["providers"] != _expected_providers():
        raise RuntimeRefusal("NATIVE_BYOK_PROVIDERS_DRIFT")
    if MODELARK_CONTRACT["base_url"].rstrip("/") in MODELARK_CONTRACT["personal_plan_base_urls"]:
        raise RuntimeRefusal("NATIVE_BYOK_REALM_DRIFT")
    if native["mcp_servers"]["mastermind_steward"]["enabled"] is not False:
        raise RuntimeRefusal("NATIVE_BYOK_MCP_ENABLED")
    if primary.provider_id == "cursor-pool":
        raise RuntimeRefusal("NATIVE_BYOK_DISABLED_PRIMARY")
    # No auxiliary/vision model is added at this stage: the required
    # computer-use enrollment and mini1 effect authorization do not exist.
    native["model"] = required_model
    native["providers"] = overlay["providers"]
    # The WP1 base has an inert-looking vision auxiliary stanza. Removing
    # it is necessary: this wave has no accepted mini1 vision grant.
    native.pop("auxiliary", None)
    import yaml  # no PyYAML import for the unrelated Secretary shadow scanner

    rendered = (
        "# Mastermind role model configured, not provider-armed or verified.\n"
        "# Steward MCP, vision, computer-use and automatic fallback remain OFF.\n"
        + yaml.safe_dump(native, sort_keys=False, allow_unicode=False)
    )
    if len(rendered.encode("utf-8")) > 64 * 1024:
        raise RuntimeRefusal("NATIVE_BYOK_CONFIG_TOO_LARGE")
    try:
        checked = _load_unique_yaml(rendered.encode("utf-8"))
    except ValueError:
        raise RuntimeRefusal("NATIVE_BYOK_CONFIG_INVALID") from None
    if checked != native or any(
        forbidden in rendered.lower()
        for forbidden in ("api_key:", "fallback_model:", "api/coding", "access_token:")
    ):
        raise RuntimeRefusal("NATIVE_BYOK_CONFIG_INVALID")
    return rendered
