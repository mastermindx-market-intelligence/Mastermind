"""Canonical live issuer and terminal child selection, without an acceptance verdict."""

import pytest

from control_plane.executive_runtime import StateConflict


def live_programme(directory, monkeypatch):
    from tests.test_product_acceptance_request_owner import programme

    runtime, requester, binding, target, basis = programme(directory, monkeypatch)
    return (
        runtime,
        requester._test_root,
        requester._test_issuer_dispatch.attempt,
        runtime.attempts.get_attempt(target.current_attempt_id),
        requester._test_review_dispatch.attempt,
    )


def select(runtime, issuer, subject_id):
    with runtime.observe_bounded_read() as observation:
        selected = observation.read_product_acceptance_subject_bounded(
            issuer_job_id=issuer.job_id,
            issuer_attempt_id=issuer.attempt_id,
            issuer_worker_id=issuer.worker_id,
            subject_job_id=subject_id,
        )
    return selected, observation.receipt


def test_actual_live_dependent_child_selects_two_terminal_prerequisite_results_without_writes(
    tmp_path, monkeypatch
):
    runtime, root, issuer, subject, review = live_programme(tmp_path, monkeypatch)
    before = runtime.events.list_events(aggregate_type="job", aggregate_id=root.job_id)
    selected, receipt = select(runtime, issuer, subject.job_id)
    assert selected.root_job_id == root.job_id
    assert selected.issuer_attempt_id == issuer.attempt_id
    assert selected.issuer_job_id != selected.root_job_id
    assert len(selected.dependency_manifest_digest) == 64
    assert selected.subject.attempt_id == subject.attempt_id
    assert selected.reviewer.attempt_id == review.attempt_id
    assert selected.subject.completion.job.status.value == "COMPLETED"
    assert selected.reviewer.completion.job.status.value == "COMPLETED"
    assert selected.root_objective == root.objective
    assert "accepted" not in selected.__dict__
    assert receipt.before == receipt.after
    assert (
        runtime.events.list_events(aggregate_type="job", aggregate_id=root.job_id)
        == before
    )


def test_terminal_reviewer_cannot_be_recast_as_live_request_issuer(
    tmp_path, monkeypatch
):
    runtime, root, issuer, subject, review = live_programme(tmp_path, monkeypatch)
    with pytest.raises(StateConflict):
        select(runtime, review, subject.job_id)


def test_live_issuer_cannot_select_foreign_root_subject(tmp_path, monkeypatch):
    runtime, root, issuer, subject, review = live_programme(tmp_path, monkeypatch)
    other = runtime.jobs.create_job(
        "Foreign completed object", requested_authorities=["READ"]
    )
    with pytest.raises(StateConflict):
        select(runtime, issuer, other.job_id)


def test_wrong_live_attempt_or_worker_cannot_select_results(tmp_path, monkeypatch):
    from dataclasses import replace

    runtime, root, issuer, subject, review = live_programme(tmp_path, monkeypatch)
    for changed in (
        replace(issuer, attempt_id=subject.attempt_id),
        replace(issuer, worker_id="foreign-worker"),
    ):
        with pytest.raises(StateConflict):
            select(runtime, changed, subject.job_id)


def test_expired_live_issuer_cannot_select_results(tmp_path, monkeypatch):
    runtime, root, issuer, subject, review = live_programme(tmp_path, monkeypatch)
    with runtime.store.transaction() as connection:
        connection.execute(
            "UPDATE attempts SET lease_expires_at_ms=1 WHERE attempt_id=?",
            (issuer.attempt_id,),
        )
    with pytest.raises(StateConflict):
        select(runtime, issuer, subject.job_id)


def test_selection_remains_a_single_bounded_observation(tmp_path, monkeypatch):
    runtime, root, issuer, subject, review = live_programme(tmp_path, monkeypatch)
    with runtime.observe_bounded_read() as observation:
        observation.read_product_acceptance_subject_bounded(
            issuer_job_id=issuer.job_id,
            issuer_attempt_id=issuer.attempt_id,
            issuer_worker_id=issuer.worker_id,
            subject_job_id=subject.job_id,
        )
        with pytest.raises(StateConflict):
            observation.read_role_result_bounded(
                root.job_id,
                subject.job_id,
                expected_attempt_id=subject.attempt_id,
                expected_result_envelope_digest="0" * 64,
            )
    with pytest.raises(StateConflict):
        observation.receipt


def test_programme_root_cannot_request_a_ruling_from_its_own_coo_principal(
    tmp_path, monkeypatch
):
    from dataclasses import replace

    runtime, root, issuer, subject, review = live_programme(tmp_path, monkeypatch)
    with pytest.raises(StateConflict, match="live commissioned child issuer"):
        select(runtime, replace(issuer, job_id=root.job_id), subject.job_id)


def test_same_programme_sibling_is_not_a_commissioned_prerequisite(
    tmp_path, monkeypatch
):
    from tests.test_product_acceptance_request_owner import programme

    runtime, requester, binding, target, basis = programme(tmp_path, monkeypatch)
    with pytest.raises(StateConflict, match="accepted commissioned prerequisite"):
        select(
            runtime,
            requester._test_issuer_dispatch.attempt,
            requester._test_sibling.job_id,
        )
