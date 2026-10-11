from __future__ import annotations

import pandas as pd

from research import trend_persistence_experiment as exp


def _series(mult: float, periods: int = 330):
    idx = pd.bdate_range("2025-01-01", periods=periods)
    vals = [100.0]
    for i in range(1, periods):
        vals.append(vals[-1] * (1.0 + mult + (0.001 if i % 7 == 0 else 0.0)))
    return pd.Series(vals, index=idx)


def test_build_panel_is_point_in_time_and_forward_labels_are_future_only():
    spy = _series(0.0005)
    aaa = _series(0.0010)
    rows = exp.build_panel({"AAA": aaa}, spy, horizons=(5,), formation_step=20, min_history=253)
    assert rows
    first = rows[0]
    pos = aaa.index.get_loc(pd.Timestamp(first["asof"]))
    expected = (aaa.iloc[pos + 5] / aaa.iloc[pos] - 1.0) - (
        spy.iloc[pos + 5] / spy.iloc[pos] - 1.0
    )
    assert first["forward_rel"] == expected
    assert first["continued"] == int(expected > 0)
    assert first["persistence.asof"] == first["asof"]


def test_build_panel_respects_point_in_time_eligibility():
    spy = _series(0.0005)
    aaa = _series(0.0010)
    seen = []
    def eligible(ticker, asof):
        seen.append((ticker, asof))
        return False

    rows = exp.build_panel(
        {"AAA": aaa}, spy, horizons=(5,), formation_step=20,
        min_history=253, eligible_asof=eligible,
    )
    assert seen
    assert rows == []


def test_evaluate_reports_raw_and_momentum_conditioned_rank_ic():
    rows = []
    dates = pd.bdate_range("2026-01-02", periods=50)
    for di, d in enumerate(dates[::5]):
        for i in range(30):
            mom = (i - 15) / 100.0
            quality = (i % 7) / 10.0
            rows.append({
                "asof": str(d)[:10], "ticker": f"T{i:02d}", "horizon_d": 5,
                "persistence.momentum.ret_20d": mom,
                "persistence.momentum.ret_60d": mom * 0.8,
                "persistence.momentum.ret_120d": mom * 0.6,
                "persistence.momentum.ret_252d": mom * 0.4,
                "persistence.path_quality.efficiency_20d": quality,
                "forward_rel": mom + quality * 0.2 + di * 0.0001,
            })
    out = exp.evaluate(rows, horizons=(5,))
    feat = out["horizons"]["5"]["features"]["persistence.path_quality.efficiency_20d"]
    assert feat["raw_ic"]["n_dates"] >= 8
    assert feat["conditional_rank_ic"]["n_dates"] >= 8
    assert feat["conditional_rank_ic"]["mean"] is not None
