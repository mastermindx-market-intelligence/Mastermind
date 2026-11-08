from __future__ import annotations

import copy
import hashlib
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




# ---- Q2 -------------------------------------------------------------------------------------




def _q2(mean, p_above_zero):
    return {"oracle": {"mean": mean, "p_one_sided": p_above_zero}}






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




# ---- the test of a mean ---------------------------------------------------------------------












# ---- gates and decision ---------------------------------------------------------------------
def _summary(d_ic, p, blocks, d_cap, slope, brier_a, brier_b):
    return {"pairs": {"A_vs_B2": {"d_ic": {"mean": d_ic, "p_one_sided": p},
                                  "d_ic_by_block": dict(zip("abcde", blocks)),
                                  "d_capture": {"mean": d_cap}}},
            "models": {"A": {"calibration": {"slope": slope}, "brier_mean": brier_a},
                       "B2": {"brier_mean": brier_b}}}




# ---- guards ---------------------------------------------------------------------------------












@pytest.fixture
def staged(pinned, monkeypatch, tmp_path):
    """``run`` wired to a synthetic panel and to result and attempt files in a scratch folder."""
    from research import trend_persistence_substrate as substrate
    panel, inputs = _panel(seed=11, signal=0.6)
    # Reuse construction within this fixture; every loader call gets fresh nested data.
    holdout_seed = _holdout_like(panel, inputs)
    state = {"clean": True, "panel": panel}
    monkeypatch.setattr(wf, "pinned_reference", lambda: _reference())
    monkeypatch.setattr(wf, "pinned_holdout_result", lambda: copy.deepcopy(holdout_seed))
    monkeypatch.setattr(wf, "_git_state", lambda: {"head": "a" * 40, "clean": state["clean"]})
    monkeypatch.setattr(substrate, "load_repaired_panel",
                        lambda *a, **k: (None, None, None, None, {"store": {"names": []}}))
    monkeypatch.setattr(tpp, "build_panel", lambda *a, **k: state["panel"])
    monkeypatch.setattr(wf, "price_inputs", lambda *a, **k: inputs)
    monkeypatch.setattr(wf, "RESULT_FILE", str(tmp_path / "result.json"))
    monkeypatch.setattr(wf, "ATTEMPT_FILE", str(tmp_path / "attempt.json"))
    state["result"], state["attempt"] = tmp_path / "result.json", tmp_path / "attempt.json"
    return state










# ---- simulated reference --------------------------------------------------------------------




# ---- the committed pins -------------------------------------------------------------------------
