"""Registered accountability API routes distinguish valid empty evidence from failed reads."""
from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app import web

    application = FastAPI()
    application.include_router(web.router)
    with TestClient(application) as connection:
        yield connection


def _body(resp):
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    return resp.json()


def _boom(*_args, **_kwargs):
    raise RuntimeError("secret /Users/private/accountability api_key=bad")


def test_outcomes_full_failure_is_unavailable_and_secret_safe(monkeypatch, client, caplog):
    from brain import outcomes

    monkeypatch.setattr(outcomes, "realized_returns", _boom)
    response = client.get("/api/outcomes")
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "error": "outcomes_unavailable",
        "labels": None,
        "summary": None,
        "track_record": None,
        "calibration": None,
    }
    raw = response.text
    assert "secret" not in raw and "/Users/private" not in raw and "api_key" not in raw
    assert "secret" not in caplog.text and "/Users/private" not in caplog.text and "api_key" not in caplog.text


def test_outcomes_calibration_failure_is_partial_not_empty(monkeypatch, client, caplog):
    from brain import calibration, outcomes, scorer

    monkeypatch.setattr(outcomes, "realized_returns", lambda _asof: {"AAPL": 0.1})
    monkeypatch.setattr(outcomes, "all_labels", lambda _asof: [{"ticker": "AAPL"}])
    monkeypatch.setattr(outcomes, "summary", lambda _asof: {"n": 1})
    monkeypatch.setattr(scorer, "track_record", lambda _asof, realized=None: {"n": 1})
    monkeypatch.setattr(calibration, "load", _boom)
    monkeypatch.setattr(calibration, "compute", _boom)

    payload = _body(client.get("/api/outcomes"))
    assert payload["read_status"] == "partial"
    assert payload["failed_sources"] == ["calibration"]
    assert payload["labels"] == [{"ticker": "AAPL"}]
    assert payload["summary"] == {"n": 1}
    assert payload["track_record"] == {"n": 1}
    assert payload["calibration"] is None
    assert "error" not in payload
    assert "secret" not in caplog.text and "/Users/private" not in caplog.text and "api_key" not in caplog.text


def test_outcomes_success_contract_stays_legacy_shape(monkeypatch, client, caplog):
    from brain import calibration, outcomes, scorer

    monkeypatch.setattr(outcomes, "realized_returns", lambda _asof: {})
    monkeypatch.setattr(outcomes, "all_labels", lambda _asof: [])
    monkeypatch.setattr(outcomes, "summary", lambda _asof: {"n": 0, "status": "building"})
    monkeypatch.setattr(scorer, "track_record", lambda _asof, realized=None: {})
    monkeypatch.setattr(calibration, "load", lambda: {"status": "building"})

    payload = _body(client.get("/api/outcomes"))
    assert payload == {
        "labels": [],
        "summary": {"n": 0, "status": "building"},
        "track_record": {},
        "calibration": {"status": "building"},
    }


def test_rejections_failure_is_unavailable_not_empty(monkeypatch, client, caplog):
    from portfolio import rejections

    monkeypatch.setattr(rejections, "summary", _boom)
    response = client.get("/api/rejections")
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "error": "rejections_unavailable",
        "coverage": None,
        "scorecard": None,
    }
    assert "secret" not in response.text
    assert "secret" not in caplog.text and "/Users/private" not in caplog.text and "api_key" not in caplog.text


def test_bandit_failure_is_unavailable_not_building(monkeypatch, client, caplog):
    from portfolio import bandit

    monkeypatch.setattr(bandit, "rank_shadow_books", _boom)
    response = client.get("/api/shadow_bandit")
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "status": "unavailable",
        "arms": None,
        "error": "shadow_bandit_unavailable",
    }
    assert "secret" not in response.text
    assert "secret" not in caplog.text and "/Users/private" not in caplog.text and "api_key" not in caplog.text


def test_interim_marks_failure_is_unavailable_not_empty(monkeypatch, client, caplog):
    from brain import interim_marks

    monkeypatch.setattr(interim_marks, "summary", _boom)
    response = client.get("/api/interim_marks")
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "scorecard": None,
        "error": "interim_marks_unavailable",
    }
    assert "secret" not in response.text
    assert "secret" not in caplog.text and "/Users/private" not in caplog.text and "api_key" not in caplog.text


def test_etf_outcomes_failure_is_unavailable_not_building(monkeypatch, client, caplog):
    from portfolio import etf_outcomes

    monkeypatch.setattr(etf_outcomes, "summary", _boom)
    response = client.get("/api/etf/outcomes")
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "scorecard": None,
        "error": "etf_outcomes_unavailable",
    }
    assert "secret" not in response.text
    assert "secret" not in caplog.text and "/Users/private" not in caplog.text and "api_key" not in caplog.text


@pytest.mark.parametrize("module_name, reader_name, path, expected", [
    ("portfolio.bandit", "rank_shadow_books", "/api/shadow_bandit",
     {"status": "building", "arms": []}),
    ("brain.interim_marks", "summary", "/api/interim_marks", {"scorecard": {}}),
    ("portfolio.etf_outcomes", "summary", "/api/etf/outcomes",
     {"scorecard": {"status": "building"}}),
    ("portfolio.rejections", "summary", "/api/rejections",
     {"coverage": {"n_total": 0}, "scorecard": {"status": "building"}}),
])
def test_registered_routes_preserve_successful_empty_or_building(
        monkeypatch, client, module_name, reader_name, path, expected):
    reader = importlib.import_module(module_name)
    calls = []

    def read(*args, **kwargs):
        calls.append((args, kwargs))
        return expected

    monkeypatch.setattr(reader, reader_name, read)
    response = client.get(path)
    assert _body(response) == expected
    assert len(calls) == 1
    assert "read_status" not in response.json() and "error" not in response.json()


def test_registered_outcomes_compute_failure_preserves_other_evidence(
        monkeypatch, client, caplog):
    from brain import calibration, outcomes, scorer

    monkeypatch.setattr(outcomes, "realized_returns", lambda _asof: {})
    monkeypatch.setattr(outcomes, "all_labels", lambda _asof: [])
    monkeypatch.setattr(outcomes, "summary", lambda _asof: {"n": 0})
    monkeypatch.setattr(scorer, "track_record", lambda _asof, realized=None: None)
    monkeypatch.setattr(calibration, "load", lambda: None)
    monkeypatch.setattr(calibration, "compute", _boom)

    payload = _body(client.get("/api/outcomes"))
    assert payload == {
        "labels": [], "summary": {"n": 0}, "track_record": None, "calibration": None,
        "read_status": "partial", "failed_sources": ["calibration"],
    }
    assert "secret" not in caplog.text and "/Users/private" not in caplog.text and "api_key" not in caplog.text


def test_registered_outcomes_preserves_successful_null_evidence(monkeypatch, client):
    from brain import calibration, outcomes, scorer

    monkeypatch.setattr(outcomes, "realized_returns", lambda _asof: {})
    monkeypatch.setattr(outcomes, "all_labels", lambda _asof: None)
    monkeypatch.setattr(outcomes, "summary", lambda _asof: None)
    monkeypatch.setattr(scorer, "track_record", lambda _asof, realized=None: None)
    monkeypatch.setattr(calibration, "load", lambda: None)
    monkeypatch.setattr(calibration, "compute", lambda _asof: None)

    assert _body(client.get("/api/outcomes")) == {
        "labels": None, "summary": None, "track_record": None, "calibration": None,
    }
