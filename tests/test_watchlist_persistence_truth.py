"""Watchlist canonical evidence must stay truthful under corruption and failed publication."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from portfolio import watchlist as W


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_WATCHLIST", tmp_path / "watchlist.jsonl", raising=False)
    monkeypatch.setattr(W, "_STATE", tmp_path / "watchlist_state.jsonl", raising=False)


def test_corrupt_append_log_is_failed_evidence_not_empty():
    raw = "{broken secret token=do-not-return\n"
    W._WATCHLIST.write_text(raw)

    with pytest.raises(Exception):
        W.all_rows()

    assert W._WATCHLIST.read_text() == raw


def test_append_refuses_to_overwrite_corrupt_log():
    raw = "{broken\n"
    W._WATCHLIST.write_text(raw)

    assert W.append("AAPL", "2026-09-18", "extended") is False
    assert W._WATCHLIST.read_text() == raw


def test_corrupt_state_snapshot_is_failed_evidence_not_empty():
    raw = "{broken secret token=do-not-return\n"
    W._STATE.write_text(raw)

    with pytest.raises(Exception):
        W.state_rows()

    assert W._STATE.read_text() == raw


def test_append_replace_failure_preserves_prior_complete_bytes(monkeypatch):
    assert W.append("OLD", "2026-09-17", "old") is True
    prior = W._WATCHLIST.read_text()
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == W._WATCHLIST:
            raise OSError("secret /Users/private/watchlist token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    assert W.append("NEW", "2026-09-18", "new") is False
    assert W._WATCHLIST.read_text() == prior
    assert not list(W._WATCHLIST.parent.glob(".*.tmp"))


def test_state_replace_failure_preserves_prior_complete_bytes(monkeypatch):
    assert W._write_state([{"ticker": "OLD", "state": "watch"}]) is True
    prior = W._STATE.read_text()
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == W._STATE:
            raise OSError("secret /Users/private/watch-state token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    assert W._write_state([{"ticker": "NEW", "state": "watch"}]) is False
    assert W._STATE.read_text() == prior
    assert not list(W._STATE.parent.glob(".*.tmp"))


def test_advance_rotation_does_not_report_unpersisted_state(monkeypatch):
    assert W.append_rotation("SMH", "2026-09-17", "rot:semis") is True
    monkeypatch.setattr(W, "_write_state", lambda _rows: False)

    out = W._advance_rotation("rot:semis", "2026-09-18", state="armed")

    assert out is None


def test_review_does_not_return_unpersisted_promotion(monkeypatch):
    assert W.append("AAPL", "2026-09-17", "extended", combined=80.0) is True
    monkeypatch.setattr(W, "_write_state", lambda _rows: False)

    out = W.review("2026-09-18", still_withheld=lambda _ticker: None)

    assert out == {"promote": [], "expired": [], "active": []}


def test_watchlist_lock_serializes_independent_processes():
    assert hasattr(W, "_watchlist_lock"), "canonical mutations require a cross-process lock"
    ctx = mp.get_context("fork")
    entered = ctx.Event()
    release = ctx.Event()
    acquired_after_release = ctx.Value("b", False)

    def holder():
        with W._watchlist_lock():
            entered.set()
            release.wait(timeout=5)

    def waiter():
        entered.wait(timeout=5)
        with W._watchlist_lock():
            acquired_after_release.value = release.is_set()

    first = ctx.Process(target=holder)
    second = ctx.Process(target=waiter)
    first.start()
    assert entered.wait(timeout=5)
    second.start()
    time.sleep(0.15)
    assert second.is_alive(), "second process should block on the canonical watchlist lock"

    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert first.exitcode == 0
    assert second.exitcode == 0
    assert bool(acquired_after_release.value)


def test_desk_watchlist_corrupt_state_is_unavailable():
    from app import web

    assert W.append("AAPL", "2026-09-17", "extended") is True
    W._STATE.write_text("{broken\n")

    body = json.loads(web.api_desk_watchlist().body)

    assert body["status"] == "unavailable"
    assert body["error"] == "desk_watchlist_unavailable"
    assert body["watchlist"] is None


def test_desk_watchlist_missing_state_remains_valid_success():
    from app import web

    assert W.append("AAPL", "2026-09-17", "extended") is True
    assert not W._STATE.exists()

    body = json.loads(web.api_desk_watchlist().body)

    assert "status" not in body
    assert body["watchlist"][0]["ticker"] == "AAPL"



def _unavailable_read(monkeypatch, target, failure):
    real_exists = Path.exists
    real_read = Path.read_text

    def exists(path):
        # Model the inaccessible-path result of newer pathlib versions without
        # changing permissions on any real application or user-owned path.
        return False if path == target else real_exists(path)

    def read(path, *args, **kwargs):
        if path == target:
            raise failure("private path /Users/secret token=do-not-return")
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", exists)
    monkeypatch.setattr(Path, "read_text", read)
    return real_read


@pytest.mark.parametrize("path_name,reader", [
    ("_WATCHLIST", "all_rows"), ("_STATE", "state_rows"),
])
@pytest.mark.parametrize("failure", [PermissionError, OSError])
def test_unavailable_canonical_read_is_not_misclassified_as_missing(
    monkeypatch, path_name, reader, failure,
):
    target = getattr(W, path_name)
    raw = '{"ticker": "KEEP", "state": "watch"}\n'
    target.write_text(raw)
    real_read = _unavailable_read(monkeypatch, target, failure)

    with pytest.raises(failure):
        getattr(W, reader)()

    assert real_read(target) == raw


@pytest.mark.parametrize("failure", [PermissionError, OSError])
def test_unavailable_append_log_cannot_be_replaced_with_a_new_row(monkeypatch, failure):
    raw = '{"ticker": "KEEP", "asof": "2026-09-17", "reason": "retained"}\n'
    W._WATCHLIST.write_text(raw)
    real_read = _unavailable_read(monkeypatch, W._WATCHLIST, failure)

    assert W.append("NEW", "2026-09-18", "candidate") is False
    assert real_read(W._WATCHLIST) == raw


@pytest.mark.parametrize("failure", [PermissionError, OSError])
def test_unavailable_state_cannot_be_replaced_by_rotation_enrollment(monkeypatch, failure):
    raw = '{"ticker": "KEEP", "state": "watch"}\n'
    W._STATE.write_text(raw)
    real_read = _unavailable_read(monkeypatch, W._STATE, failure)

    assert W.append_rotation("SMH", "2026-09-18", "rot:semis") is False
    assert real_read(W._STATE) == raw


@pytest.mark.parametrize("path_name", ["_WATCHLIST", "_STATE"])
@pytest.mark.parametrize("failure", [PermissionError, OSError])
def test_desk_watchlist_unavailable_read_has_fixed_response_and_type_only_log(
    monkeypatch, caplog, path_name, failure,
):
    from app import web

    target = getattr(W, path_name)
    raw = '{"ticker": "KEEP", "state": "watch"}\n'
    target.write_text(raw)
    real_read = _unavailable_read(monkeypatch, target, failure)

    with caplog.at_level("WARNING", logger="app.web"):
        body = json.loads(web.api_desk_watchlist().body)

    assert body == {
        "status": "unavailable", "book": "flagship",
        "watchlist": None, "error": "desk_watchlist_unavailable",
    }
    assert [record.getMessage() for record in caplog.records] == [
        "desk_watchlist_unavailable: " + failure.__name__,
    ]
    assert "secret" not in json.dumps(body) + caplog.text
    assert "do-not-return" not in json.dumps(body) + caplog.text
    assert real_read(target) == raw


def test_genuinely_missing_canonical_files_are_valid_empty_reads():
    from app import web

    assert W.all_rows() == []
    assert W.state_rows() == []
    assert json.loads(web.api_desk_watchlist().body) == {
        "book": "flagship", "watchlist": [],
    }


_JS_WATCHLIST_READ = r"""
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
const loader = section('window.loadDesk = function()', '\nfunction renderDeskPage()');
const renderer = section('function renderDeskWatchlist()', '\nfunction renderDeskScorecard()');
const empty = section('function _deskEmpty(', '\nwindow.loadDesk = function()');
const escape = section('\nvar esc = function(s) {', '\nvar pct = function(v)');
const host = {innerHTML: ''};
const requests = [];
const snapshots = [];
let renders = 0;
let complete;
const done = new Promise(resolve => { complete = resolve; });
const context = {
  window: {},
  document: {documentElement: {getAttribute: () => scenario.lang || 'en'}},
  _deskData: {watchlist: scenario.initial || null},
  E: id => id === 'desk-watchlist' ? host : null,
  t: key => key === 'desk.wl_empty' ? 'EMPTY_WATCHLIST' : key,
  fmtDate: value => String(value || ''),
  fetch: url => {
    requests.push(url);
    if (url !== '/api/desk/watchlist?book=flagship') {
      if (!Object.prototype.hasOwnProperty.call(scenario.siblings, url)) throw Error('unexpected sibling request');
      const value = scenario.siblings[url];
      return Promise.resolve({ok: true, json: () => Promise.resolve(value)});
    }
    if (scenario.mode === 'reject') return Promise.reject(Error('controlled read failure'));
    if (scenario.mode === 'http') {
      return Promise.resolve({ok: false, json: () => { throw Error('failed HTTP must not be parsed'); }});
    }
    if (scenario.mode === 'json') {
      return Promise.resolve({ok: true, json: () => Promise.reject(Error('controlled invalid JSON'))});
    }
    return Promise.resolve({ok: true, json: () => Promise.resolve(scenario.value)});
  },
};
context.renderDeskPage = () => {
  context.renderDeskWatchlist();
  snapshots.push(host.innerHTML);
  if (++renders === 2) complete();
};
vm.createContext(context);
vm.runInContext(escape + '\n' + empty + '\n' + loader + '\n' + renderer, context);
(async () => {
  const timeout = setTimeout(() => { throw Error('watchlist loader did not settle'); }, 2000);
  context.window.loadDesk();
  await done;
  clearTimeout(timeout);
  process.stdout.write(JSON.stringify({html: host.innerHTML, data: context._deskData, requests, renders, snapshots}));
})().catch(error => { process.stderr.write(String(error)); process.exitCode = 1; });
"""


_SIBLING_PAYLOADS = {
    "strategist": {"source": "/api/desk/strategist", "status": "building"},
    "decisions": {"source": "/api/desk/decisions", "status": "building", "decisions": []},
    "scorecard": {"source": "/api/desk/scorecard", "status": "building", "seats": []},
    "firm": {"source": "/api/desk/firm-exposure", "books": []},
    "macroRisk": {"source": "/api/desk/macro-risk", "status": "building"},
    "scheduler": {"source": "/api/scheduler", "jobs": []},
}


def _read_watchlist_ui(mode, value, *, initial=None, lang="en"):
    node = shutil.which("node")
    assert node is not None, "Watchlist JavaScript regression requires Node.js"
    path = Path(__file__).parents[1] / "app" / "static" / "index.html"
    result = subprocess.run(
        [node, "-e", _JS_WATCHLIST_READ,
         json.dumps({"mode": mode, "value": value, "initial": initial, "lang": lang,
                     "siblings": {row["source"]: row for row in _SIBLING_PAYLOADS.values()}}),
         str(path)],
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
        ("value", False, "unavailable"),
        ("value", {}, "unavailable"),
        ("value", {"watchlist": None}, "unavailable"),
        ("value", {"watchlist": {}}, "unavailable"),
        ("value", {"watchlist": "broken"}, "unavailable"),
        ("value", {"status": "unavailable", "watchlist": None,
                   "error": "desk_watchlist_unavailable"}, "unavailable"),
        ("value", {"status": "unavailable", "watchlist": []}, "unavailable"),
        ("value", {"book": "flagship", "watchlist": []}, "empty"),
        ("value", {"book": "flagship", "watchlist": [
            {"ticker": "<KEEP>", "asof": "2026-09-18", "reason": "<script>private</script>"},
        ]}, "rows"),
    ],
    ids=["fetch-rejected", "http-failed", "invalid-json", "null-json", "false-json",
         "missing-rows", "null-rows", "object-rows", "string-rows", "typed-unavailable",
         "unavailable-with-empty-array", "valid-empty", "escaped-row"],
)
def test_watchlist_actual_loader_and_renderer_preserve_read_truth(mode, value, expected):
    observed = _read_watchlist_ui(mode, value)
    assert observed["renders"] == 2
    assert observed["requests"].count("/api/desk/watchlist?book=flagship") == 1
    assert len(observed["requests"]) == 7
    # Compose valid independent panels through the actual Desk normalizer.
    for key, payload in _SIBLING_PAYLOADS.items():
        assert observed["data"][key] == payload

    rendered = observed["html"]
    if expected == "unavailable":
        assert "Watchlist unavailable." in rendered
        assert "EMPTY_WATCHLIST" not in rendered
        assert "Loading watchlist" not in rendered
    elif expected == "empty":
        assert "EMPTY_WATCHLIST" in rendered
        assert "unavailable" not in rendered
    else:
        assert "<table" in rendered and "&lt;KEEP&gt;" in rendered
        assert "&lt;script&gt;private&lt;/script&gt;" in rendered
        assert "<KEEP>" not in rendered and "<script>" not in rendered
        assert "EMPTY_WATCHLIST" not in rendered


def test_watchlist_initial_render_waits_for_a_completed_read():
    observed = _read_watchlist_ui("value", {"watchlist": []})
    first, final = observed["snapshots"]
    assert "Loading watchlist" in first
    assert "EMPTY_WATCHLIST" not in first
    assert "unavailable" not in first
    assert "EMPTY_WATCHLIST" in final


def test_watchlist_refresh_preserves_cached_rows_until_failed_read_completes():
    observed = _read_watchlist_ui(
        "reject", None, initial={"watchlist": [
            {"ticker": "CACHED", "asof": "2026-09-18", "reason": "prior read"},
        ]},
    )
    first, final = observed["snapshots"]
    assert "CACHED" in first and "<table" in first
    assert "Loading watchlist" not in first
    assert "Watchlist unavailable." in final
    assert "CACHED" not in final and "EMPTY_WATCHLIST" not in final


def test_watchlist_chinese_loading_and_failure_are_distinct_from_empty():
    observed = _read_watchlist_ui("reject", None, lang="zh")
    first, final = observed["snapshots"]
    assert "正在读取观察名单" in first and "EMPTY_WATCHLIST" not in first
    assert "观察名单暂不可用" in final and "EMPTY_WATCHLIST" not in final
