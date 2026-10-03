"""Vectorized, holdout-fenced Trend Persistence research instrument.

Advisory research only: no live ranking, sizing, gates, buys or sells.

This is the measurement instrument for the Trend Persistence pre-registrations
(``research/TREND_PERSISTENCE_PREREG_V1.md`` and ``..._V2.md``). It owns exactly three things:

* a fast wide-panel computation of the features defined canonically in
  ``brain.trend_persistence`` (parity is pinned by tests, so that module stays the definition);
* leakage-safe forward labels on one global formation calendar, with a one-session entry lag
  and delisting-aware terminal prices;
* a development/holdout fence. Each design pins the sha256 of its committed pre-registration;
  nothing is scored if the file no longer hashes to the pin, the sample boundaries are module
  constants no caller can move, and a holdout run re-derives the development survivors itself
  and scores those tests and no others.

It never re-implements a judge. HAC inference and FDR control are ``engine.validation``'s
``newey_west_tstat`` and ``benjamini_hochberg``; the conditional IC reproduces
``engine.validation.incremental_ic`` semantics on rank-transformed inputs (parity pinned by
tests).

Designs. ``v1`` is the first pre-registration exactly as frozen; its development sample has
been scored and its holdout is closed for good (an independent review found that V1 lets the
audited sanitizer's gap fills, which depend on later prices, decide eligibility, and V1
controls volatility with a single 60-session window). ``v2`` is the confirmatory design for
the downside-risk claim: quoted-price mask, multi-window volatility controls, and a holdout
universe repaired from the whole-market store (``research/trend_persistence_substrate.py``).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np
import pandas as pd

SCHEMA = 2

# ---- frozen design (mirrored in the pre-registrations' machine-readable blocks) -----------
WINDOWS = (20, 60, 120)
MOMENTUM_WINDOWS = (20, 60, 120, 252)
HORIZONS = (5, 20, 60)
FORMATION_STEP = 5
ENTRY_LAG = 1
MIN_HISTORY = 252
VOL_WINDOW = 60
BETA_WINDOW = 252
RISK_WINDOWS = (20, 60, 120, 252)     # v2: realized volatility at four spans
DOWNSIDE_WINDOWS = (60, 252)          # v2: downside semi-deviation at two spans
SELECT_FLOOR = 5.0
MIN_NAMES_PER_DATE = 100
MIN_NAMES_PER_BUCKET = 20
N_BUCKETS = 5
N_BINS = 5
MIN_DATES_FOR_MEAN = 8                # a per-date series shorter than this has no mean
HOLDOUT_START = "2022-01-01"          # mirrors loop.factor_experiment.HOLDOUT_START (locked)
HOLDOUT_FORMATION_START_V2 = "2022-07-06"   # first formation date with 252 store sessions
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
RISK_CONTROLS = (tuple(f"vol_{w}d" for w in RISK_WINDOWS)
                 + tuple(f"downvol_{w}d" for w in DOWNSIDE_WINDOWS))
CONTROLS_V2 = MOMENTUM_CONTROLS + RISK_CONTROLS + (f"beta_{BETA_WINDOW}d",)
ENDPOINTS = ("forward_rel", "forward_max_drawdown")
FEATURES = tuple(f"{base}_{w}d" for bases in FAMILIES.values() for base in bases for w in WINDOWS)

_HERE = os.path.dirname(os.path.abspath(__file__))


@dataclass(frozen=True)
class Design:
    """Everything that differs between pre-registrations. Instances are module constants."""
    id: str
    prereg_file: str
    prereg_sha256: str | None            # the committed file must hash to exactly this
    controls: tuple
    endpoints: tuple
    holdout_formation_start: str         # first formation date of the holdout sample
    observed_mask: bool                  # only quoted prices decide eligibility and features
    printed_floor: bool                  # price thresholds are tested on the close as printed
    risk_bucket_gate: bool               # G7: same sign across volatility quintiles
    substrate: str                       # "audited" | "repaired"
    holdout_open: bool                   # False: this design's holdout is never scored


DESIGNS: Mapping[str, Design] = MappingProxyType({
    "v1": Design(
        id="v1", prereg_file="TREND_PERSISTENCE_PREREG_V1.md",
        prereg_sha256="5edc15d6482668cde5bfd13485811d20e3ef22d125658e4f89bc11d6ed64aa05",
        controls=CONTROLS, endpoints=ENDPOINTS, holdout_formation_start=HOLDOUT_START,
        observed_mask=False, printed_floor=False, risk_bucket_gate=False, substrate="audited",
        holdout_open=False),
    "v2": Design(
        id="v2", prereg_file="TREND_PERSISTENCE_PREREG_V2.md",
        prereg_sha256="2882865d02ad75a6db78a292daae1a8391bf7f876f615234d063cb455b782d17",
        controls=CONTROLS_V2, endpoints=("forward_max_drawdown",),
        holdout_formation_start=HOLDOUT_FORMATION_START_V2,
        observed_mask=True, printed_floor=True, risk_bucket_gate=True, substrate="repaired",
        holdout_open=True),
})


def design_of(design: "str | Design") -> Design:
    if isinstance(design, Design):
        if DESIGNS.get(design.id) is not design:
            raise KeyError("unregistered design")
        return design
    return DESIGNS[str(design)]


class HoldoutLocked(RuntimeError):
    """Raised when the holdout is requested without everything the pre-registration demands."""


class PreregDrift(RuntimeError):
    """Raised when a pre-registration file no longer hashes to the value pinned in code."""


def frozen_design(design: "str | Design" = "v1") -> dict[str, Any]:
    """The design constants a pre-registration freezes (compared against it by tests)."""
    d = design_of(design)
    out = {
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
        "controls": list(d.controls), "endpoints": list(d.endpoints), "features": list(FEATURES),
    }
    if d.id != "v1":
        del out["vol_window"]
        out.update({
            "design": d.id, "risk_windows": list(RISK_WINDOWS),
            "downside_windows": list(DOWNSIDE_WINDOWS), "risk_controls": list(RISK_CONTROLS),
            "holdout_formation_start": d.holdout_formation_start,
            "observed_mask": d.observed_mask, "printed_floor": d.printed_floor,
            "risk_bucket_gate": d.risk_bucket_gate,
            "substrate": d.substrate, "n_bins": N_BINS,
            "min_dates_for_mean": MIN_DATES_FOR_MEAN, "thinning_phase": 0,
        })
    return out


def prereg_path(design: "str | Design" = "v1") -> str:
    return os.path.join(_HERE, design_of(design).prereg_file)


def prereg_sha256(path: str | None = None, design: "str | Design" = "v1") -> str | None:
    """sha256 of a pre-registration file as it is on disk (None when unreadable)."""
    try:
        with open(path or prereg_path(design), "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def pinned_prereg(design: "str | Design") -> str:
    """The pinned hash of a design, after proving the committed file still matches it."""
    d = design_of(design)
    if not d.prereg_sha256:
        raise PreregDrift(f"design {d.id} has no pinned pre-registration yet")
    with open(os.path.join(_HERE, d.prereg_file), "rb") as fh:      # never a relocatable path
        on_disk = hashlib.sha256(fh.read()).hexdigest()
    if on_disk != d.prereg_sha256:
        raise PreregDrift(f"{d.prereg_file} hashes to {on_disk[:12]}…, pinned {d.prereg_sha256[:12]}…")
    return d.prereg_sha256


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
    (features, controls): dicts of (len(rows), N) arrays keyed by FEATURES and by every control
    name any design uses (CONTROLS ∪ CONTROLS_V2).
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
    c_dn2 = np.cumsum(np.where(rz < 0, rz * rz, 0.0), axis=0)
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

        for n in sorted({VOL_WINDOW, *RISK_WINDOWS}):
            s1, s2 = win(c_r, n), win(c_r2, n)
            var = (s2 - s1 * s1 / n) / (n - 1)
            ctrl[f"vol_{n}d"] = np.where(win(c_bad, n) == 0, np.sqrt(np.maximum(var, 0.0)),
                                         np.nan)
        for n in DOWNSIDE_WINDOWS:          # downside semi-deviation: sqrt(mean(min(r, 0)^2))
            ctrl[f"downvol_{n}d"] = np.where(win(c_bad, n) == 0,
                                             np.sqrt(np.maximum(win(c_dn2, n), 0.0) / n), np.nan)

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


def build_panel(closes: pd.DataFrame, mem: pd.DataFrame, *, observed: pd.DataFrame | None = None,
                printed: pd.DataFrame | None = None, store_sourced=(), horizons=HORIZONS,
                step: int = FORMATION_STEP, lag: int = ENTRY_LAG) -> dict[str, Any]:
    """Assemble the PIT feature/label panel on one global formation calendar.

    ``observed`` (same shape as ``closes``) marks cells whose close was actually quoted. When it
    is given, a name is eligible only on a quoted price and a feature window holding any
    unquoted cell yields no value; labels still follow the cleaned series, so a name that stops
    trading keeps its last price. Without it the cleaned panel is taken as is (design v1).
    ``printed`` (same shape) holds the close exactly as it printed that day, unadjusted, where
    one is known. Where it is, the selection floor is tested on it and not on the adjusted,
    cleaned level — an adjusted price depends on splits that had not happened yet.
    The sample boundaries are not a property of the panel: ``sample_rows`` reads them from the
    design, so no caller can move them.
    """
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
    quoted = None
    if observed is not None:
        quoted = observed.reindex(index=closes.index, columns=names).fillna(False).to_numpy(bool)
        quoted = quoted & np.isfinite(P)
    feats, ctrl = compute_features(P if quoted is None else np.where(quoted, P, np.nan), spy, rows)
    labels = compute_labels(P, spy, rows, horizons, lag)
    floor_px, floor_printed = P, np.zeros(P.shape, bool)
    if printed is not None:
        asprinted = printed.reindex(index=closes.index, columns=names).to_numpy(float)
        floor_printed = np.isfinite(asprinted)
        floor_px = np.where(floor_printed, asprinted, P)
    with np.errstate(invalid="ignore"):
        eligible = member[rows] & np.isfinite(P[rows]) & (floor_px[rows] >= SELECT_FLOOR)
    if quoted is not None:
        eligible &= quoted[rows]
    stored = set(store_sourced)
    digest = hashlib.sha256()
    for part in (index.asi8, np.ascontiguousarray(P), np.ascontiguousarray(spy), member,
                 quoted, np.ascontiguousarray(floor_px), floor_printed):
        digest.update(b"-" if part is None else np.ascontiguousarray(part).tobytes())
    digest.update(repr(("|".join(map(str, names)), sorted(map(str, stored)), int(step), int(lag),
                        tuple(int(h) for h in horizons), MIN_HISTORY, SELECT_FLOOR)).encode())
    return {
        "index": index, "names": names, "rows": rows, "features": feats, "controls": ctrl,
        "labels": labels, "eligible": eligible, "step": int(step), "lag": int(lag),
        "horizons": tuple(int(h) for h in horizons),
        "observed_mask": quoted is not None, "printed_floor": printed is not None,
        "floor_printed": floor_printed[rows],
        "store_sourced": np.array([n in stored for n in names], bool),
        "digest": digest.hexdigest(),
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


def sample_rows(panel: dict, horizon: int, sample: str,
                design: "str | Design" = "v1") -> np.ndarray:
    """Formation positions belonging to a sample for one horizon.

    dev: the label's exit precedes the first session on or after HOLDOUT_START (purged, so no
    development label touches a holdout price) — the same boundary for every design.
    holdout: formation on or after the design's first holdout formation date. Dates between
    the two are scored by nobody. Both boundaries are module constants.
    """
    d = design_of(design)
    lab = panel["labels"][int(horizon)]
    first_locked = int(panel["index"].searchsorted(pd.Timestamp(HOLDOUT_START), side="left"))
    first_holdout = int(panel["index"].searchsorted(pd.Timestamp(d.holdout_formation_start),
                                                    side="left"))
    if sample == "dev":
        return np.flatnonzero(lab["observable"] & (lab["exit_rows"] < first_locked))
    if sample == "holdout":
        return np.flatnonzero(lab["observable"] & (panel["rows"] >= max(first_locked,
                                                                        first_holdout)))
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
    if len(s) < MIN_DATES_FOR_MEAN:
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


def _check_panel(panel: dict, d: Design) -> None:
    if bool(panel.get("observed_mask")) != d.observed_mask:
        raise ValueError(f"design {d.id} needs a panel built "
                         f"{'with' if d.observed_mask else 'without'} the quoted-price mask")
    if bool(panel.get("printed_floor")) != d.printed_floor:
        raise ValueError(f"design {d.id} needs a panel built "
                         f"{'with' if d.printed_floor else 'without'} printed prices")
    if (panel.get("step"), panel.get("lag"), tuple(panel.get("horizons", ()))) != (
            FORMATION_STEP, ENTRY_LAG, HORIZONS):
        raise ValueError("the panel was not built on the pre-registered calendar "
                         "(formation step, entry lag, horizons)")


def _check_holdout_request(d: Design, pin: str, prereg_hash, dev_result) -> None:
    if not d.holdout_open:
        raise HoldoutLocked(f"design {d.id}: this holdout is closed and is never scored")
    if not prereg_hash or prereg_hash != pin:
        raise HoldoutLocked(f"holdout scoring requires prereg_hash == sha256({d.prereg_file})")
    if (not isinstance(dev_result, dict) or dev_result.get("status") != "scored"
            or dev_result.get("sample") != "dev" or dev_result.get("design_id") != d.id
            or dev_result.get("prereg_sha256") != pin):
        raise HoldoutLocked(
            "holdout scoring requires this design's committed development result")


def score(panel: dict, *, design: "str | Design" = "v1", sample: str = "dev",
          prereg_hash: str | None = None, dev_result: dict | None = None) -> dict[str, Any]:
    """Score one design's pre-registered tests on one sample.

    Nothing is scored unless the design's pre-registration still hashes to its pin. A holdout
    run additionally needs that hash from the caller and the committed development result. The
    panel must be, byte for byte, the one that result was scored on; the development survivors
    are then re-derived on it, the run refuses if they differ from the committed ones, and it
    scores those tests and no others. With no survivor it does not
    run, and the holdout stays unspent.
    """
    d = design_of(design)
    if sample not in ("dev", "holdout"):
        raise ValueError(f"unknown sample {sample!r}")
    pin = pinned_prereg(d)
    if sample == "holdout":
        _check_holdout_request(d, pin, prereg_hash, dev_result)
    _check_panel(panel, d)
    if sample == "holdout" and (not panel.get("digest")
                                or dev_result.get("panel_sha256") != panel["digest"]):
        raise HoldoutLocked("the panel is not the one the committed development result was "
                            "scored on (inputs differ); the holdout was not scored")
    try:
        V = _judges()
    except Exception as exc:                                  # engine not importable
        return {"schema": SCHEMA, "status": "unavailable", "error": str(exc)}

    dev = _score_sample(V, panel, d, pin, "dev", None)
    _apply_dev_gates(V, dev, d)
    if sample == "dev":
        return dev
    survivors = dev["survivors"]
    committed = {str(k): int(v) for k, v in (dev_result.get("survivors") or {}).items()}
    if committed != survivors:
        raise HoldoutLocked("the committed development result does not reproduce on this "
                            "panel; the holdout was not scored")
    if not survivors:
        # nothing survived development: the holdout stays unspent for a later pre-registration
        return {"schema": SCHEMA, "status": "not_run", "sample": sample, "design_id": d.id,
                "reason": "no_dev_survivors_holdout_unspent", "prereg_sha256": pin}
    out = _score_sample(V, panel, d, pin, "holdout", survivors)
    _apply_holdout_confirmation(V, out, survivors)
    return out


def _score_sample(V, panel: dict, d: Design, pin: str, sample: str,
                  only: dict[str, int] | None) -> dict[str, Any]:
    """Per-date statistics for one sample.

    ``only`` is None in development (every pre-registered test). In the holdout it is the
    development survivors: horizons without a survivor are not touched and no statistic of any
    other test is formed, so there is nothing to read that was not pre-registered.
    """
    index, rows, step, lag = panel["index"], panel["rows"], panel["step"], panel["lag"]
    controls, endpoints = d.controls, d.endpoints
    assert controls[:len(MOMENTUM_CONTROLS)] == MOMENTUM_CONTROLS
    X_all = np.stack([panel["features"][f] for f in FEATURES], axis=2)       # (F, N, K)
    Z_all = np.stack([panel["controls"][c] for c in controls], axis=2)       # (F, N, C)
    n_mom = len(MOMENTUM_CONTROLS)
    v1_cols = [controls.index(c) for c in CONTROLS] if controls != CONTROLS else None
    risk_cols = ([controls.index(c) for c in RISK_CONTROLS] if d.risk_bucket_gate else None)
    stored = panel.get("store_sourced")
    stored = stored if stored is not None and bool(np.any(stored)) else None
    E = len(endpoints)
    result: dict[str, Any] = {
        "schema": SCHEMA, "status": "scored", "sample": sample, "design_id": d.id,
        "prereg_sha256": pin, "panel_sha256": panel.get("digest"), "design": frozen_design(d),
        "coverage": {}, "tests": {},
    }
    gating = sample == "dev"            # bucket, era and thinned statistics gate development only
    floor_printed = panel.get("floor_printed")

    for h in panel["horizons"]:
        cols = list(range(len(FEATURES)))
        if only is not None:
            cols = [k for k, f in enumerate(FEATURES)
                    if any(f"{f}|{h}|{e}" in only for e in endpoints)]
            if not cols:
                continue
        K = len(cols)
        lab = panel["labels"][h]
        sel = sample_rows(panel, h, sample, d)
        dates, n_names, n_deli, n_incomplete, n_stored, n_printed = [], [], [], [], [], []
        ext, mom, v1c, raw, drop, aud = [], [], [], [], [], []
        buckets, rbuckets, bins = [], [], []

        def quintile_ics(score_, X, Z, Y, n):
            order = np.argsort(np.argsort(score_, kind="stable"), kind="stable")
            grp = np.minimum(order * N_BUCKETS // n, N_BUCKETS - 1)
            ic_q = np.full((N_BUCKETS, K, E), np.nan)
            for q in range(N_BUCKETS):
                g = grp == q
                if int(g.sum()) >= MIN_NAMES_PER_BUCKET:
                    ic_q[q], _ = semi_partial_rank_ic(X[g], Z[g], Y[g])
            return ic_q

        for f in sel:
            Y = np.column_stack([lab[e][f] for e in endpoints])
            base = panel["eligible"][f] & np.isfinite(Y).all(axis=1)
            ok = base & np.isfinite(Z_all[f]).all(axis=1) & np.isfinite(X_all[f]).all(axis=1)
            n = int(ok.sum())
            if n < MIN_NAMES_PER_DATE:
                continue
            X, Z, Y = X_all[f][ok][:, cols], Z_all[f][ok], Y[ok]
            deli = lab["delisted_in_window"][f][ok]
            ic_ext, Rr = semi_partial_rank_ic(X, Z, Y)
            ic_mom, _ = semi_partial_rank_ic(X, Z[:, :n_mom], Y)
            ic_drop = np.full((K, E), np.nan)
            if int((~deli).sum()) >= MIN_NAMES_PER_DATE:
                ic_drop, _ = semi_partial_rank_ic(X[~deli], Z[~deli], Y[~deli])
            if v1_cols is not None:
                v1c.append(semi_partial_rank_ic(X, Z[:, v1_cols], Y)[0])
            if stored is not None:
                keep = ~stored[ok]
                n_stored.append(int((~keep).sum()))
                ic_aud = np.full((K, E), np.nan)
                if int(keep.sum()) >= MIN_NAMES_PER_DATE:
                    ic_aud, _ = semi_partial_rank_ic(X[keep], Z[keep], Y[keep])
                aud.append(ic_aud)
            # momentum buckets: equal-count groups of the mean rank of the momentum controls
            if gating:
                buckets.append(quintile_ics(_rank(Z[:, :n_mom]).mean(axis=1), X, Z, Y, n))
                if risk_cols is not None:
                    rbuckets.append(quintile_ics(_rank(Z[:, risk_cols]).mean(axis=1), X, Z, Y, n))
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
            if floor_printed is not None:
                n_printed.append(int(floor_printed[f][ok].sum()))
            ext.append(ic_ext)
            mom.append(ic_mom)
            raw.append(_corr(_rank(X), _rank(Y)))
            drop.append(ic_drop)
            bins.append(bm)

        cov = {
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
        if stored is not None and n_names:
            cov["store_sourced_fraction"] = float(sum(n_stored) / max(1, sum(n_names)))
        if d.printed_floor and n_names:
            cov["printed_floor_fraction"] = float(sum(n_printed) / max(1, sum(n_names)))
        result["coverage"][str(h)] = cov
        if not dates:
            continue
        dates_a = np.asarray(dates)
        ext_a, mom_a, raw_a, drop_a = (np.asarray(a) for a in (ext, mom, raw, drop))
        bucket_a, bins_a = (np.asarray(buckets) if gating else None), np.asarray(bins)

        def series_mean(a):
            with np.errstate(invalid="ignore"):
                return (float(np.nanmean(a)) if np.isfinite(a).sum() >= MIN_DATES_FOR_MEAN
                        else None)

        for j, k in enumerate(cols):
            feature = FEATURES[k]
            for e, endpoint in enumerate(endpoints):
                key = f"{feature}|{h}|{endpoint}"
                if only is not None and key not in only:
                    continue
                st = _series_stats(V, dates_a, ext_a[:, j, e], h, step, lag)
                with np.errstate(invalid="ignore"):
                    bin_means = [float(np.nanmean(bins_a[:, q, j, e])) for q in range(N_BINS)]
                st.update({
                    "feature": feature, "family": family_of(feature), "horizon_d": int(h),
                    "endpoint": endpoint,
                    "raw_mean": float(np.nanmean(raw_a[:, j, e])),
                    "momentum_only_mean": float(np.nanmean(mom_a[:, j, e])),
                    "drop_mean": series_mean(drop_a[:, j, e]),
                    "bin_means": bin_means,
                })
                if gating:
                    st["bucket_means"] = [series_mean(bucket_a[:, q, j, e])
                                          for q in range(N_BUCKETS)]
                else:
                    for unlisted in ("hit", "thinned", "era_means"):
                        del st[unlisted]
                if v1c:
                    st["v1_controls_mean"] = float(np.nanmean(np.asarray(v1c)[:, j, e]))
                if rbuckets:
                    ra = np.asarray(rbuckets)
                    st["risk_bucket_means"] = [series_mean(ra[:, q, j, e])
                                               for q in range(N_BUCKETS)]
                if aud:
                    st["audited_only_mean"] = series_mean(np.asarray(aud)[:, j, e])
                result["tests"][key] = st
    return result


def _apply_dev_gates(V, result: dict, d: Design) -> None:
    # a test without a p-value still counts in the family: it enters as p = 1
    pvals = {k: (float(st["p_hac"]) if st["p_hac"] is not None else 1.0)
             for k, st in result["tests"].items()}
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
        if d.risk_bucket_gate:
            gates["g7_risk_buckets"] = (sum(_same_sign(m, sign)
                                            for m in st.get("risk_bucket_means", []))
                                        >= BUCKET_AGREE_MIN)
        st["q_bh"] = bh.get(key, {}).get("q")
        st["gates"] = gates
        st["advance_dev"] = all(gates.values())
        if st["advance_dev"]:
            survivors[key] = sign
    result["n_tests"] = len(result["tests"])
    result["n_tests_with_p"] = sum(st["p_hac"] is not None for st in result["tests"].values())
    result["survivors"] = survivors
    result["family_summary"] = _family_summary(result["tests"], "advance_dev", d)


def _apply_holdout_confirmation(V, result: dict, confirm: dict[str, int]) -> None:
    one_sided: dict[str, float] = {}
    for key, sign in confirm.items():
        st = result["tests"].get(key)
        if st is None or st["p_hac"] is None or st["mean"] is None:
            one_sided[key] = 1.0          # every survivor counts in the family
            continue
        p = float(st["p_hac"])
        one_sided[key] = p / 2.0 if _same_sign(st["mean"], sign) else 1.0 - p / 2.0
    bh = V.benjamini_hochberg(one_sided, alpha=BH_ALPHA)
    for key in confirm:
        if key not in result["tests"]:                 # no usable holdout date at this horizon
            feature, horizon, endpoint = key.split("|")
            result["tests"][key] = {
                "feature": feature, "family": family_of(feature), "horizon_d": int(horizon),
                "endpoint": endpoint, "n_dates": 0, "mean": None, "t_hac": None, "p_hac": None,
                "hac_lags": None, "not_scored": "no_usable_holdout_dates"}
    confirmed = {}
    for key, st in result["tests"].items():
        p1 = one_sided.get(key)
        gates = {
            "h1_same_sign": _same_sign(st["mean"], confirm[key]),
            "h2_one_sided_p": p1 is not None and p1 <= HOLDOUT_P_ONE_SIDED,
            "h3_bh_fdr": bool(bh.get(key, {}).get("reject")),
            "h4_ic_floor": st["mean"] is not None and abs(st["mean"]) >= IC_FLOOR_HOLDOUT,
        }
        st["dev_sign"] = int(confirm[key])
        st["p_one_sided"] = p1
        st["holdout_gates"] = gates
        st["confirmed_holdout"] = all(gates.values())
        if st["confirmed_holdout"]:
            confirmed[key] = int(confirm[key])
    result["n_confirm_requested"] = len(confirm)
    result["confirmed"] = confirmed
    result["family_summary"] = _family_summary(
        result["tests"], "confirmed_holdout", design_of(result["design_id"]))


def _family_summary(tests: dict, flag: str, d: Design) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for family in FAMILIES:
        for endpoint in d.endpoints:
            keys = [k for k, st in tests.items()
                    if st["family"] == family and st["endpoint"] == endpoint]
            passed = sorted(k for k in keys if tests[k].get(flag))
            out[f"{family}|{endpoint}"] = {"n_tests": len(keys), "n_passed": len(passed),
                                           "passed": passed}
    return out


# ---- substrates ----------------------------------------------------------------------------
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


def universe_coverage(closes: pd.DataFrame, mem: pd.DataFrame,
                      observed: pd.DataFrame | None = None,
                      printed: pd.DataFrame | None = None) -> dict[str, Any]:
    """How much of the point-in-time universe the panel can actually price, year by year.

    On the first session of each year: members by the membership file, members with a price
    column at all, members with a usable price that day, and members that also clear the
    selection floor (on the printed close where one is known). Prices and membership only — no
    label enters, so this is safe to print for any year.
    """
    index = pd.DatetimeIndex(closes.index)
    starts, ends = pd.to_datetime(mem["start_date"]), pd.to_datetime(mem["end_date"])
    tickers = mem["ticker"].astype(str)
    cols = set(map(str, closes.columns))
    out: dict[str, Any] = {}
    for year in range(int(index[MIN_HISTORY].year) + 1, int(index[-1].year) + 1):
        pos = int(index.searchsorted(pd.Timestamp(f"{year}-01-01"), side="left"))
        if pos >= len(index):
            break
        t = index[pos]
        members = sorted(set(tickers[(starts <= t) & (ends.isna() | (ends > t))]))
        have = [m for m in members if m in cols]
        px = closes.loc[t, have].to_numpy(float)
        usable = np.isfinite(px)
        if observed is not None:
            usable &= observed.loc[t, have].to_numpy(bool)
        floor_px = px
        if printed is not None:
            asprinted = printed.loc[t].reindex(have).to_numpy(float)
            floor_px = np.where(np.isfinite(asprinted), asprinted, px)
        with np.errstate(invalid="ignore"):
            above = usable & (floor_px >= SELECT_FLOOR)
        out[str(year)] = {"date": str(t)[:10], "members": len(members),
                          "with_price_column": len(have), "priced": int(usable.sum()),
                          "above_floor": int(above.sum())}
    return out


def run(*, design: "str | Design" = "v1", sample: str = "dev", breadth_dir: str | None = None,
        store_dir: str | None = None, prereg_hash: str | None = None,
        dev_result: dict | None = None) -> dict[str, Any]:
    """End-to-end run of one design on its substrate. Dev by default; the holdout is fenced."""
    d = design_of(design)
    pin = pinned_prereg(d)
    if sample == "holdout":
        _check_holdout_request(d, pin, prereg_hash, dev_result)   # fail before loading anything
    observed, printed, stored = None, None, ()
    if d.substrate == "repaired":
        from research import trend_persistence_substrate as substrate
        closes, observed, printed, mem, provenance = substrate.load_repaired_panel(
            breadth_dir, store_dir)
        stored = provenance["store"]["names"]
    else:
        closes, mem, provenance = load_audited_panel(breadth_dir)
    if closes is None or closes.empty or "SPY" not in closes.columns:
        return {"schema": SCHEMA, "status": "unavailable",
                "reason": "audited_price_panel_missing"}
    panel = build_panel(closes, mem, observed=observed if d.observed_mask else None,
                        printed=printed if d.printed_floor else None, store_sourced=stored)
    out = score(panel, design=d, sample=sample, prereg_hash=prereg_hash, dev_result=dev_result)
    out.update({
        "universe": "sp1500_pit",
        "panel": ("deep_plus_delisted_sanitized" if d.substrate == "audited"
                  else "deep_plus_delisted_plus_store_sanitized_quoted"),
        "universe_names": len(panel["names"]), "provenance": provenance,
        "universe_coverage": universe_coverage(closes, mem,
                                               observed if d.observed_mask else None,
                                               printed if d.printed_floor else None),
    })
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--design", choices=sorted(DESIGNS), default="v1")
    ap.add_argument("--sample", choices=("dev", "holdout"), default="dev")
    ap.add_argument("--breadth-dir")
    ap.add_argument("--store-dir", help="whole-market daily store (repaired substrate only)")
    ap.add_argument("--prereg-hash", help="sha256 of the committed pre-registration (holdout)")
    ap.add_argument("--dev-result", help="the committed development result JSON (holdout)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    dev_result = None
    if args.dev_result:
        with open(args.dev_result) as fh:
            dev_result = json.load(fh)
    out = run(design=args.design, sample=args.sample, breadth_dir=args.breadth_dir,
              store_dir=args.store_dir, prereg_hash=args.prereg_hash, dev_result=dev_result)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    print(json.dumps({k: out.get(k) for k in ("status", "sample", "design_id", "n_tests",
                                              "coverage")}, default=str), flush=True)
    return 0 if out.get("status") in ("scored", "not_run") else 1


if __name__ == "__main__":
    raise SystemExit(main())
