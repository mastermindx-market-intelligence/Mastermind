"""Opt-in, stateless MCP Events request contract for canonical native reply events.

This is a protocol adapter, *not* an MCP server, subscriber registry, transport,
authentication service or callback sender. The existing authenticated Executive
host owns route/credential verification and passes a validated neutral principal.
The injected canonical subscription owner alone checks original-request custody,
performs verification through an SSRF-safe HTTPS transport, persists the grant,
handles refresh and revocation, and controls retries and actual outbound delivery.

Nothing in this module advertises event capability on the installed server.
Actual MCP 2.0 negotiation and method routing require separate host admission.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import re
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlsplit, unquote

from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.session_bridge.web_reply_events import EVENT_NAME, reply_event_definition
from integrations.session_bridge.web_reply_delivery import _SUB, _secret

VERSION = "2026-07-28"
READ_SCOPE = "mastermind.executive.read"
DEFAULT_TTL_MS = 3_600_000
MAX_TTL_MS = 7 * 24 * 60 * 60 * 1000
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_HOST = re.compile(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")
_MODERN_META = "io.modelcontextprotocol/protocolVersion"
_ALLOWED_METHODS = frozenset({"events/list", "events/subscribe", "events/unsubscribe"})


@dataclasses.dataclass(frozen=True)
class EventSubscribeRequest:
    """Validated untrusted request; destination and secret are NEVER authority."""
    request_ref: str
    callback_url: str = dataclasses.field(repr=False)
    signing_secret: str = dataclasses.field(repr=False)
    requested_ttl_ms: int
    event_name: str = EVENT_NAME


@dataclasses.dataclass(frozen=True)
class EventUnsubscribeRequest:
    request_ref: str
    callback_url: str = dataclasses.field(repr=False)
    event_name: str = EVENT_NAME


@dataclasses.dataclass(frozen=True)
class EventSubscriptionReceipt:
    """Admission *claim* from the current authorized subscription writer.

    The authenticated host alone must choose the trusted owner. A fixture
    returning these bytes proves no real verification/storage/admission.
    """
    subscription_id: str
    expires_at: int
    callback_verified: bool
    persisted: bool
    original_request_current: bool


@dataclasses.dataclass(frozen=True)
class EventUnsubscribeReceipt:
    stopped: bool
    committed: bool


class CallbackVerificationError(ValueError):
    """Only the subscribed host can report a categorical callback refusal."""
    def __init__(self, reason: str = "challenge_failed"):
        self.reason = reason if reason in {"challenge_failed", "timeout", "invalid_destination"} else "challenge_failed"
        super().__init__(self.reason)


class OriginalReplySubscriptionOwner(Protocol):
    async def can_discover(self, principal: NeutralPrincipalProjection) -> bool: ...
    async def subscribe(self, principal: NeutralPrincipalProjection,
                        requested: EventSubscribeRequest) -> EventSubscriptionReceipt: ...
    async def unsubscribe(self, principal: NeutralPrincipalProjection,
                          requested: EventUnsubscribeRequest) -> EventUnsubscribeReceipt: ...


def _closed_params(method: str, params: Any) -> tuple[str, str | None]:
    if type(params) is not dict:
        raise ValueError("invalid params")
    fields = {"_meta"}
    if method == "events/list":
        fields |= {"cursor"}
    elif method == "events/subscribe":
        fields |= {"name", "arguments", "delivery", "cursor", "ttlMs"}
    elif method == "events/unsubscribe":
        fields |= {"name", "arguments", "delivery"}
    else:
        raise ValueError("unsupported method")
    if set(params) - fields:
        raise ValueError("unexpected event parameters")
    meta = params.get("_meta", {})
    if type(meta) is not dict or (meta and meta != {_MODERN_META: VERSION}):
        raise ValueError("wrong protocol version")
    if method == "events/list":
        if params.get("cursor") is not None:
            raise ValueError("non-replayable catalog")
        return method, None
    if params.get("name") != EVENT_NAME or "arguments" not in params:
        raise ValueError("wrong event filter")
    args = params["arguments"]
    if type(args) is not dict or set(args) != {"request_ref"}:
        raise ValueError("event filter must contain one original request")
    ref = args["request_ref"]
    if type(ref) is not str or _ID.fullmatch(ref) is None:
        raise ValueError("invalid request reference")
    if method == "events/subscribe" and params.get("cursor") is not None:
        raise ValueError("unsupported event cursor")
    return method, ref


def _callback_url(value: Any) -> str:
    """Cheap static defense only; owner MUST resolve/connect safely per attempt."""
    if type(value) is not str or not 0 < len(value) <= 2048:
        raise ValueError("callback URL is unavailable")
    if any(ord(c) < 32 or ord(c) == 127 for c in unquote(value)):
        raise ValueError("control bytes in destination")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise ValueError("invalid callback URL") from None
    if (parts.scheme != "https" or not parts.netloc or not host
            or parts.username is not None or parts.password is not None
            or parts.fragment or port == 0 or parts.netloc.count("@")
            or host.endswith(".") or not host.isascii()):
        raise ValueError("invalid callback URL")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("local callback forbidden")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        # Even public IP literals are held; TLS original-host identity must be
        # bound to the DNS-verifying caller and to connection-time checks.
        raise ValueError("literal callback IP not allowed")
    if not _HOST.fullmatch(host) or any(
        label.startswith("-") or label.endswith("-") for label in host.split(".")
    ):
        raise ValueError("invalid callback hostname")
    return value


def _delivery(params: dict[str, Any], *, subscribe: bool) -> tuple[str, str | None]:
    d = params.get("delivery")
    required = {"mode", "url", "secret"} if subscribe else {"mode", "url"}
    if type(d) is not dict or set(d) != required or d.get("mode") != "webhook":
        raise ValueError("only signed webhook delivery supported")
    url = _callback_url(d.get("url"))
    secret = None
    if subscribe:
        _secret(d["secret"])
        secret = d["secret"]
    return url, secret


def _ttl(params: dict[str, Any]) -> int:
    requested = params.get("ttlMs", DEFAULT_TTL_MS)
    if requested is None:
        # A client may request no expiration, but this guarded profile grants
        # finite subscriptions only; the caller cannot force an endless watch.
        return DEFAULT_TTL_MS
    if type(requested) is not int or not 0 < requested <= MAX_TTL_MS:
        raise ValueError("requested subscription TTL out of bounds")
    return requested


def _validated_principal(principal: object, now: int) -> bool:
    if type(principal) is not NeutralPrincipalProjection or type(now) is not int:
        return False
    try:
        return bool(
            type(principal.issued_at) is int and type(principal.expires_at) is int
            and principal.issued_at <= now < principal.expires_at
            and type(principal.issuer) is str
            and principal.issuer_digest == hashlib.sha256(principal.issuer.encode("utf-8")).hexdigest()
            and type(principal.scopes) is tuple and READ_SCOPE in principal.scopes
        )
    except (UnicodeError, TypeError, ValueError):
        return False


def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _err(request_id: Any, code: int, message: str, reason: str | None = None) -> dict[str, Any]:
    details: dict[str, Any] = {"code": code, "message": message}
    if reason is not None:
        details["data"] = {"reason": reason}
    return {"jsonrpc": "2.0", "id": request_id, "error": details}


class WebReplyEventRpc:
    """One authenticated event protocol delegate, with no storage or HTTP."""

    def __init__(self, owner: OriginalReplySubscriptionOwner, *,
                 clock: Callable[[], int]):
        if (not callable(getattr(owner, "can_discover", None))
                or not callable(getattr(owner, "subscribe", None))
                or not callable(getattr(owner, "unsubscribe", None))
                or not callable(clock)):
            raise TypeError("existing authenticated subscription owner is required")
        self._owner = owner
        self._clock = clock

    async def handle(self, request: Any,
                     principal: NeutralPrincipalProjection) -> dict[str, Any]:
        request_id = request.get("id") if type(request) is dict else None
        if type(request_id) not in (str, int) or (
            type(request_id) is str and not 0 < len(request_id) <= 1024
        ):
            request_id = None
        if not _validated_principal(principal, self._clock()):
            return _err(request_id, -32001, "event authorization unavailable")
        if (type(request) is not dict or request_id is None or "id" not in request
                or set(request) - {"jsonrpc", "id", "method", "params"}
                or request.get("jsonrpc") != "2.0" or request.get("id") != request_id
                or request.get("method") not in _ALLOWED_METHODS):
            return _err(request_id, -32600, "invalid event protocol request")
        method = request["method"]
        params = request.get("params", {})
        # Pre-dispatch validation is strictly separate from owner effects.
        # A ValueError after dispatch can mean an ACK was lost after commit.
        try:
            _, ref = _closed_params(method, params)
            if method == "events/subscribe":
                url, secret = _delivery(params, subscribe=True)
                ttl = _ttl(params)
            elif method == "events/unsubscribe":
                url, _ = _delivery(params, subscribe=False)
        except (ValueError, TypeError):
            return _err(request_id, -32602, "invalid event parameters")
        try:
            if method == "events/list":
                allowed = await self._owner.can_discover(principal)
                if type(allowed) is not bool:
                    raise TypeError("owner discovery unavailable")
                return _ok(request_id, {"events": [reply_event_definition()] if allowed else []})
            if method == "events/subscribe":
                requested = EventSubscribeRequest(
                    request_ref=ref, callback_url=url,
                    signing_secret=secret, requested_ttl_ms=ttl,
                )
                receipt = await self._owner.subscribe(principal, requested)
                if (type(receipt) is not EventSubscriptionReceipt
                        or receipt.callback_verified is not True
                        or receipt.persisted is not True
                        or receipt.original_request_current is not True
                        or not _validated_principal(principal, self._clock())
                        or type(receipt.expires_at) is not int
                        or not self._clock() < receipt.expires_at
                        or receipt.expires_at > self._clock() + (ttl - 1) // 1000 + 1
                        or type(receipt.subscription_id) is not str
                        or _SUB.fullmatch(receipt.subscription_id) is None):
                    raise RuntimeError("unverified owner subscription effect")
                expires = datetime.fromtimestamp(receipt.expires_at, timezone.utc)
                return _ok(request_id, {
                    "id": receipt.subscription_id,
                    "refreshBefore": expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
                    "cursor": None, "truncated": False,
                })
            requested = EventUnsubscribeRequest(request_ref=ref, callback_url=url)
            receipt = await self._owner.unsubscribe(principal, requested)
            if (type(receipt) is not EventUnsubscribeReceipt
                    or receipt.stopped is not True or receipt.committed is not True
                    or not _validated_principal(principal, self._clock())):
                raise RuntimeError("original subscription withdrawal unknown")
            return _ok(request_id, {})
        except CallbackVerificationError as exc:
            return _err(request_id, -32015, "callback endpoint refused", exc.reason)
        except Exception:
            return _err(request_id, -32010, "existing subscription owner outcome unknown")


__all__ = ["VERSION", "WebReplyEventRpc", "OriginalReplySubscriptionOwner",
           "EventSubscribeRequest", "EventUnsubscribeRequest",
           "EventSubscriptionReceipt", "EventUnsubscribeReceipt",
           "CallbackVerificationError"]
