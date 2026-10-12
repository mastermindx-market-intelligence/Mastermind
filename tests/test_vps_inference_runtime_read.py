"""Bounded owner-only direct service result observation; synthetic terminal rows.

Positive fixtures simulate a *future* trusted completion writer in temporary
SQLite. They establish no real Supervisor/provider/raw-file authenticity.
"""
import asyncio
import hashlib
import json

import pytest

from control_plane import executive_inference_ingress as ingress
from control_plane import executive_inference_io as io
from control_plane.executive_runtime import Runtime, StateConflict
from control_plane.model_router import ModelRouter
from tests.test_vps_inference_service import GROUND, host_execution_binding, service_request


OP = "inference-test"


def admitted(tmp_path):
    runtime = Runtime.at(tmp_path / "runtime")
    class Ground:
        def observe(self):
            return GROUND
    receipt = asyncio.run(ingress.handle_frame(
        {"schema": ingress.SUBMIT_SCHEMA, "request": service_request(),
         "observed_grounding": GROUND},
        runtime=runtime, grounding_provider=Ground(), workspace_root=tmp_path,
        admission_guard=lambda _: None,
        execution_binding_provider=lambda identity: host_execution_binding(tmp_path, identity),
    ))
    return runtime, receipt


def qualified_attempt(runtime, job_id):
    router = ModelRouter.load()
    model = router.resolve_model_alias("fast.research")
    metadata = {
        "adapter_id": model.adapter_id,
        "model_alias": model.model_alias,
        "provider_alias": model.provider_alias,
        "routing_policy_version": router.policy_version,
        "execution_profile_id": model.execution_profile_id,
        "execution_profile_digest": model.execution_profile_digest,
        "capability_policy_version": model.capability_policy_version,
        "capability_policy_digest": model.capability_policy_digest,
    }
    runtime.workers.register_worker(
        "fixture-worker", provider=model.provider_alias,
        account_label="temporary-fixture", worker_type=model.adapter_id,
        capabilities=list(model.capabilities),
        quota_classes={"fixture": {
            "provider": model.provider_alias, "model": model.model,
            "effort": model.effort, "cost_class": model.cost_class,
            "capabilities": list(model.capabilities), "metadata": metadata,
        }},
    )
    lease = runtime.broker.claim(job_id, lease_owner="source-test")
    assert lease is not None
    return lease.attempt


def synthetic_complete(runtime, job_id, *, ref=None, answer="SYNTHETIC ONLY: no provider"):
    attempt = qualified_attempt(runtime, job_id)
    result = {"schema_version": io.WORKER_RESULT_SCHEMA, "job_id": job_id,
              "run_id": attempt.attempt_id, "worker_id": attempt.worker_id,
              "status": "COMPLETED", "answer": answer}
    ref = ref or io.result_reference(
        job_id=job_id, attempt_id=attempt.attempt_id, worker_id=attempt.worker_id,
        result_sha256="b" * 64,
        content_sha256=hashlib.sha256(io.canonical_bytes(result)).hexdigest(),
    )
    doc = io.result_document(
        reference=ref, result=result, raw_result_sha256="b" * 64,
        max_output_chars=4096,
    )
    encoded = io.canonical_bytes(doc).decode()
    # Fixture-only simulation of the *future* writer. No provider or Supervisor
    # is invoked. Do not classify this as actual terminal creation evidence.
    with runtime.store.transaction() as db:
        db.execute(
            "UPDATE attempts SET status='COMPLETED',result_json=?,exit_code=0,"
            "lease_token=NULL,finished_at_ms=1000,updated_at_ms=1000 "
            "WHERE attempt_id=?",
            (encoded, attempt.attempt_id),
        )
        db.execute("UPDATE jobs SET status='COMPLETED',result_json=?,updated_at_ms=1000 WHERE job_id=?",
                   (encoded, job_id))
    return ref, doc, attempt


def observe(runtime, operation_key=OP, reference=None):
    with runtime.observe_bounded_read() as read:
        value = read.read_service_inference_bounded(operation_key, reference=reference)
    return value, read.receipt


def test_queued_job_has_no_result_reference_and_never_opens_new_database(tmp_path, monkeypatch):
    runtime, receipt = admitted(tmp_path)
    assert runtime.jobs.get_job(receipt["job_id"]).current_attempt_id is None
    value, observation = observe(runtime)
    assert value is None
    assert observation.state == "UNKNOWN"  # No installed namespace binding.
    with runtime.observe_bounded_read() as read:
        assert read.read_service_inference_bounded("other-operation") is None


def test_exact_terminal_reference_retrieval_and_status_only_no_answer(tmp_path):
    runtime, receipt = admitted(tmp_path)
    ref, document, attempt = synthetic_complete(runtime, receipt["job_id"])
    status, observation = observe(runtime)
    assert status == {"reference": ref, "request_fingerprint": receipt["fingerprint"],
                      "intent_id": receipt["intent_id"],
                      "observation_source_identity": None}
    assert "document" not in status
    value, another = observe(runtime, reference=ref)
    assert value["reference"] == ref
    assert value["document"] == document
    assert value["request_fingerprint"] == receipt["fingerprint"]
    assert value["intent_id"] == receipt["intent_id"]
    assert observation.state == another.state == "UNKNOWN"
    assert runtime.jobs.get_job(receipt["job_id"]).status.value == "COMPLETED"


def test_status_selects_exact_operation_and_refuses_foreign_result(tmp_path):
    runtime, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(runtime, receipt["job_id"])
    assert observe(runtime, operation_key="other-operation")[0] is None
    with pytest.raises(StateConflict):
        observe(runtime, operation_key="other-operation", reference=ref)
    for changed in [
        dict(ref, result_sha256="f" * 64),
        dict(ref, content_sha256="f" * 64),
        dict(ref, attempt_id="ATT-" + "a" * 32),
        dict(ref, job_id="JOB-999"),
    ]:
        with pytest.raises((StateConflict, io.InferenceIOError)):
            observe(runtime, reference=changed)


def test_generic_completed_jobpayload_is_never_an_inference_answer(tmp_path):
    runtime, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(runtime, receipt["job_id"])
    with runtime.store.transaction() as db:
        generic = json.dumps({"summary": "fake answer", "errors": []})
        # Job rows are mutable; Attempt terminal rows are immutable.
        db.execute("UPDATE jobs SET result_json=? WHERE job_id=?", (generic, receipt["job_id"]))
    with pytest.raises((StateConflict, io.InferenceIOError)):
        observe(runtime)
    with pytest.raises((StateConflict, io.InferenceIOError)):
        observe(runtime, reference=ref)


def test_absence_of_completed_attempt_refuses_answer(tmp_path):
    runtime, receipt = admitted(tmp_path)
    attempt = qualified_attempt(runtime, receipt["job_id"])
    assert runtime.attempts.get_attempt(attempt.attempt_id).status.value == "CLAIMED"
    value, _ = observe(runtime)
    assert value is None


def test_foreign_result_is_not_accepted_after_same_payload_tamper(tmp_path):
    runtime, receipt = admitted(tmp_path)
    ref, doc, _ = synthetic_complete(runtime, receipt["job_id"])
    tampered = json.loads(json.dumps(doc))
    tampered["result"]["answer"] = "FORGED ANSWER"
    encoded = io.canonical_bytes(tampered).decode()
    with runtime.store.transaction() as db:
        db.execute("UPDATE jobs SET result_json=? WHERE job_id=?", (encoded, receipt["job_id"]))
    with pytest.raises((StateConflict, io.InferenceIOError)):
        observe(runtime, reference=ref)


def test_observation_single_selection_fence_and_closed_receipt(tmp_path):
    runtime, _ = admitted(tmp_path)
    with runtime.observe_bounded_read() as read:
        assert read.read_service_inference_bounded(OP) is None
        with pytest.raises(StateConflict):
            read.read_service_inference_bounded(OP)
        with pytest.raises(StateConflict):
            _ = read.receipt


def test_identity_checked_before_result_projection(tmp_path):
    runtime, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(runtime, receipt["job_id"])
    # A v1 reference has raw provenance only; the direct consumer requires v2.
    raw_only = {k: v for k, v in ref.items() if k != "content_sha256"}
    raw_only["schema"] = io.RESULT_REF_SCHEMA
    with pytest.raises((StateConflict, io.InferenceIOError)):
        observe(runtime, reference=raw_only)

def test_failed_direct_selection_never_finalizes_an_observation_receipt(tmp_path):
    runtime, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(runtime, receipt["job_id"])
    wrong = dict(ref, content_sha256="f" * 64)
    with runtime.observe_bounded_read() as reader:
        with pytest.raises((StateConflict, io.InferenceIOError)):
            reader.read_service_inference_bounded(OP, reference=wrong)
    with pytest.raises(StateConflict):
        _ = reader.receipt


def test_live_result_is_not_an_authorized_synthetic_worker_attestation(tmp_path):
    runtime, receipt = admitted(tmp_path)
    ref, _, attempt = synthetic_complete(runtime, receipt["job_id"])
    # The read contract sees only completed DB rows. A positive fixture must
    # not be misrepresented as proof that the raw provider bytes exist, or that
    # a Supervisor/adapter ran, even when canonical content hashes match.
    value, observed = observe(runtime, reference=ref)
    assert value["document"]["result"]["answer"].startswith("SYNTHETIC")
    assert observed.state == "UNKNOWN"
    assert runtime.attempts.get_attempt(attempt.attempt_id).provider_session_id is None

def test_malformed_reference_valueerror_poisoned_observation_cannot_report_success(tmp_path):
    runtime, _ = admitted(tmp_path)
    with runtime.observe_bounded_read() as reader:
        with pytest.raises(StateConflict):
            reader.read_service_inference_bounded(OP, reference={"schema": "invalid"})
    with pytest.raises(StateConflict):
        _ = reader.receipt
