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
    assert get_profile("glm-coding-plan").model_for("routine") == "GLM-4.7"
    assert get_profile("glm-coding-plan").model_for("hard") == "GLM-5.1"
    assert get_profile("alibaba-token-plan-personal").model_for() == "qwen3.8-max"
    assert get_profile("minimax-token-plan").model_for() == "MiniMax-M2.7"


def test_minimax_m3_is_not_advertised_on_anthropic_adapter_before_provider_support():
    profile = get_profile("minimax-token-plan")
    assert all("M3" not in model for model in profile.models.values())


def test_profiles_cannot_self_arm_or_embed_credential_authority():
    catalog = copy.deepcopy(load_profiles())
    catalog["profiles"]["glm-coding-plan"]["autonomous_allowed"] = True
    with pytest.raises(ProviderProfileError, match="cannot be autonomous"):
        validate_profiles(catalog)
    catalog = copy.deepcopy(load_profiles())
    catalog["profiles"]["glm-coding-plan"]["credential_binding"] = "request_payload"
    with pytest.raises(ProviderProfileError, match="credential authority"):
        validate_profiles(catalog)
