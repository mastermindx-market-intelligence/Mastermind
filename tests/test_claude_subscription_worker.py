from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import inspect
import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

from control_plane.claude_subscription_worker import (
    ClaudeSubscriptionWorkerAdapter,
    ClaudeSubscriptionWorkerError,
    attest_claude_binary,
)
from control_plane.codex_worker import LaunchValidationError
from control_plane.executive_worker_broker import (
    BROKER_REQUEST_SCHEMA_VERSION,
    ExecutiveWorkerBroker,
    WorkerAdapterNotImplementedError,
    WorkerBrokerError,
)
from control_plane.executive_steward import CapacityState, SourceOwner
from control_plane.codex_provider_realm import (
    _PROVIDER_REALM_OWNER_SEAM,
    issue_provider_realm_enrollment_receipt,
)
from control_plane.model_router import (
    _CAPACITY_OWNER_SEAM,
    export_capacity_owner_fact,
)
from control_plane.subscription_canary_admission import (
    CanaryAdmissionError,
    SubscriptionCanaryAdmission,
    seal_subscription_canary_admission,
    verify_subscription_canary_admission,
)
from ops.executive_os.capacity_owner_facts import (
    CapacityOwnerFact,
    CapacityOwnerFactError,
)
from ops.executive_os.provider_realm_facts import (
    ProviderRealmEnrollmentReceipt,
    ProviderRealmFactError,
    compose_realm_receipt_digest,
)
from control_plane.subscription_harness_bindings import (
    DEFAULT_BINDINGS_PATH,
    get_binding,
    load_bindings,
)
from control_plane.subscription_provider_profiles import DEFAULT_PROFILES_PATH, get_profile
from control_plane.worker_adapter import (
    AdapterBindingError,
    ADAPTER_DESCRIPTORS,
    adapter_descriptor,
    construct_reviewed_adapter,
)
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
_CAPACITY_TEST_KEY = b"r581-test-capacity-owner-key"
_REALM_TEST_KEY = b"r581-test-provider-realm-owner-key"


@pytest.fixture(autouse=True)
def _inject_owner_test_keys():
    with _CAPACITY_OWNER_SEAM.install_test_key(
        _CAPACITY_TEST_KEY
    ), _PROVIDER_REALM_OWNER_SEAM.install_test_key(
        _REALM_TEST_KEY
    ), _PROVIDER_REALM_OWNER_SEAM.install_test_enrollment("enrolled"):
        yield


def _documents(*, implementation_state: str = "BUILT_NOT_PROVEN"):
    profiles = json.loads(DEFAULT_PROFILES_PATH.read_text(encoding="utf-8"))
    bindings = json.loads(DEFAULT_BINDINGS_PATH.read_text(encoding="utf-8"))
    bindings["bindings"][_GLM_BINDING]["implementation_state"] = implementation_state
    return bindings, profiles


def _capacity_fact(**changes):
    values = {
        "worker_id": _WORKER_ID,
        "state": CapacityState.AVAILABLE,
        "generation": _CAPACITY_GENERATION,
    }
    values.update(changes)
    return export_capacity_owner_fact(**values)


def _realm_receipt(bindings, profiles, **changes):
    enrollment = changes.pop("enrollment_state", "enrolled")
    with _PROVIDER_REALM_OWNER_SEAM.install_test_enrollment(enrollment):
        values = {
            "binding_id": _GLM_BINDING,
            "bindings_document": bindings,
            "profiles_document": profiles,
            "generation": _REALM_GENERATION,
        }
        values.update(changes)
        return issue_provider_realm_enrollment_receipt(**values)


def _owner_seal(*, capacity_fact=None, realm_receipt=None, bindings=None, profiles=None):
    documents = _documents()
    bindings = bindings if bindings is not None else documents[0]
    profiles = profiles if profiles is not None else documents[1]
    return seal_subscription_canary_admission(
        capacity_fact=capacity_fact if capacity_fact is not None else _capacity_fact(),
        realm_receipt=(
            realm_receipt
            if realm_receipt is not None
            else _realm_receipt(bindings, profiles)
        ),
        bindings_document=bindings,
        profiles_document=profiles,
    )


def _owner_kwargs(**changes):
    bindings, profiles = _documents()
    values = {
        "capacity_fact": _capacity_fact(),
        "realm_receipt": _realm_receipt(bindings, profiles),
        "bindings_document": bindings,
        "profiles_document": profiles,
    }
    values.update(changes)
    return values


def _adapter(tmp_path: Path, binding_id: str = _GLM_BINDING) -> ClaudeSubscriptionWorkerAdapter:
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary, allowed_versions=frozenset({"2.1.239"}))
    bindings, profiles = _documents()
    admission = _owner_seal()
    return ClaudeSubscriptionWorkerAdapter(
        binary,
        admission=admission,
        credential_loader=lambda: _FAKE_SECRET,
        allowed_versions=frozenset({"2.1.239"}),
        binary_attestation=attestation,
        bindings_document=bindings,
        profiles_document=profiles,
    )


def _reviewed_adapter(tmp_path: Path) -> ClaudeSubscriptionWorkerAdapter:
    tmp_path.mkdir(parents=True, mode=0o700, exist_ok=True)
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary, allowed_versions=frozenset({"2.1.239"}))
    bindings, profiles = _documents()
    admission = _owner_seal(bindings=bindings, profiles=profiles)
    return construct_reviewed_adapter(
        get_binding(_GLM_BINDING).adapter_id,
        binary,
        admission=admission,
        credential_loader=lambda: _FAKE_SECRET,
        allowed_versions=frozenset({"2.1.239"}),
        binary_attestation=attestation,
        bindings_document=bindings,
        profiles_document=profiles,
    )


def test_common_adapter_descriptor_is_implemented_only_through_reviewed_receipt():
    binding = get_binding(_GLM_BINDING)
    assert not adapter_descriptor(binding.adapter_id).implemented
    class ClaimedAdapter:
        adapter_id = binding.adapter_id

        def status(self, ref=None):
            return None

    with pytest.raises(AdapterBindingError, match="does not accept"):
        construct_reviewed_adapter(binding.adapter_id, ClaimedAdapter())


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
    bindings, profiles = _documents()
    adapter = ClaudeSubscriptionWorkerAdapter(
        binary,
        admission=_owner_seal(bindings=bindings, profiles=profiles),
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
        documents = _documents()
        documents[0]["bindings"][binding_id]["implementation_state"] = "SPEC_ONLY"
        receipt_documents = _documents()
        with pytest.raises(CanaryAdmissionError, match="SPEC_ONLY|implementation"):
            seal_subscription_canary_admission(
                capacity_fact=_capacity_fact(),
                realm_receipt=_realm_receipt(*receipt_documents, binding_id=binding_id),
                bindings_document=documents[0],
                profiles_document=documents[1],
            )


def test_openai_compatible_binding_cannot_exceed_spec_only_while_adapter_is_unimplemented():
    descriptor = adapter_descriptor("openai-compatible")
    assert descriptor.implemented is False

    # While the openai-compatible adapter remains unimplemented, the production
    # MiniMax row may not claim more than an unproven specification seam.
    binding = get_binding("minimax-token-plan.openai-compatible")
    assert binding.implementation_state == "SPEC_ONLY"
    assert binding.autonomous_allowed is False


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
    production_receipt = _realm_receipt(
        load_bindings(), json.loads(DEFAULT_PROFILES_PATH.read_text(encoding="utf-8"))
    )
    with pytest.raises(CanaryAdmissionError, match="SPEC_ONLY|implementation"):
        seal_subscription_canary_admission(
            capacity_fact=_capacity_fact(),
            realm_receipt=production_receipt,
            bindings_document=load_bindings(),
            profiles_document=json.loads(DEFAULT_PROFILES_PATH.read_text(encoding="utf-8")),
        )


def test_seal_refuses_raw_boolean_activation_inputs():
    for key in (
        "adapter_implemented",
        "provider_realm_enrolled",
        "capacity_known",
        "usage_policy_satisfied",
        "real_canary_passed",
    ):
        with pytest.raises(CanaryAdmissionError, match="raw boolean|boolean activation"):
            seal_subscription_canary_admission(**_owner_kwargs(**{key: True}))


def test_seal_refuses_wrong_ids():
    with pytest.raises(ValueError, match="worker identity is invalid"):
        export_capacity_owner_fact(
            worker_id="worker:1",
            state=CapacityState.AVAILABLE,
            generation=_CAPACITY_GENERATION,
        )
    with pytest.raises(Exception, match="unknown harness binding"):
        _realm_receipt(*_documents(), binding_id="not-a-reviewed-binding")
    with pytest.raises(CanaryAdmissionError, match="typed capacity fact"):
        seal_subscription_canary_admission(
            capacity_fact=object(),
            realm_receipt=_realm_receipt(*_documents()),
        )
    bindings, profiles = _documents()
    with pytest.raises(CanaryAdmissionError, match="unsupported admission input"):
        seal_subscription_canary_admission(
            capacity_fact=_capacity_fact(),
            realm_receipt=_realm_receipt(bindings, profiles),
            bindings_document=bindings,
            profiles_document=profiles,
            realm_receipt_id="",
        )


def test_seal_refuses_owner_selected_generation_primitives():
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        export_capacity_owner_fact(
            worker_id=_WORKER_ID,
            state=CapacityState.AVAILABLE,
            generation=_CAPACITY_GENERATION,
            capacity_generation=_CAPACITY_GENERATION,
            current_capacity_generation=_CAPACITY_GENERATION + 1,
        )
    bindings, profiles = _documents()
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        _realm_receipt(
            bindings,
            profiles,
            realm_generation=_REALM_GENERATION,
            current_realm_generation=_REALM_GENERATION + 1,
        )
    values = _owner_kwargs()
    values["capacity_generation"] = _CAPACITY_GENERATION
    with pytest.raises(CanaryAdmissionError, match="unsupported admission input"):
        seal_subscription_canary_admission(**values)
    values = _owner_kwargs()
    values["realm_generation"] = _REALM_GENERATION
    with pytest.raises(CanaryAdmissionError, match="unsupported admission input"):
        seal_subscription_canary_admission(**values)
    values = _owner_kwargs(capacity_source=SourceOwner.EXECUTIVE_OS.value)
    with pytest.raises(CanaryAdmissionError, match="unsupported admission input"):
        seal_subscription_canary_admission(**values)


def test_seal_refuses_changed_catalog_digest():
    bindings, profiles = _documents()
    honest = _owner_seal(bindings=bindings, profiles=profiles)
    mutated = json.loads(json.dumps(bindings))
    mutated["bindings"][_GLM_BINDING]["model_classes"] = ["routine", "hard"]
    honest_receipt_digest = _realm_receipt(bindings, profiles).receipt_digest
    mutated_receipt = _realm_receipt(mutated, profiles)
    assert mutated_receipt.receipt_digest != honest_receipt_digest
    with pytest.raises(CanaryAdmissionError, match="catalog digest|realm receipt digest"):
        seal_subscription_canary_admission(
            capacity_fact=_capacity_fact(),
            realm_receipt=_realm_receipt(bindings, profiles),
            bindings_document=mutated,
            profiles_document=profiles,
        )


def test_seal_refuses_unenrolled_realm():
    with pytest.raises(CanaryAdmissionError, match="issued provider-realm receipt"):
        seal_subscription_canary_admission(
            capacity_fact=_capacity_fact(),
            realm_receipt=object(),
        )


def test_seal_refuses_spec_only_implementation_state():
    bindings, profiles = _documents(implementation_state="SPEC_ONLY")
    with pytest.raises(CanaryAdmissionError, match="SPEC_ONLY|implementation"):
        _owner_seal(bindings=bindings, profiles=profiles)
    production_bindings = load_bindings()
    production_profiles = json.loads(DEFAULT_PROFILES_PATH.read_text(encoding="utf-8"))
    production_receipt = _realm_receipt(production_bindings, production_profiles)
    with pytest.raises(CanaryAdmissionError, match="SPEC_ONLY|implementation"):
        seal_subscription_canary_admission(
            capacity_fact=_capacity_fact(),
            realm_receipt=production_receipt,
            bindings_document=production_bindings,
            profiles_document=production_profiles,
        )


def test_seal_refuses_autonomous_mode():
    admission = _owner_seal()
    assert admission.execution_mode == "interactive_canary"
    assert "autonomous" not in admission.execution_mode


def test_admission_factory_consumes_only_owner_exported_typed_facts() -> None:
    bindings, profiles = _documents()
    capacity = _capacity_fact()
    receipt = _realm_receipt(bindings, profiles)
    admission = _owner_seal(capacity_fact=capacity, realm_receipt=receipt)
    assert admission.capacity_generation == capacity.generation
    assert admission.realm_receipt_id == receipt.receipt_id
    assert admission.realm_receipt_digest == receipt.receipt_digest
    with pytest.raises(CanaryAdmissionError, match="typed capacity fact"):
        seal_subscription_canary_admission(
            capacity_fact=object(),
            realm_receipt=receipt,
        )
    with pytest.raises(CanaryAdmissionError, match="typed capacity fact"):
        seal_subscription_canary_admission(
            **{**_owner_kwargs(), "capacity_fact": object(), "realm_receipt": receipt}
        )


def test_admission_refuses_unenrolled_or_mismatched_issued_receipts() -> None:
    bindings, profiles = _documents()
    with pytest.raises(CanaryAdmissionError, match="enrollment state"):
        _owner_seal(
            realm_receipt=_realm_receipt(
                bindings, profiles, enrollment_state="unenrolled"
            )
        )
    other_bindings, other_profiles = _documents()
    other_bindings["bindings"][_GLM_BINDING]["endpoint"] = {
        "source": "reviewed_override",
        "base_url": "https://example.invalid/anthropic",
    }
    mismatched = _realm_receipt(other_bindings, other_profiles)
    with pytest.raises(CanaryAdmissionError, match="receipt digest"):
        _owner_seal(realm_receipt=mismatched)


def test_worker_identity_must_match_before_spawn(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    spec, _workspace = _spec(tmp_path / "identity-case", binding_id=_GLM_BINDING)
    spec = WorkerLaunchSpec(**{**spec.__dict__, "worker_id": "worker-2"})
    assert spec.worker_id != adapter.admission.worker_id
    with pytest.raises(LaunchValidationError, match="worker_id does not match admission"):
        adapter._validate_spec(spec)
    with pytest.raises(LaunchValidationError, match="worker_id does not match admission"):
        asyncio.run(adapter.start(spec))


def test_caller_supplied_descriptor_fails_closed_at_broker_construction(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    broker_root = tmp_path / "broker-root"
    broker_root.mkdir(mode=0o700)
    _broker, policy, sweeper, _peer, _wire = _broker_fixture(broker_root)
    with pytest.raises(WorkerBrokerError, match="was not constructed"):
        ExecutiveWorkerBroker(adapter, policy, sweeper, adapter_id=adapter.adapter_id)


def test_adapter_refuses_forged_admission(tmp_path: Path):
    binary = _fake_claude(tmp_path)
    attestation = attest_claude_binary(binary)
    honest = _owner_seal()
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
    honest = _owner_seal()
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
    admission = _owner_seal(bindings=bindings, profiles=profiles)
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


def test_claude_lane_is_spec_only_and_broker_execution_refuses_before_provider_entry() -> None:
    binding = get_binding(_GLM_BINDING)
    assert binding.implementation_state == "SPEC_ONLY"
    assert not ADAPTER_DESCRIPTORS[binding.adapter_id].implemented
    class ClaimedAdapter:
        adapter_id = binding.adapter_id

        def status(self, ref=None):
            return None

    with pytest.raises(WorkerBrokerError, match="reviewed implementation"):
        ExecutiveWorkerBroker(
            ClaimedAdapter(), object(), object(), adapter_id=binding.adapter_id
        )


def test_broker_execution_refuses_reviewed_spec_only_adapter_before_config_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def credential_loader():
        raise AssertionError("credential/config read")

    adapter = _reviewed_adapter(tmp_path / "reviewed-claude")
    monkeypatch.setattr(adapter, "credential_loader", credential_loader)

    async def credential_start_tripwire(spec):
        raise AssertionError("credential/config read")

    fixture_broker, _fixture_adapter, sweeper, _fixture_peer, wire = _broker_fixture(tmp_path)
    wire["worker_id"] = adapter.admission.worker_id
    wire["model"] = adapter.selected_model
    wire["authorities"] = ["READ"]
    workspace = Path(wire["workspace_path"])
    _git(workspace, "init", "-q")
    _git(workspace, "config", "user.email", "fixture@example.invalid")
    _git(workspace, "config", "user.name", "Fixture")
    (workspace / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-qm", "fixture")
    wire["expected_base_sha"] = _git(workspace, "rev-parse", "HEAD")
    Path(wire["run_dir"]).chmod(0o700)
    isolation_roots = [Path(value) for value in wire["isolation_roots"]]
    run_dir = Path(wire["run_dir"])
    workspace_root = next(
        root for root in isolation_roots if workspace.parent == root
    )
    run_root = next(root for root in isolation_roots if run_dir.parent == root)

    def isolation_identity(path: Path) -> dict:
        info = path.lstat()
        return {
            "path": str(path),
            "device": info.st_dev,
            "inode": info.st_ino,
            "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid,
            "gid": info.st_gid,
            "mtime_ns": info.st_mtime_ns,
        }

    manifest = {
        "schema_version": "mastermind.executive_isolation_manifest/v1",
        "roots": sorted(
            (isolation_identity(workspace_root), isolation_identity(run_root)),
            key=lambda value: value["path"],
        ),
        "entries": sorted(
            (
                {
                    "root_path": str(workspace_root),
                    "disposition": "CURRENT_WORKSPACE",
                    "identity": isolation_identity(workspace),
                },
                {
                    "root_path": str(run_root),
                    "disposition": "CURRENT_RUN",
                    "identity": isolation_identity(run_dir),
                },
            ),
            key=lambda entry: entry["identity"]["path"],
        ),
        "workspace_path": str(workspace),
        "run_dir": str(run_dir),
    }
    wire["isolation_manifest"] = manifest
    wire["isolation_manifest_sha256"] = hashlib.sha256(
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    fixture_broker.adapter = _fixture_adapter
    fixture_broker.adapter.start = credential_start_tripwire
    policy = dataclasses.replace(
        fixture_broker.policy, worker_id=adapter.admission.worker_id
    )
    broker = ExecutiveWorkerBroker(
        adapter, policy, sweeper, adapter_id=adapter.adapter_id
    )
    peer = _fixture_peer

    async def scenario() -> None:
        with pytest.raises(
            WorkerAdapterNotImplementedError,
            match=(
                "is not implemented for broker execution|"
                "catalog binding is SPEC_ONLY for broker execution|"
                "does not allow autonomous broker execution"
            ),
        ):
            await broker.execute(
                {
                    "schema_version": BROKER_REQUEST_SCHEMA_VERSION,
                    "request_id": "request-1",
                    "operation": "start",
                    "payload": {"launch_spec": wire, "validation_commands": []},
                },
                peer=peer,
            )

    asyncio.run(scenario())


def test_catalog_digest_entrypoints_share_one_policy() -> None:
    from control_plane.subscription_canary_admission import (
        compose_catalog_digest as admission_digest,
    )
    from control_plane.subscription_catalog import (
        compose_catalog_digest as catalog_digest,
    )

    bindings, profiles = _documents()
    assert admission_digest(
        bindings_document=bindings,
        profiles_document=profiles,
    ) == catalog_digest(
        bindings_document=bindings,
        profiles_document=profiles,
    )


def test_attack_a_primitive_kwarg_construction_is_typed_field_refusal() -> None:
    """(a) Residual TypeError surface: primitives must name capacity_fact/realm_receipt."""

    with pytest.raises(CanaryAdmissionError, match="capacity_fact") as capacity_exc:
        seal_subscription_canary_admission(
            worker_id=_WORKER_ID,
            binding_id=_GLM_BINDING,
            capacity_state=CapacityState.AVAILABLE.value,
            capacity_source=SourceOwner.CAPACITY.value,
            capacity_generation=999,
            current_capacity_generation=999,
            realm_receipt_id="provider-realm:glm-coding-plan.claude-code-anthropic:42",
            realm_generation=42,
            current_realm_generation=42,
        )
    assert "capacity_fact" in str(capacity_exc.value)
    with pytest.raises(CanaryAdmissionError, match="realm_receipt") as realm_exc:
        seal_subscription_canary_admission(
            capacity_fact=_capacity_fact(),
            worker_id=_WORKER_ID,
            binding_id=_GLM_BINDING,
            capacity_generation=999,
            current_capacity_generation=999,
            realm_receipt_id="provider-realm:glm-coding-plan.claude-code-anthropic:42",
            realm_generation=42,
            current_realm_generation=42,
        )
    assert "realm_receipt" in str(realm_exc.value)


def test_attack_b_forged_realm_id_is_refused() -> None:
    """(b) Forged receipt_id provider-realm:caller-forged:99 must be refused."""

    bindings, profiles = _documents()
    honest = _realm_receipt(bindings, profiles)
    stolen = object.__getattribute__(honest, "_seal")
    from control_plane.subscription_canary_admission import compose_catalog_digest

    forged_id = "provider-realm:caller-forged:99"
    catalog_digest = compose_catalog_digest(
        bindings_document=bindings,
        profiles_document=profiles,
    )
    public_digest = compose_realm_receipt_digest(
        receipt_id=forged_id,
        binding_id=honest.binding_id,
        profile_id=honest.profile_id,
        adapter_id=honest.adapter_id,
        generation=99,
        catalog_digest=catalog_digest,
    )
    with pytest.raises(
        (CanaryAdmissionError, ProviderRealmFactError),
        match="receipt_id",
    ) as exc:
        forged = ProviderRealmEnrollmentReceipt(
            receipt_id=forged_id,
            receipt_digest=public_digest,
            binding_id=honest.binding_id,
            profile_id=honest.profile_id,
            adapter_id=honest.adapter_id,
            generation=99,
            enrollment_state="enrolled",
            _seal=stolen,
        )
        seal_subscription_canary_admission(
            capacity_fact=_capacity_fact(),
            realm_receipt=forged,
            bindings_document=bindings,
            profiles_document=profiles,
        )
    assert "receipt_id" in str(exc.value)


def test_attack_c_public_input_digest_is_refused() -> None:
    """(c) A caller-computed public digest is not an owner-issued receipt seal."""

    bindings, profiles = _documents()
    honest = _realm_receipt(bindings, profiles)
    stolen = object.__getattribute__(honest, "_seal")
    from control_plane.subscription_canary_admission import compose_catalog_digest

    catalog_digest = compose_catalog_digest(
        bindings_document=bindings,
        profiles_document=profiles,
    )
    public_digest = compose_realm_receipt_digest(
        receipt_id=honest.receipt_id,
        binding_id=honest.binding_id,
        profile_id=honest.profile_id,
        adapter_id=honest.adapter_id,
        generation=honest.generation,
        catalog_digest=catalog_digest,
    )
    with pytest.raises(
        (CanaryAdmissionError, ProviderRealmFactError),
        match="receipt_digest",
    ) as exc:
        forged = ProviderRealmEnrollmentReceipt(
            receipt_id=honest.receipt_id,
            receipt_digest=public_digest,
            binding_id=honest.binding_id,
            profile_id=honest.profile_id,
            adapter_id=honest.adapter_id,
            generation=honest.generation,
            enrollment_state=honest.enrollment_state,
            _seal=stolen,
        )
        seal_subscription_canary_admission(
            capacity_fact=_capacity_fact(),
            realm_receipt=forged,
            bindings_document=bindings,
            profiles_document=profiles,
        )
    assert "receipt_digest" in str(exc.value)


def test_attack_d_stolen_seal_on_different_content_is_refused() -> None:
    """(d) A stolen owner seal must not attest different capacity content."""

    honest = _capacity_fact()
    stolen = object.__getattribute__(honest, "_seal")
    bindings, profiles = _documents()
    with pytest.raises(
        (CanaryAdmissionError, CapacityOwnerFactError),
        match="capacity_fact|_seal|generation|worker_id",
    ) as exc:
        forged = CapacityOwnerFact(
            worker_id="attacker-9",
            state=CapacityState.AVAILABLE,
            source=SourceOwner.CAPACITY,
            generation=12345,
            _seal=stolen,
        )
        seal_subscription_canary_admission(
            capacity_fact=forged,
            realm_receipt=_realm_receipt(bindings, profiles),
            bindings_document=bindings,
            profiles_document=profiles,
        )
    assert any(
        name in str(exc.value)
        for name in ("capacity_fact", "_seal", "generation", "worker_id")
    )


def test_attack_e_replace_unenrolled_to_enrolled_is_refused() -> None:
    """(e) dataclasses.replace must not turn an unenrolled receipt into enrolled."""

    bindings, profiles = _documents()
    with _PROVIDER_REALM_OWNER_SEAM.install_test_enrollment("unenrolled"):
        unenrolled = issue_provider_realm_enrollment_receipt(
            binding_id=_GLM_BINDING,
            bindings_document=bindings,
            profiles_document=profiles,
            generation=_REALM_GENERATION,
        )
    assert unenrolled.enrollment_state == "unenrolled"
    with pytest.raises(
        (CanaryAdmissionError, ProviderRealmFactError),
        match="enrollment_state",
    ) as exc:
        mutated = dataclasses.replace(unenrolled, enrollment_state="enrolled")
        seal_subscription_canary_admission(
            capacity_fact=_capacity_fact(),
            realm_receipt=mutated,
            bindings_document=bindings,
            profiles_document=profiles,
        )
    assert "enrollment_state" in str(exc.value)


def test_attack_f_every_use_admission_seal_bypass_is_refused() -> None:
    """Every-use verification refuses a mutated live admission plus a valid replacement fact."""

    bindings, profiles = _documents()
    replacement = _capacity_fact(worker_id="worker-2")

    def _mutated_live_admission(*, seal=...):
        admission = _owner_seal(bindings=bindings, profiles=profiles)
        object.__setattr__(admission, "worker_id", "worker-2")
        object.__setattr__(admission, "_capacity_fact", replacement)
        if seal is not ...:
            object.__setattr__(admission, "_seal", seal)
        return admission

    def _verify(admission):
        return verify_subscription_canary_admission(
            admission,
            adapter_id=admission.adapter_id,
            bindings_document=bindings,
            profiles_document=profiles,
        )

    with pytest.raises(CanaryAdmissionError, match="seal_digest") as digest_exc:
        _verify(_mutated_live_admission())
    assert "seal_digest" in str(digest_exc.value)

    with pytest.raises(CanaryAdmissionError, match="_seal") as cleared_exc:
        _verify(_mutated_live_admission(seal=None))
    assert "_seal" in str(cleared_exc.value)

    with pytest.raises(CanaryAdmissionError, match="_seal") as forged_exc:
        _verify(_mutated_live_admission(seal=object()))
    assert "_seal" in str(forged_exc.value)
