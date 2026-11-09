"""US equity market calendar — the single authority for *when* the bot may trade.

Doctrine: the paper book only transacts during regular US cash-session hours
(09:30–16:00 America/New_York, Mon–Fri, excluding exchange holidays), at the
live market price. Anything decided while the market is CLOSED is queued as a
PENDING order to be filled at the next open — never booked as an instantaneous
fill at a stale close. This module owns the open/closed test and the trading-day
arithmetic; `paper_account` owns the pending-order lifecycle that depends on it.

Pure-stdlib (zoneinfo), offline, deterministic. Published closures and shortened
cash sessions cover 2025–2027; extend them from exchange notices as years roll
forward. This static calendar does not discover exceptional closures or qualify
prices, auction eligibility, or dates outside its published coverage.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Regular cash session, Eastern time.
_OPEN = time(9, 30)
_CLOSE = time(16, 0)

# NYSE full-day closures (observed dates). Juneteenth 2026-06-19 is the holiday
# that, with the weekend, keeps the desk shut Fri–Sun before the 2026-06-22 open.
_HOLIDAYS: frozenset[date] = frozenset(
    date.fromisoformat(s)
    for s in (
        # 2025; January 9 was the national day of mourning for President Carter.
        "2025-01-09",
        "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
        "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
        # 2026
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
        "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
        # 2027
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
        "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    )
)

# Published regular cash-session early closes, shared by settlement and display.
# NYSE current calendar: https://www.nyse.com/trade/hours-calendars
# 2025: ICE "NYSE Group Announces 2023, 2024 and 2025 Holiday and Early
# Closings Calendar" (2022). Carter closure: ICE notice, 2024-12-30.
_EARLY_CLOSES = frozenset(
    date.fromisoformat(value)
    for value in (
        "2025-07-03", "2025-11-28", "2025-12-24",
        "2026-11-27", "2026-12-24",
        "2027-11-26",
    )
)


def is_early_close(d: date) -> bool:
    """Whether a published trading day has a 13:00 ET regular cash close."""
    return is_trading_day(d) and d in _EARLY_CLOSES


def session_close(d: date) -> time:
    """Scheduled regular cash close; callers must separately check trading-day eligibility."""
    return time(13, 0) if is_early_close(d) else _CLOSE


def is_holiday(d: date) -> bool:
    return d in _HOLIDAYS


def is_trading_day(d: date) -> bool:
    """True for a regular NYSE session day (weekday, not a holiday)."""
    return d.weekday() < 5 and d not in _HOLIDAYS


def session_date_evidence(start: date, end: date) -> dict[str, object]:
    """Describe the published static schedule; do not qualify prices or fills.

    The caller receives a fresh, bounded window from this calendar's existing
    trading-day rule. Dates outside published coverage are never extrapolated.
    """
    if type(start) is not date or type(end) is not date or start > end:
        raise ValueError("session date evidence requires an ordered date window")
    coverage_start, coverage_end = date(2025, 1, 1), date(2027, 12, 31)
    evidence = {
        "schema": "mastermind.cash_session_date_evidence.v1",
        "calendar_owner": "portfolio.market_calendar",
        "venue": "US",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "coverage_start": coverage_start.isoformat(),
        "coverage_end": coverage_end.isoformat(),
        "source_checked_on": "2026-10-18",
        "source_refs": [
            "https://www.nyse.com/trade/hours-calendars",
            "https://ir.theice.com/press/news-details/2022/NYSE-Group-Announces-2023-2024-and-2025-Holiday-and-Early-Closings-Calendar/default.aspx",
            "https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx",
        ],
        "scope": "published_static_cash_session_dates",
        "exceptional_closures": "listed_only",
        "price_or_cutoff_qualified": False,
        "rule_version": "monday_friday_excluding_listed_closures.v1",
        "full_day_closures": [
            day.isoformat() for day in sorted(_HOLIDAYS)
            if coverage_start <= day <= coverage_end
        ],
        "scheduled_dates": None,
        "status": "unavailable",
        "missing_reason": "outside_published_calendar_coverage",
    }
    if start < coverage_start or end > coverage_end:
        return evidence
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    return {
        **evidence,
        "scheduled_dates": [day.isoformat() for day in days if is_trading_day(day)],
        "status": "available",
        "missing_reason": None,
    }


def _now_et(now: datetime | None) -> datetime:
    """Coerce `now` to an Eastern-time aware datetime (naive is assumed ET)."""
    if now is None:
        return datetime.now(ET)
    if now.tzinfo is None:
        return now.replace(tzinfo=ET)
    return now.astimezone(ET)


def is_open(now: datetime | None = None) -> bool:
    """True iff the US cash session is open right now (regular hours, ET)."""
    et = _now_et(now)
    if not is_trading_day(et.date()):
        return False
    return _OPEN <= et.time() < session_close(et.date())


def previous_trading_day(d: date) -> date:
    """The most recent trading day strictly before `d`."""
    cur = d - timedelta(days=1)
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur


def next_trading_day(d: date) -> date:
    """The next trading day strictly after `d`."""
    cur = d + timedelta(days=1)
    while not is_trading_day(cur):
        cur += timedelta(days=1)
    return cur


def next_open(now: datetime | None = None) -> datetime:
    """The next moment the session opens (today's open if still pre-market, else
    the next trading day's 09:30 ET)."""
    et = _now_et(now)
    today = et.date()
    if is_trading_day(today) and et.time() < _OPEN:
        return datetime.combine(today, _OPEN, tzinfo=ET)
    nxt = next_trading_day(today)
    return datetime.combine(nxt, _OPEN, tzinfo=ET)


def next_open_day(now: datetime | None = None) -> date:
    """Calendar date of the next session open (for display: 'fills at <date>')."""
    return next_open(now).date()


def status(now: datetime | None = None) -> dict:
    """A compact, display-ready snapshot of where we are in the calendar."""
    et = _now_et(now)
    open_now = is_open(et)
    nxt = next_open(et)
    return {
        "open": open_now,
        "asof_et": et.isoformat(),
        "trading_day": is_trading_day(et.date()),
        "holiday": is_holiday(et.date()),
        "next_open": nxt.isoformat(),
        "next_open_day": nxt.date().isoformat(),
        "prev_trading_day": previous_trading_day(et.date()).isoformat(),
    }
