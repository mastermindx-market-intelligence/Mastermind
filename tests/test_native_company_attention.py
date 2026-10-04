"""Company evidence from the existing attention queue, without consumption."""
import threading

import pytest

from control_plane.native_company_receipt import project_company_read
from control_plane.operator_harness_contract import ATTENTION_TURN_INSTRUCTION
from scripts.ohf.laboratory import AppServerClient
from tests.test_codex_app_server_wake_rpc import (
    FakeOwnedAppServerClient, _owned_adapter, GENERATION, ATTEMPT_ID, BINDING,
    NATIVE_HANDLE, NUDGE_ID, OPAQUE_IDS,
)
from tests.test_native_company_receipt_adapter import _subject
from tests.test_native_company_receipt import SERVER, make_params, make_item


class OrderedClient(FakeOwnedAppServerClient):
    """Use the production queue-prefix owner with an in-memory notification queue."""
    def __init__(self, notifications):
        super().__init__()
        self.notifications = list(notifications)
        self._notification_condition = threading.Condition()
        self._transport_closed = False

    _wait_notification_prefix = AppServerClient._wait_notification_prefix

    def wait_notifications_through(self, method, *, timeout=15.0, predicate=None):
        self.calls.append(("prefix:" + method, timeout))
        return AppServerClient.wait_notifications_through(self, method, timeout=timeout, predicate=predicate)


def item(**changes):
    params = make_params()
    params.update(threadId=NATIVE_HANDLE, turnId="turn-wake-456")
    params.update(changes)
    return {"method": "item/completed", "params": params}


def completion(status="completed", **changes):
    params = {"threadId": NATIVE_HANDLE, "turn": {"id": "turn-wake-456", "status": status}}
    params.update(changes)
    return {"method": "turn/completed", "params": params}


def subject(notifications):
    client = OrderedClient(notifications)
    adapter = _owned_adapter(client)
    state = adapter._generations[GENERATION.process_generation_id]
    _, admitted, _ = _subject()
    state.requested.capabilities = admitted.requested.capabilities
    state.attestation.capabilities = admitted.attestation.capabilities
    state.attestation.effective_mcp = admitted.attestation.effective_mcp
    return adapter, state, client


def deliver(adapter):
    return adapter.deliver_attention(
        generation=GENERATION, attempt_id=ATTEMPT_ID,
        binding_id=BINDING.binding_id, binding_generation=BINDING.binding_generation,
        provider_session_id=NATIVE_HANDLE, nudge_id=NUDGE_ID,
        opaque_ids=OPAQUE_IDS, instruction=ATTENTION_TURN_INSTRUCTION,
        completion_timeout_seconds=0.1,
    )


def test_attention_read_uses_ordered_prefix_and_leaves_late_frames_queued():
    before, late = item(), item(completedAtMs=5678)
    adapter, state, client = subject([before, completion(), late])
    observation = deliver(adapter)
    receipt = observation.company_read_projection
    assert observation.delivered and receipt is not None
    expected = project_company_read(before["params"], server_name=SERVER,
                                    thread_id=NATIVE_HANDLE, turn_id="turn-wake-456")
    assert receipt.result_sha256 == expected["result_sha256"]
    assert receipt.native_item_sha256 == expected["native_item_sha256"]
    assert receipt.target_attempt_id == ATTEMPT_ID
    assert receipt.binding_id == BINDING.binding_id
    assert receipt.binding_generation == BINDING.binding_generation
    assert receipt.provider_native_turn_id == "turn-wake-456"
    assert client.notifications == [late]
    assert state.events == [] and state.turns == {}
    assert observation.wake_ack_projection is None
    assert sum(method == "turn/start" for method, _ in client.calls) == 1
    assert "company_read_projection" not in repr(observation)


@pytest.mark.parametrize("notifications", [
    [completion(), item()],
    [item(threadId="different-thread"), completion()],
    [item(turnId="different-turn"), completion()],
    [item(item=make_item(server="other-server")), completion()],
    [item(), item(), completion()],
    [item(), completion("failed")],
    [item(), completion("interrupted")],
    [item()] * 4097 + [completion()],
])
def test_attention_never_selects_late_foreign_duplicate_or_failed_read(notifications):
    adapter, _, _ = subject(notifications)
    assert deliver(adapter).company_read_projection is None


def test_attention_requires_exact_requested_and_observed_company_capability():
    adapter, state, client = subject([item(), completion()])
    state.attestation.capabilities = ()
    observation = deliver(adapter)
    assert observation.company_read_projection is None
    assert not any(name.startswith("prefix:") for name, _ in client.calls)


def test_late_exact_attention_completion_reuses_original_prefix_without_resubmission():
    adapter, state, client = subject([item()])
    first = deliver(adapter)
    assert first.accepted and not first.delivered and first.company_read_projection is None
    assert state.attention_inflight and len(client.notifications) == 1
    late = item(completedAtMs=123456)
    client.notifications.extend([completion(), late])
    reconciled = adapter._reconcile_late_attention_completion(state)
    assert reconciled.delivered and reconciled.company_read_projection is not None
    assert client.notifications == [late]
    assert sum(method == "turn/start" for method, _ in client.calls) == 1
    assert not state.attention_inflight
    assert adapter._reconcile_late_attention_completion(state) is None


def test_foreign_completion_does_not_publish_company_projection():
    adapter, state, client = subject([item(), completion(threadId="foreign")])
    first = deliver(adapter)
    assert first.accepted and not first.delivered
    assert state.attention_inflight and len(client.notifications) == 2
    client.notifications.append(completion())
    reconciled = adapter._reconcile_late_attention_completion(state)
    assert reconciled.delivered and reconciled.company_read_projection is not None
    assert sum(method == "turn/start" for method, _ in client.calls) == 1


def test_conflicting_inner_thread_completion_does_not_publish_company_projection():
    conflicting = completion()
    conflicting["params"]["turn"]["threadId"] = "foreign-inner-thread"
    adapter, state, client = subject([item(), conflicting])
    first = deliver(adapter)
    assert first.accepted and not first.delivered
    assert first.company_read_projection is None
    assert state.attention_inflight and len(client.notifications) == 2
    client.notifications.append(completion())
    reconciled = adapter._reconcile_late_attention_completion(state)
    assert reconciled.delivered and reconciled.company_read_projection is not None
    assert sum(method == "turn/start" for method, _ in client.calls) == 1


def test_exact_attention_completion_keeps_receipt_before_foreign_completion():
    adapter, _, client = subject([item(), completion(threadId="foreign"), completion(), item()])
    observation = deliver(adapter)
    assert observation.delivered and observation.company_read_projection is not None
    assert len(client.notifications) == 1
