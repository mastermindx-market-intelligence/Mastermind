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
    assert get_profile("glm-coding-plan").model_for("routine") == "GLM-5.3-Flash"
    assert get_profile("glm-coding-plan").model_for("subagent") == "GLM-5.3-Flash"
    assert get_profile("glm-coding-plan").model_for("hard") == "GLM-5.3"
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
    catalog["adapter_id"] = "example-adapter"
    with pytest.raises(ProviderProfileError, match="must not name an adapter"):
        validate_profiles(catalog)
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["adapter_id"] = "example-adapter"
    with pytest.raises(ProviderProfileError, match="must not name an adapter"):
        validate_profiles(catalog)


def test_harness_id_is_rejected_at_document_and_row_levels():
    catalog = _catalog()
    catalog["harness_id"] = "example-harness"
    with pytest.raises(ProviderProfileError, match="must not name an adapter"):
        validate_profiles(catalog)
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["harness_id"] = "example-harness"
    with pytest.raises(ProviderProfileError, match="must not name an adapter"):
        validate_profiles(catalog)


def test_profile_protocols_are_plan_declared_and_fail_closed():
    catalog = copy.deepcopy(load_profiles())
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
        (lambda catalog: catalog["profiles"]["glm-coding-plan"].__setitem__("notes", ["plan note"]), r"profiles\.glm-coding-plan\.notes: unknown key"),
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
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["usage_policy"]["supported_harness_required"] = False
    with pytest.raises(ProviderProfileError, match=r"supported_harness_required is unsafe"):
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
        "https://api.z.ai/./anthropic",
        "https://api.z.ai//anthropic",
        "https://api.z.ai/api%2Fanthropic",
    ],
)
def test_base_url_rejects_query_fragment_userinfo_and_malformed_forms(base_url):
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["base_url"] = base_url
    with pytest.raises(ProviderProfileError, match="invalid base URL"):
        validate_profiles(catalog)


def test_base_url_rejects_empty_query_suffix():
    _reject_base_url("https://api.z.ai/api/anthropic?")


def test_base_url_rejects_empty_fragment_suffix():
    _reject_base_url("https://api.z.ai/api/anthropic#")


def test_base_url_rejects_empty_params_suffix():
    _reject_base_url("https://api.z.ai/api/anthropic;")


def test_base_url_accepts_unsuffixed_allowlisted_url():
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["base_url"] = "https://api.z.ai/api/anthropic"
    validate_profiles(catalog)


def _reject_base_url(base_url: str) -> None:
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["base_url"] = base_url
    with pytest.raises(ProviderProfileError, match="invalid base URL"):
        validate_profiles(catalog)


def test_base_url_rejects_encoded_backslash():
    _reject_base_url("https://api.z.ai/a%5Cb")


def test_base_url_rejects_literal_backslash():
    _reject_base_url("https://api.z.ai/a\\b")


def test_base_url_rejects_unicode_dot_aliases():
    _reject_base_url("https://api.z.ai/\u2024")
    _reject_base_url("https://api.z.ai/\uff0e")


def test_base_url_rejects_double_encoded_dots():
    _reject_base_url("https://api.z.ai/%252e%252e")


def test_base_url_rejects_empty_non_root_segment():
    _reject_base_url("https://api.z.ai/a/")
    _reject_base_url("https://api.z.ai//a")


def test_base_url_rejects_non_ascii_host_or_path():
    _reject_base_url("https://ex\u00e4mple.com/api/anthropic")
    _reject_base_url("https://api.z.ai/caf\u00e9")


def test_base_url_rejects_percent_in_path():
    _reject_base_url("https://api.z.ai/api%41")


def test_base_url_rejects_uppercase_scheme():
    _reject_base_url("HTTPS://api.z.ai/api/anthropic")


def test_base_url_rejects_uppercase_host():
    _reject_base_url("https://API.Z.AI/api/anthropic")


def test_base_url_rejects_trailing_dot_host():
    _reject_base_url("https://api.z.ai./api/anthropic")


def test_base_url_rejects_default_port():
    _reject_base_url("https://api.z.ai:443/api/anthropic")


def test_base_url_rejects_nonstandard_port():
    _reject_base_url("https://api.z.ai:8443/api/anthropic")


def test_base_url_rejects_empty_port():
    _reject_base_url("https://api.z.ai:/api/anthropic")


def test_base_url_rejects_userinfo():
    _reject_base_url("https://user@api.z.ai/api/anthropic")
    _reject_base_url("https://user:pass@api.z.ai/api/anthropic")


def test_base_url_rejects_punycode_label():
    _reject_base_url("https://xn--fiqs8s.example/api/anthropic")


def test_base_url_rejects_ipv6_literal():
    _reject_base_url("https://[2606:4700::6810:85e5]/api/anthropic")


def test_base_url_rejects_ipv4_literal():
    _reject_base_url("https://1.1.1.1/api/anthropic")


def test_base_url_rejects_tab_control_character():
    _reject_base_url("https://api.z.ai/api\t/anthropic")


def test_base_url_rejects_carriage_return_control_character():
    _reject_base_url("https://api.z.ai/api\r/anthropic")


def test_base_url_rejects_nul_control_character():
    _reject_base_url("https://api\x00.z.ai/api/anthropic")


def test_base_url_rejects_urls_over_512_characters():
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["base_url"] = (
        "https://api.z.ai/" + "a" * (513 - len("https://api.z.ai/"))
    )
    with pytest.raises(
        ProviderProfileError,
        match=r"base_url exceeds string bounds",
    ):
        validate_profiles(catalog)


def test_catalog_base_urls_use_canonical_dns_authorities():
    catalog = _catalog()
    validate_profiles(catalog)
    assert {
        profile["base_url"]
        for profile in catalog["profiles"].values()
    } == {
        "https://api.z.ai/api/anthropic",
        "https://token-plan.ap-southeast-1.maas.aliyuncs.com/apps/anthropic",
        "https://api.minimax.io/anthropic",
    }


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
    catalog["profiles"]["glm-coding-plan"]["protocol"] = "p" * 257
    with pytest.raises(ProviderProfileError, match="exceeds string bounds"):
        validate_profiles(catalog)


@pytest.mark.parametrize("flag", [1, 0, "true", "false", None])
def test_autonomous_allowed_rejects_non_bool(flag):
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["autonomous_allowed"] = flag
    with pytest.raises(ProviderProfileError, match=r"autonomous_allowed must be a bool"):
        validate_profiles(catalog)


@pytest.mark.parametrize("key", ["single_user_only", "payg_recommended_for_production"])
@pytest.mark.parametrize("flag", [1, 0, "true", "false", None])
def test_optional_policy_flags_reject_non_bool(key, flag):
    catalog = _catalog()
    catalog["profiles"]["glm-coding-plan"]["usage_policy"][key] = flag
    with pytest.raises(ProviderProfileError, match=rf"{key} must be a bool"):
        validate_profiles(catalog)


def test_closed_model_entry_and_empty_metadata_are_accepted():
    catalog = _catalog()
    catalog["metadata"] = {}
    catalog["profiles"]["glm-coding-plan"]["metadata"] = {}
    catalog["profiles"]["glm-coding-plan"]["models"]["routine"] = {"id": "GLM-5.3"}
    validate_profiles(catalog)
    assert get_profile("glm-coding-plan", document=catalog).model_for("routine") == "GLM-5.3"
