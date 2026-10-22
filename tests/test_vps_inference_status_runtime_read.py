"""Service status consumes a host-provided, source-qualified Runtime read owner.

No new service entrypoint, queue or caller-provided read path. Synthetic terminal
rows in this test are NOT worker/collect/production completion evidence.
"""
import asyncio

import pytest

from control_plane import executive_inference_ingress as ingress
from control_plane.executive_ceo_ingress import CeoIngressError
from tests.test_vps_inference_runtime_read import admitted, synthetic_complete, OP
from tests.test_vps_inference_runtime_projection import qualified_reader, cleanup


def status(writer, *, read_runtime=None, operation=OP):
    class Ground:
        def observe(self): return {"unused": "status needs no fresh grounding"}
    return asyncio.run(ingress.handle_frame(
        {"schema": ingress.STATUS_SCHEMA, "operation_key": operation},
        runtime=writer, grounding_provider=Ground(), workspace_root=None,
        admission_guard=None, result_read_runtime=read_runtime,
    ))


def test_no_read_owner_retains_null_reference_for_queued_job(tmp_path):
    writer, receipt = admitted(tmp_path)
    result = status(writer)
    assert result["receipt"]["job_id"] == receipt["job_id"]
    assert result["terminal_result_ref"] is None


def test_bound_canonical_reader_exposes_exact_terminal_reference_only(tmp_path):
    writer, receipt = admitted(tmp_path)
    ref, doc, _ = synthetic_complete(writer, receipt["job_id"])
    reader, binding = qualified_reader(writer, tmp_path)
    try:
        result = status(writer, read_runtime=reader)
    finally:
        cleanup(binding)
    assert result["receipt"]["job_id"] == receipt["job_id"]
    assert result["terminal_result_ref"] == ref
    assert "document" not in result
    assert "answer" not in str(result)


def test_unqualified_reader_refuses_instead_of_claiming_null_terminal_state(tmp_path):
    writer, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(writer, receipt["job_id"])
    with pytest.raises(CeoIngressError) as error:
        status(writer, read_runtime=writer)
    assert error.value.code == "backend_unavailable"


def test_status_rejects_wrong_reader_type_without_calling_it(tmp_path):
    writer, receipt = admitted(tmp_path)
    class Hostile:
        def __getattr__(self, name):
            pytest.fail("untrusted reader entered")
    with pytest.raises(CeoIngressError) as error:
        status(writer, read_runtime=Hostile())
    assert error.value.code == "backend_unavailable"


def test_queued_status_with_qualified_reader_still_has_no_result(tmp_path):
    writer, receipt = admitted(tmp_path)
    reader, binding = qualified_reader(writer, tmp_path)
    try:
        value = status(writer, read_runtime=reader)
    finally:
        cleanup(binding)
    assert value["terminal_result_ref"] is None


def test_submit_frame_does_not_use_status_reader(tmp_path):
    writer, receipt = admitted(tmp_path)
    class Hostile:
        def __getattr__(self, name):
            pytest.fail("submit crossed status-only read boundary")
    class Ground:
        def observe(self):
            from tests.test_vps_inference_service import GROUND
            return GROUND
    from tests.test_vps_inference_service import GROUND, service_request
    result = asyncio.run(ingress.handle_frame(
        {"schema": ingress.SUBMIT_SCHEMA, "request": service_request(),
         "observed_grounding": GROUND},
        runtime=writer, grounding_provider=Ground(), workspace_root=tmp_path,
        admission_guard=None, result_read_runtime=Hostile(),
    ))
    assert result["job_id"] == receipt["job_id"] and result["duplicate"] is True


def test_foreign_read_runtime_with_same_operation_and_job_number_is_refused(tmp_path):
    left_root, right_root = tmp_path/"left", tmp_path/"right"
    left_root.mkdir(); right_root.mkdir()
    left, left_receipt = admitted(left_root)
    right, right_receipt = admitted(right_root)
    assert left_receipt["job_id"] == right_receipt["job_id"]
    # The same operation and synthetic grounding can create the same fingerprint
    # in separate databases; this still cannot authorize a cross-source read.
    assert left_receipt["fingerprint"] == right_receipt["fingerprint"]
    synthetic_complete(right, right_receipt["job_id"])
    reader, binding = qualified_reader(right, right_root)
    try:
        with pytest.raises(CeoIngressError) as failure:
            status(left, read_runtime=reader)
        assert failure.value.code == "backend_unavailable"
    finally:
        cleanup(binding)


def test_status_receipt_is_acquired_with_its_reference_not_from_earlier_runtime(tmp_path,monkeypatch):
    writer, receipt = admitted(tmp_path)
    ref, _, _ = synthetic_complete(writer, receipt["job_id"])
    reader, binding = qualified_reader(writer, tmp_path)
    async def stale_writer_receipt(*args):
        # A pre-read writer receipt is from an old source generation.
        return dict(receipt, fingerprint="f"*64)
    monkeypatch.setattr(ingress.ingress, "_resolve_status_intent", stale_writer_receipt)
    try:
        observed = status(writer, read_runtime=reader)
    finally:
        cleanup(binding)
    assert observed["receipt"]["fingerprint"] == receipt["fingerprint"]
    assert observed["terminal_result_ref"] == ref


def test_queued_status_with_bound_owner_returns_original_receipt_without_writer_read(tmp_path,monkeypatch):
    writer, receipt = admitted(tmp_path)
    reader, binding = qualified_reader(writer, tmp_path)
    async def stale_writer_receipt(*args):
        raise AssertionError("separate original Runtime receipt lookup is forbidden")
    monkeypatch.setattr(ingress.ingress, "_resolve_status_intent", stale_writer_receipt)
    try:
        observed = status(writer, read_runtime=reader)
    finally:
        cleanup(binding)
    assert observed["receipt"]["fingerprint"] == receipt["fingerprint"]
    assert observed["terminal_result_ref"] is None


def test_direct_read_cannot_cross_runtime_sources_even_when_job_and_request_match(tmp_path):
    from control_plane.executive_inference_ingress import DIRECT_RESULT_SCHEMA
    from control_plane.executive_ceo_ingress import CeoIngressError
    left_root=tmp_path/"left";right_root=tmp_path/"right"
    left_root.mkdir();right_root.mkdir()
    writer,receipt=admitted(left_root)
    other,foreign=admitted(right_root)
    assert receipt["job_id"]==foreign["job_id"]
    assert receipt["fingerprint"]==foreign["fingerprint"]
    ref,_,_=synthetic_complete(other,foreign["job_id"])
    reader,binding=qualified_reader(other,right_root)
    class Grounding:
        def observe(self):return {}
    try:
        with pytest.raises(CeoIngressError) as raised:
            asyncio.run(ingress.handle_frame({
                "schema":DIRECT_RESULT_SCHEMA,"operation_key":OP,"reference":ref},
                runtime=writer,grounding_provider=Grounding(),workspace_root=left_root,
                admission_guard=None,result_read_runtime=reader))
        assert raised.value.code=="backend_unavailable"
    finally:cleanup(binding)


def test_direct_read_cannot_use_operation_present_only_in_foreign_reader(tmp_path):
    from control_plane.executive_inference_ingress import DIRECT_RESULT_SCHEMA
    from control_plane.executive_ceo_ingress import CeoIngressError
    left_root=tmp_path/"left";right_root=tmp_path/"right"
    left_root.mkdir();right_root.mkdir()
    from control_plane.executive_runtime import Runtime
    writer=Runtime.at(left_root/"runtime")
    other,foreign=admitted(right_root)
    ref,_,_=synthetic_complete(other,foreign["job_id"])
    reader,binding=qualified_reader(other,right_root)
    class Grounding:
        def observe(self):return {}
    try:
        with pytest.raises(CeoIngressError) as raised:
            asyncio.run(ingress.handle_frame({
                "schema":DIRECT_RESULT_SCHEMA,"operation_key":OP,"reference":ref},
                runtime=writer,grounding_provider=Grounding(),workspace_root=left_root,
                admission_guard=None,result_read_runtime=reader))
        assert raised.value.code=="backend_unavailable"
    finally:cleanup(binding)
