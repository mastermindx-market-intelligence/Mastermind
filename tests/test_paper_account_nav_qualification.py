"""A02 NAV qualification — valuation()/mark() classify every held line's price.

Covers the contract in portfolio/paper_account.py: FRESH/CARRIED/UNATTESTED/
UNPRICED classification, QUALIFIED/PROVISIONAL/WITHHELD status, the withheld
ledger, and the legacy nav() cost-basis substitution warning. Offline/fast;
all data dirs are redirected into per-test temp dirs (never the real data/).
"""
from __future__ import annotations

import inspect
import logging
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Generator
from unittest import mock

import pytest

import bot  # noqa: F401  -> vendor/macro onto sys.path


# ---------------------------------------------------------------------------
# Fixtures: redirect all file paths to a temp dir so tests are isolated
# (same pattern as tests/test_paper_account.py)
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_account(tmp_path: Path) -> Generator[None, None, None]:
    """Redirect paper_account file paths into a fresh temp directory."""
    from portfolio import paper_account

    with (
        mock.patch.object(paper_account, "_DATA", tmp_path),
        mock.patch.object(paper_account, "_ACCOUNT_PATH", tmp_path / "account.json"),
        mock.patch.object(paper_account, "_FILLS_PATH", tmp_path / "fills.jsonl"),
        mock.patch.object(paper_account, "_NAV_PATH", tmp_path / "nav_history.jsonl"),
    ):
        yield tmp_path


_PRICES = {"AAPL": 200.0, "MSFT": 400.0, "SPY": 500.0}
_D = "2026-03-10"

_FRESH_EV = {
    "AAPL": {"source": "polygon-eod", "price": 200.0, "stale_days": None},
    "MSFT": {"source": "polygon-eod", "price": 400.0, "stale_days": 0},
}


def _book(weights: dict[str, float] | None = None) -> None:
    """Rebalance the default book so positions + cash exist (no persisted marks)."""
    from portfolio import paper_account
    paper_account.rebalance(weights or {"AAPL": 0.5, "MSFT": 0.3}, _PRICES, _D)


def _strip_persisted_marks() -> None:
    """Drop every persisted current_price* field so lines are UNPRICED, not carried."""
    from portfolio import paper_account
    state = paper_account._load_account()
    for pos in state["positions"].values():
        for key in ("current_price", "current_price_asof",
                    "current_price_source", "current_price_time_kind"):
            pos.pop(key, None)
    paper_account._save_account(state)


def _withheld_rows(tmp_path: Path) -> list[dict]:
    from portfolio import paper_account
    path = paper_account._paths()["nav"].with_name("nav_withheld.jsonl")
    if not path.exists():
        return []
    return [
        json_row for line in path.read_text().splitlines()
        if line.strip() and (json_row := _loads(line)) is not None
    ]


def _loads(line: str):
    import json
    try:
        return json.loads(line)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# 1. all FRESH -> QUALIFIED
# ---------------------------------------------------------------------------

def test_all_fresh_is_qualified(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    v = paper_account.mark(_PRICES, _D, price_evidence=_FRESH_EV)

    assert v["nav_status"] == "QUALIFIED"
    assert v["nav_qualified"] == v["nav"]
    assert v["carried"] == []
    assert v["unattested"] == []
    assert v["unpriced"] == []
    assert all(line["class"] == "FRESH" for line in v["lines"].values())

    rows = paper_account._load_jsonl(paper_account._NAV_PATH)
    assert len(rows) == 1
    assert rows[0]["nav_status"] == "QUALIFIED"
    assert rows[0]["nav_qualified"] == rows[0]["nav"]
    assert rows[0]["mark_source"] == "paper_account_mark"
    assert rows[0]["unattested"] == []
    assert rows[0]["nav"] == pytest.approx(1_000_000.0)   # 0.8 deployed + 0.2 cash


# ---------------------------------------------------------------------------
# 2. CARRIED from input evidence -> PROVISIONAL, observed date persisted
# ---------------------------------------------------------------------------

def test_carried_input_evidence_is_provisional_and_stamps_observed_date(
        tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    ev = dict(_FRESH_EV)
    ev["AAPL"] = {"source": "last-good-carry", "price": 200.0, "stale_days": 2}
    v = paper_account.mark(_PRICES, _D, price_evidence=ev)

    assert v["nav_status"] == "PROVISIONAL"
    assert v["nav_qualified"] is None
    line = v["lines"]["AAPL"]
    assert line["class"] == "CARRIED"
    assert line["price_asof"] == "2026-03-08"          # asof - stale_days
    assert line["age_days"] == 2
    assert line["source"] == "last-good-carry"
    assert v["lines"]["MSFT"]["class"] == "FRESH"         # fresh evidence for MSFT
    assert v["unattested"] == []

    carried = v["carried"][0]
    assert carried["ticker"] == "AAPL"
    assert carried["age_days"] == 2
    assert carried["value"] == pytest.approx(500_000.0)
    assert carried["weight_of_invested"] == pytest.approx(0.625)   # / invested (800k)
    assert v["carried_value"] == pytest.approx(500_000.0)
    assert v["carried_fraction"] == pytest.approx(0.625)

    # per-position persistence: the OBSERVED date travels, never the mark date
    pos = paper_account._load_account()["positions"]["AAPL"]
    assert pos["current_price_asof"] == "2026-03-08"
    assert pos["current_price_asof"] != _D
    assert pos["current_price_source"] == "last-good-carry"

    rows = paper_account._load_jsonl(paper_account._NAV_PATH)
    assert rows[0]["nav_status"] == "PROVISIONAL"
    assert rows[0]["nav_qualified"] is None
    assert rows[0]["carried_value"] == pytest.approx(500_000.0)
    assert rows[0]["carried_fraction"] == pytest.approx(0.625)


def test_carried_input_does_not_roll_back_a_newer_stored_mark(tmp_account: Path) -> None:
    """The skip-newer-stored-mark rule stays, judged against the OBSERVED date."""
    from portfolio import paper_account

    _book()
    state = paper_account._load_account()
    state["positions"]["AAPL"]["current_price"] = 199.0
    state["positions"]["AAPL"]["current_price_asof"] = "2026-03-09"   # newer than the carry
    paper_account._save_account(state)

    ev = {"AAPL": {"source": "last-good-carry", "price": 200.0, "stale_days": 2}}
    paper_account.mark(_PRICES, _D, price_evidence=ev)

    pos = paper_account._load_account()["positions"]["AAPL"]
    assert pos["current_price_asof"] == "2026-03-09"    # untouched
    assert pos["current_price"] == 199.0


# ---------------------------------------------------------------------------
# 3. CARRIED from persisted metadata (within bound) -> PROVISIONAL
# ---------------------------------------------------------------------------

def test_persisted_mark_within_bound_is_carried(tmp_account: Path) -> None:
    from portfolio import paper_account

    state = {
        "cash": 1_000.0,
        "positions": {
            "AAPL": {"shares": 10.0, "avg_cost": 200.0, "current_price": 205.0,
                     "current_price_asof": "2026-03-05",
                     "current_price_source": "polygon-eod"},
        },
    }
    v = paper_account.valuation({}, _D, state=state)
    assert v["nav_status"] == "PROVISIONAL"
    line = v["lines"]["AAPL"]
    assert line["class"] == "CARRIED"
    assert line["price"] == 205.0
    assert line["price_asof"] == "2026-03-05"
    assert line["age_days"] == 5
    assert line["value"] == pytest.approx(2_050.0)
    assert v["nav"] == pytest.approx(3_050.0)
    assert v["nav_qualified"] is None


# ---------------------------------------------------------------------------
# 4. persisted mark NEWER than asof -> UNPRICED (direction-aware)
# ---------------------------------------------------------------------------

def test_persisted_mark_newer_than_asof_is_unpriced(tmp_account: Path) -> None:
    from portfolio import paper_account

    state = {
        "cash": 1_000.0,
        "positions": {
            "AAPL": {"shares": 10.0, "avg_cost": 200.0, "current_price": 205.0,
                     "current_price_asof": "2026-03-15",
                     "current_price_source": "polygon-eod"},
        },
    }
    v = paper_account.valuation({}, _D, state=state)
    assert v["nav_status"] == "WITHHELD"
    assert v["lines"]["AAPL"]["class"] == "UNPRICED"
    assert v["lines"]["AAPL"]["value"] is None
    assert v["nav"] is None
    assert v["invested"] is None
    row = v["unpriced"][0]
    assert row["ticker"] == "AAPL"
    assert row["last_observed_price"] == 205.0
    assert row["last_observed_asof"] == "2026-03-15"


# ---------------------------------------------------------------------------
# 5. persisted mark older than stale_max -> UNPRICED
# ---------------------------------------------------------------------------

def test_persisted_mark_older_than_stale_max_is_unpriced(tmp_account: Path) -> None:
    from portfolio import marks, paper_account

    stale_max = int(marks._stale_max_days())
    too_old = (date(2026, 3, 10) - timedelta(days=stale_max + 5)).isoformat()
    state = {
        "cash": 1_000.0,
        "positions": {
            "AAPL": {"shares": 10.0, "avg_cost": 200.0, "current_price": 205.0,
                     "current_price_asof": too_old,
                     "current_price_source": "polygon-eod"},
        },
    }
    v = paper_account.valuation({}, _D, state=state)
    assert v["nav_status"] == "WITHHELD"
    assert v["lines"]["AAPL"]["class"] == "UNPRICED"
    assert v["unpriced"][0]["last_observed_asof"] == too_old


# ---------------------------------------------------------------------------
# 6. UNATTESTED (valid price, no evidence) -> PROVISIONAL
# ---------------------------------------------------------------------------

def test_unattested_price_without_evidence_is_provisional(tmp_account: Path) -> None:
    from portfolio import paper_account

    state = {
        "cash": 1_000.0,
        "positions": {"AAPL": {"shares": 10.0, "avg_cost": 200.0}},
    }
    v = paper_account.valuation({"AAPL": 205.0}, _D, state=state)
    assert v["nav_status"] == "PROVISIONAL"
    assert v["lines"]["AAPL"]["class"] == "UNATTESTED"
    assert v["lines"]["AAPL"]["value"] == pytest.approx(2_050.0)
    assert v["unattested"] == ["AAPL"]
    assert v["nav_qualified"] is None
    assert v["nav"] == pytest.approx(3_050.0)


# ---------------------------------------------------------------------------
# 7. one line unpriced -> WITHHELD, no nav row, withheld ledger row
# ---------------------------------------------------------------------------

def test_one_unpriced_line_withholds_nav(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    v = paper_account.mark({"AAPL": 200.0, "SPY": 500.0}, _D)   # MSFT has no price

    assert v["nav_status"] == "WITHHELD"
    assert v["nav"] is None
    assert v["invested"] is None
    assert v["lines"]["MSFT"]["class"] == "UNPRICED"
    assert v["unpriced"][0]["ticker"] == "MSFT"
    assert v["unpriced"][0]["shares"] == pytest.approx(750.0)

    # no nav row is written for the withheld date
    assert paper_account._load_jsonl(paper_account._NAV_PATH) == []

    withheld = _withheld_rows(tmp_account)
    assert len(withheld) == 1
    assert withheld[0]["date"] == _D
    assert withheld[0]["mark_source"] == "paper_account_mark"
    assert withheld[0]["reason"] == "unpriced_held_position"
    assert withheld[0]["unpriced"][0]["ticker"] == "MSFT"


# ---------------------------------------------------------------------------
# 8. every line unpriced -> WITHHELD, no exception
# ---------------------------------------------------------------------------

def test_every_line_unpriced_withholds_without_raising(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    v = paper_account.mark({"SPY": 500.0}, _D)   # neither held name has a price

    assert v["nav_status"] == "WITHHELD"
    assert v["nav"] is None
    assert {row["ticker"] for row in v["unpriced"]} == {"AAPL", "MSFT"}
    assert paper_account._load_jsonl(paper_account._NAV_PATH) == []
    assert len(_withheld_rows(tmp_account)) == 1


# ---------------------------------------------------------------------------
# 9. WITHHELD leaves an existing row for that date byte-identical
# ---------------------------------------------------------------------------

def test_withheld_keeps_existing_nav_row_byte_identical(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    paper_account.mark(_PRICES, _D)          # a row for _D exists
    nav_path = paper_account._paths()["nav"]
    before = nav_path.read_bytes()

    _strip_persisted_marks()      # so the retry is UNPRICED, not carried
    v = paper_account.mark({"AAPL": 200.0, "SPY": 500.0}, _D)

    assert v["nav_status"] == "WITHHELD"
    assert nav_path.read_bytes() == before
    assert len(_withheld_rows(tmp_account)) == 1


# ---------------------------------------------------------------------------
# 10. withheld row idempotent per (date, mark_source)
# ---------------------------------------------------------------------------

def test_withheld_row_is_idempotent_per_date_and_source(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    paper_account.mark({"AAPL": 200.0, "SPY": 500.0}, _D)   # withheld, default source
    paper_account.mark({"AAPL": 200.0, "SPY": 500.0}, _D)   # identical retry

    rows = _withheld_rows(tmp_account)
    assert len(rows) == 1
    assert rows[0]["date"] == _D
    assert rows[0]["mark_source"] == "paper_account_mark"

    # a different mark_source is a separate ledger entry for the same date
    paper_account.mark({"AAPL": 200.0, "SPY": 500.0}, _D, mark_source="nightly_retry")
    rows = _withheld_rows(tmp_account)
    assert len(rows) == 2
    assert {r["mark_source"] for r in rows} == {"paper_account_mark", "nightly_retry"}


# ---------------------------------------------------------------------------
# 11. grep-style: no avg_cost on a value path of valuation/mark
# ---------------------------------------------------------------------------

def test_no_avg_cost_on_valuation_or_mark_value_paths(tmp_account: Path) -> None:
    from portfolio import paper_account

    src_valuation = inspect.getsource(paper_account.valuation)
    assert "avg_cost" not in src_valuation, (
        "valuation() must never mention avg_cost — not even in comments"
    )

    src_mark = inspect.getsource(paper_account.mark)
    assert re.search(r"prices\.get\([^)]*avg_cost", src_mark) is None, (
        "mark() must not substitute avg_cost for a missing price"
    )


# ---------------------------------------------------------------------------
# 12. nav() default behaviour unchanged + substitution warning
# ---------------------------------------------------------------------------

def test_nav_default_unchanged_and_warns_on_substitution(
        tmp_account: Path, caplog) -> None:
    from portfolio import paper_account

    _book()
    state = paper_account._load_account()
    aapl = state["positions"]["AAPL"]

    with caplog.at_level(logging.WARNING, logger="portfolio.paper_account"):
        # full prices: legacy value, no substitution, no warning
        assert paper_account.nav(_PRICES) == pytest.approx(
            state["cash"]
            + sum(state["positions"][t]["shares"] * _PRICES[t] for t in state["positions"])
        )
        assert not [r for r in caplog.records if "nav_avg_cost_fallback_used" in r.message]

        # AAPL priced, MSFT missing -> substituted at avg_cost, warned once
        msft = state["positions"]["MSFT"]
        expected = state["cash"] + aapl["shares"] * 200.0 + msft["shares"] * msft["avg_cost"]
        assert paper_account.nav({"AAPL": 200.0}) == pytest.approx(expected)

    warnings_ = [r for r in caplog.records if "nav_avg_cost_fallback_used" in r.message]
    assert len(warnings_) == 1
    assert "MSFT" in warnings_[0].getMessage()


# ---------------------------------------------------------------------------
# 13. nav(strict=True): raises NavWithheld / returns provisional
# ---------------------------------------------------------------------------

def test_nav_strict_raises_when_unpriced(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book({"AAPL": 0.5})
    with pytest.raises(paper_account.NavWithheld) as exc_info:
        paper_account.nav({}, strict=True, asof=_D)
    v = exc_info.value.valuation
    assert v["nav_status"] == "WITHHELD"
    assert v["unpriced"][0]["ticker"] == "AAPL"
    assert isinstance(exc_info.value, ValueError)


def test_nav_strict_returns_provisional_when_carried(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book({"AAPL": 0.5})
    paper_account.mark(_PRICES, _D)          # persists AAPL current_price at _D
    state = paper_account._load_account()
    aapl = state["positions"]["AAPL"]
    expected = state["cash"] + aapl["shares"] * aapl["current_price"]

    result = paper_account.nav({}, strict=True, asof="2026-03-11")   # 1-day carry
    assert isinstance(result, float)
    assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 14. mark() still blocked by a pending settlement receipt
# ---------------------------------------------------------------------------

def test_mark_still_blocked_by_pending_settlement_receipt(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    with mock.patch.object(
        paper_account, "pending_settlement_receipts",
        return_value=[{"transaction_id": "tx-unfinalized"}],
    ):
        with pytest.raises(
            paper_account.PaperTransactionConflict,
            match="NAV mark blocked by an unfinalized settlement receipt",
        ):
            paper_account.mark(_PRICES, _D)


# ---------------------------------------------------------------------------
# 15. no positions -> QUALIFIED
# ---------------------------------------------------------------------------

def test_no_positions_is_qualified(tmp_account: Path) -> None:
    from portfolio import paper_account

    v = paper_account.valuation({}, _D, state={"cash": 500.0, "positions": {}})
    assert v["nav_status"] == "QUALIFIED"
    assert v["nav"] == 500.0
    assert v["nav_qualified"] == 500.0
    assert v["carried"] == []
    assert v["carried_fraction"] == 0.0

    # and through mark(): an empty book writes a QUALIFIED row
    v2 = paper_account.mark({"SPY": 500.0}, _D)
    assert v2["nav_status"] == "QUALIFIED"
    rows = paper_account._load_jsonl(paper_account._NAV_PATH)
    assert rows[0]["nav_status"] == "QUALIFIED"
    assert rows[0]["nav"] == pytest.approx(paper_account._STARTING_NAV)


# ---------------------------------------------------------------------------
# 16. evidence shaped like marks.mark_symbols()["sources"] is accepted
# ---------------------------------------------------------------------------

def test_marks_source_shaped_evidence_is_accepted(tmp_account: Path) -> None:
    from portfolio import paper_account

    state = {
        "cash": 1_000.0,
        "positions": {
            "AAPL": {"shares": 10.0, "avg_cost": 200.0},
            "MSFT": {"shares": 5.0, "avg_cost": 400.0},
        },
    }
    # exactly the {source, price, stale_days} shape mark_symbols()["sources"] emits
    evidence = {
        "AAPL": {"source": "polygon-eod", "price": 200.0, "stale_days": None},
        "MSFT": {"source": "last-good-carry", "price": 400.0, "stale_days": 3},
    }
    v = paper_account.valuation({"AAPL": 200.0, "MSFT": 400.0}, _D,
                                state=state, price_evidence=evidence)
    assert v["lines"]["AAPL"]["class"] == "FRESH"
    assert v["lines"]["MSFT"]["class"] == "CARRIED"
    assert v["lines"]["MSFT"]["price_asof"] == "2026-03-07"
    assert v["lines"]["MSFT"]["age_days"] == 3
    assert v["nav_status"] == "PROVISIONAL"
    assert v["nav"] == pytest.approx(1_000.0 + 2_000.0 + 2_000.0)


# ---------------------------------------------------------------------------
# close_qualified (CONTRACTS §a item 1): an explicit False can value, never qualify
# ---------------------------------------------------------------------------

def test_close_qualified_false_is_unattested_not_fresh(tmp_account: Path) -> None:
    from portfolio import paper_account

    state = {
        "cash": 1_000.0,
        "positions": {
            "AAPL": {"shares": 10.0, "avg_cost": 200.0},
            "MSFT": {"shares": 5.0, "avg_cost": 400.0},
        },
    }
    evidence = {
        # same-date, not a carry, but an intraday print -> not close-grade
        "AAPL": {"source": "polygon-intraday", "price": 205.0, "stale_days": 0,
                 "observed_asof": _D, "close_qualified": False},
        "MSFT": {"source": "polygon-eod", "price": 400.0, "stale_days": 0,
                 "observed_asof": _D, "close_qualified": True},
    }
    v = paper_account.valuation({"AAPL": 205.0, "MSFT": 400.0}, _D,
                                state=state, price_evidence=evidence)
    assert v["lines"]["AAPL"]["class"] == "UNATTESTED"
    assert v["lines"]["AAPL"]["value"] == pytest.approx(2_050.0)
    assert v["lines"]["MSFT"]["class"] == "FRESH"
    assert v["unattested"] == ["AAPL"]
    assert v["nav_status"] == "PROVISIONAL"
    assert v["nav_qualified"] is None
    assert v["nav"] == pytest.approx(1_000.0 + 2_050.0 + 2_000.0)


def test_close_qualified_true_or_absent_keeps_fresh(tmp_account: Path) -> None:
    from portfolio import paper_account

    state = {
        "cash": 1_000.0,
        "positions": {
            "AAPL": {"shares": 10.0, "avg_cost": 200.0},
            "MSFT": {"shares": 5.0, "avg_cost": 400.0},
        },
    }
    evidence = {
        "AAPL": {"source": "polygon-eod", "price": 200.0, "stale_days": 0,
                 "observed_asof": _D, "close_qualified": True},
        "MSFT": {"source": "polygon-eod", "price": 400.0, "stale_days": None},
    }
    v = paper_account.valuation({"AAPL": 200.0, "MSFT": 400.0}, _D,
                                state=state, price_evidence=evidence)
    assert {t: line["class"] for t, line in v["lines"].items()} == {
        "AAPL": "FRESH", "MSFT": "FRESH"}
    assert v["nav_status"] == "QUALIFIED"
    assert v["nav_qualified"] == pytest.approx(v["nav"])


def test_close_qualified_false_on_a_carry_stays_carried(tmp_account: Path) -> None:
    from portfolio import paper_account

    state = {"cash": 0.0, "positions": {"AAPL": {"shares": 10.0, "avg_cost": 200.0}}}
    evidence = {"AAPL": {"source": "last-good-carry", "price": 199.0, "stale_days": 2,
                         "observed_asof": "2026-03-08", "close_qualified": False}}
    v = paper_account.valuation({"AAPL": 199.0}, _D, state=state, price_evidence=evidence)
    assert v["lines"]["AAPL"]["class"] == "CARRIED"
    assert v["lines"]["AAPL"]["price_asof"] == "2026-03-08"
    assert v["lines"]["AAPL"]["age_days"] == 2
    assert v["nav_status"] == "PROVISIONAL"


def test_mark_writes_unattested_close_unqualified_line(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    evidence = dict(_FRESH_EV)
    evidence["AAPL"] = {"source": "polygon-intraday", "price": 200.0, "stale_days": 0,
                        "observed_asof": _D, "close_qualified": False}
    v = paper_account.mark(_PRICES, _D, price_evidence=evidence)
    assert v["nav_status"] == "PROVISIONAL"
    rows = paper_account._load_jsonl(paper_account._NAV_PATH)
    assert len(rows) == 1
    assert rows[0]["nav_status"] == "PROVISIONAL"
    assert rows[0]["nav_qualified"] is None
    assert rows[0]["unattested"] == ["AAPL"]


# ---------------------------------------------------------------------------
# lr-a02-r1 finding 1: an unreadable stale_days can value a line, never qualify it
# ---------------------------------------------------------------------------

_ONE_LINE = {"cash": 0.0, "positions": {"AAPL": {"shares": 10.0, "avg_cost": 150.0}}}


@pytest.mark.parametrize("raw_stale", [
    "not-a-number", "", True, False, float("nan"), float("inf"), "-inf", [1], {"d": 1},
])
def test_unreadable_stale_days_is_unattested_not_fresh(tmp_account: Path, raw_stale) -> None:
    from portfolio import paper_account

    evidence = {"AAPL": {"source": "polygon-eod", "price": 200.0, "stale_days": raw_stale,
                         "observed_asof": _D}}
    v = paper_account.valuation({"AAPL": 200.0}, _D, state=_ONE_LINE, price_evidence=evidence)
    assert v["lines"]["AAPL"]["class"] == "UNATTESTED"
    assert v["lines"]["AAPL"]["value"] == pytest.approx(2_000.0)
    assert v["lines"]["AAPL"]["source"] == "polygon-eod"
    assert v["nav_status"] == "PROVISIONAL"
    assert v["nav_qualified"] is None


@pytest.mark.parametrize("raw_stale,age", [("2.9", 3), (2.9, 3), (0.4, 1), ("3", 3)])
def test_numeric_stale_days_rounds_away_from_zero_to_carried(
        tmp_account: Path, raw_stale, age: int) -> None:
    from portfolio import paper_account

    evidence = {"AAPL": {"source": "polygon-eod", "price": 200.0, "stale_days": raw_stale}}
    v = paper_account.valuation({"AAPL": 200.0}, _D, state=_ONE_LINE, price_evidence=evidence)
    line = v["lines"]["AAPL"]
    assert line["class"] == "CARRIED"
    assert line["age_days"] == age
    assert line["price_asof"] == (date.fromisoformat(_D) - timedelta(days=age)).isoformat()
    assert v["nav_status"] == "PROVISIONAL"


def test_negative_fractional_stale_days_is_unpriced(tmp_account: Path) -> None:
    from portfolio import paper_account

    evidence = {"AAPL": {"source": "polygon-eod", "price": 200.0, "stale_days": -0.5}}
    v = paper_account.valuation({"AAPL": 200.0}, _D, state=_ONE_LINE, price_evidence=evidence)
    assert v["lines"]["AAPL"]["class"] == "UNPRICED"
    assert v["nav_status"] == "WITHHELD"
    assert v["nav"] is None


def test_unreadable_stale_days_does_not_override_direction_or_carry(tmp_account: Path) -> None:
    from portfolio import paper_account

    future = (date.fromisoformat(_D) + timedelta(days=1)).isoformat()
    after = {"AAPL": {"source": "polygon-eod", "price": 200.0, "stale_days": "x",
                      "observed_asof": future}}
    v = paper_account.valuation({"AAPL": 200.0}, _D, state=_ONE_LINE, price_evidence=after)
    assert v["lines"]["AAPL"]["class"] == "UNPRICED"
    assert v["nav_status"] == "WITHHELD"

    carry = {"AAPL": {"source": "last-good-carry", "price": 200.0, "stale_days": "x",
                      "observed_asof": "2026-03-06"}}
    v = paper_account.valuation({"AAPL": 200.0}, _D, state=_ONE_LINE, price_evidence=carry)
    assert v["lines"]["AAPL"]["class"] == "CARRIED"
    assert v["lines"]["AAPL"]["price_asof"] == "2026-03-06"
    assert v["lines"]["AAPL"]["age_days"] == 4


# ---------------------------------------------------------------------------
# lr-a02-r1 finding 2: mark() never persists an input the qualification rejected
# ---------------------------------------------------------------------------

def test_mark_does_not_persist_an_unpriced_input(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    _strip_persisted_marks()
    future = (date.fromisoformat(_D) + timedelta(days=2)).isoformat()
    evidence = dict(_FRESH_EV)
    evidence["AAPL"] = {"source": "polygon-eod", "price": 200.0, "stale_days": None,
                        "observed_asof": future}
    v = paper_account.mark(_PRICES, _D, price_evidence=evidence)
    assert v["lines"]["AAPL"]["class"] == "UNPRICED"
    assert v["nav_status"] == "WITHHELD"

    positions = paper_account._load_account()["positions"]
    assert "current_price" not in positions["AAPL"]
    assert "current_price_asof" not in positions["AAPL"]
    assert positions["MSFT"]["current_price"] == pytest.approx(400.0)
    assert positions["MSFT"]["current_price_asof"] == _D
    assert paper_account._load_jsonl(paper_account._NAV_PATH) == []


def test_mark_keeps_the_prior_persisted_mark_when_input_is_unpriced(tmp_account: Path) -> None:
    from portfolio import paper_account

    _book()
    _strip_persisted_marks()
    prior = (date.fromisoformat(_D) - timedelta(days=1)).isoformat()
    state = paper_account._load_account()
    state["positions"]["AAPL"].update({"current_price": 190.0, "current_price_asof": prior,
                                       "current_price_source": "polygon-eod"})
    paper_account._save_account(state)

    future = (date.fromisoformat(_D) + timedelta(days=2)).isoformat()
    evidence = dict(_FRESH_EV)
    evidence["AAPL"] = {"source": "polygon-eod", "price": 250.0, "stale_days": None,
                        "observed_asof": future}
    paper_account.mark({**_PRICES, "AAPL": 250.0}, _D, price_evidence=evidence)
    aapl = paper_account._load_account()["positions"]["AAPL"]
    assert aapl["current_price"] == pytest.approx(190.0)
    assert aapl["current_price_asof"] == prior
    assert aapl["current_price_source"] == "polygon-eod"
