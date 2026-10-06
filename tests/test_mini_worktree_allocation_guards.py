"""Allocation guard regressions; only disposable Git fixtures are mutated."""
from pathlib import Path

import pytest

from scripts import mini_worktree as mw
from test_mini_worktree import _fixture, _git


def test_low_object_store_volume_refuses_before_clone(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    monkeypatch.setattr(mw, "_free_bytes", lambda p: 0 if p == cfg.store_root else 100)
    with pytest.raises(mw.MiniWorktreeError, match="STORE_STORAGE_LOW_SPACE"):
        mw.bootstrap_repo(cfg, "fixture")
    assert not cfg.store_root.exists()
    assert not cfg.hot_root.exists()


@pytest.mark.parametrize("side", ["hot", "store"])
@pytest.mark.parametrize("observation", [None, True, -1, "100"])
def test_unknown_capacity_refuses_without_allocation(tmp_path, monkeypatch, side, observation):
    cfg, _ = _fixture(tmp_path)
    target = cfg.hot_root if side == "hot" else cfg.store_root
    monkeypatch.setattr(mw, "_free_bytes", lambda p: observation if p == target else 100)
    with pytest.raises(mw.MiniWorktreeError, match="STORAGE_OBSERVATION_UNAVAILABLE"):
        mw.bootstrap_repo(cfg, "fixture")
    assert not cfg.store_root.exists()
    assert not cfg.hot_root.exists()


def test_clone_capacity_loss_stops_before_fetch_and_preserves_store(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    actual = mw._run
    state = {"free": 100, "fetches": 0}
    monkeypatch.setattr(mw, "_free_bytes", lambda p: state["free"])
    def run(argv, **kwargs):
        state["fetches"] += int("fetch" in argv)
        result = actual(argv, **kwargs)
        if "clone" in argv:
            state["free"] = 0
        return result
    monkeypatch.setattr(mw, "_run", run)
    with pytest.raises(mw.MiniWorktreeError, match="STORAGE_LOW_SPACE"):
        mw.bootstrap_repo(cfg, "fixture")
    assert (cfg.store_root / "fixture" / ".git").is_dir()
    assert state["fetches"] == 0


def test_post_bootstrap_capacity_loss_stops_before_worktree_add(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    actual = mw.bootstrap_repo
    state = {"free": 100}
    monkeypatch.setattr(mw, "_free_bytes", lambda p: state["free"])
    def bootstrap(config, key):
        result = actual(config, key)
        state["free"] = 0
        return result
    monkeypatch.setattr(mw, "bootstrap_repo", bootstrap)
    with pytest.raises(mw.MiniWorktreeError, match="STORAGE_LOW_SPACE"):
        mw.create_worktree(cfg, "fixture", "pressure", "session-pressure")
    assert not (cfg.hot_root / "fixture" / "pressure").exists()
    assert "mmx/fixture/pressure" not in _git(cfg.store_root / "fixture", "branch", "--list")


def test_post_checkout_capacity_loss_does_not_report_success(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    actual = mw._apply_sparse_profile
    state = {"free": 100}
    monkeypatch.setattr(mw, "_free_bytes", lambda p: state["free"])
    def hydrate(path, includes, **kwargs):
        result = actual(path, includes, **kwargs)
        if path.is_relative_to(cfg.hot_root):
            state["free"] = 0
        return result
    monkeypatch.setattr(mw, "_apply_sparse_profile", hydrate)
    with pytest.raises(mw.MiniWorktreeError, match="STORAGE_LOW_SPACE"):
        mw.create_worktree(cfg, "fixture", "during-checkout", "session-pressure")
    assert (cfg.hot_root / "fixture" / "during-checkout").is_dir()


def test_existing_session_resume_never_needs_a_new_space_observation(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    first = mw.create_worktree(cfg, "fixture", "kept", "kept-session")
    marker = Path(first["workspace"]) / "unpublished.txt"
    marker.write_text("must survive")
    def unavailable(path):
        raise OSError("disk telemetry unavailable")
    monkeypatch.setattr(mw, "_free_bytes", unavailable)
    resumed = mw.create_worktree(cfg, "fixture", "kept", "kept-session")
    assert resumed["reused"] is True
    assert marker.read_text() == "must survive"


@pytest.mark.parametrize("stage", ["fetch", "store-hydration"])
def test_bootstrap_capacity_is_rechecked_after_expensive_stages(tmp_path, monkeypatch, stage):
    cfg, _ = _fixture(tmp_path)
    actual_run = mw._run
    actual_sparse = mw._apply_sparse_profile
    state = {"free": 100, "hydrations": 0}
    monkeypatch.setattr(mw, "_free_bytes", lambda p: state["free"])
    def run(argv, **kwargs):
        result = actual_run(argv, **kwargs)
        if stage == "fetch" and "fetch" in argv:
            state["free"] = 0
        return result
    def hydrate(path, includes, **kwargs):
        state["hydrations"] += 1
        result = actual_sparse(path, includes, **kwargs)
        if stage == "store-hydration":
            state["free"] = 0
        return result
    monkeypatch.setattr(mw, "_run", run)
    monkeypatch.setattr(mw, "_apply_sparse_profile", hydrate)
    with pytest.raises(mw.MiniWorktreeError, match="STORAGE_LOW_SPACE"):
        mw.bootstrap_repo(cfg, "fixture")
    assert (cfg.store_root / "fixture" / ".git").is_dir()
    assert state["hydrations"] == (0 if stage == "fetch" else 1)


@pytest.mark.parametrize("side", ["hot", "store"])
def test_capacity_probe_failure_is_typed_and_preserves_no_allocation(tmp_path, monkeypatch, side):
    cfg, _ = _fixture(tmp_path)
    target = cfg.hot_root if side == "hot" else cfg.store_root
    def fail(path):
        if path == target:
            raise OSError("unreadable volume")
        return 100
    monkeypatch.setattr(mw, "_free_bytes", fail)
    with pytest.raises(mw.MiniWorktreeError, match="STORAGE_OBSERVATION_UNAVAILABLE"):
        mw.bootstrap_repo(cfg, "fixture")
    assert not cfg.store_root.exists()
