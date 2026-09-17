"""Readiness and experiment-registry outages stay distinct from legitimate empty state."""
from __future__ import annotations

import json


def _body(resp):
    return json.loads(resp.body)


def _boom(*_args, **_kwargs):
    raise RuntimeError("secret /Users/private/governance token=bad")


def test_readiness_successful_empty_state_remains_successful(monkeypatch):
    from app import web
    from portfolio import readiness

    monkeypatch.setattr(readiness, "status", lambda: {})
    monkeypatch.setattr(readiness, "alerts", lambda: [])
    payload = _body(web.api_readiness())
    assert payload == {"status": {}, "alerts": []}


def test_readiness_failure_is_unavailable_not_empty(monkeypatch):
    from app import web
    from portfolio import readiness

    monkeypatch.setattr(readiness, "status", _boom)
    response = web.api_readiness()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "status": None,
        "alerts": None,
        "error": "readiness_unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw


def test_experiment_registry_successful_zero_state_remains_zero(monkeypatch):
    from app import web
    from brain import experiment_registry

    monkeypatch.setattr(experiment_registry, "summary", lambda: {
        "as_of": "2026-09-17", "total": 0, "open": 0, "matured": 0,
        "judged": 0, "cancelled": 0, "matured_items": [], "open_tristate": [],
    })
    monkeypatch.setattr(experiment_registry, "load", lambda: [])
    payload = _body(web.api_desk_experiments())
    assert payload["total"] == 0
    assert payload["all_items"] == []
    assert "read_status" not in payload
    assert "error" not in payload


def test_experiment_registry_failure_is_unavailable_not_zero(monkeypatch):
    from app import web
    from brain import experiment_registry

    monkeypatch.setattr(experiment_registry, "summary", _boom)
    response = web.api_desk_experiments()
    payload = _body(response)
    assert payload == {
        "read_status": "unavailable",
        "as_of": None,
        "total": None,
        "open": None,
        "matured": None,
        "judged": None,
        "cancelled": None,
        "matured_items": None,
        "all_items": None,
        "open_tristate": None,
        "error": "experiment_registry_unavailable",
    }
    raw = response.body.decode()
    assert "secret" not in raw and "/Users/private" not in raw and "token=bad" not in raw
