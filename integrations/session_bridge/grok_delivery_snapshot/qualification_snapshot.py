import os,sys,fcntl,importlib.util,json,sqlite3
from pathlib import Path
import pytest
BASE=Path(__file__).parent
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
sys.path.insert(0,str(EXT))
spec=importlib.util.spec_from_file_location('locked_delivery',Path(os.environ['FABRIC_DELIVERY_CANDIDATE']));d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

@pytest.fixture
def broker(tmp_path,monkeypatch):
 p=tmp_path/'broker';p.mkdir();(p/'leases.lock').write_bytes(b'');os.chmod(p/'leases.lock',0o600)
 with sqlite3.connect(p/'leases.sqlite') as c:
  c.execute('CREATE TABLE leases(id,orchestrator_id,host,account,model,state)')
  c.execute("INSERT INTO leases VALUES('lease','root','ubuntu3','default','grok-4.6','released')")
 monkeypatch.setattr(d,'HERE',tmp_path)
 return p

def test_original_snapshot_under_shared_writer_lock(broker,monkeypatch):
 orig=d.read_local_at;seen=[]
 def read(chain,name,limit):
  fd=os.open(broker/'leases.lock',os.O_RDWR)
  try:
   with pytest.raises(BlockingIOError):fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  finally:os.close(fd)
  seen.append(name);return orig(chain,name,limit)
 monkeypatch.setattr(d,'read_local_at',read)
 assert d.retained_lease('lease')['state']=='released';assert len(seen)==2

@pytest.mark.parametrize('suffix',['-wal','-journal'])
def test_sidecars_still_refuse(broker,suffix):
 (broker/('leases.sqlite'+suffix)).write_bytes(b'busy')
 with pytest.raises(ValueError,match='live_sidecar'):d.retained_lease('lease')

def test_existing_writer_times_out_without_write(broker):
 fd=os.open(broker/'leases.lock',os.O_RDWR);fcntl.flock(fd,fcntl.LOCK_EX)
 try:
  with d.DirectoryChain(broker) as chain:
   with pytest.raises(ValueError,match='snapshot_busy'):
    with d.LeaseSnapshotLock(chain,seconds=.03):pass
 finally:os.close(fd)

@pytest.mark.parametrize('mode',[0o622,0o666])
def test_unsafe_lock_refuses(broker,mode):
 os.chmod(broker/'leases.lock',mode)
 with pytest.raises(ValueError,match='lock_metadata'):d.retained_lease('lease')

def test_diagnostic_never_echoes_exception_secret(monkeypatch,capsys):
 monkeypatch.setattr(sys,'argv',['artifact_delivery','run','--root','root','--parent','parent','--host','ubuntu3','--stdout-sha256','a'*64,'--destination','/Volumes/Mastermind/evidence/x','--path','/tmp/file'])
 def fail(*a):raise ValueError('private_token_or_prompt')
 monkeypatch.setattr(d,'export',fail)
 assert d.main()==75
 text=capsys.readouterr().out;assert 'private_token' not in text and json.loads(text)['diagnostic']=='unclassified_local_failure'


def test_changed_lock_after_read_refuses(broker):
 with d.DirectoryChain(broker) as chain:
  with pytest.raises(ValueError,match='lease_lock_changed'):
   with d.LeaseSnapshotLock(chain):
    os.rename(broker/'leases.lock',broker/'original.lock')
    (broker/'leases.lock').write_bytes(b'');os.chmod(broker/'leases.lock',0o600)

def test_permission_is_distinct(monkeypatch,capsys):
 monkeypatch.setattr(sys,'argv',['artifact_delivery','run','--root','root','--parent','parent','--host','ubuntu3','--stdout-sha256','a'*64,'--destination','/Volumes/Mastermind/evidence/x','--path','/tmp/file'])
 def fail(*a):raise d.failure_phase(PermissionError('secret'), 'qualification')
 monkeypatch.setattr(d,'export',fail)
 assert d.main()==75
 obj=json.loads(capsys.readouterr().out)
 assert obj['diagnostic']=='permission_denied' and obj['failure_phase']=='qualification'
