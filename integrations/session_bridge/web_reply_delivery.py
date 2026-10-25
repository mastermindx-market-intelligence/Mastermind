"""Inert Standard Webhooks encoder for already-authorized MCP reply events.

This is NOT an endpoint, subscriber store, networking client, replay/cursor owner,
retry engine or completion/consumption writer. An authenticated Executive host
must supply a freshly resolved, verified original-request subscription, recheck
current access, verify the callback destination, and own delivery/uncertainty.
The input event comes from the existing CanonicalReplyEventProjector. Nothing
in this module accepts a destination URL, chooses a recipient, or sends a POST.

Protocol: https://developers.openai.com/plugins/build/mcp-events
Signature: https://github.com/standard-webhooks/standard-webhooks
"""
from __future__ import annotations

import base64
import binascii
import dataclasses
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from .web_reply_events import EVENT_NAME

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SUB = re.compile(r"^sub[-_][A-Za-z0-9][A-Za-z0-9._:-]{0,126}$")
_EVENT = re.compile(r"^evt-[0-9a-f]{64}$")
_SHA_SECRET = re.compile(r"^whsec_[A-Za-z0-9+/]+={0,2}$")
_KEYS = frozenset({"eventId", "name", "timestamp", "data", "cursor"})
_DATA = frozenset({"request_ref", "message_key", "in_reply_to", "summary",
                   "read_ref", "reply_committed", "parent_consumed"})
_MAX_BYTES = 8192
_MAX_UNIX = 4102444800  # fixed limit avoids Python/platform-dependent overflow


@dataclasses.dataclass(frozen=True)
class VerifiedReplySubscription:
    """Current authenticated owner projection, not an authentication token.

    Construct this only in the existing installed subscription owner after it
    authenticates the caller, validates original request and callback, and
    checks live access and expiration. Class construction alone grants nothing.
    """
    subscription_id: str
    principal_ref: str
    request_ref: str
    event_name: str
    access_current: bool
    active: bool
    expires_at: int
    signing_secrets: tuple[str, ...] = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True)
class PendingReplyCallback:
    """Pre-verification callback projection from the existing authenticated owner.

    This is not a subscription, callback grant or persistence record.
    The owner must have validated destination and principal and generated a
    fresh single-use challenge before preparing a verification request.
    """
    subscription_id: str
    principal_ref: str
    request_ref: str
    access_current: bool
    expires_at: int
    signing_secret: str = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True)
class PreparedReplyWebhook:
    """Exact signed body/headers. Transport, status and acceptance unobserved."""
    body: bytes = dataclasses.field(repr=False)
    headers: Mapping[str, str] = dataclasses.field(repr=False)


def _identifier(value: Any, regex=_ID) -> str:
    if type(value) is not str or regex.fullmatch(value) is None:
        raise ValueError("invalid trusted identity")
    return value


def _secret(value: str) -> bytes:
    if type(value) is not str or _SHA_SECRET.fullmatch(value) is None:
        raise ValueError("invalid Standard Webhooks secret")
    try:
        raw = base64.b64decode(value[6:], validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("invalid Standard Webhooks secret") from None
    if not (24 <= len(raw) <= 64):
        raise ValueError("invalid Standard Webhooks key length")
    if base64.b64encode(raw).decode("ascii") != value[6:]:
        raise ValueError("noncanonical Standard Webhooks secret")
    return raw


def _validated_event(event: Mapping[str, Any], request_ref: str) -> bytes:
    if type(event) is not dict or set(event) != _KEYS:
        raise ValueError("event must be an exact canonical projection")
    _identifier(event["eventId"], _EVENT)
    if event["name"] != EVENT_NAME or event["cursor"] is not None:
        raise ValueError("wrong event or unsupported replay")
    timestamp = event["timestamp"]
    if type(timestamp) is not str or not timestamp.endswith("Z"):
        raise ValueError("event timestamp must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid event timestamp") from None
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("event timestamp must be UTC")
    data = event["data"]
    if type(data) is not dict or set(data) != _DATA:
        raise ValueError("event data is not the fixed read-only projection")
    for key in ("request_ref", "message_key", "in_reply_to", "read_ref"):
        _identifier(data[key])
    if (data["request_ref"] != request_ref
            or not data["message_key"].startswith("asd-native-reply-")
            or not data["in_reply_to"].startswith("asd-")
            or data["reply_committed"] is not True
            or data["parent_consumed"] is not False
            or type(data["summary"]) is not str
            or len(data["summary"]) > 360):
        raise ValueError("foreign or uncommitted original-parent event")
    body = json.dumps(event, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(body) > _MAX_BYTES:
        raise ValueError("webhook payload exceeds projection bound")
    return body


def _signed_packet(*, body: bytes, message_id: str, subscription_id: str,
                   signed_at: int, keys: tuple[bytes, ...]) -> PreparedReplyWebhook:
    timestamp = str(signed_at)
    signed = (message_id + "." + timestamp + ".").encode("ascii") + body
    signatures = [
        "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode("ascii")
        for key in keys
    ]
    return PreparedReplyWebhook(body=body, headers=MappingProxyType({
        "Content-Type": "application/json",
        "webhook-id": message_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": " ".join(signatures),
        "X-MCP-Subscription-Id": subscription_id,
    }))


def prepare_reply_webhook(*, subscription: VerifiedReplySubscription,
                          event: Mapping[str, Any], signed_at: int) -> PreparedReplyWebhook:
    """Purely encode/sign one retained event. Every attempt uses a fresh owner read.

    Only a caller with the original authorized subscription may call this.
    The installed HTTP owner MUST send these exact body bytes, authenticate the
    current subscription and URL, prohibit redirects/SSRF, and retain response
    evidence on the original carrier. A prepared result is NOT delivery.
    """
    if (type(subscription) is not VerifiedReplySubscription
            or subscription.access_current is not True or subscription.active is not True
            or type(signed_at) is not int or not 0 < signed_at <= _MAX_UNIX
            or type(subscription.expires_at) is not int
            or not signed_at < subscription.expires_at):
        raise ValueError("subscription current access/expiry not proven")
    _identifier(subscription.subscription_id, _SUB)
    _identifier(subscription.principal_ref)
    _identifier(subscription.request_ref)
    if subscription.event_name != EVENT_NAME:
        raise ValueError("foreign subscription event")
    secrets = subscription.signing_secrets
    if type(secrets) is not tuple or not 1 <= len(secrets) <= 2:
        raise ValueError("unsupported signing key count")
    keys = tuple(_secret(s) for s in secrets)
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate signing key")
    body = _validated_event(event, subscription.request_ref)
    return _signed_packet(body=body, message_id=event["eventId"],
                          subscription_id=subscription.subscription_id,
                          signed_at=signed_at, keys=keys)


_NONCE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_VERIFICATION_ID = re.compile(r"^msg_verification_[A-Za-z0-9_-]{10,80}$")


def prepare_reply_webhook_verification(*, callback: PendingReplyCallback,
                                       challenge: str, message_id: str,
                                       signed_at: int) -> PreparedReplyWebhook:
    """Sign a supplied fresh one-time challenge, but never perform verification.

    The authenticated owner must persist/consume nonce freshness and compare the
    exact callback response; this function cannot enroll or arm a subscription.
    """
    if (type(callback) is not PendingReplyCallback
            or callback.access_current is not True
            or type(signed_at) is not int or not 0 < signed_at <= _MAX_UNIX
            or type(callback.expires_at) is not int or signed_at >= callback.expires_at):
        raise ValueError("pending original-request callback not current")
    _identifier(callback.subscription_id, _SUB)
    _identifier(callback.principal_ref)
    _identifier(callback.request_ref)
    _identifier(challenge, _NONCE)
    _identifier(message_id, _VERIFICATION_ID)
    key = _secret(callback.signing_secret)
    body = json.dumps({"type": "verification", "challenge": challenge},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return _signed_packet(body=body, message_id=message_id,
                          subscription_id=callback.subscription_id,
                          signed_at=signed_at, keys=(key,))


def verify_reply_webhook_challenge_response(*, challenge: str,
                                             response_body: Any,
                                             status: Any) -> bool:
    """Inspect one response with no side effects or subscription-state transition.

    Success proves only challenge echo from this response, not current account
    access, callback origin, subscription storage or future event consumption.
    """
    if (type(challenge) is not str or _NONCE.fullmatch(challenge) is None
            or type(status) is not int or not 200 <= status < 300
            or type(response_body) is not bytes or len(response_body) > 512):
        return False

    def unique_object(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate callback key")
            out[key] = value
        return out
    try:
        data = json.loads(response_body, object_pairs_hook=unique_object)
    except (UnicodeDecodeError, ValueError):
        return False
    return (type(data) is dict and set(data) == {"challenge"}
            and type(data["challenge"]) is str
            and hmac.compare_digest(data["challenge"], challenge))


def classify_reply_webhook_response(status: Any) -> str:
    """Advisory observation only; never infer original-parent consumption.

    Retry eligibility is NOT permission to retry. The existing owner must
    reconcile effect uncertainty, retry budget and original subscription.
    """
    if type(status) is not int or not 100 <= status < 600:
        return "EFFECT_UNKNOWN"
    if 200 <= status < 300:
        return "TRANSPORT_ACCEPTED_PARENT_UNPROVEN"
    if status in (410, 413):
        return "DELIVERY_TERMINAL_REFUSAL"
    if status in (408, 429) or 500 <= status < 600:
        return "RETRY_DECISION_BY_EXISTING_OWNER"
    if 300 <= status < 400:
        return "REFUSED_NO_REDIRECT"
    return "DELIVERY_REFUSED"


__all__ = ["VerifiedReplySubscription", "PendingReplyCallback",
           "PreparedReplyWebhook", "prepare_reply_webhook",
           "prepare_reply_webhook_verification",
           "verify_reply_webhook_challenge_response",
           "classify_reply_webhook_response"]
