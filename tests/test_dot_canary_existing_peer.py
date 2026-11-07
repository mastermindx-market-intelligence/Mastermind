"""Chris-Dot event over the REAL existing Executive App-peer and Runtime store.

Fake Slack/HTTPS and synthetic neutral principal; not an OpenAI account canary.
"""
import asyncio
import dataclasses
import json

from integrations.slack_agent_dialogue.dot_canary_event import TrustedCanaryPolicy
from integrations.session_bridge.dot_canary_mcp_route import (
    CANARY_SCOPE, CanarySubscribeRequest, CanaryUnsubscribeRequest,
)
from integrations.session_bridge.runtime_reply_subscriptions import ExecutiveReplyCipher
from integrations.session_bridge.web_reply_subscription_owner import owner_key
from integrations.session_bridge.installed_reply_events import RuntimeReplyEventHost
from test_session_bridge_reply_event_host_integration import (
    event_case, short_socket_root, with_peer, URL, SECRET,
    authenticated_receiver, native_case,
)


def admit(s):
    source=s.host
    who=s.principal
    policy=TrustedCanaryPolicy(
        workspace_id="T0BRD2AQXQV",channel_id="C0BSBM78V1N",
        relay_bot_user_id="U0BT71H4FQE",owner_slack_user_id="U0BRET6191C",
        principal_digest=owner_key(who),
        not_before_ts="1794017500.000001",current=True,
    )
    s.host=RuntimeReplyEventHost(
        s.owner,ExecutiveReplyCipher("fixture-key",b"k"*32),
        s.auth.policies,clock=lambda:s.auth.now[0],enabled=True,
        resolver=source.challenge.resolver,connector=source.challenge.connector,
        canary_policy_provider=lambda principal:policy,
    )
    return who,policy


def test_exact_existing_peer_challenge_persists_chris_subscription(event_case,tmp_path,short_socket_root):
    s=event_case
    who,policy=admit(s)
    async def act(client,service):
        observed=await client._call("canary_policy",who,{})
        assert observed==dataclasses.asdict(policy)
        subscribed=await client._call("canary_subscribe",who,dataclasses.asdict(
            CanarySubscribeRequest("C0BSBM78V1N",URL,SECRET,240000)))
        return subscribed
    receipt=asyncio.run(with_peer(s,tmp_path,short_socket_root,act))
    assert receipt["persisted"] is True and receipt["callback_verified"] is True
    assert receipt["owner_access_current"] is True
    assert len(s.http)==1 and s.http[0][0]["type"]=="verification"
    stored=s.host.canary_owner.store
    record=asyncio.run(stored.read(receipt["subscription_id"]))
    assert record.channel_id=="C0BSBM78V1N"
    view=stored.delivery_view(record.subscription_id,
        expected_version=asyncio.run(stored.snapshot(record.subscription_id)).version,
        owner_key=owner_key(who))
    assert view.signing_secrets==(SECRET,)
    assert SECRET not in json.dumps([e.to_dict() for e in s.f.runtime.store.list_events()])
    assert URL not in json.dumps([e.to_dict() for e in s.f.runtime.store.list_events()])


def test_original_default_off_host_does_not_grant_canary(event_case,tmp_path,short_socket_root):
    s=event_case
    who=s.principal
    async def act(client,service):
        return await client._call("canary_policy",who,{})
    try:
        asyncio.run(with_peer(s,tmp_path,short_socket_root,act))
    except Exception:
        pass
    else:
        raise AssertionError("no canary enrollment may be inferred")
    assert s.host.canary_owner is None


def test_existing_peer_unsubscribe_revokes_current_chris_subscription(event_case,tmp_path,short_socket_root):
    s=event_case
    who,policy=admit(s)
    async def act(client,service):
        enrolled=await client._call("canary_subscribe",who,dataclasses.asdict(
            CanarySubscribeRequest("C0BSBM78V1N",URL,SECRET,240000)))
        stopped=await client._call("canary_unsubscribe",who,dataclasses.asdict(
            CanaryUnsubscribeRequest("C0BSBM78V1N",URL)))
        return enrolled,stopped
    enrolled,stopped=asyncio.run(with_peer(s,tmp_path,short_socket_root,act))
    assert stopped=={"stopped":True,"committed":True}
    assert asyncio.run(s.host.canary_owner.store.read(enrolled["subscription_id"])) is None



def test_canary_delivery_over_original_authenticated_CeoIngress_peer(
    event_case,tmp_path,short_socket_root,monkeypatch,
):
    """No new listener: existing App peer -> enrolled A2 reader -> 1 callback."""
    s=event_case
    who,policy=admit(s)
    from integrations.session_bridge.installed_dot_canary_source import InstalledA2CanaryReader
    import integrations.session_bridge.installed_dot_canary_source as source_module
    from test_dot_canary_reader import source, ROOT, MESSAGE
    local_source,http = source(policy=policy)
    async def a2_transport(socket_path,request,*,timeout_seconds):
        assert request["operation"]=="read_dot_canary"
        args=request["args"]
        assert args["principal_digest"]==policy.principal_digest
        observed=await local_source.observe(
            thread_ts=args["thread_ts"],message_ts=args["message_ts"],
        )
        return {"ok":True,"result":{
            "state":"OBSERVED" if observed else "NOT_ELIGIBLE",
            "message":dataclasses.asdict(observed) if observed else None,
        }}
    monkeypatch.setattr(source_module,"InstalledA2CanaryReader",
        lambda path,current:InstalledA2CanaryReader(
            path,current,transport=a2_transport,
        ))
    async def exercise(client,service):
        enrolled=await client._call("canary_subscribe",who,dataclasses.asdict(
            CanarySubscribeRequest("C0BSBM78V1N",URL,SECRET,240000)))
        assert enrolled["persisted"] is True
        params={"thread_ts":ROOT,"message_ts":MESSAGE}
        once=await client._call("canary_deliver",who,params)
        twice=await client._call("canary_deliver",who,params)
        return once,twice
    once,twice=asyncio.run(with_peer(s,tmp_path,short_socket_root,exercise))
    assert len(once)==len(twice)==1
    assert once[0]["state"]=="RECEIVED" and once[0]["fresh_send"] is True
    assert once[0]["dot_consumed"] is False
    assert twice[0]["state"]=="RECEIVED" and twice[0]["fresh_send"] is False
    assert len(s.http)==2  # one verification + one owner-authorized event
    assert s.http[1][0]["name"]=="mastermind.slack_canary_message"
    assert len(http.calls)==2  # each user-triggered read, no W3C/poller
