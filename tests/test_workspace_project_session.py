"""Synthetic project source plus real inert Runtime/OHF records; no provider."""
import copy
import dataclasses

import pytest

from common import workspace_project_session_contract as wire
from control_plane.executive_runtime import Runtime
from control_plane.operator_harness_contract import OperationId, ProcessIdentityObservation
from control_plane.operator_harness_wire import to_wire as operator_to_wire
from control_plane.operator_materialization_receipt import (
    MATERIALIZATION_STATUS_SCHEMA, build_operator_materialization_receipt, requested_profile_digest,
)
from control_plane.workspace_project_session import read_creation_evidence, compose_project_session_association
from tests.test_ceo_intent import _submit, _v2_intent
from tests.test_ohf_p1b_runtime import _profile, _attestation
from tests.test_operator_materialization_receipt import _inputs


def owner_fixture(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    runtime.workers.register_worker("worker-a", provider="codex", account_label="synthetic-only",
        worker_type="mock", capabilities=["read", "research"], quota_classes={"default": {
            "provider": "codex", "capabilities": ["read", "research"], "cost_class": "small"}})
    intent = _v2_intent(tmp_path, workstream="WS:SYNTHETIC-PROJECT")
    created = _submit(runtime, intent, tmp_path)
    selected = {"work_ref": intent["workstream"], "root_job_id": created["job_id"]}
    source = {"repository": "macro", "commit": intent["grounding"]["macro_sha"],
        "path": "agentos/workstreams/WS-SYNTHETIC-PROJECT.md", "content_sha256": "d" * 64,
        "request_sha256": "e" * 64}
    evidence = read_creation_evidence(runtime, selected=selected, project_source=source)
    planner = runtime.jobs.create_cycle_planner(created["job_id"],
        command_id=f"coo-cycle:{created['job_id']}:create-planner:0")
    dispatch = runtime.attempts.dispatch_cycle_job(planner.job_id,
        command_id=f"coo-cycle:{created['job_id']}:dispatch:{planner.job_id}:attempt:1", worker_id="worker-a")
    profile = _profile(dispatch)
    harness = runtime.operator_harness
    sealed = harness.seal_operator_harness_attempt(dispatch.attempt.attempt_id,
        fence_generation=dispatch.attempt.fence_generation, lease_token=dispatch.lease_token, requested=profile)
    operation = OperationId(f"ohf-op:start:{dispatch.attempt.attempt_id}")
    epoch, generation = harness.reserve_start(sealed.attempt_id, fence_generation=dispatch.attempt.fence_generation,
        lease_token=dispatch.lease_token, operation_id=operation)
    harness.bind_start_result(epoch=epoch, generation=generation, operation_id=operation,
        fence_generation=dispatch.attempt.fence_generation, lease_token=dispatch.lease_token,
        provider_session_id="synthetic-provider-session", process=ProcessIdentityObservation(2101, 2101, "synthetic-start", "synthetic-boot"))
    values = _inputs()
    values.pop("expected_provider_session_id")
    profile_digest = requested_profile_digest(operator_to_wire(profile))
    values.update(operation_command_id=operation.command_id, attempt_id=epoch.attempt_id,
        worker_id=epoch.worker_id, session_epoch_id=epoch.session_epoch_id,
        process_generation_id=generation.process_generation_id, generation_number=generation.generation_number,
        provider_session_id="synthetic-provider-session", requested_profile_digest=profile_digest,
        observed_attestation=operator_to_wire(_attestation(profile)))
    receipt = build_operator_materialization_receipt(**values)
    status = {"schema_version": MATERIALIZATION_STATUS_SCHEMA,
              "status": "RECEIPT_CURRENT_IN_LIVE_BROKER", "receipt": receipt.to_dict()}
    return runtime, selected, source, evidence, epoch, generation, profile_digest, status


def read(fixture, **overrides):
    _, _, _, evidence, epoch, generation, profile_digest, status = fixture
    args = {"epoch": epoch, "generation": generation, "requested_profile_digest": profile_digest,
            "broker_status": status}
    args.update(overrides)
    return compose_project_session_association(evidence, **args)


def test_real_creation_ohf_refs_and_receipt_project_only_observational_evidence(tmp_path):
    fixture = owner_fixture(tmp_path)
    body = read(fixture)
    assert body["state"] == "MATERIALIZED_OBSERVATION"
    assert body["can_send"] is False and body["continuation_target"] is None and body["observational_only"] is True
    assert body["project_source"] == fixture[2]
    assert body["runtime_creation"]["intent_id"] == "CEO-2026-08-13-A"
    assert body["materialization"]["generation_number"] == 1
    import json
    text = json.dumps(body)
    for private in ("synthetic-provider-session", "synthetic-start", "/var/empty", "synthetic-only", "process_credentials"):
        assert private not in text


@pytest.mark.parametrize("status,state,reason", [
    ("ABSENT", "PREPARING", "NOT_MATERIALIZED"),
    ("CONFLICT", "UNAVAILABLE", "MATERIALIZATION_CONFLICT"),
    ("RECEIPT_ONLY_AFTER_RESTART", "RECORDED_MATERIALIZATION", "BROKER_RESTARTED"),
])
def test_actual_broker_state_vocabulary_remains_distinct(tmp_path, status, state, reason):
    fixture = owner_fixture(tmp_path)
    observation = copy.deepcopy(fixture[-1])
    observation["status"] = status
    if status in {"ABSENT", "CONFLICT"}:
        observation["receipt"] = None
    body = read(fixture, broker_status=observation)
    assert (body["state"], body["reason"]) == (state, reason)
    assert body["can_send"] is False
    if state == "UNAVAILABLE":
        assert body["project_source"] is body["runtime_creation"] is body["materialization"] is None


def test_queued_root_never_becomes_a_conversation_without_real_epoch_and_broker_evidence(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    intent = _v2_intent(tmp_path, workstream="WS:SYNTHETIC-PROJECT")
    receipt = _submit(runtime, intent, tmp_path)
    selected = {"work_ref": intent["workstream"], "root_job_id": receipt["job_id"]}
    source = {"repository": "macro", "commit": intent["grounding"]["macro_sha"],
        "path": "agentos/workstreams/WS-SYNTHETIC-PROJECT.md", "content_sha256": "d" * 64, "request_sha256": "e" * 64}
    evidence = read_creation_evidence(runtime, selected=selected, project_source=source)
    body = compose_project_session_association(evidence, epoch=None, generation=None,
        requested_profile_digest="a" * 64, broker_status={"schema_version": MATERIALIZATION_STATUS_SCHEMA,
                                                      "status": "ABSENT", "receipt": None})
    assert body["state"] == "UNAVAILABLE" and body["materialization"] is None


def test_frame_reuses_exact_workspace_read_principal_and_refuses_caller_session_fields():
    from tests.test_workspace_member_bindings import fixture, principal
    _, bindings = fixture()
    request = {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION, "principal": principal(bindings),
               "selection": {"work_ref": "WS:SYNTHETIC-PROJECT", "root_job_id": "JOB-001"}}
    assert wire.validate_frame(request) == request
    for fields in ({"provider_session_id": "client-session"}, {"epoch": "client-epoch"}, {"principal": "chairman"}):
        changed = copy.deepcopy(request)
        changed["selection"].update(fields)
        with pytest.raises(ValueError): wire.validate_frame(changed)
    changed = copy.deepcopy(request)
    changed["principal"]["scopes"] = ["mastermind.executive.intent.submit"]
    with pytest.raises(ValueError): wire.validate_frame(changed)


def test_foreign_or_changed_source_and_profile_cannot_bind_a_session(tmp_path):
    fixture = owner_fixture(tmp_path)
    runtime, selected, source = fixture[:3]
    for replacement in ({"commit": "a" * 40}, {"path": "agentos/workstreams/WS-OTHER.md"}):
        with pytest.raises(ValueError):
            read_creation_evidence(runtime, selected=selected, project_source={**source, **replacement})
    assert read(fixture, requested_profile_digest="f" * 64)["reason"] == "SOURCE_MISMATCH"
    foreign_generation = dataclasses.replace(fixture[5], worker_id="foreign-worker")
    assert read(fixture, generation=foreign_generation)["reason"] == "SOURCE_MISMATCH"


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(can_send=True), lambda b: b.update(continuation_target="fabric_attempt:invented"),
    lambda b: b.update(observational_only=False), lambda b: b.update(state="CURRENT_QUALIFIED_TARGET"),
    lambda b: b["materialization"].update(provider_session_id="raw-secret-session"),
    lambda b: b["materialization"].update(recorded_at="2026-02-30T00:00:00Z"),
    lambda b: b["materialization"].update(generation_number=True),
    lambda b: b.update(reason="BROKER_RESTARTED"),
])
def test_closed_dto_rejects_authority_foreign_fields_and_false_clocks(tmp_path, mutation):
    body = read(owner_fixture(tmp_path))
    mutation(body)
    with pytest.raises(ValueError):
        wire.validate_body(body)
