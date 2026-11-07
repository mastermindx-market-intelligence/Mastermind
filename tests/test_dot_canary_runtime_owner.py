"""Chris-Dot original Runtime subscriber: verified synthetic challenge and durable CAS.

No actual Slack user/app OAuth or external HTTP.
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json

import pytest

from control_plane.executive_runtime import Runtime
from control_plane.principal_projection import neutral_principal_projection
from integrations.business_mcp_auth.contracts import AUTH_POLICY_SCHEMA,load_resource_policy
from integrations.mastermind_executive_app.gateway import AppPolicies
from integrations.session_bridge.reply_policy_selection import ReplyPolicySelection
from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher
from integrations.session_bridge.runtime_dot_canary_subscriptions import RuntimeCanarySubscriptionStore
from integrations.session_bridge.runtime_dot_canary_owner import RuntimeCanarySubscriptionOwner
from integrations.session_bridge.dot_canary_mcp_route import (
    CANARY_SCOPE,CanarySubscribeRequest,CanaryUnsubscribeRequest,
)
from integrations.session_bridge.web_reply_subscription_owner import (
    VerifiedChallengeHTTP,SubscriptionEffectUnknown,owner_key,
)
from integrations.slack_agent_dialogue.dot_canary_event import TrustedCanaryPolicy

NOW=1794017601
URL="https://receiver.example.com/mcp-events/callback_123"
SECRET="whsec_"+base64.b64encode(b"s"*32).decode("ascii")
CHANNEL="C0BSBM78V1N"
ISSUER="https://auth.example.com/"
RESOURCE="https://mcp.mastermind-x.com"


def call(awaitable):
    return asyncio.run(awaitable)


def principal(*,subject="a"*64,scopes=(CANARY_SCOPE,)):
    return neutral_principal_projection(
        policy_id="mmx-chris-dot",issuer=ISSUER,
        issuer_digest=hashlib.sha256(ISSUER.encode()).hexdigest(),
        resource=RESOURCE,subject_digest=subject,client_ref="b"*64,
        scopes=scopes,issued_at=NOW-30,expires_at=NOW+600,jti_digest=None,
    )


def resources():
    p=principal()
    raw=dict(schema=AUTH_POLICY_SCHEMA,policy_id=p.policy_id,resource=p.resource,
        resource_metadata_url=RESOURCE+"/.well-known/oauth-protected-resource/mcp",
        issuer=ISSUER,authorization_servers=[ISSUER],
        jwks_uri=ISSUER+".well-known/jwks.json",
        required_scopes=sorted(p.scopes),allowed_subject_digests=[p.subject_digest],
        allowed_algorithms=["RS256"],clock_skew_seconds=0,
        max_token_lifetime_seconds=1800,jwks_cache_ttl_seconds=300,
        unknown_kid_refresh_cooldown_seconds=30,fetch_failure_backoff_seconds=5)
    accepted=load_resource_policy(raw)
    alt=load_resource_policy({**raw,"policy_id":"mmx-chris-dot-submit",
        "required_scopes":sorted(["mastermind.executive.read",
                                   "mastermind.executive.intent.submit"])})
    return ReplyPolicySelection((AppPolicies(read=accepted,submit=alt),))


class Challenge:
    def __init__(self):
        self.calls=[]
        self.fail=False
        self.on_success=None

    async def verify(self,url,packet):
        self.calls.append((url,packet))
        if self.fail:
            raise TimeoutError("unconfirmed callback")
        value=json.loads(packet.body)
        assert value["type"]=="verification"
        if self.on_success:
            self.on_success()
        return VerifiedChallengeHTTP(200,json.dumps({"challenge":value["challenge"]}).encode())


def make_case(tmp_path):
    runtime=Runtime.at(tmp_path)
    cipher=ExecutiveReplyCipher("existing-key",b"k"*32)
    store=RuntimeCanarySubscriptionStore(runtime,cipher,clock=lambda:NOW)
    policy=TrustedCanaryPolicy(
        workspace_id="T0BRD2AQXQV",channel_id=CHANNEL,
        relay_bot_user_id="U0BT71H4FQE",owner_slack_user_id="U0BRET6191C",
        principal_digest=owner_key(principal()),not_before_ts="1794017500.000001",
        current=True,
    )
    state=[policy]
    challenge=Challenge()
    handler=RuntimeCanarySubscriptionOwner(
        store,resources(),challenge,clock=lambda:NOW,enabled=True,
        policy_provider=lambda who:state[0],
    )
    return runtime,store,state,challenge,handler


def request():
    return CanarySubscribeRequest(
        channel_id=CHANNEL,callback_url=URL,signing_secret=SECRET,
        requested_ttl_ms=300000,
    )


def test_owner_challenges_once_persists_and_refreshes_without_duplicate_effect(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    p=principal()
    assert call(handler.policy_for(p))==state[0]
    a=call(handler.subscribe(p,request()))
    assert a.callback_verified is True and a.persisted is True and a.owner_access_current is True
    assert len(challenge.calls)==1
    assert a.expires_at==NOW+300
    assert call(store.read(a.subscription_id)) is not None
    pre=list(runtime.store.list_events())
    b=call(handler.subscribe(p,request()))
    assert a==b and len(challenge.calls)==1
    assert runtime.store.list_events()==pre
    unsub=call(handler.unsubscribe(p,CanaryUnsubscribeRequest(CHANNEL,URL)))
    assert unsub.stopped is True and unsub.committed is True
    assert call(store.read(a.subscription_id)) is None


def test_account_owner_and_scope_deny_before_callback_or_write(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    foreign=principal(subject="c"*64)
    assert call(handler.policy_for(foreign)) is None
    with pytest.raises(Exception):
        call(handler.subscribe(foreign,request()))
    wrong_scope=principal(scopes=())
    assert call(handler.policy_for(wrong_scope)) is None
    with pytest.raises(Exception):
        call(handler.subscribe(wrong_scope,request()))
    assert not challenge.calls and not runtime.store.list_events()


def test_wrong_channel_or_policy_change_during_challenge_fails_closed(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    bad=dataclasses.replace(request(),channel_id="C0BRFC9JXK8")
    with pytest.raises(Exception):
        call(handler.subscribe(principal(),bad))
    assert not challenge.calls
    challenge.on_success=lambda:state.__setitem__(0,dataclasses.replace(state[0],current=False))
    with pytest.raises(Exception):
        call(handler.subscribe(principal(),request()))
    assert len(challenge.calls)==1 and runtime.store.list_events()==[]


def test_uncertain_challenge_is_not_persisted_or_retried(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    challenge.fail=True
    with pytest.raises(SubscriptionEffectUnknown):
        call(handler.subscribe(principal(),request()))
    assert len(challenge.calls)==1
    assert not runtime.store.list_events()


def test_lost_commit_ack_is_fenced_by_canonical_readback(tmp_path,monkeypatch):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    original=store.commit
    async def lost_ack(*args,**kwargs):
        await original(*args,**kwargs)
        raise RuntimeError("unknown response after committed write")
    monkeypatch.setattr(store,"commit",lost_ack)
    with pytest.raises(SubscriptionEffectUnknown):
        call(handler.subscribe(principal(),request()))
    assert len(challenge.calls)==1
    assert len(runtime.store.list_events(aggregate_type="reply_subscription"))==1


def test_policy_fingerprint_change_refuses_discovery_and_new_subscribe(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    handler.policy_provider=lambda who:None
    assert call(handler.policy_for(principal())) is None
    with pytest.raises(Exception):
        call(handler.subscribe(principal(),request()))
    assert not runtime.store.list_events()


def test_subscription_lifetime_bounded_by_authenticated_principal(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    long=dataclasses.replace(request(),requested_ttl_ms=8*24*60*60*1000)
    with pytest.raises(Exception):
        call(handler.subscribe(principal(),long))
    accepted=call(handler.subscribe(principal(),dataclasses.replace(request(),requested_ttl_ms=700000)))
    assert accepted.expires_at == NOW+600


def test_inert_owner_never_advertises_or_subscribes(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    handler.enabled=False
    assert call(handler.policy_for(principal())) is None
    with pytest.raises(Exception):
        call(handler.subscribe(principal(),request()))
    assert not challenge.calls and not runtime.store.list_events()
