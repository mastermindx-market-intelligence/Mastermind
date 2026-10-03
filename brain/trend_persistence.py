"""Trend-persistence feature extraction — advisory research substrate.

This module deliberately does NOT size, gate, buy, sell, or rank the live book. It turns
point-in-time close histories into interpretable persistence features for the existing
outcome-ledger / shadow-book machinery.

v0 has no fitted thresholds or composite score: research must earn them.
"""
from __future__ import annotations
from typing import Any

_WINDOWS = (5, 20, 60, 120, 252)


def _finite_float(value: Any) -> float | None:
    try:
        import math
        out = float(value)
        return out if math.isfinite(out) else None
    except (TypeError, ValueError):
        return None


def _slice_asof(series, asof=None):
    try:
        import pandas as pd
        s = series.astype(float).replace([float("inf"), float("-inf")], float("nan")).dropna()
        s = s[s > 0].sort_index()
        if asof is not None:
            cutoff = pd.Timestamp(asof)
            try:
                if getattr(s.index, "tz", None) is not None and cutoff.tzinfo is None:
                    cutoff = cutoff.tz_localize(s.index.tz)
            except Exception:
                pass
            s = s[s.index <= cutoff]
        return s
    except Exception:
        return None


def _trailing_return(s, sessions: int) -> float | None:
    try:
        if s is None or len(s) <= sessions:
            return None
        base, last = float(s.iloc[-1 - sessions]), float(s.iloc[-1])
        return last / base - 1.0 if base > 0 else None
    except Exception:
        return None


def _path_efficiency(s, sessions: int) -> float | None:
    """Net absolute move / sum absolute daily moves; 1 is maximally direct."""
    try:
        if s is None or len(s) <= sessions:
            return None
        w = s.iloc[-1 - sessions :]
        gross = w.pct_change().dropna().abs().sum()
        if gross <= 0:
            return None
        net = abs(float(w.iloc[-1] / w.iloc[0] - 1.0))
        return _finite_float(net / gross)
    except Exception:
        return None


def _positive_day_fraction(s, sessions: int) -> float | None:
    try:
        if s is None or len(s) <= sessions:
            return None
        r = s.iloc[-1 - sessions :].pct_change().dropna()
        return _finite_float((r > 0).mean()) if len(r) else None
    except Exception:
        return None


def _gain_retention(s, sessions: int) -> float | None:
    """Net return / compounded gross up-day opportunity; negatives are informative."""
    try:
        if s is None or len(s) <= sessions:
            return None
        w = s.iloc[-1 - sessions :]
        r = w.pct_change().dropna()
        up = r[r > 0]
        gross_up = float((1.0 + up).prod() - 1.0) if len(up) else 0.0
        if gross_up <= 0:
            return None
        net = float(w.iloc[-1] / w.iloc[0] - 1.0)
        return _finite_float(net / gross_up)
    except Exception:
        return None


def _drawdown_shape(s, sessions: int) -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {
        "max_drawdown": None, "current_drawdown": None, "sessions_since_high": None,
    }
    try:
        if s is None or len(s) <= sessions:
            return out
        w = s.iloc[-1 - sessions :]
        high = w.cummax()
        dd = w / high - 1.0
        out["max_drawdown"] = _finite_float(dd.min())
        out["current_drawdown"] = _finite_float(dd.iloc[-1])
        peak = float(w.max())
        locs = [i for i, v in enumerate(w.tolist()) if float(v) == peak]
        if locs:
            out["sessions_since_high"] = int(len(w) - 1 - locs[-1])
    except Exception:
        pass
    return out


def _relative_strength(prices, benchmark, sessions: int) -> float | None:
    p = _trailing_return(prices, sessions)
    b = _trailing_return(benchmark, sessions)
    return _finite_float(p - b) if p is not None and b is not None else None


def extract(prices, *, benchmark=None, asof=None) -> dict[str, Any]:
    """Compute point-in-time persistence features, keeping vanilla momentum separate."""
    s = _slice_asof(prices, asof)
    b = _slice_asof(benchmark, asof) if benchmark is not None else None
    n = int(len(s)) if s is not None else 0
    out: dict[str, Any] = {
        "schema": 1,
        "asof": str(s.index[-1])[:10] if n else (str(asof)[:10] if asof is not None else None),
        "observations": n,
        "momentum": {}, "relative_strength": {}, "path_quality": {},
        "gain_retention": {}, "drawdown": {},
    }
    for w in _WINDOWS:
        out["momentum"][f"ret_{w}d"] = _trailing_return(s, w)
        out["relative_strength"][f"excess_{w}d"] = _relative_strength(s, b, w) if b is not None else None
    for w in (20, 60, 120):
        out["path_quality"][f"efficiency_{w}d"] = _path_efficiency(s, w)
        out["path_quality"][f"positive_day_fraction_{w}d"] = _positive_day_fraction(s, w)
        out["gain_retention"][f"retained_{w}d"] = _gain_retention(s, w)
        out["drawdown"][f"{w}d"] = _drawdown_shape(s, w)
    return out


def flatten(record: dict[str, Any], prefix: str = "persistence") -> dict[str, Any]:
    """Flatten a record for ledgers/dataframes while retaining namespaces."""
    out: dict[str, Any] = {}
    for key, value in (record or {}).items():
        if isinstance(value, dict):
            out.update(flatten(value, f"{prefix}.{key}"))
        else:
            out[f"{prefix}.{key}"] = value
    return out
