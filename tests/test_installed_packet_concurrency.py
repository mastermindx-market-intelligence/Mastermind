"""Concurrency regressions for the installed packet build, not Runtime reads."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock

import pytest

from integrations.executive_mcp.installed import InstalledBootPacketCollector
from integrations.executive_mcp.schemas import GatewayError


def collector_at(tmp_path):
    return InstalledBootPacketCollector(
        source_root=tmp_path / 'source', macro_root=tmp_path / 'macro',
        code_root=tmp_path / 'code', python_executable=Path('/usr/bin/python3'),
    )


def call(collector, *, now=None, timeout=3):
    return collector(repo_root=collector._source_root,
                     macro_root_flag=str(collector._macro_root),
                     now=now, timeout=timeout)


def test_overlapping_failed_source_proof_runs_once_and_is_not_cached(tmp_path, monkeypatch):
    collector = collector_at(tmp_path)
    entered, duplicate, release = Event(), Event(), Event()
    lock = Lock()
    count = 0

    def reject(*args, **kwargs):
        nonlocal count
        with lock:
            count += 1
            (entered if count == 1 else duplicate).set()
        assert release.wait(3)
        raise GatewayError('backend_unavailable', 'source changed')

    monkeypatch.setattr(collector, '_snapshot_pair', reject)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call, collector)
        assert entered.wait(1)
        second = pool.submit(call, collector)
        try:
            assert not duplicate.wait(.25), 'duplicate source proof while first still in flight'
        finally:
            release.set()
        for future in (first, second):
            with pytest.raises(GatewayError, match='source changed'):
                future.result(2)
    assert count == 1
    with pytest.raises(GatewayError, match='source changed'):
        call(collector)
    assert count == 2, 'a completed failure must never become a cached result'


def test_success_is_copied_per_caller_and_next_call_rebuilds(tmp_path, monkeypatch):
    collector = collector_at(tmp_path)
    entered, release, joined = Event(), Event(), Event()
    count = 0

    def build(**kwargs):
        nonlocal count
        count += 1
        entered.set()
        assert release.wait(3)
        return {'generation': count, 'nested': {'values': [count]}}

    monkeypatch.setattr(collector, '_collect_packet', build)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call, collector)
        assert entered.wait(1)
        # Observe follower entry without sleeps or allowing the owner to finish.
        pending = next(iter(collector._collections.values())).future
        original = pending.result
        def wait_for_result(timeout):
            joined.set()
            return original(timeout)
        monkeypatch.setattr(pending, 'result', wait_for_result)
        second = pool.submit(call, collector)
        try:
            assert joined.wait(1)
        finally:
            release.set()
        a, b = first.result(2), second.result(2)
    assert count == 1
    a['nested']['values'].append('caller mutation')
    assert b == {'generation': 1, 'nested': {'values': [1]}}
    assert call(collector)['generation'] == 2


@pytest.mark.parametrize('different', [{'now': 'different-clock'}, {'timeout': 2}])
def test_distinct_request_inputs_do_not_share(tmp_path, monkeypatch, different):
    collector = collector_at(tmp_path)
    entered, both, release = Event(), Event(), Event()
    count = 0
    lock = Lock()
    def build(**kwargs):
        nonlocal count
        with lock:
            count += 1
            (entered if count == 1 else both).set()
        assert release.wait(3)
        return {'now': kwargs['now'], 'timeout': kwargs['timeout']}
    monkeypatch.setattr(collector, '_collect_packet', build)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call, collector)
        assert entered.wait(1)
        second = pool.submit(call, collector, **different)
        try:
            assert both.wait(1)
        finally:
            release.set()
        assert first.result(2) != second.result(2)
    assert count == 2


def test_follower_timeout_does_not_cancel_owner_or_cache_failure(tmp_path, monkeypatch):
    collector = collector_at(tmp_path)
    entered, release = Event(), Event()
    def build(**kwargs):
        entered.set()
        assert release.wait(3)
        return {'complete': True}
    monkeypatch.setattr(collector, '_collect_packet', build)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(call, collector, timeout=.05)
        assert entered.wait(1)
        try:
            with pytest.raises(GatewayError, match='cumulative deadline'):
                call(collector, timeout=.05)
            assert not first.done()
        finally:
            release.set()
        assert first.result(2) == {'complete': True}
    assert not collector._collections


def test_root_mismatch_cannot_join_an_active_collection(tmp_path, monkeypatch):
    collector = collector_at(tmp_path)
    entered, release = Event(), Event()
    def build(**kwargs):
        entered.set()
        assert release.wait(3)
        return {'complete': True}
    monkeypatch.setattr(collector, '_collect_packet', build)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(call, collector)
        assert entered.wait(1)
        try:
            with pytest.raises(GatewayError, match='roots changed'):
                collector(repo_root=tmp_path/'other', macro_root_flag=str(collector._macro_root), now=None, timeout=3)
        finally:
            release.set()
        assert first.result(2) == {'complete': True}


def test_queued_reads_share_overlap_but_project_runtime_separately(tmp_path, monkeypatch):
    import asyncio
    from common.bounded_sync_executor import BoundedSyncExecutor
    from integrations.executive_mcp.adapter import ExecutiveMcpGateway
    from integrations.executive_mcp.installed import InstalledExecutiveReaders

    reader = InstalledExecutiveReaders(
        repo_root=tmp_path/'source', macro_root=tmp_path/'macro',
        runtime_root=tmp_path/'runtime', code_root=tmp_path/'code',
        boot_python=Path('/usr/bin/python3'),
    )
    reader._read_executor = BoundedSyncExecutor(max_concurrency=2)
    collector = reader._packet_builder
    entered, release = Event(), Event()
    builds = projections = 0
    lock = Lock()

    def build(**kwargs):
        nonlocal builds
        builds += 1
        entered.set()
        assert release.wait(3)
        return {'source_generation': builds}

    def project(self, name, arguments, generated_at):
        nonlocal projections
        packet = collector(repo_root=self.config.repo_root,
                           macro_root_flag=self.config.macro_root_flag,
                           now=self.config.now, timeout=self.config.boot_packet_timeout)
        with lock:
            projections += 1
            revision = projections
        packet['runtime_revision'] = revision
        return packet

    monkeypatch.setattr(collector, '_collect_packet', build)
    monkeypatch.setattr(ExecutiveMcpGateway, '_read', project)

    async def scenario():
        reads = [asyncio.create_task(reader._run_read_attempt(
            'executive_state' if i % 2 else 'executive_inbox', {}, 'now')) for i in range(7)]
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            assert next(iter(collector._collections.values())).subscribers == 7
            release.set()
            results = await asyncio.gather(*reads)
            assert builds == 1
            assert [r['source_generation'] for r in results] == [1] * 7
            assert sorted(r['runtime_revision'] for r in results) == list(range(1, 8))
            assert not collector._collections
            later = await reader._run_read_attempt('executive_state', {}, 'later')
            assert later == {'source_generation': 2, 'runtime_revision': 8}
        finally:
            release.set()
            await reader.aclose()
    asyncio.run(scenario())


def test_abandoned_pre_admission_scope_has_no_pending_collection(tmp_path):
    collector = collector_at(tmp_path)
    with pytest.raises(RuntimeError, match='admission closed'):
        with collector.request_scope(now=None, timeout=3):
            assert len(collector._collections) == 1
            raise RuntimeError('admission closed')
    assert not collector._collections


def test_abandoned_caller_preserves_admitted_physical_subscription(tmp_path, monkeypatch):
    import contextvars
    collector = collector_at(tmp_path)
    physical, proceed, building, release = Event(), Event(), Event(), Event()
    count = 0

    def build(**kwargs):
        nonlocal count
        count += 1
        building.set()
        assert release.wait(3)
        return {'generation': count}

    def delayed_read():
        with collector.physical_scope():
            physical.set()
            assert proceed.wait(3)
            return call(collector)

    monkeypatch.setattr(collector, '_collect_packet', build)
    with ThreadPoolExecutor(max_workers=2) as pool:
        with collector.request_scope(now=None, timeout=3):
            context = contextvars.copy_context()
            first = pool.submit(context.run, delayed_read)
            assert physical.wait(1)
        # The async caller has left, but admitted physical work retains its
        # original collection until it drains. A new caller must join it.
        entry = next(iter(collector._collections.values()))
        assert entry.subscribers == 0 and entry.physical == 1
        second = pool.submit(call, collector)
        try:
            assert building.wait(1)
            proceed.set()
            release.set()
            assert first.result(2) == second.result(2) == {'generation': 1}
        finally:
            proceed.set()
            release.set()
    assert count == 1
    assert not collector._collections
