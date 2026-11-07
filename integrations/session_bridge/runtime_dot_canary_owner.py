"""Owner-side Chris-Dot MCP event subscriptions on incumbent Executive Runtime.

No alternate OAuth system, Slack consumer, queue, timer, key store, callback
listener or retry path. The installed authenticated Executive owner MUST inject
its current sealed policy selection and exact single-account canary policy.
The only storage is the existing Runtime event DB/AEAD key.
"""
from __future__ import annotations

import dataclasses
import hashlib
import secrets
from collections.abc import Callable

from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.slack_agent_dialogue.dot_canary_event import TrustedCanaryPolicy, canary_event_definition
from .dot_canary_mcp_route import (
    CANARY_SCOPE, CanarySubscribeRequest, CanaryUnsubscribeRequest,
    CanarySubscriptionReceipt, CanaryUnsubscribeReceipt,
)
from .reply_policy_selection import ReplyPolicySelection, ReplyPolicyDenied
from .runtime_dot_canary_subscriptions import (
    CanaryRecord, RuntimeCanarySubscriptionStore, subscription_id, _digest,
)
from .runtime_reply_authorization import policy_fingerprint
from .web_reply_delivery import (
    PendingReplyCallback, prepare_reply_webhook_verification,
    verify_reply_webhook_challenge_response, _secret,
)
from .web_reply_event_rpc import (
    _callback_url, _validated_principal, CallbackVerificationError,
)
from .web_reply_subscription_owner import (
    VerifiedChallengeHTTP, SubscriptionConflict, SubscriptionUnavailable,
    SubscriptionEffectUnknown, owner_key,
)


class RuntimeCanarySubscriptionOwner:
    """No principal source: injected host derives it from its verified JWT."""

    def __init__(self, store: RuntimeCanarySubscriptionStore,
                 policies: ReplyPolicySelection, challenge_sender,
                 *, policy_provider: Callable[[NeutralPrincipalProjection], TrustedCanaryPolicy | None],
                 clock: Callable[[], int], enabled: bool = False):
        if (type(store) is not RuntimeCanarySubscriptionStore
                or not isinstance(policies, ReplyPolicySelection)
                or not callable(getattr(challenge_sender, "verify", None))
                or not callable(policy_provider)
                or not callable(clock) or type(enabled) is not bool):
            raise TypeError("existing Runtime, authenticated policies and challenge owner required")
        self.store, self.policies = store, policies
        self.challenge, self.policy_provider = challenge_sender, policy_provider
        self.clock, self.enabled = clock, enabled

    def _now(self):
        now = self.clock()
        if type(now) is not int or not 0 < now <= 4102444800:
            raise SubscriptionUnavailable("clock unavailable")
        return now

    def _current(self, principal):
        now = self._now()
        if (not self.enabled or not _validated_principal(principal, now)
                or CANARY_SCOPE not in principal.scopes):
            raise SubscriptionUnavailable("canary principal not admitted")
        try:
            source = self.policies.select(principal)
        except ReplyPolicyDenied:
            raise SubscriptionUnavailable("original account policy denied") from None
        selected = self.policy_provider(principal)
        if selected is None:
            raise SubscriptionUnavailable("Chris account not enrolled")
        if type(selected) is not TrustedCanaryPolicy or selected.current is not True:
            raise SubscriptionUnavailable("current canary policy unavailable")
        if selected.principal_digest != owner_key(principal):
            raise SubscriptionUnavailable("cross-account canary policy")
        canary_event_definition(selected)
        return selected, policy_fingerprint(source), now

    async def policy_for(self, principal):
        try:
            return self._current(principal)[0]
        except SubscriptionUnavailable:
            return None

    def _current_again(self, principal, expected, digest):
        selected, source, now = self._current(principal)
        if selected != expected or source != digest:
            raise SubscriptionUnavailable("canary owner policy changed")
        return now

    async def subscribe(self, principal: NeutralPrincipalProjection,
                        request: CanarySubscribeRequest) -> CanarySubscriptionReceipt:
        if (type(request) is not CanarySubscribeRequest
                or type(request.requested_ttl_ms) is not int
                or not 0 < request.requested_ttl_ms <= 604800000):
            raise SubscriptionUnavailable("invalid canary subscription request")
        policy, source, now = self._current(principal)
        if request.channel_id != policy.channel_id:
            raise SubscriptionUnavailable("foreign canary channel")
        try:
            url = _callback_url(request.callback_url)
            _secret(request.signing_secret)
        except Exception:
            raise SubscriptionUnavailable("invalid subscribed callback") from None
        expires = min(now + request.requested_ttl_ms // 1000, principal.expires_at)
        if expires <= now:
            raise SubscriptionUnavailable("canary subscription token expires too soon")
        key = owner_key(principal)
        ident = subscription_id(key, policy.channel_id, url)
        try:
            before = await self.store.snapshot(ident)
            prior = before.record
        except Exception:
            raise SubscriptionUnavailable("canary Runtime snapshot unavailable") from None
        if prior is not None and (prior.owner_key != key or prior.channel_id != policy.channel_id
                                  or prior.callback_url_digest != _digest(url)):
            raise SubscriptionUnavailable("foreign canary subscription")
        cached = bool(
            prior is not None and prior.signing_secret_digest == _digest(request.signing_secret)
            and prior.source_policy_sha256 == source
            and prior.authorized_until == principal.expires_at
            and prior.verified_at <= now < prior.expires_at
            and now - prior.verified_at <= 300
        )
        if not cached:
            nonce = secrets.token_urlsafe(24)
            msg = "msg_verification_" + secrets.token_hex(16)
            pending = PendingReplyCallback(
                subscription_id=ident, principal_ref=key,
                request_ref=policy.channel_id, access_current=True,
                expires_at=expires, signing_secret=request.signing_secret,
            )
            packet = prepare_reply_webhook_verification(
                callback=pending, challenge=nonce, message_id=msg, signed_at=now,
            )
            # One original callback attempt. A timeout is EFFECT_UNKNOWN, not a
            # reason to retry on another transport or replace the subscription.
            try:
                observed = await self.challenge.verify(url, packet)
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    raise
                raise SubscriptionEffectUnknown("callback challenge outcome unknown") from None
            if (type(observed) is not VerifiedChallengeHTTP
                    or not verify_reply_webhook_challenge_response(
                        challenge=nonce, response_body=observed.response_body,
                        status=observed.status_code)):
                raise CallbackVerificationError("challenge_failed")

        after_verify = self._current_again(principal, policy, source)
        if after_verify >= expires:
            raise SubscriptionUnavailable("subscription expired during verification")
        record = CanaryRecord(
            subscription_id=ident, owner_key=key, channel_id=policy.channel_id,
            callback_url_digest=_digest(url),
            signing_secret_digest=_digest(request.signing_secret),
            source_policy_sha256=source,
            verified_at=prior.verified_at if cached else now,
            expires_at=expires, authorized_until=principal.expires_at,
        )
        if prior == record and cached:
            try:
                same = await self.store.snapshot(ident)
            except Exception:
                raise SubscriptionEffectUnknown("original canary readback unavailable") from None
            if same != before:
                raise SubscriptionEffectUnknown("original canary version changed")
            return CanarySubscriptionReceipt(ident, expires, True, True, True)
        grant = dataclasses.asdict(principal)
        grant["scopes"] = list(principal.scopes)
        authorization = {
            "principal": grant,
            "owner_key": key,
            "channel_id": policy.channel_id,
            "source_policy_sha256": source,
            "authorized_until": principal.expires_at,
        }
        try:
            committed = await self.store.commit(
                record, request.signing_secret, callback_url=url,
                authorization=authorization, expected_version=before.version,
            )
            readback = await self.store.read(ident)
        except SubscriptionConflict:
            raise
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise SubscriptionEffectUnknown("canary persistent effect unknown") from None
        if committed != record or readback != record:
            raise SubscriptionEffectUnknown("canary subscription readback not proven")
        try:
            after_commit = self._current_again(principal, policy, source)
            if after_commit >= expires:
                raise SubscriptionUnavailable("subscription expired after commit")
        except Exception:
            raise SubscriptionEffectUnknown("post-commit canary policy unknown") from None
        return CanarySubscriptionReceipt(ident, expires, True, True, True)

    async def unsubscribe(self, principal: NeutralPrincipalProjection,
                          request: CanaryUnsubscribeRequest) -> CanaryUnsubscribeReceipt:
        if type(request) is not CanaryUnsubscribeRequest:
            raise SubscriptionUnavailable("invalid canary unsubscribe")
        policy, source, now = self._current(principal)
        if request.channel_id != policy.channel_id:
            raise SubscriptionUnavailable("unowned canary channel")
        try:
            url = _callback_url(request.callback_url)
        except Exception:
            raise SubscriptionUnavailable("invalid unsubscribe URL") from None
        key = owner_key(principal)
        ident = subscription_id(key, policy.channel_id, url)
        try:
            before = await self.store.snapshot(ident)
            await self.store.remove(
                ident, owner_key=key, channel_id=policy.channel_id,
                callback_url_digest=_digest(url), expected_version=before.version,
            )
            after = await self.store.read(ident)
        except SubscriptionConflict:
            raise
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise SubscriptionEffectUnknown("original canary revoke effect unknown") from None
        if after is not None:
            raise SubscriptionEffectUnknown("revoke readback not empty")
        # Account revocation after the commit cannot make a recorded withdrawal
        # false; fresh policy is not required to report an already durable stop.
        return CanaryUnsubscribeReceipt(stopped=True, committed=True)
