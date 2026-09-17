"""Regression for the synthetic do-nothing shadow arm.

The arm is the churn counterfactual: after its one inception rebalance, later signals and market-price
moves may change marked NAV but must never change held share inventory or cash.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

import bot  # noqa: F401 — bootstrap vendored macro
from portfolio import shadow_books as S


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "_SHADOW", tmp_path)
    monkeypatch.setattr(S, "_INPUTS", tmp_path / "inputs")
    monkeypatch.setattr(S, "_BOOKS", tmp_path / "books")
    monkeypatch.setattr(S, "_LEADERBOARD", tmp_path / "leaderboard.json")
    return tmp_path


def _rec(ticker: str, weight: float) -> dict:
    return {
        "ticker": ticker,
        "forge_confirmed": True,
        "base_weight": weight,
        "name_cap": 1.0,
        "weight_forge": weight,
        "weight_prod": weight,
        "committee": None,
        "sentinel": None,
        "price": 100.0,
        "raw_prob_correct": 0.55,
        "horizon_d": 21,
    }


def _prices(**extra) -> dict:
    base = {t: 100.0 for t in S._DEFENSIVE_BASKET}
    base.update({"SPY": 500.0}, **extra)
    return base


def test_do_nothing_changes_nav_but_never_shares_or_cash_after_inception(sandbox):
    day1 = S.run(
        "2026-06-01",
        prices=_prices(AAA=100.0),
        inputs=[_rec("AAA", 0.20)],
    )
    before = deepcopy(S._load_account("do_nothing"))
    before_nav = day1["books"]["do_nothing"]["nav"]

    assert before["positions"]["AAA"]["shares"] > 0

    # AAA rallies hard and an unrelated BBB signal arrives. The do-nothing arm should merely mark
    # its original AAA inventory; it must not trim AAA, buy BBB, or change cash.
    day2 = S.run(
        "2026-06-02",
        prices=_prices(AAA=150.0, BBB=50.0, SPY=510.0),
        inputs=[_rec("BBB", 0.80)],
    )
    after = S._load_account("do_nothing")

    assert set(after["positions"]) == {"AAA"}
    assert after["positions"]["AAA"]["shares"] == pytest.approx(
        before["positions"]["AAA"]["shares"]
    )
    assert after["cash"] == pytest.approx(before["cash"])
    assert day2["books"]["do_nothing"]["nav"] > before_nav
