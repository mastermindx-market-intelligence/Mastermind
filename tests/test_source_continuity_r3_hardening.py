from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "source_continuity.py"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
TOKEN = "token"
HEAD, TREE, BASE, MERGE_BASE, BLOB = (c * 40 for c in "abcde")
BRANCH = "sol/source-continuity-r3-rename-git-env-hardening-20260903"
OWNED = ("scripts/source_continuity.py", "tests/test_source_continuity_r3_hardening.py")


def _module():
    name = "source_continuity_r3_adapter_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FilesHTTP:
    def __init__(self, files: list[object]) -> None:
        self.files = files

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        assert url.endswith("/files?per_page=100&page=1")
        return self.files


def changed_paths(module: Any, files: list[object]) -> tuple[str, ...]:
    paths, complete = module._changed_paths(FilesHTTP(files), TOKEN, REPOSITORY, 448)
    assert complete is True
    return paths


def test_closed_file_reducer_emits_old_then_new_for_rename() -> None:
    module = _module()
    assert changed_paths(
        module,
        [{"filename": OWNED[1], "status": "renamed", "previous_filename": "tests/old.py"}],
    ) == ("tests/old.py", OWNED[1])


@pytest.mark.parametrize(
    "row",
    [
        {"filename": "a.py", "status": "renamed"},
        {"filename": "a.py", "status": "renamed", "previous_filename": ""},
        {"filename": "a.py", "status": "renamed", "previous_filename": "a.py"},
        {"filename": "a.py", "status": "renamed", "previous_filename": 7},
        {"filename": "a.py", "status": "unknown"},
        {"filename": "a.py", "status": "modified", "previous_filename": "b.py"},
        {"filename": "../a.py", "status": "modified"},
        {"filename": "bad\ud800.py", "status": "modified"},
    ],
)
def test_closed_file_reducer_rejects_malformed_or_open_world_rows(row: object) -> None:
    module = _module()
    with pytest.raises(module._RemoteProbeError):
        changed_paths(module, [row])


def test_closed_file_reducer_rejects_duplicate_effective_paths() -> None:
    module = _module()
    with pytest.raises(module._RemoteProbeError):
        changed_paths(
            module,
            [
                {"filename": "a.py", "status": "modified"},
                {"filename": "b.py", "status": "renamed", "previous_filename": "a.py"},
            ],
        )


def test_closed_file_reducer_rejects_statusless_row() -> None:
    module = _module()
    with pytest.raises(module._RemoteProbeError):
        changed_paths(module, [{"filename": "a.py"}])


class CollisionHTTP:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        if url.endswith("/pulls?state=open&per_page=100&page=1"):
            return [{"number": 448}, {"number": 999}]
        if url.endswith("/pulls/999/files?per_page=100&page=1"):
            return [self.row]
        raise AssertionError(url)


@pytest.mark.parametrize(
    "row",
    [
        {"filename": "outside.py", "status": "renamed", "previous_filename": OWNED[0]},
        {"filename": OWNED[0], "status": "renamed", "previous_filename": "outside.py"},
    ],
)
def test_collision_census_catches_rename_on_either_side(row: dict[str, object]) -> None:
    module = _module()
    state, numbers, complete, snapshot = module._collision_census(
        CollisionHTTP(row), TOKEN, REPOSITORY, 448, (OWNED[0],)
    )
    assert (state, numbers, complete) == (module.CollisionState.OVERLAP, (999,), True)
    assert snapshot == ((448, ()), (999, tuple(row[key] for key in ("previous_filename", "filename"))))


class CollisionRowsHTTP:
    def __init__(self, rows: dict[int, list[dict[str, object]]]) -> None:
        self.rows = rows

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        if url.endswith("/pulls?state=open&per_page=100&page=1"):
            return [{"number": 448}, *({"number": number} for number in self.rows)]
        for number, rows in self.rows.items():
            if url.endswith(f"/pulls/{number}/files?per_page=100&page=1"):
                return rows
        raise AssertionError(url)


def test_collision_census_retains_complete_normalized_open_pr_and_path_evidence() -> None:
    module = _module()
    state, numbers, complete, snapshot = module._collision_census(
        CollisionRowsHTTP(
            {
                999: [{"filename": OWNED[0], "status": "modified"}],
                1000: [{"filename": "docs/unrelated.md", "status": "modified"}],
            }
        ),
        TOKEN,
        REPOSITORY,
        448,
        OWNED,
    )
    assert (state, numbers, complete) == (module.CollisionState.OVERLAP, (999,), True)
    assert snapshot == (
        (448, ()),
        (999, (OWNED[0],)),
        (1000, ("docs/unrelated.md",)),
    )


def request(module: Any):
    return module.SourceContinuityRequest(
        receipt_kind=module.ReceiptKind.CHECKPOINT_VERIFIED,
        operation_key="source-continuity-r3-rename-git-env-hardening-20260903-sol-001",
        repository=REPOSITORY,
        pr_number=448,
        branch=BRANCH,
        base_ref="master",
        pinned_base_sha=BASE,
        owned_paths=OWNED,
        verified_at="2026-09-04T04:00:00Z",
    )


def pr_payload() -> dict[str, object]:
    return {
        "state": "open",
        "draft": True,
        "labels": [],
        "head": {"ref": BRANCH, "sha": HEAD, "repo": {"full_name": REPOSITORY}},
        "base": {"ref": "master"},
    }


class PrefixHTTP:
    def __init__(self, files: list[object]) -> None:
        self.files = files

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        if url.endswith("/pulls/448"):
            return pr_payload()
        if url.endswith(f"/branches/{BRANCH.replace('/', '%2F')}"):
            return {"commit": {"sha": HEAD}}
        if url.endswith(f"/git/commits/{HEAD}"):
            return {"tree": {"sha": TREE}}
        if url.endswith("/branches/master"):
            return {"commit": {"sha": BASE}}
        if url.endswith(f"/compare/{BASE}...{HEAD}"):
            return {"merge_base_commit": {"sha": MERGE_BASE}}
        if url.endswith("/pulls/448/files?per_page=100&page=1"):
            return self.files
        if url.endswith("/pulls?state=open&per_page=100&page=1"):
            return [{"number": 448}]
        raise AssertionError(url)


class ForbiddenRunner:
    def __init__(self) -> None:
        self.called = False

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self.called = True
        raise AssertionError("local Git must not run")


def main_args() -> list[str]:
    args = [
        "verify", "--kind", "checkpoint", "--operation-key",
        "source-continuity-r3-rename-git-env-hardening-20260903-sol-001",
        "--workspace", "/repo", "--repository", REPOSITORY, "--pr-number", "448",
        "--branch", BRANCH, "--base-ref", "master", "--pinned-base-sha", BASE,
    ]
    for path in OWNED:
        args += ["--owned-path", path]
    return args + [
        "--external-effect-state", "NONE", "--branch-effect-dependency", "NONE",
        "--external-effect-evidence-fingerprint", "f" * 64,
    ]


def test_cli_target_rename_outside_to_owned_refuses_before_local_git(capsys) -> None:
    module, runner = _module(), ForbiddenRunner()
    code = module.main(
        main_args(), runner=runner,
        http_get=PrefixHTTP([
            {"filename": OWNED[0], "status": "renamed", "previous_filename": "outside.py"}
        ]),
        environ={"GITHUB_TOKEN": TOKEN}, clock=lambda: "2026-09-04T04:00:00Z",
    )
    output = capsys.readouterr().out
    assert code == 1 and runner.called is False
    assert "PATH_OUTSIDE_OWNERSHIP" in output and "outside.py" not in output


def test_cli_malformed_rename_is_fixed_non_echo_refusal(capsys) -> None:
    module, runner = _module(), ForbiddenRunner()
    secret = "secret-path"
    code = module.main(
        main_args(), runner=runner,
        http_get=PrefixHTTP([
            {"filename": OWNED[0], "status": "renamed", "previous_filename": secret + "\ud800"}
        ]),
        environ={"GITHUB_TOKEN": TOKEN}, clock=lambda: "2026-09-04T04:00:00Z",
    )
    output = capsys.readouterr().out
    assert code == 2 and runner.called is False
    assert "REMOTE_PROBE_FAILED" in output
    assert secret not in output and TOKEN not in output


class FenceHTTP:
    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        if url.endswith("/pulls/448"):
            return pr_payload()
        if url.endswith(f"/branches/{BRANCH.replace('/', '%2F')}"):
            return {"commit": {"sha": HEAD}}
        if url.endswith("/branches/master"):
            return {"commit": {"sha": BASE}}
        if url.endswith("/pulls?state=open&per_page=100&page=1"):
            return [{"number": 448}]
        raise AssertionError(url)


@pytest.mark.parametrize(
    ("second_paths", "complete", "expected"),
    [
        ((OWNED[0], "tests/changed.py"), True, "REMOTE_PROOF_CHANGED"),
        (OWNED, False, "REMOTE_CENSUS_INCOMPLETE"),
        (OWNED, True, None),
    ],
)
def test_final_fence_rechecks_target_file_census(monkeypatch, second_paths, complete, expected) -> None:
    module = _module()
    calls = 0

    def reread(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return second_paths, complete

    monkeypatch.setattr(module, "_changed_paths", reread)
    result = module._remote_still_matches(
        FenceHTTP(), TOKEN, request(module), module._pr_identity(pr_payload()),
        HEAD, BASE, OWNED, True, module.CollisionState.NONE, (), True, ((448, ()),),
    )
    assert calls == 1
    if expected is None:
        assert result is None
    else:
        assert result is not None and result.code.value == expected


class CollisionDriftFenceHTTP(FenceHTTP):
    def __init__(self, rows: dict[int, str]) -> None:
        self.rows = rows

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN and timeout > 0
        if url.endswith("/pulls/448/files?per_page=100&page=1"):
            return [{"filename": path, "status": "modified"} for path in OWNED]
        if url.endswith("/pulls?state=open&per_page=100&page=1"):
            return [{"number": 448}, *({"number": number} for number in self.rows)]
        for number, path in self.rows.items():
            if url.endswith(f"/pulls/{number}/files?per_page=100&page=1"):
                return [{"filename": path, "status": "modified"}]
        return super().__call__(url, token=token, timeout=timeout)


@pytest.mark.parametrize(
    ("first_snapshot", "second_rows"),
    [
        (
            ((448, ()), (999, (OWNED[0],))),
            {999: OWNED[1]},
        ),
        (
            ((448, ()), (999, (OWNED[0],)), (1000, ("docs/a.md",))),
            {999: OWNED[0], 1001: "docs/a.md"},
        ),
    ],
)
def test_final_fence_rejects_same_summary_collision_path_or_open_set_churn(
    first_snapshot: tuple[tuple[int, tuple[str, ...]], ...],
    second_rows: dict[int, str],
) -> None:
    module = _module()
    result = module._remote_still_matches(
        CollisionDriftFenceHTTP(second_rows),
        TOKEN,
        request(module),
        module._pr_identity(pr_payload()),
        HEAD,
        BASE,
        OWNED,
        True,
        module.CollisionState.OVERLAP,
        (999,),
        True,
        first_snapshot,
    )
    assert result is not None and result.code.value == "REMOTE_PROOF_CHANGED"


class CaptureRunner:
    def __init__(self, workspace: str = "/repo") -> None:
        self.workspace = workspace
        self.commands: list[tuple[str, ...]] = []
        self.environments: list[dict[str, str]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> SimpleNamespace:
        full = tuple(command)
        self.commands.append(full)
        self.environments.append(dict(kwargs["env"]))
        tail = git_tail(full)
        outputs = {
            ("rev-parse", "--show-toplevel"): self.workspace + "\n",
            ("symbolic-ref", "--short", "HEAD"): BRANCH + "\n",
            ("rev-parse", "HEAD^{commit}"): HEAD + "\n",
            ("rev-parse", "HEAD^{tree}"): TREE + "\n",
            ("rev-parse", "--git-common-dir"): self.workspace + "/.git\n",
        }
        if tail in outputs:
            return SimpleNamespace(returncode=0, stdout=outputs[tail])
        if tail[:2] in {("cat-file", "-e"), ("merge-base", "--is-ancestor")}:
            return SimpleNamespace(returncode=0, stdout="")
        if tail[:2] == ("rev-list", "--count"):
            return SimpleNamespace(returncode=0, stdout="0\n")
        if tail[0] == "config":
            return SimpleNamespace(returncode=1, stdout="")
        if tail[0] == "diff":
            return SimpleNamespace(
                returncode=0,
                stdout=(OWNED[0] + "\0") if f"{MERGE_BASE}..{HEAD}" in tail else "",
            )
        if tail[0] == "ls-files":
            return SimpleNamespace(returncode=0, stdout="")
        if tail[0] == "ls-tree":
            return SimpleNamespace(returncode=0, stdout=f"100644 blob {BLOB} 12\t{OWNED[0]}\0")
        if tail[0] == "status":
            return SimpleNamespace(returncode=0, stdout="")
        raise AssertionError(full)


def git_tail(command: tuple[str, ...]) -> tuple[str, ...]:
    commands = {"rev-parse", "symbolic-ref", "cat-file", "merge-base", "rev-list", "config", "diff", "ls-files", "ls-tree", "status"}
    return command[next(i for i, value in enumerate(command) if i and value in commands):]


OVERRIDES = (
    "core.fsmonitor=false", "core.untrackedCache=false", "core.hooksPath=/dev/null",
    "core.attributesFile=/dev/null", "core.excludesFile=/dev/null", "diff.external=",
    "diff.renames=false", "core.fileMode=true", "core.ignoreStat=false",
    "core.checkStat=default", "core.trustctime=true", "core.symlinks=true",
    "credential.helper=", "protocol.allow=never",
    "protocol.file.allow=always",
)


def assert_git_prefix(command: tuple[str, ...]) -> None:
    assert command[:3] == ("/usr/bin/git", "--no-pager", "--no-replace-objects")
    command_index = command.index(git_tail(command)[0])
    assert command[command_index - 1] == "--work-tree=."
    prefix = command[: command_index - 1]
    joined = "\0".join(prefix)
    for setting in OVERRIDES:
        assert f"-c\0{setting}" in joined


class AssertionRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def __call__(self, command: list[str], **_kwargs: Any) -> object:
        self.commands.append(tuple(command))
        raise AssertionError("test double rejected the command")


def test_injected_runner_assertion_never_retries_without_the_git_fence() -> None:
    module, runner = _module(), AssertionRunner()
    assert module._invoke_git(runner, "/repo", "rev-parse", "HEAD^{commit}") is None
    assert len(runner.commands) == 1
    assert_git_prefix(runner.commands[0])


def test_all_local_probes_use_closed_argv_and_explicit_diff_controls() -> None:
    module, runner = _module(), CaptureRunner()
    result = module._probe_local_and_entries(
        runner, "/repo", request(module), HEAD, MERGE_BASE, (OWNED[0],)
    )
    assert not isinstance(result, module.SourceContinuityRefusal)
    for command in runner.commands:
        assert_git_prefix(command)
    diffs = [git_tail(c) for c in runner.commands if git_tail(c)[0] == "diff"]
    assert len(diffs) == 3
    for command in diffs:
        for flag in (
            "--no-renames", "--no-ext-diff", "--no-textconv",
            "--ignore-submodules=none", "--name-only", "-z", "--",
        ):
            assert flag in command
    tree = next(git_tail(c) for c in runner.commands if git_tail(c)[0] == "ls-tree")
    assert "--" in tree and tree[-1] == OWNED[0]
    assert all(env["GIT_LITERAL_PATHSPECS"] == "1" for env in runner.environments)


ENV_KEYS = {
    "LANG", "LC_ALL", "TZ", "PATH", "HOME", "GIT_OPTIONAL_LOCKS", "GIT_NO_LAZY_FETCH",
    "GIT_TERMINAL_PROMPT", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL",
    "GIT_ATTR_NOSYSTEM", "GIT_LITERAL_PATHSPECS", "GIT_NO_REPLACE_OBJECTS",
    "GIT_PAGER", "GIT_EDITOR", "GIT_SEQUENCE_EDITOR", "GIT_ASKPASS", "SSH_ASKPASS",
    "GIT_SSH", "GIT_SSH_COMMAND", "GIT_CONFIG_COUNT",
}


def test_git_child_environment_is_exact_and_ignores_hostile_ambient(monkeypatch) -> None:
    hostile = {
        "GITHUB_TOKEN": "secret", "GIT_DIR": "/tmp/dir", "GIT_WORK_TREE": "/tmp/work",
        "GIT_COMMON_DIR": "/tmp/common", "GIT_INDEX_FILE": "/tmp/index",
        "GIT_OBJECT_DIRECTORY": "/tmp/object", "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/alt",
        "GIT_REPLACE_REF_BASE": "refs/hostile/", "GIT_CONFIG_PARAMETERS": "hostile",
        "GIT_CONFIG_SYSTEM": "/tmp/system", "GIT_CONFIG_LOCAL": "/tmp/local",
        "XDG_CONFIG_HOME": "/tmp/xdg", "GIT_EXTERNAL_DIFF": "/tmp/external",
        "PAGER": "/tmp/pager", "EDITOR": "/tmp/editor", "VISUAL": "/tmp/visual",
        "GIT_ASKPASS": "/tmp/askpass", "SSH_ASKPASS": "/tmp/ssh-askpass",
        "GIT_SSH": "/tmp/ssh", "GIT_SSH_COMMAND": "/tmp/ssh-command",
        "GIT_PROXY_COMMAND": "/tmp/proxy", "GIT_ALLOW_PROTOCOL": "https:file:ssh",
        "GIT_PROTOCOL_FROM_USER": "1", "GIT_GLOB_PATHSPECS": "1",
        "GIT_NOGLOB_PATHSPECS": "0", "GIT_ICASE_PATHSPECS": "1",
        "GIT_CEILING_DIRECTORIES": "/tmp", "GIT_DISCOVERY_ACROSS_FILESYSTEM": "1",
        "HTTP_PROXY": "http://proxy.invalid", "HTTPS_PROXY": "http://proxy.invalid",
        "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor",
        "GIT_CONFIG_VALUE_0": "/tmp/helper",
    }
    for key, value in hostile.items():
        monkeypatch.setenv(key, value)
    module, runner = _module(), CaptureRunner()
    assert module._invoke_git(runner, "/repo", "status", "--porcelain") is not None
    env = runner.environments[-1]
    assert set(env) == ENV_KEYS
    assert all(env.get(key) != value for key, value in hostile.items() if key in env)
    assert env == {
        "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "PATH": "/usr/bin:/bin", "HOME": "/",
        "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1", "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_ATTR_NOSYSTEM": "1", "GIT_LITERAL_PATHSPECS": "1",
        "GIT_NO_REPLACE_OBJECTS": "1", "GIT_PAGER": "cat",
        "GIT_EDITOR": "/usr/bin/false", "GIT_SEQUENCE_EDITOR": "/usr/bin/false",
        "GIT_ASKPASS": "/usr/bin/false", "SSH_ASKPASS": "/usr/bin/false",
        "GIT_SSH": "/usr/bin/false", "GIT_SSH_COMMAND": "/usr/bin/false",
        "GIT_CONFIG_COUNT": "0",
    }
    assert_git_prefix(runner.commands[-1])


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", *args], cwd=repo, check=True, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(repo)},
    )
    return result.stdout.strip()


def init_repo(path: Path, value: str) -> str:
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.name", "R3 Test")
    git(path, "config", "user.email", "r3@example.invalid")
    (path / "value.txt").write_text(value, encoding="utf-8")
    git(path, "add", "value.txt")
    git(path, "commit", "-q", "-m", value)
    return git(path, "rev-parse", "HEAD^{commit}")


def repo_request(module: Any, repo: Path, head: str):
    return module.SourceContinuityRequest(
        receipt_kind=module.ReceiptKind.CHECKPOINT_VERIFIED,
        operation_key="source-continuity-r3-local-index-hardening-20260904-sol-001",
        repository=REPOSITORY,
        pr_number=448,
        branch=git(repo, "symbolic-ref", "--short", "HEAD"),
        base_ref="master",
        pinned_base_sha=head,
        owned_paths=("value.txt",),
        verified_at="2026-09-04T04:00:00Z",
    )


def request_with_owned_paths(module: Any, repo: Path, head: str, *paths: str):
    return module.SourceContinuityRequest(
        receipt_kind=module.ReceiptKind.CHECKPOINT_VERIFIED,
        operation_key="source-continuity-r3-local-path-hardening-20260904-sol-001",
        repository=REPOSITORY,
        pr_number=448,
        branch=git(repo, "symbolic-ref", "--short", "HEAD"),
        base_ref="master",
        pinned_base_sha=head,
        owned_paths=paths,
        verified_at="2026-09-04T04:00:00Z",
    )


def git_common_dir(repo: Path) -> Path:
    raw = Path(git(repo, "rev-parse", "--git-common-dir"))
    return raw if raw.is_absolute() else repo / raw


@pytest.mark.parametrize(
    ("exclude_source", "owned", "expected_field"),
    [
        ("gitignore", True, "untracked_in_scope_count"),
        ("common-info-exclude", False, "untracked_out_of_scope_count"),
    ],
)
def test_real_probe_counts_ignored_untracked_paths(
    tmp_path,
    exclude_source: str,
    owned: bool,
    expected_field: str,
) -> None:
    repo = tmp_path / exclude_source
    head = init_repo(repo, "base")
    if exclude_source == "gitignore":
        (repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        git(repo, "add", ".gitignore")
        git(repo, "commit", "-q", "-m", "ignore path")
        head = git(repo, "rev-parse", "HEAD^{commit}")
    else:
        (git_common_dir(repo) / "info" / "exclude").write_text(
            "ignored.txt\n", encoding="utf-8"
        )
    (repo / "ignored.txt").write_text("untracked", encoding="utf-8")
    module = _module()
    paths = ("ignored.txt",) if owned else ("value.txt",)
    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        request_with_owned_paths(module, repo, head, *paths),
        head,
        head,
        (),
    )
    assert not isinstance(result, module.SourceContinuityRefusal)
    local_facts, _ = result
    assert getattr(local_facts, expected_field) == 1


def unrelated_commit(repo: Path, message: str) -> str:
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    return git(repo, "commit-tree", tree, "-m", message)


def test_real_probe_refuses_nonempty_graft_before_ancestry_is_trusted(tmp_path) -> None:
    repo = tmp_path / "grafted-history"
    local_head = init_repo(repo, "local")
    remote_head = unrelated_commit(repo, "unrelated remote")
    grafts = git_common_dir(repo) / "info" / "grafts"
    grafts.write_text(f"{local_head} {remote_head}\n", encoding="ascii")
    assert git(repo, "merge-base", "--is-ancestor", remote_head, local_head) == ""

    module = _module()
    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        repo_request(module, repo, remote_head),
        remote_head,
        remote_head,
        (),
    )
    assert isinstance(result, module.SourceContinuityRefusal)
    assert result.code.value == "LOCAL_PROBE_FAILED"


@pytest.mark.parametrize("unsafe_kind", ["symlink", "directory"])
def test_real_probe_refuses_special_grafts_path(tmp_path, unsafe_kind: str) -> None:
    repo = tmp_path / f"grafts-{unsafe_kind}"
    head = init_repo(repo, "base")
    grafts = git_common_dir(repo) / "info" / "grafts"
    if unsafe_kind == "symlink":
        target = tmp_path / "empty-grafts-target"
        target.write_text("", encoding="ascii")
        grafts.symlink_to(target)
    else:
        grafts.mkdir()

    module = _module()
    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        repo_request(module, repo, head),
        head,
        head,
        (),
    )
    assert isinstance(result, module.SourceContinuityRefusal)
    assert result.code.value == "LOCAL_PROBE_FAILED"


class GraftAfterTreeRunner:
    def __init__(self, grafts: Path) -> None:
        self.grafts = grafts

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(command, **kwargs)
        if git_tail(tuple(command))[0] == "ls-tree":
            self.grafts.write_text("f" * 40 + " " + "e" * 40 + "\n", encoding="ascii")
        return completed


def test_real_probe_rechecks_graft_state_at_final_local_fence(tmp_path) -> None:
    repo = tmp_path / "graft-toctou"
    head = init_repo(repo, "base")
    grafts = git_common_dir(repo) / "info" / "grafts"
    module = _module()
    result = module._probe_local_and_entries(
        GraftAfterTreeRunner(grafts),
        str(repo),
        repo_request(module, repo, head),
        head,
        head,
        (),
    )
    assert isinstance(result, module.SourceContinuityRefusal)
    assert result.code.value == "LOCAL_PROBE_FAILED"


def test_real_probe_observes_mode_change_despite_local_core_filemode_false(tmp_path) -> None:
    repo = tmp_path / "filemode"
    head = init_repo(repo, "base")
    git(repo, "config", "core.fileMode", "false")
    (repo / "value.txt").chmod(0o755)
    module = _module()
    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        repo_request(module, repo, head),
        head,
        head,
        (),
    )
    assert not isinstance(result, module.SourceContinuityRefusal)
    local_facts, _ = result
    assert local_facts.uncommitted_in_scope_count == 1


def test_real_probe_observes_same_size_timestamp_restored_byte_drift(
    tmp_path,
) -> None:
    repo = tmp_path / "hostile-stat-cache"
    head = init_repo(repo, "base")
    git(repo, "config", "core.checkStat", "minimal")
    git(repo, "config", "core.trustctime", "false")
    path = repo / "value.txt"
    original = path.stat()
    path.write_text("drft", encoding="utf-8")
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    changed = path.stat()
    assert changed.st_size == original.st_size
    assert changed.st_mtime_ns == original.st_mtime_ns
    assert changed.st_ctime_ns != original.st_ctime_ns

    module = _module()
    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        repo_request(module, repo, head),
        head,
        head,
        (),
    )
    assert not isinstance(result, module.SourceContinuityRefusal)
    local_facts, _ = result
    assert local_facts.uncommitted_in_scope_count == 1


@pytest.mark.parametrize("index_flag", ["--assume-unchanged", "--skip-worktree"])
def test_real_probe_refuses_index_flags_that_conceal_owned_byte_drift(
    tmp_path,
    index_flag: str,
) -> None:
    repo = tmp_path / index_flag.removeprefix("--")
    head = init_repo(repo, "base")
    git(repo, "update-index", index_flag, "value.txt")
    (repo / "value.txt").write_text("concealed", encoding="utf-8")
    module = _module()
    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        repo_request(module, repo, head),
        head,
        head,
        (),
    )
    assert isinstance(result, module.SourceContinuityRefusal)
    assert result.code.value == "LOCAL_PROBE_FAILED"


def test_real_probe_ignores_ambient_repo_selectors(tmp_path, monkeypatch) -> None:
    primary, foreign = tmp_path / "primary", tmp_path / "foreign"
    primary_head, foreign_head = init_repo(primary, "primary"), init_repo(foreign, "foreign")
    assert primary_head != foreign_head
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(foreign))
    result = _module()._invoke_git(subprocess.run, str(primary), "rev-parse", "HEAD^{commit}")
    assert result is not None and result.returncode == 0 and result.stdout.strip() == primary_head


def test_real_git_child_binds_cwd_despite_local_core_worktree(tmp_path) -> None:
    repo = tmp_path / "primary-worktree"
    init_repo(repo, "HEAD")
    foreign = tmp_path / "foreign-worktree"
    foreign.mkdir()
    (foreign / "value.txt").write_text("HEAD", encoding="utf-8")
    git(repo, "config", "core.worktree", str(foreign))
    (repo / "value.txt").write_text("DIRTY", encoding="utf-8")

    result = _module()._invoke_git(
        subprocess.run,
        str(repo),
        "diff",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
        "--name-only",
        "-z",
        "HEAD",
        "--",
    )
    assert result is not None and result.returncode == 0
    assert result.stdout == "value.txt\0"


def test_real_git_child_worktree_binding_preserves_linked_worktrees(tmp_path) -> None:
    primary = tmp_path / "primary"
    init_repo(primary, "base")
    linked = tmp_path / "linked"
    git(primary, "worktree", "add", "-q", "-b", "r3-linked", str(linked))
    (linked / "value.txt").write_text("dirty", encoding="utf-8")

    result = _module()._invoke_git(
        subprocess.run,
        str(linked),
        "diff",
        "--no-renames",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
        "--name-only",
        "-z",
        "HEAD",
        "--",
    )
    assert result is not None and result.returncode == 0
    assert result.stdout == "value.txt\0"


def test_real_probe_ignores_repository_replace_refs(tmp_path) -> None:
    repo = tmp_path / "replace"
    first = init_repo(repo, "first")
    first_tree = git(repo, "rev-parse", f"{first}^{{tree}}")
    (repo / "value.txt").write_text("second", encoding="utf-8")
    git(repo, "add", "value.txt")
    git(repo, "commit", "-q", "-m", "second")
    second_tree = git(repo, "rev-parse", "HEAD^{tree}")
    assert first_tree != second_tree
    git(repo, "replace", "HEAD", first)
    result = _module()._invoke_git(subprocess.run, str(repo), "rev-parse", "HEAD^{tree}")
    assert result is not None and result.returncode == 0 and result.stdout.strip() == second_tree


def helper(path: Path, marker: Path, output: str = "") -> None:
    path.write_text(
        "#!/bin/sh\n" + f"printf hit > {marker}\n" +
        (f"printf '%s' '{output}'\n" if output else "") + "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.mark.parametrize("helper_key", ["clean", "process"])
def test_real_probe_refuses_filter_helpers_before_they_execute(
    tmp_path,
    helper_key: str,
) -> None:
    repo = tmp_path / f"filter-{helper_key}"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "R3 Test")
    git(repo, "config", "user.email", "r3@example.invalid")
    (repo / ".gitattributes").write_text("*.txt filter=evil\n", encoding="utf-8")
    (repo / "value.txt").write_text("AAAA", encoding="utf-8")
    git(repo, "add", ".gitattributes", "value.txt")
    git(repo, "commit", "-q", "-m", "filtered base")
    head = git(repo, "rev-parse", "HEAD^{commit}")

    marker = tmp_path / f"{helper_key}-executed"
    script = tmp_path / f"{helper_key}-filter.sh"
    if helper_key == "clean":
        script.write_text(
            "#!/bin/sh\ncat >/dev/null\n"
            f"printf hit > {marker}\n"
            "printf AAAA\n",
            encoding="utf-8",
        )
    else:
        script.write_text(
            "#!/bin/sh\n"
            f"printf hit > {marker}\n"
            "exit 1\n",
            encoding="utf-8",
        )
    script.chmod(0o755)
    git(repo, "config", f"filter.evil.{helper_key}", str(script))
    git(repo, "config", "filter.evil.required", "true")
    (repo / "value.txt").write_text("BBBB", encoding="utf-8")
    marker.unlink(missing_ok=True)

    module = _module()
    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        repo_request(module, repo, head),
        head,
        head,
        (),
    )
    assert isinstance(result, module.SourceContinuityRefusal)
    assert result.code.value == "LOCAL_PROBE_FAILED"
    assert not marker.exists()


def test_real_probe_observes_dirty_submodule_despite_local_ignore_all(tmp_path) -> None:
    child = tmp_path / "child"
    init_repo(child, "child")
    parent = tmp_path / "parent"
    init_repo(parent, "parent")
    git(
        parent,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(child),
        "sub",
    )
    git(parent, "commit", "-q", "-am", "add submodule")
    merge_base = git(parent, "rev-parse", "HEAD^{commit}")
    (parent / "value.txt").write_text("remote", encoding="utf-8")
    git(parent, "add", "value.txt")
    git(parent, "commit", "-q", "-m", "remote value change")
    head = git(parent, "rev-parse", "HEAD^{commit}")
    git(parent, "config", "submodule.sub.ignore", "all")
    (parent / "sub" / "value.txt").write_text("dirty", encoding="utf-8")

    module = _module()
    result = module._probe_local_and_entries(
        subprocess.run,
        str(parent),
        repo_request(module, parent, head),
        head,
        merge_base,
        ("value.txt",),
    )
    assert not isinstance(result, module.SourceContinuityRefusal)
    local_facts, _ = result
    assert local_facts.uncommitted_out_of_scope_count == 1


def test_real_probe_observes_symlink_replaced_by_same_bytes_regular_file(
    tmp_path,
) -> None:
    repo = tmp_path / "symlink-mode"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "R3 Test")
    git(repo, "config", "user.email", "r3@example.invalid")
    link = repo / "link"
    link.symlink_to("target")
    git(repo, "add", "link")
    git(repo, "commit", "-q", "-m", "symlink base")
    head = git(repo, "rev-parse", "HEAD^{commit}")
    git(repo, "config", "core.symlinks", "false")
    link.unlink()
    link.write_text("target", encoding="utf-8")

    module = _module()
    request_with_link = module.SourceContinuityRequest(
        receipt_kind=module.ReceiptKind.CHECKPOINT_VERIFIED,
        operation_key="source-continuity-r3-symlink-hardening-20260904-sol-001",
        repository=REPOSITORY,
        pr_number=448,
        branch=git(repo, "symbolic-ref", "--short", "HEAD"),
        base_ref="master",
        pinned_base_sha=head,
        owned_paths=("link",),
        verified_at="2026-09-04T04:00:00Z",
    )
    result = module._probe_local_and_entries(
        subprocess.run,
        str(repo),
        request_with_link,
        head,
        head,
        (),
    )
    assert not isinstance(result, module.SourceContinuityRefusal)
    local_facts, _ = result
    assert local_facts.uncommitted_in_scope_count == 1


def test_real_diff_disables_fsmonitor_external_diff_and_textconv(tmp_path) -> None:
    repo = tmp_path / "helpers"
    init_repo(repo, "base")
    markers = [tmp_path / name for name in ("fsmonitor", "external", "textconv")]
    scripts = [tmp_path / f"{name}.sh" for name in ("fsmonitor", "external", "textconv")]
    helper(scripts[0], markers[0], "{}")
    helper(scripts[1], markers[1])
    helper(scripts[2], markers[2], "converted")
    git(repo, "config", "core.fsmonitor", str(scripts[0]))
    git(repo, "config", "diff.external", str(scripts[1]))
    git(repo, "config", "diff.touch.textconv", str(scripts[2]))
    (repo / ".gitattributes").write_text("*.txt diff=touch\n", encoding="utf-8")
    git(repo, "add", ".gitattributes")
    git(repo, "commit", "-q", "-m", "attrs")
    (repo / "value.txt").write_text("changed", encoding="utf-8")
    for marker in markers:
        marker.unlink(missing_ok=True)
    result = _module()._invoke_git(
        subprocess.run, str(repo), "diff", "--no-renames", "--no-ext-diff",
        "--no-textconv", "--name-only", "-z", "HEAD", "--",
    )
    assert result is not None and result.returncode == 0 and "value.txt" in result.stdout
    assert all(not marker.exists() for marker in markers)


def test_real_no_rename_diff_reports_old_and_new_for_range_staged_and_unstaged(tmp_path) -> None:
    repo = tmp_path / "rename"
    first = init_repo(repo, "base")
    git(repo, "mv", "value.txt", "renamed.txt")
    module = _module()
    common = ("--no-renames", "--no-ext-diff", "--no-textconv", "--name-only", "-z")
    staged = module._invoke_git(subprocess.run, str(repo), "diff", "--cached", *common, "--")
    assert staged is not None and set(filter(None, staged.stdout.split("\0"))) == {"value.txt", "renamed.txt"}
    git(repo, "commit", "-q", "-m", "rename")
    second = git(repo, "rev-parse", "HEAD^{commit}")
    ranged = module._invoke_git(subprocess.run, str(repo), "diff", *common, f"{first}..{second}", "--")
    assert ranged is not None and set(filter(None, ranged.stdout.split("\0"))) == {"value.txt", "renamed.txt"}
    (repo / "renamed.txt").rename(repo / "again.txt")
    git(repo, "add", "-N", "again.txt")
    unstaged = module._invoke_git(subprocess.run, str(repo), "diff", *common, "HEAD", "--")
    assert unstaged is not None and set(filter(None, unstaged.stdout.split("\0"))) == {"renamed.txt", "again.txt"}
