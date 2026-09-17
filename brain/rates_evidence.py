"""Bounded RIC evidence for the existing decision_context, not a signal engine.

No fetching, writing, scoring, or historical-vintage certification. An explicit
cutoff withholds untimed or later-built values; it cannot reconstruct past data.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
import re
from typing import Any

_TENORS = ("2y", "5y", "10y", "20y", "30y")
_HORIZONS = ("5d", "22d", "63d")
_WATCHES = {"rolldown_forming", "extreme_high_watch", "rollup_forming", "extreme_low_watch"}
_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$")
_SOURCE = "vendor/macro/data/rates_command/latest.json"


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _day(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _clock(value: Any) -> tuple[str, datetime | None]:
    if value is None:
        return "missing", None
    if _day(value) is not None:
        return "date_only", None
    if not isinstance(value, str) or not _INSTANT.fullmatch(value):
        return "invalid", None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return "known", dt.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return "invalid", None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, OverflowError):
        return None


def project_rates(
    artifact: Any,
    *,
    market_asof: str | None = None,
    analysis_cutoff: str | None = None,
) -> dict[str, Any]:
    """Project daily nominal evidence; never certify an as-observed replay.

    Current context requires a matching observation date and a usable source
    status. Cutoff inspection additionally requires timestamped availability and
    a producer build no later than the cutoff. Neither proves vintage lineage.
    """
    raw = _dict(artifact)
    momentum = _dict(raw.get("yield_momentum"))
    rows = _dict(momentum.get("series"))
    market_day = _day(market_asof)
    artifact_day = _day(raw.get("asof"))
    build_kind, built = _clock(raw.get("built"))
    cutoff_kind, cutoff = _clock(analysis_cutoff)
    strict = analysis_cutoff is not None
    valid_source = (raw.get("schema") == "rates_command.v1"
                    and momentum.get("schema") == "yield_momentum.v1")
    issues: list[str] = []
    blocked = not valid_source or market_day is None
    if not raw:
        issues.append("source_missing")
    elif not valid_source:
        issues.append("unsupported_source_schema")
    if market_day is None:
        issues.append("invalid_market_asof")
    if strict and cutoff is None:
        issues.append("invalid_analysis_cutoff")
        blocked = True
    if strict and built is None:
        issues.append("producer_build_time_unknown")
        blocked = True
    if strict and built and cutoff and built > cutoff:
        issues.append("producer_build_after_cutoff")
        blocked = True
    if market_day and artifact_day and artifact_day > market_day:
        issues.append("artifact_wrapper_after_market_asof")

    series: dict[str, dict[str, Any]] = {}
    for tenor in _TENORS:
        source = _dict(rows.get(tenor)) if valid_source else {}
        row_issues: list[str] = []
        usable = not blocked
        observed = _day(source.get("as_of"))
        availability_kind, available = _clock(source.get("available_at"))
        status = source.get("status")
        status = status if status in ("available", "insufficient_history", "stale", "missing") else "unknown"
        if status not in ("available", "insufficient_history"):
            row_issues.append("source_status_" + status)
            usable = False
        if source.get("source_column") != "us" + tenor:
            row_issues.append("unexpected_source_column")
            usable = False
        if observed is None:
            row_issues.append("invalid_observation_date")
            usable = False
        elif market_day and observed != market_day:
            row_issues.append("observation_after_market_asof" if observed > market_day
                              else "observation_before_market_asof")
            usable = False
        if available is None:
            row_issues.append(availability_kind + "_available_at")
            if strict:
                usable = False
        elif cutoff and available > cutoff:
            row_issues.append("availability_after_cutoff")
            usable = False
        if available and built and available > built:
            row_issues.append("availability_after_producer_build")
            usable = False
        level = _number(source.get("level"))
        if level is None:
            row_issues.append("missing_or_invalid_level")
            usable = False
        velocity = _dict(source.get("velocity_bp"))
        projected_velocity = {h: _number(velocity.get(h)) for h in _HORIZONS}
        if any(v is None for v in projected_velocity.values()):
            row_issues.append("momentum_horizon_incomplete")
        watch = source.get("turn_watch")
        watch = watch if isinstance(watch, str) and watch in _WATCHES else None
        series[tenor] = {
            "source_column": "us" + tenor,
            "source_status": status,
            "observation_date": observed.isoformat() if observed else None,
            "age_calendar_days": (market_day - observed).days if market_day and observed else None,
            "available_at": available.isoformat() if available else None,
            "availability_kind": availability_kind,
            "usable_for_context": usable,
            "level": level if usable else None,
            "velocity_bp": projected_velocity if usable else {h: None for h in _HORIZONS},
            "acceleration_bp": _number(source.get("acceleration_bp")) if usable else None,
            "turn_watch": watch if usable else None,
            "issues": row_issues,
        }
    count = sum(row["usable_for_context"] for row in series.values())
    return {
        "schema": "decision_context.rates_evidence.v1",
        "source_contract": "rates_command.v1 / yield_momentum.v1",
        "source_ref": _SOURCE,
        "status": "available_context" if count == len(_TENORS) else "partial_context" if count else "unavailable",
        "market_asof": market_day.isoformat() if market_day else None,
        "artifact_asof": artifact_day.isoformat() if artifact_day else None,
        "producer_built_at": built.isoformat() if built else None,
        "producer_build_time_kind": build_kind,
        "analysis_cutoff": cutoff.isoformat() if cutoff else None,
        "analysis_mode": "cutoff_inspection" if strict else "current_context",
        "level_unit": "percent",
        "change_unit": "basis_points",
        "horizon_basis": "observed_intervals_not_verified_exchange_sessions",
        "acceleration_definition": "current_22_observed_interval_change_minus_prior_22",
        "series": series,
        "coverage": {"requested_rows": len(_TENORS), "context_rows": count,
                     "timed_context_rows": sum(row["usable_for_context"] and row["availability_kind"] == "known"
                                               for row in series.values())},
        "as_observed_replay_certified": False,
        "capabilities": {"nominal_yield_momentum_context": bool(count),
                         "real_yield_momentum": False,
                         "meeting_specific_surprise": False,
                         "intraday_rate_timing": False},
        "authority": {"allowed_effect": "annotate_only", "can_rank": False,
                      "can_score": False, "can_size": False, "can_gate": False, "can_trade": False},
        "issues": issues,
        "limitations": ["Daily nominal observations, not intraday rates or real yields.",
                        "Turn watches describe source state, not confirmed reversals or entry signals.",
                        "Source schema lacks historical-vintage lineage; cutoff inspection is not certified replay."],
    }
