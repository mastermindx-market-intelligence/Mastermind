"""Role and provider catalog for Hermes profiles.

Identifiers for GLM-5.3-Flash and DeepSeek Flash are the commercial ModelArk
contract staged on PR #1824 (head f559d9d1), not the Personal Coding Plan.
This module does not enable those aliases in ModelRouter and does not read
secret values.
"""

from __future__ import annotations

from dataclasses import dataclass


UPSTREAM_HERMES_SHA = "1c0cd667746d3395fe9e1b6c74f8f85952486f18"
OVERLAY_SCHEMA = "mastermind.hermes_model_provider_overlay.v1"
USAGE_SCHEMA = "mastermind.hermes_model_usage.v1"

# Commercial ap-southeast-1 ModelArk, OpenAI-compatible /api/v3.
# Personal Coding Plan endpoints are a different product and must not be used.
MODELARK_CONTRACT = {
    "source_pr": 1824,
    "source_head": "f559d9d188ab8905bd84779ed01b26a867f36ab9",
    "realm_id": "byteplus-modelark-commercial",
    "provider_alias": "byteplus-modelark",
    "base_url": "https://ark.ap-southeast.bytepluses.com/api/v3",
    "env_key": "BYTEPLUS_MODELARK_API_KEY",
    "wire_note": "Codex realm uses Responses; Hermes profiles use chat_completions on the same base URL",
    "personal_plan_base_urls": (
        "https://ark.ap-southeast.bytepluses.com/api/coding",
        "https://ark.ap-southeast.bytepluses.com/api/coding/v3",
    ),
    "aliases": {
        "byteplus-modelark.glm-5.3-flash": "glm-5-3-flash-260828",
        "byteplus-modelark.deepseek-v4.1-flash": "deepseek-v4-1-flash-261017",
    },
}

# Z.AI OpenAI-compatible international endpoint from the existing GLM key reader.
ZAI_OPENAI_BASE_URL = "https://api.z.ai/api/paas/v4"
# Existing reviewed MiniMax OpenAI-compatible binding.
MINIMAX_OPENAI_BASE_URL = "https://api.minimax.io/v1"
# RFC 2606 sink. Live Cursor pool calls require HERMES_CURSOR_POOL_BASE_URL.
CURSOR_POOL_PLACEHOLDER_BASE_URL = "https://cursor-pool.invalid/v1"
# Default model id of the existing Fabric cursor pool.
CURSOR_POOL_MODEL = "composer-2.5"

PERSONAL_PLAN_BASE_URLS = frozenset(MODELARK_CONTRACT["personal_plan_base_urls"])
API_MODE = "chat_completions"


@dataclass(frozen=True)
class ProviderSpec:
    """One OpenAI-compatible chat provider. Secrets are names, never values."""

    provider_id: str
    hermes_name: str
    display_name: str
    served_model: str
    base_url: str
    credential_env: str
    credential_file_env: str
    router_alias: str | None = None
    base_url_env: str | None = None
    enabled_in_profile: bool = True

    def __post_init__(self) -> None:
        if self.base_url.rstrip("/") in PERSONAL_PLAN_BASE_URLS:
            raise ValueError("personal coding plan endpoint is not the ModelArk contract")
        if "://" not in self.base_url or self.base_url.startswith("http://"):
            raise ValueError("provider base_url must be https")
        lowered = self.base_url.lower()
        if "@" in lowered or "api_key=" in lowered or "bearer " in lowered:
            raise ValueError("provider base_url must not carry credentials")


PROVIDERS: dict[str, ProviderSpec] = {
    "zai.glm-5.3": ProviderSpec(
        provider_id="zai.glm-5.3",
        hermes_name="zai-glm",
        display_name="Z.AI GLM-5.3",
        served_model="glm-5.3",
        base_url=ZAI_OPENAI_BASE_URL,
        credential_env="ZAI_API_KEY",
        credential_file_env="ZAI_API_KEY_FILE",
        router_alias=None,
    ),
    "byteplus-modelark.glm-5.3-flash": ProviderSpec(
        provider_id="byteplus-modelark.glm-5.3-flash",
        hermes_name="byteplus-modelark",
        display_name="BytePlus ModelArk Commercial",
        served_model=MODELARK_CONTRACT["aliases"]["byteplus-modelark.glm-5.3-flash"],
        base_url=MODELARK_CONTRACT["base_url"],
        credential_env=MODELARK_CONTRACT["env_key"],
        credential_file_env="BYTEPLUS_MODELARK_API_KEY_FILE",
        router_alias="byteplus-modelark.glm-5.3-flash",
    ),
    "byteplus-modelark.deepseek-v4.1-flash": ProviderSpec(
        provider_id="byteplus-modelark.deepseek-v4.1-flash",
        hermes_name="byteplus-modelark",
        display_name="BytePlus ModelArk Commercial",
        served_model=MODELARK_CONTRACT["aliases"]["byteplus-modelark.deepseek-v4.1-flash"],
        base_url=MODELARK_CONTRACT["base_url"],
        credential_env=MODELARK_CONTRACT["env_key"],
        credential_file_env="BYTEPLUS_MODELARK_API_KEY_FILE",
        router_alias="byteplus-modelark.deepseek-v4.1-flash",
    ),
    "minimax.attended": ProviderSpec(
        provider_id="minimax.attended",
        hermes_name="minimax-m3",
        display_name="MiniMax-M3",
        served_model="MiniMax-M3",
        base_url=MINIMAX_OPENAI_BASE_URL,
        credential_env="MINIMAX_TOKEN_PLAN_KEY",
        credential_file_env="MINIMAX_TOKEN_PLAN_KEY_FILE",
        router_alias="minimax.attended",
    ),
    "cursor-pool": ProviderSpec(
        provider_id="cursor-pool",
        hermes_name="cursor-pool",
        display_name="Cursor pool",
        served_model=CURSOR_POOL_MODEL,
        base_url=CURSOR_POOL_PLACEHOLDER_BASE_URL,
        credential_env="CURSOR_API_KEY",
        credential_file_env="CURSOR_API_KEY_FILE",
        router_alias=None,
        base_url_env="HERMES_CURSOR_POOL_BASE_URL",
        enabled_in_profile=False,
    ),
}


@dataclass(frozen=True)
class RoleSpec:
    role: str
    profile: str | None
    logical_model: str
    provider_ids: tuple[str, ...]


# Chairman mapping, 2026-10-25. Flash aliases share one ModelArk credential.
# Cursor pool is the last resort, not a silent replay target.
ROLES: dict[str, RoleSpec] = {
    "meta-ceo": RoleSpec(
        role="meta-ceo",
        profile="mmmeta",
        logical_model="glm-5.3",
        provider_ids=("zai.glm-5.3", "cursor-pool"),
    ),
    "secretary": RoleSpec(
        role="secretary",
        profile="mmsecretary",
        logical_model="glm-5.3-flash",
        provider_ids=(
            "byteplus-modelark.glm-5.3-flash",
            "byteplus-modelark.deepseek-v4.1-flash",
            "cursor-pool",
        ),
    ),
    "watcher": RoleSpec(
        role="watcher",
        profile="mmsecretary",
        logical_model="glm-5.3-flash",
        provider_ids=(
            "byteplus-modelark.glm-5.3-flash",
            "byteplus-modelark.deepseek-v4.1-flash",
            "cursor-pool",
        ),
    ),
    "implementation-subagent": RoleSpec(
        role="implementation-subagent",
        profile="mmsecretary",
        logical_model="glm-5.3-flash",
        provider_ids=(
            "byteplus-modelark.glm-5.3-flash",
            "byteplus-modelark.deepseek-v4.1-flash",
            "cursor-pool",
        ),
    ),
    "vision": RoleSpec(
        role="vision",
        profile=None,
        logical_model="MiniMax-M3",
        provider_ids=("minimax.attended", "cursor-pool"),
    ),
    "computer-use": RoleSpec(
        role="computer-use",
        profile=None,
        logical_model="MiniMax-M3",
        provider_ids=("minimax.attended", "cursor-pool"),
    ),
}

PROFILE_PRIMARY = {
    "mmmeta": "zai.glm-5.3",
    "mmsecretary": "byteplus-modelark.glm-5.3-flash",
}

CREDENTIAL_ENV_NAMES = tuple(sorted({spec.credential_env for spec in PROVIDERS.values()}))
CREDENTIAL_FILE_ENV_NAMES = tuple(
    sorted({spec.credential_file_env for spec in PROVIDERS.values()})
)
CREDENTIAL_POINTER_NAMES = tuple(sorted(set(CREDENTIAL_ENV_NAMES) | set(CREDENTIAL_FILE_ENV_NAMES)))


def provider(provider_id: str) -> ProviderSpec:
    try:
        return PROVIDERS[provider_id]
    except KeyError as exc:
        raise KeyError(f"unknown hermes provider {provider_id!r}") from exc


def role(role_id: str) -> RoleSpec:
    try:
        return ROLES[role_id]
    except KeyError as exc:
        raise KeyError(f"unknown hermes role {role_id!r}") from exc


def chain_for(role_id: str, *, provider_id: str | None = None) -> tuple[ProviderSpec, ...]:
    spec = role(role_id)
    if provider_id is None:
        return tuple(provider(item) for item in spec.provider_ids)
    if provider_id not in spec.provider_ids:
        raise KeyError(f"provider {provider_id!r} is outside role {role_id!r}")
    # An explicit provider pin is one attempt. It does not walk the failover chain.
    return (provider(provider_id),)
