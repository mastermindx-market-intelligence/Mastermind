from __future__ import annotations

import copy

import pytest

from control_plane.subscription_provider_profiles import ProviderProfileError, get_profile, load_profiles, validate_profiles


def _catalog() -> dict:
    return copy.deepcopy(load_profiles())


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
        assert profile.usage_policy["supported_harness_required"] is True
        assert profile.usage_policy["interactive_only"] is True
        assert profile.usage_policy["unattended_background_allowed"] is False
        assert profile.usage_policy["production_backend_allowed"] is False


def test_profiles_cannot_self_arm_or_embed_credential_authority():
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["autonomous_allowed"] = True
    with pytest.raises(ProviderProfileError, match="cannot be autonomous"):
        validate_profiles(catalog)
    catalog = _catalog()
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
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["adapter_id"] = "claude-compatible-subscription"
    with pytest.raises(ProviderProfileError, match="must not name an adapter"):
        validate_profiles(catalog)


def test_profile_protocols_are_plan_declared_and_fail_closed():
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["protocol"] = "openai-chat"
    validate_profiles(catalog)
    catalog["profiles"]["glm-coding-plan"]["protocol"] = "responses"
    validate_profiles(catalog)
    catalog["profiles"]["glm-coding-plan"]["protocol"] = "openai-compatible"
    with pytest.raises(ProviderProfileError, match="unsupported protocol"):
        validate_profiles(catalog)
    catalog["profiles"]["glm-coding-plan"]["protocol"] = "unknown-wire"
    with pytest.raises(ProviderProfileError, match="unsupported protocol"):
        validate_profiles(catalog)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda catalog: catalog.__setitem__("api_key", "sk-test"), r"document\.api_key: unknown key"),
        (lambda catalog: catalog.__setitem__("account", "owner@example.com"), r"document\.account: unknown key"),
        (lambda catalog: catalog.__setitem__("authority", "self-arm"), r"document\.authority: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"].__setitem__("api_key", "sk-test"), r"profiles\.glm-coding-plan\.api_key: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"].__setitem__("account", "acct-1"), r"profiles\.glm-coding-plan\.account: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"].__setitem__("authority", "override"), r"profiles\.glm-coding-plan\.authority: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"]["quota_profile"].__setitem__("api_key", "sk-test"), r"profiles\.glm-coding-plan\.quota_profile\.api_key: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"]["quota_profile"].__setitem__("account", "acct-1"), r"profiles\.glm-coding-plan\.quota_profile\.account: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"]["quota_profile"].__setitem__("authority", "quota-admin"), r"profiles\.glm-coding-plan\.quota_profile\.authority: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"]["usage_policy"].__setitem__("api_key", "sk-test"), r"profiles\.glm-coding-plan\.usage_policy\.api_key: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"]["usage_policy"].__setitem__("account", "acct-1"), r"profiles\.glm-coding-plan\.usage_policy\.account: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"]["usage_policy"].__setitem__("authority", "policy-admin"), r"profiles\.glm-coding-plan\.usage_policy\.authority: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"]["models"].__setitem__("api_key", "sk-test"), r"profiles\.glm-coding-plan\.models\.api_key: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"]["models"].__setitem__("account", "acct-1"), r"profiles\.glm-coding-plan\.models\.account: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"]["models"].__setitem__("authority", "model-admin"), r"profiles\.glm-coding-plan\.models\.authority: unknown key"),
        (lambda catalog: catalog.__setitem__("metadata", {"api_key": "sk-test"}), r"document\.metadata\.api_key: unknown key"),
        (lambda catalog: catalog.__setitem__("metadata", {"account": "acct-1"}), r"document\.metadata\.account: unknown key"),
        (lambda catalog: catalog.__setitem__("metadata", {"authority": "meta-admin"}), r"document\.metadata\.authority: unknown key"),
        (lambda catalog: catalog["profiles"]["glm-coding-plan"].__setitem__("metadata", {"api_key": "sk-test"}), r"profiles\.glm-coding-plan\.metadata\.api_key: unknown key"),
        (
            lambda catalog: catalog["profiles"]["glm-coding-plan"]["models"].__setitem__(
                "routine", {"id": "GLM-5.3", "api_key": "sk-test"}
            ),
            r"profiles\.glm-coding-plan\.models\.routine\.api_key: unknown key",
        ),
        (
            lambda catalog: catalog["profiles"]["glm-coding-plan"]["models"].__setitem__(
                "routine", {"id": "GLM-5.3", "account": "acct-1"}
            ),
            r"profiles\.glm-coding-plan\.models\.routine\.account: unknown key",
        ),
        (
            lambda catalog: catalog["profiles"]["glm-coding-plan"]["models"].__setitem__(
                "routine", {"id": "GLM-5.3", "authority": "model-admin"}
            ),
            r"profiles\.glm-coding-plan\.models\.routine\.authority: unknown key",
        ),
    ],
)
def test_secret_account_authority_extras_are_rejected_at_every_level(mutate, match):
    catalog = _catalog()
    mutate(catalog)
    with pytest.raises(ProviderProfileError, match=match):
        validate_profiles(catalog)


def test_usage_policy_cannot_omit_or_weaken_baseline_fences():
    catalog = _catalog()
    del catalog["profiles"]["glm-coding-plan"]["usage_policy"]["supported_harness_required"]
    with pytest.raises(ProviderProfileError, match=r"usage_policy\.supported_harness_required: missing key"):
        validate_profiles(catalog)
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["usage_policy"]["interactive_only"] = False
    with pytest.raises(ProviderProfileError, match=r"usage_policy\.interactive_only is unsafe"):
        validate_profiles(catalog)
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["usage_policy"]["unattended_background_allowed"] = True
    with pytest.raises(ProviderProfileError, match=r"unattended_background_allowed is unsafe"):
        validate_profiles(catalog)
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["usage_policy"]["production_backend_allowed"] = True
    with pytest.raises(ProviderProfileError, match=r"production_backend_allowed is unsafe"):
        validate_profiles(catalog)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.z.ai/api/anthropic?k=v",
        "https://api.z.ai/api/anthropic#frag",
        "https://user:pass@api.z.ai/api/anthropic",
        "https://user@api.z.ai/api/anthropic",
        "http://api.z.ai/api/anthropic",
        "https://",
        "not-a-url",
        "https://api.z.ai/foo/../anthropic",
        "https://api.z.ai/foo/%2e%2e/anthropic",
    ],
)
def test_base_url_rejects_query_fragment_userinfo_and_malformed_forms(base_url):
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["base_url"] = base_url
    with pytest.raises(ProviderProfileError, match="invalid base URL"):
        validate_profiles(catalog)


@pytest.mark.parametrize("flag", [1, 0, "true", "false", None])
def test_supported_tool_only_rejects_non_bool(flag):
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["supported_tool_only"] = flag
    with pytest.raises(ProviderProfileError, match=r"supported_tool_only must be a bool"):
        validate_profiles(catalog)
    profile = get_profile("minimax-token-plan")
    assert profile.supported_tool_only is False


def test_oversized_strings_are_rejected():
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["provider"] = "g" * 257
    with pytest.raises(ProviderProfileError, match="invalid provider"):
        validate_profiles(catalog)
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["models"]["routine"] = "M" * 257
    with pytest.raises(ProviderProfileError, match="invalid"):
        validate_profiles(catalog)
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["notes"] = ["n" * 257]
    with pytest.raises(ProviderProfileError, match="exceeds string bounds"):
        validate_profiles(catalog)


def test_closed_model_entry_and_empty_metadata_are_accepted():
    catalog = _catalog()
    catalog["metadata"] = {}
    catalog["profiles"]["glm-coding-plan"]["metadata"] = {}
    catalog["profiles"]["glm-coding-plan"]["models"]["routine"] = {"id": "GLM-5.3"}
    validate_profiles(catalog)
    assert get_profile("glm-coding-plan", document=catalog).model_for("routine") == "GLM-5.3"
