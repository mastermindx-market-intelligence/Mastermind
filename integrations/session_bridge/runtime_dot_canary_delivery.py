"""One-shot Chris-Dot callback consumer on the ORIGINAL Executive Runtime/A2 owners.

This is a bounded owner-invoked continuation, NOT a daemon, watcher, Slack
listener, account issuer, callback store, new HTTP client or retry engine.
The incumbent Executive service owns Runtime/AEAD and an existing A2 reader
owns Slack credentials. No user-provided model payload can be an observation.
Delivery reservation happens on the canonical Runtime BEFORE outbound I/O.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from integrations.slack_agent_dialogue.dot_canary_event import (
    VerifiedSlackCanaryMessage, project_canary_message,
)
from integrations.slack_agent_dialogue.dot_canary_reader import (
    ExistingA2CanaryReader, CanarySourceUnavailable,
)
from .installed_dot_canary_source import InstalledA2CanaryReader
from .installed import _principal
from .dot_canary_webhook import (
    VerifiedCanarySubscription, prepare_canary_webhook,
)
from .runtime_dot_canary_owner import RuntimeCanarySubscriptionOwner
from .runtime_dot_canary_subscriptions import (
    RuntimeCanarySubscriptionStore, CanaryDeliveryView,
)
from .runtime_reply_authorization import policy_fingerprint
from .web_reply_callback_transport import (
    send_once, CallbackHTTPReceipt, CallbackEffectUnknown,
    CallbackDestinationRefused,
)
from .web_reply_subscription_owner import owner_key


@dataclass(frozen=True)
class CanaryDeliveryResult:
    delivery_ref: str | None
    state: str
    fresh_send: bool
    dot_consumed: bool = False


class RuntimeCanaryDeliveryConsumer:
    def __init__(self, owner: RuntimeCanarySubscriptionOwner, *,
                 resolver=None, connector=None):
        if type(owner) is not RuntimeCanarySubscriptionOwner or not owner.enabled:
            raise TypeError("armed incumbent Runtime canary owner required")
        self.owner, self.store = owner, owner.store
        self.resolver, self.connector = resolver, connector

    def _authorize(self, view: CanaryDeliveryView, reader: ExistingA2CanaryReader):
        if type(view) is not CanaryDeliveryView or type(reader) not in (
            ExistingA2CanaryReader,InstalledA2CanaryReader):
            raise ValueError("original A2 source and sealed Runtime grant required")
        auth = view.authorization
        principal = _principal(auth["principal"])
        policy, digest, now = self.owner._current(principal)
        record = view.record
        if (record.owner_key != owner_key(principal)
                or record.source_policy_sha256 != digest
                or auth["source_policy_sha256"] != digest
                or auth["authorized_until"] != principal.expires_at
                or auth["owner_key"] != record.owner_key
                or auth["channel_id"] != record.channel_id
                or reader.policy != policy
                or record.channel_id != policy.channel_id):
            raise ValueError("stale or cross-account canary admission")
        return principal, policy, now

    def _fresh_packet(self, ident, version, reader, event, expected_account):
        snapshot = self.store._state(ident)[0]
        if (snapshot.record is None or snapshot.version != version
                or snapshot.record.owner_key != expected_account):
            raise ValueError("canary grant changed before send")
        view = self.store.delivery_view(
            ident,expected_version=version,owner_key=expected_account,
        )
        principal, policy, now = self._authorize(view,reader)
        if policy_fingerprint(self.owner.policies.select(principal)) != view.record.source_policy_sha256:
            raise ValueError("current event account policy differs")
        return view, prepare_canary_webhook(
            subscription=VerifiedCanarySubscription(
                subscription_id=ident,
                principal_digest=expected_account,
                channel_id=policy.channel_id,
                event_name=event["name"],
                expires_at=view.record.expires_at,
                authorized_until=view.record.authorized_until,
                active=True,access_current=True,
                signing_secrets=view.signing_secrets,
            ),
            policy=policy,event=event,signed_at=now,
        )

    async def deliver_one(self, reader: ExistingA2CanaryReader, *,
                          thread_ts: str, message_ts: str) -> tuple[CanaryDeliveryResult, ...]:
        """Explicit source-owner invocation for ONE existing Slack message.

        All current subscriptions are checked against the same authenticated
        Chris account. Any duplicate, ambiguous producer or stale resource
        is withheld. A 2xx proves only provider transport acknowledgment.
        """
        if type(reader) not in (ExistingA2CanaryReader,InstalledA2CanaryReader):
            raise TypeError("canonical A2 source required")
        if not self.owner.enabled:
            return (CanaryDeliveryResult(None,"NOT_ARMED",False),)
        ids = self.store.subscriptions_for_channel(reader.policy.channel_id)
        if not ids:
            return (CanaryDeliveryResult(None,"NO_SUBSCRIPTION",False),)
        # A canary intended for one Dot cannot broadcast to two arbitrary
        # callback URLs or foreign accounts.
        if len(ids) != 1:
            return (CanaryDeliveryResult(None,"AMBIGUOUS_AUDIENCE",False),)
        ident=ids[0]
        try:
            snap = await self.store.snapshot(ident)
            if snap.record is None:
                return (CanaryDeliveryResult(None,"NO_SUBSCRIPTION",False),)
            view = self.store.delivery_view(
                ident,expected_version=snap.version,owner_key=snap.record.owner_key,
            )
            principal,policy,_ = self._authorize(view,reader)
        except Exception:
            return (CanaryDeliveryResult(None,"AUTH_UNAVAILABLE",False),)
        try:
            observed = await reader.observe(thread_ts=thread_ts,message_ts=message_ts)
            if observed is None:
                return (CanaryDeliveryResult(None,"NOT_ELIGIBLE",False),)
            if type(observed) is not VerifiedSlackCanaryMessage:
                return (CanaryDeliveryResult(None,"SOURCE_UNAVAILABLE",False),)
            event = project_canary_message(
                policy, observed, authenticated_principal_digest=owner_key(principal),
                arguments={"channel_id":policy.channel_id},
            )
            if event is None:
                return (CanaryDeliveryResult(None,"NOT_ELIGIBLE",False),)
        except (CanarySourceUnavailable, ValueError):
            return (CanaryDeliveryResult(None,"SOURCE_UNAVAILABLE",False),)
        try:
            reservation = await self.store.reserve_delivery(
                ident=ident,version=snap.version,owner_key=snap.record.owner_key,
                event_id=event["eventId"],
            )
        except Exception:
            return (CanaryDeliveryResult(None,"AUTH_UNAVAILABLE",False),)
        if not reservation.fresh:
            return (CanaryDeliveryResult(
                reservation.delivery_ref,reservation.state,False),)
        outcome="EFFECT_UNKNOWN"
        status=None
        try:
            # Existing send_once performs DNS, pinned TLS and the adjacent
            # synchronous current-policy/store check on its original I/O lane.
            def one_call():
                fresh_view, packet = self._fresh_packet(
                    ident,snap.version,reader,event,snap.record.owner_key,
                )
                def before_request():
                    new_view,new_packet = self._fresh_packet(
                        ident,snap.version,reader,event,snap.record.owner_key,
                    )
                    if (new_view.callback_url != fresh_view.callback_url
                            or new_packet.body != packet.body):
                        raise CallbackDestinationRefused("canary grant changed")
                    return new_packet
                return send_once(
                    fresh_view.callback_url,packet,
                    resolver=self.resolver,connector=self.connector,
                    before_request=before_request,
                )
            receipt = await asyncio.to_thread(one_call)
            if type(receipt) is not CallbackHTTPReceipt:
                raise CallbackEffectUnknown("unverified callback response")
            status=receipt.status_code
            outcome="RECEIVED" if 200 <= status < 300 else "REFUSED"
        except CallbackDestinationRefused:
            outcome="REFUSED"
        except BaseException as exc:
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):
                raise
            outcome="EFFECT_UNKNOWN"
        # Settlement failure cannot authorize another send. Reservation
        # remains as a permanent original-operation fence.
        try:
            await self.store.settle_delivery(
                reservation.delivery_ref,outcome=outcome,status=status,
            )
        except Exception:
            return (CanaryDeliveryResult(
                reservation.delivery_ref,"EFFECT_UNKNOWN",True),)
        return (CanaryDeliveryResult(
            reservation.delivery_ref,outcome,True),)


__all__=["RuntimeCanaryDeliveryConsumer","CanaryDeliveryResult"]
