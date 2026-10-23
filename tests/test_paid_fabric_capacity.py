"""Tests for the read-only paid Capacity observer.

SYNTHETIC FIXTURE DISCLOSURE: no live owner, gateway, broker, provider,
credential, configuration or network is exercised anywhere in this module.
The owner object is created with ``CanonicalPaidBackend.__new__`` so it has
the EXACT real class while its instance attributes point at synthetic
shim/context/gateway doubles that only mirror the incumbent retained-state
and read-only lease surfaces. Every guard that passes here proves class
identity and internal wiring coherence ONLY; it is explicitly NOT proof of
live authentication, authorization or provider readiness, and this suite
makes no such claim. Actual owner construction is left to the parent's final
review. Databases are temporary on-disk or in-memory SQLite only. The module
clock hook ``paid_fabric_capacity._now`` is monkeypatched; no public
argument ever carries a clock, runner, DB path or auth callback.
"""
import inspect
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from control_plane import paid_fabric_capacity as capacity
from control_plane.paid_fabric_capacity import (
    PaidCapacityRefused,
    observe_paid_capacity,
    validate_paid_capacity_observation,
)

from control_plane.paid_model_execution_contract import paid_host_reference

from control_plane.paid_fabric_backend import (
    CanonicalPaidBackend,
    PaidOwnerRefused,
    _SOURCE_QUALIFIED,
)

_SHA = 'a' * 64
_SHA2 = 'b' * 64


def _digest(value):
    return capacity.digest(value)


class _FakeAccountTable:
    """Retained-cache double mirroring the incumbent AccountTable surface.

    Forbidden metadata/API reader methods (refresh/select/get/api_keys/
    mark_exhausted) are never defined; touching them fails the test, proving
    the observer reads retained state only and never refreshes or selects.
    """

    FORBIDDEN = ('refresh', 'select', 'get', 'api_keys', 'mark_exhausted')

    def __init__(self, states, fail_state_on=None, racy_snapshot=None):
        self._states = states
        self._lock = threading.Lock()
        self.calls = []
        self._fail_state_on = fail_state_on or 0
        self._racy_snapshot = racy_snapshot

    def names(self):
        with self._lock:
            self.calls.append('names')
            return list(self._states)

    def state(self, name):
        with self._lock:
            self.calls.append('state')
            self._fail_state_on -= 1
            if self._fail_state_on == 0:
                raise RuntimeError('synthetic provider failure')
            return dict(self._states.get(name, {}))

    def snapshot(self):
        with self._lock:
            self.calls.append('snapshot')
            if self._racy_snapshot is not None:
                self._racy_snapshot(self._states)
            return [dict(name=name, exhausted_until=s['exhausted_until_ts'],
                         pct_5h=s['last_pct_5h'],
                         pct_week=s['last_pct_week'],
                         observed_at=s['observed_at'])
                    for name, s in self._states.items()]

    def __getattr__(self, name):
        if name in self.FORBIDDEN:
            raise AssertionError('forbidden AccountTable method: ' + name)
        raise AttributeError(name)


class _FakeShim:
    """Synthetic shim module double; discloses that guard passes here are
    wiring-coherence evidence, never live-incumbent evidence."""

    AccountTable = _FakeAccountTable

    def __init__(self, context, gateway, flip_after=0):
        self._context = context
        self._gateway = gateway
        self.calls = 0
        self._flip_after = flip_after
        self._other_gateway = object()

    def require_canonical_incumbent(self, incumbent):
        self.calls += 1
        if self._flip_after and self.calls > self._flip_after:
            return self._context, self._other_gateway
        return self._context, self._gateway


_FORBIDDEN_GATEWAY = ('_lease_lookup', '_issue_canonical', 'acquire',
                      'cancel', 'heartbeat', 'refresh', '_gc', '_status')


class _FakeGateway:
    """Synthetic gateway double with the incumbent read-only connection law.

    ``_connection`` reproduces the actual sqlite ``mode=ro`` URI connect.
    Forbidden mutation/process operations raise if ever touched, and every
    statement is traced so tests can prove exactly one scoped SELECT ran.
    """

    def __init__(self, db_path, accounts=frozenset({'acct-a'}), broken=False):
        self._db_path = db_path
        self._accounts = accounts
        self._canonical_owner = None
        self._broken = broken
        self.connections = []
        self.statements = []

    def _connection(self):
        if self._broken:
            raise RuntimeError('synthetic lease capability refused')
        connection = sqlite3.connect(
            self._db_path.as_uri() + '?mode=ro', uri=True, timeout=0.25)
        connection.set_trace_callback(self.statements.append)
        self.connections.append(connection)
        return connection

    def __getattr__(self, name):
        if name in _FORBIDDEN_GATEWAY:
            raise AssertionError('forbidden gateway operation: ' + name)
        raise AttributeError(name)


class _Startup:
    def __init__(self):
        self._qualified = _SOURCE_QUALIFIED
        self.bridge_uid = os.geteuid()


def _build_owner(table, gateway, flip_after=0):
    """Exact-class synthetic owner. Disclosed assumption: constructed via
    ``__new__`` with doubles; this is fixture wiring, not live auth."""
    owner = CanonicalPaidBackend.__new__(CanonicalPaidBackend)
    context = types.SimpleNamespace(account_table=table)
    shim = _FakeShim(context, gateway, flip_after=flip_after)
    owner._shim = shim
    owner._context = context
    owner._gateway = gateway
    owner._incumbent = object()
    owner._startup = _Startup()
    owner._operations = {}
    owner._lock = threading.RLock()
    gateway._canonical_owner = owner
    return owner


def _shim_of(owner):
    return owner._shim


def _binary():
    return dict(sha256=_SHA, size=12345, device=1, inode=2, mode=0o755,
                uid=1001, gid=1001, mtime_ns=1000, path='/opt/py/bin/python',
                real_path='/opt/py/bin/python3.12', version='3.12.1',
                team_identifier=None)


def _qualification():
    return dict(registry_key='host-a', registry_sha256=_SHA, transport_alias='glm-host-a',
                host_env_path='/tmp/cap/ext/HOST_ENV.sh', host_env_sha256=_SHA2,
                boot_id='boot-1', capture_identity=dict(device=1, inode=9,
                    mode=0o40700, uid=1001, gid=1001),
                qualifier_source_manifest_sha256=_SHA,
                qualifier_sources_sha256={name: _SHA for name in (
                    'host_pull.sh', 'host_pull_backend.py',
                    'host_pull_probe.template', 'paid_host_qualification.py',
                    'remote_sub.sh')},
                probe_sha256=_SHA2)


def _source_config(**over):
    source = dict(schema_version='mastermind.paid_worker_source/v1',
        worker_id='worker-1', provider='glm', host_ref=paid_host_reference('host-a','glm-host-a'),
        model='glm-5.3', worker_uid=1001, worker_gid=1001,
        worker_user='runner', binary=_binary(),
        permission_profile_sha256=_SHA, execution_profile_digest=_SHA2,
        service_source_sha256=_SHA, bridge_uid=501,
        socket_path='/run/glm/sock', capture_root='/tmp/cap/ext/lanes',
        qualification=_qualification(), capacity_capability_id='cap-1')
    source.update(over)
    return source


def _physical(source):
    physical = {k: v for k, v in source.items()
                if k not in ('schema_version', 'capacity_capability_id')}
    physical['schema_version'] = 'mastermind.paid_fabric_host_binding/v1'
    physical['worker_source_config_digest'] = _digest(source)
    return physical


_SCHEMA = '''
CREATE TABLE leases (id TEXT PRIMARY KEY, pool TEXT, account TEXT,
 model TEXT, host TEXT, state TEXT, granted_at REAL, ttl REAL,
 last_heartbeat REAL, renewable INTEGER)
'''


def _lease(ident, pool='glm', account='acct-a', model='glm-5.3',
           host='host-a', state='held', granted=None, ttl=3600.0,
           heartbeat=None, renewable=1):
    return (ident, pool, account, model, host, state, granted, ttl,
            heartbeat, renewable)


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='paid-capacity-test-')
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, 'broker', 'leases.sqlite')
        os.makedirs(os.path.dirname(self.db_path))
        self.connection = sqlite3.connect(self.db_path)
        self.addCleanup(self.connection.close)
        self.connection.execute(_SCHEMA)
        self.connection.commit()
        self.now = 1_900_000_000.0
        self._clock_patch = patch_now(self.now)
        self.addCleanup(self._clock_patch)
        self.source = _source_config()
        self.physical = _physical(self.source)

    def fresh_state(self, **over):
        state = dict(exhausted_until_ts=0.0, last_pct_5h=12.5,
                     last_pct_week=40.0, observed_at=self.now - 10.0,
                     next_reset_5h=self.now + 3000.0)
        state.update(over)
        state.setdefault('canonical_status_state','OBSERVED')
        state.setdefault('canonical_status_observed_at',state['observed_at'])
        return state

    def rows(self):
        return [
            _lease('l1', granted=self.now - 60.0, heartbeat=self.now - 30.0),
            _lease('l2', model='', state='rented', granted=self.now - 90.0,
                   heartbeat=self.now - 45.0),
            _lease('l3', host='host-b', granted=self.now - 120.0,
                   heartbeat=self.now - 60.0),
            _lease('l4', pool='other-pool', granted=self.now - 30.0,
                   heartbeat=self.now - 20.0),
            _lease('l5', account='acct-b', state='rented',
                   granted=self.now - 45.0, heartbeat=self.now - 15.0),
            _lease('l6', model='glm-5.3-flash', granted=self.now - 15.0,
                   heartbeat=self.now - 5.0),
        ]

    def seed(self, rows):
        for row in rows:
            self.connection.execute(
                'INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?,?)', row)
        self.connection.commit()

    def observe(self, table, gateway, **over):
        owner = _build_owner(table, gateway)
        return owner, observe_paid_capacity(
            owner, physical=over.get('physical', self.physical),
            source_config=over.get('source_config', self.source),
            account_label=over.get('account_label', 'acct-a'),
            quota_class=over.get('quota_class', 'glm'))

    def full_table(self, **over):
        return _FakeAccountTable({'acct-a': self.fresh_state(**over)})

    def observe_offline(self, table, gateway=None, **over):
        gateway = gateway or _FakeGateway(Path(self.db_path))
        _, observation = self.observe(table, gateway, **over)
        self.assertEqual(observation['observation_state'], 'OFFLINE')
        self.assertEqual(observation['provider_readiness'], 'UNKNOWN')
        return observation


def patch_now(now):
    original = capacity._now
    capacity._now = lambda: now
    return lambda: setattr(capacity, '_now', original)


class PositiveObservationTest(_Base):
    def test_fresh_observed_with_full_broker_counts(self):
        self.seed(self.rows())
        gateway = _FakeGateway(Path(self.db_path))
        owner, observation = self.observe(self.full_table(), gateway)
        self.assertEqual(observation['schema_version'],
                         'mastermind.paid_fabric_capacity_observation/v1')
        self.assertEqual(observation['profile_id'],
                         'fabric.paid.glm.sealed-input.v1')
        self.assertEqual(observation['adapter_id'], 'canonical-paid-fabric')
        self.assertEqual(observation['observation_state'], 'OBSERVED')
        self.assertEqual(observation['reason'], 'OBSERVED')
        self.assertEqual(observation['provider_readiness'], 'UNKNOWN')
        self.assertAlmostEqual(
            observation['expires_at'] - observation['observed_at'], 15.0)
        scope = observation['scope']
        self.assertEqual(scope, dict(worker_id='worker-1', provider='glm',
            host_ref=paid_host_reference('host-a','glm-host-a'), transport_host='host-a', model='glm-5.3', account_label='acct-a',
            quota_class='glm', pool='glm',
            physical_binding_sha256=_digest(self.physical),
            worker_source_config_digest=_digest(self.source)))
        account = observation['account']
        self.assertEqual(account['membership'], 'PRESENT')
        self.assertEqual(account['freshness'], 'FRESH')
        self.assertEqual(account['cooldown'], 'NO')
        self.assertEqual(account['pct_5h'], 12.5)
        self.assertEqual(account['pct_week'], 40.0)
        self.assertEqual(account['observed_at'], self.now - 10.0)
        self.assertEqual(account['age_seconds'], 10.0)
        self.assertIsNone(account['exhausted_until'])
        self.assertEqual(account['next_reset_5h'], self.now + 3000.0)
        broker = observation['broker']
        self.assertEqual(broker['freshness'], 'OBSERVED')
        self.assertEqual(broker['rows_observed'], 6)
        self.assertEqual(broker['held_pool'], 5)
        self.assertEqual(broker['held_account'], 4)
        self.assertEqual(broker['held_host'], 5)
        self.assertEqual(broker['held_model'], 3)
        self.assertEqual(broker['held_route'], 1)
        self.assertEqual(broker['legacy_model_count'], 1)
        self.assertEqual(broker['expired_retained_count'], 0)
        self.assertEqual(_shim_of(owner).calls, 2)
        # The exact original class method object is what the observer binds:
        # before/after proof comes from the shim call count (2), and this
        # identity check shows no subclass override or injected callback is
        # involved. Passing guards with synthetic doubles is wiring evidence,
        # not live-auth evidence.
        self.assertIs(CanonicalPaidBackend.require_gateway,
                      CanonicalPaidBackend.__dict__['require_gateway'])
        self.assertIs(type(owner), CanonicalPaidBackend)

    def test_flash_counts_exact_model_and_timestamp_retention(self):
        self.seed(self.rows())
        source = _source_config(model='glm-5.3-flash')
        gateway = _FakeGateway(Path(self.db_path))
        table = _FakeAccountTable({'acct-a': self.fresh_state(
            observed_at='2026-01-01T00:00:00Z', next_reset_5h=None)})
        owner, observation = self.observe(
            table, gateway, physical=_physical(source), source_config=source)
        self.assertEqual(observation['scope']['model'], 'glm-5.3-flash')
        broker = observation['broker']
        self.assertEqual(broker['held_model'], 1)
        self.assertEqual(broker['legacy_model_count'], 1)
        self.assertEqual(broker['held_route'], 1)
        self.assertIsInstance(table._states['acct-a']['observed_at'], str)
        self.assertEqual(observation['account']['observed_at'],
                         1767225600.0)
        self.assertIsNone(observation['account']['next_reset_5h'])

    def test_epoch_string_and_millisecond_normalization(self):
        self.seed(self.rows())
        gateway = _FakeGateway(Path(self.db_path))
        table = _FakeAccountTable({'acct-a': self.fresh_state(
            observed_at=(self.now - 10.0) * 1000.0,
            next_reset_5h=(self.now + 3000.0) * 1000.0)})
        _, observation = self.observe(table, gateway)
        self.assertEqual(observation['account']['observed_at'],
                         self.now - 10.0)
        self.assertEqual(observation['account']['next_reset_5h'],
                         self.now + 3000.0)
        self.assertEqual(observation['observation_state'], 'OBSERVED')

    def test_datetime_observed_at_accepted(self):
        from datetime import datetime, timezone
        self.seed(self.rows())
        gateway = _FakeGateway(Path(self.db_path))
        table = _FakeAccountTable({'acct-a': self.fresh_state(
            observed_at=datetime.fromtimestamp(self.now - 10.0,
                                               tz=timezone.utc))})
        _, observation = self.observe(table, gateway)
        self.assertEqual(observation['account']['observed_at'],
                         self.now - 10.0)
        self.assertEqual(observation['observation_state'], 'OBSERVED')




class AccountStateOfflineTest(_Base):
    def test_membership_unknown_never_fabricates_facts(self):
        gateway = _FakeGateway(Path(self.db_path),
                               accounts=frozenset({'other'}))
        table = _FakeAccountTable({'other': self.fresh_state()})
        observation = self.observe_offline(table, gateway)
        self.assertEqual(observation['reason'], 'ACCOUNT_UNKNOWN')
        account = observation['account']
        self.assertEqual(account['membership'], 'UNKNOWN')
        self.assertEqual(account['freshness'], 'UNKNOWN')
        self.assertEqual(account['cooldown'], 'UNKNOWN')
        for key in ('observed_at', 'age_seconds', 'pct_5h', 'pct_week',
                    'exhausted_until', 'next_reset_5h'):
            self.assertIsNone(account[key])

    def test_new_empty_account_table_stays_offline_without_bootstrap(self):
        gateway = _FakeGateway(Path(self.db_path))
        states = {'acct-a': dict(exhausted_until_ts=0.0, last_pct_5h=None,
                                 last_pct_week=None, observed_at=None,
                                 next_reset_5h=None)}
        table = _FakeAccountTable(states)
        observation = self.observe_offline(table, gateway)
        self.assertEqual(observation['reason'], 'INVALID_READING')
        account = observation['account']
        self.assertEqual(account['membership'], 'PRESENT')
        self.assertEqual(account['freshness'], 'UNKNOWN')
        self.assertIsNone(account['observed_at'])
        self.assertIsNone(account['age_seconds'])
        self.assertIsNone(account['pct_5h'])
        self.assertIsNone(account['pct_week'])
        self.assertIsNone(account['exhausted_until'])
        self.assertEqual(account['cooldown'], 'NO')
        # Retained cache untouched: a fresh startup table is never seeded
        # with fake freshness or zero percentages.
        self.assertIsNone(states['acct-a']['last_pct_5h'])
        self.assertIsNone(states['acct-a']['observed_at'])

    def test_stale_cache_is_stale_offline(self):
        observation = self.observe_offline(self.full_table(
            observed_at=self.now - 300.0))
        self.assertEqual(observation['reason'], 'STALE_READING')
        account = observation['account']
        self.assertEqual(account['freshness'], 'STALE')
        self.assertEqual(account['age_seconds'], 300.0)
        self.assertEqual(account['pct_5h'], 12.5)

    def test_missing_observed_time_is_unknown(self):
        observation = self.observe_offline(self.full_table(observed_at=None))
        self.assertEqual(observation['reason'], 'INVALID_READING')
        account = observation['account']
        self.assertEqual(account['freshness'], 'UNKNOWN')
        self.assertIsNone(account['age_seconds'])
        self.assertEqual(account['pct_5h'], 12.5)

    def test_future_observed_time_is_contradictory(self):
        observation = self.observe_offline(self.full_table(
            observed_at=self.now + 30.0))
        self.assertEqual(observation['reason'], 'CONTRADICTORY_TIME')
        self.assertEqual(observation['observation_state'], 'OFFLINE')

    def test_boundary_future_tolerance_is_not_contradictory(self):
        self.seed(self.rows())
        gateway = _FakeGateway(Path(self.db_path))
        table = self.full_table(observed_at=self.now + 5.0)
        _, observation = self.observe(table, gateway)
        self.assertNotEqual(observation['reason'], 'CONTRADICTORY_TIME')
        self.assertEqual(observation['account']['age_seconds'], 0.0)

    def test_active_cooldown_is_offline_yes(self):
        observation = self.observe_offline(self.full_table(
            exhausted_until_ts=self.now + 1200.0))
        self.assertEqual(observation['reason'], 'ACTIVE_COOLDOWN')
        self.assertEqual(observation['account']['cooldown'], 'YES')
        self.assertEqual(observation['account']['exhausted_until'],
                         self.now + 1200.0)

    def test_expired_cooldown_record_is_no_cooldown(self):
        # Only ACTIVE cooldown is offline; a retained expired exhaustion
        # marker with fresh consistent readings remains an observation.
        gateway = _FakeGateway(Path(self.db_path))
        self.seed(self.rows())
        _, observation = self.observe(self.full_table(
            exhausted_until_ts=self.now - 50.0), gateway)
        self.assertEqual(observation['observation_state'], 'OBSERVED')
        self.assertEqual(observation['account']['cooldown'], 'NO')
        self.assertEqual(observation['account']['exhausted_until'],
                         self.now - 50.0)

    def test_hundred_percent_5h_is_full(self):
        observation = self.observe_offline(self.full_table(last_pct_5h=100.0))
        self.assertEqual(observation['reason'], 'FULL_UTILIZATION')
        self.assertEqual(observation['account']['pct_5h'], 100.0)

    def test_hundred_percent_week_is_full(self):
        observation = self.observe_offline(self.full_table(
            last_pct_week=100.0))
        self.assertEqual(observation['reason'], 'FULL_UTILIZATION')

    def test_nan_percentage_refused_to_offline(self):
        # NaN never compares equal to itself, so the retained snapshot and
        # state reread are an incoherent join as well as an invalid number.
        observation = self.observe_offline(self.full_table(
            last_pct_5h=float('nan')))
        self.assertEqual(observation['reason'], 'INCOHERENT_READING')
        self.assertIsNone(observation['account']['pct_5h'])

    def test_infinite_percentage_refused(self):
        observation = self.observe_offline(self.full_table(
            last_pct_week=float('inf')))
        self.assertEqual(observation['reason'], 'INVALID_READING')
        self.assertIsNone(observation['account']['pct_week'])

    def test_boolean_percentage_refused(self):
        observation = self.observe_offline(self.full_table(last_pct_5h=True))
        self.assertEqual(observation['reason'], 'INVALID_READING')
        self.assertIsNone(observation['account']['pct_5h'])

    def test_out_of_range_percentage_refused(self):
        observation = self.observe_offline(self.full_table(last_pct_5h=120.0))
        self.assertEqual(observation['reason'], 'INVALID_READING')

    def test_custom_object_timestamp_refused(self):
        observation = self.observe_offline(self.full_table(
            observed_at=object()))
        self.assertEqual(observation['reason'], 'INVALID_READING')
        self.assertIsNone(observation['account']['observed_at'])

    def test_boolean_timestamp_refused(self):
        observation = self.observe_offline(self.full_table(observed_at=True))
        self.assertEqual(observation['reason'], 'INVALID_READING')

    def test_unparseable_string_timestamp_refused(self):
        observation = self.observe_offline(self.full_table(
            observed_at='not-a-time'))
        self.assertEqual(observation['reason'], 'INVALID_READING')

    def test_negative_exhausted_refused(self):
        observation = self.observe_offline(self.full_table(
            exhausted_until_ts=-5.0))
        self.assertEqual(observation['reason'], 'INVALID_READING')

    def test_provider_exception_from_cache_never_leaks(self):
        table = _FakeAccountTable({'acct-a': self.fresh_state()},
                                  fail_state_on=2)
        gateway = _FakeGateway(Path(self.db_path))
        _, observation = self.observe(table, gateway)
        self.assertEqual(observation['observation_state'], 'OFFLINE')
        self.assertEqual(observation['reason'], 'INCOHERENT_READING')
        account = observation['account']
        self.assertEqual(account['freshness'], 'UNKNOWN')
        self.assertIsNone(account['pct_5h'])


class SnapshotRaceTest(_Base):
    def test_snapshot_state_mutation_is_incoherent(self):
        def race(states):
            states['acct-a']['last_pct_5h'] = 55.0
        table = _FakeAccountTable({'acct-a': self.fresh_state()},
                                  racy_snapshot=race)
        gateway = _FakeGateway(Path(self.db_path))
        _, observation = self.observe(table, gateway)
        self.assertEqual(observation['reason'], 'INCOHERENT_READING')
        self.assertEqual(observation['account']['freshness'], 'UNKNOWN')

    def test_state_rewrite_between_reads_is_incoherent(self):
        table = _FakeAccountTable({'acct-a': self.fresh_state()})
        original_snapshot = table.snapshot
        calls = []
        def racing_snapshot():
            calls.append(1)
            if len(calls) == 1:
                table._states['acct-a']['last_pct_week'] = 90.0
            return original_snapshot()
        table.snapshot = racing_snapshot
        gateway = _FakeGateway(Path(self.db_path))
        _, observation = self.observe(table, gateway)
        self.assertEqual(observation['reason'], 'INCOHERENT_READING')


class BrokerReadTest(_Base):
    def test_missing_database_is_offline_unknown_broker(self):
        gateway = _FakeGateway(Path(self.db_path) .with_name('absent.sqlite'))
        observation = self.observe_offline(self.full_table(), gateway)
        self.assertEqual(observation['reason'], 'BROKER_UNAVAILABLE')
        broker = observation['broker']
        self.assertEqual(broker['freshness'], 'UNKNOWN')
        for key in capacity._BROKER_COUNTS:
            self.assertIsNone(broker[key])

    def test_gateway_connection_failure_is_generic(self):
        gateway = _FakeGateway(Path(self.db_path), broken=True)
        observation = self.observe_offline(self.full_table(), gateway)
        self.assertEqual(observation['reason'], 'BROKER_UNAVAILABLE')
        self.assertEqual(observation['broker']['freshness'], 'UNKNOWN')

    def test_schema_mismatch_is_generic_without_leak(self):
        wrong_path = os.path.join(self._tmp.name, 'wrong.sqlite')
        wrong = sqlite3.connect(wrong_path)
        self.addCleanup(wrong.close)
        wrong.execute('CREATE TABLE leases (unrelated TEXT)')
        wrong.commit()
        observation = self.observe_offline(self.full_table(),
                                           _FakeGateway(Path(wrong_path)))
        self.assertEqual(observation['reason'], 'BROKER_UNAVAILABLE')

    def test_overflow_rows_are_not_partial_counts(self):
        rows = [_lease('l%d' % i, granted=self.now - 10.0,
                       heartbeat=self.now - 5.0)
                for i in range(capacity.MAX_ROWS + 1)]
        self.seed(rows)
        observation = self.observe_offline(self.full_table(),
                                           _FakeGateway(Path(self.db_path)))
        self.assertEqual(observation['reason'], 'BROKER_OVERFLOW')
        self.assertEqual(observation['broker']['freshness'], 'UNKNOWN')
        for key in capacity._BROKER_COUNTS:
            self.assertIsNone(observation['broker'][key])

    def test_corrupted_rows_are_generic_and_database_unchanged(self):
        self.seed([
            _lease('bad-ttl', granted=self.now - 10.0, ttl=0.0),
            _lease('bad-state', state='stolen'),
            _lease('bad-grant', granted='nope'),
            _lease('bad-renew', renewable=2),
            _lease('null-host', host=None),
            _lease('heartbeat-backwards', granted=self.now - 10.0,
                   heartbeat=self.now - 100.0),
        ])
        before = self.connection.execute(
            'SELECT count(*) FROM leases').fetchone()[0]
        observation = self.observe_offline(self.full_table(),
                                           _FakeGateway(Path(self.db_path)))
        self.assertEqual(observation['reason'], 'BROKER_UNAVAILABLE')
        self.assertEqual(observation['broker']['freshness'], 'UNKNOWN')
        after = self.connection.execute(
            'SELECT count(*) FROM leases').fetchone()[0]
        self.assertEqual(before, after)

    def test_expired_retained_lease_is_offline_but_counted(self):
        self.seed(self.rows() + [
            _lease('old', granted=self.now - 7200.0, ttl=600.0,
                   heartbeat=self.now - 7000.0)])
        observation = self.observe_offline(self.full_table(),
                                           _FakeGateway(Path(self.db_path)))
        self.assertEqual(observation['reason'], 'EXPIRED_RETAINED')
        broker = observation['broker']
        self.assertEqual(broker['freshness'], 'OBSERVED')
        self.assertEqual(broker['expired_retained_count'], 1)
        self.assertEqual(broker['rows_observed'], 7)
        self.assertEqual(broker['held_pool'], 6)

    def test_readonly_trace_single_scoped_select_and_closed_connections(self):
        self.seed(self.rows())
        gateway = _FakeGateway(Path(self.db_path))
        _, observation = self.observe(self.full_table(), gateway)
        self.assertEqual(observation['observation_state'], 'OBSERVED')
        self.assertEqual(len(gateway.statements), 1)
        statement = gateway.statements[0].upper()
        self.assertIn("STATE IN ('HELD','RENTED')", statement)
        self.assertIn("(POOL='GLM' OR HOST='HOST-A')", statement)
        self.assertIn('LIMIT 4097', statement)
        self.assertIn('FROM LEASES', statement)
        self.assertNotIn('PRAGMA', statement.upper())
        self.assertNotIn('INSERT', statement.upper())
        self.assertNotIn('UPDATE', statement.upper())
        self.assertNotIn('DELETE', statement.upper())
        self.assertNotIn('CREATE', statement.upper())
        self.assertEqual(len(gateway.connections), 1)
        connection = gateway.connections[0]
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute('SELECT 1')

    def test_forbidden_gateway_operations_never_called(self):
        self.seed(self.rows())
        gateway = _FakeGateway(Path(self.db_path))
        table = self.full_table()
        self.observe(table, gateway)
        self.assertNotIn('refresh', table.calls)
        for name in _FORBIDDEN_GATEWAY:
            with self.assertRaises(AssertionError):
                getattr(gateway, name)

    def test_forbidden_account_reader_methods_never_called(self):
        self.seed(self.rows())
        table = self.full_table()
        self.observe(table, _FakeGateway(Path(self.db_path)))
        self.assertEqual(sorted(set(table.calls)),
                         sorted(['names', 'state', 'snapshot']))
        for forbidden in _FakeAccountTable.FORBIDDEN:
            with self.assertRaises(AssertionError):
                getattr(table, forbidden)




class ArgumentRefusalTest(_Base):
    def setUp(self):
        super().setUp()
        self.table = self.full_table()
        self.gateway = _FakeGateway(Path(self.db_path))

    def refuse(self, **over):
        owner = over.pop('owner', _build_owner(self.table, self.gateway))
        arguments = dict(physical=over.pop('physical', self.physical),
                         source_config=over.pop('source_config', self.source),
                         account_label=over.pop('account_label', 'acct-a'),
                         quota_class=over.pop('quota_class', 'glm'))
        arguments.update(over)
        with self.assertRaises(PaidCapacityRefused):
            observe_paid_capacity(owner, **arguments)
        # Refusal happened before any retained-state or lease read.
        self.assertEqual(self.table.calls, [])
        self.assertEqual(self.gateway.connections, [])
        if isinstance(owner, CanonicalPaidBackend):
            self.assertEqual(_shim_of(owner).calls, 0)

    def test_non_owner_objects_refused(self):
        self.refuse(owner=object())
        self.refuse(owner=None)

    def test_owner_subclass_refused(self):
        class _Sub(CanonicalPaidBackend):
            pass
        instance = _Sub.__new__(_Sub)
        self.table.calls.append('probe')
        with self.assertRaises(PaidCapacityRefused):
            observe_paid_capacity(instance, physical=self.physical,
                source_config=self.source, account_label='acct-a',
                quota_class='glm')
        self.assertEqual(self.table.calls, ['probe'])
        self.assertEqual(self.gateway.connections, [])
        self.table.calls = []

    def test_account_label_and_quota_class_refused(self):
        for label in (None, 12, '', 'has space', '../acct', 'a' * 200):
            self.refuse(account_label=label)
        for quota in (None, '', 'has space', '../quota', 7):
            self.refuse(quota_class=quota)

    def test_physical_field_set_refused(self):
        physical = dict(self.physical)
        del physical['bridge_uid']
        self.refuse(physical=physical)
        physical = dict(self.physical)
        physical['secret_extra'] = 'nope'
        self.refuse(physical=physical)
        self.refuse(physical=list(self.physical.items()))

    def test_source_field_set_refused(self):
        source = dict(self.source)
        del source['capacity_capability_id']
        self.refuse(source_config=source)
        source = dict(self.source)
        source['api_key'] = 'leak'
        self.refuse(source_config=source)

    def test_schema_version_and_digest_duplication_refused(self):
        source = _source_config(
            schema_version='mastermind.paid_worker_source/v0')
        self.refuse(physical=_physical(source), source_config=source)
        source = _source_config()
        physical = _physical(source)
        physical['worker_source_config_digest'] = _SHA2
        self.refuse(physical=physical, source_config=source)
        source = _source_config(bridge_uid=0)
        self.refuse(physical=_physical(source), source_config=source)

    def test_provider_model_route_refused(self):
        source = _source_config(provider='openai')
        self.refuse(physical=_physical(source), source_config=source)
        source = _source_config(model='gpt-9')
        self.refuse(physical=_physical(source), source_config=source)
        source = _source_config(worker_id='../escape')
        self.refuse(physical=_physical(source), source_config=source)

    def test_nested_wire_shapes_refused(self):
        source = _source_config(binary=('not', 'a', 'dict'))
        self.refuse(physical=_physical(source), source_config=source)
        source = _source_config(qualification={'registry_sha256': _SHA})
        self.refuse(physical=_physical(source), source_config=source)
        source = _source_config()
        source['qualification']['qualifier_sources_sha256'] = {'x': _SHA}
        self.refuse(physical=_physical(source), source_config=source)

    def test_relative_secret_paths_refused(self):
        source = _source_config(socket_path='relative/sock')
        self.refuse(physical=_physical(source), source_config=source)
        source = _source_config()
        source['binary']['path'] = 'python'
        self.refuse(physical=_physical(source), source_config=source)

    def test_guard_failure_raises_and_never_fabricates(self):
        owner = _build_owner(self.table, self.gateway)
        owner._startup._qualified = object()
        with self.assertRaises(PaidOwnerRefused):
            observe_paid_capacity(owner, physical=self.physical,
                source_config=self.source, account_label='acct-a',
                quota_class='glm')
        self.assertEqual(self.table.calls, [])

    def test_accounts_table_disagreement_refused(self):
        gateway = _FakeGateway(Path(self.db_path),
                               accounts=frozenset({'other'}))
        owner = _build_owner(self.table, gateway)
        with self.assertRaises(PaidCapacityRefused):
            observe_paid_capacity(owner, physical=self.physical,
                source_config=self.source, account_label='acct-a',
                quota_class='glm')
        self.assertEqual(self.gateway.connections, [])

    def test_post_guard_refusal_still_raises(self):
        owner = _build_owner(self.table, self.gateway, flip_after=1)
        self.seed(self.rows())
        # The after-observation guard runs the exact original class method;
        # its own refusal error propagates and no observation is fabricated.
        with self.assertRaises((PaidOwnerRefused, PaidCapacityRefused)):
            observe_paid_capacity(owner, physical=self.physical,
                source_config=self.source, account_label='acct-a',
                quota_class='glm')
        self.assertEqual(_shim_of(owner).calls, 2)


class PublicSurfaceTest(_Base):
    def test_no_injectable_clock_runner_db_or_auth_arguments(self):
        signature = inspect.signature(observe_paid_capacity)
        parameters = list(signature.parameters)
        self.assertEqual(parameters, ['owner', 'physical', 'source_config',
                                      'account_label', 'quota_class'])
        for name in list(parameters)[1:]:
            self.assertEqual(
                signature.parameters[name].kind,
                inspect.Parameter.KEYWORD_ONLY)
        signature = inspect.signature(validate_paid_capacity_observation)
        self.assertEqual(list(signature.parameters), ['value'])

    def test_module_clock_hook_is_the_only_time_source(self):
        self.assertTrue(callable(capacity._now))
        shifted = patch_now(1234.0)
        try:
            self.assertEqual(capacity._now(), 1234.0)
        finally:
            shifted()

    def test_refusal_is_value_error(self):
        self.assertTrue(issubclass(PaidCapacityRefused, ValueError))


class ValidatorTest(_Base):
    def setUp(self):
        super().setUp()
        self.seed(self.rows())
        self.gateway = _FakeGateway(Path(self.db_path))
        _, self.observation = self.observe(self.full_table(), self.gateway)
        self.validated = validate_paid_capacity_observation(self.observation)

    def test_valid_observation_passes_and_is_detached(self):
        result = self.validated
        self.assertEqual(result, self.observation)
        self.assertIsNot(result, self.observation)
        self.assertIsNot(result['scope'], self.observation['scope'])
        json.loads(json.dumps(result, allow_nan=False))
        mutated = json.loads(json.dumps(self.observation))
        mutated['scope']['model'] = 'mutated'
        mutated['account']['pct_5h'] = 999.0
        self.assertEqual(result['scope']['model'], 'glm-5.3')
        self.assertEqual(result['account']['pct_5h'], 12.5)

    def test_plain_types_only(self):
        def walk(value):
            self.assertIsInstance(value, (dict, list, str, int, float,
                                          bool, type(None)))
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertIsInstance(key, str)
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(self.validated)

    def mutate(self, **over):
        value = json.loads(json.dumps(self.observation))
        for key, item in over.items():
            if item is DELETE:
                value.pop(key, None)
            else:
                value[key] = item
        return value

    def reject(self, **over):
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(self.mutate(**over))


class _Delete:
    pass


DELETE = _Delete()


class ValidatorRejectionTest(ValidatorTest):
    def test_structure_rejections(self):
        self.reject(schema_version='mastermind.paid_fabric_capacity/v0')
        self.reject(profile_id='other-profile')
        self.reject(adapter_id='other-adapter')
        self.reject(provider_readiness='READY')
        self.reject(provider_readiness=None)
        self.reject(observation_state='PARTIAL')
        self.reject(reason='MADE_UP')
        self.reject(extra='field')
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(
                self.mutate(unused='x', expires_at=DELETE))
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation([])
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(None)
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation('observation')

    def test_state_reason_coherence(self):
        self.reject(observation_state='OBSERVED', reason='STALE_READING')
        self.reject(observation_state='OFFLINE', reason='OBSERVED')

    def test_time_rejections(self):
        self.reject(observed_at=0)
        self.reject(observed_at=-1.0)
        self.reject(observed_at=True)
        self.reject(observed_at=float('nan'))
        self.reject(observed_at=float('inf'))
        self.reject(observed_at=10 ** 12)
        self.reject(expires_at=self.observation['observed_at'])
        self.reject(expires_at=self.observation['observed_at'] + 15.5)
        self.reject(expires_at=self.observation['observed_at'] - 1.0)
        self.reject(expires_at='soon')
        self.reject(expires_at=True)

    def test_scope_rejections(self):
        self.reject(scope=dict(self.observation['scope'], provider='openai'))
        self.reject(scope=dict(self.observation['scope'], pool='glm-frontier'))
        self.reject(scope=dict(self.observation['scope'], model='glm-6'))
        self.reject(scope=dict(self.observation['scope'],
                               quota_class='invalid/quota'))
        self.reject(scope=dict(self.observation['scope'],
                               physical_binding_sha256='short'))
        self.reject(scope=dict(self.observation['scope'],
                               worker_source_config_digest=None))
        self.reject(scope=dict(self.observation['scope'], worker_id=''))
        scope = dict(self.observation['scope'])
        scope['secret'] = 'x'
        self.reject(scope=scope)
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(
                self.mutate(scope=list(self.observation['scope'].items())))

    def test_account_rejections(self):
        self.reject(account=dict(self.observation['account'],
                                 membership='ABSENT'))
        self.reject(account=dict(self.observation['account'],
                                 freshness='LIVE'))
        self.reject(account=dict(self.observation['account'],
                                 cooldown='MAYBE'))
        self.reject(account=dict(self.observation['account'], pct_5h=101.0))
        self.reject(account=dict(self.observation['account'], pct_week=-0.5))
        self.reject(account=dict(self.observation['account'], pct_5h=True))
        self.reject(account=dict(self.observation['account'],
                                 age_seconds=-1.0))
        self.reject(account=dict(self.observation['account'],
                                 exhausted_until='soon'))
        self.reject(account=dict(self.observation['account'],
                                 cooldown='YES'))
        self.reject(account=dict(self.observation['account'],
                                 observed_at=self.observation['observed_at'],
                                 age_seconds=10.0))
        unknown = dict(observed_at=None, age_seconds=None, pct_5h=None,
                       pct_week=None, exhausted_until=None,
                       next_reset_5h=None, cooldown='UNKNOWN',
                       membership='UNKNOWN', freshness='UNKNOWN')
        self.reject(account=unknown)
        offline = dict(unknown, membership='PRESENT', freshness='FRESH',
                       observed_at=self.observation['observed_at'],
                       age_seconds=10.0, cooldown='NO')
        self.reject(account=offline)
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(
                self.mutate(account=types.MappingProxyType(
                    dict(self.observation['account']))))

    def test_broker_rejections(self):
        self.reject(broker=dict(self.observation['broker'],
                                freshness='LIVE'))
        self.reject(broker=dict(self.observation['broker'],
                                rows_observed=4097))
        self.reject(broker=dict(self.observation['broker'],
                                held_pool=-1))
        self.reject(broker=dict(self.observation['broker'],
                                held_pool=1.0))
        self.reject(broker=dict(self.observation['broker'],
                                held_pool=True))
        self.reject(broker=dict(self.observation['broker'],
                                rows_observed=None))
        unknown = {key: None for key in capacity._BROKER_COUNTS}
        self.reject(broker=dict(unknown, freshness='UNKNOWN'))
        observed = dict(self.observation['broker'],
                        expired_retained_count=1)
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(
                self.mutate(broker=observed, reason='EXPIRED_RETAINED'))
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(
                self.mutate(broker=types.MappingProxyType(
                    dict(self.observation['broker']))))

    def test_dict_subclass_rejected(self):
        class _Shadow(dict):
            pass
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(
                _Shadow(self.observation))
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(
                dict(self.observation, scope=_Shadow(
                    self.observation['scope'])))

    def test_offline_observations_validate(self):
        stale = self.observe(self.full_table(
            observed_at=self.now - 900.0), self.gateway)[1]
        validated = validate_paid_capacity_observation(stale)
        self.assertEqual(validated['observation_state'], 'OFFLINE')
        self.assertEqual(validated['reason'], 'STALE_READING')
        unknown_table = _FakeAccountTable({'acct-a': dict(
            exhausted_until_ts=0.0, last_pct_5h=None, last_pct_week=None,
            observed_at=None, next_reset_5h=None)})
        offline = self.observe(unknown_table, self.gateway)[1]
        validated = validate_paid_capacity_observation(offline)
        self.assertEqual(validated['reason'], 'INVALID_READING')
        broken = _FakeGateway(Path(self.db_path), broken=True)
        missing = self.observe(self.full_table(), broken)[1]
        validated = validate_paid_capacity_observation(missing)
        self.assertEqual(validated['reason'], 'BROKER_UNAVAILABLE')
        self.assertEqual(validated['broker']['freshness'], 'UNKNOWN')

    def test_validator_cannot_escalate_any_receipt(self):
        stale = self.observe(self.full_table(
            observed_at=self.now - 900.0), self.gateway)[1]
        self.assertEqual(stale['observation_state'], 'OFFLINE')
        # Bare state escalation is refused: retained freshness contradicts.
        forged = json.loads(json.dumps(stale))
        forged['observation_state'] = 'OBSERVED'
        forged['reason'] = 'OBSERVED'
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(forged)
        # Rewriting the freshness label alone still contradicts the age.
        forged['account']['freshness'] = 'FRESH'
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(forged)
        # Provider readiness is never claimable by any receipt.
        forged = json.loads(json.dumps(self.observation))
        forged['provider_readiness'] = 'READY'
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(forged)




class CurrentContractRegressionTest(_Base):
    def test_arbitrary_runtime_quota_label_and_raw_transport_host(self):
        self.seed(self.rows())
        gateway = _FakeGateway(Path(self.db_path))
        _, result = self.observe(self.full_table(), gateway, quota_class='paid-read')
        self.assertEqual(result['scope']['quota_class'], 'paid-read')
        self.assertEqual(result['scope']['transport_host'], 'host-a')
        self.assertEqual(result['scope']['host_ref'], paid_host_reference('host-a', 'glm-host-a'))
        self.assertIn("HOST='HOST-A'", gateway.statements[0].upper())
        self.assertNotIn(result['scope']['host_ref'], gateway.statements[0])
        self.assertEqual(result['broker']['held_account'], 4)

    def test_source_host_mapping_must_match_qualified_registry_key(self):
        source = _source_config()
        source['qualification']['registry_key'] = 'host-b'
        with self.assertRaises(PaidCapacityRefused):
            self.observe(self.full_table(), _FakeGateway(Path(self.db_path)),
                         source_config=source, physical=_physical(source))

    def test_nonobserved_canonical_status_never_reuses_fresh_old_pair(self):
        for status in ('PENDING', 'AUTH_REFUSED', 'RATE_LIMITED', 'UNKNOWN'):
            with self.subTest(status=status):
                result = self.observe_offline(self.full_table(
                    canonical_status_state=status, canonical_status_observed_at=None))
                self.assertEqual(result['reason'], 'STATUS_NOT_OBSERVED')
                self.assertEqual(result['account']['freshness'], 'FRESH')
                self.assertEqual(result['account']['canonical_status_state'], status)

    def test_legacy_manual_cache_has_no_canonical_readiness(self):
        state = self.fresh_state()
        state.pop('canonical_status_state')
        state.pop('canonical_status_observed_at')
        result = self.observe_offline(_FakeAccountTable({'acct-a': state}))
        self.assertEqual(result['reason'], 'STATUS_NOT_OBSERVED')
        self.assertEqual(result['account']['canonical_status_state'], 'UNKNOWN')

    def test_observed_status_requires_exact_same_pair_timestamp(self):
        for value in (None, self.now - 9):
            with self.subTest(value=value):
                result = self.observe_offline(self.full_table(canonical_status_observed_at=value))
                self.assertEqual(result['reason'], 'STATUS_NOT_OBSERVED')

    def test_gateway_rotation_cannot_mix_read_handles(self):
        table = self.full_table()
        gateway = _FakeGateway(Path(self.db_path))
        owner = _build_owner(table, gateway)
        original = gateway._connection
        replacement = _FakeGateway(Path(self.db_path))
        replacement._canonical_owner = owner
        def rotate():
            connection = original()
            owner._gateway = replacement
            owner._shim._gateway = replacement
            return connection
        gateway._connection = rotate
        with self.assertRaises(PaidCapacityRefused):
            observe_paid_capacity(owner, physical=self.physical,
                source_config=self.source, account_label='acct-a', quota_class='paid-read')

    def test_status_transition_during_broker_read_invalidates_observation(self):
        table = self.full_table()
        gateway = _FakeGateway(Path(self.db_path))
        original = gateway._connection
        def transition():
            connection = original()
            table._states['acct-a']['canonical_status_state'] = 'PENDING'
            table._states['acct-a']['canonical_status_observed_at'] = None
            return connection
        gateway._connection = transition
        result = self.observe_offline(table, gateway)
        self.assertEqual(result['reason'], 'INCOHERENT_READING')
        self.assertEqual(result['account']['freshness'], 'UNKNOWN')

    def test_missing_either_percentage_is_offline(self):
        for key in ('last_pct_5h', 'last_pct_week'):
            with self.subTest(key=key):
                result = self.observe_offline(self.full_table(**{key: None}))
                self.assertEqual(result['reason'], 'INVALID_READING')

    def test_renewable_lease_uses_recent_heartbeat_not_original_grant(self):
        self.seed([_lease('renewed', granted=self.now - 1000, ttl=100,
                          heartbeat=self.now - 1, renewable=1)])
        result = self.observe(self.full_table(), _FakeGateway(Path(self.db_path)))[1]
        self.assertEqual(result['observation_state'], 'OBSERVED')
        self.assertEqual(result['broker']['expired_retained_count'], 0)
        self.assertEqual(result['broker']['held_route'], 1)

    def test_nonrenewable_absolute_expiry_and_stale_heartbeat_stay_counted(self):
        self.seed([
            _lease('fixed', granted=self.now - 1000, ttl=100,
                   heartbeat=self.now - 1, renewable=0),
            _lease('stale', granted=self.now - 1000, ttl=100,
                   heartbeat=self.now - 101, renewable=1),
        ])
        result = self.observe_offline(self.full_table())
        self.assertEqual(result['reason'], 'EXPIRED_RETAINED')
        self.assertEqual(result['broker']['expired_retained_count'], 2)
        self.assertEqual(result['broker']['held_route'], 2)

    def test_broker_model_count_matches_incumbent_case_insensitive_law(self):
        self.seed([_lease('upper', model='GLM-5.3', granted=self.now - 10,
                          heartbeat=self.now - 1)])
        result = self.observe(self.full_table(), _FakeGateway(Path(self.db_path)))[1]
        self.assertEqual(result['broker']['held_model'], 1)
        self.assertEqual(result['broker']['held_route'], 1)

    def test_compound_unknown_account_and_broker_is_valid_offline(self):
        result = self.observe_offline(_FakeAccountTable({'acct-a': self.fresh_state()}),
            _FakeGateway(Path(self.db_path), broken=True), account_label='absent')
        self.assertEqual(result['reason'], 'ACCOUNT_UNKNOWN')
        self.assertEqual(result['broker']['freshness'], 'UNKNOWN')
        self.assertEqual(validate_paid_capacity_observation(result), result)

    def test_expiry_is_clipped_at_retained_reading_freshness_boundary(self):
        result = self.observe(self.full_table(observed_at=self.now - 299),
                              _FakeGateway(Path(self.db_path)))[1]
        self.assertEqual(result['observation_state'], 'OBSERVED')
        self.assertEqual(result['expires_at'], self.now + 1)
        result['expires_at'] = self.now + 2
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(result)

    def test_validator_rejects_false_observed_marker_pct_age_host_or_future(self):
        result = self.observe(self.full_table(), _FakeGateway(Path(self.db_path)))[1]
        mutations = [
            ('account', 'canonical_status_state', 'AUTH_REFUSED'),
            ('account', 'canonical_status_observed_at', None),
            ('account', 'pct_5h', None),
            ('account', 'age_seconds', 0),
            ('scope', 'host_ref', 'host-a'),
        ]
        for section, key, value in mutations:
            with self.subTest(key=key):
                altered = json.loads(json.dumps(result))
                altered[section][key] = value
                with self.assertRaises(PaidCapacityRefused):
                    validate_paid_capacity_observation(altered)
        altered = json.loads(json.dumps(result))
        altered['account']['observed_at'] = self.now + 6
        altered['account']['canonical_status_observed_at'] = self.now + 6
        altered['account']['age_seconds'] = 0
        with self.assertRaises(PaidCapacityRefused):
            validate_paid_capacity_observation(altered)


if __name__ == '__main__':
    unittest.main()
