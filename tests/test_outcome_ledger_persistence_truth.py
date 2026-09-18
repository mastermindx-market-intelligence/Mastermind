"""Outcome-ledger persistence must be atomic, KEEP-FIRST, and fail closed on corrupt evidence."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest


def _thesis(tid="t1", subject="NVDA"):
    return {
        "id": tid,
        "subject": subject,
        "prob_correct": 0.7,
        "lean": "add",
        "horizon_d": 21,
        "sleeve": "conviction",
        "state_asof": "2026-09-01",
        "falsifier": {"check": {"kind": "rel_return", "op": "<", "threshold": -0.05}},
    }


def _wire(tmp_path, monkeypatch):
    from brain import outcome_ledger as ol
    path = tmp_path / "outcome_ledger.jsonl"
    monkeypatch.setattr(ol, "_PATH", path)
    return ol, path


def test_malformed_row_is_failed_evidence_not_silently_dropped(tmp_path, monkeypatch):
    ol, path = _wire(tmp_path, monkeypatch)
    path.write_text(json.dumps({"thesis_id": "good", "outcome": 1, "prob_correct": 0.7}) + "\n{broken\n")

    with pytest.raises(Exception):
        ol.load()
    with pytest.raises(Exception):
        ol.summary()


def test_resolve_refuses_corrupt_existing_ledger_without_overwrite(tmp_path, monkeypatch):
    ol, path = _wire(tmp_path, monkeypatch)
    corrupt = '{"thesis_id":"old","outcome":1}\n{broken\n'
    path.write_text(corrupt)

    with pytest.raises(Exception):
        ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()])

    assert path.read_text() == corrupt


def test_failed_publish_preserves_prior_complete_ledger(tmp_path, monkeypatch):
    ol, path = _wire(tmp_path, monkeypatch)
    previous = json.dumps({"thesis_id": "old", "outcome": 1, "prob_correct": 0.7}) + "\n"
    path.write_text(previous)
    original_open = Path.open
    original_replace = os.replace

    class PartialAppend:
        def __init__(self, fh):
            self.fh = fh
        def __enter__(self):
            return self
        def write(self, _text):
            self.fh.write("{")
            self.fh.flush()
            raise OSError("secret /Users/private/outcome token=do-not-return")
        def __exit__(self, *_args):
            self.fh.close()
            return False

    def injected_open(self, mode="r", *args, **kwargs):
        if self == path and mode == "a":
            return PartialAppend(original_open(self, mode, *args, **kwargs))
        return original_open(self, mode, *args, **kwargs)

    def fail_replace(src, dst):
        if Path(dst) == path:
            raise OSError("secret /Users/private/replace token=do-not-return")
        return original_replace(src, dst)

    monkeypatch.setattr(Path, "open", injected_open)
    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()])

    assert path.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_concurrent_resolve_keeps_first_exactly_once(tmp_path, monkeypatch):
    ol, path = _wire(tmp_path, monkeypatch)
    barrier = threading.Barrier(2)
    monkeypatch.setattr(ol, "_lens_snapshot", lambda *_args: (barrier.wait(timeout=5), {})[1])

    results = []
    errors = []

    def run():
        try:
            results.append(ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()]))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(results) == [0, 1]
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["thesis_id"] == "t1"
