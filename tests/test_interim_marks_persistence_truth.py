"""Interim trajectory marks must be strict, atomic, and KEEP-FIRST under concurrency."""
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
        "status": "open",
        "state_asof": "2026-09-01",
        "prob_correct": 0.7,
        "horizon_d": 21,
        "entry_levels": {"ticker": subject, "price": 100.0},
        "falsifier": {"check": {"kind": "rel_return", "op": "<", "threshold": -0.05}},
    }


def _wire(tmp_path, monkeypatch):
    from brain import interim_marks as im
    path = tmp_path / "interim_marks.jsonl"
    monkeypatch.setattr(im, "_PATH", path)
    return im, path


def test_malformed_or_wrong_shape_history_is_failed_evidence(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    path.write_text(json.dumps({"thesis_id": "good", "checkpoint": 5}) + "\n{broken\n")
    with pytest.raises(Exception):
        im.scorecard()
    path.write_text(json.dumps(["wrong-shape"]) + "\n")
    with pytest.raises(Exception):
        im.early_warnings()


def test_record_refuses_corrupt_existing_history_without_overwrite(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    corrupt = '{"thesis_id":"old","checkpoint":5}\n{broken\n'
    path.write_text(corrupt)
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis()])
    monkeypatch.setattr(im, "_mark", lambda *_args: {"resolved": True, "rel_return": 0.04, "barrier": "time"})

    with pytest.raises(Exception):
        im.record("2026-09-17")

    assert path.read_text() == corrupt


def test_failed_publish_preserves_prior_complete_history(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    previous = json.dumps({"thesis_id": "old", "subject": "OLD", "checkpoint": 5}) + "\n"
    path.write_text(previous)
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis()])
    monkeypatch.setattr(im, "_mark", lambda *_args: {"resolved": True, "rel_return": 0.04, "barrier": "time"})
    original_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == path:
            raise OSError("secret /Users/private/interim token=do-not-return")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        im.record("2026-09-17")

    assert path.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_concurrent_record_keeps_first_checkpoint_exactly_once(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(im, "_CHECKPOINTS", [5])
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis()])
    barrier = threading.Barrier(2)

    def mark(*_args):
        barrier.wait(timeout=5)
        return {"resolved": True, "rel_return": 0.04, "barrier": "time"}

    monkeypatch.setattr(im, "_mark", mark)
    results = []
    errors = []

    def run():
        try:
            results.append(im.record("2026-09-17"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(result["new"] for result in results) == [0, 1]
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["thesis_id"] == "t1" and rows[0]["checkpoint"] == 5


def test_canonical_thesis_read_failure_is_not_reported_as_zero_marks(tmp_path, monkeypatch):
    im, _ = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(im, "all_theses", lambda: (_ for _ in ()).throw(RuntimeError("ledger unavailable")))

    with pytest.raises(RuntimeError):
        im.record("2026-09-17")


def test_price_label_failure_remains_a_legitimate_noop(tmp_path, monkeypatch):
    im, _ = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis()])
    monkeypatch.setattr(im, "_mark", lambda *_args: None)

    assert im.record("2026-09-17") == {"n_marks": 0, "new": 0}
