"""Watchlist canonical evidence must stay truthful under corruption and failed publication."""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import time
from pathlib import Path

import pytest

from portfolio import watchlist as W


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_WATCHLIST", tmp_path / "watchlist.jsonl", raising=False)
    monkeypatch.setattr(W, "_STATE", tmp_path / "watchlist_state.jsonl", raising=False)


def test_corrupt_append_log_is_failed_evidence_not_empty():
    raw = "{broken secret token=do-not-return\n"
    W._WATCHLIST.write_text(raw)

    with pytest.raises(Exception):
        W.all_rows()

    assert W._WATCHLIST.read_text() == raw


def test_append_refuses_to_overwrite_corrupt_log():
    raw = "{broken\n"
    W._WATCHLIST.write_text(raw)

    assert W.append("AAPL", "2026-09-18", "extended") is False
    assert W._WATCHLIST.read_text() == raw


def test_corrupt_state_snapshot_is_failed_evidence_not_empty():
    raw = "{broken secret token=do-not-return\n"
    W._STATE.write_text(raw)

    with pytest.raises(Exception):
        W.state_rows()

    assert W._STATE.read_text() == raw


def test_append_replace_failure_preserves_prior_complete_bytes(monkeypatch):
    assert W.append("OLD", "2026-09-17", "old") is True
    prior = W._WATCHLIST.read_text()
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == W._WATCHLIST:
            raise OSError("secret /Users/private/watchlist token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    assert W.append("NEW", "2026-09-18", "new") is False
    assert W._WATCHLIST.read_text() == prior
    assert not list(W._WATCHLIST.parent.glob(".*.tmp"))


def test_state_replace_failure_preserves_prior_complete_bytes(monkeypatch):
    assert W._write_state([{"ticker": "OLD", "state": "watch"}]) is True
    prior = W._STATE.read_text()
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == W._STATE:
            raise OSError("secret /Users/private/watch-state token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    assert W._write_state([{"ticker": "NEW", "state": "watch"}]) is False
    assert W._STATE.read_text() == prior
    assert not list(W._STATE.parent.glob(".*.tmp"))


def test_advance_rotation_does_not_report_unpersisted_state(monkeypatch):
    assert W.append_rotation("SMH", "2026-09-17", "rot:semis") is True
    monkeypatch.setattr(W, "_write_state", lambda _rows: False)

    out = W._advance_rotation("rot:semis", "2026-09-18", state="armed")

    assert out is None


def test_review_does_not_return_unpersisted_promotion(monkeypatch):
    assert W.append("AAPL", "2026-09-17", "extended", combined=80.0) is True
    monkeypatch.setattr(W, "_write_state", lambda _rows: False)

    out = W.review("2026-09-18", still_withheld=lambda _ticker: None)

    assert out == {"promote": [], "expired": [], "active": []}


def test_watchlist_lock_serializes_independent_processes():
    ctx = mp.get_context("fork")
    entered = ctx.Event()
    release = ctx.Event()
    acquired_after_release = ctx.Value("b", False)

    def holder():
        with W._watchlist_lock():
            entered.set()
            release.wait(timeout=5)

    def waiter():
        entered.wait(timeout=5)
        with W._watchlist_lock():
            acquired_after_release.value = release.is_set()

    first = ctx.Process(target=holder)
    second = ctx.Process(target=waiter)
    first.start()
    assert entered.wait(timeout=5)
    second.start()
    time.sleep(0.15)
    assert second.is_alive(), "second process should block on the canonical watchlist lock"

    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert first.exitcode == 0
    assert second.exitcode == 0
    assert bool(acquired_after_release.value)


def test_desk_watchlist_corrupt_state_is_unavailable():
    from app import web

    assert W.append("AAPL", "2026-09-17", "extended") is True
    W._STATE.write_text("{broken\n")

    body = json.loads(web.api_desk_watchlist().body)

    assert body["status"] == "unavailable"
    assert body["error"] == "desk_watchlist_unavailable"
    assert body["watchlist"] is None


def test_desk_watchlist_missing_state_remains_valid_success():
    from app import web

    assert W.append("AAPL", "2026-09-17", "extended") is True
    assert not W._STATE.exists()

    body = json.loads(web.api_desk_watchlist().body)

    assert "status" not in body
    assert body["watchlist"][0]["ticker"] == "AAPL"
