"""Actual issuer/rereader/Runtime/FD/collector/pair join in disposable stores.

Explicit inert primitives: installed root/file ownership, kernel gateway/Control
identity, Linux fixed source response, native process UID/generation, and provider
reply. Real JWT verifier, sealed configuration parser/registry, admission writer,
canonical mapping rereader, original leases/Events, broker/budget, private bytes,
owned subprocess FD delivery and typed collector/pair/resolution are exercised.
No actual study, credentials, provider, installation, source read or grant.
"""
import asyncio
import base64
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time
from types import SimpleNamespace
import pytest
import httpx

from common import memory_native_wire as w
from common import memory_evaluation_contract as c
from control_plane import protected_memory_evaluation_source as source
from control_plane import protected_memory_evaluation_assignment as a
from control_plane import protected_memory_annotations as ann
from control_plane import protected_memory_evaluation_execution as exe
from control_plane import protected_memory_original as original
from control_plane import protected_memory_profile as profile
from control_plane import protected_memory_execution as old
from control_plane import protected_memory_peer as peer
from control_plane import executive_memory_issuer as root
from control_plane import memory_native_issuer as facade
from control_plane.executive_runtime import Runtime, JobPayload
from control_plane.executive_supervisor import ExecutiveSupervisor
from tests.test_protected_memory_execution import joined
from tests.test_protected_memory_peer import installed
from tests.test_executive_coo_host import registry_file, PRINCIPAL_PROFILE, ROOT, install, mandate
from tests.test_executive_peer_identity import owner_observation, bind_fixture
from tests.test_memory_evaluation_contract import ref
from tests import test_executive_coo_app as coo_app
from tests import test_mastermind_executive_app_asgi as jwt_fixture
from tests.test_protected_memory_economic import OperatorOwner, Broker, ProtectedMemoryEconomicOwner, pool_ledger, _bind_economic_namespace
rsa_key=jwt_fixture.rsa_key
REAL_POPEN=subprocess.Popen
from integrations.executive_mcp.server import _LiteralCooRoute
from control_plane import paid_fabric_backend as paid_module
REAL_PRIVATE_READ=paid_module._private_read


@pytest.fixture
def configured(tmp_path,monkeypatch):
    from tests.test_memory_native_wire import issuer
    from control_plane import native_memory_admission as native
    value=dict(schema=profile.SCHEMA,profile_id=profile.PROFILE,policy_sha256=c.digest(profile.POLICY),
        worker_id='protected-fixture',quota_class='memory-read',provider='glm',model='glm-5.3-flash',
        account_ref='configured-fixture-account',api_origin='https://api.z.ai/api/paas/v4',credential_slot='memory-model-01')
    meta=dict(adapter_id='protected-memory-model',execution_profile_id=profile.PROFILE,execution_profile_digest=c.digest(value),
        capability_policy_version='memory-fixture-v1',capability_policy_digest=value['policy_sha256'])
    runtime=Runtime.at(tmp_path/'runtime')
    runtime.workers.register_worker('study-control',provider='glm',account_label='inert-control',worker_type='protected-memory-model',capabilities=['research'],quota_classes={'root':{'provider':'glm','model':value['model'],'capabilities':['research'],'metadata':meta}})
    parent=runtime.jobs.create_job('Inert still-active study',requested_authorities=['READ'],constraints={'eligible_quota_classes':['root'],**{k:v for k,v in meta.items() if k!='adapter_id'}})
    assert runtime.attempts.claim_job(parent.job_id,worker_id='study-control',quota_class='root',lease_owner='fixture')
    runtime.workers.register_worker(value['worker_id'],provider='glm',account_label=value['account_ref'],worker_type='protected-memory-model',capabilities=['research'],quota_classes={value['quota_class']:{'provider':'glm','model':value['model'],'capabilities':['research'],'metadata':meta}})
    job=runtime.jobs.create_job('Original answer fixture',parent_job_id=parent.job_id,requested_authorities=['READ'],constraints={
        'eligible_quota_classes':['memory-read'],**{k:v for k,v in meta.items() if k!='adapter_id'},'native_memory':{'schema':'mastermind.native_memory_runtime_intent.v1','operation_id':'original-op','intent':{'study_id':'study','root_id':'native-root','operator_run_id':'native-parent','child_run_id':'native-child'}}})
    lease=runtime.attempts.claim_job(job.job_id,worker_id=value['worker_id'],quota_class=value['quota_class'],lease_owner='fixture');assert lease
    claim=native.capture_memory_runtime_claim(runtime,lease)
    raw=w.canonical(dict(runtime_root=str(runtime.store.root),protected_memory_execution=value,memory_native_issuer=dict(schema='mastermind.fixed_memory_issuer_transport.v2',protocol='memory.e0.native_issuer.v3',service_key_fingerprint=issuer(3)['broker_service_fingerprint'],known_hosts_sha256='a'*64,transport_profile='memory.e0.protected_m2_service_ssh.v2')))
    state=dict(raw=raw,credential=(1,2,3),owner=dict(service_label='com.mastermind.executive.control',configuration_sha256=hashlib.sha256(raw).hexdigest()),study_job=parent)
    monkeypatch.setattr(profile.os,'geteuid',lambda:450)
    monkeypatch.setattr(profile,'_read_config',lambda:state['raw'])
    monkeypatch.setattr(profile,'_credential_metadata',lambda:state['credential'])
    return runtime,job,claim,state


@pytest.fixture
def economy(tmp_path,monkeypatch,request):
    _bind_economic_namespace(request)
    # Four originally authorized DISPOSABLE children: subject + 2review +1judge.
    # This is initial fixture DATA, never a new allowance on a real root.
    here=tmp_path/'ext';(here/'broker').mkdir(parents=True);policy=tmp_path/'orch/fabric/pools.yaml';policy.parent.mkdir(parents=True)
    policy.write_text(json.dumps({'pools':{'glm':{'models':{'executor':'glm-5.3-flash'}}}}))
    (here/'state/remote_sub').mkdir(parents=True)
    accounts=tmp_path/'accounts.json';accounts.write_text(json.dumps({'providers':{'glm':{'enabled':True,'concurrency_cap':8,'accounts':[{'name':v,'per_account_cap':8} for v in ('configured-fixture-account','fixture-b','fixture-c')]}}}))
    hosts=tmp_path/'hosts.json';hosts.write_text('{}');status=tmp_path/'status.json';status.write_text('{}');clock=[1000.]
    import glm_host_account_source
    monkeypatch.setattr(glm_host_account_source,'filter_observed_accounts',lambda accounts,**kw:(accounts,'fixture_current_host_account'))
    broker=Broker(db_path=str(here/'broker/leases.sqlite'),lock_path=str(here/'broker/leases.lock'),accounts_path=str(accounts),status_json=str(status),hosts_path=str(hosts),this_host=socket.gethostname().split()[0],now_fn=lambda:clock[0],external_gates=False,check_pid=False)
    owner=OperatorOwner(here=here,clock=lambda:clock[0]);parent=broker.acquire('native-root','glm',account='configured-fixture-account',host=broker.this_host,pid=123,model='glm-5.3',task_class='remote-glm',ttl=180);assert parent.ok
    owner.authorize_root('native-root',4,2200.)
    token=owner.issue(dict(root='native-root',run_id='native-parent',lease_id=parent.lease_id,pool='glm',model='glm-5.3',account='configured-fixture-account',host=broker.this_host,support_sha256='a'*64,packet_sha256='b'*64,task_class='domain_orchestration'),4)['token']
    ledger=tmp_path/'ledger.jsonl';ledger.touch(mode=0o600);monkeypatch.setattr(pool_ledger,'LEDGER_PATH',str(ledger))
    grant=dict(schema='mastermind.fabric_protected_memory_pre_input.v1',root='native-root',parent='native-parent',run_id='native-child',task_class='extract',task_complexity='C1_ROUTINE_BOUNDED',pre_input_sha256='c'*64,profile_sha256='d'*64,model='glm-5.3-flash')
    selector={k:grant[k] for k in ('root','parent','run_id','pre_input_sha256','profile_sha256')};route=dict(account='configured-fixture-account',model='glm-5.3-flash',host=broker.this_host)
    engine=ProtectedMemoryEconomicOwner(owner,broker)
    from control_plane import executive_peer_identity as peers
    import protected_memory_economic as economics
    sock,other=socket.socketpair();request.addfinalizer(lambda:(sock.close(),other.close()));previous=peers._observe_socket
    def observe(connection):
        if connection.fileno()==sock.fileno():return peers._KernelObservation(b'R'*32,0,os.getppid(),987,peers._descriptor_identity(sock))
        return previous(connection)
    monkeypatch.setattr(peers,'_observe_socket',observe)
    def authority(scope):
        previous_uid=os.geteuid;monkeypatch.setattr(os,'geteuid',lambda:501)
        try:return economics.root_helper_invocation(sock,scope)
        finally:monkeypatch.setattr(os,'geteuid',previous_uid)
    engine._fixture_root_authority=authority
    return owner,broker,engine,token,grant,selector,route,clock,ledger


@pytest.fixture
def evaluation(joined,economy,rsa_key,tmp_path,monkeypatch,request):
    runtime,subject,lease,_,_,_,_,legacy,_=joined
    supervisor=legacy['supervisor']
    asyncio.run(supervisor.run_protected_memory_case(lease))
    original_ref=original.completed_original_reference(runtime,lease.attempt.attempt_id)
    parent=runtime.jobs.get_job(subject.root_job_id);assert parent.status.value=='RUNNING'
    app,token,current,settings=coo_app.setup(rsa_key,tmp_path/'app')
    from integrations.mastermind_executive_app.coo_binding import _digest
    from control_plane.executive_agent_capabilities import ExecutionCapabilityRegistry
    from ops.executive_os.coo_principal_host import CooInstalledSource
    from ops.executive_os import executive_mcp_entry as entry
    from integrations.executive_mcp.web_ceo_v3 import WEB_CEO_V3_PROFILE
    from control_plane.coo_principal_host import CooHostProvider
    from control_plane.workspace_read_service import WorkspaceReadService
    binding=current['binding'];stamp=_digest(binding['binding'])
    registry=ExecutionCapabilityRegistry.load(registry_file(tmp_path),source_root=ROOT)
    now=runtime.store.now_ms()
    grant=dict(schema=c.DELEGATION,enabled=True,generation='inert-assessment-1',study_root='native-root',study_id='study',root_job_id=parent.job_id,
        registration_ref=ref('registration'),reviewer_plan_ref=ref('reviewer-plan'),guide_ref=dict(ref('guide'),sha256=c.GUIDE_SHA),source_purpose_ref=ref('separate-evaluation-purpose'),
        source_audience=dict(receiver_kind='native_evaluation_custodian',service_key_fingerprint=json.loads(legacy['config']['raw'])['memory_native_issuer']['service_key_fingerprint'],control_service_label='com.mastermind.executive.control'),decision_ref=ref('explicit-study-delegation'),principal_binding_digest=stamp,actions=list(c.ACTIONS),evidence_profile=c.PROFILE,not_before_ms=now-1000,expires_at_ms=now+3600000)
    row=dict(enabled=True,work_ref='WS:ONE',principal_binding_digest=stamp,mission_authority_ref='authority:inert-study',outcome_ref='outcome:inert',proof_contract_ref='proof:inert',capability_profile_id=PRINCIPAL_PROFILE,capability_profile_digest=registry.profiles[PRINCIPAL_PROFILE].profile_digest,execution_profiles=['research_only'],allowed_write_paths=[],authority_version=3,principal_actions=['bounded_intent','governed_orchestration'],memory_evaluation_delegation=grant)
    coo=dict(policy=dict(dataclasses.asdict(settings.policy),schema='mastermind.business_mcp_auth_policy.v1'),binding=binding,missions=[row])
    # Exact policy schema is inherited from the actual fixture resource policy.
    from integrations.business_mcp_auth.contracts import AUTH_POLICY_SCHEMA
    coo['policy']['schema']=AUTH_POLICY_SCHEMA
    raw_install=install.base_document();raw_install['policies']={'schema':'mastermind.executive_app_policy_example.v1','read':dict(dataclasses.asdict(settings.executive.policies.read),schema=AUTH_POLICY_SCHEMA),'submit':dict(dataclasses.asdict(settings.executive.policies.submit),schema=AUTH_POLICY_SCHEMA)}
    raw_install.update(coo=coo,executive_mcp_profile=WEB_CEO_V3_PROFILE)
    source_dir=tmp_path/raw_install['release_sha'];(source_dir/'config').mkdir(parents=True)
    (source_dir/'config/executive_claude_principal_capabilities.json').write_bytes((ROOT/'config/executive_claude_principal_capabilities.json').read_bytes())
    coo_path=tmp_path/'executive-mcp.json';coo_path.write_text(json.dumps(raw_install))
    monkeypatch.setattr(entry,'require_sealed_path',lambda *args,**kwargs:None) # INERT ownership premise only
    workspace=WorkspaceReadService(cache=None,runtime=runtime,authorize=None,armed={},runtime_identity={})
    mission=mandate._real_owner_mission();mission=json.loads(json.dumps(mission).replace(json.dumps(mission['mission']['root_job_id']),json.dumps(parent.job_id)));current['mission']=mission
    monkeypatch.setattr(workspace,'read_mission_for_work_ref',lambda work:copy.deepcopy(mission)) # actual cached acquisition premise
    config=json.loads(legacy['config']['raw']);profiles=[];documents=[];slots=[];maps={};known_creds={}
    accounts=['configured-fixture-account','fixture-b','fixture-c']
    shared_actor=getattr(request,'param',None)=='same-owned-actor'
    if shared_actor:accounts[1]=accounts[0]
    for i,role in enumerate(c.ROLES):
        selected=dict(config['protected_memory_execution'],worker_id='evaluation-'+str(i),account_ref=accounts[i],credential_slot='memory-model-'+str(i+1).zfill(2))
        credential=w.canonical(dict(schema='mastermind.protected_memory_model_credential.v1',account_ref=accounts[i],api_key='INERT_ONLY_CREDENTIAL_'+str(i)))
        credential_path=tmp_path/(selected['credential_slot']+'.json');credential_path.write_bytes(credential);credential_path.chmod(0o440)
        known_creds[selected['credential_slot']]=(credential_path,credential)
        credential_ref=ref('installed-credential-'+str(i))
        mapping=dict(schema='mastermind.native_model_actor_mapping.v1',actor_kind='NATIVE_MODEL',canonical_actor_ref=ref('assessor-admitted-actor-'+str(0 if shared_actor and i==1 else i)),credential_bindings=[dict(credential_binding_ref=credential_ref,credential_document_sha256=hashlib.sha256(credential).hexdigest())],assessment_basis='Explicit inert reasoned canonical mapping from current retained assessment evidence, including aliases/rotation',limitations=list(c.LIMITS))
        fields={}
        for kind in ('principal_ref','qualification_ref','independence_ref','identity_mapping_ref'):
            body=mapping if kind=='identity_mapping_ref' else dict(schema='research_factory.market_memory_e0_reviewer_'+kind.removesuffix('_ref')+'_metadata.v2',object_id=role+'-'+kind,authority='display_only',study_id='study',participant_id=role+'-principal_ref',verification=dict(w.FLAGS))
            if kind=='principal_ref':body['execution_identity']=None
            elif kind=='qualification_ref':body['declared_competencies']=['source_support']
            elif kind=='independence_ref':body.update(declared_distinct_from=[r+'-principal_ref' for r in c.ROLES if r!=role],prior_exposure_status='not_established',peer_ratings_visibility='not_established')
            r=ref(role+'-'+kind,body);r['schema']=body['schema'];documents.append(dict(reference=r,body=body));fields[kind]=r
        slots.append(dict(role=role,execution_profile_id='model-'+str(i),**fields));maps[role]=mapping
        profiles.append(dict(id='model-'+str(i),profile=selected,credential_binding_ref=credential_ref,credential_document_sha256=hashlib.sha256(credential).hexdigest()))
        meta=dict(adapter_id='protected-memory-model',execution_profile_id=profile.PROFILE,execution_profile_digest=c.digest(selected),capability_policy_version='memory-fixture-v1',capability_policy_digest=selected['policy_sha256'])
        runtime.workers.register_worker(selected['worker_id'],provider='glm',account_label=accounts[i],worker_type='protected-memory-model',capabilities=['research'],quota_classes={'memory-read':{'provider':'glm','model':selected['model'],'capabilities':['research'],'metadata':meta}})
    # The source-owned registered plan is retained evidence, not a caller slot.
    from common.memory_participant_view import _json
    case=(runtime.store.root/'data/control_plane/runs'/lease.attempt.attempt_id/'memory-original-input').read_bytes()
    task_id=_json(case[:-len(w.SUFFIX)],canonical=True)['task']['task_id']
    plan_schema=json.loads((ROOT/'tests/fixtures/market-memory-owner-contract/contracts/market_memory/e0_reviewer_plan.v1.schema.json').read_bytes())
    people=[{k:s[k] for k in ('principal_ref','qualification_ref','independence_ref')} for s in slots]
    plan=dict(schema='research_factory.market_memory_e0_reviewer_plan.v1',object_id='registered-plan',authority='display_only',study_id='study',preregistered_at='2026-11-01T00:00:00Z',
        **{k:plan_schema['properties'][k]['const'] for k in ('protocol_sha256','annotation_guide_sha256','membership_sha256')},
        tasks_ref=dict(schema='research_factory.market_memory_e0_tasks.v1',object_id='registered-tasks',sha256='c'*64,bytes=20),
        reviewers=people[:2],adjudicator=people[2],assignments=[dict(task_id=task_id,reviewer_principal_ids=[v['principal_ref']['object_id'] for v in people[:2]],adjudicator_principal_id=people[2]['principal_ref']['object_id'])],
        blinding={k:v['const'] for k,v in plan_schema['$defs']['blinding']['properties'].items()})
    grant['reviewer_plan_ref']=dict(ref('registered-plan',plan),schema=plan['schema'])
    documents.append(dict(reference=grant['reviewer_plan_ref'],body=plan))
    coo_path.write_text(json.dumps(raw_install))
    installed_source=CooInstalledSource.from_path(coo_path,source_dir,expected_uid=450)
    provider=CooHostProvider(installed_source,workspace)
    basis=dict(schema='research_factory.memory_evaluation_basis.v1',**{k:grant[k] for k in ('registration_ref','reviewer_plan_ref','guide_ref','source_purpose_ref')},required_criteria=['identity','independence','qualification'],independence_rules=['distinct_canonical_actor','assessed_conflicts'],slots=slots,evidence=documents)
    config['memory_evaluation']=dict(schema=source.CONFIG_SCHEMA,armed=True,coo_config=str(coo_path),coo_source=str(source_dir),work_ref='WS:ONE',profiles=profiles,source_protocol='memory.e0.evaluation_issuer.v1')
    legacy['config']['raw']=w.canonical(config);legacy['config']['owner']['configuration_sha256']=hashlib.sha256(legacy['config']['raw']).hexdigest()
    # Real credential bytes/read/hash/stability; only root ownership of disposable
    # objects and their namespace are substituted, never a top-level qualifier.
    from control_plane import codex_provider_realm as realm
    from contextlib import contextmanager
    fds=set();private_fds=set();real_fstat=os.fstat;real_open=os.open;real_close=os.close;real_lstat=os.lstat
    def opened(path,*args,**kwargs):
        fd=real_open(path,*args,**kwargs)
        if isinstance(path,(str,Path)) and Path(path).is_relative_to(runtime.store.root/'data/control_plane/runs'):private_fds.add(fd)
        return fd
    def closed(fd):
        private_fds.discard(fd);return real_close(fd)
    def observed_stat(fd):
        s=real_fstat(fd)
        if fd not in fds and fd not in private_fds:return s
        uid=0 if fd in fds else 450
        return SimpleNamespace(**{k:getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')},st_uid=uid,st_gid=450)
    def named_stat(path,*args,**kwargs):
        s=real_lstat(path,*args,**kwargs)
        if isinstance(path,(str,Path)) and Path(path).is_relative_to(runtime.store.root/'data/control_plane/runs') and stat.S_ISREG(s.st_mode):
            return SimpleNamespace(**{k:getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')},st_uid=450,st_gid=450)
        return s
    @contextmanager
    def native_open(path,**kwargs):
        allowed=[v[0] for v in known_creds.values()]
        assert path in allowed
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW);fds.add(fd)
        try:yield fd,observed_stat(fd)
        finally:fds.remove(fd);os.close(fd)
    monkeypatch.setattr(realm,'_native_open',native_open);monkeypatch.setattr(os,'fstat',observed_stat)
    monkeypatch.setattr(os,'open',opened);monkeypatch.setattr(os,'close',closed);monkeypatch.setattr(os,'lstat',named_stat)
    monkeypatch.setattr(paid_module,'_private_read',REAL_PRIVATE_READ)
    def private_directory(path):
        assert path.parent==runtime.store.root/'data/control_plane/runs' and runtime.attempts.get_attempt(path.name) is not None
        assert not path.is_symlink() and stat.S_IMODE(path.stat().st_mode)==0o700
    monkeypatch.setattr(old,'_private_directory',private_directory)
    monkeypatch.setattr(source,'SLOTS',{slot:v[0] for slot,v in known_creds.items()})
    previous_exchange=root._exchange;source_actions=[];faults={}
    def exchange(raw):
        q=w._unframe(raw,262144)
        if q['schema']!=c.REQUEST:return previous_exchange(raw)
        c.request(q);source_actions.append(q['action'])
        if faults.get('source'):raise root.IssuerExchangeUnknown()
        if faults.get('change_owned_process_on_exposure') and q['action']=='authorize_annotation_exposure':faults['process_changed']=True
        r=dict(schema=c.RESPONSE,state='CURRENT',request_sha256=c.digest(q),source_purpose_ref=grant['source_purpose_ref'],source_owner=dict(installation_id='inert-linux',installation_epoch='1',service_key_fingerprint=grant['source_audience']['service_key_fingerprint']),generation='access-1',not_before_ms=now-1000,expires_at_ms=now+3600000,basis=basis if q['action']=='read_evaluation_basis' else None,verification=dict(w.FLAGS),scientific_admission=False)
        if faults.get('expired'):r.update(not_before_ms=now-5000,expires_at_ms=now-1)
        if faults.get('access_advance'):r['generation']='access-2'
        b=w.canonical(r);return len(b).to_bytes(4,'big')+b
    monkeypatch.setattr(root,'_exchange',exchange)
    # Kernel identity/source qualification fixture on THIS accepted App socket.
    from control_plane import executive_peer_identity as peers, executive_installed_peer as installed_peer
    gateway,other=socket.socketpair();request.addfinalizer(lambda:(gateway.close(),other.close()));previous_observe=peers._observe_socket
    def observe(connection):
        if connection.fileno()==gateway.fileno():return peers._KernelObservation(b'G'*32,458,os.getpid(),1357,peers._descriptor_identity(gateway))
        return previous_observe(connection)
    monkeypatch.setattr(peers,'_observe_socket',observe)
    previous_qualify=installed_peer.qualify_installed_peer
    def qualify(capture,*,role):
        if role=='gateway':return bind_fixture(capture,dataclasses.replace(owner_observation(capture),service_label='com.mastermind.executive.mcp',config_digest=hashlib.sha256(coo_path.read_bytes()).hexdigest()))
        return previous_qualify(capture,role=role)
    monkeypatch.setattr(installed_peer,'qualify_installed_peer',qualify)
    from integrations.mastermind_executive_app.gateway import CeoIngressResponse,TRANSPORT_SENT_OK
    async def send(path,frame):
        assert path==settings.executive.ceo_ingress_socket_path
        answer=a.assess_from_installed_app(gateway,frame,provider,supervisor)
        return CeoIngressResponse(transport=TRANSPORT_SENT_OK,ok=answer['ok'],result=answer.get('result'),error=answer.get('error'))
    monkeypatch.setattr(app._client,'send_frame',send) # only local App transport; actual issuer remains REAL
    settings=dataclasses.replace(settings,authority_provider=lambda principal,work:installed_source.snapshot(work)[2])
    app.settings=settings
    # Fixed public guide read primitive + installed binary primitive only.
    from control_plane import paid_fabric_backend as paid
    monkeypatch.setattr(paid,'_root_source',lambda path:path.read_bytes() if path in (ROOT/'common/memory_evaluation_guide.md',coo_path) else (_ for _ in ()).throw(AssertionError('unexpected source')))
    monkeypatch.setattr(exe,'_source_binary',old._source_binary)
    launches=[]
    class Inspector:
        def inspect(self,pid):
            assert pid in launches
            return SimpleNamespace(pgid=pid,start_identity='inert-owned-'+str(pid),session_id=pid,effective_uid=501 if faults.get('process_changed') else 450,effective_gid=450,real_uid=450,real_gid=450)
        def boot_session_id(self):return 'inert-boot'
    monkeypatch.setattr(exe,'ProcessInspector',Inspector)
    monkeypatch.setattr(__import__('control_plane.codex_worker',fromlist=['ProcessInspector']),'ProcessInspector',Inspector)
    original_popen=REAL_POPEN
    program='''import os,sys,socket,json,base64,hashlib
s=socket.socket(fileno=int(sys.argv[1]));s.sendall(b'READY\\n');raw=b''
while True:
 p=s.recv(65536)
 if not p:break
 raw+=p
assert int.from_bytes(raw[:4],'big')==len(raw)-4
env=json.loads(raw[4:]);packet=base64.b64decode(env['input_base64']);body=json.loads(base64.b64decode(env['body_base64']));assert body['input'].encode()==packet
p=json.loads(packet[:packet.rfind(b'}')+1]);assert p['result_contract']['result_schema'].startswith('mastermind.memory_evaluation_')
original=json.loads(p['original_packet'][:p['original_packet'].rfind('}')+1]);descriptors=[{k:card[k] for k in ('context_id','capture_id','packet_sha256')}|{'field':fact['field'],'citation':fact['citation']} for card in original['source_view']['source_cards'] for fact in card['facts']]
if p['stage']=='independent_annotation':
 assert p['comparison'] is None
 ans=p['answer'].encode();j=int(sys.argv[2]);quote=ans[:7]
 value={'schema':'mastermind.memory_evaluation_annotation.v1','answer_assessment':'incorrect' if j==1 else 'correct','facets':[{'facet_id':f,'assessment':'incorrect' if j==1 else 'correct','reason':'inert original reason '+str(j)} for f in p['task']['required_facet_ids']], 'claims':[{'claim_id':'local-'+str(j),'span':{'start_byte':0,'end_byte_exclusive':7,'quoted_utf8':quote.decode(),'span_sha256':hashlib.sha256(quote).hexdigest()},'verdict':'unsupported' if j==1 else 'supported','material':True,'critical':j==1,'source_support':[] if j==1 else [descriptors[0]],'reason':'Retained inert original claim judgment'}], 'relevance':[{'context_id':card['context_id'],'relevance':2,'facet_ids':p['task']['required_facet_ids'],'reason':'Inert registered facet'} for card in json.loads(p['original_packet'][:p['original_packet'].rfind('}')+1])['source_view']['source_cards']]}
else:
 assert 'actor_keys' not in p['comparison']
 value={'schema':'mastermind.memory_evaluation_resolution.v1','resolutions':[{'item_key':item['item_key'],'judgment':{'assessment':'correct'} if item['item_key']=='answer' or item['item_key'].startswith('facet:') else {'verdict':'supported','material':True,'critical':False,'source_support':[descriptors[0]]},'reason':'Original harsher provisional finding resolved with retained reason'} for item in p['comparison']['comparison_items']], 'overall_reason':'Explicit inert distinct-adjudicator original resolution'}
os.write(1,json.dumps(value,sort_keys=True,separators=(',',':')).encode());s.close()
'''
    def popen(argv,**kwargs):
        assert argv[3]==str(old.RUNNER) and len(kwargs['pass_fds'])==1
        index=len(launches)
        proc=original_popen([sys.executable,'-I','-c',program,argv[4],str(index)],**kwargs);launches.append(proc.pid);return proc
    monkeypatch.setattr(exe.subprocess,'Popen',popen)
    def create_lease(role):
        i=c.ROLES.index(role);p=profiles[i]['profile'];meta=dict(execution_profile_id=profile.PROFILE,execution_profile_digest=c.digest(p),capability_policy_version='memory-fixture-v1',capability_policy_digest=p['policy_sha256'])
        job=runtime.jobs.create_job('Inert registered evaluation '+role,parent_job_id=parent.job_id,requested_authorities=['READ'],constraints={**meta,'eligible_quota_classes':['memory-read'],'native_memory':{'schema':'mastermind.native_memory_runtime_intent.v1','operation_id':'eval-'+role,'intent':{'study_id':'study','root_id':'native-root','operator_run_id':'native-parent','child_run_id':'eval-'+role}},'native_memory_evaluation':dict(schema='mastermind.native_memory_evaluation_intent.v1',subject_attempt_id=lease.attempt.attempt_id,participant_slot=role,**{k:grant[k] for k in ('registration_ref','reviewer_plan_ref','guide_ref')})})
        result=runtime.attempts.claim_job(job.job_id,worker_id=p['worker_id'],quota_class='memory-read',lease_owner='fixture');assert result
        directory=runtime.store.root/'data/control_plane/runs'/result.attempt.attempt_id;directory.mkdir(mode=0o700);return result
    from starlette.applications import Starlette
    actual_route=_LiteralCooRoute(Starlette(),evaluation_core=app)
    async def admit(role,token_override=None,decision_override=None):
        slot=next(s for s in slots if s['role']==role);m=c.evidence_body(basis,slot['identity_mapping_ref'])
        decision=dict(schema=c.FRAME,command_id='inert-assess-'+role,work_ref='WS:ONE',participant_slot=role,decision='ADMIT',criteria=[dict(criterion_id=k,evidence_ref=slot[{'identity':'principal_ref','independence':'independence_ref','qualification':'qualification_ref'}[k]],finding='SATISFIED',reason='Actual inert authorized assessor reason for '+k) for k in basis['required_criteria']],canonical_actor_ref=m['canonical_actor_ref'],identity_mapping_ref=slot['identity_mapping_ref'],limitations=list(c.LIMITS))
        if decision_override:decision.update(decision_override)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=actual_route),base_url='http://inert') as client:
            return await client.post('/mcp/coo/evaluation-assessment',headers={'authorization':'Bearer '+(token_override or token)},json=decision)
    async def assign(role,lease,**changes):
        slot=next(s for s in slots if s['role']==role)
        decision=dict(schema=a.ASSIGN,command_id='assign-'+lease.attempt.attempt_id,work_ref='WS:ONE',job_id=lease.attempt.job_id,
            original_attempt_id=original_ref and original.current_reference(original_ref)['attempt_id'],participant_principal_ref=slot['principal_ref'],reason='Explicit inert authenticated assessor assignment of registered participant to actual original result')
        decision.update(changes)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=actual_route),base_url='http://inert') as client:
            return await client.post('/mcp/coo/evaluation-assessment',headers={'authorization':'Bearer '+token},json=decision)
    return SimpleNamespace(runtime=runtime,supervisor=supervisor,reference=original_ref,subject=subject,subject_lease=lease,grant=grant,basis=basis,profiles=profiles,maps=maps,config=config,coo=raw_install,coo_path=coo_path,state=legacy['config'],create_lease=create_lease,admit=admit,assign=assign,launches=launches,source_actions=source_actions,faults=faults,economy=economy,app=app,route=actual_route,token=token,provider=provider,gateway=gateway)


def complete(e,role,pair=None):
    response=asyncio.run(e.admit(role));assert response.status_code==200,response.text
    lease=e.create_lease(role)
    assigned=asyncio.run(e.assign(role,lease));assert assigned.status_code==200,assigned.text
    prepared=a.prepare_registered_evaluation(e.supervisor,original_reference=e.reference,original_attempt_lease=lease)
    exe.retain_evaluation_economic_delegation(prepared,e.economy[3],task_class='extract',task_complexity='C1_ROUTINE_BOUNDED')
    exe.start_registered_evaluation(prepared,pair=pair)
    proc=exe._RUNS[prepared]['proc'];assert proc.wait(timeout=5)==0
    receipt=exe.collect_registered_evaluation(prepared)
    e.runtime.attempts.complete_attempt(lease.attempt.attempt_id,fence_generation=lease.attempt.fence_generation,lease_token=lease.lease_token,payload=JobPayload(summary='Inert original annotation retained'))
    return lease,receipt,prepared


def test_real_issuer_actor_fd_collector_pair_and_distinct_resolution(evaluation):
    e=evaluation
    left,lreceipt,_=complete(e,'reviewer_1')
    right,rreceipt,_=complete(e,'reviewer_2')
    pair=ann.capture_retained_annotation_pair(e.supervisor,original_attempt_id=e.subject_lease.attempt.attempt_id,reviewer_attempt_ids=[left.attempt.attempt_id,right.attempt.attempt_id])
    original_pair=ann.current_pair(pair);assert len(original_pair['original_annotations'])==2
    judge,_,_=complete(e,'adjudicator',pair)
    final=ann.read_retained_resolution(e.supervisor,adjudication_attempt_id=judge.attempt.attempt_id,pair=pair)
    assert final['pair']==original_pair and final['original_resolution']
    assert final['scientific_admission'] is False and final['holds_released'] is False
    assert len(e.launches)==3 and all(not v for v in final['verification'].values())
    assert 'Original harsher provisional finding' in final['original_resolution']
    events=e.runtime.events.list_events();assert sum(x.event_type=='MEMORY_EVALUATOR_ADMITTED' for x in events)==3
    assert sum(x.event_type=='MEMORY_EVALUATION_ASSIGNED' for x in events)==3
    assert sum(x.event_type=='MEMORY_EVALUATION_EXPOSED' for x in events)==3
    assert sum(x.event_type=='MEMORY_EVALUATION_COMPLETED' for x in events)==3
    # Final rereads remain real source/recipient checks, not cached permissions.
    before=economic_count(e);path=e.runtime.store.root/'data/control_plane/runs'/judge.attempt.attempt_id/'memory-evaluation-result'
    raw=path.read_bytes();path.write_bytes(raw.replace(b'Original harsher',b'Xriginal harsher',1))
    with pytest.raises(ValueError):ann.read_retained_resolution(e.supervisor,adjudication_attempt_id=judge.attempt.attempt_id,pair=pair)
    path.write_bytes(raw)
    reader=paid_module._private_read;changed=[]
    def revoke_during_read(selected,limit):
        body=reader(selected,limit)
        if selected==path and not changed:changed.append(True);e.faults['source']=True
        return body
    # The underlying private FD reader stays unchanged; the source permission
    # withdraws during one body read, so the entire new view must be withheld.
    with pytest.MonkeyPatch.context() as m:
        m.setattr(paid_module,'_private_read',revoke_during_read)
        with pytest.raises(ValueError):ann.read_retained_resolution(e.supervisor,adjudication_attempt_id=judge.attempt.attempt_id,pair=pair)
    assert changed and path.read_bytes()==raw
    e.faults['source']=False;e.faults['access_advance']=True
    assert ann.read_retained_resolution(e.supervisor,adjudication_attempt_id=judge.attempt.attempt_id,pair=pair)['original_resolution']==final['original_resolution']
    assert economic_count(e)==before and len(e.launches)==3
    # The final pair reread can block after adjudicator _completed returned.
    # A real authenticated revocation there must withhold the already-read body.
    previous_pair=ann.current_pair;pair_reads=[]
    def revoke_during_last_pair(cap):
        value=previous_pair(cap);pair_reads.append(True)
        if len(pair_reads)==2:
            r=asyncio.run(e.admit('adjudicator',decision_override={'decision':'REFUSE'}))
            assert r.status_code==200,r.text
        return value
    with pytest.MonkeyPatch.context() as m:
        m.setattr(ann,'current_pair',revoke_during_last_pair)
        with pytest.raises(ValueError):ann.read_retained_resolution(e.supervisor,adjudication_attempt_id=judge.attempt.attempt_id,pair=pair)
    assert len(pair_reads)==2 and path.read_bytes()==raw
    assert economic_count(e)==before and len(e.launches)==3


def economic_count(e):
    with e.economy[0].transaction() as con:
        return con.execute('SELECT count(*) FROM operator_child_authorizations').fetchone()[0]


@pytest.mark.parametrize('evaluation',['same-owned-actor'],indirect=True)
def test_owned_actor_alias_falsifier_refuses_before_b_fd_and_pair(evaluation):
    e=evaluation
    first,_,_=complete(e,'reviewer_1')
    assert asyncio.run(e.admit('reviewer_2')).status_code==200
    before=economic_count(e)
    other=e.create_lease('reviewer_2')
    assigned=asyncio.run(e.assign('reviewer_2',other));assert assigned.status_code==200,assigned.text
    assert other.attempt.attempt_id!=first.attempt.attempt_id
    left=a.current_admission(e.runtime,'reviewer_1');right=a.current_admission(e.runtime,'reviewer_2')
    assert left['slot']['principal_ref']!=right['slot']['principal_ref']
    assert left['actor_key']==right['actor_key']
    assert e.profiles[0]['profile']['account_ref']==e.profiles[1]['profile']['account_ref']
    assert e.profiles[0]['profile']['credential_slot']!=e.profiles[1]['profile']['credential_slot']
    with pytest.raises(ValueError):
        a.prepare_registered_evaluation(e.supervisor,original_reference=e.reference,original_attempt_lease=other)
    with pytest.raises(ValueError):
        ann.capture_retained_annotation_pair(e.supervisor,original_attempt_id=e.subject_lease.attempt.attempt_id,
            reviewer_attempt_ids=[first.attempt.attempt_id,other.attempt.attempt_id])
    assert len(e.launches)==1 and economic_count(e)==before
    assert not any(x.event_type=='MEMORY_EVALUATION_EXPOSURE_ATTEMPT' and x.attempt_id==other.attempt.attempt_id for x in e.runtime.events.list_events())
    assert not (e.runtime.store.root/'data/control_plane/runs'/other.attempt.attempt_id/'memory-evaluation-input').exists()


@pytest.mark.parametrize('fault',['bad-signature','read-only','foreign-client','expired'])
def test_actual_jwt_ingress_refuses_before_assignment_and_source(evaluation,rsa_key,fault):
    e=evaluation
    if fault=='bad-signature':token='not.a.signature'
    else:
        changes={'scope':' '.join(coo_app.COO_SCOPES)}
        if fault=='read-only':changes['scope']='mastermind.executive.read'
        elif fault=='foreign-client':changes['client_id']='unbound-inert-client'
        else:changes.update(iat=jwt_fixture.NOW-600,nbf=jwt_fixture.NOW-600,exp=jwt_fixture.NOW-60)
        token=jwt_fixture._token(rsa_key,**changes)
    before=economic_count(e);answer=asyncio.run(e.admit('reviewer_1',token))
    assert answer.status_code in (401,403)
    assert e.source_actions==[] and e.launches==[] and economic_count(e)==before
    assert not any(x.event_type=='MEMORY_EVALUATOR_ADMITTED' for x in e.runtime.events.list_events())


@pytest.mark.parametrize('fault',['missing-purpose','revoked-delegation','source-unknown','expired-source','unsupported-independence','unsupported-actor'])
def test_real_installed_or_source_authority_failure_never_issues_admission(evaluation,fault):
    e=evaluation
    if fault in ('missing-purpose','revoked-delegation'):
        raw=json.loads(e.coo_path.read_bytes())
        if fault=='missing-purpose':
            raw['coo']['missions'][0].pop('memory_evaluation_delegation');raw['coo']['missions'][0]['authority_version']=2
        else:raw['coo']['missions'][0]['memory_evaluation_delegation']['enabled']=False
        e.coo_path.write_text(json.dumps(raw))
    elif fault=='source-unknown':e.faults['source']=True
    elif fault=='expired-source':e.faults['expired']=True
    elif fault=='unsupported-independence':e.basis['independence_rules']=['three_providers']
    else:
        slot=e.basis['slots'][0];item=next(i for i in e.basis['evidence'] if i['reference']==slot['identity_mapping_ref'])
        item['body']['actor_kind']='HUMAN';r=ref(item['reference']['object_id'],item['body']);r['schema']=item['body']['schema']
        slot['identity_mapping_ref']=r;item['reference']=r
    before=economic_count(e)
    answer=asyncio.run(e.admit('reviewer_1'))
    assert answer.status_code!=200
    assert not any(x.event_type=='MEMORY_EVALUATOR_ADMITTED' for x in e.runtime.events.list_events())
    assert e.launches==[] and economic_count(e)==before


def test_authenticated_revocation_reread_withholds_existing_assignment(evaluation):
    e=evaluation
    assert asyncio.run(e.admit('reviewer_1')).status_code==200
    original_admission=a.current_admission(e.runtime,'reviewer_1')['event_id']
    lease=e.create_lease('reviewer_1');before=economic_count(e)
    assigned=asyncio.run(e.assign('reviewer_1',lease));assert assigned.status_code==200,assigned.text
    assert asyncio.run(e.admit('reviewer_1',decision_override={'decision':'REFUSE'})).status_code==200
    with pytest.raises(ValueError):a.current_admission(e.runtime,'reviewer_1')
    with pytest.raises(ValueError):a.prepare_registered_evaluation(e.supervisor,original_reference=e.reference,original_attempt_lease=lease)
    assert any(x.event_type=='MEMORY_EVALUATOR_ADMITTED' and x.event_id==original_admission for x in e.runtime.events.list_events())
    assert e.launches==[] and economic_count(e)==before


@pytest.mark.parametrize('kind',['dict','clone','subclass'])
def test_capability_shape_cannot_release_fd_or_read_private_pair(kind):
    if kind=='dict':value={'registered':True,'actor_key':'anything'}
    elif kind=='clone':value=object.__new__(a.EvaluationAssignmentCapability)
    else:
        class Borrowed(a.EvaluationAssignmentCapability):pass
        value=object.__new__(Borrowed)
    with pytest.raises(ValueError):a.current_assignment(value)
    with pytest.raises(ValueError):ann.current_pair(value)


def test_process_actor_change_during_source_authorization_withholds_fd(evaluation):
    e=evaluation
    assert asyncio.run(e.admit('reviewer_1')).status_code==200
    lease=e.create_lease('reviewer_1')
    assigned=asyncio.run(e.assign('reviewer_1',lease));assert assigned.status_code==200,assigned.text
    prepared=a.prepare_registered_evaluation(e.supervisor,original_reference=e.reference,original_attempt_lease=lease)
    exe.retain_evaluation_economic_delegation(prepared,e.economy[3],task_class='extract',task_complexity='C1_ROUTINE_BOUNDED')
    e.faults['change_owned_process_on_exposure']=True
    with pytest.raises(old.MemoryExecutionUnknown):exe.start_registered_evaluation(prepared)
    run=exe._RUNS[prepared];assert run['proc'].wait(timeout=5)!=0
    assert len(e.launches)==1
    assert not any(x.event_type=='MEMORY_EVALUATION_EXPOSED' and x.attempt_id==lease.attempt.attempt_id for x in e.runtime.events.list_events())
    # Original attempt/paid rows remain, not a refund/replacement/retry grant.
    with pytest.raises(ValueError):exe.start_registered_evaluation(prepared)
    assert len(e.launches)==1


def test_public_facet_is_literal_and_never_exposes_or_accepts_other_paths(evaluation):
    e=evaluation
    async def requests():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=e.route),base_url='http://inert') as client:
            for path,method in [('/mcp/coo/evaluation-assessment?role=adjudicator','POST'),
                    ('/mcp/coo/evaluation-assessment/extra','POST'),('/mcp/coo/evaluation-assessment','GET')]:
                r=await client.request(method,path,headers={'authorization':'Bearer '+e.token},content=b'INERT_PRIVATE_CANARY')
                assert r.status_code==404 and b'INERT_PRIVATE_CANARY' not in r.content
    asyncio.run(requests())
    assert not e.source_actions and not e.launches


def test_admission_and_caller_role_do_not_assign_or_expose_private_input(evaluation):
    e=evaluation
    assert asyncio.run(e.admit('reviewer_1')).status_code==200
    lease=e.create_lease('reviewer_1');before=economic_count(e)
    with pytest.raises(ValueError):a.prepare_registered_evaluation(e.supervisor,original_reference=e.reference,original_attempt_lease=lease)
    assert len(e.launches)==0 and economic_count(e)==before
    assert not any(x.event_type=='MEMORY_EVALUATION_ASSIGNED' for x in e.runtime.events.list_events())
    # A real authenticated request for the wrong registered participant still
    # cannot relabel the already-created Job's role and expose it.
    r=asyncio.run(e.assign('reviewer_2',lease));assert r.status_code!=200
    assert len(e.launches)==0 and economic_count(e)==before


def test_assignment_source_withdrawal_during_retained_subject_read_never_commits(evaluation,monkeypatch):
    e=evaluation
    assert asyncio.run(e.admit('reviewer_1')).status_code==200
    lease=e.create_lease('reviewer_1');before=economic_count(e)
    path=e.runtime.store.root/'data/control_plane/runs'/e.subject_lease.attempt.attempt_id/'memory-original-input'
    previous=paid_module._private_read;reads=[]
    def withdraw(selected,limit):
        result=previous(selected,limit)
        if selected==path:reads.append(True);e.faults['source']=True
        return result
    monkeypatch.setattr(paid_module,'_private_read',withdraw)
    result=asyncio.run(e.assign('reviewer_1',lease))
    assert result.status_code!=200 and reads
    assert not any(x.event_type=='MEMORY_EVALUATION_ASSIGNED' for x in e.runtime.events.list_events())
    assert e.launches==[] and economic_count(e)==before


def test_post_commit_auth_withdrawal_retains_original_and_returns_unknown(evaluation,monkeypatch):
    e=evaluation;previous=e.app._same_auth
    async def current(request,authenticated):
        live=await previous(request,authenticated)
        if any(x.event_type=='MEMORY_EVALUATOR_ADMITTED' for x in e.runtime.events.list_events()):return False
        return live
    monkeypatch.setattr(e.app,'_same_auth',current)
    response=asyncio.run(e.admit('reviewer_1'))
    assert response.status_code!=200 and response.json()['error']['code']=='effect_unknown'
    assert sum(x.event_type=='MEMORY_EVALUATOR_ADMITTED' for x in e.runtime.events.list_events())==1
    assert e.launches==[] and not any(x.event_type=='MEMORY_EVALUATION_ASSIGNED' for x in e.runtime.events.list_events())
