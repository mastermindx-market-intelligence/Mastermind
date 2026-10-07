"""Tests of the Wave C instrument, research/trend_persistence_group.py.

The eight tests TREND_PERSISTENCE_PREREG_C1.md section 11 names are here under their own names;
the rest pin the pieces the pre-registration imports or fixes (the column map, the test of a
mean, the noncentral t power rule, the constants block, the one-run guard).
"""
from __future__ import annotations

import hashlib
import json
import math
import os

import numpy as np
import pandas as pd
import pytest

from research import trend_persistence_group as g
from research import trend_persistence_panel as tpp
from research import trend_persistence_walkforward as wf

START, N_SESSIONS = "2016-01-01", 2700
PER_SECTOR, N_UNLABELLED = 28, 12


def _synthetic(seed: int = 0, signal: float = 0.0, leavers: int = 6):
    """Random-walk closes for 11 x 28 labelled names and 12 unlabelled ones, SPY first, with a
    membership frame and a sector snapshot shaped like the loaders' output. ``signal`` plants a
    persistent sector drift that a sector-relative-strength feature can see."""
    rng = np.random.default_rng(seed)
    index = pd.bdate_range(START, periods=N_SESSIONS)
    K = len(g.SECTORS)
    labelled = [f"S{k:02d}N{i:02d}" for k in range(K) for i in range(PER_SECTOR)]
    names = labelled + [f"UNL{i:02d}" for i in range(N_UNLABELLED)]
    N = len(names)
    sector_of = {n: g.SECTORS[int(n[1:3])] for n in labelled}
    sec_idx = np.array([g.SECTORS.index(sector_of[n]) if n in sector_of else -1 for n in names])
    mkt = rng.normal(0.0003, 0.010, N_SESSIONS)
    sect = rng.normal(0.0, 0.006, (N_SESSIONS, K))
    drift = np.zeros((N_SESSIONS, K))
    if signal:
        state = np.zeros(K)
        for t in range(N_SESSIONS):
            state = 0.98 * state + rng.normal(0, 0.0008, K)
            drift[t] = signal * state
    r = rng.normal(0.0, 0.015, (N_SESSIONS, N)) + mkt[:, None]
    lab = sec_idx >= 0
    r[:, lab] += sect[:, sec_idx[lab]] + drift[:, sec_idx[lab]]
    closes = pd.DataFrame(np.exp(np.log(50.0) + np.cumsum(r, axis=0)), index=index, columns=names)
    closes.insert(0, "SPY", np.exp(np.log(300.0) + np.cumsum(mkt)))
    observed = pd.DataFrame(True, index=index, columns=closes.columns)
    end = [pd.NaT] * N
    for j in range(leavers):
        end[j * 20] = index[1800 + 40 * j]
    mem = pd.DataFrame({"ticker": names, "start_date": [index[0]] * N, "end_date": end,
                        "src": [g.TIERS[i % 3] for i in range(N)]})
    snapshot = {"sector": {n: sector_of.get(n) for n in names},
                "current": {n: pd.isna(e) for n, e in zip(names, end)},
                "label_asof": pd.Timestamp("2026-10-04"), "sha256": "synthetic", "path": "synthetic",
                "era_correct_any": False, "n_rows": N}
    return closes, observed, mem, snapshot


def _build(seed: int = 0, signal: float = 0.0, horizons=(20,), **kw):
    closes, observed, mem, snapshot = _synthetic(seed, signal, **kw)
    panel = tpp.build_panel(closes, mem, observed=observed, horizons=horizons)
    inputs = wf.price_inputs(panel, closes, observed)
    sec, cur = g.sector_codes(panel["names"], snapshot)
    tier = g.tier_codes(panel["index"], panel["names"], mem)
    gi = g.group_inputs(closes, observed, panel, sec, tier, cur)
    return {"panel": panel, "inputs": inputs, "closes": closes, "observed": observed, "mem": mem,
            "snapshot": snapshot, "sec": sec, "cur": cur, "tier": tier, "gi": gi}


@pytest.fixture(scope="module")
def world():
    return _build()


@pytest.fixture(scope="module")
def assembled(world):
    red = g.redundancy(world["gi"], world["panel"])
    data = g.assemble_group(world["panel"], world["inputs"], world["gi"], 20, surviving=red["surviving"])
    return red, data


def _sector_level_columns():
    return ([g.IDX[k] for k in g.SECTOR_VOL] + [g.IDX["grp_size"]] + [g.IDX[k] for k in g.GROUP_FEATURES]
            + [g.IDX[f"sector:{s}"] for s in g.SECTORS])


# ---- the eight tests section 11 names -----------------------------------------------------------
def test_zero_within_sector_variance_of_every_sector_level_regressor(assembled):
    _, data = assembled
    cols = _sector_level_columns()
    for d in range(data["n_dates"]):
        sl = slice(int(data["start"][d]), int(data["start"][d + 1]))
        R, sec = data["R"][sl][:, cols], data["sec"][sl]
        for k in np.unique(sec):
            block = R[sec == k]
            assert np.all(block.max(axis=0) == block.min(axis=0)), (d, k)
    # and the sector-level ranks really vary ACROSS sectors on a date
    sl = slice(int(data["start"][0]), int(data["start"][1]))
    assert len(np.unique(data["R"][sl][:, g.IDX["grp_rs_60"]])) == len(g.SECTORS)


def test_reproduction_of_the_two_b2_means_is_the_committed_result_and_refuses_a_drift(world, monkeypatch):
    # the real pin: the committed file hashes to the frozen constant and carries the frozen means
    b2 = g.pinned_b2_result()
    for h, (mean, n) in g.B2_MEANS.items():
        assert b2["horizons"][str(h)]["models"]["B2"]["ic"]["mean"] == mean
        assert b2["horizons"][str(h)]["models"]["B2"]["ic"]["n_dates"] == n
    # the mechanism, on the synthetic panel: B2's own assembly and scoring must reproduce exactly
    panel, inputs = world["panel"], world["inputs"]
    data = wf.assemble(panel, inputs, 20)
    ic = wf.score_blocks(data, 20, wf.BLOCKS, models=("B2",))["per_date"]["B2"]["ic"]
    mean, n = float(np.mean(ic)), int(len(ic))
    fake = {"horizons": {"20": {"models": {"B2": {"ic": {"mean": mean, "n_dates": n}}}}}}
    monkeypatch.setattr(g, "B2_MEANS", {20: (mean, n)})
    out = g.reproduce_b2(panel, inputs, fake)
    assert out["20"]["mean"] == mean and out["20"]["n_dates"] == n
    monkeypatch.setattr(g, "B2_MEANS", {20: (mean + 1e-6, n)})
    with pytest.raises(tpp.PreregDrift):            # the committed file disagrees with the constant
        g.reproduce_b2(panel, inputs, fake)
    fake2 = {"horizons": {"20": {"models": {"B2": {"ic": {"mean": mean + 1e-6, "n_dates": n}}}}}}
    with pytest.raises(g.GroupRefused):             # the constant and file agree; the panel does not
        g.reproduce_b2(panel, inputs, fake2)


def test_validity_refusal_at_h60_under_96_dates_and_acceptance_at_96():
    assert not g.valid_gate(95, 60) and g.valid_gate(96, 60)
    assert g.valid_gate(32, 20) and not g.valid_gate(31, 20)
    rng = np.random.default_rng(3)
    assert g.series_summary(rng.normal(size=95), 60)["valid_gate"] is False
    assert g.series_summary(rng.normal(size=96), 60)["valid_gate"] is True
    # the rule is the family's: floor(n / 2q) >= EWC_MIN_DF with q = ceil(h / step)
    assert wf.ewc_df(96, 60, g.STEP) >= wf.EWC_MIN_DF


def test_determinism_of_the_redundancy_rule(world):
    a = g.redundancy(world["gi"], world["panel"])
    b = g.redundancy(world["gi"], world["panel"])
    assert a == b and a["dropped"] == [] and tuple(a["surviving"]) == g.GROUP_FEATURES
    assert a["threshold"] == g.REDUNDANCY_RHO and a["n_dates"] > 0
    # a planted duplicate drops the LATER-numbered feature, never the earlier one
    gi = dict(world["gi"])
    gi["sector"] = dict(gi["sector"])
    gi["sector"]["grp_hit_20"] = gi["sector"]["grp_rs_60"].copy()
    c = g.redundancy(gi, world["panel"])
    assert c["dropped"] == ["grp_hit_20"] and "grp_rs_60" in c["surviving"]
    assert len(g.column_map(c["surviving"])["G"]) == len(g.GROUP_FEATURES) - 1
    assert g.redundancy(gi, world["panel"]) == c


def test_the_group_date_rule_needs_all_eleven_sectors_with_twenty_five_members(world):
    gi = world["gi"]
    assert gi["group_date"].all() and (gi["counts"] >= g.MIN_SECTOR_MEMBERS).all()
    # 24 labelled members in one sector: that sector fails on every date, so no date is a group date
    sec = world["sec"].copy()
    members = np.flatnonzero(sec == len(g.SECTORS) - 1)
    sec[members[g.MIN_SECTOR_MEMBERS - 1:]] = -1
    short = g.group_inputs(world["closes"], world["observed"], world["panel"], sec, world["tier"], world["cur"])
    assert not short["group_date"].any()
    assert not short["sector_ok"][:, -1].any() and short["sector_ok"][:, :-1].all()
    data = g.assemble_group(world["panel"], world["inputs"], short, 20)
    assert data["n_dates"] == 0 and len(data["group_failures"]) > 0
    assert data["group_failures"][0]["sectors"] == [g.SECTORS[-1]]
    # exactly 25 is enough
    sec = world["sec"].copy()
    sec[members[g.MIN_SECTOR_MEMBERS:]] = -1
    ok = g.group_inputs(world["closes"], world["observed"], world["panel"], sec, world["tier"], world["cur"])
    assert ok["group_date"].any()


def test_bracket_ni_sets_ranks_zero_interactions_zero_and_adds_no_indicator(world, assembled):
    red, primary = assembled
    ni = g.assemble_group(world["panel"], world["inputs"], world["gi"], 20, bracket="NI", surviving=red["surviving"])
    assert ni["n_unlabelled"].sum() > 0 and primary["n_unlabelled"].sum() == 0
    assert ni["R"].shape[1] == primary["R"].shape[1] == len(g.COLUMNS)
    assert not any("unlabel" in c.lower() for c in g.COLUMNS)
    unl = ni["sec"] < 0
    zero_cols = _sector_level_columns() + [g.IDX[k] for k in g.INTERACTIONS]
    assert np.all(ni["R"][unl][:, zero_cols] == 0.0)
    assert np.all(ni["R"][~unl][:, [g.IDX[f"sector:{s}"] for s in g.SECTORS]].sum(axis=1) == 1.0)
    # labelled cases keep real ranks under the bracket, and the bracket scores
    assert np.any(ni["R"][~unl][:, g.IDX["grp_rs_60"]] != 0.0)
    cols = g.column_map(red["surviving"])
    s = g.summarise(g.score_group(ni, cols, g.BLOCKS, models=g.BRACKET_MODELS, fit_sector=False), 20, "test",
                    pairs=(("A", "Bstar"), ("I", "A")))
    assert s["n_dates"] > 0 and s["unlabelled_share"] > 0 and "A-Bstar" in s["pairs"]


def test_the_snapshot_for_a_confirmatory_date_is_the_earliest_with_label_asof_on_or_after_it():
    snaps = [{"label_asof": pd.Timestamp(d), "sha256": d} for d in ("2026-10-04", "2027-04-01", "2027-10-01")]
    fallback = snaps[0]
    assert g.choose_snapshot(pd.Timestamp("2026-11-15"), snaps, fallback)["sha256"] == "2027-04-01"
    assert g.choose_snapshot(pd.Timestamp("2027-04-01"), snaps, fallback)["sha256"] == "2027-04-01"
    assert g.choose_snapshot(pd.Timestamp("2027-04-02"), snaps, fallback)["sha256"] == "2027-10-01"
    assert g.choose_snapshot(pd.Timestamp("2026-10-03"), snaps, fallback)["sha256"] == "2026-10-04"
    assert g.choose_snapshot(pd.Timestamp("2028-01-01"), snaps, fallback)["sha256"] == fallback["sha256"]
    assert g.choose_snapshot(pd.Timestamp("2028-01-01"), list(reversed(snaps)), fallback)["sha256"] == fallback["sha256"]
    assert g.choose_snapshot(pd.Timestamp("2027-04-02"), list(reversed(snaps)), fallback)["sha256"] == "2027-10-01"


def test_the_embargo_drops_every_c1_label_exiting_after_the_cutoff(world):
    exits = pd.DatetimeIndex(["2026-06-01", "2026-06-02", "2026-06-03", "2026-07-01"])
    assert g.embargo_mask(exits).tolist() == [True, True, False, False]
    assert g.embargo_mask(exits, None).tolist() == [True] * 4
    assert g.EMBARGO_EXIT == "2026-06-02"
    cutoff = "2020-06-30"
    data = g.assemble_group(world["panel"], world["inputs"], world["gi"], 20, embargo=cutoff)
    index = world["panel"]["index"]
    assert (index[data["exit"]] <= pd.Timestamp(cutoff)).all()
    assert len(data["embargoed"]) > 0 and min(data["embargoed"]) > "2020-05-01"
    full = g.assemble_group(world["panel"], world["inputs"], world["gi"], 20, embargo=None)
    assert full["n_dates"] == data["n_dates"] + len(data["embargoed"])


# ---- the pieces the pre-registration fixes --------------------------------------------------------
def test_pins_match_the_committed_files():
    assert g.prereg_sha256() == g.PREREG_SHA256
    g.pinned_prereg()
    assert g._sha256(os.path.join(g._HERE, g.B2_RESULT_FILE)) == g.B2_RESULT_SHA256
    assert len(g.code_sha256()) == 64


def test_the_column_map_nests_and_b_is_b2s_fifty_regressors():
    cm = g.column_map()
    assert len(cm["B"]) == 50 == len(wf.columns(20)["B2"])
    assert cm["B"] == list(range(50)) and cm["Bstar"][:50] == cm["B"]
    assert len(cm["Bstar"]) == 62 and cm["A"] == cm["Bstar"] + [g.IDX[k] for k in g.GROUP_FEATURES]
    assert cm["I"] == cm["A"] + [g.IDX[k] for k in g.INTERACTIONS]
    assert cm["BstarD"] == cm["Bstar"] + [g.IDX[f"sector:{s}"] for s in g.SECTORS]
    assert set(cm["Bstar"]) - set(cm["SPLIT"]) == {g.IDX["c:ret_60d"], g.IDX["c:ret_120d"],
                                                    g.IDX["c2:ret_60d"], g.IDX["c2:ret_120d"]}
    assert set(cm["SPLIT"]) - set(cm["Bstar"]) == {g.IDX[p] for p in g.SPLIT_PARTS} | {g.IDX[f"{p}_sq"] for p in g.SPLIT_PARTS}
    assert len(g.COLUMNS) == len(set(g.COLUMNS)) == 91
    assert cm["G"] == [g.IDX[k] for k in g.GROUP_FEATURES]


def test_the_market_state_is_standardised_over_the_trailing_year():
    rng = np.random.default_rng(5)
    spy = np.exp(np.cumsum(rng.normal(0.0003, 0.01, 1200)))
    ms = g.market_state(spy)
    z = ms["z_spy_ret_60"]
    assert np.isnan(z[:60 + g.Z_WINDOW - 1]).all() and np.isfinite(z[60 + g.Z_WINDOW - 1:]).all()
    L = np.log(spy)
    x = pd.Series(L).diff(60)
    t = 900
    want = (x[t] - x[t - g.Z_WINDOW + 1:t + 1].mean()) / x[t - g.Z_WINDOW + 1:t + 1].std(ddof=0)
    assert abs(z[t] - want) < 1e-12
    assert ms["spy_ret_60_sign"][t] == np.sign(x[t])


def test_the_t_quantile_matches_tabulated_values():
    assert abs(g.t_quantile(0.975, 10) - 2.228139) < 1e-6
    assert abs(g.t_quantile(0.975, 47) - 2.011741) < 1e-6
    assert abs(g.t_quantile(0.95, 5) - 2.015048) < 1e-6
    assert abs(g.t_quantile(0.9975, 20) - 3.153401) < 1e-6


def test_the_noncentral_t_reduces_to_student_t_at_zero_and_matches_scipy_where_available():
    for df, t in ((10, 2.228139), (47, 2.011741), (20, 3.153401)):
        assert abs(g.nct_cdf(t, df, 0.0) - (1.0 - wf.student_t_sf(t, df))) < 1e-9
    assert abs(g.nct_cdf(0.0, 12, 1.3) - 0.5 * math.erfc(1.3 / math.sqrt(2.0))) < 1e-12
    assert abs(g.nct_cdf(2.0, 20, 3.0) - 0.1641010730) < 1e-9     # scipy.stats.nct.cdf(2.0, 20, 3.0)
    assert abs(g.nct_cdf(1.5, 47, 0.8) - 0.7529860545) < 1e-9
    assert abs(g.nct_cdf(-1.0, 15, 0.5) - 0.0721494262) < 1e-9
    stats = pytest.importorskip("scipy.stats")
    for t, df, d in ((2.3, 10, 2.3), (0.5, 30, -1.0), (3.0, 100, 2.9), (1.0, 9, 0.0)):
        assert abs(g.nct_cdf(t, df, d) - stats.nct.cdf(t, df, d)) < 1e-10


def test_the_power_rule_picks_the_smallest_read_size_and_declares_futility():
    # power rises with n and with the effect; delta* has a floor
    p = [g.power_at(n, 20, 0.012, 0.08) for n in g.N_READ_SET]
    assert p[0] < p[1] < p[2] and g.power_at(96, 20, 0.02, 0.08) > p[1]
    strong = g.n_read_for(0.10, 0.08, 20)
    assert strong["delta_star"] == 0.05 and strong["n_read"] == 48 and not strong["futile"]
    # with nu(48) = 5 degrees of freedom a 0.03 effect on a 0.08 series needs the 96-date read
    middling = g.n_read_for(0.06, 0.08, 20)
    assert middling["delta_star"] == 0.03 and middling["n_read"] == 96 and wf.ewc_df(48, 20, g.STEP) == 5
    assert g.n_read_for(0.01, 0.08, 20)["delta_star"] == g.DELTA_FLOOR
    weak = g.n_read_for(0.012, 0.17, 20)
    assert weak["futile"] and weak["n_read"] is None and weak["n_needed"] is not None and weak["n_needed"] > 144
    # the primary's read size is the family's; a carried h=60 cell needs n_read >= 96 to be live
    sel = {g.cell_key(g.CELLS[0]): {"carried": True, "cell": list(g.CELLS[0]), "mean": 0.10, "sigma_lr": 0.08},
           g.cell_key(g.CELLS[1]): {"carried": True, "cell": list(g.CELLS[1]), "mean": 0.10, "sigma_lr": 0.08},
           g.cell_key(g.CELLS[2]): {"carried": False, "cell": list(g.CELLS[2])}}
    pw = g.power_rule(sel)
    assert pw["n_read"] == 48 and pw["primary_futile"] is False
    dec = g.decide(sel, pw)
    assert dec["outcome"] == "C1-CARRY" and [s["step"] for s in dec["sequence"]] == [1]
    # a 96-date primary read lets the h=60 step in
    for k in (g.cell_key(g.CELLS[0]), g.cell_key(g.CELLS[1])):
        sel[k]["mean"] = 0.06
    pw = g.power_rule(sel)
    assert pw["n_read"] == 96 and [s["step"] for s in g.decide(sel, pw)["sequence"]] == [1, 2]
    sel[g.cell_key(g.CELLS[0])]["sigma_lr"] = 0.5
    pw = g.power_rule(sel)
    assert g.decide(sel, pw)["outcome"] == "C1-UNDERPOWERED"
    assert g.decide({k: {"carried": False, "cell": v["cell"]} for k, v in sel.items()}, {})["outcome"] == "C1-NULL"


def test_the_constants_block_is_a_closed_list():
    sel = {g.cell_key(g.CELLS[0]): {"carried": True, "cell": list(g.CELLS[0]), "mean": 0.06, "sigma_lr": 0.08}}
    pw = g.power_rule(sel)
    dec = g.decide(sel, pw)
    freeze = {"commit": "0" * 40, "committer_utc": "2026-10-04T07:00:00+00:00", "freeze_date": "2026-10-04",
              "interim_date": "2027-04-04", "first_confirmatory_rule": "x", "read_rule": "y"}
    block = g.constants_block(dec, pw, sel, g.GROUP_FEATURES, "a" * 64, freeze, "b" * 64)
    assert g.check_constants_block(block) == []
    assert set(block) == set(g.CONSTANTS_KEYS) and block["appended"] == []
    block["extra"] = 1
    assert g.check_constants_block(block) == ["unexpected key 'extra'"]
    del block["extra"]
    block["carried_cells"][g.cell_key(g.CELLS[0])]["tuned"] = 2
    assert any("unexpected ['tuned']" in b for b in g.check_constants_block(block))


def test_the_one_run_guard_refuses_a_second_run(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "_HERE", str(tmp_path))
    os.makedirs(tmp_path / "data")
    monkeypatch.setattr(g, "pinned_prereg", lambda: None)
    monkeypatch.setattr(g, "pinned_b2_result", lambda path=None: {})
    (tmp_path / g.RESULT_FILE).write_text("{}")
    with pytest.raises(tpp.HoldoutLocked):
        g.run(sector_snapshot="x")
    (tmp_path / g.RESULT_FILE).unlink()
    (tmp_path / g.ATTEMPT_FILE).write_text(json.dumps({"attempts": [{"started_utc": "t"}]}))
    with pytest.raises(tpp.HoldoutLocked):
        g.run(sector_snapshot="x")


def test_a_planted_sector_drift_is_credited_to_a_over_bstar_and_noise_is_not():
    outcomes = {}
    for signal in (0.0, 0.3):
        w = _build(seed=1, signal=signal)
        red = g.redundancy(w["gi"], w["panel"])
        cols = g.column_map(red["surviving"])
        data = g.assemble_group(w["panel"], w["inputs"], w["gi"], 20, surviving=red["surviving"])
        scored = g.score_group(data, cols, g.BLOCKS, models=("G", "B", "Bstar", "A", "I"))
        s = g.summarise(scored, 20, "test")
        outcomes[signal] = s["pairs"]["A-Bstar"]["ic"], s["pairs"]["G-0"]["ic"]
    ab0, g0 = outcomes[0.0]
    ab1, g1 = outcomes[0.3]
    assert ab1["mean"] > ab0["mean"] and g1["mean"] > g0["mean"]
    assert ab1["mean"] > 0.01 and ab1["p_one_sided"] < 0.05 and g1["mean"] > 0.02
    assert ab0["p_one_sided"] > 0.05


def test_the_freeze_is_the_oldest_commit_adding_the_pinned_document():
    info = g.freeze_info()
    assert len(info["commit"]) == 40 and info["committer_utc"].endswith("+00:00")
    freeze = pd.Timestamp(info["freeze_date"])
    assert pd.Timestamp(info["committer_utc"]).tz_convert("UTC").date() == freeze.date()
    assert pd.Timestamp(info["interim_date"]) == freeze + pd.Timedelta(days=g.INTERIM_DAYS)
    assert set(info) == {"commit", "committer_utc", "freeze_date", "interim_date",
                         "first_confirmatory_rule", "read_rule"}
    with pytest.raises(g.GroupRefused):
        g.freeze_info(os.path.join(g._HERE, "trend_persistence_group.py"))
