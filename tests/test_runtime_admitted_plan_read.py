"""Real Runtime admitted-plan reads; fixtures never contact a provider or host."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import FrozenInstanceError, fields
import json
import sqlite3

import pytest

from control_plane import executive_runtime as er
from control_plane.executive_orchestration_result import canonical_digest
from tests.test_executive_runtime_bounded_read import ObservationNamespace
from tests.test_executive_runtime_bounded_role_result import _fill_events
from tests.test_executive_terminal_return import _completed_planner
from tests.test_interactive_tx5_runtime import _started_interactive, _sealed_plan_result


@pytest.fixture
def completed(tmp_path):
    runtime, planner, attempt = _completed_planner(tmp_path)
    return runtime, planner.root_job_id, planner, attempt


def _active(tmp_path, *, admit=True):
    runtime, root, planner, dispatch, epoch, generation = _started_interactive(tmp_path)
    _sealed_plan_result(runtime, root, planner, dispatch, epoch, generation)
    if admit:
        runtime.jobs.admit_cycle_plan(root.job_id, command_id=(
            f"coo-cycle:{root.job_id}:admit-plan:{dispatch.attempt.attempt_id}"))
    return runtime, root.job_id, planner, dispatch.attempt


def _read(runtime, root_id):
    with runtime.observe_bounded_read() as observation:
        snapshot = observation.read_admitted_plan_bounded(root_id)
    return snapshot, observation


@contextmanager
def _bound(runtime):
    keeper = sqlite3.connect(runtime.store.path, isolation_level=None)
    keeper.execute('SELECT 1 FROM jobs').fetchone()
    namespace = ObservationNamespace(runtime.store.path)
    binding = er.RuntimeReadBinding(namespace)
    reader = er.Runtime.at(runtime.store.path.parents[2], create=False, read_binding=binding)
    try:
        yield reader, namespace, binding
    finally:
        keeper.close()
        if binding._unclosed_connection is not None:
            sqlite3.Connection.close(binding._unclosed_connection)
        if binding._retained_namespace is not None:
            binding._retained_namespace.close()


def _corrupt(runtime, mutate):
    """Offline adversarial fixture: restore all exact triggers after corruption."""
    with sqlite3.connect(runtime.store.path) as connection:
        connection.row_factory = sqlite3.Row
        ddl = connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
        for row in ddl:
            connection.execute('DROP TRIGGER "' + row['name'].replace('"', '""') + '"')
        mutate(connection)
        for row in ddl:
            connection.execute(row['sql'])


def _duplicate_event(connection, event_type, root_id):
    if event_type == 'COO_PLAN_ADMITTED':
        # Deliberately corrupt the private fixture past its uniqueness index.
        connection.execute('DROP INDEX events_one_coo_plan_admission_per_root')
    row = dict(connection.execute('SELECT * FROM events WHERE event_type=? AND job_id=?',
                                  (event_type, root_id)).fetchone())
    row.pop('event_id')
    row['command_id'] += ':duplicate'
    row['sequence'] += 10000
    connection.execute('INSERT INTO events (' + ','.join(row) + ') VALUES (' +
                       ','.join('?' for _ in row) + ')', tuple(row.values()))


def test_completed_admission_exact_typed_plan_and_distinct_digests(completed):
    runtime, root_id, planner, attempt = completed
    snapshot, observation = _read(runtime, root_id)
    assert isinstance(snapshot, er.BoundedAdmittedPlanSnapshot)
    assert [f.name for f in fields(snapshot)] == [
        'root_job_id', 'root_metadata', 'admission', 'plan', 'observation_source_identity']
    assert snapshot.root_job_id == root_id
    assert snapshot.root_metadata.job_id == root_id
    assert snapshot.root_metadata.creation_command_id == 'ceo-intent:CEO-TERMINAL-RETURN-PLANNER'
    assert snapshot.admission['plan_attempt_id'] == attempt.attempt_id
    assert snapshot.plan['plan_attempt_id'] == attempt.attempt_id
    assert snapshot.admission['plan_digest'] == canonical_digest(snapshot.plan)
    reservation = dict(snapshot.admission)
    digest = reservation.pop('reservation_digest')
    assert digest == canonical_digest(reservation)
    assert digest != snapshot.admission['plan_digest']
    assert observation.receipt.state == 'UNKNOWN'  # no namespace capability supplied
    with pytest.raises(FrozenInstanceError):
        snapshot.root_job_id = 'changed'


def test_active_interactive_admission_does_not_require_completed_planner(tmp_path):
    runtime, root_id, planner, attempt = _active(tmp_path)
    assert runtime.attempts.get_attempt(attempt.attempt_id).status.value == 'RUNNING'
    snapshot, _ = _read(runtime, root_id)
    assert snapshot.plan['steps'][0]['step_id'] == 'step-interactive'
    assert snapshot.admission['plan_attempt_id'] == attempt.attempt_id


def test_sealed_proposal_without_admission_is_typed_missing(tmp_path):
    runtime, root_id, *_ = _active(tmp_path, admit=False)
    with pytest.raises(er.RuntimePlanAdmissionNotEstablished) as error:
        with runtime.observe_bounded_read() as observation:
            observation.read_admitted_plan_bounded(root_id)
    assert error.value.code == 'ADMISSION_NOT_ESTABLISHED'
    with pytest.raises(er.StateConflict):
        _ = observation.receipt


def test_duplicate_admission_is_typed_conflict(completed, monkeypatch):
    runtime, root_id, *_ = completed
    _corrupt(runtime, lambda con: _duplicate_event(con, 'COO_PLAN_ADMITTED', root_id))
    # Only schema admission is bypassed for the deliberately corrupt DB;
    # the actual bounded SQL loader and semantic validators remain real.
    monkeypatch.setattr(runtime.store, '_verify_current_schema', lambda con: None)
    with pytest.raises(er.RuntimePlanAdmissionConflict) as error:
        _read(runtime, root_id)
    assert error.value.code == 'ADMISSION_CONFLICT'


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'fingerprint', 'noncanonical'])
def test_immutable_root_creation_provenance_required(completed, change):
    runtime, root_id, *_ = completed
    def mutate(con):
        if change == 'duplicate':
            return _duplicate_event(con, 'JOB_CREATED', root_id)
        row = con.execute("SELECT event_id,payload_json FROM events WHERE event_type='JOB_CREATED' AND job_id=?", (root_id,)).fetchone()
        if change == 'missing':
            con.execute('DELETE FROM events WHERE event_id=?', (row['event_id'],))
            return
        payload = json.loads(row['payload_json'])
        if change == 'fingerprint':
            payload['provenance']['fingerprint'] = 'f' * 64
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        if change == 'noncanonical':
            raw = raw[:-1] + ',"provenance":' + json.dumps(payload['provenance']) + '}'
        con.execute('UPDATE events SET payload_json=? WHERE event_id=?', (raw, row['event_id']))
    _corrupt(runtime, mutate)
    with pytest.raises(er.StateConflict):
        _read(runtime, root_id)


def test_snapshot_detaches_nested_validator_material(completed, monkeypatch):
    runtime, root_id, *_ = completed
    original = er._validated_plan_admission
    captured = []
    def capture(loader, root):
        value = original(loader, root)
        captured.append((loader, value))
        return value
    monkeypatch.setattr(er, '_validated_plan_admission', capture)
    snapshot, _ = _read(runtime, root_id)
    assert len(captured) == 1
    assert isinstance(captured[0][0], er._BoundedRoleResultLoader)
    admission, plan = captured[0][1]
    plan['steps'][0]['objective'] = 'mutated retained validator object'
    admission['steps'][0]['ordinal'] = 999
    assert snapshot.plan['steps'][0]['objective'] != plan['steps'][0]['objective']
    assert snapshot.admission['steps'][0]['ordinal'] == 0
    snapshot.plan['steps'][0]['objective'] = 'consumer mutation'
    assert _read(runtime, root_id)[0].plan['steps'][0]['objective'] != 'consumer mutation'


def test_one_selection_and_no_early_receipt(completed):
    runtime, root_id, *_ = completed
    with runtime.observe_bounded_read() as observation:
        observation.read_admitted_plan_bounded(root_id)
        with pytest.raises(er.StateConflict):
            _ = observation.receipt
        with pytest.raises(er.StateConflict):
            observation.read_admitted_plan_bounded(root_id)
    with pytest.raises(er.StateConflict):
        _ = observation.receipt


def test_physical_close_then_same_receipt(completed, monkeypatch):
    runtime, root_id, *_ = completed
    opened = []
    connect = er.sqlite3.connect
    with _bound(runtime) as (reader, namespace, _):
        def capture(*args, **kwargs):
            con = connect(*args, **kwargs)
            opened.append(con)
            return con
        monkeypatch.setattr(er.sqlite3, 'connect', capture)
        snapshot, observation = _read(reader, root_id)
        assert observation.receipt.state == 'SAME'
        assert snapshot.observation_source_identity == observation.receipt.source_identity
        assert len(snapshot.observation_source_identity) == 32
        assert namespace.entries == namespace.exits == 1
        assert len(opened) == 1
        with pytest.raises(sqlite3.ProgrammingError):
            opened[0].execute('SELECT 1')


def test_concurrent_source_change_is_conflict(completed):
    runtime, root_id, *_ = completed
    with _bound(runtime) as (reader, _, _):
        with reader.observe_bounded_read() as observation:
            observation.read_admitted_plan_bounded(root_id)
            with runtime.store.transaction() as con:
                con.execute('UPDATE jobs SET objective=? WHERE job_id=?', ('changed', root_id))
        assert observation.receipt.state == 'CONFLICT'


def test_close_failure_has_no_receipt(completed, monkeypatch):
    runtime, root_id, *_ = completed
    with _bound(runtime) as (reader, _, _):
        def fail(connection):
            connection._retain_uncertain()
            raise er.RuntimeReadUnavailable('fixture physical close unknown')
        monkeypatch.setattr(er._BoundReadConnection, '_drain_and_close', fail)
        with pytest.raises(er.RuntimeReadUnavailable):
            with reader.observe_bounded_read() as observation:
                observation.read_admitted_plan_bounded(root_id)
        with pytest.raises(er.StateConflict):
            _ = observation.receipt


def test_vm_exhaustion_is_shared_typed_budget(completed):
    runtime, root_id, *_ = completed
    _fill_events(runtime.store.path, 150_000)
    with pytest.raises(er.RuntimeRoleResultOverBudget) as error:
        with runtime.observe_bounded_read() as observation:
            observation.read_admitted_plan_bounded(root_id)
    assert error.value.code == 'OVER_BUDGET'
    assert observation._vm_progress.tripped
    with pytest.raises(er.StateConflict):
        _ = observation.receipt


@pytest.mark.parametrize('corruption', ['writer', 'attestation', 'provider'])
def test_invalid_active_seal_never_falls_back_to_completed_history(tmp_path, monkeypatch, corruption):
    runtime, root_id, planner, attempt = _active(tmp_path)
    def mutate(con):
        # A retained completion marker exercises the canonical branch choice.
        con.execute("INSERT INTO events (aggregate_type,aggregate_id,sequence,event_type,command_id,actor,job_id,attempt_id,payload_json,created_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ('job', planner.job_id, 10001, 'JOB_COMPLETED', 'fixture:completed-history',
                     'fixture', planner.job_id, attempt.attempt_id, '{}', runtime.store.now_ms()))
        column, value = {'writer': ('executive_writer_held', 0),
                         'attestation': ('observed_attestation_digest', 'f' * 64),
                         'provider': ('provider_session_id', 'FOREIGN-SESSION')}[corruption]
        con.execute('UPDATE process_generations SET ' + column + '=?', (value,))
    _corrupt(runtime, mutate)
    def forbidden(*args, **kwargs):
        pytest.fail('active failure fell back to completed seal validation')
    monkeypatch.setattr(er, '_validated_orchestration_role_result_payload', forbidden)
    with pytest.raises(er.StateConflict):
        _read(runtime, root_id)


def test_completed_admission_uses_exact_admitted_attempt_not_current_pointer(completed):
    runtime, root_id, planner, attempt = completed
    _corrupt(runtime, lambda con: con.execute("UPDATE jobs SET current_attempt_id=NULL,assigned_worker_id=NULL,assigned_quota_class=NULL,status='QUEUED' WHERE job_id=?", (planner.job_id,)))
    snapshot, _ = _read(runtime, root_id)
    assert snapshot.admission['plan_attempt_id'] == attempt.attempt_id


def test_finite_completion_marker_without_admission_is_not_authority(completed):
    runtime, root_id, planner, attempt = completed
    def mutate(con):
        # The finite proposal's marker is not an admission. This is a negative
        # stored-event fixture, not a claim of live finite-Operator acceptance.
        con.execute("DELETE FROM events WHERE event_type='COO_PLAN_ADMITTED' AND job_id=?", (root_id,))
        con.execute("INSERT INTO events (aggregate_type,aggregate_id,sequence,event_type,command_id,actor,job_id,attempt_id,payload_json,created_at_ms) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    ('job', root_id, 10001, 'OPERATOR_COMPLETED', 'fixture:finite-proposal',
                     'fixture', root_id, attempt.attempt_id, '{"state":"OPERATOR_COMPLETED"}', runtime.store.now_ms()))
    _corrupt(runtime, mutate)
    with pytest.raises(er.RuntimePlanAdmissionNotEstablished):
        _read(runtime, root_id)


@pytest.mark.parametrize('value', [' JOB-001', 'JOB-001 ', '', 3, 'A' * 129])
def test_exact_root_identifier_required(completed, value):
    runtime, *_ = completed
    with pytest.raises(er.StateConflict):
        _read(runtime, value)


def test_nonroot_and_missing_root_refused(completed):
    runtime, _, planner, _ = completed
    for root_id in (planner.job_id, 'JOB-ABSENT'):
        with pytest.raises((er.PersistenceError, er.StateConflict)):
            _read(runtime, root_id)


@pytest.mark.parametrize('budget', ['statements', 'rows', 'bytes'])
def test_canonical_validation_cannot_reset_acquisition_budget(completed, monkeypatch, budget):
    runtime, root_id, *_ = completed
    canonical = er._validated_plan_admission
    def nearly_exhausted(loader, row):
        assert loader._statements > 0 and loader._rows > 0 and loader._total_bytes > 0
        # Spend the remaining allowance on real SQL through the SAME loader.
        if budget == 'statements':
            while loader._statements < er.BOUNDED_ROLE_RESULT_MAX_STATEMENTS - 1:
                loader.execute('SELECT 1 AS budget_probe').fetchone()
        elif budget == 'rows':
            loader.execute('WITH RECURSIVE rows(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM rows WHERE n<505) SELECT n FROM rows').fetchall()
        else:
            cell = 'x' * 1_000_000
            while loader._total_bytes < er.BOUNDED_ROLE_RESULT_MAX_TOTAL_BYTES - 1_000_000:
                loader.execute('SELECT ? AS budget_probe', (cell,)).fetchone()
            remaining = er.BOUNDED_ROLE_RESULT_MAX_TOTAL_BYTES - loader._total_bytes - 1
            loader.execute('SELECT ? AS budget_probe', ('x' * remaining,)).fetchone()
        # Canonical validation itself must cross the remaining allowance; a
        # new loader here would incorrectly let this selection succeed.
        return canonical(loader, row)
    monkeypatch.setattr(er, '_validated_plan_admission', nearly_exhausted)
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        with runtime.observe_bounded_read() as observation:
            observation.read_admitted_plan_bounded(root_id)
    with pytest.raises(er.StateConflict):
        _ = observation.receipt
    assert not observation._vm_progress._active


def test_root_cell_guard_before_material_conversion(completed):
    runtime, root_id, *_ = completed
    with runtime.store.transaction() as con:
        con.execute('UPDATE jobs SET objective=? WHERE job_id=?',
                    ('x' * (er.BOUNDED_ROLE_RESULT_MAX_CELL_BYTES + 1), root_id))
    with pytest.raises(er.RuntimeRoleResultOverBudget):
        _read(runtime, root_id)


def test_eight_step_admission_measured_with_fixed_shared_limits(tmp_path, monkeypatch):
    from tests.test_executive_os_phase1fc import _register_placement_union, _admit_v2_plan
    runtime = er.Runtime.at(tmp_path)
    _register_placement_union(runtime)
    runtime, root, plan, _ = _admit_v2_plan(runtime, placements=[{'provider_realm': 'codex', 'quota_class': 'codex-hf1q-step'}] * 8)
    original = er._BoundedRoleResultLoader.__init__
    loaders = []
    def capture(loader, connection):
        original(loader, connection)
        loaders.append(loader)
    monkeypatch.setattr(er._BoundedRoleResultLoader, '__init__', capture)
    snapshot, _ = _read(runtime, root.job_id)
    assert snapshot.plan == plan and len(snapshot.plan['steps']) == 8
    assert len(loaders) == 1
    loader = loaders[0]
    assert 0 < loader._statements <= 256
    assert 0 < loader._rows <= 512
    assert 0 < loader._total_bytes <= 33_554_432
    assert er.BOUNDED_ROLE_RESULT_MAX_VM_STEPS == 200_000


def test_read_is_select_only_and_old_completed_reader_unchanged(completed, monkeypatch):
    runtime, root_id, planner, attempt = completed
    expected = runtime.validated_role_completion(planner.job_id, expected_attempt_id=attempt.attempt_id)
    connect = er.sqlite3.connect
    traces = []
    def traced(*args, **kwargs):
        con = connect(*args, **kwargs)
        con.set_trace_callback(traces.append)
        return con
    monkeypatch.setattr(er.sqlite3, 'connect', traced)
    _read(runtime, root_id)
    forbidden = ('INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE', 'DROP', 'ALTER')
    assert not any(sql.lstrip().upper().startswith(forbidden) for sql in traces)
    with runtime.observe_bounded_read() as observation:
        result = observation.read_role_result_bounded(root_id, planner.job_id,
            expected_attempt_id=attempt.attempt_id, expected_result_envelope_digest=expected.result_digest)
    assert result.completion == expected
