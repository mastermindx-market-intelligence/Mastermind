"""US/HK display and settlement must consume the same venue calendar authority."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from portfolio import china_calendar as cc, market_calendar as mc, market_sessions

HKT = ZoneInfo("Asia/Hong_Kong")


@pytest.mark.parametrize("value", [
    "2025-01-28", "2025-12-24", "2025-12-31",
    "2026-02-16", "2026-12-24", "2026-12-31",
    "2027-02-05", "2027-12-24", "2027-12-31",
])
def test_hk_half_days_have_no_afternoon_continuous_session(value):
    day = date.fromisoformat(value)
    def at(hour, minute=0):
        return datetime.combine(day, time(hour, minute), tzinfo=HKT)
    assert cc.is_open(at(11, 59), venue="HK") is True
    for hour in (12, 13, 14, 15):
        assert cc.is_open(at(hour), venue="HK") is False, value
        shown = market_sessions.status_for_portfolio("hk", at(hour))
        assert shown["is_open"] is False and shown["state"] == "early_close"
    # The existing simulation excludes closing-auction sessions; noon is the
    # continuous-session boundary, not a claim that HKEX CAS ends at noon.


@pytest.mark.parametrize("value,expected", [
    ("2025-01-28", "2025-02-03"),
    ("2026-02-16", "2026-02-20"),
    ("2027-02-05", "2027-02-10"),
])
def test_hk_no_phantom_afternoon_reopen_on_lunar_new_year_eve(value, expected):
    now = datetime.fromisoformat(value + "T12:15:00+08:00")
    nxt = cc.next_open(now, venue="HK")
    assert nxt == datetime.fromisoformat(expected + "T09:30:00+08:00")
    assert market_sessions.status_for_portfolio("hk", now)["next_open"] == nxt.isoformat()


def test_hk_display_consumes_calendar_close_not_its_own_table(monkeypatch):
    assert callable(getattr(cc, "session_close_time", None)), "missing venue close authority"
    assert callable(getattr(cc, "is_early_close", None)), "missing venue early-close authority"
    monkeypatch.setattr(cc, "is_early_close", lambda day, venue="CN": venue == "HK")
    shown = market_sessions.status_for_portfolio("hk", datetime(2026, 6, 22, 13, 30, tzinfo=HKT))
    assert shown["is_open"] is False and shown["session_close"].endswith("12:00:00+08:00")


def test_settlement_resolves_existing_calendar_owners():
    from bot import settle
    assert settle._calendar("autonomous") is mc
    assert settle._calendar("hk") is cc
    assert settle._calendar("china") is cc
