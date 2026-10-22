"""Regression for action admission waiting before a durable claim exists."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import threading
from types import SimpleNamespace

import pytest

from integrations.workbench_action_mcp.action_artifacts import acquire_store_writer
from integrations.workbench_browser_mcp import browser_port as module
from integrations.mastermind_browser_link.tool_contract import LINK_TOOL_SCHEMA_DIGEST, OWNER_RESULT_SCHEMA
from tests.test_workbench_browser_port import _fixture


def reply(request):
    return {"schema": "mastermind.workbench_browser_relay_response.v1",
            "request_id": request["request_id"], "resource_id": "c" * 32,
            "ok": True, "result": {"content": [], "isError": False}}


def test_reconcile_does_not_report_no_effect_while_original_waits_to_claim(tmp_path, monkeypatch):
    calls = []
    def relay(_path, request, **_):
        calls.append(request)
        return reply(request)
    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    waiting = threading.Event()
    actual_writer = port._action_writer
    def writer():
        waiting.set()
        return actual_writer()
    monkeypatch.setattr(port, "_action_writer", writer)
    try:
        action = port.prepare_action(caller, browser_ref, "browser_click", {"target": "button"})
        with ThreadPoolExecutor(1) as pool:
            with acquire_store_writer(port._store):
                future = pool.submit(port.run_action, caller, browser_ref, action)
                assert waiting.wait(2)
                assert port.reconcile_action(caller, browser_ref, action)["effect_state"] == "EFFECT_UNKNOWN"
                assert calls == []
            assert future.result(timeout=3)["effect_state"] == "APPLIED"
        assert len(calls) == 1
    finally:
        os.close(fd)


def test_distinct_actions_release_store_writer_during_browser_io(tmp_path):
    barrier = threading.Barrier(2)
    calls = []
    def relay(_path, request, **_):
        calls.append(request["request_id"])
        with acquire_store_writer(port._store):
            pass
        barrier.wait(timeout=3)
        return reply(request)
    fd, caller, port, browser_ref = _fixture(tmp_path, relay)
    try:
        actions = [port.prepare_action(caller, browser_ref, "browser_click", {"target": target})
                   for target in ("one", "two")]
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(port.run_action, caller, browser_ref, action) for action in actions]
            assert [future.result(timeout=5)["effect_state"] for future in futures] == ["APPLIED", "APPLIED"]
        assert len(set(calls)) == 2
    finally:
        os.close(fd)


@pytest.mark.parametrize("status,effect,is_error,expected", [
    ("completed", "APPLIED", False, "APPLIED"),
    ("refused", "NOT_APPLIED", True, "NOT_APPLIED"),
    ("refused", "EFFECT_UNKNOWN", True, "EFFECT_UNKNOWN"),
    ("pending", "EFFECT_UNKNOWN", True, "EFFECT_UNKNOWN"),
    ("completed", "NOT_APPLIED", False, None),
    ("refused", "APPLIED", True, None),
    ("completed", "APPLIED", True, None),
])
def test_link_action_receipts_have_explicit_effect_semantics(status, effect, is_error, expected):
    browser = SimpleNamespace(tool_schema_digest=LINK_TOOL_SCHEMA_DIGEST)
    prepared = SimpleNamespace(action_id="a" * 32)
    result = {"isError": is_error, "structuredContent": {
        "schema": OWNER_RESULT_SCHEMA, "request_id": prepared.action_id,
        "status": status, "effect_state": effect,
    }}
    assert module.BrowserActionPort._result_effect(browser, prepared, result) == expected
    result["structuredContent"]["request_id"] = "b" * 32
    assert module.BrowserActionPort._result_effect(browser, prepared, result) is None


@pytest.mark.parametrize("failure", ["lost_response", "persistence_failure", "qualified_unknown"])
def test_link_durable_uncertainty_blocks_later_new_mutation(tmp_path, monkeypatch, failure):
    from integrations.workbench_action_mcp.action_artifacts import ActionArtifactUncertain
    from integrations.mastermind_browser_link.tool_contract import ACTION_TOOL
    from integrations.workbench_browser_mcp.browser_port import BrowserPortRefused
    from integrations.workbench_browser_mcp.relay import BrowserRelayError
    calls = []
    def relay(_path, request, **_):
        calls.append(request)
        if failure == "lost_response":
            raise BrowserRelayError("receipt lost after dispatch")
        effect = "EFFECT_UNKNOWN" if failure == "qualified_unknown" else "APPLIED"
        return {**reply(request), "result": {"content": [], "isError": effect != "APPLIED",
                "structuredContent": {"schema": OWNER_RESULT_SCHEMA, "request_id": request["request_id"],
                    "status": "refused" if effect == "EFFECT_UNKNOWN" else "completed", "effect_state": effect}}}
    fd, caller, port, legacy_ref = _fixture(tmp_path, relay)
    try:
        browser = port.codec.decode_resource(legacy_ref, now_ms=2000)
        browser_ref = port.codec.encode_resource(replace(browser, mode="extension",
            profile_ref="link-" + "a" * 64, tool_schema_digest=LINK_TOOL_SCHEMA_DIGEST))
        first = port.prepare_action(caller, browser_ref, ACTION_TOOL, {"fixture": 1})
        second = port.prepare_action(caller, browser_ref, ACTION_TOOL, {"fixture": 2})
        if failure == "persistence_failure":
            monkeypatch.setattr(port, "_finalize_claimed",
                                lambda *a, **kw: (_ for _ in ()).throw(ActionArtifactUncertain("fsync failed")))
        assert port.run_action(caller, browser_ref, first)["effect_state"] == "EFFECT_UNKNOWN"
        assert not port._inflight_actions
        with pytest.raises(BrowserPortRefused, match="BROWSER_EFFECT_UNRESOLVED"):
            port.run_action(caller, browser_ref, second)
        assert len(calls) == 1
        assert port.reconcile_action(caller, browser_ref, first)["effect_state"] == "EFFECT_UNKNOWN"
    finally:
        os.close(fd)
