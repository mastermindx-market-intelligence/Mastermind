"""Pure descriptive comparisons of existing named wealth curves.

No persistence, price reconstruction, portfolio rebalancing, ranking, or consumer
wiring lives here. Supplied dates are labels, not proof of fresh or complete
observations, and common-point counts are not independent review counts. Results
must not be used as qualified decision evidence.

Each caller must retain the existing owner's curve identity and lineage. In
particular, do not alias missing carry to SPY, mix regional benchmark lineages,
or pass a legacy regime-max envelope as though it were a source component.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from math import isfinite
from numbers import Real


def _canonical_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _require_date(value: object, name: str) -> None:
    if not _canonical_date(value):
        raise ValueError(f"{name} must be a canonical YYYY-MM-DD date")


def _usable_curve(curve: Mapping, asof: str) -> dict[str, float]:
    if not isinstance(curve, Mapping):
        raise ValueError("each supplied curve must be a date-to-number mapping")
    out = {}
    for day, value in curve.items():
        if not _canonical_date(day) or day > asof:
            continue
        if isinstance(value, bool) or not isinstance(value, Real):
            continue
        try:
            number = float(value)
        except (OverflowError, ValueError):
            continue
        if isfinite(number) and number > 0:
            out[day] = number
    return out


def _ratio(end: float, start: float) -> float:
    ratio = end / start
    # Underflow to zero must not masquerade as a real zero-valued observation.
    if not isfinite(ratio) or ratio <= 0:
        raise ArithmeticError("unrepresentable ratio")
    return ratio


def _return_pct(ratio: float) -> float:
    value = (ratio - 1.0) * 100.0
    if not isfinite(value):
        raise ArithmeticError("unrepresentable percentage")
    return value


def _cohort_and_pairs(cohort: Sequence, delta_pairs: Sequence) -> tuple[tuple, tuple]:
    if isinstance(cohort, (str, bytes)) or not isinstance(cohort, Sequence):
        raise ValueError("cohort must be an explicit sequence of participant IDs")
    ids = tuple(cohort)
    if len(ids) < 2 or any(not isinstance(name, str) or not name.strip() for name in ids):
        raise ValueError("cohort must contain at least two nonempty string IDs")
    if len(set(ids)) != len(ids):
        raise ValueError("cohort IDs must be distinct")
    if isinstance(delta_pairs, (str, bytes)) or not isinstance(delta_pairs, Sequence):
        raise ValueError("delta_pairs must be an explicit sequence of ID pairs")
    pairs = []
    for pair in delta_pairs:
        if isinstance(pair, (str, bytes)) or not isinstance(pair, Sequence) or len(pair) != 2:
            raise ValueError("each delta pair must contain two included participant IDs")
        left, right = pair
        if left not in ids or right not in ids or left == right:
            raise ValueError("each delta pair must refer to two distinct cohort participants")
        if (left, right) in pairs:
            raise ValueError("delta pairs must not be duplicated")
        pairs.append((left, right))
    return ids, tuple(pairs)


def compare_curves(
    curves: Mapping[str, Mapping], *, cohort: Sequence[str], asof: str,
    delta_pairs: Sequence[tuple[str, str]] = (),
) -> dict:
    """Rebase the explicit cohort over its first/last shared usable dates.

    Returns are percentages; requested deltas are left minus right in percentage
    points. No rounding is applied here; a future presentation boundary owns
    display rounding. Two actual distinct common dates are required. Invalid
    points are excluded, not filled. A missing participant remains unavailable
    and never silently shrinks the cohort. Unselected curves have no influence.

    Invalid API configuration raises ValueError. Insufficient observations or
    unrepresentable arithmetic yield status='unavailable' and no numeric returns.
    The output is ephemeral; it must not replace persisted own-window returns.
    """
    _require_date(asof, "asof")
    ids, pairs = _cohort_and_pairs(cohort, delta_pairs)
    if not isinstance(curves, Mapping):
        raise ValueError("curves must be an ID-to-curve mapping")
    # A missing peer must not conceal malformed configuration in a supplied
    # selected curve. None is intentionally treated as unavailable data.
    for name in ids:
        if name in curves and curves[name] is not None and not isinstance(curves[name], Mapping):
            raise ValueError("each supplied curve must be a date-to-number mapping")
    result = {
        "status": "unavailable", "reason": None, "asof": asof, "cohort": ids,
        "start": None, "end": None, "common_dates": (), "common_point_count": 0,
        "returns_pct": None, "deltas_pp": None,
    }
    if any(name not in curves or curves[name] is None for name in ids):
        result["reason"] = "missing_curve"
        return result
    usable = {name: _usable_curve(curves[name], asof) for name in ids}
    common = tuple(sorted(set.intersection(*(set(curve) for curve in usable.values()))))
    result.update(common_dates=common, common_point_count=len(common))
    if len(common) < 2:
        result["reason"] = "insufficient_common_dates"
        return result
    start, end = common[0], common[-1]
    result.update(start=start, end=end)
    try:
        returns = {name: _return_pct(_ratio(curve[end], curve[start]))
                   for name, curve in usable.items()}
        deltas = []
        for left, right in pairs:
            delta = returns[left] - returns[right]
            if not isfinite(delta):
                raise ArithmeticError("unrepresentable delta")
            deltas.append({"left_id": left, "right_id": right, "delta_pp": delta})
    except ArithmeticError:
        result["reason"] = "numeric_range"
        return result
    result.update(status="descriptive", returns_pct=returns, deltas_pp=tuple(deltas))
    return result


def aligned_regime_envelope(
    spy_curve: Mapping, defensive_curve: Mapping, *, start: str, end: str,
    asof: str, regime: Mapping | None,
) -> dict:
    """Recompute the US regime envelope on one explicit caller-selected window.

    Pass source SPY and defensive wealth curves, never an old maximum envelope.
    Select the book/cohort interval first, then recompute at that exact start.
    This result is bound to that window; rebasing it later is not equivalent to
    recomputing its components and is unsupported.

    The single injected regime applies uniformly, preserving benchmark_ledger's
    risk-on/plain-SPY and WEAKENING/defensive-allowed rule. Only supplied usable
    SPY dates within the window appear. Missing defensive base means SPY-only
    throughout; missing defensive dates mean SPY-only on those dates. Coverage
    labels distinguish that fallback from a two-component maximum. A fallback
    return does not establish that defense was flat, fully observed, or beaten.

    This US-only function neither selects a regional benchmark nor implements
    holdings/currency policy. Missing SPY endpoints or unrepresentable computed
    values return unavailable, with no synthetic endpoints or numeric outputs.
    """
    for name, value in (("start", start), ("end", end), ("asof", asof)):
        _require_date(value, name)
    if not start < end <= asof:
        raise ValueError("window must satisfy start < end <= asof")
    if regime is not None and not isinstance(regime, Mapping):
        raise ValueError("regime must be a mapping or None")
    spy = _usable_curve(spy_curve, asof)
    defense = _usable_curve(defensive_curve, asof)
    r = regime or {}
    state = str(r.get("state") or r.get("risk_state") or "risk_on").lower()
    transition = str(r.get("transition_state") or r.get("transition") or "").upper()
    use_defense = state != "risk_on" or transition == "WEAKENING"
    result = {
        "status": "unavailable", "reason": None, "asof": asof, "start": start, "end": end,
        "component_ids": ("spy", "defensive"), "curve": None, "coverage": None,
        "return_pct": None, "defensive_return_pct": None,
    }
    if start not in spy or end not in spy:
        result["reason"] = "missing_spy_endpoint"
        return result
    curve, coverage = {}, {}
    try:
        for day in sorted(day for day in spy if start <= day <= end):
            sv = _ratio(spy[day], spy[start])
            if not use_defense:
                value, source = sv, "spy_only_regime"
            elif start not in defense:
                value, source = sv, "spy_only_missing_defensive_base"
            elif day not in defense:
                value, source = sv, "spy_only_missing_defensive_point"
            else:
                value = max(sv, _ratio(defense[day], defense[start]))
                source = "spy_and_defensive"
            curve[day], coverage[day] = value, source
        return_pct = _return_pct(curve[end])
        defensive_return_pct = None
        if use_defense and start in defense and end in defense:
            defensive_return_pct = _return_pct(_ratio(defense[end], defense[start]))
    except ArithmeticError:
        result["reason"] = "numeric_range"
        return result
    result.update(status="descriptive", curve=curve, coverage=coverage,
                  return_pct=return_pct, defensive_return_pct=defensive_return_pct)
    return result
