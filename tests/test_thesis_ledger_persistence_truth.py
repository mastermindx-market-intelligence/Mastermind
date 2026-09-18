"""The thesis accountability ledger is serialized and atomically replaced."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest


def _wire(monkeypatch, ledger, tmp_path):
    path = tmp_path / "theses.jsonl"
    monkeypatch.setattr(ledger, "_LEDGER", path)
    return path


def _row(subject="NVDA", ident="d1", status="open"):
    return {"id": ident, "subject": subject, "lean": "add", "status": status}


def test_concurrent_same_subject_append_has_one_winner(tmp_path, monkeypatch):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    barrier = threading.Barrier(2)
    original_open_subjects = ledger.open_subjects

    # Force the historical read-then-append implementation to let both callers observe the
    # same empty pre-state. The repaired implementation owns the check inside its ledger lock
    # and therefore never calls this externally-racy helper from append().
    def synchronized_open_subjects():
        seen = original_open_subjects()
        barrier.wait(timeout=5)
        return seen

    monkeypatch.setattr(ledger, "open_subjects", synchronized_open_subjects)
    results = []
    errors = []

    def worker(ident):
        try:
            results.append(ledger.append({"id": ident, "subject": "NVDA", "lean": "add"}))
        except Exception as exc:  # pragma: no cover - surfaced by assertion below
            errors.append(exc)

    a = threading.Thread(target=worker, args=("d1",))
    b = threading.Thread(target=worker, args=("d2",))
    a.start(); b.start(); a.join(timeout=10); b.join(timeout=10)

    assert errors == []
    assert sorted(results) == [False, True]
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1 and rows[0]["subject"] == "NVDA"


def test_failed_append_replace_preserves_previous_complete_ledger(tmp_path, monkeypatch):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    previous = json.dumps(_row()) + "\n"
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
            raise OSError("simulated partial append")
        def __exit__(self, *_args):
            self.fh.close()
            return False

    def injected_open(self, mode="r", *args, **kwargs):
        if self == path and mode == "a":
            return PartialAppend(original_open(self, mode, *args, **kwargs))
        return original_open(self, mode, *args, **kwargs)

    def fail_replace(src, dst):
        if Path(dst) == path:
            raise OSError("simulated atomic replace refusal")
        return original_replace(src, dst)

    monkeypatch.setattr(Path, "open", injected_open)
    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        ledger.append({"id": "d2", "subject": "MSFT", "lean": "add"})

    assert path.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_failed_close_replace_preserves_previous_open_state(tmp_path, monkeypatch):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    previous = json.dumps(_row()) + "\n"
    path.write_text(previous)
    original_write_text = Path.write_text
    original_replace = os.replace

    def partial_direct_rewrite(self, text, *args, **kwargs):
        if self == path:
            original_write_text(self, "{", *args, **kwargs)
            raise OSError("simulated partial close rewrite")
        return original_write_text(self, text, *args, **kwargs)

    def fail_replace(src, dst):
        if Path(dst) == path:
            raise OSError("simulated atomic replace refusal")
        return original_replace(src, dst)

    monkeypatch.setattr(Path, "write_text", partial_direct_rewrite)
    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        ledger.close("NVDA", "exited")

    assert path.read_text() == previous
    assert ledger.all_theses()[0]["status"] == "open"
    assert not list(tmp_path.glob(".*.tmp"))


def test_malformed_ledger_blocks_append_without_rewriting_evidence(tmp_path, monkeypatch):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    raw = json.dumps(_row()) + "\n{"  # existing corrupt evidence must not be silently repaired here
    path.write_text(raw)

    with pytest.raises(json.JSONDecodeError):
        ledger.append({"id": "d2", "subject": "MSFT", "lean": "add"})

    assert path.read_text() == raw


def test_append_close_roundtrip_semantics_unchanged(tmp_path, monkeypatch):
    from brain import ledger

    _wire(monkeypatch, ledger, tmp_path)
    assert ledger.append({"id": "d1", "subject": "NVDA", "lean": "add"}) is True
    assert ledger.append({"id": "d2", "subject": "NVDA", "lean": "add"}) is False
    assert ledger.append({"id": "d3", "subject": "MSFT", "lean": "add"}) is True
    assert ledger.open_subjects() == {"NVDA", "MSFT"}

    assert ledger.close("NVDA", "exited", outcome=0, realized=-0.04) == 1
    by_subject = {row["subject"]: row for row in ledger.all_theses()}
    assert by_subject["NVDA"]["status"] == "exited"
    assert by_subject["NVDA"]["outcome"] == 0
    assert by_subject["NVDA"]["realized"] == -0.04
    assert by_subject["MSFT"]["status"] == "open"
    assert ledger.append({"id": "d4", "subject": "NVDA", "lean": "watch"}) is True
