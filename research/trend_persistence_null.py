"""Trend Persistence — volatility-only null benchmark.

The V2 tests ask whether a feature's rank still lines up with forward maximum drawdown after
eleven momentum, volatility and beta ranks are removed. This module asks what those same tests
return on simulated prices that have volatility and nothing else: zero-mean returns, no return
autocorrelation, no trend persistence of any kind.

Every simulated panel is scored by the V2 instrument's own code, on its development path.
No real label is scored. The only real data this module can read is development-era prices,
and only to compare how volatility clusters in them with how it clusters in the simulation.
All simulated dates end before 2022, so the instrument treats them as development data and
its holdout fence is not involved.

Advisory research only.
"""
from __future__ import annotations

import json
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

from research import trend_persistence_panel as tpp

SCHEMA = 1
DESIGN = "v2"
N_NAMES = 500
BURN_IN = 500
LONG_START, LONG_SESSIONS = "2002-01-02", 4900      # ends in 2020: every development era
SHORT_START, SHORT_SESSIONS = "2008-01-01", 1300    # about as many dates as the real holdout
SEEDS = (11, 12, 13, 14, 15)
SHORT_SEED_OFFSET = 1000                            # the second panel is an independent draw

STOCK_VOL_MEDIAN = 0.018                            # per day
STOCK_VOL_LOG_SD = 0.40
MARKET_VOL_MEDIAN = 0.010
BETA_MEAN, BETA_SD = 1.0, 0.30
T_DF = 5
JUMP_EVERY = 63                                     # sessions between scheduled jumps

# What each specification switches on. Volatility is the only thing that varies in any of them.
_CLUSTER = {"phi_s": 0.995, "sd_s": 0.45, "fast": (0.90, 0.30), "phi_m": 0.995, "sd_m": 0.55}
SPECS: Mapping[str, Mapping[str, Any]] = {
    # every stock has the same constant volatility: the tests should find nothing
    "same_vol": {"gauss": True, "same": True},
    # each stock has its own constant volatility; independent Gaussian returns
    "fixed_vol": {"gauss": True},
    # volatility clusters (a slow and a fast component), fat-tailed returns
    "clustered": dict(_CLUSTER),
    # ... and a negative return raises later volatility
    "clustered_leverage": {**_CLUSTER, "lev": 0.05, "lev_m": 0.08},
    # ... and every stock has a scheduled jump each quarter, of its own typical size
    "clustered_leverage_jumps": {**_CLUSTER, "lev": 0.05, "lev_m": 0.08, "jump": (3.0, 0.5)},
}
LEVERAGE_CENTRE = 0.40                              # roughly E[max(-z, 0)]


def _shocks(rng, shape, gauss: bool) -> np.ndarray:
    if gauss:
        return rng.standard_normal(shape)
    return rng.standard_t(T_DF, size=shape) / math.sqrt(T_DF / (T_DF - 2))


def simulate(seed: int, spec: str, *, n_names: int = N_NAMES, n_sessions: int = LONG_SESSIONS,
             start: str = LONG_START, burn: int = BURN_IN) -> pd.DataFrame:
    """Closes for ``n_names`` stocks and SPY (first column). Log returns have zero mean."""
    m = SPECS[spec]
    rng = np.random.default_rng(seed)
    total = n_sessions + burn
    gauss = bool(m.get("gauss"))
    level = STOCK_VOL_MEDIAN * np.exp(rng.normal(0.0, STOCK_VOL_LOG_SD, n_names))
    if m.get("same"):
        level = np.full(n_names, STOCK_VOL_MEDIAN)
    beta = rng.normal(BETA_MEAN, BETA_SD, n_names)

    phi_m, sd_m = m.get("phi_m", 0.0), m.get("sd_m", 0.0)
    step_m = sd_m * math.sqrt(1.0 - phi_m ** 2)
    shock_m = _shocks(rng, total, gauss)
    market = np.zeros(total)
    h_m = 0.0
    for t in range(1, total):
        h_m = phi_m * h_m + step_m * rng.standard_normal()
        if m.get("lev_m"):
            h_m += m["lev_m"] * (max(-shock_m[t - 1], 0.0) - LEVERAGE_CENTRE)
        market[t] = MARKET_VOL_MEDIAN * math.exp(h_m) * shock_m[t]

    phi_s, sd_s = m.get("phi_s", 0.0), m.get("sd_s", 0.0)
    step_s = sd_s * math.sqrt(1.0 - phi_s ** 2)
    fast = m.get("fast")
    lev = m.get("lev", 0.0)
    h = rng.normal(0.0, sd_s, n_names) if sd_s else np.zeros(n_names)
    h_fast = np.zeros(n_names)
    own = np.zeros((total, n_names))
    z_prev = np.zeros(n_names)
    centre = 0.5 * (sd_s ** 2 + (fast[1] ** 2 if fast else 0.0))
    for t in range(total):
        if sd_s:
            h = phi_s * h + step_s * rng.standard_normal(n_names)
        if lev:
            h = h + lev * (np.maximum(-z_prev, 0.0) - LEVERAGE_CENTRE)
        if fast:
            h_fast = fast[0] * h_fast + fast[1] * math.sqrt(1.0 - fast[0] ** 2) \
                * rng.standard_normal(n_names)
        z = _shocks(rng, n_names, gauss)
        own[t] = level * np.exp(h + h_fast - centre) * z
        z_prev = z
    r = beta[None, :] * market[:, None] + own
    if m.get("jump"):
        size = m["jump"][0] * np.exp(rng.normal(0.0, m["jump"][1], n_names)) * level
        phase = rng.integers(0, JUMP_EVERY, n_names)
        hit = ((np.arange(total)[:, None] - phase[None, :]) % JUMP_EVERY) == 0
        r = r + hit * size[None, :] * _shocks(rng, (total, n_names), gauss)
    r, market = r[burn:], market[burn:]
    index = pd.bdate_range(start, periods=n_sessions)
    closes = pd.DataFrame(100.0 * np.exp(np.cumsum(r, axis=0)), index=index,
                          columns=[f"S{i:03d}" for i in range(n_names)])
    closes.insert(0, "SPY", 300.0 * np.exp(np.cumsum(market)))
    return closes


def stylized_facts(closes: pd.DataFrame, lags=(1, 5, 20, 60)) -> dict[str, Any]:
    """Price-only facts used to judge a specification: how volatility clusters and skews.

    ``abs_autocorr`` is the median over stocks of the autocorrelation of absolute daily
    returns; ``leverage`` is the median correlation of a return with the next day's absolute
    return; ``daily_sd`` gives the 10th, 50th and 90th percentile of per-stock volatility.
    """
    r = np.log(closes.drop(columns="SPY", errors="ignore")).diff().iloc[1:]
    a = r.abs()
    out: dict[str, Any] = {"abs_autocorr": {}}
    for lag in lags:
        out["abs_autocorr"][str(lag)] = float(a.corrwith(a.shift(lag)).median())
    out["leverage"] = float(r.shift(1).corrwith(a).median())
    out["daily_sd"] = [float(v) for v in r.std().quantile([0.10, 0.50, 0.90])]
    return out


def score_simulated(closes: pd.DataFrame) -> dict[str, Any]:
    """Score a simulated panel with the V2 instrument, development path, V2's own settings."""
    if closes.index[-1] >= pd.Timestamp(tpp.HOLDOUT_START):
        raise ValueError("simulated panels must end before the holdout boundary")
    names = [c for c in closes.columns if c != "SPY"]
    mem = pd.DataFrame({"ticker": names, "start_date": closes.index[0],
                        "end_date": pd.Series([pd.NaT] * len(names), dtype="datetime64[ns]")})
    printed = pd.DataFrame(np.nan, index=closes.index, columns=names)   # as in real development
    panel = tpp.build_panel(closes, mem, observed=closes[names].notna(), printed=printed)
    return tpp.score(panel, design=DESIGN, sample="dev")


def confirm(result: dict, signs: Mapping[str, int]) -> dict[str, bool]:
    """V2's holdout gates H1–H4 applied to a scored simulated panel, for the tests in ``signs``."""
    V = tpp._judges()
    one_sided: dict[str, float] = {}
    for key, sign in signs.items():
        st = result["tests"][key]
        if st["p_hac"] is None or st["mean"] is None:
            one_sided[key] = 1.0
            continue
        p = float(st["p_hac"])
        one_sided[key] = p / 2.0 if tpp._same_sign(st["mean"], sign) else 1.0 - p / 2.0
    bh = V.benjamini_hochberg(one_sided, alpha=tpp.BH_ALPHA) if one_sided else {}
    out = {}
    for key, sign in signs.items():
        mean = result["tests"][key]["mean"]
        out[key] = bool(tpp._same_sign(mean, sign)
                        and one_sided[key] <= tpp.HOLDOUT_P_ONE_SIDED
                        and bh.get(key, {}).get("reject")
                        and mean is not None and abs(mean) >= tpp.IC_FLOOR_HOLDOUT)
    return out


def run_seed(spec: str, seed: int, real_signs: Mapping[str, int], *,
             n_names: int = N_NAMES, long_sessions: int = LONG_SESSIONS,
             short_sessions: int = SHORT_SESSIONS) -> dict[str, Any]:
    """One simulated market, taken through the whole V2 procedure.

    A long panel goes through the seven development gates. A second, independent panel of about
    the real holdout's length is then asked to confirm (a) the simulated market's own survivors
    and (b) the tests the real data confirmed, with the real development signs.
    """
    long_result = score_simulated(simulate(seed, spec, n_names=n_names,
                                           n_sessions=long_sessions, start=LONG_START))
    short_result = score_simulated(simulate(seed + SHORT_SEED_OFFSET, spec, n_names=n_names,
                                            n_sessions=short_sessions, start=SHORT_START))
    own = {str(k): int(v) for k, v in long_result["survivors"].items()}
    own_confirmed = confirm(short_result, own)
    real_confirmed = confirm(short_result, real_signs)
    return {
        "seed": int(seed),
        "dev_survivors": sorted(own),
        "own_confirmed": sorted(k for k, v in own_confirmed.items() if v),
        "real_keys_confirmed": sorted(k for k, v in real_confirmed.items() if v),
        "ic_long": {k: st["mean"] for k, st in long_result["tests"].items()},
        "ic_short": {k: st["mean"] for k, st in short_result["tests"].items()},
        "bins_short": {k: short_result["tests"][k]["bin_means"] for k in real_signs},
        "n_dates_long": {h: c["n_dates"] for h, c in long_result["coverage"].items()},
        "n_dates_short": {h: c["n_dates"] for h, c in short_result["coverage"].items()},
    }


def summarise(runs: list[dict], keys) -> dict[str, Any]:
    def stats(values):
        v = np.asarray([x for x in values if x is not None], float)
        if not len(v):
            return {"mean": None, "sd": None, "n": 0}
        return {"mean": float(v.mean()), "sd": float(v.std(ddof=1)) if len(v) > 1 else None,
                "n": int(len(v))}
    per_key = {}
    for key in keys:
        per_key[key] = {
            "long": stats([r["ic_long"].get(key) for r in runs]),
            "short": stats([r["ic_short"].get(key) for r in runs]),
            "dev_survivor_in": sum(key in r["dev_survivors"] for r in runs),
            "confirmed_in": sum(key in r["real_keys_confirmed"] for r in runs),
        }
        bins = [r["bins_short"][key] for r in runs if key in r["bins_short"]]
        if bins:
            per_key[key]["bins_short"] = [float(v) for v in np.mean(np.asarray(bins, float),
                                                                    axis=0)]
    return {
        "n_seeds": len(runs),
        "dev_survivors_of_72": [len(r["dev_survivors"]) for r in runs],
        "own_confirmed": [len(r["own_confirmed"]) for r in runs],
        "real_keys_confirmed": [len(r["real_keys_confirmed"]) for r in runs],
        "per_test": per_key,
    }


def run(holdout_result: dict, *, specs=tuple(SPECS), seeds=SEEDS, n_names: int = N_NAMES,
        long_sessions: int = LONG_SESSIONS, short_sessions: int = SHORT_SESSIONS,
        log=None) -> dict[str, Any]:
    """The whole benchmark. ``holdout_result`` supplies only which tests were confirmed, and
    their development signs; no real price or label is read."""
    signs = {str(k): int(st["dev_sign"]) for k, st in holdout_result["tests"].items()
             if st.get("confirmed_holdout")}
    keys = [f"{f}|{h}|forward_max_drawdown" for f in tpp.FEATURES for h in tpp.HORIZONS]
    out: dict[str, Any] = {
        "schema": SCHEMA, "design_id": DESIGN, "prereg_sha256": tpp.pinned_prereg(DESIGN),
        "n_names": int(n_names), "long": [LONG_START, int(long_sessions)],
        "short": [SHORT_START, int(short_sessions)], "seeds": [int(s) for s in seeds],
        "spec_definitions": {k: dict(v) for k, v in SPECS.items()},
        "constants": {"stock_vol_median": STOCK_VOL_MEDIAN, "stock_vol_log_sd": STOCK_VOL_LOG_SD,
                      "market_vol_median": MARKET_VOL_MEDIAN, "beta": [BETA_MEAN, BETA_SD],
                      "t_df": T_DF, "jump_every": JUMP_EVERY, "burn_in": BURN_IN,
                      "leverage_centre": LEVERAGE_CENTRE},
        "real_confirmed_tests": len(signs), "specs": {},
    }
    for spec in specs:
        runs = []
        for seed in seeds:
            runs.append(run_seed(spec, seed, signs, n_names=n_names,
                                 long_sessions=long_sessions, short_sessions=short_sessions))
            if log:
                log(f"{spec} seed {seed}: {len(runs[-1]['dev_survivors'])} of 72 pass development, "
                    f"{len(runs[-1]['real_keys_confirmed'])} of {len(signs)} real tests confirm")
        summary = summarise(runs, keys)
        summary["stylized_facts"] = stylized_facts(
            simulate(seeds[0], spec, n_names=n_names, n_sessions=long_sessions))
        out["specs"][spec] = summary
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--holdout-result", required=True,
                    help="the committed V2 holdout result (read for test names and signs only)")
    ap.add_argument("--real-closes", help="optional parquet of development-era closes: adds the "
                                          "real stylized facts next to the simulated ones")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    with open(args.holdout_result) as fh:
        holdout = json.load(fh)
    out = run(holdout, log=lambda s: print(s, flush=True))
    if args.real_closes:
        real = pd.read_parquet(args.real_closes)
        real.index = pd.to_datetime(real.index)
        real = real[(real.index >= "2003-01-01") & (real.index < tpp.HOLDOUT_START)]
        real = real.loc[:, real.notna().mean() > 0.95].iloc[:, :400]
        out["real_stylized_facts"] = {"window": ["2003-01-01", tpp.HOLDOUT_START],
                                      "n_names": int(real.shape[1]), **stylized_facts(real)}
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
