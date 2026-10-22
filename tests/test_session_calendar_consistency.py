"""Published cash-session boundaries must agree at actual execution consumers.

Bot Renewal #1357, existing 05A/06A calendar work. Offline fixtures only.
Date oracles: NYSE hours-calendars (2026/27), ICE 2022 holiday release
(2025 shortened sessions), ICE 2024-12-30 Carter closure, SSE notice
2025-12-22, HKEX CT/063/24, CT/075/25 and CT/077/26.
Closing auctions and non-trading settlement days are outside this contract.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

from portfolio import china_calendar, market_calendar, market_clock, market_sessions


US_SHORT_DAYS = [
    ("2025-07-03", "2025-07-07"),
    ("2025-11-28", "2025-12-01"),
    ("2025-12-24", "2025-12-26"),
    ("2026-11-27", "2026-11-30"),
    ("2026-12-24", "2026-12-28"),
    ("2027-11-26", "2027-11-29"),
]
HK_SHORT_DAYS = [
    ("2025-01-28", "2025-02-03"),
    ("2025-12-24", "2025-12-29"),
    ("2025-12-31", "2026-01-02"),
    ("2026-02-16", "2026-02-20"),
    ("2026-12-24", "2026-12-28"),
    ("2026-12-31", "2027-01-04"),
    ("2027-02-05", "2027-02-10"),
    ("2027-12-24", "2027-12-28"),
    # The gate is covered; do not certify an unqualified 2028 annual calendar.
    ("2027-12-31", None),
]


@pytest.mark.parametrize("day,next_day", US_SHORT_DAYS)
def test_us_short_session_agrees_across_bot_manual_and_dashboard(day, next_day):
    d = date.fromisoformat(day)
    for at, expected in [(time(9, 29), False), (time(9, 30), True),
                         (time(12, 59, 59), True), (time(13), False),
                         (time(15), False)]:
        now = datetime.combine(d, at)
        assert market_calendar.is_open(now) is expected
        assert market_clock.is_open(now) is expected
        assert market_clock.status(now)["is_open"] is expected
        for book in ("autonomous", "self_directed"):
            shown = market_sessions.status_for_portfolio(book, now)
            assert shown["is_open"] is expected
            assert shown["early_close"] is True
            assert datetime.fromisoformat(shown["session_close"]).time() == time(13)
    closed = datetime.combine(d, time(13))
    assert market_clock.status(closed)["session"] == "post"
    assert market_calendar.next_open(closed).date().isoformat() == next_day
    manual_next = market_clock.next_open(closed)
    assert manual_next == datetime.fromisoformat(next_day + "T09:30")
    assert manual_next.tzinfo is None  # preserve the manual account's naive ET API
    shown = market_sessions.status_for_portfolio("autonomous", closed)
    assert shown["state"] == "early_close"
    assert shown["poll_after_seconds"] > 120


@pytest.mark.parametrize("day,next_day", HK_SHORT_DAYS)
def test_hk_half_day_never_reopens_at_lunch_or_in_afternoon(day, next_day):
    d = date.fromisoformat(day)
    zone = ZoneInfo("Asia/Hong_Kong")
    for at, expected in [(time(9, 29), False), (time(9, 30), True),
                         (time(11, 59, 59), True), (time(12), False),
                         (time(12, 30), False), (time(13), False),
                         (time(15, 30), False)]:
        now = datetime.combine(d, at, tzinfo=zone)
        assert china_calendar.is_open(now, venue="HK") is expected
        raw = china_calendar.status(now, venue="HK")
        shown = market_sessions.status_for_portfolio("hk", now)
        assert raw["open"] is expected
        assert shown["is_open"] is expected
        assert datetime.fromisoformat(shown["session_close"]).time() == time(12)
        if at >= time(12):
            assert shown["state"] == "early_close"
            # Consumer must not repair an incorrect raw calendar wake itself.
            assert datetime.fromisoformat(raw["next_open"]) == datetime.fromisoformat(shown["next_open"])
            if next_day is not None:
                assert china_calendar.next_open(now, venue="HK").date().isoformat() == next_day


def test_mainland_january_2_closure_is_not_imposed_on_hk():
    d = date(2026, 1, 2)
    assert china_calendar.is_holiday(d) is True
    assert china_calendar.is_trading_day(d) is False
    for hour in (10, 14):
        now = datetime(2026, 1, 2, hour)
        assert china_calendar.is_open(now) is False
        assert china_calendar.is_open(now, venue="HK") is True
        shown = market_sessions.status_for_portfolio("china", now)
        assert shown["state"] == "holiday"
        assert shown["next_open"].startswith("2026-01-05T09:30")
    assert china_calendar.next_trading_day(date(2025, 12, 31)) == date(2026, 1, 5)
    assert china_calendar.previous_trading_day(date(2026, 1, 5)) == date(2025, 12, 31)
    assert china_calendar.next_open(datetime(2025, 12, 31, 16)).date() == date(2026, 1, 5)


def test_published_2025_us_exceptional_closure():
    mourning = datetime(2025, 1, 9, 10)
    assert market_calendar.is_open(mourning) is False
    assert market_clock.is_open(mourning) is False
    assert market_sessions.status_for_portfolio("autonomous", mourning)["is_open"] is False
    assert market_calendar.next_open(mourning).date() == date(2025, 1, 10)


def test_hk_2025_june_2_is_open_while_mainland_is_closed():
    # HKEX CT/063/24 does not close the Monday after the Saturday Tuen Ng holiday.
    assert china_calendar.is_open(datetime(2025, 6, 2, 10), venue="HK") is True
    assert china_calendar.is_open(datetime(2025, 6, 2, 10), venue="CN") is False


def test_half_day_change_preserves_other_venues_and_regular_lunch():
    now = datetime(2026, 12, 24, 13, 30)
    assert china_calendar.is_open(now, venue="HK") is False
    assert china_calendar.is_open(now, venue="CN") is True
    normal_lunch = datetime(2026, 12, 23, 12, 30)
    for venue in ("CN", "HK"):
        assert china_calendar.is_open(normal_lunch, venue=venue) is False
        assert china_calendar.next_open(normal_lunch, venue=venue) == datetime(
            2026, 12, 23, 13, tzinfo=china_calendar.CST)
        assert china_calendar.is_open(datetime(2026, 12, 23, 13), venue=venue) is True


@pytest.mark.parametrize("instant", [
    datetime(2025, 7, 3, 17, tzinfo=timezone.utc),  # 13:00 EDT
    datetime(2026, 11, 27, 18, tzinfo=timezone.utc),  # 13:00 EST
])
def test_us_short_close_uses_exchange_time_in_both_dst_seasons(instant):
    assert market_calendar.is_open(instant) is False
    assert market_sessions.status_for_portfolio("autonomous", instant)["is_open"] is False


def _freeze_calendar_time(monkeypatch, instant):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(market_calendar, "datetime", FrozenDateTime)
    monkeypatch.setattr(china_calendar, "datetime", FrozenDateTime)


@pytest.mark.parametrize("book,instant", [
    ("autonomous", datetime(2026, 11, 27, 13, tzinfo=ZoneInfo("America/New_York"))),
    ("hk", datetime(2026, 12, 24, 12, tzinfo=ZoneInfo("Asia/Hong_Kong"))),
    ("hk", datetime(2026, 12, 24, 13, tzinfo=ZoneInfo("Asia/Hong_Kong"))),
    ("china", datetime(2026, 1, 2, 10, tzinfo=ZoneInfo("Asia/Shanghai"))),
])
def test_real_settlement_gate_stops_before_recovery_or_quotes(tmp_path, monkeypatch, book, instant):
    from bot import settle
    from portfolio import paper_account

    _freeze_calendar_time(monkeypatch, instant)
    book_dir = tmp_path / "closed-book"
    book_dir.mkdir()
    names = {"account": "account.json", "pending": "pending_orders.json",
             "fills": "fills.jsonl", "nav": "nav_history.jsonl"}
    paths = {"data": book_dir, **{key: book_dir / name for key, name in names.items()}}
    original = {}
    for key, name in names.items():
        raw = ("untouched-" + key + "\n").encode()
        (book_dir / name).write_bytes(raw)
        original[name] = raw
    monkeypatch.setattr(paper_account, "_paths", lambda pid=None: paths)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("forbidden")
        raise AssertionError("closed calendar entered recovery or price path")

    monkeypatch.setattr(paper_account, "recover_paper_transaction", forbidden)
    monkeypatch.setattr(paper_account, "pending_settlement_receipts", forbidden)
    for _ in range(2):
        assert settle.settle_open(book, instant.date().isoformat(), _open_price_fn=forbidden) == {
            "ok": False, "skipped": "market_closed"}
    assert calls == []
    assert {name: (book_dir / name).read_bytes() for name in original} == original
    # Public settle_open acquires its canonical file lock before checking the clock.
    assert {p.name for p in book_dir.iterdir()} == set(original) | {".paper_transaction.lock"}


def test_manual_late_half_day_order_queues_then_fills_once_at_valid_session(tmp_path, monkeypatch):
    from portfolio import self_directed as sd

    monkeypatch.setattr(sd, "_DATA", tmp_path)
    for attr, name in [("_ACCOUNT_PATH", "account.json"), ("_FILLS_PATH", "fills.jsonl"),
                       ("_PENDING_PATH", "pending.json"), ("_THESES_PATH", "theses.json"),
                       ("_NAV_PATH", "nav_history.jsonl")]:
        monkeypatch.setattr(sd, attr, tmp_path / name)

    def forbidden(*args, **kwargs):
        raise AssertionError("fixture must not request a live quote")

    monkeypatch.setattr(sd, "_current_price", forbidden)
    late = datetime(2026, 11, 27, 13, 30)
    order = sd.place_order("AAPL", "buy", 2, price=100, now=late)
    assert order["ok"] is True and order["status"] == "pending"
    assert not sd._FILLS_PATH.exists()
    saved_pending = sd._PENDING_PATH.read_bytes()
    assert sd.settle_pending(now=late, prices={"AAPL": 100}) == []
    assert sd._PENDING_PATH.read_bytes() == saved_pending
    next_session = datetime(2026, 11, 30, 9, 30)
    fills = sd.settle_pending(now=next_session, prices={"AAPL": 100})
    assert len(fills) == 1 and fills[0]["status"] == "filled"
    assert sd._load_account()["positions"]["AAPL"]["shares"] == 2
    assert sd.settle_pending(now=next_session, prices={"AAPL": 100}) == []
    assert len(sd._FILLS_PATH.read_text().splitlines()) == 1


def test_bot_half_day_queue_survives_then_settles_once_at_next_open(tmp_path, monkeypatch):
    from bot import autonomous, settle
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    late = datetime(2026, 11, 27, 13, 30, tzinfo=market_calendar.ET)
    _freeze_calendar_time(monkeypatch, late)
    paper_account._save_account(
        {"inception_date": "2026-11-27", "starting_nav": 1_000_000.0,
         "cash": 1_000_000.0, "positions": {}, "spy_shares": None,
         "spy_inception_price": None}, "autonomous")
    submission = {"holdings": [{"ticker": "AAPL", "weight": 0.5, "action_effective": "add"}],
                  "summary": "isolated half-day calendar fixture"}
    autonomous._append_decision_log(
        "2026-11-27", submission, [], [], {}, target_status="queued",
        effective_target={"AAPL": 0.5})
    paper_account.save_pending_target(
        {"AAPL": 0.5}, "2026-11-27", portfolio_id="autonomous",
        decision_snapshot=submission)
    book_dir = registry.data_dir("autonomous")
    preserved = {p.relative_to(book_dir): p.read_bytes() for p in book_dir.rglob("*") if p.is_file()}
    price_calls = []

    def fixture_open(ticker):
        price_calls.append(ticker)
        return 200.0, "polygon_open"

    assert settle.settle_open("autonomous", "2026-11-27", _open_price_fn=fixture_open) == {
        "ok": False, "skipped": "market_closed"}
    assert price_calls == []
    assert {p: (book_dir / p).read_bytes() for p in preserved} == preserved
    _freeze_calendar_time(monkeypatch, datetime(2026, 11, 30, 9, 30, tzinfo=market_calendar.ET))
    result = settle.settle_open("autonomous", "2026-11-30", _open_price_fn=fixture_open)
    assert result["ok"] is True
    assert len(result["executed"]) == 1
    assert result["executed"][0]["ticker"] == "AAPL"
    assert paper_account.load_pending_target("autonomous") is None
    fills_path = paper_account._paths("autonomous")["fills"]
    fills_before_repeat = fills_path.read_bytes()
    again = settle.settle_open("autonomous", "2026-11-30", _open_price_fn=fixture_open)
    assert again == {"ok": False, "skipped": "nothing_queued"}
    assert fills_path.read_bytes() == fills_before_repeat


@pytest.mark.parametrize("venue,expected", [("US", 48), ("CN", 43), ("HK", 48)])
def test_session_date_evidence_uses_the_existing_regional_schedule(venue, expected):
    from datetime import date
    from portfolio import market_calendar as us, china_calendar as asia

    begin, end = date(2026, 8, 11), date(2026, 10, 16)
    evidence = (us.session_date_evidence(begin, end) if venue == "US"
                else asia.session_date_evidence(begin, end, venue=venue))
    assert evidence["schema"] == "mastermind.cash_session_date_evidence.v1"
    assert evidence["venue"] == venue
    assert evidence["status"] == "available"
    assert evidence["start"] == begin.isoformat()
    assert evidence["end"] == end.isoformat()
    assert len(evidence["scheduled_dates"]) == expected
    assert evidence["scheduled_dates"] == sorted(set(evidence["scheduled_dates"]))
    assert evidence["source_refs"]
    assert evidence["scope"] == "published_static_cash_session_dates"
    assert evidence["exceptional_closures"] == "listed_only"
    assert evidence["price_or_cutoff_qualified"] is False
    excluded = {"US": ["2026-09-07"],
                "CN": ["2026-09-25", "2026-10-01", "2026-10-02",
                       "2026-10-05", "2026-10-06", "2026-10-07"],
                "HK": ["2026-10-01"]}[venue]
    assert not set(excluded).intersection(evidence["scheduled_dates"])


@pytest.mark.parametrize("venue", ["US", "CN", "HK"])
@pytest.mark.parametrize("year", [2024, 2028])
def test_session_date_evidence_withholds_outside_published_coverage(venue, year):
    from datetime import date
    from portfolio import market_calendar as us, china_calendar as asia

    begin, end = date(year, 1, 2), date(year, 1, 9)
    evidence = (us.session_date_evidence(begin, end) if venue == "US"
                else asia.session_date_evidence(begin, end, venue=venue))
    assert evidence["status"] == "unavailable"
    assert evidence["missing_reason"] == "outside_published_calendar_coverage"
    assert evidence["scheduled_dates"] is None


def test_session_date_evidence_never_qualifies_approximate_cn_2027(monkeypatch):
    from datetime import date
    from portfolio import china_calendar as asia

    def forbidden(*args, **kwargs):
        raise AssertionError("unpublished years must be withheld before weekday classification")

    monkeypatch.setattr(asia, "is_trading_day", forbidden)
    evidence = asia.session_date_evidence(date(2026, 12, 31), date(2027, 1, 4), venue="CN")
    assert evidence["coverage_end"] == "2026-12-31"
    assert evidence["status"] == "unavailable"
    assert evidence["scheduled_dates"] is None


@pytest.mark.parametrize("venue", ["", "hk", "US", None])
def test_session_date_evidence_does_not_apply_legacy_unknown_venue_fallback(venue):
    from datetime import date
    from portfolio import china_calendar as asia

    with pytest.raises(ValueError):
        asia.session_date_evidence(date(2026, 7, 1), date(2026, 7, 2), venue=venue)


@pytest.mark.parametrize("venue,day", [("US", "2026-11-27"), ("HK", "2026-02-16")])
def test_session_date_evidence_counts_shortened_day_once_without_price_claim(venue, day):
    from datetime import date
    from portfolio import market_calendar as us, china_calendar as asia

    d = date.fromisoformat(day)
    evidence = (us.session_date_evidence(d, d) if venue == "US"
                else asia.session_date_evidence(d, d, venue=venue))
    assert evidence["scheduled_dates"] == [day]
    assert evidence["price_or_cutoff_qualified"] is False


def test_session_date_evidence_requires_canonical_date_window():
    from datetime import date, datetime
    from portfolio import market_calendar as us, china_calendar as asia

    for begin, end in [
        ("2026-08-11", date(2026, 8, 12)),
        (date(2026, 8, 11), datetime(2026, 8, 12)),
        (date(2026, 8, 12), date(2026, 8, 11)),
    ]:
        for owner in (us, asia):
            with pytest.raises(ValueError):
                owner.session_date_evidence(begin, end)


def test_session_date_evidence_tracks_owner_closures_without_aliasing(monkeypatch):
    from datetime import date
    from portfolio import market_calendar as us

    begin, end = date(2026, 8, 11), date(2026, 8, 12)
    before = us.session_date_evidence(begin, end)
    monkeypatch.setattr(us, "_HOLIDAYS", us._HOLIDAYS | {begin})
    after = us.session_date_evidence(begin, end)
    assert before["scheduled_dates"] == ["2026-08-11", "2026-08-12"]
    assert after["scheduled_dates"] == ["2026-08-12"]
    assert "2026-08-11" in after["full_day_closures"]
    after["scheduled_dates"].append("fake")
    after["source_refs"].clear()
    repeated = us.session_date_evidence(begin, end)
    assert repeated["scheduled_dates"] == ["2026-08-12"]
    assert repeated["source_refs"]
