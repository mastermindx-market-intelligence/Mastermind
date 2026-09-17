"""Desk read failures are unavailable, never ordinary building/empty states."""
from __future__ import annotations

import json
from pathlib import Path


def _body(resp):
    return json.loads(resp.body)


def _assert_closed(payload: dict, code: str) -> None:
    assert payload["status"] == "unavailable"
    assert payload["error"] == code
    raw = json.dumps(payload)
    assert "secret" not in raw.lower()
    assert "/Users/private" not in raw


def test_strategist_failure_is_unavailable(monkeypatch):
    from app import web

    monkeypatch.setattr(
        web, "_committee_dir",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/strategist.json")),
    )
    _assert_closed(_body(web.api_desk_strategist()), "desk_strategist_unavailable")


def test_decision_failure_is_unavailable_not_empty(monkeypatch):
    from app import web

    monkeypatch.setattr(
        web, "_committee_dir",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/decisions")),
    )
    payload = _body(web.api_desk_decisions())
    _assert_closed(payload, "desk_decisions_unavailable")
    assert payload["decisions"] is None


def test_watchlist_failure_is_unavailable_not_empty(monkeypatch):
    from app import web
    from portfolio import watchlist

    monkeypatch.setattr(
        watchlist, "latest",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/watchlist.jsonl")),
    )
    payload = _body(web.api_desk_watchlist())
    _assert_closed(payload, "desk_watchlist_unavailable")
    assert payload["watchlist"] is None


def test_macro_risk_failure_is_unavailable_not_building(monkeypatch):
    from app import web

    monkeypatch.setattr(
        web, "_macro_risk_dir",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/macro-risk")),
    )
    payload = _body(web.api_desk_macro_risk())
    _assert_closed(payload, "desk_macro_risk_unavailable")
    assert payload["state"] is None


def test_firm_exposure_failure_is_unavailable_not_zero_books(monkeypatch):
    from app import web
    from portfolio import firm_exposure

    monkeypatch.setattr(
        firm_exposure, "summary",
        lambda: (_ for _ in ()).throw(RuntimeError("secret /Users/private/firm-exposure")),
    )
    payload = _body(web.api_desk_firm_exposure())
    _assert_closed(payload, "desk_firm_exposure_unavailable")
    assert payload["books"] is None
    assert payload["n_books"] is None


def test_desk_ui_consumes_unavailable_before_building_or_empty():
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "function _deskUnavailable()" in html
    load_start = html.index("window.loadDesk = function()")
    load_end = html.index("function renderDeskPage()", load_start)
    load = html[load_start:load_end]
    assert "_deskUnavailable()" in load

    spans = (
        ("function renderDeskStrategist()", "function renderDeskMacroRisk()", "d.status === 'unavailable'", "d.status === 'building'"),
        ("function renderDeskMacroRisk()", "function _deskActChip", "d.status === 'unavailable'", "d.status === 'building'"),
        ("function renderDeskDecisions()", "function renderDeskWatchlist()", "d.status === 'unavailable'", "d.status === 'building'"),
        ("function renderDeskWatchlist()", "function renderDeskScorecard()", "d.status === 'unavailable'", "!rows.length"),
        ("function renderDeskScorecard()", "function _firmBooksStr", "d.status === 'unavailable'", "!rendered.length"),
        ("function renderDeskFirm()", "window.openThesis", "d.status === 'unavailable'", "!(d.books || []).length"),
    )
    for start, end, unavailable, ordinary in spans:
        a = html.index(start)
        b = html.index(end, a)
        block = html[a:b]
        assert unavailable in block
        assert block.index(unavailable) < block.index(ordinary)


def test_scorecard_transport_unavailable_clears_cio_stale_state():
    html = (Path(__file__).parents[1] / 'app' / 'static' / 'index.html').read_text()
    a = html.index('function renderDeskScorecard()')
    b = html.index('function _firmBooksStr', a)
    block = html[a:b]
    guard = "d.status === 'unavailable'"
    assert guard in block
    assert "cioHost.innerHTML = _deskUnavailableHtml()" in block
    assert block.index(guard) < block.index("!rendered.length")
