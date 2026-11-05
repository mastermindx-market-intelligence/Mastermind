"""Decision-journal failures must stay unavailable and portfolio-scoped."""
from __future__ import annotations

import json
from pathlib import Path


def test_api_decisions_failure_is_unknown_and_secret_safe(monkeypatch):
    from app import web

    monkeypatch.setattr(
        web,
        "_brain_book_module",
        lambda _portfolio: (_ for _ in ()).throw(RuntimeError("secret /Users/private/decisions.json")),
    )

    payload = json.loads(web.api_decisions("autonomous").body)

    assert payload["portfolio"] == "autonomous"
    assert payload["decisions"] is None
    assert payload["decision_log_status"] == "unavailable"
    assert payload["error"] == "decisions_unavailable"
    encoded = json.dumps(payload)
    assert "secret" not in encoded
    assert "/Users/private" not in encoded


def test_decision_ui_preserves_unavailable_and_clears_cross_book_state():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "_decisionsStatus = 'loading'" in html

    render_start = html.index("function renderDecisions()")
    render_end = html.index("function _decisionPresentation", render_start)
    render = html[render_start:render_end]
    assert "_decisionsStatus === 'loading'" in render
    assert "_decisionsStatus === 'unavailable'" in render
    assert "Loading decision journal" in render
    assert "Decision journal unavailable" in render
    assert render.index("_decisionsStatus === 'loading'") < render.index("_decisionsStatus === 'unavailable'") < render.index("!_decisions || !_decisions.length")

    details_start = html.index("function _fetchPortfolioDetails")
    details_end = html.index("function _fetchPortfolioSnapshot", details_start)
    details = html[details_start:details_end]
    assert "decisionsStatus" in details
    assert "decisions_unavailable" in details
    assert "Array.isArray(dec.decisions) ? dec.decisions : null" in details

    apply_start = html.index("function _applyPortfolioSnapshot")
    apply_end = html.index("function _paintPortfolioSnapshot", apply_start)
    apply = html[apply_start:apply_end]
    assert "Array.isArray(snapshot.decisions)" in apply
    assert "_decisionsStatus = snapshot.decisionsStatus || null" in apply

    switch_start = html.index("window.setPortfolio = function(id)")
    switch_end = html.index("async function loadPortfolios", switch_start)
    switch = html[switch_start:switch_end]
    assert "_decisions = []" in switch
    assert "_decisionsStatus = 'loading'" in switch
