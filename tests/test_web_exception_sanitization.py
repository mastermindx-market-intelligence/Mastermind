"""Public web errors stay stable while exception detail remains in server logs."""
from __future__ import annotations

import json
import logging


def _body(response) -> dict:
    return json.loads(response.body)


def test_forward_evaluation_rejection_does_not_expose_exception(monkeypatch, caplog):
    from app import web
    from portfolio import forward_evaluation

    internal_detail = "internal path /srv/private/evidence.json"

    def reject(*_args, **_kwargs):
        raise ValueError(internal_detail)

    monkeypatch.setattr(forward_evaluation, "status", reject)
    with caplog.at_level(logging.WARNING, logger="app.web"):
        response = web.api_forward_evaluation("autonomous", "not-a-date")

    payload = _body(response)
    assert response.status_code == 400
    assert payload["status"] == "invalid_request"
    assert payload["error"] == "asof must be a valid ISO date (YYYY-MM-DD)"
    assert internal_detail not in response.body.decode()
    assert any(
        record.exc_info and str(record.exc_info[1]) == internal_detail
        for record in caplog.records
    )


def test_portfolio_learning_failure_does_not_expose_exception(monkeypatch, caplog):
    from app import web
    from brain import portfolio_learning

    internal_detail = "credential-like detail must stay server-side"

    def fail():
        raise RuntimeError(internal_detail)

    monkeypatch.setattr(portfolio_learning, "status", fail)
    with caplog.at_level(logging.ERROR, logger="app.web"):
        response = web.api_portfolio_learning()

    payload = _body(response)
    assert response.status_code == 200
    assert payload == {
        "schema": "mastermind_portfolio_learning.v1",
        "error": "portfolio learning unavailable",
    }
    assert internal_detail not in response.body.decode()
    assert any(
        record.exc_info and str(record.exc_info[1]) == internal_detail
        for record in caplog.records
    )
