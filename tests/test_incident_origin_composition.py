"""Dormant composition with real imported contracts and inert native seams.

Anonymous pipes/socketpairs exercise parent/client/host together. No native
probe, UID drop, launchctl, provider, DB or production path is executed. The
original synthetic-world candidate and all seven old REDs remain immutable
in the original owner's evidence; these tests replace package-substitution
fixtures with actual bf6 dependencies.
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
import socket
import threading
import time
from types import SimpleNamespace as S
from unittest.mock import Mock

import pytest
from control_plane import executive_incident_origin as o
from control_plane import executive_incident_forward_host as h
from scripts import executive_os_incident_foreground_client as c
from control_plane import executive_privileged_broker as broker
from control_plane.executive_privileged_client import validate_forward_recovery_response
from ops.executive_os import provider_incident_forward as f
from tests.test_provider_incident_forward import forward_args, forward_policy

BOOT = '11111111-2222-3333-4444-555555555555'
COMMIT = 'a' * 40
ORIGIN = o.Instance(10, 110, 1)
BROKER = o.Instance(20, 220, 2)
CHILD = o.Instance(30, 330, 3)
SOURCE = {'release_sha': COMMIT, 'manifest_sha256': 'b' * 64}


def budget(seconds=3):
    return o.release._Budget(time.monotonic_ns() + int(seconds * 1e9))


def release(state='RUNNING', boot=BOOT, commit=COMMIT):
    from tests.incident_release_fixtures import make_observation
    return make_observation(source=dict(SOURCE, release_sha=commit), boot=boot,
                            states={'broker': state}, broker=BROKER)


def terminal(raw):
    request, digest = f.validate_forward_request(raw)
    value = {'schema': broker.RECEIPT_SCHEMA, 'request_id': request.request_id,
        'request_sha256': digest, 'action': request.action,
        'effect_class': broker.ACTION_EFFECT_CLASS[request.action],
        'started_at': '2026-10-14T00:00:00Z', 'finished_at': '2026-10-14T00:00:01Z',
        'outcome': 'SUCCEEDED', 'exit_code': 0, 'release_sha': COMMIT, 'broker_version': 'test'}
    for stream in ('stdout', 'stderr'):
        value.update({stream+'_bytes': 0, stream+'_sha256': hashlib.sha256(b'').hexdigest(), stream+'_excerpt': ''})
    return broker._wire_success(value, replayed=False)


@pytest.fixture
def world(monkeypatch):
    # Patch native/effect leaves, never the package, protocol or core types.
    handles = []
    def acquire(*, deadline_monotonic_ns):
        v = S(budget=o.release._Budget(deadline_monotonic_ns), closed=False)
        handles.append(v)
        return v
    def close(v):
        assert not v.closed
        v.closed = True
    anchor = o.namespace._SocketNode((1,2,3))
    monkeypatch.setattr(o.namespace, '_acquire_namespace', acquire)
    monkeypatch.setattr(o.namespace, '_release_namespace', Mock(side_effect=close))
    monkeypatch.setattr(o.namespace, '_recheck_namespace', Mock())
    monkeypatch.setattr(o.namespace, '_require_socket_absent', Mock())
    monkeypatch.setattr(o.namespace, '_observe_socket_node', Mock(return_value=anchor))
    monkeypatch.setattr(o.namespace, '_require_same_socket', Mock())
    monkeypatch.setattr(o.incident_release, '_observe_incident_release', Mock(return_value=release()))
    monkeypatch.setattr(o.release, '_boot', Mock(return_value=BOOT))
    monkeypatch.setattr(o, '_observe_running_owner_set', Mock(return_value=S(
        origin_instance=ORIGIN, broker_instance=BROKER, boot_id=BOOT)))
    native = S(unique_id=CHILD.unique_id, pidversion=CHILD.pidversion,
               parent_unique_id=ORIGIN.unique_id, parent_pidversion=ORIGIN.pidversion)
    monkeypatch.setattr(o, '_observe_native_instance', Mock(return_value=native))
    monkeypatch.setattr(h, '_observe_native_instance', Mock(return_value=native))
    monkeypatch.setattr(c, '_observe_process_instance', Mock(return_value=native))
    monkeypatch.setattr(c, 'capture_peer_identity', Mock(return_value=S(euid=0,pid=1)))
    monkeypatch.setattr(c, '_current_capture', Mock())
    monkeypatch.setattr(h, 'capture_peer_identity', Mock(return_value=S(euid=450,pid=CHILD.pid,pidversion=CHILD.pidversion)))
    monkeypatch.setattr(h, '_current_capture', Mock())
    monkeypatch.setattr(f, 'PRODUCTION_FORWARD_RECOVERY_POLICY', forward_policy())
    monkeypatch.setattr(f.recovery, 'current_executive_source', Mock(return_value=SOURCE))
    return S(handles=handles, acquire=acquire, anchor=anchor)


def interval(world, seconds=3):
    b = budget(seconds)
    v = o._OriginInterval(boot_id=BOOT, release_commit=COMMIT, cohort_content_sha256=release().cohort_content_sha256, observer=ORIGIN,
        deadline_monotonic_ns=b.endpoint, handles=world.acquire(deadline_monotonic_ns=b.endpoint),
        started_monotonic_ns=b.started, completed_monotonic_ns=b.last)
    v.phase='OBSERVATION_ONLY'; v.bootstrapped=True; v._socket_anchor=world.anchor
    return v


class Connected:
    def __init__(self, sock): self.sock=sock; self.submissions=0
    def connect(self, path): assert path == o.namespace._CANONICAL
    def sendall(self, data): self.submissions += 1; self.sock.sendall(data)
    def __getattr__(self, name): return getattr(self.sock,name)


def chain(monkeypatch, world, *, broken=None, core=None):
    """Real pipes and accepted socket; broker fixture executes the real ABC stages."""
    server, client = socket.socketpair()
    conn = Connected(client)
    monkeypatch.setattr(c, 'socket', S(socket=lambda *a:conn, AF_UNIX=socket.AF_UNIX,
        SOCK_STREAM=socket.SOCK_STREAM, timeout=socket.timeout))
    owned=[]
    def pipe():
        rd,wr=os.pipe(); r=os.fdopen(rd,'rb',buffering=0); w=os.fdopen(wr,'wb',buffering=0)
        owned.extend((r,w)); return r,w
    child_in,parent_out=pipe(); parent_in,child_out=pipe(); parent_err,child_err=pipe()
    origin=interval(world)
    raw=forward_args(); request,digest=f.validate_forward_request(raw)
    errors=[]; stage_results=[]
    def child_run():
        try: c._run_origin_client(stdin=child_in,stdout=child_out)
        except BaseException as e: errors.append(e)
        finally: child_out.close(); child_err.close()
    ct=threading.Thread(target=child_run)
    process=S(pid=CHILD.pid,stdin=parent_out,stdout=parent_in,stderr=parent_err)
    def wait(timeout):
        ct.join(timeout)
        if ct.is_alive(): raise TimeoutError('fixture child not settled')
        if broken=='settlement': raise RuntimeError('settlement unproven')
        return 0 if not errors else 3
    process.wait=wait; process.kill=lambda:None
    child=o._OriginChild(process,digest,request,origin);child.instance=CHILD;origin.child=child
    if broken=='partial-send':
        def uncertain(data):conn.submissions+=1;raise OSError('lost write outcome')
        conn.sendall=uncertain
    if broken=='cleanup':
        monkeypatch.setattr(o.namespace,'_release_namespace',Mock(side_effect=RuntimeError('cleanup failed')))
    def server_run():
        try:
            server.settimeout(3)
            incoming=h._read_frame(server,budget())
            assert incoming==raw
            if core is not None:
                core.config=dataclasses.replace(core.config,allowed_peer_uids=(450,))
                core._forward_host_guard=h._make_forward_host_context
                receipt,replayed=core._handle_forward_outcome(incoming,peer_uid=450,connection=server)
                h._send_frame(server,broker._wire_success(receipt,replayed=replayed),budget())
                return
            if broken=='negative':
                h._send_frame(server,broker._wire_error('unavailable','fixture'),budget());return
            binding=f._ForwardGuardRequest(f.ORIGINAL_ISSUER_REQUEST_ID,f.ORIGINAL_REQUEST_SHA256,
                f.ORIGINAL_MARKER_SHA256,f.ORIGINAL_RELEASE_SHA,f.SUCCESSOR_REQUEST_ID,digest,
                tuple(sorted(f.validate_forward_policy(f.PRODUCTION_FORWARD_RECOVERY_POLICY).items())),
                tuple(sorted(SOURCE.items())),450,server,object(),budget().endpoint)
            with h._make_forward_host_context(binding) as context:
                for i,stage in enumerate(o._STAGES):
                    stage_results.append(context.revalidate(binding,stage=stage,
                        reservation_sha256=None if i<2 else 'a'*64))
            h._send_frame(server,terminal(raw),budget())
        except BaseException as e:errors.append(e)
        finally:server.close()
    st=threading.Thread(target=server_run);st.start();ct.start()
    try: result=o._serve_origin_witnesses(origin,child)
    finally:
        client.close();server.close()
        for stream in owned:
            try:stream.close()
            except OSError:pass
        ct.join(4);st.join(4)
    assert not ct.is_alive() and not st.is_alive()
    return result,errors,stage_results,conn,origin


def test_actual_client_precheck_and_seven_challenges_close_through_parent(world,monkeypatch):
    result,errors,stages,conn,origin=chain(monkeypatch,world)
    assert not errors, errors
    assert result.classification=='SUCCEEDED', result
    assert len(stages)==result.exchanges==7 and all(type(v)is f._ForwardHostObservation for v in stages)
    assert conn.submissions==1 and origin.closed
    assert all(x.closed for x in world.handles)
    assert o.namespace._require_same_socket.call_count>=17


@pytest.mark.parametrize('broken',['partial-send','negative','settlement','cleanup'])
def test_uncertain_or_negative_paths_never_succeed(world,monkeypatch,broken):
    result,_,_,conn,_=chain(monkeypatch,world,broken=broken)
    assert conn.submissions==1
    assert result.classification=='UNKNOWN_RETAINED'


def test_coalesced_parent_frames_are_consumed_before_another_read():
    stream=io.BytesIO(b'{"first":1}\n{"second":2}\n'); pending=c._StreamBuffer()
    assert c._read_stream_frame(stream,pending)=={'first':1}
    assert c._read_stream_frame(stream,pending)=={'second':2}


@pytest.mark.parametrize('raw',[b'{"v":1,"v":2}', b'{"a":{"x":1,"x":2}}',b'{"n":NaN}',b'[]',b'\xff',b'{'])
def test_malformed_or_duplicate_frames_refuse(raw):
    with pytest.raises(ValueError):c._parse_frame_line(raw,code_prefix='TEST')


@pytest.mark.parametrize('bad',[True,None,0,-1,2**63,'3'])
def test_invalid_endpoints_refuse(bad):
    with pytest.raises(ValueError):o._tighten(budget(),bad)


def test_endpoint_tightens_without_resetting_sticky_budget():
    b=budget();first=b.endpoint;shorter=first-1_000_000
    assert o._tighten(b,shorter)==shorter
    assert o._tighten(b,first)==shorter
    b.violation=o.release.ReleaseObservationError('retained')
    with pytest.raises(ValueError,match='retained'):o._tighten(b,first)


def test_open_pipe_small_frame_does_not_wait_for4096bytes():
    rd,wr=os.pipe()
    try:
        os.write(wr,b'{"ok":true}\n')
        with os.fdopen(rd,'rb',buffering=0) as stream:
            assert c._read_stream_frame(stream,budget=budget(.5))=={'ok':True}
    finally:os.close(wr)


def test_open_empty_pipe_hits_deadline():
    rd,wr=os.pipe()
    try:
        with os.fdopen(rd,'rb',buffering=0) as stream:
            with pytest.raises(ValueError):c._read_stream_frame(stream,budget=budget(.02))
    finally:os.close(wr)


def test_full_pipe_write_hits_deadline_without_flush():
    rd,wr=os.pipe()
    try:
        os.set_blocking(wr,False)
        while True:
            try:os.write(wr,b'x'*4096)
            except BlockingIOError:break
        with os.fdopen(wr,'wb',buffering=0) as stream:
            with pytest.raises(ValueError):o._stream_send(stream,{'v':1},budget(.02))
    finally:os.close(rd)


@pytest.mark.parametrize('raw',[b'{',b'x'*65536])
def test_partial_and_oversized_frames_refuse(raw):
    with pytest.raises(ValueError):c._read_stream_frame(io.BytesIO(raw))


@pytest.mark.parametrize('field,value',[('v',True),('v',1),('v',3),('kind','wrong'),('extra',None)])
def test_closed_frame_keys_and_types(field,value):
    frame={'kind':'sent','v':2,'forward_request_sha256':'f'*64};frame[field]=value
    with pytest.raises(ValueError):o._shape(frame,{'kind','v','forward_request_sha256'},'sent')


@pytest.mark.parametrize('field,value',[('pid',True),('pid',0),('pid',2**31),('unique_id',0),('unique_id',True),('unique_id',2**64),('pidversion',0),('pidversion',2**31)])
def test_native_instance_fields_strict(field,value):
    record=o._instance_record(ORIGIN);record[field]=value
    with pytest.raises(ValueError):c._instance_fields(record)


@pytest.mark.parametrize('field,value',[('original_request_sha256','1'*64),('original_marker_sha256','1'*64),('original_release_sha','1'*40),('successor_request_id','other')])
def test_wrong_canonical_identity_refuses(field,value):
    with pytest.raises(f.ForwardRecoveryError):f.validate_forward_request(forward_args(**{field:value}))


def test_production_remains_dormant():
    assert f.PRODUCTION_FORWARD_RECOVERY_POLICY is None
    assert 'executive_incident_forward_host' not in Path('scripts/executive_os_privileged_broker.py').read_text()


from pathlib import Path


@pytest.mark.parametrize('failure',['enable','bootstrap','readback','namespace'])
def test_bootstrap_attempt_is_burned_and_not_retried(world,monkeypatch,failure):
    v=interval(world);v.phase='EXCLUSIVE';v.bootstrapped=False
    monkeypatch.setattr(o.incident_release,'_observe_incident_release',Mock(return_value=release('UNLOADED')))
    calls=[]
    def command(argv,b):
        calls.append(argv)
        if (failure=='enable' and argv==o._ENABLE_ARGV) or (failure=='bootstrap' and argv==o._BOOTSTRAP_ARGV):return 1,b'',b'failed'
        return 0,b'loaded',b''
    monkeypatch.setattr(o,'_run_origin_command',command)
    monkeypatch.setattr(o,'_broker_load_state',Mock(side_effect=RuntimeError('readback') if failure=='readback' else None))
    if failure=='namespace':monkeypatch.setattr(o.namespace,'_observe_socket_node',Mock(side_effect=RuntimeError('node')))
    with pytest.raises(Exception):v.bootstrap_once()
    before=list(calls)
    with pytest.raises(ValueError):v.bootstrap_once()
    assert calls==before and v.bootstrap_attempted


def test_bootstrap_enable_then_bootstrap_and_retains_creation_anchor(world,monkeypatch):
    v=interval(world);v.phase='EXCLUSIVE';v.bootstrapped=False
    monkeypatch.setattr(o.incident_release,'_observe_incident_release',Mock(return_value=release('UNLOADED')))
    effect=Mock(return_value=(0,b'',b''));monkeypatch.setattr(o,'_run_origin_command',effect)
    monkeypatch.setattr(o,'_broker_load_state',Mock(return_value='LOADED'))
    v.bootstrap_once()
    assert [a.args[0] for a in effect.call_args_list]==[o._ENABLE_ARGV,o._BOOTSTRAP_ARGV]
    assert v._socket_anchor is world.anchor and v.phase=='OBSERVATION_ONLY'


@pytest.mark.parametrize('bad',['source','boot','socket','namespace'])
def test_original_anchors_refuse_drift(world,monkeypatch,bad):
    v=interval(world)
    if bad in ('source','boot'):
        monkeypatch.setattr(o.incident_release,'_observe_incident_release',Mock(return_value=release(
            commit='d'*40 if bad=='source' else COMMIT,boot='different' if bad=='boot' else BOOT)))
    else:
        seam='_require_same_socket' if bad=='socket' else '_recheck_namespace'
        monkeypatch.setattr(o.namespace,seam,Mock(side_effect=RuntimeError('drift')))
    with pytest.raises(Exception):o._parent_observation(v,'before_grant',4,v._budget())


def test_cleanup_closes_once_and_preserves_uncertainty(world,monkeypatch):
    v=interval(world)
    monkeypatch.setattr(o.namespace,'_release_namespace',Mock(side_effect=RuntimeError('close')))
    with pytest.raises(RuntimeError):v.close_once()
    with pytest.raises(ValueError):v.close_once()
    assert o.namespace._release_namespace.call_count==1 and v.closed


def test_helper_mode_matches_manifest_bytes(world,monkeypatch):
    v=interval(world); raw=b'fixed source'
    row={'path':o._ORIGIN_CLIENT_RELATIVE,'type':'file','mode':0o644,'uid':0,'gid':0,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    read=Mock(side_effect=[(raw,None),(o._canonical({'commit_sha':COMMIT,'entries':[row]}),None)])
    monkeypatch.setattr(o.peer,'_read_trusted_bytes',read)
    assert o._sealed_client_entrypoint(v._budget(),v).endswith(o._ORIGIN_CLIENT_RELATIVE)
    assert read.call_args_list[0].kwargs['expected_mode']==0o644


@pytest.mark.parametrize('bad',['sha256','mode','uid','commit','duplicate'])
def test_helper_manifest_drift_refuses(world,monkeypatch,bad):
    v=interval(world);raw=b'fixed source'
    row={'path':o._ORIGIN_CLIENT_RELATIVE,'type':'file','mode':0o644,'uid':0,'gid':0,'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    doc={'commit_sha':COMMIT,'entries':[row]}
    if bad=='commit':doc['commit_sha']='d'*40
    elif bad=='duplicate':doc['entries'].append(dict(row))
    else:row[bad]='bad'
    monkeypatch.setattr(o.peer,'_read_trusted_bytes',Mock(side_effect=[(raw,None),(o._canonical(doc),None)]))
    with pytest.raises(ValueError):o._sealed_client_entrypoint(v._budget(),v)


def test_response_validator_binds_real_request_digest_and_release():
    raw=forward_args();response=terminal(raw)
    assert validate_forward_recovery_response(response,raw,expected_release_sha=COMMIT)['ok']
    for field,value in [('request_sha256','f'*64),('release_sha','f'*40),('request_id','other')]:
        altered=json.loads(json.dumps(response));altered['receipt'][field]=value
        with pytest.raises(RuntimeError):validate_forward_recovery_response(altered,raw,expected_release_sha=COMMIT)


@pytest.mark.parametrize('bad',['extra-runtime','missing-row','foreign-observer','boot','broker','collapsed','row-drift'])
def test_real_running_owner_set_keeps_complete_census_and_refuses_ambiguity(monkeypatch,bad):
    # Exercise the actual census consumer, not a substituted owner-set function.
    b=budget(); snap=release()
    matching=[ORIGIN,BROKER]
    rows=[S(instance=ORIGIN),S(instance=BROKER),S(instance=o.Instance(99,999,9))]
    observer=ORIGIN
    if bad=='extra-runtime':matching.append(rows[2].instance)
    if bad=='missing-row':rows=rows[1:]
    if bad=='foreign-observer':observer=rows[2].instance
    if bad=='boot':snap=release(boot='wrong')
    if bad=='broker':snap=release('UNLOADED')
    if bad=='row-drift':rows[0]=S(instance=o.Instance(10,111,1))
    monkeypatch.setattr(o.host,'_instance',Mock(return_value=BROKER))
    monkeypatch.setattr(o.host,'_root_census',Mock(return_value=S(observer=observer,rows=tuple(rows),matching_runtime_instances=tuple(matching))))
    monkeypatch.setattr(o.release,'_boot',Mock(return_value=BOOT))
    with pytest.raises(ValueError):o._observe_running_owner_set(b,origin_instance=BROKER if bad=='collapsed' else ORIGIN,broker_observation=snap)


def test_real_running_owner_set_retains_nonmatching_rows(monkeypatch):
    rows=(S(instance=ORIGIN),S(instance=BROKER),S(instance=o.Instance(99,999,9)))
    monkeypatch.setattr(o.host,'_instance',Mock(return_value=BROKER))
    monkeypatch.setattr(o.host,'_root_census',Mock(return_value=S(observer=ORIGIN,rows=rows,matching_runtime_instances=(ORIGIN,BROKER))))
    monkeypatch.setattr(o.release,'_boot',Mock(return_value=BOOT))
    assert o._observe_running_owner_set(budget(),origin_instance=ORIGIN,broker_observation=release()).rows==rows


@pytest.mark.parametrize('bad',['uid','token','R','source-duplicate','policy-duplicate','deadline','foreign-type'])
def test_factory_rejects_malformed_or_foreign_binding(bad):
    server,client=socket.socketpair()
    try:
        binding=f._ForwardGuardRequest(f.ORIGINAL_ISSUER_REQUEST_ID,f.ORIGINAL_REQUEST_SHA256,f.ORIGINAL_MARKER_SHA256,
            f.ORIGINAL_RELEASE_SHA,f.SUCCESSOR_REQUEST_ID,'f'*64,(('policy','value'),),(('release_sha',COMMIT),),450,server,object(),budget().endpoint)
        changes={'uid':{'peer_uid':501},'token':{'invocation_token':'fake'},'R':{'original_release_sha':'1'*40},
            'source-duplicate':{'sealed_source':(('release_sha',COMMIT),('release_sha',COMMIT))},
            'policy-duplicate':{'policy_binding':(('policy','value'),('policy','value'))},'deadline':{'deadline_monotonic_ns':True}}
        value=S(**vars(binding)) if bad=='foreign-type' else dataclasses.replace(binding,**changes[bad])
        with pytest.raises(ValueError):h._make_forward_host_context(value)
    finally:server.close();client.close()


@pytest.mark.parametrize('bad',['replay','skip','unknown','premature-digest','missing-digest','wrong-request'])
def test_stage_order_failure_is_sticky(world,monkeypatch,bad):
    server,client=socket.socketpair()
    try:
        binding=f._ForwardGuardRequest(f.ORIGINAL_ISSUER_REQUEST_ID,f.ORIGINAL_REQUEST_SHA256,f.ORIGINAL_MARKER_SHA256,
            f.ORIGINAL_RELEASE_SHA,f.SUCCESSOR_REQUEST_ID,'f'*64,(('policy','value'),),(('release_sha',COMMIT),),450,server,object(),budget().endpoint)
        ctx=h._make_forward_host_context(binding)
        # A narrow state-machine unit fixture; full acquisition is tested by chain.
        ctx._entered=True;ctx._captured=S(euid=450,pid=30)
        stage='before_preflight';reservation=None;req=binding
        if bad=='replay':ctx._stage_index=7
        if bad=='skip':stage='before_reservation'
        if bad=='unknown':stage='eighth'
        if bad=='premature-digest':reservation='a'*64
        if bad=='missing-digest':ctx._stage_index=2;stage='before_reservation_attempt'
        if bad=='wrong-request':req=dataclasses.replace(binding)
        with pytest.raises(ValueError):ctx.revalidate(req,stage=stage,reservation_sha256=reservation)
        with pytest.raises(ValueError,match='CONTEXT_FAILED'):ctx.revalidate(binding,stage='before_preflight',reservation_sha256=None)
    finally:server.close();client.close()


def test_fixed_spawn_owns_uid_drop_and_isolated_args(world,monkeypatch):
    v=interval(world);process=S(pid=CHILD.pid,stdin=io.BytesIO(),stdout=io.BytesIO(),stderr=io.BytesIO())
    popen=Mock(return_value=process)
    monkeypatch.setattr(o,'_sealed_client_entrypoint',Mock(return_value='/fixed/entry.py'))
    monkeypatch.setattr(o.subprocess,'Popen',popen)
    child=o._spawn_origin_client(v,forward_args())
    assert child.instance==CHILD and child.origin is v and v.child is child
    call=popen.call_args
    # Independently bind the observed spawn to the qualified signed main image,
    # not the pythonw launcher which performs another exec after Popen returns.
    assert call.args[0]==(o.peer._PYTHON_MAIN_EXECUTABLE,'-I','-S','-B','/fixed/entry.py')
    assert call.args[0][0] != o.peer._PYTHON_LAUNCHER
    assert 'executable' not in call.kwargs
    assert call.kwargs['user']==call.kwargs['group']==450
    assert call.kwargs['extra_groups']==[] and call.kwargs['close_fds'] and call.kwargs['bufsize']==0
    assert call.kwargs['env']==o._CHILD_ENVIRONMENT
    with pytest.raises(ValueError):o._spawn_origin_client(v,forward_args())
    assert popen.call_count==1


@pytest.mark.parametrize('field,value',[('parent_unique_id',111),('parent_pidversion',None),('unique_id',0),('pidversion',True)])
def test_native_child_join_is_not_a_pid_label(world,field,value):
    v=interval(world);ch=o._OriginChild(S(pid=CHILD.pid),'f'*64,None,v)
    record=S(unique_id=CHILD.unique_id,pidversion=CHILD.pidversion,parent_unique_id=ORIGIN.unique_id,parent_pidversion=ORIGIN.pidversion)
    setattr(record,field,value)
    with pytest.raises(ValueError):o._require_child_parent(ch,record,v,v._budget())


# Existing isolated durable-core fixture: all roots are pytest temporary paths.
from tests.test_provider_incident_forward import forward_env  # noqa: F401
from tests.test_provider_incident_recovery import recovery, state, custody_root  # noqa: F401


def test_real_core_uses_connected_context_through_durable_settlement(world, forward_env, monkeypatch):
    result,errors,_,conn,origin=chain(monkeypatch,world,core=forward_env.fwd_broker)
    assert not errors, errors
    assert result.classification=='SUCCEEDED', result
    assert result.exchanges==7 and conn.submissions==1 and origin.closed
    assert f.reservation_path(forward_env.fwd_broker.receipt_root).exists()
    assert f.terminal_path(forward_env.fwd_broker.receipt_root).exists()
    assert not f.guard_path(forward_env.fwd_broker.receipt_root).exists()


def test_parent_eof_interrupts_silent_broker_without_deadline_wait():
    a,b=socket.socketpair();rd,wr=os.pipe();os.close(wr)
    try:
        with os.fdopen(rd,'rb',buffering=0) as parent:
            start=time.monotonic()
            with pytest.raises(c.OriginClientError,match='PARENT_EOF'):
                c._read_socket_frame(a,budget(3).endpoint,c._StreamBuffer(),parent)
            assert time.monotonic()-start < 1
    finally:a.close();b.close()


def test_split_frame_from_open_pipe_progresses():
    rd,wr=os.pipe()
    def writer():
        try:
            os.write(wr,b'{"v":');os.write(wr,b'1}\n')
        finally:os.close(wr)
    t=threading.Thread(target=writer);t.start()
    with os.fdopen(rd,'rb',buffering=0) as reader:
        assert c._read_stream_frame(reader,budget=budget())=={'v':1}
    t.join(1);assert not t.is_alive()


def test_stderr_overflow_drains_concurrently_without_fixture_deadlock(world):
    v=interval(world)
    rd,wr=os.pipe();er,ew=os.pipe()
    stdout=os.fdopen(rd,'rb',buffering=0);stderr=os.fdopen(er,'rb',buffering=0)
    # Keep stdout open and silent while stderr fills: both channels must progress.
    def writer():
        try:
            view=memoryview(b'x'*70000)
            while view:
                count=os.write(ew,view);view=view[count:]
        except BrokenPipeError:pass
        finally:os.close(ew);os.close(wr)
    t=threading.Thread(target=writer);t.start()
    def wait(timeout):t.join(timeout);return 0 if not t.is_alive() else None
    request,digest=f.validate_forward_request(forward_args())
    proc=S(pid=CHILD.pid,stdin=io.BytesIO(),stdout=stdout,stderr=stderr,wait=wait,kill=lambda:None)
    child=o._OriginChild(proc,digest,request,v);child.instance=CHILD;v.child=child
    result=o._serve_origin_witnesses(v,child)
    t.join(1)
    assert not t.is_alive()
    assert result.refusal=='ORIGIN_CHILD_STDERR_OVERFLOW'
    assert result.classification=='REFUSED_CLEAN'


def test_spawn_postbirth_deadline_failure_still_settles_registered_child(world,monkeypatch):
    v=interval(world);proc=S(pid=CHILD.pid,stdin=io.BytesIO(),stdout=io.BytesIO(),stderr=io.BytesIO())
    monkeypatch.setattr(o,'_sealed_client_entrypoint',Mock(return_value='/fixed'))
    def born(*a,**kw):
        v._budget().primary_refusal=o.OriginIntervalError('inert expired after birth')
        return proc
    monkeypatch.setattr(o.subprocess,'Popen',born)
    settle=Mock();monkeypatch.setattr(v,'_abandon_child',settle)
    with pytest.raises(ValueError):o._spawn_origin_client(v,forward_args())
    assert v.child.process is proc and v.failed
    settle.assert_called_once_with(v.child)


def test_partial_socket_writes_share_one_absolute_deadline(monkeypatch):
    ticks = iter((1_000_000_000, 1_000_000_000, 3_000_000_000))
    monkeypatch.setattr(c, 'time', S(monotonic_ns=lambda: next(ticks, 3_000_000_000)))
    writes = []
    conn = S(settimeout=lambda value: None, send=lambda view: writes.append(bytes(view)) or 1)
    with pytest.raises(c.OriginClientError, match='DEADLINE'):
        c._send_socket_frame(conn, {'v': 1}, 2_000_000_000)
    assert len(writes) <= 2


def test_unsettled_child_before_submission_is_not_clean(world, monkeypatch):
    v = interval(world)
    rd, wr = os.pipe(); er, ew = os.pipe(); os.close(wr); os.close(ew)
    proc = S(pid=CHILD.pid, stdin=io.BytesIO(), stdout=os.fdopen(rd, 'rb', buffering=0),
             stderr=os.fdopen(er, 'rb', buffering=0))
    request, digest = f.validate_forward_request(forward_args())
    child = o._OriginChild(proc, digest, request, v); child.instance = CHILD; v.child = child
    def uncertain(ch):
        proc.stdout.close(); proc.stderr.close()
        raise RuntimeError('inert cleanup outcome unknown')
    monkeypatch.setattr(v, '_settle_child', uncertain)
    result = o._serve_origin_witnesses(v, child)
    assert result.classification == 'UNKNOWN_RETAINED'


@pytest.mark.parametrize('boundary', ['acquire-version', 'stage-unique', 'cleanup-version'])
def test_guard_joins_captured_child_generation_at_every_boundary(world, monkeypatch, boundary):
    calls = 0
    def observe(pid):
        nonlocal calls
        calls += 1
        version = CHILD.pidversion
        unique = CHILD.unique_id
        if boundary == 'acquire-version' or (boundary == 'cleanup-version' and calls >= 9):
            version += 1
        if boundary == 'stage-unique' and calls >= 2:
            unique += 1
        return S(unique_id=unique, pidversion=version,
                 parent_unique_id=ORIGIN.unique_id, parent_pidversion=ORIGIN.pidversion)
    monkeypatch.setattr(h, '_observe_native_instance', observe)
    result, errors, _, conn, _ = chain(monkeypatch, world)
    assert result.classification == 'UNKNOWN_RETAINED'
    assert conn.submissions == 1
    assert any(isinstance(error, h.ForwardHostContextError)
               and 'CHILD' in error.code for error in errors), errors
