"""Disposable real Runtime reads; no browser, broker, provider or installed run.

Paid launch observations reuse the existing inert fixture DATA. Principal roots
are created through the real admission sink, never by promoting a CEO root or
rewriting its immutable provenance for the successful cases.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import sqlite3

import pytest

from control_plane import executive_runtime as er
from control_plane import workspace_paid_fabric_runtime as owner
from control_plane.coo_principal_envelope import (
    PrincipalAdmissionContext,
    derive_principal_orchestration_envelope,
)
from tests import test_paid_runtime_owner_integration as paid_fixtures
from tests.test_executive_runtime_bounded_read import ObservationNamespace


CONTEXT = PrincipalAdmissionContext(
    "WS:PAID-UNIT", "a" * 64, "authority:paid-browser-test", "b" * 64
)


def _principal_submission(runtime, intent, **kwargs):
    bundle = derive_principal_orchestration_envelope(
        {"operation_key": "paid-browser-test", "objective": intent["objective"],
         "department": intent["department"], "priority": intent["priority"],
         "workstream": CONTEXT.work_ref, "business_impact": intent["business_impact"]},
        context=CONTEXT, grounding=intent["grounding"],
    )
    def admitted(candidate):
        assert candidate == bundle
    root = runtime.jobs.create_principal_orchestration_root(
        bundle, principal_admission_guard=admitted, **kwargs
    )
    # The principal sink derives its own worktree. Populate that actual test
    # worktree from the fixture's real Control Git source at the same commit.
    shutil.copytree(intent["execution_contract"]["worktree"], root.worktree)
    return {"job_id": root.job_id}


@pytest.fixture
def paid(tmp_path, monkeypatch):
    monkeypatch.setattr(paid_fixtures, "submit_intent", _principal_submission)
    states = []
    def make(*, completed=False, claimed_only=False):
        directory = tmp_path / f"runtime-{len(states)}"
        directory.mkdir(mode=0o700)
        if claimed_only:
            runtime, root, job, claim, *_ = paid_fixtures.paid_cycle_claim(directory)
            state = dict(runtime=runtime, root=root, job=job, running=claim.attempt, claim=claim)
        else:
            state = (paid_fixtures.paid_completed(directory) if completed
                     else paid_fixtures.paid_running(directory))
        writer = state["runtime"]
        # Retain the ordinary WAL namespace while observation owns its private
        # connection, just as the existing bounded Runtime fixture does.
        keeper = sqlite3.connect(writer.store.path, isolation_level=None)
        keeper.execute("SELECT 1 FROM jobs").fetchone()
        namespace = ObservationNamespace(writer.store.path)
        state["reader"] = er.Runtime.at(directory, create=False,
            read_binding=er.RuntimeReadBinding(namespace))
        state["namespace"] = namespace
        state["keeper"] = keeper
        states.append(state)
        return state
    yield make
    for state in states:
        state["keeper"].close()
        namespace = state["namespace"]
        assert namespace.entries == namespace.exits and not namespace.active


def _select(state, **overrides):
    arguments = dataclasses.asdict(CONTEXT) | overrides
    with state["reader"].observe_bounded_read() as read:
        snapshot = read.read_paid_fabric_runs_bounded(state["root"].job_id, **arguments)
        with pytest.raises(er.StateConflict, match="not finalized"):
            _ = read.receipt
    receipt = read.receipt
    assert receipt.state == "SAME"
    assert receipt.source_identity == snapshot.observation_source_identity
    return snapshot, receipt


def test_actual_principal_job_attempt_launch_binding_and_final_receipt(paid):
    state = paid()
    before = (len(state["runtime"].jobs.list_jobs()),
              len(state["runtime"].events.list_events()))
    snapshot, receipt = _select(state)
    assert snapshot.limit == 8 and snapshot.selected_count == 1
    assert snapshot.partial is snapshot.truncated is False
    assert snapshot.unlaunched_count == 0
    assert len(snapshot.runs) == 1
    run = snapshot.runs[0]
    assert run.run_id == run.attempt_id == state["running"].attempt_id
    assert run.job_id == state["job"].job_id
    assert run.root_id == run.parent_run_id == state["root"].job_id
    assert run.launch_request == state["payload"]
    assert run.physical_binding == state["payload"]["paid_physical_binding"]
    assert run.process_ref == state["ref"].to_dict()
    assert run.process_ref_sha256 == er.orchestration_digest(state["ref"].to_dict())
    assert run.physical_binding_sha256 == state["payload"]["physical_binding_sha256"]
    assert run.remote_launch_identity_sha256 == er.orchestration_digest(state["identity"])
    assert run.effective_grant_digest == state["running"].effective_grant_digest
    assert run.execution_principal_snapshot_digest == state["running"].execution_principal_snapshot_digest
    assert state["spec"].prompt not in repr(snapshot)
    assert not hasattr(snapshot, "to_dict") and not hasattr(run, "to_dict")
    assert before == (len(state["runtime"].jobs.list_jobs()),
                      len(state["runtime"].events.list_events()))
    # Detached data does not alter retained evidence or a later read generation.
    run.launch_request["binding"]["root_id"] = "tampered-detached-copy"
    second, second_receipt = _select(state)
    assert second.snapshot_digest == snapshot.snapshot_digest
    assert second.runs[0].launch_request == state["payload"]
    assert second_receipt.source_identity != receipt.source_identity


@pytest.mark.parametrize("field,value", [
    ("work_ref", "WS:OTHER"),
    ("principal_binding_digest", "c" * 64),
    ("mission_authority_ref", "authority:other"),
    ("authority_generation_digest", "d" * 64),
])
def test_foreign_principal_or_revoked_generation_cannot_select_launch(paid, monkeypatch, field, value):
    state = paid()
    monkeypatch.setattr(owner, "_validated_paid_launch_evidence",
        lambda *a, **kw: pytest.fail("must reject before touching launch material"))
    with pytest.raises(er.RuntimeReadUnavailable):
        _select(state, **{field: value})


def test_ordinary_ceo_root_cannot_be_adopted_from_workstream_label(tmp_path, monkeypatch):
    state = paid_fixtures.paid_running(tmp_path)
    writer = state["runtime"]
    keeper = sqlite3.connect(writer.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    try:
        state["reader"] = er.Runtime.at(tmp_path, create=False,
            read_binding=er.RuntimeReadBinding(ObservationNamespace(writer.store.path)))
        monkeypatch.setattr(owner, "_validated_paid_launch_evidence",
            lambda *a, **kw: pytest.fail("ordinary CEO source must not reach native material"))
        with state["reader"].observe_bounded_read() as read:
            with pytest.raises(owner.PaidFabricRootNotBound) as omitted:
                read.read_paid_fabric_runs_bounded(state["root"].job_id, **dataclasses.asdict(CONTEXT))
            with pytest.raises(er.StateConflict, match="not finalized"):
                _ = read.receipt
        assert read.receipt.state == "SAME"
        assert read.receipt.source_identity == omitted.value.observation_source_identity
        assert omitted.value.root_job_id == state["root"].job_id
        assert len(omitted.value.root_creation_digest) == len(omitted.value.snapshot_digest) == 64
    finally:
        keeper.close()


@pytest.mark.parametrize("fault", ["schema", "fingerprint", "actor", "foreign_workstream", "unexpected_field"])
def test_malformed_or_foreign_ordinary_root_is_not_an_omission(tmp_path, monkeypatch, fault):
    from tests.test_runtime_root_origin_bounded import corrupt_creation

    state = paid_fixtures.paid_running(tmp_path)
    writer = state["runtime"]
    values = {"schema": ("schema", "unsupported"), "fingerprint": ("fingerprint", "f" * 64),
        "actor": ("actor", "bad actor"), "foreign_workstream": ("workstream", "WS:FOREIGN"),
        "unexpected_field": ("principal_binding_digest", CONTEXT.principal_binding_digest)}
    key, value = values[fault]
    corrupt_creation(writer, state["root"].job_id,
        payload=lambda body: body["provenance"].update({key: value}))
    keeper = sqlite3.connect(writer.store.path, isolation_level=None)
    keeper.execute("SELECT 1 FROM jobs").fetchone()
    try:
        reader = er.Runtime.at(tmp_path, create=False,
            read_binding=er.RuntimeReadBinding(ObservationNamespace(writer.store.path)))
        with pytest.raises((er.StateConflict, er.RuntimeReadUnavailable)) as refused:
            with reader.observe_bounded_read() as read:
                read.read_paid_fabric_runs_bounded(state["root"].job_id, **dataclasses.asdict(CONTEXT))
        assert not isinstance(refused.value, owner.PaidFabricRootNotBound)
        with pytest.raises(er.StateConflict, match="not finalized"):
            _ = read.receipt
    finally:
        keeper.close()


def test_terminal_retained_attempt_does_not_require_live_lease_or_capacity(paid):
    state = paid(completed=True)
    attempt = state["runtime"].attempts.get_attempt(state["running"].attempt_id)
    assert attempt.status.value == "COMPLETED"
    snapshot, _ = _select(state)
    assert snapshot.runs[0].attempt_id == attempt.attempt_id
    assert snapshot.runs[0].execution_principal_snapshot_digest == attempt.execution_principal_snapshot_digest


def test_retained_launch_does_not_require_unexpired_execution_lease(paid):
    state = paid()
    with state["runtime"].store.transaction() as connection:
        connection.execute("UPDATE attempts SET lease_expires_at_ms=1 WHERE attempt_id=?",
            (state["running"].attempt_id,))
    snapshot, _ = _select(state)
    assert snapshot.runs[0].attempt_id == state["running"].attempt_id


def test_not_yet_pinned_claim_is_partial_without_a_guessed_run(paid):
    state = paid(claimed_only=True)
    snapshot, _ = _select(state)
    assert snapshot.runs == ()
    assert snapshot.partial is True and snapshot.truncated is False
    assert snapshot.selected_count == snapshot.unlaunched_count == 1


def test_missing_material_cannot_hide_original_pin_as_unlaunched(paid):
    state = paid(claimed_only=True)
    attempt, claim = state["running"], state["claim"]
    state["runtime"].attempts.pin_remote_launch_identity(attempt.attempt_id,
        fence_generation=attempt.fence_generation, lease_token=claim.lease_token,
        expected_version=attempt.version, identity_digest="e" * 64)
    with pytest.raises(er.StateConflict):
        _select(state)
    # Disposable corruption leaves the immutable original pin Event intact.
    # An empty metadata object must not suppress that retained unknown run.
    with state["runtime"].store.transaction() as connection:
        connection.execute("UPDATE attempts SET launch_metadata_json='{}' WHERE attempt_id=?",
            (attempt.attempt_id,))
    # A failed bound observation invalidates that capability. Reacquire through
    # its owner for this independent corruption case, preserving that behavior.
    state["reader"] = er.Runtime.at(state["runtime"].store.root, create=False,
        read_binding=er.RuntimeReadBinding(state["namespace"]))
    with pytest.raises(er.RuntimeReadUnavailable, match="original launch material"):
        _select(state)


def test_exact_adoption_chain_is_allowed_and_changes_read_generation(paid):
    state = paid()
    first, _ = _select(state)
    original = state["running"]
    adopted = state["runtime"].attempts.adopt_attempt(original.attempt_id,
        expected_fence_generation=original.fence_generation, lease_owner="browser-fixture-successor")
    second, _ = _select(state)
    assert second.runs[0].fence_generation == adopted.attempt.fence_generation
    assert second.runs[0].remote_launch_identity_sha256 == first.runs[0].remote_launch_identity_sha256
    assert second.snapshot_digest != first.snapshot_digest
    # Disposable DB corruption: no corresponding adoption event authorizes this fence.
    with state["runtime"].store.transaction() as connection:
        connection.execute("UPDATE attempts SET fence_generation=fence_generation+1 WHERE attempt_id=?",
            (original.attempt_id,))
    with pytest.raises(er.StateConflict, match="adoption history"):
        _select(state)


@pytest.mark.parametrize("fault", ["identity", "physical", "unsealed", "lost_reply"])
def test_launch_evidence_drift_or_incomplete_original_refuses_without_receipt(paid, monkeypatch, fault):
    with monkeypatch.context() as pause:
        if fault == "unsealed":
            mark_running = er.AttemptRegistry.mark_running
            def stop_before_paid_seal(registry, attempt_id, **kwargs):
                attempt = registry.get_attempt(attempt_id)
                if attempt.worker_id == "paid-subject":
                    return attempt
                return mark_running(registry, attempt_id, **kwargs)
            # Retain the real post-record_process, pre-mark_running state.
            # No immutable snapshot/event is erased to make this condition.
            pause.setattr(er.AttemptRegistry, "mark_running", stop_before_paid_seal)
        state = paid()
    writer, attempt_id = state["runtime"], state["running"].attempt_id
    with writer.store.transaction() as connection:
        row = connection.execute("SELECT launch_metadata_json FROM attempts WHERE attempt_id=?",
            (attempt_id,)).fetchone()
        metadata = json.loads(row[0])
        if fault == "identity":
            metadata["paid_launch_identity"]["request"]["binding"]["attempt_id"] = "ATT-foreign"
        elif fault == "physical":
            metadata["paid_launch_identity"]["physical_binding_sha256"] = "0" * 64
        elif fault == "lost_reply":
            metadata = {er.REMOTE_LAUNCH_IDENTITY_KEY: metadata[er.REMOTE_LAUNCH_IDENTITY_KEY]}
        else:
            assert state["running"].execution_principal_snapshot is None
        connection.execute("UPDATE attempts SET launch_metadata_json=? WHERE attempt_id=?",
            (er._json_dumps(metadata), attempt_id))
    with pytest.raises(er.StateConflict):
        with state["reader"].observe_bounded_read() as read:
            read.read_paid_fabric_runs_bounded(state["root"].job_id, **dataclasses.asdict(CONTEXT))
    with pytest.raises(er.StateConflict, match="not finalized"):
        _ = read.receipt


def test_selection_uses_sql_sentinel_and_existing_cumulative_budget(paid, monkeypatch):
    state = paid()
    traces = []
    connect = er.sqlite3.connect
    def traced(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(traces.append)
        return connection
    monkeypatch.setattr(er.sqlite3, "connect", traced)
    monkeypatch.setattr(er.JobRegistry, "list_jobs", lambda *a, **kw: pytest.fail("unbounded jobs"))
    monkeypatch.setattr(er.AttemptRegistry, "list_attempts", lambda *a, **kw: pytest.fail("unbounded attempts"))
    _select(state)
    selectors = [" ".join(query.split()) for query in traces if "SELECT a.attempt_id FROM jobs" in query]
    assert selectors and all("LIMIT 9" in query for query in selectors)
    assert not any(query.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")) for query in traces)
    monkeypatch.setattr(er, "BOUNDED_ROLE_RESULT_MAX_STATEMENTS", 1)
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        _select(state)


def test_vm_exhaustion_aborts_without_finalized_receipt(paid, monkeypatch):
    state = paid()
    guard = er._RuntimeReadProgressGuard
    monkeypatch.setattr(er, "_RuntimeReadProgressGuard", lambda: guard(limit=5))
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        with state["reader"].observe_bounded_read() as read:
            read.read_paid_fabric_runs_bounded(state["root"].job_id, **dataclasses.asdict(CONTEXT))
    with pytest.raises(er.StateConflict, match="not finalized"):
        _ = read.receipt


def test_concurrent_runtime_write_marks_conflict_not_same(paid):
    state = paid()
    with state["reader"].observe_bounded_read() as read:
        snapshot = read.read_paid_fabric_runs_bounded(state["root"].job_id,
            **dataclasses.asdict(CONTEXT))
        state["runtime"].jobs.create_job("Concurrent unrelated fixture mutation")
    assert read.receipt.state == "CONFLICT"
    assert read.receipt.source_identity == snapshot.observation_source_identity


def test_unbound_namespace_cannot_mint_same_read_receipt(paid):
    state = paid()
    state["reader"] = er.Runtime.at(state["runtime"].store.root, create=False)
    with state["reader"].observe_bounded_read() as read:
        snapshot = read.read_paid_fabric_runs_bounded(state["root"].job_id,
            **dataclasses.asdict(CONTEXT))
    assert read.receipt.state == "UNKNOWN"
    assert snapshot.observation_source_identity is None
