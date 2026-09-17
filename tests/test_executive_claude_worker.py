"""Task 1/2 contract tests for the native, foreground Claude Code adapter."""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import os
from pathlib import Path
import subprocess

import pytest

from control_plane import claude_worker
from control_plane.claude_worker import (
    ClaudeAuthObservation,
    ClaudeCodeWorkerAdapter,
    ClaudeWorkerContractError,
    attest_claude_code_binary,
)
from control_plane.worker_adapter import (
    WorkerExecutionAdapter,
    adapter_descriptor,
    adapter_implementation,
)
from control_plane.worker_execution_contract import (
    CancelReceipt,
    CollectionReceipt,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRunStatus,
)


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
        'root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
        'mode=$(cat "$root/mode")\n'
        'printf "%s\\n" "$@" > "$root/argv"\n'
        'env | LC_ALL=C sort > "$root/environment"\n'
        'if [ "$1" = "--safe-mode" ] && [ "$2" = "--setting-sources" ] && [ -z "$3" ] && [ "$4" = "auth" ] && [ "$5" = "status" ] && [ "$#" -eq 5 ]; then\n'
        '  case "$mode" in\n'
        '    auth-ready) printf \'{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","email":"person@example.invalid","organization":"discard-me","subscriptionType":"discard-me","apiKeySource":"/login managed key"}\\n\'; exit 0 ;;\n'
        '    auth-logged-out) printf \'{"loggedIn":false}\\n\'; exit 1 ;;\n'
        '    auth-malformed) printf \'not-json\\n\'; exit 0 ;;\n'
        '    auth-unknown) printf \'{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","credential":"CREDENTIAL-SENTINEL"}\\n\'; exit 0 ;;\n'
        '    auth-token) printf \'{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","email":"Bearer abcdefghijklmnopqrstuvwxyz"}\\n\'; exit 0 ;;\n'
        '    auth-nonzero) printf \'{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty"}\\n\'; exit 9 ;;\n'
        '    auth-sleep) sleep 2; exit 0 ;;\n'
        '  esac\n'
        'fi\n'
        'case "$mode" in\n'
        '  success) printf \'{"is_error":false,"model":"claude-opus-4-6","session_id":"fixture-session","usage":{"input_tokens":1,"output_tokens":2},"structured_output":{"outcome":"ok","run_id":"run-1","job_id":"job-1","worker_id":"worker-1","artifacts":[]}}\\n\' ;;\n'
        '  refusal) printf \'{"is_error":true,"subtype":"error","message":"refused"}\\n\' ;;\n'
        '  malformed) printf \'not-json\\n\' ;;\n'
        '  model-mismatch) printf \'{"is_error":false,"model":"another-model","structured_output":{"outcome":"ok","artifacts":[]}}\\n\' ;;\n'
        '  secret-output) printf \'{"is_error":false,"model":"claude-opus-4-6","structured_output":{"outcome":"CREDENTIAL-SENTINEL","token":"CREDENTIAL-SENTINEL","artifacts":[]}}\\n\' ;;\n'
        '  sleep) sleep 2 ;;\n'
        '  *) printf \'{"is_error":true,"subtype":"error"}\\n\' ;;\n'
        'esac\n'
        "exit 0\n",
        encoding="utf-8",
    )
    binary.chmod(0o700)
    (tmp_path / "mode").write_text("auth-ready", encoding="utf-8")
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


def _workspace_and_spec(
    tmp_path: Path, *, run_id: str = "run-1", **changes: object
) -> WorkerLaunchSpec:
    workspace = tmp_path / f"workspace-{run_id}"
    workspace.mkdir(mode=0o700)
    (workspace / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["/usr/bin/git", "init", "-q"], cwd=workspace, check=True)
    subprocess.run(["/usr/bin/git", "add", "README.md"], cwd=workspace, check=True)
    subprocess.run(
        [
            "/usr/bin/git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "initial",
        ],
        cwd=workspace,
        check=True,
    )
    run_dir = tmp_path / f"run-{run_id}"
    run_dir.mkdir(mode=0o700)
    schema = run_dir / "result.schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["outcome", "artifacts"],
                "properties": {
                    "outcome": {"type": "string"},
                    "artifacts": {"type": "array"},
                },
            }
        ),
        encoding="utf-8",
    )
    values: dict[str, object] = {
        "run_id": run_id,
        "job_id": "job-1",
        "worker_id": "worker-1",
        "workspace_path": workspace,
        "run_dir": run_dir,
        "prompt": "fixture foreground task",
        "result_schema_path": schema,
        "authorities": ("READ",),
        "model": _EXACT_MODEL,
        "timeout_seconds": 0.15,
        "cancel_grace_seconds": 0.1,
    }
    values.update(changes)
    return WorkerLaunchSpec(**values)  # type: ignore[arg-type]


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


def test_binary_attestation_refuses_symlink_unsafe_mode_and_changed_bytes(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    linked = tmp_path / "linked-claude"
    linked.symlink_to(binary)
    with pytest.raises(ClaudeWorkerContractError, match="must not be a symlink"):
        attest_claude_code_binary(
            linked, allowed_versions=frozenset({_FIXTURE_VERSION})
        )

    binary.chmod(0o777)
    with pytest.raises(ClaudeWorkerContractError, match="group/other writable"):
        attest_claude_code_binary(
            binary, allowed_versions=frozenset({_FIXTURE_VERSION})
        )

    binary.chmod(0o700)
    attestation = attest_claude_code_binary(
        binary, allowed_versions=frozenset({_FIXTURE_VERSION})
    )
    binary.write_text("#!/bin/sh\nexit 64\n", encoding="utf-8")
    binary.chmod(0o700)
    with pytest.raises(ClaudeWorkerContractError, match="changed"):
        claude_worker._assert_claude_binary_unchanged(attestation)


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
                    ["Glob(./**)", "Grep(./**)", "Read(./**)"]
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
                "deny": (
                    [
                        "Agent",
                        "Bash",
                        "Edit",
                        "NotebookEdit",
                        "Skill",
                        "Task",
                        "WebFetch",
                        "WebSearch",
                        "Write",
                        "mcp__*",
                    ]
                    if invocation is read_only
                    else [
                        "Agent",
                        "NotebookEdit",
                        "Skill",
                        "Task",
                        "WebFetch",
                        "WebSearch",
                        "mcp__*",
                    ]
                ),
                "disableBypassPermissionsMode": "disable",
            },
            "switchModelsOnFlag": False,
        }

    read_tools = read_only.argv[read_only.argv.index("--tools") + 1]
    read_allowed = read_only.argv[read_only.argv.index("--allowedTools") + 1]
    write_tools = write_and_test.argv[write_and_test.argv.index("--tools") + 1]
    write_allowed = write_and_test.argv[write_and_test.argv.index("--allowedTools") + 1]
    assert read_tools == "Glob,Grep,Read"
    assert read_allowed == "Glob(./**),Grep(./**),Read(./**)"
    assert write_tools == "Bash,Edit,Glob,Grep,Read,Write"
    assert write_allowed == (
        "Bash(python3 -m pytest *),Edit(./src/allowed.py),Glob(./**),Grep(./**),"
        "Read(./**),"
        "Write(./src/allowed.py)"
    )
    assert "Edit" not in write_allowed.split(",")
    assert "Write" not in write_allowed.split(",")
    for invocation in (read_only, write_and_test):
        settings = json.loads(
            invocation.argv[invocation.argv.index("--settings") + 1]
        )
        allowed = invocation.argv[
            invocation.argv.index("--allowedTools") + 1
        ].split(",")
        denied = invocation.argv[
            invocation.argv.index("--disallowedTools") + 1
        ].split(",")
        assert settings["permissions"]["allow"] == allowed
        assert settings["permissions"]["deny"] == denied
        assert not {
            "Bash",
            "Edit",
            "Glob",
            "Grep",
            "Read",
            "Write",
        }.intersection(allowed)
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


@pytest.mark.parametrize(
    "path",
    (
        "/absolute.py",
        "",
        ".",
        "..",
        "a/../b.py",
        "a//b.py",
        "a/./b.py",
        r"a\b.py",
        "src/\x00x.py",
        "src/\x1fx.py",
        "src/x),Bash(*)",
        ".git/config",
        ".codex/config.toml",
        ".claude/settings.json",
        "config.toml",
        ".env",
        ".env.secret",
    ),
)
def test_compiler_refuses_unsafe_write_permission_path(
    tmp_path: Path, path: str
) -> None:
    with pytest.raises(ClaudeWorkerContractError, match="not safe"):
        _adapter(tmp_path).compile_launch(
            _spec(
                tmp_path,
                authorities=("READ", "WRITE_BRANCH"),
                allowed_artifact_paths=(path,),
            )
        )


def test_compiler_refuses_duplicate_write_permission_paths(tmp_path: Path) -> None:
    with pytest.raises(ClaudeWorkerContractError, match="duplicate"):
        _adapter(tmp_path).compile_launch(
            _spec(
                tmp_path,
                authorities=("READ", "WRITE_BRANCH"),
                allowed_artifact_paths=("src/**/*.py", "src/**/*.py"),
            )
        )


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
    serialized = json.dumps({"argv": invocation.argv, "environment": repr(invocation.environment)})

    with pytest.raises(TypeError):
        invocation.environment["ANTHROPIC_AUTH_TOKEN"] = "must-not-fit"  # type: ignore[index]
    with pytest.raises(ClaudeWorkerContractError, match="not realized"):
        invocation.environment.as_subprocess_environment()
    for name, value in ambient.items():
        assert name not in serialized
        assert value not in serialized


def test_auth_observation_uses_exact_fenced_argv_and_closed_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    monkeypatch.setenv("ARBITRARY_AMBIENT_VARIABLE", "ambient-sentinel")
    observation = _adapter(tmp_path, binary).observe_auth_status(timeout_seconds=1)

    assert observation == ClaudeAuthObservation(
        client_version=_FIXTURE_VERSION,
        authenticated=True,
        ready=True,
        auth_method="claudeai",
        api_provider="first_party",
        exit_code=0,
        observed_at=observation.observed_at,
    )
    assert (tmp_path / "argv").read_text(encoding="utf-8").splitlines() == [
        "--safe-mode",
        "--setting-sources",
        "",
        "auth",
        "status",
    ]
    child_environment = (tmp_path / "environment").read_text(encoding="utf-8")
    assert "ARBITRARY_AMBIENT_VARIABLE" not in child_environment
    assert "ANTHROPIC_" not in child_environment
    assert "CLAUDE_CODE_" not in child_environment


def test_auth_observation_discards_pii_and_reports_logged_out(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    adapter = _adapter(tmp_path, binary)

    ready = adapter.observe_auth_status(timeout_seconds=1)
    (tmp_path / "mode").write_text("auth-logged-out", encoding="utf-8")
    logged_out = adapter.observe_auth_status(timeout_seconds=1)

    serialized = repr(ready)
    assert "person@example.invalid" not in serialized
    assert "discard-me" not in serialized
    assert logged_out.authenticated is False
    assert logged_out.ready is False
    assert logged_out.auth_method == "unknown"
    assert logged_out.api_provider == "unknown"
    assert logged_out.exit_code == 1


@pytest.mark.parametrize(
    "mode",
    ("auth-malformed", "auth-unknown", "auth-token", "auth-nonzero", "auth-sleep"),
)
def test_auth_observation_refuses_unsafe_provider_responses(
    tmp_path: Path, mode: str
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text(mode, encoding="utf-8")

    with pytest.raises(ClaudeWorkerContractError) as raised:
        _adapter(tmp_path, binary).observe_auth_status(timeout_seconds=0.05)
    assert "CREDENTIAL-SENTINEL" not in str(raised.value)


def test_auth_observation_refuses_ambient_provider_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "CREDENTIAL-SENTINEL")
    with pytest.raises(ClaudeWorkerContractError, match="environment"):
        _adapter(tmp_path).observe_auth_status(timeout_seconds=1)


def test_foreground_success_returns_common_structured_result(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    spec = _workspace_and_spec(tmp_path)

    async def execute() -> CollectionReceipt:
        return await adapter.collect_result(await adapter.start(spec))

    receipt = asyncio.run(execute())

    assert isinstance(receipt, CollectionReceipt)
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED
    assert receipt.result.structured_output == {
        "outcome": "ok",
        "run_id": "run-1",
        "job_id": "job-1",
        "worker_id": "worker-1",
        "artifacts": (),
    }
    assert receipt.process_ref.provider_session_id == "fixture-session"
    assert receipt.result.usage == {"input_tokens": 1, "output_tokens": 2}
    argv = (tmp_path / "argv").read_text(encoding="utf-8").splitlines()
    assert "--json-schema" in argv
    assert argv[argv.index("--model") + 1] == _EXACT_MODEL


@pytest.mark.parametrize(
    "mode",
    ("refusal", "malformed", "model-mismatch", "secret-output"),
)
def test_foreground_bad_provider_output_never_succeeds_or_persists_secret(
    tmp_path: Path, mode: str
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text(mode, encoding="utf-8")
    spec = _workspace_and_spec(tmp_path, run_id=f"run-{mode}")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> CollectionReceipt:
        return await adapter.collect_result(await adapter.start(spec))

    receipt = asyncio.run(execute())

    assert receipt.result.status is WorkerRunStatus.INVALID_RESULT
    for path in (
        Path(receipt.process_ref.stdout_path),
        Path(receipt.process_ref.stderr_path),
        Path(receipt.process_ref.result_path),
    ):
        assert "CREDENTIAL-SENTINEL" not in path.read_text(encoding="utf-8")


def test_collect_timeout_is_typed_common_result(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    spec = _workspace_and_spec(tmp_path, timeout_seconds=0.05)

    async def execute() -> CollectionReceipt:
        return await adapter.collect_result(await adapter.start(spec))

    receipt = asyncio.run(execute())

    assert isinstance(receipt, CollectionReceipt)
    assert receipt.result.status is WorkerRunStatus.TIMED_OUT
    assert receipt.result.structured_output is None


def test_explicit_cancel_returns_common_receipt_and_terminal_cancelled(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> tuple[CancelReceipt, CollectionReceipt]:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=1))
        return await adapter.cancel(ref, "operator requested"), await adapter.collect_result(ref)

    cancellation, receipt = asyncio.run(execute())

    assert isinstance(cancellation, CancelReceipt)
    assert cancellation.signal_sent is True
    assert receipt.result.status is WorkerRunStatus.CANCELLED


def test_unknown_or_ambiguous_process_reference_refuses(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> None:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=1))
        altered = dataclasses.replace(ref, launch_nonce="other")
        with pytest.raises(ClaudeWorkerContractError):
            await adapter.status(altered)

        class AmbiguousInspector:
            def boot_session_id(self) -> str:
                return ref.boot_session_id

            def inspect(self, _pid: int) -> object:
                return object()

            def identity(self, _pid: int) -> tuple[str, int]:
                return "other", ref.pgid

        adapter.inspector = AmbiguousInspector()
        with pytest.raises(ClaudeWorkerContractError):
            await adapter.status(ref)
        os.killpg(ref.pgid, 15)
        await adapter.collect_result(ref)

    asyncio.run(execute())


def test_status_and_shell_free_validation_use_common_contracts(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    spec = _workspace_and_spec(tmp_path)

    async def execute() -> ValidationReceipt:
        ref = await adapter.start(spec)
        assert await adapter.status(ref) is WorkerRunStatus.RUNNING
        await adapter.collect_result(ref)
        return await adapter.run_validation_argv(spec, ("/usr/bin/true",), timeout_seconds=1)

    validation = asyncio.run(execute())
    assert isinstance(validation, ValidationReceipt)
    assert validation.exit_code == 0
    with pytest.raises(ClaudeWorkerContractError, match="shell"):
        asyncio.run(adapter.run_validation_argv(spec, ("/bin/sh", "-c", "true")))
