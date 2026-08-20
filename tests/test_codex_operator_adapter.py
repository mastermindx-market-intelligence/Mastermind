from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from control_plane.codex_operator_adapter import (
    CodexAdapterError,
    CodexOperatorAdapter,
)
from control_plane.operator_harness_contract import (
    AdapterFailureClass,
    CapabilityManifest,
    EventCursor,
    LaunchDecision,
    NativeHelperPolicy,
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
from scripts.ohf.laboratory import AppServerClient
from scripts.ohf.redaction import REDACTED

REPO_ROOT = Path(__file__).resolve().parents[1]
_CREATED_ADAPTERS: list[CodexOperatorAdapter] = []


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
        **(extra_env or {}),
    }
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
        network_policy=network_policy,
        turn_input_loader=lambda turn: turn_input,
        base_sha_resolver=lambda path: "b" * 40,
        process_identity_observer=_process,
        extra_env=env,
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
        native_helper_policy=NativeHelperPolicy.DISABLED,
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
