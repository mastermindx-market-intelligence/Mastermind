"""Rejected-name/off-policy ledger must be strict, atomic, and race-safe."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest


def _wire(tmp_path, monkeypatch):
    from portfolio import rejections as r
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(r, "_DIR", tmp_path)
    monkeypatch.setattr(r, "_LEDGER", ledger)
    monkeypatch.delenv("MASTERMIND_SELECTION_EXPLORE", raising=False)
    return r, ledger


def _held(ticker):
    return {"ticker": ticker, "reason": "Insufficient research conviction", "combined": 60, "confluence": 0.2}


def test_corrupt_or_wrong_shape_ledger_is_failed_evidence(tmp_path, monkeypatch):
    r, ledger = _wire(tmp_path, monkeypatch)
    ledger.write_text(json.dumps({"ticker": "GOOD", "status": "open"}) + "\n{broken\n")
    with pytest.raises(Exception):
        r._load_ledger()
    ledger.write_text(json.dumps(["wrong-shape"]) + "\n")
    with pytest.raises(Exception):
        r.summary("2026-09-17")


def test_record_refuses_corrupt_existing_ledger_without_overwrite(tmp_path, monkeypatch):
    r, ledger = _wire(tmp_path, monkeypatch)
    corrupt = '{"ticker":"OLD","status":"open"}\n{broken\n'
    ledger.write_text(corrupt)
    monkeypatch.setattr(r, "_grade", lambda *_args: None)

    with pytest.raises(Exception):
        r.record("2026-09-17", held=[_held("AAPL")])
    assert ledger.read_text() == corrupt


def test_failed_publish_preserves_prior_complete_ledger(tmp_path, monkeypatch):
    r, ledger = _wire(tmp_path, monkeypatch)
    previous = json.dumps({
        "id": "old", "ticker": "OLD", "asof": "2026-09-01", "action": "reject",
        "stage": "research_hold", "reason": "old", "score": 1, "confluence": 0.0,
        "propensity": 0.0, "policy": "deterministic", "horizon_d": 21,
        "status": "open", "realized": None, "resolved_on": None,
    }) + "\n"
    ledger.write_text(previous)
    monkeypatch.setattr(r, "_grade", lambda *_args: None)
    original_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == ledger:
            raise OSError("secret /Users/private/rejections token=do-not-return")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        r.record("2026-09-17", held=[_held("AAPL")])

    assert ledger.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_concurrent_record_serializes_read_modify_write_without_lost_names(tmp_path, monkeypatch):
    r, ledger = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(r, "_grade", lambda *_args: None)
    original_load = r._load_ledger
    gate = threading.Barrier(3)
    active_lock = threading.Lock()
    active = 0
    max_active = 0

    def slow_load():
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.15)
            return original_load()
        finally:
            with active_lock:
                active -= 1

    monkeypatch.setattr(r, "_load_ledger", slow_load)
    errors = []

    def run(ticker):
        try:
            gate.wait(timeout=5)
            r.record("2026-09-17", held=[_held(ticker)])
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=run, args=("AAPL",), name="writer-a"),
        threading.Thread(target=run, args=("MSFT",), name="writer-b"),
    ]
    for thread in threads:
        thread.start()
    gate.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert max_active == 1
    rows = [json.loads(line) for line in ledger.read_text().splitlines() if line.strip()]
    assert {row["ticker"] for row in rows} == {"AAPL", "MSFT"}
    assert len(rows) == 2


def test_empty_carried_day_remains_valid_noop(tmp_path, monkeypatch):
    r, _ = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(r, "_grade", lambda *_args: None)
    out = r.record("2026-09-17")
    assert out["n_total"] == 0
    assert r._load_ledger() == []
