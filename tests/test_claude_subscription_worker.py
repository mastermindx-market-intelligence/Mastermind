from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest

from control_plane.claude_subscription_worker import (
    ClaudeSubscriptionWorkerAdapter,
    ClaudeSubscriptionWorkerError,
    attest_claude_binary,
)
from control_plane.codex_worker import LaunchValidationError
from control_plane.subscription_provider_profiles import get_profile
from control_plane.worker_adapter import adapter_descriptor
from control_plane.worker_execution_contract import WorkerLaunchSpec, WorkerRunStatus


_FAKE_SECRET = "fixture-provider-secret-never-serialize"


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"},
    )
    return completed.stdout.strip()


def _workspace(tmp_path: Path) -> tuple[Path, str]:
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    _git(workspace, "init", "-q")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-qm", "fixture")
    return workspace, _git(workspace, "rev-parse", "HEAD")


def _fake_claude(tmp_path: Path) -> Path:
    binary = tmp_path / "fake-claude"
    binary.write_text(
        """#!/usr/bin/python3
import json, os, sys
if '--version' in sys.argv:
    print('2.1.239 (Claude Code)')
    raise SystemExit(0)
if os.environ.get('ANTHROPIC_AUTH_TOKEN') != 'fixture-provider-secret-never-serialize':
    raise SystemExit(51)
if os.environ.get('CLAUDE_CODE_MAX_RETRIES') != '0':
    raise SystemExit(52)
if '--safe-mode' not in sys.argv or '--json-schema' not in sys.argv:
    raise SystemExit(53)
print(json.dumps({
    'type': 'result',
    'subtype': 'success',
    'is_error': False,
    'session_id': 'fixture-session',
    'structured_output': {'decision': 'PASS', 'artifacts': []},
    'usage': {'input_tokens': 11, 'output_tokens': 7},
}, sort_keys=True))
""",
        encoding="utf-8",
    )
    binary.chmod(0o700)
    return binary


def _spec(tmp_path: Path, profile_id: str = "glm-coding-plan") -> tuple[WorkerLaunchSpec, Path]:
    workspace, head = _workspace(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir(mode=0o700)
    input_dir = run_dir / "input"
    input_dir.mkdir(mode=0o700)
    schema = input_dir / "result.schema.json"
    schema.write_text(json.dumps({
        "type": "object",
        "required": ["decision", "artifacts"],
        "properties": {
            "decision": {"const": "PASS"},
            "artifacts": {"type": "array", "maxItems": 0},
        },
        "additionalProperties": False,
    }), encoding="utf-8")
    profile = get_profile(profile_id)
    return WorkerLaunchSpec(
        run_id="run-1", job_id="job-1", worker_id="worker-1",
        workspace_path=workspace, run_dir=run_dir,
        prompt="Read the assigned workspace and return the requested structured result.",
        result_schema_path=schema, authorities=("READ",), model=profile.model_for(),
        expected_base_sha=head,
    ), workspace


def _adapter(tmp_path: Path, profile_id: str = "glm-coding-plan") -> ClaudeSubscriptionWorkerAdapter:
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary, allowed_versions=frozenset({"2.1.239"}))
    return ClaudeSubscriptionWorkerAdapter(
        binary,
        profile=get_profile(profile_id),
        credential_loader=lambda: _FAKE_SECRET,
        execution_mode="interactive_canary",
        allowed_versions=frozenset({"2.1.239"}),
        binary_attestation=attestation,
    )




def test_common_adapter_descriptor_is_implemented_only_after_vertical_exists():
    descriptor = adapter_descriptor("claude-compatible-subscription")
    assert descriptor.implemented is True
    assert descriptor.structured_output is True


def test_current_subscription_profiles_cannot_be_composed_as_unattended_executive_workers(tmp_path: Path):
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary)
    for profile_id in ("glm-coding-plan", "alibaba-token-plan-personal", "minimax-token-plan"):
        with pytest.raises(ClaudeSubscriptionWorkerError, match="interactive-only|not eligible"):
            ClaudeSubscriptionWorkerAdapter(
                binary,
                profile=get_profile(profile_id),
                credential_loader=lambda: _FAKE_SECRET,
                execution_mode="executive_worker",
                binary_attestation=attestation,
            )


def test_command_is_fixed_profile_secret_free_and_bash_free(tmp_path: Path):
    adapter = _adapter(tmp_path)
    spec, _workspace_path = _spec(tmp_path / "case")
    schema = json.loads(Path(spec.result_schema_path).read_text(encoding="utf-8"))
    argv = adapter._command(spec, schema=schema)
    env = adapter._environment(home=tmp_path / "h", tmp=tmp_path / "t", credential=_FAKE_SECRET)
    assert adapter.profile.base_url not in argv
    assert _FAKE_SECRET not in "\n".join(argv)
    assert "Bash" not in tuple(argv[argv.index("--tools") + 1 : argv.index("--allowedTools")])
    assert "Bash" in argv
    assert env["ANTHROPIC_AUTH_TOKEN"] == _FAKE_SECRET
    assert env["ANTHROPIC_BASE_URL"] == adapter.profile.base_url
    assert env["CLAUDE_CODE_MAX_RETRIES"] == "0"


def test_model_mismatch_is_refused_before_credential_load(tmp_path: Path):
    adapter = _adapter(tmp_path)
    spec, _workspace_path = _spec(tmp_path / "case")
    bad = WorkerLaunchSpec(**{**spec.__dict__, "model": "wrong-model"})
    with pytest.raises(LaunchValidationError, match="fixed provider realm model"):
        adapter._validate_spec(bad)


def test_fake_provider_executes_one_read_only_common_worker_receipt_without_secret_leak(tmp_path: Path):
    adapter = _adapter(tmp_path)
    spec, workspace = _spec(tmp_path / "case")

    async def scenario():
        ref = await adapter.start(spec)
        assert await adapter.status(ref) in {WorkerRunStatus.RUNNING, WorkerRunStatus.FAILED}
        receipt = await adapter.collect_result(ref)
        return ref, receipt

    ref, receipt = asyncio.run(scenario())
    assert receipt.result.status is WorkerRunStatus.SUCCEEDED
    assert receipt.result.structured_output == {"decision": "PASS", "artifacts": ()}
    assert receipt.result.provider_session_id == "fixture-session"
    assert receipt.result.usage == {"input_tokens": 11, "output_tokens": 7}
    assert receipt.result.git_manifest["changed_paths"] == ()
    assert _git(workspace, "status", "--porcelain") == ""
    evidence = json.dumps(adapter.launch_attestation(ref), sort_keys=True)
    assert _FAKE_SECRET not in evidence
    assert _FAKE_SECRET not in Path(ref.stdout_path).read_text(encoding="utf-8")
    assert adapter.launch_attestation(ref)["retry_policy"] == "zero"
    assert adapter.launch_attestation(ref)["execution_mode"] == "interactive_canary"
