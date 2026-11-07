"""Existing-owner composition for MCP reply subscriptions: no added lifecycle or DB.

All storage, access and callback implementations in this suite are fakes; these
tests do not prove a production persistence backend or live ChatGPT callback.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json

import pytest

from control_plane.principal_projection import neutral_principal_projection
from integrations.session_bridge.web_reply_event_rpc import (
    EventSubscribeRequest, EventUnsubscribeRequest, WebReplyEventRpc,
)
from integrations.session_bridge.web_reply_delivery import (
    verify_reply_webhook_challenge_response,
)

NOW=1791766800
URL="https://receiver.example.com/callback_proven001"
SECRET="whsec_"+base64.b64encode(b"a"*32).decode("ascii")


def api():
    from integrations.session_bridge import web_reply_subscription_owner as module
    return module


def principal(subject="f"*64):
    issuer="https://idp.example.net"
    return neutral_principal_projection(
        policy_id="test-policy", issuer=issuer,
        issuer_digest=hashlib.sha256(issuer.encode()).hexdigest(),
        resource="https://mcp.mastermind-x.com", subject_digest=subject,
        client_ref="b"*64, scopes=("mastermind.executive.read",),
        issued_at=NOW-100, expires_at=NOW+2000, jti_digest=None)


class Access:
    def __init__(self):
        self.calls=[]
        self.active=True
        self.owner_override=None
    async def resolve(self, who, request_ref):
        self.calls.append((who.subject_digest,request_ref))
        return api().OriginalReplyGrant(
            owner_key=self.owner_override or api().owner_key(who),
            request_ref=request_ref,
            read_ref="native-return-read-001",
            revision="current-generation-001",
            access_current=self.active,
            expires_at=NOW+1800,
        )


class ExistingStore:
    """Fake durable-contract port. Has NO filesystem, database or credentials."""
    def __init__(self):
        self.rows={}
        self.calls=[]
        self.lock=asyncio.Lock()
        self.after_write=None
        self.versions={}
        self.bindings={}
    async def snapshot(self, subscription_id):
        row=await self.read(subscription_id)
        return api().SubscriptionSnapshot(row,self.versions.get(subscription_id,"empty"),self.bindings.get(subscription_id))
    async def commit(self, record, secret, **kwargs):
        self.calls.append(("commit", record.subscription_id))
        assert type(secret) is str and secret.startswith("whsec_")
        assert secret not in repr(record)
        if self.rows.get(record.subscription_id)==record:
            return record
        if kwargs["expected_version"] != self.versions.get(record.subscription_id,"empty"):
            raise api().SubscriptionConflict("stale subscription")
        assert hashlib.sha256(kwargs["callback_url"].encode()).hexdigest()==record.callback_url_digest
        self.versions[record.subscription_id]="version-"+str(len(self.calls))
        self.bindings[record.subscription_id]=(record.owner_key,record.request_ref,record.callback_url_digest)
        self.rows[record.subscription_id]=record
        if self.after_write:
            raise self.after_write
        return record
    async def read(self, subscription_id):
        self.calls.append(("read",subscription_id))
        return self.rows.get(subscription_id)
    async def remove(self, subscription_id, owner_key, **kwargs):
        self.calls.append(("remove",subscription_id))
        row=self.rows.get(subscription_id)
        if row is not None and row.owner_key!=owner_key:
            raise ValueError("FOREIGN_ACCOUNT")
        if kwargs["expected_version"] != self.versions.get(subscription_id,"empty"):
            raise api().SubscriptionConflict("stale subscription")
        self.versions[subscription_id]="version-"+str(len(self.calls))
        self.bindings[subscription_id]=(owner_key,kwargs["request_ref"],kwargs["callback_url_digest"])
        self.rows.pop(subscription_id,None)


class Callback:
    def __init__(self):
        self.calls=[]
        self.status=200
        self.corrupt=False
        self.error=None
        self.delay=None
    async def verify(self, url,packet):
        self.calls.append((url,packet))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        body=json.loads(packet.body)
        echo=body["challenge"]+("forged" if self.corrupt else "")
        return api().VerifiedChallengeHTTP(
            status_code=self.status,
            response_body=json.dumps({"challenge":echo}).encode())


def subscribe():
    return EventSubscribeRequest(
        request_ref="request-001",callback_url=URL,signing_secret=SECRET,
        requested_ttl_ms=900_000)


def unsubscribe():
    return EventUnsubscribeRequest(request_ref="request-001",callback_url=URL)


def owner(*,store=None,access=None,callback=None,enabled=True,clock=None):
    store=store if store is not None else ExistingStore()
    access=access if access is not None else Access()
    callback=callback if callback is not None else Callback()
    result=api().OriginalReplySubscriptionAdapter(
        resolver=access,storage=store,challenge_sender=callback,
        clock=clock or (lambda:NOW),enabled=enabled)
    return result,store,access,callback


def run(coro):
    return asyncio.run(coro)


def test_disabled_owner_advertises_nothing_and_cannot_create_effects():
    adapter,store,access,callback=owner(enabled=False)
    assert run(adapter.can_discover(principal())) is False
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.subscribe(principal(),subscribe()))
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.unsubscribe(principal(),unsubscribe()))
    assert store.calls==access.calls==callback.calls==[]


def test_authorized_subscribe_verifies_fresh_single_use_challenge_before_durable_commit():
    adapter,store,access,callback=owner()
    receipt=run(adapter.subscribe(principal(),subscribe()))
    assert receipt.callback_verified is True
    assert receipt.persisted is True
    assert receipt.original_request_current is True
    assert receipt.subscription_id.startswith("sub_")
    assert receipt.expires_at == NOW+900
    assert [x[0] for x in store.calls] == ["read","commit","read"]
    assert len(access.calls)>=2
    assert len(callback.calls)==1
    url,packet=callback.calls[0]
    assert url==URL
    assert packet.headers["X-MCP-Subscription-Id"]==receipt.subscription_id
    assert verify_reply_webhook_challenge_response(
        challenge=json.loads(packet.body)["challenge"],
        response_body=json.dumps({"challenge":json.loads(packet.body)["challenge"]}).encode(),
        status=200)
    assert len(json.loads(packet.body)["challenge"])>=16
    assert SECRET not in repr(packet)
    assert SECRET not in repr(store.rows[receipt.subscription_id])
    assert SECRET not in repr(adapter)


def test_idempotent_refresh_uses_exact_same_subscription_id_across_adapter_restart():
    store=ExistingStore()
    a1,_,_,_=owner(store=store)
    r1=run(a1.subscribe(principal(),subscribe()))
    a2,_,_,_=owner(store=store)
    r2=run(a2.subscribe(principal(),subscribe()))
    assert r1.subscription_id==r2.subscription_id
    assert len(store.rows)==1
    assert [x[0] for x in store.calls].count("commit")==1
    assert r2.expires_at==NOW+900


def test_distinct_principal_or_url_maps_to_different_deterministic_subscription():
    a,store,access,callback=owner()
    x=run(a.subscribe(principal(),subscribe()))
    y=run(a.subscribe(principal("e"*64),subscribe()))
    z=run(a.subscribe(principal(),dataclasses.replace(subscribe(),
                                         callback_url="https://receiver.example.com/second")))
    assert len({x.subscription_id,y.subscription_id,z.subscription_id})==3
    assert len(store.rows)==3


def test_callback_error_or_bad_echo_cannot_create_subscription():
    for bad in ("wrong_echo", "unauthorized_url", "lost_response"):
        callback=Callback()
        if bad=="wrong_echo": callback.corrupt=True
        elif bad=="unauthorized_url": callback.status=403
        else: callback.error=TimeoutError("maybe delivered")
        adapter,store,_,_=owner(callback=callback)
        from integrations.session_bridge.web_reply_event_rpc import CallbackVerificationError
        failure=(api().SubscriptionEffectUnknown if bad=="lost_response"
                 else CallbackVerificationError)
        with pytest.raises(failure):
            run(adapter.subscribe(principal(),subscribe()))
        assert store.rows=={}


def test_authorization_changed_during_callback_cannot_install_subscription():
    access=Access()
    class RevokingCallback(Callback):
        async def verify(self,url,packet):
            result=await super().verify(url,packet)
            access.active=False
            return result
    adapter,store,_,_=owner(access=access,callback=RevokingCallback())
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.subscribe(principal(),subscribe()))
    assert not store.rows


def test_foreign_owner_grant_refuses_effect_before_callback_or_store():
    access=Access()
    access.owner_override="0"*64
    adapter,store,_,callback=owner(access=access)
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.subscribe(principal(),subscribe()))
    assert not store.calls and not callback.calls


def test_post_commit_lost_ack_is_unknown_and_never_retried():
    store=ExistingStore()
    store.after_write=RuntimeError("connection disappeared AFTER COMMIT")
    adapter,_,_,callback=owner(store=store)
    with pytest.raises(api().SubscriptionEffectUnknown):
        run(adapter.subscribe(principal(),subscribe()))
    assert len(callback.calls)==1
    assert len(store.rows)==1
    assert [x[0] for x in store.calls].count("commit")==1


def test_unsubscribe_is_idempotent_but_requires_same_original_owner():
    a,store,access,callback=owner()
    x=run(a.subscribe(principal(),subscribe()))
    result=run(a.unsubscribe(principal(),unsubscribe()))
    again=run(a.unsubscribe(principal(),unsubscribe()))
    assert result.stopped is True and result.committed is True
    assert again.stopped is True
    assert x.subscription_id not in store.rows
    assert len(callback.calls)==1
    foreign=run(a.unsubscribe(principal("e"*64),unsubscribe()))
    assert foreign.committed is True


def test_revoke_after_commit_not_proven_if_readback_still_exists():
    class UnremovedStore(ExistingStore):
        async def remove(self,subscription_id,owner_key, **kwargs):
            self.calls.append(("remove",subscription_id))
    store=UnremovedStore()
    a,_,_,_=owner(store=store)
    run(a.subscribe(principal(),subscribe()))
    with pytest.raises(api().SubscriptionEffectUnknown):
        run(a.unsubscribe(principal(),unsubscribe()))
    assert len(store.rows)==1


def test_rpc_real_adapter_composes_without_a_second_registry_or_backend():
    a,store,_,callback=owner()
    rpc=WebReplyEventRpc(a,clock=lambda:NOW)
    args={"name":"session.reply_committed","arguments":{"request_ref":"request-001"},
          "delivery":{"mode":"webhook","url":URL,"secret":SECRET},"cursor":None,
          "ttlMs":900_000}
    response=run(rpc.handle({"jsonrpc":"2.0","id":1,"method":"events/subscribe",
                             "params":args},principal()))
    assert response["result"]["id"].startswith("sub_")
    assert response["result"]["cursor"] is None
    assert "whsec_" not in json.dumps(response)
    assert len(store.rows)==1 and len(callback.calls)==1


def test_secret_custody_is_an_explicit_required_store_capability():
    class Incomplete:
        pass
    with pytest.raises(TypeError):
        api().OriginalReplySubscriptionAdapter(
            resolver=Access(),storage=Incomplete(),challenge_sender=Callback(),
            clock=lambda:NOW,enabled=True)


@pytest.mark.parametrize("elapsed", (101, 901))
def test_subscription_never_commits_after_access_or_requested_ttl_expires_during_https(elapsed):
    current=[NOW]
    class SlowCallback(Callback):
        async def verify(self,url,packet):
            result=await super().verify(url,packet)
            current[0]=NOW+elapsed
            return result
    adapter,store,access,cb=owner(callback=SlowCallback(),clock=lambda:current[0])
    short_token=dataclasses.replace(principal(),expires_at=NOW+100)
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.subscribe(short_token,subscribe()))
    assert len(cb.calls)==1 and [x[0] for x in store.calls]==["read"]
    # Expiry is detected before a second owner read or any durable write.
    assert len(access.calls)==1


@pytest.mark.parametrize("invalid", [
    "",
    "request with space",
    "request\nnewline",
    "x"*257,
    "untrusted@example.com",
])
def test_direct_adapter_refuses_malformed_original_request_before_resolver_or_send(invalid):
    adapter,store,access,cb=owner()
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.subscribe(principal(),dataclasses.replace(subscribe(),request_ref=invalid)))
    assert not access.calls and not store.calls and not cb.calls


def test_changed_original_session_revision_during_callback_never_commits():
    class GenerationAccess(Access):
        async def resolve(self,who,request_ref):
            grant=await super().resolve(who,request_ref)
            if len(self.calls)==2:
                return dataclasses.replace(grant,revision="different-generation")
            return grant
    adapter,store,_,cb=owner(access=GenerationAccess())
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.subscribe(principal(),subscribe()))
    assert len(cb.calls)==1 and not store.rows


@pytest.mark.parametrize("bad_attribute", [
    {"read_ref":"untrusted\ncontent"},
    {"revision":"bad\nrevision"},
    {"read_ref":"x"*257},
])
def test_untrusted_original_grant_contract_must_fail_before_network(bad_attribute):
    class InvalidGrant(Access):
        async def resolve(self,who,request_ref):
            return dataclasses.replace(await super().resolve(who,request_ref),**bad_attribute)
    adapter,store,_,cb=owner(access=InvalidGrant())
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.subscribe(principal(),subscribe()))
    assert not store.rows and not cb.calls


def test_durable_readback_mismatch_retains_effect_unknown_not_success():
    class WrongReadback(ExistingStore):
        async def read(self,subscription_id):
            record=await super().read(subscription_id)
            return dataclasses.replace(record,read_ref="wrong-original-read") if record is not None else None
    adapter,store,_,cb=owner(store=WrongReadback())
    with pytest.raises(api().SubscriptionEffectUnknown):
        run(adapter.subscribe(principal(),subscribe()))
    assert len(cb.calls)==1 and len(store.rows)==1


def test_unsubscribe_keeps_effect_unknown_on_lost_remove_ack():
    class RemovalLostAck(ExistingStore):
        async def remove(self,subscription_id,owner_key, **kwargs):
            await super().remove(subscription_id,owner_key, **kwargs)
            raise OSError("connection lost after tombstone commit")
    adapter,store,_,cb=owner(store=RemovalLostAck())
    run(adapter.subscribe(principal(),subscribe()))
    with pytest.raises(api().SubscriptionEffectUnknown):
        run(adapter.unsubscribe(principal(),unsubscribe()))
    assert not store.rows


def test_fresh_verified_callback_is_reused_on_idempotent_refresh_without_new_network():
    store=ExistingStore()
    callback=Callback()
    first,_,_,_=owner(store=store,callback=callback)
    prior=run(first.subscribe(principal(),subscribe()))
    restarted,_,_,_=owner(store=store,callback=callback)
    later=run(restarted.subscribe(principal(),subscribe()))
    assert prior.subscription_id==later.subscription_id
    assert len(callback.calls)==1
    assert len(store.rows)==1
    assert store.rows[later.subscription_id].verified_at==NOW
    assert [x[0] for x in store.calls].count("commit")==1


def test_callback_cache_does_not_renew_itself_forever_after_expiration():
    now=[NOW]
    callback=Callback()
    store=ExistingStore()
    adapter,_,_,_=owner(store=store,callback=callback,clock=lambda:now[0])
    run(adapter.subscribe(principal(),subscribe()))
    now[0]=NOW+301
    run(adapter.subscribe(principal(),subscribe()))
    assert len(callback.calls)==2
    row=next(iter(store.rows.values()))
    assert row.verified_at==NOW+301


def test_rotation_of_chatgpt_signing_secret_requires_new_verified_callback():
    callback=Callback()
    adapter,store,_,_=owner(callback=callback)
    first=run(adapter.subscribe(principal(),subscribe()))
    new_secret="whsec_"+base64.b64encode(b"q"*32).decode()
    second=run(adapter.subscribe(principal(),dataclasses.replace(
        subscribe(),signing_secret=new_secret)))
    assert second.subscription_id==first.subscription_id
    assert len(callback.calls)==2
    assert new_secret not in repr(store.rows[first.subscription_id])


def test_same_owner_refuses_mismatched_store_identity_before_using_cached_callback():
    class Mismatched(ExistingStore):
        async def read(self,subscription_id):
            found=await super().read(subscription_id)
            if found is not None:
                return dataclasses.replace(found,owner_key="other-owner")
            return found
    store=Mismatched()
    callback=Callback()
    adapter,_,_,_=owner(store=store,callback=callback)
    # First commit would fail readback: create an existing forged row directly.
    subid=api()._subscription_id(api().owner_key(principal()),subscribe().request_ref,URL)
    store.rows[subid]=api().StoredReplySubscription(
        subscription_id=subid,owner_key="other-owner",
        request_ref="request-001", callback_url_digest="x"*64,
        signing_secret_digest="y"*64,read_ref="native-return-read-001",
        revision="current-generation-001",expires_at=NOW+900,verified_at=NOW)
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.subscribe(principal(),subscribe()))
    assert not callback.calls


def test_expired_token_during_committed_write_never_reports_accepted_subscription():
    now=[NOW]
    class SlowCommittedStore(ExistingStore):
        async def commit(self,record,secret, **kwargs):
            result=await super().commit(record,secret, **kwargs)
            now[0]=NOW+110
            return result
    store=SlowCommittedStore()
    callback=Callback()
    adapter,_,_,_=owner(store=store,callback=callback,clock=lambda:now[0])
    token=dataclasses.replace(principal(),expires_at=NOW+100)
    with pytest.raises(api().SubscriptionEffectUnknown):
        run(adapter.subscribe(token,subscribe()))
    assert len(callback.calls)==1 and len(store.rows)==1


def test_revoked_request_after_commit_cannot_be_promoted_to_completed_grant():
    access=Access()
    class RevokingOnCommit(ExistingStore):
        async def commit(self,record,secret, **kwargs):
            result=await super().commit(record,secret, **kwargs)
            access.active=False
            return result
    store=RevokingOnCommit()
    adapter,_,_,cb=owner(store=store,access=access)
    with pytest.raises(api().SubscriptionEffectUnknown):
        run(adapter.subscribe(principal(),subscribe()))
    assert len(cb.calls)==1 and len(store.rows)==1


def test_lost_commit_ack_reconciles_existing_exact_record_without_replay():
    store=ExistingStore()
    store.after_write=ConnectionError("ACK lost AFTER durable write")
    callback=Callback()
    adapter,_,_,_=owner(store=store,callback=callback)
    with pytest.raises(api().SubscriptionEffectUnknown):
        run(adapter.subscribe(principal(),subscribe()))
    assert len(store.rows)==1
    assert [x[0] for x in store.calls].count("commit")==1
    store.after_write=None
    receipt=run(adapter.subscribe(principal(),subscribe()))
    assert receipt.persisted is True and receipt.callback_verified is True
    assert len(store.rows)==1
    assert [x[0] for x in store.calls].count("commit")==1
    assert len(callback.calls)==1


def test_owned_unsubscribe_survives_writer_retirement_but_not_expired_principal():
    adapter, store, access, _ = owner()
    run(adapter.subscribe(principal(),subscribe()))
    access.active=False
    calls=len(access.calls)
    assert run(adapter.unsubscribe(principal(),unsubscribe())).stopped is True
    assert len(access.calls)==calls and not store.rows
    with pytest.raises(api().SubscriptionUnavailable):
        run(adapter.unsubscribe(dataclasses.replace(principal(),expires_at=NOW),unsubscribe()))
