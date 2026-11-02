"""Only terminal identities/branches qualify intermediate observations."""
from contextlib import nullcontext
import ast
import shlex
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ops.native_fabric.quota_continuity.candidate import paid_provider_entry as entry
from tests import h1_terminal_diagnostic as m

SECRET='DO_NOT_RENDER_PRIVATE_CANARY_MESSAGE_PATH_ARGV'
REMOTE='''import os
SCENARIO=''
def _execute():
    if SCENARIO=='fd-custody' and os.get_inheritable(HOOK.__globals__['_saved']):
        raise ValueError('SAVED_FD_MUST_NOT_BE_INHERITED')
    if SCENARIO in ('handled-success','handled-return','handled-then-terminal','same-type'):
        try:raise FileNotFoundError('FIRST_PRIVATE_CONTROL_FLOW')
        except FileNotFoundError:pass
    if SCENARIO=='handled-then-terminal':raise ValueError('TERMINAL_PRIVATE_MESSAGE')
    if SCENARIO=='same-type':raise FileNotFoundError('SECOND_PRIVATE_TERMINAL')
    if SCENARIO=='cleanup':
        try:raise ValueError('PRIMARY_PRIVATE_MESSAGE')
        finally:raise RuntimeError('ACTUAL_TERMINAL_CLEANUP')
    if SCENARIO=='escaping':raise KeyboardInterrupt('PRIVATE_INTERRUPT')
    if SCENARIO=='redirect':
        fd=os.open(os.devnull,os.O_WRONLY)
        os.dup2(fd,1);os.close(fd)
    if SCENARIO in ('handled-return','ignored-return','redirect'):return 78
    return 0
'''
SOURCE='''import os,types
def _bootstrap_main(args):
    try:
        here,scenario=args[1:3]
        remote=types.ModuleType('remote_sub_exec')
        remote.__file__=os.path.join(here,'remote_sub_exec.py')
        exec(compile(REMOTE,remote.__file__,'exec'),remote.__dict__)
        remote.SCENARIO=scenario
        remote.HOOK=_h1_terminal
        result=remote._execute()
        return 0 if scenario=='ignored-return' else result
    except Exception:
        # No exception/raw command, environment, capability or provider prose.
        return 78
'''.replace('REMOTE',repr(REMOTE),1)


def line(marker):
    pos=REMOTE.index(marker)
    return REMOTE.count('\n',0,pos)+1


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':')).encode()+b'\n'


def run(tmp_path,scenario):
    program=entry._bootstrap_source(SOURCE.encode())
    wrapper=m.build_variant(program,str(tmp_path))
    result=subprocess.run([sys.executable,'-I','-S','-B','-c',wrapper,
        'executor',str(tmp_path),scenario],capture_output=True,timeout=20,
        env={'PATH':'/usr/bin:/bin'})
    expected=130 if scenario=='escaping' else 78 if scenario in ('handled-then-terminal','same-type','cleanup','handled-return','redirect') else 0
    if result.returncode!=expected or result.stderr:raise AssertionError('terminal test child refused')
    assert str(tmp_path).encode()not in result.stdout
    assert b'PRIVATE'not in result.stdout and b'CANARY'not in result.stdout
    assert result.stdout.count(b'\n')==1 and len(result.stdout)<=4097
    return m.read_record(result.stdout)


@pytest.mark.parametrize('scenario,kind,marker',[
    ('handled-then-terminal','ValueError',"if SCENARIO=='handled-then-terminal'"),
    ('same-type','FileNotFoundError',"if SCENARIO=='same-type'"),
    ('cleanup','RuntimeError',"finally:raise RuntimeError"),
])
def test_exact_caught_terminal_exception_not_first_control_flow(tmp_path,scenario,kind,marker):
    value=run(tmp_path,scenario)
    assert value==dict(scope=m.SCOPE,event='HANDLED_TERMINAL_EXCEPTION',
        module='remote_sub_exec',function='_execute',line=line(marker),type=kind)


def test_escaping_terminal_exception_is_exact_and_nontextual(tmp_path):
    value=run(tmp_path,'escaping')
    assert value['event']=='ESCAPING_TERMINAL_EXCEPTION'
    assert value['type']=='KeyboardInterrupt' and value['line']==line("if SCENARIO=='escaping'")


@pytest.mark.parametrize('scenario',['handled-return','redirect'])
def test_nonzero_return_reports_real_terminal_branch_and_saved_fd(tmp_path,scenario):
    value=run(tmp_path,scenario)
    assert value==dict(scope=m.SCOPE,event='TERMINAL_RETURN_NONZERO',
        module='remote_sub_exec',function='_execute',
        line=line("if SCENARIO in ('handled-return','ignored-return','redirect')"),
        type='NONZERO_RETURN')


@pytest.mark.parametrize('scenario',['handled-success','ignored-return','success','fd-custody'])
def test_handled_exception_or_nonterminal_return_is_not_called_failure(tmp_path,scenario):
    value=run(tmp_path,scenario)
    assert value==dict(scope=m.SCOPE,event='DIAGNOSTIC_COMPLETED',module='',function='',line=0,
        type='NO_TERMINAL_REFUSAL')


def test_only_handler_reporting_changes_and_line_numbers_preserved(tmp_path):
    original=entry._bootstrap_source(SOURCE.encode())
    wrapper=m.build_variant(original,str(tmp_path))
    assert m._ANCHOR.count('\n')==m._REPLACEMENT.count('\n')
    expected=SOURCE.replace(m._ANCHOR,m._REPLACEMENT,1)
    assert repr(expected)in wrapper or repr(repr(expected))[1:-1]in wrapper
    assert SOURCE.count(m._ANCHOR)==1
    with pytest.raises(ValueError,match='^terminal_variant_shape_refused$'):
        m.build_variant(entry._bootstrap_source(b'def _bootstrap_main(args):return 0\n'),str(tmp_path))


@pytest.mark.parametrize('change',[
    {'scope':'READY'}, {'event':'READY'}, {'type':SECRET}, {'module':SECRET},
    {'function':SECRET}, {'line':True}, {'line':-1}, {'line':65536}, {'private':SECRET},
    {'event':'TERMINAL_RETURN_NONZERO'}, {'type':'NONZERO_RETURN'},
])
def test_parser_refuses_private_extra_type_bounds_and_inconsistent_records(change):
    value=dict(scope=m.SCOPE,event='DIAGNOSTIC_COMPLETED',module='',function='',line=0,
        type='NO_TERMINAL_REFUSAL');value.update(change)
    with pytest.raises(ValueError,match='^terminal_record_refused$'):
        m.read_record(canonical(value))


@pytest.mark.parametrize('raw',[b'',b'{}',b'{}\n\n',b'x'*4098,b'\x1b[31m\n',b'\xff\n',
    b'{"scope":"INTERMEDIATE_ONLY","scope":"INTERMEDIATE_ONLY"}\n',
    b'PRIVATE\n{}\n',b'{"scope":"\\u0049NTERMEDIATE_ONLY"}\n'])
def test_parser_refuses_malformed_control_duplicate_and_escaped_input(raw):
    with pytest.raises(ValueError,match='^terminal_record_refused$'):m.read_record(raw)


def request(lines,*,broken=False):
    def write(value):
        if broken:raise ValueError(SECRET)
        lines.append(value)
    return SimpleNamespace(config=SimpleNamespace(pluginmanager=SimpleNamespace(
        getplugin=lambda name:SimpleNamespace(write_line=write))),
        getfixturevalue=lambda name:SimpleNamespace(disabled=nullcontext))


@pytest.mark.parametrize('raw',[
    canonical(dict(scope=m.SCOPE,event='DIAGNOSTIC_COMPLETED',module='',function='',line=0,type='NO_TERMINAL_REFUSAL')),
    canonical(dict(scope=m.SCOPE,event='TERMINAL_RETURN_NONZERO',module='remote_sub_exec',function='_execute',line=815,type='NONZERO_RETURN')),
    SECRET.encode()+b'\n',
])
def test_parent_unconditionally_refuses_qualification_without_raw_rendering(raw):
    from tests import test_paid_provider_entry_linux as fixture
    lines=[]
    with pytest.raises(AssertionError,match='^INTERMEDIATE diagnostic cannot qualify original provider proof$') as caught:
        fixture._fixture_intermediate_failure(request(lines),raw)
    assert caught.value.__suppress_context__
    assert len(lines)==1 and SECRET not in lines[0]
    assert json.loads(lines[0].split('::',2)[2])['scope']==m.SCOPE


def test_reporter_failure_still_cannot_qualify_or_render_its_exception():
    from tests import test_paid_provider_entry_linux as fixture
    with pytest.raises(AssertionError) as caught:
        fixture._fixture_intermediate_failure(request([],broken=True),b'invalid\n')
    assert str(caught.value)=='INTERMEDIATE diagnostic cannot qualify original provider proof'
    assert caught.value.__suppress_context__


def test_actual_producer_handler_anchor_changes_only_reporting_ast(tmp_path):
    source=Path(entry.__file__).read_text()
    assert source.count(m._ANCHOR)==1
    changed=source.replace(m._ANCHOR,m._REPLACEMENT,1)
    before=ast.parse(source);after=ast.parse(changed)
    handlers=[node for node in ast.walk(after)if isinstance(node,ast.ExceptHandler)
        and node.name=='_h1_terminal_error']
    assert len(handlers)==1
    handler=handlers[0];call=handler.body.pop(0)
    assert isinstance(call,ast.Expr)and isinstance(call.value,ast.Call)
    assert isinstance(call.value.func,ast.Name)and call.value.func.id=='_h1_terminal'
    assert len(call.value.args)==1 and call.value.args[0].id=='_h1_terminal_error'
    handler.name=None
    assert ast.dump(before)==ast.dump(after)
    assert source.count('\n')==changed.count('\n')
    program=entry._bootstrap_source(source.encode())
    wrapper=m.build_variant(program,str(tmp_path))
    assert len(wrapper.encode())<=100000


def test_variant_preserves_original_argv_except_diagnostic_body(tmp_path):
    from tests import test_paid_provider_entry_linux as fixture
    here=tmp_path/'lanes/support-releases'/('a'*64)/'ext';key='fixture-run'
    lanes=here.parent.parent.parent
    source=Path(entry.__file__).read_bytes();program=entry._bootstrap_source(source)
    argv=['/usr/bin/env','FABRIC_CANONICAL_PAID_MODE=sealed-model-only-v1',
        'GLM_REMOTE_CAPABILITY_FILE='+str(lanes/'tmp'/(key+'.glm-cap.json')),
        '/usr/bin/python3.12','-I','-S','-B','-c',program,'executor',str(here),
        'public-support-hashes',key,'glm-5.3-flash','b'*64,'c'*64]
    original=shlex.join(argv);variant=fixture._fixture_intermediate_command(original,here)
    actual=shlex.split(variant)
    assert actual[:8]==argv[:8] and actual[9:]==argv[9:]
    assert actual[8]!=program and len(variant.encode())+1<=100000
    assert shlex.split(original)==argv


def test_private_wrong_argv_shape_has_fixed_exception_and_no_launch(tmp_path):
    from tests import test_paid_provider_entry_linux as fixture
    with pytest.raises(AssertionError) as caught:
        fixture._fixture_intermediate_command(SECRET,tmp_path)
    assert str(caught.value)=='INTERMEDIATE diagnostic shape refused'
    assert caught.value.__suppress_context__
