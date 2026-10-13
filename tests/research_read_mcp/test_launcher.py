"""Portable candidate launcher proof; no listener, store or provider is started."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import asyncio
import time

import pytest

from tests.research_read_mcp.test_port_adapter import Service
from tests.research_read_mcp.test_app import Harness
from tests.research_read_mcp.test_runtime import parsed,write_grant
from integrations.research_read_mcp.port_adapter import CanonicalReadContext

PATH=Path(__file__).resolve().parents[2]/'scripts/mastermind_research_read_server.py'

def launcher():
    spec=importlib.util.spec_from_file_location('research_launcher_under_test',PATH)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_launcher_import_inert_and_describe_never_claims_live():
    script='''import runpy,os,subprocess,socket,sys
def no(*a,**k):raise AssertionError('import effect')
os.open=no;subprocess.run=no;socket.socket=no
m=runpy.run_path(sys.argv[1],run_name='inert_source_test')
assert m['describe']()['state']=='BUILT_NOT_PROVEN'
'''
    subprocess.run([sys.executable,'-I','-B','-c',script,str(PATH)],capture_output=True,check=True,timeout=20)
    result=subprocess.run([sys.executable,'-I','-B',str(PATH),'--describe'],capture_output=True,text=True,check=True,timeout=20)
    assert json.loads(result.stdout)['source_config_runtime_client_acceptance'] is False


def test_launcher_identity_refuses_before_policy_or_provider(tmp_path,monkeypatch):
    from integrations.research_read_mcp import runtime,release_identity
    m=launcher()
    monkeypatch.setattr(runtime,'load_deployment',lambda *a,**k:parsed())
    monkeypatch.setattr(release_identity,'load_archive_verifier',lambda *a,**k:lambda *a:None)
    with pytest.raises(runtime.RuntimeRefused,match='LAUNCHER_IDENTITY_REFUSED'):
        m.qualify('/synthetic/deployment.json','/synthetic/archive.json')


def test_composes_existing_auth_current_grant_and_actual_health_routes(tmp_path,monkeypatch):
    asyncio.run(composition(tmp_path,monkeypatch))


@pytest.mark.parametrize('unsafe', [None, 'writable', 'symlink'])
def test_serving_entry_opens_secure_durable_audit_before_runtime(tmp_path, monkeypatch, unsafe):
    from integrations.business_mcp_auth.contracts import AUTH_AUDIT_SCHEMA, AuthAuditEvent
    import uvicorn
    m = launcher()
    target = tmp_path.resolve() / 'audit'
    target.mkdir(mode=0o700)
    selected = target
    if unsafe == 'writable':
        target.chmod(0o777)
    elif unsafe == 'symlink':
        selected = tmp_path.resolve() / 'audit-link'
        selected.symlink_to(target, target_is_directory=True)
    policy = Harness().policy
    deployment = parsed(policy_id=policy.policy_id)
    monkeypatch.setattr(m, 'qualify', lambda *args: (deployment, None, policy))
    composed = []
    served = []
    def create(*args, audit_sink):
        # Exercise real append/fsync and secure acquisition. No store is opened.
        audit_sink.emit(AuthAuditEvent(AUTH_AUDIT_SCHEMA, policy.policy_id, 'accepted', True))
        composed.append(audit_sink)
        return object()
    monkeypatch.setattr(m, 'create_runtime', create)
    monkeypatch.setattr(uvicorn, 'run', lambda *args, **kwargs: served.append(kwargs))
    result = m.main(['--config', '/synthetic/deployment.json', '--audit-directory', str(selected)])
    if unsafe:
        assert result == 1 and not composed and not served
        assert not (target / 'auth-audit.jsonl').exists()
    else:
        assert result == 0 and len(composed) == len(served) == 1
        record = target / 'auth-audit.jsonl'
        assert record.stat().st_uid == os.geteuid()
        assert record.stat().st_mode & 0o777 == 0o600
        assert json.loads(record.read_text())['accepted'] is True
        assert served[0]['host'] == '127.0.0.1'
        assert served[0]['access_log'] is False and served[0]['proxy_headers'] is False

async def composition(tmp_path,monkeypatch):
    from integrations.research_read_mcp import port_adapter
    h=Harness();s=Service();m=launcher();h.clock=int(time.time())
    path=tmp_path.resolve()/'grant.json'
    write_grant(path,h.policy.policy_id,h.full.subject_digest,expires=h.clock+100)
    deployment=parsed(grant_path=str(path),policy_id=h.policy.policy_id)
    monkeypatch.setattr(port_adapter,'compose_macro_service',lambda *a,**k:(s,CanonicalReadContext,{'state':'SYNTHETIC_FACTORY_ONLY'}))
    class Verifier:
        receipts=({'state':'SYNTHETIC_BYTES_ONLY'},)
        def __call__(self,*args):return None
    h.app=m.create_runtime(deployment,Verifier(),h.policy,audit_sink=h.audit)
    await h.start()
    try:
        health=await h.client.get('/healthz')
        assert health.status_code==200 and health.json()=={'ok':True}
        ready=await h.client.get('/readyz')
        assert ready.status_code==503 and ready.json()=={'ready':False}
        assert ready.headers['cache-control']=='no-store'
        write_grant(path,h.policy.policy_id,h.full.subject_digest,expires=h.clock-1)
        ready=await h.client.get('/readyz')
        assert ready.status_code==503 and ready.json()=={'ready':False}
        denied=await h.call('research_status',{})
        assert denied.status_code==401
    finally:
        await h.stop()
