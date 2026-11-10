"""tests/test_runlog_codeql_hardening.py — boundary + response guards for the run log.

Pins the CodeQL hardening of GET /api/runlog (app/web.py ``api_runlog``):

* py/path-injection — a run id is allowlisted *before* it reaches the filesystem
  (``validate_run_id``) and the joined path is containment-checked against the
  runs directory (``_run_path``); a traversal id never becomes a path.
* py/stack-trace-exposure — neither ``read_run`` nor the route ever returns
  exception text or a traceback in the JSON response body.

Offline: the runs store is redirected at a tmp dir, so no real data is touched.
"""
from __future__ import annotations

import json
import os
from contextlib import nullcontext
from pathlib import Path

import pytest

from app import web


# ── helpers ──────────────────────────────────────────────────────────────────

def _patch_store(tmp_path: Path, monkeypatch):
    """Point brain.runlog's store at tmp_path and return the module."""
    import brain.runlog as rl
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rl, "_RUNS_DIR", runs_dir)
    monkeypatch.setattr(rl, "_INDEX", runs_dir / "index.jsonl")
    return rl


BAD_RUN_IDS = [
    "../etc/passwd",
    "a/b",
    "a\\b",
    "..",
    ".",
    "",
    "a..b",
    "-leading",
    "a" * 97,
    None,
    123,
    "a\x00b",
    "a b",
    "a%2f",
]


# ── validate_run_id ──────────────────────────────────────────────────────────

def test_validate_run_id_accepts_generated_id(tmp_path, monkeypatch):
    rl = _patch_store(tmp_path, monkeypatch)
    run_id = rl.start_run("test")
    assert rl.validate_run_id(run_id) == run_id
    assert rl.validate_run_id("abc_1.2:3-x") == "abc_1.2:3-x"


@pytest.mark.parametrize("bad", BAD_RUN_IDS, ids=lambda v: repr(v)[:24])
def test_validate_run_id_rejects_traversal_and_non_tokens(tmp_path, monkeypatch, bad):
    rl = _patch_store(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        rl.validate_run_id(bad)


# ── _run_path containment ────────────────────────────────────────────────────

def test_run_path_resolves_directly_inside_runs_dir(tmp_path, monkeypatch):
    rl = _patch_store(tmp_path, monkeypatch)
    p = rl._run_path("abc")
    assert p.parent == Path(os.path.normpath(str(rl._RUNS_DIR)))
    assert p.name == "abc.jsonl"


# ── read_run response guarding ──────────────────────────────────────────────

def test_read_run_rejects_traversal_id_without_echo(tmp_path, monkeypatch):
    rl = _patch_store(tmp_path, monkeypatch)
    result = rl.read_run("../../etc/passwd")
    assert result["error"] == "invalid run_id"
    assert result["run_id"] is None
    assert "etc" not in json.dumps(result)


def test_read_run_exception_is_not_echoed(tmp_path, monkeypatch):
    rl = _patch_store(tmp_path, monkeypatch)

    def boom():
        raise RuntimeError("SECRET-DETAIL-XYZ")

    monkeypatch.setattr(rl, "_portfolio_index", boom)
    # The lock is not the subject here; keep the test off the real lock tree.
    monkeypatch.setattr(rl, "portfolio_lock", nullcontext)

    result = rl.read_run("abc")
    text = json.dumps(result)
    assert result["error"] == "runlog read failed"
    assert "SECRET-DETAIL-XYZ" not in text
    assert "Traceback" not in text


# ── route-level guard (direct call, no server) ─────────────────────────────

def test_api_runlog_unexpected_error_degrades(monkeypatch):
    import brain.runlog as rl

    def boom(_run_id=None):
        raise RuntimeError("SECRET-DETAIL-XYZ")

    monkeypatch.setattr(rl, "read_run", boom)
    response = web.api_runlog(run_id="abc")
    body = bytes(response.body).decode("utf-8")
    data = json.loads(body)
    assert response.status_code == 500
    assert data["error"] == "runlog unavailable"
    assert "SECRET-DETAIL-XYZ" not in body
    assert "Traceback" not in body
    assert "RuntimeError" not in body


def test_api_runlog_traversal_id_is_rejected(tmp_path, monkeypatch):
    _patch_store(tmp_path, monkeypatch)
    response = web.api_runlog(run_id="../../etc/passwd")
    body = bytes(response.body).decode("utf-8")
    data = json.loads(body)
    assert data["error"] == "invalid run_id"
    assert "etc/passwd" not in body
