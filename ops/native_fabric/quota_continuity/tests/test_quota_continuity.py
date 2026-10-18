"""Offline lifecycle tests; no provider requests, credentials or live broker."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'candidate'), str(ROOT / 'source')]
import lease_broker
import provider_outcome as outcome
import quota_circuit as circuit


def rejection(code='rate_limit', turns=1):
    return [
        {'type': 'system', 'subtype': 'init'},
        {'type': 'assistant', 'error': code,
         'message': {'content': [{'type': 'text', 'text': 'provider rejected this request'}]}},
        {'type': 'result', 'subtype': 'error_during_execution', 'is_error': True,
         'num_turns': turns, 'errors': ['not parsed as quota evidence']},
    ]


class Classification(unittest.TestCase):
    def parse(self, value, rc=1):
        return outcome.parse_claude(json.dumps(value).encode(), rc)[1]

    def test_initial_rejection_has_narrow_replay_evidence(self):
        row = self.parse(rejection())
        self.assertEqual(row['kind'], 'rate_limit')
        self.assertTrue(row['initial_rejection'])

    def test_worker_prose_never_quarantines_capacity(self):
        row = self.parse({'type': 'result', 'subtype': 'success', 'is_error': False,
                          'result': 'SESSION END PLATFORM_FAILURE token quota rate_limit'}, 0)
        self.assertEqual(row['kind'], 'success')
        self.assertFalse(row['initial_rejection'])

    def test_prior_tool_or_normal_work_blocks_replay(self):
        for prior in [
            {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'name': 'Bash'}]}},
            {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'changed files'}]}},
            {'type': 'system', 'subtype': 'hook_started'},
            {'type': 'unknown_future_event'},
        ]:
            with self.subTest(prior=prior):
                rows = rejection(); rows.insert(1, prior)
                row = self.parse(rows)
                self.assertEqual(row['kind'], 'rate_limit')
                self.assertFalse(row['initial_rejection'])

    def test_final_only_and_bad_capture_are_not_replay_proof(self):
        final = rejection()[-1]; final['api_error_status'] = 429
        self.assertEqual(self.parse(final)['kind'], 'rate_limit')
        self.assertFalse(self.parse(final)['initial_rejection'])
        for raw in [b'{"type":', b'quota exhausted', b'[{"type":"result"}]xxx']:
            display, row, _ = outcome.parse_claude(raw, 1)
            self.assertFalse(row['initial_rejection'])
            self.assertEqual(display, '')

    def test_budget_and_permission_are_not_capacity_failover(self):
        for subtype, expected in outcome.STOP_REASONS.items():
            rows = rejection(); rows[-1]['subtype'] = subtype
            self.assertEqual(self.parse(rows)['kind'], expected)
            self.assertFalse(self.parse(rows)['initial_rejection'])
        rows = rejection(); rows[-1]['permission_denials'] = [{'tool_name': 'Bash'}]
        self.assertEqual(self.parse(rows)['kind'], 'permission')
        self.assertFalse(self.parse(rows)['initial_rejection'])
        for err in ('authentication_failed', 'billing_error'):
            self.assertFalse(self.parse(rejection(err))['initial_rejection'])

    def test_thoughts_not_exposed_and_reset_is_structured(self):
        rows = rejection()
        rows.insert(1, {'type': 'rate_limit_event', 'rate_limit_info': {
            'status': 'rejected', 'resetsAt': 3000}})
        rows[-1]['result'] = 'visible'
        rows[1]['private_thought'] = 'secret-reasoning-fixture'
        display, row, _ = outcome.parse_claude(json.dumps(rows).encode(), 1)
        self.assertEqual(display, 'visible\n')
        self.assertNotIn('secret-reasoning-fixture', json.dumps(row))
        self.assertEqual(row['reset_at'], 3000)


class BrokerCircuit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = [1000.0]
        providers = {}
        for name in ('minimax', 'glm', 'healthy'):
            spec = {'enabled': True, 'concurrency_cap': 8,
                    'accounts': [{'name': 'account', 'per_account_cap': 8}]}
            if name in ('minimax', 'glm'):
                spec['quota_scope'] = 'same-shared-allowance'
            if name == 'minimax':
                spec['pool_aliases'] = ['minimax-codex']
            providers[name] = spec
        (self.root / 'accounts.json').write_text(json.dumps({'providers': providers}))
        self.br = self.broker()

    def broker(self):
        return lease_broker.Broker(db_path=str(self.root / 'broker.sqlite'),
            lock_path=str(self.root / 'broker.lock'), accounts_path=str(self.root / 'accounts.json'),
            now_fn=lambda: self.clock[0], check_pid=False, external_gates=False,
            grok_marker=str(self.root / 'no-marker'), this_host='fixture')

    def acquire(self, br=None, pool='minimax', root='root'):
        return (br or self.br).acquire(root, pool, model='fixture-model', host='fixture',
                                       task_class='fixture', ttl=1000, wait=0)

    def observe(self, lease, kind='rate_limit', run=None, rc=1, reset=None, mutate=None):
        run = run or 'run-' + lease.lease_id
        value = dict(schema=outcome.SCHEMA, run_id=run, lease_id=lease.lease_id,
            root_id=lease.orchestrator_id, provider=lease.pool, account='account',
            host='fixture', model='fixture-model', kind=kind, command_rc=rc,
            observed_at=self.clock[0], reset_at=reset,
            reset_source='provider_event' if reset else None,
            initial_rejection=True, stdout_sha256=hashlib.sha256(b'').hexdigest())
        process = dict(schema='mastermind.local_owned_process_receipt.v1', label=run,
            returncode=rc, stdout_sha256=value['stdout_sha256'], stdout_truncated=False,
            stderr_truncated=False, timed_out=False,
            cleanup=dict(census_proven=True, identity_verified=True, residual_count=0, status='not_needed'))
        if mutate:
            mutate(value, process)
        op, pp = self.root / (run + '.outcome'), self.root / (run + '.process')
        op.write_text(json.dumps(value)); pp.write_text(json.dumps(process))
        lock = self.br._lock()
        try:
            conn = self.br._conn()
            try:
                return circuit.observe_locked(self.br, conn, lease.lease_id,
                    lease.orchestrator_id, run, op, pp)
            finally:
                conn.close()
        finally:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_UN); lock.close()

    def test_shared_allowance_blocks_aliases_but_not_healthy_pool(self):
        lease = self.acquire(); self.assertTrue(lease.ok)
        self.observe(lease)
        self.br.release(lease.lease_id, 'root')
        for pool in ('minimax', 'minimax-codex', 'glm'):
            self.assertTrue(circuit.pool_blocked(self.br, pool))
            self.assertFalse(self.acquire(pool=pool).ok)
        self.assertTrue(self.acquire(pool='healthy').ok)

    def test_cooldown_survives_new_broker_process(self):
        lease = self.acquire(); self.observe(lease)
        self.br.release(lease.lease_id, 'root')
        self.assertFalse(self.acquire(br=self.broker()).ok)

    def test_only_one_half_open_probe_across_shared_products(self):
        lease = self.acquire(); self.observe(lease)
        self.br.release(lease.lease_id, 'root'); self.clock[0] += 61
        brokers = [self.broker() for _ in range(12)]
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = [executor.submit(self.acquire, br, 'glm' if i % 2 else 'minimax', 'root')
                       for i, br in enumerate(brokers)]
            grants = [f.result() for f in futures]
        self.assertEqual(sum(g.ok for g in grants), 1)
        winner = next(g for g in grants if g.ok)
        self.observe(winner, kind='success', rc=0)
        self.br.release(winner.lease_id, 'root')
        self.assertIsNone(circuit.cooldown(self.br, 'minimax', 'account'))
        self.assertTrue(self.acquire().ok)

    def test_old_success_does_not_reopen_new_quota_failure(self):
        old = self.acquire(); bad = self.acquire()
        self.clock[0] += 1
        self.observe(bad)
        self.observe(old, kind='success', rc=0)
        self.assertTrue(circuit.pool_blocked(self.br, 'minimax'))

    def test_retry_after_and_duplicate_observation(self):
        lease = self.acquire(); self.observe(lease, reset=5000)
        before = circuit.cooldown(self.br, 'minimax', 'account')
        result = self.observe(lease, reset=5000)
        self.assertTrue(result['duplicate'])
        self.assertEqual(circuit.cooldown(self.br, 'minimax', 'account'), before)
        self.assertEqual(before['until_ts'], 5000)

    def test_uncertain_cleanup_or_wrong_identity_never_changes_admission(self):
        mutators = [lambda v,p: p['cleanup'].update(residual_count=1),
                    lambda v,p: v.update(account='wrong'),
                    lambda v,p: p.update(stdout_sha256='0'*64),
                    lambda v,p: p.update(stdout_truncated=True)]
        for i, mutate in enumerate(mutators):
            lease = self.acquire()
            with self.assertRaises(ValueError):
                self.observe(lease, run='bad-' + str(i), mutate=mutate)
            self.br.release(lease.lease_id, 'root')
            self.assertFalse(circuit.pool_blocked(self.br, 'minimax'))


if __name__ == '__main__':
    unittest.main()
