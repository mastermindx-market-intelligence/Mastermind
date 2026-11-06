"""Explicit installation fixtures, never a live root/systemd/process proof.

Physical held descriptors/bytes/races are real. Root UID/GID/ACL, Linux paths,
runtime and process epochs are explicitly synthetic; no host query is made.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import signal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.test_hermes_isolated_entry import owner_module, manifest, Proxy, root_info
from tests.test_hermes_role_host_observation import _snapshots, IMPLEMENTATION, BINDING
from ops.executive_os import hermes_role_metadata_observer as observer
from common.hermes_role_status_contract import RoleStatusError

sha = lambda raw: hashlib.sha256(raw).hexdigest()


@pytest.fixture
def installed(tmp_path):
    m = owner_module()
    root = tmp_path.resolve() / 'releases' / IMPLEMENTATION
    (root / 'ops/executive_os').mkdir(parents=True)
    (root / 'ops/executive_os/hermes_role_metadata_observer.py').write_text('# explicit held fixture\n')
    (root / 'ops/executive_os/release_manifest.py').write_text('# explicit held entry fixture\n')
    manifest(root)
    physical = tmp_path.resolve() / 'root-install'
    physical.mkdir()
    runtime = physical / 'runtime'; runtime.mkdir()
    executable = runtime / 'python3.12'; executable.write_bytes(b'INERT_INTERPRETER_BYTES_NOT_EXECUTED')
    library = runtime / 'inert.py'; library.write_bytes(b'INERT_STDLIB_BYTES_NOT_EXECUTED')
    record = physical / 'hermes-role-observation.json'
    units = []
    mappings = {'/usr/local/lib/inert.py': library}
    for index, role in enumerate(('mmsecretary', 'mmmeta')):
        argv = [str(executable), '-I', '-S', '-B', str(root / 'ops/executive_os/release_manifest.py'),
                'hermes-runtime', 'supervise', '--profile', '/ROLE_PRIVATE_NOT_OPENED/profile.yaml',
                '--hermes-bin', '/ROLE_PRIVATE_NOT_OPENED/hermes']
        raw = ('[Service]\nUser=' + role + '\nExecStart=' + ' '.join(argv) + '\n').encode()
        path = physical / ('hermes-runtime-' + role + '.service'); path.write_bytes(raw)
        mappings['/etc/systemd/system/' + path.name] = path
        units.append(dict(role=role, sha256=sha(raw), uid=1100 + index, gid=1200 + index,
                          argv=argv, exec_start='EXPLICIT_PID1_EXECSTART_FIXTURE_' + role))
    document = dict(schema='mastermind.hermes_observation_installation.v1',
                    implementation_sha=IMPLEMENTATION, host_binding_sha256=BINDING, epoch='e' * 64,
                    observer_uid=os.getuid(), observer_gid=os.getgid(),
                    runtime=dict(executable=str(executable), sha256=sha(executable.read_bytes()),
                                 import_paths=[str(runtime)], module_files={'/usr/local/lib/inert.py': sha(library.read_bytes())}),
                    units=units)
    record.write_text(json.dumps(document))
    ancestors = {(p.stat().st_dev, p.stat().st_ino) for p in root.parents}
    ancestors |= {(p.stat().st_dev, p.stat().st_ino) for p in physical.parents}
    m.os = Proxy(os, stat=lambda *a, **k: root_info(os.stat(*a, **k), ancestors),
                 fstat=lambda fd: root_info(os.fstat(fd), ancestors))
    m.sys = Proxy(sys, platform='linux', executable=str(executable), path=[str(runtime)], modules={})
    m._LINUX_RELEASES = root.parent
    m._HERMES_OBSERVATION_INSTALL = record
    m._linux_source_acl = lambda fd, directory: None
    owner = m._HeldReleaseSources(root)
    read = owner.read
    def mapped(path, maximum):
        return read(mappings.get(str(path), path), maximum)
    owner.read = mapped
    yield SimpleNamespace(m=m, owner=owner, record=record, document=document,
                          root=root, physical=physical, executable=executable, library=library)
    owner.close()


def test_explicit_root_installation_produces_current_held_source_identity(installed):
    c = installed; bound = c.m._HermesObservationInstallation(c.owner, BINDING)
    identity = bound.identity()
    assert identity == sha(c.record.read_bytes()) and len(identity) == 64
    assert c.owner.held[c.record][0] >= 0
    assert all(c.owner.held[p][0] >= 0 for p in c.owner.held)


@pytest.mark.parametrize('fault', ['absent', 'foreign-release', 'foreign-binding', 'bool-uid',
                                 'wrong-rights', 'caller-extra', 'wrong-executable', 'wrong-digest',
                                 'wrong-imports', 'foreign-module', 'duplicate-role', 'same-role-uid',
                                 'wrong-entry', 'bool-role-uid', 'not-root'])
def test_absent_forged_or_foreign_installation_refuses_before_any_pid1_io(installed, fault):
    c = installed; value = copy.deepcopy(c.document)
    if fault == 'absent': c.record.unlink()
    elif fault == 'foreign-release': value['implementation_sha'] = 'f' * 40
    elif fault == 'foreign-binding': value['host_binding_sha256'] = 'f' * 64
    elif fault == 'bool-uid': value['observer_uid'] = True
    elif fault == 'wrong-rights': value['observer_uid'] += 1
    elif fault == 'caller-extra': value['verified'] = True
    elif fault == 'wrong-executable': value['runtime']['executable'] = '/caller/python'
    elif fault == 'wrong-digest': value['runtime']['sha256'] = 'f' * 64
    elif fault == 'wrong-imports': value['runtime']['import_paths'] = ['/caller/imports']
    elif fault == 'foreign-module': value['runtime']['module_files'] = {'/private/not-opened': 'f' * 64}
    elif fault == 'duplicate-role': value['units'][1] = value['units'][0]
    elif fault == 'same-role-uid': value['units'][1]['uid'] = value['units'][0]['uid']
    elif fault == 'wrong-entry': value['units'][0]['argv'][4] = '/caller/entry.py'
    elif fault == 'bool-role-uid': value['units'][0]['uid'] = True
    else: c.record.chmod(0o666)
    if fault not in {'absent', 'not-root'}: c.record.write_text(json.dumps(value))
    with pytest.raises((c.m.ReleaseManifestError, OSError)):
        c.m._HermesObservationInstallation(c.owner, BINDING)


@pytest.mark.parametrize('fault', ['epoch', 'record-replaced', 'unit', 'interpreter', 'stdlib', 'rights', 'import-path'])
def test_installation_runtime_or_current_rights_change_withdraws_identity(installed, fault):
    c = installed; bound = c.m._HermesObservationInstallation(c.owner, BINDING)
    if fault == 'epoch':
        value = c.document | {'epoch': 'f' * 64}; c.record.write_text(json.dumps(value))
    elif fault == 'record-replaced':
        raw = c.record.read_bytes(); c.record.unlink(); c.record.write_bytes(raw)
    elif fault == 'unit': (c.physical / 'hermes-runtime-mmmeta.service').write_text('foreign unit')
    elif fault == 'interpreter': c.executable.write_bytes(b'foreign interpreter')
    elif fault == 'stdlib': c.library.write_bytes(b'foreign module')
    elif fault == 'rights': c.m.os = Proxy(c.m.os, geteuid=lambda: 99999)
    else: c.m.sys = Proxy(c.m.sys, path=['/foreign/import'])
    with pytest.raises((c.m.ReleaseManifestError, OSError)):
        bound.identity()


@pytest.mark.parametrize('fault', [None, 'dropin', 'fragment', 'reload', 'user', 'exec-start'])
def test_effective_unit_contract_is_checked_before_any_process_metadata(installed, fault):
    c = installed; bound = c.m._HermesObservationInstallation(c.owner, BINDING)
    rows = _snapshots()[0]['roles']
    for row in rows:
        expected = bound.units[row['role']]
        row['effective_source'] = dict(FragmentPath='/etc/systemd/system/' + row['unit'],
            DropInPaths='', NeedDaemonReload='no', User=row['role'], Group=row['role'], ExecStart=expected['exec_start'])
    if fault:
        name = {'dropin': 'DropInPaths', 'fragment': 'FragmentPath', 'reload': 'NeedDaemonReload',
                'user': 'User', 'exec-start': 'ExecStart'}[fault]
        rows[0]['effective_source'][name] = 'foreign'
    calls = []
    c.m._qualify_hermes_process = lambda row, expected: calls.append(row['role'])
    if fault:
        with pytest.raises(c.m.ReleaseManifestError): bound.qualify_rows(rows)
        assert calls == []
    else:
        assert len(bound.qualify_rows(rows)) == 2 and calls == ['mmmeta', 'mmsecretary']
        assert all('effective_source' not in row for row in rows)


def test_unbound_ordinary_import_cannot_invent_source_identity(monkeypatch):
    monkeypatch.setattr(observer, '__loader__', SimpleNamespace(installed_hermes_identity=lambda *a: 'f' * 64))
    assert observer._installed_source_identity(IMPLEMENTATION) is None


@pytest.mark.parametrize('fault', [None, 'missing', 'extra', 'duplicate'])
def test_actual_pid1_decoder_retains_closed_effective_source_fields(fault):
    import tests.test_hermes_role_host_observation as old
    blocks = []
    for row in old._observation()['roles']:
        fields = dict(Id=row['unit'], MainPID=str(row['main_pid']),
            ExecMainStartTimestampMonotonic=str(row['main_start_monotonic_us']),
            InvocationID=row['invocation_id'], NotifyAccess='main', ActiveState='active', SubState='running',
            StatusText=old.status.encode_status_text(row['status']),
            FragmentPath='/etc/systemd/system/'+row['unit'], DropInPaths='', NeedDaemonReload='no',
            User=row['role'], Group=row['role'], ExecStart='explicit-fixture')
        if fault=='missing': fields.pop('DropInPaths')
        if fault=='extra': fields['Environment']='must-not-be-read'
        raw='\n'.join(k+'='+v for k,v in fields.items())
        if fault=='duplicate': raw+='\nExecStart=foreign'
        blocks.append(raw)
    raw=('\n\n'.join(blocks)+'\n').encode()
    if fault:
        with pytest.raises(RoleStatusError): observer._decode_pid1(raw, source_bound=True)
    else:
        rows=observer._decode_pid1(raw, source_bound=True)
        assert len(rows)==2 and all(set(r['effective_source'])==set(observer._SOURCE_PROPERTIES) for r in rows)


@pytest.mark.parametrize('fault', [None, 'pid-epoch', 'executable', 'argv', 'uid', 'cgroup', 'pid-reused'])
def test_actual_process_validator_uses_only_fixed_public_kernel_metadata(installed, fault):
    c = installed; expected = c.document['units'][0]
    row = dict(role='mmsecretary', unit='hermes-runtime-mmsecretary.service',
               main_pid=123, main_start_monotonic_us=50_000_000)
    proc = c.physical / 'proc-fixture'; proc.mkdir()
    stat_fields = [b'S'] + [b'0'] * 18 + [b'5000'] + [b'0'] * 5
    stat_raw = b'123 (inert python) ' + b' '.join(stat_fields) + b'\n'
    documents = {'stat': stat_raw,
        'cmdline': b'\0'.join(v.encode() for v in expected['argv']) + b'\0',
        'status': ('Uid:\t' + '\t'.join([str(expected['uid'])] * 4) + '\nGid:\t' +
                   '\t'.join([str(expected['gid'])] * 4) + '\n').encode(),
        'cgroup': b'0::/system.slice/hermes-runtime-mmsecretary.service\n'}
    if fault == 'pid-epoch': documents['stat'] = stat_raw.replace(b'5000', b'9000')
    elif fault == 'argv': documents['cmdline'] = b'/foreign/entry\0'
    elif fault == 'uid': documents['status'] = documents['status'].replace(str(expected['uid']).encode(), b'999')
    elif fault == 'cgroup': documents['cgroup'] = b'0::/user.slice/caller.service\n'
    for name, raw in documents.items(): (proc / name).write_bytes(raw)
    reads = []
    def opened(path, flags, **kwargs):
        path = Path(path)
        assert path.parent == Path('/proc/123') and path.name in documents
        reads.append(path.name)
        if fault == 'pid-reused' and reads.count('stat') == 2:
            (proc / 'stat').write_bytes(stat_raw.replace(b'5000', b'9000'))
        return os.open(proc / path.name, flags, **kwargs)
    c.m.os = Proxy(c.m.os, open=opened, sysconf=lambda key: 100,
                   readlink=lambda path: '/foreign/executable' if fault == 'executable' else expected['argv'][0])
    if fault:
        with pytest.raises(c.m.ReleaseManifestError): c.m._qualify_hermes_process(row, expected)
    else:
        c.m._qualify_hermes_process(row, expected)
        assert set(reads) == {'stat', 'cmdline', 'status', 'cgroup'}
    assert 'environ' not in reads


def test_root_preparation_never_infers_installation_from_nonroot_or_a_label(installed):
    c = installed
    c.owner.read = lambda *args: pytest.fail('root recipe refusal must precede source reads')
    with pytest.raises(c.m.ReleaseManifestError):
        c.m.prepare_hermes_observation_installation(c.owner, binding=BINDING, epoch='e' * 64,
            observer_uid=501, observer_gid=20, units=[])


def test_actual_root_preparer_derives_bytes_without_install_or_query(installed):
    c = installed
    real_read = c.owner.read
    c.owner.read = lambda path, limit: real_read(c.executable if str(path)=='/usr/bin/python3.12' else path, limit)
    real_path = c.m.Path
    class RecipePath(type(Path())):
        def resolve(self, *args, **kwargs):
            return self if str(self)=='/usr/bin/python3.12' else super().resolve(*args, **kwargs)
    c.m.Path = RecipePath
    c.m.os = Proxy(c.m.os, getuid=lambda: 0, geteuid=lambda: 0)
    c.m.sys = Proxy(c.m.sys, executable='/usr/bin/python3.12', version_info=(3,12),
        flags=SimpleNamespace(isolated=1,no_site=1,dont_write_bytecode=1),
        modules={'inertstdlib':SimpleNamespace(__spec__=SimpleNamespace(origin='/usr/local/lib/inert.py'),
                                             __file__='/usr/local/lib/inert.py')})
    rows = [{k:v for k,v in row.items() if k!='sha256'} for row in c.document['units']]
    before = c.record.read_bytes()
    raw = c.m.prepare_hermes_observation_installation(c.owner, binding=BINDING, epoch='e'*64,
        observer_uid=os.getuid(), observer_gid=os.getgid(), units=rows)
    value = json.loads(raw)
    assert c.record.read_bytes()==before  # Preparation returns bytes only.
    assert value['runtime']['sha256']==sha(c.executable.read_bytes())
    assert value['runtime']['module_files']=={'/usr/local/lib/inert.py':sha(c.library.read_bytes())}
    for row in value['units']:
        assert row['sha256']==sha((c.physical/('hermes-runtime-'+row['role']+'.service')).read_bytes())
    assert value['epoch']=='e'*64 and value['host_binding_sha256']==BINDING
    c.m.Path = real_path


def _source_loader_fixture(c, monkeypatch):
    # Explicit synthetic __main__/root installation; real finder/currentness
    # methods are used, not a callback returning a chosen identity digest.
    modules = {}
    paths = list(c.m.sys.path)
    c.m.sys = Proxy(c.m.sys, modules=modules, meta_path=[], path=paths)
    finder = c.m._ReleaseSourceFinder(c.owner)
    c.m.sys.meta_path.insert(0, finder)
    finder.hermes_observation = c.m._HermesObservationInstallation(c.owner, BINDING)
    entry = SimpleNamespace(_ReleaseSourceFinder=c.m._ReleaseSourceFinder,
                            __file__=str(c.root/'ops/executive_os/release_manifest.py'))
    modules.update({'__main__': entry, observer.__name__: observer})
    finder.owned[observer.__name__] = observer
    monkeypatch.setattr(observer, '__loader__', finder)
    monkeypatch.setattr(observer, 'sys', c.m.sys)
    return finder


def test_actual_loader_identity_checks_current_module_and_root_epoch(installed, monkeypatch):
    c = installed; finder = _source_loader_fixture(c, monkeypatch)
    assert observer._installed_source_identity(IMPLEMENTATION) == sha(c.record.read_bytes())
    assert observer._installed_source_identity('f'*40) is None
    c.record.write_text(json.dumps(c.document | {'epoch': 'f'*64}))
    assert observer._installed_source_identity(IMPLEMENTATION) is None


@pytest.mark.anyio
async def test_source_owner_to_existing_two_snapshot_projection(installed, monkeypatch):
    c = installed; finder = _source_loader_fixture(c, monkeypatch)
    before, after = _snapshots()
    import tests.test_hermes_role_host_observation as old
    rows = copy.deepcopy(before['roles'])
    for row in rows:
        row['effective_source'] = dict(FragmentPath='/etc/systemd/system/'+row['unit'],
            DropInPaths='', NeedDaemonReload='no', User=row['role'], Group=row['role'],
            ExecStart=finder.hermes_observation.units[row['role']]['exec_start'])
    c.m._qualify_hermes_process = lambda row, expected: None  # Kernel fixture is covered independently above.
    monkeypatch.setattr(observer, '_boot_id', lambda: old.BOOT)
    query = AsyncMock(side_effect=[copy.deepcopy(rows), copy.deepcopy(rows)])
    monkeypatch.setattr(observer, '_query_fixed_pid1', query)
    monkeypatch.setattr(observer, 'time', SimpleNamespace(time_ns=lambda: old.NOW*1_000_000,
                                                        monotonic_ns=lambda: old.MONOTONIC*1_000_000))
    value = await observer.HermesRoleMetadataObserver(host_binding_sha256=BINDING,
                                                      implementation_sha=IMPLEMENTATION).read_pair()
    assert value == old._observation() and query.await_count == 2
    projection = old.status.project_observation(value, expected_host_binding_sha256=BINDING,
        expected_implementation_sha=IMPLEMENTATION, now_ms=old.NOW)
    assert projection['state']=='OBSERVED' and projection['proof']==old.workspace.proof()
    assert projection['proof']['credential_enrollment']=='UNVERIFIED'


@pytest.mark.anyio
async def test_source_epoch_changes_during_query_withholds_rows(installed, monkeypatch):
    c = installed; _source_loader_fixture(c, monkeypatch)
    monkeypatch.setattr(observer, '_boot_id', lambda: '12345678-1234-1234-1234-123456789abc')
    async def changed():
        c.record.write_text(json.dumps(c.document | {'epoch':'f'*64}))
        return []
    monkeypatch.setattr(observer, '_query_fixed_pid1', changed)
    with pytest.raises(RoleStatusError):
        await observer.HermesRoleMetadataObserver(host_binding_sha256=BINDING,
            implementation_sha=IMPLEMENTATION).read_pair()


@pytest.mark.anyio
@pytest.mark.parametrize('mode', ['timeout', 'cancel', 'cancel-twice'])
async def test_owned_observation_timeout_and_cancel_settle_waiting_descendant(tmp_path, mode):
    # Only two newly-created benign fixture processes. The parent owns/reaps
    # its child and reports cleanup; no Hermes, systemctl or host PID is read.
    marker = tmp_path/'settled'
    script = r'''
import os,signal,subprocess,sys
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
def stop(sig,frame):
 child.terminate()
 child.wait(timeout=2)
 with open(sys.argv[1],'w') as f:f.write('owned-descendant-reaped')
 raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
print('READY',flush=True)
signal.pause()
'''
    process = await asyncio.create_subprocess_exec(sys.executable, '-I', '-S', '-B', '-c', script, str(marker),
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=True)
    assert await process.stdout.readline() == b'READY\n'
    published = []
    async def request():
        try:
            if mode=='timeout':
                async with asyncio.timeout(0.02): await process.stdout.read()
            else: await process.stdout.read()
            published.append('observation')
        finally:
            task=asyncio.create_task(observer._settle_owned_read(process,session=True))
            await observer._await_owned_cleanup(task)
    task=asyncio.create_task(request())
    if mode!='timeout':
        await asyncio.sleep(0.02);task.cancel()
        if mode=='cancel-twice': await asyncio.sleep(0);task.cancel()
    with pytest.raises((asyncio.CancelledError,asyncio.TimeoutError)):
        await asyncio.wait_for(task,timeout=3)
    assert process.returncode is not None and await process.wait()==0
    assert marker.read_text()=='owned-descendant-reaped' and published==[]
    assert await process.stdout.read()==b''


@pytest.mark.anyio
async def test_fixed_query_cancellation_kills_and_awaits_its_exact_owned_process(monkeypatch):
    process=await asyncio.create_subprocess_exec(sys.executable,'-I','-S','-B','-c','import time;time.sleep(60)',
        stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
    create=AsyncMock(return_value=process)
    monkeypatch.setattr(observer.asyncio,'create_subprocess_exec',create)
    task=asyncio.create_task(observer._query_fixed_pid1())
    await asyncio.sleep(0.02);task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert process.returncode is not None and await process.wait()!=0
    args,kwargs=create.call_args
    assert args[:3]==('/usr/bin/systemctl','show','--no-pager')
    assert args[-2:]==tuple(observer.UNITS)


@pytest.mark.anyio
async def test_direct_parent_kill_preimage_leaves_the_owned_descendant_pipe_open():
    # Causal preimage: the exact former kill-only strategy leaves a waiting
    # descendant. Give only this inert fixture a private session for cleanup;
    # this does not claim the old production reader created one.
    script="import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);print('READY',flush=True);time.sleep(60)"
    process=await asyncio.create_subprocess_exec(sys.executable,'-I','-S','-B','-c',script,
        stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,start_new_session=True)
    assert await process.stdout.readline()==b'READY\n'
    process.kill()  # The previous outer finally, targeting Python only.
    # asyncio Process.wait also waits for inherited pipes; awaiting it here
    # would let the descendant's natural timeout erase the leak discriminator.
    async with asyncio.timeout(1):
        while process.returncode is None: await asyncio.sleep(0.001)
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(process.stdout.read(),timeout=0.03)
    finally:
        # Only the known private fixture group, whose live child holds its
        # session/group identity. No historical or unrelated process target.
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        assert await asyncio.wait_for(process.stdout.read(),timeout=1)==b''
        await process.wait()


@pytest.mark.anyio
async def test_exited_parent_with_waiting_descendant_is_bounded_refusal_not_a_group_signal(monkeypatch):
    script="import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);print('READY',flush=True);time.sleep(60)"
    process=await asyncio.create_subprocess_exec(sys.executable,'-I','-S','-B','-c',script,
        stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,start_new_session=True)
    assert await process.stdout.readline()==b'READY\n'
    process.kill()
    async with asyncio.timeout(1):
        while process.returncode is None: await asyncio.sleep(0.001)
    real_killpg=os.killpg
    signals=[]
    def forbidden(group,sig):
        signals.append((group,sig))
        raise AssertionError('exited leader cannot authenticate a group signal')
    monkeypatch.setattr(observer.os,'killpg',forbidden)
    started=asyncio.get_running_loop().time()
    try:
        with pytest.raises(RoleStatusError):
            await asyncio.wait_for(observer._settle_owned_read(process,session=True),timeout=1.5)
        assert asyncio.get_running_loop().time()-started < 1.5 and signals==[]
    finally:
        # Fixture-only custody remains known separately, so settle its child
        # without routing that authority through the production helper.
        try: real_killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        assert await asyncio.wait_for(process.stdout.read(),timeout=1)==b''
        await process.wait()


@pytest.mark.anyio
async def test_absent_installed_command_refuses_before_subprocess_or_unit(monkeypatch):
    from ops.executive_os import release_manifest as m
    monkeypatch.setattr(observer.sys, 'platform', 'linux')
    def missing(*args): raise m.ReleaseManifestError('explicit absent installation')
    monkeypatch.setattr(m, 'hermes_observation_command', missing)
    forbidden = AsyncMock(side_effect=AssertionError('no observation process before installation'))
    monkeypatch.setattr(observer.asyncio, 'create_subprocess_exec', forbidden)
    with pytest.raises(RoleStatusError):
        await observer.InstalledHermesRoleMetadataObserver(host_binding_sha256=BINDING, implementation_sha=IMPLEMENTATION).read_pair()
    forbidden.assert_not_called()


@pytest.fixture
def anyio_backend(): return 'asyncio'
