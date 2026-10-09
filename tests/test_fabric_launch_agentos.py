import json
import subprocess
import types
import pytest
from ops.fabric_launch import agentos as a
from ops.fabric_launch.context import LaunchInputError


def bundle():
    return {'schema':'context_bundle.v1','target':{'workstream':'WS-FIXTURE'.replace('WS-', 'WS:')},
            'no_answer_reason':None,'sections':[{'id':'higher_law','items':['must preserve']}],
            'degraded':['mandatory context exceeds requested budget'],'excluded':[],
            'omitted_due_to_budget':['optional-old-note'],'token_budget':800,'token_estimate':1500,
            'repo_sha':'fixture-source','generated_at':'2026-10-06T00:00:00Z'}


def test_exact_owner_bytes_and_degraded_accounting_are_preserved(tmp_path):
    script=tmp_path/'scripts/agentos.py';script.parent.mkdir();script.write_text('# owner fixture')
    raw=(json.dumps(bundle(),indent=2)+'\n').encode();calls=[]
    def run(argv,**kwargs):
        calls.append((argv,kwargs));kwargs['stdout'].write(raw);return types.SimpleNamespace(returncode=0)
    before=set(tmp_path.rglob('*'))
    actual,receipt=a.read_context('FIXTURE',800,owner_root=tmp_path,run=run)
    assert actual==raw
    assert receipt['owner']=='agent_os' and receipt['execution_authority'] is False
    assert receipt['degraded_count']==1 and receipt['omitted_count']==1
    assert len(calls)==1
    assert calls[0][0][2:]==['compile-context','--workstream','FIXTURE','--json','--budget','800']
    assert calls[0][1]['timeout']==25 and 'shell' not in calls[0][1]
    assert set(tmp_path.rglob('*'))==before


@pytest.mark.parametrize('field',['degraded','excluded','omitted_due_to_budget','sections'])
def test_missing_accounting_fails_instead_of_silent_omission(field):
    v=bundle();v.pop(field)
    with pytest.raises(LaunchInputError,match='ACCOUNTING_MISSING'):
        a.validate_bundle(json.dumps(v).encode(),'FIXTURE')


def test_no_answer_does_not_invent_project_context():
    v=bundle();v['target']['workstream']=None;v['no_answer_reason']='index missing'
    with pytest.raises(LaunchInputError,match='UNRESOLVED'):
        a.validate_bundle(json.dumps(v).encode(),'FIXTURE')


@pytest.mark.parametrize('key',['--root','foo;cat .env','WS:OTHER SPACE','','fixture'])
def test_invalid_workstream_never_invokes_owner(tmp_path,key):
    with pytest.raises(LaunchInputError,match='WORKSTREAM_INVALID'):
        a.read_context(key,owner_root=tmp_path,run=lambda *a,**k:pytest.fail('not invoked'))


@pytest.mark.parametrize('budget',[True,0,799,12001,'4000'])
def test_bad_budget_never_invokes_owner(tmp_path,budget):
    with pytest.raises(LaunchInputError,match='BUDGET_INVALID'):
        a.read_context('FIXTURE',budget,owner_root=tmp_path,run=lambda *a,**k:pytest.fail('not invoked'))


def test_timeout_has_no_retry_or_mutation(tmp_path):
    p=tmp_path/'scripts/agentos.py';p.parent.mkdir();p.write_text('# owner')
    calls=[]
    def run(argv,**kwargs):calls.append(argv);raise subprocess.TimeoutExpired(argv,25)
    with pytest.raises(LaunchInputError,match='READ_TIMEOUT'):
        a.read_context('FIXTURE',owner_root=tmp_path,run=run)
    assert len(calls)==1


def test_source_change_refuses_result(tmp_path):
    p=tmp_path/'scripts/agentos.py';p.parent.mkdir();p.write_text('# old')
    def run(argv,**kwargs):
        p.write_text('# changed');kwargs['stdout'].write(json.dumps(bundle()).encode());return types.SimpleNamespace(returncode=0)
    with pytest.raises(LaunchInputError,match='SOURCE_CHANGED'):
        a.read_context('FIXTURE',owner_root=tmp_path,run=run)
