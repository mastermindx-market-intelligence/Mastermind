"""China (Greater-China) equity market calendar — when the China and HK books may trade.

This module supplies the mainland A-share clock by default and the HKEX clock
for venue='HK'. A book-level clock does not qualify a mixed-venue holding or its
price for execution; instrument and venue identity remain separate requirements.

**Venue support (A4b fix):** ``is_trading_day(d, venue='CN'|'HK')`` gates on the correct
exchange calendar. The HK book (bot/hk.py) was previously gated on the mainland A-share
calendar, which misses ~6 HKEX-only holidays per year (e.g. HK SAR Establishment Day,
Buddha's Birthday). Adding the HKEX closure set fixes the CN-HK-1 novel problem.
Callers that omit `venue` default to ``'CN'``.

Mirrors the API of ``portfolio.market_calendar`` (is_trading_day / is_open / next_open /
status / trading-day arithmetic) so the builder and the pending-order lifecycle can use it
interchangeably, scoped by portfolio.

Pure-stdlib (zoneinfo), offline, deterministic. The A-share session is two halves
(09:30–11:30 and 13:00–15:00 China Standard Time, Mon–Fri). Holidays are a best-effort
SSE/SZSE closure set — the Lunar-calendar holidays SHIFT each year and the exchanges publish
the official calendar only ~a year ahead, so the forward years are approximate; refresh them
from the official SSE/SZSE notice as each year is published. Weekends are always closed.
This static calendar does not discover exceptional closures or qualify prices.
HKEX shortened sessions omit the afternoon continuous session; closing auctions
and securities/cash settlement-day rules are outside this execution gate.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

CST = ZoneInfo("Asia/Shanghai")          # China Standard Time (UTC+8, no DST)

# A-share regular cash session, two halves (China Standard Time).
_AM_OPEN = time(9, 30)
_AM_CLOSE = time(11, 30)
_PM_OPEN = time(13, 0)
_PM_CLOSE = time(15, 0)

# HKEX regular cash session (Hong Kong time == CST, both UTC+8, no DST): 09:30–12:00 / 13:00–16:00.
# The HK book gates on THESE bounds (via is_open(venue='HK')), not the earlier-closing A-share ones.
_HK_AM_OPEN = time(9, 30)
_HK_AM_CLOSE = time(12, 0)
_HK_PM_OPEN = time(13, 0)
_HK_PM_CLOSE = time(16, 0)

# SSE/SZSE full-day closures (best-effort; Lunar holidays are approximate in forward years —
# refresh from the official exchange calendar yearly). Covers the live track's near lifetime.
_HOLIDAYS: frozenset[date] = frozenset(
    date.fromisoformat(s)
    for s in (
        # 2025 (official SSE/SZSE)
        "2025-01-01",                                                   # New Year
        "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",         # Spring Festival
        "2025-02-03", "2025-02-04",
        "2025-04-04",                                                   # Qingming
        "2025-05-01", "2025-05-02", "2025-05-05",                       # Labour Day
        "2025-06-02",                                                   # Dragon Boat
        "2025-10-01", "2025-10-02", "2025-10-03", "2025-10-06",         # Nat'l Day + Mid-Autumn
        "2025-10-07", "2025-10-08",
        # 2026 (official SSE/SZSE schedule published 2025-12-22)
        # https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml
        "2026-01-01", "2026-01-02",                                     # New Year
        "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19",         # Spring Festival (CNY 2026-02-17)
        "2026-02-20", "2026-02-23",
        "2026-04-06",                                                   # Qingming (obs)
        "2026-05-01", "2026-05-04", "2026-05-05",                       # Labour Day
        "2026-06-19",                                                   # Dragon Boat
        "2026-09-25",                                                   # Mid-Autumn
        "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06",         # National Day
        "2026-10-07",
        # 2027 (approximate)
        "2027-01-01",                                                   # New Year
        "2027-02-08", "2027-02-09", "2027-02-10", "2027-02-11",         # Spring Festival (CNY 2027-02-06)
        "2027-02-12", "2027-02-15", "2027-02-16",
        "2027-04-05",                                                   # Qingming
        "2027-05-03", "2027-05-04", "2027-05-05",                       # Labour Day
        "2027-06-09",                                                   # Dragon Boat
        "2027-09-15",                                                   # Mid-Autumn
        "2027-10-01", "2027-10-04", "2027-10-05", "2027-10-06",         # National Day
        "2027-10-07", "2027-10-08",
    )
)


# ---------------------------------------------------------------------------
# HKEX holiday set — Hong Kong Exchange closures BEYOND shared weekends.
# Source: HKEX official holiday schedule https://www.hkex.com.hk/Services/
#         Trading/Securities/Overview/Trading-Hours-and-Schedules/
#         Exchange-Holidays?sc_lang=en  (verified 2026-07-30, covers 2025–2027).
# Each venue selects its own holiday set; the CN/HK sets are not unioned.
# Published HKEX securities circulars: CT/063/24 (2025), CT/075/25 (2026),
# CT/077/26 (2027), verified against the exchange notices on 2026-10-18.
# ---------------------------------------------------------------------------
_HKEX_HOLIDAYS: frozenset[date] = frozenset(
    date.fromisoformat(s)
    for s in (
        # 2025 (official HKEX)
        "2025-01-01",                                   # New Year's Day
        "2025-01-29", "2025-01-30", "2025-01-31",       # Lunar New Year
        "2025-04-04",                                   # Ching Ming Festival
        "2025-04-18", "2025-04-19", "2025-04-21",       # Good Friday + Easter Monday
        "2025-05-01",                                   # Labour Day
        "2025-05-05",                                   # Buddha's Birthday
        "2025-07-01",                                   # HK SAR Establishment Day
        "2025-10-01",                                   # National Day
        "2025-10-07",                                   # day after Mid-Autumn Festival
        "2025-10-29",                                   # Chung Yeung Festival
        "2025-12-25", "2025-12-26",                     # Christmas / Boxing Day
        # 2026 (official HKEX securities-market circular CT/075/25)
        "2026-01-01",                                   # New Year's Day
        "2026-02-17", "2026-02-18", "2026-02-19",       # Lunar New Year
        "2026-04-03",                                   # Good Friday
        "2026-04-06",                                   # day following Ching Ming Festival
        "2026-04-07",                                   # day following Easter Monday
        "2026-05-01",                                   # Labour Day
        "2026-05-25",                                   # day following Birthday of Buddha
        "2026-06-19",                                   # Tuen Ng Festival
        "2026-07-01",                                   # HK SAR Establishment Day
        "2026-10-01",                                   # National Day
        "2026-10-19",                                   # day following Chung Yeung Festival
        "2026-12-25",                                   # Christmas Day
        # 2027 (official HKEX securities-market circular CT/077/26)
        "2027-01-01",                                   # New Year's Day
        "2027-02-06", "2027-02-08", "2027-02-09",       # Lunar New Year
        "2027-03-26",                                   # Good Friday
        "2027-03-29",                                   # Easter Monday
        "2027-04-05",                                   # Ching Ming Festival
        "2027-05-01",                                   # Labour Day
        "2027-05-13",                                   # Buddha's Birthday
        "2027-06-09",                                   # Tuen Ng Festival
        "2027-07-01",                                   # HK SAR Establishment Day
        "2027-09-16",                                   # day after Mid-Autumn Festival
        "2027-10-01",                                   # National Day
        "2027-10-08",                                   # Chung Yeung Festival
        "2027-12-27",                                   # Christmas (obs)
    )
)

# Published half-days, moved from the dashboard into the execution authority.
# Sources: HKEX securities-market circulars CT/063/24, CT/075/25, CT/077/26.
# Continuous trading ends at 12:00; this gate does not admit closing auctions.
_HK_EARLY_CLOSES = frozenset(
    date.fromisoformat(value)
    for value in (
        "2025-01-28", "2025-12-24", "2025-12-31",
        "2026-02-16", "2026-12-24", "2026-12-31",
        "2027-02-05", "2027-12-24", "2027-12-31",
    )
)


def is_early_close(d: date, venue: str = "CN") -> bool:
    """Whether HKEX omits the afternoon continuous session on a published half-day."""
    return venue == "HK" and is_trading_day(d, venue=venue) and d in _HK_EARLY_CLOSES


def session_close(d: date, venue: str = "CN") -> time:
    """Scheduled continuous-session close, independent of full-day eligibility."""
    if venue == "HK":
        return _HK_AM_CLOSE if is_early_close(d, venue=venue) else _HK_PM_CLOSE
    return _PM_CLOSE


def is_holiday(d: date) -> bool:
    """True if `d` is a mainland A-share public holiday (does NOT cover weekends)."""
    return d in _HOLIDAYS


def is_hkex_holiday(d: date) -> bool:
    """True if `d` is an HKEX holiday (does NOT cover weekends)."""
    return d in _HKEX_HOLIDAYS


def is_trading_day(d: date, venue: str = "CN") -> bool:
    """True for a regular trading session day at the given `venue` ('CN' or 'HK').

    Default ``venue='CN'`` is the mainland A-share calendar (SSE/SZSE) — all existing
    callers that omit the argument are unchanged. ``venue='HK'`` gates on the HKEX
    holiday set instead, fixing the CN-HK-1 novel problem where the HK book ran on
    ~6 HKEX-only closure days per year (e.g. HK SAR Establishment Day on 2026-07-01).
    An unrecognised venue retains the legacy CN fallback; it is not strict venue validation.
    """
    if d.weekday() >= 5:          # weekends closed at both exchanges
        return False
    if venue == "HK":
        return d not in _HKEX_HOLIDAYS
    return d not in _HOLIDAYS     # 'CN' (default) or any unrecognised venue → A-share gate


def session_date_evidence(start: date, end: date, venue: str = "CN") -> dict[str, object]:
    """Describe only published CN/HK session dates, with explicit venue and coverage.

    The approximate mainland 2027 table remains usable by legacy callers but
    cannot qualify evaluation evidence through this stricter observation contract.
    """
    if type(start) is not date or type(end) is not date or start > end:
        raise ValueError("session date evidence requires an ordered date window")
    if type(venue) is not str or venue not in {"CN", "HK"}:
        raise ValueError("session date evidence requires CN or HK")
    coverage_start = date(2025, 1, 1)
    coverage_end = date(2027 if venue == "HK" else 2026, 12, 31)
    holidays = _HKEX_HOLIDAYS if venue == "HK" else _HOLIDAYS
    sources = [
        "https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2024/ce_SEHK_CT_063_2024.pdf",
        "https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2025/ce_SEHK_CT_075_2025.pdf",
        "https://www.hkex.com.hk/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2026/SEHK_CT_077_2026Jun01162846?sc_lang=en",
    ] if venue == "HK" else [
        "https://www.sse.com.cn/disclosure/announcement/general/c/c_20241223_10767108.shtml",
        "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml",
    ]
    evidence = {
        "schema": "mastermind.cash_session_date_evidence.v1",
        "calendar_owner": "portfolio.china_calendar",
        "venue": venue,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "coverage_start": coverage_start.isoformat(),
        "coverage_end": coverage_end.isoformat(),
        "source_checked_on": "2026-10-18",
        "source_refs": sources,
        "scope": "published_static_cash_session_dates",
        "exceptional_closures": "listed_only",
        "price_or_cutoff_qualified": False,
        "rule_version": "monday_friday_excluding_listed_closures.v1",
        "full_day_closures": [
            day.isoformat() for day in sorted(holidays)
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
        "scheduled_dates": [day.isoformat() for day in days if is_trading_day(day, venue=venue)],
        "status": "available",
        "missing_reason": None,
    }


def _now_cst(now: datetime | None) -> datetime:
    """Coerce `now` to a China-time aware datetime (naive is assumed CST)."""
    if now is None:
        return datetime.now(CST)
    if now.tzinfo is None:
        return now.replace(tzinfo=CST)
    return now.astimezone(CST)


def is_open(now: datetime | None = None, venue: str = "CN") -> bool:
    """True iff a regular session half is open right now at `venue` ('CN' A-share / 'HK' HKEX).

    Default ``venue='CN'`` keeps the mainland A-share session + holidays (existing callers unchanged).
    ``venue='HK'`` gates on the HKEX holiday set AND the HKEX session hours (09:30–12:00 / 13:00–16:00;
    HK time == CST, both UTC+8). Fixes CN-HK-1: the HK book was gating on the A-share calendar+hours,
    so it read HKEX-only holidays (e.g. 2026-07-01) as OPEN and the 15:00–16:00 HK hour as CLOSED."""
    cst = _now_cst(now)
    if not is_trading_day(cst.date(), venue=venue):
        return False
    t = cst.time()
    if venue == "HK":
        return (_HK_AM_OPEN <= t < _HK_AM_CLOSE) or (
            not is_early_close(cst.date(), venue=venue) and _HK_PM_OPEN <= t < _HK_PM_CLOSE)
    return (_AM_OPEN <= t < _AM_CLOSE) or (_PM_OPEN <= t < _PM_CLOSE)


def previous_trading_day(d: date, venue: str = "CN") -> date:
    """The most recent trading day strictly before `d` (at `venue`)."""
    cur = d - timedelta(days=1)
    while not is_trading_day(cur, venue=venue):
        cur -= timedelta(days=1)
    return cur


def next_trading_day(d: date, venue: str = "CN") -> date:
    """The next trading day strictly after `d` (at `venue`)."""
    cur = d + timedelta(days=1)
    while not is_trading_day(cur, venue=venue):
        cur += timedelta(days=1)
    return cur


def next_open(now: datetime | None = None, venue: str = "CN") -> datetime:
    """The next moment a session opens (at `venue`): today's morning open if still pre-market, the
    same-day afternoon reopen during a regular lunch break, else the next trading day's morning open."""
    cst = _now_cst(now)
    today = cst.date()
    am_open, am_close, pm_open = (
        (_HK_AM_OPEN, _HK_AM_CLOSE, _HK_PM_OPEN) if venue == "HK"
        else (_AM_OPEN, _AM_CLOSE, _PM_OPEN))
    if is_trading_day(today, venue=venue):
        t = cst.time()
        if t < am_open:
            return datetime.combine(today, am_open, tzinfo=CST)
        if not is_early_close(today, venue=venue) and am_close <= t < pm_open:
            return datetime.combine(today, pm_open, tzinfo=CST)
    nxt = next_trading_day(today, venue=venue)
    return datetime.combine(nxt, am_open, tzinfo=CST)


def next_open_day(now: datetime | None = None, venue: str = "CN") -> date:
    """Calendar date of the next session open at `venue` (for display: 'fills at <date>')."""
    return next_open(now, venue=venue).date()


def status(now: datetime | None = None, venue: str = "CN") -> dict:
    """A compact, display-ready snapshot of where we are in the calendar (A-share by default, HKEX
    when ``venue='HK'`` — so the HK book's status strip reflects its own exchange, not the A-share)."""
    cst = _now_cst(now)
    open_now = is_open(cst, venue=venue)
    nxt = next_open(cst, venue=venue)
    hk = venue == "HK"
    return {
        "open": open_now,
        "venue": "HKEX (Hong Kong)" if hk else "A-share (Shanghai/Shenzhen)",
        "asof": cst.isoformat(),        # stable key matching no-suffix consumers
        "asof_cst": cst.isoformat(),
        "trading_day": is_trading_day(cst.date(), venue=venue),
        "holiday": (is_hkex_holiday(cst.date()) if hk else is_holiday(cst.date())),
        "next_open": nxt.isoformat(),
        "next_open_day": nxt.date().isoformat(),
        "prev_trading_day": previous_trading_day(cst.date(), venue=venue).isoformat(),
    }
