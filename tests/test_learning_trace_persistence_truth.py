from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


def _wire(tmp_path, monkeypatch):
    from brain import portfolio_learning as pl
    monkeypatch.setattr(pl, "_DIR", tmp_path / "learning")
    return pl


def _application_row(pl):
    return {
        "schema": "portfolio.lesson_application.v1",
        "application_id": "application.v1." + "a" * 24,
        "decision_id": "decision.v1." + "b" * 24,
        "presentation_id": "presentation.v1." + "c" * 24,
        "book": "autonomous",
        "book_scope": "US_ONLY",
        "accepted_asof": "2026-09-18",
        "lesson_ids": ["lesson.v1.US_ONLY.persistence_truth"],
        "lesson_basis": [{"id": "lesson.v1.US_ONLY.persistence_truth"}],
        "submission_sha256": "d" * 64,
        "target_sha256": "e" * 64,
        "target_status": "queued",
        "executed": False,
        "authority": pl.APPLICATION_AUTHORITY,
        "evidence_cohort": pl.LESSON_TRACE_COHORT,
    }


def test_corrupt_application_trace_is_failed_evidence(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._book_dir("autonomous") / "applications.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(_application_row(pl)) + "\n{broken secret token=do-not-return\n"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(Exception):
        pl.applications("autonomous")

    assert path.read_text(encoding="utf-8") == raw


def test_wrong_shaped_application_trace_is_failed_evidence(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._book_dir("autonomous") / "applications.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(["not", "a", "mapping"]) + "\n", encoding="utf-8")

    with pytest.raises(Exception):
        pl.applications("autonomous")


def test_corrupt_presentation_trace_cannot_be_extended(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._book_dir("autonomous") / "presentations.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = "{broken presentation evidence\n"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(Exception):
        pl._record_presentation("autonomous", "2026-09-18", [])

    assert path.read_text(encoding="utf-8") == raw


@pytest.mark.parametrize("name", ["applications.jsonl", "presentations.jsonl"])
def test_trace_replace_failure_preserves_prior_complete_bytes(tmp_path, monkeypatch, name):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._book_dir("autonomous") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = json.dumps({"schema": "prior.v1", "id": "old"}) + "\n"
    path.write_text(prior, encoding="utf-8")
    real_replace = os.replace

    def fail_replace(src, dst):
        if Path(dst) == path:
            raise OSError("secret /Users/private/trace token=do-not-return")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_replace)

    assert pl._append_jsonl(path, {"schema": "new.v1", "id": "new"}) is False
    assert path.read_text(encoding="utf-8") == prior
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_non_trace_jsonl_keeps_existing_best_effort_read_contract(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = tmp_path / "learning" / "context_requests.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": "ctx-good"}) + "\n{broken\n", encoding="utf-8")

    assert pl._read_jsonl(path) == [{"id": "ctx-good"}]
