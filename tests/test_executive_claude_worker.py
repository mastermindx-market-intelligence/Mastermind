"""Task 1/2 contract tests for the native, foreground Claude Code adapter."""
from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import os
from pathlib import Path
import pwd
import platform
import signal
import subprocess
import time
from types import SimpleNamespace

import pytest

from control_plane import claude_worker
from control_plane.claude_worker import (
    ClaudeAuthObservation,
    ClaudeCodeWorkerAdapter,
    ClaudeWorkerContractError,
    attest_claude_code_binary,
)
from control_plane.claude_native_helper_projection import (
    ClaudeNativeHelperDefinition,
    project_claude_native_helpers,
)
from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
from control_plane.operator_harness_contract import ObservedTriState
from control_plane.worker_adapter import (
    WorkerExecutionAdapter,
    adapter_descriptor,
    adapter_implementation,
)
from control_plane.worker_execution_contract import (
    CancelReceipt,
    CollectionReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerRunStatus,
)


_EXACT_MODEL = "claude-opus-4-6"
_FIXTURE_VERSION = "2.1.239"


def _passing_canary() -> dict[str, object]:
    return {
        "schema_version": "mastermind.executive_secret_canary/v1",
        "passed": True,
        "checks": {
            "control_service_environment": "DENIED",
            "administrative_checkout": "DENIED",
            "executive_database": "DENIED",
            "other_worker_home": "DENIED",
            "forbidden_production_path": "DENIED",
        },
        "receipt_sha256": "a" * 64,
        "control_environment_probe_sha256": "b" * 64,
        "observed_at": "2026-09-17T00:00:00Z",
        "worker_auth_exception": "DEDICATED_CODEX_HOME_ONLY",
    }


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
        '    auth-discard-nested) printf \'{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","accountId":{"safe":[1,{"nested":true}]},"organizationId":[null,7],"email":{"nested":"discard"}}\\n\'; exit 0 ;;\n'
        '    auth-discard-secret) printf \'{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","organization":{"credential":"CREDENTIAL-SENTINEL"}}\\n\'; exit 0 ;;\n'
        '    auth-malformed-sentinel) printf \'CREDENTIAL-SENTINEL{not-json\\n\'; exit 0 ;;\n'
        '  esac\n'
        'fi\n'
        'case "$mode" in\n'
        '  success) printf \'{"is_error":false,"model":"claude-opus-4-6","session_id":"fixture-session","usage":{"input_tokens":1,"output_tokens":2},"structured_output":{"outcome":"ok","run_id":"run-1","job_id":"job-1","worker_id":"worker-1","artifacts":[]}}\\n\' ;;\n'
        '  refusal) printf \'{"is_error":true,"subtype":"error","message":"refused"}\\n\' ;;\n'
        '  malformed) printf \'not-json\\n\' ;;\n'
        '  model-mismatch) printf \'{"is_error":false,"model":"another-model","structured_output":{"outcome":"ok","artifacts":[]}}\\n\' ;;\n'
        '  secret-output) printf \'{"is_error":false,"model":"claude-opus-4-6","structured_output":{"outcome":"CREDENTIAL-SENTINEL","token":"CREDENTIAL-SENTINEL","artifacts":[]}}\\n\' ;;\n'
        '  secret-stderr) printf \'{"is_error":false,"model":"claude-opus-4-6","structured_output":{"outcome":"ok","artifacts":[]}}\\n\'; printf \'CREDENTIAL-SENTINEL\\n\' >&2 ;;\n'
        '  refusal-pure) printf \'{"is_error":true,"model":"claude-opus-4-6","structured_output":{"outcome":"ok","artifacts":[]}}\\n\' ;;\n'
        '  malformed-sentinel) printf \'CREDENTIAL-SENTINEL{not-json\\n\' ;;\n'
        '  descendant) (sleep 1) & printf \'{"is_error":false,"model":"claude-opus-4-6","structured_output":{"outcome":"ok","artifacts":[]}}\\n\' ;;\n'
        '  stream-cap) printf \'abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz\\n\'; sleep 1 ;;\n'
        '  delayed-success) sleep 0.2; printf \'{"is_error":false,"model":"claude-opus-4-6","structured_output":{"outcome":"ok","artifacts":[]}}\\n\' ;;\n'
        '  git-change) printf \'changed\\n\' > unexpected.txt; printf \'{"is_error":false,"model":"claude-opus-4-6","structured_output":{"outcome":"ok","artifacts":[]}}\\n\' ;;\n'
        '  nonzero-secret) printf \'{"is_error":false,"model":"claude-opus-4-6","structured_output":{"outcome":"ok","artifacts":[]}}\\n\'; printf \'CREDENTIAL-SENTINEL\\n\' >&2; exit 9 ;;\n'
        '  nonzero) printf \'ordinary fixture failure\\n\' >&2; exit 9 ;;\n'
        '  sleep) sleep 2 ;;\n'
        '  sleep-short) sleep 0.35 ;;\n'
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
    """One reviewed adapter with a valid typed consumer-side observer fake."""

    binary = binary or _fixture_claude_binary(tmp_path)
    return ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=_observer_for(binary, generation=_VALID_GENERATION),
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
        "timeout_seconds": 0.5,
        "cancel_grace_seconds": 0.1,
        # Native Claude execution requires an exact worker principal; the
        # fixture runs as the calling principal so lifecycle tests keep
        # exercising their original cancellation/timeout/cleanup contract.
        "worker_user": pwd.getpwuid(os.geteuid()).pw_name,
        "expected_worker_uid": os.geteuid(),
        "expected_worker_gid": os.getegid(),
        "shared_run_gid": os.getegid(),
    }
    values.update(changes)
    return WorkerLaunchSpec(**values)  # type: ignore[arg-type]


def test_descriptor_remains_unarmed_until_real_turn_proof() -> None:
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
        "managed_policy_observer",
    )
    observer_parameter = signature.parameters["managed_policy_observer"]
    assert observer_parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert observer_parameter.default is None
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
            # The observer seam is required first, so supply a valid one to
            # reach the binary attestation edge this discriminator targets.
            managed_policy_observer=_observer_for(binary),
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
            # The emitted request carries the closed model fences.
            "model": _EXACT_MODEL,
            "fallbackModel": [],
            "availableModels": [_EXACT_MODEL],
            "enforceAvailableModels": True,
            "switchModelsOnFlag": False,
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
                        # ... and every enabled file tool denies the protected
                        # custody classes in the same serialized request.
                        "Glob(.claude/**)",
                        "Glob(.codex/**)",
                        "Glob(.env)",
                        "Glob(.env.*)",
                        "Glob(.git/**)",
                        "Glob(config.toml)",
                        "Grep(.claude/**)",
                        "Grep(.codex/**)",
                        "Grep(.env)",
                        "Grep(.env.*)",
                        "Grep(.git/**)",
                        "Grep(config.toml)",
                        "Read(.claude/**)",
                        "Read(.codex/**)",
                        "Read(.env)",
                        "Read(.env.*)",
                        "Read(.git/**)",
                        "Read(config.toml)",
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
                        "Edit(.claude/**)",
                        "Edit(.codex/**)",
                        "Edit(.env)",
                        "Edit(.env.*)",
                        "Edit(.git/**)",
                        "Edit(config.toml)",
                        "Glob(.claude/**)",
                        "Glob(.codex/**)",
                        "Glob(.env)",
                        "Glob(.env.*)",
                        "Glob(.git/**)",
                        "Glob(config.toml)",
                        "Grep(.claude/**)",
                        "Grep(.codex/**)",
                        "Grep(.env)",
                        "Grep(.env.*)",
                        "Grep(.git/**)",
                        "Grep(config.toml)",
                        "Read(.claude/**)",
                        "Read(.codex/**)",
                        "Read(.env)",
                        "Read(.env.*)",
                        "Read(.git/**)",
                        "Read(config.toml)",
                        "Write(.claude/**)",
                        "Write(.codex/**)",
                        "Write(.env)",
                        "Write(.env.*)",
                        "Write(.git/**)",
                        "Write(config.toml)",
                    ]
                ),
                "disableBypassPermissionsMode": "disable",
            },
            # The fail-closed subprocess sandbox rides in the same request.
            "sandbox": _PROTECTED_SANDBOX_REQUEST,
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
        # ``--disallowedTools`` carries only the tool-level denials; the
        # serialized request additionally denies the protected custody classes
        # for every enabled file tool, after exactly those tool denials.
        enabled_file_tools = {
            rule.split("(", 1)[0] for rule in allowed
        } & set(_FILE_TOOLS)
        assert settings["permissions"]["deny"][: len(denied)] == list(denied)
        assert set(settings["permissions"]["deny"]) == set(denied) | {
            f"{tool}({protected})"
            for tool in enabled_file_tools
            for protected in _PROTECTED_PATH_CLASSES
        }
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


def _native_helper_projection():
    registry = ExecutionCapabilityRegistry.load(
        Path(
            "tests/fixtures/"
            "executive_agent_capabilities_claude_native_helper_v3.json"
        ),
        source_root=Path.cwd(),
    )
    profile = registry.resolve("operator.claude.readonly.native-helper.v1")
    profile = dataclasses.replace(profile, mcp_server_grants=())
    return project_claude_native_helpers(
        profile,
        helpers=(
            ClaudeNativeHelperDefinition(
                agent_id="code-reader",
                description="Inspect bounded implementation evidence read-only.",
                prompt="Read only. Return bounded findings and risks.",
                max_turns=8,
            ),
        ),
        permission_mode="dontAsk",
        execution_mode="noninteractive",
        supports_subagent_capability_ceiling=ObservedTriState.VERIFIED,
    )


def test_native_helper_candidate_compiler_composes_exact_cardless_parent_contract(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    spec = _spec(tmp_path)
    projection = _native_helper_projection()

    candidate = adapter.compile_native_helper_candidate_launch(spec, projection)

    assert candidate.production_armed is False
    assert candidate.runtime_ceiling_seconds == projection.runtime_ceiling_seconds
    assert dict(candidate.environment_overrides) == projection.environment()
    argv = candidate.argv
    assert "--agents" in argv
    assert argv[argv.index("--agents") + 1] == projection.cli_arguments()[-1]
    assert set(argv[argv.index("--tools") + 1].split(",")) == {
        "Agent", "Glob", "Grep", "Read"
    }
    allowed = argv[argv.index("--allowedTools") + 1].split(",")
    denied = argv[argv.index("--disallowedTools") + 1].split(",")
    assert "Agent" in allowed
    assert "Agent" not in denied
    assert {"SendMessage", "ListAgents", "TaskCreate", "TaskUpdate"} <= set(denied)
    assert "mcp__*" in denied
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings["permissions"]["allow"] == allowed
    assert settings["permissions"]["deny"][: len(denied)] == denied
    assert settings["model"] == _EXACT_MODEL
    assert settings["availableModels"] == [_EXACT_MODEL]


def test_native_helper_candidate_does_not_change_live_start_compiler(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    spec = _spec(tmp_path)
    projection = _native_helper_projection()

    candidate = adapter.compile_native_helper_candidate_launch(spec, projection)
    live = adapter.compile_launch(spec)

    assert "--agents" in candidate.argv
    assert "--agents" not in live.argv
    assert "Agent" in live.argv[live.argv.index("--disallowedTools") + 1].split(",")
    assert "Agent" not in live.argv[live.argv.index("--tools") + 1].split(",")
    assert "native_helper_projection" not in inspect.signature(adapter.start).parameters


def test_native_helper_candidate_refuses_write_parent_or_mcp_projection(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    projection = _native_helper_projection()
    with pytest.raises(ClaudeWorkerContractError, match="read-only parent"):
        adapter.compile_native_helper_candidate_launch(
            _spec(
                tmp_path,
                authorities=("READ", "WRITE_BRANCH"),
                allowed_artifact_paths=("src/allowed.py",),
            ),
            projection,
        )

    drifted = dataclasses.replace(
        projection,
        source_mcp_grant_digests=("a" * 64,),
    )
    with pytest.raises(ClaudeWorkerContractError, match="zero-MCP"):
        adapter.compile_native_helper_candidate_launch(_spec(tmp_path), drifted)


def test_native_helper_candidate_refuses_untyped_or_armed_projection(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    spec = _spec(tmp_path)
    with pytest.raises(ClaudeWorkerContractError, match="typed native-helper projection"):
        adapter.compile_native_helper_candidate_launch(spec, object())
    projection = _native_helper_projection()
    object.__setattr__(projection, "production_armed", True)
    with pytest.raises(ClaudeWorkerContractError, match="production-inert"):
        adapter.compile_native_helper_candidate_launch(spec, projection)

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

        await adapter.cancel(ref, "legacy cleanup")
        await adapter.collect_result(ref)

    asyncio.run(execute())


def test_complete_launch_attestation_is_redacted_and_principal_bound(
    tmp_path: Path,
) -> None:
    prompt = "private Claude job packet that must only be hashed"
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    spec = _workspace_and_spec(
        tmp_path,
        prompt=prompt,
        expected_worker_uid=os.geteuid(),
        expected_worker_gid=os.getegid(),
        worker_user=__import__("pwd").getpwuid(os.geteuid()).pw_name,
        secret_canary_verdict=_passing_canary(),
        require_secret_canary=True,
    )

    async def execute():
        ref = await adapter.start(spec)
        attestation = adapter.launch_attestation(ref)
        receipt = await adapter.collect_result(ref)
        return ref, attestation, receipt

    ref, attestation, receipt = asyncio.run(execute())
    document = attestation.to_dict()
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED
    assert document["schema_version"] == "mastermind.executive_launch_attestation/v1"
    assert document["executable_path"] == str(binary.resolve())
    assert len(document["permission_profile_sha256"]) == 64
    assert document["prompt_sha256"] == __import__("hashlib").sha256(
        prompt.encode("utf-8")
    ).hexdigest()
    assert document["expected_base_sha"] == spec.expected_base_sha
    assert document["observed_base_sha"] == ref.base_sha
    assert document["workspace_identity"]["path"] == str(
        Path(spec.workspace_path).resolve()
    )
    assert document["worker_identity"]["effective_uid"] == os.geteuid()
    assert document["provider_home_identity"]["path"] == str(
        (Path(spec.run_dir) / "home").resolve()
    )
    assert document["secret_canary_verdict"]["passed"] is True
    assert document["launch_nonce"] == ref.launch_nonce
    assert document["process_identity"]["pid"] == ref.pid
    assert document["process_identity"]["session_id"] == ref.session_id == ref.pid
    serialized = json.dumps(document, sort_keys=True)
    assert prompt not in serialized
    assert "structured_output" not in serialized
    assert sorted(document["environment_keys"]) == document["environment_keys"]




def test_process_ref_construction_failure_reaps_unpublished_process(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    real_inspector = adapter.inspector
    observed_pids: list[int] = []

    class MalformedPrincipalInspector:
        def boot_session_id(self) -> str:
            return real_inspector.boot_session_id()

        def inspect(self, pid: int) -> object:
            observed_pids.append(pid)
            observed = real_inspector.inspect(pid)
            return SimpleNamespace(
                start_identity=observed.start_identity,
                pgid=observed.pgid,
                session_id=observed.session_id,
                effective_uid=None,
                effective_gid=observed.effective_gid,
                real_uid=observed.real_uid,
                real_gid=observed.real_gid,
            )

    adapter.inspector = MalformedPrincipalInspector()

    async def execute() -> tuple[BaseException | None, bool]:
        error: BaseException | None = None
        leaked = False
        try:
            await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=5))
        except BaseException as exc:
            error = exc
        pid = observed_pids[0] if observed_pids else None
        if pid is not None:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                leaked = False
            else:
                leaked = True
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.sleep(0.05)
        return error, leaked

    error, leaked = asyncio.run(execute())
    assert leaked is False
    assert isinstance(error, claude_worker.ClaudeProcessIdentityError)
    assert adapter._runs == {}

def test_launch_attestation_failure_reaps_unpublished_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    real_inspector = adapter.inspector
    observed_pids: list[int] = []

    class RecordingInspector:
        def boot_session_id(self) -> str:
            return real_inspector.boot_session_id()

        def inspect(self, pid: int) -> object:
            observed_pids.append(pid)
            return real_inspector.inspect(pid)

    adapter.inspector = RecordingInspector()
    monkeypatch.setattr(
        claude_worker,
        "_path_identity",
        lambda _path: (_ for _ in ()).throw(OSError("attestation identity race")),
    )

    async def execute() -> tuple[BaseException | None, bool]:
        error: BaseException | None = None
        leaked = False
        try:
            await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=5))
        except BaseException as exc:  # inspect the exact refusal type below
            error = exc
        pid = observed_pids[0] if observed_pids else None
        if pid is not None:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                leaked = False
            else:
                leaked = True
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.sleep(0.05)
        return error, leaked

    error, leaked = asyncio.run(execute())
    assert leaked is False
    assert isinstance(error, claude_worker.ClaudeProcessIdentityError)
    assert str(error) in {
        "Claude launch attestation is unavailable",
        "unaccepted Claude launch could not be safely reaped",
    }
    assert adapter._runs == {}

def test_status_and_direct_validation_fail_closed_before_common_sandbox(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    # Keep the fixture alive long enough to exercise the RUNNING status edge;
    # an instant synthetic exit can disappear before macOS identity sampling.
    (tmp_path / "mode").write_text("delayed-success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    spec = _workspace_and_spec(tmp_path)

    async def execute() -> None:
        ref = await adapter.start(spec)
        assert await adapter.status(ref) is WorkerRunStatus.RUNNING
        await adapter.collect_result(ref)
        with pytest.raises(
            claude_worker.ClaudeWorkerNotImplementedError,
            match="common broker sandbox",
        ):
            await adapter.run_validation_argv(
                spec, ("/usr/bin/true",), timeout_seconds=1
            )

    asyncio.run(execute())


def test_direct_validation_cannot_mutate_workspace_without_common_sandbox(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    adapter = _adapter(tmp_path, binary)
    spec = _workspace_and_spec(tmp_path)
    target = Path(spec.workspace_path) / "UNAUTHORIZED_VALIDATION_WRITE.txt"

    with pytest.raises(
        claude_worker.ClaudeWorkerNotImplementedError,
        match="common broker sandbox",
    ):
        asyncio.run(
            adapter.run_validation_argv(
                spec,
                (
                    "/usr/bin/python3",
                    "-c",
                    "from pathlib import Path; "
                    "Path('UNAUTHORIZED_VALIDATION_WRITE.txt').write_text('escaped')",
                ),
                timeout_seconds=1,
            )
        )

    assert not target.exists()


def test_auth_observation_uses_principal_neutral_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    ambient = {
        "HOME": "/private/chairman-home",
        "XDG_CONFIG_HOME": "/private/xdg-config",
        "XDG_CACHE_HOME": "/private/xdg-cache",
        "CLAUDE_CONFIG_DIR": "/private/claude-config",
        "SSL_CERT_FILE": "/private/certificate",
        "ARBITRARY_AMBIENT_VARIABLE": "ambient-sentinel",
    }
    for key, value in ambient.items():
        monkeypatch.setenv(key, value)

    _adapter(tmp_path, binary).observe_auth_status(timeout_seconds=1)

    child = (tmp_path / "environment").read_text(encoding="utf-8")
    assert "HOME=/var/empty" in child
    for key, value in ambient.items():
        if key == "HOME":
            assert child.count("HOME=") == 1
            continue
        assert f"{key}=" not in child
        assert value not in child


def test_auth_discard_fields_accept_safe_nested_values_and_reject_nested_secrets(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    adapter = _adapter(tmp_path, binary)
    (tmp_path / "mode").write_text("auth-discard-nested", encoding="utf-8")
    assert adapter.observe_auth_status(timeout_seconds=1).ready is True

    (tmp_path / "mode").write_text("auth-discard-secret", encoding="utf-8")
    with pytest.raises(ClaudeWorkerContractError) as raised:
        adapter.observe_auth_status(timeout_seconds=1)
    assert "CREDENTIAL-SENTINEL" not in str(raised.value)


def test_malformed_json_never_retains_raw_payload_in_exception_chain(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    adapter = _adapter(tmp_path, binary)
    (tmp_path / "mode").write_text("auth-malformed-sentinel", encoding="utf-8")

    with pytest.raises(ClaudeWorkerContractError) as auth_raised:
        adapter.observe_auth_status(timeout_seconds=1)
    assert auth_raised.value.__cause__ is None
    assert auth_raised.value.__context__ is None
    assert "CREDENTIAL-SENTINEL" not in repr(auth_raised.value)

    (tmp_path / "mode").write_text("malformed-sentinel", encoding="utf-8")
    async def malformed() -> CollectionReceipt:
        return await adapter.collect_result(await adapter.start(_workspace_and_spec(tmp_path)))

    receipt = asyncio.run(malformed())
    assert receipt.result.status is WorkerRunStatus.INVALID_RESULT
    assert "CREDENTIAL-SENTINEL" not in str(receipt.result.error)


def test_foreground_environment_is_private_and_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "CREDENTIAL-SENTINEL")
    monkeypatch.setenv("ARBITRARY_AMBIENT_VARIABLE", "ambient-sentinel")
    adapter = _adapter(tmp_path, binary)
    spec = _workspace_and_spec(tmp_path)

    async def execute() -> CollectionReceipt:
        return await adapter.collect_result(await adapter.start(spec))

    receipt = asyncio.run(execute())
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED
    child = (tmp_path / "environment").read_text(encoding="utf-8")
    assert f"HOME={spec.run_dir / 'home'}" in child
    assert f"TMPDIR={spec.run_dir / 'tmp'}" in child
    assert "ANTHROPIC_AUTH_TOKEN" not in child
    assert "CREDENTIAL-SENTINEL" not in child
    assert "ARBITRARY_AMBIENT_VARIABLE" not in child


def test_launch_relative_timeout_and_descendant_pipe_are_bounded(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    spec = _workspace_and_spec(tmp_path, timeout_seconds=0.08)

    async def timeout_after_delay() -> CollectionReceipt:
        ref = await adapter.start(spec)
        await asyncio.sleep(0.16)
        return await asyncio.wait_for(adapter.collect_result(ref), timeout=0.5)

    assert asyncio.run(timeout_after_delay()).result.status is WorkerRunStatus.TIMED_OUT

    (tmp_path / "mode").write_text("descendant", encoding="utf-8")
    descendant_adapter = _adapter(tmp_path, binary)
    descendant_spec = _workspace_and_spec(tmp_path, run_id="run-descendant", timeout_seconds=1)

    async def collect_descendant() -> CollectionReceipt:
        return await asyncio.wait_for(
            descendant_adapter.collect_result(await descendant_adapter.start(descendant_spec)),
            timeout=0.5,
        )

    assert asyncio.run(collect_descendant()).result.status is WorkerRunStatus.INVALID_RESULT


def test_timeout_path_reconciles_residual_process_group_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    original_cleanup = ClaudeCodeWorkerAdapter._kill_residual_process_group
    cleanup_calls = 0

    async def counted_cleanup(
        current: ClaudeCodeWorkerAdapter, state: object
    ) -> bool:
        nonlocal cleanup_calls
        cleanup_calls += 1
        return await original_cleanup(current, state)  # type: ignore[arg-type]

    monkeypatch.setattr(
        ClaudeCodeWorkerAdapter, "_kill_residual_process_group", counted_cleanup
    )

    async def execute() -> CollectionReceipt:
        ref = await adapter.start(
            _workspace_and_spec(
                tmp_path, timeout_seconds=0.05, cancel_grace_seconds=0.1
            )
        )
        return await asyncio.wait_for(adapter.collect_result(ref), timeout=5)

    receipt = asyncio.run(execute())
    assert receipt.result.status is WorkerRunStatus.TIMED_OUT
    assert cleanup_calls == 1


def test_stream_violation_and_pure_refusal_never_succeed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("stream-cap", encoding="utf-8")
    monkeypatch.setattr(claude_worker, "_MAX_STDOUT_BYTES", 16)
    adapter = _adapter(tmp_path, binary)

    async def capped() -> CollectionReceipt:
        return await adapter.collect_result(await adapter.start(_workspace_and_spec(tmp_path)))

    assert asyncio.run(capped()).result.status is WorkerRunStatus.INVALID_RESULT

    monkeypatch.setattr(claude_worker, "_MAX_STDOUT_BYTES", 32 * 1024 * 1024)
    (tmp_path / "mode").write_text("refusal-pure", encoding="utf-8")
    refused_adapter = _adapter(tmp_path, binary)

    async def refused() -> CollectionReceipt:
        return await refused_adapter.collect_result(
            await refused_adapter.start(_workspace_and_spec(tmp_path, run_id="run-refusal-pure"))
        )

    assert asyncio.run(refused()).result.status is WorkerRunStatus.INVALID_RESULT


def test_cancel_identity_ambiguity_fails_closed_then_real_identity_cleans_up(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    real_inspector = adapter.inspector

    async def execute() -> CollectionReceipt:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=1))

        class AmbiguousInspector:
            def boot_session_id(self) -> str:
                return ref.boot_session_id

            def inspect(self, _pid: int) -> object:
                return object()

            def identity(self, _pid: int) -> tuple[str, int]:
                return "other", ref.pgid

        adapter.inspector = AmbiguousInspector()
        with pytest.raises(ClaudeWorkerContractError):
            await adapter.cancel(ref, "operator requested")
        adapter.inspector = real_inspector
        cancellation = await adapter.cancel(ref, "operator requested")
        assert cancellation.signal_sent is True
        return await adapter.collect_result(ref)

    assert asyncio.run(execute()).result.status is WorkerRunStatus.CANCELLED


def test_secret_stderr_and_replaced_bound_evidence_never_succeed(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("secret-stderr", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def secret_stderr() -> CollectionReceipt:
        return await adapter.collect_result(await adapter.start(_workspace_and_spec(tmp_path)))

    secret_receipt = asyncio.run(secret_stderr())
    assert secret_receipt.result.status is WorkerRunStatus.INVALID_RESULT
    assert "CREDENTIAL-SENTINEL" not in Path(secret_receipt.process_ref.stderr_path).read_text()

    for label in ("stdout_path", "stderr_path", "result_path"):
        (tmp_path / "mode").write_text("delayed-success", encoding="utf-8")
        replacing_adapter = _adapter(tmp_path, binary)
        spec = _workspace_and_spec(
            tmp_path, run_id=f"run-replace-{label}", timeout_seconds=0.7
        )
        victim = tmp_path / f"victim-{label}"
        victim.write_text("victim-data", encoding="utf-8")

        async def replace_then_collect() -> CollectionReceipt:
            ref = await replacing_adapter.start(spec)
            target = Path(getattr(ref, label))
            target.unlink()
            os.link(victim, target)
            return await replacing_adapter.collect_result(ref)

        receipt = asyncio.run(replace_then_collect())
        assert receipt.result.status is WorkerRunStatus.INVALID_RESULT
        assert victim.read_text(encoding="utf-8") == "victim-data"


def test_post_parse_git_rejection_leaves_bound_result_empty(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("git-change", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> CollectionReceipt:
        return await adapter.collect_result(await adapter.start(_workspace_and_spec(tmp_path)))

    receipt = asyncio.run(execute())
    assert receipt.result.status is WorkerRunStatus.INVALID_RESULT
    assert Path(receipt.process_ref.result_path).read_bytes() == b""


def test_nonzero_secret_stderr_precedes_ordinary_exit_failure(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("nonzero-secret", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> CollectionReceipt:
        return await adapter.collect_result(await adapter.start(_workspace_and_spec(tmp_path)))

    receipt = asyncio.run(execute())
    assert receipt.result.status is WorkerRunStatus.INVALID_RESULT
    assert Path(receipt.process_ref.stderr_path).read_bytes() == b""
    assert "CREDENTIAL-SENTINEL" not in str(receipt.result.error)

    (tmp_path / "mode").write_text("nonzero", encoding="utf-8")
    ordinary = _adapter(tmp_path, binary)

    async def ordinary_exit() -> CollectionReceipt:
        return await ordinary.collect_result(
            await ordinary.start(_workspace_and_spec(tmp_path, run_id="run-nonzero"))
        )

    assert asyncio.run(ordinary_exit()).result.status is WorkerRunStatus.FAILED


def test_concurrent_collectors_share_a_single_terminal_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("delayed-success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    writes = 0
    original_write = claude_worker._write_bound_evidence

    def counted_write(*args: object, **kwargs: object) -> str:
        nonlocal writes
        writes += 1
        return original_write(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(claude_worker, "_write_bound_evidence", counted_write)

    async def execute() -> tuple[CollectionReceipt, CollectionReceipt]:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=1))
        first, second = await asyncio.gather(
            adapter.collect_result(ref), adapter.collect_result(ref)
        )
        return first, second

    first, second = asyncio.run(execute())
    assert first is second
    assert first.result.status is WorkerRunStatus.SUCCEEDED
    assert writes == 3


def test_cancelled_collector_does_not_cancel_shared_terminal_collection(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("delayed-success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> CollectionReceipt:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=1))
        abandoned = asyncio.create_task(adapter.collect_result(ref))
        await asyncio.sleep(0.03)
        abandoned.cancel()
        with pytest.raises(asyncio.CancelledError):
            await abandoned
        return await asyncio.wait_for(adapter.collect_result(ref), timeout=1)

    assert asyncio.run(execute()).result.status is WorkerRunStatus.SUCCEEDED


def test_terminal_shared_collection_wins_same_turn_waiter_cancellation() -> None:
    async def execute() -> tuple[object, object]:
        terminal: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        sentinel = object()
        waiter = asyncio.create_task(
            ClaudeCodeWorkerAdapter._await_shared_collection(terminal)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0)
        terminal.set_result(sentinel)
        waiter.cancel()
        return await waiter, sentinel

    observed, expected = asyncio.run(execute())
    assert observed is expected


def test_cancel_accepts_os_absence_while_wait_task_settles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path)

    async def execute() -> tuple[bool, bool, bool]:
        process_wait_task: asyncio.Future[int] = (
            asyncio.get_running_loop().create_future()
        )
        state = SimpleNamespace(
            ref=object(),
            process_wait_task=process_wait_task,
            termination_lock=asyncio.Lock(),
            spec=SimpleNamespace(cancel_grace_seconds=0.001),
            cancel_reason=None,
            status=WorkerRunStatus.RUNNING,
            residual_reconciliation_task=None,
            signal_sent=False,
            terminal_cleanup_error=None,
            stream_errors=[],
        )
        leader_observations = 0

        def leader_then_absent(
            _adapter: ClaudeCodeWorkerAdapter, _ref: object
        ) -> object | None:
            nonlocal leader_observations
            leader_observations += 1
            return object() if leader_observations == 1 else None

        monkeypatch.setattr(
            ClaudeCodeWorkerAdapter, "_exact_leader_identity", leader_then_absent
        )
        monkeypatch.setattr(
            ClaudeCodeWorkerAdapter,
            "_signal_owned_group",
            lambda _adapter, _ref, _signum: True,
        )
        monkeypatch.setattr(
            ClaudeCodeWorkerAdapter,
            "_owned_residual_members",
            lambda _adapter, _ref: (),
        )

        async def no_residual(
            _adapter: ClaudeCodeWorkerAdapter, _state: object
        ) -> bool:
            return False

        monkeypatch.setattr(
            ClaudeCodeWorkerAdapter,
            "_reconcile_residual_process_group",
            no_residual,
        )
        asyncio.get_running_loop().call_later(
            0.01, process_wait_task.set_result, 0
        )

        result = await adapter._terminate(state, "operator requested")  # type: ignore[arg-type]
        assert state.cancel_reason == "operator requested"
        assert state.status is WorkerRunStatus.CANCELLING
        return result

    assert asyncio.run(execute()) == (True, False, False)


def test_cancel_racing_collection_has_one_cancelled_receipt(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> CollectionReceipt:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=1))
        collecting = asyncio.create_task(adapter.collect_result(ref))
        await asyncio.sleep(0.03)
        cancellation = await adapter.cancel(ref, "operator requested")
        receipt = await asyncio.wait_for(collecting, timeout=1)
        assert cancellation.signal_sent is True
        return receipt

    assert asyncio.run(execute()).result.status is WorkerRunStatus.CANCELLED


def test_foreign_or_permission_denied_residual_group_never_receives_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> None:
        ref = await adapter.start(_workspace_and_spec(tmp_path))
        await adapter.collect_result(ref)
        state = adapter._runs[ref.run_id]

        class ForeignInspector:
            def boot_session_id(self) -> str:
                return ref.boot_session_id

            def inspect(self, _pid: int) -> object:
                class Foreign:
                    start_identity = "foreign-start"
                    pgid = ref.pgid
                    session_id = ref.session_id
                    effective_uid = ref.effective_uid
                    effective_gid = ref.effective_gid
                    real_uid = ref.real_uid
                    real_gid = ref.real_gid
                return Foreign()

        adapter.inspector = ForeignInspector()
        signals: list[tuple[int, int]] = []
        monkeypatch.setattr(claude_worker, "_process_group_exists", lambda _pgid: True)
        monkeypatch.setattr(
            claude_worker.os, "killpg", lambda pgid, sig: signals.append((pgid, sig))
        )
        with pytest.raises(claude_worker.ClaudeProcessIdentityError):
            await adapter._kill_residual_process_group(state)
        assert signals == []

        adapter.inspector = ForeignInspector()
        monkeypatch.setattr(
            claude_worker,
            "_process_group_exists",
            lambda _pgid: (_ for _ in ()).throw(
                claude_worker.ProcessIdentityError("permission denied")
            ),
        )
        with pytest.raises(claude_worker.ClaudeProcessIdentityError):
            await adapter._kill_residual_process_group(state)

    asyncio.run(execute())


def test_residual_cleanup_uses_only_two_adjacent_ownership_censuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> None:
        ref = await adapter.start(_workspace_and_spec(tmp_path))
        await adapter.collect_result(ref)
        state = adapter._runs[ref.run_id]

        class ResidualInspector:
            def boot_session_id(self) -> str:
                return ref.boot_session_id

            def inspect(self, _pid: int) -> object:
                class Residual:
                    start_identity = "residual-start"
                    pgid = ref.pgid
                    session_id = ref.session_id
                    effective_uid = ref.effective_uid
                    effective_gid = ref.effective_gid
                    real_uid = ref.real_uid
                    real_gid = ref.real_gid

                return Residual()

        adapter.inspector = ResidualInspector()
        monkeypatch.setattr(
            ClaudeCodeWorkerAdapter,
            "_exact_leader_identity",
            lambda _adapter, _ref: None,
        )
        census_calls = 0

        def residual_census(_pgid: int) -> tuple[claude_worker._ProcessGroupMember, ...]:
            nonlocal census_calls
            census_calls += 1
            return (claude_worker._ProcessGroupMember(4242, "S"),)

        signals: list[tuple[int, signal.Signals]] = []
        monkeypatch.setattr(claude_worker, "_process_group_member_pids", residual_census)
        monkeypatch.setattr(claude_worker, "_process_group_exists", lambda _pgid: True)
        monkeypatch.setattr(
            claude_worker,
            "_wait_for_process_group_exit",
            lambda _pgid, timeout: asyncio.sleep(0, result=True),
        )
        monkeypatch.setattr(
            claude_worker.os,
            "killpg",
            lambda pgid, signum: signals.append((pgid, signum)),
        )

        assert await adapter._kill_residual_process_group(state)
        assert census_calls == 2
        assert signals == [(ref.pgid, signal.SIGKILL)]

    asyncio.run(execute())


def test_terminal_identity_ambiguity_cannot_mint_success(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> None:
        ref = await adapter.start(_workspace_and_spec(tmp_path))
        state = adapter._runs[ref.run_id]
        assert state.monitor_task is not None
        await state.monitor_task

        class ReusedInspector:
            def boot_session_id(self) -> str:
                return ref.boot_session_id

            def inspect(self, _pid: int) -> object:
                class Foreign:
                    start_identity = "reused-start"
                    pgid = ref.pgid
                    session_id = ref.session_id
                    effective_uid = ref.effective_uid
                    effective_gid = ref.effective_gid
                    real_uid = ref.real_uid
                    real_gid = ref.real_gid
                return Foreign()

        adapter.inspector = ReusedInspector()
        with pytest.raises(claude_worker.ClaudeProcessIdentityError):
            await adapter.collect_result(ref)
        assert state.receipt is None

    asyncio.run(execute())


def test_cancel_rechecks_ownership_at_the_final_signal_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> None:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=1))
        real_identity = ClaudeCodeWorkerAdapter._exact_leader_identity
        real_killpg = claude_worker.os.killpg
        observations = 0

        def changes_after_early_proof(
            _adapter: ClaudeCodeWorkerAdapter, observed_ref: object
        ) -> object | None:
            nonlocal observations
            observations += 1
            if observations == 1:
                return real_identity(_adapter, observed_ref)  # type: ignore[arg-type]
            raise claude_worker.ClaudeProcessIdentityError("identity changed")

        signals: list[tuple[int, int]] = []
        monkeypatch.setattr(
            ClaudeCodeWorkerAdapter, "_exact_leader_identity", changes_after_early_proof
        )
        monkeypatch.setattr(
            claude_worker.os, "killpg", lambda pgid, sig: signals.append((pgid, sig))
        )
        with pytest.raises(claude_worker.ClaudeProcessIdentityError):
            await adapter.cancel(ref, "operator requested")
        assert signals == []

        monkeypatch.setattr(ClaudeCodeWorkerAdapter, "_exact_leader_identity", real_identity)
        monkeypatch.setattr(claude_worker.os, "killpg", real_killpg)
        await adapter.cancel(ref, "operator requested")
        assert (await adapter.collect_result(ref)).result.status is WorkerRunStatus.CANCELLED

    asyncio.run(execute())



def test_local_task_settlement_consumes_failed_owned_task_exceptions(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)

    async def fail_now() -> int:
        raise RuntimeError("already failed")

    async def fail_during_wait() -> None:
        await asyncio.sleep(0.01)
        raise ValueError("failed during wait")

    async def execute() -> tuple[bool, bool, tuple[str, ...], list[dict[str, object]]]:
        loop = asyncio.get_running_loop()
        reported: list[dict[str, object]] = []
        old_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: reported.append(context))
        try:
            first = asyncio.create_task(fail_now())
            second = asyncio.create_task(fail_during_wait())
            await asyncio.sleep(0)
            state = SimpleNamespace(
                process_wait_task=first,
                stdout_task=second,
                stderr_task=None,
                monitor_task=None,
                stream_errors=[],
            )
            await adapter._settle_or_cancel_local_tasks(state)  # type: ignore[arg-type]
            await asyncio.sleep(0)
            return first.done(), second.done(), tuple(state.stream_errors), reported
        finally:
            loop.set_exception_handler(old_handler)

    first_done, second_done, errors, reported = asyncio.run(execute())
    assert first_done and second_done
    assert "local task failed: RuntimeError" in errors
    assert "local task failed: ValueError" in errors
    assert reported == []


def test_monitor_identity_failure_bounds_owned_tasks_and_records_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> tuple[bool, bool, bool, bool, str | None, tuple[str, ...]]:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=5))
        state = adapter._runs[ref.run_id]
        assert state.monitor_task is not None

        async def fail_terminate(
            _adapter: ClaudeCodeWorkerAdapter, _state: object, _reason: str | None
        ) -> tuple[bool, bool, bool]:
            raise claude_worker.ClaudeProcessIdentityError("synthetic identity uncertainty")

        monkeypatch.setattr(ClaudeCodeWorkerAdapter, "_terminate", fail_terminate)
        state.violation.set()
        try:
            with pytest.raises(
                claude_worker.ClaudeProcessIdentityError,
                match="synthetic identity uncertainty",
            ):
                await asyncio.wait_for(asyncio.shield(state.monitor_task), timeout=1)
            return (
                state.process_wait_task.done(),
                bool(state.stdout_task and state.stdout_task.done()),
                bool(state.stderr_task and state.stderr_task.done()),
                state.monitor_task.done(),
                state.finished_at,
                tuple(state.stream_errors),
            )
        finally:
            monkeypatch.undo()
            try:
                os.killpg(ref.pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(state.process.wait(), timeout=1)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass

    settled = asyncio.run(execute())
    assert settled[:4] == (True, True, True, True)
    assert settled[4] is not None
    assert any("identity" in error.lower() for error in settled[5])



def test_monitor_failure_stays_bounded_when_owned_task_suppresses_cancel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> bool:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=5))
        state = adapter._runs[ref.run_id]
        assert state.monitor_task is not None
        release = asyncio.Event()
        original_stdout = state.stdout_task
        if original_stdout is not None:
            original_stdout.cancel()
            await asyncio.gather(original_stdout, return_exceptions=True)

        async def stubborn_owned_task() -> None:
            while not release.is_set():
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    continue

        state.stdout_task = asyncio.create_task(stubborn_owned_task())

        async def fail_terminate(
            _adapter: ClaudeCodeWorkerAdapter, _state: object, _reason: str | None
        ) -> tuple[bool, bool, bool]:
            raise claude_worker.ClaudeProcessIdentityError("synthetic bounded failure")

        monkeypatch.setattr(ClaudeCodeWorkerAdapter, "_terminate", fail_terminate)
        monkeypatch.setattr(claude_worker, "_LOCAL_TASK_SETTLEMENT_SECONDS", 0.01)
        state.violation.set()
        bounded = True
        try:
            try:
                await asyncio.wait_for(asyncio.shield(state.monitor_task), timeout=0.1)
            except claude_worker.ClaudeProcessIdentityError:
                bounded = True
            except asyncio.TimeoutError:
                bounded = False
        finally:
            release.set()
            if state.stdout_task is not None and not state.stdout_task.done():
                state.stdout_task.cancel()
            await asyncio.gather(state.stdout_task, return_exceptions=True)
            if state.monitor_task is not None:
                await asyncio.gather(state.monitor_task, return_exceptions=True)
            monkeypatch.undo()
            try:
                os.killpg(ref.pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(state.process.wait(), timeout=1)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass
        return bounded

    assert asyncio.run(execute()) is True


def test_cancel_signal_refusal_stops_monitor_reentry_and_local_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)
    real_killpg = claude_worker.os.killpg
    signal_calls: list[tuple[int, int]] = []

    def refuse_signal(pgid: int, signum: int) -> None:
        signal_calls.append((pgid, signum))
        raise PermissionError("synthetic signal refusal")

    async def execute() -> tuple[BaseException | None, int, bool, bool, bool, bool, str | None]:
        ref = await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=5))
        state = adapter._runs[ref.run_id]
        monkeypatch.setattr(claude_worker.os, "killpg", refuse_signal)
        error: BaseException | None = None
        try:
            try:
                await adapter.cancel(ref, "operator requested")
            except BaseException as exc:
                error = exc
            state.violation.set()
            await asyncio.sleep(0.05)
            return (
                error,
                len(signal_calls),
                bool(state.monitor_task and state.monitor_task.done()),
                state.process_wait_task.done(),
                bool(state.stdout_task and state.stdout_task.done()),
                bool(state.stderr_task and state.stderr_task.done()),
                state.finished_at,
            )
        finally:
            monkeypatch.setattr(claude_worker.os, "killpg", real_killpg)
            try:
                real_killpg(ref.pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(state.process.wait(), timeout=1)
            except (asyncio.TimeoutError, ProcessLookupError):
                pass

    observed = asyncio.run(execute())
    assert isinstance(observed[0], claude_worker.ClaudeProcessIdentityError)
    assert observed[1:6] == (1, True, True, True, True)
    assert observed[6] is not None


def test_unprovable_launch_cleanup_is_bounded_and_closes_evidence(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep-short", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    refusal_started: list[float] = []

    class AmbiguousInspector:
        def boot_session_id(self) -> str:
            return "unknown"

        def inspect(self, _pid: int) -> object:
            if not refusal_started:
                refusal_started.append(time.monotonic())
            raise claude_worker.ProcessIdentityError("unavailable")

    adapter.inspector = AmbiguousInspector()

    async def execute() -> None:
        with pytest.raises(claude_worker.ClaudeProcessIdentityError):
            await asyncio.wait_for(
                adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=1)),
                timeout=5,
            )
        assert refusal_started
        assert time.monotonic() - refusal_started[0] < 1.0
        await asyncio.sleep(0.25)

    asyncio.run(execute())


def test_abandoned_failed_collection_retrieves_shared_task_exception(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> None:
        ref = await adapter.start(_workspace_and_spec(tmp_path))
        state = adapter._runs[ref.run_id]
        assert state.monitor_task is not None
        await state.monitor_task
        loop = asyncio.get_running_loop()
        reported: list[dict[str, object]] = []
        old_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: reported.append(context))
        try:
            async def fail_monitor() -> None:
                await asyncio.sleep(0.02)

            state.monitor_task = asyncio.create_task(fail_monitor())

            class ReusedInspector:
                def boot_session_id(self) -> str:
                    return ref.boot_session_id

                def inspect(self, _pid: int) -> object:
                    class Foreign:
                        start_identity = "reused-start"
                        pgid = ref.pgid
                        session_id = ref.session_id
                        effective_uid = ref.effective_uid
                        effective_gid = ref.effective_gid
                        real_uid = ref.real_uid
                        real_gid = ref.real_gid
                    return Foreign()

            adapter.inspector = ReusedInspector()
            waiter = asyncio.create_task(adapter.collect_result(ref))
            await asyncio.sleep(0)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
            await asyncio.sleep(0.05)
            assert not reported
            with pytest.raises(claude_worker.ClaudeProcessIdentityError):
                await adapter.collect_result(ref)
        finally:
            loop.set_exception_handler(old_handler)

    asyncio.run(execute())


def test_zombie_only_or_unreadable_residual_census_never_signals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    adapter = _adapter(tmp_path, binary)

    async def execute() -> None:
        ref = await adapter.start(_workspace_and_spec(tmp_path))
        await adapter.collect_result(ref)
        state = adapter._runs[ref.run_id]
        signals: list[tuple[int, int]] = []
        monkeypatch.setattr(
            claude_worker.os, "killpg", lambda pgid, sig: signals.append((pgid, sig))
        )
        monkeypatch.setattr(
            claude_worker,
            "_process_group_member_pids",
            lambda _pgid: (claude_worker._ProcessGroupMember(99, "Z"),),
        )
        monkeypatch.setattr(claude_worker, "_process_group_exists", lambda _pgid: True)
        assert not await adapter._kill_residual_process_group(state)
        assert signals == []

        monkeypatch.setattr(
            claude_worker,
            "_process_group_member_pids",
            lambda _pgid: (_ for _ in ()).throw(
                claude_worker.ClaudeProcessIdentityError("census refused")
            ),
        )
        with pytest.raises(claude_worker.ClaudeProcessIdentityError):
            await adapter._kill_residual_process_group(state)
        assert signals == []

    asyncio.run(execute())


def test_process_group_census_scopes_ps_to_exact_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    real_popen = subprocess.Popen
    observed_argv: list[tuple[str, ...]] = []

    def exact_group_popen(
        argv: object, **kwargs: object
    ) -> subprocess.Popen[bytes]:
        observed_argv.append(tuple(argv))  # type: ignore[arg-type]
        return real_popen(
            ("/usr/bin/printf", "42 99 S\n"),
            **kwargs,
        )

    monkeypatch.setattr(claude_worker.subprocess, "Popen", exact_group_popen)

    assert claude_worker._process_group_member_pids(99) == (
        claude_worker._ProcessGroupMember(42, "S"),
    )
    assert observed_argv == [
        ("/bin/ps", "-g", "99", "-o", "pid=,pgid=,state=")
    ]


def test_process_group_census_accepts_empty_exact_group_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    real_popen = subprocess.Popen

    def empty_group_popen(
        _argv: object, **kwargs: object
    ) -> subprocess.Popen[bytes]:
        return real_popen(("/usr/bin/false",), **kwargs)

    monkeypatch.setattr(claude_worker.subprocess, "Popen", empty_group_popen)
    monkeypatch.setattr(
        claude_worker, "_process_group_exists", lambda _pgid: False
    )

    assert claude_worker._process_group_member_pids(99) == ()


def test_process_group_census_refuses_empty_error_for_existing_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    real_popen = subprocess.Popen

    def failed_group_query(
        _argv: object, **kwargs: object
    ) -> subprocess.Popen[bytes]:
        return real_popen(("/usr/bin/false",), **kwargs)

    monkeypatch.setattr(claude_worker.subprocess, "Popen", failed_group_query)
    monkeypatch.setattr(
        claude_worker, "_process_group_exists", lambda _pgid: True
    )

    with pytest.raises(claude_worker.ClaudeProcessIdentityError):
        claude_worker._process_group_member_pids(99)


def test_process_group_census_accepts_darwin_state_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen

    def flagged_state_popen(
        _argv: object, **kwargs: object
    ) -> subprocess.Popen[bytes]:
        return real_popen(
            ("/usr/bin/printf", "42 99 SN\\n43 99 Z+\\n"),
            **kwargs,
        )

    monkeypatch.setattr(claude_worker.subprocess, "Popen", flagged_state_popen)

    assert claude_worker._process_group_member_pids(99) == (
        claude_worker._ProcessGroupMember(42, "S"),
        claude_worker._ProcessGroupMember(43, "Z"),
    )


def test_exited_launch_pid_reuse_never_signals_foreign_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    adapter = _adapter(tmp_path, binary)

    class ReusedInspector:
        def boot_session_id(self) -> str:
            return "boot-reused"

        def inspect(self, _pid: int) -> object:
            class ForeignSession:
                start_identity = "foreign-reused-start"
                pgid = 4242
                session_id = 4242
                effective_uid = os.geteuid()
                effective_gid = os.getegid()
                real_uid = os.getuid()
                real_gid = os.getgid()

            return ForeignSession()

    class ReapedProcess:
        pid = 4242

        def __init__(self) -> None:
            self.returncode_reads = 0

        @property
        def returncode(self) -> int | None:
            self.returncode_reads += 1
            return None if self.returncode_reads == 1 else 0

    adapter.inspector = ReusedInspector()
    process = ReapedProcess()
    signals: list[tuple[int, signal.Signals]] = []
    monkeypatch.setattr(
        claude_worker.os,
        "killpg",
        lambda pgid, signum: signals.append((pgid, signum)),
    )

    outcome = asyncio.run(
        adapter._safe_launch_failure_cleanup(process)  # type: ignore[arg-type]
    )

    assert outcome is claude_worker._LaunchCleanupOutcome.ABSENT
    assert signals == []
    assert process.returncode_reads >= 2

# ---------------------------------------------------------------------------
# Discriminators for the trusted managed-model-policy observation seam and the
# fail-closed review-enforced Claude argv/permission contract.  These tests
# must fail RED against an untouched copy of the supplied preimage and turn
# GREEN only after the corrections in control_plane/claude_worker.py bind the
# observer and the closed review-enforced argv/policy into the canonical
# LaunchAttestation.
# ---------------------------------------------------------------------------

import hashlib

_PROTECTED_PATH_CLASSES = (
    ".git/**",
    ".claude/**",
    ".codex/**",
    ".env",
    ".env.*",
    "config.toml",
)
_PROTECTED_SANDBOX_REQUEST = {
    "enabled": True,
    "allowUnsandboxedCommands": False,
    "failIfUnavailable": True,
    "blockReadsOutsideWorkingDirectories": True,
    "network": {
        "allowedDomains": [],
        "strictAllowlist": True,
    },
}
_FILE_TOOLS = ("Edit", "Glob", "Grep", "Read", "Write")
_VALID_GENERATION = 1
_INVALID_GENERATIONS = (
    ("bool-true", True),
    ("bool-false", False),
    ("zero", 0),
    ("negative", -1),
    ("above-2**63-1", 2**63),
    ("numeric-string", "1"),
    ("float", 1.0),
)


class _FakeManagedPolicyObserver:
    """Frozen consumer-side seam; tests may not depend on any producer."""

    def __init__(
        self,
        *,
        exact_model: str,
        binary_sha256: str,
        binary_version: str,
        generation: object,
        allow_alternate_models: tuple[str, ...] = (),
        fallback_models: tuple[str, ...] = (),
    ) -> None:
        self.exact_model = exact_model
        self.binary_sha256 = binary_sha256
        self.binary_version = binary_version
        self.generation = generation
        self.allow_alternate_models = tuple(allow_alternate_models)
        self.fallback_models = tuple(fallback_models)
        self.calls = 0

    def observe(self) -> "ManagedModelPolicyObservation":
        from control_plane.claude_worker import ManagedModelPolicyObservation

        self.calls += 1
        return ManagedModelPolicyObservation(
            exact_model=self.exact_model,
            binary_sha256=self.binary_sha256,
            binary_version=self.binary_version,
            generation=self.generation,
            allow_alternate_models=self.allow_alternate_models,
            fallback_models=self.fallback_models,
        )


def _observation_for(binary: Path, **changes: object) -> object:
    from control_plane.claude_worker import ManagedModelPolicyObservation

    values: dict[str, object] = {
        "exact_model": _EXACT_MODEL,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "binary_version": _FIXTURE_VERSION,
        "generation": _VALID_GENERATION,
    }
    values.update(changes)
    return ManagedModelPolicyObservation(**values)  # type: ignore[arg-type]


def _observer_for(binary: Path, *, generation: object = _VALID_GENERATION):
    """Describe the exact already-created fixture binary.

    This deliberately re-reads the caller's binary instead of calling
    ``_fixture_claude_binary`` again: rewriting the already-attested executable
    would change its ``mtime_ns`` and reset the requested lifecycle ``mode``.
    """

    return _FakeManagedPolicyObserver(
        exact_model=_EXACT_MODEL,
        binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        binary_version=_FIXTURE_VERSION,
        generation=generation,
    )


def _sequence_observer(binary: Path, *later: object):
    """One valid initial observation, then scripted later results.

    The seam must succeed at construction and only then raise or drift, so a
    pre-spawn discriminator can actually reach the pre-spawn edge.
    """

    class _SequenceManagedPolicyObserver:
        def __init__(self) -> None:
            self.calls = 0
            self._pending: list[object] = [
                _observation_for(binary),
                *later,
            ]

        def observe(self) -> object:
            self.calls += 1
            if not self._pending:
                raise claude_worker.ClaudeWorkerContractError(
                    "managed policy observation is unavailable"
                )
            item = self._pending.pop(0)
            if isinstance(item, BaseException):
                raise item
            return item

    return _SequenceManagedPolicyObserver()


def _refuse_spawn(monkeypatch: pytest.MonkeyPatch) -> list[object]:

    """Count every attempted subprocess creation and make it impossible."""

    attempted: list[object] = []

    def record(*args: object, **kwargs: object) -> object:
        attempted.append(args)
        raise AssertionError("no subprocess may be created for a refused launch")

    monkeypatch.setattr(claude_worker.asyncio, "create_subprocess_exec", record)
    return attempted


def _count_cleanups(monkeypatch: pytest.MonkeyPatch, adapter: object) -> list[object]:
    """Count the bounded launch-failure cleanups the adapter still performs."""

    performed: list[object] = []
    original = type(adapter)._safe_launch_failure_cleanup

    async def counting(self: object, process: object) -> object:
        performed.append(process)
        return await original(self, process)

    monkeypatch.setattr(type(adapter), "_safe_launch_failure_cleanup", counting)
    return performed


def _claude_settings(invocation: object) -> dict:
    argv = invocation.argv  # type: ignore[attr-defined]
    return json.loads(argv[argv.index("--settings") + 1])


def test_claude_code_descriptor_remains_inert_and_unknown_aliases_fail_closed() -> None:
    descriptor = adapter_descriptor("claude-code")
    assert descriptor.implemented is False
    assert descriptor.implementation == (
        "control_plane.claude_worker.ClaudeCodeWorkerAdapter"
    )
    for alias in ("claude", "claude-cli", "claude-code-v1", "claude-compatible"):
        with pytest.raises(ValueError, match="unknown worker adapter"):
            adapter_descriptor(alias)
    subscription = adapter_descriptor("claude-compatible-subscription")
    assert subscription.adapter_id == "claude-compatible-subscription"
    assert subscription.implemented is False
    assert subscription.adapter_id != descriptor.adapter_id


def test_managed_policy_observer_is_required_at_construction(tmp_path: Path) -> None:
    with pytest.raises(
        ClaudeWorkerContractError, match="managed model policy observer"
    ):
        ClaudeCodeWorkerAdapter(
            _fixture_claude_binary(tmp_path),
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
        )


def test_observer_that_is_not_the_typed_seam_refuses_construction(
    tmp_path: Path,
) -> None:
    class NotAnObserver:
        pass

    with pytest.raises(
        ClaudeWorkerContractError, match="does not satisfy the frozen consumer seam"
    ):
        ClaudeCodeWorkerAdapter(
            _fixture_claude_binary(tmp_path),
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=NotAnObserver(),  # type: ignore[arg-type]
        )


def test_wrong_observation_return_type_refuses_construction(tmp_path: Path) -> None:
    """A structurally valid seam returning a non-seam value must fail closed.

    The frozen pre-correction behavior read ``observation.generation`` before
    any type check, so this returned ``AttributeError`` instead of the typed
    contract refusal. It is retained as a RED control for that boundary.
    """

    class WrongReturnObserver:
        def __init__(self) -> None:
            self.calls = 0

        def observe(self) -> ManagedModelPolicyObservation:
            self.calls += 1
            return object()  # type: ignore[return-value]

    observer = WrongReturnObserver()
    with pytest.raises(
        ClaudeWorkerContractError, match="not a typed seam value"
    ) as refused:
        ClaudeCodeWorkerAdapter(
            _fixture_claude_binary(tmp_path),
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=observer,  # type: ignore[arg-type]
        )
    assert type(refused.value) is ClaudeWorkerContractError
    assert not isinstance(refused.value, AttributeError)
    assert "has no attribute" not in str(refused.value)
    assert observer.calls == 1


def test_wrong_exact_model_in_observer_refuses_construction(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    observer = _observer_for(binary)
    observer.exact_model = "claude-sonnet-4-6"
    with pytest.raises(ClaudeWorkerContractError, match="exact configured model"):
        ClaudeCodeWorkerAdapter(
            binary,
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=observer,
        )


def test_wrong_binary_sha256_in_observer_refuses_construction(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    observer = _observer_for(binary)
    observer.binary_sha256 = "f" * 64
    with pytest.raises(ClaudeWorkerContractError, match="binary identity"):
        ClaudeCodeWorkerAdapter(
            binary,
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=observer,
        )


def test_wrong_binary_version_in_observer_refuses_construction(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    observer = _observer_for(binary)
    observer.binary_version = "9.9.999"
    with pytest.raises(ClaudeWorkerContractError, match="binary version"):
        ClaudeCodeWorkerAdapter(
            binary,
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=observer,
        )


def test_observer_alternate_model_allowed_refuses_construction(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    observer = _observer_for(binary)
    observer.allow_alternate_models = (_EXACT_MODEL,)
    with pytest.raises(ClaudeWorkerContractError, match="alternate"):
        ClaudeCodeWorkerAdapter(
            binary,
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=observer,
        )


def test_observer_fallback_present_refuses_construction(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    observer = _observer_for(binary)
    observer.fallback_models = ("claude-sonnet-4-6",)
    with pytest.raises(ClaudeWorkerContractError, match="fallback"):
        ClaudeCodeWorkerAdapter(
            binary,
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=observer,
        )


@pytest.mark.parametrize(
    "label, generation",
    _INVALID_GENERATIONS,
    ids=[label for label, _value in _INVALID_GENERATIONS],
)
def test_non_canonical_generation_refuses_construction(
    tmp_path: Path, label: str, generation: object
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    observer = _observer_for(binary, generation=generation)
    with pytest.raises(ClaudeWorkerContractError, match="generation"):
        ClaudeCodeWorkerAdapter(
            binary,
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=observer,
        )
    assert observer.calls == 1


def test_valid_generation_is_canonical_and_bounded(tmp_path: Path) -> None:
    binary = _fixture_claude_binary(tmp_path)
    for generation in (1, 2**63 - 1):
        observer = _observer_for(binary, generation=generation)
        adapter = ClaudeCodeWorkerAdapter(
            binary,
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=observer,
        )
        assert adapter.managed_policy_generation == generation
        assert type(adapter.managed_policy_generation) is int
        assert adapter.managed_policy_generation is not True


def test_observer_generation_drift_between_construction_and_pre_spawn_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    # Construction observes once; the mandatory pre-spawn re-observation is the
    # second call and the only place this drift can be caught.
    sequence = _sequence_observer(
        binary,
        _observation_for(binary, generation=2),
    )
    adapter = ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=sequence,
    )
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    spec = _workspace_and_spec(tmp_path)
    attempted = _refuse_spawn(monkeypatch)

    async def execute() -> None:
        with pytest.raises(ClaudeWorkerContractError, match="generation"):
            await adapter.start(spec)

    asyncio.run(execute())
    assert sequence.calls == 2
    assert attempted == []


def test_wrong_observation_return_type_refuses_pre_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mandatory pre-spawn re-observation must also fail closed on a wrong return."""

    binary = _fixture_claude_binary(tmp_path)
    # Construction observes the valid seam value once; the second, pre-spawn
    # call is the only place this wrong return can reach the spawn edge.
    sequence = _sequence_observer(binary, object())
    adapter = ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=sequence,  # type: ignore[arg-type]
    )
    assert sequence.calls == 1
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    spec = _workspace_and_spec(tmp_path)
    attempted = _refuse_spawn(monkeypatch)
    cleanups = _count_cleanups(monkeypatch, adapter)

    async def execute() -> None:
        with pytest.raises(
            ClaudeWorkerContractError, match="not a typed seam value"
        ) as refused:
            await adapter.start(spec)

    asyncio.run(execute())
    assert sequence.calls == 2
    assert attempted == []
    assert cleanups == []
    assert adapter._runs == {}


def test_observer_absence_during_pre_spawn_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    # The seam succeeds exactly once at construction and only then disappears.
    sequence = _sequence_observer(binary)
    adapter = ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=sequence,
    )
    assert sequence.calls == 1
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    spec = _workspace_and_spec(tmp_path)
    attempted = _refuse_spawn(monkeypatch)

    async def execute() -> None:
        with pytest.raises(ClaudeWorkerContractError, match="unavailable"):
            await adapter.start(spec)

    asyncio.run(execute())
    assert sequence.calls == 2
    assert attempted == []


def test_observer_model_drift_pre_spawn_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    sequence = _sequence_observer(
        binary,
        _observation_for(binary, exact_model="claude-sonnet-4-6"),
    )
    adapter = ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=sequence,
    )
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    attempted = _refuse_spawn(monkeypatch)

    async def execute() -> None:
        with pytest.raises(ClaudeWorkerContractError, match="pre-spawn"):
            await adapter.start(_workspace_and_spec(tmp_path))

    asyncio.run(execute())
    assert sequence.calls == 2
    assert attempted == []


def test_observer_binary_identity_drift_pre_spawn_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    sequence = _sequence_observer(binary, _observation_for(binary, binary_sha256="e" * 64))
    adapter = ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=sequence,
    )
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    attempted = _refuse_spawn(monkeypatch)

    async def execute() -> None:
        with pytest.raises(ClaudeWorkerContractError, match="identity"):
            await adapter.start(_workspace_and_spec(tmp_path))

    asyncio.run(execute())
    assert sequence.calls == 2
    assert attempted == []


def test_observer_alternate_and_fallback_drift_pre_spawn_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    for index, drifted in enumerate(
        (
            _observation_for(binary, allow_alternate_models=("claude-sonnet-4-6",)),
            _observation_for(binary, fallback_models=("claude-sonnet-4-6",)),
        )
    ):
        sequence = _sequence_observer(binary, drifted)
        adapter = ClaudeCodeWorkerAdapter(
            binary,
            allowed_versions=frozenset({_FIXTURE_VERSION}),
            exact_model=_EXACT_MODEL,
            max_turns=4,
            managed_policy_observer=sequence,
        )
        (tmp_path / "mode").write_text("success", encoding="utf-8")
        attempted = _refuse_spawn(monkeypatch)
        # Each iteration needs its own run/workspace pair, or the second one
        # fails in workspace validation instead of reaching the pre-spawn edge.
        run_id = f"run-drift-{index}"

        async def execute() -> None:
            await adapter.start(_workspace_and_spec(tmp_path, run_id=run_id))

        with pytest.raises(ClaudeWorkerContractError):
            asyncio.run(execute())
        assert sequence.calls == 2
        assert attempted == []


def test_compile_launch_argv_contains_restricted_and_closed_model_policy(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    invocation = adapter.compile_launch(_spec(tmp_path))
    argv = invocation.argv
    assert "--restricted" in argv
    assert "--safe-mode" in argv
    assert ("--model", _EXACT_MODEL) == (
        argv[argv.index("--model") : argv.index("--model") + 2]
    )
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings["model"] == _EXACT_MODEL
    assert settings["fallbackModel"] == []
    assert settings["availableModels"] == [_EXACT_MODEL]
    assert settings["enforceAvailableModels"] is True
    assert settings["switchModelsOnFlag"] is False
    # The serialized request, not an attestation-only object, carries the fences.
    assert adapter.validate_settings(settings) is None
    assert settings["sandbox"] == _PROTECTED_SANDBOX_REQUEST


def test_settings_request_denies_protected_paths_for_enabled_file_tools(
    tmp_path: Path,
) -> None:
    for authorities in (("READ",), ("READ", "WRITE_BRANCH"), ("READ", "RUN_TESTS")):
        adapter = _adapter(tmp_path)
        spec = _spec(
            tmp_path,
            authorities=authorities,
            allowed_artifact_paths=("src/a.py",),
        )
        settings = _claude_settings(adapter.compile_launch(spec))
        deny = settings["permissions"]["deny"]
        enabled_file_tools = {
            rule.split("(", 1)[0] for rule in settings["permissions"]["allow"]
        } & set(_FILE_TOOLS)
        assert enabled_file_tools
        for tool in sorted(enabled_file_tools):
            for protected in _PROTECTED_PATH_CLASSES:
                assert f"{tool}({protected})" in deny, (
                    f"{tool} does not deny {protected} in the --settings request"
                )
        for protected in _PROTECTED_PATH_CLASSES:
            for rule in deny:
                if rule.endswith(f"({protected})"):
                    assert rule.split("(", 1)[0] in enabled_file_tools
        adapter.validate_settings(settings)


def test_permission_profile_reflects_the_emitted_settings_request(
    tmp_path: Path,
) -> None:
    adapter = _adapter(tmp_path)
    spec = _spec(tmp_path)
    settings = _claude_settings(adapter.compile_launch(spec))
    profile = adapter.permission_profile(spec)
    assert profile["requested_settings"] == settings
    assert profile["file_tool_denies"] == [
        rule for rule in settings["permissions"]["deny"]
        if rule not in profile["forbidden_tools"]
    ]
    assert set(profile["file_tool_denies"]) == {
        f"{tool}({protected})"
        for tool in ("Glob", "Grep", "Read")
        for protected in _PROTECTED_PATH_CLASSES
    }
    assert profile["subprocess_sandbox"] == settings["sandbox"]
    assert profile["subprocess_sandbox"] == _PROTECTED_SANDBOX_REQUEST


@pytest.mark.parametrize(
    "mutator",
    [
        pytest.param(lambda s: s.pop("model"), id="delete-model"),
        pytest.param(
            lambda s: s.__setitem__("model", "claude-sonnet-4-6"), id="widen-model"
        ),
        pytest.param(lambda s: s.pop("fallbackModel"), id="delete-fallbackModel"),
        pytest.param(
            lambda s: s.__setitem__("fallbackModel", ["claude-sonnet-4-6"]),
            id="widen-fallbackModel",
        ),
        pytest.param(lambda s: s.pop("availableModels"), id="delete-availableModels"),
        pytest.param(
            lambda s: s.__setitem__("availableModels", ["claude-sonnet-4-6"]),
            id="widen-availableModels",
        ),
        pytest.param(
            lambda s: s.__setitem__("enforceAvailableModels", False),
            id="disable-enforceAvailableModels",
        ),
        pytest.param(
            lambda s: s.__setitem__("switchModelsOnFlag", True),
            id="enable-switchModelsOnFlag",
        ),
        pytest.param(
            lambda s: s["permissions"]["deny"].remove("Read(.git/**)"),
            id="delete-git-deny",
        ),
        pytest.param(
            lambda s: s["permissions"]["deny"].remove("Read(.claude/**)"),
            id="delete-claude-deny",
        ),
        pytest.param(
            lambda s: s["permissions"]["deny"].remove("Read(.codex/**)"),
            id="delete-codex-deny",
        ),
        pytest.param(
            lambda s: s["permissions"]["deny"].remove("Read(.env)"),
            id="delete-env-deny",
        ),
        pytest.param(
            lambda s: s["permissions"]["deny"].remove("Read(.env.*)"),
            id="delete-env-star-deny",
        ),
        pytest.param(
            lambda s: s["permissions"]["deny"].remove("Read(config.toml)"),
            id="delete-config-toml-deny",
        ),
        pytest.param(
            lambda s: s["permissions"]["deny"].remove("Grep(config.toml)"),
            id="delete-one-file-tool-deny",
        ),
        pytest.param(
            lambda s: s["permissions"]["deny"].__setitem__(
                s["permissions"]["deny"].index("Read(.git/**)"), "Read(.git/HEAD)"
            ),
            id="narrow-git-deny",
        ),
        pytest.param(
            lambda s: s["permissions"]["deny"].__setitem__(
                s["permissions"]["deny"].index("Read(.env.*)"), "Read(.env.example)"
            ),
            id="narrow-env-star-deny",
        ),
        pytest.param(
            lambda s: s["sandbox"].pop("failIfUnavailable"),
            id="delete-failIfUnavailable",
        ),
        pytest.param(
            lambda s: s["sandbox"].__setitem__("failIfUnavailable", False),
            id="widen-failIfUnavailable",
        ),
        pytest.param(
            lambda s: s["sandbox"].__setitem__("allowUnsandboxedCommands", True),
            id="allow-unsandboxed-commands",
        ),
        pytest.param(
            lambda s: s["sandbox"].__setitem__(
                "blockReadsOutsideWorkingDirectories", False
            ),
            id="allow-reads-outside-workdirs",
        ),
        pytest.param(
            lambda s: s["sandbox"].__setitem__("enabled", False), id="disable-sandbox"
        ),
        pytest.param(
            lambda s: s["sandbox"].pop("network"), id="delete-network-allowlist"
        ),
        pytest.param(
            lambda s: s["sandbox"]["network"]["allowedDomains"].append("example.invalid"),
            id="allow-network-domain",
        ),
        pytest.param(
            lambda s: s["sandbox"]["network"].__setitem__("strictAllowlist", False),
            id="drop-strict-network-allowlist",
        ),
    ],
)
def test_any_single_emitted_fence_mutation_refuses(
    tmp_path: Path, mutator, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path)
    spec = _spec(tmp_path)
    settings = _claude_settings(adapter.compile_launch(spec))
    baseline_digest = adapter.permission_profile_digest(spec)
    mutator(settings)
    attempted = _refuse_spawn(monkeypatch)
    with pytest.raises(
        ClaudeWorkerContractError, match="(model fence|deny fence|sandbox fence)"
    ):
        adapter.validate_settings(settings)
    assert attempted == []
    # The attested contract is bound to the exact emitted settings, so a mutated
    # request can never hash to the launch attestation the review recorded.
    mutated_profile = dict(
        adapter.permission_profile(spec), requested_settings=settings
    )
    assert (
        adapter.permission_profile_digest(spec, profile=mutated_profile)
        != baseline_digest
    )
    assert adapter.permission_profile_digest(spec) == baseline_digest


def test_permission_profile_digest_binds_complete_policy_and_managed_observation(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    observer = _observer_for(binary)
    adapter = ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=observer,
    )
    spec = _spec(tmp_path)
    profile = adapter.permission_profile(spec)
    digest_a = adapter.permission_profile_digest(spec)
    digest_b = adapter.permission_profile_digest(spec)
    assert digest_a == digest_b
    assert digest_a == claude_worker._canonical_sha256(profile)
    # A mutable fake cannot retroactively move an already frozen configuration
    # digest; only a fresh accepted observation at the spawn edge may agree.
    # Only the generation mutates, so the pre-spawn edge below is reached by
    # the generation drift and not by an earlier model/identity refusal.
    observer.generation = 2
    assert adapter.permission_profile_digest(spec) == digest_a
    assert adapter.managed_policy_observation.generation == 1
    # ... and the mandatory pre-spawn re-observation refuses exactly that drift.
    (tmp_path / "mode").write_text("success", encoding="utf-8")

    async def execute() -> None:
        await adapter.start(_workspace_and_spec(tmp_path))

    with pytest.raises(ClaudeWorkerContractError, match="generation"):
        asyncio.run(execute())
    assert observer.calls == 2


def test_launch_attestation_includes_review_enforced_permission_profile(
    tmp_path: Path,
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    observer = _observer_for(binary)
    (tmp_path / "mode").write_text("success", encoding="utf-8")
    adapter = ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=observer,
    )
    spec = _workspace_and_spec(
        tmp_path,
        expected_worker_uid=os.geteuid(),
        expected_worker_gid=os.getegid(),
        worker_user=__import__("pwd").getpwuid(os.geteuid()).pw_name,
        secret_canary_verdict=_passing_canary(),
        require_secret_canary=True,
    )

    async def execute() -> object:
        ref = await adapter.start(spec)
        attestation = adapter.launch_attestation(ref)
        await adapter.collect_result(ref)
        return attestation

    attestation = asyncio.run(execute())
    document = attestation.to_dict()
    assert document["schema_version"] == "mastermind.executive_launch_attestation/v1"
    assert len(document["permission_profile_sha256"]) == 64
    # The attested digest source is the exact emitted settings plus the tool and
    # isolation fields: the very request the launched process received.
    settings = _claude_settings(adapter.compile_launch(spec))
    assert profile_settings_bound(adapter, spec, settings) == (
        document["permission_profile_sha256"]
    )
    assert settings["model"] == _EXACT_MODEL
    assert document["worker_identity"]["managed_policy_observation"]["exact_model"] == _EXACT_MODEL
    assert document["worker_identity"]["managed_policy_observation"]["generation"] == 1
    assert document["worker_identity"]["managed_policy_generation"] == 1
    assert observer.calls == 2


def profile_settings_bound(adapter: object, spec: object, settings: dict) -> str:
    return claude_worker._canonical_sha256(
        dict(adapter.permission_profile(spec), requested_settings=settings)  # type: ignore[arg-type]
    )


def test_missing_expected_worker_uid_and_gid_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path)
    spec = _workspace_and_spec(tmp_path)
    object.__setattr__(spec, "expected_worker_uid", None)
    object.__setattr__(spec, "expected_worker_gid", None)
    attempted = _refuse_spawn(monkeypatch)

    async def execute() -> BaseException:
        try:
            await adapter.start(spec)
        except ClaudeWorkerContractError as exc:
            return exc
        raise AssertionError("the launch must refuse")

    refusal = asyncio.run(execute())
    # ``_validate_spec`` exposes only the generic outer refusal and chains the
    # specific reason as the cause; that redaction is the reviewed contract.
    assert type(refusal) is claude_worker.ClaudeLaunchError
    assert str(refusal) == "common launch validation refused"
    cause = refusal.__cause__
    assert isinstance(cause, claude_worker.LaunchValidationError)
    # Both halves missing skips the "together" pairing rule and lands on the
    # exact-worker-principal requirement itself.
    assert str(cause) == "native Claude execution requires exact worker UID/GID"
    assert attempted == []
    assert adapter._runs == {}


def test_missing_expected_gid_only_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path)
    spec = _workspace_and_spec(tmp_path, expected_worker_gid=None)
    attempted = _refuse_spawn(monkeypatch)

    async def execute() -> BaseException:
        try:
            await adapter.start(spec)
        except ClaudeWorkerContractError as exc:
            return exc
        raise AssertionError("the launch must refuse")

    refusal = asyncio.run(execute())
    assert type(refusal) is claude_worker.ClaudeLaunchError
    assert str(refusal) == "common launch validation refused"
    cause = refusal.__cause__
    assert isinstance(cause, claude_worker.LaunchValidationError)
    assert str(cause) == "worker UID/GID must be configured together"
    assert attempted == []
    assert adapter._runs == {}


def test_caller_principal_mismatch_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter(tmp_path)
    cleanups = _count_cleanups(monkeypatch, adapter)
    attempted = _refuse_spawn(monkeypatch)
    bogus_uid = (os.geteuid() + 99_999_999) % 4_294_967_295 or 1
    spec = _workspace_and_spec(
        tmp_path, expected_worker_uid=bogus_uid, expected_worker_gid=os.getegid()
    )

    async def execute() -> BaseException:
        try:
            await adapter.start(spec)
        except ClaudeWorkerContractError as exc:
            return exc
        raise AssertionError("the launch must refuse")

    refusal = asyncio.run(execute())
    assert type(refusal) is claude_worker.ClaudeLaunchError
    assert str(refusal) == "common launch validation refused"
    cause = refusal.__cause__
    assert isinstance(cause, claude_worker.LaunchValidationError)
    assert (
        str(cause)
        == "adapter caller principal does not match the configured worker principal"
    )
    assert attempted == []
    assert cleanups == []
    assert adapter._runs == {}


def test_post_spawn_principal_mismatch_refuses_and_retains_cleanup_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = _fixture_claude_binary(tmp_path)
    (tmp_path / "mode").write_text("sleep", encoding="utf-8")
    adapter = ClaudeCodeWorkerAdapter(
        binary,
        allowed_versions=frozenset({_FIXTURE_VERSION}),
        exact_model=_EXACT_MODEL,
        max_turns=4,
        managed_policy_observer=_observer_for(binary),
    )
    real_inspector = adapter.inspector
    observed_pids: list[int] = []

    class WrongPrincipalInspector:
        def boot_session_id(self) -> str:
            return real_inspector.boot_session_id()

        def inspect(self, pid: int) -> object:
            observed_pids.append(pid)
            identity = real_inspector.inspect(pid)
            return SimpleNamespace(
                start_identity=identity.start_identity,
                pgid=identity.pgid,
                session_id=identity.session_id,
                effective_uid=(identity.effective_uid or 0) + 1,
                effective_gid=identity.effective_gid,
                real_uid=identity.real_uid,
                real_gid=(identity.real_gid or 0) + 1,
            )

    adapter.inspector = WrongPrincipalInspector()
    cleanups = _count_cleanups(monkeypatch, adapter)

    async def execute() -> tuple[BaseException | None, bool, bool]:
        leaked = False
        error: BaseException | None = None
        try:
            await adapter.start(_workspace_and_spec(tmp_path, timeout_seconds=5))
        except BaseException as exc:
            error = exc
        pid = observed_pids[0] if observed_pids else None
        if pid is not None:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                leaked = False
            else:
                leaked = True
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.sleep(0.05)
        return error, leaked, adapter._runs == {}

    error, leaked, runs_empty = asyncio.run(execute())
    assert leaked is False
    assert runs_empty is True
    assert isinstance(error, claude_worker.ClaudeProcessIdentityError)
    assert observed_pids, "the process was created, so cleanup custody applies"
    assert cleanups, "the refused launch must retain and perform cleanup custody"
