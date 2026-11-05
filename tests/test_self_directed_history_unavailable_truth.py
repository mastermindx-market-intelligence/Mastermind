"""Self-Directed history failures must not become a zero-trade blotter."""
from __future__ import annotations

import json
from pathlib import Path


def test_self_directed_history_failure_is_unknown_and_secret_safe(monkeypatch):
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(
        self_directed,
        "_load_account",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/self-history")),
    )

    payload = json.loads(web.api_self_directed_history().body)

    assert payload["history_status"] == "unavailable"
    assert payload["error"] == "self_directed_history_unavailable"
    assert payload["history"] is None
    assert payload["pending"] is None
    assert payload["realized_total"] is None
    assert payload["n_closed"] is None
    assert payload["n_buys"] is None
    assert payload["win_rate"] is None
    encoded = json.dumps(payload)
    assert "secret" not in encoded
    assert "/Users/private" not in encoded


def test_self_history_ui_distinguishes_loading_unavailable_and_empty():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "_selfHist = {history_status:'loading'}" in html
    assert "function _selfHistoryUnavailable()" in html

    render_start = html.index("function renderSelfHistory()")
    render_end = html.index("// ── order ticket", render_start)
    render = html[render_start:render_end]
    assert "d.history_status === 'loading'" in render
    assert "self_directed_history_unavailable" in render
    assert "Self-Directed trade history unavailable" in render
    assert render.index("history_status === 'loading'") < render.index("self_directed_history_unavailable") < render.index("!hist.length")

    refresh_start = html.index("function refreshSelf()")
    refresh_end = html.index("function _heldShares", refresh_start)
    refresh = html[refresh_start:refresh_end]
    assert "_selfHistoryUnavailable()" in refresh

    details_start = html.index("function _fetchPortfolioDetails")
    details_end = html.index("function _fetchPortfolioSnapshot", details_start)
    details = html[details_start:details_end]
    assert "selfHistory: history || _selfHistoryUnavailable()" in details

    switch_start = html.index("window.setPortfolio = function(id)")
    switch_end = html.index("async function loadPortfolios", switch_start)
    switch = html[switch_start:switch_end]
    assert "if (id === 'self_directed') _selfHist = {history_status:'loading'}" in switch
