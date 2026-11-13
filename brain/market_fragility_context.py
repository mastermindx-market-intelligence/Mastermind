"""Compact consumer of Macro's canonical descriptive fragility observation.

This is a read-time contract/freshness adapter, not a gamma estimator, risk score,
validation gate or trade policy. Macro owns the source and its calculations.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Any

_SCHEMA = "market_fragility/v1"
_SOURCE = "cboe/gex_SPX"
_AUTHORITY = {
    "display_only": True, "directional_signal": False, "ranking": False,
    "position_sizing": False, "risk_override": False, "trade_execution": False,
}


def _unknown(reason: str) -> dict[str, Any]:
    return {
        "schema": _SCHEMA, "status": "unavailable", "state": "unknown",
        "reason": reason, "authority": dict(_AUTHORITY),
        "predictive_validation": "not_established",
    }


def _clock(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo is not None else None
    except ValueError:
        return None


def _day(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def project_market_fragility(payload: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Validate and re-age an optional published observation without re-deriving it."""
    if payload is None:
        return _unknown("not_published")
    if not isinstance(payload, dict) or payload.get("schema") != _SCHEMA:
        return _unknown("invalid_schema")
    fields = ("source", "clocks", "current", "history", "quality", "authority")
    if any(not isinstance(payload.get(key), dict) for key in fields):
        return _unknown("invalid_contract")
    source, clocks, current = (payload[key] for key in fields[:3])
    quality, authority = payload["quality"], payload["authority"]
    if (source.get("id") != _SOURCE or source.get("instrument") != "SPX"
            or source.get("position_basis") != "assumption"
            or source.get("actual_dealer_inventory_observed") is not False):
        return _unknown("unsupported_source_basis")
    if any(authority.get(key) is not expected for key, expected in _AUTHORITY.items()):
        return _unknown("unexpected_authority")
    if (quality.get("point_in_time_qualified") is not False
            or quality.get("predictive_validation") != "not_established"):
        return _unknown("unsupported_validation_claim")
    if current.get("net_gex_unit") != "USD_bn_per_1pct_underlying_move":
        return _unknown("unsupported_units")
    if payload["history"].get("source") != _SOURCE:
        return _unknown("mixed_history_source")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    computed = _clock(clocks.get("computed_at"))
    if computed is None or computed > now:
        return _unknown("invalid_computation_clock")
    # Reuse the vendored calendar owner. A missing dependency is an unavailable
    # observation, not permission to approximate weekdays and invent freshness.
    try:
        from lib import nyse_calendar
        today = now.astimezone(nyse_calendar.ET).date()
        day = _day(clocks.get("source_session"))
        eligible = day is not None and day <= today and nyse_calendar.is_session(day)
        age = nyse_calendar.sessions_behind(day, now) if eligible else None
    except Exception:  # noqa: BLE001 - optional context cannot break core regime
        return _unknown("calendar_unavailable")
    if day is not None and day > computed.astimezone(nyse_calendar.ET).date():
        return _unknown("source_postdates_computation")
    for key in ("source_observed_at", "source_available_at"):
        raw = clocks.get(key)
        clock = _clock(raw)
        if raw is not None and (clock is None or clock > computed):
            return _unknown("invalid_source_clock")
    sign = current.get("reported_gamma_regime")
    state = payload.get("state")
    if not isinstance(state, str) or state not in {"amplifying", "damping", "unknown"}:
        return _unknown("invalid_state")
    if current.get("usable") is True:
        expected = {"short": "amplifying", "long": "damping"}.get(sign) if isinstance(sign, str) else None
        if state != expected:
            return _unknown("inconsistent_state")
    elif current.get("usable") is not False or state != "unknown":
        return _unknown("inconsistent_state")
    usable = current["usable"] and eligible and age == 0
    reasons = quality.get("reasons")
    if not isinstance(reasons, list) or any(not isinstance(x, str) for x in reasons) or len(reasons) > 32:
        return _unknown("invalid_quality_reasons")
    if current["usable"] and reasons:
        return _unknown("inconsistent_quality")
    history = payload["history"]
    history_keys = (
        "window_sessions", "observed_sessions", "unknown_sessions", "short_sessions",
        "long_sessions", "short_share_observed", "coverage_fraction", "adjacent_pairs_observed",
        "sign_changes", "terminal_run_sessions", "max_long_run_sessions", "observed_regime_runs",
    )
    h = {key: _number(history.get(key)) for key in history_keys}
    h.update(window_end=history.get("window_end") if _day(history.get("window_end")) else None,
             terminal_regime=history.get("terminal_regime") if history.get("terminal_regime") in ("long", "short") else None,
             counts_are_independent_trials=False,
             terminal_run_left_censored=history.get("terminal_run_left_censored") is True)
    out: dict[str, Any] = {
        "schema": _SCHEMA, "status": "current" if usable else "stale" if age is not None and age > 0 else "unavailable",
        "state": state if usable else "unknown", "source": _SOURCE, "position_basis": "assumption",
        "source_session": day.isoformat() if day else None,
        "source_age_sessions_at_read": age, "computed_at": clocks["computed_at"],
        "source_available_at": clocks.get("source_available_at"),
        "reported_gamma_regime": sign if isinstance(sign, str) and sign in {"short", "long"} else None,
        "reported_net_gex_bn": _number(current.get("reported_net_gex_bn")),
        "net_gex_unit": "USD_bn_per_1pct_underlying_move",
        "gamma_flip": _number(current.get("gamma_flip")),
        "history": h, "reasons": [x[:160] for x in reasons],
        "predictive_validation": "not_established", "point_in_time_qualified": False,
        "authority": dict(_AUTHORITY),
        "interpretation": "Gamma can amplify either direction; no crash, buy/sell, or sizing inference is authorized.",
    }
    if age is not None and age > 0 and "source_stale_at_read" not in out["reasons"]:
        out["reasons"].append("source_stale_at_read")
    context = payload.get("context")
    if isinstance(context, dict):
        out["context"] = {}
        for key in ("vix", "vvix", "realized_volatility", "macro_liquidity"):
            raw = context.get(key)
            if not isinstance(raw, dict):
                continue
            context_day = _day(raw.get("source_session"))
            valid = context_day is not None and context_day <= today and nyse_calendar.is_session(context_day)
            context_age = nyse_calendar.sessions_behind(context_day, now) if valid else None
            context_state = raw.get("status")
            status = ("unavailable" if not valid else "stale" if context_age else
                      context_state if context_state in ("reported", "degraded", "unavailable") else "unavailable")
            value = raw.get("value")
            if key == "macro_liquidity":
                value = value if isinstance(value, str) and value in {
                    "benign-expansion", "stress-expansion", "neutral", "neutral-hollow", "contracting"
                } else None
            else:
                value = _number(value)
            out["context"][key] = {
                "value": value, "source_session": context_day.isoformat() if context_day else None,
                "age_sessions_at_read": context_age, "status": status,
                "raw_input_clocks_verified": False, "trade_authority": False,
            }
        out["context"]["market_depth_available"] = False
        out["context"]["gamma_spot_sensitivity_available"] = False
    return out
