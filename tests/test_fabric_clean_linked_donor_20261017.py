"""Portable real-Git trust-contract tests for the pre-provisioned Fabric sparse donor.

The shipped patch is source-only, never auto-installs workers. These tests
execute the *actual patched donor-validation function* extracted from its
reviewable diff against disposable local Git repositories. No live Fabric
controller, provider credentials, or host source tree are accessed.
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATCH = (ROOT / "integrations" / "fleet" /
         "ubuntu_thermal_headroom_20261013" /
         "FABRIC_CLEAN_LINKED_DONOR_FALLBACK_20261016.patch")
PATCH_SHA256 = "32773b3642d47579b1794878db48e4993f7114995d729ef203c93993c74a7ee3"
OLD_BLOB = "296e47bab2d28f9a019e81b5aef76eeea62a6cc3"
REVIEWED_BLOB = "75297acb10d0cef4d01730a59fdcad19c7cfd3e6"
REVIEWED_MERGE = "40abd9bd2291997cc066f30b408a1e670124cec4"


class SparseWorkspaceRefused(ValueError):
    pass


def _git(cwd: Path, *args: str) -> str:
    cmd = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True,
                         text=True, check=False, timeout=20)
    assert cmd.returncode == 0, (args, cmd.stderr[:500])
    return cmd.stdout.strip()


def _blob(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def _patched_donor_validator(merge: str, helper_blob: str):
    raw = PATCH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PATCH_SHA256
    patch = raw.decode("utf-8")
    assert patch.startswith("--- a/remote_sub_exec.py\n+++ b/remote_sub_exec.py\n")
    assert patch.count("+++ b/") == 1
    start = patch.index("+def _clean_linked_sparse_donor(original: Path) -> Path:\n")
    stop = patch.index(" def _new_macro_workspace(", start)
    diff_lines = patch[start:stop].splitlines()
    assert all(line.startswith("+") or not line.strip() for line in diff_lines)
    code = "\n".join(line[1:] for line in diff_lines if line.startswith("+")) + "\n"
    parsed = ast.parse(code)
    assert len(parsed.body) == 1 and isinstance(parsed.body[0], ast.FunctionDef)
    assert parsed.body[0].name == "_clean_linked_sparse_donor"
    ns = {
        "Path": Path,
        "os": os,
        "stat": stat,
        "subprocess": subprocess,
        "SparseWorkspaceRefused": SparseWorkspaceRefused,
        "_MACRO_PINNED_DONOR_COMMIT": merge,
        "_MACRO_FABRIC_SPARSE_BLOB": helper_blob,
    }
    exec(compile(parsed, str(PATCH), "exec"), ns)
    return ns["_clean_linked_sparse_donor"]


@pytest.fixture
def repository(tmp_path: Path):
    # resolve() allows this to run on macOS too, where /tmp -> /private/tmp.
    home = tmp_path.resolve(strict=True)
    original = home / "lanes" / "repos" / "macro"
    original.mkdir(parents=True)
    _git(original, "init", "-q")
    _git(original, "config", "user.email", "fixture@example.invalid")
    _git(original, "config", "user.name", "Fabric Regression")
    _git(original, "config", "extensions.worktreeConfig", "true")
    (original / "scripts").mkdir()
    (original / "scripts" / "worktree_sparse.py").write_bytes(b"old reviewed test fixture\n")
    (original / "preserve.txt").write_text("keep\n")
    _git(original, "add", ".")
    _git(original, "commit", "-qm", "original donor source")
    original_head = _git(original, "rev-parse", "HEAD")

    alt = original.parent / "macro-fabric-pinned-20261016"
    _git(original, "worktree", "add", "-q", "-b", "reviewed-fixture", str(alt))
    reviewed_bytes = b"new reviewed test fixture\n"
    (alt / "scripts" / "worktree_sparse.py").write_bytes(reviewed_bytes)
    _git(alt, "add", ".")
    _git(alt, "commit", "-qm", "reviewed donor helper")
    reviewed_head = _git(alt, "rev-parse", "HEAD")
    _git(alt, "sparse-checkout", "set", "--cone", "scripts")
    assert _git(alt, "status", "--porcelain=v1", "--untracked-files=all") == ""

    (original / "preserve.txt").write_text("ORIGINAL UNCOMMITTED WORK\n")
    assert _git(original, "rev-parse", "HEAD") == original_head
    return original, alt, reviewed_head, reviewed_bytes, original_head


def test_clean_same_common_git_donor_is_qualified_without_touching_old_source(repository):
    orig, alt, rev, body, old = repository
    selected = _patched_donor_validator(rev, _blob(body))(orig)
    assert selected == alt
    assert _git(orig, "rev-parse", "HEAD") == old
    assert (orig / "preserve.txt").read_text() == "ORIGINAL UNCOMMITTED WORK\n"
    assert _git(alt, "status", "--porcelain=v1", "--untracked-files=all") == ""


def test_missing_replacement_refuses(repository):
    orig, alt, rev, body, _ = repository
    _git(orig, "worktree", "remove", "--force", str(alt))  # scratch fixture only
    with pytest.raises(SparseWorkspaceRefused, match="REVIEWED_DONOR_UNAVAILABLE"):
        _patched_donor_validator(rev, _blob(body))(orig)


def test_dirty_replacement_refuses(repository):
    orig, alt, rev, body, _ = repository
    (alt / "untracked.tmp").write_text("do not trust")
    with pytest.raises(SparseWorkspaceRefused, match="REVIEWED_DONOR_UNQUALIFIED"):
        _patched_donor_validator(rev, _blob(body))(orig)


def test_unreviewed_commit_refuses(repository):
    orig, alt, rev, body, _ = repository
    with pytest.raises(SparseWorkspaceRefused, match="REVIEWED_DONOR_UNQUALIFIED"):
        _patched_donor_validator("f" * 40, _blob(body))(orig)


def test_unreviewed_helper_blob_refuses(repository):
    orig, alt, rev, body, _ = repository
    with pytest.raises(SparseWorkspaceRefused, match="REVIEWED_DONOR_UNQUALIFIED"):
        _patched_donor_validator(rev, "a" * 40)(orig)


def test_unrelated_git_repository_cannot_impersonate_linked_donor(repository):
    orig, alt, rev, body, _ = repository
    _git(orig, "worktree", "remove", "--force", str(alt))  # scratch fixture only
    subprocess.run(["git", "clone", "-q", "--shared", str(orig), str(alt)],
                   check=True, capture_output=True, timeout=20)
    _git(alt, "checkout", "-q", rev)
    _git(alt, "sparse-checkout", "set", "--cone", "scripts")
    with pytest.raises(SparseWorkspaceRefused, match="REVIEWED_DONOR_UNQUALIFIED"):
        _patched_donor_validator(rev, _blob(body))(orig)


def test_trusted_donor_commit_and_path_are_exactly_pinned():
    raw = PATCH.read_text()
    assert '+_MACRO_PINNED_DONOR_COMMIT = "6ee058b0491a3f67e843f25d4379b94e98880e8b"' in raw
    assert '+    alternate = original.parent / "macro-fabric-pinned-20261016"' in raw
    assert '+            or inspect("rev-parse", "HEAD") != _MACRO_PINNED_DONOR_COMMIT' in raw


def test_source_patch_preserves_lease_and_capacity_owners():
    patch = PATCH.read_text()
    changed = [s.split("b/", 1)[-1] for s in patch.splitlines() if s.startswith("+++ b/")]
    assert changed == ["remote_sub_exec.py"]
    assert "hosts.json" not in patch
    assert "max_active" not in patch
    assert "LaneLease.acquire" not in patch
    assert '+            or inspect("ls-files", "--others", "--ignored", "--exclude-standard", "-z")' in patch
    assert '+            [sys.executable, "-I", str(helper), "fabric-mint", key, commit],' in patch
    assert '+        if _clean_linked_sparse_donor(original_donor) != donor:' in patch
    assert "fabric-mint" not in patch.split("+def _clean_linked_sparse_donor", 1)[1].split(" def _new_macro_workspace", 1)[0]
    assert '+        if attempt == 0 and git_blob == _MACRO_PREMERGE_SPARSE_BLOB:' in patch
    assert '+            donor = _clean_linked_sparse_donor(donor)' in patch
    assert '+            raise SparseWorkspaceRefused("FABRIC_SPARSE_HELPER_BLOB_MISMATCH")' in patch
    assert 'donor_git = Path(git_value(donor, "rev-parse", "--path-format=absolute",' in patch

def test_ignored_untracked_stdlib_shadow_refused_by_reviewed_donor(repository):
    orig, alt, rev, body, _ = repository
    # The ignore rule is tracked by the reviewed worktree commit; the malicious
    # Python file is not. --porcelain alone falsely reports this checkout clean.
    (alt / ".gitignore").write_text("scripts/json.py\n")
    _git(alt, "add", ".gitignore")
    _git(alt, "commit", "-qm", "fixture ignore rule")
    reviewed_head = _git(alt, "rev-parse", "HEAD")
    (alt / "scripts" / "json.py").write_text("raise RuntimeError('shadow')\n")
    assert _git(alt, "status", "--porcelain=v1", "--untracked-files=all") == ""
    assert "scripts/json.py" in _git(
        alt, "ls-files", "--others", "--ignored", "--exclude-standard", "-z"
    )
    with pytest.raises(SparseWorkspaceRefused, match="REVIEWED_DONOR_UNQUALIFIED"):
        _patched_donor_validator(reviewed_head, _blob(body))(orig)


def test_isolated_python_invocation_blocks_late_shadow_import(tmp_path):
    """Even if a file appears after validation, -I excludes scripts/."""
    patch = PATCH.read_text()
    assert '[sys.executable, "-I", str(helper), "fabric-mint", key, commit]' in patch
    directory = tmp_path / "scripts"
    directory.mkdir()
    sentinel = tmp_path / "shadow-executed"
    helper = directory / "helper.py"
    helper.write_text("import json\nprint('stdlib-import-finished')\n")
    (directory / "json.py").write_text(
        "from pathlib import Path\n"
        + "Path(" + repr(str(sentinel)) + ").write_text('injected')\n"
    )
    nonisolated = subprocess.run(
        [sys.executable, str(helper)], capture_output=True, text=True, timeout=8
    )
    assert nonisolated.returncode == 0 and sentinel.is_file()
    sentinel.unlink()
    isolated = subprocess.run(
        [sys.executable, "-I", str(helper)], capture_output=True, text=True, timeout=8
    )
    assert isolated.returncode == 0
    assert "stdlib-import-finished" in isolated.stdout
    assert not sentinel.exists()
