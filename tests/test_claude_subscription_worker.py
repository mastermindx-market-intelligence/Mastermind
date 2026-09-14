from __future__ import annotations

import asyncio
import dataclasses
import inspect
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
from control_plane.executive_steward import CapacityState, SourceOwner
from control_plane.subscription_canary_admission import (
    CanaryAdmissionError,
    SubscriptionCanaryAdmission,
    seal_subscription_canary_admission,
)
from control_plane.subscription_harness_bindings import (
    DEFAULT_BINDINGS_PATH,
    get_binding,
    load_bindings,
)
from control_plane.subscription_provider_profiles import DEFAULT_PROFILES_PATH, get_profile
from control_plane.worker_adapter import adapter_descriptor
from control_plane.worker_execution_contract import WorkerLaunchSpec
from test_executive_worker_broker import _fixture as _broker_fixture


_FAKE_SECRET = "fixture-provider-secret-never-serialize"
_GLM_BINDING = "glm-coding-plan.claude-code-anthropic"


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


def _spec(tmp_path: Path, binding_id: str = _GLM_BINDING) -> tuple[WorkerLaunchSpec, Path]:
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
    binding = get_binding(binding_id)
    profile = get_profile(binding.profile_id)
    return WorkerLaunchSpec(
        run_id="run-1", job_id="job-1", worker_id="worker-1",
        workspace_path=workspace, run_dir=run_dir,
        prompt="Read the assigned workspace and return the requested structured result.",
        result_schema_path=schema, authorities=("READ",), model=binding.model_for(profile),
        expected_base_sha=head,
    ), workspace


_WORKER_ID = "worker-1"
_CAPACITY_GENERATION = 7
_REALM_GENERATION = 3
_REALM_RECEIPT_ID = "realm-enroll:glm-coding-plan.claude-code-anthropic:3"


def _documents(*, implementation_state: str = "BUILT_NOT_PROVEN"):
    profiles = json.loads(DEFAULT_PROFILES_PATH.read_text(encoding="utf-8"))
    bindings = json.loads(DEFAULT_BINDINGS_PATH.read_text(encoding="utf-8"))
    bindings["bindings"][_GLM_BINDING]["implementation_state"] = implementation_state
    return bindings, profiles


def _seal_kwargs(**changes):
    bindings, profiles = _documents()
    values = {
        "worker_id": _WORKER_ID,
        "binding_id": _GLM_BINDING,
        "execution_mode": "interactive_canary",
        "capacity_state": CapacityState.AVAILABLE.value,
        "capacity_source": SourceOwner.CAPACITY.value,
        "capacity_generation": _CAPACITY_GENERATION,
        "current_capacity_generation": _CAPACITY_GENERATION,
        "realm_receipt_id": _REALM_RECEIPT_ID,
        "realm_generation": _REALM_GENERATION,
        "current_realm_generation": _REALM_GENERATION,
        "bindings_document": bindings,
        "profiles_document": profiles,
    }
    values.update(changes)
    return values


def _seal(**changes):
    return seal_subscription_canary_admission(**_seal_kwargs(**changes))


def _adapter(tmp_path: Path, binding_id: str = _GLM_BINDING) -> ClaudeSubscriptionWorkerAdapter:
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary, allowed_versions=frozenset({"2.1.239"}))
    bindings, profiles = _documents()
    admission = _seal(
        binding_id=binding_id,
        bindings_document=bindings,
        profiles_document=profiles,
    )
    return ClaudeSubscriptionWorkerAdapter(
        binary,
        admission=admission,
        credential_loader=lambda: _FAKE_SECRET,
        allowed_versions=frozenset({"2.1.239"}),
        binary_attestation=attestation,
        bindings_document=bindings,
        profiles_document=profiles,
    )


def test_common_adapter_descriptor_is_not_implemented_without_receipt():
    binding = get_binding(_GLM_BINDING)
    with pytest.raises(ValueError, match="unknown worker adapter"):
        adapter_descriptor(binding.adapter_id)


def test_worker_takes_adapter_endpoint_and_models_from_binding_catalog(tmp_path: Path):
    adapter = _adapter(tmp_path)
    binding = get_binding(_GLM_BINDING)
    profile = get_profile(binding.profile_id)
    assert adapter.binding.binding_id == binding.binding_id
    assert adapter.binding.adapter_id == binding.adapter_id
    assert adapter.binding.effective_base_url == binding.effective_base_url
    assert adapter.binding.autonomous_allowed is False
    assert adapter.profile == profile
    assert adapter.selected_model == binding.model_for(adapter.profile)
    env = adapter._environment(home=tmp_path / "h", tmp=tmp_path / "t", credential=_FAKE_SECRET)
    assert env["ANTHROPIC_BASE_URL"] == binding.effective_base_url
    assert env["ANTHROPIC_MODEL"] == binding.model_for(adapter.profile, "routine")
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == binding.model_for(adapter.profile, "fast")
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == binding.model_for(adapter.profile, "routine")
    assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == binding.model_for(adapter.profile, "hard")
    assert env["CLAUDE_CODE_SUBAGENT_MODEL"] == binding.model_for(adapter.profile, "subagent")
    worker_source = (Path("control_plane") / "claude_subscription_worker.py").read_text(encoding="utf-8")
    profile_source = (Path("control_plane") / "subscription_provider_profiles.py").read_text(encoding="utf-8")
    assert "_claude_code_binding" not in worker_source
    assert 'harness_id == "claude-code"' not in worker_source
    assert 'ADAPTER_ID' not in profile_source
    assert "adapter_id" not in profile_source.split("_FORBIDDEN_HARNESS_FIELDS", 1)[0]
    assert adapter.adapter_id == adapter.binding.adapter_id


def test_caller_supplied_profile_cannot_bypass_catalog(tmp_path: Path):
    catalog_profile = get_profile("glm-coding-plan")
    fabricated = dataclasses.replace(
        catalog_profile,
        autonomous_allowed=True,
        usage_policy={
            **catalog_profile.usage_policy,
            "interactive_only": False,
            "unattended_background_allowed": True,
        },
    )
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary)
    signature = inspect.signature(ClaudeSubscriptionWorkerAdapter.__init__)
    assert "profile" not in signature.parameters
    assert "binding_id" not in signature.parameters
    assert "execution_mode" not in signature.parameters
    assert "admission" in signature.parameters
    with pytest.raises(ClaudeSubscriptionWorkerError, match="admission"):
        ClaudeSubscriptionWorkerAdapter(
            binary,
            profile=fabricated,
            credential_loader=lambda: _FAKE_SECRET,
            execution_mode="executive_worker",
            binary_attestation=attestation,
        )
    with pytest.raises(ClaudeSubscriptionWorkerError, match="admission"):
        ClaudeSubscriptionWorkerAdapter(
            binary,
            binding_id=_GLM_BINDING,
            profile=fabricated,
            credential_loader=lambda: _FAKE_SECRET,
            execution_mode="interactive_canary",
            binary_attestation=attestation,
        )
    with pytest.raises(CanaryAdmissionError, match="interactive_canary|execution mode"):
        _seal(execution_mode="executive_worker")
    bindings, profiles = _documents()
    adapter = ClaudeSubscriptionWorkerAdapter(
        binary,
        admission=_seal(bindings_document=bindings, profiles_document=profiles),
        credential_loader=lambda: _FAKE_SECRET,
        binary_attestation=attestation,
        bindings_document=bindings,
        profiles_document=profiles,
    )
    assert adapter.profile == catalog_profile
    assert adapter.profile != fabricated
    assert adapter.profile.autonomous_allowed is False
    assert adapter.profile.usage_policy.get("unattended_background_allowed") is not True
    adapter.profile = fabricated
    adapter.binding = dataclasses.replace(adapter.binding, autonomous_allowed=True)
    adapter._refresh_catalog_pair()
    refreshed = get_profile("glm-coding-plan", document=profiles)
    assert adapter.profile == refreshed
    assert adapter.profile.autonomous_allowed is False
    assert adapter.binding.autonomous_allowed is False


def test_current_subscription_profiles_cannot_be_composed_as_unattended_executive_workers(tmp_path: Path):
    for binding_id in (
        "glm-coding-plan.claude-code-anthropic",
        "alibaba-token-plan-personal.claude-code-anthropic",
        "minimax-token-plan.claude-code-anthropic",
    ):
        with pytest.raises(CanaryAdmissionError, match="interactive_canary|execution mode"):
            _seal(binding_id=binding_id, execution_mode="executive_worker")
        with pytest.raises(CanaryAdmissionError, match="SPEC_ONLY|implementation"):
            _seal(binding_id=binding_id, bindings_document=None, profiles_document=None)


def test_command_is_fixed_profile_secret_free_and_bash_free(tmp_path: Path):
    adapter = _adapter(tmp_path)
    spec, _workspace_path = _spec(tmp_path / "case")
    schema = json.loads(Path(spec.result_schema_path).read_text(encoding="utf-8"))
    argv = adapter._command(spec, schema=schema)
    env = adapter._environment(home=tmp_path / "h", tmp=tmp_path / "t", credential=_FAKE_SECRET)
    assert adapter.binding.effective_base_url not in argv
    assert _FAKE_SECRET not in "\n".join(argv)
    assert "Bash" not in tuple(argv[argv.index("--tools") + 1 : argv.index("--allowedTools")])
    assert "Bash" in argv
    assert env["ANTHROPIC_AUTH_TOKEN"] == _FAKE_SECRET
    assert env["ANTHROPIC_BASE_URL"] == adapter.binding.effective_base_url
    assert env["CLAUDE_CODE_MAX_RETRIES"] == "0"


def test_model_mismatch_is_refused_before_credential_load(tmp_path: Path):
    adapter = _adapter(tmp_path)
    spec, _workspace_path = _spec(tmp_path / "case")
    bad = WorkerLaunchSpec(**{**spec.__dict__, "model": "wrong-model"})
    with pytest.raises(LaunchValidationError, match="fixed provider realm model"):
        adapter._validate_spec(bad)


def test_turn_refuses_catalog_canary_and_autonomous_blockers(tmp_path: Path):
    from control_plane.subscription_harness_bindings import (
        autonomous_activation_blockers,
        canary_blockers,
    )

    production = get_binding(_GLM_BINDING)
    assert production.implementation_state == "SPEC_ONLY"
    assert production.autonomous_allowed is False
    assert canary_blockers(
        production,
        adapter_implemented=True,
        provider_realm_enrolled=True,
        capacity_known=True,
        usage_policy_satisfied=True,
    ) == ("implementation_not_built",)
    autonomous = autonomous_activation_blockers(
        production,
        adapter_implemented=True,
        provider_realm_enrolled=True,
        capacity_known=True,
        real_canary_passed=True,
        usage_policy_satisfied=True,
    )
    assert "source_policy_disarmed" in autonomous
    assert "implementation_not_proven_live" in autonomous
    with pytest.raises(CanaryAdmissionError, match="SPEC_ONLY|implementation"):
        _seal(bindings_document=None, profiles_document=None)


def test_seal_refuses_raw_boolean_activation_inputs():
    for key in (
        "adapter_implemented",
        "provider_realm_enrolled",
        "capacity_known",
        "usage_policy_satisfied",
        "real_canary_passed",
    ):
        with pytest.raises(CanaryAdmissionError, match="raw boolean|boolean activation"):
            seal_subscription_canary_admission(**_seal_kwargs(**{key: True}))


def test_seal_refuses_wrong_ids():
    with pytest.raises(CanaryAdmissionError, match="worker_id|invalid"):
        _seal(worker_id="worker 1")
    with pytest.raises(CanaryAdmissionError, match="unknown|not reviewed|binding"):
        _seal(binding_id="not-a-reviewed-binding")
    with pytest.raises(CanaryAdmissionError, match="profile|adapter|identity"):
        _seal(profile_id="minimax-token-plan")
    with pytest.raises(CanaryAdmissionError, match="profile|adapter|identity"):
        _seal(adapter_id="codex-cli")


def test_seal_refuses_stale_source_generation():
    with pytest.raises(CanaryAdmissionError, match="stale|generation"):
        _seal(capacity_generation=_CAPACITY_GENERATION, current_capacity_generation=_CAPACITY_GENERATION + 1)
    with pytest.raises(CanaryAdmissionError, match="stale|generation"):
        _seal(realm_generation=_REALM_GENERATION, current_realm_generation=_REALM_GENERATION + 1)


def test_seal_refuses_wrong_capacity_owner():
    with pytest.raises(CanaryAdmissionError, match="owner"):
        _seal(capacity_source=SourceOwner.EXECUTIVE_OS.value)
    with pytest.raises(CanaryAdmissionError, match="owner|capacity"):
        _seal(capacity_source="provider-control")


def test_seal_refuses_changed_catalog_digest():
    bindings, profiles = _documents()
    honest = _seal(bindings_document=bindings, profiles_document=profiles)
    mutated = json.loads(json.dumps(bindings))
    mutated["bindings"][_GLM_BINDING]["model_classes"] = ["routine", "hard"]
    with pytest.raises(CanaryAdmissionError, match="catalog digest"):
        seal_subscription_canary_admission(
            **_seal_kwargs(
                bindings_document=mutated,
                profiles_document=profiles,
                catalog_digest=honest.catalog_digest,
            )
        )


def test_seal_refuses_unenrolled_realm():
    with pytest.raises(CanaryAdmissionError, match="unenrolled|realm"):
        _seal(realm_receipt_id="")
    with pytest.raises(CanaryAdmissionError, match="unenrolled|realm"):
        _seal(realm_receipt_id="   ")
    with pytest.raises(CanaryAdmissionError, match="digest|forged|realm"):
        _seal(realm_receipt_digest="0" * 64)


def test_seal_refuses_spec_only_implementation_state():
    bindings, profiles = _documents(implementation_state="SPEC_ONLY")
    with pytest.raises(CanaryAdmissionError, match="SPEC_ONLY|implementation"):
        _seal(bindings_document=bindings, profiles_document=profiles)
    production = load_bindings()
    with pytest.raises(CanaryAdmissionError, match="SPEC_ONLY|implementation"):
        _seal(bindings_document=production, profiles_document=None)


def test_seal_refuses_autonomous_mode():
    with pytest.raises(CanaryAdmissionError, match="interactive_canary|autonomous|execution mode"):
        _seal(execution_mode="executive_worker")
    with pytest.raises(CanaryAdmissionError, match="interactive_canary|autonomous|execution mode"):
        _seal(execution_mode="autonomous")


def test_adapter_refuses_forged_admission(tmp_path: Path):
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary)
    honest = _seal()
    with pytest.raises((CanaryAdmissionError, ClaudeSubscriptionWorkerError, TypeError), match="forged|unsealed|admission"):
        SubscriptionCanaryAdmission(
            worker_id=honest.worker_id,
            binding_id=honest.binding_id,
            profile_id=honest.profile_id,
            adapter_id=honest.adapter_id,
            execution_mode=honest.execution_mode,
            capacity_state=honest.capacity_state,
            capacity_source=honest.capacity_source,
            capacity_generation=honest.capacity_generation,
            realm_receipt_id=honest.realm_receipt_id,
            realm_receipt_digest=honest.realm_receipt_digest,
            realm_generation=honest.realm_generation,
            catalog_digest=honest.catalog_digest,
            implementation_state=honest.implementation_state,
            seal_digest=honest.seal_digest,
        )
    with pytest.raises((CanaryAdmissionError, ClaudeSubscriptionWorkerError), match="forged|unsealed|admission"):
        ClaudeSubscriptionWorkerAdapter(
            binary,
            admission=object(),
            credential_loader=lambda: _FAKE_SECRET,
            binary_attestation=attestation,
        )


def test_adapter_refuses_stale_or_wrong_binding_evidence(tmp_path: Path):
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary)
    honest = _seal()
    with pytest.raises((CanaryAdmissionError, ClaudeSubscriptionWorkerError), match="stale|forged|generation|seal"):
        stale = dataclasses.replace(honest, capacity_generation=honest.capacity_generation - 1)
        ClaudeSubscriptionWorkerAdapter(
            binary,
            admission=stale,
            credential_loader=lambda: _FAKE_SECRET,
            binary_attestation=attestation,
            bindings_document=_documents()[0],
            profiles_document=_documents()[1],
        )
    with pytest.raises((CanaryAdmissionError, ClaudeSubscriptionWorkerError), match="binding|forged|identity|seal"):
        wrong_binding = dataclasses.replace(
            honest,
            binding_id="alibaba-token-plan-personal.claude-code-anthropic",
        )
        ClaudeSubscriptionWorkerAdapter(
            binary,
            admission=wrong_binding,
            credential_loader=lambda: _FAKE_SECRET,
            binary_attestation=attestation,
            bindings_document=_documents()[0],
            profiles_document=_documents()[1],
        )


def test_adapter_refuses_missing_capacity_or_realm_proof_and_changed_catalog(tmp_path: Path):
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary)
    with pytest.raises((TypeError, CanaryAdmissionError, ClaudeSubscriptionWorkerError), match="admission"):
        ClaudeSubscriptionWorkerAdapter(
            binary,
            binding_id=_GLM_BINDING,
            credential_loader=lambda: _FAKE_SECRET,
            execution_mode="interactive_canary",
            binary_attestation=attestation,
        )
    bindings, profiles = _documents()
    admission = _seal(bindings_document=bindings, profiles_document=profiles)
    changed = json.loads(json.dumps(bindings))
    changed["verified_at"] = "2026-09-13T23:59:59Z"
    with pytest.raises((CanaryAdmissionError, ClaudeSubscriptionWorkerError), match="catalog digest"):
        ClaudeSubscriptionWorkerAdapter(
            binary,
            admission=admission,
            credential_loader=lambda: _FAKE_SECRET,
            binary_attestation=attestation,
            bindings_document=changed,
            profiles_document=profiles,
        )


def test_admitted_interactive_canary_executes_through_existing_broker(tmp_path: Path):
    bindings, profiles = _documents()
    admission = _seal(bindings_document=bindings, profiles_document=profiles)
    assert admission.execution_mode == "interactive_canary"
    assert admission.implementation_state != "SPEC_ONLY"
    assert admission.capacity_source == SourceOwner.CAPACITY.value
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary, allowed_versions=frozenset({"2.1.239"}))
    adapter = ClaudeSubscriptionWorkerAdapter(
        binary,
        admission=admission,
        credential_loader=lambda: _FAKE_SECRET,
        allowed_versions=frozenset({"2.1.239"}),
        binary_attestation=attestation,
        bindings_document=bindings,
        profiles_document=profiles,
    )
    assert adapter.adapter_id == admission.adapter_id
    spec, workspace = _spec(tmp_path / "case", binding_id=_GLM_BINDING)
    spec = WorkerLaunchSpec(**{**spec.__dict__, "worker_id": admission.worker_id})
    broker_root = tmp_path / "broker"
    broker_root.mkdir(mode=0o700)
    broker, _placeholder, _sweeper, _peer, _wire = _broker_fixture(broker_root)
    broker.adapter = adapter

    async def scenario():
        ref = await broker.adapter.start(spec)
        receipt = await broker.adapter.collect_result(ref)
        return ref, receipt

    ref, receipt = asyncio.run(scenario())
    assert receipt.result.status.name == "SUCCEEDED"
    attestation_payload = adapter.launch_attestation(ref)
    dumped = json.dumps(attestation_payload, sort_keys=True)
    assert _FAKE_SECRET not in dumped
    assert attestation_payload.get("credential_value_persisted") is False
    assert attestation_payload.get("credential_present") is True
    argv = adapter._command(spec, schema=json.loads(Path(spec.result_schema_path).read_text(encoding="utf-8")))
    assert _FAKE_SECRET not in "\n".join(argv)
    assert spec.model
    assert _git(workspace, "status", "--porcelain") == ""
