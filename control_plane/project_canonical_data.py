"""Private data-only canonical observation of the existing fixed Git owner.

A latest-data grant is distinct from revision-pinned Workspace READ. No source
root/HEAD is advanced, no code is loaded from the observed data revision, and
no PR branch is mistaken for protected/default publication. This is request-
local evidence, not a cache, store, grant, installer or publication command.

An unrelated canonical movement may instead retain a nominal unchanged-DATA
proof: the actual configured readers discover the same finite selected inputs
at both C and N, with C ancestral to N. This proof never supplies an Event or
publication clock. Changed selected DATA still needs the existing real Event
proof; source writes and their original-CAS authority are unchanged.
"""
from dataclasses import dataclass,field
from contextlib import contextmanager
from contextvars import ContextVar
from copy import copy
import json
import hashlib
import os
from pathlib import Path
import re
import time
from control_plane import workspace_project_git_publisher as p

_SEAL=object()
_CAPTURE=ContextVar("canonical_project_data_capture",default=None)

@dataclass(slots=True)
class _Capture:
 view:object=field(repr=False)
 operation:object=field(repr=False)
 identity:tuple=field(repr=False)
 parent:object=field(default=None,repr=False)
 active:bool=True
 def remaining(self):
  self.view._check_capture(self)
  return self.operation.read_deadline-time.monotonic()

# Exact executed/helper/config surface of Agent OS brief + fixed project reads
# and the current Knowledge compiler. All are loaded from the configured pin.
# Inline parser checkers are schema authority; canonical schema files are also
# bound so a producer cannot silently change declared record compatibility.
_READER_CODE=frozenset({'scripts/__init__.py','scripts/agentos.py',
 'scripts/agentos_direction.py','scripts/agentos_project_plan_contract.py',
 'scripts/agentos_project_archive.py','scripts/audit_stranded_work.py',
 'scripts/project_knowledge_recipes.py','config/mastermind_programs.yml'})
_SCHEMA_PREFIX='agentos/schema/'

def local_git_environment():
 clean={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
 clean.update(GIT_NO_REPLACE_OBJECTS='1',GIT_NO_LAZY_FETCH='1',GIT_CONFIG_NOSYSTEM='1',
  GIT_CONFIG_GLOBAL='/dev/null',GIT_CONFIG_SYSTEM='/dev/null',GIT_OPTIONAL_LOCKS='0')
 return clean

class CanonicalDataUnavailable(ValueError):
 pass

def _fail():raise CanonicalDataUnavailable('CANONICAL_DATA_UNAVAILABLE')

@dataclass(frozen=True,slots=True)
class _UnchangedProjectDataProof:
 _seal:object=field(repr=False)
 _owner:object=field(repr=False)
 _principal:object=field(repr=False)
 _scope:str
 _stamp:str
 _work_ref:str
 _binding:str
 _code_root:Path=field(repr=False)
 _deadline:float
 _material:bytes=field(repr=False)

@dataclass(frozen=True,slots=True)
class CanonicalProjectDataView:
 _seal:object=field(repr=False)
 _owner:object=field(repr=False)
 _operation:object=field(repr=False)
 data_commit:str
 code_commit:str
 _root:Path=field(repr=False)
 _code_root:Path=field(repr=False)
 _witness:dict=field(repr=False)
 _publication:object=field(repr=False,default=None)
 _verified_facts:dict=field(repr=False,default_factory=dict)
 _deadline:object=field(repr=False,default=None)
 _continuity:object=field(repr=False,default=None)
 def _full_check(self,operation=None):
  if self._seal is not _SEAL or type(self._owner) is not CanonicalProjectDataMode:_fail()
  try:self._owner.check(self,operation=operation)
  except (p._Refusal,p._Unknown,OSError,ValueError,TypeError,KeyError,AttributeError):_fail()
 def _check_capture(self,capture):
  try:self._owner._capture_check(capture)
  except (p._Refusal,p._Unknown,OSError,ValueError,TypeError,KeyError,AttributeError):_fail()
 def check(self):
  capture=_CAPTURE.get()
  if capture is not None and capture.view is self:
   self._check_capture(capture)
  else:self._full_check()
 @contextmanager
 def capture_scope(self,*,deadline=None):
  """Pure read/compiler capture ONLY, never publication or another effect.

  Full current principal/default/Event/config fences bracket the outer capture.
  Nested checks reuse the exact immutable C/N/postimage facts and still check
  current permissions, binding identity and the original remaining budget.
  No observation lifetime, external deadline or authority is renewed here.
  """
  if self._seal is not _SEAL or type(self._owner) is not CanonicalProjectDataMode:_fail()
  parent=_CAPTURE.get()
  limit=self._operation.read_deadline
  if deadline is not None:
   if type(deadline) not in (int,float) or not 0<deadline<float('inf'):_fail()
   limit=min(limit,deadline)
  if parent is not None:
   parent.view._check_capture(parent)
   limit=min(limit,parent.operation.read_deadline)
  operation=copy(self._operation);operation.read_deadline=limit
  same=parent is not None and parent.view is self
  if not same:self._full_check(operation)
  capture=_Capture(self,operation,self._owner._view_identity(self),parent)
  self._check_capture(capture)
  token=_CAPTURE.set(capture)
  try:
   yield capture
   self._check_capture(capture)
   if not same:self._full_check(operation)
  finally:
   capture.active=False
   _CAPTURE.reset(token)
 def witness(self):
  self.check()
  from copy import deepcopy
  from common.canonical_project_data_observation_contract import validate
  return validate(deepcopy(self._witness))
 def _require_work(self,work_ref):
  if self.data_commit!=self.code_commit and work_ref!=self._operation.selected_work_ref:_fail()
 def read_plan(self,*,work_ref):
  self._require_work(work_ref)
  from control_plane.agentos_project_plan import read_from_macro_owner
  with self.capture_scope(deadline=time.monotonic()+10.0) as capture:
   value=read_from_macro_owner(macro_root=self._root,expected_macro_sha=self.data_commit,work_ref=work_ref,include_continuity=True,_canonical_data_view=self,timeout=min(10.0,capture.remaining()))
  return value
 def read_knowledge_catalogue(self,*,work_ref):
  self._require_work(work_ref)
  from control_plane.agentos_project_knowledge import read_project_knowledge_catalogue
  with self.capture_scope(deadline=time.monotonic()+10.0) as capture:
   value=read_project_knowledge_catalogue(macro_root=self._root,expected_macro_sha=self.data_commit,work_ref=work_ref,_canonical_data_view=self,timeout=min(10.0,capture.remaining()))
  return value
 def read_knowledge_source(self,*,work_ref,source_ref,expected_revision):
  self._require_work(work_ref)
  from control_plane.agentos_project_knowledge import read_project_knowledge_source
  with self.capture_scope(deadline=time.monotonic()+10.0) as capture:
   value=read_project_knowledge_source(macro_root=self._root,expected_macro_sha=self.data_commit,work_ref=work_ref,source_ref=source_ref,expected_revision=expected_revision,_canonical_data_view=self,timeout=min(10.0,capture.remaining()))
  return value
 def read_knowledge_memory(self,*,work_ref):
  self._require_work(work_ref)
  from control_plane.agentos_project_knowledge import read_project_communication_preference
  with self.capture_scope(deadline=time.monotonic()+10.0) as capture:
   value=read_project_communication_preference(macro_root=self._root,expected_macro_sha=self.data_commit,work_ref=work_ref,_canonical_data_view=self,timeout=min(10.0,capture.remaining()))
  return value

class CanonicalProjectDataMode:
 """Installed source owner supplies all fixed config and current grant seams."""
 def __init__(self,publisher,*,pinned_macro_root,code_commit,authorize_read,read_stamp,authorize_data,data_stamp,publication=None,events=None):
  self.publisher=publisher
  self.code_root=None if pinned_macro_root is None else Path(pinned_macro_root)
  self.code_commit=code_commit
  self.publication=publication
  self.events=events
  if publication is not None:p._require_callable(publication,'canonical_data_publication')
  self.publication_identity=None if publication is None else p._callable_identity(publication)
  self.seams=dict(authorize_read=authorize_read,read_stamp=read_stamp,authorize_data=authorize_data,data_stamp=data_stamp)
  for k,v in self.seams.items():
   if v is not None:p._require_callable(v,k)
  self.identities={k:None if v is None else p._callable_identity(v) for k,v in self.seams.items()}
 def permission(self,principal,op):
  if self.code_root is None or not self.code_root.is_absolute() or not p._is_hex40(self.code_commit) or any(v is None for v in self.seams.values()):_fail()
  if {k:p._callable_identity(v) for k,v in self.seams.items()}!=self.identities:_fail()
  if self.seams['authorize_read'](principal) is not True or self.seams['authorize_data'](principal) is not True:_fail()
  stamps=[self.seams[k](principal) for k in ('read_stamp','data_stamp')]
  if any(not p._is_hex64(v) for v in stamps):_fail()
  return hashlib.sha256(('\n'.join(stamps)).encode()).hexdigest()
 def _configured(self,operation=None):
  # The surrounding installed collector still owns the full source seal.
  # Requiring the original configured HEAD makes this view data-only.
  from control_plane.ceo_boot_packet import bounded_subprocess_runner
  clean_env=local_git_environment()
  def budget():
   remaining=5.0 if operation is None else min(5.0,operation.read_deadline-time.monotonic())
   if remaining<=0:_fail()
   return remaining
  observed=bounded_subprocess_runner(['git','--no-replace-objects','-C',str(self.code_root),'rev-parse','HEAD'],cwd=self.code_root,timeout=budget(),max_bytes=64,env=clean_env)
  if observed.get('code')!=0 or observed.get('stdout','').strip()!=self.code_commit or any(observed.get(k) is True for k in ('timed_out','limit_exceeded','invalid_utf8')):_fail()
  clean=bounded_subprocess_runner(['git','--no-replace-objects','-C',str(self.code_root),
   'status','--porcelain=v1','--untracked-files=all','--','scripts','config','agentos/schema','agentos/schemas'],
   cwd=self.code_root,timeout=budget(),max_bytes=262144,env=clean_env)
  if clean.get('code')!=0 or clean.get('stdout')!='' or any(clean.get(k) is True for k in ('timed_out','limit_exceeded','invalid_utf8')):_fail()
 def _view_identity(self,view):
  op=view._operation
  return (view._owner,id(op),id(op.principal),op.scope,op.stamp,op.selected_work_ref,
   op.read_deadline,view._deadline,view.data_commit,view.code_commit,view._root,view._code_root,
   self.publisher._binding.fingerprint,id(view._publication),id(view._continuity))
 def _validate_view(self,view):
  if (view._seal is not _SEAL or view._owner is not self or view.code_commit!=self.code_commit
      or view._code_root!=self.code_root or view._root!=Path(self.publisher._binding.worktree)
      or type(view._deadline) not in (int,float) or view._operation.read_deadline!=view._deadline):_fail()
 def _permission_guard(self,operation):
  # Event SQL needs current READ identity, not another Git-origin observation
  # for every tiny database fence. Full publisher/source guards bracket it.
  if time.monotonic()>=operation.read_deadline:_fail()
  self.publisher._require_seams()
  if (self.permission(operation.principal,operation)!=operation.stamp
      or self.publisher._principal_scope(operation.principal)!=operation.scope):_fail()
  return True
 def _capture_check(self,capture):
  self._validate_view(capture.view)
  if not capture.active or capture.identity!=self._view_identity(capture.view):_fail()
  parent=capture.parent
  while parent is not None:
   if not parent.active or time.monotonic()>=parent.operation.read_deadline:_fail()
   parent=parent.parent
  self._permission_guard(capture.operation)
 def check(self,view,*,operation=None):
  self._validate_view(view)
  op=view._operation if operation is None else operation
  if (op.principal is not view._operation.principal or op.scope!=view._operation.scope
      or op.stamp!=view._operation.stamp or op.selected_work_ref!=view._operation.selected_work_ref
      or op.read_deadline>view._operation.read_deadline):_fail()
  self._permission_guard(op)
  self.publisher._read_guard(op);self._configured(op)
  if self.publisher._remote_branch_commit(op,self.publisher._binding.default_branch)!=view.data_commit:_fail()
  if view.data_commit!=view.code_commit:
   if view._continuity is not None:
    material=self._check_continuity(op,view.data_commit,view._continuity)
    if material!=view._witness.get('data_continuity') or view._publication is not None:_fail()
   else:self._proof(op,view.data_commit,view._publication,verified=view._verified_facts)
  self.publisher._read_guard(op)
  self._permission_guard(op)
 def _check_continuity(self,op,canonical,proof):
  if (type(proof) is not _UnchangedProjectDataProof or proof._seal is not _SEAL or proof._owner is not self
      or proof._principal is not op.principal or proof._scope!=op.scope or proof._stamp!=op.stamp
      or proof._work_ref!=op.selected_work_ref or proof._binding!=self.publisher._binding.fingerprint
      or proof._code_root!=self.code_root or op.read_deadline>proof._deadline):_fail()
  material=json.loads(proof._material)
  if material['executable_macro_commit']!=self.code_commit or material['canonical_data_commit']!=canonical:_fail()
  return material
 def _capture_continuity(self,op,canonical,reader_digest):
  # Only immutable Git facts may survive within the original issued view.
  # Current grants, principal, config, origin and actual default still bracket
  # every outer capture/check. No Event or publication clock is acquired.
  from control_plane.agentos_project_knowledge import capture_selected_project_data_closure,_CaptureFailure
  self._permission_guard(op)
  ancestor=self.publisher._git(['merge-base','--is-ancestor',self.code_commit,canonical],op)
  if ancestor.returncode!=0:_fail()
  try:
   digest=capture_selected_project_data_closure(macro_root=Path(self.publisher._binding.worktree),
    code_root=self.code_root,code_commit=self.code_commit,data_commit=canonical,
    work_ref=op.selected_work_ref,deadline=op.read_deadline)
  except (_CaptureFailure,ImportError,SystemExit):_fail()
  material=dict(schema='mastermind.project_data_continuity.v1',kind='UNCHANGED_SELECTED_PROJECT_DATA',
   work_ref=op.selected_work_ref,principal_scope=op.scope,executable_macro_commit=self.code_commit,
   canonical_data_commit=canonical,reader_closure_sha256=reader_digest,
   selected_data_closure_sha256=digest,ancestry='CODE_ANCESTOR_OF_DATA')
  self._permission_guard(op)
  return _UnchangedProjectDataProof(_SEAL,self,op.principal,op.scope,op.stamp,op.selected_work_ref,
   self.publisher._binding.fingerprint,self.code_root,op.read_deadline,
   json.dumps(material,sort_keys=True,separators=(',',':')).encode())
 def _proof(self,op,canonical,proof,*,verified=None):
  from control_plane.canonical_data_publication import CanonicalDataPublicationProof
  if type(proof) is not CanonicalDataPublicationProof:_fail()
  material=proof.check(op.scope)
  if material['selection']['work_ref']!=op.selected_work_ref:_fail()
  # Only immutable Git facts are memoized, within this one original view's
  # unchanged 15s budget. Actual Event and current authorization are NOT cached.
  key=(self.publisher._binding.fingerprint,canonical,op.scope,op.selected_work_ref,
       hashlib.sha256(json.dumps(material,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).digest())
  if verified is None or key not in verified:
   commit=material['sources'][0]['commit']
   ancestor=self.publisher._git(['merge-base','--is-ancestor',commit,canonical],op)
   if ancestor.returncode!=0:_fail()
   for source in material['sources']:
    raw=self.publisher._read_blob_at(op,canonical,source['path'])
    if raw is None or hashlib.sha256(raw).hexdigest()!=source['content_sha256']:_fail()
   proof.check(op.scope)
   if verified is not None:verified[key]=True
  return material
 def observe(self,principal,*,work_ref=None):
  op=p._Operation(self.publisher._binding);op.mode='canonical_data';op.principal=principal;op.selected_work_ref=work_ref
  op.read_deadline=time.monotonic()+15.0
  try:
   op.scope=self.publisher._principal_scope(principal)
   if not p._is_hex64(op.scope):_fail()
   op.stamp=self.permission(principal,op)
   self.publisher._require_seams();self.publisher._require_qualifier();self._configured(op)
   if self.publisher._check_worktree(op)!='sha1':_fail()
   observed=self.publisher._resolve_default_commit(op)
   # Exact finite compatibility closure, rather than a whole-repository diff:
   # unrelated canonical site/docs/test movement cannot exhaust a read bound.
   paths=[*sorted(_READER_CODE),_SCHEMA_PREFIX]
   closure=self.publisher._git(['ls-tree','-r','-z',self.code_commit,'--',*paths],op)
   compatible=self.publisher._git(['diff-tree','-r','--quiet',self.code_commit,observed,'--',*paths],op)
   if closure.returncode!=0 or compatible.returncode!=0 or len(closure.stdout)>65536:_fail()
   if not closure.stdout or any(re.fullmatch(rb'100(?:644|755) blob [a-f0-9]{40}\t[^\x00\r\n]+',row) is None
       for row in closure.stdout.rstrip(b'\0').split(b'\0')):_fail()
   proof=None;publication=None;verified={};continuity=None
   reader_digest=hashlib.sha256(closure.stdout).hexdigest()
   if observed!=self.code_commit:
    from control_plane.canonical_data_publication import select_source_publication,CanonicalPublicationUnavailable
    try:
     if self.publication is not None:
      if p._callable_identity(self.publication)!=self.publication_identity:_fail()
      proof=self.publication(principal,observed,work_ref)
     else:
      proof=select_source_publication(self.events,work_ref,op.scope,
       qualify=lambda candidate: self._proof(op,observed,candidate,verified=verified) is not None,
       guard=lambda: self._permission_guard(op))
     publication=self._proof(op,observed,proof,verified=verified)
    except CanonicalPublicationUnavailable:
     continuity=self._capture_continuity(op,observed,reader_digest)
   stamp=self.publisher._git(['show','-s','--format=%cI',observed],op)
   if stamp.returncode!=0:_fail()
   committed_at=stamp.stdout.decode('ascii').strip()
   from datetime import datetime
   if datetime.fromisoformat(committed_at.replace('Z','+00:00')).utcoffset() is None:_fail()
   witness=dict(schema='mastermind.canonical_project_data_observation.v1',repository=p.REPOSITORY,default_ref=self.publisher._binding.default_branch,
    executable_macro_commit=self.code_commit,canonical_data_commit=observed,canonical_commit_at=committed_at,
    canonical_observed_at_ms=int(time.time()*1000),publication_recorded_at_ms=None if publication is None else publication['recorded_at_ms'],publication_time=None,
    source_operation=publication,reader_closure_sha256=reader_digest,
    code_config_relation='IDENTICAL_READER_CLOSURE',authority='OBSERVATION_ONLY')
   if continuity is not None:witness['data_continuity']=self._check_continuity(op,observed,continuity)
   view=CanonicalProjectDataView(_SEAL,self,op,observed,self.code_commit,Path(self.publisher._binding.worktree),self.code_root,witness,proof,verified,op.read_deadline,continuity)
   view.check();return view
  except (p._Refusal,p._Unknown,OSError,ValueError,TypeError,KeyError,AttributeError,UnicodeError):_fail()
