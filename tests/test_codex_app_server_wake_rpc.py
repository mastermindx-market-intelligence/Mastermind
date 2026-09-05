from __future__ import annotations

import asyncio
import dataclasses
import inspect
import threading
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import pytest

from control_plane import codex_operator_adapter as codex_adapter
from control_plane import executive_worker_broker as broker_module
from control_plane import runtime_binding_projection
from control_plane.executive_worker_broker import (
    BrokerEffectUnknownError,
    BrokerPreSubmitError,
    BrokerProtocolError,
    RemoteBrokerError,
)
from control_plane.operator_harness_contract import (
    ATTENTION_TURN_INSTRUCTION,
    AttentionTurnObservation,
    AuthRealmFact,
    CapabilityManifest,
    LaunchDecision,
    NativeHelperPolicy,
    ObservedHarnessAttestation,
    ObservedTriState,
    OperationId,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProcessLiveness,
    ProviderSessionHandoff,
    ProviderWriterState,
    ReconcileObservation,
    RequestedExecutionProfile,
    SessionEpochRef,
    TurnRef,
    WorkerLocalWakeAckProjection,
    WorkspaceIdentity,
    runtime_binding_id_for,
)
from control_plane.session_targets import RuntimeBinding
from control_plane.wake_ack_ingress import TrustedWorkerWakeAckProjection
from control_plane.operator_harness_wire import (
    attention_turn_observation,
    reconcile_observation,
    to_wire,
)
from control_plane.operator_materialization_receipt import (
    MATERIALIZATION_STATUS_SCHEMA,
    build_operator_materialization_receipt,
    requested_profile_digest,
)
from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
from control_plane.wake_dispatcher import WakePreSubmitError
from integrations.executive_wake.codex_app_server import CODEX_WAKE_INSTRUCTION
from integrations.executive_wake import codex_app_server_rpc as wake_rpc
from integrations.executive_wake.codex_app_server_rpc import CodexCurrentWriterWakeClient
from scripts.ohf.laboratory import AppServerStopProof, JsonRpcError


NATIVE_HANDLE = "019cafe0-1111-7222-8333-abcdefabcdef"
NUDGE_ID = "NUDGE-" + "2" * 32
OPAQUE_IDS = ("WAKE-123", "WAKE-123:ATTEMPT:1")
ACK_OID_A = "WAKE-" + "a" * 32
ACK_OID_B = "WAKE-" + "b" * 32
ACK_OPAQUE_IDS = (ACK_OID_A, ACK_OID_B, f"{ACK_OID_A}:A1", f"{ACK_OID_B}:A1")
ATTEMPT_ID = "ATT-" + "1" * 32
EPOCH = SessionEpochRef(
    session_epoch_id="epoch-123",
    attempt_id=ATTEMPT_ID,
    worker_id="worker-123",
    epoch_number=3,
)
GENERATION = ProcessGenerationRef(
    process_generation_id="generation-123",
    session_epoch_id="epoch-123",
    generation_number=7,
    worker_id="worker-123",
)
BINDING = RuntimeBinding(
    session_alias="EXECUTIVE-CTO-FORGE",
    binding_id=runtime_binding_id_for(ATTEMPT_ID, EPOCH.session_epoch_id),
    binding_generation=GENERATION.generation_number,
    native_handle=NATIVE_HANDLE,
    reasoning_surface="codex",
)
PROCESS = ProcessIdentityObservation(
    pid=4242,
    pgid=4242,
    process_start_identity="Mon Aug 30 01:00:00 2026",
    boot_id="boot-123",
)


@dataclass
class FakeOwnedAppServerClient:
    turn_id: str = "turn-wake-456"
    fail_request: bool = False
    completion_timeout: bool = False
    completion: Mapping[str, Any] | None = None
    queued_notifications: list[dict[str, Any]] = field(default_factory=list)
    running: bool = True
    calls: list[tuple[str, object]] = field(default_factory=list)

    def alive(self) -> bool:
        self.calls.append(("alive", None))
        return self.running

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        self.calls.append((method, dict(params or {})))
        if method == "thread/read":
            return {"thread": {"id": NATIVE_HANDLE}}
        if method != "turn/start":
            raise AssertionError(f"second-writer/cold-resume method attempted: {method}")
        if self.fail_request:
            raise RuntimeError("turn/start transport lost")
        return {"turn": {"id": self.turn_id}}

    def wait_notification(self, method: str, *, timeout: float = 15.0) -> dict[str, Any]:
        self.calls.append((f"wait:{method}", timeout))
        for notification in self.queued_notifications:
            if notification.get("method") == method:
                self.queued_notifications.remove(notification)
                return notification
        if self.completion_timeout:
            raise JsonRpcError(f"timeout waiting for notification {method}")
        if self.completion is not None:
            completion = dict(self.completion)
            self.completion = None
            return completion
        return {
            "method": "turn/completed",
            "params": {
                "threadId": NATIVE_HANDLE,
                "turn": {"id": self.turn_id, "status": "completed"},
            },
        }

    def drain_notifications(self) -> list[dict[str, Any]]:
        self.calls.append(("drain_notifications", None))
        return []

    def graceful_close(self, *, wait: float = 5.0) -> AppServerStopProof:
        self.calls.append(("graceful_close", wait))
        self.running = False
        return AppServerStopProof(
            controller_returncode=0,
            private_group_id=4242,
            private_group_empty=True,
            leader_exit_confirmed_graceful=True,
            survivors_detected_after_controller_exit=False,
            termination_outcome="graceful",
        )

    def terminate(self, *, wait: float = 5.0) -> None:
        self.calls.append(("terminate", wait))
        self.running = False


@dataclass
class FakeBoundBrowserResource:
    """Minimal real adapter boundary for the Browser B1 turn contract."""

    prompt_calls: int = 0
    observed_results: list[str] = field(default_factory=list)
    stop_calls: int = 0

    def turn_prompt_suffix(self) -> str:
        self.prompt_calls += 1
        return "\n\nBROWSER_B1_CLOSED_TURN_CONTRACT"

    def observe_canonical_result(self, value: str) -> None:
        self.observed_results.append(value)

    def stop(self) -> None:
        self.stop_calls += 1


def _owned_adapter(
    client: FakeOwnedAppServerClient,
    *,
    provider_session_id: str = NATIVE_HANDLE,
    observed_process: ProcessIdentityObservation = PROCESS,
    writer_state: ProviderWriterState = ProviderWriterState.HELD,
    resource: FakeBoundBrowserResource | None = None,
):
    adapter = object.__new__(codex_adapter.CodexOperatorAdapter)
    adapter.worker_id = GENERATION.worker_id
    adapter.workspace_root = Path("/tmp/mastermind-w3a-owned-workspace")
    adapter.process_identity_observer = lambda _pid: observed_process
    requested = SimpleNamespace(approval_policy="never")
    attestation = SimpleNamespace(effective_config_digest="d" * 64)
    adapter._active_workers = {
        adapter.worker_id: GENERATION.process_generation_id,
    }
    adapter._generations = {
        GENERATION.process_generation_id: SimpleNamespace(
            epoch=EPOCH,
            generation=GENERATION,
            provider_session_id=provider_session_id,
            writer_state=writer_state,
            client=client,
            process=PROCESS,
            requested=requested,
            attestation=attestation,
            resource=resource,
            events=[],
            turns={},
            turn_subordinates={},
            attention_inflight=False,
            attention_native_turn_id=None,
        )
    }
    return adapter


def _begin_ordinary_turn(adapter: codex_adapter.CodexOperatorAdapter) -> None:
    state = adapter._generations[GENERATION.process_generation_id]
    adapter.turn_input_loader = lambda _turn: "ordinary governed turn"
    adapter.begin_turn(
        operation_id=object(),
        turn=TurnRef(
            turn_id="ordinary-turn-1",
            session_epoch_id=EPOCH.session_epoch_id,
            process_generation_id=GENERATION.process_generation_id,
            attempt_id=ATTEMPT_ID,
        ),
        generation=GENERATION,
        launch=SimpleNamespace(
            decision=LaunchDecision.ALLOW,
            observed=state.attestation,
            requested=state.requested,
        ),
    )


def test_attention_observation_is_closed_and_delivery_requires_acceptance() -> None:
    assert ATTENTION_TURN_INSTRUCTION == CODEX_WAKE_INSTRUCTION
    assert runtime_binding_id_for(ATTEMPT_ID, EPOCH.session_epoch_id) == BINDING.binding_id
    observation = AttentionTurnObservation(
        process_generation_id=GENERATION.process_generation_id,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        provider_native_turn_id="turn-wake-456",
        accepted=True,
        delivered=True,
    )

    assert [item.name for item in fields(WorkerLocalWakeAckProjection)] == [
        "target_attempt_id",
        "process_generation_id",
        "binding_id",
        "binding_generation",
        "provider_session_id",
        "provider_native_turn_id",
        "nudge_id",
        "obligation_ids",
        "terminal_ack_trailer",
    ]
    assert observation.wake_ack_projection is None


_MISSING_STATUS = object()


def _completion_with_text(
    text: str,
    *,
    status: object = "completed",
) -> dict[str, Any]:
    completion = {
        "method": "turn/completed",
        "params": {
            "threadId": NATIVE_HANDLE,
            "turn": {
                "id": "turn-wake-456",
                "items": [
                    {
                        "type": "agentMessage",
                        "phase": "final_answer",
                        "text": text,
                    }
                ],
            },
        },
    }
    if status is not _MISSING_STATUS:
        completion["params"]["turn"]["status"] = status
    return completion


def _deliver_marker_text(text: str) -> AttentionTurnObservation:
    client = FakeOwnedAppServerClient(completion=_completion_with_text(text))
    return _owned_adapter(client).deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=ACK_OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )


def test_attention_instruction_preserves_disclaimer_and_adds_bounded_marker_contract() -> None:
    assert "grants no authority, acknowledges nothing, and does not resolve the source" in (
        ATTENTION_TURN_INSTRUCTION
    )
    assert (
        "After you have actually consumed the supplied Wake obligation(s) and recovered "
        "canonical Executive/Agent OS state, emit one final marker line per consumed obligation:"
        in ATTENTION_TURN_INSTRUCTION
    )
    assert "MASTERMIND_WAKE_ACK <WAKE-ID>" in ATTENTION_TURN_INSTRUCTION
    assert (
        "Do not put seat, session, binding, provider, host, nudge, source-resolution or "
        "authority data in the marker."
        in ATTENTION_TURN_INSTRUCTION
    )


@pytest.mark.parametrize(
    "text",
    [
        "ordinary completion without a marker",
        "I saw MASTERMIND_WAKE_ACK in the supplied instruction.",
        f"`MASTERMIND_WAKE_ACK {ACK_OID_A}`",
        f"> MASTERMIND_WAKE_ACK {ACK_OID_A}",
        f"- MASTERMIND_WAKE_ACK {ACK_OID_A}",
        f"```text\nMASTERMIND_WAKE_ACK {ACK_OID_A}\n```",
        f"```text\nMASTERMIND_WAKE_ACK {ACK_OID_A}",
        f"```text\n```not-a-closing-fence\nMASTERMIND_WAKE_ACK {ACK_OID_A}",
        f"MASTERMIND_WAKE_ACK {ACK_OID_A}\nLater prose makes this nonterminal.",
    ],
)
def test_worker_local_terminal_trailer_ignores_instruction_echo_shapes(text: str) -> None:
    observation = _deliver_marker_text(text)

    assert observation.delivered is True
    assert observation.wake_ack_projection is None


def test_worker_local_terminal_trailer_reduces_one_exact_marker() -> None:
    observation = _deliver_marker_text(
        f"Recovered canonical state.\n\nMASTERMIND_WAKE_ACK {ACK_OID_A}\n"
    )

    assert observation.wake_ack_projection == WorkerLocalWakeAckProjection(
        target_attempt_id=ATTEMPT_ID,
        process_generation_id=GENERATION.process_generation_id,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        provider_native_turn_id="turn-wake-456",
        nudge_id=NUDGE_ID,
        obligation_ids=(ACK_OID_A,),
        terminal_ack_trailer=True,
    )


def test_worker_local_terminal_trailer_reduces_distinct_atomic_batch_only() -> None:
    observation = _deliver_marker_text(
        "\n".join(
            (
                f"```text\nMASTERMIND_WAKE_ACK {'WAKE-' + 'c' * 32}\n```",
                "Recovered canonical state.",
                f"MASTERMIND_WAKE_ACK {ACK_OID_B}",
                f"MASTERMIND_WAKE_ACK {ACK_OID_A}",
            )
        )
    )

    assert observation.wake_ack_projection is not None
    assert observation.wake_ack_projection.obligation_ids == tuple(
        sorted((ACK_OID_A, ACK_OID_B))
    )


@pytest.mark.parametrize(
    "text",
    [
        f"MASTERMIND_WAKE_ACK {ACK_OID_A}\nMASTERMIND_WAKE_ACK {ACK_OID_A}",
        "MASTERMIND_WAKE_ACK WAKE-malformed",
    ],
)
def test_worker_local_completed_duplicate_or_malformed_trailer_is_inert(
    text: str,
) -> None:
    client = FakeOwnedAppServerClient(completion=_completion_with_text(text))
    observation = _owned_adapter(client).deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=ACK_OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation.accepted is True
    assert observation.delivered is True
    assert observation.wake_ack_projection is None
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_worker_local_completed_conflicting_text_representations_are_inert() -> None:
    completion = _completion_with_text(f"MASTERMIND_WAKE_ACK {ACK_OID_A}")
    item = completion["params"]["turn"]["items"][0]
    item["content"] = [
        {
            "type": "output_text",
            "text": f"MASTERMIND_WAKE_ACK {ACK_OID_B}",
        }
    ]
    client = FakeOwnedAppServerClient(completion=completion)

    observation = _owned_adapter(client).deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=ACK_OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation.accepted is True
    assert observation.delivered is True
    assert observation.wake_ack_projection is None
    assert [name for name, _payload in client.calls].count("turn/start") == 1


@pytest.mark.parametrize("status", ("failed", "interrupted"))
def test_known_terminal_provider_failure_is_accepted_not_delivered(
    status: str,
) -> None:
    client = FakeOwnedAppServerClient(
        completion=_completion_with_text(
            f"MASTERMIND_WAKE_ACK {ACK_OID_A}",
            status=status,
        )
    )
    adapter = _owned_adapter(client)
    state = adapter._generations[GENERATION.process_generation_id]

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=ACK_OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation.accepted is True
    assert observation.delivered is False
    assert observation.wake_ack_projection is None
    assert state.attention_inflight is False
    assert state.attention_native_turn_id is None
    assert [name for name, _payload in client.calls].count("turn/start") == 1


@pytest.mark.parametrize(
    "status",
    (_MISSING_STATUS, "unknown", "inProgress"),
    ids=("missing", "unknown", "nonterminal"),
)
def test_unrecognized_completion_status_retains_no_resend_fence(
    status: object,
) -> None:
    client = FakeOwnedAppServerClient(
        completion=_completion_with_text(
            f"MASTERMIND_WAKE_ACK {ACK_OID_A}",
            status=status,
        )
    )
    adapter = _owned_adapter(client)
    state = adapter._generations[GENERATION.process_generation_id]

    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=ACK_OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.effect_unknown is True
    assert state.attention_inflight is True
    assert state.attention_native_turn_id == "turn-wake-456"
    with pytest.raises(codex_adapter.CodexAdapterError) as second:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id="nudge-456",
            opaque_ids=ACK_OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )
    assert second.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    with pytest.raises(codex_adapter.CodexAdapterError) as ordinary:
        _begin_ordinary_turn(adapter)
    assert ordinary.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_attention_projection_wire_is_closed_and_rejects_unknown_nested_fields() -> None:
    projection = WorkerLocalWakeAckProjection(
        target_attempt_id=ATTEMPT_ID,
        process_generation_id=GENERATION.process_generation_id,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        provider_native_turn_id="turn-wake-456",
        nudge_id=NUDGE_ID,
        obligation_ids=(ACK_OID_A,),
        terminal_ack_trailer=True,
    )
    observation = AttentionTurnObservation(
        process_generation_id=GENERATION.process_generation_id,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        provider_native_turn_id="turn-wake-456",
        accepted=True,
        delivered=True,
        wake_ack_projection=projection,
    )
    wire = to_wire(observation)

    assert attention_turn_observation(wire) == observation
    wire["wake_ack_projection"]["raw_model_text"] = "must not cross"
    with pytest.raises(Exception, match="fields"):
        attention_turn_observation(wire)
    assert observation.delivered is True

    with pytest.raises(ValueError):
        AttentionTurnObservation(
            process_generation_id=GENERATION.process_generation_id,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            provider_native_turn_id=None,
            accepted=False,
            delivered=True,
        )

    with pytest.raises(ValueError, match="native turn"):
        AttentionTurnObservation(
            process_generation_id=GENERATION.process_generation_id,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            provider_native_turn_id="turn-wake-456",
            accepted=False,
            delivered=False,
        )


def test_runtime_binding_projector_delegates_identity_to_shared_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The canonical projector must not maintain a second binding-id formula."""

    sentinel = "bind-" + "f" * 40
    facts = SimpleNamespace(
        attempt_id=ATTEMPT_ID,
        session_epoch_id=EPOCH.session_epoch_id,
        generation_number=GENERATION.generation_number,
        provider_session_id=NATIVE_HANDLE,
        account_label="account-a",
    )
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        runtime_binding_projection,
        "active_operator_binding_facts",
        lambda _runtime, _attempt_id, _target, connection=None: facts,
    )

    def shared_binding_id(attempt_id: str, session_epoch_id: str) -> str:
        calls.append((attempt_id, session_epoch_id))
        return sentinel

    monkeypatch.setattr(
        runtime_binding_projection,
        "runtime_binding_id_for",
        shared_binding_id,
        raising=False,
    )

    projected = runtime_binding_projection.project_runtime_binding(
        object(),
        ATTEMPT_ID,
        SimpleNamespace(
            session_alias="EXECUTIVE-CTO-FORGE",
            reasoning_surface="codex",
        ),
    )

    assert projected.binding_id == sentinel
    assert calls == [(ATTEMPT_ID, EPOCH.session_epoch_id)]


def test_worker_local_attention_reuses_exact_owned_generation_without_start_or_resume() -> None:
    client = FakeOwnedAppServerClient()
    adapter = _owned_adapter(client)

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation == AttentionTurnObservation(
        process_generation_id=GENERATION.process_generation_id,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        provider_native_turn_id="turn-wake-456",
        accepted=True,
        delivered=True,
    )
    methods = [name for name, _payload in client.calls]
    assert "start" not in methods
    assert "initialize" not in methods
    assert "thread/resume" not in methods
    assert "thread/start" not in methods
    assert methods.count("turn/start") == 1
    payload = next(payload for name, payload in client.calls if name == "turn/start")
    assert payload["threadId"] == NATIVE_HANDLE
    assert payload["clientUserMessageId"] == NUDGE_ID
    assert payload["input"][0]["type"] == "text"
    assert payload["input"][0]["text_elements"] == []
    assert CODEX_WAKE_INSTRUCTION in payload["input"][0]["text"]
    for opaque_id in OPAQUE_IDS:
        assert opaque_id in payload["input"][0]["text"]


def test_provider_session_drift_refuses_before_provider_io() -> None:
    client = FakeOwnedAppServerClient()
    adapter = _owned_adapter(client, provider_session_id="foreign-session")

    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.effect_unknown is False
    assert error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert client.calls == []


def test_attempt_drift_refuses_before_provider_io() -> None:
    client = FakeOwnedAppServerClient()
    adapter = _owned_adapter(client)

    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id="attempt-foreign",
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert error.value.effect_unknown is False
    assert client.calls == []


@pytest.mark.parametrize(
    ("binding_id", "binding_generation"),
    (
        ("bind-ffffffffffffffffffffffffffffffffffffffff", BINDING.binding_generation),
        (BINDING.binding_id, BINDING.binding_generation + 1),
    ),
)
def test_runtime_binding_drift_refuses_at_worker_local_edge_before_provider_io(
    binding_id: str,
    binding_generation: int,
) -> None:
    client = FakeOwnedAppServerClient()
    adapter = _owned_adapter(client)

    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=binding_id,
            binding_generation=binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert error.value.effect_unknown is False
    assert client.calls == []


def test_released_writer_refuses_before_provider_io() -> None:
    client = FakeOwnedAppServerClient()
    adapter = _owned_adapter(client, writer_state=ProviderWriterState.RELEASED)

    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert error.value.effect_unknown is False
    assert client.calls == []


def test_active_normal_turn_refuses_attention_before_provider_io() -> None:
    client = FakeOwnedAppServerClient()
    adapter = _owned_adapter(client)
    state = adapter._generations[GENERATION.process_generation_id]
    state.turns = {"executive-turn-1": "provider-turn-1"}
    state.events = []

    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert error.value.effect_unknown is False
    assert client.calls == []


def test_process_identity_drift_refuses_before_provider_io() -> None:
    client = FakeOwnedAppServerClient()
    adapter = _owned_adapter(
        client,
        observed_process=ProcessIdentityObservation(
            pid=9999,
            pgid=9999,
            process_start_identity="different",
            boot_id="boot-foreign",
        ),
    )

    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.effect_unknown is False
    assert client.calls == []


def test_turn_start_transport_loss_is_effect_unknown() -> None:
    client = FakeOwnedAppServerClient(fail_request=True)
    adapter = _owned_adapter(client)

    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.effect_unknown is True
    assert [name for name, _payload in client.calls].count("turn/start") == 1

    with pytest.raises(codex_adapter.CodexAdapterError) as second:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id="nudge-456",
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert second.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert second.value.effect_unknown is False
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_completion_timeout_is_accepted_not_delivered_on_same_owned_writer() -> None:
    client = FakeOwnedAppServerClient(completion_timeout=True)
    adapter = _owned_adapter(client)

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation.accepted is True
    assert observation.delivered is False
    assert observation.provider_native_turn_id == "turn-wake-456"


def test_completion_timeout_blocks_a_second_attention_provider_write() -> None:
    client = FakeOwnedAppServerClient(completion_timeout=True)
    adapter = _owned_adapter(client)

    first = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert first.accepted is True
    assert first.delivered is False
    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id="nudge-456",
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert error.value.effect_unknown is False
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_completion_timeout_blocks_ordinary_turn_provider_write() -> None:
    client = FakeOwnedAppServerClient(completion_timeout=True)
    adapter = _owned_adapter(client)

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation.accepted is True
    assert observation.delivered is False
    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        _begin_ordinary_turn(adapter)

    assert error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert error.value.effect_unknown is False
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_post_submit_effect_unknown_blocks_ordinary_turn_provider_write() -> None:
    client = FakeOwnedAppServerClient(fail_request=True)
    adapter = _owned_adapter(client)

    with pytest.raises(codex_adapter.CodexAdapterError) as attention_error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert attention_error.value.effect_unknown is True
    client.fail_request = False
    with pytest.raises(codex_adapter.CodexAdapterError) as ordinary_error:
        _begin_ordinary_turn(adapter)

    assert ordinary_error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert ordinary_error.value.effect_unknown is False
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_mismatched_completion_blocks_ordinary_turn_provider_write() -> None:
    client = FakeOwnedAppServerClient(
        completion={
            "method": "turn/completed",
            "params": {
                "threadId": NATIVE_HANDLE,
                "turn": {"id": "stale-turn", "status": "completed"},
            },
        }
    )
    adapter = _owned_adapter(client)

    with pytest.raises(codex_adapter.CodexAdapterError) as attention_error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert attention_error.value.effect_unknown is True
    with pytest.raises(codex_adapter.CodexAdapterError) as ordinary_error:
        _begin_ordinary_turn(adapter)

    assert ordinary_error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert ordinary_error.value.effect_unknown is False
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_exact_completion_allows_later_ordinary_turn() -> None:
    client = FakeOwnedAppServerClient()
    adapter = _owned_adapter(client)

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation.delivered is True
    _begin_ordinary_turn(adapter)
    assert [name for name, _payload in client.calls].count("turn/start") == 2


def test_composed_exact_attention_completion_preserves_browser_turn_contract() -> None:
    """Clearing the attention fence must not clear the Browser B1 resource."""

    client = FakeOwnedAppServerClient()
    resource = FakeBoundBrowserResource()
    adapter = _owned_adapter(client, resource=resource)
    state = adapter._generations[GENERATION.process_generation_id]

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation.delivered is True
    assert state.attention_inflight is False
    assert state.attention_native_turn_id is None
    assert state.resource is resource
    assert resource.prompt_calls == 0
    assert resource.observed_results == []

    _begin_ordinary_turn(adapter)

    turn_starts = [payload for name, payload in client.calls if name == "turn/start"]
    assert len(turn_starts) == 2
    assert turn_starts[1]["input"] == [
        {
            "type": "text",
            "text": "ordinary governed turn\n\nBROWSER_B1_CLOSED_TURN_CONTRACT",
        }
    ]
    assert state.resource is resource
    assert resource.prompt_calls == 1
    assert resource.observed_results == []


def test_composed_attention_timeout_keeps_browser_resource_and_blocks_turn() -> None:
    """A completion timeout must retain both fences after exactly one write."""

    client = FakeOwnedAppServerClient(completion_timeout=True)
    resource = FakeBoundBrowserResource()
    adapter = _owned_adapter(client, resource=resource)
    state = adapter._generations[GENERATION.process_generation_id]

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation.accepted is True
    assert observation.delivered is False
    assert state.attention_inflight is True
    assert state.attention_native_turn_id == "turn-wake-456"
    assert state.resource is resource

    with pytest.raises(codex_adapter.CodexAdapterError) as error:
        _begin_ordinary_turn(adapter)

    assert error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
    assert resource.prompt_calls == 0
    assert resource.observed_results == []
    assert [name for name, _payload in client.calls].count("turn/start") == 1


@pytest.mark.parametrize("status", ("completed", "failed", "interrupted"))
def test_reconcile_late_recognized_terminal_status_clears_only_attention_fence(
    status: str,
) -> None:
    """The owned reader may reconcile a late exact completion without a resend."""

    client = FakeOwnedAppServerClient(completion_timeout=True)
    resource = FakeBoundBrowserResource()
    adapter = _owned_adapter(client, resource=resource)
    state = adapter._generations[GENERATION.process_generation_id]

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )
    assert observation.delivered is False
    client.queued_notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": NATIVE_HANDLE,
                "turn": {"id": "turn-wake-456", "status": status},
            },
        }
    )

    reconciled = adapter.reconcile(GENERATION)

    assert reconciled.provider_session_reachable is True
    late = reconciled.late_attention_observation
    assert late is not None
    assert late.process_generation_id == GENERATION.process_generation_id
    assert late.provider_session_id == NATIVE_HANDLE
    assert late.nudge_id == NUDGE_ID
    assert late.provider_native_turn_id == "turn-wake-456"
    assert late.accepted is True
    assert late.delivered is (status == "completed")
    assert late.wake_ack_projection is None
    assert state.attention_inflight is False
    assert state.attention_native_turn_id is None
    assert state.resource is resource
    assert resource.prompt_calls == 0
    assert resource.observed_results == []
    assert resource.stop_calls == 0

    _begin_ordinary_turn(adapter)

    turn_starts = [payload for name, payload in client.calls if name == "turn/start"]
    assert len(turn_starts) == 2
    assert turn_starts[1]["input"] == [
        {
            "type": "text",
            "text": "ordinary governed turn\n\nBROWSER_B1_CLOSED_TURN_CONTRACT",
        }
    ]


@pytest.mark.parametrize(
    "status",
    (_MISSING_STATUS, "unknown", "inProgress"),
    ids=("missing", "unknown", "nonterminal"),
)
def test_reconcile_late_unrecognized_status_keeps_no_resend_fence(
    status: object,
) -> None:
    client = FakeOwnedAppServerClient(completion_timeout=True)
    resource = FakeBoundBrowserResource()
    adapter = _owned_adapter(client, resource=resource)
    state = adapter._generations[GENERATION.process_generation_id]

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )
    assert observation.delivered is False
    client.queued_notifications.append(
        _completion_with_text("late provider result", status=status)
    )

    adapter.reconcile(GENERATION)

    assert state.attention_inflight is True
    assert state.attention_native_turn_id == "turn-wake-456"
    assert state.resource is resource
    with pytest.raises(codex_adapter.CodexAdapterError):
        _begin_ordinary_turn(adapter)
    assert resource.prompt_calls == 0
    assert resource.observed_results == []
    assert resource.stop_calls == 0
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_reconcile_late_completed_returns_exact_closed_ack_projection() -> None:
    """Catches consuming a valid late ACK while returning no persisted-Wake projection."""

    client = FakeOwnedAppServerClient(completion_timeout=True)
    adapter = _owned_adapter(client)

    first = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=ACK_OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )
    assert first.accepted is True and first.delivered is False
    client.queued_notifications.append(
        _completion_with_text(
            f"provider result\nMASTERMIND_WAKE_ACK {ACK_OID_B}\n"
            f"MASTERMIND_WAKE_ACK {ACK_OID_A}",
            status="completed",
        )
    )

    reconciled = adapter.reconcile(GENERATION)

    late = reconciled.late_attention_observation
    assert late is not None and late.delivered is True
    assert late.wake_ack_projection == _worker_projection()
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_reconcile_wire_round_trip_preserves_only_typed_late_attention() -> None:
    """Catches the existing OHF wire discarding the transient late projection."""

    late = AttentionTurnObservation(
        process_generation_id=GENERATION.process_generation_id,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        provider_native_turn_id="turn-wake-456",
        accepted=True,
        delivered=True,
        wake_ack_projection=_worker_projection(),
    )
    observation = ReconcileObservation(
        process_liveness=ProcessLiveness.ALIVE,
        observed_process=PROCESS,
        provider_session_reachable=True,
        provider_writer_state=ProviderWriterState.HELD,
        observed_provider_session_id=NATIVE_HANDLE,
        late_attention_observation=late,
    )

    assert reconcile_observation(to_wire(observation)) == observation


@pytest.mark.parametrize(
    ("thread_id", "turn_id"),
    ((NATIVE_HANDLE, "stale-turn"), ("wrong-thread", "turn-wake-456")),
)
def test_reconcile_stale_attention_completion_keeps_no_resend_fence(
    thread_id: str,
    turn_id: str,
) -> None:
    """A late completion clears the fence only on both exact identities."""

    client = FakeOwnedAppServerClient(completion_timeout=True)
    resource = FakeBoundBrowserResource()
    adapter = _owned_adapter(client, resource=resource)
    state = adapter._generations[GENERATION.process_generation_id]

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )
    assert observation.delivered is False
    client.queued_notifications.append(
        {
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {"id": turn_id, "status": "completed"},
            },
        }
    )

    adapter.reconcile(GENERATION)

    assert state.attention_inflight is True
    assert state.attention_native_turn_id == "turn-wake-456"
    assert state.resource is resource
    with pytest.raises(codex_adapter.CodexAdapterError):
        _begin_ordinary_turn(adapter)
    assert resource.prompt_calls == 0
    assert resource.observed_results == []
    assert resource.stop_calls == 0
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_composed_stale_completion_clears_neither_attention_nor_browser_fence() -> None:
    """A stale native completion cannot release either composed owner state."""

    client = FakeOwnedAppServerClient(
        completion={
            "method": "turn/completed",
            "params": {
                "threadId": NATIVE_HANDLE,
                "turn": {"id": "stale-turn", "status": "completed"},
            },
        }
    )
    resource = FakeBoundBrowserResource()
    adapter = _owned_adapter(client, resource=resource)
    state = adapter._generations[GENERATION.process_generation_id]

    with pytest.raises(codex_adapter.CodexAdapterError) as attention_error:
        adapter.deliver_attention(
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            binding_id=BINDING.binding_id,
            binding_generation=BINDING.binding_generation,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert attention_error.value.effect_unknown is True
    assert state.attention_inflight is True
    assert state.attention_native_turn_id == "turn-wake-456"
    assert state.resource is resource

    with pytest.raises(codex_adapter.CodexAdapterError):
        _begin_ordinary_turn(adapter)

    assert resource.prompt_calls == 0
    assert resource.observed_results == []
    assert [name for name, _payload in client.calls].count("turn/start") == 1


@pytest.mark.parametrize("terminal_operation", ("graceful_stop", "cancel"))
def test_composed_terminal_adapter_path_synthesizes_no_attention_or_browser_cleanup(
    terminal_operation: str,
) -> None:
    """Provider termination is not an attention completion or resource cleanup."""

    client = FakeOwnedAppServerClient(completion_timeout=True)
    resource = FakeBoundBrowserResource()
    adapter = _owned_adapter(client, resource=resource)
    state = adapter._generations[GENERATION.process_generation_id]

    observation = adapter.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )
    assert observation.delivered is False

    if terminal_operation == "graceful_stop":
        terminal = adapter.graceful_stop(GENERATION, operation_id=object())
        assert terminal.provider_writer_state is ProviderWriterState.RELEASED
    else:
        terminal = adapter.cancel(
            GENERATION,
            reason="bounded test cancellation",
            operation_id=object(),
        )
        assert terminal.provider_writer_state is ProviderWriterState.UNKNOWN

    assert state.attention_inflight is True
    assert state.attention_native_turn_id == "turn-wake-456"
    assert state.resource is resource
    assert resource.prompt_calls == 0
    assert resource.observed_results == []
    assert resource.stop_calls == 0
    assert [name for name, _payload in client.calls].count("turn/start") == 1


@dataclass
class FakeBrokerClient:
    response: AttentionTurnObservation
    calls: list[tuple[str, object, float | None]] = field(default_factory=list)

    def request_sync(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        self.calls.append((operation, dict(payload), timeout_seconds))
        return {"observation": to_wire(self.response)}


def test_remote_adapter_uses_one_closed_worker_broker_attention_operation() -> None:
    expected = AttentionTurnObservation(
        process_generation_id=GENERATION.process_generation_id,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        provider_native_turn_id="turn-wake-456",
        accepted=True,
        delivered=True,
    )
    broker = FakeBrokerClient(expected)
    remote = RemoteCodexOperatorAdapter(broker, turn_input_loader=lambda _turn: "unused")

    observation = remote.deliver_attention(
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation == expected
    assert len(broker.calls) == 1
    operation, payload, timeout = broker.calls[0]
    assert operation == "ohf-deliver-attention"
    assert payload["generation"] == to_wire(GENERATION)
    assert payload["attempt_id"] == ATTEMPT_ID
    assert payload["binding_id"] == BINDING.binding_id
    assert payload["binding_generation"] == BINDING.binding_generation
    assert payload["provider_session_id"] == NATIVE_HANDLE
    assert payload["nudge_id"] == NUDGE_ID
    assert payload["opaque_ids"] == list(OPAQUE_IDS)
    assert payload["instruction"] == CODEX_WAKE_INSTRUCTION
    assert payload["completion_timeout_seconds"] == 3.0
    assert timeout is not None


@dataclass
class FakeMaterializationStatusClient:
    response: dict[str, Any]
    calls: list[tuple[str, object, float | None]] = field(default_factory=list)

    def request_sync(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        self.calls.append((operation, dict(payload), timeout_seconds))
        return dict(self.response)


def test_remote_adapter_uses_one_bounded_materialization_status_request() -> None:
    attempt_id = "ATT-STATUS"
    epoch = SessionEpochRef("epoch-status", attempt_id, "worker-123", 1)
    generation = ProcessGenerationRef(
        "generation-status", epoch.session_epoch_id, 1, "worker-123"
    )
    workspace = WorkspaceIdentity("/tmp/status-workspace", "b" * 40, 1, 2, 3, 4)
    requested = RequestedExecutionProfile(
        worker_id="worker-123",
        provider="openai-codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest="a" * 64,
        harness_version="0.147.0",
        workspace=workspace,
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash="c" * 64,
    )
    process = {
        "pid": 4242,
        "pgid": 4242,
        "process_start_identity": "start-4242",
        "boot_id": "boot-status",
    }
    receipt = build_operator_materialization_receipt(
        operation_command_id=f"ohf-op:start:{attempt_id}",
        operation_kind="start_session",
        attempt_id=attempt_id,
        worker_id="worker-123",
        session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id,
        generation_number=1,
        requested_profile_digest=requested_profile_digest(to_wire(requested)),
        provider_session_id=NATIVE_HANDLE,
        process_identity=process,
        observed_attestation=to_wire(
            ObservedHarnessAttestation(
                served_model="gpt-5.6-sol",
                harness_version="0.147.0",
                harness_binary_digest="a" * 64,
                capabilities=(),
                effective_skills=(),
                effective_mcp=(),
                effective_plugins_or_apps=(),
                sandbox_state="read-only",
                approval_state="never",
                network_state="disabled",
                effective_config_digest="d" * 64,
                auth=AuthRealmFact(
                    worker_id="worker-123",
                    provider="openai-codex",
                ),
                workspace=workspace,
                supports_subagent_capability_ceiling=ObservedTriState.FALSE,
            )
        ),
        process_credentials={
            "process_identity": process,
            "os_principal_name": "fixture-worker",
            "os_principal_uid": 501,
        },
        provider_home_identity={
            "path": "/var/empty/worker-123",
            "device": 1,
            "inode": 2,
            "uid": 501,
            "gid": 20,
            "mode": 0o700,
        },
        created_at="2026-09-03T00:00:00+00:00",
    )
    broker = FakeMaterializationStatusClient(
        {
            "schema_version": MATERIALIZATION_STATUS_SCHEMA,
            "status": "RECEIPT_ONLY_AFTER_RESTART",
            "receipt": receipt.to_dict(),
        }
    )
    remote = RemoteCodexOperatorAdapter(broker, turn_input_loader=lambda _turn: "unused")

    observed = remote.materialization_status(
        operation_id=OperationId(f"ohf-op:start:{attempt_id}"),
        requested=requested,
        epoch=epoch,
        generation=generation,
    )

    assert observed.status == "RECEIPT_ONLY_AFTER_RESTART"
    assert observed.receipt == receipt
    assert len(broker.calls) == 1
    operation, payload, timeout = broker.calls[0]
    assert operation == "ohf-materialization-status"
    assert payload == {
        "operation_id": to_wire(OperationId(f"ohf-op:start:{attempt_id}")),
        "requested": to_wire(requested),
        "epoch": to_wire(epoch),
        "generation": to_wire(generation),
    }
    assert timeout == 30

    drifted = dataclasses.replace(requested, requested_model="gpt-drift")
    mismatched_remote = RemoteCodexOperatorAdapter(
        FakeMaterializationStatusClient(dict(broker.response)),
        turn_input_loader=lambda _turn: "unused",
    )
    with pytest.raises(BrokerProtocolError, match="identity"):
        mismatched_remote.materialization_status(
            operation_id=OperationId(f"ohf-op:start:{attempt_id}"),
            requested=drifted,
            epoch=epoch,
            generation=generation,
        )


def test_remote_materialization_status_refuses_mixed_identities_before_transport() -> None:
    attempt_id = "ATT-MIXED"
    epoch = SessionEpochRef("epoch-mixed", attempt_id, "worker-123", 1)
    generation = ProcessGenerationRef("generation-mixed", "epoch-mixed", 1, "worker-123")
    workspace = WorkspaceIdentity("/tmp/mixed-workspace", "b" * 40, 1, 2, 3, 4)
    requested = RequestedExecutionProfile(
        worker_id="worker-123",
        provider="openai-codex",
        requested_model="gpt-5.6-sol",
        harness_kind="codex-app-server",
        harness_binary_digest="a" * 64,
        harness_version="0.147.0",
        workspace=workspace,
        sandbox_policy="read-only",
        approval_policy="never",
        network_policy="disabled",
        capabilities=CapabilityManifest(),
        native_helper_policy=NativeHelperPolicy.DISABLED,
        authority_policy_hash="c" * 64,
    )

    def assert_refused(**updates: Any) -> None:
        client = FakeMaterializationStatusClient(
            {
                "schema_version": MATERIALIZATION_STATUS_SCHEMA,
                "status": "ABSENT",
                "receipt": None,
            }
        )
        remote = RemoteCodexOperatorAdapter(
            client, turn_input_loader=lambda _turn: "unused"
        )
        with pytest.raises(BrokerProtocolError, match="identity"):
            remote.materialization_status(
                operation_id=updates.get(
                    "operation_id", OperationId(f"ohf-op:start:{attempt_id}")
                ),
                requested=updates.get("requested", requested),
                epoch=epoch,
                generation=updates.get("generation", generation),
                provider_session=updates.get("provider_session"),
            )
        assert client.calls == []

    assert_refused(requested=dataclasses.replace(requested, worker_id="worker-other"))
    assert_refused(
        generation=dataclasses.replace(generation, worker_id="worker-other")
    )
    assert_refused(
        generation=dataclasses.replace(generation, session_epoch_id="epoch-other")
    )
    assert_refused(
        operation_id=OperationId(f"ohf-op:recover-resume:{attempt_id}"),
        generation=dataclasses.replace(generation, generation_number=2),
        provider_session=ProviderSessionHandoff(NATIVE_HANDLE, "worker-other"),
    )


def _real_broker_with_owned_adapter(
    adapter: Any, *, busy: bool = False
) -> broker_module.ExecutiveWorkerBroker:
    broker = object.__new__(broker_module.ExecutiveWorkerBroker)
    broker.operator_harness_armed = False
    broker._state_lock = asyncio.Lock()
    broker._operator_run = broker_module._BrokerOperatorRun(
        adapter=adapter,
        requested=SimpleNamespace(approval_policy="never"),
        epoch=EPOCH,
        generation=GENERATION,
        provider_session_id=NATIVE_HANDLE,
        busy=busy,
    )
    return broker


def _attention_payload() -> dict[str, Any]:
    return {
        "generation": to_wire(GENERATION),
        "attempt_id": ATTEMPT_ID,
        "binding_id": BINDING.binding_id,
        "binding_generation": BINDING.binding_generation,
        "provider_session_id": NATIVE_HANDLE,
        "nudge_id": NUDGE_ID,
        "opaque_ids": list(OPAQUE_IDS),
        "instruction": CODEX_WAKE_INSTRUCTION,
        "completion_timeout_seconds": 3.0,
    }


def test_real_broker_consumer_reaches_real_owned_adapter_once() -> None:
    client = FakeOwnedAppServerClient()
    broker = _real_broker_with_owned_adapter(_owned_adapter(client))

    result = asyncio.run(broker._ohf_deliver_attention(_attention_payload()))

    observation = attention_turn_observation(result["observation"])
    assert observation.accepted is True
    assert observation.delivered is True
    assert [name for name, _payload in client.calls].count("turn/start") == 1


@pytest.mark.parametrize(
    "text",
    (
        f"MASTERMIND_WAKE_ACK {ACK_OID_A}\nMASTERMIND_WAKE_ACK {ACK_OID_A}",
        "MASTERMIND_WAKE_ACK WAKE-malformed",
    ),
    ids=("duplicate", "malformed"),
)
def test_real_broker_treats_completed_invalid_ack_as_inert_after_one_write(
    text: str,
) -> None:
    client = FakeOwnedAppServerClient(completion=_completion_with_text(text))
    broker = _real_broker_with_owned_adapter(_owned_adapter(client))

    result = asyncio.run(broker._ohf_deliver_attention(_attention_payload()))

    observation = attention_turn_observation(result["observation"])
    assert observation.accepted is True
    assert observation.delivered is True
    assert observation.wake_ack_projection is None
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_real_broker_treats_completed_conflicting_text_as_inert_after_one_write() -> None:
    completion = _completion_with_text(f"MASTERMIND_WAKE_ACK {ACK_OID_A}")
    completion["params"]["turn"]["items"][0]["content"] = [
        {
            "type": "output_text",
            "text": f"MASTERMIND_WAKE_ACK {ACK_OID_B}",
        }
    ]
    client = FakeOwnedAppServerClient(completion=completion)
    broker = _real_broker_with_owned_adapter(_owned_adapter(client))

    result = asyncio.run(broker._ohf_deliver_attention(_attention_payload()))

    observation = attention_turn_observation(result["observation"])
    assert observation.accepted is True
    assert observation.delivered is True
    assert observation.wake_ack_projection is None
    assert [name for name, _payload in client.calls].count("turn/start") == 1


@pytest.mark.parametrize(
    "status",
    (_MISSING_STATUS, "unknown", "inProgress"),
    ids=("missing", "unknown", "nonterminal"),
)
def test_real_broker_preserves_effect_unknown_for_unrecognized_status(
    status: object,
) -> None:
    client = FakeOwnedAppServerClient(
        completion=_completion_with_text("provider result", status=status)
    )
    broker = _real_broker_with_owned_adapter(_owned_adapter(client))

    with pytest.raises(BrokerEffectUnknownError):
        asyncio.run(broker._ohf_deliver_attention(_attention_payload()))

    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_real_broker_busy_refuses_before_provider_io() -> None:
    client = FakeOwnedAppServerClient()
    broker = _real_broker_with_owned_adapter(_owned_adapter(client), busy=True)

    with pytest.raises(BrokerPreSubmitError):
        asyncio.run(broker._ohf_deliver_attention(_attention_payload()))

    assert client.calls == []


def test_real_broker_attempt_drift_refuses_before_provider_io() -> None:
    client = FakeOwnedAppServerClient()
    broker = _real_broker_with_owned_adapter(_owned_adapter(client))
    payload = _attention_payload()
    payload["attempt_id"] = "attempt-foreign"

    with pytest.raises(BrokerPreSubmitError):
        asyncio.run(broker._ohf_deliver_attention(payload))

    assert client.calls == []


def test_real_broker_preserves_effect_unknown_after_one_provider_write() -> None:
    client = FakeOwnedAppServerClient(fail_request=True)
    broker = _real_broker_with_owned_adapter(_owned_adapter(client))

    with pytest.raises(BrokerEffectUnknownError):
        asyncio.run(broker._ohf_deliver_attention(_attention_payload()))

    assert [name for name, _payload in client.calls].count("turn/start") == 1


@dataclass
class FakeUnclassifiedPostSubmitAttentionAdapter:
    provider_writes: int = 0

    def deliver_attention(self, **_kwargs: Any) -> AttentionTurnObservation:
        self.provider_writes += 1
        raise RuntimeError("unexpected failure after provider submission")


def test_real_broker_fails_closed_on_unclassified_attention_exception() -> None:
    adapter = FakeUnclassifiedPostSubmitAttentionAdapter()
    broker = _real_broker_with_owned_adapter(adapter)

    with pytest.raises(BrokerEffectUnknownError):
        asyncio.run(broker._ohf_deliver_attention(_attention_payload()))

    assert adapter.provider_writes == 1


@dataclass
class FakeRemoteAttentionAdapter:
    response: AttentionTurnObservation | None = None
    error: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def deliver_attention(self, **kwargs: Any) -> AttentionTurnObservation:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def _deliver_via_wake_client(
    fake: FakeRemoteAttentionAdapter,
    *,
    opaque_ids: tuple[str, ...] = OPAQUE_IDS,
):
    client = CodexCurrentWriterWakeClient(
        operator_adapter=fake,
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        runtime_binding=BINDING,
        completion_timeout_seconds=3.0,
    )
    return asyncio.run(
        client.deliver_wake(
            native_handle=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=opaque_ids,
            instruction=CODEX_WAKE_INSTRUCTION,
        )
    )


def test_wake_client_delegates_to_bound_generation_and_returns_provider_observation() -> None:
    fake = FakeRemoteAttentionAdapter(
        response=AttentionTurnObservation(
            process_generation_id=GENERATION.process_generation_id,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            provider_native_turn_id="turn-wake-456",
            accepted=True,
            delivered=True,
        )
    )

    observation = _deliver_via_wake_client(fake)

    assert observation.native_handle == NATIVE_HANDLE
    assert observation.nudge_id == NUDGE_ID
    assert observation.accepted is True
    assert observation.delivered is True
    assert len(fake.calls) == 1
    assert fake.calls[0]["generation"] == GENERATION
    assert fake.calls[0]["attempt_id"] == ATTEMPT_ID
    assert fake.calls[0]["provider_session_id"] == NATIVE_HANDLE
    assert fake.calls[0]["binding_id"] == BINDING.binding_id
    assert fake.calls[0]["binding_generation"] == BINDING.binding_generation


@pytest.mark.parametrize("status", ("failed", "interrupted"))
def test_wake_client_preserves_known_terminal_acceptance_without_delivery(
    status: str,
) -> None:
    provider_client = FakeOwnedAppServerClient(
        completion=_completion_with_text(
            f"MASTERMIND_WAKE_ACK {ACK_OID_A}",
            status=status,
        )
    )
    wake_client = CodexCurrentWriterWakeClient(
        operator_adapter=_owned_adapter(provider_client),
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        runtime_binding=BINDING,
        completion_timeout_seconds=3.0,
    )

    observation = asyncio.run(
        wake_client.deliver_wake(
            native_handle=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=ACK_OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
        )
    )

    assert observation.accepted is True
    assert observation.delivered is False
    assert observation.target_ack_projection is None
    assert [name for name, _payload in provider_client.calls].count("turn/start") == 1


def _worker_projection(**overrides: object) -> WorkerLocalWakeAckProjection:
    values: dict[str, object] = {
        "target_attempt_id": ATTEMPT_ID,
        "process_generation_id": GENERATION.process_generation_id,
        "binding_id": BINDING.binding_id,
        "binding_generation": BINDING.binding_generation,
        "provider_session_id": NATIVE_HANDLE,
        "provider_native_turn_id": "turn-wake-456",
        "nudge_id": NUDGE_ID,
        "obligation_ids": tuple(sorted((ACK_OID_A, ACK_OID_B))),
        "terminal_ack_trailer": True,
    }
    values.update(overrides)
    return WorkerLocalWakeAckProjection(**values)


def test_wake_client_reconciles_late_exact_completion_without_second_turn_start() -> None:
    """Catches the current-writer client lacking an existing-reconcile projection path."""

    provider_client = FakeOwnedAppServerClient(completion_timeout=True)
    wake_client = CodexCurrentWriterWakeClient(
        operator_adapter=_owned_adapter(provider_client),
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        runtime_binding=BINDING,
        completion_timeout_seconds=3.0,
    )

    accepted = asyncio.run(
        wake_client.deliver_wake(
            native_handle=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=ACK_OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
        )
    )
    assert accepted.accepted is True and accepted.delivered is False
    provider_client.queued_notifications.append(
        _completion_with_text(
            f"provider result\nMASTERMIND_WAKE_ACK {ACK_OID_A}\n"
            f"MASTERMIND_WAKE_ACK {ACK_OID_B}",
            status="completed",
        )
    )

    late = asyncio.run(
        wake_client.reconcile_wake(
            native_handle=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=ACK_OPAQUE_IDS,
        )
    )

    assert late.accepted is True and late.delivered is True
    assert late.target_ack_projection == TrustedWorkerWakeAckProjection(
        **dataclasses.asdict(_worker_projection())
    )
    assert [name for name, _payload in provider_client.calls].count("turn/start") == 1


def test_wake_client_promotes_only_exact_outer_and_submitted_worker_projection() -> None:
    worker_projection = _worker_projection()
    fake = FakeRemoteAttentionAdapter(
        response=AttentionTurnObservation(
            process_generation_id=GENERATION.process_generation_id,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            provider_native_turn_id="turn-wake-456",
            accepted=True,
            delivered=True,
            wake_ack_projection=worker_projection,
        )
    )

    observation = _deliver_via_wake_client(fake, opaque_ids=ACK_OPAQUE_IDS)

    assert observation.target_ack_projection == TrustedWorkerWakeAckProjection(
        **dataclasses.asdict(worker_projection)
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"target_attempt_id": "attempt-foreign"},
        {"binding_id": "bind-ffffffffffffffffffffffffffffffffffffffff"},
        {"binding_generation": BINDING.binding_generation + 1},
        {"obligation_ids": (ACK_OID_A,)},
    ],
)
def test_wake_client_refuses_nested_projection_outside_exact_current_submission(
    overrides: dict[str, object],
) -> None:
    fake = FakeRemoteAttentionAdapter(
        response=AttentionTurnObservation(
            process_generation_id=GENERATION.process_generation_id,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            provider_native_turn_id="turn-wake-456",
            accepted=True,
            delivered=True,
            wake_ack_projection=_worker_projection(**overrides),
        )
    )

    with pytest.raises(RuntimeError, match="ACK projection"):
        _deliver_via_wake_client(fake, opaque_ids=ACK_OPAQUE_IDS)


def test_wake_client_refuses_runtime_binding_generation_mispairing() -> None:
    stale = RuntimeBinding(
        session_alias=BINDING.session_alias,
        binding_id=BINDING.binding_id,
        binding_generation=BINDING.binding_generation + 1,
        native_handle=BINDING.native_handle,
        reasoning_surface=BINDING.reasoning_surface,
    )

    with pytest.raises(ValueError, match="binding generation"):
        CodexCurrentWriterWakeClient(
            operator_adapter=FakeRemoteAttentionAdapter(),
            generation=GENERATION,
            attempt_id=ATTEMPT_ID,
            runtime_binding=stale,
        )


def test_broker_pre_submit_refusal_maps_to_wake_target_unavailable() -> None:
    fake = FakeRemoteAttentionAdapter(
        error=RemoteBrokerError("BrokerPreSubmitError", "pre-submit refusal")
    )

    with pytest.raises(WakePreSubmitError) as error:
        _deliver_via_wake_client(fake)

    assert error.value.reason_code == "target_unavailable"


def test_final_guard_runs_in_worker_thread_immediately_before_provider_io() -> None:
    order: list[tuple[str, int]] = []

    class Adapter(FakeRemoteAttentionAdapter):
        def deliver_attention(self, **kwargs):
            order.append(("provider", threading.get_ident()))
            return super().deliver_attention(**kwargs)

    fake = Adapter(
        response=AttentionTurnObservation(
            process_generation_id=GENERATION.process_generation_id,
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            provider_native_turn_id="turn-wake-456",
            accepted=True,
            delivered=True,
        )
    )
    client = CodexCurrentWriterWakeClient(
        operator_adapter=fake,
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        runtime_binding=BINDING,
        pre_submit_guard=lambda: order.append(("guard", threading.get_ident())),
    )
    caller_thread = threading.get_ident()

    asyncio.run(
        client.deliver_wake(
            native_handle=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
        )
    )

    assert [name for name, _thread in order] == ["guard", "provider"]
    assert order[0][1] == order[1][1]
    assert order[0][1] != caller_thread


def test_final_guard_refusal_is_typed_and_reconcile_never_calls_guard() -> None:
    calls = 0

    def refuse() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("binding moved")

    fake = FakeRemoteAttentionAdapter()
    client = CodexCurrentWriterWakeClient(
        operator_adapter=fake,
        generation=GENERATION,
        attempt_id=ATTEMPT_ID,
        runtime_binding=BINDING,
        pre_submit_guard=refuse,
    )
    with pytest.raises(WakePreSubmitError) as error:
        asyncio.run(
            client.deliver_wake(
                native_handle=NATIVE_HANDLE,
                nudge_id=NUDGE_ID,
                opaque_ids=OPAQUE_IDS,
                instruction=CODEX_WAKE_INSTRUCTION,
            )
        )
    assert error.value.reason_code == "target_unavailable"
    assert fake.calls == []
    with pytest.raises(Exception):
        asyncio.run(
            client.reconcile_wake(
                native_handle=NATIVE_HANDLE,
                nudge_id=NUDGE_ID,
                opaque_ids=OPAQUE_IDS,
            )
        )
    assert calls == 1


def test_broker_effect_unknown_never_maps_to_safe_refusal() -> None:
    remote_error = RemoteBrokerError("BrokerEffectUnknownError", "provider write uncertain")
    fake = FakeRemoteAttentionAdapter(error=remote_error)

    with pytest.raises(RemoteBrokerError) as error:
        _deliver_via_wake_client(fake)

    assert error.value.code == "BrokerEffectUnknownError"


def test_w3a_module_contains_no_second_app_server_or_cold_resume_path() -> None:
    source = inspect.getsource(wake_rpc)
    assert "AppServerClient" not in source
    assert "client.start" not in source
    assert '"thread/resume"' not in source
    assert '"thread/start"' not in source
