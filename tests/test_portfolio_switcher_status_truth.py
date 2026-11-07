"""Portfolio switcher badges preserve partial/unavailable quick-status truth."""
from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _switcher_private_state(monkeypatch):
    from app import web
    from brain import benchmark_ledger
    monkeypatch.setattr(web, "_portfolios_cache", {})
    monkeypatch.setattr(benchmark_ledger, "latest", lambda: {"bogeys": {}})
    monkeypatch.setattr(benchmark_ledger, "read_nav_history", lambda _path: [])
    monkeypatch.setattr(benchmark_ledger, "compare_book_to_ledger", lambda *_a, **_k: {
        "status": "unavailable", "reason": "insufficient_common_dates",
        "start": None, "end": None, "common_point_count": 0, "endpoint_status": None,
    })


def _body(resp):
    return json.loads(resp.body)


def test_self_directed_unknown_valuation_stays_null_and_partial(monkeypatch):
    from app import web
    from brain import benchmark_ledger
    from portfolio import registry, self_directed

    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {"AAPL": {}}})
    monkeypatch.setattr(web, "_live_prices", lambda _held, refresh=False: {})
    monkeypatch.setattr(self_directed, "book", lambda **_kwargs: {
        "nav": None,
        "inception_date": "2026-09-01",
        "valuation_complete": False,
        "unpriced_tickers": ["AAPL"],
        "positions": [{"ticker": "AAPL"}],
        "allocation": {"cash_pct": None, "total_return_pct": None, "n_positions": 1},
    })
    monkeypatch.setattr(benchmark_ledger, "latest", lambda: {"bogeys": {}})

    row = web._portfolio_status(registry.get("self_directed"))
    status = row["status"]
    assert status["cash_pct"] is None
    assert status["holdings"] == 1
    assert status["nav"] is None
    assert status["valuation_complete"] is False
    assert status["unpriced_tickers"] == ["AAPL"]
    assert status["read_status"] == "partial"
    assert status["status_reasons"] == ["valuation_incomplete"]


def test_self_directed_book_failure_is_unavailable_not_zero(monkeypatch):
    from app import web
    from brain import benchmark_ledger
    from portfolio import registry, self_directed

    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {"AAPL": {}}})
    monkeypatch.setattr(web, "_live_prices", lambda _held, refresh=False: {})
    monkeypatch.setattr(self_directed, "book", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(benchmark_ledger, "latest", lambda: {"bogeys": {}})

    status = web._portfolio_status(registry.get("self_directed"))["status"]
    assert status["read_status"] == "unavailable"
    assert status["failed_sources"] == ["book"]
    assert status["nav"] is None
    assert status["holdings"] is None
    assert status["cash_pct"] is None


def test_managed_performance_failure_preserves_snapshot_as_partial(tmp_path, monkeypatch):
    from app import web
    from portfolio import paper_account, registry

    (tmp_path / "latest.json").write_text(json.dumps({"as_of": "2026-09-17", "positions": [{}, {}]}))
    monkeypatch.setattr(registry, "data_dir", lambda _pid: tmp_path)
    monkeypatch.setattr(web, "_book_marks", lambda _pid, refresh=False: {})
    monkeypatch.setattr(paper_account, "performance", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    status = web._portfolio_status(registry.get("autonomous"))["status"]
    assert status["read_status"] == "partial"
    assert status["failed_sources"] == ["performance"]
    assert status["nav"] is None
    assert status["holdings"] == 2
    assert status["as_of"] == "2026-09-17"


def test_managed_corrupt_snapshot_preserves_performance_as_partial(tmp_path, monkeypatch):
    from app import web
    from portfolio import paper_account, registry

    (tmp_path / "latest.json").write_text("{bad-json")
    monkeypatch.setattr(registry, "data_dir", lambda _pid: tmp_path)
    monkeypatch.setattr(web, "_book_marks", lambda _pid, refresh=False: {})
    monkeypatch.setattr(paper_account, "performance", lambda **_kwargs: {
        "current_nav": 1_010_000.0, "total_return_pct": 1.0,
        "vs_benchmark_pct": 0.2, "vs_spy_pct": 0.2,
        "day_change_pct": 0.1, "cash": 100_000.0, "realized_since": "2026-09-01",
        "availability": {"status": "available", "as_of": "2026-09-17"},
    })

    status = web._portfolio_status(registry.get("autonomous"))["status"]
    assert status["read_status"] == "partial"
    assert status["failed_sources"] == ["snapshot"]
    assert status["nav"] == 1_010_000.0
    assert status["holdings"] is None


def test_degraded_rows_are_not_cached(monkeypatch):
    from app import web
    from portfolio import registry

    monkeypatch.setattr(web, "_portfolios_cache", {})
    meta = registry.get("autonomous")
    monkeypatch.setattr(registry, "all_portfolios", lambda: [meta])
    monkeypatch.setattr(web, "_portfolio_status", lambda _meta: {
        "id": "autonomous", "status": {"read_status": "partial", "nav": None}
    })
    payload = _body(web.api_portfolios())
    assert payload["portfolios"][0]["status"]["read_status"] == "partial"
    assert "payload" not in web._portfolios_cache


def test_full_rows_remain_cacheable(monkeypatch):
    from app import web
    from portfolio import registry

    monkeypatch.setattr(web, "_portfolios_cache", {})
    meta = registry.get("autonomous")
    monkeypatch.setattr(registry, "all_portfolios", lambda: [meta])
    monkeypatch.setattr(web, "_portfolio_status", lambda _meta: {
        "id": "autonomous", "status": {"read_status": "available", "nav": 1_000_000.0}
    })
    _body(web.api_portfolios())
    assert "payload" in web._portfolios_cache


def test_portfolios_outer_failure_is_closed(monkeypatch):
    from app import web
    from portfolio import registry

    monkeypatch.setattr(web, "_portfolios_cache", {})
    monkeypatch.setattr(registry, "all_portfolios", lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/registry")))
    response = web.api_portfolios()
    payload = _body(response)
    assert response.status_code == 503
    assert payload["read_status"] == "unavailable"
    assert payload["portfolios"] is None
    assert payload["error"] == "portfolios_unavailable"
    assert "secret" not in response.body.decode()


def test_switcher_renders_partial_and_unavailable_labels():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    start = html.index("function renderPortfolioSwitch()")
    end = html.index("function revealActivePortfolioTab", start)
    block = html[start:end]
    assert "st.read_status === 'partial'" in block
    assert "st.read_status === 'unavailable'" in block
    assert "PARTIAL" in block
    assert "UNAVAILABLE" in block
    assert "_portfoliosStatus === 'unavailable'" in block
    assert "Portfolios unavailable" in block

    load_start = html.index("async function loadPortfolios()")
    load_end = html.index("\n}", load_start) + 2
    load = html[load_start:load_end]
    assert "_portfoliosStatus = 'unavailable'" in load
    assert "renderPortfolioSwitch();" in load

def _available_performance():
    return {
        "current_nav": 1_000_000.0, "cash": 100_000.0, "total_return_pct": 4.0,
        "vs_benchmark_pct": 0.2, "vs_spy_pct": 0.2, "day_change_pct": 0.1,
        "availability": {"status": "available", "as_of": "2026-11-05"},
        "frozen_as_of": "2026-10-30",
    }


def _setup_status(tmp_path, monkeypatch, pid="autonomous", performance=None):
    from app import web
    from portfolio import paper_account, registry
    perf = _available_performance() if performance is None else performance
    monkeypatch.setattr(registry, "data_dir", lambda _pid: tmp_path)
    def marks(_pid, refresh=False):
        assert _pid == pid and refresh is False
        return {}
    monkeypatch.setattr(web, "_book_marks", marks)
    if pid == "flagship":
        monkeypatch.setattr(web, "_archived_performance", lambda _pid: perf)
        monkeypatch.setattr(paper_account, "performance", lambda **_kw: pytest.fail("archive used live performance"))
    else:
        monkeypatch.setattr(paper_account, "performance", lambda **_kw: perf)
    return web, registry, paper_account, tmp_path / "latest.json"


@pytest.mark.parametrize("pid", ["autonomous", "flagship"])
@pytest.mark.parametrize("case", [
    "missing", "null", "wrong_object", "positions_missing", "positions_null",
    "positions_dict", "positions_string", "positions_badrow", "corrupt",
    "unreadable", "dangling", "directory", "empty", "rows", "exists_lie",
])
def test_snapshot_read_first_shapes_and_known_empty(tmp_path, monkeypatch, pid, case):
    web, registry, _, latest = _setup_status(tmp_path, monkeypatch, pid)
    payloads = {
        "null": None, "wrong_object": [], "positions_missing": {},
        "positions_null": {"positions": None}, "positions_dict": {"positions": {}},
        "positions_string": {"positions": ""}, "positions_badrow": {"positions": [None]},
        "empty": {"positions": [], "as_of": "2026-11-06"},
        "rows": {"positions": [{}, {}], "as_of": "2026-11-06"},
        "exists_lie": {"positions": [{}, {}], "as_of": "2026-11-06"},
    }
    if case in payloads:
        latest.write_text(json.dumps(payloads[case]))
    elif case == "corrupt":
        latest.write_text("{bad-json")
    elif case == "dangling":
        latest.symlink_to(tmp_path / "absent-target")
    elif case == "directory":
        latest.mkdir()
    elif case == "unreadable":
        latest.write_text('{"positions":[]}')
        read = Path.read_text
        def fail_read(path, *args, **kwargs):
            if path == latest:
                raise PermissionError("secret /Users/private/account")
            return read(path, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", fail_read)
    if case == "exists_lie":
        exists = Path.exists
        monkeypatch.setattr(Path, "exists", lambda path: False if path == latest else exists(path))
    row = web._portfolio_status(registry.get(pid))
    st = row["status"]
    assert st["nav"] == 1_000_000.0
    if case in ("empty", "rows", "exists_lie"):
        assert st["read_status"] == "available"
        assert st["holdings"] == (0 if case == "empty" else 2)
        assert st["as_of"] == "2026-11-06"
        assert not st.get("failed_sources")
    else:
        assert st["read_status"] == "partial"
        assert st["holdings"] is None
        if case == "missing":
            assert st["status_reasons"] == ["snapshot_missing"]
            assert not st.get("failed_sources")
        else:
            assert st["failed_sources"] == ["snapshot"]
    if pid == "flagship":
        assert row["lifecycle"] == "archived" and row["active"] is False
        assert st["cash_pct"] == 10.0
        assert st["total_return_pct"] == 4.0
    else:
        assert st["performance_as_of"] == "2026-11-05"
        assert st["performance_status"] == "available"
    assert "secret" not in json.dumps(row)


@pytest.mark.parametrize("pid", ["autonomous", "flagship"])
@pytest.mark.parametrize("snapshot", ["missing", "corrupt", "empty"])
def test_only_observed_snapshot_supplies_surviving_primary_evidence(tmp_path, monkeypatch, pid, snapshot):
    web, registry, paper_account, latest = _setup_status(tmp_path, monkeypatch, pid)
    def fail(*_a, **_k):
        raise RuntimeError("private provider detail")
    monkeypatch.setattr(web if pid == "flagship" else paper_account,
                        "_archived_performance" if pid == "flagship" else "performance", fail)
    if snapshot == "empty":
        latest.write_text('{"positions":[]}')
    elif snapshot == "corrupt":
        latest.write_text("{bad")
    st = web._portfolio_status(registry.get(pid))["status"]
    assert st["read_status"] == ("partial" if snapshot == "empty" else "unavailable")
    assert st["nav"] is None
    assert st["holdings"] == (0 if snapshot == "empty" else None)
    assert st["failed_sources"] == (["performance", "snapshot"] if snapshot == "corrupt" else ["performance"])
    if snapshot == "missing":
        assert st["status_reasons"] == ["snapshot_missing"]


@pytest.mark.parametrize("snapshot", [False, True])
def test_actual_typed_unavailable_performance_is_not_a_successful_read(tmp_path, monkeypatch, snapshot):
    from portfolio import paper_account
    unavailable = paper_account.unavailable_performance("autonomous")
    web, registry, _, latest = _setup_status(tmp_path, monkeypatch, performance=unavailable)
    if snapshot:
        latest.write_text('{"positions":[]}')
    st = web._portfolio_status(registry.get("autonomous"))["status"]
    assert st["read_status"] == ("partial" if snapshot else "unavailable")
    assert st["performance_status"] == "unavailable"
    assert st["performance_as_of"] is None
    assert st["nav"] is None and st["total_return_pct"] is None
    assert st["holdings"] == (0 if snapshot else None)
    assert "performance_unavailable" in st["status_reasons"]
    assert "performance" not in st.get("failed_sources", [])


@pytest.mark.parametrize("snapshot", [False, True])
def test_provisional_performance_remains_usable_and_qualified(tmp_path, monkeypatch, snapshot):
    perf = _available_performance()
    perf["availability"] = {"status": "provisional", "as_of": "2026-11-05",
                            "history_status": "partial", "valuation_basis": "last_recorded_nav"}
    web, registry, _, latest = _setup_status(tmp_path, monkeypatch, performance=perf)
    if snapshot:
        latest.write_text('{"positions":[]}')
    st = web._portfolio_status(registry.get("autonomous"))["status"]
    assert st["read_status"] == "partial"
    assert st["nav"] == 1_000_000.0 and st["total_return_pct"] == 4.0
    assert st["performance_status"] == "provisional" and st["performance_as_of"] == "2026-11-05"
    assert "performance_provisional" in st["status_reasons"]
    assert "performance_unavailable" not in st["status_reasons"]
    assert not st.get("failed_sources")


def test_missing_performance_qualification_does_not_cache_as_healthy(tmp_path, monkeypatch):
    perf = _available_performance()
    perf.pop("availability")
    web, registry, _, latest = _setup_status(tmp_path, monkeypatch, performance=perf)
    latest.write_text('{"positions":[]}')
    monkeypatch.setattr(registry, "all_portfolios", lambda: [registry.get("autonomous")])
    payload = _body(web.api_portfolios())
    st = payload["portfolios"][0]["status"]
    assert st["read_status"] == "partial"
    assert st["performance_status"] is None
    assert st["status_reasons"] == ["performance_unavailable"]
    assert "payload" not in web._portfolios_cache


@pytest.mark.parametrize("status", [None, "partial", "unavailable"])
def test_new_unqualified_rows_are_not_cached(monkeypatch, status):
    from app import web
    from portfolio import registry
    monkeypatch.setattr(registry, "all_portfolios", lambda: [registry.get("autonomous")])
    row = {"id": "autonomous", "status": {} if status is None else {"read_status": status}}
    monkeypatch.setattr(web, "_portfolio_status", lambda _meta: row)
    assert _body(web.api_portfolios())["portfolios"] == [row]
    assert "payload" not in web._portfolios_cache and "ts" not in web._portfolios_cache


@pytest.mark.parametrize("case", ["missing_status", "partial", "unavailable", "wrong_rows", "wrong_row"])
def test_existing_unqualified_cache_is_rebuilt(monkeypatch, case):
    from app import web
    from portfolio import registry
    rows = [{"id": "old", "status": {}}]
    if case in ("partial", "unavailable"):
        rows[0]["status"]["read_status"] = case
    elif case == "wrong_rows":
        rows = {}
    elif case == "wrong_row":
        rows = [None]
    web._portfolios_cache.update(payload={"portfolios": rows}, ts=web.time.time())
    calls = []
    monkeypatch.setattr(registry, "all_portfolios", lambda: [registry.get("autonomous")])
    def healthy(meta):
        calls.append(meta["id"])
        return {"id": "autonomous", "status": {"read_status": "available", "nav": 77}}
    monkeypatch.setattr(web, "_portfolio_status", healthy)
    payload = _body(web.api_portfolios())
    assert payload["portfolios"][0]["id"] == "autonomous"
    assert calls == ["autonomous"]
    assert web._portfolios_cache["payload"] == payload


def test_existing_healthy_cache_keeps_current_ttl(monkeypatch):
    from app import web
    from portfolio import registry
    payload = {"portfolios": [{"id": "autonomous", "status": {"read_status": "available", "nav": 12}}]}
    web._portfolios_cache.update(payload=payload, ts=web.time.time())
    monkeypatch.setattr(registry, "all_portfolios", lambda: pytest.fail("fresh healthy cache was rebuilt"))
    assert _body(web.api_portfolios()) == payload


def test_actual_asgi_registry_failure_and_recovery(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    web, registry, _, latest = _setup_status(tmp_path, monkeypatch)
    latest.write_text('{"positions":[],"as_of":"2026-11-06"}')
    meta = registry.get("autonomous")
    def fail():
        raise RuntimeError("secret /Users/private/registry")
    monkeypatch.setattr(registry, "all_portfolios", fail)
    app = FastAPI()
    app.include_router(web.router)
    with TestClient(app) as client:
        bad = client.get("/api/portfolios")
        assert bad.status_code == 503
        assert bad.json()["error"] == "portfolios_unavailable"
        assert bad.json()["portfolios"] is None
        assert "secret" not in bad.text
        monkeypatch.setattr(registry, "all_portfolios", lambda: [meta])
        good = client.get("/api/portfolios")
    assert good.status_code == 200
    row = good.json()["portfolios"][0]["status"]
    assert row["read_status"] == "available"
    assert row["holdings"] == 0 and row["nav"] == 1_000_000.0
    assert row["performance_as_of"] == "2026-11-05" and row["as_of"] == "2026-11-06"


def test_self_directed_zero_is_real_and_reads_are_snapshot_only(monkeypatch):
    from app import web
    from portfolio import self_directed, registry
    calls = []
    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {}})
    def prices(held, refresh=False):
        assert held == [] and refresh is False
        return {}
    monkeypatch.setattr(web, "_live_prices", prices)
    def book(**kwargs):
        calls.append(kwargs)
        return {"nav": 100, "valuation_complete": True, "positions": [],
                "unpriced_tickers": [], "allocation": {"cash_pct": 0, "total_return_pct": 0, "n_positions": 0}}
    monkeypatch.setattr(self_directed, "book", book)
    st = web._portfolio_status(registry.get("self_directed"))["status"]
    assert st["read_status"] == "available" and st["holdings"] == 0 and st["cash_pct"] == 0
    assert calls == [{"prices": {}, "read_only": True, "resolve_missing_prices": False}]
    assert not any(k in st for k in ("vs_spy_pct", "vs_defensive_pct", "vs_benchmark_pct"))


@pytest.mark.parametrize("book", [None, {"allocation": []}, {"allocation": {"n_positions": True}}])
def test_malformed_self_directed_book_does_not_become_empty(monkeypatch, book):
    from app import web
    from portfolio import self_directed, registry
    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {}})
    monkeypatch.setattr(web, "_live_prices", lambda *_a, **_k: {})
    monkeypatch.setattr(self_directed, "book", lambda **_kw: book)
    st = web._portfolio_status(registry.get("self_directed"))["status"]
    assert st["read_status"] == "unavailable" and st["holdings"] is None
    assert st["failed_sources"] == ["book"]


def test_benchmark_failure_preserves_self_directed_book(monkeypatch):
    from app import web
    from brain import benchmark_ledger
    from portfolio import self_directed, registry
    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {}})
    monkeypatch.setattr(web, "_live_prices", lambda *_a, **_k: {})
    monkeypatch.setattr(self_directed, "book", lambda **_kw: {
        "nav": 100, "valuation_complete": True, "positions": [],
        "allocation": {"cash_pct": 1, "total_return_pct": 0, "n_positions": 0},
    })
    monkeypatch.setattr(benchmark_ledger, "compare_book_to_ledger",
                        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("secret benchmark")))
    st = web._portfolio_status(registry.get("self_directed"))["status"]
    assert st["read_status"] == "partial" and st["nav"] == 100 and st["cash_pct"] == 100
    assert st["failed_sources"] == ["benchmark"]
    assert "secret" not in json.dumps(st)


def test_managed_nonpositive_nav_keeps_cash_percentage_unknown(tmp_path, monkeypatch):
    perf = _available_performance()
    perf.update(current_nav=-1, cash=100)
    web, registry, _, latest = _setup_status(tmp_path, monkeypatch, performance=perf)
    latest.write_text('{"positions":[]}')
    st = web._portfolio_status(registry.get("autonomous"))["status"]
    assert st["cash_pct"] is None
    assert st["performance_as_of"] == "2026-11-05"


_NODE_RUNNER = "const vm = require('node:vm');\nconst assert = require('node:assert/strict');\nconst input = JSON.parse(process.argv[1]);\nconst elements = {'pf-switch': {innerHTML: ''}};\nconst ctx = {\n  assert, _portfolio: 'autonomous', _portfolios: [], _portfoliosStatus: 'loading',\n  _path0: '/', _hashOwnsBook: false, _pendingSelfSelect: false,\n  _calls: [], _prefetches: 0,\n  E: id => elements[id] || (elements[id] = {innerHTML: ''}),\n  document: {documentElement: {getAttribute: () => 'en'}},\n  window: {requestAnimationFrame: () => {}}, setTimeout: () => {},\n  revealActivePortfolioTab: () => {},\n  esc: value => String(value == null ? '' : value).replace(/&/g, '&amp;').replace(/</g, '&lt;'),\n  _pfOrdered: rows => rows, _ccySymOf: () => '$',\n  _pfLabel: row => row.name || row.id,\n  _fmtPctSigned: value => value == null ? '—' : String(value) + '%',\n};\nctx.setPortfolio = (id, opts) => {\n  ctx._calls.push([id, opts]); ctx._portfolio = id; ctx._hashOwnsBook = true;\n};\nctx._schedulePortfolioPrefetch = () => { ctx._prefetches += 1; };\nvm.createContext(ctx);\nconst pending = vm.runInContext(input.source + '\\n;(async function () {\\n' + input.body + '\\n})()',\n  ctx, {timeout: 1500});\nPromise.resolve(pending).then(() => process.stdout.write('ok\\n')).catch(error => {\n  process.stderr.write(String(error.stack || error) + '\\n'); process.exitCode = 1;\n});\n"

_CLIENT_CASES = {
    "http_failure": "_portfolios = [{id:'autonomous'}]; var old = _portfolios;\nfetch = async () => ({ok:false});\nawait loadPortfolios();\nassert.equal(_portfoliosStatus,'unavailable');\nassert.strictEqual(_portfolios,old);\nassert.ok(E('pf-switch').innerHTML.includes('Portfolios unavailable'));\nassert.equal(_prefetches,0);",
    "network_failure": "_portfolios = [{id:'autonomous'}]; var old = _portfolios;\nfetch = async () => { throw new Error('secret transport'); };\nawait loadPortfolios();\nassert.equal(_portfoliosStatus,'unavailable');\nassert.strictEqual(_portfolios,old);\nassert.ok(E('pf-switch').innerHTML.includes('Portfolios unavailable'));\nassert.ok(!E('pf-switch').innerHTML.includes('secret'));",
    "malformed_payload": "var old = [{id:'autonomous'}];\nfor (var bad of [null,{}, {portfolios:null}, {portfolios:{}}, {portfolios:'wrong'}, {portfolios:0}]) {\n  _portfolios=old; _portfoliosStatus='available';\n  fetch=async()=>({ok:true,json:async()=>bad});\n  await loadPortfolios();\n  assert.equal(_portfoliosStatus,'unavailable');\n  assert.strictEqual(_portfolios,old);\n  assert.ok(E('pf-switch').innerHTML.includes('Portfolios unavailable'));\n}\nassert.equal(_prefetches,0);",
    "malformed_rows": "var old = [{id:'autonomous'}];\nfor (var rows of [[null],[[]],[{}],[{id:1}],[{id:''}]]) {\n  _portfolios=old; _portfoliosStatus='available';\n  fetch=async()=>({ok:true,json:async()=>({portfolios:rows})});\n  await loadPortfolios();\n  assert.equal(_portfoliosStatus,'unavailable');\n  assert.strictEqual(_portfolios,old);\n}\nassert.equal(_prefetches,0);",
    "typed_unavailable": "_portfolios=[{id:'autonomous'}];var old=_portfolios;\nfetch=async()=>({ok:true,json:async()=>({read_status:'unavailable',portfolios:[{id:'flagship'}]})});\nawait loadPortfolios();\nassert.equal(_portfoliosStatus,'unavailable');assert.strictEqual(_portfolios,old);\nassert.equal(_portfolio,'autonomous');assert.equal(_prefetches,0);",
    "recovery": "fetch=async()=>({ok:false});await loadPortfolios();\nassert.equal(_portfoliosStatus,'unavailable');\nvar rows=[{id:'autonomous',name:'US Brain',status:{nav:500,read_status:'available'}}];\nfetch=async()=>({ok:true,json:async()=>({portfolios:rows,default:'autonomous'})});\nawait loadPortfolios();\nassert.equal(_portfoliosStatus,'available');assert.strictEqual(_portfolios,rows);\nassert.ok(E('pf-switch').innerHTML.includes('US Brain'));\nassert.ok(!E('pf-switch').innerHTML.includes('Portfolios unavailable'));\nassert.equal(_prefetches,1);",
    "partial_row": "_portfoliosStatus='available';\n_portfolios=[{id:'autonomous',name:'US Brain',status:{nav:500,total_return_pct:2,read_status:'partial'}}];\nrenderPortfolioSwitch();\nassert.ok(E('pf-switch').innerHTML.includes('PARTIAL'));\nassert.ok(E('pf-switch').innerHTML.includes('$500'));\nassert.ok(E('pf-switch').innerHTML.includes('US Brain'));",
    "unavailable_archived_row": "_portfoliosStatus='available';\n_portfolios=[{id:'flagship',name:'Flagship',lifecycle:'archived',active:false,status:{nav:null,read_status:'unavailable'}}];\nrenderPortfolioSwitch();\nvar html=E('pf-switch').innerHTML;\nassert.ok(html.includes('UNAVAILABLE'));assert.ok(html.includes('ARCHIVED'));\nassert.ok(html.includes('—'));assert.ok(!html.includes('$0'));",
    "root_default": "_portfolio='flagship';\nvar rows=[{id:'autonomous',status:{read_status:'available'}},{id:'flagship',status:{read_status:'available'}}];\nfetch=async()=>({ok:true,json:async()=>({portfolios:rows,default:'autonomous'})});\nawait loadPortfolios();\nassert.equal(_portfolio,'autonomous');assert.strictEqual(_portfolios,rows);\nassert.equal(_calls.length,0);assert.equal(_prefetches,1);",
    "hash_owned": "_portfolio='china';_hashOwnsBook=true;\nfetch=async()=>({ok:true,json:async()=>({portfolios:[{id:'autonomous'},{id:'china'}],default:'autonomous'})});\nawait loadPortfolios();\nassert.equal(_portfolio,'china');assert.equal(_calls.length,0);assert.equal(_prefetches,1);",
    "invalid_hash_replacement": "_portfolio='missing';_hashOwnsBook=true;\nfetch=async()=>({ok:true,json:async()=>({portfolios:[{id:'autonomous'}],default:'autonomous'})});\nawait loadPortfolios();\nassert.equal(_portfolio,'autonomous');assert.equal(_calls.length,1);\nassert.equal(_calls[0][0],'autonomous');assert.equal(_calls[0][1].replace,true);\nassert.equal(_prefetches,1);",
    "pending_self_selection": "_pendingSelfSelect=true;\nfetch=async()=>({ok:true,json:async()=>({portfolios:[{id:'autonomous'},{id:'self_directed'}],default:'autonomous'})});\nawait loadPortfolios();\nassert.equal(_portfolio,'self_directed');assert.equal(_pendingSelfSelect,false);\nassert.equal(_calls.length,1);assert.equal(_calls[0][1].replace,true);assert.equal(_prefetches,1);",
    "route_owned": "_path0='/research';_portfolio='flagship';\nfetch=async()=>({ok:true,json:async()=>({portfolios:[{id:'autonomous'},{id:'flagship'}],default:'autonomous'})});\nawait loadPortfolios();\nassert.equal(_portfolio,'flagship');assert.equal(_calls.length,0);assert.equal(_prefetches,1);",
    "valid_empty_registry": "fetch=async()=>({ok:true,json:async()=>({portfolios:[],default:'autonomous'})});\nawait loadPortfolios();\nassert.equal(_portfoliosStatus,'available');assert.equal(_portfolios.length,0);\nassert.equal(E('pf-switch').innerHTML,'');assert.equal(_prefetches,1);"
}

@lru_cache(maxsize=1)
def _node_runtime():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable for the isolated dashboard behavior checks")
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
    html = (Path(__file__).parents[1] / "app/static/index.html").read_text()
    sections = []
    for start in ("function renderPortfolioSwitch()", "async function loadPortfolios()"):
        begin = html.index(start)
        sections.append(html[begin:html.index("\n}", begin) + 2])
    return "\n".join(sections)


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




@pytest.mark.parametrize("case", ["http_failure","network_failure","malformed_payload","malformed_rows","typed_unavailable","recovery","partial_row","unavailable_archived_row","root_default","hash_owned","invalid_hash_replacement","pending_self_selection","route_owned","valid_empty_registry"])
def test_actual_switcher_client(case):
    _run_client(case)
