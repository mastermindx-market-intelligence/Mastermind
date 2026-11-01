"""Focused tests for the executor-owned held_yaml context in paid_yaml_runtime.

Positive real PyYAML 6.0.3 semantics -- in-process and in a fresh
``python3 -I -S -B`` child -- plus the sealed-custody refusals: pinned-asset
tamper, member inventory metadata, ambient/binary/unknown namespace handling,
owner-check drift, partial import, foreign replacement preservation and exact
cleanup.  The Root-only loader is asserted unchanged by AST comparison
against the pinned original source below.

Pinned assets and runtime are loaded only from this repository's fixed
public candidate directory. Missing or drifted inputs fail the tests.
"""

import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import zipfile

import pytest

ZIP_SHA256 = '1d6b5f7c42bc620557966d5cc6ca1933a7a12670658a7604676f0aebc26a3131'
PROVENANCE_SHA256 = '7883d48401f41d9470660bfd6114e6199002da8e142c1e7d196d9da4e4e17f64'
ARTIFACT_SHA256 = 'fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0'
CANDIDATE_RELATIVE = Path('ops') / 'native_fabric' / 'quota_continuity' / 'candidate'
RUNTIME_NAME = 'paid_yaml_runtime'
TEST_MODULE_NAME = 'paid_yaml_runtime_under_test'
ORIGIN_LABEL = 'held-pyyaml-6.0.3'


# The pinned original paid_yaml_runtime.py source (Root-only loader part).
# The shipped module must keep `_read` and `load_yaml` AST-identical to it.
ORIGINAL_RUNTIME_SOURCE = '''\
"""Load only the reviewed pure PyYAML closure in the sealed paid release.

No site loading, ambient package fallback, C extension or global path addition.
The lock-pinned wheel is source provenance, not a runtime dependency installer.
"""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import zipfile
import zipimport

ZIP_SHA256 = '1d6b5f7c42bc620557966d5cc6ca1933a7a12670658a7604676f0aebc26a3131'
PROVENANCE_SHA256 = '7883d48401f41d9470660bfd6114e6199002da8e142c1e7d196d9da4e4e17f64'
ARTIFACT_SHA256 = 'fc09d0aa354569bc501d4e787133afc08552722d3ab34836a80547331bb5d4a0'
HERE = Path(__file__).resolve().parent
_loaded = None


def _read(name, expected):
    dfd = os.open(HERE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        directory = os.fstat(dfd)
        if directory.st_uid != 0 or directory.st_mode & 0o022:
            raise ValueError('paid_yaml_source_refused')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
        try:
            before = os.fstat(fd)
            identity = lambda s: (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,
                                  s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != 0
                    or before.st_mode & 0o022 or before.st_nlink != 1
                    or not 0 < before.st_size <= 1048576):
                raise ValueError('paid_yaml_source_refused')
            data = bytearray()
            while len(data) <= before.st_size:
                part = os.read(fd, min(65536,before.st_size+1-len(data)))
                if not part: break
                data.extend(part)
            if (len(data) != before.st_size or identity(before) != identity(os.fstat(fd))
                    or identity(before) != identity(os.stat(name,dir_fd=dfd,follow_symlinks=False))
                    or (directory.st_dev,directory.st_ino) != (HERE.lstat().st_dev,HERE.lstat().st_ino)
                    or hashlib.sha256(data).hexdigest() != expected):
                raise ValueError('paid_yaml_source_refused')
            return bytes(data)
        finally: os.close(fd)
    finally: os.close(dfd)


def load_yaml():
    global _loaded
    archive = _read('paid_pyyaml_6_0_3.zip',ZIP_SHA256)
    provenance = json.loads(_read('paid_pyyaml_provenance.json',PROVENANCE_SHA256))
    if (provenance['package'] != 'PyYAML' or provenance['version'] != '6.0.3'
            or provenance['artifact_sha256'] != ARTIFACT_SHA256):
        raise ValueError('paid_yaml_source_refused')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if len(z.namelist()) != len(set(z.namelist())) or set(z.namelist()) != set(provenance['files']):
            raise ValueError('paid_yaml_source_refused')
        for name, item in provenance['files'].items():
            raw = z.read(name)
            if (name not in {'LICENSE','METADATA'} and not (name.startswith('yaml/') and name.endswith('.py'))
                    or len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']):
                raise ValueError('paid_yaml_source_refused')
    if _loaded is not None:
        if sys.modules.get('yaml') is not _loaded:
            raise ValueError('paid_yaml_ambient_refused')
        return _loaded
    if any(name == 'yaml' or name.startswith('yaml.') for name in sys.modules):
        raise ValueError('paid_yaml_ambient_refused')
    # Only this fixed verified archive supplies the package search location.
    importer = zipimport.zipimporter(str(HERE/'paid_pyyaml_6_0_3.zip'))
    spec = importer.find_spec('yaml')
    module = importlib.util.module_from_spec(spec)
    sys.modules['yaml'] = module
    try:
        spec.loader.exec_module(module)
        if module.__version__ != '6.0.3' or module.__with_libyaml__ is not False:
            raise ValueError('paid_yaml_source_refused')
        # Revalidate the same immutable files after zipimport has read them.
        _read('paid_pyyaml_6_0_3.zip',ZIP_SHA256)
        _read('paid_pyyaml_provenance.json',PROVENANCE_SHA256)
    except BaseException:
        for name in list(sys.modules):
            if name == 'yaml' or name.startswith('yaml.'): del sys.modules[name]
        raise
    _loaded = module
    return module
\
'''


def _yaml_names():
    return [n for n in sys.modules
            if n == 'yaml' or n.startswith('yaml.') or n == '_yaml']


@pytest.fixture(scope='session')
def assets():
    root = Path(__file__).resolve().parents[1] / CANDIDATE_RELATIVE
    archive = (root / 'paid_pyyaml_6_0_3.zip').read_bytes()
    provenance = (root / 'paid_pyyaml_provenance.json').read_bytes()
    assert hashlib.sha256(archive).hexdigest() == ZIP_SHA256
    assert hashlib.sha256(provenance).hexdigest() == PROVENANCE_SHA256
    return SimpleNamespace(archive=archive, provenance=provenance, root=root)


def _runtime_path(root):
    return root / (RUNTIME_NAME + '.py')


@pytest.fixture(scope='session')
def runtime(assets):
    path = _runtime_path(assets.root)
    existing = sys.modules.get(TEST_MODULE_NAME)
    if existing is not None and getattr(existing, '__file__', None) == str(path):
        return existing
    spec = importlib.util.spec_from_file_location(TEST_MODULE_NAME, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[TEST_MODULE_NAME] = module
    return module


@pytest.fixture
def clean_namespace():
    """Require a yaml-free namespace and restore it afterwards."""
    preexisting = _yaml_names()
    if preexisting:
        pytest.skip('pre-existing yaml namespace in the pytest process: %s'
                    % sorted(preexisting))
    meta_before = list(sys.meta_path)
    yield
    for name in _yaml_names():
        del sys.modules[name]
    for finder in list(sys.meta_path):
        if not any(finder is kept for kept in meta_before):
            sys.meta_path.remove(finder)


def _members_of(archive):
    with zipfile.ZipFile(io.BytesIO(archive)) as handle:
        return {name: handle.read(name) for name in handle.namelist()}


def _rebuild_zip(members, duplicate=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as new:
        for name in sorted(members):
            new.writestr(name, members[name])
            if duplicate == name:
                new.writestr(name, members[name])
    return buffer.getvalue()


def _provenance_dict(assets):
    return json.loads(assets.provenance.decode('utf-8'))


# ---------------------------------------------------------------------------
# Positive: real pure PyYAML 6.0.3 semantics served only from the held bytes.
# ---------------------------------------------------------------------------

def test_positive_real_semantics_and_exact_lifecycle(runtime, assets,
                                                     clean_namespace):
    calls = []

    def check():
        calls.append(1)
        return True

    assert runtime._loaded is None
    context = runtime.held_yaml(assets.archive, assets.provenance, check)
    with context as y:
        assert y.__version__ == '6.0.3'
        assert y.__with_libyaml__ is False
        assert y.__spec__.origin.startswith(ORIGIN_LABEL + '://')
        assert getattr(y, '__file__', None) is None
        assert list(y.__path__) == []
        assert sys.modules['yaml'] is y
        finder = y.__spec__.loader
        assert sys.meta_path[0] is finder
        assert importlib.util.find_spec('yaml').origin.startswith(ORIGIN_LABEL + '://')
        # Every pinned pure module was served by the one held finder at a
        # virtual origin; the binary wrapper stays a recorded partial import.
        installed = {n for n in sys.modules
                     if n == 'yaml' or n.startswith('yaml.')}
        assert installed == set(runtime._HELD_MODULE_FULLNAMES) - {'yaml.cyaml'}
        assert all(sys.modules[n].__spec__.loader is finder for n in installed)
        assert all(sys.modules[n].__spec__.origin.startswith(ORIGIN_LABEL + '://')
                   for n in installed)
        owned = finder.owned()
        assert sorted(owned) == sorted(runtime._HELD_MODULE_FULLNAMES)
        assert 'yaml.cyaml' not in sys.modules
        # Real PyYAML semantics, not a finite fake parser.
        assert y.safe_load('p: {q: [1, 2], r: null}') == {'p': {'q': [1, 2], 'r': None}}
        roundtrip = y.safe_load(y.safe_dump({'k': [True, None, 'v', 3.5]}))
        assert roundtrip == {'k': [True, None, 'v', 3.5]}
        anchored = y.safe_load('x: &a [1, 2]\ny: *a\n')
        assert anchored['y'] == [1, 2] and anchored['y'] is anchored['x']
        assert y.safe_load('b: &b {k: 1}\ni:\n  <<: *b\n  k: 2\n') == \
            {'b': {'k': 1}, 'i': {'k': 2}}
        # This pinned upstream 6.0.3 wheel resolves duplicate plain keys
        # last-one-wins (it ships no check_mapping_key); the tests assert the
        # real pinned semantics, not a later distribution's policy.
        assert y.safe_load('a: 1\na: 2\n') == {'a': 2}
        with pytest.raises(y.scanner.ScannerError):
            y.safe_load('a: b: c\n')
        with pytest.raises(y.error.YAMLError):
            y.safe_load('a:\n  - b\n c: 1\n')
        with pytest.raises(y.error.YAMLError):
            y.safe_load('!!python/object/apply:os.system [echo no]')
        # Unknown and compiled-extension names are refused before any
        # ambient fallback.
        for bad in ('yaml._yaml', 'yaml.unknown_name', '_yaml'):
            with pytest.raises(ModuleNotFoundError):
                importlib.import_module(bad)
        assert '_yaml' not in sys.modules and 'yaml._yaml' not in sys.modules
        # enter + 17 module executions (cyaml included, partial) + attestation
        assert len(calls) == 19
    assert len(calls) == 20  # the exit owner check
    assert not _yaml_names()
    assert runtime._loaded is None
    assert not [kept for kept in sys.meta_path if kept is finder]


def test_positive_isolated_interpreter_journey(runtime, assets):
    """The real positive journey inside a fresh ``-I -S -B`` compiler child."""
    path = _runtime_path(assets.root)
    command = [sys.executable, '-I', '-S', '-B', '-c', ISOLATED_DRIVER,
               str(path),
               str(assets.root / 'paid_pyyaml_6_0_3.zip'),
               str(assets.root / 'paid_pyyaml_provenance.json')]
    completed = subprocess.run(command, capture_output=True, text=True,
                               timeout=180)
    assert completed.returncode == 0, completed.stderr
    assert 'Traceback' not in completed.stderr
    assert 'HELD_YAML_ISOLATED_OK calls=20' in completed.stdout


def test_repeated_entries_are_independent(runtime, assets, clean_namespace):
    with runtime.held_yaml(assets.archive, assets.provenance, lambda: True) as first:
        assert first.__version__ == '6.0.3'
    assert not _yaml_names()
    with runtime.held_yaml(assets.archive, assets.provenance, lambda: True) as second:
        assert second is not first
    assert not _yaml_names()
    assert runtime._loaded is None


def test_ambient_finder_is_not_consulted(runtime, assets, clean_namespace):
    class AmbientFinder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == 'yaml' or fullname.startswith('yaml.') or fullname == '_yaml':
                raise AssertionError('ambient yaml resolution attempted')
            return None

    ambient = AmbientFinder()
    sys.meta_path.insert(0, ambient)
    try:
        with runtime.held_yaml(assets.archive, assets.provenance, lambda: None) as y:
            assert y.__spec__.origin.startswith(ORIGIN_LABEL + '://')
            for name in ('yaml.unknown_name', 'yaml._yaml', '_yaml'):
                with pytest.raises(ModuleNotFoundError):
                    importlib.import_module(name)
        assert sys.meta_path[0] is ambient
        assert not _yaml_names()
    finally:
        sys.meta_path.remove(ambient)


def test_held_path_avoids_zipimport_sys_path_and_root_custody(runtime, assets,
                                                              clean_namespace,
                                                              monkeypatch):
    def refused_zipimporter(*args, **kwargs):
        raise AssertionError('held path must not use zipimport')

    def refused_read(name, expected):
        raise AssertionError('held path must not read Root custody files: %s' % name)

    monkeypatch.setattr(runtime.zipimport, 'zipimporter', refused_zipimporter)
    monkeypatch.setattr(runtime, '_read', refused_read)
    path_before = list(sys.path)
    with runtime.held_yaml(assets.archive, assets.provenance, lambda: True) as y:
        assert getattr(y, '__file__', None) is None
        assert y.__spec__.origin.startswith(ORIGIN_LABEL + '://')
    assert list(sys.path) == path_before
    assert runtime._loaded is None


def test_held_yaml_ignores_the_root_cache(runtime, assets, clean_namespace,
                                          monkeypatch):
    monkeypatch.setattr(runtime, '_loaded', object())
    with runtime.held_yaml(assets.archive, assets.provenance, lambda: True) as y:
        assert y.__version__ == '6.0.3'
    assert not _yaml_names()


def test_context_reuse_is_refused(runtime, assets, clean_namespace):
    context = runtime.held_yaml(assets.archive, assets.provenance, lambda: True)
    with context:
        pass
    with pytest.raises(ValueError, match='paid_yaml_state_refused'):
        with context:
            pass


def test_held_yaml_call_installs_nothing(runtime, assets, clean_namespace):
    meta_before = list(sys.meta_path)
    context = runtime.held_yaml(assets.archive, assets.provenance, lambda: True)
    assert list(sys.meta_path) == meta_before
    assert not _yaml_names()
    provenance = runtime._held_provenance(assets.provenance)
    assert provenance['package'] == 'PyYAML'
    assert provenance['version'] == '6.0.3'
    assert provenance['artifact_sha256'] == ARTIFACT_SHA256
    assert provenance['zip_sha256'] == ZIP_SHA256
    assert provenance['excluded_binary_extensions'] is True
    table = runtime._held_member_table(assets.archive, provenance)
    assert len(table) == 17
    assert sorted(table) == sorted(runtime._HELD_MODULE_FULLNAMES)
    assert all(isinstance(raw, bytes) for raw in table.values())
    pinned = _members_of(assets.archive)
    for fullname, member in runtime._HELD_MEMBER_OF.items():
        assert table[fullname] == pinned[member]


def test_pinned_member_constants(runtime):
    assert len(runtime._HELD_PACKAGE_MEMBERS) == 19
    assert len(runtime._HELD_MODULE_FULLNAMES) == 17
    assert runtime._HELD_PACKAGE_MEMBERS == tuple(sorted(runtime._HELD_PACKAGE_MEMBERS))
    assert [m for m in runtime._HELD_PACKAGE_MEMBERS if m.endswith('.py')] == \
        [runtime._HELD_MEMBER_OF[n] for n in runtime._HELD_MODULE_FULLNAMES]
    assert not [m for m in runtime._HELD_PACKAGE_MEMBERS
                if m.endswith(runtime._HELD_BINARY_SUFFIXES)]
    assert runtime._HELD_MEMBER_OF['yaml'] == 'yaml/__init__.py'


# ---------------------------------------------------------------------------
# Pinned-asset gates on the public constructor.
# ---------------------------------------------------------------------------

def test_wrong_archive_bytes_refused_with_no_effect(runtime, assets,
                                                    clean_namespace):
    tampered = bytearray(assets.archive)
    tampered[len(tampered) // 2] ^= 0x01
    meta_before = list(sys.meta_path)
    modules_before = set(sys.modules)
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime.held_yaml(bytes(tampered), assets.provenance, lambda: True)
    assert set(sys.modules) == modules_before
    assert list(sys.meta_path) == meta_before
    assert runtime._loaded is None


def test_wrong_provenance_bytes_refused(runtime, assets, clean_namespace):
    tampered = bytearray(assets.provenance)
    tampered[-2] ^= 0x01
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime.held_yaml(assets.archive, bytes(tampered), lambda: True)


def test_non_bytes_inputs_refused(runtime, assets):
    for archive, provenance in ((bytearray(assets.archive), assets.provenance),
                                (memoryview(assets.archive), assets.provenance),
                                (str(assets.archive), assets.provenance),
                                (assets.archive, bytearray(assets.provenance)),
                                (assets.archive, memoryview(assets.provenance))):
        with pytest.raises(ValueError, match='paid_yaml_source_refused'):
            runtime.held_yaml(archive, provenance, lambda: True)


def test_missing_owner_callback_refused(runtime, assets, clean_namespace):
    context = runtime.held_yaml(assets.archive, assets.provenance, None)
    with pytest.raises(ValueError, match='paid_yaml_owner_refused'):
        context.__enter__()
    assert not _yaml_names()


# ---------------------------------------------------------------------------
# Member inventory metadata (consistent crafted pairs, unit level).
# ---------------------------------------------------------------------------

def test_missing_member_refused(runtime, assets):
    members = _members_of(assets.archive)
    provenance = _provenance_dict(assets)
    dropped = 'yaml/resolver.py'
    members.pop(dropped)
    provenance['files'].pop(dropped)
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime._held_member_table(_rebuild_zip(members), provenance)


def test_extra_member_refused(runtime, assets):
    members = _members_of(assets.archive)
    provenance = _provenance_dict(assets)
    extra = 'yaml/extra_helper.py'
    members[extra] = b'VALUE = 1\n'
    provenance['files'][extra] = {
        'bytes': len(members[extra]),
        'sha256': hashlib.sha256(members[extra]).hexdigest(),
    }
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime._held_member_table(_rebuild_zip(members), provenance)


@pytest.mark.filterwarnings('ignore:Duplicate name')
def test_duplicate_member_refused(runtime, assets):
    members = _members_of(assets.archive)
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime._held_member_table(
            _rebuild_zip(members, duplicate='yaml/scanner.py'),
            _provenance_dict(assets))


def test_binary_member_refused(runtime, assets):
    members = _members_of(assets.archive)
    provenance = _provenance_dict(assets)
    binary = 'yaml/_blocked.so'
    members[binary] = b'\x7fELFfake'
    provenance['files'][binary] = {
        'bytes': len(members[binary]),
        'sha256': hashlib.sha256(members[binary]).hexdigest(),
    }
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime._held_member_table(_rebuild_zip(members), provenance)


def test_member_hash_mismatch_refused(runtime, assets):
    members = _members_of(assets.archive)
    victim = 'yaml/tokens.py'
    members[victim] = members[victim][:-1] + bytes([members[victim][-1] ^ 0x01])
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime._held_member_table(_rebuild_zip(members), _provenance_dict(assets))


def test_member_length_mismatch_refused(runtime, assets):
    provenance = _provenance_dict(assets)
    victim = 'yaml/parser.py'
    provenance['files'][victim]['bytes'] += 1
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime._held_member_table(assets.archive, provenance)


def test_wrong_member_count_refused(runtime, assets):
    provenance = _provenance_dict(assets)
    provenance['files'].pop('METADATA')
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime._held_member_table(
            _rebuild_zip(_members_of(assets.archive)), provenance)


def test_unparsable_provenance_refused(runtime, assets):
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime._held_provenance(b'not json')


# ---------------------------------------------------------------------------
# Owner-check drift, exceptions and interrupts.
# ---------------------------------------------------------------------------

def test_owner_false_at_enter_refused(runtime, assets, clean_namespace):
    calls = []

    def check():
        calls.append(1)
        return False

    context = runtime.held_yaml(assets.archive, assets.provenance, check)
    with pytest.raises(ValueError, match='paid_yaml_owner_refused'):
        context.__enter__()
    assert calls == [1]
    assert not _yaml_names()
    meta_before = list(sys.meta_path)
    assert list(sys.meta_path) == meta_before


def test_owner_drift_mid_import_cleans_partial_import(runtime, assets,
                                                      clean_namespace):
    observed = {}
    calls = []

    def check():
        calls.append(1)
        if len(calls) == 6:
            observed['executing'] = sorted(_yaml_names())
            return False
        return True

    context = runtime.held_yaml(assets.archive, assets.provenance, check)
    with pytest.raises(ValueError, match='paid_yaml_owner_refused'):
        context.__enter__()
    assert len(calls) == 6
    # The refusal happened mid package import: modules had already been
    # executed and recorded, and the partial import was cleaned exactly.
    assert observed['executing']
    assert 'yaml' in observed['executing']
    assert not _yaml_names()


def test_owner_callback_exception_propagates_with_cleanup(runtime, assets,
                                                          clean_namespace):
    class CustodyProbe(Exception):
        pass

    calls = []

    def check():
        calls.append(1)
        if len(calls) == 4:
            raise CustodyProbe('custody probe failed')
        return True

    context = runtime.held_yaml(assets.archive, assets.provenance, check)
    with pytest.raises(CustodyProbe):
        context.__enter__()
    assert len(calls) == 4
    assert not _yaml_names()


def test_body_interrupt_propagates_with_cleanup(runtime, assets,
                                                clean_namespace):
    with pytest.raises(KeyboardInterrupt):
        with runtime.held_yaml(assets.archive, assets.provenance,
                               lambda: True) as y:
            assert y.__version__ == '6.0.3'
            assert len(y.__spec__.loader.owned()) == 17
            raise KeyboardInterrupt
    assert not _yaml_names()


def test_body_exception_propagates_with_cleanup(runtime, assets,
                                                clean_namespace):
    class BodyError(Exception):
        pass

    with pytest.raises(BodyError):
        with runtime.held_yaml(assets.archive, assets.provenance, lambda: True):
            raise BodyError('body failure')
    assert not _yaml_names()


def test_exit_owner_interrupt_still_cleans_exactly(runtime, assets,
                                                   clean_namespace):
    calls = []

    def check():
        calls.append(1)
        if len(calls) == 20:
            raise KeyboardInterrupt
        return True

    with pytest.raises(KeyboardInterrupt):
        with runtime.held_yaml(assets.archive, assets.provenance, check) as y:
            assert len(calls) == 19
    assert len(calls) == 20
    assert not _yaml_names()


# ---------------------------------------------------------------------------
# Namespace and finder replacement: preserve foreign state, refuse.
# ---------------------------------------------------------------------------

def test_foreign_replacement_preserved_and_refused(runtime, assets,
                                                   clean_namespace):
    replacement = ModuleType('yaml')
    with pytest.raises(ValueError, match='paid_yaml_ambient_refused'):
        with runtime.held_yaml(assets.archive, assets.provenance,
                               lambda: True) as y:
            # A foreign object occupying the owned package slot mid-flight.
            sys.modules['yaml'] = replacement
    assert sys.modules['yaml'] is replacement
    assert not [n for n in sys.modules if n.startswith('yaml.')]
    assert not [kept for kept in sys.meta_path if kept is y.__spec__.loader]
    del sys.modules['yaml']


@pytest.mark.parametrize('name', ['yaml', 'yaml.scanner', '_yaml'])
def test_preexisting_namespace_refused_and_preserved(runtime, assets,
                                                     clean_namespace, name):
    foreign = ModuleType(name)
    sys.modules[name] = foreign
    try:
        meta_before = list(sys.meta_path)
        with pytest.raises(ValueError, match='paid_yaml_ambient_refused'):
            with runtime.held_yaml(assets.archive, assets.provenance,
                                   lambda: True):
                pass
        assert sys.modules.get(name) is foreign
        assert list(sys.meta_path) == meta_before
    finally:
        sys.modules.pop(name, None)


def test_finder_displacement_refused_but_cleanup_exact(runtime, assets,
                                                       clean_namespace):
    with pytest.raises(ValueError, match='paid_yaml_ambient_refused'):
        with runtime.held_yaml(assets.archive, assets.provenance,
                               lambda: True) as y:
            sys.meta_path.remove(y.__spec__.loader)
    assert not _yaml_names()
    assert not [kept for kept in sys.meta_path
                if getattr(kept, '__module__', '') == 'paid_yaml_runtime'
                and kept.__class__.__name__ == '_HeldYamlFinder']


# ---------------------------------------------------------------------------
# Root-only loader preservation.
# ---------------------------------------------------------------------------

def test_root_loader_ast_constants_and_custody_preserved(runtime):
    original = ast.parse(ORIGINAL_RUNTIME_SOURCE)
    shipped = ast.parse(Path(runtime.__file__).read_text(encoding='utf-8'))
    shipped_functions = {node.name: node for node in shipped.body
                         if isinstance(node, ast.FunctionDef)}
    compared = []
    for node in original.body:
        if isinstance(node, ast.FunctionDef):
            assert node.name in shipped_functions
            assert ast.dump(shipped_functions[node.name]) == ast.dump(node), \
                'Root function AST changed: %s' % node.name
            compared.append(node.name)
    assert compared == ['_read', 'load_yaml']
    assert runtime.ZIP_SHA256 == ZIP_SHA256
    assert runtime.PROVENANCE_SHA256 == PROVENANCE_SHA256
    assert runtime.ARTIFACT_SHA256 == ARTIFACT_SHA256
    assert runtime._loaded is None
    # Root-only custody still refuses outside a root-owned directory.
    if os.geteuid() == 0:
        pytest.skip('running as root: non-Root custody refusal not observable')
    here = Path(runtime.__file__).resolve().parent
    if here.stat().st_uid == 0:
        pytest.skip('runtime directory is root-owned on this host')
    # Custody refusal must preserve any ambient namespace, including an empty one.
    namespace_before = {name: sys.modules[name] for name in _yaml_names()}
    with pytest.raises(ValueError, match='paid_yaml_source_refused'):
        runtime.load_yaml()
    assert runtime._loaded is None
    namespace_after = {name: sys.modules[name] for name in _yaml_names()}
    assert namespace_after.keys() == namespace_before.keys()
    assert all(namespace_after[name] is module
               for name, module in namespace_before.items())


# ---------------------------------------------------------------------------
# Isolated -I -S -B driver.
# ---------------------------------------------------------------------------

ISOLATED_DRIVER = """\
import hashlib
import importlib.util
import sys

runtime_path, archive_path, provenance_path = sys.argv[1:4]
with open(archive_path, 'rb') as handle:
    archive = handle.read()
with open(provenance_path, 'rb') as handle:
    provenance = handle.read()
assert hashlib.sha256(archive).hexdigest() == '1d6b5f7c42bc620557966d5cc6ca1933a7a12670658a7604676f0aebc26a3131'
assert hashlib.sha256(provenance).hexdigest() == '7883d48401f41d9470660bfd6114e6199002da8e142c1e7d196d9da4e4e17f64'
# The isolated child has no ambient PyYAML before the held context installs one.
assert importlib.util.find_spec('yaml') is None
assert not any(n == 'yaml' or n.startswith('yaml.') or n == '_yaml' for n in sys.modules)
spec = importlib.util.spec_from_file_location('paid_yaml_runtime', runtime_path)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
calls = []


def check():
    calls.append(1)
    return True


with runtime.held_yaml(archive, provenance, check) as y:
    assert y.__version__ == '6.0.3'
    assert y.__with_libyaml__ is False
    assert y.__spec__.origin.startswith('held-pyyaml-6.0.3://')
    assert getattr(y, '__file__', None) is None
    assert list(y.__path__) == []
    assert importlib.util.find_spec('yaml').origin.startswith('held-pyyaml-6.0.3://')
    assert y.safe_load('p: {q: [1, 2], r: null}') == {'p': {'q': [1, 2], 'r': None}}
    assert y.safe_load(y.safe_dump({'k': [True, None, 'v', 3.5]})) == {'k': [True, None, 'v', 3.5]}
    assert y.safe_load('x: &a [1, 2]\\ny: *a')['y'] == [1, 2]
    assert y.safe_load('b: &b {k: 1}\\ni:\\n  <<: *b\\n  k: 2\\n') == {'b': {'k': 1}, 'i': {'k': 2}}
    # This pinned upstream 6.0.3 wheel resolves duplicate plain keys
    # last-one-wins; assert the real pinned semantics.
    assert y.safe_load('a: 1\\na: 2\\n') == {'a': 2}
    try:
        y.safe_load('a: b: c\\n')
    except y.scanner.ScannerError:
        pass
    else:
        raise AssertionError('bad mapping accepted')
    assert len([n for n in sys.modules if n == 'yaml' or n.startswith('yaml.')]) == 16
    assert 'yaml.cyaml' not in sys.modules
    assert sorted(y.__spec__.loader.owned()) == sorted(runtime._HELD_MODULE_FULLNAMES)
    for bad in ('yaml._yaml', 'yaml.unknown_name', '_yaml'):
        try:
            __import__(bad)
        except ModuleNotFoundError:
            pass
        else:
            raise AssertionError('blocked import resolved: ' + bad)
    assert len(calls) == 19
assert not any(n == 'yaml' or n.startswith('yaml.') or n == '_yaml' for n in sys.modules)
assert runtime._loaded is None
print('HELD_YAML_ISOLATED_OK calls=%d' % len(calls))
"""


@pytest.mark.parametrize('owner_result', [None, True])
def test_real_guard_return_contract(runtime, assets, clean_namespace, owner_result):
    with runtime.held_yaml(assets.archive, assets.provenance,
                           lambda: owner_result) as y:
        assert y.safe_load('valid: true') == {'valid': True}
    assert not _yaml_names()


@pytest.mark.parametrize('error_type', [RuntimeError, KeyboardInterrupt])
def test_post_import_owner_failure_cleans_before_enter_returns(
        runtime, assets, clean_namespace, error_type):
    calls = []
    before = list(sys.meta_path)

    def check():
        calls.append(1)
        if len(calls) == 19:
            assert 'yaml' in sys.modules
            raise error_type('owned attestation refused')

    with pytest.raises(error_type):
        runtime.held_yaml(assets.archive, assets.provenance, check).__enter__()
    assert len(calls) == 19
    assert not _yaml_names()
    assert sys.meta_path == before


def test_foreign_none_sentinel_is_preserved_and_refused(runtime, assets, clean_namespace):
    with pytest.raises(ValueError, match='paid_yaml_ambient_refused'):
        with runtime.held_yaml(assets.archive, assets.provenance, lambda: None):
            sys.modules['yaml'] = None
    assert 'yaml' in sys.modules and sys.modules['yaml'] is None
    del sys.modules['yaml']


def test_foreign_namespace_addition_is_preserved_and_refused(runtime, assets, clean_namespace):
    foreign = ModuleType('yaml.foreign')
    with pytest.raises(ValueError, match='paid_yaml_ambient_refused'):
        with runtime.held_yaml(assets.archive, assets.provenance, lambda: None):
            sys.modules['yaml.foreign'] = foreign
    assert sys.modules['yaml.foreign'] is foreign
    del sys.modules['yaml.foreign']


def test_completed_module_removal_is_refused(runtime, assets, clean_namespace):
    with pytest.raises(ValueError, match='paid_yaml_ambient_refused'):
        with runtime.held_yaml(assets.archive, assets.provenance, lambda: None):
            del sys.modules['yaml.scanner']
    assert not _yaml_names()


def test_foreign_finder_prepend_is_preserved_and_refused(runtime, assets, clean_namespace):
    foreign = object()
    try:
        with pytest.raises(ValueError, match='paid_yaml_ambient_refused'):
            with runtime.held_yaml(assets.archive, assets.provenance, lambda: None):
                sys.meta_path.insert(0, foreign)
        assert sys.meta_path[0] is foreign
        assert not _yaml_names()
    finally:
        sys.meta_path.remove(foreign)


def test_duplicate_owned_finder_is_fully_removed_and_refused(runtime, assets, clean_namespace):
    before = list(sys.meta_path)
    with pytest.raises(ValueError, match='paid_yaml_ambient_refused'):
        with runtime.held_yaml(assets.archive, assets.provenance, lambda: None) as y:
            finder = y.__spec__.loader
            sys.meta_path.append(finder)
    assert not _yaml_names()
    assert not any(item is finder for item in sys.meta_path)
    assert sys.meta_path == before
