"""Original diagnostics, veto and terminal-result owners composed on fake transports.

The actual bridge and shared provider waterfall execute. These tests neither
invoke providers nor infer submission acceptance from diagnostic observations.
"""
from __future__ import annotations

import asyncio
import copy
import json

import pytest

from test_sdk_diagnostic_bridge import (
    AssistantMessage, CANDIDATES, DiagnosticInterruption, Harness, ResultMessage,
    TextBlock, ToolResultBlock, ToolUseBlock, UserMessage, envelope,
)


def waterfall_call(harness, monkeypatch, *, guard=None):
    """Keep the real waterfall; owned terminals and vetoes never consult shared auth."""
    from brain import provider_waterfall as pw
    shared_lookups = []

    def unexpected_shared_modules():
        shared_lookups.append(True)
        raise AssertionError("a refusal or owned SDK terminal cannot consult shared auth")

    monkeypatch.setattr(pw, "_shared_modules", unexpected_shared_modules)
    monkeypatch.setattr(pw, "provider_rungs", lambda _role: [
        {"provider": "oauth", **candidate, "cooling": False} for candidate in CANDIDATES
    ])
    entries, classifications = [], []
    original_reason = harness.cb._reason
    original_failure_kind = pw._failure_kind

    async def reason(prompt, **kwargs):
        entries.append(kwargs["_subscription_slots"])
        return await original_reason(prompt, **kwargs)

    def failure_kind(error):
        classifications.append(error)
        return original_failure_kind(error)

    monkeypatch.setattr(harness.cb, "_reason", reason)
    monkeypatch.setattr(pw, "_failure_kind", failure_kind)

    def invoke():
        try:
            return asyncio.run(pw.reason(
                "fixture prompt", model="fixture-model", role="deep", arm=True,
                allowed_tools=[], add_dirs=[], mcp_servers={}, cwd="/fixture/workspace",
                book="autonomous", before_provider_start=guard,
            ))
        finally:
            assert shared_lookups == [], "owned terminal/refusal consulted shared auth"

    return invoke, entries, classifications


@pytest.mark.parametrize("guard_kind", ["callback_refusal", "invalid_cleanup", "cancelled_cleanup"])
@pytest.mark.parametrize("diagnostic_failure", ["none", "ordinary_logger", "base_logger"])
def test_veto_finalizes_once_before_query_observation_and_never_replays(
    monkeypatch, guard_kind, diagnostic_failure,
):
    h = Harness(monkeypatch)
    h.plans = [[ResultMessage()]]
    events, original_errors, record_calls, finish_calls, projections = [], [], [], [], []
    original_require = h.cb._require_provider_start
    original_observe = h.cb._observe_sdk_diagnostic
    original_record = h.cb._record_sdk_diagnostic
    original_finish = h.diag.SDKInvocationDiagnostics.finish
    original_log = h.rl.log_step
    private_detail = "SYNTHETIC_PRIVATE_VALIDATION_DETAIL"
    cancelled = asyncio.CancelledError(private_detail)

    class InvalidCleanup:
        @property
        def close(self):
            if guard_kind == "cancelled_cleanup":
                raise cancelled
            raise ValueError(private_detail)

    def guard():
        events.append("veto")
        if guard_kind == "callback_refusal":
            raise ValueError(private_detail)
        return InvalidCleanup()

    def require(callback):
        try:
            return original_require(callback)
        except BaseException as exc:
            original_errors.append(exc)
            raise

    def observe(state, **kwargs):
        events.append("query_observation" if kwargs.get("query_entered") else "message_observation")
        return original_observe(state, **kwargs)

    def record(*args, **kwargs):
        record_calls.append((args, kwargs))
        return original_record(*args, **kwargs)

    def finish(self, end_state, exception=None):
        events.append("diagnostic_finish")
        finish_calls.append((end_state, exception))
        projection = original_finish(self, end_state, exception)
        projections.append(copy.deepcopy(projection))
        return projection

    def log(*args, **kwargs):
        if args[1] == "provider_diagnostic":
            events.append("diagnostic_log")
            if diagnostic_failure == "ordinary_logger":
                raise RuntimeError("429 quota diagnostic logger failure")
            if diagnostic_failure == "base_logger":
                raise DiagnosticInterruption("429 quota diagnostic logger interruption")
        return original_log(*args, **kwargs)

    monkeypatch.setattr(h.cb, "_require_provider_start", require)
    monkeypatch.setattr(h.cb, "_observe_sdk_diagnostic", observe)
    monkeypatch.setattr(h.cb, "_record_sdk_diagnostic", record)
    monkeypatch.setattr(h.diag.SDKInvocationDiagnostics, "finish", finish)
    monkeypatch.setattr(h.rl, "log_step", log)
    invoke, entries, outer_classifications = waterfall_call(h, monkeypatch, guard=guard)
    expected_type = asyncio.CancelledError if guard_kind == "cancelled_cleanup" else h.cb.ProviderStartRefused
    with pytest.raises(expected_type) as caught:
        invoke()

    assert len(original_errors) == 1 and caught.value is original_errors[0]
    expected_end = "interrupted" if guard_kind == "cancelled_cleanup" else "raised"
    assert finish_calls == [(expected_end, caught.value)]
    assert len(record_calls) == len(projections) == 1
    assert events == ["veto", "diagnostic_finish", "diagnostic_log"]
    assert projections[0]["observation"]["query_entered_observed"] is False
    assert projections[0]["observation"]["sdk_messages_observed"] == 0
    assert projections[0]["exit"]["end_state"] == expected_end
    assert projections[0]["qualifications"]["effect_reconciliation"] == "not_performed"
    assert len(entries) == 1 and h.providers == []
    assert outer_classifications == h.classifications == h.cooling == h.sessions == []
    if guard_kind == "cancelled_cleanup":
        assert caught.value is cancelled
        assert h.cb.provider_refusal_run_id(caught.value, book="autonomous", role="deep") is None
    else:
        assert str(caught.value) == "source admission revoked before provider start"
        assert private_detail not in json.dumps(projections)
        assert h.cb.provider_refusal_run_id(caught.value, book="autonomous", role="deep") == "fixture-run"
        assert h.cb.provider_refusal_run_id(caught.value, book="hk", role="deep") is None
    if diagnostic_failure == "none":
        assert envelope(h) == projections[0]


@pytest.mark.parametrize("enabled", [False, True])
def test_sticky_terminal_preserves_thinking_text_and_tool_handlers(
    monkeypatch, enabled,
):
    from brain import thinking_log

    h = Harness(monkeypatch)
    if not enabled:
        monkeypatch.setattr(h.cb, "_new_sdk_diagnostic", lambda *a: None)
        monkeypatch.setattr(h.cb, "_record_sdk_diagnostic", lambda *a: None)
    thought = "PRIVATE_TOOL_THOUGHT"
    synthesis = "PRIVATE_SYNTHESIS_THOUGHT"
    plan = [
        AssistantMessage([
            {"type": "thinking", "thinking": thought},
            {"type": "redacted_thinking"},
            TextBlock("intermediate assistant text"), ToolUseBlock(),
        ]),
        UserMessage([ToolResultBlock(is_error=True)]),
        ResultMessage(is_error=True, result="401 429 usage limit reached",
                      errors=["disabled Claude subscription access"]),
        AssistantMessage([{"type": "thinking", "thinking": synthesis}, TextBlock("later assistant text")]),
        ResultMessage(is_error=False, result="later terminal", total_cost_usd=0.75),
    ]
    original_plan = copy.deepcopy(plan)
    h.plans = [plan]
    ledger = []
    monkeypatch.setattr(thinking_log, "log_turn_async", lambda **kwargs: ledger.append(copy.deepcopy(kwargs)))
    invoke, entries, outer_classifications = waterfall_call(h, monkeypatch)
    result = invoke()

    assert plan == original_plan
    assert result["ok"] is False and result["error"] == "sdk_terminal_error"
    assert result["text"] == "later terminal" and result["tools_used"] == ["mcp__bot__read"]
    assert result["cost_usd"] == 0.75 and result["session_id"] == "fixture-session"
    assert result["usage"] == {"input_tokens": 11, "output_tokens": 7}
    assert len(entries) == len(h.providers) == len(result["provider_attempts"]) == 1
    assert outer_classifications == []
    assert h.classifications == h.cooling == h.sessions == []
    assert len(ledger) == 1
    assert ledger[0]["thinking"] == [
        {"round": 1, "phase": "tool", "model": "fixture-model", "text": thought},
        {"round": 1, "phase": "tool", "model": "fixture-model", "text": "", "redacted": True},
        {"round": 3, "phase": "synthesis", "model": "fixture-model", "text": synthesis},
    ]
    assert "thinking" not in result
    assert thought not in json.dumps(result) and synthesis not in json.dumps(result)
    if enabled:
        diagnostic = envelope(h)
        assert diagnostic["exit"]["end_state"] == "exhausted"
        assert diagnostic["observation"]["query_entered_observed"] is True
        assert diagnostic["observation"]["sdk_messages_observed"] == 5
        assert diagnostic["observation"]["tool_use_blocks_observed"] == 1
        assert diagnostic["observation"]["tool_result_blocks_observed"] == 1
        assert diagnostic["terminals"]["count"] == 2
        assert diagnostic["terminals"]["first"]["is_error"] is True
        assert diagnostic["terminals"]["last"]["is_error"] is False
    else:
        assert h.diagnostics() == []


@pytest.mark.parametrize("failure_point", ["finish", "logger"])
@pytest.mark.parametrize("failure_type", ["ordinary", "base"])
def test_terminal_finalization_failure_never_becomes_auth_or_quota_replay(
    monkeypatch, failure_point, failure_type,
):
    h = Harness(monkeypatch)
    h.plans = [[ResultMessage(is_error=True, result="401 429 usage limit reached")]]
    failure = (RuntimeError("disabled Claude subscription access 429 quota")
               if failure_type == "ordinary" else DiagnosticInterruption("429 quota diagnostic interruption"))
    original_finish = h.diag.SDKInvocationDiagnostics.finish
    original_log = h.rl.log_step
    original_record = h.cb._record_sdk_diagnostic
    finishes, records = [], []

    def finish(self, end_state, exception=None):
        finishes.append((end_state, exception))
        if failure_point == "finish":
            raise failure
        return original_finish(self, end_state, exception)

    def log(*args, **kwargs):
        if failure_point == "logger" and args[1] == "provider_diagnostic":
            raise failure
        return original_log(*args, **kwargs)

    def record(*args, **kwargs):
        records.append((args, kwargs))
        return original_record(*args, **kwargs)

    monkeypatch.setattr(h.diag.SDKInvocationDiagnostics, "finish", finish)
    monkeypatch.setattr(h.rl, "log_step", log)
    monkeypatch.setattr(h.cb, "_record_sdk_diagnostic", record)
    invoke, entries, outer_classifications = waterfall_call(h, monkeypatch)
    if failure_type == "base":
        with pytest.raises(DiagnosticInterruption) as caught:
            invoke()
        assert caught.value is failure
        assert outer_classifications == []
    else:
        result = invoke()
        assert result["ok"] is False and result["error"] == "sdk_terminal_error"
        assert result["text"] == "401 429 usage limit reached"
        assert len(result["provider_attempts"]) == 1
        assert outer_classifications == []
    assert finishes == [("exhausted", None)] and len(records) == 1
    assert len(entries) == len(h.providers) == 1
    assert h.classifications == h.cooling == h.sessions == []
