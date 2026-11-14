"""Critical account reconciliation is atomic and visible when unavailable."""
from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import pytest


def _body(resp):
    return json.loads(resp.body)


class _FailSecondGet(dict):
    def __init__(self):
        super().__init__({"AAPL": {"source": "test"}, "MSFT": {"source": "test"}})
        self.calls = 0

    def get(self, key, default=None):
        self.calls += 1
        if self.calls >= 2:
            raise RuntimeError("secret /Users/private/account token=do-not-return")
        return super().get(key, default)


def _seed_snapshot(tmp_path: Path) -> dict:
    payload = {
        "as_of": "2026-09-17",
        "summary": "persisted strategy snapshot",
        "positions": [
            {"ticker": "AAPL", "weight": 0.20, "entry_price": 100.0},
            {"ticker": "MSFT", "weight": 0.15, "entry_price": 200.0},
        ],
        "rejected": [],
    }
    (tmp_path / "latest.json").write_text(json.dumps(payload))
    return payload


def _wire_account(monkeypatch, web, paper_account):
    monkeypatch.setattr(web, "_cached_zh", lambda _text: None)
    monkeypatch.setattr(web, "_account_state_probe", lambda _pid: None)
    monkeypatch.setattr(web, "_book_marks", lambda _pid: {"AAPL": 150.0, "MSFT": 250.0})
    monkeypatch.setattr(paper_account, "positions_pnl", lambda _prices, portfolio_id=None: {
        "AAPL": {"shares": 10, "avg_cost": 100.0, "current_price": 150.0, "market_value": 1500.0,
                 "unrealized_pnl": 500.0, "unrealized_pct": 50.0},
        "MSFT": {"shares": 5, "avg_cost": 200.0, "current_price": 250.0, "market_value": 1250.0,
                 "unrealized_pnl": 250.0, "unrealized_pct": 25.0},
    })
    monkeypatch.setattr(paper_account, "nav", lambda _prices, portfolio_id=None: 10_000.0)
    monkeypatch.setattr(paper_account, "_load_account", lambda _pid=None: {
        "cash": 7_250.0, "starting_nav": 9_000.0, "inception_date": "2026-09-01"
    })


def test_mid_overlay_failure_rolls_back_entire_account_enrichment(tmp_path, monkeypatch):
    from app import web
    from portfolio import paper_account, registry

    persisted = _seed_snapshot(tmp_path)
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    monkeypatch.setattr(web, "_attach_security_names", lambda _rows: None)
    monkeypatch.setattr(web, "_brain_book_module", lambda _pid: None)
    monkeypatch.setattr(registry, "is_archived", lambda _pid: False)
    _wire_account(monkeypatch, web, paper_account)
    monkeypatch.setattr(web, "_book_quote_provenance", lambda _pid, _tickers: _FailSecondGet())

    response = web.api_portfolio("autonomous")
    payload = _body(response)
    assert response.status_code == 200
    assert payload["positions"] == persisted["positions"]
    assert "account_preview" not in payload
    assert payload["account_reconciliation_status"] == "unavailable"
    assert payload["snapshot_status"] == "partial"
    assert payload["failed_sources"] == ["account_reconciliation"]
    assert "secret /Users/private/account" not in response.body.decode()
    assert "do-not-return" not in response.body.decode()


def test_successful_overlay_commits_account_preview_and_positions_together(tmp_path, monkeypatch):
    from app import web
    from portfolio import paper_account, registry

    _seed_snapshot(tmp_path)
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    monkeypatch.setattr(web, "_attach_security_names", lambda _rows: None)
    monkeypatch.setattr(web, "_brain_book_module", lambda _pid: None)
    monkeypatch.setattr(registry, "is_archived", lambda _pid: False)
    _wire_account(monkeypatch, web, paper_account)
    monkeypatch.setattr(web, "_book_quote_provenance", lambda _pid, _tickers: {})

    payload = _body(web.api_portfolio("autonomous"))
    assert payload["account_reconciliation_status"] == "available"
    assert payload["account_preview"]["current_nav"] == 10_000.0
    assert payload["positions"][0]["current_price"] == 150.0
    assert payload["positions"][1]["current_price"] == 250.0


def test_critical_client_carries_partial_status_and_positions_warn_before_empty():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    critical = html[html.index("function _fetchPortfolioCritical(id, onAvailability)") : html.index("function _fetchPortfolioDetails", html.index("function _fetchPortfolioCritical(id, onAvailability)"))]
    assert "decisionAvailability: availability" in critical
    assert "if (onAvailability) onAvailability(availability)" in critical
    assert "book.account_preview && book.account_preview.availability" in critical
    assert "book: book" in critical

    start = html.index("function renderPositions()")
    end = html.index("window.toggleExpand", start)
    render = html[start:end]
    assert "b.account_reconciliation_status === 'unavailable'" in render
    assert "Account reconciliation unavailable" in render
    assert render.index("b.account_reconciliation_status === 'unavailable'") < render.index("if (!positions.length)")
    assert "published strategy positions only" in render


def test_complete_live_marks_reconciliation_clears_account_warning():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    start = html.index("function _mergeLiveMarks(data)")
    end = html.index("function _scheduleLiveMarks", start)
    block = html[start:end]
    assert "Object.assign({}, row, mark)" in block
    assert "Object.assign(row, mark)" not in block
    assert "if (holdingsComplete) _book.positions = reconciled;" in block
    assert "holdingsComplete && _book.account_reconciliation_status === 'unavailable'" in block
    assert "_book.account_reconciliation_status = 'available'" in block
    assert "account_reconciliation" in block
    assert "_book.snapshot_status = 'available'" in block


def _setup_snapshot(tmp_path, monkeypatch):
    from app import web
    from portfolio import paper_account, registry

    persisted = _seed_snapshot(tmp_path)
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: tmp_path)
    monkeypatch.setattr(web, "_attach_security_names", lambda _rows: None)
    monkeypatch.setattr(web, "_brain_book_module", lambda _pid: None)
    monkeypatch.setattr(registry, "is_archived", lambda _pid: False)
    _wire_account(monkeypatch, web, paper_account)
    monkeypatch.setattr(web, "_book_quote_provenance", lambda _pid, _tickers: {})
    return web, paper_account, registry, persisted


def test_early_failure_removes_stale_preview_and_never_logs_exception_text(tmp_path, monkeypatch, caplog):
    web, _, _, persisted = _setup_snapshot(tmp_path, monkeypatch)
    persisted["account_preview"] = {"current_nav": 999_999, "stale": True}
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(persisted))
    before = path.read_bytes()

    def fail(_pid):
        raise RuntimeError("secret /Users/private/account token=do-not-return")

    monkeypatch.setattr(web, "_book_marks", fail)
    response = web.api_portfolio("autonomous")
    payload = _body(response)
    assert payload["positions"] == persisted["positions"]
    assert "account_preview" not in payload
    assert payload["account_reconciliation_status"] == "unavailable"
    assert payload["snapshot_status"] == "partial"
    assert "RuntimeError" in caplog.text
    assert "do-not-return" not in caplog.text + response.body.decode()
    assert "/Users/private/account" not in caplog.text + response.body.decode()
    assert path.read_bytes() == before


def test_failure_while_adding_account_only_row_rolls_back_all_prior_rows(tmp_path, monkeypatch):
    web, paper_account, _, persisted = _setup_snapshot(tmp_path, monkeypatch)
    monkeypatch.setattr(paper_account, "positions_pnl", lambda *_a, **_k: {
        "AAPL": {"avg_cost": 100.0, "current_price": 150.0, "market_value": 1500.0},
        "MSFT": {"avg_cost": 200.0, "current_price": 250.0, "market_value": 1250.0},
        "NVDA": {"avg_cost": 50.0, "current_price": 60.0, "market_value": 600.0},
    })

    class FailAccountOnly(dict):
        def get(self, key, default=None):
            if key == "NVDA":
                raise RuntimeError("private late-overlay detail")
            return {"source": "fixture"}

    monkeypatch.setattr(web, "_book_quote_provenance", lambda *_a: FailAccountOnly())
    payload = _body(web.api_portfolio("autonomous"))
    assert payload["positions"] == persisted["positions"]
    assert "account_preview" not in payload
    assert payload["account_reconciliation_status"] == "unavailable"
    assert payload["failed_sources"] == ["account_reconciliation"]


def test_account_only_holdings_commit_when_published_strategy_has_no_rows(tmp_path, monkeypatch):
    web, _, _, persisted = _setup_snapshot(tmp_path, monkeypatch)
    persisted["positions"] = []
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(persisted))
    before = path.read_bytes()
    payload = _body(web.api_portfolio("autonomous"))
    assert payload["account_reconciliation_status"] == "available"
    assert {p["ticker"] for p in payload["positions"]} == {"AAPL", "MSFT"}
    assert all(p["sleeve"] == "account" and p["live_only"] for p in payload["positions"])
    assert payload["account_preview"]["current_nav"] == 10_000.0
    assert path.read_bytes() == before


def test_actual_read_only_invalid_account_probe_survives_overlay_failure(tmp_path, monkeypatch):
    from app import web

    real_probe = web._account_state_probe
    web, paper_account, _, persisted = _setup_snapshot(tmp_path, monkeypatch)
    path = tmp_path / "invalid-account.json"
    path.write_text("{ secret-fixture malformed")
    before = path.read_bytes()
    before_names = sorted(p.name for p in tmp_path.iterdir())
    monkeypatch.setattr(paper_account, "_paths", lambda _pid=None: {"account": path})
    monkeypatch.setattr(web, "_account_state_probe", real_probe)
    monkeypatch.setattr(web, "_book_quote_provenance", lambda *_a: _FailSecondGet())
    response = web.api_portfolio("autonomous")
    payload = _body(response)
    assert payload["positions"] == persisted["positions"]
    assert payload["account_reconciliation_status"] == "unavailable"
    assert payload["account_state"]["status"] == "invalid"
    assert payload["account_state"]["quarantine_sha16"] == hashlib.sha256(before).hexdigest()[:16]
    assert payload["account_state"]["problems"]
    assert all(isinstance(p, str) for p in payload["account_state"]["problems"])
    assert "secret-fixture" not in response.body.decode()
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == before_names


@pytest.mark.parametrize("reasons", [["freshness"], ["account_reconciliation"]])
def test_failed_overlay_retains_existing_failure_reasons_without_duplicate(tmp_path, monkeypatch, reasons):
    web, _, _, persisted = _setup_snapshot(tmp_path, monkeypatch)
    persisted["failed_sources"] = reasons
    persisted["snapshot_status"] = "partial"
    (tmp_path / "latest.json").write_text(json.dumps(persisted))
    monkeypatch.setattr(web, "_book_quote_provenance", lambda *_a: _FailSecondGet())
    payload = _body(web.api_portfolio("autonomous"))
    assert payload["account_reconciliation_status"] == "unavailable"
    assert payload["snapshot_status"] == "partial"
    assert payload["failed_sources"] == list(dict.fromkeys(reasons + ["account_reconciliation"]))


def test_archived_book_retains_frozen_preview_and_never_reads_live_marks(tmp_path, monkeypatch):
    web, _, registry, persisted = _setup_snapshot(tmp_path, monkeypatch)
    monkeypatch.setattr(registry, "is_archived", lambda _pid: True)
    frozen = {"current_nav": 12345, "frozen_as_of": "2026-09-01", "series": [], "note": "frozen"}
    monkeypatch.setattr(web, "_archived_performance", lambda _pid: frozen)
    calls = []

    def forbidden(_pid):
        calls.append(_pid)
        raise AssertionError("archived book requested live marks")

    monkeypatch.setattr(web, "_book_marks", forbidden)
    payload = _body(web.api_portfolio("autonomous"))
    assert calls == []
    assert payload["positions"] == persisted["positions"]
    assert payload["archived"] is True
    assert payload["account_preview"] == {"current_nav": 12345, "frozen_as_of": "2026-09-01"}
    assert "account_reconciliation_status" not in payload


def test_actual_asgi_portfolio_route_exposes_atomic_partial_snapshot(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    web, _, _, persisted = _setup_snapshot(tmp_path, monkeypatch)
    monkeypatch.setattr(web, "_book_quote_provenance", lambda *_a: _FailSecondGet())
    app = FastAPI()
    app.include_router(web.router)
    with TestClient(app) as client:
        response = client.get("/api/portfolio", params={"portfolio": "autonomous"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["positions"] == persisted["positions"]
    assert payload["account_reconciliation_status"] == "unavailable"
    assert payload["failed_sources"] == ["account_reconciliation"]
    assert "account_preview" not in payload


def test_decision_availability_returns_before_snapshot_or_account_overlay(tmp_path, monkeypatch):
    from app import decision_availability, web

    calls = []
    evidence = {"schema": "mastermind.bot.decision_availability.v1", "portfolio_id": "autonomous"}

    def read(pid, **kwargs):
        calls.append((pid, kwargs))
        return evidence

    monkeypatch.setattr(decision_availability, "read_decision_availability", read)
    monkeypatch.setattr(web, "_portfolio_dir", lambda *_a: pytest.fail("decision view read strategy snapshot"))
    monkeypatch.setattr(web, "_book_marks", lambda *_a: pytest.fail("decision view read account quotes"))
    response = web.api_portfolio("autonomous", view="decision_availability")
    assert _body(response) == evidence
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == 1 and calls[0][0] == "autonomous"
    assert callable(calls[0][1]["inspect_settlement_prices"])
    assert callable(calls[0][1]["inspect_provider_diagnostics"])


def test_unsupported_view_returns_before_snapshot_or_account_overlay(monkeypatch):
    from app import web

    monkeypatch.setattr(web, "_portfolio_dir", lambda *_a: pytest.fail("unsupported view read strategy snapshot"))
    monkeypatch.setattr(web, "_book_marks", lambda *_a: pytest.fail("unsupported view read quotes"))
    response = web.api_portfolio("autonomous", view="not-a-view")
    assert response.status_code == 400
    assert _body(response)["error"] == "unsupported_portfolio_view"


_NODE_RUNNER = "const vm = require('node:vm');\nconst assert = require('node:assert/strict');\nconst input = JSON.parse(process.argv[1]);\nconst elements = {positions: {innerHTML: ''}};\nconst ctx = {\n  assert, _portfolio: 'autonomous', _book: null, _perf: null, _liveMarks: null,\n  _self: null, _selfSettled: false, _portfolios: [], _trades: [], _expandedIdx: null,\n  _invalid: null, _calls: [],\n  E: id => elements[id] || (elements[id] = {innerHTML: '', style: {}}),\n  document: {documentElement: {getAttribute: () => 'en'}, querySelector: () => null},\n  t: key => key === 'pos.empty' ? 'GENERIC_EMPTY' : key,\n  esc: value => String(value == null ? '' : value),\n  securityName: row => row.name || '',\n  _ccySym: () => '$', pct: value => String(value), helpIcon: () => '',\n  pnlCell: () => ({cls: '', txt: 'marked'}), _heldPendingChange: () => null,\n  _bookInvalidHtml: () => 'CANONICAL_ACCOUNT_INVALID', _unavailHtml: () => 'UNAVAILABLE',\n  _isAvailabilityBook: () => false,\n  renderPerformance: () => {}, renderEquityCurve: () => {}, renderAutoBanner: () => {},\n  renderSafety: () => {}, renderAllocation: () => {},\n  renderLiveMarksStatus: () => {}, renderPortfolioSwitch: () => {},\n};\nctx._accountStateInvalid = () => ctx._invalid || (ctx._liveMarks && ctx._liveMarks.account_state) ||\n  (ctx._book && ctx._book.account_state) || null;\nctx.renderSelf = () => ctx._calls.push('self');\nctx._safeRender = (_label, fn) => fn();\nvm.createContext(ctx);\nconst pending = vm.runInContext(input.source + '\\n;(async function () {\\n' + input.body + '\\n})()',\n  ctx, {timeout: 1500});\nPromise.resolve(pending).then(() => process.stdout.write('ok\\n')).catch(error => {\n  process.stderr.write(String(error.stack || error) + '\\n');\n  process.exitCode = 1;\n});\n"

_CLIENT_CASES = {
    "incomplete_count": "var row = {ticker:'AAPL',current_price:100,weight:0.2,verdict:'hold'};\n_book = {positions:[row],account_reconciliation_status:'unavailable',snapshot_status:'partial',failed_sources:['account_reconciliation']};\nvar rows = _book.positions;\n_mergeLiveMarks({portfolio:'autonomous',positions:[{ticker:'AAPL',current_price:150}],pricing:{total_positions:2}});\nassert.strictEqual(_book.positions, rows);\nassert.strictEqual(_book.positions[0], row);\nassert.equal(row.current_price,100);\nassert.equal(_book.account_reconciliation_status,'unavailable');",
    "missing_pricing": "var row = {ticker:'AAPL',current_price:100,weight:0.2,verdict:'hold'};\n_book = {positions:[row],account_reconciliation_status:'unavailable',snapshot_status:'partial'};\nvar rows = _book.positions;\n_mergeLiveMarks({portfolio:'autonomous',positions:[{ticker:'AAPL',current_price:150}]});\nassert.strictEqual(_book.positions, rows);\nassert.equal(row.current_price,100);\nassert.equal(_liveMarks.pricing_partial,true);\nassert.equal(_book.account_reconciliation_status,'unavailable');",
    "error_response": "var row = {ticker:'AAPL',current_price:100,weight:0.2,verdict:'hold'};\n_book = {positions:[row],account_reconciliation_status:'unavailable',snapshot_status:'partial'};\nvar rows = _book.positions;\n_mergeLiveMarks({portfolio:'autonomous',error:'unavailable',positions:[{ticker:'AAPL',current_price:150}],pricing:{total_positions:1}});\nassert.strictEqual(_book.positions,rows);\nassert.equal(row.current_price,100);\nassert.equal(_book.account_reconciliation_status,'unavailable');",
    "complete_success": "var row = {ticker:'AAPL',current_price:100,weight:0.2,verdict:'hold',entry_price:80};\n_book = {positions:[row],account_reconciliation_status:'unavailable',snapshot_status:'partial',failed_sources:['account_reconciliation']};\nvar mark = {ticker:'AAPL',current_price:150,shares:10};\n_mergeLiveMarks({portfolio:'autonomous',positions:[mark],pricing:{total_positions:1}});\nassert.notStrictEqual(_book.positions[0],row);\nassert.equal(row.current_price,100);\nassert.equal(_book.positions[0].current_price,150);\nassert.equal(_book.positions[0].entry_price,80);\nassert.equal(_book.account_reconciliation_status,'available');\nassert.equal(_book.snapshot_status,'available');\nassert.deepEqual(_book.failed_sources,[]);\nassert.equal(mark.entry_price,undefined);",
    "unrelated_partial": "_book = {positions:[],account_reconciliation_status:'unavailable',snapshot_status:'partial',failed_sources:['freshness','account_reconciliation']};\n_mergeLiveMarks({portfolio:'autonomous',positions:[],pricing:{total_positions:0}});\nassert.equal(_book.account_reconciliation_status,'available');\nassert.equal(_book.snapshot_status,'partial');\nassert.deepEqual(_book.failed_sources,['freshness']);",
    "unknown_partial_missing": "_book = {positions:[],account_reconciliation_status:'unavailable',snapshot_status:'partial'};\n_mergeLiveMarks({portfolio:'autonomous',positions:[],pricing:{total_positions:0}});\nassert.equal(_book.account_reconciliation_status,'available');\nassert.equal(_book.snapshot_status,'partial');\nassert.equal(_book.failed_sources,undefined);",
    "unknown_partial_empty": "_book = {positions:[],account_reconciliation_status:'unavailable',snapshot_status:'partial',failed_sources:[]};\n_mergeLiveMarks({portfolio:'autonomous',positions:[],pricing:{total_positions:0}});\nassert.equal(_book.account_reconciliation_status,'available');\nassert.equal(_book.snapshot_status,'partial');\nassert.deepEqual(_book.failed_sources,[]);",
    "invalid_state": "var row = {ticker:'AAPL',current_price:100,weight:0.2,verdict:'hold'};\n_book = {positions:[row],account_reconciliation_status:'unavailable',snapshot_status:'partial'};\n_perf = {current_nav:1000};\nvar before = JSON.stringify(_book);\n_mergeLiveMarks({portfolio:'autonomous',account_state:{status:'invalid'},positions:[{ticker:'AAPL',current_price:150}],pricing:{total_positions:1},performance:{current_nav:9000}});\nassert.equal(JSON.stringify(_book),before);\nassert.equal(_perf.current_nav,1000);\nassert.ok(E('positions').innerHTML.includes('CANONICAL_ACCOUNT_INVALID'));\nassert.ok(!E('positions').innerHTML.includes('Account reconciliation unavailable'));",
    "invalid_transport_recovery": "var row = {ticker:'AAPL',current_price:100,weight:0.2,verdict:'hold'};\n_book = {positions:[row]};\n_perf = {current_nav:1000};\nvar invalid = {status:'invalid'};\n_mergeLiveMarks({portfolio:'autonomous',error:'live_marks_unavailable',account_state:invalid});\n_mergeLiveMarks({portfolio:'autonomous',error:'live_marks_unavailable'});\nassert.strictEqual(_liveMarks.account_state,invalid);\nassert.strictEqual(_book.positions[0],row);\nassert.equal(_perf.current_nav,1000);\nassert.ok(E('positions').innerHTML.includes('CANONICAL_ACCOUNT_INVALID'));\n_mergeLiveMarks({portfolio:'autonomous',positions:[{ticker:'AAPL',current_price:115}],pricing:{total_positions:1},performance:{current_nav:1015}});\nassert.equal(_liveMarks.account_state,undefined);\nassert.equal(_book.positions[0].current_price,115);\nassert.equal(_perf.current_nav,1015);\nassert.ok(!E('positions').innerHTML.includes('CANONICAL_ACCOUNT_INVALID'));",
    "warning_empty": "_book = {positions:[],account_reconciliation_status:'unavailable',snapshot_status:'partial'};\nrenderPositions();\nvar html = E('positions').innerHTML;\nassert.ok(html.includes('Account reconciliation unavailable'));\nassert.ok(html.includes('actual account holdings could not be reconciled'));\nassert.ok(!html.includes('GENERIC_EMPTY'));",
    "warning_rows": "_book = {positions:[{ticker:'AAPL',current_price:100,weight:0.2,verdict:'hold'}],account_reconciliation_status:'unavailable'};\nrenderPositions();\nvar html = E('positions').innerHTML;\nassert.ok(html.includes('Account reconciliation unavailable'));\nassert.ok(html.includes('AAPL'));\nassert.ok(html.indexOf('Account reconciliation unavailable') < html.indexOf('<table>'));",
    "ordinary_empty": "_book = {positions:[]};\nrenderPositions();\nassert.ok(E('positions').innerHTML.includes('GENERIC_EMPTY'));\nassert.ok(!E('positions').innerHTML.includes('Account reconciliation unavailable'));",
    "critical_snapshot": "var requests = [], observed = [];\nvar evidence = {portfolio_id:'autonomous',schema:'mastermind.bot.decision_availability.v1',current:{available:false}};\nvar book = {positions:[],account_reconciliation_status:'unavailable',snapshot_status:'partial',failed_sources:['account_reconciliation'],account_preview:{current_nav:999}};\n_isAvailabilityBook = () => true;\nfetch = async function(url, options) {\n  requests.push([url,options]);\n  return {ok:true,json:async () => url.includes('decision_availability') ? evidence : book};\n};\nvar snapshot = await _fetchPortfolioCritical('autonomous', value => observed.push(value));\nassert.strictEqual(snapshot.book,book);\nassert.strictEqual(snapshot.decisionAvailability,evidence);\nassert.strictEqual(observed[0],evidence);\nassert.equal(snapshot.performance.current_nav,undefined);\nassert.equal(snapshot.performance.load_status,'loading');\nassert.equal(requests.length,2);\nassert.equal(requests[0][1].cache,'no-store');\nassert.equal(requests[1][0],'/api/portfolio?portfolio=autonomous');\nassert.equal(snapshot.book.snapshot_status,'partial');",
    "foreign_portfolio": "_book = {positions:[]};\nvar book = _book;\n_liveMarks = {retained:true};\nvar marks = _liveMarks;\n_mergeLiveMarks({portfolio:'another-book',positions:[],pricing:{total_positions:0}});\nassert.strictEqual(_book,book);\nassert.strictEqual(_liveMarks,marks);\nassert.equal(_calls.length,0);",
    "self_directed": "_portfolio = 'self_directed';\n_book = {positions:[]};\nvar book = _book, self = {nav:123,positions:[]};\n_mergeLiveMarks({portfolio:'self_directed',book:self,positions:[],pricing:{total_positions:0}});\nassert.strictEqual(_book,book);\nassert.strictEqual(_self,self);\nassert.equal(_selfSettled,true);\nassert.ok(_calls.includes('self'));"
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
    for start, end in (
        ("function _performanceLoading()", "var _runsLoaded"),
        ("function renderPositions()", "window.toggleExpand"),
        ("function _mergeLiveMarks(data)", "function _scheduleLiveMarks"),
        ("function _fetchPortfolioCritical(", "function _fetchPortfolioDetails"),
    ):
        begin = html.index(start)
        sections.append(html[begin:html.index(end, begin)])
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


@pytest.mark.parametrize("case", ["incomplete_count","missing_pricing","error_response","complete_success","unrelated_partial","unknown_partial_missing","unknown_partial_empty","invalid_state","invalid_transport_recovery","warning_empty","warning_rows","ordinary_empty","critical_snapshot","foreign_portfolio","self_directed"])
def test_actual_client_reconciliation_and_rendering(case):
    _run_client(case)
