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
    from integrations.research_read_mcp import citation_transport
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
    monkeypatch.setattr(m, 'qualify', lambda *args: (deployment, SelectedOwnerVerifier(None), policy))
    composed = []
    served = []
    def create(*args, audit_sink):
        # Exercise real append/fsync and secure acquisition. No store is opened.
        audit_sink.emit(AuthAuditEvent(AUTH_AUDIT_SCHEMA, policy.policy_id, 'accepted', True))
        composed.append(audit_sink)
        return object()
    monkeypatch.setattr(m, 'create_runtime', create)
    monkeypatch.setattr(citation_transport, 'run_mcp_server', lambda **kwargs: served.append(kwargs))
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
        assert served[0]['port'] == deployment.bind_port

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


def selected_read_options():
    from integrations.research_read_mcp.selected_factory import SelectedReadOptions
    return SelectedReadOptions(expected_producer_commit='b'*40,writer_policy=lambda:True)


class SelectedOwnerVerifier:
    '''Synthetic bound verifier carrying admitted v2 options; bytes are not its claim.'''
    receipts=()
    def __init__(self,options):
        self.selected_options=options
    def __call__(self,*args):
        return None


def serve_with(tmp_path,monkeypatch,m,deployment,policy,verifier,create):
    from integrations.research_read_mcp import citation_transport
    served=[]
    monkeypatch.setattr(m,'qualify',lambda *args:(deployment,verifier,policy))
    if create is not None:
        monkeypatch.setattr(m,'create_runtime',create)
    monkeypatch.setattr(citation_transport,'run_mcp_server',lambda **kwargs:served.append(kwargs))
    target=tmp_path.resolve()/'audit';target.mkdir(mode=0o700)
    return (m.main(['--config','/synthetic/deployment.json','--audit-directory',str(target)]),served)


def test_serving_main_passes_admitted_selected_options(tmp_path,monkeypatch):
    m=launcher();policy=Harness().policy;deployment=parsed(policy_id=policy.policy_id)
    options=selected_read_options();captured={}
    def create(*args,audit_sink,**kwargs):
        captured['selected_options']=kwargs.get('selected_options');return object()
    result,served=serve_with(tmp_path,monkeypatch,m,deployment,policy,
                             SelectedOwnerVerifier(options),create)
    # The admitted owner declaration is the only way options reach the factory.
    assert result==0 and len(served)==1
    assert captured['selected_options'] is options


def test_serving_main_v1_owner_keeps_exact_legacy_factory_call(tmp_path,monkeypatch):
    m=launcher();policy=Harness().policy;deployment=parsed(policy_id=policy.policy_id)
    captured={}
    def create(*args,audit_sink,**kwargs):
        captured['args']=args;captured['kwargs']=kwargs;return object()
    from integrations.research_read_mcp import release_identity
    from tests.research_read_mcp.test_release_identity import owner_config
    verifier=release_identity.load_archive_verifier(str(owner_config(tmp_path)), deployment, owner_uid=os.geteuid())
    result,served=serve_with(tmp_path,monkeypatch,m,deployment,policy,verifier,create)
    # A real v1 bound owner supplies no selected options.
    assert result==0 and len(served)==1
    assert 'selected_options' not in captured['kwargs']


def test_selected_preparation_failure_refuses_without_fallback(tmp_path,monkeypatch):
    from integrations.research_read_mcp import citation_transport,port_adapter
    from integrations.research_read_mcp.contracts import ContractViolation
    m=launcher();policy=Harness().policy;deployment=parsed(policy_id=policy.policy_id)
    attempts=[];legacy=[];served=[]
    def refused(*args,**kwargs):
        attempts.append(kwargs);raise ContractViolation('SOURCE_UNAVAILABLE')
    monkeypatch.setattr(port_adapter,'compose_selected_macro_service',refused)
    monkeypatch.setattr(port_adapter,'compose_macro_service',lambda *a,**k:legacy.append(k))
    monkeypatch.setattr(m,'qualify',lambda *args:(deployment,SelectedOwnerVerifier(selected_read_options()),policy))
    monkeypatch.setattr(citation_transport,'run_mcp_server',lambda **kwargs:served.append(kwargs))
    target=tmp_path.resolve()/'audit';target.mkdir(mode=0o700)
    # The real create_runtime runs: the selected path refuses and never degrades.
    result=m.main(['--config','/synthetic/deployment.json','--audit-directory',str(target)])
    assert result==1 and len(attempts)==1 and not legacy and not served


@pytest.mark.parametrize("writer_declaration", [1, True])
def test_invalid_selected_owner_refuses_before_runtime_or_audit(tmp_path,monkeypatch,writer_declaration):
    from integrations.research_read_mcp import release_identity,runtime
    m=launcher()
    owner=tmp_path.resolve()/'owner.json'
    value={'schema':release_identity.SELECTED_ARCHIVE_OWNER_SCHEMA,
        'manifest_path':str(tmp_path.resolve()/'manifest.json'),
        'manifest_sha256':'e'*64,
        'selected_read':{'expected_producer_commit':'b'*40,'max_age_seconds':3600,
            'max_reuse_seconds':300,'corpus_byte_budget':32*1024*1024,
            'image_admission_bytes':256*1024*1024,'refresh_interval_seconds':30,
            'writer_protocol_qualified':writer_declaration,'valid_until':int(time.time())+3600}}
    owner.write_text(json.dumps(value));owner.chmod(0o600)
    archive_checks=[]
    monkeypatch.setattr(release_identity,'verify_archive_release',lambda *a,**k:archive_checks.append(a))
    monkeypatch.setattr(runtime,'load_deployment',lambda *a,**k:parsed())
    composed=[]
    monkeypatch.setattr(m,'create_runtime',lambda *a,**k:composed.append(a))
    target=tmp_path.resolve()/'audit'
    # qualify itself refuses: no audit directory, factory or listener is ever reached.
    result=m.main(['--config','/synthetic/deployment.json','--archive-owner',str(owner),
                   '--audit-directory',str(target)])
    assert result==1 and not composed and not target.exists()
    # A valid declaration reaches both archive checks before this deliberately
    # foreign launcher identity refuses. An invalid declaration reaches none;
    # missing manifest or later gates cannot make the negative case vacuous.
    assert len(archive_checks)==(2 if writer_declaration is True else 0)


def test_admitted_options_run_selected_path_with_owner_and_refresh(tmp_path,monkeypatch):
    asyncio.run(selected_composition(tmp_path,monkeypatch))


async def selected_composition(tmp_path,monkeypatch):
    from integrations.research_read_mcp import port_adapter
    from integrations.research_read_mcp.selected_delivery import GuardedOperation
    from integrations.research_read_mcp.selected_factory import (SelectedMacroComposition,
                                                                SelectedReadOptions)
    h=Harness();s=Service();m=launcher();h.clock=int(time.time())
    path=tmp_path.resolve()/'grant.json'
    write_grant(path,h.policy.policy_id,h.full.subject_digest,expires=h.clock+100)
    deployment=parsed(grant_path=str(path),policy_id=h.policy.policy_id)
    options=SelectedReadOptions(expected_producer_commit='b'*40,writer_policy=lambda:True)
    prepared=[]
    class Provider:
        def run(self,operation):
            return GuardedOperation(value=None,selection_identity=None,
                                    delivery_guard=lambda:'UNPREPARED')
        def prepare(self):
            prepared.append('prepare')
        def refresh(self):
            prepared.append('refresh')
    # The real supplied composition wrapper around the same synthetic service.
    selected=SelectedMacroComposition(s,CanonicalReadContext,{'state':'SYNTHETIC_FACTORY_ONLY'},
                                      Provider(),GuardedOperation,KeyError)
    assert selected.ready() is False
    monkeypatch.setattr(port_adapter,'compose_selected_macro_service',lambda *a,**k:selected)
    class Verifier:
        receipts=({'state':'SYNTHETIC_BYTES_ONLY'},)
        selected_options=options
        def __call__(self,*args):return None
    h.app=m.create_runtime(deployment,Verifier(),h.policy,audit_sink=h.audit,
                           selected_options=options)
    assert h.app.state.research_selection_owner is selected
    assert h.app.state.research_refresh_owner is not None
    # This test substitutes the entire composition factory, including prepare.
    # Real startup preparation is pinned by test_selected_factory.
    assert prepared==[]
    await h.start()
    try:
        health=await h.client.get('/healthz')
        assert health.status_code==200 and health.json()=={'ok':True}
        ready=await h.client.get('/readyz')
        # An unprepared generation stays unready: the legacy path never answers.
        assert ready.status_code==503 and ready.json()=={'ready':False}
        assert ready.headers['cache-control']=='no-store'
    finally:
        await h.stop()


def test_unexpected_owner_shape_refuses_without_legacy_factory(tmp_path,monkeypatch):
    m=launcher();policy=Harness().policy;deployment=parsed(policy_id=policy.policy_id)
    calls=[]
    result,served=serve_with(tmp_path,monkeypatch,m,deployment,policy,object(),
        lambda *a,**k:calls.append(k))
    assert result==1 and not calls and not served
