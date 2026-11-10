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
