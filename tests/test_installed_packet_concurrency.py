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
        pending = next(iter(collector._collections.values()))
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
