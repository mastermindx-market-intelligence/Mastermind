"""Real-Git regressions for the private admin checkout's selected-source clone.

Only new temporary repositories are changed. The commands under test come from
the installer; no installed checkout, service or external remote is accessed.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest

from ops.executive_os.admin_checkout import normalize_admin_checkout
from ops.executive_os.install_source_policy import (
    InstallSourcePolicyError,
    validate_install_source,
)

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "ops" / "executive_os" / "install.sh"
GIT = "/usr/bin/git"
pytestmark = pytest.mark.skipif(
    not Path(GIT).is_file() or not Path("/bin/bash").is_file(),
    reason="the installer's Git and Bash executables are required",
)


def _env() -> dict[str, str]:
    return {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _git(repo: Path, *args: str, data: str | None = None) -> str:
    result = subprocess.run(
        [GIT, "-C", str(repo), *args],
        input=data,
        text=True,
        capture_output=True,
        env=_env(),
        timeout=20,
        check=True,
    )
    return result.stdout.strip()


def _history(tmp_path: Path) -> tuple[Path, list[str]]:
    repo = (tmp_path / "source").resolve()
    subprocess.run(
        [GIT, "init", "-b", "master", str(repo)],
        env=_env(), capture_output=True, text=True, timeout=20, check=True,
    )
    for key, value in (
        ("user.name", "Fixture"),
        ("user.email", "fixture@example.com"),
        ("commit.gpgsign", "false"),
        ("gc.auto", "0"),
        ("maintenance.auto", "false"),
    ):
        _git(repo, "config", key, value)
    history = []
    for number in range(3):
        (repo / "state.txt").write_text(f"revision {number}\n", encoding="utf-8")
        _git(repo, "add", "state.txt")
        _git(repo, "commit", "-m", f"revision {number}")
        history.append(_git(repo, "rev-parse", "HEAD"))
    _git(repo, "update-ref", "refs/remotes/origin/master", history[-1])
    return repo, history


def _remove_fixture_tree(repo: Path, tree: str, fixture_root: Path) -> None:
    path = Path(_git(repo, "rev-parse", "--git-path", f"objects/{tree[:2]}/{tree[2:]}"))
    if not path.is_absolute():
        path = repo / path
    path = path.resolve()
    assert path.is_relative_to(fixture_root.resolve())
    assert path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1
    path.unlink()


def _broken_unrelated_ref(repo: Path, fixture_root: Path) -> str:
    blob = _git(repo, "hash-object", "-w", "--stdin", data="unrelated fixture only\n")
    tree = _git(repo, "mktree", data=f"100644 blob {blob}\tunrelated.txt\n")
    unrelated = _git(repo, "commit-tree", tree, "-m", "unrelated orphan")
    _git(repo, "update-ref", "refs/heads/unrelated-broken", unrelated)
    _git(repo, "tag", "-a", "unrelated-broken-tag", unrelated, "-m", "unrelated tag")
    assert tree not in _git(repo, "rev-list", "--format=%T", "HEAD").splitlines()
    _remove_fixture_tree(repo, tree, fixture_root)
    return unrelated


def _installer_statements() -> tuple[str, str, str]:
    lines = INSTALL.read_text(encoding="utf-8").splitlines()
    matches = [
        index for index, line in enumerate(lines)
        if line.strip().startswith("/usr/bin/git ") and
        'clone --no-hardlinks --no-checkout' in line
    ]
    assert len(matches) == 1
    index = matches[0]
    clone, checkout, remove_origin = (line.strip() for line in lines[index:index + 3])
    assert 'checkout --detach "$EXPECTED_SHA"' in checkout
    assert 'remote remove origin' in remove_origin
    return clone, checkout, remove_origin


def _clone(
    source: Path, destination: Path, expected: str, *, legacy: bool = False
) -> subprocess.CompletedProcess[str]:
    # Keep the real source qualifier in the path: a historical expected commit
    # that checkout could resolve is still not the selected source HEAD.
    validate_install_source(
        source_repo=source,
        expected_sha=expected,
        protected_master_sha=None,
        allow_frozen_accepted_ancestor=False,
    )
    clone, checkout, remove_origin = _installer_statements()
    if legacy:
        clone = clone.replace(" --single-branch", "").replace(" --no-tags", "")
    environment = {
        **_env(),
        "SOURCE_REPO": str(source),
        "ADMIN_CHECKOUT": str(destination),
        "EXPECTED_SHA": expected,
    }
    return subprocess.run(
        ["/bin/bash", "-c", "set -euo pipefail\n" +
         "\n".join((clone, checkout, remove_origin)) + "\n"],
        env=environment, capture_output=True, text=True, timeout=30, check=False,
    )


@pytest.mark.parametrize("linked", [False, True], ids=["main-checkout", "detached-worktree"])
def test_unrelated_broken_refs_do_not_block_exact_full_history_clone(
    tmp_path: Path, linked: bool
) -> None:
    repo, history = _history(tmp_path)
    source = repo
    if linked:
        source = (tmp_path / "linked-source").resolve()
        _git(repo, "worktree", "add", "--detach", str(source), history[-1])
    unrelated = _broken_unrelated_ref(repo, tmp_path)
    source_config = (repo / ".git" / "config").read_bytes()

    old = _clone(source, tmp_path / "old-admin", history[-1], legacy=True)
    assert old.returncode != 0, "fixture must reproduce the original all-ref clone failure"

    checkout = (tmp_path / "admin").resolve()
    result = _clone(source, checkout, history[-1])
    assert result.returncode == 0, result.stderr
    assert _git(checkout, "rev-parse", "HEAD") == history[-1]
    assert _git(checkout, "rev-list", "HEAD").splitlines() == list(reversed(history))
    assert _git(checkout, "rev-parse", "--is-shallow-repository") == "false"
    for number, commit in enumerate(history):
        assert _git(checkout, "show", f"{commit}:state.txt") == f"revision {number}"
    assert _git(checkout, "remote") == ""
    assert _git(checkout, "for-each-ref", "--format=%(refname)", "refs/tags") == ""
    assert _git(checkout, "for-each-ref", "--format=%(refname)", "refs/heads/unrelated-broken") == ""
    assert (checkout / "state.txt").read_text(encoding="utf-8") == "revision 2\n"
    assert normalize_admin_checkout(checkout, expected_commit=history[-1])["commit"] == history[-1]
    assert _git(repo, "rev-parse", "refs/heads/unrelated-broken") == unrelated
    assert _git(source, "rev-parse", "HEAD") == history[-1]
    assert (repo / ".git" / "config").read_bytes() == source_config


def test_missing_required_ancestor_tree_still_refuses(tmp_path: Path) -> None:
    repo, history = _history(tmp_path)
    ancestor_tree = _git(repo, "rev-parse", f"{history[0]}^{{tree}}")
    assert ancestor_tree != _git(repo, "rev-parse", "HEAD^{tree}")
    _remove_fixture_tree(repo, ancestor_tree, tmp_path)
    # The tip and current worktree remain valid; full history must still be
    # transferred and qualified, rather than silently becoming a shallow copy.
    assert _git(repo, "status", "--porcelain=v1") == ""
    result = _clone(repo, tmp_path / "admin", history[-1])
    assert result.returncode != 0


def test_ancestor_expected_sha_is_refused_before_clone(tmp_path: Path) -> None:
    repo, history = _history(tmp_path)
    destination = tmp_path / "admin"
    with pytest.raises(InstallSourcePolicyError, match="HEAD is not the exact expected SHA"):
        _clone(repo, destination, history[0])
    assert not destination.exists()
