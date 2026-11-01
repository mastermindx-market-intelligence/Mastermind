"""The separate diagnostic must stay before the original executor and be private."""
from contextlib import nullcontext
import json
from pathlib import Path
import shlex
import sys
from types import ModuleType,SimpleNamespace

import pytest

from tests import test_paid_provider_entry_linux as fixture

PRIVATE='PRIVATE_TOKEN_PATH_EXCEPTION_ARGV'


def material(tmp_path,monkeypatch,*,result=None,error=None):
    lines=[];seen=[];original='original-public-bootstrap-program'
    here=tmp_path/'sealed/ext';lanes=tmp_path/'lanes';key='fixture-run'
    argv=['/usr/bin/env','FABRIC_CANONICAL_PAID_MODE=sealed-model-only-v1',
        'GLM_REMOTE_CAPABILITY_FILE='+str(lanes/'tmp'/(key+'.glm-cap.json')),
        '/usr/bin/python3.12','-I','-S','-B','-c',original,
        'executor',str(here),'public-support-hashes',key,'glm-5.3-flash','a'*64,'b'*64]
    command=shlex.join(argv);env={'REMOTE_SUB_LANES':str(lanes)}
    module=ModuleType('tests.h1_bootstrap_diagnostic')
    module.build_probe=lambda program,path:'diagnostic:'+program
    module.read_record=lambda raw:result
    monkeypatch.setitem(sys.modules,module.__name__,module)
    def child(actual,**kwargs):
        seen.append((actual,kwargs))
        if error is not None:raise error
        return b'fixed-result'
    monkeypatch.setattr(fixture.initializer,'_bounded_child',child)
    request=SimpleNamespace(config=SimpleNamespace(pluginmanager=SimpleNamespace(
        getplugin=lambda name:SimpleNamespace(write_line=lines.append))),
        getfixturevalue=lambda name:SimpleNamespace(disabled=nullcontext))
    return command,env,here,request,argv,seen,lines


def test_diagnostic_uses_same_interpreter_flags_args_and_original_remains_unchanged(tmp_path,monkeypatch):
    result=dict(outcome='READY',phase='READY',module='paid_provider_entry',function='_run_executor',line=1,exception='')
    command,env,here,request,argv,seen,lines=material(tmp_path,monkeypatch,result=result)
    fixture._fixture_premodel_diagnostic(command,env,here,request)
    assert shlex.split(command)==argv
    diagnostic,kwargs=seen[0]
    assert diagnostic[:8]==argv[:8] and diagnostic[9:]==argv[9:]
    assert diagnostic[8]=='diagnostic:'+argv[8]
    assert kwargs==dict(env=env,timeout=20)
    assert len(lines)==1 and json.loads(lines[0].split('::',2)[2])==result


@pytest.mark.parametrize('failure', ['child','record','refusal'])
def test_private_acquisition_or_report_failures_are_fixed_and_do_not_qualify(tmp_path,monkeypatch,failure):
    result=dict(outcome='REFUSED',phase='REQUEST',module='',function='',line=0,exception='UNKNOWN') if failure=='refusal' else None
    error=ValueError(PRIVATE)if failure=='child'else None
    command,env,here,request,argv,seen,lines=material(tmp_path,monkeypatch,result=result,error=error)
    with pytest.raises(AssertionError,match='^fixture premodel diagnostic refused$'):
        fixture._fixture_premodel_diagnostic(command,env,here,request)
    assert len(lines)==1 and PRIVATE not in lines[0]
    assert 'original-public-bootstrap-program'not in lines[0] and str(tmp_path)not in lines[0]
    value=json.loads(lines[0].split('::',2)[2])
    assert value['outcome'] in ('CHILD_REFUSED','REFUSED')


def test_private_command_shape_is_never_rendered_or_launched(tmp_path,monkeypatch):
    command,env,here,request,argv,seen,lines=material(tmp_path,monkeypatch)
    with pytest.raises(AssertionError) as caught:
        fixture._fixture_premodel_diagnostic(PRIVATE,env,here,request)
    assert str(caught.value)=='fixture premodel diagnostic shape refused'
    assert caught.value.__suppress_context__ and seen==[] and lines==[]
