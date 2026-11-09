"""Truthful Self-Directed valuation through the actual book, HTTP route and UI guards.

A missing market mark is not a cost-basis valuation. Dated carry keeps its original
vintage, and a partial book must not authorize either order entry point.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from portfolio import self_directed as SD

pytestmark = pytest.mark.strict_book_dirs
ROOT = Path(__file__).parents[1]


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    data = tmp_path / "self_directed"
    for name, path in {
        "_DATA": data,
        "_ACCOUNT_PATH": data / "account.json",
        "_FILLS_PATH": data / "fills.jsonl",
        "_PENDING_PATH": data / "pending.json",
        "_THESES_PATH": data / "theses.json",
        "_NAV_PATH": data / "nav_history.jsonl",
        "_PUBLISHED_PATH": tmp_path / "published" / "latest.json",
    }.items():
        monkeypatch.setattr(SD, name, path)
    monkeypatch.setattr(SD, "_today", lambda: "2026-06-02")
    monkeypatch.setattr(SD, "_market_status", lambda: {"is_open": False, "session": "closed"})
    monkeypatch.setattr(SD, "_carry_stale_max_days", lambda: 30)
    monkeypatch.setattr(SD, "_price_resolver", None)
    SD.bootstrap_book_dir()
    return data


def _state(positions: dict, *, cash: float = 500_000.0) -> dict:
    return {
        "inception_date": "2026-05-01",
        "starting_nav": 1_000_000.0,
        "cash": cash,
        "positions": positions,
    }


def _pos(*, shares=1_000.0, avg_cost=100.0, current=None, current_asof=None) -> dict:
    row = {"shares": shares, "avg_cost": avg_cost}
    if current is not None:
        row["current_price"] = current
    if current_asof is not None:
        row["current_price_asof"] = current_asof
    return row


def _read(prices=None):
    return SD.book(prices=prices or {}, read_only=True, resolve_missing_prices=False)


def _assert_unknown_totals(book):
    assert book["valuation_complete"] is False
    assert book["nav"] is None and book["invested"] is None
    assert all(row["weight"] is None for row in book["positions"])
    for name in (
        "cash_pct", "invested_pct", "gross", "largest_weight",
        "total_unrealized_pnl", "total_return_pct",
    ):
        assert book["allocation"][name] is None, name


@pytest.mark.parametrize("shares", [1_000.0, -1_000.0, 0.00000001, -0.00000001])
def test_any_signed_nonzero_unpriced_holding_makes_totals_unknown(sandbox, shares):
    SD._save_account(_state({"AAPL": _pos(shares=shares)}))
    book = _read()
    _assert_unknown_totals(book)
    assert book["unpriced_tickers"] == ["AAPL"]
    assert book["cash"] == 500_000.0
    assert book["allocation"]["n_positions"] == 1
    assert book["positions"][0]["current_price"] is None
    assert book["positions"][0]["market_value"] is None
    assert book["positions"][0].get("current_price_asof") is None


@pytest.mark.parametrize("asof", ["2026-06-02", "2026-06-01", "2026-05-03"])
def test_eligible_carry_preserves_original_vintage_and_market_value(sandbox, asof):
    SD._save_account(_state({
        "AAPL": _pos(current=150.0, current_asof=asof),
    }))
    book = _read()
    row = book["positions"][0]
    assert book["valuation_complete"] is True and book["unpriced_tickers"] == []
    assert book["nav"] == 650_000.0 and book["invested"] == 150_000.0
    assert row["current_price"] == 150.0
    assert row["current_price_asof"] == asof
    assert row["market_value"] == 150_000.0
    assert row["weight"] == pytest.approx(150_000.0 / 650_000.0, abs=1e-6)
    assert book["allocation"]["total_unrealized_pnl"] == 50_000.0


@pytest.mark.parametrize("asof", ["2026-06-03", "2026-05-02", "not-a-date", None])
def test_future_over_age_malformed_and_undated_carry_remain_unknown(sandbox, asof):
    SD._save_account(_state({
        "AAPL": _pos(current=150.0, current_asof=asof),
    }))
    book = _read()
    _assert_unknown_totals(book)
    assert book["unpriced_tickers"] == ["AAPL"]
    assert book["positions"][0].get("current_price_asof") is None


@pytest.mark.parametrize("price", [0, -1, float("nan"), float("inf"), "invalid"])
def test_invalid_supplied_prices_are_not_market_marks(sandbox, price):
    SD._save_account(_state({"AAPL": _pos()}))
    book = _read({"AAPL": price})
    _assert_unknown_totals(book)
    assert book["positions"][0]["current_price"] is None
    json.dumps(book, allow_nan=False)


def test_supplied_price_wins_without_borrowing_saved_date(sandbox, monkeypatch):
    SD._save_account(_state({
        "AAPL": _pos(current=150.0, current_asof="2026-06-01"),
    }))
    monkeypatch.setattr(SD, "_current_price", lambda _ticker: pytest.fail("no live lookup"))
    book = _read({"AAPL": 175.0})
    assert book["valuation_complete"] is True
    assert book["nav"] == 675_000.0
    assert book["positions"][0]["current_price"] == 175.0
    assert book["positions"][0].get("current_price_asof") is None


def test_optional_resolution_still_precedes_carry(sandbox, monkeypatch):
    SD._save_account(_state({
        "AAPL": _pos(current=150.0, current_asof="2026-06-01"),
    }))
    calls = []
    monkeypatch.setattr(SD, "_current_price", lambda ticker: calls.append(ticker) or 125.0)
    book = SD.book(prices={}, read_only=True, resolve_missing_prices=True)
    assert calls == ["AAPL"]
    assert book["valuation_complete"] is True
    assert book["nav"] == 625_000.0
    assert book["positions"][0]["current_price"] == 125.0
    assert book["positions"][0].get("current_price_asof") is None


def test_partial_book_keeps_cash_and_known_row_without_partial_totals(sandbox):
    SD._save_account(_state({
        "AAPL": _pos(shares=-1_000.0),
        "MSFT": _pos(shares=500.0, avg_cost=200.0),
    }, cash=-500.0))
    book = _read({"MSFT": 220.0})
    _assert_unknown_totals(book)
    by = {row["ticker"]: row for row in book["positions"]}
    assert book["unpriced_tickers"] == ["AAPL"] and book["cash"] == -500.0
    assert book["allocation"]["n_positions"] == 2
    assert by["MSFT"]["current_price"] == 220.0
    assert by["MSFT"]["market_value"] == 110_000.0
    assert by["MSFT"]["unrealized_pnl"] == 10_000.0
    assert by["AAPL"]["current_price"] is None


@pytest.mark.parametrize("cash", [1_000_000.0, 0.0, -123.0])
def test_empty_book_is_complete_known_cash(sandbox, cash):
    SD._save_account(_state({}, cash=cash))
    book = _read()
    assert book["valuation_complete"] is True and book["unpriced_tickers"] == []
    assert book["nav"] == cash and book["cash"] == cash and book["invested"] == 0.0
    assert book["allocation"]["n_positions"] == 0


def test_exact_zero_quantity_needs_no_market_mark(sandbox):
    SD._save_account(_state({"AAPL": _pos(shares=0.0)}))
    book = _read()
    assert book["valuation_complete"] is True and book["unpriced_tickers"] == []
    assert book["nav"] == 500_000.0 and book["invested"] == 0.0
    assert book["positions"][0]["market_value"] == 0.0
    assert book["positions"][0]["weight"] == 0.0


def test_read_only_carry_does_not_settle_fetch_or_rewrite_provenance(sandbox, monkeypatch):
    SD._save_account(_state({
        "AAPL": _pos(current=150.0, current_asof="2026-06-01"),
    }))
    before = {p.name: p.read_bytes() for p in sandbox.iterdir() if p.is_file()}
    monkeypatch.setattr(SD, "_current_price", lambda _ticker: pytest.fail("no live lookup"))
    monkeypatch.setattr(SD, "settle_pending", lambda **_kwargs: pytest.fail("no settlement"))
    book = _read()
    assert book["positions"][0]["current_price_asof"] == "2026-06-01"
    assert {p.name: p.read_bytes() for p in sandbox.iterdir() if p.is_file()} == before


def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import web

    app = FastAPI()
    app.include_router(web.router)
    return TestClient(app)


def test_registered_http_route_preserves_partial_known_values(sandbox, monkeypatch):
    from app import web

    SD._save_account(_state({
        "AAPL": _pos(), "MSFT": _pos(shares=500.0, avg_cost=200.0),
    }))
    monkeypatch.setattr(web, "_live_prices", lambda tickers: {"MSFT": 220.0})
    monkeypatch.setattr(web, "_attach_security_names", lambda rows: None)
    monkeypatch.setattr(SD, "_current_price", lambda _ticker: pytest.fail("no per-name lookup"))
    monkeypatch.setattr(SD, "settle_pending", lambda **_kwargs: pytest.fail("GET must not settle"))
    with _client() as client:
        response = client.get("/api/self_directed")
    assert response.status_code == 200
    book = response.json()
    _assert_unknown_totals(book)
    assert book["cash"] == 500_000.0 and len(book["positions"]) == 2
    assert next(row for row in book["positions"] if row["ticker"] == "MSFT")["market_value"] == 110_000.0


def test_http_failure_redacts_exception_but_keeps_unavailable_contract(sandbox, monkeypatch, caplog):
    secret = "sensitive-account-detail-735"
    monkeypatch.setattr(
        SD, "_load_account", lambda: (_ for _ in ()).throw(RuntimeError(secret))
    )
    with _client() as client:
        response = client.get("/api/self_directed")
    payload = response.json()
    assert response.status_code == 200 and payload["status"] == "unavailable"
    assert payload["reason_code"] == "self_directed_book_unreadable"
    assert payload["nav"] is None and payload["cash"] is None and payload["invested"] is None
    assert payload["valuation_complete"] is False
    assert payload["error"] == "self_directed_unavailable"
    assert secret not in response.text and secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_http_corruption_keeps_typed_quarantine_evidence(sandbox):
    raw = b"{invalid account data"
    SD._ACCOUNT_PATH.write_bytes(raw)
    with _client() as client:
        response = client.get("/api/self_directed")
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == "self_directed_account_invalid"
    assert payload["problems"] == ["unparseable"]
    assert payload["quarantine_file"]
    assert payload["valuation_complete"] is False
    assert payload["error"] == "self_directed_unavailable"
    assert SD._ACCOUNT_PATH.read_bytes() == raw
    quarantine = sandbox / Path(payload["quarantine_file"]).name
    assert quarantine.read_bytes() == raw


def _ui_state_source():
    html = (ROOT / "app/static/index.html").read_text()
    return html.split("// PBR-SELF-UNAVAILABLE:BEGIN", 1)[1].split(
        "// PBR-SELF-UNAVAILABLE:END", 1
    )[0]


def _node(script):
    result = subprocess.run(
        ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_actual_ui_classifier_preserves_precedence_and_partial_book_contract():
    script = _ui_state_source() + r"""
const cases = [
  [null, false, 'pending'],
  [null, true, 'unavailable'],
  [{status:'unavailable',valuation_complete:false,cash:1,positions:[]},true,'unavailable'],
  [{valuation_complete:false,cash:500000,positions:[{ticker:'AAPL'}],nav:null},true,'incomplete'],
  [{valuation_complete:false,cash:-500,positions:[{ticker:'AAPL'}],nav:999999},true,'incomplete'],
  [{valuation_complete:false,positions:[]},true,'unavailable'],
  [{valuation_complete:false,cash:1,positions:{}},true,'unavailable'],
  [{nav:null},true,'unavailable'],
  [{nav:0,cash:0,positions:[],valuation_complete:true},true,'ok'],
  [{nav:500000,cash:500000,positions:[]},true,'ok']
];
const assert = require('node:assert/strict');
for (const [book,settled,want] of cases) assert.equal(_selfBookState(book,settled),want);
console.log(JSON.stringify({cases:cases.length}));
"""
    assert _node(script) == {"cases": 10}


def test_actual_order_function_blocks_both_entry_points_until_book_is_ok():
    html = (ROOT / "app/static/index.html").read_text()
    order = "window.placeSelfOrder = function" + html.split(
        "window.placeSelfOrder = function", 1
    )[1].split("\nwindow.saveSelfThesis", 1)[0]
    script = _ui_state_source() + r"""
const assert = require('node:assert/strict');
var window = globalThis, _self = null, _selfSettled = false, _selfBusy = false;
var _selfSel = {ticker:'AAPL',price:100}, _selfUnit = 'shares', calls = [];
function E() {return {value:'1',disabled:false};}
function t(k) {return k;}
function esc(v) {return String(v);}
function fmtShares(v) {return String(v);}
function fmtNav(v) {return String(v);}
function _selfMsg() {}
function selfUpdateEst() {}
function refreshSelf() {return Promise.resolve();}
function fetch(url,options) {
  calls.push({url,options});
  return Promise.resolve({json:()=>Promise.resolve({ok:false})});
}
""" + order + r"""
(async()=>{
  const bad = [
    [null,false],
    [{status:'unavailable'},true],
    [{valuation_complete:false,cash:500000,positions:[{ticker:'AAPL'}],nav:null},true]
  ];
  for (const [book,settled] of bad) {
    for (const ticker of [undefined,'AAPL']) {
      _self=book;_selfSettled=settled;_selfBusy=false;
      placeSelfOrder('buy',ticker);
      await new Promise(resolve=>setImmediate(resolve));
    }
  }
  assert.equal(calls.length,0,'non-ok books must never POST an order');
  _self={nav:500000,cash:500000,positions:[],valuation_complete:true};_selfSettled=true;
  for (const ticker of [undefined,'AAPL']) {
    _selfBusy=false;placeSelfOrder('buy',ticker);
    await new Promise(resolve=>setImmediate(resolve));
  }
  assert.equal(calls.length,2,'both complete-book entry points remain available');
  for (const call of calls) {
    assert.equal(call.url,'/api/self_directed/order');
    assert.equal(call.options.method,'POST');
  }
  console.log(JSON.stringify({blocked:6,positive:2}));
})().catch(e=>{console.error(e);process.exitCode=1;});
"""
    assert _node(script) == {"blocked": 6, "positive": 2}
