"""Genuine sealed-config target into the real factory; disposable files only."""
import asyncio
import copy
import dataclasses
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.executive_os import executive_mcp_entry as entry
from ops.executive_os.coo_principal_host import CooInstalledSource
from control_plane.workspace_read_service import WorkspaceReadService
from tests.test_principal_ruling_installed_composition import document


def installed(tmp_path, monkeypatch, *, selected=True, target=None):
    raw = document(tmp_path)
    if target is not None:
        raw['principal_ruling_target'] = dataclasses.asdict(target)
        raw['coo']['missions'][0]['work_ref'] = target.work_ref
    if not selected:
        del raw['principal_ruling_target']
    source = tmp_path / raw['release_sha']
    source.mkdir()
    path = tmp_path / 'executive-mcp.json'
    path.write_text(json.dumps(raw))
    # Only privileged ownership admission is a fixture. Actual descriptor,
    # inode/content, process and factory behavior run against disposable files.
    monkeypatch.setattr(entry, 'require_sealed_path', lambda *a, **kw: None)
    owner = CooInstalledSource.from_path(path, source, expected_uid=os.geteuid())
    return owner, path, source, raw


def test_existing_sealed_producer_yields_one_fixed_target(tmp_path, monkeypatch):
    owner, _, _, raw = installed(tmp_path, monkeypatch)
    first = owner.original_acceptance_target()
    assert dataclasses.asdict(first) == raw['principal_ruling_target']
    assert owner.original_acceptance_target() is first


def test_absence_does_not_follow_later_target_enrollment(tmp_path, monkeypatch):
    owner, path, _, raw = installed(tmp_path, monkeypatch, selected=False)
    assert owner.original_acceptance_target() is None
    raw['principal_ruling_target'] = dict(work_ref=raw['coo']['missions'][0]['work_ref'],
        obligation_id='WAKE-' + 'a' * 32, reasoning_surface='future')
    path.write_text(json.dumps(raw))
    assert owner.original_acceptance_target() is None


@pytest.mark.parametrize('change', ['target', 'withdraw', 'same_bytes_replacement',
    'content_aba', 'source_replacement', 'source_mode', 'config_symlink', 'uid', 'pid', 'seal_refusal'])
def test_selected_target_refuses_source_or_process_generation_drift(tmp_path, monkeypatch, change):
    owner, path, source, raw = installed(tmp_path, monkeypatch)
    owner.original_acceptance_target()
    if change == 'target':
        raw['principal_ruling_target']['reasoning_surface'] = 'rotated'
        path.write_text(json.dumps(raw))
    elif change == 'withdraw':
        del raw['principal_ruling_target']
        path.write_text(json.dumps(raw))
    elif change == 'same_bytes_replacement':
        sibling = path.with_suffix('.new')
        sibling.write_bytes(path.read_bytes())
        sibling.replace(path)
    elif change == 'content_aba':
        original, old = path.read_bytes(), path.stat()
        path.write_bytes(original + b' ')
        path.write_bytes(original)
        # Even restoring mtime cannot restore inode ctime.
        os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
    elif change == 'source_replacement':
        source.rename(source.with_name(source.name + '-old'))
        source.mkdir()
    elif change == 'source_mode':
        source.chmod(source.stat().st_mode ^ 0o100)
    elif change == 'config_symlink':
        real = path.with_suffix('.real')
        path.rename(real)
        path.symlink_to(real)
    elif change == 'uid':
        monkeypatch.setattr(entry.os, 'geteuid', lambda: 999999)
    elif change == 'pid':
        monkeypatch.setattr(entry.os, 'getpid', lambda: 999999)
    else:
        def refuse(*a, **kw):
            raise ValueError('actual custody refusal')
        monkeypatch.setattr(entry, 'require_sealed_path', refuse)
    with pytest.raises((ValueError, OSError)):
        owner.original_acceptance_target()


def test_source_replacement_during_descriptor_read_is_refused(tmp_path, monkeypatch):
    owner, path, _, _ = installed(tmp_path, monkeypatch)
    original_open = os.open
    def swapped(candidate, flags, *args, **kwargs):
        fd = original_open(candidate, flags, *args, **kwargs)
        if Path(candidate) == path:
            sibling = path.with_suffix('.new')
            sibling.write_bytes(path.read_bytes())
            sibling.replace(path)
        return fd
    monkeypatch.setattr(os, 'open', swapped)
    with pytest.raises(ValueError):
        owner.original_acceptance_target()


@pytest.mark.parametrize('selected', [False, True])
def test_actual_control_factory_binds_same_installed_owner(tmp_path, monkeypatch, selected):
    from tests.test_product_acceptance_host_selection import configured
    from scripts import executive_os_phase1c as cli
    from control_plane import executive_worker_broker
    from control_plane.executive_runtime import Runtime
    fixture_root, host_root = tmp_path / 'installed', tmp_path / 'host'
    fixture_root.mkdir(); host_root.mkdir()
    owner, path, _, raw_install = installed(fixture_root, monkeypatch, selected=selected)
    raw, options, _ = configured(host_root, monkeypatch, False)
    options['coo_source'] = owner
    captured = {}
    def service(config, **bindings):
        captured.update(bindings)
        return SimpleNamespace(config=config)
    monkeypatch.setattr(cli, 'ExecutiveControlService', service)
    from tests.executive_installed_control_fixture import unix_listener
    import shutil
    room_sockets = []
    def activated(name):
        # Only the Control Room adopts a real listener; give it a test-owned egid dir.
        if name == 'WorkspaceControlRoom':
            listener, room_path = unix_listener()
            room_sockets.append((listener, room_path))
            raw['workspace_control_room']['socket_path'] = room_path
            return listener
        return object()
    monkeypatch.setattr(cli, 'activate_launchd_socket', activated)
    monkeypatch.setattr(executive_worker_broker, 'WorkerBrokerClient', lambda *a, **kw: object())
    try:
        service = cli._service_from_config(raw, **options)
    finally:
        for listener, room_path in room_sockets:
            listener.close()
            shutil.rmtree(os.path.dirname(room_path), ignore_errors=True)
    runtime = Runtime.at(tmp_path / 'runtime')
    service.runtime = runtime
    service._namespace_custody = SimpleNamespace(bound_runtime=lambda actual: actual)
    binding = captured['ceo_ingress_app_binding']
    provider = binding.workspace_read_provider_factory(runtime)
    assert type(provider) is WorkspaceReadService
    assert provider.runtime is runtime
    assert provider._bounded_runtime(runtime) is runtime
    if selected:
        assert provider._product_acceptance_owner_target is owner.original_acceptance_target()
        assert provider._product_acceptance_owner_guard() is None
        raw_install['principal_ruling_target']['reasoning_surface'] = 'rotated'
        path.write_text(json.dumps(raw_install))
        with pytest.raises(ValueError):
            provider._product_acceptance_owner_guard()
    else:
        assert provider._product_acceptance_owner_target is None
        assert provider._product_acceptance_owner_guard is None
    assert not binding.armed
    assert not service.config.coo_autonomy_armed


@pytest.mark.parametrize('change', ['stable', 'before_read', 'during_read', 'guard_replacement'])
def test_real_selector_brackets_installed_target_guard(tmp_path, monkeypatch, change):
    from tests.test_product_acceptance_acquisition_service import acquisition_frame
    from tests.test_product_acceptance_original_selector import anchor, bind_actual_issuer
    from tests.test_product_acceptance_read_projection import case
    from tests.test_product_acceptance_workspace_read import provider
    from control_plane.principal_ruling_target import PrincipalRulingTarget
    import integrations.product_acceptance_selector as selector
    bind_actual_issuer(monkeypatch)
    work, host = tmp_path / 'work', tmp_path / 'host'
    work.mkdir(); host.mkdir()
    with case(work, monkeypatch) as (runtime, basis, _, _, selected, run):
        obligation = anchor(runtime, basis, selected)
        target = PrincipalRulingTarget(selected['work_ref'], obligation.obligation_id, 'original-owner')
        owner, path, _, raw = installed(host, monkeypatch, target=target)
        fixed = owner.original_acceptance_target()
        def guard():
            if owner.original_acceptance_target() is not fixed:
                raise ValueError('changed target')
        calls = []
        actual = selector.read_original_acceptance_observation
        def rotate():
            raw['principal_ruling_target']['reasoning_surface'] = 'rotated'
            path.write_text(json.dumps(raw))
        async def read(service, frame, *, owner_target):
            calls.append(owner_target)
            result = await actual(service, frame, owner_target=owner_target)
            if change == 'during_read':
                rotate()
            elif change == 'guard_replacement':
                service._product_acceptance_owner_guard = lambda: None
            return result
        monkeypatch.setattr(selector, 'read_original_acceptance_observation', read)
        before = runtime.events.list_events()
        def execute(bound):
            svc, frame, _ = provider(work, runtime, basis.reader, selected, bound)
            svc._product_acceptance_owner_target = fixed
            svc._product_acceptance_owner_guard = guard
            if change == 'before_read':
                rotate()
            return asyncio.run(svc.handle_frame(acquisition_frame(frame)))
        result = execute(None) if change == 'before_read' else run(execute)
        if change == 'stable':
            assert result['ok'] is True, result
            assert result['result']['product_acceptance']['selection'] == selected
        else:
            assert result['ok'] is False and result['status'] == 503
        assert len(calls) == (0 if change == 'before_read' else 1)
        assert runtime.events.list_events() == before


def test_unrelated_sibling_does_not_change_selected_namespace(tmp_path, monkeypatch):
    owner, _, _, _ = installed(tmp_path, monkeypatch)
    target = owner.original_acceptance_target()
    (tmp_path / 'unrelated-directory').mkdir()
    assert owner.original_acceptance_target() is target


@pytest.mark.parametrize('bad_guard', [False, {}, 'client-selector'])
def test_constructor_rejects_noncallable_source_guard(tmp_path, monkeypatch, bad_guard):
    owner, _, _, _ = installed(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        WorkspaceReadService(cache=None, runtime=None, authorize=lambda _: True,
            armed={}, runtime_identity={}, product_acceptance_owner_target=owner.original_acceptance_target(),
            product_acceptance_owner_guard=bad_guard)


def test_guard_cannot_supply_missing_target():
    with pytest.raises(ValueError):
        WorkspaceReadService(cache=None, runtime=None, authorize=lambda _: True,
            armed={}, runtime_identity={}, product_acceptance_owner_guard=lambda: None)


def test_guarded_acquisition_cancellation_settles_without_disclosure(tmp_path, monkeypatch):
    import threading
    from tests.test_product_acceptance_acquisition_service import acquisition_frame
    from tests.test_product_acceptance_original_selector import anchor, bind_actual_issuer
    from tests.test_product_acceptance_read_projection import case
    from tests.test_product_acceptance_workspace_read import provider
    from control_plane.principal_ruling_target import PrincipalRulingTarget
    bind_actual_issuer(monkeypatch)
    work, host = tmp_path / 'work', tmp_path / 'host'
    work.mkdir(); host.mkdir()
    with case(work, monkeypatch) as (runtime, basis, _, _, selected, run):
        obligation = anchor(runtime, basis, selected)
        target = PrincipalRulingTarget(selected['work_ref'], obligation.obligation_id, 'original-owner')
        owner, _, _, _ = installed(host, monkeypatch, target=target)
        fixed = owner.original_acceptance_target()
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        guard_calls = []
        before = runtime.events.list_events()
        def execute(bound):
            svc, frame, _ = provider(work, runtime, basis.reader, selected, bound)
            svc._product_acceptance_owner_target = fixed
            def guard():
                assert owner.original_acceptance_target() is fixed
                guard_calls.append('checked')
            svc._product_acceptance_owner_guard = guard
            actual = svc._read_mission_v4
            def held_read(value):
                started.set()
                try:
                    assert release.wait(3)
                    return actual(value)
                finally:
                    finished.set()
            monkeypatch.setattr(svc, '_read_mission_v4', held_read)
            async def cancelled():
                task = asyncio.create_task(svc.handle_frame(acquisition_frame(frame)))
                try:
                    assert await asyncio.to_thread(started.wait, 2)
                    task.cancel()
                    await asyncio.sleep(.02)
                    task.cancel()
                    await asyncio.sleep(.02)
                    assert not task.done()
                finally:
                    release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert finished.is_set()
            asyncio.run(cancelled())
        run(execute)
        assert guard_calls == ['checked']
        assert runtime.events.list_events() == before
