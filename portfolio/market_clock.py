"""Compatibility clock for the manual Self-Directed account.

The US execution calendar owns holidays and shortened cash sessions. This
adapter preserves the manual account's public keys and naive ET datetimes,
while delegating session eligibility and next-open arithmetic to that owner.
No separate holiday table or hand-maintained DST rule is kept here.
"""
from __future__ import annotations

from datetime import date, datetime, time

from portfolio import market_calendar


def now_et() -> datetime:
    """Current US-Eastern wall-clock as a naive datetime."""
    return datetime.now(market_calendar.ET).replace(tzinfo=None)


def is_holiday(d: date) -> bool:
    return market_calendar.is_holiday(d)


def is_session_day(d: date) -> bool:
    """A weekday that is not a published NYSE closure."""
    return market_calendar.is_trading_day(d)


def is_open(now: datetime | None = None) -> bool:
    """True iff the regular cash session is open, including shortened days."""
    return market_calendar.is_open(now or now_et())


def next_open(now: datetime | None = None) -> datetime:
    """Next regular-session open, preserving the legacy naive ET return type."""
    return market_calendar.next_open(now or now_et()).replace(tzinfo=None)


def status(now: datetime | None = None) -> dict:
    """Legacy open/pre/post/closed contract at the shared calendar boundary."""
    raw = market_calendar.status(now or now_et())
    local_now = datetime.fromisoformat(raw["asof_et"]).replace(tzinfo=None)
    if raw["open"]:
        session = "open"
    elif raw["trading_day"] and local_now.time() < time(9, 30):
        session = "pre"
    elif raw["trading_day"]:
        session = "post"
    else:
        session = "closed"
    return {
        "is_open": session == "open",
        "session": session,
        "now_et": local_now.isoformat(timespec="minutes"),
        "next_open": datetime.fromisoformat(raw["next_open"]).replace(
            tzinfo=None).isoformat(timespec="minutes"),
    }
