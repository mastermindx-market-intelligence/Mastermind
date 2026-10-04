"""Same current-writer response evidence, closed wire and pre-submit falsifiers."""
import dataclasses
import json

import pytest

from control_plane.codex_operator_adapter import CodexAdapterError
from control_plane.operator_harness_contract import ATTENTION_TURN_INSTRUCTION, AttentionContinuationInput
from control_plane.operator_harness_wire import (
    attention_continuation_input, attention_turn_observation, to_wire, OperatorHarnessWireError)
from tests.test_codex_app_server_wake_rpc import (
    FakeOwnedAppServerClient, _owned_adapter, _completion_with_text,
    GENERATION, ATTEMPT_ID, BINDING, NATIVE_HANDLE, NUDGE_ID, ACK_OID_A)


def source(**changes):
    args = dict(obligation_id=ACK_OID_A, operation_key="continue-exact-001",
                request_message_key="asd-request-one", physical_source_sha256="b"*64,
                continuation_text="Read the bounded finding.", stop_condition="Return one finding.")
    args.update(changes)
    return AttentionContinuationInput.create(**args)


def response_text(value, **changes):
    response = {k: getattr(value, k) for k in (
        "obligation_id", "operation_key", "request_message_key",
        "physical_source_sha256", "immutable_input_sha256")}
    response.update(text="The bounded finding is confirmed.", next_step="Continue the parent task.")
    response.update(changes)
    return "MASTERMIND_CONTINUE_RESPONSE " + json.dumps(
        response, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def deliver(adapter, value, *, opaque=None):
    return adapter.deliver_attention(
        generation=GENERATION, attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id, binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE, nudge_id=NUDGE_ID,
        opaque_ids=opaque or (value.obligation_id, value.obligation_id + ":A1"),
        instruction=ATTENTION_TURN_INSTRUCTION, completion_timeout_seconds=0.1,
        continuation_input=value)


def trailer(value, **changes):
    return response_text(value, **changes) + "\nMASTERMIND_WAKE_ACK " + value.obligation_id


def test_same_turn_produces_closed_response_and_preserves_fixed_instruction():
    value = source()
    client = FakeOwnedAppServerClient(completion=_completion_with_text(trailer(value)))
    observation = deliver(_owned_adapter(client), value)
    projection = observation.continuation_response_projection
    assert projection and projection.immutable_input_sha256 == value.immutable_input_sha256
    assert projection.provider_session_id == NATIVE_HANDLE
    assert observation.wake_ack_projection.obligation_ids == (value.obligation_id,)
    assert attention_turn_observation(to_wire(observation)) == observation
    assert attention_continuation_input(to_wire(value)) == value
    starts = [p for m, p in client.calls if m == "turn/start"]
    assert len(starts) == 1
    assert starts[0]["input"][0]["text"].startswith(ATTENTION_TURN_INSTRUCTION)
    assert value.continuation_text in starts[0]["input"][0]["text"]
    assert value.continuation_text not in repr(value)
    assert projection.text not in repr(observation)
    wire = to_wire(observation)
    wire["continuation_response_projection"]["extra"] = "refuse"
    with pytest.raises(OperatorHarnessWireError):
        attention_turn_observation(wire)


@pytest.mark.parametrize("change", [
    {"operation_key": "other"}, {"request_message_key": "other"},
    {"immutable_input_sha256": "c"*64}, {"physical_source_sha256": "c"*64},
    {"text": ""}, {"text": "x"*701}, {"text": "bad\u0000value"},
    {"next_step": True}, {"extra": "refuse"}, {"text": "/Users/private/secret.txt"},
])
def test_foreign_or_unsafe_reply_withholds_projection_without_losing_delivery(change):
    value = source()
    client = FakeOwnedAppServerClient(completion=_completion_with_text(trailer(value, **change)))
    observed = deliver(_owned_adapter(client), value)
    assert observed.delivered and observed.continuation_response_projection is None


@pytest.mark.parametrize("mutate", [
    lambda text: "```\n"+text+"\n```",
    lambda text: text.replace("\nMASTERMIND_WAKE_ACK ", "\nintervening\nMASTERMIND_WAKE_ACK "),
    lambda text: text.replace('"next_step":', '"next_step" :'),
    lambda text: text+"\ntrailing text",
    lambda text: text.split("\n")[0]+"\n"+text,
    lambda text: text.replace(ACK_OID_A, "WAKE-"+"c"*32),
])
def test_only_unique_unfenced_canonical_response_next_to_exact_ack_is_reduced(mutate):
    value = source()
    client = FakeOwnedAppServerClient(completion=_completion_with_text(mutate(trailer(value))))
    assert deliver(_owned_adapter(client), value).continuation_response_projection is None


@pytest.mark.parametrize("opaque", [
    ("other-id", ACK_OID_A), (ACK_OID_A, "other-id"),
    (ACK_OID_A+":A1", ACK_OID_A), (ACK_OID_A, "WAKE-"+"b"*32+":A1"),
])
def test_misbound_delivery_ids_refuse_before_provider(opaque):
    value = source()
    client = FakeOwnedAppServerClient()
    with pytest.raises(CodexAdapterError):
        deliver(_owned_adapter(client), value, opaque=opaque)
    assert not any(m == "turn/start" for m, _ in client.calls)


def test_late_response_reuses_the_original_turn_and_pending_input():
    value = source()
    client = FakeOwnedAppServerClient(completion_timeout=True)
    adapter = _owned_adapter(client)
    assert not deliver(adapter, value).delivered
    client.completion_timeout = False
    client.completion = _completion_with_text(trailer(value))
    state = adapter._generations[GENERATION.process_generation_id]
    observed = adapter._reconcile_late_attention_completion(state)
    assert observed.continuation_response_projection is not None
    assert sum(m == "turn/start" for m, _ in client.calls) == 1


@pytest.mark.parametrize("change", [
    {"continuation_text": ""}, {"stop_condition": "x"*701},
    {"obligation_id": "WAKE-invalid"}, {"physical_source_sha256": "X"*64},
])
def test_invalid_input_is_not_constructed(change):
    with pytest.raises(ValueError):
        source(**change)


def test_input_digest_and_wire_cannot_be_reauthored():
    value = source()
    with pytest.raises(ValueError):
        dataclasses.replace(value, continuation_text="changed")
    wire = to_wire(value)
    wire["extra"] = "unbound"
    with pytest.raises(OperatorHarnessWireError):
        attention_continuation_input(wire)


def test_remote_wire_real_broker_and_owned_adapter_share_one_response_turn():
    import asyncio
    from control_plane.remote_codex_operator_adapter import RemoteCodexOperatorAdapter
    from tests.test_codex_app_server_wake_rpc import _real_broker_with_owned_adapter
    value = source()
    client = FakeOwnedAppServerClient(completion=_completion_with_text(trailer(value)))
    broker = _real_broker_with_owned_adapter(_owned_adapter(client))
    class Bridge:
        calls = 0
        def request_sync(self, operation, payload, **kwargs):
            assert operation == "ohf-deliver-attention"
            self.calls += 1
            return asyncio.run(broker._ohf_deliver_attention(payload))
    bridge = Bridge()
    remote = RemoteCodexOperatorAdapter(bridge, turn_input_loader=lambda _: "unused")
    observed = deliver(remote, value)
    assert bridge.calls == 1 and observed.continuation_response_projection is not None
    assert sum(m == "turn/start" for m, _ in client.calls) == 1


@pytest.mark.parametrize("mutate", [
    lambda payload: payload["continuation_input"].update(extra="refuse"),
    lambda payload: payload["continuation_input"].update(immutable_input_sha256="f"*64),
])
def test_broker_rejects_malformed_continuation_before_provider(mutate):
    import asyncio
    from control_plane.executive_worker_broker import BrokerPreSubmitError
    from tests.test_codex_app_server_wake_rpc import _real_broker_with_owned_adapter, _attention_payload
    value = source()
    client = FakeOwnedAppServerClient()
    broker = _real_broker_with_owned_adapter(_owned_adapter(client))
    payload = _attention_payload()
    payload["continuation_input"] = to_wire(value)
    payload["opaque_ids"] = [value.obligation_id, value.obligation_id + ":A1"]
    mutate(payload)
    with pytest.raises(BrokerPreSubmitError):
        asyncio.run(broker._ohf_deliver_attention(payload))
    assert client.calls == []
