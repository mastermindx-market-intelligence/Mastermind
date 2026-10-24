"""Final pytest failure metadata only; child failures stay failures."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import ci_pytest_timing as m

MODULE='tests/test_paid_initializer_nosite.py'
CASE='test_profile_is_explicit_nested_only_and_decode_has_no_policy_side_effect'
PRIVATE='NEVER_EMIT_PRIVATE_MESSAGE_OR_PARAMETER'


@pytest.mark.parametrize('phase',['collect','setup','call','teardown','both'])
def test_actual_pytest_final_failure_phases_emit_only_static_metadata(tmp_path,phase):
    tests=tmp_path/'tests';tests.mkdir();file=tests/'test_paid_initializer_nosite.py'
    if phase=='collect':source='raise RuntimeError('+repr(PRIVATE)+')\n'
    elif phase=='call':source='def '+CASE+'():\n raise OSError(13,'+repr(PRIVATE)+')\n'
    else:
        source='import pytest\n@pytest.fixture(autouse=True)\ndef synthetic_fixture():\n'
        source+=(' yield\n raise RuntimeError('+repr(PRIVATE)+')\n' if phase in ('teardown','both') else ' raise RuntimeError('+repr(PRIVATE)+')\n')
        source+='def '+CASE+'():'+('raise OSError(13,'+repr(PRIVATE)+')' if phase=='both' else 'pass')+'\n'
    file.write_text(source)
    env={**os.environ,'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(Path(__file__).resolve().parents[1])}
    child=subprocess.run([sys.executable,'-m','pytest','-q','--tb=short','-p','no:cacheprovider','-p','scripts.ci_pytest_timing',MODULE],cwd=tmp_path,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=20)
    assert child.returncode!=0
    lines=[line for line in child.stdout.splitlines() if line.startswith('::error ') and 'H1 preflight failure metadata' in line]
    if phase=='both':
        values=[json.loads(line.split('::',2)[2])for line in lines]
        assert [value['phase']for value in values]==['call','teardown']
        assert values[0]['errno']==13 and all(PRIVATE not in line for line in lines)
        return
    assert len(lines)==1
    value=json.loads(lines[0].split('::',2)[2])
    assert set(value)=={'module','case','function','phase','line','errno'}
    assert value['module']==MODULE and value['phase']==phase
    assert value['case']==(None if phase=='collect' else CASE)
    assert PRIVATE not in lines[0] and str(tmp_path) not in lines[0]
    if phase=='call':assert value['function']==CASE and value['line']==2 and value['errno']==13
    if phase=='collect':assert value['line']==1


def test_case_parameters_and_unowned_modules_never_become_diagnostic_values():
    value=m._h1_failure_metadata(MODULE+'::'+CASE+'['+PRIVATE+']','call')
    assert value['case']==CASE and PRIVATE not in json.dumps(value)
    assert m._h1_failure_metadata('tests/'+PRIVATE+'.py::'+CASE,'call') is None
    assert m._h1_failure_metadata(MODULE+'::'+PRIVATE,'call')['case'] is None
    assert m._h1_failure_metadata(MODULE+'::'+CASE,PRIVATE) is None


def test_call_and_cleanup_are_distinct_reports_without_rendering_exception_context():
    try:
        try:raise OSError(13,PRIVATE)
        finally:raise RuntimeError(PRIVATE)
    except RuntimeError as error:
        call=m._h1_failure_metadata(MODULE+'::'+CASE,'call',error=error.__context__)
        cleanup=m._h1_failure_metadata(MODULE+'::'+CASE,'teardown',error=error)
    assert call['phase']=='call' and call['errno']==13
    assert cleanup['phase']=='teardown' and cleanup['errno'] is None
    assert PRIVATE not in json.dumps([call,cleanup])


def test_diagnostic_internal_failure_cannot_replace_original_outcome(monkeypatch):
    from types import SimpleNamespace
    lines=[];plugin=m.ModuleTiming(SimpleNamespace(write_line=lines.append))
    def unavailable(*args,**kwargs):raise RuntimeError(PRIVATE)
    monkeypatch.setattr(m,'_h1_failure_metadata',unavailable)
    plugin._h1_failure(MODULE+'::'+CASE,'teardown',error=ValueError(PRIVATE))
    assert len(lines)==1 and PRIVATE not in lines[0]
    value=json.loads(lines[0].split('::',2)[2])
    assert value==dict(module=MODULE,case=None,function=None,phase='teardown',line=None,errno=None)


@pytest.mark.parametrize('field,value',[('module',PRIVATE),('case',PRIVATE),('function',PRIVATE),('phase',PRIVATE),('line',True),('errno',True),('extra',PRIVATE)])
def test_emission_boundary_cannot_render_private_or_unapproved_fields(monkeypatch,field,value):
    from types import SimpleNamespace
    data=dict(module=MODULE,case=CASE,function=None,phase='call',line=None,errno=None)
    data[field]=value;lines=[]
    monkeypatch.setattr(m,'_h1_failure_metadata',lambda *a,**kw:data)
    m.ModuleTiming(SimpleNamespace(write_line=lines.append))._h1_failure(MODULE+'::'+CASE,'call')
    assert lines==[]
