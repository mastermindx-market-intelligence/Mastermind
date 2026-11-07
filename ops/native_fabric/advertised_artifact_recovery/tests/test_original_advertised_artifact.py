"""Inert tests for the exact source-admitted advertised artifact recovery.

Every fixture is a local temporary tree. No test performs a remote invocation,
reads the real advertised path, touches the original run's retained bytes, or
mutates any incumbent file. The remote half is exercised by executing the
actual shipped module bytes in a private namespace with an inert scope and
home.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import types

import pytest

MODULE_NAME = 'original_advertised_artifact.py'
SCHEMA = 'mastermind.source_admitted_advertised_artifact_read.v1'
FIXTURE_RUN_ID = 'fixture-advertised-run-01'
FIXTURE_ROOT = '01aaaaaa-1111-2222-3333-444444444444'
FIXTURE_HOST = 'fixture-host'


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _module_path():
    """Find the module under test in the assembled overlay or the repo layout."""
    here = Path(__file__).resolve().parent
    incumbent = Path(__file__).resolve().parents[4] / 'ops/native_fabric/quota_continuity/candidate' / MODULE_NAME
    if incumbent.is_file():
        return incumbent
    for base in (here, *here.parents):
        for candidate in (base / MODULE_NAME,
                          base / 'candidate' / MODULE_NAME,
                          base / 'source' / MODULE_NAME):
            if candidate.is_file():
                return candidate
    raise RuntimeError(MODULE_NAME + ' not found next to the test')


def _load_module():
    path = _module_path()
    spec = importlib.util.spec_from_file_location('advertised_artifact_under_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _incumbent_paths():
    """Directories that let the incumbent import as it is installed."""
    bases = []
    override = os.environ.get('ARTIFACT_DELIVERY_DIR')
    if override and (Path(override) / 'artifact_delivery.py').is_file():
        bases.append(Path(override))
    here = Path(__file__).resolve().parent
    protected = Path(__file__).resolve().parents[4] / 'ops/native_fabric/quota_continuity/candidate'
    if (protected / 'artifact_delivery.py').is_file():
        bases.append(protected)
    for base in (here, *here.parents):
        for candidate in (base, base / 'candidate', base / 'source'):
            if (candidate / 'artifact_delivery.py').is_file():
                bases.append(candidate)
    for primary in bases:
        paths = [primary]
        for sibling in (primary.parent / 'source', primary.parent / 'candidate'):
            if sibling.is_dir() and (sibling / 'artifact_reader.py').is_file():
                paths.append(sibling)
        return paths
    return []


def _import_incumbent(name):
    paths = _incumbent_paths()
    if not paths:
        pytest.skip('no incumbent artifact_delivery.py on this host')
    sys.dont_write_bytecode = True
    try:
        for path in reversed(paths):
            sys.path.insert(0, str(path))
        return __import__(name)
    finally:
        for path in paths:
            try:
                sys.path.remove(str(path))
            except ValueError:
                pass
        sys.dont_write_bytecode = False


def _chain_is_secure(path):
    parts = path.resolve().parts
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            info = current.lstat()
        except OSError:
            return False
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
            return False
    return True


def _secure_root():
    """A writable directory whose whole chain from / is owner-only writable.

    The remote walk starts at ``/`` and refuses a group or world writable
    directory, so the fixture tree needs such an ancestor. The test tree may
    itself live under a world writable directory (a temporary checkout), in
    which case the nearest secure home directory is used instead.
    """
    bases = [Path(__file__).resolve().parent, Path.cwd(),
             Path.home() / '.cache', Path.home()]
    seen = set()
    for base in bases:
        try:
            base = base.resolve()
        except OSError:
            continue
        if base in seen or not base.is_dir():
            continue
        seen.add(base)
        for candidate in (base, *base.parents):
            if _chain_is_secure(candidate) and os.access(candidate, os.W_OK):
                return candidate
    return None


@pytest.fixture(scope='session')
def module():
    return _load_module()


@pytest.fixture()
def secure_tmp():
    """A private fixture root outside any group/world writable ancestor."""
    root = _secure_root()
    if root is None:
        pytest.skip('no owner-only writable ancestor for the remote fixture')
    directory = Path(tempfile.mkdtemp(prefix='advertised-fixture-', dir=str(root)))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


class _Chain:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.fd = self.directory
        self.closed = False

    def verify(self):
        return True

    def close(self):
        self.closed = True


class FakeIncumbent:
    """An inert stand-in for the incumbent artifact_delivery/fabric_task pair."""

    def __init__(self, root):
        self.root = Path(root)
        self.transport_calls = []
        self.transport_result = None
        self.transport_error = None
        self.mutate_local_file = None
        self.status = None
        self.published = []

    # -- artifact_delivery surface -------------------------------------
    def local_file(self, path, limit=1048576):
        data = Path(path).read_bytes()
        if self.mutate_local_file is not None:
            data = self.mutate_local_file(Path(path), data)
        if len(data) > limit:
            raise ValueError('local_evidence_owner_mode_type_or_size')
        return data

    @staticmethod
    def digest(raw):
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def validate_capsule_process(raw, stdout, run_id):
        row = json.loads(raw)
        if (row.get('schema') != 'mastermind.local_owned_process_receipt.v1'
                or row.get('label') != run_id or row.get('returncode') != 0
                or row.get('timed_out') is not False
                or row.get('stdout_bytes') != len(stdout)
                or row.get('stdout_truncated') is not False
                or row.get('stderr_truncated') is not False
                or row.get('runtime_failure_code') is not None):
            raise ValueError('ordinary_process_unqualified')
        cleanup = row.get('cleanup')
        if (not isinstance(cleanup, dict) or cleanup.get('identity_verified') is not True
                or cleanup.get('census_proven') is not True
                or cleanup.get('residual_count') != 0
                or cleanup.get('status') not in ('not_needed', 'terminated')
                or cleanup.get('error_code') is not None):
            raise ValueError('ordinary_cleanup_unproven')
        for stem in ('stdin_delivery', 'stdout_capture', 'stderr_capture'):
            if cleanup.get(stem + '_complete') is not True or cleanup.get(stem + '_error') is not None:
                raise ValueError('ordinary_capture_unproven')

    def transport(self, alias, request, **kwargs):
        self.transport_calls.append((alias, request))
        if self.transport_error is not None:
            raise self.transport_error
        return self.transport_result

    def reserve_destination(self, destination):
        path = Path(destination)
        path.mkdir(parents=True, exist_ok=True)
        return _Chain(path)

    def write_exclusive(self, fd, name, data):
        target = Path(fd) / name
        with open(target, 'xb') as handle:
            handle.write(data)
        return (target.stat().st_dev, target.stat().st_ino)

    def verify_delivered(self, chain, files):
        for entry in files:
            if entry.get('local_name'):
                raw = (Path(chain.fd) / entry['local_name']).read_bytes()
                if len(raw) != entry['bytes'] or _digest(raw) != entry['sha256']:
                    raise ValueError('delivered_file_integrity')

    def publish_receipt(self, chain, receipt, request, verify_source=None):
        if verify_source is not None:
            verify_source()
        payload = _canonical(receipt)
        with open(Path(chain.fd) / 'receipt.json', 'xb') as handle:
            handle.write(payload)
        if verify_source is not None:
            verify_source()
        self.published.append(payload)

    # -- fabric_task surface ------------------------------------------
    def inspect_run(self, run_id):
        return dict(self.status)


def _install(monkeypatch, incumbent):
    delivery = types.ModuleType('artifact_delivery')
    delivery.HERE = incumbent.root
    delivery.ADVERTISED_RECOVERY_SOURCE_SHA256 = _digest(_module_path().read_bytes())
    delivery.local_file = incumbent.local_file
    def checked_source():
        raw = delivery.local_file(delivery.HERE / MODULE_NAME, 131072)
        if _digest(raw) != delivery.ADVERTISED_RECOVERY_SOURCE_SHA256:
            raise ValueError('advertised_remote_source_changed')
        return raw
    delivery.advertised_recovery_source = checked_source
    delivery.digest = incumbent.digest
    delivery.validate_capsule_process = incumbent.validate_capsule_process
    delivery.transport = incumbent.transport
    delivery.reserve_destination = incumbent.reserve_destination
    delivery.write_exclusive = incumbent.write_exclusive
    delivery.verify_delivered = incumbent.verify_delivered
    delivery.publish_receipt = incumbent.publish_receipt
    fabric = types.ModuleType('fabric_task')

    class FabricTaskError(Exception):
        pass

    fabric.FabricTaskError = FabricTaskError
    fabric.inspect_run = incumbent.inspect_run
    monkeypatch.setitem(sys.modules, 'artifact_delivery', delivery)
    monkeypatch.setitem(sys.modules, 'fabric_task', fabric)
    return incumbent


def _process_receipt(run_id, stdout_bytes):
    return {
        'schema': 'mastermind.local_owned_process_receipt.v1',
        'label': run_id,
        'returncode': 0,
        'timed_out': False,
        'pid': 4242,
        'pgid': 4242,
        'stdout_bytes': len(stdout_bytes),
        'stderr_bytes': 0,
        'stdout_truncated': False,
        'stderr_truncated': False,
        'runtime_failure_code': None,
        'started_at': '2026-11-05T12:00:00+00:00',
        'ended_at': '2026-11-05T12:05:00+00:00',
        'cleanup': {
            'identity_verified': True,
            'census_proven': True,
            'residual_count': 0,
            'status': 'not_needed',
            'error_code': None,
            'stdin_delivery_complete': True,
            'stdin_delivery_error': None,
            'stdout_capture_complete': True,
            'stdout_capture_error': None,
            'stderr_capture_complete': True,
            'stderr_capture_error': None,
        },
    }


def _provider_outcome(scope):
    return {
        'schema': 'mastermind.provider_outcome.v1',
        'run_id': scope['run_id'],
        'root_id': scope['root'],
        'host': scope['host'],
        'provider': 'minimax',
        'model': 'MiniMax-M3',
        'account': 'default',
        'lease_id': 'cfe993acf89d',
        'kind': 'success',
        'cli_subtype': 'success',
        'cli_terminal_reason': 'completed',
        'command_rc': 0,
        'cli_command_rc': 0,
        'complete_event_capture': True,
        'initial_rejection': False,
        'permission_denial_count': 0,
        'permission_denials_role': 'none',
        'api_status': None,
        'stdout_sha256': scope['stdout_sha256'],
        'session_id': 'fixture-session',
        'observed_at': 1793922872.0,
    }


def _log_text(scope, events=None):
    if events is None:
        events = [
            'RUN_RESERVED explicit=1',
            'LEASE_OK pool=minimax',
            'SUPPORT_VERSION_READY digest=' + 'a' * 64 + ' policy=' + 'b' * 64,
            'LAUNCH stdout=lanes_' + scope['run_id'] + '.stdout rc_file=ext/lanes_'
            + scope['run_id'] + '.rc cwd=~',
            'LAUNCH_ATTEMPT attempt=1',
            'REMOTE_DONE rc=0',
            'PROCESS_RECEIPT_SAVED file=' + scope['run_id'] + '.process.jsonl',
            'PROVIDER_OUTCOME_RECORDED file=' + scope['run_id'] + '.provider.json',
            'REMOTE_CLEANED transport=1 receipt_saved=1 usage_saved=1',
            'DONE rc=0 signal=ok',
        ]
    return ''.join('2026-11-05T12:00Z [remote_sub id=' + scope['run_id'] + ' host='
                   + scope['host'] + '] ' + event + '\n' for event in events)


def _stdout_text(path, sha):
    return ('The component is complete and verified.\n'
            '\n'
            '**Unified patch**:\n'
            '`' + path + '`\n'
            'sha256 `' + sha + '`\n'
            '\n'
            'SESSION END: PROVEN_OUTCOME\n')


class LocalFixture:
    """One complete, inert local evidence tree for the fixture run."""

    def __init__(self, root, scope, payload):
        self.root = Path(root)
        self.scope = scope
        self.payload = payload
        self.stdout = _stdout_text(scope['path'], scope['sha256']).encode()
        self.log = _log_text(scope).encode()
        self.process = json.dumps(_process_receipt(scope['run_id'], self.stdout)).encode()
        self.packet = b'{"fixture":"request packet"}'
        self.provider = json.dumps(_provider_outcome(scope)).encode()
        self.lanes = self.root / 'lanes'
        self.state = self.root / 'state' / 'remote_sub'
        self.lanes.mkdir(parents=True, exist_ok=True)
        self.state.mkdir(parents=True, exist_ok=True)
        (self.lanes / (scope['run_id'] + '.remote.stdout')).write_bytes(self.stdout)
        (self.state / (scope['run_id'] + '.process.jsonl')).write_bytes(self.process)
        (self.state / (scope['run_id'] + '.provider.json')).write_bytes(self.provider)
        (self.state / (scope['run_id'] + '.log')).write_bytes(self.log)
        (self.state / (scope['run_id'] + '.request.packet')).write_bytes(self.packet)
        (self.root / 'hosts.json').write_bytes(json.dumps({
            FIXTURE_HOST: {'allowed_modes': ['minimax', 'qwen'], 'ssh_alias': 'fixture-alias'},
        }).encode())

    @property
    def evidence_sha256(self):
        return {
            'stdout': _digest(self.stdout),
            'process': _digest(self.process),
            'log': _digest(self.log),
            'packet': _digest(self.packet),
            'provider': _digest(self.provider),
        }


def _local_fixture(tmp_path, payload=b'fixture advertised bytes'):
    scope = {
        'schema': SCHEMA,
        'run_id': FIXTURE_RUN_ID,
        'root': FIXTURE_ROOT,
        'parent': FIXTURE_ROOT,
        'host': FIXTURE_HOST,
        'stdout_sha256': '',
        'path': str(tmp_path / 'advertised' / 'artifact.patch'),
        'sha256': _digest(payload),
    }
    fixture = LocalFixture(tmp_path, scope, payload)
    # The provider outcome joins the retained stdout digest, so it is written
    # once the scope carries that digest.
    scope['stdout_sha256'] = fixture.evidence_sha256['stdout']
    fixture.scope = scope
    fixture.provider = json.dumps(_provider_outcome(scope)).encode()
    (fixture.state / (scope['run_id'] + '.provider.json')).write_bytes(fixture.provider)
    return fixture


def _apply_scope(monkeypatch, module, fixture):
    monkeypatch.setattr(module, 'SCOPE', dict(fixture.scope))
    monkeypatch.setattr(module, 'DESTINATION', str(fixture.root / 'evidence' / 'recovery'))
    monkeypatch.setattr(module, 'EVIDENCE_SHA256', dict(fixture.evidence_sha256))
    monkeypatch.setenv('CODEX_THREAD_ID', fixture.scope['parent'])
    monkeypatch.delenv('POOL_ORCHESTRATOR_ID', raising=False)


def _repin(monkeypatch, module, name, data):
    """Re-pin one evidence kind so the next predicate, not the pin, is tested."""
    pins = dict(module.EVIDENCE_SHA256)
    pins[name] = _digest(data)
    monkeypatch.setattr(module, 'EVIDENCE_SHA256', pins)


def _install_local(monkeypatch, module, tmp_path, payload=b'fixture advertised bytes'):
    fixture = _local_fixture(tmp_path, payload)
    shutil.copyfile(_module_path(), fixture.root / MODULE_NAME)
    incumbent = _install(monkeypatch, FakeIncumbent(fixture.root))
    incumbent.status = {
        'schema': 'mastermind.fabric_task_status.v1',
        'run_id': fixture.scope['run_id'],
        'state': 'TERMINAL',
        'rc': 0,
        'signal': 'ok',
        'result_available': True,
        'result_bytes': len(fixture.stdout),
        'root_id': fixture.scope['root'],
        'parent_run_id': fixture.scope['parent'],
        'acceptance_state': 'NOT_ACCEPTED',
    }
    _apply_scope(monkeypatch, module, fixture)
    return fixture, incumbent


def _remote_response(scope, payload):
    return _canonical({
        'schema': SCHEMA,
        'request_sha256': _digest(_canonical(scope)),
        'files': [{
            'path': scope['path'],
            'status': 'RETRIEVED',
            'bytes': len(payload),
            'sha256': scope['sha256'],
            'data_base64': base64.b64encode(payload).decode(),
            'observed_file': {
                'device': 1, 'inode': 2, 'size': len(payload), 'mtime_ns': 3,
                'ctime_ns': 4, 'mode': 0o600, 'uid': os.getuid(), 'links': 1,
            },
        }],
    })


# ---------------------------------------------------------------------------
# The closed scope itself
# ---------------------------------------------------------------------------

def test_scope_is_the_exact_admitted_object(module):
    assert module.SCOPE == {
        'schema': 'mastermind.source_admitted_advertised_artifact_read.v1',
        'run_id': 'mm-u0-revision-lens-component-20261105-root',
        'root': '01a1333c-a475-7052-95a8-72c623fb12e1',
        'parent': '01a1333c-a475-7052-95a8-72c623fb12e1',
        'host': 'ubuntu1',
        'stdout_sha256': 'b8a7cb1e01bbb384026a39beafd0ff1eee8d4fa850bdb6c1b96a714a034ca63e',
        'path': ('/home/longr/lanes/scratch/p15t1s2-revision-lens-20261105-01/'
                 'market_memory_revision_lens.patch'),
        'sha256': '0337b34f526a9c155d2c5ac3b52485a6d95b1abf88287fc767f6f8930083a3bd',
    }
    assert module.EVIDENCE_SHA256 == {
        'stdout': 'b8a7cb1e01bbb384026a39beafd0ff1eee8d4fa850bdb6c1b96a714a034ca63e',
        'process': '862ad6d0d358633fbe82773b4bfc71c572de838047b3487904c6d2796d3110a6',
        'log': '4b8c4211b8fecad7d458e04b6d37d6127ea918ff2e02eedb293db6284c527048',
        'packet': '4eab8898d2d2528e7139e074a196f2cc9897c6a65644e56a0da5030e6342b3ea',
        'provider': '11b26c9a061e801bcd8ec64f391810ba0562eee6bb17381bcd5d7a0f4b5b7cb6',
    }
    assert module.REMOTE_HOME == '/home/longr'


def test_request_must_equal_the_closed_scope(module):
    base = dict(module.SCOPE)
    module.validate_request(base)
    for mutation in (
        {'extra': 'field'},
        {'schema': 'mastermind.fabric_artifact_read.v1'},
        {'run_id': 'other-run'},
        {'root': '01bbbbbb-1111-2222-3333-444444444444'},
        {'parent': '01bbbbbb-1111-2222-3333-444444444444'},
        {'host': 'ubuntu0'},
        {'stdout_sha256': '0' * 64},
        {'path': '/home/longr/lanes/scratch/other.patch'},
        {'sha256': '0' * 64},
    ):
        forged = dict(base)
        forged.update(mutation)
        with pytest.raises(ValueError) as excinfo:
            module.validate_request(forged)
        assert str(excinfo.value) == 'advertised_request_mismatch'
    with pytest.raises(ValueError):
        module.validate_request(list(base))


def test_the_remote_program_is_the_exact_current_module_bytes(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    shutil.copyfile(_module_path(), fixture.root / MODULE_NAME)
    code = module.code_for_request(dict(fixture.scope), expected_hash=_digest(_module_path().read_bytes()))
    assert code == _module_path().read_text(encoding='utf-8')
    assert 'def remote_main' in code and 'def remote_read' in code


# ---------------------------------------------------------------------------
# The remote half
# ---------------------------------------------------------------------------

def _remote_namespace():
    path = _module_path()
    namespace = {'__name__': 'advertised_remote_fixture', '__file__': str(path)}
    exec(compile(path.read_bytes(), str(path), 'exec'), namespace)
    return namespace


def _remote_fixture(secure_tmp, namespace, payload=b'fixture advertised bytes'):
    home = secure_tmp / 'home'
    nested = home / 'nested'
    nested.mkdir(parents=True)
    artifact = nested / 'artifact.patch'
    artifact.write_bytes(payload)
    os.chmod(artifact, 0o600)
    scope = {
        'schema': SCHEMA,
        'run_id': FIXTURE_RUN_ID,
        'root': FIXTURE_ROOT,
        'parent': FIXTURE_ROOT,
        'host': FIXTURE_HOST,
        'stdout_sha256': _digest(b'stdout'),
        'path': str(artifact),
        'sha256': _digest(payload),
    }
    namespace['SCOPE'] = scope
    namespace['REMOTE_HOME'] = str(home)
    namespace['_current_home'] = lambda: str(home)
    return scope, artifact


def test_remote_read_returns_the_exact_bytes(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    result = namespace['remote_read'](scope)
    assert result['status'] == 'RETRIEVED'
    assert result['path'] == scope['path']
    assert result['bytes'] == len(b'fixture advertised bytes')
    assert result['sha256'] == scope['sha256']
    assert base64.b64decode(result['data_base64'], validate=True) == artifact.read_bytes()
    observed = result['observed_file']
    assert set(observed) == {'device', 'inode', 'size', 'mtime_ns', 'ctime_ns', 'mode', 'uid', 'links'}
    assert observed['size'] == len(b'fixture advertised bytes')
    assert observed['mode'] == 0o600
    assert observed['links'] == 1


def test_remote_read_refuses_a_scope_that_is_not_the_closed_scope(secure_tmp):
    namespace = _remote_namespace()
    scope, _ = _remote_fixture(secure_tmp, namespace)
    forged = dict(scope)
    forged['path'] = forged['path'] + '.other'
    with pytest.raises(ValueError) as excinfo:
        namespace['remote_read'](forged)
    assert str(excinfo.value) == 'advertised_remote_scope_mismatch'


def test_remote_read_refuses_a_symlinked_ancestor(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    real = artifact.parent.parent / 'real'
    real.mkdir()
    os.rename(artifact, real / 'artifact.patch')
    artifact.parent.rmdir()
    (artifact.parent).symlink_to(real)
    result = namespace['remote_read'](scope)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] in namespace['REMOTE_REASONS']


def test_remote_read_refuses_a_symlinked_final_file(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    payload = artifact.read_bytes()
    artifact.unlink()
    target = artifact.parent / 'target.patch'
    target.write_bytes(payload)
    artifact.symlink_to(target)
    result = namespace['remote_read'](scope)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] in namespace['REMOTE_REASONS']


def test_remote_read_refuses_a_group_writable_directory(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    os.chmod(artifact.parent, 0o775)
    try:
        result = namespace['remote_read'](scope)
    finally:
        os.chmod(artifact.parent, 0o755)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'directory_owner_or_mode'


def test_remote_read_refuses_a_world_writable_file(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    os.chmod(artifact, 0o666)
    try:
        result = namespace['remote_read'](scope)
    finally:
        os.chmod(artifact, 0o600)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'file_owner_mode_or_type'


def test_remote_read_refuses_a_hard_linked_file(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    os.link(artifact, artifact.parent / 'second.patch')
    result = namespace['remote_read'](scope)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'file_owner_mode_or_type'


def test_remote_read_refuses_a_fifo(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    artifact.unlink()
    os.mkfifo(artifact)
    result = namespace['remote_read'](scope)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'file_owner_mode_or_type'


def test_remote_read_refuses_an_oversize_file(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace, payload=b'x' * (262144 + 1))
    result = namespace['remote_read'](scope)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'size_limit'


def test_remote_read_refuses_a_missing_file(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    artifact.unlink()
    result = namespace['remote_read'](scope)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'missing_at_read'


def test_remote_read_refuses_content_that_does_not_match_the_advertisement(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    artifact.write_bytes(b'different bytes')
    os.chmod(artifact, 0o600)
    result = namespace['remote_read'](scope)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'content_digest_mismatch'


def test_remote_read_refuses_a_foreign_owner(secure_tmp):
    """A file owned by another account is refused, as is a foreign chain."""
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    real_os = namespace['os']

    class _OsProxy:
        def __init__(self, wrapped, uid):
            self._wrapped = wrapped
            self._uid = uid

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def getuid(self):
            return self._uid

    namespace['os'] = _OsProxy(real_os, real_os.getuid() + 1)
    try:
        result = namespace['remote_read'](scope)
    finally:
        namespace['os'] = real_os
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] in ('file_owner_mode_or_type', 'directory_owner_or_mode')


def test_remote_read_refuses_a_truncated_read(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    real_os = namespace['os']

    class _TruncatingOs:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def read(self, fd, count):
            return self._wrapped.read(fd, 0)

    namespace['os'] = _TruncatingOs(real_os)
    try:
        result = namespace['remote_read'](scope)
    finally:
        namespace['os'] = real_os
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'changed_during_read'


def test_remote_read_refuses_a_swapped_directory_edge(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    real_os = namespace['os']
    state = {'calls': 0}

    class _SwappingOs:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

        def stat(self, path, *args, **kwargs):
            info = self._wrapped.stat(path, *args, **kwargs)
            state['calls'] += 1
            if state['calls'] == 2:
                fields = list(info)
                fields[1] = info.st_ino + 1
                return os.stat_result(tuple(fields))
            return info

    namespace['os'] = _SwappingOs(real_os)
    try:
        result = namespace['remote_read'](scope)
    finally:
        namespace['os'] = real_os
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] in ('directory_chain_changed', 'changed_during_read')


def test_remote_read_refuses_a_home_that_is_not_the_account_home(secure_tmp):
    namespace = _remote_namespace()
    scope, _ = _remote_fixture(secure_tmp, namespace)
    namespace['_current_home'] = lambda: '/home/someone-else'
    result = namespace['remote_read'](scope)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'home_mismatch'


def test_remote_read_refuses_a_path_outside_the_account_home(secure_tmp):
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    scope = dict(scope)
    scope['path'] = '/etc/hostname'
    namespace['SCOPE'] = scope
    result = namespace['remote_read'](scope)
    assert result['status'] == 'UNAVAILABLE'
    assert result['reason'] == 'path_outside_home'


def test_remote_main_answers_one_request_on_stdin(secure_tmp, module):
    """The whole remote program: one request in, one bounded answer out."""
    namespace = _remote_namespace()
    scope, artifact = _remote_fixture(secure_tmp, namespace)
    out = io_bytes()
    namespace['sys'] = types.SimpleNamespace(
        stdin=types.SimpleNamespace(buffer=io_bytes(_canonical(scope))),
        stdout=types.SimpleNamespace(buffer=out),
        flags=types.SimpleNamespace(isolated=1, no_site=1),
        argv=['-c'],
    )
    namespace['remote_main']()
    answer = out.getvalue()
    item, data = module.validate_response(answer, scope)
    assert item['status'] == 'RETRIEVED'
    assert data == artifact.read_bytes()
    assert item['sha256'] == scope['sha256']


def test_remote_main_refuses_a_request_that_is_not_the_closed_scope(secure_tmp):
    namespace = _remote_namespace()
    scope, _ = _remote_fixture(secure_tmp, namespace)
    forged = dict(scope)
    forged['path'] = forged['path'] + '.other'
    namespace['sys'] = types.SimpleNamespace(
        stdin=types.SimpleNamespace(buffer=io_bytes(_canonical(forged))),
        stdout=types.SimpleNamespace(buffer=io_bytes()),
        flags=types.SimpleNamespace(isolated=1, no_site=1),
        argv=['-c'],
    )
    with pytest.raises(SystemExit) as excinfo:
        namespace['remote_main']()
    assert excinfo.value.code == 65


def test_remote_main_refuses_to_run_outside_the_isolated_interpreter(secure_tmp, monkeypatch):
    namespace = _remote_namespace()
    scope, _ = _remote_fixture(secure_tmp, namespace)
    namespace['sys'] = types.SimpleNamespace(
        stdin=types.SimpleNamespace(buffer=io_bytes(_canonical(scope))),
        stdout=types.SimpleNamespace(buffer=io_bytes(), flush=lambda: None),
        flags=types.SimpleNamespace(isolated=0, no_site=1),
        argv=['original_advertised_artifact.py'],
    )
    with pytest.raises(SystemExit) as excinfo:
        namespace['remote_main']()
    assert excinfo.value.code == 65


def io_bytes(initial=b''):
    import io
    return io.BytesIO(initial)


# ---------------------------------------------------------------------------
# The local qualification
# ---------------------------------------------------------------------------

def test_qualify_accepts_the_complete_fixture_evidence(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    evidence = module.qualify(dict(fixture.scope))
    assert evidence['evidence_sha256'] == fixture.evidence_sha256
    assert evidence['ssh_alias'] == 'fixture-alias'
    assert evidence['advertisement'] == {'path': fixture.scope['path'], 'sha256': fixture.scope['sha256']}
    assert evidence['lease_id'] == 'cfe993acf89d'
    assert evidence['historical_joint_seal'] == 'NOT_RETAINED'
    assert incumbent.transport_calls == []


def test_qualify_refuses_a_wrong_native_caller(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    monkeypatch.setenv('CODEX_THREAD_ID', '01bbbbbb-1111-2222-3333-444444444444')
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value) == 'advertised_native_caller_mismatch'
    monkeypatch.delenv('CODEX_THREAD_ID', raising=False)
    with pytest.raises(ValueError):
        module.qualify(dict(fixture.scope))
    assert incumbent.transport_calls == []


def test_qualify_refuses_a_disagreeing_orchestrator(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    monkeypatch.setenv('POOL_ORCHESTRATOR_ID', '01bbbbbb-1111-2222-3333-444444444444')
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value) == 'advertised_native_orchestrator_mismatch'
    assert incumbent.transport_calls == []


@pytest.mark.parametrize('mutation', [
    {'state': 'RUNNING'},
    {'rc': 1},
    {'signal': 'effect_unknown'},
    {'result_available': False},
    {'root_id': '01bbbbbb-1111-2222-3333-444444444444'},
    {'parent_run_id': '01bbbbbb-1111-2222-3333-444444444444'},
    {'acceptance_state': 'UNVERIFIED'},
])
def test_qualify_refuses_an_unqualified_run_projection(monkeypatch, module, tmp_path, mutation):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    incumbent.status.update(mutation)
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value) == 'advertised_run_status_unqualified'
    assert incumbent.transport_calls == []


@pytest.mark.parametrize('name', ['stdout', 'process', 'log', 'packet', 'provider'])
def test_qualify_refuses_changed_evidence(monkeypatch, module, tmp_path, name):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    path = {
        'stdout': fixture.lanes / (fixture.scope['run_id'] + '.remote.stdout'),
        'process': fixture.state / (fixture.scope['run_id'] + '.process.jsonl'),
        'provider': fixture.state / (fixture.scope['run_id'] + '.provider.json'),
        'log': fixture.state / (fixture.scope['run_id'] + '.log'),
        'packet': fixture.state / (fixture.scope['run_id'] + '.request.packet'),
    }[name]
    path.write_bytes(path.read_bytes() + b'tampered')
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value) == 'advertised_evidence_changed_' + name
    assert incumbent.transport_calls == []


@pytest.mark.parametrize('mutation', [
    {'returncode': 1},
    {'stdout_bytes': 3},
    {'timed_out': True},
    {'stdout_truncated': True},
])
def test_qualify_refuses_an_unqualified_process_receipt(monkeypatch, module, tmp_path, mutation):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    receipt = json.loads(fixture.process)
    receipt.update(mutation)
    raw = json.dumps(receipt).encode()
    (fixture.state / (fixture.scope['run_id'] + '.process.jsonl')).write_bytes(raw)
    _repin(monkeypatch, module, 'process', raw)
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value) == 'ordinary_process_unqualified'
    assert incumbent.transport_calls == []


def test_qualify_refuses_a_process_receipt_that_carries_artifact_production(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    receipt = json.loads(fixture.process)
    receipt['artifact_production'] = {'schema': 'mastermind.fabric_artifact_completion.v1'}
    raw = json.dumps(receipt).encode()
    (fixture.state / (fixture.scope['run_id'] + '.process.jsonl')).write_bytes(raw)
    _repin(monkeypatch, module, 'process', raw)
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value) == 'advertised_process_artifact_production_unexpected'
    assert incumbent.transport_calls == []


@pytest.mark.parametrize('mutation', [
    {'root_id': '01bbbbbb-1111-2222-3333-444444444444'},
    {'host': 'other-host'},
    {'model': 'other-model'},
    {'run_id': 'other-run'},
    {'stdout_sha256': '0' * 64},
    {'kind': 'failure'},
    {'command_rc': 1},
    {'initial_rejection': True},
    {'permission_denials_role': 'some-role'},
])
def test_qualify_refuses_a_provider_that_does_not_join(monkeypatch, module, tmp_path, mutation):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    provider = json.loads(fixture.provider)
    provider.update(mutation)
    raw = json.dumps(provider).encode()
    (fixture.state / (fixture.scope['run_id'] + '.provider.json')).write_bytes(raw)
    _repin(monkeypatch, module, 'provider', raw)
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value) == 'advertised_provider_mismatch'
    assert incumbent.transport_calls == []


@pytest.mark.parametrize('mutation', ['two_attempts', 'no_lease', 'wrong_pool', 'no_support',
                                     'no_done', 'uncertainty'])
def test_qualify_refuses_a_log_that_is_not_the_one_settled_launch(monkeypatch, module, tmp_path, mutation):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    events = [
        'RUN_RESERVED explicit=1',
        'LEASE_OK pool=minimax',
        'SUPPORT_VERSION_READY digest=' + 'a' * 64 + ' policy=' + 'b' * 64,
        'LAUNCH stdout=lanes_' + fixture.scope['run_id'] + '.stdout rc_file=ext/lanes_'
        + fixture.scope['run_id'] + '.rc cwd=~',
        'LAUNCH_ATTEMPT attempt=1',
        'REMOTE_DONE rc=0',
        'DONE rc=0 signal=ok',
    ]
    if mutation == 'two_attempts':
        events.insert(-1, 'LAUNCH_ATTEMPT attempt=1')
    elif mutation == 'no_lease':
        events = [event for event in events if not event.startswith('LEASE_OK')]
    elif mutation == 'wrong_pool':
        events = ['LEASE_OK pool=qwen' if event.startswith('LEASE_OK') else event for event in events]
    elif mutation == 'no_support':
        events = [event for event in events if not event.startswith('SUPPORT_VERSION_READY')]
    elif mutation == 'no_done':
        events = [event for event in events if not event.startswith('DONE ')]
    elif mutation == 'uncertainty':
        events.append('DONE rc=0 signal=effect_unknown')
    (fixture.state / (fixture.scope['run_id'] + '.log')).write_bytes(_log_text(fixture.scope, events).encode())
    _repin(monkeypatch, module, 'log', (fixture.state / (fixture.scope['run_id'] + '.log')).read_bytes())
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value).startswith('advertised_log_')
    assert incumbent.transport_calls == []


@pytest.mark.parametrize('mutation', ['missing_path', 'duplicate_path', 'missing_digest',
                                     'duplicate_digest', 'digest_not_adjacent'])
def test_qualify_refuses_a_missing_or_duplicate_advertisement(monkeypatch, module, tmp_path, mutation):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    path = fixture.scope['path']
    sha = fixture.scope['sha256']
    if mutation == 'missing_path':
        text = 'no advertisement here\n'
    elif mutation == 'duplicate_path':
        text = '`' + path + '`\n`' + path + '`\nsha256 `' + sha + '`\n'
    elif mutation == 'missing_digest':
        text = '`' + path + '`\nno digest line\n'
    elif mutation == 'duplicate_digest':
        text = '`' + path + '`\nsha256 `' + sha + '`\nsha256 `' + sha + '`\n'
    else:
        text = '`' + path + '`\n\nsome other line\nsha256 `' + sha + '`\n'
    stdout = text.encode()
    (fixture.lanes / (fixture.scope['run_id'] + '.remote.stdout')).write_bytes(stdout)
    receipt = json.loads(fixture.process)
    receipt['stdout_bytes'] = len(stdout)
    process = json.dumps(receipt).encode()
    (fixture.state / (fixture.scope['run_id'] + '.process.jsonl')).write_bytes(process)
    _repin(monkeypatch, module, 'stdout', stdout)
    _repin(monkeypatch, module, 'process', process)
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value).startswith('advertised_advertisement_')
    assert incumbent.transport_calls == []


@pytest.mark.parametrize('registry', [
    {},
    {FIXTURE_HOST: {'allowed_modes': ['qwen'], 'ssh_alias': 'fixture-alias'}},
    {FIXTURE_HOST: {'allowed_modes': ['minimax']}},
    {FIXTURE_HOST: {'allowed_modes': ['minimax'], 'ssh_alias': 'not a valid alias'}},
    {FIXTURE_HOST: {'allowed_modes': 'minimax', 'ssh_alias': 'fixture-alias'}},
])
def test_qualify_refuses_a_registry_that_does_not_admit_the_host(monkeypatch, module, tmp_path, registry):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    (fixture.root / 'hosts.json').write_bytes(json.dumps(registry).encode())
    with pytest.raises(ValueError) as excinfo:
        module.qualify(dict(fixture.scope))
    assert str(excinfo.value) == 'advertised_registry_mismatch'
    assert incumbent.transport_calls == []


# ---------------------------------------------------------------------------
# The local publication
# ---------------------------------------------------------------------------

def test_collect_reads_once_and_publishes_one_receipt(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    incumbent.transport_result = _remote_response(fixture.scope, b'fixture advertised bytes')
    destination = tmp_path / 'evidence' / 'recovery'
    receipt = module.collect(fixture.scope['run_id'], destination)
    assert len(incumbent.transport_calls) == 1
    alias, request = incumbent.transport_calls[0]
    assert alias == 'fixture-alias'
    assert request == fixture.scope
    assert receipt['state'] == 'COMPLETE'
    assert receipt['advertised_digest_matched'] is True
    assert receipt['recovery_basis'] == 'source_admitted_current_read'
    assert receipt['historical_producer_attestation'] is False
    assert receipt['historical_joint_seal'] == 'NOT_RETAINED'
    assert receipt['outcome_accepted'] is False
    assert receipt['original_operation_mutated'] is False
    assert receipt['execution_replayed'] is False
    assert receipt['files'][0]['sha256'] == fixture.scope['sha256']
    assert (destination / 'request.json').is_file()
    assert (destination / 'receipt.json').is_file()
    assert (destination / 'artifact.patch').read_bytes() == b'fixture advertised bytes'
    assert len(incumbent.published) == 1


def test_collect_never_retries_a_failed_read(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    incumbent.transport_error = ValueError('transport_unavailable')
    destination = tmp_path / 'evidence' / 'recovery'
    receipt = module.collect(fixture.scope['run_id'], destination)
    assert len(incumbent.transport_calls) == 1
    assert receipt['state'] == 'UNAVAILABLE'
    assert receipt['advertised_digest_matched'] is False
    assert receipt['failure_diagnostic'] == 'advertised_local_failure_unclassified'
    assert (destination / 'request.json').is_file()
    assert not (destination / 'artifact.patch').exists()


def test_collect_refuses_bytes_that_do_not_match_the_advertisement(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    response = json.loads(_remote_response(fixture.scope, b'fixture advertised bytes'))
    response['files'][0]['sha256'] = '0' * 64
    incumbent.transport_result = _canonical(response)
    destination = tmp_path / 'evidence' / 'recovery'
    receipt = module.collect(fixture.scope['run_id'], destination)
    assert len(incumbent.transport_calls) == 1
    assert receipt['state'] == 'UNAVAILABLE'
    assert receipt['advertised_digest_matched'] is False
    assert not (destination / 'artifact.patch').exists()


def test_collect_refuses_another_run_id(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    with pytest.raises(ValueError) as excinfo:
        module.collect('some-other-run', tmp_path / 'evidence' / 'recovery')
    assert str(excinfo.value) == 'advertised_run_id_mismatch'
    assert incumbent.transport_calls == []


def test_collect_refuses_when_the_evidence_changes_during_the_read(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    incumbent.transport_result = _remote_response(fixture.scope, b'fixture advertised bytes')
    state = {'reads': 0}

    def mutate(path, data):
        if path.name.endswith('.remote.stdout'):
            state['reads'] += 1
            # The first read qualifies the run; the second re-read happens
            # after the transport and must refuse the delivery.
            if state['reads'] == 2:
                return data + b'tampered'
        return data

    incumbent.mutate_local_file = mutate
    destination = tmp_path / 'evidence' / 'recovery'
    receipt = module.collect(fixture.scope['run_id'], destination)
    assert receipt['state'] == 'UNAVAILABLE'
    assert receipt['advertised_digest_matched'] is False
    assert receipt['failure_diagnostic'] == 'advertised_evidence_changed_stdout'
    assert not (destination / 'artifact.patch').exists()


# ---------------------------------------------------------------------------
# The incumbent is not widened
# ---------------------------------------------------------------------------

def test_the_incumbent_reader_still_refuses_paths_outside_tmp():
    reader = _import_incumbent('artifact_reader')
    assert reader.validate_path('/tmp/dir/file') == ['dir', 'file']
    for refused in ('/home/longr/lanes/file', '/tmp/dir/../file', '/tmp/dir/file/extra'):
        with pytest.raises(ValueError):
            reader.validate_path(refused)


def test_the_incumbent_process_validator_accepts_the_fixture_receipt_shape():
    incumbent = _import_incumbent('artifact_delivery')
    stdout = b'fixture stdout'
    receipt = _process_receipt(FIXTURE_RUN_ID, stdout)
    incumbent.validate_capsule_process(json.dumps(receipt).encode(), stdout, FIXTURE_RUN_ID)
    receipt['cleanup']['stdout_capture_complete'] = False
    with pytest.raises(ValueError):
        incumbent.validate_capsule_process(json.dumps(receipt).encode(), stdout, FIXTURE_RUN_ID)


def test_the_incumbent_transport_carries_the_advertised_schema_branch():
    paths = _incumbent_paths()
    if not paths:
        pytest.skip('no incumbent artifact_delivery.py on this host')
    text = (paths[0] / 'artifact_delivery.py').read_text(encoding='utf-8')
    if 'mastermind.source_admitted_advertised_artifact_read.v1' not in text:
        pytest.skip('the two-hunk plumbing patch is not applied in this tree')
    assert "code = advertised_recovery_source().decode('utf-8')" in text
    assert 'receipt = recovery.collect(args.run_id, args.destination)' in text


def test_destination_cannot_change_to_replay_failed_read(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    incumbent.transport_error = ValueError('transport_unavailable')
    destination = Path(module.DESTINATION)
    receipt = module.collect(fixture.scope['run_id'], destination)
    assert receipt['state'] == 'UNAVAILABLE'
    assert (destination / 'request.json').exists()
    with pytest.raises(FileExistsError):
        module.collect(fixture.scope['run_id'], destination)
    with pytest.raises(ValueError, match='advertised_destination_mismatch'):
        module.collect(fixture.scope['run_id'], tmp_path / 'different-output')
    assert len(incumbent.transport_calls) == 1


def test_destination_mismatch_refuses_before_qualification(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    monkeypatch.setattr(module, '_status', lambda _: pytest.fail('read after wrong destination'))
    with pytest.raises(ValueError, match='advertised_destination_mismatch'):
        module.collect(fixture.scope['run_id'], tmp_path / 'other')
    assert incumbent.transport_calls == []


def test_module_source_failure_does_not_fall_back(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    calls = []
    def denied(path, limit):
        calls.append(path)
        raise PermissionError('private detail must not cause another source read')
    monkeypatch.setattr(sys.modules['artifact_delivery'], 'local_file', denied)
    with pytest.raises(PermissionError):
        module.code_for_request(dict(fixture.scope), expected_hash=_digest(_module_path().read_bytes()))
    assert calls == [fixture.root / MODULE_NAME]
    assert incumbent.transport_calls == []


def test_real_incumbent_publication_retains_one_attempt_and_original_metadata(monkeypatch, module, secure_tmp):
    real = _import_incumbent('artifact_delivery')
    fixture, inert = _install_local(monkeypatch, module, secure_tmp)
    shim = sys.modules['artifact_delivery']
    for name in ('local_file', 'reserve_destination', 'write_exclusive', 'verify_delivered', 'publish_receipt'):
        monkeypatch.setattr(shim, name, getattr(real, name))
    monkeypatch.setattr(real, 'DESTINATION_ROOT', secure_tmp)
    destination = Path(module.DESTINATION)
    destination.parent.mkdir(mode=0o700)
    inert.transport_result = _remote_response(fixture.scope, b'fixture advertised bytes')
    original = {name: path.read_bytes() for name, path in module._evidence_paths(fixture.scope['run_id']).items()}
    receipt = module.collect(fixture.scope['run_id'], destination)
    assert receipt['state'] == 'COMPLETE'
    published = json.loads((destination / 'receipt.json').read_bytes())
    assert published == receipt
    assert (destination / 'request.json').is_file()
    assert published['historical_producer_attestation'] is False
    assert published['original_operation_mutated'] is False
    assert published['outcome_accepted'] is False
    assert {name: path.read_bytes() for name, path in module._evidence_paths(fixture.scope['run_id']).items()} == original
    with pytest.raises(FileExistsError):
        module.collect(fixture.scope['run_id'], destination)
    with pytest.raises(ValueError, match='advertised_destination_mismatch'):
        module.collect(fixture.scope['run_id'], destination.with_name('alternate'))
    assert len(inert.transport_calls) == 1


def test_metadata_paths_use_incumbent_state_not_remote_stdout_directory(monkeypatch, module, tmp_path):
    fixture, _ = _install_local(monkeypatch, module, tmp_path)
    paths = module._evidence_paths(fixture.scope['run_id'])
    assert paths['stdout'].parent == fixture.root / 'lanes'
    assert paths['process'].parent == paths['provider'].parent == fixture.root / 'state' / 'remote_sub'


def test_inert_source_body_mutation_refuses_before_transport(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    path = fixture.root / MODULE_NAME
    path.write_bytes(path.read_bytes() + b'\n# changed inert source body\n')
    with pytest.raises(ValueError, match='advertised_remote_source_changed'):
        module.qualify(dict(fixture.scope))
    with pytest.raises(ValueError, match='advertised_remote_source_changed'):
        module.code_for_request(dict(fixture.scope), expected_hash=_digest(_module_path().read_bytes()))
    assert incumbent.transport_calls == []
    assert not Path(module.DESTINATION).exists()


def test_source_drift_between_qualification_and_transport_cannot_send(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    original_verify = _Chain.verify
    def mutate_after_qualification(chain):
        original_verify(chain)
        path = fixture.root / MODULE_NAME
        path.write_bytes(path.read_bytes() + b'\n# source drift before transport\n')
    monkeypatch.setattr(_Chain, 'verify', mutate_after_qualification)
    def checked_transport(alias, request):
        # Exercise the real dispatch seam before any inert simulated send.
        module.code_for_request(request, expected_hash=sys.modules['artifact_delivery'].ADVERTISED_RECOVERY_SOURCE_SHA256)
        return incumbent.transport(alias, request)
    monkeypatch.setattr(sys.modules['artifact_delivery'], 'transport', checked_transport)
    with pytest.raises(ValueError, match='advertised_remote_source_changed'):
        module.collect(fixture.scope['run_id'], module.DESTINATION)
    assert incumbent.transport_calls == []
    assert (Path(module.DESTINATION) / 'request.json').exists()
    assert not (Path(module.DESTINATION) / 'artifact.patch').exists()


def test_caller_hash_cannot_replace_incumbent_generation_pin(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    path = fixture.root / MODULE_NAME
    path.write_bytes(path.read_bytes() + b'\n# alternate source\n')
    with pytest.raises(ValueError, match='advertised_remote_source_hash_unqualified'):
        module.code_for_request(dict(fixture.scope), expected_hash=_digest(path.read_bytes()))
    assert incumbent.transport_calls == []


def test_transport_pin_matches_exact_shipped_module():
    delivery = _import_incumbent('artifact_delivery')
    assert delivery.ADVERTISED_RECOVERY_SOURCE_SHA256 == _digest(_module_path().read_bytes())


def test_real_dispatcher_refuses_changed_source_before_ssh(monkeypatch, module, tmp_path):
    real = _import_incumbent('artifact_delivery')
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    monkeypatch.setattr(real, 'HERE', fixture.root)
    monkeypatch.setattr(real, 'local_file', incumbent.local_file)
    monkeypatch.setattr(real.subprocess, 'Popen', lambda *a, **k: pytest.fail('unqualified SSH launch'))
    path = fixture.root / MODULE_NAME
    path.write_bytes(path.read_bytes() + b'\n# inert unreviewed body\n')
    with pytest.raises(ValueError, match='advertised_remote_source_changed'):
        real.transport('fixture-alias', dict(fixture.scope))
    assert incumbent.transport_calls == []


def test_transport_source_bytes_are_not_reread_after_hash_check(monkeypatch, module, tmp_path):
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    raw = _module_path().read_bytes()
    calls = []
    def once(path, limit):
        calls.append(path)
        assert len(calls) == 1, 'second unqualified source read'
        return raw
    monkeypatch.setattr(sys.modules['artifact_delivery'], 'local_file', once)
    code = module.code_for_request(dict(fixture.scope), expected_hash=_digest(raw))
    assert code.encode() == raw
    assert calls == [fixture.root / MODULE_NAME]


def test_real_dispatcher_never_imports_unchecked_remote_module(monkeypatch, module, tmp_path):
    real = _import_incumbent('artifact_delivery')
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    monkeypatch.setattr(real, 'HERE', fixture.root)
    monkeypatch.setattr(real, 'local_file', incumbent.local_file)
    monkeypatch.setattr(real.subprocess, 'Popen', lambda *a, **k: pytest.fail('unqualified SSH launch'))
    # The source retains the old function names but would have a top-level
    # side effect and a lying validator if imported. The trusted dispatcher
    # must reject its bytes without consulting either function.
    marker = fixture.root / 'must-not-exist'
    hostile = ("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n"
               "def remote_main(): pass\ndef remote_read(): pass\n"
               "def code_for_request(*a, **k): return 'forged remote code'\n")
    (fixture.root / MODULE_NAME).write_text(hostile)
    with pytest.raises(ValueError, match='advertised_remote_source_changed'):
        real.transport('fixture-alias', dict(fixture.scope))
    assert not marker.exists()


def test_actual_main_refuses_modified_module_before_import_or_ssh(monkeypatch, module, tmp_path, capsys):
    real = _import_incumbent('artifact_delivery')
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    monkeypatch.setattr(real, 'HERE', fixture.root)
    monkeypatch.setattr(real, 'local_file', incumbent.local_file)
    monkeypatch.setattr(real.subprocess, 'Popen', lambda *a, **k: pytest.fail('unqualified SSH launch'))
    marker = fixture.root / 'main-must-not-import'
    hostile = ("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n"
               "def remote_main(): pass\ndef remote_read(): pass\n"
               "def collect(*a, **k): return {'state':'COMPLETE'}\n")
    (fixture.root / MODULE_NAME).write_text(hostile)
    monkeypatch.setattr(sys, 'argv', ['artifact_delivery.py', '--capsule-current',
        'mm-u0-revision-lens-component-20261105-root', '--destination', str(fixture.root / 'output')])
    assert real.main() == 75
    assert json.loads(capsys.readouterr().out)['state'] == 'REFUSED'
    assert not marker.exists()
    assert not (fixture.root / 'output').exists()
    assert incumbent.transport_calls == []


def test_checked_bundle_loader_ignores_cached_unchecked_module(monkeypatch, module, tmp_path):
    real = _import_incumbent('artifact_delivery')
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    monkeypatch.setattr(real, 'HERE', fixture.root)
    monkeypatch.setattr(real, 'local_file', incumbent.local_file)
    forged = types.SimpleNamespace(collect=lambda *a, **k: pytest.fail('cached unchecked module used'))
    monkeypatch.setitem(sys.modules, 'original_advertised_artifact', forged)
    loaded = real.advertised_recovery_module()
    assert loaded is not forged
    assert loaded.SCOPE['run_id'] == 'mm-u0-revision-lens-component-20261105-root'
    assert loaded._delivery().transport is real.transport
    assert loaded._delivery().advertised_recovery_source is real.advertised_recovery_source
    assert incumbent.transport_calls == []


def test_checked_bundle_loader_executes_one_checked_snapshot(monkeypatch, module, tmp_path):
    real = _import_incumbent('artifact_delivery')
    fixture, incumbent = _install_local(monkeypatch, module, tmp_path)
    monkeypatch.setattr(real, 'HERE', fixture.root)
    original = _module_path().read_bytes()
    path = fixture.root / MODULE_NAME
    marker = fixture.root / 'second-read-must-not-execute'
    calls = []
    def read_then_replace(source, limit):
        calls.append(source)
        assert len(calls) == 1
        path.write_text("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n")
        return original
    monkeypatch.setattr(real, 'local_file', read_then_replace)
    loaded = real.advertised_recovery_module()
    assert loaded.SCOPE['run_id'] == 'mm-u0-revision-lens-component-20261105-root'
    assert not marker.exists()
    assert calls == [path]
