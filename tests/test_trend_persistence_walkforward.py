from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pytest

from research import trend_persistence_panel as tpp
from research import trend_persistence_walkforward as wf

N_NAMES = 160
START, N_SESSIONS = "2016-01-01", 2700  # … to spring 2026: early blocks get enough training
MDD = "max_drawdown_60d"                # confirmed at every horizon


def _panel(seed: int = 0, signal: float = 0.0, curve: float = 0.0, descriptor: float = 0.0,
           window_vol: float = 0.0, horizons=tpp.HORIZONS):
    """A panel and its price-only inputs with a known data-generating process.

    Forward drawdown deepens with ``vol_60d``, with ``curve`` times its square, with ``signal``
    times ``max_drawdown_60d``, with ``descriptor`` times ``ewma_vol_3`` and with ``window_vol``
    times the label window's own volatility. Everything else is noise.
    """
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(START, periods=N_SESSIONS)
    rows = np.arange(tpp.MIN_HISTORY, N_SESSIONS, tpp.FORMATION_STEP)
    F = len(rows)
    feats = {f: rng.normal(size=(F, N_NAMES)) for f in tpp.FEATURES}
    ctrl = {c: rng.normal(size=(F, N_NAMES)) for c in tpp.design_of("v2").controls}
    desc = {k: rng.normal(size=(F, N_NAMES)) for k in wf.DESCRIPTORS}
    labels, label_vol = {}, {}
    for h in horizons:
        fv = rng.normal(size=(F, N_NAMES))
        risk = (0.8 * ctrl["vol_60d"] + curve * ctrl["vol_60d"] ** 2 + signal * feats[MDD]
                + descriptor * desc["ewma_vol_3"] + window_vol * fv
                + rng.normal(size=(F, N_NAMES)))
        exit_rows = rows + tpp.ENTRY_LAG + h
        labels[int(h)] = {"forward_max_drawdown": -0.05 * np.exp(0.5 * risk),
                          "observable": exit_rows < N_SESSIONS, "exit_rows": exit_rows}
        label_vol[int(h)] = fv
    panel = {"index": index, "names": [f"N{i:03d}" for i in range(N_NAMES)], "rows": rows,
             "features": feats, "controls": ctrl, "labels": labels,
             "eligible": np.ones((F, N_NAMES), bool), "step": tpp.FORMATION_STEP,
             "lag": tpp.ENTRY_LAG, "horizons": tuple(horizons), "observed_mask": True,
             "printed_floor": True, "store_sourced": np.zeros(N_NAMES, bool),
             "digest": "synthetic"}
    return panel, {"descriptors": desc, "label_vol": label_vol}


def _holdout_like(panel, inputs):
    """A V2-holdout-shaped result that this panel reproduces, so ``compare`` can run on it."""
    V = tpp._judges()
    tests = {}
    for h in wf.HORIZONS:
        for key, st in wf.summarise_q2(V, wf.assemble(panel, inputs, h), h,
                                       panel["step"]).items():
            tests[key] = {"confirmed_holdout": True, "mean": st["v2"]["mean"],
                          "n_dates": st["v2"]["n_dates"],
                          "dev_sign": 1 if st["v2"]["mean"] >= 0 else -1}
    return {"tests": tests}


def _reference(lo: float = -0.002, hi: float = 0.002):
    runs = [{"q2": {k: {s: v for s in wf.Q2_SERIES} for k in wf.confirmed_keys()}}
            for v in (lo, hi)]
    return {"runs": runs, "q1_ranges": {}}


@pytest.fixture
def pinned(monkeypatch):
    monkeypatch.setattr(wf, "PREREG_SHA256", wf.prereg_sha256())


# ---- pieces ---------------------------------------------------------------------------------
def test_ranks_are_centred_and_bounded():
    r = wf._centred_ranks(np.random.default_rng(0).normal(size=(101, 3)))
    assert np.allclose(r.mean(axis=0), 0.0)
    assert r.min() > -0.5 and r.max() < 0.5


def test_the_event_is_exactly_the_deepest_tenth_of_a_date():
    v = np.random.default_rng(1).normal(size=137)
    mask = wf._deepest(v, 0.10)
    assert mask.sum() == 13
    assert v[mask].max() <= v[~mask].min()
    top = wf._deepest(v, 0.10, largest=True)
    assert top.sum() == 13 and v[top].min() >= v[~top].max()


@pytest.mark.parametrize("h", wf.HORIZONS)
def test_models_nest_and_the_augmented_model_adds_only_confirmed_features(h):
    cols = wf.columns(h)
    n_c, n_d = len(tpp.design_of("v2").controls), len(wf.DESCRIPTORS)
    n_f = sum(len(v) for v in wf.CONFIRMED[h].values())
    assert set(cols["B0"]) < set(cols["B1"]) < set(cols["B2"]) < set(cols["A"])
    assert len(cols["B0"]) == n_c == 11 and len(cols["B1"]) == 2 * n_c
    assert len(cols["B2"]) == 2 * n_c + 2 * n_d + 6 == 50
    assert len(cols["A"]) == len(cols["B2"]) + n_f
    assert set(cols["A_dd"]) | set(cols["A_pq"]) == set(cols["A"])
    assert set(cols["A_dd"]) & set(cols["A_pq"]) == set(cols["B2"])
    for fam in wf.CONFIRMED[h].values():
        assert set(fam) <= set(tpp.FEATURES)


def test_confirmed_features_are_the_committed_holdout_result():
    path = os.path.join(os.path.dirname(wf.__file__), wf.HOLDOUT_RESULT_FILE)
    with open(path) as fh:
        held = json.load(fh)
    tests = held["tests"]
    confirmed = sorted(k for k, st in tests.items() if st["confirmed_holdout"])
    assert confirmed == sorted(wf.confirmed_keys()) and len(confirmed) == 29
    # and the panel B2 will accept is the one that result was scored on
    assert wf.V2_PANEL_SHA256 == held["panel_sha256"] and len(wf.V2_PANEL_SHA256) == 64


def test_logistic_fit_recovers_known_coefficients_from_any_start():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(200_000, 2))
    p = 1 / (1 + np.exp(-(-2.0 + 0.7 * X[:, 0] - 0.4 * X[:, 1])))
    e = (rng.random(len(p)) < p).astype(float)
    A = wf._with_intercept(X)
    b = wf.fit_logit(A, e)
    assert b == pytest.approx([-2.0, 0.7, -0.4], abs=0.03)
    assert wf.fit_logit(A, e, b0=np.array([-1.0, 0.0, 0.3])) == pytest.approx(b, abs=1e-6)
    y = 0.3 + X @ np.array([0.5, -0.2]) + rng.normal(size=len(X))
    assert wf.fit_ols(A, y) == pytest.approx(np.linalg.lstsq(A, y, rcond=None)[0], abs=1e-9)


def test_descriptors_match_their_definitions_and_need_a_fully_quoted_window():
    rng = np.random.default_rng(12)
    T, N = 500, 5
    P = 50.0 * np.exp(np.cumsum(0.02 * rng.normal(size=(T, N)), axis=0))
    P[300, 1] = np.nan                                       # one unquoted cell: two returns lost
    rows = np.array([60, 200, 322, 499])
    got = wf.descriptors(P, rows)
    r = np.diff(np.log(P), axis=0, prepend=np.nan)
    f, n = 200, 0
    win = r[f - wf.EWMA_SPAN + 1:f + 1, n]
    for hl in wf.EWMA_HALF_LIVES:
        w = 0.5 ** (np.arange(wf.EWMA_SPAN - 1, -1, -1.0) / hl)
        assert got[f"ewma_vol_{hl}"][1, n] == pytest.approx(
            np.sqrt((w * win ** 2).sum() / w.sum()))
    for w in wf.ABS_WINDOWS:
        assert got[f"mean_abs_{w}"][1, n] == pytest.approx(np.abs(win[-w:]).mean())
        assert got[f"max_abs_{w}"][1, n] == pytest.approx(np.abs(win[-w:]).max())
    for w in wf.DOWN_WINDOWS:
        assert got[f"downvol_{w}"][1, n] == pytest.approx(
            np.sqrt((np.minimum(win[-w:], 0.0) ** 2).mean()))
    assert set(got) == set(wf.DESCRIPTORS) and len(wf.DESCRIPTORS) == 11
    assert all(np.isnan(v[0]).all() for v in got.values())    # row 60: no 120-session window
    # row 322: the lost returns (300, 301) sit inside the 120- and 60-session windows only
    assert np.isnan(got["ewma_vol_3"][2, 1]) and np.isnan(got["mean_abs_60"][2, 1])
    assert np.isfinite(got["mean_abs_20"][2, 1]) and np.isnan(got["downvol_120"][2, 1])
    assert np.isfinite(got["ewma_vol_3"][2, 0])
    assert np.isfinite(got["ewma_vol_3"][3]).sum() == N       # row 499: the gap has rolled out


def test_label_window_volatility_covers_exactly_the_label_window():
    rng = np.random.default_rng(13)
    T, N, h, lag = 120, 3, 20, 1
    P = 30.0 * np.exp(np.cumsum(0.03 * rng.normal(size=(T, N)), axis=0))
    rows = np.array([40, 98, 110])
    got = wf.label_window_vol(P, rows, h, lag)
    r = np.diff(np.log(P), axis=0)                             # r[t - 1] is the return into t
    e, x = 40 + lag, 40 + lag + h
    assert got[0] == pytest.approx(np.sqrt((r[e:x] ** 2).mean(axis=0)))
    assert np.isfinite(got[1]).all()                           # exits on the last session
    assert np.isnan(got[2]).all()                              # the window runs off the panel
    P[60:, 2] = np.nan                                         # stops trading: price carried
    carried = wf.label_window_vol(P, np.array([70]), h, lag)
    assert carried[0, 2] == 0.0


def test_inputs_refuse_prices_from_another_calendar():
    panel, _ = _panel(seed=2)
    closes = pd.DataFrame(1.0, index=panel["index"][1:], columns=panel["names"])
    with pytest.raises(ValueError, match="same calendar"):
        wf.price_inputs(panel, closes, closes.notna())


# ---- assembly -------------------------------------------------------------------------------
def test_assembled_rows_are_complete_cases_in_date_order():
    panel, inputs = _panel(seed=4)
    panel["features"]["retained_20d"][10, :70] = np.nan      # a feature B2 does not use
    panel["eligible"][11, :] = False
    data = wf.assemble(panel, inputs, 20)
    n_obs = int(panel["labels"][20]["observable"].sum())
    assert data["n_dates"] == n_obs - 2                      # date 10 falls under 100 names
    assert np.all(np.diff(data["form"]) > 0)
    assert data["R"].shape == (data["start"][-1], len(wf.columns(20)["A"]))
    first = slice(data["start"][0], data["start"][1])
    assert data["event"][first].sum() == int(N_NAMES * wf.EVENT_FRACTION)
    assert data["raw"][first][data["event"][first] == 1].max() <= \
        data["raw"][first][data["event"][first] == 0].min()
    # test dates are V2's holdout dates; development dates end before 2022
    assert data["dates"][data["is_test"]].min() >= pd.Timestamp("2022-07-06")
    assert data["dates"][data["is_dev"]].max() < pd.Timestamp(tpp.HOLDOUT_START)
    assert not (data["is_test"] & data["is_dev"]).any()
    assert all(v.shape == (int(data["is_test"].sum()), len(data["features"]))
               for v in data["q2"].values())


def test_a_complete_case_without_a_descriptor_stops_the_instrument():
    panel, inputs = _panel(seed=4)
    inputs["descriptors"]["max_abs_60"][50, 3] = np.nan
    with pytest.raises(ValueError, match="missing on a complete case"):
        wf.assemble(panel, inputs, 20)
    cov = wf.coverage(panel, inputs)
    assert cov["20"]["missing_descriptor"] == 1 and cov["20"]["missing_label_vol"] == 0
    assert cov["20"]["complete_cases"] == cov["20"]["dates"] * N_NAMES
    panel["eligible"][50, 3] = False                         # not a complete case: no stop
    assert wf.assemble(panel, inputs, 20)["n_dates"] > 0


def test_the_v2_statistic_inside_b2_is_the_committed_one():
    panel, inputs = _panel(seed=14, signal=0.4)
    data = wf.assemble(panel, inputs, 20)
    feats = data["features"]
    j = feats.index(MDD)
    d = tpp.design_of("v2")
    lab = panel["labels"][20]
    pos = tpp.sample_rows(panel, 20, "holdout", "v2")
    want = []
    for i in pos:
        X = np.column_stack([panel["features"][f][i] for f in feats])
        Z = np.column_stack([panel["controls"][c][i] for c in d.controls])
        ic, _ = tpp.semi_partial_rank_ic(X, Z, lab["forward_max_drawdown"][i][:, None])
        want.append(ic[j, 0])
    assert data["q2"]["v2"][:, j] == pytest.approx(np.asarray(want), abs=1e-12)


# ---- Q1 -------------------------------------------------------------------------------------
def test_a_block_is_scored_by_models_that_never_saw_it():
    panel, inputs = _panel(seed=5, signal=0.5)
    data = wf.assemble(panel, inputs, 60)
    base = wf.score_blocks(data, 60, wf.BLOCKS, models=("B2", "A"))
    for b in base["blocks"]:
        assert pd.Timestamp(b["train_last_formation"]) < pd.Timestamp(b["first"])
        first = int(np.searchsorted(data["dates"], pd.Timestamp(b["first"])))
        assert data["exit"][b["train_dates"] - 1] < data["form"][first]
        assert data["exit"][b["train_dates"]] >= data["form"][first]
    # Scramble every label from T3's first formation date on: T1 and T2 scores must not move.
    t3 = int(np.searchsorted(data["dates"], pd.Timestamp("2024-01-01")))
    cut = int(data["start"][t3])
    rng = np.random.default_rng(0)
    scr = dict(data)
    scr["y"], scr["event"] = data["y"].copy(), data["event"].copy()
    scr["y"][cut:] = rng.permutation(scr["y"][cut:])
    scr["event"][cut:] = rng.permutation(scr["event"][cut:])
    moved = wf.score_blocks(scr, 60, wf.BLOCKS, models=("B2", "A"))
    early = np.isin(base["block"], ("T1", "T2"))
    late = base["block"] == "T5"
    for metric in ("ic", "capture", "brier"):
        assert np.array_equal(base["per_date"]["A"][metric][early],
                              moved["per_date"]["A"][metric][early])
    assert not np.array_equal(base["per_date"]["A"]["ic"][late],
                              moved["per_date"]["A"]["ic"][late])


def test_a_planted_incremental_signal_is_measured_and_calibrated(pinned):
    panel, inputs = _panel(seed=6, signal=0.6)
    out = wf.compare(panel, inputs, _holdout_like(panel, inputs), _reference())
    assert out["status"] == "scored"
    for h in ("20", "60"):
        res = out["horizons"][h]
        pair = res["pairs"]["A_vs_B2"]
        assert pair["d_ic"]["mean"] > 0.02
        assert pair["d_capture"]["mean"] > wf.CAPTURE_MIN
        assert all(v is None or v > 0 for v in pair["d_ic_by_block"].values())
        cal = res["models"]["A"]["calibration"]
        assert wf.SLOPE_RANGE[0] <= cal["slope"] <= wf.SLOPE_RANGE[1]
        assert res["gates"]["passed"]
        assert res["models"]["A"]["capture_mean"] > res["models"]["B2"]["capture_mean"] > 0.10
        assert res["models"]["A"]["flagged_mean_drawdown"] < res["mean_drawdown_all"]
        assert out["early"][h]["n_dates"] > 0 and "A_vs_B2" in out["early"][h]["pairs"]
    d = out["decision"]
    assert d["outcome"] == "eligible_calibrated_profile" and d["horizons"] == [20, 60]
    assert out["q1_vs_simulated"] == {}                       # this reference carries no Q1 range
    beside = wf.q1_vs_simulated(out["horizons"], {"20": {"d_ic": [0.0, 0.5], "d_capture": [0.0, 0.001],
                                                         "d_brier": [0.0, 0.0]}})
    assert list(beside) == ["20"] and not beside["20"]["d_ic"]["above_simulated"]
    assert beside["20"]["d_capture"]["above_simulated"]
    # the planted feature acts directly on the drawdown, so it survives the oracle control
    key = f"{MDD}|20|forward_max_drawdown"
    assert out["q2"][key]["more_than_volatility"] and key in d["more_than_volatility"]["20"]
    assert d["kind"] == {"20": "path_information", "60": "path_information"}
    assert not d["family_stops_at_wave_b"]


def test_no_signal_gives_no_model_value(pinned):
    panel, inputs = _panel(seed=7, signal=0.0)
    out = wf.compare(panel, inputs, _holdout_like(panel, inputs), _reference())
    for h in ("20", "60"):
        res = out["horizons"][h]
        assert abs(res["pairs"]["A_vs_B2"]["d_ic"]["mean"]) < 0.01
        assert not res["gates"]["w1"] and not res["gates"]["passed"]
    assert out["decision"]["outcome"] == "no_model_value"
    assert out["decision"]["family_stops_at_wave_b"] and out["decision"]["kind"] == {}


def test_what_a_volatility_descriptor_explains_is_credited_to_the_baseline(pinned):
    """A feature that only proxies short-memory volatility must not look like new information."""
    panel, inputs = _panel(seed=8, descriptor=0.9)
    v = inputs["descriptors"]["ewma_vol_3"]
    panel["features"][MDD] = v + 0.5 * np.random.default_rng(80).normal(size=v.shape)
    out = wf.compare(panel, inputs, _holdout_like(panel, inputs), _reference())
    res = out["horizons"]["20"]
    assert res["pairs"]["A_vs_B1"]["d_ic"]["mean"] > 0.02          # looks useful against B1
    assert res["pairs"]["B2_vs_B1"]["d_ic"]["mean"] > 0.02         # the descriptor explains it
    assert res["pairs"]["A_vs_B2"]["d_ic"]["mean"] < 0.25 * res["pairs"]["A_vs_B1"]["d_ic"]["mean"]
    assert not res["gates"]["w3"]


# ---- Q2 -------------------------------------------------------------------------------------
def test_a_feature_that_only_tracks_the_label_windows_volatility_carries_nothing_more(pinned):
    panel, inputs = _panel(seed=9, window_vol=1.0)
    fv = inputs["label_vol"][20]
    panel["features"][MDD] = fv + 0.7 * np.random.default_rng(90).normal(size=fv.shape)
    out = wf.compare(panel, inputs, _holdout_like(panel, inputs), _reference())
    st = out["q2"][f"{MDD}|20|forward_max_drawdown"]
    assert abs(st["v2"]["mean"]) > 0.15                       # V2's gates would pass it
    assert abs(st["controls_sq"]["mean"]) > 0.15              # and so would squared controls
    for k in ("oracle", "descriptors_oracle"):                # nothing once that is controlled
        assert abs(st[k]["mean"]) < 0.03 * abs(st["v2"]["mean"]) and abs(st[k]["t_hac"]) < 2.5
    assert not st["more_than_volatility"]


def test_the_window_volatility_control_is_a_rank_and_twenty_equal_bins():
    fv = np.random.default_rng(21).lognormal(size=1000)
    C = wf._window_vol_columns(fv)
    assert C.shape == (1000, 1 + wf.WINDOW_VOL_BINS - 1) and wf.WINDOW_VOL_BINS == 20
    assert C[:, 0].mean() == pytest.approx(0.0) and C[:, 0].std() == pytest.approx(1.0)
    assert np.array_equal(C[:, 1:].sum(axis=0), np.full(19, 50.0))   # 50 names per bin
    assert np.array_equal(np.argsort(fv)[:50], np.flatnonzero(C[:, 1:].sum(axis=1) == 0)[
        np.argsort(fv[C[:, 1:].sum(axis=1) == 0])])                   # the lowest bin is implicit
    # the residual is orthogonal to the control; ranked again, it is not
    A = np.column_stack([np.ones(1000), C])
    x = tpp._rank(fv + 0.5 * np.random.default_rng(22).normal(size=1000))
    y = tpp._rank(-fv)
    resid = x - A @ np.linalg.lstsq(A, x, rcond=None)[0]
    assert np.abs(A.T @ resid).max() < 1e-6
    clean = wf._residual_ic(x[:, None], A, y)[0]
    again = wf._residual_ic(x[:, None], A, y, rerank=True)[0]
    assert abs(clean) < 0.02 and abs(again) > 2 * abs(clean)


def _q2(mean, p, sign=1):
    return {"oracle": {"mean": mean, "p_hac": p}, "dev_sign": sign}


def test_more_than_volatility_needs_every_gate_and_the_simulated_range():
    V = tpp._judges()
    keys = wf.confirmed_keys()
    signs = {k: 1 for k in keys}
    signs[keys[3]] = -1
    q2 = {k: _q2(0.0001, 0.9) for k in keys}
    q2[keys[0]] = _q2(0.020, 0.0002)             # clear, above the range
    q2[keys[1]] = _q2(0.020, 0.0002)             # clear, but inside the range
    q2[keys[2]] = _q2(0.004, 0.0002)             # under the floor
    q2[keys[3]] = _q2(-0.020, 0.0002)            # negative development sign, and negative
    q2[keys[4]] = _q2(-0.020, 0.0002)            # wrong sign
    q2[keys[5]] = _q2(0.020, 0.2)                # not significant
    ranges = {k: {"oracle": [-0.002, 0.003]} for k in keys}
    ranges[keys[1]] = {"oracle": [0.001, 0.025]}
    ranges[keys[3]] = {"oracle": [-0.010, 0.030]}
    wf.apply_q2_gates(V, q2, signs, ranges)
    assert q2[keys[0]]["more_than_volatility"] and all(q2[keys[0]]["gates"].values())
    assert q2[keys[1]]["gates"] == {"k1_same_sign": True, "k2_one_sided_p": True,
                                    "k3_bh_fdr": True, "k4_ic_floor": True,
                                    "k5_above_simulated": False}
    assert not q2[keys[2]]["gates"]["k4_ic_floor"]
    # signed like development: -0.020 is 0.020, the range tops out at 0.010
    assert q2[keys[3]]["more_than_volatility"]
    assert not q2[keys[4]]["gates"]["k1_same_sign"] and q2[keys[4]]["p_one_sided"] > 0.99
    assert not q2[keys[5]]["gates"]["k2_one_sided_p"]
    assert sum(st["more_than_volatility"] for st in q2.values()) == 2


def test_simulated_ranges_span_the_run_means():
    ref = {"runs": [{"q2": {"a": {"oracle": 0.01, "v2": 0.03}}},
                    {"q2": {"a": {"oracle": -0.02, "v2": 0.05}}},
                    {"q2": {"a": {"oracle": 0.00, "v2": 0.04}}}]}
    assert wf.simulated_ranges(ref) == {"a": {"oracle": [-0.02, 0.01], "v2": [0.03, 0.05]}}


# ---- gates and decision ---------------------------------------------------------------------
def _summary(d_ic, p, blocks, d_cap, slope, brier_a, brier_b):
    return {"pairs": {"A_vs_B2": {"d_ic": {"mean": d_ic, "p_one_sided": p},
                                  "d_ic_by_block": dict(zip("abcde", blocks)),
                                  "d_capture": {"mean": d_cap}}},
            "models": {"A": {"calibration": {"slope": slope}, "brier_mean": brier_a},
                       "B2": {"brier_mean": brier_b}}}


def test_gates_and_decision_follow_the_preregistered_rule():
    ok = _summary(0.01, 0.01, [0.01, 0.02, 0.01, -0.01, 0.01], 0.012, 1.0, 0.080, 0.081)
    g = wf.apply_gates(ok)
    assert g == {"w1": True, "w2": True, "w3": True, "w4": True, "blocks_positive": 4,
                 "passed": True}
    small = wf.apply_gates(_summary(0.004, 0.02, [0.01] * 5, 0.004, 1.0, 0.080, 0.081))
    assert small["w1"] and small["w2"] and not small["w3"] and not small["passed"]
    weak = wf.apply_gates(_summary(0.004, 0.20, [0.01] * 5, 0.02, 1.0, 0.080, 0.081))
    assert not weak["w1"] and not weak["passed"]
    patchy = wf.apply_gates(_summary(0.01, 0.01, [0.03, 0.03, 0.03, -0.01, -0.01], 0.02, 1.0,
                                     0.080, 0.081))
    assert patchy["w1"] and not patchy["w2"]
    off = wf.apply_gates(_summary(0.01, 0.01, [0.01] * 5, 0.02, 0.7, 0.080, 0.081))
    assert not off["w4"]
    worse = wf.apply_gates(_summary(0.01, 0.01, [0.01] * 5, 0.02, 1.0, 0.082, 0.081))
    assert not worse["w4"]
    neg = wf.apply_gates(_summary(-0.01, 0.99, [-0.01] * 5, -0.01, 1.0, 0.080, 0.081))
    assert not neg["w1"] and not neg["w2"] and not neg["w3"]
    assert not wf.apply_gates({"pairs": {}, "models": {}})["passed"]

    key20 = f"{MDD}|20|forward_max_drawdown"
    q2 = {key20: {"more_than_volatility": True},
          f"{MDD}|60|forward_max_drawdown": {"more_than_volatility": False}}
    both = wf.decide({"20": {"gates": g}, "60": {"gates": g}}, q2)
    assert both["outcome"] == "eligible_calibrated_profile" and both["horizons"] == [20, 60]
    assert both["kind"] == {"20": "path_information", "60": "volatility_type"}
    assert both["more_than_volatility"]["20"] == [key20]
    one = wf.decide({"20": {"gates": g}, "60": {"gates": small}}, {})
    assert one["horizons"] == [20] and one["kind"] == {"20": "volatility_type"}
    assert both["advances"] and not both["family_stops_at_wave_b"]
    immaterial = wf.decide({"20": {"gates": small}, "60": {"gates": weak}}, q2)
    assert immaterial["outcome"] == "detectable_immaterial" and immaterial["kind"] == {}
    assert immaterial["family_stops_at_wave_b"] and not immaterial["advances"]
    uncal = wf.decide({"20": {"gates": off}, "60": {"gates": small}}, q2)
    assert uncal["outcome"] == "material_uncalibrated" and uncal["horizons"] == []
    assert not uncal["advances"] and not uncal["family_stops_at_wave_b"]
    assert wf.decide({"20": {"gates": weak}, "60": {"gates": patchy}}, q2)["outcome"] == \
        "no_model_value"
    # The 5-session horizon never gates.
    assert wf.decide({"5": {"gates": g}, "20": {"gates": weak}, "60": {"gates": weak}}, q2)[
        "outcome"] == "no_model_value"


# ---- guards ---------------------------------------------------------------------------------
def test_nothing_is_scored_without_the_pinned_preregistration(monkeypatch):
    panel, inputs = _panel(seed=9)
    monkeypatch.setattr(wf, "PREREG_SHA256", None)
    with pytest.raises(tpp.PreregDrift):
        wf.compare(panel, inputs, {"tests": {}}, _reference())
    with pytest.raises(tpp.PreregDrift):
        wf.build_reference()
    monkeypatch.setattr(wf, "PREREG_SHA256", "0" * 64)
    with pytest.raises(tpp.PreregDrift):
        wf.compare(panel, inputs, {"tests": {}}, _reference())
    with pytest.raises(tpp.PreregDrift):
        wf.run()


def test_real_data_is_not_scored_without_the_pinned_reference(pinned, monkeypatch, tmp_path):
    monkeypatch.setattr(wf, "REFERENCE_SHA256", None)
    with pytest.raises(tpp.PreregDrift, match="no pinned simulated reference"):
        wf.run()
    ref = tmp_path / "ref.json"
    ref.write_text(json.dumps({"prereg_sha256": wf.PREREG_SHA256, "design": {"design": "other"}}))
    monkeypatch.setattr(wf, "REFERENCE_FILE", str(ref))
    monkeypatch.setattr(wf, "REFERENCE_SHA256", "0" * 64)
    with pytest.raises(tpp.PreregDrift, match="hashes to"):
        wf.pinned_reference()
    monkeypatch.setattr(wf, "REFERENCE_SHA256", wf._sha256(str(ref)))
    with pytest.raises(tpp.PreregDrift, match="different design"):
        wf.pinned_reference()
    ref.write_text(json.dumps({"prereg_sha256": wf.PREREG_SHA256, "design": wf.frozen_design()}))
    monkeypatch.setattr(wf, "REFERENCE_SHA256", wf._sha256(str(ref)))
    assert wf.pinned_reference()["design"] == wf.frozen_design()


def test_b2_stops_if_v2s_holdout_statistic_does_not_reproduce(pinned):
    panel, inputs = _panel(seed=10)
    held = _holdout_like(panel, inputs)
    key = wf.confirmed_keys()[0]
    held["tests"][key]["mean"] += 1e-6
    with pytest.raises(tpp.PreregDrift, match="does not reproduce"):
        wf.compare(panel, inputs, held, _reference())
    held = _holdout_like(panel, inputs)
    held["tests"][key]["n_dates"] += 1
    with pytest.raises(tpp.PreregDrift, match="does not reproduce"):
        wf.compare(panel, inputs, held, _reference())
    held = _holdout_like(panel, inputs)
    del held["tests"][key]
    with pytest.raises(tpp.PreregDrift, match="not the 29"):
        wf.compare(panel, inputs, held, _reference())


def test_a_panel_off_the_v2_design_is_refused(pinned):
    panel, inputs = _panel(seed=10)
    held = _holdout_like(panel, inputs)
    panel["observed_mask"] = False
    with pytest.raises(ValueError):
        wf.compare(panel, inputs, held, _reference())


def test_the_run_refuses_any_other_panel_and_any_second_run(pinned, monkeypatch, tmp_path):
    from research import trend_persistence_substrate as substrate
    synthetic, _ = _panel(seed=11)
    monkeypatch.setattr(wf, "pinned_reference", lambda: _reference())
    monkeypatch.setattr(substrate, "load_repaired_panel",
                        lambda *a, **k: (None, None, None, None, {"store": {"names": []}}))
    monkeypatch.setattr(tpp, "build_panel", lambda *a, **k: synthetic)
    with pytest.raises(tpp.PreregDrift, match="not the one V2"):
        wf.run()
    done = tmp_path / "b2.json"
    done.write_text("{}")
    with pytest.raises(tpp.HoldoutLocked, match="not run again"):
        wf.run(out_path=str(done))


# ---- simulated reference --------------------------------------------------------------------
def test_a_reference_run_is_reproducible_and_reads_no_prices():
    kwargs = {"n_names": 130, "n_sessions": 3000, "start": "2014-06-02"}
    a = wf.reference_run("clustered_leverage", 3, **kwargs)
    b = wf.reference_run("clustered_leverage", 3, **kwargs)
    assert a == b and a["spec"] == "clustered_leverage" and a["seed"] == 3
    assert sorted(a["q1"]) == ["20", "5", "60"]
    assert sorted(a["q2"]) == sorted(wf.confirmed_keys())
    assert all(set(st) == set(wf.Q2_SERIES) for st in a["q2"].values())
    assert set(a["q1"]["20"]["models"]) == set(wf.SIM_MODELS)
    assert a["q1"]["20"]["models"]["B2"]["ic"] > 0.3          # volatility ranks drawdown
    with pytest.raises(ValueError, match="unknown specification"):
        wf.reference_run("real", 3)
    last = pd.bdate_range(wf.SIM_START, periods=wf.SIM_SESSIONS)[-1]
    assert last >= pd.Timestamp("2026-06-01")                 # reaches the last test block


# ---- the committed pins -------------------------------------------------------------------------
def test_the_pins_match_the_committed_files_and_the_reference_says_what_the_prereg_says():
    assert wf.PREREG_SHA256 == wf.prereg_sha256()
    ref = wf.pinned_reference()
    assert {(r["spec"], r["seed"]) for r in ref["runs"]} == {
        (s, k) for s in wf.SIM_SPECS for k in wf.SIM_SEEDS} and len(ref["runs"]) == 10
    assert sorted(ref["q2_ranges"]) == sorted(wf.confirmed_keys())
    gated = [str(h) for h in wf.GATE_HORIZONS]
    # §7: W3 passes nowhere in the simulated market; W1 and W2 pass at a gated horizon in 8 runs
    assert not any(r["q1"][h]["gates"]["w3"] for r in ref["runs"] for h in r["q1"])
    assert sum(any(r["q1"][h]["gates"]["w1"] and r["q1"][h]["gates"]["w2"] for h in gated)
               for r in ref["runs"]) == 8
    for h in gated:
        lo, hi = ref["q1_ranges"][h]["d_ic"]
        assert 0.00004 <= lo and hi <= 0.0006
        lo, hi = ref["q1_ranges"][h]["d_capture"]
        assert -0.0010 - 1e-4 <= lo and hi <= 0.0014 + 1e-4
    # §12: the volatility-controlled statistic is near zero in every simulated test
    lows = [v[wf.Q2_GATED][0] for v in ref["q2_ranges"].values()]
    highs = [v[wf.Q2_GATED][1] for v in ref["q2_ranges"].values()]
    assert -0.0065 < min(lows) and max(highs) < 0.0115
