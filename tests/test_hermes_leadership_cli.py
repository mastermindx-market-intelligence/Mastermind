"""Runnable policy consumer, never a live credential or admission interface."""
import importlib
import json
import subprocess
import sys
from pathlib import Path
import pytest
from tests.test_hermes_leadership_budget import snapshot,request,NOW
ROOT=Path(__file__).resolve().parents[1]


def run(*args,data=''):
    return subprocess.run([sys.executable,'-m','integrations.hermes_leadership',*args],
        input=data,text=True,capture_output=True,cwd=ROOT,timeout=10)


def test_cli_module_exists():
    assert importlib.util.find_spec('integrations.hermes_leadership.__main__') is not None


def test_charter_command_is_detached_guidance():
    result=run('charter','secretary')
    assert result.returncode==0,result.stderr
    body=json.loads(result.stdout)
    assert body['key']=='secretary' and body['authority_grant'] is False


def test_budget_command_is_advisory():
    result=run('budget',data=json.dumps({'snapshot':snapshot(),'request':request(),'now':NOW.isoformat()}))
    assert result.returncode==0,result.stderr
    body=json.loads(result.stdout)
    assert body['decision']=='ELIGIBLE_FOR_CAPACITY_CHECK'
    assert body['admitted'] is False and body['reservation_created'] is False


@pytest.mark.parametrize('data',['{','{"now":1,"now":2}','{"x":NaN}','x'*65537,
    json.dumps({'snapshot':snapshot(),'request':request(),'now':NOW.isoformat(),'secret':'SENTINEL'})])
def test_invalid_input_is_bounded_and_value_free(data):
    result=run('budget',data=data)
    assert result.returncode==2 and result.stdout==''
    assert result.stderr=='invalid_input\n'


@pytest.mark.parametrize('args',[('unknown-secret',),('charter','unknown-secret'),
    ('budget','unknown-secret'),('charter',),('charter','secretary','unknown-secret')])
def test_bad_arguments_never_echo_values(args):
    result=run(*args)
    assert result.returncode==2 and result.stdout==''
    assert 'unknown-secret' not in result.stderr
