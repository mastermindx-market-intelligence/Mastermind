"""Actual candidate executor/runner composition with an inert lease and local child."""
import ast
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

from test_fabric_owned_process_phases import lr
from test_fabric_original_owner_runner import setup, _inject_owner_test_keys
from test_fabric_bound_controller_wire import patched


def original(tmp_path, monkeypatch, lr):
    ns, args, _ = setup(tmp_path, monkeypatch)
    tree = ast.parse(patched(tmp_path, 'remote_sub_exec.py', 'EXECUTOR_SOURCE.json'))
    names = {'_begin_reserved_attended_under_lease', '_prepare_reserved_attended_under_lease',
             '_begin_lease_process', '_retain_original_cleanup_hold', '_verify_reserved_realm_observation'}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    ns.update(asyncio=asyncio, os=os, LaneRuntimeError=lr.LaneRuntimeError,
              _launch_receipt_directory=lr._launch_receipt_directory,
              begin_owned_process=lr.begin_owned_process,
              abort_owned_process=lr.abort_owned_process,
              start_owned_process_finisher=lr.start_owned_process_finisher,
              OwnedProcessStartError=lr.OwnedProcessStartError)
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'original-executor-candidate', 'exec'), ns)
    release = tmp_path / 'release'
    binary = tmp_path / 'inert-harness'
    binary.write_text('#!' + sys.executable + '\nimport sys,time\nfrom pathlib import Path\n'
        'sys.stdin.read()\np=Path(' + repr(str(release)) + ')\n'
        'while not p.exists(): time.sleep(.01)\nprint("original owner retained result")\n')
    binary.chmod(0o700)
    args['preparation']['binary'] = dataclasses.replace(args['preparation']['binary'],
        path=str(binary), real_path=str(binary), sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    return ns, args, release


def test_original_lease_is_retained_after_start_and_terminal_is_not_early_release(lr, tmp_path, monkeypatch):
    ns, args, release = original(tmp_path, monkeypatch, lr)
    async def scenario():
        owner, validation = ns['_begin_reserved_attended_under_lease'](**args)
        assert owner.process.poll() is None and args['state']['started']
        assert owner._original_lease is args['lease']
        assert args['lease'].holds == [] and not args['receipt'].exists()
        assert validation == ()
        release.touch()
        result = await lr.collect_owned_process(owner)
        await asyncio.sleep(0)  # original terminal hold callback
        assert result.stdout == 'original owner retained result\n' and result.cleanup_proven
        assert args['lease'].holds == []
        assert owner._original_lease is args['lease']  # assignment ACK still belongs to caller
    asyncio.run(scenario())


def test_original_lease_hold_is_applied_once_only_after_failed_capture(lr, tmp_path, monkeypatch):
    ns, args, release = original(tmp_path, monkeypatch, lr)
    mark = lr._mark_stream_state_unproven
    monkeypatch.setattr(lr, '_mark_stream_state_unproven',
        lambda cleanup, **kw: mark(cleanup, **{**kw, 'stdout_complete': False, 'stdout_error': 'fixture'}))
    async def scenario():
        owner, _ = ns['_begin_reserved_attended_under_lease'](**args)
        assert args['lease'].holds == []
        release.touch()
        first, second = await asyncio.gather(lr.collect_owned_process(owner), lr.collect_owned_process(owner))
        await asyncio.sleep(0)
        assert first is second and not first.cleanup_proven
        assert args['lease'].holds == ['worker_cleanup_unproven']
    asyncio.run(scenario())


def test_missing_event_loop_refuses_before_handler_or_process_effect(lr, tmp_path, monkeypatch):
    ns, args, _ = original(tmp_path, monkeypatch, lr)
    ns['install_signal_cleanup'] = lambda **kw: pytest.fail('signal handler changed')
    ns['begin_owned_process'] = lambda **kw: pytest.fail('spawned')
    with pytest.raises(RuntimeError, match='no running event loop'):
        ns['_begin_reserved_attended_under_lease'](**args)
    assert not args['state']['started'] and args['lease'].holds == []


def test_known_exec_failure_preserves_not_started_and_no_cleanup_hold(lr, tmp_path, monkeypatch):
    ns, args, _ = original(tmp_path, monkeypatch, lr)
    def fail(**kw): raise lr.OwnedProcessStartError(7)
    ns['begin_owned_process'] = fail
    async def scenario():
        with pytest.raises(lr.OwnedProcessStartError): ns['_begin_reserved_attended_under_lease'](**args)
        assert args['state']['started'] is False and args['lease'].holds == []
    asyncio.run(scenario())


def test_missing_terminal_receipt_keeps_same_owner_and_hold(lr, tmp_path, monkeypatch):
    ns, args, release = original(tmp_path, monkeypatch, lr)
    def fail(*a): raise OSError('fixture terminal write failure')
    monkeypatch.setattr(lr, '_append_process_receipt', fail)
    async def scenario():
        owner, _ = ns['_begin_reserved_attended_under_lease'](**args)
        release.touch()
        with pytest.raises(OSError, match='terminal write'): await lr.collect_owned_process(owner)
        await asyncio.sleep(0)
        assert args['lease'].holds == ['worker_cleanup_unproven']
        assert lr._EXECUTION_OWNER is owner and owner._original_lease is args['lease']
    asyncio.run(scenario())


def test_immediate_shutdown_cancellation_before_finisher_entry_settles_same_child(lr, tmp_path, monkeypatch):
    ns, args, _ = original(tmp_path, monkeypatch, lr)
    async def scenario():
        owner, _ = ns['_begin_reserved_attended_under_lease'](**args)
        # No yield: cancellation precedes first execution of finisher coroutine.
        owner._finisher.cancel()
        with pytest.raises(asyncio.CancelledError): await owner._finisher
        await asyncio.sleep(0)
        assert owner.process.poll() is not None
        assert isinstance(owner.failure, asyncio.CancelledError)
        rows = args['receipt'].read_text().splitlines()
        assert len(rows) == 1 and json.loads(rows[0])['cleanup']['residual_count'] == 0
        assert owner._original_lease is args['lease']
        assert args['lease'].holds == []
    asyncio.run(scenario())
