"""Descriptive date-standardization; no alpha test or causal claim by itself."""
from __future__ import annotations
import numpy as np
import pandas as pd
from .core import ContractError, calendar_index, session


def decompose(frame: pd.DataFrame, *, permitted_end: str) -> dict:
    """Exact symmetric within-date/composition decomposition on common-support dates.

    One row per event, not repeated display days. `treated` labels an existing
    comparison; it is not assumed randomized. Never interpret date matching as
    removing every sector, beta, issuer, or selection confound.
    """
    required = {"event_id", "origin", "label_end", "treated", "outcome"}
    if not required.issubset(frame):
        raise ContractError("missing event, outcome or maturity fields")
    if frame.empty or frame.event_id.isna().any() or frame.event_id.duplicated().any():
        raise ContractError("nonempty unique event addresses required")
    f = frame.copy()
    f["origin"] = f.origin.map(session)
    f["label_end"] = f.label_end.map(session)
    end = session(permitted_end)
    if (f.label_end < f.origin).any() or (f.label_end > end).any() or (f.origin > end).any():
        raise ContractError("unmatured or unreleased outcome window")
    if any(type(v) not in (bool, np.bool_) for v in f.treated):
        raise ContractError("treated must be explicit booleans")
    f["outcome"] = pd.to_numeric(f.outcome, errors="coerce")
    good = np.isfinite(f.outcome)
    missing = int((~good).sum())
    f = f.loc[good]
    if f.empty or ((f.outcome < 0) | (f.outcome > 1)).any():
        raise ContractError("this ruler expects a probability/rate in [0,1]")
    global_means = f.groupby("treated").outcome.mean()
    if len(global_means) != 2:
        raise ContractError("both comparison arms required")
    table = f.groupby(["origin", "treated"]).outcome.agg(["mean", "size"]).unstack("treated")
    shared = table.dropna()
    if shared.empty:
        return {"status": "NO_COMMON_DATE_SUPPORT", "pooled_gap": float(global_means[True]-global_means[False]),
                "missing_outcomes": missing, "paired_dates": 0, "within_date_gap": None,
                "causal_effect_established": False}
    mu1, mu0 = shared["mean"][True], shared["mean"][False]
    n1, n0 = shared["size"][True], shared["size"][False]
    w1, w0 = n1/n1.sum(), n0/n0.sum()
    within = float(((w1+w0)/2*(mu1-mu0)).sum())
    composition = float(((w1-w0)*(mu1+mu0)/2).sum())
    paired_pooled = float((w1*mu1).sum()-(w0*mu0).sum())
    if not np.isclose(within+composition, paired_pooled, rtol=0, atol=1e-12):
        raise AssertionError("decomposition did not reconcile")
    return {"status": "DESCRIPTIVE", "pooled_gap": float(global_means[True]-global_means[False]),
            "common_date_pooled_gap": paired_pooled, "within_date_gap": within,
            "date_composition_component": composition, "equal_date_gap": float((mu1-mu0).mean()),
            "paired_dates": len(shared), "all_dates": int(f.origin.nunique()),
            "paired_events": int(n1.sum()+n0.sum()), "available_events": len(f),
            "missing_outcomes": missing, "causal_effect_established": False,
            "notes": "Paired support only; overlapping episodes and issuer/beta composition still require separate controls."}


def mature_episode_training(rows: pd.DataFrame, *, origin: str, minimum_events: int = 30) -> pd.DataFrame:
    """A small extraction seam: only labels fully observable before this origin.

    Does not fit a personality classifier, invent a permanent stock type or
    change Stock Identity. Thin samples are returned empty, never imputed.
    """
    need = {"event_id", "origin", "label_end", "label_available_session"}
    if not need.issubset(rows) or rows.event_id.duplicated().any():
        raise ContractError("invalid episode training contract")
    f = rows.copy()
    for c in ("origin", "label_end", "label_available_session"):
        f[c] = f[c].map(session)
    if ((f.label_end < f.origin) | (f.label_available_session < f.label_end)).any():
        raise ContractError("label clocks conflict")
    t = session(origin)
    eligible = f[(f.origin < t) & (f.label_end < t) & (f.label_available_session < t)]
    return eligible.copy() if len(eligible) >= minimum_events else eligible.iloc[:0].copy()
