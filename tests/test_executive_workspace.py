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


def test_tracked_vendor_symlink_is_worker_readable_and_launch_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Regression for the real macOS Phase 1C-A `vendor/macro` failure."""

    source, _ = _repository(tmp_path)
    vendor = source / "vendor"
    vendor.mkdir()
    (vendor / "macro").symlink_to("../macro")
    _git(source, "add", "vendor/macro")
    _git(source, "commit", "-qm", "tracked vendor symlink")
    base_sha = _git(source, "rev-parse", "HEAD")

    shared_links: list[str] = []
    real_share = executive_workspace._share_symlink_with_group

    def observed_share(path: Path, *, shared_gid: int) -> None:
        shared_links.append(path.relative_to(path.parents[1]).as_posix())
        real_share(path, shared_gid=shared_gid)

    monkeypatch.setattr(
        executive_workspace, "_share_symlink_with_group", observed_share
    )
    previous_umask = os.umask(0o077)
    try:
        receipt = prepare_credentialless_clone(
            source,
            tmp_path / "workspaces",
            job_id="JOB-SYMLINK",
            base_sha=base_sha,
            shared_gid=os.getegid(),
            shared_write_paths=("research/proof/receipt.md",),
        )
    finally:
        os.umask(previous_umask)

    workspace = Path(receipt.workspace_path)
    link = workspace / "vendor" / "macro"
    link_info = link.lstat()
    link_mode = stat.S_IMODE(link_info.st_mode)
    assert shared_links == ["vendor/macro"]
    assert stat.S_ISLNK(link_info.st_mode)
    assert link_info.st_gid == os.getegid()
    assert link_mode & stat.S_IRGRP
    assert not link_mode & stat.S_IWGRP
    if os.chmod in os.supports_follow_symlinks:
        assert not link_mode & stat.S_IRWXO
    observation = executive_workspace.observe_launch_cleanliness(
        lambda arguments: subprocess.run(
            ["git", *arguments],
            cwd=workspace,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    )
    assert observation.dirty is False


def test_symlink_permission_repair_fails_closed_when_mode_does_not_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source, _ = _repository(tmp_path)
    vendor = source / "vendor"
    vendor.mkdir()
    (vendor / "macro").symlink_to("../macro")
    _git(source, "add", "vendor/macro")
    _git(source, "commit", "-qm", "tracked vendor symlink")
    base_sha = _git(source, "rev-parse", "HEAD")
    real_chmod = os.chmod

    def unchanged_symlink_mode(path, mode, *, follow_symlinks=True):
        if follow_symlinks is False:
            return None
        return real_chmod(path, mode)

    monkeypatch.setattr(executive_workspace.os, "chmod", unchanged_symlink_mode)
    monkeypatch.setattr(
        executive_workspace.os,
        "supports_follow_symlinks",
        {unchanged_symlink_mode},
    )
    root = tmp_path / "workspaces"
    previous_umask = os.umask(0o077)
    try:
        with pytest.raises(WorkspaceError, match="tracked symlink"):
            prepare_credentialless_clone(
                source,
                root,
                job_id="JOB-SYMLINK-MUTATION",
                base_sha=base_sha,
                shared_gid=os.getegid(),
            )
    finally:
        os.umask(previous_umask)
    assert not (root / "job-symlink-mutation").exists()


def test_launch_cleanliness_definition_includes_ignored_untracked_material():
    calls: list[tuple[str, ...]] = []

    def observe(arguments):
        value = tuple(arguments)
        calls.append(value)
        if value == executive_workspace.LAUNCH_CLEAN_UNTRACKED_ARGS:
            return b"ignored-runtime-file\0"
        return b""

    observation = executive_workspace.observe_launch_cleanliness(observe)

    assert calls == [
        executive_workspace.LAUNCH_CLEAN_STATUS_ARGS,
        executive_workspace.LAUNCH_CLEAN_UNTRACKED_ARGS,
    ]
    assert observation.status == b""
    assert observation.all_untracked == b"ignored-runtime-file\0"
    assert observation.dirty is True


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


# ---------------------------------------------------------------------------
# The SAME incident, next chapter (2026-08-14). The #56 fix above packs the
# administrative checkout with `git repack -ad`, but `repack -ad` packs only
# REACHABLE objects. install.sh removes the checkout's "origin" remote
# (`git remote remove origin`, inside the creation guard, right after the
# initial clone) BEFORE repack ever runs. That deletes the remote-tracking
# refs and orphans anything reachable only through them, so those orphans
# stay loose after repack, install's own hard "count == 0" postcondition
# correctly fires, and install exits 65 -- leaving the host half-installed
# with a stale control config pinned to the previous release.
#
# Reproduced for real against the real repository: 141 refs survived the
# initial `clone --no-hardlinks --no-checkout`, 7 after `remote remove
# origin`; `count: 2533` (`in-pack: 4201`) after `repack -ad` ALONE; `count:
# 0` only after `git prune --expire=now`, with HEAD still resolving to the
# exact expected SHA afterward and the pruned checkout still usable as the
# source for the existing `git clone --local --no-hardlinks` workspace
# clone. The fix below adds exactly that `git prune --expire=now` call, run
# as the same CONTROL_USER principal under the same scrubbed Git environment
# as the repack it follows, between the repack and the existing (unchanged)
# hard assertion.
# ---------------------------------------------------------------------------


def _repository_with_orphaned_history(tmp_path: Path) -> tuple[Path, str]:
    """A source repo shaped like the real incident.

    Reachable history the admin checkout must keep (`main`), PLUS history
    that an ordinary `git clone` fetches -- it mirrors every branch, not
    only the default one -- but that becomes unreachable the instant
    install.sh deletes the "origin" remote: `feature/orphan` never gets a
    local branch ref of its own anywhere in this repository, so once its
    only ref (`refs/remotes/origin/feature/orphan`) is removed along with
    the remote, nothing points at its five commits any more.
    """
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q", "-b", "main")
    _git(source, "config", "user.name", "Executive Test")
    _git(source, "config", "user.email", "executive@example.invalid")
    (source / "a.txt").write_text("base\n", encoding="utf-8")
    _git(source, "add", "a.txt")
    _git(source, "commit", "-qm", "base")
    base_sha = _git(source, "rev-parse", "HEAD")
    (source / "b.txt").write_text("second\n", encoding="utf-8")
    _git(source, "add", "b.txt")
    _git(source, "commit", "-qm", "second")
    expected_sha = _git(source, "rev-parse", "HEAD")

    _git(source, "checkout", "-q", "-b", "feature/orphan", base_sha)
    for index in range(5):
        (source / f"orphan-{index}.txt").write_text(f"orphan {index}\n", encoding="utf-8")
        _git(source, "add", f"orphan-{index}.txt")
        _git(source, "commit", "-qm", f"orphan commit {index}")
    _git(source, "checkout", "-q", "main")
    return source, expected_sha


def _count_objects(repo: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in _git(repo, "count-objects", "-v").splitlines():
        key, _, value = line.partition(":")
        counts[key.strip()] = int(value.strip())
    return counts


def test_install_sh_prunes_unreachable_objects_after_repack_and_before_final_chown():
    """The fix: `git prune --expire=now`, run after repack (the companion
    test below proves repack alone is not enough) and before the existing
    hard "count == 0" postcondition, as the same CONTROL_USER principal
    under the same scrubbed Git environment as the repack it follows --
    never as root, for the same "dubious ownership" / root-owned-pack-files
    reasons the repack call's own comment documents. The postcondition
    itself, and its `exit 65` on failure, are UNCHANGED: this fix satisfies
    the existing guard, it does not weaken it.
    """
    install_text = _INSTALL_SH.read_text(encoding="utf-8")

    repack_marker = '/usr/bin/git -C "$ADMIN_CHECKOUT" repack -ad'
    prune_marker = '/usr/bin/git -C "$ADMIN_CHECKOUT" prune --expire=now'
    assertion_marker = "administrative checkout still holds loose objects after repack"
    assert install_text.count(repack_marker) == 1
    assert install_text.count(prune_marker) == 1
    assert install_text.count(assertion_marker) == 1

    repack_index = install_text.index(repack_marker)
    prune_index = install_text.index(prune_marker)
    assertion_index = install_text.index(assertion_marker)

    # Ownership/mode re-assertion must still run LAST, over whatever prune
    # leaves behind -- not be skipped, and not reordered ahead of prune.
    chown_marker = '/usr/sbin/chown -R "$CONTROL_USER:$CONTROL_GROUP" "$ADMIN_CHECKOUT"'
    chmod_marker = '/bin/chmod -R go-rwx "$ADMIN_CHECKOUT"'
    between_repack_and_assertion = install_text[repack_index:assertion_index]
    assert between_repack_and_assertion.count(chown_marker) == 1
    assert between_repack_and_assertion.count(chmod_marker) == 1
    chown_index = install_text.index(chown_marker, repack_index)
    chmod_index = install_text.index(chmod_marker, repack_index)

    # Exact ordering: repack -> prune -> chown -> chmod -> hard assertion.
    assert repack_index < prune_index < chown_index < chmod_index < assertion_index

    # The prune call mirrors the repack call's invocation shape byte for
    # byte: same control principal, same scrubbed environment, never root.
    preceding_repack = install_text[:repack_index]
    repack_invocation = preceding_repack[preceding_repack.rindex("/usr/bin/sudo -u"):]
    preceding_prune = install_text[:prune_index]
    prune_invocation = preceding_prune[preceding_prune.rindex("/usr/bin/sudo -u"):]
    for line in (
        '/usr/bin/sudo -u "$CONTROL_USER" /usr/bin/env -i \\',
        'PATH=/usr/bin:/bin:/usr/sbin:/sbin HOME="$CONTROL_HOME" \\',
        "LANG=C.UTF-8 LC_ALL=C.UTF-8 \\",
        "GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1 \\",
    ):
        assert line in repack_invocation
        assert line in prune_invocation

    # The postcondition itself is untouched: still a hard `exit 65`, never
    # downgraded to a warning.
    assert "exit 65" in install_text[assertion_index:assertion_index + 200]

    # Never widen to `git gc` -- forbidden by the CEO ruling absent evidence
    # prune is insufficient, and the reproduction found it sufficient.
    admin_checkout_block = install_text[
        install_text.index('ADMIN_CHECKOUT="$RUNTIME_ROOT'):assertion_index
    ]
    assert "git gc" not in admin_checkout_block
    assert " gc " not in admin_checkout_block

    # The comment documents the intended sequence and why repack alone
    # cannot satisfy the postcondition once a remote has been removed.
    comment_block = install_text[repack_index:prune_index]
    assert "remote removed" in comment_block
    assert "repack reachable objects" in comment_block
    assert "prune unreachable" in comment_block
    assert "verify zero loose objects" in comment_block
    assert "not company state" in comment_block


def test_prune_after_repack_reaches_zero_loose_objects_and_stays_clonable(tmp_path: Path):
    """The full fix, proved end to end without root.

    Covers all eight points of the regression spec: a source repo with
    reachable history PLUS orphanable history (1), cloned the way
    install.sh clones the admin checkout (2), with its remote removed
    exactly as install.sh removes it (3) -- proving `repack -ad` alone is
    not enough (4) -- then `git prune --expire=now` (5) reaches zero loose
    objects (6), HEAD still resolves to the exact expected SHA (7), and the
    pruned checkout is still clean and usable as the source for the
    existing `git clone --local --no-hardlinks` workspace clone that
    `prepare_credentialless_clone` performs per job (8).
    """
    source, expected_sha = _repository_with_orphaned_history(tmp_path)
    admin_checkout = tmp_path / "admin-checkout"

    # 1 & 2: clone the admin checkout exactly the way install.sh's creation
    # guard does.
    subprocess.run(
        ["git", "clone", "--no-hardlinks", "--no-checkout", str(source), str(admin_checkout)],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    _git(admin_checkout, "checkout", "--detach", expected_sha)

    # 3: remove origin / remote-tracking refs exactly as install.sh does.
    remote_refs_before = _git(admin_checkout, "for-each-ref", "refs/remotes")
    assert "feature/orphan" in remote_refs_before, "fixture must fetch the orphan branch too"
    _git(admin_checkout, "remote", "remove", "origin")
    assert _git(admin_checkout, "remote") == ""
    assert _git(admin_checkout, "for-each-ref", "refs/remotes") == ""
    heads_after_removal = _git(admin_checkout, "for-each-ref", "refs/heads")
    assert heads_after_removal.count("\n") == 0, "exactly one local ref (main) should survive"
    assert expected_sha in heads_after_removal and "refs/heads/main" in heads_after_removal

    # 4: repack ALONE must leave loose objects -- the exact defect real-host
    # install.sh hit.
    _git(admin_checkout, "repack", "-ad")
    after_repack = _count_objects(admin_checkout)
    assert after_repack["count"] > 0, (
        "fixture produced no orphaned objects after repack -ad -- the "
        "orphan branch history must be unreachable from refs/heads/main "
        "and detached HEAD, or this test is vacuous"
    )

    # 5: the fix -- prune unreachable loose objects.
    _git(admin_checkout, "prune", "--expire=now")

    # 6: zero loose objects, matching install.sh's hard assertion exactly
    # (the "count" field of `git count-objects -v`).
    after_prune = _count_objects(admin_checkout)
    assert after_prune["count"] == 0
    # The reachable, packed history is untouched by prune.
    assert after_prune["in-pack"] == after_repack["in-pack"]

    # 7: HEAD still resolves to the exact expected SHA, and the checkout is
    # still clean.
    assert _git(admin_checkout, "rev-parse", "HEAD") == expected_sha
    assert _git(admin_checkout, "status", "--porcelain=v1") == ""

    # 8: the pruned checkout is still usable as the source for the SAME
    # `git clone --local --no-hardlinks` workspace clone
    # prepare_credentialless_clone performs per job -- proving prune did not
    # remove or corrupt anything the workspace clone actually needs.
    receipt = prepare_credentialless_clone(
        admin_checkout,
        tmp_path / "workspaces",
        job_id="JOB-PRUNE-1",
        base_sha=expected_sha,
    )
    assert receipt.base_sha == expected_sha
    assert receipt.remote_count == 0
    workspace = Path(receipt.workspace_path)
    # Raises if the base commit object is missing from the clone result.
    _git(workspace, "cat-file", "-e", f"{expected_sha}^{{commit}}")
    assert _git(workspace, "rev-parse", "HEAD") == expected_sha
