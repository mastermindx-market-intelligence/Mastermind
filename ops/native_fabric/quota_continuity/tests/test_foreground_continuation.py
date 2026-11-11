"""Fault injection into the native foreground owner, with an isolated broker."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_quota_continuity as _fixture
outcome, circuit = _fixture.outcome, _fixture.circuit
import fabric_continuation as continuation


class Foreground(unittest.TestCase):
    def setUp(self):
        self.fixture = _fixture.BrokerCircuit(methodName='test_shared_allowance_blocks_aliases_but_not_healthy_pool')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        (self.root / 'state/remote_sub').mkdir(parents=True)
        (self.root / 'lanes').mkdir()
        self.statuses = {}; self.calls = []; self.leases = []
        self.fail_mode = 'initial'; self.all_fail = False
        self.api = SimpleNamespace(HERE=self.root, MAX_RESULT_BYTES=8388608,
            inspect_run=self.inspect, request=self.request,
            _paths=lambda r:(self.path(r,'.log'),self.root/'lanes'/(r+'.remote.stdout')))
        self.patch = patch('lease_broker.default_broker', return_value=self.fixture.br)
        self.patch.start(); self.addCleanup(self.patch.stop)

    def path(self,r,s):
        return self.root/'state/remote_sub'/(r+s)

    def inspect(self,r):
        return self.statuses.get(r, dict(schema='mastermind.fabric_task_status.v1',run_id=r,
            state='NOT_FOUND',rc=None,signal=None,root_id=None,parent_run_id=None,result_available=False))

    def request(self,r,tc,**kwargs):
        self.calls.append((r,tc,kwargs))
        source=kwargs['packet'].read_bytes() if kwargs.get('packet') else kwargs['stdin_bytes']
        self.path(r,'.request.packet').write_bytes(source)
        self.path(r,'.request.json').write_text(json.dumps(dict(
            schema='mastermind.fabric_request_artifact.v1',run_id=r,root_id='root',
            parent_run_id='parent',packet=r+'.request.packet',packet_sha256=outcome.digest(source))))
        pool='minimax' if len(self.calls)==1 or self.all_fail else 'healthy'
        if self.all_fail and len(self.calls)>1:
            # A different eligible account in a test-only pool; production uses
            # the incumbent picker. This fixture exercises the attempt bound.
            pool='healthy'
            conn=self.fixture.br._conn();conn.execute('DELETE FROM quota_cooldowns');conn.commit();conn.close()
        lease=self.fixture.acquire(pool=pool)
        if not lease.ok: raise AssertionError('fixture admission: '+lease.reason)
        self.leases.append(lease)
        rc=75 if len(self.calls)==1 or self.all_fail else 0
        run='run-'+lease.lease_id
        proof=_fixture.preflight_fixture(self.root/'state/remote_sub',r)
        self.fixture.observe(lease,kind='rate_limit' if rc else 'success',rc=rc,run=r,
            mutate=lambda value,process:value.update(pre_task_evidence=proof) if self.fail_mode!='cli-initial' else None)
        for source_suffix,target_suffix in [('.outcome','.provider.json'),('.process','.process.jsonl')]:
            self.path(r,target_suffix).write_bytes((self.root/(r+source_suffix)).read_bytes())
        self.path(r,'.provider-observed.json').write_text(json.dumps({'recorded':True,'kind':'rate_limit' if rc else 'success'}))
        value=json.loads(self.path(r,'.provider.json').read_text())
        if self.fail_mode=='worked': value['initial_rejection']=False
        if self.fail_mode=='wrong-root': value['root_id']='different'
        if self.fail_mode!='initial':
            self.path(r,'.provider.json').write_text(json.dumps(value))
        if self.fail_mode!='held': self.fixture.br.release(lease.lease_id,'root')
        self.statuses[r]=dict(schema='mastermind.fabric_task_status.v1',run_id=r,
            state='EFFECT_UNKNOWN' if self.fail_mode=='uncertain' else 'TERMINAL',
            rc=rc,signal='quota' if rc else 'ok',root_id='root',parent_run_id='parent',
            result_available=True,result_bytes=7,accepted=False)
        self.path(r,'.log').write_text('SUPPORT_VERSION_READY digest='+proof['support_digest']+'\nfixture strict terminal publication\n')
        if self.fail_mode=='manifest':self.path(r,'.support.json').write_text('{}')
        if self.fail_mode=='source-ready':self.path(r,'.log').write_text('SUPPORT_VERSION_READY digest='+'0'*64+'\n')
        return rc

    def run_owner(self,origin='origin',**extra):
        kwargs=dict(cwd='~',packet=None,stdin_bytes=b'commission bytes\n',root_id='root',
                    parent_run_id='parent',task_complexity='C0_MECHANICAL')
        kwargs.update(extra)
        return continuation.foreground(self.api,origin,'mechanical',**kwargs)

    def test_quota_then_success_keeps_exact_attempt_and_effective_identity(self):
        self.assertEqual(self.run_owner(),0)
        value=continuation.resolve(self.api,'origin')
        self.assertEqual(self.inspect('origin')['rc'],75)
        self.assertEqual(value['effective_status']['rc'],0)
        self.assertNotEqual(value['effective_run_id'],'origin')
        self.assertEqual(len(value['prior_attempts']),1)
        self.assertEqual(value['controller_return'],'RECORDED')
        for r,tc,kw in self.calls:
            self.assertEqual(kw['root_id'],'root'); self.assertEqual(kw['parent_run_id'],'parent')
            self.assertLessEqual(kw['request_remaining_seconds'],7200)
        self.assertEqual(self.path(value['effective_run_id'],'.request.packet').read_bytes(),b'commission bytes\n')

    def test_uncertain_effect_prior_work_held_lease_and_tampering_do_not_retry(self):
        for mode in ('worked','held','wrong-root','uncertain','cli-initial','manifest','source-ready'):
            with self.subTest(mode=mode):
                conn=self.fixture.br._conn()
                conn.execute('DELETE FROM quota_cooldowns'); conn.execute('DELETE FROM leases'); conn.execute('DELETE FROM waiters')
                conn.commit(); conn.close()
                self.calls=[]
                self.fail_mode=mode
                count=len(self.calls)
                self.run_owner('case-'+mode)
                self.assertEqual(len(self.calls),count+1)
                self.assertFalse(self.path('case-'+mode,'.successor.json').exists())

    def test_attempt_bound_never_creates_a_fourth_worker(self):
        self.all_fail=True
        self.assertEqual(self.run_owner(),75)
        self.assertEqual(len(self.calls),3)
        self.assertEqual(len(continuation.resolve(self.api,'origin')['prior_attempts']),2)

    def test_competing_controllers_cannot_replay_origin(self):
        barrier=threading.Barrier(2)
        def start():
            barrier.wait()
            try:return self.run_owner()
            except (ValueError,FileExistsError):return 'refused'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:start(),range(2)))
        self.assertIn('refused',results)
        self.assertEqual(len(self.calls),2)  # one rejected attempt + one successful successor

    def test_crash_after_successor_reservation_does_not_invent_start_or_retry(self):
        original=self.api.request
        def crash(r,tc,**kw):
            if self.calls:raise RuntimeError('fixture controller crash before successor start')
            return original(r,tc,**kw)
        self.api.request=crash
        with self.assertRaises(RuntimeError):self.run_owner()
        value=continuation.resolve(self.api,'origin')
        self.assertEqual(value['controller_return'],'UNCONFIRMED')
        self.assertEqual(value['controller_reason'],'controller_exception')
        # Simulate an abrupt exit before the finally receipt reached disk.
        self.path('origin','.continuation-finished.json').unlink()
        value=continuation.resolve(self.api,'origin')
        self.assertEqual(value['effective_status']['state'],'NOT_FOUND')
        self.assertEqual(value['controller_return'],'UNCONFIRMED')
        self.assertEqual(len(self.calls),1)
        continuation.resolve(self.api,'origin')
        self.assertEqual(len(self.calls),1)

    def test_successor_packet_readback_is_bound_to_original(self):
        self.run_owner()
        value=continuation.resolve(self.api,'origin')
        self.path(value['effective_run_id'],'.request.packet').write_bytes(b'different task')
        with self.assertRaisesRegex(ValueError,'successor_task_changed'):
            continuation.resolve(self.api,'origin')

    def test_identity_bearing_modes_require_their_own_contract(self):
        for kw in ({'native_return':True},{'artifact_names':['out.txt']},{'pool':'glm'},
                   {'requested_model':'specific-model'},{'new_macro_worktree':'a'*40}):
            with self.subTest(kw=kw):
                with self.assertRaises(ValueError):self.run_owner(**kw)
        self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
