from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

import pytest


def _wire(tmp_path, monkeypatch):
    from brain import portfolio_learning as pl
    monkeypatch.setattr(pl, "_DIR", tmp_path / "learning")
    return pl


def _request_row(request_id="ctx-existing"):
    return {
        "schema": "portfolio.context_request.v1",
        "id": request_id,
        "ts": "2026-09-18T00:00:00+00:00",
        "book": "autonomous",
        "plane": "terminal.flow",
        "ticker": "AAPL",
        "reason": "Need verified flow context for a current exit review.",
        "status": "queued_for_orchestrator_review",
        "authority": "request_only",
    }


def test_corrupt_context_request_ledger_is_failed_evidence(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._DIR / "context_requests.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(_request_row()) + "\n{broken secret token=do-not-return\n"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(Exception):
        pl.context_requests(limit=None)

    assert path.read_text(encoding="utf-8") == raw


def test_wrong_shaped_context_request_row_is_failed_evidence(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._DIR / "context_requests.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(["not", "a", "mapping"]) + "\n", encoding="utf-8")

    with pytest.raises(Exception):
        pl.context_requests(limit=None)


def test_context_request_replace_failure_preserves_prior_complete_bytes(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._DIR / "context_requests.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = json.dumps(_request_row()) + "\n"
    path.write_text(prior, encoding="utf-8")
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == path:
            raise OSError("secret /Users/private/context token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)
    result = pl.request_context(
        "autonomous",
        "terminal.options",
        "Need verified options structure for this current exit review.",
        "AAPL",
    )

    assert result == {"ok": False, "error": "context_request_write_failed"}
    assert path.read_text(encoding="utf-8") == prior
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_request_context_holds_context_mutation_lock(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    entered = []

    @contextmanager
    def observed_lock():
        entered.append("request")
        yield

    monkeypatch.setattr(pl, "_context_request_lock", observed_lock)
    result = pl.request_context(
        "autonomous",
        "terminal.intraday",
        "Need verified intraday breadth for current portfolio timing.",
        "AAPL",
    )

    assert result["ok"] is True
    assert entered == ["request"]


def test_advance_context_request_holds_context_mutation_lock(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    created = pl.request_context(
        "autonomous",
        "terminal.flow",
        "Need verified flow context for a current exit review.",
        "AAPL",
    )["request"]
    entered = []

    @contextmanager
    def observed_lock():
        entered.append("advance")
        yield

    monkeypatch.setattr(pl, "_context_request_lock", observed_lock)
    assert pl.advance_context_request(
        created["id"], "directive_queued", directive_id="directive-1"
    ) is True
    assert entered == ["advance"]


def test_missing_context_ledger_remains_legitimate_first_request(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    result = pl.request_context(
        "autonomous",
        "terminal.flow",
        "Need verified same-session flow context for this exit review.",
        "AAPL",
    )

    assert result["ok"] is True
    assert pl.context_requests(limit=None)[0]["id"] == result["request"]["id"]


def test_unrelated_jsonl_keeps_best_effort_compatibility(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._DIR / "legacy_best_effort.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": "good"}) + "\n{broken\n", encoding="utf-8")

    assert pl._read_jsonl(path) == [{"id": "good"}]


def test_context_request_lock_serializes_independent_processes(tmp_path, monkeypatch):
    import multiprocessing as mp
    import time

    pl = _wire(tmp_path, monkeypatch)
    ctx = mp.get_context("fork")
    entered = ctx.Event()
    release = ctx.Event()
    acquired_after_release = ctx.Value("b", False)

    def holder():
        with pl._context_request_lock():
            entered.set()
            release.wait(timeout=5)

    def waiter():
        entered.wait(timeout=5)
        with pl._context_request_lock():
            acquired_after_release.value = release.is_set()

    first = ctx.Process(target=holder)
    second = ctx.Process(target=waiter)
    first.start()
    assert entered.wait(timeout=5)
    second.start()
    time.sleep(0.15)
    assert second.is_alive()

    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert first.exitcode == 0 and second.exitcode == 0
    assert bool(acquired_after_release.value)


def test_transition_replace_failure_preserves_prior_state_for_retry(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    created = pl.request_context(
        "autonomous",
        "terminal.flow",
        "Need verified same-session flow context for this current exit review.",
        "AAPL",
    )["request"]
    path = pl._DIR / "context_requests.jsonl"
    prior = path.read_text(encoding="utf-8")
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == path:
            raise OSError("transition publish unavailable")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    assert pl.advance_context_request(
        created["id"], "directive_queued", directive_id="directive-1"
    ) is False
    assert path.read_text(encoding="utf-8") == prior
    assert pl.context_requests(limit=None)[0]["status"] == "queued_for_orchestrator_review"
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_mastermind_ai_transport_does_not_turn_corrupt_context_ledger_into_no_work(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    from brain import mastermind_ai as mai

    path = pl._DIR / "context_requests.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken request evidence\n", encoding="utf-8")
    ai_dir = tmp_path / "mastermind_ai"
    monkeypatch.setattr(mai, "_DIR", ai_dir)
    monkeypatch.setattr(mai, "_DIRECTIVES", ai_dir / "directives.jsonl")
    monkeypatch.setattr(mai, "_SETTINGS", ai_dir / "settings.json")

    result = mai.draft_directives_from_context_requests()

    assert result["ok"] is False
    assert "queued" not in result
    assert result["error"] in {"JSONDecodeError", "ValueError", "OSError"}
