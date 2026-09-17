"""Secret-safe, non-fabricated degradation for Self-Directed auxiliary API surfaces."""
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
    raise RuntimeError("secret backend detail api_key=do-not-return")


def test_history_failure_is_unavailable_not_zero_trades(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(web, "_self_directed_mutation_lock", lambda _op: _Lock())
    monkeypatch.setattr(self_directed, "_load_account", lambda: {"positions": {}})
    monkeypatch.setattr(self_directed, "history", _secret_failure)

    response = web.api_self_directed_history()
    payload = _body(response)

    assert payload["error"] == "self_directed_history_unavailable"
    assert payload["history"] == [] and payload["pending"] == []
    assert payload["realized_total"] is None
    assert payload["n_closed"] is None
    assert payload["n_buys"] is None
    assert payload["win_rate"] is None
    assert "secret backend detail" not in response.body.decode()


def test_search_failure_is_closed_and_secret_safe(monkeypatch) -> None:
    from app import web
    from data_layer import polygon

    monkeypatch.setattr(polygon, "search_tickers", _secret_failure)
    response = web.api_self_directed_search("AAPL")
    payload = _body(response)

    assert payload == {"results": [], "error": "self_directed_search_unavailable"}
    assert "api_key" not in response.body.decode()


def test_quote_failure_is_closed_and_secret_safe(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(self_directed, "quote_info", _secret_failure)
    response = web.api_self_directed_quote("aapl")
    payload = _body(response)

    assert payload == {
        "ticker": "AAPL", "price": None, "name": "",
        "error": "self_directed_quote_unavailable",
    }
    assert "api_key" not in response.body.decode()


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


def test_ui_names_auxiliary_failures_instead_of_false_empty_states() -> None:
    html = (Path(__file__).parents[1] / "app" / "static" / "index.html").read_text()

    assert "Trade history unavailable" in html
    assert "renderSelfResults([], 'err')" in html
    assert "self_directed_quote_unavailable" in html
    assert "Quote unavailable" in html
    assert "!String(d.error).startsWith('self_directed_')" in html
    assert "d && d.ok" in html and "cancelSelfOrder" in html
