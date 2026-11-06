"""Finite current PLAN/DEC basis captured from an issued canonical data view.

The actual pinned Agent OS parser owns YAML, plan lineage and source refs.
Absence means a complete bounded DEC inventory was qualified; the public
legacy NOT_DECLARED projection is never interpreted as a null predecessor.
"""
from copy import deepcopy
from dataclasses import dataclass,field
import hashlib
import re
import sys
import types
from control_plane.project_canonical_data import CanonicalProjectDataView,CanonicalDataUnavailable
from control_plane import workspace_project_git_publisher as p

_SEAL=object();MACRO=p.REPOSITORY
_ROW=re.compile(rb'100644 blob ([a-f0-9]{40}) +([0-9]+)\t([^\x00\r\n]+)\x00')
class PlanBasisUnavailable(ValueError):pass
def _fail():raise PlanBasisUnavailable('PLAN_BASIS_UNAVAILABLE')
class _Text:
 def __init__(self,raw):self.raw=raw
 def read_text(self,*,encoding):return self.raw.decode(encoding)
def _git(view,args,input_bytes=None,maximum=16777216):
 value=view._owner.publisher._git(args,view._operation,stdin_bytes=input_bytes)
 if value.returncode!=0 or len(value.stdout)>maximum:_fail()
 return value.stdout

def _one(view,commit,path):
 listed=_git(view,['ls-tree','-z',commit,'--',path],maximum=2048)
 if re.fullmatch(rb'100644 blob ([a-f0-9]{40})\t'+re.escape(path.encode())+b'\x00',listed) is None:_fail()
 raw=_git(view,['show',commit+':'+path],maximum=262144)
 return {'source':dict(repository=MACRO,commit=commit,path=path,content_sha256=hashlib.sha256(raw).hexdigest()),'raw_bytes':raw}

def _decision_captures(view):
 raw=_git(view,['--literal-pathspecs','ls-tree','-r','-l','-z',view.data_commit,'--','agentos/decisions/'],maximum=1048576)
 rows=[];position=0;total=0
 while position<len(raw):
  match=_ROW.match(raw,position)
  if match is None:_fail()
  oid,length,path=match.groups();size=int(length);position=match.end();total+=size
  if not 0<size<=262144 or total>16777216 or len(rows)>=4096:_fail()
  if re.fullmatch(rb'agentos/decisions/DEC-[A-Z0-9]+(?:-[A-Z0-9]+)*\.md',path) is None:_fail()
  rows.append((oid,size,path.decode()))
 if not rows:return []
 stream=_git(view,['cat-file','--batch'],b''.join(oid+b'\n' for oid,_,_ in rows),maximum=16777216+409600)
 captures=[];position=0
 for oid,size,path in rows:
  header=oid+b' blob '+str(size).encode()+b'\n'
  if stream[position:position+len(header)]!=header:_fail()
  position+=len(header);body=stream[position:position+size];position+=size
  if stream[position:position+1]!=b'\n' or hashlib.sha1(b'blob '+str(size).encode()+b'\0'+body).hexdigest().encode()!=oid:_fail()
  position+=1;captures.append({'source':dict(repository=MACRO,commit=view.data_commit,path=path,content_sha256=hashlib.sha256(body).hexdigest()),'raw_bytes':body})
 if position!=len(stream):_fail()
 return captures

def _owner(view):
 code={}
 for key,path in [('owner','scripts/agentos.py'),('contract','scripts/agentos_project_plan_contract.py')]:
  raw=_git(view,['show',view.code_commit+':'+path],maximum=1048576)
  module=types.ModuleType('agentos_bound_current_plan_'+key);module.__file__=str(view._code_root/path)
  prior=sys.modules.get(module.__name__);sys.modules[module.__name__]=module;original_path=list(sys.path)
  try:exec(compile(raw,module.__file__,'exec'),module.__dict__)
  finally:
   sys.path[:]=original_path
   if prior is None:sys.modules.pop(module.__name__,None)
   else:sys.modules[module.__name__]=prior
  code[key]=module
 code['owner']._project_plan_contract=lambda:code['contract']
 return code['owner']

@dataclass(frozen=True,slots=True)
class CanonicalProjectPlanBasis:
 _seal:object=field(repr=False)
 _view:CanonicalProjectDataView=field(repr=False)
 _owner:object=field(repr=False)
 _snapshot:dict=field(repr=False)
 _current:object=field(repr=False)
 def check(self):
  if self._seal is not _SEAL:_fail()
  try:self._view.check()
  except (ValueError,p._Refusal,p._Unknown):_fail()
 def material(self):
  self.check();base=self._snapshot['base']['source'];current=self._current
  return dict(schema='mastermind.canonical_project_plan_basis.v1',work_ref=self._snapshot['work_ref'],
   source=deepcopy(self._snapshot['workstream']['source']),base_source=deepcopy(base),
   base_adoption=None if current is None else current['decision_ref'],
   adoption_qualification='QUALIFIED_FULL_DEC_INVENTORY',
   executable_macro_commit=self._view.code_commit,canonical_data_commit=self._view.data_commit)
 def execution_material(self):
  """Private exact authored/adopted bytes from this qualified full inventory."""
  self.check()
  def body(capture):
   return dict(source=deepcopy(capture['source']),content=capture['raw_bytes'].decode('utf-8',errors='strict'))
  current=deepcopy(self._current)
  value=dict(schema='mastermind.project_execution_plan_input.v1',work_ref=self._snapshot['work_ref'],
   authored_record=body(self._snapshot['workstream']),adoption=current,
   adopted_plan=None if current is None else body(self._snapshot['base']),
   decisions=[body(item) for item in self._snapshot['decisions']])
  self.check();return value
 def qualify_creation_source(self,source):
  """Actual historical CREATE marker + current same-work data qualification.

  The existing creation reader validates exact original request bytes/marker,
  historical ancestry and pinned parser/config. A hash or a WS title alone
  cannot replace that owner, nor the original retained publication Event.
  """
  self.check()
  if (type(source) is not dict or set(source)!={'repository','commit','path','content_sha256','request_sha256'}
      or source['repository']!='macro' or source['path']!=self._snapshot['workstream']['source']['path']):_fail()
  from control_plane.agentos_project_creation_source import read_from_macro_owner
  try:
   observed=read_from_macro_owner(macro_root=self._view._root,expected_macro_sha=self._view.data_commit,
    record_commit=source['commit'],work_ref=self._snapshot['work_ref'],_canonical_data_view=self._view)
  except (ValueError,TypeError,KeyError,AttributeError,OSError,UnicodeError):_fail()
  if observed!=source:_fail()
  self.check();return deepcopy(observed)
 def proposal_snapshot(self,*,request_id,evidence=()):
  self.check()
  if type(request_id) is not str or re.fullmatch(r'mmos-project-plan-proposal-[a-f0-9]{40}',request_id) is None or type(evidence) not in (list,tuple) or len(evidence)>32:_fail()
  work=self._snapshot['work_ref'];path='research/project-plans/PLAN-'+work[3:]+'-'+request_id[-40:]+'.md'
  if _git(self._view,['ls-tree','-z',self._view.data_commit,'--',path],maximum=2048):_fail()
  record,_=self._owner.parse_record(_Text(self._snapshot['workstream']['raw_bytes']))
  allowed={ref.removeprefix('macro:') for ref in record.get('artifacts',[]) if type(ref) is str}
  captured=[]
  for value in evidence:
   ref=self._owner._project_plan_contract().validate_source_ref(value)
   if ref['repository']!=MACRO or (ref['path'] not in allowed and re.fullmatch(r'agentos/(?:workstreams/WS|decisions/DEC)-[A-Z0-9]+(?:-[A-Z0-9]+)*\.md',ref['path']) is None):_fail()
   _git(self._view,['merge-base','--is-ancestor',ref['commit'],self._view.data_commit],maximum=2048)
   cap=_one(self._view,ref['commit'],ref['path'])
   if cap['source']!=ref:_fail()
   captured.append(cap)
  return dict(schema='agentos.project_plan_proposal_snapshot.v1',repository=MACRO,commit=self._view.data_commit,
   workstream=deepcopy(self._snapshot['workstream']),decisions=deepcopy(self._snapshot['decisions']),base=deepcopy(self._snapshot['base']),
   proposal_target=dict(path=path,state='ABSENT'),evidence=captured,
   source_binding=self._view.witness())

def capture_current_plan_basis(view,*,work_ref):
 try:
  from common.workspace_project_plan_contract import work_ref_key
  if type(view) is not CanonicalProjectDataView:_fail()
  key=work_ref_key(work_ref);view._require_work(work_ref);view.check();owner=_owner(view)
  ws=_one(view,view.data_commit,'agentos/workstreams/WS-'+key+'.md');record,_=owner.parse_record(_Text(ws['raw_bytes']))
  from pathlib import Path
  if record.get('key')!=key or any(p.hard for p in owner.check_workstream(record,Path(ws['source']['path']),None)):_fail()
  all_decisions=_decision_captures(view);relevant=[];records=[]
  for cap in all_decisions:
   rec,_=owner.parse_record(_Text(cap['raw_bytes']))
   if cap['source']['path']!='agentos/decisions/DEC-'+str(rec.get('key'))+'.md' or any(p.hard for p in owner.check_decision(rec,Path(cap['source']['path']))):_fail()
   if work_ref in (rec.get('affects') or []) or (rec.get('project_plan_adoption') or {}).get('work_ref')==work_ref:
    relevant.append(cap);records.append(rec)
  if len(relevant)>128:_fail()
  current=owner.select_project_plan_adoption(records,work_ref=work_ref)
  base=ws
  if current is not None:
   ref=current['adoption']['adopted_source']
   if ref['repository']!=MACRO:_fail()
   _git(view,['merge-base','--is-ancestor',ref['commit'],view.data_commit],maximum=2048)
   base=_one(view,ref['commit'],ref['path'])
   if base['source']!=ref:_fail()
  view.check()
  return CanonicalProjectPlanBasis(_SEAL,view,owner,dict(work_ref=work_ref,workstream=ws,decisions=relevant,base=base),deepcopy(current))
 except (CanonicalDataUnavailable,ValueError,TypeError,KeyError,AttributeError,OSError,UnicodeError,SyntaxError,RecursionError,OverflowError,p._Refusal,p._Unknown):_fail()


# Current project-file DATA for initial planning. This stays in the same fixed
# CODE owner already imported for historical CREATE/canonical-basis joins.
import json as _file_json
from common.workspace_project_knowledge_contract import validate_catalogue, validate_source
from control_plane.terminal_original_input_artifacts import MAX_PAYLOAD_BYTES

_FILE_CONTEXT_SEAL = object()


def _file_context_fail():
    raise ValueError('PROJECT_PLANNING_FILE_CONTEXT_UNAVAILABLE')


def _file_context_canonical(value):
    return _file_json.dumps(value, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=False, allow_nan=False).encode('utf-8')


@dataclass(frozen=True, slots=True)
class ProjectPlanningFileContext:
    _seal: object = field(repr=False)
    _view: CanonicalProjectDataView = field(repr=False)
    _identity: tuple = field(repr=False)
    _material: bytes = field(repr=False)

    def check(self):
        if self._seal is not _FILE_CONTEXT_SEAL or type(self._view) is not CanonicalProjectDataView:
            _file_context_fail()
        view = self._view
        if view._owner._view_identity(view) != self._identity:
            _file_context_fail()
        # Actual current principal/grants/default/Event checks and original
        # expiry remain owned by this SAME view; no replacement is acquired.
        view.check()
        if view._owner._view_identity(view) != self._identity:
            _file_context_fail()

    def material(self):
        self.check()
        return _file_json.loads(self._material)


def capture_current_project_files(view, *, work_ref):
    """Eager, bounded, same-view file capture; return only after its postcheck.

    All declared files must be readable and completely listed. An unavailable
    body or over-budget payload is refused, never omitted from planning.
    """
    if type(view) is not CanonicalProjectDataView:
        _file_context_fail()
    view._require_work(work_ref)
    view.check()
    identity = view._owner._view_identity(view)
    with view.capture_scope():
        catalogue = validate_catalogue(view.read_knowledge_catalogue(work_ref=work_ref))
        if (catalogue['availability'] != 'AVAILABLE'
                or catalogue['selection'] != {'work_ref': work_ref}
                or catalogue['source']['commit'] != view.data_commit):
            _file_context_fail()
        project = catalogue['project']
        coverage = project['coverage']['files']
        if (coverage['state'] != 'COMPLETE' or coverage['omitted'] != 0
                or coverage['declared'] != len(project['files'])):
            _file_context_fail()
        workspace_source = None
        if project['files']:
            publication = view.witness()['source_operation']
            if (publication is None or publication['selection']['action'] != 'add_project_file'
                    or publication['selection']['work_ref'] != work_ref):
                _file_context_fail()
            ws_path = 'agentos/workstreams/WS-' + work_ref[3:] + '.md'
            ws_images = [source for source in publication['sources'] if source['path'] == ws_path]
            if (len(ws_images) != 1
                    or ws_images[0]['content_sha256'] != catalogue['source']['workstream_sha256']):
                _file_context_fail()
            # The nominal view independently proved these postimage bytes at
            # CURRENT N; retain the original Event rather than relabel its clock.
            workspace_source = dict(repository='mastermindx-market-intelligence/macro',
                commit=view.data_commit, path=ws_path,
                content_sha256=catalogue['source']['workstream_sha256'])
        files = []
        seen = set()
        for row in project['files']:
            if (row['state'] != 'READABLE' or row['repository'] != 'macro'
                    or row['source_ref'] in seen):
                _file_context_fail()
            seen.add(row['source_ref'])
            source = validate_source(view.read_knowledge_source(work_ref=work_ref,
                source_ref=row['source_ref'], expected_revision=row['revision']))
            if (source['availability'] != 'AVAILABLE'
                    or source['selection'] != {'work_ref': work_ref, 'source_ref': row['source_ref']}):
                _file_context_fail()
            pointer, document = source['source'], source['document']
            if (pointer['repository'] != 'mastermindx-market-intelligence/macro'
                    or pointer['commit'] != view.data_commit
                    or pointer['path'] != row['path'] or pointer['revision'] != row['revision']
                    or pointer['content_sha256'] != row['content_sha256']
                    or document['content_sha256'] != row['content_sha256']
                    or document['media_type'] != row['media_type']):
                _file_context_fail()
            files.append(dict(source_ref=row['source_ref'], display_name=row['display_name'],
                source=deepcopy(pointer), media_type=document['media_type'],
                content_utf8=document['content_utf8']))
        material = _file_context_canonical(dict(schema='mastermind.project_planning_file_context.v1',
            authority='UNTRUSTED_PROJECT_DATA', work_ref=work_ref,
            executable_macro_commit=view.code_commit, canonical_data_commit=view.data_commit,
            workspace_source=workspace_source, files=files))
        if len(material) > MAX_PAYLOAD_BYTES:
            _file_context_fail()
        if view._owner._view_identity(view) != identity:
            _file_context_fail()
    # No eager file DATA or capability escapes an unsuccessful outer postcheck.
    value = ProjectPlanningFileContext(_FILE_CONTEXT_SEAL, view, identity, material)
    value.check()
    return value
