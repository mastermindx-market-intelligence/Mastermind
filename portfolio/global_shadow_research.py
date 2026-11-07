"""Fail-closed, research-only cross-asset scenario context.

Uses the incumbent portfolio.global_scenario_context.compare for arithmetic
and constraints. Macro's daily ETF observations are descriptive context ONLY;
they never become return assumptions, executable quotes, forecasts or trades.

No file, network, account, clock, persistence, active allocator or model calls.
The source digest is format-checked, not independently authenticated.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from numbers import Real
from typing import Any

from portfolio.global_scenario_context import AUTHORITY, ContractError, compare

SCHEMA = "mastermind.global_shadow_research/v1"
SOURCE_SCHEMA = "mastermind.multi_asset_daily_context/v1"
SOURCE_METHOD = "same_us_cash_session_snapshot.v1"
SOURCE_KIND = "captured_mutable_daily_cache"
ALIGNMENT = "US_CASH_SESSION_LABEL_NOT_QUOTE_TIMESTAMP"
COHERENCE = "individually_hashed_not_atomic_bundle"
POLICY = "global_research_shadow_only:v1"
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_STATES = frozenset(("AVAILABLE", "PARTIAL", "STALE", "UNAVAILABLE"))
_CLASS = frozenset((
    "POSITIVE_AND_OUTPERFORMING", "RELATIVE_RESILIENCE_ONLY",
    "UNDERPERFORMING", "IN_LINE",
))
_LIMITS = (
    "not_intraday", "not_native_foreign_market_returns", "not_observed_fund_flows",
    "not_point_in_time_backtest_evidence", "funds_may_overlap",
    "cash_is_separate_from_short_duration_funds", "not_an_allocation_recommendation",
)

# Exactly the existing Macro US-listed proxy universe. Factor tags are overlapping
# descriptive risk labels, NOT issuer look-through, true hedges or trade permission.
ROSTER: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "SPY": ("equity", "US", ("asset:equity", "region:US", "equity_beta")),
    "EFA": ("equity", "DM_EX_US", ("asset:equity", "region:DM_EX_US", "equity_beta", "non_us")),
    "EEM": ("equity", "EM", ("asset:equity", "region:EM", "equity_beta", "non_us", "em_equity")),
    "FXI": ("equity", "CHINA_HK", ("asset:equity", "region:CHINA_HK", "equity_beta", "em_equity", "china_equity")),
    "KWEB": ("equity", "CHINA_OFFSHORE", ("asset:equity", "region:CHINA_OFFSHORE", "equity_beta", "em_equity", "china_equity")),
    "GLD": ("gold", "GLOBAL", ("asset:gold", "region:GLOBAL", "metals")),
    "HYG": ("credit", "US", ("asset:credit", "region:US", "credit_risk", "rates_factor")),
    "SHY": ("rates", "US", ("asset:rates", "region:US", "rates_factor", "short_duration")),
    "TLT": ("rates", "US", ("asset:rates", "region:US", "rates_factor", "long_duration")),
    "USO": ("energy", "GLOBAL", ("asset:energy", "region:GLOBAL", "commodity_beta")),
    "IBIT": ("crypto", "GLOBAL", ("asset:crypto", "region:GLOBAL", "crypto_beta")),
}


def _date(s: Any) -> date | None:
    if not isinstance(s, str) or not _DAY.fullmatch(s):
        return None
    try:
        d = date.fromisoformat(s)
        return d if d.isoformat() == s else None
    except (ValueError, OverflowError):
        return None


def _time(s: Any) -> datetime | None:
    if not isinstance(s, str) or len(s) > 45 or "T" not in s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo and t.utcoffset() is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _number(s: Any, lower: float = -math.inf) -> float | None:
    if isinstance(s, bool) or not isinstance(s, Real):
        return None
    try:
        v = float(s)
        return v if math.isfinite(v) and v >= lower else None
    except (ValueError, TypeError, OverflowError):
        return None


def _bounded(s: Any, size: int = 128) -> bool:
    return isinstance(s, str) and 0 < len(s) <= size and s.strip() == s


def _seq(s: Any) -> bool:
    return isinstance(s, Sequence) and not isinstance(s, (str, bytes, bytearray))


def _context_status(ctx: Mapping[str, Any], as_of: datetime) -> tuple[str | None, str, dict[str, Any]]:
    """Validate the fixed descriptive universe; do not trust caller attestations.

    Return (error, classified_source_state, recognized_qualified_rows).
    A valid STALE source remains usable *only* as historical context.
    """
    if (ctx.get("schema") != SOURCE_SCHEMA or ctx.get("method_version") != SOURCE_METHOD):
        return "context_schema_invalid", "UNAVAILABLE", {}
    authority = ctx.get("authority")
    if (not isinstance(authority, Mapping) or set(authority) !=
            {"can_rank", "can_gate", "can_size", "can_trade"} or
            any(v is not False for v in authority.values()) or
            ctx.get("display_only") is not True or ctx.get("no_predictive_claim") is not True):
        return "context_authority_invalid", "UNAVAILABLE", {}
    if (ctx.get("source_kind") != SOURCE_KIND or ctx.get("alignment_basis") != ALIGNMENT or
            ctx.get("capture_coherence") != COHERENCE or ctx.get("provider_available_at", "MISSING") is not None or
            ctx.get("historical_original_availability_proven") is not False or
            ctx.get("base_currency") != "USD" or ctx.get("benchmark_instrument_id") != "SPY" or
            not isinstance(ctx.get("context_digest"), str) or
            not _DIGEST.fullmatch(ctx["context_digest"]) or
            ctx.get("limitations") != list(_LIMITS)):
        return "context_source_basis_invalid", "UNAVAILABLE", {}
    captured = _time(ctx.get("captured_at"))
    window = ctx.get("window")
    if captured is None or captured > as_of or not isinstance(window, Mapping):
        return "context_clock_unqualified", "UNAVAILABLE", {}
    start, end, expected = (
        _date(window.get("start_session")), _date(window.get("end_session")),
        _date(window.get("expected_session")),
    )
    horizon = window.get("horizon_sessions")
    if (not start or not end or not expected or not start < end <= expected or
            end > captured.date() or expected > as_of.date() or
            isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 252 or
            window.get("calendar_owner") != "lib.nyse_calendar" or
            window.get("listing_timezone") != "America/New_York"):
        return "context_window_invalid", "UNAVAILABLE", {}
    coverage = ctx.get("coverage")
    if not isinstance(coverage, Mapping):
        return "context_coverage_invalid", "UNAVAILABLE", {}
    counts = tuple(coverage.get(k) for k in ("requested", "observed", "comparable", "invalid_sources"))
    if (any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in counts) or
            counts[0] != len(ROSTER) or counts[1] > counts[0] or
            counts[2] > counts[1] or counts[3] > counts[0]):
        return "context_coverage_invalid", "UNAVAILABLE", {}
    rows = ctx.get("rows")
    if not _seq(rows) or len(rows) != len(ROSTER):
        return "context_roster_invalid", "UNAVAILABLE", {}
    # Reject duplicate or unexpected identities BEFORE validating metadata. A
    # malformed duplicate must never be accepted as a newer revision/overwrite.
    ids = [r.get("instrument_id") if isinstance(r, Mapping) else None for r in rows]
    if any(not isinstance(i, str) or i not in ROSTER for i in ids) or len(set(ids)) != len(ROSTER):
        return "context_roster_invalid", "UNAVAILABLE", {}
    if not _seq(ctx.get("reasons")) or len(ctx["reasons"]) > 30 or any(not _bounded(s) for s in ctx["reasons"]):
        return "context_reasons_invalid", "UNAVAILABLE", {}
    eligible: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    observed = comp = 0
    bench: float | None = None
    for raw in rows:
        if not isinstance(raw, Mapping):
            return "context_row_invalid", "UNAVAILABLE", {}
        identity = raw.get("instrument_id")
        if not isinstance(identity, str) or identity not in ROSTER or identity in seen:
            return "context_roster_invalid", "UNAVAILABLE", {}
        seen.add(identity)
        asset, region, factors = ROSTER[identity]
        if (raw.get("asset_class") != asset or raw.get("exposure_region") != region or
                raw.get("listing_market") != "US" or raw.get("currency") != "USD" or
                raw.get("return_basis") != "total_return" or
                raw.get("evidence_family_id") != "yahoo_daily_adjusted_prices" or
                raw.get("source_ref") != f"data/yahoo/{identity}.parquet" or
                not _bounded(raw.get("label_en")) or not _bounded(raw.get("label_zh")) or
                raw.get("start_session") != start.isoformat() or
                raw.get("end_session") != end.isoformat() or
                raw.get("status") not in ("OBSERVED", "UNAVAILABLE")):
            return "context_row_invalid", "UNAVAILABLE", {}
        source_last = _date(raw.get("last_source_session"))
        if source_last is not None and source_last > end:
            return "context_source_session_invalid", "UNAVAILABLE", {}
        row_reason = raw.get("reasons")
        if not _seq(row_reason) or len(row_reason) > 20 or any(not _bounded(s) for s in row_reason):
            return "context_row_reasons_invalid", "UNAVAILABLE", {}
        sd = raw.get("source_digest")
        if sd is not None and (not isinstance(sd, str) or not _DIGEST.fullmatch(sd)):
            return "context_source_digest_invalid", "UNAVAILABLE", {}
        if raw["status"] == "OBSERVED":
            absolute = _number(raw.get("absolute_return"), -1)
            if absolute is None or sd is None or source_last != end or row_reason:
                return "context_observation_invalid", "UNAVAILABLE", {}
            observed += 1
            if identity == "SPY":
                bench = absolute
                if (raw.get("relative_return") is not None or raw.get("classification") is not None or
                        raw.get("comparison_status") is not None):
                    return "context_benchmark_invalid", "UNAVAILABLE", {}
            elif raw.get("comparison_status") == "OBSERVED":
                relative = _number(raw.get("relative_return"))
                kind = raw.get("classification")
                if relative is None or not isinstance(kind, str) or kind not in _CLASS:
                    return "context_relative_invalid", "UNAVAILABLE", {}
                comp += 1
            elif (raw.get("comparison_status") not in ("UNAVAILABLE", None) or
                  raw.get("relative_return") is not None or raw.get("classification") is not None):
                return "context_relative_invalid", "UNAVAILABLE", {}
            eligible[identity] = {
                "instrument_id": identity, "eligibility": "QUALIFIED",
                "currency": "USD", "policy_ref": POLICY,
                "risk_keys": sorted(factors),
            }
        else:
            if (not row_reason or raw.get("absolute_return") is not None or
                    raw.get("relative_return") is not None or raw.get("classification") is not None or
                    raw.get("comparison_status") is not None):
                return "context_unavailable_row_invalid", "UNAVAILABLE", {}
    if seen != set(ROSTER) or bench is None or bench <= -1:
        return "context_benchmark_unavailable", "UNAVAILABLE", {}
    if _number(ctx.get("benchmark_return"), -1) != bench:
        return "context_benchmark_mismatch", "UNAVAILABLE", {}
    if observed != counts[1] or comp != counts[2]:
        return "context_coverage_disagreement", "UNAVAILABLE", {}
    for row in rows:
        if row["status"] != "OBSERVED" or row["instrument_id"] == "SPY" or row.get("comparison_status") != "OBSERVED":
            continue
        absolute = float(row["absolute_return"])
        relative = float(row["relative_return"])
        calculated = (1 + absolute) / (1 + bench) - 1
        if not math.isfinite(calculated) or abs(calculated - relative) > 1e-8:
            return "context_relative_math_invalid", "UNAVAILABLE", {}
        classification = ("POSITIVE_AND_OUTPERFORMING" if absolute > 0 and relative > 0 else
                          "RELATIVE_RESILIENCE_ONLY" if absolute <= 0 and relative > 0 else
                          "UNDERPERFORMING" if relative < 0 else "IN_LINE")
        if row["classification"] != classification:
            return "context_classification_invalid", "UNAVAILABLE", {}
    expected_status = ("UNAVAILABLE" if not comp else
                       "STALE" if end < expected else
                       "PARTIAL" if observed < len(ROSTER) or counts[3] or comp < observed - 1 else
                       "AVAILABLE")
    if ctx.get("status") != expected_status:
        return "context_status_mismatch", "UNAVAILABLE", {}
    expected_reasons = (["benchmark_unavailable" if bench is None else "no_comparable_returns"] if not comp
                        else ["older_than_expected_session"] if end < expected else [])
    if list(ctx["reasons"]) != expected_reasons:
        return "context_reasons_mismatch", "UNAVAILABLE", {}
    return None, expected_status, eligible


def _unavailable(as_of: str, reason: str, *, source_status: str = "UNAVAILABLE") -> dict[str, Any]:
    return {
        "schema": SCHEMA, "method_version": "research_only_core_delegate.v1",
        "as_of": as_of, "status": "UNAVAILABLE", "reasons": [reason], "alternatives": [],
        "market_context": {"status": source_status, "source_authenticated": False},
        "scenario_basis": "hypothetical_not_forecast",
        "display_only": True, "hypothetical_only": True,
        "no_predictive_claim": True, "authority": dict(AUTHORITY),
    }


def compare_global_shadow(*, context: Mapping[str, Any], book: Mapping[str, Any],
                          alternatives: Sequence[Mapping[str, Any]],
                          scenarios: Sequence[Mapping[str, Any]], as_of: str) -> dict[str, Any]:
    """Research-only, user-supplied what-if for the fixed US ETF proxy universe.

    Never treats historical ETF returns as scenario assumptions. All-supplied
    base-currency scenario P&L, costs, exposure ceilings and missingness are
    delegated without modifications to the incumbent pure comparison owner.
    """
    when = _time(as_of)
    if when is None:
        raise ContractError("aware_as_of_required")
    at = when.isoformat().replace("+00:00", "Z")
    if (not isinstance(context, Mapping) or not isinstance(book, Mapping) or
            not _seq(alternatives) or not _seq(scenarios)):
        raise ContractError("mapping_and_sequences_required")
    if len(alternatives) > 30 or len(scenarios) > 30:
        raise ContractError("too_many_alternatives_or_scenarios")
    problem, source_state, eligible = _context_status(context, when)
    if problem:
        return _unavailable(at, problem, source_status=source_state)
    if (book.get("book_id") != "global_research_shadow" or
            book.get("research_only") is not True or
            book.get("active_account") is not False or
            book.get("user_supplied_scenario_assumptions") is not True or
            book.get("base_currency") != "USD" or
            not _bounded(book.get("book_revision"))):
        return _unavailable(at, "research_book_identity_invalid", source_status=source_state)
    if any(k in book for k in ("account_id", "tenant_id", "broker_id", "order_id", "account", "auth_token", "universe")):
        return _unavailable(at, "active_account_identity_prohibited", source_status=source_state)
    supplied = book.get("positions")
    if not isinstance(supplied, Mapping):
        return _unavailable(at, "book_positions_invalid", source_status=source_state)
    if any(not isinstance(k, str) or k not in eligible for k in supplied):
        return _unavailable(at, "held_instrument_unavailable", source_status=source_state)
    # The same caller-provided snapshot/constraints pass through the native core;
    # only the untrusted instrument universe is replaced with the fixed roster.
    derived = {
        "book_id": "global_research_shadow",
        "book_revision": book["book_revision"],
        "known_at": book.get("known_at"),
        "valid_until": book.get("valid_until"),
        "base_currency": "USD",
        "positions": dict(supplied),
        "cash_weight": book.get("cash_weight"),
        "constraints": book.get("constraints"),
        "universe": [eligible[k] for k in sorted(eligible)],
    }
    # This is an explicit assertion that inputs are hypothetical, NOT a vendor
    # inference. The original core still qualifies the source and numeric rows.
    if any(not isinstance(s, Mapping) or s.get("assumption_kind") != "hypothetical" for s in scenarios):
        return _unavailable(at, "scenario_hypothetical_declaration_missing", source_status=source_state)
    base = compare(derived, alternatives, scenarios, as_of=at)
    result = dict(base)
    result["schema"] = SCHEMA
    result["method_version"] = "research_only_core_delegate.v1"
    result["source_computation_status"] = base.get("status")
    # Keep original result status as the arithmetic qualification only, never
    # a statement that source is realtime, independently verified or actionable.
    result["market_context"] = {
        "status": source_state,
        "source_session": context["window"]["end_session"],
        "expected_session": context["window"]["expected_session"],
        "context_digest": context["context_digest"],
        "coverage": dict(context["coverage"]),
        "source_authenticated": False,
        "input_basis": "operator_supplied_descriptive_context",
        "return_window_kind": "historical_us_listed_etf_adjusted",
        "eligible_ids": sorted(eligible),
        "excluded_ids": sorted(set(ROSTER).difference(eligible)),
        "allocation_authority": False,
    }
    result["scenario_basis"] = "hypothetical_not_forecast"
    result["display_only"] = True
    result["hypothetical_only"] = True
    result["no_predictive_claim"] = True
    result["authority"] = dict(AUTHORITY)
    return result
