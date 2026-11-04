"""Reply subscription and delivery facts in the EXISTING Executive Runtime.

No database/schema/queue, HTTP, key provisioning, account grant, or default host
selection. The installed host must supply its own 256-bit storage key and current
account/committed-reply authority. Callback URLs and signing keys remain sealed.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import re
import secrets
from typing import Any

from control_plane.executive_runtime import Runtime
from integrations.session_bridge.web_reply_subscription_owner import (
    StoredReplySubscription, SubscriptionSnapshot, SubscriptionConflict, _digest,
    _subscription_id,
)
from integrations.session_bridge.web_reply_event_rpc import _callback_url
from integrations.session_bridge.web_reply_delivery import _secret

_SCHEMA = "mastermind.reply_subscription_event.v1"
_AUTH_SCHEMA = "mastermind.reply_subscription_event.v2"
_AGGREGATE = "reply_subscription"
_DELIVERY = "reply_subscription_delivery"
_ACTOR = "executive.reply_subscriptions"
_MAX_HISTORY = 4096
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _hash(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _record(value):
    if type(value) is not StoredReplySubscription:
        raise ValueError("canonical metadata required")
    for field in ("subscription_id", "request_ref", "read_ref", "revision"):
        if type(getattr(value, field)) is not str or not _ID.fullmatch(getattr(value, field)):
            raise ValueError("invalid metadata identity")
    for field in ("owner_key", "callback_url_digest", "signing_secret_digest"):
        if type(getattr(value, field)) is not str or not _SHA.fullmatch(getattr(value, field)):
            raise ValueError("invalid metadata digest")
    if (value.schema != "mastermind.native_reply_subscription.v1"
            or type(value.expires_at) is not int or type(value.verified_at) is not int
            or not 0 <= value.verified_at < value.expires_at):
        raise ValueError("invalid metadata lifetime")
    return dataclasses.asdict(value)


class ExecutiveReplyCipher:
    """Concrete AEAD codec; key custody/provisioning belongs to the host."""
    def __init__(self, key_id: str, key: bytes):
        if type(key_id) is not str or not _ID.fullmatch(key_id) or type(key) is not bytes or len(key) != 32:
            raise ValueError("host-provisioned storage key required")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        self.key_id, self._aead = key_id, AESGCM(key)

    def seal(self, private, associated):
        nonce = secrets.token_bytes(12)
        ciphertext = self._aead.encrypt(nonce, _json(private), _json(associated))
        return {"key_id": self.key_id, "nonce": base64.b64encode(nonce).decode(),
                "ciphertext": base64.b64encode(ciphertext).decode()}

    def open(self, envelope, associated):
        try:
            if type(envelope) is not dict or set(envelope) != {"key_id", "nonce", "ciphertext"} or envelope["key_id"] != self.key_id:
                raise ValueError
            nonce = base64.b64decode(envelope["nonce"], validate=True)
            ciphertext = base64.b64decode(envelope["ciphertext"], validate=True)
            if len(nonce) != 12 or not 16 <= len(ciphertext) <= 16384:
                raise ValueError
            return json.loads(self._aead.decrypt(nonce, ciphertext, _json(associated)))
        except Exception:
            raise ValueError("sealed subscription unavailable") from None


@dataclasses.dataclass(frozen=True)
class ReplyDeliveryView:
    record: StoredReplySubscription
    callback_url: str = dataclasses.field(repr=False)
    signing_secrets: tuple[str, ...] = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True)
class ReplyDeliveryReservation:
    delivery_ref: str
    fresh: bool
    state: str


class RuntimeReplySubscriptionStore:
    """One existing Runtime event owner. This constructor grants no authority."""
    def __init__(self, runtime: Runtime, cipher: ExecutiveReplyCipher, *, clock):
        if type(runtime) is not Runtime or type(cipher) is not ExecutiveReplyCipher or not callable(clock):
            raise TypeError("existing Runtime, host storage key and clock required")
        self._runtime, self._store, self._cipher, self._clock = runtime, runtime.store, cipher, clock

    def _now(self):
        now = self._clock()
        if type(now) is not int or now < 0:
            raise ValueError("invalid owner clock")
        return now

    def _state(self, subscription_id, connection=None):
        if type(subscription_id) is not str or not _ID.fullmatch(subscription_id):
            raise ValueError("invalid subscription")
        events = self._store.list_events(aggregate_type=_AGGREGATE, aggregate_id=subscription_id, connection=connection)
        if len(events) > _MAX_HISTORY:
            raise ValueError("subscription history exceeds bound")
        snapshot, envelope, associated = SubscriptionSnapshot(None, "empty", None), None, None
        for sequence, event in enumerate(events, 1):
            p = event.payload
            if (event.sequence != sequence or event.actor != _ACTOR
                    or event.event_type not in {"REPLY_SUBSCRIPTION_COMMITTED", "REPLY_SUBSCRIPTION_REVOKED"}
                    or type(p) is not dict or set(p) not in ({"schema", "previous", "record", "binding", "envelope", "operation_digest"},
                        {"schema", "previous", "record", "binding", "envelope", "operation_digest", "authorization_digest"})
                    or p["schema"] != (_AUTH_SCHEMA if "authorization_digest" in p else _SCHEMA) or p["previous"] != snapshot.version
                    or event.command_id != "reply-subscription:" + p["operation_digest"]
                    or type(p["binding"]) is not list or len(p["binding"]) != 3):
                raise ValueError("subscription event chain unavailable")
            binding = tuple(p["binding"])
            if (snapshot.binding is not None and snapshot.binding != binding
                    or not all(type(v) is str for v in binding)
                    or not _SHA.fullmatch(binding[0]) or not _ID.fullmatch(binding[1]) or not _SHA.fullmatch(binding[2])):
                raise ValueError("subscription owner binding changed")
            record = None if p["record"] is None else StoredReplySubscription(**p["record"])
            if event.event_type == "REPLY_SUBSCRIPTION_COMMITTED":
                metadata = _record(record)
                if record.subscription_id != subscription_id or binding != (record.owner_key, record.request_ref, record.callback_url_digest) or type(p["envelope"]) is not dict:
                    raise ValueError("subscription metadata changed")
                envelope = p["envelope"]
                associated = {"metadata": metadata, "previous": p["previous"], "binding": p["binding"]}
                if "authorization_digest" in p:
                    if type(p["authorization_digest"]) is not str or not _SHA.fullmatch(p["authorization_digest"]):
                        raise ValueError("authorization digest unavailable")
                    associated["authorization_digest"] = p["authorization_digest"]
            elif record is not None or p["envelope"] is not None:
                raise ValueError("invalid revocation event")
            else:
                envelope = associated = None
            semantic = {"previous": p["previous"], "record": p["record"], "binding": p["binding"], "kind": event.event_type}
            if "authorization_digest" in p:
                semantic["authorization_digest"] = p["authorization_digest"]
            if _hash(semantic) != p["operation_digest"]:
                raise ValueError("subscription operation identity changed")
            snapshot = SubscriptionSnapshot(record, event.command_id, binding)
        return snapshot, envelope, associated

    async def snapshot(self, subscription_id):
        snapshot, envelope, associated = self._state(subscription_id)
        if snapshot.record is not None:
            self._private(snapshot, envelope, associated)
        return snapshot

    async def read(self, subscription_id):
        return (await self.snapshot(subscription_id)).record

    def _private(self, snapshot, envelope, associated):
        private = self._cipher.open(envelope, associated)
        if type(private) is not dict or set(private) not in ({"url", "current", "previous", "previous_until"},
                {"url", "current", "previous", "previous_until", "authorization"}):
            raise ValueError("private subscription shape unavailable")
        record = snapshot.record
        if record is None or _callback_url(private["url"]) != private["url"] or _digest(private["url"]) != record.callback_url_digest or _digest(private["current"]) != record.signing_secret_digest:
            raise ValueError("sealed subscription binding changed")
        _secret(private["current"])
        if type(private["previous_until"]) is not int or private["previous_until"] < 0:
            raise ValueError("invalid key grace")
        if private["previous"] is not None:
            _secret(private["previous"])
            if private["previous"] == private["current"]:
                raise ValueError("duplicate rotation key")
        elif private["previous_until"] != 0:
            raise ValueError("invalid empty key grace")
        if "authorization_digest" in associated:
            if "authorization" not in private or _hash(private["authorization"]) != associated["authorization_digest"]:
                raise ValueError("sealed authorization binding changed")
        elif "authorization" in private:
            raise ValueError("unbound sealed authorization")
        return private

    async def commit(self, record, signing_secret, *, callback_url, expected_version, authorization=None):
        metadata = _record(record)
        if type(expected_version) is not str or not _ID.fullmatch(expected_version):
            raise ValueError("canonical store version required")
        if (_callback_url(callback_url) != callback_url or _digest(callback_url) != record.callback_url_digest
                or _digest(signing_secret) != record.signing_secret_digest
                or _subscription_id(record.owner_key, record.request_ref, callback_url) != record.subscription_id):
            raise ValueError("private subscription differs from metadata")
        _secret(signing_secret)
        now = self._now()
        if not record.verified_at <= now < record.expires_at:
            raise ValueError("subscription expired or unverified")
        prior, envelope, associated = self._state(record.subscription_id)
        private = {"url": callback_url, "current": signing_secret, "previous": None, "previous_until": 0}
        if prior.record is not None:
            old = self._private(prior, envelope, associated)
            if old["current"] == signing_secret:
                private["previous"], private["previous_until"] = old["previous"], old["previous_until"]
            else:
                private["previous"], private["previous_until"] = old["current"], min(now + 300, prior.record.expires_at)
        binding = [record.owner_key, record.request_ref, record.callback_url_digest]
        semantic = {"previous": expected_version, "record": metadata, "binding": binding, "kind": "REPLY_SUBSCRIPTION_COMMITTED"}
        associated = {"metadata": metadata, "previous": expected_version, "binding": binding}
        if authorization is not None:
            from control_plane.native_continuation import stored_continuation_request
            from .installed import _principal
            from .web_reply_subscription_owner import owner_key
            event, value = stored_continuation_request(self._runtime, record.read_ref)
            if (type(authorization) is not dict or authorization.get("request_ref") != record.request_ref
                    or authorization.get("read_ref") != record.read_ref or authorization.get("expires_at") != record.expires_at
                    or authorization.get("request_event_sha256") != _hash(event.to_dict())
                    or event.command_id != record.request_ref
                    or owner_key(_principal(authorization.get("principal"))) != record.owner_key):
                raise ValueError("original accepted authorization differs")
            # Source authorization comes only from the authenticated receiver;
            # current policy admission is rechecked by its concrete owner.
            authorization = json.loads(_json(authorization))
            private["authorization"] = authorization
            associated["authorization_digest"] = _hash(authorization)
            semantic["authorization_digest"] = associated["authorization_digest"]
        digest = _hash(semantic)
        sealed = self._cipher.seal(private, associated)
        with self._store.transaction() as connection:
            current, _, current_associated = self._state(record.subscription_id, connection)
            existing = self._store.get_event_by_command_id("reply-subscription:" + digest, connection=connection)
            if existing is not None:
                if (current.record != record or current.version != existing.command_id
                        or (current_associated or {}).get("authorization_digest") != associated.get("authorization_digest")):
                    raise SubscriptionConflict("original subscription was superseded")
                return record
            if current.version != expected_version or (current.binding is not None and current.binding != tuple(binding)):
                raise SubscriptionConflict("subscription version changed")
            self._store.append_event(connection, aggregate_type=_AGGREGATE, aggregate_id=record.subscription_id,
                event_type=semantic["kind"], actor=_ACTOR, command_id="reply-subscription:" + digest,
                payload={"schema": _AUTH_SCHEMA if authorization is not None else _SCHEMA, "previous": expected_version, "record": metadata, "binding": binding,
                         "envelope": sealed, "operation_digest": digest,
                         **({"authorization_digest": associated["authorization_digest"]} if authorization is not None else {})})
        return record

    async def remove(self, subscription_id, owner_key, *, request_ref, callback_url_digest, expected_version):
        binding = [owner_key, request_ref, callback_url_digest]
        if type(expected_version) is not str or not _ID.fullmatch(expected_version):
            raise ValueError("canonical store version required")
        if not _SHA.fullmatch(owner_key) or not _ID.fullmatch(request_ref) or not _SHA.fullmatch(callback_url_digest):
            raise ValueError("invalid revocation binding")
        semantic = {"previous": expected_version, "record": None, "binding": binding, "kind": "REPLY_SUBSCRIPTION_REVOKED"}
        digest = _hash(semantic)
        with self._store.transaction() as connection:
            current, _, _ = self._state(subscription_id, connection)
            existing = self._store.get_event_by_command_id("reply-subscription:" + digest, connection=connection)
            if existing is not None:
                if current.version != existing.command_id:
                    raise SubscriptionConflict("original revocation was superseded")
                return
            if current.version != expected_version or (current.binding is not None and current.binding != tuple(binding)):
                raise SubscriptionConflict("subscription owner/version changed")
            if current.record is None and current.binding == tuple(binding):
                return
            self._store.append_event(connection, aggregate_type=_AGGREGATE, aggregate_id=subscription_id,
                event_type=semantic["kind"], actor=_ACTOR, command_id="reply-subscription:" + digest,
                payload={"schema": _SCHEMA, "previous": expected_version, "record": None, "binding": binding,
                         "envelope": None, "operation_digest": digest})

    def accepted_authorization(self, subscription_id, *, expected_version=None):
        snapshot, envelope, associated = self._state(subscription_id)
        if snapshot.record is None or expected_version is not None and snapshot.version != expected_version:
            raise SubscriptionConflict("accepted subscription changed")
        private = self._private(snapshot, envelope, associated)
        value = private.get("authorization")
        if type(value) is not dict:
            raise ValueError("legacy subscription has no retained authorization")
        return snapshot, json.loads(_json(value))

    def subscriptions_for_reply(self, request_ref, read_ref):
        # Existing event owner only; no new index/database/queue. Refuse an
        # excessive census rather than omitting an unknown matching audience.
        events = self._store.list_events(aggregate_type=_AGGREGATE)
        if len(events) > _MAX_HISTORY:
            raise ValueError("subscription audience census exceeds bound")
        ids = sorted({e.aggregate_id for e in events if type(e.payload) is dict
            and type(e.payload.get("record")) is dict and e.payload["record"].get("request_ref") == request_ref})
        if len(ids) > 32:
            raise ValueError("reply audience exceeds bound")
        result = []
        for ident in ids:
            snapshot, _, _ = self._state(ident)
            if snapshot.record is not None and snapshot.record.request_ref == request_ref and snapshot.record.read_ref == read_ref:
                result.append(ident)
        return tuple(result)

    def delivery_view(self, subscription_id, *, expected_version, owner_key, grant_revision):
        snapshot, envelope, associated = self._state(subscription_id)
        record = snapshot.record
        if (snapshot.version != expected_version or record is None or record.owner_key != owner_key
                or record.revision != grant_revision or not self._now() < record.expires_at):
            raise ValueError("current delivery subscription unavailable")
        private = self._private(snapshot, envelope, associated)
        now = self._now()
        if not now < record.expires_at:
            raise ValueError("subscription expired while opening sealed payload")
        keys = (private["current"],) + ((private["previous"],) if private["previous"] is not None and now < private["previous_until"] else ())
        return ReplyDeliveryView(record, private["url"], keys)

    def _delivery_events(self, delivery_ref, connection=None):
        if type(delivery_ref) is not str or not re.fullmatch(r"reply-delivery:[0-9a-f]{64}", delivery_ref):
            raise ValueError("invalid delivery reference")
        events = self._store.list_events(aggregate_type=_DELIVERY, aggregate_id=delivery_ref, connection=connection)
        if len(events) > 2:
            raise ValueError("delivery history unavailable")
        for sequence, event in enumerate(events, 1):
            p = event.payload
            expected_keys = ({"schema", "subscription_id", "subscription_version", "event_id", "grant_revision", "parent_consumed"}
                             if sequence == 1 else {"schema", "outcome", "http_status", "parent_consumed"})
            if (event.actor != _ACTOR or event.sequence != sequence or type(p) is not dict or set(p) != expected_keys
                    or p["schema"] != "mastermind.reply_delivery.v1" or p["parent_consumed"] is not False
                    or event.command_id != delivery_ref + ("" if sequence == 1 else ":observed")
                    or event.event_type != ("REPLY_DELIVERY_STARTED" if sequence == 1 else "REPLY_DELIVERY_OBSERVED")):
                raise ValueError("delivery evidence binding changed")
            if sequence == 1:
                if (not all(type(p[k]) is str and _ID.fullmatch(p[k]) for k in ("subscription_id", "subscription_version", "grant_revision"))
                        or type(p["event_id"]) is not str or not re.fullmatch(r"evt-[0-9a-f]{64}", p["event_id"])
                        or delivery_ref != "reply-delivery:" + _hash([p["subscription_id"], p["event_id"]])):
                    raise ValueError("delivery identity changed")
            elif (p["outcome"] not in {"RECEIVED", "REFUSED", "EFFECT_UNKNOWN"}
                    or (p["http_status"] is not None and (type(p["http_status"]) is not int or not 100 <= p["http_status"] <= 599))
                    or (p["outcome"] == "RECEIVED" and (p["http_status"] is None or not 200 <= p["http_status"] < 300))):
                raise ValueError("invalid observed delivery outcome")
        return events

    async def reserve_delivery(self, *, subscription_id, expected_version, owner_key, grant_revision, event_id):
        if type(event_id) is not str or not re.fullmatch(r"evt-[0-9a-f]{64}", event_id):
            raise ValueError("canonical event identity required")
        ref = "reply-delivery:" + _hash([subscription_id, event_id])
        with self._store.transaction() as connection:
            snapshot, _, _ = self._state(subscription_id, connection)
            record = snapshot.record
            if snapshot.version != expected_version or record is None or record.owner_key != owner_key or record.revision != grant_revision or not self._now() < record.expires_at:
                raise SubscriptionConflict("delivery subscription changed")
            events = self._delivery_events(ref, connection)
            if events:
                return ReplyDeliveryReservation(ref, False, "EFFECT_UNKNOWN" if len(events) == 1 else events[-1].payload["outcome"])
            self._store.append_event(connection, aggregate_type=_DELIVERY, aggregate_id=ref, event_type="REPLY_DELIVERY_STARTED",
                actor=_ACTOR, command_id=ref, payload={"schema": "mastermind.reply_delivery.v1", "subscription_id": subscription_id,
                "subscription_version": expected_version, "event_id": event_id, "grant_revision": grant_revision, "parent_consumed": False})
        return ReplyDeliveryReservation(ref, True, "STARTED")

    async def delivery_status(self, delivery_ref):
        events = self._delivery_events(delivery_ref)
        if not events:
            raise ValueError("delivery evidence unavailable")
        return dict({**events[0].payload, **events[-1].payload}, outcome="EFFECT_UNKNOWN" if len(events) == 1 else events[-1].payload["outcome"], parent_consumed=False)

    async def settle_delivery(self, delivery_ref, *, outcome, http_status=None):
        if outcome not in {"RECEIVED", "REFUSED", "EFFECT_UNKNOWN"} or (http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599)):
            raise ValueError("invalid observed transport outcome")
        if outcome == "RECEIVED" and (http_status is None or not 200 <= http_status < 300):
            raise ValueError("transport receipt requires observed success")
        payload = {"schema": "mastermind.reply_delivery.v1", "outcome": outcome, "http_status": http_status, "parent_consumed": False}
        with self._store.transaction() as connection:
            events = self._delivery_events(delivery_ref, connection)
            if not events:
                raise ValueError("original delivery reservation unavailable")
            if len(events) == 2:
                if events[-1].payload != payload:
                    raise ValueError("original delivery outcome differs")
                return
            self._store.append_event(connection, aggregate_type=_DELIVERY, aggregate_id=delivery_ref,
                event_type="REPLY_DELIVERY_OBSERVED", actor=_ACTOR, command_id=delivery_ref + ":observed", payload=payload)
