"""Mastermind Portfolio Loop admin reads preserve empty-vs-unavailable truth."""
from __future__ import annotations

import json


def _body(resp):
    return json.loads(resp.body)


def _boom(*_args, **_kwargs):
    raise RuntimeError("secret /Users/private/mastermind-ai token=bad")


def test_status_success_keeps_product_identity(monkeypatch):
    from app import web
    from brain import mastermind_ai

    monkeypatch.setattr(mastermind_ai, "status", lambda: {"schema": "mastermind_ai_status.v1", "loop_n": 0})
    payload = _body(web.api_mastermind_ai())
    assert payload["schema"] == "mastermind_ai_status.v1"
    assert payload["loop_n"] == 0
    assert payload["product_scope"] == "mastermind_portfolio_loop"
    assert payload["public_chatbot_separate"] is True
    assert "read_status" not in payload and "error" not in payload


def test_status_failure_is_unavailable_and_secret_safe(monkeypatch):
    from app import web
    from brain import mastermind_ai

    monkeypatch.setattr(mastermind_ai, "status", _boom)
    response = web.api_mastermind_ai()
    payload = _body(response)
    assert payload == {
        "schema": "mastermind_ai_status.v1",
        "read_status": "unavailable",
        "product_scope": "mastermind_portfolio_loop",
        "public_chatbot_separate": True,
        "legacy_route_prefix": "/api/mastermind_ai",
        "error": "mastermind_ai_status_unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


def test_loop_log_successful_empty_remains_empty(monkeypatch):
    from app import web
    from brain import mastermind_ai

    monkeypatch.setattr(mastermind_ai, "loop_log", lambda limit=50: [])
    monkeypatch.setattr(mastermind_ai, "reviews", lambda limit=12: [])
    payload = _body(web.api_mastermind_ai_loop_log())
    assert payload == {"loop_log": [], "reviews": []}


def test_loop_log_failure_is_unavailable_not_empty(monkeypatch):
    from app import web
    from brain import mastermind_ai

    monkeypatch.setattr(mastermind_ai, "loop_log", _boom)
    response = web.api_mastermind_ai_loop_log()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "loop_log": None,
        "reviews": None,
        "error": "mastermind_ai_loop_log_unavailable",
    }
    assert "secret" not in response.body.decode()


def test_improvements_successful_empty_remains_empty(monkeypatch):
    from app import web
    from brain import mastermind_ai

    expected = {"pins": [], "self_tune": {}, "agenda_top": [], "lessons_by_taxonomy": {}}
    monkeypatch.setattr(mastermind_ai, "improvements", lambda: expected)
    assert _body(web.api_mastermind_ai_improvements()) == expected


def test_improvements_failure_is_unavailable_not_empty(monkeypatch):
    from app import web
    from brain import mastermind_ai

    monkeypatch.setattr(mastermind_ai, "improvements", _boom)
    response = web.api_mastermind_ai_improvements()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "pins": None,
        "self_tune": None,
        "agenda_top": None,
        "lessons_by_taxonomy": None,
        "error": "mastermind_ai_improvements_unavailable",
    }
    assert "secret" not in response.body.decode()


def test_reflection_successful_absence_remains_absent(monkeypatch):
    from app import web
    from brain import nw_reflection

    monkeypatch.setattr(nw_reflection, "latest", lambda: None)
    payload = _body(web.api_mastermind_ai_reflection())
    assert payload["state"] == "absent"
    assert payload["schema"] == nw_reflection.SCHEMA
    assert "read_status" not in payload and "error" not in payload


def test_reflection_failure_is_unavailable_not_absent(monkeypatch):
    from app import web
    from brain import nw_reflection

    monkeypatch.setattr(nw_reflection, "latest", _boom)
    response = web.api_mastermind_ai_reflection()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "state": "unavailable",
        "error": "mastermind_ai_reflection_unavailable",
    }
    assert "secret" not in response.body.decode()
