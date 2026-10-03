"""Trend Persistence — walk-forward comparison and volatility decomposition (pre-registration B2).

V2's 29 confirmed tests pass gates that a simulated market with nothing but volatility also
passes (readout §10). This module asks the two questions that result leaves open:

  Q1, value. Do the confirmed features improve a volatility-aware model's out-of-sample
      ranking of forward maximum drawdown, by a material amount?
  Q2, kind.  With the realised volatility of the label's own window controlled, is anything
      left beyond what the simulated market leaves?

The design is frozen by ``research/TREND_PERSISTENCE_PREREG_B2.md``; nothing is scored unless
that file still hashes to the pin below. Panel, eligibility, complete cases and labels are
V2's, built by the V2 instrument. The simulated reference is produced by this module from the
committed benchmark generator, never from real prices, and is pinned before the real run.
Every year in the sample has been looked at before, so a pass here is a measurement, not a
confirmation.

Advisory research only. Nothing here ranks, sizes or gates anything.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any, Mapping

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from research import trend_persistence_null as null
from research import trend_persistence_panel as tpp

SCHEMA = 1
PREREG_FILE = "TREND_PERSISTENCE_PREREG_B2.md"
PREREG_SHA256: str | None = "75bf31d8f052c77ddf72f873a553580307803b207277359698e25c6d4f17972b"
REFERENCE_FILE = os.path.join("data", "trend_persistence_b2_reference.json")
REFERENCE_SHA256: str | None = "cdada6c4008ca5ad3939ff3e958f84fa7c0604ce02fb4f983de4276397febcd9"
HOLDOUT_RESULT_FILE = os.path.join("data", "trend_persistence_v2_holdout.json")
V2_PANEL_SHA256 = tpp.HOLDOUT_PANEL_SHA256["v2"]

DESIGN = "v2"                          # panel, eligibility, controls and label come from V2
ENDPOINT = "forward_max_drawdown"
HORIZONS = (5, 20, 60)
GATE_HORIZONS = (20, 60)
BLOCKS = (                             # gated test blocks, by formation date (inclusive)
    ("T1", "2022-07-06", "2022-12-31"),
    ("T2", "2023-01-01", "2023-12-31"),
    ("T3", "2024-01-01", "2024-12-31"),
    ("T4", "2025-01-01", "2025-12-31"),
    ("T5", "2026-01-01", "2026-12-31"),
)
EARLY_BLOCKS = tuple((str(y), f"{y}-01-01", f"{y}-12-31") for y in range(2009, 2022))
EVENT_FRACTION = 0.10                  # the deepest tenth of a date's forward drawdowns
FLAG_FRACTION = 0.10                   # the tenth a model rates most at risk
RELIABILITY_BINS = 10
MIN_TRAIN_DATES = 100
LOGIT_MAX_ITER = 60
LOGIT_TOL = 1e-8
GRAM_CHUNK = 1 << 18

P_ONE_SIDED = 0.025                    # W1: 0.05 split over the two gated horizons
BLOCK_AGREE_MIN = 4                    # W2
CAPTURE_MIN = 0.010                    # W3: one percentage point of capture
SLOPE_RANGE = (0.80, 1.25)             # W4
Q2_P_ONE_SIDED = 0.05                  # K2
Q2_BH_ALPHA = 0.10                     # K3
Q2_IC_FLOOR = 0.005                    # K4
REPRODUCTION_TOL = 1e-9                # V2's holdout means must come back to this

# Added price-only volatility descriptors, known at the formation date.
EWMA_HALF_LIVES = (3, 10, 30)
EWMA_SPAN = 120
ABS_WINDOWS = (20, 60, 120)
DOWN_WINDOWS = (20, 120)
DESCRIPTORS = (tuple(f"ewma_vol_{h}" for h in EWMA_HALF_LIVES)
               + tuple(f"mean_abs_{w}" for w in ABS_WINDOWS)
               + tuple(f"max_abs_{w}" for w in ABS_WINDOWS)
               + tuple(f"downvol_{w}" for w in DOWN_WINDOWS))
PRODUCT_WINDOWS = (20, 60, 120)        # trailing return x volatility, and its square x volatility

# Development survivors that passed the holdout gates (readout §10), by horizon and family.
CONFIRMED = {
    5: {
        "drawdown_shape": ("distance_to_high_20d", "distance_to_high_60d",
                           "distance_to_high_120d", "max_drawdown_20d", "max_drawdown_60d",
                           "max_drawdown_120d"),
        "path_quality": ("efficiency_20d", "positive_day_fraction_20d",
                         "positive_day_fraction_60d", "positive_day_fraction_120d"),
    },
    20: {
        "drawdown_shape": ("distance_to_high_20d", "distance_to_high_60d",
                           "distance_to_high_120d", "max_drawdown_20d", "max_drawdown_60d",
                           "max_drawdown_120d", "sessions_since_high_60d",
                           "sessions_since_high_120d"),
        "path_quality": ("efficiency_20d", "positive_day_fraction_60d",
                         "positive_day_fraction_120d"),
    },
    60: {
        "drawdown_shape": ("distance_to_high_20d", "distance_to_high_60d",
                           "distance_to_high_120d", "max_drawdown_20d", "max_drawdown_60d",
                           "max_drawdown_120d", "sessions_since_high_120d"),
        "path_quality": ("positive_day_fraction_60d",),
    },
}
MODELS = ("B0", "B1", "B2", "A", "A_dd", "A_pq")
GATED_PAIR = ("A", "B2")
PAIRS = (("A", "B2"), ("A", "B1"), ("A", "B0"), ("B2", "B1"), ("B1", "B0"),
         ("A_dd", "B2"), ("A_pq", "B2"))
EARLY_MODELS = ("B0", "B2", "A")

# Q2: what is removed from a feature before it is correlated with the label.
Q2_SERIES = ("v2", "controls_sq", "descriptors", "oracle", "descriptors_oracle")
Q2_GATED = "oracle"
WINDOW_VOL_BINS = 20                   # equal-count bins of the label window's volatility

# The simulated reference: volatility only, no drift, no return autocorrelation.
SIM_SPECS = ("clustered_leverage", "clustered_leverage_jumps")
SIM_SEEDS = tuple(null.SEEDS)
SIM_NAMES = 1500
SIM_START, SIM_SESSIONS = "2012-01-02", 3770        # ends 2026-06-12: reaches the last block
SIM_MODELS = ("B0", "B1", "B2", "A")

_HERE = os.path.dirname(os.path.abspath(__file__))


def confirmed_keys() -> list[str]:
    return [f"{f}|{h}|{ENDPOINT}" for h in HORIZONS
            for fam in ("drawdown_shape", "path_quality") for f in CONFIRMED[h][fam]]


def frozen_design() -> dict[str, Any]:
    """Every constant the pre-registration fixes, as the instrument holds it."""
    return {
        "design": "b2", "panel_design": DESIGN, "endpoint": ENDPOINT,
        "horizons": list(HORIZONS), "gate_horizons": list(GATE_HORIZONS),
        "blocks": [list(b) for b in BLOCKS], "early_blocks": [list(b) for b in EARLY_BLOCKS],
        "event_fraction": EVENT_FRACTION, "flag_fraction": FLAG_FRACTION,
        "reliability_bins": RELIABILITY_BINS, "min_train_dates": MIN_TRAIN_DATES,
        "min_names_per_date": tpp.MIN_NAMES_PER_DATE,
        "controls": list(tpp.design_of(DESIGN).controls),
        "descriptors": list(DESCRIPTORS), "ewma_span": EWMA_SPAN,
        "product_windows": list(PRODUCT_WINDOWS),
        "confirmed": {str(h): {fam: list(fs) for fam, fs in fams.items()}
                      for h, fams in CONFIRMED.items()},
        "models": {"B0": "controls", "B1": "B0 + squared controls",
                   "B2": "B1 + descriptors + squared descriptors + products",
                   "A": "B2 + confirmed features", "A_dd": "B2 + confirmed drawdown shape",
                   "A_pq": "B2 + confirmed path quality"},
        "gated_pair": list(GATED_PAIR),
        "gates": {"w1_p_one_sided": P_ONE_SIDED, "w2_blocks_positive": BLOCK_AGREE_MIN,
                  "w3_capture_min": CAPTURE_MIN, "w4_slope_range": list(SLOPE_RANGE),
                  "k2_p_one_sided": Q2_P_ONE_SIDED, "k3_bh_alpha": Q2_BH_ALPHA,
                  "k4_ic_floor": Q2_IC_FLOOR},
        "q2_series": list(Q2_SERIES), "q2_gated": Q2_GATED, "window_vol_bins": WINDOW_VOL_BINS,
        "simulated": {"specs": list(SIM_SPECS), "seeds": list(SIM_SEEDS), "names": SIM_NAMES,
                      "start": SIM_START, "sessions": SIM_SESSIONS, "models": list(SIM_MODELS)},
        "v2_panel_sha256": V2_PANEL_SHA256,
    }


def _sha256(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def prereg_sha256() -> str | None:
    return _sha256(os.path.join(_HERE, PREREG_FILE))


def pinned_prereg() -> str:
    """The pinned hash, after proving the committed pre-registration still matches it."""
    if not PREREG_SHA256:
        raise tpp.PreregDrift("B2 has no pinned pre-registration yet; nothing is scored")
    on_disk = prereg_sha256()
    if on_disk != PREREG_SHA256:
        raise tpp.PreregDrift(f"{PREREG_FILE} hashes to {str(on_disk)[:12]}…, "
                              f"pinned {PREREG_SHA256[:12]}…")
    return PREREG_SHA256


def pinned_reference() -> dict[str, Any]:
    """The committed simulated reference, after proving it still matches its pin."""
    if not REFERENCE_SHA256:
        raise tpp.PreregDrift("B2 has no pinned simulated reference yet; real data is not scored")
    path = os.path.join(_HERE, REFERENCE_FILE)
    on_disk = _sha256(path)
    if on_disk != REFERENCE_SHA256:
        raise tpp.PreregDrift(f"{REFERENCE_FILE} hashes to {str(on_disk)[:12]}…, "
                              f"pinned {REFERENCE_SHA256[:12]}…")
    with open(path) as fh:
        ref = json.load(fh)
    if ref.get("prereg_sha256") != PREREG_SHA256 or ref.get("design") != frozen_design():
        raise tpp.PreregDrift("the simulated reference was produced under a different design")
    return ref


# ---- price-only inputs ----------------------------------------------------------------------
def descriptors(P: np.ndarray, rows: np.ndarray, chunk: int = 48) -> dict[str, np.ndarray]:
    """The added volatility descriptors at each formation row, from prices at or before it.

    ``P`` holds quoted prices (unquoted cells are NaN). A window holding any unquoted cell
    yields no value. Returns arrays of shape (len(rows), n_names), keyed by ``DESCRIPTORS``.
    """
    with np.errstate(invalid="ignore", divide="ignore"):
        L = np.log(np.where(P > 0, P, np.nan))
    r = np.full(P.shape, np.nan)
    r[1:] = L[1:] - L[:-1]
    out = {k: np.full((len(rows), P.shape[1]), np.nan) for k in DESCRIPTORS}
    if len(P) < EWMA_SPAN:
        return out
    view = sliding_window_view(r, EWMA_SPAN, axis=0)         # (T - span + 1, N, span)
    age = np.arange(EWMA_SPAN - 1, -1, -1.0)                 # the last column is the formation row
    for a0 in range(0, len(rows), chunk):
        sl = slice(a0, a0 + chunk)
        at = rows[sl] - EWMA_SPAN + 1
        good = at >= 0
        if not good.any():
            continue
        win = view[at[good]]                                 # (c, N, span)
        full = np.isfinite(win).all(axis=2)
        wz = np.nan_to_num(win)
        dst = np.flatnonzero(good) + a0
        for hl in EWMA_HALF_LIVES:
            wts = 0.5 ** (age / hl)
            wts /= wts.sum()
            out[f"ewma_vol_{hl}"][dst] = np.where(
                full, np.sqrt(np.einsum("rnk,k->rn", wz * wz, wts)), np.nan)
        absr, neg = np.abs(wz), np.minimum(wz, 0.0)
        for w in ABS_WINDOWS:
            okw = np.isfinite(win[:, :, -w:]).all(axis=2)
            out[f"mean_abs_{w}"][dst] = np.where(okw, absr[:, :, -w:].mean(axis=2), np.nan)
            out[f"max_abs_{w}"][dst] = np.where(okw, absr[:, :, -w:].max(axis=2), np.nan)
        for w in DOWN_WINDOWS:
            okw = np.isfinite(win[:, :, -w:]).all(axis=2)
            out[f"downvol_{w}"][dst] = np.where(
                okw, np.sqrt((neg[:, :, -w:] ** 2).mean(axis=2)), np.nan)
    return out


def label_window_vol(P: np.ndarray, rows: np.ndarray, horizon: int, lag: int) -> np.ndarray:
    """Root mean squared daily log return over the label's own window (entry to exit).

    Uses the same carried-forward prices the label uses. Not known at formation: it is used to
    split what a feature says, never to predict.
    """
    Pff = pd.DataFrame(P).ffill().to_numpy(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        L = np.log(np.where(Pff > 0, Pff, np.nan))
    r = np.full(P.shape, np.nan)
    r[1:] = L[1:] - L[:-1]
    bad = np.vstack([np.zeros((1, P.shape[1])), np.cumsum(~np.isfinite(r), axis=0)])
    c2 = np.vstack([np.zeros((1, P.shape[1])), np.cumsum(np.nan_to_num(r) ** 2, axis=0)])
    out = np.full((len(rows), P.shape[1]), np.nan)
    for i, f in enumerate(rows):
        e, x = int(f) + lag, int(f) + lag + horizon
        if x <= len(P) - 1:
            whole = (bad[x + 1] - bad[e + 1]) == 0
            out[i] = np.where(whole, np.sqrt((c2[x + 1] - c2[e + 1]) / horizon), np.nan)
    return out


def price_inputs(panel: dict, closes: pd.DataFrame, observed: pd.DataFrame) -> dict[str, Any]:
    """Descriptors and label-window volatility for a panel, from the prices it was built on."""
    closes = closes.sort_index()
    if not pd.DatetimeIndex(closes.index).equals(panel["index"]):
        raise ValueError("prices and panel are not on the same calendar")
    names = panel["names"]
    P = closes[names].to_numpy(float)
    quoted = (observed.reindex(index=closes.index, columns=names).fillna(False).to_numpy(bool)
              & np.isfinite(P))
    rows = panel["rows"]
    return {"descriptors": descriptors(np.where(quoted, P, np.nan), rows),
            "label_vol": {int(h): label_window_vol(P, rows, int(h), panel["lag"])
                          for h in panel["horizons"]}}


# ---- data -----------------------------------------------------------------------------------
def _centred_ranks(a: np.ndarray) -> np.ndarray:
    """Column-wise percentile rank minus one half, in (-0.5, 0.5)."""
    a = np.asarray(a, float)
    return (tpp._rank(a) - 0.5) / a.shape[0] - 0.5


def _deepest(values: np.ndarray, fraction: float, largest: bool = False) -> np.ndarray:
    """Mask of the ``fraction`` of entries with the smallest (or largest) value; ties by position."""
    n = len(values)
    k = int(n * fraction)
    order = np.argsort(-values if largest else values, kind="stable")
    mask = np.zeros(n, bool)
    mask[order[:k]] = True
    return mask


def columns(horizon: int) -> dict[str, list[int]]:
    """Regressor columns of each model in the stacked matrix for one horizon."""
    n_c, n_d = len(tpp.design_of(DESIGN).controls), len(DESCRIPTORS)
    n_p = 2 * len(PRODUCT_WINDOWS)
    dd, pq = CONFIRMED[horizon]["drawdown_shape"], CONFIRMED[horizon]["path_quality"]
    c = list(range(n_c))
    s = list(range(n_c, 2 * n_c))
    v = list(range(2 * n_c, 2 * n_c + 2 * n_d + n_p))        # descriptors, squares, products
    base = 2 * n_c + 2 * n_d + n_p
    d = list(range(base, base + len(dd)))
    q = list(range(base + len(dd), base + len(dd) + len(pq)))
    return {"B0": c, "B1": c + s, "B2": c + s + v, "A": c + s + v + d + q,
            "A_dd": c + s + v + d, "A_pq": c + s + v + q}


def _products(Zr: np.ndarray, controls: tuple) -> np.ndarray:
    cols = []
    for w in PRODUCT_WINDOWS:
        ret, vol = Zr[:, controls.index(f"ret_{w}d")], Zr[:, controls.index(f"vol_{w}d")]
        cols += [ret * vol, ret * ret * vol]
    return np.column_stack(cols)


def _control_design(Zr: np.ndarray, square: bool) -> np.ndarray:
    """Intercept and standardised control ranks, optionally with their squares."""
    sd = Zr.std(axis=0)
    sd[sd == 0] = 1.0
    S = (Zr - Zr.mean(axis=0)) / sd
    cols = [np.ones(len(S)), *S.T]
    if square:
        cols += [S[:, j] ** 2 for j in range(S.shape[1])]
    return np.column_stack(cols)


def _window_vol_columns(fv: np.ndarray) -> np.ndarray:
    """The label window's realised volatility as a control: its standardised rank, and one
    indicator per equal-count bin of that rank (the first is left to the intercept)."""
    r = tpp._rank(fv)
    n = len(r)
    b = np.minimum(((r - 0.5) / n * WINDOW_VOL_BINS).astype(int), WINDOW_VOL_BINS - 1)
    ind = np.zeros((n, WINDOW_VOL_BINS))
    ind[np.arange(n), b] = 1.0
    sd = r.std() or 1.0
    return np.column_stack([(r - r.mean()) / sd, ind[:, 1:]])


def _residual_ic(Xr: np.ndarray, A: np.ndarray, Yr: np.ndarray, rerank: bool = False) -> np.ndarray:
    """Correlation with the label's rank of each feature's rank after removing the columns of ``A``.

    V2's statistic ranks the residual again (``rerank``). The volatility-controlled series do
    not: a re-ranked residual is no longer orthogonal to the controls, and a feature that only
    tracks a control leaks back in through the residual's skew.
    """
    resid = Xr - A @ np.linalg.lstsq(A, Xr, rcond=None)[0]
    return tpp._corr(tpp._rank(resid) if rerank else resid, Yr[:, None])[:, 0]


def assemble(panel: dict, inputs: dict, horizon: int) -> dict[str, Any]:
    """Every complete-case stock-date at one horizon, as centred within-date ranks.

    Complete cases are V2's: eligible, the label, all eleven controls and all 24 features. The
    added descriptors and the label-window volatility must exist on every one of them; the
    instrument stops if they do not. Columns of ``R``: controls, squared controls, descriptors,
    squared descriptors, products, confirmed drawdown-shape features, confirmed path-quality
    features. The label rank rises with a shallower forward drawdown.

    On dates in V2's holdout sample (the gated blocks) the Q2 statistics are formed as well:
    the correlation of the label's rank with each confirmed feature's rank after removing,
    cross-sectionally,
      v2                  the eleven controls, the residual ranked again (V2's own statistic)
      controls_sq         the controls and their squares
      descriptors         the controls, the descriptors, and all their squares
      oracle              controls_sq, plus the rank and the equal-count bins of the realised
                          volatility of the label's window
      descriptors_oracle  descriptors, plus the same
    """
    d = tpp.design_of(DESIGN)
    controls = tuple(d.controls)
    lab = panel["labels"][int(horizon)]
    feats = CONFIRMED[horizon]["drawdown_shape"] + CONFIRMED[horizon]["path_quality"]
    keep = [tpp.FEATURES.index(f) for f in feats]
    X_all = np.stack([panel["features"][f] for f in tpp.FEATURES], axis=2)
    Z_all = np.stack([panel["controls"][c] for c in controls], axis=2)
    D_all = np.stack([inputs["descriptors"][k] for k in DESCRIPTORS], axis=2)
    fv_all = inputs["label_vol"][int(horizon)]
    Y_all = lab[ENDPOINT]
    stored = panel.get("store_sourced")
    test_pos = set(int(i) for i in tpp.sample_rows(panel, horizon, "holdout", DESIGN))
    dev_pos = set(int(i) for i in tpp.sample_rows(panel, horizon, "dev", DESIGN))
    R, y, raw, event, aud = [], [], [], [], []
    form, exit_row, start, is_test, is_dev = [], [], [0], [], []
    q2: dict[str, list] = {k: [] for k in Q2_SERIES}
    for i in np.flatnonzero(lab["observable"]):
        ok = (panel["eligible"][i] & np.isfinite(Y_all[i])
              & np.isfinite(Z_all[i]).all(axis=1) & np.isfinite(X_all[i]).all(axis=1))
        n = int(ok.sum())
        if n < tpp.MIN_NAMES_PER_DATE:
            continue
        D, fv = D_all[i][ok], fv_all[i][ok]
        if not (np.isfinite(D).all() and np.isfinite(fv).all()):
            raise ValueError(
                f"{panel['index'][panel['rows'][i]].date()}: a descriptor or the label-window "
                "volatility is missing on a complete case; B2 was not scored")
        Zr = _centred_ranks(Z_all[i][ok])
        Dr = _centred_ranks(D)
        Xr = _centred_ranks(X_all[i][ok][:, keep])
        R.append(np.column_stack([Zr, Zr * Zr, Dr, Dr * Dr, _products(Zr, controls), Xr]))
        y.append(_centred_ranks(Y_all[i][ok]))
        raw.append(Y_all[i][ok])
        event.append(_deepest(Y_all[i][ok], EVENT_FRACTION))
        aud.append(~stored[ok] if stored is not None else np.ones(n, bool))
        form.append(int(panel["rows"][i]))
        exit_row.append(int(lab["exit_rows"][i]))
        start.append(start[-1] + n)
        is_test.append(int(i) in test_pos)
        is_dev.append(int(i) in dev_pos)
        if is_test[-1]:
            xr, yr = tpp._rank(X_all[i][ok][:, keep]), tpp._rank(Y_all[i][ok])
            z, dz, fo = tpp._rank(Z_all[i][ok]), tpp._rank(D), _window_vol_columns(fv)
            zc, zd = _control_design(z, True), _control_design(np.column_stack([z, dz]), True)
            q2["v2"].append(_residual_ic(xr, _control_design(z, False), yr, rerank=True))
            q2["controls_sq"].append(_residual_ic(xr, zc, yr))
            q2["descriptors"].append(_residual_ic(xr, zd, yr))
            q2["oracle"].append(_residual_ic(xr, np.column_stack([zc, fo]), yr))
            q2["descriptors_oracle"].append(_residual_ic(xr, np.column_stack([zd, fo]), yr))
    if not R:
        return {"n_dates": 0}
    form_a = np.asarray(form)
    return {
        "n_dates": len(form), "R": np.vstack(R), "y": np.concatenate(y),
        "raw": np.concatenate(raw), "event": np.concatenate(event).astype(float),
        "audited": np.concatenate(aud), "form": form_a, "exit": np.asarray(exit_row),
        "start": np.asarray(start), "dates": panel["index"][form_a],
        "is_test": np.asarray(is_test, bool), "is_dev": np.asarray(is_dev, bool),
        "features": feats,
        "q2": {k: (np.vstack(v) if v else np.zeros((0, len(feats)))) for k, v in q2.items()},
    }


def coverage(panel: dict, inputs: dict) -> dict[str, Any]:
    """Sample sizes, and how many complete cases lack a descriptor or the label-window
    volatility. Price-only: counts of stock-dates, never a feature compared with a label."""
    d = tpp.design_of(DESIGN)
    X_all = np.stack([panel["features"][f] for f in tpp.FEATURES], axis=2)
    Z_all = np.stack([panel["controls"][c] for c in d.controls], axis=2)
    D_ok = np.isfinite(np.stack([inputs["descriptors"][k] for k in DESCRIPTORS], axis=2)).all(axis=2)
    out = {}
    for h in panel["horizons"]:
        lab = panel["labels"][int(h)]
        fv_ok = np.isfinite(inputs["label_vol"][int(h)])
        test_pos = set(int(i) for i in tpp.sample_rows(panel, h, "holdout", DESIGN))
        missing_d = missing_v = 0
        kept, sizes, tested = [], [], []
        for i in np.flatnonzero(lab["observable"]):
            ok = (panel["eligible"][i] & np.isfinite(lab[ENDPOINT][i])
                  & np.isfinite(Z_all[i]).all(axis=1) & np.isfinite(X_all[i]).all(axis=1))
            if int(ok.sum()) < tpp.MIN_NAMES_PER_DATE:
                continue
            kept.append(int(i))
            sizes.append(int(ok.sum()))
            tested.append(int(i) in test_pos)
            missing_d += int((ok & ~D_ok[i]).sum())
            missing_v += int((ok & ~fv_ok[i]).sum())
        kept_a, sizes_a, tested_a = np.asarray(kept, int), np.asarray(sizes, int), np.asarray(tested, bool)
        dates = panel["index"][panel["rows"][kept_a]] if len(kept_a) else pd.DatetimeIndex([])
        blocks = {}
        for name, lo, hi in BLOCKS:
            sel = np.flatnonzero(tested_a & (dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi)))
            if not len(sel):
                blocks[name] = {"test_dates": 0}
                continue
            first = int(panel["rows"][kept_a[sel[0]]])
            train = lab["exit_rows"][kept_a] < first
            blocks[name] = {"test_dates": int(len(sel)), "test_cases": int(sizes_a[sel].sum()),
                            "first": str(dates[sel[0]])[:10], "last": str(dates[sel[-1]])[:10],
                            "train_dates": int(train.sum()),
                            "train_cases": int(sizes_a[train].sum())}
        out[str(int(h))] = {"dates": int(len(kept_a)), "complete_cases": int(sizes_a.sum()),
                            "test_dates": int(tested_a.sum()),
                            "missing_descriptor": missing_d, "missing_label_vol": missing_v,
                            "blocks": blocks}
    return out


# ---- fits -----------------------------------------------------------------------------------
def _with_intercept(X: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones(len(X)), X])


def _gram(A: np.ndarray, w: np.ndarray | None = None) -> np.ndarray:
    G = np.zeros((A.shape[1], A.shape[1]))
    for a in range(0, len(A), GRAM_CHUNK):
        B = A[a:a + GRAM_CHUNK]
        G += B.T @ B if w is None else (B * w[a:a + GRAM_CHUNK, None]).T @ B
    return G


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -35.0, 35.0)))


def fit_ols(A: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Least squares on a matrix that already carries its intercept column."""
    return np.linalg.lstsq(_gram(A), A.T @ y, rcond=None)[0]


def fit_logit(A: np.ndarray, e: np.ndarray, b0: np.ndarray | None = None) -> np.ndarray:
    """Unpenalised logistic regression by Newton's method; ``A`` carries the intercept first."""
    if b0 is not None and len(b0) == A.shape[1]:
        b = np.array(b0, float)
    else:
        b = np.zeros(A.shape[1])
        rate = float(np.clip(e.mean(), 1e-6, 1 - 1e-6))
        b[0] = math.log(rate / (1 - rate))
    for _ in range(LOGIT_MAX_ITER):
        p = _sigmoid(A @ b)
        step = np.linalg.lstsq(_gram(A, p * (1.0 - p)), A.T @ (e - p), rcond=None)[0]
        b = b + step
        if float(np.abs(step).max()) < LOGIT_TOL:
            return b
    raise RuntimeError("the logistic fit did not converge; B2 was not scored")


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    return float(tpp._corr(tpp._rank(a)[:, None], tpp._rank(b)[:, None])[0, 0])


# ---- Q1: walk-forward -----------------------------------------------------------------------
def score_blocks(data: dict, horizon: int, blocks, models=MODELS,
                 sample: str = "is_test") -> dict[str, Any]:
    """Fit each model before each block and score it on the block's dates.

    A block's models are fitted on every date whose label ends before the block's first
    formation date, so no fitted number has seen a price from inside the block. ``sample``
    names the mask of dates a block may score: V2's holdout dates for the gated blocks, V2's
    development dates for the early ones.
    """
    cols = columns(horizon)
    R, y, event, raw, start = data["R"], data["y"], data["event"], data["raw"], data["start"]
    per_date: dict[str, dict[str, list]] = {
        m: {"ic": [], "capture": [], "brier": [], "flag_mdd": [], "ic_audited": []}
        for m in models}
    pooled = {m: {"p": [], "e": []} for m in models}
    out_dates, out_block, all_mdd, info = [], [], [], []
    warm: dict[str, np.ndarray] = {}
    for name, lo, hi in blocks:
        in_block = (data["dates"] >= pd.Timestamp(lo)) & (data["dates"] <= pd.Timestamp(hi))
        test = np.flatnonzero(in_block & data[sample])
        if not len(test):
            info.append({"block": name, "n_dates": 0})
            continue
        train = np.flatnonzero(data["exit"] < data["form"][test[0]])
        if len(train) < MIN_TRAIN_DATES:
            info.append({"block": name, "n_dates": int(len(test)), "skipped": "short_training"})
            continue
        if train[-1] + 1 != len(train):                   # dates are in order; training is a prefix
            raise ValueError("training dates are not a prefix of the formation calendar")
        if train[-1] >= test[0]:
            raise ValueError("a training date is not before the block")
        tr = slice(0, int(start[len(train)]))
        fits = {}
        for m in models:
            A = _with_intercept(R[tr][:, cols[m]])
            fits[m] = (fit_ols(A, y[tr]), fit_logit(A, event[tr], warm.get(m)))
            warm[m] = fits[m][1]
            del A
        info.append({
            "block": name, "n_dates": int(len(test)), "first": str(data["dates"][test[0]])[:10],
            "last": str(data["dates"][test[-1]])[:10], "train_dates": int(len(train)),
            "train_rows": int(tr.stop),
            "train_last_formation": str(data["dates"][train[-1]])[:10],
        })
        for t in test:
            sl = slice(int(start[t]), int(start[t + 1]))
            ev, yy, rr, au = event[sl], y[sl], raw[sl], data["audited"][sl]
            for m in models:
                A = _with_intercept(R[sl][:, cols[m]])
                s = A @ fits[m][0]
                p = _sigmoid(A @ fits[m][1])
                flag = _deepest(p, FLAG_FRACTION, largest=True)
                pd_ = per_date[m]
                pd_["ic"].append(_spearman(s, yy))
                pd_["capture"].append(float(ev[flag].mean()) if flag.any() else np.nan)
                pd_["brier"].append(float(((p - ev) ** 2).mean()))
                pd_["flag_mdd"].append(float(rr[flag].mean()) if flag.any() else np.nan)
                pd_["ic_audited"].append(_spearman(s[au], yy[au])
                                         if int(au.sum()) >= tpp.MIN_NAMES_PER_DATE else np.nan)
                pooled[m]["p"].append(p)
                pooled[m]["e"].append(ev)
            out_dates.append(data["dates"][t])
            out_block.append(name)
            all_mdd.append(float(rr.mean()))
    return {"per_date": {m: {k: np.asarray(v, float) for k, v in d.items()}
                         for m, d in per_date.items()},
            "pooled": {m: {k: (np.concatenate(v) if v else np.zeros(0)) for k, v in d.items()}
                       for m, d in pooled.items()},
            "dates": pd.DatetimeIndex(out_dates), "block": np.asarray(out_block),
            "all_mdd": np.asarray(all_mdd, float), "blocks": info}


def _series(V, s: np.ndarray, horizon: int, step: int) -> dict[str, Any]:
    """Mean of a per-date series, its HAC t under V2's lag rule, and the one-sided p above zero."""
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    out = {"n_dates": int(len(s)), "mean": None, "t_hac": None, "p_hac": None,
           "p_one_sided": None, "hac_lags": None}
    if len(s) < tpp.MIN_DATES_FOR_MEAN:
        return out
    nw = V.newey_west_tstat(pd.Series(s), lags=max(4, 2 * math.ceil(horizon / step)))
    mean = float(s.mean())
    one = None
    if nw["p"] is not None and np.isfinite(nw["p"]):
        one = nw["p"] / 2 if mean > 0 else 1 - nw["p"] / 2
    out.update({"mean": mean, "t_hac": nw["t"], "p_hac": nw["p"], "p_one_sided": one,
                "hac_lags": nw["lags"]})
    return out


def _calibration(p: np.ndarray, e: np.ndarray) -> dict[str, Any]:
    """Pooled reliability table and the slope/intercept of the event on the logit of p."""
    if not len(p):
        return {"n": 0, "slope": None, "intercept": None, "bins": []}
    q = np.clip(p, 1e-9, 1 - 1e-9)
    b = fit_logit(_with_intercept(np.log(q / (1 - q))[:, None]), e)
    order = np.argsort(p, kind="stable")
    bins = []
    for part in np.array_split(order, RELIABILITY_BINS):
        bins.append({"n": int(len(part)), "predicted": float(p[part].mean()),
                     "observed": float(e[part].mean())})
    return {"n": int(len(p)), "intercept": float(b[0]), "slope": float(b[1]), "bins": bins}


def summarise(V, scored: dict, horizon: int, step: int, block_names, pairs=PAIRS) -> dict[str, Any]:
    per, block = scored["per_date"], scored["block"]
    models = {}
    for m, d in per.items():
        models[m] = {
            "ic": _series(V, d["ic"], horizon, step),
            "capture_mean": float(np.nanmean(d["capture"])) if len(d["capture"]) else None,
            "brier_mean": float(np.nanmean(d["brier"])) if len(d["brier"]) else None,
            "flagged_mean_drawdown": (float(np.nanmean(d["flag_mdd"]))
                                      if len(d["flag_mdd"]) else None),
            "calibration": _calibration(scored["pooled"][m]["p"], scored["pooled"][m]["e"]),
        }
    out_pairs = {}
    for a, b in pairs:
        if a not in per or b not in per:
            continue
        d_ic = per[a]["ic"] - per[b]["ic"]
        by_block = {}
        for name in block_names:
            sel = block == name
            by_block[name] = float(d_ic[sel].mean()) if bool(sel.any()) else None
        out_pairs[f"{a}_vs_{b}"] = {
            "d_ic": _series(V, d_ic, horizon, step),
            "d_ic_by_block": by_block,
            "d_ic_audited": _series(V, per[a]["ic_audited"] - per[b]["ic_audited"], horizon, step),
            "d_capture": _series(V, per[a]["capture"] - per[b]["capture"], horizon, step),
            # baseline minus augmented: positive means the augmented model scores better
            "d_brier": _series(V, per[b]["brier"] - per[a]["brier"], horizon, step),
            "d_flagged_drawdown": _series(V, per[a]["flag_mdd"] - per[b]["flag_mdd"],
                                          horizon, step),
        }
    return {"n_dates": int(len(scored["dates"])), "blocks": scored["blocks"],
            "mean_drawdown_all": (float(scored["all_mdd"].mean())
                                  if len(scored["all_mdd"]) else None),
            "models": models, "pairs": out_pairs}


def apply_gates(h: dict) -> dict[str, Any]:
    """W1–W4 on the gated pair for one horizon's summary."""
    a, b = GATED_PAIR
    pair = h["pairs"].get(f"{a}_vs_{b}")
    if not pair or pair["d_ic"]["mean"] is None:
        return {"w1": False, "w2": False, "w3": False, "w4": False, "blocks_positive": 0,
                "passed": False}
    d_ic, d_cap = pair["d_ic"], pair["d_capture"]
    w1 = bool(d_ic["mean"] > 0 and d_ic["p_one_sided"] is not None
              and d_ic["p_one_sided"] <= P_ONE_SIDED)
    positive = sum(1 for v in pair["d_ic_by_block"].values() if v is not None and v > 0)
    w2 = positive >= BLOCK_AGREE_MIN
    w3 = bool(d_cap["mean"] is not None and d_cap["mean"] >= CAPTURE_MIN)
    slope = h["models"][a]["calibration"]["slope"]
    w4 = bool(slope is not None and SLOPE_RANGE[0] <= slope <= SLOPE_RANGE[1]
              and h["models"][a]["brier_mean"] <= h["models"][b]["brier_mean"])
    return {"w1": w1, "w2": w2, "w3": w3, "w4": w4, "blocks_positive": positive,
            "passed": bool(w1 and w2 and w3 and w4)}


# ---- Q2: what kind of information -----------------------------------------------------------
def summarise_q2(V, data: dict, horizon: int, step: int) -> dict[str, Any]:
    """Per confirmed feature at one horizon: each Q2 series' mean and HAC t over the test dates."""
    out = {}
    for j, f in enumerate(data["features"]):
        out[f"{f}|{horizon}|{ENDPOINT}"] = {
            k: _series(V, data["q2"][k][:, j], horizon, step) for k in Q2_SERIES}
    return out


def check_reproduction(q2: dict, holdout_result: dict) -> None:
    """V2's own statistic, recomputed here on the test dates, must return the committed means."""
    for key, st in q2.items():
        ref = holdout_result["tests"][key]
        got = st["v2"]
        if got["n_dates"] != ref["n_dates"] or got["mean"] is None \
                or abs(got["mean"] - ref["mean"]) > REPRODUCTION_TOL:
            raise tpp.PreregDrift(
                f"{key}: V2's holdout statistic does not reproduce "
                f"({got['mean']} on {got['n_dates']} dates, committed {ref['mean']} on "
                f"{ref['n_dates']}); B2 was not scored")


def simulated_ranges(reference: dict) -> dict[str, dict[str, list]]:
    """Per test and Q2 series: the smallest and largest of the simulated run means."""
    out: dict[str, dict[str, list]] = {}
    for run in reference["runs"]:
        for key, st in run["q2"].items():
            for k, v in st.items():
                out.setdefault(key, {}).setdefault(k, []).append(v)
    return {key: {k: [min(v), max(v)] for k, v in st.items()} for key, st in out.items()}


def apply_q2_gates(V, q2: dict, signs: Mapping[str, int], ranges: Mapping[str, Any]) -> None:
    """K1–K5 per confirmed test: does it carry more than volatility?"""
    one_sided: dict[str, float] = {}
    for key, st in q2.items():
        s = st[Q2_GATED]
        if s["mean"] is None or s["p_hac"] is None:
            one_sided[key] = 1.0
            continue
        same = float(np.sign(s["mean"])) == float(signs[key])
        one_sided[key] = s["p_hac"] / 2.0 if same else 1.0 - s["p_hac"] / 2.0
    bh = V.benjamini_hochberg(one_sided, alpha=Q2_BH_ALPHA)
    for key, st in q2.items():
        s, sign = st[Q2_GATED], int(signs[key])
        lo, hi = ranges[key][Q2_GATED]
        top = max(sign * lo, sign * hi)                       # the range, signed like development
        signed = None if s["mean"] is None else sign * s["mean"]
        gates = {
            "k1_same_sign": signed is not None and signed > 0,
            "k2_one_sided_p": one_sided[key] <= Q2_P_ONE_SIDED,
            "k3_bh_fdr": bool(bh.get(key, {}).get("reject")),
            "k4_ic_floor": s["mean"] is not None and abs(s["mean"]) >= Q2_IC_FLOOR,
            "k5_above_simulated": signed is not None and signed > top,
        }
        st.update({"dev_sign": sign, "p_one_sided": one_sided[key],
                   "simulated_range": {k: list(v) for k, v in ranges[key].items()},
                   "gates": gates, "more_than_volatility": all(gates.values())})


def decide(horizons: dict, q2: dict) -> dict[str, Any]:
    """The pre-registered decision (§8) from the gated horizons' gates and the Q2 verdicts."""
    gates = {h: horizons[str(h)]["gates"] for h in GATE_HORIZONS if str(h) in horizons}
    passed = [h for h, g in gates.items() if g["passed"]]
    beyond = {h: sorted(k for k, st in q2.items()
                        if int(k.split("|")[1]) == h and st.get("more_than_volatility"))
              for h in HORIZONS}
    kind = {str(h): ("path_information" if beyond[h] else "volatility_type") for h in passed}
    if passed:
        outcome = "eligible_calibrated_profile"
    elif any(g["w1"] and g["w2"] and g["w3"] for g in gates.values()):
        outcome = "material_uncalibrated"
    elif any(g["w1"] and g["w2"] for g in gates.values()):
        outcome = "detectable_immaterial"
    else:
        outcome = "no_model_value"
    return {"outcome": outcome, "horizons": passed, "kind": kind,
            "more_than_volatility": {str(h): v for h, v in beyond.items()},
            "advances": outcome == "eligible_calibrated_profile",
            "family_stops_at_wave_b": outcome in ("detectable_immaterial", "no_model_value")}


# ---- the measurement ------------------------------------------------------------------------
def measure(V, panel: dict, inputs: dict, *, models=MODELS, early: bool = True,
            holdout_result: dict | None = None) -> dict[str, Any]:
    """Q2 then Q1 on one panel. With ``holdout_result`` the V2 statistic must reproduce first."""
    tpp._check_panel(panel, tpp.design_of(DESIGN))
    data, q2 = {}, {}
    for h in HORIZONS:
        data[h] = assemble(panel, inputs, h)
        if data[h]["n_dates"]:
            q2.update(summarise_q2(V, data[h], h, panel["step"]))
    if holdout_result is not None:
        check_reproduction(q2, holdout_result)
    pairs = tuple(p for p in PAIRS if p[0] in models and p[1] in models)
    horizons, early_out = {}, {}
    for h in HORIZONS:
        if not data[h]["n_dates"]:
            continue
        s = summarise(V, score_blocks(data[h], h, BLOCKS, models=models), h, panel["step"],
                      [b[0] for b in BLOCKS], pairs)
        s["gates"] = apply_gates(s)
        horizons[str(h)] = s
        if early:
            early_out[str(h)] = summarise(
                V, score_blocks(data[h], h, EARLY_BLOCKS, models=EARLY_MODELS, sample="is_dev"),
                h, panel["step"], [b[0] for b in EARLY_BLOCKS],
                tuple(p for p in PAIRS if p[0] in EARLY_MODELS and p[1] in EARLY_MODELS))
        data[h] = None                                        # free the stacked matrix
    return {"horizons": horizons, "early": early_out, "q2": q2}


# ---- simulated reference --------------------------------------------------------------------
def reference_run(spec: str, seed: int, *, n_names: int = SIM_NAMES,
                  n_sessions: int = SIM_SESSIONS, start: str = SIM_START) -> dict[str, Any]:
    """Q1 and Q2 on one simulated panel. Takes a specification and a seed, never prices."""
    if spec not in null.SPECS:
        raise ValueError(f"unknown specification {spec!r}")
    V = tpp._judges()
    closes = null.simulate(int(seed), spec, n_names=n_names, n_sessions=n_sessions, start=start)
    names = [c for c in closes.columns if c != "SPY"]
    mem = pd.DataFrame({"ticker": names, "start_date": closes.index[0],
                        "end_date": pd.Series([pd.NaT] * len(names), dtype="datetime64[ns]")})
    printed = pd.DataFrame(np.nan, index=closes.index, columns=names)
    observed = closes[names].notna()
    panel = tpp.build_panel(closes, mem, observed=observed, printed=printed)
    m = measure(V, panel, price_inputs(panel, closes, observed), models=SIM_MODELS, early=False)
    q1 = {}
    for h, s in m["horizons"].items():
        pair = s["pairs"][f"{GATED_PAIR[0]}_vs_{GATED_PAIR[1]}"]
        q1[h] = {
            "n_dates": s["n_dates"], "gates": s["gates"],
            "d_ic": pair["d_ic"]["mean"], "d_ic_t": pair["d_ic"]["t_hac"],
            "d_capture": pair["d_capture"]["mean"], "d_brier": pair["d_brier"]["mean"],
            "models": {k: {"ic": v["ic"]["mean"], "capture": v["capture_mean"],
                           "brier": v["brier_mean"], "slope": v["calibration"]["slope"]}
                       for k, v in s["models"].items()},
        }
    return {"spec": spec, "seed": int(seed), "q1": q1,
            "q2": {key: {k: st[k]["mean"] for k in Q2_SERIES} for key, st in m["q2"].items()}}


def _reference_job(job):
    return reference_run(*job)


def build_reference(*, specs=SIM_SPECS, seeds=SIM_SEEDS, jobs: int = 1) -> dict[str, Any]:
    """The simulated reference: every specification and seed, by the code that scores real data."""
    pin = pinned_prereg()
    todo = [(s, int(k)) for s in specs for k in seeds]
    if jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            runs = list(pool.map(_reference_job, todo))
    else:
        runs = [reference_run(*job) for job in todo]
    out = {"schema": SCHEMA, "design_id": "b2", "kind": "simulated_reference",
           "prereg_sha256": pin, "design": frozen_design(), "runs": runs}
    out["q2_ranges"] = simulated_ranges(out)
    q1: dict[str, dict[str, list]] = {}
    for r in runs:
        for h, s in r["q1"].items():
            for k in ("d_ic", "d_capture", "d_brier"):
                q1.setdefault(h, {}).setdefault(k, []).append(s[k])
    out["q1_ranges"] = {h: {k: [min(v), max(v)] for k, v in d.items()} for h, d in q1.items()}
    return out


def q1_vs_simulated(horizons: dict, ranges: Mapping[str, Any] | None) -> dict[str, Any]:
    """Each gated-pair difference beside the spread of the simulated runs. Reported, not gating."""
    out: dict[str, Any] = {}
    pair_key = f"{GATED_PAIR[0]}_vs_{GATED_PAIR[1]}"
    for h, s in horizons.items():
        pair, sim = s["pairs"].get(pair_key), (ranges or {}).get(h)
        if not pair or not sim:
            continue
        out[h] = {}
        for k in ("d_ic", "d_capture", "d_brier"):
            mean = pair[k]["mean"]
            out[h][k] = {"mean": mean, "simulated_range": list(sim[k]),
                         "above_simulated": mean is not None and mean > sim[k][1]}
    return out


# ---- real data ------------------------------------------------------------------------------
def compare(panel: dict, inputs: dict, holdout_result: dict, reference: dict) -> dict[str, Any]:
    """The pre-registered comparison on one panel, against a simulated reference."""
    pin = pinned_prereg()
    try:
        V = tpp._judges()
    except Exception as exc:                                  # engine not importable
        return {"schema": SCHEMA, "status": "unavailable", "error": str(exc)}
    signs = {k: int(st["dev_sign"]) for k, st in holdout_result["tests"].items()
             if st.get("confirmed_holdout")}
    if sorted(signs) != sorted(confirmed_keys()):
        raise tpp.PreregDrift("the confirmed tests are not the 29 the pre-registration names")
    m = measure(V, panel, inputs, models=MODELS, early=True, holdout_result=holdout_result)
    apply_q2_gates(V, m["q2"], signs, simulated_ranges(reference))
    return {
        "schema": SCHEMA, "status": "scored", "design_id": "b2", "prereg_sha256": pin,
        "panel_sha256": panel.get("digest"), "design": frozen_design(),
        "horizons": m["horizons"], "early": m["early"], "q2": m["q2"],
        "q1_vs_simulated": q1_vs_simulated(m["horizons"], reference.get("q1_ranges")),
        "decision": decide(m["horizons"], m["q2"]),
    }


def _load_real(breadth_dir, store_dir):
    from research import trend_persistence_substrate as substrate
    closes, observed, printed, mem, provenance = substrate.load_repaired_panel(breadth_dir,
                                                                               store_dir)
    panel = tpp.build_panel(closes, mem, observed=observed, printed=printed,
                            store_sourced=provenance["store"]["names"])
    if panel["digest"] != V2_PANEL_SHA256:
        raise tpp.PreregDrift("the panel is not the one V2 was scored on; B2 was not run")
    return panel, price_inputs(panel, closes, observed), provenance


def run(*, breadth_dir: str | None = None, store_dir: str | None = None,
        out_path: str | None = None) -> dict[str, Any]:
    """The one run on V2's repaired panel. Refuses any other panel and any second run."""
    pinned_prereg()                                           # fail before loading anything
    reference = pinned_reference()
    if out_path and os.path.exists(out_path):
        raise tpp.HoldoutLocked(f"{out_path} exists: B2 has been run and is not run again")
    with open(os.path.join(_HERE, HOLDOUT_RESULT_FILE)) as fh:
        holdout_result = json.load(fh)
    panel, inputs, provenance = _load_real(breadth_dir, store_dir)
    out = compare(panel, inputs, holdout_result, reference)
    out.update({"universe": "sp1500_pit", "universe_names": len(panel["names"]),
                "provenance": provenance, "panel_design": DESIGN,
                "reference_sha256": REFERENCE_SHA256})
    return out


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reference", action="store_true",
                    help="build the simulated reference (no real prices are read)")
    ap.add_argument("--coverage", action="store_true",
                    help="count complete cases lacking a descriptor (price-only; nothing scored)")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--breadth-dir")
    ap.add_argument("--store-dir")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    if args.reference:
        out = build_reference(jobs=args.jobs)
    elif args.coverage:
        panel, inputs, _ = _load_real(args.breadth_dir, args.store_dir)
        out = {"kind": "coverage", "panel_sha256": panel["digest"],
               "coverage": coverage(panel, inputs)}
    else:
        out = run(breadth_dir=args.breadth_dir, store_dir=args.store_dir, out_path=args.out)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    print(json.dumps({"kind": out.get("kind", "b2"), "status": out.get("status"),
                      "decision": out.get("decision"), "coverage": out.get("coverage")},
                     default=str), flush=True)
    return 0 if out.get("status", "scored") == "scored" else 1


if __name__ == "__main__":
    raise SystemExit(main())
