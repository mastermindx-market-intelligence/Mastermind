"""Held-risk outcome persistence must be strict, atomic, and KEEP-FIRST."""
from __future__ import annotations

import json
import os
import threading
from datetime import date
from pathlib import Path

import pytest


def _alert(alert_id="alert-1", ticker="AAPL"):
    return {
        "alert_id": alert_id,
        "ticker": ticker,
        "type": "monitor",
        "ts": "2026-08-01",
        "lanes": ["macro_sensitivity"],
    }


def _wire(tmp_path, monkeypatch):
    from portfolio import held_risk_outcomes as hro
    alerts = tmp_path / "alerts.jsonl"
    outcomes = tmp_path / "outcomes.jsonl"
    monkeypatch.setattr(hro, "_ALERTS_PATH", alerts)
    monkeypatch.setattr(hro, "_OUTCOMES_PATH", outcomes)
    monkeypatch.setattr(hro, "_HORIZONS", [5])
    return hro, alerts, outcomes


def _write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_corrupt_outcome_ledger_is_failed_evidence_not_silently_dropped(tmp_path, monkeypatch):
    hro, alerts, outcomes = _wire(tmp_path, monkeypatch)
    _write_jsonl(alerts, [_alert()])
    corrupt = json.dumps({"alert_id": "old", "horizon": 5}) + "\n{broken\n"
    outcomes.write_text(corrupt)
    monkeypatch.setattr(hro, "_grade_outcome", lambda *_args, **_kwargs: (100.0, 105.0, False))

    with pytest.raises(Exception):
        hro.append_outcomes(today=date(2026, 9, 17))

    assert outcomes.read_text() == corrupt


def test_corrupt_alert_ledger_is_failed_evidence_not_empty_input(tmp_path, monkeypatch):
    hro, alerts, _ = _wire(tmp_path, monkeypatch)
    alerts.write_text(json.dumps(_alert("good")) + "\n{broken\n")

    with pytest.raises(Exception):
        hro.append_outcomes(today=date(2026, 9, 17))


def test_failed_atomic_publish_preserves_prior_complete_outcomes(tmp_path, monkeypatch):
    hro, alerts, outcomes = _wire(tmp_path, monkeypatch)
    _write_jsonl(alerts, [_alert()])
    previous = json.dumps({
        "alert_id": "old", "ticker": "MSFT", "horizon": 5,
        "fwd_return_pct": 2.0, "graded_at": "2026-09-16",
    }) + "\n"
    outcomes.write_text(previous)
    monkeypatch.setattr(hro, "_grade_outcome", lambda *_args, **_kwargs: (100.0, 105.0, False))
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == outcomes:
            raise OSError("secret /Users/private/held-risk token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        hro.append_outcomes(today=date(2026, 9, 17))

    assert outcomes.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_concurrent_same_alert_grades_exactly_once(tmp_path, monkeypatch):
    hro, alerts, outcomes = _wire(tmp_path, monkeypatch)
    _write_jsonl(alerts, [_alert()])
    barrier = threading.Barrier(2)

    def grade(*_args, **_kwargs):
        barrier.wait(timeout=5)
        return 100.0, 105.0, False

    monkeypatch.setattr(hro, "_grade_outcome", grade)
    results = []
    errors = []

    def run():
        try:
            results.append(hro.append_outcomes(today=date(2026, 9, 17)))
        except Exception as exc:  # pragma: no cover - assertion below reports it
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(results) == [0, 1]
    rows = [json.loads(line) for line in outcomes.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["alert_id"] == "alert-1" and rows[0]["horizon"] == 5


def test_missing_forward_price_remains_legitimate_noop(tmp_path, monkeypatch):
    hro, alerts, outcomes = _wire(tmp_path, monkeypatch)
    _write_jsonl(alerts, [_alert()])
    monkeypatch.setattr(hro, "_grade_outcome", lambda *_args, **_kwargs: (None, None, False))

    assert hro.append_outcomes(today=date(2026, 9, 17)) == 0
    assert not outcomes.exists()


def test_outcome_lock_serializes_independent_processes(tmp_path, monkeypatch):
    """The canonical lock is process-visible, not only protected by the local RLock."""
    import multiprocessing as mp
    import time

    hro, _, _ = _wire(tmp_path, monkeypatch)
    ctx = mp.get_context("fork")
    entered = ctx.Event()
    release = ctx.Event()
    acquired_after_release = ctx.Value("b", False)

    def holder():
        with hro._outcomes_lock():
            entered.set()
            release.wait(timeout=5)

    def waiter():
        entered.wait(timeout=5)
        with hro._outcomes_lock():
            acquired_after_release.value = release.is_set()

    first = ctx.Process(target=holder)
    second = ctx.Process(target=waiter)
    first.start()
    assert entered.wait(timeout=5)
    second.start()
    time.sleep(0.15)
    assert second.is_alive(), "second process should be blocked on the held file lock"
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert first.exitcode == 0
    assert second.exitcode == 0
    assert bool(acquired_after_release.value) is True
