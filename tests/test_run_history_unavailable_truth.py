"""Run-history and evidence-trace failures must never masquerade as no runs/no steps."""
from __future__ import annotations

import json
from pathlib import Path


def test_runs_backend_failure_is_closed_and_unknown(monkeypatch):
    from app import web
    from brain import runlog

    monkeypatch.setattr(
        runlog, "list_runs",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/runs/index.jsonl")),
    )
    resp = web.api_runs()
    payload = json.loads(resp.body)

    assert resp.status_code >= 500
    assert payload["run_status"] == "unavailable"
    assert payload["error"] == "run_history_unavailable"
    assert payload["runs"] is None
    raw = json.dumps(payload)
    assert "secret" not in raw.lower()
    assert "/Users/private" not in raw


def test_runlog_backend_failure_is_closed_and_steps_unknown(monkeypatch):
    from app import web
    from brain import runlog

    monkeypatch.setattr(
        runlog, "read_run",
        lambda _rid=None: (_ for _ in ()).throw(RuntimeError("secret /Users/private/runs/run.jsonl")),
    )
    resp = web.api_runlog("run-123")
    payload = json.loads(resp.body)

    assert resp.status_code >= 500
    assert payload["trace_status"] == "unavailable"
    assert payload["error"] == "runlog_unavailable"
    assert payload["run_id"] == "run-123"
    assert payload["steps"] is None
    raw = json.dumps(payload)
    assert "secret" not in raw.lower()
    assert "/Users/private" not in raw


def test_runs_ui_distinguishes_loading_unavailable_and_empty_and_retries():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "var _runsStatus = 'loading'" in html
    assert "function _runsUnavailable()" in html
    start = html.index("function _ensureRuns()")
    end = html.index("function _ensureResearchPapers()", start)
    ensure = html[start:end]
    assert "_runsUnavailable()" in ensure
    assert "_runsLoaded = _runsStatus !== 'unavailable'" in ensure

    start = html.index("function renderRuns()")
    end = html.index("window.showMoreRuns", start)
    render = html[start:end]
    assert "_runsStatus === 'loading'" in render
    assert "_runsStatus === 'unavailable'" in render
    assert render.index("_runsStatus === 'unavailable'") < render.index("!runs.length")
    assert "Run history unavailable" in render


def test_both_trace_consumers_preserve_unavailable_before_no_steps():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    assert "function _runlogUnavailable(runId)" in html
    assert "function _runlogFetch(runId)" in html

    start = html.index("window.toggleRun = function")
    end = html.index("function renderSteps", start)
    toggle = html[start:end]
    assert "_runlogFetch(runId)" in toggle
    assert "data.trace_status === 'unavailable'" in toggle
    assert toggle.index("data.trace_status === 'unavailable'") < toggle.index("_runLogCache[runId] =")

    start = html.index("window.toggleDecReason = function")
    end = html.index("function _renderRunTrace", start)
    decision = html[start:end]
    assert "_runlogFetch(runId)" in decision

    start = html.index("function _renderRunTrace(run)")
    end = html.index("// ── SHADOW BOOKS", start)
    trace = html[start:end]
    assert "run.trace_status === 'unavailable'" in trace
    assert trace.index("run.trace_status === 'unavailable'") < trace.index("!steps.length")
    assert "evidence trace unavailable" in trace


def test_genuine_empty_run_history_remains_successfully_empty(monkeypatch):
    from app import web
    from brain import runlog

    monkeypatch.setattr(runlog, "list_runs", lambda: [])
    resp = web.api_runs()
    assert resp.status_code == 200
    assert json.loads(resp.body) == []


def test_genuine_zero_step_trace_remains_successfully_empty(monkeypatch):
    from app import web
    from brain import runlog

    monkeypatch.setattr(runlog, "read_run", lambda _rid=None: {"run_id": "run-0", "steps": []})
    resp = web.api_runlog("run-0")
    assert resp.status_code == 200
    payload = json.loads(resp.body)
    assert payload == {"run_id": "run-0", "steps": []}
    assert "trace_status" not in payload
