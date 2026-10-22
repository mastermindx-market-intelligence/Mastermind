"""Typed provider-failure evidence: capture in the handler, carry beside the legacy error.

The production incident (2026-10-10 → 10-21): the SDK raised
``Exception("Claude Code returned an error result: success")`` while the real
cause — ``AssistantMessage.error == "authentication_failed"`` and its 401 banner
text — rode the earlier message.  These tests pin the EVIDENCE-ONLY typed record:
legacy fields stay byte-identical, the record is never a routing input, and it
never carries response/prompt text or credential material.
"""
from __future__ import annotations

import asyncio
import copy
import json
from dataclasses import dataclass, field

import pytest

from test_sdk_diagnostic_bridge import Harness, ResultMessage, TextBlock, ToolUseBlock


@dataclass
class AssistantMessage:
    # The real SDK AssistantMessage carries `error` (e.g. "authentication_failed").
    content: list = field(default_factory=list)
    error: str | None = None


BANNER = "Failed to authenticate. API Error: 401 OAuth access token has been revoked."
# What the SDK actually raised (its repr() — the recorded legacy error — wraps it again).
SDK_RAISED = "Claude Code returned an error result: success"
LEGACY_ERROR = "Exception('Claude Code returned an error result: success')"

EXPECTED_KEYS = {
    "schema", "kind", "evidence", "source", "sdk_assistant_error",
    "sdk_result_subtype", "sdk_result_is_error", "api_error_status",
    "label_misleading", "tool_activity_observed", "provider", "key_id",
}


def plan_401(with_tool: bool = False):
    """The retained production failure sequence for one SDK candidate."""
    plan: list = []
    if with_tool:
        plan.append(AssistantMessage(content=[ToolUseBlock()]))
    plan += [
        AssistantMessage(content=[TextBlock(BANNER)], error="authentication_failed"),
        ResultMessage(subtype="success", is_error=True, result="", errors=[]),
        Exception(SDK_RAISED),
    ]
    return plan


# --------------------------------------------------------------------------- #
# 1-3: handler capture through the real _reason
# --------------------------------------------------------------------------- #
def test_armed_exception_keeps_legacy_error_and_carries_evidence(monkeypatch):
    h = Harness(monkeypatch)
    result = h.run([plan_401()], arm=True)
    assert result["error"] == LEGACY_ERROR
    assert result["backend"] == "none"
    assert result["ok"] is False
    assert result["provider_failure_evidence"] == {
        "tool_activity_observed": False,
        "assistant_error": "authentication_failed",
        "result_is_error": True,
        "result_subtype": "success",
    }


def test_tool_activity_before_the_failure_is_observed(monkeypatch):
    h = Harness(monkeypatch)
    result = h.run([plan_401(with_tool=True)], arm=True)
    assert result["provider_failure_evidence"]["tool_activity_observed"] is True
    assert result["provider_failure_evidence"]["assistant_error"] == "authentication_failed"


def test_terminal_error_path_attaches_evidence_without_a_raise(monkeypatch):
    h = Harness(monkeypatch)
    plan = [
        AssistantMessage(content=[], error="rate_limit"),
        ResultMessage(subtype="success", is_error=True, result="x"),
    ]
    result = h.run([plan], arm=True)
    assert result["error"] == "sdk_terminal_error"
    assert result["ok"] is False
    assert result["provider_failure_evidence"]["assistant_error"] == "rate_limit"
    assert result["provider_failure_evidence"]["result_is_error"] is True


# --------------------------------------------------------------------------- #
# 4: diagnostics on/off equality still holds
# --------------------------------------------------------------------------- #
def test_diagnostics_disabled_leaves_legacy_and_evidence_paths_equal(monkeypatch):
    observations = []
    for enabled in (True, False):
        with monkeypatch.context() as mp:
            h = Harness(mp)
            if not enabled:
                mp.setattr(h.cb, "_new_sdk_diagnostic", lambda *a: None)
                mp.setattr(h.cb, "_record_sdk_diagnostic", lambda *a: None)
            result = h.run([plan_401()], arm=True)
            observations.append(h.legacy(result))
    assert observations[0] == observations[1]


# --------------------------------------------------------------------------- #
# 5: unknown / forged assistant-error literals are not recorded
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("forged", ["something_else", 401, None, ["authentication_failed"]])
def test_unknown_or_forged_assistant_error_never_enters_the_evidence(monkeypatch, forged):
    h = Harness(monkeypatch)
    plan = [
        AssistantMessage(content=[], error=forged),
        ResultMessage(subtype="success", is_error=True, result="", errors=[]),
        Exception(SDK_RAISED),
    ]
    result = h.run([plan], arm=True)
    assert "assistant_error" not in result["provider_failure_evidence"]


# --------------------------------------------------------------------------- #
# 6: evidence never carries text
# --------------------------------------------------------------------------- #
def test_evidence_never_carries_response_or_exception_text(monkeypatch):
    h = Harness(monkeypatch)
    result = h.run([plan_401()], arm=True)
    dumped = json.dumps(result["provider_failure_evidence"])
    assert "401" not in dumped
    assert "revoked" not in dumped
    assert BANNER not in dumped
    assert "Exception" not in dumped


# --------------------------------------------------------------------------- #
# 7-8: waterfall carries the typed record without changing any decision
# --------------------------------------------------------------------------- #
def case1_result() -> dict:
    return {
        "model": "fixture-model", "role": "analyst", "armed": True,
        "ok": False, "backend": "none", "text": None,
        "error": LEGACY_ERROR,
        "provider_failure_evidence": {
            "tool_activity_observed": False,
            "assistant_error": "authentication_failed",
            "result_is_error": True,
            "result_subtype": "success",
        },
    }


def _oauth_rung(key_id: str) -> dict:
    return {"provider": "oauth", "key_id": key_id,
            "env_name": f"CLAUDE_CODE_OAUTH_TOKEN_{key_id[-1]}", "cooling": False}


def _patch_waterfall(monkeypatch, rungs, results):
    from brain import cli_bridge
    from brain import provider_waterfall as pw
    from test_provider_waterfall import _SharedAuth, _SharedKeyPool

    monkeypatch.setattr(pw, "_shared_modules", lambda: (_SharedAuth, _SharedKeyPool()))
    monkeypatch.setattr(pw, "provider_rungs", lambda _role: rungs)
    calls: list = []

    async def fake_reason(_prompt, **kwargs):
        calls.append(kwargs.get("_backend_override"))
        return copy.deepcopy(results[len(calls) - 1])

    monkeypatch.setattr(cli_bridge, "_reason", fake_reason)
    return pw, calls


def test_waterfall_types_credential_and_leaves_legacy_fields_untouched(monkeypatch):
    pw, calls = _patch_waterfall(
        monkeypatch, [_oauth_rung("claude_code_oauth_1")], [case1_result()])
    out = asyncio.run(pw.reason("test", role="pm"))

    failure = out["provider_failure"]
    assert failure["kind"] == "credential"
    assert failure["evidence"] == "sdk_assistant_error:authentication_failed"
    assert failure["label_misleading"] is True
    assert failure["tool_activity_observed"] is False
    assert failure["provider"] == "oauth"
    assert failure["key_id"] == "claude_code_oauth_1"
    assert out["error"] == LEGACY_ERROR
    assert out["provider_attempts"] == [
        {"provider": "oauth", "key_id": "claude_code_oauth_1", "ok": False, "cooling": False}]
    assert out["provider_failures"] == [out["provider_failure"]]
    assert calls == ["cli"]


def test_typed_record_never_authorizes_failover(monkeypatch):
    # Codex first: a non-provider failure returns immediately…
    codex_result = {"ok": False, "text": None, "error": "codex CLI not installed",
                    "backend": "codex"}
    pw, calls = _patch_waterfall(
        monkeypatch,
        [{"provider": "codex", "key_id": "codex_account", "env_name": None,
          "cooling": False},
         _oauth_rung("claude_code_oauth_1")],
        [codex_result, case1_result()],
    )
    from brain import provider_waterfall as _pw_module
    monkeypatch.setattr(_pw_module, "_note_codex", lambda *_args, **_kwargs: None)
    out = asyncio.run(pw.reason("test", role="pm"))
    assert calls == ["codex"]
    assert out["error"] == "codex CLI not installed"
    assert out["provider_failure"]["kind"] == "unclassified"

    # …and separately: two OAuth rungs, first types credential — still one call.
    pw2, calls2 = _patch_waterfall(
        monkeypatch,
        [_oauth_rung("claude_code_oauth_1"), _oauth_rung("claude_code_oauth_5")],
        [case1_result(), case1_result()],
    )
    out2 = asyncio.run(pw2.reason("test", role="pm"))
    assert calls2 == ["cli"]
    assert out2["provider_failure"]["kind"] == "credential"
    assert out2["provider_failure"]["evidence"] == "sdk_assistant_error:authentication_failed"
    assert len(out2["provider_attempts"]) == 1
    assert out2["provider_failures"] == [out2["provider_failure"]]


# --------------------------------------------------------------------------- #
# 9: classify unit table
# --------------------------------------------------------------------------- #
def test_classify_unit_table():
    from brain import codex_bridge, provider_failure

    rec = provider_failure.classify(
        error="You've hit your weekly limit · resets Oct 18, 7pm (UTC)")
    assert rec["kind"] == "quota" and rec["evidence"] == "weekly limit"
    assert rec["source"] == "error_text"

    rec = provider_failure.classify(error=BANNER)
    assert rec["kind"] == "credential" and rec["evidence"] == "401"

    rec = provider_failure.classify(error="elapsed 4012s")
    assert rec["kind"] == "unclassified" and rec["evidence"] is None

    rec = provider_failure.classify(error=f"Exception('Claude Code returned an error result: success')")
    assert rec["kind"] == "unclassified" and rec["label_misleading"] is True

    rec = provider_failure.classify(evidence={"api_error_status": 529})
    assert rec["kind"] == "availability" and rec["evidence"] == "api_error_status:529"
    assert rec["api_error_status"] == 529 and rec["source"] == "api_error_status"

    rec = provider_failure.classify(evidence={"api_error_status": True})
    assert rec["kind"] == "unclassified" and rec["api_error_status"] is None

    rec = provider_failure.classify(evidence={"result_subtype": "error_max_turns"})
    assert rec["kind"] == "deadline" and rec["source"] == "sdk_result_subtype"

    rec = provider_failure.classify(error=codex_bridge.WRITE_TOOL_FAILURE_ERROR)
    assert rec["kind"] == "tool_contract" and rec["evidence"] == "failed write tool call"

    rec = provider_failure.classify()
    assert rec["kind"] == "unclassified" and rec["label_misleading"] is False


def test_classify_records_always_have_exactly_the_documented_shape():
    from brain import provider_failure

    cases = [
        {},
        {"error": "401 revoked"},
        {"error": "overloaded", "provider": "oauth", "key_id": "k"},
        {"evidence": {"assistant_error": "authentication_failed",
                      "result_is_error": True, "result_subtype": "success",
                      "api_error_status": 401, "tool_activity_observed": True},
         "error": "x", "provider": "oauth", "key_id": "k", "tools_used": ["Read"]},
        {"evidence": None, "error": None},
        {"evidence": "not-a-dict", "error": 42, "provider": 7, "key_id": ["k"],
         "tools_used": "not-a-list"},
    ]
    for kwargs in cases:
        rec = provider_failure.classify(**kwargs)
        assert set(rec) == EXPECTED_KEYS, kwargs
        assert rec["schema"] == "mastermind.bot.provider_failure.v1"
        assert rec["kind"] in provider_failure.KINDS
        assert rec["evidence"] is None or (
            isinstance(rec["evidence"], str) and len(rec["evidence"]) <= 80)


def test_classify_survives_an_error_whose_str_raises():
    from brain import provider_failure

    class BoomStr:
        def __str__(self):
            raise RuntimeError("no string form")

    rec = provider_failure.classify(error=BoomStr())
    assert rec["kind"] == "unclassified"
    assert set(rec) == EXPECTED_KEYS


# --------------------------------------------------------------------------- #
# 10: no-rungs fallback still types availability
# --------------------------------------------------------------------------- #
def test_no_rungs_fallback_types_availability_without_changing_error(monkeypatch):
    from brain import provider_waterfall as pw

    monkeypatch.setattr(pw, "provider_rungs", lambda _role: [])
    out = asyncio.run(pw.reason("test", role="pm"))
    assert out["error"] == "no shared Codex or Claude OAuth provider is available"
    assert out["provider_failure"]["kind"] == "availability"
    assert out["provider_failure"]["evidence"] == (
        "no shared codex or claude oauth provider is available")
    assert out["provider_failures"] == []


# --------------------------------------------------------------------------- #
# 11: decision rows carry the record for all three books
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("module_name, book_id", [
    ("bot.autonomous", "autonomous"),
    ("bot.china", "china"),
    ("bot.hk", "hk"),
])
def test_decision_rows_carry_the_typed_record(tmp_path, monkeypatch, module_name, book_id):
    import importlib

    from brain import provider_failure
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    book = importlib.import_module(module_name)

    record = provider_failure.classify(
        error=LEGACY_ERROR,
        evidence={"tool_activity_observed": False,
                  "assistant_error": "authentication_failed",
                  "result_is_error": True, "result_subtype": "success"},
        provider="oauth", key_id="claude_code_oauth_1",
    )
    brain = {"error": LEGACY_ERROR, "provider_failure": record}
    book._append_decision_log("2026-10-20", None, [], [], brain,
                              target_status="rejected_no_submission")

    path = registry.data_dir(book_id) / "decisions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    row = next(r for r in rows if r.get("asof") == "2026-10-20")
    assert row["provider_failure"] == record
    assert row["error"] == LEGACY_ERROR

    # A brain dict without the key records None, never a fabricated record.
    book._append_decision_log("2026-10-21", None, [], [], {"error": "later failure"},
                              target_status="rejected_no_submission")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    row = next(r for r in rows if r.get("asof") == "2026-10-21")
    assert row["provider_failure"] is None


# --------------------------------------------------------------------------- #
# 12: source guard — the typed record is never read below its append
# --------------------------------------------------------------------------- #
def test_waterfall_source_guard_typed_record_never_read_in_control_flow():
    import re
    from pathlib import Path

    from brain import provider_waterfall

    src = Path(provider_waterfall.__file__).read_text(encoding="utf-8")
    start = src.index("failures.append(")
    tail = src[start:]
    typed_record = re.compile(r"\bfailure\b|\bprovider_failure\b")
    for line in tail.splitlines():
        stripped = line.strip()
        if stripped.startswith(("if ", "elif ", "continue")):
            assert not typed_record.search(stripped), (
                f"typed record read in a control-flow condition: {stripped!r}")
