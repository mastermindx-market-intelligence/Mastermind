from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import ops.executive_os.install_source_policy as source_policy
from ops.executive_os.install_source_policy import (
    InstallSourcePolicyError,
    validate_install_source,
)


ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "ops" / "executive_os" / "install.sh"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repo_with_accepted_ancestor(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    subprocess.run(
        ["git", "init", "-b", "master", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")

    (repo / "state.txt").write_text("accepted\n", encoding="utf-8")
    _git(repo, "add", "state.txt")
    _git(repo, "commit", "-m", "accepted")
    accepted = _git(repo, "rev-parse", "HEAD")

    (repo / "state.txt").write_text("protected\n", encoding="utf-8")
    _git(repo, "commit", "-am", "protected")
    protected = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/master", protected)
    return repo, accepted, protected


def test_exact_install_mode_preserves_existing_origin_master_equality(tmp_path: Path) -> None:
    repo, accepted, protected = _repo_with_accepted_ancestor(tmp_path)
    _git(repo, "checkout", "--detach", protected)

    receipt = validate_install_source(
        source_repo=repo,
        expected_sha=protected,
        protected_master_sha=None,
        allow_frozen_accepted_ancestor=False,
    )

    assert receipt["mode"] == "exact_protected_master"
    assert receipt["expected_sha"] == protected
    assert receipt["protected_master_sha"] == protected

    _git(repo, "checkout", "--detach", accepted)
    with pytest.raises(InstallSourcePolicyError, match="exact origin/master"):
        validate_install_source(
            source_repo=repo,
            expected_sha=accepted,
            protected_master_sha=None,
            allow_frozen_accepted_ancestor=False,
        )


def test_frozen_mode_accepts_only_a_strict_ancestor_of_attested_protected_master(
    tmp_path: Path,
) -> None:
    repo, accepted, protected = _repo_with_accepted_ancestor(tmp_path)
    _git(repo, "checkout", "--detach", accepted)

    receipt = validate_install_source(
        source_repo=repo,
        expected_sha=accepted,
        protected_master_sha=protected,
        allow_frozen_accepted_ancestor=True,
    )

    assert receipt == {
        "expected_sha": accepted,
        "mode": "frozen_accepted_ancestor",
        "protected_master_sha": protected,
    }

    _git(repo, "checkout", "--detach", protected)
    with pytest.raises(InstallSourcePolicyError, match="strict ancestor"):
        validate_install_source(
            source_repo=repo,
            expected_sha=protected,
            protected_master_sha=protected,
            allow_frozen_accepted_ancestor=True,
        )


def test_frozen_mode_rejects_a_claimed_protected_head_that_is_not_origin_master(
    tmp_path: Path,
) -> None:
    repo, accepted, protected = _repo_with_accepted_ancestor(tmp_path)
    _git(repo, "checkout", "--detach", accepted)

    with pytest.raises(InstallSourcePolicyError, match="protected master"):
        validate_install_source(
            source_repo=repo,
            expected_sha=accepted,
            protected_master_sha="f" * 40,
            allow_frozen_accepted_ancestor=True,
        )

    assert _git(repo, "rev-parse", "refs/remotes/origin/master") == protected


def test_frozen_mode_rejects_non_ancestor_and_dirty_source(tmp_path: Path) -> None:
    repo, accepted, protected = _repo_with_accepted_ancestor(tmp_path)

    _git(repo, "checkout", "--orphan", "unrelated")
    _git(repo, "rm", "-rf", ".")
    (repo / "other.txt").write_text("other\n", encoding="utf-8")
    _git(repo, "add", "other.txt")
    _git(repo, "commit", "-m", "unrelated")
    unrelated = _git(repo, "rev-parse", "HEAD")
    with pytest.raises(InstallSourcePolicyError, match="ancestor"):
        validate_install_source(
            source_repo=repo,
            expected_sha=unrelated,
            protected_master_sha=protected,
            allow_frozen_accepted_ancestor=True,
        )

    _git(repo, "checkout", "--detach", accepted)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(InstallSourcePolicyError, match="clean"):
        validate_install_source(
            source_repo=repo,
            expected_sha=accepted,
            protected_master_sha=protected,
            allow_frozen_accepted_ancestor=True,
        )


def test_frozen_mode_binds_the_installer_checkout_to_current_protected_master(
    tmp_path: Path,
) -> None:
    installer, accepted, protected = _repo_with_accepted_ancestor(tmp_path)
    source = tmp_path / "frozen-source"
    _git(installer, "worktree", "add", "--detach", str(source), accepted)

    receipt = validate_install_source(
        source_repo=source,
        expected_sha=accepted,
        protected_master_sha=protected,
        allow_frozen_accepted_ancestor=True,
        installer_repo=installer,
    )
    assert receipt["mode"] == "frozen_accepted_ancestor"

    _git(installer, "checkout", "--detach", accepted)
    with pytest.raises(InstallSourcePolicyError, match="installer checkout HEAD"):
        validate_install_source(
            source_repo=source,
            expected_sha=accepted,
            protected_master_sha=protected,
            allow_frozen_accepted_ancestor=True,
            installer_repo=installer,
        )

    _git(installer, "checkout", "--detach", protected)
    (installer / "dirty-installer.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(InstallSourcePolicyError, match="installer checkout is not clean"):
        validate_install_source(
            source_repo=source,
            expected_sha=accepted,
            protected_master_sha=protected,
            allow_frozen_accepted_ancestor=True,
            installer_repo=installer,
        )


def test_installer_exposes_explicit_frozen_mode_without_reusing_historical_source_law() -> None:
    install = INSTALL.read_text(encoding="utf-8")
    assert "--allow-frozen-accepted-ancestor" in install
    assert "--protected-master-sha" in install
    assert '"$SCRIPT_DIR/install_source_policy.py"' in install
    assert "refs/remotes/origin/master" not in install


def test_git_uses_exact_command_scoped_safe_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(source_policy.subprocess, "run", fake_run)
    result = source_policy._git(repo, "rev-parse", "HEAD")

    trusted = str(repo.resolve())
    assert result.stdout == "ok\n"
    assert calls == [[
        "/usr/bin/git", "--no-optional-locks",
        "-c", f"safe.directory={trusted}",
        "-C", trusted, "rev-parse", "HEAD",
    ]]


def test_git_refuses_symlink_alias_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(repo, target_is_directory=True)
    monkeypatch.setattr(
        source_policy.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Git must not spawn for an alias"),
    )
    with pytest.raises(InstallSourcePolicyError, match="path is unsafe"):
        source_policy._git(alias, "rev-parse", "HEAD")


def test_git_refuses_wildcard_safe_directory_value_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo*"
    repo.mkdir()
    monkeypatch.setattr(
        source_policy.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("Git must not spawn for wildcard trust"),
    )
    with pytest.raises(InstallSourcePolicyError, match="path is unsafe"):
        source_policy._git(repo, "rev-parse", "HEAD")


@pytest.mark.parametrize("linked", [False, True])
@pytest.mark.parametrize("operation", ["tree", "archive", "clone"])
def test_installer_source_reads_work_without_persistent_ownership_trust(
    tmp_path: Path, operation: str, linked: bool
) -> None:
    repo, _accepted, protected = _repo_with_accepted_ancestor(tmp_path)
    if linked:
        worktree = tmp_path / "linked-source"
        _git(repo, "worktree", "add", "--detach", str(worktree), protected)
        repo = worktree
    source_config = Path(_git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "config"
    config_before = source_config.read_bytes()
    staging = tmp_path / "staging"
    staging.mkdir()
    checkout = tmp_path / "admin"
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "SOURCE_REPO": str(repo.resolve()),
        "EXPECTED_SHA": protected,
        "STAGING": str(staging),
        "ADMIN_CHECKOUT": str(checkout),
    }
    baseline = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "rev-parse", "HEAD"],
        env=env, capture_output=True, text=True, check=False,
    )
    assert baseline.returncode != 0
    assert "dubious ownership" in baseline.stderr

    selectors = {
        "tree": 'TREE_SHA="$(',
        "archive": 'archive --format=tar "$EXPECTED_SHA"',
        "clone": 'clone --no-hardlinks --no-checkout',
    }
    statements = [
        line.strip() for line in INSTALL.read_text(encoding="utf-8").splitlines()
        if selectors[operation] in line
    ]
    assert len(statements) == 1
    script = "set -euo pipefail\n" + statements[0] + "\n"
    if operation == "tree":
        script += 'printf "%s\\n" "$TREE_SHA"\n'
    completed = subprocess.run(
        ["/bin/bash", "-c", script],
        env=env, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    if operation == "tree":
        assert completed.stdout.strip() == _git(repo, "rev-parse", f"{protected}^{{tree}}")
    elif operation == "archive":
        assert (staging / "state.txt").read_text(encoding="utf-8") == "protected\n"
    else:
        assert _git(checkout, "rev-parse", "HEAD") == protected
        assert not (checkout / "state.txt").exists()
        assert "safe.directory" not in (checkout / ".git" / "config").read_text(encoding="utf-8")
    assert source_config.read_bytes() == config_before


@pytest.mark.parametrize("linked", [False, True])
def test_acceptance_reads_different_owner_without_changing_git_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, linked: bool
) -> None:
    from ops.executive_os.acceptance import Acceptance

    repo, _accepted, protected = _repo_with_accepted_ancestor(tmp_path)
    if linked:
        linked_repo = tmp_path / "acceptance-source"
        _git(repo, "worktree", "add", "--detach", str(linked_repo), protected)
        repo = linked_repo
    tree = _git(repo, "rev-parse", f"{protected}^{{tree}}")
    git_dir = Path(_git(repo, "rev-parse", "--absolute-git-dir"))
    common = Path(_git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    paths = [git_dir / "index", common / "config"]
    before = [(p.read_bytes(), p.stat()) for p in paths]
    # Force status to inspect a changed stat without permitting index refresh.
    tracked = repo / "state.txt"
    info = tracked.stat()
    os.utime(tracked, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")
    bare = subprocess.run(
        ["/usr/bin/git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    assert bare.returncode != 0 and "dubious ownership" in bare.stderr

    proof = object.__new__(Acceptance)
    proof.source_repository = repo
    proof.expected_sha = protected
    assert proof._source_tree_sha() == tree
    for path, (raw, old_stat) in zip(paths, before):
        assert path.read_bytes() == raw
        assert path.stat() == old_stat
    assert not (git_dir / "index.lock").exists()


@pytest.mark.parametrize("failure", ["dirty", "head", "remote", "alias", "wildcard"])
def test_acceptance_source_refuses_drift_and_unsafe_trust(
    tmp_path: Path, failure: str
) -> None:
    from ops.executive_os.acceptance import Acceptance, AcceptanceError

    repo, accepted, protected = _repo_with_accepted_ancestor(tmp_path)
    if failure == "dirty":
        (repo / "untracked.txt").write_text("unreviewed", encoding="utf-8")
    elif failure == "head":
        _git(repo, "checkout", "--detach", accepted)
    elif failure == "remote":
        _git(repo, "update-ref", "refs/remotes/origin/master", accepted)
    elif failure == "alias":
        alias = tmp_path / "source-alias"
        alias.symlink_to(repo, target_is_directory=True)
        repo = alias
    elif failure == "wildcard":
        renamed = tmp_path / "source*"
        repo.rename(renamed)
        repo = renamed

    proof = object.__new__(Acceptance)
    proof.source_repository = repo
    proof.expected_sha = protected
    with pytest.raises(AcceptanceError) as caught:
        proof._source_tree_sha()
    assert isinstance(caught.value.__cause__, InstallSourcePolicyError)
