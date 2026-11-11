"""Real store and registered HTTP proof for Research Feed/Papers read truth."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def stores(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import web
    from brain import research_paper

    root = tmp_path / "data"
    papers = root / "research" / "papers"
    monkeypatch.setattr(web, "_data", lambda: root)
    monkeypatch.setattr(web, "_cached_zh", lambda _text: None)
    monkeypatch.setattr(research_paper, "_PAPERS", papers)
    app = FastAPI()
    app.include_router(web.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield root, client, web, research_paper


def _route(kind):
    return "/api/research" if kind == "feed" else "/api/research_papers"


def _path(root, kind):
    return root / "research" / ("notes" if kind == "feed" else "papers")


def _unavailable(response, kind):
    assert response.status_code == 500
    expected = (
        {"research_status": "unavailable", "error": "research_feed_unavailable", "notes": None}
        if kind == "feed" else
        {"paper_status": "unavailable", "error": "research_papers_unavailable", "papers": None}
    )
    assert response.json() == expected
    assert "secret" not in response.text and "/private/" not in response.text


def _paper(**updates):
    return {"id": "proof-1", "ticker": "AAPL",
            "generated_at": "2026-11-09T12:00:00+00:00",
            "summary": "Independent evidence", "report_md": "# Evidence",
            "engine_score": 0, "research_score": 0, "combined": 0,
            **updates}


@pytest.mark.parametrize("kind", ["feed", "papers"])
@pytest.mark.parametrize("shape", ["missing", "empty", "file", "dangling", "ancestor-file", "ancestor-link", "unreadable"])
def test_observed_store_absence_is_distinct_from_store_failure(stores, kind, shape):
    root, client, _, _ = stores
    path = _path(root, kind)
    restore = None
    if shape == "empty":
        path.mkdir(parents=True)
    elif shape == "file":
        path.parent.mkdir(parents=True)
        path.write_text("secret /private/not-a-directory")
    elif shape == "dangling":
        path.parent.mkdir(parents=True)
        path.symlink_to(root / "missing-private-target", target_is_directory=True)
    elif shape == "ancestor-file":
        root.mkdir()
        (root / "research").write_text("secret /private/not-a-directory")
    elif shape == "ancestor-link":
        root.mkdir()
        (root / "research").symlink_to(root / "missing-parent", target_is_directory=True)
    elif shape == "unreadable":
        if os.name != "posix" or os.geteuid() == 0:
            pytest.skip("real POSIX denial requires a non-root test account")
        path.mkdir(parents=True)
        path.chmod(0)
        restore = path
    try:
        response = client.get(_route(kind))
        if shape in {"missing", "empty"}:
            assert response.status_code == 200
            assert response.json() == ([] if kind == "feed" else {"papers": []})
        else:
            _unavailable(response, kind)
    finally:
        if restore:
            restore.chmod(0o700)


@pytest.mark.parametrize("kind", ["feed", "papers"])
@pytest.mark.parametrize("damage", ["encoding", "unreadable", "directory", "dangling"])
def test_real_broken_entry_never_disappears_from_a_successful_read(stores, kind, damage):
    root, client, _, _ = stores
    path = _path(root, kind)
    path.mkdir(parents=True)
    file = path / ("secret.md" if kind == "feed" else "secret.json")
    restore = None
    if damage == "encoding":
        file.write_bytes(b"\xff\xfe secret /private/broken")
    elif damage == "unreadable":
        if os.name != "posix" or os.geteuid() == 0:
            pytest.skip("real POSIX denial requires a non-root test account")
        file.write_text("# Evidence\nbody" if kind == "feed" else json.dumps(_paper()))
        file.chmod(0)
        restore = file
    elif damage == "directory":
        file.mkdir()
    else:
        file.symlink_to(path / "missing-entry")
    try:
        _unavailable(client.get(_route(kind)), kind)
    finally:
        if restore:
            restore.chmod(0o600)


@pytest.mark.parametrize("raw", [
    "{secret /private/broken",
    "null",
    "[]",
    "7",
    '{"id":"proof-1","id":"proof-2"}',
    '{"id":"proof-1","ticker":"AAPL","generated_at":"2026-11-09T12:00:00","summary":"secret"}',
    '{"id":"proof-1","ticker":null,"generated_at":"2026-11-09T12:00:00+00:00"}',
    '{"id":"proof-1","ticker":"AAPL","generated_at":"2026-11-09T12:00:00+00:00","combined":NaN}',
])
def test_real_malformed_paper_is_unavailable(stores, raw):
    root, client, _, _ = stores
    path = _path(root, "papers")
    path.mkdir(parents=True)
    (path / "secret.json").write_text(raw, encoding="utf-8")
    _unavailable(client.get(_route("papers")), "papers")


def test_duplicate_paper_identity_conflict_is_not_hidden(stores):
    root, client, _, _ = stores
    path = _path(root, "papers")
    path.mkdir(parents=True)
    for name, summary in [("one", "First evidence"), ("two", "Conflicting evidence")]:
        (path / f"{name}.json").write_text(json.dumps(_paper(summary=summary)))
    _unavailable(client.get(_route("papers")), "papers")


@pytest.mark.parametrize("kind", ["feed", "papers"])
def test_entry_disappearing_after_listing_is_not_an_empty_store(stores, monkeypatch, kind):
    root, client, web, rp = stores
    path = _path(root, kind)
    path.mkdir(parents=True)
    file = path / ("one.md" if kind == "feed" else "one.json")
    file.write_text("# Evidence\nbody" if kind == "feed" else json.dumps(_paper()))
    if kind == "feed":
        original = web._parse_note
        def disappear(p, *, strict=False):
            p.unlink()
            return original(p, strict=strict)
        monkeypatch.setattr(web, "_parse_note", disappear)
    else:
        original = rp._paper_read
        def disappear(p):
            p.unlink()
            return original(p)
        monkeypatch.setattr(rp, "_paper_read", disappear)
    _unavailable(client.get(_route(kind)), kind)


@pytest.mark.parametrize("kind", ["feed", "papers"])
def test_actual_reader_is_strict_and_preserves_good_evidence(stores, monkeypatch, kind):
    root, client, web, rp = stores
    path = _path(root, kind)
    path.mkdir(parents=True)
    seen = []
    if kind == "feed":
        (path / "one.md").write_text("# Evidence\n*tickers: AAPL · 2026-11-09T12:00:00Z*\n\nBody")
        original = web._parse_note
        def capture(p, *, strict=False):
            seen.append(strict)
            return original(p, strict=strict)
        monkeypatch.setattr(web, "_parse_note", capture)
    else:
        (path / "one.json").write_text(json.dumps(_paper()))
        original = rp.load_papers
        def capture(*, strict=False):
            seen.append(strict)
            return original(strict=strict)
        monkeypatch.setattr(rp, "load_papers", capture)
    response = client.get(_route(kind))
    assert response.status_code == 200
    assert seen == [True]
    rows = response.json() if kind == "feed" else response.json()["papers"]
    assert len(rows) == 1
    if kind == "feed":
        assert rows[0]["title"] == "Evidence" and rows[0]["body_md"] == "Body"
        assert rows[0]["tickers"] == ["AAPL"]
        assert rows[0]["title_zh"] is None and rows[0]["body_md_zh"] is None
    else:
        assert rows[0]["ticker"] == "AAPL"
        assert rows[0]["engine_score"] == rows[0]["research_score"] == rows[0]["combined"] == 0
        assert rows[0]["summary"] == "Independent evidence"


def test_feed_preserves_empty_note_and_deduplicates_valid_notes(stores):
    root, client, _, _ = stores
    path = _path(root, "feed")
    path.mkdir(parents=True)
    (path / "empty.md").write_text("")
    for name in ("one", "two"):
        (path / f"{name}.md").write_text("# Same\n*tickers: AAPL · 2026-11-09T12:00:00Z*\n\nSame body")
    response = client.get(_route("feed"))
    assert response.status_code == 200 and len(response.json()) == 1


@pytest.mark.parametrize("kind", ["feed", "papers"])
def test_enrichment_failure_is_closed_without_raw_exception(stores, monkeypatch, kind):
    root, client, web, _ = stores
    path = _path(root, kind)
    path.mkdir(parents=True)
    (path / ("one.md" if kind == "feed" else "one.json")).write_text(
        "# Evidence\nBody" if kind == "feed" else json.dumps(_paper())
    )
    def boom(_):
        raise OSError("secret /private/translation-cache")
    monkeypatch.setattr(web, "_cached_zh", boom)
    _unavailable(client.get(_route(kind)), kind)


def test_actual_research_javascript_boundaries():
    """Run the shipped loaders/renderers; malformed evidence must not look empty."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the research JavaScript behavior checks")
    source = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"
    program = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[1], 'utf8');
function block(start, end) {
  const a=html.indexOf(start), b=html.indexOf(end,a+start.length);
  assert(a>=0 && b>a, 'shipped source boundary: '+start);
  return html.slice(a,b);
}
const source = [
  block('var I18N = {', '// PBR-B0-PRIMITIVES:BEGIN'),
  block('function renderMd(', '// Parse a date string LOCALLY.'),
  block("var _book = null,", "var _activityStatus ="),
  block("var _activityStatus =", "var _shadowBooks ="),
  block('var _papers = []', 'var _calib ='),
  html.match(/var _papersLoaded = false, _papersLoad = null;/)[0],
  block('function _researchUnavailable()', 'window.toggleResearch'),
  block('function _viabClass(', 'function _ensureRuns()'),
  block('function _researchPapersUnavailable()', 'function _ensureCalibration()'),
  block('window.openThesis =', '// Generate + download the research paper'),
  block('function _hydrateShared()', 'async function fetchAll('),
].join('\n');
const goodNote={title:'READABLE_NOTE',body_md:'**READABLE_BODY**',tickers:['AAPL'],date:'2026-11-09',title_zh:null,body_md_zh:null};
const goodPaper={id:'paper-1',ticker:'AAPL',reviewed_at:'2026-11-09T12:00:00Z',action:'evaluated',
  mode:'engine',engine_score:0,research_score:0,combined:0,fair_value:0,
  viability:'fair',summary:'SAVED_SUMMARY',report_md:'**SAVED_REPORT**'};
function copy(value) { return JSON.parse(JSON.stringify(value)); }
function make(lang='en') {
  const hosts={}, language={value:lang}, counts={renders:0,portfolioPrefetch:0,workspacePrefetch:0};
  function element(id) {
    return hosts[id] || (hosts[id]={innerHTML:'',textContent:'',style:{},
      classList:{values:new Set(),add(v){this.values.add(v);},remove(v){this.values.delete(v);},contains(v){return this.values.has(v);}}});
  }
  const ctx={document:{getElementById:element,documentElement:{getAttribute(){return language.value;}},
      body:{style:{}},addEventListener(){}},console,
    _researchPage:0,RESEARCH_PAGE_SIZE:10,PAPERS_RENDER_CHUNK:60,_currentView:'research',
    _sharedLoaded:false,_sharedLoad:null,_collapsed:{runs:true},
    collH2:()=>'<h2>Research Feed</h2>',applyColl(){},_pager:()=>'',fmtTs:s=>s||'—',
    _safeRender(name,run){run();},loadPortfolios:()=>Promise.resolve(),
    _schedulePortfolioPrefetch(){counts.portfolioPrefetch++;},
    _scheduleWorkspacePrefetch(){counts.workspacePrefetch++;},
    renderBrainLog(){},_ensureRuns(){throw Error('unexpected run read');}};
  ctx.window=ctx;vm.createContext(ctx);vm.runInContext(source,ctx);
  ctx._renderAll=()=>{counts.renders++;ctx.renderResearch();ctx.renderResearchPapers();};
  const e={ctx,hosts,language,counts,calls:[]};
  e.respond=(url,payload,mode)=>{
    e.calls.push(url);
    if(mode==='sync')throw Error('secret /private/source');
    if(mode==='network')return Promise.reject(Error('secret /private/source'));
    if(mode==='http')return Promise.resolve({ok:false});
    if(mode==='json')return Promise.resolve({ok:true,json:()=>Promise.reject(SyntaxError('secret JSON'))});
    return Promise.resolve({ok:true,json:()=>Promise.resolve(payload)});
  };
  e.feed=async(payload=[copy(goodNote)],mode)=>{
    ctx.fetch=url=>e.respond(url,payload,mode);
    await ctx.retryResearchFeed();
  };
  e.papers=async(payload={papers:[copy(goodPaper)]},mode)=>{
    ctx.fetch=url=>e.respond(url,payload,mode);
    await ctx.retryResearchPapers();
  };
  return e;
}
function unavailable(e,kind) {
  const text=e.hosts[kind==='feed'?'research':'rp-host'].innerHTML;
  assert.match(text,/mm-research-unavailable/);
  assert.match(text,/mm-scope-retry/);
  assert.doesNotMatch(text,/READABLE_|SAVED_|secret|\/private|research_feed_unavailable|research_papers_unavailable|No research.*yet|暂无研究.*运行后/);
  assert.equal(e.ctx[kind==='feed'?'_researchStatus':'_papersStatus'],'unavailable');
  assert.equal(e.ctx[kind==='feed'?'_research':'_papers'].length,0);
  if(kind==='papers'){assert.equal(e.ctx._papersLoaded,false);assert.equal(e.ctx._papersLoad,null);assert.equal(e.ctx._openPaperId,null);}
}
const cases=[];
async function test(name,fn){try{await fn();cases.push({name,passed:true});}catch(e){cases.push({name,passed:false,error:String(e.stack||e)});}}
(async()=>{
  for(const kind of ['feed','papers']) await test(kind+' pending is a neutral skeleton',async()=>{
    const e=make();e.ctx.fetch=()=>new Promise(()=>{});
    if(kind==='feed')e.ctx.retryResearchFeed();else e.ctx._ensureResearchPapers();
    const text=e.hosts[kind==='feed'?'research':'rp-host'].innerHTML;
    assert.match(text,/mm-research-loading/);assert.match(text,/aria-busy="true"/);
    assert.doesNotMatch(text,/mm-empty|mm-research-unavailable|No research/);
  });
  const wrongFeed=[null,{},17,'secret',true,{research_status:'unavailable',notes:null,error:'secret'},[null],[[]]];
  for(let i=0;i<wrongFeed.length;i++)await test('feed malformed successful envelope '+i,async()=>{
    const e=make();await e.feed();await e.feed(wrongFeed[i]);unavailable(e,'feed');
  });
  const wrongPapers=[null,[],17,'secret',true,{}, {papers:null},{papers:{}},{papers:[null]},{papers:[[]]},
    {papers:[],paper_status:'unavailable',error:'secret'}, {papers:[],error:'secret'},
    {papers:[],paper_status:'partial'}];
  for(let i=0;i<wrongPapers.length;i++)await test('papers malformed successful envelope '+i,async()=>{
    const e=make();await e.papers();e.ctx.openThesis('paper-1');await e.papers(wrongPapers[i]);unavailable(e,'papers');
    assert(!e.hosts['mm-thesis-modal'].classList.contains('open'));
  });
  for(const kind of ['feed','papers'])for(const mode of ['http','json','network','sync'])
    await test(kind+' '+mode+' failure clears old evidence',async()=>{
      const e=make();await e[kind]();await e[kind](null,mode);unavailable(e,kind);
    });
  const badNote=[{title:{}},{body_md:[]},{body_md:42},{tickers:'AAPL'},{tickers:[null]},{date:42},{title_zh:42},{body_md_zh:{}}];
  for(let i=0;i<badNote.length;i++)await test('feed consumed field '+i,async()=>{
    const e=make();await e.feed([Object.assign(copy(goodNote),badNote[i])]);unavailable(e,'feed');
  });
  const badPaper=[{id:null},{id:' '},{ticker:{}},{ticker:''},{trade_time:42},{reviewed_at:[]},
    {action:{}},{mode:[]},{viability:{}},{summary:[]},{summary_zh:17},{report_md:{}},{report_md_zh:42},
    {engine_score:'0'},{research_score:NaN},{combined:Infinity},{fair_value:'<img src=x onerror=alert(1)>'}];
  for(let i=0;i<badPaper.length;i++)await test('papers consumed field '+i,async()=>{
    const e=make();await e.papers({papers:[Object.assign(copy(goodPaper),badPaper[i])]});unavailable(e,'papers');
  });
  await test('observed empty collections retain empty wording',async()=>{
    const e=make();await e.feed([]);await e.papers({papers:[]});
    assert.match(e.hosts.research.innerHTML,/No research notes yet/);
    assert.match(e.hosts['rp-host'].innerHTML,/No research papers yet/);
    assert.doesNotMatch(e.hosts.research.innerHTML+e.hosts['rp-host'].innerHTML,/mm-research-unavailable/);
    assert.equal(e.ctx._papersLoaded,true);
  });
  await test('zeros and real report survive rendering and opening',async()=>{
    const e=make();await e.feed();await e.papers();e.ctx.openThesis('paper-1');
    assert.match(e.hosts.research.innerHTML,/<strong>READABLE_BODY<\/strong>/);
    assert.equal((e.hosts['rp-host'].innerHTML.match(/>0<\/span>/g)||[]).length,3);
    assert.match(e.hosts['mm-modal-scores'].innerHTML,/\$0/);
    assert.match(e.hosts['mm-modal-body'].innerHTML,/<strong>SAVED_REPORT<\/strong>/);
  });
  await test('optional absent paper details preserve a genuine saved row',async()=>{
    const e=make();await e.papers({papers:[{id:'minimal',ticker:'MSFT'}]});
    assert.match(e.hosts['rp-host'].innerHTML,/MSFT/);assert.equal(e.ctx._papersStatus,'available');
    e.ctx.openThesis('minimal');assert.equal(e.ctx._openPaperId,'minimal');
  });
  await test('valid text is escaped in date viability and paper identity',async()=>{
    const e=make();const id="x');alert('secret";
    await e.feed([Object.assign(copy(goodNote),{date:'<img>x',title:'<img>'})]);
    await e.papers({papers:[Object.assign(copy(goodPaper),{id,viability:'<img src=x>'})]});
    assert.match(e.hosts.research.innerHTML,/&lt;img&gt;/);
    assert.match(e.hosts['rp-host'].innerHTML,/&lt;img src=x&gt;/);
    assert.match(e.hosts['rp-host'].innerHTML,/onclick="openThesis\(this\.getAttribute\('data-paper-id'\)\)"/);
    assert.doesNotMatch(e.hosts['rp-host'].innerHTML,/<img|onclick="openThesis\('x/);
    e.ctx.openThesis(id);assert.equal(e.ctx._openPaperId,id);
  });
  await test('feed retry calls share one pending transport',async()=>{
    const e=make();let resolve,count=0;e.ctx.fetch=()=>{count++;return new Promise(r=>resolve=r);};
    const a=e.ctx.retryResearchFeed(),b=e.ctx.retryResearchFeed();
    await Promise.resolve();assert.equal(count,1);
    resolve({ok:true,json:()=>Promise.resolve([copy(goodNote)])});
    await Promise.all([a,b]);assert.equal(e.ctx._researchLoad,null);assert.equal(e.ctx._researchStatus,'available');
  });
  await test('papers open retry and cache share one in-flight request',async()=>{
    const e=make();let resolve,count=0;e.ctx.fetch=()=>{count++;return new Promise(r=>resolve=r);};
    const a=e.ctx._ensureResearchPapers(),b=e.ctx._ensureResearchPapers(),c=e.ctx.retryResearchPapers();
    assert.equal(a,b);assert.equal(b,c);await Promise.resolve();assert.equal(count,1);
    resolve({ok:true,json:()=>Promise.resolve({papers:[copy(goodPaper)]})});await a;
    await e.ctx._ensureResearchPapers();assert.equal(count,1);assert.equal(e.ctx._papersLoaded,true);
  });
  await test('failed papers can reopen and then cache successful recovery',async()=>{
    const e=make();await e.papers(null,'http');unavailable(e,'papers');
    e.ctx.fetch=url=>e.respond(url,{papers:[copy(goodPaper)]});
    await e.ctx._ensureResearchPapers();await e.ctx._ensureResearchPapers();
    assert.equal(e.calls.length,2);assert.equal(e.ctx._papersStatus,'available');
  });
  for(const lang of ['en','zh'])await test(lang+' failed state rerenders from cache without fetch',async()=>{
    const e=make(lang);await e.feed(null,'http');await e.papers(null,'network');
    const count=e.calls.length;const text=e.hosts.research.innerHTML+e.hosts['rp-host'].innerHTML;
    assert(text.includes(lang==='zh'?'研究动态暂不可用':'Research feed is unavailable'));
    assert(text.includes(lang==='zh'?'研究论文暂不可用':'Research papers are unavailable'));
    e.language.value=lang==='en'?'zh':'en';e.ctx.renderResearch();e.ctx.renderResearchPapers();
    assert(e.hosts['rp-host'].innerHTML.includes(lang==='en'?'研究论文暂不可用':'Research papers are unavailable'));
    assert.equal(e.calls.length,count);
  });
  await test('actual shared hydration preserves siblings and does not refetch them on feed retry',async()=>{
    const e=make();let fail=true;
    const activity={ts:'2026-11-09',kind:'trade',title:'KEEP_ACTIVITY',detail:'independent'};
    e.ctx.fetch=url=>e.respond(url,url==='/api/research'?(fail?{research_status:'unavailable',notes:null}:[copy(goodNote)]):
      url==='/api/activity'?[activity]:{marker:url});
    e.ctx._learningFetch=url=>e.ctx.fetch(url).then(r=>r.json());
    const a=e.ctx._hydrateShared(),b=e.ctx._hydrateShared();assert.equal(a,b);await a;
    unavailable(e,'feed');assert.equal(e.ctx._activity[0].title,'KEEP_ACTIVITY');
    assert.equal(e.ctx._activityStatus,'available');
    for(const [key,url]of[['_shadowBooks','/api/shadow_books'],['_predictions','/api/predictions'],
      ['_engineBacktest','/api/engine_backtest'],['_factorZoo','/api/factor_zoo'],['_fundamentals','/api/fundamentals'],
      ['_student','/api/student'],['_distill','/api/distill']])assert.equal(e.ctx[key].marker,url);
    assert.equal(e.calls.length,9);assert.equal(e.ctx._sharedLoaded,true);
    assert.equal(e.counts.portfolioPrefetch,1);assert.equal(e.counts.workspacePrefetch,1);
    await e.ctx._hydrateShared();assert.equal(e.calls.length,9);
    fail=false;await e.ctx.retryResearchFeed();
    assert.equal(e.calls.length,10);assert.equal(e.calls.at(-1),'/api/research');
    assert.equal(e.ctx._researchStatus,'available');assert.equal(e.ctx._activity[0].title,'KEEP_ACTIVITY');
  });
  const failures=cases.filter(x=>!x.passed);
  console.log(JSON.stringify({cases:cases.length,passed:cases.length-failures.length,failed:failures.length,failures}));
  if(failures.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    result = subprocess.run([node, "-e", program, str(source)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["failed"] == 0
    assert evidence["cases"] == evidence["passed"]
    print("RESEARCH_JS " + json.dumps(evidence))
