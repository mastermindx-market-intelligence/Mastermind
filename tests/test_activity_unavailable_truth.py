"""Brain Log activity preserves partial/unavailable evidence truth."""
from __future__ import annotations

import json
from pathlib import Path


def _body(resp):
    return json.loads(resp.body)


def test_successful_empty_activity_keeps_legacy_list_contract(tmp_path, monkeypatch):
    from app import web

    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    payload = _body(web.api_activity())
    assert payload == []


def test_successful_activity_events_keep_required_shape(tmp_path, monkeypatch):
    from app import web

    book = tmp_path / "portfolio"
    book.mkdir(parents=True)
    (book / "latest.json").write_text(json.dumps({
        "as_of": "2026-09-17",
        "gross": 0.25,
        "cash": 0.75,
        "regime": {"quad_name": "Goldilocks"},
        "decisions": [{"subject": "AAPL", "lean": "buy", "thesis": "test", "logged_at": "2026-09-17T12:00:00Z"}],
    }))
    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    payload = _body(web.api_activity())
    assert isinstance(payload, list) and payload
    assert {row["kind"] for row in payload} >= {"decision", "run"}
    for row in payload:
        for field in ("ts", "kind", "title", "detail"):
            assert field in row


def test_one_source_failure_is_partial_not_silently_omitted(tmp_path, monkeypatch):
    from app import web

    book = tmp_path / "portfolio"
    book.mkdir(parents=True)
    (book / "latest.json").write_text(json.dumps({
        "as_of": "2026-09-17", "gross": 0.2, "cash": 0.8,
        "decisions": [{"subject": "AAPL", "lean": "watch", "thesis": "healthy source"}],
    }))

    calls = {"n": 0}
    def data_root():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("secret /Users/private/positions_ledger.json")
        return tmp_path

    monkeypatch.setattr(web, "_data", data_root)
    response = web.api_activity()
    payload = _body(response)

    assert payload["activity_status"] == "partial"
    assert isinstance(payload["events"], list) and payload["events"]
    assert {row["kind"] for row in payload["events"]} >= {"decision", "run"}
    assert payload["failed_sources"] == ["trades"]
    assert "secret" not in response.body.decode()
    assert "/Users/private" not in response.body.decode()


def test_all_source_failures_are_unavailable_not_empty(monkeypatch):
    from app import web

    monkeypatch.setattr(
        web,
        "_data",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/activity")),
    )
    response = web.api_activity()
    payload = _body(response)

    assert payload["activity_status"] == "unavailable"
    assert payload["events"] is None
    assert payload["failed_sources"] == ["trades", "decisions", "research"]
    assert "secret" not in response.body.decode()
    assert "/Users/private" not in response.body.decode()


def test_activity_client_consumes_unavailable_and_partial_before_empty():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "function _activityFetch()" in html
    assert "function _applyActivityFeed(data)" in html
    assert "window.retryBrainActivity = function()" in html

    render_start = html.index("function renderBrainLog()")
    render_end = html.index("// ── RESEARCH FEED", render_start)
    render = html[render_start:render_end]
    assert "_activityStatus === 'loading'" in render
    assert "_activityStatus === 'unavailable'" in render
    assert "_activityStatus === 'partial'" in render
    assert render.index("_activityStatus === 'unavailable'") < render.index("!_activity.length")
    assert render.index("_activityStatus === 'partial'") < render.index("!_activity.length")
    assert "retryBrainActivity()" in render

    hydrate_start = html.index("function _hydrateShared()")
    hydrate_end = html.index("async function fetchAll", hydrate_start)
    hydrate = html[hydrate_start:hydrate_end]
    assert "_activityFetch()" in hydrate
    assert "_applyActivityFeed" in hydrate
    assert "fetch('/api/activity').then(function(r)  { return r.ok ? r.json() : [];" not in hydrate


import asyncio
from datetime import date
from functools import lru_cache
import shutil
import subprocess

import pytest


_SECRET = "secret /Users/private/activity token=hidden"


@pytest.fixture(autouse=True)
def _private_activity_root(tmp_path, monkeypatch):
    from app import web

    monkeypatch.setattr(web, "_data", lambda: tmp_path)
    monkeypatch.setattr(web, "_cached_zh", lambda text: None)
    return tmp_path


def _healthy_sources(root):
    directory = root / "portfolio"
    directory.mkdir(parents=True)
    notes = root / "research" / "notes"
    notes.mkdir(parents=True)
    today = date.today().isoformat()
    ledger = directory / "positions_ledger.json"
    latest = directory / "latest.json"
    note = notes / "note.md"
    ledger.write_text(json.dumps({"core:AAPL": {
        "ticker": "AAPL", "sleeve": "core", "still_open": True,
        "history": [{"ts": today + "T11:00:00Z", "event": "open", "weight": 0.1}],
    }}))
    latest.write_text(json.dumps({
        "as_of": today, "gross": 0.2, "cash": 0.8, "regime": {"quad_name": "Goldilocks"},
        "decisions": [{"subject": "MSFT", "lean": "watch", "thesis": "Healthy decision",
                       "logged_at": today + "T12:00:00Z"}],
    }))
    note.write_text("# Healthy research\n*tickers: NVDA · " + today + "T13:00:00Z*\n\nHealthy body\n")
    return {"trades": ledger, "decisions": latest, "research": notes, "note": note}


def _assert_partial(response, family, *, empty=False):
    payload = _body(response)
    assert response.status_code == 200
    assert isinstance(payload, dict), "failed evidence must not become a successful legacy list"
    assert payload["activity_status"] == "partial"
    assert payload["failed_sources"] == [family]
    assert isinstance(payload["events"], list)
    kinds = {"trades": {"trade"}, "decisions": {"decision", "run"}, "research": {"research"}}
    assert not ({row["kind"] for row in payload["events"]} & kinds[family])
    assert bool(payload["events"]) is not empty
    assert _SECRET not in response.body.decode()
    assert "/Users/private" not in response.body.decode()
    return payload


@pytest.mark.parametrize("family,mode", [
    ("trades", "json"), ("trades", "utf8"), ("trades", "shape"),
    ("trades", "history_shape"),
    ("decisions", "json"), ("decisions", "utf8"), ("decisions", "shape"),
    ("decisions", "decisions_shape"), ("research", "utf8"),
])
def test_actual_source_bytes_failure_preserves_other_families(tmp_path, family, mode):
    from app import web

    paths = _healthy_sources(tmp_path)
    path = paths["note"] if family == "research" else paths[family]
    if mode == "utf8":
        path.write_bytes(b"\xff")
    elif mode == "json":
        path.write_text("{")
    elif mode == "shape":
        path.write_text("[]")
    elif mode == "history_shape":
        path.write_text('{"core:AAPL":{"history":{}}}')
    else:
        path.write_text('{"decisions":{}}')
    _assert_partial(web.api_activity(), family)


@pytest.mark.parametrize("family,mode", [
    ("trades", "dangling_leaf"), ("decisions", "read_denied"),
    ("decisions", "probe_denied"), ("research", "dangling_directory"),
    ("research", "not_directory"), ("research", "enumeration_denied"),
    ("research", "enumeration_partial"), ("research", "selected_missing"),
    ("research", "note_stat_denied"), ("trades", "appeared_after_missing"),
])
def test_false_absence_and_note_read_failures_are_partial(tmp_path, monkeypatch, family, mode):
    from app import web

    paths = _healthy_sources(tmp_path)
    target = paths[family]
    if mode == "dangling_leaf":
        target.unlink()
        target.symlink_to(tmp_path / "absent.json")
    elif mode in ("dangling_directory", "not_directory"):
        paths["note"].unlink()
        target.rmdir()
        if mode == "dangling_directory":
            target.symlink_to(tmp_path / "absent-notes", target_is_directory=True)
        else:
            target.write_text("not a directory")
    elif mode in ("enumeration_denied", "enumeration_partial"):
        original = Path.iterdir

        def iterdir(self):
            if self == target:
                if mode == "enumeration_partial":
                    yield paths["note"]
                raise PermissionError(_SECRET)
            yield from original(self)

        monkeypatch.setattr(Path, "iterdir", iterdir)
    elif mode == "probe_denied":
        target.unlink()
        original = Path.lstat

        def lstat(self, *args, **kwargs):
            if self == target:
                raise PermissionError(_SECRET)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "lstat", lstat)
    elif mode == "note_stat_denied":
        paths["note"].write_text("# Undated note\n\nBody\n")
        original = Path.stat

        def stat(self, *args, **kwargs):
            if self == paths["note"]:
                raise PermissionError(_SECRET)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", stat)
    else:
        original = Path.read_text
        if mode == "appeared_after_missing":
            target.unlink()

        def read_text(self, *args, **kwargs):
            if mode == "selected_missing" and self == paths["note"]:
                self.unlink()
                return original(self, *args, **kwargs)
            if self == target and mode == "read_denied":
                raise PermissionError(_SECRET)
            if self == target and mode == "appeared_after_missing":
                self.write_text("{}")
                raise FileNotFoundError(_SECRET)
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", read_text)
    _assert_partial(web.api_activity(), family)


@pytest.mark.parametrize("mode", ["parent_file", "symlink_parent"])
def test_non_directory_or_symlink_absence_does_not_hide_two_failed_families(tmp_path, mode):
    from app import web

    paths = _healthy_sources(tmp_path)
    paths["trades"].unlink()
    paths["decisions"].unlink()
    parent = tmp_path / "portfolio"
    parent.rmdir()
    if mode == "parent_file":
        parent.write_text("not a directory")
    else:
        actual = tmp_path / "actual-portfolio"
        actual.mkdir()
        parent.symlink_to(actual, target_is_directory=True)
    payload = _body(web.api_activity())
    assert isinstance(payload, dict)
    assert payload["activity_status"] == "partial"
    assert payload["failed_sources"] == ["trades", "decisions"]
    assert {row["kind"] for row in payload["events"]} == {"research"}


@pytest.mark.parametrize("family", ["trades", "decisions", "research"])
def test_failed_family_discards_rows_already_read(tmp_path, family):
    from app import web

    paths = _healthy_sources(tmp_path)
    if family == "trades":
        rows = json.loads(paths[family].read_text())
        rows["core:AAPL"]["history"].append(None)
        paths[family].write_text(json.dumps(rows))
    elif family == "decisions":
        rows = json.loads(paths[family].read_text())
        rows["decisions"].append(None)
        paths[family].write_text(json.dumps(rows))
    else:
        (paths["research"] / "second.md").write_bytes(b"\xff")
    _assert_partial(web.api_activity(), family)


@pytest.mark.parametrize("field", ["trade_ts", "decision_ts", "as_of"])
@pytest.mark.parametrize("value", [0, False, 7, []])
def test_invalid_timestamp_is_caught_inside_its_family(tmp_path, field, value):
    from app import web

    paths = _healthy_sources(tmp_path)
    family = "trades" if field == "trade_ts" else "decisions"
    data = json.loads(paths[family].read_text())
    if field == "trade_ts":
        data["core:AAPL"]["history"][0]["ts"] = value
    elif field == "decision_ts":
        data["decisions"][0]["logged_at"] = value
    else:
        data["as_of"] = value
    paths[family].write_text(json.dumps(data))
    _assert_partial(web.api_activity(), family)


@pytest.mark.parametrize("family", ["trades", "decisions"])
def test_empty_json_bytes_are_a_read_failure(tmp_path, family):
    from app import web

    paths = _healthy_sources(tmp_path)
    paths[family].write_bytes(b"")
    _assert_partial(web.api_activity(), family)


@pytest.mark.parametrize("failed_count", [1, 2])
def test_partial_with_no_surviving_rows_stays_partial(tmp_path, failed_count):
    from app import web

    directory = tmp_path / "portfolio"
    directory.mkdir()
    (directory / "positions_ledger.json").write_text("{")
    if failed_count == 2:
        (directory / "latest.json").write_text("{")
    payload = _body(web.api_activity())
    assert isinstance(payload, dict)
    assert payload["activity_status"] == "partial"
    assert payload["events"] == []
    assert payload["failed_sources"] == ["trades", "decisions"][:failed_count]


def test_all_real_input_failures_are_fixed_unavailable(tmp_path):
    from app import web

    paths = _healthy_sources(tmp_path)
    paths["trades"].write_text("{")
    paths["decisions"].write_text("[]")
    paths["note"].write_bytes(b"\xff")
    payload = _body(web.api_activity())
    assert payload == {
        "activity_status": "unavailable", "events": None,
        "failed_sources": ["trades", "decisions", "research"], "error": "activity_unavailable",
    }


def test_valid_empty_objects_empty_notes_and_undated_notes_remain_empty(tmp_path):
    from app import web

    paths = _healthy_sources(tmp_path)
    paths["trades"].write_text('{"core:AAPL":{"history":[]}}')
    paths["decisions"].write_text('{"decisions":[]}')
    paths["note"].write_text("")
    (paths["research"] / "undated.md").write_text("# Undated\n\nBody\n")
    assert _body(web.api_activity()) == []


def test_genuine_missing_nested_families_remain_empty(tmp_path, monkeypatch):
    from app import web

    monkeypatch.setattr(web, "_data", lambda: tmp_path / "not-created" / "nested")
    assert _body(web.api_activity()) == []


def test_default_note_parser_retains_its_tolerant_contract(tmp_path, monkeypatch):
    from app import web

    path = tmp_path / "bad.md"
    path.write_bytes(b"\xff")
    assert web._parse_note(path) is None
    path.write_text("# Undated\n\nBody\n")
    original = Path.stat

    def stat(self, *args, **kwargs):
        if self == path:
            raise PermissionError(_SECRET)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    assert web._parse_note(path) is None


def test_healthy_order_cap_today_and_note_deduplication_are_preserved(tmp_path):
    from app import web

    paths = _healthy_sources(tmp_path)
    today = date.today().isoformat()
    history = [{"ts": today + f"T15:{minute:02}:00Z", "event": "open"} for minute in range(60)]
    history += [{"ts": today + "T14:00:00Z", "event": "close"}] * 5
    paths["trades"].write_text(json.dumps({"core:AAPL": {"ticker": "AAPL", "history": history}}))
    payload = _body(web.api_activity())
    assert isinstance(payload, list) and len(payload) == 60
    assert [row["ts"] for row in payload] == sorted((row["ts"] for row in payload), reverse=True)
    assert all(row["today"] is True for row in payload)
    paths["trades"].write_text("{}")
    paths["decisions"].write_text("{}")
    paths["note"].write_text("# Duplicate\n*tickers: AAPL · 2020-01-01*\n\nSame body\n")
    (paths["research"] / "new.md").write_text("# Duplicate\n*tickers: AAPL · 2021-01-01*\n\nSame body\n")
    (paths["research"] / "other.md").write_text("# Other\n*tickers: MSFT · 2022-01-01*\n\nSame body\n")
    payload = _body(web.api_activity())
    assert [row["title"] for row in payload] == ["Other", "Duplicate"]
    assert [row["ts"] for row in payload] == ["2022-01-01", "2021-01-01"]


@pytest.mark.parametrize("mode", ["empty", "partial", "unavailable"])
def test_registered_activity_route_preserves_availability_contract(tmp_path, mode):
    from app import web
    from fastapi import FastAPI
    import httpx

    if mode != "empty":
        paths = _healthy_sources(tmp_path)
        paths["trades"].write_text("{")
        if mode == "unavailable":
            paths["decisions"].write_text("[]")
            paths["note"].write_bytes(b"\xff")
    application = FastAPI()
    application.include_router(web.router)

    async def request():
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://private.test") as client:
            return await client.get("/api/activity")

    response = asyncio.run(request())
    assert response.status_code == 200
    if mode == "empty":
        assert response.json() == []
    else:
        assert response.json()["activity_status"] == mode


_NODE_RUNNER = "const vm = require('node:vm');\nconst assert = require('node:assert/strict');\nconst input = JSON.parse(process.argv[1]);\nconst elements = {brainlog: {innerHTML: ''}};\nconst records = {fetches: [], learning: [], pages: [], renders: 0, loads: 0, prefetch: [], collapses: []};\nconst ctx = {\n  assert, elements, records, language: 'en',\n  _brainPage: 0, BRAIN_PAGE_SIZE: 14, _sharedLoaded: false, _sharedLoad: null,\n  _collapsed: {runs: true}, _shadowBooks: null, _predictions: null,\n  _engineBacktest: null, _factorZoo: null, _fundamentals: null, _student: null, _distill: null,\n  E: id => elements[id] || null,\n  document: {documentElement: {getAttribute: () => ctx.language}},\n  esc: value => String(value == null ? '' : value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'),\n  collH2: () => '<h2>Brain Log</h2>',\n  applyColl: name => records.collapses.push(name),\n  t: key => key === 'brain.empty' ? '[LEGITIMATE EMPTY]' : key,\n  _pager: (cur, pages, fn) => {records.pages.push([cur,pages,fn]); return '<footer data-page=\"'+cur+'\"></footer>';},\n  http: (status, body) => ({ok: status >= 200 && status < 300, status, json: async () => body}),\n  drain: () => new Promise(resolve => setImmediate(resolve)),\n  event: (kind='trade', title='Healthy event') => ({ts:'2026-11-07T12:00:00Z',kind,title,detail:'Healthy detail'}),\n  loadPortfolios: async () => {records.loads++;},\n  _learningFetch: async (url, surface) => {records.learning.push(url);return {surface};},\n  _schedulePortfolioPrefetch: () => records.prefetch.push('portfolio'),\n  _scheduleWorkspacePrefetch: () => records.prefetch.push('workspace'),\n  _ensureRuns: () => {records.runs=(records.runs||0)+1;},\n};\nctx.window = ctx;\nctx._renderAll = () => {records.renders++;ctx.renderBrainLog();};\nvm.createContext(ctx);\nfor (const key of ['format','state','render','research','hydrate']) {\n  vm.runInContext(input.source[key], ctx, {timeout: 1500});\n}\nconst pending = vm.runInContext('(async function () {\\n' + input.body + '\\n})()', ctx, {timeout:1500});\nPromise.resolve(pending).then(() => process.stdout.write('ok\\n')).catch(error => {\n  process.stderr.write(String(error.stack || error)+'\\n');process.exitCode=1;\n});\n"

_CLIENT_CASES = {
    "initial_loading": "renderBrainLog();assert.ok(E('brainlog').innerHTML.includes('Loading activity'));assert.ok(!E('brainlog').innerHTML.includes('[LEGITIMATE EMPTY]'));",
    "unavailable_fixed": "_applyActivityFeed({activity_status:'unavailable',events:null,failed_sources:['trades','decisions','research'],error:'secret </div><b>'});renderBrainLog();\nassert.equal(_activityStatus,'unavailable');assert.equal(_activity.length,0);\nassert.ok(E('brainlog').innerHTML.includes('Brain Log unavailable'));assert.ok(E('brainlog').innerHTML.includes('retryBrainActivity()'));\nassert.ok(!E('brainlog').innerHTML.includes('secret'));assert.ok(!E('brainlog').innerHTML.includes('[LEGITIMATE EMPTY]'));\nlanguage='zh';renderBrainLog();assert.ok(E('brainlog').innerHTML.includes('脑波日志暂不可用'));",
    "partial_empty": "_applyActivityFeed({activity_status:'partial',events:[],failed_sources:['research']});renderBrainLog();\nassert.equal(_activityStatus,'partial');assert.ok(E('brainlog').innerHTML.includes('Partial activity'));\nassert.ok(E('brainlog').innerHTML.includes('No events were available from the readable'));assert.ok(!E('brainlog').innerHTML.includes('[LEGITIMATE EMPTY]'));",
    "partial_rows_localized": "var row=event('decision','Healthy <decision>');row.title_zh='中文 <决策>';row.detail_zh='证据';row.today=true;\n_applyActivityFeed({activity_status:'partial',events:[row],failed_sources:['research']});renderBrainLog();\nassert.equal(_activityStatus,'partial');assert.ok(E('brainlog').innerHTML.includes('Healthy &lt;decision&gt;'));\nassert.ok(E('brainlog').innerHTML.includes('Partial activity'));assert.ok(E('brainlog').innerHTML.includes('NEW'));\nlanguage='zh';renderBrainLog();assert.ok(E('brainlog').innerHTML.includes('中文 &lt;决策&gt;'));assert.ok(E('brainlog').innerHTML.includes('证据'));",
    "legacy_empty": "_applyActivityFeed([]);renderBrainLog();assert.equal(_activityStatus,'available');\nassert.ok(E('brainlog').innerHTML.includes('[LEGITIMATE EMPTY]'));assert.ok(!E('brainlog').innerHTML.includes('unavailable'));",
    "valid_paging": "var rows=Array.from({length:20},(_,i)=>event('trade','row-'+i));_applyActivityFeed(rows);_brainPage=99;renderBrainLog();\nassert.equal(_activityStatus,'available');assert.equal(_brainPage,1);assert.equal(records.pages[0][1],2);\nassert.ok(E('brainlog').innerHTML.includes('row-14'));assert.ok(!E('brainlog').innerHTML.includes('row-0</div>'));\nassert.ok(E('brainlog').innerHTML.includes('<br><span'));",
    "malformed_responses": "for(var payload of [null,{},1,'secret',{activity_status:'available',events:[]},\n{activity_status:'partial',events:null,failed_sources:['trades']},\n[null],[{}],[{...event(),kind:'trade\"><b>'}],[{...event(),ts:7}],\n[{...event(),title_zh:{}}],[{...event(),detail_zh:null}],[{...event(),today:'true'}]]) {\n_applyActivityFeed(payload);renderBrainLog();assert.equal(_activityStatus,'unavailable');assert.equal(_activity.length,0);\nassert.ok(E('brainlog').innerHTML.includes('Brain Log unavailable'));assert.ok(!E('brainlog').innerHTML.includes('secret'));\n}",
    "http_failure": "fetch=async url=>{records.fetches.push(url);return http(503,{error:'secret'});};\n_applyActivityFeed(await _activityFetch());renderBrainLog();assert.equal(records.fetches[0],'/api/activity');\nassert.equal(_activityStatus,'unavailable');assert.ok(!E('brainlog').innerHTML.includes('secret'));",
    "transport_and_json_failure": "for(var mode of ['transport','json']){\nfetch=async()=>{if(mode==='transport')throw new Error('secret');return {ok:true,json:async()=>{throw new Error('secret');}};};\n_applyActivityFeed(await _activityFetch());renderBrainLog();assert.equal(_activityStatus,'unavailable');\nassert.ok(E('brainlog').innerHTML.includes('Brain Log unavailable'));assert.ok(!E('brainlog').innerHTML.includes('secret'));\n}",
    "retry_recovers": "_applyActivityFeed({activity_status:'partial',events:[event('decision')],failed_sources:['research']});\nvar resolveFetch;fetch=url=>{records.fetches.push(url);return new Promise(resolve=>{resolveFetch=resolve;});};\nvar pending=retryBrainActivity();assert.equal(_activityStatus,'loading');assert.ok(E('brainlog').innerHTML.includes('Loading activity'));\nresolveFetch(http(200,[]));await pending;assert.equal(_activityStatus,'available');assert.equal(_activity.length,0);\nassert.equal(_activityFailedSources.length,0);assert.ok(E('brainlog').innerHTML.includes('[LEGITIMATE EMPTY]'));assert.equal(records.fetches.length,1);",
    "shared_hydration_singleton": "var book={id:'keep-selected-book'};_book=book;\nvar note={title:'research-unchanged',body_md:'',tickers:[]};\nfetch=async url=>{records.fetches.push(url);return http(200,url==='/api/activity'?{activity_status:'partial',events:[event('decision')],failed_sources:['research']}:[note]);};\nvar first=_hydrateShared(),second=_hydrateShared();assert.equal(first,second);await first;\nassert.equal(records.loads,1);assert.equal(records.fetches.filter(x=>x==='/api/activity').length,1);\nassert.equal(records.learning.length,7);assert.equal(_research[0].title,'research-unchanged');assert.equal(_book,book);\nassert.equal(_activityStatus,'partial');assert.equal(records.renders,1);assert.equal(_sharedLoaded,true);assert.equal(_sharedLoad,null);\nassert.equal(records.prefetch.length,2);await _hydrateShared();assert.equal(records.loads,1);assert.equal(records.fetches.length,2);",
    "hydration_failure_then_retry": "fetch=async url=>{records.fetches.push(url);return url==='/api/activity'?http(503,{error:'secret'}):http(200,[{title:'preserved-research',body_md:'',tickers:[]}]);};\nawait _hydrateShared();assert.equal(_activityStatus,'unavailable');assert.equal(_sharedLoaded,true);\nvar research=_research,shadow=_shadowBooks,learningCount=records.learning.length;\nfetch=async url=>{records.fetches.push(url);return http(200,[event('run','Recovered')]);};await retryBrainActivity();\nassert.equal(_activityStatus,'available');assert.ok(E('brainlog').innerHTML.includes('Recovered'));\nassert.equal(_research,research);assert.equal(_shadowBooks,shadow);assert.equal(records.learning.length,learningCount);assert.equal(records.fetches.length,3);",
    "invalid_timestamp_safe": "var row=event();row.ts='</div><b>';_applyActivityFeed([row]);renderBrainLog();\nassert.equal(_activityStatus,'available');assert.ok(E('brainlog').innerHTML.includes('&lt;/div&gt;&lt;b&gt;'));\nassert.ok(!E('brainlog').innerHTML.includes('<b>'));row.ts='';_applyActivityFeed([row]);renderBrainLog();\nassert.ok(E('brainlog').innerHTML.includes('mm-tl-ts\">—'));",
    "contradictory_partial_rejected": "for(var payload of [\n{activity_status:'partial',events:[],failed_sources:[]},\n{activity_status:'partial',events:[],failed_sources:['secret']},\n{activity_status:'partial',events:[],failed_sources:['trades','trades']},\n{activity_status:'partial',events:[],failed_sources:['trades','decisions','research']},\n{activity_status:'partial',events:[event('trade')],failed_sources:['trades']},\n{activity_status:'partial',events:[event('run')],failed_sources:['decisions']}]) {\n_applyActivityFeed(payload);renderBrainLog();assert.equal(_activityStatus,'unavailable');assert.equal(_activity.length,0);\nassert.ok(!E('brainlog').innerHTML.includes('secret'));\n}"
}


@lru_cache(maxsize=1)
def _node_runtime():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable for isolated dashboard behavior checks")
    result = subprocess.run(
        [node, "--version"], capture_output=True, text=True, timeout=8,
        env={"PATH": str(Path(node).parent), "LANG": "C"},
    )
    assert result.returncode == 0, result.stderr
    major = int(result.stdout.strip().lstrip("v").split(".")[0])
    if major < 20:
        pytest.skip("Node 20+ is required for permission-constrained dashboard checks")
    return node, "--permission" if major >= 23 else "--experimental-permission"


def _client_source():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    fmt = html.index("var fmtTsShort = function(s)")
    state = html.index("var _book = null, _trades = null, _activity = [], _research = [];")
    render = html.index("function renderBrainLog()")
    research = html.index("function _researchUnavailable()")
    hydrate = html.index("function _hydrateShared()")
    return {
        "format": html[fmt:html.index("\n};", fmt) + len("\n};")],
        "state": html[state:html.index("var _shadowBooks", state)],
        "render": html[render:html.index("// ── RESEARCH FEED", render)],
        "research": html[research:html.index("function _researchLoading()", research)],
        "hydrate": html[hydrate:html.index("async function fetchAll", hydrate)],
    }


def _run_client(case):
    node, permission = _node_runtime()
    payload = json.dumps({"case": case, "source": _client_source(), "body": _CLIENT_CASES[case]})
    result = subprocess.run(
        [node, permission, "--eval", _NODE_RUNNER, "--", payload],
        cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=8,
        env={"PATH": str(Path(node).parent), "LANG": "C"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ok\n", result.stdout


@pytest.mark.parametrize("case", ["initial_loading","unavailable_fixed","partial_empty","partial_rows_localized","legacy_empty","valid_paging","malformed_responses","http_failure","transport_and_json_failure","retry_recovers","shared_hydration_singleton","hydration_failure_then_retry","invalid_timestamp_safe","contradictory_partial_rejected"])
def test_actual_activity_client(case):
    _run_client(case)
