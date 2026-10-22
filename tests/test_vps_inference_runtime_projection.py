"""Pure service return projection over the existing bounded Runtime observation.

Fixtures create synthetic terminal rows in temporary SQLite; this does not
prove Supervisor collection, installed namespace custody or provider execution.
"""
import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from control_plane.executive_runtime import Runtime, RuntimeReadBinding, StateConflict
from control_plane.executive_inference_contract import validate_direct_result
from integrations.executive_mcp import web_ceo
from integrations.executive_mcp import schemas
from tests.test_vps_inference_runtime_read import admitted, synthetic_complete, OP
from tests.test_executive_runtime_bounded_read import ObservationNamespace


def projected(runtime, ref):
    from control_plane.executive_inference_runtime_view import direct_result_from_runtime
    return direct_result_from_runtime(runtime, OP, ref)


def qualified_reader(writer, tmp_path):
    root = tmp_path / "runtime"
    namespace = ObservationNamespace(writer.store.path)
    binding = RuntimeReadBinding(namespace)
    runtime = Runtime.at(root, create=False, read_binding=binding)
    return runtime, binding


def cleanup(binding):
    if binding._unclosed_connection is not None:
        sqlite3.Connection.close(binding._unclosed_connection)
    if binding._retained_namespace is not None:
        binding._retained_namespace.close()


def test_default_writable_runtime_cannot_claim_same_source_generation(tmp_path):
    writer, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(writer, receipt["job_id"])
    with pytest.raises(StateConflict):
        projected(writer, ref)


def test_qualified_fixture_observation_projects_complete_bound_result(tmp_path):
    writer, receipt = admitted(tmp_path)
    ref, doc, _ = synthetic_complete(writer, receipt["job_id"])
    reader, binding = qualified_reader(writer, tmp_path)
    try:
        value = projected(reader, ref)
    finally:
        cleanup(binding)
    assert value["schema"] == "mastermind.fabric_service_inference_result_view.v1"
    assert value["operation_ref"] == receipt["intent_id"]
    assert value["reference"] == ref
    assert value["request_fingerprint"] == receipt["fingerprint"]
    assert value["generation"]["state"] == "SAME"
    assert value["availability"] == "AVAILABLE"
    assert value["execution_status"] == "COMPLETED"
    assert value["content_complete"] is True
    assert value["acceptance"] == "NOT_PROJECTED"
    assert value["document"] == doc


def test_existing_client_validator_accepts_the_exact_bounded_fixture_view(tmp_path):
    writer, receipt = admitted(tmp_path)
    ref, doc, _ = synthetic_complete(writer, receipt["job_id"])
    reader, binding = qualified_reader(writer, tmp_path)
    try:
        projection = projected(reader, ref)
    finally:
        cleanup(binding)
    envelope = schemas.result_envelope(
        "executive_fabric", mode=schemas.ServerMode.READONLY,
        generated_at="2026-10-12T00:00:00Z", data=projection,
        grounding={"fixture": "temporary", "source": "bounded Runtime"},
        degraded=[],
    )
    envelope["server_version"] = web_ceo.WEB_CEO_V2_SERVER_VERSION
    checked = validate_direct_result(
        envelope, operation_key=OP, receipt=receipt, reference=ref, max_output_chars=4096,
    )
    assert checked == projection
    assert checked["document"]["result"]["answer"] == doc["result"]["answer"]


def test_missing_or_foreign_reference_cannot_be_projected_as_a_result(tmp_path):
    writer, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(writer, receipt["job_id"])
    for altered in [dict(ref, job_id="JOB-999"),
                    dict(ref, content_sha256="f" * 64)]:
        # One failed bound Runtime observation is poisoned and cannot reopen;
        # each independent negative test needs a new test-owned namespace.
        reader, binding = qualified_reader(writer, tmp_path)
        try:
            with pytest.raises((StateConflict, ValueError)):
                projected(reader, altered)
        finally:
            cleanup(binding)


def test_nonexistent_direct_producer_never_looks_like_a_completed_answer(tmp_path):
    writer, _ = admitted(tmp_path)
    reader, binding = qualified_reader(writer, tmp_path)
    try:
        with pytest.raises(StateConflict):
            projected(reader, {"schema":"invalid"})
    finally:
        cleanup(binding)


def test_direct_projection_refuses_substituted_observation_identity(tmp_path, monkeypatch):
    from control_plane import executive_runtime as runtime_owner
    writer, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(writer, receipt["job_id"])
    reader, binding = qualified_reader(writer, tmp_path)
    original = runtime_owner.BoundedRuntimeReadObservation.read_service_inference_bounded

    def substitute(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if result is not None:
            result["observation_source_identity"] = "f" * 32
        return result

    try:
        with monkeypatch.context() as patch:
            patch.setattr(runtime_owner.BoundedRuntimeReadObservation,
                          "read_service_inference_bounded", substitute)
            with pytest.raises(StateConflict, match="identity"):
                projected(reader, ref)
    finally:
        cleanup(binding)


def test_qualified_direct_snapshot_carries_same_observation_identity(tmp_path):
    writer, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(writer, receipt["job_id"])
    reader, binding = qualified_reader(writer, tmp_path)
    try:
        with reader.observe_bounded_read() as observed:
            raw = observed.read_service_inference_bounded(OP, reference=ref)
        proof = observed.receipt.to_dict()
        assert proof["state"] == "SAME"
        assert raw["observation_source_identity"] == proof["source_identity"]
    finally:
        cleanup(binding)


def test_valid_near_document_limit_is_not_incorrectly_rejected_by_view_budget(tmp_path):
    import hashlib
    from control_plane import executive_inference_ingress as ingress
    from control_plane import executive_inference_io as io
    from tests.test_vps_inference_service import GROUND, host_execution_binding, service_request, inference_request
    from tests.test_vps_inference_runtime_read import qualified_attempt
    root=tmp_path
    runtime=Runtime.at(root/"runtime")
    request=service_request("large-source-only", "Inspect preserved evidence.",
                            request=inference_request(max_output_chars=131072))
    class Ground:
        def observe(self):return GROUND
    receipt=asyncio.run(ingress.handle_frame(
        {"schema":ingress.SUBMIT_SCHEMA,"request":request,"observed_grounding":GROUND},
        runtime=runtime,grounding_provider=Ground(),workspace_root=root,
        admission_guard=lambda _:None,
        execution_binding_provider=lambda identity:host_execution_binding(root,identity),
    ))
    attempt=qualified_attempt(runtime,receipt["job_id"])
    answer="é"*97900
    result={"schema_version":io.WORKER_RESULT_SCHEMA,"job_id":receipt["job_id"],
            "run_id":attempt.attempt_id,"worker_id":attempt.worker_id,
            "status":"COMPLETED","answer":answer}
    ref=io.result_reference(job_id=receipt["job_id"],attempt_id=attempt.attempt_id,
        worker_id=attempt.worker_id,result_sha256="b"*64,
        content_sha256=hashlib.sha256(io.canonical_bytes(result)).hexdigest())
    document=io.result_document(reference=ref,result=result,max_output_chars=131072,
        raw_result_sha256="b"*64)
    assert len(io.canonical_bytes(document))<io.MAX_RESULT_BYTES
    encoded=io.canonical_bytes(document).decode()
    with runtime.store.transaction() as db:
        db.execute("UPDATE attempts SET status='COMPLETED',result_json=?,exit_code=0,"
                   "lease_token=NULL,finished_at_ms=1000,updated_at_ms=1000 WHERE attempt_id=?",
                   (encoded,attempt.attempt_id))
        db.execute("UPDATE jobs SET status='COMPLETED',result_json=? WHERE job_id=?",
                   (encoded,receipt["job_id"]))
    reader,binding=qualified_reader(runtime,root)
    try:
        from control_plane.executive_inference_runtime_view import direct_result_from_runtime
        view=direct_result_from_runtime(reader,"large-source-only",ref)
    finally:
        cleanup(binding)
    assert view["document"]==document
    assert view["document"]["result"]["answer"]==answer
    assert len(io.canonical_bytes(view))>io.MAX_RESULT_BYTES
    # Final authenticated/socket layers have stricter limits and MUST refuse
    # an oversized envelope. A complete read projection is not a delivery proof.
