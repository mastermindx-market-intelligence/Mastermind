from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from control_plane import executive_workspace
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


# ---------------------------------------------------------------------------
# A failed preparation must not leave a corpse behind.
#
# Real-host incident (Executive OS Phase 1C acceptance, 2026-08-14): the
# administrative checkout carried 2,503 loose objects, so `git clone --local
# --no-hardlinks` copied them one file at a time as the control principal on a
# host at load ~29 and blew the 60 s `_run` timeout about 21 % through.  git
# had already written `HEAD -> refs/heads/.invalid` and part of the object
# store, and that half-written directory then failed the NEXT attempt with
# "workspace already exists" and kept the workspace root non-empty, which host
# acceptance refuses outright.  One transient timeout wedged every later run.
# ---------------------------------------------------------------------------


def test_timed_out_clone_leaves_no_partial_workspace(tmp_path, monkeypatch):
    source, head = _repository(tmp_path)
    root = tmp_path / "workspaces"
    destination = root / "job-1"

    real_run = subprocess.run

    def fake_run(argv, **kwargs):
        if "clone" in argv:
            # Reproduce the incident: git creates the destination and writes
            # part of it, then is killed by the timeout.
            git_dir = destination / ".git"
            git_dir.mkdir(parents=True)
            (git_dir / "HEAD").write_text("ref: refs/heads/.invalid\n", encoding="utf-8")
            raise subprocess.TimeoutExpired(cmd=list(argv), timeout=60)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(WorkspaceError, match="workspace command could not run"):
        prepare_credentialless_clone(
            source, root, job_id="JOB-1", base_sha=head
        )

    assert not destination.exists()
    # Only the git supervisor home may remain; no job corpse.
    assert [entry.name for entry in root.iterdir()] == [".supervisor-home"]


def test_failure_after_clone_removes_the_workspace(tmp_path, monkeypatch):
    source, head = _repository(tmp_path)
    root = tmp_path / "workspaces"
    destination = root / "job-2"

    real_run = subprocess.run

    def fake_run(argv, **kwargs):
        # Let the clone succeed, then fail the very next git command so the
        # cleanup path is exercised against a fully created destination.
        if "checkout" in argv:
            raise subprocess.TimeoutExpired(cmd=list(argv), timeout=60)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(WorkspaceError):
        prepare_credentialless_clone(
            source, root, job_id="JOB-2", base_sha=head
        )

    assert not destination.exists()


def test_cleanup_does_not_mask_the_original_failure(tmp_path, monkeypatch):
    """The real cause must survive cleanup, even if discarding fails."""

    source, head = _repository(tmp_path)
    root = tmp_path / "workspaces"

    real_run = subprocess.run

    def fake_run(argv, **kwargs):
        if "clone" in argv:
            (root / "job-3").mkdir(parents=True)
            raise subprocess.TimeoutExpired(cmd=list(argv), timeout=60)
        return real_run(argv, **kwargs)

    def exploding_rmtree(*args, **kwargs):
        raise OSError("cleanup itself failed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(executive_workspace.shutil, "rmtree", exploding_rmtree)

    # The timeout, not the cleanup error, is what the caller sees.
    with pytest.raises(WorkspaceError, match="timed out"):
        prepare_credentialless_clone(
            source, root, job_id="JOB-3", base_sha=head
        )


def test_repeat_preparation_succeeds_after_a_failed_attempt(tmp_path, monkeypatch):
    """The end-to-end property the incident violated: a retry must work."""

    source, head = _repository(tmp_path)
    root = tmp_path / "workspaces"
    real_run = subprocess.run
    attempts = {"count": 0}

    def fake_run(argv, **kwargs):
        if "clone" in argv and attempts["count"] == 0:
            attempts["count"] += 1
            (root / "job-4" / ".git").mkdir(parents=True)
            raise subprocess.TimeoutExpired(cmd=list(argv), timeout=60)
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(WorkspaceError):
        prepare_credentialless_clone(source, root, job_id="JOB-4", base_sha=head)

    # Same job ID, second attempt: this raised "workspace already exists"
    # before the fix.
    receipt = prepare_credentialless_clone(source, root, job_id="JOB-4", base_sha=head)
    assert receipt.base_sha == head
    assert receipt.remote_count == 0


# ---------------------------------------------------------------------------
# The install-side half of the same incident: the administrative checkout must
# be PACKED, because every job clones it with `git clone --local
# --no-hardlinks`, which copies each loose object as an individual file.
# ---------------------------------------------------------------------------

_INSTALL_SH = Path(__file__).resolve().parents[1] / "ops" / "executive_os" / "install.sh"


def test_install_sh_packs_the_administrative_checkout_outside_the_existence_guard():
    install_text = _INSTALL_SH.read_text(encoding="utf-8")
    guard = 'if [ ! -d "$ADMIN_CHECKOUT/.git" ]; then'
    assert guard in install_text
    _, after_guard = install_text.split(guard, 1)
    body, after_fi = after_guard.split("\nfi\n", 1)

    # The repack must NOT sit inside the creation guard: an already-installed
    # host carries the loose objects that caused the incident, and an
    # existence guard that skips the repair is exactly the trap the Codex
    # attestation receipt writer had to be freed from.
    assert "repack" not in body
    assert "repack -ad" in after_fi

    # It must run as the control principal, never as root: git refuses a
    # repository owned by neither the effective UID nor SUDO_UID, and packing
    # as root would leave root-owned pack files in a control-owned checkout.
    repack_line = next(
        line for line in after_fi.splitlines() if "repack -ad" in line
    )
    preceding = after_fi.split("repack -ad", 1)[0]
    assert '/usr/bin/sudo -u "$CONTROL_USER"' in preceding
    assert "repack" in repack_line

    # And the result is verified rather than assumed.
    assert "administrative checkout still holds loose objects after repack" in after_fi


def test_packing_collapses_the_local_clone_to_a_single_object_file(tmp_path):
    """Prove the mechanism the install-side fix depends on, without root.

    `git clone --local --no-hardlinks` copies the source object store.  With
    loose objects that is one filesystem operation per object -- 2,503 of them
    on the real host, which exceeded the 60 s `_run` bound under load.  Packed,
    it is a single pack file.
    """

    source = tmp_path / "loose"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.name", "Executive Test")
    _git(source, "config", "user.email", "executive@example.invalid")
    for index in range(40):
        (source / f"file-{index}.txt").write_text(f"content {index}\n", encoding="utf-8")
        _git(source, "add", f"file-{index}.txt")
        _git(source, "commit", "-qm", f"commit {index}")

    def _object_file_count(repo: Path) -> int:
        objects = repo / ".git" / "objects"
        return sum(1 for path in objects.rglob("*") if path.is_file())

    loose_before = _object_file_count(source)
    assert loose_before > 40, "fixture should carry many loose objects"

    subprocess.run(
        ["git", "clone", "--local", "--no-hardlinks", "--no-checkout",
         str(source), str(tmp_path / "clone-loose")],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    copied_loose = _object_file_count(tmp_path / "clone-loose")

    _git(source, "repack", "-ad")
    subprocess.run(
        ["git", "clone", "--local", "--no-hardlinks", "--no-checkout",
         str(source), str(tmp_path / "clone-packed")],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    copied_packed = _object_file_count(tmp_path / "clone-packed")

    # The packed clone copies an order of magnitude fewer files.
    assert copied_packed < copied_loose / 5
