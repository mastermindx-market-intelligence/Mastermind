"""Secret-safe, truth-preserving degradation for Self-Directed interaction surfaces."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


class _Lock:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _body(response) -> dict:
    return json.loads(response.body)


def _secret_failure(*_args, **_kwargs):
    raise RuntimeError("secret backend detail api_key=do-not-return /Users/private/state.json")


def test_search_failure_is_unavailable_not_empty(monkeypatch) -> None:
    from app import web
    from data_layer import polygon

    monkeypatch.setattr(polygon, "search_tickers", _secret_failure)
    response = web.api_self_directed_search("AAPL")
    payload = _body(response)

    assert payload == {
        "search_status": "unavailable",
        "results": None,
        "error": "self_directed_search_unavailable",
    }
    assert "api_key" not in response.body.decode()
    assert "/Users/private" not in response.body.decode()


def test_successful_empty_search_remains_available_empty(monkeypatch) -> None:
    from app import web
    from data_layer import polygon

    monkeypatch.setattr(polygon, "search_tickers", lambda _q: [])
    payload = _body(web.api_self_directed_search("NOPE"))
    assert payload == {"search_status": "available", "results": []}


def test_quote_failure_is_unavailable_not_no_price(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(self_directed, "quote_info", _secret_failure)
    response = web.api_self_directed_quote("aapl")
    payload = _body(response)

    assert payload == {
        "quote_status": "unavailable",
        "ticker": "AAPL",
        "price": None,
        "name": None,
        "market": None,
        "error": "self_directed_quote_unavailable",
    }
    assert "api_key" not in response.body.decode()
    assert "/Users/private" not in response.body.decode()


def test_successful_quote_without_price_remains_available(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(
        self_directed,
        "quote_info",
        lambda _ticker: {"ticker": "AAPL", "price": None, "name": "Apple", "market": {"session": "closed"}},
    )
    payload = _body(web.api_self_directed_quote("AAPL"))
    assert payload["quote_status"] == "available"
    assert payload["price"] is None
    assert payload["name"] == "Apple"
    assert "error" not in payload


@pytest.mark.parametrize(
    ("operation", "code"),
    [
        ("order", "self_directed_order_unavailable"),
        ("thesis", "self_directed_thesis_unavailable"),
        ("cancel", "self_directed_cancel_unavailable"),
    ],
)
def test_mutation_exception_codes_are_closed(monkeypatch, operation, code) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(web, "_self_directed_mutation_lock", lambda _op: _Lock())
    monkeypatch.setattr(self_directed, "place_order", _secret_failure)
    monkeypatch.setattr(self_directed, "set_thesis", _secret_failure)
    monkeypatch.setattr(self_directed, "cancel_order", _secret_failure)

    if operation == "order":
        response = web.api_self_directed_order(
            web._OrderReq(ticker="AAPL", side="buy", shares=1.0)
        )
    elif operation == "thesis":
        response = web.api_self_directed_thesis(
            web._ThesisReq(ticker="AAPL", note="note")
        )
    else:
        response = web.api_self_directed_cancel("order-1")

    payload = _body(response)
    assert response.status_code == 500
    assert payload == {"ok": False, "error": code}
    assert "secret backend detail" not in response.body.decode()


def test_expected_order_rejection_remains_user_visible(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(web, "_self_directed_mutation_lock", lambda _op: _Lock())
    monkeypatch.setattr(
        self_directed,
        "place_order",
        lambda *args, **kwargs: {"ok": False, "error": "insufficient cash"},
    )

    payload = _body(web.api_self_directed_order(
        web._OrderReq(ticker="AAPL", side="buy", shares=1.0)
    ))
    assert payload == {"ok": False, "error": "insufficient cash"}


def test_cancel_miss_is_explicit_not_ambiguous_false(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(web, "_self_directed_mutation_lock", lambda _op: _Lock())
    monkeypatch.setattr(self_directed, "cancel_order", lambda _oid: False)
    payload = _body(web.api_self_directed_cancel("already-gone"))
    assert payload == {"ok": False, "error": "self_directed_cancel_not_found"}


def test_ui_distinguishes_unavailable_no_data_and_effect_unknown() -> None:
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    search_start = html.index("window.selfSearch = function()")
    search_end = html.index("function renderSelfResults", search_start)
    search = html[search_start:search_end]
    assert "d.search_status === 'unavailable'" in search
    assert "self_directed_search_unavailable" in search
    assert "renderSelfResults([], 'err')" in search

    select_start = html.index("window.selectSelfTicker = function")
    select_end = html.index("function renderSelfSelected", select_start)
    select = html[select_start:select_end]
    assert "d.quote_status === 'unavailable'" in select
    assert "quote_status: 'unavailable'" in select

    render_start = html.index("function renderSelfSelected")
    render_end = html.index("var _selfUnit", render_start)
    render = html[render_start:render_end]
    assert "s.quote_status === 'unavailable'" in render
    assert "sd.quote_unavail" in render
    assert "sd.no_price" in render

    order_start = html.index("window.placeSelfOrder = function")
    order_end = html.index("window.saveSelfThesis", order_start)
    order = html[order_start:order_end]
    assert "if (_selfBusy || _selfOrderEffectUnknown)" in order
    assert "self_directed_order_unavailable" in order
    assert "_selfOrderEffectUnknown = true" in order
    assert "sd.order_unknown" in order
    assert "!String(d.error).startsWith('self_directed_')" in order

    thesis_start = html.index("window.saveSelfThesis = function")
    thesis_end = html.index("window.cancelSelfOrder", thesis_start)
    thesis = html[thesis_start:thesis_end]
    assert "sd.thesis_failed" in thesis
    assert ".catch(function(){});" not in thesis

    cancel_start = html.index("window.cancelSelfOrder = function")
    cancel_end = html.index("// close the search dropdown", cancel_start)
    cancel = html[cancel_start:cancel_end]
    assert "if (!d || !d.ok)" in cancel
    assert "sd.cancel_failed" in cancel
    assert cancel.index("if (!d || !d.ok)") < cancel.index("return refreshSelf()")
