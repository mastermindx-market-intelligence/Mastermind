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


@pytest.mark.parametrize("metadata_kind", ["gitfile", "symlink"])
def test_clean_snapshot_refuses_non_directory_git_metadata_before_git(
    tmp_path: Path, metadata_kind: str,
):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo = tmp_path / "repo"
    repo.mkdir()
    external_git = tmp_path / "external.git"
    external_git.mkdir()
    git_metadata = repo / ".git"
    if metadata_kind == "gitfile":
        git_metadata.write_text(f"gitdir: {external_git}\n", encoding="utf-8")
    else:
        git_metadata.symlink_to(external_git, target_is_directory=True)

    calls = 0

    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("unsafe Git metadata must refuse before Git execution")

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _clean_git_snapshot(
            repo, runner=runner, env=env, label="Mastermind source",
        )
    assert calls == 0


@pytest.mark.parametrize(
    ("marker_path", "content"),
    [
        ("commondir", "../shared.git\n"),
        ("shallow", "0" * 40 + "\n"),
        ("objects/info/alternates", "/tmp/foreign-objects\n"),
        ("objects/info/http-alternates", "https://example.invalid/objects/\n"),
        ("objects/pack/pack-test.promisor", ""),
    ],
)
def test_clean_snapshot_refuses_unsafe_git_topology_markers_before_git(
    tmp_path: Path, marker_path: str, content: str,
):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    marker = repo / ".git" / marker_path
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(content, encoding="utf-8")
    calls = 0

    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("unsafe topology must refuse before Git execution")

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _clean_git_snapshot(
            repo, runner=runner, env=env, label="Mastermind source",
        )
    assert calls == 0


def test_clean_snapshot_refuses_symlinked_object_store_before_git(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    objects = repo / ".git" / "objects"
    external_objects = tmp_path / "external-objects"
    objects.rename(external_objects)
    objects.symlink_to(external_objects, target_is_directory=True)
    calls = 0

    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("symlinked object store must refuse before Git execution")

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _clean_git_snapshot(
            repo, runner=runner, env=env, label="Mastermind source",
        )
    assert calls == 0


@pytest.mark.parametrize(
    ("config_key", "config_value"),
    [
        ("extensions.partialClone", "origin"),
        ("remote.origin.promisor", "true"),
        ("remote.origin.partialCloneFilter", "blob:none"),
        ("remote.origin.uploadpack", "/tmp/forbidden-upload-pack"),
    ],
)
def test_clean_snapshot_refuses_partial_clone_and_helper_config_before_git(
    tmp_path: Path, config_key: str, config_value: str,
):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    _git(repo, "config", config_key, config_value)
    calls = 0

    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("unsafe repository config must refuse before Git execution")

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _clean_git_snapshot(
            repo, runner=runner, env=env, label="Mastermind source",
        )
    assert calls == 0


def test_clean_snapshot_refuses_missing_reachable_blob(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, tracked = _clean_repo(tmp_path)
    blob_oid = _git(repo, "rev-parse", "HEAD:tracked.txt").stdout.strip()
    object_path = repo / ".git" / "objects" / blob_oid[:2] / blob_oid[2:]
    assert object_path.is_file()
    object_path.unlink()
    assert tracked.read_text(encoding="utf-8") == "original\n"

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="repository objects are incomplete"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env, label="Mastermind source",
        )


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
    with pytest.raises(GatewayError, match="worktree bytes differ"):
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


def test_clean_snapshot_ignores_local_clean_filter_when_hashing_worktree(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, tracked = _clean_repo(tmp_path)
    info_attributes = repo / ".git" / "info" / "attributes"
    info_attributes.write_text("tracked.txt filter=hide\n", encoding="utf-8")
    _git(repo, "config", "filter.hide.clean", "sed s/modified/original/")
    tracked.write_text("modified\n", encoding="utf-8")

    status = subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "core.fsmonitor=false",
            "-c", "core.untrackedCache=false",
            "-c", "core.hooksPath=/dev/null",
            "status", "--porcelain=v2", "--branch", "--untracked-files=all",
        ],
        check=True, capture_output=True, text=True,
    )
    assert all(not line or line.startswith("# ") for line in status.stdout.splitlines())
    assert tracked.read_text(encoding="utf-8") == "modified\n"

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="worktree bytes differ"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env, label="Mastermind source",
        )


def test_clean_snapshot_refuses_untracked_file_hidden_by_info_exclude(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    hidden = repo / "hidden-authoritative.txt"
    hidden.write_text("shadow\n", encoding="utf-8")
    (repo / ".git" / "info" / "exclude").write_text(
        "hidden-authoritative.txt\n", encoding="utf-8"
    )

    status = _git(repo, "status", "--porcelain=v2", "--branch", "--untracked-files=all")
    assert all(not line or line.startswith("# ") for line in status.stdout.splitlines())

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="worktree path set differs"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env, label="Mastermind source",
        )


def _commit_path(repo: Path, relative: str, content: str) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", relative)
    _git(repo, "commit", "-q", "-m", f"add {relative}")
    return path


def test_macro_brief_scope_hashes_records_but_not_unread_tracked_bytes(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, unrelated = _clean_repo(tmp_path)
    record = _commit_path(
        repo, "agentos/workstreams/WS-TEST.md", "---\nkey: TEST\n---\nbody\n"
    )
    env = _installed_child_env(code_root=repo, macro_root=repo)

    # Content outside the brief's byte-reading closure does not affect its result;
    # path existence is still bound by the whole-tree leaf comparison.
    unrelated.write_text("modified but unread\n", encoding="utf-8")
    observed = _clean_git_snapshot(
        repo, runner=_default_packet_runner, env=env,
        label="Macro source", content_scope="macro_brief",
    )
    assert len(observed) == 40

    record.write_text("---\nkey: TEST\n---\nchanged\n", encoding="utf-8")
    with pytest.raises(GatewayError, match="worktree bytes differ"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env,
            label="Macro source", content_scope="macro_brief",
        )


def test_macro_brief_scope_refuses_hidden_extra_anywhere(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    hidden = repo / "ignored" / "phantom.txt"
    hidden.parent.mkdir()
    hidden.write_text("can alter path-existence joins\n", encoding="utf-8")
    (repo / ".git" / "info" / "exclude").write_text("ignored/\n", encoding="utf-8")
    env = _installed_child_env(code_root=repo, macro_root=repo)

    with pytest.raises(GatewayError, match="worktree path set differs"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env,
            label="Macro source", content_scope="macro_brief",
        )


def test_macro_brief_scope_refuses_untracked_empty_directory(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    empty = repo / "phantom-empty"
    empty.mkdir()
    # Git status cannot report an empty directory; Path.exists() in Agent OS can.
    status = _git(repo, "status", "--porcelain=v2", "--branch", "--untracked-files=all")
    assert all(not line or line.startswith("# ") for line in status.stdout.splitlines())
    env = _installed_child_env(code_root=repo, macro_root=repo)

    with pytest.raises(GatewayError, match="worktree path set differs"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env,
            label="Macro source", content_scope="macro_brief",
        )


def test_installed_child_env_disables_ambient_terminal_sibling(tmp_path: Path):
    from integrations.executive_mcp.installed import _installed_child_env

    env = _installed_child_env(code_root=tmp_path / "code", macro_root=tmp_path / "macro")
    assert env["MACRO_TERMINAL_REPO"].endswith("/.executive-no-terminal-repo")
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"


def test_macro_brief_scope_refuses_tracked_leaf_replaced_by_symlink(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, tracked = _clean_repo(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("original\n", encoding="utf-8")
    tracked.unlink()
    tracked.symlink_to(outside)
    env = _installed_child_env(code_root=repo, macro_root=repo)

    with pytest.raises(GatewayError, match="worktree path set differs"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env,
            label="Macro source", content_scope="macro_brief",
        )


def test_macro_brief_scope_refuses_committed_symlink_dependency(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    target = repo / "target.txt"
    target.write_text("target\n", encoding="utf-8")
    link = repo / "linked.txt"
    link.symlink_to("target.txt")
    _git(repo, "add", "target.txt", "linked.txt")
    _git(repo, "commit", "-q", "-m", "add symlink")
    env = _installed_child_env(code_root=repo, macro_root=repo)

    with pytest.raises(GatewayError, match="symlinks are unsupported"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env,
            label="Macro source", content_scope="macro_brief",
        )
