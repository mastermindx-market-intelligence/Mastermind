"""Adversarial contract tests for the generation-bound ChatGPT GUI resource."""
from dataclasses import dataclass, field, replace

import pytest

from control_plane.executive_worker_broker import (
    UID_SWEEP_SCHEMA_VERSION,
    UIDSweepReceipt,
)
from control_plane.operator_harness_contract import (
    OperationId,
    OperationIntentReceipt,
    OperationIntentTarget,
    OperationKind,
    OperationResolution,
    ProcessGenerationRef,
    SessionEpochRef,
)
from integrations.chatgpt_desktop.provider_identity import (
    NativeThreadIdentity,
    ProviderLogBinding,
)
from integrations.chatgpt_desktop.resource import (
    CHATGPT_APP_BUNDLE_ID,
    CHATGPT_GUI_OPERATIONS,
    ChatGPTGuiAttemptResource,
    ChatGPTGuiCloseReceipt,
    ChatGPTGuiGenerationBinding,
    ChatGPTGuiMutationReceipt,
    ChatGPTGuiObservation,
    ChatGPTGuiOpenReceipt,
    ChatGPTGuiSeatClient,
)
from integrations.chatgpt_desktop.turn import (
    DesktopSnapshot,
    DesktopTarget,
    EvidenceError,
    MessageEvidence,
    ModeSelection,
    prepare_turn,
)

APP_SESSION = "0e5071d2-6744-4025-be75-74a52d629fcd"
CONVERSATION = "01a0f046-2c55-74e3-a9da-5beb58a140f7"
TURN = "01a0fac5-caaf-7613-a997-739a1fa4a049"
PID = 10061
HELPER_DIGEST = "a" * 64
RESOURCE_DIGEST = "b" * 64
NOW = 1790913801.524


def _epoch_generation():
    epoch = SessionEpochRef("epoch-gui", "ATT-GUI", "worker-gui", 1)
    generation = ProcessGenerationRef(
        "generation-gui", "epoch-gui", 1, "worker-gui"
    )
    return epoch, generation


def _binding():
    epoch, generation = _epoch_generation()
    return ChatGPTGuiGenerationBinding(
        attempt_id=epoch.attempt_id,
        session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id,
        worker_id=generation.worker_id,
        host_ref="mini3",
        seat_ref="coo",
        project_ref="MastermindX",
        resource_contract_digest=RESOURCE_DIGEST,
        helper_binary_digest=HELPER_DIGEST,
        helper_version="1.0.0",
    )


def _identity(pid=PID):
    log = ProviderLogBinding(
        f"codex-desktop-{APP_SESSION}-{pid}-t0-i1-000006-0.log",
        pid,
        APP_SESSION,
    )
    return NativeThreadIdentity(
        binding=log,
        observed_at=NOW,
        conversation_id=CONVERSATION,
        thread_id=CONVERSATION,
        latest_turn_id=TURN,
        document_visibility="visible",
        assigned_stream_role="owner",
        has_latest_thread_settings=True,
    )


def _target():
    binding = _binding()
    return DesktopTarget(
        OperationIntentTarget(
            OperationKind.BEGIN_TURN,
            binding.attempt_id,
            binding.session_epoch_id,
            binding.process_generation_id,
            binding.worker_id,
            CONVERSATION,
        ),
        "bind-fixture",
        1,
        binding.host_ref,
        binding.seat_ref,
        binding.project_ref,
        CHATGPT_APP_BUNDLE_ID,
        "26.928.21956",
        PID,
        "process-start-10061",
        456,
    )


def _plan():
    target = _target()
    intent = OperationIntentReceipt(
        OperationId("ohf-op:chatgpt-gui-turn"),
        target.intent_target,
    )
    mode = ModeSelection("chat", "Fixture Exact Model", "PRO")
    before = DesktopSnapshot(
        target, "snapshot-before", NOW, "semantic", True, mode, "idle", "", ()
    )
    return prepare_turn(
        intent=intent,
        target=target,
        requested_mode=mode,
        prompt="Return the canary result.",
        snapshot=before,
        now=NOW,
    )


def _snapshot(plan=None):
    plan = _plan() if plan is None else plan
    mode = plan.requested_mode
    user = MessageEvidence(
        "user-1", "user", plan.wire_text, True, TURN
    )
    reply = MessageEvidence(
        "assistant-1", "assistant", "Canary result.", True, TURN, "user-1"
    )
    return DesktopSnapshot(
        plan.target,
        "snapshot-after",
        NOW + 1,
        "semantic",
        True,
        mode,
        "idle",
        "",
        (user, reply),
    )


def _observation(binding=None, helper_instance="helper-1", snapshot=None):
    binding = _binding() if binding is None else binding
    return ChatGPTGuiObservation(
        binding=binding,
        helper_instance_id=helper_instance,
        observed_at=NOW + 1,
        app_version="26.928.21956",
        pid=PID,
        process_start_ref="process-start-10061",
        window_id=456,
        provider_session_id=CONVERSATION,
        provider_native_turn_id=TURN,
        identity=_identity(),
        snapshot=snapshot,
    )


def _open(binding=None, helper_instance="helper-1"):
    binding = _binding() if binding is None else binding
    return ChatGPTGuiOpenReceipt(
        binding=binding,
        helper_instance_id=helper_instance,
        helper_binary_digest=binding.helper_binary_digest,
        helper_version=binding.helper_version,
        supported_operations=CHATGPT_GUI_OPERATIONS,
    )


def _close(binding=None, helper_instance="helper-1"):
    binding = _binding() if binding is None else binding
    return ChatGPTGuiCloseReceipt(
        binding=binding,
        helper_instance_id=helper_instance,
        closed=True,
        no_active_operation=True,
    )


def _mutation(binding, action, operation_id, effect=OperationResolution.APPLIED):
    return ChatGPTGuiMutationReceipt(
        binding=binding,
        helper_instance_id="helper-1",
        action=action,
        operation_id=operation_id,
        effect=effect,
        before_snapshot_id="snapshot-before",
        after_snapshot_id="snapshot-after",
    )


@dataclass
class FakeClient:
    open_receipt: ChatGPTGuiOpenReceipt
    observation: ChatGPTGuiObservation
    close_receipt: ChatGPTGuiCloseReceipt
    calls: list[tuple] = field(default_factory=list)

    def open_generation(self, binding):
        self.calls.append(("open_generation", binding))
        return self.open_receipt

    def observe_target(self, binding, *, provider_session_id):
        self.calls.append(("observe_target", binding, provider_session_id))
        return self.observation

    def prepare_composer(self, binding, plan):
        self.calls.append(("prepare_composer", binding, plan.intent.command_id))
        return _mutation(binding, "prepare_composer", plan.intent.command_id)

    def submit_prepared(self, binding, plan, prepared):
        self.calls.append(("submit_prepared", binding, plan.intent.command_id))
        return _mutation(binding, "submit_prepared", plan.intent.command_id)

    def observe_turn(self, binding, plan):
        self.calls.append(("observe_turn", binding, plan.intent.command_id))
        return replace(self.observation, snapshot=_snapshot(plan))

    def interrupt_turn(self, binding, plan, operation_id):
        self.calls.append(("interrupt_turn", binding, operation_id))
        return _mutation(binding, "interrupt_turn", operation_id)

    def reconcile(self, binding, plan):
        self.calls.append(("reconcile", binding, plan.intent.command_id))
        return replace(self.observation, snapshot=_snapshot(plan))

    def close_generation(self, binding):
        self.calls.append(("close_generation", binding))
        return self.close_receipt


def _resource(client=None):
    epoch, generation = _epoch_generation()
    if client is None:
        binding = _binding()
        client = FakeClient(_open(binding), _observation(binding), _close(binding))
    return ChatGPTGuiAttemptResource(
        client,
        epoch=epoch,
        generation=generation,
        host_ref="mini3",
        seat_ref="coo",
        project_ref="MastermindX",
        resource_contract_digest=RESOURCE_DIGEST,
        helper_binary_digest=HELPER_DIGEST,
        helper_version="1.0.0",
    )


def _sweep(*, residual_after=()):
    return UIDSweepReceipt(
        schema_version=UID_SWEEP_SCHEMA_VERSION,
        observed_at="2026-10-02T04:03:30+00:00",
        reason="operator_terminal",
        worker_uid=501,
        broker_pid=999,
        residual_pids_before=(),
        residual_pids_after=tuple(residual_after),
        signal_name="SIGTERM",
        signal_sent=False,
        quiescent_observations=2,
    )


def test_protocol_surface_has_no_generic_desktop_escape_hatches():
    assert CHATGPT_GUI_OPERATIONS == (
        "observe_target",
        "prepare_composer",
        "submit_prepared",
        "observe_turn",
        "interrupt_turn",
        "reconcile",
    )
    forbidden = {
        "action",
        "click",
        "clipboard",
        "shell",
        "type",
        "run_command",
        "select_app",
    }
    assert forbidden.isdisjoint(set(dir(ChatGPTGuiSeatClient)))
    assert forbidden.isdisjoint(set(CHATGPT_GUI_OPERATIONS))


def test_generation_binding_is_exact_and_chatgpt_only():
    binding = _binding()
    assert binding.app_bundle_id == CHATGPT_APP_BUNDLE_ID
    assert binding.resource_contract_digest == RESOURCE_DIGEST

    with pytest.raises(EvidenceError, match="app_bundle_not_allowed"):
        replace(binding, app_bundle_id="com.apple.TextEdit")
    with pytest.raises(EvidenceError, match="resource_contract_digest_invalid"):
        replace(binding, resource_contract_digest="not-a-digest")


def test_open_receipt_requires_closed_operation_surface():
    binding = _binding()
    with pytest.raises(EvidenceError, match="operation_surface_invalid"):
        ChatGPTGuiOpenReceipt(
            binding=binding,
            helper_instance_id="helper-1",
            helper_binary_digest=HELPER_DIGEST,
            helper_version="1.0.0",
            supported_operations=CHATGPT_GUI_OPERATIONS + ("action",),
        )


def test_resource_start_binds_exact_helper_identity_and_capability():
    resource = _resource()
    resource.start()
    client = resource.client
    assert client.calls == [("open_generation", resource.binding)]
    assert resource.observed_capability.name == "chatgpt-desktop-gui-v1"
    assert resource.observed_capability.resource_contract_digest == RESOURCE_DIGEST

    resource.stop()
    assert client.calls[-1] == ("close_generation", resource.binding)
    assert resource.seal_after_uid_sweep(_sweep()) is None


def test_resource_refuses_open_receipt_from_other_generation():
    binding = _binding()
    wrong = replace(binding, process_generation_id="generation-other")
    client = FakeClient(_open(wrong), _observation(binding), _close(binding))
    resource = _resource(client)
    with pytest.raises(EvidenceError, match="open_receipt_mismatch"):
        resource.start()


def test_observe_and_mutation_calls_are_generation_bound():
    resource = _resource()
    resource.start()
    observed = resource.observe_target(provider_session_id=CONVERSATION)
    assert observed.provider_session_id == CONVERSATION

    plan = _plan()
    prepared = resource.prepare_composer(plan)
    submitted = resource.submit_prepared(plan, prepared)
    after = resource.observe_turn(plan)
    reconciled = resource.reconcile(plan)
    interrupted = resource.interrupt_turn(
        plan,
        operation_id="ohf-op:interrupt-chatgpt-gui",
    )

    assert submitted.action == "submit_prepared"
    assert after.snapshot is not None
    assert reconciled.snapshot is not None
    assert interrupted.action == "interrupt_turn"
    for call in resource.client.calls:
        if call[0] != "open_generation":
            assert call[1] == resource.binding


def test_plan_requires_prior_exact_target_observation():
    resource = _resource()
    resource.start()
    with pytest.raises(EvidenceError, match="target_not_observed"):
        resource.prepare_composer(_plan())


@pytest.mark.parametrize(
    "field,value",
    [
        ("host_ref", "mini-other"),
        ("seat_ref", "ceo"),
        ("project_ref", "OtherProject"),
        ("pid", PID + 1),
        ("window_id", 999),
        ("process_start_ref", "new-process"),
        ("app_version", "next-build"),
    ],
)
def test_plan_cannot_retarget_observed_chatgpt_surface(field, value):
    resource = _resource()
    resource.start()
    resource.observe_target(provider_session_id=CONVERSATION)
    plan = _plan()
    wrong_target = replace(plan.target, **{field: value})
    wrong_plan = replace(plan, target=wrong_target)
    with pytest.raises(EvidenceError, match="plan_target_mismatch"):
        resource.prepare_composer(wrong_plan)


def test_provider_session_drift_refuses_before_mutation():
    resource = _resource()
    resource.start()
    resource.observe_target(provider_session_id=CONVERSATION)
    plan = _plan()
    other = replace(
        plan.target.intent_target,
        provider_session_id="01a0f4b0-23c8-70bb-a0e7-832e34f7e0c3",
    )
    wrong_target = replace(plan.target, intent_target=other)
    wrong_plan = replace(
        plan,
        target=wrong_target,
        intent=OperationIntentReceipt(plan.intent.operation_id, other),
    )
    with pytest.raises(EvidenceError, match="plan_target_mismatch"):
        resource.prepare_composer(wrong_plan)


def test_submit_requires_applied_prepare_from_same_helper_and_operation():
    resource = _resource()
    resource.start()
    resource.observe_target(provider_session_id=CONVERSATION)
    plan = _plan()
    refused = ChatGPTGuiMutationReceipt(
        binding=resource.binding,
        helper_instance_id="helper-1",
        action="prepare_composer",
        operation_id=plan.intent.command_id,
        effect=OperationResolution.REFUSED,
        before_snapshot_id="snapshot-before",
        after_snapshot_id=None,
    )
    before = len(resource.client.calls)
    with pytest.raises(EvidenceError, match="prepare_receipt_invalid"):
        resource.submit_prepared(plan, refused)
    assert len(resource.client.calls) == before


def test_helper_instance_drift_is_refused():
    binding = _binding()
    client = FakeClient(
        _open(binding),
        _observation(binding, helper_instance="helper-other"),
        _close(binding),
    )
    resource = _resource(client)
    resource.start()
    with pytest.raises(EvidenceError, match="helper_identity_mismatch"):
        resource.observe_target(provider_session_id=CONVERSATION)


def test_observation_requires_provider_log_and_semantic_snapshot_identity_agreement():
    binding = _binding()
    with pytest.raises(EvidenceError, match="provider_identity_mismatch"):
        replace(
            _observation(binding),
            provider_native_turn_id="01a0f4b0-2b47-77d2-a54e-c7bc2a46992f",
        )

    plan = _plan()
    wrong_snapshot = replace(_snapshot(plan), target=replace(plan.target, pid=PID + 1))
    with pytest.raises(EvidenceError, match="snapshot_target_mismatch"):
        _observation(binding, snapshot=wrong_snapshot)


def test_stop_requires_same_helper_instance_and_clean_close():
    binding = _binding()
    client = FakeClient(
        _open(binding),
        _observation(binding),
        _close(binding, helper_instance="helper-other"),
    )
    resource = _resource(client)
    resource.start()
    with pytest.raises(EvidenceError, match="close_receipt_mismatch"):
        resource.stop()

    with pytest.raises(EvidenceError, match="close_not_clean"):
        ChatGPTGuiCloseReceipt(
            binding=binding,
            helper_instance_id="helper-1",
            closed=True,
            no_active_operation=False,
        )


def test_seal_requires_helper_close_and_passing_existing_uid_sweep():
    resource = _resource()
    resource.start()
    with pytest.raises(EvidenceError, match="cleanup_not_closed"):
        resource.seal_after_uid_sweep(_sweep())

    resource.stop()
    with pytest.raises(EvidenceError, match="uid_sweep_not_passing"):
        resource.seal_after_uid_sweep(_sweep(residual_after=(9001,)))


def test_resource_methods_refuse_after_close():
    resource = _resource()
    resource.start()
    resource.observe_target(provider_session_id=CONVERSATION)
    resource.stop()
    with pytest.raises(EvidenceError, match="resource_closed"):
        resource.observe_target(provider_session_id=CONVERSATION)


def test_generation_constructor_rejects_epoch_worker_drift():
    epoch, generation = _epoch_generation()
    wrong = replace(generation, worker_id="worker-other")
    with pytest.raises(EvidenceError, match="generation_identity_mismatch"):
        ChatGPTGuiAttemptResource(
            FakeClient(_open(), _observation(), _close()),
            epoch=epoch,
            generation=wrong,
            host_ref="mini3",
            seat_ref="coo",
            project_ref="MastermindX",
            resource_contract_digest=RESOURCE_DIGEST,
            helper_binary_digest=HELPER_DIGEST,
            helper_version="1.0.0",
        )
