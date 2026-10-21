"""Leakage-safe research harness for trend-persistence experiments.

Advisory-only: no live ranking, sizing, gates, buys or sells. Historical research reuses
Mastermind's audited survivorship/PIT panel when available and asks whether path-quality
features add information conditional on vanilla momentum.

This module holds no data and no holdout fence: ``build_panel`` and ``evaluate`` score
whatever prices they are handed. The pre-registered tests live in
``research.trend_persistence_panel``, which owns the fence. Do not feed this harness real
prices for formation dates on or after 2022-01-01 — that would read the locked holdout
outside the pre-registration.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from brain import trend_persistence as tp

DEFAULT_HORIZONS = (5, 20, 60)
MIN_NAMES_PER_DATE = 20
MIN_INDEPENDENT_DATES = 8
_BASELINE = (
    "persistence.momentum.ret_20d", "persistence.momentum.ret_60d",
    "persistence.momentum.ret_120d", "persistence.momentum.ret_252d",
)
_INCREMENTAL = (
    "persistence.path_quality.efficiency_20d", "persistence.path_quality.efficiency_60d",
    "persistence.path_quality.efficiency_120d",
    "persistence.path_quality.positive_day_fraction_20d",
    "persistence.path_quality.positive_day_fraction_60d",
    "persistence.path_quality.positive_day_fraction_120d",
    "persistence.path_quality.directional_consistency_20d",
    "persistence.path_quality.directional_consistency_60d",
    "persistence.path_quality.directional_consistency_120d",
    "persistence.gain_retention.retained_20d", "persistence.gain_retention.retained_60d",
    "persistence.gain_retention.retained_120d",
    "persistence.drawdown.20d.max_drawdown", "persistence.drawdown.60d.max_drawdown",
    "persistence.drawdown.120d.max_drawdown",
    "persistence.drawdown.20d.distance_to_high", "persistence.drawdown.60d.distance_to_high",
    "persistence.drawdown.120d.distance_to_high",
)


def _finite(v: Any):
    try:
        import math
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _forward_label(subject, benchmark, pos: int, horizon: int):
    try:
        p0, b0 = float(subject.iloc[pos]), float(benchmark.iloc[pos])
        if p0 <= 0 or b0 <= 0 or pos + horizon >= len(subject):
            return None
        path = subject.iloc[pos : pos + horizon + 1].astype(float)
        bp = benchmark.iloc[pos : pos + horizon + 1].astype(float)
        ret = float(path.iloc[-1] / p0 - 1.0)
        bret = float(bp.iloc[-1] / b0 - 1.0)
        dd = path / path.cummax() - 1.0
        return {
            "forward_return": ret,
            "forward_rel": ret - bret,
            "forward_max_drawdown": float(dd.min()),
            "continued": int(ret - bret > 0.0),
        }
    except Exception:
        return None


def build_panel(
    prices: dict,
    benchmark,
    *,
    horizons=DEFAULT_HORIZONS,
    formation_step: int = 5,
    min_history: int = 253,
    eligible_asof=None,
):
    """Build a PIT feature/label panel.

    eligible_asof(ticker, timestamp) is optional but should be supplied for historical
    experiments so current constituents are never projected backwards.
    """
    try:
        b = benchmark.astype(float).dropna()
        b = b[b > 0].sort_index()
    except Exception:
        return []
    horizons = tuple(sorted({int(h) for h in horizons if int(h) > 0}))
    max_h = max(horizons) if horizons else 0
    out = []
    for ticker, raw in (prices or {}).items():
        try:
            s = raw.astype(float).dropna()
            s = s[s > 0].sort_index()
            common = s.index.intersection(b.index)
            s, bb = s.reindex(common), b.reindex(common)
        except Exception:
            continue
        if len(s) <= min_history + max_h:
            continue
        for pos in range(min_history - 1, len(s) - max_h, max(1, int(formation_step))):
            asof = s.index[pos]
            if eligible_asof is not None:
                try:
                    if not bool(eligible_asof(str(ticker), asof)):
                        continue
                except Exception:
                    continue
            features = tp.flatten(tp.extract(s, benchmark=bb, asof=asof))
            for h in horizons:
                label = _forward_label(s, bb, pos, h)
                if label is not None:
                    out.append({
                        "asof": str(asof)[:10], "ticker": str(ticker).upper(),
                        "horizon_d": h, **features, **label,
                    })
    return out


def _thin(pairs, horizon):
    try:
        import numpy as np
        import pandas as pd
        kept, last = [], None
        for d, v in sorted(pairs):
            ts = pd.Timestamp(d)
            if last is None or int(np.busday_count(last.date(), ts.date())) >= int(horizon):
                kept.append(float(v))
                last = ts
        return kept
    except Exception:
        return []


def _summary(values):
    if not values:
        return {"n_dates": 0, "mean": None, "positive_fraction": None}
    return {
        "n_dates": len(values),
        "mean": round(sum(values) / len(values), 5),
        "positive_fraction": round(sum(v > 0 for v in values) / len(values), 3),
    }


def _partial_rank_ic(complete, rank_ic):
    """Spearman-style partial IC: rank-transform feature/outcome/controls, then residualise."""
    try:
        import numpy as np
        import pandas as pd
        a = np.asarray(complete, float)
        ranked = pd.DataFrame(a).rank(axis=0, method="average", pct=True).to_numpy(float)
        x, y, z = ranked[:, 0], ranked[:, 1], ranked[:, 2:]
        design = np.column_stack([np.ones(len(z)), z])
        xr = x - design @ np.linalg.lstsq(design, x, rcond=None)[0]
        yr = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
        ic = rank_ic(pd.Series(xr), pd.Series(yr))
        return float(ic) if ic == ic else None
    except Exception:
        return None


def evaluate(panel, *, horizons=DEFAULT_HORIZONS):
    try:
        import pandas as pd
        from engine.validation import rank_ic
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}
    result = {"schema": 2, "status": "building", "horizons": {}}
    for horizon in sorted({int(h) for h in horizons}):
        rows = [r for r in panel if int(r.get("horizon_d") or 0) == horizon]
        by_date = defaultdict(list)
        for r in rows:
            by_date[str(r.get("asof"))].append(r)
        hr = {"n_rows": len(rows), "n_dates": len(by_date), "features": {}}
        for feature in _INCREMENTAL:
            raw_pairs, cond_pairs = [], []
            for d, rs in by_date.items():
                pairs = [(_finite(r.get(feature)), _finite(r.get("forward_rel"))) for r in rs]
                pairs = [p for p in pairs if None not in p]
                if len(pairs) >= MIN_NAMES_PER_DATE:
                    ic = rank_ic(pd.Series([p[0] for p in pairs]), pd.Series([p[1] for p in pairs]))
                    if ic == ic:
                        raw_pairs.append((d, float(ic)))
                complete = []
                for r in rs:
                    vals = [_finite(r.get(feature)), _finite(r.get("forward_rel"))]
                    vals += [_finite(r.get(k)) for k in _BASELINE]
                    if all(v is not None for v in vals):
                        complete.append(vals)
                if len(complete) >= MIN_NAMES_PER_DATE:
                    ic = _partial_rank_ic(complete, rank_ic)
                    if ic is not None:
                        cond_pairs.append((d, ic))
            raw, cond = _thin(raw_pairs, horizon), _thin(cond_pairs, horizon)
            hr["features"][feature] = {
                "raw_ic": _summary(raw),
                "conditional_rank_ic": _summary(cond),
            }
        hr["effective_n"] = max(
            [v["conditional_rank_ic"]["n_dates"] for v in hr["features"].values()] or [0]
        )
        hr["ready"] = hr["effective_n"] >= MIN_INDEPENDENT_DATES
        result["horizons"][str(horizon)] = hr
    if any(v.get("ready") for v in result["horizons"].values()):
        result["status"] = "scoring"
    return result


def run_audited_panel():
    """Development-sample run on the audited deep+delisted, sanitized, PIT S&P1500 substrate.

    Delegates to ``research.trend_persistence_panel``, which owns the global formation
    calendar, the delisting-aware labels and the holdout fence. The design is frozen by
    ``research/TREND_PERSISTENCE_PREREG_V1.md``; this entry point cannot score the holdout.
    """
    try:
        from research import trend_persistence_panel as panel
        return panel.run(sample="dev")
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}
