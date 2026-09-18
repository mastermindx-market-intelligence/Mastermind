"""Universe prediction ledger must be strict, atomic, and race-safe."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest


def _wire(tmp_path, monkeypatch):
    from portfolio import predictions as p
    ledger = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(p, "_PRED_DIR", tmp_path)
    monkeypatch.setattr(p, "_LEDGER", ledger)
    return p, ledger


def _u(ticker):
    return {"ticker": ticker, "dir": "up", "score": 40, "band": "high", "price": 100.0}


def test_corrupt_or_wrong_shape_ledger_is_failed_evidence(tmp_path, monkeypatch):
    p, ledger = _wire(tmp_path, monkeypatch)
    ledger.write_text(json.dumps({"ticker": "GOOD", "status": "open"}) + "\n{broken\n")
    with pytest.raises(Exception):
        p._load_ledger()
    ledger.write_text(json.dumps(["wrong-shape"]) + "\n")
    with pytest.raises(Exception):
        p.summary("2026-09-17")


def test_record_refuses_corrupt_existing_ledger_without_overwrite(tmp_path, monkeypatch):
    p, ledger = _wire(tmp_path, monkeypatch)
    corrupt = '{"ticker":"OLD","status":"open"}\n{broken\n'
    ledger.write_text(corrupt)
    monkeypatch.setattr(p, "universe", lambda: [_u("AAPL")])
    monkeypatch.setattr(p, "_load_panel", lambda: None)
    monkeypatch.setattr(p, "_spy_series", lambda: None)

    with pytest.raises(Exception):
        p.record("2026-09-17")
    assert ledger.read_text() == corrupt


def test_failed_publish_preserves_prior_complete_ledger(tmp_path, monkeypatch):
    p, ledger = _wire(tmp_path, monkeypatch)
    previous = json.dumps({
        "id": "old", "ticker": "OLD", "asof": "2026-09-01", "dir": "up", "score": 1,
        "band": "neutral", "prob": 0.5, "entry_px": 10.0, "horizon_d": 21,
        "status": "open", "realized": None, "resolved_on": None,
    }) + "\n"
    ledger.write_text(previous)
    monkeypatch.setattr(p, "_HORIZONS", [21])
    monkeypatch.setattr(p, "universe", lambda: [_u("AAPL")])
    monkeypatch.setattr(p, "_load_panel", lambda: None)
    monkeypatch.setattr(p, "_spy_series", lambda: None)
    original_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == ledger:
            raise OSError("secret /Users/private/predictions token=do-not-return")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        p.record("2026-09-17")

    assert ledger.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_concurrent_record_serializes_read_modify_write_without_lost_names(tmp_path, monkeypatch):
    p, ledger = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(p, "_HORIZONS", [21])
    monkeypatch.setattr(p, "_load_panel", lambda: None)
    monkeypatch.setattr(p, "_spy_series", lambda: None)
    monkeypatch.setattr(p, "universe", lambda: [_u("AAPL" if threading.current_thread().name == "writer-a" else "MSFT")])

    original_load = p._load_ledger
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

    monkeypatch.setattr(p, "_load_ledger", slow_load)
    results = []
    errors = []

    def run():
        try:
            gate.wait(timeout=5)
            results.append(p.record("2026-09-17"))
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=run, name="writer-a"),
        threading.Thread(target=run, name="writer-b"),
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
    assert len(results) == 2


def test_missing_ledger_and_empty_universe_remain_valid_noop(tmp_path, monkeypatch):
    p, ledger = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(p, "universe", lambda: [])
    monkeypatch.setattr(p, "_load_panel", lambda: None)
    monkeypatch.setattr(p, "_spy_series", lambda: None)

    out = p.record("2026-09-17")
    assert out["n_total"] == 0
    assert p._load_ledger() == []
