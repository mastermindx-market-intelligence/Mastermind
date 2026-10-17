"""Executable hostile tests for the package-local Reality verifier."""
from __future__ import annotations
import hashlib, importlib.util, json, struct, zlib
from copy import deepcopy
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
PKG=ROOT/'plugins/mastermind-reality'
V=PKG/'scripts/verify_reality_observation.py'
SCHEMA=PKG/'references/reality-observation.schema.json'
OBS=ROOT/'research/MASTERMIND_REALITY_R1_CONTROL_ROOM_OBSERVATION_2026-09-07.json'

def mod():
    assert V.is_file(), 'package-local deterministic verifier is missing'
    s=importlib.util.spec_from_file_location('reality_verifier',V); assert s and s.loader
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def sha(b): return hashlib.sha256(b).hexdigest()
def chunk(k,p): return struct.pack('>I',len(p))+k+p+struct.pack('>I',zlib.crc32(k+p)&0xffffffff)
def png(w,h):
    row=b'\0'+b'\0\0\0\xff'*w
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(row*h))+chunk(b'IEND',b'')
def put(root,ref,b):
    p=root/ref; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b)
    return {'artifact_ref':ref,'sha256':sha(b),'coverage':'fixture'}
def control(status,method,signal,refs=()):
    return {'status':status,'method':method,'signal':signal,'evidence_refs':list(refs),'detail':f'discriminates {signal}'}

def fixture(tmp):
    root=tmp/'owner'; dbytes,mbytes=png(40,30),png(20,35)
    d=put(root,'private-evidence/desktop.png',dbytes); m=put(root,'private-evidence/mobile.png',mbytes)
    sem=put(root,'private-evidence/semantic.json',b'{"surface":"advanced"}\n')
    run=put(root,'private-evidence/state.json',b'{"runtime":"degraded"}\n')
    eff=put(root,'private-evidence/effect.json',b'{"state":"NOT_APPLIED"}\n')
    clean=put(root,'private-evidence/cleanup.json',b'{"temporary_profile":"UNKNOWN"}\n')
    consumer='web-sol/current-chairman-directed-session'
    proof_body=json.dumps({'consumer_ref':consumer,'consumed_artifacts':[{'artifact_ref':d['artifact_ref'],'sha256':d['sha256']},{'artifact_ref':m['artifact_ref'],'sha256':m['sha256']}]},sort_keys=True).encode()
    proof=put(root,'private-evidence/consumption.json',proof_body)
    shots=[]
    for x,w,h,n in ((d,40,30,len(dbytes)),(m,20,35,len(mbytes))):
        shots.append({'artifact_ref':x['artifact_ref'],'sha256':x['sha256'],'mime_type':'image/png','bytes':n,'bytes_present':True,'viewport':{'width':w,'height':h},'data_state':'DEGRADED','consumption':{'state':'CONSUMED','consumer_ref':consumer,'method':'MODEL_VISIBLE_IMAGE_DELIVERY','proof_ref':proof['artifact_ref'],'proof_sha256':proof['sha256'],'consumed_at':None,'limitation':'Provider exposed no native consumption time.'}})
    r={'schema':'mastermind.reality_observation.v1','observation_id':'REALITY-TEST-001','capability_state':'PARTIAL','recorded_at':'2026-09-08T12:00:00Z','revision':{'state':'ORIGINAL','predecessor_observation_id':None,'changed_input_refs':[],'affected_finding_ids':[],'reason':None,'revised_conclusion':None},'persona':{'name':'Chairman','user_job':'Inspect one decision surface','non_goals':['account actuation']},'target':{'product':'Chairman Control Room','environment':'approved fixture','locator':'owner-qualified-loopback','authorization_ref':'current-live-assignment','surface_class':'APPROVED_PRODUCT','surface_name':'current Control Room inspector','experience_role':'ADVANCED','architecture_ref':'Mastermind:decision-first@e18cab4f3ca41725fdb517623543fa4fb1aba467','observed_surface_state':'PARTIAL'},'source_relationship':{'protected_sha':'a'*40,'observed_deployed_sha':'b'*40,'relation':'DIFFERENT','observed_at':'2026-09-08T11:59:00Z','revision_comparison':'DISTINCT'},'journey':{'steps':[{'action':'inspect','result':'degraded state visible'}],'outcome':'PARTIAL'},'capture':{'started_at':'2026-09-08T11:59:00Z','completed_at':'2026-09-08T11:59:10Z','screenshots':shots,'semantic_evidence':{'state':'AVAILABLE','artifacts':[{**sem,'consumed':True}],'reason':None},'runtime_evidence':{'state':'AVAILABLE','artifacts':[{**run,'consumed':True}],'reason':None}},'findings':[{'finding_id':'FINDING-001','basis':'MODEL_INFERENCE','claim':'Diagnostics compete with outcome.','evidence_refs':[d['artifact_ref'],sem['artifact_ref']],'unknowns':['No causal study.']}],'negative_controls':{'wrong_target':control('DETECTED','OWNER_EVIDENCE','HTTP_404',[eff['artifact_ref']]),'stale_capture':control('DETECTED','OWNER_EVIDENCE','STALE_INPUT_DISCLOSED',[run['artifact_ref']]),'different_build':control('DETECTED','OWNER_EVIDENCE','SOURCE_SHA_DISTINCT',[run['artifact_ref']]),'different_viewport_or_data_state':control('DETECTED','OWNER_EVIDENCE','VIEWPORT_OR_DATA_STATE_DISTINCT',[d['artifact_ref'],m['artifact_ref']]),'missing_screenshot_bytes':control('REFUSED','CONTRACT_REFUSAL','SCREENSHOT_BYTES_REQUIRED'),'broken_browser_connection':control('DETECTED','OWNER_EVIDENCE','PROVIDER_DISCONNECTED',[run['artifact_ref']]),'excluded_account_surface':control('REFUSED','CONTRACT_REFUSAL','TARGET_CLASS_EXCLUDED')},'effect':{'state':'NOT_APPLIED','operation_ref':'reality-test','carrier_ref':consumer,'evidence':[eff],'detail':'Read-only.'},'cleanup':{'state':'INCOMPLETE','temporary_processes':'ABSENT','temporary_profile':'UNKNOWN','shared_resources':'UNCHANGED','evidence':[clean],'detail':'Profile removal unproven.'},'limitations':['synthetic verifier fixture'],'next_action':{'owner':'reviewer','action':'review','terminal':False}}
    p=tmp/'observation.json'; p.write_text(json.dumps(r),encoding='utf-8'); return r,root,p

def verify(tmp,r):
    _,root,p=fixture(tmp); p.write_text(json.dumps(r),encoding='utf-8'); return mod().verify_observation_file(p,root,SCHEMA)
def codes(x): return {e['code'] for e in x['errors']}

def test_contract_adds_verifier_surface_revision_and_finding_identity():
    assert V.is_file(); s=json.loads(SCHEMA.read_text())
    assert 'revision' in s['required']
    assert {'surface_name','experience_role','architecture_ref','observed_surface_state'}<=set(s['properties']['target']['required'])
    assert 'finding_id' in s['properties']['findings']['items']['required']

def test_published_record_names_actual_surface_and_original_revision():
    r=json.loads(OBS.read_text()); assert r['target']['surface_name']=='current Control Room inspector'
    assert r['target']['experience_role']=='ADVANCED' and r['target']['observed_surface_state']=='PARTIAL'
    assert r['revision']['state']=='ORIGINAL' and 'Chairman Today decision surface' not in json.dumps(r)

def test_valid_fixture_returns_closed_receipt_without_writes(tmp_path):
    _,root,p=fixture(tmp_path); before={x:x.read_bytes() for x in [p,*[q for q in root.rglob('*') if q.is_file()]]}
    x=mod().verify_observation_file(p,root,SCHEMA)
    assert x['verdict']=='VALID' and x['errors']==[] and x['artifact_count']==7
    assert set(x)=={'schema','verdict','observation_id','observation_sha256','artifact_count','checks','errors'}
    assert before=={q:q.read_bytes() for q in before}

def test_duplicate_json_key_is_rejected(tmp_path):
    p=tmp_path/'d.json'; p.write_text('{"schema":"a","schema":"b"}')
    assert 'JSON_DUPLICATE_KEY' in codes(mod().verify_observation_file(p,tmp_path,SCHEMA))

@pytest.mark.parametrize('case,code',[('bad_date','TIMESTAMP_INVALID'),('order','TIME_ORDER_INVALID'),('match','SOURCE_RELATION_INVALID'),('different','SOURCE_RELATION_INVALID'),('size','ARTIFACT_SIZE_MISMATCH'),('digest','ARTIFACT_DIGEST_MISMATCH'),('dimension','PNG_DIMENSION_MISMATCH'),('identity','ARTIFACT_IDENTITY_CONFLICT'),('finding','EVIDENCE_REF_UNDECLARED'),('secret','SECRET_SHAPED_VALUE'),('proven','CAPABILITY_CONSISTENCY_INVALID'),('correction','CORRECTION_INVALID'),('cleanup','CLEANUP_CLAIM_INVALID')])
def test_cross_field_mutants_fail_for_intended_reason(tmp_path,case,code):
    r,_,_=fixture(tmp_path)
    if case=='bad_date': r['recorded_at']='2026-02-30T10:00:00Z'
    elif case=='order': r['capture']['completed_at']='2026-09-08T11:58:00Z'
    elif case=='match': r['source_relationship'].update(relation='MATCH',revision_comparison='EQUAL')
    elif case=='different': r['source_relationship'].update(observed_deployed_sha='a'*40)
    elif case=='size': r['capture']['screenshots'][0]['bytes']+=1
    elif case=='digest': r['capture']['semantic_evidence']['artifacts'][0]['sha256']='0'*64
    elif case=='dimension': r['capture']['screenshots'][0]['viewport']['width']=41
    elif case=='identity':
        x=deepcopy(r['capture']['screenshots'][0]); x['sha256']='0'*64; r['capture']['screenshots'].append(x)
    elif case=='finding': r['findings'][0]['evidence_refs']=['private-evidence/undeclared.json']
    elif case=='secret': r['target']['locator']='ghp_abcdefghijklmnopqrstuvwxyz123456'
    elif case=='proven': r.update(capability_state='PROVEN_LIVE')
    elif case=='correction': r['revision'].update(state='CORRECTION',predecessor_observation_id=r['observation_id'],changed_input_refs=[r['capture']['semantic_evidence']['artifacts'][0]['artifact_ref']],affected_finding_ids=['FINDING-001'],reason='changed',revised_conclusion='changed')
    elif case=='cleanup': r['cleanup'].update(state='CLEAN',temporary_profile='REMOVED')
    assert code in codes(verify(tmp_path,r))

@pytest.mark.parametrize('case,code',[('missing','ARTIFACT_MISSING'),('not_png','PNG_INVALID'),('proof','CONSUMPTION_BINDING_INVALID'),('consumer','CONSUMPTION_BINDING_INVALID'),('escape','ARTIFACT_REF_INVALID')])
def test_artifact_and_consumption_mutants_fail(tmp_path,case,code):
    r,root,p=fixture(tmp_path); m=mod()
    if case=='missing': (root/'private-evidence/state.json').unlink()
    elif case=='not_png':
        q=root/'private-evidence/desktop.png'; q.write_bytes(b'bad'); r['capture']['screenshots'][0].update(bytes=3,sha256=sha(b'bad'))
    elif case in {'proof','consumer'}:
        q=root/'private-evidence/consumption.json'; x=json.loads(q.read_text())
        if case=='proof': x['consumed_artifacts'][0]['sha256']='0'*64
        else: x['consumer_ref']='other'
        q.write_text(json.dumps(x)); h=sha(q.read_bytes())
        for s in r['capture']['screenshots']: s['consumption']['proof_sha256']=h
    else: r['capture']['screenshots'][0]['artifact_ref']='../escape.png'
    p.write_text(json.dumps(r)); assert code in codes(m.verify_observation_file(p,root,SCHEMA))

@pytest.mark.parametrize('name,bad',[('wrong_target','CONTRACT_REFUSAL'),('stale_capture','CONTRACT_REFUSAL'),('different_build','HTTP_404'),('different_viewport_or_data_state','SOURCE_SHA_DISTINCT'),('missing_screenshot_bytes','OWNER_EVIDENCE'),('broken_browser_connection','HTTP_404'),('excluded_account_surface','OWNER_EVIDENCE')])
def test_each_negative_control_is_discriminating(tmp_path,name,bad):
    r,_,_=fixture(tmp_path)
    if bad in {'CONTRACT_REFUSAL','OWNER_EVIDENCE'}: r['negative_controls'][name]['method']=bad
    else: r['negative_controls'][name]['signal']=bad
    assert 'NEGATIVE_CONTROL_INVALID' in codes(verify(tmp_path,r))
