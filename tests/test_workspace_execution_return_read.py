"""Honest execution-return projection reads (source-level composition proofs).

Every store below is a disposable ``RuntimeStore`` under ``tmp_path``; events
are appended through the store's own transaction/append path in the exact
shape the seam (``control_plane/execution_return_wiring.py``) writes.  These
prove the read owner's semantics only: no test delivers, retries or changes a
real job.  A missing receipt is the honest unavailable document; a malformed
row is a typed refusal; neither is ever a partial projection or an error.
"""
import asyncio

import pytest

from common import workspace_execution_return_contract as wire
from control_plane.workspace_execution_return_read import (
    ExistingExecutionReturnSource,
    default_source,
    handle_execution_return_frame,
)

ATTEMPT = "runs/att-1"
JOB = "JOB-42"
NOW = "2026-11-10T12:00:00+00:00"

RECEIPT = {
    "schema": wire.DELIVERY_SCHEMA,
    "return_id": "ret-1",
    "return_digest": "a" * 64,
    "conversation_id": "conv-1",
    "submission_id": "execret-" + "0" * 32,
    "state": "delivered",
    "transport_ref": "t3://thread/abc/run/77",
    "refusal_code": None,
}

REQUESTER_BLOCK = {
    "teammate_id": "hermes-engineering",
    "conversation_id": "sess-3f9c2",
    "project_id": "proj-mmos-v1",
    "carrier_kind": "",
}


def _clock():
    from datetime import datetime, timezone
    return datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


_WORKER = "W-1"
_QUOTA = "Q-1"
_HASH64 = "a" * 64
_NOW_MS = 1_800_000_000_000


def _seed_parents(connection, events):
    """Insert the FK parent rows the events table requires — the workers,
    quota class, jobs and attempts rows Executive admission would have
    created before any receipt event exists."""
    connection.execute(
        "INSERT INTO workers(worker_id, provider, account_label, worker_type,"
        " last_seen_at_ms, created_at_ms, updated_at_ms) VALUES(?,?,?,?,?,?,?)",
        (_WORKER, "fabric", "fixture", "fixture", _NOW_MS, _NOW_MS, _NOW_MS))
    connection.execute(
        "INSERT INTO worker_quota_classes(worker_id, quota_class, status, provider,"
        " last_seen_at_ms, created_at_ms, updated_at_ms) VALUES(?,?,?,?,?,?,?)",
        (_WORKER, _QUOTA, "AVAILABLE", "fabric", _NOW_MS, _NOW_MS, _NOW_MS))
    for job_id in sorted({e.get("job_id") for e in events} - {None}):
        connection.execute(
            "INSERT INTO jobs(job_id, objective, department, status, authority_level,"
            " constraints_json, requested_authorities_json, authority_policy_hash,"
            " available_at_ms, created_at_ms, updated_at_ms)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, "fixture objective", "fixture", "QUEUED", "CONTROL",
             "{}", "[]", _HASH64, _NOW_MS, _NOW_MS, _NOW_MS))
    for attempt_id, job_id in sorted(
            {(e.get("attempt_id"), e.get("job_id")) for e in events} - {(None, None)}):
        if attempt_id is None:
            continue
        connection.execute(
            "INSERT INTO attempts(attempt_id, job_id, attempt_number, worker_id,"
            " quota_class, status, fence_generation, authority_policy_hash,"
            " lease_token, lease_owner, lease_expires_at_ms, heartbeat_at_ms,"
            " started_at_ms, created_at_ms, updated_at_ms)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (attempt_id, job_id, 1, _WORKER, _QUOTA, "CLAIMED", 1, _HASH64,
             "lease-fixture", "fixture", _NOW_MS + 60_000, _NOW_MS,
             _NOW_MS, _NOW_MS, _NOW_MS))


def _write_store(tmp_path, events):
    """Create a real RuntimeStore and append the given events through it."""
    from control_plane.executive_runtime import RuntimeStore

    store = RuntimeStore(tmp_path)
    with store.transaction() as connection:
        _seed_parents(connection, events)
        for event in events:
            store.append_event(
                connection,
                aggregate_type=event.get("aggregate_type", "attempt"),
                aggregate_id=event.get("aggregate_id", ATTEMPT),
                event_type=event["event_type"],
                job_id=event.get("job_id"),
                attempt_id=event.get("attempt_id"),
                payload=event.get("payload") or {},
                command_id=event.get("command_id"),
            )
    return RuntimeStore(tmp_path)


def _receipt_event(payload=None, *, command_id=None, job_id=JOB):
    from control_plane.execution_return_wiring import (
        EXECUTION_RETURN_DELIVERY_EVENT,
        execution_return_receipt_command_id,
    )
    return {
        "event_type": EXECUTION_RETURN_DELIVERY_EVENT,
        "job_id": job_id,
        "attempt_id": ATTEMPT,
        "payload": {"delivery": dict(RECEIPT)} if payload is None else payload,
        "command_id": command_id or execution_return_receipt_command_id(ATTEMPT),
    }


def _job_created(job_id, provenance):
    return {
        "aggregate_type": "job", "aggregate_id": job_id,
        "event_type": "JOB_CREATED", "job_id": job_id,
        "payload": {"provenance": provenance},
    }


def _source(tmp_path, events):
    return ExistingExecutionReturnSource(
        store=_write_store(tmp_path, events), clock=_clock)


# ── honest states ───────────────────────────────────────────────────────────


def test_no_receipt_row_is_the_honest_unavailable_document(tmp_path):
    document = _source(tmp_path, []).read(ATTEMPT)
    assert wire.validate_document(document) is document
    assert document == wire.unavailable(
        ATTEMPT, "EXECUTION_RETURN_NOT_RECORDED", NOW)


def test_persisted_receipt_projects_verbatim_with_job_id_and_stage(tmp_path):
    events = [_receipt_event(payload={"delivery": dict(RECEIPT), "stage": "pr_open"})]
    document = _source(tmp_path, events).read(ATTEMPT)
    assert wire.validate_document(document) is document
    assert document["availability"] == "AVAILABLE"
    assert document["reason"] is None
    assert document["attempt_id"] == ATTEMPT
    assert document["job_id"] == JOB
    assert document["delivery"] == RECEIPT
    assert document["stage"] == "pr_open"
    # The result reference a Paperclip tab needs is the receipt's own locator.
    assert document["delivery"]["transport_ref"] == RECEIPT["transport_ref"]


def test_refused_receipt_projects_with_the_refusal_detail(tmp_path):
    receipt = {**RECEIPT, "state": "refused", "transport_ref": None,
               "return_id": "", "return_digest": "0" * 64,
               "refusal_code": "EXECUTION_RETURN_NO_BINDING"}
    events = [_receipt_event(payload={"delivery": receipt,
                                      "refusal_detail": "no original requester binding"})]
    document = _source(tmp_path, events).read(ATTEMPT)
    assert document["availability"] == "AVAILABLE"
    assert document["delivery"]["state"] == "refused"
    assert document["delivery"]["refusal_code"] == "EXECUTION_RETURN_NO_BINDING"
    assert document["refusal_detail"] == "no original requester binding"
    assert document["stage"] is None


def test_read_at_utc_uses_the_installed_clock(tmp_path):
    document = _source(tmp_path, []).read(ATTEMPT)
    assert document["read_at_utc"] == NOW


def test_invalid_attempt_id_raises_before_any_store_touch(tmp_path):
    source = _source(tmp_path, [_receipt_event()])
    with pytest.raises(ValueError):
        source.read("../escape")


# ── typed refusals, never partial ───────────────────────────────────────────


@pytest.mark.parametrize("payload", [
    {"delivery": dict(RECEIPT), "unexpected": 1},        # foreign payload key
    {"stage": "pr_open"},                                # delivery key absent
    {"delivery": None},
    {"delivery": {**RECEIPT, "schema": "mastermind.foreign/v1"}},
    {"delivery": {**RECEIPT, "state": "maybe"}},
    {"delivery": dict(RECEIPT), "stage": 42},
    {"delivery": dict(RECEIPT), "stage": "x" * 65},
    {"delivery": dict(RECEIPT), "refusal_detail": 7},
    {"delivery": dict(RECEIPT), "refusal_detail": "x" * 513},
])
def test_malformed_receipt_payload_is_a_typed_refusal(tmp_path, payload):
    document = _source(tmp_path, [_receipt_event(payload=payload)]).read(ATTEMPT)
    assert document == wire.unavailable(ATTEMPT, "RECEIPT_PAYLOAD_MALFORMED", NOW)


def test_wrong_event_type_at_the_receipt_command_id_is_malformed(tmp_path):
    from control_plane.execution_return_wiring import execution_return_receipt_command_id
    event = _receipt_event()
    event["event_type"] = "SOME_OTHER_EVENT"
    event["command_id"] = execution_return_receipt_command_id(ATTEMPT)
    document = _source(tmp_path, [event]).read(ATTEMPT)
    assert document == wire.unavailable(ATTEMPT, "RECEIPT_PAYLOAD_MALFORMED", NOW)


def test_an_unreadable_store_is_a_typed_refusal_not_a_traceback(tmp_path):
    class _BrokenStore:
        def get_event_by_command_id(self, command_id):
            raise OSError("disk gone")

        def list_events(self, **kwargs):
            raise OSError("disk gone")

    source = ExistingExecutionReturnSource(store=_BrokenStore(), clock=_clock)
    assert source.read(ATTEMPT) == wire.unavailable(ATTEMPT, "STORE_READ_FAILED", NOW)


def test_row_without_a_valid_job_id_keeps_the_receipt_and_nulls_the_join(tmp_path):
    document = _source(tmp_path, [_receipt_event(job_id="not-a-job")]).read(ATTEMPT)
    assert document["availability"] == "AVAILABLE"
    assert document["job_id"] is None
    assert document["original_requester"] is None
    assert document["delivery"] == RECEIPT


# ── the two-hop original_requester join ─────────────────────────────────────


def _direct_provenance():
    return {"original_requester": dict(REQUESTER_BLOCK)}


def _composed_provenance(admission_command_id):
    return {"child_placement_composition":
            {"admission_command_id": admission_command_id}}


def test_direct_job_provenance_projects_the_requester_block(tmp_path):
    events = [
        _receipt_event(),
        _job_created(JOB, _direct_provenance()),
    ]
    document = _source(tmp_path, events).read(ATTEMPT)
    assert document["original_requester"] == REQUESTER_BLOCK


def test_two_hop_provenance_reaches_the_admission_requester(tmp_path):
    admission_command_id = "admission-cmd-1"
    events = [
        _receipt_event(),
        _job_created(JOB, _composed_provenance(admission_command_id)),
        # The admission job's creation record carries the requester block.
        {**_job_created("JOB-7", _direct_provenance()),
         "command_id": admission_command_id},
    ]
    document = _source(tmp_path, events).read(ATTEMPT)
    assert document["original_requester"] == REQUESTER_BLOCK


@pytest.mark.parametrize("provenance", [
    None,                                                  # no JOB_CREATED provenance
    {"child_placement_composition": {"admission_command_id": "gone"}},
    {"child_placement_composition": {"admission_command_id": ""}},
    {"child_placement_composition": "not-a-dict"},
    {"original_requester": {"teammate_id": "only"}},       # not the closed block
    {"original_requester": {**REQUESTER_BLOCK, "authenticated_namespace": "ns"}},
])
def test_unreachable_or_foreign_provenance_is_null_never_guessed(tmp_path, provenance):
    events = [_receipt_event()]
    if provenance is not None:
        events.append(_job_created(JOB, provenance))
    document = _source(tmp_path, events).read(ATTEMPT)
    assert document["availability"] == "AVAILABLE"
    assert document["original_requester"] is None
    assert document["delivery"] == RECEIPT


# ── read-only proof ─────────────────────────────────────────────────────────


def test_read_opens_no_write_transaction_and_adds_no_event(tmp_path):
    store = _write_store(tmp_path, [_receipt_event()])
    source = ExistingExecutionReturnSource(store=store, clock=_clock)
    before = [(e.event_type, e.command_id) for e in store.list_events()]
    document = source.read(ATTEMPT)
    assert document["availability"] == "AVAILABLE"
    # The projection is read-only: every event row is untouched, nothing appended.
    assert [(e.event_type, e.command_id) for e in store.list_events()] == before


def test_default_source_composes_the_read_only_installed_store(tmp_path, monkeypatch):
    _write_store(tmp_path, [_receipt_event()])
    from control_plane import executive_runtime
    monkeypatch.setattr(executive_runtime, "_ROOT", tmp_path)
    source = default_source()
    assert type(source) is ExistingExecutionReturnSource
    assert source.store.create is False and source.store.existing_writable is False
    from control_plane.executive_runtime import StateConflict
    with pytest.raises(StateConflict):
        source.store.transaction()
    # And the composed default source reads real rows.
    assert source.read(ATTEMPT)["availability"] == "AVAILABLE"


# ── frame handler ───────────────────────────────────────────────────────────


class _Owner:
    def __init__(self, source):
        self._execution_return_source = source
        self.authorize = lambda principal: True
        self.authorize.binding_digest = lambda principal: "a" * 64


def _frame(attempt=ATTEMPT):
    return {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION,
            "selection": attempt, "principal": {"sub": "fixture"}}


def test_frame_handler_without_installed_source_serves_typed_absence():
    result = asyncio.run(handle_execution_return_frame(_Owner(None), _frame()))
    assert result["ok"] is True
    assert result["result"]["availability"] == "UNAVAILABLE"
    assert result["result"]["reason"] == "SOURCE_UNAVAILABLE"


def test_frame_handler_refuses_foreign_frame_shape():
    owner = _Owner(None)
    for frame in (None, {}, {**_frame(), "schema": "foreign"},
                  {**_frame(), "operation": "other"}, {**_frame(), "extra": 1},
                  {**_frame("../escape")}):
        result = asyncio.run(handle_execution_return_frame(owner, frame))
        assert result["ok"] is False and result["status"] == 400


def test_frame_handler_serves_the_exact_validated_document(tmp_path):
    owner = _Owner(_source(tmp_path, [_receipt_event()]))
    result = asyncio.run(handle_execution_return_frame(owner, _frame()))
    assert result["ok"] is True
    assert wire.validate_document(result["result"]) is result["result"]
    assert result["result"]["delivery"]["transport_ref"] == RECEIPT["transport_ref"]


def test_frame_handler_serves_source_swapped_mid_read_as_source_changed(
        tmp_path, monkeypatch):
    owner = _Owner(_source(tmp_path, [_receipt_event()]))
    real_read = ExistingExecutionReturnSource.read

    def swap_mid_read(self, attempt_id_value):
        owner._execution_return_source = ExistingExecutionReturnSource(
            store=self.store, clock=self.clock)
        return real_read(self, attempt_id_value)

    monkeypatch.setattr(ExistingExecutionReturnSource, "read", swap_mid_read)
    result = asyncio.run(handle_execution_return_frame(owner, _frame()))
    assert result["ok"] is True
    assert result["result"]["reason"] == "SOURCE_CHANGED"


@pytest.mark.parametrize("principal_revoked", [True, False])
def test_frame_handler_enforces_permission_at_release(tmp_path, principal_revoked):
    owner = _Owner(_source(tmp_path, [_receipt_event()]))
    calls = {"authorize": 0}

    def authorize(principal):
        calls["authorize"] += 1
        return not (principal_revoked and calls["authorize"] > 1)

    authorize.binding_digest = lambda principal: "a" * 64
    owner.authorize = authorize
    result = asyncio.run(handle_execution_return_frame(owner, _frame()))
    if principal_revoked:
        assert result["ok"] is False and result["status"] == 403
    else:
        assert result["ok"] is True
        assert result["result"]["attempt_id"] == ATTEMPT


def test_frame_handler_denies_a_denied_principal_before_any_read(tmp_path):
    owner = _Owner(_source(tmp_path, [_receipt_event()]))
    owner.authorize = lambda principal: False
    owner.authorize.binding_digest = lambda principal: "a" * 64
    result = asyncio.run(handle_execution_return_frame(owner, _frame()))
    assert result["ok"] is False and result["status"] == 403
