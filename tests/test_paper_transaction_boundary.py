"""Fault-injection coverage for executable-target and paper-transaction authority boundaries."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


BOOK_CASES = {
    "autonomous": ({"AAPL": 0.20, "MSFT": 0.20}, {"AAPL": 100.0, "MSFT": 200.0, "SPY": 500.0}),
    "china": (
        {"600519.SS": 0.20, "000858.SZ": 0.20},
        {"600519.SS": 100.0, "000858.SZ": 200.0, "000300.SS": 50.0},
    ),
    "hk": ({"0700.HK": 0.20, "9988.HK": 0.20}, {"0700.HK": 100.0, "9988.HK": 200.0, "^HSI": 50.0}),
}


@pytest.fixture
def isolated_books(tmp_path, monkeypatch):
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    return tmp_path


def _seed_fresh(paper_account, portfolio_id: str) -> Path:
    from portfolio import registry

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
    return registry.data_dir(portfolio_id)


def _fills(book_dir: Path) -> list[dict]:
    path = book_dir / "fills.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.mark.parametrize("portfolio_id", BOOK_CASES)
@pytest.mark.parametrize("save_mode", ["before_replace", "after_replace"])
def test_account_write_failure_replays_once_and_clears_exact_pending(
    isolated_books, monkeypatch, portfolio_id, save_mode
):
    from portfolio import paper_account

    target, prices = BOOK_CASES[portfolio_id]
    book_dir = _seed_fresh(paper_account, portfolio_id)
    account_before = (book_dir / "account.json").read_bytes()
    paper_account.save_pending_target(target, "2026-08-08", portfolio_id=portfolio_id)

    real_save = paper_account._save_account
    failed = {"done": False}

    def fail_once(state, pid=None):
        if not failed["done"]:
            failed["done"] = True
            if save_mode == "after_replace":
                real_save(state, pid)
            raise OSError(f"account-{save_mode}")
        return real_save(state, pid)

    monkeypatch.setattr(paper_account, "_save_account", fail_once)
    with pytest.raises(OSError, match=f"account-{save_mode}"):
        paper_account.settle_target(prices, "2026-08-09", portfolio_id=portfolio_id)

    assert paper_account._transaction_path(portfolio_id).exists()
    assert paper_account.pending_target_file_exists(portfolio_id)
    if save_mode == "before_replace":
        assert (book_dir / "account.json").read_bytes() == account_before

    recovered = paper_account.recover_paper_transaction(portfolio_id)
    assert recovered and recovered["status"] == "committed"
    assert not paper_account._transaction_path(portfolio_id).exists()
    assert not paper_account.pending_target_file_exists(portfolio_id)
    rows = _fills(book_dir)
    assert len(rows) == 2
    assert len({row["fill_id"] for row in rows}) == 2
    assert {row["transaction_id"] for row in rows} == {recovered["transaction_id"]}
    assert set(paper_account._load_account(portfolio_id)["positions"]) == set(target)
    assert paper_account.recover_paper_transaction(portfolio_id) is None
    assert len(_fills(book_dir)) == 2


@pytest.mark.parametrize("portfolio_id", BOOK_CASES)
@pytest.mark.parametrize("failure_index", [0, 1])
@pytest.mark.parametrize("failure_mode", ["before_append", "after_append"])
def test_each_fill_append_failure_is_idempotently_recovered(
    isolated_books, monkeypatch, portfolio_id, failure_index, failure_mode
):
    from portfolio import paper_account

    target, prices = BOOK_CASES[portfolio_id]
    book_dir = _seed_fresh(paper_account, portfolio_id)
    paper_account.save_pending_target(target, "2026-08-08", portfolio_id=portfolio_id)
    real_append = paper_account._append_jsonl
    fill_calls = {"count": 0}

    def fail_selected(path, row):
        if path.name != "fills.jsonl":
            return real_append(path, row)
        index = fill_calls["count"]
        fill_calls["count"] += 1
        if index == failure_index:
            if failure_mode == "after_append":
                real_append(path, row)
            raise OSError(f"fill-{failure_mode}-{failure_index}")
        return real_append(path, row)

    monkeypatch.setattr(paper_account, "_append_jsonl", fail_selected)
    with pytest.raises(OSError, match=f"fill-{failure_mode}-{failure_index}"):
        paper_account.settle_target(prices, "2026-08-09", portfolio_id=portfolio_id)

    assert paper_account._transaction_path(portfolio_id).exists()
    assert paper_account.pending_target_file_exists(portfolio_id)
    recovered = paper_account.recover_paper_transaction(portfolio_id)

    assert recovered and recovered["status"] == "committed"
    assert not paper_account.pending_target_file_exists(portfolio_id)
    rows = _fills(book_dir)
    assert len(rows) == 2
    assert len({row["fill_id"] for row in rows}) == 2
    assert len({row["transaction_id"] for row in rows}) == 1
    assert paper_account.recover_paper_transaction(portfolio_id) is None
    assert len(_fills(book_dir)) == 2


def test_partial_fill_line_is_quarantined_and_replayed_once(isolated_books, monkeypatch):
    from portfolio import paper_account

    target, prices = BOOK_CASES["autonomous"]
    book_dir = _seed_fresh(paper_account, "autonomous")
    paper_account.save_pending_target(target, "2026-08-08", portfolio_id="autonomous")
    real_append = paper_account._append_jsonl
    failed = {"done": False}

    def partial_then_fail(path, row):
        if path.name == "fills.jsonl" and not failed["done"]:
            failed["done"] = True
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("ab") as fh:
                fh.write(json.dumps(row).encode("utf-8")[:31])
            raise OSError("partial-fill-write")
        return real_append(path, row)

    monkeypatch.setattr(paper_account, "_append_jsonl", partial_then_fail)
    with pytest.raises(OSError, match="partial-fill-write"):
        paper_account.settle_target(prices, "2026-08-09", portfolio_id="autonomous")

    paper_account.recover_paper_transaction("autonomous")
    assert len(_fills(book_dir)) == 2
    assert len({row["fill_id"] for row in _fills(book_dir)}) == 2
    assert list(book_dir.glob("fills.jsonl.partial.*"))


def test_concurrent_recovery_serializes_and_never_duplicates_fills(isolated_books, monkeypatch):
    from portfolio import paper_account

    target, prices = BOOK_CASES["autonomous"]
    book_dir = _seed_fresh(paper_account, "autonomous")
    paper_account.save_pending_target(target, "2026-08-08", portfolio_id="autonomous")
    real_append = paper_account._append_jsonl
    failed = {"done": False}

    def fail_once(path, row):
        if path.name == "fills.jsonl" and not failed["done"]:
            failed["done"] = True
            raise OSError("seed-recovery-wal")
        return real_append(path, row)

    monkeypatch.setattr(paper_account, "_append_jsonl", fail_once)
    with pytest.raises(OSError, match="seed-recovery-wal"):
        paper_account.settle_target(prices, "2026-08-09", portfolio_id="autonomous")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: paper_account.recover_paper_transaction("autonomous"), range(2)))

    assert sum(bool(result and result.get("status") == "committed") for result in results) == 1
    rows = _fills(book_dir)
    assert len(rows) == 2
    assert len({row["fill_id"] for row in rows}) == 2


@pytest.mark.parametrize("portfolio_id", BOOK_CASES)
@pytest.mark.parametrize("clear_mode", ["before_unlink", "after_unlink"])
def test_pending_clear_failure_retains_wal_and_recovery_never_refills(
    isolated_books, monkeypatch, portfolio_id, clear_mode
):
    from portfolio import paper_account

    target, prices = BOOK_CASES[portfolio_id]
    book_dir = _seed_fresh(paper_account, portfolio_id)
    paper_account.save_pending_target(target, "2026-08-08", portfolio_id=portfolio_id)
    real_clear = paper_account.clear_pending_target
    failed = {"done": False}

    def fail_once(pid=None):
        if not failed["done"]:
            failed["done"] = True
            if clear_mode == "after_unlink":
                real_clear(pid)
            raise OSError("pending-clear")
        return real_clear(pid)

    monkeypatch.setattr(paper_account, "clear_pending_target", fail_once)
    with pytest.raises(OSError, match="pending-clear"):
        paper_account.settle_target(prices, "2026-08-09", portfolio_id=portfolio_id)

    rows_before = _fills(book_dir)
    assert len(rows_before) == 2
    assert paper_account.pending_target_file_exists(portfolio_id) is (clear_mode == "before_unlink")
    assert paper_account._transaction_path(portfolio_id).exists()

    recovered = paper_account.recover_paper_transaction(portfolio_id)
    assert recovered and recovered["status"] == "committed"
    assert not paper_account.pending_target_file_exists(portfolio_id)
    assert not paper_account._transaction_path(portfolio_id).exists()
    assert _fills(book_dir) == rows_before


INVALID_TARGETS = [
    {"AAPL": -0.01},
    {"AAPL": float("nan")},
    {"AAPL": float("inf")},
    {"AAPL": "0.25"},
    {"AAPL": True},
    {"AAPL": 0.60, "MSFT": 0.50},
]


@pytest.mark.parametrize("target", INVALID_TARGETS)
def test_invalid_direct_rebalance_raises_before_any_account_or_fill_write(
    isolated_books, target
):
    from portfolio import paper_account

    book_dir = _seed_fresh(paper_account, "autonomous")
    account_before = (book_dir / "account.json").read_bytes()
    with pytest.raises(paper_account.InvalidTargetWeights):
        paper_account.rebalance(
            target,
            {"AAPL": 100.0, "MSFT": 100.0},
            "2026-08-09",
            portfolio_id="autonomous",
        )
    assert (book_dir / "account.json").read_bytes() == account_before
    assert _fills(book_dir) == []
    assert not paper_account._transaction_path("autonomous").exists()


@pytest.mark.parametrize("portfolio_id", BOOK_CASES)
@pytest.mark.parametrize("target", INVALID_TARGETS + [{"aapl": 0.20}])
def test_invalid_persisted_target_is_quarantined_before_account_write(
    isolated_books, portfolio_id, target
):
    from portfolio import paper_account

    book_dir = _seed_fresh(paper_account, portfolio_id)
    account_before = (book_dir / "account.json").read_bytes()
    payload = {"target": target, "asof": "2026-08-08", "queued_at": "2026-08-08T23:00:00Z"}
    if portfolio_id == "autonomous":
        payload.update({
            "schema_version": paper_account.PENDING_TARGET_SCHEMA_V2,
            "engine_version": paper_account.US_BRAIN_ENGINE_V2,
            "portfolio_id": "autonomous",
        })
    (book_dir / "pending_target.json").write_text(json.dumps(payload), encoding="utf-8")

    result = paper_account.preflight_pending_target(portfolio_id)

    assert result["ok"] is False
    assert result["quarantined"] is True
    assert result["quarantine"]["status"] == "quarantined"
    assert result["quarantine"]["reason"].startswith("invalid_target:")
    assert (book_dir / "account.json").read_bytes() == account_before
    assert not paper_account.pending_target_file_exists(portfolio_id)
    assert list(book_dir.glob("pending_target.quarantine.*.json"))
    assert _fills(book_dir) == []


@pytest.mark.parametrize("target", INVALID_TARGETS)
def test_save_pending_target_rejects_invalid_intent_without_replacing_queue(
    isolated_books, target
):
    from portfolio import paper_account

    _seed_fresh(paper_account, "autonomous")
    paper_account.save_pending_target({"AAPL": 0.20}, "2026-08-08", portfolio_id="autonomous")
    before = paper_account._pending_target_path("autonomous").read_bytes()
    with pytest.raises(paper_account.InvalidTargetWeights):
        paper_account.save_pending_target(target, "2026-08-09", portfolio_id="autonomous")
    assert paper_account._pending_target_path("autonomous").read_bytes() == before


def test_execute_or_queue_rejects_invalid_target_before_account_read(
    isolated_books, monkeypatch
):
    from bot import settle
    from portfolio import paper_account

    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("invalid target reached account state")
        ),
    )
    result = settle.execute_or_queue(
        "autonomous",
        {"AAPL": float("nan")},
        {"AAPL": 100.0},
        "2026-08-09",
        market_open=True,
    )
    assert result["skipped"] == "invalid_target_weights"
    assert result["invalid_target_reason"] == "non_finite_weight:AAPL"
    assert result["executed"] == []


def test_execute_or_queue_reports_recovered_append_as_committed(
    isolated_books, monkeypatch
):
    from bot import settle
    from portfolio import paper_account

    target, prices = BOOK_CASES["autonomous"]
    _seed_fresh(paper_account, "autonomous")
    real_append = paper_account._append_jsonl
    failed = {"done": False}

    def transient_append(path, row):
        if path.name == "fills.jsonl" and not failed["done"]:
            failed["done"] = True
            raise OSError("transient-append")
        return real_append(path, row)

    monkeypatch.setattr(paper_account, "_append_jsonl", transient_append)
    result = settle.execute_or_queue(
        "autonomous", target, prices, "2026-08-09", market_open=True
    )

    assert "error" not in result
    assert result["settlement_recovered"] is True
    assert {row["ticker"] for row in result["executed"]} == set(target)
    assert not paper_account.pending_target_file_exists("autonomous")
    assert not paper_account._transaction_path("autonomous").exists()


def test_execute_or_queue_unresolved_transaction_returns_without_auto_recovery_read(
    isolated_books, monkeypatch
):
    from bot import settle
    from portfolio import paper_account

    target, prices = BOOK_CASES["autonomous"]
    _seed_fresh(paper_account, "autonomous")
    real_load = paper_account._load_account

    def guarded_load(pid=None):
        if paper_account._transaction_path(pid).exists():
            raise AssertionError("error path attempted an auto-recovering account read")
        return real_load(pid)

    real_append = paper_account._append_jsonl

    def route_append(path, row):
        if path.name == "fills.jsonl":
            raise OSError("persistent-append")
        return real_append(path, row)

    monkeypatch.setattr(paper_account, "_load_account", guarded_load)
    monkeypatch.setattr(paper_account, "_append_jsonl", route_append)
    result = settle.execute_or_queue(
        "autonomous", target, prices, "2026-08-09", market_open=True
    )

    assert result["skipped"] == "settle_failed"
    assert "persistent-append" in result["error"]
    assert "persistent-append" in result["recovery_error"]
    assert result["pending_retained"] is True
    assert paper_account._transaction_path("autonomous").exists()


def test_settle_open_reports_recovered_pending_clear_as_success(
    isolated_books, monkeypatch
):
    from bot import settle
    from portfolio import paper_account

    target, prices = BOOK_CASES["autonomous"]
    _seed_fresh(paper_account, "autonomous")
    paper_account.save_pending_target(target, "2026-08-08", portfolio_id="autonomous")
    real_clear = paper_account.clear_pending_target
    failed = {"done": False}

    def transient_clear(pid=None):
        if not failed["done"]:
            failed["done"] = True
            raise OSError("transient-clear")
        return real_clear(pid)

    monkeypatch.setattr(paper_account, "clear_pending_target", transient_clear)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    monkeypatch.setattr(settle, "_republish", lambda *args, **kwargs: None)
    monkeypatch.setattr(paper_account, "mark", lambda *args, **kwargs: None)

    def open_price(ticker):
        return (prices.get(ticker), "polygon_open")

    result = settle.settle_open(
        "autonomous", "2026-08-09", _open_price_fn=open_price
    )

    assert result["ok"] is True
    assert result["settlement_recovered"] is True
    assert {row["ticker"] for row in result["executed"]} == set(target)
    assert not paper_account.pending_target_file_exists("autonomous")
    assert not paper_account._transaction_path("autonomous").exists()
