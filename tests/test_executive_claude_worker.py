"""Task 1 contract tests for the native, foreground Claude Code adapter."""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from control_plane.claude_worker import (
    ClaudeCodeWorkerAdapter,
    ClaudeWorkerContractError,
    attest_claude_code_binary,
)
from control_plane.worker_adapter import (
    WorkerExecutionAdapter,
    adapter_descriptor,
    adapter_implementation,
)
from control_plane.worker_execution_contract import WorkerLaunchSpec


_EXACT_MODEL = "claude-opus-4-6"
_FIXTURE_VERSION = "2.1.239"


def _fixture_claude_binary(tmp_path: Path) -> Path:
    binary = tmp_path / "fixture-claude"
    binary.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        f"  printf '{_FIXTURE_VERSION} (Claude Code)\\n'\n"
        "  exit 0\n"
        "fi\n"
        "exit 64\n",
        encoding="utf-8",
    )
    binary.chmod(0o700)
    return binary


def _spec(tmp_path: Path, **changes: object) -> WorkerLaunchSpec:
    values: dict[str, object] = {
        "run_id": "run-1",
        "job_id": "job-1",
        "worker_id": "worker-1",
        "workspace_path": tmp_path / "workspace",
        "run_dir": tmp_path / "run",
        "prompt": "Perform only the authorized bounded task.",
        "result_schema_path": tmp_path / "result.schema.json",
        "authorities": ("READ",),
        # Provider model selection is adapter-private; this must not affect
        # the native Claude invocation.
        "model": "provider-neutral-model-label",
    }
    values.update(changes)
    return WorkerLaunchSpec(**values)  # type: ignore[arg-type]


def _adapter(tmp_path: Path, binary: Path | None = None) -> ClaudeCodeWorkerAdapter:
    binary = binary or _fixture_claude_binary(tmp_path)
    return ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
    )


def test_descriptor_is_unimplemented_but_resolves_the_exact_native_class() -> None:
    descriptor = adapter_descriptor("claude-code")

    assert descriptor.implemented is False
    assert descriptor.implementation == "control_plane.claude_worker.ClaudeCodeWorkerAdapter"
    assert adapter_implementation("claude-code") is ClaudeCodeWorkerAdapter
    for alias in ("claude", "claude-cli", "claude-code-v1", "claude-compatible"):
        with pytest.raises(ValueError, match="unknown worker adapter"):
            adapter_descriptor(alias)


def test_constructor_attests_an_absolute_versioned_non_secret_binary(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)

    attestation = attest_claude_code_binary(
        binary, allowed_versions=frozenset({_FIXTURE_VERSION})
    )
    adapter = _adapter(tmp_path, binary)

    assert attestation.path == str(binary)
    assert attestation.real_path == str(binary.resolve())
    assert attestation.version == _FIXTURE_VERSION
    assert attestation.team_identifier is None
    assert adapter.binary == attestation
    assert isinstance(adapter, WorkerExecutionAdapter)
    signature = inspect.signature(ClaudeCodeWorkerAdapter)
    assert tuple(signature.parameters) == (
        "claude_binary",
        "allowed_versions",
        "exact_model",
        "max_turns",
    )
    with pytest.raises(AttributeError):
        adapter.exact_model = "claude-sonnet-4-6"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        adapter.max_turns = 5  # type: ignore[misc]
    with pytest.raises(ClaudeWorkerContractError, match="must be absolute"):
        ClaudeCodeWorkerAdapter(
            Path("fixture-claude"),
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
        )


def test_compiler_projects_only_read_write_and_test_capabilities(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)

    read_only = adapter.compile_launch(_spec(tmp_path))
    write_and_test = adapter.compile_launch(
        _spec(
            tmp_path,
            authorities=("READ", "WRITE_BRANCH", "RUN_TESTS"),
            allowed_artifact_paths=("src/allowed.py",),
        )
    )

    for invocation in (read_only, write_and_test):
        argv = invocation.argv
        assert argv[0] == str((tmp_path / "fixture-claude").resolve())
        assert "-p" in argv
        assert ("--output-format", "json") == (
            argv[argv.index("--output-format") : argv.index("--output-format") + 2]
        )
        assert "--safe-mode" in argv
        assert "--no-chrome" in argv
        assert "--no-session-persistence" in argv
        assert ("--max-turns", "4") == (
            argv[argv.index("--max-turns") : argv.index("--max-turns") + 2]
        )
        assert ("--model", _EXACT_MODEL) == (
            argv[argv.index("--model") : argv.index("--model") + 2]
        )
        assert ("--permission-mode", "dontAsk") == (
            argv[argv.index("--permission-mode") : argv.index("--permission-mode") + 2]
        )
        assert "--strict-mcp-config" in argv
        assert "--disable-slash-commands" in argv
        assert '{"mcpServers":{}}' in argv
        settings = json.loads(argv[argv.index("--settings") + 1])
        assert settings == {
            "autoMemoryEnabled": False,
            "disableAllHooks": True,
            "enableAllProjectMcpServers": False,
            "enabledMcpjsonServers": [],
            "permissions": {
                "allow": (
                    [
                        "Glob(./**)",
                        "Grep(./**)",
                        "Read(./**)",
                    ]
                    if invocation is read_only
                    else [
                        "Bash(python3 -m pytest *)",
                        "Edit(./src/allowed.py)",
                        "Glob(./**)",
                        "Grep(./**)",
                        "Read(./**)",
                        "Write(./src/allowed.py)",
                    ]
                ),
                "ask": [],
                "defaultMode": "dontAsk",
                "deny": [
                    "Agent",
                    "NotebookEdit",
                    "Skill",
                    "Task",
                    "WebFetch",
                    "WebSearch",
                    "mcp__*",
                ],
                "disableBypassPermissionsMode": "disable",
            },
            "switchModelsOnFlag": False,
        }

    read_tools = read_only.argv[read_only.argv.index("--tools") + 1]
    read_allowed = read_only.argv[read_only.argv.index("--allowedTools") + 1]
    write_tools = write_and_test.argv[write_and_test.argv.index("--tools") + 1]
    write_allowed = write_and_test.argv[write_and_test.argv.index("--allowedTools") + 1]
    assert read_tools == read_allowed == "Glob,Grep,Read"
    assert write_tools == "Bash,Edit,Glob,Grep,Read,Write"
    assert write_allowed == (
        "Bash(python3 -m pytest *),Edit(./src/allowed.py),Glob,Grep,Read,"
        "Write(./src/allowed.py)"
    )
    assert "Edit" not in write_allowed.split(",")
    assert "Write" not in write_allowed.split(",")
    assert read_only.argv[read_only.argv.index("--disallowedTools") + 1] == (
        "Agent,Bash,Edit,NotebookEdit,Skill,Task,WebFetch,WebSearch,Write,mcp__*"
    )
    assert write_and_test.argv[write_and_test.argv.index("--disallowedTools") + 1] == (
        "Agent,NotebookEdit,Skill,Task,WebFetch,WebSearch,mcp__*"
    )


def test_compiler_refuses_unknown_or_unmapped_capabilities(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)

    for authorities in (
        ("RESEARCH",),
        ("READ", "BROWSER"),
        ("READ", "MCP"),
        ("READ", "DEPLOY"),
        ("READ", "WRITE_BRANCH"),
    ):
        with pytest.raises(ClaudeWorkerContractError, match="unsupported or unmapped"):
            adapter.compile_launch(_spec(tmp_path, authorities=authorities))


def test_compiler_refuses_an_empty_capability_grant(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)

    with pytest.raises(ClaudeWorkerContractError, match="explicit capability grant"):
        adapter.compile_launch(_spec(tmp_path, authorities=(), authority=None))


def test_compiler_uses_closed_environment_without_ambient_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ambient = {
        "ANTHROPIC_API_KEY": "api-key-sentinel",
        "ANTHROPIC_AUTH_TOKEN": "auth-token-sentinel",
        "CLAUDE_CODE_OAUTH_TOKEN": "oauth-token-sentinel",
        "CLAUDE_SETUP_TOKEN": "setup-token-sentinel",
        "ARBITRARY_AMBIENT_VARIABLE": "ambient-sentinel",
    }
    for name, value in ambient.items():
        monkeypatch.setenv(name, value)

    invocation = _adapter(tmp_path).compile_launch(_spec(tmp_path))
    serialized = json.dumps({"argv": invocation.argv, "environment": invocation.environment})

    assert invocation.environment == {
        "HOME": "/var/empty",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "TZ": "UTC",
    }
    for name, value in ambient.items():
        assert name not in invocation.environment
        assert name not in serialized
        assert value not in serialized
