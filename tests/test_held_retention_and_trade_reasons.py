"""Two regressions from the 2026-08-06 portfolio-decisions pass.

A. HELD NAMES ARE ALWAYS EVALUATED (portfolio/conviction.py)
   `candidates()` unions the DISCOVERY sources (universe / intake / regime seed / Prophet) and
   never included the names we already own. `build()` then looped over that pool only, so `held`
   was consulted purely as an `is_held` flag INSIDE the loop. A held name that had merely fallen
   out of every discovery source was therefore never evaluated, never reached the exit hysteresis,
   and silently vanished from the target book — which `paper_account.rebalance` / `queue_orders`
   executes as a FULL SELL. Every exit rule (`_EXIT_CONFLUENCE_FLOOR`, the freeze-on-degrade
   branch) was dead code for exactly the names it was written to protect.

   The invariant these tests pin: board membership is a DISCOVERY signal, never an EXIT signal.

B. PER-TRADE REASONING (brain/trade_rationale.py)
   The decision log recorded a book-level summary and a per-HOLDING rationale but nothing per
   TRADE, so an add or an exit carried no cause. `reconcile()` derives one row per trade that
   ACTUALLY FILLED and joins the Brain's stated reason onto it — deliberately fill-driven so an
   unexplained trade is visible rather than absent.
"""
from __future__ import annotations

import pytest

from brain import trade_rationale
from portfolio import conviction


# ===========================================================================
# A. held-name retention
# ===========================================================================

def _syn(**over):
    """A minimal lenses.full() payload. Healthy by default; override to break it."""
    syn = {"confluence": 0.55, "vetoes": [], "bull": ["b"], "bear": [],
           "size_authority": "up", "divergences": []}
    syn.update(over)
    return {"synthesis": syn, "rows": []}


@pytest.fixture
def _inert_sizing(monkeypatch):
    """Neutralize the vol-managed sizing lever. `risk_sizing.apply` falls back to an on-the-fly
    inverse-vol estimate for OFF-BOARD names, which reaches the live price store — these tests are
    about MEMBERSHIP (is the name in the book at all), not weights, so the lever is stubbed out to
    keep them hermetic and offline. Patched on the module object because conviction imports it
    lazily inside build()."""
    from portfolio import risk_sizing
    monkeypatch.setattr(risk_sizing, "apply", lambda positions, *a, **k: positions)


@pytest.fixture
def _no_discovery(monkeypatch, _inert_sizing):
    """The exact failure shape: EVERY discovery source is empty, so the pool is empty unless the
    held names are unioned in. Also disables the W8 entry/context assessors (they only touch NEW
    entries and would otherwise reach for vendor artifacts absent in a bare checkout)."""
    monkeypatch.setattr(conviction, "candidates", lambda: [])
    monkeypatch.setattr(conviction, "_entry_gate_enabled", lambda: False)


def test_held_name_absent_from_every_source_is_still_evaluated(_no_discovery, monkeypatch):
    """The core regression. A held name surfaced by NO discovery source must still be scored."""
    seen: list[str] = []

    def _full(t, _kind="name"):
        seen.append(t)
        return _syn()

    monkeypatch.setattr(conviction.lenses, "full", _full)
    sized, _rejected = conviction.build(1.0, held={"HELDCO"})
    assert "HELDCO" in seen, "a held name must be evaluated even when no board surfaces it"
    assert "HELDCO" in {p["ticker"] for p in sized}, "a healthy held name must stay in the book"


def test_held_name_off_board_but_healthy_is_not_sold(_no_discovery, monkeypatch):
    """Confluence comfortably above the EXIT floor but BELOW the 0.30 entry bar: the asymmetric
    hysteresis must keep the position. This is the case the old code sold — the name is not
    re-enterable today, which is precisely why it must not be judged by the entry bar."""
    monkeypatch.setattr(conviction.lenses, "full",
                        lambda t, k="name": _syn(confluence=0.28, size_authority="hold"))
    sized, _ = conviction.build(1.0, held={"HELDCO"})
    assert "HELDCO" in {p["ticker"] for p in sized}
    held_row = next(p for p in sized if p["ticker"] == "HELDCO")
    assert held_row["retained"] is True          # kept by hysteresis, not re-entered
    assert held_row["verdict"] == "hold"


def test_held_name_below_exit_floor_does_leave_and_says_why(_no_discovery, monkeypatch):
    """The fix must not make positions immortal. Below `_EXIT_CONFLUENCE_FLOOR` the name still
    goes — but now as an explicit, attributable EXIT rather than a silent disappearance."""
    monkeypatch.setattr(conviction.lenses, "full",
                        lambda t, k="name": _syn(confluence=0.10, size_authority="hold"))
    sized, rejected = conviction.build(1.0, held={"HELDCO"})
    assert "HELDCO" not in {p["ticker"] for p in sized}
    row = next(r for r in rejected if r["ticker"] == "HELDCO")
    assert row["held_exit"] is True
    assert row["exit_trigger"] == "confluence_below_exit_floor"
    # the sell reason must quote the EXIT floor it actually failed, not the entry bar
    assert "0.25" in row["reason"]


def test_held_name_with_hard_veto_exits_and_is_attributed(_no_discovery, monkeypatch):
    monkeypatch.setattr(conviction.lenses, "full",
                        lambda t, k="name": _syn(vetoes=["altman_distress"]))
    sized, rejected = conviction.build(1.0, held={"HELDCO"})
    assert "HELDCO" not in {p["ticker"] for p in sized}
    row = next(r for r in rejected if r["ticker"] == "HELDCO")
    assert row["held_exit"] is True and row["exit_trigger"] == "hard_veto"


def test_unreadable_held_name_freezes_instead_of_liquidating(_no_discovery, monkeypatch):
    """A read failure on a HELD name must never liquidate it (the documented freeze doctrine).
    A read failure on a name we do NOT own is still just skipped."""
    def _boom(t, _kind="name"):
        raise RuntimeError("vendor artifact unreadable")

    monkeypatch.setattr(conviction.lenses, "full", _boom)
    sized, _ = conviction.build(1.0, held={"HELDCO"})
    tickers = {p["ticker"] for p in sized}
    assert "HELDCO" in tickers, "an unreadable HELD name must freeze, not be sold"
    row = next(p for p in sized if p["ticker"] == "HELDCO")
    assert row["retained_reason"] == "data_degraded_freeze"


def test_unheld_unreadable_name_is_still_skipped(monkeypatch, _inert_sizing):
    """The freeze is scoped to held names — it must not resurrect broken candidates."""
    monkeypatch.setattr(conviction, "candidates", lambda: ["RANDOMCO"])
    monkeypatch.setattr(conviction, "_entry_gate_enabled", lambda: False)

    def _boom(t, _kind="name"):
        raise RuntimeError("nope")

    monkeypatch.setattr(conviction.lenses, "full", _boom)
    sized, rejected = conviction.build(1.0, held=set())
    assert "RANDOMCO" not in {p["ticker"] for p in sized}
    assert "RANDOMCO" not in {r["ticker"] for r in rejected}


def test_manual_exclude_still_wins_over_the_held_union(_no_discovery, monkeypatch):
    """`_MANUAL_EXCLUDE` is the operator's explicit do-not-carry kill-switch; the retention fix
    must not silently widen it into 'hold forever'."""
    excluded = sorted(conviction._MANUAL_EXCLUDE)[0]
    monkeypatch.setattr(conviction.lenses, "full", lambda t, k="name": _syn())
    sized, _ = conviction.build(1.0, held={excluded})
    assert excluded not in {p["ticker"] for p in sized}


# ===========================================================================
# B. per-trade reasoning
# ===========================================================================

def test_reconcile_derives_action_from_the_fills_not_the_label():
    """The action is DERIVED from the position transition — a Brain that mislabels its own trade
    is recorded accurately AND flagged, rather than believed."""
    stated = [{"ticker": "AAA", "action": "trim", "reason": "thesis intact, taking some off"}]
    executed = [{"ticker": "AAA", "side": "sell", "shares": 10, "price": 5.0, "value": 50.0}]
    rows = trade_rationale.reconcile(stated, executed,
                                     prior_positions=["AAA"], target_holdings=[])
    assert len(rows) == 1
    # it left the book entirely → that is an EXIT, whatever the Brain called it
    assert rows[0]["action"] == "exit"
    assert rows[0]["stated_action"] == "trim"
    assert rows[0]["action_mismatch"] is True
    assert rows[0]["explained"] is True


def test_reconcile_distinguishes_new_buy_from_add_and_trim_from_exit():
    executed = [
        {"ticker": "NEW", "side": "buy", "shares": 5},
        {"ticker": "OLD", "side": "buy", "shares": 5},
        {"ticker": "CUT", "side": "sell", "shares": 5},
        {"ticker": "GONE", "side": "sell", "shares": 5},
    ]
    rows = {r["ticker"]: r for r in trade_rationale.reconcile(
        [], executed,
        prior_positions={"OLD": {}, "CUT": {}, "GONE": {}},
        target_holdings=[{"ticker": "NEW"}, {"ticker": "OLD"}, {"ticker": "CUT"}])}
    assert rows["NEW"]["action"] == "new_buy"
    assert rows["OLD"]["action"] == "add"
    assert rows["CUT"]["action"] == "trim"
    assert rows["GONE"]["action"] == "exit"


def test_unexplained_trade_is_logged_not_dropped():
    """The whole point: a trade the Brain never justified must still appear, marked unexplained."""
    executed = [{"ticker": "QUIET", "side": "sell", "shares": 3}]
    rows = trade_rationale.reconcile([], executed,
                                     prior_positions=["QUIET"], target_holdings=[])
    assert len(rows) == 1
    assert rows[0]["explained"] is False and rows[0]["reason"] is None
    cov = trade_rationale.coverage(rows)
    assert cov == {"n_trades": 1, "n_explained": 0, "pct_explained": 0.0, "unexplained": ["QUIET"]}


def test_stated_reason_for_a_trade_that_never_filled_is_not_invented():
    """Rows are driven by fills. A claimed trade with no fill produces no executed row (its prose
    survives separately as `trades_stated` in the decision log)."""
    stated = [{"ticker": "PHANTOM", "action": "new_buy", "reason": "great setup"}]
    assert trade_rationale.reconcile(stated, []) == []


def test_normalize_is_defensive():
    assert trade_rationale.normalize(None) == []
    assert trade_rationale.normalize("nope") == []
    assert trade_rationale.normalize([{"ticker": "A"}]) == []          # no reason → dropped
    assert trade_rationale.normalize([{"reason": "x"}]) == []          # no ticker → dropped
    dupe = [{"ticker": "a", "action": "add", "reason": "first"},
            {"ticker": "A", "action": "trim", "reason": "second"}]
    out = trade_rationale.normalize(dupe)
    assert len(out) == 1 and out[0]["ticker"] == "A" and out[0]["reason"] == "first"
    # an unrecognized action degrades to None rather than being trusted through
    assert trade_rationale.normalize(
        [{"ticker": "A", "action": "yolo", "reason": "r"}])[0]["stated_action"] is None


def test_reconcile_never_raises_on_garbage():
    assert trade_rationale.reconcile(None, None) == []
    assert trade_rationale.reconcile([], [{"nonsense": True}, "string", None]) == []
    assert trade_rationale.coverage(None)["n_trades"] == 0
