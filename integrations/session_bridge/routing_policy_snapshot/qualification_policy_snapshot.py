import importlib.util,sys,os,json,hashlib,copy,fcntl
from pathlib import Path
import pytest,yaml
BASE=Path(os.environ.get('POLICY_EVIDENCE_DIR',str(Path(__file__).parent)))
CAND=Path(os.environ.get('POLICY_CANDIDATE',str(BASE/'candidate')))
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0,str(CAND));sys.path.insert(1,str(EXT))
import fabric_policy_snapshot as snap
import support_bundle as bundle

@pytest.fixture
def docs():
 b=BASE.parent/'grok-priority-20261012'
 return (b/'preimage/pools.yaml').read_bytes(),(b/'candidate/pools.yaml').read_bytes()

def test_exact_advisory_change_only(docs):
 old,new=docs;r=snap.compatible(new,old);assert r['stable_sha256']!=r['snapshot_sha256']

@pytest.mark.parametrize('field',['cap','model','role','unknown','reset_anchor','economic','bool_int'])
def test_critical_changes_fail(docs,field):
 old,new=docs;d=yaml.safe_load(new)
 if field=='cap':d['pools']['grok']['caps']['concurrent']=1000
 if field=='model':d['pools']['glm']['models']['executor']='evil'
 if field=='role':d['pools']['grok']['role']=['seat']
 if field=='unknown':d['unknown']='new'
 if field=='reset_anchor':d['pools']['grok']['windows']['weekly']['reset_anchor_file']='elsewhere'
 if field=='economic':d['routing']['acceptance_floor']='0.0 over last 20'
 if field=='bool_int':d['routing']['reviewer_not_author']=1
 with pytest.raises(ValueError,match='CRITICAL'):snap.compatible(yaml.safe_dump(d).encode(),old)

@pytest.mark.parametrize('raw',[b'a: 1\na: 2\n',b'[1,2]',b'a: .nan\n',b'1: value\n'])
def test_bad_yaml_fail(raw):
 with pytest.raises((ValueError,TypeError)):snap.parse_policy(raw)

@pytest.fixture
def fixture(tmp_path,docs):
 old,new=docs
 stable=tmp_path/'lanes/ext';stable.mkdir(parents=True)
 (stable/'active').mkdir();(stable.parent/'support-releases').mkdir()
 (stable.parent/'orch/fabric').mkdir(parents=True);(stable.parent/'orch/fabric/pools.yaml').write_bytes(old)
 source=tmp_path/'source';source.mkdir()
 for n in bundle.SOURCE_FILES:
  data=new if n=='pools.yaml' else (CAND/n).read_bytes() if (CAND/n).exists() else (EXT/n).read_bytes()
  (source/n).write_bytes(data)
 manifest={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in bundle.SOURCE_FILES}
 return stable,source,manifest

def test_publish_with_active_worker_keeps_global_bytes(fixture,docs):
 stable,source,manifest=fixture;(stable/'active/existing-worker').write_text('untouched')
 before=(stable.parent/'orch/fabric/pools.yaml').read_bytes()
 released=bundle.publish(source,stable,manifest)
 assert snap.verified_snapshot_path(released)==released/'pools.yaml'
 assert (stable.parent/'orch/fabric/pools.yaml').read_bytes()==before
 assert (stable/'active/existing-worker').read_text()=='untouched'
 assert bundle.publish(source,stable,manifest)==released
 assert snap.verify_for_admission(released,stable/'active')['stable_sha256']==hashlib.sha256(before).hexdigest()


def test_original_shared_policy_guard_still_refuses(fixture):
 stable,source,manifest=fixture;(stable/'active/existing').write_text('untouched')
 with pytest.raises(ValueError,match='STALE_ACTIVE'):bundle.ensure_policy(source/'pools.yaml',stable,manifest['pools.yaml'])


def test_drift_between_publication_and_admission_fails_without_marker(fixture,monkeypatch):
 stable,source,manifest=fixture;released=bundle.publish(source,stable,manifest)
 sp=importlib.util.spec_from_file_location('snapshot_lane',released/'lane_runtime.py')
 lane=importlib.util.module_from_spec(sp);sys.modules[sp.name]=lane;sp.loader.exec_module(lane)
 policy=stable.parent/'orch/fabric/pools.yaml';d=yaml.safe_load(policy.read_bytes());d['pools']['grok']['caps']['concurrent']=3;policy.write_text(yaml.safe_dump(d))
 with pytest.raises(lane.LaneRuntimeError,match='routing_policy_admission_refused'):
  lane.LaneLease.acquire(stable/'active',key='new-run',label='new-run',max_active=4,load1=0,cpu_count=8,env={})
 assert not (stable/'active/new-run').exists()


def test_actual_admission_holds_existing_lock_until_marker(fixture,monkeypatch):
 stable,source,manifest=fixture;released=bundle.publish(source,stable,manifest)
 sp=importlib.util.spec_from_file_location('snapshot_lane_ok',released/'lane_runtime.py')
 lane=importlib.util.module_from_spec(sp);sys.modules[sp.name]=lane;sp.loader.exec_module(lane)
 original=snap.verify_for_admission;seen=[]
 def check(here,active):
  fd=os.open(active/'.admission.lock',os.O_RDWR)
  try:
   with pytest.raises(BlockingIOError):fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  finally:os.close(fd)
  seen.append(True);return original(here,active)
 monkeypatch.setattr(snap,'verify_for_admission',check)
 lease=lane.LaneLease.acquire(stable/'active',key='new-run',label='new-run',max_active=4,load1=0,cpu_count=8,env={})
 try:assert seen and (stable/'active/new-run').exists()
 finally:lease.release()


def test_exhaustion_link_and_snapshot_tamper_refuse(fixture):
 stable,source,manifest=fixture;released=bundle.publish(source,stable,manifest)
 os.chmod(released,0o755);(released/'GROK_EXHAUSTED').unlink();(released/'GROK_EXHAUSTED').symlink_to(stable/'different');os.chmod(released,0o555)
 with pytest.raises(ValueError,match='SHARED_BINDING'):snap.verify_for_admission(released,stable/'active')
 os.chmod(released/'pools.yaml',0o600)
 with pytest.raises(ValueError,match='UNSEALED'):snap.verified_snapshot_path(released)

def test_actual_picker_uses_sealed_generation_not_stable_policy(fixture,docs):
 stable,source,manifest=fixture;released=bundle.publish(source,stable,manifest)
 sp=importlib.util.spec_from_file_location('snapshot_pick',released/'pick.py')
 p=importlib.util.module_from_spec(sp);sp.loader.exec_module(p)
 assert p.POOLS_YAML==str(released/'pools.yaml')
 assert p.load_pools()['routing']['grok_expiring_priority']['enabled'] is True
 assert 'grok_expiring_priority' not in yaml.safe_load((stable.parent/'orch/fabric/pools.yaml').read_bytes())['routing']


def test_controller_manifest_hashes_actual_policy_source(tmp_path,docs):
 import subprocess
 root=tmp_path/'ext';root.mkdir();(root.parent/'orch/fabric').mkdir(parents=True)
 old,new=docs;(root.parent/'orch/fabric/pools.yaml').write_bytes(new)
 (root/'worker.py').write_bytes(b'print(1)')
 target=tmp_path/'manifest.json'
 r=subprocess.run([sys.executable,str(CAND/'remote_sub_helpers.py'),'support-meta',str(root),str(target),'worker.py','pools.yaml'],capture_output=True,text=True)
 assert r.returncode==0,r.stderr
 files=json.loads(target.read_text());assert files['pools.yaml']==hashlib.sha256(new).hexdigest()
 expected=hashlib.sha256(json.dumps({'schema':'remote-support-code.v1','files':files},sort_keys=True,separators=(',',':')).encode()).hexdigest()
 assert r.stdout.split()==[expected,files['pools.yaml']]
