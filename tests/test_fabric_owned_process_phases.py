"""Original collector/owner phases; harmless local children, inert identity/census."""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

BUNDLE = Path(__file__).resolve().parents[1] / 'integrations/session_bridge/bound_launch_capture'


@pytest.fixture
def lr(tmp_path, monkeypatch):
    manifest = json.loads((BUNDLE / 'CAPTURE_SOURCE.json').read_text())
    path = tmp_path / 'lane_runtime.py'
    path.write_bytes((BUNDLE / 'fixtures/lane_runtime.base.py').read_bytes())
    r = subprocess.run(['patch', '--batch', '-p1', '-i', str(BUNDLE / 'lane_runtime.py.patch')],
                       cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert r.returncode == 0, r.stdout + r.stderr
    assert hashlib.sha256(path.read_bytes()).hexdigest() == manifest['candidate_sha256']
    spec = importlib.util.spec_from_file_location('owned_phase_fixture', path)
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, mod)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, '_observe_owned_launch_identity', lambda pid: {
        'pid': pid, 'pgid': pid, 'session_id': pid, 'boot_id': 'fixture-boot',
        'process_start_identity': 'fixture-generation', 'effective_uid': os.geteuid(),
        'effective_gid': os.getegid(), 'real_uid': os.getuid(), 'real_gid': os.getgid()})
    monkeypatch.setattr(mod, '_session_pids', lambda pgid: ())
    monkeypatch.setattr(mod, '_verified_group_members', lambda pgid: ((pgid,), True))
    def terminate(proc, pgid, *, grace, reason):
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=3)
        return dict(status='terminated', reason=reason, identity_verified=True,
                    census_proven=True, residual_count=0, sigterm_sent=True, sigkill_sent=False)
    monkeypatch.setattr(mod, '_terminate_verified_group', terminate)
    yield mod
    owner = getattr(mod, '_EXECUTION_OWNER', None)
    if owner is not None and isinstance(owner, mod.OwnedExecution):
        if owner.result is None and owner.failure is None:
            try:
                mod.abort_owned_process(owner, RuntimeError('test-finalizer'))
            except RuntimeError:
                pass


def begin(lr, tmp_path, **extra):
    release = tmp_path / 'release'
    command = [sys.executable, '-c',
        'import sys,time; from pathlib import Path; print("started", flush=True); '
        'p=Path(sys.argv[1]);\nwhile not p.exists(): time.sleep(.01)\nprint("completed")',
        str(release)]
    owner = lr.begin_owned_process(command, timeout=3, label='original-run',
        receipt_path=tmp_path / 'terminal.jsonl', **extra)
    return owner, release


def test_begin_retains_actual_child_and_capture_until_original_finish(lr, tmp_path):
    owner, release = begin(lr, tmp_path)
    assert owner.process.poll() is None
    assert not (tmp_path / 'terminal.jsonl').exists()
    assert owner.process_identity['pid'] == owner.process.pid
    release.touch()
    result = lr.finish_owned_process(owner)
    assert result.stdout == 'started\ncompleted\n'
    assert result.returncode == 0 and result.cleanup_proven
    assert lr.finish_owned_process(owner) is result
    rows = (tmp_path / 'terminal.jsonl').read_text().splitlines()
    assert len(rows) == 1 and json.loads(rows[0])['pid'] == owner.process.pid


def test_second_begin_refuses_before_any_second_spawn(lr, tmp_path, monkeypatch):
    owner, release = begin(lr, tmp_path)
    monkeypatch.setattr(lr.subprocess, 'Popen', lambda *a, **kw: pytest.fail('second spawn'))
    with pytest.raises(lr.LaneRuntimeError, match='owner_busy'):
        begin(lr, tmp_path)
    release.touch()
    lr.finish_owned_process(owner)


def test_async_collectors_share_one_finisher_and_rpc_cancel_does_not_cancel_it(lr, tmp_path):
    async def scenario():
        owner, release = begin(lr, tmp_path)
        finisher = lr.start_owned_process_finisher(owner)
        assert lr.start_owned_process_finisher(owner) is finisher
        first = asyncio.create_task(lr.collect_owned_process(owner))
        second = asyncio.create_task(lr.collect_owned_process(owner))
        await asyncio.sleep(.01)
        first.cancel()
        with pytest.raises(asyncio.CancelledError): await first
        assert not finisher.cancelled() and owner.process.poll() is None
        release.touch()
        result = await second
        assert result.cleanup_proven and result is await lr.collect_owned_process(owner)
        assert len((tmp_path / 'terminal.jsonl').read_text().splitlines()) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('bad', ['label', 'identity', 'generation'])
def test_wrong_or_stale_cancel_never_signals(lr, tmp_path, monkeypatch, bad):
    owner, release = begin(lr, tmp_path)
    args = dict(label='original-run', process_identity=owner.process_identity, reason='operator_cancel')
    if bad == 'label': args['label'] = 'sibling'
    if bad == 'identity': args['process_identity'] = {**owner.process_identity, 'pid': 999999}
    if bad == 'generation':
        monkeypatch.setattr(lr, '_observe_owned_launch_identity',
                            lambda pid: {**owner.process_identity, 'process_start_identity': 'reused'})
    terminate = lr._terminate_verified_group
    monkeypatch.setattr(lr, '_terminate_verified_group', lambda *a, **kw: pytest.fail('foreign signal'))
    with pytest.raises(lr.LaneRuntimeError): lr.cancel_exact_owned_process(owner, **args)
    assert owner.process.poll() is None
    monkeypatch.setattr(lr, '_terminate_verified_group', terminate)
    release.touch()
    lr.finish_owned_process(owner)


def test_exact_cancel_uses_original_process_and_single_terminal_owner(lr, tmp_path):
    owner, _ = begin(lr, tmp_path)
    result = lr.cancel_exact_owned_process(owner, label='original-run',
        process_identity=owner.process_identity, reason='operator_cancel')
    assert result['identity_verified'] and owner.process.poll() is not None
    terminal = lr.finish_owned_process(owner)
    assert terminal.cleanup_proven and terminal.returncode != 0
    assert len((tmp_path / 'terminal.jsonl').read_text().splitlines()) == 1


def test_new_begin_rejects_thread_handoff_before_spawn(lr, tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr(lr.subprocess, 'Popen', lambda *a, **kw: pytest.fail('thread spawn'))
    def other_thread():
        try: begin(lr, tmp_path)
        except lr.LaneRuntimeError as exc: errors.append(str(exc))
    thread = threading.Thread(target=other_thread); thread.start(); thread.join()
    assert errors == ['owned_process_main_thread_required']


def test_exception_after_begin_uses_same_settlement_and_retains_failure(lr, tmp_path):
    owner, _ = begin(lr, tmp_path)
    with pytest.raises(RuntimeError, match='owner refusal'):
        lr.abort_owned_process(owner, RuntimeError('owner refusal'))
    assert owner.process.poll() is not None
    row = json.loads((tmp_path / 'terminal.jsonl').read_text())
    assert row['cleanup']['residual_count'] == 0
    with pytest.raises(RuntimeError, match='owner refusal'): lr.finish_owned_process(owner)


def test_async_wait_preserves_process_group_limit_fuse(lr, tmp_path, monkeypatch):
    async def scenario():
        owner, _ = begin(lr, tmp_path)
        monkeypatch.setattr(lr, 'OWNED_PROCESS_CENSUS_INTERVAL_SECONDS', .001)
        monkeypatch.setattr(lr, '_verified_group_members',
                            lambda pgid: (tuple(range(lr.MAX_OWNED_PROCESS_GROUP_MEMBERS + 1)), True))
        result = await lr.collect_owned_process(owner)
        assert result.returncode == lr.PROCESS_LIMIT_RETURNCODE
        assert result.cleanup['reason'] == 'process_group_member_limit_exceeded'
    asyncio.run(scenario())


def test_capture_failure_keeps_owner_excluded_after_terminal(lr, tmp_path, monkeypatch):
    owner, release = begin(lr, tmp_path)
    original = lr._mark_stream_state_unproven
    def incomplete(cleanup, **kw):
        return original(cleanup, **{**kw, 'stdout_complete': False, 'stdout_error': 'fixture'})
    monkeypatch.setattr(lr, '_mark_stream_state_unproven', incomplete)
    release.touch()
    result = lr.finish_owned_process(owner)
    assert not result.cleanup_proven and lr._EXECUTION_OWNER is owner
    monkeypatch.setattr(lr.subprocess, 'Popen', lambda *a, **kw: pytest.fail('replacement spawn'))
    with pytest.raises(lr.LaneRuntimeError, match='owner_busy'): begin(lr, tmp_path)


def test_lost_terminal_receipt_keeps_original_failure_and_exclusion(lr, tmp_path, monkeypatch):
    owner, release = begin(lr, tmp_path)
    def failure(*args): raise OSError('inert durable receipt failure')
    monkeypatch.setattr(lr, '_append_process_receipt', failure)
    release.touch()
    with pytest.raises(OSError, match='durable receipt'): lr.finish_owned_process(owner)
    assert owner.process.poll() is not None and lr._EXECUTION_OWNER is owner
    assert isinstance(owner.failure, OSError)
    with pytest.raises(OSError, match='durable receipt'): lr.finish_owned_process(owner)


def test_interrupted_popen_without_returned_pid_does_not_prove_no_effect(lr, tmp_path, monkeypatch):
    def interrupted(*a, **kw): raise KeyboardInterrupt('fixture interrupted spawn')
    monkeypatch.setattr(lr.subprocess, 'Popen', interrupted)
    with pytest.raises(KeyboardInterrupt): begin(lr, tmp_path)
    assert lr._EXECUTION_OWNER.process is None
    assert lr._EXECUTION_OWNER.spawn_attempted is True
    with pytest.raises(lr.LaneRuntimeError, match='owner_busy'): begin(lr, tmp_path)
