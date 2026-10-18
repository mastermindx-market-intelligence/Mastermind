"""Causal bridge tests: actual dispatcher and handler, synthetic transport only.

The collector is an observational side channel. These tests compare provider
arguments, classification, cooling, legacy results and interruption identity.
They do not establish provider health, accepted effects or investment value.
"""
from __future__ import annotations

import asyncio
import copy
import importlib.metadata
import inspect
import json
import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace

import pytest


@dataclass
class ResultMessage:
    subtype: str = "success"
    is_error: bool = False
    result: str = "fixture answer"
    errors: list = field(default_factory=list)
    total_cost_usd: float = 0.25
    session_id: str = "fixture-session"
    usage: dict = field(default_factory=lambda: {"input_tokens": 11, "output_tokens": 7})


@dataclass
class TextBlock:
    text: str = "fixture text"


@dataclass
class ToolUseBlock:
    id: str = "fixture-tool"
    name: str = "mcp__bot__read"
    input: dict = field(default_factory=dict)


@dataclass
class ToolResultBlock:
    tool_use_id: str = "fixture-tool"
    content: str = "fixture tool result"
    is_error: bool = False


@dataclass
class AssistantMessage:
    content: list = field(default_factory=list)


@dataclass
class UserMessage:
    content: list = field(default_factory=list)


class StructuredError(RuntimeError):
    def __init__(self, message="ordinary stream termination", **fields):
        super().__init__(message)
        self.__dict__.update(fields)


class DiagnosticInterruption(BaseException):
    pass


class Harness:
    def __init__(self, monkeypatch):
        from brain import cli_bridge, key_rotor, runlog, sdk_diagnostics, thinking_log
        self.cb, self.kr, self.rl, self.diag = cli_bridge, key_rotor, runlog, sdk_diagnostics
        self.mp = monkeypatch
        self.timeline, self.rows, self.providers, self.classifications = [], [], [], []
        self.cooling, self.sessions, self.costs, self.versions = [], [], [], []
        self.plans = []
        self.option_error = None
        self.real_classify = key_rotor.classify_failure
        monkeypatch.setattr(cli_bridge, "_SDK", True)
        monkeypatch.setattr(cli_bridge, "cli_path", lambda: "/fixture/claude")
        monkeypatch.setattr(cli_bridge, "_cfg", lambda: {"reasoning": {"max_turns": 1, "research_max_turns": 2}})
        monkeypatch.setattr(cli_bridge, "_subscription_env", lambda name=None: {"FIXTURE_CANDIDATE": name or "legacy"})
        monkeypatch.setattr(cli_bridge, "_Options", self.options, raising=False)
        monkeypatch.setattr(cli_bridge, "_sdk_query", self.query, raising=False)
        monkeypatch.setattr(cli_bridge, "_via_subprocess", self.subprocess)
        monkeypatch.setattr(cli_bridge, "_record_cli_cost", lambda result, **kw: self.costs.append((copy.deepcopy(result), kw)))
        monkeypatch.setattr(key_rotor, "candidates", lambda: [])
        monkeypatch.setattr(key_rotor, "classify_failure", self.classify)
        monkeypatch.setattr(key_rotor, "mark_cooling", self.cool)
        monkeypatch.setattr(key_rotor, "record_session", lambda *a, **kw: self.sessions.append((a, kw)))
        monkeypatch.setattr(key_rotor, "all_cooling_info", lambda: {"all_cooling": True, "earliest_reset": "fixture"})
        monkeypatch.setattr(runlog, "start_run", lambda *a, **kw: "fixture-run")
        monkeypatch.setattr(runlog, "log_step", self.log)
        monkeypatch.setattr(runlog, "end_run", lambda *a, **kw: None)
        monkeypatch.setattr(thinking_log, "log_turn_async", lambda **kw: None)
        monkeypatch.setattr(importlib.metadata, "version", self.version)
        cli_module = ModuleType("claude_agent_sdk._cli_version")
        cli_module.__cli_version__ = "fixture-cli"
        monkeypatch.setitem(sys.modules, "claude_agent_sdk._cli_version", cli_module)

    def version(self, name):
        self.versions.append(name)
        return "fixture-sdk"

    def options(self, **kwargs):
        self.timeline.append(("options", kwargs["env"]["FIXTURE_CANDIDATE"]))
        assert "_diagnostic" not in kwargs
        assert "provider_diagnostic" not in kwargs
        assert kwargs["permission_mode"] == "dontAsk"
        if self.option_error is not None:
            raise self.option_error
        return SimpleNamespace(**kwargs)

    async def query(self, *, prompt, options):
        index = sum(p[0] == "sdk" for p in self.providers)
        self.providers.append(("sdk", prompt, copy.deepcopy(vars(options))))
        self.timeline.append(("sdk", options.env["FIXTURE_CANDIDATE"]))
        for item in self.plans[index]:
            if isinstance(item, BaseException):
                raise item
            if callable(item):
                effect = item()
                if inspect.isawaitable(effect):
                    await effect
            else:
                yield item

    async def subprocess(self, *args, **kwargs):
        self.providers.append(("subprocess", copy.deepcopy(args), copy.deepcopy(kwargs)))
        self.timeline.append(("subprocess", kwargs.get("env_name")))
        return {**args[10], "ok": True, "text": "fixture fallback", "backend": "cli",
                "cost_usd": None, "session_id": "fixture-subprocess", "usage": {}, "error": None}

    def classify(self, value, *args, **kwargs):
        self.classifications.append((value, args, dict(kwargs)))
        self.timeline.append(("classify", value, args, dict(kwargs)))
        return self.real_classify(value, *args, **kwargs)

    def cool(self, key, **kwargs):
        self.cooling.append((key, kwargs))
        self.timeline.append(("cool", key, kwargs))

    def log(self, run_id, kind, title, detail, **extra):
        self.timeline.append(("log", kind))
        self.rows.append({"run_id": run_id, "type": kind, "title": title, "detail": detail, **copy.deepcopy(extra)})

    def run(self, plans, *, arm=True, log_run=True, candidates=None):
        self.plans = plans
        return asyncio.run(self.cb._reason(
            "fixture prompt", model="fixture-model", role="analyst", arm=arm,
            allowed_tools=[], add_dirs=[], mcp_servers={}, cwd="/fixture/workspace",
            book="autonomous", log_run=log_run, _backend_override="cli",
            _oauth_candidates=[] if candidates is None else candidates,
        ))

    def diagnostics(self):
        return [row for row in self.rows if row["type"] == "provider_diagnostic"]

    def legacy(self, result):
        return {
            "result": copy.deepcopy(result),
            "providers": copy.deepcopy(self.providers),
            "classification": copy.deepcopy(self.classifications),
            "cooling": copy.deepcopy(self.cooling),
            "sessions": copy.deepcopy(self.sessions),
            "costs": copy.deepcopy(self.costs),
            "rows": [copy.deepcopy(r) for r in self.rows if r["type"] != "provider_diagnostic"],
            "timeline": [copy.deepcopy(e) for e in self.timeline if e != ("log", "provider_diagnostic")],
        }


@pytest.fixture
def harness(monkeypatch):
    return Harness(monkeypatch)


def envelope(harness):
    rows = harness.diagnostics()
    assert len(rows) == 1
    assert rows[0]["provider_diagnostic_capture"]["status"] == "available"
    return rows[0]["provider_diagnostic"]


def test_actual_handler_contradictory_terminal_keeps_legacy_result(harness):
    result = harness.run([[ResultMessage(subtype="success", is_error=True, result="contradictory answer")]])
    assert result["ok"] is True and result["text"] == "contradictory answer"
    diagnostic = envelope(harness)
    assert diagnostic["terminals"]["first"]["contradictory_success_with_is_error"] is True
    assert diagnostic["observation"]["query_entered_observed"] is True
    assert diagnostic["exit"]["end_state"] == "exhausted"
    assert diagnostic["identity"]["book"] == "autonomous"
    assert diagnostic["identity"]["candidate_ordinal"] == 0
    assert "provider_diagnostic" not in result


def test_query_entry_without_messages_is_partial_and_never_replay_permission(harness):
    result = harness.run([[StructuredError()]])
    diagnostic = envelope(harness)
    assert result["ok"] is False
    assert len(harness.providers) == 1
    assert diagnostic["observation"]["query_entered_observed"] is True
    assert diagnostic["observation"]["sdk_messages_observed"] == 0
    assert diagnostic["qualifications"]["effect_reconciliation"] == "not_performed"
    assert diagnostic["qualifications"]["completeness"] == "partial_abnormal_end_state"
    assert "zero_messages_observed_does_not_imply_safe_retry" in diagnostic["qualifications"]["notes"]


def test_options_failure_records_no_query_entry(harness):
    harness.option_error = ValueError("fixture options failure")
    result = harness.run([])
    diagnostic = envelope(harness)
    assert result["ok"] is False and harness.providers == []
    assert diagnostic["observation"]["query_entered_observed"] is False
    assert diagnostic["exit"]["end_state"] == "raised"


def test_actual_handler_counts_tool_messages_and_multiple_terminals(harness):
    result = harness.run([[
        AssistantMessage([TextBlock(), ToolUseBlock()]),
        UserMessage([ToolResultBlock(is_error=True)]),
        ResultMessage(result="first"), ResultMessage(result="last"),
    ]])
    diagnostic = envelope(harness)
    assert result["text"] == "last" and result["tools_used"] == ["mcp__bot__read"]
    assert diagnostic["observation"]["sdk_messages_observed"] == 4
    assert diagnostic["observation"]["tool_use_blocks_observed"] == 1
    assert diagnostic["observation"]["tool_result_blocks_observed"] == 1
    assert diagnostic["terminals"]["count"] == 2


CANDIDATES = [
    {"key_id": "fixture-a", "env_name": "FIXTURE_A"},
    {"key_id": "fixture-b", "env_name": "FIXTURE_B"},
]


def plans_for(case):
    if case == "success":
        return [[ResultMessage()]], True, []
    if case == "ordinary":
        return [[StructuredError()]], True, []
    if case == "fallback":
        return [[StructuredError()]], False, CANDIDATES
    if case == "rotation":
        return [[RuntimeError("disabled claude subscription access")], [ResultMessage()]], True, CANDIDATES
    if case == "diagnostic_trigger":
        return [[StructuredError(errors=["429 quota invalid token"], result="429 quota", is_error=True)]], True, CANDIDATES
    if case == "terminal_trigger":
        return [[ResultMessage(result="ordinary answer", errors=["429 quota invalid token"], is_error=True)]], True, CANDIDATES
    raise AssertionError(case)


@pytest.mark.parametrize("case", ["success", "ordinary", "fallback", "rotation", "diagnostic_trigger", "terminal_trigger"])
def test_diagnostics_preserve_all_legacy_control_and_result_fields(monkeypatch, case):
    observations = []
    for enabled in (True, False):
        with monkeypatch.context() as mp:
            h = Harness(mp)
            if not enabled:
                mp.setattr(h.cb, "_new_sdk_diagnostic", lambda *a: None)
                mp.setattr(h.cb, "_record_sdk_diagnostic", lambda *a: None)
            plans, arm, candidates = plans_for(case)
            result = h.run(plans, arm=arm, candidates=candidates)
            observations.append(h.legacy(result))
            if enabled and case == "rotation":
                diagnostics = h.diagnostics()
                assert [d["provider_diagnostic"]["identity"]["candidate_ordinal"] for d in diagnostics] == [0, 1]
                assert [d["provider_diagnostic"]["exit"]["end_state"] for d in diagnostics] == ["raised", "exhausted"]
                positions = [i for i, event in enumerate(h.timeline) if event == ("log", "provider_diagnostic")]
                cooling = [i for i, event in enumerate(h.timeline) if event[0] == "cool"]
                assert positions[0] < cooling[0] < positions[1]
            if enabled and "trigger" in case:
                assert "429" in json.dumps(h.diagnostics())
                assert h.cooling == [] and len(h.providers) == 1
    assert observations[0] == observations[1]


@pytest.mark.parametrize("after_terminal", [False, True])
@pytest.mark.parametrize("failure_kind", ["none", "ordinary_finish", "base_finish", "base_logger"])
def test_original_cancellation_survives_diagnostic_failures(harness, monkeypatch, after_terminal, failure_kind):
    cancelled = asyncio.CancelledError("original provider cancellation")
    if failure_kind.endswith("finish"):
        failure = RuntimeError("diagnostic failure") if failure_kind.startswith("ordinary") else DiagnosticInterruption("diagnostic failure")
        def finish(*a, **kw):
            raise failure
        monkeypatch.setattr(harness.diag.SDKInvocationDiagnostics, "finish", finish)
    elif failure_kind == "base_logger":
        original = harness.rl.log_step
        def log(*a, **kw):
            if a[1] == "provider_diagnostic":
                raise DiagnosticInterruption("diagnostic logger")
            return original(*a, **kw)
        monkeypatch.setattr(harness.rl, "log_step", log)
    plan = ([ResultMessage()] if after_terminal else []) + [cancelled]
    with pytest.raises(asyncio.CancelledError) as caught:
        harness.run([plan])
    assert caught.value is cancelled
    assert harness.cooling == [] and harness.classifications == []
    assert len(harness.providers) == 1
    if failure_kind == "none":
        diagnostic = envelope(harness)
        assert diagnostic["exit"]["end_state"] == "interrupted"
        assert diagnostic["terminals"]["count"] == int(after_terminal)


@pytest.mark.parametrize("arm", [True, False])
@pytest.mark.parametrize("failure_point", ["finish", "logger"])
def test_pending_ordinary_failure_keeps_baseline_outcome_when_diagnostics_raise_baseexception(
    harness, monkeypatch, arm, failure_point,
):
    if failure_point == "finish":
        def fail(*a, **kw):
            raise DiagnosticInterruption("must not replace pending provider failure")
        monkeypatch.setattr(harness.diag.SDKInvocationDiagnostics, "finish", fail)
    else:
        original = harness.rl.log_step
        def fail(*a, **kw):
            if a[1] == "provider_diagnostic":
                raise DiagnosticInterruption("must not replace pending provider failure")
            return original(*a, **kw)
        monkeypatch.setattr(harness.rl, "log_step", fail)
    result = harness.run([[StructuredError()]], arm=arm, candidates=CANDIDATES)
    assert result["ok"] is (not arm)
    assert harness.cooling == []
    assert [p[0] for p in harness.providers] == (["sdk"] if arm else ["sdk", "subprocess"])
    assert harness.classifications[0][0] == "StructuredError('ordinary stream termination')"


def test_original_repr_evaluations_and_classifier_input_are_frozen_before_diagnostics(harness):
    class CountedError(RuntimeError):
        count = 0
        def __repr__(self):
            self.count += 1
            return "classification first repr" if self.count == 1 else "outward second repr"
    error = CountedError("stored diagnostic text")
    result = harness.run([[error]], candidates=CANDIDATES)
    assert error.count == 2
    assert harness.classifications[0] == ("classification first repr", (), {})
    assert result["error"] == "outward second repr"
    diagnostic = envelope(harness)
    assert diagnostic["exit"]["exception_text"] == "stored diagnostic text"


@pytest.mark.parametrize("which", [1, 2])
def test_original_repr_failure_is_not_hidden_by_diagnostics(harness, which):
    original = LookupError("original repr failure")
    class BrokenRepr(RuntimeError):
        count = 0
        def __repr__(self):
            self.count += 1
            if self.count == which:
                raise original
            return "ordinary first repr"
    error = BrokenRepr("stored")
    with pytest.raises(LookupError) as caught:
        harness.run([[error]], candidates=CANDIDATES)
    assert caught.value is original and error.count == which
    assert harness.cooling == [] and len(harness.providers) == 1
    assert harness.diagnostics() == []


def test_observer_failure_after_terminal_has_machine_readable_partial_capture(harness, monkeypatch):
    original = harness.diag.SDKInvocationDiagnostics.observe_message
    seen = []
    def observe(self, message):
        seen.append(message)
        if len(seen) == 2:
            raise RuntimeError("fixture observer failure")
        return original(self, message)
    monkeypatch.setattr(harness.diag.SDKInvocationDiagnostics, "observe_message", observe)
    result = harness.run([[ResultMessage(), UserMessage([])]])
    assert result["ok"] is True
    row = harness.diagnostics()[0]
    assert row["provider_diagnostic_capture"] == {"status": "partial", "reason": "observer_call_failed"}
    assert row["provider_diagnostic"]["qualifications"]["completeness"] == "complete_limited_to_observed_sdk_messages"


@pytest.mark.parametrize("point", ["constructor", "finish", "logger", "version", "cli_version", "redactor"])
def test_ordinary_diagnostic_dependency_failures_do_not_change_success(harness, monkeypatch, point):
    def fail(*a, **kw):
        raise RuntimeError("fixture diagnostic dependency failure")
    if point == "constructor":
        monkeypatch.setattr(harness.diag, "SDKInvocationDiagnostics", fail)
    elif point == "finish":
        monkeypatch.setattr(harness.diag.SDKInvocationDiagnostics, "finish", fail)
    elif point == "logger":
        original = harness.rl.log_step
        def log(*a, **kw):
            if a[1] == "provider_diagnostic":
                return fail()
            return original(*a, **kw)
        monkeypatch.setattr(harness.rl, "log_step", log)
    elif point == "version":
        monkeypatch.setattr(importlib.metadata, "version", fail)
    elif point == "cli_version":
        monkeypatch.setitem(sys.modules, "claude_agent_sdk._cli_version", None)
    else:
        monkeypatch.setattr(harness.diag, "sanitize_external_text", fail)
    result = harness.run([[ResultMessage()]])
    assert result["ok"] is True and result["text"] == "fixture answer"
    assert len(harness.providers) == 1 and harness.cooling == []
    if point in {"constructor", "finish"}:
        assert harness.diagnostics()[0]["provider_diagnostic_capture"]["status"] == "unavailable"


@pytest.mark.parametrize("without_run", ["log_run_false", "start_run_failed", "sdk_absent"])
def test_absent_logging_or_sdk_does_not_discover_diagnostic_dependencies(harness, monkeypatch, without_run):
    if without_run == "start_run_failed":
        def fail(*a, **kw):
            raise OSError("fixture run log failure")
        monkeypatch.setattr(harness.rl, "start_run", fail)
    elif without_run == "sdk_absent":
        monkeypatch.setattr(harness.cb, "_SDK", False)
    result = harness.run([[ResultMessage()]], log_run=without_run != "log_run_false", arm=without_run != "sdk_absent")
    assert result["ok"] is True
    assert harness.versions == [] and harness.diagnostics() == []


def test_actual_runlog_writes_readable_bounded_envelope_with_distinct_ascii_row_size(harness, monkeypatch, tmp_path, record_property):
    from brain import runlog
    # Recover the real function from its source, not the fixture's recording spy.
    import importlib.util
    spec = importlib.util.spec_from_file_location("fixture_real_runlog", runlog.__file__)
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)
    real._RUNS_DIR = tmp_path
    real._INDEX = tmp_path / "index.jsonl"
    monkeypatch.setattr(runlog, "log_step", real.log_step)
    result = harness.run([[ResultMessage(
        result="供应链" * 1000, is_error=True, subtype="error",
        errors=["收益风险" * 1000, "市场观察" * 1000],
    )]])
    assert result["ok"] is True
    rows = (tmp_path / "fixture-run.jsonl").read_bytes().splitlines(keepends=True)
    raw = next(row for row in rows if json.loads(row)["type"] == "provider_diagnostic")
    row = json.loads(raw)
    diagnostic = row["provider_diagnostic"]
    canonical_size = len(json.dumps(diagnostic, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode())
    record_property("diagnostic_canonical_utf8_bytes", canonical_size)
    record_property("actual_ascii_runlog_row_bytes", len(raw))
    assert canonical_size <= 16384
    assert len(raw) > canonical_size
    assert row["provider_diagnostic_capture"]["status"] == "available"
    assert real.read_run("fixture-run")["steps"]


@pytest.mark.parametrize("diagnostic_failure", ["none", "ordinary", "base"])
def test_real_book_owner_keeps_persisted_submission_after_sdk_failure(
    monkeypatch, tmp_path, diagnostic_failure,
):
    """Real submission allocator, book caller, queue and decision owner retain authority."""
    from bot import autonomous, settle
    from brain import autonomous_mcp, cost_guard, decision_submission, portfolio_learning
    from portfolio import advisor_trade, firm_exposure, paper_account, registry, safety
    from control_plane import packet_gate

    outcomes = []
    for enabled in (True, False):
        with monkeypatch.context() as mp:
            h = Harness(mp)
            mp.setattr(registry, "_ROOT", tmp_path / ("enabled" if enabled else "disabled"))
            mp.setattr(cost_guard, "over_budget", lambda *a, **kw: False)
            mp.setattr(cost_guard, "record", lambda *a, **kw: None)
            mp.setattr(advisor_trade, "pending_proposals", lambda **kw: [])
            mp.setattr(paper_account, "_current_price", lambda ticker: {"AAPL": 200.0, "SPY": 500.0}.get(ticker))
            mp.setattr(decision_submission, "_instrument_identity", lambda ticker: {
                "kind": "common_stock", "status": "fixture_common_stock", "verified": True,
            })
            mp.setattr(settle, "is_open", lambda portfolio_id: False)
            mp.setattr(packet_gate, "process", lambda *a, **kw: None)
            mp.setattr(portfolio_learning, "attach_lesson_trace", lambda *a, **kw: {"ok": True, "cited_ids": []})
            mp.setattr(portfolio_learning, "record_application", lambda *a, **kw: {"ok": True, "recorded": False})
            mp.setattr(firm_exposure, "caps_enabled", lambda: False)
            mp.setattr(safety, "compute_safety", lambda *a, **kw: {})
            mp.setattr(safety, "gross_overlay", lambda *a, **kw: {"gross_mult": 1.0})
            mp.setattr(safety, "persist", lambda *a, **kw: None)
            if not enabled:
                mp.setattr(h.cb, "_new_sdk_diagnostic", lambda *a: None)
                mp.setattr(h.cb, "_record_sdk_diagnostic", lambda *a: None)
            elif diagnostic_failure != "none":
                failure = RuntimeError("diagnostic failure") if diagnostic_failure == "ordinary" else DiagnosticInterruption("diagnostic failure")
                def finish(*a, **kw):
                    raise failure
                mp.setattr(h.diag.SDKInvocationDiagnostics, "finish", finish)

            submitted = []
            async def accept_submission():
                tool_result = await autonomous_mcp.submit_book.handler({
                    "holdings": [{"ticker": "AAPL", "action": "add", "conviction": "high",
                                  "rationale": "fixture thesis", "evidence": ["fixture research"],
                                  "why_now": "fixture catalyst"}],
                    "summary": "fixture accepted thesis", "exit_decisions": [],
                })
                accepted = autonomous_mcp.read_submission("autonomous")
                assert accepted and len(accepted["holdings"]) == 1
                assert "SUBMISSION REJECTED" not in json.dumps(tool_result)
                submitted.append(copy.deepcopy(accepted))

            from claude_agent_sdk import _errors
            result_error = getattr(_errors, "ResultError", None)
            if result_error is None:
                pytest.skip("Actual ResultError compatibility proof requires an SDK exposing that type.")
            error = result_error("adapter cleanup failed", data={
                "type": "result", "subtype": "success", "is_error": True,
                "result": "diagnostic-only detail", "errors": ["429 quota diagnostic only"],
                "api_error_status": 503, "terminal_reason": "api_error", "stop_reason": "error",
            }, exit_code=1)
            def real_bridge(*a, **kw):
                return h.run([[accept_submission, error]], candidates=CANDIDATES)
            mp.setattr(autonomous, "_run_brain", real_bridge)
            out = autonomous.run_autonomous(asof="2026-10-16", armed=True)
            assert len(submitted) == 1 and len(h.providers) == 1 and h.cooling == []
            if enabled and diagnostic_failure == "none":
                diagnostic = envelope(h)
                assert diagnostic["exception"]["field_source"] == "sdk_result_error_data_allowlist"
                assert diagnostic["exception"]["contradictory_success_with_is_error"] is True
                assert diagnostic["exception"]["api_error_status"] == 503
                assert diagnostic["terminals"]["count"] == 0
            assert out["brain"]["ok"] is False
            assert out["decided"] is True and out["target_status"] == "queued"
            assert out["decision_effective"] is True and out["executed"] == []
            pending = json.loads(paper_account._pending_target_path("autonomous").read_text())
            expected = {row["ticker"]: row["weight"] for row in submitted[0]["holdings"]}
            assert pending["target"] == expected and expected
            row = autonomous.load_decisions()[0]
            assert row["decision_effective"] is True and row["target_status"] == "queued"
            assert row["summary"] == "fixture accepted thesis"
            assert "adapter cleanup failed" in row["error"]
            assert "diagnostic" not in row["error"]
            assert not paper_account._load_account("autonomous")["positions"]
            outcomes.append({
                "brain": out["brain"], "target": pending["target"],
                "target_sha256": row["target_sha256"], "effective_holdings": row["effective_holdings"],
                "target_status": row["target_status"], "error": row["error"],
            })
    assert outcomes[0] == outcomes[1]


def test_collector_import_failure_is_diagnostic_unavailability_not_provider_failure(harness, monkeypatch):
    import builtins
    original = builtins.__import__
    def guarded(name, *a, **kw):
        if name == "brain.sdk_diagnostics":
            raise ImportError("fixture collector unavailable")
        return original(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", guarded)
    result = harness.run([[ResultMessage()]])
    assert result["ok"] is True and len(harness.providers) == 1
    assert harness.versions == []
    assert harness.diagnostics()[0]["provider_diagnostic_capture"] == {
        "status": "unavailable", "reason": "collector_unavailable",
    }


def test_handler_failure_precedes_observer_and_preserves_original_error(harness, monkeypatch):
    sequence = []
    class HandlerError(RuntimeError):
        pass
    original_error = HandlerError("original SDK handler failure")
    class ResultMessage:
        @property
        def result(self):
            sequence.append("handler")
            raise original_error
    def observe(*a, **kw):
        sequence.append("observer")
        raise DiagnosticInterruption("secondary observer failure")
    monkeypatch.setattr(harness.diag.SDKInvocationDiagnostics, "observe_message", observe)
    result = harness.run([[ResultMessage()]])
    assert sequence == ["handler", "observer"]
    assert result["error"] == repr(original_error)
    assert len(harness.providers) == 1
    assert envelope(harness)["exit"]["exception_class"] == "HandlerError"


def test_successful_handler_observer_interruption_remains_an_interruption(harness, monkeypatch):
    """The library-created-object assumption does not promise arbitrary getter noninterference."""
    interruption = DiagnosticInterruption("observer interruption")
    def observe(*a, **kw):
        raise interruption
    monkeypatch.setattr(harness.diag.SDKInvocationDiagnostics, "observe_message", observe)
    with pytest.raises(DiagnosticInterruption) as caught:
        harness.run([[ResultMessage()]])
    assert caught.value is interruption
    assert len(harness.providers) == 1 and harness.cooling == []
    assert envelope(harness)["exit"]["end_state"] == "interrupted"


@pytest.mark.parametrize("with_terminal", [False, True])
def test_actual_sdk_types_cross_real_bridge_without_double_counting(harness, with_terminal):
    from claude_agent_sdk import ResultMessage as SDKResultMessage, _errors
    result_error = getattr(_errors, "ResultError", None)
    if result_error is None:
        pytest.skip("Actual ResultError compatibility proof requires an SDK exposing that type.")
    terminal = SDKResultMessage(
        subtype="success", duration_ms=1, duration_api_ms=1, is_error=True,
        num_turns=1, session_id="fixture-sdk", result="ordinary outward message",
        api_error_status=503, terminal_reason="api_error", stop_reason="error",
    )
    error = result_error("ordinary stream end", data={
        "subtype": "success", "is_error": True, "result": "diagnostic-only text",
        "errors": ["429 quota invalid token"], "api_error_status": True,
        "terminal_reason": "api_error", "stop_reason": "error",
    }, exit_code=1)
    assert not hasattr(error, "is_error")
    result = harness.run([([terminal] if with_terminal else []) + [error]], candidates=CANDIDATES)
    diagnostic = envelope(harness)
    assert result["ok"] is False and result["error"] == repr(error)
    assert harness.cooling == [] and len(harness.providers) == 1
    assert diagnostic["terminals"]["count"] == int(with_terminal)
    assert diagnostic["exception"]["is_error"] is True
    assert diagnostic["exception"]["api_error_status"] is None
    assert diagnostic["exception"]["contradictory_success_with_is_error"] is True
    assert diagnostic["exit"]["exit_code"] == 1
    if with_terminal:
        assert diagnostic["terminals"]["first"]["api_error_status"] == 503
