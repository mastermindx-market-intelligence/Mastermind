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
    path.write_text(json.dumps(_row(tid="good")) + "\n{broken\n")
    with pytest.raises(Exception):
        im.scorecard()
    path.write_text(json.dumps(["wrong-shape"]) + "\n")
    with pytest.raises(Exception):
        im.early_warnings()


def test_record_refuses_corrupt_existing_history_without_overwrite(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    corrupt = json.dumps(_row()) + "\n{broken\n"
    path.write_text(corrupt)
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis()])
    monkeypatch.setattr(im, "_mark", lambda *_args: {"resolved": True, "rel_return": 0.04, "barrier": "time"})

    with pytest.raises(Exception):
        im.record("2026-09-17")

    assert path.read_text() == corrupt


def test_failed_publish_preserves_prior_complete_history(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    previous = json.dumps(_row()) + "\n"
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


# The core below is consumed by KEEP-FIRST, scoring and warning identity.  The
# remaining writer metadata is deliberately optional for legacy row compatibility.
def _row(tid="old", subject="OLD", checkpoint=5, rel=0.0, **extra):
    return {
        "thesis_id": tid, "subject": subject, "checkpoint": checkpoint,
        "rel_return": rel, "falsified_so_far": rel < -0.05,
        "underwater": rel <= -0.03, **extra,
    }


def _put(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.mark.parametrize("field", [
    "thesis_id", "subject", "checkpoint", "rel_return",
    "falsified_so_far", "underwater",
])
def test_missing_core_evidence_never_becomes_a_healthy_row(tmp_path, monkeypatch, field):
    im, path = _wire(tmp_path, monkeypatch)
    row = _row()
    del row[field]
    _put(path, [row])
    with pytest.raises(ValueError):
        im.summary()


@pytest.mark.parametrize("field,value", [
    ("thesis_id", ""), ("thesis_id", None), ("thesis_id", 1),
    ("subject", None), ("subject", 1),
    ("checkpoint", True), ("checkpoint", 5.0), ("checkpoint", "5"),
    ("checkpoint", 0), ("checkpoint", 21),
    ("rel_return", True), ("rel_return", None), ("rel_return", "0"),
    ("rel_return", float("nan")), ("rel_return", float("inf")),
    ("rel_return", -float("inf")),
    ("falsified_so_far", 0), ("falsified_so_far", "false"),
    ("falsified_so_far", None), ("underwater", 0),
    ("underwater", "false"), ("underwater", None),
])
def test_invalid_core_values_fail_closed(tmp_path, monkeypatch, field, value):
    im, path = _wire(tmp_path, monkeypatch)
    row = _row()
    row[field] = value
    _put(path, [row])
    with pytest.raises(ValueError):
        im._load()


@pytest.mark.parametrize("raw", [
    "{}\n", "[]\n", "null\n", "false\n", "7\n", '"text"\n',
    '{"thesis_id":"x","subject":"","checkpoint":5,"rel_return":1e999,'
    '"falsified_so_far":false,"underwater":false}\n',
])
def test_wrong_shape_and_overflow_json_are_unavailable(tmp_path, monkeypatch, raw):
    im, path = _wire(tmp_path, monkeypatch)
    path.write_text(raw)
    with pytest.raises(ValueError):
        im._load()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_extension_metadata_is_not_strict_json(tmp_path, monkeypatch, value):
    im, path = _wire(tmp_path, monkeypatch)
    _put(path, [_row(extra={"nested": [value]})])
    with pytest.raises(ValueError):
        im._load()


@pytest.mark.parametrize("contents", [None, "", " \n\n\t\n"])
def test_genuine_missing_or_empty_history(tmp_path, monkeypatch, contents):
    im, path = _wire(tmp_path, monkeypatch)
    if contents is not None:
        path.write_text(contents)
    assert im._load() == []
    assert im.summary()["scorecard"]["n_marks"] == 0
    assert im.early_warnings() == []


def test_zero_optional_metadata_and_extensions_survive_append(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    prior = [
        _row(tid="  exact id  ", subject="", checkpoint=10, rel=0),
        _row(tid="nullable", barrier=None, prob_correct=None, horizon_d=None,
             recorded_at=None, entry_date="", extension={"keep": [0, None, "yes"]}),
    ]
    _put(path, prior)
    monkeypatch.setattr(im, "_CHECKPOINTS", [5])
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis("fresh")])
    monkeypatch.setattr(im, "_mark", lambda *_: {"resolved": True, "rel_return": 0})
    assert im.record("2026-09-17") == {"n_marks": 3, "new": 1}
    rows = im._load()
    assert rows[:2] == prior
    assert rows[2]["rel_return"] == 0
    assert rows[2]["falsified_so_far"] is False
    assert rows[2]["underwater"] is False
    assert im.scorecard()["by_checkpoint"]["5"]["avg_rel"] == 0


def test_duplicate_existing_checkpoints_refuse_the_whole_ledger(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    _put(path, [_row(rel=0.04), _row(rel=-0.09)])
    previous = path.read_bytes()
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis()])
    with pytest.raises(ValueError):
        im.record("2026-09-17")
    assert path.read_bytes() == previous


def test_read_is_direct_and_only_file_not_found_means_empty(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    original_read = Path.read_text
    seen = []

    def read(target, *args, **kwargs):
        if target == path:
            seen.append(target)
            raise PermissionError("secret /private/ledger token=fixture")
        return original_read(target, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    with pytest.raises(PermissionError):
        im._load()
    assert seen == [path]


@pytest.mark.parametrize("rel", [True, "0", float("nan"), float("inf"), -float("inf")])
def test_invalid_resolved_label_cannot_publish_healthy_mark(tmp_path, monkeypatch, rel):
    im, path = _wire(tmp_path, monkeypatch)
    _put(path, [_row()])
    previous = path.read_bytes()
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis()])
    monkeypatch.setattr(im, "_mark", lambda *_: {"resolved": True, "rel_return": rel})
    with pytest.raises((TypeError, ValueError)):
        im.record("2026-09-17")
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("threshold", [True, float("nan"), float("inf"), -float("inf")])
def test_invalid_threshold_cannot_create_healthy_decisions(tmp_path, monkeypatch, threshold):
    im, path = _wire(tmp_path, monkeypatch)
    thesis = _thesis()
    thesis["falsifier"]["check"]["threshold"] = threshold
    monkeypatch.setattr(im, "all_theses", lambda: [thesis])
    monkeypatch.setattr(im, "_mark", lambda *_: {"resolved": True, "rel_return": 0})
    with pytest.raises(ValueError):
        im.record("2026-09-17")
    assert not path.exists()


def test_invalid_candidate_metadata_is_not_stringified(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    thesis = _thesis()
    thesis["prob_correct"] = object()
    monkeypatch.setattr(im, "all_theses", lambda: [thesis])
    monkeypatch.setattr(im, "_mark", lambda *_: {"resolved": True, "rel_return": 0})
    with pytest.raises((TypeError, ValueError)):
        im.record("2026-09-17")
    assert not path.exists()


def test_scorecard_and_warnings_use_one_file_snapshot(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    first = _row(rel=-0.09)
    _put(path, [first])
    original = im._load
    calls = []

    def load_once():
        calls.append(True)
        rows = original()
        _put(path, [_row(tid="later", subject="LATER", rel=0.04)])
        return rows

    monkeypatch.setattr(im, "_load", load_once)
    score = im.scorecard()
    assert len(calls) == 1
    assert score["n_marks"] == 1
    assert score["by_checkpoint"]["5"]["avg_rel"] == -0.09
    assert score["early_warnings"] == [{
        "subject": "OLD", "checkpoint": 5, "rel_return": -0.09, "entry_date": None,
    }]


def test_corruption_between_initial_read_and_locked_reread_is_not_replaced(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    _put(path, [_row()])
    corrupt = path.read_text() + "{broken\n"
    monkeypatch.setattr(im, "_CHECKPOINTS", [5])
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis()])

    def mark(*_):
        path.write_text(corrupt)
        return {"resolved": True, "rel_return": 0.04}

    monkeypatch.setattr(im, "_mark", mark)
    with pytest.raises(ValueError):
        im.record("2026-09-17")
    assert path.read_text() == corrupt
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("stage", ["write", "flush", "fsync"])
def test_pre_replace_io_failure_preserves_history_and_removes_temporary(
    tmp_path, monkeypatch, stage
):
    im, path = _wire(tmp_path, monkeypatch)
    _put(path, [_row()])
    previous = path.read_bytes()
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis()])
    monkeypatch.setattr(im, "_mark", lambda *_: {"resolved": True, "rel_return": 0.04})
    factory = im.tempfile.NamedTemporaryFile
    reached = []

    class FaultFile:
        def __init__(self, *args, **kwargs):
            self.file = factory(*args, **kwargs)
            self.name = self.file.name

        def __enter__(self):
            self.file.__enter__()
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

        def write(self, payload):
            if stage == "write":
                self.file.write(payload[:7])
                reached.append("write")
                raise OSError("injected partial write")
            return self.file.write(payload)

        def flush(self):
            if stage == "flush":
                reached.append("flush")
                raise OSError("injected flush")
            return self.file.flush()

        def fileno(self):
            return self.file.fileno()

    monkeypatch.setattr(im.tempfile, "NamedTemporaryFile", FaultFile)
    if stage == "fsync":
        def fail_fsync(_fd):
            reached.append("fsync")
            raise OSError("injected fsync")
        monkeypatch.setattr(im.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="injected"):
        im.record("2026-09-17")
    assert reached == [stage]
    assert path.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def _process_writer(path, tid, rel, role, first_locked, second_ready,
                    second_locked, release_first, results):
    """Independent interpreter: only the price input is controlled."""
    from brain import interim_marks as im
    im._PATH = Path(path)
    im._CHECKPOINTS = [5]
    im.all_theses = lambda: [_thesis(tid, tid.upper())]

    def mark(*_):
        if role == "second":
            second_ready.set()
        return {"resolved": True, "rel_return": rel}

    im._mark = mark
    original_read = im._load_unlocked
    reads = 0

    def controlled_read():
        nonlocal reads
        reads += 1
        if reads == 2 and role == "second":
            second_locked.set()
        rows = original_read()
        if reads == 2 and role == "first":
            first_locked.set()
            if not release_first.wait(10):
                raise TimeoutError("first writer was not released")
        return rows

    im._load_unlocked = controlled_read
    try:
        results.put({"role": role, "result": im.record("2026-09-17")})
    except BaseException as exc:
        results.put({"role": role, "error": type(exc).__name__ + ": " + str(exc)})
        raise


@pytest.mark.parametrize("same_key", [True, False])
def test_separate_processes_serialize_first_commit_and_preserve_other_keys(
    tmp_path, same_key
):
    import multiprocessing
    ctx = multiprocessing.get_context("spawn")
    path = tmp_path / "interim_marks.jsonl"
    seed = _row(tid="seed", subject="SEED", checkpoint=10)
    _put(path, [seed])
    first_locked, second_ready, second_locked, release_first = [
        ctx.Event() for _ in range(4)
    ]
    results = ctx.Queue()
    first = ctx.Process(target=_process_writer, args=(
        str(path), "t1", 0.04, "first", first_locked, second_ready,
        second_locked, release_first, results,
    ))
    second = ctx.Process(target=_process_writer, args=(
        str(path), "t1" if same_key else "t2", -0.09, "second",
        first_locked, second_ready, second_locked, release_first, results,
    ))
    first.start()
    try:
        assert first_locked.wait(10), "first process never reached the locked reread"
        second.start()
        assert second_ready.wait(10), "second process never finished candidate preparation"
        # This witness fails if flock is removed: an independent process then
        # enters the locked reread while the first process is deliberately held.
        assert not second_locked.wait(0.4), "second process bypassed the file lock"
    finally:
        release_first.set()
        for process in (first, second):
            if process.pid is not None:
                process.join(timeout=12)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
    assert first.exitcode == second.exitcode == 0
    observed = [results.get(timeout=3) for _ in range(2)]
    results.close()
    results.join_thread()
    assert all("error" not in result for result in observed), observed
    assert second_locked.is_set()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[0] == seed
    keyed = {(r["thesis_id"], r["checkpoint"]): r for r in rows}
    assert len(keyed) == len(rows) == (2 if same_key else 3)
    assert keyed[("t1", 5)]["rel_return"] == 0.04
    assert sorted(r["result"]["new"] for r in observed) == ([0, 1] if same_key else [1, 1])
    if not same_key:
        assert keyed[("t2", 5)]["rel_return"] == -0.09


def test_threads_preserve_disjoint_candidates(tmp_path, monkeypatch):
    im, path = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(im, "_CHECKPOINTS", [5])
    monkeypatch.setattr(im, "all_theses", lambda: [_thesis(threading.current_thread().name)])
    barrier = threading.Barrier(2)
    def mark(*_):
        barrier.wait(timeout=5)
        return {"resolved": True, "rel_return": 0.04}
    monkeypatch.setattr(im, "_mark", mark)
    results, errors = [], []
    def record():
        try:
            results.append(im.record("2026-09-17"))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=record, name=tid) for tid in ["one", "two"]]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not t.is_alive() for t in threads)
    assert not errors
    assert [r["new"] for r in results] == [1, 1]
    assert {r["thesis_id"] for r in im._load()} == {"one", "two"}


@pytest.fixture
def marks_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import web
    application = FastAPI()
    application.include_router(web.router)
    with TestClient(application) as client:
        yield client


@pytest.mark.parametrize("case", ["missing", "empty", "zero", "underwater"])
def test_registered_api_uses_real_summary_for_valid_history(
    tmp_path, monkeypatch, marks_client, case
):
    im, path = _wire(tmp_path, monkeypatch)
    if case == "empty":
        path.write_text("")
    elif case in {"zero", "underwater"}:
        _put(path, [_row(rel=0 if case == "zero" else -0.09)])
    response = marks_client.get("/api/interim_marks")
    assert response.status_code == 200
    result = response.json()
    assert "read_status" not in result and "error" not in result
    assert result == im.summary()
    score = result["scorecard"]
    assert score["n_marks"] == (1 if case in {"zero", "underwater"} else 0)
    assert len(score["early_warnings"]) == (1 if case == "underwater" else 0)
    if case == "zero":
        assert score["by_checkpoint"]["5"]["avg_rel"] == 0
        assert score["by_checkpoint"]["5"]["hit_rate"] == 1


@pytest.mark.parametrize("case", ["malformed", "shape", "nonfinite", "unreadable"])
def test_registered_api_real_failed_evidence_is_unavailable_and_secret_safe(
    tmp_path, monkeypatch, marks_client, caplog, case
):
    im, path = _wire(tmp_path, monkeypatch)
    if case == "malformed":
        path.write_text("{broken\n")
    elif case == "shape":
        _put(path, [{}])
    elif case == "nonfinite":
        _put(path, [_row(rel=float("nan"))])
    else:
        original = Path.read_text
        def unreadable(target, *args, **kwargs):
            if target == path:
                raise PermissionError("secret /private/marks api_key=fixture-only")
            return original(target, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", unreadable)
    response = marks_client.get("/api/interim_marks")
    assert response.status_code == 200
    assert response.json() == {
        "read_status": "unavailable", "scorecard": None,
        "error": "interim_marks_unavailable",
    }
    for secret in ["secret", "/private/marks", "api_key"]:
        assert secret not in response.text and secret not in caplog.text


def test_actual_scheduler_reports_mark_failure_and_continues_later_steps(
    tmp_path, monkeypatch
):
    import importlib
    import sys
    import types
    import app.scheduler as scheduler
    from control_plane import run_events

    im, path = _wire(tmp_path, monkeypatch)
    path.write_text("{corrupt\n")
    seen = []
    original_record = im.record

    def actual_record(*args, **kwargs):
        seen.append("actual_interim_marks")
        return original_record(*args, **kwargs)

    monkeypatch.setattr(im, "record", actual_record)
    # Only unrelated maintenance leaves are controlled.  Both the actual
    # interim-mark record and the production step_failed event helper execute.
    leaves = {
        "portfolio.predictions": "record", "portfolio.rejections": "record",
        "brain.student": "train", "brain.distill": "train",
        "portfolio.shadow_books": "run", "portfolio.desk_ab": "run",
        "brain.outcomes": "realized_returns", "brain.outcome_ledger": "resolve",
        "brain.calibration": "persist", "brain.attribution": "persist",
        "brain.mastermind_ai": "run_cycle",
    }
    for name, operation in leaves.items():
        parent_name, leaf = name.rsplit(".", 1)
        parent = importlib.import_module(parent_name)
        stub = types.ModuleType(name)
        def controlled(*_args, _name=name, **_kwargs):
            seen.append(_name)
            return {} if _name == "brain.outcomes" else None
        setattr(stub, operation, controlled)
        monkeypatch.setitem(sys.modules, name, stub)
        monkeypatch.setattr(parent, leaf, stub, raising=False)
    events = []
    monkeypatch.setattr(run_events, "append", lambda event: events.append(event))
    scheduler._run_loop_maintenance_steps()
    assert "actual_interim_marks" in seen
    assert seen.index("actual_interim_marks") < seen.index("portfolio.shadow_books")
    assert seen[-1] == "brain.mastermind_ai"
    assert len(events) == 1
    event = events[0]
    assert {k: event[k] for k in ["kind", "job", "book", "step", "status", "severity", "actor"]} == {
        "kind": "step_failed", "job": "loop_maintenance", "book": "",
        "step": "interim_marks.record", "status": "error",
        "severity": "ADVISORY_ONLY", "actor": "system",
    }
    assert isinstance(event["err"], ValueError)
    assert path.read_text() == "{corrupt\n"
