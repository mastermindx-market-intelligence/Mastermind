"""Actual bounded Runtime workstream joins; namespace custody is fixture-only.

No provider, process, auth enrollment or installed source is used. The root
and its immutable creation provenance are created by the actual intent owner.
"""
from control_plane.ceo_intent import submit_intent
from control_plane.executive_runtime import Runtime
from control_plane.fabric_job_view import read_fabric_view_v3_from_runtime
from tests.test_executive_os_phase1fc import _v2_intent
from tests.test_fabric_result_projection import _bound_reader, _release


def _observe(tmp_path, *, source_work_ref, expected_work_ref):
    writer = Runtime.at(tmp_path / "runtime")
    extra = {} if source_work_ref is None else {"workstream": source_work_ref}
    created = submit_intent(writer, _v2_intent(**extra))
    keeper, _namespace, binding, reader = _bound_reader(writer)
    try:
        return read_fabric_view_v3_from_runtime(
            reader, created["job_id"], armed={},
            runtime_identity={"db_present": True},
            expected_work_ref=expected_work_ref,
        )
    finally:
        _release(keeper, binding)


def test_same_observation_proves_actual_creation_workstream(tmp_path):
    observed = _observe(tmp_path, source_work_ref="WS:RETAINED",
                        expected_work_ref="WS:RETAINED")
    assert observed["result_refs"]["generation"]["state"] == "SAME"
    assert observed["result_refs"]["availability"] == "AVAILABLE"


def test_other_workstream_cannot_use_an_actual_root(tmp_path):
    observed = _observe(tmp_path, source_work_ref="WS:RETAINED",
                        expected_work_ref="WS:OTHER")
    assert observed["result_refs"]["generation"]["state"] == "UNKNOWN"
    assert observed["result_refs"]["refs"] == []
    assert observed["result_refs"]["availability"] != "AVAILABLE"


def test_missing_creation_workstream_is_not_inferred_from_the_request(tmp_path):
    observed = _observe(tmp_path, source_work_ref=None,
                        expected_work_ref="WS:RETAINED")
    assert observed["result_refs"]["generation"]["state"] == "UNKNOWN"
    assert observed["result_refs"]["refs"] == []


def test_existing_unselected_observation_keeps_its_historical_contract(tmp_path):
    observed = _observe(tmp_path, source_work_ref=None, expected_work_ref=None)
    assert observed["result_refs"]["generation"]["state"] == "SAME"
