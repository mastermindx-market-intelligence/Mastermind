import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest
from unittest.mock import patch

from fabric_operator_owner import OperatorOwner, DelegationRefused, clean_child_environment
from fabric_operator_client import load_operator_environment
from fabric_client_projection import project_fabric_client, FabricClientProjectionError


class OwnerChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.here = Path(self.temp.name)
        (self.here / 'broker').mkdir()
        (self.here / 'broker/leases.lock').touch(mode=0o600)
        (self.here / 'state/remote_sub').mkdir(parents=True)
        self.now = 1000.
        self.owner = OperatorOwner(here=self.here, clock=lambda: self.now)
        self.lease = dict(id='lease-operator', orchestrator_id='root', pool='glm-frontier', account='account-1',
                          task_class='remote-glm', model='glm-5.3', host='ubuntu1', pid=123,
                          granted_at=990., ttl=180, last_heartbeat=999., state='held', renewable=1)
        with sqlite3.connect(self.owner.db) as con:
            columns=', '.join(k+' '+('REAL' if type(v) is float else 'INTEGER' if type(v) is int else 'TEXT') for k,v in self.lease.items())
            con.execute('CREATE TABLE leases ('+columns+')')
            con.execute('INSERT INTO leases VALUES ('+','.join('?' for _ in self.lease)+')',tuple(self.lease.values()))
        self.launch = dict(root='root', run_id='operator', lease_id='lease-operator', pool='glm-frontier', model='glm-5.3',
                           account='account-1', host='ubuntu1', support_sha256='a'*64,
                           packet_sha256=hashlib.sha256(b'packet').hexdigest(), task_class='domain_orchestration')
        self.owner.authorize_root('root', 3, 2200.)
        self.cap = self.owner.issue(self.launch, 2)
        self.request = dict(schema='mastermind.fabric_operator_child_request.v1', root='root', parent='operator',
                            run_id='child-1', task_class='mechanical', task_complexity='C0_MECHANICAL', packet='Bounded useful task')

    def tearDown(self): self.temp.cleanup()

    def set_headroom(self, seconds, grant_limited=False):
        with sqlite3.connect(self.owner.db) as con:
            if grant_limited:
                grant=json.loads(con.execute("SELECT grant_json FROM operator_grants").fetchone()[0])
                grant['expires_at']=self.now+seconds
                con.execute("UPDATE operator_grants SET grant_json=?",(json.dumps(grant),))
            else:
                con.execute("UPDATE operator_root_grants SET expires=?",(self.now+seconds,))

    def test_start_window_refuses_without_consuming_authorization(self):
        for grant_limited in (False, True):
            with self.subTest(grant_limited=grant_limited):
                self.set_headroom(615,grant_limited)
                with self.assertRaisesRegex(DelegationRefused,'^operator_child_start_window_expired$'):
                    self.owner.reserve(self.cap['token'],self.request)
                with sqlite3.connect(self.owner.db) as con:
                    self.assertEqual(con.execute('SELECT count(*) FROM operator_child_authorizations').fetchone()[0],0)
                self.assertEqual(self.owner.describe(self.cap['token'])['child_budget_remaining'],2)
                self.set_headroom(1200,grant_limited)

    def test_exact_start_window_and_later_broker_race(self):
        from fabric_operator_owner import validate_child_admission
        self.set_headroom(660)
        self.owner.reserve(self.cap['token'],self.request)
        with self.owner.transaction() as con:
            validate_child_admission(con,'child-1','root',now=self.now)
        with self.owner.transaction() as con:
            with self.assertRaisesRegex(DelegationRefused,'^operator_child_start_window_expired$'):
                validate_child_admission(con,'child-1','root',now=self.now+1)
        self.assertEqual(self.owner.describe(self.cap['token'])['child_budget_remaining'],1)

    def test_refusal_payload_exposes_only_fixed_public_reason(self):
        from fabric_operator_owner import refusal_payload
        known=refusal_payload(DelegationRefused('operator_child_start_window_expired'))
        self.assertEqual(known,dict(state='OPERATOR_REQUEST_REFUSED',retry_authorized=False,reason='operator_child_start_window_expired'))
        for exc in (DelegationRefused('private-token-path'), OSError('operator_child_start_window_expired')):
            self.assertEqual(refusal_payload(exc),dict(state='OPERATOR_REQUEST_REFUSED',retry_authorized=False))

    def test_declared_pool_alias_binds_actual_broker_pool(self):
        with sqlite3.connect(self.owner.db) as con:
            con.execute("UPDATE leases SET pool='glm'")
        with patch('lease_broker._load_yaml',return_value={'providers':{'glm':{'pool_aliases':['glm-frontier']}}}):
            cap=self.owner.issue(dict(self.launch,run_id='alias-operator'),1)
        self.assertEqual(cap['pool'],'glm')
        self.assertEqual(self.owner.describe(cap['token'])['operator_run'],'alias-operator')

    def test_undeclared_pool_alias_refuses(self):
        with sqlite3.connect(self.owner.db) as con:con.execute("UPDATE leases SET pool='glm'")
        with patch('lease_broker._load_yaml',return_value={'providers':{'glm':{'pool_aliases':[]}}}):
            with self.assertRaises(DelegationRefused):self.owner.issue(dict(self.launch,run_id='alias-operator'),1)

    def test_private_token_is_not_stored_in_broker(self):
        with sqlite3.connect(self.owner.db) as con:
            row=con.execute('SELECT * FROM operator_grants').fetchone()
        self.assertNotIn(self.cap['token'], str(row))
        self.assertIn(hashlib.sha256(self.cap['token'].encode()).hexdigest(),row)

    def test_bad_token_does_not_reserve(self):
        with self.assertRaises(DelegationRefused):self.owner.reserve('0'*64,self.request)
        self.assertEqual(self.owner.describe(self.cap['token'])['child_budget_remaining'],2)

    def test_only_local_issued_budget_can_be_used(self):
        self.owner.reserve(self.cap['token'],self.request)
        self.owner.reserve(self.cap['token'],dict(self.request,run_id='child-2'))
        with self.assertRaises(DelegationRefused):self.owner.reserve(self.cap['token'],dict(self.request,run_id='child-3'))
        self.assertEqual(self.owner.describe(self.cap['token'])['child_budget_remaining'],0)

    def test_duplicate_does_not_dispatch(self):
        calls=[]
        fake=lambda *a,**k:(calls.append((a,k)) or types.SimpleNamespace(pid=444))
        self.owner.dispatch(self.cap['token'],self.request,popen=fake)
        with self.assertRaises(DelegationRefused):self.owner.dispatch(self.cap['token'],self.request,popen=fake)
        self.assertEqual(len(calls),1)

    def test_concurrent_same_id_only_one_authorization(self):
        def run(_):
            try:self.owner.reserve(self.cap['token'],copy.deepcopy(self.request));return True
            except DelegationRefused:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            results=list(ex.map(run,range(6)))
        self.assertEqual(sum(results),1)

    def test_root_budget_shared_between_operators(self):
        cap2=self.owner.issue(dict(self.launch,run_id='operator-2'),2)
        self.owner.reserve(self.cap['token'],self.request)
        self.owner.reserve(self.cap['token'],dict(self.request,run_id='child-2'))
        self.owner.reserve(cap2['token'],dict(self.request,parent='operator-2',run_id='child-3'))
        with self.assertRaises(DelegationRefused):self.owner.reserve(cap2['token'],dict(self.request,parent='operator-2',run_id='child-4'))

    def test_expired_or_released_operator_cannot_issue_child(self):
        with sqlite3.connect(self.owner.db) as con:con.execute("UPDATE leases SET state='released'")
        with self.assertRaises(DelegationRefused):self.owner.reserve(self.cap['token'],self.request)

    def test_changed_launch_rejected(self):
        with self.assertRaises(DelegationRefused):self.owner.issue(dict(self.launch,run_id='other',pool='grok'),2)

    def test_wrong_parent_and_override_refused(self):
        for request in [dict(self.request,parent='other'),dict(self.request,host='ubuntu2'),dict(self.request,task_class='domain_orchestration')]:
            with self.assertRaises(DelegationRefused):self.owner.reserve(self.cap['token'],request)

    def test_controller_environment_does_not_reuse_parent_lease(self):
        env=clean_child_environment({'PATH':'/bin','POOL_LEASE_ID':'outer','LANE_LEASED':'1','FABRIC_OPERATOR_CAPABILITY':'secret','POOL_OPERATOR_CHILD_BUDGET':'2','GROK_AUTH_TOKEN':'secret'})
        self.assertEqual(env,{'PATH':'/bin'})

    def test_unknown_spawn_effect_is_not_refunded(self):
        def broken(*a,**k):raise OSError('broken')
        result=self.owner.dispatch(self.cap['token'],self.request,popen=broken)
        self.assertFalse(result['retry_authorized'])
        self.assertEqual(result['state'],'DISPATCH_UNVERIFIED')
        self.assertEqual(self.owner.describe(self.cap['token'])['child_budget_remaining'],1)

    def test_existing_run_refused(self):
        (self.here/'state/remote_sub/child-1.log').write_text('original')
        with self.assertRaises(DelegationRefused):self.owner.reserve(self.cap['token'],self.request)

    def test_cross_operator_result_refused(self):
        self.owner.reserve(self.cap['token'],self.request)
        other=self.owner.issue(dict(self.launch,run_id='other'),2)
        with self.assertRaises(DelegationRefused):self.owner.child_binding(other['token'],'child-1')

    def test_released_lease_preserves_child_record(self):
        self.owner.reserve(self.cap['token'],self.request)
        self.now=2400
        with self.assertRaises(DelegationRefused):self.owner.child_binding(self.cap['token'],'child-1')
        with sqlite3.connect(self.owner.db) as con:self.assertEqual(con.execute('SELECT count(*) FROM operator_child_authorizations').fetchone()[0],1)

    def test_frontier_review_is_not_a_cheap_leaf_class(self):
        with self.assertRaises(DelegationRefused):self.owner.reserve(self.cap['token'],dict(self.request,task_class='review'))

    def test_projection_uses_placeholder_not_bearer(self):
        for provider in ('claude','grok'):
            p=project_fabric_client(provider,'domain_orchestration',read_url='https://test.ts.net/studio-fabric',design_url='https://test.ts.net/studio-design',operator_delegation=True)
            self.assertIn('${FABRIC_OPERATOR_CAPABILITY}',p.config_text)
            self.assertNotIn(self.cap['token'],p.config_text)
        with self.assertRaises(FabricClientProjectionError):project_fabric_client('claude','mechanical',read_url='https://test.ts.net/studio-fabric',design_url='https://test.ts.net/studio-design',operator_delegation=True)

    def test_capsule_bound_to_run_packet_and_private_file(self):
        directory=self.here/'lanes/tmp';directory.mkdir(parents=True)
        p=directory/'operator.operator-cap.json';p.write_text(json.dumps(self.cap));p.chmod(0o600)
        env=dict(FABRIC_OPERATOR_CAPSULE='lanes/tmp/operator.operator-cap.json',POOL_TASK_CLASS='domain_orchestration',
                 POOL_ORCHESTRATOR_ID='root',POOL_LEASE_ID='lease-operator',POOL_ACCOUNT='account-1',LANE_REMOTE_HOST='ubuntu1',SUPPORT_DIGEST='a'*64)
        result=load_operator_environment(env,'operator','glm','glm-5.3',b'packet',home=self.here,now=1000)
        self.assertEqual(result['FABRIC_OPERATOR_CAPABILITY'],self.cap['token'])
        with self.assertRaises(ValueError):load_operator_environment(env,'operator','glm','glm-5.3',b'changed',home=self.here,now=1000)
        bad=dict(self.cap,expires_at=float('inf'));p.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):load_operator_environment(env,'operator','glm','glm-5.3',b'packet',home=self.here,now=1000)
        p.write_text(json.dumps(self.cap))
        p.chmod(0o644)
        with self.assertRaises(ValueError):load_operator_environment(env,'operator','glm','glm-5.3',b'packet',home=self.here,now=1000)

    def test_plain_leaf_cannot_inherit_bearer(self):
        self.assertNotIn('FABRIC_OPERATOR_CAPABILITY',load_operator_environment({'FABRIC_OPERATOR_CAPABILITY':'evil'},'child','glm','glm-5.3-flash',b'packet'))


if __name__=='__main__':unittest.main()
