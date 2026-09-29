"""Focused B7 Runtime admission, fence and closing foundation tests."""

from __future__ import annotations

import copy
import hashlib
import sqlite3

import pytest

from control_plane import executive_release_contract as rc
from control_plane import executive_runtime as er
from tests.test_executive_release_admission_read import (
    _append_admission_event,
    _build_wrapper_with_sequence,
    _hex,
    _make_preconditions,
    _principal_digest,
    make_approval,
)
from tests.test_executive_release_contract import (
    prestart_fixture, terminal_fixture,
)


def _canonical(value):
    return rc.canonical_release_bytes(value)


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _context_preconditions(approval):
    return _make_preconditions(
        approval=approval,
        admission_contract_digest=_hex(32),
        approval_evidence_digest=_digest(approval),
    )


def _admit(store, approval, *, deadline=300_000, root=_hex(30)):
    store.now_ms = lambda: 2_000
    preconditions = _context_preconditions(approval)
    registry = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        approval_context = er._release_context_for_test(
            store, connection, sealed_approval=approval
        )
        registry.record_approval(
            connection=connection,
            sealed_approval=approval,
            trusted_context=approval_context,
        )
        admission_context = (
            er.ReleaseMaintenanceRegistry._release_admission_context_for_test(
                store,
                connection,
                approval=approval,
                preconditions=preconditions,
                target_observation_digest=_hex(31),
                prepared_deadline_ms=deadline,
                root_qualification_digest=root,
            )
        )
        return registry.record_admission(
            connection=connection,
            sealed_approval=approval,
            request_fingerprint=rc.request_fingerprint_for(approval),
            preconditions=preconditions,
            target_observation_digest=_hex(31),
            trusted_context=admission_context,
        )


def _terminal_fixture(approval, state="SUCCEEDED"):
    _, _, status = _terminal_parts(approval, state)
    return status


def _terminal_parts(approval, state):
    request_fingerprint = rc.request_fingerprint_for(approval)
    preconditions = _context_preconditions(approval)
    admission = {
        "schema": "mastermind.executive_release_admission/v1",
        "operation_key": approval["operation_key"],
        "approved_transition_ref": approval["approved_transition_ref"],
        "target_ref": approval["target_ref"],
        "owner_installation_id": approval["owner_installation_id"],
        "boot_id": preconditions["boot_id"],
        "request_fingerprint": request_fingerprint,
        "effective_grant_digest": approval["effective_grant_digest"],
        "maintenance_sequence": 2,
        "admission_event_command_id": "p4-admit:" + approval["request_ref"],
        "target_observation_digest": _hex(31),
        "admission_contract_digest": preconditions["admission_contract_digest"],
    }
    return approval, {
        "schema": "mastermind.executive_release_terminal_status/v1",
        "state": state,
    }


def test_record_admission_persists_owner_sequence_and_global_unresolved(tmp_path):
    store = er.RuntimeStore(tmp_path)
    approval = make_approval()
    admission = _admit(store, approval)
    assert admission["maintenance_sequence"] == 2
    with store.read() as connection:
        unresolved = er.ReleaseMaintenanceRegistry(store).read_unresolved_admission(connection)
    assert unresolved is not None
    assert rc.canonical_release_bytes(unresolved["admission"]) == _canonical(admission)
    assert unresolved["root_qualification_digest"] == _hex(30)


def test_second_admission_refuses_while_first_unresolved(tmp_path):
    store = er.RuntimeStore(tmp_path)
    first = make_approval()
    second = make_approval(op="p4-b7-second")
    _admit(store, first)
    with pytest.raises(er.ReleaseMaintenanceError):
        _admit(store, second)


def test_expired_prepared_deadline_refuses(tmp_path):
    store = er.RuntimeStore(tmp_path)
    approval = make_approval()
    with pytest.raises(er.ReleaseMaintenanceError):
        _admit(store, approval, deadline=1)


def _admit_contract_vector(store):
    """One real source-only admission against the independent #1084 vectors."""
    store.now_ms = lambda: 2_000
    approval, reservation, _, cancellation = prestart_fixture()
    registry = er.ReleaseMaintenanceRegistry(store)
    with store.transaction() as connection:
        registry.record_approval(
            connection, sealed_approval=approval,
            trusted_context=er._release_context_for_test(
                store, connection, sealed_approval=approval
            ),
        )
        preconditions = reservation["preconditions"]
        context = registry._release_admission_context_for_test(
            store, connection, approval=approval, preconditions=preconditions,
            target_observation_digest=reservation["target_observation_digest"],
            prepared_deadline_ms=reservation["prepared_payload"]["expires_at_ms"],
            root_qualification_digest=_digest(reservation),
        )
        admission = registry.record_admission(
            connection, sealed_approval=approval,
            request_fingerprint=rc.request_fingerprint_for(approval),
            preconditions=preconditions,
            target_observation_digest=reservation["target_observation_digest"],
            trusted_context=context,
        )
    cancellation["admission_digest"] = _digest(admission)
    _, status = terminal_fixture()
    status["admission"] = admission.to_dict()
    status["admission_digest"] = _digest(admission)
    status["terminal_receipt"]["admission_digest"] = _digest(admission)
    assert rc.validate_release_prestart_cancellation(
        cancellation, expected_approval=approval, expected_admission=admission,
        expected_reservation=reservation,
    )
    assert rc.validate_release_terminal_status(status, expected_approval=approval)
    return registry, approval, admission, reservation, cancellation, status


def test_terminal_closure_requires_original_admission_and_releases_once(tmp_path):
    store = er.RuntimeStore(tmp_path)
    registry, approval, admission, _, _, status = _admit_contract_vector(store)
    with store.transaction() as connection:
        context = registry._release_closing_context_for_test(
            store, connection, approval=approval, admission=admission,
            terminal_status=status, journal_observation_digest=_hex(64),
        )
        result = registry.record_terminal(
            connection, approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(approval),
            terminal_status=status, trusted_context=context,
        )
        assert result["state"] == "SUCCEEDED"
        assert registry.read_unresolved_admission(connection) is None
    with store.read() as connection:
        assert registry.read_unresolved_admission(connection) is None
    with store.transaction() as connection:
        context = registry._release_closing_context_for_test(
            store, connection, approval=approval, admission=admission,
            terminal_status=status, journal_observation_digest=_hex(64),
        )
        registry.record_terminal(
            connection, approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(approval),
            terminal_status=status, trusted_context=context,
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='EXECUTIVE_RELEASE_CLOSED'"
        ).fetchone()[0] == 1
    successor = _admit(store, make_approval(op="after-qualified-terminal"))
    assert successor["maintenance_sequence"] > admission["maintenance_sequence"]


def test_prestart_cancellation_is_distinct_and_releases_once(tmp_path):
    store = er.RuntimeStore(tmp_path)
    registry, approval, admission, reservation, cancellation, _ = _admit_contract_vector(store)
    with store.transaction() as connection:
        context = registry._release_cancellation_context_for_test(
            store, connection, approval=approval, admission=admission,
            reservation=reservation, cancellation=cancellation,
            journal_observation_digest=_hex(65),
        )
        result = registry.record_cancellation(
            connection, approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(approval),
            reservation=reservation, cancellation=cancellation,
            trusted_context=context,
        )
        assert result["reason"] == "PREPARED_TOKEN_EXPIRED"
        assert registry.read_unresolved_admission(connection) is None
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE event_type='EXECUTIVE_RELEASE_CLOSED'"
        ).fetchone()[0] == 0
    with store.read() as connection:
        assert registry.read_unresolved_admission(connection) is None
    successor = _admit(store, make_approval(op="after-qualified-cancellation"))
    assert successor["maintenance_sequence"] > admission["maintenance_sequence"]


def test_admission_and_claim_share_one_transactional_fence(tmp_path):
    store = er.RuntimeStore(tmp_path)
    store.now_ms = lambda: 2_000
    runtime = er.Runtime.from_store(store)
    runtime.workers.register_worker(
        "worker-01", provider="codex", account_label="one", worker_type="test"
    )
    job = runtime.jobs.create_job("queued during release")
    _admit(store, make_approval())
    with pytest.raises(er.StateConflict, match="release admission"):
        runtime.attempts.claim_job(job.job_id)
    assert runtime.attempts.list_attempts(job.job_id) == []

    other = er.RuntimeStore(tmp_path / "claim-first")
    other.now_ms = lambda: 2_000
    other_runtime = er.Runtime.from_store(other)
    other_runtime.workers.register_worker(
        "worker-01", provider="codex", account_label="one", worker_type="test"
    )
    other_job = other_runtime.jobs.create_job("claimed before admission")
    lease = other_runtime.attempts.claim_job(other_job.job_id)
    assert lease is not None
    with pytest.raises(er.ReleaseMaintenanceError, match="ACTIVE_ATTEMPT"):
        _admit(other, make_approval(op="claim-first-release"))


def test_closing_context_capability_and_connection_cannot_be_replayed(tmp_path):
    store = er.RuntimeStore(tmp_path)
    registry, approval, admission, _, _, status = _admit_contract_vector(store)
    with store.transaction() as connection:
        context = registry._release_closing_context_for_test(
            store, connection, approval=approval, admission=admission,
            terminal_status=status, journal_observation_digest=_hex(64),
        )
        stale = registry._release_closing_context_for_test(
            store, connection, approval=approval, admission=admission,
            terminal_status=status, journal_observation_digest=_hex(64),
        )
        object.__setattr__(context, "_capability", object())
        with pytest.raises(er.ReleaseMaintenanceError, match="CAPABILITY"):
            registry.record_terminal(
                connection, approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
                terminal_status=status, trusted_context=context,
            )
        assert registry.read_unresolved_admission(connection) is not None
    with store.transaction() as connection:
        with pytest.raises(er.ReleaseMaintenanceError, match="FOREIGN_CONNECTION"):
            registry.record_terminal(
                connection, approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
                terminal_status=status, trusted_context=stale,
            )


def test_mutated_closure_header_never_releases_fence(tmp_path):
    store = er.RuntimeStore(tmp_path)
    registry, approval, admission, _, _, status = _admit_contract_vector(store)
    with store.transaction() as connection:
        context = registry._release_closing_context_for_test(
            store, connection, approval=approval, admission=admission,
            terminal_status=status, journal_observation_digest=_hex(64),
        )
        registry.record_terminal(
            connection, approved_transition_ref=approval["approved_transition_ref"],
            request_fingerprint=rc.request_fingerprint_for(approval),
            terminal_status=status, trusted_context=context,
        )
    raw = sqlite3.connect(str(store.path))
    try:
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_update")
        raw.execute("DROP TRIGGER IF EXISTS events_are_immutable_delete")
        raw.execute(
            "UPDATE events SET command_id=? WHERE event_type='EXECUTIVE_RELEASE_CLOSED'",
            ("p4-close:req-" + "f" * 32,),
        )
        raw.commit()
    finally:
        raw.close()
    with store.read() as connection:
        with pytest.raises(er.ReleaseMaintenanceError):
            registry.read_unresolved_admission(connection)


def test_cancellation_reservation_drift_refuses_without_closing(tmp_path):
    store = er.RuntimeStore(tmp_path)
    registry, approval, admission, reservation, cancellation, _ = _admit_contract_vector(store)
    changed = copy.deepcopy(reservation)
    changed["prepared_token_digest"] = _hex(99)
    with store.transaction() as connection:
        context = registry._release_cancellation_context_for_test(
            store, connection, approval=approval, admission=admission,
            reservation=reservation, cancellation=cancellation,
            journal_observation_digest=_hex(65),
        )
        with pytest.raises((er.ReleaseMaintenanceError, rc.ReleaseContractError)):
            registry.record_cancellation(
                connection, approved_transition_ref=approval["approved_transition_ref"],
                request_fingerprint=rc.request_fingerprint_for(approval),
                reservation=changed, cancellation=cancellation,
                trusted_context=context,
            )
        assert registry.read_unresolved_admission(connection) is not None
