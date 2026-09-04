from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "source_continuity.py"
REPOSITORY = "mastermindx-market-intelligence/Mastermind"
TOKEN = "token"


def _module():
    name = "source_continuity_r3_adapter_under_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _FilesHTTP:
    def __init__(self, files: list[object]) -> None:
        self.files = files

    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN
        assert timeout > 0
        assert url.endswith("/files?per_page=100&page=1")
        return self.files


def _changed_paths(module: Any, files: list[object]) -> tuple[str, ...]:
    paths, complete = module._changed_paths(
        _FilesHTTP(files), TOKEN, REPOSITORY, 446
    )
    assert complete is True
    return paths


def test_rename_census_contains_both_previous_and_current_paths() -> None:
    module = _module()
    assert _changed_paths(
        module,
        [
            {
                "filename": "tests/test_source_continuity_r3_hardening.py",
                "status": "renamed",
                "previous_filename": "tests/old_source_continuity_test.py",
            }
        ],
    ) == (
        "tests/old_source_continuity_test.py",
        "tests/test_source_continuity_r3_hardening.py",
    )


@pytest.mark.parametrize(
    "item",
    [
        {"filename": "a.py", "status": "renamed"},
        {"filename": "a.py", "status": "renamed", "previous_filename": ""},
        {"filename": "a.py", "status": "renamed", "previous_filename": 7},
        {"filename": "a.py", "status": "unknown"},
        {"filename": "a.py", "status": "modified", "previous_filename": "b.py"},
        {"filename": "bad\ud800.py", "status": "modified"},
    ],
)
def test_malformed_or_open_world_file_metadata_fails_closed(item: object) -> None:
    module = _module()
    with pytest.raises(module._RemoteProbeError):
        _changed_paths(module, [item])


def test_duplicate_effective_rename_paths_fail_closed() -> None:
    module = _module()
    with pytest.raises(module._RemoteProbeError):
        _changed_paths(
            module,
            [
                {"filename": "a.py", "status": "modified"},
                {
                    "filename": "b.py",
                    "status": "renamed",
                    "previous_filename": "a.py",
                },
            ],
        )


def test_legacy_statusless_fixture_remains_a_single_nonrename_path() -> None:
    module = _module()
    assert _changed_paths(module, [{"filename": "a.py"}]) == ("a.py",)


class _CollisionHTTP:
    def __call__(self, url: str, *, token: str, timeout: float) -> object:
        assert token == TOKEN
        assert timeout > 0
        if url.endswith("/pulls?state=open&per_page=100&page=1"):
            return [{"number": 446}, {"number": 999}]
        if url.endswith("/pulls/999/files?per_page=100&page=1"):
            return [
                {
                    "filename": "archive/source_continuity.py",
                    "status": "renamed",
                    "previous_filename": "scripts/source_continuity.py",
                }
            ]
        raise AssertionError(url)


def test_collision_census_catches_another_pr_renaming_owned_path_away() -> None:
    module = _module()
    state, numbers, complete = module._collision_census(
        _CollisionHTTP(),
        TOKEN,
        REPOSITORY,
        446,
        ("scripts/source_continuity.py",),
    )
    assert state is module.CollisionState.OVERLAP
    assert numbers == (999,)
    assert complete is True


class _CaptureRunner:
    def __init__(self) -> None:
        self.command: tuple[str, ...] | None = None
        self.kwargs: dict[str, Any] | None = None

    def __call__(self, command: list[str], **kwargs: Any) -> SimpleNamespace:
        self.command = tuple(command)
        self.kwargs = dict(kwargs)
        return SimpleNamespace(returncode=0, stdout="")


def _captured_git_env(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, dict[str, str]]:
    hostile = {
        "HOME": "/tmp/hostile-home",
        "XDG_CONFIG_HOME": "/tmp/hostile-xdg",
        "GITHUB_TOKEN": "secret",
        "GIT_DIR": "/tmp/other.git",
        "GIT_WORK_TREE": "/tmp/other-tree",
        "GIT_COMMON_DIR": "/tmp/common",
        "GIT_INDEX_FILE": "/tmp/index",
        "GIT_OBJECT_DIRECTORY": "/tmp/objects",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/alternates",
        "GIT_REPLACE_REF_BASE": "refs/replace-hostile/",
        "GIT_EXTERNAL_DIFF": "/tmp/run-me",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "alias.status",
        "GIT_CONFIG_VALUE_0": "!touch /tmp/owned",
        "GIT_CONFIG_PARAMETERS": "'core.fsmonitor=/tmp/run-me'",
        "GIT_CONFIG_SYSTEM": "/tmp/system-config",
        "GIT_CONFIG_GLOBAL": "/tmp/global-config",
        "GIT_LITERAL_PATHSPECS": "0",
        "GIT_GLOB_PATHSPECS": "1",
        "GIT_NOGLOB_PATHSPECS": "0",
        "GIT_ICASE_PATHSPECS": "1",
    }
    for key, value in hostile.items():
        monkeypatch.setenv(key, value)

    module = _module()
    runner = _CaptureRunner()
    result = module._invoke_git(runner, "/repo", "status", "--porcelain")
    assert result is not None
    assert runner.kwargs is not None
    env = runner.kwargs["env"]
    assert isinstance(env, dict)
    return module, env


def test_git_probe_environment_does_not_inherit_host_selectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, env = _captured_git_env(monkeypatch)
    forbidden = {
        "HOME",
        "XDG_CONFIG_HOME",
        "GITHUB_TOKEN",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_REPLACE_REF_BASE",
        "GIT_EXTERNAL_DIFF",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_SYSTEM",
        "GIT_GLOB_PATHSPECS",
        "GIT_NOGLOB_PATHSPECS",
        "GIT_ICASE_PATHSPECS",
    }
    assert forbidden.isdisjoint(env)


def test_git_probe_environment_installs_closed_safety_controls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, env = _captured_git_env(monkeypatch)
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    assert env["GIT_NO_LAZY_FETCH"] == "1"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["GIT_ATTR_NOSYSTEM"] == "1"
    assert env["GIT_LITERAL_PATHSPECS"] == "1"
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert env["GIT_PAGER"] == "cat"

    count = int(env["GIT_CONFIG_COUNT"])
    config = {
        env[f"GIT_CONFIG_KEY_{index}"]: env[f"GIT_CONFIG_VALUE_{index}"]
        for index in range(count)
    }
    assert config == {
        "core.fsmonitor": "false",
        "core.untrackedCache": "false",
        "diff.external": "",
        "diff.renames": "false",
    }
