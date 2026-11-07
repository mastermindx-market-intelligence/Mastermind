"""Closed projections of public display evidence; never a trade/freshness owner."""
from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .contracts import finite, time_observation, utc_now

SOURCE_BASES = ("settled", "legacy_display", "live_display")
CAUSE_BASES = (*SOURCE_BASES, "live_score_pending_band")
MARKET_STATES = ("current", "stale", "missing", "unavailable", "partial")
SESSION_STATES = ("open", "closed", "regular", "pre_market", "after_hours", "holiday", "weekend")
BANDS = ("low", "normal", "elevated", "high", "extreme")
UNKNOWN_STATES = ("unknown", "invalid", "other")
OWNER_REASON_CODES = (
    "unknown_source_schema", "missing_or_invalid_verdict", "invalid_score",
    "missing_or_invalid_asof", "future_asof", "expired_asof", "owner_stale",
    "source_stale", "invalid_built", "future_built", "invalid_source_event_time",
    "future_source_event_time", "missing_live_source_clock", "missing_live_expiry",
    "invalid_stale_after", "expired_source",
)
UNKNOWN_OWNER_REASON = "unrecognized_owner_reason"
OVERLAY_REASONS = (
    "intraday_cadence_unqualified", "producer_build_not_regime_state",
    "no_fresh_quote_claim", "reported_delayed_feed",
    "claimed_realtime_not_independently_verified", "reported_delay_realtime_conflict",
)
RISK_REASONS = (
    "owner_freshness_missing", "owner_freshness_refused", "owner_reasons_invalid",
    "owner_freshness_incoherent", "owner_reported_reasons", "stale_reasons_invalid",
    "owner_stale_reasons", "owner_stale", "owner_stale_unknown", "score_unavailable",
    "unknown_source_basis", "invalid_cause_basis", "build_unavailable",
    "invalid_build", "future_build", "invalid_source_event_time",
    "future_source_event", "missing_live_source_clock", "source_session_mismatch",
    "unqualified_intraday_expiry", "invalid_stale_after", "elapsed_expiry",
)
NEW_TOOLS = {"product_macro_overlay": "macro_overlay", "product_market_risk": "market_risk"}


def _enum(value, allowed):
    if value is None:
        return "unknown"
    if type(value) is not str:
        return "invalid"
    return value if value in allowed else "other"


def _boolean(value):
    return value if type(value) is bool else None


def _day(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _stamp(value, now, *, overlay_build=False):
    # This one producer uses a documented UTC spelling. Do not relax RFC3339
    # for any other clock or admit basic/week dates and implicit timezones.
    if (overlay_build and type(value) is str
            and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC", value)):
        value = value[:10] + "T" + value[11:19] + "Z"
    stamp = time_observation(value, now)
    if stamp["age_seconds"] is not None and stamp["age_seconds"] < 0:
        stamp["status"] = "future"
    return stamp


def _overlay_freshness(data):
    reasons = list(OVERLAY_REASONS[:2])
    if data["n_fresh"] == 0:
        reasons.append("no_fresh_quote_claim")
    if data["delayed_min"] > 0:
        reasons.append("reported_delayed_feed")
    elif data["reported_realtime"]:
        reasons.append("claimed_realtime_not_independently_verified")
    if data["delayed_min"] > 0 and data["reported_realtime"]:
        reasons.append("reported_delay_realtime_conflict")
    return {"state": "partial", "qualified": False, "reasons": reasons}


def macro_overlay(raw, now):
    if raw.get("schema") != "live.overlay.v2":
        raise ValueError("invalid_overlay_schema")
    built = _stamp(raw.get("built"), now, overlay_build=True)
    if built["status"] != "observed":
        raise ValueError("invalid_overlay_build")
    if (any(type(raw.get(k)) is not int or not 0 <= raw[k] <= 500 for k in ("n", "n_fresh", "n_quotes"))
            or raw["n_fresh"] > raw["n"]):
        raise ValueError("invalid_overlay_counts")
    if (type(raw.get("delayed_min")) is not int or not 0 <= raw["delayed_min"] <= 1440
            or type(raw.get("realtime")) is not bool):
        raise ValueError("invalid_overlay_delay")
    if type(raw.get("market")) is not dict or type(raw.get("sessions")) is not dict:
        raise ValueError("missing_overlay_context")
    market = {}
    for symbol in ("SPY", "QQQ", "VIX"):
        row = raw["market"].get(symbol)
        if type(row) is dict:
            day = _day(row.get("data_through"))
            market[symbol] = {
                "stale": _boolean(row.get("stale")), "band": _enum(row.get("band"), BANDS),
                "data_state": _enum(row.get("data_state"), MARKET_STATES),
                "data_frozen": _boolean(row.get("data_frozen")),
                "data_through": day.isoformat() if day else None,
                "session_state": _enum(row.get("session_state"), SESSION_STATES),
            }
    sessions = {}
    for venue in ("us", "cn", "hk", "ca"):
        row = raw["sessions"].get(venue)
        if type(row) is dict:
            day = _day(row.get("expected_session"))
            sessions[venue] = {
                "state": _enum(row.get("state"), SESSION_STATES),
                "calendar_verified": _boolean(row.get("calendar_verified")),
                "data_frozen": _boolean(row.get("data_frozen")),
                "expected_session": day.isoformat() if day else None,
            }
    data = {
        "schema": "live.overlay.v2", "built": built,
        "quote_ts_max": _stamp(raw.get("quote_ts_max"), now),
        "n": raw["n"], "n_fresh": raw["n_fresh"], "n_quotes": raw["n_quotes"],
        "delayed_min": raw["delayed_min"], "reported_realtime": raw["realtime"],
        "market": market, "sessions": sessions,
    }
    data["freshness"] = _overlay_freshness(data)
    return data


def _reasons(value):
    if type(value) is not list:
        return {"codes": [], "count": None, "valid": False}
    codes = []
    valid = len(value) <= 32
    for reason in value[:32]:
        if type(reason) is not str or reason not in OWNER_REASON_CODES:
            reason, valid = UNKNOWN_OWNER_REASON, False
        if reason not in codes:
            codes.append(reason)
    return {"codes": codes, "count": len(value), "valid": valid}


def _risk_freshness(data, now):
    reasons = []
    owner = data["owner_freshness"]
    if owner["qualified"] is None:
        reasons.append("owner_freshness_missing")
    elif owner["qualified"] is False:
        reasons.append("owner_freshness_refused")
    if not owner["reasons"]["valid"]:
        reasons.append("owner_reasons_invalid")
    if owner["reasons"]["count"]:
        reasons.append("owner_reported_reasons")
        if owner["qualified"] is True:
            reasons.append("owner_freshness_incoherent")
    if not data["stale_reasons"]["valid"]:
        reasons.append("stale_reasons_invalid")
    if data["stale_reasons"]["count"]:
        reasons.append("owner_stale_reasons")
    if data["stale"] is True:
        reasons.append("owner_stale")
    elif data["stale"] is None:
        reasons.append("owner_stale_unknown")
    if data["score"] is None:
        reasons.append("score_unavailable")
    if data["source_basis"] not in SOURCE_BASES:
        reasons.append("unknown_source_basis")
    cause = data["cause_basis"]
    if (cause in ("invalid", "other")
            or (cause in CAUSE_BASES and cause != data["source_basis"]
                and not (cause == "live_score_pending_band" and data["source_basis"] == "live_display"))):
        reasons.append("invalid_cause_basis")
    built, event, expiry = (data[k] for k in ("built", "source_event_time", "stale_after"))
    if built["status"] == "unknown":
        reasons.append("build_unavailable")
    elif built["status"] == "invalid":
        reasons.append("invalid_build")
    elif built["status"] == "future":
        reasons.append("future_build")
    if event["status"] == "invalid":
        reasons.append("invalid_source_event_time")
    elif event["status"] == "future":
        reasons.append("future_source_event")
    if data["source_basis"] == "live_display":
        if event["status"] not in ("observed", "future"):
            reasons.append("missing_live_source_clock")
        else:
            parsed = datetime.fromisoformat(event["value"].replace("Z", "+00:00").replace("z", "+00:00"))
            if parsed.astimezone(ZoneInfo("America/New_York")).date().isoformat() != data["asof"]:
                reasons.append("source_session_mismatch")
    if expiry["status"] == "unknown":
        reasons.append("unqualified_intraday_expiry")
    elif expiry["status"] == "invalid":
        reasons.append("invalid_stale_after")
    elif expiry["age_seconds"] >= 0:
        reasons.append("elapsed_expiry")
    stale = any(r in reasons for r in ("owner_stale", "future_build", "future_source_event", "elapsed_expiry"))
    return {"state": "stale" if stale else "partial" if reasons else "qualified",
            "qualified": not reasons, "reasons": reasons}


def market_risk(raw, now):
    if raw.get("schema") != "market_risk/v1" or raw.get("verdict") not in ("RISK_ON", "MIXED", "RISK_OFF"):
        raise ValueError("invalid_risk_contract")
    if raw.get("is_display_only") is not True:
        raise ValueError("unqualified_display_authority")
    score = raw.get("score")
    if score is not None and (finite(score) is None or not 0 <= score <= 100):
        raise ValueError("invalid_score")
    day = _day(raw.get("asof"))
    if day is None or day > now.astimezone(ZoneInfo("America/New_York")).date():
        raise ValueError("invalid_or_future_session")
    owner = raw.get("freshness")
    owner = owner if type(owner) is dict else {}
    data = {
        "schema": "market_risk/v1", "verdict": raw["verdict"], "score": score,
        "asof": day.isoformat(), "is_display_only": True, "stale": _boolean(raw.get("stale")),
        "built": _stamp(raw.get("built"), now),
        "source_event_time": _stamp(raw.get("source_event_time"), now),
        "stale_after": _stamp(raw.get("stale_after"), now),
        "source_basis": _enum(raw.get("source_basis"), SOURCE_BASES),
        "cause_basis": _enum(raw.get("cause_basis"), CAUSE_BASES),
        "owner_freshness": {"qualified": _boolean(owner.get("qualified")),
                            "reasons": _reasons(owner.get("reasons"))},
        "stale_reasons": _reasons(raw.get("stale_reasons", [])),
    }
    data["freshness"] = _risk_freshness(data, now)
    return data


def validate_projection_result(result):
    """Enforce semantic invariants again at the authenticated buffered return.

    The existing closed JSON schemas run first. A faulty trusted reader cannot
    promote a partial/stale display or overlay by changing only its verdict.
    This is output validation, not a new freshness or source-identity authority.
    """
    endpoint = NEW_TOOLS.get(result.get("tool"))
    if endpoint is None:
        return
    observation = result["observations"][0]
    if observation["state"] != "observed":
        return
    data = observation["data"]
    now = utc_now(datetime.fromisoformat(observation["observed_at"].replace("Z", "+00:00").replace("z", "+00:00")))
    fields = ("built", "quote_ts_max") if endpoint == "macro_overlay" else ("built", "source_event_time", "stale_after")
    for field in fields:
        stamp = data[field]
        if stamp["value"] is None:
            if stamp["status"] not in ("unknown", "invalid") or stamp["age_seconds"] is not None:
                raise ValueError("inconsistent_source_clock")
        elif stamp != _stamp(stamp["value"], now):
            raise ValueError("inconsistent_source_clock")
    if endpoint == "macro_overlay":
        if data["n_fresh"] > data["n"] or data["built"]["status"] != "observed":
            raise ValueError("invalid_overlay_result")
        expected = _overlay_freshness(data)
    else:
        if date.fromisoformat(data["asof"]) > now.astimezone(ZoneInfo("America/New_York")).date():
            raise ValueError("future_source_session")
        for entry in (data["owner_freshness"]["reasons"], data["stale_reasons"]):
            size, codes = entry["count"], entry["codes"]
            if (size is None and (entry["valid"] or codes)
                    or size is not None and (len(codes) > size or (size > 0 and not codes))
                    or entry["valid"] and (size > 32 or UNKNOWN_OWNER_REASON in codes)):
                raise ValueError("inconsistent_owner_reasons")
        expected = _risk_freshness(data, now)
    if data["freshness"] != expected:
        raise ValueError("unqualified_projection_result")
