"""Max funding proof and closed permission diagnostics; no provider calls."""
from __future__ import annotations
import hashlib
import json
import pytest
from control_plane.experiential_plan_policy import (
    FREE_CHAT_MODELS, FREE_NATIVE_MODELS, require_included_funding, PlanRequestRefused,
)
from ops.native_fabric.experiential53 import experiential_transport as transport


def observed():
    return {
        "schema":"mastermind.experiential_included_funding/v1",
        "source":"authenticated_provider_account",
        "organization_sha256":hashlib.sha256(b"fixture-org").hexdigest(),
        "plan_tier":"max","plan_active":True,"daily_credits":7000,
        "continue_on_credits":False,"provider_enforces_included_stop":True,
        "paid_uncensored_remains_available":True,"observed_at_unix":1000.0,
        "included_models":list(FREE_CHAT_MODELS)+list(FREE_NATIVE_MODELS),
    }


def test_complete_observation_does_not_invent_remaining_capacity():
    value=observed()
    out=require_included_funding(value,organization_sha256=value["organization_sha256"],now=1001)
    assert out=={"funding_contract":"max_included","paid_overflow":False,"observed_at_unix":1000.0}


@pytest.mark.parametrize("field,value", [
    ("source","chairman_declared_plan"),("plan_tier","pro"),("plan_active",1),
    ("daily_credits",7000.0),("continue_on_credits",True),("continue_on_credits",0),
    ("provider_enforces_included_stop",False),("paid_uncensored_remains_available",False),
    ("organization_sha256","0"*64),("included_models",list(FREE_CHAT_MODELS)),
    ("observed_at_unix",True),("observed_at_unix",float("nan")),
    ("observed_at_unix",940),("observed_at_unix",1002),
])
def test_missing_stale_or_paid_overflow_evidence_cannot_admit(field,value):
    proof=observed();org=proof["organization_sha256"];proof[field]=value
    with pytest.raises(PlanRequestRefused):
        require_included_funding(proof,organization_sha256=org,now=1001)


def test_absent_funding_proof_cannot_be_replaced_by_wallet():
    with pytest.raises(PlanRequestRefused,match="INCLUDED_FUNDING_UNVERIFIED"):
        require_included_funding(None,organization_sha256="0"*64)


@pytest.mark.parametrize("status,kind,reason", [
    (401,"authentication","GATEWAY_AUTH_REFUSED"),
    (403,"permission","GATEWAY_PERMISSION_REFUSED"),
    (429,"rate_limit","GATEWAY_RATE_LIMITED"),
])
def test_http_refusals_keep_closed_error_metadata(status,kind,reason):
    body=json.dumps({"error":{"code":"model_not_granted","type":"permission_error",
                             "param":"model","message":"SECRET-PROMPT-OR-KEY"}}).encode()
    exc=transport._classify_http_error(status,"application/json; charset=utf-8",
        provider_request_id="fixture-request",error_body=body)
    assert exc.reason==reason
    assert "SECRET" not in str(exc)
    metadata=transport.transport_refusal_metadata(reason+": "+str(exc))
    assert metadata=={"kind":kind,"transport_reason":reason,"http_status":status,
        "provider_error":{"code":"model_not_granted","type":"permission_error","param":"model"},
        "provider_request_id":"fixture-request"}


@pytest.mark.parametrize("body,content_type", [
    (b'{"error":{"code":"xpl_secret","type":"SECRET","param":"SECRET"}}',"application/json"),
    (b'{"error":{"code":"model_not_granted","code":"invalid_key"}}',"application/json"),
    (b'{"error":{"code":"model_not_granted"}}',"text/html"),
    (b"x"*(transport.MAX_ERROR_BODY_BYTES+1),"application/json"),
    (b'{"error":{"code":["model_not_granted"]}}',"application/json"),
])
def test_error_bodies_cannot_inject_unknown_or_unbounded_metadata(body,content_type):
    exc=transport._classify_http_error(403,content_type,error_body=body)
    assert transport.transport_refusal_metadata(str(exc))=={
        "kind":"permission","transport_reason":"GATEWAY_PERMISSION_REFUSED","http_status":403}
