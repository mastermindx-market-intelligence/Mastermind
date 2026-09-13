"""Secret-free custom-provider realms for the hardened Codex worker.

A realm selects Codex's standard OpenAI-compatible provider transport. It owns
no lifecycle, credential bytes, routing decision, or retry policy. Executive OS
remains the Job/Attempt authority and CodexWorkerAdapter remains the process
boundary.
"""
from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable
from urllib.parse import urlparse


_REALM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_SECRET_SHAPE_RE = re.compile(r"(?i)(?:sk-[a-z0-9_-]{12,}|bearer\s+[a-z0-9._-]{12,})")
_WIRE_APIS = frozenset({"responses", "chat"})


class ProviderRealmError(ValueError):
    """A provider realm or credential observation is unsafe or malformed."""


@dataclasses.dataclass(frozen=True)
class CodexProviderRealm:
    realm_id: str
    provider_alias: str
    display_name: str
    base_url: str
    env_key: str
    wire_api: str
    requires_codex_auth_file: bool = False
    interactive_subscription_only: bool = True
    request_max_retries: int = 0
    stream_max_retries: int = 0
    def __post_init__(self) -> None:
        for field_name in ("realm_id", "provider_alias"):
            value = str(getattr(self, field_name) or "").strip().lower()
            if _REALM_ID_RE.fullmatch(value) is None:
                raise ProviderRealmError(f"{field_name} is invalid")
            object.__setattr__(self, field_name, value)
        name = str(self.display_name or "").strip()
        if not name or len(name) > 96 or _SECRET_SHAPE_RE.search(name):
            raise ProviderRealmError("display_name is invalid")
        object.__setattr__(self, "display_name", name)
        endpoint = str(self.base_url or "").strip().rstrip("/")
        parsed = urlparse(endpoint)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ProviderRealmError("base_url must be a credential-free HTTPS endpoint")
        if parsed.query or parsed.fragment or _SECRET_SHAPE_RE.search(endpoint):
            raise ProviderRealmError("base_url contains forbidden material")
        object.__setattr__(self, "base_url", endpoint)
        env_key = str(self.env_key or "").strip()
        if _ENV_KEY_RE.fullmatch(env_key) is None:
            raise ProviderRealmError("env_key is invalid")
        object.__setattr__(self, "env_key", env_key)
        wire_api = str(self.wire_api or "").strip().lower()
        if wire_api not in _WIRE_APIS:
            raise ProviderRealmError("wire_api is unsupported")
        object.__setattr__(self, "wire_api", wire_api)
        for field_name in ("request_max_retries", "stream_max_retries"):
            value = getattr(self, field_name)
            if type(value) is not int or value != 0:
                raise ProviderRealmError(f"{field_name} must remain zero")
        if self.interactive_subscription_only is not True:
            raise ProviderRealmError("subscription realms must remain interactive-only")

    @property
    def codex_provider_id(self) -> str:
        return "mastermind_" + self.realm_id.replace("-", "_").replace(".", "_")

    def config_overrides(self) -> tuple[str, ...]:
        provider_id = self.codex_provider_id
        prefix = f"model_providers.{provider_id}"
        return (
            f"model_provider={json.dumps(provider_id)}",
            f"{prefix}.name={json.dumps(self.display_name)}",
            f"{prefix}.base_url={json.dumps(self.base_url)}",
            f"{prefix}.env_key={json.dumps(self.env_key)}",
            f"{prefix}.wire_api={json.dumps(self.wire_api)}",
            f"{prefix}.request_max_retries=0",
            f"{prefix}.stream_max_retries=0",
        )

    def validate_credential(self, value: str) -> str:
        if not isinstance(value, str):
            raise ProviderRealmError("provider credential is unavailable")
        credential = value.strip()
        if not credential or len(credential) > 4096 or any(ch in credential for ch in "\r\n\x00"):
            raise ProviderRealmError("provider credential is unavailable")
        return credential


MINIMAX_TOKEN_PLAN = CodexProviderRealm(
    realm_id="minimax-token-plan",
    provider_alias="minimax",
    display_name="MiniMax Token Plan",
    base_url="https://api.minimax.io/v1",
    env_key="MINIMAX_TOKEN_PLAN_KEY",
    wire_api="chat",
)

ALIBABA_TOKEN_PLAN = CodexProviderRealm(
    realm_id="alibaba-token-plan-sg",
    provider_alias="alibaba",
    display_name="Alibaba Model Studio Token Plan",
    base_url="https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1",
    env_key="ALIBABA_TOKEN_PLAN_KEY",
    wire_api="responses",
)

REVIEWED_CODEX_PROVIDER_REALMS = {
    realm.realm_id: realm for realm in (MINIMAX_TOKEN_PLAN, ALIBABA_TOKEN_PLAN)
}

ProviderCredentialLoader = Callable[[], str]

__all__ = [
    "ALIBABA_TOKEN_PLAN",
    "MINIMAX_TOKEN_PLAN",
    "REVIEWED_CODEX_PROVIDER_REALMS",
    "CodexProviderRealm",
    "ProviderCredentialLoader",
    "ProviderRealmError",
]
