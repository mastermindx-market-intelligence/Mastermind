import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lease_broker import Broker
from fabric_operator_owner import OperatorOwner, DelegationRefused, validate_child_admission

class AdmissionBoundary(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.base=Path(self.t.name);self.now=1000.
        (self.base/'broker').mkdir();(self.base/'state/remote_sub').mkdir(parents=True)
        accounts=self.base/'accounts.yaml';accounts.write_text('''schema: mastermind.provider_accounts.v1
providers:
  glm-frontier:
    enabled: true
    accounts:
      - name: test
        per_account_cap: 3
  bailian:
    enabled: true
    accounts:
      - name: test
        per_account_cap: 3
''')
        self.b=Broker(db_path=str(self.base/'broker/leases.sqlite'),lock_path=str(self.base/'broker/leases.lock'),accounts_path=str(accounts),now_fn=lambda:self.now,check_pid=False,external_gates=False,this_host='testhost',status_json=str(self.base/'status.json'))
        self.o=OperatorOwner(here=self.base,clock=lambda:self.now)
        self.lease=self.b.acquire('root','glm-frontier',model='glm-5.3',task_class='remote-glm',host='ubuntu1',ttl=2000)
        assert self.lease.ok,self.lease
        self.o.authorize_root('root',2,2200.)
        launch=dict(root='root',run_id='operator',lease_id=self.lease.lease_id,pool='glm-frontier',model='glm-5.3',account='test',host='ubuntu1',support_sha256='a'*64,packet_sha256='b'*64,task_class='domain_orchestration')
        self.cap=self.o.issue(launch,2)
        self.req=dict(schema='mastermind.fabric_operator_child_request.v1',root='root',parent='operator',run_id='leaf',task_class='audit',task_complexity='C1_ROUTINE_BOUNDED',packet='bounded input')
        self.o.reserve(self.cap['token'],self.req)
    def tearDown(self):self.t.cleanup()
    def acquire(self):return self.b.acquire('root','bailian',model='qwen3.8-flash',task_class='remote-qwen',host='ubuntu2',operator_child_id='leaf',ttl=600)
    def test_distinct_lease_and_duplicate_acquisition_refused(self):
        child=self.acquire();self.assertTrue(child.ok);self.assertNotEqual(child.lease_id,self.lease.lease_id)
        self.assertEqual(self.acquire().reason,'operator_authorization_refused')
        with self.o.transaction() as con:validate_child_admission(con,'leaf','root',now=self.now,admitted_lease_id=child.lease_id)
    def test_parent_released_after_reserve_refuses_real_acquire(self):
        self.b.release(self.lease.lease_id,'root')
        self.assertEqual(self.acquire().reason,'operator_authorization_refused')
    def test_expired_after_reserve_refuses_real_acquire(self):
        self.now=1600.
        self.assertEqual(self.acquire().reason,'operator_authorization_refused')
    def test_expired_after_child_grant_refuses_start(self):
        child=self.acquire();self.assertTrue(child.ok);self.now=1600.
        with self.o.transaction() as con:
            with self.assertRaises(DelegationRefused):validate_child_admission(con,'leaf','root',now=self.now,admitted_lease_id=child.lease_id)
    def test_ordinary_acquire_does_not_need_operator_tables(self):
        result=self.b.acquire('ordinary','bailian',model='qwen3.8-flash',task_class='remote-qwen',host='ubuntu2');self.assertTrue(result.ok)
    def test_wrong_root_cannot_consume_child_reservation(self):
        self.assertFalse(self.b.acquire('foreign','bailian',operator_child_id='leaf').ok)
    def test_unchanged_adapter_result_binding_is_double_checked(self):
        state=dict(result_available=True,root_id='root',parent_run_id='operator',rc=0)
        fake=type('Fake',(),{'inspect_run':staticmethod(lambda _:state), 'read_result':staticmethod(lambda *a,**k:b'ok')})
        with patch.dict('sys.modules',{'fabric_task':fake}):
            r=self.o.observe(self.cap['token'],'result','leaf');self.assertEqual(r['content'],'ok')
        with patch.object(fake,'read_result',side_effect=[b'old',b'changed']),patch.dict('sys.modules',{'fabric_task':fake}):
            with self.assertRaises(DelegationRefused):self.o.observe(self.cap['token'],'result','leaf')
if __name__=='__main__':unittest.main()
