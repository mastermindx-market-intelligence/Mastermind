"""Bounded RIC evidence for the existing decision_context, not a signal engine.

No fetching, writing, scoring, or historical-vintage certification. An explicit
cutoff withholds untimed or later-built values; it cannot reconstruct past data.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from copy import deepcopy
import json
import math
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def _market_date(instant: datetime | None) -> date | None:
    """US observation labels use New York dates, never host-local or UTC dates."""
    if instant is None:
        return None
    try:
        return instant.astimezone(ZoneInfo("America/New_York")).date()
    except (ZoneInfoNotFoundError, ValueError, OverflowError):
        return None


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
    cutoff_day = _market_date(cutoff)
    build_day = _day(raw.get("built")) if build_kind == "date_only" else _market_date(built)
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
        available_day = (_day(source.get("available_at")) if availability_kind == "date_only"
                         else _market_date(available))
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
        if observed is not None:
            for instant, local_day, reason in (
                (available, available_day, "observation_after_available_date"),
                (built, build_day, "observation_after_producer_build_date"),
                (cutoff, cutoff_day, "observation_after_cutoff_market_date"),
            ):
                if instant is not None and local_day is None:
                    row_issues.append("market_timezone_conversion_unavailable")
                    usable = False
                elif local_day is not None and observed > local_day:
                    row_issues.append(reason)
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
        "market": "US",
        "observation_timezone": "America/New_York",
        "observation_origin": "unverified",
        "current_session_freshness": "not_certified",
        "freshness_basis": "frame_alignment_only",
        "status": "available_context" if count == len(_TENORS) else "partial_context" if count else "unavailable",
        "market_asof": market_day.isoformat() if market_day else None,
        "artifact_asof": artifact_day.isoformat() if artifact_day else None,
        "producer_built_at": built.isoformat() if built else None,
        "producer_build_time_kind": build_kind,
        "analysis_cutoff": cutoff.isoformat() if cutoff else None,
        "analysis_mode": "cutoff_inspection" if strict else "dated_context",
        "level_unit": "percent",
        "change_unit": "basis_points",
        "horizon_basis": "source_frame_intervals",
        "acceleration_definition": "current_22_frame_interval_change_minus_prior_22",
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
        "limitations": ["Daily nominal frame; may be forward-filled, not raw rate ticks.",
                        "Turn watches describe source state, not confirmed reversals or entry signals.",
                        "Source schema lacks historical-vintage lineage; cutoff inspection is not certified replay."],
    }


def annotate_ticker_package(
    package: dict[str, Any],
    rates: Any,
    *,
    intelligence_artifact_asof: Any = None,
) -> dict[str, Any]:
    """Attach existing market context without changing a name's evidence or rank.

    This is not a candidate-episode join. The two artifacts retain separate dates;
    no historical receipt, ticker beta, leadership, or entry decision is inferred.
    """
    unavailable = project_rates(None)
    candidate = _dict(rates)
    valid = (
        candidate.get("schema") == unavailable["schema"]
        and candidate.get("authority") == unavailable["authority"]
        and candidate.get("as_observed_replay_certified") is False
        and candidate.get("current_session_freshness") == "not_certified"
        and set(unavailable).issubset(candidate)
    )
    try:
        valid = valid and len(json.dumps(candidate, allow_nan=False).encode("utf-8")) <= 16000
    except (TypeError, ValueError, OverflowError):
        valid = False
    if not valid:
        candidate = unavailable
        candidate["issues"].append("rates_context_contract_unavailable")
    # The projector owns the schema; unknown top-level additions are not forwarded.
    evidence = {key: deepcopy(candidate[key]) for key in unavailable}
    day = _day(intelligence_artifact_asof)
    time_kind, instant = _clock(intelligence_artifact_asof)
    artifact_label = day.isoformat() if day else instant.isoformat() if instant else None
    out = dict(package)
    out["rates_context"] = evidence
    out["rates_context_status"] = evidence["status"]
    out["rates_relationship"] = {
        "scope": "US_market_context_only",
        "ticker_specific_sensitivity": "not_provided",
        "decision_time_join": "not_established",
        "intelligence_artifact_asof": artifact_label,
        "intelligence_time_kind": time_kind,
        "historical_candidate_evidence_modified": False,
    }
    return out



def _columnar_ticker_rates(rates: dict[str, Any]) -> dict[str, Any] | None:
    """Lossless presentation only: factor repeated row fields, never omit facts."""
    series = _dict(rates.get("series"))
    if set(series) != set(_TENORS):
        return None
    first = _dict(series[_TENORS[0]])
    if not first or any(set(_dict(series[t])) != set(first) for t in _TENORS):
        return None
    shared = {key: deepcopy(value) for key, value in first.items()
              if all(series[t][key] == value for t in _TENORS)}
    columns = [key for key in first if key not in shared]
    packed = {key: deepcopy(value) for key, value in rates.items()
              if key not in ("schema", "series")}
    packed["schema"] = "decision_context.rates_evidence.columnar.v1"
    packed["source_schema"] = rates["schema"]
    packed["series"] = {
        "shared": shared,
        "columns": columns,
        "rows": {tenor: [deepcopy(series[tenor][key]) for key in columns] for tenor in _TENORS},
    }
    return packed


def serialize_ticker_package(package: dict[str, Any], serializer: Any) -> dict[str, Any]:
    """Preserve the existing stock serializer's result and add lossless rates.

    The generic owner sees primary stock evidence exactly once. Its decoded
    result is never subjected to another lossy compaction because of this
    optional context. Only JSON whitespace and repeated rates fields may shrink.
    The 8,000-byte ceiling is this consumer's budget, not a claimed SDK limit.
    """
    protected = ("rates_context", "rates_context_status", "rates_relationship")
    primary = {key: value for key, value in package.items() if key not in protected}
    baseline = None
    envelope = None
    try:
        envelope = serializer(deepcopy(primary))
        content = envelope["content"]
        if len(content) == 1 and content[0].get("type") == "text":
            text = content[0]["text"]
            if isinstance(text, str) and len(text) <= 64000:
                decoded = json.loads(text)
                if isinstance(decoded, dict):
                    baseline = decoded
    except Exception:  # backend exception contents are not research evidence
        baseline = None

    def encode(value: dict[str, Any]) -> dict[str, Any] | None:
        try:
            text = json.dumps(value, ensure_ascii=False, allow_nan=False,
                              separators=(",", ":"))
            if len(text.encode("utf-8")) > 8000 or envelope is None:
                return None
            response = deepcopy(envelope)
            response["content"][0]["text"] = text
            return response
        except Exception:  # invalid JSON scalars/encoding are closed unavailable
            return None

    if baseline is not None:
        full = {**baseline, **{key: deepcopy(package.get(key)) for key in protected}}
        response = encode(full)
        if response is not None:
            return response
        packed_rates = _columnar_ticker_rates(_dict(package.get("rates_context")))
        if packed_rates is not None:
            packed = {**full, "rates_context": packed_rates,
                      "rates_context_encoding": "columnar_shared_fields_v1"}
            response = encode(packed)
            if response is not None:
                return response
        # No rates numbers remain, so there is no numerical join to qualify.
        reduced = {**baseline, "rates_context_status": "omitted_transport_budget",
                   "rates_context_tool": "get_rates_evidence"}
        response = encode(reduced)
        if response is not None:
            return response
    ticker = package.get("ticker")
    ticker = ticker[:32] if isinstance(ticker, str) else None
    failure = {"ticker": ticker, "status": "unavailable_transport_budget",
               "rates_context_status": "omitted_transport_budget",
               "decision_time_join": "not_established",
               "next_reads": ["get_intelligence", "get_rates_evidence"]}
    return {"content": [{"type": "text", "text": json.dumps(failure, allow_nan=False)}]}
