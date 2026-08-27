from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

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


def test_installer_exposes_explicit_frozen_mode_without_reusing_historical_source_law() -> None:
    install = INSTALL.read_text(encoding="utf-8")
    assert "--allow-frozen-accepted-ancestor" in install
    assert "--protected-master-sha" in install
    assert '"$SCRIPT_DIR/install_source_policy.py"' in install
    assert "refs/remotes/origin/master" not in install
