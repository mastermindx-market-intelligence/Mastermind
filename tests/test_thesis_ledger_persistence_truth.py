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


@pytest.mark.parametrize("operation", ["read", "append", "close"])
def test_dangling_thesis_ledger_is_not_absent(tmp_path, monkeypatch, operation):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    missing = tmp_path / "missing-theses.jsonl"
    path.symlink_to(missing)

    with pytest.raises(FileNotFoundError):
        if operation == "read":
            ledger.all_theses()
        elif operation == "append":
            ledger.append(_row())
        else:
            ledger.close("NVDA", "exited")

    assert path.is_symlink()
    assert path.readlink() == missing
    assert not missing.exists()


def test_unavailable_stat_cannot_replace_retained_ledger(tmp_path, monkeypatch):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    previous = json.dumps(_row()) + "\n"
    path.write_text(previous)
    real_exists, real_lstat = Path.exists, Path.lstat

    def unavailable_exists(self):
        return False if self == path else real_exists(self)

    def unavailable_lstat(self, *args, **kwargs):
        if self == path:
            raise PermissionError("canonical stat unavailable")
        return real_lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", unavailable_exists)
    monkeypatch.setattr(Path, "lstat", unavailable_lstat)

    with pytest.raises(PermissionError, match="canonical stat unavailable"):
        ledger.append(_row("MSFT", "d2"))

    assert path.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("row", [None, [], 7, "not-a-row"])
def test_nonmapping_thesis_evidence_is_failed_at_reader(tmp_path, monkeypatch, row):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    previous = json.dumps(_row()) + "\n" + json.dumps(row) + "\n"
    path.write_text(previous)

    with pytest.raises(ValueError, match="rows must be mappings"):
        ledger.all_theses()

    assert path.read_text() == previous


def _lock_cleanup_fault(monkeypatch, ledger, cleanup):
    original_open = Path.open
    original_flock = ledger.fcntl.flock
    faults = []

    class LockFile:
        def __init__(self, handle):
            self.handle = handle

        def fileno(self):
            return self.handle.fileno()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()
            return False

        def close(self):
            self.handle.close()
            if cleanup == "close":
                faults.append("close")
                raise OSError("lock descriptor cleanup failed")

    def open_lock(self, mode="r", *args, **kwargs):
        handle = original_open(self, mode, *args, **kwargs)
        return LockFile(handle) if self == ledger._lock_path() else handle

    def flock(fd, operation):
        if cleanup == "unlock" and operation == ledger.fcntl.LOCK_UN:
            faults.append("unlock")
            raise OSError("lock unlock cleanup failed")
        return original_flock(fd, operation)

    monkeypatch.setattr(Path, "open", open_lock)
    monkeypatch.setattr(ledger.fcntl, "flock", flock)
    return faults


@pytest.mark.parametrize("operation,cleanup", [
    ("append", "unlock"), ("append", "close"), ("close", "unlock"), ("close", "close"),
])
def test_lock_cleanup_preserves_committed_result(tmp_path, monkeypatch, operation, cleanup):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    if operation == "close":
        path.write_text(json.dumps(_row()) + "\n")
    faults = _lock_cleanup_fault(monkeypatch, ledger, cleanup)

    if operation == "append":
        assert ledger.append(_row()) is True
        assert ledger.all_theses() == [_row()]
    else:
        assert ledger.close("NVDA", "exited", outcome=1, realized=0.04) == 1
        assert ledger.all_theses() == [{**_row(status="exited"), "outcome": 1, "realized": 0.04}]

    assert faults == [cleanup]
    # The underlying descriptor has closed; a subsequent mutation can acquire the same lock.
    assert ledger.append(_row("MSFT", "d2")) is True
    assert len(ledger.all_theses()) == 2
    assert faults == [cleanup, cleanup]
    assert not list(tmp_path.glob(".*.tmp"))


def test_lock_cleanup_does_not_mask_primary_replace_failure(tmp_path, monkeypatch):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    previous = json.dumps(_row()) + "\n"
    path.write_text(previous)
    faults = _lock_cleanup_fault(monkeypatch, ledger, "close")
    original_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == path:
            raise OSError("canonical replace failed")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="canonical replace failed"):
        ledger.append(_row("MSFT", "d2"))

    assert faults == ["close"]
    assert path.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_lock_cleanup_does_not_mask_acquisition_failure(tmp_path, monkeypatch):
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    previous = json.dumps(_row()) + "\n"
    path.write_text(previous)
    faults = _lock_cleanup_fault(monkeypatch, ledger, "close")
    original_flock = ledger.fcntl.flock

    def fail_acquire(fd, operation):
        if operation == ledger.fcntl.LOCK_EX:
            raise PermissionError("lock acquisition refused")
        return original_flock(fd, operation)

    monkeypatch.setattr(ledger.fcntl, "flock", fail_acquire)

    with pytest.raises(PermissionError, match="lock acquisition refused"):
        ledger.append(_row("MSFT", "d2"))

    assert faults == ["close"]
    assert path.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_process_lock_serializes_independent_ledger_writers(tmp_path, monkeypatch):
    import fcntl
    import multiprocessing as mp
    from brain import ledger

    path = _wire(monkeypatch, ledger, tmp_path)
    ctx = mp.get_context("fork")
    entered, attempting, release = ctx.Event(), ctx.Event(), ctx.Event()
    contended, committed, completed_after_release = ctx.Value("b", False), ctx.Value("b", False), ctx.Value("b", False)

    def holder():
        with ledger._ledger_lock():
            entered.set()
            assert release.wait(timeout=5)

    def waiter():
        assert entered.wait(timeout=5)
        with ledger._lock_path().open("a+", encoding="utf-8") as probe:
            try:
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                contended.value = True
            else:
                fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        attempting.set()
        committed.value = ledger.append(_row())
        completed_after_release.value = release.is_set()

    first, second = ctx.Process(target=holder), ctx.Process(target=waiter)
    try:
        first.start()
        assert entered.wait(timeout=5)
        second.start()
        assert attempting.wait(timeout=5)
        assert bool(contended.value), "independent process must observe the held OS lock"
        assert first.pid != second.pid and os.getpid() not in (first.pid, second.pid)
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)

    assert first.exitcode == 0 and second.exitcode == 0
    assert bool(committed.value) is True
    assert bool(completed_after_release.value) is True
    assert [json.loads(line) for line in path.read_text().splitlines()] == [_row()]


def test_actual_research_ingestion_preserves_one_open_thesis_and_reentry(tmp_path, monkeypatch):
    from brain import ledger
    from brain import research_desk as rd
    from portfolio import lenses

    _wire(monkeypatch, ledger, tmp_path)
    proposals = tmp_path / "proposals.jsonl"
    monkeypatch.setattr(rd, "_PROPOSALS", proposals)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: {
        "rows": [], "synthesis": {"size_authority": "up", "vetoes": []},
    })

    def ingest(thesis, day):
        proposals.write_text(json.dumps({
            "subject": "NVDA", "lean": "add", "conviction": "high", "prob_correct": 0.75,
            "horizon_d": 21, "thesis": thesis, "evidence": ["private:e1"], "status": "proposed",
        }) + "\n")
        return rd.ingest_proposals(asof=day)

    first = ingest("first", "2026-09-17")
    duplicate = ingest("another still-open proposal", "2026-09-18")
    assert first["theses"][0]["appended"] is True
    assert duplicate["theses"][0]["appended"] is False
    assert len(ledger.all_theses()) == 1
    assert ledger.all_theses()[0]["falsifier"]["check"]["kind"] == "rel_return"
    assert ledger.close("NVDA", "exited", outcome=1, realized=0.04) == 1
    reopened = ingest("fresh thesis after exit", "2026-09-19")
    assert reopened["theses"][0]["appended"] is True
    rows = ledger.all_theses()
    assert len(rows) == 2
    assert rows[0]["status"] == "exited" and rows[0]["outcome"] == 1 and rows[0]["realized"] == 0.04
    assert rows[1]["status"] == "open" and rows[1]["thesis"] == "fresh thesis after exit"
    assert rows[0]["id"] != rows[1]["id"]
    assert ledger.open_subjects() == {"NVDA"}


@pytest.mark.parametrize("boundary", ["cleanup", "replace"])
def test_actual_ingestion_keeps_publication_truth_across_cleanup_fault(tmp_path, monkeypatch, boundary):
    from brain import ledger
    from brain import research_desk as rd
    from portfolio import lenses

    path = _wire(monkeypatch, ledger, tmp_path)
    prior_ledger = json.dumps(_row("MSFT", "earlier")) + "\n"
    path.write_text(prior_ledger)
    proposals = tmp_path / "proposals.jsonl"
    proposal = {"subject": "NVDA", "lean": "add", "conviction": "high", "prob_correct": 0.75,
                "horizon_d": 21, "thesis": "fresh", "evidence": ["private:e1"], "status": "proposed"}
    prior_proposals = json.dumps(proposal) + "\n"
    proposals.write_text(prior_proposals)
    monkeypatch.setattr(rd, "_PROPOSALS", proposals)
    monkeypatch.setattr(lenses, "full", lambda *_a, **_k: {
        "rows": [], "synthesis": {"size_authority": "up", "vetoes": []},
    })
    faults = _lock_cleanup_fault(monkeypatch, ledger, "close")
    original_replace = os.replace

    def replace(src, dst):
        if boundary == "replace" and Path(dst) == path:
            raise OSError("canonical replace failed")
        return original_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace)

    if boundary == "replace":
        with pytest.raises(OSError, match="canonical replace failed"):
            rd.ingest_proposals(asof="2026-09-17")
        assert path.read_text() == prior_ledger
        assert proposals.read_text() == prior_proposals
    else:
        out = rd.ingest_proposals(asof="2026-09-17")
        assert out["theses"][0]["appended"] is True
        rows = ledger.all_theses()
        assert len(rows) == 2
        assert rows[0] == _row("MSFT", "earlier")
        assert rows[1]["subject"] == "NVDA" and rows[1]["status"] == "open"
        assert json.loads(proposals.read_text())["status"] == "ingested"
    assert faults == ["close"]
    assert not list(tmp_path.glob(".*.tmp"))
