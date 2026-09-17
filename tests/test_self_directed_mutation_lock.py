"""One canonical book lock serializes every production Self-Directed mutation carrier."""
from __future__ import annotations

import json

import pytest


@pytest.mark.parametrize("operation", ["history", "order", "thesis", "cancel"])
def test_self_directed_mutation_routes_refuse_when_book_lock_is_held(monkeypatch, operation) -> None:
    from app import web
    from portfolio import self_directed

    monkeypatch.setattr(web, "_self_directed_mutation_lock", lambda _operation: None, raising=False)
    monkeypatch.setattr(
        self_directed,
        "history",
        lambda **kwargs: pytest.fail("history must not mutate while lock is held"),
    )
    monkeypatch.setattr(
        self_directed,
        "place_order",
        lambda *args, **kwargs: pytest.fail("order must not mutate while lock is held"),
    )
    monkeypatch.setattr(
        self_directed,
        "set_thesis",
        lambda *args, **kwargs: pytest.fail("thesis must not mutate while lock is held"),
    )
    monkeypatch.setattr(
        self_directed,
        "cancel_order",
        lambda *args, **kwargs: pytest.fail("cancel must not mutate while lock is held"),
    )

    if operation == "history":
        response = web.api_self_directed_history()
    elif operation == "order":
        response = web.api_self_directed_order(
            web._OrderReq(ticker="AAPL", side="buy", shares=1.0)
        )
    elif operation == "thesis":
        response = web.api_self_directed_thesis(
            web._ThesisReq(ticker="AAPL", note="test")
        )
    else:
        response = web.api_self_directed_cancel("order-1")

    payload = json.loads(response.body)
    assert response.status_code == 409
    assert payload["ok"] is False
    assert payload["error"] == "self_directed_busy_retry"


def test_self_directed_order_holds_book_lock_across_mutation(monkeypatch) -> None:
    from app import web
    from portfolio import self_directed

    state = {"entered": False, "exited": False}

    class _Lock:
        def __enter__(self):
            state["entered"] = True
            return self

        def __exit__(self, *args):
            state["exited"] = True

    monkeypatch.setattr(web, "_self_directed_mutation_lock", lambda _operation: _Lock(), raising=False)

    def _place(*args, **kwargs):
        assert state["entered"] is True and state["exited"] is False
        return {"ok": True, "status": "pending"}

    monkeypatch.setattr(self_directed, "place_order", _place)
    response = web.api_self_directed_order(
        web._OrderReq(ticker="AAPL", side="buy", shares=1.0)
    )

    assert response.status_code == 200
    assert state == {"entered": True, "exited": True}


def test_mutation_lock_uses_canonical_self_directed_book_name(monkeypatch) -> None:
    from app import web
    from control_plane import locks

    calls = []
    sentinel = object()
    monkeypatch.setattr(
        locks,
        "acquire_or_log",
        lambda name, **kwargs: calls.append((name, kwargs)) or sentinel,
    )

    assert web._self_directed_mutation_lock("order") is sentinel
    assert calls == [(
        "book:self_directed",
        {"job": "self_directed_order", "book": "self_directed"},
    )]
