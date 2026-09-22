"""Real SQLite and service-lock custody proofs, exclusively disposable fixtures."""
from __future__ import annotations

import asyncio
import fcntl
import gc
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from control_plane import executive_runtime as er
from control_plane.executive_backup import create_online_backup, restore_backup_offline, RestoreSafetyError
from control_plane.executive_runtime import Runtime, RuntimeReadUnavailable
from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody

WRITER = """import sqlite3,sys
c=sqlite3.connect(sys.argv[1],timeout=.03,isolation_level=None)
try:
 c.execute('BEGIN IMMEDIATE');c.execute('ROLLBACK');print('RESERVED')
except sqlite3.OperationalError: print('BLOCKED')
finally: c.close()
"""
SNAPSHOT = """import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); print(json.dumps({x.name:[x.stat().st_ino,hashlib.sha256(x.read_bytes()).hexdigest()] for x in p.iterdir() if x.is_file()},sort_keys=True))
"""


def writer_result(runtime):
    return subprocess.check_output([sys.executable, '-c', WRITER, str(runtime.store.path)], text=True).strip()


def snapshot(runtime):
    # Hashing in the SQLite process itself would close raw main/SHM descriptors.
    return subprocess.check_output([sys.executable, '-c', SNAPSHOT, str(runtime.store.path.parent)], text=True)


def make_owner(tmp_path):
    runtime = Runtime.at(tmp_path.resolve() / 'runtime')
    directory = runtime.store.path.parent
    lock = directory / 'executive-service.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    marker = directory / 'executive-service.running'
    marker.write_text(json.dumps({'instance_id': 'fixture', 'pid': os.getpid()}))
    marker.chmod(0o600)
    owner = ServiceRuntimeNamespaceCustody(runtime=runtime, service_lock_fd=fd,
        lock_path=lock, marker_path=marker, instance_id='fixture')
    owner.start()
    return runtime, owner, fd


@pytest.fixture
def owned(tmp_path):
    runtime, owner, fd = make_owner(tmp_path)
    yield runtime, owner
    # Failed-close tests run in their own subprocess, never bypass quarantine.
    owner.close()
    os.close(fd)


def test_actual_bounded_read_preserves_bytes_and_blocks_separate_writer(owned):
    runtime, owner = owned
    before = snapshot(runtime)
    bound = owner.bound_runtime(runtime)
    with bound.store.read() as connection:
        assert connection.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0
        assert writer_result(runtime) == 'BLOCKED'
    assert snapshot(runtime) == before
    assert writer_result(runtime) == 'RESERVED'


def test_all_supported_same_process_actors_preserve_reservation(owned, tmp_path):
    from control_plane.executive_service import ExecutiveControlService
    from integrations.executive_mcp.adapter import _open_readonly_runtime
    runtime, owner = owned
    with owner.bound_runtime(runtime).store.read():
        for other in (runtime, Runtime.at(runtime.store.root, create=False),
                      _open_readonly_runtime(runtime.store.root)):
            with other.store.read() as connection:
                connection.execute('SELECT COUNT(*) FROM events').fetchone()
            assert writer_result(runtime) == 'BLOCKED'
        service = ExecutiveControlService.__new__(ExecutiveControlService)
        service.runtime = runtime
        assert service._database_health()['ok']
        assert writer_result(runtime) == 'BLOCKED'
        create_online_backup(runtime.store, tmp_path / 'backup')
        assert writer_result(runtime) == 'BLOCKED'


def test_exact_runtime_identity_and_monotonic_name_invalidation(owned):
    runtime, owner = owned
    with pytest.raises(RuntimeReadUnavailable):
        owner.bound_runtime(Runtime.at(runtime.store.root, create=False))
    marker = owner._marker_path
    old = marker.read_bytes()
    marker.write_text('{}')
    with pytest.raises(RuntimeReadUnavailable):
        owner.bound_runtime(runtime)
    marker.write_bytes(old)
    with pytest.raises(RuntimeReadUnavailable):
        owner.bound_runtime(runtime)


def test_replacement_directory_detected_and_not_recovered(owned):
    runtime, owner = owned
    root = runtime.store.root
    moved = root.with_name('old-runtime')
    root.rename(moved)
    root.mkdir()
    with pytest.raises((RuntimeReadUnavailable, OSError)):
        owner.bound_runtime(runtime)
    root.rmdir()
    moved.rename(root)
    with pytest.raises(RuntimeReadUnavailable):
        owner.bound_runtime(runtime)


def test_canonical_lock_is_never_unlocked_during_read(owned):
    runtime, owner = owned
    script = """import fcntl,os,sys
f=os.open(sys.argv[1],os.O_RDONLY)
try:
 fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB); print('UNLOCKED')
except BlockingIOError: print('HELD')
finally: os.close(f)
"""
    for _ in range(2):
        with owner.bound_runtime(runtime).store.read():
            assert subprocess.check_output([sys.executable, '-c', script, str(owner._lock_path)], text=True).strip() == 'HELD'


def test_writer_busy_is_bounded_and_does_not_poison_next_request(owned):
    runtime, owner = owned
    process = subprocess.Popen([sys.executable, '-u', '-c', """import sqlite3,sys
c=sqlite3.connect(sys.argv[1],isolation_level=None);c.execute('BEGIN IMMEDIATE');print('READY');sys.stdin.readline();c.execute('ROLLBACK');c.close()
""", str(runtime.store.path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'READY'
        started = time.monotonic()
        with pytest.raises(RuntimeReadUnavailable):
            with owner.bound_runtime(runtime).store.read():
                pass
        assert time.monotonic() - started < .7
    finally:
        process.communicate('\n', timeout=3)
    with owner.bound_runtime(runtime).store.read():
        pass


def test_finite_drain_retains_active_binding_and_lock(owned):
    runtime, owner = owned
    ready, release = threading.Event(), threading.Event()
    errors = []
    def read():
        try:
            with owner.bound_runtime(runtime).store.read():
                ready.set()
                release.wait(3)
        except RuntimeReadUnavailable:
            errors.append('closed during observation')
    thread = threading.Thread(target=read)
    thread.start()
    assert ready.wait(2)
    try:
        with pytest.raises(RuntimeReadUnavailable):
            owner.close(timeout_seconds=.02)
        gc.collect()
        assert owner._active.binding is not None
        assert owner._connection is not None
        assert writer_result(runtime) == 'BLOCKED'
    finally:
        release.set()
        thread.join(3)
    assert errors
    owner.close()


def test_at_rest_readonly_constructor_is_not_no_creation(tmp_path):
    runtime = Runtime.at(tmp_path / 'runtime')
    names = set(runtime.store.path.parent.iterdir())
    assert not Path(str(runtime.store.path) + '-wal').exists()
    Runtime.at(runtime.store.root, create=False)
    assert set(runtime.store.path.parent.iterdir()) != names


def test_offline_restore_path_locator_refuses_before_live_sqlite_open(owned, tmp_path, monkeypatch):
    runtime, owner = owned
    receipt = create_online_backup(runtime.store, tmp_path / 'backup')
    before = snapshot(runtime)
    original = sqlite3.connect
    def connect(path, *args, **kwargs):
        assert str(runtime.store.path) not in str(path), 'live SQLite opened before lock'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', connect)
    with pytest.raises(RestoreSafetyError, match='marker exists'):
        restore_backup_offline(runtime.store.root, receipt.database_path, receipt.manifest_path)
    assert snapshot(runtime) == before


def test_arbitrary_symlink_is_refused_without_opening_target(owned, tmp_path):
    runtime, owner = owned
    alias = tmp_path / 'alias'
    alias.symlink_to(runtime.store.root, target_is_directory=True)
    assert owner._canonical(alias) == alias
    with pytest.raises(RuntimeReadUnavailable):
        owner._seal_chain(alias)


def test_darwin_var_alias_is_explicit_and_sealed(owned):
    if sys.platform != 'darwin':
        pytest.skip('Darwin canonical alias')
    runtime, owner = owned
    assert owner._canonical(Path('/var')) == Path('/private/var')
    assert Path('/var') in owner._aliases


def test_canary_at_rest_cli_does_not_construct_runtime(tmp_path, capsys):
    from scripts.web_ceo_offline_delivery_canary import main
    root = tmp_path / 'absent'
    assert main(['--runtime-root', str(root), '--root-job-id', 'JOB-test',
                 '--expected-release-sha', 'a' * 40]) == 2
    assert not root.exists()
    assert 'INPUT_REFUSED' in capsys.readouterr().out


@pytest.mark.parametrize('failure', ['physical_close', 'rollback', 'owner_close', 'startup_close'])
def test_uncertain_close_retains_custody_in_separate_process(tmp_path, failure):
    script = r'''
import gc,os,sqlite3,sys
from pathlib import Path
sys.path.insert(0, 'tests')
from test_runtime_namespace_custody import make_owner, writer_result
from control_plane import executive_runtime as er
from control_plane.runtime_namespace_custody import ServiceRuntimeNamespaceCustody
runtime, owner, fd = make_owner(Path(sys.argv[1]))
mode = sys.argv[2]
if mode == 'startup_close':
    owner.close()
    owner = ServiceRuntimeNamespaceCustody(
        runtime=runtime, service_lock_fd=fd,
        lock_path=runtime.store.path.parent / 'executive-service.lock',
        marker_path=runtime.store.path.parent / 'executive-service.running',
        instance_id='fixture')
    original_seal = owner._seal
    def partial_seal(path, **kwargs):
        original_seal(path, **kwargs)
        if str(path).endswith('-wal'):
            raise RuntimeError('fixture partial startup after retaining WAL seal')
    owner._seal = partial_seal
    try: owner.start()
    except RuntimeError: pass
    else: raise AssertionError('expected startup failure')
    assert owner._connection is not None and owner._fds
if mode == 'physical_close':
    def fail(self):
        self._retain_uncertain()
        raise RuntimeError('fixture uncertain physical close')
    er._BoundReadConnection._drain_and_close = fail
elif mode == 'rollback':
    original = owner._statement
    def statement(sql):
        if sql == 'ROLLBACK': raise RuntimeError('fixture rollback uncertainty')
        return original(sql)
    owner._statement = statement
if mode in ('physical_close', 'rollback'):
    try:
        with owner.bound_runtime(runtime).store.read() as connection:
            connection.execute('SELECT COUNT(*) FROM events').fetchone()
    except Exception: pass
    else: raise AssertionError('expected read failure')
    gc.collect()
    assert owner._active is not None
    assert owner._active.binding is not None
    assert writer_result(runtime) == 'BLOCKED'
else:
    native = owner._connection
    class Uncertain:
        def close(self): raise RuntimeError('fixture close uncertainty')
    owner._connection = Uncertain()
    # Keep native strongly owned as well; this is an injected close failure.
    owner.injected_native = native
for attempt in range(2):
    try: owner.close(timeout_seconds=.01)
    except er.RuntimeReadUnavailable: pass
    else: raise AssertionError('uncertain close released custody')
assert owner._connection is not None and owner._lock_fd is not None and owner._fds
print('RETAINED')
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), failure], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == 'RETAINED'


def test_offline_locator_at_rest_held_lock_creates_no_names(tmp_path):
    runtime = Runtime.at(tmp_path / 'runtime')
    receipt = create_online_backup(runtime.store, tmp_path / 'backups')
    lock = runtime.store.path.parent / 'executive-service.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    before = snapshot(runtime)
    assert not Path(str(runtime.store.path) + '-wal').exists()
    try:
        with pytest.raises(RestoreSafetyError, match='lock is held'):
            restore_backup_offline(runtime.store.root, receipt.database_path, receipt.manifest_path)
        assert snapshot(runtime) == before
    finally:
        os.close(fd)


def test_actual_operator_backup_shutdown_and_delayed_connection(tmp_path):
    import tempfile
    from test_executive_service import _service
    from control_plane.executive_service import send_control_request, ServiceError

    async def exercise(socket_root):
        service, _ = _service(tmp_path, socket_root=socket_root)
        await service.start()
        entered, release = threading.Event(), threading.Event()
        native_backup = service._backup_backend.create_online_backup
        def backup(*args, **kwargs):
            entered.set()
            assert release.wait(5)
            return native_backup(*args, **kwargs)
        service._backup_backend.create_online_backup = backup
        idle_reader, idle_writer = await asyncio.open_unix_connection(str(service.socket_path))
        # Use the real local socket and existing backup business owner.
        request = asyncio.create_task(send_control_request(service.socket_path, 'backup', {}))
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(.01)
            assert entered.is_set()
            with pytest.raises(ServiceError, match='not drained'):
                await service.close()
            assert service._lock_fd is not None
            assert service._namespace_custody._connection is not None
            assert service.running_marker_path.exists()
            assert await asyncio.wait_for(idle_reader.read(), 1) == b''
            with pytest.raises(ServiceError, match='closing'):
                await service._dispatch_request({'version': 'mastermind.executive_control/v1', 'command': 'health', 'args': {}})
        finally:
            release.set()
            await asyncio.gather(request, return_exceptions=True)
            await service.close()
            idle_writer.close()
            await idle_writer.wait_closed()
        assert service._lock_fd is None
        assert service._namespace_custody._closed

    with tempfile.TemporaryDirectory(prefix='custody-sock-') as directory:
        asyncio.run(exercise(Path(directory)))


@pytest.mark.parametrize("nested_supervisor", [False, True])
def test_cancelled_operator_physical_work_remains_service_owned(tmp_path, nested_supervisor):
    import tempfile
    from test_executive_service import _service
    from control_plane.executive_service import ServiceError

    async def exercise(socket_root):
        service, _ = _service(tmp_path, socket_root=socket_root)
        await service.start()
        entered, release = threading.Event(), threading.Event()
        def read():
            with service.runtime.store.read() as connection:
                connection.execute('SELECT COUNT(*) FROM events').fetchone()
                entered.set()
                release.wait(5)
        async def supervisor():
            await asyncio.to_thread(read)
        operation = (service._run_owned_coroutine(supervisor()) if nested_supervisor
                     else service._run_physical(read))
        request = asyncio.create_task(operation)
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(.01)
        assert entered.is_set()
        request.cancel()
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)
        try:
            with pytest.raises(ServiceError, match='not drained'):
                await service.close()
            assert service._physical_workers
            assert service._lock_fd is not None
        finally:
            release.set()
            await asyncio.wait(tuple(service._physical_workers), timeout=3)
            await service.close()
    with tempfile.TemporaryDirectory(prefix='custody-sock-') as directory:
        asyncio.run(exercise(Path(directory)))


def test_actual_bounded_root_snapshot_uses_owner_capability(owned):
    runtime, owner = owned
    root = runtime.jobs.create_job('fixture bounded root')
    bound = owner.bound_runtime(runtime)
    observed = bound.read_job_root_bounded(root.job_id)
    assert observed.root_job_id == root.job_id
    assert observed.jobs[0].objective == 'fixture bounded root'
    bound.store.read_binding.validate_before_core_return()


def test_startup_partial_seals_close_after_retained_sqlite(tmp_path, monkeypatch):
    runtime, initial, fd = make_owner(tmp_path)
    initial.close()
    owner = ServiceRuntimeNamespaceCustody(
        runtime=runtime, service_lock_fd=fd, lock_path=initial._lock_path,
        marker_path=initial._marker_path, instance_id='fixture')
    original_seal = owner._seal
    def seal(path, **kwargs):
        original_seal(path, **kwargs)
        if str(path).endswith('-wal'):
            raise RuntimeError('partial startup')
    monkeypatch.setattr(owner, '_seal', seal)
    with pytest.raises(RuntimeError, match='partial startup'):
        owner.start()
    native = owner._connection
    calls = []
    class Connection:
        def close(self):
            native.close()
            calls.append('sqlite closed')
    owner._connection = Connection()
    original_close = os.close
    def close(descriptor):
        calls.append('raw closed')
        original_close(descriptor)
    monkeypatch.setattr(os, 'close', close)
    owner.close()
    assert calls[0] == 'sqlite closed'
    assert calls.count('raw closed') > 3
    os.close(fd)


def test_phase1c_offline_restore_passes_only_pure_locator(tmp_path, monkeypatch):
    from argparse import Namespace
    from scripts import executive_os_phase1c as cli
    from control_plane import executive_backup
    root = tmp_path / 'absent-runtime'
    monkeypatch.setattr(cli, 'load_control_config', lambda path: {'runtime_root': str(root)})
    monkeypatch.setattr(cli, '_backup_paths', lambda config, name: (tmp_path / 'b.sqlite3', tmp_path / 'b.json'))
    observed = []
    def restore(locator, database, manifest):
        observed.append(locator)
        assert isinstance(locator, Path)
        assert not root.exists()
        return 'receipt'
    monkeypatch.setattr(executive_backup, 'restore_backup_offline', restore)
    assert cli._offline_restore(Namespace(config='fixture', name='b', command='restore')) == 'receipt'
    assert observed == [root]


def test_pure_locator_successful_offline_restore(tmp_path):
    runtime = Runtime.at(tmp_path / 'runtime')
    root = runtime.jobs.create_job('backed up')
    receipt = create_online_backup(runtime.store, tmp_path / 'backup')
    runtime.jobs.create_job('after backup')
    restored = restore_backup_offline(runtime.store.root, receipt.database_path, receipt.manifest_path)
    assert restored is not None
    reopened = Runtime.at(runtime.store.root, create=False)
    assert [job.job_id for job in reopened.jobs.list_jobs()] == [root.job_id]
