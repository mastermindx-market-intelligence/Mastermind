"""Fixed Knowledge service and signed HTTP joins; isolated owners, no live effects."""
import asyncio
import hashlib
from pathlib import Path
import pytest
from common import executive_workspace_contract as workspace
from common import workspace_project_knowledge_read_contract as wire
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane import installed_project_knowledge_readers as readers
from tests.test_workspace_read_service import cache_fixture,frame
from tests.test_workspace_read_app import rsa_key,_make_app,_workspace_token

WORK="WS:ONE"; COMMIT="a"*40; REV="b"*40; REF="project-file.v1."+"c"*64
TEXT="# Original source\r\nneedle 原文 🧭\r\n"; SHA=hashlib.sha256(TEXT.encode()).hexdigest(); PATH="docs/owner.md"
OPERATIONS=("project_knowledge_catalogue","project_knowledge_memory","project_knowledge_source")
ROUTES=("/workspace/project-knowledge/current","/workspace/project-memory/current","/workspace/project-source/current")
TYPES=(readers.AgentOsProjectKnowledgeCatalogueReader,readers.AgentOsProjectKnowledgeMemoryReader,readers.AgentOsProjectKnowledgeSourceReader)

def selected(operation):return dict(work_ref=WORK,**({"source_ref":REF,"expected_revision":REV} if operation.endswith("_source") else {}))
def request(operation):
 value=frame();value.update(schema=wire.FRAME_SCHEMA,operation=operation,selection=selected(operation));return value

def body(operation):
 origin=dict(repository="mastermindx-market-intelligence/macro",commit=COMMIT,path=PATH,revision=REV,content_sha256=SHA,committed_at="2026-11-04T00:00:00Z")
 if operation.endswith("_source"):
  return dict(schema="mastermind.workspace_project_source.v1",selection={"work_ref":WORK,"source_ref":REF},availability="AVAILABLE",reason_codes=[],source=origin,document=dict(title="owner.md",media_type="text/markdown",content_utf8=TEXT,content_sha256=SHA))
 if operation.endswith("_memory"):
  return dict(schema="mastermind.workspace_project_preference.v1",selection={"work_ref":WORK},availability="EMPTY",reason_codes=[],source=None,memory=None)
 return dict(schema="mastermind.workspace_project_knowledge.v1",selection={"work_ref":WORK},availability="AVAILABLE",reason_codes=[],source=dict(repository=origin["repository"],commit=COMMIT,workstream_sha256="d"*64),project=dict(title="Owner project",files=[dict(source_ref=REF,repository="macro",path=PATH,revision=REV,display_name="owner.md",media_type="text/markdown",content_sha256=SHA,state="READABLE",origin=dict(kind="DECLARED_ARTIFACT",actor_ref=None,request_sha256=None),viewer_relation="UNKNOWN")],records=[],memory=dict(state="EMPTY",source_ref=None,revision=None),coverage=dict(files=dict(state="COMPLETE",declared=1,listed=1,omitted=0),records=dict(state="BOUNDED_SAMPLE",scanned=1,matched=0,omitted=0,invalid=0))))

def provider(tmp_path,monkeypatch,operation,authorize=lambda _:True,after=None):
 owners,clock,cache=cache_fixture(tmp_path);owners[0].state_cache["doc"]["sources"]={"macro_sha":COMMIT}
 reader_type=TYPES[OPERATIONS.index(operation)];reader=reader_type(macro_root=Path("/qualified/macro"));calls=[]
 def acquire(self,**kwargs):
  calls.append(kwargs);value=body(operation)
  if after:after(owners,value)
  return value
 monkeypatch.setattr(reader_type,"read",acquire)
 class RuntimeForbidden:
  def __getattr__(self,name):pytest.fail("Knowledge READ must not use Runtime")
 service=WorkspaceReadService(cache=cache,runtime=RuntimeForbidden(),authorize=authorize,armed={},runtime_identity={},**{operation+"_reader":reader})
 return service,owners,calls

@pytest.mark.parametrize("operation",OPERATIONS)
def test_rootless_fixed_read_joins_existing_project_without_runtime(tmp_path,monkeypatch,operation):
 service,_,calls=provider(tmp_path,monkeypatch,operation);result=asyncio.run(service.handle_frame(request(operation)))
 assert result=={"ok":True,"result":body(operation)};assert calls==[selected(operation)]

@pytest.mark.parametrize("operation",OPERATIONS)
def test_permission_refusal_never_reads_source(tmp_path,monkeypatch,operation):
 service,_,calls=provider(tmp_path,monkeypatch,operation,authorize=lambda _:False)
 assert asyncio.run(service.handle_frame(request(operation)))==workspace.error("access_denied",403);assert calls==[]

@pytest.mark.parametrize("change",["revocation","stamp","publication","macro","document","wrong_selection","wrong_revision"])
def test_adverse_after_source_discards_private_body(tmp_path,monkeypatch,change):
 allowed=[True];stamp=["a"*64]
 def authorize(_):return allowed[0]
 authorize.binding_digest=lambda _:stamp[0]
 def mutate(owners,value):
  if change=="revocation":allowed[0]=False
  if change=="stamp":stamp[0]="b"*64
  if change=="publication":owners[0].state_published_seq+=1
  if change=="macro":owners[0].state_cache["doc"]["sources"]["macro_sha"]="e"*40
  if change=="document":owners[0].state_cache["doc"]["work"][0]["agent_os"]["title"]="Changed"
  if change=="wrong_selection":value["selection"]["work_ref"]="WS:OTHER"
  if change=="wrong_revision":value["source"]["revision"]="e"*40
 operation=OPERATIONS[2];service,_,calls=provider(tmp_path,monkeypatch,operation,authorize=authorize,after=mutate)
 result=asyncio.run(service.handle_frame(request(operation)));assert calls
 if change in ("revocation","stamp"):assert result==workspace.error("access_denied",403)
 else:assert result["result"]["availability"]=="UNAVAILABLE";assert result["result"]["document"] is None
 assert TEXT not in str(result)

def test_unknown_project_never_reaches_source(tmp_path,monkeypatch):
 operation=OPERATIONS[0];service,_,calls=provider(tmp_path,monkeypatch,operation);value=request(operation);value["selection"]={"work_ref":"WS:OTHER"}
 assert asyncio.run(service.handle_frame(value))==workspace.error("selection_not_found",404);assert calls==[]

@pytest.mark.parametrize("operation,route",zip(OPERATIONS,ROUTES))
def test_signed_fixed_http_route_and_full_service_join(tmp_path,monkeypatch,rsa_key,operation,route):
 service,_,calls=provider(tmp_path,monkeypatch,operation)
 class Client:
  async def request(self,frame):return await service.handle_frame(dict(frame))
 client,_=_make_app(rsa_key,client=Client());response=client.get(route,params=selected(operation),headers={"Authorization":"Bearer "+_workspace_token(rsa_key)})
 assert response.status_code==200,response.text;assert response.json()==body(operation);assert calls==[selected(operation)]
 assert "no-store" in response.headers["cache-control"]

@pytest.mark.parametrize("route",ROUTES)
def test_anonymous_get_has_no_owner_read(rsa_key,route):
 client,fake=_make_app(rsa_key);assert client.get(route,params={"work_ref":WORK}).status_code==401;assert fake.calls==[]

@pytest.mark.parametrize("query",["?work_ref=WS:ONE&path=docs/private.md","?work_ref=WS:ONE&root_job_id=JOB-1","?work_ref=WS:ONE&work_ref=WS:OTHER","?work_ref=../private"])
def test_invalid_selector_never_dispatches_owner(rsa_key,query):
 client,fake=_make_app(rsa_key);response=client.get(ROUTES[0]+query,headers={"Authorization":"Bearer "+_workspace_token(rsa_key)})
 assert response.status_code==400;assert fake.calls==[]
