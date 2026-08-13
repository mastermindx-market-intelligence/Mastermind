"""Crash-durability gates for projections required before settlement-receipt ACK."""
from __future__ import annotations

import json
import stat
from pathlib import Path


def _fsync_kinds(monkeypatch, module) -> list[str]:
    """Record regular-file vs directory fsync while still exercising the real syscall."""
    real_fsync = module.os.fsync
    calls: list[str] = []

    def recording_fsync(fd: int) -> None:
        mode = module.os.fstat(fd).st_mode
        calls.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(fd)

    monkeypatch.setattr(module.os, "fsync", recording_fsync)
    return calls


def test_first_learning_append_fsyncs_file_and_parent(monkeypatch, tmp_path):
    from brain import portfolio_learning

    path = tmp_path / "autonomous" / "applications.jsonl"
    calls = _fsync_kinds(monkeypatch, portfolio_learning)

    assert portfolio_learning._append_jsonl(path, {"application_id": "application.v1.test"})

    assert json.loads(path.read_text()) == {"application_id": "application.v1.test"}
    assert calls == ["file", "directory"]


def test_position_ledger_replace_is_atomic_and_durable(monkeypatch, tmp_path):
    from portfolio import position_log

    path = tmp_path / "positions_ledger.json"
    monkeypatch.setattr(position_log, "_LEDGER_PATH", path)
    calls = _fsync_kinds(monkeypatch, position_log)
    real_replace = position_log.os.replace
    replacements: list[tuple[Path, Path]] = []

    def recording_replace(source, destination):
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(position_log.os, "replace", recording_replace)

    position_log._save({"brain:AAPL": {"ticker": "AAPL", "still_open": True}})

    assert json.loads(path.read_text()) == {
        "brain:AAPL": {"ticker": "AAPL", "still_open": True}
    }
    assert len(replacements) == 1
    assert replacements[0][0] != path and replacements[0][1] == path
    assert calls == ["file", "directory"]
    assert list(tmp_path.glob(".*.tmp")) == []


def test_both_published_portfolio_contracts_are_atomic_and_durable(monkeypatch, tmp_path):
    from bridge import build_portfolio
    from portfolio import registry

    base = tmp_path / "autonomous"
    monkeypatch.setattr(registry, "data_dir", lambda portfolio_id=None: base)
    calls = _fsync_kinds(monkeypatch, build_portfolio)
    real_replace = build_portfolio.os.replace
    destinations: list[Path] = []

    def recording_replace(source, destination):
        destinations.append(Path(destination))
        real_replace(source, destination)

    monkeypatch.setattr(build_portfolio.os, "replace", recording_replace)

    result = build_portfolio.write(
        {"asof": "2026-08-13", "positions": [{"ticker": "AAPL", "weight": 0.04}]},
        "autonomous",
    )

    hub = Path(result["hub"])
    site = Path(result["site"])
    assert destinations == [hub, site]
    assert calls == ["file", "directory", "file", "directory"]
    assert hub.read_bytes() == site.read_bytes()
    published = json.loads(hub.read_text())
    assert published["schema"] == "portfolio.v1"
    assert published["portfolio_id"] == "autonomous"
    assert list(base.glob(".*.tmp")) == []


def test_nav_mark_uses_durable_atomic_writer(monkeypatch, tmp_path):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    state = paper_account._fresh_account()
    state.update(
        {
            "spy_shares": 2_000.0,
            "spy_inception_price": 500.0,
            "benchmark_symbol": "SPY",
        }
    )
    paper_account._save_account(state, "autonomous")
    nav_path = paper_account._paths("autonomous")["nav"]
    real_atomic_write = paper_account._atomic_write_bytes
    writes: list[Path] = []

    def recording_atomic_write(path, payload):
        writes.append(Path(path))
        real_atomic_write(path, payload)

    monkeypatch.setattr(paper_account, "_atomic_write_bytes", recording_atomic_write)

    paper_account.mark({"SPY": 505.0}, "2026-08-13", portfolio_id="autonomous")

    assert writes == [nav_path]
    row = json.loads(nav_path.read_text().strip())
    assert row["date"] == "2026-08-13"
    assert row["benchmark"] == "SPY"


def test_first_fill_append_fsyncs_file_and_parent(monkeypatch, tmp_path):
    from portfolio import paper_account

    path = tmp_path / "autonomous" / "fills.jsonl"
    calls = _fsync_kinds(monkeypatch, paper_account)

    paper_account._append_jsonl(path, {"fill_id": "fill.test"})

    assert json.loads(path.read_text()) == {"fill_id": "fill.test"}
    assert calls == ["file", "directory"]


def test_pending_target_and_wal_unlinks_are_directory_durable(monkeypatch, tmp_path):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    calls = _fsync_kinds(monkeypatch, paper_account)
    pending = paper_account._pending_target_path("autonomous")
    wal = paper_account._transaction_path("autonomous")
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text("{}", encoding="utf-8")
    wal.write_text("{}", encoding="utf-8")

    paper_account.clear_pending_target("autonomous")
    paper_account._durable_unlink(wal)

    assert not pending.exists() and not wal.exists()
    assert calls == ["directory", "directory"]


def test_quarantine_rename_fsyncs_parent_directory(monkeypatch, tmp_path):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    source = paper_account._pending_target_path("autonomous")
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps({"target": {"AAPL": 0.2}}), encoding="utf-8")
    calls = _fsync_kinds(monkeypatch, paper_account)

    result = paper_account.quarantine_pending_target(
        "autonomous", "superseded_valid_queue", {"target": {"AAPL": 0.2}}
    )

    assert result["status"] == "quarantined"
    assert not source.exists()
    assert calls[0] == "directory"


def test_delayed_older_nav_repair_keeps_ledger_chronological(monkeypatch, tmp_path):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    state = paper_account._fresh_account()
    state.update({
        "spy_shares": 2_000.0,
        "spy_inception_price": 500.0,
        "benchmark_symbol": "SPY",
    })
    paper_account._save_account(state, "autonomous")

    paper_account.mark({"SPY": 510.0}, "2026-08-14", portfolio_id="autonomous")
    paper_account.mark({"SPY": 505.0}, "2026-08-13", portfolio_id="autonomous")

    rows = [
        json.loads(line)
        for line in paper_account._paths("autonomous")["nav"].read_text().splitlines()
        if line.strip()
    ]
    assert [row["date"] for row in rows] == ["2026-08-13", "2026-08-14"]


def test_plain_mark_is_blocked_while_receipt_owns_projection(monkeypatch, tmp_path):
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    paper_account._save_account(paper_account._fresh_account(), "autonomous")
    monkeypatch.setattr(
        paper_account,
        "pending_settlement_receipts",
        lambda portfolio_id=None: [{"transaction_id": "a" * 64}],
    )

    try:
        paper_account.mark({"SPY": 500.0}, "2026-08-13", portfolio_id="autonomous")
    except paper_account.PaperTransactionConflict as exc:
        assert "unfinalized settlement receipt" in str(exc)
    else:
        raise AssertionError("plain NAV mark crossed the settlement receipt fence")
