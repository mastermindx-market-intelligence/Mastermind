from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import pytest

from brain import trend_persistence as tp
from research import trend_persistence_panel as panel


def _prices(n_sessions: int, n_names: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n_sessions)
    drift = rng.normal(0.0003, 0.0004, n_names)
    steps = rng.normal(drift, 0.02, (n_sessions, n_names))
    steps[rng.random((n_sessions, n_names)) < 0.03] = 0.0        # flat sessions happen
    closes = pd.DataFrame(40.0 * np.exp(np.cumsum(steps, axis=0)), index=idx,
                          columns=[f"N{i:03d}" for i in range(n_names)])
    spy = pd.Series(300.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n_sessions))), index=idx)
    return closes, spy


def _membership(closes, **overrides):
    rows = [{"ticker": c, "start_date": closes.index[0], "end_date": pd.NaT}
            for c in closes.columns]
    mem = pd.DataFrame(rows)
    for ticker, (start, end) in overrides.items():
        mem.loc[mem["ticker"] == ticker, ["start_date", "end_date"]] = [start, end]
    mem["start_date"] = pd.to_datetime(mem["start_date"])
    mem["end_date"] = pd.to_datetime(mem["end_date"])
    return mem


def test_vectorized_features_match_the_canonical_definitions():
    closes, spy = _prices(330, 5, seed=1)
    rows = np.array([252, 277, 329])
    feats, ctrl = panel.compute_features(closes.to_numpy(float), spy.to_numpy(float), rows)
    checked = 0
    for j, name in enumerate(closes.columns):
        for a, row in enumerate(rows):
            rec = tp.extract(closes[name], benchmark=spy, asof=closes.index[row])
            for w in panel.WINDOWS:
                expected = {
                    f"efficiency_{w}d": rec["path_quality"][f"efficiency_{w}d"],
                    f"signed_efficiency_{w}d": rec["path_quality"][f"signed_efficiency_{w}d"],
                    f"positive_day_fraction_{w}d":
                        rec["path_quality"][f"positive_day_fraction_{w}d"],
                    f"directional_consistency_{w}d":
                        rec["path_quality"][f"directional_consistency_{w}d"],
                    f"retained_{w}d": rec["gain_retention"][f"retained_{w}d"],
                    f"max_drawdown_{w}d": rec["drawdown"][f"{w}d"]["max_drawdown"],
                    f"distance_to_high_{w}d": rec["drawdown"][f"{w}d"]["distance_to_high"],
                    f"sessions_since_high_{w}d": rec["drawdown"][f"{w}d"]["sessions_since_high"],
                }
                for key, want in expected.items():
                    assert want is not None, key
                    assert feats[key][a, j] == pytest.approx(want, abs=1e-9), (key, name, row)
                    checked += 1
            for w in panel.MOMENTUM_WINDOWS:
                assert ctrl[f"ret_{w}d"][a, j] == pytest.approx(
                    rec["momentum"][f"ret_{w}d"], abs=1e-9)
    assert checked == 5 * 3 * 3 * 8
    assert set(feats) == set(panel.FEATURES) and set(ctrl) == set(panel.CONTROLS)


def test_volatility_and_beta_controls_match_a_direct_computation():
    closes, spy = _prices(300, 3, seed=2)
    rows = np.array([260, 299])
    _, ctrl = panel.compute_features(closes.to_numpy(float), spy.to_numpy(float), rows)
    lr, lm = np.log(closes).diff(), np.log(spy).diff()
    for a, row in enumerate(rows):
        for j, name in enumerate(closes.columns):
            window = lr[name].iloc[row - 59: row + 1]
            assert ctrl["vol_60d"][a, j] == pytest.approx(window.std(ddof=1), rel=1e-9)
            x, m = lr[name].iloc[row - 251: row + 1], lm.iloc[row - 251: row + 1]
            beta = np.cov(x, m, ddof=1)[0, 1] / m.var(ddof=1)
            assert ctrl["beta_252d"][a, j] == pytest.approx(beta, rel=1e-8)


def test_features_do_not_read_the_future():
    closes, spy = _prices(320, 4, seed=3)
    rows = np.array([252, 262, 272])
    base, base_ctrl = panel.compute_features(closes.to_numpy(float), spy.to_numpy(float), rows)
    future = closes.copy()
    future.iloc[273:] *= 3.0                                  # rewrite everything after row 272
    later_spy = spy.copy()
    later_spy.iloc[273:] *= 0.5
    moved, moved_ctrl = panel.compute_features(future.to_numpy(float),
                                               later_spy.to_numpy(float), rows)
    for key in base:
        np.testing.assert_array_equal(base[key], moved[key])
    for key in base_ctrl:
        np.testing.assert_array_equal(base_ctrl[key], moved_ctrl[key])


def test_a_window_with_a_missing_price_yields_no_value():
    closes, spy = _prices(300, 2, seed=4)
    P = closes.to_numpy(float).copy()
    P[280, 0] = np.nan
    feats, ctrl = panel.compute_features(P, spy.to_numpy(float), np.array([299]))
    assert np.isnan(feats["efficiency_20d"][0, 0]) and np.isnan(feats["max_drawdown_60d"][0, 0])
    assert np.isnan(ctrl["ret_252d"][0, 0]) and np.isnan(ctrl["vol_60d"][0, 0])
    assert np.isfinite(feats["efficiency_20d"][0, 1])


def test_labels_enter_after_formation_and_carry_delisted_names():
    closes, spy = _prices(300, 3, seed=5)
    P = closes.to_numpy(float).copy()
    P[271:, 2] = np.nan                                         # last trade on row 270
    s = spy.to_numpy(float)
    rows = np.array([252, 262, 292])
    lab = panel.compute_labels(P, s, rows, horizons=(5, 20), lag=1)

    five = lab[5]
    assert five["forward_return"][0, 0] == pytest.approx(P[258, 0] / P[253, 0] - 1.0)
    assert five["forward_rel"][0, 0] == pytest.approx(
        P[258, 0] / P[253, 0] - 1.0 - (s[258] / s[253] - 1.0))
    path = P[253:259, 0]
    assert five["forward_max_drawdown"][0, 0] == pytest.approx(
        float((path / np.maximum.accumulate(path) - 1.0).min()))
    # formation-day price never enters the label
    bumped = P.copy()
    bumped[252, 0] *= 5.0
    again = panel.compute_labels(bumped, s, rows, horizons=(5,), lag=1)[5]
    assert again["forward_return"][0, 0] == five["forward_return"][0, 0]

    twenty = lab[20]
    # the delisting name is kept: exit priced at its last trade, and flagged
    assert not five["delisted_in_window"][0, 2]
    assert twenty["delisted_in_window"][0, 2]
    assert twenty["forward_return"][0, 2] == pytest.approx(P[270, 2] / P[253, 2] - 1.0)
    # a label whose exit is past the panel end does not exist
    assert not twenty["observable"][2] and np.isnan(twenty["forward_return"][2]).all()
    assert five["observable"][2]


def test_delisting_flag_only_fires_when_the_exit_has_no_trade():
    closes, spy = _prices(300, 2, seed=6)
    P = closes.to_numpy(float).copy()
    P[271:, 1] = np.nan
    lab = panel.compute_labels(P, spy.to_numpy(float), np.array([262, 266]), horizons=(5,))[5]
    assert not lab["delisted_in_window"][0, 1]                  # exit row 268: traded
    assert lab["delisted_in_window"][1, 1]                      # exit row 272: carried


def test_membership_mask_matches_the_audited_predicate():
    closes, _ = _prices(120, 4, seed=7)
    idx = closes.index
    mem = _membership(closes, N001=(idx[10], idx[50]), N002=(idx[90], pd.NaT))
    mem = pd.concat([mem, pd.DataFrame([{"ticker": "N001", "start_date": idx[80],
                                         "end_date": idx[100]}])], ignore_index=True)
    mask = panel.membership_mask(idx, list(closes.columns), mem)
    for i, t in enumerate(idx):
        active = mem[(mem["start_date"] <= t) & (mem["end_date"].isna() | (mem["end_date"] > t))]
        want = set(active["ticker"])
        got = {c for c, flag in zip(closes.columns, mask[i]) if flag}
        assert got == want, t


def test_semi_partial_rank_ic_reproduces_the_frozen_judge():
    V = pytest.importorskip("engine.validation")
    rng = np.random.default_rng(8)
    n = 240
    Z = rng.normal(size=(n, 3))
    X = np.column_stack([Z[:, 0] * 0.7 + rng.normal(size=n), rng.normal(size=n)])
    Y = np.column_stack([X[:, 0] * 0.3 + Z[:, 1] + rng.normal(size=n), rng.normal(size=n)])
    ic, _ = panel.semi_partial_rank_ic(X, Z, Y)
    names = [f"n{i}" for i in range(n)]
    loadings = pd.DataFrame(Z, index=names).rank()
    for k in range(X.shape[1]):
        resid = V.cross_sectional_resid(pd.Series(X[:, k], index=names).rank(), loadings)
        for e in range(Y.shape[1]):
            want = V.rank_ic(resid, pd.Series(Y[:, e], index=names))
            assert ic[k, e] == pytest.approx(want, abs=1e-10)


def _synthetic_panel(holdout_start: str):
    closes, spy = _prices(520, 130, seed=9)
    closes.insert(0, "SPY", spy)
    mem = _membership(closes.drop(columns="SPY"))
    return panel.build_panel(closes, mem, holdout_start=holdout_start)


def test_development_sample_never_touches_a_holdout_price():
    built = _synthetic_panel("2020-06-01")
    first_holdout = int(built["index"].searchsorted(pd.Timestamp("2020-06-01")))
    assert 252 < first_holdout < len(built["index"])
    for h in panel.HORIZONS:
        dev = panel.sample_rows(built, h, "dev")
        hold = panel.sample_rows(built, h, "holdout")
        assert len(dev) and len(hold)
        assert (built["labels"][h]["exit_rows"][dev] < first_holdout).all()
        assert (built["rows"][hold] >= first_holdout).all()
        assert not set(dev) & set(hold)


def test_holdout_is_locked_without_the_preregistration_hash():
    built = _synthetic_panel("2020-06-01")
    with pytest.raises(panel.HoldoutLocked):
        panel.score(built, sample="holdout")
    with pytest.raises(panel.HoldoutLocked):
        panel.score(built, sample="holdout", prereg_hash="0" * 64, confirm={"x": 1})
    with pytest.raises(panel.HoldoutLocked):
        panel.run(sample="holdout")
    # with the right hash but no development survivor, the holdout is left unspent
    out = panel.score(built, sample="holdout", prereg_hash=panel.prereg_sha256(), confirm={})
    assert out["status"] == "not_run"


def test_development_scoring_runs_every_preregistered_test():
    pytest.importorskip("engine.validation")
    built = _synthetic_panel("2020-06-01")
    out = panel.score(built, sample="dev")
    assert out["status"] == "scored" and out["sample"] == "dev"
    assert out["prereg_sha256"] == panel.prereg_sha256()
    assert out["n_tests"] == len(panel.FEATURES) * len(panel.HORIZONS) * len(panel.ENDPOINTS)
    assert out["n_tests"] == 144
    one = out["tests"]["signed_efficiency_60d|20|forward_rel"]
    assert one["family"] == "path_quality" and one["n_dates"] > 8
    assert set(one["gates"]) == {"g1_bh_fdr", "g2_ic_floor", "g3_thinned", "g4_eras",
                                 "g5_momentum_buckets", "g6_delisting_invariant"}
    assert all(isinstance(v, bool) for v in one["gates"].values())
    assert len(one["bucket_means"]) == panel.N_BUCKETS and len(one["bin_means"]) == panel.N_BINS
    assert set(out["survivors"]) == {k for k, st in out["tests"].items() if st["advance_dev"]}
    assert set(out["family_summary"]) == {f"{f}|{e}" for f in panel.FAMILIES
                                          for e in panel.ENDPOINTS}
    json.dumps(out, default=str)


def test_holdout_reports_only_the_survivors_it_was_asked_to_confirm():
    pytest.importorskip("engine.validation")
    built = _synthetic_panel("2020-06-01")
    key = "retained_60d|5|forward_rel"
    out = panel.score(built, sample="holdout", prereg_hash=panel.prereg_sha256(),
                      confirm={key: 1})
    assert out["status"] == "scored" and list(out["tests"]) == [key]
    assert set(out["tests"][key]["holdout_gates"]) == {
        "h1_same_sign", "h2_one_sided_p", "h3_bh_fdr", "h4_ic_floor"}
    assert out["n_confirm_requested"] == 1


def test_a_planted_conditional_signal_is_recovered_with_the_right_sign():
    pytest.importorskip("engine.validation")
    rng = np.random.default_rng(10)
    n_names = 150
    X = rng.normal(size=(n_names, 2))
    Z = rng.normal(size=(n_names, 2))
    y_pos = 0.5 * X[:, 0] + Z[:, 0] + rng.normal(size=n_names)
    y_neg = -0.5 * X[:, 0] + Z[:, 0] + rng.normal(size=n_names)
    ic, _ = panel.semi_partial_rank_ic(X, Z, np.column_stack([y_pos, y_neg]))
    assert ic[0, 0] > 0.15 and ic[0, 1] < -0.15
    assert abs(ic[1, 0]) < 0.2 and abs(ic[1, 1]) < 0.2


def test_preregistration_freezes_the_instrument_constants():
    text = open(panel.PREREG_PATH, encoding="utf-8").read()
    block = re.search(r"```json\n(.*?)\n```", text, re.S)
    assert block, "pre-registration must carry its machine-readable design block"
    assert json.loads(block.group(1)) == panel.frozen_design()
    assert panel.prereg_sha256() and len(panel.prereg_sha256()) == 64
    assert pd.Timestamp(panel.HOLDOUT_START) == pd.Timestamp("2022-01-01")


def test_every_feature_belongs_to_exactly_one_family():
    assert len(panel.FEATURES) == 24 and len(set(panel.FEATURES)) == 24
    assert {panel.family_of(f) for f in panel.FEATURES} == set(panel.FAMILIES)
