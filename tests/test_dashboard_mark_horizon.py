"""Dashboard display carries must obey the canonical portfolio.marks carry horizon."""
from __future__ import annotations

import json


def test_persisted_book_quote_uses_canonical_mark_horizon(tmp_path, monkeypatch) -> None:
    from app import web
    from portfolio import marks

    base = tmp_path / "autonomous"
    base.mkdir()
    (base / "latest.json").write_text(json.dumps({
        "as_of": "2026-09-13",
        "market_status": {"open": False, "trading_day": True},
        "positions": [{"ticker": "AAPL", "current_price": 200.0}],
    }))
    monkeypatch.setattr(web, "_portfolio_dir", lambda _pid=None: base)
    monkeypatch.setattr(marks, "_stale_max_days", lambda: 2)

    assert web._persisted_book_quotes(
        "autonomous", ["AAPL"], asof="2026-09-15"
    )["AAPL"]["price_local"] == 200.0
    assert web._persisted_book_quotes(
        "autonomous", ["AAPL"], asof="2026-09-16"
    ) == {}


def test_terminal_snapshot_selection_uses_canonical_mark_horizon(monkeypatch) -> None:
    from app import web
    from portfolio import marks

    monkeypatch.setattr(marks, "_stale_max_days", lambda: 2)
    terminal = {
        "source": "terminal_snapshot",
        "as_of": "2026-09-13",
        "time_kind": "snapshot_market_date",
        "price_local": 200.0,
    }

    assert web._select_dashboard_quote(terminal, None, asof="2026-09-15") == terminal
    assert web._select_dashboard_quote(terminal, None, asof="2026-09-16") is None
