"""Signal history must be strict, atomic, and KEEP-FIRST under concurrency."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest


def _wire(tmp_path, monkeypatch):
    from brain import signal_history as sh
    path = tmp_path / "signals.jsonl"
    monkeypatch.setattr(sh, "_PATH", path)
    return sh, path


def test_malformed_or_wrong_shape_row_is_failed_evidence(tmp_path, monkeypatch):
    sh, path = _wire(tmp_path, monkeypatch)
    path.write_text(json.dumps({"asof": "2026-09-17", "ticker": "AAPL"}) + "\n{broken\n")
    with pytest.raises(Exception):
        sh.load()
    path.write_text(json.dumps(["wrong-shape"]) + "\n")
    with pytest.raises(Exception):
        sh.load()


def test_archive_refuses_corrupt_existing_history_without_overwrite(tmp_path, monkeypatch):
    sh, path = _wire(tmp_path, monkeypatch)
    corrupt = '{"asof":"2026-09-17","ticker":"AAPL"}\n{broken\n'
    path.write_text(corrupt)
    with pytest.raises(Exception):
        sh.archive("2026-09-17", [{"ticker": "MSFT"}])
    assert path.read_text() == corrupt


def test_failed_publish_preserves_prior_complete_history(tmp_path, monkeypatch):
    sh, path = _wire(tmp_path, monkeypatch)
    previous = json.dumps({"asof": "2026-09-16", "ticker": "AAPL"}) + "\n"
    path.write_text(previous)
    original_open = Path.open
    original_replace = os.replace

    class PartialAppend:
        def __init__(self, fh): self.fh = fh
        def __enter__(self): return self
        def write(self, _text):
            self.fh.write("{")
            self.fh.flush()
            raise OSError("secret /Users/private/signal token=do-not-return")
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
        sh.archive("2026-09-17", [{"ticker": "MSFT"}])
    assert path.read_text() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def test_concurrent_same_day_archive_keeps_first_exactly_once(tmp_path, monkeypatch):
    sh, path = _wire(tmp_path, monkeypatch)
    barrier = threading.Barrier(2)
    monkeypatch.setattr(sh, "_now_iso", lambda: (barrier.wait(timeout=5), "2026-09-17T20:00:00+00:00")[1])
    results = []
    errors = []

    def run(value):
        try:
            results.append(sh.archive("2026-09-17", [{"ticker": "NVDA", "confluence": value}]))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(v,)) for v in (0.2, 0.9)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert sorted(results) == [0, 1]
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(rows) == 1 and rows[0]["ticker"] == "NVDA"


def test_archive_argument_owns_record_asof(tmp_path, monkeypatch):
    sh, _ = _wire(tmp_path, monkeypatch)
    assert sh.archive("2026-09-17", [{"ticker": "AAPL", "asof": "1999-01-01"}]) == 1
    row = sh.load()[0]
    assert row["asof"] == "2026-09-17"


def _exercise(sh, operation):
    if operation == "load":
        return sh.load()
    if operation == "seen":
        return sh.seen_keys("2026-09-17")
    return sh.archive("2026-09-17", [{"ticker": "MSFT"}])


@pytest.mark.parametrize("operation", ["load", "seen", "archive"])
@pytest.mark.parametrize("component", ["leaf", "directory"])
def test_dangling_history_path_remains_unavailable(tmp_path, monkeypatch, operation, component):
    sh, path = _wire(tmp_path, monkeypatch)
    missing = tmp_path / "missing-target"
    link = path if component == "leaf" else tmp_path / "alias"
    if component == "directory":
        monkeypatch.setattr(sh, "_PATH", link / "signals.jsonl")
    link.symlink_to(missing, target_is_directory=component == "directory")
    original = link.lstat()

    with pytest.raises(OSError):
        _exercise(sh, operation)
    assert link.is_symlink()
    assert link.lstat().st_ino == original.st_ino
    assert link.readlink() == missing
    assert not missing.exists()


def test_first_use_and_readable_symlink(tmp_path, monkeypatch):
    sh, _ = _wire(tmp_path, monkeypatch)
    path = tmp_path / "new" / "history" / "signals.jsonl"
    monkeypatch.setattr(sh, "_PATH", path)
    assert sh.load() == []
    assert sh.seen_keys("2026-09-17") == set()
    path.parent.mkdir(parents=True)
    path.touch()
    assert sh.load() == []
    assert sh.archive("2026-09-17", [{"ticker": "MSFT"}]) == 1
    alias = tmp_path / "readable.jsonl"
    alias.symlink_to(path)
    monkeypatch.setattr(sh, "_PATH", alias)
    assert sh.seen_keys("2026-09-17") == {"MSFT"}


@pytest.mark.parametrize("operation", ["load", "seen", "archive"])
@pytest.mark.parametrize("seam", ["read_text", "lstat"])
@pytest.mark.parametrize("failure", [PermissionError(13, "fixture denied"), OSError(5, "fixture I/O error")])
def test_history_io_failure_is_never_absence(tmp_path, monkeypatch, operation, seam, failure):
    sh, path = _wire(tmp_path, monkeypatch)
    original = b'{"asof":"2026-09-16","ticker":"AAPL"}\n'
    if seam == "read_text":
        path.write_bytes(original)
    real = getattr(Path, seam)
    calls = []

    def fail_for_history(self, *args, **kwargs):
        if self == path:
            calls.append(self)
            raise failure
        return real(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, seam, fail_for_history)
        with pytest.raises(OSError) as received:
            _exercise(sh, operation)
    assert received.value is failure
    assert calls == [path]
    if seam == "read_text":
        assert path.read_bytes() == original
    else:
        assert not path.exists()
    assert not list(tmp_path.glob(".*.tmp"))
