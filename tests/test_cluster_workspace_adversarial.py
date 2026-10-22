"""Independent exact-head review cases; fixtures only, no production writes."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import pytest
from scripts import mini_worktree as mw
from test_mini_worktree import _fixture, _git


def test_missing_registered_workspace_is_not_reported_clean(tmp_path):
    cfg, _ = _fixture(tmp_path)
    result = mw.create_worktree(cfg, "fixture", "missing", "audit")
    path = Path(result["workspace"])
    path.rename(path.with_name("preserved-moved-workspace"))
    try:
        rows = mw.census(cfg)["repositories"]["fixture"]["worktrees"]
    except mw.MiniWorktreeError:
        return  # A typed fail-closed census is also acceptable.
    assert rows[0]["dirty"] is None, rows[0]
    assert rows[0].get("observation_state") == "UNKNOWN", rows[0]


def test_failed_checkout_cannot_claim_no_effect(tmp_path, monkeypatch, capsys):
    cfg, _ = _fixture(tmp_path)
    monkeypatch.setattr(mw, "load_config", lambda _: cfg)
    original = mw._apply_sparse_profile
    def fail_only_worker(path, includes):
        if path.is_relative_to(cfg.hot_root):
            raise mw.MiniWorktreeError("injected post-add checkout failure")
        return original(path, includes)
    monkeypatch.setattr(mw, "_apply_sparse_profile", fail_only_worker)
    assert mw.main(["create", "--repo", "fixture", "--name", "failed", "--session-id", "audit"]) == 2
    payload = json.loads(capsys.readouterr().err)
    assert (cfg.hot_root / "fixture" / "failed").exists()
    assert payload["effect"] != "NOT_APPLIED", payload


def test_existing_exact_session_resume_needs_no_remote_fetch(tmp_path, monkeypatch):
    cfg, _ = _fixture(tmp_path)
    first = mw.create_worktree(cfg, "fixture", "resume", "audit")
    original = mw._run
    def deny_network(args, **kwargs):
        if "fetch" in args or "clone" in args:
            raise mw.MiniWorktreeError("network deliberately unavailable")
        return original(args, **kwargs)
    monkeypatch.setattr(mw, "_run", deny_network)
    resumed = mw.create_worktree(cfg, "fixture", "resume", "audit")
    assert resumed["reused"] is True
    assert resumed["workspace"] == first["workspace"]


def test_creation_cannot_advance_to_a_different_default_head(tmp_path, monkeypatch):
    cfg, source = _fixture(tmp_path)
    original_bootstrap = mw.bootstrap_repo
    frozen = {}
    def remote_moves_after_snapshot(config, key):
        result = original_bootstrap(config, key)
        frozen["base"] = result["remote_head"]
        (source / "README.md").write_text("newer uncommissioned source\n")
        _git(source, "add", "README.md")
        _git(source, "commit", "-qm", "remote moved")
        _git(source, "push", str(tmp_path / "remote.git"), "main")
        _git(config.store_root / key, "fetch", "origin", "main")
        return result
    monkeypatch.setattr(mw, "bootstrap_repo", remote_moves_after_snapshot)
    receipt = mw.create_worktree(cfg, "fixture", "drift", "audit")
    assert receipt["head"] == frozen["base"], receipt
