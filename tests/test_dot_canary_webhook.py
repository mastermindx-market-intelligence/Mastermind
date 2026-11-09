"""Signed Chris-Dot event meets original Executive one-shot webhook transport.

All DNS, TLS/Slack and OAuth are synthetic: no live send, store or account grant.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import socket

import pytest

from integrations.slack_agent_dialogue.dot_canary_event import (
    EVENT_NAME, MARKER, TrustedCanaryPolicy, VerifiedSlackCanaryMessage,
    project_canary_message,
)
from integrations.session_bridge.dot_canary_webhook import (
    VerifiedCanarySubscription, prepare_canary_webhook,
)
from integrations.session_bridge.web_reply_callback_transport import (
    CallbackDestinationRefused, send_once,
)
from test_session_bridge_web_reply_callback_transport import (
    FakeConnection, resolver,
)

NOW = 1794017601
URL = "https://receiver.example.com/mcp-events/callback_123"
SECRET = "whsec_" + base64.b64encode(b"k" * 32).decode("ascii")
POLICY = TrustedCanaryPolicy(
    workspace_id="T0BRD2AQXQV",channel_id="C0BSBM78V1N",
    relay_bot_user_id="U0BT71H4FQE",owner_slack_user_id="U0BRET6191C",
    principal_digest=hashlib.sha256(b"fake-Chris-identity").hexdigest(),
    not_before_ts="1794017500.000001",current=True,
)
MSG = VerifiedSlackCanaryMessage(
    workspace_id=POLICY.workspace_id,channel_id=POLICY.channel_id,
    ts="1794017600.000001",author_user_id=POLICY.owner_slack_user_id,
    text=MARKER + " harmless owner-authored test message.",
    thread_ts="1794017500.000002",history_complete=True,
    mutation_evidence_complete=True,
)


def event():
    return project_canary_message(POLICY,MSG,
        authenticated_principal_digest=POLICY.principal_digest,
        arguments={"channel_id":POLICY.channel_id})


def binding(**changes):
    return VerifiedCanarySubscription(
        subscription_id=changes.pop("subscription_id","sub_chrisdot001"),
        principal_digest=changes.pop("principal_digest",POLICY.principal_digest),
        channel_id=changes.pop("channel_id",POLICY.channel_id),
        event_name=changes.pop("event_name",EVENT_NAME),
        expires_at=changes.pop("expires_at",NOW+300),
        authorized_until=changes.pop("authorized_until",NOW+600),
        active=changes.pop("active",True),
        access_current=changes.pop("access_current",True),
        signing_secrets=changes.pop("signing_secrets",(SECRET,)),
        **changes,
    )


def sign(*, owner=None, data=None, account_policy=None):
    return prepare_canary_webhook(
        subscription=binding() if owner is None else owner,
        policy=POLICY if account_policy is None else account_policy,
        event=event() if data is None else data,
        signed_at=NOW,
    )


def test_canary_signing_uses_original_standard_webhooks_and_exact_event_id():
    signed = sign()
    data = json.loads(signed.body)
    assert data == event()
    assert signed.headers["webhook-id"] == event()["eventId"]
    assert signed.headers["X-MCP-Subscription-Id"] == "sub_chrisdot001"
    assert signed.headers["webhook-timestamp"] == str(NOW)
    digest = hmac.new(
        b"k"*32,(event()["eventId"] + f".{NOW}.").encode() + signed.body,
        hashlib.sha256,
    ).digest()
    assert signed.headers["webhook-signature"] == "v1," + base64.b64encode(digest).decode("ascii")
    assert SECRET not in repr(signed)
    assert SECRET not in repr(binding())


def test_existing_ssrf_safe_transport_accepts_exact_canary_packet_without_new_sender():
    connection=FakeConnection(status=202,body=b"")
    receipt=send_once(URL,sign(),resolver=resolver,connector=lambda *a:connection)
    assert receipt.status_code == 202
    assert len(connection.calls)==1 and connection.closed
    method,path,body,headers=connection.calls[0]
    assert method=="POST" and path=="/mcp-events/callback_123"
    assert body==sign().body and headers["webhook-id"]==event()["eventId"]
    assert "challenge" not in body.decode("utf-8")
    assert not hasattr(receipt,"dot_executed")


@pytest.mark.parametrize("changes",[
    {"active":False}, {"access_current":False},
    {"principal_digest":"f"*64}, {"channel_id":"C0BRFC9JXK8"},
    {"event_name":"session.reply_committed"},
    {"expires_at":NOW}, {"expires_at":NOW+900},
    {"authorized_until":NOW-1},
    {"signing_secrets":()},
    {"signing_secrets":(SECRET,SECRET)},
    {"signing_secrets":("whsec_fake",)},
])
def test_foreign_or_expired_subscription_cannot_sign(changes):
    with pytest.raises(ValueError):
        sign(owner=binding(**changes))


@pytest.mark.parametrize("changes",[
    {"current":False},
    {"workspace_id":"T0BRD2AQXQW"},
    {"channel_id":"C0BRFC9JXK8"},
    {"owner_slack_user_id":"U0BR1GQH7SB"},
    {"not_before_ts":MSG.ts},
])
def test_revoked_or_different_policy_cannot_sign(changes):
    with pytest.raises(ValueError):
        sign(account_policy=dataclasses.replace(POLICY,**changes))


@pytest.mark.parametrize("changes",[
    {"name":"session.reply_committed"}, {"cursor":"replay-001"},
    {"eventId":"evt-"+"f"*64}, {"timestamp":"2026-10-12T01:00:00.000001Z"},
    {"extra_instruction":"reply to me"},
    {"data":{"channel_id":"C0BRFC9JXK8"}},
])
def test_malformed_or_replayed_canary_data_not_signed(changes):
    with pytest.raises(ValueError):
        sign(data={**event(),**changes})


@pytest.mark.parametrize("changes",[
    {"text":MARKER+"X"*400}, {"untrusted_text":False},
    {"message_ts":"18000000000.000001"},
    {"author_user_id":"U0BR1GQH7SB"},
    {"thread_ts":"invalid"},
    {"workspace_id":"T0BRD2AQXQW"},
])
def test_forged_signed_body_refused_pre_dns_even_if_headers_are_present(changes):
    signed=sign()
    forged_body=json.dumps({**event(),"data":{**event()["data"],**changes}},
        sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")
    fake=dataclasses.replace(signed,body=forged_body)
    visited=[]
    with pytest.raises(CallbackDestinationRefused):
        send_once(URL,fake,resolver=lambda *a,**kw:visited.append("dns"),
                         connector=lambda *a:visited.append("socket"))
    assert visited == []


def test_canary_transport_refuses_mismatched_webhook_id_without_dns():
    signed=sign()
    fake=dataclasses.replace(signed,headers={**signed.headers,
        "webhook-id":"evt-"+"f"*64})
    called=[]
    with pytest.raises(CallbackDestinationRefused):
        send_once(URL,fake,resolver=lambda *a,**kw:called.append("dns"))
    assert called==[]


def test_unknown_event_and_control_schema_preserve_original_transport_guards():
    signed=sign()
    forged=json.dumps({**event(),"name":"other.event"},sort_keys=True,
        separators=(",",":"),ensure_ascii=True).encode("ascii")
    fake=dataclasses.replace(signed,body=forged)
    called=[]
    with pytest.raises(CallbackDestinationRefused):
        send_once(URL,fake,resolver=lambda *a,**kw:called.append("dns"))
    assert called==[]
