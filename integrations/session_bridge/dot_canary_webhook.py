"""Inert, owner-bound Standard Webhooks signer for one Chris-Dot Slack canary event.

Reuses the original Executive MCP Events signer/header format and HTTPS transport.
It owns no callback URL, OAuth identity, subscriber store, retry or Slack reader.
Only a fresh, owner-authorized and complete Slack observation may be projected and
signed; host code must still reauthorize immediately before sending.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from integrations.slack_agent_dialogue.dot_canary_event import (
    EVENT_NAME, MARKER, TrustedCanaryPolicy, canary_event_definition,
)
from .web_reply_delivery import (
    _EVENT, _SUB, _MAX_UNIX, _secret, _signed_packet, PreparedReplyWebhook,
)

_EVENT_FIELDS = frozenset({"eventId", "name", "timestamp", "data", "cursor"})
_DATA_FIELDS = frozenset({
    "workspace_id", "channel_id", "message_ts", "author_user_id",
    "thread_ts", "text", "untrusted_text",
})
_SLACK_TS = re.compile(r"^[0-9]{10,16}\.[0-9]{6}$")
_WORKSPACE = re.compile(r"^T[A-Z0-9]{8,31}$")
_CHANNEL = re.compile(r"^C[A-Z0-9]{8,31}$")
_USER = re.compile(r"^[UW][A-Z0-9]{8,31}$")
_PRINCIPAL = re.compile(r"^[0-9a-f]{64}$")


@dataclasses.dataclass(frozen=True)
class VerifiedCanarySubscription:
    """Trusted host projection of ONE stored, currently authorized subscription.

    Constructing this value cannot create OAuth/grant/storage authority. The host
    must check active subscription version, original account, sealed key rotation,
    current Slack read access and current callback policy before network I/O.
    """
    subscription_id: str
    principal_digest: str
    channel_id: str
    event_name: str
    expires_at: int
    authorized_until: int
    active: bool
    access_current: bool
    signing_secrets: tuple[str, ...] = dataclasses.field(repr=False)


def _validated_canary_event(
    event: Mapping[str, Any], policy: TrustedCanaryPolicy | None = None,
) -> bytes:
    """Validate exact canonical source-derived event, before DNS/socket usage.

    With no policy this performs only *structural* verification for the existing
    HTTP transport. The owner-supplied policy is required for signing.
    """
    if (type(event) is not dict or set(event) != _EVENT_FIELDS
            or type(event.get("eventId")) is not str
            or _EVENT.fullmatch(event["eventId"]) is None
            or event.get("name") != EVENT_NAME
            or event.get("cursor") is not None):
        raise ValueError("invalid canary event envelope")
    data = event.get("data")
    if type(data) is not dict or set(data) != _DATA_FIELDS:
        raise ValueError("invalid canary event data")
    workspace, channel, message_ts, author, text = (
        data[k] for k in ("workspace_id", "channel_id", "message_ts", "author_user_id", "text")
    )
    if (type(workspace) is not str or _WORKSPACE.fullmatch(workspace) is None
            or type(channel) is not str or _CHANNEL.fullmatch(channel) is None
            or type(author) is not str or _USER.fullmatch(author) is None
            or type(message_ts) is not str or _SLACK_TS.fullmatch(message_ts) is None
            or type(text) is not str or not text.startswith(MARKER)
            or not 0 < len(text) <= 360 or data["untrusted_text"] is not True):
        raise ValueError("invalid or unmarked canary message")
    thread_ts = data["thread_ts"]
    if thread_ts is not None and (
        type(thread_ts) is not str or _SLACK_TS.fullmatch(thread_ts) is None
    ):
        raise ValueError("invalid canary thread reference")
    try:
        seconds, micros = (int(x) for x in message_ts.split("."))
        if not 0 < seconds <= _MAX_UNIX:
            raise ValueError("canary timestamp out of range")
        timestamp = datetime.fromtimestamp(seconds,timezone.utc).replace(
            microsecond=micros,
        ).isoformat(timespec="microseconds").replace("+00:00","Z")
    except (OverflowError, OSError, ValueError):
        raise ValueError("invalid canary timestamp") from None
    if event["timestamp"] != timestamp:
        raise ValueError("canary event timestamp differs from Slack")
    material = [workspace, channel, message_ts, author, text]
    identity = hashlib.sha256(json.dumps(
        material, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")).hexdigest()
    if event["eventId"] != "evt-" + identity:
        raise ValueError("canary event identity differs from Slack message")
    if policy is not None:
        if type(policy) is not TrustedCanaryPolicy:
            raise ValueError("trusted canary policy required")
        canary_event_definition(policy)
        if (workspace != policy.workspace_id or channel != policy.channel_id
                or author != policy.owner_slack_user_id
                or (seconds, micros) <= tuple(
                    int(value) for value in policy.not_before_ts.split(".")
                )):
            raise ValueError("canary event not admitted by current policy")
    body = json.dumps(
        event, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    ).encode("ascii")
    if len(body) > 8192:
        raise ValueError("oversized signed canary event")
    return body


def prepare_canary_webhook(
    *, subscription: VerifiedCanarySubscription,
    policy: TrustedCanaryPolicy,
    event: Mapping[str, Any],
    signed_at: int,
) -> PreparedReplyWebhook:
    """Prepare a signed event; no network, storage, OAuth or Slack side effects."""
    if (type(subscription) is not VerifiedCanarySubscription
            or type(policy) is not TrustedCanaryPolicy
            or type(signed_at) is not int or not 0 < signed_at <= _MAX_UNIX
            or subscription.active is not True
            or subscription.access_current is not True
            or type(subscription.subscription_id) is not str
            or _SUB.fullmatch(subscription.subscription_id) is None
            or type(subscription.principal_digest) is not str
            or _PRINCIPAL.fullmatch(subscription.principal_digest) is None
            or subscription.principal_digest != policy.principal_digest
            or subscription.channel_id != policy.channel_id
            or subscription.event_name != EVENT_NAME
            or type(subscription.expires_at) is not int
            or type(subscription.authorized_until) is not int
            or not signed_at < subscription.expires_at <= subscription.authorized_until
            or policy.current is not True):
        raise ValueError("current account-bound canary subscription required")
    secrets = subscription.signing_secrets
    if type(secrets) is not tuple or not 1 <= len(secrets) <= 2:
        raise ValueError("invalid canary signing key count")
    keys = tuple(_secret(secret) for secret in secrets)
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate canary signing key")
    body = _validated_canary_event(event, policy)
    return _signed_packet(
        body=body, message_id=event["eventId"],
        subscription_id=subscription.subscription_id,
        signed_at=signed_at, keys=keys,
    )


__all__ = ["VerifiedCanarySubscription", "prepare_canary_webhook"]
