"""Vectorized, holdout-fenced Trend Persistence research instrument.

Advisory research only: no live ranking, sizing, gates, buys or sells.

This is the measurement instrument for ``research/TREND_PERSISTENCE_PREREG_V1.md``. It owns
exactly three things and nothing else:

* a fast wide-panel computation of the features defined canonically in
  ``brain.trend_persistence`` (parity is pinned by tests, so that module stays the definition);
* leakage-safe forward labels on one global formation calendar, with a one-session entry lag
  and delisting-aware terminal prices;
* a development/holdout fence: the holdout cannot be scored without the hash of the committed
  pre-registration.

It never re-implements a judge. HAC inference and FDR control are ``engine.validation``'s
``newey_west_tstat`` and ``benjamini_hochberg``; the conditional IC reproduces
``engine.validation.incremental_ic`` semantics on rank-transformed inputs (parity pinned by
tests). The audited deep+delisted, sanitized, PIT S&P 1500 substrate is loaded through
``loop.factor_experiment`` unchanged.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any

import numpy as np
import pandas as pd

SCHEMA = 1

# ---- frozen design (mirrored in the pre-registration's machine-readable block) ----------
WINDOWS = (20, 60, 120)
MOMENTUM_WINDOWS = (20, 60, 120, 252)
HORIZONS = (5, 20, 60)
FORMATION_STEP = 5
ENTRY_LAG = 1
MIN_HISTORY = 252
VOL_WINDOW = 60
BETA_WINDOW = 252
SELECT_FLOOR = 5.0
MIN_NAMES_PER_DATE = 100
MIN_NAMES_PER_BUCKET = 20
N_BUCKETS = 5
N_BINS = 5
HOLDOUT_START = "2022-01-01"          # mirrors loop.factor_experiment.HOLDOUT_START (locked)
DEV_ERAS = (
    ("2003-01-01", "2006-12-31"), ("2007-01-01", "2010-12-31"), ("2011-01-01", "2014-12-31"),
    ("2015-01-01", "2018-12-31"), ("2019-01-01", "2021-12-31"),
)
MIN_DATES_PER_ERA = 8
BH_ALPHA = 0.10
IC_FLOOR_DEV = 0.010
IC_FLOOR_HOLDOUT = 0.005
THINNED_T_MIN = 2.0
ERA_AGREE_MIN = 4
BUCKET_AGREE_MIN = 4
HOLDOUT_P_ONE_SIDED = 0.05

FAMILIES = {
    "path_quality": ("efficiency", "signed_efficiency", "positive_day_fraction",
                     "directional_consistency"),
    "gain_retention": ("retained",),
    "drawdown_shape": ("max_drawdown", "distance_to_high", "sessions_since_high"),
}
MOMENTUM_CONTROLS = tuple(f"ret_{w}d" for w in MOMENTUM_WINDOWS)
CONTROLS = MOMENTUM_CONTROLS + (f"vol_{VOL_WINDOW}d", f"beta_{BETA_WINDOW}d")
ENDPOINTS = ("forward_rel", "forward_max_drawdown")
FEATURES = tuple(f"{base}_{w}d" for bases in FAMILIES.values() for base in bases for w in WINDOWS)

PREREG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "TREND_PERSISTENCE_PREREG_V1.md")


class HoldoutLocked(RuntimeError):
    """Raised when the holdout is requested without the committed pre-registration hash."""


def frozen_design() -> dict[str, Any]:
    """The design constants the pre-registration freezes (compared against it by tests)."""
    return {
        "windows": list(WINDOWS), "momentum_windows": list(MOMENTUM_WINDOWS),
        "horizons": list(HORIZONS), "formation_step": FORMATION_STEP, "entry_lag": ENTRY_LAG,
        "min_history": MIN_HISTORY, "vol_window": VOL_WINDOW, "beta_window": BETA_WINDOW,
        "select_floor": SELECT_FLOOR, "min_names_per_date": MIN_NAMES_PER_DATE,
        "min_names_per_bucket": MIN_NAMES_PER_BUCKET, "n_buckets": N_BUCKETS,
        "holdout_start": HOLDOUT_START, "dev_eras": [list(e) for e in DEV_ERAS],
        "min_dates_per_era": MIN_DATES_PER_ERA, "bh_alpha": BH_ALPHA,
        "ic_floor_dev": IC_FLOOR_DEV, "ic_floor_holdout": IC_FLOOR_HOLDOUT,
        "thinned_t_min": THINNED_T_MIN, "era_agree_min": ERA_AGREE_MIN,
        "bucket_agree_min": BUCKET_AGREE_MIN, "holdout_p_one_sided": HOLDOUT_P_ONE_SIDED,
        "controls": list(CONTROLS), "endpoints": list(ENDPOINTS), "features": list(FEATURES),
    }


def prereg_sha256(path: str | None = None) -> str | None:
    try:
        with open(path or PREREG_PATH, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def family_of(feature: str) -> str:
    base = feature.rsplit("_", 1)[0]
    for family, bases in FAMILIES.items():
        if base in bases:
            return family
    raise KeyError(feature)


# ---- wide-panel features -----------------------------------------------------------------
def _window_shape(P: np.ndarray, rows: np.ndarray, w: int, chunk: int = 48):
    """Drawdown shape of the (w+1)-price window ending at each row.

    Returns (max_drawdown, distance_to_high, sessions_since_high), NaN where the window holds
    any missing price. Chunked so the windowed copy stays a few hundred MB on a 3,000-name panel.
    """
    from numpy.lib.stride_tricks import sliding_window_view
    n_rows, n_cols = len(rows), P.shape[1]
    mdd = np.full((n_rows, n_cols), np.nan)
    dist = np.full((n_rows, n_cols), np.nan)
    since = np.full((n_rows, n_cols), np.nan)
    if n_rows == 0:
        return mdd, dist, since
    view = sliding_window_view(P, w + 1, axis=0)                  # (T - w, N, w + 1)
    for a in range(0, n_rows, chunk):
        win = view[rows[a:a + chunk] - w]                          # copy: (c, N, w + 1)
        ok = np.isfinite(win).all(axis=2)
        with np.errstate(invalid="ignore", divide="ignore"):
            high = np.maximum.accumulate(win, axis=2)
            peak = win.max(axis=2)
            m = (win / high - 1.0).min(axis=2)
            d = win[:, :, -1] / peak - 1.0
            s = np.argmax(win[:, :, ::-1] == peak[:, :, None], axis=2).astype(float)
        mdd[a:a + chunk] = np.where(ok, m, np.nan)
        dist[a:a + chunk] = np.where(ok, d, np.nan)
        since[a:a + chunk] = np.where(ok, s, np.nan)
    return mdd, dist, since


def compute_features(P: np.ndarray, spy: np.ndarray, rows: np.ndarray):
    """Features and controls at each formation row, using prices at or before that row only.

    P is (T, N) closes with NaN outside a name's listed life; spy is (T,). Returns
    (features, controls): dicts of (len(rows), N) arrays keyed by FEATURES / CONTROLS.
    """
    P = np.asarray(P, float)
    spy = np.asarray(spy, float)
    rows = np.asarray(rows, int)
    T, N = P.shape
    with np.errstate(invalid="ignore", divide="ignore"):
        L = np.log(np.where(P > 0, P, np.nan))
        lm = np.log(np.where(spy > 0, spy, np.nan))
    r = np.full((T, N), np.nan)
    r[1:] = L[1:] - L[:-1]
    rm = np.full(T, np.nan)
    rm[1:] = lm[1:] - lm[:-1]
    bad, badm = ~np.isfinite(r), ~np.isfinite(rm)
    rz, rmz = np.where(bad, 0.0, r), np.where(badm, 0.0, rm)

    c_bad = np.cumsum(bad, axis=0, dtype=np.int32)
    c_badm = np.cumsum(badm, dtype=np.int32)
    c_abs = np.cumsum(np.abs(rz), axis=0)
    c_pos = np.cumsum(rz > 0, axis=0, dtype=np.int32)
    c_neg = np.cumsum(rz < 0, axis=0, dtype=np.int32)
    c_up = np.cumsum(np.where(rz > 0, rz, 0.0), axis=0)
    c_r = np.cumsum(rz, axis=0)
    c_r2 = np.cumsum(rz * rz, axis=0)
    c_rm = np.cumsum(rmz)
    c_rm2 = np.cumsum(rmz * rmz)
    c_rrm = np.cumsum(rz * rmz[:, None], axis=0)

    def win(c, w):                      # sum over the w returns ending at each formation row
        return c[rows] - c[rows - w]

    feats: dict[str, np.ndarray] = {}
    ctrl: dict[str, np.ndarray] = {}
    with np.errstate(invalid="ignore", divide="ignore"):
        for w in MOMENTUM_WINDOWS:
            ok = win(c_bad, w) == 0
            ctrl[f"ret_{w}d"] = np.where(ok, P[rows] / P[rows - w] - 1.0, np.nan)
        for w in WINDOWS:
            ok = win(c_bad, w) == 0
            net = L[rows] - L[rows - w]
            gross = win(c_abs, w)
            pos = win(c_pos, w).astype(float)
            neg = win(c_neg, w).astype(float)
            ratio = np.full(net.shape, np.nan)
            np.divide(net, gross, out=ratio, where=ok & (gross > 0))
            feats[f"signed_efficiency_{w}d"] = np.clip(ratio, -1.0, 1.0)
            feats[f"efficiency_{w}d"] = np.clip(np.abs(ratio), 0.0, 1.0)
            feats[f"positive_day_fraction_{w}d"] = np.where(ok, pos / w, np.nan)
            agree = np.where(net > 0, pos, np.where(net < 0, neg, w - pos - neg))
            feats[f"directional_consistency_{w}d"] = np.where(ok, agree / w, np.nan)
            gross_up = np.expm1(win(c_up, w))
            retained = np.full(net.shape, np.nan)
            np.divide(P[rows] / P[rows - w] - 1.0, gross_up, out=retained,
                      where=ok & (gross_up > 0))
            feats[f"retained_{w}d"] = retained
            mdd, dist, since = _window_shape(P, rows, w)
            feats[f"max_drawdown_{w}d"] = mdd
            feats[f"distance_to_high_{w}d"] = dist
            feats[f"sessions_since_high_{w}d"] = since

        n = VOL_WINDOW
        s1, s2 = win(c_r, n), win(c_r2, n)
        var = (s2 - s1 * s1 / n) / (n - 1)
        ctrl[f"vol_{n}d"] = np.where(win(c_bad, n) == 0, np.sqrt(np.maximum(var, 0.0)), np.nan)

        n = BETA_WINDOW
        ok = (win(c_bad, n) == 0) & (win(c_badm, n) == 0)[:, None]
        sx, sm = win(c_r, n), win(c_rm, n)[:, None]
        cov = (win(c_rrm, n) - sx * sm / n) / (n - 1)
        varm = np.broadcast_to((win(c_rm2, n)[:, None] - sm * sm / n) / (n - 1), cov.shape)
        beta = np.full(cov.shape, np.nan)
        np.divide(cov, varm, out=beta, where=ok & (varm > 0))
        ctrl[f"beta_{n}d"] = beta
    return feats, ctrl


def compute_labels(P: np.ndarray, spy: np.ndarray, rows: np.ndarray, horizons=HORIZONS,
                   lag: int = ENTRY_LAG):
    """Forward labels entered ``lag`` sessions after formation and held ``h`` sessions.

    A name that stops trading inside the window keeps its last traded price to the exit
    (hold-to-last-trade, then cash) and is flagged, so the cross-section is never conditioned
    on surviving the forward window. Rows whose exit lies past the panel end are unobservable.
    """
    P = np.asarray(P, float)
    spy = np.asarray(spy, float)
    rows = np.asarray(rows, int)
    T, N = P.shape
    Pff = pd.DataFrame(P).ffill().to_numpy(float)          # extends past the LAST trade only
    out = {}
    for h in horizons:
        entry, exit_ = rows + lag, rows + lag + h
        obs = exit_ <= T - 1
        ret = np.full((len(rows), N), np.nan)
        rel = np.full((len(rows), N), np.nan)
        mdd = np.full((len(rows), N), np.nan)
        deli = np.zeros((len(rows), N), bool)
        ro = np.flatnonzero(obs)
        if len(ro):
            ee, xx = entry[ro], exit_[ro]
            with np.errstate(invalid="ignore", divide="ignore"):
                fr = Pff[xx] / Pff[ee] - 1.0
                mr = spy[xx] / spy[ee] - 1.0
            ret[ro] = fr
            rel[ro] = fr - mr[:, None]
            mdd[ro] = _window_shape(Pff, xx, h)[0]
            deli[ro] = ~np.isfinite(P[xx]) & np.isfinite(Pff[xx])
        out[int(h)] = {"forward_return": ret, "forward_rel": rel, "forward_max_drawdown": mdd,
                       "delisted_in_window": deli, "observable": obs, "exit_rows": exit_}
    return out


def membership_mask(index: pd.DatetimeIndex, names: list, mem: pd.DataFrame) -> np.ndarray:
    """PIT membership (T, N): member at t iff start <= t and (end is null or end > t).

    Same predicate as ``loop.factor_experiment.members_asof``, evaluated for every date at once;
    a ticker with several disjoint spans is the union of its spans.
    """
    col = {str(n): j for j, n in enumerate(names)}
    mask = np.zeros((len(index), len(names)), bool)
    starts = pd.to_datetime(mem["start_date"])
    ends = pd.to_datetime(mem["end_date"])
    for ticker, start, end in zip(mem["ticker"], starts, ends):
        j = col.get(str(ticker))
        if j is None or pd.isna(start):
            continue
        lo = int(index.searchsorted(start, side="left"))
        hi = len(index) if pd.isna(end) else int(index.searchsorted(end, side="left"))
        if hi > lo:
            mask[lo:hi, j] = True
    return mask


def build_panel(closes: pd.DataFrame, mem: pd.DataFrame, *, horizons=HORIZONS,
                step: int = FORMATION_STEP, lag: int = ENTRY_LAG,
                holdout_start: str = HOLDOUT_START) -> dict[str, Any]:
    """Assemble the PIT feature/label panel on one global formation calendar."""
    closes = closes.sort_index()
    index = pd.DatetimeIndex(closes.index)
    spy = closes["SPY"].to_numpy(float)
    names = [c for c in closes.columns if c != "SPY"]
    member = membership_mask(index, names, mem)
    keep = member.any(axis=0)
    names = [n for n, k in zip(names, keep) if k]
    member = member[:, keep]
    P = closes[names].to_numpy(float)
    rows = np.arange(MIN_HISTORY, len(index), max(1, int(step)))
    feats, ctrl = compute_features(P, spy, rows)
    labels = compute_labels(P, spy, rows, horizons, lag)
    with np.errstate(invalid="ignore"):
        eligible = member[rows] & np.isfinite(P[rows]) & (P[rows] >= SELECT_FLOOR)
    return {
        "index": index, "names": names, "rows": rows, "features": feats, "controls": ctrl,
        "labels": labels, "eligible": eligible, "step": int(step), "lag": int(lag),
        "horizons": tuple(int(h) for h in horizons),
        "holdout_start": pd.Timestamp(holdout_start),
    }


# ---- cross-sectional statistics ----------------------------------------------------------
def _rank(a: np.ndarray) -> np.ndarray:
    """Column-wise average ranks — pandas ``.rank()``, the method the frozen judge uses."""
    a = np.asarray(a, float)
    if a.ndim == 1:
        return pd.Series(a).rank().to_numpy(float)
    return pd.DataFrame(a).rank(axis=0).to_numpy(float)


def _corr(X: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Pearson correlation of every column of X (n, K) with every column of Y (n, E)."""
    Xc, Yc = X - X.mean(axis=0), Y - Y.mean(axis=0)
    den = np.sqrt((Xc * Xc).sum(axis=0))[:, None] * np.sqrt((Yc * Yc).sum(axis=0))[None, :]
    out = np.full(den.shape, np.nan)
    np.divide(Xc.T @ Yc, den, out=out, where=den > 0)
    return out


def semi_partial_rank_ic(X: np.ndarray, Z: np.ndarray, Y: np.ndarray):
    """Rank IC of each feature AFTER removing what the controls already explain.

    Feature and control columns are rank-transformed; each feature's ranks are residualised on
    an intercept plus the standardised control ranks; the IC is the Spearman correlation of that
    residual with the label. This is ``engine.validation.incremental_ic`` (cross_sectional_resid
    then rank_ic) applied to rank-transformed inputs. Returns (ic (K, E), residual ranks (n, K)).
    """
    Xr, Zr, Yr = _rank(X), _rank(Z), _rank(Y)
    sd = Zr.std(axis=0)
    sd[sd == 0] = 1.0
    A = np.column_stack([np.ones(len(Zr)), (Zr - Zr.mean(axis=0)) / sd])
    resid = Xr - A @ np.linalg.lstsq(A, Xr, rcond=None)[0]
    Rr = _rank(resid)
    return _corr(Rr, Yr), Rr


def sample_rows(panel: dict, horizon: int, sample: str) -> np.ndarray:
    """Formation positions belonging to a sample for one horizon.

    dev: the label's exit precedes the first holdout session (purged, so no dev label touches
    holdout prices). holdout: formation on or after the first holdout session.
    """
    lab = panel["labels"][int(horizon)]
    first_holdout = int(panel["index"].searchsorted(panel["holdout_start"], side="left"))
    if sample == "dev":
        return np.flatnonzero(lab["observable"] & (lab["exit_rows"] < first_holdout))
    if sample == "holdout":
        return np.flatnonzero(lab["observable"] & (panel["rows"] >= first_holdout))
    raise ValueError(f"unknown sample {sample!r}")


def _judges():
    from engine import validation as V
    return V


def _series_stats(V, dates, series, horizon: int, step: int, lag: int) -> dict[str, Any]:
    s = np.asarray(series, float)
    keep = np.isfinite(s)
    s, d = s[keep], np.asarray(dates)[keep]
    out: dict[str, Any] = {"n_dates": int(len(s)), "mean": None, "t_hac": None, "p_hac": None,
                           "hac_lags": None, "hit": None,
                           "thinned": {"n": 0, "mean": None, "t": None}, "era_means": []}
    if len(s) < 8:
        return out
    nw = V.newey_west_tstat(pd.Series(s), lags=max(4, 2 * math.ceil(horizon / step)))
    every = max(1, math.ceil((horizon + lag) / step))
    thin = s[::every]
    nwt = V.newey_west_tstat(pd.Series(thin), lags=2)
    eras = []
    for a, b in DEV_ERAS:
        sel = (d >= np.datetime64(a)) & (d <= np.datetime64(b))
        eras.append(float(s[sel].mean()) if int(sel.sum()) >= MIN_DATES_PER_ERA else None)
    out.update({
        "mean": float(s.mean()), "t_hac": nw["t"], "p_hac": nw["p"], "hac_lags": nw["lags"],
        "hit": float((s > 0).mean()),
        "thinned": {"n": int(len(thin)), "mean": float(thin.mean()) if len(thin) else None,
                    "t": nwt["t"]},
        "era_means": eras,
    })
    return out


def _same_sign(value, sign) -> bool:
    return value is not None and sign != 0 and float(np.sign(value)) == float(sign)


def score(panel: dict, *, sample: str = "dev", prereg_hash: str | None = None,
          confirm: dict[str, int] | None = None) -> dict[str, Any]:
    """Score the pre-registered tests on one sample.

    The holdout is refused unless ``prereg_hash`` equals the sha256 of the committed
    pre-registration; a holdout run confirms, and reports, only the dev survivors passed in
    ``confirm`` (test key -> expected sign), and does not run at all when there are none.
    """
    current = prereg_sha256()
    if sample == "holdout" and (not prereg_hash or prereg_hash != current):
        raise HoldoutLocked(
            "holdout scoring requires prereg_hash == sha256(TREND_PERSISTENCE_PREREG_V1.md)")
    if sample == "holdout" and not confirm:
        # nothing survived development: the holdout stays unspent for a later pre-registration
        return {"schema": SCHEMA, "status": "not_run", "sample": sample,
                "reason": "no_dev_survivors_holdout_unspent", "prereg_sha256": current}
    try:
        V = _judges()
    except Exception as exc:                                  # engine not importable
        return {"schema": SCHEMA, "status": "unavailable", "error": str(exc)}

    index, rows, step, lag = panel["index"], panel["rows"], panel["step"], panel["lag"]
    X_all = np.stack([panel["features"][f] for f in FEATURES], axis=2)       # (F, N, K)
    Z_all = np.stack([panel["controls"][c] for c in CONTROLS], axis=2)       # (F, N, C)
    n_mom = len(MOMENTUM_CONTROLS)
    K, E = len(FEATURES), len(ENDPOINTS)
    result: dict[str, Any] = {
        "schema": SCHEMA, "status": "scored", "sample": sample, "prereg_sha256": current,
        "design": frozen_design(), "coverage": {}, "tests": {},
    }
    pvals: dict[str, float] = {}

    for h in panel["horizons"]:
        lab = panel["labels"][h]
        sel = sample_rows(panel, h, sample)
        dates, n_names, n_deli, n_incomplete = [], [], [], []
        ext, mom, raw, drop = [], [], [], []
        buckets, bins = [], []
        for f in sel:
            Y = np.column_stack([lab[e][f] for e in ENDPOINTS])
            base = panel["eligible"][f] & np.isfinite(Y).all(axis=1)
            ok = base & np.isfinite(Z_all[f]).all(axis=1) & np.isfinite(X_all[f]).all(axis=1)
            n = int(ok.sum())
            if n < MIN_NAMES_PER_DATE:
                continue
            X, Z, Y = X_all[f][ok], Z_all[f][ok], Y[ok]
            deli = lab["delisted_in_window"][f][ok]
            ic_ext, Rr = semi_partial_rank_ic(X, Z, Y)
            ic_mom, _ = semi_partial_rank_ic(X, Z[:, :n_mom], Y)
            ic_drop = np.full((K, E), np.nan)
            if int((~deli).sum()) >= MIN_NAMES_PER_DATE:
                ic_drop, _ = semi_partial_rank_ic(X[~deli], Z[~deli], Y[~deli])
            # momentum buckets: equal-count groups of the mean rank of the momentum controls
            order = np.argsort(np.argsort(_rank(Z[:, :n_mom]).mean(axis=1), kind="stable"),
                               kind="stable")
            grp = np.minimum(order * N_BUCKETS // n, N_BUCKETS - 1)
            ic_b = np.full((N_BUCKETS, K, E), np.nan)
            for q in range(N_BUCKETS):
                g = grp == q
                if int(g.sum()) >= MIN_NAMES_PER_BUCKET:
                    ic_b[q], _ = semi_partial_rank_ic(X[g], Z[g], Y[g])
            # label means by quintile of the control-neutral feature rank (descriptive)
            which = np.minimum(((Rr - 1.0) * N_BINS // n).astype(int), N_BINS - 1)
            bm = np.full((N_BINS, K, E), np.nan)
            for k in range(K):
                cnt = np.bincount(which[:, k], minlength=N_BINS).astype(float)
                for e in range(E):
                    tot = np.bincount(which[:, k], weights=Y[:, e], minlength=N_BINS)
                    np.divide(tot, cnt, out=bm[:, k, e], where=cnt > 0)
            dates.append(index[rows[f]].to_datetime64())
            n_names.append(n)
            n_deli.append(int(deli.sum()))
            n_incomplete.append(int(base.sum()) - n)
            ext.append(ic_ext)
            mom.append(ic_mom)
            raw.append(_corr(_rank(X), _rank(Y)))
            drop.append(ic_drop)
            buckets.append(ic_b)
            bins.append(bm)

        result["coverage"][str(h)] = {
            "n_dates": len(dates),
            "first_date": str(dates[0])[:10] if dates else None,
            "last_date": str(dates[-1])[:10] if dates else None,
            "median_names": float(np.median(n_names)) if n_names else None,
            "delisted_label_fraction": (float(sum(n_deli) / max(1, sum(n_names)))
                                        if n_names else None),
            "incomplete_case_fraction": (
                float(sum(n_incomplete) / max(1, sum(n_names) + sum(n_incomplete)))
                if n_names else None),
        }
        if not dates:
            continue
        dates_a = np.asarray(dates)
        ext_a, mom_a, raw_a, drop_a = (np.asarray(a) for a in (ext, mom, raw, drop))
        bucket_a, bins_a = np.asarray(buckets), np.asarray(bins)
        for k, feature in enumerate(FEATURES):
            for e, endpoint in enumerate(ENDPOINTS):
                key = f"{feature}|{h}|{endpoint}"
                st = _series_stats(V, dates_a, ext_a[:, k, e], h, step, lag)
                with np.errstate(invalid="ignore"):
                    bucket_means = [
                        float(np.nanmean(bucket_a[:, q, k, e]))
                        if np.isfinite(bucket_a[:, q, k, e]).sum() >= MIN_DATES_PER_ERA else None
                        for q in range(N_BUCKETS)]
                    drop_mean = (float(np.nanmean(drop_a[:, k, e]))
                                 if np.isfinite(drop_a[:, k, e]).sum() >= 8 else None)
                    bin_means = [float(np.nanmean(bins_a[:, q, k, e])) for q in range(N_BINS)]
                st.update({
                    "feature": feature, "family": family_of(feature), "horizon_d": int(h),
                    "endpoint": endpoint,
                    "raw_mean": float(np.nanmean(raw_a[:, k, e])),
                    "momentum_only_mean": float(np.nanmean(mom_a[:, k, e])),
                    "bucket_means": bucket_means, "drop_mean": drop_mean,
                    "bin_means": bin_means,
                })
                result["tests"][key] = st
                if st["p_hac"] is not None:
                    pvals[key] = float(st["p_hac"])

    if sample == "dev":
        _apply_dev_gates(V, result, pvals)
    else:
        _apply_holdout_confirmation(V, result, confirm or {})
    return result


def _apply_dev_gates(V, result: dict, pvals: dict) -> None:
    bh = V.benjamini_hochberg(pvals, alpha=BH_ALPHA)
    survivors: dict[str, int] = {}
    for key, st in result["tests"].items():
        mean = st["mean"]
        sign = int(np.sign(mean)) if mean is not None else 0
        thin = st["thinned"]
        gates = {
            "g1_bh_fdr": bool(bh.get(key, {}).get("reject")),
            "g2_ic_floor": mean is not None and abs(mean) >= IC_FLOOR_DEV,
            "g3_thinned": (_same_sign(thin["mean"], sign) and thin["t"] is not None
                           and abs(thin["t"]) >= THINNED_T_MIN),
            "g4_eras": sum(_same_sign(m, sign) for m in st["era_means"]) >= ERA_AGREE_MIN,
            "g5_momentum_buckets": (sum(_same_sign(m, sign) for m in st["bucket_means"])
                                    >= BUCKET_AGREE_MIN),
            "g6_delisting_invariant": (_same_sign(st["drop_mean"], sign)
                                       and abs(st["drop_mean"]) >= IC_FLOOR_DEV),
        }
        st["q_bh"] = bh.get(key, {}).get("q")
        st["gates"] = gates
        st["advance_dev"] = all(gates.values())
        if st["advance_dev"]:
            survivors[key] = sign
    result["n_tests"] = len(result["tests"])
    result["survivors"] = survivors
    result["family_summary"] = _family_summary(result["tests"], "advance_dev")


def _apply_holdout_confirmation(V, result: dict, confirm: dict[str, int]) -> None:
    one_sided: dict[str, float] = {}
    for key, sign in confirm.items():
        st = result["tests"].get(key)
        if st is None or st["p_hac"] is None or st["mean"] is None:
            continue
        p = float(st["p_hac"])
        one_sided[key] = p / 2.0 if _same_sign(st["mean"], sign) else 1.0 - p / 2.0
    bh = V.benjamini_hochberg(one_sided, alpha=BH_ALPHA)
    confirmed = {}
    # only the pre-registered survivors are reported: holdout statistics for every other test
    # are discarded unread, so a later study cannot be steered by them
    result["tests"] = {k: st for k, st in result["tests"].items() if k in confirm}
    for key, st in result["tests"].items():
        p1 = one_sided.get(key)
        gates = {
            "h1_same_sign": _same_sign(st["mean"], confirm[key]),
            "h2_one_sided_p": p1 is not None and p1 <= HOLDOUT_P_ONE_SIDED,
            "h3_bh_fdr": bool(bh.get(key, {}).get("reject")),
            "h4_ic_floor": st["mean"] is not None and abs(st["mean"]) >= IC_FLOOR_HOLDOUT,
        }
        st["p_one_sided"] = p1
        st["holdout_gates"] = gates
        st["confirmed_holdout"] = all(gates.values())
        if st["confirmed_holdout"]:
            confirmed[key] = int(confirm[key])
    result["n_confirm_requested"] = len(confirm)
    result["confirmed"] = confirmed
    result["family_summary"] = _family_summary(result["tests"], "confirmed_holdout")


def _family_summary(tests: dict, flag: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for family in FAMILIES:
        for endpoint in ENDPOINTS:
            keys = [k for k, st in tests.items()
                    if st["family"] == family and st["endpoint"] == endpoint]
            passed = sorted(k for k in keys if tests[k].get(flag))
            out[f"{family}|{endpoint}"] = {"n_tests": len(keys), "n_passed": len(passed),
                                           "passed": passed}
    return out


# ---- audited substrate ---------------------------------------------------------------------
def _file_stamp(path: str) -> dict[str, Any]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                digest.update(block)
        return {"sha256_16": digest.hexdigest()[:16], "bytes": os.path.getsize(path),
                "mtime": pd.Timestamp(os.path.getmtime(path), unit="s").strftime("%Y-%m-%d")}
    except OSError as exc:
        return {"error": str(exc)}


def load_audited_panel(breadth_dir: str | None = None):
    """Load the deep+delisted, sanitized panel and PIT membership via loop.factor_experiment.

    ``breadth_dir`` (or TREND_PERSISTENCE_BREADTH_DIR) only relocates the three input files;
    the loader, the sanitizer and the membership predicate are the audited owner's, unchanged.
    """
    from loop import factor_experiment as fx
    root = breadth_dir or os.environ.get("TREND_PERSISTENCE_BREADTH_DIR")
    if root:
        fx.BREADTH = root
    closes, mem, _idx, hygiene = fx.load_panel()
    provenance = {
        "breadth_dir": fx.BREADTH, "hygiene": hygiene,
        "first_date": str(closes.index[0])[:10], "last_date": str(closes.index[-1])[:10],
        "n_sessions": int(len(closes)), "n_columns": int(closes.shape[1]),
        "files": {name: _file_stamp(os.path.join(fx.BREADTH, name)) for name in (
            "_closes_deep.parquet", "_closes_delisted.parquet", "sp1500_pit_membership.parquet")},
    }
    return closes, mem, provenance


def run(*, sample: str = "dev", breadth_dir: str | None = None, prereg_hash: str | None = None,
        confirm: dict[str, int] | None = None) -> dict[str, Any]:
    """End-to-end run on the audited substrate. Dev by default; the holdout stays fenced."""
    if sample == "holdout" and (not prereg_hash or prereg_hash != prereg_sha256()):
        raise HoldoutLocked(
            "holdout scoring requires prereg_hash == sha256(TREND_PERSISTENCE_PREREG_V1.md)")
    closes, mem, provenance = load_audited_panel(breadth_dir)
    if closes is None or closes.empty or "SPY" not in closes.columns:
        return {"schema": SCHEMA, "status": "unavailable",
                "reason": "audited_price_panel_missing"}
    panel = build_panel(closes, mem)
    out = score(panel, sample=sample, prereg_hash=prereg_hash, confirm=confirm)
    out.update({"universe": "sp1500_pit", "panel": "deep_plus_delisted_sanitized",
                "universe_names": len(panel["names"]), "provenance": provenance})
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", choices=("dev", "holdout"), default="dev")
    ap.add_argument("--breadth-dir")
    ap.add_argument("--prereg-hash", help="sha256 of the committed pre-registration (holdout)")
    ap.add_argument("--confirm", help="dev result JSON whose survivors the holdout confirms")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    confirm = None
    if args.confirm:
        with open(args.confirm) as fh:
            confirm = {k: int(v) for k, v in json.load(fh).get("survivors", {}).items()}
    out = run(sample=args.sample, breadth_dir=args.breadth_dir, prereg_hash=args.prereg_hash,
              confirm=confirm)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    print(json.dumps({k: out.get(k) for k in ("status", "sample", "n_tests", "coverage")},
                     default=str), flush=True)
    return 0 if out.get("status") in ("scored", "not_run") else 1


if __name__ == "__main__":
    raise SystemExit(main())
