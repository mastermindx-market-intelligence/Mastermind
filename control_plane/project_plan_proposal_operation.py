"""Typed planning-result recipe over the existing private source-operation owner.

The installed source factory qualifies actual code/snapshot acquisition; initial
preparation requires a live S19 retained result object. Restoration is ONLY for
the existing owner after verified original-input custody and committed digest.
It cannot reconstruct/retry an unknown operation from changed current data.
"""
from copy import deepcopy
import re
from types import ModuleType
from control_plane.project_plan_result_source import QualifiedPlanningResult, _ConsumedPlanningObservation
from control_plane.project_plan_proposal_git import validate_request,ACTION

PRIVATE_SCHEMA='mastermind.project_source_original_input.v1'
_PATHS={'compiler':'scripts/agentos_plan_proposal_recipe.py','declaration':'scripts/agentos_plan_proposal.py','owner':'scripts/agentos.py','contract':'scripts/agentos_project_plan_contract.py'}
_KEYS={'schema','action','request','actor','initial_snapshot','source_binding'}
class PlanProposalOperationError(ValueError):pass

def _fail():raise PlanProposalOperationError('PLAN_PROPOSAL_INPUT_UNAVAILABLE')

class PreparedPlanProposal:
 __slots__=('_payload','_fingerprint')
 def __init__(self,payload,fingerprint):self._payload=deepcopy(payload);self._fingerprint=fingerprint
 @property
 def fingerprint_sha256(self):return self._fingerprint
 def private_payload(self):return deepcopy(self._payload)

class PlanProposalRecipeAdapter:
 action=ACTION
 def __init__(self,*,compiler,owner,declaration,source_binding):
  if any(type(m) is not ModuleType for m in (compiler,owner,declaration)) or type(source_binding) is not dict or set(source_binding)!=set(_PATHS):_fail()
  for key,path in _PATHS.items():
   ref=source_binding[key]
   if (type(ref) is not dict or set(ref)!={'repository','path','commit','content_sha256'} or ref['repository']!='mastermindx-market-intelligence/macro' or ref['path']!=path
       or type(ref['commit']) is not str or re.fullmatch(r'[a-f0-9]{40}',ref['commit']) is None or type(ref['content_sha256']) is not str or re.fullmatch(r'[a-f0-9]{64}',ref['content_sha256']) is None):_fail()
  if len({ref['commit'] for ref in source_binding.values()})!=1:_fail()
  self._compiler,self._owner,self._declaration=compiler,owner,declaration;self._binding=deepcopy(source_binding)
 def _recipe(self,payload):
  try:
   if type(payload) is not dict or set(payload)!=_KEYS or payload['schema']!=PRIVATE_SCHEMA or payload['action']!=ACTION or payload['source_binding']!=self._binding:_fail()
   basis=payload['initial_snapshot']
   if type(basis) is not dict or set(basis)!={'snapshot','planning_result'}:_fail()
   request=validate_request(payload['request'])
   recipe=self._compiler.compile_proposal_recipe(request,deepcopy(basis['snapshot']),deepcopy(basis['planning_result']),deepcopy(payload['actor']),owner=self._owner,declaration_owner=self._declaration)
   if recipe.get('status') not in ('DRAFT_ONLY','NO_PROPOSAL') or recipe.get('schema')!='agentos.project_plan_proposal_recipe.v1':_fail()
   return recipe
  except (ValueError,KeyError,AttributeError,TypeError,UnicodeError,RecursionError):_fail()
 def prepare(self,*,request,initial_snapshot,actor,qualified_result):
  if type(qualified_result) is not QualifiedPlanningResult:_fail()
  with qualified_result.read_scope():
   data=qualified_result.check()
   payload=dict(schema=PRIVATE_SCHEMA,action=ACTION,request=deepcopy(request),actor=deepcopy(actor),initial_snapshot=dict(snapshot=deepcopy(initial_snapshot),planning_result=data),source_binding=deepcopy(self._binding))
   recipe=self._recipe(payload)
   if recipe['status']=='NO_PROPOSAL':return None
   qualified_result.check()  # The original request is still live before freeze.
   return PreparedPlanProposal(payload,recipe['recipe_fingerprint_sha256'])
 def restore(self,*,private_payload,trusted_recipe_fingerprint):
  recipe=self._recipe(private_payload)
  if recipe.get('recipe_fingerprint_sha256')!=trusted_recipe_fingerprint:_fail()
  return PreparedPlanProposal(private_payload,trusted_recipe_fingerprint)
 def _prepare_observed(self,*,request,initial_snapshot,actor,qualified_result,observation):
  # Fixed installed service only: its genuine pre/post Runtime observations
  # surround this PURE compiler. A public DTO/flag cannot select this entry.
  if type(observation) is not _ConsumedPlanningObservation:_fail()
  data=observation.material(qualified_result)
  payload=dict(schema=PRIVATE_SCHEMA,action=ACTION,request=deepcopy(request),actor=deepcopy(actor),initial_snapshot=dict(snapshot=deepcopy(initial_snapshot),planning_result=data),source_binding=deepcopy(self._binding))
  recipe=self._recipe(payload)
  if recipe['status']=='NO_PROPOSAL':return None
  observation.material(qualified_result)
  return PreparedPlanProposal(payload,recipe['recipe_fingerprint_sha256'])
 def recipe(self,prepared):
  if type(prepared) is not PreparedPlanProposal:_fail()
  recipe=self._recipe(prepared.private_payload())
  if recipe.get('recipe_fingerprint_sha256')!=prepared.fingerprint_sha256:_fail()
  return deepcopy(recipe)
