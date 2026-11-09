"""Manual-carrier owner joins for declared Memory participant metadata.

Bindings extend the incumbent child authorization row, never a participant or
study registry. Private operator capability authentication remains in that
owner. Reserved/selected facts never become a served actor or study admission.
Only metadata bytes are returned; no arbitrary rating/source/annotation
reference reader exists. Owned native input is hashed internally, never returned.
"""
from __future__ import annotations
import base64
import hashlib
import json
import re

SCHEMA='mastermind.fabric_participant_observation.v1'
PREFIX='research_factory.market_memory_e0_'
FLAGS=('authenticated','qualification_verified','independence_verified','exposure_verified','operational_admission')
ROLES=('principal_ref','qualification_ref','independence_ref')
HEX=re.compile(r'[a-f0-9]{64}\Z')
IDENT=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')


def fail():
 from fabric_operator_contract import DelegationRefused
 raise DelegationRefused('participant_binding_or_view_refused')


def canonical(value):
 try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
 except (ValueError,TypeError,UnicodeError,RecursionError):fail()


def sha(raw):return hashlib.sha256(raw).hexdigest()


def parse(raw,limit):
 if type(raw) is not bytes or not 1<=len(raw)<=limit:fail()
 def pairs(items):
  result={}
  for k,v in items:
   if k in result:fail()
   result[k]=v
  return result
 try:value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:fail())
 except (ValueError,TypeError,UnicodeError,RecursionError):fail()
 if canonical(value)!=raw:fail()
 return value


def validate_payload(descriptor,raw,all_reads):
 value=parse(raw,8192);role=descriptor['evidence_role']
 common={'schema','object_id','authority','study_id','participant_id','verification'}
 extra={'principal_ref':{'execution_identity'},'qualification_ref':{'declared_competencies'},
        'independence_ref':{'declared_distinct_from','prior_exposure_status','peer_ratings_visibility'}}[role]
 ref=descriptor['reference']
 if (type(value) is not dict or set(value)!=common|extra or value['schema']!=ref['schema']
     or value['object_id']!=ref['object_id'] or value['study_id']!=descriptor['study_id']
     or value['participant_id']!=descriptor['participant_id'] or value['authority']!='display_only'
     or canonical(value['verification'])!=canonical({k:False for k in FLAGS})
     or len(raw)!=ref['bytes'] or sha(raw)!=ref['sha256']):fail()
 if role=='principal_ref' and value['execution_identity'] is not None:
  x=value['execution_identity'];keys={'source_schema','attempt_id','worker_id','quota_class','provider','placement_snapshot_digest'}
  if type(x) is not dict or set(x)!=keys or x['source_schema']!='mastermind.execution_principal_snapshot/v1':fail()
  if any(type(x[k]) is not str or not IDENT.fullmatch(x[k]) for k in ('attempt_id','worker_id','quota_class')):fail()
  if type(x['provider']) is not str or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}',x['provider']):fail()
  if type(x['placement_snapshot_digest']) is not str or not HEX.fullmatch(x['placement_snapshot_digest']):fail()
 elif role=='qualification_ref':
  x=value['declared_competencies'];allowed={'source_support','contradiction_detection','material_omissions','market_context'}
  if type(x) is not list or len(x)>4 or any(type(v) is not str or v not in allowed for v in x) or len(set(x))!=len(x):fail()
 elif role=='independence_ref':
  x=value['declared_distinct_from'];others={r['participant_id'] for r in all_reads}-{descriptor['participant_id']}
  if (type(x) is not list or len(x)!=2 or any(type(v) is not str for v in x) or set(x)!=others
      or value['prior_exposure_status']!='not_established' or value['peer_ratings_visibility']!='not_established'):fail()
 return value


def prepare(owner,grant,request,participant):
 """Data validation at the real owner's prelaunch reservation boundary."""
 from participant_binding import validate_binding
 if type(participant) is not dict or set(participant)!={'binding','reviewer_plan_bytes','metadata_payloads'}:fail()
 # The actual controller sends this exact suffixed input, not a caller digest.
 from fabric_operator_owner import CHILD_SUFFIX,digest,canonical as owner_canonical
 input_digest=sha((request['packet']+CHILD_SUFFIX).encode())
 try:
  normalized=validate_binding(participant['binding'],participant['reviewer_plan_bytes'],
   expected_root=grant['root'],expected_parent=grant['operator_run'],expected_run=request['run_id'],
   expected_input_sha256=input_digest)
  binding=parse(normalized,65536) if type(normalized) is bytes else parse(canonical(normalized),65536)
 except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):fail()
 reads=binding['read_plan']['reads'];payloads=participant['metadata_payloads']
 if type(payloads) is not dict or set(payloads)!={r['reference']['object_id'] for r in reads}:fail()
 for row in reads:validate_payload(row,payloads[row['reference']['object_id']],reads)
 record={'schema':'mastermind.fabric_participant_binding_record.v1','binding':binding,
  'reviewer_plan_base64':base64.b64encode(participant['reviewer_plan_bytes']).decode(),
  'metadata':{k:base64.b64encode(v).decode() for k,v in payloads.items()},
  'request_digest':digest(owner_canonical(request).encode())}
 raw=canonical(record)
 if len(raw)>524288:fail()
 return raw.decode()


def unwrap(owner,grant,stored,*,expected_run):
 """Exact new-row envelope; legacy requests/columns remain unchanged."""
 if type(stored) is not dict or set(stored)!={'schema','request','participant'} or stored['schema']!='mastermind.fabric_bound_child_authorization.v2':fail()
 request=stored['request'];record=stored['participant']
 if (type(request) is not dict or request.get('run_id')!=expected_run or request.get('root')!=grant['root'] or request.get('parent')!=grant['operator_run']):fail()
 if type(record) is not dict or set(record)!={'schema','binding','reviewer_plan_base64','metadata','request_digest'} or record['schema']!='mastermind.fabric_participant_binding_record.v1':fail()
 if type(record['metadata']) is not dict or type(record['reviewer_plan_base64']) is not str:fail()
 if any(type(k) is not str or type(v) is not str for k,v in record['metadata'].items()):fail()
 try:
  original={'binding':record['binding'],'reviewer_plan_bytes':base64.b64decode(record['reviewer_plan_base64'],validate=True),
   'metadata_payloads':{k:base64.b64decode(v,validate=True) for k,v in record['metadata'].items()}}
 except (ValueError,TypeError,KeyError):fail()
 if prepare(owner,grant,request,original)!=canonical(record).decode():fail()
 return request,record


def load(owner,token,rid,binding_sha256):
 """Capability + same child/root/parent + immutable source/request joins."""
 import sqlite3
 from fabric_operator_owner import digest,canonical as owner_canonical
 if type(binding_sha256) is not str or not HEX.fullmatch(binding_sha256):fail()
 with owner.transaction() as con:
  grant,launch,lease,_=owner._authorized(con,token)
  row=con.execute('SELECT * FROM operator_child_authorizations WHERE run_id=? AND operator_run=? AND root=?',
   (rid,grant['operator_run'],grant['root'])).fetchone()
  if row is None:fail()
  row=dict(row)
  if type(row['request_json']) is not str or len(row['request_json'].encode())>600000:fail()
  stored=json.loads(row['request_json'])
  if owner_canonical(stored)!=row['request_json'] or row['request_digest']!=digest(owner_canonical(stored).encode()):fail()
  request,record=unwrap(owner,grant,stored,expected_run=rid)
  from fabric_operator_contract import validate_launch
  validate_launch(grant,lease,launch,request,now=owner.clock(),used_children=0,root_children_remaining=1)
  if sha(canonical(record['binding']))!=binding_sha256:fail()
  child=None
  if row['admitted_lease_id'] is not None:
   child=dict(owner.lease(con,row['admitted_lease_id']))
   if child.get('id')!=row['admitted_lease_id'] or child.get('orchestrator_id')!=grant['root']:fail()
   for key in ('pool','model','account','host'):
    if type(child.get(key)) is not str or not IDENT.fullmatch(child[key]):fail()
 return grant,row,record,child


def recheck(owner,token,rid,binding_sha256,before):
 """Fresh owner permission and immutable same-child joins before disclosure."""
 after=load(owner,token,rid,binding_sha256)
 def material(value):
  grant,row,record,child=value
  return (grant,{k:row[k] for k in ('run_id','operator_run','root','request_digest','request_json','admitted_lease_id')},record,
   None if child is None else {k:child[k] for k in ('id','orchestrator_id','pool','model','account','host')})
 if canonical(material(before))!=canonical(material(after)):fail()


def original_input(owner,grant,row,binding):
 """Read only the fixed native request/launch of this new bound operation.

 This is recorded controller input/reservation, not provider context or START.
 Old/unknown operations cannot gain this path by supplying a descriptor.
 """
 import artifact_delivery as delivery
 rid=row['run_id'];base=owner.here/'state/remote_sub'
 names=(rid+'.request.json',rid+'.request-launch.json',rid+'.request.packet')
 try:
  request_raw=delivery.local_file(base/names[0],32768)
  launch_raw=delivery.local_file(base/names[1],32768)
  from fabric_operator_owner import CHILD_SUFFIX
  packet_limit=65536+len(CHILD_SUFFIX.encode())
  packet=delivery.local_file(base/names[2],packet_limit)
 except FileNotFoundError:return None
 request=json.loads(request_raw);launch=json.loads(launch_raw)
 if type(request) is not dict or type(launch) is not dict:fail()
 if (request.get('schema')!='mastermind.fabric_request_artifact.v1'
     or launch.get('schema')!='mastermind.fabric_request_launch.v1'
     or request.get('run_id')!=rid or launch.get('run_id')!=rid
     or request.get('root_id')!=grant['root'] or launch.get('root_id')!=grant['root']
     or request.get('parent_run_id')!=grant['operator_run'] or launch.get('parent_run_id')!=grant['operator_run']
     or request.get('packet')!=names[2] or request.get('packet_sha256')!=binding['input_sha256']
     or request.get('packet_bytes')!=len(packet) or sha(packet)!=binding['input_sha256']
     or launch.get('packet_sha256')!=binding['input_sha256'] or launch.get('request_sha256')!=sha(request_raw)
     or launch.get('state')!='LAUNCH_ATTEMPT_RESERVED'):fail()
 if (delivery.local_file(base/names[0],32768)!=request_raw
     or delivery.local_file(base/names[1],32768)!=launch_raw
     or delivery.local_file(base/names[2],packet_limit)!=packet):fail()
 return {'state':'RECORDED_NATIVE_INPUT_AND_LAUNCH_RESERVATION',
  'input_sha256':sha(packet),'input_bytes':len(packet),'request_sha256':sha(request_raw),
  'launch_record_sha256':sha(launch_raw),'provider_consumption_proven':False}


def original_controller_launch(owner,grant,row,child):
 """Reuse the incumbent strict ordinary-plain retained binding validator.

 The record is source-owned prelaunch correlation inside this authenticated
 owner read, not native actor/served-model authentication or process proof.
 """
 if child is None:return None
 import artifact_delivery as delivery
 import original_delivery_collector as collector
 import remote_sub_helpers
 import fabric_task
 rid=row['run_id'];base=owner.here/'state/remote_sub'
 raw=delivery.local_file(base/(rid+'.log'),fabric_task.MAX_LOG_BYTES)
 text=remote_sub_helpers.macro_result_status_text(raw,rid)
 pattern=re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z \[remote_sub id='+re.escape(rid)+r' host='+re.escape(child['host'])+r'\] (.*)')
 events=[]
 for line in text.splitlines():
  match=pattern.fullmatch(line)
  if match is None:fail()
  events.append(match[1])
 records=[x[len('LAUNCH_BINDING '):] for x in events if x.startswith('LAUNCH_BINDING ')]
 if not records:return None
 if len(records)!=1:fail()
 record=collector.reader.strict_json(records[0].encode())
 if type(record) is not dict:fail()
 if record.get('schema') not in (collector.PLAIN_BINDING_SCHEMA,collector.PLAIN_BINDING_SCHEMA_V2,collector.PLAIN_BINDING_SCHEMA_V3):return None
 if (record.get('lease_id')!=child['id'] or record.get('account')!=child['account']
     or record.get('host')!=child['host'] or record.get('requested_model')!=child['model']
     or record.get('acquisition_pool',record.get('pool'))!=child['pool']):fail()
 from fabric_operator_owner import CHILD_SUFFIX
 packet_limit=65536+len(CHILD_SUFFIX.encode())
 packet=delivery.local_file(base/(rid+'.request.packet'),packet_limit)
 value={'run_id':rid,'root':grant['root'],'parent':grant['operator_run'],'host':child['host'],
  'mode':record.get('mode'),'requested_model':child['model'],'artifact_names':[]}
 try:checked=collector.retained_plain_binding(events,value,{'log':raw,'packet':packet})
 except (ValueError,TypeError,KeyError):fail()
 if checked is None:return None
 if delivery.local_file(base/(rid+'.log'),fabric_task.MAX_LOG_BYTES)!=raw or delivery.local_file(base/(rid+'.request.packet'),packet_limit)!=packet:fail()
 return {k:checked[k] for k in ('lease_id','account','host','mode','requested_model','packet_sha256','support_digest','acquire_response_sha256','binding_sha256')} | {
  'controller_attempt':1,'worker_start_proven':False,'served_identity_proven':False}


def observation(owner,token,rid,binding_sha256):
 grant,row,record,child=load(owner,token,rid,binding_sha256)
 import fabric_task
 binding=record['binding'];role=binding['participant_role']
 reads=[r for r in binding['read_plan']['reads'] if r['participant_role']==role]
 # Retain state from the actual existing owner reader, never a supplied DTO.
 before=fabric_task.inspect_run(rid,owner_ext=owner.here)
 result=None
 unresolved=before.get('state')=='EFFECT_UNKNOWN'
 withheld=before.get('state') in ('EFFECT_UNKNOWN','STATUS_UNREADABLE')
 original=None if withheld else original_input(owner,grant,row,binding)
 launch=None if withheld or original is None else original_controller_launch(owner,grant,row,child)
 if (child is not None and original is not None and before.get('state')=='TERMINAL' and before.get('rc')==0 and before.get('signal')=='ok'
     and before.get('result_available') is True):
  if before.get('root_id')!=grant['root'] or before.get('parent_run_id')!=grant['operator_run']:fail()
  path=fabric_task._paths(rid,owner_ext=owner.here)[1]
  raw=fabric_task._bounded_regular(path,65536)
  if fabric_task.inspect_run(rid,owner_ext=owner.here)!=before or fabric_task._bounded_regular(path,65536)!=raw:fail()
  result={'sha256':sha(raw),'bytes':len(raw),'content_returned':False}
 recheck(owner,token,rid,binding_sha256,(grant,row,record,child))
 # No provider-served principal or all-channel blinding producer currently
 # exists in this owner. These explicit gaps cannot be supplied by the caller.
 return {'schema':SCHEMA,'source_owner':'MANUAL_FABRIC_OPERATOR_OWNER','root':grant['root'],
  'actual_parent':grant['operator_run'],'parent_kind':'MANUAL_FABRIC_OPERATOR_RUN',
  'native_parent_authenticated':False,'run_id':rid,'binding_sha256':binding_sha256,
  'scope':binding['scope'],'participant_role':role,'participant_id':reads[0]['participant_id'],
  'metadata_references':[r['reference'] for r in reads],
  'reserved_input_sha256':binding['input_sha256'],'request_digest':row['request_digest'],
  'recorded_native_input':original,'recorded_controller_launch':launch,
  'admitted_child_selection':None if child is None else {
   'lease_id':child['id'],'pool':child['pool'],'selected_model':child['model'],
   'selected_account':child['account'],'host':child['host'],
   'fact_source':'RETAINED_ADMITTED_CHILD_LEASE_ROW','provider_account_authentication':'NOT_OBSERVED'},
  'retained_result':result,'observed_state':before.get('state'),
  'unresolved_original_effect':unresolved,'original_observation_withheld':withheld,
  'fact_states':{'broker_child_selection':'RECORDED' if child is not None else 'NOT_OBSERVED',
   'native_input_reservation':'RECORDED' if original is not None else 'NOT_OBSERVED',
   'controller_attempt':'RECORDED' if launch is not None else 'NOT_OBSERVED',
   'remote_process_birth':'NOT_OBSERVED','provider_turn':'NOT_OBSERVED','served_identity':'NOT_OBSERVED',
   'stable_result_integrity':'RETAINED_UNTRUSTED_BYTES' if result is not None else 'NOT_OBSERVED'},
  'served_principal':None,'served_model':None,'execution_attempt':None,
  'origin_authentication':'OWNER_CAPABILITY_AND_CHILD_CUSTODY_ONLY',
  'view_policy':'OWN_DECLARED_METADATA_ONLY_NO_RATING_READS',
  'remaining_boundaries':['SERVED_PARTICIPANT_ORIGIN_NOT_OBSERVED','FULL_INPUT_EXPOSURE_ISOLATION_NOT_ATTESTED','RETAINED_DISAGREEMENT_OWNER_NOT_JOINED'],
  'scientific_admission':False,'execution_replayed':False,'retry_authorized':False}


def metadata(owner,token,rid,binding_sha256,object_id):
 snapshot=load(owner,token,rid,binding_sha256)
 _,_,record,_=snapshot
 binding=record['binding'];role=binding['participant_role']
 # No caller boolean/ref may advance an adjudicator to a disagreement stage.
 if role=='adjudicator':fail()
 reads=[r for r in binding['read_plan']['reads'] if r['participant_role']==role and r['reference']['object_id']==object_id]
 if len(reads)!=1:fail()
 raw=base64.b64decode(record['metadata'][object_id],validate=True)
 value=validate_payload(reads[0],raw,binding['read_plan']['reads'])
 recheck(owner,token,rid,binding_sha256,snapshot)
 return {'schema':'mastermind.fabric_participant_metadata_view.v1','binding_sha256':binding_sha256,
  'scope':binding['scope'],'descriptor':reads[0],'metadata':value,
  'view_policy':'OWN_DECLARED_METADATA_ONLY_NO_RATING_READS','scientific_admission':False,
  'retry_authorized':False}
