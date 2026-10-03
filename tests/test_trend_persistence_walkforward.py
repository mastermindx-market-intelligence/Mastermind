from __future__ import annotations

import json
import math
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


def _holdout_like(panel, inputs, flip=()):
    """A V2-holdout-shaped result that this panel reproduces, so ``compare`` can run on it.

    The development sign is the sign the panel shows, except for the keys in ``flip``.
    """
    tests = {}
    for h in wf.HORIZONS:
        for key, st in wf.summarise_q2(wf.assemble(panel, inputs, h), h, panel["step"]).items():
            sign = 1 if st["v2"]["mean"] >= 0 else -1
            tests[key] = {"confirmed_holdout": True, "mean": st["v2"]["mean"],
                          "n_dates": st["v2"]["n_dates"],
                          "dev_sign": -sign if key in flip else sign}
    return {"tests": tests}


def _k5(mean: float = 0.0, sd: float = 0.002, threshold: float = 3.0, **spec_means):
    """A simulated K5 reference: per specification, every test's mean, spread and threshold."""
    keys = wf.confirmed_keys()
    return {spec: {"n_runs": 100, "threshold": threshold, "sd": {k: sd for k in keys},
                   "signed_mean": {k: spec_means.get(spec, {}).get(k, mean) for k in keys},
                   "false_label": {}}
            for spec in wf.SIM_SPECS}


def _reference(**kwargs):
    return {"k5": _k5(**kwargs), "q1_ranges": {}, "code_sha256": wf.code_sha256()}


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
    assert out["q2"][key]["beyond_simulated_volatility"]
    assert key in d["beyond_simulated_volatility"]["20"]
    assert d["kind"] == {"20": "beyond_simulated_volatility", "60": "beyond_simulated_volatility"}
    assert not d["family_stops_at_wave_b"]
    assert set(out["q2"][key]["simulated"]) == set(wf.SIM_SPECS)
    json.dumps(out, default=str)                              # the result is writable as it is


def test_a_leftover_against_the_development_sign_is_not_credited(pinned):
    panel, inputs = _panel(seed=6, signal=0.6)
    key = f"{MDD}|20|forward_max_drawdown"
    out = wf.compare(panel, inputs, _holdout_like(panel, inputs, flip=(key,)), _reference())
    st = out["q2"][key]
    assert st["dev_sign"] * st["oracle"]["mean"] < 0 and st["p_signed"] > 0.99
    assert not st["gates"]["k1_same_sign"] and not st["gates"]["k2_one_sided_p"]
    assert not st["gates"]["k5_above_simulated"] and not st["beyond_simulated_volatility"]
    assert key not in out["decision"]["beyond_simulated_volatility"]["20"]


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
        assert abs(st[k]["mean"]) < 0.03 * abs(st["v2"]["mean"]) and abs(st[k]["t"]) < 2.5
    assert not st["beyond_simulated_volatility"]


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


def _q2(mean, p_above_zero):
    return {"oracle": {"mean": mean, "p_one_sided": p_above_zero}}


def test_beyond_simulated_volatility_needs_every_gate_against_every_specification():
    keys = wf.confirmed_keys()
    signs = {k: 1 for k in keys}
    signs[keys[3]] = -1
    q2 = {k: _q2(0.0001, 0.45) for k in keys}
    q2[keys[0]] = _q2(0.020, 0.0002)             # clear of both simulated markets
    q2[keys[1]] = _q2(0.020, 0.0002)             # clear of one simulated market only
    q2[keys[2]] = _q2(0.004, 0.0002)             # under the floor
    q2[keys[3]] = _q2(-0.020, 0.9998)            # negative development sign, and negative
    q2[keys[4]] = _q2(-0.020, 0.9998)            # wrong sign
    q2[keys[5]] = _q2(0.020, 0.2)                # not significant
    q2[keys[6]] = _q2(0.0055, 0.0002)            # every gate but the simulated one
    k5 = _k5(**{wf.SIM_SPECS[1]: {keys[1]: 0.016}})
    wf.apply_q2_gates(q2, signs, k5)
    assert q2[keys[0]]["beyond_simulated_volatility"] and all(q2[keys[0]]["gates"].values())
    assert q2[keys[0]]["simulated"][wf.SIM_SPECS[0]]["z"] == pytest.approx(10.0)
    assert q2[keys[1]]["gates"] == {"k1_same_sign": True, "k2_one_sided_p": True,
                                    "k3_bh_fdr": True, "k4_ic_floor": True,
                                    "k5_above_simulated": False}
    assert q2[keys[1]]["simulated"][wf.SIM_SPECS[0]]["z"] > 3 > \
        q2[keys[1]]["simulated"][wf.SIM_SPECS[1]]["z"]
    assert not q2[keys[2]]["gates"]["k4_ic_floor"]
    # signed like development: -0.020 is 0.020, and its p is the lower tail
    assert q2[keys[3]]["beyond_simulated_volatility"]
    assert q2[keys[3]]["p_signed"] == pytest.approx(0.0002)
    assert not q2[keys[4]]["gates"]["k1_same_sign"] and q2[keys[4]]["p_signed"] > 0.99
    assert not q2[keys[5]]["gates"]["k2_one_sided_p"]
    g = q2[keys[6]]["gates"]                                  # z = 2.75, under the threshold
    assert g["k1_same_sign"] and g["k2_one_sided_p"] and g["k3_bh_fdr"] and g["k4_ic_floor"]
    assert not g["k5_above_simulated"]
    assert sum(st["beyond_simulated_volatility"] for st in q2.values()) == 2
    # with no simulated reference nothing can be called beyond it
    bare = {k: _q2(0.020, 0.0002) for k in keys}
    wf.apply_q2_gates(bare, {k: 1 for k in keys}, {})
    assert not any(st["beyond_simulated_volatility"] for st in bare.values())


def test_the_simulated_spread_is_taken_to_the_series_own_number_of_dates():
    keys = wf.confirmed_keys()
    signs = {k: 1 for k in keys}
    k5 = _k5()
    for ref in k5.values():
        ref["n_dates"] = {"5": 200, "20": 200, "60": 200}
    same = {k: {"oracle": {"mean": 0.020, "p_one_sided": 0.0002, "n_dates": 200}} for k in keys}
    half = {k: {"oracle": {"mean": 0.020, "p_one_sided": 0.0002, "n_dates": 100}} for k in keys}
    wf.apply_q2_gates(same, signs, k5)
    wf.apply_q2_gates(half, signs, k5)
    a, b = same[keys[0]]["simulated"][wf.SIM_SPECS[0]], half[keys[0]]["simulated"][wf.SIM_SPECS[0]]
    assert a["sd_scale"] == 1.0 and b["sd_scale"] == pytest.approx(math.sqrt(2.0))
    assert b["simulated_sd"] == pytest.approx(a["simulated_sd"] * math.sqrt(2.0))
    assert b["z"] == pytest.approx(a["z"] / math.sqrt(2.0)) and b["simulated_dates"] == 200


def _fake_runs(n: int = 60, seed: int = 0, shift: float = 0.0):
    rng = np.random.default_rng(seed)
    keys = wf.confirmed_keys()
    runs = []
    for i, spec in enumerate(wf.SIM_SPECS):
        for k in range(n):
            x = rng.normal(0.001 * i + shift, 0.002, size=len(keys))
            runs.append({"spec": spec, "seed": k, "q2_dates": {"5": 205, "20": 202, "60": 194},
                         "q2": {key: {wf.Q2_GATED: float(v)} for key, v in zip(keys, x)},
                         "q2_p": {key: 0.5 * math.erfc(v / 0.002 / math.sqrt(2.0))
                                  for key, v in zip(keys, x)}})
    return runs


def test_the_simulated_threshold_is_the_largest_leave_one_out_excess_few_runs_reach():
    keys = wf.confirmed_keys()
    signs = {k: 1 for k in keys}
    runs = _fake_runs()
    ref = wf.k5_reference(runs, signs)
    assert set(ref) == set(wf.SIM_SPECS)
    spec = wf.SIM_SPECS[0]
    x = np.array([[r["q2"][k][wf.Q2_GATED] for k in keys] for r in runs if r["spec"] == spec])
    largest = []
    for i in range(len(x)):
        rest = np.delete(x, i, axis=0)
        largest.append(((x[i] - rest.mean(axis=0)) / rest.std(axis=0, ddof=1)).max())
    assert ref[spec]["largest_excess"] == pytest.approx(largest, abs=1e-9)
    assert ref[spec]["threshold"] == pytest.approx(np.sort(largest)[56])     # 57th of 60
    assert ref[spec]["signed_mean"][keys[0]] == pytest.approx(x[:, 0].mean())
    assert ref[spec]["sd"][keys[0]] == pytest.approx(x[:, 0].std(ddof=1))
    for st in ref.values():
        fl = st["false_label"]
        assert fl["k5_any_test"] <= wf.K5_ALPHA                # no more than 3 of 60 runs
        assert fl["all_gates_gated_horizons"] <= fl["all_gates_any_test"] <= fl["k5_any_test"]
        assert fl["k5_gated_horizons"] <= fl["k5_any_test"]
    # a negative development sign flips the simulated value it is compared with
    flipped = wf.k5_reference(runs, {**signs, keys[0]: -1})
    assert flipped[spec]["signed_mean"][keys[0]] == pytest.approx(-x[:, 0].mean())
    with pytest.raises(ValueError, match="cannot set a threshold"):
        wf.k5_reference(runs[:10], signs)
    assert ref[spec]["n_dates"] == {"5": 205, "20": 202, "60": 194}
    with pytest.raises(ValueError, match="differ in their test dates"):
        wf.k5_reference([{**runs[0], "q2_dates": {"5": 204, "20": 202, "60": 194}}] + runs[1:],
                        signs)
    # fresh runs from the same two markets are labelled about as rarely; shifted ones are not
    same = wf.k5_check(_fake_runs(n=200, seed=1), signs, ref)
    far = wf.k5_check(_fake_runs(n=20, seed=2, shift=0.02), signs, ref)
    for spec in wf.SIM_SPECS:
        assert same[spec]["n_runs"] == 200 and same[spec]["k5_any_test"] < 0.15
        assert same[spec]["all_gates_gated_horizons"] <= same[spec]["all_gates_any_test"] \
            <= same[spec]["k5_any_test"]
        assert far[spec]["k5_any_test"] == far[spec]["all_gates_any_test"] == 1.0
        assert len(far[spec]["runs"][0]["beyond"]) == 29
        assert set(far[spec]["runs"][0]["largest_excess"]) == set(wf.SIM_SPECS)
    assert wf.k5_check([], signs, ref) == {}


# ---- the test of a mean ---------------------------------------------------------------------
def test_student_t_tail_matches_tabulated_critical_values():
    assert wf.student_t_sf(2.364624, 7) == pytest.approx(0.025, abs=1e-7)
    assert wf.student_t_sf(2.160369, 13) == pytest.approx(0.025, abs=1e-7)
    assert wf.student_t_sf(2.776445, 4) == pytest.approx(0.025, abs=1e-7)
    assert wf.student_t_sf(1.894579, 7) == pytest.approx(0.05, abs=1e-7)
    assert wf.student_t_sf(0.0, 9) == 0.5
    assert wf.student_t_sf(-1.3, 4) == pytest.approx(1 - wf.student_t_sf(1.3, 4))
    assert 0 < wf.student_t_sf(40.0, 7) < 1e-8


def test_the_cosine_terms_follow_the_overlap_of_the_labels():
    # the real test-date counts: 13, 13 and 7 terms
    assert [wf.ewc_df(n, h, 5) for n, h in ((197, 5), (194, 20), (186, 60))] == [13, 13, 7]
    assert wf.ewc_df(30, 60, 5) == wf.EWC_MIN_DF == 4
    assert wf.ewc_df(2000, 5, 5) == int(0.4 * 2000 ** (2 / 3))


def test_the_test_of_a_mean_holds_its_size_where_v2s_rule_does_not():
    """Per-date series with the serial dependence 60-session labels induce at a 5-session step."""
    rng = np.random.default_rng(5)
    n, h, step, draws = 186, 60, 5, 3000
    q = h // step
    new = old = 0
    for _ in range(draws):
        x = np.convolve(rng.standard_normal(n + q - 1), np.ones(q), "valid")
        r = wf._rejects(x, h, step)
        new += r["at_0.025"]
        old += r["v2_rule_at_0.025"]
    assert 0.015 < new / draws < 0.037                        # stated 0.025
    assert old / draws > 0.055                                # V2's rule: more than twice that
    # and it finds a mean that is there
    x = 1.5 + np.convolve(rng.standard_normal(n + q - 1), np.ones(q), "valid") / math.sqrt(q)
    t, df, p = wf.ewc_test(x, h, step)
    assert df == 7 and t > 3 and p < 0.01
    assert wf.ewc_test(np.zeros(50), 20, 5) == (None, 5, None)


def test_the_reported_v2_statistic_is_the_engines_and_the_series_summary_is_unrounded():
    rng = np.random.default_rng(6)
    s = 0.01 + 0.05 * rng.standard_normal(190)
    s[7] = np.nan
    out = wf._series(s, 20, 5)
    clean = s[np.isfinite(s)]
    V = tpp._judges()
    assert out["n_dates"] == 189 and out["mean"] == float(clean.mean()) and out["df"] == 13
    assert out["t_v2_rule"] == pytest.approx(V.newey_west_tstat(pd.Series(clean), lags=8)["t"],
                                             abs=6e-4)
    assert out["p_one_sided"] == wf.student_t_sf(out["t"], 13)
    assert wf._series(s[:6], 20, 5)["p_one_sided"] is None


def test_false_discovery_control_is_the_step_up_rule():
    p = {"a": 0.001, "b": 0.011, "c": 0.02, "d": 0.03, "e": 0.9}
    assert wf._bh_reject(p, 0.05) == {"a", "b", "c", "d"}     # 0.03 <= 0.05 * 4 / 5
    assert wf._bh_reject(p, 0.01) == {"a"}
    assert wf._bh_reject({"a": 0.2, "b": 0.3}, 0.10) == set()
    V = tpp._judges()
    rng = np.random.default_rng(8)
    many = {f"k{i}": float(v) for i, v in enumerate(rng.random(40) ** 3)}
    got = V.benjamini_hochberg(many, alpha=0.10)
    assert wf._bh_reject(many, 0.10) == {k for k, v in got.items() if v["reject"]}


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
    q2 = {key20: {"beyond_simulated_volatility": True},
          f"{MDD}|60|forward_max_drawdown": {"beyond_simulated_volatility": False}}
    both = wf.decide({"20": {"gates": g}, "60": {"gates": g}}, q2)
    assert both["outcome"] == "eligible_calibrated_profile" and both["horizons"] == [20, 60]
    assert both["kind"] == {"20": "beyond_simulated_volatility", "60": "volatility_type"}
    assert both["beyond_simulated_volatility"]["20"] == [key20]
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

    def write(**body):
        ref.write_text(json.dumps(body))
        monkeypatch.setattr(wf, "REFERENCE_SHA256", wf._sha256(str(ref)))

    write(prereg_sha256=wf.PREREG_SHA256, design={"design": "other"})
    monkeypatch.setattr(wf, "REFERENCE_FILE", str(ref))
    monkeypatch.setattr(wf, "REFERENCE_SHA256", "0" * 64)
    with pytest.raises(tpp.PreregDrift, match="hashes to"):
        wf.pinned_reference()
    write(prereg_sha256=wf.PREREG_SHA256, design={"design": "other"})
    with pytest.raises(tpp.PreregDrift, match="different design"):
        wf.pinned_reference()
    write(prereg_sha256=wf.PREREG_SHA256, design=wf.frozen_design(), code_sha256="0" * 64)
    with pytest.raises(tpp.PreregDrift, match="different code"):
        wf.pinned_reference()
    write(prereg_sha256=wf.PREREG_SHA256, design=wf.frozen_design(),
          code_sha256=wf.code_sha256())
    assert wf.pinned_reference()["design"] == wf.frozen_design()


def test_the_code_hash_covers_the_instrument_and_ignores_only_its_two_pins(monkeypatch, tmp_path):
    here = os.path.dirname(wf.__file__)
    for name in wf.CODE_FILES:
        with open(os.path.join(here, name), "rb") as fh:
            (tmp_path / name).write_bytes(fh.read())
    assert len(wf._PIN_LINE.findall((tmp_path / wf.CODE_FILES[0]).read_bytes())) == 2
    before = wf.code_sha256()
    monkeypatch.setattr(wf, "_HERE", str(tmp_path))
    assert wf.code_sha256() == before and len(before) == 64
    main = tmp_path / wf.CODE_FILES[0]
    body = main.read_text()
    main.write_text(wf._PIN_LINE.sub(rb'\1: str | None = "f00d"', body.encode()).decode())
    assert wf.code_sha256() == before                         # a pin changed: same code
    main.write_text(body.replace("CAPTURE_MIN = 0.010", "CAPTURE_MIN = 0.001"))
    assert body != main.read_text() and wf.code_sha256() != before   # a threshold changed
    main.write_text(body)
    other = tmp_path / wf.CODE_FILES[1]
    other.write_text(other.read_text() + "\n# edited\n")
    assert wf.code_sha256() != before                         # the panel module changed


def test_the_holdout_result_b2_reads_is_the_pinned_file(monkeypatch, tmp_path):
    held = wf.pinned_holdout_result()
    assert len(wf.dev_signs(held)) == 29 and set(wf.dev_signs(held).values()) <= {1, -1}
    other = tmp_path / "held.json"
    other.write_text(json.dumps(held))
    monkeypatch.setattr(wf, "HOLDOUT_RESULT_FILE", str(other))
    with pytest.raises(tpp.PreregDrift, match="hashes to"):
        wf.pinned_holdout_result()


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


@pytest.fixture
def staged(pinned, monkeypatch, tmp_path):
    """``run`` wired to a synthetic panel and to result and attempt files in a scratch folder."""
    from research import trend_persistence_substrate as substrate
    panel, inputs = _panel(seed=11, signal=0.6)
    state = {"clean": True, "panel": panel}
    monkeypatch.setattr(wf, "pinned_reference", lambda: _reference())
    monkeypatch.setattr(wf, "pinned_holdout_result", lambda: _holdout_like(panel, inputs))
    monkeypatch.setattr(wf, "_git_state", lambda: {"head": "a" * 40, "clean": state["clean"]})
    monkeypatch.setattr(substrate, "load_repaired_panel",
                        lambda *a, **k: (None, None, None, None, {"store": {"names": []}}))
    monkeypatch.setattr(tpp, "build_panel", lambda *a, **k: state["panel"])
    monkeypatch.setattr(wf, "price_inputs", lambda *a, **k: inputs)
    monkeypatch.setattr(wf, "RESULT_FILE", str(tmp_path / "result.json"))
    monkeypatch.setattr(wf, "ATTEMPT_FILE", str(tmp_path / "attempt.json"))
    state["result"], state["attempt"] = tmp_path / "result.json", tmp_path / "attempt.json"
    return state


def test_the_run_refuses_an_uncommitted_tree_and_any_other_panel(staged):
    staged["clean"] = False
    with pytest.raises(tpp.PreregDrift, match="uncommitted"):
        wf.run()
    assert not staged["attempt"].exists()                     # nothing was read: no attempt
    staged["clean"] = True
    with pytest.raises(tpp.PreregDrift, match="not the one V2"):
        wf.run()
    assert not staged["result"].exists()
    attempts = json.loads(staged["attempt"].read_text())["attempts"]
    assert len(attempts) == 1 and attempts[0]["retry_reason"] is None
    assert attempts[0]["git_head"] == "a" * 40 and attempts[0]["code_sha256"] == wf.code_sha256()


def test_an_attempt_that_left_no_result_needs_a_stated_reason(staged):
    with pytest.raises(tpp.PreregDrift, match="not the one V2"):
        wf.run()
    for reason in (None, "", "   "):
        with pytest.raises(tpp.HoldoutLocked, match="needs a stated reason"):
            wf.run(retry_reason=reason)
    with pytest.raises(tpp.PreregDrift, match="not the one V2"):
        wf.run(retry_reason="the loader pointed at the wrong store")
    attempts = json.loads(staged["attempt"].read_text())["attempts"]
    assert [a["retry_reason"] for a in attempts] == [None, "the loader pointed at the wrong store"]


def test_the_run_writes_one_result_and_is_never_made_again(staged, monkeypatch):
    monkeypatch.setattr(wf, "V2_PANEL_SHA256", "synthetic")
    out = wf.run()
    assert out["status"] == "scored" and out["decision"]["outcome"] == "eligible_calibrated_profile"
    written = json.loads(staged["result"].read_text())
    assert written["decision"] == out["decision"] and written["git_head"] == "a" * 40
    assert written["code_sha256"] == wf.code_sha256() and len(written["attempts"]) == 1
    assert written["holdout_result_sha256"] == wf.HOLDOUT_RESULT_SHA256
    assert not os.path.exists(str(staged["result"]) + ".tmp")
    for kwargs in ({}, {"retry_reason": "again"}):
        with pytest.raises(tpp.HoldoutLocked, match="not run again"):
            wf.run(**kwargs)
    assert len(json.loads(staged["attempt"].read_text())["attempts"]) == 1


def test_the_real_run_takes_no_output_path(capsys):
    with pytest.raises(SystemExit):
        wf.main(["--out", "elsewhere.json"])
    assert "fixed path" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        wf.main(["--reference"])
    assert "--out is required" in capsys.readouterr().err
    assert os.path.dirname(wf.RESULT_FILE) == os.path.dirname(wf.ATTEMPT_FILE) == "data"


# ---- simulated reference --------------------------------------------------------------------
def test_a_reference_run_is_reproducible_and_reads_no_prices():
    kwargs = {"n_names": 130, "n_sessions": 3000, "start": "2014-06-02"}
    a = wf.reference_run("clustered_leverage", 3, **kwargs)
    b = wf.reference_run("clustered_leverage", 3, **kwargs)
    assert a == b and a["spec"] == "clustered_leverage" and a["seed"] == 3
    assert sorted(a["q1"]) == ["20", "5", "60"]
    assert sorted(a["q2"]) == sorted(a["q2_p"]) == sorted(wf.confirmed_keys())
    assert all(set(st) == set(wf.Q2_SERIES) for st in a["q2"].values())
    assert all(0.0 < p < 1.0 for p in a["q2_p"].values())
    assert set(a["q1"]["20"]["models"]) == set(wf.SIM_MODELS)
    assert a["q1"]["20"]["models"]["B2"]["ic"] > 0.3          # volatility ranks drawdown
    assert 0.0 < a["q1"]["20"]["d_ic_p"] < 1.0
    with pytest.raises(ValueError, match="unknown specification"):
        wf.reference_run("real", 3)
    last = pd.bdate_range(wf.SIM_START, periods=wf.SIM_SESSIONS)[-1]
    assert last >= pd.Timestamp("2026-06-01")                 # reaches the last test block
    # the Q2-only run is the same Q2, and carries the per-date series the size check needs
    c = wf.reference_run("clustered_leverage", 3, q1=False, keep_series=True, **kwargs)
    assert c["q1"] == {} and c["q2"] == a["q2"] and c["q2_p"] == a["q2_p"]
    assert c["q2_dates"] == a["q2_dates"] and c["_series"]["d_ic"] == {}
    key = wf.confirmed_keys()[0]
    assert float(np.mean(c["_series"]["q2"][key])) == pytest.approx(a["q2"][key][wf.Q2_GATED])


def test_the_reference_is_assembled_from_every_specification_and_seed(pinned, monkeypatch):
    keys = wf.confirmed_keys()

    def job(args):
        spec, seed, q1 = args
        rng = np.random.default_rng(seed + 1000 * wf.SIM_SPECS.index(spec))
        series = {k: rng.normal(0.0, 0.03, size=190) for k in keys}
        run = {"spec": spec, "seed": seed, "q1": {},
               "q2_dates": {str(h): 190 for h in wf.HORIZONS},
               "q2": {k: {s: float(v.mean()) for s in wf.Q2_SERIES} for k, v in series.items()},
               "q2_p": {k: wf.ewc_test(v, int(k.split("|")[1]), 5)[2] for k, v in series.items()},
               "_series": {"q2": series, "d_ic": {}}}
        if q1:
            d = {str(h): rng.normal(0.0002, 0.004, size=190) for h in wf.HORIZONS}
            run["_series"]["d_ic"] = d
            run["q1"] = {h: {"gates": {"w1": False, "w2": True, "w3": False, "w4": True,
                                       "passed": False},
                             "d_ic": float(v.mean()), "d_capture": 0.0, "d_brier": 0.0}
                         for h, v in d.items()}
        return run

    monkeypatch.setattr(wf, "_reference_job", job)
    ref = wf.build_reference(seeds=tuple(range(11, 51)), q1_seeds=tuple(range(11, 21)),
                             check_seeds=tuple(range(51, 81)))
    assert len(ref["runs"]) == 80 and not any("_series" in r for r in ref["runs"])
    assert {r["seed"] for r in ref["runs"]} == set(range(11, 51))
    for spec in wf.SIM_SPECS:
        assert [r["seed"] for r in ref["k5_check"][spec]["runs"]] == list(range(51, 81))
        assert 0.0 <= ref["k5_check"][spec]["all_gates_any_test"] <= 0.2
    assert ref["code_sha256"] == wf.code_sha256() and ref["design"] == wf.frozen_design()
    assert ref["q1_gates"] == {"runs": 20, "w1_and_w2_at_a_gated_horizon": 0,
                               "w3_at_any_horizon": 0, "w4_run_horizons": 60,
                               "passed_at_a_gated_horizon": 0}
    assert set(ref["k5"]) == set(wf.SIM_SPECS) == set(ref["size"]["q2"]) == set(ref["size"]["d_ic"])
    for spec in wf.SIM_SPECS:
        assert ref["k5"][spec]["n_runs"] == 40
        assert ref["k5"][spec]["n_dates"] == {str(h): 190 for h in wf.HORIZONS}
        cells = ref["size"]["q2"][spec]
        assert sum(c["cells"] for c in cells.values()) == 40 * 29
        assert all(0.0 <= c["at_0.025"] <= c["at_0.05"] < 0.12 for c in cells.values())
        assert all(c["cells"] == 10 for c in ref["size"]["d_ic"][spec].values())
    json.dumps(ref)                                           # plain numbers throughout


# ---- the committed pins -------------------------------------------------------------------------
def test_the_pins_match_the_committed_files_and_the_reference_says_what_the_prereg_says():
    assert wf.PREREG_SHA256 == wf.prereg_sha256()
    ref = wf.pinned_reference()
    assert ref["prereg_sha256"] == wf.PREREG_SHA256 and ref["code_sha256"] == wf.code_sha256()
    assert [(r["spec"], r["seed"], bool(r["q1"])) for r in ref["runs"]] == [
        (s, k, k in wf.SIM_Q1_SEEDS) for s in wf.SIM_SPECS for k in wf.SIM_SEEDS]
    assert len(ref["runs"]) == 200 and sorted(ref["q2_ranges"]) == sorted(wf.confirmed_keys())
    cl, clj = wf.SIM_SPECS
    gated = [str(h) for h in wf.GATE_HORIZONS]

    # §7, Q1: W1 and W2 pass in the simulated market; W3 does not
    assert ref["q1_gates"] == {"runs": 40, "w1_and_w2_at_a_gated_horizon": 25,
                               "w3_at_any_horizon": 0, "w4_run_horizons": 115,
                               "passed_at_a_gated_horizon": 0}
    d_ic = [x for h in gated for x in ref["q1_ranges"][h]["d_ic"]]
    assert round(min(d_ic), 5) == -0.00008 and round(max(d_ic), 5) == 0.00079
    cap = [x for h in ref["q1_ranges"] for x in ref["q1_ranges"][h]["d_capture"]]
    assert round(100 * min(cap), 2) == -0.19 and round(100 * max(cap), 2) == 0.19
    slopes = [r["q1"][h]["models"]["A"]["slope"] for r in ref["runs"] if r["q1"] for h in r["q1"]]
    assert round(min(slopes), 2) == 0.92 and round(max(slopes), 2) == 1.06

    # §7, the test of a mean on centred simulated series: near its level; V2's rule is not
    printed = {cl: {"5": (0.022, 0.038, 0.028, 0.051), "20": (0.026, 0.052, 0.041, 0.065),
                    "60": (0.025, 0.054, 0.055, 0.090)},
               clj: {"5": (0.024, 0.041, 0.025, 0.040), "20": (0.034, 0.057, 0.049, 0.082),
                     "60": (0.029, 0.056, 0.058, 0.092)}}
    for spec, by_h in printed.items():
        for h, row in by_h.items():
            c = ref["size"]["q2"][spec][h]
            assert [c["at_0.025"], c["at_0.05"], c["v2_rule_at_0.025"],
                    c["v2_rule_at_0.05"]] == pytest.approx(row, abs=0.00051)
    assert {h: ref["size"]["q2"][cl][h]["cells"] for h in ("5", "20", "60")} == {
        "5": 1000, "20": 1100, "60": 800}

    # §7, K5: the thresholds, the dates they belong to, and how often the label is given
    assert {s: round(v["threshold"], 3) for s, v in ref["k5"].items()} == {cl: 2.952, clj: 2.870}
    real = {"5": 197, "20": 194, "60": 186}                  # §3
    bars = []
    for key in wf.confirmed_keys():
        h = key.split("|")[1]
        bars.append(max(v["signed_mean"][key] + v["threshold"] * v["sd"][key]
                        * math.sqrt(v["n_dates"][h] / real[h]) for v in ref["k5"].values()))
    assert round(min(bars), 4) == 0.0047 and round(max(bars), 4) == 0.0153
    assert sum(b < wf.Q2_IC_FLOOR for b in bars) == 1
    labels = {}
    for spec in wf.SIM_SPECS:
        k5, check = ref["k5"][spec], ref["k5_check"][spec]
        assert k5["n_runs"] == check["n_runs"] == 100
        assert k5["n_dates"] == {"5": 205, "20": 202, "60": 194}
        assert [r["seed"] for r in check["runs"]] == list(wf.SIM_CHECK_SEEDS)
        labels[spec] = [round(100 * x) for x in (
            k5["false_label"]["k5_any_test"], k5["false_label"]["all_gates_any_test"],
            k5["false_label"]["all_gates_gated_horizons"], check["k5_any_test"],
            check["all_gates_any_test"], check["all_gates_gated_horizons"])]
    assert labels == {cl: [1, 0, 0, 0, 0, 0], clj: [4, 4, 4, 4, 4, 1]}

    # §12: the volatility-controlled statistic across the 200 runs
    lows = [v[wf.Q2_GATED][0] for v in ref["q2_ranges"].values()]
    highs = [v[wf.Q2_GATED][1] for v in ref["q2_ranges"].values()]
    assert round(min(lows), 4) == -0.0105 and round(max(highs), 4) == 0.0172


def test_the_committed_result_was_produced_once_under_the_pinned_files():
    here = os.path.dirname(wf.__file__)
    with open(os.path.join(here, wf.RESULT_FILE)) as fh:
        out = json.load(fh)
    with open(os.path.join(here, wf.ATTEMPT_FILE)) as fh:
        attempts = json.load(fh)["attempts"]
    assert out["prereg_sha256"] == wf.PREREG_SHA256
    assert out["reference_sha256"] == wf.REFERENCE_SHA256
    assert out["code_sha256"] == wf.code_sha256()
    assert out["holdout_result_sha256"] == wf.HOLDOUT_RESULT_SHA256
    assert out["panel_sha256"] == wf.V2_PANEL_SHA256
    assert out["attempts"] == attempts and len(attempts) == 1
    assert attempts[0]["retry_reason"] is None and attempts[0]["git_head"] == out["git_head"]
    # what the readout reports (§11): no gated horizon passes, three tests carry the label
    assert out["status"] == "scored" and out["decision"]["outcome"] == "no_model_value"
    assert out["decision"]["advances"] is False and out["decision"]["horizons"] == []
    assert not any(out["horizons"][h]["gates"]["passed"] for h in ("20", "60"))
    assert sum(s["beyond_simulated_volatility"] for s in out["q2"].values()) == 3
