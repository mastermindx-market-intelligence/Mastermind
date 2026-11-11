"""Outcome resolution must not permanently erase unavailable point-in-time signal evidence."""
from __future__ import annotations

import json

import pytest


def _thesis(tid="t1", subject="NVDA", state_asof="2026-09-01"):
    return {
        "id": tid,
        "subject": subject,
        "prob_correct": 0.7,
        "lean": "add",
        "horizon_d": 21,
        "sleeve": "conviction",
        "state_asof": state_asof,
        "falsifier": {"check": {"kind": "rel_return", "op": "<", "threshold": -0.05}},
    }


def _wire(tmp_path, monkeypatch):
    from brain import outcome_ledger as ol
    from brain import signal_history as sh
    monkeypatch.setattr(ol, "_PATH", tmp_path / "outcomes.jsonl")
    monkeypatch.setattr(sh, "_PATH", tmp_path / "signals.jsonl")
    return ol, sh


def test_unavailable_signal_history_blocks_keep_first_outcome_write(tmp_path, monkeypatch):
    ol, sh = _wire(tmp_path, monkeypatch)
    (tmp_path / "signals.jsonl").write_text('{broken\n')

    with pytest.raises(Exception):
        ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()])

    assert not (tmp_path / "outcomes.jsonl").exists()


def test_genuine_missing_snapshot_resolves_with_explicit_missing_status(tmp_path, monkeypatch):
    ol, _ = _wire(tmp_path, monkeypatch)

    assert ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()]) == 1
    row = ol.load()[0]
    assert row["lens_snapshot_status"] == "missing"
    assert row["lens_dirs"] == {}


def test_available_snapshot_is_recorded_as_available_even_with_no_directional_lenses(tmp_path, monkeypatch):
    ol, sh = _wire(tmp_path, monkeypatch)
    sh.archive("2026-09-01", [{
        "ticker": "NVDA",
        "lens_dirs": {},
        "confluence": 0.0,
        "size_authority": "hold",
        "quad": "Q2",
    }])

    assert ol.resolve("2026-09-17", {"t1": 0.10}, theses=[_thesis()]) == 1
    row = ol.load()[0]
    assert row["lens_snapshot_status"] == "available"
    assert row["lens_dirs"] == {}
    assert row["confluence_at_entry"] == 0.0
    assert row["size_authority_at_entry"] == "hold"
    assert row["quad_at_entry"] == "Q2"


def test_recorded_outcome_skips_history_while_new_outcomes_remain_retryable(tmp_path, monkeypatch):
    ol, sh = _wire(tmp_path, monkeypatch)
    first = _thesis()
    assert ol.resolve("2026-09-17", {"t1": 0.10}, theses=[first]) == 1
    original = ol._PATH.read_bytes()
    sh._PATH.write_text("{broken\n")

    assert ol.resolve("2026-09-18", {"t1": -0.20}, theses=[first]) == 0
    assert ol._PATH.read_bytes() == original

    undated = _thesis("t2", state_asof=None)
    assert ol.resolve("2026-09-18", {"t1": -0.20, "t2": 0.10}, theses=[first, undated]) == 1
    assert ol.load()[1]["lens_snapshot_status"] == "missing"

    new = _thesis("t3")
    before_retry = ol._PATH.read_bytes()
    with pytest.raises(json.JSONDecodeError):
        ol.resolve("2026-09-18", {"t3": 0.10}, theses=[new])
    assert ol._PATH.read_bytes() == before_retry

    sh._PATH.write_text("")
    assert ol.resolve("2026-09-18", {"t3": 0.10}, theses=[new]) == 1
