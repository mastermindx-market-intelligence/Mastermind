"""Critical account reconciliation is atomic and visible when unavailable."""
from __future__ import annotations

import json
from pathlib import Path


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

    critical = html[html.index("function _fetchPortfolioCritical(id)") : html.index("function _fetchPortfolioDetails", html.index("function _fetchPortfolioCritical(id)"))]
    assert "criticalStatus: book ? 'ready' : 'unavailable'" in critical
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
