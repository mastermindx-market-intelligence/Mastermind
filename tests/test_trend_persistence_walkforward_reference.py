"""Preserved walk-forward reference and volatility contracts."""
from __future__ import annotations

import json
import math
import numpy as np
import pandas as pd
import pytest
from research import trend_persistence_panel as tpp
from research import trend_persistence_walkforward as wf

from tests.test_trend_persistence_walkforward import (
    MDD,
    _fake_runs,
    _holdout_like,
    _k5,
    _panel,
    _q2,
    _reference,
    _summary,
    pinned,
)


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
