"""Dashboard display carry must use the canonical portfolio.marks horizon."""
from __future__ import annotations

import json


def _write_snapshot(base, as_of: str) -> None:
    (base / "latest.json").write_text(json.dumps({
        "as_of": as_of,
        "market_status": {"open": False, "trading_day": True},
        "positions": [{"ticker": "AAPL", "current_price": 150.0}],
    }))


def test_persisted_book_quotes_follow_canonical_carry_horizon(tmp_path, monkeypatch):
    from app import web
    from portfolio import marks

    base = tmp_path / "autonomous"
    base.mkdir()
    _write_snapshot(base, "2026-08-06")
    monkeypatch.setattr(web, "_portfolio_dir", lambda pid=None: base)

    monkeypatch.setattr(marks, "_stale_max_days", lambda: 5)
    assert web._persisted_book_quotes("autonomous", ["AAPL"], asof="2026-08-12") == {}

    monkeypatch.setattr(marks, "_stale_max_days", lambda: 6)
    quote = web._persisted_book_quotes("autonomous", ["AAPL"], asof="2026-08-12")
    assert quote["AAPL"]["price_local"] == 150.0
    assert quote["AAPL"]["stale_days"] == 6


def test_terminal_snapshot_uses_same_canonical_horizon(monkeypatch):
    from app import web
    from portfolio import marks

    current = {
        "source": "terminal_snapshot", "as_of": "2026-08-06",
        "time_kind": "snapshot_market_date", "price_local": 150.0,
    }
    monkeypatch.setattr(marks, "_stale_max_days", lambda: 5)
    assert web._select_dashboard_quote(current, None, asof="2026-08-12") is None

    monkeypatch.setattr(marks, "_stale_max_days", lambda: 6)
    assert web._select_dashboard_quote(current, None, asof="2026-08-12") == current


def test_canonical_horizon_resolution_failure_rejects_dashboard_carry(tmp_path, monkeypatch):
    from app import web
    from portfolio import marks

    base = tmp_path / "autonomous"
    base.mkdir()
    _write_snapshot(base, "2026-08-12")
    monkeypatch.setattr(web, "_portfolio_dir", lambda pid=None: base)
    monkeypatch.setattr(marks, "_stale_max_days", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    assert web._persisted_book_quotes("autonomous", ["AAPL"], asof="2026-08-12") == {}
    current = {
        "source": "terminal_snapshot", "as_of": "2026-08-12",
        "time_kind": "snapshot_market_date", "price_local": 150.0,
    }
    assert web._select_dashboard_quote(current, None, asof="2026-08-12") is None
