from __future__ import annotations

import json
import os
import stat
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


def test_unrelated_jsonl_keeps_existing_best_effort_read_contract(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = tmp_path / "learning" / "legacy_best_effort.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": "ctx-good"}) + "\n{broken\n", encoding="utf-8")

    assert pl._read_jsonl(path) == [{"id": "ctx-good"}]


def test_unrelated_jsonl_stat_failure_keeps_best_effort(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._DIR / "legacy_best_effort.jsonl"
    original_exists = Path.exists

    def fail_target_exists(self):
        if self == path:
            raise OSError("legacy-history-stat-unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", fail_target_exists)

    assert pl._read_jsonl(path) == []


@pytest.mark.parametrize("name", ["applications.jsonl", "presentations.jsonl"])
def test_existing_trace_read_failure_is_not_empty(tmp_path, monkeypatch, name):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._book_dir("autonomous") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    original_read = Path.read_text

    def fail_target_read(self, *args, **kwargs):
        if self == path:
            raise OSError("trace-read-unavailable")
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_target_read)

    with pytest.raises(OSError, match="trace-read-unavailable"):
        if name == "applications.jsonl":
            pl.applications("autonomous")
        else:
            pl._record_presentation("autonomous", "2026-09-18", [])


@pytest.mark.parametrize("name", ["applications.jsonl", "presentations.jsonl"])
def test_dangling_trace_is_not_absent_and_is_not_replaced(tmp_path, monkeypatch, name):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._book_dir("autonomous") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    missing = path.parent / "missing-trace.jsonl"
    path.symlink_to(missing)

    with pytest.raises(FileNotFoundError):
        if name == "applications.jsonl":
            pl.applications("autonomous")
        else:
            pl._record_presentation("autonomous", "2026-09-18", [])

    assert path.is_symlink()
    assert path.readlink() == missing
    assert not missing.exists()
    assert pl._append_jsonl(path, {"schema": "unaccepted.v1"}) is False
    assert path.is_symlink()
    assert not missing.exists()


@pytest.mark.parametrize("name", ["applications.jsonl", "presentations.jsonl"])
def test_trace_directory_fsync_failure_reports_unconfirmed_visible_effect(tmp_path, monkeypatch, name):
    pl = _wire(tmp_path, monkeypatch)
    path = pl._book_dir("autonomous") / name
    path.parent.mkdir(parents=True, exist_ok=True)
    prior = {"schema": "prior.v1", "id": "old"}
    added = {"schema": "new.v1", "id": "new"}
    path.write_text(json.dumps(prior) + "\n", encoding="utf-8")
    real_fsync = os.fsync
    attempts = []

    def fail_directory_fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            attempts.append("directory")
            raise OSError("trace-directory-durability-unconfirmed")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)

    assert pl._append_jsonl(path, added) is False
    assert attempts == ["directory"]
    assert [json.loads(line) for line in path.read_text().splitlines()] == [prior, added]
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_unrelated_jsonl_directory_fsync_retains_best_effort(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    real_fsync = os.fsync
    attempts = []

    def fail_directory_fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            attempts.append("directory")
            raise OSError("legacy-directory-durability-unavailable")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory_fsync)

    path = pl._DIR / "legacy_best_effort.jsonl"
    row = {"schema": "legacy.v1", "id": "good"}

    assert pl._append_jsonl(path, row) is True
    assert attempts == ["directory"]
    assert pl._read_jsonl(path) == [row]


def test_real_presentation_publication_is_stable_and_deduplicated(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    lesson = {"id": "lesson.v1.US_ONLY.persistence_truth", "scope": "US_ONLY",
              "status": "active", "authority": pl.LESSON_AUTHORITY}

    first = pl._record_presentation("autonomous", "2026-09-18", [lesson])
    second = pl._record_presentation("autonomous", "2026-09-18", [lesson])

    assert first == second
    assert first["lesson_ids"] == [lesson["id"]]
    assert first["authority"] == pl.APPLICATION_AUTHORITY
    path = pl._book_dir("autonomous") / "presentations.jsonl"
    assert [json.loads(line) for line in path.read_text().splitlines()] == [first]


def test_valid_application_trace_round_trips_through_verified_reader(tmp_path, monkeypatch):
    pl = _wire(tmp_path, monkeypatch)
    row = _application_row(pl)
    row["executed_at"] = None
    row["material_difference"] = {}
    row["decision_id"] = "decision.v1." + pl._sha256([
        row["book"], row["accepted_asof"], row["presentation_id"], row["submission_sha256"],
    ])[:24]
    row["application_id"] = "application.v1." + pl._sha256([
        row["decision_id"], row["presentation_id"], row["lesson_ids"],
    ])[:24]
    assert pl._valid_initial_application(row, "autonomous", row["application_id"]) is True
    path = pl._book_dir("autonomous") / "applications.jsonl"

    with pl._trace_lock("autonomous"):
        assert pl._append_jsonl(path, row) is True

    assert pl.applications("autonomous") == [row]
    assert pl.applications("autonomous")[0]["executed"] is False
