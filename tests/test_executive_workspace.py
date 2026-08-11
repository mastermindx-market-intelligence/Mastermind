from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from control_plane.executive_workspace import WorkspaceError, prepare_credentialless_clone


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
