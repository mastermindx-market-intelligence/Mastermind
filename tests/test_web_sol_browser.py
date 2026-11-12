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
    # Snapshot-free reads (0b5edb927) take no snapshot id; diagnostics alone
    # also accepts the last observation's id, so keep its string to cover that.
    if action in protocol.NO_SNAPSHOT and action != "diagnostics":
        value.update(snapshot_id=None)
    value.update(changes)
    return value


@pytest.mark.parametrize("action", sorted(protocol.ACTIONS))
def test_closed_actions_round_trip(action):
    params = {"open":{"url":"https://example.test/"}, "navigate":{"url":"http://localhost:8080/page"},
        "fill":{"text":"Hello\nworld"}, "select":{"value":"one"}, "press":{"key":"Enter"},
        "scroll":{"x":0,"y":700}, "read":{"offset":0},
        # Advanced actions carry their payload in params; each needs its own
        # minimal valid shape to round-trip validate_window.
        "cdp":{"method":"Page.enable"}, "evaluate":{"expression":"1+1"},
        "interact":{"ref":"n"+"a"*24,"kind":"click"}, "locate":{"locator":{"css":"div"}},
        "wait":{"locator":{"css":"div"}},
        "download":{"url":"https://example.test/file.bin"},
        "response_body":{"request_id":"request-one"}, "result":{"result_id":"result-one"},
        "route":{"rules":[{"url_pattern":"https://example.test/","action":"continue"}]},
        "upload":{"ref":"n"+"a"*24,"files":["/tmp/upload.txt"]}}.get(action,{})
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


def test_read_pages_one_elements_text_by_ref():
    # read is a snapshot-ref read: it needs the observation's element ref and
    # takes exactly one integer offset (character position for paging).
    accepted = protocol.validate_window(request("read", params={"offset": 12345}))
    assert accepted["params"] == {"offset": 12345}
    assert accepted["ref"] == "e1"
    for bad in ({"offset": -1}, {"offset": 2000001}, {"offset": "0"}, {"offset": 0, "extra": 1}, {}):
        with pytest.raises(legacy.WebSolProtocolError):
            protocol.validate_window(request("read", params=bad))


def test_fill_cap_counts_utf16_units_not_code_points():
    # Every JavaScript layer of the pipeline caps fill length in UTF-16 code
    # units; Python's len() counts code points. Astral characters are two
    # units each, so 15,001 of them passed the protocol's 30,000 cap while the
    # page refused the dispatch. The protocol gate must count the same units.
    with pytest.raises(legacy.WebSolProtocolError):
        protocol.validate_window(request("fill", params={"text": "\U0001D54F" * 15001}))
    accepted = protocol.validate_window(request("fill", params={"text": "\U0001D54F" * 15000}))
    assert accepted["params"]["text"] == "\U0001D54F" * 15000
    # Lone surrogates are one UTF-16 unit each and must not crash the gate.
    with pytest.raises(legacy.WebSolProtocolError):
        protocol.validate_window(request("fill", params={"text": "\uD800" * 30001}))


def test_fill_refuses_line_counts_that_freeze_the_editor_pipeline():
    # The editor pipeline issues one execCommand pair per line; a 30,000-newline
    # fill used to reach the page and freeze the tab (SCORE e2#2). The protocol
    # refuses normalized line counts above the cap before any dispatch; the cap
    # boundary itself still validates.
    with pytest.raises(legacy.WebSolProtocolError):
        protocol.validate_window(request("fill", params={"text": "a\n" * 15000}))
    with pytest.raises(legacy.WebSolProtocolError):
        protocol.validate_window(request("fill", params={"text": "\n" * 2001}))
    accepted = protocol.validate_window(request("fill", params={"text": "\n" * 2000}))
    assert accepted["params"]["text"] == "\n" * 2000
    # Lone CR normalizes to a line break on the insertion feed, so it counts
    # toward the cap rather than sneaking lines past it.
    with pytest.raises(legacy.WebSolProtocolError):
        protocol.validate_window(request("fill", params={"text": "\r" * 2001}))


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


def test_bridge_emit_never_fails_on_unencodable_reply_text(monkeypatch):
    # p1#7 + ruling 15 item 4: page-produced text can reach the reply
    # carrying lone surrogates — high (\ud800) or low (\udc80) — and the
    # operator's only reply channel is stdout. The bridge encodes strictly
    # itself and writes bytes through sys.stdout.buffer: a text layer with
    # errors="surrogateescape" (the default for the spawned subprocess under
    # plain, PYTHONUTF8=1 and LC_ALL=C) passes low surrogates through as raw
    # bytes and would emit an invalid UTF-8 line without raising. One
    # parseable reply always arrives.
    raw=io.BytesIO()
    stream=io.TextIOWrapper(raw,encoding="utf-8",errors="surrogateescape",newline="")
    monkeypatch.setattr(bridge.sys,"stdout",stream)
    bridge._emit({"state":"RECEIPT","data":{"content":"end \ud800 tail"}})
    bridge._emit({"state":"RECEIPT","data":{"content":"low \udc80 tail"}})
    stream.flush()
    lines=raw.getvalue().split(b"\n")
    assert lines[-1]==b""
    for line in lines[:-1]:
        json.loads(line.decode("utf-8"))
    assert all(line for line in lines[:-1]),"every emitted line is strict-valid UTF-8"
    assert json.loads(lines[0].decode("utf-8"))["data"]["content"]=="end \ud800 tail"
    assert json.loads(lines[1].decode("utf-8"))["data"]["content"]=="low \udc80 tail"
    # An ordinary non-ASCII payload keeps the compact unescaped channel.
    raw.seek(0); raw.truncate()
    bridge._emit({"state":"RECEIPT","data":{"content":"café 𝕏"}})
    stream.flush()
    assert raw.getvalue()==b'{"state":"RECEIPT","data":{"content":"caf\xc3\xa9 \xf0\x9d\x95\x8f"}}\n'


def test_read_contract_states_enforced_limits_and_operator_rules():
    # p1#1: the read contract must state what is actually enforced (worker
    # 800,000-byte RESULT_TOO_LARGE; native host 921,600-byte MAX_MESSAGE_BYTES)
    # instead of the never-enforced 32,768-byte envelope, and carry the three
    # operator rules: no drift guard across pages, repeated blank lines can
    # hide a dropped empty line, read the box before sending.
    schema=bridge.TOOL_SCHEMA["description"]
    assert "skip or repeat" in schema and "dropped empty line" in schema
    assert "read the box before sending" in schema
    assert "32,768" not in schema
    page=(ROOT/"integrations/chairman_surfaces/web_sol_extension/browser_page.js").read_text()
    assert "32,768" not in page
    for ceiling in ("800,000","921,600"):
        assert ceiling in page,f"the page comment names the enforced ceiling {ceiling}"
    doc=(ROOT/"integrations/hermes_harness/mcp_bridge_install.md").read_text()
    assert "32,768-byte envelope" not in doc
    for phrase in ("skip or repeat","dropped empty line","read the box before sending","800,000","921,600","settle interval"):
        assert phrase in doc,f"the install doc states {phrase}"
    for name in ("browser_bridge.py","browser_tool_schema.json"):
        digest=hashlib.sha256((ROOT/"integrations/hermes_harness"/name).read_bytes()).hexdigest()
        assert digest in doc,f"the doc pins the wrong hash for {name}"


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



def test_invalid_arguments_names_missing_and_unexpected_arguments_only(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,"inventory",lambda _: [{"browser_id":"a"*64}])
    monkeypatch.setattr(bridge.routes,"load",lambda _: None)
    refused=bridge.execute({"action":"fill","browser_id":"a"*64,"tab_id":3,"url_fingerprint":"c"*64,
        "ref":"e1","text":"secret payload value","options":{}},
        native_session_id="s",profile_ref="/profile",bindings_path=tmp_path/"bindings")
    assert refused["state"]=="REFUSED" and refused["reason"]=="INVALID_ARGUMENTS"
    detail=str(refused.get("detail"))
    # A missing connection_id is now distinguishable from a missing snapshot_id.
    for name in ("connection_id","snapshot_id","options"):
        assert name in detail, detail
    assert "text" not in detail, "a correctly supplied name is never named"
    assert "secret payload value" not in detail


def test_unknown_argument_name_is_reported_without_its_value(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,"inventory",lambda _: [{"browser_id":"a"*64}])
    refused=bridge.execute({"action":"status","browser_id":"a"*64,"bogus":"value-never-shown"},
        native_session_id="s",profile_ref="/profile",bindings_path=tmp_path/"bindings")
    assert refused["reason"]=="INVALID_ARGUMENTS"
    assert "bogus" in str(refused.get("detail"))
    assert "value-never-shown" not in str(refused.get("detail"))


def test_read_takes_offset_with_ref_and_snapshot(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,"inventory",lambda _: [{"browser_id":"a"*64}])
    monkeypatch.setattr(bridge.routes,"load",lambda _: None)
    seen=[]
    def exchange(browser_id,session_id,operation_key,action,connection_id,tab_id,
                 url_fingerprint,snapshot_id,ref,params,nonce):
        seen.append({"browser_id":browser_id,"action":action,"connection_id":connection_id,
            "tab_id":tab_id,"url_fingerprint":url_fingerprint,"snapshot_id":snapshot_id,
            "ref":ref,"params":params})
        return {"status":"OK","effect":"NOT_APPLIED","data":{"offset":params.get("offset")}}
    out=bridge.execute({"action":"read","browser_id":"a"*64,"connection_id":"conn-1","tab_id":3,
        "url_fingerprint":"c"*64,"snapshot_id":"snapshot-observation-001","ref":"e7","offset":4096},
        native_session_id="s",profile_ref="/profile",bindings_path=tmp_path/"bindings",exchange=exchange)
    assert out["state"]=="RECEIPT", out
    assert seen==[{"browser_id":"a"*64,"action":"read","connection_id":"conn-1","tab_id":3,
        "url_fingerprint":"c"*64,"snapshot_id":"snapshot-observation-001","ref":"e7",
        "params":{"offset":4096}}]
    # Without offset the bridge names it missing instead of dispatching.
    missing=bridge.execute({"action":"read","browser_id":"a"*64,"connection_id":"conn-1","tab_id":3,
        "url_fingerprint":"c"*64,"snapshot_id":"snapshot-observation-001","ref":"e7"},
        native_session_id="s",profile_ref="/profile",bindings_path=tmp_path/"bindings")
    assert missing["reason"]=="INVALID_ARGUMENTS" and "offset" in str(missing.get("detail"))


def test_diagnostics_is_callable_without_a_snapshot_id(tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,"inventory",lambda _: [{"browser_id":"a"*64}])
    monkeypatch.setattr(bridge.routes,"load",lambda _: None)
    seen=[]
    def exchange(browser,**kwargs):
        seen.append(kwargs);return {"status":"OK","effect":"NOT_APPLIED","data":{"page_world":"ok"}}
    result=bridge.execute({"action":"diagnostics","browser_id":"a"*64,"connection_id":"c1",
        "tab_id":3,"url_fingerprint":"c"*64},
        native_session_id="s",profile_ref="/profile",bindings_path=tmp_path/"bindings",exchange=exchange)
    assert result["state"]=="RECEIPT", result
    assert seen[-1]["snapshot_id"] is None
    assert result["receipt"]["status"]=="OK"


@pytest.mark.parametrize("snapshot_id",[None,"snapshot-observation-001"])
def test_diagnostics_window_request_accepts_optional_snapshot_id(snapshot_id):
    original=request("diagnostics",snapshot_id=snapshot_id)
    assert protocol.validate_window(original)==original


@pytest.mark.parametrize("extra",[{}, {"snapshot_id":None}, {"snapshot_id":"snapshot-observation-001"}])
def test_bridge_diagnostics_accepts_optional_snapshot_id(extra,tmp_path,monkeypatch):
    monkeypatch.setattr(bridge,"inventory",lambda _: [{"browser_id":"a"*64}])
    monkeypatch.setattr(bridge.routes,"load",lambda _: None)
    seen=[]
    def exchange(browser,**kwargs):
        seen.append(kwargs);return {"status":"OK","effect":"NOT_APPLIED","data":{"page_world":"ok"}}
    result=bridge.execute({"action":"diagnostics","browser_id":"a"*64,"connection_id":"c1",
        "tab_id":3,"url_fingerprint":"c"*64,**extra},
        native_session_id="s",profile_ref="/profile",bindings_path=tmp_path/"bindings",exchange=exchange)
    assert result["state"]=="RECEIPT", result
    assert seen[-1]["snapshot_id"] is None or type(seen[-1]["snapshot_id"]) is str
