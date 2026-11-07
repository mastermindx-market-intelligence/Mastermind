"""Exact control guard and bounded private pipe transport; no auth claim."""
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
CONTROL_FILES=('common/workspace_project_knowledge_contract.py',
    'control_plane/agentos_project_knowledge.py','control_plane/agentos_project_knowledge_recipe.py')
OLD=re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]')


def test_control_ranges_exhaustively_preserve_all_unicode_and_exact_control_set():
    patterns=[]
    for name in CONTROL_FILES:
        tree=ast.parse((ROOT/name).read_bytes())
        node=next(n for n in tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='_CONTROL' for t in n.targets))
        patterns.append(re.compile(ast.literal_eval(node.value.args[0])))
    refused=[]
    for ordinal in range(sys.maxunicode+1):
        text=chr(ordinal);expected=OLD.search(text) is not None
        assert all((pattern.search(text) is not None)==expected for pattern in patterns)
        if expected:refused.append(ordinal)
    assert refused==list(range(9))+[11,12]+list(range(14,32))+list(range(127,160))
    assert all(not pattern.search('\t\r\n中文🌊') for pattern in patterns)


@pytest.fixture
def entry():
    spec=importlib.util.spec_from_file_location('knowledge_protocol_test_entry',ROOT/'scripts/agentos_project_knowledge_recipe_entry.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class PipeOutput:
    def __init__(self,fd,mode='complete'):
        self.raw=os.fdopen(fd,'wb',buffering=0);self.mode=mode;self.buffer=self
    def fileno(self):return self.raw.fileno()
    def flush(self):self.raw.flush()
    def write(self,packet):
        if self.mode=='error':raise OSError('private failure canary must not be echoed')
        if self.mode=='partial':return self.raw.write(packet[:5])
        return self.raw.write(packet)
    def close(self):self.raw.close()


def invoke(entry,monkeypatch,stdout,*,payload=None):
    from control_plane import agentos_project_knowledge_recipe as engine
    body={'schema':entry.CAPTURE_REQUEST_SCHEMA,'request':{},'trusted':{
        'actor_ref':'workspace:'+'a'*64,'permission_binding_digest':'b'*64,'decision_date':'2026-11-05'}}
    stdin=io.TextIOWrapper(io.BytesIO(json.dumps(body).encode()),encoding='utf-8')
    stderr=io.StringIO();calls=[]
    if payload is None:payload={'schema':'test-only-protocol-frame','private_body':'literal 文 🌊\r\n','digest':'b'*64}
    def compiler(**kwargs):
        calls.append(True)
        print('private compiler diagnostic canary')
        print('private compiler error canary',file=sys.stderr)
        return payload
    monkeypatch.setattr(engine,'compile_project_knowledge_recipe',compiler)
    monkeypatch.setattr(sys,'argv',['entry','--macro-root','/never-read','--expected-macro-sha','a'*40,'--mode','prepare'])
    monkeypatch.setattr(sys,'stdin',stdin);monkeypatch.setattr(sys,'stdout',stdout);monkeypatch.setattr(sys,'stderr',stderr)
    try:code=entry.main()
    except SystemExit as exc:code=exc.code
    except BaseException:
        try:entry._refuse()
        except SystemExit as exc:code=exc.code
    return code,stderr.getvalue(),calls,stdin


def test_private_pipe_protocol_is_exact_canonical_utf8_not_diagnostics(entry,monkeypatch):
    read,write=os.pipe();output=PipeOutput(write)
    payload={'schema':'test-only-protocol-frame','private_body':'literal 文 🌊\r\n','digest':'b'*64}
    try:
        code,stderr,calls,_=invoke(entry,monkeypatch,output,payload=payload)
    finally:output.close()
    with os.fdopen(read,'rb') as stream:packet=stream.read()
    assert code==0 and calls==[True] and stderr==''
    assert packet==(json.dumps(payload,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':'))+'\n').encode('utf-8')
    assert packet.count(b'\n')==1 and b'compiler' not in packet


@pytest.mark.parametrize('destination',['file','tty','invalid'])
def test_non_pipe_output_refuses_before_private_frame_or_compile(entry,monkeypatch,tmp_path,destination):
    master=None
    if destination=='file':output=(tmp_path/'accidental-log').open('w+')
    elif destination=='tty':master,slave=os.openpty();output=os.fdopen(slave,'w')
    else:output=io.StringIO()
    try:
        code,stderr,calls,stdin=invoke(entry,monkeypatch,output)
        assert code==2 and stderr=='project_knowledge_recipe_unavailable\n' and calls==[]
        assert stdin.buffer.tell()==0
        if destination=='file':output.seek(0);assert output.read()==''
        elif destination=='invalid':assert output.getvalue()==''
    finally:
        output.close()
        if master is not None:os.close(master)


@pytest.mark.parametrize('failure',['partial','error','limit'])
def test_partial_error_and_oversized_frame_refuse_without_private_diagnostic_echo(entry,monkeypatch,failure):
    read,write=os.pipe();output=PipeOutput(write,mode=failure)
    payload={'value':'x'*(entry.RESULT_LIMIT+1)} if failure=='limit' else None
    try:code,stderr,calls,_=invoke(entry,monkeypatch,output,payload=payload)
    finally:output.close()
    with os.fdopen(read,'rb') as stream:packet=stream.read()
    assert code==2 and calls==[True] and stderr=='project_knowledge_recipe_unavailable\n'
    assert packet==(b'{"dig' if failure=='partial' else b'')
    assert b'canary' not in packet


@pytest.mark.parametrize('destination',['file','tty'])
def test_real_child_rejects_nonpipe_before_blocked_private_stdin(destination,tmp_path):
    import errno
    import subprocess
    read,write=os.pipe();master=slave=None
    path=tmp_path/'accidental-log'
    output=path.open('wb') if destination=='file' else None
    if destination=='tty':master,slave=os.openpty()
    process=None
    try:
        # Keep the input pipe OPEN without a frame. Reading private stdin
        # before rejecting the output mode would block and fail this deadline.
        process=subprocess.Popen([sys.executable,str(ROOT/'scripts/agentos_project_knowledge_recipe_entry.py'),
            '--macro-root',str(tmp_path/'never-compiled'),'--expected-macro-sha','a'*40,'--mode','prepare'],
            stdin=read,stdout=output if output is not None else slave,stderr=subprocess.PIPE)
        assert process.wait(timeout=5)==2
        assert process.stderr.read()==b'project_knowledge_recipe_unavailable\n'
        if output is not None:output.flush();assert path.read_bytes()==b''
        else:
            os.set_blocking(master,False)
            try:assert os.read(master,4096)==b''
            except (BlockingIOError,OSError) as exc:
                assert exc.errno in (errno.EAGAIN,errno.EWOULDBLOCK,errno.EIO)
    finally:
        if process is not None:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            process.stderr.close()
        os.close(read);os.close(write)
        if output is not None:output.close()
        if master is not None:os.close(master);os.close(slave)


def test_pipe_stdout_cannot_substitute_a_different_buffer_sink(entry,monkeypatch,tmp_path):
    read,write=os.pipe();pipe=PipeOutput(write)
    with (tmp_path/'alternate-log').open('wb') as alternate:
        pipe.buffer=alternate
        try:
            code,stderr,calls,stdin=invoke(entry,monkeypatch,pipe)
            assert code==2 and calls==[] and stdin.buffer.tell()==0
            assert stderr=='project_knowledge_recipe_unavailable\n'
            assert alternate.tell()==0
        finally:pipe.close();os.close(read)


def test_real_fixed_child_uses_actual_bounded_pipe_consumer(tmp_path):
    import hashlib
    import subprocess
    from tests.test_agentos_project_knowledge_recipe import (owner_bytes,canonical_workstream,
        earlier_decision,_file_request,ACTOR_REF,BINDING_DIGEST,DECISION_DATE)
    from control_plane.ceo_boot_packet import bounded_subprocess_runner
    root=tmp_path/'macro';(root/'scripts').mkdir(parents=True)
    for relative in ('scripts/agentos.py','scripts/project_knowledge_recipes.py'):
        (root/relative).write_text(owner_bytes(relative),encoding='utf-8')
    ws=canonical_workstream();path=root/'agentos/workstreams/WS-ALPHA.md'
    path.parent.mkdir(parents=True);path.write_text(ws,encoding='utf-8')
    path=root/'agentos/decisions/DEC-EARLIER-CALL.md';path.parent.mkdir(parents=True)
    path.write_text(earlier_decision(),encoding='utf-8')
    env=dict(os.environ,GIT_AUTHOR_NAME='source-test',GIT_AUTHOR_EMAIL='test@example.invalid',
        GIT_COMMITTER_NAME='source-test',GIT_COMMITTER_EMAIL='test@example.invalid')
    for args in (['init','-q'],['add','.'],['commit','-qm','actual protected compiler fixture']):
        subprocess.run(['git',*args],cwd=root,env=env,check=True,capture_output=True,timeout=30)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    request=_file_request('notes.md','Literal protocol body 文 🌊\r\n')
    request.update(source_commit=commit,base_revision=hashlib.sha256(ws.encode()).hexdigest())
    frame=dict(schema='mastermind.project_knowledge_recipe_capture_request.v1',request=request,
        trusted=dict(actor_ref=ACTOR_REF,permission_binding_digest=BINDING_DIGEST,decision_date=DECISION_DATE))
    argv=[sys.executable,'-I','-B',str(ROOT/'scripts/agentos_project_knowledge_recipe_entry.py'),
        '--macro-root',str(root),'--expected-macro-sha',commit,'--mode','prepare','--timeout','10']
    result=bounded_subprocess_runner(argv,cwd=ROOT,timeout=15,max_bytes=524288,
        input_bytes=json.dumps(frame,ensure_ascii=False).encode())
    assert result['code']==0 and result['stderr']==''
    assert not any(result.get(k) for k in ('timed_out','limit_exceeded','invalid_utf8'))
    capture=json.loads(result['stdout'])
    assert capture['schema']=='mastermind.project_knowledge_recipe_capture.v1'
    assert capture['recipe']['state']=='DRAFT_ONLY'
    assert result['stdout']==json.dumps(capture,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':'))+'\n'
    frame.update(initial_snapshot=capture['initial_snapshot'],source_binding=capture['source_binding'])
    argv[argv.index('prepare')]='restore'
    restored=bounded_subprocess_runner(argv,cwd=ROOT,timeout=15,max_bytes=524288,input_bytes=json.dumps(frame).encode())
    assert restored['code']==0 and restored['stderr']==''
    assert json.loads(restored['stdout'])['recipe']==capture['recipe']


@pytest.mark.parametrize('excess',[0,1],ids=['complete-frame-exact-limit','complete-frame-one-byte-over'])
def test_real_pipe_complete_frame_limit_includes_lf(excess):
    from control_plane.ceo_boot_packet import bounded_subprocess_runner
    # This synthetic compiler payload tests transport only; it issues no
    # nominal source proof. The actual entry writer and installed bounded
    # consumer run as real subprocess/pipe endpoints with the unchanged cap.
    harness=r'''
import importlib.util,json,sys
from pathlib import Path
root=Path(sys.argv[1]);excess=int(sys.argv[2])
spec=importlib.util.spec_from_file_location('boundary_entry',root/'scripts/agentos_project_knowledge_recipe_entry.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
from control_plane import agentos_project_knowledge_recipe as engine
payload={'schema':'mastermind.project_knowledge_recipe_capture.v1','recipe':{},'initial_snapshot':{'padding':''},'source_binding':{}}
base=len((json.dumps(payload,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':'))+'\n').encode())
payload['initial_snapshot']['padding']='x'*(entry.RESULT_LIMIT-base+excess)
engine.compile_project_knowledge_recipe=lambda **kwargs:payload
sys.argv=['entry','--macro-root','/never-compiled','--expected-macro-sha','a'*40,'--mode','prepare']
try:raise SystemExit(entry.main())
except SystemExit:raise
except BaseException:entry._refuse()
'''
    frame={'schema':'mastermind.project_knowledge_recipe_capture_request.v1','request':{},'trusted':{
        'actor_ref':'workspace:'+'a'*64,'permission_binding_digest':'b'*64,'decision_date':'2026-11-05'}}
    result=bounded_subprocess_runner([sys.executable,'-I','-c',harness,str(ROOT),str(excess)],
        cwd=ROOT,timeout=15,max_bytes=524288,input_bytes=json.dumps(frame).encode())
    assert not any(result.get(k) for k in ('timed_out','limit_exceeded','invalid_utf8'))
    if excess:
        assert result['code']==2 and result['stdout']==''
        assert result['stderr']=='project_knowledge_recipe_unavailable\n'
    else:
        assert result['code']==0 and result['stderr']==''
        wire=result['stdout'].encode('utf-8')
        assert len(wire)==524288 and wire.endswith(b'\n') and wire.count(b'\n')==1
        value=json.loads(wire)
        assert set(value)=={'schema','recipe','initial_snapshot','source_binding'}
        assert value['schema']=='mastermind.project_knowledge_recipe_capture.v1'
