"""Actual current installed factories vs Fresh's existing nominal phase.

No Fresh modifying operation, provider, Job, Attempt or original-store write.
The owned fixture AF_UNIX constructor never starts/serves; published-cache and
namespace/seal/physical-child seams are explicitly inherited fixture inputs.
"""
import os
import shutil
import pytest
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from common import fresh_conversation_contract as wire
from common.executive_workspace_contract import RESOURCE,SCOPE
from integrations.business_mcp_auth.contracts import load_resource_policy,subject_digest,AUTH_POLICY_SCHEMA
from control_plane.executive_runtime import Runtime
from control_plane.workspace_source_operations import SourceOperationEvents
from control_plane.workspace_project_git_publisher import PublisherBinding
from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData
from integrations.mastermind_workspace_app.project_git_identity import InstalledProjectGitIdentity
from integrations.mastermind_workspace_app.project_authoring_grant import SCHEMA_V5,legacy_workspace_document
from integrations.mastermind_workspace_app.contract import workspace_authorizers
from control_plane.workspace_read_service import WorkspaceReadService
from control_plane.fresh_conversation_membership import read_canonical_membership
from tests.test_workspace_project_authoring_grant import project_bindings
from tests.test_workspace_read_service import cache_fixture
from scripts import chairman_control_room as ccr
import control_plane.project_canonical_data
import control_plane.agentos_project_plan
import control_plane.agentos_plan_continuity_capture

P=Path('/Volumes/Mastermind/evidence/mmos-commission-01a15741/product-parity/s34-fresh-conversation-01a1aa3d')
ORIGINAL_B=Path('/var/folders/sb/h3rq5rvj1b3_r18p6w9swyp80000gn/T/mmos-s34-source-measure-7ff7-01a1aa3d/test_signed_created_n_preview_0').resolve()
REPO=Path.cwd()

def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()



@pytest.fixture
def installed_inputs(monkeypatch,tmp_path):
    import faulthandler
    faulthandler.cancel_dump_traceback_later();faulthandler.enable()
    B=ORIGINAL_B
    if not B.is_dir():pytest.skip('requires retained inert canonical CREATE source operands; no live substitute')
    fixture=json.loads((P/'S34_SOURCE_CHECK_MEASURE_7FF7.json').read_bytes())
    work=fixture['request']['work_ref'];code=fixture['code_commit'];current=fixture['data_commit']
    assert git(B/'configured-code','rev-parse','HEAD')==code
    assert git(B/'origin.git','rev-parse','main')==current
    source_B=B
    for part in ('configured-code','clone','origin.git'):shutil.copytree(B/part,tmp_path/part)
    B=tmp_path
    git(B/'clone','remote','set-url','origin',str(B/'origin.git'))
    runtime=Runtime.at(source_B/'planning/runtime',create=False)
    before=(len(runtime.events.list_events()),len(runtime.jobs.list_jobs()),len(runtime.attempts.list_attempts()))
    events=SourceOperationEvents(runtime.store)
    issuer='https://issuer.example.invalid'
    policy=load_resource_policy(dict(schema=AUTH_POLICY_SCHEMA,policy_id='planning-workspace-read',resource=RESOURCE,
        resource_metadata_url=RESOURCE+'/.well-known/oauth-protected-resource',issuer=issuer,authorization_servers=[issuer],
        jwks_uri=issuer+'/.well-known/jwks.json',required_scopes=[SCOPE],allowed_subject_digests=[subject_digest(issuer=issuer,subject='inert-chairman')],
        allowed_algorithms=['RS256'],clock_skew_seconds=30,max_token_lifetime_seconds=900,jwks_cache_ttl_seconds=300,
        unknown_kid_refresh_cooldown_seconds=30,fetch_failure_backoff_seconds=5))
    frame=dict(policy_id=policy.policy_id,issuer_digest=hashlib.sha256(issuer.encode()).hexdigest(),resource=RESOURCE,
        subject_digest=policy.allowed_subject_digests[0],client_ref=hashlib.sha256((issuer+'\nclient\ninert-client').encode()).hexdigest(),scopes=[SCOPE])
    # Reconstruct the same declared inert READ binding from the original fixture
    # recipe, and first prove its namespace equals the EXISTING real Event.
    scope=wire.canonical_digest(frame)
    lookup={'schema':'mastermind.workspace_source_operation_lookup.v1',**fixture['project_source']['selection']}
    original=events.read_status(lookup,scope,guard=lambda:True)
    assert original["receipt"]["kind"]=="SOURCE_OBSERVED"
    _,document=project_bindings();document=copy.deepcopy(document);document['schema']=SCHEMA_V5
    for slot in document['profiles'].values():
        slot['enabled']=False;slot['binding']=None
        slot['project_plan_proposal_publish']=None;slot['project_canonical_data_read']=None
    slot=document['profiles'][document['primary_profile']]
    slot['enabled']=True;slot['binding']={**frame,'permission_digest':'a'*64};slot['project_canonical_data_read']='b'*64
    from ops.executive_os import executive_mcp_entry
    monkeypatch.setattr(executive_mcp_entry,'require_sealed_path',lambda _:None)  # same named inert seal seam
    config=source_B/'control.json'
    identity=InstalledProjectGitIdentity(config_path=config,expected_config_sha256=hashlib.sha256(config.read_bytes()).hexdigest())
    identity.binding=PublisherBinding(worktree=str(B/'clone'),expected_origin=str(B/'origin.git'),default_branch='main',publisher_identity='synthetic-fixed-service-identity')
    monkeypatch.setattr(identity,'qualify',lambda binding:binding==identity.binding)  # same credential/account seam
    source=source_B/'planning/proof-source';source_sha=git(source,'rev-parse','HEAD')
    collector=InstalledBootPacketCollector(source_root=source,macro_root=B/'configured-code',code_root=REPO,
        python_executable=Path(sys.executable),expected_source_sha=source_sha)
    from integrations.executive_mcp import installed as installed_module
    def same_actual_snapshot(env,*,deadline=None,snapshot_capture=None):
        observed=installed_module._clean_git_snapshot(B/'configured-code',runner=collector._runner,env=env,label='Macro source',
            content_scope='macro_brief',include_seal=True,deadline=deadline,snapshot_capture=snapshot_capture,_allow_synthetic_fixture=True)
        return source_sha,observed[0],'synthetic-test-Root-seal',observed[1]
    monkeypatch.setattr(collector,'_snapshot_pair',same_actual_snapshot)
    def same_physical_child(**selected):
        owner,view,selected_work=installed_module._CANONICAL_PROJECT_DATA.get()
        assert owner is collector and selected_work==selected['work_ref']
        return view.read_plan(**selected)
    monkeypatch.setattr(collector,'read_project_plan',same_physical_child)  # same declared isolated-child seam
    data=InstalledCanonicalProjectData(collector=collector,policy=policy,load_bindings=lambda:document,
        git_identity=identity,events=events,runtime_guard=lambda:True)
    owners,clock,cache=cache_fixture(tmp_path/'read-only-profile-cache')
    doc=owners[0].state_cache['doc'];doc['sources']={'macro_sha':code}
    with owners[0].state_lock:ccr._publish_source_validity(owners[0],doc,tuple(clock),tuple(clock))
    _,authorize=workspace_authorizers(policy=policy,load_bindings=lambda:legacy_workspace_document(document,policy))
    reader=WorkspaceReadService(cache=cache,runtime=runtime,authorize=authorize,armed={},runtime_identity={},canonical_project_data=data.installed_binding())
    snapshot=reader.cache.snapshot()
    return locals()



from tests.test_workspace_control_room_factory import hosted,room_socket
from tests.test_mastermind_executive_app_asgi import rsa_key


@pytest.fixture
def actual_installed_owner(installed_inputs,hosted,rsa_key,monkeypatch,tmp_path):
    import asyncio
    from integrations.mastermind_workspace_app.installed_source_operations import InstalledWorkspaceSourceOperations
    from control_plane.workspace_read_service import workspace_provider_factory
    from control_plane.fresh_conversation import FreshConversationOwner
    from control_plane.fresh_conversation_membership import _project_validation_phase,_PHASE
    from control_plane.executive_service import ExecutiveControlService,CeoIngressAppBinding
    from tests.test_executive_service import _config
    from tests import test_mastermind_executive_app_asgi as auth
    from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
    from control_plane.principal_projection import neutral_principal_projection
    f=installed_inputs;host,_baseline=hosted
    # Only published-cache ownership is a declared inert hosted-lifecycle seam.
    # Constructor verified the fixture's actual owned AF_UNIX listener. No start.
    assert host._server is None and host._server_thread is None
    f['owners'][0].state_cache['composed_monotonic']=time.monotonic()
    monkeypatch.setattr(host,'current_owner',lambda:f['owners'][0])
    namespace={'current':True}
    factory=InstalledWorkspaceSourceOperations(collector=f['collector'],policy=f['policy'],
        load_bindings=lambda:f['document'],git_identity=f['identity'],runtime_guard=lambda r:r is f['runtime'] and namespace['current'])
    provide=workspace_provider_factory(control_room=host,authorize=f['authorize'],armed={},runtime_identity={},
        canonical_project_read_bindings_factory=factory.read_bindings)
    issued=[]
    actual_init=WorkspaceReadService.__init__
    def observed_init(reader,*args,**kwargs):
        actual_init(reader,*args,**kwargs);issued.append(reader)
    monkeypatch.setattr(WorkspaceReadService,'__init__',observed_init)
    # Observe the actual constructor, keep the actual installed provider itself
    # in the App binding (no wrapper can hide its nominal source identity).
    config=_config(tmp_path/'service',runtime_root=f['runtime'].store.root)
    service=ExecutiveControlService(config)
    service.runtime=f['runtime']
    class NoExecutionGrounding:
        def observe(self):raise AssertionError('pure membership read acquired execution grounding')
    binding=CeoIngressAppBinding(peer_uid=os.geteuid(),armed=True,grounding_provider=NoExecutionGrounding(),
        session_bridge_provider_factory=lambda runtime:None,workspace_read_provider_factory=provide)
    service._ceo_ingress_app_binding=binding;service._ceo_ingress_ready=True
    issuer=f['issuer'];now=int(time.time())
    policy=auth._submit_policy(issuer=issuer,authorization_servers=[issuer],jwks_uri=issuer+'/.well-known/jwks.json',
        allowed_subject_digests=[f['policy'].allowed_subject_digests[0]])
    exec_auth=JwtAuthenticator(policy=policy,jwks_cache=auth._FakeJwksCache(rsa_key))
    exec_token=auth._submit_token(rsa_key,iss=issuer,sub='inert-chairman',client_id='inert-client',iat=now-1,nbf=now-1,exp=now+600)
    workspace_auth=JwtAuthenticator(policy=f['policy'],jwks_cache=auth._FakeJwksCache(rsa_key))
    workspace_token=auth._token(rsa_key,scope=SCOPE,aud=RESOURCE,iss=issuer,sub='inert-chairman',client_id='inert-client',iat=now-1,nbf=now-1,exp=now+600)
    async def verified():
        return (await exec_auth.verify_token(exec_token,now=now),await workspace_auth.verify_token(workspace_token,now=now))
    signed,read_signed=asyncio.run(verified())
    principal=neutral_principal_projection(**dataclasses.asdict(signed))
    workspace=neutral_principal_projection(**dataclasses.asdict(read_signed))
    assert {key:list(workspace.scopes)if key=='scopes'else getattr(workspace,key)for key in f['frame']}==f['frame']
    owner=FreshConversationOwner(service,expected_policy=(principal.policy_id,principal.issuer_digest,principal.resource))
    return locals()


def test_current_installed_factory_rejoins_one_fresh_pure_phase(actual_installed_owner,tmp_path):
    from control_plane.fresh_conversation_membership import _project_validation_phase,_PHASE
    a=actual_installed_owner
    f,host,owner,principal,workspace,issued=(a[k]for k in ('f','host','owner','principal','workspace','issued'))
    output=Path(os.environ['S34_FACTORY_LIFETIME_OUTPUT']) if 'S34_FACTORY_LIFETIME_OUTPUT' in os.environ else tmp_path/'installed-reader-lifetime.json'
    diagnostic=dict(schema='mastermind.s34.installed_reader_lifetime_discriminator.v1',
        source_revision=os.environ.get('S34_SOURCE_REVISION'),seams=['actual owned AF_UNIX constructor, no host start/serve',
            'published-cache lifecycle/namespace/Root seal/credential/physical-child fixture seams',
            'actual current installed SourceOperations.read_bindings and workspace_provider_factory',
            'actual signed RS256 principal pair; no Fresh modifying call or provider'])
    def save():
        diagnostic.update(provider_calls=len(issued),distinct_readers=len({id(r)for r in issued}),
            distinct_bindings=len({id(r._canonical_project_data)for r in issued}),
            same_store=all(r.runtime.store is f['runtime'].store for r in issued),
            same_policy_object=all(r._canonical_project_data.owner.policy is f['policy']for r in issued),
            counts_unchanged=f['before']==(len(f['runtime'].events.list_events()),len(f['runtime'].jobs.list_jobs()),len(f['runtime'].attempts.list_attempts())),
            hosted_started=host._server is not None)
        output.write_text(json.dumps(diagnostic,sort_keys=True,indent=2)+'\n')
    try:
        with _project_validation_phase(owner,principal,workspace,f['work']):
            phase=_PHASE.get();assert phase.view is not None and phase.active
            diagnostic['first_actual_canonical_read_succeeded']=True
            expected=phase.project_digest
            result=owner._project(principal,workspace,f['work'])
            assert wire.canonical_digest(result)==expected
            diagnostic['nested_rejoin_succeeded']=True
    except Exception as exc:
        diagnostic.update(error_type=type(exc).__name__,public_reason=str(exc),nested_rejoin_succeeded=False)
        save();raise
    finally:
        save()
        assert diagnostic['counts_unchanged'] and not diagnostic['hosted_started']


@pytest.mark.parametrize("change",[
    "descriptor_metadata", "source_constructor", "source_method", "source_runtime_guard",
    "collector", "loader", "source_pin", "owner", "principal", "workspace", "work", "phase_copy",
    "read_revocation", "namespace", "deadline", "default_drift", "lease_copy", "descriptor_copy",
])
def test_actual_installed_phase_refuses_changed_context(actual_installed_owner,monkeypatch,change):
    from control_plane.fresh_conversation_membership import _project_validation_phase,_PHASE,_reader_for_project_phase
    a=actual_installed_owner
    f,owner,principal,workspace,provide,factory=(a[k]for k in ('f','owner','principal','workspace','provide','factory'))
    before=f['before'];changed_callback_calls=[]
    try:
        with pytest.raises((ValueError,PermissionError)):
            with _project_validation_phase(owner,principal,workspace,f['work']):
                phase=_PHASE.get();assert phase.active
                with monkeypatch.context() as m:
                    if change=='descriptor_metadata':
                        constructor=dict(zip(provide.__code__.co_freevars,(c.cell_contents for c in provide.__closure__)))
                        m.setitem(constructor['armed'],'changed',True)
                    elif change=='source_constructor':m.setattr(factory,'_journey',object())
                    elif change=='source_method':m.setattr(factory,'canonical_data_owner',lambda runtime:None)
                    elif change=='source_runtime_guard':m.setattr(factory,'_runtime_guard',lambda runtime:(changed_callback_calls.append(True) or True))
                    elif change=='collector':m.setattr(factory,'_collector',object())
                    elif change=='loader':m.setattr(factory._permissions,'_load_bindings',lambda:f['document'])
                    elif change=='source_pin':m.setattr(f['collector'],'_expected_source_sha','0'*40)
                    elif change=='owner':
                        other=copy.copy(owner)
                        _reader_for_project_phase(other,principal,workspace,f['work'],provide)
                    elif change=='principal':
                        _reader_for_project_phase(owner,copy.copy(principal),workspace,f['work'],provide)
                    elif change=='workspace':
                        _reader_for_project_phase(owner,principal,copy.copy(workspace),f['work'],provide)
                    elif change=='work':
                        _reader_for_project_phase(owner,principal,workspace,'WS:FOREIGN',provide)
                    elif change=='phase_copy':
                        token=_PHASE.set(copy.copy(phase))
                        try:_reader_for_project_phase(owner,principal,workspace,f['work'],provide)
                        finally:_PHASE.reset(token)
                    elif change=='lease_copy':m.setattr(phase,'provider_lease',copy.copy(phase.provider_lease))
                    elif change=='descriptor_copy':
                        from control_plane.workspace_read_provider_binding import _ATTRIBUTE
                        m.setattr(provide,_ATTRIBUTE,copy.copy(getattr(provide,_ATTRIBUTE)))
                    elif change=='read_revocation':
                        m.setitem(f['document']['profiles'][f['document']['primary_profile']],'enabled',False)
                    elif change=='namespace':m.setitem(a['namespace'],'current',False)
                    elif change=='deadline':m.setattr(phase.capture.operation,'read_deadline',time.monotonic()-1)
                    elif change=='default_drift':
                        git(f['B']/'clone','fetch','origin','main')
                        git(f['B']/'clone','checkout','--detach','FETCH_HEAD')
                        git(f['B']/'clone','commit','--allow-empty','-m','actual external default drift')
                        git(f['B']/'clone','push','origin','HEAD:main')
                    owner._project(principal,workspace,f['work'])
                    if change!='default_drift':
                        pytest.fail('changed context escaped the actual installed pure phase')
                    # Default is a full outer-post fence, not a cached inner
                    # Git observation. Let that real fence execute below.
    finally:
        assert before==(len(f['runtime'].events.list_events()),len(f['runtime'].jobs.list_jobs()),len(f['runtime'].attempts.list_attempts()))
        assert a['host']._server is None
        assert not changed_callback_calls


def test_actual_installed_reader_lease_closes_at_phase_exit(actual_installed_owner):
    from control_plane.fresh_conversation_membership import _project_validation_phase,_PHASE
    a=actual_installed_owner
    f,owner,principal,workspace,provide=(a[k]for k in ('f','owner','principal','workspace','provide'))
    with _project_validation_phase(owner,principal,workspace,f['work']):
        phase=_PHASE.get();lease=phase.provider_lease
        assert wire.canonical_digest(owner._project(principal,workspace,f['work']))==phase.project_digest
        assert len(a['issued'])==1
    assert not lease.lifetime.active and phase.provider_lease is None
    with pytest.raises(ValueError):lease.current(phase,provide,f['runtime'])
    first=provide(f['runtime']);second=provide(f['runtime'])
    assert first is not second and first._canonical_project_data is not second._canonical_project_data
    assert _PHASE.get() is None
    assert f['before']==(len(f['runtime'].events.list_events()),len(f['runtime'].jobs.list_jobs()),len(f['runtime'].attempts.list_attempts()))


@pytest.mark.parametrize('change',['descriptor','principal','provider'])
def test_actual_installed_phase_refuses_late_full_post_change(actual_installed_owner,monkeypatch,change):
    from control_plane.fresh_conversation_membership import _project_validation_phase,_PHASE
    a=actual_installed_owner
    f,owner,principal,workspace,factory=(a[k]for k in ('f','owner','principal','workspace','factory'))
    fired=[];original_expiry=principal.expires_at;original_provider=owner._app.workspace_read_provider_factory
    try:
        with pytest.raises((ValueError,PermissionError)):
            with _project_validation_phase(owner,principal,workspace,f['work']):
                phase=_PHASE.get();mode=phase.view._owner;original=mode.check
                def transparent_full_post(view,*,operation=None):
                    result=original(view,operation=operation)
                    if view is phase.view and not phase.active:
                        fired.append(True)
                        if change=='descriptor':factory._journey=object()
                        elif change=='provider':object.__setattr__(owner._app,'workspace_read_provider_factory',lambda runtime:None)
                        else:object.__setattr__(principal,'expires_at',int(time.time())-1)
                    return result
                monkeypatch.setattr(mode,'check',transparent_full_post)
                assert wire.canonical_digest(owner._project(principal,workspace,f['work']))==phase.project_digest
        assert fired, 'late change was not exercised after the actual blocking full post'
    finally:
        object.__setattr__(principal,'expires_at',original_expiry)
        object.__setattr__(owner._app,'workspace_read_provider_factory',original_provider)
        assert f['before']==(len(f['runtime'].events.list_events()),len(f['runtime'].jobs.list_jobs()),len(f['runtime'].attempts.list_attempts()))


def test_installed_descriptor_cannot_tag_arbitrary_callback(actual_installed_owner):
    from control_plane.workspace_read_provider_binding import bind_installed_read_provider
    a=actual_installed_owner;calls=[]
    def arbitrary(runtime):calls.append(runtime);raise AssertionError('arbitrary callback ran')
    with pytest.raises(ValueError):bind_installed_read_provider(arbitrary,a['factory'].read_bindings)
    assert not calls and not a['issued']
