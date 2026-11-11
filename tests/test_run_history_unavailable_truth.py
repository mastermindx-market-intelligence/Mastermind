"""Run-history failures stay unknown through the real disk, routes and UI consumers."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from brain import runlog as R

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    runs = root / "runs"
    runs.mkdir()
    monkeypatch.setattr(R, "_RUNS_DIR", runs)
    monkeypatch.setattr(R, "_INDEX", runs / "index.jsonl")
    monkeypatch.setattr(R, "_PROTOCOL_LOCK_ROOT", root)
    from app import web
    monkeypatch.setattr(web, "_cached_zh", lambda _text: None)
    return runs


def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import web
    app = FastAPI()
    app.include_router(web.router)
    return TestClient(app)


def seed(run_id="run-1"):
    return {"run_id": run_id, "ts": "2026-11-10T12:00:00Z", "kind": "daily",
            "title": "Daily review", "n_steps": 0, "cost_usd": None, "summary": ""}


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def legacy(store, steps=()):
    meta = seed()
    write_rows(store / "run-1.jsonl", [{"_meta": meta}, *steps])
    write_rows(R._INDEX, [{**meta, "n_steps": len(steps), "summary": "Review complete"}])
    return meta


def claim():
    from brain import fabric_portfolio as F
    return R.portfolio_claim({
        "schema": F.SCHEMA, "run_id": "selected-run", "book": "autonomous",
        "request": {"asof": "2026-11-10", "force": False, "armed": True, "directive": None},
        "asof": "2026-11-10", "phase": "claimed", "steps": [], "tools": []})


def test_genuinely_missing_index_and_empty_index_stay_successful(store):
    for write in (False, True):
        if write:
            R._INDEX.write_bytes(b"")
        with client() as c:
            listing = c.get("/api/runs")
            latest = c.get("/api/runlog")
        assert listing.status_code == latest.status_code == 200
        assert listing.json() == []
        assert latest.json()["steps"] == [] and latest.json()["run_id"] is None


def test_legacy_seed_zero_steps_and_unfinalized_trace_are_valid(store):
    run_id = R.start_run("daily", "Review in progress")
    assert not R._INDEX.exists()
    assert R.read_run(run_id, strict=True)["steps"] == []
    R.log_step(run_id, "tool_call", "Read news", "Observed result", tool="news")
    R.end_run(run_id, "Finished", 0.25)
    # start_run metadata remains a seed, not a second receipt of final counts.
    assert json.loads(R._run_path(run_id).read_text().splitlines()[0])["_meta"]["n_steps"] == 0
    actual = R.read_run(run_id, strict=True)
    assert actual["steps"][0]["detail"] == "Observed result"
    listing = R.list_runs(strict=True)
    assert listing[0]["n_steps"] == 1 and listing[0]["cost_usd"] == 0.25


@pytest.mark.parametrize("raw", [
    b'{"run_id":', b'[]\n', b'null\n', b'{}\n',
    b'{"run_id":"bad/id"}\n', b'{"run_id":"run-1","cost_usd":"0.5"}\n',
    b'{"run_id":"run-1","n_steps":true}\n', b'{"run_id":"run-1","title":[]}\n',
    b'{"run_id":"run-1","cost_usd":NaN}\n',
])
def test_bad_index_cannot_be_successful_empty_history(store, raw):
    R._INDEX.write_bytes(raw)
    with client() as c:
        for url in ("/api/runs", "/api/runlog"):
            response = c.get(url)
            body = response.json()
            assert response.status_code == 500
            assert body.get("run_status", body.get("trace_status")) == "unavailable"
            assert body.get("runs", body.get("steps")) is None


@pytest.mark.parametrize("raw", [
    b"", b'{"_meta":', b'[]\n', b'null\n', b'{}\n',
    b'{"_meta":null}\n', b'{"_meta":[]}\n',
    b'{"_meta":{"run_id":"other"}}\n',
    b'{"_meta":{"run_id":"run-1","title":[]}}\n',
    b'{"_meta":{"run_id":"run-1"}}\n{"type":"tool_call"}',
    b'{"_meta":{"run_id":"run-1"}}\n[]\n',
    b'{"_meta":{"run_id":"run-1"}}\n{}\n',
    b'{"_meta":{"run_id":"run-1"}}\n{"detail":{}}\n',
    b'{"_meta":{"run_id":"run-1"}}\n{"_fabric_portfolio":{}}\n',
    b'{"_meta":{"run_id":"run-1"}}\n{"_meta":{"run_id":"run-1"}}\n',
])
def test_partial_malformed_or_unanchored_run_is_not_zero_steps(store, raw):
    legacy(store)
    R._run_path("run-1").write_bytes(raw)
    with client() as c:
        response = c.get("/api/runlog", params={"run_id": "run-1"})
    assert response.status_code == 500
    assert response.json()["trace_status"] == "unavailable"
    assert response.json()["steps"] is None
    assert R._run_path("run-1").read_bytes() == raw


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink"])
def test_missing_or_nonregular_run_is_unavailable_without_repair_write(store, kind):
    path = R._run_path("run-1")
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        target = store / "original.jsonl"
        write_rows(target, [{"_meta": seed()}])
        path.symlink_to(target)
    with client() as c:
        response = c.get("/api/runlog", params={"run_id": "run-1"})
    assert response.status_code == 500
    assert response.json()["steps"] is None
    if kind == "missing":
        assert not path.exists()


def test_valid_legacy_routes_preserve_translation_and_order(store, monkeypatch):
    from app import web
    legacy(store, [{"type": "tool_result", "title": "News", "detail": "Observed news"}])
    second = {**seed("run-2"), "ts": "2026-11-10T13:00:00Z", "title": "New review"}
    with R._INDEX.open("a") as f:
        f.write(json.dumps(second) + "\n")
    monkeypatch.setattr(web, "_cached_zh", lambda text: {"Daily review": "每日复盘"}.get(text))
    with client() as c:
        rows = c.get("/api/runs").json()
        trace = c.get("/api/runlog", params={"run_id": "run-1"}).json()
    assert [row["run_id"] for row in rows] == ["run-2", "run-1"]
    assert rows[1]["title_zh"] == "每日复盘" and rows[1]["n_steps"] == 1
    assert trace["steps"][0]["detail"] == "Observed news"


def test_selected_revision_and_public_filter_survive_strict_reads(store):
    doc = claim()
    doc["state"]["error"] = "PRIVATE_SENTINEL"
    R.portfolio_save(doc)
    rows = R.strict_rows(R._INDEX)
    rows[0].update(n_steps=999, summary="PRIVATE_SENTINEL_INDEX")
    write_rows(R._INDEX, rows)
    with client() as c:
        listing = c.get("/api/runs")
        detail = c.get("/api/runlog", params={"run_id": "selected-run"})
    assert listing.status_code == detail.status_code == 200
    for result in (listing.json()[0], detail.json()):
        assert result["projection_revision"] == 1
        assert result["n_steps"] == 0
        assert "PRIVATE_SENTINEL" not in json.dumps(result)
        assert "_fabric_portfolio" not in json.dumps(result)


def test_damaged_selected_original_is_unavailable_but_legacy_default_is_preserved(store):
    claim()
    path = R._run_path("selected-run")
    path.write_bytes(path.read_bytes()[:-1])
    assert R.list_runs()[0]["status"] == "unavailable"
    with client() as c:
        for url in ("/api/runs", "/api/runlog?run_id=selected-run"):
            response = c.get(url)
            assert response.status_code == 500
            body = response.json()
            assert body.get("runs", body.get("steps")) is None


@pytest.mark.parametrize("url", ["/api/runs", "/api/runlog?run_id=run-1"])
def test_owner_failure_logs_only_type_and_never_returns_sensitive_detail(store, monkeypatch, caplog, url):
    marker = "SECRET_RUN_OWNER_DETAIL_753"
    def fail():
        raise RuntimeError(marker)
    monkeypatch.setattr(R, "_portfolio_index", fail)
    with client() as c:
        response = c.get(url)
    assert response.status_code == 500
    assert marker not in response.text and marker not in caplog.text
    assert "RuntimeError" in caplog.text
    assert "Traceback" not in caplog.text


def test_invalid_id_is_fixed_non_echoing_boundary_response(store):
    with client() as c:
        response = c.get("/api/runlog", params={"run_id": "../../SECRET_ESCAPE"})
    assert response.json()["error"] == "invalid run_id"
    assert response.json()["run_id"] is None
    assert "SECRET_ESCAPE" not in response.text
    assert list(store.iterdir()) == []


def ui_source():
    html = (ROOT / "app/static/index.html").read_text()
    return (
        html[html.index("function runsH2()"):html.index("function rejH2()")]
        + html[html.index("function _ensureRuns()"):html.index("function _researchPapersUnavailable()")]
        + html[html.index("window.toggleDecReason = function"):html.index("// ── SHADOW BOOKS")]
    )


HARNESS = r"""
const assert = require('node:assert/strict');
var window=globalThis, elements={}, _runs=[], _runsLoaded=false, _runsLoad=null, _runsStatus='loading';
var _runLogCache=Object.create(null), _runLogLoads=Object.create(null);
var RUNS_RENDER_CHUNK=60, _runsVisible=60;
var document={documentElement:{getAttribute:()=> 'en'}};
function E(id) {
  if(!elements[id]) {
    const classes=new Set(),attrs={};
    elements[id]={innerHTML:'',textContent:'',style:{display:'none'},
      classList:{contains:k=>classes.has(k),add:k=>classes.add(k),remove:k=>classes.delete(k)},
      setAttribute:(k,v)=>{attrs[k]=v;},getAttribute:k=>attrs[k]||null,removeAttribute:k=>{delete attrs[k];}};
  }
  return elements[id];
}
function esc(v){return String(v).replaceAll('&','&amp;').replaceAll('<','&lt;');}
function t(k){return k;}
function runKindClass(){return '';} function stepTypeClass(){return '';}
function stepDotClass(){return '';} function fmtTs(x){return x||'';}
function applyColl(){} function _safeRender(id,fn){fn();}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const ok=data=>({ok:true,json:()=>Promise.resolve(data)});
const row={run_id:'run-1',kind:'daily',title:'Review',ts:'2026-11-10T12:00:00Z',n_steps:0,cost_usd:null};
"""


def node(script):
    result = subprocess.run(["node", "-e", HARNESS + ui_source() + "\n" + script],
                            cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("payload", [
    "null", "{}", "{run_status:'unavailable',runs:null}", "[null]", "[[]]",
    "[{...row,run_id:'../bad'}]", "[{...row,title:[]}]", "[{...row,cost_usd:'0.1'}]",
    "[{...row,cost_usd:Infinity}]", "[{...row,n_steps:true}]", "[{...row,n_steps:-1}]",
    "[{...row,status:'unavailable'}]", "[row,{...row,summary:{}}]",
])
def test_actual_list_loader_rejects_bad_200_without_cache_poisoning(payload):
    node("""
(async()=>{
  fetch=()=>Promise.resolve(ok(""" + payload + """));
  await _ensureRuns();
  assert.equal(_runsLoaded,false);assert.equal(_runsStatus,'unavailable');assert.equal(_runs,null);
  assert.match(E('runs').innerHTML,/runs.unavailable/);
  assert.doesNotMatch(E('runs').innerHTML,/runs.empty/);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


@pytest.mark.parametrize("fetcher", [
    "()=>Promise.reject(new Error('offline'))",
    "()=>Promise.resolve({ok:false,json:()=>Promise.resolve([])})",
    "()=>Promise.resolve({ok:true,json:()=>Promise.reject(new SyntaxError('bad JSON'))})",
])
def test_actual_list_loader_keeps_transport_and_parse_failures_retryable(fetcher):
    node("""
(async()=>{
  fetch=""" + fetcher + """;
  await _ensureRuns();assert.equal(_runsLoaded,false);assert.equal(_runsStatus,'unavailable');
  let calls=0;fetch=()=>{calls++;return Promise.resolve(ok([]));};
  await _ensureRuns();await _ensureRuns();
  assert.equal(calls,1);assert.equal(_runsLoaded,true);assert.equal(_runsStatus,'available');
  assert.match(E('runs').innerHTML,/runs.empty/);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_actual_list_loading_coalesces_and_retains_bounded_pagination():
    node(r"""
(async()=>{
  let calls=0,release;
  fetch=()=>{calls++;return new Promise(resolve=>{release=resolve;});};
  const a=_ensureRuns(),b=_ensureRuns();assert.equal(a,b);assert.equal(calls,1);
  assert.equal(_runsLoaded,false);assert.equal(_runsStatus,'loading');
  assert.doesNotMatch(E('runs').innerHTML,/runs.empty/);
  const rows=Array.from({length:61},(_,i)=>({...row,run_id:'run-'+i}));
  release(ok(rows));await a;
  assert.equal((E('runs').innerHTML.match(/id="run-row-/g)||[]).length,60);
  assert.match(E('runs').innerHTML,/Show older activity/);
  showMoreRuns();
  assert.equal((E('runs').innerHTML.match(/id="run-row-/g)||[]).length,61);
  await _ensureRuns();assert.equal(calls,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


@pytest.mark.parametrize("payload", [
    "null", "{}", "{run_id:'run-1',steps:[{}]}", "{run_id:'other',steps:[]}", "{run_id:'run-1',steps:null}",
    "{run_id:'run-1',steps:{}}", "{run_id:'run-1',steps:[null]}",
    "{run_id:'run-1',steps:[{detail:{}}]}", "{run_id:'run-1',steps:[],error:'failed'}",
    "{run_id:'run-1',steps:[],trace_status:'unavailable'}",
    "{run_id:'run-1',steps:[],status:'unavailable'}",
])
def test_both_actual_trace_consumers_reject_invalid_success_without_loaded_flags(payload):
    node("""
(async()=>{
  fetch=()=>Promise.resolve(ok(""" + payload + """));
  toggleRun(0,'run-1');toggleDecReason(0,'run-1');await tick();await tick();
  assert.equal(Object.hasOwn(_runLogCache,'run-1'),false);
  assert.equal(E('dec-trace-0').getAttribute('data-loaded'),null);
  assert.match(E('run-steps-0').innerHTML,/runs.trace_unavailable/);
  assert.match(E('dec-trace-0').innerHTML,/runs.trace_unavailable/);
  assert.doesNotMatch(E('run-steps-0').innerHTML,/runs.no_steps/);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_actual_trace_consumers_coalesce_and_cache_genuine_zero_steps():
    node(r"""
(async()=>{
  let calls=0,release;
  fetch=()=>{calls++;return new Promise(resolve=>{release=resolve;});};
  toggleRun(0,'constructor');toggleDecReason(0,'constructor');
  toggleRun(0,'constructor');toggleRun(0,'constructor');
  toggleDecReason(0,'constructor');toggleDecReason(0,'constructor');
  assert.equal(calls,1);assert.equal(E('dec-trace-0').getAttribute('data-loaded'),null);
  release(ok({run_id:'constructor',steps:[]}));await tick();await tick();
  assert.equal(E('dec-trace-0').getAttribute('data-loaded'),'1');
  assert.match(E('run-steps-0').innerHTML,/runs.no_steps/);
  toggleRun(0,'constructor');toggleRun(0,'constructor');
  toggleDecReason(0,'constructor');toggleDecReason(0,'constructor');
  await tick();assert.equal(calls,1);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_actual_decision_retry_recovers_and_keeps_internal_reasoning_hidden():
    node(r"""
(async()=>{
  let calls=0;
  fetch=()=>{calls++;return Promise.reject(new Error('offline'));};
  toggleDecReason(0,'run-1');await tick();await tick();
  assert.equal(E('dec-trace-0').getAttribute('data-loaded'),null);
  assert.equal(E('dec-trace-0').getAttribute('data-loading'),null);
  fetch=()=>{calls++;return Promise.resolve(ok({run_id:'run-1',steps:[
    {type:'reasoning',detail:'PRIVATE_REASONING_SENTINEL'},
    {type:'tool_call',tool:'news',title:'News',args:{ticker:'AAPL'}},
    {type:'tool_result',result:'Observed evidence',detail:'Observed evidence'}]}));};
  toggleDecReason(0,'run-1');toggleDecReason(0,'run-1');
  await tick();await tick();
  assert.equal(calls,2);assert.equal(E('dec-trace-0').getAttribute('data-loaded'),'1');
  assert.match(E('dec-trace-0').innerHTML,/Observed evidence/);
  assert.doesNotMatch(E('dec-trace-0').innerHTML,/PRIVATE_REASONING_SENTINEL/);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_unknown_future_step_types_stay_valid_without_a_closed_catalogue(store):
    legacy(store, [{"type": "future_step", "title": "New observation"}])
    with client() as c:
        response = c.get("/api/runlog", params={"run_id": "run-1"})
    assert response.status_code == 200
    assert response.json()["steps"] == [{"type": "future_step", "title": "New observation"}]


def test_new_decision_view_does_not_reuse_older_brain_evidence():
    node(r"""
(async()=>{
  let calls=0;
  fetch=()=>{calls++;return Promise.resolve(ok({run_id:'run-1',projection_revision:0,status:'claimed',steps:[]}));};
  toggleRun(0,'run-1');await tick();await tick();
  fetch=()=>{calls++;return Promise.resolve(ok({run_id:'run-1',projection_revision:1,status:'complete',
    steps:[{type:'tool_result',result:'Newly recorded evidence'}]}));};
  toggleDecReason(0,'run-1');await tick();await tick();
  assert.equal(calls,2);
  assert.match(E('dec-trace-0').innerHTML,/Newly recorded evidence/);
  delete elements['dec-trace-0'];delete elements['dec-reason-0'];
  toggleDecReason(0,'run-1');await tick();await tick();
  assert.equal(calls,3,'a new decision disclosure reads the current original');
})().catch(e=>{console.error(e);process.exitCode=1;});
""")


def test_active_selected_brain_trace_is_refreshed_after_reopening():
    node(r"""
(async()=>{
  let calls=0;
  fetch=()=>{calls++;return Promise.resolve(ok({run_id:'run-1',projection_revision:calls,status:'claimed',
    steps:calls===1?[]:[{type:'future_step',title:'New observation',detail:'Fresh step'}]}));};
  toggleRun(0,'run-1');await tick();await tick();
  assert.equal(Object.hasOwn(_runLogCache,'run-1'),false);
  toggleRun(0,'run-1');toggleRun(0,'run-1');await tick();await tick();
  assert.equal(calls,2);assert.match(E('run-steps-0').innerHTML,/Fresh step/);
})().catch(e=>{console.error(e);process.exitCode=1;});
""")
