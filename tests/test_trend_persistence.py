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
    assert out["path_quality"]["directional_consistency_60d"] == pytest.approx(1.0)
    assert out["gain_retention"]["retained_60d"] == pytest.approx(1.0)
    assert out["drawdown"]["60d"]["max_drawdown"] == pytest.approx(0.0)
    assert out["drawdown"]["60d"]["distance_to_high"] == pytest.approx(0.0)


def test_path_efficiency_is_bounded_scale_invariant_and_symmetric():
    up = _series([100.0 * (1.003 ** i) for i in range(80)])
    down = _series([100.0 * (0.997 ** i) for i in range(80)])
    scaled = up * 17.0

    for s in (up, down, scaled):
        value = tp.extract(s)["path_quality"]["efficiency_60d"]
        assert 0.0 <= value <= 1.0
        assert value == pytest.approx(1.0)

    assert tp.extract(up)["path_quality"]["efficiency_60d"] == pytest.approx(
        tp.extract(scaled)["path_quality"]["efficiency_60d"]
    )


def test_choppy_path_has_lower_efficiency_and_retention_than_smooth_path():
    smooth = _series([100.0 * (1.002 ** i) for i in range(80)])
    vals = [100.0]
    for i in range(1, 80):
        vals.append(vals[-1] * (1.018 if i % 2 else 0.986))
    choppy = _series(vals)

    a = tp.extract(smooth)
    b = tp.extract(choppy)

    assert a["path_quality"]["efficiency_60d"] > b["path_quality"]["efficiency_60d"]
    assert a["path_quality"]["directional_consistency_60d"] > b["path_quality"]["directional_consistency_60d"]
    assert a["gain_retention"]["retained_60d"] > b["gain_retention"]["retained_60d"]


def test_asof_excludes_future_prices_and_is_unchanged_by_future_append():
    base = _series([100.0 + i for i in range(100)])
    cutoff = base.index[69]
    before = tp.extract(base, asof=cutoff)

    extended = pd.concat([
        base,
        _series([1000.0, 10.0, 2000.0], start=str((base.index[-1] + pd.offsets.BDay(1)).date())),
    ])
    after = tp.extract(extended, asof=cutoff)

    assert before == after
    assert before["observations"] == 70
    assert before["asof"] == str(cutoff)[:10]
    expected = float(base.iloc[69] / base.iloc[49] - 1.0)
    assert before["momentum"]["ret_20d"] == pytest.approx(expected)


def test_distance_to_high_detects_giveback():
    vals = [100.0 + i for i in range(70)] + [168.0, 165.0, 160.0, 155.0, 150.0]
    out = tp.extract(_series(vals))
    shape = out["drawdown"]["60d"]
    assert shape["sessions_since_high"] == 5
    assert shape["distance_to_high"] < 0
    assert shape["current_drawdown"] == pytest.approx(shape["distance_to_high"])


def test_short_or_bad_history_degrades_to_nulls():
    s = _series([0.0, -1.0, 100.0, 101.0, 102.0])
    out = tp.extract(s)

    assert out["observations"] == 3
    assert out["momentum"]["ret_20d"] is None
    assert out["path_quality"]["efficiency_20d"] is None
    assert out["drawdown"]["20d"]["max_drawdown"] is None
    assert out["drawdown"]["20d"]["distance_to_high"] is None


def test_flatten_keeps_feature_namespaces():
    out = tp.flatten(tp.extract(_series([100.0 + i for i in range(80)])))
    assert "persistence.momentum.ret_20d" in out
    assert "persistence.path_quality.efficiency_60d" in out
    assert "persistence.path_quality.directional_consistency_60d" in out
    assert "persistence.gain_retention.retained_60d" in out
    assert "persistence.drawdown.60d.distance_to_high" in out
