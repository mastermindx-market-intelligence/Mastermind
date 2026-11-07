"""Optional Chris-Dot event route inside the EXISTING Executive MCP Events RPC.

This file does not create a host, subscription store, Slack token, callback sender,
OAuth principal or delivery worker. The incumbent authenticated RPC may inject one
current, authorized owner; the default remains OFF. Only the incumbent Runtime
and HTTPS callback owners may persist or deliver a verified subscription.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.slack_agent_dialogue.dot_canary_event import (
    EVENT_NAME, TrustedCanaryPolicy, canary_event_definition,
)
from integrations.session_bridge.web_reply_subscription_owner import owner_key
from .web_reply_event_rpc import (
    VERSION, _MODERN_META, _SUB, _delivery, _err, _ok, _ttl,
    _validated_principal, CallbackVerificationError, READ_SCOPE,
)

# The existing Executive read OAuth grant is the only accepted ChatGPT scope.
# Chris-only access is additionally fenced by the sealed subject digest and
# exact channel policy; do not invent a new OAuth scope or widen AppPolicies.
CANARY_SCOPE = READ_SCOPE


@dataclasses.dataclass(frozen=True)
class CanarySubscribeRequest:
    channel_id: str
    callback_url: str = dataclasses.field(repr=False)
    signing_secret: str = dataclasses.field(repr=False)
    requested_ttl_ms: int = 0
    event_name: str = EVENT_NAME


@dataclasses.dataclass(frozen=True)
class CanaryUnsubscribeRequest:
    channel_id: str
    callback_url: str = dataclasses.field(repr=False)
    event_name: str = EVENT_NAME


@dataclasses.dataclass(frozen=True)
class CanarySubscriptionReceipt:
    subscription_id: str
    expires_at: int
    callback_verified: bool
    persisted: bool
    owner_access_current: bool


@dataclasses.dataclass(frozen=True)
class CanaryUnsubscribeReceipt:
    stopped: bool
    committed: bool


class CanarySubscriptionOwner(Protocol):
    """Only the existing authenticated owner may supply this; no generic backend."""

    async def policy_for(
        self, principal: NeutralPrincipalProjection,
    ) -> TrustedCanaryPolicy | None: ...

    async def subscribe(
        self, principal: NeutralPrincipalProjection, request: CanarySubscribeRequest,
    ) -> CanarySubscriptionReceipt: ...

    async def unsubscribe(
        self, principal: NeutralPrincipalProjection, request: CanaryUnsubscribeRequest,
    ) -> CanaryUnsubscribeReceipt: ...


async def _current_policy(
    owner: CanarySubscriptionOwner, principal: NeutralPrincipalProjection,
    clock: Callable[[], int],
) -> TrustedCanaryPolicy | None:
    """Bind the event to the current RESOURCE+ISSUER+SUBJECT+CLIENT, not a model name."""
    if not _validated_principal(principal, clock()) or CANARY_SCOPE not in principal.scopes:
        return None
    policy = await owner.policy_for(principal)
    if policy is None:
        return None
    if type(policy) is not TrustedCanaryPolicy:
        raise TypeError("trusted current canary policy required")
    if policy.principal_digest != owner_key(principal):
        return None
    canary_event_definition(policy)  # validate the closed current policy
    return policy


async def discover_canary(
    owner: CanarySubscriptionOwner, principal: NeutralPrincipalProjection,
    clock: Callable[[], int],
) -> dict[str, Any] | None:
    """Only explicitly authorized accounts see the otherwise hidden event."""
    policy = await _current_policy(owner, principal, clock)
    return canary_event_definition(policy) if policy is not None else None


def _validate_params(method: str, params: Any) -> str:
    if type(params) is not dict:
        raise ValueError("closed canary event params required")
    fields = {"name", "arguments", "delivery", "_meta"}
    if method == "events/subscribe":
        fields |= {"cursor", "ttlMs"}
    if set(params) - fields or params.get("name") != EVENT_NAME:
        raise ValueError("unexpected canary params")
    meta = params.get("_meta", {})
    if type(meta) is not dict or meta not in ({}, {_MODERN_META: VERSION}):
        raise ValueError("wrong protocol version")
    arguments = params.get("arguments")
    if type(arguments) is not dict or set(arguments) != {"channel_id"}:
        raise ValueError("one channel filter required")
    channel = arguments["channel_id"]
    if type(channel) is not str or not 0 < len(channel) <= 35:
        raise ValueError("invalid channel identity")
    if method == "events/subscribe" and params.get("cursor") is not None:
        raise ValueError("canary replay not supported")
    return channel


async def handle_canary(
    owner: CanarySubscriptionOwner,
    request_id: str | int,
    method: str,
    params: Any,
    principal: NeutralPrincipalProjection,
    clock: Callable[[], int],
) -> dict[str, Any]:
    """Delegated branch under the original WebReplyEventRpc's validated envelope."""
    if method not in {"events/subscribe", "events/unsubscribe"}:
        return _err(request_id, -32601, "unsupported event method")
    try:
        channel = _validate_params(method, params)
        callback, secret = _delivery(params, subscribe=method == "events/subscribe")
        ttl = _ttl(params) if method == "events/subscribe" else None
    except (ValueError, TypeError):
        return _err(request_id, -32602, "invalid canary event parameters")
    try:
        policy = await _current_policy(owner, principal, clock)
        if policy is None or policy.channel_id != channel:
            return _err(request_id, -32001, "canary event authorization unavailable")
        if method == "events/subscribe":
            receipt = await owner.subscribe(principal, CanarySubscribeRequest(
                channel_id=channel, callback_url=callback,
                signing_secret=secret, requested_ttl_ms=ttl,
            ))
            now = clock()
            if (type(receipt) is not CanarySubscriptionReceipt
                    or receipt.callback_verified is not True
                    or receipt.persisted is not True
                    or receipt.owner_access_current is not True
                    or type(receipt.subscription_id) is not str
                    or _SUB.fullmatch(receipt.subscription_id) is None
                    or type(receipt.expires_at) is not int
                    or not now < receipt.expires_at <= now + (ttl - 1) // 1000 + 1
                    or receipt.expires_at > principal.expires_at
                    or await _current_policy(owner, principal, clock) != policy):
                raise RuntimeError("unverified canary subscription effect")
            expires = datetime.fromtimestamp(receipt.expires_at, timezone.utc)
            return _ok(request_id, {
                "id": receipt.subscription_id,
                "refreshBefore": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "cursor": None, "truncated": False,
            })
        receipt = await owner.unsubscribe(principal, CanaryUnsubscribeRequest(
            channel_id=channel, callback_url=callback,
        ))
        if (type(receipt) is not CanaryUnsubscribeReceipt
                or receipt.stopped is not True
                or receipt.committed is not True
                or await _current_policy(owner, principal, clock) != policy):
            raise RuntimeError("canary withdrawal outcome unknown")
        return _ok(request_id, {})
    except CallbackVerificationError as exc:
        return _err(request_id, -32015, "callback endpoint refused", exc.reason)
    except Exception:
        # An owner callback or store commit might already have happened.
        return _err(request_id, -32010, "existing canary subscription outcome unknown")


__all__ = [
    "CANARY_SCOPE", "CanarySubscribeRequest", "CanaryUnsubscribeRequest",
    "CanarySubscriptionReceipt", "CanaryUnsubscribeReceipt",
    "CanarySubscriptionOwner", "discover_canary", "handle_canary",
]
