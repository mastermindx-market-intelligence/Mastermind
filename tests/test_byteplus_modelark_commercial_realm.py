"""Commercial BytePlus API identity is separate from the Personal Coding Plan.

No provider call, secret read, worker enrollment, or Capacity fact is made here.
"""
from dataclasses import replace

import pytest

from control_plane.codex_provider_realm import (
    BYTEPLUS_MODELARK_COMMERCIAL,
    CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY,
    CodexProviderRealm,
    ProviderRealmError,
    REVIEWED_CODEX_PROVIDER_REALMS,
)


def test_commercial_realm_has_unique_api_and_entitlement_scope():
    commercial = BYTEPLUS_MODELARK_COMMERCIAL
    assert commercial.provider_alias == "byteplus-modelark"
    assert commercial.realm_id == "byteplus-modelark-commercial"
    assert commercial.base_url == "https://ark.ap-southeast.bytepluses.com/api/v3"
    assert commercial.wire_api == "responses"
    assert commercial.env_key == "BYTEPLUS_MODELARK_API_KEY"
    assert commercial.commercial_api_only is True
    assert commercial.interactive_subscription_only is False
    assert commercial.requires_codex_auth_file is False


def test_commercial_realm_does_not_mint_review_or_start():
    realm = BYTEPLUS_MODELARK_COMMERCIAL
    assert CANDIDATE_CODEX_PROVIDER_REALMS_SPEC_ONLY[realm.realm_id] is realm
    assert realm.realm_id not in REVIEWED_CODEX_PROVIDER_REALMS


def test_commercial_provider_config_uses_separate_env_and_url():
    opts = BYTEPLUS_MODELARK_COMMERCIAL.config_overrides()
    joined = "\n".join(opts)
    assert "BYTEPLUS_MODELARK_API_KEY" in joined
    assert "ark.ap-southeast.bytepluses.com/api/v3" in joined
    assert "/api/coding" not in joined
    assert "model_provider=" in joined
    assert "request_max_retries=0" in joined
    assert "stream_max_retries=0" in joined
    assert not any("Bearer " in item for item in opts)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"commercial_api_only": False},
        {"interactive_subscription_only": True},
        {"base_url": "https://ark.ap-southeast.bytepluses.com/api/coding"},
        {"base_url": "https://ark.ap-southeast.bytepluses.com/api/coding/v3"},
        {"base_url": "https://ark.eu-west.bytepluses.com/api/v3"},
        {"provider_alias": "byteplus"},
        {"realm_id": "byteplus-coding-plan-personal"},
        {"env_key": "ARK_API_KEY"},
        {"wire_api": "openai-chat"},
        {"requires_codex_auth_file": True},
        {"commercial_api_only": "true"},
    ],
)
def test_commercial_identity_rejects_unsafe_substitutions(kwargs):
    with pytest.raises(ProviderRealmError):
        replace(BYTEPLUS_MODELARK_COMMERCIAL, **kwargs)


def test_other_provider_cannot_self_promote_to_commercial():
    with pytest.raises(ProviderRealmError, match="unreviewed autonomous"):
        CodexProviderRealm(
            realm_id="another-provider",
            provider_alias="other",
            display_name="Other",
            base_url="https://other.example.com/v1",
            env_key="OTHER_API_KEY",
            wire_api="responses",
            interactive_subscription_only=False,
            commercial_api_only=True,
        )


def test_personal_subscription_cannot_claim_commercial_flag():
    with pytest.raises(ProviderRealmError, match="commercial API realm"):
        CodexProviderRealm(
            realm_id="byteplus-coding-plan-personal",
            provider_alias="byteplus",
            display_name="Personal Coding Plan",
            base_url="https://ark.ap-southeast.bytepluses.com/api/coding",
            env_key="BYTEPLUS_CODING_KEY",
            wire_api="responses",
            commercial_api_only=True,
        )
