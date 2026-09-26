"""Mark-authority proof for the trusted decision-normalization boundary.

Average acquisition cost is historical transaction evidence. It is never a current market
observation, so it may not be substituted for an absent quote and then consumed as current
NAV / weight evidence by the deterministic allocator.

These tests own that boundary contract at ``brain.decision_submission._latest_holdings`` and
prove it through the real regional MCP callers: an unpriceable held line freezes the whole
submission *before* any numeric target is constructed, and the prior paper book survives
untouched (no write, no sell, no queue, no account mutation).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from brain import decision_submission as ds


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _args(holdings=None, exits=None):
    """A minimally valid ordinal submission that needs current weights to allocate."""
    return {
        "holdings": holdings or [],
        "summary": "reviewed book",
        "exit_decisions": exits or [],
        "falsifiers": ["market frame breaks"],
        "evidence_planes": ["prophet"],
        "source_provenance": ["prophet:index:test"],
        "expected_failure_mode": "rotation reverses",
        "risk_posture": "normal",
        "cash_rationale": "candidate quality determines residual cash",
        "decision_memo": {"candidate_funnel": {"reviewed": 4}},
    }


def _seed_account(monkeypatch, *, positions, cash, price, currency="USD", fx_rate=None):
    """Seed a paper account whose held names may or may not carry a trustworthy mark.

    ``price`` is a ``ticker -> USD mark or None`` map; ``None`` models a quote outage while a
    valid historical ``avg_cost`` is still on file.
    """
    from portfolio import fx, paper_account, registry

    monkeypatch.setattr(registry, "currency", lambda book: currency)
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda book: {"cash": cash, "positions": json.loads(json.dumps(positions))},
    )
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: price.get(ticker))
    if fx_rate is not None:
        monkeypatch.setattr(fx, "usd_to", lambda px, cur: px * fx_rate)


class _MutationSentinel:
    """Fails the test if the refusal path touches any paper-account write surface."""

    def __init__(self, monkeypatch):
        from portfolio import paper_account

        self.calls: list[str] = []
        for name in (
            "_save_account",
            "_write_transaction",
            "_write_settlement_receipt",
            "_save_pending",
            "save_pending_target",
        ):
            if hasattr(paper_account, name):
                monkeypatch.setattr(
                    paper_account,
                    name,
                    lambda *a, _n=name, **k: self.calls.append(_n),
                )


# ---------------------------------------------------------------------------
# 1. the fabrication itself
# ---------------------------------------------------------------------------


def test_unpriceable_holding_is_not_valued_at_average_cost(monkeypatch):
    """A held name with valid shares + valid avg_cost but NO trustworthy current mark must
    not be handed a fabricated current valuation."""
    _seed_account(
        monkeypatch,
        positions={"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
        cash=500.0,
        price={"BIIB": None},
    )
    with pytest.raises(
        ds.DecisionBoundaryFreeze, match=r"^unpriceable_held_position:BIIB$"
    ):
        ds._latest_holdings("autonomous")


@pytest.mark.parametrize(
    "avg_cost, truth_note",
    [
        (100.0, "bought at 100, actually near 55 — cost overstates the position"),
        (100.0, "bought at 100, actually near 180 — cost understates the position"),
        (1.0, "a near-zero cost basis fabricates a near-zero weight"),
        (10_000.0, "an extreme cost basis fabricates a dominant weight"),
    ],
)
def test_cost_substitution_is_direction_blind_not_conservative(
    monkeypatch, avg_cost, truth_note
):
    """The substitution is not a conservative valuation: it is purely a function of an old
    transaction, so it fabricates in whichever direction the cost basis happens to sit."""
    _seed_account(
        monkeypatch,
        positions={"BIIB": {"shares": 5.0, "avg_cost": avg_cost}},
        cash=500.0,
        price={"BIIB": None},
    )
    with pytest.raises(
        ds.DecisionBoundaryFreeze, match=r"^unpriceable_held_position:BIIB$"
    ):
        ds._latest_holdings("autonomous")


def test_one_unpriceable_line_freezes_the_whole_book_not_just_that_line(monkeypatch):
    """A priced sibling must not be allowed to carry an unpriceable line into a NAV: the
    denominator itself is unknown, so every weight in the book is unproven."""
    _seed_account(
        monkeypatch,
        positions={
            "AAPL": {"shares": 10.0, "avg_cost": 50.0},
            "BIIB": {"shares": 5.0, "avg_cost": 100.0},
        },
        cash=500.0,
        price={"AAPL": 80.0, "BIIB": None},
    )
    with pytest.raises(
        ds.DecisionBoundaryFreeze, match=r"^unpriceable_held_position:BIIB$"
    ):
        ds._latest_holdings("autonomous")


def test_zero_and_negative_quotes_are_not_valid_marks(monkeypatch):
    """A non-positive or non-finite quote is an absent quote, not a cheap holding."""
    for bad in (0.0, -12.0, float("nan"), float("inf")):
        _seed_account(
            monkeypatch,
            positions={"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
            cash=500.0,
            price={"BIIB": bad},
        )
        with pytest.raises(
            ds.DecisionBoundaryFreeze, match=r"^unpriceable_held_position:BIIB$"
        ):
            ds._latest_holdings("autonomous")


def test_raising_price_source_is_not_rescued_by_cost(monkeypatch):
    """A price source that raises is an absent authority, not a licence to use cost."""
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "currency", lambda book: "USD")
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda book: {
            "cash": 500.0,
            "positions": {"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
        },
    )

    def _boom(ticker):
        raise RuntimeError("quote feed down")

    monkeypatch.setattr(paper_account, "_current_price", _boom)
    with pytest.raises(
        ds.DecisionBoundaryFreeze, match=r"^unpriceable_held_position:BIIB$"
    ):
        ds._latest_holdings("autonomous")


# ---------------------------------------------------------------------------
# 2. regional books — the substitution also bypasses FX
# ---------------------------------------------------------------------------


def test_regional_cny_unpriceable_holding_does_not_bypass_fx(monkeypatch):
    """``avg_cost`` is stored USD-basis (portfolio/fx.py: "everything marked in USD"), while
    the book NAV here is CNY-basis. Substituting cost therefore also smuggles a raw USD
    number into a CNY NAV — a second, compounding fabrication."""
    _seed_account(
        monkeypatch,
        positions={"600519.SS": {"shares": 1.0, "avg_cost": 600.0}},
        cash=700.0,
        price={"600519.SS": None},
        currency="CNY",
        fx_rate=7.0,
    )
    with pytest.raises(
        ds.DecisionBoundaryFreeze, match=r"^unpriceable_held_position:600519\.SS$"
    ):
        ds._latest_holdings("china")


def test_regional_hkd_unpriceable_holding_freezes(monkeypatch):
    _seed_account(
        monkeypatch,
        positions={"0700.HK": {"shares": 100.0, "avg_cost": 40.0}},
        cash=1_000.0,
        price={"0700.HK": None},
        currency="HKD",
        fx_rate=7.8,
    )
    with pytest.raises(
        ds.DecisionBoundaryFreeze, match=r"^unpriceable_held_position:0700\.HK$"
    ):
        ds._latest_holdings("hk")


def test_fx_is_never_applied_to_a_cost_basis(monkeypatch):
    """Belt and braces: the repair must not 'fix' the bypass by FX-converting cost instead.
    Cost must never reach the converter at all."""
    from portfolio import fx

    seen: list[float] = []
    _seed_account(
        monkeypatch,
        positions={"600519.SS": {"shares": 1.0, "avg_cost": 600.0}},
        cash=700.0,
        price={"600519.SS": None},
        currency="CNY",
    )
    monkeypatch.setattr(
        fx, "usd_to", lambda px, cur: seen.append(px) or (px * 7.0)
    )
    with pytest.raises(ds.DecisionBoundaryFreeze):
        ds._latest_holdings("china")
    assert 600.0 not in seen, "cost basis must never be routed through FX conversion"


# ---------------------------------------------------------------------------
# 3. valid marks keep normalizing — including the regional conversion
# ---------------------------------------------------------------------------


def test_valid_us_mark_still_normalizes(tmp_path, monkeypatch):
    from portfolio import registry

    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    _seed_account(
        monkeypatch,
        positions={"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
        cash=500.0,
        price={"BIIB": 100.0},
    )
    rows = ds._latest_holdings("autonomous")
    assert rows["BIIB"]["weight"] == pytest.approx(0.5)
    assert rows["BIIB"]["holding_mark_source"] == "live_quote"


def test_valid_regional_mark_still_converts_usd_to_cny(tmp_path, monkeypatch):
    """The existing regional conversion contract is preserved exactly: applied once, to a
    real mark only."""
    from portfolio import registry

    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    _seed_account(
        monkeypatch,
        positions={"600519.SS": {"shares": 1.0, "avg_cost": 600.0}},
        cash=700.0,
        price={"600519.SS": 100.0},
        currency="CNY",
        fx_rate=7.0,
    )
    rows = ds._latest_holdings("china")
    assert rows["600519.SS"]["weight"] == pytest.approx(0.5)
    assert rows["600519.SS"]["holding_mark_source"] == "live_quote"


def test_valid_regional_mark_still_converts_usd_to_hkd(tmp_path, monkeypatch):
    from portfolio import registry

    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    _seed_account(
        monkeypatch,
        positions={"0700.HK": {"shares": 10.0, "avg_cost": 40.0}},
        cash=780.0,
        price={"0700.HK": 10.0},
        currency="HKD",
        fx_rate=7.8,
    )
    rows = ds._latest_holdings("hk")
    assert rows["0700.HK"]["weight"] == pytest.approx(0.5)
    assert rows["0700.HK"]["holding_mark_source"] == "live_quote"


def test_no_holding_can_report_avg_cost_fallback_provenance(tmp_path, monkeypatch):
    """The fabricated provenance label is structurally unreachable, so the audit's
    ``quote_fallback_holdings`` invariant is now proven rather than merely reported."""
    from portfolio import registry

    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    _seed_account(
        monkeypatch,
        positions={"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
        cash=500.0,
        price={"BIIB": 100.0},
    )
    rows = ds._latest_holdings("autonomous")
    assert all(
        row.get("holding_mark_source") != "account_avg_cost_fallback"
        for row in rows.values()
    )


def test_stale_fallback_provenance_in_a_legacy_file_is_not_re_propagated(
    tmp_path, monkeypatch
):
    """A prior submission written before this repair may carry the fabricated label; the
    boundary must overwrite it from the freshly proven mark, never inherit it."""
    from portfolio import registry

    (tmp_path / "latest.json").write_text(
        json.dumps(
            {
                "positions": [
                    {
                        "ticker": "BIIB",
                        "rationale": "published thesis",
                        "conviction": "high",
                        "holding_mark_source": "account_avg_cost_fallback",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    _seed_account(
        monkeypatch,
        positions={"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
        cash=500.0,
        price={"BIIB": 100.0},
    )
    rows = ds._latest_holdings("autonomous")
    assert rows["BIIB"]["holding_mark_source"] == "live_quote"


# ---------------------------------------------------------------------------
# 4. caller-level proof — the book is preserved, nothing is mutated
# ---------------------------------------------------------------------------


def test_normalize_freezes_before_constructing_any_numeric_target(monkeypatch):
    """The refusal lands before deterministic sizing, so no target book is ever built."""
    _seed_account(
        monkeypatch,
        positions={"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
        cash=500.0,
        price={"BIIB": None},
    )
    sized: list[object] = []
    monkeypatch.setattr(
        ds,
        "_allocate_deterministically",
        lambda *a, **k: sized.append(a) or {},
    )
    with pytest.raises(ds.DecisionBoundaryFreeze, match="unpriceable_held_position"):
        ds.normalize(
            "autonomous",
            _args(),
            stock_only=True,
            early_exit_hysteresis=True,
            deterministic_sizing=True,
        )
    assert sized == [], "sizing must never run on incomplete current valuation evidence"


def test_autonomous_caller_preserves_prior_book_and_mutates_nothing(
    tmp_path, monkeypatch
):
    from brain import autonomous_mcp
    from portfolio import registry

    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    prior = tmp_path / "_pending_decision.json"
    prior_payload = {"schema": "mastermind.target_book.v2", "holdings": [{"ticker": "BIIB"}]}
    prior.write_text(json.dumps(prior_payload), encoding="utf-8")
    before = prior.read_bytes()

    sentinel = _MutationSentinel(monkeypatch)
    _seed_account(
        monkeypatch,
        positions={"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
        cash=500.0,
        price={"BIIB": None},
    )

    result = asyncio.run(autonomous_mcp.submit_book.handler(_args()))
    text = result["content"][0]["text"]

    assert "SUBMISSION REJECTED" in text
    assert "prior paper book preserved unchanged" in text
    assert "unpriceable_held_position:BIIB" in text
    assert prior.read_bytes() == before, "prior target book must survive byte-identical"
    assert sentinel.calls == [], f"refusal mutated the account: {sentinel.calls}"


def test_china_caller_preserves_prior_book_and_mutates_nothing(tmp_path, monkeypatch):
    from brain import china_mcp
    from portfolio import registry

    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    prior = tmp_path / "_pending_decision.json"
    prior.write_text(json.dumps({"holdings": [{"ticker": "600519.SS"}]}), encoding="utf-8")
    before = prior.read_bytes()

    sentinel = _MutationSentinel(monkeypatch)
    _seed_account(
        monkeypatch,
        positions={"600519.SS": {"shares": 1.0, "avg_cost": 600.0}},
        cash=700.0,
        price={"600519.SS": None},
        currency="CNY",
        fx_rate=7.0,
    )

    result = asyncio.run(china_mcp.submit_book.handler(_args()))
    text = result["content"][0]["text"]

    assert "SUBMISSION REJECTED" in text
    assert "unpriceable_held_position:600519.SS" in text
    assert prior.read_bytes() == before
    assert sentinel.calls == []


def test_refusal_never_emits_an_exit_or_liquidation(tmp_path, monkeypatch):
    """The unpriceable line must not be sold, zero-weighted, or converted to cash: the
    refusal carries no book at all."""
    from brain import autonomous_mcp
    from portfolio import registry

    monkeypatch.setattr(registry, "data_dir", lambda book: tmp_path)
    _MutationSentinel(monkeypatch)
    _seed_account(
        monkeypatch,
        positions={"BIIB": {"shares": 5.0, "avg_cost": 100.0}},
        cash=500.0,
        price={"BIIB": None},
    )
    result = asyncio.run(autonomous_mcp.submit_book.handler(_args()))
    text = result["content"][0]["text"]

    assert autonomous_mcp.BOOK_MARKER not in text, "no target book may be published"
    assert not (tmp_path / "_pending_decision.json").exists()
    for word in ("exit", "sell", "liquidat", "trim"):
        assert word not in text.lower(), f"refusal leaked a {word} instruction"
