"""The existing census must not report allocatable capacity from one volume."""
import pytest

from scripts import mini_worktree as mw
from test_mini_worktree import _fixture


@pytest.mark.parametrize("hot,store,state,allowed", [
    (100, 100, "READY", True),
    (0, 100, "LOW_SPACE", False),
    (100, 0, "LOW_SPACE", False),
    (100, None, "UNKNOWN", False),
    (None, 100, "UNKNOWN", False),
])
def test_census_projects_both_allocation_targets_without_creating_work(tmp_path, monkeypatch, hot, store, state, allowed):
    cfg, _ = _fixture(tmp_path)
    monkeypatch.setattr(mw, "_free_bytes", lambda p: hot if p == cfg.hot_root else store)
    result = mw.census(cfg)
    assert result["free_bytes"] == hot
    assert result["store_free_bytes"] == store
    assert result["storage"]["state"] == state
    assert result["storage"]["new_allocation_allowed"] is allowed
    assert result["storage"]["reservation"] is False
    assert not cfg.store_root.exists()
    assert not cfg.hot_root.exists()


def test_capacity_observation_failure_does_not_hide_registered_worktrees(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    created = mw.create_worktree(cfg, "fixture", "still-here", "same-session")
    def broken(path):
        raise OSError("unavailable disk telemetry")
    monkeypatch.setattr(mw, "_free_bytes", broken)
    result = mw.census(cfg)
    assert result["storage"]["state"] == "UNKNOWN"
    assert result["storage"]["new_allocation_allowed"] is False
    assert result["free_bytes"] is None
    assert result["store_free_bytes"] is None
    rows = result["repositories"]["fixture"]["worktrees"]
    assert len(rows) == 1 and rows[0]["path"] == created["workspace"]
    assert rows[0]["dirty"] is False
