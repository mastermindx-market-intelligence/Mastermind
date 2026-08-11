"""Queued targets retain the exact accepted structured PM rationale through settlement."""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.mark.parametrize(
    ("portfolio_id", "module_name", "mcp_name", "ticker", "benchmark"),
    [
        ("autonomous", "bot.autonomous", "brain.autonomous_mcp", "AAPL", "SPY"),
        ("china", "bot.china", "brain.china_mcp", "600519.SS", "000300.SS"),
        ("hk", "bot.hk", "brain.hk_mcp", "0700.HK", "^HSI"),
    ],
)
def test_failed_refinement_cannot_erase_settlement_rationale(
    tmp_path,
    monkeypatch,
    portfolio_id,
    module_name,
    mcp_name,
    ticker,
    benchmark,
):
    from bot import settle
    from portfolio import fx, paper_account, registry

    module = importlib.import_module(module_name)
    mcp = importlib.import_module(mcp_name)
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(module, "_warm_live", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(fx, "usd_to", lambda value, currency: value)
    monkeypatch.setattr(paper_account, "_current_price", lambda symbol: 100.0)
    monkeypatch.setattr(
        settle,
        "_price_and_sources",
        lambda pid, symbols, _open_price_fn=None: (
            {symbol: 100.0 for symbol in symbols},
            {symbol: "test_open" for symbol in symbols},
        ),
    )

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 1_000_000.0,
            "positions": {},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        portfolio_id,
    )
    accepted = {
        "schema": "mastermind.target_book.v2",
        "holdings": [
            {
                "ticker": ticker,
                "weight": 0.20,
                "action": "add",
                "conviction": "high",
                "rationale": f"accepted rationale for {ticker}",
                "why_now": "The verified trend and sector evidence are aligned.",
            }
        ],
        "exit_decisions": [],
        "summary": f"accepted summary for {portfolio_id}",
        "decision_memo": {"selection_funnel": [ticker]},
    }

    queued = settle.execute_or_queue(
        portfolio_id,
        {ticker: 0.20},
        {ticker: 100.0, benchmark: 100.0},
        "2026-08-08",
        market_open=False,
        decision_snapshot=accepted,
    )
    assert queued["queued"] is True
    persisted = paper_account.load_pending_target(portfolio_id)
    assert persisted is not None
    assert persisted["decision_snapshot"]["submission"] == accepted

    # A failed overnight/manual turn clears the mutable MCP scratch file before producing no new
    # submission.  The executable queue and its accepted rationale must remain independently whole.
    if portfolio_id == "autonomous":
        mcp.clear_submission(portfolio_id)
    else:
        mcp.clear_submission()

    result = settle.settle_open(portfolio_id, "2026-08-09")

    assert result["ok"] is True
    assert result["republish"]["ok"] is True
    assert paper_account.pending_target_file_exists(portfolio_id) is False
    account = paper_account._load_account(portfolio_id)
    assert account["positions"][ticker]["shares"] > 0
    latest = json.loads((registry.data_dir(portfolio_id) / "latest.json").read_text())
    assert latest["target_status"] == "executed"
    assert latest["decision_effective"] is True
    assert latest["summary"] == accepted["summary"]
    row = next(position for position in latest["positions"] if position["ticker"] == ticker)
    assert row["rationale"] == accepted["holdings"][0]["rationale"]


def test_pending_decision_hash_mismatch_is_quarantined(tmp_path, monkeypatch):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    paper_account.save_pending_target(
        {"AAPL": 0.20},
        "2026-08-08",
        portfolio_id="autonomous",
        decision_snapshot={
            "holdings": [{"ticker": "AAPL", "weight": 0.20, "rationale": "bound"}],
            "summary": "bound decision",
        },
    )
    path = registry.data_dir("autonomous") / "pending_target.json"
    payload = json.loads(path.read_text())
    payload["target"] = {"AAPL": 0.30}
    path.write_text(json.dumps(payload))

    result = paper_account.preflight_pending_target("autonomous")

    assert result["ok"] is False
    assert result["quarantine"]["reason"] == "decision_snapshot_target_mismatch"
    assert not path.exists()


@pytest.mark.parametrize(
    ("portfolio_id", "module_name", "ticker", "benchmark"),
    [
        ("autonomous", "bot.autonomous", "AAPL", "SPY"),
        ("china", "bot.china", "600519.SS", "000300.SS"),
        ("hk", "bot.hk", "0700.HK", "^HSI"),
    ],
)
def test_restart_recovery_outbox_finishes_mark_and_publish_once(
    tmp_path,
    monkeypatch,
    portfolio_id,
    module_name,
    ticker,
    benchmark,
):
    """An arbitrary account read may replay the WAL, but cannot consume its publish obligation."""
    from bot import settle
    from portfolio import fx, paper_account, registry

    module = importlib.import_module(module_name)
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(module, "_warm_live", lambda *args, **kwargs: None, raising=False)
    monkeypatch.setattr(fx, "usd_to", lambda value, currency: value)
    monkeypatch.setattr(paper_account, "_current_price", lambda symbol: 100.0)
    monkeypatch.setattr(
        settle,
        "_price_and_sources",
        lambda pid, symbols, _open_price_fn=None: (
            {symbol: 100.0 for symbol in symbols},
            {symbol: "test_open" for symbol in symbols},
        ),
    )
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 1_000_000.0,
            "positions": {},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        portfolio_id,
    )
    accepted = {
        "schema": "mastermind.target_book.v2",
        "holdings": [{
            "ticker": ticker,
            "weight": 0.20,
            "action": "add",
            "rationale": f"restart-safe rationale for {ticker}",
        }],
        "summary": f"restart-safe summary for {portfolio_id}",
    }
    paper_account.save_pending_target(
        {ticker: 0.20},
        "2026-08-08",
        portfolio_id=portfolio_id,
        decision_snapshot=accepted,
    )

    real_append = paper_account._append_jsonl
    failed = {"done": False}

    def fail_first_fill(path, row):
        if path.name == "fills.jsonl" and not failed["done"]:
            failed["done"] = True
            raise OSError("simulated-process-death")
        return real_append(path, row)

    monkeypatch.setattr(paper_account, "_append_jsonl", fail_first_fill)
    with pytest.raises(OSError, match="simulated-process-death"):
        paper_account.settle_target(
            {ticker: 100.0, benchmark: 100.0},
            "2026-08-09",
            portfolio_id=portfolio_id,
        )
    assert paper_account._transaction_path(portfolio_id).exists()
    monkeypatch.setattr(paper_account, "_append_jsonl", real_append)

    # Simulate a fresh process whose unrelated account read reaches recovery before the scheduled
    # settlement entrypoint. Numeric commit and queue clear happen here, but the outbox survives.
    recovered_state = paper_account._load_account(portfolio_id)
    assert ticker in recovered_state["positions"]
    assert not paper_account._transaction_path(portfolio_id).exists()
    assert not paper_account.pending_target_file_exists(portfolio_id)
    assert len(paper_account.pending_settlement_receipts(portfolio_id)) == 1

    result = settle.settle_open(portfolio_id, "2026-08-09")

    assert result["ok"] is True
    assert result["settlement_recovered"] is True
    assert result["receipt_acknowledged"] is True
    assert not paper_account.pending_settlement_receipts(portfolio_id)
    fills_path = registry.data_dir(portfolio_id) / "fills.jsonl"
    fills = [json.loads(line) for line in fills_path.read_text().splitlines() if line]
    assert len(fills) == 1
    assert len({row["fill_id"] for row in fills}) == 1
    latest = json.loads((registry.data_dir(portfolio_id) / "latest.json").read_text())
    assert latest["summary"] == accepted["summary"]
    assert latest["target_status"] == "executed"
    assert latest["positions"][0]["rationale"] == accepted["holdings"][0]["rationale"]
    nav_rows = (registry.data_dir(portfolio_id) / "nav_history.jsonl").read_text().splitlines()
    assert len(nav_rows) == 1

    again = settle.settle_open(portfolio_id, "2026-08-09")
    assert again["skipped"] == "nothing_queued"
    assert len([line for line in fills_path.read_text().splitlines() if line]) == 1
