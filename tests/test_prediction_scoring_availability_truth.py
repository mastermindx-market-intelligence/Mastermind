"""Prediction scoring must remain live without the optional vendored validation package."""
from __future__ import annotations

import builtins

import pytest


def test_dependency_independent_validation_primitives_match_canonical_examples():
    from portfolio import predictions as p

    rank_ic = p._rank_ic_fallback
    nw = p._newey_west_tstat_fallback
    brier = p._brier_reliability_fallback

    assert rank_ic(range(10), range(10)) == pytest.approx(1.0)
    assert nw([0.01, 0.02, -0.01, 0.03, 0.0, 0.04, -0.02, 0.01, 0.02, 0.03], lags=2) == {
        "mean": 0.013,
        "se": 0.00379,
        "t": 3.435,
        "p": 0.0006,
        "n": 10,
        "lags": 2,
        "lags_requested": 2,
    }
    probs = [0.7] * 30
    outs = [0, 1] * 15
    br = brier(probs, outs)
    assert br["brier"] == 0.29
    assert br["base_brier"] == 0.25
    assert br["skill_score"] == -0.16
    assert br["n"] == 30 and br["base_rate"] == 0.5


def test_validation_helper_selection_falls_back_only_when_engine_import_is_unavailable(monkeypatch):
    from portfolio import predictions as p

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "engine.validation":
            raise ModuleNotFoundError("engine.validation unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    rank_ic, nw, brier = p._validation_helpers()
    assert rank_ic is p._rank_ic_fallback
    assert nw is p._newey_west_tstat_fallback
    assert brier is p._brier_reliability_fallback


def test_score_does_not_rewrite_canonical_ledger_failure_as_building(monkeypatch):
    from portfolio import predictions as p

    def explode():
        raise RuntimeError("secret /Users/private/prediction-ledger token=do-not-return")

    monkeypatch.setattr(p, "_load_ledger", explode)
    with pytest.raises(RuntimeError, match="prediction-ledger"):
        p.score("2026-09-17")



def _force_engine_validation_unavailable(monkeypatch):
    real_import = builtins.__import__
    calls = []

    def unavailable(name, *args, **kwargs):
        if name == "engine.validation":
            calls.append(name)
            raise ModuleNotFoundError("engine.validation unavailable for source qualification")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    return calls


def test_actual_prediction_summary_statistical_failure_is_unavailable(monkeypatch, caplog):
    import json
    from app import web
    from portfolio import predictions as p

    rows = [{"id": f"rank-{i}", "ticker": f"T{i}", "asof": "2026-09-17",
             "dir": "up", "score": i * 10, "prob": 0.7, "horizon_d": 21,
             "status": "resolved", "realized": i / 1000.0, "resolved_on": "2026-10-16"}
            for i in range(10)]
    monkeypatch.setattr(p, "_load_ledger", lambda: rows)
    coverage = p.coverage()
    assert coverage["n_total"] == 10 and coverage["n_resolved"] == 10
    assert coverage["by_horizon"] == {"21": {"open": 0, "resolved": 10}}
    imports = _force_engine_validation_unavailable(monkeypatch)
    entered = []
    sentinel = "secret /Users/private/rank-statistics token=do-not-return"

    def fail_rank(signal, forward):
        assert len(signal) == 10 and len(forward) == 10
        entered.append((len(signal), len(forward)))
        raise RuntimeError(sentinel)

    monkeypatch.setattr(p, "_rank_ic_fallback", fail_rank)
    helpers = p._validation_helpers()
    assert helpers == (fail_rank, p._newey_west_tstat_fallback, p._brier_reliability_fallback)
    response = web.api_predictions()
    assert imports and entered
    assert response.status_code == 200
    assert json.loads(response.body) == {
        "read_status": "unavailable", "error": "predictions_unavailable",
        "coverage": None, "scorecard": None,
    }
    assert sentinel not in response.body.decode() and sentinel not in caplog.text
    assert "/Users/private" not in response.body.decode() and "/Users/private" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_actual_prediction_summary_empty_ledger_remains_building(monkeypatch):
    import json
    from app import web
    from portfolio import predictions as p

    monkeypatch.setattr(p, "_load_ledger", lambda: [])
    imports = _force_engine_validation_unavailable(monkeypatch)
    response = web.api_predictions()
    payload = json.loads(response.body)
    assert response.status_code == 200 and imports
    assert "read_status" not in payload and "error" not in payload
    assert payload["coverage"]["n_total"] == 0 and payload["coverage"]["n_resolved"] == 0
    assert payload["scorecard"]["status"] == "building" and payload["scorecard"]["n_resolved"] == 0
    assert set(payload["scorecards_by_horizon"]) == {"3", "5", "10", "21"}
    for horizon, scorecard in payload["scorecards_by_horizon"].items():
        assert scorecard["status"] == "building" and scorecard["n_resolved"] == 0
        assert scorecard["horizon_d"] == int(horizon)


def test_non_import_error_validation_initialization_propagates(monkeypatch):
    from portfolio import predictions as p
    real_import = builtins.__import__
    calls = []

    def broken_initialization(name, *args, **kwargs):
        if name == "engine.validation":
            calls.append(name)
            raise RuntimeError("validation initialization failed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_initialization)
    with pytest.raises(RuntimeError, match="validation initialization failed"):
        p._validation_helpers()
    assert calls == ["engine.validation"]
