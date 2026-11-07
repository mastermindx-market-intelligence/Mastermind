"""Default-off Chris-Dot MCP Events routing; no network, Slack, OAuth or store writes."""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import hashlib
import json

import pytest

from control_plane.principal_projection import neutral_principal_projection
from integrations.session_bridge.web_reply_event_rpc import WebReplyEventRpc
from integrations.session_bridge.web_reply_subscription_owner import owner_key
from integrations.session_bridge.dot_canary_mcp_route import (
    CANARY_SCOPE, CanarySubscriptionReceipt, CanaryUnsubscribeReceipt,
)
from integrations.slack_agent_dialogue.dot_canary_event import (
    EVENT_NAME, TrustedCanaryPolicy,
)

NOW = 1791766800
URL = "https://receiver.example.com/mcp-events/callback_123"
SECRET = "whsec_" + base64.b64encode(b"k" * 32).decode("ascii")
CHANNEL = "C0BSBM78V1N"


def principal(scopes=(CANARY_SCOPE,), *, subject="a" * 64):
    issuer = "https://auth.example.com"
    return neutral_principal_projection(
        policy_id="mmx-chris-dot-canary",
        issuer=issuer, issuer_digest=hashlib.sha256(issuer.encode()).hexdigest(),
        resource="https://mcp.mastermind-x.com",
        subject_digest=subject, client_ref="b" * 64, scopes=scopes,
        issued_at=NOW - 60, expires_at=NOW + 3600, jti_digest=None,
    )


def policy(who=None):
    who = principal() if who is None else who
    return TrustedCanaryPolicy(
        workspace_id="T0BRD2AQXQV", channel_id=CHANNEL,
        relay_bot_user_id="U0BT71H4FQE", owner_slack_user_id="U0BRET6191C",
        principal_digest=owner_key(who), not_before_ts="1791766700.000001",
        current=True,
    )


class FakeReplyOwner:
    def __init__(self):
        self.calls = []

    async def can_discover(self, who):
        self.calls.append("discover")
        return True

    async def subscribe(self, who, request):
        self.calls.append("subscribe")
        raise AssertionError("canary must not reach reply subscriber")

    async def unsubscribe(self, who, request):
        self.calls.append("unsubscribe")
        raise AssertionError("canary must not reach reply subscriber")


class FakeCanaryOwner:
    """Not persistent, not an authorization grant, never a production owner."""

    def __init__(self, enrolled=None):
        self.enrolled = policy() if enrolled is None else enrolled
        self.calls = []
        self.fail = None

    async def policy_for(self, who):
        self.calls.append(("policy", who.subject_digest))
        if self.fail == "policy":
            raise RuntimeError("policy not available")
        return self.enrolled

    async def subscribe(self, who, request):
        self.calls.append(("subscribe", who.subject_digest, request))
        if self.fail == "subscribe":
            raise RuntimeError("lost response after commit")
        return CanarySubscriptionReceipt(
            subscription_id="sub_chrisdot001", expires_at=NOW + 1200,
            callback_verified=True, persisted=True, owner_access_current=True,
        )

    async def unsubscribe(self, who, request):
        self.calls.append(("unsubscribe", who.subject_digest, request))
        if self.fail == "unsubscribe":
            raise RuntimeError("lost unsubscribe response")
        return CanaryUnsubscribeReceipt(stopped=True, committed=True)


def request(method, params=None):
    return {"jsonrpc": "2.0", "id": 12, "method": method, "params": {} if params is None else params}


def invoke(method, params=None, *, canary=None, reply=None, who=None):
    canary = FakeCanaryOwner() if canary is None else canary
    reply = FakeReplyOwner() if reply is None else reply
    who = principal() if who is None else who
    return asyncio.run(WebReplyEventRpc(
        reply, clock=lambda: NOW, canary_owner=canary,
    ).handle(request(method, params), who))


def subscribe_params():
    return {
        "name": EVENT_NAME,
        "arguments": {"channel_id": CHANNEL},
        "delivery": {"mode": "webhook", "url": URL, "secret": SECRET},
        "cursor": None,
    }


def test_default_off_preserves_original_one_event_catalog_and_refuses_canary():
    owner = FakeReplyOwner()
    rpc = WebReplyEventRpc(owner, clock=lambda: NOW)
    catalog = asyncio.run(rpc.handle(request("events/list"), principal()))
    assert [x["name"] for x in catalog["result"]["events"]] == ["session.reply_committed"]
    denied = asyncio.run(rpc.handle(request("events/subscribe", subscribe_params()), principal()))
    assert denied["error"]["code"] == -32602
    assert owner.calls == ["discover"]


def test_scoped_discovery_shows_two_distinct_events_without_mutating_reply_catalog():
    canary = FakeCanaryOwner()
    catalog = invoke("events/list", {}, canary=canary)
    assert [x["name"] for x in catalog["result"]["events"]] == [
        "session.reply_committed", EVENT_NAME,
    ]
    event = catalog["result"]["events"][1]
    assert event["inputSchema"]["properties"]["channel_id"]["const"] == CHANNEL
    assert event["delivery"] == ["webhook"]
    assert event["payloadSchema"]["additionalProperties"] is False


@pytest.mark.parametrize("scopes", [
    (), ("unrelated.scope",),
])
def test_missing_read_scope_cannot_discover_or_subscribe(scopes):
    p = principal(scopes=scopes)
    canary = FakeCanaryOwner()
    catalog = invoke("events/list", {}, canary=canary, who=p)
    assert catalog["error"]["code"] == -32001
    sub = invoke("events/subscribe", subscribe_params(), canary=canary, who=p)
    assert sub["error"]["code"] == -32001
    assert not any(item[0] == "subscribe" for item in canary.calls)


def test_valid_owner_subscription_has_verified_receipt_and_no_secret_exposure():
    canary = FakeCanaryOwner()
    result = invoke("events/subscribe", subscribe_params(), canary=canary)
    assert result["result"]["id"] == "sub_chrisdot001"
    assert result["result"]["cursor"] is None
    assert result["result"]["truncated"] is False
    assert any(x[0] == "subscribe" for x in canary.calls)
    sub = next(x[2] for x in canary.calls if x[0] == "subscribe")
    assert sub.channel_id == CHANNEL
    assert sub.callback_url == URL and sub.signing_secret == SECRET
    assert SECRET not in repr(sub) and SECRET not in json.dumps(result)


def test_valid_owner_unsubscribe_has_empty_response_and_no_secret():
    params = subscribe_params()
    params.pop("cursor")
    params["delivery"] = {"mode": "webhook", "url": URL}
    canary = FakeCanaryOwner()
    result = invoke("events/unsubscribe", params, canary=canary)
    assert result["result"] == {}
    unsub = next(x[2] for x in canary.calls if x[0] == "unsubscribe")
    assert unsub.callback_url == URL
    assert "signing_secret" not in repr(unsub)


@pytest.mark.parametrize("change", [
    {"name": "other.event"},
    {"arguments": {"channel_id": "C0BRFC9JXK8"}},
    {"arguments": {"channel_id": CHANNEL, "principal": "admin"}},
    {"delivery": {"mode": "webhook", "url": "https://127.0.0.1", "secret": SECRET}},
    {"delivery": {"mode": "webhook", "url": URL, "secret": "nope"}},
    {"cursor": "stale"},
    {"ttlMs": 0}, {"ttlMs": True},
    {"unexpected": "override"},
])
def test_malformed_subscriptions_refuse_before_owner_write(change):
    canary = FakeCanaryOwner()
    result = invoke("events/subscribe", {**subscribe_params(), **change}, canary=canary)
    assert "error" in result
    assert not any(x[0] == "subscribe" for x in canary.calls)


@pytest.mark.parametrize("invalid_policy", [
    lambda p: dataclasses.replace(p, current=False),
    lambda p: dataclasses.replace(p, principal_digest="f" * 64),
    lambda p: dataclasses.replace(p, channel_id="C0BRFC9JXK8"),
])
def test_mismatched_or_revoked_policy_cannot_grant_subscription(invalid_policy):
    canary = FakeCanaryOwner(invalid_policy(policy()))
    result = invoke("events/subscribe", subscribe_params(), canary=canary)
    assert "error" in result
    assert not any(x[0] == "subscribe" for x in canary.calls)


@pytest.mark.parametrize("failure", ["policy", "subscribe", "unsubscribe"])
def test_ambiguous_owner_failure_never_becomes_success(failure):
    canary = FakeCanaryOwner()
    canary.fail = failure
    params = subscribe_params()
    if failure == "unsubscribe":
        params.pop("cursor")
        params["delivery"] = {"mode": "webhook", "url": URL}
    result = invoke("events/unsubscribe" if failure == "unsubscribe" else "events/subscribe",
                    params, canary=canary)
    assert result["error"]["code"] == -32010
    assert SECRET not in json.dumps(result)


def test_foreign_principal_cannot_use_another_account_canary_policy():
    other = principal(subject="d" * 64)
    canary = FakeCanaryOwner()
    catalog = invoke("events/list", {}, canary=canary, who=other)
    assert [x["name"] for x in catalog["result"]["events"]] == ["session.reply_committed"]
    result = invoke("events/subscribe", subscribe_params(), canary=canary, who=other)
    assert result["error"]["code"] == -32001
    assert not any(x[0] == "subscribe" for x in canary.calls)


def test_bad_constructor_cannot_make_spoof_owner():
    with pytest.raises(TypeError):
        WebReplyEventRpc(FakeReplyOwner(), clock=lambda: NOW, canary_owner=object())


def test_subscription_cannot_outlive_original_account_token_even_with_long_ttl():
    class LongGrant(FakeCanaryOwner):
        async def subscribe(self, who, request):
            result = await super().subscribe(who, request)
            return dataclasses.replace(result, expires_at=NOW + 7200)
    params = {**subscribe_params(), "ttlMs": 24 * 60 * 60 * 1000}
    canary = LongGrant()
    result = invoke("events/subscribe", params, canary=canary)
    assert result["error"]["code"] == -32010
    assert any(x[0] == "subscribe" for x in canary.calls)
    assert SECRET not in json.dumps(result)


def test_policy_change_after_owner_effect_cannot_be_reported_as_success():
    class RevokedDuringSubscription(FakeCanaryOwner):
        async def subscribe(self, who, request):
            result = await super().subscribe(who, request)
            self.enrolled = dataclasses.replace(self.enrolled, current=False)
            return result
    canary = RevokedDuringSubscription()
    result = invoke("events/subscribe", subscribe_params(), canary=canary)
    assert result["error"]["code"] == -32010
    assert SECRET not in json.dumps(result)
