"""G8 bounded Runtime acquisition: SQL-bounded owner reads before projection."""

from __future__ import annotations

from contextlib import contextmanager
import threading

import pytest

from control_plane import executive_runtime as er
from control_plane.executive_runtime import JobPayload, Runtime, StateConflict


def _runtime(tmp_path):
    root = tmp_path / "runtime"
    root.mkdir()
    return root, Runtime.at(root)


def _register_worker(runtime: Runtime) -> None:
    runtime.workers.register_worker(
        "worker-01",
        provider="codex",
        account_label="primary",
        worker_type="mock",
        capabilities=["code", "research"],
    )


def _make_attempts(runtime: Runtime, job_id: str, count: int) -> None:
    _register_worker(runtime)
    for index in range(count):
        lease = runtime.attempts.claim_job(job_id)
        assert lease is not None
        runtime.jobs.fail_job(
            job_id,
            JobPayload(errors=[f"fixture attempt {index + 1}"]),
        )
        if index + 1 < count:
            runtime.jobs.requeue_job(job_id)


def test_bounded_ceilings_track_existing_owner_policy():
    from control_plane.ceo_intent import MAX_ATTEMPT_LIMIT
    from control_plane.executive_coo_policy import CooCyclePolicy

    policy = CooCyclePolicy.load()
    assert er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN == policy.max_children_total
    assert er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS == MAX_ATTEMPT_LIMIT
    assert er.BOUNDED_RUNTIME_ROOT_MAX_ATTEMPTS_TOTAL == (
        (1 + policy.max_children_total) * MAX_ATTEMPT_LIMIT
    )


def test_bounded_queries_put_sentinel_limits_in_sqlite(tmp_path, monkeypatch):
    _root, runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    runtime.jobs.create_job("child", parent_job_id=root.job_id)

    traces = []
    original_connect = er.sqlite3.connect

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        connection.set_trace_callback(traces.append)
        return connection

    monkeypatch.setattr(er.sqlite3, "connect", connect)
    runtime.discover_job_roots_bounded()
    runtime.read_job_root_bounded(root.job_id)

    normalized = [" ".join(sql.split()) for sql in traces]
    assert any(
        "WITH RECURSIVE bounded_root_ids" in sql
        and f"LIMIT {er.BOUNDED_RUNTIME_ROOT_DISCOVERY_MAX_ROOTS + 1}" in sql
        for sql in normalized
    )
    assert any(
        "WHERE (root_job_id=" in sql
        and "ORDER BY depth,created_at_ms,job_id" in sql
        and f"LIMIT {er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN + 2}" in sql
        for sql in normalized
    )
    assert any(
        "FROM attempts" in sql
        and "job_id IN" in sql
        and f"LIMIT {er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS + 1}" in sql
        for sql in normalized
    )


def test_root_discovery_is_sql_bounded_before_job_conversion(tmp_path, monkeypatch):
    _root, runtime = _runtime(tmp_path)
    for index in range(er.BOUNDED_RUNTIME_ROOT_DISCOVERY_MAX_ROOTS + 3):
        runtime.jobs.create_job(f"root {index:03d}")

    converted = []
    original = er._job_from_row

    def spy(row):
        converted.append(str(row["job_id"]))
        return original(row)

    monkeypatch.setattr(er, "_job_from_row", spy)
    observed = runtime.discover_job_roots_bounded()

    assert observed.schema_version == er.BOUNDED_RUNTIME_DISCOVERY_SCHEMA
    assert len(observed.roots) == er.BOUNDED_RUNTIME_ROOT_DISCOVERY_MAX_ROOTS
    assert observed.truncated is True
    assert len(converted) == er.BOUNDED_RUNTIME_ROOT_DISCOVERY_MAX_ROOTS
    assert observed.snapshot_digest == runtime.discover_job_roots_bounded().snapshot_digest


def test_exact_root_snapshot_materializes_only_root_plus_closed_child_budget(
    tmp_path, monkeypatch
):
    _root, runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    children = [
        runtime.jobs.create_job(f"child {index:03d}", parent_job_id=root.job_id)
        for index in range(er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN + 2)
    ]

    converted = []
    original = er._job_from_row

    def spy(row):
        converted.append(str(row["job_id"]))
        return original(row)

    monkeypatch.setattr(er, "_job_from_row", spy)
    observed = runtime.read_job_root_bounded(root.job_id)

    assert observed.schema_version == er.BOUNDED_RUNTIME_ROOT_SNAPSHOT_SCHEMA
    assert observed.root_job_id == root.job_id
    assert observed.jobs[0].job_id == root.job_id
    assert len(observed.jobs) == 1 + er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN
    assert observed.jobs_truncated is True
    assert len(converted) == 1 + er.BOUNDED_RUNTIME_ROOT_MAX_CHILDREN
    assert set(job.job_id for job in observed.jobs[1:]).issubset(
        {child.job_id for child in children}
    )
    # Legacy registry behavior is deliberately unchanged and still sees everything.
    assert len(runtime.jobs.list_jobs()) == 1 + len(children)


def test_attempts_are_bounded_per_job_before_attempt_conversion(tmp_path, monkeypatch):
    _root, runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    child = runtime.jobs.create_job(
        "attempt-heavy child",
        parent_job_id=root.job_id,
        attempt_limit=er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS + 1,
    )
    _make_attempts(runtime, child.job_id, er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS + 1)

    converted = []
    original = er._attempt_from_row

    def spy(row):
        converted.append(str(row["attempt_id"]))
        return original(row)

    monkeypatch.setattr(er, "_attempt_from_row", spy)
    observed = runtime.read_job_root_bounded(root.job_id)

    assert len(observed.attempts) == er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS
    assert observed.attempts_truncated_job_ids == (child.job_id,)
    assert len(converted) == er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS
    assert all(attempt.job_id == child.job_id for attempt in observed.attempts)
    assert len(runtime.attempts.list_attempts(child.job_id)) == (
        er.BOUNDED_RUNTIME_JOB_MAX_ATTEMPTS + 1
    )


def test_root_snapshot_refuses_nonroot_and_never_leaks_another_root(tmp_path):
    _root, runtime = _runtime(tmp_path)
    first = runtime.jobs.create_job("first root")
    first_child = runtime.jobs.create_job("first child", parent_job_id=first.job_id)
    second = runtime.jobs.create_job("second root")
    second_child = runtime.jobs.create_job("second child", parent_job_id=second.job_id)

    with pytest.raises(StateConflict, match="exact root"):
        runtime.read_job_root_bounded(first_child.job_id)

    observed = runtime.read_job_root_bounded(first.job_id)
    assert {job.job_id for job in observed.jobs} == {first.job_id, first_child.job_id}
    assert second.job_id not in {job.job_id for job in observed.jobs}
    assert second_child.job_id not in {job.job_id for job in observed.jobs}


def test_snapshot_digest_is_content_addressed_and_changes_with_runtime_state(tmp_path):
    _root, runtime = _runtime(tmp_path)
    root = runtime.jobs.create_job("root")
    first = runtime.read_job_root_bounded(root.job_id)
    again = runtime.read_job_root_bounded(root.job_id)
    assert first.snapshot_digest == again.snapshot_digest

    runtime.jobs.create_job("new child", parent_job_id=root.job_id)
    changed = runtime.read_job_root_bounded(root.job_id)
    assert changed.snapshot_digest != first.snapshot_digest


def test_bounded_snapshot_composes_with_existing_runtime_read_binding(tmp_path):
    root_path, writer = _runtime(tmp_path)
    root = writer.jobs.create_job("root")
    writer.jobs.create_job("child", parent_job_id=root.job_id)

    class Namespace(er.RuntimeNamespaceCapability):
        def __init__(self):
            self.lock = threading.Lock()
            self.entries = 0
            self.exits = 0

        @contextmanager
        def namespace(self, database_path):
            assert self.lock.acquire(timeout=1)
            self.entries += 1
            try:
                yield
            finally:
                self.exits += 1
                self.lock.release()

        def validate(self, database_path):
            return None

    provider = Namespace()
    binding = er.RuntimeReadBinding(provider)
    observed = Runtime.read_bound(
        root_path,
        binding=binding,
        reader=lambda runtime: runtime.read_job_root_bounded(root.job_id),
    )

    assert observed.root_job_id == root.job_id
    assert [job.objective for job in observed.jobs] == ["root", "child"]
    assert provider.entries == provider.exits == 1


# Currentness fixtures are a closed, test-owned namespace, not installed custody.
# All namespace mutation actors in this fixture use Namespace.replace; deliberate
# bypass below exercises invalidation detection, never qualifies a real service.
class ObservationNamespace(er.RuntimeNamespaceCapability):
    def __init__(self, path):
        self.path = path
        self.active = False
        self.entries = self.exits = 0
        self.invalid = False
        self.identities = {}

    @contextmanager
    def namespace(self, path):
        assert path == self.path and not self.active
        self.active = True
        self.entries += 1
        paths = [path, path.parent, path.parent.parent,
                 path.with_name(path.name + '-wal'), path.with_name(path.name + '-shm')]
        self.identities = {p: (p.stat().st_dev, p.stat().st_ino) for p in paths if p.exists()}
        try:
            yield
        finally:
            self.active = False
            self.exits += 1

    def replace(self, source, destination):
        if self.active:
            raise er.RuntimeReadUnavailable('fixture namespace is exclusively owned')
        source.replace(destination)

    def validate(self, path):
        if self.invalid or path != self.path:
            raise er.RuntimeReadUnavailable('fixture namespace invalid')
        for p, expected in self.identities.items():
            if not p.exists() or (p.stat().st_dev, p.stat().st_ino) != expected:
                raise er.RuntimeReadUnavailable('fixture namespace identity changed')


@pytest.fixture
def observation_fixture(tmp_path):
    from control_plane.ceo_intent import submit_intent
    root, writer = _runtime(tmp_path)
    intent = {
        'schema': 'mastermind.ceo_intent.v2', 'intent_id': 'OBS-ROOT-001',
        'actor': 'ceo-sol', 'objective': 'Observe one bounded fixture root',
        'department': 'executive-infrastructure', 'priority': 5,
        'intent_kind': 'executive_coo_cycle', 'business_impact': 'material',
        'grounding': {'mastermind_sha': '1' * 40, 'macro_sha': '2' * 40,
                      'boot_packet_schema': 'mastermind.ceo_boot_packet.v1'},
        'execution_contract': {'requested_authorities': ['READ'], 'attempt_limit': 2},
    }
    job_id = submit_intent(writer, intent)['job_id']
    # Keep actual WAL/SHM namespace stable across reader opens and closes.
    keeper = er.sqlite3.connect(writer.store.path, isolation_level=None)
    keeper.execute('SELECT 1 FROM jobs').fetchone()
    namespace = ObservationNamespace(writer.store.path)
    binding = er.RuntimeReadBinding(namespace)
    runtime = Runtime.at(root, create=False, read_binding=binding)
    try:
        yield root, writer, runtime, namespace, binding, job_id, 'ceo-intent:OBS-ROOT-001'
    finally:
        keeper.close()
        if binding._unclosed_connection is not None:
            er.sqlite3.Connection.close(binding._unclosed_connection)
        if binding._retained_namespace is not None:
            binding._retained_namespace.close()


def test_observation_same_one_scope_and_point_provenance(observation_fixture, monkeypatch):
    root, writer, runtime, namespace, binding, job_id, command = observation_fixture
    traces, opened = [], []
    original = er.sqlite3.connect
    def connect(*args, **kwargs):
        conn = original(*args, **kwargs)
        conn.set_trace_callback(traces.append)
        opened.append(conn)
        return conn
    monkeypatch.setattr(er.sqlite3, 'connect', connect)
    monkeypatch.setattr(runtime.events, 'list_events', lambda **kw: pytest.fail('legacy history'))
    with runtime.observe_bounded_read() as read:
        with pytest.raises(StateConflict):
            _ = read.receipt
        snapshot = read.read_job_root_bounded(job_id)
        event = read.get_creation_event_by_command_id(command)
        count = len(traces)
        assert read.get_creation_event_by_command_id(command) is event
        assert len(traces) == count
    receipt = read.receipt.to_dict()
    assert receipt == {'schema': 'mastermind.runtime_read_observation.v1', 'state': 'SAME',
                       'source_identity': receipt['source_identity'],
                       'before': receipt['before'], 'after': receipt['before']}
    assert type(receipt['before']) is int and receipt['before'] >= 0
    assert len(receipt['source_identity']) == 32 and str(root) not in receipt['source_identity']
    assert len(opened) == namespace.entries == namespace.exits == 1
    assert event.job_id == job_id and event.event_type == 'JOB_CREATED'
    assert snapshot.root_job_id == job_id
    normalized = [s.strip().upper() for s in traces]
    tokens = [i for i, s in enumerate(normalized) if s == 'PRAGMA DATA_VERSION']
    assert len(tokens) == 2
    assert tokens[0] < normalized.index('BEGIN') < normalized.index('COMMIT') < tokens[1]
    with pytest.raises(er.sqlite3.ProgrammingError):
        opened[0].execute('SELECT 1')
    with pytest.raises(StateConflict):
        read.read_job_root_bounded(job_id)


@pytest.mark.parametrize('restore', [False, True])
def test_observation_detects_non_event_commits_even_restored(observation_fixture, restore):
    _, writer, runtime, _, _, job_id, _ = observation_fixture
    original = writer.jobs.get_job(job_id).objective
    events_before = len(writer.events.list_events())
    with runtime.observe_bounded_read() as read:
        snapshot = read.read_job_root_bounded(job_id)
        with writer.store.transaction() as conn:
            conn.execute('UPDATE jobs SET objective=? WHERE job_id=?', ('changed', job_id))
        if restore:
            with writer.store.transaction() as conn:
                conn.execute('UPDATE jobs SET objective=? WHERE job_id=?', (original, job_id))
    assert read.receipt.state == 'CONFLICT'
    assert read.receipt.before != read.receipt.after
    assert len(writer.events.list_events()) == events_before
    if restore:
        assert writer.read_job_root_bounded(job_id).snapshot_digest == snapshot.snapshot_digest


def test_observation_unbound_never_qualifies(observation_fixture):
    _, writer, _, _, _, job_id, _ = observation_fixture
    with writer.observe_bounded_read() as read:
        read.read_job_root_bounded(job_id)
    assert read.receipt.state == 'UNKNOWN'
    assert read.receipt.source_identity is None


def test_observation_gap_is_not_continuous_exclusion(observation_fixture, monkeypatch):
    _, writer, runtime, _, _, job_id, _ = observation_fixture
    original = runtime.store._close_read_connection
    def close(connection):
        with writer.store.transaction() as conn:
            conn.execute('UPDATE jobs SET objective=? WHERE job_id=?', ('after sample', job_id))
        original(connection)
    monkeypatch.setattr(runtime.store, '_close_read_connection', close)
    with runtime.observe_bounded_read() as read:
        snapshot = read.read_job_root_bounded(job_id)
    assert read.receipt.state == 'SAME' and read.receipt.before == read.receipt.after
    assert writer.read_job_root_bounded(job_id).snapshot_digest != snapshot.snapshot_digest


@pytest.mark.parametrize('operation', ['second_root', 'extra_discovery', 'unrelated_event', 'event_first'])
def test_observation_refuses_extra_scope(observation_fixture, operation):
    _, _, runtime, _, _, job_id, command = observation_fixture
    with runtime.observe_bounded_read() as read:
        if operation != 'event_first':
            read.read_job_root_bounded(job_id)
        with pytest.raises(StateConflict):
            if operation == 'second_root': read.read_job_root_bounded(job_id)
            elif operation == 'extra_discovery': read.discover_job_roots_bounded()
            elif operation == 'unrelated_event': read.get_creation_event_by_command_id('ceo-intent:UNRELATED')
            else: read.get_creation_event_by_command_id(command)
    with pytest.raises(StateConflict):
        _ = read.receipt


def test_observation_discovery_uses_same_handle(observation_fixture):
    _, _, runtime, namespace, _, job_id, command = observation_fixture
    with runtime.observe_bounded_read() as read:
        discovery = read.discover_job_roots_bounded()
        assert [j.job_id for j in discovery.roots] == [job_id]
        assert read.get_creation_event_by_command_id(command).job_id == job_id
    assert read.receipt.state == 'SAME'
    assert namespace.entries == 1


@pytest.mark.parametrize('fault', ['body', 'namespace', 'close'])
def test_observation_failure_has_no_receipt(observation_fixture, monkeypatch, fault):
    _, _, runtime, namespace, binding, job_id, _ = observation_fixture
    if fault == 'close':
        original = er._BoundReadConnection._drain_and_close
        def fail(self):
            self._retain_uncertain()
            raise er.RuntimeReadUnavailable('fixture close unknown')
        monkeypatch.setattr(er._BoundReadConnection, '_drain_and_close', fail)
    with pytest.raises((RuntimeError, er.PersistenceError)):
        with runtime.observe_bounded_read() as read:
            read.read_job_root_bounded(job_id)
            if fault == 'body': raise RuntimeError('body failure')
            if fault == 'namespace': namespace.invalid = True
    with pytest.raises(StateConflict):
        _ = read.receipt
    if fault == 'close':
        assert binding._unclosed_connection is not None and namespace.exits == 0
    else:
        assert namespace.exits == 1


@pytest.mark.parametrize('bad', [None, True, '2', -1, 2.5])
def test_observation_malformed_samples_never_qualify(observation_fixture, monkeypatch, bad):
    _, _, runtime, namespace, _, job_id, _ = observation_fixture
    original = er._BoundReadConnection._owner_execute
    class TokenCursor:
        def fetchone(self): return None if bad is None else (bad,)
    def execute(self, sql):
        if sql == 'PRAGMA data_version': return TokenCursor()
        return original(self, sql)
    monkeypatch.setattr(er._BoundReadConnection, '_owner_execute', execute)
    with pytest.raises(er.RuntimeReadUnavailable):
        with runtime.observe_bounded_read() as read:
            read.read_job_root_bounded(job_id)
    assert namespace.entries == namespace.exits == 1


@pytest.mark.parametrize('fault', ['token', 'commit', 'query', 'interrupt'])
def test_observation_owner_failures_close_before_unavailable(observation_fixture, monkeypatch, fault):
    _, _, runtime, namespace, _, job_id, _ = observation_fixture
    if fault in ('token', 'interrupt'):
        original = er._BoundReadConnection._owner_execute
        def execute(self, sql):
            if sql == 'PRAGMA data_version':
                if fault == 'interrupt': raise KeyboardInterrupt('sample interrupted')
                raise er.sqlite3.OperationalError('sample failed')
            return original(self, sql)
        monkeypatch.setattr(er._BoundReadConnection, '_owner_execute', execute)
    elif fault == 'commit':
        original = er._BoundReadConnection._owner_finish
        def finish(self, *, commit):
            if commit: raise er.sqlite3.OperationalError('commit failed')
            return original(self, commit=commit)
        monkeypatch.setattr(er._BoundReadConnection, '_owner_finish', finish)
    else:
        original = er._BoundReadConnection.execute
        def execute(self, sql, parameters=()):
            if 'SELECT job_id,parent_job_id' in sql:
                raise er.sqlite3.OperationalError('query failed')
            return original(self, sql, parameters)
        monkeypatch.setattr(er._BoundReadConnection, 'execute', execute)
    with pytest.raises((er.PersistenceError, KeyboardInterrupt)):
        with runtime.observe_bounded_read() as read:
            read.read_job_root_bounded(job_id)
    assert namespace.entries == namespace.exits == 1
    if fault in ('commit', 'query'):
        with pytest.raises(StateConflict): _ = read.receipt


@pytest.mark.parametrize('target', ['database', 'parent', 'wal', 'shm'])
def test_observation_namespace_replacement_does_not_qualify(observation_fixture, target):
    _, writer, runtime, namespace, _, job_id, _ = observation_fixture
    with pytest.raises(er.RuntimeReadUnavailable):
        with runtime.observe_bounded_read() as read:
            read.read_job_root_bounded(job_id)
            if target == 'parent':
                victim = writer.store.path.parent
                victim.rename(victim.with_name('replaced-parent'))
            else:
                victim = writer.store.path if target == 'database' else writer.store.path.with_name(writer.store.path.name + '-' + target)
                replacement = victim.with_name(victim.name + '.replacement')
                replacement.write_bytes(victim.read_bytes())
                # Deliberately bypass the fixture's exclusion actor to model a
                # broken capability; identity validation must still refuse SAME.
                replacement.replace(victim)
    with pytest.raises(StateConflict): _ = read.receipt
    assert namespace.exits == 1


def test_observation_exclusion_actor_and_final_return_validation(observation_fixture, monkeypatch):
    _, writer, runtime, namespace, binding, job_id, _ = observation_fixture
    replacement = writer.store.path.with_name('replacement')
    replacement.write_bytes(b'fixture')
    original = namespace.validate
    def validate(path):
        original(path)
        if namespace.entries and not namespace.active:
            raise er.RuntimeReadUnavailable('final return revoked')
    monkeypatch.setattr(namespace, 'validate', validate)
    with pytest.raises(er.RuntimeReadUnavailable):
        with runtime.observe_bounded_read() as read:
            read.read_job_root_bounded(job_id)
            with pytest.raises(er.RuntimeReadUnavailable):
                namespace.replace(replacement, writer.store.path)
    with pytest.raises(StateConflict): _ = read.receipt
    assert binding._unclosed_connection is None


def test_observation_wrong_handle_and_schema_fail_closed(observation_fixture, tmp_path, monkeypatch):
    _, _, runtime, namespace, _, job_id, _ = observation_fixture
    foreign = Runtime.at(tmp_path / 'foreign')
    original = er.sqlite3.connect
    def connect(*args, **kwargs):
        return original(foreign.store.path.as_uri() + '?mode=ro', **kwargs)
    monkeypatch.setattr(er.sqlite3, 'connect', connect)
    with pytest.raises(er.RuntimeReadUnavailable):
        with runtime.observe_bounded_read() as read:
            read.read_job_root_bounded(job_id)
    assert namespace.exits == 1


def test_observation_schema_corruption_refuses(observation_fixture):
    _, writer, runtime, namespace, _, _, _ = observation_fixture
    with writer.store.transaction() as conn:
        conn.execute('CREATE TABLE foreign_schema(value TEXT)')
    with pytest.raises(er.PersistenceError):
        with runtime.observe_bounded_read() as read:
            read.discover_job_roots_bounded()
    assert namespace.exits == 1


@pytest.mark.parametrize('field,value', [
    ('source_digest', 'not-a-digest'), ('source_id', 'x'),
    ('job_id', 'JOB-OTHER'), ('root_job_id', 'JOB-OTHER'),
    ('command_id', 'ceo-intent:OTHER'), ('extra_key', 'unrecognized'),
])
def test_observation_provenance_refuses_before_event_query(observation_fixture, monkeypatch, field, value):
    import dataclasses
    _, writer, runtime, _, _, job_id, command = observation_fixture
    cycle = dict(writer.jobs.get_job(job_id).orchestration_provenance)
    cycle[field] = value
    original = er._read_job_root_bounded
    def materialize(acquisition, root_id):
        snapshot = original(acquisition, root_id)
        malformed = dataclasses.replace(snapshot.jobs[0],
            orchestration_provenance=cycle,
            orchestration_provenance_digest=er.orchestration_digest(cycle))
        return dataclasses.replace(snapshot, jobs=(malformed, *snapshot.jobs[1:]))
    monkeypatch.setattr(er, '_read_job_root_bounded', materialize)
    monkeypatch.setattr(runtime.store, 'get_event_by_command_id', lambda *a, **k: pytest.fail('unauthorized Event query'))
    with runtime.observe_bounded_read() as read:
        read.read_job_root_bounded(job_id)
        with pytest.raises(StateConflict): read.get_creation_event_by_command_id(command)
    with pytest.raises(StateConflict): _ = read.receipt


def test_observation_point_budget_refuses_eighteenth_before_query(observation_fixture, monkeypatch):
    from control_plane.ceo_intent import submit_intent
    _, writer, runtime, _, _, _, command = observation_fixture
    commands = [command]
    for i in range(17):
        intent_id = f'OBS-MANY-{i:03}'
        submit_intent(writer, {
            'schema': 'mastermind.ceo_intent.v2', 'intent_id': intent_id, 'actor': 'ceo-sol',
            'objective': 'Bounded fixture root', 'department': 'executive-infrastructure', 'priority': 5,
            'intent_kind': 'executive_coo_cycle', 'business_impact': 'material',
            'grounding': {'mastermind_sha': '1' * 40, 'macro_sha': '2' * 40,
                          'boot_packet_schema': 'mastermind.ceo_boot_packet.v1'},
            'execution_contract': {'requested_authorities': ['READ'], 'attempt_limit': 2},
        })
        commands.append('ceo-intent:' + intent_id)
    with runtime.observe_bounded_read() as read:
        assert len(read.discover_job_roots_bounded().roots) == 18
        for token in commands[:17]: assert read.get_creation_event_by_command_id(token) is not None
        monkeypatch.setattr(runtime.store, 'get_event_by_command_id', lambda *a, **k: pytest.fail('eighteenth query'))
        with pytest.raises(StateConflict): read.get_creation_event_by_command_id(commands[17])
    with pytest.raises(StateConflict): _ = read.receipt


def test_observation_public_proxy_still_denies_pragma(observation_fixture, monkeypatch):
    _, _, runtime, _, _, job_id, _ = observation_fixture
    original = er.BoundedRuntimeAcquisition._require_open
    checked = []
    def require(self):
        original(self)
        if not checked:
            checked.append(True)
            with pytest.raises(er.sqlite3.DatabaseError):
                self._connection.execute('PRAGMA data_version')
    monkeypatch.setattr(er.BoundedRuntimeAcquisition, '_require_open', require)
    with runtime.observe_bounded_read() as read:
        read.read_job_root_bounded(job_id)
    assert checked and read.receipt.state == 'SAME'


def test_observation_missing_event_is_cached(observation_fixture, monkeypatch):
    _, _, runtime, _, _, job_id, command = observation_fixture
    calls = []
    def absent(token, *, connection):
        calls.append(token)
        assert connection is not None
        return None
    monkeypatch.setattr(runtime.store, 'get_event_by_command_id', absent)
    with runtime.observe_bounded_read() as read:
        read.read_job_root_bounded(job_id)
        assert read.get_creation_event_by_command_id(command) is None
        assert read.get_creation_event_by_command_id(command) is None
    assert calls == [command] and read.receipt.state == 'SAME'


@pytest.mark.parametrize('field,value', [('job_id', 'JOB-FOREIGN'), ('event_type', 'JOB_UPDATED'),
                                        ('command_id', 'ceo-intent:FOREIGN')])
def test_observation_foreign_event_refuses(observation_fixture, monkeypatch, field, value):
    import dataclasses
    _, writer, runtime, _, _, job_id, command = observation_fixture
    event = writer.store.get_event_by_command_id(command)
    monkeypatch.setattr(runtime.store, 'get_event_by_command_id',
                        lambda *a, **k: dataclasses.replace(event, **{field: value}))
    with pytest.raises(er.RuntimeReadUnavailable):
        with runtime.observe_bounded_read() as read:
            read.read_job_root_bounded(job_id)
            read.get_creation_event_by_command_id(command)
    with pytest.raises(StateConflict): _ = read.receipt


def test_observation_returned_job_cannot_expand_point_authority(observation_fixture, monkeypatch):
    _, _, runtime, _, _, job_id, command = observation_fixture
    with runtime.observe_bounded_read() as read:
        snapshot = read.read_job_root_bounded(job_id)
        snapshot.jobs[0].orchestration_provenance['command_id'] = 'ceo-intent:FOREIGN'
        monkeypatch.setattr(runtime.store, 'get_event_by_command_id', lambda *a, **k: pytest.fail('foreign query'))
        with pytest.raises(StateConflict): read.get_creation_event_by_command_id('ceo-intent:FOREIGN')
    with pytest.raises(StateConflict): _ = read.receipt


@pytest.mark.parametrize('fault', ['drain', 'namespace_exit'])
def test_observation_teardown_failure_no_receipt(observation_fixture, monkeypatch, fault):
    _, _, runtime, namespace, binding, job_id, _ = observation_fixture
    if fault == 'drain':
        def fail(cursor):
            raise er.sqlite3.OperationalError('cursor finalization fault')
        monkeypatch.setattr(er._BoundReadCursor, '_finalize', fail)
    else:
        original = namespace.namespace
        @contextmanager
        def fail(path):
            with original(path):
                yield
            raise RuntimeError('namespace exit fault')
        monkeypatch.setattr(namespace, 'namespace', fail)
    with pytest.raises((er.PersistenceError, er.sqlite3.Error)):
        with runtime.observe_bounded_read() as read:
            read.read_job_root_bounded(job_id)
    with pytest.raises(StateConflict): _ = read.receipt
    if fault == 'drain':
        assert binding._unclosed_connection is not None and namespace.exits == 0


def test_observation_identity_unique_and_closed_public_surface(observation_fixture):
    _, _, runtime, _, _, job_id, _ = observation_fixture
    identities = []
    for _ in range(2):
        with runtime.observe_bounded_read() as read:
            read.read_job_root_bounded(job_id)
            for name in ('connection', 'execute', 'cursor', 'token', 'list_events'):
                assert not hasattr(read, name)
        identities.append(read.receipt.source_identity)
        with pytest.raises(StateConflict): read.get_creation_event_by_command_id('ceo-intent:OBS-ROOT-001')
    assert identities[0] != identities[1]
    with pytest.raises(TypeError):
        with runtime.observe_bounded_read(before=2): pass
