from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from ops.devbox.codespace_preflight import (
    CodespacePreflightError,
    qualify_codespace_environment,
)

REPOSITORY = "mastermindx-market-intelligence/Mastermind"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "Mastermind"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "preflight@example.invalid")
    _git(root, "config", "user.name", "Preflight")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "baseline")
    return root


def _env() -> dict[str, str]:
    return {
        "CODESPACES": "true",
        "CODESPACE_NAME": "silver-space-abc123",
        "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
        "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_TOKEN": "ambient-secret-that-must-not-project",
    }


def test_qualified_codespace_derives_exact_forwarded_https_identity(
    repo: Path, tmp_path: Path
) -> None:
    result = qualify_codespace_environment(
        repo_root=repo,
        state_root=tmp_path / "state",
        expected_repository=REPOSITORY,
        port=8767,
        env=_env(),
        platform_name="linux",
    )
    assert result.codespace_name == "silver-space-abc123"
    assert result.forwarded_host == "silver-space-abc123-8767.app.github.dev"
    assert result.forwarded_mcp_url == "https://silver-space-abc123-8767.app.github.dev/mcp"
    assert result.repository == REPOSITORY
    assert result.observed_head == _git(repo, "rev-parse", "HEAD")
    assert result.repo_root == repo.resolve()
    assert result.state_root == (tmp_path / "state").absolute()
    assert "ambient-secret" not in repr(result)


@pytest.mark.parametrize(
    ("platform_name", "changes"),
    [
        ("darwin", {}),
        ("linux", {"CODESPACES": "false"}),
        ("linux", {"CODESPACE_NAME": "bad/name"}),
        ("linux", {"GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "https://evil.example"}),
        ("linux", {"GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev/extra"}),
        ("linux", {"GITHUB_REPOSITORY": "other/repo"}),
    ],
)
def test_non_codespace_or_mismatched_environment_refuses(
    repo: Path, tmp_path: Path, platform_name: str, changes: dict[str, str]
) -> None:
    env = _env()
    env.update(changes)
    with pytest.raises(CodespacePreflightError):
        qualify_codespace_environment(
            repo_root=repo,
            state_root=tmp_path / "state",
            expected_repository=REPOSITORY,
            port=8767,
            env=env,
            platform_name=platform_name,
        )


@pytest.mark.parametrize("port", [True, 0, 65536, "8767"])
def test_port_must_be_exact_integer(repo: Path, tmp_path: Path, port: object) -> None:
    with pytest.raises(CodespacePreflightError):
        qualify_codespace_environment(
            repo_root=repo,
            state_root=tmp_path / "state",
            expected_repository=REPOSITORY,
            port=port,
            env=_env(),
            platform_name="linux",
        )


def test_state_root_must_be_outside_repo(repo: Path) -> None:
    with pytest.raises(CodespacePreflightError):
        qualify_codespace_environment(
            repo_root=repo,
            state_root=repo / ".state",
            expected_repository=REPOSITORY,
            port=8767,
            env=_env(),
            platform_name="linux",
        )


def test_symlink_repo_or_state_refuses(repo: Path, tmp_path: Path) -> None:
    repo_link = tmp_path / "repo-link"
    repo_link.symlink_to(repo, target_is_directory=True)
    with pytest.raises(CodespacePreflightError):
        qualify_codespace_environment(
            repo_root=repo_link,
            state_root=tmp_path / "state",
            expected_repository=REPOSITORY,
            port=8767,
            env=_env(),
            platform_name="linux",
        )

    external = tmp_path / "external"
    external.mkdir()
    state_link = tmp_path / "state-link"
    state_link.symlink_to(external, target_is_directory=True)
    with pytest.raises(CodespacePreflightError):
        qualify_codespace_environment(
            repo_root=repo,
            state_root=state_link,
            expected_repository=REPOSITORY,
            port=8767,
            env=_env(),
            platform_name="linux",
        )


def test_nested_directory_is_not_accepted_as_repo_root(repo: Path, tmp_path: Path) -> None:
    nested = repo / "nested"
    nested.mkdir()
    with pytest.raises(CodespacePreflightError):
        qualify_codespace_environment(
            repo_root=nested,
            state_root=tmp_path / "state",
            expected_repository=REPOSITORY,
            port=8767,
            env=_env(),
            platform_name="linux",
        )


def test_missing_state_parent_refuses_without_creating_it(repo: Path, tmp_path: Path) -> None:
    parent = tmp_path / "missing"
    with pytest.raises(CodespacePreflightError):
        qualify_codespace_environment(
            repo_root=repo,
            state_root=parent / "state",
            expected_repository=REPOSITORY,
            port=8767,
            env=_env(),
            platform_name="linux",
        )
    assert not parent.exists()
