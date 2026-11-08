"""Foreground Web team client proofs with an isolated incumbent-tool fake."""
from __future__ import annotations

import asyncio
import pytest

from integrations.session_bridge.web_team_client import (
    TeamBusEffectUnknown, TeamBusUnavailable, WebTeamClient,
)


def run(task):
    return asyncio.run(task)


def target(kind="hermes_meta"):
    return {
        "kind": kind,
        "target_ref": kind + ":" + "a" * 64,
        "continuation_operation_key": "session-continue-" + "b" * 64,
        "work_ref": "WS:EXECUTIVE-ECOSYSTEM-COMPLETION",
    }


def reply(name, data):
    return {"schema": "mastermind.session_bridge_result.v1", "tool": name,
            "ok": True, "data": data, "error": None}


def setup(reply_read=None, send=None):
    calls = []

    async def call(name, args):
        calls.append((name, dict(args)))
        if name == "session_targets":
            return reply(name, [target(args["kind"])])
        if name == "session_send":
            if isinstance(send, Exception):
                raise send
            return reply(name, send if send is not None else {"native_status": "ADMITTED"})
        if name == "session_reply_read":
            if isinstance(reply_read, Exception):
                raise reply_read
            return reply(name, reply_read if reply_read is not None else {
                "native_status": "OBSERVED", "successful": True, "answer": "received"})
        return reply(name, {"accepted": False})

    return WebTeamClient(call), calls


def test_discover_exact_native_bot_and_send_verbatim_once():
    client, calls = setup()
    (selected,) = run(client.targets("hermes_meta"))
    original = "Build a narrow proof.\n  Preserve formatting."
    result = run(client.send(selected, original, "Return original reply"))
    assert result["data"]["native_status"] == "ADMITTED"
    assert calls == [
        ("session_targets", {"kind": "hermes_meta"}),
        ("session_send", {"target_ref": selected.target_ref, "instruction": original,
                          "stop_condition": "Return original reply",
                          "operation_key": selected.operation_key}),
    ]


def test_secretary_discovery_does_not_default_to_legacy_roster():
    client, calls = setup()
    selected = run(client.targets("hermes_secretary"))
    assert selected[0].kind == "hermes_secretary"
    assert calls == [("session_targets", {"kind": "hermes_secretary"})]
    with pytest.raises(ValueError):
        run(client.targets("arbitrary_worker"))


def test_unselected_and_stale_target_cannot_trigger_send():
    client, calls = setup()
    from integrations.session_bridge.web_team_client import HermesTarget
    forged = HermesTarget("hermes_meta", "hermes_meta:" + "a" * 64,
                          "session-continue-" + "b" * 64)
    with pytest.raises(ValueError):
        run(client.send(forged, "hi", "stop"))
    assert calls == []
    selected, = run(client.targets("hermes_meta"))
    # Server can change the projected target: a different discovery clears it.
    async def moved(name, args):
        return reply(name, [{**target(), "target_ref": "hermes_meta:" + "f" * 64}])
    client._call_tool = moved
    run(client.targets("hermes_meta"))
    with pytest.raises(ValueError):
        run(client.send(selected, "hi", "stop"))


def test_transport_loss_preserves_original_key_without_retry():
    client, calls = setup(send=ConnectionError("connection lost"))
    selected, = run(client.targets("hermes_meta"))
    with pytest.raises(TeamBusEffectUnknown) as caught:
        run(client.send(selected, "First instruction", "Return one result"))
    assert caught.value.operation_key == selected.operation_key
    assert [name for name, _ in calls].count("session_send") == 1
    assert len(calls) == 2


def test_typed_effect_unknown_is_preserved_not_retried():
    client, calls = setup()
    selected, = run(client.targets("hermes_meta"))
    async def uncertain(name, args):
        if name == "session_send":
            calls.append((name, dict(args)))
            return {"tool": name, "ok": False, "data": None,
                    "error": {"code": "effect_unknown", "message": "original receipt unknown"}}
        raise AssertionError("unexpected")
    client._call_tool = uncertain
    response = run(client.send(selected, "Work", "Return"))
    assert response["error"]["code"] == "effect_unknown"
    assert [name for name, _ in calls].count("session_send") == 1


def test_original_answer_read_is_distinct_and_does_not_send():
    client, calls = setup(reply_read={"native_status": "OBSERVED", "answer": "original", "successful": True,
                                            "parent_consumed": False})
    key = "session-continue-" + "0" * 64
    observed = run(client.read_original(key))
    assert observed["answer"] == "original"
    assert observed["parent_consumed"] is False
    assert calls == [("session_reply_read", {"operation_key": key})]


def test_read_failure_never_becomes_pending_or_empty_result():
    client, calls = setup(reply_read=TimeoutError("no read"))
    with pytest.raises(TeamBusUnavailable):
        run(client.read_original("session-continue-" + "0" * 64))
    assert len(calls) == 1
    with pytest.raises(ValueError):
        run(client.read_original("latest"))


def test_malformed_roster_rejected_before_any_send():
    async def bogus(name, args):
        return reply(name, [{**target(), "continuation_operation_key": "fake"}])
    client = WebTeamClient(bogus)
    with pytest.raises(TeamBusUnavailable):
        run(client.targets("hermes_meta"))


def test_delegation_uses_existing_executive_and_never_pins_deepseek():
    client, calls = setup()
    args = dict(operation_key="web-team-bus-testrun", objective="Source review", department="executive-infrastructure",
                priority=0, execution_profile="research_only",
                workstream="WS:EXECUTIVE-ECOSYSTEM-COMPLETION")
    result = run(client.submit_worker(args))
    assert result["data"]["accepted"] is False
    assert calls == [("session_summon", {**args, "allowed_write_paths": [],
                                     "validation": {}, "attempt_limit": 2})]
    with pytest.raises(Exception):
        run(client.submit_worker({**args, "provider": "deepseek"}))
    assert len(calls) == 1


def test_worker_uncertain_effect_is_not_replayed():
    calls = []
    async def failed(name, args):
        calls.append(name)
        raise ConnectionError("send outcome unknown")
    client = WebTeamClient(failed)
    args = dict(operation_key="web-team-bus-testrun", objective="Source review", department="executive-infrastructure",
                priority=0, execution_profile="research_only",
                workstream="WS:EXECUTIVE-ECOSYSTEM-COMPLETION")
    with pytest.raises(TeamBusEffectUnknown) as caught:
        run(client.submit_worker(args))
    assert caught.value.operation_key == "web-team-bus-testrun"
    assert calls == ["session_summon"]
