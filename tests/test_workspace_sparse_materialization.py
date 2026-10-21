"""Real-Git creation regressions: sparse before hydration, never active-tree retrofit."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from control_plane import executive_workspace as ew


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True,
        text=True, timeout=20,
    ).stdout.strip()


def source_repo(tmp_path: Path, *, policy=None) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-q")
    git(source, "config", "user.name", "Storage regression")
    git(source, "config", "user.email", "storage@example.invalid")
    git(source, "config", "extensions.worktreeConfig", "true")
    for name in ("engine/main.py", "data/large.bin", "site/large.bin", "README.md"):
        p = source / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("fixture\n")
    config = source / "config/sparse_worktree.json"
    config.parent.mkdir()
    config.write_text(json.dumps(policy if policy is not None else {
        "enabled": True, "exclude_dirs": ["data", "site"], "_comment": "canonical profile",
    }))
    git(source, "add", ".")
    git(source, "commit", "-qm", "source")
    return source, git(source, "rev-parse", "HEAD")


def linked(source: Path, root: Path, base: str):
    return ew.prepare_linked_worktree(
        source, root, operation_id="sparse-test", lane="web", base_sha=base,
        branch="sol/sparse-test",
    )


def test_linked_never_materializes_excluded_files_and_preserves_source_config(tmp_path, monkeypatch):
    source, base = source_repo(tmp_path)
    source_config = (source / ".git/config").read_bytes()
    root = tmp_path / "workspaces"
    destination = root / "web/sparse-test"
    calls = []
    actual = ew._run

    def observe(argv, *, cwd, env):
        result = actual(argv, cwd=cwd, env=env)
        calls.append(tuple(argv))
        assert not (destination / "data/large.bin").exists(), "full hydration occurred"
        assert not (destination / "site/large.bin").exists(), "full hydration occurred"
        return result

    monkeypatch.setattr(ew, "_run", observe)
    receipt = linked(source, root, base)
    assert Path(receipt.workspace_path) == destination
    assert (destination / "engine/main.py").is_file()
    assert git(destination, "status", "--porcelain") == ""
    assert git(destination, "config", "--worktree", "--get", "core.sparseCheckout") == "true"
    assert (source / ".git/config").read_bytes() == source_config
    assert (source / "data/large.bin").is_file()
    adds = [a for a in calls if "worktree" in a and "add" in a]
    assert len(adds) == 1 and "--no-checkout" in adds[0]
    assert "--lock" in adds[0], "custody lock must be acquired with creation"


def test_private_worker_uses_exact_base_profile_not_dirty_source_or_source_head(tmp_path, monkeypatch):
    source, base = source_repo(tmp_path)
    (source / "config/sparse_worktree.json").write_text(json.dumps({
        "enabled": True, "exclude_dirs": ["engine"],
    }))
    git(source, "add", ".")
    git(source, "commit", "-qm", "different current profile")
    (source / "config/sparse_worktree.json").write_text("not valid JSON")
    root = tmp_path / "workers"
    destination = root / "job-sparse"
    actual = ew._run

    def observe(argv, *, cwd, env):
        result = actual(argv, cwd=cwd, env=env)
        assert not (destination / "data/large.bin").exists(), "full private checkout occurred"
        return result

    monkeypatch.setattr(ew, "_run", observe)
    receipt = ew.prepare_credentialless_clone(source, root, job_id="JOB-SPARSE", base_sha=base)
    assert receipt.base_sha == base
    assert (destination / "engine/main.py").is_file()
    assert not (destination / "data").exists()
    assert (destination / ".git").is_dir()
    assert not (destination / ".git/objects/info/alternates").exists()
    assert git(destination, "remote") == ""
    assert git(destination, "status", "--porcelain") == ""
    object_path = git(source, "rev-parse", "HEAD")
    rel = Path("objects") / object_path[:2] / object_path[2:]
    assert (source / ".git" / rel).stat().st_ino != (destination / ".git" / rel).stat().st_ino


@pytest.mark.parametrize("policy", [
    {"enabled": "yes", "exclude_dirs": ["data"]},
    {"enabled": True, "exclude_dirs": "data"},
    {"enabled": True, "exclude_dirs": ["../outside"]},
    {"enabled": True, "exclude_dirs": [".git"]},
    {"enabled": True, "exclude_dirs": ["data", "data"]},
    {"enabled": True, "exclude_dirs": ["data/child"]},
])
def test_invalid_pinned_policy_refused_before_destination_creation(tmp_path, policy):
    source, base = source_repo(tmp_path, policy=policy)
    root = tmp_path / "workspaces"
    with pytest.raises(ew.WorkspaceError, match="sparse"):
        linked(source, root, base)
    assert not (root / "web/sparse-test").exists()
    assert "sol/sparse-test" not in git(source, "branch", "--list")


def test_symlink_policy_is_not_followed(tmp_path):
    source, _ = source_repo(tmp_path)
    path = source / "config/sparse_worktree.json"
    path.unlink()
    path.symlink_to("../README.md")
    git(source, "add", ".")
    git(source, "commit", "-qm", "symlink policy")
    with pytest.raises(ew.WorkspaceError, match="sparse"):
        linked(source, tmp_path / "workspaces", git(source, "rev-parse", "HEAD"))


def test_duplicate_policy_keys_are_refused(tmp_path):
    source, _ = source_repo(tmp_path)
    (source / "config/sparse_worktree.json").write_text(
        '{"enabled":false,"enabled":true,"exclude_dirs":["data"]}'
    )
    git(source, "add", ".")
    git(source, "commit", "-qm", "ambiguous policy")
    with pytest.raises(ew.WorkspaceError, match="sparse"):
        linked(source, tmp_path / "workspaces", git(source, "rev-parse", "HEAD"))


def test_sparse_linked_creation_requires_host_worktree_config_enrollment(tmp_path):
    source, base = source_repo(tmp_path)
    git(source, "config", "--unset", "extensions.worktreeConfig")
    before = (source / ".git/config").read_bytes()
    with pytest.raises(ew.WorkspaceError, match="worktreeConfig"):
        linked(source, tmp_path / "workspaces", base)
    assert (source / ".git/config").read_bytes() == before


def test_explicitly_disabled_profile_preserves_full_checkout(tmp_path):
    source, base = source_repo(tmp_path, policy={"enabled": False, "exclude_dirs": ["data"]})
    receipt = linked(source, tmp_path / "workspaces", base)
    assert (Path(receipt.workspace_path) / "data/large.bin").is_file()


def test_worker_granted_write_roots_remain_materialized_and_git_private(tmp_path):
    source, base = source_repo(tmp_path)
    receipt = ew.prepare_credentialless_clone(
        source, tmp_path / "workers", job_id="JOB-WRITE", base_sha=base,
        shared_gid=os.getegid(), shared_write_paths=("data/large.bin",),
    )
    destination = Path(receipt.workspace_path)
    assert (destination / "data/large.bin").read_text() == "fixture\n"
    assert not (destination / "site").exists()
    ew.validate_shared_git_handoff(destination, control_uid=os.geteuid(), shared_gid=os.getegid())


def test_reuse_never_retrofits_or_discards_active_edits(tmp_path):
    source, base = source_repo(tmp_path)
    root = tmp_path / "workspaces"
    first = linked(source, root, base)
    destination = Path(first.workspace_path)
    git(destination, "sparse-checkout", "add", "data")
    (destination / "data/large.bin").write_text("active uncommitted changes\n")
    again = linked(source, root, base)
    assert again.reused is True
    assert (destination / "data/large.bin").read_text() == "active uncommitted changes\n"


def test_sparse_configuration_failure_discards_only_new_workspace(tmp_path, monkeypatch):
    source, base = source_repo(tmp_path)
    root = tmp_path / "workspaces"
    actual = ew._run_bytes_with_input

    def fail_sparse(argv, **kwargs):
        if "sparse-checkout" in argv:
            raise ew.WorkspaceError("sparse fixture refusal")
        return actual(argv, **kwargs)

    monkeypatch.setattr(ew, "_run_bytes_with_input", fail_sparse)
    with pytest.raises(ew.WorkspaceError, match="sparse fixture refusal"):
        linked(source, root, base)
    assert not (root / "web/sparse-test").exists()
    assert (source / "data/large.bin").is_file()
    assert "sol/sparse-test" not in git(source, "branch", "--list")
