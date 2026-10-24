"""One joint Runtime selection for an associated Mission and role Result.

Budgets are cumulative. The receipt exists only after physical close.
"""
import pytest

from control_plane import executive_runtime as er
from tests.test_fabric_result_projection import (
    _bound_reader,
    _release,
    _select_bound,
    complete_all_severity_chain,
)


@pytest.fixture
def joint(tmp_path):
    writer, root, _work, review = complete_all_severity_chain(tmp_path / "runtime")
    keeper, namespace, binding, reader = _bound_reader(writer)
    try:
        snapshot, receipt = _select_bound(reader, root.job_id, review)
        yield {
            "writer": writer,
            "reader": reader,
            "namespace": namespace,
            "binding": binding,
            "root_id": root.job_id,
            "job_id": review.job.job_id,
            "attempt_id": review.attempt.attempt_id,
            "digest": review.result_digest,
            "separate_digest": snapshot.snapshot_digest if hasattr(snapshot, "snapshot_digest") else None,
            "separate_root_digest": None,
        }
    finally:
        _release(keeper, binding)


def _select(reader, root_id, job_id, attempt_id, digest):
    with reader.observe_bounded_read() as observation:
        material = observation.read_root_role_result_bounded(
            root_id, job_id, expected_attempt_id=attempt_id,
            expected_result_envelope_digest=digest,
        )
    return material, observation.receipt


def test_joint_selection_finalizes_same_receipt_after_close(joint):
    before = joint["namespace"].entries
    material, receipt = _select(
        joint["reader"], joint["root_id"], joint["job_id"], joint["attempt_id"], joint["digest"],
    )
    assert receipt.state == "SAME"
    assert receipt.before == receipt.after
    assert receipt.source_identity == material.observation_source_identity
    assert material.role_result.observation_source_identity == receipt.source_identity
    assert material.role_result.job_id == joint["job_id"]
    assert material.role_result.result_envelope_digest == joint["digest"]
    assert material.root.root_job_id == joint["root_id"]
    assert material.creation_event.event_type == "JOB_CREATED"
    assert material.creation_event.job_id == joint["root_id"]
    assert any(job.job_id == joint["job_id"] for job in material.root.jobs)
    assert joint["namespace"].entries == before + 1 == joint["namespace"].exits
    assert not joint["namespace"].active
    with joint["reader"].observe_bounded_read() as again:
        again.read_root_role_result_bounded(
            joint["root_id"], joint["job_id"], expected_attempt_id=joint["attempt_id"],
            expected_result_envelope_digest=joint["digest"],
        )
        with pytest.raises(er.StateConflict):
            again.read_role_result_bounded(
                joint["root_id"], joint["job_id"],
                expected_attempt_id=joint["attempt_id"],
                expected_result_envelope_digest=joint["digest"],
            )
    with pytest.raises(er.StateConflict):
        _ = again.receipt


def test_independent_observations_mint_distinct_identities(joint):
    first, left = _select(
        joint["reader"], joint["root_id"], joint["job_id"], joint["attempt_id"], joint["digest"],
    )
    second, right = _select(
        joint["reader"], joint["root_id"], joint["job_id"], joint["attempt_id"], joint["digest"],
    )
    assert left.state == right.state == "SAME"
    assert left.source_identity != right.source_identity
    assert first.observation_source_identity != second.observation_source_identity
    assert first.root.snapshot_digest == second.root.snapshot_digest


def test_root_snapshot_matches_standalone_root_read(joint):
    material, _receipt = _select(
        joint["reader"], joint["root_id"], joint["job_id"], joint["attempt_id"], joint["digest"],
    )
    with joint["reader"].observe_bounded_read() as observation:
        standalone = observation.read_job_root_bounded(joint["root_id"])
    assert material.root.snapshot_digest == standalone.snapshot_digest
    assert [job.job_id for job in material.root.jobs] == [job.job_id for job in standalone.jobs]
    assert [item.attempt_id for item in material.root.attempts] == [
        item.attempt_id for item in standalone.attempts
    ]


@pytest.mark.parametrize("field", ["digest", "attempt", "job", "root"])
def test_wrong_tuple_poisons_without_receipt(joint, field):
    root_id, job_id, attempt_id, digest = (
        joint["root_id"], joint["job_id"], joint["attempt_id"], joint["digest"],
    )
    if field == "digest":
        digest = "ab" * 32
    elif field == "attempt":
        attempt_id = "ATT-" + "ab" * 16
    elif field == "job":
        job_id = "JOB-999999"
    else:
        root_id = "JOB-999999"
    before = joint["namespace"].entries
    with pytest.raises((er.StateConflict, er.RuntimeReadUnavailable, er.PersistenceError)):
        with joint["reader"].observe_bounded_read() as failed:
            failed.read_root_role_result_bounded(
                root_id, job_id, expected_attempt_id=attempt_id,
                expected_result_envelope_digest=digest,
            )
    with pytest.raises(er.StateConflict):
        _ = failed.receipt
    assert joint["namespace"].entries == joint["namespace"].exits
    assert joint["namespace"].entries >= before
    assert not joint["namespace"].active


def test_cumulative_statement_budget_is_not_reset_between_phases(joint, monkeypatch):
    marks = {}
    original_root = er._accounted_root_snapshot
    original_result = er._bounded_role_result_material
    original_event = er._accounted_creation_event

    def root(loader, root_token):
        marks["loader"] = id(loader)
        value = original_root(loader, root_token)
        marks["after_root"] = loader._statements
        return value

    def result(loader, **kwargs):
        assert id(loader) == marks["loader"]
        marks["before_result"] = loader._statements
        value = original_result(loader, **kwargs)
        marks["after_result"] = loader._statements
        return value

    def event(observation, loader):
        assert id(loader) == marks["loader"]
        marks["before_event"] = loader._statements
        value = original_event(observation, loader)
        marks["after_event"] = loader._statements
        return value

    monkeypatch.setattr(er, "_accounted_root_snapshot", root)
    monkeypatch.setattr(er, "_bounded_role_result_material", result)
    monkeypatch.setattr(er, "_accounted_creation_event", event)
    _select(joint["reader"], joint["root_id"], joint["job_id"], joint["attempt_id"], joint["digest"])
    monkeypatch.undo()
    root_phase = marks["after_root"]
    result_phase = marks["after_result"] - marks["before_result"]
    event_phase = marks["after_event"] - marks["before_event"]
    assert marks["before_result"] == marks["after_root"]
    assert marks["before_event"] == marks["after_result"]
    assert min(root_phase, result_phase, event_phase) > 0
    combined = marks["after_event"]
    ceiling = max(root_phase, result_phase, event_phase)
    assert combined > ceiling
    monkeypatch.setattr(er, "BOUNDED_ROLE_RESULT_MAX_STATEMENTS", ceiling)
    before = joint["namespace"].entries
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        with joint["reader"].observe_bounded_read() as observation:
            observation.read_root_role_result_bounded(
                joint["root_id"], joint["job_id"],
                expected_attempt_id=joint["attempt_id"],
                expected_result_envelope_digest=joint["digest"],
            )
    with pytest.raises(er.StateConflict):
        _ = observation.receipt
    assert joint["namespace"].exits == joint["namespace"].entries
    assert joint["namespace"].entries >= before
    assert not joint["namespace"].active


def test_uncertain_close_refuses_receipt(joint, monkeypatch):
    original = er.RuntimeStore._close_read_connection

    def close(store, connection):
        original(store, connection)
        if store is joint["reader"].store:
            raise er.RuntimeReadUnavailable("fixture close uncertainty")

    monkeypatch.setattr(er.RuntimeStore, "_close_read_connection", close)
    with pytest.raises(er.RuntimeReadUnavailable):
        _select(joint["reader"], joint["root_id"], joint["job_id"], joint["attempt_id"], joint["digest"])
    assert not joint["namespace"].active
