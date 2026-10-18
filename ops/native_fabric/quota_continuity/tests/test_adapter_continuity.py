"""Real request/status/ledger/broker/continuation with an inert transport.

Historical incident-specific reconciliation modules are unavailable fixtures;
none of their paths is exercised or granted by these tests. Current quota and
request owners are imported unchanged from candidate/ and source/.
"""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'candidate'),str(ROOT/'source')]
import lease_broker
import pool_ledger
import provider_outcome as outcome
import quota_circuit
import fabric_continuation

legacy = {}
for name in ('a04_terminal_reconcile','native_completion_reconcile',
             'native_prestart_reconcile','native_preexec_reconcile',
             'native_host_review_controller_reconcile'):
    module=ModuleType(name)
    module.RUN=module.RUN_ID='unavailable-historical-fixture'
    module.KNOWN_RUNS=()
    legacy[name]=module
spec=importlib.util.spec_from_file_location('quota_fixture_adapter',ROOT/'candidate/fabric_task.py')
api=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,legacy):
    spec.loader.exec_module(api)


class Adapter(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'lanes').mkdir()
        accounts={'providers':{p:{'enabled':True,'concurrency_cap':8,
            'accounts':[{'name':'account','per_account_cap':8}]} for p in ('minimax','healthy')}}
        (self.root/'accounts.json').write_text(json.dumps(accounts))
        self.br=lease_broker.Broker(db_path=str(self.root/'broker.db'),
            lock_path=str(self.root/'broker.lock'),accounts_path=str(self.root/'accounts.json'),
            check_pid=False,external_gates=False,now_fn=lambda:1000,this_host='fixture')
        self.calls=[];self.fail_first=False;self.hold=False
        for target,attr,value in ((api,'HERE',self.root),(pool_ledger,'LEDGER_PATH',str(self.root/'ledger.jsonl'))):
            p=patch.object(target,attr,value);p.start();self.addCleanup(p.stop)
        p=patch('lease_broker.default_broker',return_value=self.br);p.start();self.addCleanup(p.stop)
        def route(*args,**kwargs):
            pool='healthy' if quota_circuit.pool_blocked(self.br,'minimax') else 'minimax'
            return f'POOL={pool} MODEL=fixture-model HOST=fixture MODE={pool}'
        for target,attr,value in ((api.pick,'format_pick',route),
                (api.pick,'launch_policy',lambda *a,**k:{'allowed':True}),
                (api.subprocess,'run',self.transport)):
            p=patch.object(target,attr,side_effect=value);p.start();self.addCleanup(p.stop)

    def path(self,run,suffix):
        return self.root/'state/remote_sub'/(run+suffix)

    def request(self,run='actual-request'):
        return api.request(run,'mechanical',cwd='~',packet=None,stdin_bytes=b'original task\n',
            root_id='root',parent_run_id='parent',task_complexity='C0_MECHANICAL',
            request_remaining_seconds=300)

    def transport(self,argv,env):
        run=argv[-1];pool=argv[3]
        self.calls.append((argv,env))
        rc=75 if self.fail_first and len(self.calls)==1 else 0
        lease=self.br.acquire('root',pool,model='fixture-model',host='fixture',
            task_class='mechanical',wait=0)
        self.assertTrue(lease.ok)
        output=b'' if rc else b'STATUS: COMPLETE\n'
        value=dict(schema=outcome.SCHEMA,run_id=run,lease_id=lease.lease_id,
            root_id='root',provider=pool,account='account',host='fixture',model='fixture-model',
            kind='rate_limit' if rc else 'success',command_rc=rc,observed_at=1000,
            initial_rejection=bool(rc),stdout_sha256=outcome.digest(output),reset_at=None)
        from test_quota_continuity import preflight_fixture
        proof=preflight_fixture(self.root/'state/remote_sub',run)
        if rc:value['pre_task_evidence']=proof
        process=dict(schema='mastermind.local_owned_process_receipt.v1',label=run,
            returncode=rc,stdout_sha256=value['stdout_sha256'],stdout_truncated=False,
            stderr_truncated=False,timed_out=False,
            cleanup=dict(census_proven=True,identity_verified=True,residual_count=0,status='not_needed'))
        self.path(run,'.provider.json').write_text(json.dumps(value))
        self.path(run,'.process.jsonl').write_text(json.dumps(process)+'\n')
        lock=self.br._lock()
        try:
            conn=self.br._conn()
            try:
                observed=quota_circuit.observe_locked(self.br,conn,lease.lease_id,'root',run,
                    self.path(run,'.provider.json'),self.path(run,'.process.jsonl'))
            finally:conn.close()
        finally:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
        self.path(run,'.provider-observed.json').write_text(json.dumps(observed))
        signal='quota' if rc else 'ok'
        self.assertTrue(pool_ledger.append(pool=pool,task_class='remote-'+pool,
            job_class='mechanical',rc=rc,signal=signal,run_id=run,model='fixture-model',
            root_id='root',parent_run_id='parent',strict=True))
        self.path(run,'.log').write_text('SUPPORT_VERSION_READY digest='+proof['support_digest']+f'\nDONE rc={rc} signal={signal}\n')
        (self.root/'lanes'/(run+'.remote.stdout')).write_bytes(output)
        if not self.hold:self.br.release(lease.lease_id,'root')
        return SimpleNamespace(returncode=rc)

    def test_prelaunch_refusal_is_retained_and_never_silently_replayed(self):
        with patch.object(api.pick,'format_pick',side_effect=ValueError('no capacity')):
            with self.assertRaises(ValueError):self.request()
        self.assertEqual(self.calls,[])
        self.assertEqual(self.path('actual-request','.request.packet').read_bytes(),b'original task\n')
        status=api.inspect_run('actual-request')
        self.assertEqual(status['state'],'REQUEST_REFUSED_BEFORE_LAUNCH')
        self.assertTrue(status['execution_absence_proven'])
        with self.assertRaises(api.FabricTaskError):self.request()
        self.assertEqual(self.calls,[])

    def test_real_transport_arguments_keep_frozen_task_identity_and_deadline(self):
        self.assertEqual(self.request(),0)
        self.assertEqual(len(self.calls),1)
        argv,env=self.calls[0]
        self.assertEqual(Path(argv[4]).read_bytes(),b'original task\n')
        self.assertEqual(env['POOL_ORCHESTRATOR_ID'],'root')
        self.assertEqual(env['POOL_PARENT_RUN_ID'],'parent')
        self.assertEqual(env['POOL_COMMISSION_REMAINING_SECONDS'],'300')
        self.assertEqual(api.inspect_run('actual-request')['root_id'],'root')

    def test_real_adapter_continues_to_independent_available_pool(self):
        self.fail_first=True
        rc=fabric_continuation.foreground(api,'origin','mechanical',cwd='~',packet=None,
            stdin_bytes=b'original task\n',root_id='root',parent_run_id='parent',task_complexity='C0_MECHANICAL')
        self.assertEqual(rc,0)
        self.assertEqual([args[3] for args,env in self.calls],['minimax','healthy'])
        view=fabric_continuation.resolve(api,'origin')
        self.assertEqual(api.inspect_run('origin')['rc'],75)
        self.assertEqual(view['effective_status']['rc'],0)
        self.assertEqual(view['effective_status']['root_id'],'root')
        self.assertFalse(view['effective_status']['accepted'])

    def test_unreleased_lease_and_wrong_root_never_authorize_successor(self):
        self.fail_first=True;self.hold=True
        self.request()
        for root in ('root','wrong-root'):
            with self.assertRaises(ValueError):
                fabric_continuation.eligible(api,self.root,'actual-request',root,'parent')
