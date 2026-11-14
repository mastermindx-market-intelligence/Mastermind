"""Narrow, evidence-bound constant-share-unit admission for five declared splits.

Does NOT adjust prices or distributions. The supplied Yahoo snapshot already
uses post-split share units; independent unadjusted OHLC verifies that fact.
XLF's 2016 in-kind XLRE distribution is deliberately outside this adapter.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .targets import validate_prices

SYMBOLS = frozenset(("XLB", "XLE", "XLK", "XLU", "XLY"))
SPLIT_DATE = pd.Timestamp("2025-12-05")
ISSUER_REFERENCE = "https://investors.statestreet.com/investor-news-events/press-releases/news-details/2025/State-Street-Investment-Management-Announces-Share-Splits-for-Five-Select-Sector-SPDR-ETFs/default.aspx"


def qualify_constant_share_units(instrument: str, prices: pd.DataFrame,
                                 independent_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if instrument not in SYMBOLS:
        raise ValueError("corporate-action profile does not admit this instrument")
    for name, frame in (("prices", prices), ("independent", independent_raw)):
        if (not isinstance(frame.index, pd.DatetimeIndex) or frame.index.hasnans
                or not frame.index.is_unique or not frame.index.is_monotonic_increasing
                or frame.index.tz is not None):
            raise ValueError(name + ": invalid session index")
    required = ["open", "high", "low", "close", "dividends", "adj_close", "stock_splits"]
    if not set(required).issubset(prices):
        raise ValueError("missing corporate-action evidence columns")
    event = prices.loc[prices.stock_splits.ne(0), "stock_splits"]
    if len(event) != 1 or event.index[0] != SPLIT_DATE or event.iloc[0] != 2.0:
        raise ValueError("unqualified split event set")
    if not set(("open", "high", "low", "close")).issubset(independent_raw):
        raise ValueError("independent OHLC missing")
    joint = prices[["open", "high", "low", "close"]].join(
        independent_raw[["open", "high", "low", "close"]], how="inner", rsuffix="_raw")
    if (len(joint) < 500 or (joint.index < SPLIT_DATE).sum() < 20
            or (joint.index >= SPLIT_DATE).sum() < 20
            or not {pd.Timestamp("2025-12-04"), SPLIT_DATE}.issubset(joint.index)):
        raise ValueError("insufficient independent split-basis coverage")
    if not np.isfinite(joint.to_numpy()).all() or (joint.to_numpy() <= 0).any():
        raise ValueError("invalid independent prices")
    factor = np.where(joint.index < SPLIT_DATE, .5, 1.0)
    errors = {c: float(np.max(np.abs(joint[c].to_numpy() /
                         (factor * joint[c + "_raw"].to_numpy()) - 1)))
              for c in ("open", "high", "low", "close")}
    if errors["close"] > 1e-5 or max(errors[c] for c in ("open", "high", "low")) > .001:
        raise ValueError("independent split basis disagrees")
    adjustment = prices.adj_close / prices.close
    if not np.isfinite(adjustment).all() or (adjustment <= 0).any():
        raise ValueError("invalid dividend adjustment evidence")
    distribution = prices.dividends + prices.get("capital_gains", 0.0)
    implied = prices.close.shift(1) * (1 - adjustment.shift(1)/adjustment)
    event_mask = distribution.gt(0) & implied.notna()
    if event_mask.sum() < 4:
        raise ValueError("insufficient distribution basis evidence")
    error = float((implied[event_mask] - distribution[event_mask]).abs().max())
    nonday_error = float((adjustment/adjustment.shift(1)-1)[~event_mask].abs().max())
    if not np.isfinite([error, nonday_error]).all() or error > .0001 or nonday_error > .00001:
        raise ValueError("distribution units or adjustment factors disagree")
    out = prices.copy()
    out["source_stock_splits"] = out.stock_splits
    # Semantic projection: zero UNAPPLIED splits in the already constant-unit panel.
    # The original event remains explicit, and every price/distribution is unchanged.
    out["stock_splits"] = 0.0
    validate_prices(out)
    record = {"profile": "qualified_constant_share_units_20251205.v1", "instrument": instrument,
              "split_date": str(SPLIT_DATE.date()), "ratio": 2.0,
              "issuer_reference": ISSUER_REFERENCE, "independent_overlap_rows": len(joint),
              "maximum_relative_ohlc_discrepancy": errors,
              "maximum_distribution_factor_discrepancy_dollars": error,
              "maximum_nondistribution_factor_change": nonday_error,
              "prices_modified": False, "distributions_modified": False,
              "event_retained_in": "source_stock_splits", "share_basis": "constant_post_split_units",
              "historical_vintage_proven": False,
              "caveat": "Current-vintage basis qualification; not point-in-time vendor certification."}
    return out, record
