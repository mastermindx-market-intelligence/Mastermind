"""Closed DATA observation facts only; no grant, clock acquisition or I/O."""
from copy import deepcopy
from datetime import datetime
import re

SCHEMA='mastermind.canonical_project_data_observation.v1'
_KEYS={'schema','repository','default_ref','executable_macro_commit','canonical_data_commit','canonical_commit_at','canonical_observed_at_ms','publication_recorded_at_ms','publication_time','source_operation','reader_closure_sha256','code_config_relation','authority'}
_CONTINUITY_KEYS={'schema','kind','work_ref','principal_scope','executable_macro_commit','canonical_data_commit','reader_closure_sha256','selected_data_closure_sha256','ancestry'}
def _fail():raise ValueError('INVALID_CANONICAL_DATA_OBSERVATION')
def _hex(v,n):
 if type(v) is not str or re.fullmatch(r'[a-f0-9]{'+str(n)+'}',v) is None:_fail()
def _integer(v,minimum=0):
 if type(v) is not int or not minimum<=v<=9007199254740991:_fail()
def validate(value):
 try:
  if type(value) is not dict or set(value) not in (_KEYS,_KEYS|{'data_continuity'}) or value['schema']!=SCHEMA or value['repository']!='mastermindx-market-intelligence/macro' or value['code_config_relation']!='IDENTICAL_READER_CLOSURE' or value['authority']!='OBSERVATION_ONLY' or value['publication_time'] is not None:_fail()
  if type(value['default_ref']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}',value['default_ref']) is None or any(part in ('','.','..') for part in value['default_ref'].split('/')):_fail()
  for k in ('executable_macro_commit','canonical_data_commit'):_hex(value[k],40)
  _hex(value['reader_closure_sha256'],64);_integer(value['canonical_observed_at_ms'],1)
  if type(value['canonical_commit_at']) is not str or len(value['canonical_commit_at'])>64 or datetime.fromisoformat(value['canonical_commit_at'].replace('Z','+00:00')).utcoffset() is None:_fail()
  operation=value['source_operation']
  if 'data_continuity' in value:
   proof=value['data_continuity']
   if (type(proof) is not dict or set(proof)!=_CONTINUITY_KEYS
       or proof['schema']!='mastermind.project_data_continuity.v1'
       or proof['kind']!='UNCHANGED_SELECTED_PROJECT_DATA'
       or proof['ancestry']!='CODE_ANCESTOR_OF_DATA'
       or operation is not None or value['publication_recorded_at_ms'] is not None
       or value['executable_macro_commit']==value['canonical_data_commit']):_fail()
   if type(proof['work_ref']) is not str or re.fullmatch(r'WS:[A-Z0-9]+(?:-[A-Z0-9]+)*',proof['work_ref']) is None or not 2<=len(proof['work_ref'][3:])<=64:_fail()
   for k in ('principal_scope','reader_closure_sha256','selected_data_closure_sha256'):_hex(proof[k],64)
   for k in ('executable_macro_commit','canonical_data_commit'):_hex(proof[k],40)
   if any(proof[k]!=value[k] for k in ('executable_macro_commit','canonical_data_commit','reader_closure_sha256')):_fail()
  elif operation is None:
   if value['publication_recorded_at_ms'] is not None or value['executable_macro_commit']!=value['canonical_data_commit']:_fail()
  else:
   expected={'selection','principal_scope','request_sha256','recipe_fingerprint_sha256','event_id','receipt_sha256','recorded_at_ms','sources'}
   if type(operation) is not dict or set(operation)!=expected:_fail()
   for k in ('principal_scope','request_sha256','recipe_fingerprint_sha256','receipt_sha256'):_hex(operation[k],64)
   _integer(operation['event_id'],1);_integer(operation['recorded_at_ms'])
   if value['publication_recorded_at_ms']!=operation['recorded_at_ms']:_fail()
   selected=operation['selection']
   if type(selected) is not dict or set(selected)!={'action','request_id','work_ref'}:_fail()
   prefixes={'add_project_file':'mmos-project-file-add-','set_project_communication_preference':'mmos-project-preference-set-', 'publish_project_proposal':'mmos-project-create-','publish_project_plan_proposal':'mmos-project-plan-proposal-','ADOPT_PLAN':'mmos-project-adopt-'}
   prefix=prefixes.get(selected['action'])
   if prefix is None or type(selected['request_id']) is not str or re.fullmatch(re.escape(prefix)+r'[a-f0-9]{40}',selected['request_id']) is None or type(selected['work_ref']) is not str or re.fullmatch(r'WS:[A-Z0-9]+(?:-[A-Z0-9]+)*',selected['work_ref']) is None or not 2<=len(selected['work_ref'][3:])<=64:_fail()
   if selected['action']=='ADOPT_PLAN' and (type(operation['sources']) is not list or len(operation['sources']) not in (2,3)):_fail()
   count=(len(operation['sources']) if selected['action']=='ADOPT_PLAN'
          else 1 if selected['action']=='publish_project_proposal' else 2)
   if type(operation['sources']) is not list or len(operation['sources'])!=count:_fail()
   for source in operation['sources']:
    if type(source) is not dict or set(source)!={'repository','commit','path','content_sha256'} or source['repository']!='macro':_fail()
    _hex(source['commit'],40);_hex(source['content_sha256'],64)
    if type(source['path']) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,511}',source['path']) is None or any(part in ('','.','..') for part in source['path'].split('/')):_fail()
   if len({s['path'] for s in operation['sources']})!=count or len({s['commit'] for s in operation['sources']})!=1:_fail()
   if selected['action']=='ADOPT_PLAN':
    from common.plan_adoption_publication_contract import validate_adoption_sources
    validate_adoption_sources(selected,operation['sources'])
   elif selected['action'] in {'publish_project_proposal','publish_project_plan_proposal'}:
    work=selected['work_ref'][3:];paths={'agentos/workstreams/WS-'+work+'.md'}
    if count==2:paths.add('research/project-plans/PLAN-'+work+'-'+selected['request_id'][-40:]+'.md')
    if {s['path'] for s in operation['sources']}!=paths:_fail()
  return deepcopy(value)
 except (ValueError,TypeError,KeyError,AttributeError,OverflowError):_fail()
