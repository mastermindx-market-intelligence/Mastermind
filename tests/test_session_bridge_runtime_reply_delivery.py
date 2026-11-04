"""Executable real Runtime/canonical-owner composition with a fake HTTPS peer."""
import asyncio
import base64
import dataclasses
import hashlib
import socket
import time
from types import SimpleNamespace

import pytest

import test_session_bridge_runtime_return as native
from integrations.session_bridge.web_reply_subscription_owner import StoredReplySubscription, owner_key, _subscription_id
from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher, RuntimeReplySubscriptionStore

setup = native.setup
URL = "https://receiver.example.com/callback_test_private"
SECRET = "whsec_" + base64.b64encode(b"a" * 32).decode()


def run(awaitable):
    return asyncio.run(awaitable)


def composition(s, *, enabled=True, status=200, error=False):
    from integrations.session_bridge.runtime_reply_delivery import build_runtime_reply_delivery
    ref = native.populate(s)
    event, value = s.owner._stored_request(ref)
    now = int(time.time())
    store = RuntimeReplySubscriptionStore(s.runtime, ExecutiveReplyCipher("fixture-key", b"k" * 32), clock=lambda: now)
    record = StoredReplySubscription(subscription_id=_subscription_id(owner_key(s.projection), event.command_id, URL),
        owner_key=owner_key(s.projection), request_ref=event.command_id, read_ref=ref, revision="fixture-original-grant",
        expires_at=now+300, verified_at=now, callback_url_digest=hashlib.sha256(URL.encode()).hexdigest(),
        signing_secret_digest=hashlib.sha256(SECRET.encode()).hexdigest())
    run(store.commit(record,SECRET,callback_url=URL,expected_version="empty"))
    calls=[]
    class Connection:
        def request(self,*args,**kwargs):
            calls.append((args,kwargs))
            if error:raise TimeoutError("fake lost response")
        def getresponse(self):return SimpleNamespace(status=status,read=lambda _size:b"accepted")
        def close(self):pass
    def resolver(*_args,**_kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,"",("93.184.216.34",443))]
    delivery=build_runtime_reply_delivery(s.owner,store,clock=lambda:now,enabled=enabled,
        resolver=resolver,connector=lambda *_args:Connection())
    return delivery,store,record,calls


def test_real_canonical_reply_projects_signs_and_sends_once_without_consumption(setup):
    delivery,store,record,calls=composition(setup)
    first=run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert first["state"]=="TRANSPORT_ACCEPTED_PARENT_UNPROVEN" and first["parent_consumed"] is False
    assert len(calls)==1 and calls[0][0][0]=="POST"
    second=run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert second["fresh_send"] is False and len(calls)==1
    assert run(store.delivery_status(first["delivery_ref"]))["parent_consumed"] is False


def test_default_disabled_composition_has_no_read_reservation_or_send(setup):
    delivery,_,record,calls=composition(setup,enabled=False)
    before=len(setup.service.calls)
    with pytest.raises(ValueError):run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert len(setup.service.calls)==before and not calls
    assert not setup.runtime.store.list_events(aggregate_type="reply_subscription_delivery")


@pytest.mark.parametrize("fault",["foreign","expired","submit_only","dict"])
def test_current_original_read_identity_required_before_effect(setup,fault):
    delivery,_,record,calls=composition(setup)
    p=setup.principal
    if fault=="foreign":p=dataclasses.replace(p,subject_digest="f"*64)
    elif fault=="expired":p=dataclasses.replace(p,expires_at=p.issued_at)
    elif fault=="submit_only":p=dataclasses.replace(p,scopes=("mastermind.executive.intent.submit",))
    else:p=dataclasses.asdict(p)
    with pytest.raises(ValueError):run(delivery.deliver_current(p,record.subscription_id))
    assert not calls and not setup.runtime.store.list_events(aggregate_type="reply_subscription_delivery")


def test_committed_reply_delivery_survives_writer_disarm(setup):
    delivery,_,record,calls=composition(setup)
    setup.enabled[0]=False
    result=run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert result["state"]=="TRANSPORT_ACCEPTED_PARENT_UNPROVEN" and len(calls)==1


def test_lost_http_response_is_unknown_and_never_replayed(setup):
    delivery,_,record,calls=composition(setup,error=True)
    first=run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert first["state"]=="EFFECT_UNKNOWN" and len(calls)==1
    second=run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert second["fresh_send"] is False and len(calls)==1


def test_late_revocation_before_sender_prevents_http_and_keeps_original_attempt(setup,monkeypatch):
    delivery,store,record,calls=composition(setup)
    resolving=delivery._events.resolve
    count=[0]
    async def revoke_on_revalidation(*args,**kwargs):
        event=await resolving(*args,**kwargs)
        count[0]+=1
        if count[0]==2:
            snapshot=await store.snapshot(record.subscription_id)
            await store.remove(record.subscription_id,record.owner_key,request_ref=record.request_ref,
                callback_url_digest=record.callback_url_digest,expected_version=snapshot.version)
        return event
    monkeypatch.setattr(delivery._events,"resolve",revoke_on_revalidation)
    result=run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert result["state"]=="NOT_SENT" and not calls
    assert len(setup.runtime.store.list_events(aggregate_type="reply_subscription_delivery"))==2


def test_expiry_while_waiting_for_io_lane_never_enters_transport(setup,monkeypatch):
    delivery,_,record,calls=composition(setup)
    async def queued_then_expired(function,*args,**kwargs):
        delivery._events._reader._clock=lambda:setup.principal.expires_at+1
        delivery._clock=lambda:setup.principal.expires_at+1
        return function(*args,**kwargs)
    monkeypatch.setattr(asyncio,"to_thread",queued_then_expired)
    result=run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert result["state"]=="NOT_SENT" and not calls


def test_duplicate_canonical_reply_during_async_read_refuses_before_reservation(setup):
    import copy
    delivery,_,record,calls=composition(setup)
    reads=[0]
    def duplicate_on_snapshot_read():
        reads[0]+=1
        if reads[0]==2:setup.service.items.append(copy.deepcopy(setup.service.items[-1]))
    setup.service.on_read=duplicate_on_snapshot_read
    with pytest.raises(ValueError):run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert not calls and not setup.runtime.store.list_events(aggregate_type="reply_subscription_delivery")


@pytest.mark.parametrize("status,expected",[(410,"DELIVERY_TERMINAL_REFUSAL"),(503,"RETRY_DECISION_BY_EXISTING_OWNER")])
def test_http_classification_is_advisory_and_does_not_autoretry(setup,status,expected):
    delivery,_,record,calls=composition(setup,status=status)
    first=run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert first["state"]==expected and first["parent_consumed"] is False
    second=run(delivery.deliver_current(setup.principal,record.subscription_id))
    assert second["fresh_send"] is False and len(calls)==1
