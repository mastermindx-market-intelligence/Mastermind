"""Pluggable result-return delivery contract tests (plan V3 §8a).

The registry routes by origin kind and refuses unknown kinds with a
typed error — never a silent default, never a silent drop.  The Hermes
wrapper passes records through verbatim.  The wiring resolves the origin
from the admission requester block: a registered carrier kind claims its
own transport; everything else rides the default Hermes path exactly as
today.  Covers the L1B3-4 fix: attempt.idempotency_key prefers the
binding's per-attempt ``operation_key`` over the job-level command id.
"""
from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from typing import Any

import pytest

from control_plane.execution_return_wiring import (
    EXECUTION_RETURN_DELIVERY_EVENT,
    ExecutionReturnWiring,
)
from control_plane.result_delivery import (
    HERMES_ORIGIN_KIND,
    HermesResultDeliveryTransport,
    OriginRef,
    ResultDeliveryRegistry,
    UnknownOriginKindError,
)

NAMESPACE = "t3-mastermind//principal-e2e"


class RecordingDeliverer:
    """A Hermes-shaped deliverer: async deliver(record) -> receipt."""

    def __init__(self) -> None:
        self.records: list[Any] = []

    async def deliver(self, record: Any) -> dict[str, Any]:
        self.records.append(record)
        return {"state": "delivered", "transport_ref": "native-ref-1"}


class RecordingTransport:
    """A second transport for a NEW origin kind (the pluggable shape)."""

    def __init__(self) -> None:
        self.calls: list[tuple[OriginRef, Any]] = []

    async def deliver(self, origin: OriginRef, payload: Any) -> dict[str, Any]:
        self.calls.append((origin, payload))
        return {"state": "delivered", "transport_ref": "issue-returned-1"}


class FakeEvent:
    def __init__(self, event_type: str, payload: dict, attempt_id: str = "") -> None:
        self.event_type, self.payload, self.attempt_id = event_type, payload, attempt_id


class FakeStore:
    """The minimal event-log surface the wiring seam reads."""

    def __init__(self, events: list[FakeEvent]) -> None:
        self.events, self.appended = events, []

    def list_events(self, job_id=None, attempt_id=None, **_) -> list[FakeEvent]:
        return [e for e in self.events
                if attempt_id is None or e.attempt_id == attempt_id]

    def get_event_by_command_id(self, command_id: str) -> None:
        return None

    @contextlib.contextmanager
    def transaction(self):
        yield None

    def append_event(self, _connection, **kwargs) -> None:
        self.appended.append(kwargs)


class FakeAdapter:
    """Attests the launch namespace; no ledgered result reference."""

    def launch_receipt(self, run_id: str) -> Any:
        return SimpleNamespace(request_namespace=NAMESPACE)

    def result_ledger_entry(self, run_id: str) -> None:
        return None


class FakeJob:
    job_id, current_attempt_id, root_job_id = "JOB-1", "ATT-1", "ROOT-1"
    branch, result = None, {"summary": "pluggable return", "artifacts": []}


def _wiring_store(carrier_kind: str | None, *, operation_key: str | None = "op-att-1",
                  command_id: str | None = "child-request:job-1") -> FakeStore:
    requester: dict[str, Any] = {
        "teammate_id": "hermes-tm-42", "conversation_id": "conv-7",
        "project_id": "proj-mm",
    }
    if carrier_kind is not None:
        requester["carrier_kind"] = carrier_kind
    binding: dict[str, Any] = {"runtime_kind": "t3-native"}
    if operation_key is not None:
        binding["operation_key"] = operation_key
    child_request: dict[str, Any] = {"root_ref": "root-company-1"}
    if command_id is not None:
        child_request["command_id"] = command_id
    return FakeStore([
        FakeEvent("JOB_CLAIMED", {"execution_binding": binding}, attempt_id="ATT-1"),
        FakeEvent("JOB_CREATED", {"provenance": {
            "original_requester": requester, "child_request": child_request}}),
    ])


def _deliver(store: FakeStore, **kwargs: Any) -> None:
    ExecutionReturnWiring(
        store=store, t3_adapter=FakeAdapter(), **kwargs
    ).deliver(job=FakeJob(), status="completed")


def _receipt(store: FakeStore) -> dict:
    rows = [a for a in store.appended
            if a["event_type"] == EXECUTION_RETURN_DELIVERY_EVENT]
    assert len(rows) == 1, "exactly one receipt event per attempt"
    return rows[0]["payload"]


# --- 1. the registry contract ---------------------------------------------


def test_registry_routes_registered_kind_and_refuses_unknown_kinds():
    registry, transport = ResultDeliveryRegistry(), RecordingTransport()
    hermes = RecordingDeliverer()
    registry.register(HERMES_ORIGIN_KIND, HermesResultDeliveryTransport(hermes))
    registry.register("paperclip_issue", transport)
    origin = OriginRef("paperclip_issue", {"issue_id": "PAPER-9"})
    receipt = asyncio.run(registry.lookup("paperclip_issue").deliver(
        origin, {"schema": "mastermind.execution_return/v1"}))
    assert receipt["state"] == "delivered"
    assert transport.calls[0][0] is origin
    assert transport.calls[0][1]["schema"] == "mastermind.execution_return/v1"
    # UNKNOWN kind: typed refusal; the registered Hermes transport is NOT
    # silently applied as a default, and nothing is dropped.
    with pytest.raises(UnknownOriginKindError) as caught:
        registry.lookup("slack_thread")
    assert caught.value.kind == "slack_thread"
    assert hermes.records == []


def test_hermes_wrapper_passes_the_record_through_verbatim():
    deliverer = RecordingDeliverer()
    wrapper = HermesResultDeliveryTransport(deliverer)
    record = {"schema": "mastermind.execution_return/v1", "digest": "0" * 64}
    receipt = asyncio.run(wrapper.deliver(OriginRef(HERMES_ORIGIN_KIND, {}), record))
    assert deliverer.records == [record]  # exact object, untouched
    assert receipt == {"state": "delivered", "transport_ref": "native-ref-1"}


# --- 2. the wiring routes by origin kind -----------------------------------


def _registry_with(transport: Any, kind: str = "paperclip_issue"
                   ) -> ResultDeliveryRegistry:
    registry = ResultDeliveryRegistry()
    registry.register(kind, transport)
    return registry


def test_wiring_routes_a_registered_carrier_kind_to_its_transport():
    store = _wiring_store("paperclip_issue")
    transport = RecordingTransport()
    _deliver(store, registry=_registry_with(transport))
    origin, payload = transport.calls[0]
    assert origin.kind == "paperclip_issue"
    assert origin.ids["conversation_id"] == "conv-7"  # typed ids survive
    assert payload["schema"] == "mastermind.execution_return/v1"
    assert _receipt(store)["delivery"]["state"] == "delivered"


def test_wiring_unregistered_kind_without_a_transport_refuses_honestly():
    # "hermes_teammate" is not a registered kind and no Hermes deliverer
    # was installed: the delivery refuses, never silently drops.
    store = _wiring_store("hermes_teammate")
    _deliver(store, registry=_registry_with(RecordingTransport()))
    receipt = _receipt(store)
    assert receipt["delivery"]["state"] == "refused"
    assert receipt["delivery"]["refusal_code"] == "ORIGIN_KIND_UNKNOWN"


def test_wiring_default_install_keeps_exactly_today_hermes_behavior():
    store = _wiring_store("hermes_teammate")  # unregistered carrier kind
    deliverer = RecordingDeliverer()
    _deliver(store, deliverer=deliverer)  # today's bare-install shape
    assert len(deliverer.records) == 1
    assert deliverer.records[0]["original_requester"]["conversation_id"] == "conv-7"
    assert _receipt(store)["delivery"]["state"] == "delivered"


def test_wiring_retry_after_a_committed_receipt_makes_no_second_delivery():
    """A replayed reconciliation of the SAME attempt finds the committed
    receipt event and returns without a second delivery — the non-Hermes
    transport target sees exactly one call, ever (the events table's
    UNIQUE command_id is what makes this atomic in production)."""
    store = _wiring_store("paperclip_issue")

    def by_command_id(command_id):
        return next(
            (row for row in store.appended
             if row.get("command_id") == command_id), None)

    store.get_event_by_command_id = by_command_id
    transport = RecordingTransport()
    _deliver(store, registry=_registry_with(transport))
    assert len(transport.calls) == 1
    # The retry: same attempt, same job, a fresh reconciler.
    _deliver(store, registry=_registry_with(transport))
    assert len(transport.calls) == 1
    assert len([a for a in store.appended
                if a["event_type"] == EXECUTION_RETURN_DELIVERY_EVENT]) == 1


# --- 3. the L1B3-4 idempotency fix ------------------------------------------


def test_idempotency_key_prefers_operation_key_then_falls_back_then_refuses():
    deliverer = RecordingDeliverer()
    store = _wiring_store("hermes_teammate", operation_key="op-per-attempt-9",
                          command_id="child-request:job-1")
    _deliver(store, deliverer=deliverer)
    assert deliverer.records[0]["attempt"]["idempotency_key"] == "op-per-attempt-9"
    # No binding operation_key: the admission command id is the fallback.
    store = _wiring_store(None, operation_key=None, command_id="child-request:cmd-1")
    _deliver(store, deliverer=deliverer)
    assert deliverer.records[-1]["attempt"]["idempotency_key"] == "child-request:cmd-1"
    # Neither id exists: honest refusal, never a guess.
    store = _wiring_store(None, operation_key=None, command_id=None)
    _deliver(store, deliverer=deliverer)
    receipt = _receipt(store)
    assert receipt["delivery"]["state"] == "refused"
    assert receipt["delivery"]["refusal_code"] == "ORIGINAL_BINDING_MISSING"
