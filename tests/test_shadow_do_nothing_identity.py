"""Regression for the synthetic do-nothing shadow arm.

The arm is the churn counterfactual: it may take exactly ONE inception trade (the first usable
non-empty production allocation); after that its share inventory, average costs and cash are frozen.
Later signals and price moves may change marked NAV and the dated NAV rows — and nothing else.

Every case runs the REAL ``S.run`` / ``_synthetic_carry_targets`` / ``_rebalance`` / ``_mark`` /
``_mark_to`` / account+NAV persistence in test-owned temp paths. Only the two EXTERNAL price owners
(the canonical marking layer, the legacy undated accessor) plus the outcome store are stubbed; no
economic function is stubbed and no feed or network is reached.

Inventory assertions are EXACT (``==``), never ``pytest.approx``: an approximation tolerance is wide
enough to hide a small share/cash mutation — exactly the defect under test.
"""
from __future__ import annotations

import pytest

import bot  # noqa: F401 — bootstrap vendored macro
from portfolio import marks
from portfolio import paper_account
from portfolio import shadow_books as S


def _rec(ticker: str, weight: float, **kw) -> dict:
    rec = {"ticker": ticker, "forge_confirmed": True, "base_weight": weight, "name_cap": 1.0,
           "weight_forge": weight, "weight_prod": weight, "committee": None, "sentinel": None,
           "price": 100.0, "raw_prob_correct": 0.55, "horizon_d": 21}
    rec.update(kw)
    return rec


def _px(**extra) -> dict:
    """A COMPLETE explicit price set: SPY plus the whole defensive basket, plus any overrides.

    A symbol deliberately left out (e.g. AAA) is simply UNPRICED — nothing backfills it.
    """
    px = {t: 100.0 for t in S._DEFENSIVE_BASKET}
    px["SPY"] = 500.0
    px.update(extra)
    return px


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Test-owned shadow paths + offline external price owners. No feed, store or network."""
    monkeypatch.setattr(S, "_SHADOW", tmp_path)
    monkeypatch.setattr(S, "_INPUTS", tmp_path / "inputs")
    monkeypatch.setattr(S, "_BOOKS", tmp_path / "books")
    monkeypatch.setattr(S, "_LEADERBOARD", tmp_path / "leaderboard.json")
    # EXTERNAL price owner #1 — the canonical marking layer. The explicit seed IS the mark set, so a
    # symbol missing from it stays UNPRICED (never avg_cost, never a live feed).
    monkeypatch.setattr(marks, "prices_for", lambda want, asof, **kw: dict(kw.get("seed") or {}))
    # EXTERNAL price owner #2 — the legacy undated accessor; a historical replay must never read it.
    monkeypatch.setattr(paper_account, "_current_price",
                        lambda t: pytest.fail("historical shadow replay must not read live prices"))
    # outcome store — never grade a thesis against a real parquet store
    monkeypatch.setattr("brain.outcomes.label_thesis",
                        lambda t, asof=None: {"resolved": False, "rel_return": None})
    return tmp_path


@pytest.fixture()
def rebalance_calls(monkeypatch):
    """Record every _rebalance call and DELEGATE to the real one (an observer, not a stub)."""
    calls = []
    real = S._rebalance

    def spy(book_id, targets, prices, asof):
        calls.append({"book_id": book_id, "targets": dict(targets or {}), "asof": asof})
        return real(book_id, targets, prices, asof)

    monkeypatch.setattr(S, "_rebalance", spy)
    return calls


def _donothing_calls(calls: list) -> list:
    return [c for c in calls if c["book_id"] == "do_nothing"]


def _acct_bytes(sandbox, book_id: str = "do_nothing") -> bytes:
    return (sandbox / "books" / book_id / "account.json").read_bytes()


def _nav_bytes(sandbox, book_id: str = "do_nothing") -> bytes:
    return (sandbox / "books" / book_id / "nav_history.jsonl").read_bytes()


def test_seeded_do_nothing_freezes_inventory_across_signals_and_price_moves(sandbox, rebalance_calls):
    """After its ONE inception trade the shares, average costs and cash are EXACTLY frozen."""
    day1 = S.run("2026-06-01", prices=_px(AAA=100.0), inputs=[_rec("AAA", 0.20)])
    seeded = S._load_account("do_nothing")
    seeded_bytes = _acct_bytes(sandbox)

    assert seeded["positions"] == {"AAA": {"shares": 2000.0, "avg_cost": 100.0}}
    assert seeded["cash"] == 800000.0
    assert seeded["inception_date"] == "2026-06-01"
    assert seeded["starting_nav"] == 1000000.0
    assert day1["books"]["do_nothing"]["nav"] == 1000000.0
    assert len(_donothing_calls(rebalance_calls)) == 1              # exactly ONE trade edge
    assert _donothing_calls(rebalance_calls)[0]["targets"] == {"AAA": 0.2}

    day2 = S.run("2026-06-02", prices=_px(AAA=150.0, BBB=50.0, SPY=510.0),
                 inputs=[_rec("BBB", 0.80)])
    after = S._load_account("do_nothing")

    assert set(after["positions"]) == {"AAA"}                  # EXACT keys — no replacement
    assert after["positions"]["AAA"]["shares"] == 2000.0        # EXACT — no trim
    assert after["positions"]["AAA"]["avg_cost"] == 100.0       # EXACT — no cost-basis drift
    assert after["cash"] == 800000.0                            # EXACT — no cash move
    assert "BBB" not in after["positions"]                      # no new signal position
    assert after["inception_date"] == "2026-06-01"
    assert after["starting_nav"] == 1000000.0
    assert after == seeded                                       # the WHOLE account is identical
    assert _acct_bytes(sandbox) == seeded_bytes                 # ...byte-for-byte on disk

    assert day2["books"]["do_nothing"]["nav"] == 1100000.0
    assert day2["books"]["do_nothing"]["holdings"] == ["AAA"]
    assert day2["books"]["do_nothing"]["n_positions"] == 1
    assert day2["books"]["do_nothing"]["n_marks"] == 2
    assert len(_donothing_calls(rebalance_calls)) == 1          # never rebalanced again

    day3 = S.run("2026-06-03", prices=_px(AAA=120.0, BBB=40.0, SPY=490.0),
                 inputs=[_rec("BBB", 0.80)])
    after3 = S._load_account("do_nothing")
    assert after3 == seeded
    assert after3["positions"]["AAA"]["shares"] == 2000.0
    assert after3["positions"]["AAA"]["avg_cost"] == 100.0
    assert after3["cash"] == 800000.0
    assert day3["books"]["do_nothing"]["nav"] == 1040000.0
    assert len(_donothing_calls(rebalance_calls)) == 1

    assert S._nav_rows("do_nothing") == [
        {"date": "2026-06-01", "nav": 1000000.0, "cash": 800000.0,
         "invested": 200000.0, "spy_px": 500.0},
        {"date": "2026-06-02", "nav": 1100000.0, "cash": 800000.0,
         "invested": 300000.0, "spy_px": 510.0},
        {"date": "2026-06-03", "nav": 1040000.0, "cash": 800000.0,
         "invested": 240000.0, "spy_px": 490.0},
    ]


# ── 2. the delayed seed: an empty book stays ELIGIBLE for its first allocation ─
def test_delayed_first_usable_allocation_still_seeds_after_an_all_cash_run(sandbox, rebalance_calls):
    """An all-cash run stamps inception_date while positions stay EMPTY — such a book must stay
    ELIGIBLE for the first usable allocation."""
    # day 1 — a quiet carried day: no decision inputs at all, so no book is rebalanced
    S.run("2026-06-01", prices=_px(AAA=100.0), inputs=[])
    quiet = S._load_account("do_nothing")
    assert quiet["positions"] == {}
    assert quiet["inception_date"] is None
    assert not (sandbox / "books" / "do_nothing" / "account.json").exists()
    assert _donothing_calls(rebalance_calls) == []

    # day 2 — an explicit all-cash / non-confirmed allocation: the run IS executed (inputs present) so
    # inception_date is stamped, but nothing is forge-confirmed so NO position exists.
    S.run("2026-06-02", prices=_px(AAA=100.0),
          inputs=[_rec("AAA", 0.20, forge_confirmed=False, weight_forge=0.0, weight_prod=0.0)])
    allcash = S._load_account("do_nothing")
    assert allcash["positions"] == {}                  # still EMPTY ...
    assert allcash["inception_date"] == "2026-06-02"   # ... but the date IS stamped
    assert allcash["cash"] == 1000000.0
    assert (sandbox / "books" / "do_nothing" / "account.json").exists()

    S.run("2026-06-03", prices=_px(AAA=100.0), inputs=[_rec("AAA", 0.20)])
    seeded = S._load_account("do_nothing")
    assert seeded["positions"] == {"AAA": {"shares": 2000.0, "avg_cost": 100.0}}
    assert seeded["cash"] == 800000.0
    assert seeded["inception_date"] == "2026-06-02"    # the seeded inception is preserved
    assert _donothing_calls(rebalance_calls)[-1]["targets"] == {"AAA": 0.2}


def test_unpriced_first_candidate_does_not_consume_the_first_usable_allocation(sandbox, rebalance_calls):
    """A first candidate with no canonical mark buys nothing — and must not burn the seed."""
    S.run("2026-06-01", prices=_px(), inputs=[])          # quiet day: nothing yet
    S.run("2026-06-02", prices=_px(), inputs=[_rec("AAA", 0.20)])   # AAA is UNPRICED
    assert S._load_account("do_nothing")["positions"] == {}

    S.run("2026-06-03", prices=_px(AAA=100.0), inputs=[_rec("AAA", 0.20)])
    seeded = S._load_account("do_nothing")
    assert seeded["positions"] == {"AAA": {"shares": 2000.0, "avg_cost": 100.0}}
    assert seeded["cash"] == 800000.0


def test_seeded_do_nothing_holds_inventory_through_a_quiet_inputs_day(sandbox):
    """inputs==[] — a quiet/carried day. The carried book is held, the mark still moves."""
    S.run("2026-06-01", prices=_px(AAA=100.0), inputs=[_rec("AAA", 0.20)])
    before = S._load_account("do_nothing")
    before_bytes = _acct_bytes(sandbox)

    day2 = S.run("2026-06-02", prices=_px(AAA=150.0, SPY=510.0), inputs=[])

    after = S._load_account("do_nothing")
    assert after == before                                # the WHOLE account is identical
    assert after["positions"]["AAA"]["shares"] == 2000.0
    assert after["positions"]["AAA"]["avg_cost"] == 100.0
    assert after["cash"] == 800000.0
    assert _acct_bytes(sandbox) == before_bytes
    assert day2["books"]["do_nothing"]["nav"] == 1100000.0        # the mark still moved
    assert [r["date"] for r in S._nav_rows("do_nothing")] == ["2026-06-01", "2026-06-02"]


def test_seeded_do_nothing_holds_inventory_through_a_true_all_cash_day(sandbox):
    """inputs PRESENT but nothing forge-confirmed — a genuine all-cash signal."""
    S.run("2026-06-01", prices=_px(AAA=100.0), inputs=[_rec("AAA", 0.20)])
    before = S._load_account("do_nothing")
    before_bytes = _acct_bytes(sandbox)

    day2 = S.run("2026-06-02", prices=_px(AAA=150.0, SPY=510.0),
                 inputs=[_rec("AAA", 0.20, forge_confirmed=False,
                              weight_forge=0.0, weight_prod=0.0)])

    after = S._load_account("do_nothing")
    assert after == before
    assert after["positions"]["AAA"]["shares"] == 2000.0
    assert after["positions"]["AAA"]["avg_cost"] == 100.0
    assert after["cash"] == 800000.0
    assert _acct_bytes(sandbox) == before_bytes
    assert day2["books"]["do_nothing"]["nav"] == 1100000.0
    assert [r["date"] for r in S._nav_rows("do_nothing")] == ["2026-06-01", "2026-06-02"]


def test_repeating_the_same_asof_keeps_inventory_and_one_dated_nav_row(sandbox):
    """Re-running one date is idempotent for the dated NAV and inert for the inventory."""
    S.run("2026-06-01", prices=_px(AAA=100.0), inputs=[_rec("AAA", 0.20)])
    before = S._load_account("do_nothing")

    S.run("2026-06-01", prices=_px(AAA=150.0, BBB=50.0, SPY=510.0), inputs=[_rec("BBB", 0.80)])

    after = S._load_account("do_nothing")
    assert after == before
    assert after["positions"]["AAA"]["shares"] == 2000.0
    assert after["cash"] == 800000.0
    assert "BBB" not in after["positions"]
    rows = S._nav_rows("do_nothing")
    assert len(rows) == 1
    assert [r["date"] for r in rows] == ["2026-06-01"]
    assert rows[0]["nav"] == 1100000.0          # the day's row is re-marked, not duplicated


def test_missing_held_mark_preserves_account_and_prior_nav_bytes(sandbox):
    """No canonical mark for the held name: refuse, never fabricate."""
    S.run("2026-06-01", prices=_px(AAA=100.0), inputs=[_rec("AAA", 0.20)])
    acct_before = _acct_bytes(sandbox)
    nav_before = _nav_bytes(sandbox)

    res = S.run("2026-06-02", prices=_px(SPY=510.0), inputs=[_rec("AAA", 0.20)])

    assert _acct_bytes(sandbox) == acct_before
    assert _nav_bytes(sandbox) == nav_before
    assert [r["date"] for r in S._nav_rows("do_nothing")] == ["2026-06-01"]
    assert "do_nothing" not in res["books"]              # no fabricated book result
    assert "defensive" in res["books"]                   # per-book refusal stays isolated
    with pytest.raises(S.ShadowMarkUnavailable):
        S._mark("do_nothing", {}, "2026-06-02")


def test_freeze_is_do_nothing_only_prod_still_liquidates_and_defensive_still_rebalances(sandbox):
    """A broad freeze would strand the ordinary books — this pins the scope of the guard."""
    S.run("2026-06-01", prices=_px(AAA=100.0), inputs=[_rec("AAA", 0.20)])
    prod1 = S._load_account("prod")
    def1 = S._load_account("defensive")
    assert prod1["positions"]["AAA"]["shares"] == 2000.0
    assert set(def1["positions"]) == set(S._DEFENSIVE_BASKET)

    S.run("2026-06-02", prices=_px(AAA=150.0, XLU=200.0, SPY=510.0),
          inputs=[_rec("AAA", 0.20, forge_confirmed=False, weight_forge=0.0, weight_prod=0.0)])
    assert "AAA" not in S._load_account("prod")["positions"]          # prod still liquidates
    assert S._load_account("do_nothing")["positions"]["AAA"]["shares"] == 2000.0

    def2 = S._load_account("defensive")
    assert def2["positions"]["XLU"]["shares"] != def1["positions"]["XLU"]["shares"]
    assert def2["positions"]["XLU"]["shares"] == 1562.5
