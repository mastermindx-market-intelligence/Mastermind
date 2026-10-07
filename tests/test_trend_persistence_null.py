from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import pytest

from research import trend_persistence_null as null
from research import trend_persistence_panel as panel

KEY = "max_drawdown_60d|20|forward_max_drawdown"


def test_simulated_prices_are_reproducible_and_carry_no_drift():
    a = null.simulate(3, "clustered_leverage", n_names=60, n_sessions=800, start="2010-01-04")
    b = null.simulate(3, "clustered_leverage", n_names=60, n_sessions=800, start="2010-01-04")
    assert a.equals(b) and list(a.columns)[0] == "SPY" and a.shape == (800, 61)
    assert not a.equals(null.simulate(4, "clustered_leverage", n_names=60, n_sessions=800,
                                      start="2010-01-04"))
    r = np.log(a.drop(columns="SPY")).diff().iloc[1:]
    t_stat = r.mean() / (r.std() / np.sqrt(len(r)))          # zero-mean log returns
    assert float((t_stat.abs() > 3.0).mean()) < 0.05
    lag1 = float(r.corrwith(r.shift(1)).median())
    assert abs(lag1) < 0.03                                  # no return autocorrelation


def test_every_specification_ends_before_the_holdout_boundary():
    for start, n in ((null.LONG_START, null.LONG_SESSIONS),
                     (null.SHORT_START, null.SHORT_SESSIONS)):
        assert pd.bdate_range(start, periods=n)[-1] < pd.Timestamp(panel.HOLDOUT_START)
    late = null.simulate(1, "same_vol", n_names=20, n_sessions=400, start="2021-01-04")
    with pytest.raises(ValueError, match="before the holdout boundary"):
        null.score_simulated(late)


def test_volatility_clusters_only_where_the_specification_says_so():
    flat = null.stylized_facts(null.simulate(5, "fixed_vol", n_names=80, n_sessions=1500))
    clustered = null.stylized_facts(null.simulate(5, "clustered", n_names=80, n_sessions=1500))
    skewed = null.stylized_facts(
        null.simulate(5, "clustered_leverage", n_names=80, n_sessions=1500))
    assert abs(flat["abs_autocorr"]["5"]) < 0.03
    assert clustered["abs_autocorr"]["5"] > 0.10
    assert skewed["leverage"] < clustered["leverage"] - 0.01
    assert flat["daily_sd"][0] < flat["daily_sd"][1] < flat["daily_sd"][2]
    # with one volatility for every stock, only the market beta still spreads them
    same = null.stylized_facts(null.simulate(5, "same_vol", n_names=80, n_sessions=1500))
    assert same["daily_sd"][2] / same["daily_sd"][0] < 1.3 < \
        flat["daily_sd"][2] / flat["daily_sd"][0]


def test_identical_volatility_gives_nothing_and_unequal_volatility_gives_the_artefact():
    """The instrument is unbiased when stocks do not differ, and is not when they do."""
    pytest.importorskip("engine.validation")
    kwargs = {"n_names": 300, "n_sessions": 1500, "start": null.SHORT_START}
    same = null.score_simulated(null.simulate(21, "same_vol", **kwargs))
    fixed = null.score_simulated(null.simulate(21, "fixed_vol", **kwargs))
    assert same["status"] == fixed["status"] == "scored" and len(fixed["tests"]) == 72
    assert abs(same["tests"][KEY]["mean"]) < 0.012
    # constant per-stock volatility, independent Gaussian returns, no persistence of any kind:
    assert fixed["tests"][KEY]["mean"] > 0.008
    assert fixed["tests"][KEY]["raw_mean"] > 0.15            # all of it is volatility


def test_confirmation_applies_the_holdout_gates():
    pytest.importorskip("engine.validation")
    result = {"tests": {
        "a": {"mean": 0.02, "p_hac": 0.001}, "b": {"mean": -0.02, "p_hac": 0.001},
        "c": {"mean": 0.004, "p_hac": 0.001}, "d": {"mean": 0.02, "p_hac": 0.5},
        "e": {"mean": None, "p_hac": None}}}
    got = null.confirm(result, {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1})
    assert got == {"a": True, "b": False, "c": False, "d": False, "e": False}
    assert null.confirm(result, {"b": -1}) == {"b": True}
    assert null.confirm(result, {}) == {}


def test_committed_benchmark_matches_the_module_and_the_holdout_result():
    path = os.path.join(os.path.dirname(null.__file__), "data", "trend_persistence_v2_null.json")
    with open(path) as fh:
        out = json.load(fh)
    assert out["schema"] == null.SCHEMA and out["design_id"] == "v2"
    assert out["prereg_sha256"] == panel.pinned_prereg("v2")
    assert out["spec_definitions"] == json.loads(json.dumps(
        {k: dict(v) for k, v in null.SPECS.items()}))
    assert out["seeds"] == list(null.SEEDS) and out["n_names"] == null.N_NAMES
    with open(os.path.join(os.path.dirname(path), "trend_persistence_v2_holdout.json")) as fh:
        confirmed = {k for k, st in json.load(fh)["tests"].items() if st["confirmed_holdout"]}
    assert out["real_confirmed_tests"] == len(confirmed) == 29
    for spec, summary in out["specs"].items():
        assert summary["n_seeds"] == len(null.SEEDS)
        assert len(summary["per_test"]) == 72
        assert all(0 <= n <= 29 for n in summary["real_keys_confirmed"])
    # the sanity specification finds nothing; the others do
    assert max(out["specs"]["same_vol"]["dev_survivors_of_72"]) <= 2
    assert min(out["specs"]["clustered_leverage"]["real_keys_confirmed"]) >= 5
