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

def witnessed_fixture_payloads():
    """Synthetic owner facts for each deliberate negative case."""
    names = ("wrong_target", "stale_capture", "different_build",
             "missing_screenshot_bytes", "broken_browser_connection",
             "excluded_account_surface")
    facts = {
        name: {
            "control": name, "case_ref": "fixture/" + name,
            "operation_ref": "reality-test",
            "carrier_ref": "web-sol/current-chairman-directed-session",
            "observed_at": "2026-09-08T11:59:05Z",
            "target_ref": "owner-qualified-loopback",
        }
        for name in names
    }
    facts["wrong_target"].update(target_ref="fixture/wrong-target", http_status=404)
    facts["stale_capture"].update(
        input_ref="private-evidence/stale-input.png", input_sha256=sha(b"synthetic stale input"),
        input_captured_at="2026-09-07T11:00:00Z",
        required_not_before="2026-09-08T11:59:00Z", stale_disclosed=True,
    )
    facts["different_build"].update(
        target_ref="fixture/different-build", protected_sha="a"*40, observed_deployed_sha="b"*40,
    )
    facts["missing_screenshot_bytes"].update(
        attempted_artifact_ref="private-evidence/not-delivered.png",
        screenshot_bytes_present=False, refusal_code="SCREENSHOT_BYTES_REQUIRED",
    )
    facts["broken_browser_connection"].update(
        provider_ref="fixture/browser", connection_state="DISCONNECTED",
    )
    facts["excluded_account_surface"].update(
        target_ref="fixture/excluded-proposal", surface_class="MANAGED_CHAIRMAN_ACCOUNT",
        access_attempted=False, refusal_code="TARGET_CLASS_EXCLUDED",
    )
    runtime = {"runtime": "degraded", "negative_controls": {
        name: facts[name] for name in ("stale_capture", "different_build", "broken_browser_connection")
    }}
    effect = {
        "state": "NOT_APPLIED", "operation_ref": "reality-test",
        "carrier_ref": "web-sol/current-chairman-directed-session",
        "negative_controls": {
            name: facts[name] for name in ("wrong_target", "missing_screenshot_bytes", "excluded_account_surface")
        },
    }
    return tuple((json.dumps(value, sort_keys=True) + "\n").encode() for value in (runtime, effect))

def fixture(tmp):
    root=tmp/'owner'; dbytes,mbytes=png(40,30),png(20,35)
    d=put(root,'private-evidence/desktop.png',dbytes); m=put(root,'private-evidence/mobile.png',mbytes)
    sem=put(root,'private-evidence/semantic.json',b'{"surface":"advanced"}\n')
    runtime_bytes, effect_bytes = witnessed_fixture_payloads()
    run=put(root,'private-evidence/state.json',runtime_bytes)
    eff=put(root,'private-evidence/effect.json',effect_bytes)
    clean=put(root,'private-evidence/cleanup.json',b'{"temporary_profile":"UNKNOWN"}\n')
    consumer='web-sol/current-chairman-directed-session'
    proof_body=json.dumps({'consumer_ref':consumer,'consumed_artifacts':[{'artifact_ref':d['artifact_ref'],'sha256':d['sha256']},{'artifact_ref':m['artifact_ref'],'sha256':m['sha256']}]},sort_keys=True).encode()
    proof=put(root,'private-evidence/consumption.json',proof_body)
    shots=[]
    for x,w,h,n in ((d,40,30,len(dbytes)),(m,20,35,len(mbytes))):
        shots.append({'artifact_ref':x['artifact_ref'],'sha256':x['sha256'],'mime_type':'image/png','bytes':n,'bytes_present':True,'viewport':{'width':w,'height':h},'data_state':'DEGRADED','consumption':{'state':'CONSUMED','consumer_ref':consumer,'method':'MODEL_VISIBLE_IMAGE_DELIVERY','proof_ref':proof['artifact_ref'],'proof_sha256':proof['sha256'],'consumed_at':None,'limitation':'Provider exposed no native consumption time.'}})
    r={'schema':'mastermind.reality_observation.v1','observation_id':'REALITY-TEST-001','capability_state':'PARTIAL','recorded_at':'2026-09-08T12:00:00Z','revision':{'state':'ORIGINAL','predecessor_observation_id':None,'changed_input_refs':[],'affected_finding_ids':[],'reason':None,'revised_conclusion':None},'persona':{'name':'Chairman','user_job':'Inspect one decision surface','non_goals':['account actuation']},'target':{'product':'Chairman Control Room','environment':'approved fixture','locator':'owner-qualified-loopback','authorization_ref':'current-live-assignment','surface_class':'APPROVED_PRODUCT','surface_name':'current Control Room inspector','experience_role':'ADVANCED','architecture_ref':'Mastermind:decision-first@e18cab4f3ca41725fdb517623543fa4fb1aba467','observed_surface_state':'PARTIAL'},'source_relationship':{'protected_sha':'a'*40,'observed_deployed_sha':'b'*40,'relation':'DIFFERENT','observed_at':'2026-09-08T11:59:00Z','revision_comparison':'DISTINCT'},'journey':{'steps':[{'action':'inspect','result':'degraded state visible'}],'outcome':'PARTIAL'},'capture':{'started_at':'2026-09-08T11:59:00Z','completed_at':'2026-09-08T11:59:10Z','screenshots':shots,'semantic_evidence':{'state':'AVAILABLE','artifacts':[{**sem,'consumed':True}],'reason':None},'runtime_evidence':{'state':'AVAILABLE','artifacts':[{**run,'consumed':True}],'reason':None}},'findings':[{'finding_id':'FINDING-001','basis':'MODEL_INFERENCE','claim':'Diagnostics compete with outcome.','evidence_refs':[d['artifact_ref'],sem['artifact_ref']],'unknowns':['No causal study.']}],'negative_controls':{'wrong_target':control('DETECTED','OWNER_EVIDENCE','HTTP_404',[eff['artifact_ref']]),'stale_capture':control('DETECTED','OWNER_EVIDENCE','STALE_INPUT_DISCLOSED',[run['artifact_ref']]),'different_build':control('DETECTED','OWNER_EVIDENCE','SOURCE_SHA_DISTINCT',[run['artifact_ref']]),'different_viewport_or_data_state':control('DETECTED','OWNER_EVIDENCE','VIEWPORT_OR_DATA_STATE_DISTINCT',[d['artifact_ref'],m['artifact_ref']]),'missing_screenshot_bytes':control('REFUSED','CONTRACT_REFUSAL','SCREENSHOT_BYTES_REQUIRED',[eff['artifact_ref']]),'broken_browser_connection':control('DETECTED','OWNER_EVIDENCE','PROVIDER_DISCONNECTED',[run['artifact_ref']]),'excluded_account_surface':control('REFUSED','CONTRACT_REFUSAL','TARGET_CLASS_EXCLUDED',[eff['artifact_ref']])},'effect':{'state':'NOT_APPLIED','operation_ref':'reality-test','carrier_ref':consumer,'evidence':[eff],'detail':'Read-only.'},'cleanup':{'state':'INCOMPLETE','temporary_processes':'ABSENT','temporary_profile':'UNKNOWN','shared_resources':'UNCHANGED','evidence':[clean],'detail':'Profile removal unproven.'},'limitations':['synthetic verifier fixture'],'next_action':{'owner':'reviewer','action':'review','terminal':False}}
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


# ---------------------------------------------------------------------------
# Refinement 5649522220 additions.
#
# Every fixture below is generated in a temporary directory. The bytes are
# synthetic; a passing synthetic case proves the verifier discriminates the
# invariant, not that a real product journey ever happened.
# ---------------------------------------------------------------------------

CONTROL_NAMES = (
    'wrong_target',
    'stale_capture',
    'different_build',
    'different_viewport_or_data_state',
    'missing_screenshot_bytes',
    'broken_browser_connection',
    'excluded_account_surface',
)


def verify_record(root, r):
    p = root.parent / 'observation.json'
    p.write_text(json.dumps(r), encoding='utf-8')
    return mod().verify_observation_file(p, root, SCHEMA)


def success_record(tmp_path):
    """A synthetic, fully evidenced approved-product success case."""
    r, root, _ = fixture(tmp_path)
    r['capability_state'] = 'PROVEN_LIVE'
    r['journey']['outcome'] = 'SUCCESS'
    r['target']['observed_surface_state'] = 'LIVE'
    return r, root


def correction_record(tmp_path):
    """A genuine correction: changed evidence, a revised finding, bound predecessor."""
    r, root, _ = fixture(tmp_path)
    predecessor = deepcopy(r)
    predecessor['observation_id'] = 'REALITY-TEST-000'
    sem_ref = 'private-evidence/semantic.json'
    amended = b'{"surface":"advanced","amended":true}\n'
    (root / sem_ref).write_bytes(amended)
    r['capture']['semantic_evidence']['artifacts'][0]['sha256'] = sha(amended)
    r['findings'][0]['claim'] = (
        'Diagnostics compete with the outcome; the amended snapshot narrows the claim.'
    )
    r['observation_id'] = 'REALITY-TEST-001-CORRECTION'
    predecessor_bytes = json.dumps(predecessor, sort_keys=True).encode()
    (root / 'private-evidence/predecessor-observation.json').write_bytes(predecessor_bytes)
    r['revision'] = {
        'state': 'CORRECTION',
        'predecessor_observation_id': 'REALITY-TEST-000',
        'changed_input_refs': [sem_ref],
        'affected_finding_ids': ['FINDING-001'],
        'reason': 'The semantic snapshot was re-read and the earlier claim was too broad.',
        'revised_conclusion': 'The finding is narrowed; the journey outcome is unchanged.',
        'predecessor_record_ref': 'private-evidence/predecessor-observation.json',
        'predecessor_record_sha256': sha(predecessor_bytes),
    }
    return r, root


def test_valid_correction_is_accepted_against_its_bound_predecessor(tmp_path):
    r, root = correction_record(tmp_path)
    x = verify_record(root, r)
    assert x['verdict'] == 'VALID' and x['errors'] == []
    assert x['artifact_count'] == 7


def test_synthetic_approved_success_case_is_valid(tmp_path):
    r, root = success_record(tmp_path)
    x = verify_record(root, r)
    assert x['verdict'] == 'VALID' and x['errors'] == []
    assert x['artifact_count'] == 7


def test_missing_effect_artifact_fails_independently(tmp_path):
    r, root, _ = fixture(tmp_path)
    (root / 'private-evidence/effect.json').unlink()
    assert 'ARTIFACT_MISSING' in codes(verify_record(root, r))


def test_missing_cleanup_artifact_fails_independently(tmp_path):
    r, root, _ = fixture(tmp_path)
    (root / 'private-evidence/cleanup.json').unlink()
    assert 'ARTIFACT_MISSING' in codes(verify_record(root, r))


@pytest.mark.parametrize(
    'mutate',
    [
        'unresolved_input',
        'unknown_finding',
        'empty_changed',
        'empty_affected',
        'timestamp_only',
        'digest_mismatch',
        'missing_predecessor',
        'epoch_upgrade',
        'effect_upgrade',
        'self_reference',
    ],
)
def test_correction_failures_are_refused_for_their_own_reason(tmp_path, mutate):
    r, root = correction_record(tmp_path)
    if mutate == 'unresolved_input':
        r['revision']['changed_input_refs'] = ['private-evidence/undeclared.json']
    elif mutate == 'unknown_finding':
        r['revision']['affected_finding_ids'] = ['FINDING-999']
    elif mutate == 'empty_changed':
        r['revision']['changed_input_refs'] = []
    elif mutate == 'empty_affected':
        r['revision']['affected_finding_ids'] = []
    elif mutate == 'timestamp_only':
        original = b'{"surface":"advanced"}\n'
        (root / 'private-evidence/semantic.json').write_bytes(original)
        r['capture']['semantic_evidence']['artifacts'][0]['sha256'] = sha(original)
        r['findings'][0]['claim'] = 'Diagnostics compete with outcome.'
    elif mutate == 'digest_mismatch':
        r['revision']['predecessor_record_sha256'] = '0' * 64
    elif mutate == 'missing_predecessor':
        (root / 'private-evidence/predecessor-observation.json').unlink()
    elif mutate == 'epoch_upgrade':
        r['capture']['started_at'] = '2026-09-08T11:58:00Z'
    elif mutate == 'effect_upgrade':
        r['effect']['state'] = 'APPLIED'
    elif mutate == 'self_reference':
        r['revision']['predecessor_observation_id'] = r['observation_id']
        r['revision']['predecessor_record_sha256'] = '1' * 64
    x = verify_record(root, r)
    assert 'CORRECTION_INVALID' in codes(x)
    assert x['verdict'] != 'VALID'


@pytest.mark.parametrize(
    'mutate', ['fixture_target', 'failure_journey', 'unknown_journey']
)
def test_proven_live_refuses_inconsistent_target_or_journey(tmp_path, mutate):
    r, root = success_record(tmp_path)
    if mutate == 'fixture_target':
        r['target']['surface_class'] = 'TEST_FIXTURE'
    elif mutate == 'failure_journey':
        r['journey']['outcome'] = 'FAILURE'
    else:
        r['journey']['outcome'] = 'UNKNOWN'
    assert 'CAPABILITY_CONSISTENCY_INVALID' in codes(verify_record(root, r))


@pytest.mark.parametrize('control_name', CONTROL_NAMES)
def test_proven_live_refuses_each_unexercised_control(tmp_path, control_name):
    r, root = success_record(tmp_path)
    r['negative_controls'][control_name]['status'] = 'NOT_EXERCISED'
    assert 'CAPABILITY_CONSISTENCY_INVALID' in codes(verify_record(root, r))


def test_control_evidence_must_resolve_to_a_declared_artifact(tmp_path):
    r, root, _ = fixture(tmp_path)
    r['negative_controls']['wrong_target']['evidence_refs'] = [
        'private-evidence/undeclared.json'
    ]
    assert 'NEGATIVE_CONTROL_INVALID' in codes(verify_record(root, r))


def test_control_evidence_must_exist_on_disk(tmp_path):
    r, root, _ = fixture(tmp_path)
    r['negative_controls']['stale_capture']['evidence_refs'] = [
        'private-evidence/state.json'
    ]
    (root / 'private-evidence/state.json').unlink()
    assert 'ARTIFACT_MISSING' in codes(verify_record(root, r))


def test_secret_shape_in_a_non_locator_text_field_is_refused(tmp_path):
    r, root, _ = fixture(tmp_path)
    r['findings'][0]['claim'] = 'Diagnostics compete; credential ghp_' + 'a' * 36
    assert 'SECRET_SHAPED_VALUE' in codes(verify_record(root, r))


def test_unresolved_historical_identity_is_never_valid(tmp_path):
    root = tmp_path / 'owner'
    root.mkdir()
    x = mod().verify_observation_file(OBS, root, SCHEMA)
    assert 'ARTIFACT_IDENTITY_UNRESOLVED' in codes(x)
    assert x['verdict'] != 'VALID'


def test_published_record_declares_nine_unique_historical_files(tmp_path):
    root = tmp_path / 'owner'
    root.mkdir()
    x = mod().verify_observation_file(OBS, root, SCHEMA)
    assert x['artifact_count'] == 9


def test_symlink_escape_from_the_evidence_root_is_refused(tmp_path):
    r, root, _ = fixture(tmp_path)
    outside = tmp_path / 'outside'
    outside.mkdir()
    target = outside / 'desktop.png'
    target.write_bytes((root / 'private-evidence/desktop.png').read_bytes())
    link = root / 'private-evidence/linked.png'
    link.symlink_to(target)
    extra = deepcopy(r['capture']['screenshots'][0])
    extra['artifact_ref'] = 'private-evidence/linked.png'
    r['capture']['screenshots'].append(extra)
    assert 'ARTIFACT_REF_INVALID' in codes(verify_record(root, r))


def test_url_shaped_artifact_reference_is_refused(tmp_path):
    r, root, _ = fixture(tmp_path)
    r['capture']['screenshots'][0]['artifact_ref'] = (
        'https://example.invalid/image.png?token=secret'
    )
    assert 'ARTIFACT_REF_INVALID' in codes(verify_record(root, r))


# Boundaries repaired after the original source review. All witnesses below are
# synthetic fixture bytes, never recaptured historical or live account evidence.
def replace_artifact(root, record, ref, data):
    (root / ref).write_bytes(data)
    def update(node):
        if isinstance(node, dict):
            if node.get('artifact_ref') == ref:
                node['sha256'] = sha(data)
                if 'bytes' in node:
                    node['bytes'] = len(data)
            if node.get('proof_ref') == ref:
                node['proof_sha256'] = sha(data)
            for value in node.values():
                update(value)
        elif isinstance(node, list):
            for value in node:
                update(value)
    update(record)


def replace_payload(root, record, ref, payload):
    replace_artifact(root, record, ref, (json.dumps(payload, sort_keys=True) + '\n').encode())


def replace_screenshot(root, record, data, width, height, index=0):
    screenshot = record['capture']['screenshots'][index]
    ref = screenshot['artifact_ref']
    replace_artifact(root, record, ref, data)
    screenshot['viewport'] = {'width': width, 'height': height}
    proof_ref = screenshot['consumption']['proof_ref']
    proof = json.loads((root / proof_ref).read_text())
    for consumed in proof['consumed_artifacts']:
        if consumed['artifact_ref'] == ref:
            consumed['sha256'] = sha(data)
    replace_payload(root, record, proof_ref, proof)


def invoke_module(module, root, record, schema=SCHEMA):
    p = root.parent / 'observation.json'
    p.write_text(json.dumps(record), encoding='utf-8')
    return module.verify_observation_file(p, root, schema)


def assert_closed_invalid(result):
    assert result['verdict'] == 'INVALID' and result['errors']
    assert set(result) == {'schema','verdict','observation_id','observation_sha256','artifact_count','checks','errors'}
    assert all(error['code'] in mod().ERROR_CODES for error in result['errors'])


@pytest.mark.parametrize('case', [
    'capture', 'screenshots', 'screenshot', 'viewport', 'consumption',
    'semantic', 'artifact', 'effect', 'cleanup', 'finding', 'finding_id',
    'control', 'control_refs', 'revision_refs',
])
def test_healed_unsafe_nested_records_return_closed_errors(tmp_path, case):
    r, root, _ = fixture(tmp_path)
    if case == 'capture': r['capture'] = []
    elif case == 'screenshots': r['capture']['screenshots'] = {}
    elif case == 'screenshot': r['capture']['screenshots'][0] = None
    elif case == 'viewport': r['capture']['screenshots'][0]['viewport'] = 'bad'
    elif case == 'consumption': r['capture']['screenshots'][0]['consumption'] = []
    elif case == 'semantic': r['capture']['semantic_evidence'] = 1
    elif case == 'artifact': r['capture']['runtime_evidence']['artifacts'] = ['bad']
    elif case == 'effect': r['effect']['evidence'] = [False]
    elif case == 'cleanup': r['cleanup'] = 1
    elif case == 'finding': r['findings'] = [[]]
    elif case == 'finding_id': r['findings'][0]['finding_id'] = {}
    elif case == 'control': r['negative_controls']['wrong_target'] = []
    elif case == 'control_refs': r['negative_controls']['wrong_target']['evidence_refs'] = [{}]
    else: r['revision']['changed_input_refs'] = [{}]
    assert_closed_invalid(verify_record(root, r))


@pytest.mark.parametrize('family', ['semantic_evidence', 'runtime_evidence'])
@pytest.mark.parametrize('state', ['AVAILABLE', 'PARTIAL', 'UNAVAILABLE'])
def test_healed_all_evidence_family_refusals_are_total(tmp_path, family, state):
    r, root, _ = fixture(tmp_path)
    block = r['capture'][family]
    block['state'] = state
    if state == 'AVAILABLE': block['reason'] = 'contradicts availability'
    elif state == 'PARTIAL': block['reason'] = None
    else: block['reason'] = 'artifacts still present'
    result = verify_record(root, r)
    assert 'EVIDENCE_STATE_INVALID' in codes(result)
    assert_closed_invalid(result)


@pytest.mark.parametrize('kind', ['observation', 'schema', 'artifact', 'aggregate'])
def test_healed_read_budgets_fail_without_a_prefix_digest(tmp_path, monkeypatch, kind):
    r, root, p = fixture(tmp_path); module = mod()
    if kind == 'observation': monkeypatch.setattr(module, 'MAX_OBSERVATION_BYTES', 64)
    elif kind == 'schema': monkeypatch.setattr(module, 'MAX_SCHEMA_BYTES', 64)
    elif kind == 'artifact': monkeypatch.setattr(module, 'MAX_ARTIFACT_BYTES', 16)
    else: monkeypatch.setattr(module, 'MAX_TOTAL_ARTIFACT_BYTES', 16)
    result = module.verify_observation_file(p, root, SCHEMA)
    assert_closed_invalid(result)
    if kind == 'observation':
        assert result['observation_sha256'] is None
    elif kind == 'schema':
        assert {x['name']:x['status'] for x in result['checks']}['SCHEMA_CLOSED_SHAPE'] == 'FAIL'
    else:
        assert 'ARTIFACT_SIZE_MISMATCH' in codes(result)


def test_healed_missing_schema_cannot_report_schema_pass(tmp_path):
    _, root, p = fixture(tmp_path)
    result = mod().verify_observation_file(p, root, tmp_path/'missing-schema.json')
    assert_closed_invalid(result)
    assert {x['name']:x['status'] for x in result['checks']}['SCHEMA_CLOSED_SHAPE'] == 'FAIL'


def test_healed_deep_json_returns_a_bounded_receipt(tmp_path):
    p=tmp_path/'deep.json'; p.write_text('['*1500+'0'+']'*1500)
    result=mod().verify_observation_file(p,tmp_path,SCHEMA)
    assert 'JSON_INVALID' in codes(result)
    assert_closed_invalid(result)
    assert len(json.dumps(result)) < 10000


@pytest.mark.parametrize('kind', ['artifact', 'observation'])
def test_healed_nonregular_inputs_are_refused_without_blocking(tmp_path, kind):
    import os
    _, root, p=fixture(tmp_path)
    target=p if kind=='observation' else root/'private-evidence/state.json'
    target.unlink(); os.mkfifo(target)
    result=mod().verify_observation_file(p,root,SCHEMA)
    assert ('OBSERVATION_UNREADABLE' if kind=='observation' else 'ARTIFACT_NOT_REGULAR_FILE') in codes(result)
    assert_closed_invalid(result)


def test_healed_in_root_symlink_is_not_followed(tmp_path):
    r, root, _=fixture(tmp_path)
    target=root/'private-evidence/state.json'
    saved=root/'private-evidence/saved-state.json'; target.rename(saved)
    target.symlink_to(saved.name)
    assert 'ARTIFACT_REF_INVALID' in codes(verify_record(root,r))


@pytest.mark.parametrize('unsafe', ['private-evidence\\state.json', 'private-evidence//state.json', 'private-evidence/./state.json'])
def test_healed_reference_grammar_precedes_file_lookup(tmp_path, unsafe):
    r, root, _=fixture(tmp_path)
    r['capture']['runtime_evidence']['artifacts'][0]['artifact_ref']=unsafe
    assert 'ARTIFACT_REF_INVALID' in codes(verify_record(root,r))


def test_healed_replaced_open_file_is_refused(tmp_path, monkeypatch):
    import os
    r, root, _=fixture(tmp_path); module=mod()
    target=root/'private-evidence/state.json'
    replacement=root/'private-evidence/replacement.json'
    replacement.write_bytes(target.read_bytes())
    expected=(target.stat().st_dev,target.stat().st_ino)
    real_read=os.read; swapped=[]
    def race(fd, length):
        info=os.fstat(fd)
        if (info.st_dev,info.st_ino)==expected and not swapped:
            os.replace(replacement,target); swapped.append(True)
        return real_read(fd,length)
    monkeypatch.setattr(module.os,'read',race)
    result=invoke_module(module,root,r)
    assert swapped == [True]
    assert 'ARTIFACT_REF_INVALID' in codes(result)


def test_healed_consumption_uses_the_already_qualified_bytes(tmp_path, monkeypatch):
    r, root, _=fixture(tmp_path); module=mod()
    original=module._consumption_problem
    proof=root/'private-evidence/consumption.json'
    before=proof.read_bytes(); replacements=[]
    def replace_after_qualification(record, resolved):
        changed=json.loads(before); changed['consumer_ref']='other-consumer'
        proof.write_text(json.dumps(changed)); replacements.append(True)
        return original(record,resolved)
    monkeypatch.setattr(module,'_consumption_problem',replace_after_qualification)
    result=invoke_module(module,root,r)
    assert replacements == [True] and proof.read_bytes() != before
    assert result['verdict']=='VALID' and result['errors']==[]


@pytest.mark.parametrize('key,reference', [
    ('$ref','https://example.invalid/never-fetch.json'),
    ('$ref','file:///must-not-read.json'), ('$ref','other-schema.json'),
    ('$dynamicRef','https://example.invalid/never-fetch.json#node'),
    ('$recursiveRef','https://example.invalid/never-fetch.json'),
])
def test_healed_schema_references_are_refused_before_retrieval(tmp_path, monkeypatch, key, reference):
    import socket, urllib.request
    r,root,_=fixture(tmp_path); attempts=[]
    def denied(*args,**kwargs):
        attempts.append(True); raise AssertionError('schema retrieval attempted')
    monkeypatch.setattr(socket.socket,'connect',denied)
    monkeypatch.setattr(socket,'create_connection',denied)
    monkeypatch.setattr(urllib.request,'urlopen',denied)
    schema=json.loads(SCHEMA.read_text())
    schema['properties']['schema'][key]=reference
    supplied=tmp_path/'reference-schema.json'; supplied.write_text(json.dumps(schema))
    result=invoke_module(mod(),root,r,supplied)
    assert attempts == []
    assert 'SCHEMA_INVALID' in codes(result)
    assert_closed_invalid(result)


def test_healed_schema_id_is_an_identifier_without_retrieval(tmp_path):
    r,root,_=fixture(tmp_path); schema=json.loads(SCHEMA.read_text())
    schema['$id']='https://example.invalid/identifier-only'
    supplied=tmp_path/'identified-schema.json'; supplied.write_text(json.dumps(schema))
    result=invoke_module(mod(),root,r,supplied)
    assert result['verdict']=='VALID' and result['errors']==[]


@pytest.mark.parametrize('site', ['observation_id','unknown_key','artifact_ref','journey_state'])
def test_healed_secret_shaped_values_never_escape_in_receipts(tmp_path,site):
    r,root,_=fixture(tmp_path)
    secret=('AKIA'+'A'*16) if site=='observation_id' else ('ghp_'+'a'*36)
    if site=='observation_id': r['observation_id']=secret
    elif site=='unknown_key': r[secret]='untrusted field'
    elif site=='artifact_ref': r['capture']['screenshots'][0]['artifact_ref']=secret
    else:
        r['capability_state']='PROVEN_LIVE'; r['journey']['outcome']=secret
    result=verify_record(root,r)
    assert 'SECRET_SHAPED_VALUE' in codes(result)
    assert secret not in json.dumps(result)
    if site=='observation_id': assert result['observation_id'] is None
    assert all(len(error['detail'])<=240 for error in result['errors'])


def png_stream(width, height, depth, color, raster, *, interlace=0, before=(), idats=None, after=(), end=b''):
    header=chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,depth,color,0,0,interlace))
    data=zlib.compress(raster)
    pieces=[data] if idats is None else idats(data)
    return b'\x89PNG\r\n\x1a\n'+header+b''.join(before)+b''.join(chunk(b'IDAT',piece) for piece in pieces)+b''.join(after)+chunk(b'IEND',end)


@pytest.mark.parametrize('case', [
    'rgba_depth','palette_missing','palette_index','palette_size','gray_palette',
    'filter','nonconsecutive','iend_payload','after_iend','unknown_critical',
    'adam7_missing','extra_raster','truncated_zlib','ihdr_not_first','duplicate_ihdr',
])
def test_healed_png_structural_mutants_fail_with_matching_digests(tmp_path,case):
    r,root,_=fixture(tmp_path); width=height=1
    raw=png_stream(1,1,8,6,b'\0'+b'\0'*4)
    if case=='rgba_depth': raw=png_stream(1,1,1,6,b'\0\0')
    elif case=='palette_missing': raw=png_stream(1,1,1,3,b'\0\0')
    elif case=='palette_index': raw=png_stream(1,1,1,3,b'\0\x80',before=[chunk(b'PLTE',b'\0'*3)])
    elif case=='palette_size': raw=png_stream(1,1,1,3,b'\0\0',before=[chunk(b'PLTE',b'\0'*9)])
    elif case=='gray_palette': raw=png_stream(1,1,8,0,b'\0\0',before=[chunk(b'PLTE',b'\0'*3)])
    elif case=='filter': raw=png_stream(1,1,8,6,b'\5'+b'\0'*4)
    elif case=='nonconsecutive':
        compressed=zlib.compress(b'\0'+b'\0'*4)
        raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',compressed[:3])+chunk(b'tEXt',b'k\0v')+chunk(b'IDAT',compressed[3:])+chunk(b'IEND',b'')
    elif case=='iend_payload': raw=png_stream(1,1,8,6,b'\0'+b'\0'*4,end=b'x')
    elif case=='after_iend': raw+=b'trailing-data'
    elif case=='unknown_critical': raw=png_stream(1,1,8,6,b'\0'+b'\0'*4,before=[chunk(b'ABCD',b'')])
    elif case=='adam7_missing': raw=png_stream(1,1,8,6,b'',interlace=1)
    elif case=='extra_raster': raw=png_stream(1,1,8,6,b'\0'+b'\0'*5)
    elif case=='truncated_zlib': raw=png_stream(1,1,8,6,b'\0'+b'\0'*4,idats=lambda x:[x[:-2]])
    elif case=='ihdr_not_first': raw=raw[:8]+chunk(b'tEXt',b'k\0v')+raw[8:]
    elif case=='duplicate_ihdr': raw=raw[:33]+raw[8:33]+raw[33:]
    replace_screenshot(root,r,raw,width,height)
    result=verify_record(root,r)
    assert 'ARTIFACT_DIGEST_MISMATCH' not in codes(result)
    assert 'ARTIFACT_SIZE_MISMATCH' not in codes(result)
    assert 'PNG_INVALID' in codes(result)


@pytest.mark.parametrize('case', ['sub','up','average','paeth','split_empty','idat_padding','packed_padding','indexed','adam7_empty_passes','ancillary'])
def test_healed_valid_png_variants_remain_valid(tmp_path,case):
    r,root,_=fixture(tmp_path); width=height=1
    if case in ('sub','up','average','paeth'):
        filter_type={'sub':1,'up':2,'average':3,'paeth':4}[case]
        raw=png_stream(1,1,8,6,bytes([filter_type])+b'\1\2\3\4')
    elif case=='split_empty': raw=png_stream(1,1,8,6,b'\0'+b'\0'*4,idats=lambda x:[b'',x[:2],b'',x[2:],b''])
    elif case=='idat_padding': raw=png_stream(1,1,8,6,b'\0'+b'\0'*4,idats=lambda x:[x+b'permitted padding'])
    elif case=='packed_padding': raw=png_stream(1,1,1,0,b'\0\x7f')
    elif case=='indexed': raw=png_stream(1,1,2,3,b'\0\x7f',before=[chunk(b'PLTE',b'\0'*6)])
    elif case=='adam7_empty_passes': raw=png_stream(1,1,8,6,b'\0'+b'\0'*4,interlace=1)
    else: raw=png_stream(1,1,8,6,b'\0'+b'\0'*4,before=[chunk(b'tEXt',b'author\0synthetic fixture')])
    replace_screenshot(root,r,raw,width,height)
    result=verify_record(root,r)
    assert result['verdict']=='VALID' and result['errors']==[]


def rewrite_predecessor(root, record, mutate):
    ref=record['revision']['predecessor_record_ref']
    predecessor=json.loads((root/ref).read_text()); mutate(predecessor)
    raw=json.dumps(predecessor,sort_keys=True).encode()
    (root/ref).write_bytes(raw); record['revision']['predecessor_record_sha256']=sha(raw)


@pytest.mark.parametrize('case',['malformed','invalid_time','identity_conflict','completed_epoch','effect_deletion','operation_change'])
def test_healed_corrections_preserve_closed_predecessor_and_effect_binding(tmp_path,case):
    r,root=correction_record(tmp_path)
    if case=='malformed': rewrite_predecessor(root,r,lambda x:x['capture'].update(screenshots=[None]))
    elif case=='invalid_time': rewrite_predecessor(root,r,lambda x:x['capture'].update(completed_at='2026-02-30T11:59:10Z'))
    elif case=='identity_conflict':
        def conflict(x):
            extra=deepcopy(x['capture']['screenshots'][0]);extra['sha256']='f'*64
            x['capture']['screenshots'].append(extra)
        rewrite_predecessor(root,r,conflict)
    elif case=='completed_epoch': r['capture']['completed_at']='2026-09-08T11:59:11Z'
    elif case=='effect_deletion':
        def extra_old(x):
            x['effect']['evidence'].append({'artifact_ref':'private-evidence/retired-effect.json','sha256':'d'*64,'coverage':'old owner witness'})
        rewrite_predecessor(root,r,extra_old); r['effect']['state']='APPLIED'
    else: r['effect']['operation_ref']='different-operation'
    assert 'CORRECTION_INVALID' in codes(verify_record(root,r))


def test_healed_correction_compares_capture_instants_not_spelling(tmp_path):
    r,root=correction_record(tmp_path)
    r['capture']['started_at']='2026-09-08T11:59:00.000000000Z'
    r['capture']['completed_at']='2026-09-08T11:59:10.0Z'
    result=verify_record(root,r)
    assert result['verdict']=='VALID' and result['artifact_count']==7


@pytest.mark.parametrize('named',[False,True])
def test_healed_effect_upgrade_needs_new_named_supporting_bytes(tmp_path,named):
    r,root=correction_record(tmp_path);ref='private-evidence/effect.json'
    payload=json.loads((root/ref).read_text());payload['state']='APPLIED'
    replace_payload(root,r,ref,payload);r['effect']['state']='APPLIED'
    if named: r['revision']['changed_input_refs'].append(ref)
    result=verify_record(root,r)
    if named:
        assert result['verdict']=='VALID' and result['artifact_count']==7
    else:
        assert 'CORRECTION_INVALID' in codes(result)


@pytest.mark.parametrize('field,value',[('state','APPLIED'),('operation_ref','other-operation'),('carrier_ref','other-carrier')])
def test_healed_ordinary_effect_receipts_must_match_record(tmp_path,field,value):
    r,root,_=fixture(tmp_path);ref='private-evidence/effect.json'
    payload=json.loads((root/ref).read_text());payload[field]=value
    replace_payload(root,r,ref,payload)
    assert 'EFFECT_INVALID' in codes(verify_record(root,r))


def positive_cleanup(root,record,profile='REMOVED'):
    identity='fixture/profile-1'
    record['cleanup'].update(state='CLEAN',temporary_profile=profile,temporary_profile_id=identity)
    payload={
        'temporary_profile_id':identity,'temporary_profile':profile,
        'temporary_processes':'ABSENT','shared_resources':'UNCHANGED',
        'operation_ref':record['effect']['operation_ref'],'carrier_ref':record['effect']['carrier_ref'],
        'pre_removal':{'temporary_profile_id':identity,'present':profile=='REMOVED','observed_at':'2026-09-08T11:59:10Z'},
    }
    if profile=='REMOVED':
        payload['post_removal']={'temporary_profile_id':identity,'present':False,'observed_at':'2026-09-08T11:59:11Z'}
    else:
        payload['creation']={'temporary_profile_id':identity,'created':False,'observed_at':'2026-09-08T11:59:11Z','owner_ref':'fixture/profile-owner'}
    replace_payload(root,record,'private-evidence/cleanup.json',payload)
    return payload


@pytest.mark.parametrize('profile',['REMOVED','NOT_CREATED'])
def test_healed_typed_profile_cleanup_has_a_valid_positive(tmp_path,profile):
    r,root,_=fixture(tmp_path);positive_cleanup(root,r,profile)
    result=verify_record(root,r)
    assert result['verdict']=='VALID' and result['artifact_count']==7


@pytest.mark.parametrize('case',['missing_expected','wrong_profile','empty_before','empty_after','string_boolean','time_reverse','process_contradiction','wrong_carrier','no_create_missing','no_create_owner'])
def test_healed_cleanup_labels_and_empty_objects_do_not_prove_removal(tmp_path,case):
    r,root,_=fixture(tmp_path)
    profile='NOT_CREATED' if case.startswith('no_create') else 'REMOVED'
    payload=positive_cleanup(root,r,profile)
    if case=='missing_expected': del r['cleanup']['temporary_profile_id']
    elif case=='wrong_profile': payload['temporary_profile_id']='fixture/other-profile'
    elif case=='empty_before': payload['pre_removal']={}
    elif case=='empty_after': payload['post_removal']={}
    elif case=='string_boolean': payload['post_removal']['present']='false'
    elif case=='time_reverse': payload['post_removal']['observed_at']='2026-09-08T11:59:09Z'
    elif case=='process_contradiction': payload['temporary_processes']='PRESENT'
    elif case=='wrong_carrier': payload['carrier_ref']='other-carrier'
    elif case=='no_create_missing': del payload['creation']
    else: del payload['creation']['owner_ref']
    replace_payload(root,r,'private-evidence/cleanup.json',payload)
    assert 'CLEANUP_CLAIM_INVALID' in codes(verify_record(root,r))


@pytest.mark.parametrize('name',CONTROL_NAMES)
def test_healed_control_labels_without_evidence_are_refused(tmp_path,name):
    r,root,_=fixture(tmp_path);r['negative_controls'][name]['evidence_refs']=[]
    assert 'NEGATIVE_CONTROL_INVALID' in codes(verify_record(root,r))


@pytest.mark.parametrize('name',CONTROL_NAMES)
def test_healed_control_fact_contradictions_are_refused(tmp_path,name):
    r,root,_=fixture(tmp_path)
    if name=='different_viewport_or_data_state':
        replace_screenshot(root,r,png(40,30),40,30,index=1)
    else:
        ref=r['negative_controls'][name]['evidence_refs'][0]
        payload=json.loads((root/ref).read_text());fact=payload['negative_controls'][name]
        if name=='wrong_target': fact['http_status']=200
        elif name=='stale_capture': fact['input_captured_at']='2026-09-08T11:59:05Z'
        elif name=='different_build': fact['observed_deployed_sha']=fact['protected_sha']
        elif name=='missing_screenshot_bytes': fact['screenshot_bytes_present']=True
        elif name=='broken_browser_connection': fact['connection_state']='CONNECTED'
        else: fact['access_attempted']=True
        replace_payload(root,r,ref,payload)
    assert 'NEGATIVE_CONTROL_INVALID' in codes(verify_record(root,r))


@pytest.mark.parametrize('field,value',[
    ('operation_ref','different-operation'),('carrier_ref','different-carrier'),
    ('observed_at','2026-09-08T11:59:11Z'),('protected_sha','c'*40),
    ('target_ref','owner-qualified-loopback'),
])
def test_healed_negative_build_case_keeps_original_bindings(tmp_path,field,value):
    r,root,_=fixture(tmp_path);ref='private-evidence/state.json'
    payload=json.loads((root/ref).read_text());payload['negative_controls']['different_build'][field]=value
    replace_payload(root,r,ref,payload)
    assert 'NEGATIVE_CONTROL_INVALID' in codes(verify_record(root,r))


def test_healed_primary_matching_build_can_pass_its_separate_negative_case(tmp_path):
    r,root=success_record(tmp_path)
    r['source_relationship'].update(relation='MATCH',revision_comparison='EQUAL',observed_deployed_sha='a'*40)
    result=verify_record(root,r)
    assert result['verdict']=='VALID' and result['errors']==[]


def test_healed_not_exercised_control_remains_honest_partial_data(tmp_path):
    r,root,_=fixture(tmp_path)
    r['negative_controls']['wrong_target'].update(status='NOT_EXERCISED',evidence_refs=[])
    result=verify_record(root,r)
    assert result['verdict']=='VALID' and result['errors']==[]


@pytest.mark.parametrize('invalid', [
    '2026-02-30T12:00:00Z',
    '2026-09-08T12:61:00Z',
    '2026-09-08T12:00:00Z\n',
])
def test_healed_consumption_timestamps_require_real_utc_calendar(tmp_path, invalid):
    r,root,_=fixture(tmp_path)
    r['capture']['screenshots'][0]['consumption'].update(consumed_at=invalid,limitation=None)
    result=verify_record(root,r)
    assert 'TIMESTAMP_INVALID' in codes(result)
    assert_closed_invalid(result)


@pytest.mark.parametrize('valid', [
    '2026-09-08T12:00:00Z', '2026-09-08T12:00:00.123456789Z',
])
def test_healed_valid_provider_consumption_time_remains_valid(tmp_path, valid):
    r,root,_=fixture(tmp_path)
    r['capture']['screenshots'][0]['consumption'].update(consumed_at=valid,limitation=None)
    result=verify_record(root,r)
    assert result['verdict']=='VALID' and result['errors']==[]


@pytest.mark.parametrize('site,code', [
    ('recorded_at','TIMESTAMP_INVALID'),
    ('negative_control','NEGATIVE_CONTROL_INVALID'),
    ('cleanup','CLEANUP_CLAIM_INVALID'),
])
@pytest.mark.parametrize('variant',['trailing_newline','non_ascii'])
def test_healed_utc_spelling_is_strict_for_record_and_witness(tmp_path,site,code,variant):
    r,root,_=fixture(tmp_path)
    instant='2026-09-08T11:59:05Z'
    malformed=instant+'\n' if variant=='trailing_newline' else instant.replace('2026','\uff12\uff10\uff12\uff16')
    if site=='recorded_at':
        r['recorded_at']=malformed
    elif site=='negative_control':
        ref='private-evidence/effect.json';payload=json.loads((root/ref).read_text())
        payload['negative_controls']['wrong_target']['observed_at']=malformed
        replace_payload(root,r,ref,payload)
    else:
        payload=positive_cleanup(root,r)
        payload['post_removal']['observed_at']=malformed.replace('11:59:05','11:59:11')
        replace_payload(root,r,'private-evidence/cleanup.json',payload)
    result=verify_record(root,r)
    assert code in codes(result)
    assert_closed_invalid(result)


def test_healed_renaming_old_effect_bytes_cannot_support_a_state_change(tmp_path):
    r,root=correction_record(tmp_path)
    rewrite_predecessor(root,r,lambda value:value['effect'].update(state='EFFECT_UNKNOWN'))
    old_ref='private-evidence/effect.json';new_ref='private-evidence/renamed-effect.json'
    original_bytes=(root/old_ref).read_bytes()
    (root/new_ref).write_bytes(original_bytes)
    r['effect']['evidence'][0]['artifact_ref']=new_ref
    for control_value in r['negative_controls'].values():
        control_value['evidence_refs']=[new_ref if ref==old_ref else ref for ref in control_value['evidence_refs']]
    r['revision']['changed_input_refs'].append(new_ref)
    result=verify_record(root,r)
    assert 'CORRECTION_INVALID' in codes(result)
    assert 'EFFECT_INVALID' not in codes(result)
    assert 'ARTIFACT_DIGEST_MISMATCH' not in codes(result)
    assert sha((root/new_ref).read_bytes())==sha(original_bytes)


def test_primary_source_sha_newline_cannot_fake_distinct_revision(tmp_path):
    r, root, _ = fixture(tmp_path)
    r['source_relationship']['observed_deployed_sha'] = r['source_relationship']['protected_sha'] + '\n'
    result = verify_record(root, r)
    assert_closed_invalid(result)
    assert codes(result) == {'SOURCE_RELATION_INVALID'}
    assert {'name': 'SOURCE_RELATION_CONSISTENCY', 'status': 'FAIL'} in result['checks']


@pytest.mark.parametrize('malformed_protected', [False, True])
def test_primary_unknown_source_requires_strict_protected_sha(tmp_path, malformed_protected):
    r, root, _ = fixture(tmp_path)
    r['source_relationship'].update(
        observed_deployed_sha=None, observed_at=None,
        relation='UNKNOWN', revision_comparison='UNOBSERVABLE',
    )
    r['negative_controls']['different_build'].update(status='NOT_EXERCISED', evidence_refs=[])
    if malformed_protected:
        r['source_relationship']['protected_sha'] += '\n'
    result = verify_record(root, r)
    if malformed_protected:
        assert_closed_invalid(result)
        assert codes(result) == {'SOURCE_RELATION_INVALID'}
        assert {'name': 'SOURCE_RELATION_CONSISTENCY', 'status': 'FAIL'} in result['checks']
    else:
        assert result['verdict'] == 'VALID' and result['errors'] == []
        assert {'name': 'SOURCE_RELATION_CONSISTENCY', 'status': 'PASS'} in result['checks']
