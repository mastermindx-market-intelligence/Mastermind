"""Opt-in MCP reply subscription adapter over an EXISTING authorized owner.

This module has NO persistent storage, credentials, sockets, default server
selection, callback sender, scheduler, retry loop or Executive lifecycle.
An installed owner must inject its exact canonical original-request resolver,
secret-sealing durable subscription store and bounded verified HTTPS callback
sender. Inert source and fake stores do not prove production persistence.

The injected store MUST atomically commit/replace an exactly bound subscriber
and encrypt its secret using the incumbent credential owner. The returned
public record contains only *digests*, not ciphertext, token or signing key.
Stored grant/readback is required before returning a subscription receipt.
No model-provided callback or request ref can replace the canonical owner.
"""
from __future__ import annotations

import dataclasses
import hashlib
import hmac
import json
import secrets
from typing import Any, Callable, Protocol

from control_plane.principal_projection import NeutralPrincipalProjection
from .web_reply_delivery import (
    PendingReplyCallback,
    _secret,
    prepare_reply_webhook_verification,
    verify_reply_webhook_challenge_response,
)
from .web_reply_event_rpc import (
    CallbackVerificationError,
    EventSubscribeRequest,
    EventSubscriptionReceipt,
    EventUnsubscribeRequest,
    EventUnsubscribeReceipt,
    READ_SCOPE,
    EVENT_NAME,
    _ID,
    _callback_url,
)

SCHEMA="mastermind.native_reply_subscription.v1"


class SubscriptionUnavailable(ValueError):
    """Original-request authorization or required local capability is absent."""


class SubscriptionConflict(SubscriptionUnavailable):
    """Known pre-write CAS conflict; no replacement is authorized."""


class SubscriptionEffectUnknown(RuntimeError):
    """A callback or durable effect may have happened; same owner must reconcile."""


@dataclasses.dataclass(frozen=True,slots=True)
class OriginalReplyGrant:
    """Trusted and freshly resolved canonical original-request rights."""
    owner_key: str
    request_ref: str
    read_ref: str
    revision: str
    access_current: bool
    expires_at: int


@dataclasses.dataclass(frozen=True,slots=True)
class VerifiedChallengeHTTP:
    """Bounded, untrusted HTTP observation; NOT subscription acceptance."""
    status_code: int
    response_body: bytes = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True,slots=True)
class StoredReplySubscription:
    """Store's current, sealed-and-committed *metadata* readback."""
    subscription_id: str
    owner_key: str
    request_ref: str
    callback_url_digest: str
    signing_secret_digest: str
    read_ref: str
    revision: str
    expires_at: int
    verified_at: int
    schema: str=SCHEMA


@dataclasses.dataclass(frozen=True,slots=True)
class SubscriptionSnapshot:
    record: StoredReplySubscription | None
    version: str
    binding: tuple[str,str,str] | None


class OriginalRequestResolver(Protocol):
    async def resolve(self, principal: NeutralPrincipalProjection,
                      request_ref: str) -> OriginalReplyGrant: ...


class CanonicalSubscriptionStore(Protocol):
    """This MUST be the incumbent writer/credential store, never a new registry.

    The store implementation must seal the signing_secret at rest and bind
    transactions to subscription_id/owner_key; commit must be atomic and
    idempotent. An async return is not enough: readback is required.
    """
    async def snapshot(self, subscription_id: str) -> SubscriptionSnapshot: ...
    async def commit(self, record: StoredReplySubscription,
                     signing_secret: str, *, callback_url: str,
                     expected_version: str) -> StoredReplySubscription: ...
    async def read(self, subscription_id: str) -> StoredReplySubscription | None: ...
    async def remove(self, subscription_id: str, owner_key: str, *,
                     request_ref: str, callback_url_digest: str,
                     expected_version: str) -> None: ...


class ChallengeSender(Protocol):
    """Owner-controlled HTTPS I/O lane: pinned TLS, no redirects/retry."""
    async def verify(self, callback_url: str,
                     packet: Any) -> VerifiedChallengeHTTP: ...


def owner_key(principal: NeutralPrincipalProjection) -> str:
    """Pseudonymous stable original account key, no raw tokens/subjects in state."""
    if type(principal) is not NeutralPrincipalProjection:
        raise SubscriptionUnavailable("current principal required")
    try:
        components=(principal.policy_id,principal.issuer_digest,principal.resource,
                    principal.subject_digest,principal.client_ref)
        if any(type(value) is not str or not value for value in components):
            raise ValueError
        encoded=json.dumps(components,ensure_ascii=True,
                           separators=(",",":"),allow_nan=False).encode("ascii")
    except (ValueError,TypeError,UnicodeError):
        raise SubscriptionUnavailable("current principal identity unavailable") from None
    return hashlib.sha256(b"mastermind.reply-event.owner.v1\0"+encoded).hexdigest()


def _subscription_id(principal_key: str, request_ref: str, url: str) -> str:
    identity=json.dumps([principal_key,EVENT_NAME,request_ref,url],
                        ensure_ascii=True,separators=(",",":")).encode("ascii")
    # The deterministic ID is an identifier, NEVER an authorization token.
    return "sub_"+hashlib.sha256(
        b"mastermind.reply-event.subscription.v1\0"+identity
    ).hexdigest()[:40]


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _current_grant(grant: Any, principal_key: str, request_ref: str,
                   timestamp: int) -> OriginalReplyGrant:
    if (type(grant) is not OriginalReplyGrant
            or grant.access_current is not True
            or grant.owner_key != principal_key
            or grant.request_ref != request_ref
            or type(grant.read_ref) is not str
            or _ID.fullmatch(grant.read_ref) is None
            or type(grant.revision) is not str
            or _ID.fullmatch(grant.revision) is None
            or type(grant.expires_at) is not int
            or timestamp >= grant.expires_at):
        raise SubscriptionUnavailable("original request not currently available")
    return grant


def _current_store_readback(value: Any, expected: StoredReplySubscription) -> bool:
    return type(value) is StoredReplySubscription and value == expected


class OriginalReplySubscriptionAdapter:
    """No other state than immutable dependency bindings; opt-in only."""

    def __init__(self, *, resolver: OriginalRequestResolver,
                 storage: CanonicalSubscriptionStore,
                 challenge_sender: ChallengeSender,
                 clock: Callable[[],int],
                 enabled: bool=False) -> None:
        if (not callable(getattr(resolver,"resolve",None))
                or not callable(getattr(storage,"commit",None))
                or not callable(getattr(storage,"read",None))
                or not callable(getattr(storage,"snapshot",None))
                or not callable(getattr(storage,"remove",None))
                or not callable(getattr(challenge_sender,"verify",None))
                or not callable(clock) or type(enabled) is not bool):
            raise TypeError("existing canonical authorization/store/callback owners required")
        self._resolver=resolver
        self._store=storage
        self._sender=challenge_sender
        self._clock=clock
        self._enabled=enabled

    def _admitted(self, principal: NeutralPrincipalProjection) -> tuple[str,int]:
        now=self._clock()
        if (not self._enabled or type(now) is not int
                or type(principal) is not NeutralPrincipalProjection
                or type(principal.issued_at) is not int
                or type(principal.expires_at) is not int
                or not principal.issued_at <= now < principal.expires_at
                or type(principal.scopes) is not tuple
                or READ_SCOPE not in principal.scopes):
            raise SubscriptionUnavailable("event subscription owner not admitted")
        return owner_key(principal),now

    async def can_discover(self, principal: NeutralPrincipalProjection) -> bool:
        try:
            self._admitted(principal)
            return True
        except SubscriptionUnavailable:
            return False

    async def subscribe(self, principal: NeutralPrincipalProjection,
                        requested: EventSubscribeRequest) -> EventSubscriptionReceipt:
        key,now=self._admitted(principal)
        if (type(requested) is not EventSubscribeRequest
                or requested.event_name!=EVENT_NAME
                or type(requested.request_ref) is not str
                or _ID.fullmatch(requested.request_ref) is None
                or type(requested.requested_ttl_ms) is not int
                or not 0<requested.requested_ttl_ms<=604800000):
            raise SubscriptionUnavailable("invalid original event request")
        try:
            url=_callback_url(requested.callback_url)
            _secret(requested.signing_secret)
        except (ValueError,TypeError):
            raise SubscriptionUnavailable("invalid signed callback") from None
        # Resolve the canonical owner BEFORE creating a verification effect.
        try:
            grant=_current_grant(await self._resolver.resolve(
                principal,requested.request_ref),key,requested.request_ref,now)
        except Exception:
            raise SubscriptionUnavailable("original request unavailable") from None

        # Grant finite TTL only, limited by caller request, current token and
        # original-request generation. Millisecond durations round down.
        expires=min(now+requested.requested_ttl_ms//1000,
                    grant.expires_at,principal.expires_at)
        if expires <= now:
            raise SubscriptionUnavailable("event subscription lifetime too short")
        subscription_id=_subscription_id(key,requested.request_ref,url)
        # Reuse ONLY canonical persisted verification evidence. This is not a
        # new cache, in-memory registry or invented owner. The stored proof
        # remains tied to account, original request, URL, secret and generation.
        try:
            before_snapshot=await self._store.snapshot(subscription_id)
            if type(before_snapshot) is not SubscriptionSnapshot or type(before_snapshot.version) is not str:
                raise ValueError("canonical subscription snapshot required")
            prior=before_snapshot.record
        except Exception:
            raise SubscriptionUnavailable("current subscription read unavailable") from None
        if prior is not None and (
                type(prior) is not StoredReplySubscription
                or prior.subscription_id!=subscription_id
                or prior.owner_key!=key
                or prior.request_ref!=requested.request_ref
                or prior.callback_url_digest!=_digest(url)
                or prior.schema!=SCHEMA):
            raise SubscriptionUnavailable("foreign canonical subscription identity")
        cached=bool(
            prior is not None
            and prior.signing_secret_digest==_digest(requested.signing_secret)
            and prior.read_ref==grant.read_ref
            and prior.revision==grant.revision
            and type(prior.verified_at) is int
            and prior.verified_at<=now
            and now-prior.verified_at<=300
            and type(prior.expires_at) is int
            and now<prior.expires_at
        )
        if not cached:
            nonce=secrets.token_urlsafe(24)
            msg="msg_verification_"+secrets.token_hex(16)
            pending=PendingReplyCallback(
                subscription_id=subscription_id,principal_ref=key,
                request_ref=requested.request_ref,access_current=True,
                expires_at=expires,signing_secret=requested.signing_secret)
            packet=prepare_reply_webhook_verification(
                callback=pending,challenge=nonce,message_id=msg,signed_at=now)
            # Once network verification begins, absence/timeout is not proof
            # the callback was never received. Never auto-resubmit.
            try:
                observed=await self._sender.verify(url,packet)
            except BaseException as exc:
                if isinstance(exc,(KeyboardInterrupt,SystemExit)):
                    raise
                raise SubscriptionEffectUnknown("callback verification effect uncertain") from None
            if (type(observed) is not VerifiedChallengeHTTP
                    or not verify_reply_webhook_challenge_response(
                        challenge=nonce,response_body=observed.response_body,
                        status=observed.status_code)):
                raise CallbackVerificationError("challenge_failed")

        # A callback could succeed while original access is revoked: compare
        # exact generation/read owner again before touching durable state.
        try:
            after_verify=self._clock()
            if (type(after_verify) is not int or after_verify >= expires
                    or after_verify >= principal.expires_at):
                raise SubscriptionUnavailable("original request or subscription expired")
            refreshed=_current_grant(await self._resolver.resolve(
                principal,requested.request_ref),key,requested.request_ref,after_verify)
        except Exception:
            raise SubscriptionUnavailable("original request changed") from None
        if refreshed != grant:
            raise SubscriptionUnavailable("original request generation changed")

        record=StoredReplySubscription(
            subscription_id=subscription_id,owner_key=key,
            request_ref=requested.request_ref,
            callback_url_digest=_digest(url),
            signing_secret_digest=_digest(requested.signing_secret),
            read_ref=grant.read_ref,revision=grant.revision,
            expires_at=expires,verified_at=prior.verified_at if cached else now,
        )
        if cached and _current_store_readback(prior,record):
            # A prior attempt may have committed before losing its ACK.
            # Reconcile the SAME exact durable fact twice and return without
            # issuing a duplicate mutation, challenge or new operation.
            try:
                current_snapshot=await self._store.snapshot(subscription_id)
                current_again=current_snapshot.record
                if current_snapshot.version != before_snapshot.version:
                    raise ValueError("subscription version changed")
            except Exception:
                raise SubscriptionEffectUnknown("original committed subscription readback unknown") from None
            if not _current_store_readback(current_again,record):
                raise SubscriptionEffectUnknown("original committed subscription changed")
            return EventSubscriptionReceipt(subscription_id,expires,True,True,True)
        try:
            written=await self._store.commit(record,requested.signing_secret,
                callback_url=url,expected_version=before_snapshot.version)
            current=await self._store.read(subscription_id)
        except SubscriptionConflict:
            raise
        except BaseException as exc:
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):
                raise
            raise SubscriptionEffectUnknown("original subscription persistence effect uncertain") from None
        if (not _current_store_readback(written,record)
                or not _current_store_readback(current,record)):
            raise SubscriptionEffectUnknown("original subscription durable readback failed")
        # Durable commit can race with account revocation, generation changes,
        # or expiry. Never report a completed current grant using an old read.
        try:
            after_commit=self._clock()
            if (type(after_commit) is not int or after_commit >= expires
                    or after_commit >= principal.expires_at):
                raise SubscriptionEffectUnknown("subscription expired during commit")
            final_grant=_current_grant(await self._resolver.resolve(
                principal,requested.request_ref),key,requested.request_ref,after_commit)
            if final_grant != grant:
                raise SubscriptionEffectUnknown("original request changed during commit")
        except Exception:
            raise SubscriptionEffectUnknown("post-commit grant not current") from None
        return EventSubscriptionReceipt(subscription_id,expires,True,True,True)

    async def unsubscribe(self,principal: NeutralPrincipalProjection,
                          requested: EventUnsubscribeRequest) -> EventUnsubscribeReceipt:
        key,now=self._admitted(principal)
        if (type(requested) is not EventUnsubscribeRequest
                or requested.event_name!=EVENT_NAME
                or type(requested.request_ref) is not str
                or _ID.fullmatch(requested.request_ref) is None):
            raise SubscriptionUnavailable("invalid original unsubscribe")
        try:
            url=_callback_url(requested.callback_url)
        except Exception:
            raise SubscriptionUnavailable("original unsubscribe authority unavailable") from None
        subscription_id=_subscription_id(key,requested.request_ref,url)
        try:
            snapshot=await self._store.snapshot(subscription_id)
            if type(snapshot) is not SubscriptionSnapshot:
                raise ValueError("canonical subscription snapshot required")
            if snapshot.binding is not None and snapshot.binding != (key,requested.request_ref,_digest(url)):
                raise SubscriptionUnavailable("foreign subscription")
            await self._store.remove(subscription_id,key,request_ref=requested.request_ref,
                callback_url_digest=_digest(url),expected_version=snapshot.version)
            remaining=await self._store.read(subscription_id)
        except SubscriptionConflict:
            raise
        except BaseException as exc:
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):
                raise
            raise SubscriptionEffectUnknown("original unsubscribe effect uncertain") from None
        if remaining is not None:
            raise SubscriptionEffectUnknown("original unsubscribe readback not clear")
        return EventUnsubscribeReceipt(stopped=True,committed=True)


__all__=["SubscriptionUnavailable","SubscriptionEffectUnknown","SubscriptionConflict","SubscriptionSnapshot",
         "OriginalReplyGrant","VerifiedChallengeHTTP",
         "StoredReplySubscription","OriginalRequestResolver",
         "CanonicalSubscriptionStore","ChallengeSender","owner_key",
         "OriginalReplySubscriptionAdapter"]
