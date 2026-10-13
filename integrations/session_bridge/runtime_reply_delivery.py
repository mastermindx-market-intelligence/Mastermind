"""Default-disabled executable reply delivery for a CURRENT authenticated caller.

The existing host must provide VerifiedPrincipal from its real JWT owner. This
module cannot recover fresh account authority from persisted identity digests or
from a native worker. No listener/tool, token cache, watcher or background hook is
installed here. Native-COMMIT wiring/current original-account issuance remain
separate installation obligations. Reader calls never trigger outbound effects.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
from typing import Any

from integrations.business_mcp_auth.principal_projection import principal_projection
from integrations.slack_agent_dialogue.contract_v2 import validate_message_v2
from integrations.slack_agent_dialogue.service import CONTROL_VERSION_V2
from .native_read import NativeReplyReader
from .runtime_return import RuntimeSessionReturn
from .runtime_reply_subscriptions import RuntimeReplySubscriptionStore
from .web_reply_subscription_owner import owner_key
from .web_reply_events import CanonicalReplyEventProjector, ReplyEventBinding, EVENT_NAME
from .web_reply_delivery import VerifiedReplySubscription, prepare_reply_webhook, classify_reply_webhook_response
from .web_reply_callback_transport import send_once, CallbackDestinationRefused, CallbackHTTPReceipt


class ReplyDeliveryUnavailable(ValueError):
    """Current original account/read/subscription authority is unavailable."""


@dataclasses.dataclass(frozen=True)
class ResolvedReplyEvent:
    event: dict[str, Any]
    read_ref: str
    principal_ref: str


class RuntimeReplyEventResolver:
    """Actual async authorized reads; synchronous projection receives their snapshot."""
    def __init__(self, owner: RuntimeSessionReturn, *, clock):
        if type(owner) is not RuntimeSessionReturn or not callable(clock):
            raise TypeError("exact canonical read owner required")
        self._owner = owner
        self._reader = NativeReplyReader(owner, socket_path=owner.socket_path,
            service_call=owner.service_call, clock=clock)

    def current(self, principal):
        # Existing edge projection and reader lifetime/READ checks, no new auth.
        try:
            principal_projection(principal)
            return self._reader._current_principal(principal)
        except Exception:
            raise ReplyDeliveryUnavailable("current original READ principal required") from None

    async def resolve(self, principal, request_ref):
        try:
            projection = self.current(principal)
            event = self._owner.runtime.events.get_event_by_command_id(request_ref)
            if event is None:
                raise ValueError
            read_ref = event.payload["read_ref"]
            stored, value = self._owner._stored_request(read_ref)
            if stored.to_dict() != event.to_dict() or stored.command_id != request_ref:
                raise ValueError
            # resolve_read retains exact committed read provenance after cleanup.
            # _request/fresh subscription admission is intentionally not reused.
            binding = await self._owner.resolve_read(principal=projection, read_ref=read_ref)
            if binding.request_ref != request_ref:
                raise ValueError
            snapshot = json.dumps(dataclasses.asdict(binding), sort_keys=True, allow_nan=False)
            response = await self._owner.service_call(self._owner.socket_path, {
                "version": CONTROL_VERSION_V2, "operation": "read_thread",
                "args": {"context": binding.context.normalized(), "thread_ts": binding.thread_ts}})
            if type(response) is not dict or response.get("ok") is not True:
                raise ValueError
            data = response["result"]
            if (type(data) is not dict or data.get("thread_ts") != binding.thread_ts
                    or data.get("historical_messages") != [] or type(data.get("mutated_count")) is not int
                    or data["mutated_count"] != 0 or type(data.get("messages")) is not list or len(data["messages"]) > 256):
                raise ValueError
            matches = []
            for item in data["messages"]:
                if type(item) is not dict:
                    raise ValueError
                message = validate_message_v2(item["message"])
                if message["message_key"] == binding.reply_message_key:
                    matches.append((message, item["primary_ts"]))
            if len(matches) != 1 or matches[0][0]["fingerprint"] != binding.reply_fingerprint:
                raise ValueError
            refreshed = self.current(principal)
            after = await self._owner.resolve_read(principal=refreshed, read_ref=read_ref)
            if json.dumps(dataclasses.asdict(after), sort_keys=True, allow_nan=False) != snapshot:
                raise ValueError
            self.current(principal)
            public_principal = owner_key(refreshed)
            reply, primary_ts = matches[0]
            concrete = ReplyEventBinding(principal_ref=public_principal, request_ref=request_ref,
                request_message_key=binding.request_message_key, thread_ts=binding.thread_ts,
                context=binding.context, reply_message=reply, reply_primary_ts=primary_ts,
                read_ref=read_ref, access_current=True)

            class SnapshotResolver:
                def resolve_reply(self, *, principal_ref, request_ref, message_key):
                    if (principal_ref != concrete.principal_ref or request_ref != concrete.request_ref
                            or message_key != binding.reply_message_key):
                        raise ValueError("projection snapshot binding changed")
                    return concrete

            projected = CanonicalReplyEventProjector(SnapshotResolver()).project(
                principal_ref=public_principal, arguments={"request_ref":request_ref}, message_key=binding.reply_message_key)
            return ResolvedReplyEvent(projected, read_ref, public_principal)
        except Exception:
            raise ReplyDeliveryUnavailable("authorized canonical reply event unavailable") from None


class RuntimeReplyDelivery:
    """Private host-owned SEND entry; explicit selection, never a READ-tool side effect."""
    def __init__(self, events, store, *, clock, enabled=False, resolver=None, connector=None):
        if (type(events) is not RuntimeReplyEventResolver or type(store) is not RuntimeReplySubscriptionStore
                or not callable(clock) or type(enabled) is not bool
                or (resolver is not None and not callable(resolver)) or (connector is not None and not callable(connector))):
            raise TypeError("exact current owners and explicit host configuration required")
        self._events, self._store, self._clock = events, store, clock
        self._enabled, self._resolver, self._connector = enabled, resolver, connector

    def _send_selected(self, principal, record, version, resolved):
        # A busy executor may start later than the interactive preflight. Check
        # current READ lifetime, subscription/version/expiry, and rotation keys
        # on the actual owned I/O lane before entering the one-shot transport.
        try:
            self._events.current(principal)
            view = self._store.delivery_view(record.subscription_id, expected_version=version,
                owner_key=record.owner_key, grant_revision=record.revision)
            self._events.current(principal)
            packet = prepare_reply_webhook(subscription=VerifiedReplySubscription(
                subscription_id=record.subscription_id, principal_ref=record.owner_key, request_ref=record.request_ref,
                event_name=EVENT_NAME, access_current=True, active=True, expires_at=record.expires_at,
                signing_secrets=view.signing_secrets), event=resolved.event, signed_at=int(self._clock()))
        except Exception:
            raise ReplyDeliveryUnavailable("delivery admission expired before I/O") from None
        return send_once(view.callback_url, packet, resolver=self._resolver, connector=self._connector)

    async def deliver_current(self, principal, subscription_id):
        if not self._enabled:
            raise ReplyDeliveryUnavailable("reply delivery is not selected by the host")
        projection = self._events.current(principal)
        snapshot = await self._store.snapshot(subscription_id)
        record = snapshot.record
        if record is None or record.owner_key != owner_key(projection):
            raise ReplyDeliveryUnavailable("original subscriber unavailable")
        resolved = await self._events.resolve(principal, record.request_ref)
        if resolved.read_ref != record.read_ref or resolved.principal_ref != record.owner_key:
            raise ReplyDeliveryUnavailable("original reply subscription changed")
        view = self._store.delivery_view(subscription_id, expected_version=snapshot.version,
            owner_key=record.owner_key, grant_revision=record.revision)
        self._events.current(principal)
        reservation = await self._store.reserve_delivery(subscription_id=subscription_id,
            expected_version=snapshot.version, owner_key=record.owner_key, grant_revision=record.revision,
            event_id=resolved.event["eventId"])
        result = {"delivery_ref":reservation.delivery_ref, "event_id":resolved.event["eventId"],
                  "parent_consumed":False, "fresh_send":False, "state":reservation.state}
        if not reservation.fresh:
            return result
        # Final current authorization/canonical reply/subscription checks before
        # the one external effect. Revocation after actual I/O starts remains an
        # in-flight effect; no cancellation or external exactly-once is promised.
        try:
            fresh = await self._events.resolve(principal, record.request_ref)
            current = await self._store.snapshot(subscription_id)
            self._events.current(principal)
            if fresh != resolved or current != snapshot:
                raise ReplyDeliveryUnavailable("delivery admission changed")
            view = self._store.delivery_view(subscription_id, expected_version=snapshot.version,
                owner_key=record.owner_key, grant_revision=record.revision)
        except Exception:
            await self._store.settle_delivery(reservation.delivery_ref, outcome="REFUSED")
            return dict(result, state="NOT_SENT")
        try:
            observed = await asyncio.to_thread(self._send_selected, principal, record, snapshot.version, resolved)
        except (CallbackDestinationRefused, ReplyDeliveryUnavailable):
            await self._store.settle_delivery(reservation.delivery_ref, outcome="REFUSED")
            return dict(result, state="NOT_SENT")
        except BaseException as exc:
            await self._store.settle_delivery(reservation.delivery_ref, outcome="EFFECT_UNKNOWN")
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            return dict(result, state="EFFECT_UNKNOWN")
        if type(observed) is not CallbackHTTPReceipt:
            await self._store.settle_delivery(reservation.delivery_ref, outcome="EFFECT_UNKNOWN")
            return dict(result, state="EFFECT_UNKNOWN")
        classified = classify_reply_webhook_response(observed.status_code)
        outcome = ("RECEIVED" if classified == "TRANSPORT_ACCEPTED_PARENT_UNPROVEN" else
                   "EFFECT_UNKNOWN" if classified in {"EFFECT_UNKNOWN", "RETRY_DECISION_BY_EXISTING_OWNER"} else "REFUSED")
        await self._store.settle_delivery(reservation.delivery_ref, outcome=outcome, http_status=observed.status_code)
        return dict(result, state=classified, fresh_send=True)


def build_runtime_reply_delivery(owner, store, *, clock, enabled=False, resolver=None, connector=None):
    """Explicit existing-host composition; starts/installs/arms nothing by itself.

    The actual host must call deliver_current with its freshly JWT-authorized
    original-account VerifiedPrincipal. No automatic native-COMMIT registration
    or cached/fabricated original principal is supplied by this factory.
    """
    return RuntimeReplyDelivery(RuntimeReplyEventResolver(owner, clock=clock), store,
        clock=clock, enabled=enabled, resolver=resolver, connector=connector)
