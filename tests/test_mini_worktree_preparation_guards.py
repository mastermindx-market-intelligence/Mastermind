"""Early Git custody and completed-preparation evidence, on local fixtures only."""
import json
from pathlib import Path

import pytest

from scripts import mini_worktree as mw
from test_mini_worktree import _fixture, _git


def test_new_worktree_is_locked_before_first_sparse_materialization(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    actual = mw._apply_sparse_profile
    seen = []
    def hydrate(path, includes, **kwargs):
        if path.is_relative_to(cfg.hot_root):
            record = mw._registered_at(cfg.store_root / "fixture", path)
            assert record is not None and record.get("locked", "").startswith(mw.LOCK_PREFIX)
            seen.append(record["locked"])
        return actual(path, includes, **kwargs)
    monkeypatch.setattr(mw, "_apply_sparse_profile", hydrate)
    receipt = mw.create_worktree(cfg, "fixture", "early-lock", "same-session")
    assert seen == [receipt["lock_reason"]]


def _interrupt(cfg, monkeypatch, name):
    actual = mw._apply_sparse_profile
    def fail(path, includes, **kwargs):
        if path.is_relative_to(cfg.hot_root):
            (path / "partial-evidence.txt").write_text("preserve")
            raise mw.MiniWorktreeError("injected materialization interruption")
        return actual(path, includes, **kwargs)
    monkeypatch.setattr(mw, "_apply_sparse_profile", fail)
    with pytest.raises(mw.MiniWorktreeError, match="injected materialization"):
        mw.create_worktree(cfg, "fixture", name, "same-session")
    return cfg.hot_root / "fixture" / name


def test_failed_materialization_preserves_custody_and_refuses_false_resume(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    path = _interrupt(cfg, monkeypatch, "interrupted")
    record = mw._registered_at(cfg.store_root / "fixture", path)
    assert record.get("locked", "").startswith(mw.LOCK_PREFIX)
    with pytest.raises(mw.MiniWorktreeError, match="preparation incomplete"):
        mw.create_worktree(cfg, "fixture", "interrupted", "same-session")
    assert (path / "partial-evidence.txt").read_text() == "preserve"


def test_interrupted_preparation_census_is_partial_not_ready(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    path = _interrupt(cfg, monkeypatch, "census-pending")
    rowset = mw.census(cfg)["repositories"]["fixture"]
    assert rowset["state"] == "PARTIAL"
    assert len(rowset["worktrees"]) == 1
    row = rowset["worktrees"][0]
    assert row["path"] == str(path)
    assert row["observation_state"] == "UNKNOWN"
    assert row["null_reason"] == "WORKTREE_PREPARATION_INCOMPLETE"


@pytest.mark.parametrize("damage", ["missing", "foreign", "duplicate"])
def test_preparation_evidence_cannot_be_missing_or_from_another_operation(tmp_path, monkeypatch, damage):
    cfg, _ = _fixture(tmp_path)
    first = mw.create_worktree(cfg, "fixture", "checked", "same-session")
    path = Path(first["workspace"])
    key = "mastermind.miniPrepared"
    if damage == "missing":
        _git(path, "config", "--worktree", "--unset-all", key)
    elif damage == "foreign":
        _git(path, "config", "--worktree", key, "another-operation")
    else:
        _git(path, "config", "--worktree", "--add", key, first["lock_reason"])
    def forbidden(*args, **kwargs):
        raise AssertionError("incomplete resume must not bootstrap")
    monkeypatch.setattr(mw, "bootstrap_repo", forbidden)
    with pytest.raises(mw.MiniWorktreeError, match="preparation incomplete"):
        mw.create_worktree(cfg, "fixture", "checked", "same-session")
    assert path.is_dir()


def test_successful_preparation_is_bound_to_worktree_identity(tmp_path):
    cfg, _ = _fixture(tmp_path)
    first = mw.create_worktree(cfg, "fixture", "first", "same-session")
    path = Path(first["workspace"])
    assert first["lock_reason"].startswith("mastermind-mini-hot:v2 ")
    assert _git(path, "config", "--worktree", "--get-all", "mastermind.miniPrepared") == first["lock_reason"]
    assert mw.create_worktree(cfg, "fixture", "first", "same-session")["reused"] is True
    assert mw.census(cfg)["repositories"]["fixture"]["state"] == "READY"


def test_legacy_successful_session_stays_resumable_without_new_marker(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    first = mw.create_worktree(cfg, "fixture", "legacy", "legacy-session")
    path = Path(first["workspace"])
    store = cfg.store_root / "fixture"
    legacy_reason = "mastermind-mini-hot:v1 repo=fixture name=legacy session=legacy-session"
    _git(store, "worktree", "unlock", str(path))
    _git(store, "worktree", "lock", "--reason", legacy_reason, str(path))
    mw._run(("git", "-C", str(path), "config", "--worktree", "--unset-all", "mastermind.miniPrepared"), check=False)
    marker = path / "active-unpublished.txt"
    marker.write_text("keep this")
    def forbidden(*args, **kwargs):
        raise AssertionError("legacy resume must not fetch or check new-allocation space")
    monkeypatch.setattr(mw, "bootstrap_repo", forbidden)
    monkeypatch.setattr(mw, "_free_bytes", forbidden)
    result = mw.create_worktree(cfg, "fixture", "legacy", "legacy-session")
    assert result["reused"] is True
    assert result["lock_reason"] == legacy_reason
    assert marker.read_text() == "keep this"


def test_head_movement_during_hydration_never_qualifies_preparation(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    actual = mw._apply_sparse_profile
    def moved(path, includes, **kwargs):
        result = actual(path, includes, **kwargs)
        if path.is_relative_to(cfg.hot_root):
            _git(path, "config", "user.name", "Fixture")
            _git(path, "config", "user.email", "fixture@example.invalid")
            _git(path, "commit", "--allow-empty", "-qm", "unrequested movement")
        return result
    monkeypatch.setattr(mw, "_apply_sparse_profile", moved)
    with pytest.raises(mw.MiniWorktreeError, match="prepared workspace identity"):
        mw.create_worktree(cfg, "fixture", "moved", "same-session")
    with pytest.raises(mw.MiniWorktreeError, match="preparation incomplete"):
        mw.create_worktree(cfg, "fixture", "moved", "same-session")


def test_low_space_after_hydration_keeps_unqualified_locked_workspace(tmp_path, monkeypatch, capsys):
    cfg, _ = _fixture(tmp_path)
    actual = mw._apply_sparse_profile
    free = {"bytes": 100}
    monkeypatch.setattr(mw, "_free_bytes", lambda p: free["bytes"])
    monkeypatch.setattr(mw, "load_config", lambda p: cfg)
    def hydrate(path, includes, **kwargs):
        result = actual(path, includes, **kwargs)
        if path.is_relative_to(cfg.hot_root):
            free["bytes"] = 0
        return result
    monkeypatch.setattr(mw, "_apply_sparse_profile", hydrate)
    assert mw.main(["create", "--repo", "fixture", "--name", "disk-full", "--session-id", "same-session"]) == 2
    refusal = json.loads(capsys.readouterr().err)
    assert refusal["effect"] == "EFFECT_UNKNOWN"
    assert refusal["reconciliation_required"] is True
    path = cfg.hot_root / "fixture" / "disk-full"
    record = mw._registered_at(cfg.store_root / "fixture", path)
    assert record["locked"].startswith(mw.LOCK_PREFIX)
    free["bytes"] = 100
    with pytest.raises(mw.MiniWorktreeError, match="preparation incomplete"):
        mw.create_worktree(cfg, "fixture", "disk-full", "same-session")
    assert mw.census(cfg)["repositories"]["fixture"]["state"] == "PARTIAL"


def test_prepared_marker_is_not_shared_with_the_source_store(tmp_path):
    cfg, _ = _fixture(tmp_path)
    receipt = mw.create_worktree(cfg, "fixture", "private-marker", "same-session")
    store = cfg.store_root / "fixture"
    result = mw._run(("git", "-C", str(store), "config", "--local", "--get-all", "mastermind.miniPrepared"), check=False)
    assert result.returncode == 1
    assert mw._preparation_is_complete(Path(receipt["workspace"]), receipt["lock_reason"])
