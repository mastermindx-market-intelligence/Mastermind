"""Fixed transport serialization tests. No SSH/provider/secret/profile is read."""
import json
import os
import subprocess
import sys
import urllib.request
from unittest import mock
import pytest
from control_plane import executive_memory_issuer as root
from scripts import protected_memory_model_runner as runner
from common.protected_memory_model_input import compile_memory_model_input
from common.memory_native_wire import SUFFIX


def test_actual_bounded_ssh_pipe_mechanics_fixed_argv_no_identity_fallback(monkeypatch):
    captured=[];actual=subprocess.Popen;reply=b'\0\0\0\x02{}'
    for key,value in {'SSH_AUTH_SOCK':'/hostile/agent','HOME':'/hostile/home',
            'PATH':'/hostile/bin','LD_PRELOAD':'/hostile/library','DYLD_INSERT_LIBRARIES':'/hostile/library',
            'SSH_ASKPASS':'/hostile/askpass','DISPLAY':'hostile:0','LANG':'hostile',
            'BASH_ENV':'/hostile/environment'}.items():monkeypatch.setenv(key,value)
    def inert(argv,**kwargs):
        captured.append((argv,kwargs['env']))
        # Actual subprocess/pipe/select/EOF mechanics; wholly inert Python echo.
        return actual([sys.executable,'-I','-c','import sys; x=sys.stdin.buffer.read();sys.stdout.buffer.write(b"\\0\\0\\0\\2{}")'],
            stdin=kwargs['stdin'],stdout=kwargs['stdout'],stderr=kwargs['stderr'],close_fds=True,env=kwargs['env'])
    monkeypatch.setattr(root.subprocess,'Popen',inert)
    assert root._exchange(b'x'*16384)==reply
    argv,environment=captured[0]
    assert argv[0]=='/usr/bin/ssh' and argv[-1]==root.REMOTE_COMMAND
    assert argv[-2]=='root@146.190.142.17'
    assert '-F' in argv and '/dev/null' in argv and 'IdentityAgent=none' in argv
    assert 'StrictHostKeyChecking=yes' in argv and 'ClearAllForwardings=yes' in argv
    assert all(option in argv for option in ('SendEnv=-*','ControlMaster=no','ControlPath=none','ControlPersist=no'))
    assert str(root.KEY) in argv and 'macro_dashboard_deploy_v2' not in ' '.join(argv)
    assert environment=={'PATH':'/usr/bin:/bin','HOME':'/var/empty','LANG':'C'}


@pytest.mark.parametrize('field',['argv','env','command','key','path','ssh_options','transport_profile'])
def test_wire_selector_cannot_control_fixed_transport(field):
    from common import memory_native_wire as wire
    request={'schema':'research_factory.market_memory_e0_native_issuer_request.v3',
        'action':'qualify_current_case','operation_id':'original-op',
        'intent':{'study_id':'study','root_id':'root','operator_run_id':'operator',
            'child_run_id':'child','participant_binding_sha256':'a'*64},field:'hostile'}
    with pytest.raises(ValueError):wire.validate_request(request)


@pytest.mark.parametrize('damage',['tools','unfinished','oversize','multiple'])
def test_fixed_model_response_refuses_tool_partial_or_oversize(damage,monkeypatch):
    value={'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':'untrusted-result'}}]}
    if damage=='tools':value['choices'][0]['message']['tool_calls']=[{'function':'forbidden'}]
    elif damage=='unfinished':value['choices'][0]['finish_reason']='length'
    elif damage=='oversize':value['choices'][0]['message']['content']='x'*65537
    else:value['choices'].append(value['choices'][0])
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,n):return json.dumps(value).encode()[:n]
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(runner.urllib.request,'build_opener',lambda *a:Opener())
    with pytest.raises(ValueError):runner._post({'api_origin':'https://api.z.ai/api/paas/v4'},
        compile_memory_model_input(b'input'+SUFFIX,model='glm-5.3'),'INERT_TEST_CREDENTIAL')


def test_native_packet_is_single_exact_user_message_no_schema_or_retry(monkeypatch):
    calls=[];packet='问题\n'.encode()+SUFFIX
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,n):return b'{"choices":[{"finish_reason":"stop","message":{"role":"assistant","content":"untrusted"}}]}'
    class Opener:
        def open(self,request,**kwargs):calls.append((request,kwargs));return Response()
    monkeypatch.setattr(runner.urllib.request,'build_opener',lambda *a:Opener())
    assert runner._post({'api_origin':'https://api.z.ai/api/paas/v4'},
        compile_memory_model_input(packet,model='glm-5.3'),'INERT_TEST_CREDENTIAL')==b'untrusted'
    assert len(calls)==1
    request,_=calls[0];body=json.loads(request.data)
    assert set(body)=={'model','messages','stream','max_tokens'}
    assert body['messages']==[{'role':'user','content':packet.decode()}]
    assert request.full_url=='https://api.z.ai/api/paas/v4/chat/completions'
    assert 'RESULT_SCHEMA_JSON' not in body['messages'][0]['content']


def test_redirect_never_forwards_body_or_credentials():
    with pytest.raises(ValueError):runner.NoRedirect().redirect_request(None,None,None,None,None,None)
