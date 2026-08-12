from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from control_plane.executive_workspace import (
    AssignmentSealError,
    WorkspaceError,
    prepare_credentialless_clone,
    seal_control_owned_paths,
)


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.name", "Executive Test")
    _git(source, "config", "user.email", "executive@example.invalid")
    (source / "README.md").write_text("proof fixture\n", encoding="utf-8")
    _git(source, "add", "README.md")
    _git(source, "commit", "-qm", "fixture")
    return source, _git(source, "rev-parse", "HEAD")


def test_prepares_exact_sha_private_clone_without_remote(tmp_path):
    source, base_sha = _repository(tmp_path)
    receipt = prepare_credentialless_clone(
        source,
        tmp_path / "workspaces",
        job_id="JOB-001",
        base_sha=base_sha,
    )
    workspace = Path(receipt.workspace_path)

    assert receipt.base_sha == base_sha
    assert receipt.branch == "codex/job-job-001"
    assert receipt.remote_count == 0
    assert receipt.git_dir_is_private is True
    assert (workspace / ".git").is_dir()
    assert _git(workspace, "remote") == ""
    assert _git(workspace, "status", "--porcelain=v1") == ""


def test_refuses_existing_destination_and_unsafe_job_id(tmp_path):
    source, base_sha = _repository(tmp_path)
    root = tmp_path / "workspaces"
    prepare_credentialless_clone(source, root, job_id="JOB-001", base_sha=base_sha)

    with pytest.raises(WorkspaceError, match="already exists"):
        prepare_credentialless_clone(source, root, job_id="JOB-001", base_sha=base_sha)
    with pytest.raises(WorkspaceError, match="unsafe"):
        prepare_credentialless_clone(source, root, job_id="../escape", base_sha=base_sha)


def test_refuses_unknown_base_commit(tmp_path):
    source, _ = _repository(tmp_path)

    with pytest.raises(WorkspaceError, match="workspace command failed"):
        prepare_credentialless_clone(source, tmp_path / "workspaces", job_id="JOB-002", base_sha="0" * 40)


def test_exact_sha_workspace_can_be_shared_with_only_the_worker_group(tmp_path):
    source, base_sha = _repository(tmp_path)
    receipt = prepare_credentialless_clone(
        source,
        tmp_path / "workspaces",
        job_id="JOB-003",
        base_sha=base_sha,
        shared_gid=os.getegid(),
        shared_write_paths=("research/proof/receipt.md",),
    )
    workspace = Path(receipt.workspace_path)

    assert receipt.base_sha == base_sha
    assert receipt.workspace_gid == os.getegid()
    assert receipt.workspace_mode & 0o070 == 0o050
    assert receipt.workspace_mode & 0o007 == 0
    assert stat.S_IMODE((workspace / "README.md").stat().st_mode) & 0o070 == 0o040
    assert stat.S_IMODE((workspace / ".git" / "config").stat().st_mode) & 0o030 == 0
    assert stat.S_IMODE((workspace / "research" / "proof").stat().st_mode) == 0o770
    assert _git(workspace, "rev-parse", "HEAD") == base_sha
    assert _git(workspace, "remote") == ""


def test_shared_write_paths_reject_protected_or_escaping_targets(tmp_path):
    source, base_sha = _repository(tmp_path)
    for index, unsafe in enumerate(("../escape", ".git/config", ".codex/config.toml")):
        with pytest.raises(WorkspaceError, match="shared write"):
            prepare_credentialless_clone(
                source,
                tmp_path / f"workspaces-{index}",
                job_id=f"JOB-{100 + index}",
                base_sha=base_sha,
                shared_gid=os.getegid(),
                shared_write_paths=(unsafe,),
            )


def test_terminal_assignment_seal_revokes_group_traversal_at_both_boundaries(
    tmp_path: Path,
):
    workspace = tmp_path / "workspaces" / "assigned"
    run_dir = tmp_path / "runs" / "ATT-001"
    workspace.mkdir(parents=True, mode=0o750)
    run_dir.mkdir(parents=True, mode=0o770)
    (workspace / "artifact.txt").write_text("preserved\n", encoding="utf-8")

    receipt = seal_control_owned_paths(
        {"workspace": workspace, "run": run_dir}, control_uid=os.geteuid()
    )

    assert receipt["passed"] is True
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
    assert receipt["paths"]["workspace"]["after"]["inode"] == workspace.stat().st_ino
    assert receipt["paths"]["run"]["worker_traversal_revoked"] is True
    assert (workspace / "artifact.txt").read_text(encoding="utf-8") == "preserved\n"


def test_terminal_assignment_seal_fails_closed_for_unowned_or_world_boundary(
    tmp_path: Path,
):
    workspace = tmp_path / "workspace"
    run_dir = tmp_path / "run"
    workspace.mkdir(mode=0o755)
    run_dir.mkdir(mode=0o700)

    with pytest.raises(AssignmentSealError, match="failed closed"):
        seal_control_owned_paths({"workspace": workspace, "run": run_dir})

    assert stat.S_IMODE(run_dir.stat().st_mode) == 0o700
