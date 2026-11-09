"""Desk missing data, failed reads and completed browser requests stay distinct."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

DATE = "2026-10-01"


@pytest.fixture
def desk(monkeypatch, tmp_path):
    from app import web
    from brain import macro_risk

    data = tmp_path / "data"
    monkeypatch.setattr(web, "_data", lambda: data)
    calls = []

    def fallback(asof, regime):
        calls.append((asof, regime))
        return {"asof": asof, "state": "caution", "allow_adds": False}

    monkeypatch.setattr(macro_risk, "risk_state", fallback)
    app = FastAPI()
    app.include_router(web.router)
    with TestClient(app) as client:
        yield web, data, client, calls


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def get(desk, endpoint, query=""):
    response = desk[2].get("/api/desk/" + endpoint + query)
    assert response.status_code == 200
    return response.json()


def assert_unavailable(payload, code):
    assert payload["status"] == "unavailable"
    assert payload["error"] == code
    assert "secret" not in json.dumps(payload).lower()
    assert "/Users/private" not in json.dumps(payload)


@pytest.mark.parametrize("endpoint,key", [
    ("strategist", None), ("decisions", "decisions"),
])
def test_missing_roots_remain_building(desk, endpoint, key):
    payload = get(desk, endpoint)
    assert payload["status"] == "building"
    assert payload["asof"] is None
    if key:
        assert payload[key] == []


@pytest.mark.parametrize("endpoint,relative,code", [
    ("strategist", "committee/" + DATE + "/_FLAGSHIP/strategist.json", "desk_strategist_unavailable"),
    ("decisions", "gate_officer/" + DATE + "/decisions.json", "desk_decisions_unavailable"),
    ("macro-risk", "macro_risk/" + DATE + "/state.json", "desk_macro_risk_unavailable"),
])
@pytest.mark.parametrize("raw", [b"{secret", b"[]", b"null", b'"not an object"', b"\xff"])
def test_corrupt_artifacts_are_unavailable(desk, endpoint, relative, code, raw, caplog):
    path = desk[1] / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    payload = get(desk, endpoint)
    assert_unavailable(payload, code)
    if endpoint == "decisions":
        assert payload["decisions"] is None
    if endpoint == "macro-risk":
        assert payload["state"] is None
        assert desk[3] == []
    assert str(path) not in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.parametrize("endpoint,root,code", [
    ("strategist", "committee", "desk_strategist_unavailable"),
    ("decisions", "risk_officer", "desk_decisions_unavailable"),
    ("macro-risk", "macro_risk", "desk_macro_risk_unavailable"),
])
def test_existing_non_directory_is_not_missing(desk, endpoint, root, code):
    path = desk[1] / root
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not a directory")
    assert_unavailable(get(desk, endpoint), code)
    assert desk[3] == []


def test_selected_decision_directory_failure_is_not_empty(desk):
    path = desk[1] / "committee" / DATE
    path.parent.mkdir(parents=True)
    path.write_text("not a directory")
    payload = get(desk, "decisions", "?asof=" + DATE)
    assert_unavailable(payload, "desk_decisions_unavailable")
    assert payload["decisions"] is None


@pytest.mark.parametrize("seat", ["forge", "sentinel", "nexus"])
def test_missing_seat_is_unknown_but_corrupt_seat_fails_read(desk, seat):
    path = desk[1] / "committee" / DATE / "NVDA" / (seat + ".json")
    path.parent.mkdir(parents=True)
    payload = get(desk, "decisions")
    assert payload["status"] == "scoring"
    assert payload["decisions"][0][seat] is None
    path.write_text("{secret")
    payload = get(desk, "decisions")
    assert_unavailable(payload, "desk_decisions_unavailable")
    assert payload["decisions"] is None


def test_mixed_missing_roots_keep_gate_only_decision(desk):
    path = desk[1] / "gate_officer" / DATE / "decisions.json"
    write(path, {"result": {"decisions": [
        {"ticker": "NVDA", "action": "withhold", "reason": "risk"},
    ]}})
    payload = get(desk, "decisions")
    assert payload["status"] == "scoring"
    row = payload["decisions"][0]
    assert row["ticker"] == "NVDA"
    assert row["gate"]["action"] == "withhold"
    assert row["forge"] is None and row["risk"] is None


def test_bad_consumed_decision_shape_is_closed(desk):
    write(desk[1] / "gate_officer" / DATE / "decisions.json",
          {"result": {"decisions": [None]}})
    assert_unavailable(get(desk, "decisions"), "desk_decisions_unavailable")


def test_strategist_empty_object_and_zero_theme_verdict_remain_distinct(desk):
    path = desk[1] / "committee" / DATE / "_FLAGSHIP" / "strategist.json"
    write(path, {})
    assert get(desk, "strategist")["status"] == "building"
    write(path, {"verdict": {
        "confirmed_themes": [], "backdrop_stance": "defensive",
        "rationale": "Valid zero-theme verdict",
    }, "input": {"regime": {"quad": "Q4"}}})
    payload = get(desk, "strategist")
    assert payload["status"] == "scoring"
    assert payload["confirmed_themes"] == []
    assert payload["rationale"] == "Valid zero-theme verdict"


def test_unreadable_artifact_does_not_become_building(desk):
    if os.geteuid() == 0:
        pytest.skip("POSIX mode bits do not deny the root user")
    path = desk[1] / "committee" / DATE / "_FLAGSHIP" / "strategist.json"
    write(path, {"verdict": {"rationale": "secret"}})
    path.chmod(0)
    try:
        assert_unavailable(get(desk, "strategist"), "desk_strategist_unavailable")
    finally:
        path.chmod(0o600)


def test_unreadable_root_does_not_become_building(desk):
    if os.geteuid() == 0:
        pytest.skip("POSIX mode bits do not deny the root user")
    path = desk[1] / "committee"
    path.mkdir(parents=True)
    path.chmod(0)
    try:
        assert_unavailable(get(desk, "strategist"), "desk_strategist_unavailable")
    finally:
        path.chmod(0o700)


def test_failed_mixed_root_does_not_publish_other_roots(desk, monkeypatch):
    write(desk[1] / "gate_officer" / DATE / "decisions.json",
          {"result": {"decisions": [{"ticker": "NVDA", "action": "add"}]}})
    original = Path.iterdir
    bad_root = desk[1] / "risk_officer"

    def interrupted(path):
        if path == bad_root:
            raise OSError("secret /Users/private/risk")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", interrupted)
    assert_unavailable(get(desk, "decisions"), "desk_decisions_unavailable")


@pytest.mark.parametrize("state_file", ["missing", "empty"])
def test_missing_or_empty_state_uses_existing_fallback(desk, state_file):
    if state_file == "empty":
        write(desk[1] / "macro_risk" / DATE / "state.json", {})
    payload = get(desk, "macro-risk")
    assert payload["status"] == "scoring"
    assert payload["state"] == "caution"
    assert payload["allow_adds"] is False
    assert desk[3] == [("", None)]


def test_valid_persisted_state_does_not_compute_fallback(desk):
    write(desk[1] / "macro_risk" / DATE / "state.json", {
        "state": {"asof": DATE, "state": "risk_off", "allow_adds": False},
    })
    payload = get(desk, "macro-risk")
    assert payload["state"] == "risk_off"
    assert payload["allow_adds"] is False
    assert desk[3] == []


@pytest.mark.parametrize("raw", [b"{secret", b"[]", b"null", b"\xff"])
def test_corrupt_regime_does_not_compute_a_replacement(desk, raw):
    path = desk[1].parent / "vendor" / "macro" / "data" / "regime" / "latest.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    assert_unavailable(get(desk, "macro-risk"), "desk_macro_risk_unavailable")
    assert desk[3] == []


def test_valid_regime_reaches_existing_fallback(desk):
    value = {"date": DATE, "quad": "Q4"}
    write(desk[1].parent / "vendor" / "macro" / "data" / "regime" / "latest.json", value)
    assert get(desk, "macro-risk")["state"] == "caution"
    assert desk[3] == [(DATE, value)]


@pytest.mark.parametrize("endpoint,attribute,code", [
    ("strategist", "_committee_dir", "desk_strategist_unavailable"),
    ("decisions", "_committee_dir", "desk_decisions_unavailable"),
    ("macro-risk", "_macro_risk_dir", "desk_macro_risk_unavailable"),
])
def test_outer_read_failures_use_closed_codes(desk, monkeypatch, endpoint, attribute, code):
    def fail():
        raise RuntimeError("secret /Users/private/source")
    monkeypatch.setattr(desk[0], attribute, fail)
    assert_unavailable(get(desk, endpoint), code)


def test_firm_empty_is_known_but_failed_read_is_unknown(desk, monkeypatch, caplog):
    from portfolio import firm_exposure

    empty = {"as_of": None, "books": [], "n_books": 0, "top_exposures": [],
             "flags": [], "by_sector": {}, "by_chain": {}, "thresholds": {},
             "currency_clean": False, "note": "No books yet"}
    monkeypatch.setattr(firm_exposure, "summary", lambda: empty)
    assert get(desk, "firm-exposure") == empty

    def fail():
        raise RuntimeError("secret /Users/private/account")
    monkeypatch.setattr(firm_exposure, "summary", fail)
    payload = get(desk, "firm-exposure")
    assert_unavailable(payload, "desk_firm_exposure_unavailable")
    for key in ("books", "n_books", "top_exposures", "flags",
                "by_sector", "by_chain", "thresholds", "currency_clean"):
        assert payload[key] is None
    assert "secret" not in caplog.text


def test_landed_watchlist_failure_contract_is_preserved(desk, monkeypatch):
    from portfolio import watchlist

    monkeypatch.setattr(watchlist, "state_rows", lambda: [])

    def fail():
        raise RuntimeError("secret /Users/private/watchlist")
    monkeypatch.setattr(watchlist, "latest", fail)
    payload = get(desk, "watchlist")
    assert_unavailable(payload, "desk_watchlist_unavailable")
    assert payload["watchlist"] is None


def test_actual_desk_loader_and_rendering_boundaries():
    """Exercise the shipped JavaScript and Markdown renderer with a minimal DOM."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the Desk JavaScript behavior checks")
    source = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
    program = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[1], 'utf8');
const start = html.indexOf('// ── DESK page');
const end = html.indexOf('window.openThesis', start);
assert(start >= 0 && end > start);
const helperStart = html.indexOf('function renderMd(');
const helperEnd = html.indexOf('// Parse a date string LOCALLY.', helperStart);
const source = html.slice(helperStart, helperEnd) + '\n' + html.slice(start, end);
const urls = {
  strategist:'/api/desk/strategist', decisions:'/api/desk/decisions',
  scorecard:'/api/desk/scorecard', firm:'/api/desk/firm-exposure',
  macroRisk:'/api/desk/macro-risk'
};
const ids = {strategist:'desk-strategist', decisions:'desk-decisions',
  scorecard:'desk-scorecard', firm:'desk-firm', macroRisk:'desk-macro-risk'};
const healthy = {
  strategist:{status:'scoring', asof:'2026-10-01', confirmed_themes:[],
    backdrop_stance:'defensive', rationale:'ZERO_THEME_VERDICT', regime:{},
    crowding_flags:[], watch_emerging:[]},
  decisions:{status:'scoring', decisions:[{ticker:'AAPL', nexus:{action:'hold', rationale:'KEEP_DECISION'}}]},
  scorecard:{status:'scoring', seats:[{seat:'strategist', n:0, attributed_bps:0}],
    cio:{note_md:'**KEEP_CIO**'}},
  firm:{books:['flagship'], flags:[], top_exposures:[{ticker:'MSFT', n_books:1, firm_weight_pct:0}],
    by_sector:{}, by_chain:{}},
  macroRisk:{status:'scoring', state:'caution', allow_adds:false, fragility:0,
    gross_cap:0, axes:{}, drivers:[], defensive_tilt:{}}
};
const markers = {strategist:'ZERO_THEME_VERDICT', decisions:'KEEP_DECISION',
  scorecard:'strategist', firm:'MSFT', macroRisk:'desk.mr_caution'};
function copy(x) { return JSON.parse(JSON.stringify(x)); }
function make(lang='en') {
  const hosts = {};
  const doc = {getElementById(id) { return hosts[id] || (hosts[id]={innerHTML:''}); },
    documentElement:{getAttribute() { return lang; }}};
  const ctx = {document:doc, t:key=>key, loadDeskPosture(){}, console};
  ctx.window=ctx;
  vm.createContext(ctx); vm.runInContext(source, ctx);
  const env = {ctx, hosts, lang};
  env.reply = function(url, kind, bad, mode) {
    if (url===urls[kind]) {
      if (mode==='http') return Promise.resolve({ok:false});
      if (mode==='network') return Promise.reject(new Error('secret /private/source'));
      if (mode==='json') return Promise.resolve({ok:true, json:()=>Promise.reject(new SyntaxError('secret'))});
      return Promise.resolve({ok:true, json:()=>Promise.resolve(bad)});
    }
    const key=Object.keys(urls).find(k=>urls[k]===url);
    const body=key ? copy(healthy[key]) :
      url.includes('watchlist') ? {watchlist:[{ticker:'WATCH',asof:'2026-10-01',reason:'healthy'}]} :
      {jobs:[{id:'SCHED',last_status:'ok'}]};
    return Promise.resolve({ok:true,json:()=>Promise.resolve(body)});
  };
  env.fetch = function(kind, bad, mode) { ctx.fetch=url=>env.reply(url,kind,bad,mode); };
  env.read = async function(kind, bad, mode) {
    env.fetch(kind,bad,mode);
    const completion=ctx.loadDesk();
    await completion;
    await new Promise(resolve=>setImmediate(resolve));
  };
  return env;
}
function unavailable(e,kind) {
  const text=e.hosts[ids[kind]].innerHTML;
  assert.match(text,/mm-desk-unavailable/,kind);
  assert.match(text,/mm-scope-retry/,kind);
  assert.doesNotMatch(text,/secret|\/private|desk_.*_unavailable/);
  if(kind==='scorecard') {
    assert.match(e.hosts['desk-cio'].innerHTML,/mm-desk-unavailable/);
    assert.doesNotMatch(e.hosts['desk-cio'].innerHTML,/KEEP_CIO/);
  }
  if(kind==='strategist') assert.equal(e.hosts['desk-asof'].innerHTML,'');
  for(const other of Object.keys(urls)) if(other!==kind)
    assert(e.hosts[ids[other]].innerHTML.includes(markers[other]),'healthy sibling '+other);
  assert(e.hosts['desk-watchlist'].innerHTML.includes('WATCH'));
  assert(e.hosts['desk-scheduler'].innerHTML.includes('SCHED'));
}
const cases=[];
async function test(name,run) {
  try { await run(); cases.push({name,passed:true}); }
  catch(err) { cases.push({name,passed:false,error:String(err.stack||err)}); }
}
(async function() {
  await test('first unresolved read is loading in all six hosts',async()=>{
    const e=make();e.ctx.fetch=()=>new Promise(()=>{});e.ctx.loadDesk();
    for(const id of [...Object.values(ids),'desk-cio']) {
      assert.match(e.hosts[id].innerHTML,/mm-desk-loading/);
      assert.doesNotMatch(e.hosts[id].innerHTML,/mm-desk-building|unavailable|RISK-ON/);
    }
  });
  const common=[['null',null],['array',[]],['primitive',17],['empty',{}],['http',null],
    ['json',null],['network',null],['explicit',{status:'unavailable',error:'secret /private/source'}]];
  for(const kind of Object.keys(urls)) for(const [mode,payload] of common)
    await test(kind+' completed '+mode+' failure clears cached content',async()=>{
      const e=make();await e.read();await e.read(kind,payload,mode);unavailable(e,kind);
    });
  const malformed=[
    ['strategist',{confirmed_themes:[null]}],['strategist',{confirmed_themes:[{names:'AAPL'}]}],
    ['strategist',{crowding_flags:{}}],['strategist',{regime:[]}],
    ['decisions',{decisions:[null]}],['decisions',{decisions:[{ticker:'AAPL',gate:[]}]}],
    ['scorecard',{seats:{}}],['scorecard',{seats:[null]}],['scorecard',{cio:'bad'}],
    ['scorecard',{cio:{note_md:42}}],['firm',{flags:[null]}],
    ['firm',{flags:[{kind:'name',books_holding:'flagship'}]}],
    ['firm',{by_sector:{energy:null}}],['firm',{by_chain:{energy:{leading_tickers:'AAPL'}}}],
    ['macroRisk',{state:'unknown'}],['macroRisk',{allow_adds:'false'}],
    ['macroRisk',{axes:{liquidity:null}}],['macroRisk',{drivers:[null]}],
    ['macroRisk',{drivers:[{hot_overlap:'AAPL'}]}],
    ['macroRisk',{defensive_tilt:{archetype:'defensive',favor:'cash'}}]
  ];
  for(let i=0;i<malformed.length;i++) {
    const [kind,delta]=malformed[i];
    await test('malformed '+kind+' '+i+' is contained',async()=>{
      const e=make();await e.read();await e.read(kind,Object.assign(copy(healthy[kind]),delta));
      unavailable(e,kind);
    });
  }
  await test('zero themes with a real verdict and zero seat metrics remain visible',async()=>{
    const e=make();await e.read();
    assert.match(e.hosts['desk-strategist'].innerHTML,/ZERO_THEME_VERDICT/);
    assert.doesNotMatch(e.hosts['desk-strategist'].innerHTML,/mm-desk-building/);
    assert.match(e.hosts['desk-scorecard'].innerHTML,/<td>0<\/td>/);
    assert.match(e.hosts['desk-scorecard'].innerHTML,/\+0/);
    assert.match(e.hosts['desk-cio'].innerHTML,/<strong>KEEP_CIO<\/strong>/);
  });
  await test('building scorecard preserves a valid independent CIO note',async()=>{
    const e=make();await e.read('scorecard',{status:'building',seats:[],cio:{note_md:'**PARTIAL_CIO**'}});
    assert.match(e.hosts['desk-scorecard'].innerHTML,/desk.sc_building/);
    assert.match(e.hosts['desk-cio'].innerHTML,/<strong>PARTIAL_CIO<\/strong>/);
  });
  await test('legitimate building and empty collections are not unavailable',async()=>{
    const e=make();
    for(const [kind,payload] of [
      ['strategist',{status:'building'}],['decisions',{status:'building',decisions:[]}],
      ['scorecard',{status:'building',seats:[],cio:null}],['firm',{books:[]}],
      ['macroRisk',{status:'building',state:null}]]) {
      await e.read(kind,payload);
      assert.match(e.hosts[ids[kind]].innerHTML,/mm-desk-building/);
      assert.doesNotMatch(e.hosts[ids[kind]].innerHTML,/mm-desk-unavailable/);
    }
  });
  await test('cached pending read then failure then recovery follows actual loadDesk',async()=>{
    const e=make();await e.read();const before=e.hosts['desk-scorecard'].innerHTML;
    const pending=[];e.ctx.fetch=url=>new Promise(resolve=>pending.push({url,resolve}));
    const completion=e.ctx.loadDesk();
    assert.equal(e.hosts['desk-scorecard'].innerHTML,before);
    assert.match(e.hosts['desk-cio'].innerHTML,/KEEP_CIO/);
    for(const p of pending) p.resolve(await e.reply(p.url,'scorecard',null,'http'));
    await completion;await new Promise(resolve=>setImmediate(resolve));unavailable(e,'scorecard');
    await e.read();assert.equal(e.hosts['desk-scorecard'].innerHTML,before);
    assert.match(e.hosts['desk-cio'].innerHTML,/KEEP_CIO/);
  });
  await test('residual text conversion exception cannot stop later healthy panels',async()=>{
    const e=make();await e.read();
    const d=copy(healthy.strategist);d.rationale={toString(){throw new Error('secret conversion');}};
    await e.read('strategist',d);unavailable(e,'strategist');
  });
  await test('unknown add permission is not rendered as allowed',async()=>{
    const e=make();await e.read('macroRisk',Object.assign(copy(healthy.macroRisk),{allow_adds:null}));
    assert.doesNotMatch(e.hosts['desk-macro-risk'].innerHTML,/desk.mr_allowed|desk.mr_blocked/);
    assert.match(e.hosts['desk-macro-risk'].innerHTML,/desk.mr_adds:<\/strong> —/);
  });
  for(const lang of ['en','zh']) await test(lang+' unavailable and loading are localized',async()=>{
    const e=make(lang);await e.read();await e.read('scorecard',null,'http');unavailable(e,'scorecard');
    assert(e.hosts['desk-scorecard'].innerHTML.includes(lang==='zh'?'席位记分卡暂不可用':'Seat scorecard is unavailable'));
    assert(e.hosts['desk-cio'].innerHTML.includes(lang==='zh'?'CIO 周报暂不可用':'CIO note is unavailable'));
    const first=make(lang);first.ctx.fetch=()=>new Promise(()=>{});first.ctx.loadDesk();
    assert(first.hosts['desk-cio'].innerHTML.includes(lang==='zh'?'正在读取面板':'Loading panel'));
  });
  const failed=cases.filter(c=>!c.passed);
  console.log(JSON.stringify({cases:cases.length,passed:cases.length-failed.length,failed:failed.length,failures:failed}));
  if(failed.length)process.exitCode=1;
})().catch(err=>{console.error(err);process.exitCode=1;});
'''
    result = subprocess.run([node, "-e", program, str(source)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["failed"] == 0
    assert evidence["cases"] == evidence["passed"] == 69
