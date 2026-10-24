"""Pure opt-in MCP Events RPC bridge; storage/auth/callback delivery stay with incumbent owners.

No socket, provider, callback or Executive process is invoked by these tests.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from datetime import datetime, timezone

import pytest

from control_plane.principal_projection import neutral_principal_projection

SCHEMA = "integrations.session_bridge.web_reply_event_rpc"
SECRET = "whsec_" + base64.b64encode(b"s" * 32).decode("ascii")
EVENT = "session.reply_committed"
VERSION = "2026-07-28"
NOW = 1_791_766_800
URL = "https://receiver.example.com/mcp-events/callback_123"
BASE_PARAMS = {
    "name": EVENT,
    "arguments": {"request_ref": "request-001"},
    "delivery": {"mode": "webhook", "url": URL, "secret": SECRET},
    "cursor": None,
}


def api():
    import importlib
    return importlib.import_module(SCHEMA)


def principal(*, subject="a" * 64, scopes=("mastermind.executive.read",), now=NOW):
    issuer = "https://auth.example.com"
    return neutral_principal_projection(
        policy_id="mmx-event-account",
        issuer=issuer, issuer_digest=hashlib.sha256(issuer.encode()).hexdigest(),
        resource="https://mcp.mastermind-x.com",
        subject_digest=subject, client_ref="b" * 64, scopes=scopes,
        issued_at=now-60, expires_at=now+3600, jti_digest=None,
    )


class FakeOriginalOwner:
    """Deliberately fake; this is not durable service/production capability proof."""
    def __init__(self, *, store=None):
        self.store = store if store is not None else {}
        self.calls = []
        self.fail = None
        self.allowed = True

    async def can_discover(self, identity):
        self.calls.append(("discover",identity.subject_digest))
        return self.allowed

    async def subscribe(self, identity, requested):
        self.calls.append(("subscribe", identity.subject_digest, requested))
        if self.fail: raise self.fail
        if requested.request_ref != "request-001": raise ValueError("unavailable")
        key = (identity.subject_digest,requested.request_ref,requested.callback_url)
        same = self.store.get(key)
        result = api().EventSubscriptionReceipt(
            subscription_id=(same.subscription_id if same else "sub_original001"),
            expires_at=NOW+1800,
            callback_verified=True,
            persisted=True,
            original_request_current=True,
        )
        self.store[key] = result
        return result

    async def unsubscribe(self,identity,requested):
        self.calls.append(("unsubscribe",identity.subject_digest,requested))
        if self.fail: raise self.fail
        key = (identity.subject_digest,requested.request_ref,requested.callback_url)
        self.store.pop(key,None)
        return api().EventUnsubscribeReceipt(stopped=True,committed=True)


def req(method, params=None, request_id=2):
    result = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None: result["params"] = params
    return result


def call(owner,method,params=None,who=None):
    return asyncio.run(api().WebReplyEventRpc(owner,clock=lambda:NOW).handle(
        req(method,params),principal() if who is None else who,
    ))


def test_discovery_is_bounded_to_authenticated_principal_and_one_event():
    owner=FakeOriginalOwner()
    result=call(owner,"events/list",{})
    assert result["id"] == 2
    definition=result["result"]["events"]
    assert len(definition)==1 and definition[0]["name"]==EVENT
    assert definition[0]["delivery"]==["webhook"]
    assert definition[0]["inputSchema"]["required"]==["request_ref"]
    assert "nextCursor" not in result["result"]
    owner.allowed=False
    assert call(owner,"events/list",{})["result"]=={"events":[]}


def test_subscription_writes_once_through_original_owner_and_returns_exact_receipt():
    owner=FakeOriginalOwner()
    result=call(owner,"events/subscribe",BASE_PARAMS)
    assert result["result"] == {"id":"sub_original001","refreshBefore":"2026-10-12T01:30:00Z","cursor":None,"truncated":False}
    assert result["result"]["cursor"] is None
    assert result["result"]["truncated"] is False
    assert len(owner.store)==1
    request=owner.calls[-1][2]
    assert request.callback_url==URL
    assert request.signing_secret==SECRET
    assert request.request_ref=="request-001"
    assert "whsec_" not in repr(request)
    assert "whsec_" not in json.dumps(result)


def test_duplicate_and_refresh_are_handled_only_by_the_same_existing_owner():
    store={}
    one=FakeOriginalOwner(store=store)
    a=call(one,"events/subscribe",BASE_PARAMS)
    b=call(FakeOriginalOwner(store=store),"events/subscribe",{**BASE_PARAMS,"ttlMs":1800000})
    assert a["result"]["id"]==b["result"]["id"]
    assert len(store)==1


def test_unsubscribe_is_idempotent_and_never_accepts_arbitrary_filter_or_secret():
    owner=FakeOriginalOwner()
    call(owner,"events/subscribe",BASE_PARAMS)
    unsub={k:v for k,v in BASE_PARAMS.items() if k not in ("cursor",)}
    unsub["delivery"]={"mode":"webhook","url":URL}
    one=call(owner,"events/unsubscribe",unsub)
    two=call(owner,"events/unsubscribe",unsub)
    assert one["result"]=={} and two["result"]=={} and not owner.store
    assert "signing_secret" not in repr(owner.calls[-1][2])


@pytest.mark.parametrize("url", [
    "http://receiver.example.com/hook", "//receiver.example.com/hook",
    "https://127.0.0.1/hook","https://10.0.0.1/hook",
    "https://[::1]/hook","https://localhost/hook",
    "https://internal.local/hook","https://receiver.example.com@127.0.0.1/hook",
    "https://user:pass@receiver.example.com/hook",
    "https://receiver.example.com/hook#fragment", "https://receiver.example.com:99999/x",
    "https://-bad.example.com/x", "https://receiver.example.com/%0Aevil\n",
])
def test_unsafe_destinations_are_refused_before_owner_execution(url):
    owner=FakeOriginalOwner()
    result=call(owner,"events/subscribe",{**BASE_PARAMS,"delivery":{**BASE_PARAMS["delivery"],"url":url}})
    assert result["error"]["code"]==-32602
    assert not any(x[0]=="subscribe" for x in owner.calls)
    assert "whsec_" not in json.dumps(result)


@pytest.mark.parametrize("param", [
    {"name": "other.event"},
    {"arguments":{"request_ref":"bad ref"}},
    {"arguments":{"request_ref":"request-001","other":True}},
    {"delivery":{"mode":"poll","url":URL,"secret":SECRET}},
    {"delivery":{"mode":"webhook","url":URL}},
    {"delivery":{"mode":"webhook","url":URL,"secret":"bad"}},
    {"cursor":"cursor-1"},
    {"ttlMs":0},{"ttlMs":True},{"ttlMs":604800001},
    {"malicious":"actor-override"},
])
def test_malformed_or_unauthorized_subscription_cannot_reach_owner(param):
    owner=FakeOriginalOwner()
    result=call(owner,"events/subscribe",{**BASE_PARAMS,**param})
    assert result["error"]["code"]==-32602
    assert not any(x[0]=="subscribe" for x in owner.calls)


def test_authorization_is_current_and_unspoofable_by_request_body():
    owner=FakeOriginalOwner()
    expired=principal(now=NOW-3700)
    assert call(owner,"events/subscribe",BASE_PARAMS,who=expired)["error"]["code"]==-32001
    assert call(owner,"events/list",{},who=principal(scopes=()))["error"]["code"]==-32001
    assert call(owner,"events/subscribe",BASE_PARAMS,who={"scopes":["mastermind.executive.read"]})["error"]["code"]==-32001
    assert not owner.calls


@pytest.mark.parametrize("bad", [
    {"jsonrpc":"1.0","id":2,"method":"events/subscribe","params":BASE_PARAMS},
    {"jsonrpc":"2.0","id":True,"method":"events/subscribe","params":BASE_PARAMS},
    {"jsonrpc":"2.0","id":2,"method":"events/subscribe","params":BASE_PARAMS,"principal":"fake"},
    {"jsonrpc":"2.0","id":2,"method":"events/subscribe","params":BASE_PARAMS,"result":{}},
    {"jsonrpc":"2.0","id":2,"method":"unknown","params":BASE_PARAMS},
])
def test_bad_jsonrpc_envelope_and_foreign_method_never_create_subscription(bad):
    owner=FakeOriginalOwner()
    result=asyncio.run(api().WebReplyEventRpc(owner,clock=lambda:NOW).handle(bad,principal()))
    assert "error" in result
    assert not owner.calls


def test_owner_refusal_and_uncertainty_never_return_success_or_retry():
    owner=FakeOriginalOwner()
    owner.fail=RuntimeError("ACCESS_TOKEN=secret DO NOT LEAK")
    result=call(owner,"events/subscribe",BASE_PARAMS)
    assert result["error"]["code"]==-32010
    assert "secret" not in json.dumps(result)
    assert len([x for x in owner.calls if x[0]=="subscribe"])==1


@pytest.mark.parametrize("receipt_changes",[
    {"callback_verified":False},{"persisted":False},
    {"original_request_current":False},
    {"expires_at":NOW-1},{"expires_at":NOW+60*60*24*30},
    {"subscription_id":"forged\nheader"},
])
def test_unverified_or_invalid_owner_receipt_cannot_be_promoted(receipt_changes):
    class BadOwner(FakeOriginalOwner):
        async def subscribe(self, identity, request):
            self.calls.append(("subscribe",identity.subject_digest,request))
            return api().EventSubscriptionReceipt(
                subscription_id=receipt_changes.get("subscription_id","sub_original001"),
                expires_at=receipt_changes.get("expires_at",NOW+1800),
                callback_verified=receipt_changes.get("callback_verified",True),
                persisted=receipt_changes.get("persisted",True),
                original_request_current=receipt_changes.get("original_request_current",True),
            )
    result=call(BadOwner(),"events/subscribe",BASE_PARAMS)
    assert "error" in result


def test_opt_in_rpc_has_no_server_no_transport_no_persistent_state():
    instance=api().WebReplyEventRpc(FakeOriginalOwner(),clock=lambda:NOW)
    assert not hasattr(instance,"send_http")
    assert not hasattr(instance,"create_job")
    assert not hasattr(instance,"database")


def test_notification_without_id_or_with_null_id_never_modifies_subscription():
    owner = FakeOriginalOwner()
    for invalid in (
        {"jsonrpc":"2.0","method":"events/subscribe","params":BASE_PARAMS},
        {"jsonrpc":"2.0","id":None,"method":"events/subscribe","params":BASE_PARAMS},
    ):
        result = asyncio.run(api().WebReplyEventRpc(owner, clock=lambda: NOW).handle(
            invalid, principal(),
        ))
        assert result["error"]["code"] == -32600
        assert result["id"] is None
    assert not owner.calls


def test_authorization_expiry_during_owner_call_does_not_greenwash_effect():
    clock = [NOW]
    class ClockAdvancingOwner(FakeOriginalOwner):
        async def subscribe(self, who, requested):
            result = await super().subscribe(who, requested)
            clock[0] = NOW + 4000
            return result
    owner = ClockAdvancingOwner()
    result = asyncio.run(api().WebReplyEventRpc(owner, clock=lambda: clock[0]).handle(
        req("events/subscribe", BASE_PARAMS), principal(),
    ))
    assert result["error"]["code"] == -32010
    assert len(owner.store) == 1  # old operation may have committed: NEVER auto-retry


def test_callback_verification_refusal_has_closed_category_and_no_secret():
    owner = FakeOriginalOwner()
    owner.fail = api().CallbackVerificationError("challenge_failed")
    result = call(owner, "events/subscribe", BASE_PARAMS)
    assert result["error"] == {
        "code": -32015, "message": "callback endpoint refused",
        "data": {"reason": "challenge_failed"},
    }
    assert "whsec_" not in json.dumps(result)
    assert len([x for x in owner.calls if x[0] == "subscribe"]) == 1


def test_modern_protocol_metadata_accepts_exact_version_and_rejects_other():
    owner = FakeOriginalOwner()
    params = {"_meta": {"io.modelcontextprotocol/protocolVersion": VERSION}}
    assert call(owner,"events/list",params)["result"]["events"]
    assert call(owner,"events/list",{"_meta":{
        "io.modelcontextprotocol/protocolVersion":"2025-06-18",
    }})["error"]["code"] == -32602


def test_unsubscribe_requires_committed_owner_write_or_returns_unknown():
    class UncommittedOwner(FakeOriginalOwner):
        async def unsubscribe(self,who,requested):
            self.calls.append(("unsubscribe",who.subject_digest,requested))
            return api().EventUnsubscribeReceipt(stopped=True, committed=False)
    result = call(UncommittedOwner(), "events/unsubscribe", {
        "name": EVENT,
        "arguments":{"request_ref":"request-001"},
        "delivery":{"mode":"webhook","url":URL},
    })
    assert result["error"]["code"] == -32010


@pytest.mark.parametrize("method", ["events/list", "events/subscribe", "events/unsubscribe"])
def test_owner_value_error_after_dispatch_is_never_misreported_as_preflight(method):
    owner = FakeOriginalOwner()
    owner.fail = ValueError("OWNER MAY HAVE COMMITTED")
    if method == "events/list":
        class DiscoverFails(FakeOriginalOwner):
            async def can_discover(self, identity):
                self.calls.append(("discover",identity.subject_digest))
                raise ValueError("OWNER MAY HAVE COMMITTED")
        owner = DiscoverFails()
        params={}
    elif method == "events/subscribe":
        params=BASE_PARAMS
    else:
        params={"name":EVENT,"arguments":{"request_ref":"request-001"},
                "delivery":{"mode":"webhook","url":URL}}
    result=call(owner,method,params)
    assert result["error"]["code"]==-32010
    assert "OWNER MAY HAVE" not in json.dumps(result)
    assert len(owner.calls)==1
