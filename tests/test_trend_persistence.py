from __future__ import annotations

import pandas as pd
import pytest

from brain import trend_persistence as tp


def _series(values, start="2026-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_extract_separates_momentum_from_path_quality():
    smooth = _series([100.0 + i for i in range(130)])
    benchmark = _series([100.0 + 0.25 * i for i in range(130)])
    out = tp.extract(smooth, benchmark=benchmark)

    assert out["schema"] == 1
    assert out["momentum"]["ret_60d"] > 0
    assert out["relative_strength"]["excess_60d"] > 0
    assert out["path_quality"]["efficiency_60d"] == pytest.approx(1.0)
    assert out["gain_retention"]["retained_60d"] == pytest.approx(1.0)
    assert out["drawdown"]["60d"]["max_drawdown"] == pytest.approx(0.0)


def test_choppy_path_has_lower_efficiency_and_retention_than_smooth_path():
    # Both end higher, but the second path repeatedly gives gains back.
    smooth = _series([100.0 * (1.002 ** i) for i in range(80)])
    vals = [100.0]
    for i in range(1, 80):
        vals.append(vals[-1] * (1.018 if i % 2 else 0.986))
    choppy = _series(vals)

    a = tp.extract(smooth)
    b = tp.extract(choppy)

    assert a["path_quality"]["efficiency_60d"] > b["path_quality"]["efficiency_60d"]
    assert a["gain_retention"]["retained_60d"] > b["gain_retention"]["retained_60d"]


def test_asof_excludes_future_prices():
    s = _series([100.0 + i for i in range(100)])
    cutoff = s.index[69]
    out = tp.extract(s, asof=cutoff)

    assert out["observations"] == 70
    assert out["asof"] == str(cutoff)[:10]
    expected = float(s.iloc[69] / s.iloc[49] - 1.0)
    assert out["momentum"]["ret_20d"] == pytest.approx(expected)


def test_short_or_bad_history_degrades_to_nulls():
    s = _series([0.0, -1.0, 100.0, 101.0, 102.0])
    out = tp.extract(s)

    assert out["observations"] == 3
    assert out["momentum"]["ret_20d"] is None
    assert out["path_quality"]["efficiency_20d"] is None
    assert out["drawdown"]["20d"]["max_drawdown"] is None


def test_flatten_keeps_feature_namespaces():
    out = tp.flatten(tp.extract(_series([100.0 + i for i in range(80)])))
    assert "persistence.momentum.ret_20d" in out
    assert "persistence.path_quality.efficiency_60d" in out
    assert "persistence.gain_retention.retained_60d" in out
