from __future__ import annotations

import copy

import pytest

from control_plane.subscription_provider_profiles import ProviderProfileError, get_profile, load_profiles, validate_profiles


def test_all_three_subscription_providers_are_reviewed_and_inert_by_default():
    catalog = load_profiles()
    assert set(catalog["profiles"]) == {"glm-coding-plan", "alibaba-token-plan-personal", "minimax-token-plan"}
    for profile_id in catalog["profiles"]:
        profile = get_profile(profile_id, document=catalog)
        assert profile.autonomous_allowed is False
        assert profile.activation_gate == "provider_realm_enrolled_and_capacity_known"
        assert profile.base_url.startswith("https://")


def test_official_anthropic_compatibility_profiles_pin_supported_models():
    assert get_profile("glm-coding-plan").model_for("routine") == "GLM-5.3"
    assert get_profile("glm-coding-plan").model_for("fast") == "GLM-5.3-Flash"
    assert get_profile("alibaba-token-plan-personal").model_for() == "qwen3.8-max"
    assert get_profile("alibaba-token-plan-personal").model_for("subagent") == "qwen3.7-max"
    assert get_profile("minimax-token-plan").model_for() == "MiniMax-M3"


def test_purchased_subscription_profiles_are_not_eligible_for_unattended_production():
    for profile_id in ("glm-coding-plan", "alibaba-token-plan-personal", "minimax-token-plan"):
        profile = get_profile(profile_id)
        assert profile.usage_policy["interactive_only"] is True
        assert profile.usage_policy["unattended_background_allowed"] is False
        assert profile.usage_policy["production_backend_allowed"] is False


def test_profiles_cannot_self_arm_or_embed_credential_authority():
    catalog = copy.deepcopy(load_profiles())
    catalog["profiles"]["glm-coding-plan"]["autonomous_allowed"] = True
    with pytest.raises(ProviderProfileError, match="cannot be autonomous"):
        validate_profiles(catalog)
    catalog = copy.deepcopy(load_profiles())
    catalog["profiles"]["glm-coding-plan"]["credential_binding"] = "request_payload"
    with pytest.raises(ProviderProfileError, match="credential authority"):
        validate_profiles(catalog)


def test_profile_document_carrying_adapter_id_is_rejected():
    catalog = load_profiles()
    assert "adapter_id" not in catalog
    catalog = copy.deepcopy(catalog)
    catalog["adapter_id"] = "claude-compatible-subscription"
    with pytest.raises(ProviderProfileError, match="must not name an adapter"):
        validate_profiles(catalog)
    catalog = copy.deepcopy(load_profiles())
    catalog["profiles"]["glm-coding-plan"]["adapter_id"] = "claude-compatible-subscription"
    with pytest.raises(ProviderProfileError, match="must not name an adapter"):
        validate_profiles(catalog)


def test_profile_protocols_are_plan_declared_and_fail_closed():
    catalog = copy.deepcopy(load_profiles())
    catalog["profiles"]["glm-coding-plan"]["protocol"] = "openai-chat"
    validate_profiles(catalog)
    catalog["profiles"]["glm-coding-plan"]["protocol"] = "openai-compatible"
    with pytest.raises(ProviderProfileError, match="unsupported protocol"):
        validate_profiles(catalog)
    catalog["profiles"]["glm-coding-plan"]["protocol"] = "unknown-wire"
    with pytest.raises(ProviderProfileError, match="unsupported protocol"):
        validate_profiles(catalog)
