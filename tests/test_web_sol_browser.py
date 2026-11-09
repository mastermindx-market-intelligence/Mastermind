"""Browser-family behavior on the incumbent protocol, native host and client."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import secrets
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from integrations.chairman_surfaces import web_sol_browser_protocol as protocol
from integrations.chairman_surfaces import web_sol_client as client
from integrations.chairman_surfaces import web_sol_native_host as native
from integrations.chairman_surfaces import web_sol_protocol as legacy
from integrations.hermes_harness import browser_bridge as bridge
from test_web_sol_deployment import binding

ROOT = Path(__file__).resolve().parents[1]


def request(action="click", **changes):
    now = datetime.now(timezone.utc)
    value = dict(schema=protocol.REQUEST_SCHEMA, adapter_instance_id="a"*64,
        session_id="b"*64, operation_key="browser-contract", nonce=secrets.token_hex(24),
        transport_boot_nonce="connection-generation-001", action=action,
        tab_id=17, url_fingerprint="c"*64, snapshot_id="snapshot-observation-001",
        ref="e1", params={}, issued_at=now.isoformat().replace("+00:00", "Z"),
        expires_at=(now+timedelta(seconds=30)).isoformat().replace("+00:00", "Z"))
    if action not in protocol.TAB_ACTIONS:
        value.update(tab_id=None, url_fingerprint=None, snapshot_id=None, ref=None)
    elif action == "snapshot":
        value.update(snapshot_id=None, ref=None)
    elif action not in protocol.PAGE_ACTIONS:
        value.update(ref=None)
    value.update(changes)
    return value


@pytest.mark.parametrize("action", sorted(protocol.ACTIONS))
def test_closed_actions_round_trip(action):
    params = {"open":{"url":"https://example.test/"}, "navigate":{"url":"http://localhost:8080/page"},
        "fill":{"text":"Hello\nworld"}, "select":{"value":"one"}, "press":{"key":"Enter"},
        "scroll":{"x":0,"y":700}}.get(action,{})
    original=request(action,params=params)
    accepted=protocol.validate_window(original)
    assert accepted == original and accepted is not original
    receipt=protocol.receipt(accepted,status="OK")
    assert protocol.validate_receipt(receipt)==receipt


@pytest.mark.parametrize("changes", [
    {"action":[]}, {"session_id":"invented"}, {"adapter_instance_id":"b"*63},
    {"tab_id":True}, {"tab_id":-1}, {"snapshot_id":None}, {"ref":"x"*33},
    {"transport_boot_nonce":None}, {"params":{"selector":"#submit"}},
    {"params":{"script":"alert(1)"}}, {"issued_at":"2026-99-99T00:00:00Z"},
    {"expires_at":"2020-01-01T00:00:00Z"}, {"grant":"invented"},
])
def test_invalid_stale_or_extended_messages_fail_closed(changes):
    with pytest.raises(legacy.WebSolProtocolError):protocol.validate_window(dict(request(),**changes))


@pytest.mark.parametrize("url", ["chrome://settings", "file:///tmp/private", "javascript:alert(1)",
    "https://user:secret@example.test/", "https://example.test:0/", "https://example.test/ a"])
def test_navigation_has_no_privileged_or_credential_urls(url):
    with pytest.raises(legacy.WebSolProtocolError):protocol.validate_request(request("navigate",params={"url":url}))


def test_bounded_receipts_reject_nonfinite_mutable_and_wrong_effect_values():
    good=protocol.receipt(request(),status="OK")
    for changes in ({"effect":{}},{"data":{"x":float("nan")}}, {"data":{"secret":"x"*70000}}):
        with pytest.raises(legacy.WebSolProtocolError):protocol.validate_receipt(dict(good,**changes))


def test_native_forwards_once_and_rejects_replay_without_writing():
    original=request(); writes=[]
    expected=protocol.receipt(original,status="ACTION_DISPATCHED",effect="APPLIED")
    first=native.forward_request(original,write_chrome=writes.append,read_chrome=lambda _:expected,timeout_seconds=1)
    second=native.forward_request(original,write_chrome=writes.append,read_chrome=lambda _:pytest.fail("replay read"),timeout_seconds=1)
    assert first==expected and len(writes)==1
    assert second["status"]=="NONCE_REUSED" and second["effect"]=="NOT_APPLIED"


@pytest.mark.parametrize("field", protocol.IDENTITY_FIELDS)
def test_mismatched_receipt_after_mutation_is_uncertain(field):
    original=request(); reply=protocol.receipt(original,status="ACTION_DISPATCHED",effect="APPLIED")
    reply[field]="wrong"
    with pytest.raises(native.NativeHostError,match="browser_effect_unknown"):
        native.forward_request(original,write_chrome=lambda _:None,read_chrome=lambda _:reply,timeout_seconds=1)


@pytest.mark.parametrize("action,code", [("click","browser_effect_unknown"),("snapshot","browser_unavailable")])
def test_lost_native_reply_is_classified_without_retry(action,code):
    writes=[]
    with pytest.raises(native.NativeHostError,match=code):
        native.forward_request(request(action),write_chrome=writes.append,read_chrome=lambda _:None,timeout_seconds=1)
    assert len(writes)==1


def test_hermes_identity_is_native_profile_and_session_not_model_supplied(tmp_path,monkeypatch):
    rows={"schema":"mastermind.surface_bindings.v1","bindings":[binding()]}
    monkeypatch.setattr(bridge.surface_bindings,"load_bindings",lambda _: (copy.deepcopy(rows),[]))
    seen=[]
    def exchange(browser,**kwargs):
        seen.append((browser,kwargs)); return {"status":"OK"}
    inventory=bridge.execute({"action":"browsers"},native_session_id="session-one",profile_ref="/profile/a",bindings_path=tmp_path/"bindings",exchange=exchange)
    browser=inventory["browsers"][0]["browser_id"]
    assert seen==[] and inventory["browsers"][0]["installed"] is None
    for session,profile in (("session-one","/profile/a"),("session-two","/profile/a"),("session-one","/profile/b")):
        result=bridge.execute({"action":"status","browser_id":browser},native_session_id=session,profile_ref=profile,bindings_path=tmp_path/"bindings",exchange=exchange)
        assert result["state"]=="RECEIPT"
        assert seen[-1][1]["session_id"]==hashlib.sha256((profile+"\0"+session).encode()).hexdigest()
    assert len({row[1]["session_id"] for row in seen})==3
    rejected=bridge.execute({"action":"status","browser_id":browser,"session_id":"forged"},native_session_id="session-one",profile_ref="/profile/a",bindings_path=tmp_path/"bindings",exchange=exchange)
    assert rejected["state"]=="REFUSED" and len(seen)==3


def test_consumer_keeps_uncertain_operation_identity(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,"inventory",lambda _: [{"browser_id":"a"*64}])
    calls=[]
    def exchange(*args,**kwargs):
        calls.append(kwargs);raise client.WebSolExtensionError("browser_effect_unknown")
    result=bridge.execute({"action":"open","browser_id":"a"*64,"connection_id":"connection-generation-001","url":"https://example.test/"},
        native_session_id="actual-session",profile_ref="/profile",bindings_path=tmp_path/"bindings",exchange=exchange,
        operation_key="hermes-browser-"+"1"*32,nonce="2"*48)
    assert len(calls)==1 and result["state"]=="EFFECT_UNKNOWN" and result["retry_allowed"] is False
    assert result["request_ref"]["nonce"]=="2"*48


def test_native_tool_schema_matches_consumer():
    assert json.loads((ROOT/"integrations/hermes_harness/browser_tool_schema.json").read_text())==bridge.TOOL_SCHEMA
    assert "session_id" not in bridge.TOOL_SCHEMA["parameters"]["properties"]


def test_client_stamps_discovered_connection_and_refuses_changed_generation_before_write(monkeypatch):
    writes=[]
    connection=SimpleNamespace(settimeout=lambda _:None,connect=lambda _:None,
        makefile=lambda *args,**kwargs:io.BytesIO(),close=lambda:None)
    monkeypatch.setattr(client,"_private_socket",lambda _:None)
    monkeypatch.setattr(client.socket,"socket",lambda *args:connection)
    monkeypatch.setattr(client,"_complete_transport_handshake",lambda *args,**kwargs:{"boot_nonce":"current-connection-generation"})
    monkeypatch.setattr(native,"write_frame",lambda stream,value,**kwargs:writes.append(copy.deepcopy(value)))
    monkeypatch.setattr(native,"read_frame",lambda *args,**kwargs:protocol.receipt(writes[-1],status="OK"))
    result=client.browser_via_extension("a"*64,session_id="b"*64,operation_key="status-operation",action="status")
    assert result["transport_boot_nonce"]=="current-connection-generation" and len(writes)==1
    with pytest.raises(client.WebSolExtensionError,match="browser_connection_changed"):
        client.browser_via_extension("a"*64,session_id="b"*64,operation_key="tabs-operation",action="tabs",
                                     connection_id="previous-connection-generation")
    assert len(writes)==1


def test_client_lost_action_reply_keeps_unknown_without_second_write(monkeypatch):
    writes=[]
    connection=SimpleNamespace(settimeout=lambda _:None,connect=lambda _:None,
        makefile=lambda *args,**kwargs:io.BytesIO(),close=lambda:None)
    monkeypatch.setattr(client,"_private_socket",lambda _:None)
    monkeypatch.setattr(client.socket,"socket",lambda *args:connection)
    monkeypatch.setattr(client,"_complete_transport_handshake",lambda *args,**kwargs:{"boot_nonce":"current-connection-generation"})
    monkeypatch.setattr(native,"write_frame",lambda stream,value,**kwargs:writes.append(copy.deepcopy(value)))
    def lost(*args,**kwargs):raise native.NativeHostError("read_timeout")
    monkeypatch.setattr(native,"read_frame",lost)
    with pytest.raises(client.WebSolExtensionError,match="browser_effect_unknown"):
        client.browser_via_extension("a"*64,session_id="b"*64,operation_key="open-operation",action="open",
            connection_id="current-connection-generation",params={"url":"https://example.test/"})
    assert len(writes)==1


def test_browser_controller_behavior_in_node():
    node=shutil.which("node")
    if not node:pytest.skip("Node unavailable")
    run=subprocess.run([node,str(ROOT/"tests/browser_control_contract.cjs")],cwd=ROOT,capture_output=True,text=True,timeout=15)
    assert run.returncode==0,run.stdout+run.stderr
    assert "browser controller contract passed" in run.stdout
