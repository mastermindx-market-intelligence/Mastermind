"""New fixed Knowledge issuers retain original opaque composition fences."""
import copy
from types import SimpleNamespace
import pytest
from common import workspace_project_knowledge_read_contract as wire
from control_plane import installed_project_knowledge_readers as readers
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from tests.test_installed_product_acceptance_context import fixture

KINDS = [
    ("project_knowledge_catalogue", readers.AgentOsProjectKnowledgeCatalogueReader),
    ("project_knowledge_memory", readers.AgentOsProjectKnowledgeMemoryReader),
    ("project_knowledge_source", readers.AgentOsProjectKnowledgeSourceReader),
]
SOURCE = {"source_ref": "project-file.v1."+"a"*64, "expected_revision":"b"*40}

@pytest.fixture(params=KINDS)
def issued(request,tmp_path,monkeypatch):
    kind,reader_type=request.param
    collector,_,seen=fixture(tmp_path)
    monkeypatch.setattr(readers,"_SOURCE_ROOT",seen["code"])
    calls=[]; marker={"owned":True}
    def read(owner,**kwargs): calls.append(kwargs); return marker
    monkeypatch.setattr(InstalledBootPacketCollector,"read_"+kind,read)
    reader=getattr(collector,kind+"_reader")(macro_root=seen["macro"])
    selected={"work_ref":"WS:ONE",**(SOURCE if kind.endswith("_source") else {})}
    return SimpleNamespace(kind=kind,reader_type=reader_type,reader=reader,collector=collector,
        seen=seen,calls=calls,marker=marker,selected=selected)

def test_exact_current_issued_reader(issued):
    assert issued.reader.read(**issued.selected) is issued.marker
    assert issued.calls==[issued.selected]

@pytest.mark.parametrize("replacement",["bare","label","copied","other_owner"])
def test_not_transferable_or_mintable(issued,replacement):
    reader=issued.reader_type(macro_root=issued.seen["macro"])
    reader._installed_context_owner=issued.collector
    reader._installed_context_binding=issued.reader._installed_context_binding
    if replacement=="label":reader._installed_reader_binding=SimpleNamespace(issued=True)
    if replacement in ("copied","other_owner"):reader._installed_reader_binding=issued.reader._installed_reader_binding
    if replacement=="other_owner":reader._installed_context_owner=copy.copy(issued.collector)
    with pytest.raises(readers.ProjectKnowledgeSourceUnavailable):reader.read(**issued.selected)
    assert issued.calls==[]

def test_callback_replacement_never_called(issued,monkeypatch):
    monkeypatch.setattr(InstalledBootPacketCollector,"read_"+issued.kind,lambda *a,**kw:pytest.fail("changed callback"))
    with pytest.raises(readers.ProjectKnowledgeSourceUnavailable):issued.reader.read(**issued.selected)
    assert issued.calls==[]

def test_source_changed_before_read(issued):
    issued.collector._expected_source_sha="f"*40
    with pytest.raises(readers.ProjectKnowledgeSourceUnavailable):issued.reader.read(**issued.selected)
    assert issued.calls==[]

def test_source_changed_during_read_discards_body(issued,monkeypatch):
    def mutate(owner,**kwargs):owner._expected_source_sha="f"*40;return {"private":"must not return"}
    monkeypatch.setattr(InstalledBootPacketCollector,"read_"+issued.kind,mutate)
    reader=getattr(issued.collector,issued.kind+"_reader")(macro_root=issued.seen["macro"])
    with pytest.raises(readers.ProjectKnowledgeSourceUnavailable):reader.read(**issued.selected)

@pytest.mark.parametrize("extra",[{"path":"docs/private.md"},{"root_job_id":"JOB-1"},{"principal":"someone"},{"expected_revision":"a"*40+"\n"},{"source_ref":"https://example.com/private"}])
def test_fixed_source_selector_closed(extra):
    selected={"work_ref":"WS:ONE",**SOURCE,**extra}
    with pytest.raises(ValueError):wire.selection(selected,operation="project_knowledge_source")

@pytest.mark.parametrize("operation",["project_knowledge_catalogue","project_knowledge_memory"])
def test_rootless_catalogue_and_memory_have_only_work(operation):
    assert wire.selection({"work_ref":"WS:ONE"},operation=operation)=={"work_ref":"WS:ONE"}
    with pytest.raises(ValueError):wire.selection({"work_ref":"WS:ONE",**SOURCE},operation=operation)
