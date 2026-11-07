"""Opus-distillation model (brain.distill, #3 v2) — a CatBoost classifier that mimics Opus's buys.

Pins the rank-AUC helper, the Opus-buys/universe join + labels, the degrade-safe train paths, and (with
catboost) a real walk-forward train where Opus 'buys' high-momentum names so the model must learn them.
CatBoost optional: the heavy test is importorskip'd.
"""
from __future__ import annotations

import pytest

from brain import distill as D


def _pairwise_auc(y, scores):
    """Independent probability-of-superiority reference: wins + half-credit ties.

    This compares every positive/negative pair rather than implementing rank averaging.
    See https://arxiv.org/abs/2409.05038 for the tie-adjusted Mann-Whitney effect.
    """
    positives = [score for label, score in zip(y, scores) if label == 1]
    negatives = [score for label, score in zip(y, scores) if label == 0]
    if not positives or not negatives:
        return None
    credit = sum(
        1.0 if positive > negative else 0.5 if positive == negative else 0.0
        for positive in positives
        for negative in negatives
    )
    return round(credit / (len(positives) * len(negatives)), 3)


def test_auc_all_ties_receive_half_credit_in_either_class_order():
    for y in ([0, 1], [1, 0], [0, 0, 1, 1], [1, 1, 0, 0], [1, 0, 1, 0]):
        assert D._auc(y, [0.5] * len(y)) == 0.5


def test_auc_mixed_ties_match_pairwise_half_credit():
    cases = (
        ([0, 1, 0, 1], [0.1, 0.1, 0.8, 0.8]),
        ([0, 0, 1, 1], [0.1, 0.4, 0.4, 0.9]),
        ([1, 0, 0, 1, 0, 1], [-2.0, -2.0, 0.0, 0.0, 4.0, 4.0]),
    )
    for y, scores in cases:
        assert D._auc(y, scores) == _pairwise_auc(y, scores)


def test_auc_joint_row_permutations_preserve_mixed_tie_result():
    from itertools import permutations

    y = [0, 1, 0, 1, 1, 0]
    scores = [0.1, 0.1, 0.4, 0.4, 0.9, 0.9]
    expected = _pairwise_auc(y, scores)
    count = 0
    for order in permutations(range(len(y))):
        assert D._auc([y[i] for i in order], [scores[i] for i in order]) == expected
        count += 1
    assert count == 720


def test_auc_exhaustive_small_populations_match_pairwise_reference():
    from itertools import product

    count = 0
    for size in range(2, 6):
        for rows in product(tuple(product((0, 1), (-1.0, 0.0, 1.0))), repeat=size):
            y, scores = zip(*rows)
            if len(set(y)) < 2:
                continue
            assert D._auc(y, scores) == _pairwise_auc(y, scores), (y, scores)
            count += 1
    assert count == 8604


def test_auc_retains_three_decimal_rounding():
    assert D._auc([1, 0, 0, 0], [1.0, 0.0, 2.0, 3.0]) == 0.333
    assert D._auc([1, 0, 0, 0], [2.0, 0.0, 1.0, 3.0]) == 0.667
    assert D._auc([1, 0, 0, 0], [0.0, 0.0, 1.0, 2.0]) == 0.167


def test_auc_empty_and_one_class_populations_stay_undefined():
    for y, scores in (([], []), ([0, 0], [0.1, 0.9]), ([1, 1], [0.1, 0.9])):
        assert D._auc(y, scores) is None


def test_auc_does_not_mutate_array_inputs():
    import numpy as np

    y = np.array([1, 0, 1, 0])
    scores = np.array([0.8, 0.8, 0.1, 0.1])
    original_y, original_scores = y.copy(), scores.copy()
    assert D._auc(y, scores) == 0.5
    np.testing.assert_array_equal(y, original_y)
    np.testing.assert_array_equal(scores, original_scores)


def test_auc_large_tie_group_retains_half_credit():
    import numpy as np

    y = np.tile([0, 1], 10_000)
    assert D._auc(y, np.full(len(y), 0.5)) == 0.5


def test_auc_untied_populations_preserve_ordinal_rank_results():
    import numpy as np

    rng = np.random.default_rng(20261013)
    for size in range(2, 32):
        for _ in range(10):
            y = rng.integers(0, 2, size=size)
            y[0], y[1] = 0, 1
            scores = rng.permutation(size).astype(float)
            # With no ties, each value has its unique one-based ordinal rank.
            n_pos, n_neg = int((y == 1).sum()), int((y == 0).sum())
            rank_sum = (scores[y == 1] + 1).sum()
            expected = round(float((rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)), 3)
            assert D._auc(y, scores) == expected



def _panel(n: int = 460, ntick: int = 30, start: str = "2024-05-01"):
    import numpy as np
    import pandas as pd
    idx = pd.bdate_range(start, periods=n)
    cols = {}
    for i in range(ntick):
        slope = 60 + 4.0 * i                                   # higher i → stronger trend (higher ret_252)
        cols[f"T{i:02d}"] = pd.Series(np.linspace(100, 100 + slope, n), index=idx)
    spy = pd.Series(np.linspace(400, 440, n), index=idx)
    return cols, spy


def test_auc_rank_separation():
    assert D._auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0    # perfect ranking
    assert D._auc([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]) == 0.0    # reversed
    assert D._auc([1, 1], [0.5, 0.5]) is None                   # one class only → undefined


def test_opus_buys_are_fresh_entries_not_holdings(monkeypatch):
    # `holdings` is the full daily book; a buy is the DELTA. AAA is held both days → it's a buy ONCE.
    from brain import calibration
    monkeypatch.setattr(calibration, "_book_decisions", lambda book: iter([
        {"asof": "2026-06-21", "holdings": [{"ticker": "AAA"}, {"ticker": "bbb"}]},
        {"asof": "2026-06-22", "holdings": [{"ticker": "AAA"}, {"ticker": "CCC"}]},   # AAA held, CCC new
        {"asof": "", "holdings": [{"ticker": "X"}]},            # no date → dropped
    ]))
    buys = D._opus_buys()
    assert buys == {"2026-06-21": {"AAA", "BBB"}, "2026-06-22": {"CCC"}}   # AAA NOT re-counted on 06-22


def test_dataset_labels_positives_and_negatives(monkeypatch):
    panel, spy = _panel()
    asof = panel["T00"].index[-1].strftime("%Y-%m-%d")
    from portfolio import predictions as P
    from brain import calibration
    monkeypatch.setattr(P, "_load_panel", lambda: panel)
    monkeypatch.setattr(P, "_spy_series", lambda: spy)
    monkeypatch.setattr(P, "_load_ledger", lambda: [{"asof": asof, "ticker": t} for t in panel])
    monkeypatch.setattr(calibration, "_book_decisions",
                        lambda book: iter([{"asof": asof, "holdings": [{"ticker": "T29"}, {"ticker": "T28"}]}]))
    rows, _, _ = D._dataset(asof)
    by_tk = {r["ticker"]: r for r in rows}
    assert by_tk["T29"]["y"] == 1 and by_tk["T28"]["y"] == 1    # bought → positive
    assert by_tk["T00"]["y"] == 0                               # not bought → negative
    assert all("ret_252" in r for r in rows)                   # carries the PIT feature vector


def test_train_unavailable_without_catboost(monkeypatch, tmp_path):
    monkeypatch.setattr(D, "_classifier", lambda: None)
    monkeypatch.setattr(D, "_DIR", tmp_path)
    monkeypatch.setattr(D, "_METRICS", tmp_path / "m.json")
    assert D.train("2026-06-25")["status"] == "unavailable"


def test_train_building_below_min_positives(monkeypatch, tmp_path):
    monkeypatch.setattr(D, "_classifier", lambda: object)
    monkeypatch.setattr(D, "_dataset", lambda asof=None: ([{"asof": "2026-06-21", "y": 1}], None, None))
    monkeypatch.setattr(D, "_DIR", tmp_path)
    monkeypatch.setattr(D, "_METRICS", tmp_path / "m.json")
    out = D.train("2026-06-25")
    assert out["status"] == "building" and out["n_pos"] == 1


def test_train_real_catboost_learns_opus(monkeypatch, tmp_path):
    pytest.importorskip("catboost")
    import numpy as np
    import pandas as pd
    n = 520
    idx = pd.bdate_range("2024-05-01", periods=n)
    cols = {f"L{i:02d}": pd.Series(np.linspace(100, 101, n), index=idx) for i in range(30)}      # flat lows
    cols.update({f"H{i:02d}": pd.Series(np.linspace(100, 140 + i, n), index=idx) for i in range(70)})  # rising
    spy = pd.Series(np.linspace(400, 440, n), index=idx)
    lows = [f"L{i:02d}" for i in range(30)]
    dates = [idx[300 + 10 * k].strftime("%Y-%m-%d") for k in range(14)]   # 14 dates, all ≥260 history
    # Opus INITIATES 5 NEW high-momentum names each date (book accumulates) → 70 fresh buys, all high-trend
    holdings = [[f"H{j:02d}" for j in range(5 * (k + 1))] for k in range(14)]
    fresh = lambda k: [f"H{j:02d}" for j in range(5 * k, 5 * k + 5)]
    from portfolio import predictions as P
    from brain import calibration
    monkeypatch.setattr(P, "_load_panel", lambda: cols)
    monkeypatch.setattr(P, "_spy_series", lambda: spy)
    monkeypatch.setattr(P, "_load_ledger", lambda: [   # per-date universe = that day's fresh-5 high + all lows
        {"asof": dates[k], "ticker": t} for k in range(14) for t in (fresh(k) + lows)])
    monkeypatch.setattr(P, "universe", lambda: [{"ticker": t, "dir": "up", "score": 0, "band": "na",
                                                 "price": 100.0} for t in cols])
    monkeypatch.setattr(calibration, "_book_decisions", lambda book: iter([
        {"asof": dates[k], "holdings": [{"ticker": t} for t in holdings[k]]} for k in range(14)]))
    monkeypatch.setattr(D, "_DIR", tmp_path)
    monkeypatch.setattr(D, "_MODEL", tmp_path / "model.cbm")
    monkeypatch.setattr(D, "_METRICS", tmp_path / "m.json")
    out = D.train("2026-06-25")
    assert out["status"] == "scoring" and out["n_pos"] >= D._MIN_POS    # 5 fresh × 14 = 70 positives
    assert out["oos_auc"] is not None and out["oos_auc"] > 0.6          # learns Opus initiates high-momentum
    assert isinstance(D.predict("2026-06-25"), list)
