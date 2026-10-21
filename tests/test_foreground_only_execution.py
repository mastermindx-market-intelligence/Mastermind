"""Persistent host mode excludes old/new roots outside their live request.

Real Runtime admission and source contexts; no provider or host activation.
"""
import asyncio
import dataclasses
from types import SimpleNamespace

import pytest

from control_plane import foreground_operation as scope
from control_plane.executive_runtime import StateConflict
from tests.test_foreground_operator_completion import service_at
from tests.test_foreground_operation import frame, admit


def foreground_only(service, monkeypatch):
    service.config = dataclasses.replace(service.config, coo_autonomy_armed=True,
                                         coo_foreground_only=True)
    monkeypatch.setattr(service, '_require_current_autonomy', lambda: None)
    service._service_state = 'READY'


def test_after_root_commit_crash_cannot_select_or_drive_historical_roots(tmp_path, monkeypatch):
    async def run():
        service=service_at(tmp_path);foreground_only(service,monkeypatch)
        roots=[]
        for index in range(2):
            f=frame(f'committed-before-crash-{index}')
            async with scope._session_bridge_foreground_dispatch(service.runtime,f,lambda:None) as op:
                # Canonical commit occurs; no later finite arm is constructed.
                roots.append((await admit(service.runtime,tmp_path,op,f))['job_id'])
        before=[job.to_dict() for job in service.runtime.jobs.list_jobs()]
        monkeypatch.setattr(service,'_is_bound_coo_root',lambda _:True)
        monkeypatch.setattr(service,'_require_initial_coo_workspace',lambda _:None)
        monkeypatch.setattr(service,'_require_coo_worker_composed',lambda:pytest.fail('unattended root reached mutation boundary'))
        assert service._next_bound_coo_root() is None
        for root in roots:
            with pytest.raises(StateConflict,match='foreground-only'):
                await service._run_coo_cycle(root)
        # A new service object over the same Runtime has no transient owner.
        restarted=service_at(tmp_path);foreground_only(restarted,monkeypatch)
        monkeypatch.setattr(restarted,'_require_coo_worker_composed',lambda:pytest.fail('restart reached mutation boundary'))
        with pytest.raises(StateConflict,match='foreground-only'):
            await restarted._run_coo_cycle(roots[0])
        assert before==[job.to_dict() for job in service.runtime.jobs.list_jobs()]
        assert service.runtime.attempts.list_attempts()==[]
    asyncio.run(run())


def test_foreground_only_tick_never_selects_or_writes_diagnostics(tmp_path,monkeypatch):
    async def run():
        service=service_at(tmp_path);foreground_only(service,monkeypatch)
        service._coo_shutdown_event=asyncio.Event()
        object.__setattr__(service.config,'coo_tick_interval_seconds',0.001)
        monkeypatch.setattr(service,'_next_bound_coo_root',lambda **_:pytest.fail('selector entered'))
        monkeypatch.setattr(service,'_record_coo_tick_refusal',lambda *_:pytest.fail('diagnostic write entered'))
        await asyncio.wait_for(service._coo_tick_loop(),0.05)
        assert service.runtime.jobs.list_jobs()==[]
    asyncio.run(run())


def test_callback_inherited_source_allowed_but_foreign_root_and_cycle_task_refuse(tmp_path,monkeypatch):
    async def run():
        service=service_at(tmp_path);foreground_only(service,monkeypatch)
        f=frame()
        async with scope._session_bridge_foreground_dispatch(service.runtime,f,lambda:None) as op:
            async with service._foreground_cycle_scope(op):
                root=(await admit(service.runtime,tmp_path,op,f))['job_id']
                service._require_foreground_only_source(root,cycle_entry=True)
                async def callback():
                    # The real dispatcher callback is a separate task.
                    service._require_foreground_only_source(root)
                    with pytest.raises(StateConflict,match='foreground-only'):
                        service._require_foreground_only_source(root,cycle_entry=True)
                    with pytest.raises(scope.ForegroundOperationRefusal,match='fresh admitted root'):
                        service._require_foreground_only_source('foreign')
                await asyncio.create_task(callback())
            with pytest.raises(StateConflict,match='foreground-only'):
                service._require_foreground_only_source(root)
    asyncio.run(run())


def test_dispatch_rechecks_source_after_waiting_for_workspace_lock(tmp_path,monkeypatch):
    async def run():
        service=service_at(tmp_path);foreground_only(service,monkeypatch)
        f=frame()
        async with scope._session_bridge_foreground_dispatch(service.runtime,f,lambda:None) as op:
            async with service._foreground_cycle_scope(op):
                root=(await admit(service.runtime,tmp_path,op,f))['job_id']
                planner=service.runtime.jobs.create_cycle_planner(root,command_id=f'coo-cycle:{root}:create-planner:0')
                monkeypatch.setattr(service,'_require_bound_coo_job',lambda _:service.runtime.jobs.get_job(root))
                monkeypatch.setattr(service,'_require_coo_workspace',lambda _:pytest.fail('closed source reached workspace/start'))
                await service._workspace_lock.acquire()
                task=asyncio.create_task(service._dispatch_cycle_job_exact(planner.job_id,'scoped-dispatch'))
                await asyncio.sleep(0)
                op._mark_source_closed()
                service._workspace_lock.release()
                with pytest.raises(scope.ForegroundOperationClosed):await task
                assert service.runtime.attempts.list_attempts()==[]
    asyncio.run(run())


def test_direct_proof_dispatch_is_not_a_foreground_bypass(tmp_path,monkeypatch):
    async def run():
        service=service_at(tmp_path);foreground_only(service,monkeypatch)
        service.supervisor=SimpleNamespace(start_job=lambda _:pytest.fail('direct dispatch'))
        with pytest.raises(StateConflict,match='foreground-only'):
            await service._dispatch_job('arbitrary-proof')
    asyncio.run(run())
