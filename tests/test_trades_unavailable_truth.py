"""Trade-history read failures must remain unavailable, never false-empty."""
from __future__ import annotations

import json
from pathlib import Path


def test_api_trades_failure_is_unknown_not_empty_and_secret_safe(monkeypatch):
    from app import web
    from portfolio import registry

    def boom(_portfolio):
        raise RuntimeError("secret backend detail /Users/private/path")

    monkeypatch.setattr(registry, "is_archived", boom)
    payload = json.loads(web.api_trades("autonomous").body)

    assert payload["error"] == "trades_unavailable"
    assert payload["snapshot_status"] == "unavailable"
    assert payload["open"] is None
    assert payload["closed"] is None
    assert payload["history"] is None
    assert payload["pending"] is None
    assert payload["market"] is None
    assert "secret backend detail" not in json.dumps(payload)
    assert "/Users/private/path" not in json.dumps(payload)


def test_trade_renderer_distinguishes_unavailable_from_empty_history():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()
    start = html.index("function renderTrades()")
    end = html.index("window.tradesPage", start)
    render = html[start:end]

    assert "trades_unavailable" in render
    assert "trades.unavailable" in render
    assert render.index("trades_unavailable") < render.index("var hist")
