"""Held attended sources selected by the incumbent Darwin Executive release.

This module reads published source observations, never private Control contents,
credentials or enrollment. It preserves the original engine/lib import identity.
"""
from __future__ import annotations

from contextlib import contextmanager

import ctypes
import errno
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import sys
from threading import RLock
import types

from .errors import HermesFabricError

_SYSTEM = Path("/Library/Application Support/MastermindExecutive")
_OBSERVATION = _SYSTEM / "config/control-observation.json"
_CONTROL = _SYSTEM / "config/control.json"
_PLIST = Path("/Library/LaunchDaemons/com.mastermind.executive.control.plist")
_MANIFEST = ".executive-release-manifest.json"
_PROJECTION = "native-dependencies/hermes-attended-macro"
_INVENTORY = "native-dependencies/hermes-attended-inventory.json"
_RECEIPT = "native-dependencies/hermes-attended-sources.json"
_COMMITMENT = "integrations/hermes_application_fabric/macro-source.json"
_VERIFIER = "ops/executive_os/native_gateway_sources.py"
_CONFIG_HELPER = "ops/executive_os/hermes_attended_configuration.py"
_CONFIG_FIELD = "hermes_attended_configuration_sha256"
_PREFIXES = ("config", "engine", "lib")
_SHA = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHARED = None
_SHARED_LOCK = RLock()


def _refuse():
    raise HermesFabricError("hermes_fabric_source_unavailable")


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _refuse()
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: _refuse())
    except (ValueError, UnicodeError, RecursionError):
        _refuse()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _identity(info, *, directory=False):
    common = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)
    # Ancestors are shared system directories. Their unrelated child changes
    # do not select a different release. NativeSourceClosure checks complete
    # dependency membership and directory identities within each source root.
    return common if directory else common + (
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _no_acl(fd, directory):
    if sys.platform != "darwin":
        _refuse()
    libc = ctypes.CDLL(None, use_errno=True)
    get = libc.acl_get_fd_np
    get.argtypes, get.restype = [ctypes.c_int, ctypes.c_int], ctypes.c_void_p
    entry = libc.acl_get_entry
    entry.argtypes, entry.restype = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)], ctypes.c_int
    free = libc.acl_free
    free.argtypes, free.restype = [ctypes.c_void_p], ctypes.c_int
    ctypes.set_errno(0)
    acl = get(fd, 0x00000100)
    if not acl:
        if ctypes.get_errno() == errno.ENOENT:
            return
        _refuse()
    pointer = ctypes.c_void_p()
    clear = False
    try:
        # Darwin: zero means an entry; one means there are no entries.
        clear = entry(acl, 0, ctypes.byref(pointer)) == 1
    finally:
        released = free(acl) == 0
    if not clear or not released:
        _refuse()


class _FixedReleaseReader:
    """Retain source descriptors; root ownership and direct ancestry are fixed."""
    def __init__(self):
        self.records = {}
        self.closed = False

    def hold(self, path, *, directory=False):
        path = Path(path)
        if self.closed or not path.is_absolute() or ".." in path.parts:
            _refuse()
        if path in self.records:
            fd, identity, kind = self.records[path]
            if kind is not directory:
                _refuse()
            self._check_one(path, fd, identity, kind)
            return fd
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        if directory:
            flags |= os.O_DIRECTORY
        if path == Path("/"):
            fd = os.open(path, flags)
        else:
            parent = self.hold(path.parent, directory=True)
            fd = os.open(path.name, flags, dir_fd=parent)
        try:
            info = os.fstat(fd)
            allowed_gid = (0, 80) if path == Path("/Library/Application Support") else (0,)
            if (not (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
                    or info.st_uid != 0 or info.st_gid not in allowed_gid
                    or info.st_mode & 0o7022
                    or (stat.S_IMODE(info.st_mode) & (0o005 if directory else 0o004))
                        != (0o005 if directory else 0o004)
                    or not directory and info.st_nlink != 1):
                _refuse()
            _no_acl(fd, directory)
            identity = _identity(info, directory=directory)
            self.records[path] = (fd, identity, directory)
            self._check_one(path, fd, identity, directory)
            return fd
        except BaseException:
            self.records.pop(path, None)
            os.close(fd)
            raise

    def _check_one(self, path, fd, identity, directory):
        observed = os.fstat(fd)
        if _identity(observed, directory=directory) != identity:
            _refuse()
        _no_acl(fd, directory)
        if path == Path("/"):
            named = os.stat(path, follow_symlinks=False)
        else:
            parent = self.records.get(path.parent)
            if parent is None:
                _refuse()
            named = os.stat(path.name, dir_fd=parent[0], follow_symlinks=False)
        if _identity(named, directory=directory) != identity:
            _refuse()

    def read(self, path, limit):
        fd = self.hold(path)
        self.check()
        size = os.fstat(fd).st_size
        if type(limit) is not int or not 0 <= size <= limit:
            _refuse()
        raw = bytearray()
        os.lseek(fd, 0, os.SEEK_SET)
        while len(raw) <= size:
            part = os.read(fd, min(65536, size + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        if len(raw) != size:
            _refuse()
        self.check()
        return bytes(raw)

    def check(self):
        if self.closed:
            _refuse()
        for path, (fd, identity, directory) in tuple(self.records.items()):
            self._check_one(path, fd, identity, directory)

    def close(self):
        if self.closed:
            return
        self.closed = True
        for fd, _, _ in self.records.values():
            os.close(fd)
        self.records.clear()


def _package_read(path, limit):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or not 0 <= before.st_size <= limit):
            _refuse()
        raw = bytearray()
        while len(raw) <= before.st_size:
            part = os.read(fd, min(65536, before.st_size + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        if (len(raw) != before.st_size or _identity(os.fstat(fd)) != _identity(before)
                or _identity(os.stat(path, follow_symlinks=False)) != _identity(before)):
            _refuse()
        return bytes(raw)
    finally:
        os.close(fd)


def attended_package_digest():
    """The complete installed adapter payload, independent of PM build metadata."""
    package = Path(__file__).resolve().parent
    document = _json(_package_read(package / "attended-runtime-files.json", 16384))
    files = document.get("files") if type(document) is dict else None
    if (type(document) is not dict or set(document) != {"schema", "files"}
            or document["schema"] != "mastermind.hermes_attended_adapter_files/v1"
            or type(files) is not list or not 1 <= len(files) <= 64
            or any(type(p) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", p)
                   or any(part in {".", ".."} for part in p.split("/")) for p in files)
            or files != sorted(set(files)) or "attended-runtime-files.json" not in files):
        _refuse()
    rows = []
    for relative in files:
        path = package / relative
        if path.is_symlink() or path.resolve().parent != (package / relative).parent.resolve():
            _refuse()
        for parent in path.parents:
            if parent == package.parent:
                break
            if parent.is_symlink():
                _refuse()
        raw = _package_read(path, 4 * 1024 * 1024)
        rows.append([relative, hashlib.sha256(raw).hexdigest()])
    return hashlib.sha256(_canonical(rows)).hexdigest()



class _ControlSelection:
    """One held observation of the existing selector, never private config data."""
    def __init__(self):
        self.owner = _FixedReleaseReader()
        self.closure = None
        try:
            observation = _json(self.owner.read(_OBSERVATION, 8192))
            base = {"schema", "source_release_sha", "control_sha256", "control_identity",
                    "control_uid", "python_runtime_provenance_digest", "control_acl_absent"}
            extended = type(observation) is dict and observation.get("schema") == "mastermind.control_observation/v2"
            fields = base | {_CONFIG_FIELD} if extended else base
            if (type(observation) is not dict or set(observation) != fields
                    or observation["schema"] != ("mastermind.control_observation/v2" if extended
                                                 else "mastermind.control_observation/v1")
                    or type(observation["source_release_sha"]) is not str
                    or _COMMIT.fullmatch(observation["source_release_sha"]) is None
                    or any(type(observation[key]) is not str or _SHA.fullmatch(observation[key]) is None
                           or set(observation[key]) == {"0"}
                           for key in ("control_sha256", "python_runtime_provenance_digest"))
                    or extended and (type(observation[_CONFIG_FIELD]) is not str
                                     or _SHA.fullmatch(observation[_CONFIG_FIELD]) is None
                                     or set(observation[_CONFIG_FIELD]) == {"0"})
                    or type(observation["control_uid"]) is not int
                    or not 0 < observation["control_uid"] < 2 ** 31
                    or observation["control_acl_absent"] is not True
                    or type(observation["control_identity"]) is not list
                    or len(observation["control_identity"]) != 9
                    or any(type(value) is not int for value in observation["control_identity"])):
                _refuse()
            if stat.S_IMODE(os.fstat(self.owner.hold(_OBSERVATION)).st_mode) != 0o444:
                _refuse()
            self.control_identity = tuple(observation["control_identity"])
            self.control_uid = observation["control_uid"]
            self.release_root = _SYSTEM / "releases" / observation["source_release_sha"]
            self.configuration_digest = observation.get(_CONFIG_FIELD)
            self.root = None
            self.check()
        except BaseException:
            self.close()
            raise

    def check(self):
        self.owner.check()
        parent = self.owner.hold(_CONTROL.parent, directory=True)
        info = os.stat(_CONTROL.name, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o440
                or info.st_uid != 0 or info.st_gid != self.control_uid or info.st_nlink != 1
                or not 0 < info.st_size <= 4 * 1024 * 1024
                or _identity(info) != self.control_identity):
            _refuse()
        if self.closure is not None:
            self.closure.check()

    def close(self):
        if self.closure is not None:
            self.closure.close()
        self.owner.close()


class _SourceContext(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, adapter_digest):
        self.owner = _FixedReleaseReader()
        self.closure = None
        self.modules = {}
        self.pending = {}
        self.import_failed = False
        self.references = 0
        self.closed = False
        self.lock = RLock()
        self.adapter_digest = adapter_digest
        try:
            self._select_release()
            self._open_sources()
            if any(name in {"engine", "lib"} or name.startswith(("engine.", "lib."))
                   for name in sys.modules):
                _refuse()
            sys.meta_path.insert(0, self)
            self.check()
        except BaseException:
            self.close()
            raise

    def _select_release(self):
        selected = _ControlSelection()
        try:
            self.root = selected.release_root
        finally:
            selected.close()
        launch = plistlib.loads(self.owner.read(_PLIST, 1024 * 1024))
        args = launch.get("ProgramArguments") if type(launch) is dict else None
        if (type(args) is not list or any(type(value) is not str for value in args)
                or args.count("--release-root") != 1
                or args.index("--release-root") + 1 >= len(args)
                or args[args.index("--release-root") + 1] != str(self.root)
                or launch.get("WorkingDirectory") != str(self.root)
                or launch.get("Label") != "com.mastermind.executive.control"):
            _refuse()
        self._check_control()
        manifest = _json(self.owner.read(self.root / _MANIFEST, 32 * 1024 * 1024))
        if (type(manifest) is not dict
                or manifest.get("schema_version") != "mastermind.executive_release_manifest/v1"
                or manifest.get("commit_sha") != self.root.name
                or type(manifest.get("tree_sha")) is not str
                or _COMMIT.fullmatch(manifest["tree_sha"]) is None
                or type(manifest.get("entries")) is not list):
            _refuse()
        self.entries = {}
        for row in manifest["entries"]:
            path = row.get("path") if type(row) is dict else None
            if (type(path) is not str or not path or path.startswith("/") or "\\" in path
                    or any(p in {"", ".", ".."} for p in path.split("/"))
                    or path in self.entries):
                _refuse()
            self.entries[path] = row

    def _check_control(self):
        # Configuration renewal can keep the same code owner. Observe the
        # current release without pinning a selector inode for the plugin life.
        selected = _ControlSelection()
        try:
            if selected.release_root != self.root:
                _refuse()
        finally:
            selected.close()

    def _sealed_read(self, relative, limit):
        row = self.entries.get(relative)
        if (type(row) is not dict or row.get("type") != "file"
                or row.get("uid") != 0 or row.get("gid") != 0
                or type(row.get("size")) is not int or not 0 <= row["size"] <= limit
                or type(row.get("mode")) is not int
                or type(row.get("sha256")) is not str or _SHA.fullmatch(row["sha256"]) is None):
            _refuse()
        path = self.root / relative
        raw = self.owner.read(path, limit)
        info = os.fstat(self.owner.hold(path))
        if (len(raw) != row["size"] or stat.S_IMODE(info.st_mode) != row["mode"]
                or hashlib.sha256(raw).hexdigest() != row["sha256"]):
            _refuse()
        return raw

    def _open_sources(self):
        receipt = _json(self._sealed_read(_RECEIPT, 8192))
        commitment = _json(self._sealed_read(_COMMITMENT, 8192))
        roots = [str(self.root / _PROJECTION / prefix) for prefix in _PREFIXES]
        if (type(receipt) is not dict or set(receipt) != {
                "schema", "release_sha", "repository", "commit", "tree", "projection",
                "material_manifest_sha256", "archive_sha256", "adapter_package_sha256",
                "dependency_inventory", "import_roots"}
                or type(commitment) is not dict or set(commitment) != {
                    "schema", "repository", "commit", "tree", "projection",
                    "material_manifest_sha256", "archive_sha256", "archive_size"}
                or commitment["schema"] != "mastermind.hermes_attended_source_projection/v1"
                or receipt["schema"] != "mastermind.hermes_attended_installed_sources/v1"
                or receipt["release_sha"] != self.root.name
                or receipt["repository"] != "mastermindx-market-intelligence/macro"
                or receipt["projection"] != "engine-lib-config/v1"
                or receipt["adapter_package_sha256"] != self.adapter_digest
                or receipt["import_roots"] != roots
                or any(receipt[key] != commitment[key] for key in
                       ("repository", "commit", "tree", "projection",
                        "material_manifest_sha256", "archive_sha256"))
                or any(type(receipt[key]) is not str or _COMMIT.fullmatch(receipt[key]) is None
                       for key in ("commit", "tree"))
                or any(type(receipt[key]) is not str or _SHA.fullmatch(receipt[key]) is None
                       for key in ("material_manifest_sha256", "archive_sha256"))):
            _refuse()
        inventory = receipt["dependency_inventory"]
        if (type(inventory) is not dict or set(inventory) != {"path", "sha256", "size"}
                or inventory["path"] != str(self.root / _INVENTORY)
                or type(inventory["sha256"]) is not str or _SHA.fullmatch(inventory["sha256"]) is None
                or type(inventory["size"]) is not int or not 1 <= inventory["size"] <= 8 * 1024 * 1024):
            _refuse()
        raw = self._sealed_read(_INVENTORY, 8 * 1024 * 1024)
        if len(raw) != inventory["size"] or hashlib.sha256(raw).hexdigest() != inventory["sha256"]:
            _refuse()
        source = self._sealed_read(_VERIFIER, 1024 * 1024)
        verifier = types.ModuleType("_mastermind_attended_native_sources")
        verifier.__file__ = str(self.root / _VERIFIER)
        exec(compile(source, verifier.__file__, "exec"), verifier.__dict__)
        self.closure = verifier.NativeSourceClosure(
            self.owner, {"import_roots": roots, "dependency_inventory": inventory}, _no_acl)
        self.projection = self.root / _PROJECTION
        self.commitment = commitment
        self.verifier = verifier

    def configuration(self):
        """Freeze the current consumer view for one catalog or native turn."""
        self.check()
        selected = _ControlSelection()
        try:
            if selected.release_root != self.root:
                _refuse()
            selected.root = self.projection
            if selected.configuration_digest is not None:
                source = self._sealed_read(_CONFIG_HELPER, 1024 * 1024)
                helper = types.ModuleType("_mastermind_attended_configuration")
                helper.__file__ = str(self.root / _CONFIG_HELPER)
                exec(compile(source, helper.__file__, "exec"), helper.__dict__)
                inputs = {}
                for relative in helper.INPUTS:
                    prefix, name = relative.split("/", 1)
                    row = self.closure.expected[self.projection / prefix][name]
                    raw = self.owner.read(self.projection / relative, helper.MAX_BYTES)
                    if row["size"] != len(raw) or row["sha256"] != hashlib.sha256(raw).hexdigest():
                        _refuse()
                    inputs[relative] = raw
                selected.root = _SYSTEM / "config" / helper.DIRECTORY / selected.configuration_digest
                raw = selected.owner.read(selected.root / helper.CAPSULE_FILE, helper.MAX_BYTES)
                _, files = helper.validate_capsule(
                    raw, selected.configuration_digest, self.commitment, inputs)
                inventory = helper.inventory_bytes(files, selected.root)
                inventory_path = selected.root / helper.INVENTORY_FILE
                if selected.owner.read(inventory_path, helper.MAX_BYTES) != inventory:
                    _refuse()
                selected.closure = self.verifier.NativeSourceClosure(
                    selected.owner, {
                        "import_roots": [str(selected.root / "config")],
                        "dependency_inventory": {
                            "path": str(inventory_path), "size": len(inventory),
                            "sha256": hashlib.sha256(inventory).hexdigest()},
                    }, _no_acl)
            selected.check()
            self.check()
            return selected
        except BaseException:
            selected.close()
            raise

    def check(self):
        with self.lock:
            if self.closed:
                _refuse()
            self._check_import()
            if self.closure is not None:
                self.closure.check()
            self.owner.check()

    def factory(self, configuration_root):
        # Python owns per-module import locks. Never hold our state lock while
        # acquiring those locks or executing the original factory's module code.
        self.check()
        from engine import provider_production_modes as owner
        if Path(owner.__file__) != self.projection / "engine/provider_production_modes.py":
            _refuse()
        result = owner.make_application_fabric_factory(
            mode_id="shared_fabric", lane="hermes-attended",
            service_mode_id="hermes_attended_fabric",
            workload_cfg={"workload_profile": "hermes_attended", "provider_order": ["fabric"]},
            root=configuration_root)
        self.check()
        return result

    def _check_import(self):
        if self.closed or self.import_failed:
            _refuse()
        self.owner.check()
        self._check_control()
        for name, module in tuple(sys.modules.items()):
            if name not in {"engine", "lib"} and not name.startswith(("engine.", "lib.")):
                continue
            pending = self.pending.get(name)
            if self.modules.get(name) is not module and not (
                    pending is not None and getattr(module, "__spec__", None) is pending
                    and getattr(module, "__loader__", None) is self):
                _refuse()
        if any(sys.modules.get(name) is not module for name, module in self.modules.items()):
            _refuse()

    def find_spec(self, fullname, path=None, target=None):
        parts = fullname.split(".")
        if parts[0] not in {"engine", "lib"}:
            return None
        with self.lock:
            self._check_import()
            if target is not None or fullname in self.modules or fullname in self.pending:
                _refuse()
            if any(not part.isidentifier() for part in parts):
                _refuse()
            root = self.projection / parts[0]
            candidate = root.joinpath(*parts[1:])
            expected = self.closure.expected[root]
            package = candidate / "__init__.py"
            module = candidate.with_suffix(".py")
            package_key = str(package.relative_to(root))
            module_key = str(module.relative_to(root)) if module.is_relative_to(root) else ""
            if package_key in expected and expected[package_key]["type"] == "file":
                filename, is_package = package, True
            elif module_key in expected and expected[module_key]["type"] == "file":
                filename, is_package = module, False
            elif candidate == root or expected.get(str(candidate.relative_to(root)), {}).get("type") == "directory":
                filename, is_package = None, True
            else:
                raise ModuleNotFoundError(f"No verified module named {fullname!r}", name=fullname)
            spec = importlib.machinery.ModuleSpec(fullname, self, origin=str(filename) if filename else None,
                                                  is_package=is_package)
            spec.has_location = filename is not None
            spec.loader_state = filename
            if is_package:
                spec.submodule_search_locations = [str(candidate)]
            self.pending[fullname] = spec
            return spec

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        # An import is an operation too; unloading the plugin cannot close its
        # retained reader while Python is executing this verified module.
        with _SHARED_LOCK:
            with self.lock:
                if (self.closed or module.__name__ in self.modules
                        or self.pending.get(module.__name__) is not module.__spec__):
                    _refuse()
                operation = _SourceLease(self)
                self.modules[module.__name__] = module
        try:
            with self.lock:
                self._check_import()
                filename = module.__spec__.loader_state
                raw = None
                if filename is not None:
                    root = self.projection / module.__name__.split(".")[0]
                    entry = self.closure.expected[root][str(filename.relative_to(root))]
                    raw = self.owner.read(filename, entry["size"])
                    if len(raw) != entry["size"] or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                        _refuse()
                    module.__file__ = str(filename)
            if raw is not None:
                exec(compile(raw, str(filename), "exec"), module.__dict__)
            with self.lock:
                self.pending.pop(module.__name__, None)
                self._check_import()
        except BaseException:
            with self.lock:
                self.pending.pop(module.__name__, None)
                self.modules.pop(module.__name__, None)
                self.import_failed = True
            raise
        finally:
            operation.close()

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            if self in sys.meta_path:
                sys.meta_path.remove(self)
            for name, module in reversed(tuple(self.modules.items())):
                if sys.modules.get(name) is module:
                    del sys.modules[name]
            self.modules.clear()
            self.pending.clear()
            if self.closure is not None:
                self.closure.close()
            self.owner.close()


class _SourceLease:
    def __init__(self, context):
        self._context = context
        self._closed = False
        self._configuration = None
        self._configuration_lock = RLock()
        context.references += 1

    def check(self):
        if self._closed:
            _refuse()
        self._context.check()
        if self._configuration is not None:
            self._configuration.check()

    def factory(self):
        self.check()
        with self._configuration_lock:
            if self._closed:
                _refuse()
            if self._configuration is None:
                self._configuration = self._context.configuration()
            configuration_root = self._configuration.root
        result = self._context.factory(configuration_root)
        self.check()
        return result

    @contextmanager
    def operation(self):
        # Retain sources across catalog inspection and the entire admitted turn,
        # including original-owner close. Plugin unload only drops its own lease.
        with _SHARED_LOCK:
            self.check()
            borrowed = _SourceLease(self._context)
        try:
            yield borrowed
        finally:
            borrowed.close()

    def close(self):
        global _SHARED
        with _SHARED_LOCK:
            if self._closed:
                return
            self._closed = True
            with self._configuration_lock:
                if self._configuration is not None:
                    self._configuration.close()
            self._context.references -= 1
            if self._context.references == 0:
                self._context.close()
                if _SHARED is self._context:
                    _SHARED = None


def open_attended_source_context(*, adapter_package_sha256):
    """Acquire the selected immutable sources; accepts no caller source path."""
    global _SHARED
    with _SHARED_LOCK:
        if (sys.platform != "darwin" or type(adapter_package_sha256) is not str
                or _SHA.fullmatch(adapter_package_sha256) is None):
            _refuse()
        candidate = None
        try:
            if _SHARED is None:
                candidate = _SourceContext(adapter_package_sha256)
                candidate.check()
                lease = _SourceLease(candidate)
                _SHARED = candidate
                return lease
            if _SHARED.adapter_digest != adapter_package_sha256:
                _refuse()
            _SHARED.check()
            return _SourceLease(_SHARED)
        except BaseException as error:
            if candidate is not None and candidate.references == 0:
                candidate.close()
            if isinstance(error, HermesFabricError):
                raise
            if isinstance(error, Exception):
                _refuse()
            raise
