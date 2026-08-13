"""Proof for the explicit, paper-only US Brain legacy-ETF migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


PRICES = {
    "AAPL": 200.0,
    "NVDA": 300.0,
    "USMV": 100.0,
    "XLP": 90.0,
    "XLV": 170.0,
    "SPY": 500.0,
}
ETF_NAMES = {"USMV", "XLP", "XLV"}


def _identity(ticker: str) -> dict:
    if ticker in ETF_NAMES:
        return {"ticker": ticker, "kind": "etf", "status": "test_etf", "verified": True}
    if ticker in {"AAPL", "NVDA"}:
        return {
            "ticker": ticker,
            "kind": "common_stock",
            "status": "test_common_stock",
            "verified": True,
        }
    return {
        "ticker": ticker,
        "kind": "unknown",
        "status": "test_unknown",
        "verified": False,
    }


@pytest.fixture
def migration_book(tmp_path, monkeypatch) -> Path:
    from brain import decision_submission
    from portfolio import instrument_policy, paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    monkeypatch.setattr(instrument_policy, "classify_us_instrument", _identity)
    monkeypatch.setattr(
        decision_submission,
        "_instrument_identity",
        lambda ticker: {k: v for k, v in _identity(ticker).items() if k != "ticker"},
    )
    monkeypatch.setattr(paper_account, "_current_price", lambda ticker: PRICES.get(ticker))
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 875_000.0,
            "positions": {
                "AAPL": {"shares": 100.0, "avg_cost": 180.0},
                "USMV": {"shares": 300.0, "avg_cost": 99.0},
                "XLP": {"shares": 200.0, "avg_cost": 86.0},
                "XLV": {"shares": 85.0, "avg_cost": 166.0},
            },
            "spy_shares": None,
            "spy_inception_price": None,
        },
        "autonomous",
    )
    return registry.data_dir("autonomous")


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _fills(book: Path) -> list[dict]:
    path = book / "fills.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _audit(book: Path) -> list[dict]:
    path = book / "legacy_etf_migration.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_dry_run_is_strictly_read_only_and_builds_explicit_normalized_exit(
    migration_book,
):
    from portfolio import autonomous_migration

    before = _tree_bytes(migration_book)
    result = autonomous_migration.migrate(
        "2026-08-11", apply=False, market_open=False
    )

    assert result["ok"] is True
    assert result["status"] == "ready"
    assert result["target"] == {"AAPL": pytest.approx(result["target"]["AAPL"])}
    assert result["legacy_etfs"] == ["USMV", "XLP", "XLV"]
    assert {
        row["ticker"] for row in result["submission"]["exit_decisions"]
    } == ETF_NAMES
    assert all(
        row["reason_code"] == "legacy_instrument_migration"
        for row in result["submission"]["exit_decisions"]
    )
    assert result["submission"]["operator_migration"]["paper_only"] is True
    assert _tree_bytes(migration_book) == before


def test_closed_apply_queues_hash_bound_stock_only_target_without_fill_or_account_write(
    migration_book,
):
    from portfolio import autonomous_migration, paper_account

    account_path = migration_book / "account.json"
    account_before = account_path.read_bytes()
    expected_positions_sha256 = paper_account.positions_sha256(
        paper_account._load_account("autonomous")["positions"]
    )
    result = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )

    assert result["ok"] is True
    assert result["status"] == "queued"
    assert result["queued"] is True
    assert result["executed"] == []
    assert account_path.read_bytes() == account_before
    assert _fills(migration_book) == []
    pending = paper_account.load_pending_target("autonomous")
    assert set(pending["target"]) == {"AAPL"}
    assert pending["execution_constraints"] == {
        "schema": "execution_constraints.v1",
        "mode": "preserve_existing_shares",
        "tickers": ["AAPL"],
        "target_sha256": paper_account._target_sha256(pending["target"]),
        "positions_sha256": expected_positions_sha256,
    }
    snapshot = pending["decision_snapshot"]
    assert snapshot["target_sha256"] == paper_account._target_sha256(pending["target"])
    assert snapshot["submission"]["operator_migration"]["migration_id"] == result["migration_id"]
    assert (
        snapshot["submission"]["operator_migration"]["positions_sha256"]
        == expected_positions_sha256
    )
    assert {row["ticker"] for row in snapshot["submission"]["exit_decisions"]} == ETF_NAMES
    latest = json.loads((migration_book / "latest.json").read_text())
    assert latest["legacy_etf_migration"]["status"] == "pending"
    pending_rows = {
        row["ticker"]: row for row in latest["positions"] if row["ticker"] in ETF_NAMES
    }
    assert set(pending_rows) == ETF_NAMES
    assert all(row["verdict"] == "exit_pending" for row in pending_rows.values())
    decisions = [
        json.loads(line)
        for line in (migration_book / "decisions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert decisions[-1]["target_status"] == "queued"
    assert decisions[-1]["model"] == "deterministic_operator_migration"
    assert [row["event"] for row in _audit(migration_book)] == [
        "migration_authorized",
        "migration_outcome",
    ]


def test_open_apply_still_queues_then_scheduler_sells_etfs_and_preserves_stock(
    migration_book, monkeypatch
):
    from bot import settle
    from portfolio import autonomous_migration, paper_account

    before_aapl = paper_account._load_account("autonomous")["positions"]["AAPL"].copy()
    queued = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=True, prices=PRICES
    )

    assert queued["ok"] is True
    assert queued["status"] == "queued"
    assert queued["operator_execution_mode"] == "queue_only"
    assert queued["observed_market_open"] is True
    assert _fills(migration_book) == []
    assert paper_account._load_account("autonomous")["positions"]["AAPL"] == before_aapl

    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    result = settle.settle_open(
        "autonomous",
        "2026-08-12",
        _open_price_fn=lambda ticker: (PRICES.get(ticker), "test_open"),
    )

    assert result["ok"] is True
    account = paper_account._load_account("autonomous")
    assert set(account["positions"]) == {"AAPL"}
    assert account["positions"]["AAPL"]["shares"] == before_aapl["shares"]
    assert account["positions"]["AAPL"]["avg_cost"] == before_aapl["avg_cost"]
    fills = _fills(migration_book)
    assert [(row["ticker"], row["side"]) for row in fills] == [
        ("USMV", "sell"),
        ("XLP", "sell"),
        ("XLV", "sell"),
    ]
    assert [
        {key: row.get(key) for key in ("ticker", "side", "shares", "price", "value")}
        for row in result["executed"]
    ] == [
        {
            "ticker": row["ticker"],
            "side": "sell",
            "shares": row["shares"],
            "price": row["price"],
            "value": row["value"],
        }
        for row in fills
    ]
    assert result["receipt_acknowledged"] is True
    assert result["migration_settlement_link"]["migration_id"] == queued["migration_id"]
    assert paper_account.pending_settlement_receipts("autonomous") == []
    latest = json.loads((migration_book / "latest.json").read_text())
    assert latest["legacy_etf_migration"]["status"] == "settled"
    assert {row["ticker"] for row in latest["positions"]} == {"AAPL"}
    decision = json.loads((migration_book / "decisions.jsonl").read_text().splitlines()[-1])
    assert decision["target_status"] == "executed"

    rerun = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=True, prices=PRICES
    )
    assert rerun["status"] == "already_complete"
    assert _fills(migration_book) == fills


def test_missing_open_exit_price_retains_queued_intent_and_mutates_no_account_or_fills(
    migration_book, monkeypatch
):
    from bot import settle
    from portfolio import autonomous_migration, paper_account

    monkeypatch.setattr(
        paper_account,
        "_current_price",
        lambda ticker: PRICES.get(ticker) if ticker != "XLV" else None,
    )
    account_path = migration_book / "account.json"
    account_before = account_path.read_bytes()
    incomplete = {ticker: price for ticker, price in PRICES.items() if ticker != "XLV"}

    queued = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=True, prices=incomplete
    )

    assert queued["status"] == "queued"
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    result = settle.settle_open(
        "autonomous",
        "2026-08-12",
        _open_price_fn=lambda ticker: (incomplete.get(ticker), "test_open"),
    )

    assert result["skipped"] == "unpriceable_exit_prices"
    assert result["unpriceable_exits"] == ["XLV"]
    assert result["pending_retained"] is True
    assert account_path.read_bytes() == account_before
    assert _fills(migration_book) == []
    pending = paper_account.load_pending_target("autonomous")
    assert set(pending["target"]) == {"AAPL"}
    assert pending["decision_snapshot"]["submission"]["operator_migration"]
    latest = json.loads((migration_book / "latest.json").read_text())
    assert latest["legacy_etf_migration"]["status"] == "pending"
    assert latest["legacy_etf_migration"]["pending_reason"] == "next_market_open"
    by_ticker = {row["ticker"]: row for row in latest["positions"]}
    assert by_ticker["XLV"]["migration_status"] == "legacy_etf_exit_pending"


def test_unknown_held_instrument_freezes_before_any_write(migration_book):
    from portfolio import autonomous_migration, paper_account

    state = paper_account._load_account("autonomous")
    state["positions"]["MYSTERY"] = {"shares": 10.0, "avg_cost": 50.0}
    paper_account._save_account(state, "autonomous")
    before = _tree_bytes(migration_book)

    result = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )

    assert result["ok"] is False
    assert result["status"] == "blocked_unknown_held_instrument"
    assert result["blocked_instruments"] == [
        {"ticker": "MYSTERY", "kind": "unknown", "status": "test_unknown"}
    ]
    assert _tree_bytes(migration_book) == before


def test_equivalent_closed_queue_and_completed_book_are_idempotent(migration_book):
    from portfolio import autonomous_migration, paper_account

    first = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )
    pending_path = migration_book / "pending_target.json"
    pending_before = pending_path.read_bytes()
    audit_before = _audit(migration_book)

    second = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )
    assert first["status"] == "queued"
    assert second["status"] == "already_queued"
    assert pending_path.read_bytes() == pending_before
    assert _audit(migration_book) == audit_before

    # Simulate the already-completed state without fabricating a fill: the no-ETF
    # branch must be a pure no-op and must not create another queue or audit row.
    state = paper_account._load_account("autonomous")
    state["positions"] = {"AAPL": state["positions"]["AAPL"]}
    paper_account._save_account(state, "autonomous")
    paper_account.clear_pending_target("autonomous")
    completed_before = _tree_bytes(migration_book)
    completed = autonomous_migration.migrate(
        "2026-08-12", apply=True, market_open=False, prices=PRICES
    )
    assert completed["status"] == "already_complete"
    assert _tree_bytes(migration_book) == completed_before


def test_next_open_two_x_common_stock_gap_preserves_exact_shares_and_sells_only_etfs(
    migration_book, monkeypatch
):
    from bot import settle
    from portfolio import autonomous_migration, paper_account

    queued = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )
    assert queued["status"] == "queued"
    pending = paper_account.load_pending_target("autonomous")
    assert pending["execution_constraints"]["mode"] == "preserve_existing_shares"
    before = paper_account._load_account("autonomous")["positions"]["AAPL"].copy()

    # AAPL doubles between the decision and next open.  The static percentage
    # target would otherwise sell roughly half the line, well beyond the 1% NAV
    # continuation band; the hash-bound execution constraint must pin its lot.
    open_prices = {**PRICES, "AAPL": 400.0, "SPY": 500.0}
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    result = settle.settle_open(
        "autonomous",
        "2026-08-12",
        _open_price_fn=lambda ticker: (open_prices.get(ticker), "test_open"),
    )

    assert result["ok"] is True
    account = paper_account._load_account("autonomous")
    assert set(account["positions"]) == {"AAPL"}
    assert account["positions"]["AAPL"]["shares"] == before["shares"]
    assert account["positions"]["AAPL"]["avg_cost"] == before["avg_cost"]
    fills = _fills(migration_book)
    assert [(row["ticker"], row["side"]) for row in fills] == [
        ("USMV", "sell"),
        ("XLP", "sell"),
        ("XLV", "sell"),
    ]
    assert not any(row["ticker"] == "AAPL" for row in fills)
    assert not paper_account.pending_target_file_exists("autonomous")
    assert paper_account.pending_settlement_receipts("autonomous") == []


def test_pending_migration_fences_nightly_overnight_and_derisk_rewriters(
    migration_book, monkeypatch
):
    from bot import autonomous, derisk, overnight
    from portfolio import autonomous_migration, paper_account

    queued = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )
    assert queued["status"] == "queued"
    pending_path = migration_book / "pending_target.json"
    before = pending_path.read_bytes()

    def forbidden(*args, **kwargs):
        raise AssertionError("migration queue overwrite path was reached")

    monkeypatch.setattr(autonomous, "_run_brain", forbidden)
    monkeypatch.setattr(derisk, "tripwire", forbidden)
    monkeypatch.setattr(paper_account, "save_pending_target", forbidden)

    nightly = autonomous.run_autonomous(asof="2026-08-11", armed=True)
    overnight_result = overnight.watch("autonomous", asof="2026-08-12", force=True)
    derisk_result = derisk.derisk_brain("autonomous", asof="2026-08-12", force=True)

    assert nightly["skipped"] == "legacy_etf_migration_pending"
    assert overnight_result["skipped"] == "legacy_etf_migration_pending"
    assert derisk_result["skipped"] == "legacy_etf_migration_pending"
    assert pending_path.read_bytes() == before


def test_non_equivalent_valid_stock_queue_blocks_migration_without_replacement(
    migration_book,
):
    from portfolio import autonomous_migration, paper_account

    paper_account.save_pending_target(
        {"AAPL": 0.02, "NVDA": 0.05},
        "2026-08-10",
        portfolio_id="autonomous",
        decision_snapshot={
            "schema": "mastermind.target_book.v2",
            "holdings": [
                {"ticker": "AAPL", "weight": 0.02, "rationale": "existing queue"},
                {"ticker": "NVDA", "weight": 0.05, "rationale": "existing queue"},
            ],
            "summary": "independently accepted stock target",
        },
    )
    pending_path = migration_book / "pending_target.json"
    pending_before = pending_path.read_bytes()
    account_before = (migration_book / "account.json").read_bytes()
    tree_before = _tree_bytes(migration_book)

    result = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )

    assert result["ok"] is False
    assert result["status"] == "blocked_non_equivalent_pending_target"
    assert result["existing_pending_sha256"]
    assert pending_path.read_bytes() == pending_before
    assert (migration_book / "account.json").read_bytes() == account_before
    assert _fills(migration_book) == []
    assert _tree_bytes(migration_book) == tree_before


def test_pending_target_created_after_plan_is_rechecked_before_authorization(
    migration_book, monkeypatch
):
    from portfolio import autonomous_migration, paper_account

    real_build_plan = autonomous_migration.build_plan
    raced: dict[str, bytes] = {}
    account_before = (migration_book / "account.json").read_bytes()

    def build_then_race(asof=None):
        plan = real_build_plan(asof)
        assert plan["status"] == "ready"
        paper_account.save_pending_target(
            {"AAPL": 0.02, "NVDA": 0.05},
            "2026-08-10",
            portfolio_id="autonomous",
            decision_snapshot={
                "schema": "mastermind.target_book.v2",
                "holdings": [
                    {"ticker": "AAPL", "weight": 0.02, "rationale": "raced queue"},
                    {"ticker": "NVDA", "weight": 0.05, "rationale": "raced queue"},
                ],
                "summary": "new nightly target arrived after operator planning",
            },
        )
        raced["pending"] = (migration_book / "pending_target.json").read_bytes()
        return plan

    monkeypatch.setattr(autonomous_migration, "build_plan", build_then_race)
    result = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )

    assert result["ok"] is False
    assert result["status"] == "blocked_non_equivalent_pending_target"
    assert result["pending_recheck_stage"] == "pre_authorization"
    assert (migration_book / "pending_target.json").read_bytes() == raced["pending"]
    assert (migration_book / "account.json").read_bytes() == account_before
    assert _fills(migration_book) == []
    assert _audit(migration_book) == []


@pytest.mark.parametrize("drift", ["changed_etf_shares", "added_common_stock"])
def test_held_lot_drift_after_plan_blocks_before_authorization(
    migration_book, monkeypatch, drift
):
    from portfolio import autonomous_migration, paper_account

    real_build_plan = autonomous_migration.build_plan
    pending_path = migration_book / "pending_target.json"

    def build_then_drift(asof=None):
        plan = real_build_plan(asof)
        assert plan["status"] == "ready"
        state = paper_account._load_account("autonomous")
        if drift == "changed_etf_shares":
            state["positions"]["USMV"]["shares"] += 1.0
        else:
            state["positions"]["NVDA"] = {"shares": 2.0, "avg_cost": 250.0}
        paper_account._save_account(state, "autonomous")
        return plan

    monkeypatch.setattr(autonomous_migration, "build_plan", build_then_drift)
    result = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )

    assert result["ok"] is False
    assert result["status"] == "blocked_positions_changed"
    assert result["positions_recheck_stage"] == "pre_authorization"
    assert result["observed_positions_sha256"] != result["positions_sha256"]
    assert not pending_path.exists()
    assert _fills(migration_book) == []
    assert _audit(migration_book) == []


def test_held_lot_drift_immediately_before_save_aborts_without_queue_or_fill(
    migration_book, monkeypatch
):
    from portfolio import autonomous_migration, paper_account

    real_append_audit = autonomous_migration._append_audit

    def append_then_drift(event):
        real_append_audit(event)
        if event.get("event") == "migration_authorized":
            state = paper_account._load_account("autonomous")
            state["positions"]["XLV"]["shares"] += 1.0
            paper_account._save_account(state, "autonomous")

    monkeypatch.setattr(autonomous_migration, "_append_audit", append_then_drift)
    result = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )

    assert result["ok"] is False
    assert result["status"] == "blocked_positions_changed"
    assert result["positions_recheck_stage"] == "immediate_pre_save"
    assert result["observed_positions_sha256"] != result["positions_sha256"]
    assert not (migration_book / "pending_target.json").exists()
    assert _fills(migration_book) == []
    assert [row["event"] for row in _audit(migration_book)] == [
        "migration_authorized",
        "migration_aborted",
    ]


def test_atomic_require_absent_cas_preserves_queue_raced_after_last_operator_check(
    migration_book, monkeypatch
):
    from bot import settle
    from portfolio import autonomous_migration, paper_account

    real_execute_or_queue = settle.execute_or_queue
    raced: dict[str, bytes] = {}
    account_before = (migration_book / "account.json").read_bytes()

    def queue_rival_then_execute(*args, **kwargs):
        paper_account.save_pending_target(
            {"AAPL": 0.02, "NVDA": 0.05},
            "2026-08-10",
            portfolio_id="autonomous",
            decision_snapshot={
                "schema": "mastermind.target_book.v2",
                "holdings": [
                    {"ticker": "AAPL", "weight": 0.02, "rationale": "CAS rival"},
                    {"ticker": "NVDA", "weight": 0.05, "rationale": "CAS rival"},
                ],
                "summary": "nightly target won the atomic queue race",
            },
        )
        raced["pending"] = (migration_book / "pending_target.json").read_bytes()
        return real_execute_or_queue(*args, **kwargs)

    monkeypatch.setattr(settle, "execute_or_queue", queue_rival_then_execute)
    result = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )

    assert result["status"] == "blocked"
    assert result["skipped"] == "pending_target_cas_conflict"
    assert result["pending_recheck_stage"] == "atomic_save"
    assert result["target_status"] is None
    assert (migration_book / "pending_target.json").read_bytes() == raced["pending"]
    assert (migration_book / "account.json").read_bytes() == account_before
    assert _fills(migration_book) == []
    assert not (migration_book / "latest.json").exists()
    assert not (migration_book / "decisions.jsonl").exists()
    assert [row["event"] for row in _audit(migration_book)] == [
        "migration_authorized",
        "migration_outcome",
    ]
    assert _audit(migration_book)[-1]["status"] == "blocked"


def test_rejected_migration_payload_never_labels_actual_etfs_as_exit_queued(
    migration_book,
):
    from bot import autonomous
    from portfolio import autonomous_migration

    plan = autonomous_migration.build_plan("2026-08-11")
    payload = autonomous._build_payload(
        "2026-08-11",
        plan["submission"],
        PRICES,
        [],
        [],
        {"model": "deterministic_operator_migration", "cost_usd": 0.0},
        target_status="rejected_latest_target_queue_failed",
    )

    etf_rows = {
        row["ticker"]: row for row in payload["positions"] if row["ticker"] in ETF_NAMES
    }
    assert set(etf_rows) == ETF_NAMES
    assert all(row["verdict"] == "mandate_violation" for row in etf_rows.values())
    assert all(row["migration_pending"] is False for row in etf_rows.values())
    assert all(
        row["mandate_status"] == "legacy_etf_exit_blocked"
        for row in etf_rows.values()
    )
    assert payload["legacy_etf_migration"]["status"] == "blocked"
    assert payload["legacy_etf_migration"]["target_status"] == (
        "rejected_latest_target_queue_failed"
    )


def test_settlement_link_is_durable_before_ack_and_deduplicates_retry(
    migration_book, monkeypatch
):
    from bot import settle
    from portfolio import autonomous_migration, paper_account

    queued = autonomous_migration.migrate(
        "2026-08-11", apply=True, market_open=False, prices=PRICES
    )
    assert queued["status"] == "queued"
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    real_ack = paper_account.acknowledge_settlement_receipt
    calls = {"n": 0}

    def fail_first_ack(transaction_id, portfolio_id=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated_ack_failure")
        return real_ack(transaction_id, portfolio_id)

    monkeypatch.setattr(paper_account, "acknowledge_settlement_receipt", fail_first_ack)
    price_fn = lambda ticker: (PRICES.get(ticker), "test_open")

    first = settle.settle_open(
        "autonomous", "2026-08-12", _open_price_fn=price_fn
    )
    assert first["ok"] is False
    assert first["skipped"] == "settlement_receipt_ack_pending"
    assert first["receipt_retained"] is True
    assert first["migration_settlement_link"]["deduplicated"] is False
    receipts = paper_account.pending_settlement_receipts("autonomous")
    assert len(receipts) == 1
    receipt_transaction_id = receipts[0]["transaction_id"]

    links = [
        row for row in _audit(migration_book)
        if row.get("event") == "migration_settlement_committed"
    ]
    assert len(links) == 1
    link = links[0]
    fills = _fills(migration_book)
    assert link["migration_id"] == queued["migration_id"]
    assert link["transaction_id"] == receipts[0]["transaction_id"]
    assert link["fill_ids"] == sorted(row["fill_id"] for row in fills)

    second = settle.settle_open(
        "autonomous", "2026-08-12", _open_price_fn=price_fn
    )
    assert second["ok"] is True
    assert second["receipt_acknowledged"] is True
    assert second["migration_settlement_link"]["deduplicated"] is True
    assert paper_account.pending_settlement_receipts("autonomous") == []
    assert len(
        [
            row for row in _audit(migration_book)
            if row.get("event") == "migration_settlement_committed"
        ]
    ) == 1
    assert len(_fills(migration_book)) == 3
    decisions = [
        json.loads(line)
        for line in (migration_book / "decisions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    # The exact accepted row transitions in place; settlement must not create a second date row.
    settled = [
        row for row in decisions
        if row.get("asof") == "2026-08-11" and row.get("target_status") == "executed"
    ]
    assert len(settled) == 1
    assert settled[0]["settled_asof"] == "2026-08-12"
    assert settled[0]["settlement_transaction_id"] == receipt_transaction_id
    assert not [row for row in decisions if row.get("asof") == "2026-08-12"]
