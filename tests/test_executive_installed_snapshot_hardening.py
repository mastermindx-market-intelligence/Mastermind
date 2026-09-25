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


def test_macro_brief_scope_refuses_consumed_symlink_dependency(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    target = repo / "target.md"
    target.write_text("target\n", encoding="utf-8")
    records = repo / "agentos" / "workstreams"
    records.mkdir(parents=True)
    link = records / "linked.md"
    link.symlink_to("../../target.md")
    _git(repo, "add", "target.md", "agentos/workstreams/linked.md")
    _git(repo, "commit", "-q", "-m", "add consumed symlink")
    env = _installed_child_env(code_root=repo, macro_root=repo)

    with pytest.raises(GatewayError, match="symlinks are unsupported"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env,
            label="Macro source", content_scope="macro_brief",
        )


def test_macro_brief_scope_allows_tracked_symlink_outside_read_closure(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )

    repo, _tracked = _clean_repo(tmp_path)
    target = repo / "target.txt"
    target.write_text("target\n", encoding="utf-8")
    unrelated = repo / "collectors" / "marketdesk_extractor"
    unrelated.mkdir(parents=True)
    link = unrelated / "feed.sh"
    link.symlink_to("../../target.txt")
    _git(repo, "add", "target.txt", "collectors/marketdesk_extractor/feed.sh")
    _git(repo, "commit", "-q", "-m", "add unrelated symlink")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    env = _installed_child_env(code_root=repo, macro_root=repo)

    assert _clean_git_snapshot(
        repo, runner=_default_packet_runner, env=env,
        label="Macro source", content_scope="macro_brief",
    ) == head


def test_clean_snapshot_refuses_grafts_before_git(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    grafts = repo / ".git" / "info" / "grafts"
    grafts.parent.mkdir(parents=True, exist_ok=True)
    grafts.write_text("0" * 40 + "\n", encoding="utf-8")
    calls = 0

    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("grafts must refuse before Git execution")

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _clean_git_snapshot(
            repo, runner=runner, env=env, label="Mastermind source",
        )
    assert calls == 0


def test_clean_snapshot_refuses_nonempty_linked_worktree_admin_before_git(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _tracked = _clean_repo(tmp_path)
    admin = repo / ".git" / "worktrees" / "foreign"
    admin.mkdir(parents=True)
    (admin / "HEAD").write_text("ref: refs/heads/foreign\n", encoding="utf-8")
    calls = 0

    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("linked-worktree admin must refuse before Git execution")

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _clean_git_snapshot(
            repo, runner=runner, env=env, label="Macro source",
        )
    assert calls == 0


def test_clean_snapshot_refuses_missing_reachable_parent_commit(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, tracked = _clean_repo(tmp_path)
    tracked.write_text("second\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "second")
    parent_oid = _git(repo, "rev-parse", "HEAD^").stdout.strip()
    parent_object = repo / ".git" / "objects" / parent_oid[:2] / parent_oid[2:]
    assert parent_object.is_file()
    parent_object.unlink()

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="repository objects are incomplete"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env, label="Mastermind source",
        )


def test_clean_snapshot_refuses_missing_reachable_parent_even_with_commit_graph(
    tmp_path: Path,
):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, tracked = _clean_repo(tmp_path)
    tracked.write_text("second\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "second")
    _git(repo, "commit-graph", "write", "--reachable")

    parent_oid = _git(repo, "rev-parse", "HEAD^").stdout.strip()
    parent_object = repo / ".git" / "objects" / parent_oid[:2] / parent_oid[2:]
    assert parent_object.is_file()
    parent_object.unlink()
    assert subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", parent_oid],
        capture_output=True,
    ).returncode != 0

    env = _installed_child_env(code_root=repo, macro_root=repo)
    with pytest.raises(GatewayError, match="repository objects are incomplete"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env, label="Mastermind source",
        )


@pytest.mark.parametrize("tree_suffix", ["^{tree}", ":agentos", ":agentos/workstreams"])
def test_macro_snapshot_refuses_missing_historical_record_tree(tmp_path: Path, tree_suffix: str):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot, _default_packet_runner, _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    macro, _head = _macro_sparse_fixture(tmp_path)
    old_tree = _git(macro, "rev-parse", "HEAD" + tree_suffix).stdout.strip()
    record = macro / "agentos/workstreams/WS-SPARSE.md"
    record.write_text(record.read_text() + "second version\n")
    _git(macro, "add", ".")
    _git(macro, "commit", "-q", "-m", "second")
    _git(macro, "commit-graph", "write", "--reachable")
    (macro / ".git/objects" / old_tree[:2] / old_tree[2:]).unlink()
    # HEAD bytes remain readable, but the exact history reader loses dates.
    assert _git(macro, "ls-tree", "-r", "HEAD").returncode == 0
    broken_log = subprocess.run(
        ["git", "-C", str(macro), "log", "--diff-filter=A", "--format=%as", "--",
         "agentos/workstreams/WS-SPARSE.md"], capture_output=True,
    )
    assert broken_log.returncode != 0
    env = _installed_child_env(code_root=macro, macro_root=macro)
    with pytest.raises(GatewayError, match="repository objects are incomplete"):
        _clean_git_snapshot(
            macro, runner=_default_packet_runner, env=env, label="Macro source",
            content_scope="macro_brief",
        )


def test_macro_history_proof_excludes_unconsumed_historical_objects(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot, _default_packet_runner, _installed_child_env,
    )

    macro, _head = _macro_sparse_fixture(tmp_path)
    old_blob = _git(macro, "rev-parse", "HEAD:unrelated/large.bin").stdout.strip()
    old_tree = _git(macro, "rev-parse", "HEAD:unrelated").stdout.strip()
    (macro / "unrelated/large.bin").write_bytes(b"changed")
    _git(macro, "add", ".")
    _git(macro, "commit", "-q", "-m", "unrelated history")
    for oid in (old_blob, old_tree):
        (macro / ".git/objects" / oid[:2] / oid[2:]).unlink()
    calls = []

    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        assert kwargs["env"]["GIT_NO_LAZY_FETCH"] == "1"
        return _default_packet_runner(argv, **kwargs)

    env = _installed_child_env(code_root=macro, macro_root=macro)
    assert _clean_git_snapshot(
        macro, runner=runner, env=env, label="Macro source", content_scope="macro_brief",
    ) == _git(macro, "rev-parse", "HEAD").stdout.strip()
    tree_walks = [call for call in calls if "--objects" in call]
    assert tree_walks and all("--filter=blob:none" in call and "--" in call for call in tree_walks)


@pytest.mark.parametrize("shape", ["ignored", "tracked", "no-repository"])
def test_clean_snapshot_refuses_root_without_direct_git_before_git(
    tmp_path: Path, shape: str,
):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    ancestor = tmp_path / "ancestor"
    ancestor.mkdir()
    subprocess.run(["git", "init", "-q", str(ancestor)], check=True)
    _git(ancestor, "config", "user.email", "test@example.invalid")
    _git(ancestor, "config", "user.name", "Test")
    (ancestor / "README.md").write_text("ancestor\n", encoding="utf-8")
    nested = ancestor / "payload"
    nested.mkdir()
    if shape == "ignored":
        (ancestor / ".gitignore").write_text("payload/\n", encoding="utf-8")
        record = nested / "agentos" / "workstreams" / "example.md"
        record.parent.mkdir(parents=True)
        record.write_text("UNCOMMITTED\n", encoding="utf-8")
    elif shape == "tracked":
        (nested / "tracked.txt").write_text("tracked\n", encoding="utf-8")
        _git(ancestor, "add", "payload/tracked.txt")
    else:
        nested = tmp_path / "not-a-repository"
        nested.mkdir()
    _git(ancestor, "add", "README.md", ".gitignore") if shape == "ignored" else None
    _git(ancestor, "commit", "-q", "-m", "ancestor") if shape != "no-repository" else None

    calls = 0
    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("missing direct .git must refuse before Git execution")

    env = _installed_child_env(code_root=ancestor, macro_root=nested)
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        _clean_git_snapshot(
            nested, runner=runner, env=env, label="Macro source",
        )
    assert calls == 0


def test_installed_collector_refuses_when_direct_git_disappears_before_child(
    tmp_path: Path,
):
    import json
    import shutil
    from integrations.executive_mcp.installed import (
        InstalledBootPacketCollector,
        _default_packet_runner,
    )
    from integrations.executive_mcp.schemas import GatewayError

    mastermind_fixture = tmp_path / "mastermind-fixture"
    macro_fixture = tmp_path / "macro-fixture"
    mastermind_fixture.mkdir()
    macro_fixture.mkdir()
    repo, _tracked = _clean_repo(mastermind_fixture)
    macro, _macro_tracked = _clean_repo(macro_fixture)
    code = tmp_path / "immutable-release"
    (code / "scripts").mkdir(parents=True)
    python = tmp_path / "python"
    python.write_text("fixture", encoding="utf-8")
    source_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    macro_sha = _git(macro, "rev-parse", "HEAD").stdout.strip()
    helper_called = False
    removed = False

    def runner(argv, **kwargs):
        nonlocal helper_called, removed
        if str(argv[0]) == "git":
            result = _default_packet_runner(argv, **kwargs)
            # Remove Macro metadata after the source pre-observation completes.
            if Path(kwargs["cwd"]) == repo and not removed:
                shutil.rmtree(macro / ".git")
                removed = True
            return result
        helper_called = True
        return {
            "code": 0,
            "stdout": json.dumps({
                "schema": "mastermind.ceo_boot_packet.v1",
                "mastermind": {"root": str(repo), "sha": source_sha, "branch": "HEAD"},
                "macro": {
                    "root": str(macro), "sha": macro_sha,
                    "resolved_via": "flag", "candidates_tried": [],
                },
            }),
            "stderr": "", "timed_out": False,
            "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha=source_sha,
    )
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        collector(
            repo_root=repo, macro_root_flag=str(macro), now=None, timeout=5.0,
        )
    assert helper_called is False


def test_installed_grounding_observer_refuses_nested_root_without_direct_git(
    tmp_path: Path,
):
    import subprocess
    from integrations.executive_mcp.installed import InstalledExecutiveReaders

    ancestor = tmp_path / "ancestor"
    ancestor.mkdir()
    subprocess.run(["git", "init", "-q", str(ancestor)], check=True)
    _git(ancestor, "config", "user.email", "test@example.invalid")
    _git(ancestor, "config", "user.name", "Test")
    (ancestor / ".gitignore").write_text("payload/\n", encoding="utf-8")
    (ancestor / "README.md").write_text("ancestor\n", encoding="utf-8")
    _git(ancestor, "add", ".gitignore", "README.md")
    _git(ancestor, "commit", "-q", "-m", "ancestor")

    nested = ancestor / "payload"
    record = nested / "agentos" / "workstreams" / "example.md"
    record.parent.mkdir(parents=True)
    record.write_text("UNCOMMITTED\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    readers = InstalledExecutiveReaders(
        repo_root=ancestor, macro_root=nested, runtime_root=runtime,
    )
    with pytest.raises(ValueError, match="grounding is unavailable"):
        readers.observe()


def test_installed_collector_refuses_if_git_disappears_after_macro_presnapshot(
    tmp_path: Path,
):
    import json
    import shutil
    from integrations.executive_mcp.installed import (
        InstalledBootPacketCollector,
        _default_packet_runner,
    )
    from integrations.executive_mcp.schemas import GatewayError

    mastermind_fixture = tmp_path / "mastermind-fixture-2"
    macro_fixture = tmp_path / "macro-fixture-2"
    mastermind_fixture.mkdir()
    macro_fixture.mkdir()
    repo, _tracked = _clean_repo(mastermind_fixture)
    macro, _macro_tracked = _clean_repo(macro_fixture)
    code = tmp_path / "immutable-release-2"
    (code / "scripts").mkdir(parents=True)
    python = tmp_path / "python-2"
    python.write_text("fixture", encoding="utf-8")
    source_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    macro_sha = _git(macro, "rev-parse", "HEAD").stdout.strip()
    macro_head_observations = 0
    helper_called = False

    def runner(argv, **kwargs):
        nonlocal macro_head_observations, helper_called
        if str(argv[0]) == "git":
            result = _default_packet_runner(argv, **kwargs)
            if (
                Path(kwargs["cwd"]) == macro
                and tuple(str(item) for item in argv[1:])
                == ("rev-parse", "--verify", "HEAD^{commit}")
            ):
                macro_head_observations += 1
                # The snapshot begins and ends by observing the exact HEAD.
                # Remove .git only after the second observation has returned,
                # which is the completed pre-snapshot boundary independent of
                # how many bounded object/tree checks happen in between.
                if macro_head_observations == 2:
                    shutil.rmtree(macro / ".git")
            return result
        helper_called = True
        return {
            "code": 0,
            "stdout": json.dumps({
                "schema": "mastermind.ceo_boot_packet.v1",
                "mastermind": {"root": str(repo), "sha": source_sha, "branch": "HEAD"},
                "macro": {
                    "root": str(macro), "sha": macro_sha,
                    "resolved_via": "flag", "candidates_tried": [],
                },
            }),
            "stderr": "", "timed_out": False,
            "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha=source_sha,
    )
    with pytest.raises(GatewayError, match="repository topology is unsafe"):
        collector(
            repo_root=repo, macro_root_flag=str(macro), now=None, timeout=5.0,
        )
    assert macro_head_observations == 2
    assert helper_called is False


def test_clean_snapshot_avoids_full_reachable_object_history_transport(tmp_path: Path):
    """Production history can contain millions of objects; closure proof must not
    serialize every historical tree/blob through the bounded runner."""
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )

    repo, tracked = _clean_repo(tmp_path)
    tracked.write_text("second\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-q", "-m", "second")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    calls: list[tuple[str, ...]] = []

    def bounded_runner(argv, **kwargs):
        normalized = tuple(str(item) for item in argv)
        calls.append(normalized)
        if len(normalized) >= 3 and normalized[:2] == ("git", "rev-list") and "--objects" in normalized:
            return {
                "code": 0,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
                "limit_exceeded": True,
                "invalid_utf8": False,
            }
        return _default_packet_runner(argv, **kwargs)

    env = _installed_child_env(code_root=repo, macro_root=repo)
    assert _clean_git_snapshot(
        repo, runner=bounded_runner, env=env, label="Mastermind source",
    ) == head
    assert any(call[:2] == ("git", "rev-list") and "--parents" in call for call in calls)
    assert not any(call[:2] == ("git", "rev-list") and "--objects" in call for call in calls)


def test_installed_collector_runs_macro_closure_once_with_cumulative_budget(
    tmp_path: Path,
):
    import json
    from integrations.executive_mcp.installed import (
        InstalledBootPacketCollector,
        _default_packet_runner,
    )

    mastermind_parent = tmp_path / "mastermind-fixture"
    macro_parent = tmp_path / "macro-fixture"
    mastermind_parent.mkdir()
    macro_parent.mkdir()
    repo, _tracked = _clean_repo(mastermind_parent)
    macro, _macro_tracked = _clean_repo(macro_parent)
    code = tmp_path / "immutable-release"
    (code / "scripts").mkdir(parents=True)
    python = tmp_path / "python"
    python.write_text("fixture", encoding="utf-8")
    source_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    macro_sha = _git(macro, "rev-parse", "HEAD").stdout.strip()
    macro_history_walks = 0
    child_budget: dict[str, float] = {}

    def runner(argv, **kwargs):
        nonlocal macro_history_walks
        normalized = tuple(str(item) for item in argv)
        if normalized[0] == "git":
            if (
                Path(kwargs["cwd"]) == macro
                and normalized[1:3] == ("rev-list", "--parents")
            ):
                macro_history_walks += 1
            return _default_packet_runner(argv, **kwargs)

        child_macro = Path(normalized[normalized.index("--macro-root") + 1])
        child_budget["runner"] = float(kwargs["timeout"])
        child_budget["inner"] = float(normalized[normalized.index("--timeout") + 1])
        return {
            "code": 0,
            "stdout": json.dumps({
                "schema": "mastermind.ceo_boot_packet.v1",
                "mastermind": {"root": str(repo), "sha": source_sha, "branch": "HEAD"},
                "macro": {
                    "root": str(child_macro), "sha": macro_sha,
                    "resolved_via": "flag", "candidates_tried": [],
                },
            }),
            "stderr": "", "timed_out": False,
            "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha=source_sha,
    )
    packet = collector(
        repo_root=repo, macro_root_flag=str(macro), now=None, timeout=28.0,
    )

    assert macro_history_walks == 1
    assert 0 < child_budget["runner"] < 28.0
    assert 0 < child_budget["inner"] < child_budget["runner"]
    assert packet["mastermind"]["sha"] == source_sha
    assert packet["macro"]["sha"] == macro_sha
    assert packet["macro"]["root"] == str(macro)


def _macro_sparse_fixture(tmp_path: Path) -> tuple[Path, str]:
    macro = tmp_path / "macro-sparse"
    (macro / "scripts").mkdir(parents=True)
    (macro / "config").mkdir()
    (macro / "data/governance").mkdir(parents=True)
    (macro / "agentos/workstreams").mkdir(parents=True)
    (macro / "agentos/decisions").mkdir()
    (macro / "agentos/discoveries").mkdir()
    (macro / "agentos/handoffs").mkdir()
    (macro / "research").mkdir()
    (macro / "data/probe/nested").mkdir(parents=True)
    (macro / "unrelated").mkdir()

    (macro / "scripts/__init__.py").write_text("", encoding="utf-8")
    (macro / "scripts/agentos.py").write_text("print('fixture')\n", encoding="utf-8")
    (macro / "scripts/audit_stranded_work.py").write_text("", encoding="utf-8")
    (macro / "config/mastermind_programs.yml").write_text(
        "schema: mastermind_programs.v1\nontology: {lifecycle_states: [active]}\nprograms: {}\n",
        encoding="utf-8",
    )
    (macro / "data/governance/active_builds.json").write_text(
        '{"schema":"active_builds.v1"}\n', encoding="utf-8",
    )
    (macro / "research/evidence.md").write_text("evidence\n", encoding="utf-8")
    (macro / "data/probe/nested/payload.json").write_text("{}\n", encoding="utf-8")
    (macro / "unrelated/large.bin").write_bytes(b"x" * 1024)
    (macro / "agentos/decisions/DEC-ONE.md").write_text("---\nkey: ONE\n---\n", encoding="utf-8")
    # Git cannot bind empty directories. Keep the fixture's canonical Agent OS
    # namespaces represented by tracked records so the full path-set verifier
    # is testing source behavior rather than fixture-only empty-directory drift.
    (macro / "agentos/discoveries/DISC-ONE.md").write_text("---\nkey: DISC-ONE\n---\n", encoding="utf-8")
    (macro / "agentos/handoffs/HANDOFF-ONE.md").write_text("---\nkey: HANDOFF-ONE\n---\n", encoding="utf-8")
    (macro / "agentos/workstreams/WS-SPARSE.md").write_text(
        """---
key: SPARSE
title: Sparse fixture
objective: Preserve exact read semantics.
status: active
program: fixture
repos: [macro, terminal]
owner: Sol
class: build
blast_radius: reversible
ambiguity: specified
owns_paths:
  - data/probe/**
  - terminal:site/**
  - missing/**
artifacts:
  - research/evidence.md
  - terminal:research/external.md
waves:
  - id: W0
    title: Fixture
    status: in_progress
next_action: Continue.
---
body
""",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(macro)], check=True)
    _git(macro, "config", "user.email", "test@example.invalid")
    _git(macro, "config", "user.name", "Test")
    _git(macro, "add", ".")
    _git(macro, "commit", "-q", "-m", "fixture")
    return macro, _git(macro, "rev-parse", "HEAD").stdout.strip()


def test_sparse_macro_materialization_preserves_brief_and_path_existence_closure(
    tmp_path: Path,
):
    from integrations.executive_mcp.installed import (
        _build_macro_materialization_plan,
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
        _materialized_macro_root,
    )

    macro, head = _macro_sparse_fixture(tmp_path)
    env = _installed_child_env(code_root=macro, macro_root=macro)
    plan = _build_macro_materialization_plan(
        macro, runner=_default_packet_runner, env=env, deadline=None,
    )

    assert plan.head == head
    assert "scripts/agentos.py" in plan.files
    assert "agentos/workstreams/WS-SPARSE.md" in plan.files
    assert "research/evidence.md" in plan.files
    assert "data/probe" in plan.directories
    assert "unrelated/large.bin" not in plan.files
    assert all(not path.startswith("terminal:") for path in plan.files)
    assert all(not path.startswith("missing") for path in plan.files | plan.directories)

    with _materialized_macro_root(macro, timeout=5.0, plan=plan) as materialized:
        assert materialized != macro
        assert (materialized / "scripts/agentos.py").read_text(encoding="utf-8") == "print('fixture')\n"
        assert (materialized / "research/evidence.md").read_text(encoding="utf-8") == "evidence\n"
        assert (materialized / "data/probe").is_dir()
        assert not (materialized / "unrelated/large.bin").exists()
        assert not (materialized / ".git/index").exists()
        assert not (materialized / ".git/hooks").exists()
        assert not (materialized / ".git/logs").exists()
        assert _git(materialized, "rev-parse", "HEAD").stdout.strip() == head
        assert _git(
            materialized, "log", "-1", "--format=%H", "--",
            "agentos/workstreams/WS-SPARSE.md",
        ).stdout.strip() == head
        assert _git(materialized, "worktree", "list", "--porcelain").stdout
        child_env = _installed_child_env(code_root=macro, macro_root=materialized)
        observed = _clean_git_snapshot(
            materialized,
            runner=_default_packet_runner,
            env=child_env,
            label="materialized Macro source",
            content_scope="macro_brief",
            include_seal=True,
            verify_repository_closure=False,
            admitted_worktree_files=set(plan.files),
            admitted_worktree_directories=set(plan.directories),
        )
        assert observed[0] == head


@pytest.mark.parametrize("field", ["artifacts", "owns_paths"])
@pytest.mark.parametrize("suffix", ["evidence.md", "nested/**"])
@pytest.mark.parametrize("link_path", ["alias", "links/alias"])
@pytest.mark.parametrize("target_kind", ["internal", "external", "dangling"])
def test_sparse_macro_materialization_refuses_symlink_prefix(
    tmp_path: Path, field: str, suffix: str, link_path: str, target_kind: str,
):
    from integrations.executive_mcp.installed import (
        _build_macro_materialization_plan, _default_packet_runner, _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    macro, _head = _macro_sparse_fixture(tmp_path)
    target = macro / "research" if target_kind == "internal" else tmp_path / target_kind
    if target_kind != "dangling":
        (target / "nested").mkdir(parents=True)
        (target / "evidence.md").write_text("evidence\n")
        (target / "nested/payload.md").write_text("nested evidence\n")
    link = macro / link_path
    link.parent.mkdir(parents=True, exist_ok=True)
    link_target = ("../" * (len(link.parts) - len(macro.parts) - 1) + "research") \
        if target_kind == "internal" else target
    link.symlink_to(link_target, target_is_directory=True)
    (macro / "agentos/workstreams/WS-SPARSE.md").write_text(
        f"---\nrepos: [macro]\n{field}:\n  - {link_path}/{suffix}\n---\n",
    )
    _git(macro, "add", ".")
    _git(macro, "commit", "-q", "-m", "path probe through tracked symlink")
    assert not _git(macro, "status", "--porcelain").stdout
    probe = f"{link_path}/nested" if suffix.endswith("/**") else f"{link_path}/{suffix}"
    assert (macro / probe).exists() is (target_kind != "dangling")
    env = _installed_child_env(code_root=macro, macro_root=macro)

    with pytest.raises(GatewayError, match="path-list frontmatter is unsupported") as refused:
        _build_macro_materialization_plan(
            macro, runner=_default_packet_runner, env=env, deadline=None,
        )
    assert "symlink" in str(refused.value.__cause__)


@pytest.mark.parametrize("field", ["artifacts", "owns_paths"])
@pytest.mark.parametrize("suffix", ["evidence.md", "nested/**"])
def test_sparse_macro_materialization_preserves_direct_directory_prefix(
    tmp_path: Path, field: str, suffix: str,
):
    from integrations.executive_mcp.installed import (
        _build_macro_materialization_plan, _default_packet_runner,
        _installed_child_env, _materialized_macro_root,
    )

    macro, _head = _macro_sparse_fixture(tmp_path)
    (macro / "links/alias/nested").mkdir(parents=True)
    (macro / "links/alias/evidence.md").write_text("evidence\n")
    (macro / "links/alias/nested/payload.md").write_text("nested evidence\n")
    (macro / "agentos/workstreams/WS-SPARSE.md").write_text(
        f"---\nrepos: [macro]\n{field}:\n  - links/alias/{suffix}\n---\n",
    )
    _git(macro, "add", ".")
    _git(macro, "commit", "-q", "-m", "path probe through direct directories")
    env = _installed_child_env(code_root=macro, macro_root=macro)
    plan = _build_macro_materialization_plan(
        macro, runner=_default_packet_runner, env=env, deadline=None,
    )
    probe = "links/alias/nested" if suffix.endswith("/**") else f"links/alias/{suffix}"
    with _materialized_macro_root(macro, timeout=5.0, plan=plan) as materialized:
        assert (materialized / probe).exists() == (macro / probe).exists() is True


def test_sparse_macro_materialization_refuses_unsupported_path_list_shape(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _build_macro_materialization_plan,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    macro, _head = _macro_sparse_fixture(tmp_path)
    record = macro / "agentos/workstreams/WS-SPARSE.md"
    text = record.read_text(encoding="utf-8").replace(
        "artifacts:\n  - research/evidence.md\n  - terminal:research/external.md\n",
        "artifacts: {path: research/evidence.md}\n",
    )
    record.write_text(text, encoding="utf-8")
    _git(macro, "add", str(record.relative_to(macro)))
    _git(macro, "commit", "-q", "-m", "unsupported path list")
    env = _installed_child_env(code_root=macro, macro_root=macro)

    with pytest.raises(GatewayError, match="path-list frontmatter is unsupported"):
        _build_macro_materialization_plan(
            macro, runner=_default_packet_runner, env=env, deadline=None,
        )


@pytest.mark.parametrize("path_fields", [
    "repos:\n- macro\nartifacts:\n- research/it's.md\nowns_paths:\n- data/probe/**\n",
    "'repos': [macro]\n\"artifacts\":\n  - research/it's.md\n'owns_paths':\n  - data/probe/**\n",
    "repos: [macro]\nartifacts:\n  - 'research/it''s.md'\nowns_paths:\n  - 'data/probe/**'\n",
])
def test_sparse_macro_yaml_forms_preserve_canonical_path_existence(tmp_path: Path, path_fields: str):
    import yaml
    from integrations.executive_mcp.installed import (
        _build_macro_materialization_plan, _default_packet_runner,
        _frontmatter_lists, _installed_child_env, _materialized_macro_root,
    )

    macro, _head = _macro_sparse_fixture(tmp_path)
    payload = ("---\n" + path_fields + "---\nbody\n").encode()
    (macro / "agentos/workstreams/WS-SPARSE.md").write_bytes(payload)
    (macro / "research/it's.md").write_text("evidence\n")
    _git(macro, "add", ".")
    _git(macro, "commit", "-q", "-m", "valid YAML path forms")
    canonical = yaml.safe_load(path_fields)
    assert _frontmatter_lists(payload) == canonical
    env = _installed_child_env(code_root=macro, macro_root=macro)
    plan = _build_macro_materialization_plan(
        macro, runner=_default_packet_runner, env=env, deadline=None,
    )
    with _materialized_macro_root(macro, timeout=5.0, plan=plan) as materialized:
        for relative in canonical["artifacts"]:
            assert (materialized / relative).exists() == (macro / relative).exists() is True
        assert (materialized / "data/probe").is_dir()
        assert not (materialized / "research/its.md").exists()


@pytest.mark.parametrize("path_fields", [
    "# Valid YAML with a uniformly indented root mapping.\n\n"
    "  repos: [macro]\n  artifacts:\n    - research/evidence.md\n"
    "  owns_paths:\n    - data/probe/**\n",
    "defaults: &paths\n  repos: [macro]\n  artifacts:\n    - research/evidence.md\n"
    "  owns_paths:\n    - data/probe/**\n<<: *paths\n",
    "<<: {repos: [macro], artifacts: [research/evidence.md], owns_paths: [data/probe/**]}\n",
    "&root\n  repos: [macro]\n  artifacts:\n    - research/evidence.md\n"
    "  owns_paths:\n    - data/probe/**\n",
])
def test_sparse_macro_refuses_unsupported_yaml_root_and_merges(tmp_path: Path, path_fields: str):
    import yaml
    from integrations.executive_mcp.installed import (
        _build_macro_materialization_plan, _default_packet_runner,
        _frontmatter_lists, _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    macro, _head = _macro_sparse_fixture(tmp_path)
    canonical = yaml.safe_load(path_fields)
    assert canonical["repos"] == ["macro"]
    assert canonical["artifacts"] == ["research/evidence.md"]
    assert canonical["owns_paths"] == ["data/probe/**"]
    assert (macro / canonical["artifacts"][0]).is_file()
    payload = ("---\n" + path_fields + "---\nbody\n").encode()
    (macro / "agentos/workstreams/WS-SPARSE.md").write_bytes(payload)
    _git(macro, "add", ".")
    _git(macro, "commit", "-q", "-m", "unsupported valid YAML root")
    # These forms are outside the closed parser subset, never empty path lists.
    with pytest.raises(ValueError, match="unsupported"):
        _frontmatter_lists(payload)
    env = _installed_child_env(code_root=macro, macro_root=macro)
    with pytest.raises(GatewayError, match="path-list frontmatter is unsupported"):
        _build_macro_materialization_plan(
            macro, runner=_default_packet_runner, env=env, deadline=None,
        )


@pytest.mark.parametrize("document", [
    "{\n  repos: [macro],\n  artifacts: [research/evidence.md]\n}\n",
    "[\n  {artifacts: [research/evidence.md]}\n]\n",
    "- artifacts: [research/evidence.md]\n",
    "a plain scalar root\n",
    "null\n",
    "\n# Empty YAML document.\n",
    "? artifacts\n: [research/evidence.md]\n",
    "!!map\nartifacts: [research/evidence.md]\n",
    "artifacts: [research/evidence.md]\n...\n",
    "artifacts:\n  - research/evidence.md\n    folded continuation\n",
])
def test_frontmatter_closed_grammar_refuses_valid_unsupported_roots(document: str):
    import yaml
    from integrations.executive_mcp.installed import _frontmatter_lists

    # Every discriminator is valid canonical YAML, not a malformed-input check.
    yaml.safe_load(document)
    payload = ("---\n" + document + "---\n").encode()
    with pytest.raises(ValueError, match="unsupported"):
        _frontmatter_lists(payload)


@pytest.mark.parametrize("document", [
    "artifacts: []\n%YAML 1.1\n",
    "artifacts: []\nstray structural line\n",
    "artifacts: []\n  stray indentation\n",
    "artifacts: []\n- stray sequence item\n",
])
def test_frontmatter_closed_grammar_refuses_unowned_structure(document: str):
    from integrations.executive_mcp.installed import _frontmatter_lists

    with pytest.raises(ValueError, match="unsupported"):
        _frontmatter_lists(("---\n" + document + "---\n").encode())


def test_frontmatter_closed_grammar_preserves_explicit_nested_metadata():
    import yaml
    from integrations.executive_mcp.installed import _frontmatter_lists

    document = """title: A record
objective: >
  Plain folded metadata can mention artifacts: without becoming a root key.
waves:
  - id: W0
    status: in_progress
    pr: [834, 900]
    note: |
      Literal metadata remains metadata.
      repos: [terminal]
    details:
      owner: Sol
repos: [macro, terminal]
artifacts:
- research/evidence.md
owns_paths:
  - data/probe/**
landmines:
  - 'Do not drop read paths.'
  - "A quoted metadata item may continue
    on an indented line without consuming a root field."
  - Unquoted narrative metadata may also
    continue on an indented line.
other_waves:
  - {id: W1, title: "A bounded metadata map", status: done, pr: 834}
"""
    canonical = yaml.safe_load(document)
    assert _frontmatter_lists(("---\n" + document + "---\n").encode()) == {
        field: canonical[field] for field in ("repos", "artifacts", "owns_paths")
    }


@pytest.mark.parametrize("value", ["*paths", "&paths []", "!!seq []", "{artifacts: []}", "|"])
def test_frontmatter_consumed_fields_refuse_node_properties_and_nonlists(value: str):
    from integrations.executive_mcp.installed import _frontmatter_lists

    with pytest.raises(ValueError, match="unsupported"):
        _frontmatter_lists(f"---\nartifacts: {value}\n---\n".encode())


@pytest.mark.parametrize("item", ["? research/evidence.md", "- research/evidence.md", "0x10", ".5", "2026-09-22", "# comment"])
def test_frontmatter_consumed_items_refuse_yaml_nonstring_nodes(item: str):
    import yaml
    from integrations.executive_mcp.installed import _frontmatter_lists

    document = f"artifacts:\n  - {item}\n"
    assert not isinstance(yaml.safe_load(document)["artifacts"][0], str)
    with pytest.raises(ValueError, match="unsupported"):
        _frontmatter_lists(("---\n" + document + "---\n").encode())


@pytest.mark.parametrize("document", [
    'title: "unfinished\nartifacts: []\nowner: Sol"\n',
    'metadata:\n  - "unfinished\nartifacts: []\nowner: Sol"\n',
    'metadata:\n  nested: {note: "unfinished\nartifacts: []\nowner: Sol"}\n',
])
def test_frontmatter_metadata_cannot_hide_root_fields_in_unfinished_quotes(document: str):
    import yaml
    from integrations.executive_mcp.installed import _frontmatter_lists

    canonical = yaml.safe_load(document)
    assert "artifacts" not in canonical
    with pytest.raises(ValueError, match="unsupported"):
        _frontmatter_lists(("---\n" + document + "---\n").encode())


def _direct_pair_collector(tmp_path: Path):
    from integrations.executive_mcp.installed import InstalledBootPacketCollector

    source_parent = tmp_path / "source-parent"
    macro_parent = tmp_path / "macro-parent"
    source_parent.mkdir()
    macro_parent.mkdir()
    source, _source_file = _clean_repo(source_parent)
    macro, _macro_file = _clean_repo(macro_parent)
    code = tmp_path / "immutable-release"
    (code / "scripts").mkdir(parents=True)
    python = tmp_path / "python"
    python.write_text("fixture", encoding="utf-8")
    source_sha = _git(source, "rev-parse", "HEAD").stdout.strip()
    macro_sha = _git(macro, "rev-parse", "HEAD").stdout.strip()
    collector = InstalledBootPacketCollector(
        source_root=source,
        macro_root=macro,
        code_root=code,
        python_executable=python,
        expected_source_sha=source_sha,
    )
    return collector, source, macro, source_sha, macro_sha


def test_inner_packet_timeout_uses_reviewed_subsecond_settlement_reserve():
    from integrations.executive_mcp.installed import _inner_packet_timeout

    # The outer installed-reader budget remains 28s inside the 30s gateway.
    # Only the nested child settlement reserve changes, per production proof.
    assert _inner_packet_timeout(28.0) == pytest.approx(27.25)


def test_installed_collector_pre_snapshots_overlap_for_direct_repositories(
    tmp_path: Path, monkeypatch,
):
    import threading
    import time
    from integrations.executive_mcp import installed

    collector, source, macro, source_sha, macro_sha = _direct_pair_collector(tmp_path)
    rendezvous = threading.Barrier(2)
    thread_ids: set[int] = set()

    def snapshot(path: Path, **_kwargs):
        thread_ids.add(threading.get_ident())
        rendezvous.wait(timeout=1.0)
        if Path(path) == source:
            return source_sha, "source-seal"
        if Path(path) == macro:
            return macro_sha, "macro-seal"
        raise AssertionError(f"unexpected snapshot root: {path}")

    monkeypatch.setattr(installed, "_clean_git_snapshot", snapshot)
    observed = collector._snapshot_pair({}, deadline=time.monotonic() + 2.0)

    assert observed == (source_sha, macro_sha, "source-seal", "macro-seal")
    assert len(thread_ids) == 2


def test_installed_collector_post_generations_overlap_for_direct_repositories(
    tmp_path: Path, monkeypatch,
):
    import threading
    import time
    from integrations.executive_mcp import installed

    collector, source, macro, source_sha, macro_sha = _direct_pair_collector(tmp_path)
    rendezvous = threading.Barrier(2)
    thread_ids: set[int] = set()

    def generation(path: Path, **_kwargs):
        thread_ids.add(threading.get_ident())
        rendezvous.wait(timeout=1.0)
        if Path(path) == source:
            return source_sha, "source-seal"
        if Path(path) == macro:
            return macro_sha, "macro-seal"
        raise AssertionError(f"unexpected generation root: {path}")

    monkeypatch.setattr(installed, "_snapshot_generation_observation", generation)
    observed = collector._generation_pair({}, deadline=time.monotonic() + 2.0)

    assert observed == (source_sha, macro_sha, "source-seal", "macro-seal")
    assert len(thread_ids) == 2


def test_installed_collector_pair_enforces_outer_cumulative_deadline(
    tmp_path: Path, monkeypatch,
):
    import time
    from integrations.executive_mcp import installed
    from integrations.executive_mcp.schemas import GatewayError

    collector, _source, _macro, _source_sha, _macro_sha = _direct_pair_collector(tmp_path)

    def ignores_deadline(*_args, **_kwargs):
        time.sleep(0.30)
        return "a" * 40, "seal"

    monkeypatch.setattr(installed, "_clean_git_snapshot", ignores_deadline)
    started = time.monotonic()
    with pytest.raises(GatewayError, match="cumulative deadline"):
        collector._snapshot_pair({}, deadline=started + 0.05)
    assert time.monotonic() - started < 0.20


def test_installed_collector_synthetic_snapshot_pair_stays_sequential(
    tmp_path: Path, monkeypatch,
):
    from integrations.executive_mcp import installed
    from integrations.executive_mcp.installed import InstalledBootPacketCollector

    source = tmp_path / "source"
    macro = tmp_path / "macro"
    code = tmp_path / "code"
    for root in (source, macro, code):
        root.mkdir()
    python = tmp_path / "python"
    python.write_text("fixture", encoding="utf-8")
    calls: list[Path] = []

    def snapshot(path: Path, **_kwargs):
        calls.append(Path(path))
        marker = "a" if Path(path) == source else "b"
        return marker * 40, f"{marker}-seal"

    monkeypatch.setattr(installed, "_clean_git_snapshot", snapshot)
    collector = InstalledBootPacketCollector(
        source_root=source,
        macro_root=macro,
        code_root=code,
        python_executable=python,
        expected_source_sha="a" * 40,
        _allow_synthetic_fixture=True,
    )

    assert collector._snapshot_pair({}, deadline=None) == (
        "a" * 40, "b" * 40, "a-seal", "b-seal",
    )
    assert calls == [source, macro]


def test_clean_snapshot_uses_buffered_type_only_object_probes(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )

    repo, _tracked = _clean_repo(tmp_path)
    commands: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        normalized = tuple(str(item) for item in argv)
        commands.append(normalized)
        return _default_packet_runner(argv, **kwargs)

    env = _installed_child_env(code_root=repo, macro_root=repo)
    _clean_git_snapshot(
        repo, runner=runner, env=env, label="Mastermind source",
    )

    probes = [
        command for command in commands
        if command[:2] == ("git", "cat-file")
    ]
    assert probes
    assert all("--buffer" in command for command in probes)
    assert all(
        "--batch-check=%(objectname) %(objecttype)" in command
        for command in probes
    )
    assert all(
        not any("objectsize" in argument for argument in command)
        for command in probes
    )


def test_macro_materialization_plan_reuses_verified_tree(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _build_macro_materialization_plan,
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )

    macro, head = _macro_sparse_fixture(tmp_path)
    env = _installed_child_env(code_root=macro, macro_root=macro)
    commands: list[tuple[str, ...]] = []
    captures = []

    def runner(argv, **kwargs):
        normalized = tuple(str(item) for item in argv)
        commands.append(normalized)
        return _default_packet_runner(argv, **kwargs)

    observed = _clean_git_snapshot(
        macro, runner=runner, env=env, label="Macro source",
        content_scope="macro_brief", include_seal=True,
        snapshot_capture=captures,
    )
    assert observed[0] == head
    assert len(captures) == 1

    plan = _build_macro_materialization_plan(
        macro, runner=runner, env=env, deadline=None,
        verified_snapshot=captures[0],
    )

    assert plan.head == head
    assert set(plan.file_objects) == set(plan.files)
    assert sum(
        command[1:4] == ("ls-tree", "-r", "-z")
        for command in commands
    ) == 1


def test_materialized_macro_verifier_uses_preverified_object_map(tmp_path: Path):
    from integrations.executive_mcp.installed import (
        _build_macro_materialization_plan,
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
        _materialized_macro_root,
        _verify_materialized_macro_root,
    )
    from integrations.executive_mcp.schemas import GatewayError

    macro, head = _macro_sparse_fixture(tmp_path)
    live_env = _installed_child_env(code_root=macro, macro_root=macro)
    captures = []
    _clean_git_snapshot(
        macro, runner=_default_packet_runner, env=live_env,
        label="Macro source", content_scope="macro_brief", include_seal=True,
        snapshot_capture=captures,
    )
    plan = _build_macro_materialization_plan(
        macro, runner=_default_packet_runner, env=live_env, deadline=None,
        verified_snapshot=captures[0],
    )

    with _materialized_macro_root(macro, timeout=5.0, plan=plan) as materialized:
        child_env = _installed_child_env(code_root=macro, macro_root=materialized)
        commands: list[tuple[str, ...]] = []

        def runner(argv, **kwargs):
            normalized = tuple(str(item) for item in argv)
            commands.append(normalized)
            return _default_packet_runner(argv, **kwargs)

        observed = _verify_materialized_macro_root(
            materialized, plan=plan, runner=runner, env=child_env,
            deadline=None,
        )
        assert observed[0] == head
        assert not any(command[1:2] == ("rev-list",) for command in commands)
        assert not any(command[1:2] == ("ls-tree",) for command in commands)

        target = materialized / "agentos/workstreams/WS-SPARSE.md"
        original = target.read_bytes()
        target.write_bytes(original + b"mutated\n")
        with pytest.raises(GatewayError, match="worktree bytes differ"):
            _verify_materialized_macro_root(
                materialized, plan=plan, runner=_default_packet_runner,
                env=child_env, deadline=None,
            )


def test_installed_collector_reuses_single_macro_tree_proof_before_child(tmp_path: Path):
    """Collector composition: one live Macro ls-tree, no materialized tree walk,
    child starts only after both proofs. Fixture-scale only.
    """
    import json
    from integrations.executive_mcp.installed import (
        InstalledBootPacketCollector,
        _default_packet_runner,
    )

    mastermind_parent = tmp_path / "mastermind-fixture"
    mastermind_parent.mkdir()
    repo, _tracked = _clean_repo(mastermind_parent)
    macro, macro_sha = _macro_sparse_fixture(tmp_path)
    code = tmp_path / "immutable-release"
    (code / "scripts").mkdir(parents=True)
    python = tmp_path / "python"
    python.write_text("fixture", encoding="utf-8")
    source_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    live_macro = macro.resolve()
    live_source = repo.resolve()
    events: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        argv_s = tuple(str(item) for item in argv)
        cwd = Path(kwargs["cwd"]).resolve()
        if argv_s[0] == "git":
            if argv_s[1:4] == ("ls-tree", "-r", "-z"):
                events.append(("ls-tree", str(cwd)))
            else:
                events.append(("git", argv_s[1], str(cwd)))
            return _default_packet_runner(argv, **kwargs)
        child_macro = Path(argv_s[argv_s.index("--macro-root") + 1]).resolve()
        events.append(("child", str(child_macro)))
        return {
            "code": 0,
            "stdout": json.dumps({
                "schema": "mastermind.ceo_boot_packet.v1",
                "mastermind": {"root": str(repo), "sha": source_sha, "branch": "HEAD"},
                "macro": {
                    "root": str(child_macro), "sha": macro_sha,
                    "resolved_via": "flag", "candidates_tried": [],
                },
            }),
            "stderr": "", "timed_out": False,
            "limit_exceeded": False, "invalid_utf8": False,
        }

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha=source_sha,
    )
    packet = collector(
        repo_root=repo, macro_root_flag=str(macro), now=None, timeout=8.0,
    )

    child_indexes = [index for index, event in enumerate(events) if event[0] == "child"]
    assert len(child_indexes) == 1
    child_index = child_indexes[0]
    child_root = events[child_index][1]
    live_ls_tree = [
        index for index, event in enumerate(events)
        if event[0] == "ls-tree" and event[1] == str(live_macro)
    ]
    materialized_ls_tree = [
        index for index, event in enumerate(events)
        if event[0] == "ls-tree" and event[1] not in {str(live_macro), str(live_source)}
    ]
    pre_child_materialized = [
        event for index, event in enumerate(events)
        if index < child_index and event[-1] == child_root
    ]

    assert len(live_ls_tree) == 1, live_ls_tree
    assert live_ls_tree[0] < child_index
    assert materialized_ls_tree == []
    assert pre_child_materialized
    assert child_root != str(live_macro)
    assert Path(child_root).exists() is False
    assert packet["mastermind"]["sha"] == source_sha
    assert packet["macro"]["sha"] == macro_sha
    assert packet["macro"]["root"] == str(macro)


def test_installed_collector_refuses_after_cleanup_exhausts_budget(tmp_path, monkeypatch):
    """A completed cleanup cannot turn an expired collection into success."""
    from integrations.executive_mcp import installed
    from integrations.executive_mcp.schemas import GatewayError

    original_cleanup = installed.tempfile.TemporaryDirectory.cleanup
    original_clock = installed.time.monotonic
    cleaned_roots = []

    def cleanup(directory):
        original_cleanup(directory)
        cleaned_roots.append(Path(directory.name))

    monkeypatch.setattr(installed.tempfile.TemporaryDirectory, "cleanup", cleanup)
    monkeypatch.setattr(
        installed.time,
        "monotonic",
        lambda: original_clock() + (100.0 if cleaned_roots else 0.0),
    )
    with pytest.raises(GatewayError, match="cumulative deadline"):
        test_installed_collector_reuses_single_macro_tree_proof_before_child(tmp_path)

    assert cleaned_roots
    assert all(not root.exists() for root in cleaned_roots)


# ---------------------------------------------------------------------------
# Bounded same-invocation overlap of one snapshot's two full-proof branches
# ---------------------------------------------------------------------------


def _overlappable_repo(tmp_path: Path) -> tuple[Path, str]:
    """A clean real checkout exercising every tracked leaf kind and ancestry."""
    repo = tmp_path / "overlappable"
    repo.mkdir()
    (repo / "deep/nested").mkdir(parents=True)
    (repo / "plain.txt").write_text("first\n", encoding="utf-8")
    (repo / "deep/nested/leaf.txt").write_text("leaf\n", encoding="utf-8")
    executable = repo / "run.sh"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    (repo / "deep/link").symlink_to("nested/leaf.txt")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first")
    (repo / "plain.txt").write_text("second\n", encoding="utf-8")
    _git(repo, "add", "plain.txt")
    _git(repo, "commit", "-q", "-m", "second")
    return repo, _git(repo, "rev-parse", "HEAD").stdout.strip()


def _proof_observations(
    monkeypatch, *, timeout: float = 10.0,
    object_failure: BaseException | None = None,
    inventory_failure: BaseException | None = None,
    on_enter=None,
) -> dict[str, object]:
    """Instrument the two real full-proof branches with an entry rendezvous.

    Each branch records that it was entered and then waits, under a finite
    timeout, for the other branch to have been entered as well, before
    delegating to the real implementation.  Every object and every raw entry is
    therefore still checked exactly once, and a serial implementation cannot
    satisfy the rendezvous: the discriminator is a synchronization fact, not a
    sleep-based speed measurement.
    """
    import threading
    from integrations.executive_mcp import installed

    real_objects = installed._require_git_object_types
    real_inventory = installed._worktree_path_sets
    entered = {"objects": threading.Event(), "inventory": threading.Event()}
    announced = {"objects": False, "inventory": False}
    state: dict[str, object] = {
        "overlaps": [],
        "threads": set(),
        "object_maps": [],
        "inventories": [],
        "entered": set(),
        "settled": set(),
    }

    def _rendezvous(mine: str, theirs: str) -> None:
        state["threads"].add(threading.get_ident())
        # The object proof enters twice (commits, then blobs); only its first
        # entry takes part in the rendezvous.
        if announced[mine]:
            return
        announced[mine] = True
        state["entered"].add(mine)
        if on_enter is not None:
            on_enter(mine)
        entered[mine].set()
        if entered[theirs].wait(timeout=timeout):
            state["overlaps"].append(f"{mine}+{theirs}")

    def object_probe(*args, **kwargs):
        try:
            _rendezvous("objects", "inventory")
            if object_failure is not None:
                raise object_failure
            mapping = args[1] if len(args) > 1 else kwargs["expected_types"]
            state["object_maps"].append(dict(mapping))
            return real_objects(*args, **kwargs)
        finally:
            state["settled"].add("objects")

    def inventory_probe(*args, **kwargs):
        try:
            _rendezvous("inventory", "objects")
            if inventory_failure is not None:
                raise inventory_failure
            observed = real_inventory(*args, **kwargs)
            state["inventories"].append(observed)
            return observed
        finally:
            state["settled"].add("inventory")

    monkeypatch.setattr(installed, "_require_git_object_types", object_probe)
    monkeypatch.setattr(installed, "_worktree_path_sets", inventory_probe)
    return state


def _tracked_leaf_paths(repo: Path, head: str) -> set[str]:
    return {
        record.partition("\t")[2]
        for record in _git(
            repo, "ls-tree", "-r", "-z", "--full-tree", head,
        ).stdout.split("\0")
        if record
    }


def test_clean_snapshot_overlaps_full_object_closure_with_full_inventory(
    tmp_path: Path, monkeypatch,
):
    """Real object proof and complete raw inventory overlap inside one call."""
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )

    repo, head = _overlappable_repo(tmp_path)
    state = _proof_observations(monkeypatch)
    env = _installed_child_env(code_root=repo, macro_root=repo)
    captures: list = []
    observed = _clean_git_snapshot(
        repo, runner=_default_packet_runner, env=env, label="Mastermind source",
        include_seal=True, snapshot_capture=captures,
    )

    assert observed[0] == head
    assert sorted(state["overlaps"]) == ["inventory+objects", "objects+inventory"]
    assert len(state["threads"]) == 2

    # Both branches stay complete: every expected object exactly once ...
    expected_commits = set(_git(repo, "rev-list", "--parents", head).stdout.split())
    expected_blobs = {
        record.partition("\t")[0].split()[2]
        for record in _git(
            repo, "ls-tree", "-r", "-z", "--full-tree", head,
        ).stdout.split("\0")
        if record
    }
    object_maps = state["object_maps"]
    assert len(object_maps) == 2
    checked = [object_id for mapping in object_maps for object_id in mapping]
    assert len(checked) == len(set(checked))
    assert set(checked) == expected_commits | expected_blobs
    assert object_maps[1] == {object_id: "blob" for object_id in expected_blobs}
    assert set(object_maps[0]) == expected_commits

    # ... and one full raw inventory, with no leaf or directory dropped.
    inventories = state["inventories"]
    assert len(inventories) == 1
    leaves, directories, _worktree_seal = inventories[0]
    tracked = _tracked_leaf_paths(repo, head)
    assert set(leaves) == tracked
    assert leaves["deep/link"] == "symlink"
    assert leaves["run.sh"] == "regular"
    assert leaves["plain.txt"] == "regular"
    assert directories == {"deep", "deep/nested"}
    assert len(captures) == 1


def test_clean_snapshot_overlap_preserves_exact_head_and_generation_seal(
    tmp_path: Path, monkeypatch,
):
    """The overlapped proof binds the exact HEAD and seal a direct read binds."""
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _direct_git_directory,
        _git_generation_seal,
        _installed_child_env,
    )

    repo, head = _overlappable_repo(tmp_path)
    state = _proof_observations(monkeypatch)
    env = _installed_child_env(code_root=repo, macro_root=repo)
    captures: list = []
    observed = _clean_git_snapshot(
        repo, runner=_default_packet_runner, env=env, label="Mastermind source",
        include_seal=True, snapshot_capture=captures,
    )

    _leaves, _directories, worktree_seal = state["inventories"][0]
    assert observed == (head, _git_generation_seal(
        _direct_git_directory(repo, label="Mastermind source"),
        worktree_seal=worktree_seal, deadline=None, label="Mastermind source",
    ))
    assert len(captures) == 1
    assert captures[0].root == repo.resolve()
    assert captures[0].head == head
    assert captures[0].worktree_seal == worktree_seal
    assert captures[0].generation_seal == observed[1]


def test_clean_snapshot_overlap_still_refuses_untracked_ignored_and_empty(
    tmp_path: Path, monkeypatch,
):
    """Raw inventory completeness survives the overlap; drift is still refused."""
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _head = _overlappable_repo(tmp_path)
    (repo / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (repo / "empty").mkdir()
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-q", "-m", "ignore")
    ignored = repo / "ignored"
    ignored.mkdir()
    (ignored / "payload.txt").write_text("ignored\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    state = _proof_observations(monkeypatch)
    env = _installed_child_env(code_root=repo, macro_root=repo)
    captures: list = []
    with pytest.raises(GatewayError, match="worktree path set differs"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env, label="Mastermind source",
            include_seal=True, snapshot_capture=captures,
        )

    assert len(state["inventories"]) == 1
    leaves, directories, _worktree_seal = state["inventories"][0]
    assert leaves["untracked.txt"] == "regular"
    assert leaves["ignored/payload.txt"] == "regular"
    assert "empty" in directories
    assert captures == []


def test_clean_snapshot_object_closure_failure_blocks_inventory_use(
    tmp_path: Path, monkeypatch,
):
    """An object-proof failure is typed and leaves no captured snapshot."""
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _head = _overlappable_repo(tmp_path)
    refusal = GatewayError(
        "backend_unavailable",
        "installed Mastermind source repository objects are incomplete",
    )
    state = _proof_observations(monkeypatch, object_failure=refusal)
    env = _installed_child_env(code_root=repo, macro_root=repo)
    captures: list = []
    with pytest.raises(GatewayError, match="repository objects are incomplete"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env, label="Mastermind source",
            include_seal=True, snapshot_capture=captures,
        )

    # The concurrent inventory still reached a terminal state before the refusal.
    assert "inventory" in state["settled"]
    assert len(state["inventories"]) == 1
    assert state["object_maps"] == []
    assert captures == []


def test_clean_snapshot_inventory_failure_blocks_object_use(
    tmp_path: Path, monkeypatch,
):
    """An inventory failure keeps its canonical wrapping and blocks the proof."""
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    repo, _head = _overlappable_repo(tmp_path)
    state = _proof_observations(
        monkeypatch, inventory_failure=NotADirectoryError(21, "root replaced"),
    )
    env = _installed_child_env(code_root=repo, macro_root=repo)
    captures: list = []
    with pytest.raises(GatewayError, match="worktree observation failed"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env, label="Mastermind source",
            include_seal=True, snapshot_capture=captures,
        )

    # The concurrent object proof still settled before the refusal surfaced.
    assert len(state["object_maps"]) == 2
    assert state["inventories"] == []
    assert captures == []


def test_clean_snapshot_overlap_cannot_resurrect_expired_deadline(
    tmp_path: Path, monkeypatch,
):
    """Exhaustion reached inside the proof pair stays typed and never succeeds.

    The canonical outcome is the object-proof refusal: the deadline check feeds
    the bounded runner timeout, so the object proof converts it exactly as it
    does for any other bounded-runner failure.
    """
    from integrations.executive_mcp import installed
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )

    repo, _head = _overlappable_repo(tmp_path)
    real_monotonic = installed.time.monotonic
    clock = {"value": real_monotonic()}

    def exhaust_budget(branch: str) -> None:
        # The cumulative deadline runs out exactly when the proof pair runs, so
        # the branch-level check is what refuses.
        if branch == "objects":
            clock["value"] += 3600.0

    def fake_monotonic() -> float:
        return clock["value"]

    monkeypatch.setattr(installed.time, "monotonic", fake_monotonic)
    state = _proof_observations(monkeypatch, on_enter=exhaust_budget)
    env = _installed_child_env(code_root=repo, macro_root=repo)
    captures: list = []
    deadline = fake_monotonic() + 60.0
    from integrations.executive_mcp.schemas import GatewayError

    with pytest.raises(GatewayError, match="repository objects are incomplete"):
        _clean_git_snapshot(
            repo, runner=_default_packet_runner, env=env, label="Mastermind source",
            include_seal=True, snapshot_capture=captures, deadline=deadline,
        )

    # The deadline that ran out is still the deadline that ran out, the blob
    # proof never completed, and no snapshot survived the exhausted budget.
    assert deadline < installed.time.monotonic()
    assert not any(
        set(mapping.values()) == {"blob"} for mapping in state["object_maps"]
    )
    assert captures == []
    assert state["inventories"] == []


def test_installed_collector_refuses_without_child_when_proof_branch_fails(
    tmp_path: Path, monkeypatch,
):
    """A failed proof branch stops the collector before any child launch."""
    import json
    from integrations.executive_mcp import installed
    from integrations.executive_mcp.installed import InstalledBootPacketCollector
    from integrations.executive_mcp.schemas import GatewayError

    collector, source, macro, source_sha, macro_sha = _direct_pair_collector(tmp_path)
    child_seen = False

    def runner(argv, **kwargs):
        nonlocal child_seen
        if str(argv[0]) != "git":
            child_seen = True
            return {
                "code": 0,
                "stdout": json.dumps({
                    "schema": "mastermind.ceo_boot_packet.v1",
                    "mastermind": {"root": str(source), "sha": source_sha,
                                   "branch": "HEAD"},
                    "macro": {"root": str(macro), "sha": macro_sha,
                              "resolved_via": "flag", "candidates_tried": []},
                }),
                "stderr": "", "timed_out": False,
                "limit_exceeded": False, "invalid_utf8": False,
            }
        return installed._default_packet_runner(argv, **kwargs)

    refusal = GatewayError(
        "backend_unavailable", "installed forced proof-branch refusal",
    )

    def object_probe(*_args, **_kwargs):
        raise refusal

    monkeypatch.setattr(installed, "_require_git_object_types", object_probe)
    collector = InstalledBootPacketCollector(
        source_root=source, macro_root=macro,
        code_root=tmp_path / "immutable-release",
        python_executable=tmp_path / "python", runner=runner,
        expected_source_sha=source_sha,
    )
    with pytest.raises(GatewayError, match="forced proof-branch refusal"):
        collector(
            repo_root=source, macro_root_flag=str(macro), now=None, timeout=20.0,
        )
    assert child_seen is False


def test_installed_collector_refuses_live_macro_mutation_made_during_child(
    tmp_path: Path,
):
    """A real byte mutation during the child fails the final generation check."""
    import json
    from integrations.executive_mcp.installed import (
        InstalledBootPacketCollector,
        _default_packet_runner,
    )
    from integrations.executive_mcp.schemas import GatewayError

    source_parent = tmp_path / "source-parent"
    source_parent.mkdir()
    repo, _tracked = _clean_repo(source_parent)
    macro, macro_sha = _macro_sparse_fixture(tmp_path)
    code = tmp_path / "immutable-release"
    (code / "scripts").mkdir(parents=True)
    python = tmp_path / "python"
    python.write_text("fixture", encoding="utf-8")
    source_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    consumed = macro / "agentos/workstreams/WS-SPARSE.md"
    materialized_roots: list[Path] = []
    child_seen = False

    def runner(argv, **kwargs):
        nonlocal child_seen
        argv_s = tuple(str(item) for item in argv)
        if argv_s[0] != "git":
            child_seen = True
            materialized_roots.append(Path(argv_s[argv_s.index("--macro-root") + 1]))
            # Real filesystem mutation of live Macro consumed bytes while the
            # child is the only thing still running.
            consumed.write_text(
                consumed.read_text(encoding="utf-8") + "mutated\n",
                encoding="utf-8",
            )
            return {
                "code": 0,
                "stdout": json.dumps({
                    "schema": "mastermind.ceo_boot_packet.v1",
                    "mastermind": {"root": str(repo), "sha": source_sha,
                                   "branch": "HEAD"},
                    "macro": {"root": str(materialized_roots[0]), "sha": macro_sha,
                              "resolved_via": "flag", "candidates_tried": []},
                }),
                "stderr": "", "timed_out": False,
                "limit_exceeded": False, "invalid_utf8": False,
            }
        return _default_packet_runner(argv, **kwargs)

    collector = InstalledBootPacketCollector(
        source_root=repo, macro_root=macro, code_root=code,
        python_executable=python, runner=runner, expected_source_sha=source_sha,
    )
    with pytest.raises(GatewayError, match="source changed during boot-packet read"):
        collector(
            repo_root=repo, macro_root_flag=str(macro), now=None, timeout=20.0,
        )

    assert child_seen is True
    assert len(materialized_roots) == 1
    assert materialized_roots[0] != macro
    assert not materialized_roots[0].exists()
    assert consumed.read_text(encoding="utf-8").endswith("mutated\n")


def test_macro_snapshot_capture_scopes_live_inventory_to_child_visible_paths(
    tmp_path: Path,
):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )

    macro, head = _macro_sparse_fixture(tmp_path)
    unrelated = macro / "unrelated/runtime-only.tmp"
    unrelated.write_text("not child visible\n", encoding="utf-8")
    env = _installed_child_env(code_root=macro, macro_root=macro)
    captures = []

    observed = _clean_git_snapshot(
        macro,
        runner=_default_packet_runner,
        env=env,
        label="Macro source",
        content_scope="macro_brief",
        include_seal=True,
        snapshot_capture=captures,
    )

    assert observed[0] == head
    assert len(captures) == 1
    assert captures[0].sealed_to_caller is True


def test_macro_snapshot_capture_still_refuses_untracked_record_namespace(
    tmp_path: Path,
):
    from integrations.executive_mcp.installed import (
        _clean_git_snapshot,
        _default_packet_runner,
        _installed_child_env,
    )
    from integrations.executive_mcp.schemas import GatewayError

    macro, _head = _macro_sparse_fixture(tmp_path)
    shadow = macro / "agentos/workstreams/SHADOW.md"
    shadow.write_text("---\nkey: SHADOW\n---\n", encoding="utf-8")
    env = _installed_child_env(code_root=macro, macro_root=macro)

    with pytest.raises(GatewayError, match="worktree observation failed"):
        _clean_git_snapshot(
            macro,
            runner=_default_packet_runner,
            env=env,
            label="Macro source",
            content_scope="macro_brief",
            include_seal=True,
            snapshot_capture=[],
        )


def test_object_type_probe_shards_large_complete_sets_without_weakening():
    from pathlib import Path
    from integrations.executive_mcp.installed import _require_git_object_types

    expected = {f"{index:040x}": "blob" for index in range(48_001)}
    calls: list[tuple[str, ...]] = []

    def runner(argv, **kwargs):
        object_ids = tuple(
            line for line in kwargs["input_bytes"].decode("ascii").splitlines() if line
        )
        calls.append(object_ids)
        return {
            "code": 0,
            "stdout": "".join(f"{object_id} blob\n" for object_id in object_ids),
            "stderr": "",
            "timed_out": False,
            "limit_exceeded": False,
            "invalid_utf8": False,
        }

    _require_git_object_types(
        Path("/tmp/unused"),
        expected,
        runner=runner,
        env={},
        deadline=None,
        label="Macro source",
    )

    assert len(calls) == 2
    assert {object_id for call in calls for object_id in call} == set(expected)
    assert sum(len(call) for call in calls) == len(expected)

def test_scoped_macro_seal_refuses_symlink_parent_before_descendant(
    tmp_path: Path, monkeypatch,
):
    """A substituted directory symlink is rejected before any child lookup."""
    from integrations.executive_mcp.installed import _scoped_worktree_path_sets

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "leaf.txt").write_text("outside\n", encoding="utf-8")
    (root / "scope").symlink_to(outside, target_is_directory=True)

    descendant = root / "scope" / "leaf.txt"
    real_lstat = Path.lstat
    observed: list[Path] = []

    def guarded_lstat(path: Path):
        observed.append(path)
        if path == descendant:
            raise AssertionError("scoped seal followed a substituted directory symlink")
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", guarded_lstat)
    with pytest.raises(OSError, match="directory topology differs"):
        _scoped_worktree_path_sets(
            root,
            files={"scope/leaf.txt"},
            directories={"scope"},
            deadline=None,
            label="Macro source",
        )

    assert descendant not in observed
