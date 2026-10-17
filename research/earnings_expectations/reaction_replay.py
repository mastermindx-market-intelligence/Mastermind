"""Research-only regular-session earnings reaction replay.

This is an offline *labeler*, not a trade signal, source of truth, or publisher.
It consumes independently verified first-public-release UTC clocks, exchange regular
sessions and consistent adjusted-close series. No network, imports or data writes.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

SCHEMA = "earnings.reaction_replay.research.v1"
ADJUSTMENT = "split_dividend_adjusted_close"
ET = ZoneInfo("America/New_York")


class ReplayError(ValueError):
    """Malformed-source refusal, not a missing market observation."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _time(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ReplayError("TIMESTAMP_WITH_OFFSET_REQUIRED")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReplayError("INVALID_TIMESTAMP") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReplayError("TIMESTAMP_WITH_OFFSET_REQUIRED")
    return value.astimezone(timezone.utc)


def _day(raw: object) -> date:
    if not isinstance(raw, str):
        raise ReplayError("INVALID_SESSION_DATE")
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ReplayError("INVALID_SESSION_DATE") from exc
    if parsed.isoformat() != raw:
        raise ReplayError("INVALID_SESSION_DATE")
    return parsed


def _sessions(rows: object) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        raise ReplayError("EXCHANGE_SESSIONS_REQUIRED")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ReplayError("MALFORMED_EXCHANGE_SESSION")
        day = _day(row.get("date"))
        op = _time(row.get("open_utc"))
        cl = _time(row.get("close_utc"))
        if not op < cl or op.astimezone(ET).date() != day or cl.astimezone(ET).date() != day:
            raise ReplayError("INVALID_EXCHANGE_SESSION_CLOCK")
        if out and (day <= out[-1]["date"] or op <= out[-1]["close"]):
            raise ReplayError("DUPLICATE_OR_UNSORTED_SESSION")
        out.append({"date": day, "open": op, "close": cl})
    return out


def _bars(bundle: object, dates: set[date], visible_dates: set[date], cutoff_date: date) -> dict[date, float]:
    if not isinstance(bundle, dict) or bundle.get("adjustment") != ADJUSTMENT:
        raise ReplayError("ADJUSTMENT_PROVENANCE_REQUIRED")
    source = bundle.get("source_ref")
    if not isinstance(source, str) or not source.strip():
        raise ReplayError("PRICE_SOURCE_REQUIRED")
    rows = bundle.get("bars")
    if not isinstance(rows, list):
        raise ReplayError("PRICE_BARS_REQUIRED")
    out: dict[date, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ReplayError("INVALID_BAR")
        day = _day(row.get("date"))
        # A source packet may include later bars. Their values, duplicates and
        # missingness must not affect an earlier as-of replay: those future
        # records were unobservable at the evaluation cutoff.
        if day not in dates and day > cutoff_date:
            continue
        if day not in dates:
            raise ReplayError("BAR_OUTSIDE_EXCHANGE_SESSIONS")
        if day not in visible_dates:
            continue
        if day in out:
            raise ReplayError("DUPLICATE_PRICE_BAR")
        value = row.get("adjusted_close")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ReplayError("INVALID_ADJUSTED_CLOSE")
        out[day] = float(value)
    return out


def _ret(prices: dict[date, float], start: date, stop: date) -> float | None:
    if start not in prices or stop not in prices:
        return None
    return prices[stop] / prices[start] - 1.0


def _window(start: date, end: date, prices: dict[str, dict[date, float]]) -> dict:
    returns = {role: _ret(series, start, end) for role, series in prices.items()}
    if returns["issuer"] is None:
        return {"status": "MISSING_ISSUER_CLOSE", "returns": None}
    if returns["market"] is None:
        return {"status": "MISSING_MARKET_CLOSE", "returns": None}
    if returns["sector"] is None:
        return {"status": "MISSING_SECTOR_CLOSE", "returns": None}
    return {
        "status": "AVAILABLE",
        "start_session": start.isoformat(),
        "end_session": end.isoformat(),
        "returns": {
            "issuer": returns["issuer"],
            "market": returns["market"],
            "sector": returns["sector"],
            "issuer_minus_market": returns["issuer"] - returns["market"],
            "issuer_minus_sector": returns["issuer"] - returns["sector"],
        },
    }


def replay(packet: dict) -> dict:
    """Return deterministic research labels, or a typed refusal for malformed inputs.

    Release is earliest verified public time, NOT SEC acceptance when a press
    release preceded it. Intraday reactions are explicitly non-estimable using
    close-only series; H5/H20 begin at the first affected *close* and are not
    labeled as executable entry fills. As-of gating on session closes does NOT
    make retrospectively adjusted vendor prices historical PIT-admitted prices.
    """
    if not isinstance(packet, dict):
        raise ReplayError("PACKET_OBJECT_REQUIRED")
    event = packet.get("event")
    if not isinstance(event, dict) or not all(isinstance(event.get(k), str) and event[k] for k in ("issuer_ref", "fiscal_target", "event_ref", "first_public_source_ref")):
        raise ReplayError("IMMUTABLE_EVENT_IDENTITY_REQUIRED")
    clock_class = event.get("first_publication_clock_status")
    if clock_class not in {"VERIFIED_FIRST_PUBLIC_RELEASE", "AFTER_CLOSE_WINDOW_CORROBORATED"}:
        raise ReplayError("FIRST_PUBLIC_RELEASE_CLOCK_NOT_VERIFIED")
    asof = _time(packet.get("evaluated_asof_utc"))
    sessions = _sessions(packet.get("sessions"))
    if clock_class == "VERIFIED_FIRST_PUBLIC_RELEASE":
        published = _time(event.get("first_published_utc"))
        if asof < published:
            raise ReplayError("EVALUATION_BEFORE_PUBLICATION")
        prior = [idx for idx, s in enumerate(sessions) if s["close"] < published]
        first = next((idx for idx, s in enumerate(sessions) if s["close"] > published), None)
        before = prior[-1] if prior else None
        public_by = published
        clock_quality = "FIRST_PUBLIC_RELEASE_EXACT_OR_DECLARED_PRECISION"
        evidences = [event["first_public_source_ref"]]
    else:
        # A second, strictly weaker proof: corroborated publication in the
        # regular-close-to-next-open interval. No claim about its earliest second.
        if event.get("first_published_utc") is not None:
            raise ReplayError("WINDOW_MODE_CANNOT_ASSERT_FIRST_PUBLIC_CLOCK")
        report_session = _day(event.get("after_close_session"))
        match = [idx for idx, s in enumerate(sessions) if s["date"] == report_session]
        if not match:
            raise ReplayError("RELEASE_SESSION_NOT_IN_EXCHANGE_CALENDAR")
        before = match[0]
        first = before + 1 if before + 1 < len(sessions) else None
        evidences = event.get("after_close_evidence_refs")
        if (not isinstance(evidences, list) or len(evidences) < 2
                or any(not isinstance(ref, str) or not ref.strip() for ref in evidences)
                or len(set(evidences)) != len(evidences)):
            raise ReplayError("CORROBORATING_PUBLIC_RELEASE_EVIDENCE_REQUIRED")
        if event.get("public_by_source_kind") not in {"ISSUER_WIRE_DISTRIBUTION", "PRESS_RELEASE_REPRINT"}:
            raise ReplayError("NON_SEC_PUBLIC_RELEASE_WITNESS_REQUIRED")
        public_by = _time(event.get("observed_public_by_utc"))
        if public_by <= sessions[before]["close"]:
            raise ReplayError("PUBLIC_WITNESS_NOT_AFTER_SESSION_CLOSE")
        if first is not None and public_by >= sessions[first]["open"]:
            raise ReplayError("PUBLIC_WITNESS_NOT_BEFORE_NEXT_OPEN")
        if asof < public_by:
            raise ReplayError("EVALUATION_BEFORE_PUBLICATION")
        published = None
        clock_quality = "SESSION_WINDOW_CORROBORATED_EARLIEST_RELEASE_UNKNOWN"
    prices_in = packet.get("price_series")
    if not isinstance(prices_in, dict) or any(k not in prices_in for k in ("issuer", "market", "sector")):
        raise ReplayError("THREE_PRICE_SERIES_REQUIRED")
    dates = {s["date"] for s in sessions}
    visible_dates = {s["date"] for s in sessions if s["close"] <= asof}
    cutoff_date = asof.astimezone(ET).date()
    prices = {role: _bars(prices_in[role], dates, visible_dates, cutoff_date)
              for role in ("issuer", "market", "sector")}
    out = {
        "schema": SCHEMA,
        "event_ref": event["event_ref"],
        "issuer_ref": event["issuer_ref"],
        "fiscal_target": event["fiscal_target"],
        "release_source_ref": event["first_public_source_ref"],
        "first_public_source_ref": event["first_public_source_ref"] if published else None,
        "first_published_utc": published.isoformat().replace("+00:00", "Z") if published else None,
        "observed_public_by_utc": public_by.isoformat().replace("+00:00", "Z"),
        "clock_quality": clock_quality,
        "clock_evidence_refs": evidences,
        "evaluated_asof_utc": asof.isoformat().replace("+00:00", "Z"),
        "price_adjustment": ADJUSTMENT,
        "price_sources": {role: prices_in[role]["source_ref"] for role in prices},
        "authority": "RESEARCH_ONLY_NO_TRADING",
        "reaction": {"status": "UNESTIMABLE"},
        "pre_event": {"P5": {"status": "NO_UNAFFECTED_PRIOR_CLOSE"},
                      "P10": {"status": "NO_UNAFFECTED_PRIOR_CLOSE"},
                      "P20": {"status": "NO_UNAFFECTED_PRIOR_CLOSE"}},
        "calendar_basis": "SUPPLIED_SESSION_CLOCKS_NOT_INDEPENDENTLY_EXCHANGE_VERIFIED",
        "drift": {"H5": {"status": "UNESTIMABLE"}, "H20": {"status": "UNESTIMABLE"}},
    }
    if before is None:
        out["reaction"] = {"status": "NO_UNAFFECTED_PRIOR_CLOSE"}
        return out
    # Pre-event anticipation ends at the last unaffected regular-session close.
    # Session arithmetic requires a complete, externally qualified exchange
    # calendar; this tool explicitly reports the supplied-only calendar basis.
    for n in (5, 10, 20):
        if before < n:
            out["pre_event"][f"P{n}"] = {"status": "INSUFFICIENT_PRIOR_SESSIONS"}
        else:
            out["pre_event"][f"P{n}"] = _window(
                sessions[before - n]["date"], sessions[before]["date"], prices
            )
    if first is None:
        out["reaction"] = {"status": "NO_AFFECTED_FUTURE_SESSION"}
        return out
    after = first
    affected = sessions[after]
    if published is not None and any(s["close"] == published for s in sessions):
        out["reaction"] = {"status": "AMBIGUOUS_RELEASE_AT_REGULAR_CLOSE"}
    elif published is not None and affected["open"] <= published:
        out["reaction"] = {"status": "INTRADAY_CLOSE_WINDOW_CONTAMINATED", "affected_session": affected["date"].isoformat()}
    elif asof < affected["close"]:
        out["reaction"] = {"status": "AFFECTED_CLOSE_NOT_YET_KNOWN", "affected_session": affected["date"].isoformat()}
    else:
        out["reaction"] = _window(sessions[before]["date"], affected["date"], prices)
    out["first_affected_session"] = affected["date"].isoformat()
    out["unaffected_last_close_session"] = sessions[before]["date"].isoformat()
    for n in (5, 20):
        if after + n >= len(sessions):
            out["drift"][f"H{n}"] = {"status": "INSUFFICIENT_FUTURE_SESSIONS"}
            continue
        endpoint = sessions[after + n]
        if endpoint["close"] > asof:
            out["drift"][f"H{n}"] = {"status": "HORIZON_NOT_YET_OBSERVABLE"}
            continue
        out["drift"][f"H{n}"] = _window(affected["date"], endpoint["date"], prices)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline, read-only earnings event label replay")
    parser.add_argument("packet", type=Path, help="JSON packet with sourced event, schedule, and adjusted closes")
    args = parser.parse_args(argv)
    try:
        with args.packet.open(encoding="utf-8") as fh:
            packet = json.load(fh)
        result = replay(packet)
    except (ReplayError, json.JSONDecodeError, OSError) as exc:
        error = exc.reason if isinstance(exc, ReplayError) else type(exc).__name__
        print(json.dumps({"schema": SCHEMA, "status": "REFUSED", "reason": error}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
