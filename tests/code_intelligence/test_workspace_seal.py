"""C0 falsifier — exact workspace sealing and zero-candidate-write proof.

The seal is what makes "exact worktree" mean something. Every test here is a
hostile case: if any of them stops failing, the isolation claim is void.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from experiments.code_intelligence.workspace_seal import (
    SEAL_FIELDS,
    WorkspaceSeal,
    WorkspaceSealError,
    candidate_tree_fingerprint,
    capture_workspace_seal,
    create_external_scratch,
    verify_workspace_seal,
    workspace_binding_digest,
)

GIT_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "HOME": "/nonexistent-codeintel-c0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_AUTHOR_NAME": "c0",
    "GIT_AUTHOR_EMAIL": "c0@example.invalid",
    "GIT_COMMITTER_NAME": "c0",
    "GIT_COMMITTER_EMAIL": "c0@example.invalid",
}


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
        shell=False,
    )
    return result.stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(base: Path, sentinel: str) -> Path:
    """A minimal repo whose file names are identical across fixtures."""
    root = base / "origin"
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "main")
    _write(root / "src" / "sample" / "producer.py", f'SENTINEL = "{sentinel}"\n')
    _write(root / "README.md", "codeintel c0 fixture\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "fixture")
    return root


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _make_repo(tmp_path, "WORKTREE_ORIGIN_ONLY")


@pytest.fixture
def alpha_beta(tmp_path: Path) -> tuple[Path, Path]:
    """Two simultaneous linked worktrees, identical names, distinct sentinels."""
    root = _make_repo(tmp_path, "WORKTREE_ORIGIN_ONLY")
    alpha = tmp_path / "alpha"
    beta = tmp_path / "beta"
    _git(root, "worktree", "add", "-q", "-b", "alpha", str(alpha))
    _git(root, "worktree", "add", "-q", "-b", "beta", str(beta))
    _write(alpha / "src" / "sample" / "producer.py", 'SENTINEL = "WORKTREE_ALPHA_ONLY"\n')
    _git(alpha, "add", "-A")
    _git(alpha, "commit", "-q", "-m", "alpha")
    _write(beta / "src" / "sample" / "producer.py", 'SENTINEL = "WORKTREE_BETA_ONLY"\n')
    _git(beta, "add", "-A")
    _git(beta, "commit", "-q", "-m", "beta")
    return alpha, beta


class TestSealShape:
    def test_seal_fields_are_exactly_the_frozen_set(self) -> None:
        assert SEAL_FIELDS == (
            "resolved_root",
            "device",
            "inode",
            "uid",
            "gid",
            "git_common_dir",
            "git_dir",
            "head_sha",
            "status_porcelain_v2_sha256",
            "candidate_tree_sha256",
        )

    def test_capture_populates_every_field(self, repo: Path) -> None:
        seal = capture_workspace_seal(repo)
        for field in SEAL_FIELDS:
            assert getattr(seal, field) not in (None, "")

    def test_seal_is_immutable(self, repo: Path) -> None:
        seal = capture_workspace_seal(repo)
        with pytest.raises(Exception):
            seal.head_sha = "0" * 40  # type: ignore[misc]

    def test_binding_digest_is_stable_and_changes_with_content(self, repo: Path) -> None:
        first = workspace_binding_digest(capture_workspace_seal(repo))
        assert len(first) == 64
        assert first == workspace_binding_digest(capture_workspace_seal(repo))
        _write(repo / "new.py", "x = 1\n")
        assert workspace_binding_digest(capture_workspace_seal(repo)) != first

    def test_verify_passes_on_an_unchanged_worktree(self, repo: Path) -> None:
        verify_workspace_seal(capture_workspace_seal(repo))


class TestHostileRoots:
    def test_symlink_root_is_refused(self, repo: Path, tmp_path: Path) -> None:
        link = tmp_path / "link-root"
        link.symlink_to(repo, target_is_directory=True)
        with pytest.raises(WorkspaceSealError) as excinfo:
            capture_workspace_seal(link)
        assert excinfo.value.code == "SYMLINK_ROOT_REFUSED"

    def test_symlink_ancestor_is_refused(self, tmp_path: Path) -> None:
        real_parent = tmp_path / "real"
        real_parent.mkdir()
        repo = _make_repo(real_parent, "WORKTREE_ORIGIN_ONLY")
        link_parent = tmp_path / "link-parent"
        link_parent.symlink_to(real_parent, target_is_directory=True)
        with pytest.raises(WorkspaceSealError) as excinfo:
            capture_workspace_seal(link_parent / "origin")
        assert excinfo.value.code == "SYMLINK_ANCESTOR_REFUSED"

    def test_missing_root_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(WorkspaceSealError) as excinfo:
            capture_workspace_seal(tmp_path / "absent")
        assert excinfo.value.code == "ROOT_UNRESOLVABLE"

    def test_non_git_root_is_refused(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain"
        plain.mkdir()
        with pytest.raises(WorkspaceSealError) as excinfo:
            capture_workspace_seal(plain)
        assert excinfo.value.code == "GIT_ROOT_MISMATCH"

    def test_subdirectory_of_a_repo_is_refused_as_root(self, repo: Path) -> None:
        with pytest.raises(WorkspaceSealError) as excinfo:
            capture_workspace_seal(repo / "src")
        assert excinfo.value.code == "GIT_ROOT_MISMATCH"


class TestDriftDetection:
    def test_moved_root_is_refused(self, repo: Path, tmp_path: Path) -> None:
        seal = capture_workspace_seal(repo)
        repo.rename(tmp_path / "moved-away")
        with pytest.raises(WorkspaceSealError) as excinfo:
            verify_workspace_seal(seal)
        assert excinfo.value.code == "ROOT_UNRESOLVABLE"

    def test_replaced_inode_is_refused(self, repo: Path, tmp_path: Path) -> None:
        seal = capture_workspace_seal(repo)
        repo.rename(tmp_path / "stashed")
        _make_repo(tmp_path, "WORKTREE_ORIGIN_ONLY")
        with pytest.raises(WorkspaceSealError) as excinfo:
            verify_workspace_seal(seal)
        assert excinfo.value.code == "ROOT_IDENTITY_CHANGED"

    def test_changed_head_is_refused(self, repo: Path) -> None:
        seal = capture_workspace_seal(repo)
        _write(repo / "another.py", "y = 2\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", "second")
        with pytest.raises(WorkspaceSealError) as excinfo:
            verify_workspace_seal(seal)
        assert excinfo.value.code == "HEAD_CHANGED"

    def test_modified_tracked_file_is_a_candidate_write(self, repo: Path) -> None:
        seal = capture_workspace_seal(repo)
        _write(repo / "README.md", "tampered\n")
        with pytest.raises(WorkspaceSealError) as excinfo:
            verify_workspace_seal(seal)
        assert excinfo.value.code == "CANDIDATE_TREE_WRITE_DETECTED"

    def test_untracked_file_is_a_candidate_write(self, repo: Path) -> None:
        seal = capture_workspace_seal(repo)
        _write(repo / ".semantic-cache" / "index.db", "cache\n")
        with pytest.raises(WorkspaceSealError) as excinfo:
            verify_workspace_seal(seal)
        assert excinfo.value.code == "CANDIDATE_TREE_WRITE_DETECTED"

    def test_index_only_change_is_dirty_drift_not_a_write(self, repo: Path) -> None:
        # Staging an unchanged-on-disk deletion moves git status without moving
        # file bytes: a distinct signal from a tree write.
        seal = capture_workspace_seal(repo)
        _git(repo, "rm", "-q", "--cached", "README.md")
        with pytest.raises(WorkspaceSealError) as excinfo:
            verify_workspace_seal(seal)
        assert excinfo.value.code == "DIRTY_FINGERPRINT_DRIFT"

    def test_git_dir_mismatch_is_refused(self, alpha_beta: tuple[Path, Path]) -> None:
        alpha, beta = alpha_beta
        alpha_seal = capture_workspace_seal(alpha)
        beta_seal = capture_workspace_seal(beta)
        forged = WorkspaceSeal(
            **{
                **{field: getattr(alpha_seal, field) for field in SEAL_FIELDS},
                "git_dir": beta_seal.git_dir,
            }
        )
        with pytest.raises(WorkspaceSealError) as excinfo:
            verify_workspace_seal(forged)
        assert excinfo.value.code == "GIT_ROOT_MISMATCH"


class TestTwoWorktreeIsolation:
    def test_alpha_and_beta_share_a_common_dir_but_differ(
        self, alpha_beta: tuple[Path, Path]
    ) -> None:
        alpha, beta = alpha_beta
        alpha_seal = capture_workspace_seal(alpha)
        beta_seal = capture_workspace_seal(beta)
        assert alpha_seal.git_common_dir == beta_seal.git_common_dir
        assert alpha_seal.git_dir != beta_seal.git_dir
        assert alpha_seal.inode != beta_seal.inode
        assert alpha_seal.candidate_tree_sha256 != beta_seal.candidate_tree_sha256
        assert alpha_seal.head_sha != beta_seal.head_sha

    def test_sentinels_are_actually_distinct_on_disk(
        self, alpha_beta: tuple[Path, Path]
    ) -> None:
        alpha, beta = alpha_beta
        alpha_text = (alpha / "src" / "sample" / "producer.py").read_text()
        beta_text = (beta / "src" / "sample" / "producer.py").read_text()
        assert "WORKTREE_ALPHA_ONLY" in alpha_text
        assert "WORKTREE_BETA_ONLY" not in alpha_text
        assert "WORKTREE_BETA_ONLY" in beta_text
        assert "WORKTREE_ALPHA_ONLY" not in beta_text

    def test_each_seal_verifies_only_against_its_own_worktree(
        self, alpha_beta: tuple[Path, Path]
    ) -> None:
        alpha, beta = alpha_beta
        verify_workspace_seal(capture_workspace_seal(alpha))
        verify_workspace_seal(capture_workspace_seal(beta))


class TestTreeFingerprint:
    def test_fingerprint_ignores_git_metadata_churn(self, repo: Path) -> None:
        before = candidate_tree_fingerprint(repo)
        _git(repo, "log", "--oneline")  # touches .git internals only
        (repo / ".git" / "codeintel-probe").write_text("noise\n", encoding="utf-8")
        assert candidate_tree_fingerprint(repo) == before

    def test_fingerprint_tracks_content(self, repo: Path) -> None:
        before = candidate_tree_fingerprint(repo)
        _write(repo / "src" / "sample" / "producer.py", 'SENTINEL = "CHANGED"\n')
        assert candidate_tree_fingerprint(repo) != before

    def test_fingerprint_tracks_renames(self, repo: Path) -> None:
        before = candidate_tree_fingerprint(repo)
        (repo / "README.md").rename(repo / "READMEX.md")
        assert candidate_tree_fingerprint(repo) != before

    def test_special_file_is_refused(self, repo: Path) -> None:
        os.mkfifo(repo / "a-fifo")
        with pytest.raises(WorkspaceSealError) as excinfo:
            candidate_tree_fingerprint(repo)
        assert excinfo.value.code == "SPECIAL_FILE_REFUSED"

    def test_symlink_escaping_the_root_is_refused(self, repo: Path, tmp_path: Path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        (repo / "escape.txt").symlink_to(outside)
        with pytest.raises(WorkspaceSealError) as excinfo:
            candidate_tree_fingerprint(repo)
        assert excinfo.value.code == "TREE_TRAVERSAL_REFUSED"


class TestExternalScratch:
    def test_scratch_inside_the_candidate_tree_is_refused(self, repo: Path) -> None:
        seal = capture_workspace_seal(repo)
        with pytest.raises(WorkspaceSealError) as excinfo:
            create_external_scratch(parent=repo / "scratch", seal=seal)
        assert excinfo.value.code == "SCRATCH_INSIDE_CANDIDATE_TREE"

    def test_scratch_equal_to_the_root_is_refused(self, repo: Path) -> None:
        seal = capture_workspace_seal(repo)
        with pytest.raises(WorkspaceSealError) as excinfo:
            create_external_scratch(parent=repo, seal=seal)
        assert excinfo.value.code == "SCRATCH_INSIDE_CANDIDATE_TREE"

    def test_scratch_outside_the_tree_is_created(self, repo: Path, tmp_path: Path) -> None:
        seal = capture_workspace_seal(repo)
        scratch = create_external_scratch(parent=tmp_path / "scratch", seal=seal)
        assert scratch.is_dir()
        assert not str(scratch).startswith(str(repo))
        verify_workspace_seal(seal)

    def test_scratch_is_unique_per_call(self, repo: Path, tmp_path: Path) -> None:
        seal = capture_workspace_seal(repo)
        first = create_external_scratch(parent=tmp_path / "scratch", seal=seal)
        second = create_external_scratch(parent=tmp_path / "scratch", seal=seal)
        assert first != second


class TestZeroWriteProof:
    """The plan's Task 2 Step 4: a fake backend that writes must be caught."""

    def test_backend_writing_the_worktree_is_refused(self, repo: Path) -> None:
        seal = capture_workspace_seal(repo)

        def bad_backend() -> None:
            (repo / ".semantic-cache").mkdir(exist_ok=True)
            (repo / ".semantic-cache" / "db").write_text("x\n", encoding="utf-8")

        bad_backend()
        with pytest.raises(WorkspaceSealError) as excinfo:
            verify_workspace_seal(seal)
        assert excinfo.value.code == "CANDIDATE_TREE_WRITE_DETECTED"

    def test_same_backend_writing_external_scratch_is_allowed(
        self, repo: Path, tmp_path: Path
    ) -> None:
        seal = capture_workspace_seal(repo)
        scratch = create_external_scratch(parent=tmp_path / "scratch", seal=seal)

        def good_backend() -> None:
            (scratch / ".semantic-cache").mkdir(exist_ok=True)
            (scratch / ".semantic-cache" / "db").write_text("x\n", encoding="utf-8")

        good_backend()
        verify_workspace_seal(seal)
