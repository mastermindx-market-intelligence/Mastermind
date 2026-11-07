"""Actual temp-Git/Macro parser → incumbent isolated source seals → issued reader."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import pytest
from integrations.executive_mcp.installed import _default_packet_runner
from integrations.executive_mcp.schemas import GatewayError
from control_plane import installed_project_knowledge_readers as readers
from control_plane import agentos_project_knowledge as capture
from tests.test_installed_product_acceptance_context import fixture
from tests.test_agentos_project_knowledge import canonical_workstream,canonical_decision,canonical_discovery,canonical_handoff

OWNER_ROOT=Path(os.environ.get("MM_TEST_MACRO_OWNER_ROOT", "") or "")
pytestmark=pytest.mark.skipif(not (OWNER_ROOT/'scripts/agentos.py').is_file(),reason='Actual Macro owner source not provided')

def bound(tmp_path,monkeypatch,mutation=None):
 collector,_,seen=fixture(tmp_path);macro=seen['macro']
 files={'agentos/workstreams/WS-ALPHA.md':canonical_workstream(),
  'agentos/decisions/DEC-EARLIER-CALL.md':canonical_decision(),
  'agentos/discoveries/DSC-PARSER-LANDMINE.md':canonical_discovery(),
  'agentos/handoffs/HND-ALPHA-2026-02-01.md':canonical_handoff(),
  'research/notes.md':'# Exact retained file\r\nneedle 中文 🧭\r\n'}
 for relative,text in files.items():
  path=macro/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(text.encode())
 (macro/'scripts').mkdir();shutil.copyfile(OWNER_ROOT/'scripts/agentos.py',macro/'scripts/agentos.py')
 subprocess.run(['git','-C',str(macro),'add','.'],check=True,capture_output=True)
 subprocess.run(['git','-C',str(macro),'commit','-qm','canonical Knowledge fixture'],check=True,capture_output=True)
 seen['sha']=subprocess.check_output(['git','-C',str(macro),'rev-parse','HEAD'],text=True).strip()
 seen['record']=macro/'agentos/workstreams/WS-ALPHA.md'
 monkeypatch.setattr(readers,'_SOURCE_ROOT',seen['code'])
 def runner(argv,**limits):
  seen['calls'].append((list(argv),dict(limits)))
  if argv[0]=='git':return _default_packet_runner(argv,**limits)
  operation=argv[argv.index('--operation')+1];child=Path(argv[argv.index('--macro-root')+1]);seen['child_macro']=child
  kwargs=dict(macro_root=child,expected_macro_sha=argv[argv.index('--expected-macro-sha')+1],work_ref=argv[argv.index('--work-ref')+1],timeout=float(argv[argv.index('--timeout')+1]))
  if operation=='project_knowledge_catalogue':value=capture.read_project_knowledge_catalogue(**kwargs)
  elif operation=='project_knowledge_memory':value=capture.read_project_communication_preference(**kwargs)
  else:value=capture.read_project_knowledge_source(**kwargs,source_ref=argv[argv.index('--source-ref')+1],expected_revision=argv[argv.index('--expected-revision')+1])
  if mutation:mutation(value,child,seen)
  return dict(code=0,stdout=json.dumps(value),timed_out=False,limit_exceeded=False,invalid_utf8=False)
 collector._runner=runner
 return collector,seen

def test_actual_canonical_catalogue_memory_and_file_through_sealed_fixed_children(tmp_path,monkeypatch):
 collector,seen=bound(tmp_path,monkeypatch)
 catalogue=collector.project_knowledge_catalogue_reader(macro_root=seen['macro']).read(work_ref='WS:ALPHA')
 assert catalogue['availability']=='AVAILABLE',catalogue
 assert catalogue['source']['commit']==seen['sha'];assert len(catalogue['project']['records'])==4
 row=catalogue['project']['files'][0]
 source=collector.project_knowledge_source_reader(macro_root=seen['macro']).read(work_ref='WS:ALPHA',source_ref=row['source_ref'],expected_revision=row['revision'])
 assert source['document']['content_utf8']=='# Exact retained file\r\nneedle 中文 🧭\r\n'
 assert source['source']['revision']==row['revision']!=seen['sha']
 memory=collector.project_knowledge_memory_reader(macro_root=seen['macro']).read(work_ref='WS:ALPHA');assert memory['availability']=='EMPTY'
 child_calls=[(argv,limits) for argv,limits in seen['calls'] if argv[0]!='git'];assert len(child_calls)==3
 for argv,limits in child_calls:
  assert argv[:4]==[str(seen['python']),'-I','-B',str(seen['code']/'scripts/agentos_project_knowledge_entry.py')]
  assert limits['max_bytes']==131072 and 0<limits['timeout']<=15
 assert not seen['child_macro'].exists();assert not collector._collections

@pytest.mark.parametrize('change',['live','materialized','commit','extra'])
def test_changed_source_or_child_body_never_releases_content(tmp_path,monkeypatch,change):
 def mutate(value,child,seen):
  if change=='commit':value['source']['commit']='f'*40
  elif change=='extra':value['project']['private']='unpublished'
  else:
   path=seen['record'] if change=='live' else child/'agentos/workstreams/WS-ALPHA.md'
   original=path.read_bytes();path.write_bytes(b'transient change\n');path.write_bytes(original)
 collector,seen=bound(tmp_path,monkeypatch,mutate)
 with pytest.raises(GatewayError):collector.project_knowledge_catalogue_reader(macro_root=seen['macro']).read(work_ref='WS:ALPHA')
 assert not seen['child_macro'].exists()

def test_actual_cf1_isolated_child_reads_canonical_source(tmp_path,monkeypatch):
 from ops.executive_os.capacity_source_contract import PYTHON_BINARY
 if not Path(PYTHON_BINARY).is_file():pytest.skip('Incumbent source interpreter not present')
 collector,seen=bound(tmp_path,monkeypatch)
 entry=Path(__file__).resolve().parents[1]/'scripts/agentos_project_knowledge_entry.py'
 run=subprocess.run([str(PYTHON_BINARY),'-I','-B',str(entry),'--macro-root',str(seen['macro']),'--expected-macro-sha',seen['sha'],'--operation','project_knowledge_catalogue','--work-ref','WS:ALPHA'],capture_output=True,text=True,timeout=30)
 assert run.returncode==0,run.stderr;value=json.loads(run.stdout)
 assert value['availability']=='AVAILABLE',value;assert value['source']['commit']==seen['sha'];assert run.stderr==''
