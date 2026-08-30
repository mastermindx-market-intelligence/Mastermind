from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import pytest

from control_plane import codex_operator_adapter as codex_adapter
from control_plane import executive_worker_broker as broker_module
from control_plane.executive_worker_broker import RemoteBrokerError
from control_plane.operator_harness_contract import (
    AttentionTurnObservation,
    ProcessGenerationRef,
    ProcessIdentityObservation,
    ProviderWriterState,
)
from control_plane.operator_harness_wire import to_wire
from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
from control_plane.wake_dispatcher import WakePreSubmitError
from integrations.executive_wake.codex_app_server import CODEX_WAKE_INSTRUCTION
from integrations.executive_wake import codex_app_server_rpc as wake_rpc
from integrations.executive_wake.codex_app_server_rpc import CodexCurrentWriterWakeClient
from scripts.ohf.laboratory import JsonRpcError


NATIVE_HANDLE = "019cafe0-1111-7222-8333-abcdefabcdef"
NUDGE_ID = "nudge-123"
OPAQUE_IDS = ("WAKE-123", "WAKE-123:ATTEMPT:1")
GENERATION = ProcessGenerationRef(
    process_generation_id="generation-123",
    session_epoch_id="epoch-123",
    generation_number=7,
    worker_id="worker-123",
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
    calls: list[tuple[str, object]] = field(default_factory=list)

    def alive(self) -> bool:
        self.calls.append(("alive", None))
        return True

    def request(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        self.calls.append((method, dict(params or {})))
        if method != "turn/start":
            raise AssertionError(f"second-writer/cold-resume method attempted: {method}")
        if self.fail_request:
            raise RuntimeError("turn/start transport lost")
        return {"turn": {"id": self.turn_id}}

    def wait_notification(self, method: str, *, timeout: float = 15.0) -> dict[str, Any]:
        self.calls.append((f"wait:{method}", timeout))
        if self.completion_timeout:
            raise JsonRpcError(f"timeout waiting for notification {method}")
        if self.completion is not None:
            return dict(self.completion)
        return {
            "method": "turn/completed",
            "params": {
                "threadId": NATIVE_HANDLE,
                "turn": {"id": self.turn_id, "status": "completed"},
            },
        }


def _owned_adapter(
    client: FakeOwnedAppServerClient,
    *,
    provider_session_id: str = NATIVE_HANDLE,
    observed_process: ProcessIdentityObservation = PROCESS,
):
    adapter = object.__new__(codex_adapter.CodexOperatorAdapter)
    adapter.worker_id = GENERATION.worker_id
    adapter.workspace_root = Path("/tmp/mastermind-w3a-owned-workspace")
    adapter.process_identity_observer = lambda _pid: observed_process
    adapter._generations = {
        GENERATION.process_generation_id: SimpleNamespace(
            generation=GENERATION,
            provider_session_id=provider_session_id,
            writer_state=ProviderWriterState.HELD,
            client=client,
            process=PROCESS,
            requested=SimpleNamespace(approval_policy="never"),
        )
    }
    return adapter


def test_attention_observation_is_closed_and_delivery_requires_acceptance() -> None:
    observation = AttentionTurnObservation(
        process_generation_id=GENERATION.process_generation_id,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        provider_native_turn_id="turn-wake-456",
        accepted=True,
        delivered=True,
    )
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


def test_worker_local_attention_reuses_exact_owned_generation_without_start_or_resume() -> None:
    client = FakeOwnedAppServerClient()
    adapter = _owned_adapter(client)

    observation = adapter.deliver_attention(
        generation=GENERATION,
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
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.effect_unknown is False
    assert error.value.failure_class.value == "ACTIVE_WRITER_CONFLICT"
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
            provider_session_id=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
            instruction=CODEX_WAKE_INSTRUCTION,
            completion_timeout_seconds=3.0,
        )

    assert error.value.effect_unknown is True
    assert [name for name, _payload in client.calls].count("turn/start") == 1


def test_completion_timeout_is_accepted_not_delivered_on_same_owned_writer() -> None:
    client = FakeOwnedAppServerClient(completion_timeout=True)
    adapter = _owned_adapter(client)

    observation = adapter.deliver_attention(
        generation=GENERATION,
        provider_session_id=NATIVE_HANDLE,
        nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS,
        instruction=CODEX_WAKE_INSTRUCTION,
        completion_timeout_seconds=3.0,
    )

    assert observation.accepted is True
    assert observation.delivered is False
    assert observation.provider_native_turn_id == "turn-wake-456"


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
    assert payload["provider_session_id"] == NATIVE_HANDLE
    assert payload["nudge_id"] == NUDGE_ID
    assert payload["opaque_ids"] == list(OPAQUE_IDS)
    assert payload["instruction"] == CODEX_WAKE_INSTRUCTION
    assert payload["completion_timeout_seconds"] == 3.0
    assert timeout is not None


def test_broker_surface_has_dedicated_attention_operation_and_typed_effect_boundary() -> None:
    source = inspect.getsource(broker_module)
    assert '"ohf-deliver-attention"' in source
    assert "def _ohf_deliver_attention" in source
    assert "BrokerPreSubmitError" in source
    assert "BrokerEffectUnknownError" in source


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


def _deliver_via_wake_client(fake: FakeRemoteAttentionAdapter):
    client = CodexCurrentWriterWakeClient(
        operator_adapter=fake,
        generation=GENERATION,
        completion_timeout_seconds=3.0,
    )
    return asyncio.run(
        client.deliver_wake(
            native_handle=NATIVE_HANDLE,
            nudge_id=NUDGE_ID,
            opaque_ids=OPAQUE_IDS,
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
    assert fake.calls[0]["provider_session_id"] == NATIVE_HANDLE


def test_broker_pre_submit_refusal_maps_to_wake_target_unavailable() -> None:
    fake = FakeRemoteAttentionAdapter(
        error=RemoteBrokerError("BrokerPreSubmitError", "pre-submit refusal")
    )

    with pytest.raises(WakePreSubmitError) as error:
        _deliver_via_wake_client(fake)

    assert error.value.reason_code == "target_unavailable"


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
