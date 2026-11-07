"""Typed source qualification; installed owners and binary reads are fixtures.

No real service, credentials, provider, reservation or production admission.
"""
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest
from control_plane import codex_provider_realm as realm
from control_plane import executive_fabric_bridge_broker as bridge
from control_plane.executive_fabric_adapter import FabricHostBinding
from control_plane.executive_worker_broker import BrokerPolicy, WorkerBrokerError
from control_plane.worker_execution_contract import BinaryAttestation
from integrations.session_bridge.bound_launch_capture import owner_assembly as assembly
from integrations.session_bridge.bound_launch_capture import fabric_attended_backend as backend
from scripts import executive_fabric_bridge as entry


@pytest.fixture
def fixed(tmp_path, monkeypatch):
    uid, gid = os.getuid(), os.getgid()
    paths = {key: tmp_path/key for key in ('workspace', 'runs', 'home', 'active')}
    for path in paths.values():
        path.mkdir(mode=0o700)
    raw = dict(control_uid=450, worker_uid=uid, worker_gid=gid, worker_id='finite-minimax',
        worker_user='fixture-worker', allowed_supplementary_gids=[],
        provider_home=str(paths['home']), workspace_root=str(paths['workspace']), run_root=str(paths['runs']))
    config_path=tmp_path/'bridge.json'
    document=dict(schema_version=bridge.CONFIG_SCHEMA_VERSION, adapter_id='attended-fabric',
        bridge_uid=uid, control_uid=450, launchd_socket_name='FabricBridge',
        socket_path=str(tmp_path/'fixture.sock'), workspace_root=str(paths['workspace']),
        run_root=str(paths['runs']), max_request_bytes=65536, max_response_bytes=262144,
        request_timeout_seconds=10, validation_commands=[])
    def config():
        return dataclasses.replace(bridge.BridgeConfig.from_document(document),
            source_sha256=hashlib.sha256(json.dumps(document).encode()).hexdigest(),
            _trust=bridge._TRUSTED_CONFIG)
    # These are explicit protected-file issuers, not fake source classes. Every
    # actual policy/catalogue/factory/entrypoint below runs without substitution.
    monkeypatch.setattr(bridge, 'load_config', lambda path: config())
    monkeypatch.setattr(entry, 'load_config', lambda path: config())
    physical=FabricHostBinding(socket_path=document['socket_path'], host_ref='fixture-host',
        worker_id=raw['worker_id'], worker_uid=uid, worker_gid=gid, bridge_uid=uid,
        provider='minimax', model='MiniMax-M3', provider_home=raw['provider_home'],
        worker_source_config_digest='a'*64, execution_profile_digest='b'*64,
        service_source_sha256='c'*64, binary_sha256='d'*64, permission_profile_sha256=assembly.finite_read_permission_digest())
    holder=SimpleNamespace(physical=physical, raw=raw, document=document, config=config, calls=[],
        realm_reads=0, definition_reads=0, binary_reads=0, drift=None)
    class Source:
        def __call__(self,*args):
            return holder.physical
    monkeypatch.setattr(assembly.FabricBindingSource, 'from_path', lambda *a,**k: Source())
    def definition(*args):
        holder.definition_reads += 1
        if holder.drift == 'definition' and holder.definition_reads > 1:
            return {**raw,'worker_user':'successor'}
        return dict(raw)
    monkeypatch.setattr(assembly.canary, 'definition', definition)
    owner=realm.SubscriptionRealmOwner(tmp_path/'worker.json','a'*64,realm._SUBSCRIPTION_REALM_OWNER_SEAL)
    observation=dict(worker_id=raw['worker_id'],control_uid=450,binding_id=assembly.canary.BINDING,
        profile_id='minimax-token-plan',adapter_id='claude-compatible-subscription',
        realm_config_sha256='a'*64,realm_generation=1,catalog_digest=assembly.compose_catalog_digest())
    def observe(self):
        holder.realm_reads += 1
        if holder.drift == 'realm' and holder.realm_reads > 1:
            return {**observation,'realm_generation':2}
        return dict(observation)
    monkeypatch.setattr(realm.SubscriptionRealmOwner, 'observe', observe)
    monkeypatch.setattr(realm,'load_subscription_realm_owner', lambda *a,**k: owner)
    binary=BinaryAttestation(path='/fixture/claude',real_path='/fixture/claude',version='fixture-1',
        sha256='d'*64,team_identifier=None,size=11,device=1,inode=2,mode=0o555,uid=0,gid=gid,mtime_ns=1)
    def read_binary(*args):
        holder.binary_reads += 1
        if holder.drift == 'binary' and holder.binary_reads > 1:
            return dataclasses.replace(holder.binary,inode=3)
        return holder.binary
    holder.binary=binary
    monkeypatch.setattr(realm,'_observe_attended_claude_binary',read_binary)
    def credential():
        holder.calls.append('credential')
        raise AssertionError('assembly must not load credentials')
    args=dict(config_path=config_path,bindings_path=tmp_path/'physical.json',bindings_sha256='f'*64,
        realm_config_path=owner._config_path,host_ref='fixture-host',worker_id=raw['worker_id'],
        routing_root_id='original-root',routing_parent_run_id='assigning-parent',active_dir=paths['active'],
        model_class='general',max_turns=2,credential_loader=credential,
        verified_release_manifest_sha256='c'*64)
    # Use the canonical catalogue's class, not a fixture alias or moving model.
    profiles=assembly.load_profiles()
    binding=assembly.get_binding(assembly.canary.BINDING,profiles_document=profiles)
    profile=assembly.get_profile(binding.profile_id,document=profiles)
    args['model_class']=next(key for key in binding.model_classes if binding.model_for(profile,key)==physical.model)
    holder.args=args;holder.observation=observation;holder.owner=owner
    yield holder
    assert holder.calls == [], 'secret bytes must remain untouched'


def compose(fixed, **changes):
    return assembly.compose_owner_resources(fixed.config(),**{**fixed.args,**changes})


def test_installed_private_entry_binds_loader_without_reading_secret(fixed, monkeypatch):
    def capture(**kwargs):
        assert kwargs['routing_root_id'] == fixed.args['routing_root_id']
        assert callable(kwargs['credential_loader'])
        return 47
    monkeypatch.setattr(assembly, 'run_owner_bridge', capture)
    monkeypatch.setattr(realm, 'load_private_provider_credential',
        lambda *a,**k: pytest.fail('construction cannot open a private credential'))
    arguments={key:value for key,value in fixed.args.items() if key != 'credential_loader'}
    assert assembly.run_private_owner_bridge(**arguments)==47


def test_private_entry_loader_rechecks_original_definition_before_open(fixed, monkeypatch):
    loaded=[]
    monkeypatch.setattr(realm, 'load_private_provider_credential',
        lambda *a,**k: loaded.append((a,k)))
    def capture(**kwargs):
        fixed.drift='definition'
        with pytest.raises(bridge.BridgeProtocolError):kwargs['credential_loader']()
    monkeypatch.setattr(assembly, 'run_owner_bridge', capture)
    arguments={key:value for key,value in fixed.args.items() if key != 'credential_loader'}
    assembly.run_private_owner_bridge(**arguments)
    assert loaded==[]


def test_typed_resources_reach_real_fixed_factory_without_start(fixed):
    resources=compose(fixed)
    assert type(resources.preparation['policy']) is BrokerPolicy
    assert resources.preparation['policy'].require_assignment_seal
    assert type(resources.binary_pin) is BinaryAttestation
    assert resources.credential_realm_owner is fixed.owner
    assert resources.routing_root_id=='original-root'
    assert resources.routing_parent_run_id=='assigning-parent'
    assert set(resources.preparation)=={'policy','binary','binding','profile','model_class','max_turns','allowed_validation_commands'}
    value=backend.create_attended_backend(fixed.config(),owner_resources=resources)
    assert type(value) is backend._SingleAssignmentComposition
    assert value._backend is None and not value._attempted
    assert set(fixed.owner.observe())=={'worker_id','control_uid','binding_id','profile_id','adapter_id','realm_config_sha256','realm_generation','catalog_digest'}


@pytest.mark.parametrize('fault', [None, 'host', 'capability', 'generation', 'revoke'])
def test_opted_in_owner_assembly_rechecks_source_enrollment_before_any_secret(fixed, monkeypatch, fault):
    fixed.raw.update(native_capacity_enrollment={}, capacity_capability_id='cap.fixture')
    reads = []
    def native(self):
        reads.append(1)
        value = {'host_ref': fixed.physical.host_ref, 'capacity_capability_id': 'cap.fixture',
                 'realm_generation': fixed.observation['realm_generation']}
        if fault == 'host': value['host_ref'] = 'foreign'
        if fault == 'capability': value['capacity_capability_id'] = 'foreign'
        if fault == 'generation': value['realm_generation'] += 1
        if fault == 'revoke' and len(reads) > 1:
            raise realm.ProviderRealmError('revoked current source')
        return value
    monkeypatch.setattr(realm.SubscriptionRealmOwner, 'observe_capacity_enrollment', native)
    if fault:
        with pytest.raises((bridge.BridgeProtocolError, realm.ProviderRealmError)): compose(fixed)
    else:
        assert compose(fixed).credential_realm_owner is fixed.owner
        assert len(reads) == 2
    assert fixed.calls == []


@pytest.mark.parametrize('change',[
    {'credential_loader':None},{'max_turns':True},{'max_turns':0},{'max_turns':65},
    {'nice':-1},{'nice':True},{'nice':20},{'routing_root_id':''},{'routing_parent_run_id':'bad parent'},
    {'active_dir':Path('relative')},
])
def test_bad_fixed_arguments_refuse_before_realm_or_secret(fixed,change):
    with pytest.raises(bridge.BridgeProtocolError): compose(fixed,**change)
    assert fixed.realm_reads==0


@pytest.mark.parametrize('field,value',[
    ('bridge_uid',460),('control_uid',451),('socket_path','/fixture/other.sock'),
    ('workspace_root','/fixture/other-workspace'),('run_root','/fixture/other-runs'),
    ('validation_commands',[['/usr/bin/true']]),
])
def test_config_policy_physical_mismatch_is_closed(fixed,field,value):
    fixed.document[field]=value
    with pytest.raises((bridge.BridgeProtocolError,ValueError)): compose(fixed)
    assert fixed.realm_reads==0


@pytest.mark.parametrize('field,value',[
    ('worker_uid',450),('worker_gid',9999),('worker_id','other'),
    ('provider_home','/fixture/foreign-home'),('bridge_uid',460),('provider','grok'),('model','different-model'),
])
def test_physical_join_does_not_relabel_actual_worker(fixed,field,value):
    fixed.physical=dataclasses.replace(fixed.physical,**{field:value})
    with pytest.raises((bridge.BridgeProtocolError,ValueError,WorkerBrokerError)): compose(fixed)
    assert fixed.realm_reads==0


def test_nonisolated_groups_refuse(fixed):
    fixed.raw['allowed_supplementary_gids']=[9999]
    with pytest.raises(WorkerBrokerError,match='isolated primary group'): compose(fixed)
    assert fixed.realm_reads==0


@pytest.mark.parametrize('field,value',[
    ('worker_id','other'),('control_uid',451),('binding_id','other'),('profile_id','other'),
    ('adapter_id','other'),('realm_config_sha256','9'*64),('catalog_digest','9'*64),
])
def test_wrong_realm_observation_refuses(fixed,field,value):
    fixed.observation[field]=value
    with pytest.raises(bridge.BridgeProtocolError): compose(fixed)


def test_binary_pin_mismatch_refuses(fixed):
    fixed.binary=dataclasses.replace(fixed.binary,sha256='9'*64)
    with pytest.raises(bridge.BridgeProtocolError): compose(fixed)


@pytest.mark.parametrize('drift',['definition','realm','binary'])
def test_current_owner_reads_cannot_drift_during_assembly(fixed,drift):
    fixed.drift=drift
    with pytest.raises(bridge.BridgeProtocolError): compose(fixed)


def test_config_digest_drift_is_not_hidden_by_equal_settings(fixed,monkeypatch):
    original=fixed.config()
    monkeypatch.setattr(bridge,'load_config',lambda _:dataclasses.replace(original,source_sha256='9'*64))
    with pytest.raises(bridge.BridgeProtocolError): compose(fixed)


def test_wrong_model_class_refuses(fixed):
    with pytest.raises(ValueError): compose(fixed,model_class='not-a-catalogue-class')
    assert fixed.realm_reads==0


@pytest.mark.parametrize('change', [{'implementation_state':'SPEC_ONLY'}, {'autonomous_allowed':True},
                                 {'profile_id':'foreign'}, {'provider':'grok'}])
def test_ineligible_catalogue_record_cannot_enable_route(fixed,monkeypatch,change):
    original=assembly.get_binding(assembly.canary.BINDING)
    monkeypatch.setattr(assembly,'get_binding',lambda *a,**k:dataclasses.replace(original,**change))
    with pytest.raises((ValueError,bridge.BridgeProtocolError)): compose(fixed)
    assert fixed.realm_reads==0


def test_background_thread_refuses_before_service(fixed):
    failures=[]
    def attempt():
        try: compose(fixed)
        except bridge.BridgeProtocolError as exc: failures.append(exc)
    thread=threading.Thread(target=attempt);thread.start();thread.join()
    assert len(failures)==1 and fixed.realm_reads==0


def test_actual_main_receives_fixed_backend_and_uses_one_main_loop(fixed,monkeypatch):
    seen=[]
    async def inert_serve(config,value,**kwargs):
        seen.append((config,value,asyncio.get_running_loop(),threading.current_thread()))
        assert type(value) is backend._SingleAssignmentComposition
        assert value._backend is None
    monkeypatch.setattr(entry,'serve',inert_serve)  # no socket activation in source qualification
    assert assembly.run_owner_bridge(**fixed.args)==0
    assert len(seen)==1 and seen[0][0]==fixed.config()
    assert seen[0][3] is threading.main_thread() and seen[0][2].is_closed()


def test_default_cli_stays_closed(fixed,monkeypatch):
    monkeypatch.setattr(entry,'serve',lambda *a,**k:pytest.fail('must not activate'))
    assert entry.main(['serve','--config',str(fixed.args['config_path'])])==2


def test_bad_owner_never_reaches_entrypoint_activation(fixed,monkeypatch):
    monkeypatch.setattr(entry,'serve',lambda *a,**k:pytest.fail('must not activate'))
    fixed.observation['catalog_digest']='9'*64
    assert assembly.run_owner_bridge(**fixed.args)==2


def test_existing_binary_validator_returns_attestation_without_changing_observation(monkeypatch):
    import ast
    import contextlib
    import inspect
    from control_plane import codex_worker
    binary=BinaryAttestation(path='/fixture/claude',real_path='/fixture/claude',version='fixture-1',
        sha256='d'*64,team_identifier=None,size=11,device=1,inode=2,mode=0o555,uid=0,gid=460,mtime_ns=1)
    raw=dict(claude_binary=binary.path,claude_attestation_receipt='/fixture/receipt',
        claude_attestation_sha256='a'*64,allowed_claude_versions=[binary.version])
    reads=[];assertions=[]
    def receipt(path,digest):
        reads.append((path,digest))
        return dict(schema_version='mastermind.attended_claude_binary/v1',binary=dataclasses.asdict(binary))
    @contextlib.contextmanager
    def opened(path):
        yield 9,SimpleNamespace(st_gid=460,st_mode=0o100440)
    monkeypatch.setattr(realm,'_native_read_config',receipt)
    monkeypatch.setattr(realm,'_native_open',opened)
    monkeypatch.setattr(codex_worker,'_assert_binary_unchanged',assertions.append)
    assert realm._observe_attended_claude_binary(raw,460)==binary
    assert assertions==[binary] and reads==[(Path('/fixture/receipt'),'a'*64)]*2
    # The existing exact START consumer forbids additive observation fields.
    source=ast.parse(inspect.getsource(realm))
    cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='SubscriptionRealmOwner')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='observe')
    returned=[n for n in ast.walk(method) if isinstance(n,ast.Return)]
    assert len(returned)==1
    assert {key.value for key in returned[0].value.keys}=={
        'worker_id','control_uid','binding_id','profile_id','adapter_id',
        'realm_config_sha256','realm_generation','catalog_digest'}
