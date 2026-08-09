"""Regression coverage for quote gaps at the US Brain paper-execution boundary."""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def isolated_book(tmp_path, monkeypatch):
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    return tmp_path


def _seed_aapl(paper_account) -> None:
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 999_000.0,
            "positions": {"AAPL": {"shares": 10.0, "avg_cost": 100.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )


def test_autonomous_second_quote_miss_carries_held_row_but_skips_new_add(
    isolated_book, monkeypatch
):
    """A transient quote miss after normalization must not erase a carried holding from the queue."""
    from bot import autonomous, settle
    from brain import autonomous_mcp
    from portfolio import firm_exposure, paper_account, safety

    _seed_aapl(paper_account)
    quotes = {"MSFT": 400.0, "SPY": 500.0}  # AAPL and new GLD both miss this second pass
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: quotes.get(ticker))
    monkeypatch.setattr(settle, "is_open", lambda pid: False)
    monkeypatch.setattr(
        safety,
        "compute_safety",
        lambda *args, **kwargs: {"status": "ok"},
    )
    monkeypatch.setattr(safety, "gross_overlay", lambda report: {"gross_mult": 1.0})
    monkeypatch.setattr(safety, "persist", lambda *args, **kwargs: None)
    monkeypatch.setattr(firm_exposure, "caps_enabled", lambda: False)

    def fake_brain(asof, inaugural):
        autonomous_mcp.submission_path().parent.mkdir(parents=True, exist_ok=True)
        autonomous_mcp.submission_path().write_text(
            json.dumps(
                {
                    "schema": "mastermind.target_book.v2",
                    "holdings": [
                        {"ticker": "AAPL", "weight": 0.10, "rationale": "continue holding"},
                        {"ticker": "MSFT", "weight": 0.10, "rationale": "new priced leader"},
                        {"ticker": "GLD", "weight": 0.05, "rationale": "unpriceable new idea"},
                    ],
                    "summary": "quote-gap regression",
                    "gross": 0.25,
                }
            )
        )
        return {"ok": True, "text": "done", "cost_usd": 0.0, "model": "test"}

    monkeypatch.setattr(autonomous, "_run_brain", fake_brain)

    result = autonomous.run_autonomous(asof="2026-08-09", armed=True)
    pending = paper_account.load_pending_target("autonomous")

    assert result["queued_for_open"] is True
    assert result["carried_unpriceable_holdings"] == ["AAPL"]
    assert result["skipped_unpriceable"] == ["GLD"]
    assert pending is not None
    assert pending["target"] == {"AAPL": 0.1, "MSFT": 0.1}
    assert paper_account._load_account("autonomous")["positions"]["AAPL"]["shares"] == 10.0


def test_rebalance_never_books_dropped_holding_at_average_cost(isolated_book):
    """The lowest boundary carries an omitted holding when no execution price exists."""
    from portfolio import paper_account, registry

    _seed_aapl(paper_account)
    paper_account.rebalance({}, {"SPY": 500.0}, "2026-08-09", portfolio_id="autonomous")

    state = paper_account._load_account("autonomous")
    assert state["positions"]["AAPL"] == {"shares": 10.0, "avg_cost": 100.0}
    fills_path = registry.data_dir("autonomous") / "fills.jsonl"
    assert not fills_path.exists() or fills_path.read_text().strip() == ""


def test_rebalance_dropped_holding_still_exits_at_valid_price(isolated_book):
    """The quote guard must not weaken a genuine exit once a trusted price is present."""
    from portfolio import paper_account, registry

    _seed_aapl(paper_account)
    paper_account.rebalance({}, {"AAPL": 120.0, "SPY": 500.0}, "2026-08-09",
                            portfolio_id="autonomous")

    state = paper_account._load_account("autonomous")
    assert "AAPL" not in state["positions"]
    fills = [
        json.loads(line)
        for line in (registry.data_dir("autonomous") / "fills.jsonl").read_text().splitlines()
    ]
    assert [{k: row[k] for k in ("date", "ticker", "side", "shares", "price", "value")}
            for row in fills] == [{
        "date": "2026-08-09",
        "ticker": "AAPL",
        "side": "sell",
        "shares": 10.0,
        "price": 120.0,
        "value": 1200.0,
    }]
    assert len(fills[0]["fill_id"]) == 64
    assert len(fills[0]["transaction_id"]) == 64


def test_settle_open_unpriceable_exit_writes_nothing_and_retains_pending(
    isolated_book, monkeypatch
):
    """An open-settle retry is atomic: no fill, no account save, and no queue clear."""
    from bot import settle
    from portfolio import paper_account, registry

    _seed_aapl(paper_account)
    paper_account.save_pending_target({}, "2026-08-08", portfolio_id="autonomous")
    account_path = registry.data_dir("autonomous") / "account.json"
    account_before = account_path.read_bytes()
    pending_before = paper_account.load_pending_target("autonomous")
    save_calls: list[dict] = []

    def forbidden_save(*args, **kwargs):
        save_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("account write crossed the exit-price guard")

    monkeypatch.setattr(paper_account, "_save_account", forbidden_save)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(settle, "_republish", lambda *args, **kwargs: None)

    def missing_aapl(ticker):
        return (500.0, "polygon_open") if ticker == "SPY" else (None, "last_price")

    result = settle.settle_open("autonomous", "2026-08-09", _open_price_fn=missing_aapl)

    assert result["ok"] is False
    assert result["skipped"] == "unpriceable_exit_prices"
    assert result["unpriceable_exits"] == ["AAPL"]
    assert result["pending_retained"] is True
    assert result["executed"] == []
    assert save_calls == []
    assert account_path.read_bytes() == account_before
    assert paper_account.load_pending_target("autonomous") == pending_before


def test_direct_market_open_replaces_stale_pending_exit_with_latest_keep(
    isolated_book, monkeypatch
):
    """A newer current KEEP target supersedes an older queued EXIT during a quote outage."""
    from bot import settle
    from portfolio import paper_account, registry

    _seed_aapl(paper_account)
    paper_account.save_pending_target({}, "2026-08-08", portfolio_id="autonomous")
    account_path = registry.data_dir("autonomous") / "account.json"
    account_before = account_path.read_bytes()
    save_calls: list[dict] = []
    real_save_account = paper_account._save_account

    def forbidden_save(*args, **kwargs):
        save_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("account write crossed the exit-price guard")

    monkeypatch.setattr(paper_account, "_save_account", forbidden_save)
    result = settle.execute_or_queue(
        "autonomous",
        {"AAPL": 0.10},  # current decision keeps it; the older pending target exits it
        {"SPY": 500.0},
        "2026-08-09",
        market_open=True,
    )

    assert result["skipped"] == "unpriceable_target_prices"
    assert result["unpriceable_targets"] == ["AAPL"]
    assert result["unpriceable_exits"] == []
    assert result["pending_retained"] is True
    assert result["executed"] == []
    assert save_calls == []
    assert account_path.read_bytes() == account_before
    pending = paper_account.load_pending_target("autonomous")
    assert pending is not None
    assert pending["target"] == {"AAPL": 0.10}
    assert pending["asof"] == "2026-08-09"

    # When a price later arrives, settlement follows the latest keep rather than selling AAPL.
    monkeypatch.setattr(paper_account, "_save_account", real_save_account)
    paper_account.settle_target(
        {"AAPL": 100.0, "SPY": 500.0}, "2026-08-10", portfolio_id="autonomous"
    )
    assert "AAPL" in paper_account._load_account("autonomous")["positions"]
    assert paper_account.pending_target_file_exists("autonomous") is False


def test_direct_market_open_replaces_stale_keep_with_latest_exit(isolated_book, monkeypatch):
    """The reverse conflict also honors the latest PM: a new EXIT replaces an old KEEP."""
    from bot import settle
    from portfolio import paper_account, registry

    _seed_aapl(paper_account)
    paper_account.save_pending_target(
        {"AAPL": 0.10}, "2026-08-08", portfolio_id="autonomous"
    )
    account_path = registry.data_dir("autonomous") / "account.json"
    account_before = account_path.read_bytes()

    result = settle.execute_or_queue(
        "autonomous", {}, {"SPY": 500.0}, "2026-08-09", market_open=True
    )

    assert result["skipped"] == "unpriceable_exit_prices"
    assert result["pending_retained"] is True
    assert account_path.read_bytes() == account_before
    pending = paper_account.load_pending_target("autonomous")
    assert pending is not None and pending["target"] == {}

    paper_account.settle_target(
        {"AAPL": 100.0, "SPY": 500.0}, "2026-08-10", portfolio_id="autonomous"
    )
    assert "AAPL" not in paper_account._load_account("autonomous")["positions"]


def test_failed_latest_replacement_quarantines_stale_pending_intent(
    isolated_book, monkeypatch
):
    """A failed queue replacement must not leave the superseded target executable."""
    from bot import settle
    from portfolio import paper_account, registry

    _seed_aapl(paper_account)
    paper_account.save_pending_target({}, "2026-08-08", portfolio_id="autonomous")
    account_path = registry.data_dir("autonomous") / "account.json"
    account_before = account_path.read_bytes()

    monkeypatch.setattr(
        paper_account,
        "save_pending_target",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("replace failed")),
    )
    result = settle.execute_or_queue(
        "autonomous",
        {"AAPL": 0.10},
        {"SPY": 500.0},
        "2026-08-09",
        market_open=True,
    )

    assert result["skipped"] == "unpriceable_target_prices"
    assert result["retry_target_queued"] is False
    assert "replace failed" in result["retry_queue_error"]
    assert result["stale_pending_quarantine"]["status"] == "quarantined"
    assert result["stale_pending_executable"] is False
    assert paper_account.pending_target_file_exists("autonomous") is False
    assert account_path.read_bytes() == account_before
    quarantined = list(
        registry.data_dir("autonomous").glob("pending_target.quarantine.*.json")
    )
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text())["target"] == {}


def test_priceable_open_latest_keep_supersedes_stale_exit_without_round_trip(
    isolated_book,
):
    """A current KEEP must not execute an older EXIT before applying the latest target."""
    from bot import settle
    from portfolio import paper_account, registry

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 900_000.0,
            "positions": {"AAPL": {"shares": 1_000.0, "avg_cost": 90.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )
    paper_account.save_pending_target({}, "2026-08-08", portfolio_id="autonomous")

    result = settle.execute_or_queue(
        "autonomous",
        {"AAPL": 0.10},
        {"AAPL": 100.0, "SPY": 500.0},
        "2026-08-09",
        market_open=True,
    )

    state = paper_account._load_account("autonomous")
    fills_path = registry.data_dir("autonomous") / "fills.jsonl"
    assert result["executed"] == []
    assert state["positions"]["AAPL"]["shares"] == 1_000.0
    assert state["positions"]["AAPL"]["avg_cost"] == 90.0
    assert not fills_path.exists() or fills_path.read_text().strip() == ""
    assert paper_account.pending_target_file_exists("autonomous") is False


def test_priceable_open_latest_exit_supersedes_stale_keep_with_one_sell(
    isolated_book,
):
    """A current EXIT replaces an older KEEP and produces one net fill, never a round trip."""
    from bot import settle
    from portfolio import paper_account, registry

    _seed_aapl(paper_account)
    paper_account.save_pending_target(
        {"AAPL": 0.001}, "2026-08-08", portfolio_id="autonomous"
    )

    result = settle.execute_or_queue(
        "autonomous",
        {},
        {"AAPL": 120.0, "SPY": 500.0},
        "2026-08-09",
        market_open=True,
    )

    fills = [
        json.loads(line)
        for line in (registry.data_dir("autonomous") / "fills.jsonl").read_text().splitlines()
    ]
    assert result["executed"] == [{
        "ticker": "AAPL",
        "side": "sell",
        "shares": 10.0,
        "price": 120.0,
        "value": 1200.0,
    }]
    assert [row["side"] for row in fills] == ["sell"]
    assert paper_account._load_account("autonomous")["positions"] == {}
    assert paper_account.pending_target_file_exists("autonomous") is False


def test_direct_market_open_queues_new_blocked_target_for_retry(isolated_book, monkeypatch):
    """Without an older queue, a blocked open-session target is persisted instead of forgotten."""
    from bot import settle
    from portfolio import paper_account, registry

    _seed_aapl(paper_account)
    account_path = registry.data_dir("autonomous") / "account.json"
    account_before = account_path.read_bytes()
    save_calls: list[dict] = []

    def forbidden_save(*args, **kwargs):
        save_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("account write crossed the exit-price guard")

    monkeypatch.setattr(paper_account, "_save_account", forbidden_save)
    result = settle.execute_or_queue(
        "autonomous",
        {},
        {"SPY": 500.0},
        "2026-08-09",
        market_open=True,
    )

    assert result["skipped"] == "unpriceable_exit_prices"
    assert result["queued"] is True
    assert result["retry_target_queued"] is True
    assert result["pending_retained"] is True
    assert save_calls == []
    assert account_path.read_bytes() == account_before
    pending = paper_account.load_pending_target("autonomous")
    assert pending is not None and pending["target"] == {}
    assert pending["schema_version"] == paper_account.PENDING_TARGET_SCHEMA_V2


def test_settle_open_executes_and_clears_pending_once_exit_is_priceable(
    isolated_book, monkeypatch
):
    """A later trusted open quote releases the same retained instruction normally."""
    from bot import settle
    from portfolio import paper_account

    _seed_aapl(paper_account)
    paper_account.save_pending_target({}, "2026-08-08", portfolio_id="autonomous")
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(settle, "_republish", lambda *args, **kwargs: None)

    def priced(ticker):
        return (120.0, "polygon_open") if ticker == "AAPL" else (500.0, "polygon_open")

    result = settle.settle_open("autonomous", "2026-08-09", _open_price_fn=priced)

    assert result["ok"] is True
    assert result["settled_to"] == []
    assert result["executed"] == [{
        "ticker": "AAPL",
        "side": "sell",
        "shares": 10.0,
        "price": 120.0,
        "value": 1200.0,
        "fill_price_source": "polygon_open",
    }]
    assert paper_account._load_account("autonomous")["positions"] == {}
    assert paper_account.load_pending_target("autonomous") is None


@pytest.mark.parametrize(
    ("portfolio_id", "ticker"),
    [
        ("autonomous", "AAPL"),
        ("china", "600519.SS"),
        ("hk", "0700.HK"),
    ],
)
@pytest.mark.parametrize("already_held", [False, True])
def test_complete_target_waits_for_every_positive_price_then_settles_once(
    isolated_book, portfolio_id, ticker, already_held
):
    """No region may partially consume and clear a target with an unpriceable ADD/HOLD."""
    from portfolio import paper_account, registry

    positions = (
        {ticker: {"shares": 10.0, "avg_cost": 100.0}}
        if already_held
        else {}
    )
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 999_000.0 if already_held else 1_000_000.0,
            "positions": positions,
            "spy_shares": None,
            "spy_inception_price": None,
        },
        portfolio_id,
    )
    target = {ticker: 0.20}
    paper_account.save_pending_target(target, "2026-08-08", portfolio_id=portfolio_id)
    account_path = registry.data_dir(portfolio_id) / "account.json"
    account_before = account_path.read_bytes()
    pending_before = paper_account.load_pending_target(portfolio_id)

    with pytest.raises(paper_account.UnpriceableExitPrices) as stopped:
        paper_account.settle_target({}, "2026-08-09", portfolio_id=portfolio_id)

    assert stopped.value.tickers == [ticker]
    assert stopped.value.positive_target_tickers == [ticker]
    assert stopped.value.exit_tickers == []
    assert account_path.read_bytes() == account_before
    assert paper_account.load_pending_target(portfolio_id) == pending_before
    fills_path = registry.data_dir(portfolio_id) / "fills.jsonl"
    assert not fills_path.exists() or fills_path.read_text().strip() == ""

    settled = paper_account.settle_target(
        {ticker: 100.0}, "2026-08-10", portfolio_id=portfolio_id
    )
    assert settled == target
    assert paper_account.pending_target_file_exists(portfolio_id) is False
    assert paper_account._load_account(portfolio_id)["positions"][ticker]["shares"] > 10.0
    fills = [json.loads(line) for line in fills_path.read_text().splitlines()]
    assert len(fills) == 1 and fills[0]["ticker"] == ticker and fills[0]["side"] == "buy"


@pytest.mark.parametrize(
    ("module_name", "mcp_name", "portfolio_id", "ticker", "benchmark"),
    [
        ("bot.china", "brain.china_mcp", "china", "600519.SS", "000300.SS"),
        ("bot.hk", "brain.hk_mcp", "hk", "0700.HK", "^HSI"),
    ],
)
def test_regional_runner_skips_mark_and_retains_blocked_exit(
    isolated_book,
    monkeypatch,
    module_name,
    mcp_name,
    portfolio_id,
    ticker,
    benchmark,
):
    """CN and HK honor the central exit-price stop without mutating their paper account."""
    module = importlib.import_module(module_name)
    mcp = importlib.import_module(mcp_name)
    from bot import settle
    from brain import cost_guard, portfolio_learning
    from bridge import build_portfolio
    from control_plane import packet_gate
    from data_layer import feed_health
    from portfolio import fx, mandate_packet, paper_account, registry

    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 999_000.0,
            "positions": {ticker: {"shares": 10.0, "avg_cost": 100.0}},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        portfolio_id,
    )
    account_path = registry.data_dir(portfolio_id) / "account.json"
    account_before = account_path.read_bytes()

    submission = {
        "holdings": [],
        "summary": "explicit exit awaiting a trusted quote",
        "exit_decisions": [{
            "ticker": ticker,
            "action": "exit",
            "reason": "falsifier fired",
            "why_now": "today",
            "evidence": ["test"],
        }],
    }
    monkeypatch.setattr(mcp, "clear_submission", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcp, "read_submission", lambda *args, **kwargs: submission)
    monkeypatch.setattr(module, "_run_brain", lambda *args, **kwargs: {"ok": True, "model": "test"})
    monkeypatch.setattr(module, "_warm_live", lambda *args, **kwargs: None)
    monkeypatch.setattr(feed_health, "status", lambda *args, **kwargs: {"status": "ok"})
    monkeypatch.setattr(cost_guard, "over_budget", lambda *args, **kwargs: False)
    monkeypatch.setattr(cost_guard, "record", lambda *args, **kwargs: None)
    monkeypatch.setattr(paper_account, "_current_price",
                        lambda symbol: 500.0 if symbol == benchmark else None)
    monkeypatch.setattr(fx, "usd_to", lambda value, currency: value)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)

    class _Packet:
        ok = True
        packet_id = "test-packet"

        @staticmethod
        def to_meta():
            return {}

    monkeypatch.setattr(packet_gate, "process", lambda *args, **kwargs: _Packet())
    monkeypatch.setattr(build_portfolio, "write", lambda *args, **kwargs: {})
    monkeypatch.setattr(module, "_append_decision_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "_translate_report", lambda *args, **kwargs: False)
    monkeypatch.setattr(mandate_packet, "build", lambda *args, **kwargs: {})
    monkeypatch.setattr(mandate_packet, "write_packet", lambda *args, **kwargs: None)
    monkeypatch.setattr(mandate_packet, "emit_run_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(portfolio_learning, "refresh_post_sell",
                        lambda *args, **kwargs: {"summary": {}})
    monkeypatch.setattr(portfolio_learning, "derive_lessons",
                        lambda *args, **kwargs: {"lessons": []})

    mark_calls: list[dict] = []

    def forbidden_mark(*args, **kwargs):
        mark_calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("regional runner marked after an exit-price stop")

    monkeypatch.setattr(paper_account, "mark", forbidden_mark)
    result = (
        module.run_china("2026-08-09", armed=True, force=True)
        if portfolio_id == "china"
        else module.run_hk("2026-08-09", armed=True, force=True)
    )

    assert result["execution_skipped"] == "unpriceable_exit_prices"
    assert result["unpriceable_exits"] == [ticker]
    assert result["pending_target_retained"] is True
    assert result["queued_for_open"] is True
    assert result["mark_skipped"] == "execution_quote_guard"
    assert result["executed"] == []
    assert mark_calls == []
    assert account_path.read_bytes() == account_before
    pending = paper_account.load_pending_target(portfolio_id)
    assert pending is not None and pending["target"] == {}
