"""Synthetic-only qualification of private provider diagnostic projection/export."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProviderDiagnosticExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Keep the real custody guard: /tmp is world-writable on Linux.
        cls.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        result = subprocess.run([sys.executable, str(ROOT/'ops/native_fabric/quota_continuity/rollout/build_review_stage.py'), '--output', cls.tmp.name], capture_output=True, text=True)
        if result.returncode: raise AssertionError(result.stderr)
        cls.ext = Path(cls.tmp.name)/'native-code-stage/ext'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_case(self, code):
        prefix = f"import sys\nsys.path.insert(0,{str(self.ext)!r})\n"
        prefix += '''import original_delivery_collector as c
import artifact_delivery as d
import artifact_reader as reader
import json, os, tempfile, hashlib
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager

@contextmanager
def synthetic_destination(path):
    path.mkdir(mode=0o700)
    with d.DirectoryChain(path) as chain:yield chain

def events(error='server_error', status=None):
    return [{'type':'system','subtype':'init'},
        {'type':'assistant','error':error,'message':{'content':[{'type':'text','text':'PROMPT_SECRET https://u:password@bad/?token=SECRET'}]}},
        {'type':'result','subtype':'success','is_error':True,'api_error_status':status,'num_turns':1,'result':'ENV_SECRET'}]

def raw_events(error='server_error',status=None):
    return c.canonical(events(error,status))

def fixture(home):
    rid='synthetic-run'
    for relative in ['lanes/ext/lanes','lanes/ext/active']:
        (home/relative).mkdir(parents=True,mode=0o700,exist_ok=True)
    raw=raw_events(); cap={'file':rid+'.provider.capture.jsonl','sha256':c.sha(raw),'bytes':len(raw),'source_bytes':len(raw),'truncated':False}
    outcome={'schema':'mastermind.provider_outcome.v1','run_id':rid,'root_id':'root','host':'host','provider':'glm','model':'glm-5.3-flash','account':'account','lease_id':'a'*12,'command_rc':1,'stdout_sha256':'b'*64,'api_status':None,'initial_rejection':False,'kind':'provider_error','diagnostic_capture':cap,'capture_sha256':cap['sha256'],'capture_bytes':cap['bytes']}
    provider=c.canonical(outcome)
    packet=b'synthetic private packet';support={'synthetic.py':c.sha(b'pass')};support_digest=c.sha(c.canonical({'schema':'remote-support-code.v1','files':support}))
    contract={'schema':c.PLAIN_SCHEMA,'run_id':rid,'root':'root','parent':'parent','names':[],'packet_sha256':c.sha(packet),'support_digest':support_digest,'binding_sha256':'d'*64,'acquire_response_sha256':'e'*64}
    request={'schema':c.SCHEMA,'run_id':rid,'root':'root','parent':'parent','host':'host','contract':contract,'diagnostic':{'schema':c.DIAGNOSTIC_SCHEMA,'scope':{'run_id':rid,'root':'root','parent':'parent','host':'host'},'provider_sha256':c.sha(provider),'process_sha256':'c'*64,'lease_id':'a'*12,'account':'account','model':'glm-5.3-flash','command_rc':1,'capture':cap,'lane_root':None}}
    lane=home/'lanes/ext/lanes'
    for name,data in [(rid+'.provider.json',provider),(cap['file'],raw),(rid+'.provider.capture.json',c.canonical(cap))]:
        p=lane/name;p.write_bytes(data);p.chmod(0o600)
    cleanup={'identity_verified':True,'census_proven':True,'residual_count':0,'status':'not_needed','error_code':None}
    for stem in ['stdout_capture','stderr_capture','stdin_delivery']:
        cleanup[stem+'_complete']=True;cleanup[stem+'_error']=None
    process={'schema':'mastermind.local_owned_process_receipt.v1','label':rid,'returncode':1,'runtime_failure_code':None,'pid':123,'pgid':123,'stdout_bytes':10,'stderr_bytes':0,'stdout_sha256':'b'*64,'stdout_truncated':False,'stderr_truncated':False,'timed_out':False,'started_at':'2026-11-03T12:00:00Z','ended_at':'2026-11-03T12:00:01Z','cleanup':cleanup}
    process_raw=c.canonical(process);request['diagnostic']['process_sha256']=c.sha(process_raw)
    (lane/(rid+'.process.jsonl')).write_bytes(process_raw);(lane/(rid+'.process.jsonl')).chmod(0o600)
    tmp=home/'lanes/tmp';tmp.mkdir(mode=0o700);(tmp/(rid+'.txt')).write_bytes(packet);(tmp/(rid+'.txt')).chmod(0o600)
    release=home/'lanes/support-releases'/support_digest;release_ext=release/'ext';release_ext.mkdir(mode=0o700,parents=True)
    (release/'RELEASE.json').write_bytes(c.canonical({'schema':'remote-support-code.v1','digest':support_digest,'files':support}));(release/'RELEASE.json').chmod(0o600)
    (release_ext/'synthetic.py').write_bytes(b'pass');(release_ext/'synthetic.py').chmod(0o600)
    rc=home/'lanes/ext'/('lanes_'+rid+'.rc');rc.write_bytes(b'1');rc.chmod(0o600)
    return request,lane,outcome
'''
        result = subprocess.run([sys.executable,'-B','-c',prefix+code], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_structured_discriminators_and_unknowns(self):
        self.run_case("""
p=c.project_provider_capture(raw_events('model_not_found',404), {'api_status':404,'initial_rejection':False})
assert p['model_refusal_evidence']=='typed_model_not_found_http_4xx' and p['api_status']==404
p=c.project_provider_capture(raw_events('model_not_found'), {'api_status':None,'initial_rejection':False})
assert p['model_refusal_evidence']=='unknown' and p['api_status'] is None
p=c.project_provider_capture(raw_events('server_error'), {})
assert p['initial_rejection'] is None and p['api_status'] is None
assert 'SECRET' not in c.canonical(p).decode() and 'http' not in c.canonical(p).decode()
""")

    def test_dns_and_prose_are_distinct_from_model_refusal(self):
        self.run_case("""
e=events({'code':'EAI_AGAIN'});e[-1]['result']='[claude-code:unrecognized_model] glm-5.3-flash'
p=c.project_provider_capture(c.canonical(e),{})
assert p['dns_error']=='EAI_AGAIN' and p['model_refusal_evidence']=='unknown'
p=c.project_provider_capture(raw_events('unrecognized_model'),{})
assert p['error_types']==[] and p['dns_error'] is None
""")

    def test_malformed_truncated_duplicate_and_nonfinite(self):
        self.run_case("""
for raw in [b'{',b'[]',b'{"type":"result","type":"result"}',b'{"type":"result","num_turns":NaN}',c.canonical(events()+[events()[-1]]),c.canonical(events()[:-1])]:
 try:c.project_provider_capture(raw,{})
 except (ValueError,TypeError):pass
 else:raise AssertionError('invalid capture admitted')
""")

    def test_bool_status_and_mismatched_receipts_refuse(self):
        self.run_case("""
for raw,receipt in [(raw_events(status=True),{}),(raw_events(status=404),{'api_status':500}),(raw_events(),{'initial_rejection':True})]:
 try:c.project_provider_capture(raw,receipt)
 except ValueError:pass
 else:raise AssertionError('contradiction admitted')
""")

    def test_remote_projection_contains_no_raw_capture(self):
        self.run_case("""
with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
 request,lane,outcome=fixture(Path(t).resolve());row=c.remote_diagnostic_envelope(request,home=Path(t).resolve())
 assert row['state']=='DIAGNOSED',row
 data=c.canonical(row)
 assert b'SECRET' not in data and b'password' not in data and b'data_base64' not in data
 assert set(row)=={'schema','request_sha256','state','projection'}
""")

    def test_fixed_paths_wrong_identity_and_unknown_keys(self):
        self.run_case("""
for change in ['run','root','path','unknown','parent','layout']:
 with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
  request,lane,outcome=fixture(Path(t).resolve())
  if change in ['run','root','parent']:request[{'run':'run_id','root':'root','parent':'parent'}[change]]='wrong'
  if change=='layout':request['diagnostic']['lane_root']={'path':'/different'}
  if change=='path':request['diagnostic']['capture']['file']='../../secret'
  if change=='unknown':request['diagnostic']['unexpected']='SECRET'
  row=c.remote_diagnostic_envelope(request,home=Path(t).resolve())
  assert row['state']=='UNAVAILABLE' and row['reason']=='diagnostic_unavailable',row
  assert b'SECRET' not in c.canonical(row)
""")

    def test_symlink_permissions_owner_and_hash_mutation(self):
        self.run_case("""
for change in ['symlink','writable','size','digest','truncated','provider','owner','active','process','packet','parent','cleaned']:
 with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
  request,lane,outcome=fixture(Path(t).resolve());p=lane/request['diagnostic']['capture']['file']
  if change=='symlink':p.rename(lane/'private');p.symlink_to(lane/'private')
  if change=='writable':p.chmod(0o666)
  if change=='size':p.write_bytes(b'{}')
  if change=='digest':p.write_bytes(b'X'*p.stat().st_size)
  if change=='truncated':request['diagnostic']['capture']['truncated']=True
  if change=='provider':(lane/'synthetic-run.provider.json').write_bytes(b'{}')
  if change=='process':(lane/'synthetic-run.process.jsonl').write_bytes(b'{}')
  if change=='packet':(Path(t).resolve()/'lanes/tmp/synthetic-run.txt').write_bytes(b'wrong')
  if change=='parent':request['contract']['parent']='wrong'
  if change=='cleaned':(lane/'synthetic-run.process.jsonl').unlink()
  if change=='active':(Path(t).resolve()/'lanes/ext/active/synthetic-run').write_text('HOLD')
  if change=='owner':
   original=c.os.fstat
   def bad(fd):
    s=original(fd)
    if s.st_ino==p.stat().st_ino:
     values=list(s);values[4]=s.st_uid+1;return os.stat_result(values)
    return s
   with patch.object(c.os,'fstat',bad):row=c.remote_diagnostic_envelope(request,home=Path(t).resolve())
  else:row=c.remote_diagnostic_envelope(request,home=Path(t).resolve())
  assert row['state']=='UNAVAILABLE' and row['reason']=='diagnostic_unavailable',change
""")

    def test_generated_reader_has_same_safe_boundary(self):
        self.run_case("""
with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
 request,lane,outcome=fixture(Path(t).resolve());code=c.code_for_request(request);ns={}
 exec(code[:code.rfind('\\ntry:\\n raw=')],ns)
 row=ns['remote_envelope'](request,home=Path(t).resolve())
 assert row['state']=='DIAGNOSED' and b'SECRET' not in c.canonical(row)
""")

    def test_original_result_nonzero_contract_unchanged(self):
        self.run_case("""
request={'schema':c.SCHEMA,'run_id':'r','root':'root','parent':'parent','host':'host','contract':{}}
row={'schema':c.SCHEMA,'request_sha256':c.sha(c.canonical(request)),'state':'NONZERO','files':{},'artifacts':[]}
try:c.validate_response(c.canonical(row),request,'glm')
except ValueError:pass
else:raise AssertionError('rc1 became accepted result')
""")

    def test_initial_rejection_uses_incumbent_safe_event_boundary(self):
        self.run_case("""
for change in ['tool','parent','system','subtype','terminal']:
 e=events('rate_limit',429);receipt={'kind':'rate_limit','initial_rejection':True,'api_status':429,'cli_subtype':'success'}
 if change=='tool':e[1]['message']['content']=[{'type':'tool_use','input':{'SECRET':'SECRET'}}]
 if change=='parent':e[1]['parent_tool_use_id']='SECRET'
 if change=='system':e[0]['subtype']='arbitrary_SECRET'
 if change=='subtype':e[-1]['subtype']='error_during_execution'
 if change=='terminal':receipt['cli_terminal_reason']='completed';e[-1]['terminal_reason']='hook_stopped'
 try:c.project_provider_capture(c.canonical(e),receipt)
 except ValueError:pass
 else:raise AssertionError(change)
p=c.project_provider_capture(raw_events('rate_limit',429),{'kind':'rate_limit','initial_rejection':True,'api_status':429,'cli_subtype':'success'})
assert p['initial_rejection'] is True
""")

    def test_mutation_after_parse_refuses_without_leakage(self):
        self.run_case("""
with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
 request,lane,outcome=fixture(Path(t).resolve());original=c.project_provider_capture
 def race(raw,outcome):
  value=original(raw,outcome);(lane/'synthetic-run.process.jsonl').write_text('SECRET');return value
 with patch.object(c,'project_provider_capture',race):
  row=c.remote_diagnostic_envelope(request,home=Path(t).resolve())
 assert row['state']=='UNAVAILABLE' and b'SECRET' not in c.canonical(row)
""")

    def test_process_provider_disagreement_and_unknown_custody(self):
        self.run_case("""
for change in ['rc','hash','cleanup','timeout','boolpid','residual','stdin','time']:
 with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
  request,lane,outcome=fixture(Path(t).resolve());process=reader.strict_json((lane/'synthetic-run.process.jsonl').read_bytes())
  if change=='rc':process['returncode']=2
  if change=='hash':process['stdout_sha256']='a'*64
  if change=='cleanup':process['cleanup']['census_proven']=False
  if change=='timeout':process['timed_out']=True
  if change=='boolpid':process['pid']=True
  if change=='residual':process['cleanup']['residual_count']=False
  if change=='stdin':process['cleanup']['stdin_delivery_complete']=False
  if change=='time':process['ended_at']='2026-11-03T11:00:00Z'
  try:c.validate_diagnostic_process(outcome,process,'synthetic-run')
  except ValueError:pass
  else:raise AssertionError(change)
""")

    def test_original_caller_correlation_is_not_replaceable_by_labels(self):
        self.run_case("""
with patch.dict(os.environ,{'CODEX_THREAD_ID':'child','POOL_ORCHESTRATOR_ID':'root'}):
 try:c.require_caller('root')
 except ValueError:pass
 else:raise AssertionError('borrowed root label admitted')
""")

    def test_local_lease_and_source_rechecks_before_publication(self):
        self.run_case("""
with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
 request,lane,outcome=fixture(Path(t).resolve());original=(request,'hostalias','a'*64,'b'*64,{})
 response=c.canonical(c.remote_diagnostic_envelope(request,home=Path(t).resolve()))
 with patch.object(c,'qualify_provider_diagnostics',side_effect=[original,ValueError('SECRET https://u:pw@bad')]),patch.object(d,'transport',return_value=response),patch.object(d,'reserve_destination',synthetic_destination):
  try:c.collect_provider_diagnostics('binding',run_id='synthetic-run',root='root',parent='parent',destination=Path(t).resolve()/'export')
  except ValueError as error:assert str(error)=='diagnostic_unavailable'
  else:raise AssertionError('source mutation published')
 assert not (Path(t).resolve()/'export/receipt.json').exists()
""")

    def test_transport_and_response_refusals_do_not_echo_untrusted_text(self):
        self.run_case("""
for effect in ['transport','extra','invalid']:
 with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
  request,lane,outcome=fixture(Path(t).resolve());original=(request,'hostalias','a'*64,'b'*64,{})
  response=c.remote_diagnostic_envelope(request,home=Path(t).resolve())
  if effect=='extra':response['SECRET']='https://u:pw@bad'
  kwargs={'side_effect':RuntimeError('SECRET https://u:pw@bad')} if effect=='transport' else {'return_value':b'SECRET malformed' if effect=='invalid' else c.canonical(response)}
  with patch.object(c,'qualify_provider_diagnostics',return_value=original),patch.object(d,'transport',**kwargs),patch.object(d,'reserve_destination',synthetic_destination):
   try:c.collect_provider_diagnostics('binding',run_id='synthetic-run',root='root',parent='parent',destination=Path(t).resolve()/'export')
   except ValueError as error:assert str(error)=='diagnostic_unavailable'
   else:raise AssertionError(effect)
  assert not list((Path(t).resolve()/'export').glob('read-response*'))
""")

    def test_qualified_failure_only_preserves_original_proofs(self):
        self.run_case("""
import provider_outcome as po
for change in ['qualified','success','missing','malformed','truncated','symlink','mode','active']:
 with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
  home=Path(t).resolve();request,lane,outcome=fixture(home)
  if change=='success':
   outcome['command_rc']=0
   process=reader.strict_json((lane/'synthetic-run.process.jsonl').read_bytes());process['returncode']=0
   (lane/'synthetic-run.process.jsonl').write_bytes(c.canonical(process))
   (lane/'synthetic-run.provider.json').write_bytes(c.canonical(outcome))
  if change=='missing':(lane/'synthetic-run.provider.capture.jsonl').unlink()
  if change=='malformed':(lane/'synthetic-run.provider.capture.jsonl').write_text('SECRET malformed')
  if change=='truncated':
   outcome['diagnostic_capture']['truncated']=True;(lane/'synthetic-run.provider.json').write_bytes(c.canonical(outcome))
  if change=='symlink':
   p=lane/'synthetic-run.provider.capture.jsonl';p.rename(lane/'private');p.symlink_to(lane/'private')
  if change=='mode':(lane/'synthetic-run.provider.capture.jsonl').chmod(0o644)
  if change=='active':(home/'lanes/ext/active/synthetic-run').write_text('HOLD')
  assert po.diagnostic_retention_ready(str(home/'lanes'),'synthetic-run','root') is (change=='qualified'),change
""")

    def test_local_qualification_requires_actual_released_identity(self):
        self.run_case("""
import fabric_task
for change in ['qualified','active','unknown','root','parent','process','hold']:
 with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
  home=Path(t).resolve();request,lane,outcome=fixture(home);base=home/'lanes/ext/state/remote_sub';base.mkdir(parents=True)
  for suffix in ['provider.json','process.jsonl']:
   data=(lane/('synthetic-run.'+suffix)).read_bytes();p=base/('synthetic-run.'+suffix);p.write_bytes(data);p.chmod(0o600)
  value={'run_id':'synthetic-run','root':'root','parent':'parent','host':'host','mode':'glm','requested_model':'glm-5.3-flash'}
  binding={'lease_id':'a'*12,'account':'account','acquisition_pool':'glm','transport':{'lane_root':None}}
  qualified=(value,b'binding',{'packet':b'packet','log':b'log','support':b'support'},request['contract'],'alias',b'registry',None,binding)
  state={'state':'TERMINAL','lineage_state':'VERIFIED_TERMINAL','root_id':'root','parent_run_id':'parent'}
  lease={'id':'a'*12,'orchestrator_id':'root','host':'host','account':'account','model':'glm-5.3-flash','pool':'glm','state':'released'}
  if change=='active':lease['state']='active'
  if change=='unknown':state['state']='EFFECT_UNKNOWN'
  if change=='root':lease['orchestrator_id']='different'
  if change=='parent':state['parent_run_id']='different'
  if change=='process':(base/'synthetic-run.process.jsonl').write_text('{}')
  if change=='hold':(home/'lanes/ext/active/synthetic-run').write_text('HOLD')
  with patch.object(c,'HERE',home/'lanes/ext'),patch.object(c,'load_binding',return_value=qualified),patch.object(fabric_task,'inspect_run',return_value=state),patch.object(d,'retained_lease',return_value=lease):
   if change=='qualified':
    result=c.qualify_provider_diagnostics('binding',run_id='synthetic-run',root='root',parent='parent')
    assert result[0]['diagnostic']['process_sha256']==c.sha((base/'synthetic-run.process.jsonl').read_bytes())
   else:
    try:c.qualify_provider_diagnostics('binding',run_id='synthetic-run',root='root',parent='parent')
    except (ValueError,KeyError):pass
    else:raise AssertionError(change)
""")

    def test_successful_safe_publication_and_publication_race(self):
        self.run_case("""
for mutate in [False,True]:
 with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
  home=Path(t).resolve();request,lane,outcome=fixture(home);original=(request,'alias','a'*64,'b'*64,{})
  response=c.canonical(c.remote_diagnostic_envelope(request,home=home));counter=[0]
  def qualify(*args,**kwargs):
   counter[0]+=1
   if mutate and counter[0]>=3:raise ValueError('SECRET source changed')
   return original
  with patch.object(c,'qualify_provider_diagnostics',qualify),patch.object(d,'transport',return_value=response),patch.object(d,'reserve_destination',synthetic_destination):
   if not mutate:
    receipt=c.collect_provider_diagnostics('binding',run_id='synthetic-run',root='root',parent='parent',destination=home/'export')
    assert receipt['state']=='DIAGNOSED' and receipt['acceptance']=='NOT_RECORDED' and not receipt['producer_root_authenticated']
    assert b'SECRET' not in (home/'export/diagnostics.json').read_bytes()
   else:
    try:c.collect_provider_diagnostics('binding',run_id='synthetic-run',root='root',parent='parent',destination=home/'export')
    except ValueError as error:assert str(error)=='diagnostic_unavailable'
    else:raise AssertionError('race published')
    receipt=reader.strict_json((home/'export/receipt.json').read_bytes())
    assert receipt['state']=='UNAVAILABLE' and b'SECRET' not in c.canonical(receipt)
""")

    def test_actual_cleanup_branch_with_only_offline_transport(self):
        self.run_case("""
import shutil, subprocess
source=(Path(c.HERE)/'remote_sub.sh').read_text()
start=source.index('  require_bound_lane_layout_after_launch before_cleanup')
end=source.index('\\nfi\\n\\nrequire_bound_lane_layout_after_launch after_collection',start)
branch=source[start:end]
for change in ['qualified','success','missing','malformed','truncated','duplicate-provider','duplicate-process','duplicate-meta','nonfinite']:
 with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
  home=Path(t).resolve();request,lane,outcome=fixture(home);rid='synthetic-run'
  support=home/'lanes/support-releases'/request['contract']['support_digest']/'ext'
  for name in ['provider_outcome.py','lane_runtime.py']:
   shutil.copyfile(Path(c.HERE)/name,support/name)
  (home/'lanes/ext/lanes_synthetic-run.stdout').write_text('private diagnostic')
  (home/'lanes/tmp/synthetic-run.support-src').mkdir()
  if change=='success':
   outcome['command_rc']=0;(lane/(rid+'.provider.json')).write_bytes(c.canonical(outcome))
  if change=='missing':(lane/(rid+'.provider.capture.jsonl')).unlink()
  if change=='malformed':(lane/(rid+'.provider.capture.jsonl')).write_text('SECRET malformed')
  if change=='truncated':
   outcome['diagnostic_capture']['truncated']=True;(lane/(rid+'.provider.json')).write_bytes(c.canonical(outcome))
  if change.startswith('duplicate-'):
   suffix={'duplicate-provider':'provider.json','duplicate-process':'process.jsonl','duplicate-meta':'provider.capture.json'}[change]
   p=lane/(rid+'.'+suffix);raw=p.read_bytes();p.write_bytes(b'{"duplicate":1,"duplicate":2,'+raw[1:])
  if change=='nonfinite':
   p=lane/(rid+'.process.jsonl');raw=p.read_bytes();p.write_bytes(b'{"extra":NaN,'+raw[1:])
  fake=home/'offline-ssh'
  fake.write_text('#!'+sys.executable+'\\nimport subprocess,sys\\ncommand=sys.argv[-1]\\nassert command.startswith(("python3 ","rm -f"))\\nraise SystemExit(subprocess.run(["/bin/bash","-c",command]).returncode)\\n');fake.chmod(0o700)
  env=dict(os.environ,SSH_CMD=str(fake),SSH_ALIAS='inert',REMOTE_LANES_Q=str(home/'lanes'),REMOTE_RC='lanes_synthetic-run.rc',REMOTE_STDOUT='lanes_synthetic-run.stdout',ID=rid,ORCH_ID='root',SUPPORT_DIGEST=request['contract']['support_digest'],PROVIDER_SAVED='1',RECEIPT_SAVED='1',USAGE_SAVED='0',RC='0' if change=='success' else '1')
  prefix='require_bound_lane_layout_after_launch() { :; }\\ncommission_run() { shift; "$@"; }\\nlog() { printf "%s\\\\n" "$*"; }\\n'
  result=subprocess.run(['/bin/bash','-c',prefix+branch],env=env,capture_output=True,text=True,timeout=10)
  assert result.returncode==0,(change,result.stdout,result.stderr)
  for p in [home/'lanes/tmp/synthetic-run.txt',home/'lanes/ext/lanes_synthetic-run.rc',lane/'synthetic-run.process.jsonl']:
   assert p.exists() is (change=='qualified'),(change,p,result.stdout,result.stderr)
  assert not (home/'lanes/ext/lanes_synthetic-run.stdout').exists()
  assert ('DIAGNOSTIC_PROOFS_RETAINED' in result.stdout) is (change=='qualified'),(change,result.stdout,result.stderr)
  assert 'SECRET' not in result.stdout+result.stderr
""")

    def test_local_projection_rejects_unknown_or_contradictory_values(self):
        self.run_case("""
import copy
base=c.project_provider_capture(raw_events(),{})
for key,value in [('error_types',['SECRET https://u:pw@bad']),('dns_error','SECRET'),('api_status',True),('initial_rejection',True),('extra','SECRET'),('model_refusal_evidence','typed_model_not_found_http_4xx')]:
 row=copy.deepcopy(base);row[key]=value
 try:c.validate_diagnostic_projection(row)
 except ValueError as error:assert str(error)=='diagnostic_unavailable'
 else:raise AssertionError(key)
""")

    def test_world_writable_ancestor_refuses_with_trusted_sibling_positive(self):
        self.run_case("""
import provider_outcome as po
with tempfile.TemporaryDirectory(dir=c.HERE.parent.parent) as t:
 base=Path(t).resolve()
 for mode in [0o700,0o777]:
  ancestor=base/('trusted' if mode==0o700 else 'untrusted');ancestor.mkdir(mode=mode);ancestor.chmod(mode)
  home=ancestor/'fixture';home.mkdir(mode=0o700);request,lane,outcome=fixture(home)
  row=c.remote_diagnostic_envelope(request,home=home)
  if mode==0o700:
   assert row['state']=='DIAGNOSED' and po.diagnostic_retention_ready(str(home/'lanes'),'synthetic-run','root')
  else:
   assert row['state']=='UNAVAILABLE' and row['reason']=='diagnostic_unavailable'
   assert not po.diagnostic_retention_ready(str(home/'lanes'),'synthetic-run','root')
""")
