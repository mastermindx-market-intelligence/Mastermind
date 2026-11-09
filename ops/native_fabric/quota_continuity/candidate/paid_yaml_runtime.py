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


# ---------------------------------------------------------------------------
# Executor-owned held-byte import path (new; separate lifecycle).
#
# held_yaml installs the same pinned pure PyYAML closure from exact in-memory
# bytes for the lifetime of one `with` block.  It never reads or writes the
# Root `_loaded` cache, never reopens the archive or any path, never uses
# zipimport, sys.path, site packages or pip, and removes exactly its own
# finder and module objects afterwards.  Any pre-existing `yaml`, `yaml.*` or
# `_yaml` namespace is refused, never adopted.
# ---------------------------------------------------------------------------

_HELD_PACKAGE_MEMBERS = (
    'LICENSE',
    'METADATA',
    'yaml/__init__.py',
    'yaml/composer.py',
    'yaml/constructor.py',
    'yaml/cyaml.py',
    'yaml/dumper.py',
    'yaml/emitter.py',
    'yaml/error.py',
    'yaml/events.py',
    'yaml/loader.py',
    'yaml/nodes.py',
    'yaml/parser.py',
    'yaml/reader.py',
    'yaml/representer.py',
    'yaml/resolver.py',
    'yaml/scanner.py',
    'yaml/serializer.py',
    'yaml/tokens.py',
)


def _held_fullname(member):
    stem = member[len('yaml/'):-len('.py')]
    return 'yaml' if stem == '__init__' else 'yaml.' + stem


_HELD_MEMBER_OF = dict(
    (_held_fullname(name), name)
    for name in _HELD_PACKAGE_MEMBERS if name.endswith('.py'))
_HELD_MODULE_FULLNAMES = tuple(sorted(_HELD_MEMBER_OF))
_HELD_ORIGIN = 'held-pyyaml-6.0.3'
_HELD_BINARY_SUFFIXES = ('.so', '.pyd', '.dll', '.dylib', '.exe')
_HELD_BINARY_NAMES = ('_yaml', 'yaml._yaml')
_HELD_PROVENANCE_SCHEMA = 'mastermind.paid_pure_yaml_source/v1'


def _held_origin(fullname):
    return '%s://%s' % (_HELD_ORIGIN, _HELD_MEMBER_OF[fullname])


def _reject_held_ambient():
    """Refuse any pre-existing yaml namespace; never adopt an ambient package."""
    for name in sys.modules:
        if name == 'yaml' or name.startswith('yaml.') or name == '_yaml':
            raise ValueError('paid_yaml_ambient_refused')


def _held_provenance(provenance_raw):
    """Parse and attest the exact pinned provenance bytes."""
    if type(provenance_raw) is not bytes:
        raise ValueError('paid_yaml_source_refused')
    if hashlib.sha256(provenance_raw).hexdigest() != PROVENANCE_SHA256:
        raise ValueError('paid_yaml_source_refused')
    try:
        provenance = json.loads(provenance_raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError('paid_yaml_source_refused') from error
    if not isinstance(provenance, dict):
        raise ValueError('paid_yaml_source_refused')
    files = provenance.get('files')
    if (provenance.get('package') != 'PyYAML'
            or provenance.get('version') != '6.0.3'
            or provenance.get('artifact_sha256') != ARTIFACT_SHA256
            or provenance.get('zip_sha256') != ZIP_SHA256
            or provenance.get('schema') != _HELD_PROVENANCE_SCHEMA
            or provenance.get('excluded_binary_extensions') is not True
            or not isinstance(files, dict)):
        raise ValueError('paid_yaml_source_refused')
    for item in files.values():
        if (not isinstance(item, dict)
                or type(item.get('bytes')) is not int
                or not 0 < item['bytes'] <= 1048576
                or type(item.get('sha256')) is not str
                or len(item['sha256']) != 64
                or item['sha256'] != item['sha256'].lower()
                or any(c not in '0123456789abcdef' for c in item['sha256'])):
            raise ValueError('paid_yaml_source_refused')
    return provenance


def _held_member_table(archive_raw, provenance):
    """Read the pinned members once, in memory, and return the module table.

    The duplicate-free exact member inventory, per-member byte length and
    hash, the 19 member / 17 pure module counts and the absence of executable
    binary extensions are all enforced before any module is served.
    """
    if type(archive_raw) is not bytes:
        raise ValueError('paid_yaml_source_refused')
    files = provenance['files']
    if tuple(sorted(files)) != _HELD_PACKAGE_MEMBERS:
        raise ValueError('paid_yaml_source_refused')
    if len(files) != 19 or len([n for n in files if n.endswith('.py')]) != 17:
        raise ValueError('paid_yaml_source_refused')
    sources = {}
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        names = archive.namelist()
        if (len(names) != len(set(names)) or set(names) != set(files)
                or any(name.endswith(_HELD_BINARY_SUFFIXES) for name in names)):
            raise ValueError('paid_yaml_source_refused')
        for name in _HELD_PACKAGE_MEMBERS:
            raw = archive.read(name)
            if (len(raw) != files[name]['bytes']
                    or hashlib.sha256(raw).hexdigest() != files[name]['sha256']):
                raise ValueError('paid_yaml_source_refused')
            if name.endswith('.py'):
                sources[_held_fullname(name)] = raw
    if tuple(sorted(sources)) != _HELD_MODULE_FULLNAMES:
        raise ValueError('paid_yaml_source_refused')
    return sources


class _HeldYamlFinder:
    """Finite in-memory finder/loader for exactly the pinned pure modules.

    Only the admitted `yaml`/`yaml.*` names are served, from the validated
    table, at virtual origins with an empty package search location.  Unknown
    `yaml.*` names and the `_yaml`/`yaml._yaml` compiled extension are refused
    with ModuleNotFoundError so no later finder can search disk for an
    ambient replacement.
    """

    def __init__(self, sources, owner):
        self._sources = sources
        self._owner = owner
        self._codes = {}
        self._owned = {}
        self._completed = set()

    def find_spec(self, fullname, path=None, target=None):
        if fullname in _HELD_BINARY_NAMES:
            raise ModuleNotFoundError(
                'held yaml closure excludes the compiled extension %r' % (fullname,),
                name=fullname)
        if fullname != 'yaml' and not fullname.startswith('yaml.'):
            return None
        if fullname not in self._sources:
            raise ModuleNotFoundError(
                'held yaml closure does not contain %r' % (fullname,),
                name=fullname)
        return importlib.util.spec_from_loader(
            fullname, self, origin=_held_origin(fullname),
            is_package=fullname == 'yaml')

    def is_package(self, fullname):
        if fullname in self._sources:
            return fullname == 'yaml'
        raise ImportError(
            'held yaml closure does not contain %r' % (fullname,), name=fullname)

    def get_source(self, fullname):
        return self._source(fullname).decode('utf-8')

    def get_code(self, fullname):
        code = self._codes.get(fullname)
        if code is None:
            code = compile(self._source(fullname), _held_origin(fullname),
                           'exec', dont_inherit=True)
            self._codes[fullname] = code
        return code

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        fullname = module.__spec__.name
        self._owner('exec:%s' % fullname)
        # Record the exact object before executing so a partial import stays
        # owned and is cleaned exactly like a completed one.
        self._owned[fullname] = module
        exec(self.get_code(fullname), module.__dict__)
        self._completed.add(fullname)

    def _source(self, fullname):
        source = self._sources.get(fullname)
        if source is None:
            raise ImportError(
                'held yaml closure does not contain %r' % (fullname,), name=fullname)
        return source

    def owned(self):
        """Snapshot of the exact module objects recorded before execution."""
        return dict(self._owned)


class _HeldYaml:
    """Context manager that installs and removes exactly the held yaml closure."""

    def __init__(self, sources, check):
        self._sources = sources
        self._check = check
        self._finder = None
        self._module = None
        self._entered = False

    def _finder_check(self):
        finder = self._finder
        if finder is not None and (not sys.meta_path or sys.meta_path[0] is not finder
                or sum(item is finder for item in sys.meta_path) != 1):
            raise ValueError('paid_yaml_ambient_refused')

    def _owner(self, stage):
        self._finder_check()
        if not callable(self._check):
            raise ValueError('paid_yaml_owner_refused')
        result = self._check()
        # Existing descriptor owners are guards: successful check() returns
        # None; an exception refuses. Permit explicit True, never truthiness.
        if result is not None and result is not True:
            raise ValueError('paid_yaml_owner_refused')
        self._finder_check()

    def __enter__(self):
        if self._entered or self._finder is not None:
            raise ValueError('paid_yaml_state_refused')
        self._owner('enter')
        _reject_held_ambient()
        finder = _HeldYamlFinder(self._sources, self._owner)
        self._finder = finder
        self._entered = True
        # Installed ahead of every other finder: unknown yaml names must be
        # refused here instead of falling through to an ambient package.
        sys.meta_path.insert(0, finder)
        try:
            module = importlib.import_module('yaml')
            if sys.modules.get('yaml') is not module:
                raise ValueError('paid_yaml_source_refused')
            if module.__version__ != '6.0.3' or module.__with_libyaml__ is not False:
                raise ValueError('paid_yaml_source_refused')
            self._owner('attested')
        except BaseException:
            if self._cleanup():
                raise ValueError('paid_yaml_ambient_refused')
            raise
        self._module = module
        return module

    def __exit__(self, exc_type, exc_value, tb):
        try:
            try:
                self._owner('exit')
            finally:
                drift = self._cleanup()
            if drift:
                raise ValueError('paid_yaml_ambient_refused')
        finally:
            self._module = None
        return False

    def _cleanup(self):
        """Remove exactly the owned finder and owned module objects.

        A slot now holding a foreign object is preserved untouched and
        reported as drift so the replacement stays a visible failure; a slot
        the body already emptied has nothing of ours left to remove.
        """
        finder = self._finder
        drift = False
        if finder is not None:
            owned = finder.owned()
            for fullname in reversed(list(owned)):
                current = sys.modules.get(fullname)
                if current is owned[fullname]:
                    del sys.modules[fullname]
                elif fullname in sys.modules or fullname in finder._completed:
                    drift = True
            if any((name == 'yaml' or name.startswith('yaml.') or name == '_yaml')
                    and name not in owned for name in sys.modules):
                drift = True
            indices = [i for i, item in enumerate(sys.meta_path) if item is finder]
            if indices != [0]:
                drift = True
            for index in reversed(indices):
                del sys.meta_path[index]
            self._finder = None
        return drift


def held_yaml(archive_raw, provenance_raw, check):
    """Return a context manager installing the pinned pure PyYAML closure.

    Usage:

        with held_yaml(archive_raw, provenance_raw, owner_check) as yaml:
            ...

    archive_raw and provenance_raw must be the exact immutable pinned byte
    objects, hash-bound below.  check must be a callable supplied by trusted
    entry code; it is called with no arguments before entry, before each
    module execution, after the package attestation and at context exit, and
    must return None (the existing guard contract) or True, or raise. Any
    other return value or namespace drift
    is a ValueError refusal: nothing is adopted, no path is reopened, no
    archive is re-read and no global cache is touched.  On exit exactly the
    owned finder and owned module objects are removed; foreign replacements
    are preserved and reported as a failure.
    """
    if type(archive_raw) is not bytes:
        raise ValueError('paid_yaml_source_refused')
    if hashlib.sha256(archive_raw).hexdigest() != ZIP_SHA256:
        raise ValueError('paid_yaml_source_refused')
    provenance = _held_provenance(provenance_raw)
    sources = _held_member_table(archive_raw, provenance)
    return _HeldYaml(sources, check)
