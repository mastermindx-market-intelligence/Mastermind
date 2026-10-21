"""Inert caller integration through real broker/publisher/retainer validators.

Issuer and executed-image observations are fixture facts, never production.
No assigned host, provider, credential, service or runtime admission is used.
"""
import ast
import asyncio
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest
from integrations.session_bridge.bound_launch_capture import fabric_attended_backend as backend
from control_plane import executive_fabric_bridge_broker as bridge
from control_plane.fabric_control_start import (
    ControlStartAuthority, authorize_control_command, launch_identity, SCHEMA,
)
from control_plane.executive_worker_broker import PeerCredentials, BrokerPolicy
from control_plane.worker_execution_contract import OrchestrationLaunchSpec
from test_fabric_owned_start_assembly import world, lr
from test_fabric_bound_controller_wire import patched
from test_fabric_cleanup_bound_record import actual_record
from test_fabric_executor_credential_boundary import credential_fixture, _inject_owner_test_keys


@pytest.fixture
def harness(world, lr, tmp_path, monkeypatch, request):
    """Actual publisher/FDs/retainer; original executor fragment, inert begin."""
    slot = backend._ResourceSlot()
    monkeypatch.setattr(backend, '_RESOURCE_SLOT', slot)
    shutdown = []
    monkeypatch.setattr(backend.atexit, 'register', shutdown.append)
    prepared = SimpleNamespace(request_sha256=world.original['start_request_sha256'],
        descriptor=world.descriptor, validation_commands=(), lane_runtime_arguments=lambda: {})
    import integrations.session_bridge.bound_launch_capture.fabric_reserved_attended_launch as compiler
    canonical_prepare=compiler.prepare_reserved_attended_launch
    monkeypatch.setattr(compiler, 'prepare_reserved_attended_launch', lambda *a, **k: prepared)
    from control_plane import codex_worker, executive_worker_broker
    baseline = SimpleNamespace(head=world.spec['expected_base_sha'], status='')
    monkeypatch.setattr(codex_worker, '_git_snapshot', lambda *a, **k: baseline)
    # This existing inert publisher fixture has no real Control-owned roots.
    # Fresh filesystem checks are exercised independently below on real paths.
    monkeypatch.setattr(backend, '_require_current_assignment', lambda *args: None)
    world.with_spec(effective_grant_digest=world.binding['effective_grant_digest'])
    credential_source, credential_args, _expires, credential_calls = credential_fixture(tmp_path, monkeypatch)
    credentials={key:credential_args[key] for key in (
        'credential_loader','credential_realm_owner','credential_bindings_document','credential_profiles_document')}
    source = patched(tmp_path, 'remote_sub_exec.py', 'EXECUTOR_SOURCE.json')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
                and n.name == '_begin_reserved_attended_under_lease')
    calls = []
    def original_prepare(**kw):
        kw['authority'].require(kw['payload'])
        kw['check_original_owner'](prepared)
        assert kw['credential_loader'] is credentials['credential_loader']
        assert kw['credential_realm_owner'] is credentials['credential_realm_owner']
        assert all(kw[key]==credentials[key] for key in (
            'credential_bindings_document','credential_profiles_document'))
        return prepared, {'env':{}}, lambda: None
    def original_begin(**kw):
        calls.append(kw)
        assert isinstance(kw['receipt'], Path)
        assert kw['lease'] is lease
        return world.owner
    ns = dict(json=json, Path=Path, os=os, LaneRuntimeError=RuntimeError,
        _launch_receipt_directory=lambda p: None,
        _prepare_reserved_attended_under_lease=original_prepare,
        _begin_lease_process=original_begin,
        owned_capture_paths=lr.owned_capture_paths,
        validate_owned_capture_live=lr.validate_owned_capture_live)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<exact-committed-executor>', 'exec'), ns)
    credential_verifications=[]
    def verify_credentials(**kw):
        # Existing publisher fixtures use an inert, noncatalog descriptor.
        # Actual realm/catalog negatives below reuse the canonical source helper.
        credential_verifications.append(kw)
        assert kw['prepared'] is prepared and callable(kw['credential_loader'])
    executor=SimpleNamespace(_begin_reserved_attended_under_lease=ns[node.name],
        _verify_reserved_realm_observation=verify_credentials)
    monkeypatch.setattr(__import__('integrations.session_bridge.bound_launch_capture.runtime',fromlist=['remote_sub_exec']), 'remote_sub_exec', executor, raising=False)
    # Immutable actual fixed policy observation only needed by the fragment.
    policy_workspace=tmp_path.parent/(tmp_path.name+'-workspaces');policy_workspace.mkdir(mode=0o700)
    policy_home=tmp_path.parent/(tmp_path.name+'-provider');policy_home.mkdir(mode=0o700)
    world.physical=dataclasses.replace(world.physical,bridge_uid=os.geteuid(),provider_home=str(policy_home))
    world.canary['realm_binding']['physical_binding_sha256']=world.physical.digest
    world.canary['realm_binding']['provider_home']=world.physical.provider_home
    world.material['physical_binding_sha256']=world.physical.digest
    world.with_spec(secret_canary_verdict=world.canary)
    policy = BrokerPolicy(control_uid=450,worker_uid=os.geteuid(),worker_gid=os.getegid(),
        worker_user=world.worker_user,worker_id=world.spec['worker_id'],workspace_root=policy_workspace,
        run_root=Path(world.spec['run_dir']).parent,provider_home=policy_home,
        require_assignment_seal=True)
    workspace=policy_workspace/'task';workspace.mkdir(mode=0o700)
    world.spec['workspace_path']=str(workspace)
    world.descriptor.workspace_path=str(workspace)
    world.workspace_identity['path']=str(workspace)
    world.owner._invocation['cwd']=str(workspace)
    world.spec['isolation_manifest'] = dict(entries=[dict(disposition='CURRENT_RUN', identity={'fixture':1})],
        roots=[dict(path=str(policy.run_root))])
    world.with_spec(isolation_manifest=world.spec['isolation_manifest'])
    spec = OrchestrationLaunchSpec(**world.spec)
    monkeypatch.setattr(executive_worker_broker, '_launch_spec_from_wire', lambda *a: spec)
    prepared.request_sha256 = world.original['start_request_sha256']
    world.owner._original_start_context['request_sha256'] = prepared.request_sha256
    holds, releases = [], []
    lease = SimpleNamespace(hold_for_reconciliation=holds.append, release=lambda: releases.append(True))
    acquisitions=[]
    original_acquire = lr.LaneLease.acquire
    actual_lease = getattr(request, 'param', False)
    def acquire(*a, **k):
        nonlocal lease
        acquisitions.append((a,k))
        if actual_lease:
            lease = original_acquire(*a, **k, load1=0, cpu_count=4, max_active=4, env={})
        return lease
    monkeypatch.setattr(lr.LaneLease, 'acquire', acquire)
    # Publisher reuses actual ControlStartAuthority checks, removing fixture bypass.
    def require(authority, payload): authority.require(payload)
    monkeypatch.setattr(backend.fabric_owned_start, '_require_control_authority', require)
    correlation = dict(schema_version=backend.reservation.CORRELATION_SCHEMA,
        routing_root_id='original-native-root', routing_parent_run_id='exact-native-parent',
        runtime_binding=dict(root_id=world.binding['root_id'], job_id=world.binding['job_id'],
            attempt_id=world.run_id, effective_grant_sha256=world.binding['effective_grant_digest'],
            commission_sha256=world.binding['commission_sha256'],
            physical_binding_sha256=world.physical.digest, start_request_sha256=prepared.request_sha256))
    receipt = tmp_path/'original.process.jsonl'
    inputs = backend._OriginalOwnerInputs(original=world.original, correlation=correlation,
        preparation=dict(policy=policy,binary=world.pin,result_schema={'type':'object'}),
        physical=world.physical,binary_pin=world.pin,log_path=tmp_path/'original.log',
        active_dir=tmp_path/'active',receipt_path=receipt,qualified_evidence=world.evidence,
        workspace_identity=world.workspace_identity,provider_home_identity=world.provider_home_identity,
        **credentials)
    instance = backend.FabricAttendedBackend(inputs)
    # Trusted config and Control identity are explicitly inert fixtures.
    config = bridge.BridgeConfig(schema_version=bridge.CONFIG_SCHEMA_VERSION,
        adapter_id='attended-fabric',bridge_uid=world.physical.bridge_uid,control_uid=450,
        launchd_socket_name='FabricBridge',socket_path=Path('/var/run/inert.sock'),
        workspace_root=policy_workspace,run_root=tmp_path,max_request_bytes=65536,
        max_response_bytes=262144,request_timeout_seconds=10,validation_commands=(),
        _trust=bridge._TRUSTED_CONFIG)
    service=bridge.FabricBridgeBroker(config,instance)
    command = copy.deepcopy(world.material)
    command['control_start']=dict(schema_version=SCHEMA,attempt_id=world.run_id,
        fence_generation=1,pin_version=1,pin_identity_sha256=launch_identity(command),
        lease_expires_at='2099-01-01T00:00:00Z')
    def request(op, payload=None):
        if payload is None:
            payload=dict(binding=world.binding, physical_binding_sha256=world.physical.digest,run_id=world.run_id)
        return dict(schema_version=bridge.BROKER_REQUEST_SCHEMA_VERSION,
                    request_id='inert-request',operation=op,payload=payload)
    async def start():
        return await service.execute(request('start',command),peer=PeerCredentials(uid=450,gid=450))
    yield SimpleNamespace(world=world,lr=lr,instance=instance,service=service,slot=instance._slot,
        inputs=inputs,command=command,request=request,start=start,holds=holds,releases=releases,
        calls=calls,shutdown=shutdown,acquisitions=acquisitions,baseline=baseline,spec=spec,
        credential_source=credential_source,credential_args=credential_args,
        credential_calls=credential_calls,executor=executor,prepared=prepared,
        credential_verifications=credential_verifications,canonical_prepare=canonical_prepare)
    if actual_lease:
        # Fixture teardown closes descriptors only, never reconciles the marker.
        for name in ('fd', '_assignment_release_lock_fd', '_assignment_release_parent_fd'):
            fd = getattr(lease, name, None)
            if fd is not None:
                os.close(fd)


def run(coro): return asyncio.run(coro)


def test_real_fresh_broker_start_and_retained_status(harness):
    h=harness
    async def scenario():
        result=(await h.start())['result']
        assert result['process_ref']['run_id']==h.world.run_id
        assert h.calls[0]['arguments']['owned_capture_run_dir']==h.world.spec['run_dir']
        assert h.acquisitions[0][1]['reconcile_unreleased'] is True
        query=dict(binding=h.world.binding,physical_binding_sha256=h.world.physical.digest,
            run_id=h.world.run_id,start_request_sha256=result['request_sha256'])
        response=await h.service.execute(h.request('status',query),peer=PeerCredentials(uid=450,gid=450))
        assert response['result']['start_result']==result
        assert h.inputs.log_path.read_bytes().startswith(backend.reservation.CORRELATION_PREFIX)
        assert len(list(h.inputs.log_path.parent.glob('*.log')))==1
        # A recovered status is read-only and never reconstructs authority.
        assert h.slot.owner is h.world.owner and h.slot.lease is not None
    run(scenario())
    assert h.holds==h.releases==[]


@pytest.mark.parametrize('kind',['unissued','expired'])
def test_real_authority_refuses_before_reservation_slot_or_lease(harness,kind):
    h=harness
    authority=authorize_control_command(h.command,peer=PeerCredentials(uid=450,gid=450))
    authority=dataclasses.replace(authority, **({'_peer_verified':None} if kind=='unissued' else {'expires_at':1.0}))
    async def scenario():
        payload=copy.deepcopy(h.world.original)
        with pytest.raises(ValueError,match='control_start_authority_unavailable'):
            await h.instance.start_owned(payload,authority=authority)
    run(scenario())
    assert not h.slot.claimed and not h.inputs.log_path.exists() and h.acquisitions==h.calls==[]


def test_main_thread_before_effect_and_controller_wide_slot(harness):
    h=harness; errors=[]
    def other():
        async def scenario():
            try:h.instance._controller()
            except backend.AttendedBackendRefused as exc:errors.append(exc.code)
        run(scenario())
    thread=threading.Thread(target=other);thread.start();thread.join()
    assert errors==['controller_main_thread_required'] and not h.slot.claimed
    async def scenario():
        await h.start()
        second=backend.FabricAttendedBackend(h.inputs)
        with pytest.raises(backend.AttendedBackendRefused,match='controller_slot_occupied'):
            await second.execute('status',h.request('status')['payload'])
        # Lane cleanup's clearing its own singleton cannot release this slot.
        h.lr._EXECUTION_OWNER=None
        with pytest.raises(backend.AttendedBackendRefused,match='controller_slot_occupied'):
            await second.start_owned(h.world.original,authority=object())
    run(scenario())
    assert h.releases==[]


def test_existing_log_is_consumed_without_second_begin(harness):
    h=harness;h.inputs.log_path.write_bytes(b'original unresolved');h.inputs.log_path.chmod(0o600)
    async def scenario():
        with pytest.raises(bridge.BridgeProtocolError,match='EFFECT_UNKNOWN'):await h.start()
    run(scenario())
    assert h.slot.claimed and h.calls==h.acquisitions==[]
    assert h.inputs.log_path.read_bytes()==b'original unresolved'


def test_carrier_symlink_and_foreign_route_fail_closed(harness):
    h=harness
    async def scenario():
        await h.start()
        query=h.request('status')['payload'];query['start_request_sha256']=h.world.original['start_request_sha256']
        query['physical_binding_sha256']='0'*64
        with pytest.raises(backend.AttendedBackendRefused,match='foreign_original_route'):
            await h.instance.execute('status',query)
        query['physical_binding_sha256']=h.world.physical.digest
        path=h.inputs.receipt_path.with_suffix('.start.json');path.rename(path.with_suffix('.saved'))
        path.symlink_to(path.with_suffix('.saved'))
        with pytest.raises(backend.AttendedBackendRefused,match='carrier_unreadable'):
            await h.instance.execute('status',query)
    run(scenario())


@pytest.mark.parametrize('reason', [None, '', 'x' * 501, 'stop\x00now'])
def test_real_broker_refuses_invalid_cancel_before_backend_or_hold(harness, monkeypatch, reason):
    h = harness
    async def forbidden(*args, **kwargs):
        pytest.fail('invalid cancellation reached Backend')
    async def scenario():
        await h.start()
        monkeypatch.setattr(h.instance, 'execute', forbidden)
        payload = h.request('cancel')['payload']
        payload['reason'] = reason
        with pytest.raises(bridge.BridgeProtocolError):
            await h.service.execute(h.request('cancel', payload), peer=PeerCredentials(uid=450, gid=450))
    run(scenario())
    assert h.holds == h.releases == []


def test_real_cancel_wire_preserves_exact_whitespace_and_owner(harness,monkeypatch):
    h=harness; calls=[]
    def cancel(owner, **kw):
        calls.append((owner,kw))
        return dict(cancel_receipt=dict(run_id=h.world.run_id,reason=kw['reason'],
            signal_sent=False,escalated_to_sigkill=False,already_exited=True,
            finished_at='2026-10-13T01:00:00Z'))
    monkeypatch.setattr(h.lr,'cancel_exact_owned_process',cancel)
    async def scenario():
        await h.start(); payload=h.request('cancel')['payload'];payload['reason']=' stop '
        response=await h.service.execute(h.request('cancel',payload),peer=PeerCredentials(uid=450,gid=450))
        assert response['result']['cancellation']['reason']==' stop '
        assert calls[0][0] is h.slot.owner
        assert calls[0][1]['process_identity']==h.world.owner.process_identity
        assert h.slot.lease is not None and h.releases==[]
        with pytest.raises(backend.AttendedBackendRefused,match='assignment_original_identity_mismatch'):
            await h.instance.execute('assignment-seal-finalize',h.request('status')['payload'])
    run(scenario())
    h.shutdown[0]();assert h.holds==['assignment_settlement_pending_at_shutdown']


def test_cancelled_rpc_waiter_retains_join_and_canonical_collection(harness,monkeypatch):
    h=harness; joined=[]
    raw=b'{"structured_output":{"summary":"ok"},"session_id":"observed","usage":{}}'
    output=b'{"summary":"ok"}\n'
    def record(data):
        return dict(stream_bytes=len(data),file_bytes=len(data),stream_sha256=hashlib.sha256(data).hexdigest(),
                    file_sha256=hashlib.sha256(data).hexdigest(),complete=True)
    observation=dict(run_id=h.world.run_id,stdout=raw,stderr=b'',returncode=0,timed_out=False,
        finished_at='2026-10-13T01:00:00Z',cleanup={},cancel_receipt=None,
        capture=dict(stdout=record(raw),stderr=record(b''),result=dict(state='published',bytes=len(output),sha256=hashlib.sha256(output).hexdigest())))
    monkeypatch.setattr(h.lr,'cleanup_receipt_is_proven',lambda value:True)
    monkeypatch.setattr(h.lr,'owned_capture_collection',lambda owner:copy.deepcopy(observation))
    # This mock targets projection-waiter custody; exact carrier integration is
    # exercised separately using the real bound local-child terminal bytes.
    monkeypatch.setattr(h.instance,'_retain_cleanup',lambda observation:None)
    from control_plane import codex_worker
    monkeypatch.setattr(codex_worker,'_git_changed_paths',lambda *a:[])
    async def scenario():
        await h.start(); gate=asyncio.Event()
        async def collect(owner):
            joined.append(owner);await gate.wait();return object()
        monkeypatch.setattr(h.lr,'collect_owned_process',collect)
        task=asyncio.create_task(h.service.execute(h.request('collect'),peer=PeerCredentials(uid=450,gid=450)))
        await asyncio.sleep(0);await asyncio.sleep(0);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert not h.slot.collection_task.cancelled() and h.slot.owner is h.world.owner
        gate.set()
        response=await h.service.execute(h.request('collect'),peer=PeerCredentials(uid=450,gid=450))
        result=response['result']['collection']['result']
        assert result['status']=='SUCCEEDED' and result['usage']=={} and result['provider_session_id']=='observed'
        assert response['result']['collection']['process_ref']['provider_session_id']=='observed'
        assert len(joined)==1 and h.releases==[]
        # Source observations and client-owned response maps cannot rewrite retained result.
        observation['returncode']=1; result['status']='FAILED'
        again=await h.service.execute(h.request('collect'),peer=PeerCredentials(uid=450,gid=450))
        assert again['result']['collection']['result']['status']=='SUCCEEDED'
    run(scenario())


def test_factory_and_callback_surface_closed():
    with pytest.raises(backend.BackendNotConfiguredError):backend.create_attended_backend()
    with pytest.raises(TypeError):backend.FabricAttendedBackend(owner_check=lambda:None)


def test_rpc_cancel_before_start_is_preeffect_and_after_begin_keeps_original(harness,monkeypatch):
    h=harness
    async def scenario():
        before=asyncio.create_task(h.start());before.cancel()
        with pytest.raises(asyncio.CancelledError):await before
        assert not h.slot.claimed and not h.inputs.log_path.exists()
        original=backend.fabric_owned_start.publish_owned_start
        def cancelled(**kw):
            assert kw['owner'] is h.world.owner and h.slot.lease is not None
            raise asyncio.CancelledError()
        monkeypatch.setattr(backend.fabric_owned_start,'publish_owned_start',cancelled)
        with pytest.raises(asyncio.CancelledError):await h.start()
        assert h.slot.claimed and h.slot.owner is h.world.owner and h.slot.start is None
        assert h.slot.reconciliation_required and h.releases==[]
        monkeypatch.setattr(backend.fabric_owned_start,'publish_owned_start',original)
        with pytest.raises(backend.AttendedBackendRefused):
            await h.instance.start_owned(h.world.original,authority=object())
    run(scenario())
    assert h.calls and h.holds==['attended_start_unconfirmed']


@pytest.mark.parametrize('raw,exit_code,expected',[
    (b'{"structured_output":{"summary":"ok"},"session_id":"observed"}',0,'SUCCEEDED'),
    (b'not JSON',0,'INVALID_RESULT'),
    (b'{"is_error":true}',0,'INVALID_RESULT'),
    (b'{"structured_output":{"summary":"ok"}}',3,'FAILED'),
])
def test_actual_fd_capture_maps_canonical_result_and_real_wire_contract(lr,tmp_path,monkeypatch,raw,exit_code,expected):
    """Harmless local Python child, inert identity/census; actual FD bytes and Git."""
    import subprocess
    from control_plane import codex_worker
    from control_plane.worker_execution_contract import WorkerProcessRef, BinaryAttestation
    from test_executive_fabric_bridge_broker import start_result,start_payload
    workspace=tmp_path/'workspace';workspace.mkdir(mode=0o700)
    def git(*args):
        return subprocess.run(['git',*args],cwd=workspace,capture_output=True,text=True,check=True)
    git('init','-q');git('-c','user.name=Inert fixture','-c','user.email=inert@example.invalid',
        'commit','-qm','inert empty baseline','--allow-empty')
    baseline=codex_worker._git_snapshot(workspace,require_clean=True)
    run_dir=tmp_path/'capture';run_dir.mkdir(mode=0o700)
    monkeypatch.setattr(__import__('integrations.session_bridge.bound_launch_capture.runtime',fromlist=['lane_runtime']), 'lane_runtime', lr, raising=False)
    owner=lr.begin_owned_process([sys.executable,'-c',
        'import sys;sys.stdout.buffer.write(bytes.fromhex(sys.argv[1]));sys.exit(int(sys.argv[2]))',
        raw.hex(),str(exit_code)],timeout=5,label='attempt-1',receipt_path=tmp_path/'terminal.jsonl',
        owned_capture_run_dir=run_dir,owned_capture_result_schema_json='{"type":"object"}')
    lr.finish_owned_process(owner)
    observed=lr.owned_capture_collection(owner)
    spec=OrchestrationLaunchSpec(run_id='attempt-1',job_id='job-1',worker_id='worker-1',
        workspace_path=workspace,run_dir=run_dir,prompt='inert',result_schema_path=run_dir/'schema',
        authorities=('READ',),effective_grant_digest='a'*64,expected_base_sha=baseline.head)
    reference=start_result(start_payload())['process_ref']
    reference.update(provider_session_id=None,base_sha=baseline.head,started_at=owner.started_at,
        stdout_path=observed['capture']['stdout']['path'],stderr_path=observed['capture']['stderr']['path'],
        result_path=observed['capture']['result']['path'])
    reference['binary']=BinaryAttestation(**reference['binary'])
    ref=WorkerProcessRef(**reference)
    receipt=backend._project_collection(observed,spec=spec,schema={'type':'object'},baseline=baseline,process_ref=ref)
    value=backend._jsonable(receipt)
    assert value['result']['status']==expected
    assert value['stdout_sha256']==hashlib.sha256(raw).hexdigest()
    assert value['result']['usage']=={}
    common=dict(adapter_id='attended-fabric',binding=start_payload()['binding'],physical_binding_sha256='9'*64)
    # Actual validator method reads no service/config fields for collect.
    bridge.FabricBridgeBroker._operation_result(None,'collect',{**common,'collection':value},
        {**common,'run_id':'attempt-1'})


def assignment_payload(h):
    return dict(binding=h.world.binding,physical_binding_sha256=h.world.physical.digest,
        run_id=h.world.run_id,worker_id=h.spec.worker_id,process_ref=backend._jsonable(h.slot.start[0].process_ref))


@pytest.fixture
def settled_assignment(harness,monkeypatch):
    h=harness
    from control_plane import executive_worker_broker as owner, broker_assignment_seal as seal
    # Real bounded sweep mechanics with inert principal/process observations.
    real=owner.DedicatedUIDSweeper
    sweeps=[]
    def sweeper(uid, *, receipt_path):
        sweeps.append(uid)
        return real(uid,receipt_path=receipt_path,current_uid=lambda:uid,current_pid=lambda:321,
                    process_lister=lambda uid:(321,),sleep_fn=lambda duration:None)
    monkeypatch.setattr(owner,'DedicatedUIDSweeper',sweeper)
    identities={label:dict(path=str(path),device=1,inode=i+1,mode=0o770,
                            uid=h.inputs.preparation['policy'].control_uid,
                            gid=h.world.egid,mtime_ns=1)
        for i,(label,path) in enumerate((('workspace',h.spec.workspace_path),('run',h.spec.run_dir)))}
    monkeypatch.setattr(seal,'observe_roots',lambda *a:copy.deepcopy(identities))
    def denial(snapshot,control_seal,policy):
        seal.validate_control_seal(snapshot,control_seal,policy.control_uid)
        return {label:{k:'EACCES' for k in ('open','traverse','list')} for label in identities}
    monkeypatch.setattr(seal,'verify_control_seal',denial)
    async def already_collected():
        await h.start()
        async def completed():pass
        h.slot.collection_task=asyncio.create_task(completed());await h.slot.collection_task
        h.slot.collection=b'{"result":{"status":"SUCCEEDED"}}'
    return h,already_collected,sweeps


def test_assignment_original_sweep_snapshot_commit_and_missing_ack_stay_held(settled_assignment):
    h,start,sweeps=settled_assignment
    from control_plane.broker_assignment_seal import digest,control_retention_record
    async def scenario():
        await start();payload=assignment_payload(h)
        with pytest.raises(backend.AttendedBackendRefused,match='worker_denial_required'):
            await h.instance.execute('assignment-seal-finalize',{**payload,'observation_sha256':'a'*64,'retention_sha256':'b'*64})
        prepared=await h.instance.execute('assignment-seal-prepare',payload)
        assert prepared['snapshot']['uid_sweep']['worker_uid']==h.world.euid
        assert sweeps==[h.world.euid] and not h.slot.resource_released
        before=copy.deepcopy(prepared['snapshot'])
        prepared['snapshot']['job_id']='mutated client response'
        again=await h.instance.execute('assignment-seal-prepare',payload)
        assert again['snapshot']==before and sweeps==[h.world.euid]
        paths=before['paths']
        seal=dict(schema_version='mastermind.executive_assignment_seal/v1',sealed_at='2026-10-13T01:00:00Z',
            control_uid=h.inputs.preparation['policy'].control_uid,passed=True,
            paths={label:dict(before=entry,after={**entry,'mode':0o700},worker_traversal_revoked=True)
                   for label,entry in paths.items()})
        committed=await h.instance.execute('assignment-seal-commit',{**payload,'snapshot_sha256':digest(before),'seal':seal})
        observed=committed['observation']
        assert observed['snapshot']==before and h.releases==[] and not h.slot.resource_released
        with pytest.raises(backend.AttendedBackendRefused,match='settlement_already_entered'):
            await h.instance.execute('cancel',{**h.request('cancel')['payload'],'reason':'late'})
        with pytest.raises(backend.AttendedBackendRefused,match='control_ack_mismatch'):
            await h.instance.execute('assignment-seal-finalize',{**payload,'observation_sha256':'a'*64,'retention_sha256':'b'*64})
        assert not h.slot.control_acknowledged and h.releases==[]
        # Exact genuine ACK correlation alone cannot prove physical resource release.
        ack={**payload,'observation_sha256':digest(observed),'retention_sha256':digest(control_retention_record(observed))}
        with pytest.raises(backend.AttendedBackendRefused,match='verified_release_unavailable'):
            await h.instance.execute('assignment-seal-finalize',ack)
        assert h.slot.control_acknowledged and not h.slot.resource_released and h.releases==[]
        other=backend.FabricAttendedBackend(h.inputs)
        with pytest.raises(backend.AttendedBackendRefused,match='controller_slot_occupied'):
            await other.execute('status',h.request('status')['payload'])
    run(scenario())


def test_cancelled_assignment_waiter_does_not_abandon_sweep(settled_assignment,monkeypatch):
    h,start,sweeps=settled_assignment
    from control_plane import executive_worker_broker as owner
    initial=owner.DedicatedUIDSweeper
    entered,release=threading.Event(),threading.Event()
    threads=[]
    def blocked(uid,**kw):
        instance=initial(uid,**kw);original=instance.sweep
        def sweep(reason):
            threads.append(threading.current_thread());entered.set()
            assert release.wait(2)
            return original(reason)
        instance.sweep=sweep
        return instance
    monkeypatch.setattr(owner,'DedicatedUIDSweeper',blocked)
    async def scenario():
        await start();payload=assignment_payload(h)
        waiter=asyncio.create_task(h.instance.execute('assignment-seal-prepare',payload))
        async def wait_entered():
            while not entered.is_set():await asyncio.sleep(.001)
        await asyncio.wait_for(wait_entered(),2)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):await waiter
        assert not h.slot.assignment_task.cancelled() and not h.slot.resource_released
        release.set()
        prepared=await h.instance.execute('assignment-seal-prepare',payload)
        assert prepared['snapshot']['run_id']==h.world.run_id and len(sweeps)==1
        assert threads[0] is not threading.main_thread() and h.releases==[]
    try:run(scenario())
    finally:release.set()


async def committed_assignment(h, start):
    from control_plane.broker_assignment_seal import digest, control_retention_record
    await start()
    payload = assignment_payload(h)
    prepared = (await h.service.execute(h.request('assignment-seal-prepare', payload),
                                       peer=PeerCredentials(uid=450,gid=450)))['result']
    snapshot = prepared['snapshot']
    seal = dict(schema_version='mastermind.executive_assignment_seal/v1',
        sealed_at='2026-10-13T01:00:00Z',control_uid=h.inputs.preparation['policy'].control_uid,passed=True,
        paths={label:dict(before=entry,after={**entry,'mode':0o700},worker_traversal_revoked=True)
               for label,entry in snapshot['paths'].items()})
    committed = (await h.service.execute(h.request('assignment-seal-commit',
        {**payload,'snapshot_sha256':digest(snapshot),'seal':seal}),
        peer=PeerCredentials(uid=450,gid=450)))['result']
    observation = committed['observation']
    return {**payload,'observation_sha256':digest(observation),
            'retention_sha256':digest(control_retention_record(observation))}


@pytest.mark.parametrize('harness', [True], indirect=True)
@pytest.mark.parametrize('held', [False, True])
def test_real_original_lease_ack_requires_actual_durable_release(settled_assignment, held):
    h, start, _ = settled_assignment
    async def scenario():
        ack = await committed_assignment(h, start)
        lease = h.slot.lease
        assert type(lease) is h.lr.LaneLease
        if held:
            lease.hold_for_reconciliation('inert earlier unknown')
            original_bytes = lease.path.read_bytes()
            with pytest.raises(bridge.BridgeProtocolError, match='EFFECT_UNKNOWN'):
                await h.service.execute(h.request('assignment-seal-finalize', ack),
                                        peer=PeerCredentials(uid=450,gid=450))
            assert h.slot.control_acknowledged and not h.slot.resource_released
            assert h.slot.reconciliation_required and h.slot.release_receipt is None
            assert lease.path.read_bytes() == original_bytes and lease._preserve
            with pytest.raises(backend.AttendedBackendRefused,match='controller_slot_occupied'):
                await backend.FabricAttendedBackend(h.inputs).execute('status', h.request('status')['payload'])
        else:
            response = await h.service.execute(h.request('assignment-seal-finalize', ack),
                                                peer=PeerCredentials(uid=450,gid=450))
            assert response['result']['acknowledgement']['run_id'] == h.spec.run_id
            assert h.slot.control_acknowledged and h.slot.resource_released
            assert not lease.path.exists() and lease.fd is None
            receipt = json.loads(h.slot.release_receipt)
            assert response['result']['physical_release'] == receipt
            second = await h.service.execute(h.request('assignment-seal-finalize', ack),
                                             peer=PeerCredentials(uid=450,gid=450))
            assert second['result']['physical_release'] == receipt
            assert receipt['marker_absent'] is True and receipt['parent_synced'] is True
    run(scenario())


@pytest.mark.parametrize('harness', [True], indirect=True)
def test_post_release_cleanup_refusal_preserves_verified_settlement(settled_assignment, monkeypatch):
    h, start, _ = settled_assignment
    async def scenario():
        ack = await committed_assignment(h, start)
        await h.service.execute(h.request('assignment-seal-finalize', ack),
                                peer=PeerCredentials(uid=450,gid=450))
        assert h.slot.resource_released and h.slot.control_acknowledged
        assert type(h.slot.lease) is h.lr.LaneLease and h.slot.lease.fd is None
        release_receipt = h.slot.release_receipt
        # Failure injection only: no synthetic carrier is accepted as evidence.
        h.slot.cleanup_record = (b'unavailable original row', {}, {'collection': b'{}'})
        query = dict(schema_version='mastermind.executive_fabric_cleanup_query/v1',
            scope='collection', process_ref=backend._jsonable(h.slot.start[0].process_ref),
            host_ref=h.inputs.physical.host_ref, observed_after=backend.time.time(),
            readback_sha256=None)
        def unavailable(*args, **kwargs):
            raise FileNotFoundError('original terminal carrier unavailable after seal')
        monkeypatch.setattr(backend, '_read_original_file', unavailable)
        with pytest.raises(FileNotFoundError, match='original terminal carrier unavailable'):
            h.instance._cleanup({'cleanup_query': query}, {})
        assert not h.slot.reconciliation_required
        assert h.slot.release_receipt == release_receipt and h.slot.resource_released
        assert h.slot.control_acknowledged and not h.slot.lease.path.exists()
    run(scenario())


def test_settlement_status_uses_same_retained_original_after_control_seal(settled_assignment, monkeypatch):
    h, start, _ = settled_assignment
    async def scenario():
        await committed_assignment(h, start)
        original = copy.deepcopy(backend._jsonable(h.slot.start[0].process_ref))
        monkeypatch.setattr(backend, '_read_original_start',
                            lambda *a: pytest.fail('worker cannot reopen Control-sealed roots'))
        status = await h.service.execute(h.request('status'),peer=PeerCredentials(uid=450,gid=450))
        assert status['result']['run']['process_ref'] == original
        assert status['result']['run']['status'] == 'SUCCEEDED'
        query = {**h.request('status')['payload'],
                 'start_request_sha256':h.world.original['start_request_sha256']}
        recovered = await h.service.execute(h.request('status',query),peer=PeerCredentials(uid=450,gid=450))
        assert recovered['result']['start_result']['process_ref'] == original
        assert h.slot.owner is h.world.owner and not h.slot.resource_released
    run(scenario())


@pytest.mark.parametrize('harness', [True], indirect=True)
def test_actual_pending_guard_precedes_original_atexit_release(harness, tmp_path):
    h = harness
    async def scenario():
        await h.start()
        lease = h.slot.lease
        assert len(h.shutdown) == 2
        assert h.shutdown[0].__self__ is lease and h.shutdown[0].__name__ == 'release'
        assert h.shutdown[1].__self__ is h.instance
        # Actual atexit LIFO: the pending guard holds before legacy release.
        for callback in reversed(h.shutdown):
            callback()
        # Existing hold atomically publishes its reconciliation marker.
        assert lease.path.exists() and lease._preserve
        assert json.loads(lease.path.read_bytes())['schema'] == h.lr.RECONCILIATION_HOLD_SCHEMA
        assert h.lr.read_lane_occupancy(lease.path.parent).active_count == 1
        assert not h.slot.resource_released and not h.slot.control_acknowledged
    run(scenario())
    # Exact committed called helper never enters/releases the lease context.
    source = patched(tmp_path, 'remote_sub_exec.py', 'EXECUTOR_SOURCE.json')
    functions = {n.name:n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
    for name in ('_begin_lease_process','_begin_reserved_attended_under_lease','_retain_original_cleanup_hold'):
        node = functions[name]
        assert not any(isinstance(n,(ast.With,ast.AsyncWith)) for n in ast.walk(node))
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                       and n.func.attr in ('release','__exit__') for n in ast.walk(node))


def fixed_resources(h):
    return backend._FixedOwnerResources(preparation={k:v for k,v in h.inputs.preparation.items() if k!='result_schema'},
        physical=h.inputs.physical,binary_pin=h.inputs.binary_pin,
        routing_root_id=h.inputs.correlation['routing_root_id'],
        routing_parent_run_id=h.inputs.correlation['routing_parent_run_id'],
        active_dir=h.inputs.active_dir,
        credential_loader=h.inputs.credential_loader,credential_realm_owner=h.inputs.credential_realm_owner,
        credential_bindings_document=h.inputs.credential_bindings_document,
        credential_profiles_document=h.inputs.credential_profiles_document)


def test_single_assignment_constructor_waits_for_actual_control_command(harness,monkeypatch):
    h=harness
    composition=backend._SingleAssignmentComposition(fixed_resources(h))
    h.service.backend=composition
    observations=[]
    # Constructor timing fixture only. Wire validation and actual filesystem
    # preparation have separate tests; no production source proof is minted.
    projection={'capacity':{'registered_join':{'worker_id':h.inputs.physical.worker_id,
        'provider':h.inputs.physical.provider,'capacity_join':{'host_ref':h.inputs.physical.host_ref,
            'worker_source_config_digest':h.inputs.physical.worker_source_config_digest}}}}
    monkeypatch.setattr(backend.ControlStartAuthority,'owner_projection',lambda self,p:projection)
    def assigned(*args):
        observations.append(args)
        return (h.inputs.preparation,h.inputs.qualified_evidence,h.inputs.workspace_identity,
            h.inputs.provider_home_identity,h.inputs.log_path,h.inputs.receipt_path)
    monkeypatch.setattr(backend,'_observe_assigned_resources',assigned)
    async def scenario():
        assert composition._backend is None and not composition._attempted
        unissued=dataclasses.replace(authorize_control_command(h.command,peer=PeerCredentials(uid=450,gid=450)),_peer_verified=None)
        with pytest.raises(ValueError,match='control_start_authority_unavailable'):
            await composition.start_owned(h.world.original,authority=unissued)
        assert composition._backend is None and not h.inputs.log_path.exists() and not composition._attempted
        assert observations==[]
        response=await h.start()
        value=composition._backend
        assert response['result']['process_ref']['run_id']==h.spec.run_id
        assert value._slot.owner is h.world.owner and value._slot.lease is not None
        assert value._correlation['routing_root_id']==h.inputs.correlation['routing_root_id']
        assert value._correlation['routing_parent_run_id']==h.inputs.correlation['routing_parent_run_id']
        assert value._preparation['run_id']==h.spec.run_id
        assert value._inputs.physical is h.inputs.physical
        assert len(observations)==1
        assert len(h.calls)==1 and len(list(h.inputs.log_path.parent.glob('*.log')))==1
        with pytest.raises(bridge.BridgeProtocolError,match='EFFECT_UNKNOWN'):
            await h.start()
        assert len(h.calls)==1
    run(scenario())


def test_fixed_factory_requires_trusted_static_service_join(harness):
    h=harness
    resources=fixed_resources(h)
    policy=h.inputs.preparation['policy']
    config=dataclasses.replace(h.service.config,socket_path=Path(h.inputs.physical.socket_path),
        control_uid=policy.control_uid,workspace_root=policy.workspace_root,run_root=policy.run_root)
    assert type(backend.create_attended_backend(config,owner_resources=resources)) is backend._SingleAssignmentComposition
    with pytest.raises(backend.BackendNotConfiguredError):
        backend.create_attended_backend(dataclasses.replace(config,_trust=None),owner_resources=resources)
    with pytest.raises(backend.AttendedBackendRefused,match='fixed_service_resource_mismatch'):
        backend.create_attended_backend(dataclasses.replace(config,control_uid=policy.control_uid+1),owner_resources=resources)
    foreign=dataclasses.replace(resources,physical=dataclasses.replace(resources.physical,worker_id='other-worker'))
    with pytest.raises(backend.AttendedBackendRefused,match='fixed_service_resource_mismatch'):
        backend.create_attended_backend(config,owner_resources=foreign)
    for changed in ({'credential_loader':None},{'credential_realm_owner':None}):
        with pytest.raises(backend.BackendNotConfiguredError):
            backend.create_attended_backend(config,owner_resources=dataclasses.replace(resources,**changed))
    unsealed = dataclasses.replace(resources, preparation={**resources.preparation,
        'policy':dataclasses.replace(policy,require_assignment_seal=False)})
    with pytest.raises(backend.AttendedBackendRefused,match='fixed_service_resource_mismatch'):
        backend.create_attended_backend(config,owner_resources=unsealed)


@pytest.mark.parametrize('damage',['unsealed','worker'])
def test_canonical_credential_realm_owner_refuses_before_original_reservation(harness,monkeypatch,damage):
    h=harness
    args=h.credential_args
    ns=h.credential_source
    prepared=h.canonical_prepare(args['payload'],**args['preparation'])
    # The fixed compiler/owner observations remain explicit inert fixtures;
    # canonical current realm verification below is the actual committed source.
    import integrations.session_bridge.bound_launch_capture.fabric_reserved_attended_launch as compiler
    monkeypatch.setattr(compiler,'prepare_reserved_attended_launch',lambda *_a,**_k:prepared)
    monkeypatch.setattr(h.instance,'_check_original_owner',lambda _prepared:None)
    h.instance._preparation=args['preparation']
    h.instance._credentials={key:args[key] for key in (
        'credential_loader','credential_realm_owner','credential_bindings_document','credential_profiles_document')}
    h.instance._credentials['credential_physical_binding']=args['credential_physical_binding']
    h.executor._verify_reserved_realm_observation=ns['_verify_reserved_realm_observation']
    if damage=='unsealed':h.instance._credentials['credential_realm_owner']=object()
    else:
        from control_plane.codex_provider_realm import SubscriptionRealmOwner
        observed=args['credential_realm_owner'].observe()
        observed['worker_id']='another-original-worker'
        monkeypatch.setattr(SubscriptionRealmOwner,'observe',lambda self:dict(observed))
    async def scenario():
        with pytest.raises(ValueError,match='realm_(observation_unqualified|owner_required)'):
            authority=authorize_control_command(h.command,peer=PeerCredentials(uid=450,gid=450))
            await h.instance.start_owned(h.world.original,authority=authority)
    run(scenario())
    assert h.credential_calls==[] and not h.slot.claimed and not h.inputs.log_path.exists()
    assert h.acquisitions==h.calls==[]


@pytest.fixture
def cleanup_owner(actual_record,monkeypatch):
    from control_plane.worker_execution_contract import WorkerProcessRef, BinaryAttestation
    from test_executive_fabric_bridge_broker import start_result,start_payload
    example=actual_record
    row=json.loads(example['lane_receipt_bytes'])
    identity=example['expected_process_identity']
    fields=start_result(start_payload())['process_ref']
    fields.update(run_id=row['label'],
        pid=identity['pid'],pgid=identity['pgid'],session_id=identity['session_id'],
        boot_session_id=identity['boot_session_id'],process_start_identity=identity['process_start_identity'],
        started_at=row['started_at'],provider_session_id=None,effective_uid=os.geteuid(),effective_gid=os.getegid())
    fields['binary']=BinaryAttestation(**fields['binary'])
    ref=WorkerProcessRef(**fields)
    instance=backend.FabricAttendedBackend.__new__(backend.FabricAttendedBackend)
    instance._loop=None
    instance._context=dict(binding=example['expected_binding'],physical_binding_sha256=example['expected_physical_binding_sha256'])
    terminal=Path(row['owned_capture']['run_dir']).parent/'terminal.jsonl'
    holds=[]
    instance._inputs=SimpleNamespace(receipt_path=terminal,physical=SimpleNamespace(host_ref=identity['host_ref']))
    instance._spec=SimpleNamespace(run_id=row['label'])
    instance._slot=backend._ResourceSlot();instance._slot.claim(instance)
    instance._slot.owner=object();instance._slot.lease=SimpleNamespace(hold_for_reconciliation=holds.append)
    instance._slot.start=(SimpleNamespace(process_ref=ref),b'{}')
    instance._slot.collection=b'{"result":{"status":"SUCCEEDED"}}'
    observation=dict(finished_at=row['ended_at'],returncode=row['returncode'],timed_out=row['timed_out'],
                     cleanup=row['cleanup'],capture=row['owned_capture'])
    instance._retain_cleanup(observation)
    query=dict(schema_version='mastermind.executive_fabric_cleanup_query/v1',scope='collection',
        process_ref=backend._jsonable(ref),host_ref=identity['host_ref'],
        observed_after=backend.time.time(),readback_sha256=None)
    from control_plane import fabric_cleanup_transport as transport
    query['observed_after']=transport.stamp(row['started_at'])
    payload={**instance._context,'run_id':row['label'],'cleanup_query':query}
    return SimpleNamespace(instance=instance,terminal=terminal,row=row,payload=payload,holds=holds)


def test_actual_bound_terminal_transport_rereads_exact_original_bytes(cleanup_owner,monkeypatch):
    h=cleanup_owner
    calls=[]
    original=backend._read_original_file
    def read(*a,**kw):calls.append((a,kw));return original(*a,**kw)
    monkeypatch.setattr(backend,'_read_original_file',read)
    from control_plane import fabric_cleanup_transport as transport
    async def scenario():
        first=await h.instance.execute('status',h.payload)
        bridge.FabricBridgeBroker._operation_result(None,'status',first,h.payload)
        assert first['cleanup']['lane_receipt_utf8'].encode()==h.terminal.read_bytes()
        assert first['cleanup']['observed_at']==h.row['ended_at']
        selected=copy.deepcopy(h.payload)
        selected['cleanup_query']['readback_sha256']=transport.digest(first['cleanup'])
        second=await h.instance.execute('status',selected)
        bridge.FabricBridgeBroker._operation_result(None,'status',second,selected)
        assert first['cleanup']==second['cleanup'] and len(calls)==2
        assert all(kw['identity'] is not None for _,kw in calls)
        # Returned dictionaries cannot mutate retained bytes/time/identity.
        first['cleanup']['observed_at']='2099-01-01T00:00:00Z'
        again=await h.instance.execute('status',selected)
        assert again['cleanup']['observed_at']==h.row['ended_at']
    run(scenario())


@pytest.mark.parametrize('bad',['replace','symlink','bytes','floor','scope'])
def test_cleanup_readback_never_echoes_drift_or_restamps(cleanup_owner,bad):
    h=cleanup_owner
    async def scenario():
        await h.instance.execute('status',h.payload)
        if bad=='replace':
            raw=h.terminal.read_bytes();h.terminal.rename(h.terminal.with_suffix('.retained'));h.terminal.write_bytes(raw)
        elif bad=='symlink':
            h.terminal.rename(h.terminal.with_suffix('.retained'));h.terminal.symlink_to(h.terminal.with_suffix('.retained'))
        elif bad=='bytes':h.terminal.write_bytes(h.terminal.read_bytes()+b' ')
        elif bad=='floor':h.payload['cleanup_query']['observed_after']=backend.time.time()+1
        elif bad=='scope':h.payload['cleanup_query']['scope']='restart_absence'
        with pytest.raises((ValueError,OSError)):
            await h.instance.execute('status',h.payload)
        assert not h.instance._slot.resource_released
        if bad!='scope':assert h.holds==['original_cleanup_readback_unconfirmed']
    run(scenario())


@pytest.mark.parametrize('harness', [True], indirect=True)
def test_interrupted_actual_release_hold_does_not_relock_or_free_slot(settled_assignment, monkeypatch):
    h, start, _ = settled_assignment
    async def scenario():
        ack = await committed_assignment(h, start)
        lease = h.slot.lease
        parent_inode = lease.path.parent.stat().st_ino
        original_fsync, original_flock = h.lr.os.fsync, h.lr.fcntl.flock
        locks = []
        def fsync(fd):
            if os.fstat(fd).st_ino == parent_inode:
                raise OSError('inert original release durability unknown')
            return original_fsync(fd)
        def flock(fd, operation):
            if operation & h.lr.fcntl.LOCK_EX:
                locks.append(fd)
                assert len(locks) == 1, 'holding the interrupted original release must not reacquire its lock'
            return original_flock(fd, operation)
        monkeypatch.setattr(h.lr.os, 'fsync', fsync)
        monkeypatch.setattr(h.lr.fcntl, 'flock', flock)
        with pytest.raises(bridge.BridgeProtocolError, match='EFFECT_UNKNOWN'):
            await h.service.execute(h.request('assignment-seal-finalize', ack),
                                    peer=PeerCredentials(uid=450,gid=450))
        assert len(locks) == 1 and lease._assignment_release_lock_fd is not None
        assert h.slot.control_acknowledged and h.slot.reconciliation_required
        assert not h.slot.resource_released and h.slot.release_receipt is None
        assert not lease.path.exists()  # no recreation or restamped success
        with pytest.raises(backend.AttendedBackendRefused,match='controller_slot_occupied'):
            await backend.FabricAttendedBackend(h.inputs).execute('status',h.request('status')['payload'])
    run(scenario())


def test_nonempty_validation_profile_refuses_before_original_effects(harness):
    h=harness
    command=copy.deepcopy(h.command)
    command['validation_commands']=[['inert-validator']]
    command['control_start']['pin_identity_sha256']=launch_identity(command)
    authority=authorize_control_command(command,peer=PeerCredentials(uid=450,gid=450))
    forwarded={k:v for k,v in command.items() if k!='control_start'}
    forwarded['start_request_sha256']=bridge.start_request_sha256(forwarded)
    composition=backend._SingleAssignmentComposition(fixed_resources(h))
    async def scenario():
        with pytest.raises(backend.AttendedBackendRefused,match='finite_profile_requires_empty_validations'):
            await composition.start_owned(forwarded,authority=authority)
    run(scenario())
    assert not h.inputs.log_path.exists() and composition._backend is None
    assert h.calls==h.acquisitions==[]


def test_supervisor_empty_validation_joins_real_broker_backend_terminal_reads(
        cleanup_owner, tmp_path, monkeypatch):
    """Actual consumer/transport/file semantics; Runtime enrollment is inert."""
    from control_plane.executive_fabric_adapter import AttendedFabricWorkerAdapter
    from control_plane.executive_supervisor import ExecutiveSupervisor, CleanupPolicy
    from tests.test_executive_supervisor import _runtime_and_job
    h=cleanup_owner
    instance=h.instance
    ref=instance._slot.start[0].process_ref
    binding=instance._context['binding']
    runtime, _job_id, _workspace=_runtime_and_job(tmp_path/'runtime')
    adapter=AttendedFabricWorkerAdapter(runtime,lambda *_args:None)
    physical=SimpleNamespace(digest=instance._context['physical_binding_sha256'],
        host_ref=instance._inputs.physical.host_ref,worker_uid=ref.effective_uid,
        worker_gid=ref.effective_gid)
    attempt=SimpleNamespace(attempt_id=ref.run_id,job_id=binding['job_id'],
        effective_grant_digest=binding['effective_grant_digest'],pid=ref.pid,pgid=ref.pgid,
        process_start_identity=ref.process_start_identity,boot_id=ref.boot_session_id)
    # This test supplies an inert original claim; it does not attest enrollment.
    monkeypatch.setattr(adapter,'_validate_lease',lambda _run_id:attempt)
    monkeypatch.setattr(adapter,'_resolve',lambda *_a,**_k:(attempt,physical,{'binding':binding}))
    monkeypatch.setattr(adapter,'_pin_matches',lambda *_a:None)
    config=bridge.BridgeConfig(schema_version=bridge.CONFIG_SCHEMA_VERSION,
        adapter_id='attended-fabric',bridge_uid=os.geteuid(),control_uid=450,
        launchd_socket_name='FabricBridge',socket_path=Path('/var/run/inert.sock'),
        workspace_root=tmp_path,run_root=tmp_path,max_request_bytes=65536,
        max_response_bytes=262144,request_timeout_seconds=10,validation_commands=(),
        _trust=bridge._TRUSTED_CONFIG)
    service=bridge.FabricBridgeBroker(config,instance)
    queries=[]
    async def request(operation,payload,**_options):
        queries.append(copy.deepcopy(payload['cleanup_query']))
        response=await service.execute(dict(schema_version=bridge.BROKER_REQUEST_SCHEMA_VERSION,
            request_id='inert-cleanup',operation=operation,payload=payload),
            peer=PeerCredentials(uid=450,gid=450))
        return response['result']
    adapter._refs[ref.run_id]=ref
    adapter._bound[ref.run_id]=(SimpleNamespace(request=request),{'binding':binding},physical,object())
    supervisor=ExecutiveSupervisor(runtime,adapter,cleanup_policy=CleanupPolicy.FABRIC_PROCESS_GROUP,
        require_complete_launch_attestation=True,runs_root=tmp_path/'consumer-runs')
    job=SimpleNamespace(root_job_id=binding['root_id'],validation_commands=[])
    monkeypatch.setattr(supervisor,'_job',lambda _job_id:job)
    active=SimpleNamespace(lease=SimpleNamespace(attempt=attempt),process_ref=ref,
        launch_spec=SimpleNamespace(run_dir=tmp_path/'consumer-run'),
        effective_grant={'validation_argv':[]})
    reads=[]
    original_read=backend._read_original_file
    def read(*args,**kwargs):
        reads.append((args,kwargs))
        return original_read(*args,**kwargs)
    monkeypatch.setattr(backend,'_read_original_file',read)
    async def scenario():
        receipts,path,error=await supervisor._run_supervisor_validations(active,job)
        persisted=json.loads(path.read_text())
        assert receipts==() and error is None and persisted['commands']==[]
        assert 'fabric_cleanup' not in persisted and 'uid_sweep' not in persisted
        package=supervisor._active_terminal_uid_sweep(active)
        assert package['operation']=='terminal'
        assert package['observed_at']==h.row['ended_at']
        assert package['lane_receipt_utf8'].encode()==h.terminal.read_bytes()
    run(scenario())
    assert len(reads)==2 and all(item[1]['identity'] is not None for item in reads)
    assert [q['scope'] for q in queries]==['terminal','terminal']
    assert queries[0]['readback_sha256'] is None and queries[1]['readback_sha256'] is not None
    assert h.holds==[]


@pytest.mark.parametrize('field',['realm_config_sha256','source_config_sha256'])
def test_assignment_observer_uses_actual_current_realm_contract(harness,monkeypatch,field):
    from control_plane import broker_assignment_seal, claude_subscription_worker
    h=harness
    resources=fixed_resources(h)
    monkeypatch.setattr(broker_assignment_seal,'require_worker_principal',lambda policy:None)
    monkeypatch.setattr(backend.SubscriptionRealmOwner,'observe',lambda self:{
        'worker_id':resources.physical.worker_id,field:resources.physical.worker_source_config_digest})
    calls=[]
    class ReachedActualAssignment(Exception):pass
    def assigned(*args,**kwargs):
        calls.append(True)
        raise ReachedActualAssignment()
    monkeypatch.setattr(claude_subscription_worker,'prepare_assigned_subscription_files',assigned)
    expected=ReachedActualAssignment if field=='realm_config_sha256' else backend.AttendedBackendRefused
    with pytest.raises(expected):
        backend._observe_assigned_resources(resources,h.world.original,{})
    assert calls==([True] if field=='realm_config_sha256' else [])
