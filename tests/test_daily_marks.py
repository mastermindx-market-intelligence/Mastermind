"""Daily mark-to-market — offline/deterministic tests for the loop fix that re-marks EVERY book
once per trading day (so a book built once still advances its nav_history and can be graded forward).

Covers the three additive changes:
  1. paper_account.mark() now persists each held position's current_price into account.json.
  2. app.scheduler._daily_mark_job() marks a book that would NOT otherwise advance — a fresh
     nav_history row is appended with the new date (live-price helper monkeypatched; no network).
  3. bot.phase2's entry-technical fields flow into the shadow-input record (extension/rs/urgency/
     eq_grade/parabolic), read defensively from the published stockdata JSON.

No vendor/macro engine, no network, no LLM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Generator
from unittest import mock

import pytest

import bot  # noqa: F401  -> vendor/macro onto sys.path


# ---------------------------------------------------------------------------
# 1) mark() persists current_price onto the account positions
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_account(tmp_path: Path) -> Generator[None, None, None]:
    """Redirect the legacy (flagship) paper_account file paths into a fresh temp dir."""
    from portfolio import paper_account
    with (
        mock.patch.object(paper_account, "_DATA", tmp_path),
        mock.patch.object(paper_account, "_ACCOUNT_PATH", tmp_path / "account.json"),
        mock.patch.object(paper_account, "_FILLS_PATH", tmp_path / "fills.jsonl"),
        mock.patch.object(paper_account, "_NAV_PATH", tmp_path / "nav_history.jsonl"),
    ):
        yield


_PRICES = {"AAPL": 200.0, "MSFT": 400.0, "SPY": 500.0}
_PRICES_UP = {"AAPL": 220.0, "MSFT": 440.0, "SPY": 550.0}


def test_mark_persists_current_price(tmp_account: None) -> None:
    from portfolio import paper_account

    paper_account.rebalance({"AAPL": 0.4, "MSFT": 0.4}, _PRICES, "2026-01-02")
    paper_account.mark(_PRICES, "2026-01-02")

    state = paper_account._load_account()
    assert state["positions"]["AAPL"]["current_price"] == 200.0
    assert state["positions"]["MSFT"]["current_price"] == 400.0
    assert state["positions"]["AAPL"]["current_price_asof"] == "2026-01-02"
    assert state["positions"]["AAPL"]["current_price_source"] == "paper_account_mark"

    # a later mark at higher prices updates the persisted current_price in place
    paper_account.mark(_PRICES_UP, "2026-01-03")
    state = paper_account._load_account()
    assert state["positions"]["AAPL"]["current_price"] == 220.0
    assert state["positions"]["MSFT"]["current_price"] == 440.0


def test_mark_missing_price_retains_prior_observed_mark(tmp_account: None) -> None:
    """A missing quote cannot erase the last valid EOD mark or fabricate zero P&L at avg_cost."""
    from portfolio import paper_account

    paper_account.rebalance({"AAPL": 0.5}, _PRICES, "2026-01-02")
    avg = paper_account._load_account()["positions"]["AAPL"]["avg_cost"]
    paper_account.mark({"AAPL": 210.0, "SPY": 500.0}, "2026-01-02")

    # The following day's benchmark-only run has no AAPL evidence. Retain 210.0 and its original
    # provenance instead of replacing it with the unrelated cost basis.
    paper_account.mark({"SPY": 500.0}, "2026-01-03")
    state = paper_account._load_account()
    lot = state["positions"]["AAPL"]
    assert lot["current_price"] == 210.0
    assert lot["current_price"] != round(avg, 4)
    assert lot["current_price_asof"] == "2026-01-02"


def test_mark_backfill_cannot_regress_persisted_price(tmp_account: None) -> None:
    from portfolio import paper_account

    paper_account.rebalance({"AAPL": 0.5}, _PRICES, "2026-01-02")
    paper_account.mark({"AAPL": 220.0, "SPY": 500.0}, "2026-01-03")
    paper_account.mark({"AAPL": 180.0, "SPY": 490.0}, "2026-01-02")

    lot = paper_account._load_account()["positions"]["AAPL"]
    assert lot["current_price"] == 220.0
    assert lot["current_price_asof"] == "2026-01-03"


def test_mark_current_price_does_not_change_nav(tmp_account: None) -> None:
    """Persisting current_price is purely additive — the marked NAV row is identical to before."""
    from portfolio import paper_account

    paper_account.rebalance({"AAPL": 0.5}, _PRICES, "2026-01-02")
    paper_account.mark(_PRICES_UP, "2026-01-03")
    rows = paper_account._load_jsonl(paper_account._NAV_PATH)
    # NAV is recomputed from the prices dict (cash + shares*price), independent of current_price
    expected = paper_account.nav(_PRICES_UP)
    assert abs(rows[-1]["nav"] - round(expected, 2)) < 0.01


# ---------------------------------------------------------------------------
# 2) the daily mark job advances a book that would not otherwise re-mark
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_books(tmp_path: Path, monkeypatch) -> Generator[Path, None, None]:
    """Redirect EVERY book's state dir into a tmp tree by repointing the registry + legacy root,
    so the daily-mark job writes to isolated dirs (never the live data/portfolio*)."""
    from portfolio import registry, paper_account
    monkeypatch.setattr(registry, "_ROOT", tmp_path, raising=False)
    # the legacy flagship dir is registry._ROOT/data/portfolio; keep paper_account's own legacy
    # constants pointed there too so flagship resolves into the tmp tree as well.
    legacy = tmp_path / "data" / "portfolio"
    monkeypatch.setattr(paper_account, "_DATA", legacy, raising=False)
    monkeypatch.setattr(paper_account, "_ACCOUNT_PATH", legacy / "account.json", raising=False)
    monkeypatch.setattr(paper_account, "_FILLS_PATH", legacy / "fills.jsonl", raising=False)
    monkeypatch.setattr(paper_account, "_NAV_PATH", legacy / "nav_history.jsonl", raising=False)
    yield tmp_path


def _seed_held_book(pid: str, prices: dict, asof: str) -> None:
    """Build a held book for `pid` at `prices` and mark it once at `asof` (the 'built once' state)."""
    from portfolio import paper_account
    held = next(ticker for ticker in prices if ticker != "SPY")
    paper_account.rebalance({held: 0.5}, prices, asof, portfolio_id=pid)
    paper_account.mark(prices, asof, portfolio_id=pid)


# Consecutive REAL trading sessions on all three venues (US/CN/HK), verified against
# portfolio.market_calendar + portfolio.china_calendar. These used to be 2026-01-02 -> 2026-01-03,
# but 2026-01-03 is a SATURDAY: the job's mark date was never a trading session on any exchange,
# which is precisely the class of defect the per-venue gate now rejects.
_SEED_DAY = "2026-01-02"    # Friday
_MARK_DAY = "2026-01-05"    # the following Monday


def test_daily_mark_job_advances_unrebuilt_book(tmp_books: Path, monkeypatch) -> None:
    from app import scheduler
    from portfolio import paper_account

    # the autonomous Brain book was built + marked on day 1, then never rebuilt
    _seed_held_book("autonomous", {"AAPL": 200.0, "SPY": 500.0}, _SEED_DAY)
    before = paper_account._load_jsonl(paper_account._paths("autonomous")["nav"])
    assert {r["date"] for r in before} == {_SEED_DAY}

    # day 2: no rebuild — only the daily mark job runs, at fresh (higher) prices via a stubbed feed
    def _fake_price(t: str):
        return {"AAPL": 250.0, "SPY": 520.0}.get(t)
    monkeypatch.setattr(paper_account, "_current_price", _fake_price)
    monkeypatch.setattr(scheduler, "_today_iso", lambda: _MARK_DAY)

    scheduler._daily_mark_job()

    after = paper_account._load_jsonl(paper_account._paths("autonomous")["nav"])
    dates = {r["date"] for r in after}
    assert _MARK_DAY in dates, "daily mark job must append a fresh nav row for the new date"
    # the new row reflects the higher AAPL mark (the book actually advanced)
    new_row = next(r for r in after if r["date"] == _MARK_DAY)
    old_row = next(r for r in before if r["date"] == _SEED_DAY)
    assert new_row["nav"] > old_row["nav"]


def test_daily_mark_job_is_idempotent_per_date(tmp_books: Path, monkeypatch) -> None:
    from app import scheduler
    from portfolio import paper_account

    _seed_held_book("autonomous", {"AAPL": 200.0, "SPY": 500.0}, _SEED_DAY)
    monkeypatch.setattr(paper_account, "_current_price",
                        lambda t: {"AAPL": 250.0, "SPY": 520.0}.get(t))
    monkeypatch.setattr(scheduler, "_today_iso", lambda: _MARK_DAY)

    scheduler._daily_mark_job()
    scheduler._daily_mark_job()  # twice in the same day

    rows = paper_account._load_jsonl(paper_account._paths("autonomous")["nav"])
    same_day = [r for r in rows if r["date"] == _MARK_DAY]
    assert len(same_day) == 1, "mark() is idempotent per date — exactly one row per calendar day"


def test_daily_mark_job_one_failure_does_not_abort_others(tmp_books: Path, monkeypatch) -> None:
    """A book whose mark raises must not prevent the other books from being marked."""
    from app import scheduler
    from control_plane import locks
    from portfolio import fx, paper_account

    class _Lock:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    _seed_held_book("autonomous", {"AAPL": 200.0, "SPY": 500.0}, _SEED_DAY)
    _seed_held_book("china", {"600519.SS": 100.0}, _SEED_DAY)

    real_mark = paper_account.mark

    def _flaky_mark(prices, asof, portfolio_id=None, benchmark=None, **kwargs):
        if portfolio_id == "autonomous":
            raise RuntimeError("boom")
        return real_mark(prices, asof, portfolio_id=portfolio_id, benchmark=benchmark, **kwargs)

    monkeypatch.setattr(paper_account, "_current_price",
                        lambda t: {"AAPL": 250.0, "SPY": 520.0,
                                   "600519.SS": 110.0, "000300.SS": 4_100.0}.get(t))
    monkeypatch.setattr(fx, "usd_to", lambda px, ccy: (px or 0) * 7.0 if ccy == "CNY" else px)
    monkeypatch.setattr(paper_account, "pending_settlement_receipts", lambda pid=None: [])
    monkeypatch.setattr(locks, "acquire_or_log", lambda *args, **kwargs: _Lock())
    monkeypatch.setattr(paper_account, "mark", _flaky_mark)
    monkeypatch.setattr(scheduler, "_today_iso", lambda: _MARK_DAY)

    scheduler._daily_mark_job()  # must not raise

    # china still got its fresh mark even though autonomous blew up
    china_rows = paper_account._load_jsonl(paper_account._paths("china")["nav"])
    assert _MARK_DAY in {r["date"] for r in china_rows}


def test_daily_mark_job_skips_empty_books(tmp_books: Path, monkeypatch) -> None:
    """A book with no positions and no priceable benchmark must not write a spurious nav row."""
    from app import scheduler
    from portfolio import paper_account

    monkeypatch.setattr(paper_account, "_current_price", lambda t: None)  # nothing priceable
    # W-L / L1: the job also consults the ONE marking layer — stub it dark too so "nothing
    # priceable" holds across BOTH accessors (else the real yahoo parquet prices SPY for the
    # benchmark-only row). Both marks + the benchmark-ledger builder are best-effort here.
    from portfolio import marks
    monkeypatch.setattr(marks, "prices_for", lambda syms, asof, **kw: {})
    monkeypatch.setattr(scheduler, "_today_iso", lambda: "2026-01-03")

    scheduler._daily_mark_job()  # no positions anywhere, no prices → no rows

    for pid in scheduler._MARK_BOOK_IDS:
        rows = paper_account._load_jsonl(paper_account._paths(pid)["nav"])
        assert rows == [], f"{pid} should have no nav rows when nothing is priceable"


# ---------------------------------------------------------------------------
# 2b) the sweep is gated on each book's OWN venue trading calendar
# ---------------------------------------------------------------------------
# The cron is CronTrigger(day_of_week="mon-fri"), which excludes weekends and nothing else. Every
# venue also shuts on weekday holidays, and the three books trade on three different calendars, so
# a single cron expression cannot express them. Without a per-book gate a weekday holiday would
# accrue an extra rate/252 cash-yield day, append a nav_history row dated to a session that never
# happened, and carry stale prices forward as though the mark date had advanced.

_BOOK_TICKER = {"autonomous": "AAPL", "china": "600519.SS", "hk": "0700.HK"}

# Each row is a WEEKDAY (so the Mon–Fri cron fires) on which EXACTLY ONE venue is closed and the
# other two trade — verified against this repo's own portfolio.market_calendar (US) and
# portfolio.china_calendar (CN/HK) rather than assumed.
_VENUE_HOLIDAYS = [
    pytest.param("2026-01-19", "autonomous", id="mon-us-mlk-day"),
    pytest.param("2026-11-26", "autonomous", id="thu-us-thanksgiving"),
    pytest.param("2026-07-01", "hk", id="wed-hkex-sar-establishment-day"),
    pytest.param("2026-10-19", "hk", id="mon-hkex-chung-yeung"),
    # Mainland golden week: HKEX only closes 10-01, so 10-02 is CN-shut / US+HK trading.
    pytest.param("2026-10-02", "china", id="fri-cn-golden-week"),
    pytest.param("2026-05-04", "china", id="mon-cn-labour-day-bridge"),
]


def _assert_holiday_fixture_is_honest(asof: str, closed_book: str) -> None:
    """Guard the guard: if a calendar is ever corrected, fail loudly here rather than let a
    parametrised case quietly stop testing anything."""
    from app import scheduler
    for pid in scheduler._MARK_BOOK_IDS:
        venue = scheduler._MARK_BOOK_VENUES[pid]
        expected_open = pid != closed_book
        assert scheduler._is_trading_date(venue, asof) is expected_open, (
            f"fixture drift: {asof} on {venue} should be "
            f"{'open' if expected_open else 'closed'}"
        )


@pytest.fixture()
def three_books(tmp_books: Path, monkeypatch):
    """All three managed books held and marked once at _SEED_DAY, with every external seam stubbed
    so the ONLY thing that can stop a mark is the trading-date gate under test."""
    from control_plane import locks
    from portfolio import fx, marks, paper_account

    class _Lock:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    for pid, ticker in _BOOK_TICKER.items():
        _seed_held_book(pid, {ticker: 100.0}, _SEED_DAY)

    monkeypatch.setattr(paper_account, "_current_price", lambda t: 110.0)   # everything priceable
    monkeypatch.setattr(marks, "prices_for", lambda syms, asof, **kw: {})   # no live union marks
    monkeypatch.setattr(fx, "usd_to", lambda px, ccy: px)                   # no FX distortion
    monkeypatch.setattr(paper_account, "pending_settlement_receipts", lambda pid=None: [])
    monkeypatch.setattr(locks, "acquire_or_log", lambda *args, **kwargs: _Lock())
    return paper_account


def _book_state(paper_account, pid: str) -> dict:
    """Everything the daily sweep is allowed to mutate, in one comparable snapshot."""
    state = paper_account._load_account(pid)
    rows = paper_account._load_jsonl(paper_account._paths(pid)["nav"])
    return {
        "cash": state.get("cash"),
        "cash_yield_through": state.get("cash_yield_through"),
        "nav_dates": {r["date"] for r in rows},
        "price_asof": {t: lot.get("current_price_asof")
                       for t, lot in (state.get("positions") or {}).items()},
        "price": {t: lot.get("current_price")
                  for t, lot in (state.get("positions") or {}).items()},
    }


@pytest.mark.parametrize("asof,closed_book", _VENUE_HOLIDAYS)
def test_venue_holiday_leaves_the_closed_book_untouched(three_books, monkeypatch,
                                                        asof: str, closed_book: str) -> None:
    from app import scheduler
    paper_account = three_books
    _assert_holiday_fixture_is_honest(asof, closed_book)

    before = _book_state(paper_account, closed_book)
    monkeypatch.setattr(scheduler, "_today_iso", lambda: asof)

    scheduler._daily_mark_job()

    after = _book_state(paper_account, closed_book)
    assert after["cash"] == before["cash"], "cash yield accrued on a closed session"
    assert after["cash_yield_through"] == before["cash_yield_through"], (
        "cash_yield_through advanced onto a day the venue never traded"
    )
    assert asof not in after["nav_dates"], "a NAV row was written for a closed session"
    assert after["nav_dates"] == before["nav_dates"]
    assert after["price_asof"] == before["price_asof"], "a current_price date was fabricated"
    assert after["price"] == before["price"]


@pytest.mark.parametrize("asof,closed_book", _VENUE_HOLIDAYS)
def test_venue_holiday_still_marks_the_books_that_are_open(three_books, monkeypatch,
                                                           asof: str, closed_book: str) -> None:
    """One venue's holiday must not become a firm-wide outage."""
    from app import scheduler
    paper_account = three_books
    _assert_holiday_fixture_is_honest(asof, closed_book)
    monkeypatch.setattr(scheduler, "_today_iso", lambda: asof)

    scheduler._daily_mark_job()

    for pid in scheduler._MARK_BOOK_IDS:
        if pid == closed_book:
            continue
        state = _book_state(paper_account, pid)
        assert asof in state["nav_dates"], f"{pid} trades on {asof} and must still mark"
        assert state["cash_yield_through"] == asof, f"{pid} must accrue its trading-day yield"


def test_normal_trading_date_marks_and_accrues_every_book_once(three_books, monkeypatch) -> None:
    from app import scheduler
    paper_account = three_books
    for pid in scheduler._MARK_BOOK_IDS:
        assert scheduler._is_trading_date(scheduler._MARK_BOOK_VENUES[pid], _MARK_DAY)

    monkeypatch.setattr(scheduler, "_today_iso", lambda: _MARK_DAY)
    scheduler._daily_mark_job()
    first = {pid: _book_state(paper_account, pid) for pid in scheduler._MARK_BOOK_IDS}

    scheduler._daily_mark_job()   # same date again — must be a no-op, not a second accrual
    second = {pid: _book_state(paper_account, pid) for pid in scheduler._MARK_BOOK_IDS}

    for pid in scheduler._MARK_BOOK_IDS:
        assert _MARK_DAY in first[pid]["nav_dates"]
        assert first[pid]["cash_yield_through"] == _MARK_DAY
        assert second[pid]["cash"] == first[pid]["cash"], f"{pid} double-accrued on a re-run"
        rows = paper_account._load_jsonl(paper_account._paths(pid)["nav"])
        assert len([r for r in rows if r["date"] == _MARK_DAY]) == 1


def test_weekend_is_not_a_trading_date_for_any_venue() -> None:
    """The old tests marked on 2026-01-03, a Saturday. Pin why that is now refused."""
    from app import scheduler
    for venue in ("US", "CN", "HK"):
        assert scheduler._is_trading_date(venue, "2026-01-03") is False


def test_trading_date_gate_fails_closed_on_bad_input() -> None:
    """A malformed date or unknown venue must never be read as 'open'."""
    from app import scheduler
    assert scheduler._is_trading_date("US", "not-a-date") is False
    assert scheduler._is_trading_date("US", "") is False
    assert scheduler._is_trading_date("", "2026-01-05") is False
    assert scheduler._is_trading_date("XX", "2026-01-05") is False


def test_trading_date_gate_fails_closed_when_the_calendar_raises(monkeypatch) -> None:
    from app import scheduler
    from portfolio import market_calendar

    def _boom(_d):
        raise RuntimeError("calendar unavailable")

    monkeypatch.setattr(market_calendar, "is_trading_day", _boom)
    assert scheduler._is_trading_date("US", _MARK_DAY) is False


# ---------------------------------------------------------------------------
# 3) the shadow input carries the entry-technical fields
# ---------------------------------------------------------------------------

def test_entry_tech_fields_from_synthetic_stockdata(monkeypatch) -> None:
    from bot import phase2
    from portfolio import lenses as lenses_mod

    fake_sd = {
        "tech": {"pct_vs_200dma": 12.5},
        "momentum": {"alpha": {"rs": 88.0}},
        "entry_signal": {"urgency": "now"},
        "conviction": {"ext": {"grade": "steady", "parabolic": False}},
    }
    monkeypatch.setattr(lenses_mod, "_load", lambda rel: fake_sd)

    fields = phase2._entry_tech_fields("AAPL")
    assert fields["pct_vs_200dma"] == 12.5
    assert fields["rs"] == 88.0
    assert fields["urgency"] == "now"
    assert fields["eq_grade"] == "steady"
    assert fields["parabolic"] is False


def test_entry_tech_fields_defensive_on_missing(monkeypatch) -> None:
    """A missing/empty snapshot yields all-nullable fields — never raises, never fabricates."""
    from bot import phase2
    from portfolio import lenses as lenses_mod

    monkeypatch.setattr(lenses_mod, "_load", lambda rel: None)
    fields = phase2._entry_tech_fields("ZZZZ")
    assert fields["pct_vs_200dma"] is None
    assert fields["rs"] is None
    assert fields["urgency"] is None
    assert fields["eq_grade"] is None
    assert fields["parabolic"] is False  # bool(None) → False


def test_shadow_input_record_carries_entry_tech(monkeypatch) -> None:
    """The shadow-input record emitted for a candidate must carry the entry-technical fields.

    We reconstruct the record exactly as bot.phase2._emit_shadow builds it (the closure isn't
    importable), pinning the contract the L3 timing lever reads."""
    from bot import phase2
    from portfolio import lenses as lenses_mod

    fake_sd = {
        "tech": {"pct_vs_200dma": -8.0},
        "momentum": {"alpha": {"rs": 42.0}},
        "entry_signal": {"urgency": "soon"},
        "conviction": {"extension": {"grade": "stretched", "parabolic": True}},  # fallback path
    }
    monkeypatch.setattr(lenses_mod, "_load", lambda rel: fake_sd)

    tech = phase2._entry_tech_fields("NVDA")
    # the exact subset _emit_shadow merges into the input record
    record = {
        "ticker": "NVDA",
        "extension": tech["pct_vs_200dma"], "pct_vs_200dma": tech["pct_vs_200dma"],
        "rs": tech["rs"], "urgency": tech["urgency"],
        "eq_grade": tech["eq_grade"], "parabolic": tech["parabolic"],
    }
    assert record["extension"] == -8.0
    assert record["pct_vs_200dma"] == -8.0
    assert record["rs"] == 42.0
    assert record["urgency"] == "soon"
    assert record["eq_grade"] == "stretched"      # resolved via the .extension fallback path
    assert record["parabolic"] is True
