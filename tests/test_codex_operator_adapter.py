from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

import control_plane.codex_operator_adapter as codex_operator_adapter
from control_plane.codex_operator_adapter import (
    CodexAdapterError,
    CodexOperatorAdapter,
    CodexProtocolAttestationReceipt,
    CodexSkillCanaryBinding,
    CodexSkillTurnInput,
    CodexTurnInputEnvelope,
    SKILL_INPUT_SCHEMA_EVIDENCE,
    build_protocol_attestation_receipt,
    compute_protocol_attestation_receipt_digest,
)
from control_plane.executive_agent_capabilities import (
    ExecutionCapabilityRegistry,
    NativeHelperGrant,
    app_server_security_config_digest,
)
from control_plane.executive_capability_packages import (
    build_capability_package_generation,
)
from control_plane.operator_harness_contract import (
    AdapterFailureClass,
    CapabilityIdentity,
    CapabilityManifest,
    EventCursor,
    LaunchDecision,
    NativeHelperPolicy,
    ObservedCapabilityIdentity,
    ObservedTriState,
    OperationId,
    OperatorHarnessAdapter,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderSessionHandoff,
    ProviderWriterState,
    RequestedExecutionProfile,
    SessionEpochRef,
    SupportsNativeFork,
    SupportsSessionResume,
    TurnRef,
    WorkspaceIdentity,
    compare_launch,
)
from control_plane.operator_harness_orchestrator import OperatorHarnessOrchestrator
from scripts.ohf.capability_skill_projection import (
    ORIGIN_INSTALLED_RELEASE,
    stage_skill_projection,
)
from scripts.ohf.fixtures import OHF_PROBE_MCP_SERVER
from scripts.ohf.laboratory import AppServerClient, PrivateRawTurnPage
from scripts.ohf.redaction import REDACTED

REPO_ROOT = Path(__file__).resolve().parents[1]
_CREATED_ADAPTERS: list[CodexOperatorAdapter] = []

# ---------------------------------------------------------------------------
# CAP-S1 Codex skill-canary fixtures (protocol-attestation amendment §5-§8)
# ---------------------------------------------------------------------------

CAP_S1_V4_FIXTURE = (
    REPO_ROOT / "scripts" / "ohf" / "fixtures"
    / "executive_agent_capabilities_v4_mastermind_operator.json"
)
CAP_S1_PACKAGE_CAPABILITY_ID = "mastermind-operator.p1"
CAP_S1_PROFILE_ID = "operator.appserver.readonly.mastermind-operator.v1"
CAP_S1_OPERATION_ID = "mastermind-cap-s1-complete-vertical-20260901-sol-001"
CAP_S1_HARNESS_VERSION = "ohf-fake-app-server/p0b"


def _test_binary_digest() -> str:
    """The exact digest the fake-App-Server harness (the running python
    interpreter) will compute for itself -- every skill-canary harness in
    this module launches that same interpreter, so this is a fixed value."""

    return hashlib.sha256(Path(sys.executable).resolve().read_bytes()).hexdigest()


def _load_cap_s1_generation():
    raw_document = json.loads(CAP_S1_V4_FIXTURE.read_text(encoding="utf-8"))
    raw_package = raw_document["capability_packages"][CAP_S1_PACKAGE_CAPABILITY_ID]
    return build_capability_package_generation(
        capability_id=CAP_S1_PACKAGE_CAPABILITY_ID, raw=raw_package
    )


def _load_cap_s1_profile():
    registry = ExecutionCapabilityRegistry.load(CAP_S1_V4_FIXTURE, source_root=REPO_ROOT)
    return registry.resolve(CAP_S1_PROFILE_ID)


def _installed_release_origin_root(tmp_path: Path, generation) -> Path:
    """Sol wave-3 review (5087139217, finding M6): ``INSTALLED_RELEASE``
    now requires the origin root's own basename to equal the generation's
    exact ``source_commit`` (the Executive installer's ``releases/<sha>``
    layout) -- a bare checkout root no longer authenticates. This helper
    builds that small, real (non-symlink) release-shaped origin by copying
    only the already-reviewed package subtree, never the whole repository.
    """
    release_root = tmp_path / "cap-s1-release-root" / generation.source_commit
    package_dest = release_root / generation.package_root
    package_dest.parent.mkdir(parents=True, exist_ok=True)
    if not package_dest.exists():
        shutil.copytree(REPO_ROOT / generation.package_root, package_dest)
    return release_root


def _stage_cap_s1_binding(
    tmp_path: Path,
    *,
    owning_process_generation: str = "gen-1",
    schema_supports_skill_input_path: bool = True,
) -> CodexSkillCanaryBinding:
    generation = _load_cap_s1_generation()
    profile = _load_cap_s1_profile()
    attempt_root = tmp_path / "cap-s1-attempt-root"
    attempt_root.mkdir(parents=True, exist_ok=True)
    origin_root = _installed_release_origin_root(tmp_path, generation)
    projection = stage_skill_projection(
        generation=generation,
        origin_mode=ORIGIN_INSTALLED_RELEASE,
        origin_root=origin_root,
        attempt_root=attempt_root,
        owning_operation_id=CAP_S1_OPERATION_ID,
        owning_process_generation=owning_process_generation,
    )
    return CodexSkillCanaryBinding(
        generation=generation,
        profile=profile,
        projection=projection,
        protocol_receipt=build_protocol_attestation_receipt(
            binary_path=str(Path(sys.executable).resolve()),
            binary_digest=_test_binary_digest(),
            binary_version=CAP_S1_HARNESS_VERSION,
            stable_inventory_digest="c" * 64,
            experimental_inventory_digest="d" * 64,
            supports_skill_input_path=schema_supports_skill_input_path,
            skill_input_schema_evidence=(
                SKILL_INPUT_SCHEMA_EVIDENCE
                if schema_supports_skill_input_path
                else ""
            ),
            probe_user_agent=CAP_S1_HARNESS_VERSION,
        ),
    )


def _skill_capability_requested(harness: "Harness", binding: CodexSkillCanaryBinding):
    manifest = binding.profile.capability_manifest(
        harness_binary_digest=harness.adapter.binary_digest
    )
    return replace(
        harness.requested,
        capabilities=CapabilityManifest(
            required=manifest.required,
            unclassified_policy="lab_allow_unclassified_readonly",
        ),
    )


class _RecordingSkillsClient:
    """Wraps a real ``AppServerClient``.

    Records every RPC call (method, params) so tests can assert the exact
    causal order and wire shape, and can optionally substitute scripted
    sequential ``skills/list`` responses -- used only for the malformed row
    shapes (duplicate names, mixed path presence, a wrong path) that the
    real row-faithful fake server cannot itself produce from genuine
    filesystem roots without also disturbing the empty-baseline law every
    other case here depends on.  Every other RPC always reaches the real
    fake App Server subprocess.
    """

    def __init__(self, inner: AppServerClient, skills_list_script=None) -> None:
        self._inner = inner
        self._skills_list_script = list(skills_list_script or [])
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def request(self, method, params=None, *, timeout=15.0):
        self.calls.append((method, dict(params or {})))
        if method == "skills/list" and self._skills_list_script:
            return self._skills_list_script.pop(0)
        return self._inner.request(method, params, timeout=timeout)


def _recording_client_factory(skills_list_script=None):
    def factory(argv, env, cwd):
        inner = AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)
        return _RecordingSkillsClient(inner, skills_list_script=skills_list_script)

    return factory


def _strict_skills_list_result(cwd: str, rows: list[dict]) -> dict:
    return {"data": [{"cwd": cwd, "skills": rows, "errors": []}]}


def _skill_row(name: str, *, path: str | None, enabled: bool = True) -> dict:
    row: dict[str, object] = {"name": name, "enabled": enabled}
    if path is not None:
        row["path"] = path
    return row


def _make_skill_harness(
    tmp_path: Path,
    binding: CodexSkillCanaryBinding,
    *,
    extra_env: dict[str, str] | None = None,
    client_factory=None,
    turn_input: str = "Reply with the probe acknowledgement.",
    bundled_disabled: bool = True,
) -> "Harness":
    """Build a skill-canary harness with the config-digest gate re-armed.

    ``bundled_disabled`` (default True) tells the fake App Server to echo
    ``skills.bundled.enabled=false`` from ``config/read``, matching the
    profile's own policy-side projection (protocol amendment §5). Pass
    ``bundled_disabled=False`` to build a harness whose scripted
    ``config/read`` OMITS the ``bundled`` key -- this is the re-armed gate's
    falsifier: ``compare_launch`` must then REFUSE_CONFIG_DRIFT rather than
    silently ALLOW, because ``expected_config_digest`` is always sealed onto
    a skill-canary harness now (never left unset the way the retired
    workaround left it).

    The CAP-S1 mastermind-operator profile grants zero MCP servers (its own
    ``app_server_config_projection()["mcp_servers"]`` is ``{}``), so the
    fake App Server's unrelated OHF-probe MCP fixture must not appear in
    the observed config surface either -- ``OHF_FAKE_MCP_GONE=1`` mirrors
    the same precedent already used by
    ``scripts/ohf/cap_s1_mastermind_operator_canary.py`` for this exact
    profile.
    """

    merged_env = {
        "OHF_FAKE_SKILL_ROOT": str(tmp_path / "cap-s1-no-ambient-skills"),
        "OHF_FAKE_MCP_GONE": "1",
    }
    if bundled_disabled:
        merged_env["OHF_FAKE_BUNDLED_DISABLED"] = "1"
    merged_env.update(extra_env or {})
    harness = _make_harness(
        tmp_path,
        extra_env=merged_env,
        skill_canary_binding=binding,
        client_factory=client_factory or _recording_client_factory(),
        turn_input=turn_input,
        expected_config_digest_override=binding.profile.expected_config_digest,
    )
    harness.requested = _skill_capability_requested(harness, binding)
    return harness


def _cap_s1_envelope(binding: CodexSkillCanaryBinding, *, grant_index: int = 0):
    grant = binding.profile.skill_grants[grant_index]
    final_path = f"{binding.projection.skills_root}/{grant.runtime_name}/SKILL.md"
    return CodexTurnInputEnvelope(
        text=f"${grant.runtime_name} synthetic bounded instruction",
        skills=(
            CodexSkillTurnInput(
                capability_id=grant.capability_id,
                runtime_name=grant.runtime_name,
                skill_md_path=final_path,
                skill_content_digest=grant.skill_content_digest,
                package_generation_digest=binding.generation.package_generation_digest,
            ),
        ),
    ), final_path


def _op(suffix: str) -> OperationId:
    return OperationId(f"ohf-op:{suffix}")


@dataclass
class Harness:
    adapter: CodexOperatorAdapter
    requested: RequestedExecutionProfile
    epoch: SessionEpochRef
    generation: ProcessGenerationRef
    state_path: Path


def _process(pid: int) -> ProcessIdentityObservation:
    return ProcessIdentityObservation(pid, os.getpgid(pid), f"start-{pid}", "boot-test")


def _make_harness(
    tmp_path: Path,
    *,
    extra_env: dict[str, str] | None = None,
    fault_server: bool = False,
    client_factory=None,
    turn_input: str = "Reply with the probe acknowledgement.",
    harness_version: str = "ohf-fake-app-server/p0b",
    network_policy: str = "disabled",
    native_helper: bool = False,
    skill_canary_binding: "CodexSkillCanaryBinding | None" = None,
    expected_config_digest_override: str | None = None,
) -> Harness:
    codex_home = tmp_path / "codex-home"
    workspace = tmp_path / "workspace"
    skill = workspace / ".agents" / "skills" / "ohf-probe"
    codex_home.mkdir(parents=True, exist_ok=True)
    codex_home.chmod(0o700)
    skill.mkdir(parents=True, exist_ok=True)
    (codex_home / "auth.json").write_text("fixture credential bytes", encoding="utf-8")
    (codex_home / "auth.json").chmod(0o600)
    (skill / "SKILL.md").write_text("# OHF probe\n", encoding="utf-8")
    state_path = codex_home / "fake-state.json"
    python = Path(sys.executable).resolve()
    argv = (
        (str(python), str(REPO_ROOT / "tests/fixtures/ohf_p1b_fault_app_server.py"))
        if fault_server
        else (str(python), "-m", "scripts.ohf.fake_app_server")
    )
    env = {
        "PYTHONPATH": str(REPO_ROOT),
        "OHF_FAKE_STATE": str(state_path),
        "OHF_FAKE_WORKSPACE": str(workspace),
        "OHF_FAKE_SKILL_ROOT": str(workspace / ".agents" / "skills"),
        "OHF_FAKE_MODEL": "gpt-5.6-sol",
        **({"OHF_FAKE_NATIVE_HELPER": "1"} if native_helper else {}),
        **(extra_env or {}),
    }
    native_helper_grant = (
        NativeHelperGrant(
            mechanism="codex-multi-agent-v2-inherit-parent",
            default_model="gpt-5.6-sol",
            default_reasoning_effort="xhigh",
            inherit_parent_capabilities=True,
            hide_spawn_agent_metadata=True,
            max_concurrent_helpers=1,
            max_depth=1,
            max_runtime_seconds=60,
            grant_digest="d" * 64,
        )
        if native_helper
        else None
    )
    expected_config_digest = None
    if native_helper:
        expected_config_digest = app_server_security_config_digest(
            {
                "model": "gpt-5.6-sol",
                "approval_policy": "never",
                "sandbox_mode": "read-only",
                "agents": {
                    "default_subagent_model": "gpt-5.6-sol",
                    "default_subagent_reasoning_effort": "xhigh",
                    "enabled": True,
                    "interrupt_message": None,
                    "job_max_runtime_seconds": 60,
                    "max_concurrent_threads_per_session": 1,
                    "max_depth": 1,
                },
                "features": {
                    "apps": False,
                    "auth_elicitation": False,
                    "enable_mcp_apps": False,
                    "mcp_2026_07_28": False,
                    "multi_agent": False,
                    "multi_agent_v2": {
                        "enabled": True,
                        "hide_spawn_agent_metadata": True,
                        "max_concurrent_threads_per_session": 2,
                        "non_code_mode_only": False,
                    },
                    "plugins": False,
                    "remote_plugin": False,
                    "tool_call_mcp_elicitation": False,
                },
                "mcp_servers": {OHF_PROBE_MCP_SERVER: {"command": "python3"}},
                "plugins": {},
            }
        )
    if expected_config_digest_override is not None:
        expected_config_digest = expected_config_digest_override
    kwargs = {}
    if client_factory is not None:
        kwargs["client_factory"] = client_factory
    adapter = CodexOperatorAdapter(
        binary_path=python,
        codex_home=codex_home,
        workspace_root=workspace,
        worker_id="slot-a",
        app_server_argv=argv,
        expected_harness_version=harness_version,
        expected_config_digest=expected_config_digest,
        native_helper_grant=native_helper_grant,
        network_policy=network_policy,
        turn_input_loader=lambda turn: turn_input,
        base_sha_resolver=lambda path: "b" * 40,
        process_identity_observer=_process,
        extra_env=env,
        skill_canary_binding=skill_canary_binding,
        **kwargs,
    )
    stat = workspace.stat()
    requested = RequestedExecutionProfile(
        worker_id="slot-a",
        provider="openai-codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest=adapter.binary_digest,
        harness_version=harness_version,
        workspace=WorkspaceIdentity(
            str(workspace.resolve()),
            "b" * 40,
            stat.st_dev,
            stat.st_ino,
            stat.st_uid,
            stat.st_gid,
        ),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy=network_policy,
        capabilities=CapabilityManifest(
            unclassified_policy="lab_allow_unclassified_readonly"
        ),
        native_helper_policy=(
            NativeHelperPolicy.PARENT_READ_ONLY_CEILING
            if native_helper
            else NativeHelperPolicy.DISABLED
        ),
        expected_config_digest=expected_config_digest,
        authority_policy_hash="c" * 64,
    )
    _CREATED_ADAPTERS.append(adapter)
    return Harness(
        adapter=adapter,
        requested=requested,
        epoch=SessionEpochRef("epoch-1", "attempt-1", "slot-a", 1),
        generation=ProcessGenerationRef("gen-1", "epoch-1", 1, "slot-a"),
        state_path=state_path,
    )


@pytest.fixture
def harness(tmp_path: Path):
    value = _make_harness(tmp_path)
    yield value
    for state in value.adapter._generations.values():
        state.client.close()


@pytest.fixture(autouse=True)
def _close_created_adapters():
    _CREATED_ADAPTERS.clear()
    yield
    for adapter in _CREATED_ADAPTERS:
        for state in adapter._generations.values():
            state.client.close()
    _CREATED_ADAPTERS.clear()


class _Runtime:
    """Minimal Executive test double; every method logs its commit boundary."""

    def __init__(self, harness: Harness) -> None:
        self.harness = harness
        self.calls: list[str] = []
        self.candidate = None

    def seal_operator_attempt(self, attempt_id, requested):
        self.calls.append("seal")

    def extend_operator_lease(self, attempt_id, minimum_seconds):
        self.calls.append("lease")

    def commit_operator_provider_dispatch(
        self, attempt_id, operation_id, operation_kind
    ):
        self.calls.append("dispatch")
        return True

    def commit_operator_resume_dispatch(self, attempt_id, operation_id):
        return True

    def begin_operator_session(self, attempt_id, operation_id):
        self.calls.append("start_intent")
        return self.harness.epoch, self.harness.generation

    def bind_operator_session(self, attempt_id, operation_id, observation):
        self.calls.append("start_bind")

    def seal_operator_attestation(self, attempt_id, generation, observed, launch):
        self.calls.append("attest")

    def begin_operator_turn(self, attempt_id, generation, operation_id):
        self.calls.append("turn_intent")
        return TurnRef(
            "turn-1", "epoch-1", generation.process_generation_id, attempt_id
        )

    def apply_operator_turn(self, attempt_id, operation_id, observation):
        self.calls.append("turn_bind")

    def finish_operator_candidate(self, attempt_id, turn, candidate, events, cursor):
        self.calls.append("candidate")
        self.candidate = candidate

    def record_operator_effect_unknown(self, attempt_id, operation_id, phase, detail):
        self.calls.append("effect_unknown")
        return True

    def begin_operator_generation_operation(
        self, attempt_id, generation, operation_id, operation_kind
    ):
        self.calls.append(f"{operation_kind}_intent")

    def graceful_stop_operator_generation(
        self, attempt_id, generation, operation_id, observation
    ):
        self.calls.append("stop_bind")

    def cancel_operator_generation(
        self, attempt_id, generation, operation_id, observation
    ):
        self.calls.append("cancel_bind")

    def observe_operator_reconcile(self, attempt_id, generation, observation):
        self.calls.append("reconcile")

    def begin_operator_resume(self, attempt_id, epoch, operation_id):
        self.calls.append("resume_intent")
        return ProcessGenerationRef("gen-2", epoch.session_epoch_id, 2, epoch.worker_id)

    def bind_operator_resume(self, attempt_id, operation_id, handoff, observation):
        self.calls.append("resume_bind")


def _start(harness: Harness):
    observation = harness.adapter.start_session(
        operation_id=_op("start"),
        requested=harness.requested,
        epoch=harness.epoch,
        generation=harness.generation,
    )
    attestation = harness.adapter.observed_attestation(harness.generation)
    return observation, attestation, compare_launch(harness.requested, attestation)


def test_fake_app_server_end_to_end_through_provider_neutral_orchestrator(
    harness: Harness,
) -> None:
    runtime = _Runtime(harness)
    orchestrator = OperatorHarnessOrchestrator(
        runtime,
        harness.adapter,
        attestation_reader=lambda adapter, generation: adapter.observed_attestation(
            generation
        ),
    )

    session = orchestrator.start_attempt(
        attempt_id="attempt-1",
        requested=harness.requested,
        operation_id=_op("start-e2e"),
    )
    turn = orchestrator.run_turn(session, operation_id=_op("turn-e2e"))
    stopped = orchestrator.graceful_stop(session, operation_id=_op("stop-e2e"))

    assert session.launch.decision is LaunchDecision.ALLOW
    assert turn.candidate.summary
    assert turn.candidate.complete_job_permitted is False
    assert runtime.candidate == turn.candidate
    assert all(
        event.process_generation_id == session.generation.process_generation_id
        for event in turn.events
    )
    assert turn.cursor.local_sequence == len(turn.events)
    assert stopped.process_liveness is ProcessLiveness.PROVEN_DEAD
    assert stopped.provider_writer_state is ProviderWriterState.RELEASED
    assert [call for call in runtime.calls if call not in {"lease", "dispatch"}] == [
        "seal",
        "start_intent",
        "start_bind",
        "attest",
        "turn_intent",
        "turn_bind",
        "candidate",
        "graceful_stop_intent",
        "stop_bind",
    ]


def test_native_helper_is_exactly_attested_audited_and_redacted(
    tmp_path: Path,
) -> None:
    harness = _make_harness(tmp_path, native_helper=True)
    _, observed, launch = _start(harness)
    assert launch.decision is LaunchDecision.ALLOW
    assert (
        observed.supports_subagent_capability_ceiling
        is ObservedTriState.VERIFIED
    )

    turn = TurnRef("turn-helper", "epoch-1", "gen-1", "attempt-1")
    harness.adapter.begin_turn(
        operation_id=_op("native-helper-turn"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )
    events, _ = harness.adapter.read_events(
        EventCursor("attempt-1", "epoch-1", "gen-1", turn_id=turn.turn_id)
    )
    candidate = harness.adapter.collect_candidate_result(turn)

    subordinate_ids = {
        event.native_subordinate_id
        for event in events
        if event.native_subordinate_id is not None
    }
    assert len(subordinate_ids) == 1
    assert any(
        event.payload_redacted.get("item_type") == "collabAgentToolCall"
        and event.payload_redacted.get("tool") == "spawnAgent"
        and event.payload_redacted.get("receiver_count") == 1
        for event in events
    )
    assert "fixture prompt" not in json.dumps(
        [event.payload_redacted for event in events], sort_keys=True
    )
    assert candidate.complete_job_permitted is False
    state = harness.adapter._generations[turn.process_generation_id]
    assert turn.turn_id in state.audited_native_helper_turns


def test_native_helper_hidden_model_override_fails_effect_unknown(
    tmp_path: Path,
) -> None:
    harness = _make_harness(
        tmp_path,
        native_helper=True,
        extra_env={"OHF_FAKE_NATIVE_HELPER_MODEL_OVERRIDE": "1"},
    )
    _, _, launch = _start(harness)
    turn = TurnRef("turn-helper-drift", "epoch-1", "gen-1", "attempt-1")

    with pytest.raises(CodexAdapterError, match="hidden identity override") as excinfo:
        harness.adapter.begin_turn(
            operation_id=_op("native-helper-model-drift"),
            turn=turn,
            generation=harness.generation,
            launch=launch,
        )
        harness.adapter.read_events(
            EventCursor("attempt-1", "epoch-1", "gen-1", turn_id=turn.turn_id)
        )

    assert excinfo.value.failure_class is AdapterFailureClass.CONFIG_DRIFT
    assert excinfo.value.effect_unknown is True


def test_native_helper_depth_drift_fails_tree_reconciliation(
    tmp_path: Path,
) -> None:
    harness = _make_harness(
        tmp_path,
        native_helper=True,
        extra_env={"OHF_FAKE_NATIVE_HELPER_DEPTH": "2"},
    )
    _, _, launch = _start(harness)
    turn = TurnRef("turn-helper-depth", "epoch-1", "gen-1", "attempt-1")
    harness.adapter.begin_turn(
        operation_id=_op("native-helper-depth-drift"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )

    with pytest.raises(CodexAdapterError, match="escaped its parent ceiling") as excinfo:
        harness.adapter.read_events(
            EventCursor("attempt-1", "epoch-1", "gen-1", turn_id=turn.turn_id)
        )

    assert excinfo.value.failure_class is AdapterFailureClass.CONFIG_DRIFT
    assert excinfo.value.effect_unknown is True


def test_requested_and_observed_profiles_remain_separate_and_drift_refuses(
    harness: Harness,
) -> None:
    _, observed, launch = _start(harness)
    assert launch.decision is LaunchDecision.ALLOW
    assert observed.harness_version == harness.requested.harness_version
    assert observed.harness_binary_digest == harness.requested.harness_binary_digest

    drifted = replace(harness.requested, expected_config_digest="0" * 64)
    drift_launch = compare_launch(drifted, observed)
    assert drift_launch.decision is LaunchDecision.REFUSE_CONFIG_DRIFT
    assert observed.effective_config_digest != drifted.expected_config_digest


def test_network_attestation_is_derived_from_observed_config_not_constructor(
    tmp_path: Path,
) -> None:
    harness = _make_harness(tmp_path, network_policy="restricted")
    assert harness.adapter.validate_requested_profile(harness.requested).accepted

    _, observed, launch = _start(harness)

    assert observed.network_state == "disabled"
    assert launch.decision is LaunchDecision.REFUSE_NETWORK_MISMATCH


@pytest.mark.parametrize("unexpected_environment_key", [None, "UNREVIEWED_BROWSER_AUTHORITY"])
def test_browser_resource_is_bound_before_client_and_attested_before_first_turn(
    tmp_path: Path,
    unexpected_environment_key: str | None,
) -> None:
    launched_env: dict[str, str] = {}

    def factory(argv, env, cwd):
        launched_env.update(env)
        return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)

    harness = _make_harness(
        tmp_path,
        client_factory=factory,
        network_policy="loopback-browser-only",
    )
    resource_digest = "f" * 64
    requested_resource = CapabilityIdentity(
        kind="resource",
        name="worker-browser-b1-local",
        harness_binary_digest=harness.adapter.binary_digest,
        resource_contract_digest=resource_digest,
    )
    harness.requested = replace(
        harness.requested,
        capabilities=CapabilityManifest(
            required=(requested_resource,),
            unclassified_policy="lab_allow_unclassified_readonly",
        ),
    )

    resource_environment = {
        "MASTERMIND_BROWSER_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "MASTERMIND_BROWSER_FIXTURE_A_URL": (
            "http://127.0.0.1:43123/__mastermind_browser_visual_fixture__/"
            + "a" * 32
        ),
        "MASTERMIND_BROWSER_FIXTURE_B_URL": (
            "http://127.0.0.1:43123/__mastermind_browser_visual_fixture__/"
            + "b" * 32
        ),
        "MASTERMIND_BROWSER_FIXTURE_NONCE": "c" * 32,
        "MASTERMIND_BROWSER_ORIGIN": "http://127.0.0.1:43123",
        "MASTERMIND_BROWSER_PROXY_URL": "http://127.0.0.1:43124",
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": str(
            tmp_path / "runtime" / "worker-browser-b1-install-manifest.json"
        ),
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": "d" * 64,
        "MASTERMIND_BROWSER_RUNTIME_ROOT": str(tmp_path / "runtime"),
        "MASTERMIND_BROWSER_WORKSPACE_PATH": str(tmp_path),
        "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "runtime" / "browsers"),
    }
    if unexpected_environment_key is not None:
        resource_environment[unexpected_environment_key] = "must-refuse"

    class Resource:
        attempt_id = harness.epoch.attempt_id
        session_epoch_id = harness.epoch.session_epoch_id
        process_generation_id = harness.generation.process_generation_id
        network_state = "loopback-browser-only"
        environment = resource_environment
        observed_capability = ObservedCapabilityIdentity(
            kind="resource",
            name="worker-browser-b1-local",
            resource_contract_digest=resource_digest,
        )

    if unexpected_environment_key is not None:
        with pytest.raises(
            CodexAdapterError,
            match="browser resource environment is not the reviewed closed binding",
        ):
            harness.adapter.bind_attempt_resource(
                Resource(),
                requested=harness.requested,
                epoch=harness.epoch,
                generation=harness.generation,
            )
        return

    harness.adapter.bind_attempt_resource(
        Resource(),
        requested=harness.requested,
        epoch=harness.epoch,
        generation=harness.generation,
    )
    _observation, observed, launch = _start(harness)

    assert launch.decision is LaunchDecision.ALLOW
    assert Resource.observed_capability in observed.capabilities
    assert observed.network_state == "loopback-browser-only"
    assert launched_env["MASTERMIND_BROWSER_ORIGIN"] == "http://127.0.0.1:43123"
    assert launched_env["MASTERMIND_BROWSER_FIXTURE_NONCE"] == "c" * 32


def test_browser_resource_binding_freezes_first_closed_property_snapshot(
    tmp_path: Path,
) -> None:
    """A mutable resource property cannot widen authority after bind validation."""

    launched_env: dict[str, str] = {}

    def factory(argv, env, cwd):
        launched_env.update(env)
        return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)

    harness = _make_harness(
        tmp_path,
        client_factory=factory,
        network_policy="loopback-browser-only",
    )
    resource_digest = "f" * 64
    expected_observed = ObservedCapabilityIdentity(
        kind="resource",
        name="worker-browser-b1-local",
        resource_contract_digest=resource_digest,
    )
    requested_resource = CapabilityIdentity(
        kind="resource",
        name="worker-browser-b1-local",
        harness_binary_digest=harness.adapter.binary_digest,
        resource_contract_digest=resource_digest,
    )
    harness.requested = replace(
        harness.requested,
        capabilities=CapabilityManifest(
            required=(requested_resource,),
            unclassified_policy="lab_allow_unclassified_readonly",
        ),
    )
    closed_environment = {
        "MASTERMIND_BROWSER_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "MASTERMIND_BROWSER_FIXTURE_A_URL": "http://127.0.0.1:43123/a",
        "MASTERMIND_BROWSER_FIXTURE_B_URL": "http://127.0.0.1:43123/b",
        "MASTERMIND_BROWSER_FIXTURE_NONCE": "c" * 32,
        "MASTERMIND_BROWSER_ORIGIN": "http://127.0.0.1:43123",
        "MASTERMIND_BROWSER_PROXY_URL": "http://127.0.0.1:43124",
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": str(
            tmp_path / "runtime" / "worker-browser-b1-install-manifest.json"
        ),
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": "d" * 64,
        "MASTERMIND_BROWSER_RUNTIME_ROOT": str(tmp_path / "runtime"),
        "MASTERMIND_BROWSER_WORKSPACE_PATH": str(tmp_path),
        "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "runtime" / "browsers"),
    }
    reads = {"environment": 0, "network_state": 0, "observed_capability": 0}

    class ChangingResource:
        attempt_id = harness.epoch.attempt_id
        session_epoch_id = harness.epoch.session_epoch_id
        process_generation_id = harness.generation.process_generation_id

        @property
        def environment(self):
            reads["environment"] += 1
            if reads["environment"] == 1:
                return dict(closed_environment)
            return {
                **closed_environment,
                "HOME": "/tmp/poison-home",
                "CODEX_HOME": "/tmp/poison-codex-home",
                "PATH": "/tmp/poison-path",
            }

        @property
        def network_state(self):
            reads["network_state"] += 1
            return "loopback-browser-only"

        @property
        def observed_capability(self):
            reads["observed_capability"] += 1
            return expected_observed

    resource = ChangingResource()
    harness.adapter.bind_attempt_resource(
        resource,
        requested=harness.requested,
        epoch=harness.epoch,
        generation=harness.generation,
    )
    _observation, observed, launch = _start(harness)

    assert launch.decision is LaunchDecision.ALLOW
    assert expected_observed in observed.capabilities
    assert observed.network_state == "loopback-browser-only"
    assert reads == {
        "environment": 1,
        "network_state": 1,
        "observed_capability": 1,
    }
    assert launched_env["HOME"] == str(harness.adapter.codex_home)
    assert launched_env["CODEX_HOME"] == str(harness.adapter.codex_home)
    assert launched_env["PATH"] != "/tmp/poison-path"


def test_profile_drift_and_write_capability_fail_before_process_call(
    tmp_path: Path,
) -> None:
    calls = 0

    def factory(argv, env, cwd):
        nonlocal calls
        calls += 1
        return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)

    harness = _make_harness(tmp_path, client_factory=factory)
    drifted = replace(harness.requested, harness_binary_digest="0" * 64)
    write_profile = replace(
        harness.requested, write_capable=True, allowed_write_paths=("/tmp",)
    )

    assert not harness.adapter.validate_requested_profile(drifted).accepted
    assert not harness.adapter.validate_requested_profile(write_profile).accepted
    assert calls == 0


def test_observed_harness_version_drift_fails_after_initialize(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path, harness_version="unexpected/version")
    assert harness.adapter.validate_requested_profile(harness.requested).accepted

    with pytest.raises(CodexAdapterError) as caught:
        _start(harness)

    assert (
        caught.value.failure_class is AdapterFailureClass.CAPABILITY_ATTESTATION_FAILURE
    )
    assert caught.value.effect_unknown is True


def test_auth_marker_is_only_statted_and_parent_credentials_are_not_inherited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured_env: dict[str, str] = {}

    def factory(argv, env, cwd):
        captured_env.update(env)
        return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)

    monkeypatch.setenv("OPENAI_API_KEY", "must-not-cross-boundary")
    harness = _make_harness(tmp_path, client_factory=factory)
    auth_path = harness.adapter.codex_home / "auth.json"
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path == auth_path:
            raise AssertionError("adapter attempted to read credential bytes")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    _start(harness)

    assert captured_env["CODEX_HOME"] == str(harness.adapter.codex_home)
    assert "OPENAI_API_KEY" not in captured_env


def test_default_home_and_symlinked_auth_are_refused(tmp_path: Path) -> None:
    python = Path(sys.executable).resolve()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    default_home = (Path.home() / ".codex").resolve()
    with pytest.raises(CodexAdapterError, match="default CODEX_HOME"):
        CodexOperatorAdapter(
            binary_path=python,
            codex_home=default_home,
            workspace_root=workspace,
            worker_id="slot-a",
            expected_harness_version="codex/1",
        )


def test_credential_boundary_rejects_hardlinks_modes_and_symlinked_ancestors(
    tmp_path: Path,
) -> None:
    python = Path(sys.executable).resolve()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    auth = home / "auth.json"
    auth.write_text("fixture", encoding="utf-8")
    auth.chmod(0o600)
    hardlink = tmp_path / "auth-copy"
    os.link(auth, hardlink)
    with pytest.raises(CodexAdapterError, match="singly linked"):
        CodexOperatorAdapter(
            binary_path=python,
            codex_home=home,
            workspace_root=workspace,
            worker_id="slot-a",
            expected_harness_version="codex/1",
        )
    hardlink.unlink()

    home.chmod(0o755)
    with pytest.raises(CodexAdapterError, match="mode 0700"):
        CodexOperatorAdapter(
            binary_path=python,
            codex_home=home,
            workspace_root=workspace,
            worker_id="slot-a",
            expected_harness_version="codex/1",
        )
    home.chmod(0o700)
    auth.chmod(0o644)
    with pytest.raises(CodexAdapterError, match="private, owned"):
        CodexOperatorAdapter(
            binary_path=python,
            codex_home=home,
            workspace_root=workspace,
            worker_id="slot-a",
            expected_harness_version="codex/1",
        )
    auth.chmod(0o600)

    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(tmp_path)
    with pytest.raises(CodexAdapterError, match="symlink component"):
        CodexOperatorAdapter(
            binary_path=python,
            codex_home=linked_parent / "home",
            workspace_root=workspace,
            worker_id="slot-a",
            expected_harness_version="codex/1",
        )

    dedicated = tmp_path / "dedicated"
    dedicated.mkdir()
    dedicated.chmod(0o700)
    target = tmp_path / "outside-auth"
    target.write_text("fixture", encoding="utf-8")
    (dedicated / "auth.json").symlink_to(target)
    with pytest.raises(CodexAdapterError, match="private, owned, and singly linked"):
        CodexOperatorAdapter(
            binary_path=python,
            codex_home=dedicated,
            workspace_root=workspace,
            worker_id="slot-a",
            expected_harness_version="codex/1",
        )

    regular_home = tmp_path / "regular-home"
    regular_home.mkdir()
    regular_home.chmod(0o700)
    (regular_home / "auth.json").write_text("fixture", encoding="utf-8")
    (regular_home / "auth.json").chmod(0o600)
    binary_link = tmp_path / "codex-link"
    binary_link.symlink_to(python)
    with pytest.raises(CodexAdapterError, match="symlink component"):
        CodexOperatorAdapter(
            binary_path=binary_link,
            codex_home=regular_home,
            workspace_root=workspace,
            worker_id="slot-a",
            expected_harness_version="codex/1",
        )


def test_active_writer_conflict_refuses_second_local_process(tmp_path: Path) -> None:
    process_calls = 0

    def factory(argv, env, cwd):
        nonlocal process_calls
        process_calls += 1
        return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)

    harness = _make_harness(tmp_path, client_factory=factory)
    _start(harness)
    generation2 = ProcessGenerationRef("gen-2", "epoch-1", 2, "slot-a")

    with pytest.raises(CodexAdapterError) as caught:
        harness.adapter.start_session(
            operation_id=_op("conflict"),
            requested=harness.requested,
            epoch=harness.epoch,
            generation=generation2,
        )

    assert caught.value.failure_class is AdapterFailureClass.ACTIVE_WRITER_CONFLICT
    assert process_calls == 1


def test_delayed_turn_can_be_interrupted_after_start_ack_before_completion(
    tmp_path: Path,
) -> None:
    harness = _make_harness(
        tmp_path,
        fault_server=True,
        extra_env={"OHF_FAKE_DELAY_COMPLETION": "1"},
    )
    _, _, launch = _start(harness)
    turn = TurnRef(
        "turn-delayed",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )
    started = harness.adapter.begin_turn(
        operation_id=_op("delayed"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )
    assert started.acknowledged and started.provider_native_turn_id
    harness.adapter.interrupt_turn(turn, operation_id=_op("interrupt"))
    events, _ = harness.adapter.read_events(
        EventCursor(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            turn_id=turn.turn_id,
        ),
        timeout_seconds=1.0,
    )
    assert any(event.kind == "turn/completed" for event in events)


def test_blocked_read_events_and_interrupt_demultiplex_response_and_completion(
    tmp_path: Path,
) -> None:
    harness = _make_harness(
        tmp_path,
        fault_server=True,
        extra_env={"OHF_FAKE_DELAY_COMPLETION": "1"},
    )
    _, _, launch = _start(harness)
    turn = TurnRef(
        "turn-concurrent",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )
    harness.adapter.begin_turn(
        operation_id=_op("concurrent-start"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )
    client = harness.adapter._state(harness.generation).client
    entered_wait = threading.Event()
    original_wait = client.wait_notification

    def wait_notification(method: str, *, timeout: float = 15.0):
        entered_wait.set()
        return original_wait(method, timeout=timeout)

    client.wait_notification = wait_notification  # type: ignore[method-assign]
    result: dict[str, object] = {}

    def read() -> None:
        try:
            result["value"] = harness.adapter.read_events(
                EventCursor(
                    turn.attempt_id,
                    turn.session_epoch_id,
                    turn.process_generation_id,
                    turn_id=turn.turn_id,
                ),
                timeout_seconds=2.0,
            )
        except BaseException as exc:  # test must surface background failures
            result["error"] = exc

    reader = threading.Thread(target=read)
    reader.start()
    assert entered_wait.wait(timeout=1.0), "read_events did not block on completion"
    harness.adapter.interrupt_turn(turn, operation_id=_op("concurrent-interrupt"))
    reader.join(timeout=2.0)

    assert not reader.is_alive(), "completion notification was lost"
    assert "error" not in result
    events, cursor = result["value"]  # type: ignore[misc]
    assert cursor.local_sequence == len(events)
    assert any(event.kind == "turn/completed" for event in events)
    assert all(event.payload_redacted == {"method": event.kind} for event in events)


@pytest.mark.parametrize("operation", ("cancel", "close"))
def test_private_group_shutdown_reaps_descendant_without_signaling_controller_group(
    tmp_path: Path, operation: str
) -> None:
    child_pid_file = tmp_path / "descendant.pid"
    child_ready_file = tmp_path / "descendant.ready"
    harness = _make_harness(
        tmp_path,
        fault_server=True,
        extra_env={
            "OHF_FAKE_SPAWN_DESCENDANT": "1",
            "OHF_FAKE_CHILD_PID_FILE": str(child_pid_file),
            "OHF_FAKE_CHILD_READY_FILE": str(child_ready_file),
        },
    )
    _start(harness)
    client = harness.adapter._state(harness.generation).client
    controller_pgid = os.getpgrp()
    assert child_pid_file.is_file()
    ready_deadline = time.monotonic() + 2.0
    while not child_ready_file.is_file():
        if time.monotonic() >= ready_deadline:
            pytest.fail("contained descendant did not report ready")
        time.sleep(0.01)
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    assert client.pid is not None
    assert client._private_pgid == client.pid
    assert client._private_pgid != controller_pgid
    assert os.getpgid(child_pid) == client._private_pgid

    if operation == "cancel":
        harness.adapter.cancel(
            harness.generation,
            reason="contained-fault",
            operation_id=_op("cancel-contained"),
        )
    else:
        client.close()

    assert client.last_termination_outcome == "sigterm-escalated-kill"
    assert os.getpgrp() == controller_pgid
    assert not client.private_group_alive()
    deadline = time.monotonic() + 2.0
    while True:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            pytest.fail("contained descendant survived group termination")
        time.sleep(0.02)


def test_graceful_stop_releases_only_after_leader_zero_descendant_is_reaped(
    tmp_path: Path,
) -> None:
    child_pid_file = tmp_path / "graceful-descendant.pid"
    child_ready_file = tmp_path / "graceful-descendant.ready"
    harness = _make_harness(
        tmp_path,
        fault_server=True,
        extra_env={
            "OHF_FAKE_SPAWN_DESCENDANT": "1",
            "OHF_FAKE_CHILD_PID_FILE": str(child_pid_file),
            "OHF_FAKE_CHILD_READY_FILE": str(child_ready_file),
        },
    )
    _start(harness)
    client = harness.adapter._state(harness.generation).client
    ready_deadline = time.monotonic() + 2.0
    while not child_ready_file.is_file():
        if time.monotonic() >= ready_deadline:
            pytest.fail("graceful-stop descendant did not report ready")
        time.sleep(0.01)
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    assert client.private_group_alive()
    proofs = []
    original_graceful_close = client.graceful_close

    def graceful_close(*, wait: float = 5.0):
        proof = original_graceful_close(wait=wait)
        proofs.append(proof)
        return proof

    client.graceful_close = graceful_close  # type: ignore[method-assign]

    stopped = harness.adapter.graceful_stop(
        harness.generation,
        operation_id=_op("graceful-contained"),
    )

    assert client.proc is not None
    assert client.proc.returncode == 0
    assert len(proofs) == 1
    assert proofs[0].leader_exit_confirmed_graceful is True
    assert proofs[0].survivors_detected_after_controller_exit is True
    assert proofs[0].private_group_empty is True
    assert client.last_termination_outcome == "sigterm-escalated-kill"
    assert not client.private_group_alive()
    assert stopped.process_liveness is ProcessLiveness.PROVEN_DEAD
    assert stopped.provider_writer_state is ProviderWriterState.RELEASED
    assert harness.adapter._active_workers.get("slot-a") is None
    deadline = time.monotonic() + 2.0
    while True:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            pytest.fail("leader exited 0 but same-group descendant survived")
        time.sleep(0.02)


def test_start_refuses_uncontained_process_before_any_release_claim(
    tmp_path: Path,
) -> None:
    def uncontained_factory(argv, env, cwd):
        return AppServerClient(argv, env=env, cwd=cwd)

    harness = _make_harness(tmp_path, client_factory=uncontained_factory)

    with pytest.raises(CodexAdapterError) as caught:
        harness.adapter.start_session(
            operation_id=_op("uncontained-start"),
            requested=harness.requested,
            epoch=harness.epoch,
            generation=harness.generation,
        )

    assert caught.value.failure_class is AdapterFailureClass.PROCESS_CRASH
    assert caught.value.effect_unknown is True
    assert harness.adapter._active_workers == {}


def test_candidate_and_adapter_events_redact_provider_secret_content(
    tmp_path: Path,
) -> None:
    secret = (
        "sk-proj-OHFADAPTERSECRET0123456789 "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvaGYifQ.signaturepaddingxx "
        "provider@example.invalid"
    )
    harness = _make_harness(
        tmp_path,
        fault_server=True,
        extra_env={"OHF_FAKE_SECRET_CANDIDATE": secret},
    )
    _, _, launch = _start(harness)
    turn = TurnRef("turn-redacted", "epoch-1", "gen-1", "attempt-1")
    harness.adapter.begin_turn(
        operation_id=_op("redacted-turn"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )
    events, _ = harness.adapter.read_events(
        EventCursor("attempt-1", "epoch-1", "gen-1", turn_id="turn-redacted")
    )
    candidate = harness.adapter.collect_candidate_result(turn)
    rendered = repr((candidate, events))
    for value in (
        "sk-proj-OHFADAPTERSECRET0123456789",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvaGYifQ.signaturepaddingxx",
        "provider@example.invalid",
    ):
        assert value not in rendered
    assert candidate.summary is not None
    assert REDACTED in candidate.summary


def test_cancel_does_not_invent_provider_release_or_allow_writer_steal(
    tmp_path: Path,
) -> None:
    process_calls = 0

    def factory(argv, env, cwd):
        nonlocal process_calls
        process_calls += 1
        return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)

    harness = _make_harness(tmp_path, client_factory=factory)
    _start(harness)
    cancelled = harness.adapter.cancel(
        harness.generation, reason="fault", operation_id=_op("cancel")
    )
    assert cancelled.process_liveness is ProcessLiveness.PROVEN_DEAD
    assert cancelled.provider_writer_state is ProviderWriterState.UNKNOWN

    generation2 = ProcessGenerationRef("gen-2", "epoch-1", 2, "slot-a")
    with pytest.raises(CodexAdapterError) as caught:
        harness.adapter.start_session(
            operation_id=_op("writer-steal"),
            requested=harness.requested,
            epoch=harness.epoch,
            generation=generation2,
        )
    assert caught.value.failure_class is AdapterFailureClass.ACTIVE_WRITER_CONFLICT
    assert process_calls == 1


def test_missing_and_mismatched_resume_fail_closed(tmp_path: Path) -> None:
    missing = _make_harness(tmp_path / "missing")
    generation2 = ProcessGenerationRef("gen-2", "epoch-1", 2, "slot-a")
    with pytest.raises(CodexAdapterError) as caught:
        missing.adapter.resume_session(
            operation_id=_op("resume-missing"),
            epoch=missing.epoch,
            generation=generation2,
            provider_session=ProviderSessionHandoff("not-there", "slot-a"),
            requested=missing.requested,
        )
    assert caught.value.failure_class is AdapterFailureClass.SESSION_MISSING

    first = _make_harness(tmp_path / "mismatch-source")
    observation, _, _ = _start(first)
    first.adapter.graceful_stop(first.generation, operation_id=_op("stop"))
    mismatch = _make_harness(
        tmp_path / "mismatch-source",
        fault_server=True,
        extra_env={"OHF_FAKE_RESUME_MISMATCH": "1"},
    )
    with pytest.raises(CodexAdapterError) as mismatch_error:
        mismatch.adapter.resume_session(
            operation_id=_op("resume-mismatch"),
            epoch=mismatch.epoch,
            generation=generation2,
            provider_session=ProviderSessionHandoff(
                str(observation.provider_session_id), "slot-a"
            ),
            requested=mismatch.requested,
        )
    assert (
        mismatch_error.value.failure_class is AdapterFailureClass.ACTIVE_WRITER_CONFLICT
    )


def test_rate_limit_and_process_crash_have_exact_failure_classes(
    tmp_path: Path,
) -> None:
    limited = _make_harness(
        tmp_path / "limited",
        fault_server=True,
        extra_env={"OHF_FAKE_RATE_LIMIT": "1"},
    )
    _, observed, launch = _start(limited)
    assert observed.served_model == limited.requested.requested_model
    turn = TurnRef("turn-1", "epoch-1", "gen-1", "attempt-1")
    with pytest.raises(CodexAdapterError) as rate_error:
        limited.adapter.begin_turn(
            operation_id=_op("rate"),
            turn=turn,
            generation=limited.generation,
            launch=launch,
        )
    assert rate_error.value.failure_class is AdapterFailureClass.QUOTA_OR_RATE_LIMIT
    assert rate_error.value.effect_unknown is True

    crashed = _make_harness(tmp_path / "crashed", extra_env={"OHF_FAKE_DIE_AFTER": "7"})
    _, _, crash_launch = _start(crashed)
    with pytest.raises(CodexAdapterError) as crash_error:
        crashed.adapter.begin_turn(
            operation_id=_op("crash"),
            turn=turn,
            generation=crashed.generation,
            launch=crash_launch,
        )
    assert crash_error.value.failure_class is AdapterFailureClass.PROCESS_CRASH
    assert crash_error.value.effect_unknown is True


def test_restart_reconciliation_never_adopts_stdio_and_resumes_only_bound_s1(
    tmp_path: Path,
) -> None:
    first = _make_harness(tmp_path)
    started, _, _ = _start(first)
    stopped = first.adapter.graceful_stop(first.generation, operation_id=_op("stop"))
    assert stopped.provider_writer_state is ProviderWriterState.RELEASED

    replacement = _make_harness(tmp_path)
    unknown = replacement.adapter.reconcile(first.generation)
    assert unknown.process_liveness is ProcessLiveness.UNKNOWN
    assert unknown.provider_writer_state is ProviderWriterState.UNKNOWN
    assert unknown.recommended_failure_class is AdapterFailureClass.SESSION_MISSING

    generation2 = ProcessGenerationRef("gen-2", "epoch-1", 2, "slot-a")
    resumed = replacement.adapter.resume_session(
        operation_id=_op("resume"),
        epoch=replacement.epoch,
        generation=generation2,
        provider_session=ProviderSessionHandoff(
            str(started.provider_session_id), "slot-a"
        ),
        requested=replacement.requested,
    )
    assert resumed.provider_session_id == started.provider_session_id
    assert resumed.process.pid != started.process.pid
    replacement.adapter.graceful_stop(generation2, operation_id=_op("stop-2"))


def test_event_cursor_is_generation_scoped_and_candidate_is_never_completion(
    harness: Harness,
) -> None:
    _, _, launch = _start(harness)
    turn = TurnRef("turn-1", "epoch-1", "gen-1", "attempt-1")
    started = harness.adapter.begin_turn(
        operation_id=_op("turn"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )
    events, cursor = harness.adapter.read_events(
        EventCursor("attempt-1", "epoch-1", "gen-1", turn_id="turn-1")
    )
    candidate = harness.adapter.collect_candidate_result(turn)

    assert started.acknowledged and started.provider_native_turn_id
    assert events and cursor.local_sequence == len(events)
    assert all(event.process_generation_id == "gen-1" for event in events)
    assert candidate.complete_job_permitted is False
    with pytest.raises(CodexAdapterError):
        harness.adapter.read_events(
            EventCursor("wrong-attempt", "epoch-1", "gen-1", turn_id="turn-1")
        )


def test_orchestration_principal_observations_bind_exact_launched_process_and_home(
    harness: Harness,
) -> None:
    started, _, _ = _start(harness)

    process = harness.adapter.observe_process_credentials(harness.generation)
    provider_home = harness.adapter.observe_provider_home_identity(harness.generation)

    assert process.process_identity == {
        "pid": started.process.pid,
        "pgid": started.process.pgid,
        "process_start_identity": started.process.process_start_identity,
        "boot_id": started.process.boot_id,
    }
    assert process.os_principal_uid == os.getuid()
    assert process.os_principal_name
    assert provider_home.provider_home_identity["path"] == str(
        harness.adapter.codex_home
    )
    assert provider_home.provider_home_identity["mode"] == 0o700


def test_private_raw_role_result_is_canonical_lossless_and_digest_bound(
    tmp_path: Path,
) -> None:
    envelope = {
        "schema_version": "mastermind.executive_orchestration_result/v1",
        "job_id": "JOB-PLAN",
        "attempt_id": "ATT-PLAN",
        "role": "plan",
        "worker_id": "slot-a",
        "provider": "openai-codex",
        "account_label": "slot-a@company",
        "process_generation_id": "gen-1",
        "provider_session_id": "session-fixture",
        "role_result": {
            "schema_version": "mastermind.execution_plan/v1",
            "root_job_id": "JOB-ROOT",
            "plan_attempt_id": "ATT-PLAN",
            "steps": [
                {
                    "ordinal": 0,
                    "step_id": "STEP-1",
                    "objective": "Perform one bounded read-only task.",
                    "business_impact": "routine",
                    "review_required": False,
                    "requested_authorities": ["READ"],
                    "allowed_write_paths": [],
                    "validation_ids": [],
                    "attempt_limit": 1,
                    "cost_class": "small",
                }
            ],
        },
    }
    canonical = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    harness = _make_harness(
        tmp_path,
        extra_env={"OHF_FAKE_TURN_REPLY": canonical},
        turn_input="Produce the exact closed planning result.",
    )
    _, _, launch = _start(harness)
    turn = TurnRef("turn-1", "epoch-1", "gen-1", "attempt-1")
    started = harness.adapter.begin_turn(
        operation_id=_op("raw-turn"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )
    candidate = harness.adapter.collect_candidate_result(turn)

    observation = harness.adapter.observe_raw_role_result(turn)

    assert observation.provider_native_turn_id == started.provider_native_turn_id
    assert observation.provider_turn_artifact_digest == candidate.artifact_digest
    assert observation.canonical_result_json == canonical
    assert observation.canonical_result_digest == hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    assert observation.canonical_result_byte_length == len(canonical.encode("utf-8"))
    assert canonical not in repr(observation)


def _raw_turn_fixture(tmp_path: Path, *, reply: str):
    harness = _make_harness(
        tmp_path,
        extra_env={"OHF_FAKE_TURN_REPLY": reply},
        turn_input="Produce the exact closed result.",
    )
    _, _, launch = _start(harness)
    turn = TurnRef("turn-1", "epoch-1", "gen-1", "attempt-1")
    started = harness.adapter.begin_turn(
        operation_id=_op("raw-pagination-turn"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )
    harness.adapter.collect_candidate_result(turn)
    state = harness.adapter._generations[turn.process_generation_id]
    ordinary = state.client.request(
        "thread/turns/list", {"threadId": state.provider_session_id}
    )
    row = next(item for item in ordinary["data"] if item["id"] == started.provider_native_turn_id)
    return harness, state, turn, row


def test_raw_turn_paginates_to_end_and_refuses_duplicate_match(
    tmp_path: Path, monkeypatch
) -> None:
    canonical = json.dumps({"safe": True}, sort_keys=True, separators=(",", ":"))
    harness, state, turn, row = _raw_turn_fixture(tmp_path, reply=canonical)
    pages = iter(
        [
            PrivateRawTurnPage({"data": [row], "nextCursor": "cursor-2"}, 10),
            PrivateRawTurnPage({"data": [row], "nextCursor": None}, 10),
        ]
    )
    monkeypatch.setattr(state.client, "request_raw_turn_page", lambda **_kwargs: next(pages))

    with pytest.raises(CodexAdapterError, match="missing or ambiguous"):
        harness.adapter.observe_raw_role_result(turn)


@pytest.mark.parametrize("next_cursor", [17, "", " repeated "])
def test_raw_turn_refuses_malformed_cursor(
    tmp_path: Path, monkeypatch, next_cursor
) -> None:
    canonical = json.dumps({"safe": True}, sort_keys=True, separators=(",", ":"))
    harness, state, turn, _row = _raw_turn_fixture(tmp_path, reply=canonical)
    monkeypatch.setattr(
        state.client,
        "request_raw_turn_page",
        lambda **_kwargs: PrivateRawTurnPage(
            {"data": [], "nextCursor": next_cursor}, 10
        ),
    )

    with pytest.raises(CodexAdapterError, match="cursor is malformed"):
        harness.adapter.observe_raw_role_result(turn)


def test_raw_turn_refuses_repeated_cursor_and_closed_page_exhaustion(
    tmp_path: Path, monkeypatch
) -> None:
    canonical = json.dumps({"safe": True}, sort_keys=True, separators=(",", ":"))
    harness, state, turn, _row = _raw_turn_fixture(tmp_path, reply=canonical)
    monkeypatch.setattr(
        state.client,
        "request_raw_turn_page",
        lambda **_kwargs: PrivateRawTurnPage(
            {"data": [], "nextCursor": "cursor-repeat"}, 10
        ),
    )
    with pytest.raises(CodexAdapterError, match="cursor is malformed or repeated"):
        harness.adapter.observe_raw_role_result(turn)

    calls = iter(range(3))

    def endless_pages(**_kwargs):
        index = next(calls)
        return PrivateRawTurnPage({"data": [], "nextCursor": f"cursor-{index}"}, 10)

    monkeypatch.setattr(codex_operator_adapter, "MAX_RAW_TURN_PAGES", 2)
    monkeypatch.setattr(state.client, "request_raw_turn_page", endless_pages)
    with pytest.raises(CodexAdapterError, match="closed page bound"):
        harness.adapter.observe_raw_role_result(turn)


def test_raw_result_validation_error_never_exposes_secret_shaped_key(
    tmp_path: Path,
) -> None:
    secret = "sk-phase1fc-secret-shaped-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    noncanonical = f'{{"{secret}":1,"{secret}":2}}'
    harness, _state, turn, _row = _raw_turn_fixture(tmp_path, reply=noncanonical)

    with pytest.raises(CodexAdapterError, match="canonical validation failed") as excinfo:
        harness.adapter.observe_raw_role_result(turn)

    assert secret not in str(excinfo.value)
    assert secret not in repr(excinfo.value)


def test_constructor_and_import_do_not_start_or_register_provider(
    tmp_path: Path,
) -> None:
    calls = 0

    def factory(argv, env, cwd):
        nonlocal calls
        calls += 1
        return AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)

    harness = _make_harness(tmp_path, client_factory=factory)
    assert calls == 0
    assert isinstance(harness.adapter, OperatorHarnessAdapter)
    assert isinstance(harness.adapter, SupportsSessionResume)
    assert not isinstance(harness.adapter, SupportsNativeFork)
    assert (
        "resume_session"
        in harness.adapter.describe_capabilities().supported_optional_operations
    )
    assert (
        "fork_session"
        not in harness.adapter.describe_capabilities().supported_optional_operations
    )
    assert harness.adapter.describe_capabilities().supports_native_fork is False
    assert not harness.adapter.describe_capabilities().supports_config_staging


# ---------------------------------------------------------------------------
# CAP-S1: skill_canary_binding constructor validation (protocol-attestation
# amendment §7)
# ---------------------------------------------------------------------------


def test_skill_canary_binding_constructor_validation_matrix(tmp_path: Path) -> None:
    good_binding = _stage_cap_s1_binding(tmp_path)
    scaffold = _make_harness(tmp_path / "ctor-scaffold")

    def _adapter(binding: CodexSkillCanaryBinding) -> CodexOperatorAdapter:
        return CodexOperatorAdapter(
            binary_path=scaffold.adapter.binary_path,
            codex_home=scaffold.adapter.codex_home,
            workspace_root=scaffold.adapter.workspace_root,
            worker_id="slot-a",
            expected_harness_version=scaffold.requested.harness_version,
            base_sha_resolver=lambda path: "b" * 40,
            skill_canary_binding=binding,
        )

    # The unmodified binding constructs cleanly.
    _adapter(good_binding)

    mismatched = replace(
        good_binding,
        projection=replace(
            good_binding.projection,
            skill_content_digests=(
                ("mastermind-operator.escalate-decision.v1", "0" * 64),
            ),
        ),
    )
    with pytest.raises(CodexAdapterError, match="grants do not match"):
        _adapter(mismatched)

    bad_generation_digest = replace(
        good_binding,
        projection=replace(
            good_binding.projection, package_generation_digest="1" * 64
        ),
    )
    with pytest.raises(CodexAdapterError, match="does not match the package generation"):
        _adapter(bad_generation_digest)

    # --- B3: typed protocol attestation receipt falsifiers -----------------

    forged_binary_digest = replace(
        good_binding,
        protocol_receipt=replace(good_binding.protocol_receipt, binary_digest="0" * 64),
    )
    with pytest.raises(CodexAdapterError, match="binary digest mismatch"):
        _adapter(forged_binary_digest)

    bad_binary_version = replace(
        good_binding,
        protocol_receipt=replace(
            good_binding.protocol_receipt, binary_version="wrong-harness/version"
        ),
    )
    with pytest.raises(CodexAdapterError, match="binary version mismatch"):
        _adapter(bad_binary_version)

    bad_inventory_digest = replace(
        good_binding,
        protocol_receipt=replace(
            good_binding.protocol_receipt, stable_inventory_digest="not-a-digest"
        ),
    )
    with pytest.raises(CodexAdapterError, match="inventory digest is invalid"):
        _adapter(bad_inventory_digest)

    same_inventory_digests = replace(
        good_binding,
        protocol_receipt=replace(
            good_binding.protocol_receipt,
            experimental_inventory_digest=good_binding.protocol_receipt.stable_inventory_digest,
        ),
    )
    with pytest.raises(CodexAdapterError, match="must be distinct"):
        _adapter(same_inventory_digests)

    missing_schema_evidence = replace(
        good_binding,
        protocol_receipt=replace(
            good_binding.protocol_receipt,
            supports_skill_input_path=True,
            skill_input_schema_evidence="",
        ),
    )
    with pytest.raises(CodexAdapterError, match="schema evidence is required"):
        _adapter(missing_schema_evidence)

    arbitrary_schema_evidence_receipt = build_protocol_attestation_receipt(
        binary_path=good_binding.protocol_receipt.binary_path,
        binary_digest=good_binding.protocol_receipt.binary_digest,
        binary_version=good_binding.protocol_receipt.binary_version,
        stable_inventory_digest=good_binding.protocol_receipt.stable_inventory_digest,
        experimental_inventory_digest=good_binding.protocol_receipt.experimental_inventory_digest,
        supports_skill_input_path=True,
        skill_input_schema_evidence="unrelated_skill_fragment_detected",
        probe_user_agent=good_binding.protocol_receipt.probe_user_agent,
    )
    with pytest.raises(CodexAdapterError, match="schema evidence is invalid"):
        _adapter(
            replace(
                good_binding,
                protocol_receipt=arbitrary_schema_evidence_receipt,
            )
        )

    # --- CAP-S1 Sol review item 1: splice-proof, producer-bound receipt ----
    #
    # Every mutant below is refused BEFORE ``thread/start`` -- indeed before
    # any process is ever launched, since ``_adapter`` only exercises the
    # constructor-time ``_validate_skill_canary_binding`` pass.

    # A receipt whose ``binary_digest`` correctly matches THIS adapter's own
    # binary (so the pre-existing digest-vs-``self.binary_path`` check alone
    # would pass) but whose ``binary_path`` field names a completely
    # different, real, on-disk executable -- the exact "schema generated
    # from binary A can authorize adapter binary B" splice Sol's review
    # named. Every OTHER field is a fully self-consistent receipt (built via
    # the one lawful constructor), so only the new binary-path identity
    # check can catch it.
    other_real_binary = Path(shutil.which("true") or "/usr/bin/true").resolve()
    assert other_real_binary != scaffold.adapter.binary_path
    cross_binary_receipt = build_protocol_attestation_receipt(
        binary_path=str(other_real_binary),
        binary_digest=_test_binary_digest(),
        binary_version=CAP_S1_HARNESS_VERSION,
        stable_inventory_digest="c" * 64,
        experimental_inventory_digest="d" * 64,
        supports_skill_input_path=True,
        skill_input_schema_evidence=SKILL_INPUT_SCHEMA_EVIDENCE,
        probe_user_agent=CAP_S1_HARNESS_VERSION,
    )
    cross_binary_splice = replace(good_binding, protocol_receipt=cross_binary_receipt)
    with pytest.raises(CodexAdapterError, match="binary path mismatch"):
        _adapter(cross_binary_splice)

    # A receipt bound to a genuinely distinct (but same-shaped) inventory --
    # ``build_protocol_attestation_receipt`` computes a fully self-consistent
    # digest for it, so only the dedicated non-distinctness check (never the
    # digest check) can catch it.
    non_distinct_inventory_receipt = build_protocol_attestation_receipt(
        binary_path=good_binding.protocol_receipt.binary_path,
        binary_digest=good_binding.protocol_receipt.binary_digest,
        binary_version=good_binding.protocol_receipt.binary_version,
        stable_inventory_digest="e" * 64,
        experimental_inventory_digest="e" * 64,
        supports_skill_input_path=True,
        skill_input_schema_evidence=SKILL_INPUT_SCHEMA_EVIDENCE,
        probe_user_agent=good_binding.protocol_receipt.probe_user_agent,
    )
    non_distinct_inventory = replace(
        good_binding, protocol_receipt=non_distinct_inventory_receipt
    )
    with pytest.raises(CodexAdapterError, match="must be distinct"):
        _adapter(non_distinct_inventory)

    # Every remaining mutant leaves the digest stale after a bare
    # ``dataclasses.replace`` -- the producer-bound receipt-digest
    # recomputation is what catches each of these, since none of the
    # individually-named checks above inspect ``probe_user_agent`` or the
    # digest field itself.
    spliced_probe_user_agent = replace(
        good_binding,
        protocol_receipt=replace(
            good_binding.protocol_receipt, probe_user_agent="spliced/1.0"
        ),
    )
    with pytest.raises(
        CodexAdapterError,
        match="probe user agent mismatch|protocol receipt digest mismatch",
    ):
        _adapter(spliced_probe_user_agent)

    empty_probe_user_agent = replace(
        good_binding,
        protocol_receipt=replace(good_binding.protocol_receipt, probe_user_agent=""),
    )
    with pytest.raises(
        CodexAdapterError,
        match="probe user agent mismatch|protocol receipt digest mismatch",
    ):
        _adapter(empty_probe_user_agent)

    tampered_receipt_digest = replace(
        good_binding,
        protocol_receipt=replace(good_binding.protocol_receipt, receipt_digest="0" * 64),
    )
    with pytest.raises(CodexAdapterError, match="protocol receipt digest mismatch"):
        _adapter(tampered_receipt_digest)

    # A receipt hand-built without the producer (``CodexProtocolAttestation
    # Receipt`` constructed directly, never through
    # ``build_protocol_attestation_receipt``) with an arbitrary, wrong
    # digest -- refused the same way.
    hand_built_receipt = CodexProtocolAttestationReceipt(
        binary_path=good_binding.protocol_receipt.binary_path,
        binary_digest=good_binding.protocol_receipt.binary_digest,
        binary_version=good_binding.protocol_receipt.binary_version,
        stable_inventory_digest=good_binding.protocol_receipt.stable_inventory_digest,
        experimental_inventory_digest=good_binding.protocol_receipt.experimental_inventory_digest,
        supports_skill_input_path=good_binding.protocol_receipt.supports_skill_input_path,
        skill_input_schema_evidence=good_binding.protocol_receipt.skill_input_schema_evidence,
        probe_user_agent=good_binding.protocol_receipt.probe_user_agent,
        receipt_digest="9" * 64,
    )
    hand_built = replace(good_binding, protocol_receipt=hand_built_receipt)
    with pytest.raises(CodexAdapterError, match="protocol receipt digest mismatch"):
        _adapter(hand_built)

    # Sanity: the shared digest function really is what the adapter
    # recomputes -- a receipt whose digest was correctly recomputed via
    # ``dataclasses.replace`` PLUS a fresh digest call constructs cleanly.
    honestly_updated_receipt = replace(
        good_binding.protocol_receipt, probe_user_agent=CAP_S1_HARNESS_VERSION
    )
    honestly_updated_receipt = replace(
        honestly_updated_receipt,
        receipt_digest=compute_protocol_attestation_receipt_digest(
            binary_path=honestly_updated_receipt.binary_path,
            binary_digest=honestly_updated_receipt.binary_digest,
            binary_version=honestly_updated_receipt.binary_version,
            stable_inventory_digest=honestly_updated_receipt.stable_inventory_digest,
            experimental_inventory_digest=honestly_updated_receipt.experimental_inventory_digest,
            supports_skill_input_path=honestly_updated_receipt.supports_skill_input_path,
            skill_input_schema_evidence=honestly_updated_receipt.skill_input_schema_evidence,
            probe_user_agent=honestly_updated_receipt.probe_user_agent,
        ),
    )
    _adapter(replace(good_binding, protocol_receipt=honestly_updated_receipt))

    # --- B1: projection_root is the only identity re-checked here; a
    # caller-substituted ``skills_root`` is never trusted or even inspected
    # at construction time -- it is re-derived and matched inside
    # ``_run_skill_causal_sequence`` at launch time instead (see
    # ``test_skill_canary_root_substitution_refuses_before_thread_start``).

    symlinked_root = tmp_path / "symlinked-projection-root"
    symlinked_root.symlink_to(good_binding.projection.projection_root)
    via_symlink = replace(
        good_binding,
        projection=replace(good_binding.projection, projection_root=str(symlinked_root)),
    )
    with pytest.raises(CodexAdapterError, match="must be a real directory"):
        _adapter(via_symlink)

    missing_root = replace(
        good_binding,
        projection=replace(
            good_binding.projection, projection_root=str(tmp_path / "does-not-exist")
        ),
    )
    with pytest.raises(CodexAdapterError, match="not observable"):
        _adapter(missing_root)

    different_real_root = tmp_path / "different-real-projection-root"
    different_real_root.mkdir()
    retargeted_root = replace(
        good_binding,
        projection=replace(good_binding.projection, projection_root=str(different_real_root)),
    )
    with pytest.raises(CodexAdapterError, match="identity mismatch"):
        _adapter(retargeted_root)

    for state in scaffold.adapter._generations.values():
        state.client.close()


# ---------------------------------------------------------------------------
# CAP-S1: binding-gated causal launch sequence (protocol-attestation
# amendment §5-§6)
# ---------------------------------------------------------------------------


def test_skill_canary_causal_launch_happy_path_mode_a_real_server(
    tmp_path: Path,
) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="mode-a-happy")
    harness = _make_skill_harness(tmp_path, binding)

    observation, observed, launch = _start(harness)

    assert launch.decision is LaunchDecision.ALLOW
    required_names = tuple(
        sorted(grant.runtime_name for grant in binding.profile.skill_grants)
    )
    assert observed.effective_skills == required_names
    digest_by_name = {
        grant.runtime_name: grant.skill_content_digest
        for grant in binding.profile.skill_grants
    }
    skill_rows = [item for item in observed.capabilities if item.kind == "skill"]
    assert {row.name for row in skill_rows} == set(required_names)
    for row in skill_rows:
        assert row.skill_content_digest == digest_by_name[row.name]

    client = harness.adapter._state(harness.generation).client
    extra_root_calls = [
        params for method, params in client.calls if method == "skills/extraRoots/set"
    ]
    assert extra_root_calls == [
        {"extraRoots": []},
        {"extraRoots": [binding.projection.skills_root]},
    ]


def test_skill_canary_launch_refuses_config_drift_when_bundled_key_is_omitted(
    tmp_path: Path,
) -> None:
    """CAP-S1 config-digest attestation gate re-arm falsifier.

    A skill-canary harness whose scripted ``config/read`` OMITS the
    ``skills.bundled`` key (as a real App Server would if it never echoed
    the override) must REFUSE_CONFIG_DRIFT via ``compare_launch`` -- the
    profile's ``expected_config_digest`` requires ``bundled.enabled=false``
    per the protocol amendment §5, and a skill-canary's
    ``expected_config_digest`` is now always sealed onto the harness
    (never left unset the way the retired workaround left it).
    """

    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="bundled-omitted")
    harness = _make_skill_harness(tmp_path, binding, bundled_disabled=False)

    _observation, observed, launch = _start(harness)

    assert launch.decision is LaunchDecision.REFUSE_CONFIG_DRIFT
    assert "config_drift" in launch.mismatch_reasons
    assert observed.effective_config_digest != harness.requested.expected_config_digest


def test_skill_canary_causal_launch_happy_path_mode_b_pathless(
    tmp_path: Path,
) -> None:
    binding = _stage_cap_s1_binding(
        tmp_path,
        owning_process_generation="mode-b-happy",
        schema_supports_skill_input_path=True,
    )
    harness = _make_skill_harness(
        tmp_path, binding, extra_env={"OHF_FAKE_SKILLS_OMIT_PATH": "1"}
    )

    _observation, observed, launch = _start(harness)

    assert launch.decision is LaunchDecision.ALLOW
    required_names = tuple(
        sorted(grant.runtime_name for grant in binding.profile.skill_grants)
    )
    assert observed.effective_skills == required_names


def test_skill_canary_mode_b_without_schema_support_refuses(tmp_path: Path) -> None:
    binding = _stage_cap_s1_binding(
        tmp_path,
        owning_process_generation="mode-b-unsupported",
        schema_supports_skill_input_path=False,
    )
    harness = _make_skill_harness(
        tmp_path, binding, extra_env={"OHF_FAKE_SKILLS_OMIT_PATH": "1"}
    )

    with pytest.raises(CodexAdapterError, match="skill_path_attestation_unavailable"):
        _start(harness)


def test_skill_canary_ambient_row_at_baseline_refuses(tmp_path: Path) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="ambient")
    harness = _make_skill_harness(
        tmp_path, binding, extra_env={"OHF_FAKE_AMBIENT_SKILL": "rogue-skill"}
    )

    with pytest.raises(CodexAdapterError, match="ambient_skill_surface_not_empty"):
        _start(harness)


def _shape_test_harness(tmp_path: Path, binding: CodexSkillCanaryBinding, rows: list):
    """A harness whose ``skills/list`` responses are fully scripted.

    Three calls occur before ``start_session`` returns when a binding is
    present: the ordinary (lenient) attestation call, the causal baseline
    (must be empty), then the post-add causal call -- which is where ``rows``
    is substituted.
    """

    cwd = str(tmp_path / "workspace")
    script = [
        _strict_skills_list_result(cwd, []),
        _strict_skills_list_result(cwd, []),
        _strict_skills_list_result(cwd, rows),
    ]
    return _make_skill_harness(
        tmp_path, binding, client_factory=_recording_client_factory(script)
    )


def test_skill_canary_duplicate_same_name_row_refuses(tmp_path: Path) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="duplicate")
    skills_root = binding.projection.skills_root
    names = [grant.runtime_name for grant in binding.profile.skill_grants]
    rows = [_skill_row(name, path=f"{skills_root}/{name}") for name in names]
    rows.append(_skill_row(names[0], path=f"{skills_root}/{names[0]}"))
    harness = _shape_test_harness(tmp_path, binding, rows)

    with pytest.raises(CodexAdapterError, match="duplicate_skill_row"):
        _start(harness)


def test_skill_canary_missing_one_of_four_refuses(tmp_path: Path) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="missing-one")
    skills_root = binding.projection.skills_root
    names = [grant.runtime_name for grant in binding.profile.skill_grants][:-1]
    rows = [_skill_row(name, path=f"{skills_root}/{name}") for name in names]
    harness = _shape_test_harness(tmp_path, binding, rows)

    with pytest.raises(CodexAdapterError, match="skill_set_causality_failed"):
        _start(harness)


def test_skill_canary_mode_a_wrong_path_refuses(tmp_path: Path) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="wrong-path")
    skills_root = binding.projection.skills_root
    names = [grant.runtime_name for grant in binding.profile.skill_grants]
    rows = [_skill_row(name, path=f"{skills_root}/{name}") for name in names[1:]]
    rows.append(_skill_row(names[0], path="/totally/unrelated/root/" + names[0]))
    harness = _shape_test_harness(tmp_path, binding, rows)

    with pytest.raises(CodexAdapterError, match="skill_path_mismatch"):
        _start(harness)


def test_skill_canary_mixed_path_presence_refuses(tmp_path: Path) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="mixed-path")
    skills_root = binding.projection.skills_root
    names = [grant.runtime_name for grant in binding.profile.skill_grants]
    rows = [
        _skill_row(names[0], path=f"{skills_root}/{names[0]}"),
        _skill_row(names[1], path=f"{skills_root}/{names[1]}"),
        _skill_row(names[2], path=None),
        _skill_row(names[3], path=None),
    ]
    harness = _shape_test_harness(tmp_path, binding, rows)

    with pytest.raises(CodexAdapterError, match="skill_path_precision_inconsistent"):
        _start(harness)


# ---------------------------------------------------------------------------
# CAP-S1 Sol wave-3 review B1: server-derived skills root / root substitution
# ---------------------------------------------------------------------------


def test_skill_canary_root_substitution_refuses_before_thread_start(
    tmp_path: Path,
) -> None:
    """A caller-substituted ``skills_root`` pointing at a different, real,
    attacker-controlled directory tree carrying the SAME four Skill names
    must never reach ``skills/extraRoots/set`` or ``thread/start`` -- the
    adapter derives the only lawful root itself from the already-verified
    ``projection_root`` and never trusts the binding's own field as a
    destination (CAP-S1 Sol review B1)."""

    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="root-substitution")

    alternate_root = tmp_path / "alternate-real-skills-root"
    for grant in binding.profile.skill_grants:
        skill_dir = alternate_root / grant.runtime_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# forged alternate skill\n", encoding="utf-8")

    forged_binding = replace(
        binding, projection=replace(binding.projection, skills_root=str(alternate_root))
    )

    created_clients: list = []

    def factory(argv, env, cwd):
        inner = AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)
        wrapped = _RecordingSkillsClient(inner)
        created_clients.append(wrapped)
        return wrapped

    harness = _make_skill_harness(tmp_path, forged_binding, client_factory=factory)

    with pytest.raises(CodexAdapterError, match="skill_root_identity_mismatch"):
        _start(harness)

    assert len(created_clients) == 1
    calls = [method for method, _params in created_clients[0].calls]
    assert "thread/start" not in calls
    # The forged root must never even be handed to the provider.
    extra_root_calls = [
        params
        for method, params in created_clients[0].calls
        if method == "skills/extraRoots/set"
    ]
    assert all(str(alternate_root) not in params.get("extraRoots", []) for params in extra_root_calls)


# ---------------------------------------------------------------------------
# CAP-S1 Sol wave-3 review M7: skills/changed fencing at the accepted-list
# boundary
# ---------------------------------------------------------------------------


class _NotificationAfterCallClient:
    """Wraps a real ``AppServerClient``.

    Injects one synthetic notification directly into the wrapped client's
    own live ``notifications`` buffer immediately after the Nth call to a
    chosen RPC method returns -- proving a ``skills/changed`` notification
    arriving between the accepted causal-sequence ``skills/list`` and
    ``thread/start`` cannot be silently dropped (CAP-S1 Sol review M7).
    """

    def __init__(self, inner, *, after_method: str, after_call_index: int, notification: dict) -> None:
        self._inner = inner
        self._after_method = after_method
        self._after_call_index = after_call_index
        self._notification = notification
        self._count = 0
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def request(self, method, params=None, *, timeout=15.0):
        self.calls.append((method, dict(params or {})))
        result = self._inner.request(method, params, timeout=timeout)
        if method == self._after_method:
            self._count += 1
            if self._count == self._after_call_index:
                with self._inner._notification_condition:
                    self._inner.notifications.append(dict(self._notification))
                    self._inner._notification_condition.notify_all()
        return result


def test_skills_changed_between_accepted_list_and_thread_start_refuses_before_first_turn(
    tmp_path: Path,
) -> None:
    binding = _stage_cap_s1_binding(
        tmp_path, owning_process_generation="pre-thread-start-changed"
    )

    def factory(argv, env, cwd):
        inner = AppServerClient(argv, env=env, cwd=cwd, start_new_session=True)
        # The three real ``skills/list`` calls before ``thread/start`` are:
        # (1) the ordinary lenient attestation probe, (2) the causal
        # baseline (must be empty), (3) the causal accepted list (the four
        # required Skills) -- inject right after call #3 returns.
        return _NotificationAfterCallClient(
            inner,
            after_method="skills/list",
            after_call_index=3,
            notification={"method": "skills/changed", "params": {}},
        )

    harness = _make_skill_harness(tmp_path, binding, client_factory=factory)

    _observation, _observed, launch = _start(harness)

    state = harness.adapter._state(harness.generation)
    assert state.skills_changed is True

    client = state.client
    assert "turn/start" not in [method for method, _params in client.calls]

    envelope, _final_path = _cap_s1_envelope(binding)
    harness.adapter.turn_input_loader = lambda turn: envelope
    turn = TurnRef(
        "turn-pre-thread-start-changed",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )

    with pytest.raises(CodexAdapterError, match="skills_changed_during_canary"):
        harness.adapter.begin_turn(
            operation_id=_op("pre-thread-start-changed-turn"),
            turn=turn,
            generation=harness.generation,
            launch=launch,
        )

    assert "turn/start" not in [method for method, _params in client.calls]


# ---------------------------------------------------------------------------
# CAP-S1: closed structured Skill turn-input seam (protocol-attestation
# amendment §7)
# ---------------------------------------------------------------------------


def test_skill_envelope_happy_path_produces_the_exact_two_item_wire(
    tmp_path: Path,
) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="envelope-ok")
    harness = _make_skill_harness(tmp_path, binding)
    _observation, _observed, launch = _start(harness)

    envelope, final_path = _cap_s1_envelope(binding)
    harness.adapter.turn_input_loader = lambda turn: envelope
    turn = TurnRef(
        "turn-skill-envelope",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )

    started = harness.adapter.begin_turn(
        operation_id=_op("skill-envelope"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )

    assert started.acknowledged
    client = harness.adapter._state(harness.generation).client
    turn_start_calls = [
        params for method, params in client.calls if method == "turn/start"
    ]
    grant = binding.profile.skill_grants[0]
    assert turn_start_calls[-1]["input"] == [
        {"type": "text", "text": envelope.text},
        {"type": "skill", "name": grant.runtime_name, "path": final_path},
    ]


def test_skill_envelope_without_binding_refuses(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    _observation, _observed, launch = _start(harness)
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="no-binding")
    envelope, _final_path = _cap_s1_envelope(binding)
    harness.adapter.turn_input_loader = lambda turn: envelope
    turn = TurnRef("turn-no-binding", "epoch-1", "gen-1", "attempt-1")

    with pytest.raises(CodexAdapterError, match="skill_envelope_without_binding"):
        harness.adapter.begin_turn(
            operation_id=_op("no-binding-turn"),
            turn=turn,
            generation=harness.generation,
            launch=launch,
        )


@pytest.mark.parametrize("skill_count", [0, 2])
def test_skill_envelope_cardinality_refuses(tmp_path: Path, skill_count: int) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="cardinality")
    harness = _make_skill_harness(tmp_path, binding)
    _observation, _observed, launch = _start(harness)

    envelope, _final_path = _cap_s1_envelope(binding)
    bad_envelope = replace(envelope, skills=envelope.skills * skill_count)
    harness.adapter.turn_input_loader = lambda turn: bad_envelope
    turn = TurnRef(
        "turn-cardinality",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )

    with pytest.raises(CodexAdapterError, match="skill_envelope_cardinality"):
        harness.adapter.begin_turn(
            operation_id=_op("cardinality-turn"),
            turn=turn,
            generation=harness.generation,
            launch=launch,
        )


def test_skill_envelope_identity_mismatch_refuses(tmp_path: Path) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="identity")
    harness = _make_skill_harness(tmp_path, binding)
    _observation, _observed, launch = _start(harness)

    envelope, _final_path = _cap_s1_envelope(binding)
    bad_item = replace(envelope.skills[0], skill_content_digest="0" * 64)
    bad_envelope = replace(envelope, skills=(bad_item,))
    harness.adapter.turn_input_loader = lambda turn: bad_envelope
    turn = TurnRef(
        "turn-identity",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )

    with pytest.raises(CodexAdapterError, match="skill_envelope_identity_mismatch"):
        harness.adapter.begin_turn(
            operation_id=_op("identity-turn"),
            turn=turn,
            generation=harness.generation,
            launch=launch,
        )


def test_skill_envelope_path_mismatch_refuses(tmp_path: Path) -> None:
    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="path-mismatch")
    harness = _make_skill_harness(tmp_path, binding)
    _observation, _observed, launch = _start(harness)

    envelope, _final_path = _cap_s1_envelope(binding)
    bad_item = replace(envelope.skills[0], skill_md_path="/not/the/right/path/SKILL.md")
    bad_envelope = replace(envelope, skills=(bad_item,))
    harness.adapter.turn_input_loader = lambda turn: bad_envelope
    turn = TurnRef(
        "turn-path-mismatch",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )

    with pytest.raises(CodexAdapterError, match="skill_input_path_mismatch"):
        harness.adapter.begin_turn(
            operation_id=_op("path-mismatch-turn"),
            turn=turn,
            generation=harness.generation,
            launch=launch,
        )


def test_skill_envelope_refuses_alongside_a_bound_attempt_resource(
    tmp_path: Path,
) -> None:
    binding = _stage_cap_s1_binding(
        tmp_path, owning_process_generation="resource-conflict"
    )
    harness = _make_skill_harness(tmp_path, binding)
    manifest = binding.profile.capability_manifest(
        harness_binary_digest=harness.adapter.binary_digest
    )
    resource_digest = "f" * 64
    requested_resource = CapabilityIdentity(
        kind="resource",
        name="worker-browser-b1-local",
        harness_binary_digest=harness.adapter.binary_digest,
        resource_contract_digest=resource_digest,
    )
    harness.requested = replace(
        harness.requested,
        capabilities=CapabilityManifest(
            required=(*manifest.required, requested_resource),
            unclassified_policy="lab_allow_unclassified_readonly",
        ),
    )
    resource_environment = {
        "MASTERMIND_BROWSER_ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "MASTERMIND_BROWSER_FIXTURE_A_URL": (
            "http://127.0.0.1:43123/__mastermind_browser_visual_fixture__/" + "a" * 32
        ),
        "MASTERMIND_BROWSER_FIXTURE_B_URL": (
            "http://127.0.0.1:43123/__mastermind_browser_visual_fixture__/" + "b" * 32
        ),
        "MASTERMIND_BROWSER_FIXTURE_NONCE": "c" * 32,
        "MASTERMIND_BROWSER_ORIGIN": "http://127.0.0.1:43123",
        "MASTERMIND_BROWSER_PROXY_URL": "http://127.0.0.1:43124",
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_PATH": str(
            tmp_path / "runtime" / "worker-browser-b1-install-manifest.json"
        ),
        "MASTERMIND_BROWSER_RUNTIME_MANIFEST_SHA256": "d" * 64,
        "MASTERMIND_BROWSER_RUNTIME_ROOT": str(tmp_path / "runtime"),
        "MASTERMIND_BROWSER_WORKSPACE_PATH": str(tmp_path),
        "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "runtime" / "browsers"),
    }

    class Resource:
        attempt_id = harness.epoch.attempt_id
        session_epoch_id = harness.epoch.session_epoch_id
        process_generation_id = harness.generation.process_generation_id
        network_state = "disabled"
        environment = resource_environment
        observed_capability = ObservedCapabilityIdentity(
            kind="resource",
            name="worker-browser-b1-local",
            resource_contract_digest=resource_digest,
        )

    harness.adapter.bind_attempt_resource(
        Resource(),
        requested=harness.requested,
        epoch=harness.epoch,
        generation=harness.generation,
    )
    _observation, _observed, launch = _start(harness)

    envelope, _final_path = _cap_s1_envelope(binding)
    harness.adapter.turn_input_loader = lambda turn: envelope
    turn = TurnRef(
        "turn-resource-conflict",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )

    with pytest.raises(CodexAdapterError, match="skill_envelope_resource_conflict"):
        harness.adapter.begin_turn(
            operation_id=_op("resource-conflict-turn"),
            turn=turn,
            generation=harness.generation,
            launch=launch,
        )


# ---------------------------------------------------------------------------
# CAP-S1: skills/changed invalidation and post-turn drift (protocol-
# attestation amendment §8)
# ---------------------------------------------------------------------------


def test_skills_changed_notification_invalidates_the_launch_attestation(
    tmp_path: Path,
) -> None:
    binding = _stage_cap_s1_binding(
        tmp_path, owning_process_generation="skills-changed"
    )
    harness = _make_skill_harness(tmp_path, binding)
    _observation, _observed, launch = _start(harness)

    state = harness.adapter._state(harness.generation)
    turn = TurnRef(
        "turn-skills-changed",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )
    harness.adapter._ingest_turn_notifications(
        state, turn, [{"method": "skills/changed", "params": {}}]
    )
    assert state.skills_changed is True

    envelope, _final_path = _cap_s1_envelope(binding)
    harness.adapter.turn_input_loader = lambda turn: envelope

    with pytest.raises(CodexAdapterError, match="skills_changed_during_canary"):
        harness.adapter.begin_turn(
            operation_id=_op("skills-changed-turn"),
            turn=turn,
            generation=harness.generation,
            launch=launch,
        )


def test_collect_candidate_result_refuses_on_post_turn_skill_drift(
    tmp_path: Path,
) -> None:
    binding = _stage_cap_s1_binding(
        tmp_path, owning_process_generation="post-turn-drift"
    )
    harness = _make_skill_harness(tmp_path, binding)
    _observation, _observed, launch = _start(harness)
    turn = TurnRef(
        "turn-post-drift",
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )
    harness.adapter.begin_turn(
        operation_id=_op("post-drift-turn"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )
    harness.adapter.read_events(
        EventCursor(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            turn_id=turn.turn_id,
        )
    )

    state = harness.adapter._state(harness.generation)
    # Simulate an out-of-band root clear between the turn and candidate
    # collection: the server-side skill surface no longer matches the four
    # required Skills.
    state.client.request("skills/extraRoots/set", {"extraRoots": []})

    with pytest.raises(CodexAdapterError, match="post_turn_skill_state_mismatch"):
        harness.adapter.collect_candidate_result(turn)


# ---------------------------------------------------------------------------
# CAP-S1 Sol wave-3 review B2: exact accepted-observation reducer (pre/post
# drift the old names/cardinality-only reconfirm could not see)
# ---------------------------------------------------------------------------


def _reducer_drift_harness(tmp_path: Path, binding: CodexSkillCanaryBinding, extra_rows: list):
    """A skill-canary harness whose ``skills/list`` calls after the launch
    causal sequence are fully scripted, one entry per subsequent call."""

    cwd = str(tmp_path / "workspace")
    names = [grant.runtime_name for grant in binding.profile.skill_grants]
    skills_root = binding.projection.skills_root
    good_rows = [_skill_row(name, path=f"{skills_root}/{name}") for name in names]
    script = [
        _strict_skills_list_result(cwd, []),
        _strict_skills_list_result(cwd, []),
        _strict_skills_list_result(cwd, good_rows),
        *[_strict_skills_list_result(cwd, rows) for rows in extra_rows],
    ]
    return _make_skill_harness(
        tmp_path, binding, client_factory=_recording_client_factory(script)
    )


def _begin_envelope_turn(harness: "Harness", binding: CodexSkillCanaryBinding, launch, turn_id: str):
    envelope, _final_path = _cap_s1_envelope(binding)
    harness.adapter.turn_input_loader = lambda turn: envelope
    turn = TurnRef(
        turn_id,
        harness.epoch.session_epoch_id,
        harness.generation.process_generation_id,
        harness.epoch.attempt_id,
    )
    return turn, lambda: harness.adapter.begin_turn(
        operation_id=_op(f"{turn_id}-op"),
        turn=turn,
        generation=harness.generation,
        launch=launch,
    )


def test_pre_turn_skill_observation_wrong_root_refuses(tmp_path: Path) -> None:
    """A fake server that pathes rows under a DIFFERENT root pre-turn (same
    four names) must refuse -- the old names/cardinality-only reconfirm
    could not see this at all (CAP-S1 Sol review B2)."""

    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="pre-turn-wrong-root")
    names = [grant.runtime_name for grant in binding.profile.skill_grants]
    wrong_root = str(tmp_path / "attacker-root")
    wrong_rows = [_skill_row(name, path=f"{wrong_root}/{name}") for name in names]
    harness = _reducer_drift_harness(tmp_path, binding, [wrong_rows])
    _observation, _observed, launch = _start(harness)
    client = harness.adapter._state(harness.generation).client

    turn, do_begin = _begin_envelope_turn(harness, binding, launch, "turn-pre-turn-wrong-root")
    with pytest.raises(CodexAdapterError, match="skill_set_causality_failed"):
        do_begin()
    assert "turn/start" not in [method for method, _params in client.calls]


def test_pre_turn_mixed_path_presence_refuses(tmp_path: Path) -> None:
    """Mixed path/pathless rows pre-turn must refuse via the same reducer
    logic used at launch, never a diverging pre-turn implementation (CAP-S1
    Sol review B2)."""

    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="pre-turn-mixed")
    names = [grant.runtime_name for grant in binding.profile.skill_grants]
    skills_root = binding.projection.skills_root
    mixed_rows = [
        _skill_row(names[0], path=f"{skills_root}/{names[0]}"),
        _skill_row(names[1], path=f"{skills_root}/{names[1]}"),
        _skill_row(names[2], path=None),
        _skill_row(names[3], path=None),
    ]
    harness = _reducer_drift_harness(tmp_path, binding, [mixed_rows])
    _observation, _observed, launch = _start(harness)

    turn, do_begin = _begin_envelope_turn(harness, binding, launch, "turn-pre-turn-mixed")
    with pytest.raises(CodexAdapterError, match="skill_set_causality_failed"):
        do_begin()


def test_pre_turn_pathless_flip_refuses(tmp_path: Path) -> None:
    """Mode A (paths) at launch, pathless pre-turn with the SAME four names
    must refuse -- the schema-support mode is part of the exact accepted
    reduction, so a silent mode flip can never pass as "close enough" (CAP-S1
    Sol review B2)."""

    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="pre-turn-pathless-flip")
    names = [grant.runtime_name for grant in binding.profile.skill_grants]
    pathless_rows = [_skill_row(name, path=None) for name in names]
    harness = _reducer_drift_harness(tmp_path, binding, [pathless_rows])
    _observation, _observed, launch = _start(harness)

    turn, do_begin = _begin_envelope_turn(harness, binding, launch, "turn-pre-turn-pathless-flip")
    with pytest.raises(CodexAdapterError, match="skill_set_causality_failed"):
        do_begin()


def test_post_turn_duplicate_row_refuses(tmp_path: Path) -> None:
    """A duplicate enabled row post-turn (one of the four names appearing
    twice) must refuse via the reducer with no second attempt (CAP-S1 Sol
    review B2)."""

    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="post-turn-duplicate")
    names = [grant.runtime_name for grant in binding.profile.skill_grants]
    skills_root = binding.projection.skills_root
    good_rows = [_skill_row(name, path=f"{skills_root}/{name}") for name in names]
    duplicate_rows = good_rows + [_skill_row(names[0], path=f"{skills_root}/{names[0]}")]
    harness = _reducer_drift_harness(tmp_path, binding, [good_rows, duplicate_rows])
    _observation, _observed, launch = _start(harness)

    turn, do_begin = _begin_envelope_turn(harness, binding, launch, "turn-post-turn-duplicate")
    do_begin()
    harness.adapter.read_events(
        EventCursor(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            turn_id=turn.turn_id,
        )
    )

    with pytest.raises(CodexAdapterError, match="post_turn_skill_state_mismatch"):
        harness.adapter.collect_candidate_result(turn)


def test_str_loader_wire_is_byte_identical_with_and_without_binding(
    tmp_path: Path,
) -> None:
    plain_harness = _make_harness(
        tmp_path / "plain", client_factory=_recording_client_factory()
    )
    _observation, _observed, plain_launch = _start(plain_harness)
    plain_turn = TurnRef("turn-plain", "epoch-1", "gen-1", "attempt-1")
    plain_harness.adapter.begin_turn(
        operation_id=_op("plain-wire"),
        turn=plain_turn,
        generation=plain_harness.generation,
        launch=plain_launch,
    )
    plain_client = plain_harness.adapter._state(plain_harness.generation).client
    plain_wire = next(
        params["input"] for method, params in plain_client.calls if method == "turn/start"
    )

    binding = _stage_cap_s1_binding(tmp_path, owning_process_generation="wire-parity")
    bound_harness = _make_skill_harness(tmp_path, binding)
    _observation, _observed, bound_launch = _start(bound_harness)
    bound_turn = TurnRef(
        "turn-bound",
        bound_harness.epoch.session_epoch_id,
        bound_harness.generation.process_generation_id,
        bound_harness.epoch.attempt_id,
    )
    bound_harness.adapter.begin_turn(
        operation_id=_op("bound-wire"),
        turn=bound_turn,
        generation=bound_harness.generation,
        launch=bound_launch,
    )
    bound_client = bound_harness.adapter._state(bound_harness.generation).client
    bound_wire = next(
        params["input"] for method, params in bound_client.calls if method == "turn/start"
    )

    assert (
        plain_wire
        == bound_wire
        == [{"type": "text", "text": "Reply with the probe acknowledgement."}]
    )
