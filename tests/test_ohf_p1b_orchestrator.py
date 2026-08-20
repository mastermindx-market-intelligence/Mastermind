from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from control_plane.operator_harness_contract import (
    ACCOUNT_REALM_STATUS,
    AuthRealmFact,
    CandidateResult,
    CapabilityManifest,
    EventCursor,
    LaunchDecision,
    NativeHelperPolicy,
    NormalizedEvent,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProfileValidation,
    ProviderSessionHandoff,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    SessionStartObservation,
    TurnRef,
    TurnStartObservation,
    WorkspaceIdentity,
)
from control_plane.operator_harness_orchestrator import (
    OperatorEffectUnknown,
    OperatorHarnessOrchestrationError,
    OperatorHarnessOrchestrator,
    OperatorStartRefused,
)


def _op(suffix: str) -> OperationId:
    return OperationId(f"ohf-op:{suffix}")


def _requested() -> RequestedExecutionProfile:
    return RequestedExecutionProfile(
        worker_id="slot-a",
        provider="openai-codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest="a" * 64,
        harness_version="codex/1",
        workspace=WorkspaceIdentity("/work", "b" * 40, 1, 2, 3, 4),
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="restricted",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash="c" * 64,
    )


def _observed(requested: RequestedExecutionProfile) -> ObservedHarnessAttestation:
    return ObservedHarnessAttestation(
        served_model=requested.requested_model,
        harness_version=requested.harness_version,
        harness_binary_digest=requested.harness_binary_digest,
        capabilities=(),
        effective_skills=(),
        effective_mcp=(),
        effective_plugins_or_apps=(),
        sandbox_state=requested.sandbox_policy,
        approval_state=requested.approval_policy,
        network_state=requested.network_policy,
        effective_config_digest=None,
        auth=AuthRealmFact(
            worker_id=requested.worker_id,
            provider=requested.provider,
            attestation_status=ACCOUNT_REALM_STATUS,
        ),
        workspace=requested.workspace,
        supports_subagent_capability_ceiling=ObservedTriState.FALSE,
    )


class FakeRuntime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.fail: set[str] = set()
        self.epoch = SessionEpochRef("epoch-1", "attempt-1", "slot-a", 1)
        self.generation = ProcessGenerationRef("gen-1", "epoch-1", 1, "slot-a")
        self.candidates: list[CandidateResult] = []

    def _call(self, name: str, value: object = None) -> None:
        self.calls.append((name, value))
        if name in self.fail:
            raise RuntimeError(f"injected runtime crash at {name}")

    def seal_operator_attempt(self, attempt_id, requested):
        self._call("seal")

    def extend_operator_lease(self, attempt_id, minimum_seconds):
        self.calls.append(("lease", minimum_seconds))

    def commit_operator_provider_dispatch(
        self, attempt_id, operation_id, operation_kind
    ):
        self.calls.append(("dispatch", operation_kind))
        return True

    def commit_operator_resume_dispatch(self, attempt_id, operation_id):
        return True

    def begin_operator_turn_operation(
        self, attempt_id, turn, operation_id, operation_kind
    ):
        self._call("interrupt_intent", turn.turn_id)

    def apply_operator_turn_operation(
        self, attempt_id, turn, operation_id, operation_kind
    ):
        self._call("interrupt_applied", turn.turn_id)

    def begin_operator_session(self, attempt_id, operation_id):
        self._call("start_intent", operation_id.command_id)
        return self.epoch, self.generation

    def bind_operator_session(self, attempt_id, operation_id, observation):
        self._call("start_bind", observation.provider_session_id)

    def seal_operator_attestation(self, attempt_id, generation, observed, launch):
        self._call("attest", launch.decision)

    def begin_operator_turn(self, attempt_id, generation, operation_id):
        self._call("turn_intent", operation_id.command_id)
        return TurnRef(
            "turn-1", "epoch-1", generation.process_generation_id, attempt_id
        )

    def apply_operator_turn(self, attempt_id, operation_id, observation):
        self._call("turn_bind", observation.provider_native_turn_id)

    def record_operator_effect_unknown(self, attempt_id, operation_id, phase, detail):
        self.calls.append(("effect_unknown", (operation_id.command_id, phase, detail)))
        return True

    def finish_operator_candidate(self, attempt_id, turn, candidate, events, cursor):
        self._call("candidate", candidate.complete_job_permitted)
        self.candidates.append(candidate)

    def begin_operator_generation_operation(
        self, attempt_id, generation, operation_id, operation_kind
    ):
        self._call(f"{operation_kind}_intent", operation_id.command_id)

    def graceful_stop_operator_generation(
        self, attempt_id, generation, operation_id, observation
    ):
        self._call("stop_bind", observation.provider_writer_state)

    def cancel_operator_generation(
        self, attempt_id, generation, operation_id, observation
    ):
        self._call("cancel_bind", observation.provider_writer_state)

    def observe_operator_reconcile(self, attempt_id, generation, observation):
        self._call("reconcile", observation.process_liveness)

    def begin_operator_resume(self, attempt_id, epoch, operation_id):
        self._call("resume_intent", operation_id.command_id)
        return replace(
            self.generation, process_generation_id="gen-2", generation_number=2
        )

    def bind_operator_resume(self, attempt_id, operation_id, handoff, observation):
        self._call("resume_bind", observation.provider_session_id)


class FakeAdapter:
    interface_version = "mastermind.operator_harness/v1"

    def __init__(self, requested: RequestedExecutionProfile) -> None:
        self.requested = requested
        self.calls: list[str] = []
        self.fail: set[str] = set()
        self.session_id = "session-1"
        self.attestation = _observed(requested)

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError(f"injected adapter crash at {name}")

    def validate_requested_profile(self, requested):
        self._call("validate")
        return ProfileValidation(requested, True)

    def start_session(self, **kwargs):
        self._call("start_session")
        return SessionStartObservation(
            self.session_id,
            ProcessIdentityObservation(10, 10, "start", "boot"),
        )

    def begin_turn(self, **kwargs):
        self._call("begin_turn")
        return TurnStartObservation("native-turn", True)

    def read_events(self, cursor, *, timeout_seconds=30.0):
        self._call("read_events")
        event = NormalizedEvent(
            cursor.attempt_id,
            cursor.session_epoch_id,
            cursor.process_generation_id,
            cursor.turn_id,
            "turn/completed",
        )
        return (event,), replace(cursor, local_sequence=cursor.local_sequence + 1)

    def collect_candidate_result(self, turn):
        self._call("collect_candidate_result")
        return CandidateResult(
            turn.attempt_id,
            turn.session_epoch_id,
            turn.process_generation_id,
            "d" * 64,
            "candidate only",
        )

    def graceful_stop(self, generation, *, operation_id):
        self._call("graceful_stop")
        return _reconcile(ProviderWriterState.RELEASED)

    def cancel(self, generation, *, reason, operation_id):
        self._call("cancel")
        return _reconcile(ProviderWriterState.UNKNOWN)

    def reconcile(self, generation):
        self._call("reconcile")
        return _reconcile(ProviderWriterState.HELD, alive=True)

    def resume_session(self, **kwargs):
        self._call("resume_session")
        return SessionStartObservation(
            self.session_id,
            ProcessIdentityObservation(11, 11, "start-2", "boot"),
        )

    def interrupt_turn(self, turn, *, operation_id):
        self._call("interrupt_turn")

    def describe_capabilities(self):  # pragma: no cover - protocol completeness
        raise NotImplementedError


def _reconcile(writer: ProviderWriterState, *, alive: bool = False):
    return ReconcileObservation(
        ProcessLiveness.ALIVE if alive else ProcessLiveness.PROVEN_DEAD,
        ProcessIdentityObservation(10, 10, "start", "boot"),
        True if alive else None,
        writer,
        "session-1",
    )


def _orchestrator():
    requested = _requested()
    runtime = FakeRuntime()
    adapter = FakeAdapter(requested)
    orchestrator = OperatorHarnessOrchestrator(
        runtime,
        adapter,
        attestation_reader=lambda item, generation: item.attestation,
    )
    return requested, runtime, adapter, orchestrator


def test_no_adapter_call_before_committed_start_intent() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    runtime.fail.add("start_intent")

    with pytest.raises(RuntimeError, match="start_intent"):
        orchestrator.start_attempt(
            attempt_id="attempt-1", requested=requested, operation_id=_op("start")
        )

    assert adapter.calls == ["validate"]
    assert [name for name, _ in runtime.calls if name not in {"lease", "dispatch"}] == [
        "seal",
        "start_intent",
    ]


def test_start_orders_intent_before_adapter_and_seals_allow_attestation() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    receipt = orchestrator.start_attempt(
        attempt_id="attempt-1", requested=requested, operation_id=_op("start")
    )

    assert receipt.launch.decision is LaunchDecision.ALLOW
    assert adapter.calls == ["validate", "start_session"]
    assert [name for name, _ in runtime.calls if name not in {"lease", "dispatch"}] == [
        "seal",
        "start_intent",
        "start_bind",
        "attest",
    ]


def test_post_call_crash_is_effect_unknown_and_same_operation_is_not_replayed() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    adapter.fail.add("start_session")
    operation = _op("crash")

    with pytest.raises(OperatorEffectUnknown):
        orchestrator.start_attempt(
            attempt_id="attempt-1", requested=requested, operation_id=operation
        )
    first_calls = list(adapter.calls)
    with pytest.raises(OperatorEffectUnknown, match="unknown external effect"):
        orchestrator.start_attempt(
            attempt_id="attempt-1", requested=requested, operation_id=operation
        )

    assert adapter.calls == first_calls
    assert any(name == "effect_unknown" for name, _ in runtime.calls)


@pytest.mark.parametrize("boundary", ["start_bind", "attest"])
def test_post_call_runtime_crash_is_effect_unknown(boundary: str) -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    runtime.fail.add(boundary)

    expected = (
        OperatorEffectUnknown if boundary == "start_bind" else OperatorStartRefused
    )
    with pytest.raises(expected):
        orchestrator.start_attempt(
            attempt_id="attempt-1",
            requested=requested,
            operation_id=_op(boundary),
        )

    assert adapter.calls.count("start_session") == 1
    if boundary == "start_bind":
        assert any(name == "effect_unknown" for name, _ in runtime.calls)
    else:
        assert not any(name == "effect_unknown" for name, _ in runtime.calls)


def test_observed_mismatch_after_start_returns_cleanup_handle() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    adapter.attestation = replace(adapter.attestation, served_model="wrong-model")

    with pytest.raises(
        OperatorStartRefused, match="failed observed attestation"
    ) as caught:
        orchestrator.start_attempt(
            attempt_id="attempt-1",
            requested=requested,
            operation_id=_op("drift"),
        )

    assert ("attest", LaunchDecision.REFUSE_SERVED_MODEL_MISMATCH) in runtime.calls
    assert caught.value.handle.generation == runtime.generation
    assert not any(name == "effect_unknown" for name, _ in runtime.calls)


def test_turn_persists_candidate_only_after_intent_and_bind() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    session = orchestrator.start_attempt(
        attempt_id="attempt-1", requested=requested, operation_id=_op("start")
    )
    receipt = orchestrator.run_turn(session, operation_id=_op("turn"))

    runtime_names = [
        name for name, _ in runtime.calls if name not in {"lease", "dispatch"}
    ]
    assert runtime_names[-3:] == ["turn_intent", "turn_bind", "candidate"]
    assert adapter.calls[-3:] == [
        "begin_turn",
        "read_events",
        "collect_candidate_result",
    ]
    assert receipt.candidate.complete_job_permitted is False
    assert runtime.candidates == [receipt.candidate]
    assert not hasattr(runtime, "complete_job")


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), 301])
def test_turn_timeout_is_finite_positive_and_bounded_before_tx5(timeout) -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    session = orchestrator.start_attempt(
        attempt_id="attempt-1", requested=requested, operation_id=_op("timeout-start")
    )
    before = len(runtime.calls)
    with pytest.raises(OperatorHarnessOrchestrationError, match="timeout"):
        orchestrator.run_turn(
            session, operation_id=_op("timeout-turn"), timeout_seconds=timeout
        )
    assert len(runtime.calls) == before


def test_interrupt_turn_is_durably_intended_and_applied_around_adapter_call() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    session = orchestrator.start_attempt(
        attempt_id="attempt-1", requested=requested, operation_id=_op("interrupt-start")
    )
    turn = TurnRef(
        "turn-interrupt",
        session.epoch.session_epoch_id,
        session.generation.process_generation_id,
        session.attempt_id,
    )
    orchestrator.interrupt_turn(session, turn, operation_id=_op("interrupt"))
    runtime_names = [name for name, _ in runtime.calls]
    intent_index = runtime_names.index("interrupt_intent")
    assert runtime_names[intent_index:] == [
        "interrupt_intent",
        "lease",
        "dispatch",
        "interrupt_applied",
    ]
    assert "interrupt_turn" in adapter.calls


def test_no_begin_turn_call_before_committed_turn_intent() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    session = orchestrator.start_attempt(
        attempt_id="attempt-1", requested=requested, operation_id=_op("start")
    )
    runtime.fail.add("turn_intent")
    begin_count = adapter.calls.count("begin_turn")

    with pytest.raises(RuntimeError, match="turn_intent"):
        orchestrator.run_turn(session, operation_id=_op("turn-intent-crash"))

    assert adapter.calls.count("begin_turn") == begin_count


def test_turn_bind_crash_is_nonreplayable_effect_unknown() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    session = orchestrator.start_attempt(
        attempt_id="attempt-1", requested=requested, operation_id=_op("start")
    )
    runtime.fail.add("turn_bind")
    operation = _op("turn-crash")

    with pytest.raises(OperatorEffectUnknown):
        orchestrator.run_turn(session, operation_id=operation)
    begin_count = adapter.calls.count("begin_turn")
    with pytest.raises(OperatorEffectUnknown):
        orchestrator.run_turn(session, operation_id=operation)

    assert adapter.calls.count("begin_turn") == begin_count


def test_stop_and_cancel_commit_intent_before_adapter_call() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    session = orchestrator.start_attempt(
        attempt_id="attempt-1", requested=requested, operation_id=_op("start")
    )
    orchestrator.graceful_stop(session, operation_id=_op("stop"))
    orchestrator.cancel(session, operation_id=_op("cancel"), reason="test")

    names = [name for name, _ in runtime.calls]
    assert names.index("graceful_stop_intent") < names.index("stop_bind")
    assert names.index("cancel_intent") < names.index("cancel_bind")
    assert adapter.calls[-2:] == ["graceful_stop", "cancel"]


def test_resume_is_bound_to_handoff_s1_and_mismatch_is_effect_unknown() -> None:
    requested, runtime, adapter, orchestrator = _orchestrator()
    session = orchestrator.start_attempt(
        attempt_id="attempt-1", requested=requested, operation_id=_op("start")
    )
    adapter.session_id = "different-session"

    with pytest.raises(OperatorEffectUnknown, match="preserve bound S1"):
        orchestrator.resume(
            session,
            operation_id=_op("resume"),
            handoff=ProviderSessionHandoff("session-1", "slot-a"),
        )

    assert any(name == "resume_intent" for name, _ in runtime.calls)
    assert not any(name == "resume_bind" for name, _ in runtime.calls)


def test_modules_are_unregistered_default_off_and_import_no_lifecycle_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    modules = (
        root / "control_plane/operator_harness_orchestrator.py",
        root / "control_plane/codex_operator_adapter.py",
    )
    forbidden_imports = {
        "control_plane.executive_runtime",
        "control_plane.executive_supervisor",
        "control_plane.executive_service",
        "control_plane.worker_runtime",
        "control_plane.worker_adapter",
    }
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        imported.update(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not imported.intersection(forbidden_imports)
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr
            in {"complete_job", "transition_attempt", "transition_job"}
            for node in ast.walk(tree)
        )

    for production_file in (
        root / "config/executive_worker_routes.json",
        root / "control_plane/executive_service.py",
        root / "control_plane/executive_supervisor.py",
        root / "control_plane/executive_worker_broker.py",
        root / "control_plane/flags.py",
    ):
        text = production_file.read_text(encoding="utf-8")
        assert "CodexOperatorAdapter" not in text
        assert "codex_operator_adapter" not in text
        assert "operator_harness_orchestrator" not in text
