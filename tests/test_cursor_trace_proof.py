"""Regression proof: CLI success, Task calls and Plan interactions are not START."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.cursor_agent_mastermind import trace_proof


def event(**fields: object) -> str:
    return json.dumps(fields)


def test_success_exit_is_only_root_completion() -> None:
    rows = [
        event(type="system"),
        event(type="assistant", message={"content": [{"text": "fake success"}]}),
        event(type="result", subtype="success", is_error=False, result="text"),
    ]
    result = trace_proof.inspect_lines(rows)
    assert result["state"] == "ROOT_RESPONSE_SUCCEEDED_NOT_DELIVERY_PROOF"
    assert result["terminal_process_success_observed"] is True
    assert result["native_child_start_proven"] is False
    assert result["plan_accepted_proven"] is False


def test_task_started_then_hook_denied_does_not_prove_child() -> None:
    rows = [
        event(type="tool_call", subtype="started",
              tool_call={"taskToolCall": {"args": {"subagent_type": "mmx-repo-explorer"}}}),
        event(type="tool_call", subtype="completed",
              tool_call={"taskToolCall": {"result": {"error": {"error": "blocked by hook"}}}}),
        event(type="result", subtype="success", is_error=False, result="SUBAGENT_UNAVAILABLE"),
    ]
    result = trace_proof.inspect_lines(rows)
    assert result["state"] == "NATIVE_TASK_TOOL_REFUSED"
    assert result["native_task_call_started"] == 1
    assert result["native_task_refusals"] == 1
    assert result["native_child_start_proven"] is False
    assert result["actual_child_model_proven"] is False


def test_interactive_plan_query_outweighs_exit_zero() -> None:
    rows = [
        event(type="tool_call", subtype="started",
              tool_call={"createPlanToolCall": {"args": {}}}),
        event(type="tool_call", subtype="completed",
              tool_call={"createPlanToolCall": {"result": {}}}),
        event(type="interaction_query", query={"private": "do not copy"}),
        event(type="result", subtype="success", is_error=False, result="Drafting now"),
    ]
    result = trace_proof.inspect_lines(rows)
    assert result["state"] == "INTERACTION_REQUIRED_NO_ACCEPTED_PLAN"
    assert result["interaction_queries"] == 1
    assert result["create_plan_completed"] == 1
    assert result["plan_accepted_proven"] is False
    assert "private" not in json.dumps(result)


def test_invalid_events_and_budgets_are_not_authority() -> None:
    x = trace_proof.inspect_lines(["not json", event(type="unrecognized", worker_started=True)])
    assert x["invalid_or_unrecognized_lines"] == 2
    assert x["state"] == "NO_ACCEPTED_TERMINAL_RESULT"
    with pytest.raises(trace_proof.TraceRefused, match="line budget"):
        trace_proof.inspect_lines(["{}"] * (trace_proof.MAX_LINES + 1))


def test_only_bounded_regular_trace_may_be_loaded(tmp_path: Path) -> None:
    a = tmp_path / "trace.jsonl"
    a.write_text(event(type="result", subtype="success", is_error=False) + "\n")
    assert trace_proof.inspect_file(a)["terminal_process_success_observed"] is True
    b = tmp_path / "link.jsonl"
    b.symlink_to(a)
    with pytest.raises(trace_proof.TraceRefused, match="symlink"):
        trace_proof.inspect_file(b)


def test_no_raw_tool_args_or_prompts_in_report() -> None:
    rows = [
        event(type="tool_call", subtype="completed", tool_call={
            "readToolCall": {"args": {"path": "/Users/private/secret.jwt"}},
        }),
        event(type="result", subtype="success", is_error=False,
              result="user@example.com API_KEY=secret"),
    ]
    result = trace_proof.inspect_lines(rows)
    assert "readToolCall" in result["tool_names"]
    output = json.dumps(result)
    assert "secret.jwt" not in output and "user@example.com" not in output
