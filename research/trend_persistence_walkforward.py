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

import datetime
import hashlib
import json
import math
import os
import re
import subprocess
from typing import Any, Mapping

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from research import trend_persistence_null as null
from research import trend_persistence_panel as tpp

SCHEMA = 2
PREREG_FILE = "TREND_PERSISTENCE_PREREG_B2.md"
PREREG_SHA256: str | None = "79764bf5f9bf18c6ce8a6161fa221188dc1a5859fe82d715711fecb7bb0380aa"
REFERENCE_FILE = os.path.join("data", "trend_persistence_b2_reference.json")
REFERENCE_SHA256: str | None = "6225eabb352077c21cc5977dbacd15653b6c840b7ae60c9d1ff96995c8f68d81"
HOLDOUT_RESULT_FILE = os.path.join("data", "trend_persistence_v2_holdout.json")
HOLDOUT_RESULT_SHA256 = "ff928d6c22168b4a674f63a319efd45d984f0b2a9c4095bfda8790cb6dceff41"
RESULT_FILE = os.path.join("data", "trend_persistence_b2_result.json")     # the one real result
ATTEMPT_FILE = os.path.join("data", "trend_persistence_b2_attempt.json")   # written before real data
V2_PANEL_SHA256 = tpp.HOLDOUT_PANEL_SHA256["v2"]
# The code a result depends on. The simulated reference records its hash; the real run refuses
# to compare against a reference that other code produced.
CODE_FILES = ("trend_persistence_walkforward.py", "trend_persistence_panel.py",
              "trend_persistence_null.py", "trend_persistence_substrate.py")

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

# One-sided test of a per-date mean: equal-weighted cosine variance, Student t reference.
EWC_SCALE = 0.4                        # cosine terms: 0.4 n^(2/3) …
EWC_MIN_DF = 4                         # … capped at n // (2 x label overlap), never under this

P_ONE_SIDED = 0.025                    # W1: 0.05 split over the two gated horizons
BLOCK_AGREE_MIN = 4                    # W2
CAPTURE_MIN = 0.010                    # W3: one percentage point of capture
SLOPE_RANGE = (0.80, 1.25)             # W4
Q2_P_ONE_SIDED = 0.05                  # K2
Q2_BH_ALPHA = 0.10                     # K3
Q2_IC_FLOOR = 0.005                    # K4
K5_ALPHA = 0.05                        # K5: share of simulated runs allowed any label
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
SIM_SEEDS = tuple(range(11, 111))      # Q2 on every seed
SIM_Q1_SEEDS = tuple(range(11, 31))    # Q1 as well on these
SIM_CHECK_SEEDS = tuple(range(111, 211))   # Q2 again, on runs that set no threshold
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
                  "k4_ic_floor": Q2_IC_FLOOR,
                  "k5": {"alpha": K5_ALPHA, "family": "all confirmed tests",
                         "statistic": "largest standardised excess, leave-one-out",
                         "spread": "sd * sqrt(simulated dates / dates)",
                         "against": "each simulated specification"}},
        "inference": {"variance": "equal-weighted cosine", "reference": "student t",
                      "scale": EWC_SCALE, "min_df": EWC_MIN_DF,
                      "cap": "n // (2 * ceil(horizon / step))"},
        "fit": {"logit_max_iter": LOGIT_MAX_ITER, "logit_tol": LOGIT_TOL,
                "gram_chunk": GRAM_CHUNK},
        "reproduction_tol": REPRODUCTION_TOL,
        "q2_series": list(Q2_SERIES), "q2_gated": Q2_GATED, "window_vol_bins": WINDOW_VOL_BINS,
        "q2_controls": {
            "v2": "controls; residual ranked again",
            "controls_sq": "controls + squares",
            "descriptors": "controls + descriptors + squares",
            "oracle": "controls + squares + label-window volatility (rank + bins)",
            "descriptors_oracle": "controls + descriptors + squares + label-window volatility",
        },
        "simulated": {"specs": list(SIM_SPECS), "seeds": list(SIM_SEEDS),
                      "q1_seeds": list(SIM_Q1_SEEDS), "check_seeds": list(SIM_CHECK_SEEDS),
                      "names": SIM_NAMES,
                      "start": SIM_START, "sessions": SIM_SESSIONS, "models": list(SIM_MODELS)},
        "v2_panel_sha256": V2_PANEL_SHA256, "holdout_result_sha256": HOLDOUT_RESULT_SHA256,
        "result_file": RESULT_FILE, "attempt_file": ATTEMPT_FILE, "code_files": list(CODE_FILES),
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


_PIN_LINE = re.compile(rb"^(PREREG_SHA256|REFERENCE_SHA256): str \| None = .*$", re.M)


def code_sha256() -> str:
    """One hash over the modules a result depends on, with this module's two pin lines blanked."""
    digest = hashlib.sha256()
    for name in CODE_FILES:
        with open(os.path.join(_HERE, name), "rb") as fh:
            body = fh.read()
        if name == CODE_FILES[0]:
            body = _PIN_LINE.sub(rb"\1 = <pin>", body)
        digest.update(name.encode() + b"\0" + body + b"\0")
    return digest.hexdigest()


def pinned_reference() -> dict[str, Any]:
    """The committed simulated reference, after proving it still matches its pin and this code."""
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
    if ref.get("code_sha256") != code_sha256():
        raise tpp.PreregDrift("the simulated reference was produced by different code")
    return ref


def pinned_holdout_result() -> dict[str, Any]:
    """V2's committed holdout result, after proving the file is the one this design names."""
    path = os.path.join(_HERE, HOLDOUT_RESULT_FILE)
    on_disk = _sha256(path)
    if on_disk != HOLDOUT_RESULT_SHA256:
        raise tpp.PreregDrift(f"{HOLDOUT_RESULT_FILE} hashes to {str(on_disk)[:12]}…, "
                              f"pinned {HOLDOUT_RESULT_SHA256[:12]}…")
    with open(path) as fh:
        return json.load(fh)


def dev_signs(holdout_result: Mapping[str, Any]) -> dict[str, int]:
    """The development sign of each confirmed test; they must be the 29 the design names."""
    signs = {k: int(st["dev_sign"]) for k, st in holdout_result["tests"].items()
             if st.get("confirmed_holdout")}
    if sorted(signs) != sorted(confirmed_keys()):
        raise tpp.PreregDrift("the confirmed tests are not the 29 the pre-registration names")
    return signs


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


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction of the incomplete beta function (modified Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        for aa in (m * (b - m) * x / ((qam + m2) * (a + m2)),
                   -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))):
            d = 1.0 + aa * d
            d = 1.0 / (d if abs(d) > tiny else tiny)
            c = 1.0 + aa / c
            c = c if abs(c) > tiny else tiny
            h *= d * c
        if abs(d * c - 1.0) < 1e-15:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_sf(t: float, df: int) -> float:
    """P(T > t) for Student's t with ``df`` degrees of freedom."""
    half = 0.5 * _betainc(0.5 * df, 0.5, df / (df + t * t))
    return half if t >= 0 else 1.0 - half


def ewc_df(n: int, horizon: int, step: int) -> int:
    """Cosine terms for ``n`` dates whose labels each span ``horizon / step`` formation dates."""
    overlap = max(1, math.ceil(horizon / step))
    return max(EWC_MIN_DF, min(int(EWC_SCALE * n ** (2.0 / 3.0)), n // (2 * overlap)))


def ewc_test(s: np.ndarray, horizon: int, step: int) -> tuple[float | None, int, float | None]:
    """t, degrees of freedom and P(T > t) for the mean of a per-date series.

    The long-run variance is the mean of the first ``df`` squared cosine transforms of the
    series, and t is referred to Student's t with ``df`` degrees of freedom. V2's Bartlett rule
    with a normal reference rejects a true mean of zero about twice as often as stated when
    labels overlap (pre-registration §7); this test holds its stated size there.
    """
    n = len(s)
    df = ewc_df(n, horizon, step)
    grid = (np.arange(1, n + 1) - 0.5) / n
    lam = math.sqrt(2.0 / n) * (np.cos(np.pi * np.outer(np.arange(1, df + 1), grid)) @ s)
    omega = float((lam ** 2).mean())
    if not omega > 0:
        return None, df, None
    t = math.sqrt(n) * float(s.mean()) / math.sqrt(omega)
    return t, df, student_t_sf(t, df)


def _bartlett_t(s: np.ndarray, lags: int) -> float | None:
    """V2's statistic (Bartlett kernel), unrounded. Reported beside the test; gates nothing."""
    n = len(s)
    d = s - s.mean()
    var = float(d @ d) / n
    lags = min(int(lags), n - 1)
    for j in range(1, lags + 1):
        var += 2.0 * (1.0 - j / (lags + 1)) * float(d[j:] @ d[:-j]) / n
    return float(s.mean()) / math.sqrt(var / n) if var > 0 else None


def _series(s: np.ndarray, horizon: int, step: int) -> dict[str, Any]:
    """Mean of a per-date series and its one-sided test above zero."""
    s = np.asarray(s, float)
    s = s[np.isfinite(s)]
    out = {"n_dates": int(len(s)), "mean": None, "t": None, "df": None, "p_one_sided": None,
           "t_v2_rule": None}
    if len(s) < tpp.MIN_DATES_FOR_MEAN:
        return out
    t, df, p = ewc_test(s, horizon, step)
    out.update({"mean": float(s.mean()), "t": t, "df": df, "p_one_sided": p,
                "t_v2_rule": _bartlett_t(s, max(4, 2 * math.ceil(horizon / step)))})
    return out


def _bh_reject(p: Mapping[str, float], alpha: float) -> set[str]:
    """Benjamini–Hochberg step-up: the keys rejected at false discovery rate ``alpha``."""
    order = sorted(p, key=lambda k: (p[k], k))
    last = 0
    for i, k in enumerate(order, 1):
        if p[k] <= alpha * i / len(order):
            last = i
    return set(order[:last])


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


def summarise(scored: dict, horizon: int, step: int, block_names, pairs=PAIRS) -> dict[str, Any]:
    per, block = scored["per_date"], scored["block"]
    models = {}
    for m, d in per.items():
        models[m] = {
            "ic": _series(d["ic"], horizon, step),
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
            "d_ic": _series(d_ic, horizon, step),
            "d_ic_by_block": by_block,
            "d_ic_audited": _series(per[a]["ic_audited"] - per[b]["ic_audited"], horizon, step),
            "d_capture": _series(per[a]["capture"] - per[b]["capture"], horizon, step),
            # baseline minus augmented: positive means the augmented model scores better
            "d_brier": _series(per[b]["brier"] - per[a]["brier"], horizon, step),
            "d_flagged_drawdown": _series(per[a]["flag_mdd"] - per[b]["flag_mdd"],
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
def summarise_q2(data: dict, horizon: int, step: int) -> dict[str, Any]:
    """Per confirmed feature at one horizon: each Q2 series' mean and test over the test dates."""
    out = {}
    for j, f in enumerate(data["features"]):
        out[f"{f}|{horizon}|{ENDPOINT}"] = {
            k: _series(data["q2"][k][:, j], horizon, step) for k in Q2_SERIES}
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


def _signed_p(p_upper: float | None, sign: int) -> float:
    """The one-sided p in the development direction, from the p above zero."""
    if p_upper is None:
        return 1.0
    return p_upper if sign > 0 else 1.0 - p_upper


def k5_reference(runs: list, signs: Mapping[str, int]) -> dict[str, Any]:
    """Per simulated specification: what a volatility-only market leaves in every test at once.

    For each test the runs give a mean and a spread of the volatility-controlled statistic,
    signed like development. A run's standardised excess over the others is taken test by
    test, leaving that run out of the mean and spread; its largest excess over the 29 tests is
    one draw of what a volatility-only market's best-looking test shows. The threshold is the
    value that 1 - ``K5_ALPHA`` of those draws stay under.
    """
    keys = confirmed_keys()
    sg = np.array([signs[k] for k in keys], float)
    S, stats = {}, {}
    for spec in SIM_SPECS:
        rows = [[r["q2"][k][Q2_GATED] for k in keys] for r in runs if r["spec"] == spec]
        if len(rows) < 20:
            raise ValueError(f"{spec}: {len(rows)} simulated runs cannot set a threshold")
        S[spec] = x = np.asarray(rows, float) * sg
        n = len(x)
        dates = {json.dumps(r["q2_dates"], sort_keys=True) for r in runs if r["spec"] == spec}
        if len(dates) != 1:
            raise ValueError(f"{spec}: simulated runs differ in their test dates")
        mean_loo = (x.sum(axis=0) - x) / (n - 1)
        var_loo = ((x ** 2).sum(axis=0) - x ** 2 - (n - 1) * mean_loo ** 2) / (n - 2)
        z_loo = (x - mean_loo) / np.sqrt(var_loo)
        largest = z_loo.max(axis=1)
        stats[spec] = {
            "n_runs": n, "z_loo": z_loo, "n_dates": json.loads(dates.pop()),
            "threshold": float(np.sort(largest)[math.ceil((1.0 - K5_ALPHA) * n) - 1]),
            "mean": x.mean(axis=0), "sd": x.std(axis=0, ddof=1), "largest": largest,
        }
    p_signed = {spec: np.array([[_signed_p((r.get("q2_p") or {}).get(k), signs[k]) for k in keys]
                                for r in runs if r["spec"] == spec]) for spec in SIM_SPECS}
    out = {}
    for spec, st in stats.items():
        above = st["z_loo"] > st["threshold"]                 # against its own specification
        for other, ot in stats.items():
            if other != spec:
                above &= (S[spec] - ot["mean"]) / ot["sd"] > ot["threshold"]
        gated = np.array([int(k.split("|")[1]) in GATE_HORIZONS for k in keys])
        rest = np.zeros_like(above)                           # K1 to K4 on the run's own series
        for i in range(st["n_runs"]):
            p = dict(zip(keys, p_signed[spec][i]))
            reject = _bh_reject(p, Q2_BH_ALPHA)
            rest[i] = [S[spec][i, j] > 0 and p[k] <= Q2_P_ONE_SIDED and k in reject
                       and abs(S[spec][i, j]) >= Q2_IC_FLOOR for j, k in enumerate(keys)]
        out[spec] = {
            "n_runs": st["n_runs"], "threshold": st["threshold"], "n_dates": st["n_dates"],
            "signed_mean": dict(zip(keys, st["mean"].tolist())),
            "sd": dict(zip(keys, st["sd"].tolist())),
            "largest_excess": st["largest"].tolist(),
            # the share of this specification's runs that would be given any label
            "false_label": {
                "k5_any_test": float(above.any(axis=1).mean()),
                "k5_gated_horizons": float(above[:, gated].any(axis=1).mean()),
                "all_gates_any_test": float((above & rest).any(axis=1).mean()),
                "all_gates_gated_horizons": float((above & rest)[:, gated].any(axis=1).mean()),
            },
        }
    return out


def apply_q2_gates(q2: dict, signs: Mapping[str, int], k5: Mapping[str, Any]) -> None:
    """K1–K5 per confirmed test: is anything left that the simulated markets do not leave?

    A mean over fewer dates spreads more. The simulated spread is taken to the series' own
    number of dates, ``sd * sqrt(simulated dates / dates)``, before the excess is formed.
    """
    one_sided = {key: _signed_p(st[Q2_GATED]["p_one_sided"], int(signs[key]))
                 for key, st in q2.items()}
    reject = _bh_reject(one_sided, Q2_BH_ALPHA)
    for key, st in q2.items():
        s, sign = st[Q2_GATED], int(signs[key])
        signed = None if s["mean"] is None else sign * s["mean"]
        excess = {}
        for spec, ref in k5.items():
            sim_dates = (ref.get("n_dates") or {}).get(key.split("|")[1])
            scale = math.sqrt(sim_dates / s["n_dates"]) if sim_dates and s.get("n_dates") else 1.0
            sd = ref["sd"][key] * scale
            z = None if signed is None else (signed - ref["signed_mean"][key]) / sd
            excess[spec] = {"z": z, "threshold": ref["threshold"],
                            "simulated_mean": ref["signed_mean"][key], "simulated_sd": sd,
                            "simulated_dates": sim_dates, "sd_scale": scale}
        gates = {
            "k1_same_sign": signed is not None and signed > 0,
            "k2_one_sided_p": one_sided[key] <= Q2_P_ONE_SIDED,
            "k3_bh_fdr": key in reject,
            "k4_ic_floor": s["mean"] is not None and abs(s["mean"]) >= Q2_IC_FLOOR,
            "k5_above_simulated": bool(excess) and all(
                e["z"] is not None and e["z"] > e["threshold"] for e in excess.values()),
        }
        st.update({"dev_sign": sign, "p_signed": one_sided[key], "simulated": excess,
                   "gates": gates, "beyond_simulated_volatility": all(gates.values())})


def k5_check(runs: list, signs: Mapping[str, int], k5: Mapping[str, Any]) -> dict[str, Any]:
    """Runs that set no threshold, put through the gates real data goes through.

    The thresholds make at most ``K5_ALPHA`` of the runs they were set on pass K5. This is the
    share of fresh runs that pass, which nothing forces.
    """
    out = {}
    for spec in SIM_SPECS:
        rows = []
        for r in (r for r in runs if r["spec"] == spec):
            q2 = {k: {Q2_GATED: {"mean": st[Q2_GATED], "p_one_sided": r["q2_p"][k],
                                 "n_dates": r["q2_dates"][k.split("|")[1]]}}
                  for k, st in r["q2"].items()}
            apply_q2_gates(q2, signs, k5)
            rows.append({
                "seed": r["seed"],
                "k5": sorted(k for k, st in q2.items() if st["gates"]["k5_above_simulated"]),
                "beyond": sorted(k for k, st in q2.items() if st["beyond_simulated_volatility"]),
                "largest_excess": {sp: max(st["simulated"][sp]["z"] for st in q2.values())
                                   for sp in k5},
            })
        if not rows:
            continue

        def share(field, gated_only=False):
            return float(np.mean([any(not gated_only or int(k.split("|")[1]) in GATE_HORIZONS
                                      for k in row[field]) for row in rows]))
        out[spec] = {"n_runs": len(rows), "runs": rows,
                     "k5_any_test": share("k5"), "k5_gated_horizons": share("k5", True),
                     "all_gates_any_test": share("beyond"),
                     "all_gates_gated_horizons": share("beyond", True)}
    return out


def decide(horizons: dict, q2: dict) -> dict[str, Any]:
    """The pre-registered decision (§8) from the gated horizons' gates and the Q2 verdicts."""
    gates = {h: horizons[str(h)]["gates"] for h in GATE_HORIZONS if str(h) in horizons}
    passed = [h for h, g in gates.items() if g["passed"]]
    beyond = {h: sorted(k for k, st in q2.items()
                        if int(k.split("|")[1]) == h and st.get("beyond_simulated_volatility"))
              for h in HORIZONS}
    kind = {str(h): ("beyond_simulated_volatility" if beyond[h] else "volatility_type")
            for h in passed}
    if passed:
        outcome = "eligible_calibrated_profile"
    elif any(g["w1"] and g["w2"] and g["w3"] for g in gates.values()):
        outcome = "material_uncalibrated"
    elif any(g["w1"] and g["w2"] for g in gates.values()):
        outcome = "detectable_immaterial"
    else:
        outcome = "no_model_value"
    return {"outcome": outcome, "horizons": passed, "kind": kind,
            "beyond_simulated_volatility": {str(h): v for h, v in beyond.items()},
            "advances": outcome == "eligible_calibrated_profile",
            "family_stops_at_wave_b": outcome in ("detectable_immaterial", "no_model_value")}


# ---- the measurement ------------------------------------------------------------------------
def measure(panel: dict, inputs: dict, *, models=MODELS, early: bool = True, q1: bool = True,
            holdout_result: dict | None = None, keep_series: bool = False) -> dict[str, Any]:
    """Q2 and Q1 on one panel. With ``holdout_result``, nothing is returned unless V2's own
    statistic reproduces."""
    tpp._check_panel(panel, tpp.design_of(DESIGN))
    data, q2 = {}, {}
    series: dict[str, dict] = {"q2": {}, "d_ic": {}}
    for h in HORIZONS:
        data[h] = assemble(panel, inputs, h)
        if data[h]["n_dates"]:
            q2.update(summarise_q2(data[h], h, panel["step"]))
            if keep_series:
                for j, f in enumerate(data[h]["features"]):
                    series["q2"][f"{f}|{h}|{ENDPOINT}"] = np.array(data[h]["q2"][Q2_GATED][:, j])
        if not q1:
            data[h] = None
    if holdout_result is not None:
        check_reproduction(q2, holdout_result)
    pairs = tuple(p for p in PAIRS if p[0] in models and p[1] in models)
    horizons, early_out = {}, {}
    for h in HORIZONS if q1 else ():
        if not data[h]["n_dates"]:
            continue
        scored = score_blocks(data[h], h, BLOCKS, models=models)
        s = summarise(scored, h, panel["step"], [b[0] for b in BLOCKS], pairs)
        s["gates"] = apply_gates(s)
        horizons[str(h)] = s
        if keep_series:
            a, b = GATED_PAIR
            series["d_ic"][str(h)] = scored["per_date"][a]["ic"] - scored["per_date"][b]["ic"]
        if early:
            early_out[str(h)] = summarise(
                score_blocks(data[h], h, EARLY_BLOCKS, models=EARLY_MODELS, sample="is_dev"),
                h, panel["step"], [b[0] for b in EARLY_BLOCKS],
                tuple(p for p in PAIRS if p[0] in EARLY_MODELS and p[1] in EARLY_MODELS))
        data[h] = None                                        # free the stacked matrix
    out = {"horizons": horizons, "early": early_out, "q2": q2}
    if keep_series:
        out["series"] = series
    return out


# ---- simulated reference --------------------------------------------------------------------
def reference_run(spec: str, seed: int, *, q1: bool = True, keep_series: bool = False,
                  n_names: int = SIM_NAMES, n_sessions: int = SIM_SESSIONS,
                  start: str = SIM_START) -> dict[str, Any]:
    """Q2, and Q1 when asked, on one simulated panel. Takes a specification and a seed, never
    prices."""
    if spec not in null.SPECS:
        raise ValueError(f"unknown specification {spec!r}")
    closes = null.simulate(int(seed), spec, n_names=n_names, n_sessions=n_sessions, start=start)
    names = [c for c in closes.columns if c != "SPY"]
    mem = pd.DataFrame({"ticker": names, "start_date": closes.index[0],
                        "end_date": pd.Series([pd.NaT] * len(names), dtype="datetime64[ns]")})
    printed = pd.DataFrame(np.nan, index=closes.index, columns=names)
    observed = closes[names].notna()
    panel = tpp.build_panel(closes, mem, observed=observed, printed=printed)
    m = measure(panel, price_inputs(panel, closes, observed), models=SIM_MODELS, early=False,
                q1=q1, keep_series=keep_series)
    out_q1 = {}
    for h, s in m["horizons"].items():
        pair = s["pairs"][f"{GATED_PAIR[0]}_vs_{GATED_PAIR[1]}"]
        out_q1[h] = {
            "n_dates": s["n_dates"], "gates": s["gates"],
            "d_ic": pair["d_ic"]["mean"], "d_ic_t": pair["d_ic"]["t"],
            "d_ic_p": pair["d_ic"]["p_one_sided"],
            "d_capture": pair["d_capture"]["mean"], "d_brier": pair["d_brier"]["mean"],
            "models": {k: {"ic": v["ic"]["mean"], "capture": v["capture_mean"],
                           "brier": v["brier_mean"], "slope": v["calibration"]["slope"]}
                       for k, v in s["models"].items()},
        }
    out = {"spec": spec, "seed": int(seed), "q1": out_q1,
           "q2": {key: {k: st[k]["mean"] for k in Q2_SERIES} for key, st in m["q2"].items()},
           "q2_p": {key: st[Q2_GATED]["p_one_sided"] for key, st in m["q2"].items()},
           "q2_dates": {str(h): next((st[Q2_GATED]["n_dates"] for key, st in m["q2"].items()
                                      if int(key.split("|")[1]) == h), 0) for h in HORIZONS}}
    if keep_series:
        out["_series"] = m["series"]
    return out


def _reference_job(job):
    spec, seed, q1 = job
    return reference_run(spec, seed, q1=q1, keep_series=True)


def _rejects(s: np.ndarray, horizon: int, step: int) -> dict[str, bool]:
    """Whether a centred series is rejected: by the test at both levels, and by V2's rule."""
    s = s[np.isfinite(s)]
    p = ewc_test(s, horizon, step)[2]
    t_v2 = _bartlett_t(s, max(4, 2 * math.ceil(horizon / step)))
    p_v2 = None if t_v2 is None else 0.5 * math.erfc(t_v2 / math.sqrt(2.0))
    return {"at_0.05": p is not None and p <= 0.05, "at_0.025": p is not None and p <= 0.025,
            "v2_rule_at_0.05": p_v2 is not None and p_v2 <= 0.05,
            "v2_rule_at_0.025": p_v2 is not None and p_v2 <= 0.025}


def simulated_size(runs: list, signs: Mapping[str, int]) -> dict[str, Any]:
    """How often the one-sided test rejects on simulated series whose true mean is zero.

    Each run's series is centred at the mean of the other runs of its specification, so it
    keeps its own serial dependence. ``q2`` is the volatility-controlled statistic of every
    confirmed test on every run: its true mean is the same in every run, so the centred series
    has none left to find and the rejection rate is the test's size. ``d_ic`` is the gated
    pair's rank-correlation difference on the runs that carry Q1. It is not a size: each run
    fits its own models, whose true difference differs from run to run, so some of those
    rejections are right. It is kept so that the two can be told apart.
    """
    step = tpp.FORMATION_STEP

    def rates(cells: dict[str, list]) -> dict[str, Any]:
        return {h: {"cells": len(v)} | {k: float(np.mean([c[k] for c in v])) for k in v[0]}
                for h, v in cells.items()}

    out: dict[str, Any] = {"q2": {}, "d_ic": {}}
    for spec in SIM_SPECS:
        rs = [r for r in runs if r["spec"] == spec]
        cells: dict[str, list] = {}
        for key in confirmed_keys():
            h = int(key.split("|")[1])
            means = np.array([np.nanmean(r["_series"]["q2"][key]) for r in rs])
            for r, own in zip(rs, means):
                centre = (means.sum() - own) / (len(rs) - 1)
                cells.setdefault(str(h), []).append(
                    _rejects(signs[key] * (r["_series"]["q2"][key] - centre), h, step))
        out["q2"][spec] = rates(cells)
        cells = {}
        full = [r for r in rs if r["_series"]["d_ic"]]
        for h in HORIZONS if len(full) > 1 else ():
            means = np.array([np.nanmean(r["_series"]["d_ic"][str(h)]) for r in full])
            for r, own in zip(full, means):
                centre = (means.sum() - own) / (len(full) - 1)
                cells.setdefault(str(h), []).append(
                    _rejects(r["_series"]["d_ic"][str(h)] - centre, h, step))
        out["d_ic"][spec] = rates(cells)
    return out


def build_reference(*, specs=SIM_SPECS, seeds=SIM_SEEDS, q1_seeds=SIM_Q1_SEEDS,
                    check_seeds=SIM_CHECK_SEEDS, jobs: int = 1) -> dict[str, Any]:
    """The simulated reference: every specification and seed, by the code that scores real data."""
    pin = pinned_prereg()
    signs = dev_signs(pinned_holdout_result())
    todo = [(s, int(k), int(k) in q1_seeds) for s in specs for k in seeds]
    todo += [(s, int(k), False) for s in specs for k in check_seeds]
    if jobs > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            done = list(pool.map(_reference_job, todo))
    else:
        done = [_reference_job(job) for job in todo]
    runs, fresh = done[:len(specs) * len(seeds)], done[len(specs) * len(seeds):]
    size = simulated_size(runs, signs)
    for r in done:
        del r["_series"]
    out = {"schema": SCHEMA, "design_id": "b2", "kind": "simulated_reference",
           "prereg_sha256": pin, "code_sha256": code_sha256(), "design": frozen_design(),
           "runs": runs, "size": size, "k5": k5_reference(runs, signs)}
    out["k5_check"] = k5_check(fresh, signs, out["k5"])
    out["q2_ranges"] = simulated_ranges(out)
    q1: dict[str, dict[str, list]] = {}
    full = [r for r in runs if r["q1"]]
    for r in full:
        for h, s in r["q1"].items():
            for k in ("d_ic", "d_capture", "d_brier"):
                q1.setdefault(h, {}).setdefault(k, []).append(s[k])
    out["q1_ranges"] = {h: {k: [min(v), max(v)] for k, v in d.items()} for h, d in q1.items()}
    gated = [str(h) for h in GATE_HORIZONS]
    out["q1_gates"] = {
        "runs": len(full),
        "w1_and_w2_at_a_gated_horizon": sum(
            any(r["q1"][h]["gates"]["w1"] and r["q1"][h]["gates"]["w2"] for h in gated)
            for r in full),
        "w3_at_any_horizon": sum(any(g["gates"]["w3"] for g in r["q1"].values()) for r in full),
        "w4_run_horizons": sum(g["gates"]["w4"] for r in full for g in r["q1"].values()),
        "passed_at_a_gated_horizon": sum(
            any(r["q1"][h]["gates"]["passed"] for h in gated) for r in full),
    }
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
    signs = dev_signs(holdout_result)
    m = measure(panel, inputs, models=MODELS, early=True, holdout_result=holdout_result)
    apply_q2_gates(m["q2"], signs, reference["k5"])
    return {
        "schema": SCHEMA, "status": "scored", "design_id": "b2", "prereg_sha256": pin,
        "panel_sha256": panel.get("digest"), "design": frozen_design(),
        "horizons": m["horizons"], "early": m["early"], "q2": m["q2"],
        "q1_vs_simulated": q1_vs_simulated(m["horizons"], reference.get("q1_ranges")),
        "simulated": {
            "size": reference.get("size"), "q1_gates": reference.get("q1_gates"),
            "k5": {spec: {"threshold": v["threshold"], "n_runs": v["n_runs"],
                          "false_label": v["false_label"]}
                   for spec, v in reference["k5"].items()},
            "k5_check": {spec: {k: x for k, x in v.items() if k != "runs"}
                         for spec, v in (reference.get("k5_check") or {}).items()}},
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


def _git_state() -> dict[str, Any]:
    """The commit the instrument runs from, and whether anything but the attempt record differs."""
    def git(*args):
        return subprocess.run(["git", "-C", _HERE, *args], capture_output=True, text=True,
                              check=True).stdout
    dirty = [ln for ln in git("status", "--porcelain").splitlines()
             if not ln.endswith(os.path.basename(ATTEMPT_FILE))]
    return {"head": git("rev-parse", "HEAD").strip(), "clean": not dirty}


def run(*, breadth_dir: str | None = None, store_dir: str | None = None,
        retry_reason: str | None = None) -> dict[str, Any]:
    """The one run on V2's repaired panel, written to its one fixed path.

    Refuses any other panel, any code or reference but the pinned ones, an uncommitted tree,
    and a second run. An attempt is recorded before real data is read; if it fails, another
    needs a stated reason, which is kept in the result.
    """
    pinned_prereg()                                           # fail before loading anything
    reference = pinned_reference()
    holdout_result = pinned_holdout_result()
    result_path = os.path.join(_HERE, RESULT_FILE)
    attempt_path = os.path.join(_HERE, ATTEMPT_FILE)
    if os.path.exists(result_path):
        raise tpp.HoldoutLocked(f"{RESULT_FILE} exists: B2 has been run and is not run again")
    attempts = []
    if os.path.exists(attempt_path):
        with open(attempt_path) as fh:
            attempts = json.load(fh)["attempts"]
        if not (retry_reason and retry_reason.strip()):
            raise tpp.HoldoutLocked(
                f"{ATTEMPT_FILE} records an attempt that left no result; another attempt needs "
                "a stated reason and is reported as a deviation")
    git = _git_state()
    if not git["clean"]:
        raise tpp.PreregDrift("the tree has uncommitted changes; B2 runs from a commit")
    attempts.append({
        "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "git_head": git["head"], "code_sha256": reference["code_sha256"],
        "prereg_sha256": PREREG_SHA256, "reference_sha256": REFERENCE_SHA256,
        "retry_reason": retry_reason.strip() if retry_reason else None})
    with open(attempt_path, "w") as fh:
        json.dump({"attempts": attempts}, fh, indent=1)
    panel, inputs, provenance = _load_real(breadth_dir, store_dir)
    out = compare(panel, inputs, holdout_result, reference)
    out.update({"universe": "sp1500_pit", "universe_names": len(panel["names"]),
                "provenance": provenance, "panel_design": DESIGN,
                "reference_sha256": REFERENCE_SHA256, "code_sha256": reference["code_sha256"],
                "holdout_result_sha256": HOLDOUT_RESULT_SHA256, "git_head": git["head"],
                "attempts": attempts})
    with open(result_path + ".tmp", "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    os.replace(result_path + ".tmp", result_path)
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
    ap.add_argument("--out", help="for --reference and --coverage; the real run has a fixed path")
    ap.add_argument("--retry-reason", help="why an earlier attempt left no result")
    args = ap.parse_args(argv)
    if args.reference or args.coverage:
        if not args.out:
            ap.error("--out is required with --reference and --coverage")
        if args.reference:
            out = build_reference(jobs=args.jobs)
        else:
            panel, inputs, _ = _load_real(args.breadth_dir, args.store_dir)
            out = {"kind": "coverage", "panel_sha256": panel["digest"],
                   "coverage": coverage(panel, inputs)}
        with open(args.out, "w") as fh:
            json.dump(out, fh, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
    else:
        if args.out:
            ap.error("the real run writes to its fixed path; --out is not accepted")
        out = run(breadth_dir=args.breadth_dir, store_dir=args.store_dir,
                  retry_reason=args.retry_reason)
    print(json.dumps({"kind": out.get("kind", "b2"), "status": out.get("status"),
                      "decision": out.get("decision"), "coverage": out.get("coverage")},
                     default=str), flush=True)
    return 0 if out.get("status", "scored") == "scored" else 1


if __name__ == "__main__":
    raise SystemExit(main())
