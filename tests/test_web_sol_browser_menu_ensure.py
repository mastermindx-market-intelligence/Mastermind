"""BR2 items 1+4 on the Python side: menu and snapshot-ensure validation,
and the bridge argument wiring that carries them to the native host."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets

import pytest

from integrations.chairman_surfaces import web_sol_browser_protocol as protocol
from integrations.chairman_surfaces import web_sol_protocol as legacy
from integrations.hermes_harness import browser_bridge as bridge

ROOT = Path(__file__).resolve().parents[1]


def request(action="menu", **changes):
    now = datetime.now(timezone.utc)
    value = dict(schema=protocol.REQUEST_SCHEMA, adapter_instance_id="a"*64,
        session_id="b"*64, operation_key="menu-ensure-contract", nonce=secrets.token_hex(24),
        transport_boot_nonce="connection-generation-001", action=action,
        tab_id=17, url_fingerprint="c"*64, snapshot_id="snapshot-observation-001",
        ref="e1", params={"path": ["Thinking"]},
        issued_at=now.isoformat().replace("+00:00", "Z"),
        expires_at=(now+timedelta(seconds=30)).isoformat().replace("+00:00", "Z"))
    if action == "snapshot":
        value.update(snapshot_id=None, ref=None, params={})
    value.update(changes)
    return value


def test_menu_is_a_page_action_with_a_bounded_path():
    assert "menu" in protocol.PAGE_ACTIONS and "menu" in protocol.ACTIONS
    for path in (["GPT-5"], ["Thinking", "Extra High"], ["a", "b", "c"]):
        accepted = protocol.validate_request(request(params={"path": path}))
        assert accepted["params"] == {"path": path}


@pytest.mark.parametrize("params", [
    {}, {"path": []}, {"path": ["a", "b", "c", "d"]}, {"path": "Thinking"},
    {"path": [1]}, {"path": [""]}, {"path": ["x"*161]}, {"path": ["bad\nlabel"]},
    {"path": ["Thinking"], "extra": 1},
])
def test_menu_bad_paths_fail_closed(params):
    with pytest.raises(legacy.WebSolProtocolError):
        protocol.validate_request(request(params=params))


def test_menu_requires_an_opener_ref():
    with pytest.raises(legacy.WebSolProtocolError):
        protocol.validate_request(request(ref=None))


@pytest.mark.parametrize("params", [
    {}, {"ensure_role": "textbox"}, {"ensure_role": "textbox", "ensure_name": "Message composer"},
    {"ensure_role": "button", "ensure_name": "Send"},
])
def test_snapshot_ensure_shapes_validate(params):
    accepted = protocol.validate_request(request("snapshot", params=params))
    assert accepted["params"] == params


@pytest.mark.parametrize("params", [
    {"ensure_name": "only name"}, {"ensure_role": ""}, {"ensure_role": "x"*41},
    {"ensure_role": "textbox", "ensure_name": ""},
    {"ensure_role": "textbox", "ensure_name": "x"*161},
    {"ensure_role": "text\nbox"}, {"ensure_role": 5},
    {"ensure_role": "textbox", "extra": 1},
])
def test_snapshot_bad_ensure_fails_closed(params):
    with pytest.raises(legacy.WebSolProtocolError):
        protocol.validate_request(request("snapshot", params=params))


def exchange_capture(calls):
    def exchange(browser, **kwargs):
        calls.append(kwargs)
        return {"status": "OK"}
    return exchange


def base_args(action, **extra):
    args = {"action": action, "browser_id": "a"*64,
            "connection_id": "connection-generation-001"}
    if action in protocol.TAB_ACTIONS:
        args.update(tab_id=17, url_fingerprint="c"*64)
    if action in protocol.TAB_ACTIONS - protocol.NO_SNAPSHOT:
        args.update(snapshot_id="snapshot-observation-001")
    if action in protocol.PAGE_ACTIONS:
        args.update(ref="e1")
    args.update(extra)
    return args


def run_bridge(tmp_path, monkeypatch, args, calls):
    # Isolate the argument wiring from the routing inventory: a registered
    # local browser, no fleet document.
    monkeypatch.setattr(bridge.routes, "load", lambda _: None)
    monkeypatch.setattr(bridge, "inventory", lambda _: [{"browser_id": "a"*64}])
    return bridge.execute(args, native_session_id="session-one", profile_ref="/profile/a",
        bindings_path=tmp_path/"bindings", exchange=exchange_capture(calls),
        operation_key="menu-ensure-"+"1"*32, nonce="2"*48)


def test_bridge_menu_carries_path_and_ref(tmp_path, monkeypatch):
    calls = []
    result = run_bridge(tmp_path, monkeypatch, base_args("menu", path=["Thinking", "Extra High"]), calls)
    assert result["state"] == "RECEIPT"
    assert calls[0]["params"] == {"path": ["Thinking", "Extra High"]}
    assert calls[0]["ref"] == "e1" and calls[0]["action"] == "menu"


def test_bridge_menu_requires_path_and_ref(tmp_path, monkeypatch):
    calls = []
    missing_path = run_bridge(tmp_path, monkeypatch, base_args("menu"), calls)
    assert missing_path["state"] == "REFUSED" and missing_path["reason"] == "INVALID_ARGUMENTS"
    no_ref = base_args("menu", path=["Thinking"])
    del no_ref["ref"]
    missing_ref = run_bridge(tmp_path, monkeypatch, no_ref, calls)
    assert missing_ref["state"] == "REFUSED" and missing_ref["reason"] == "INVALID_ARGUMENTS"
    assert calls == []


def test_bridge_snapshot_ensure_is_optional_and_forwarded(tmp_path, monkeypatch):
    calls = []
    plain = run_bridge(tmp_path, monkeypatch, base_args("snapshot"), calls)
    assert plain["state"] == "RECEIPT" and calls[0]["params"] == {}
    ensured = run_bridge(tmp_path, monkeypatch, base_args("snapshot", ensure_role="textbox",
        ensure_name="Message composer"), calls)
    assert ensured["state"] == "RECEIPT"
    assert calls[1]["params"] == {"ensure_role": "textbox", "ensure_name": "Message composer"}
    role_only = run_bridge(tmp_path, monkeypatch, base_args("snapshot", ensure_role="textbox"), calls)
    assert role_only["state"] == "RECEIPT" and calls[2]["params"] == {"ensure_role": "textbox"}


def test_bridge_ensure_and_path_are_action_scoped(tmp_path, monkeypatch):
    calls = []
    for args in (base_args("click", ensure_role="textbox"),
                 base_args("snapshot", path=["Thinking"]),
                 base_args("fill", text="hi", ensure_name="box")):
        result = run_bridge(tmp_path, monkeypatch, args, calls)
        assert result["state"] == "REFUSED" and result["reason"] == "INVALID_ARGUMENTS"
    assert calls == []


def test_tool_schema_states_menu_ensure_and_orphan_close():
    schema = bridge.TOOL_SCHEMA
    props = schema["parameters"]["properties"]
    assert "menu" in props["action"]["enum"]
    assert props["path"]["type"] == "array" and props["path"]["maxItems"] == 3
    assert "ensure_role" in props and "ensure_name" in props
    description = schema["description"]
    assert "read_back" in description and "EFFECT_UNKNOWN, never success" in description
    assert "ensure_role" in description and "without scrolling" in description
    assert "operator tabs" in description and "orphan_close" in description
    assert "Close is limited to tabs this session created" not in description
    on_disk = json.loads((ROOT/"integrations/hermes_harness/browser_tool_schema.json").read_text())
    assert on_disk == schema
