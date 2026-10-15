"""Full source proof budget and real ingress/Runtime ordering; source I/O is a fixture."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from control_plane import executive_ceo_ingress as ingress
from control_plane.executive_runtime import Runtime
from integrations.executive_mcp import installed
from tests.test_executive_ceo_ingress_admission_hook import _v1_frame
from tests.test_executive_ceo_ingress import GROUNDING_A


def case(tmp_path, monkeypatch, *, step=1.0):
    clock = [1000.0]
    monkeypatch.setattr(ingress, '_grounding_clock', lambda: clock[0], raising=False)
    monkeypatch.setattr(installed, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    reader = installed.InstalledExecutiveReaders(repo_root=tmp_path/'mastermind',
        macro_root=tmp_path/'macro', runtime_root=tmp_path/'runtime',
        expected_source_sha=GROUNDING_A['mastermind_sha'])
    calls = []
    def snapshot(path, **kwargs):
        calls.append((path, kwargs))
        deadline = kwargs.get('deadline')
        if deadline is not None and clock[0] >= deadline:
            raise installed.GatewayError('backend_unavailable', 'fixture budget expired')
        clock[0] += step
        return GROUNDING_A['mastermind_sha' if path.name == 'mastermind' else 'macro_sha']
    monkeypatch.setattr(installed, '_clean_git_snapshot', snapshot)
    return reader, calls, clock


def submit(tmp_path, provider, **kwargs):
    runtime = Runtime.at(tmp_path/'actual-runtime')
    return runtime, ingress.handle_frame(_v1_frame(), runtime=runtime,
        grounding_provider=provider, workspace_root=tmp_path/'workspaces', **kwargs)


def test_standalone_observation_binds_one_finite_budget_and_keeps_full_content(tmp_path, monkeypatch):
    reader, calls, clock = case(tmp_path, monkeypatch)
    assert reader.observe() == GROUNDING_A
    assert len(calls) == 2
    assert [kwargs.get('deadline') for _, kwargs in calls] == [1060.0, 1060.0]
    assert all(kwargs.get('content_scope', 'all') == 'all' for _, kwargs in calls)
    assert all(kwargs.get('verify_repository_closure', True) is True for _, kwargs in calls)
    assert [path for path, _ in calls] == [reader._source_root, reader._macro_root]


def test_two_fresh_observations_share_one_budget_and_replay_skips_all_source_reads(tmp_path, monkeypatch):
    reader, calls, clock = case(tmp_path, monkeypatch, step=10)
    runtime, operation = submit(tmp_path, reader)
    first = asyncio.run(operation)
    assert len(calls) == 4
    assert [kwargs.get('deadline') for _, kwargs in calls] == [1060.0]*4
    assert len(runtime.jobs.list_jobs()) == 1
    clock[0] += 1000
    class Refused:
        def observe(self): pytest.fail('durable replay must not observe sources')
    _, replay = submit(tmp_path, Refused())
    second = asyncio.run(replay)
    assert second['job_id'] == first['job_id']
    assert second['duplicate'] is True


def test_expired_second_observation_has_no_job_attempt_or_effect(tmp_path, monkeypatch):
    reader, calls, clock = case(tmp_path, monkeypatch, step=20)
    runtime, operation = submit(tmp_path, reader)
    with pytest.raises(ingress.CeoIngressError) as caught:
        asyncio.run(operation)
    assert caught.value.code == 'grounding_unavailable'
    assert runtime.jobs.list_jobs() == []
    assert runtime.attempts.list_attempts() == []
    assert runtime.events.list_events() == []
    assert all(kwargs.get('deadline') == 1060.0 for _, kwargs in calls)


def test_expiry_in_final_admission_guard_cannot_reach_sink(tmp_path, monkeypatch):
    reader, calls, clock = case(tmp_path, monkeypatch)
    def guard(_): clock[0] = 1061.0
    runtime, operation = submit(tmp_path, reader, admission_guard=guard)
    with pytest.raises(ingress.CeoIngressError) as caught:
        asyncio.run(operation)
    assert caught.value.code == 'grounding_unavailable'
    assert len(calls) == 4
    assert runtime.jobs.list_jobs() == []


def test_cancelled_observation_is_settled_even_after_second_cancel_and_never_submits(tmp_path):
    started, release, settled = threading.Event(), threading.Event(), threading.Event()
    class Provider:
        def observe(self):
            started.set()
            assert release.wait(3), 'fixture release was lost'
            settled.set()
            return dict(GROUNDING_A)
    runtime, operation = submit(tmp_path, Provider())
    async def run():
        task = asyncio.create_task(operation)
        try:
            assert await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.sleep(.02)
            task.cancel()
            await asyncio.sleep(.02)
            assert not task.done(), 'request returned while its source thread was still running'
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError): await task
        assert settled.is_set()
    asyncio.run(run())
    assert runtime.jobs.list_jobs() == []


def test_concurrent_admissions_do_not_share_deadlines_or_extend_expired_request(tmp_path, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(ingress, '_grounding_clock', lambda: clock[0], raising=False)
    first_started, second_started, advance = threading.Event(), threading.Event(), threading.Event()
    class Provider:
        def __init__(self, started): self.started, self.calls = started, 0
        def observe(self):
            self.calls += 1
            if self.calls == 1:
                self.started.set()
                assert advance.wait(3)
            return dict(GROUNDING_A)
    first_provider, second_provider = Provider(first_started), Provider(second_started)
    runtime1, op1 = submit(tmp_path/'first', first_provider)
    runtime2, op2 = submit(tmp_path/'second', second_provider)
    async def run():
        task1 = asyncio.create_task(op1)
        task2 = None
        try:
            assert await asyncio.to_thread(first_started.wait, 2)
            clock[0] = 1010.0
            task2 = asyncio.create_task(op2)
            assert await asyncio.to_thread(second_started.wait, 2)
            clock[0] = 1061.0
        finally:
            advance.set()
        results = await asyncio.gather(task1, task2, return_exceptions=True)
        assert isinstance(results[0], ingress.CeoIngressError), results
        assert results[0].code == 'grounding_unavailable'
        assert isinstance(results[1], dict), results
    asyncio.run(run())
    assert len(runtime1.jobs.list_jobs()) == 0
    assert len(runtime2.jobs.list_jobs()) == 1
    assert first_provider.calls == 1 and second_provider.calls == 2


def test_next_request_gets_its_own_budget_after_a_previous_failure(tmp_path, monkeypatch):
    reader, calls, clock = case(tmp_path, monkeypatch, step=20)
    _, failed = submit(tmp_path/'first', reader)
    with pytest.raises(ingress.CeoIngressError): asyncio.run(failed)
    # A separate short request must not inherit the failed operation's deadline.
    class Provider:
        def observe(self): return dict(GROUNDING_A)
    clock[0] += 1000
    runtime, success = submit(tmp_path/'second', Provider())
    asyncio.run(success)
    assert len(runtime.jobs.list_jobs()) == 1


def test_principal_transaction_guard_expiry_cannot_create_job(tmp_path, monkeypatch):
    from tests.test_executive_principal_ingress import frame, call
    clock = [1000.0]
    monkeypatch.setattr(ingress, '_grounding_clock', lambda: clock[0])
    def guard(_): clock[0] = 1061.0
    with pytest.raises(ingress.CeoIngressError) as caught:
        call(tmp_path, frame(tmp_path), guard=guard)
    assert caught.value.code == 'backend_refused'
    runtime = Runtime.at(tmp_path/'runtime')
    assert runtime.jobs.list_jobs() == []
    assert runtime.events.list_events() == []


def test_cancelled_installed_observation_settles_its_actual_bounded_child(tmp_path, monkeypatch):
    import os
    import sys
    from control_plane.ceo_boot_packet import bounded_subprocess_runner
    started, settled = threading.Event(), threading.Event()
    children = []
    reader = installed.InstalledExecutiveReaders(repo_root=tmp_path/'mastermind',
        macro_root=tmp_path/'macro', runtime_root=tmp_path/'runtime')
    def snapshot(path, **kwargs):
        started.set()
        try:
            result = bounded_subprocess_runner([sys.executable, '-I', '-B', '-c',
                'import os,time; print(os.getpid(),flush=True); time.sleep(30)'],
                cwd=tmp_path, timeout=.3, max_bytes=1024,
                env={'PATH':'/usr/bin:/bin'})
            children.append(int(result['stdout'].strip()))
            assert result['timed_out'] is True
            assert kwargs['deadline'] is not None
            raise installed.GatewayError('backend_unavailable','bounded child stopped')
        finally:
            settled.set()
    monkeypatch.setattr(installed, '_clean_git_snapshot', snapshot)
    runtime, operation = submit(tmp_path, reader)
    async def run():
        task = asyncio.create_task(operation)
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert settled.is_set()
    asyncio.run(run())
    assert len(children) == 1
    with pytest.raises(ProcessLookupError): os.kill(children[0], 0)
    assert runtime.jobs.list_jobs() == []
