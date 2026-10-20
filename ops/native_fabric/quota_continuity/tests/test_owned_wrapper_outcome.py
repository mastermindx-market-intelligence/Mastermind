"""Actual remote executor, owned process and wrappers against a loopback provider.

Credentials, SDK/MCP projection, the already-leased slot boundary and physical
host load are inert fixtures. The source under review owns process capture,
cleanup, typed provider receipts and broker observation. No real provider or
account is used, and no installed admission configuration is changed.
"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

import test_capacity_preflight as fixtures

ROOT = fixtures.ROOT
sys.path[:0] = [str(ROOT / 'candidate'), str(ROOT / 'source')]
import lease_broker
import provider_outcome
import quota_circuit


class OwnedWrapperOutcome(unittest.TestCase):
    script = fixtures.Preflight.script
    env = fixtures.Preflight.env

    def setUp(self):
        fixtures.Preflight.setUp(self)
        for name in ('remote_sub_exec.py', 'pick.py', 'commission_deadline.py'):
            shutil.copyfile(ROOT / 'candidate' / name, self.ext / name)
        for name in ('lane_runtime.py', 'native_remote.py',
                     'fabric_client_projection.py', 'yes'):
            shutil.copyfile(ROOT / 'source' / name, self.ext / name)
        (self.ext / 'yes').chmod(0o700)
        (self.ext / 'lanes').mkdir()
        # The receipt contract is independent of ambient CI/host load. Supply
        # the LaneLease's existing explicit sensor seam inside this disposable
        # process; actual admission locking, process execution and cleanup stay
        # with the production owners. No worker can access a real credential.
        (self.ext / 'run_fixture.py').write_text(
            'import sys\nimport remote_sub_exec as remote\n'
            'original_acquire=remote.LaneLease.acquire\n'
            'def acquire(cls,*args,**kwargs):\n'
            ' kwargs["load1"]=0.0\n'
            ' return original_acquire(*args,**kwargs)\n'
            'remote.LaneLease.acquire=classmethod(acquire)\n'
            'raise SystemExit(remote.main(sys.argv))\n')
        policy = self.root / 'orch' / 'fabric'
        policy.mkdir(parents=True)
        (policy / 'pools.yaml').write_text(json.dumps({
            'pools': {'glm': {'models': {'executor': 'glm-5.3-flash'}}}}))
        (self.ext / 'slot.py').write_text(
            'import os,sys\nCAPS={"glm-frontier":1}\n'
            'if __name__=="__main__":\n'
            ' print("FIXTURE_ADMISSION_DIAGNOSTIC",file=sys.stderr)\n'
            ' a=sys.argv[sys.argv.index("--")+1:]\n'
            ' os.execvp(a[0],a)\n')
        (self.ext / 'glm_keys.py').write_text(
            'import os,sys\n'
            'def accounts():return []\n'
            'def selected_account_key(*args):return "inert-fixture-key"\n'
            'if __name__=="__main__":\n'
            ' if sys.argv[1]=="anthropic_base_url":print(os.environ["FIXTURE_ENDPOINT"])\n'
            ' elif sys.argv[1]=="model":print("glm-5.3")\n'
            ' elif sys.argv[1]!="enabled":sys.exit(2)\n')
        accounts = {'providers': {
            p: {'enabled': True, 'concurrency_cap': 2,
                'accounts': [{'name': 'account', 'per_account_cap': 2}]}
            for p in ('minimax', 'glm')}}
        account_path = self.root / 'fixture-accounts.json'
        account_path.write_text(json.dumps(accounts))
        self.broker = lease_broker.Broker(
            db_path=str(self.root / 'fixture-broker.db'),
            lock_path=str(self.root / 'fixture-broker.lock'),
            accounts_path=str(account_path), check_pid=False,
            external_gates=False, this_host='fixture')

    def execute(self, provider):
        model = 'MiniMax-M3' if provider == 'minimax' else 'glm-5.3-flash'
        lease = self.broker.acquire('root', provider, model=model, host='fixture',
                                    task_class='mechanical', wait=0)
        self.assertTrue(lease.ok, lease)
        self.addCleanup(self.broker.release, lease.lease_id, 'root')
        env = self.env()
        run = env['REMOTE_SUB_RUN_ID']
        env.update(POOL_LEASE_ID=lease.lease_id, REMOTE_SUB_CHILD_TIMEOUT='20',
                   LANE_MAX_ACTIVE='1', LANE_MAX_LOAD_RATIO='1.5',
                   POOL_TASK_COMPLEXITY='C1_ROUTINE_BOUNDED')
        # These opt-ins are absent from this ordinary fixture even if the test
        # runner itself was commissioned through a richer Fabric capability.
        for key in ('FABRIC_OPERATOR_CAPSULE', 'FABRIC_OPERATOR_CAPABILITY',
                    'FABRIC_NEW_MACRO_COMMIT', 'FABRIC_CPU_SCOPE_QUOTA_PCT'):
            env.pop(key, None)
        marker = Path(env['FIXTURE_CLI_STARTED'])
        marker.unlink(missing_ok=True)
        packet = self.root / (run + '.packet')
        packet.write_text('PRIVATE TASK MUST NEVER ENTER PROBE\n')
        result = subprocess.run(
            [sys.executable, str(self.ext / 'run_fixture.py'), run,
             provider, str(packet), str(self.root), model],
            env=env, capture_output=True, timeout=30)
        receipt_path = self.ext / 'lanes' / (run + '.process.jsonl')
        outcome_path = self.ext / 'lanes' / (run + '.provider.json')
        self.assertTrue(receipt_path.is_file(), result.stderr.decode())
        self.assertTrue(outcome_path.is_file(), result.stderr.decode())
        receipt = json.loads(receipt_path.read_text().splitlines()[-1])
        outcome = json.loads(outcome_path.read_text())
        provider_outcome.validate_receipt(outcome, receipt, run)
        self.assertEqual(receipt['returncode'], result.returncode)
        self.assertEqual(receipt['stdout_bytes'], len(result.stdout))
        self.assertEqual(receipt['stdout_sha256'], provider_outcome.digest(result.stdout))
        self.assertEqual(outcome['stdout_sha256'], receipt['stdout_sha256'])
        self.assertTrue(receipt['cleanup']['census_proven'])
        self.assertEqual(receipt['cleanup']['residual_count'], 0)
        self.assertNotIn(b'inert-fixture-key', result.stdout + result.stderr
                         + receipt_path.read_bytes() + outcome_path.read_bytes())
        lock = self.broker._lock()
        try:
            conn = self.broker._conn()
            try:
                observed = quota_circuit.observe_locked(
                    self.broker, conn, lease.lease_id, 'root', run,
                    outcome_path, receipt_path)
            finally:
                conn.close()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
        self.assertTrue(observed['recorded'])
        self.assertTrue(self.broker.release(lease.lease_id, 'root'))
        return result, outcome, marker

    def test_real_capacity_receipts_bind_despite_wrapper_stderr(self):
        for provider in ('minimax', 'glm'):
            with self.subTest(provider=provider):
                result, outcome, marker = self.execute(provider)
                self.assertEqual(result.returncode, 75, result.stderr.decode())
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'FIXTURE_ADMISSION_DIAGNOSTIC', result.stderr)
                self.assertFalse(marker.exists())
                self.assertFalse(outcome['pre_task_evidence']['task_cli_started'])
                self.assertTrue(quota_circuit.pool_blocked(self.broker, provider))
        self.assertEqual(len(self.requests), 2)
        for _, body in self.requests:
            self.assertNotIn('PRIVATE TASK', json.dumps(body))
            self.assertEqual(body['max_tokens'], 1)

    def test_real_success_receipts_bind_after_task_cli_execution(self):
        self.reply = (200, {'type': 'message'}, {})
        for provider in ('minimax', 'glm'):
            with self.subTest(provider=provider):
                result, outcome, marker = self.execute(provider)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                self.assertEqual(result.stdout, b'STATUS: COMPLETE\n')
                self.assertTrue(marker.exists())
                self.assertEqual(outcome['kind'], 'success')
                self.assertNotIn('pre_task_evidence', outcome)
                self.assertFalse(quota_circuit.pool_blocked(self.broker, provider))

    def test_real_policy_denial_is_observed_without_capacity_cooldown(self):
        self.reply = (403, {'error': {'type': 'permission_error'}}, {})
        for provider in ('minimax', 'glm'):
            with self.subTest(provider=provider):
                result, outcome, marker = self.execute(provider)
                self.assertEqual(result.returncode, 78, result.stderr.decode())
                self.assertEqual(outcome['kind'], 'permission')
                self.assertFalse(marker.exists())
                self.assertFalse(outcome['initial_rejection'])
                self.assertFalse(quota_circuit.pool_blocked(self.broker, provider))


if __name__ == '__main__':
    unittest.main()
