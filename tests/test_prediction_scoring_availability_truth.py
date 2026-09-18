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
