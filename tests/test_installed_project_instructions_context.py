"""Actual canonical Git/helper/parser sealed read; no installed/live source claim."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zlib
import pytest
from control_plane import agentos_project_instructions as owner
from integrations.executive_mcp.installed import _default_packet_runner
from integrations.executive_mcp.schemas import GatewayError
from tests.test_installed_project_plan_context import bound as plan_bound


def bound(tmp_path,monkeypatch,field="supplied",mutation=None):
    collector,seen=plan_bound(tmp_path,monkeypatch)
    parser_fixture=json.loads((Path(__file__).parent/'fixtures/agentos-standing-instructions-parser-46e3fa6f.json').read_bytes())
    parser_raw=zlib.decompress(base64.b64decode(parser_fixture['zlib_base64'],validate=True))
    assert hashlib.sha256(parser_raw).hexdigest()==parser_fixture['sha256']=='acf3d970decb0b0c79b536bcc4e64cca93adace078321156fa72ff29c73f64a3'
    (seen['macro']/'scripts/agentos.py').write_bytes(parser_raw)
    fixture=json.loads((Path(__file__).parent/'fixtures/standing-instructions-projector-020942ab.json').read_bytes())
    raw=zlib.decompress(base64.b64decode(fixture['zlib_base64'],validate=True));assert hashlib.sha256(raw).hexdigest()==fixture['sha256']=='020942abf1b3faf5c7982269744c3869b0750dc3c3ad0e3ca740d9a6d6a8ea84'
    (seen['macro']/'scripts/agentos_standing_instructions.py').write_bytes(raw)
    record=seen['record'];text=record.read_text()
    extra="standing_instructions:\n  - instruction_ref: INS:DAILY-ONE\n    text: 'Review the project carefully.'\n" if field=="supplied" else "standing_instructions: []\n" if field=="empty" else ""
    record.write_text(text.replace('next_action:',extra+'next_action:'))
    subprocess.run(['git','-C',str(seen['macro']),'add','.'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(seen['macro']),'commit','-qm','canonical instruction source fixture'],check=True,capture_output=True)
    seen['sha']=subprocess.check_output(['git','-C',str(seen['macro']),'rev-parse','HEAD'],text=True).strip()
    monkeypatch.setattr(owner,'_SOURCE_ROOT',seen['code'])
    def runner(argv,**limits):
        seen['calls'].append((list(argv),dict(limits)))
        if argv[0]=='git':return _default_packet_runner(argv,**limits)
        child=Path(argv[argv.index('--macro-root')+1]);seen['child_macro']=child
        value=owner.read_from_macro_owner(macro_root=child,expected_macro_sha=argv[argv.index('--expected-macro-sha')+1],work_ref=argv[argv.index('--work-ref')+1],timeout=float(argv[-1]))
        if mutation:mutation(value,child,seen)
        return dict(code=0,stdout=json.dumps(value),timed_out=False,limit_exceeded=False,invalid_utf8=False)
    collector._runner=runner
    return collector,seen


@pytest.mark.parametrize('field,declaration,count',[('supplied','SUPPLIED',1),('empty','SUPPLIED',0),('absent','NOT_DECLARED',0)])
def test_actual_git_parser_helper_and_sealed_current_source(tmp_path,monkeypatch,field,declaration,count):
    collector,seen=bound(tmp_path,monkeypatch,field)
    value=collector.project_instructions_reader(macro_root=seen['macro']).read(work_ref='WS:ONE')
    assert value['availability']=='AVAILABLE',value
    assert value['declaration']==declaration and len(value['instructions'])==count
    assert value['source']['commit']==seen['sha']
    assert value['source']['content_sha256']==hashlib.sha256(seen['record'].read_bytes()).hexdigest()
    if count:assert value['instructions'][0]['text']=='Review the project carefully.'
    assert not collector._collections and not seen['child_macro'].exists()
    child=[(argv,limits) for argv,limits in seen['calls'] if argv[0]!='git'];assert len(child)==1
    assert child[0][0][:4]==[str(seen['python']),'-I','-B',str(seen['code']/'scripts/agentos_project_instructions_entry.py')]
    assert child[0][1]['max_bytes']==32768


@pytest.mark.parametrize('target',['body','commit','live','materialized'])
def test_late_source_change_or_foreign_body_is_not_published(tmp_path,monkeypatch,target):
    def mutation(value,child,seen):
        if target=='body':value['instructions'].append({'instruction_ref':'INS:FORGED','text':'forged','revision':'f'*64})
        elif target=='commit':value['source']['commit']='f'*40
        else:
            path=seen['record'] if target=='live' else child/'agentos/workstreams/WS-ONE.md';raw=path.read_bytes();path.write_bytes(b'changed');path.write_bytes(raw)
    collector,seen=bound(tmp_path,monkeypatch,mutation=mutation)
    with pytest.raises(GatewayError):collector.project_instructions_reader(macro_root=seen['macro']).read(work_ref='WS:ONE')


@pytest.mark.parametrize('target',['detached','source','python','method'])
def test_public_constructor_and_detached_or_retargeted_owner_never_acquire_source(tmp_path,monkeypatch,target):
    collector,seen=bound(tmp_path,monkeypatch)
    reader=collector.project_instructions_reader(macro_root=seen['macro'])
    if target=='detached':reader=owner.AgentOsProjectInstructionsReader(macro_root=seen['macro'])
    elif target=='source':collector._expected_source_sha='f'*40
    elif target=='python':collector._python=Path('/foreign/python')
    else:collector.read_project_instructions=lambda **kw:None
    with pytest.raises(owner.ProjectInstructionsSourceUnavailable):reader.read(work_ref='WS:ONE')
    assert seen['calls']==[]


def test_fixed_child_complete_python_and_missing_dependency_are_closed(tmp_path,monkeypatch):
    from ops.executive_os.capacity_source_contract import PYTHON_BINARY
    _,seen=bound(tmp_path,monkeypatch)
    entry=Path(__file__).resolve().parents[1]/'scripts/agentos_project_instructions_entry.py'
    for missing in [False,True]:
        python=Path(sys.executable) if missing or not PYTHON_BINARY.is_file() else PYTHON_BINARY
        argv=[str(python),'-I',*(['-S'] if missing else []),'-B',str(entry),'--macro-root',str(seen['macro']),'--expected-macro-sha',seen['sha'],'--work-ref','WS:ONE','--timeout','10']
        result=subprocess.run(argv,capture_output=True,timeout=15,env=dict(os.environ,GIT_NO_LAZY_FETCH='1'))
        assert result.returncode==0,result.stderr
        value=json.loads(result.stdout);assert value['availability']==('UNAVAILABLE' if missing else 'AVAILABLE'),value
        assert len(result.stdout)<=32768 and result.stderr==b'' and b'PyYAML' not in result.stdout and b'Private body' not in result.stdout
