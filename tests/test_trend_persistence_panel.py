from __future__ import annotations

import inspect
import json
import re
import shutil

import numpy as np
import pandas as pd
import pytest

from brain import trend_persistence as tp
from research import trend_persistence_panel as panel
from research import trend_persistence_substrate as substrate


def _prices(n_sessions: int, n_names: int, seed: int = 0, start: str = "2019-01-01"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n_sessions)
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
    assert set(feats) == set(panel.FEATURES)
    assert set(ctrl) == set(panel.CONTROLS) | set(panel.CONTROLS_V2)


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


def test_risk_controls_match_a_direct_computation():
    closes, spy = _prices(300, 3, seed=12)
    rows = np.array([255, 299])
    _, ctrl = panel.compute_features(closes.to_numpy(float), spy.to_numpy(float), rows)
    lr = np.log(closes).diff()
    for a, row in enumerate(rows):
        for j, name in enumerate(closes.columns):
            for w in panel.RISK_WINDOWS:
                window = lr[name].iloc[row - w + 1: row + 1]
                assert ctrl[f"vol_{w}d"][a, j] == pytest.approx(window.std(ddof=1), rel=1e-9)
            for w in panel.DOWNSIDE_WINDOWS:
                window = lr[name].iloc[row - w + 1: row + 1].to_numpy()
                want = np.sqrt(np.mean(np.minimum(window, 0.0) ** 2))
                assert ctrl[f"downvol_{w}d"][a, j] == pytest.approx(want, rel=1e-9)
    assert panel.CONTROLS_V2[:4] == panel.MOMENTUM_CONTROLS
    assert set(panel.RISK_CONTROLS) < set(panel.CONTROLS_V2) and len(panel.CONTROLS_V2) == 11


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


def _synthetic_panel(masked: bool = False, stored=()):
    """A panel that straddles both fixed boundaries: 2022-01-01 and the v2 holdout start."""
    closes, spy = _prices(900, 130, seed=9, start="2020-01-01")
    closes.insert(0, "SPY", spy)
    mem = _membership(closes.drop(columns="SPY"))
    if not masked:
        return panel.build_panel(closes, mem, store_sourced=stored)
    printed = closes[closes.index >= pd.Timestamp(substrate.STORE_START)].reindex(closes.index)
    return panel.build_panel(closes, mem, observed=closes.notna(), printed=printed,
                             store_sourced=stored)


def test_sample_boundaries_are_fixed_and_development_never_touches_a_locked_price():
    built = _synthetic_panel()
    index = built["index"]
    first_locked = int(index.searchsorted(pd.Timestamp(panel.HOLDOUT_START)))
    first_v2 = int(index.searchsorted(pd.Timestamp(panel.HOLDOUT_FORMATION_START_V2)))
    assert 252 < first_locked < first_v2 < len(index)
    for h in panel.HORIZONS:
        dev = panel.sample_rows(built, h, "dev", "v2")
        assert len(dev) and (built["labels"][h]["exit_rows"][dev] < first_locked).all()
        np.testing.assert_array_equal(dev, panel.sample_rows(built, h, "dev", "v1"))
        hold_v1 = panel.sample_rows(built, h, "holdout", "v1")
        hold_v2 = panel.sample_rows(built, h, "holdout", "v2")
        assert (built["rows"][hold_v1] >= first_locked).all()
        assert len(hold_v2) and (built["rows"][hold_v2] >= first_v2).all()
        assert not set(dev) & set(hold_v1) and set(hold_v2) < set(hold_v1)
        # the quarantine between the two boundaries belongs to nobody in v2
        quarantine = set(hold_v1) - set(hold_v2)
        assert quarantine and all(built["rows"][q] < first_v2 for q in quarantine)


def test_no_caller_can_move_the_holdout_boundary():
    assert "holdout_start" not in inspect.signature(panel.build_panel).parameters
    assert "holdout_start" not in inspect.signature(panel.score).parameters
    assert "confirm" not in inspect.signature(panel.score).parameters
    built = _synthetic_panel()
    assert "holdout_start" not in built
    before = panel.sample_rows(built, 20, "dev")
    built["holdout_start"] = "2030-01-01"                     # a stray key changes nothing
    np.testing.assert_array_equal(before, panel.sample_rows(built, 20, "dev"))
    with pytest.raises(KeyError):                             # only registered designs exist
        panel.score(built, design=panel.Design(
            id="v2", prereg_file="x.md", prereg_sha256="0" * 64, controls=panel.CONTROLS,
            endpoints=panel.ENDPOINTS, holdout_formation_start="2030-01-01",
            observed_mask=False, printed_floor=False, risk_bucket_gate=False,
            substrate="audited", holdout_open=True))
    with pytest.raises(TypeError):                            # the registry itself is read-only
        panel.DESIGNS["v1"] = panel.DESIGNS["v2"]


def test_v1_holdout_is_closed_for_good():
    built = _synthetic_panel()
    pin = panel.pinned_prereg("v1")
    with pytest.raises(panel.HoldoutLocked):
        panel.score(built, sample="holdout")
    fake_dev = {"status": "scored", "sample": "dev", "design_id": "v1", "prereg_sha256": pin,
                "survivors": {"retained_60d|5|forward_rel": 1}}
    with pytest.raises(panel.HoldoutLocked, match="closed"):
        panel.score(built, sample="holdout", prereg_hash=pin, dev_result=fake_dev)
    with pytest.raises(panel.HoldoutLocked):
        panel.run(sample="holdout", prereg_hash=pin, dev_result=fake_dev)


def test_v2_holdout_needs_the_hash_and_the_committed_development_result(monkeypatch):
    pytest.importorskip("engine.validation")
    built = _synthetic_panel(masked=True)
    monkeypatch.setattr(panel, "HOLDOUT_PANEL_SHA256", {"v2": built["digest"]})
    pin = panel.pinned_prereg("v2")
    dev = panel.score(built, design="v2", sample="dev")
    assert dev["status"] == "scored" and dev["design_id"] == "v2"
    for kwargs in (
        {},                                                               # nothing
        {"prereg_hash": "0" * 64, "dev_result": dev},                     # wrong hash
        {"prereg_hash": pin},                                             # no dev result
        {"prereg_hash": pin, "dev_result": {**dev, "design_id": "v1"}},   # another design's
        {"prereg_hash": pin, "dev_result": {**dev, "sample": "holdout"}},
        {"prereg_hash": pin, "dev_result": {**dev, "prereg_sha256": "0" * 64}},
    ):
        with pytest.raises(panel.HoldoutLocked):
            panel.score(built, design="v2", sample="holdout", **kwargs)
    with pytest.raises(panel.HoldoutLocked):                  # refused before any data is loaded
        panel.run(design="v2", sample="holdout", prereg_hash=pin)
    # a development result that this panel does not reproduce cannot open the holdout
    forged = {**dev, "survivors": {**dev["survivors"], "retained_60d|5|forward_max_drawdown": 1}}
    with pytest.raises(panel.HoldoutLocked, match="does not reproduce"):
        panel.score(built, design="v2", sample="holdout", prereg_hash=pin, dev_result=forged)


def test_holdout_is_bound_to_the_panel_the_development_result_was_scored_on(monkeypatch):
    pytest.importorskip("engine.validation")
    built = _synthetic_panel(masked=True)
    monkeypatch.setattr(panel, "HOLDOUT_PANEL_SHA256", {"v2": built["digest"]})
    pin = panel.pinned_prereg("v2")
    dev = panel.score(built, design="v2", sample="dev")
    assert dev["panel_sha256"] == built["digest"] and len(built["digest"]) == 64
    assert _synthetic_panel(masked=True)["digest"] == built["digest"]      # deterministic
    # same design, same survivors claimed, different inputs: one more stored name
    other = _synthetic_panel(masked=True, stored=("N000",))
    assert other["digest"] != built["digest"]
    with pytest.raises(panel.HoldoutLocked, match="not the one"):
        panel.score(other, design="v2", sample="holdout", prereg_hash=pin, dev_result=dev)
    legacy = {k: v for k, v in dev.items() if k != "panel_sha256"}         # an unbound result
    with pytest.raises(panel.HoldoutLocked, match="not the one"):
        panel.score(built, design="v2", sample="holdout", prereg_hash=pin, dev_result=legacy)


def test_holdout_is_pinned_in_code_to_the_panel_v2_was_scored_on():
    """A self-consistent development result on some other panel still cannot open the holdout."""
    pytest.importorskip("engine.validation")
    assert panel.HOLDOUT_PANEL_SHA256 == {
        "v2": "48cb5e76269b3a503d2973aecdd04733a2d8b88434db06de8367a224ba4ef178"}
    assert "HOLDOUT_PANEL_SHA256" not in json.dumps(panel.frozen_design("v2"))
    with open("research/data/trend_persistence_v2_dev.json") as fh:
        committed = json.load(fh)
    assert committed["panel_sha256"] == panel.HOLDOUT_PANEL_SHA256["v2"]
    built = _synthetic_panel(masked=True)
    pin = panel.pinned_prereg("v2")
    dev = panel.score(built, design="v2", sample="dev")       # binds to the synthetic panel
    with pytest.raises(panel.HoldoutLocked, match="pinned for this design"):
        panel.score(built, design="v2", sample="holdout", prereg_hash=pin, dev_result=dev)


def test_statistics_the_holdout_does_not_list_are_never_formed():
    pytest.importorskip("engine.validation")
    V = panel._judges()
    dates = pd.bdate_range("2023-01-02", periods=60).to_numpy()
    series = np.linspace(-0.01, 0.03, 60)
    full = panel._series_stats(V, dates, series, 20, 5, 1)
    lean = panel._series_stats(V, dates, series, 20, 5, 1, gating=False)
    assert set(full) - set(lean) == {"hit", "thinned", "era_means"}
    assert {k: full[k] for k in lean} == lean
    short = panel._series_stats(V, dates[:3], series[:3], 20, 5, 1, gating=False)
    assert set(short) == set(lean) and short["mean"] is None


def test_a_panel_off_the_preregistered_calendar_is_refused():
    closes, spy = _prices(400, 20, seed=5)
    closes.insert(0, "SPY", spy)
    mem = _membership(closes.drop(columns="SPY"))
    for kwargs in ({"step": 10}, {"lag": 2}, {"horizons": (5, 20)}):
        with pytest.raises(ValueError, match="pre-registered calendar"):
            panel.score(panel.build_panel(closes, mem, **kwargs), sample="dev")


def test_holdout_stays_unspent_without_a_development_survivor(monkeypatch):
    pytest.importorskip("engine.validation")
    built = _synthetic_panel(masked=True)
    monkeypatch.setattr(panel, "HOLDOUT_PANEL_SHA256", {"v2": built["digest"]})
    pin = panel.pinned_prereg("v2")
    real = panel._apply_dev_gates

    def no_survivors(V, result, d):
        real(V, result, d)
        result["survivors"] = {}

    monkeypatch.setattr(panel, "_apply_dev_gates", no_survivors)
    dev = panel.score(built, design="v2", sample="dev")
    out = panel.score(built, design="v2", sample="holdout", prereg_hash=pin, dev_result=dev)
    assert out["status"] == "not_run" and "tests" not in out and "coverage" not in out


def test_holdout_scores_the_development_survivors_and_nothing_else(monkeypatch):
    pytest.importorskip("engine.validation")
    built = _synthetic_panel(masked=True, stored=("N000", "N001", "N002"))
    monkeypatch.setattr(panel, "HOLDOUT_PANEL_SHA256", {"v2": built["digest"]})
    pin = panel.pinned_prereg("v2")
    keys = {"max_drawdown_120d|20|forward_max_drawdown": 1,
            "retained_60d|20|forward_max_drawdown": -1}
    real = panel._apply_dev_gates

    def two_survivors(V, result, d):
        real(V, result, d)
        result["survivors"] = dict(keys)

    monkeypatch.setattr(panel, "_apply_dev_gates", two_survivors)
    dev = panel.score(built, design="v2", sample="dev")
    out = panel.score(built, design="v2", sample="holdout", prereg_hash=pin, dev_result=dev)
    assert out["status"] == "scored" and out["sample"] == "holdout"
    assert set(out["tests"]) == set(keys) and out["n_confirm_requested"] == 2
    assert out["panel_sha256"] == built["digest"]
    assert out["coverage"]["20"]["printed_floor_fraction"] == 1.0
    assert list(out["coverage"]) == ["20"]                   # horizons without a survivor: untouched
    first = pd.Timestamp(out["coverage"]["20"]["first_date"])
    assert first >= pd.Timestamp(panel.HOLDOUT_FORMATION_START_V2)
    assert 0.0 < out["coverage"]["20"]["store_sourced_fraction"] < 0.1
    for key, sign in keys.items():
        st = out["tests"][key]
        assert st["dev_sign"] == sign
        assert set(st["holdout_gates"]) == {"h1_same_sign", "h2_one_sided_p", "h3_bh_fdr",
                                            "h4_ic_floor"}
        assert "drop_mean" in st and "audited_only_mean" in st and "v1_controls_mean" in st
        # nothing the pre-registration does not list is formed on the holdout
        assert not set(st) & {"hit", "thinned", "era_means", "bucket_means",
                              "risk_bucket_means", "gates", "advance_dev"}
    json.dumps(out, default=str)


def test_a_survivor_without_holdout_dates_is_printed_as_unconfirmed(monkeypatch):
    pytest.importorskip("engine.validation")
    built = _synthetic_panel(masked=True)
    monkeypatch.setattr(panel, "HOLDOUT_PANEL_SHA256", {"v2": built["digest"]})
    pin = panel.pinned_prereg("v2")
    keys = {"max_drawdown_120d|20|forward_max_drawdown": 1,
            "max_drawdown_120d|60|forward_max_drawdown": 1}
    real_gates, real_rows = panel._apply_dev_gates, panel.sample_rows

    def two_survivors(V, result, d):
        real_gates(V, result, d)
        result["survivors"] = dict(keys)

    def no_long_horizon(built_, horizon, sample, design="v1"):
        rows = real_rows(built_, horizon, sample, design)
        return rows[:0] if (sample == "holdout" and int(horizon) == 60) else rows

    monkeypatch.setattr(panel, "_apply_dev_gates", two_survivors)
    monkeypatch.setattr(panel, "sample_rows", no_long_horizon)
    dev = panel.score(built, design="v2", sample="dev")
    out = panel.score(built, design="v2", sample="holdout", prereg_hash=pin, dev_result=dev)
    assert set(out["tests"]) == set(keys) and out["n_confirm_requested"] == 2
    lost = out["tests"]["max_drawdown_120d|60|forward_max_drawdown"]
    assert lost["not_scored"] == "no_usable_holdout_dates" and lost["n_dates"] == 0
    assert lost["p_one_sided"] == 1.0 and lost["confirmed_holdout"] is False
    assert not any(lost["holdout_gates"].values())
    assert "max_drawdown_120d|60|forward_max_drawdown" not in out["confirmed"]


def test_development_scoring_runs_every_preregistered_test():
    pytest.importorskip("engine.validation")
    built = _synthetic_panel()
    out = panel.score(built, sample="dev")
    assert out["status"] == "scored" and out["sample"] == "dev" and out["design_id"] == "v1"
    assert out["prereg_sha256"] == panel.prereg_sha256() == panel.DESIGNS["v1"].prereg_sha256
    assert out["n_tests"] == len(panel.FEATURES) * len(panel.HORIZONS) * len(panel.ENDPOINTS)
    assert out["n_tests"] == 144 and out["n_tests_with_p"] == 144
    one = out["tests"]["signed_efficiency_60d|20|forward_rel"]
    assert one["family"] == "path_quality" and one["n_dates"] > 8
    assert set(one["gates"]) == {"g1_bh_fdr", "g2_ic_floor", "g3_thinned", "g4_eras",
                                 "g5_momentum_buckets", "g6_delisting_invariant"}
    assert all(isinstance(v, bool) for v in one["gates"].values())
    assert len(one["bucket_means"]) == panel.N_BUCKETS and len(one["bin_means"]) == panel.N_BINS
    assert "risk_bucket_means" not in one and "v1_controls_mean" not in one
    assert set(out["survivors"]) == {k for k, st in out["tests"].items() if st["advance_dev"]}
    assert set(out["family_summary"]) == {f"{f}|{e}" for f in panel.FAMILIES
                                          for e in panel.ENDPOINTS}
    json.dumps(out, default=str)


def test_v2_development_scores_the_risk_endpoint_with_the_volatility_gate():
    pytest.importorskip("engine.validation")
    built = _synthetic_panel(masked=True)
    out = panel.score(built, design="v2", sample="dev")
    assert out["n_tests"] == 72 and out["prereg_sha256"] == panel.DESIGNS["v2"].prereg_sha256
    assert {k.split("|")[2] for k in out["tests"]} == {"forward_max_drawdown"}
    one = out["tests"]["max_drawdown_60d|20|forward_max_drawdown"]
    assert set(one["gates"]) == {"g1_bh_fdr", "g2_ic_floor", "g3_thinned", "g4_eras",
                                 "g5_momentum_buckets", "g6_delisting_invariant",
                                 "g7_risk_buckets"}
    assert len(one["risk_bucket_means"]) == panel.N_BUCKETS
    assert isinstance(one["v1_controls_mean"], float)
    assert set(out["family_summary"]) == {f"{f}|forward_max_drawdown" for f in panel.FAMILIES}
    assert out["design"] == panel.frozen_design("v2")


def test_a_design_refuses_a_panel_built_for_the_other_mask():
    with pytest.raises(ValueError, match="quoted-price mask"):
        panel.score(_synthetic_panel(masked=True), design="v1", sample="dev")
    with pytest.raises(ValueError, match="quoted-price mask"):
        panel.score(_synthetic_panel(), design="v2", sample="dev")
    closes, spy = _prices(330, 4, seed=13)
    closes.insert(0, "SPY", spy)
    mem = _membership(closes.drop(columns="SPY"))
    with pytest.raises(ValueError, match="printed prices"):       # v2 without printed closes
        panel.score(panel.build_panel(closes, mem, observed=closes.notna()),
                    design="v2", sample="dev")


def test_the_selection_floor_is_tested_on_the_printed_close_where_one_is_known():
    closes, spy = _prices(330, 4, seed=13)
    closes.insert(0, "SPY", spy)
    mem = _membership(closes.drop(columns="SPY"))
    names = [c for c in closes.columns if c != "SPY"]
    plain = panel.build_panel(closes, mem, observed=closes.notna())
    at = {int(r): i for i, r in enumerate(plain["rows"])}
    assert plain["eligible"][at[262]].all() and not plain["printed_floor"]
    printed = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    printed.iloc[262, 1] = 4.99       # N000 printed under the floor: a later reverse split
    printed.iloc[267, 2] = 250.0      # N001 printed far above its adjusted level: a later split
    lowered = closes.copy()
    lowered.iloc[:, 2] = closes.iloc[:, 2] * (2.0 / closes.iloc[267, 2])   # adjusted level: $2
    built = panel.build_panel(lowered, mem, observed=closes.notna(), printed=printed)
    assert built["printed_floor"] and built["digest"] != plain["digest"]
    assert not built["eligible"][at[262], 0]                     # the printed close decides
    assert built["eligible"][at[262], 2] and built["eligible"][at[267], 0]   # no print: fallback
    assert built["eligible"][at[267], 1]                         # printed above, adjusted below
    assert not built["eligible"][at[262], 1]                     # no print there: adjusted $2
    assert built["floor_printed"][at[262], 0] and not built["floor_printed"][at[262], 2]
    assert names[0] == "N000"


def test_only_quoted_prices_decide_eligibility_and_features():
    closes, spy = _prices(330, 4, seed=13)
    closes.insert(0, "SPY", spy)
    mem = _membership(closes.drop(columns="SPY"))
    observed = closes.notna()
    observed.iloc[262, 1] = False                  # N000: a gap fill on a formation day
    observed.iloc[250, 2] = False                  # N001: a gap fill inside later windows
    plain = panel.build_panel(closes, mem)
    masked = panel.build_panel(closes, mem, observed=observed)
    assert masked["observed_mask"] and not plain["observed_mask"]
    at = {int(r): i for i, r in enumerate(masked["rows"])}
    assert plain["eligible"][at[262], 0] and not masked["eligible"][at[262], 0]
    assert masked["eligible"][at[267], 0]
    assert np.isnan(masked["features"]["efficiency_20d"][at[262], 1])       # row 250 in window
    assert np.isfinite(plain["features"]["efficiency_20d"][at[262], 1])
    assert np.isfinite(masked["features"]["efficiency_20d"][at[272], 1])    # window moved past it
    assert np.isnan(masked["controls"]["vol_252d"][at[272], 1])
    for h in panel.HORIZONS:                       # labels follow the cleaned series either way
        np.testing.assert_array_equal(plain["labels"][h]["forward_max_drawdown"],
                                      masked["labels"][h]["forward_max_drawdown"])


def test_nothing_is_scored_when_a_preregistration_drifts(monkeypatch, tmp_path):
    for design in panel.DESIGNS.values():
        shutil.copy(panel.prereg_path(design), tmp_path / design.prereg_file)
    with open(tmp_path / panel.DESIGNS["v2"].prereg_file, "a", encoding="utf-8") as fh:
        fh.write("\none more gate\n")
    monkeypatch.setattr(panel, "_HERE", str(tmp_path))
    assert panel.pinned_prereg("v1") == panel.DESIGNS["v1"].prereg_sha256
    with pytest.raises(panel.PreregDrift):
        panel.pinned_prereg("v2")
    with pytest.raises(panel.PreregDrift):
        panel.score(_synthetic_panel(masked=True), design="v2", sample="dev")


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


@pytest.mark.parametrize("design", ["v1", "v2"])
def test_preregistration_freezes_the_instrument_constants(design):
    text = open(panel.prereg_path(design), encoding="utf-8").read()
    block = re.search(r"```json\n(.*?)\n```", text, re.S)
    assert block, "pre-registration must carry its machine-readable design block"
    assert json.loads(block.group(1)) == panel.frozen_design(design)
    assert panel.pinned_prereg(design) == panel.prereg_sha256(design=design)
    assert len(panel.pinned_prereg(design)) == 64
    assert pd.Timestamp(panel.HOLDOUT_START) == pd.Timestamp("2022-01-01")


def test_only_the_confirmatory_design_can_ever_open_a_holdout():
    assert [d.id for d in panel.DESIGNS.values() if d.holdout_open] == ["v2"]
    v2 = panel.DESIGNS["v2"]
    assert v2.endpoints == ("forward_max_drawdown",) and v2.observed_mask and v2.risk_bucket_gate
    assert v2.printed_floor and not panel.DESIGNS["v1"].printed_floor
    assert pd.Timestamp(v2.holdout_formation_start) > pd.Timestamp(panel.HOLDOUT_START)


def test_every_feature_belongs_to_exactly_one_family():
    assert len(panel.FEATURES) == 24 and len(set(panel.FEATURES)) == 24
    assert {panel.family_of(f) for f in panel.FEATURES} == set(panel.FAMILIES)


def test_split_adjustment_puts_earlier_prices_on_the_new_share_basis():
    idx = pd.bdate_range("2022-01-03", periods=10)
    raw = pd.Series([100.0] * 5 + [50.0] * 3 + [500.0] * 2, index=idx)
    splits = pd.DataFrame({"execution_date": [idx[5], idx[8]],
                           "split_from": [1.0, 10.0], "split_to": [2.0, 1.0]})
    adj = substrate.split_adjust(raw, splits)               # 2-for-1, then 1-for-10 reverse
    assert np.allclose(adj.to_numpy(), 500.0)
    assert substrate.split_adjust(raw, splits.iloc[0:0]).equals(raw)


def test_member_segment_keeps_the_listing_the_membership_refers_to():
    old = pd.bdate_range("2021-07-06", periods=40)
    new = pd.bdate_range("2023-06-07", periods=60)
    close = pd.Series(np.r_[np.full(40, 9.0), np.full(60, 120.0)], index=old.append(new))
    spans = [(pd.Timestamp("2023-06-07"), pd.NaT)]
    kept = substrate.member_segment(close, spans)
    assert kept.index[0] == new[0] and len(kept) == 60 and (kept == 120.0).all()
    earlier = substrate.member_segment(close, [(pd.Timestamp("2020-01-01"),
                                                pd.Timestamp("2021-08-01"))])
    assert earlier.index[-1] == old[-1] and len(earlier) == 40
    assert substrate.member_segment(close, [(pd.Timestamp("2010-01-01"),
                                             pd.Timestamp("2011-01-01"))]).empty
    whole = pd.Series(1.0, index=pd.bdate_range("2022-01-03", periods=30))
    assert len(substrate.member_segment(whole, spans[:0] + [(whole.index[0], pd.NaT)])) == 30


def test_store_block_is_adjusted_trimmed_and_reported(tmp_path):
    pytest.importorskip("pyarrow")
    index = pd.bdate_range("2021-07-06", periods=300)
    pd.DataFrame({"close": np.r_[np.full(100, 60.0), np.full(200, 20.0)]},
                 index=index).to_parquet(tmp_path / "AAA.parquet")
    reused = pd.DataFrame({"close": np.r_[np.full(50, 5.0), np.full(150, 80.0)]},
                          index=index[:50].append(index[150:]))
    reused.to_parquet(tmp_path / "BBB.parquet")
    mem = pd.DataFrame({"ticker": ["AAA", "BBB", "CCC", "DD/E"],
                        "start_date": [index[0], index[150], index[0], index[0]],
                        "end_date": [pd.NaT, pd.NaT, pd.NaT, pd.NaT]})
    assert substrate.store_candidates(mem, have=["SPY", "CCC"]) == ["AAA", "BBB", "DD/E"]
    splits = pd.DataFrame({"ticker": ["AAA"], "execution_date": [index[100]],
                           "split_from": [1.0], "split_to": [3.0]})
    block, report = substrate.build_store_block(["AAA", "BBB", "DD/E"], mem, index, splits,
                                                str(tmp_path))
    assert list(block.columns) == ["AAA", "BBB"] and report["no_file"] == ["DD/E"]
    assert np.allclose(block["AAA"].to_numpy(), 20.0)       # the 3-for-1 split is removed
    assert block["BBB"].iloc[:150].isna().all() and (block["BBB"].iloc[150:] == 80.0).all()
    assert report["listings_trimmed"] == ["BBB"] and report["splits_applied"] == 1
    # printed closes are read by symbol and day, unadjusted and untrimmed
    printed, absent = substrate.load_printed(["AAA", "BBB", "CCC"], index, str(tmp_path))
    assert absent == ["CCC"] and list(printed.columns) == ["AAA", "BBB"]
    assert (printed["AAA"].iloc[:100] == 60.0).all() and (printed["AAA"].iloc[100:] == 20.0).all()
    assert (printed["BBB"].iloc[:50] == 5.0).all() and printed["BBB"].iloc[50:150].isna().all()
    assert substrate.store_window_members(mem) == ["AAA", "BBB", "CCC", "DD/E"]


def test_a_printed_close_under_a_dollar_is_not_a_quote(tmp_path, monkeypatch):
    """The quoted-price mask reads the price as printed, not the split-adjusted one."""
    pytest.importorskip("pyarrow")
    from loop import factor_experiment as fx
    index = pd.bdate_range("2021-07-06", periods=40)
    closes = pd.DataFrame({"SPY": 400.0, "AAA": 30.0, "BBB": 12.0, "CCC": 50.0}, index=index)
    mem = pd.DataFrame({"ticker": ["AAA", "BBB", "CCC", "DDD"], "start_date": index[0],
                        "end_date": pd.NaT})
    monkeypatch.setattr(panel, "load_audited_panel", lambda breadth_dir=None: (
        closes.copy(), mem.copy(), {"source": "test"}))
    monkeypatch.setattr(substrate, "_raw_audited",
                        lambda breadth, floor: closes.drop(columns="SPY").copy())
    monkeypatch.setattr(substrate, "load_split_reference", lambda: pd.DataFrame(
        {"ticker": pd.Series(dtype=str), "execution_date": pd.Series(dtype="datetime64[ns]"),
         "split_from": pd.Series(dtype=float), "split_to": pd.Series(dtype=float)}))
    # AAA printed under $1 for ten sessions although its adjusted close is $30 (a later
    # reverse split); BBB printed above $1 throughout; CCC has no file; DDD is store-sourced.
    pd.DataFrame({"close": np.r_[np.full(10, 0.60), np.full(30, 30.0)]},
                 index=index).to_parquet(tmp_path / "AAA.parquet")
    pd.DataFrame({"close": np.full(40, 12.0)}, index=index).to_parquet(tmp_path / "BBB.parquet")
    pd.DataFrame({"close": np.r_[np.full(5, 0.80), np.full(35, 9.0)]},
                 index=index).to_parquet(tmp_path / "DDD.parquet")
    out_closes, observed, printed, _, prov = substrate.load_repaired_panel(None, str(tmp_path))
    assert list(out_closes.columns) == ["SPY", "AAA", "BBB", "CCC", "DDD"]
    assert prov["store"]["names"] == ["DDD"]
    assert not observed["AAA"].iloc[:10].any() and observed["AAA"].iloc[10:].all()
    assert (printed["AAA"].iloc[:10] == 0.60).all()           # printed, not adjusted
    assert observed["BBB"].all()
    assert printed["CCC"].isna().all() and observed["CCC"].all()   # no print known: audited mask
    assert not observed["DDD"].iloc[:5].any() and observed["DDD"].iloc[5:].all()
    assert observed["SPY"].all()
    assert fx.MIN_PRICE == 1.0
    assert prov["printed"]["n_names"] == 3


def test_committed_split_reference_loads_clean():
    ref = substrate.load_split_reference()
    assert len(ref) > 100 and not ref.duplicated(["ticker", "execution_date"]).any()
    assert (ref["execution_date"] >= pd.Timestamp("2021-07-01")).all()
    assert pd.Timestamp(substrate.STORE_START) < pd.Timestamp(panel.HOLDOUT_START)
