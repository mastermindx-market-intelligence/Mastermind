"""Retain exact settlement preimages without replaying numeric paper state."""
from __future__ import annotations

import importlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest


BOOKS = {
    "autonomous": ("AAPL", "SPY", "bot.autonomous"),
    "china": ("600519.SS", "000300.SS", "bot.china"),
    "hk": ("0700.HK", "^HSI", "bot.hk"),
}
ASOF = "2026-08-13"


@pytest.fixture
def isolated_books(tmp_path, monkeypatch):
    from portfolio import registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    return tmp_path


def _seed_queue(book, *, weight=0.20, with_decision=False):
    from portfolio import paper_account

    ticker, benchmark, module_name = BOOKS[book]
    target = {ticker: weight}
    prices = {ticker: 100.0, benchmark: 500.0}
    paper_account._save_account(
        {
            "inception_date": "2026-08-01",
            "starting_nav": 1_000_000.0,
            "cash": 1_000_000.0,
            "positions": {},
            "spy_shares": None,
            "spy_inception_price": None,
        },
        book,
    )
    submission = None
    if with_decision:
        module = importlib.import_module(module_name)
        submission = {
            "schema": "mastermind.target_book.v2",
            "holdings": [{
                "ticker": ticker,
                "weight": weight,
                "action": "add",
                "action_effective": "add",
                "rationale": "original receipt-bound thesis",
            }],
            "summary": "accepted original queue",
        }
        module._append_decision_log(
            "2026-08-12", submission, [], [], {},
            target_status="queued", effective_target=target,
        )
    paper_account.save_pending_target(
        target, "2026-08-12", portfolio_id=book, decision_snapshot=submission,
    )
    pending_bytes = paper_account._pending_target_path(book).read_bytes()
    return prices, pending_bytes


def _committed_receipt(book="autonomous", *, weight=0.20):
    from portfolio import paper_account

    prices, pending_bytes = _seed_queue(book, weight=weight)
    paper_account.settle_target(
        prices, ASOF, portfolio_id=book,
        _price_sources={symbol: "captured_test_price" for symbol in prices},
    )
    receipt, = paper_account.pending_settlement_receipts(book)
    active = paper_account._settlement_receipt_path(receipt["transaction_id"], book)
    archive = active.parent / "acknowledged" / active.name
    return receipt, active, archive, pending_bytes


def _numeric_bytes(book):
    from portfolio import paper_account

    paths = paper_account._paths(book)
    return {
        kind: paths[kind].read_bytes() if paths[kind].exists() else None
        for kind in ("account", "fills", "nav")
    }


@pytest.mark.parametrize("book", BOOKS)
@pytest.mark.parametrize("weight", [0.20, 1e-9], ids=["filled", "zero_fill"])
def test_ack_retains_exact_full_receipt_and_leaves_numeric_state_unchanged(
    isolated_books, book, weight
):
    from portfolio import paper_account

    receipt, active, archive, pending_bytes = _committed_receipt(book, weight=weight)
    original = active.read_bytes()
    before = _numeric_bytes(book)
    fills = paper_account.validated_settlement_receipt_fills(receipt)
    assert bool(fills) is (weight == 0.20)

    assert paper_account.acknowledge_settlement_receipt(receipt["transaction_id"], book)

    assert archive.read_bytes() == original
    assert not active.exists()
    assert paper_account.pending_settlement_receipts(book) == []
    assert _numeric_bytes(book) == before
    retained = json.loads(archive.read_bytes())
    assert retained["transaction_identity"]["followup"]["pending_payload"] == json.loads(
        pending_bytes
    )
    assert retained["transaction_identity"]["followup"]["pending_payload"]["queued_at"]
    assert paper_account.validated_settlement_receipt_fills(retained) == fills
    assert paper_account.validated_settlement_receipt_prices(retained) == (
        paper_account.validated_settlement_receipt_prices(receipt)
    )
    assert not paper_account.acknowledge_settlement_receipt(receipt["transaction_id"], book)
    assert archive.read_bytes() == original


def test_conflicting_archive_is_never_overwritten_or_acknowledged(isolated_books):
    from portfolio import paper_account

    receipt, active, archive, _ = _committed_receipt()
    original = active.read_bytes()
    archive.parent.mkdir()
    conflict = b'{"historical_receipt":"different bytes"}\n'
    archive.write_bytes(conflict)
    before = _numeric_bytes("autonomous")

    with pytest.raises(paper_account.PaperTransactionConflict, match="archive"):
        paper_account.acknowledge_settlement_receipt(receipt["transaction_id"], "autonomous")

    assert active.read_bytes() == original
    assert archive.read_bytes() == conflict
    assert _numeric_bytes("autonomous") == before


def test_existing_identical_archive_is_reused_without_rewrite(isolated_books, monkeypatch):
    from portfolio import paper_account

    receipt, active, archive, _ = _committed_receipt()
    original = active.read_bytes()
    archive.parent.mkdir()
    archive.write_bytes(original)
    inode = archive.stat().st_ino

    def forbidden_write(*args, **kwargs):
        raise AssertionError("already retained receipt must not be rewritten")

    monkeypatch.setattr(paper_account, "_atomic_write_bytes", forbidden_write)
    assert paper_account.acknowledge_settlement_receipt(receipt["transaction_id"], "autonomous")
    assert archive.read_bytes() == original
    assert archive.stat().st_ino == inode
    assert not active.exists()


@pytest.mark.parametrize("stage", [
    "archive_write_before",
    "archive_write_after",
    "archive_file_fsync",
    "archive_directory_fsync",
    "receipt_root_fsync",
    "active_unlink",
])
def test_archive_failure_retains_active_preimage_and_retry_reuses_exact_copy(
    isolated_books, monkeypatch, stage
):
    from portfolio import paper_account

    receipt, active, archive, _ = _committed_receipt()
    original = active.read_bytes()
    before = _numeric_bytes("autonomous")
    real_write = paper_account._atomic_write_bytes
    real_fsync = os.fsync
    real_unlink = paper_account._durable_unlink

    def failed_write(path, payload):
        if Path(path) == archive:
            if stage == "archive_write_before":
                raise OSError(stage)
            real_write(path, payload)
            if stage == "archive_write_after":
                raise OSError(stage)
            return
        real_write(path, payload)

    def failed_fsync(fd):
        fd_stat = os.fstat(fd)
        expected_path = {
            "archive_file_fsync": archive,
            "archive_directory_fsync": archive.parent,
            "receipt_root_fsync": active.parent,
        }.get(stage)
        if expected_path is not None and expected_path.exists():
            expected_stat = expected_path.stat()
            if (fd_stat.st_dev, fd_stat.st_ino) == (
                expected_stat.st_dev, expected_stat.st_ino
            ):
                raise OSError(stage)
        real_fsync(fd)

    def failed_unlink(path):
        if Path(path) == active and stage == "active_unlink":
            raise OSError(stage)
        real_unlink(path)

    with monkeypatch.context() as patch:
        patch.setattr(paper_account, "_atomic_write_bytes", failed_write)
        patch.setattr(paper_account.os, "fsync", failed_fsync)
        patch.setattr(paper_account, "_durable_unlink", failed_unlink)
        with pytest.raises(OSError, match=stage):
            paper_account.acknowledge_settlement_receipt(
                receipt["transaction_id"], "autonomous"
            )

    assert active.read_bytes() == original
    assert _numeric_bytes("autonomous") == before
    assert [row["transaction_id"] for row in paper_account.pending_settlement_receipts(
        "autonomous"
    )] == [receipt["transaction_id"]]
    if stage != "archive_write_before":
        assert archive.read_bytes() == original

    assert paper_account.acknowledge_settlement_receipt(receipt["transaction_id"], "autonomous")
    assert archive.read_bytes() == original
    assert not active.exists()
    assert paper_account.pending_settlement_receipts("autonomous") == []
    assert _numeric_bytes("autonomous") == before


def test_archive_file_and_both_directories_are_synced_before_active_removal(
    isolated_books, monkeypatch
):
    from portfolio import paper_account

    receipt, active, archive, _ = _committed_receipt()
    original = active.read_bytes()
    synced = set()
    real_fsync = os.fsync
    real_unlink = paper_account._durable_unlink

    def record_fsync(fd):
        real_fsync(fd)
        fd_stat = os.fstat(fd)
        for label, path in (
            ("archive_file", archive),
            ("archive_directory", archive.parent),
            ("receipt_root", active.parent),
        ):
            if path.exists():
                path_stat = path.stat()
                if (fd_stat.st_dev, fd_stat.st_ino) == (
                    path_stat.st_dev, path_stat.st_ino
                ):
                    synced.add(label)

    def checked_unlink(path):
        if Path(path) == active:
            assert archive.read_bytes() == original
            assert synced == {"archive_file", "archive_directory", "receipt_root"}
        real_unlink(path)

    monkeypatch.setattr(paper_account.os, "fsync", record_fsync)
    monkeypatch.setattr(paper_account, "_durable_unlink", checked_unlink)
    assert paper_account.acknowledge_settlement_receipt(receipt["transaction_id"], "autonomous")


def test_concurrent_acknowledgements_keep_one_exact_archive(isolated_books):
    from portfolio import paper_account

    receipt, active, archive, _ = _committed_receipt()
    original = active.read_bytes()
    barrier = Barrier(2)

    def acknowledge():
        barrier.wait(timeout=5)
        return paper_account.acknowledge_settlement_receipt(
            receipt["transaction_id"], "autonomous"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(acknowledge) for _ in range(2)]
        results = [future.result(timeout=10) for future in futures]

    assert sorted(results) == [False, True]
    assert archive.read_bytes() == original
    assert not active.exists()


@pytest.mark.parametrize("book,weight", [
    ("autonomous", 0.20), ("china", 0.20), ("hk", 0.20), ("autonomous", 1e-9),
], ids=["us", "china", "hk", "zero_fill"])
@pytest.mark.parametrize("stage", ["archive_write_after", "active_unlink"])
def test_real_settlement_ack_retry_never_reprices_refills_or_rewrites_decision(
    isolated_books, monkeypatch, book, weight, stage
):
    from bot import settle
    from portfolio import paper_account, registry

    prices, pending_bytes = _seed_queue(book, weight=weight, with_decision=True)
    monkeypatch.setattr(settle, "is_open", lambda pid: True)
    # Publication is the external side-effect seam; receipt validation, numeric
    # settlement, NAV, position ledger and decision reconciliation remain real.
    monkeypatch.setattr(settle, "_republish", lambda *a, **k: {"ok": True})
    price_calls = []

    def original_prices(pid, symbols, _open_price_fn=None):
        price_calls.append((pid, tuple(sorted(symbols))))
        return dict(prices), {symbol: "captured_test_price" for symbol in prices}

    def no_new_quotes(*args, **kwargs):
        raise AssertionError("committed receipt retry must not fetch a quote")

    monkeypatch.setattr(settle, "_price_and_sources", original_prices)
    monkeypatch.setattr(paper_account, "_current_price", no_new_quotes)
    real_write = paper_account._atomic_write_bytes
    real_unlink = paper_account._durable_unlink

    def failed_write(path, payload):
        real_write(path, payload)
        if Path(path).parent.name == "acknowledged" and stage == "archive_write_after":
            raise OSError("archive finalization fault")

    def failed_unlink(path):
        if Path(path).parent.name == "settlement_receipts" and stage == "active_unlink":
            raise OSError("archive finalization fault")
        real_unlink(path)

    with monkeypatch.context() as patch:
        patch.setattr(paper_account, "_atomic_write_bytes", failed_write)
        patch.setattr(paper_account, "_durable_unlink", failed_unlink)
        first = settle.settle_open(book, ASOF)

    assert first["skipped"] == "settlement_receipt_ack_pending"
    assert first["receipt_retained"] is True
    assert len(price_calls) == 1
    receipt, = paper_account.pending_settlement_receipts(book)
    active = paper_account._settlement_receipt_path(first["transaction_id"], book)
    archive = active.parent / "acknowledged" / active.name
    original = active.read_bytes()
    assert archive.read_bytes() == original
    assert receipt["transaction_identity"]["followup"]["pending_payload"] == json.loads(
        pending_bytes
    )
    before_retry = _numeric_bytes(book)
    journal = registry.data_dir(book) / "decisions.jsonl"
    original_decisions = journal.read_bytes()
    original_fills = paper_account.validated_settlement_receipt_fills(receipt)
    assert len(original_fills) == (1 if weight == 0.20 else 0)
    assert not paper_account.pending_target_file_exists(book)
    monkeypatch.setattr(settle, "_price_and_sources", no_new_quotes)
    monkeypatch.setattr(settle, "_open_price_usd", no_new_quotes)

    recovered = settle.settle_open(book, "2026-08-14", _open_price_fn=no_new_quotes)

    assert recovered["ok"] is True
    assert recovered["receipt_acknowledged"] is True
    assert recovered["settlement_recovered"] is True
    assert recovered["transaction_id"] == first["transaction_id"]
    assert recovered["executed"] == first["executed"]
    assert _numeric_bytes(book) == before_retry
    assert journal.read_bytes() == original_decisions
    assert archive.read_bytes() == original
    assert not active.exists()
    assert paper_account.pending_settlement_receipts(book) == []
    assert len(price_calls) == 1
    from bot import decision_rows
    raw_decisions = [json.loads(line) for line in journal.read_text().splitlines() if line]
    # raw truth: append-only — the seeded queued row plus the appended executed revise row
    assert len(raw_decisions) == 2
    assert raw_decisions[1]["supersede_mode"] == "revise"
    assert raw_decisions[1]["supersedes"] == [raw_decisions[0]["row_id"]]
    decision, = decision_rows.effective_rows(raw_decisions)
    assert decision["settlement_transaction_id"] == receipt["transaction_id"]
    assert decision["settlement_receipt_sha256"] == paper_account._content_sha256(receipt)
    assert decision["settlement_fill_ids"] == [fill["fill_id"] for fill in original_fills]
