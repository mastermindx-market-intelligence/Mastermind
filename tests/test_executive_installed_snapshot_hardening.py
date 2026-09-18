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
    macro_git_calls = 0
    helper_called = False

    def runner(argv, **kwargs):
        nonlocal macro_git_calls, helper_called
        if str(argv[0]) == "git":
            result = _default_packet_runner(argv, **kwargs)
            if Path(kwargs["cwd"]) == macro:
                macro_git_calls += 1
                # A real production snapshot currently issues exactly five
                # bounded Git observations. Remove metadata only after the
                # complete pre-snapshot has already been observed.
                if macro_git_calls == 5:
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
    assert macro_git_calls == 5
    assert helper_called is False
