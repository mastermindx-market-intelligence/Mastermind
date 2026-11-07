"""Actual incumbent owner/SQLite + exact accepted Memory source, all inert.

No production broker, capability, task, participant, source/rating, dispatch or
study is accessed. A valid fixture still cannot authenticate a served actor.
"""
import copy,hashlib,importlib.util,json,sqlite3,sys,tempfile
from pathlib import Path
from unittest import mock
import pytest

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/'ops/native_fabric/quota_continuity'
sys.path[:0]=[str(NATIVE/'candidate'),str(NATIVE/'source')]
import fabric_operator_owner as owner_module
import fabric_participant_owner as port
import fabric_task

FIXTURE=ROOT/'tests/fixtures/market-memory-owner-contract'
spec=importlib.util.spec_from_file_location('_exact_memory_v2',FIXTURE/'engine/research_factory/market_memory_e0_review_metadata_v2.py')
memory=importlib.util.module_from_spec(spec);spec.loader.exec_module(memory)
canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

@pytest.fixture
def case(request):
 # The real DirectoryChain rejects every writable ancestor, including Linux
 # /tmp. Keep this inert state below the same owned home fixture root used by
 # the incumbent native tests; never relax or chmod a production ancestor.
 temporary=tempfile.TemporaryDirectory(prefix='.fabric-participant-',dir=Path.home().resolve(strict=True))
 request.addfinalizer(temporary.cleanup)
 here=Path(temporary.name)/'inert';(here/'broker').mkdir(parents=True,mode=0o700);(here/'broker/leases.lock').touch(mode=0o600)
 (here/'state/remote_sub').mkdir(parents=True);(here/'lanes').mkdir(mode=0o700)
 owner=owner_module.OperatorOwner(here=here,clock=lambda:1000.)
 lease=dict(id='inert-parent-lease',orchestrator_id='inert-root',pool='glm-frontier',account='parent-account',task_class='remote-glm',model='glm-5.3',host='parent-host',pid=123,granted_at=990.,ttl=180,last_heartbeat=999.,state='held',renewable=1)
 with sqlite3.connect(owner.db) as con:
  con.execute('CREATE TABLE leases ('+', '.join(k+' '+('REAL' if type(v) is float else 'INTEGER' if type(v) is int else 'TEXT') for k,v in lease.items())+')')
  con.execute('INSERT INTO leases VALUES ('+','.join('?' for _ in lease)+')',tuple(lease.values()))
 owner.db.chmod(0o600);owner.authorize_root('inert-root',3,2200.)
 launch=dict(root='inert-root',run_id='inert-operator',lease_id='inert-parent-lease',pool='glm-frontier',model='glm-5.3',account='parent-account',host='parent-host',support_sha256='a'*64,packet_sha256='b'*64,task_class='domain_orchestration')
 cap=owner.issue(launch,2)
 request=dict(schema='mastermind.fabric_operator_child_request.v1',root='inert-root',parent='inert-operator',run_id='inert-child',task_class='mechanical',task_complexity='C0_MECHANICAL',packet='INERT_CASE_INPUT_NO_RATINGS')
 return dict(owner=owner,here=here,cap=cap,request=request,lease=lease,launch=launch)


def participant(case,role='reviewer_1',slot=2):
 flags={k:False for k in memory._FLAGS};ids=['inert-p1','inert-p2','inert-p3'];bodies={};participants=[]
 for pid in ids:
  participant={}
  for evidence_role in memory.ROLES:
   object_id=pid if evidence_role=='principal_ref' else pid+'-'+evidence_role
   value=dict(schema=memory.ROLE_SCHEMAS[evidence_role],object_id=object_id,authority='display_only',study_id='inert-study',participant_id=pid,verification=flags)
   if evidence_role=='principal_ref':value['execution_identity']=None
   elif evidence_role=='qualification_ref':value['declared_competencies']=['source_support']
   else:value.update(declared_distinct_from=[p for p in ids if p!=pid],prior_exposure_status='not_established',peer_ratings_visibility='not_established')
   raw=canonical(value);bodies[object_id]=raw
   participant[evidence_role]=dict(schema=value['schema'],object_id=object_id,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
  participants.append(participant)
 schema=json.loads((FIXTURE/'contracts/market_memory/e0_reviewer_plan.v1.schema.json').read_bytes())
 plan=dict(schema=memory.PLAN_SCHEMA,object_id='inert-plan',authority='display_only',study_id='inert-study',preregistered_at='2026-11-01T00:00:00Z',
  protocol_sha256=schema['properties']['protocol_sha256']['const'],annotation_guide_sha256=schema['properties']['annotation_guide_sha256']['const'],membership_sha256=schema['properties']['membership_sha256']['const'],
  tasks_ref=dict(schema='research_factory.market_memory_e0_tasks.v1',object_id='inert-tasks',sha256='c'*64,bytes=20),reviewers=participants[:2],adjudicator=participants[2],assignments=[dict(task_id='inert-task',reviewer_principal_ids=ids[:2],adjudicator_principal_id=ids[2])],
  blinding={k:v['const'] for k,v in schema['$defs']['blinding']['properties'].items()})
 raw=canonical(plan)
 scope=dict(schema=memory.SCOPE_SCHEMA,authority='display_only',owner_contract=memory.OWNER_CONTRACT,action=memory.ACTION,study_id='inert-study',task_id='inert-task',slot=slot,
  reviewer_plan_ref=dict(schema=memory.PLAN_SCHEMA,object_id='inert-plan',sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)))
 read_plan=memory.plan_review_metadata_reads(scope,raw)
 binding=dict(schema='mastermind.fabric_memory_participant_binding.v1',root='inert-root',parent='inert-operator',run_id='inert-child',input_sha256=hashlib.sha256((case['request']['packet']+owner_module.CHILD_SUFFIX).encode()).hexdigest(),scope=scope,read_plan=read_plan,participant_role=role)
 return dict(binding=binding,reviewer_plan_bytes=raw,metadata_payloads=bodies)


def reserve(case,role='reviewer_1',slot=2):
 p=participant(case,role,slot);case['owner'].reserve(case['cap']['token'],case['request'],participant=p)
 return p,hashlib.sha256(canonical(p['binding'])).hexdigest()


def test_accepted_memory_public_contract_fixtures_are_byte_exact():
 manifest=json.loads((FIXTURE/'SOURCE.json').read_bytes())
 assert manifest['repository']=='mastermindx-market-intelligence/macro'
 assert manifest['commit']=='a6c07e2d3a6e26076fbeabbce409e135582c9f75'
 assert set(manifest['files'])=={
  'engine/research_factory/market_memory_e0_review_metadata_v2.py',
  'contracts/market_memory/e0_review_metadata.v2.schema.json',
  'contracts/market_memory/e0_reviewer_plan.v1.schema.json'}
 for name,item in manifest['files'].items():
  raw=(FIXTURE/name).read_bytes()
  assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']

def test_inert_fixture_preserves_real_directory_chain_ancestor_guard(case):
 import artifact_delivery as delivery
 with delivery.DirectoryChain(case['here']):pass
 unsafe=case['here']/'intentionally-unsafe-fixture';unsafe.mkdir();unsafe.chmod(0o1777)
 try:
  with pytest.raises(ValueError,match='directory_owner_or_mode'):
   with delivery.DirectoryChain(unsafe):pass
 finally:unsafe.chmod(0o700)

def test_unbound_old_child_cannot_be_backfilled_or_read(case):
 o=case['owner'];o.reserve(case['cap']['token'],case['request'])
 with mock.patch.object(fabric_task,'inspect_run',side_effect=AssertionError('must not read original')):
  with pytest.raises(owner_module.DelegationRefused):o.participant_observation(case['cap']['token'],'inert-child','a'*64)


def test_wrong_capability_fails_before_any_original_or_codec(case):
 with mock.patch.object(fabric_task,'inspect_run',side_effect=AssertionError('must not read original')):
  with pytest.raises(owner_module.DelegationRefused):case['owner'].participant_observation('0'*64,'inert-child','a'*64)


@pytest.mark.parametrize('role',['reviewer_1','reviewer_2'])
@pytest.mark.parametrize('slot',[0,1,2])
def test_genuine_memory_source_to_owner_metadata_join_stays_declared(case,role,slot):
 p,digest=reserve(case,role,slot);o=case['owner']
 read=next(r for r in p['binding']['read_plan']['reads'] if r['participant_role']==role and r['evidence_role']=='principal_ref')
 value=o.participant_metadata(case['cap']['token'],'inert-child',digest,read['reference']['object_id'])
 checked=memory.validate_review_metadata_payload(p['binding']['scope'],p['reviewer_plan_bytes'],value['descriptor'],canonical(value['metadata']))
 assert checked['metadata']==value['metadata'] and all(v is False for v in checked['verification'].values())
 assert checked['native_v2_owner_read_support']=='not_implemented' and value['scientific_admission'] is False
 assert value['scope']['slot']==slot and value['descriptor']['participant_role']==role


@pytest.mark.parametrize('target',['inert-p2','peer-provisional-rating','private-source-ref','../../rating'])
def test_role_view_never_follows_peer_rating_or_arbitrary_ref(case,target):
 _,digest=reserve(case)
 with pytest.raises(owner_module.DelegationRefused):case['owner'].participant_metadata(case['cap']['token'],'inert-child',digest,target)


def test_adjudicator_cannot_be_advanced_by_declared_blinding_or_caller_flag(case):
 _,digest=reserve(case,'adjudicator')
 with pytest.raises(owner_module.DelegationRefused):case['owner'].participant_metadata(case['cap']['token'],'inert-child',digest,'inert-p3')


def test_caller_metadata_cannot_inject_a_rating_or_true_flag(case):
 for change in ('rating','verification'):
  p=participant(case);x=json.loads(p['metadata_payloads']['inert-p1'])
  if change=='rating':x['peer_provisional_ratings']=[42]
  else:x['verification']['authenticated']=True
  p['metadata_payloads']['inert-p1']=canonical(x)
  before=case['owner'].describe(case['cap']['token'])
  with pytest.raises(owner_module.DelegationRefused):case['owner'].reserve(case['cap']['token'],case['request'],participant=p)
  assert case['owner'].describe(case['cap']['token'])==before


def test_parent_selection_is_not_child_served_identity(case):
 _,digest=reserve(case);o=case['owner'];value=o.participant_observation(case['cap']['token'],'inert-child',digest)
 assert value['admitted_child_selection'] is None and value['served_model'] is None and value['served_principal'] is None
 assert value['retained_result'] is None and value['scientific_admission'] is False
 assert 'parent-account' not in json.dumps(value)


def test_actual_child_broker_row_is_separate_from_parent_selection(case):
 _,digest=reserve(case);o=case['owner'];child=dict(case['lease'],id='inert-child-lease',account='child-account',model='child-model',host='child-host')
 with sqlite3.connect(o.db) as con:
  con.execute('INSERT INTO leases VALUES ('+','.join('?' for _ in child)+')',tuple(child.values()))
  con.execute('UPDATE operator_child_authorizations SET admitted_lease_id=? WHERE run_id=?',('inert-child-lease','inert-child'))
 value=o.participant_observation(case['cap']['token'],'inert-child',digest)
 assert value['admitted_child_selection']['selected_account']=='child-account' and value['admitted_child_selection']['selected_model']=='child-model'
 assert value['served_model'] is None and value['scientific_admission'] is False


@pytest.mark.parametrize('fault',['root','parent','run','input','slot'])
def test_binding_mismatch_refuses_before_authorization_or_dispatch(case,fault):
 p=participant(case)
 if fault=='input':p['binding']['input_sha256']='0'*64
 elif fault=='slot':p['binding']['scope']['slot']=True
 else:p['binding'][{'run':'run_id'}.get(fault,fault)]='foreign'
 before=case['owner'].describe(case['cap']['token'])
 with pytest.raises(owner_module.DelegationRefused):case['owner'].reserve(case['cap']['token'],case['request'],participant=p)
 assert case['owner'].describe(case['cap']['token'])==before


def test_reserved_binding_and_all_metadata_are_detached(case):
 p,digest=reserve(case);p['binding']['scope']['slot']=0;p['metadata_payloads'].clear()
 value=case['owner'].participant_metadata(case['cap']['token'],'inert-child',digest,'inert-p1')
 assert value['scope']['slot']==2 and value['metadata']['participant_id']=='inert-p1'


def test_foreign_child_broker_root_refuses(case):
 _,digest=reserve(case);o=case['owner'];child=dict(case['lease'],id='inert-child-lease',orchestrator_id='foreign')
 with sqlite3.connect(o.db) as con:
  con.execute('INSERT INTO leases VALUES ('+','.join('?' for _ in child)+')',tuple(child.values()))
  con.execute('UPDATE operator_child_authorizations SET admitted_lease_id=? WHERE run_id=?',('inert-child-lease','inert-child'))
 with pytest.raises(owner_module.DelegationRefused):o.participant_observation(case['cap']['token'],'inert-child',digest)


def complete_inert_child(case):
 o=case['owner'];rid=case['request']['run_id'];child=dict(case['lease'],id='inert-child-lease',account='child-account',model='child-model',host='child-host')
 with sqlite3.connect(o.db) as con:
  con.execute('INSERT INTO leases VALUES ('+','.join('?' for _ in child)+')',tuple(child.values()))
  con.execute('UPDATE operator_child_authorizations SET admitted_lease_id=? WHERE run_id=?',(child['id'],rid))
 state=o.here/'state/remote_sub';packet=(case['request']['packet']+owner_module.CHILD_SUFFIX).encode()
 request=dict(schema='mastermind.fabric_request_artifact.v1',run_id=rid,root_id='inert-root',parent_run_id='inert-operator',task_class='mechanical',cwd='~',packet=rid+'.request.packet',packet_sha256=hashlib.sha256(packet).hexdigest(),packet_bytes=len(packet),created_at=999.,automatic_background_execution=False)
 raw=canonical(request);launch=dict(schema='mastermind.fabric_request_launch.v1',run_id=rid,root_id='inert-root',parent_run_id='inert-operator',packet_sha256=hashlib.sha256(packet).hexdigest(),state='LAUNCH_ATTEMPT_RESERVED',created_at=999.,request_sha256=hashlib.sha256(raw).hexdigest())
 for name,body in [(rid+'.request.packet',packet),(rid+'.request.json',raw),(rid+'.request-launch.json',canonical(launch)),(rid+'.log',('2026-11-05T00:00Z [remote_sub id='+rid+' host=child-host] DONE rc=0 signal=ok\n').encode())]:
  p=state/name;p.write_bytes(body);p.chmod(0o600)
 result=fabric_task._paths(rid,owner_ext=o.here)[1];result.write_bytes(b'INERT_RESULT_NO_RATING_BODY');result.chmod(0o600)
 ledger=o.here.parent/'orch/fabric/ledger.jsonl';ledger.parent.mkdir(parents=True)
 row=dict(kind='terminal_publication',ts=1,run_id=rid,root_id='inert-root',parent_run_id='inert-operator',pool='fixture-pool',key='fixture-account',window_id='fixture-window',task_class='mechanical',model='fixture-model',rc=0,signal='ok')
 ledger.write_bytes(canonical(row)+b'\n');ledger.chmod(0o600)
 return state,result,ledger


def test_real_retained_native_request_and_stable_result_join(case):
 p,digest=reserve(case);state,result,_=complete_inert_child(case)
 # Actual incumbent inspector/ledger/result readers, no fabricated callback.
 value=case['owner'].participant_observation(case['cap']['token'],'inert-child',digest)
 assert value['observed_state']=='TERMINAL'
 assert value['recorded_native_input']['input_sha256']==p['binding']['input_sha256']
 assert value['retained_result']==dict(sha256=hashlib.sha256(result.read_bytes()).hexdigest(),bytes=result.stat().st_size,content_returned=False)
 assert b'INERT_RESULT_NO_RATING_BODY' not in canonical(value)
 assert value['served_model'] is None and value['scientific_admission'] is False


@pytest.mark.parametrize('fault',['request-root','request-parent','packet','launch-request','result-parent'])
def test_original_request_launch_result_substitution_refuses(case,fault):
 _,digest=reserve(case);state,_,ledger=complete_inert_child(case)
 if fault=='packet':(state/'inert-child.request.packet').write_bytes(b'FOREIGN')
 elif fault=='result-parent':
  x=json.loads(ledger.read_bytes());x['parent_run_id']='foreign';ledger.write_bytes(canonical(x)+b'\n')
 else:
  path=state/('inert-child.request-launch.json' if fault=='launch-request' else 'inert-child.request.json');x=json.loads(path.read_bytes())
  x[{'request-root':'root_id','request-parent':'parent_run_id','launch-request':'request_sha256'}[fault]]='foreign';path.write_bytes(canonical(x))
 with pytest.raises(owner_module.DelegationRefused):case['owner'].participant_observation(case['cap']['token'],'inert-child',digest)


def test_unknown_original_effect_prevents_native_input_or_result_read(case,monkeypatch):
 _,digest=reserve(case);state,_,_=complete_inert_child(case)
 (state/'inert-child.log').write_text('2026-11-05T00:00Z [remote_sub id=inert-child host=child-host] REMOTE_EFFECT_UNKNOWN\n')
 with mock.patch.object(port,'original_input',side_effect=AssertionError('must not read original input')):
  value=case['owner'].participant_observation(case['cap']['token'],'inert-child',digest)
 assert value['unresolved_original_effect'] is True and value['retained_result'] is None and value['recorded_native_input'] is None


@pytest.mark.parametrize('stage',['selected','launch_attempt','poll_pending','claimed_process_birth','claimed_provider_turn','stable_result'])
def test_lifecycle_selection_attempt_birth_turn_identity_and_result_are_distinct(case,stage):
 _,digest=reserve(case)
 if stage=='stable_result':complete_inert_child(case)
 else:
  o=case['owner'];child=dict(case['lease'],id='inert-child-lease',account='child-account',model='child-model',host='child-host')
  with sqlite3.connect(o.db) as con:
   con.execute('INSERT INTO leases VALUES ('+','.join('?' for _ in child)+')',tuple(child.values()))
   con.execute('UPDATE operator_child_authorizations SET admitted_lease_id=? WHERE run_id=?',('inert-child-lease','inert-child'))
  events=['LEASE_OK pool=glm']
  if stage!='selected':events.append('LAUNCH_ATTEMPT attempt=1')
  if stage=='poll_pending':events.append('POLL_PENDING poll=1')
  if stage=='claimed_process_birth':events.append('REMOTE_PROCESS_BIRTH pid=123')
  if stage=='claimed_provider_turn':events.append('PROVIDER_TURN model=declared-model')
  (o.here/'state/remote_sub/inert-child.log').write_text(''.join('2026-11-05T00:00Z [remote_sub id=inert-child host=child-host] '+x+'\n' for x in events))
 value=case['owner'].participant_observation(case['cap']['token'],'inert-child',digest)
 assert value['fact_states']['broker_child_selection']=='RECORDED'
 assert value['fact_states']['remote_process_birth']==value['fact_states']['provider_turn']==value['fact_states']['served_identity']=='NOT_OBSERVED'
 assert value['served_model'] is None and value['served_principal'] is None and value['execution_attempt'] is None
 assert value['scientific_admission'] is False
 if stage=='stable_result':assert value['fact_states']['stable_result_integrity']=='RETAINED_UNTRUSTED_BYTES'
 else:assert value['fact_states']['stable_result_integrity']=='NOT_OBSERVED'


def test_versioned_row_preserves_real_old_writer_and_new_broker_admission(case):
 reserve(case);o=case['owner']
 with o.transaction() as con:
  assert len(list(con.execute('PRAGMA table_info(operator_child_authorizations)')))==8
  owner_module.validate_child_admission(con,'inert-child','inert-root',now=1000.)
 path=NATIVE/'source/fabric_operator_owner.py'
 spec=importlib.util.spec_from_file_location('_legacy_eight_column_owner',path)
 legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
 old=legacy.OperatorOwner(here=o.here,clock=lambda:1000.)
 old.reserve(case['cap']['token'],dict(case['request'],run_id='inert-legacy-child'))
 with o.transaction() as con:
  assert len(list(con.execute('PRAGMA table_info(operator_child_authorizations)')))==8
  owner_module.validate_child_admission(con,'inert-legacy-child','inert-root',now=1000.)
  # An unupgraded receiver rejects the new row before any broker admission;
  # it does not reinterpret participant data or block ordinary old rows.
  with pytest.raises(owner_module.DelegationRefused):legacy.validate_child_admission(con,'inert-child','inert-root',now=1000.)


@pytest.mark.parametrize('fault',['run','parent','root','binding-digest','request-digest'])
def test_private_stored_authorization_substitution_does_not_authenticate(case,fault):
 _,digest=reserve(case);o=case['owner']
 with sqlite3.connect(o.db) as con:
  row=con.execute('SELECT request_json FROM operator_child_authorizations WHERE run_id=?',('inert-child',)).fetchone();x=json.loads(row[0])
  if fault in ('run','parent','root'):x['request'][{'run':'run_id'}.get(fault,fault)]='foreign'
  elif fault=='binding-digest':x['participant']['binding']['input_sha256']='0'*64
  else:x['participant']['request_digest']='0'*64
  raw=owner_module.canonical(x)
  con.execute('UPDATE operator_child_authorizations SET request_json=?,request_digest=? WHERE run_id=?',(raw,hashlib.sha256(raw.encode()).hexdigest(),'inert-child'))
 with mock.patch.object(fabric_task,'inspect_run',side_effect=AssertionError('must refuse before original read')):
  with pytest.raises(owner_module.DelegationRefused):o.participant_observation(case['cap']['token'],'inert-child',digest)


def test_read_permission_revoked_during_actual_observation_does_not_disclose(case,monkeypatch):
 _,digest=reserve(case);complete_inert_child(case)
 real=fabric_task.inspect_run
 def revoke(*a,**kw):
  result=real(*a,**kw);case['owner'].clock=lambda:2300.;return result
 monkeypatch.setattr(fabric_task,'inspect_run',revoke)
 with pytest.raises(owner_module.DelegationRefused):case['owner'].participant_observation(case['cap']['token'],'inert-child',digest)


def test_child_selection_changed_during_observation_does_not_disclose(case,monkeypatch):
 _,digest=reserve(case);complete_inert_child(case)
 real=fabric_task.inspect_run;calls=[]
 def swap(*a,**kw):
  value=real(*a,**kw)
  if not calls:
   calls.append(True)
   with sqlite3.connect(case['owner'].db) as con:con.execute('UPDATE leases SET account=? WHERE id=?',('foreign-account','inert-child-lease'))
  return value
 monkeypatch.setattr(fabric_task,'inspect_run',swap)
 with pytest.raises(owner_module.DelegationRefused):case['owner'].participant_observation(case['cap']['token'],'inert-child',digest)


@pytest.mark.parametrize('fault',['read-plan-verified','permission-verified','extra-auth-flag','duplicate-ref','plan-policy'])
def test_declarations_and_plan_builder_cannot_mint_owner_facts(case,fault):
 p=participant(case)
 if fault=='read-plan-verified':p['binding']['read_plan']['verification']['authenticated']=True
 elif fault=='permission-verified':p['binding']['read_plan']['installed_permission']='verified'
 elif fault=='extra-auth-flag':p['binding']['provider_start_proven']=True
 elif fault=='duplicate-ref':p['binding']['read_plan']['reads'][1]['reference']=p['binding']['read_plan']['reads'][0]['reference']
 else:
  plan=json.loads(p['reviewer_plan_bytes']);plan['blinding']['peer_provisional_ratings_visible']=True;p['reviewer_plan_bytes']=canonical(plan)
 before=case['owner'].describe(case['cap']['token'])
 with pytest.raises(owner_module.DelegationRefused):case['owner'].reserve(case['cap']['token'],case['request'],participant=p)
 assert case['owner'].describe(case['cap']['token'])==before


def real_inert_controller_binding(case):
 import remote_sub_helpers as helpers
 o=case['owner'];rid='inert-child';state,_,_=complete_inert_child(case)
 child_id='a'*12;model='glm-5.3-flash'
 with sqlite3.connect(o.db) as con:
  con.execute('UPDATE leases SET id=?,pool=?,model=? WHERE id=?',(child_id,'glm',model,'inert-child-lease'))
  con.execute('UPDATE operator_child_authorizations SET admitted_lease_id=? WHERE run_id=?',(child_id,rid))
 packet=(state/(rid+'.request.packet')).read_bytes();files={'inert_source.py':'d'*64}
 support=hashlib.sha256(json.dumps({'schema':'remote-support-code.v1','files':files},sort_keys=True,separators=(',',':')).encode()).hexdigest()
 acquire=b'LEASE='+child_id.encode()+b' ACCOUNT=child-account\n';acquire_path=state/'inert-acquire';acquire_path.write_bytes(acquire);acquire_path.chmod(0o600)
 policy='e'*64;packet_sha=hashlib.sha256(packet).hexdigest();acquire_sha=hashlib.sha256(acquire).hexdigest()
 receipt=dict(schema=helpers.TRANSPORT_RECEIPT_SCHEMA,run_id=rid,host='child-host',mode='glm',requested_model=model,
  packet_sha256=packet_sha,support_digest=support,policy_sha256=policy,files=files,lease_id=child_id,account='child-account',acquire_response_sha256=acquire_sha,phase='PRE_LAUNCH',verified_at='2026-11-05T00:00Z',acquisition_pool='glm',lane_root=None)
 receipt_path=state/'inert-transport.json';receipt_path.write_bytes(canonical(receipt));receipt_path.chmod(0o600)
 prefix='2026-11-05T00:00Z [remote_sub id='+rid+' host=child-host] '
 events=['RUN_RESERVED explicit=1','LEASE_OK pool=glm','SUPPORT_VERSION_READY digest='+support+' policy='+policy,
  'TRANSPORT_VERIFIED packet='+packet_sha+' support='+support+' policy='+policy+' lease='+child_id+' account=child-account acquire='+acquire_sha]
 log=state/(rid+'.log');log.write_text(''.join(prefix+x+'\n' for x in events));log.chmod(0o600)
 # Real incumbent producer, inert transport/acquire bytes only. No SSH,
 # process/provider START, credentials, current source or real lease exists.
 helpers.record_launch_binding(log,state/(rid+'.request.packet'),acquire_path,run_id=rid,root='inert-root',parent='inert-operator',host='child-host',mode='glm',model=model,support_digest=support,launch_lease_id=child_id,launch_account='child-account',acquisition_pool='glm',transport_receipt=receipt_path)
 with log.open('a') as f:
  for event in ['LAUNCH stdout=lanes_'+rid+'.stdout rc_file=ext/lanes_'+rid+'.rc cwd=~','LAUNCH_ATTEMPT attempt=1','DONE rc=0 signal=ok']:f.write(prefix+event+'\n')
 return log


def test_actual_incumbent_launch_producer_and_reader_join_without_start_promotion(case):
 _,digest=reserve(case);real_inert_controller_binding(case)
 value=case['owner'].participant_observation(case['cap']['token'],'inert-child',digest)
 launch=value['recorded_controller_launch'];assert launch['lease_id']=='a'*12 and launch['account']=='child-account'
 assert launch['controller_attempt']==1 and launch['worker_start_proven'] is False and launch['served_identity_proven'] is False
 assert value['fact_states']['controller_attempt']=='RECORDED'
 assert value['fact_states']['provider_turn']==value['fact_states']['served_identity']=='NOT_OBSERVED'
 assert value['scientific_admission'] is False


@pytest.mark.parametrize('fault',['account','model','lease','foreign-line','duplicate-attempt'])
def test_foreign_or_changed_original_launch_cannot_qualify_the_child(case,fault):
 _,digest=reserve(case);log=real_inert_controller_binding(case);text=log.read_text()
 if fault=='account':text=text.replace('"account":"child-account"','"account":"foreign-account"')
 elif fault=='model':text=text.replace('"requested_model":"glm-5.3-flash"','"requested_model":"foreign-model"')
 elif fault=='lease':text=text.replace('"lease_id":"'+('a'*12)+'"','"lease_id":"'+('b'*12)+'"')
 elif fault=='foreign-line':text+='2026-11-05T00:00Z [remote_sub id=foreign host=child-host] LAUNCH_ATTEMPT attempt=1\n'
 else:text+='2026-11-05T00:00Z [remote_sub id=inert-child host=child-host] LAUNCH_ATTEMPT attempt=1\n'
 log.write_text(text)
 with pytest.raises(owner_module.DelegationRefused):case['owner'].participant_observation(case['cap']['token'],'inert-child',digest)
