"""Disposable Runtime + existing Slack A2 reader -> exactly one fake webhook.

No live Slack, OpenAI callback, OAuth client or Executive service activated.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from integrations.session_bridge.runtime_dot_canary_delivery import (
    RuntimeCanaryDeliveryConsumer,
)
from integrations.session_bridge.dot_canary_mcp_route import (
    CanarySubscribeRequest, CanaryUnsubscribeRequest,
)
from test_dot_canary_runtime_owner import make_case, principal, NOW, SECRET, URL, CHANNEL
from test_dot_canary_reader import source, FakeSlack, messages, ROOT, MESSAGE, MARKER
from test_session_bridge_web_reply_callback_transport import FakeConnection, resolver


def run(c):
    return asyncio.run(c)


def subscribe(owner):
    return run(owner.subscribe(principal(),CanarySubscribeRequest(
        CHANNEL,URL,SECRET,300000,
    )))


def test_original_a2_to_runtime_encrypted_reservation_to_single_signed_webhook(tmp_path):
    runtime,store,policy_state,challenge,handler=make_case(tmp_path)
    receipt=subscribe(handler)
    reader,slack=source(policy=policy_state[0])
    connection=FakeConnection(status=202,body=b"")
    consumer=RuntimeCanaryDeliveryConsumer(
        handler,resolver=resolver,connector=lambda *a:connection,
    )
    first=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert len(first)==1 and first[0].state=="RECEIVED"
    assert first[0].fresh_send is True and first[0].dot_consumed is False
    assert len(connection.calls)==1
    posted=json.loads(connection.calls[0][2])
    assert posted["data"]["text"].startswith(MARKER)
    assert posted["data"]["author_user_id"]==policy_state[0].owner_slack_user_id
    assert posted["name"]=="mastermind.slack_canary_message"
    assert posted["eventId"]==connection.calls[0][3]["webhook-id"]
    again=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert again[0].state=="RECEIVED" and again[0].fresh_send is False
    assert len(connection.calls)==1
    assert store.delivery_status(first[0].delivery_ref)=="RECEIVED"


def test_owner_or_marker_mismatch_cannot_reserve_or_send(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    subscribe(handler)
    foreign=messages()
    foreign[1]["user"]="U0BR1GQH7SB"
    reader,_=source(FakeSlack(foreign),policy=state[0])
    connection=FakeConnection()
    consumer=RuntimeCanaryDeliveryConsumer(handler,resolver=resolver,connector=lambda *a:connection)
    result=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert result[0].state=="NOT_ELIGIBLE"
    assert len(connection.calls)==0
    assert runtime.store.list_events(aggregate_type="reply_subscription_delivery")==[]


def test_revoked_account_refuses_before_reserving_any_delivery(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    subscribe(handler)
    state[0]=__import__("dataclasses").replace(state[0],current=False)
    reader,_=source(policy=__import__("dataclasses").replace(state[0],current=True))
    connection=FakeConnection()
    consumer=RuntimeCanaryDeliveryConsumer(handler,resolver=resolver,connector=lambda *a:connection)
    result=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert result[0].state=="AUTH_UNAVAILABLE"
    assert len(connection.calls)==0


def test_ambiguous_post_send_response_is_never_retried(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    subscribe(handler)
    reader,_=source(policy=state[0])
    connection=FakeConnection(fail_phase="read")
    consumer=RuntimeCanaryDeliveryConsumer(handler,resolver=resolver,connector=lambda *a:connection)
    first=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert first[0].state=="EFFECT_UNKNOWN"
    assert first[0].fresh_send is True
    assert len(connection.calls)==1
    second=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert second[0].fresh_send is False
    assert second[0].state=="EFFECT_UNKNOWN"
    assert len(connection.calls)==1


def test_incomplete_history_is_not_sent(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    subscribe(handler)
    reader,_=source(FakeSlack(complete=False),policy=state[0])
    connection=FakeConnection()
    consumer=RuntimeCanaryDeliveryConsumer(handler,resolver=resolver,connector=lambda *a:connection)
    result=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert result[0].state=="SOURCE_UNAVAILABLE"
    assert len(connection.calls)==0


def test_unsubscribe_prevents_new_delivery(tmp_path):
    runtime,store,state,challenge,handler=make_case(tmp_path)
    subscribe(handler)
    run(handler.unsubscribe(principal(),CanaryUnsubscribeRequest(CHANNEL,URL)))
    reader,_=source(policy=state[0])
    connection=FakeConnection()
    consumer=RuntimeCanaryDeliveryConsumer(handler,resolver=resolver,connector=lambda *a:connection)
    result=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert result[0].state=="NO_SUBSCRIPTION" and not result[0].fresh_send
    assert len(connection.calls)==0



def test_A2_service_peer_read_to_existing_executive_runtime_single_callback(tmp_path):
    from test_dot_canary_existing_a2_service import create
    runtime,store,state,challenge,handler=make_case(tmp_path)
    subscribe(handler)
    reader,slack,service=create(tmp_path,selected_policy=state[0])
    conn=FakeConnection(status=200,body=b"")
    consumer=RuntimeCanaryDeliveryConsumer(
        handler,resolver=resolver,connector=lambda *a:conn,
    )
    accepted=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert accepted[0].state=="RECEIVED"
    assert accepted[0].fresh_send
    assert len(conn.calls)==1 and conn.closed
    assert len(slack.calls)==1 and slack.calls[0][1]=="conversations.replies"
    again=run(consumer.deliver_one(reader,thread_ts=ROOT,message_ts=MESSAGE))
    assert again[0].fresh_send is False and again[0].state=="RECEIVED"
    assert len(conn.calls)==1
