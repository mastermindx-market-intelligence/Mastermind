"""One new event *type* inside the incumbent Executive Runtime's encrypted CAS store.

No new DB/file/credential owner, queue, daemon, scheduler, ingress, or delivery
transport. The installed Executive host selects the Runtime and its already
provisioned ExecutiveReplyCipher; calling these methods alone never sends Slack
or an MCP callback. Uncertain effects are fenced by original Runtime events.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from typing import Any

from control_plane.executive_runtime import Runtime
from .runtime_reply_subscriptions import ExecutiveReplyCipher, _hash, _json
from .web_reply_delivery import _secret
from .web_reply_event_rpc import _callback_url
from .web_reply_subscription_owner import SubscriptionConflict

_SCHEMA = "mastermind.dot_canary_subscription_event.v1"
_RECORD = "mastermind.dot_canary_subscription.v1"
_AGGREGATE = "reply_subscription"  # THE incumbent Runtime store; event family isolated by ID
_DELIVERY_AGGREGATE = "reply_subscription_delivery"
_ACTOR = "executive.reply_subscriptions"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_EVENT_ID = re.compile(r"^evt-[0-9a-f]{64}$")
_SUB_ID = re.compile(r"^sub_[0-9a-f]{40}$")
_MAX_HISTORY = 4096


@dataclasses.dataclass(frozen=True)
class CanaryRecord:
    subscription_id: str
    owner_key: str
    channel_id: str
    callback_url_digest: str
    signing_secret_digest: str
    source_policy_sha256: str
    verified_at: int
    expires_at: int
    authorized_until: int
    schema: str = _RECORD


@dataclasses.dataclass(frozen=True)
class CanarySnapshot:
    record: CanaryRecord | None
    version: str
    binding: tuple[str, str, str] | None


@dataclasses.dataclass(frozen=True)
class CanaryDeliveryView:
    record: CanaryRecord
    callback_url: str = dataclasses.field(repr=False)
    signing_secrets: tuple[str, ...] = dataclasses.field(repr=False)
    authorization: dict[str, Any] = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True)
class CanaryDeliveryReservation:
    delivery_ref: str
    fresh: bool
    state: str


def subscription_id(owner_key: str, channel_id: str, callback_url: str) -> str:
    if (type(owner_key) is not str or _SHA.fullmatch(owner_key) is None
            or type(channel_id) is not str or not re.fullmatch(r"C[A-Z0-9]{8,31}", channel_id)
            or _callback_url(callback_url) != callback_url):
        raise ValueError("canonical canary subscription identity required")
    value = [owner_key, "mastermind.slack_canary_message", {"channel_id": channel_id}, callback_url]
    return "sub_" + _hash(value)[:40]


def _digest(raw: str) -> str:
    if type(raw) is not str:
        raise ValueError("raw digest input unavailable")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _record(value):
    if type(value) is not CanaryRecord or value.schema != _RECORD:
        raise ValueError("canonical canary record required")
    if (not _SUB_ID.fullmatch(value.subscription_id)
            or not all(type(getattr(value, key)) is str and _SHA.fullmatch(getattr(value, key))
                       for key in ("owner_key", "callback_url_digest", "signing_secret_digest",
                                   "source_policy_sha256"))
            or not re.fullmatch(r"C[A-Z0-9]{8,31}", value.channel_id)
            or not all(type(getattr(value, key)) is int for key in
                       ("verified_at", "expires_at", "authorized_until"))
            or not 0 <= value.verified_at < value.expires_at <= value.authorized_until):
        raise ValueError("invalid canary record")
    return dataclasses.asdict(value)


class RuntimeCanarySubscriptionStore:
    """Additional bounded schema owned by incumbent Runtime and its AEAD key."""

    def __init__(self, runtime: Runtime, cipher: ExecutiveReplyCipher, *, clock):
        if type(runtime) is not Runtime or type(cipher) is not ExecutiveReplyCipher or not callable(clock):
            raise TypeError("incumbent Runtime and sealed key required")
        self.runtime, self.store, self.cipher, self.clock = runtime, runtime.store, cipher, clock

    def _now(self):
        now = self.clock()
        if type(now) is not int or not 0 < now <= 4102444800:
            raise ValueError("canonical clock required")
        return now

    def _state(self, ident, connection=None):
        if type(ident) is not str or not _SUB_ID.fullmatch(ident):
            raise ValueError("canonical canary subscription required")
        events = self.store.list_events(
            aggregate_type=_AGGREGATE, aggregate_id=ident, connection=connection,
        )
        if len(events) > _MAX_HISTORY:
            raise ValueError("subscription event chain over bound")
        snapshot = CanarySnapshot(None, "empty", None)
        envelope = associated = None
        for sequence, event in enumerate(events, 1):
            p = event.payload
            if (event.actor != _ACTOR or event.sequence != sequence
                    or event.event_type not in ("CANARY_SUBSCRIPTION_COMMITTED",
                                                "CANARY_SUBSCRIPTION_REVOKED")
                    or type(p) is not dict
                    or set(p) != {"schema", "previous", "record", "binding", "envelope",
                                 "operation_digest"}
                    or p["schema"] != _SCHEMA or p["previous"] != snapshot.version
                    or type(p["binding"]) is not list or len(p["binding"]) != 3
                    or event.command_id != "reply-subscription:" + p["operation_digest"]):
                raise ValueError("canary event chain unavailable")
            binding = tuple(p["binding"])
            if (not all(type(x) is str for x in binding)
                    or _SHA.fullmatch(binding[0]) is None
                    or not re.fullmatch(r"C[A-Z0-9]{8,31}", binding[1])
                    or _SHA.fullmatch(binding[2]) is None
                    or snapshot.binding is not None and snapshot.binding != binding):
                raise ValueError("canary owner binding changed")
            value = None if p["record"] is None else CanaryRecord(**p["record"])
            kind = event.event_type
            semantic = {"previous": p["previous"], "record": p["record"],
                        "binding": p["binding"], "kind": kind}
            if (_hash(semantic) != p["operation_digest"] or
                    (value is not None and (value.subscription_id != ident
                        or binding != (value.owner_key, value.channel_id,
                                       value.callback_url_digest)))):
                raise ValueError("canary committed identity changed")
            if kind == "CANARY_SUBSCRIPTION_COMMITTED":
                if value is None or type(p["envelope"]) is not dict:
                    raise ValueError("missing canary sealed grant")
                associated = {"metadata": _record(value),
                              "previous": p["previous"], "binding": p["binding"]}
                envelope = p["envelope"]
            elif value is not None or p["envelope"] is not None:
                raise ValueError("invalid canary revocation event")
            else:
                envelope = associated = None
            snapshot = CanarySnapshot(value, event.command_id, binding)
        return snapshot, envelope, associated

    def _private(self, snapshot, envelope, associated):
        value = self.cipher.open(envelope, associated)
        if type(value) is not dict or set(value) != {
            "url", "current", "previous", "previous_until", "authorization",
        }:
            raise ValueError("sealed canary payload unavailable")
        record = snapshot.record
        if (record is None or _callback_url(value["url"]) != value["url"]
                or _digest(value["url"]) != record.callback_url_digest
                or _digest(value["current"]) != record.signing_secret_digest
                or type(value["previous_until"]) is not int
                or value["previous_until"] < 0
                or type(value["authorization"]) is not dict
                or set(value["authorization"]) != {
                    "principal", "owner_key", "channel_id", "source_policy_sha256",
                    "authorized_until"}
                or value["authorization"]["owner_key"] != record.owner_key
                or value["authorization"]["channel_id"] != record.channel_id
                or value["authorization"]["source_policy_sha256"] != record.source_policy_sha256
                or value["authorization"]["authorized_until"] != record.authorized_until):
            raise ValueError("canary authorization changed")
        _secret(value["current"])
        if value["previous"] is not None:
            _secret(value["previous"])
            if value["previous"] == value["current"]:
                raise ValueError("duplicate canary rotation key")
        elif value["previous_until"] != 0:
            raise ValueError("invalid empty canary key")
        return value

    async def snapshot(self, ident):
        snapshot, envelope, associated = self._state(ident)
        if snapshot.record is not None:
            self._private(snapshot, envelope, associated)
        return snapshot

    async def read(self, ident):
        return (await self.snapshot(ident)).record

    async def commit(self, record: CanaryRecord, signing_secret, *, callback_url,
                     authorization: dict, expected_version: str):
        metadata = _record(record)
        if (type(expected_version) is not str
                or (expected_version != "empty" and _ID.fullmatch(expected_version) is None)
                or _callback_url(callback_url) != callback_url
                or _digest(callback_url) != record.callback_url_digest
                or _digest(signing_secret) != record.signing_secret_digest
                or subscription_id(record.owner_key, record.channel_id, callback_url)
                    != record.subscription_id
                or type(authorization) is not dict
                or set(authorization) != {
                    "principal", "owner_key", "channel_id", "source_policy_sha256",
                    "authorized_until"}
                or authorization["owner_key"] != record.owner_key
                or authorization["channel_id"] != record.channel_id
                or authorization["source_policy_sha256"] != record.source_policy_sha256
                or authorization["authorized_until"] != record.authorized_until
                or type(authorization["principal"]) is not dict
                or not record.verified_at <= self._now() < record.expires_at):
            raise ValueError("unqualified canary subscription commit")
        _secret(signing_secret)
        prior, envelope, associated = self._state(record.subscription_id)
        private = {
            "url": callback_url, "current": signing_secret,
            "previous": None, "previous_until": 0,
            "authorization": json.loads(_json(authorization)),
        }
        if prior.record is not None:
            old = self._private(prior,envelope,associated)
            if old["current"] == signing_secret:
                private["previous"], private["previous_until"] = (
                    old["previous"], old["previous_until"])
            else:
                private["previous"], private["previous_until"] = (
                    old["current"], min(self._now()+300, prior.record.expires_at))
        binding = [record.owner_key, record.channel_id, record.callback_url_digest]
        semantic = {"previous": expected_version, "record": metadata,
                    "binding": binding, "kind": "CANARY_SUBSCRIPTION_COMMITTED"}
        associated = {"metadata": metadata, "previous": expected_version, "binding": binding}
        digest = _hash(semantic)
        with self.store.transaction() as connection:
            current, _, _ = self._state(record.subscription_id, connection)
            existing = self.store.get_event_by_command_id("reply-subscription:"+digest,connection=connection)
            if existing is not None:
                _, current_envelope, current_associated = self._state(
                    record.subscription_id, connection)
                prior_private = self._private(
                    current, current_envelope, current_associated,
                ) if current.record is not None else None
                if (current.record != record or current.version != existing.command_id
                        or prior_private is None
                        or prior_private["authorization"] != authorization
                        or prior_private["current"] != signing_secret):
                    raise SubscriptionConflict("superseded canary event or grant")
                return record
            if (current.version != expected_version or current.binding is not None
                    and current.binding != tuple(binding)):
                raise SubscriptionConflict("canary CAS owner changed")
            envelope = self.cipher.seal(private,associated)
            self.store.append_event(connection,
                aggregate_type=_AGGREGATE,aggregate_id=record.subscription_id,
                event_type=semantic["kind"],actor=_ACTOR,
                command_id="reply-subscription:"+digest,
                payload={"schema": _SCHEMA, "previous": expected_version,
                         "record": metadata, "binding": binding,
                         "envelope": envelope, "operation_digest": digest})
        return record

    async def remove(self, ident, *, owner_key, channel_id, callback_url_digest,
                     expected_version):
        if (type(ident) is not str or _SUB_ID.fullmatch(ident) is None
                or type(owner_key) is not str or _SHA.fullmatch(owner_key) is None
                or type(channel_id) is not str or not re.fullmatch(r"C[A-Z0-9]{8,31}",channel_id)
                or type(callback_url_digest) is not str or _SHA.fullmatch(callback_url_digest) is None
                or type(expected_version) is not str or
                (expected_version != "empty" and _ID.fullmatch(expected_version) is None)):
            raise ValueError("canary revocation binding invalid")
        binding = [owner_key, channel_id, callback_url_digest]
        semantic = {"previous":expected_version,"record":None,"binding":binding,
                    "kind":"CANARY_SUBSCRIPTION_REVOKED"}
        digest = _hash(semantic)
        with self.store.transaction() as connection:
            current, _, _ = self._state(ident,connection)
            existing=self.store.get_event_by_command_id("reply-subscription:"+digest,connection=connection)
            if existing is not None:
                if current.version != existing.command_id:
                    raise SubscriptionConflict("superseded canary revocation")
                return
            if (current.version != expected_version or current.binding is not None
                    and current.binding != tuple(binding)):
                raise SubscriptionConflict("canary revocation version changed")
            if current.record is None and current.binding == tuple(binding):
                return
            self.store.append_event(connection,
                aggregate_type=_AGGREGATE,aggregate_id=ident,
                event_type=semantic["kind"],actor=_ACTOR,
                command_id="reply-subscription:"+digest,
                payload={"schema":_SCHEMA,"previous":expected_version,
                         "record":None,"binding":binding,"envelope":None,
                         "operation_digest":digest})

    def delivery_view(self, ident, *, expected_version, owner_key):
        snapshot,envelope,associated=self._state(ident)
        record=snapshot.record
        if (record is None or snapshot.version != expected_version
                or record.owner_key != owner_key or not self._now() < record.expires_at):
            raise ValueError("current canary subscription unavailable")
        private=self._private(snapshot,envelope,associated)
        secrets=(private["current"],) + (
            (private["previous"],) if private["previous"] is not None
            and self._now() < private["previous_until"] else ())
        return CanaryDeliveryView(record,private["url"],secrets,
                                  json.loads(_json(private["authorization"])))

    def subscriptions_for_channel(self, channel_id):
        """Bounded scan in the incumbent Runtime event table; no parallel index."""
        if type(channel_id) is not str or not re.fullmatch(r"C[A-Z0-9]{8,31}",channel_id):
            raise ValueError("invalid canary channel")
        events=self.store.list_events(aggregate_type=_AGGREGATE)
        if len(events)>_MAX_HISTORY: raise ValueError("canary subscription census over bound")
        ids=sorted({e.aggregate_id for e in events if e.event_type == "CANARY_SUBSCRIPTION_COMMITTED"
                    and type(e.payload) is dict and type(e.payload.get("record")) is dict
                    and e.payload["record"].get("channel_id")==channel_id})
        if len(ids)>32: raise ValueError("canary audience exceeds bound")
        return tuple(s.record.subscription_id for ident in ids
                     if (s:=self._state(ident)[0]).record is not None
                     and s.record.channel_id == channel_id and self._now() < s.record.expires_at)

    async def reserve_delivery(self, *, ident, version, owner_key, event_id):
        if type(event_id) is not str or _EVENT_ID.fullmatch(event_id) is None:
            raise ValueError("canonical canary event required")
        ref="canary-delivery:"+_hash([ident,event_id])
        with self.store.transaction() as connection:
            current,_,_=self._state(ident,connection)
            if (current.record is None or current.version != version
                    or current.record.owner_key != owner_key
                    or not self._now() < current.record.expires_at):
                raise SubscriptionConflict("canary delivery grant changed")
            events=self._delivery_events(ref,connection)
            if events:
                return CanaryDeliveryReservation(ref,False,
                    "EFFECT_UNKNOWN" if len(events)==1 else events[-1].payload["outcome"])
            self.store.append_event(connection,aggregate_type=_DELIVERY_AGGREGATE,
                aggregate_id=ref,event_type="CANARY_DELIVERY_STARTED",actor=_ACTOR,
                command_id=ref,payload={"schema":_SCHEMA,"subscription_id":ident,
                    "version":version,"event_id":event_id,"outcome":None})
        return CanaryDeliveryReservation(ref,True,"STARTED")

    def _delivery_events(self, ref, connection=None):
        if type(ref) is not str or not re.fullmatch(r"canary-delivery:[0-9a-f]{64}",ref):
            raise ValueError("invalid canary delivery")
        events=self.store.list_events(aggregate_type=_DELIVERY_AGGREGATE,
            aggregate_id=ref,connection=connection)
        if len(events)>2: raise ValueError("canary delivery events over bound")
        for index,e in enumerate(events):
            p=e.payload
            if (e.actor!=_ACTOR or e.sequence!=index+1
                    or e.event_type!=("CANARY_DELIVERY_STARTED" if index==0 else "CANARY_DELIVERY_OBSERVED")
                    or e.command_id!=ref+("" if index==0 else ":observed")
                    or type(p) is not dict):
                raise ValueError("canary delivery chain unavailable")
            if index==0:
                if (set(p)!={"schema","subscription_id","version","event_id","outcome"}
                        or p.get("schema")!=_SCHEMA or p.get("outcome") is not None
                        or type(p.get("subscription_id")) is not str
                        or _SUB_ID.fullmatch(p["subscription_id"]) is None
                        or type(p.get("version")) is not str
                        or _ID.fullmatch(p["version"]) is None
                        or type(p.get("event_id")) is not str
                        or _EVENT_ID.fullmatch(p["event_id"]) is None
                        or ref!="canary-delivery:"+_hash([p["subscription_id"],p["event_id"]])):
                    raise ValueError("invalid canary delivery reservation")
            elif (set(p)!={"schema","outcome","status"}
                  or p.get("schema")!=_SCHEMA or p.get("outcome") not in {
                      "RECEIVED","REFUSED","EFFECT_UNKNOWN"}
                  or (p.get("status") is not None
                      and (type(p["status"]) is not int or not 100<=p["status"]<600))
                  or (p["outcome"]=="RECEIVED"
                      and (p["status"] is None or not 200<=p["status"]<300))):
                raise ValueError("canary delivery result malformed")
        return events

    async def settle_delivery(self, ref, *, outcome, status=None):
        if (outcome not in {"RECEIVED","REFUSED","EFFECT_UNKNOWN"}
                or (status is not None and (type(status) is not int or not 100<=status<600))
                or (outcome=="RECEIVED" and (status is None or not 200<=status<300))):
            raise ValueError("invalid canary delivery status")
        payload={"schema":_SCHEMA,"outcome":outcome,"status":status}
        with self.store.transaction() as connection:
            events=self._delivery_events(ref,connection)
            if not events:
                raise ValueError("unreserved canary delivery")
            if len(events)==2:
                if events[-1].payload != payload:
                    raise SubscriptionConflict("canary delivery outcome changed")
                return
            self.store.append_event(connection,aggregate_type=_DELIVERY_AGGREGATE,
                aggregate_id=ref,event_type="CANARY_DELIVERY_OBSERVED",actor=_ACTOR,
                command_id=ref+":observed",payload=payload)

    def delivery_status(self, ref):
        events=self._delivery_events(ref)
        if not events: raise ValueError("missing canary delivery")
        return "EFFECT_UNKNOWN" if len(events)==1 else events[-1].payload["outcome"]
