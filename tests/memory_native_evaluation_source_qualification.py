"""Real frozen Macro fixed dispatcher -> native evaluation owner source join.

Only disposable OS/install/key/grant/runtime/provider primitives are inert.
Neither issuer/admission writer/rereader nor FD/typed collector is substituted.
The source grant is explicitly retained BEFORE each authorized operation; this
transport never learns a request and grants it automatically. All flags false.
"""
import asyncio
import base64
import copy
import dataclasses
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import threading
from contextlib import contextmanager
import pytest
import httpx

from tests import test_memory_evaluation_owner as native
from tests import test_protected_memory_execution as original_fixture
from common import memory_evaluation_contract as c,memory_native_wire as w
from control_plane import protected_memory_evaluation_assignment as a,protected_memory_annotations as ann
from control_plane import protected_memory_evaluation_execution as execution,protected_memory_original as originals
from control_plane import executive_memory_issuer as root

REAL_UID=os.geteuid
FIXTURE=Path(__file__).parent/'fixtures'
TAR=FIXTURE/'memory-evaluation-macro-b2513ad2.tar'
assert hashlib.sha256(TAR.read_bytes()).hexdigest()=='ebd2ade135b34cefd184fb7081c31c9ebae1116e64a5cbdc1f2d0b07be97b317'
closure=FIXTURE/'memory-evaluation-macro-b2513ad2.closure.json'
assert hashlib.sha256(closure.read_bytes()).hexdigest()=='0000adda27baa7058d4c2831b1e432097061d3940a1e054c8658bae8b55a4245'
TEMP=tempfile.TemporaryDirectory(prefix='memory-paired-public-source-')
MACRO=Path(TEMP.name)
with tarfile.open(TAR) as archive:
    members=archive.getmembers()
    assert all((m.isfile() or m.isdir()) and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members)
    archive.extractall(MACRO,filter='data')
for name,row in json.loads(closure.read_bytes())['public_source_and_fixture_paths'].items():
    body=(MACRO/name).read_bytes();assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
sys.path.insert(0,str(MACRO))
# Same accepted source-qualification import seam as the V3 owner: replace only
# the hermetic engine package shell with this hash-verified real initializer,
# retaining Mastermind's unrelated canon fixture. This file is explicit-only,
# never default CI collection or a product import path.
canon=sys.modules.get('engine.canon')
engine_spec=importlib.util.spec_from_file_location('engine',MACRO/'engine/__init__.py',submodule_search_locations=[str(MACRO/'engine')])
engine=importlib.util.module_from_spec(engine_spec);sys.modules['engine']=engine;engine_spec.loader.exec_module(engine)
if canon is not None:engine.canon=canon

def load(leaf):
    name='tests.'+leaf
    assert name not in sys.modules
    spec=importlib.util.spec_from_file_location(name,MACRO/'tests'/(leaf+'.py'))
    value=importlib.util.module_from_spec(spec);sys.modules[name]=value;spec.loader.exec_module(value);return value

peer_fixture=load('market_memory_native_peer_fixtures')
load('market_memory_e0_fixtures')
control_fixture=load('test_market_memory_e0_control_records')
case_fixture=load('test_market_memory_e0_native_case')
macro_fixture=load('test_market_memory_e0_evaluation_source')
native_peer_primitives=peer_fixture.native_peer_primitives
native_peer_capability=peer_fixture.native_peer_capability
rsa_key=native.rsa_key
economy=native.economy
installed=native.installed
joined=native.joined

def replace_study(value):
    if type(value) is dict:return {k:replace_study(v) for k,v in value.items()}
    if type(value) is list:return [replace_study(v) for v in value]
    return 'study' if value=='synthetic-study' else value

@pytest.fixture
def records():
    return replace_study(control_fixture.records.__wrapped__())

@pytest.fixture
def native_world(tmp_path,monkeypatch,records,native_peer_capability):
    # Synthetic intent DATA, not changed source, runtime ancestry or a grant.
    for k,v in dict(study_id='study',root_id='native-root',operator_run_id='native-parent',child_run_id='native-child').items():monkeypatch.setitem(case_fixture.INTENT,k,v)
    for module in (macro_fixture.legacy,macro_fixture.evaluation):
        monkeypatch.setattr(module,'_platform',lambda:'linux');monkeypatch.setattr(module,'_uid',lambda:0)
    with case_fixture.isolated_install(tmp_path,monkeypatch) as installed_root:
        monkeypatch.setattr(macro_fixture.legacy,'ROOT',installed_root)
        generator=case_fixture._native_world(tmp_path,monkeypatch,records,native_peer_capability,installed_root)
        world=next(generator)
        request=dict(schema=macro_fixture.legacy.REQUEST,action='prepare_case',operation_id='original-operation',intent=copy.deepcopy(case_fixture.INTENT))
        answer=json.loads(macro_fixture.legacy.exchange(macro_fixture.canonical(request)))
        assert answer['status']=='CASE_PREPARED'
        world['actual_native_packet']=base64.b64decode(answer['input']['body'],validate=True)
        yield world
        with pytest.raises(StopIteration):next(generator)

@pytest.fixture
def macro_evaluation_world(monkeypatch,request,tmp_path):
    return macro_fixture.evaluation_world.__wrapped__(monkeypatch,request,tmp_path)

@pytest.fixture
def configured(tmp_path,monkeypatch,macro_evaluation_world):
    monkeypatch.setattr(original_fixture,'packet',lambda:macro_evaluation_world['actual_native_packet'])
    return native.configured.__wrapped__(tmp_path,monkeypatch)

@pytest.fixture
def paired(native_peer_primitives,macro_evaluation_world,joined,economy,rsa_key,tmp_path,monkeypatch,request):
    e=native.evaluation.__wrapped__(joined,economy,rsa_key,tmp_path,monkeypatch,request)
    world=macro_evaluation_world;module=macro_fixture.evaluation
    # Model fixture owns only its actual fixed argv. Source verification runs
    # real Git against the isolated immutable source-object fixture.
    import subprocess
    model_popen=subprocess.Popen
    def owned_process(argv,**kwargs):
        if argv and Path(argv[0]).name=='git':return native.REAL_POPEN(argv,**kwargs)
        return model_popen(argv,**kwargs)
    monkeypatch.setattr(subprocess,'Popen',owned_process)
    # Explicit inert assessor/installation/source-purpose records, retained by
    # the real existing source owner. No callback can declare these current.
    purpose=copy.deepcopy(world['purpose']);binding=purpose['delegation_binding']
    binding.update(root_job_id=e.grant['root_job_id'],principal_binding_digest=e.grant['principal_binding_digest'])
    slots=[]
    for i,role in enumerate(c.ROLES):
        mapping=copy.deepcopy(e.maps[role]);raw=w.canonical(mapping)
        ref=macro_fixture.reference(raw,mapping['schema'],'paired-canonical-mapping-'+role)
        macro_fixture.write(world['directory']/(ref['sha256']+'.json'),raw)
        slots.append(dict(role=role,identity_mapping_ref=ref,execution_profile_id='model-'+str(i)))
    purpose['slots']=slots
    purpose_ref=macro_fixture.retain(world['directory'],purpose)
    scope=copy.deepcopy(world['scope']);scope.update(purpose_ref=purpose_ref,commitments=[])
    # Complete the explicit synthetic genesis installation BEFORE the first
    # evaluation request/admission. Subsequent grants below advance the real
    # immutable history and retain this one fixed purpose reference.
    assert world['records']['access']['sequence']==0
    world['records']['access']['scope_ref']=macro_fixture.retain(world['directory'],scope)
    macro_fixture.select(world);world['scope']=scope
    world.update(purpose=purpose,purpose_ref=purpose_ref,delegation={**binding,'source_purpose_ref':purpose_ref})
    e.grant.clear();e.grant.update(copy.deepcopy(world['delegation']))
    e.coo_path.write_text(json.dumps(e.coo))
    from ops.executive_os.coo_principal_host import CooInstalledSource
    e.provider.source=CooInstalledSource.from_path(e.coo_path,e.config['memory_evaluation']['coo_source'],expected_uid=450)
    e.app.settings=dataclasses.replace(e.app.settings,authority_provider=lambda principal,work:e.provider.source.snapshot(work)[2])
    fingerprint=e.grant['source_audience']['service_key_fingerprint']
    config=json.loads(e.state['raw']);config['memory_native_issuer']['service_key_fingerprint']=fingerprint
    e.state['raw']=w.canonical(config);e.state['owner']['configuration_sha256']=hashlib.sha256(e.state['raw']).hexdigest()
    monkeypatch.setattr(root,'_enrollment',lambda _:(e.state['raw'],fingerprint,b'known',(1,2,3)))
    previous=root._exchange;frames=[]
    def transport(raw):
        req=w._unframe(raw,262144)
        if req.get('schema')!=c.REQUEST:return previous(raw)
        e.source_actions.append(req['action']);output=io.BytesIO()
        try:
            # Native Linux metadata/peer primitives remain explicit; temporary
            # source files retain their REAL Mac UID and exact mode/inode law.
            with monkeypatch.context() as filesystem:
                filesystem.setattr(os,'geteuid',REAL_UID)
                macro_fixture.dispatch.serve(io.BytesIO(raw),output)
        except SystemExit:raise root.IssuerExchangeUnknown() from None
        reply=output.getvalue();frames.append(dict(request=copy.deepcopy(req),response=w._unframe(reply,262144),request_sha256=hashlib.sha256(raw).hexdigest(),response_sha256=hashlib.sha256(reply).hexdigest()))
        return reply
    monkeypatch.setattr(root,'_exchange',transport)
    query=dict(schema=c.REQUEST,action='read_evaluation_basis',delegation=e.grant,subject=None,assignment=None,input_sha256=None,pair_sha256=None)
    basis=w._unframe(transport(len(w.canonical(query)).to_bytes(4,'big')+w.canonical(query)),262144)['basis']
    old_slots=e.basis['slots'];old_slots[:]=basis['slots'];basis['slots']=old_slots;e.basis.clear();e.basis.update(basis)
    e.maps.clear();e.maps.update({s['role']:c.evidence_body(basis,s['identity_mapping_ref']) for s in old_slots})
    async def admit(role,decision_override=None):
        slot=next(s for s in basis['slots'] if s['role']==role)
        metadata={'retained_conflicts':'independence_ref','retained_qualification':'qualification_ref'}
        decision=dict(schema=c.FRAME,command_id='paired-assess-'+role,work_ref='WS:ONE',participant_slot=role,decision='ADMIT',criteria=[dict(criterion_id=k,evidence_ref=slot[metadata[k]],finding='SATISFIED',reason='Explicit inert authorized assessor reason based on actual retained '+k) for k in basis['required_criteria']],canonical_actor_ref=e.maps[role]['canonical_actor_ref'],identity_mapping_ref=slot['identity_mapping_ref'],limitations=list(c.LIMITS))
        if decision_override:decision.update(decision_override)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=e.route),base_url='http://inert') as client:
            return await client.post('/mcp/coo/evaluation-assessment',headers={'authorization':'Bearer '+e.token},json=decision)
    e.admit=admit;e.macro=world;e.frames=frames
    return e


def grant(e,action,assignment,*,input_sha256=None,pair_sha256=None):
    row=dict(action=action,task_id=e.macro['task']['task_id'],subject=ann.subject_selector(originals.current_reference(e.reference)),assignment=assignment,input_sha256=input_sha256,pair_sha256=pair_sha256)
    scope=copy.deepcopy(e.macro['scope']);assert row not in scope['commitments'];scope['commitments'].append(row)
    macro_fixture.advance_native_scope(e.macro,scope)


def assign(e,role,lease):
    admitted=a.current_admission(e.runtime,role);slot=admitted['slot'];subject=originals.current_reference(e.reference)
    request=dict(schema=a.ASSIGN,command_id='assign-'+lease.attempt.attempt_id,work_ref='WS:ONE',job_id=lease.attempt.job_id,original_attempt_id=subject['attempt_id'],participant_principal_ref=slot['principal_ref'],reason='Explicit inert authenticated assessor assignment of registered participant to actual original result')
    proposal=dict(schema='mastermind.registered_memory_evaluation_assignment.v1',delegation=e.grant,role=role,principal_ref=slot['principal_ref'],admission_event_id=admitted['event_id'],admission_sha256=c.digest(admitted['payload']),actor_key=admitted['actor_key'],subject=subject,original_case_sha256=hashlib.sha256(originals._REFERENCES[e.reference].case).hexdigest(),job_binding=a._job_binding(e.runtime.jobs.get_job(lease.attempt.job_id)),decision=request,assessor=admitted['payload']['assessor'])
    grant(e,'authorize_evaluation_subject_read',c.digest(proposal))
    result=asyncio.run(e.assign(role,lease));assert result.status_code==200,result.text


@contextmanager
def original_lease_heartbeat(e,lease):
    """Use the real original lease/token while synchronous source IO runs.

    No changed TTL/clock, fabricated heartbeat, new Attempt, allowance or retry.
    A lost original fence remains a failure and withholds subsequent exposure.
    """
    stop=threading.Event();errors=[];beats=[]
    def beat():
        while not stop.wait(min(5,e.runtime.store.lease_seconds/3)):
            try:
                e.runtime.attempts.heartbeat_attempt(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token)
                beats.append(True)
            except Exception as error:errors.append(type(error).__name__);return
    thread=threading.Thread(target=beat,name='inert-original-source-lease-heartbeat')
    thread.start()
    try:yield beats
    finally:
        stop.set();thread.join(timeout=5);assert not thread.is_alive()
        assert not errors,errors


def test_actual_frozen_macro_dispatcher_to_native_fd_pair_and_resolution(paired):
    e=paired
    for role in c.ROLES:
        response=asyncio.run(e.admit(role));assert response.status_code==200,response.text
    retained=[];pair=None
    for role in c.ROLES:
        lease=e.create_lease(role)
        with original_lease_heartbeat(e,lease):
            assign(e,role,lease)
            prepared=a.prepare_registered_evaluation(e.supervisor,original_reference=e.reference,original_attempt_lease=lease)
            material=ann.assignment_material(a.current_prepared(prepared))
            grant(e,'authorize_evaluation_subject_read',c.digest(material))
            packet=ann.input_packet(prepared,pair=pair)
            grant(e,'authorize_adjudication_exposure' if role=='adjudicator' else 'authorize_annotation_exposure',c.digest(material),input_sha256=hashlib.sha256(packet).hexdigest(),pair_sha256=c.digest(ann.current_pair(pair)) if pair else None)
            execution.retain_evaluation_economic_delegation(prepared,e.economy[3],task_class='extract',task_complexity='C1_ROUTINE_BOUNDED')
            execution.start_registered_evaluation(prepared,pair=pair)
            assert execution._RUNS[prepared]['proc'].wait(timeout=5)==0
            execution.collect_registered_evaluation(prepared)
        from control_plane.executive_runtime import JobPayload
        e.runtime.attempts.complete_attempt(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,payload=JobPayload(summary='Actual paired source annotation retained; no science'))
        retained.append(lease.attempt.attempt_id)
        if role=='reviewer_2':pair=ann.capture_retained_annotation_pair(e.supervisor,original_attempt_id=e.subject_lease.attempt.attempt_id,reviewer_attempt_ids=retained)
    result=ann.read_retained_resolution(e.supervisor,adjudication_attempt_id=retained[-1],pair=pair)
    assert result['verification']==w.FLAGS and result['scientific_admission'] is False and result['holds_released'] is False
    assert len(e.launches)==3 and len(retained)==3
    assert {r['request']['action'] for r in e.frames}=={'read_evaluation_basis','authorize_evaluation_subject_read','authorize_annotation_exposure','authorize_adjudication_exposure'}
    assert all(r['response']['request_sha256']==c.digest(r['request']) for r in e.frames)


def assert_only_original_lease_heartbeats(e,before,lease):
    after=e.runtime.events.list_events()
    assert after[:len(before)]==before
    for row in after[len(before):]:
        assert row.event_type=='ATTEMPT_HEARTBEAT'
        assert row.attempt_id==lease.attempt.attempt_id and row.job_id==lease.attempt.job_id
        assert row.aggregate_type=='attempt' and row.aggregate_id==lease.attempt.attempt_id
        assert set(row.payload)=={'lease_expires_at_ms'}


def test_actual_source_subject_read_permission_precedes_native_private_body(paired,monkeypatch):
    e=paired
    assert asyncio.run(e.admit('reviewer_1')).status_code==200
    lease=e.create_lease('reviewer_1');reads=[]
    from control_plane import paid_fabric_backend
    def private_read(*args,**kwargs):
        reads.append(str(args[0]));raise AssertionError('ungranted original body must remain unread')
    monkeypatch.setattr(paid_fabric_backend,'_private_read',private_read)
    before=e.runtime.events.list_events();counts=native.economic_count(e)
    with original_lease_heartbeat(e,lease):
        # No matching commitment was issued by the real retained source owner.
        response=asyncio.run(e.assign('reviewer_1',lease))
    assert response.status_code in (403,503),response.text
    assert reads==[] and e.launches==[] and native.economic_count(e)==counts
    assert_only_original_lease_heartbeats(e,before,lease)
    assert e.source_actions[-1]=='authorize_evaluation_subject_read'


def test_actual_macro_last_public_read_revocation_reaches_native_before_body(paired,monkeypatch):
    import inspect
    e=paired;module=macro_fixture.evaluation;original=module._verify_source;posts=[];fired=[];reads=[]
    def verify(commit):
        result=original(commit) # real immutable Git verifier, no qualifier stub
        caller=inspect.currentframe().f_back
        if caller.f_code.co_name=='_load_selected_control_records' and 'prepared' in caller.f_locals:
            posts.append(True)
            if len(posts)==2:
                e.macro['records']['access']['status']='revoked'
                macro_fixture.select(e.macro);fired.append(True)
        return result
    monkeypatch.setattr(module,'_verify_source',verify)
    from control_plane import paid_fabric_backend
    def private_read(*args,**kwargs):
        reads.append(str(args[0]));raise AssertionError('revoked original body must remain unread')
    monkeypatch.setattr(paid_fabric_backend,'_private_read',private_read)
    before=e.runtime.events.list_events();counts=native.economic_count(e)
    response=asyncio.run(e.admit('reviewer_1'))
    assert fired and len(posts)==2,'actual final second native resolver was not exercised'
    assert response.status_code in (403,503),response.text
    assert reads==[] and e.launches==[] and native.economic_count(e)==counts
    assert e.runtime.events.list_events()==before


@pytest.mark.parametrize('paired',['same-owned-actor'],indirect=True)
def test_actual_source_alias_mapping_refuses_second_actor_before_fd_or_pair(paired):
    e=paired
    for role in ('reviewer_1','reviewer_2'):
        response=asyncio.run(e.admit(role));assert response.status_code==200,response.text
    left=a.current_admission(e.runtime,'reviewer_1');right=a.current_admission(e.runtime,'reviewer_2')
    assert left['actor_key']==right['actor_key']
    assert left['slot']['principal_ref']!=right['slot']['principal_ref']
    first=e.create_lease('reviewer_1')
    with original_lease_heartbeat(e,first):
        assign(e,'reviewer_1',first)
        prepared=a.prepare_registered_evaluation(e.supervisor,original_reference=e.reference,original_attempt_lease=first)
        material=ann.assignment_material(a.current_prepared(prepared))
        grant(e,'authorize_evaluation_subject_read',c.digest(material))
        packet=ann.input_packet(prepared)
        grant(e,'authorize_annotation_exposure',c.digest(material),input_sha256=hashlib.sha256(packet).hexdigest())
        execution.retain_evaluation_economic_delegation(prepared,e.economy[3],task_class='extract',task_complexity='C1_ROUTINE_BOUNDED')
        execution.start_registered_evaluation(prepared)
        assert execution._RUNS[prepared]['proc'].wait(timeout=5)==0
        execution.collect_registered_evaluation(prepared)
    from control_plane.executive_runtime import JobPayload
    e.runtime.attempts.complete_attempt(first.attempt.attempt_id,fence_generation=first.attempt.fence_generation,lease_token=first.lease_token,payload=JobPayload(summary='Inert original first reviewer completed'))
    second=e.create_lease('reviewer_2');assert second.attempt.attempt_id!=first.attempt.attempt_id
    with original_lease_heartbeat(e,second):
        assign(e,'reviewer_2',second)
        before=e.runtime.events.list_events();counts=native.economic_count(e)
        with pytest.raises(ValueError):a.prepare_registered_evaluation(e.supervisor,original_reference=e.reference,original_attempt_lease=second)
        assert_only_original_lease_heartbeats(e,before,second)
        assert native.economic_count(e)==counts
    assert len(e.launches)==1
    assert not any(row.event_type=='MEMORY_EVALUATION_EXPOSED' and row.attempt_id==second.attempt.attempt_id for row in e.runtime.events.list_events())
    with pytest.raises(ValueError):ann.capture_retained_annotation_pair(e.supervisor,original_attempt_id=e.subject_lease.attempt.attempt_id,reviewer_attempt_ids=[first.attempt.attempt_id,second.attempt.attempt_id])
