from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _clean_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    tracked = repo / "tracked.txt"
    tracked.write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "fixture")
    return repo, tracked


@pytest.mark.parametrize(
    "index_flag",
    ["--assume-unchanged", "--skip-worktree"],
)
def test_clean_snapshot_refuses_index_hint_that_hides_modified_bytes(
    tmp_path: Path, index_flag: str,
):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, tracked = _clean_repo(tmp_path)
    _git(repo, "update-index", index_flag, "tracked.txt")
    tracked.write_text("modified\n", encoding="utf-8")

    # This is the exact dangerous discriminator: ordinary status can still claim
    # the checkout is clean while the bytes differ from HEAD.
    status = _git(repo, "status", "--porcelain=v2", "--branch", "--untracked-files=all")
    assert all(not line or line.startswith("# ") for line in status.stdout.splitlines())
    assert _git(repo, "show", "HEAD:tracked.txt").stdout == "original\n"
    assert tracked.read_text(encoding="utf-8") == "modified\n"

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="index hint"):
        _clean_git_snapshot(
            repo,
            runner=_default_packet_runner,
            env=env,
            label="Mastermind source",
        )


def test_clean_snapshot_neutralizes_repository_local_fsmonitor(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )

    repo, _tracked = _clean_repo(tmp_path)
    marker = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(
        "#!/bin/sh\n"
        f"printf invoked > {str(marker)!r}\n"
        "printf 'token\\n'\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    _git(repo, "config", "core.fsmonitor", str(hook))

    env = _installed_child_env(code_root=repo, macro_root=repo)
    observed = _clean_git_snapshot(
        repo,
        runner=_default_packet_runner,
        env=env,
        label="Mastermind source",
    )

    assert len(observed) == 40
    assert marker.exists() is False
