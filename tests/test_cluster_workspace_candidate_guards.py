"""Additional repair regressions; all Git mutations target disposable fixtures."""
import json
from pathlib import Path
import pytest
from scripts import mini_worktree as mw
from test_mini_worktree import _fixture


def test_resume_preserves_dirty_work_and_works_below_new_allocation_floor(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    first = mw.create_worktree(cfg, "fixture", "resume-dirty", "audit")
    marker = Path(first["workspace"]) / "must-survive.txt"
    marker.write_text("not returned yet\n")
    monkeypatch.setattr(mw, "_free_bytes", lambda _: 0)
    resumed = mw.create_worktree(cfg, "fixture", "resume-dirty", "audit")
    assert resumed["reused"] is True
    assert marker.read_text() == "not returned yet\n"


def test_resume_missing_workspace_refuses_without_recreating(tmp_path):
    cfg, _ = _fixture(tmp_path)
    first = mw.create_worktree(cfg, "fixture", "gone", "audit")
    path = Path(first["workspace"])
    moved = path.with_name("preserved-gone")
    path.rename(moved)
    with pytest.raises(mw.MiniWorktreeError, match="registered workspace unavailable"):
        mw.create_worktree(cfg, "fixture", "gone", "audit")
    assert not path.exists()
    assert moved.is_dir()


def test_census_failure_has_partial_state_and_no_cleanup_authority(tmp_path):
    cfg, _ = _fixture(tmp_path)
    receipt = mw.create_worktree(cfg, "fixture", "census", "audit")
    path = Path(receipt["workspace"])
    path.rename(path.with_name("preserved-census"))
    result = mw.census(cfg)["repositories"]["fixture"]
    assert result["state"] == "PARTIAL"
    row = result["worktrees"][0]
    assert row["dirty"] is None
    assert row["observation_state"] == "UNKNOWN"
    assert row["null_reason"] == "GIT_STATUS_UNAVAILABLE"


def test_successful_repeat_bootstrap_does_not_claim_zero_mutation(tmp_path, monkeypatch, capsys):
    cfg, _ = _fixture(tmp_path)
    monkeypatch.setattr(mw, "load_config", lambda _: cfg)
    assert mw.main(["bootstrap", "--repo", "fixture"]) == 0
    capsys.readouterr()
    assert mw.main(["bootstrap", "--repo", "fixture"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["receipt"][0]["created"] is False
    assert payload["effect"] == "APPLIED"
