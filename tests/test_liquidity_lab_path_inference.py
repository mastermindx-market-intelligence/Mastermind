"""GLT T16 path inference: episode blocks, pointwise vs simultaneous bands, influence.

Named acceptance cases:
* C28 -- ``test_c28_forty_rows_from_four_shocks_report_at_most_four_episodes``
* C29 -- ``test_c29_simultaneous_band_contains_the_pointwise_band_at_every_horizon``
"""

from __future__ import annotations

import math
import sys
from datetime import date, datetime, time

import numpy as np
import pytest

from brain.liquidity_lab.contracts import TARGET_BY_ID
from brain.liquidity_lab.estimator import ForwardReturnObservation
from brain.liquidity_lab.path_inference import (
    InadequateBlocks,
    block_bootstrap_path,
    episode_blocks,
    episode_influence,
    incremental_skill,
    path_multiplicity,
)
from brain.liquidity_lab.validation import WalkForwardPrediction

FAMILY = "glt_composite"
GRID = (5, 20, 60)
PURGE = 60
SDU_HAC = (
    "StatisticalDependencyUnavailable: engine.validation.newey_west_tstat is required "
    "for incremental scoring"
)
SDU_FDR = "StatisticalDependencyUnavailable: engine.validation.benjamini_hochberg is required for W-LIQ.3 FDR"


def _bday(day: date, n: int) -> date:
    return np.busday_offset(day.isoformat(), n, roll="forward").astype(date)


def _rows(shock_id, detected, *, targets, horizons, value):
    anchor = _bday(detected, 1)
    out = []
    for target in targets:
        spec = TARGET_BY_ID[target]
        for h in horizons:
            out.append(
                ForwardReturnObservation(
                    shock_id=shock_id,
                    first_detected=datetime.combine(detected, time(21, 0)),
                    target_id=target,
                    asset_class=spec.asset_class,
                    hierarchy_parent=spec.hierarchy_parent,
                    shock_family=FAMILY,
                    shock_type="composite_z",
                    horizon_bdays=h,
                    anchor_session=anchor,
                    exit_session=_bday(anchor, h),
                    forward_return=value(h, target),
                    conditions={},
                )
            )
    return out


def _panel(n=30, *, spacing=70, seed=7, outlier=None):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        detected = _bday(date(2008, 1, 7), spacing * i)
        scale = 25.0 if outlier == i else 1.0
        rows += _rows(
            f"liq_{i:03d}",
            detected,
            targets=("spy", "qqq"),
            horizons=GRID,
            value=lambda h, t, s=scale: s * 0.003 * math.sqrt(h / 20) + float(rng.normal(0, 0.006)),
        )
    return rows


# ------------------------------------------------------------------------ C28
def test_c28_forty_rows_from_four_shocks_report_at_most_four_episodes():
    horizons = (5, 10, 20, 40, 60)
    starts = [date(2010, 3, 1), date(2010, 3, 15), date(2011, 6, 1), date(2012, 9, 3)]
    rows = []
    for i, start in enumerate(starts):
        rows += _rows(
            f"liq_c28_{i}",
            start,
            targets=("spy", "qqq"),
            horizons=horizons,
            value=lambda h, t, i=i: 0.001 * (i + 1) * h / 20,
        )
    assert len(rows) == 40
    blocks = episode_blocks(rows, purge_sessions=PURGE)
    assert blocks.n_rows == 40 and blocks.n_shocks == 4
    assert blocks.n_episodes_effective <= 4
    # Shocks 0 and 1 are 10 sessions apart: they share ONE block, never two confirmations.
    assert blocks.n_episodes_effective == 3
    assert blocks.blocks[0].shock_ids == ("liq_c28_0", "liq_c28_1")
    assert blocks.blocks[0].n_rows == 20
    boot = block_bootstrap_path(rows, horizons=horizons, purge_sessions=PURGE, n_draws=500)
    for band in (boot.pointwise, boot.simultaneous):
        assert band.n_rows == 40
        assert band.n_episodes_effective == 3 <= 4
        assert band.n_blocks == 3


# ------------------------------------------------------------------------ C29
def test_c29_simultaneous_band_contains_the_pointwise_band_at_every_horizon():
    rows = _panel()
    boot = block_bootstrap_path(rows, horizons=GRID, purge_sessions=PURGE, n_draws=2000, target_id="spy")
    pw, sim = boot.pointwise, boot.simultaneous
    assert (pw.kind, sim.kind) == ("pointwise", "simultaneous")
    assert pw is not sim and pw != sim
    assert sim.certifies_path and not pw.certifies_path
    assert pw.n_episodes_effective == sim.n_episodes_effective == 30
    assert pw.n_rows == 90
    for j, h in enumerate(GRID):
        assert sim.lower[j] <= pw.lower[j] <= boot.point[j] <= pw.upper[j] <= sim.upper[j], h
    assert sim.critical_values[0] >= max(pw.critical_values)
    assert any(s - p > 0 for s, p in zip(np.subtract(sim.upper, sim.lower), np.subtract(pw.upper, pw.lower)))


def test_bootstrap_is_deterministic_and_reports_its_method():
    rows = _panel()
    a = block_bootstrap_path(rows, horizons=GRID, purge_sessions=PURGE, n_draws=300, seed=3)
    b = block_bootstrap_path(rows, horizons=GRID, purge_sessions=PURGE, n_draws=300, seed=3)
    assert a.simultaneous == b.simultaneous
    assert a.pointwise.method == "episode_block_bootstrap_studentised"
    assert a.pointwise.n_blocks_by_horizon == (30, 30, 30)


def test_too_few_blocks_is_inadequate_not_a_band():
    rows = _rows("liq_only", date(2010, 3, 1), targets=("spy",), horizons=GRID, value=lambda h, t: 0.01)
    with pytest.raises(InadequateBlocks, match="n_episodes_effective=1"):
        block_bootstrap_path(rows, horizons=GRID, purge_sessions=PURGE)


def test_overlapping_shocks_travel_with_their_episode():
    rows = _panel(n=12, spacing=20)
    blocks = episode_blocks(rows, purge_sessions=PURGE)
    assert blocks.n_shocks == 12
    assert blocks.n_episodes_effective == 4  # 60-session purge over 20-session spacing
    assert sum(len(b.shock_ids) for b in blocks.blocks) == 12
    assert all(len(b.shock_ids) == 3 for b in blocks.blocks)


# ------------------------------------------------------------------- influence
def test_leave_one_episode_out_names_the_influential_episode():
    rows = _panel(n=20, outlier=7)
    influence = episode_influence(rows, horizons=GRID, purge_sessions=PURGE, primary_horizon=20)
    assert influence.most_influential_shocks == ("liq_007",)
    assert influence.n_episodes_effective == 20
    p = GRID.index(20)
    top = influence.loeo[influence.most_influential_block][p]
    assert abs(top) == max(abs(v[p]) for v in influence.loeo.values())
    assert top < 0  # removing the outlier lowers the mean path
    assert influence.max_episode_share[p] > 0.3
    assert set(influence.loera) == {str(y) for y in range(2008, 2014)}
    assert influence.era_concentration is not None and 0 < influence.era_concentration <= 1


def test_era_concentration_with_a_declared_era_map():
    rows = _panel(n=20)
    influence = episode_influence(
        rows,
        horizons=GRID,
        purge_sessions=PURGE,
        primary_horizon=20,
        era_of=lambda block: "pre2011" if block.anchor.year < 2011 else "post2011",
    )
    assert set(influence.loera) == {"pre2011", "post2011"}
    assert influence.most_influential_era in influence.loera


# ------------------------------------------------------ SDU: abstain, never a p
def _predictions(name, bias):
    out = []
    for i in range(12):
        anchor = _bday(date(2012, 1, 3), 70 * i)
        out.append(
            WalkForwardPrediction(
                split_index=i // 4,
                relation_id="rel",
                model_version=name,
                shock_id=f"liq_{i:03d}",
                target_id="spy",
                horizon_bdays=20,
                anchor_session=anchor,
                exit_session=_bday(anchor, 20),
                predicted_return=0.01 + bias,
                realized_return=0.01 + 0.002 * (i % 3),
                effective_n_at_fit=10,
            )
        )
    return out


def test_sdu_propagates_as_abstention_not_a_fabricated_p_value(monkeypatch):
    monkeypatch.setitem(sys.modules, "engine.validation", None)
    skill = incremental_skill(_predictions("cand", 0.0), _predictions("base", 0.005))
    assert skill["status"] == "abstained"
    assert skill["p_value"] is None and skill["mean_squared_error_improvement"] is None
    assert skill["abstention_reason"] == SDU_HAC
    fdr = path_multiplicity({"h5": 0.01, "h20": 0.02, "h60": 0.5}, alpha=0.1)
    assert fdr == {"status": "abstained", "abstention_reason": SDU_FDR, "adjusted": None}


def test_injected_judges_are_used_by_reference():
    def judge(values):
        return {"t": 3.0, "p": 0.004}

    def fdr(p_values, *, alpha):
        return {k: {"p_value": v, "rejected": v < alpha} for k, v in p_values.items()}

    skill = incremental_skill(_predictions("cand", 0.0), _predictions("base", 0.005), mean_test_fn=judge)
    assert skill["p_value"] == 0.004 and skill["abstention_reason"] is None
    assert skill["paired_keys"] == 12
    out = path_multiplicity({"h20": 0.01}, alpha=0.1, fdr_fn=fdr)
    assert out["status"] == "adjusted" and out["adjusted"]["h20"]["rejected"] is True
