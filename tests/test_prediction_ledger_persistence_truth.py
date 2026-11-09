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


def _row(ticker="OLD", **overrides):
    row = {
        "id": f"2026-09-01-{ticker}-pred", "ticker": ticker, "asof": "2026-09-01",
        "dir": "up", "score": 40, "band": "high", "prob": 0.6,
        "entry_px": 100.0, "horizon_d": 21, "status": "open",
        "realized": None, "resolved_on": None,
    }
    row.update(overrides)
    return row


def _put(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.mark.parametrize("case", ["missing", "empty", "whitespace", "mapping"])
def test_strict_default_preserves_genuine_empty_and_mapping_contract(
    tmp_path, monkeypatch, case
):
    p, ledger = _wire(tmp_path, monkeypatch)
    expected = []
    if case == "empty":
        ledger.write_text("")
    elif case == "whitespace":
        ledger.write_text(" \n\t\n")
    elif case == "mapping":
        # Historical mapping rows and extension metadata remain supported.
        expected = [{"legacy": None, "extension": {"value": 0}}]
        _put(ledger, expected)
    assert p._load_ledger() == expected
    assert p._load_ledger(strict=True) == expected
    assert p._load_ledger(strict=False) == expected


def test_explicit_nonstrict_keyword_remains_compatible(tmp_path, monkeypatch):
    p, ledger = _wire(tmp_path, monkeypatch)
    ledger.write_text("{malformed\n")
    assert p._load_ledger(strict=False) == []
    with pytest.raises(ValueError):
        p._load_ledger()
    with pytest.raises(ValueError):
        p._load_ledger(strict=True)


@pytest.mark.parametrize("case", [
    "dangling-ledger", "dangling-parent", "file-parent", "directory-ledger",
])
def test_broken_storage_path_is_not_missing_evidence(tmp_path, monkeypatch, case):
    p, ledger = _wire(tmp_path, monkeypatch)
    if case == "dangling-ledger":
        ledger.symlink_to(tmp_path / "absent-target")
    elif case == "directory-ledger":
        ledger.mkdir()
    else:
        parent = tmp_path / "unavailable"
        if case == "dangling-parent":
            parent.symlink_to(tmp_path / "absent-parent")
        else:
            parent.write_text("regular file")
        ledger = parent / "ledger.jsonl"
        monkeypatch.setattr(p, "_PRED_DIR", parent)
        monkeypatch.setattr(p, "_LEDGER", ledger)
    with pytest.raises(OSError):
        p._load_ledger()
    assert p._load_ledger(strict=False) == []


@pytest.mark.parametrize("payload", [
    b"{broken\n", b"[]\n", b"null\n", b"1\n", b'"text"\n',
    b'{"ticker":"OLD","status":"open"}\n{broken\n', b"\xff\n",
])
def test_invalid_ledger_is_never_replaced_by_a_record(
    tmp_path, monkeypatch, payload
):
    p, ledger = _wire(tmp_path, monkeypatch)
    ledger.write_bytes(payload)
    monkeypatch.setattr(p, "universe", lambda: [_u("NEW")])
    monkeypatch.setattr(p, "_load_panel", lambda: None)
    monkeypatch.setattr(p, "_spy_series", lambda: None)
    with pytest.raises(ValueError):
        p._load_ledger()
    with pytest.raises(ValueError):
        p.record("2026-09-17")
    assert ledger.read_bytes() == payload
    assert not list(tmp_path.glob(".*.tmp"))


def test_permission_error_propagates_from_normal_owner_reads(tmp_path, monkeypatch):
    p, ledger = _wire(tmp_path, monkeypatch)
    original = Path.read_text

    def unreadable(target, *args, **kwargs):
        if target == ledger:
            raise PermissionError("fixture-only inaccessible ledger")
        return original(target, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    for operation in (p._load_ledger, p.coverage, p.score, p.summary):
        with pytest.raises(PermissionError):
            operation()
    assert p._load_ledger(strict=False) == []


def test_atomic_save_retains_all_open_rows_and_latest_resolved(tmp_path, monkeypatch):
    p, ledger = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(p, "_MAX_RESOLVED", 2)
    first, second = _row("A"), _row("B")
    resolved = [
        _row(f"R{i}", status="resolved", realized=0.01, resolved_on=f"2026-09-0{i}")
        for i in (3, 1, 4, 2)
    ]
    p._save_ledger([resolved[0], first, *resolved[1:], second])
    assert p._load_ledger() == [first, second, resolved[0], resolved[2]]
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("rows", [[None], [["not", "mapping"]], ["not-mapping"]])
def test_save_rejects_nonmapping_rows_before_replacing_existing_bytes(
    tmp_path, monkeypatch, rows
):
    p, ledger = _wire(tmp_path, monkeypatch)
    _put(ledger, [_row()])
    previous = ledger.read_bytes()
    with pytest.raises(ValueError):
        p._save_ledger(rows)
    assert ledger.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("stage", ["write", "flush", "fsync"])
def test_pre_replace_io_failure_preserves_complete_ledger(
    tmp_path, monkeypatch, stage
):
    p, ledger = _wire(tmp_path, monkeypatch)
    _put(ledger, [_row()])
    previous = ledger.read_bytes()
    monkeypatch.setattr(p, "universe", lambda: [_u("NEW")])
    monkeypatch.setattr(p, "_load_panel", lambda: None)
    monkeypatch.setattr(p, "_spy_series", lambda: None)
    factory = p.tempfile.NamedTemporaryFile
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
                reached.append(stage)
                raise OSError("injected partial write")
            return self.file.write(payload)

        def flush(self):
            if stage == "flush":
                reached.append(stage)
                raise OSError("injected flush")
            return self.file.flush()

        def fileno(self):
            return self.file.fileno()

    monkeypatch.setattr(p.tempfile, "NamedTemporaryFile", FaultFile)
    if stage == "fsync":
        def fail_fsync(_fd):
            reached.append(stage)
            raise OSError("injected fsync")
        monkeypatch.setattr(p.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="injected"):
        p.record("2026-09-17")
    assert reached == [stage]
    assert ledger.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))


def _process_record(path, ticker, price, role, first_locked, second_ready,
                    second_locked, release_first, results):
    """Independent process; actual reader, file lock and atomic publisher run."""
    from portfolio import predictions as p
    p._LEDGER = Path(path)
    p._PRED_DIR = p._LEDGER.parent
    p._HORIZONS = [21]
    p.universe = lambda: [{**_u(ticker), "price": price}]
    p._load_panel = lambda: None

    def spy():
        if role == "second":
            second_ready.set()
        return None

    p._spy_series = spy
    original_load = p._load_ledger

    def controlled_load():
        if role == "second":
            second_locked.set()
        rows = original_load()
        if role == "first":
            first_locked.set()
            if not release_first.wait(10):
                raise TimeoutError("first writer was not released")
        return rows

    p._load_ledger = controlled_load
    try:
        results.put({"role": role, "result": p.record("2026-09-17")})
    except BaseException as exc:
        results.put({"role": role, "error": type(exc).__name__ + ": " + str(exc)})
        raise


@pytest.mark.parametrize("same_key", [True, False])
def test_separate_processes_keep_first_open_key_and_disjoint_writes(
    tmp_path, same_key
):
    import multiprocessing
    ctx = multiprocessing.get_context("spawn")
    ledger = tmp_path / "ledger.jsonl"
    seed = _row("SEED")
    _put(ledger, [seed])
    first_locked, second_ready, second_locked, release_first = [
        ctx.Event() for _ in range(4)
    ]
    results = ctx.Queue()
    first = ctx.Process(target=_process_record, args=(
        str(ledger), "AAPL", 100.0, "first", first_locked, second_ready,
        second_locked, release_first, results,
    ))
    second = ctx.Process(target=_process_record, args=(
        str(ledger), "AAPL" if same_key else "MSFT", 200.0, "second",
        first_locked, second_ready, second_locked, release_first, results,
    ))
    first.start()
    try:
        assert first_locked.wait(10), "first process never reached the locked reader"
        second.start()
        assert second_ready.wait(10), "second process never completed market preparation"
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
    assert all("error" not in item for item in observed), observed
    assert second_locked.is_set()
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    keyed = {(r["ticker"], r["horizon_d"]): r for r in rows}
    assert len(keyed) == len(rows) == (2 if same_key else 3)
    assert keyed[("SEED", 21)] == seed
    assert keyed[("AAPL", 21)]["entry_px"] == 100.0
    assert sorted(item["result"]["n_total"] for item in observed) == (
        [2, 2] if same_key else [2, 3]
    )
    if not same_key:
        assert keyed[("MSFT", 21)]["entry_px"] == 200.0
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.fixture
def predictions_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import web
    application = FastAPI()
    application.include_router(web.router)
    with TestClient(application) as client:
        yield client


@pytest.mark.parametrize("case", [
    "missing", "empty", "open", "resolved-zero", "resolved-loss",
])
def test_registered_predictions_api_uses_real_summary(
    tmp_path, monkeypatch, predictions_client, case
):
    p, ledger = _wire(tmp_path, monkeypatch)
    if case == "empty":
        ledger.write_text("")
    elif case == "open":
        _put(ledger, [_row()])
    elif case.startswith("resolved"):
        _put(ledger, [_row(status="resolved", realized=0 if case == "resolved-zero" else -0.09,
                          resolved_on="2026-09-17")])
    response = predictions_client.get("/api/predictions")
    assert response.status_code == 200
    result = response.json()
    assert "error" not in result and "read_status" not in result
    assert result == p.summary()
    assert result["coverage"]["n_total"] == (0 if case in {"missing", "empty"} else 1)
    assert result["horizon_d"] == 21
    assert set(result["scorecards_by_horizon"]) == {"3", "5", "10", "21"}


@pytest.mark.parametrize("case", ["malformed", "shape", "unreadable", "dangling"])
def test_registered_predictions_api_reports_real_unavailable_evidence(
    tmp_path, monkeypatch, predictions_client, caplog, case
):
    p, ledger = _wire(tmp_path, monkeypatch)
    if case == "malformed":
        ledger.write_text("{broken\n")
    elif case == "shape":
        ledger.write_text("[]\n")
    elif case == "dangling":
        ledger.symlink_to(tmp_path / "missing-target")
    else:
        original = Path.read_text

        def unreadable(target, *args, **kwargs):
            if target == ledger:
                raise PermissionError("fixture-secret /private/predictions api_key=fixture-only")
            return original(target, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", unreadable)
    response = predictions_client.get("/api/predictions")
    assert response.status_code == 200
    assert response.json() == {
        "read_status": "unavailable", "error": "predictions_unavailable",
        "coverage": None, "scorecard": None,
    }
    for secret in ["fixture-secret", "/private/predictions", "api_key"]:
        assert secret not in response.text and secret not in caplog.text


def test_actual_scheduler_reports_prediction_publish_failure_and_continues(
    tmp_path, monkeypatch
):
    import importlib
    import sys
    import types
    import app.scheduler as scheduler
    from control_plane import run_events

    p, ledger = _wire(tmp_path, monkeypatch)
    _put(ledger, [_row()])
    previous = ledger.read_bytes()
    monkeypatch.setattr(p, "universe", lambda: [_u("NEW")])
    monkeypatch.setattr(p, "_load_panel", lambda: None)
    monkeypatch.setattr(p, "_spy_series", lambda: None)
    original_record, original_replace = p.record, p.os.replace
    seen, events, publications = [], [], []

    def actual_record(*args, **kwargs):
        seen.append("actual_predictions")
        return original_record(*args, **kwargs)

    def fail_replace(source, destination):
        if Path(destination) == ledger:
            publications.append(Path(source))
            raise OSError("injected prediction publication failure")
        return original_replace(source, destination)

    monkeypatch.setattr(p, "record", actual_record)
    monkeypatch.setattr(p.os, "replace", fail_replace)
    leaves = {
        "portfolio.rejections": "record", "brain.interim_marks": "record",
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
    monkeypatch.setattr(run_events, "append", lambda event: events.append(event))
    scheduler._run_loop_maintenance_steps()
    assert len(publications) == 1
    assert seen.index("actual_predictions") < seen.index("portfolio.rejections")
    assert seen[-1] == "brain.mastermind_ai"
    assert len(events) == 1
    event = events[0]
    assert {k: event[k] for k in [
        "kind", "job", "book", "step", "status", "severity", "actor",
    ]} == {
        "kind": "step_failed", "job": "loop_maintenance", "book": "",
        "step": "predictions.record", "status": "error",
        "severity": "ADVISORY_ONLY", "actor": "system",
    }
    assert isinstance(event["err"], OSError)
    assert ledger.read_bytes() == previous
    assert not list(tmp_path.glob(".*.tmp"))


@pytest.mark.parametrize("control", [
    "test_score_recovers_real_signal",
    "test_score_thins_overlapping_dates_to_independent_clusters",
    "test_fast_tier_matures_while_canonical_tier_is_empty",
    "test_directional_reliability_curve_and_tilt",
    "test_score_building_below_min_dates",
    "test_score_empty_is_valid",
])
def test_current_statistical_controls_survive_validation_import_failure(
    monkeypatch, control
):
    import builtins
    import importlib.util
    from portfolio import predictions as p

    spec = importlib.util.spec_from_file_location(
        "prediction_regression_controls", Path(__file__).with_name("test_predictions.py")
    )
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    original_import = builtins.__import__
    attempts = []

    def unavailable_validation(name, *args, **kwargs):
        if name == "engine.validation":
            attempts.append(name)
            raise ImportError("controlled missing optional validation module")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable_validation)
    p._validation_helpers()
    getattr(baseline, control)(monkeypatch)
    assert attempts
