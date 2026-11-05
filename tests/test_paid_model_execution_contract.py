import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from control_plane import paid_model_execution_contract as contract

_PATH = Path(__file__).parents[1] / 'ops/native_fabric/quota_continuity/candidate/paid_glm_model_client.py'
_SPEC = importlib.util.spec_from_file_location('paid_glm_model_client', _PATH)
client = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(client)


def payload():
    return dict(binding=dict(root_id='JOB-root', job_id='JOB-child', attempt_id='ATT-1',
                            effective_grant_digest='a'*64, commission_sha256='b'*64),
                physical_binding_sha256='c'*64,
                launch_spec=dict(model='glm-5.3', timeout_seconds=60,
                                 job_id='JOB-child', run_id='ATT-1',
                                 effective_grant_digest='a'*64, prompt='Exact supplied evidence 中文',
                                 authorities=['READ', 'RESEARCH'], authority=None,
                                 allowed_artifact_paths=[]),
                paid_route=dict(provider='glm', host_ref='ubuntu3', model='glm-5.3',
                                parent_job_id='JOB-root'),
                paid_input=dict(prompt='Exact supplied evidence 中文',
                                result_schema={'type':'object', 'additionalProperties':False}),
                validation_commands=[])


def test_compiler_seals_actual_content_without_any_path_fetch():
    p = payload()
    raw = contract.compile_request(p)
    body = client.validate_body(raw, 'glm-5.3')
    assert set(body) == {'model', 'input', 'stream', 'max_output_tokens'}
    assert body['input'].startswith(p['paid_input']['prompt'])
    assert 'RESULT_SCHEMA_JSON:' in body['input']
    descriptor = contract.descriptor(p)
    assert descriptor['request_body_sha256'] == hashlib.sha256(raw).hexdigest()
    for key, expected in [('parent_job_id','JOB-other'), ('host_ref','ubuntu0')]:
        changed = copy.deepcopy(p)
        changed['paid_route'][key] = expected
        assert contract.descriptor(changed) != descriptor


@pytest.mark.parametrize('authorities', [[], ['RESEARCH'], ['READ', 'READ'],
    ['READ','WRITE_BRANCH'], ['READ','RUN_TESTS'], ['READ','SERVICE'], ['READ',True]])
def test_compiler_does_not_widen_grants(authorities):
    p = payload(); p['launch_spec']['authorities'] = authorities
    with pytest.raises(contract.PaidModelContractRefused, match='^paid_model_contract_refused$'):
        contract.compile_request(p)


@pytest.mark.parametrize('key,value', [('authority','READ'), ('model','other'),
    ('allowed_artifact_paths',['x']), ('timeout_seconds',True), ('timeout_seconds',float('inf')),
    ('run_id','other'), ('effective_grant_digest','d'*64)])
def test_compiler_rejects_changed_launch_binding(key, value):
    p = payload(); p['launch_spec'][key] = value
    with pytest.raises(contract.PaidModelContractRefused): contract.compile_request(p)


@pytest.mark.parametrize('change', [
    lambda p: p.update({'tools': []}),
    lambda p: p.update({'physical_binding_sha256':'bad'}),
    lambda p: p.update({'validation_commands':[['echo','test']]}),
    lambda p: p['paid_input'].update({'prompt':'different'}),
    lambda p: p['paid_input'].update({'result_schema':False}),
    lambda p: p['paid_input'].update({'path':'/secret'}),
    lambda p: p['paid_route'].update({'provider':'minimax'}),
    lambda p: p['paid_route'].update({'parent_job_id':'bad\ninput'}),
])
def test_compiler_closed_inputs(change):
    p = payload(); change(p)
    with pytest.raises(contract.PaidModelContractRefused): contract.compile_request(p)


@pytest.mark.parametrize('extra', ['tools','tool_choice','functions','mcp_servers',
                                   'previous_response_id','instructions'])
def test_client_refuses_extended_model_request(extra):
    body = json.loads(contract.compile_request(payload())); body[extra] = []
    with pytest.raises(client.ModelOnlyRefused): client.validate_body(client.canonical(body),'glm-5.3')


def response(text='{"result":"exact 中文"}'):
    return dict(status='completed',error=None,incomplete_details=None,output=[dict(
        type='message',role='assistant',status='completed',content=[dict(type='output_text',text=text)])])


def test_response_preserves_exact_result_bytes():
    text = '{"result": "exact 中文", "number": 1}'
    assert client.result_bytes(client.canonical(response(text))) == text.encode()


@pytest.mark.parametrize('change', [
    lambda p: p.update(status='incomplete'),
    lambda p: p.update(error={'message':'credential-shaped-fake'}),
    lambda p: p.update(output=[{'type':'function_call','name':'shell'}]),
    lambda p: p['output'][0].update(status='in_progress'),
    lambda p: p['output'][0]['content'][0].update(text='partial JSON {'),
])
def test_no_partial_or_tool_output(change):
    r = response(); change(r)
    with pytest.raises(client.ModelOnlyRefused): client.result_bytes(client.canonical(r))


def test_one_post_fixed_destination_no_proxy_or_redirect(monkeypatch):
    seen = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self,*_): pass
        def read(self,limit): return client.canonical(response())
    class Opener:
        def open(self,request,timeout):
            seen.append((request,timeout)); return Response()
    handlers = []
    def build(*args): handlers.extend(args); return Opener()
    monkeypatch.setattr(client,'build_opener',build)
    raw = contract.compile_request(payload())
    cap = client.canonical(dict(token='v2.synthetic-fixture',expires_at=time.time()+60,model='glm-5.3',run_id='ATT-1',host='ubuntu3'))
    assert client.execute(raw,cap,'glm-5.3') == b'{"result":"exact \xe4\xb8\xad\xe6\x96\x87"}'
    assert len(seen) == 1
    assert seen[0][0].full_url == client.URL
    assert seen[0][0].method == 'POST' and seen[0][0].data == raw
    assert handlers[0].proxies == {}
    assert isinstance(handlers[1],client._NoRedirect)


def test_transport_error_is_not_retried(monkeypatch):
    count = []
    def fail(*args,**kwargs): count.append(1); raise OSError('private secret')
    monkeypatch.setattr(client,'build_opener',lambda *_:SimpleNamespace(open=fail))
    with pytest.raises(OSError):
        client.execute(contract.compile_request(payload()),client.canonical(dict(
            token='v2.synthetic-fixture',expires_at=time.time()+60,model='glm-5.3',run_id='ATT-1',host='ubuntu3')),'glm-5.3')
    assert len(count) == 1


def test_cli_redacts_error_and_outputs_no_partial_result(capsys):
    assert client.main(['/private/credential-shaped-fake','bad','glm-5.3']) == 78
    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err == 'CANONICAL_PAID_MODEL_ONLY_UNAVAILABLE\n'
