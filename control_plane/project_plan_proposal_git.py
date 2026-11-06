"""Distinct PLAN-proposal mode of the existing fixed Git publisher.

Uses the existing private exact-once phase claim and guarded Git primitives.
No ADOPT, source grant issuance, new store or authority from returned data.
"""
from copy import deepcopy
import hashlib
import re
from control_plane import workspace_project_git_publisher as p
from control_plane.project_plan_adoption_git import PlanAdoptionGitMode,_closed,_json,_fail

ACTION='publish_project_plan_proposal'
SCHEMA='mastermind.plan_proposal_git_publication.v1'
BINDING_SCHEMA='mastermind.plan_proposal_publication_binding.v1'
LOOKUP_SCHEMA='mastermind.workspace_source_operation_lookup.v1'
REQUEST_KEYS={'schema','request_id','work_ref','expected_commit','expected_adoption','base_source','selection','result_digest'}
RECIPE_KEYS={'schema','status','action','request_id','request_sha256','recipe_fingerprint_sha256','work_ref','principal_id','expected_commit','proposal_id','proposal_path','candidate_sha256','base_source','base_adoption','result_binding','edits','preview'}

def lookup(value):
 _closed(value,{'schema','action','request_id','work_ref'})
 if (value['schema']!=LOOKUP_SCHEMA or value['action']!=ACTION or type(value['request_id']) is not str
     or re.fullmatch(r'mmos-project-plan-proposal-[0-9a-f]{40}',value['request_id']) is None or not p._valid_work_ref(value['work_ref'])):_fail('REQUEST_INVALID')
 return deepcopy(value)
def validate_request(value):
 _closed(value,REQUEST_KEYS);lookup(dict(schema=LOOKUP_SCHEMA,action=ACTION,request_id=value['request_id'],work_ref=value['work_ref']))
 if value['schema']!='mastermind.project_plan_proposal_request.v1' or not p._is_hex40(value['expected_commit']) or not p._is_hex64(value['result_digest']):_fail('REQUEST_INVALID')
 _closed(value['base_source'],{'repository','commit','path','content_sha256'})
 ref=value['base_source']
 if ref['repository']!=p.REPOSITORY or not p._is_hex40(ref['commit']) or not p._is_hex64(ref['content_sha256']) or not p._valid_repo_path(ref['path']):_fail('REQUEST_INVALID')
 prior=value['expected_adoption']
 if prior is not None and (type(prior) is not str or re.fullmatch(r'DEC:[A-Z0-9]+(?:-[A-Z0-9]+)*',prior) is None):_fail('REQUEST_INVALID')
 _closed(value['selection'],{'work_ref','job_id','attempt_id'})
 if value['selection']['work_ref']!=value['work_ref'] or any(type(value['selection'][k]) is not str or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value['selection'][k]) is None for k in ('job_id','attempt_id')):_fail('REQUEST_INVALID')
 if len(_json(value))>16384:_fail('REQUEST_INVALID')
 return deepcopy(value)

def targets(selected,images):
 proposal='research/project-plans/PLAN-'+selected['work_ref'][3:]+'-'+selected['request_id'][-40:]+'.md'
 ws='agentos/workstreams/WS-'+selected['work_ref'][3:]+'.md'
 if len(images)!=2 or {i['path'] for i in images}!={proposal,ws}:_fail()
 for i in images:
  if i['path']==proposal and i['expected_preimage_sha256'] is not None:_fail()
  if i['path']==ws and not p._is_hex64(i['expected_preimage_sha256']):_fail()
 return proposal,ws

class PlanProposalGitMode(PlanAdoptionGitMode):
 mode_name='plan_proposal'
 allowed_phases=('PUBLICATION',)
 request_keys=REQUEST_KEYS
 action=ACTION
 lookup=staticmethod(lookup)
 @staticmethod
 def branch(selected,scope,phase):
  return 'mmos/plan-proposal-'+hashlib.sha256(_json(dict(principal_scope=scope,request_id=selected['request_id']))).hexdigest()
 def _metadata(self,principal,selected,phase,scope):
  value=self.seams['load'](principal,deepcopy(selected),phase)
  _closed(value,{'schema','selection','principal_scope','request_sha256','recipe_fingerprint_sha256','permission_binding_digest','phase','publication_binding'})
  if (value['schema']!=BINDING_SCHEMA or lookup(value['selection'])!=selected or value['principal_scope']!=scope or value['phase']!='PUBLICATION' or any(not p._is_hex64(value[k]) for k in ('request_sha256','recipe_fingerprint_sha256','permission_binding_digest')) or value['request_sha256']==value['recipe_fingerprint_sha256']):_fail('OPERATION_CONFLICT',conflict=True)
  binding=value['publication_binding'];_closed(binding,{'expected_commit','postimages','branch'})
  if not p._is_hex40(binding['expected_commit']) or type(binding['postimages']) is not list:_fail()
  for image in binding['postimages']:
   _closed(image,{'path','content_sha256','expected_preimage_sha256'})
   if not p._is_hex64(image['content_sha256']):_fail()
  targets(selected,binding['postimages'])
  if binding['branch'] not in (None,self.branch(selected,scope,phase)):_fail('OPERATION_CONFLICT',conflict=True)
  return deepcopy(value)
 def _recipe(self,request,recipe,op):
  validate_request(request);_closed(recipe,RECIPE_KEYS)
  if (recipe['schema']!='agentos.project_plan_proposal_recipe.v1' or recipe['status']!='DRAFT_ONLY' or recipe['action']!=ACTION
      or recipe['request_id']!=op.original_lookup['request_id'] or recipe['work_ref']!=op.work_ref
      or recipe['request_sha256']!=op.request_sha256 or hashlib.sha256(_json(request)).hexdigest()!=op.request_sha256
      or recipe['recipe_fingerprint_sha256']!=op.recipe_fingerprint or recipe['expected_commit']!=op.expected_commit
      or request['expected_commit']!=op.expected_commit or recipe['base_source']!=request['base_source']
      or recipe['base_adoption']!=request['expected_adoption'] or not p._is_hex64(recipe['candidate_sha256'])):_fail('OPERATION_CONFLICT',conflict=True)
  if recipe['result_binding'].get('selection')!=request['selection'] or recipe['result_binding'].get('result_digest')!=request['result_digest']:_fail('OPERATION_CONFLICT',conflict=True)
  images=op.metadata['publication_binding']['postimages'];proposal,ws=targets(op.original_lookup,images)
  if recipe['proposal_path']!=proposal or recipe['proposal_id']!='PLAN-'+request['request_id'][-40:].upper():_fail()
  if type(recipe['edits']) is not list or not 1<=len(recipe['edits'])<=2:_fail()
  edits={};total=0
  for edit in recipe['edits']:
   _closed(edit,{'path','mode','expected_sha256','content_utf8','content_sha256'})
   if type(edit['path']) is not str or edit['path'] in edits or edit['path'] not in (proposal,ws) or edit['mode']!='100644' or type(edit['content_utf8']) is not str:_fail()
   raw=edit['content_utf8'].encode();total+=len(raw)
   if hashlib.sha256(raw).hexdigest()!=edit['content_sha256']:_fail('OPERATION_CONFLICT',conflict=True)
   if total>524288:_fail()
   edits[edit['path']]=edit
  normalized=[]
  for image in images:
   edit=edits.get(image['path'])
   if edit is None:
    if image['path']!=ws or image['content_sha256']!=image['expected_preimage_sha256']:_fail()
    raw=self.owner._read_blob_at(op,op.expected_commit,ws)
    if raw is None or hashlib.sha256(raw).hexdigest()!=image['content_sha256']:_fail('PREIMAGE_CONFLICT',conflict=True)
    text=raw.decode()
   else:
    if edit['content_sha256']!=image['content_sha256'] or edit['expected_sha256']!=image['expected_preimage_sha256']:_fail('OPERATION_CONFLICT',conflict=True)
    text=edit['content_utf8']
   normalized.append({**image,'content_utf8':text})
  return dict(postimages=normalized,request_fingerprint=op.recipe_fingerprint)
 def _result(self,op,state,*,source=None,proposal=None,reason=None):
  value=super()._result(op,state,source=source,proposal=proposal,reason=reason);value['schema']=SCHEMA;return value
