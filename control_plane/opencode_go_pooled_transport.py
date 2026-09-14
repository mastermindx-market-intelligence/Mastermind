"""Bounded OpenCode Go multi-account transport kernel.

This module composes an already-authorized OpenCode Go account pool into one
logical inference carrier. It deliberately does not own account ranking, quota
truth, credentials, Executive lifecycle, or provider retry policy:

- Shared Provider Control supplies each account choice through ``resolver``.
- Existing provider-home boundaries supply credential bytes through
  ``credential_loader`` only at the request edge.
- Executive OS remains the Job/Attempt/Worker authority.

Automatic in-pool rollover is permitted only for provider responses that are
provably pre-inference refusals. Ambiguous transport failure never rolls over.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import urljoin

OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1/"
_ALLOWED_PATHS = frozenset({"chat/completions", "responses", "messages"})
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_SAFE_ERROR_TYPES = {
    (429, "GoUsageLimitError"): "usage_limit",
    (401, "AuthError"): "auth",
}


class OpenCodeGoTransportError(RuntimeError):
    """Base class for bounded pooled-transport refusal."""


class OpenCodeGoPoolUnavailable(OpenCodeGoTransportError):
    """Provider Control returned no eligible account."""


class OpenCodeGoTransportContractError(OpenCodeGoTransportError):
    """A resolver, credential, or request contract was malformed."""


class OpenCodeGoEffectUnknown(OpenCodeGoTransportError):
    """A provider attempt may have taken effect; no automatic replay is safe."""

    def __init__(self, account_id: str, attempted_accounts: tuple[str, ...]) -> None:
        super().__init__("OpenCode Go provider effect is unknown; in-pool rollover refused")
        self.account_id = account_id
        self.attempted_accounts = attempted_accounts


@dataclass(frozen=True)
class ResolveRequest:
    pool_id: str
    session_id: str
    sticky_account_id: str | None
    excluded_account_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class AccountChoice:
    pool_id: str
    pool_generation: str
    account_id: str


@dataclass(frozen=True)
class ProviderRequest:
    path: str
    session_id: str
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class UpstreamRequest:
    url: str
    headers: Mapping[str, str]
    body: bytes
    account_id: str
    pool_generation: str


@dataclass(frozen=True)
class UpstreamResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class TransportReceipt:
    response: UpstreamResponse
    account_id: str
    pool_generation: str
    attempted_accounts: tuple[str, ...]
    rollover_count: int
    pool_exhausted: bool


Resolver = Callable[[ResolveRequest], AccountChoice | None]
CredentialLoader = Callable[[str], str]
Sender = Callable[[UpstreamRequest], UpstreamResponse]


def _identifier(value: object, field: str) -> str:
    text = str(value or "").strip().lower()
    if _ID_RE.fullmatch(text) is None:
        raise OpenCodeGoTransportContractError(f"invalid {field}")
    return text


def _session_id(value: object) -> str:
    if not isinstance(value, str):
        raise OpenCodeGoTransportContractError("invalid session_id")
    text = value.strip()
    if not text or len(text) > 512 or any(ord(ch) < 32 for ch in text):
        raise OpenCodeGoTransportContractError("invalid session_id")
    return text


def _path(value: object) -> str:
    text = str(value or "").strip().lstrip("/")
    if text not in _ALLOWED_PATHS:
        raise OpenCodeGoTransportContractError("unsupported OpenCode Go inference path")
    return text


def _credential(value: object) -> str:
    if not isinstance(value, str):
        raise OpenCodeGoTransportContractError("provider credential unavailable")
    secret = value.strip()
    if not secret or len(secret) > 4096 or any(ch in secret for ch in "\r\n\x00"):
        raise OpenCodeGoTransportContractError("provider credential unavailable")
    return secret


def _choice(value: AccountChoice, *, pool_id: str) -> AccountChoice:
    if not isinstance(value, AccountChoice):
        raise OpenCodeGoTransportContractError("resolver returned invalid account choice")
    selected_pool = _identifier(value.pool_id, "choice.pool_id")
    if selected_pool != pool_id:
        raise OpenCodeGoTransportContractError("resolver changed pool identity")
    generation = str(value.pool_generation or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", generation):
        raise OpenCodeGoTransportContractError("invalid pool generation")
    account = _identifier(value.account_id, "choice.account_id")
    return AccountChoice(selected_pool, generation, account)


def _error_type(response: UpstreamResponse) -> str | None:
    if response.status not in {401, 429}:
        return None
    if len(response.body) > 256 * 1024:
        return None
    try:
        body = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(body, Mapping):
        return None
    error = body.get("error")
    if not isinstance(error, Mapping):
        return None
    value = error.get("type")
    return value if isinstance(value, str) else None


def classify_pre_effect_refusal(response: UpstreamResponse) -> str | None:
    """Classify only OpenCode refusals that happen before upstream inference.

    Current OpenCode Go validates API-key auth and Go rolling/weekly/monthly
    allowance before constructing the upstream model request. Other 4xx/429
    classes are intentionally not generalized into replay permission.
    """

    return _SAFE_ERROR_TYPES.get((response.status, _error_type(response)))


def prepare_upstream_request(
    request: ProviderRequest,
    *,
    choice: AccountChoice,
    credential: str,
) -> UpstreamRequest:
    """Inject one account credential while preserving session and request body."""

    path = _path(request.path)
    session = _session_id(request.session_id)
    headers: dict[str, str] = {}
    for raw_key, raw_value in request.headers.items():
        key = str(raw_key).strip()
        value = str(raw_value)
        if not key or "\r" in key or "\n" in key or "\r" in value or "\n" in value:
            raise OpenCodeGoTransportContractError("invalid request header")
        if key.lower() in {"authorization", "host", "content-length", "x-opencode-session"}:
            continue
        headers[key] = value
    headers["Authorization"] = f"Bearer {_credential(credential)}"
    headers["x-opencode-session"] = session
    if not any(key.lower() == "user-agent" for key in headers):
        headers["User-Agent"] = "Mastermind-X/1.0"
    return UpstreamRequest(
        url=urljoin(OPENCODE_GO_BASE_URL, path),
        headers=headers,
        body=request.body,
        account_id=choice.account_id,
        pool_generation=choice.pool_generation,
    )


class OpenCodeGoPooledTransport:
    """Execute one logical inference with bounded, effect-safe in-pool rollover."""

    def __init__(
        self,
        *,
        pool_id: str,
        resolver: Resolver,
        credential_loader: CredentialLoader,
        sender: Sender,
        max_rollovers: int,
    ) -> None:
        self.pool_id = _identifier(pool_id, "pool_id")
        if not callable(resolver) or not callable(credential_loader) or not callable(sender):
            raise OpenCodeGoTransportContractError("transport dependencies must be callable")
        if isinstance(max_rollovers, bool) or not isinstance(max_rollovers, int) or not 0 <= max_rollovers <= 31:
            raise OpenCodeGoTransportContractError("invalid max_rollovers")
        self.resolver = resolver
        self.credential_loader = credential_loader
        self.sender = sender
        self.max_rollovers = max_rollovers

    def execute(
        self,
        request: ProviderRequest,
        *,
        sticky_account_id: str | None = None,
    ) -> TransportReceipt:
        session = _session_id(request.session_id)
        sticky = _identifier(sticky_account_id, "sticky_account_id") if sticky_account_id else None
        excluded: list[str] = []
        attempted: list[str] = []
        generation: str | None = None
        reason = "initial"

        while True:
            raw_choice = self.resolver(
                ResolveRequest(
                    pool_id=self.pool_id,
                    session_id=session,
                    sticky_account_id=sticky,
                    excluded_account_ids=tuple(excluded),
                    reason=reason,
                )
            )
            if raw_choice is None:
                raise OpenCodeGoPoolUnavailable("no eligible OpenCode Go account")
            choice = _choice(raw_choice, pool_id=self.pool_id)
            if generation is None:
                generation = choice.pool_generation
            elif generation != choice.pool_generation:
                raise OpenCodeGoTransportContractError("pool membership generation changed during inference")
            if choice.account_id in excluded or choice.account_id in attempted:
                raise OpenCodeGoTransportContractError("resolver repeated an excluded account")

            credential = _credential(self.credential_loader(choice.account_id))
            upstream = prepare_upstream_request(request, choice=choice, credential=credential)
            attempted.append(choice.account_id)
            try:
                response = self.sender(upstream)
            except Exception as exc:
                raise OpenCodeGoEffectUnknown(choice.account_id, tuple(attempted)) from exc
            if not isinstance(response, UpstreamResponse):
                raise OpenCodeGoEffectUnknown(choice.account_id, tuple(attempted))

            refusal = classify_pre_effect_refusal(response)
            if refusal is None:
                return TransportReceipt(
                    response=response,
                    account_id=choice.account_id,
                    pool_generation=choice.pool_generation,
                    attempted_accounts=tuple(attempted),
                    rollover_count=len(attempted) - 1,
                    pool_exhausted=False,
                )

            if len(attempted) - 1 >= self.max_rollovers:
                return TransportReceipt(
                    response=response,
                    account_id=choice.account_id,
                    pool_generation=choice.pool_generation,
                    attempted_accounts=tuple(attempted),
                    rollover_count=len(attempted) - 1,
                    pool_exhausted=True,
                )
            excluded.append(choice.account_id)
            sticky = None
            reason = refusal


__all__ = [
    "AccountChoice",
    "CredentialLoader",
    "OPENCODE_GO_BASE_URL",
    "OpenCodeGoEffectUnknown",
    "OpenCodeGoPoolUnavailable",
    "OpenCodeGoPooledTransport",
    "OpenCodeGoTransportContractError",
    "OpenCodeGoTransportError",
    "ProviderRequest",
    "ResolveRequest",
    "Sender",
    "TransportReceipt",
    "UpstreamRequest",
    "UpstreamResponse",
    "classify_pre_effect_refusal",
    "prepare_upstream_request",
]
