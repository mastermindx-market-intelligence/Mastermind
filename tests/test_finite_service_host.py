"""Real canonical source joins with isolated host observations, never root writes."""
import dataclasses
import json
from pathlib import Path
import stat
from types import SimpleNamespace
import grp
import pwd

import pytest
from ops.executive_os import finite_service_lifecycle as lifecycle
from ops.executive_os import attended_worker_definition as render
from ops.executive_os import credential_rotation_interlock as interlock
from ops.executive_os import gateway_refresh_preflight as gateway
from control_plane import codex_worker
from control_plane import fs_security
from control_plane.worker_execution_contract import BinaryAttestation
from control_plane.model_router import ModelRouter

SHA='a'*40


@pytest.fixture
def qualified_host(monkeypatch, tmp_path):
    calls=[]
    # A host observation fixture supplies an actual image on every test OS.
    # Production still resolves its fixed configured interpreter strictly.
    image = tmp_path / "python-image"
    image.write_bytes(b"fixture interpreter; never executed")
    image.chmod(0o555)
    interpreter = tmp_path / "python3"
    interpreter.symlink_to(image)
    monkeypatch.setattr(lifecycle, "PYTHON", str(interpreter))
    runtime=Path('/private/var/db/mastermind-executive')
    primary={'worker_id':'codex-01','worker_user':'_mastermind_worker','worker_uid':451,
             'worker_gid':451,'operator_harness_armed':False,'provider_home':str(runtime/'workers/codex-01/provider-home'),'control_uid':450}
    binary=BinaryAttestation(path='/fixture/claude',real_path='/fixture/claude',version='2.1.0',
        sha256='d'*64,team_identifier=None,size=11,device=1,inode=2,mode=0o555,uid=0,gid=0,mtime_ns=1)
    receipt=render._json({'schema_version':'mastermind.attended_claude_binary/v1','binary':dataclasses.asdict(binary)})
    receipt_path=lifecycle.SYSTEM/'config/claude-minimax-finite-01-attestation.json'
    manifest=render._json({'commit_sha':SHA,'tree_sha':'b'*40})
    mh=lifecycle.digest(manifest)
    artifacts=render.build_finite_worker_artifacts(primary_config=primary,worker_id='minimax-finite-01',
        worker_user='_mastermind_minimax',worker_group='_mastermind_minimax',worker_uid=470,worker_gid=470,
        control_gid=450,runtime_root=str(runtime),definition_dir=str(lifecycle.DEFINITION),
        socket_path=lifecycle.SOCKET,binary=binary,binary_receipt_path=str(receipt_path),
        binary_receipt_sha256=lifecycle.digest(receipt),realm_generation=1,
        release_root=str(lifecycle.SYSTEM/'releases'/SHA),release_commit=SHA,release_tree='b'*40,
        release_manifest_sha256=mh,python_binary=lifecycle.PYTHON,host_ref='host-'+'a'*64,model_class='routine',
        execution_profile_digest=ModelRouter.load().capability_registry.resolve('fabric.attended.claude.bounded.v1').profile_digest,
        routing_root_id=lifecycle.ROOT_ID,routing_parent_run_id=lifecycle.ROOT_ID,max_turns=2,
        capacity_capability_id='fixture-capacity')
    control=render.build_finite_control_delta(definition_dir=str(lifecycle.DEFINITION),worker_artifacts=artifacts)
    control.update({key:False for key in ('coo_autonomy_armed','coo_operator_harness_armed','coo_foreground_only','ceo_submit_armed')})
    prior=SimpleNamespace(worker=primary,control=control,worker_sha256='c69f44c3c6e17f40d2deb674be5c9a999e0c5dee9d06e71309fb244c96ce0faf',control_sha256='e'*64)
    class Owner:
        def require_exact_install(self,sha):calls.append('installed');return sha
        def require_transaction_absent(self):calls.append('no-transaction')
        def require_services_already_stopped(self):calls.append('stopped')
        def require_service_uids_quiescent(self):calls.append('primary-quiescent')
        def load_unarmed_configs(self,sha):calls.append('disarmed');return prior
        def require_runtime_quiescent(self,prior):calls.append('runtime-idle')
        def _loaded_observe_only(self,label):assert label=='com.mastermind.executive.backup';return False
    host=lifecycle.ProductionHost(mh);host.sha=SHA;host.owner=Owner()
    def disarmed():calls.append('credential-disarmed')
    monkeypatch.setattr(interlock,'assert_credential_mutation_disarmed',disarmed)
    monkeypatch.setattr(gateway,'qualify_gateway_refresh',lambda sha:{'release_sha':sha})
    monkeypatch.setattr(lifecycle,'checked_command',lambda argv:SimpleNamespace(stdout=(
        'system/com.mastermind.executive.mcp = {\n\tpath = /Library/LaunchDaemons/com.mastermind.executive.mcp.plist\n'
        '\tstate = running\n\tpid = 123\n}\n').encode()))
    monkeypatch.setattr(pwd,'getpwnam',lambda name:SimpleNamespace(pw_name='_mastermind_minimax',pw_uid=470,pw_gid=470,
        pw_dir=str(runtime/'workers/minimax-finite-01/provider-home'),pw_shell='/usr/bin/false'))
    monkeypatch.setattr(grp,'getgrnam',lambda name:SimpleNamespace(gr_gid=470))
    monkeypatch.setattr(lifecycle.os,'getgrouplist',lambda *a:[470])
    active=runtime/'workers/minimax-finite-01/active'
    original_stat=Path.lstat;original_iter=Path.iterdir
    def lstat(path):
        if path==active:return SimpleNamespace(st_uid=470,st_gid=470,st_mode=stat.S_IFDIR|0o700)
        return original_stat(path)
    def iterdir(path):
        if path==lifecycle.DEFINITION:return iter(lifecycle.DEFINITION/name for name in artifacts)
        return original_iter(path)
    monkeypatch.setattr(Path,'lstat',lstat);monkeypatch.setattr(Path,'iterdir',iterdir)
    monkeypatch.setattr(fs_security,'has_macos_acl',lambda *a,**kw:False)
    def protected(path,*,mode=0o444,gid=0):
        if path==receipt_path:
            assert (mode,gid)==(0o440,470);return receipt
        assert (mode,gid)==(0o444,0)
        if path.name=='.executive-release-manifest.json':return manifest
        return artifacts[path.name]
    monkeypatch.setattr(lifecycle,'protected_bytes',protected)
    monkeypatch.setattr(codex_worker,'_assert_binary_unchanged',lambda actual:actual==binary or pytest.fail('binary drift'))
    return host,prior,artifacts,calls


def test_production_qualifier_consumes_actual_canonical_renderer_and_all_quiescence_gates(qualified_host):
    host,prior,artifacts,calls=qualified_host
    value=host.qualify()
    assert value['artifact_sha256']=={name:lifecycle.digest(raw) for name,raw in artifacts.items()}
    assert value['gateway']=={'state':'running','pid':123}
    assert value['python_image'] == str(Path(lifecycle.PYTHON).resolve(strict=True))
    assert calls==['installed','no-transaction','stopped','primary-quiescent','credential-disarmed','disarmed','runtime-idle']


@pytest.mark.parametrize('gate',['require_transaction_absent','require_services_already_stopped',
    'require_service_uids_quiescent','require_runtime_quiescent'])
def test_live_owner_gate_failure_stops_before_canonical_artifact_acceptance(qualified_host,monkeypatch,gate):
    host,prior,artifacts,calls=qualified_host
    def refuse(*args):raise RuntimeError('owner gate refused')
    monkeypatch.setattr(host.owner,gate,refuse)
    monkeypatch.setattr(lifecycle,'protected_bytes',lambda *a,**kw:pytest.fail('must not read definition'))
    with pytest.raises(RuntimeError,match='owner gate refused'):host.qualify()


@pytest.mark.parametrize('drift',['primary','control','worker-bytes','entry-bytes','plist-bytes','groups','active-acl','gateway-not-running'])
def test_production_qualifier_refuses_real_cross_source_or_host_drift(qualified_host,monkeypatch,drift):
    host,prior,artifacts,calls=qualified_host
    if drift=='primary':prior.worker_sha256='a'*64
    elif drift=='control':prior.control['fabric_bindings_sha256']='f'*64
    elif drift=='worker-bytes':artifacts['worker.json']+=b' '
    elif drift=='entry-bytes':artifacts['owner_entry.py']+=b'# foreign\n'
    elif drift=='plist-bytes':artifacts[lifecycle.LABEL+'.plist']+=b'\n'
    elif drift=='groups':monkeypatch.setattr(lifecycle.os,'getgrouplist',lambda *a:[470,20])
    elif drift=='active-acl':monkeypatch.setattr(fs_security,'has_macos_acl',lambda *a,**kw:True)
    elif drift=='gateway-not-running':monkeypatch.setattr(lifecycle,'checked_command',lambda argv:SimpleNamespace(stdout=(
        'system/com.mastermind.executive.mcp = {\n\tpath = /Library/LaunchDaemons/com.mastermind.executive.mcp.plist\n'
        '\tstate = waiting\n}\n').encode()))
    with pytest.raises(lifecycle.LifecycleError):host.qualify()


@pytest.mark.parametrize('target,key',[
    ('control','coo_autonomy_armed'),('control','coo_operator_harness_armed'),
    ('control','coo_foreground_only'),('control','ceo_submit_armed'),
    ('control','fabric_bridge_armed'),('worker','operator_harness_armed')])
@pytest.mark.parametrize('value',[True,0,'false',None,'absent'])
def test_all_six_arm_fields_require_explicit_boolean_false_before_effect(qualified_host,monkeypatch,target,key,value):
    host,prior,artifacts,calls=qualified_host
    document=getattr(prior,target)
    if value=='absent':document.pop(key)
    else:document[key]=value
    monkeypatch.setattr(lifecycle,'protected_bytes',lambda *a,**kw:pytest.fail('must refuse before artifact reads'))
    with pytest.raises(lifecycle.LifecycleError,match='configs_not_wholly_disarmed'):host.qualify()
    assert 'runtime-idle' not in calls


def test_production_qualifier_refuses_missing_configured_interpreter(qualified_host):
    host, _, _, _ = qualified_host
    Path(lifecycle.PYTHON).unlink()
    with pytest.raises(FileNotFoundError):
        host.qualify()
