import os,sys,json,copy,hashlib,subprocess
from pathlib import Path
import pytest
BASE=Path(__file__).parent
EXT=Path.home()/'.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext'
CAND=Path(os.environ.get('NORMALIZATION_CANDIDATE',str(BASE/'candidate')))
sys.path[:0]=[str(CAND),str(EXT)]
import lane_runtime as lane,remote_sub_exec as executor,native_remote as native,artifact_production as producer,artifact_delivery as delivery

def sha(b):return hashlib.sha256(b).hexdigest()

@pytest.fixture(scope='module')
def original(tmp_path_factory):
 p=tmp_path_factory.mktemp('producer');(p/'lanes').mkdir()
 contract=dict(schema=producer.SCHEMA,root='fixture-root',parent='fixture-parent',run_id='fixture-grok',names=['result.md'],body_sha256='a'*64,support_digest='b'*64)
 manifest=dict(schema=producer.RESULT_SCHEMA,request_sha256=sha(producer.reader.canonical(contract)),root=contract['root'],parent=contract['parent'],run_id=contract['run_id'],host='ubuntu2',files=[dict(path=producer.paths(contract)[0],bytes=7,sha256=sha(b'fixture'))])
 display='Bounded final\n'+producer.RESULT_PREFIX+json.dumps(manifest)
 raw=json.dumps({'text':display,'thought':'private test filler','usage':{}})
 path=p/'lanes/fixture-grok.process.jsonl'
 result=lane.run_owned_process([sys.executable,'-c','import sys;sys.stdout.buffer.write('+repr(raw.encode())+')'],timeout=3,label='fixture-grok',receipt_path=path)
 assert result.returncode==0 and result.cleanup_proven
 env=dict(POOL_ORCHESTRATOR_ID=contract['root'],POOL_PARENT_RUN_ID=contract['parent'],REMOTE_SUB_RUN_ID=contract['run_id'],LANE_REMOTE_HOST='ubuntu2',POOL_LEASE_ID='fixture-lease',POOL_ACCOUNT='fixture-account',SUPPORT_DIGEST='b'*64)
 binding=executor.grok_output_binding(path,contract,manifest,result.stdout,display,env)
 native.terminal(p,'fixture-grok','grok','grok-4.6',env,True,0,output_binding=binding)
 terminal=json.loads((p/'lanes/fixture-grok.native-terminal.json').read_text());process=json.loads(path.read_text())
 request=dict(run_id='fixture-grok',root='fixture-root',parent='fixture-parent',host='ubuntu2',stdout_sha256=sha(display.encode()),paths=producer.paths(contract))
 return dict(raw=raw,stdout=display.encode(),terminal=terminal,process=process,request=request,path=path,contract=contract,manifest=manifest,env=env)

@pytest.fixture
def case(original,monkeypatch):
 d=copy.deepcopy(original)
 monkeypatch.setattr(delivery,'retained_lease',lambda _:dict(id='fixture-lease',orchestrator_id='fixture-root',host='ubuntu2',account='fixture-account',model='grok-4.6',state='released'))
 return d

def qualify(d):return delivery.qualify_native(d['request'],dict(stdout=d['stdout'],terminal=json.dumps(d['terminal']).encode(),process=json.dumps(d['process']).encode()))

def test_actual_raw_capture_normalized_binding_roundtrip(case):
 d=case;assert len(d['raw'].encode())!=len(d['stdout'])
 assert d['process']['stdout_sha256']==sha(d['raw'].encode())
 assert qualify(d)==dict(lease_id='fixture-lease',mode='grok')

@pytest.mark.parametrize('field',['parent','root','run_id','host','lease_id','account','support_digest','raw_bytes','raw_sha256','normalized_bytes','normalized_sha256','algorithm','extra','contract','manifest','process_digest','cleanup','truncated','stdout','duplicate','old_missing'])
def test_mismatch_refuses(case,field):
 d=case;b=d['terminal']['output_binding']
 if field in {'raw_bytes','normalized_bytes'}:b[field]+=1
 elif field=='extra':b['unexpected']=True
 elif field=='contract':b['contract']['body_sha256']='e'*64
 elif field=='manifest':b['manifest']['files'][0]['sha256']='e'*64
 elif field=='process_digest':d['process']['stdout_sha256']='e'*64
 elif field=='cleanup':d['process']['cleanup']={}
 elif field=='truncated':d['process']['stdout_truncated']=True
 elif field=='stdout':d['stdout']+=b'x'
 elif field=='duplicate':
  d['stdout']+=b'\n'+producer.RESULT_PREFIX.encode()+json.dumps(b['manifest']).encode()
  b['normalized_bytes']=len(d['stdout']);b['normalized_sha256']=d['request']['stdout_sha256']=sha(d['stdout'])
 elif field=='old_missing':del d['terminal']['output_binding']
 else:b[field]='e'*64
 with pytest.raises(ValueError):qualify(d)

def test_legacy_plaintext_exact_length_remains(case):
 d=case;del d['terminal']['output_binding'];d['terminal']['capture']['stdout_bytes']=d['process']['stdout_bytes']=len(d['stdout'])
 assert qualify(d)['mode']=='grok'

def test_producer_refuses_reconstructed_wrong_raw(original):
 d=original
 with pytest.raises(ValueError):executor.grok_output_binding(d['path'],d['contract'],d['manifest'],d['raw']+'x',d['stdout'].decode(),d['env'])

def test_capture_hashes_original_invalid_utf8(tmp_path):
 path=tmp_path/'receipt'
 r=lane.run_owned_process([sys.executable,'-c',"import sys;sys.stdout.buffer.write(b'\\xff')"],timeout=3,receipt_path=path)
 p=json.loads(path.read_text())
 assert p['stdout_sha256']==sha(b'\xff') and p['stdout_sha256']!=sha(r.stdout.encode())

def test_artifact_and_controller_support_digest_agree(tmp_path):
 import remote_sub_helpers
 # Use actual installed source root; only producer path logic differs.
 got=producer.source_digest(EXT)
 proc=subprocess.run([sys.executable,str(EXT/'remote_sub_helpers.py'),'support-meta',str(EXT),str(tmp_path/'manifest.json'),*sorted(__import__('support_bundle').SOURCE_FILES)],capture_output=True,text=True)
 assert proc.returncode==0,proc.stderr
 assert got in proc.stdout


def test_dangling_policy_never_falls_back(tmp_path,monkeypatch):
 import support_bundle
 ext=tmp_path/'ext';ext.mkdir();(tmp_path/'orch/fabric').mkdir(parents=True)
 (tmp_path/'orch/fabric/pools.yaml').write_text('valid')
 (ext/'pools.yaml').symlink_to(tmp_path/'missing')
 monkeypatch.setattr(support_bundle,'SOURCE_FILES',{'pools.yaml'})
 with pytest.raises(ValueError,match='source_unavailable'):producer.source_digest(ext)

def test_producer_rejects_altered_normalized_text(original):
 d=original
 with pytest.raises(ValueError,match='transform_mismatch'):executor.grok_output_binding(d['path'],d['contract'],d['manifest'],d['raw'],'invented',d['env'])
