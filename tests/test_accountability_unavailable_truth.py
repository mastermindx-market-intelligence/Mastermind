"""Accountability reads distinguish legitimate building/empty evidence from read failure."""
from __future__ import annotations

import json


def _body(resp):
    return json.loads(resp.body)


def _boom(*_args, **_kwargs):
    raise RuntimeError("secret /Users/private/accountability api_key=bad")


def test_outcomes_full_failure_is_unavailable_and_secret_safe(monkeypatch):
    from app import web
    from brain import outcomes

    monkeypatch.setattr(outcomes, "realized_returns", _boom)
    response = web.api_outcomes()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "error": "outcomes_unavailable",
        "labels": None,
        "summary": None,
        "track_record": None,
        "calibration": None,
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw


def test_outcomes_calibration_failure_is_partial_not_empty(monkeypatch):
    from app import web
    from brain import calibration, outcomes, scorer

    monkeypatch.setattr(outcomes, "realized_returns", lambda _asof: {"AAPL": 0.1})
    monkeypatch.setattr(outcomes, "all_labels", lambda _asof: [{"ticker": "AAPL"}])
    monkeypatch.setattr(outcomes, "summary", lambda _asof: {"n": 1})
    monkeypatch.setattr(scorer, "track_record", lambda _asof, realized=None: {"n": 1})
    monkeypatch.setattr(calibration, "load", _boom)
    monkeypatch.setattr(calibration, "compute", _boom)

    payload = _body(web.api_outcomes())
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["calibration"]
    assert payload["labels"] == [{"ticker": "AAPL"}]
    assert payload["summary"] == {"n": 1}
    assert payload["track_record"] == {"n": 1}
    assert payload["calibration"] is None
    assert "error" not in payload


def test_outcomes_success_contract_stays_legacy_shape(monkeypatch):
    from app import web
    from brain import calibration, outcomes, scorer

    monkeypatch.setattr(outcomes, "realized_returns", lambda _asof: {})
    monkeypatch.setattr(outcomes, "all_labels", lambda _asof: [])
    monkeypatch.setattr(outcomes, "summary", lambda _asof: {"n": 0, "status": "building"})
    monkeypatch.setattr(scorer, "track_record", lambda _asof, realized=None: {})
    monkeypatch.setattr(calibration, "load", lambda: {"status": "building"})

    payload = _body(web.api_outcomes())
    assert payload == {
        "labels": [],
        "summary": {"n": 0, "status": "building"},
        "track_record": {},
        "calibration": {"status": "building"},
    }


def test_rejections_failure_is_unavailable_not_empty(monkeypatch):
    from app import web
    from portfolio import rejections

    monkeypatch.setattr(rejections, "summary", _boom)
    response = web.api_rejections()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "error": "rejections_unavailable",
        "coverage": None,
        "scorecard": None,
    }
    assert "secret" not in response.body.decode()


def test_bandit_failure_is_unavailable_not_building(monkeypatch):
    from app import web
    from portfolio import bandit

    monkeypatch.setattr(bandit, "rank_shadow_books", _boom)
    response = web.api_shadow_bandit()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "status": "unavailable",
        "arms": None,
        "error": "shadow_bandit_unavailable",
    }
    assert "secret" not in response.body.decode()


def test_interim_marks_failure_is_unavailable_not_empty(monkeypatch):
    from app import web
    from brain import interim_marks

    monkeypatch.setattr(interim_marks, "summary", _boom)
    response = web.api_interim_marks()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "scorecard": None,
        "error": "interim_marks_unavailable",
    }
    assert "secret" not in response.body.decode()


def test_etf_outcomes_failure_is_unavailable_not_building(monkeypatch):
    from app import web
    from portfolio import etf_outcomes

    monkeypatch.setattr(etf_outcomes, "summary", _boom)
    response = web.api_etf_outcomes()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "scorecard": None,
        "error": "etf_outcomes_unavailable",
    }
    assert "secret" not in response.body.decode()
