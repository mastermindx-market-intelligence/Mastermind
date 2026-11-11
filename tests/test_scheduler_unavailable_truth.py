"""Scheduler health outages stay distinct from a successful empty health read."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


def _body(resp):
    return json.loads(resp.body)


def test_scheduler_successful_empty_read_remains_available(monkeypatch):
    from app import web
    import app.scheduler as scheduler

    monkeypatch.setattr(scheduler, "scheduler_health", lambda: [])
    payload = _body(web.api_scheduler())
    assert payload == {"scheduler_status": "available", "jobs": []}


def test_scheduler_failure_is_unavailable_not_empty_and_secret_safe(monkeypatch, caplog):
    from app import web
    import app.scheduler as scheduler

    monkeypatch.setattr(
        scheduler,
        "scheduler_health",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/run_events.jsonl token=bad")),
    )
    response = web.api_scheduler()
    payload = _body(response)
    assert payload == {
        "scheduler_status": "unavailable",
        "jobs": None,
        "error": "scheduler_health_unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw
    assert "scheduler health read failed: RuntimeError" in caplog.text
    assert "secret" not in caplog.text and "/Users/private" not in caplog.text and "token=bad" not in caplog.text


def test_scheduler_ui_consumes_unavailable_before_no_jobs():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    start = html.index("function renderDeskScheduler()")
    end = html.index("function renderDeskStrategist()", start)
    block = html[start:end]

    assert "d.scheduler_status === 'unavailable'" in block
    assert "d.status === 'unavailable'" in block
    assert block.index("d.scheduler_status === 'unavailable'") < block.index("!(d.jobs || []).length")
    assert "Scheduler health unavailable" in block
    assert "No scheduler jobs reported" in block


def test_scheduler_successful_rows_are_preserved(monkeypatch):
    from app import web
    import app.scheduler as scheduler

    rows = [{"id": "daily_mark", "last_status": "ok", "next_run_time": None}]
    monkeypatch.setattr(scheduler, "scheduler_health", lambda: rows)
    assert _body(web.api_scheduler()) == {"scheduler_status": "available", "jobs": rows}


# Execute the real loader, renderer and escaping function from the production HTML.
# Only fetch and the DOM host are test fixtures; no scheduler/model/provider runs.
_JS_READ = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const scenario = JSON.parse(process.argv[1]);
const html = fs.readFileSync(process.argv[2], 'utf8');
function section(start, end) {
  const a = html.indexOf(start);
  if (a < 0 || html.indexOf(start, a + start.length) >= 0) throw Error('source anchor changed');
  const b = html.indexOf(end, a + start.length);
  if (b < 0) throw Error('source boundary changed');
  return html.slice(a, b);
}
const helpers = section('function _deskRecord(', '\nfunction _deskLoadingHtml()');
const loader = section('window.loadDesk = function()', '\nfunction renderDeskPage()');
const renderer = section('function renderDeskScheduler()', '\nfunction renderDeskStrategist()');
const escape = section('\nvar esc = function(s) {', '\nvar pct = function(v)');
const host = {innerHTML: ''};
const requests = [];
const snapshots = [];
let renders = 0;
let complete;
const done = new Promise(resolve => { complete = resolve; });
const context = {
  window: {},
  _deskData: {scheduler: null},
  E: id => id === 'desk-scheduler' ? host : null,
  fetch: url => {
    requests.push(url);
    if (url !== '/api/scheduler') {
      if (!Object.prototype.hasOwnProperty.call(scenario.siblings, url)) throw Error("unexpected sibling request");
      return Promise.resolve({ok: true, json: () => Promise.resolve(scenario.siblings[url])});
    }
    if (scenario.mode === 'reject') return Promise.reject(Error('controlled fetch rejection'));
    if (scenario.mode === 'http') {
      return Promise.resolve({ok: false, json: () => { throw Error('must not parse failed HTTP'); }});
    }
    if (scenario.mode === 'json') {
      return Promise.resolve({ok: true, json: () => Promise.reject(Error('controlled invalid JSON'))});
    }
    return Promise.resolve({ok: true, json: () => Promise.resolve(scenario.value)});
  },
};
context.renderDeskPage = () => {
  context.renderDeskScheduler();
  snapshots.push(host.innerHTML);
  if (++renders === 2) complete();
};
vm.createContext(context);
vm.runInContext(escape + '\n' + helpers + '\n' + loader + '\n' + renderer, context);
(async () => {
  const timeout = setTimeout(() => { throw Error('scheduler loader did not settle'); }, 2000);
  context.window.loadDesk();
  await done;
  clearTimeout(timeout);
  process.stdout.write(JSON.stringify({html: host.innerHTML, data: context._deskData, requests, renders, snapshots}));
})().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
"""


_SIBLING_PAYLOADS = {
    "strategist": {"source": "/api/desk/strategist", "status": "building"},
    "decisions": {"source": "/api/desk/decisions", "status": "building", "decisions": []},
    "watchlist": {"source": "/api/desk/watchlist?book=flagship", "watchlist": []},
    "scorecard": {"source": "/api/desk/scorecard", "status": "building", "seats": []},
    "firm": {"source": "/api/desk/firm-exposure", "books": []},
    "macroRisk": {"source": "/api/desk/macro-risk", "status": "building"},
}


def _read_scheduler_ui(mode, value):
    node = shutil.which("node")
    assert node is not None, "Scheduler JavaScript regression requires Node.js"
    path = Path(__file__).parents[1] / "app" / "static" / "index.html"
    result = subprocess.run(
        [node, "-e", _JS_READ, json.dumps({
            "mode": mode, "value": value,
            "siblings": {row["source"]: row for row in _SIBLING_PAYLOADS.values()},
        }), str(path)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "mode,value,expected",
    [
        ("reject", None, "unavailable"),
        ("http", None, "unavailable"),
        ("json", None, "unavailable"),
        ("value", None, "unavailable"),
        ("value", {}, "unavailable"),
        ("value", {"scheduler_status": "available", "jobs": None}, "unavailable"),
        ("value", {"scheduler_status": "unavailable", "jobs": None, "error": "scheduler_health_unavailable"}, "unavailable"),
        ("value", {"status": "unavailable", "jobs": []}, "unavailable"),
        ("value", {"scheduler_status": "available", "jobs": []}, "empty"),
        ("value", {"jobs": []}, "empty"),
        ("value", {"scheduler_status": "available", "jobs": [
            {"id": "<daily_mark>", "last_status": "ok", "last_reason": "done", "next_run_time": None}
        ]}, "rows"),
    ],
    ids=["fetch-rejected", "http-failed", "invalid-json", "null-json", "missing-jobs",
         "malformed-available", "health-unavailable", "shared-unavailable",
         "available-empty", "legacy-empty", "populated"],
)
def test_scheduler_actual_loader_and_renderer_keep_read_truth(mode, value, expected):
    observed = _read_scheduler_ui(mode, value)
    assert observed["renders"] == 2
    assert observed["requests"].count("/api/scheduler") == 1
    assert len(observed["requests"]) == 7
    # Valid sibling envelopes pass through the real normalizer unchanged.
    for key, payload in _SIBLING_PAYLOADS.items():
        assert observed["data"][key] == payload

    rendered = observed["html"]
    if expected == "unavailable":
        assert "Scheduler health unavailable" in rendered
        assert "No scheduler jobs reported" not in rendered
        data = observed["data"]["scheduler"]
        assert data.get("scheduler_status") == "unavailable" or data.get("status") == "unavailable"
    elif expected == "empty":
        assert "No scheduler jobs reported" in rendered
        assert "unavailable" not in rendered
    else:
        assert "<table" in rendered and "&lt;daily_mark&gt;" in rendered
        assert "<daily_mark>" not in rendered
        assert "No scheduler jobs reported" not in rendered
        assert "unavailable" not in rendered


def test_scheduler_initial_render_waits_for_read():
    observed = _read_scheduler_ui("value", {"scheduler_status": "available", "jobs": []})
    first, final = observed["snapshots"]
    assert "Loading scheduler health" in first
    assert "No scheduler jobs reported" not in first
    assert "unavailable" not in first
    assert "No scheduler jobs reported" in final
