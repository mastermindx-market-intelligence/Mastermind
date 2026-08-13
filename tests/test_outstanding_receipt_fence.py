"""Regression coverage for committed-receipt projection fences and scheduler surfacing."""
from __future__ import annotations

import json

import pytest


class _AcceptedPacket:
    ok = True
    packet_id = "packet-test"

    @staticmethod
    def to_meta():
        return {"ok": True}


def test_execute_or_queue_surfaces_post_commit_receipt_read_failure(monkeypatch):
    """A committed account with an unreadable outbox returns a structured hard fence."""
    from bot import settle
    from portfolio import paper_account, registry

    monkeypatch.setattr(registry, "is_archived", lambda pid: False)
    monkeypatch.setattr(
        paper_account,
        "validate_target_weights",
        lambda target, **kwargs: dict(target),
    )
    monkeypatch.setattr(paper_account, "recover_paper_transaction", lambda pid: None)
    receipt_reads = 0

    def _receipts(pid):
        nonlocal receipt_reads
        receipt_reads += 1
        if receipt_reads == 1:
            return []
        raise ValueError("corrupt receipt")

    monkeypatch.setattr(paper_account, "pending_settlement_receipts", _receipts)
    monkeypatch.setattr(
        paper_account,
        "_load_account",
        lambda pid: {"positions": {}, "cash": 1_000_000.0},
    )
    monkeypatch.setattr(
        paper_account,
        "preflight_pending_target",
        lambda pid: {"ok": True, "pending": None},
    )
    monkeypatch.setattr(
        paper_account,
        "unpriceable_target_requirements",
        lambda *args, **kwargs: {
            "tickers": [],
            "exit_tickers": [],
            "positive_target_tickers": [],
        },
    )
    monkeypatch.setattr(paper_account, "save_pending_target", lambda *a, **k: None)
    monkeypatch.setattr(paper_account, "settle_target", lambda *a, **k: {"AAPL": 0.1})

    result = settle.execute_or_queue(
        "autonomous",
        {"AAPL": 0.1},
        {"AAPL": 100.0, "SPY": 500.0},
        "2026-08-12",
        market_open=True,
        _locked=True,
    )

    assert result["skipped"] == "settlement_receipt_unreadable"
    assert result["receipt_retained"] is True
    assert "corrupt receipt" in result["error"]
    assert result["settlement_receipt_error"] == result["error"]
    assert settle.settlement_projection_block_reason(result) == "settlement_receipt_unreadable"


@pytest.mark.parametrize(
    ("book", "module_name", "ticker", "mcp_attr"),
    [
        ("autonomous", "bot.autonomous", "AAPL", "autonomous_mcp"),
        ("china", "bot.china", "600519.SS", "china_mcp"),
        ("hk", "bot.hk", "0700.HK", "hk_mcp"),
    ],
)
@pytest.mark.parametrize(
    ("state_case", "finalizes", "expected_reason"),
    [
        ("outstanding", True, "outstanding_settlement_receipt"),
        ("outstanding", False, "outstanding_settlement_receipt"),
        ("recovery_failed", None, "settlement_recovery_failed"),
        ("receipt_unreadable", None, "settlement_receipt_unreadable"),
        ("receipt_retained", None, "settlement_receipt_retained"),
        ("receipt_error", None, "settlement_receipt_unreadable"),
    ],
)
def test_regional_runner_fences_current_projection_behind_older_receipt(
    tmp_path,
    monkeypatch,
    book,
    module_name,
    ticker,
    mcp_attr,
    state_case,
    finalizes,
    expected_reason,
):
    """Unresolved settlement state can never publish mutable PM-run scratch as current."""
    import importlib

    from bot import settle
    from brain import cost_guard, portfolio_learning
    from bridge import build_portfolio
    from control_plane import packet_gate
    from data_layer import feed_health
    from portfolio import (
        advisor_trade,
        autonomous_migration,
        firm_exposure,
        fx,
        mandate_packet,
        paper_account,
        registry,
        safety,
    )

    module = importlib.import_module(module_name)
    mcp = importlib.import_module(f"brain.{mcp_attr}")
    monkeypatch.setattr(registry, "_ROOT", tmp_path / "runtime", raising=False)
    monkeypatch.setattr(module, "_has_history", lambda: False)
    monkeypatch.setattr(module, "_run_brain", lambda *a, **k: {"ok": True, "model": "test"})
    monkeypatch.setattr(mcp, "clear_submission", lambda *a, **k: None)
    submission = {
        "schema": "mastermind.target_book.v2",
        "holdings": [{"ticker": ticker, "weight": 0.10, "rationale": "test"}],
        "exit_decisions": [],
        "summary": "newer decision that must remain rejected",
        "gross": 0.10,
    }
    monkeypatch.setattr(mcp, "read_submission", lambda *a, **k: submission)
    monkeypatch.setattr(cost_guard, "over_budget", lambda *a, **k: False)
    monkeypatch.setattr(cost_guard, "record", lambda *a, **k: None)
    monkeypatch.setattr(portfolio_learning, "attach_lesson_trace", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(portfolio_learning, "refresh_post_sell", lambda *a, **k: {"summary": {}})
    monkeypatch.setattr(portfolio_learning, "derive_lessons", lambda *a, **k: {"lessons": []})
    monkeypatch.setattr(packet_gate, "process", lambda *a, **k: _AcceptedPacket())
    monkeypatch.setattr(paper_account, "_current_price", lambda *a, **k: 100.0)
    monkeypatch.setattr(paper_account, "nav", lambda *a, **k: 1_000_000.0)
    monkeypatch.setattr(feed_health, "status", lambda *a, **k: {"status": "up"})
    monkeypatch.setattr(fx, "usd_to", lambda value, currency: value)
    monkeypatch.setattr(module, "_warm_live", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(advisor_trade, "pending_proposals", lambda *a, **k: [])
    monkeypatch.setattr(autonomous_migration, "is_pending_migration", lambda: False)
    monkeypatch.setattr(firm_exposure, "caps_enabled", lambda: False)
    monkeypatch.setattr(
        safety,
        "compute_safety",
        lambda *a, **k: {"portfolio_id": book},
    )
    monkeypatch.setattr(safety, "gross_overlay", lambda *a, **k: {"gross_mult": 1.0})
    monkeypatch.setattr(safety, "persist", lambda *a, **k: None)
    monkeypatch.setattr(mandate_packet, "build", lambda *a, **k: {})
    monkeypatch.setattr(mandate_packet, "write_packet", lambda *a, **k: None)
    monkeypatch.setattr(mandate_packet, "emit_run_event", lambda *a, **k: None)

    receipt_id = "a" * 64
    settlement_result = {"executed": [], "queued": False}
    if state_case == "outstanding":
        settlement_result.update({
            "skipped": "settlement_finalization_pending",
            "outstanding_settlement_receipt_id": receipt_id,
            "receipt_retained": True,
        })
    elif state_case == "recovery_failed":
        settlement_result.update({
            "skipped": "settlement_recovery_failed",
            "error": "receipt outbox unavailable",
        })
    elif state_case == "receipt_unreadable":
        settlement_result.update({
            "skipped": "settlement_receipt_unreadable",
            "error": "receipt JSON invalid",
        })
    elif state_case == "receipt_retained":
        settlement_result.update({
            "skipped": "projection_incomplete",
            "receipt_retained": True,
        })
    else:
        settlement_result["settlement_receipt_error"] = "receipt parse failed"
    monkeypatch.setattr(
        settle,
        "execute_or_queue",
        lambda *a, **k: settlement_result,
    )
    monkeypatch.setattr(settle, "is_open", lambda *a, **k: True)
    finalized: list[tuple[str, str]] = []

    def _finalize(pid, transaction_id):
        finalized.append((pid, transaction_id))
        if finalizes:
            return {"ok": True, "receipt_acknowledged": True, "executed": [{"ticker": "OLD"}]}
        return {
            "ok": False,
            "receipt_retained": True,
            "finalization_errors": ["republish:failed"],
        }

    monkeypatch.setattr(settle, "finalize_direct_settlement_receipt", _finalize)
    side_effects: list[str] = []
    monkeypatch.setattr(
        paper_account, "mark", lambda *a, **k: side_effects.append("mark")
    )
    monkeypatch.setattr(
        build_portfolio, "write", lambda *a, **k: side_effects.append("publish")
    )
    monkeypatch.setattr(
        module, "_append_decision_log", lambda *a, **k: side_effects.append("decision")
    )
    monkeypatch.setattr(
        module, "_translate_report", lambda *a, **k: side_effects.append("translate"), raising=False
    )

    out = getattr(module, f"run_{book}")(asof="2026-08-12", armed=True)

    assert finalized == ([(book, receipt_id)] if state_case == "outstanding" else [])
    assert side_effects == []
    assert out["target_status"].startswith("rejected_")
    assert out["decision_effective"] is False
    assert out["executed"] == []  # old receipt fills never impersonate this later run
    assert out["settlement_state_blocked"] is True
    assert out["settlement_state_block_reason"] == expected_reason
    assert out["mark_skipped"] == expected_reason
    assert out["publish_skipped"] == expected_reason
    assert out["decision_log_skipped"] == expected_reason
    if state_case == "outstanding":
        assert out["outstanding_settlement_receipt_acknowledged"] is finalizes
        assert out["outstanding_settlement_receipt_retained"] is (not finalizes)
        assert out["settlement_receipt_retained"] is (not finalizes)
    elif state_case == "receipt_retained":
        assert out["settlement_receipt_retained"] is True


@pytest.mark.parametrize(
    "book_result",
    [
        {"ok": False, "skipped": "settle_failed"},
        {"ok": True, "receipt_retained": True},
        {"ok": True, "settlement_receipt_error": "receipt parse failed"},
        {"ok": True, "finalization_errors": ["republish:failed"]},
    ],
)
def test_scheduler_validator_rejects_incomplete_settlement(book_result):
    from app import scheduler

    with pytest.raises(RuntimeError, match="settle_pending incomplete"):
        scheduler._require_settlement_success(
            {"autonomous": book_result}, job="settle_pending"
        )


@pytest.mark.parametrize("skipped", ["market_closed", "nothing_queued"])
def test_scheduler_validator_accepts_normal_noop(skipped):
    from app import scheduler

    scheduler._require_settlement_success(
        {"autonomous": {"ok": False, "skipped": skipped}},
        job="settle_pending",
    )


@pytest.mark.parametrize(
    ("job_name", "settle_name", "result"),
    [
        (
            "_settle_pending_job",
            "settle_us",
            {"autonomous": {"ok": False, "receipt_retained": True}},
        ),
        (
            "_settle_brain_asia_job",
            "settle_asia",
            {
                "china": {"ok": False, "finalization_errors": ["mark:failed"]},
                "hk": {"ok": False, "skipped": "nothing_queued"},
            },
        ),
    ],
)
def test_scheduler_jobs_surface_incomplete_settlement(
    tmp_path, monkeypatch, job_name, settle_name, result
):
    from app import scheduler
    from bot import settle
    from control_plane import locks, run_events

    original_locks_dir = locks._locks_dir
    original_events_path = run_events._ledger_path
    monkeypatch.setattr(locks, "_locks_dir", lambda root=None: original_locks_dir(tmp_path))
    monkeypatch.setattr(
        run_events, "_ledger_path", lambda root=None: original_events_path(tmp_path)
    )
    statuses: list[str] = []
    monkeypatch.setattr(scheduler, "_ledger_start", lambda *a, **k: object())
    monkeypatch.setattr(
        scheduler, "_ledger_end", lambda handle, status, **kwargs: statuses.append(status)
    )
    monkeypatch.setattr(settle, settle_name, lambda: result)

    getattr(scheduler, job_name)()

    assert statuses == ["error"]
    events_path = original_events_path(tmp_path)
    events = [json.loads(line) for line in events_path.read_text().splitlines()]
    failed = [event for event in events if event.get("kind") == "step_failed"]
    assert failed and failed[-1]["severity"] == "HARD_STOP"


@pytest.mark.parametrize(
    ("job_name", "settle_name", "result"),
    [
        (
            "_settle_pending_job",
            "settle_us",
            {"autonomous": {"ok": False, "skipped": "market_closed"}},
        ),
        (
            "_settle_brain_asia_job",
            "settle_asia",
            {
                "china": {"ok": False, "skipped": "nothing_queued"},
                "hk": {"ok": False, "skipped": "market_closed"},
            },
        ),
    ],
)
def test_scheduler_jobs_keep_normal_noop_non_error(
    tmp_path, monkeypatch, job_name, settle_name, result
):
    from app import scheduler
    from bot import settle
    from control_plane import locks, run_events

    original_locks_dir = locks._locks_dir
    original_events_path = run_events._ledger_path
    monkeypatch.setattr(locks, "_locks_dir", lambda root=None: original_locks_dir(tmp_path))
    monkeypatch.setattr(
        run_events, "_ledger_path", lambda root=None: original_events_path(tmp_path)
    )
    statuses: list[str] = []
    monkeypatch.setattr(scheduler, "_ledger_start", lambda *a, **k: object())
    monkeypatch.setattr(
        scheduler, "_ledger_end", lambda handle, status, **kwargs: statuses.append(status)
    )
    monkeypatch.setattr(settle, settle_name, lambda: result)

    getattr(scheduler, job_name)()

    assert statuses == ["ok"]
    assert not original_events_path(tmp_path).exists()
