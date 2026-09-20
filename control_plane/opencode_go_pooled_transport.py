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
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional
from urllib.parse import urljoin
from types import MappingProxyType

OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1/"
_ALLOWED_PATHS = frozenset({"chat/completions", "responses", "messages"})
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_SAFE_ERROR_TYPES = {
    (429, "GoUsageLimitError"): "usage_limit",
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
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True)
class UpstreamRequest:
    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)
    account_id: str
    pool_generation: str


@dataclass(frozen=True)
class UpstreamResponse:
    status: int
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)


@dataclass(frozen=True)
class TransportReceipt:
    response: UpstreamResponse
    account_id: str
    pool_generation: str
    attempted_accounts: tuple[str, ...]
    rollover_count: int
    pool_exhausted: bool
    stop_reason: str = "response"


Resolver = Callable[[ResolveRequest], Optional[AccountChoice]]
CredentialLoader = Callable[[str], str]
Sender = Callable[[UpstreamRequest], UpstreamResponse]


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise OpenCodeGoTransportContractError(f"invalid {field}")
    text = value.strip().lower()
    if _ID_RE.fullmatch(text) is None:
        raise OpenCodeGoTransportContractError(f"invalid {field}")
    return text


def _session_id(value: object) -> str:
    if not isinstance(value, str):
        raise OpenCodeGoTransportContractError("invalid session_id")
    text = value.strip()
    if value != text or not text or len(text) > 512 or any(ord(ch) < 33 or ord(ch) > 126 for ch in text):
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
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
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

    The reviewed source checks Go allowance before inference. A live binding
    must separately verify gateway behavior. AuthError also represents account
    suspension, and is deliberately never treated as rollover permission.
    """

    refusal = _SAFE_ERROR_TYPES.get((response.status, _error_type(response)))
    if refusal is None:
        return None
    try:
        payload = json.loads(response.body, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    metadata = payload.get("metadata")
    if (payload.get("type") != "error" or not isinstance(metadata, dict)
            or metadata.get("limitName") not in {"5 hour", "weekly", "monthly"}
            or not isinstance(metadata.get("workspace"), str) or not metadata["workspace"]):
        return None
    return refusal


_FORWARDED_HEADERS = frozenset({
    "content-type", "accept", "user-agent", "anthropic-version", "anthropic-beta",
    "x-opencode-request", "x-opencode-client", "x-opencode-project",
})
_HEADER_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_MAX_REQUEST_BYTES = 16 * 1024 * 1024


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError("nonfinite JSON number")


def _freeze_request(request: ProviderRequest, *, replayable: bool) -> ProviderRequest:
    if not isinstance(request, ProviderRequest):
        raise OpenCodeGoTransportContractError("invalid provider request")
    path, session = _path(request.path), _session_id(request.session_id)
    if not isinstance(request.body, (bytes, bytearray)):
        raise OpenCodeGoTransportContractError("request body must be bytes")
    body = bytes(request.body)
    if not body or len(body) > _MAX_REQUEST_BYTES:
        raise OpenCodeGoTransportContractError("request body outside size bound")
    try:
        payload = json.loads(body, object_pairs_hook=_unique_object,
                             parse_constant=_reject_json_constant)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise OpenCodeGoTransportContractError("request body must be valid JSON") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("model"), str) or not payload["model"].strip():
        raise OpenCodeGoTransportContractError("request requires explicit model")
    if replayable:
        # Inspect protocol context, not function parameter schemas named e.g. file_id.
        if any(payload.get(key) is not None for key in
               ("previous_response_id", "conversation", "container")):
            raise OpenCodeGoTransportContractError("account-scoped context is not replayable")
        pending = [payload.get("input"), payload.get("messages")]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                if (any(item.get(key) is not None for key in
                        ("file_id", "encrypted_content"))
                        or item.get("type") == "item_reference"):
                    raise OpenCodeGoTransportContractError("account-scoped context is not replayable")
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
    if not isinstance(request.headers, Mapping):
        raise OpenCodeGoTransportContractError("invalid request headers")
    headers = {}
    seen = set()
    for key, value in request.headers.items():
        if (not isinstance(key, str) or not _HEADER_RE.fullmatch(key)
                or not isinstance(value, str)
                or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
            raise OpenCodeGoTransportContractError("invalid request header")
        lowered = key.lower()
        if lowered in seen:
            raise OpenCodeGoTransportContractError("duplicate request header")
        seen.add(lowered)
        if lowered in _FORWARDED_HEADERS:
            headers[key] = value
    return ProviderRequest(path, session, MappingProxyType(headers), body)


def prepare_upstream_request(
    request: ProviderRequest,
    *,
    choice: AccountChoice,
    credential: str,
) -> UpstreamRequest:
    """Inject one account credential while preserving session and request body."""

    request = _freeze_request(request, replayable=False)
    path = request.path
    session = request.session_id
    headers: dict[str, str] = {}
    seen_headers: set[str] = set()
    for raw_key, raw_value in request.headers.items():
        key = str(raw_key).strip()
        value = str(raw_value)
        if not key or "\r" in key or "\n" in key or "\r" in value or "\n" in value:
            raise OpenCodeGoTransportContractError("invalid request header")
        lowered = key.lower()
        if lowered in seen_headers:
            raise OpenCodeGoTransportContractError("duplicate request header")
        seen_headers.add(lowered)
        if lowered in {"authorization", "host", "content-length", "x-opencode-session"}:
            continue
        headers[key] = value
    headers["Authorization"] = f"Bearer {_credential(credential)}"
    headers["x-opencode-session"] = session
    if not any(key.lower() == "user-agent" for key in headers):
        headers["User-Agent"] = "Mastermind-X/1.0"
    return UpstreamRequest(
        url=urljoin(OPENCODE_GO_BASE_URL, path),
        headers=MappingProxyType(headers),
        body=bytes(request.body),
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
        expected_pool_generation: str | None = None,
    ) -> TransportReceipt:
        request = _freeze_request(request, replayable=self.max_rollovers > 0)
        if expected_pool_generation is not None and (not isinstance(expected_pool_generation, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_pool_generation)):
            raise OpenCodeGoTransportContractError("invalid expected pool generation")
        session = request.session_id
        sticky = _identifier(sticky_account_id, "sticky_account_id") if sticky_account_id else None
        excluded: list[str] = []
        attempted: list[str] = []
        generation: str | None = expected_pool_generation
        reason = "initial"
        last_refusal: tuple[AccountChoice, UpstreamResponse] | None = None

        while True:
            try:
                raw_choice = self.resolver(
                    ResolveRequest(
                        pool_id=self.pool_id,
                        session_id=session,
                        sticky_account_id=sticky,
                        excluded_account_ids=tuple(excluded),
                        reason=reason,
                    )
                )
            except Exception as exc:
                raise OpenCodeGoTransportContractError("provider account resolution failed") from None
            if raw_choice is None:
                if last_refusal is not None:
                    last_choice, last_response = last_refusal
                    return TransportReceipt(
                        response=last_response,
                        account_id=last_choice.account_id,
                        pool_generation=last_choice.pool_generation,
                        attempted_accounts=tuple(attempted),
                        rollover_count=max(0, len(attempted) - 1),
                        pool_exhausted=True,
                        stop_reason="no_eligible_account",
                    )
                raise OpenCodeGoPoolUnavailable("no eligible OpenCode Go account")
            choice = _choice(raw_choice, pool_id=self.pool_id)
            if generation is None:
                generation = choice.pool_generation
            elif generation != choice.pool_generation:
                raise OpenCodeGoTransportContractError("pool membership generation changed during inference")
            if choice.account_id in excluded or choice.account_id in attempted:
                raise OpenCodeGoTransportContractError("resolver repeated an excluded account")

            try:
                credential = _credential(self.credential_loader(choice.account_id))
            except OpenCodeGoTransportContractError:
                raise
            except Exception as exc:
                raise OpenCodeGoTransportContractError("provider credential unavailable") from None
            upstream = prepare_upstream_request(request, choice=choice, credential=credential)
            attempted.append(choice.account_id)
            try:
                response = self.sender(upstream)
            except Exception as exc:
                raise OpenCodeGoEffectUnknown(choice.account_id, tuple(attempted)) from None
            if (
                not isinstance(response, UpstreamResponse)
                or isinstance(response.status, bool)
                or not isinstance(response.status, int)
                or not 100 <= response.status <= 599
                or not isinstance(response.headers, Mapping)
                or not isinstance(response.body, (bytes, bytearray))
            ):
                raise OpenCodeGoEffectUnknown(choice.account_id, tuple(attempted))
            if isinstance(response.body, bytearray):
                response = UpstreamResponse(response.status, response.headers, bytes(response.body))

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

            last_refusal = (choice, response)
            if len(attempted) - 1 >= self.max_rollovers:
                return TransportReceipt(
                    response=response,
                    account_id=choice.account_id,
                    pool_generation=choice.pool_generation,
                    attempted_accounts=tuple(attempted),
                    rollover_count=len(attempted) - 1,
                    pool_exhausted=False,
                    stop_reason="rollover_budget_exhausted",
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
