"""Regression coverage for legacy off-venue holdings in the CN/HK books."""
from __future__ import annotations

import importlib
import json

import pytest


class _Packet:
    ok = True
    packet_id = "test-packet"

    @staticmethod
    def to_meta():
        return {}


def _patch_regional_run(
    monkeypatch,
    module,
    mcp,
    submission_box,
    *,
    market_open: bool,
    stub_publish: bool,
) -> None:
    """Patch non-execution side effects while retaining real paper-account settlement."""
    from bot import settle
    from brain import cost_guard, portfolio_learning
    from bridge import build_portfolio
    from control_plane import packet_gate
    from data_layer import feed_health
    from portfolio import mandate_packet

    monkeypatch.setattr(mcp, "clear_submission", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        mcp, "read_submission", lambda *args, **kwargs: submission_box["payload"]
    )
    monkeypatch.setattr(
        module, "_run_brain", lambda *args, **kwargs: {"ok": True, "model": "test"}
    )
    monkeypatch.setattr(module, "_warm_live", lambda *args, **kwargs: None)
    monkeypatch.setattr(feed_health, "status", lambda *args, **kwargs: {"status": "ok"})
    monkeypatch.setattr(cost_guard, "over_budget", lambda *args, **kwargs: False)
    monkeypatch.setattr(cost_guard, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(settle, "is_open", lambda pid: market_open)
    monkeypatch.setattr(packet_gate, "process", lambda *args, **kwargs: _Packet())
    if stub_publish:
        monkeypatch.setattr(build_portfolio, "write", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "_append_decision_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_translate_report", lambda *args, **kwargs: False)
    monkeypatch.setattr(mandate_packet, "build", lambda *args, **kwargs: {})
    monkeypatch.setattr(mandate_packet, "write_packet", lambda *args, **kwargs: None)
    monkeypatch.setattr(mandate_packet, "emit_run_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        portfolio_learning, "refresh_post_sell", lambda *args, **kwargs: {"summary": {}}
    )
    monkeypatch.setattr(
        portfolio_learning, "derive_lessons", lambda *args, **kwargs: {"lessons": []}
    )


@pytest.mark.parametrize(
    ("module_name", "mcp_name", "runner_name", "portfolio_id", "legacy_ticker",
     "new_offvenue_ticker", "benchmark"),
    [
        ("bot.china", "brain.china_mcp", "run_china", "china", "0700.HK",
         "9988.HK", "000300.SS"),
        ("bot.hk", "brain.hk_mcp", "run_hk", "hk", "600519.SS",
         "300750.SZ", "^HSI"),
    ],
)
def test_legacy_offvenue_omission_carries_until_explicit_exit(
    tmp_path,
    monkeypatch,
    module_name,
    mcp_name,
    runner_name,
    portfolio_id,
    legacy_ticker,
    new_offvenue_ticker,
    benchmark,
):
    """Omission preserves legacy inventory; only a reviewed exit may sell it."""
    module = importlib.import_module(module_name)
    mcp = importlib.import_module(mcp_name)
    from bot import settle
    from brain import china_intake, cost_guard, decision_submission, portfolio_learning
    from bridge import build_portfolio
    from control_plane import packet_gate
    from data_layer import feed_health
    from portfolio import fx, mandate_packet, paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000.0,
            "cash": 900.0,
            "positions": {legacy_ticker: {"shares": 1.0, "avg_cost": 100.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        portfolio_id,
    )

    prices = {legacy_ticker: 100.0, new_offvenue_ticker: 100.0, benchmark: 100.0}
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: prices.get(ticker))
    monkeypatch.setattr(fx, "usd_to", lambda value, currency: value)

    omission_payload, omission_audit = decision_submission.normalize(
        portfolio_id,
        {
            "holdings": [{
                "ticker": new_offvenue_ticker,
                "action": "add",
                "rationale": "This deliberately invalid add proves the trusted venue gate.",
            }],
            "summary": "Carry the legacy line pending an explicit reviewed exit.",
        },
        venue_of=china_intake._venue,
        allowed_venues=set(module.ALLOWED_VENUES),
        deterministic_sizing=True,
    )
    assert omission_audit["rejected"] == [
        {"ticker": new_offvenue_ticker, "reason": "off_venue"}
    ]
    assert [row["ticker"] for row in omission_payload["holdings"]] == [legacy_ticker]
    assert omission_payload["holdings"][0]["carried_forward"] is True
    assert omission_payload["holdings"][0]["weight_source"] == "omission_carry.v1"

    current_submission = {"payload": omission_payload}
    monkeypatch.setattr(mcp, "clear_submission", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp, "read_submission", lambda *args, **kwargs: current_submission["payload"])
    monkeypatch.setattr(module, "_run_brain", lambda *args, **kwargs: {"ok": True, "model": "test"})
    monkeypatch.setattr(module, "_warm_live", lambda *args, **kwargs: None)
    monkeypatch.setattr(feed_health, "status", lambda *args, **kwargs: {"status": "ok"})
    monkeypatch.setattr(cost_guard, "over_budget", lambda *args, **kwargs: False)
    monkeypatch.setattr(cost_guard, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)

    monkeypatch.setattr(packet_gate, "process", lambda *args, **kwargs: _Packet())
    monkeypatch.setattr(build_portfolio, "write", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "_append_decision_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_translate_report", lambda *args, **kwargs: False)
    monkeypatch.setattr(mandate_packet, "build", lambda *args, **kwargs: {})
    monkeypatch.setattr(mandate_packet, "write_packet", lambda *args, **kwargs: None)
    monkeypatch.setattr(mandate_packet, "emit_run_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        portfolio_learning, "refresh_post_sell", lambda *args, **kwargs: {"summary": {}}
    )
    monkeypatch.setattr(
        portfolio_learning, "derive_lessons", lambda *args, **kwargs: {"lessons": []}
    )

    runner = getattr(module, runner_name)
    omitted = runner("2026-08-09", armed=True, force=True)

    assert omitted["decided"] is True
    assert omitted["executed"] == []
    assert omitted["rejected_offvenue"] == [new_offvenue_ticker]
    assert paper_account._load_account(portfolio_id)["positions"][legacy_ticker]["shares"] == 1.0
    fills_path = registry.data_dir(portfolio_id) / "fills.jsonl"
    assert not fills_path.exists() or fills_path.read_text(encoding="utf-8").strip() == ""

    exit_payload, exit_audit = decision_submission.normalize(
        portfolio_id,
        {
            "holdings": [],
            "summary": "Exit the legacy line after an explicit reviewed falsifier.",
            "exit_decisions": [{
                "ticker": legacy_ticker,
                "action": "exit",
                "reason": "The legacy exception no longer belongs in this venue-specific book.",
                "reason_code": "legacy_instrument_migration",
                "evidence": ["operator-reviewed venue migration"],
                "why_now": "A trusted quote is available for an orderly paper exit.",
            }],
        },
        venue_of=china_intake._venue,
        allowed_venues=set(module.ALLOWED_VENUES),
        deterministic_sizing=True,
    )
    assert exit_audit["carried"] == []
    assert exit_payload["holdings"] == []
    assert exit_payload["exit_decisions"][0]["ticker"] == legacy_ticker
    current_submission["payload"] = exit_payload

    exited = runner("2026-08-10", armed=True, force=True)

    assert exited["decided"] is True
    assert exited["executed"] == [{
        "ticker": legacy_ticker,
        "side": "sell",
        "shares": 1.0,
        "price": 100.0,
        "value": 100.0,
    }]
    assert paper_account._load_account(portfolio_id)["positions"] == {}
    fills = [
        json.loads(line)
        for line in fills_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(fills) == 1
    assert fills[0]["ticker"] == legacy_ticker
    assert fills[0]["side"] == "sell"


@pytest.mark.parametrize(
    ("module_name", "mcp_name", "runner_name", "portfolio_id", "held_ticker",
     "new_ticker", "benchmark"),
    [
        ("bot.china", "brain.china_mcp", "run_china", "china", "600519.SS",
         "300750.SZ", "000300.SS"),
        ("bot.hk", "brain.hk_mcp", "run_hk", "hk", "0700.HK",
         "9988.HK", "^HSI"),
    ],
)
def test_regional_closed_queue_drops_unpriceable_add_but_keeps_missing_holding(
    tmp_path,
    monkeypatch,
    module_name,
    mcp_name,
    runner_name,
    portfolio_id,
    held_ticker,
    new_ticker,
    benchmark,
):
    """A recovered quote cannot activate a new name skipped by the deciding run."""
    module = importlib.import_module(module_name)
    mcp = importlib.import_module(mcp_name)
    from bot import settle
    from brain import china_intake, decision_submission
    from portfolio import fx, paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000.0,
            "cash": 900.0,
            "positions": {held_ticker: {"shares": 1.0, "avg_cost": 100.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        portfolio_id,
    )
    monkeypatch.setattr(fx, "usd_to", lambda value, currency: value)
    monkeypatch.setattr(
        paper_account,
        "_current_price",
        lambda ticker: 100.0 if ticker in {held_ticker, benchmark} else None,
    )
    payload, audit = decision_submission.normalize(
        portfolio_id,
        {
            "holdings": [{
                "ticker": new_ticker,
                "action": "add",
                "rationale": "A valid venue-local candidate whose execution quote is about to miss.",
                "conviction": "high",
            }],
            "summary": "Retain existing inventory and skip any addition without a current quote.",
        },
        venue_of=china_intake._venue,
        allowed_venues=set(module.ALLOWED_VENUES),
        deterministic_sizing=True,
    )
    assert audit["rejected"] == []
    assert {row["ticker"] for row in payload["holdings"]} == {held_ticker, new_ticker}

    # The runner's second quote pass misses both rows. Existing inventory must remain in the
    # target; the brand-new addition must not become a dormant queued buy.
    monkeypatch.setattr(
        paper_account,
        "_current_price",
        lambda ticker: 100.0 if ticker == benchmark else None,
    )
    submission_box = {"payload": payload}
    _patch_regional_run(
        monkeypatch,
        module,
        mcp,
        submission_box,
        market_open=False,
        stub_publish=True,
    )

    queued = getattr(module, runner_name)("2026-08-09", armed=True, force=True)
    pending = paper_account.load_pending_target(portfolio_id)

    assert queued["queued_for_open"] is True
    assert queued["skipped_unpriceable"] == [new_ticker]
    assert queued["carried_unpriceable_holdings"] == [held_ticker]
    assert pending is not None
    assert held_ticker in pending["target"]
    assert new_ticker not in pending["target"]

    # Both quotes recover later, but settlement may use only the snapshotted executable target.
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: 100.0)
    monkeypatch.setattr(settle, "_republish", lambda *args, **kwargs: None)
    settled = settle.settle_open(portfolio_id, "2026-08-10")

    positions = paper_account._load_account(portfolio_id)["positions"]
    assert settled["ok"] is True
    assert settled["settled_to"] == [held_ticker]
    assert positions[held_ticker]["shares"] == 1.0
    assert new_ticker not in positions
    assert paper_account.load_pending_target(portfolio_id) is None


@pytest.mark.parametrize(
    ("module_name", "mcp_name", "runner_name", "portfolio_id", "held_ticker",
     "benchmark"),
    [
        ("bot.china", "brain.china_mcp", "run_china", "china", "600519.SS",
         "000300.SS"),
        ("bot.hk", "brain.hk_mcp", "run_hk", "hk", "0700.HK", "^HSI"),
    ],
)
def test_regional_all_cash_settle_republishes_empty_executed_book(
    tmp_path,
    monkeypatch,
    module_name,
    mcp_name,
    runner_name,
    portfolio_id,
    held_ticker,
    benchmark,
):
    """An explicit empty target must clear both the account and published contract."""
    module = importlib.import_module(module_name)
    mcp = importlib.import_module(mcp_name)
    from bot import settle
    from brain import china_intake, decision_submission
    from portfolio import fx, paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000.0,
            "cash": 900.0,
            "positions": {held_ticker: {"shares": 1.0, "avg_cost": 100.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        portfolio_id,
    )
    monkeypatch.setattr(fx, "usd_to", lambda value, currency: value)
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: 100.0)
    summary = "Exit the final holding and hold an explicitly reviewed all-cash target."
    payload, audit = decision_submission.normalize(
        portfolio_id,
        {
            "holdings": [],
            "summary": summary,
            "exit_decisions": [{
                "ticker": held_ticker,
                "action": "exit",
                "reason": "The position's reviewed falsifier fired.",
                "reason_code": "hard_falsifier",
                "evidence": ["trusted regression evidence"],
                "why_now": "A current trusted quote supports the paper exit.",
            }],
        },
        venue_of=china_intake._venue,
        allowed_venues=set(module.ALLOWED_VENUES),
        deterministic_sizing=True,
    )
    assert audit["carried"] == []
    assert payload["holdings"] == []
    submission_box = {"payload": payload}
    _patch_regional_run(
        monkeypatch,
        module,
        mcp,
        submission_box,
        market_open=False,
        stub_publish=False,
    )

    queued = getattr(module, runner_name)("2026-08-09", armed=True, force=True)
    assert queued["queued_for_open"] is True
    assert paper_account.load_pending_target(portfolio_id)["target"] == {}

    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    settled = settle.settle_open(portfolio_id, "2026-08-10")

    assert settled["ok"] is True
    assert paper_account._load_account(portfolio_id)["positions"] == {}
    latest = json.loads(
        (registry.data_dir(portfolio_id) / "latest.json").read_text(encoding="utf-8")
    )
    assert latest["positions"] == []
    assert latest["target_status"] == "executed"
    assert latest["decision_effective"] is True
    assert latest["summary"] == summary
