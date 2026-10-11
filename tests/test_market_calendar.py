"""Market-calendar unit tests — offline, deterministic, no network.

The decisive scenario for this build: it is Sunday 2026-06-21; Friday 2026-06-19
was the Juneteenth holiday; the desk has been shut since the Thursday 06-18
close and the next open is Monday 2026-06-22 09:30 ET.
"""
from __future__ import annotations

from datetime import date, datetime

from zoneinfo import ZoneInfo

from portfolio import market_calendar as mc

ET = ZoneInfo("America/New_York")


def test_weekend_is_closed() -> None:
    assert mc.is_open(datetime(2026, 6, 20, 12, 0, tzinfo=ET)) is False  # Sat
    assert mc.is_open(datetime(2026, 6, 21, 12, 0, tzinfo=ET)) is False  # Sun
    assert mc.is_trading_day(date(2026, 6, 20)) is False
    assert mc.is_trading_day(date(2026, 6, 21)) is False


def test_juneteenth_holiday_closed() -> None:
    assert mc.is_holiday(date(2026, 6, 19)) is True
    assert mc.is_trading_day(date(2026, 6, 19)) is False
    # noon on the holiday — still closed despite being a weekday at session time
    assert mc.is_open(datetime(2026, 6, 19, 12, 0, tzinfo=ET)) is False


def test_regular_session_hours() -> None:
    # Monday 2026-06-22 is a normal session
    assert mc.is_trading_day(date(2026, 6, 22)) is True
    assert mc.is_open(datetime(2026, 6, 22, 9, 29, tzinfo=ET)) is False   # pre-open
    assert mc.is_open(datetime(2026, 6, 22, 9, 30, tzinfo=ET)) is True    # the open
    assert mc.is_open(datetime(2026, 6, 22, 12, 0, tzinfo=ET)) is True
    assert mc.is_open(datetime(2026, 6, 22, 15, 59, tzinfo=ET)) is True
    assert mc.is_open(datetime(2026, 6, 22, 16, 0, tzinfo=ET)) is False   # the close
    assert mc.is_open(datetime(2026, 6, 22, 18, 0, tzinfo=ET)) is False   # after hours


def test_next_open_from_weekend_after_holiday() -> None:
    # Sunday afternoon -> next open is Monday 06-22 09:30 ET
    nxt = mc.next_open(datetime(2026, 6, 21, 14, 0, tzinfo=ET))
    assert nxt == datetime(2026, 6, 22, 9, 30, tzinfo=ET)
    assert mc.next_open_day(datetime(2026, 6, 21, 14, 0, tzinfo=ET)) == date(2026, 6, 22)


def test_next_open_premarket_same_day() -> None:
    # 8am on a trading day -> today's 09:30 open
    nxt = mc.next_open(datetime(2026, 6, 22, 8, 0, tzinfo=ET))
    assert nxt == datetime(2026, 6, 22, 9, 30, tzinfo=ET)


def test_next_open_after_close_rolls_forward() -> None:
    # 5pm Thursday 06-18 -> skips Fri holiday + weekend -> Mon 06-22
    nxt = mc.next_open(datetime(2026, 6, 18, 17, 0, tzinfo=ET))
    assert nxt == datetime(2026, 6, 22, 9, 30, tzinfo=ET)


def test_previous_trading_day_skips_holiday_and_weekend() -> None:
    # Before Monday 06-22 the prior session is Thursday 06-18 (skip Fri/Sat/Sun)
    assert mc.previous_trading_day(date(2026, 6, 22)) == date(2026, 6, 18)


def test_naive_datetime_assumed_et() -> None:
    # naive input is treated as ET, not UTC
    assert mc.is_open(datetime(2026, 6, 22, 12, 0)) is True
    assert mc.is_open(datetime(2026, 6, 21, 12, 0)) is False


# Published NYSE cash-equity early closes; these are not extended-session hours.
# ICE/NYSE 2025–2027 calendar, November 8, 2024; verified October 11, 2026.
def test_all_published_early_closes_have_exclusive_1300_boundary() -> None:
    for value in ("2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24", "2027-11-26"):
        day = date.fromisoformat(value)
        assert mc.is_trading_day(day) is True
        assert mc.is_open(datetime(day.year, day.month, day.day, 12, 59, 59, tzinfo=ET)) is True
        assert mc.is_open(datetime(day.year, day.month, day.day, 13, 0, tzinfo=ET)) is False, value
        assert mc.is_open(datetime(day.year, day.month, day.day, 14, 0, tzinfo=ET)) is False, value


def test_early_close_utc_conversion_and_next_open() -> None:
    assert mc.is_open(datetime.fromisoformat("2026-11-27T17:59:59+00:00")) is True
    assert mc.is_open(datetime.fromisoformat("2026-11-27T18:00:00+00:00")) is False
    assert mc.next_open(datetime(2026, 11, 27, 13, 0, tzinfo=ET)) == datetime(2026, 11, 30, 9, 30, tzinfo=ET)
    assert mc.next_open(datetime(2026, 12, 24, 13, 0, tzinfo=ET)) == datetime(2026, 12, 28, 9, 30, tzinfo=ET)


def test_national_day_of_mourning_2025_is_closed() -> None:
    # Separate official December 30, 2024 NYSE notice, not a banking holiday rule.
    day = date(2025, 1, 9)
    assert mc.is_holiday(day) is True
    assert mc.is_open(datetime(2025, 1, 9, 12, 0, tzinfo=ET)) is False
    assert mc.next_trading_day(date(2025, 1, 8)) == date(2025, 1, 10)
    assert mc.previous_trading_day(date(2025, 1, 10)) == date(2025, 1, 8)


def test_us_display_and_underlying_calendar_share_close_authority(monkeypatch) -> None:
    from datetime import time
    from portfolio import market_sessions
    assert callable(getattr(mc, "session_close_time", None)), "calendar must own session close"
    assert callable(getattr(mc, "is_early_close", None)), "calendar must own early-close facts"
    monkeypatch.setattr(mc, "session_close_time", lambda _: time(12, 0))
    monkeypatch.setattr(mc, "is_early_close", lambda _: True)
    now = datetime(2026, 6, 22, 12, 30, tzinfo=ET)
    assert mc.is_open(now) is False
    result = market_sessions.status_for_portfolio("autonomous", now)
    assert result["is_open"] is False
    assert result["session_close"] == "2026-06-22T12:00:00-04:00"
    assert result["state"] == "early_close"
