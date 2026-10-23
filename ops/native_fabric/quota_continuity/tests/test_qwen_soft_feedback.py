"""Offline Qwen adaptive-429 soft-mode tests; no provider requests, credentials or live broker.

Real candidate Broker + disposable temp SQLite/lease receipts exercise the full
observe_locked path; only the provider CLI stream is synthetic (the wrapper's
provider_outcome.v1 receipt is test-authored, as in test_quota_continuity).
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'candidate'), str(ROOT / 'source')]
import os
sys.path.insert(0, os.path.dirname(__file__))
from _offline_boundary import acquire as _offline_acquire, release as _offline_release

def setUpModule():
    _offline_acquire()

def tearDownModule():
    _offline_release()

import lease_broker
import provider_outcome as outcome
import quota_circuit as circuit

FEEDBACK_SCHEMA = 'mastermind.qwen_adaptive429_feedback.v1'


def feedback(**over):
    """One closed-shape adaptive-429 policy receipt at the fixture clock."""
    value = dict(schema=FEEDBACK_SCHEMA, account='qa',
        classification_source='qwen_wrapper_inference', classification='429',
        policy_source='bailian_keys.adaptive_http_429', observed_at=1000,
        until_ts=1120, duration_seconds=120, soft_cap=3, soft_cap_enabled=True)
    for key, val in over.items():
        if val is ...:
            value.pop(key, None)
        else:
            value[key] = val
    return value


class QwenSoft(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = [1000.0]
        providers = {}
        for name in ('bailian', 'minimax', 'healthy'):
            spec = {'enabled': True, 'concurrency_cap': 8, 'accounts': [
                {'name': 'qa' if name == 'bailian' else 'account', 'per_account_cap': 8}]}
            if name == 'bailian':
                spec['accounts'].append({'name': 'qb', 'per_account_cap': 8})
                spec['pool_aliases'] = ['bailian-codex']
            if name == 'minimax':
                spec['quota_scope'] = 'same-shared-allowance'
                spec['pool_aliases'] = ['minimax-codex']
            providers[name] = spec
        (self.root / 'accounts.json').write_text(json.dumps({'providers': providers}))
        self.br = self.broker()

    def broker(self):
        return lease_broker.Broker(db_path=str(self.root / 'broker.sqlite'),
            lock_path=str(self.root / 'broker.lock'), accounts_path=str(self.root / 'accounts.json'),
            now_fn=lambda: self.clock[0], check_pid=False, external_gates=False,
            grok_marker=str(self.root / 'no-marker'), this_host='fixture')

    def acquire(self, br=None, pool='bailian', account=None, root='root'):
        return (br or self.br).acquire(root, pool, account=account, model='fixture-model',
                                       host='fixture', task_class='fixture', ttl=1000, wait=0)

    def observe(self, lease, *, kind='unknown', run=None, rc=1, fb=None, mutate=None,
                reset=None, account=None, model='fixture-model', host='fixture',
                root=None, provider=None, observed_at=None):
        run = run or 'run-' + lease.lease_id
        provider = provider if provider is not None else self.br.provider_name(lease.pool)
        value = dict(schema=outcome.SCHEMA, run_id=run, lease_id=lease.lease_id,
            root_id=lease.orchestrator_id if root is None else root,
            provider=provider,
            account=lease.account if account is None else account,
            host=host, model=model, kind=kind, command_rc=rc,
            observed_at=self.clock[0] if observed_at is None else observed_at,
            reset_at=reset, reset_source='provider_event' if reset else None,
            initial_rejection=(kind == 'rate_limit'),
            stdout_sha256=hashlib.sha256(b'').hexdigest())
        if fb is not None:
            value['qwen_policy_feedback'] = dict(fb)
        process = dict(schema='mastermind.local_owned_process_receipt.v1', label=run,
            returncode=rc, stdout_sha256=value['stdout_sha256'], stdout_truncated=False,
            stderr_truncated=False, timed_out=False,
            cleanup=dict(census_proven=True, identity_verified=True, residual_count=0, status='not_needed'))
        if mutate:
            mutate(value, process)
        op, pp = self.root / (run + '.outcome'), self.root / (run + '.process')
        op.write_text(json.dumps(value)); pp.write_text(json.dumps(process))
        import fcntl
        lock = self.br._lock()
        try:
            conn = self.br._conn()
            try:
                return circuit.observe_locked(self.br, conn, lease.lease_id,
                    lease.orchestrator_id if root is None else root, run, op, pp)
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN); lock.close()

    def rows(self):
        conn = self.br._conn()
        try:
            return {r['scope']: dict(r) for r in conn.execute('SELECT * FROM quota_cooldowns')}
        finally:
            conn.close()

    def room(self, pool='bailian', account='qa'):
        conn = self.br._conn()
        try:
            return circuit.admission_room(self.br, conn, pool, {'name': account})
        finally:
            conn.close()

    def cap(self, pool='bailian', account='qa', base=8):
        return circuit.account_cap(self.br, pool, {'name': account}, base)


class Admission(QwenSoft):
    def test_fresh_soft_receipt_records_exact_policy_window(self):
        lease = self.acquire(account='qa')
        self.assertTrue(lease.ok)
        result = self.observe(lease, fb=feedback())
        self.assertFalse(result['duplicate'])
        self.assertFalse(result['initial_rejection'])
        soft = self.rows()['bailian-adaptive429:qa']
        self.assertEqual(soft['mode'], 'SOFT')
        self.assertEqual((soft['observed_at'], soft['until_ts']), (1000, 1120))
        self.assertEqual((soft['soft_cap'], soft['failures']), (3, 1))
        self.assertEqual(soft['reset_source'], 'local_adaptive_policy')
        self.assertEqual(soft['kind'], 'unknown')
        self.assertEqual(soft['source_run'], 'run-' + lease.lease_id)
        self.assertEqual(set(self.rows()), {'bailian-adaptive429:qa'})  # no HARD row
        self.assertFalse(circuit.pool_blocked(self.br, 'bailian'))
        self.assertEqual(self.cap(), 3)
        self.assertTrue(self.room())

    def test_soft_cap_gates_concurrency_then_expiry_restores_base(self):
        lease = self.acquire(account='qa')
        self.observe(lease, fb=feedback())
        extra = [self.acquire(account='qa', root='r%d' % i) for i in range(2)]
        self.assertTrue(all(g.ok for g in extra))
        conn = self.br._conn()
        try:
            self.assertEqual(self.br._account_held(conn, 'bailian', 'qa'), 3)
        finally:
            conn.close()
        fourth = self.acquire(account='qa', root='r9')
        self.assertFalse(fourth.ok)  # exact-account soft cap of 3
        for held in (lease, *extra):
            self.br.release(held.lease_id, held.orchestrator_id)
        self.clock[0] = 1120.5
        self.assertEqual(self.cap(), 8)  # ordinary base, no half-open throttle
        grants = [self.acquire(account='qa', root='x%d' % i) for i in range(8)]
        self.assertTrue(all(g.ok for g in grants), [g.reason for g in grants])
        self.assertFalse(self.acquire(account='qa', root='x9').ok)  # base 8 again

    def test_policy_disabled_preserves_ordinary_base(self):
        lease = self.acquire(account='qa')
        result = self.observe(lease, fb=feedback(soft_cap_enabled=False))
        self.assertEqual(self.rows(), {})  # diagnostic only; ordinary base stands
        self.assertFalse(result['duplicate'])
        self.assertTrue(self.observe(lease, fb=feedback(soft_cap_enabled=False))['duplicate'])
        self.br.release(lease.lease_id, lease.orchestrator_id)
        grants = [self.acquire(account='qa', root='d%d' % i) for i in range(8)]
        self.assertTrue(all(g.ok for g in grants), [g.reason for g in grants])
        self.assertEqual(self.cap(), 8)

    def test_expired_observation_cannot_revive_a_cooldown(self):
        lease = self.acquire(account='qa')
        self.clock[0] = 1200.0
        result = self.observe(lease, fb=feedback(), observed_at=1000)
        self.assertIsNone(result['soft'])  # window 1000..1120 already ended
        self.assertEqual(self.rows(), {})
        self.assertEqual(self.cap(), 8)
        # An existing soft row that later expires stays inert: a stale
        # observation inside the old window cannot revive or extend it.
        l2 = self.acquire(account='qa', root='r2')
        self.observe(l2, fb=feedback(observed_at=1200, until_ts=1320))
        l3 = self.acquire(account='qa', root='r3')  # clock still 1200
        self.clock[0] = 1400.0
        before = self.rows()['bailian-adaptive429:qa']
        self.assertEqual(before['until_ts'], 1320)
        result = self.observe(l3, fb=feedback(observed_at=1200, until_ts=1320),
                              observed_at=1200)
        self.assertIsNone(result['soft'])
        self.assertEqual(self.rows()['bailian-adaptive429:qa'], before)
        self.assertEqual(self.cap(), 8)


class Classification(QwenSoft):
    def test_wrapper_inference_stays_unknown_and_never_hard(self):
        lease = self.acquire(account='qa')
        result = self.observe(lease, kind='unknown',
                              fb=feedback(classification_source='qwen_wrapper_inference'))
        self.assertEqual(result['kind'], 'unknown')
        self.assertFalse(result['initial_rejection'])
        soft = self.rows()['bailian-adaptive429:qa']
        self.assertEqual(soft['kind'], 'unknown')
        self.assertNotIn(circuit.scope_for(self.br, 'bailian', 'qa'), self.rows())

    def test_typed_enum_is_distinct_and_still_never_hard_capacity(self):
        lease = self.acquire(account='qa')
        result = self.observe(lease, kind='rate_limit',
                              fb=feedback(classification_source='codex_error_enum'))
        self.assertEqual(result['kind'], 'rate_limit')
        soft = self.rows()['bailian-adaptive429:qa']
        self.assertEqual(soft['kind'], 'rate_limit')
        self.assertEqual(soft['reset_source'], 'local_adaptive_policy')
        self.assertNotIn(circuit.scope_for(self.br, 'bailian', 'qa'), self.rows())
        self.assertFalse(circuit.pool_blocked(self.br, 'bailian'))
        self.assertEqual(self.cap(), 3)

    def test_non_bailian_provider_never_records_soft(self):
        lease = self.acquire(pool='minimax', account='account')
        with self.assertRaises(ValueError):
            self.observe(lease, fb=feedback(account='account'))
        self.assertEqual(self.rows(), {})


class Refusals(QwenSoft):
    def test_unqualified_feedback_refuses_before_any_mutation(self):
        lease = self.acquire(account='qa')
        cases = [
            ('explicit_null_feedback', dict(kind='rate_limit', fb=feedback(),
                mutate=lambda v, p: v.update(qwen_policy_feedback=None))),
            ('nonliteral_rejection_flag', dict(fb=feedback(),
                mutate=lambda v, p: v.update(initial_rejection=1))),
            ('extra_field', dict(fb=feedback(extra='x'))),
            ('missing_field', dict(fb=feedback(soft_cap=...))),
            ('wrong_schema', dict(fb=feedback(schema=FEEDBACK_SCHEMA + '2'))),
            ('wrong_policy_source', dict(fb=feedback(policy_source='bailian_keys.static'))),
            ('wrong_classification', dict(fb=feedback(classification='500'))),
            ('unknown_source', dict(fb=feedback(classification_source='guess'))),
            ('mixed_source_types', dict(fb=feedback(classification_source=[
                'qwen_wrapper_inference', 'codex_error_enum']))),
            ('wrapper_kind_contradiction', dict(kind='rate_limit', fb=feedback())),
            ('wrapper_rejection_contradiction', dict(
                fb=feedback(), mutate=lambda v, p: v.update(initial_rejection=True))),
            ('enum_kind_contradiction', dict(fb=feedback(classification_source='codex_error_enum'))),
            ('success_rc0', dict(kind='success', rc=0, fb=feedback())),
            ('zero_rc', dict(fb=feedback(), mutate=lambda v, p: v.update(command_rc=0))),
            ('bool_rc', dict(fb=feedback(), mutate=lambda v, p: v.update(command_rc=True))),
            ('api_status_invention', dict(fb=feedback(), mutate=lambda v, p: v.update(api_status=429))),
            ('reset_invention', dict(fb=feedback(), mutate=lambda v, p: v.update(
                reset_at=5000, reset_source='provider_event'))),
            ('wrong_fb_account', dict(fb=feedback(account='qb'))),
            ('float_policy_clock', dict(fb=feedback(observed_at=1000.5, until_ts=1120.5))),
            ('undeclared_duration', dict(fb=feedback(duration_seconds=300, until_ts=1300))),
            ('until_mismatch', dict(fb=feedback(until_ts=2000))),
            ('cap_below_floor', dict(fb=feedback(soft_cap=2))),
            ('cap_above_bound', dict(fb=feedback(soft_cap=100001))),
            ('cap_not_int', dict(fb=feedback(soft_cap='3'))),
            ('enabled_bool_as_int', dict(fb=feedback(soft_cap_enabled=1))),
            ('enabled_string', dict(fb=feedback(soft_cap_enabled='true'))),
            ('stale_observation', dict(fb=feedback(observed_at=900, until_ts=1020))),
            ('historical_backfill', dict(fb=feedback(observed_at=800, until_ts=920))),
            ('future_observation', dict(fb=feedback(observed_at=2000, until_ts=2120))),
            ('wrong_lease', dict(mutate=lambda v, p: v.update(lease_id='other-lease'))),
            ('wrong_root', dict(root='other-root')),
            ('wrong_account', dict(account='qb')),
            ('wrong_model', dict(model='other-model')),
            ('wrong_host', dict(host='other-host')),
        ]
        for name, kwargs in cases:
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.observe(lease, **kwargs)
                self.assertEqual(self.rows(), {})
        # Nothing above bound the lease: a valid receipt still lands.
        result = self.observe(lease, fb=feedback())
        self.assertFalse(result['duplicate'])
        self.assertIn('bailian-adaptive429:qa', self.rows())


class Replay(QwenSoft):
    def test_duplicate_never_extends_and_conflict_never_mutates(self):
        lease = self.acquire(account='qa')
        self.observe(lease, fb=feedback())
        before = self.rows()['bailian-adaptive429:qa']
        self.assertTrue(self.observe(lease, fb=feedback())['duplicate'])
        self.assertEqual(self.rows()['bailian-adaptive429:qa'], before)
        with self.assertRaises(ValueError):
            self.observe(lease, fb=feedback(duration_seconds=1800, until_ts=2800))
        self.assertEqual(self.rows()['bailian-adaptive429:qa'], before)

    def test_later_observation_merges_conservatively(self):
        first = self.acquire(account='qa')
        self.observe(first, fb=feedback())  # until 1120, cap 3
        second = self.acquire(account='qa')
        self.assertTrue(second.ok)
        self.observe(second, fb=feedback(duration_seconds=480, until_ts=1480, soft_cap=5))
        soft = self.rows()['bailian-adaptive429:qa']
        self.assertEqual((soft['until_ts'], soft['soft_cap'], soft['failures']), (1480, 3, 2))
        third = self.acquire(account='qa')
        self.observe(third, fb=feedback(duration_seconds=120, until_ts=1120))
        soft = self.rows()['bailian-adaptive429:qa']
        self.assertEqual((soft['until_ts'], soft['soft_cap']), (1480, 3))  # never shortens

    def test_soft_recorded_while_stronger_hard_hold_retained(self):
        l1 = self.acquire(account='qa')
        l2 = self.acquire(account='qa')
        self.observe(l1, kind='rate_limit', rc=1, reset=5000)
        result = self.observe(l2, fb=feedback())
        hard = self.rows()[circuit.scope_for(self.br, 'bailian', 'qa')]
        self.assertEqual((hard['mode'], hard['until_ts'], hard['failures']),
                         ('HARD', 5000.0, 1))
        self.assertEqual(self.rows()['bailian-adaptive429:qa']['until_ts'], 1120)
        self.assertIsNone(self.cap())  # the stronger HARD hold rules this account
        self.assertTrue(self.observe(l2, fb=feedback())['duplicate'])  # bound anyway
        self.clock[0] = 5060.0
        self.assertEqual(self.cap(), 1)  # hard half-open; soft long expired


class Ordinary(QwenSoft):
    def test_generic_hard_path_and_migration_unchanged(self):
        lease = self.acquire(account='qa')
        self.observe(lease, kind='rate_limit', rc=1)  # bounded backoff, no provider reset
        hard = self.rows()[circuit.scope_for(self.br, 'bailian', 'qa')]
        self.assertEqual(hard['mode'], 'HARD')
        self.assertIsNone(hard['soft_cap'])
        self.assertIsNone(self.cap())  # active HARD hold closes this account
        self.assertIsInstance(self.broker().snapshot(), dict)  # idempotent re-migration
        self.br.release(lease.lease_id, lease.orchestrator_id)
        self.clock[0] += 61
        self.assertEqual(self.cap(), 1)  # ordinary half-open probe
        probe = self.acquire(root='probe')
        self.assertTrue(probe.ok)
        before = self.rows()
        result = self.observe(probe, kind='unknown', rc=1)  # old unknown outcome
        self.assertEqual(result['kind'], 'unknown')
        self.assertEqual(self.rows(), before)  # no cooldown change, no soft row

    def test_shared_hard_scope_never_spreads_one_soft_cap(self):
        path = self.root / 'accounts.json'
        doc = json.loads(path.read_text())
        doc['providers']['bailian']['quota_scope'] = 'shared-bailian-allowance'
        path.write_text(json.dumps(doc))
        self.br._accounts_mtime = None
        lease = self.acquire(account='qa')
        self.observe(lease, fb=feedback())
        self.assertEqual(self.cap(account='qa'), 3)
        self.assertEqual(self.cap(account='qb'), 8)  # deliberate shared HARD scope
        self.assertIsNone(circuit.cooldown(self.br, 'bailian', 'qb'))
        self.assertEqual(self.cap('bailian-codex', 'qa'), 3)  # alias, same account
        self.assertIsNone(circuit.cooldown(self.br, 'bailian-codex', 'qa'))
        qb = [self.acquire(account='qb', root='q%d' % i) for i in range(8)]
        self.assertTrue(all(g.ok for g in qb), [g.reason for g in qb])
        self.assertFalse(self.acquire(account='qb', root='q9').ok)
        snap = {a['name']: a for a in self.br.snapshot()['pools']['bailian']['accounts']}
        self.assertEqual(snap['qa']['quota_cooldown']['soft']['soft_cap'], 3)
        self.assertNotIn('soft', snap['qb']['quota_cooldown'] or {})

    def test_old_shared_allowance_hard_behavior_untouched(self):
        lease = self.acquire(pool='minimax', account='account')
        self.observe(lease, kind='rate_limit', rc=1)
        self.br.release(lease.lease_id, 'root')
        scope = circuit.scope_for(self.br, 'minimax', 'account')
        self.assertEqual(set(self.rows()), {scope})
        for pool in ('minimax', 'minimax-codex'):
            self.assertTrue(circuit.pool_blocked(self.br, pool))
            self.assertFalse(self.acquire(pool=pool, account='account', root='b%s' % pool).ok)
        self.assertTrue(self.acquire(pool='healthy', account='account').ok)
        self.assertFalse(circuit.pool_blocked(self.br, 'healthy'))





class ConcurrentSchemaMigration(unittest.TestCase):
    def test_two_original_initializers_upgrade_old_database_atomically(self):
        import sqlite3
        import threading
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "broker.sqlite")
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE leases (quota_outcome_sha256 TEXT, quota_scope TEXT);
                CREATE TABLE quota_cooldowns (scope TEXT PRIMARY KEY,
                    observed_at REAL NOT NULL, until_ts REAL NOT NULL,
                    failures INTEGER NOT NULL, kind TEXT NOT NULL,
                    source_run TEXT NOT NULL, reset_source TEXT NOT NULL);
            """)
            conn.close()
            stale_read_barrier = threading.Barrier(2)
            start = threading.Barrier(2)
            class Rows:
                def __init__(self, rows): self.rows = rows
                def __iter__(self):
                    stale_read_barrier.wait(timeout=5)
                    return iter(self.rows)
            class Connection(sqlite3.Connection):
                def execute(self, sql, *args):
                    result = super().execute(sql, *args)
                    if sql == "PRAGMA table_info(quota_cooldowns)" and not self.in_transaction:
                        # Force the original unsafe interleaving only when
                        # SQLite reports no transaction protecting the read.
                        return Rows(result.fetchall())
                    return result
            def initialize(_):
                conn = sqlite3.connect(path, timeout=10, factory=Connection)
                try:
                    start.wait(timeout=5)
                    circuit.init_schema(conn)
                    conn.commit()
                    return {r[1] for r in sqlite3.Connection.execute(conn, "PRAGMA table_info(quota_cooldowns)")}
                finally:
                    conn.close()
            with ThreadPoolExecutor(2) as pool:
                # Final column inspection bypasses only the test
                # synchronization, after both real migrations commit.
                results = list(pool.map(initialize, range(2)))
            for columns in results:
                self.assertTrue({"mode", "soft_cap"}.issubset(columns))



class LayeredAccountEligibility(QwenSoft):
    def test_fresh_usage_and_hard_hold_cannot_be_cleared_by_soft_expiry(self):
        from datetime import datetime, timezone
        from unittest import mock
        import bailian_keys
        lease = self.acquire(account="qa")
        self.observe(lease, fb=feedback())
        usage = self.root / "bailian_usage.json"
        def write_usage(observed, reset):
            stamp = lambda value: datetime.fromtimestamp(value, timezone.utc).isoformat()
            usage.write_text(json.dumps({"keys": {"qa": {"parked": True,
                "pct_7d": 98, "observed_at": stamp(observed),
                "resets_at": stamp(reset)}}}))
        write_usage(990, 3000)
        self.br.external_gates = True
        with mock.patch.object(bailian_keys, "HERE", str(self.root)), \
             mock.patch.object(bailian_keys, "cooldown_info", return_value=None), \
             mock.patch.object(bailian_keys, "current_per_key_cap", return_value=8):
            qa = self.br.provider("bailian")["accounts"][0]
            self.assertIsNone(self.br.account_cap("bailian", qa))
            self.assertNotIn("qa", [a["name"] for a in self.br.grantable_accounts("bailian")])
            write_usage(-100000, -1)  # UNKNOWN usage cannot erase the active soft policy.
            self.assertEqual(self.br.account_cap("bailian", qa), 3)
            self.clock[0] = 1200
            self.assertEqual(self.br.account_cap("bailian", qa), 8)
            self.br.external_gates = False  # temp-only fixture; never a live grant.
            held = self.acquire(account="qa", root="hard-fixture")
            self.observe(held, kind="rate_limit", reset=2000)
            self.br.external_gates = True
            self.assertIsNone(self.br.account_cap("bailian", qa))
            self.assertNotIn("qa", [a["name"] for a in self.br.grantable_accounts("bailian")])


class OfflineBoundaryRegression(unittest.TestCase):
    def test_real_provider_fallback_is_blocked_before_network(self):
        from unittest import mock
        import quota_remote
        from _offline_boundary import expect_blocked
        # Deliberately synthetic endpoint/key; actual reader control flow runs,
        # and both inherited auth-scheme attempts are blocked before transport.
        with mock.patch.object(quota_remote, "GLM_URL", "https://fixture.invalid/quota"):
            with expect_blocked("network", count=2):
                with self.assertRaises(RuntimeError):
                    quota_remote._live_glm("fixture-account", "fixture-only-not-a-key")

    def test_credential_open_is_blocked_before_reading_fixture_bytes(self):
        from _offline_boundary import expect_blocked, protect_fixture_credential, OfflineAccessError
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture-config.json"
            path.write_text('{"fixture":"not-a-real-secret"}')
            with protect_fixture_credential(path), expect_blocked("credential_open"):
                with self.assertRaises(OfflineAccessError):
                    path.read_bytes()


if __name__ == '__main__':
    unittest.main()
