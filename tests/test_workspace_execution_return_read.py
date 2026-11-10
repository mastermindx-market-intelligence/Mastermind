"""Real Runtime completion and original-return evidence through Workspace reads."""
import asyncio
import copy
from contextlib import contextmanager
from dataclasses import replace

import pytest

from common import workspace_execution_return_contract as wire
from control_plane import executive_runtime as er
from control_plane.execution_return_projection import (
    canonical_record_bytes, project_execution_return, mint_return_submission_id,
    validate_execution_return_delivery,
)
from control_plane.execution_return_wiring import ExecutionReturnWiring
from control_plane.executive_orchestration_principal import digest
from control_plane.workspace_execution_return_read import validate_body
from integrations.session_bridge.hermes_native_return import HermesExecutionReturnDeliverer
from tests.test_workspace_result_service import result_owner, service, request


class NeverSend:
    async def send(self, **kwargs):
        pytest.fail("a retained read attempted a native send")

    async def read_original(self, *args, **kwargs):
        pytest.fail("a retained read attempted native reconciliation")


def authorize(principal):
    return True


authorize.binding_digest = lambda principal: "a" * 64


def selected_request(owner):
    frame = request(owner)
    return {**frame, "schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION}


def call(owner, **kwargs):
    return asyncio.run(service(owner, authorize=kwargs.pop("authorize", authorize), **kwargs)
                       .handle_frame(selected_request(owner)))


def retain(owner, *, state="delivered", receipt_job_id=None):
    runtime, selection = owner["writer"], owner["selection"]
    job = runtime.jobs.get_job(selection["job_id"])
    attempt_id = selection["attempt_id"]
    seal = digest({"attempt_id": attempt_id, "job_id": job.job_id,
                   "status": job.status.value, "result_digest": digest(job.result)})
    record = project_execution_return({
        "original_requester": {"teammate_id": "fixture-team", "conversation_id": "fixture-session",
                               "project_id": "fixture-project", "authenticated_namespace": "fixture-principal"},
        "attempt": {"attempt_id": attempt_id, "root_id": selection["root_job_id"],
                    "idempotency_key": "fixture-child", "authenticated_namespace": "fixture-principal",
                    "t3_thread_id": "fixture-thread", "t3_run_id": "fixture-run",
                    "seal": {"schema": "mastermind terminal seal", "digest": seal}},
        "result": {"text": "Selected canonical result", "artifact_refs": [],
                   "acceptance": "not_accepted", "installation_claimed": False},
        "github": {"branch": None, "pr_number": None, "pr_url": None,
                   "checks": None, "merge_state": "unknown"},
    })
    wiring = ExecutionReturnWiring(store=runtime.store, deliverer=HermesExecutionReturnDeliverer(NeverSend()))
    original = {"binding": {"fixture": "private original native binding"},
                "request": {"operation": "submit", "target": {"session_id": "fixture-session"},
                            "text": canonical_record_bytes(record).decode()}, "input_sha256": "b" * 64}
    intent = wiring._reserve_original(runtime.store, job, attempt_id, record, original)
    receipt = validate_execution_return_delivery({
        "schema": "mastermind.execution_return_delivery/v1", "return_id": record["return_id"],
        "return_digest": record["digest"], "conversation_id": "fixture-session",
        "submission_id": mint_return_submission_id(record["digest"], "fixture-session"),
        "state": state, "transport_ref": "fixture-admission" if state == "delivered" else None,
        "refusal_code": "REFUSED" if state == "refused" else None,
    })
    if receipt_job_id is None:
        wiring._record_receipt(runtime.store, job, attempt_id, record, receipt, intent=intent, source="submit")
    else:
        # A wrong producer appends a foreign event once. Existing immutable
        # event triggers remain intact; the bounded consumer must refuse it.
        with runtime.store.transaction() as connection:
            runtime.store.append_event(connection, aggregate_type="attempt", aggregate_id=attempt_id,
                event_type="EXECUTION_RETURN_DELIVERY", job_id=receipt_job_id, attempt_id=attempt_id,
                command_id="execution-return:" + attempt_id, payload={
                    "delivery": receipt, "stage": record["stage"], "source": "submit",
                    "intent_command_id": "execution-return-intent:" + attempt_id, "intent_digest": intent["digest"],
                })
    return wiring, job, intent, record, receipt


def test_real_bounded_read_releases_only_original_record_and_receipt(result_owner):
    o = result_owner
    _, _, _, record, receipt = retain(o)
    events = o["writer"].store.list_events()
    before = o["namespace"].entries
    body = call(o)["result"]
    assert validate_body(body, o["selection"]) is body
    assert body["availability"] == "AVAILABLE"
    assert body["execution_return"] == record and body["delivery_receipt"] == receipt
    assert body["execution_return"]["acceptance"] == "not_accepted"
    assert "private original native binding" not in str(body)
    assert o["namespace"].entries == before + 1 == o["namespace"].exits
    assert not o["namespace"].active
    assert o["writer"].store.list_events() == events


def test_no_original_evidence_is_empty_not_delivered_or_accepted(result_owner):
    body = call(result_owner)["result"]
    assert body["availability"] == "AVAILABLE"
    assert body["execution_return"] is None and body["delivery_receipt"] is None


def test_read_only_original_unknown_then_validated_reconciliation(result_owner):
    o = result_owner
    wiring, job, intent, record, receipt = retain(o, state="unknown")
    body = call(o)["result"]
    assert body["delivery_receipt"]["state"] == "unknown"
    delivered = dict(receipt, state="delivered", transport_ref="fixture-admission")
    wiring._record_receipt(o["writer"].store, job, o["selection"]["attempt_id"], record,
                           delivered, intent=intent, source="read_original")
    body = call(o)["result"]
    assert body["delivery_receipt"] == delivered
    assert body["execution_return"]["acceptance"] == "not_accepted"


@pytest.mark.parametrize("field", ["root_job_id", "job_id", "attempt_id", "result_envelope_digest"])
def test_foreign_exact_coordinates_never_release_result(result_owner, field):
    o = result_owner
    retain(o)
    frame = selected_request(o)
    frame["selection"][field] = "c" * 64 if field == "result_envelope_digest" else (
        "ATT-foreign" if field == "attempt_id" else "JOB-foreign")
    response = asyncio.run(service(o, authorize=authorize).handle_frame(frame))
    if response.get("ok") is True:
        assert response["result"]["availability"] == "UNAVAILABLE"
        assert response["result"]["execution_return"] is None
    else:
        assert response["status"] in (400, 404)


def test_parent_root_membership_is_checked_before_runtime(result_owner):
    o = result_owner
    o["owners"][0].state_cache["doc"]["work"] = []
    before = o["namespace"].entries
    assert call(o)["status"] == 404
    assert o["namespace"].entries == before


def test_receipt_identity_corruption_discards_all_evidence(result_owner):
    o = result_owner
    retain(o, receipt_job_id=o["selection"]["root_job_id"])
    body = call(o)["result"]
    assert body == wire.unavailable(o["selection"], "SOURCE_UNAVAILABLE")["result"]


@pytest.mark.parametrize("mutation", ["owner", "publication", "document"])
def test_changed_control_room_discards_all_evidence(result_owner, mutation):
    o = result_owner
    retain(o)
    original = o["cache"].snapshot
    calls = [0]
    def snapshot():
        calls[0] += 1
        value = original()
        if calls[0] == 2:
            if mutation == "owner": value = replace(value, owner=object())
            elif mutation == "publication": value = replace(value, publication=value.publication + 1)
            else:
                document = copy.deepcopy(value.document)
                document["work"][0]["agent_os"]["title"] = "changed"
                value = replace(value, document=document)
        return value
    o["cache"].snapshot = snapshot
    assert call(o)["result"] == wire.unavailable(o["selection"], "SOURCE_CHANGED")["result"]


@pytest.mark.parametrize("stage", ["before", "after"])
def test_permission_revocation_discards_result(result_owner, monkeypatch, stage):
    o = result_owner
    retain(o)
    grant = {"enabled": True}
    def allowed(principal): return grant["enabled"]
    allowed.binding_digest = lambda principal: "a" * 64
    original = er.Runtime.observe_bounded_read
    @contextmanager
    def observed(runtime):
        with original(runtime) as observation: yield observation
        grant["enabled"] = False
    monkeypatch.setattr(er.Runtime, "observe_bounded_read", observed)
    if stage == "before": grant["enabled"] = False
    before = o["namespace"].entries
    assert call(o, authorize=allowed)["status"] == 403
    assert o["namespace"].entries - before == (stage == "after")


def test_missing_permission_receipt_never_reads_runtime(result_owner):
    before = result_owner["namespace"].entries
    assert call(result_owner, authorize=lambda principal: True)["status"] == 403
    assert result_owner["namespace"].entries == before


def test_read_budget_covers_completion_and_original_event_cells(result_owner, monkeypatch):
    o = result_owner
    retain(o)
    monkeypatch.setattr(er, "BOUNDED_ROLE_RESULT_MAX_CELL_BYTES", 32)
    assert call(o)["result"] == wire.unavailable(o["selection"], "OVER_BUDGET")["result"]


def test_a_second_selection_poisoning_remains_enforced(result_owner):
    o = result_owner
    selected = o["selection"]
    with pytest.raises(er.StateConflict):
        with o["reader"].observe_bounded_read() as observation:
            for _ in range(2):
                observation.read_execution_return_bounded(selected["root_job_id"], selected["job_id"],
                    expected_attempt_id=selected["attempt_id"],
                    expected_result_envelope_digest=selected["result_envelope_digest"])
