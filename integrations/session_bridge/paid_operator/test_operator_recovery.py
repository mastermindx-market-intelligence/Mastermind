import hashlib,json,os,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import fabric_operator_recovery as r

class Recovery(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.here=Path(self.temp.name).resolve();(self.here/'broker').mkdir();(self.here/'state/remote_sub').mkdir(parents=True)
  (self.here/'broker/leases.lock').touch();con=sqlite3.connect(self.here/'broker/leases.sqlite');con.execute('CREATE TABLE leases (orchestrator_id TEXT,granted_at REAL)');con.close()
  owner=r.OperatorOwner(here=self.here);owner.authorize_root(r.ROOT,4,time.time()+7000)
  for name in ('remote_sub.sh','fabric_operator_recovery.py','fabric_operator_owner.py'):(self.here/name).write_bytes((Path(r.__file__).parent/name).read_bytes())
  self.log=self.here/'state/remote_sub'/(r.RUN+'.log');self.log.write_bytes((r.EVIDENCE/'operator-live.stderr').read_bytes().split(b'/Users/chriswong/.claude/projects/')[0]);self.log.chmod(0o600)
  self.env={'CODEX_THREAD_ID':r.ROOT,'POOL_ORCHESTRATOR_ID':r.ROOT,'POOL_PARENT_RUN_ID':r.ROOT,'POOL_TASK_CLASS':'domain_orchestration','POOL_OPERATOR_CHILD_BUDGET':'1','POOL_TASK_COMPLEXITY':'C3_FRONTIER_JUDGMENT','FABRIC_OPERATOR_PRELEASE_CONTINUATION':r.RUN}
  self.source=patch.object(r,'__file__',str(self.here/'fabric_operator_recovery.py'));self.source.start();self.environment=patch.dict(os.environ,self.env,clear=True);self.environment.start()
 def tearDown(self):self.environment.stop();self.source.stop();self.temp.cleanup()
 def permit(self):r.write_once(self.log.with_suffix('.prelease-permit.json'),r.permit_spec(self.here))
 def reserve(self):r.reserve(str(self.log),r.RUN,'ubuntu2','glm','glm-5.3',str(r.EVIDENCE/'OPERATOR_LIVE_PACKET.txt'),'~')
 def test_exact_original_continues_once_and_preserves_log(self):
  before=self.log.read_bytes();self.permit();self.reserve();self.assertTrue(self.log.read_bytes().startswith(before));self.assertIn(b'PRELEASE_CONTINUATION',self.log.read_bytes())
  with self.assertRaises(ValueError):self.reserve()
 def test_environment_flag_without_issued_permit_is_not_authority(self):
  with self.assertRaises(FileNotFoundError):self.reserve()
 def test_wrong_root_refuses(self):
  self.permit();os.environ['POOL_PARENT_RUN_ID']='other'
  with self.assertRaises(ValueError):self.reserve()
 def test_changed_log_refuses(self):
  self.permit();self.log.write_text(self.log.read_text()+'LAUNCH stdout=unknown\n')
  with self.assertRaises(ValueError):self.reserve()
 def test_changed_controller_refuses(self):
  self.permit();(self.here/'remote_sub.sh').write_text('changed')
  with self.assertRaises(ValueError):self.reserve()
 def test_existing_operator_grant_refuses(self):
  self.permit();con=sqlite3.connect(self.here/'broker/leases.sqlite');con.execute('INSERT INTO operator_grants VALUES (?,?,?,?,?)',(r.RUN,r.ROOT,'x','{}','{}'));con.commit();con.close()
  with self.assertRaises(ValueError):self.reserve()
 def test_unrelated_root_lease_does_not_block(self):
  con=sqlite3.connect(self.here/'broker/leases.sqlite');con.execute('INSERT INTO leases VALUES (?,?)',(r.ROOT,time.time()));con.commit();con.close();self.permit();self.reserve()
 def test_changed_cwd_refuses(self):
  self.permit()
  with self.assertRaises(ValueError):r.reserve(str(self.log),r.RUN,'ubuntu2','glm','glm-5.3',str(r.EVIDENCE/'OPERATOR_LIVE_PACKET.txt'),'/other')
class PostSupport(Recovery):
 def setUp(self):
  super().setUp();os.environ['FABRIC_OPERATOR_POST_SUPPORT_CONTINUATION']=r.RUN
  live=Path('/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext/state/remote_sub')
  self.log.write_bytes((live/(r.RUN+'.log')).read_bytes())
  for suffix in ('.prelease-permit.json','.prelease-continuation.json'):
   dest=self.log.with_suffix(suffix);dest.write_bytes((live/(r.RUN+suffix)).read_bytes());dest.chmod(0o600)
  con=sqlite3.connect(self.here/'broker/leases.sqlite');con.execute('DROP TABLE leases');con.execute('CREATE TABLE leases (id TEXT,orchestrator_id TEXT,pool TEXT,account TEXT,task_class TEXT,model TEXT,host TEXT,state TEXT,granted_at REAL)');con.execute('INSERT INTO leases VALUES (?,?,?,?,?,?,?,?,?)',('6f427ba04ba1',r.ROOT,'glm','chairman-max','remote-glm','glm-5.3','ubuntu2','released',time.time()));con.commit();con.close()
 def permit(self):r.write_once(self.log.with_suffix('.post-support-permit.json'),r.permit_spec(self.here))
 def test_exact_original_continues_once_and_preserves_log(self):
  before=self.log.read_bytes();self.permit();self.reserve();self.assertTrue(self.log.read_bytes().startswith(before));self.assertIn(b'POST_SUPPORT_CONTINUATION',self.log.read_bytes())
  with self.assertRaises(ValueError):self.reserve()
 def test_unrelated_root_lease_does_not_block(self):
  self.permit();self.reserve()
 def test_original_lease_must_be_released(self):
  self.permit();con=sqlite3.connect(self.here/'broker/leases.sqlite');con.execute("UPDATE leases SET state='held'");con.commit();con.close()
  with self.assertRaises(ValueError):self.reserve()
if __name__=='__main__':unittest.main()
