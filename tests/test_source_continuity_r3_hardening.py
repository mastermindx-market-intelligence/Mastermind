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


def test_statusless_legacy_fixture_is_one_nonrename_path() -> None:
    assert changed_paths(_module(), [{"filename": "a.py"}]) == ("a.py",)


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
    state, numbers, complete = module._collision_census(
        CollisionHTTP(row), TOKEN, REPOSITORY, 448, (OWNED[0],)
    )
    assert (state, numbers, complete) == (module.CollisionState.OVERLAP, (999,), True)


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
        HEAD, BASE, OWNED, True, module.CollisionState.NONE, (), True,
    )
    assert calls == 1
    if expected is None:
        assert result is None
    else:
        assert result is not None and result.code.value == expected


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
        }
        if tail in outputs:
            return SimpleNamespace(returncode=0, stdout=outputs[tail])
        if tail[:2] in {("cat-file", "-e"), ("merge-base", "--is-ancestor")}:
            return SimpleNamespace(returncode=0, stdout="")
        if tail[:2] == ("rev-list", "--count"):
            return SimpleNamespace(returncode=0, stdout="0\n")
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
    commands = {"rev-parse", "symbolic-ref", "cat-file", "merge-base", "rev-list", "diff", "ls-files", "ls-tree", "status"}
    return command[next(i for i, value in enumerate(command) if i and value in commands):]


OVERRIDES = (
    "core.fsmonitor=false", "core.untrackedCache=false", "core.hooksPath=/dev/null",
    "core.attributesFile=/dev/null", "core.excludesFile=/dev/null", "diff.external=",
    "diff.renames=false", "credential.helper=", "protocol.allow=never",
    "protocol.file.allow=always",
)


def assert_git_prefix(command: tuple[str, ...]) -> None:
    assert command[:3] == ("/usr/bin/git", "--no-pager", "--no-replace-objects")
    prefix = command[: command.index(git_tail(command)[0])]
    joined = "\0".join(prefix)
    for setting in OVERRIDES:
        assert f"-c\0{setting}" in joined


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
        for flag in ("--no-renames", "--no-ext-diff", "--no-textconv", "--name-only", "-z", "--"):
            assert flag in command
    tree = next(git_tail(c) for c in runner.commands if git_tail(c)[0] == "ls-tree")
    assert "--" in tree and tree[-1] == OWNED[0]
    assert all(env["GIT_LITERAL_PATHSPECS"] == "1" for env in runner.environments)


ENV_KEYS = {
    "LANG", "LC_ALL", "PATH", "HOME", "GIT_OPTIONAL_LOCKS", "GIT_NO_LAZY_FETCH",
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
        "LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin", "HOME": "/",
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


def test_real_probe_ignores_ambient_repo_selectors(tmp_path, monkeypatch) -> None:
    primary, foreign = tmp_path / "primary", tmp_path / "foreign"
    primary_head, foreign_head = init_repo(primary, "primary"), init_repo(foreign, "foreign")
    assert primary_head != foreign_head
    monkeypatch.setenv("GIT_DIR", str(foreign / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(foreign))
    result = _module()._invoke_git(subprocess.run, str(primary), "rev-parse", "HEAD^{commit}")
    assert result is not None and result.returncode == 0 and result.stdout.strip() == primary_head


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
