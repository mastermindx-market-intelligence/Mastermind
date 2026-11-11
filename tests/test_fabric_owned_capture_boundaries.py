"""Original FD/cancel observations; local pipes, inert kernel and issuer only."""
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from test_fabric_owned_process_phases import lr, begin

SCHEMA = '{"type":"object"}'


def capture(lr, tmp_path, raw=None):
    run = tmp_path / 'run'; run.mkdir(mode=0o700)
    payload = raw or b'{"structured_output":{"summary":"ok"}}'
    owner = lr.begin_owned_process([sys.executable, '-c',
        'import sys; sys.stdout.buffer.write(bytes.fromhex(sys.argv[1]))', payload.hex()],
        timeout=5, label='original-run', receipt_path=tmp_path / 'terminal.jsonl',
        owned_capture_run_dir=run, owned_capture_result_schema_json=SCHEMA)
    return owner, run


@pytest.mark.parametrize('schema', [
    {'type':'object', 'unsupportedValidationKeyword': True},
    {'$defs':{'obj':{'type':'object'}}, '$ref':'#/$defs/obj', 'required':['missing']},
])
def test_actual_canonical_parser_refuses_mirrored_policy_bypass(lr, schema):
    with pytest.raises(lr.LaneRuntimeError):
        lr._owned_capture_parse_cli_result(b'{"structured_output":{}}', schema)


def test_missing_parser_refuses_before_spawn_only_when_opted_in(lr, tmp_path, monkeypatch):
    from builtins import __import__ as original
    def unavailable(name, *args, **kwargs):
        if name == 'control_plane.claude_subscription_worker':
            raise ImportError('inert missing canonical producer')
        return original(name, *args, **kwargs)
    monkeypatch.setattr('builtins.__import__', unavailable)
    monkeypatch.setattr(lr.subprocess, 'Popen', lambda *a, **k: pytest.fail('spawn before dependency'))
    run = tmp_path/'run'; run.mkdir(mode=0o700)
    with pytest.raises(lr.LaneRuntimeError, match='parser_unavailable'):
        lr.begin_owned_process(['inert'], timeout=1, owned_capture_run_dir=run,
                               owned_capture_result_schema_json=SCHEMA)
    assert not (run/'logs').exists()


@pytest.mark.parametrize('kind', ['stdout', 'stderr', 'result'])
def test_real_second_hard_link_refuses_live_start_and_terminal_qualification(lr, tmp_path, kind):
    run = tmp_path/'run'; run.mkdir(mode=0o700)
    owner, release = begin(lr, tmp_path, owned_capture_run_dir=run,
                          owned_capture_result_schema_json=SCHEMA)
    cap = owner._capture_reservation.files[kind]
    os.link(owner._capture_reservation.paths[kind], tmp_path/'alias')
    assert os.fstat(cap.fd).st_nlink == 2
    with pytest.raises(lr.LaneRuntimeError, match='identity_changed'):
        lr.validate_owned_capture_live(owner)
    release.touch(); result = lr.finish_owned_process(owner)
    assert not result.cleanup_proven
    with pytest.raises(lr.LaneRuntimeError, match='terminal_unqualified'):
        lr.owned_capture_collection(owner)


def test_run_directory_replacement_cannot_relabel_original_open_files(lr, tmp_path):
    run=tmp_path/'run'; run.mkdir(mode=0o700)
    owner, release = begin(lr, tmp_path, owned_capture_run_dir=run,
                          owned_capture_result_schema_json=SCHEMA)
    run.rename(tmp_path/'moved'); run.mkdir(mode=0o700)
    with pytest.raises(lr.LaneRuntimeError, match='file_missing'):
        lr.validate_owned_capture_live(owner)
    release.touch(); result = lr.finish_owned_process(owner)
    assert not result.cleanup_proven and result.structured_result is None


@pytest.mark.parametrize('raw', [b'{"structured_output":{"summary":"ok"}}', b'not JSON'])
def test_join_closes_every_writable_capture_fd_and_preserves_defensive_collection(lr, tmp_path, raw):
    owner, run = capture(lr, tmp_path, raw)
    fds = [cap.fd for cap in owner._capture_reservation.files.values()]
    result = lr.finish_owned_process(owner)
    assert result.cleanup_proven
    for fd in fds:
        with pytest.raises(OSError): os.fstat(fd)
    projected = lr.owned_capture_collection(owner)
    assert projected['stdout'] == raw and projected['stderr'] == b''
    assert projected['capture']['stdout']['stream_sha256'] == hashlib.sha256(raw).hexdigest()
    assert projected['finished_at'] and projected['returncode'] == 0
    # Public dictionaries cannot rewrite original receipt facts.
    projected['capture']['result']['state'] = 'invented'
    result.cleanup['status'] = 'invented'
    fresh = lr.owned_capture_collection(owner)
    assert fresh['capture']['result']['state'] != 'invented'
    assert fresh['cleanup']['status'] != 'invented'
    if raw == b'not JSON':
        assert fresh['capture']['result']['state'] == 'not_published'
        assert (run/'output/result.json').read_bytes() == b''


def test_cancel_retains_actual_receipt_once_without_resignal(lr, tmp_path, monkeypatch):
    owner, release = begin(lr, tmp_path)
    real = lr._terminate_verified_group; calls=[]
    def terminate(*a, **kw):
        calls.append(kw['reason']); return real(*a, **kw)
    monkeypatch.setattr(lr, '_terminate_verified_group', terminate)
    args=dict(label=owner.label, process_identity=owner.process_identity, reason='original cancellation')
    first=lr.cancel_exact_owned_process(owner, **args)
    assert first['cancel_receipt'] == dict(run_id=owner.label, reason=args['reason'],
        signal_sent=True, escalated_to_sigkill=False, already_exited=False,
        finished_at=first['cancel_receipt']['finished_at'])
    assert first['cancel_receipt']['finished_at']
    first['cancel_receipt']['signal_sent'] = False
    second=lr.cancel_exact_owned_process(owner, **args)
    assert second['cancel_receipt']['signal_sent'] is True and len(calls)==1
    with pytest.raises(lr.LaneRuntimeError, match='reason_changed'):
        lr.cancel_exact_owned_process(owner, **{**args, 'reason':'different'})
    result=lr.finish_owned_process(owner)
    assert result.cleanup_proven
    assert len((tmp_path/'terminal.jsonl').read_text().splitlines())==1


def test_uncertain_cancel_attempt_cannot_be_repeated(lr, tmp_path, monkeypatch):
    owner, release = begin(lr, tmp_path); holds=[]
    owner._original_lease=SimpleNamespace(hold_for_reconciliation=holds.append)
    real=lr._terminate_verified_group
    monkeypatch.setattr(lr, '_terminate_verified_group', lambda *a, **k: (_ for _ in ()).throw(OSError('inert uncertainty')))
    args=dict(label=owner.label, process_identity=owner.process_identity, reason='cancel')
    with pytest.raises(OSError): lr.cancel_exact_owned_process(owner, **args)
    monkeypatch.setattr(lr, '_terminate_verified_group', lambda *a, **k: pytest.fail('resend'))
    with pytest.raises(lr.LaneRuntimeError, match='cancel_unconfirmed'):
        lr.cancel_exact_owned_process(owner, **args)
    assert holds == ['owned_cancel_observation_unconfirmed'] and owner.process.poll() is None
    monkeypatch.setattr(lr, '_terminate_verified_group', real)
    release.touch(); lr.finish_owned_process(owner)


def test_completed_original_handle_has_actual_no_signal_already_exited_receipt(lr, tmp_path, monkeypatch):
    owner, release = begin(lr, tmp_path); release.touch(); lr.finish_owned_process(owner)
    monkeypatch.setattr(lr, '_terminate_verified_group', lambda *a, **k: pytest.fail('signal exited run'))
    expected=json.loads(owner._terminal_cleanup_record)
    owner.result.cleanup['status']='invented'
    observed=lr.cancel_exact_owned_process(owner, label=owner.label,
        process_identity=owner.process_identity, reason='late cancel')
    assert observed['status']==expected['status']
    receipt=observed['cancel_receipt']
    assert receipt['already_exited'] and not receipt['signal_sent'] and not receipt['escalated_to_sigkill']


def test_manifest_bound_control_assignment_mode_uses_actual_pinned_store_and_run(lr, tmp_path, monkeypatch):
    """Real FDs/paths, inert fstat principal projection; no chown or host grant."""
    store=tmp_path/'store'; store.mkdir(mode=0o700)
    run=store/'attempt'; run.mkdir(mode=0o700)
    real=lr.os.fstat
    control_uid=os.geteuid()+1000
    inode_modes={store.stat().st_ino:0o750, run.stat().st_ino:0o770}
    def observed(fd):
        info=real(fd)
        if info.st_ino not in inode_modes: return info
        values={field:getattr(info, field) for field in dir(info) if field.startswith('st_')}
        values.update(st_uid=control_uid, st_gid=os.getegid(),
                      st_mode=(info.st_mode & ~0o777) | inode_modes[info.st_ino])
        return SimpleNamespace(**values)
    monkeypatch.setattr(lr.os,'fstat',observed)
    def identity(path):
        info=path.stat()
        return dict(path=str(path),device=info.st_dev,inode=info.st_ino,
            mode=inode_modes[info.st_ino],uid=control_uid,gid=os.getegid(),mtime_ns=info.st_mtime_ns)
    assignment=dict(run=identity(run),store=identity(store),control_uid=control_uid,worker_gid=os.getegid())
    owner,release=begin(lr,tmp_path,owned_capture_run_dir=run,
        owned_capture_result_schema_json=SCHEMA, owned_capture_assignment=assignment)
    assert lr.validate_owned_capture_live(owner)['run_dir']==str(run)
    assert owner._capture_reservation.assignment==assignment
    # A repaired caller dict cannot change the retained immutable snapshot.
    assignment['run']['uid']=os.geteuid()
    assert owner._capture_reservation.assignment['run']['uid']==control_uid
    release.touch(); result=lr.finish_owned_process(owner)
    assert result.cleanup_proven


def test_wrong_control_assignment_root_refuses_before_spawn(lr,tmp_path,monkeypatch):
    store=tmp_path/'store';store.mkdir(mode=0o700);run=store/'run';run.mkdir(mode=0o700)
    def identity(path,mode):
        st=path.stat();return dict(path=str(path),device=st.st_dev,inode=st.st_ino,
            mode=mode,uid=os.geteuid()+1000,gid=os.getegid(),mtime_ns=st.st_mtime_ns)
    assignment=dict(run=identity(run,0o770),store=identity(store,0o750),
                    control_uid=os.geteuid()+1000,worker_gid=os.getegid())
    monkeypatch.setattr(lr.subprocess,'Popen',lambda *a,**k:pytest.fail('unqualified root spawn'))
    with pytest.raises(lr.LaneRuntimeError,match='assignment_changed'):
        lr.begin_owned_process(['inert'],timeout=1,owned_capture_run_dir=run,
            owned_capture_result_schema_json=SCHEMA,owned_capture_assignment=assignment)
    assert not (run/'logs').exists()


def test_sticky_tee_failure_cannot_be_normalized_by_matching_later_file_bytes(lr,tmp_path):
    run=tmp_path/'run';run.mkdir(mode=0o700)
    reservation=lr._OwnedCaptureReservation.create(run,result_schema_json=SCHEMA,limit_bytes=1024)
    raw=b'{"structured_output":{}}'
    cap=reservation.files['stdout'];lr._write_all(cap.fd,raw)
    cap._error_code='owned_capture_write_failed'
    import io
    out=lr._BoundedStreamCollector(io.BytesIO(raw),1024,'stdout',capture_file=cap)
    err=lr._BoundedStreamCollector(io.BytesIO(b''),1024,'stderr',capture_file=reservation.files['stderr'])
    for collector,content in [(out,raw),(err,b'')]:
        collector.eof=True;collector.total_bytes=len(content);collector.capture_hash=hashlib.sha256(content)
    block,result=reservation.finalize(out,err,cleanup=dict(status='not_needed',
        identity_verified=True,census_proven=True,residual_count=0),returncode=0,timed_out=False)
    assert result is None and not block['stdout_file_complete']


def test_close_uncertainty_retains_unqualified_terminal_instead_of_success(lr,tmp_path,monkeypatch):
    owner,run=capture(lr,tmp_path)
    target=owner._capture_reservation.files['stdout'].fd;real=lr.os.close
    def uncertain(fd):
        if fd==target:
            real(fd);raise OSError('inert lost close response')
        return real(fd)
    monkeypatch.setattr(lr.os,'close',uncertain)
    result=lr.finish_owned_process(owner)
    assert not result.cleanup_proven
    assert result.owned_capture['stdout']['error_code']=='owned_capture_close_unconfirmed'
    assert result.owned_capture['result']['state']=='unqualified'
    assert result.owned_capture['provider_observations'] is None
    with pytest.raises(lr.LaneRuntimeError,match='terminal_unqualified'):
        lr.owned_capture_collection(owner)


@pytest.mark.parametrize('reason', [' stop ', ' '])
def test_exact_reason_round_trips_real_bridge_validation(lr, tmp_path, reason):
    from control_plane.executive_fabric_bridge_broker import FabricBridgeBroker
    owner, release = begin(lr, tmp_path)
    payload = dict(binding=dict(root_id='root-inert', job_id='job-inert',
        attempt_id=owner.label,
        effective_grant_digest='a'*64, commission_sha256='b'*64),
        physical_binding_sha256='c'*64, run_id=owner.label, reason=reason)
    broker = object.__new__(FabricBridgeBroker)
    broker._payload('cancel', payload)
    result = lr.cancel_exact_owned_process(owner, label=owner.label,
        process_identity=owner.process_identity, reason=reason)
    assert result['cancel_receipt']['reason'] == reason
    wire = dict(adapter_id='attended-fabric', binding=payload['binding'],
        physical_binding_sha256=payload['physical_binding_sha256'],
        cancellation=result['cancel_receipt'])
    broker._operation_result('cancel', wire, payload)
    lr.finish_owned_process(owner)


@pytest.mark.parametrize('reason', ['', 'x'*501, 'stop\x00now'])
def test_invalid_cancel_reason_refuses_before_signal(lr, tmp_path, monkeypatch, reason):
    owner, release = begin(lr, tmp_path)
    monkeypatch.setattr(lr, '_terminate_verified_group',
        lambda *a, **k: pytest.fail('invalid reason signalled'))
    with pytest.raises(lr.LaneRuntimeError, match='reason_invalid'):
        lr.cancel_exact_owned_process(owner, label=owner.label,
            process_identity=owner.process_identity, reason=reason)
    assert not owner._cancel_attempted
    release.touch(); lr.finish_owned_process(owner)



@pytest.mark.parametrize('cleanup_passing', [True, False])
def test_natural_exit_cancel_before_finisher_preserves_original_success(lr, tmp_path, monkeypatch, cleanup_passing):
    owner, run = capture(lr, tmp_path)
    owner.process.wait(timeout=3)
    assert owner.result is None and owner.process.poll() == 0
    def no_signal(proc, pgid, **kwargs):
        assert proc is owner.process and proc.poll() == 0
        return dict(status='not_needed' if cleanup_passing else 'unknown',
                    identity_verified=True, census_proven=cleanup_passing,
                    residual_count=0 if cleanup_passing else 1,
                    sigterm_sent=False, sigkill_sent=False)
    monkeypatch.setattr(lr, '_terminate_verified_group', no_signal)
    observed = lr.cancel_exact_owned_process(owner, label=owner.label,
        process_identity=owner.process_identity, reason='late observation')
    assert observed['cancel_receipt']['already_exited'] is True
    assert observed['cancel_receipt']['signal_sent'] is False
    assert observed['cancel_receipt']['escalated_to_sigkill'] is False
    assert owner.result is None and owner._cancel_attempted
    result = lr.finish_owned_process(owner)
    assert result.returncode == 0 and result.cleanup_proven
    projected = lr.owned_capture_collection(owner)
    assert projected['cancel_receipt'] == observed['cancel_receipt']
    if cleanup_passing:
        assert result.structured_result == {'summary':'ok'}
        assert result.owned_capture['result']['state'] == 'published'
        assert json.loads((run/'output/result.json').read_bytes()) == {'summary':'ok'}
    else:
        assert result.structured_result is None
        assert result.owned_capture['result']['reason'] == 'cancelled'
        assert (run/'output/result.json').read_bytes() == b''


def test_uncertain_late_cancel_still_suppresses_success_and_refuses_resend(lr, tmp_path, monkeypatch):
    owner, run = capture(lr, tmp_path)
    owner.process.wait(timeout=3)
    calls=[]
    def uncertain(*args, **kwargs):
        calls.append(True); raise OSError('inert cancellation observation unknown')
    monkeypatch.setattr(lr, '_terminate_verified_group', uncertain)
    args=dict(label=owner.label, process_identity=owner.process_identity, reason='late unknown')
    with pytest.raises(OSError): lr.cancel_exact_owned_process(owner, **args)
    with pytest.raises(lr.LaneRuntimeError, match='cancel_unconfirmed'):
        lr.cancel_exact_owned_process(owner, **args)
    result = lr.finish_owned_process(owner)
    assert calls == [True] and owner._cancel_observation is None
    assert result.structured_result is None
    assert result.owned_capture['result']['reason'] == 'cancelled'
    assert (run/'output/result.json').read_bytes() == b''


def test_active_signal_with_zero_exit_still_suppresses_success(lr, tmp_path):
    import time
    run=tmp_path/'run'; run.mkdir(mode=0o700)
    ready=tmp_path/'ready'
    script=('import signal,sys,time; from pathlib import Path; '
            'signal.signal(signal.SIGTERM,lambda *args:sys.exit(0)); '
            'print(bytes.fromhex("7b22737472756374757265645f6f7574707574223a7b2273756d6d617279223a226f6b227d7d").decode(),flush=True); '
            'Path(sys.argv[1]).touch(); time.sleep(30)')
    owner=lr.begin_owned_process([sys.executable,'-c',script,str(ready)],
        timeout=5,label='original-run',receipt_path=tmp_path/'terminal.jsonl',
        owned_capture_run_dir=run,owned_capture_result_schema_json=SCHEMA)
    deadline=time.monotonic()+3
    while not ready.exists() and time.monotonic()<deadline: time.sleep(.01)
    assert ready.exists() and owner.process.poll() is None
    observed=lr.cancel_exact_owned_process(owner,label=owner.label,
        process_identity=owner.process_identity,reason='active cancellation')
    assert observed['cancel_receipt']['already_exited'] is False
    assert observed['cancel_receipt']['signal_sent'] is True
    result=lr.finish_owned_process(owner)
    assert result.returncode == 0 and result.structured_result is None
    assert result.owned_capture['result']['reason'] == 'cancelled'
    assert (run/'output/result.json').read_bytes() == b''
