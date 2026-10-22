"""Concrete subscription receiver and consumer on existing App/Company owners.

No listener, Runtime creation, token cache, queue, retry, key provisioning or
implicit arming. Private transport uses the existing authenticated App peer.
"""
from __future__ import annotations
import asyncio
import dataclasses
from pathlib import Path

from common.reply_subscription_private_contract import (
    PRIVATE_SCHEMA, RESULT_SCHEMA, OPERATIONS, MODIFYING, result,
    ReplyEventIngressOwner, ReplyEventCommitConsumer,
)
from control_plane.principal_projection import NeutralPrincipalProjection
from integrations.mastermind_executive_app.gateway import CeoIngressClient, TRANSPORT_SENT_OK
from .installed import _principal
from .reply_policy_selection import ReplyPolicySelection, ReplyPolicyDenied
from .runtime_reply_authorization import capture_reply_authorization, policy_fingerprint
from .runtime_reply_authorization_owner import RuntimeReplyAuthorizationOwner, ObservedReplyPolicyDenial
from .runtime_reply_delivery import build_runtime_reply_delivery, ReplyDeliveryUnavailable
from .runtime_reply_subscriptions import RuntimeReplySubscriptionStore, ExecutiveReplyCipher
from .runtime_return import RuntimeSessionReturn, RuntimeOriginalRequestResolver
from .web_reply_callback_transport import send_once, CallbackHTTPReceipt
from .web_reply_event_rpc import (EventSubscribeRequest, EventUnsubscribeRequest,
    EventSubscriptionReceipt, EventUnsubscribeReceipt, WebReplyEventRpc)
from .web_reply_subscription_owner import (OriginalReplySubscriptionAdapter,
    VerifiedChallengeHTTP, SubscriptionUnavailable, SubscriptionEffectUnknown)


class ReplyChallengeSender:
    def __init__(self, *, resolver=None, connector=None):
        self.resolver, self.connector = resolver, connector

    async def verify(self, url, packet):
        receipt = await asyncio.to_thread(send_once,url,packet,resolver=self.resolver,connector=self.connector)
        if type(receipt) is not CallbackHTTPReceipt or receipt.response_truncated:
            raise SubscriptionEffectUnknown("challenge observation unavailable")
        return VerifiedChallengeHTTP(receipt.status_code,receipt.response_body)


class _AuthorizedStore:
    """Invocation binding; all durable state remains in the original Runtime store."""
    def __init__(self, host, principal, source_policy):
        self.host, self.principal, self.source_policy = host, principal, source_policy

    async def snapshot(self, ident): return await self.host.store.snapshot(ident)
    async def read(self, ident): return await self.host.store.read(ident)
    async def remove(self, *args, **kwargs): return await self.host.store.remove(*args,**kwargs)

    async def commit(self, record, signing_secret, *, callback_url, expected_version):
        policy = self.host.policies.select(self.principal)
        if policy_fingerprint(policy) != self.source_policy:
            raise SubscriptionUnavailable("receiver policy changed before commit")
        from control_plane.native_continuation import _digest
        event, _ = self.host.returns._stored_request(record.read_ref)
        authorization = capture_reply_authorization(self.principal,policy,
            subscription_expires_at=record.expires_at, request_ref=record.request_ref,
            read_ref=record.read_ref, request_event_sha256=_digest(event.to_dict()),now=self.host.clock())
        return await self.host.store.commit(record,signing_secret,callback_url=callback_url,
            expected_version=expected_version,authorization=authorization)


class RuntimeReplyEventHost:
    def __init__(self, returns, cipher, policies, *, clock, enabled=False, resolver=None, connector=None):
        if (type(returns) is not RuntimeSessionReturn or type(cipher) is not ExecutiveReplyCipher
                or not isinstance(policies,ReplyPolicySelection) or type(enabled) is not bool
                or not callable(clock)):
            raise TypeError("exact Runtime, storage key and receiver policy composition required")
        self.returns, self.runtime, self.policies, self.clock, self.enabled = returns, returns.runtime, policies, clock, enabled
        self.store = RuntimeReplySubscriptionStore(self.runtime,cipher,clock=clock)
        self.challenge = ReplyChallengeSender(resolver=resolver,connector=connector)
        self.audiences = RuntimeReplyAuthorizationOwner(self.store,policies,clock=clock)
        self.delivery = build_runtime_reply_delivery(returns,self.store,clock=clock,enabled=enabled,
            resolver=resolver,connector=connector,audience_owner=self.audiences)
        self.ingress = ReplyEventIngressOwner(self.runtime,self.validate_frame,self.handle_frame)
        self.consumer = ReplyEventCommitConsumer(self.runtime,self.handle_committed)

    def validate_frame(self, frame):
        if (type(frame) is not dict or set(frame) != {"schema","operation","principal","arguments","source_policy_sha256"}
                or frame["schema"] != PRIVATE_SCHEMA or frame["operation"] not in OPERATIONS
                or type(frame["arguments"]) is not dict or type(frame["source_policy_sha256"]) is not str
                or len(frame["source_policy_sha256"]) != 64):
            raise SubscriptionUnavailable("private event frame unavailable")
        _principal(frame["principal"])
        operation = frame["operation"]
        if operation == "can_discover":
            if frame["arguments"]: raise SubscriptionUnavailable("unexpected discovery arguments")
        else:
            cls = EventSubscribeRequest if operation == "subscribe" else EventUnsubscribeRequest
            if set(frame["arguments"]) != {f.name for f in dataclasses.fields(cls)}:
                raise SubscriptionUnavailable("private event argument shape unavailable")
            cls(**frame["arguments"])
        return operation

    async def handle_frame(self, frame):
        operation = self.validate_frame(frame)
        if not self.enabled: return result(operation,code="subscription_unavailable")
        try:
            principal = _principal(frame["principal"])
            policy = self.policies.select(principal)
            if policy_fingerprint(policy) != frame["source_policy_sha256"]:
                raise SubscriptionUnavailable("authenticated receiver policy changed")
            adapter = OriginalReplySubscriptionAdapter(resolver=RuntimeOriginalRequestResolver(self.returns),
                storage=_AuthorizedStore(self,principal,frame["source_policy_sha256"]),
                challenge_sender=self.challenge,clock=self.clock,enabled=self.enabled)
            if operation == "can_discover":
                data = await adapter.can_discover(principal)
            else:
                cls = EventSubscribeRequest if operation == "subscribe" else EventUnsubscribeRequest
                data = dataclasses.asdict(await getattr(adapter,operation)(principal,cls(**frame["arguments"])))
            return result(operation,data=data)
        except (SubscriptionUnavailable,ReplyPolicyDenied):
            return result(operation,code="subscription_unavailable")
        except Exception:
            return result(operation,code="effect_unknown" if operation in MODIFYING else "backend_unavailable")

    async def handle_committed(self, *, read_ref, message_key, fingerprint):
        if not self.enabled: return ()
        event, _ = self.returns._stored_request(read_ref)
        observations = []
        for ident in self.store.subscriptions_for_reply(event.command_id,read_ref):
            try:
                audience = self.audiences.capture(ident)
                binding = await self.returns.resolve_read(principal=self.audiences.current(audience),read_ref=read_ref)
                if binding.reply_message_key != message_key or binding.reply_fingerprint != fingerprint:
                    raise SubscriptionUnavailable("commit differs from canonical retained reply")
                observations.append(await self.delivery.deliver_subscription(ident))
            except ObservedReplyPolicyDenial as denial:
                await self.audiences.revoke_observed(denial)
                observations.append({"state":"NOT_SENT","parent_consumed":False})
            except (SubscriptionUnavailable, ReplyDeliveryUnavailable):
                # Qualified pre-send refusal does not imply a callback attempt.
                observations.append({"state":"UNAVAILABLE","parent_consumed":False})
            except Exception:
                # Failure after a possible send/settlement must never look like
                # a proven unavailable/non-effectful callback. Reservation
                # custody still prevents the original delivery from replaying.
                observations.append({"state":"EFFECT_UNKNOWN","parent_consumed":False})
        return tuple(observations)


class InstalledReplyEventClient:
    """Existing one-frame CeoIngress client; called only by verified MCP event edge."""
    def __init__(self, socket_path, policies, *, client=None):
        self.path = Path(socket_path)
        if not self.path.is_absolute() or not isinstance(policies,ReplyPolicySelection):
            raise TypeError("existing receiver and private socket selection required")
        self.policies, self.client = policies, client or CeoIngressClient()

    async def _call(self, operation, principal, arguments):
        if type(principal) is not NeutralPrincipalProjection:
            raise SubscriptionUnavailable("authenticated receiver projection required")
        wire = dataclasses.asdict(principal);wire["scopes"] = list(principal.scopes)
        response = await self.client.send_frame(self.path,{"schema":PRIVATE_SCHEMA,"operation":operation,
            "principal":wire,"arguments":arguments,"source_policy_sha256":policy_fingerprint(self.policies.select(principal))})
        if response.transport != TRANSPORT_SENT_OK or response.ok is not True:
            raise SubscriptionEffectUnknown("original private event operation observation unavailable")
        data = response.result
        if (type(data) is not dict or set(data) != {"schema","operation","ok","data","error"}
                or data["schema"] != RESULT_SCHEMA or data["operation"] != operation or type(data["ok"]) is not bool):
            raise SubscriptionEffectUnknown("private event response unavailable")
        if data["ok"] is not True:
            if data.get("error") == {"code":"subscription_unavailable"}:
                raise SubscriptionUnavailable("private subscription unavailable")
            raise SubscriptionEffectUnknown("original subscription effect requires reconciliation")
        return data["data"]

    async def can_discover(self, principal):
        try: return await self._call("can_discover",principal,{}) is True
        except Exception: return False

    async def subscribe(self, principal, request):
        if type(request) is not EventSubscribeRequest: raise SubscriptionUnavailable("invalid event request")
        return EventSubscriptionReceipt(**await self._call("subscribe",principal,dataclasses.asdict(request)))

    async def unsubscribe(self, principal, request):
        if type(request) is not EventUnsubscribeRequest: raise SubscriptionUnavailable("invalid event request")
        return EventUnsubscribeReceipt(**await self._call("unsubscribe",principal,dataclasses.asdict(request)))


def build_installed_reply_event_rpc(socket_path, policies, *, clock, enabled=False):
    if type(enabled) is not bool: raise TypeError("explicit event host selection required")
    if not enabled: return None
    return WebReplyEventRpc(InstalledReplyEventClient(socket_path,policies),clock=clock)
