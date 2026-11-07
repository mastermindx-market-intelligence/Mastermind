"""Nominal read proof from the incumbent original SourceOperationEvents owner.

No supplied receipt authenticates itself; this object re-reads immutable actual
Events, the original planned CAS pair, scope and caller's current read guard.
No source write, retry, claim, publication or new persistence occurs here.
"""
from copy import deepcopy
from dataclasses import dataclass,field
import json
import re
from control_plane.workspace_source_operations import SourceOperationEvents

_SEAL=object()
class CanonicalPublicationUnavailable(ValueError):pass
def _fail():raise CanonicalPublicationUnavailable('CANONICAL_PUBLICATION_UNAVAILABLE')
def _bytes(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def _observe(events,lookup,scope,guard):
 if type(events) is not SourceOperationEvents or not callable(guard):_fail()
 status=SourceOperationEvents.read_status(events,lookup,scope,guard=guard)
 original=SourceOperationEvents.original(events,lookup,scope,guard=guard)
 phase='ADOPTION' if lookup['action']=='ADOPT_PLAN' else 'PUBLICATION'
 if (original is None or status['disposition']!='accepted' or status['phase']!=phase
     or status['receipt'] is None or status['receipt']['kind']!='SOURCE_OBSERVED'
     or status['receipt']['proposal'] is not None or status['owner_context']['principal_scope']!=scope
     or status['request_sha256']!=original['request_sha256']
     or status['recipe_fingerprint_sha256']!=original['recipe_fingerprint_sha256']):_fail()
 binding=(SourceOperationEvents.publication_binding(events,lookup,scope,phase=phase,guard=guard)
          if phase=='ADOPTION' else original.get('publication_binding',{}))
 images=None if binding is None else binding.get('postimages');sources=status['receipt']['sources']
 if type(images) is not list or not images or len(images)!=len(sources):_fail()
 work=lookup['work_ref'][3:];ws='agentos/workstreams/WS-'+work+'.md'
 paths={i['path'] for i in images}
 if lookup['action']=='add_project_file':
  if len(paths)!=2 or ws not in paths or any(path!=ws and re.fullmatch(r'agentos/project-files/WS-'+re.escape(work)+r'/[a-f0-9]{64}\.(?:md|txt)',path) is None for path in paths):_fail()
 elif lookup['action']=='correct_project_discovery':
  from common import workspace_discovery_correction_contract as correction
  identity=correction.validate_lookup(original['lookup_binding'])
  if any(identity[k]!=lookup[k] for k in ('action','request_id','work_ref')):_fail()
  expected=correction.expected_preimages(identity,scope)
  if len(images)!=3 or {i['path']:i['expected_preimage_sha256'] for i in images}!=expected:_fail()
 elif lookup['action']=='set_project_communication_preference':
  if paths!={ws,'agentos/decisions/DEC-PROJECT-COMMUNICATION-PREFERENCE-'+work+'.md'}:_fail()
 elif lookup['action'] in {'publish_project_proposal','publish_project_plan_proposal'}:
  from control_plane.project_journey_publication import validate_project_journey_publication
  validate_project_journey_publication(lookup,images,sources)
 elif lookup['action']=='ADOPT_PLAN':
  from common.plan_adoption_publication_contract import validate_adoption_publication
  validate_adoption_publication({key:lookup[key] for key in ('action','request_id','work_ref')},images,sources)
 else:_fail()
 if len({s['commit'] for s in sources})!=1 or any(s['repository']!='macro' for s in sources):_fail()
 if sorted((i['path'],i['content_sha256']) for i in images)!=sorted((s['path'],s['content_sha256']) for s in sources):_fail()
 if SourceOperationEvents.read_status(events,lookup,scope,guard=guard)!=status:_fail()
 return dict(selection=deepcopy(status['selection']),principal_scope=scope,request_sha256=status['request_sha256'],
  recipe_fingerprint_sha256=status['recipe_fingerprint_sha256'],event_id=status['receipt']['event_id'],
  receipt_sha256=status['receipt']['receipt_sha256'],recorded_at_ms=status['receipt']['recorded_at_ms'],
  sources=deepcopy(sources))
@dataclass(frozen=True,slots=True)
class CanonicalDataPublicationProof:
 _seal:object=field(repr=False)
 _events:SourceOperationEvents=field(repr=False)
 _lookup:dict=field(repr=False)
 _scope:str=field(repr=False)
 _guard:object=field(repr=False)
 _material:bytes=field(repr=False)
 def check(self,principal_scope):
  try:
   if self._seal is not _SEAL or self._scope!=principal_scope:_fail()
   current=_observe(self._events,self._lookup,self._scope,self._guard)
   if _bytes(current)!=self._material:_fail()
   return deepcopy(current)
  except (ValueError,TypeError,KeyError,AttributeError,PermissionError):_fail()
def capture_source_publication(events,lookup,principal_scope,*,guard):
 """Lookup is a selector; original Event owner + current guard are authority."""
 try:
  material=_observe(events,lookup,principal_scope,guard)
  return CanonicalDataPublicationProof(_SEAL,events,deepcopy(lookup),principal_scope,guard,_bytes(material))
 except (ValueError,TypeError,KeyError,AttributeError,PermissionError):_fail()


def select_source_publication(events,work_ref,principal_scope,*,qualify,guard):
 """Bounded reopen selectors are not proof. Qualify actual owner receipts.

 ``qualify`` belongs to the same fixed Git owner and checks actual current
 default ancestry/postimages. No source write or pointer store is introduced.
 """
 if type(events) is not SourceOperationEvents or not callable(qualify):_fail()
 candidates=SourceOperationEvents.publication_candidates(events,work_ref,principal_scope,guard=guard)
 for lookup in candidates['lookups']:
  try:
   proof=capture_source_publication(events,lookup,principal_scope,guard=guard)
   if qualify(proof) is True:
    proof.check(principal_scope);return proof
  except (ValueError,TypeError,KeyError,AttributeError,PermissionError):continue
 _fail()
