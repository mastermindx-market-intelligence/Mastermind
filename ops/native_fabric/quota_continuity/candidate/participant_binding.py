"""Closed data-only Memory-v2 to manual-owner binding compatibility codec.

Wire source: macro a6c07e2d3a6e26076fbeabbce409e135582c9f75. This
validates immutable declarations, never origin, qualification or admission.
No filesystem, reader callback, provider, broker or participant is consulted.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime

PREFIX='research_factory.market_memory_e0_'
ROLES=('principal_ref','qualification_ref','independence_ref')
PARTICIPANTS=('reviewer_1','reviewer_2','adjudicator')
FLAGS=('authenticated','qualification_verified','independence_verified','exposure_verified','operational_admission')
ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
SHA=re.compile(r'[a-f0-9]{64}\Z')


class BindingRefused(ValueError):pass


def fail():raise BindingRefused('participant_binding_invalid')


def canonical(value,limit=524288):
 pending=[(value,0)];count=0;minimum_bytes=0
 while pending:
  v,depth=pending.pop();count+=1
  minimum_bytes+=2
  if minimum_bytes>limit:fail()
  if count>20000 or depth>16:fail()
  t=type(v)
  if t is dict:
   if len(v)>512 or any(type(k) is not str or len(k)>128 for k in v):fail()
   try:minimum_bytes+=sum(len(k.encode())+3 for k in v)
   except UnicodeError:fail()
   if minimum_bytes>limit:fail()
   pending.extend((x,depth+1) for x in v.values())
  elif t is list:
   if len(v)>512:fail()
   pending.extend((x,depth+1) for x in v)
  elif t is str:
   if len(v)>min(limit,262144):fail()
   try:minimum_bytes+=len(v.encode())
   except UnicodeError:fail()
   if minimum_bytes>limit:fail()
  elif t is int:
   if v.bit_length()>64:fail()
  elif t is not bool and v is not None:fail()
 try:raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
 except (ValueError,TypeError,UnicodeError,RecursionError):fail()
 if len(raw)>limit:fail()
 return raw


def parse(raw,limit):
 if type(raw) is not bytes or not 1<=len(raw)<=limit:fail()
 def unique(items):
  out={}
  for k,v in items:
   if k in out:fail()
   out[k]=v
  return out
 try:value=json.loads(raw.decode(),object_pairs_hook=unique,parse_constant=lambda _:fail())
 except (ValueError,UnicodeError,RecursionError):fail()
 if canonical(value,limit)!=raw:fail()
 return value


def keys(value,expected):
 if type(value) is not dict or set(value)!=set(expected):fail()


def ident(value):
 if type(value) is not str or not ID.fullmatch(value):fail()


def ref(value,schema,limit):
 keys(value,('schema','object_id','sha256','bytes'));ident(value['object_id'])
 if value['schema']!=schema or type(value['sha256']) is not str or not SHA.fullmatch(value['sha256']):fail()
 if type(value['bytes']) is not int or not 1<=value['bytes']<=limit:fail()


def derive(scope,raw):
 keys(scope,('schema','authority','owner_contract','action','study_id','task_id','slot','reviewer_plan_ref'))
 for k in ('study_id','task_id'):ident(scope[k])
 if (scope['schema']!=PREFIX+'review_metadata_scope.v2' or scope['authority']!='display_only'
     or scope['owner_contract']!=PREFIX+'review_metadata_owner.v2' or scope['action']!='read_registered_reviewer_metadata.v2'
     or type(scope['slot']) is not int or not 0<=scope['slot']<=2):fail()
 ref(scope['reviewer_plan_ref'],PREFIX+'reviewer_plan.v1',262144)
 plan=parse(raw,262144)
 keys(plan,('schema','object_id','authority','study_id','preregistered_at','protocol_sha256','annotation_guide_sha256','membership_sha256','tasks_ref','reviewers','adjudicator','assignments','blinding'))
 ident(plan['object_id']);ident(plan['study_id'])
 if (plan['schema']!=PREFIX+'reviewer_plan.v1' or plan['authority']!='display_only' or plan['study_id']!=scope['study_id']
     or plan['object_id']!=scope['reviewer_plan_ref']['object_id'] or len(raw)!=scope['reviewer_plan_ref']['bytes']
     or hashlib.sha256(raw).hexdigest()!=scope['reviewer_plan_ref']['sha256']):fail()
 constants={'protocol_sha256':'5821074f0ad1564780759a7e5d7ca6595cd8d411f119629f31ee431f2a481ca6',
  'annotation_guide_sha256':'4efc664f6c86f5af6a62ac4fd8b98ae37ae130fa18ecfa7bdf0a88b399a71696',
  'membership_sha256':'76de9522d40c65c33de0dcde59f581a5c493f4be218df3221adb9c3af1495c8f'}
 if any(plan[k]!=v for k,v in constants.items()):fail()
 stamp=plan['preregistered_at']
 if type(stamp) is not str or len(stamp)>27 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})',stamp):fail()
 try:
  if datetime.fromisoformat(stamp.upper().replace('Z','+00:00')).tzinfo is None:fail()
 except ValueError:fail()
 ref(plan['tasks_ref'],PREFIX+'tasks.v1',4194304)
 blind={'method_identity_suppressed':True,'provider_identity_suppressed':True,'later_outcome_values_suppressed':True,
  'peer_provisional_ratings_visible':False,'original_ratings_retained':True,'adjudication_reasons_retained':True}
 if canonical(plan['blinding'])!=canonical(blind):fail()
 if type(plan['reviewers']) is not list or len(plan['reviewers'])!=2:fail()
 people=[*plan['reviewers'],plan['adjudicator']];ids=[];seen_ids=set();seen_hash=set();reads=[];total=0
 for position,p in enumerate(people):
  keys(p,ROLES)
  for role in ROLES:ref(p[role],PREFIX+'reviewer_'+role.removesuffix('_ref')+'_metadata.v2',8192)
  pid=p['principal_ref']['object_id'];ids.append(pid)
  for role in ROLES:
   r=p[role]
   if r['object_id'] in seen_ids or r['sha256'] in seen_hash:fail()
   seen_ids.add(r['object_id']);seen_hash.add(r['sha256']);total+=r['bytes']
   reads.append({'study_id':scope['study_id'],'task_id':scope['task_id'],'slot':scope['slot'],
    'participant_role':PARTICIPANTS[position],'participant_id':pid,'evidence_role':role,'reference':r})
 if total>65536 or len(set(ids))!=3:fail()
 assignments=plan['assignments'];seen_tasks=set()
 if type(assignments) is not list or not 1<=len(assignments)<=512:fail()
 for a in assignments:
  keys(a,('task_id','reviewer_principal_ids','adjudicator_principal_id'));ident(a['task_id'])
  if a['task_id'] in seen_tasks:fail()
  seen_tasks.add(a['task_id']);x=a['reviewer_principal_ids']
  if type(x) is not list or len(x)!=2 or any(type(v) is not str for v in x) or set(x)!=set(ids[:2]) or a['adjudicator_principal_id']!=ids[2]:fail()
 if scope['task_id'] not in seen_tasks:fail()
 result={'schema':PREFIX+'review_metadata_read_plan.v2','authority':'display_only','scope':scope,
  'reviewer_plan_sha256':hashlib.sha256(raw).hexdigest(),'reads':reads,'verification':{k:False for k in FLAGS},
  'native_v2_owner_read_support':'not_implemented','installed_permission':'not_verified'}
 result['plan_sha256']=hashlib.sha256(canonical(result,65536)).hexdigest()
 return result


def validate_binding(value,reviewer_plan_bytes,*,expected_root,expected_parent,expected_run,expected_input_sha256):
 value=parse(canonical(value,65536),65536)
 keys(value,('schema','root','parent','run_id','input_sha256','scope','read_plan','participant_role'))
 for k in ('root','parent','run_id'):ident(value[k])
 if (value['schema']!='mastermind.fabric_memory_participant_binding.v1' or value['root']!=expected_root
     or value['parent']!=expected_parent or value['run_id']!=expected_run
     or value['input_sha256']!=expected_input_sha256 or type(value['input_sha256']) is not str
     or not SHA.fullmatch(value['input_sha256']) or value['participant_role'] not in PARTICIPANTS):fail()
 # Recompute from the exact declared plan bytes; a caller's plan hash/builder
 # is never taken as an origin credential or as a semantic verifier.
 if canonical(value['read_plan'],65536)!=canonical(derive(value['scope'],reviewer_plan_bytes),65536):fail()
 return canonical(value,65536)
