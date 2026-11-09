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
    monkeypatch.setattr(ol, "_lens_snapshot", lambda *_args: {})
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


def test_genuine_absence_can_publish_once_without_regrading(tmp_path, monkeypatch):
    ol, path = _wire(tmp_path, monkeypatch)

    assert ol.load() == []
    assert ol.summary()["status"] == "building"
    assert ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()]) == 1
    first = path.read_bytes()
    assert ol.resolve("2026-09-18", {"t1": -0.20}, theses=[_thesis()]) == 0
    assert path.read_bytes() == first
    assert ol.summary()["n"] == 1
    assert ol.load()[0]["outcome"] == 1


@pytest.mark.parametrize("operation", ["load", "summary", "resolve"])
def test_dangling_outcome_entry_is_not_absent(tmp_path, monkeypatch, operation):
    ol, path = _wire(tmp_path, monkeypatch)
    missing = tmp_path / "missing-outcome-target.jsonl"
    path.symlink_to(missing)

    with pytest.raises(OSError):
        if operation == "resolve":
            ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()])
        else:
            getattr(ol, operation)()

    assert path.is_symlink()
    assert path.readlink() == missing
    assert not missing.exists()


@pytest.mark.parametrize("operation", ["load", "summary", "resolve"])
def test_unavailable_stat_preserves_existing_outcome_evidence(
    tmp_path, monkeypatch, operation
):
    ol, path = _wire(tmp_path, monkeypatch)
    previous = '{"thesis_id":"old","outcome":1,"prob_correct":0.7}\n'
    path.write_text(previous)
    original_stat = Path.stat
    original_lstat = Path.lstat

    def unavailable_stat(self, *args, **kwargs):
        if self == path:
            raise OSError("canonical outcome stat unavailable")
        return original_stat(self, *args, **kwargs)

    def unavailable_lstat(self, *args, **kwargs):
        if self == path:
            raise OSError("canonical outcome stat unavailable")
        return original_lstat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", unavailable_stat)
    monkeypatch.setattr(Path, "lstat", unavailable_lstat)

    with pytest.raises(OSError, match="canonical outcome stat unavailable"):
        if operation == "resolve":
            ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()])
        else:
            getattr(ol, operation)()

    assert path.read_text() == previous


@pytest.mark.parametrize("operation", ["load", "summary", "resolve"])
def test_unavailable_read_preserves_existing_outcome_evidence(
    tmp_path, monkeypatch, operation
):
    ol, path = _wire(tmp_path, monkeypatch)
    previous = b'{"thesis_id":"old","outcome":1,"prob_correct":0.7}\n'
    path.write_bytes(previous)
    original_open = Path.open

    def unavailable_open(self, mode="r", *args, **kwargs):
        if self == path and mode == "r":
            raise OSError("canonical outcome read unavailable")
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unavailable_open)

    with pytest.raises(OSError, match="canonical outcome read unavailable"):
        if operation == "resolve":
            ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()])
        else:
            getattr(ol, operation)()

    assert path.read_bytes() == previous


def _lock_cleanup_fault(monkeypatch, ol, fault):
    if fault == "unlock":
        original_flock = ol.fcntl.flock

        def fail_unlock(fd, mode):
            if mode == ol.fcntl.LOCK_UN:
                raise OSError("outcome unlock cleanup")
            return original_flock(fd, mode)

        monkeypatch.setattr(ol.fcntl, "flock", fail_unlock)
        return

    original_open = Path.open

    class FailingClose:
        def __init__(self, wrapped):
            self.wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self.wrapped, name)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()
            return False

        def close(self):
            self.wrapped.close()
            raise OSError("outcome close cleanup")

    def open_with_cleanup_fault(self, *args, **kwargs):
        opened = original_open(self, *args, **kwargs)
        return FailingClose(opened) if self == ol._lock_path() else opened

    monkeypatch.setattr(Path, "open", open_with_cleanup_fault)


@pytest.mark.parametrize("fault", ["unlock", "close"])
@pytest.mark.parametrize("existing", [False, True])
def test_lock_cleanup_preserves_resolution_or_duplicate_result(
    tmp_path, monkeypatch, fault, existing
):
    ol, path = _wire(tmp_path, monkeypatch)
    if existing:
        assert ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()]) == 1
        previous = path.read_bytes()
    _lock_cleanup_fault(monkeypatch, ol, fault)

    assert ol.resolve("2026-09-18", {"t1": -0.20}, theses=[_thesis()]) == (0 if existing else 1)
    rows = ol.load()
    assert len(rows) == 1
    assert rows[0]["outcome"] == (1 if existing else 0)
    if existing:
        assert path.read_bytes() == previous


def test_lock_close_cleanup_does_not_mask_primary_publish_failure(tmp_path, monkeypatch):
    ol, path = _wire(tmp_path, monkeypatch)
    previous = '{"thesis_id":"old","outcome":1,"prob_correct":0.7}\n'
    path.write_text(previous)
    _lock_cleanup_fault(monkeypatch, ol, "close")
    primary = OSError("primary outcome replacement failure")

    def fail_replace(_src, _dst):
        raise primary

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError) as caught:
        ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()])

    assert caught.value is primary
    assert path.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_lock_close_cleanup_does_not_mask_acquisition_failure(tmp_path, monkeypatch):
    ol, path = _wire(tmp_path, monkeypatch)
    _lock_cleanup_fault(monkeypatch, ol, "close")
    primary = OSError("primary outcome lock acquisition failure")
    original_flock = ol.fcntl.flock

    def fail_acquire(fd, mode):
        if mode == ol.fcntl.LOCK_EX:
            raise primary
        return original_flock(fd, mode)

    monkeypatch.setattr(ol.fcntl, "flock", fail_acquire)

    with pytest.raises(OSError) as caught:
        ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()])

    assert caught.value is primary
    assert not path.exists()


def test_process_lock_serializes_independent_outcome_resolvers(tmp_path, monkeypatch):
    import fcntl
    import multiprocessing as mp

    ol, path = _wire(tmp_path, monkeypatch)
    ctx = mp.get_context("fork")
    entered, attempting, release = ctx.Event(), ctx.Event(), ctx.Event()
    contended = ctx.Value("b", False)
    committed = ctx.Value("i", -1)
    completed_after_release = ctx.Value("b", False)

    def holder():
        with ol._ledger_lock():
            entered.set()
            assert release.wait(timeout=5)

    def waiter():
        assert entered.wait(timeout=5)
        with ol._lock_path().open("a+", encoding="utf-8") as probe:
            try:
                fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                contended.value = True
            else:
                fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        attempting.set()
        committed.value = ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()])
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
    assert committed.value == 1
    assert bool(completed_after_release.value) is True
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["thesis_id"] == "t1"


def test_current_thesis_owner_resolves_to_unchanged_reliability_consumers(
    tmp_path, monkeypatch
):
    from brain import ledger

    ol, path = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(ledger, "_LEDGER", tmp_path / "theses.jsonl")
    monkeypatch.setattr(ol, "_lens_snapshot", lambda *_args: {
        "lens_dirs": {"trend": "bull"},
        "confluence": 0.5,
        "size_authority": "up",
        "quad": "Q1",
    })

    assert ledger.append(_thesis()) is True
    assert ol.resolve("2026-09-17", {"t1": 0.10}) == 1
    first = path.read_bytes()
    assert ol.resolve("2026-09-18", {"t1": -0.20}) == 0
    assert path.read_bytes() == first
    summary = ol.summary()
    assert summary["n"] == 1 and summary["hits"] == 1
    assert summary["status"] == "scoring"
    assert summary["brier"] == 0.09
    assert ol.reliability_curve() == [
        {"bin": "0.60-0.80", "n": 1, "mean_predicted": 0.7, "hit_rate": 1.0},
    ]
    assert ol.lens_edge() == [
        {"lens": "trend", "direction": "bull", "n": 1, "hit_rate": 1.0},
    ]
    assert ol.lens_weights() == {}
